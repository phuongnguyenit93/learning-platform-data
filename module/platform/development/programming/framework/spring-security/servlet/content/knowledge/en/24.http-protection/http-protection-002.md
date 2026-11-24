# Cache-Control and Controlling Sensitive Content Caching in Spring Security Servlet

## 1. Objectives and scope

HTTP caching reduces latency and bandwidth: browsers, reverse proxies, or CDNs can retain a copy of a response for reuse. This is useful for public CSS, JavaScript, and images; however, it can **expose personal content, credentials, invoices, account data, or exported reports** if responses are stored and reused in the wrong context.

In a **Spring Security Servlet** application, the HTTP protection layer must emit clear caching policies for sensitive resources. This topic focuses on understanding `Cache-Control`, how Spring Security writes default headers, when `no-store` is needed, and when public resources can be cached to optimize performance.

After this lesson, you will be able to:
- Distinguish `no-store`, `no-cache`, `private`, `public`, `max-age`, `s-maxage`, `must-revalidate`, and `immutable` in terms of actual behavior.
- Explain why responses with cookies, authentication, or user information are not automatically safe across all caches.
- Use `SecurityFilterChain`, Spring MVC, and `ResponseEntity` configurations to protect sensitive data while properly caching static assets.
- Verify headers on actual responses and in `MockMvc`; troubleshoot issues across browsers, reverse proxies/CDNs, and Service Workers.

## 2. Where does caching occur and what are the risks?

A response from a Servlet application can pass through multiple layers:

```text
Browser
  |-- memory/disk HTTP cache
  |-- back/forward navigation history (bfcache has its own mechanism)
  |-- Service Worker + Cache API (if registered by the application)
        |
        v
Reverse proxy / CDN / API gateway (shared cache, depending on configuration)
        |
        v
Spring Security Filter Chain -> Spring MVC controller -> response
```

For example: `GET /api/me` returns Alice's name, email, and roles. If a CDN caches this response with `public, max-age=3600` and the cache key does not distinguish users, a subsequent request could receive Alice's content even though it belongs to Bob. Even when cache keys distinguish users, a browser on a shared machine can still keep sensitive responses in memory or on disk.

**Protection goal:** restrict or prevent HTTP caches from storing sensitive responses, especially in shared caches; prevent one user's data from appearing when another user reuses a session/browser; ensure logged-out sessions do not allow the UI to arbitrarily display stale data.

**Limitations:** `Cache-Control` is a directive for HTTP-compliant caches, **not a data-wiping tool**. It does not guarantee deletion of files downloaded by users, logs, screenshots, backend copies, content already rendered in RAM, or every state of bfcache/Service Workers. You must still use authentication, authorization, TLS, proper cache key design, and proper logout mechanisms.

## 3. Understanding Cache-Control directives properly

| Directive | Can caches store it? | Meaning for sensitive content |
| --- | --- | --- |
| `no-store` | Compliant caches must not store request/response per directive | **Preferred choice** for pages/JSON/confidential data; prevents HTTP caches from keeping a copy |
| `no-cache` | **May store**, but must revalidate with the server before reuse | Insufficient if the requirement is "do not store sensitive content" |
| `private` | Allows browser's private cache, forbids shared caches from storing per directive semantics | Helps avoid shared caches, but the browser may still store it; does not replace `no-store` |
| `public` | Allows shared caches to store, including some cases otherwise restricted | Use only for genuinely public resources |
| `max-age=600` | Response is considered fresh for up to 600 seconds from calculated age | Suitable for cacheable content; do not set on personal JSON |
| `s-maxage=600` | Sets freshness lifetime for **shared caches**, overriding `max-age` on shared caches | Requires tight CDN/reverse proxy control; do not use for private data |
| `must-revalidate` | Once stale, caches must revalidate before using | Does not prevent initial storage; often paired with `no-cache` or `max-age` |
| `immutable` | Indicates the resource is versioned and will not change while fresh | Only suitable for public assets with hashes/versioned names |
| `max-age=0` | Usually stale immediately, requiring revalidation before use | **Not** synonymous with forbidding storage |
| `no-transform` | Instructs intermediaries not to transform content | Not a cache-storage prevention directive |

