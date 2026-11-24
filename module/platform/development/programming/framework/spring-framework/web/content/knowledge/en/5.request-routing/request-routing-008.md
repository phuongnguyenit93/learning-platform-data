# Controlling Trailing Slashes in Spring MVC and Differences Across Versions

## 1. The Problem to Understand

A *trailing slash* is a `/` character at the end of the URL **path**, for example:

- `GET /api/users`: no trailing `/`.
- `GET /api/users/`: has a trailing `/`.
- `GET /api/users?page=1` and `GET /api/users/?page=1`: still differ in **path**; the query string `?page=1` does not determine trailing-slash handling.
- The root path `/` is a special case and must not be arbitrarily stripped down to an empty string.

With Spring MVC, the question is whether a controller method declaring `@GetMapping("/api/users")` accepts both of the first two URLs. The answer **depends on the Spring Framework version, path-matching configuration, declared mappings, and any filters or reverse proxies placed in front of the application**. Never treat those two URLs as automatically equivalent.

Lesson scope: **Spring MVC on the Servlet stack**, covering both plain Spring Framework apps and Spring Boot apps. Spring WebFlux, Spring Cloud Gateway, proxy configurations, and Servlet containers have their own mechanisms; do not assume they share the exact same API as MVC.

## 2. Routing Mechanism and Why Behavior Differs

When an HTTP request enters an MVC application, proxies and Servlet filters (if any) process it first, then `DispatcherServlet` looks up a matching handler, typically via `RequestMappingHandlerMapping`. Spring compares the received path against patterns in `@RequestMapping`, `@GetMapping`, `@PostMapping`, etc., while also evaluating HTTP method, `params`, `headers`, `consumes`, and `produces` when declared.

Consider this controller:

```java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping("/api/users")
    public String listUsers() {
        return "users";
    }
}
```

This is a controller class in an application with Spring MVC and an appropriate web starter, not a standalone Java file run with `java UserController`.

- `GET /api/users` matches the mapping and normally returns HTTP 200 with body `users`.
- Under defaults from **Spring Framework 6.0 onward**, `GET /api/users/` **does not match** the mapping above. If no other mapping/filter/proxy handles it, the result is typically **404 Not Found**.
- If Spring Security, a reverse proxy, a redirect filter, or another route is present, the observed HTTP status may differ (e.g., 301/308, 401/403). Therefore, inspect the entire request path before drawing conclusions.

`PathPatternParser` parses URL patterns into `PathPattern`s and matches against the request path. `AntPathMatcher` is the legacy string-matching strategy. **Choosing a parser and deciding trailing-slash rules are two separate concerns**; merely switching to `AntPathMatcher` is not a reliable way to restore old behavior.

## 3. Version Milestone Table to Remember

| Platform | Default for `@GetMapping("/api/users")` when calling `/api/users/` | Notes |
| --- | --- | --- |
| Spring Framework 5.x, including 5.3 (commonly with Boot 2.x) | Usually **matches** because optional trailing-slash match is enabled by default | Check custom configs; Boot 2.6 switched the default MVC strategy to `PathPatternParser`, which did not disable trailing-slash matching. |
| Spring Framework 6.0–6.1 (commonly Boot 3.0–3.3) | Default **does not match** | Starting in 6.0, default trailing-slash matching changed from `true` to `false` and APIs to re-enable it were deprecated. |
| Spring Framework 6.2 (commonly Boot 3.4–3.5) | Default **does not match** | Introduces `UrlHandlerFilter` (added in Framework 6.2) to explicitly redirect or wrap requests. Legacy APIs remain deprecated. |
| Spring Framework 7.0+ (Boot 4.x line) | Default **does not match** | Optional trailing-slash matching in path parsers **has been removed**; use explicit mappings, redirects/rewrites, or `UrlHandlerFilter`. |

These are **Framework version milestones**, while Spring Boot manages Framework versions via dependency management. When verifying a specific project, inspect the actual Framework version in the dependency tree rather than guessing from source code or a single Boot property.

Some easily confused distinctions:

