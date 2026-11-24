# Trailing Slash Rules and Authorization Consistency in Spring WebFlux

## 1. Why Does a Trailing Slash Matter?

The following two requests differ only by a trailing slash:

~~~text
GET /admin/reports
GET /admin/reports/
~~~

In HTTP, these are two different request targets. Controller mappings, reverse proxies, caches, and the authorization layer may interpret them according to different rules.

A common design flaw occurs when a controller or proxy treats both URLs as the same resource, while a security matcher only matches one exact form. A request with a trailing slash might fail to match the specific rule and fall through to a broader matcher. If a downstream layer later normalizes the path, the request can ultimately reach the same resource after having passed a different authorization decision.

The goal is to establish a **canonical path** so that URL normalization, Spring Security, and handler mappings all see the same path before processing the request.

## 2. Default PathPattern Rules in WebFlux

Spring WebFlux uses PathPattern and PathPatternParser to match URLs. This mechanism is designed specifically for HTTP paths and is WebFlux's choice; WebFlux does not use AntPathMatcher for controller routing.

Since Spring Framework 6.0, PathPatternParser no longer treats a trailing slash as optional by default:

~~~text
Pattern: /home

/home   -> match
/home/  -> does not match by default
~~~

Example:

~~~java
@GetMapping("/home")
public Mono<String> home() {
    return Mono.just("home");
}
~~~

GET /home matches the mapping. GET /home/ is a different path and does not match automatically just because it has an extra trailing slash.

### Changes Since Spring 6.0

In versions prior to Spring 6, PathPatternParser allowed an optional trailing separator by default. Starting with Spring 6.0:

- matchOptionalTrailingSeparator default changed from true to false.
- setMatchOptionalTrailingSeparator(boolean) was deprecated.
- Spring documentation recommends using explicit redirects or filters rather than re-enabling automatic trailing slash matching.

Do not rely on the old assumption that /resource and /resource/ are always equivalent. When upgrading to Spring 6, audit the URLs clients use and define one canonical rule.

### Pattern Examples