Some examples:

```http
# Sensitive response: do not store in HTTP cache.
Cache-Control: no-store

# Cache may store, but must ask the server before reusing.
Cache-Control: no-cache

# Data may only be cached in the browser, not in a shared proxy.
Cache-Control: private, max-age=60

# Public asset with a fingerprint in the filename.
Cache-Control: public, max-age=31536000, immutable
```

`Pragma: no-cache` and `Expires: 0` commonly appear to support legacy HTTP clients; in modern systems, `Cache-Control` is the primary directive. `Expires: 0` is a legacy compatibility pattern often seen in Spring Security and does not mean all caches have been cleared.

**Practical rule:** for responses containing secrets or per-user data, use `no-store`; `private` alone only prevents shared caching, while `no-cache` alone still allows storing for revalidation.

## 4. Spring Security Servlet defaults

When default HTTP headers are enabled on `SecurityFilterChain`, Spring Security adds anti-caching headers for responses that do not already have a cache policy set by the application:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Spring Security uses `HeaderWriterFilter` and a cache header writer component (typically `CacheControlHeadersWriter`) to handle this. With the default configuration, these headers protect dynamic pages from standard HTTP caching.

Two points to remember:

1. **The default configuration does not automatically produce an optimal cache policy for every resource type.** A versioned public image may want longer caching, while a personal API needs `no-store`. Policies must be chosen based on sensitivity and content lifecycle.
2. **When the application has already set `Cache-Control`, Spring Security does not unconditionally overwrite it with the default cache headers.** Therefore, controllers, filters, Spring MVC resource handlers, reverse proxies, or CDNs can make the final policy differ from the assumption that "Spring Security will definitely block caching". Always verify the actual headers at the client boundary.

Distinguish `authorizeHttpRequests(...permitAll())` from `web.ignoring()`: `permitAll` still sends requests through the security filter chain and security headers; `web.ignoring()` bypasses the entire chain, which can drop needed headers and alter inspection behavior. For public assets, prefer `permitAll` and set explicit caching policies.

## 5. Choosing policies by resource

| Response type | Examples | Suggested policy | Rationale |
| --- | --- | --- | --- |
| Authenticated account pages | `/account`, `/settings` | `no-store` | Private data and mutable user state |
| APIs returning personal data | `/api/me`, `/api/orders` | `no-store` | Avoid copies in browser/shared caches |
| Login/logout/password change | Form pages with tokens, post-login/logout responses | `no-store` | Avoid storing sensitive content and state |
| Tokens, recovery codes, OTPs | `/api/session`, verification screens | `no-store` | Sensitive content, short-lived |
| Exports containing customer data | PDF/CSV reports, statements | `no-store` | `Content-Disposition: attachment` does not replace cache policy |
| Fingerprinted public images/CSS/JS | `/assets/app.a1b2c3.js` | `public, max-age=31536000`; consider `immutable` | Content immutable by version, safe to cache |
| Mutable SPA HTML shell | `/index.html` | `no-cache` or short TTL by design | Allows browser revalidation on deploy; do not use long TTLs like hashed assets |
| Time-varying public data | Non-personal Catalog/FAQ | `public, max-age=<appropriate TTL>` | Caching helps if staleness is acceptable |
| Error responses containing sensitive data | 401/403 with context info, redacted errors | `no-store` when sensitive content exists | Error HTTP statuses do not guarantee no caching |

Decide based on **content sensitivity**, not merely the URL or whether a controller has `@PreAuthorize`. A public 200 response with a `Set-Cookie` header requires careful review; a 302 redirect response can also carry sensitive information. The presence of cookies or an `Authorization` header in a request **does not replace** an explicit `Cache-Control` policy. HTTP caching has special rules for requests carrying `Authorization`, but you should not rely on that to protect all session/cookie patterns or CDN configurations.

## 6. Java 17+ configuration on Spring Boot 3 / Spring Security 6

The examples below are **code placed inside a Spring Boot Servlet application**, using `spring-boot-starter-web` and `spring-boot-starter-security`. They are not standalone Java files run with plain `javac`; they require a `@SpringBootApplication` main class, dependencies, and the Spring Boot runtime.