1. Spring Framework 5.3 introduced the option to choose `PathPatternParser`, whereas MVC previously relied on `AntPathMatcher`.
2. Spring Boot 2.6 changed the default URL matching strategy to `PathPatternParser`. That differs from **Spring Framework 6.0 disabling trailing-slash matching by default**.
3. `PathMatchConfigurer#setUseTrailingSlashMatch(true)` and `PathPatternParser#setMatchOptionalTrailingSeparator(true)` were deprecated in Framework 6.0; **do not add those APIs to new configs** because the 7.0 upgrade path removes them.
4. There is no universal `application.yml` property named `spring.mvc.trailing-slash` guaranteed to re-enable this across all versions. `spring.mvc.pathmatch.matching-strategy` controls the **matching strategy** in Boot versions that support it, not a standard toggle to merge both URLs.

## 4. Choosing a URL Policy Based on API Goals

### Option A — Single Canonical URL (Recommended Default)

Design and publish `/api/users` as the canonical endpoint. Keep one mapping:

```java
@GetMapping("/api/users")
public String listUsers() {
    return "users";
}
```

Clients must use the URL exactly as documented. An invalid trailing slash will not match the mapping under Framework 6+ defaults. The advantage is a single consistent path across OpenAPI, caches, logs, request signatures, and authorization rules; the trade-off is that clients sending `/api/users/` must be updated or will receive an error.

**Never blindly strip trailing slashes from all URLs** if the application has special paths, signed URLs, reverse proxies doing rewrites, or API contracts requiring the slashed form.

### Option B — Allow Both Forms on a Specific Endpoint

Declare both patterns explicitly where needed:

```java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping({"/api/users", "/api/users/"})
    public String listUsers() {
        return "users";
    }
}
```

With this controller, both `GET /api/users` **and** `GET /api/users/` return `200 OK` with body `users` in an app without blocking filters/security. Unlike a redirect, both requests are served directly without a second round trip.

Use this option when only a few endpoints must preserve compatibility. Avoid duplicating paths across multiple controllers that cause ambiguity, and avoid duplicating the entire API without clear justification. If an endpoint handles multiple HTTP methods, declare variants for the right methods rather than adding an unrestricted `@RequestMapping`.

### Option C — Redirect to the Canonical URL at Proxy or Filter

If the goal is a **canonical URL**, redirect `/api/users/` to `/api/users`. For example, a reverse proxy handling trailing-slash policy can return 308 with `Location: /api/users`. The client then sends a new request to the canonical URL.

- **308 Permanent Redirect**: permanent redirect preserving HTTP method and request body per specification; some clients/caches may remember the redirect.
- **307 Temporary Redirect**: temporary redirect that still preserves method and body.
- **301/302**: historically caused clients to change methods (especially POST to GET); do not default to them for write APIs.
- **Redirect vs rewrite/wrap**: redirects return a 3xx response so the client makes a new call; rewrite/wrap lets the application continue processing within the same request. These differences affect HTTP observability, logging, caching, and clients that do not follow redirects automatically.

Choose 308 once the URL policy is stable and clients support it; choose 307 during transition periods to avoid long-term caching effects. Thoroughly test POST/PUT/PATCH requests, large payloads, authentication, and signed URLs.

## 5. `UrlHandlerFilter` Since Spring Framework 6.2

With Spring MVC Servlet on Framework **6.2+**, `org.springframework.web.filter.UrlHandlerFilter` lets you configure specific path groups. The example below uses Spring Boot with Spring MVC and requires Spring Framework 6.2+:

```java
package demo.web;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

@Configuration
public class TrailingSlashConfig {

    @Bean
    FilterRegistrationBean<UrlHandlerFilter> trailingSlashFilter() {
        UrlHandlerFilter filter = UrlHandlerFilter
                .trailingSlashHandler("/api/**")
                .redirect(HttpStatus.PERMANENT_REDIRECT)
                .build();

        FilterRegistrationBean<UrlHandlerFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }
}
```

With the `@GetMapping("/api/users")` mapping from section 2, assuming the filter chain is properly ordered:

```text
GET /api/users   -> 200 OK, body: users
GET /api/users/  -> 308 Permanent Redirect
                    Location: /api/users
GET /api/users   -> 200 OK, body: users  (if client follows redirect)
```