| Pattern | Path | Result |
| --- | --- | --- |
| /users | /users | Matches |
| /users | /users/ | Does not match automatically due to trailing slash |
| /users/{id} | /users/42 | Matches one segment |
| /users/{id} | /users/42/ | Does not match automatically due to trailing slash |
| /users/** | /users/42/profile | Matches multiple segments |

Wildcards such as /** have their own semantics. Do not infer from a catch-all pattern that every literal mapping also accepts a trailing slash.

## 3. Controller Routing and Authorization Are Two Separate Steps

In WebFlux, Spring Security operates via WebFilters. The security filter chain runs before the target WebHandler, which hosts DispatcherHandler and controller mappings.

~~~text
HTTP request
     |
     v
WebFilter chain
     |
     +--> URL normalization filter
     |
     +--> Spring Security WebFilterChainProxy
     |         |
     |         +--> select SecurityWebFilterChain
     |         +--> authentication
     |         +--> authorization matcher
     |
     v
DispatcherHandler
     |
     v
RequestMappingHandlerMapping
     |
     v
Controller method
~~~

Authorization rules do not wait for the controller to decide which method will handle the request. Spring Security inspects the request path using matchers right inside the filter chain.

In WebFlux Security, authorizeExchange().pathMatchers(...) and PathPatternParserServerWebExchangeMatcher use PathPattern-based path matching. Multiple SecurityWebFilterChains can be configured with their own matchers and order; the first matching chain is selected.

What must be guaranteed:

1. Paths are normalized before Security inspects them.
2. Security matchers and controller mappings apply the same path rules.
3. Specific rules come before broader rules.
4. The final fallback rule is intentional, such as authenticated or deny all.
5. No URL alias of a sensitive resource goes through a weaker authorization branch.

## 4. Mismatch Between Mapping and Authorization

Suppose an API has an administrative endpoint:

~~~java
@GetMapping("/admin/reports")
public Mono<Report> reports() {
    return reportService.load();
}
~~~

Security rule:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/admin/reports").hasRole("ADMIN")
    .anyExchange().permitAll()
)
~~~

If the request path is normalized to /admin/reports before Security, both /admin/reports and /admin/reports/ are evaluated by the same matcher and ADMIN rule.

If a filter or proxy only modifies the path after Security, Security may see /admin/reports/ while downstream processing sees /admin/reports. With an exact matcher, the request with a slash may miss the specific rule and fall through to the broader rule.

Consequences depend on the actual matchers and routes:

- Requests are rejected in one URL form yet accepted in another form.
- An alias routes to the same resource without being subject to the same authorization rule.
- Requests hit a different fallback route or error handler.
- Caches, audit logs, and rate limits record two different paths for the same resource.

Do not treat a 404 from a controller as an authorization safeguard. Authorization must be enforced accurately at the security layer, independent of whether a controller finds a handler.

## 5. UrlHandlerFilter in Spring Framework 6.2

Spring Framework 6.2 provides org.springframework.web.filter.reactive.UrlHandlerFilter for WebFlux. It is a dedicated WebFilter for handling trailing slashes.

The filter applies to selected patterns and can remove trailing slashes in two ways:

- **Redirect:** returns a redirect response so the client re-requests the canonical URL.
- **Mutate request:** modifies the path in ServerWebExchange and continues processing the current request.

Example:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
    .trailingSlashHandler("/blog/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
    .trailingSlashHandler("/admin/**")
        .mutateRequest()
    .build();
~~~

In this example, /blog/post/ is permanently redirected to /blog/post with HTTP 308; /admin/users/ is rewritten to /admin/users on the internal request.

Spring's Javadoc states that the filter should run before security filters so URL-based authorization and handler mappings share the same view of the path.

### Registering the Filter as a Bean

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter urlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/admin/**", "/api/**")
        .mutateRequest()
        .build();
}
~~~

WebFlux automatically detects WebFilter beans. @Order(Ordered.HIGHEST_PRECEDENCE) gives the filter high priority so normalization occurs before Spring Security.

Do not place URL normalization after Security. Doing so lets Security and controllers continue evaluating two different paths.

## 6. Choosing redirect or mutateRequest?

| Criterion | Redirect | Mutate request |
| --- | --- | --- |
| URL seen by client | Switches to canonical URL | Keeps original URL |
| Number of requests | Client may send a second request | Single internal request |
| Cache and bookmarks | Easily converges on canonical URL | Clients may still save the slashed URL |
| API clients | Must support redirects | Clients need no redirect handling |
| Security | Follow-up request is checked on canonical URL | Filter normalizes before Security runs |
| Client/proxy logs | May log redirect and follow-up request | Still sees original URL before the filter |

### Redirect with HTTP 308

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter docsUrlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/docs/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
}
~~~

308 Permanent Redirect indicates the resource URL has permanently moved to the canonical URI. Per HTTP semantics, 307 and 308 are method-preserving redirects; 308 fits when publishing a long-lived canonical URL.

Example:

~~~http
GET /docs/install/ HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 308 Permanent Redirect
Location: /docs/install
~~~

For POST/PUT requests, preserving method and body is critical. 301/302 have a history where clients may switch POST to GET; 307/308 are defined to avoid changing methods when following redirects.

Permanent redirects can be cached. Only use 308 once canonical URLs are stable and clients support the redirect behavior appropriately.

### Mutate Request

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter adminUrlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/admin/**")
        .mutateRequest()
        .build();
}
~~~

For GET /admin/users/, the filter rewrites the internal path to /admin/users before the request reaches Security and handler mappings.

The advantage is not requiring clients to send a second request. This is often convenient for legacy APIs with diverse clients or clients that do not handle redirects uniformly.

In exchange, the original URL seen by browsers or proxies may still contain the trailing slash. If a single public URL is needed for bookmarking or edge caching, a redirect may be better.

## 7. Filter Order Is Part of the Security Policy

~~~text
Request /admin/reports/
          |
          v
UrlHandlerFilter
          |
          | mutate request path
          v
Request /admin/reports
          |
          v
Spring Security
          |
          | matcher sees canonical path
          v
Controller mapping
          |
          | same canonical path
          v
AdminController.reports()
~~~

Principles:

- Place UrlHandlerFilter before the Spring Security WebFilter chain.
- Do not add a second custom filter that alters paths after Security.
- If a reverse proxy also normalizes paths, configure proxy and application with the same rule.
- When using multiple SecurityWebFilterChains, the canonical path must be produced before chain selection.
- If other filters check tenant, rate limits, audits, or request signatures based on path, explicitly decide whether they need the raw path or the canonical path.

### Multiple SecurityWebFilterChains

Spring Security can split chains by path:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Another chain can handle the rest. Because Spring selects chains by matcher and order, canonicalization must run before that selection process.

## 8. Designing Canonical URLs for the Application

For example, an application chooses URLs without trailing slashes for all paths except root /:

| Incoming URL | Canonical URL |
| --- | --- |
| /users | /users |
| /users/ | /users |
| /users/42 | /users/42 |
| /users/42/ | /users/42 |
| / | / |

Spring's UrlHandlerFilter excludes the root path / from trailing slash handling by default.

If an API must retain a trailing slash due to an external contract, do not register the filter for that path. Separate rules can be chosen per pattern:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
    .trailingSlashHandler("/api/**")
        .mutateRequest()
    .trailingSlashHandler("/docs/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
    .build();
~~~

Do not apply a global rule without checking routes that have special semantics. An endpoint may treat a trailing slash as part of its contract, especially for legacy compatibility or special storage keys.

### Explicit Aliases

Another approach is declaring both mappings explicitly:

~~~java
@GetMapping({"/catalog", "/catalog/"})
public Mono<Catalog> catalog() {
    return catalogService.getCatalog();
}
~~~

This makes the route accept both URLs, but does not normalize the request path for other layers. If Security, caching, rate limiting, or auditing must treat both URLs as one resource, policies across those layers still need synchronization.

## 9. Path Normalization Is Not Only Trailing Slashes

UrlHandlerFilter handles trailing slashes for declared patterns. It is not a normalizer for every URL variation.

| Path Form | Concern to Consider |
| --- | --- |
| /files//report | Duplicate slashes; proxies and servers may interpret differently |
| /files/../admin | Dot segments and path traversal handling |
| /files/%2Fadmin | Encoded slash; decoding may differ across layers |
| /files/%252Fadmin | Double encoding; do not decode repeatedly arbitrarily |
| /users;v=1 | Matrix/path parameters |
| /Admin and /admin | Case sensitivity |
| /api/v1.json | Suffix, not a trailing slash |

Spring WebFlux uses parsed RequestPath to access decoded path segments; semicolon content is handled separately for path matching. Do not write custom path string decoding code for controller matching.

Do not do things like:

~~~java
String path = exchange.getRequest().getURI().getRawPath()
    .replaceAll("/+$", "");
~~~

and construct a new request path for all cases. That can alter encoded paths, double slashes, root paths, or segment semantics unexpectedly.

If handling encoded slashes, duplicate slashes, or dot segments is needed, define uniform behavior across reverse proxy, HTTP server, and application; test the same URL matrix end-to-end. Do not double-decode.

## 10. Reverse Proxies, Gateways, and Forwarded Headers

Applications often sit behind Nginx, ingress controllers, API gateways, or load balancers. These layers may add or strip prefixes, normalize slashes, redirect URLs, rewrite paths before sending to WebFlux, or apply authorization/caching before requests reach the application.

If a proxy normalizes /admin/reports/ to /admin/reports while Security inside the app sees a different path due to inconsistent forwarded/rewrite settings, logs and policies may diverge.

Spring WebFlux provides ForwardedHeaderTransformer to process forwarded details such as host, port, scheme, and prefix. Forwarded headers are trustworthy only when the proxy at the trust boundary strips client-sent headers and writes its own verified values.

Proxy checklist:

1. Determine whether the proxy redirects or rewrites trailing slashes.
2. Document the exact path the proxy sends upstream.
3. Ensure gateway authorization and application authorization use the same canonical path.
4. Do not trust forwarded headers sent by external clients.
5. Test paths with query strings, encoded segments, and trailing slashes.
6. Avoid having two layers redirect with conflicting rules, causing redirect loops.

## 11. Complete Java 17+ Example with Spring Boot WebFlux and Security

Example using Spring Boot 3.5.0, Java 17+:

- Controller protects a resource at /admin/reports.
- Spring Security requires role ADMIN for that exact path.
- UrlHandlerFilter strips trailing slashes before Security.
- /admin/reports and /admin/reports/ go through the same authorization matcher.
- WebTestClient verifies a regular user cannot use a trailing slash to bypass the rule.

Project structure:

~~~text
webflux-path-security/
├── pom.xml
└── src/
    ├── main/java/com/example/pathsecurity/
    │   ├── PathSecurityApplication.java
    │   ├── UrlPolicyConfiguration.java
    │   ├── SecurityConfiguration.java
    │   └── AdminController.java
    └── test/java/com/example/pathsecurity/
        └── TrailingSlashSecurityTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-path-security</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

### PathSecurityApplication.java

~~~java
package com.example.pathsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathSecurityApplication.class, args);
    }
}
~~~

### UrlPolicyConfiguration.java

~~~java
package com.example.pathsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.filter.reactive.UrlHandlerFilter;

@Configuration(proxyBeanMethods = false)
public class UrlPolicyConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    UrlHandlerFilter urlHandlerFilter() {
        return UrlHandlerFilter
            .trailingSlashHandler("/admin/**")
            .mutateRequest()
            .build();
    }
}
~~~

The filter runs before Spring Security. When a request has path /admin/reports/, the request path is mutated to /admin/reports before security matchers inspect it.

### SecurityConfiguration.java

~~~java
package com.example.pathsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails admin = User.withUsername("admin")
            .password("{noop}secret")
            .roles("ADMIN")
            .build();

        UserDetails user = User.withUsername("user")
            .password("{noop}secret")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(admin, user);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/admin/reports").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

The authorization rule grants ADMIN role only on the /admin/reports matcher. Other requests are denied in this demo. The {noop} password is for local demonstration only; production must use an appropriate PasswordEncoder and secure user/role storage.

### AdminController.java

~~~java
package com.example.pathsecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/admin")
public class AdminController {

    @GetMapping("/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "resource", "admin-reports",
            "status", "ok"
        ));
    }
}
~~~

Class mapping is /admin, method mapping is /reports. Do not use @RequestMapping("/") at class level because it adds a slash to the type-level mapping and may fail to match after the filter strips the trailing slash.

### TrailingSlashSecurityTest.java

~~~java
package com.example.pathsecurity;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TrailingSlashSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void adminCanAccessBothPathForms() {
        for (String path : new String[] {
                "/admin/reports",
                "/admin/reports/"
        }) {
            client.get()
                .uri(path)
                .headers(headers -> headers.setBasicAuth("admin", "secret"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.resource").isEqualTo("admin-reports");
        }
    }

    @Test
    void userCannotBypassAuthorizationWithTrailingSlash() {
        client.get()
            .uri("/admin/reports/")
            .headers(headers -> headers.setBasicAuth("user", "secret"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousRequestIsRejectedForBothForms() {
        for (String path : new String[] {
                "/admin/reports",
                "/admin/reports/"
        }) {
            client.get()
                .uri(path)
                .exchange()
                .expectStatus().isUnauthorized();
        }
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

The tests confirm:

- ADMIN calling the path with or without a trailing slash receives the same resource.
- USER calling /admin/reports/ still receives 403.
- Unauthenticated requests receive 401 on both URL forms.

### Running the Application and Testing with cURL

Start:

~~~bash
mvn spring-boot:run
~~~

ADMIN calling path without slash:

~~~bash
curl -i -u admin:secret http://localhost:8080/admin/reports
~~~

ADMIN calling path with slash:

~~~bash
curl -i -u admin:secret http://localhost:8080/admin/reports/
~~~

Both responses look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "resource": "admin-reports",
  "status": "ok"
}
~~~

USER calling path with slash:

~~~bash
curl -i -u user:secret http://localhost:8080/admin/reports/
~~~

Response:

~~~http
HTTP/1.1 403 Forbidden
~~~

Request without credentials receives:

~~~http
HTTP/1.1 401 Unauthorized
~~~

The example uses HTTP Basic and in-memory users for learning purposes only. Do not use this password configuration in real systems.

## 12. How to Investigate a Trailing Slash Bug in Production

When /resource and /resource/ produce different statuses or permissions, inspect each layer in order:

1. **Client:** What exact URL is sent? Is a library appending a slash?
2. **Proxy/gateway:** Is the path rewritten, redirected, or normalized?
3. **Forwarded headers:** Are prefix/host processed from a trusted proxy?
4. **WebFilter order:** Does the normalization filter run before Security?
5. **SecurityWebFilterChain:** Which chain is selected for each path?
6. **Authorization matcher:** Which specific rule matches? Does it fall through to a broader matcher?
7. **Handler mapping:** Which controller or functional route matches?
8. **Method security:** Is there additional @PreAuthorize or domain-level policy?
9. **Cache/CDN:** Do the two URLs generate different cache keys?
10. **Logging/metrics:** Do logs record the path before or after normalization?

### Deliberate Path Logging

When investigating, log both the original request URI at the edge and the canonical path inside the application. Do not log just one value and assume all layers saw the same path.

You can attach a request ID to correlate gateway, WebFlux, and downstream logs. Never log authorization headers, cookies, access tokens, or sensitive data when debugging paths.

### URL Matrix Testing

For a sensitive endpoint, test at minimum:

| Path | Anonymous | USER | ADMIN |
| --- | --- | --- | --- |
| /admin/reports | 401 | 403 | 200 |
| /admin/reports/ | 401 | 403 | 200 |

If the application uses redirect instead of mutate, test the 308 response and the follow-up request separately. If the endpoint accepts POST/PUT, verify clients preserve method/body when following the redirect.

## 13. Common Pitfalls

1. **Assuming /path and /path/ are always identical:** since Spring 6.0, PathPatternParser does not automatically match optional trailing slashes.
2. **Re-enabling setMatchOptionalTrailingSeparator(true):** the API has been deprecated since Spring 6.0. Prefer an explicit URL policy via filter or redirect.
3. **Normalizing after Spring Security:** Security decides on the old path while the controller may receive the new path. Place UrlHandlerFilter before security.
4. **Fixing only controller mappings:** leaves Security matchers, caches, gateways, or rate limits out of sync.
5. **Fixing only Security matchers:** route mappings may still process a URL differently from the matcher.
6. **Using an overly broad catch-all authorization rule:** a path variant missing a specific rule can fall through to a weaker rule. Use an explicit fallback and test it.
7. **Using @RequestMapping("/") after stripping slashes:** class-level mapping may add a slash and stop matching. Use @RequestMapping without a path if a root prefix is needed.
8. **Registering UrlHandlerFilter without setting order:** the filter may run after security and fail to fix the mismatch.
9. **Using 301/302 redirects for POST without checking method semantics:** clients may change POST to GET. For method-preserving redirects, consider 307/308.
10. **Using 308 before canonical URLs are stable:** permanent redirects can be cached, making policy changes harder.
11. **Using mutateRequest but forgetting to log the original path:** logs at different layers may show different paths. Record both raw path and canonical path when needed.
12. **Applying the filter to root /:** UrlHandlerFilter excludes the root path; do not rely on the filter to alter /.
13. **Thinking UrlHandlerFilter handles duplicate slashes or encoded slashes:** the filter only handles trailing slashes for configured patterns.
14. **Decoding URIs multiple times:** can turn encoded separators into real separators or open path traversal risks.
15. **Testing only GET:** redirects for POST/PUT/PATCH have method and body behaviors that need verification.
16. **Ignoring the reverse proxy:** the proxy may canonicalize differently from the app and create discrepancies before requests reach WebFlux.
17. **Assuming 404 is enough protection:** authorization must be verified in Security; do not rely on controller mapping as a substitute.
18. **Not testing anonymous, regular user, and admin together:** a 200 status for one user does not prove path variants share the same policy.
19. **Not checking multiple SecurityWebFilterChains:** paths may select different chains if matchers and order are inconsistent.
20. **Out-of-sync cache keys:** /resource and /resource/ may store two cache entries or apply different cache policies.

## 14. Deployment Checklist

- Are canonical URLs defined for each endpoint group?
- Is the team aware that PathPatternParser does not match trailing slashes by default?
- Is Spring Framework 6.2's UrlHandlerFilter used when needed?
- Does the filter run before Spring Security?
- Is redirect or mutateRequest chosen based on client contracts?
- If redirecting, is the status appropriate and are method/body tested?
- Is the root path / handled properly?
- Do controller mappings and Security matchers share the same path policy?
- Are specific authorization rules placed before broad rules?
- Does the fallback intentionally deny or require authentication?
- Do proxies/gateways follow the same canonicalization rule?
- Do encoded slashes, duplicate slashes, dot segments, and matrix parameters have explicit policies?
- Are both /path and /path/ tested with anonymous, USER, and ADMIN?
- Are POST/PUT tested if endpoints support those methods?
- Can logs correlate raw paths and canonical paths without leaking credentials?

## 15. Self-Check Questions

**1.** Which path matching mechanism does WebFlux use? PathPattern and PathPatternParser.

**2.** Since Spring 6.0, does /home automatically match /home/? No, optional trailing separator defaults to false.

**3.** Why do trailing slashes affect authorization? Security matchers and handler mappings may see two different paths, causing requests to hit different rules.

**4.** Which version introduced UrlHandlerFilter? Spring Framework 6.2.

**5.** What are the two handling modes of UrlHandlerFilter? Redirect the client or mutate the internal request path.

**6.** Why must the filter run before Spring Security? So security matchers and controllers receive the same canonical path.

**7.** How does mutateRequest() differ from redirect? Mutate alters the path on the internal request; redirect returns a response telling the client to call the canonical URL.

**8.** What does HTTP 308 mean? Permanent Redirect; when a client follows the redirect, the HTTP method is preserved per HTTP semantics.

**9.** Does UrlHandlerFilter modify root /? No, the root path is excluded.

**10.** Why can @RequestMapping("/") cause issues after stripping trailing slashes? It adds a slash to the class-level mapping, preventing it from matching normalized paths.

**11.** Can UrlHandlerFilter be used to handle %2F or duplicate slashes? No. Those are different path forms requiring separate policies.

**12.** When a request does not match a specific authorization rule, what matters? Having an explicit fallback rule; never let path variants fall into a weaker rule unintentionally.

**13.** Which identities should be tested? Anonymous, regular user, and permitted roles, on both slashed and unslashed paths.

**14.** What must be done if a proxy already rewrites paths? Align rules across proxy, filter, Security matchers, and handler mappings; test end-to-end.

**15.** Is enabling setMatchOptionalTrailingSeparator(true) recommended? No; the setter has been deprecated since Spring 6.0. Use explicit canonicalization.

**Key takeaway:** In Spring WebFlux, /path and /path/ are distinct paths by default since Spring 6.0. If you want to accept both, normalize with Spring 6.2's UrlHandlerFilter. The filter must run before Spring Security so authorization matchers and controllers see the same canonical path. Choose 308 redirect or mutate request based on client contracts, keep root / under proper rules, and handle encoded paths and duplicate slashes with separate policies.

**Official Documentation:**
- [Spring Framework 6.2 — Reactive Core, URL Handler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html)
- [PathPatternParser Javadoc — Default trailing separator behavior](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html)
- [UrlHandlerFilter Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/reactive/UrlHandlerFilter.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [PathPatternParserServerWebExchangeMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html)
- [RFC 9110 — HTTP Semantics, Redirection](https://www.rfc-editor.org/rfc/rfc9110.html).