### 6.1. Keeping security headers for dynamic pages, narrow exception for assets

File `SecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    // Public, versioned asset files only.
    @Bean
    @Order(1)
    SecurityFilterChain assetChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/assets/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .headers(headers -> headers
                .cacheControl(cache -> cache.disable()));
        return http.build();
    }

    // All other paths, including personal content.
    @Bean
    @Order(2)
    SecurityFilterChain appChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults()));
        return http.build();
    }
}
```

In `appChain`, `cacheControl(Customizer.withDefaults())` simply makes the default policy explicit; all other security headers remain active. In `assetChain`, we only **disable the cache-control header writer for the exact `/assets/**` pattern**, without disabling all security headers or security filters. Requests select a chain by matcher and `@Order`; the configuration must fit existing chains in a real project.

**Mandatory condition:** `/assets/**` must contain only public files, never personal uploads, user-generated data, or login HTML. Disabling the cache writer on this chain delegates emitting the cache policy to the static resource handler or web infrastructure.

### 6.2. Setting long-term caching for versioned/hashed assets

File `AssetCacheConfig.java`:

```java
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(Duration.ofDays(365)).cachePublic()
            );
    }
}
```

This example serves files at `src/main/resources/static/assets/` under `/assets/**`. The header will typically include `public` and `max-age=31536000`. Apply a one-year TTL only if **asset names are fingerprinted and content at that URL is never overwritten**: for example, `app.a1b2c3.js`. If filenames are fixed like `app.js` and each deployment swaps the content, long caching will leave clients running stale versions; use a short TTL or require revalidation. `immutable` can be added if infrastructure and assets are truly immutable.

### 6.3. Setting security policy at sensitive endpoints

File `AccountController.java`:

```java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    @GetMapping("/api/me")
    ResponseEntity<AccountView> me(Authentication authentication) {
        AccountView body = new AccountView(authentication.getName());

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    record AccountView(String username) {}
}
```

Because `appChain` requires authentication, `Authentication` holds the identity of the logged-in user; the controller returns their private data. `ResponseEntity.cacheControl(CacheControl.noStore())` proactively sets the `Cache-Control: no-store` response header, expressing the policy right at the source. Spring Security also protects dynamic responses by default, but setting it directly on sensitive endpoints makes intent explicit if header configuration changes later.

Do not confuse `Content-Type`, `Content-Security-Policy`, or `X-Content-Type-Options` with `Cache-Control`: they protect different aspects of an HTTP response. Also do not rely on `Content-Disposition: attachment` to prevent PDFs/CSVs containing personal information from being stored by HTTP caches.

## 7. Real-world scenarios to handle

### 7.1. Logout and the browser Back button

Suppose a user opens `/account`, logs out, and clicks Back. If the personal response was cached, the browser may display the stale copy in some navigation flows. Setting `no-store` for personal pages/APIs is a necessary line of defense, but **HTTP cache differs from bfcache**, and history restoration behavior varies by browser, version, and conditions. Some browsers can restore previous page state without immediately fetching.

Beyond headers, the application should:
- Properly invalidate the session and clear/update authentication state on logout.
- Clear personal data held in SPA state upon logout or account switching.
- When a page is restored (`pageshow`) or the app returns to foreground, re-verify authentication before showing sensitive data; do not treat `no-store` as an authorization mechanism.
- Avoid storing profiles/access tokens in `localStorage` merely for "fast caching" without a sound reason and threat model.

Illustrative JavaScript skeleton for an SPA (illustrative only; the `/api/session` endpoint must exist in the application):

```javascript
window.addEventListener("pageshow", async (event) => {
  if (!event.persisted) return;

  const response = await fetch("/api/session", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    // Clear personal state and navigate to the login page.
  }
});
```

`fetch(..., { cache: "no-store" })` controls the request **sent by the client**; the server must still return response headers and check permissions on every request. The `pageshow` event does not cover every session state change in every browser, so this is only one part of the recovery flow.

### 7.2. CDN, reverse proxy, and API gateway