The snippet above illustrates **filter configuration and expected statuses**, not stdout from a standalone Java program. `Ordered.HIGHEST_PRECEDENCE + 20` is only an example precedence; verify your application's actual filter order. Spring documentation requires `UrlHandlerFilter` to run **after `ForwardedHeaderFilter`, before `ServletRequestPathFilter` (if present), and before security filters**. If the system uses a reverse proxy or Spring Security, verify that order is actually satisfied; never treat a constant order value as a guarantee across all setups.

If you need to keep a single request and rewrite the path internally, the Servlet API uses `wrapRequest()`:

```java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/**")
        .wrapRequest()
        .build();
```

Then a client calling `/api/users/` receives the response directly from `/api/users`'s handler without a 3xx. In return, check that logs, other filters, and security matchers all see the normalized path consistently. **Never register multiple filters with overlapping slash logic simultaneously**, as this can cause redirect loops or unpredictable behavior.

Note the filter's limitations:

- The `"/api/**"` rule affects only the configured path group; it does not indiscriminately alter every URL in the system.
- The root path `/` is excluded from trailing-slash handling.
- When normalization applies, a type-level `@RequestMapping("/")` can produce unwanted slashes; for controllers truly at root, Spring docs recommend `@RequestMapping` without a path where appropriate.
- `UrlHandlerFilter` exists only from 6.2+; in Framework 6.0–6.1 choose explicit mappings, infrastructure redirects/rewrites, or a controlled custom filter. Do not copy this class into a 6.0 project expecting it to compile.

## 6. Legacy Configuration During Upgrades: Readable, Not for New Code

In some Spring Framework 6.x projects, you may encounter a migration configuration:

```java
// ONLY ILLUSTRATES LEGACY SPRING FRAMEWORK 6.x CONFIGURATION.
// Deprecated since 6.0; do not use for new deployments or Framework 7.
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    configurer.setUseTrailingSlashMatch(true);
}
```

Or direct code using `PathPatternParser#setMatchOptionalTrailingSeparator(true)`. Both rely on a matching mechanism marked deprecated in 6.0 and removed when upgrading to 7.0. If maintaining a 6.x project, identify the exact active parser/handler mapping and test both URL variants; do not rely on this trick as a long-term upgrade strategy.

**Do not confuse this with** `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` in older Boot versions that support it: that setting picks the pattern engine and does not enable trailing slashes on Framework 6+; in Framework 7, string-based matching APIs are also deprecated/removed.

## 7. Security and Consistency Between MVC and Spring Security

One reason Spring removed the permissive default is to prevent **path-interpretation mismatches** between the authorization layer and the routing layer. Imagine a rule protecting `/resources` with different permissions from `/resources/**`. If the security matcher evaluates `/resources/` under one rule while MVC lets it enter `/resources`'s handler, users might receive unintended access. This is a design-risk example, **not a claim that every Spring Security configuration is bypassed**.

Implementation principles:

1. Apply normalization **before** authorization if choosing a filter/rewrite, so Security and MVC see the exact same path; verify with real integration tests.
2. Audit both slashed and non-slashed paths across public APIs, admin endpoints, health/actuator endpoints, and static resources; never assume they share the same policy.
3. Ensure proxies, gateways, CDNs, Spring Security, and controllers agree on canonical URL conventions; also consider case sensitivity, `%2F` encoding, and duplicate slashes where relevant.
4. For redirects, never drop query strings, HTTP methods, or bodies; verify `Location`, host, and scheme when behind a trusted proxy. Never trust `X-Forwarded-*` headers from untrusted sources.
5. For requests without a matching handler, security filters may return 401/403 before MVC ever gets a chance to return 404; looking at status codes alone is insufficient to determine path-matching rules.

## 8. Regression Testing

To test **default path-mapping behavior itself** independently of web servers, reverse proxies, and custom filters, use standalone `MockMvc`. JUnit Jupiter example with `spring-test` and version-compatible Spring test dependencies:

```java
package demo.web;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class UserControllerTest {

    @Test
    void spring6AndLaterDefaultRequiresExactPath() throws Exception {
        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(new UserController())
                .build();

        mvc.perform(get("/api/users"))
                .andExpect(status().isOk())
                .andExpect(content().string("users"));

        mvc.perform(get("/api/users/"))
                .andExpect(status().isNotFound());
    }
}
```

This test uses the **single-mapping controller** from section 2 and expects Framework **6.0+** defaults. On a 5.x project (legacy default), the second check might return 200; when using the **two-explicit-mappings controller** from section 4, update the second expectation to 200. Being standalone, this test **does not prove real-world Servlet filter ordering, Spring Security, proxies, or `UrlHandlerFilter`**.

After adding filters or Security configuration, write integration tests with an appropriate web context containing the full filter chain. Minimum test matrix:

| Request | Framework 6+ default with one mapping | Two explicit mappings | 308 redirect filter |
| --- | --- | --- | --- |
| `GET /api/users` | 200 | 200 | 200 |
| `GET /api/users/` | 404 if no other handler | 200 | 308, `Location: /api/users` |
| `GET /api/users/?page=1` | 404 if no other handler | 200 | 308, verify query preserved |
| `POST /api/users/` | Depends on actual POST mapping (possibly 404/405) | Depends on actual POST mapping | If rule applies, verify 307/308 preserves method/body |
| `GET /` | Depends on root mapping | Depends on root mapping | Filter must not strip root slash |

The 200 and 404 values in the table are **illustrative scenarios** for a GET controller returning `users`, not promises for every app. Test redirects with a **client that does not auto-follow redirects** to inspect the initial 308 response; afterward, test separately with redirect-following clients.

Quick inspection commands when running on port 8080:

```bash
curl -i --max-redirs 0 http://localhost:8080/api/users
curl -i --max-redirs 0 http://localhost:8080/api/users/
curl -i --max-redirs 0 'http://localhost:8080/api/users/?page=1'
```

Inspect the HTTP status line and `Location` header (if any), not just the response body. Do not use `curl -L` in the first step because it auto-follows redirects and hides the 3xx response.

## 9. Diagnosing 404s or Strange Redirects After an Upgrade

Follow this sequence:

1. **Confirm exact versions**: check Spring Framework, Spring Boot, and `spring-webmvc` in the dependency tree; locate the 5.3 → 6.x or 6.x → 7.x boundary.
2. **Inspect handler declarations**: check class-level and method-level `@RequestMapping`, servlet prefixes, context paths, and actual URL names; watch out for class-level `@RequestMapping("/")`.
3. **Inspect the actual request**: capture HTTP method, raw path, query string, and `Location` header; compare `/api/users` vs `/api/users/` before and after reverse proxies.
4. **Audit matching configuration**: verify `PathPatternParser`, `WebMvcConfigurer` settings, leftover deprecated APIs, and proxy/filter rewrite rules.
5. **Trace filters/security**: verify the `ForwardedHeaderFilter` → normalization → Spring Security → MVC order to prevent redirect loops, wrong host/scheme, or security path mismatches.
6. **Lock down behavior with tests**: test both path forms, all supported HTTP methods, query strings, bodies, redirects, auth, and real clients before release.

Do not conflate statuses: **404** usually means no handler found; **405** means the path has a handler but not for that HTTP method; **308** is a redirect; **401/403** usually comes from the security layer. Components and configuration can alter the path, so use logs and the filter chain to pinpoint the responder.

## 10. Self-Check Exercises

1. A project upgrades from Boot 2.7 to Boot 3.2; `GET /catalog` works yet `GET /catalog/` returns 404. Explain the milestone change from Framework 5.3 to 6.x, then choose between URL normalization and declaring dual mappings.
2. API `POST /orders/` must be redirected to `POST /orders` while preserving the JSON payload. Explain why 307/308 is better than defaulting to 301/302; verify whether clients support redirects.
3. On Framework 6.2+, apply `UrlHandlerFilter` for `/api/**` and write an integration test proving `/api/users/` returns a 308 redirect, preserves the query string, and runs before Security.
4. Before upgrading to Framework 7, find and eliminate dependencies on `setUseTrailingSlashMatch` and `setMatchOptionalTrailingSeparator`, replacing them with an explicit URL strategy.

## Official Documentation

- [Spring Framework 6.x: Upgrading Guide — trailing slash match change](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x).
- [Spring Framework 7.x: Servlet filters, URL Handler section](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Javadoc `UrlHandlerFilter` in Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/UrlHandlerFilter.html).
- [Javadoc `PathPatternParser` in Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html).
- [Spring Framework 7.0 Release Notes — removed path matching APIs](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes).
- [Spring Boot 2.7: MVC path matching configuration](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/web.html).