When intermediate caches exist, inspect the same response at **two locations**: directly from the origin and through the edge/CDN. CDNs may have their own cache rules, page rules, or policies. A final response appearing with `Cache-Control: no-store` is a necessary signal, but it does not replace configuring bypasses for authentication, account, and private API paths.

Things to verify:
- Routes like `/api/me`, `/account`, personal reports, and private downloads are never cached at the edge.
- No rule overrides `no-store` to `public` or forces a TTL.
- Cache keys never omit cookies/queries/user scope and serve one account's data to another.
- `Vary: Cookie` or `Vary: Authorization` can help describe response variants, but they are **not a substitute for `no-store`** on sensitive data; `Vary: Cookie` also heavily fragments cache keys.
- Observed headers at origin and edge must match the policy; if `Age`, `Via`, `X-Cache`, or CDN-provided trace headers exist, use them to investigate, without treating any vendor-specific header name as a universal standard.

Severe bug example: endpoint `/api/me` uses a session cookie, but the edge caches all `GET` requests with a key consisting only of the URL. When two users sequentially visit the same URL, the cache can reuse the previous user's profile. Fix this via **origin headers + edge bypass**, while verifying the server always authorizes requests; do not just add `Vary` and assume the risk is gone.

### 7.3. Service Worker and Cache API

If the application is a PWA, a Service Worker can programmatically put responses into the Cache API. This programmatic logic cannot be covered merely by checking the browser's HTTP cache. You must audit route matching: public static assets can use `cache-first`, whereas accounts/tokens/payment receipts should use `network-only` (and never call `cache.put`). On logout, delete sensitive data cached by the app and clear client-side state as needed.

**Never** place `/api/me` or responses containing personal data into a "cache all GETs" bucket simply because they are GET requests. Classify by content, not merely by HTTP method.

### 7.4. Downloadable documents and error responses

For PDF invoices, CSV statements, lab results, and access-permission exports: set `Cache-Control: no-store` on **the file response itself**, while authenticating/authorizing the download path. Even when the server sets `no-store`, a user clicking "Save" can still save the file to disk; securing downloaded files is a separate problem.

For 401/403/404/5xx responses, do not assume an error status automatically means "do not cache". Return `no-store` if the body or redirect contains sensitive data; avoid exposing tokens, session IDs, stack traces, and personal data in bodies/logs.

## 8. Testing and verifying response headers

### 8.1. Testing Spring Security Servlet with MockMvc

Add the `spring-boot-starter-test` and `spring-security-test` dependencies. File `CacheControlTest.java` (in the appropriate test package of the Spring Boot application):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheControlTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void privateAccountMustNotBeStored() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL, containsString("no-store")));
    }
}
```

This test requires the `SecurityConfig` and `AccountController` configuration from section 6. `@WithMockUser` simulates authentication for the Servlet security filter chain; the test checks that the **actual response** contains `no-store`. If the controller is changed to return `Cache-Control: public`, the test will catch the policy violation.

It can be expanded into an integration test verifying that a real asset `/assets/app.a1b2c3.js` returns `public`/`max-age` and `/api/me` responses are not cached by CDNs/shared caches. Do not assume statuses/headers solely from controller annotations; the final response can be altered by servlet filters, gateways, and reverse proxies.

### 8.2. Manual verification over HTTP

Once a validly authenticated endpoint is available, inspect the final response using DevTools Network or `curl -i`. For sensitive URLs, pass authentication cookies/tokens securely according to your environment; **never** put real credentials into public examples, tickets, or logs.

```bash
# Unauthenticated response for a public fingerprinted asset:
curl -I http://localhost:8080/assets/app.a1b2c3.js

# For an endpoint requiring login, use a valid session;
# -i to view headers + body instead of only status:
curl -i http://localhost:8080/api/me
```

The second command **without** a valid session may return 401, 403, or a redirect depending on `AuthenticationEntryPoint`; that does **not** prove the cache policy of the successful `/api/me` body. To test personal content, repeat with an authenticated session and confirm the 200 response has `Cache-Control: no-store`. For the asset, the sample file must actually exist at `src/main/resources/static/assets/app.a1b2c3.js` before expecting status 200.

Expected headers when the app runs properly with the configuration in section 6:

```http
# GET /api/me (authenticated, 200)
Cache-Control: no-store

# GET /assets/app.a1b2c3.js (file exists, 200)
Cache-Control: max-age=31536000, public
```

Directive ordering in the header may vary; check **meaning and values**, without depending on exact string order. In DevTools, inspect `Response Headers`, `Size` / cache indicators, and distinguish "from memory cache"/"from disk cache" from network responses. When checking CDN origins, also use provider HIT/MISS indicators if available, without treating them as a substitute for verifying access controls.

### 8.3. Security testing matrix

| Test case | What to verify |
| --- | --- |
| GET Alice's profile | `no-store`, body has only Alice's data, 200 when authenticated |
| Logout then Back | No profile leak from HTTP cache; UI checks auth before redisplaying |
| Log in as Bob on same machine | Does not reuse Alice's content from UI state/Service Worker/CDN |
| Unauthenticated request | No private data visible; error/redirect leaks no tokens, proper cache policy |
| Versioned public asset | `public` and long TTL; content matches hash in URL |
| Unversioned HTML shell | Has revalidation/short TTL; does not keep stale HTML |
| Private downloadable file | `no-store` and proper authorization; not served to another account |
| Through CDN/reverse proxy | Private endpoints bypassed; no cross-user cache HITs |
| SPA/PWA with Service Worker | Does not store personal responses in Cache API |

## 9. Common pitfalls

1. **Using `no-cache` to require "do not store".** This directive still permits storing; use `no-store` when the goal is not storing sensitive responses.
2. **Using `private` and thinking the browser will not keep data.** `private` forbids shared caches from storing per the directive; private caches may still retain it.
3. **Believing having cookies/sessions is enough to stop CDNs.** Not every shared cache infers privacy correctly; responses and edge rules must be explicitly configured.
4. **Setting `public, max-age=31536000` on all GETs.** Can leak profiles/HTML containing tokens, and also prevent HTML from updating on deployment.
5. **Disabling all `headers()` or bypassing the security chain just to cache assets.** Can drop unrelated security headers. Only change the cache policy for the subset of genuinely public static assets.
6. **Setting cache policies in controllers without checking edge responses.** Reverse proxies/CDNs may overwrite headers or have separate cache rules.
7. **Letting Service Workers cache all GETs.** An application-controlled Cache API can hold private data regardless of HTTP cache assumptions.
8. **Treating `no-store` as erasing all data after logout.** Browser UI state, bfcache, downloaded files, and other copies need separate mechanisms.
9. **Testing only status 200, ignoring headers and account switching.** Cache bugs may only surface when multiple users share a URL or after logout/login.
10. **Configuring large TTLs on fixed-name files.** When files change while URLs stay the same, clients can keep stale assets.

## 10. Implementation checklist

- [ ] APIs, pages, and files containing personal data/secrets emit `Cache-Control: no-store`.
- [ ] Spring Security Servlet keeps default security headers enabled for dynamic flows; any cache exceptions are narrowly scoped with clear matchers.
- [ ] Public assets are cached long-term only when versioned/hashed and free of user data.
- [ ] Login, logout, password-change endpoints, and sensitive file responses have appropriate policies.
- [ ] Reverse proxies/CDNs do not override `no-store` or mix caches across users; cache keys/bypasses are verified.
- [ ] Service Workers/PWAs do not retain personal data in Cache API; logout clears appropriate state.
- [ ] Response headers have been tested with `MockMvc`/DevTools/cURL using authenticated sessions, including post-logout/account-switch checks.
- [ ] Limitations of HTTP cache directives regarding bfcache, downloaded files, screenshots, and in-memory data are understood.

**Remember:** `no-store` is the core directive when avoiding HTTP cache storage of sensitive content; `no-cache` still allows storage for revalidation. Spring Security Servlet provides anti-caching headers by default, but the final cache policy must be verified on actual responses, including through CDNs. Optimize caching for public assets using explicit paths/versions, while always protecting personal pages/APIs with authentication, authorization, and a no-store policy.
