# RequestMatcher and Request Data Used for Matching in Spring Security Servlet

## 1. What Question Does RequestMatcher Answer?

In a **Spring Boot 3.x / Spring Security 6.x Servlet-based** application, before the system decides whether to allow an HTTP request to reach a controller, Spring Security usually has to identify **which scope the request belongs to**.

For example:

- Is `GET /products/42` a public product-read request?
- Is `POST /api/reports` an operation that requires report-write permission?
- Does `GET /admin/users` belong to the group that requires the ADMIN role?
- Does `GET /api/reports` with header `X-Api-Version: v2` belong to a special API version?
- Is the request going through the chain for `/api/**` or the chain for the web UI?

**`RequestMatcher`** is the abstraction that answers the question: "Does the current HTTP request **match this condition?**". Common interface:

~~~java
package org.springframework.security.web.util.matcher;

public interface RequestMatcher {
    boolean matches(HttpServletRequest request);
}
~~~

This is a **simplified form to explain the core method**, not an exact copy of the entire interface across all Spring Security versions. `HttpServletRequest` comes from `jakarta.servlet.http` on Spring Boot 3. Some APIs/versions add a method supporting match results containing path variables, but `matches(...)` is the foundation for understanding request selection.

**RequestMatcher does not authenticate the user itself and does not grant permissions itself.** It only answers whether a request satisfies a criterion. Access decisions still require `AuthorizationManager`, `Authentication`, and the related policies.

### Practical Scenario

~~~text
GET /api/reports?month=11
Authorization: Basic ...
X-Api-Version: v2
~~~

A matcher that only checks the `/api/reports` path may match regardless of `month=11` and the version header. A matcher that checks **method + path + header** may produce a different result. **Which conditions are used depends on the matcher type and how the developer configures it**; there is no rule that every RequestMatcher always inspects the entire request.

## 2. Where Does RequestMatcher Appear in Spring Security?

There are two important places that are very easy to confuse:

1. **`securityMatcher(...)` of a `SecurityFilterChain`**: selects whether a request is handled by that filter chain.
2. **`requestMatchers(...)` in `authorizeHttpRequests(...)`**: after the chain has been selected, selects the authorization rule applied to the request.

Simplified flow:

~~~text
HTTP request
    |
    v
Servlet container / DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    | Select the FIRST SecurityFilterChain whose chain RequestMatcher matches
    v
Security filters of that chain
    |
    | Authentication is restored/verified according to the configured mechanism
    v
AuthorizationFilter
    |
    v
RequestMatcherDelegatingAuthorizationManager
    |
    | Select the first matching RequestMatcher -> AuthorizationManager pair
    v
AuthorizationManager checks Authentication + request context
    |
    +--> allow -> controller / resource
    |
    +--> deny -> exception handling, typically 401 / 403 / redirect
~~~

Filters may have different behavior or ordering depending on the version, chain, and dispatcher; the diagram helps explain their relative roles.

### 2.1. securityMatcher vs. requestMatchers

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a configuration snippet requiring imports for `@Bean`, `@Order`, `HttpSecurity`, `Customizer`, and `SecurityFilterChain`; it is **not** a standalone Java file. `securityMatcher("/api/**")` is the condition for **selecting the chain**. If `GET /web/home` does not match the API chain, the rules inside `authorizeHttpRequests` of this chain are **not evaluated** for that request.

Within the selected chain, `requestMatchers("/api/admin/**")` is the condition for **selecting the authorization rule**. If every chain has a narrow matcher and no chain matches a URL, the request may not be protected by Spring Security. In real systems, a fallback/coverage chain should be designed according to the threat model.

### 2.2. Matcher vs. AuthorizationManager

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

The matcher checks whether the URL belongs to `/admin/**`; the manager checks whether `Authentication` has the corresponding `ROLE_ADMIN` authority. If the matcher matches and the user does not have permission, the request is **denied at the selected rule**; Spring Security does not look at rules below it to see if any rule is more permissive.

A matcher **should not read passwords itself or check user permissions from untrusted input data**. Keep "selecting the request scope" separate from "deciding who is allowed to do what".

## 3. What Data Is Available in HttpServletRequest?

`RequestMatcher.matches(HttpServletRequest)` can read many properties from the request. Some fields come from the servlet API; some are data already processed by the servlet container or earlier filters.

| Data | Typical Read | Common Purpose |
| --- | --- | --- |
| HTTP method | `request.getMethod()` | Distinguish GET, POST, PUT, DELETE… |
| Request URI | `request.getRequestURI()` | URI path on the server, **usually including context path** |
| Context path | `request.getContextPath()` | Application context name, e.g. `/shop` |
| Servlet path | `request.getServletPath()` | Path mapped to the servlet, useful for servlet/MVC matchers |
| Path info | `request.getPathInfo()` | Remaining path portion when servlet mapping has path info |
| Query string | `request.getQueryString()` | Query string from the URL, excluding the path portion |
| Query/form parameters | `request.getParameter("key")` | Select request variant, filter by parameter if truly needed |
| HTTP headers | `request.getHeader("X-Api-Version")` | API version/content negotiation/controlled routing |
| Content type | `request.getContentType()` | Distinguish JSON/form/multipart by format |
| Cookies | `request.getCookies()` | Select request based on cookie presence when needed |
| Dispatcher type | `request.getDispatcherType()` | Distinguish REQUEST, FORWARD, ERROR, ASYNC… |
| Server/host/scheme | `getServerName()`, `getScheme()`, `isSecure()` | Host/HTTPS-based policy, requires checking proxy trust |
| Client network address | `request.getRemoteAddr()` | Network/IP seen by the container, which may be a proxy |
| Request attributes | `request.getAttribute(...)` | Data attached earlier by the application/filters |
| Servlet mapping | `request.getHttpServletMapping()` | Servlet mapping context in modern Servlet APIs |

**Not every matcher inspects all of the data above.** For example, a path matcher may ignore headers/query; a method matcher may not inspect query parameters. You decide which data is used by **choosing the appropriate matcher**, or building a custom matcher when the conditions provide real value.

Do not read/buffer the entire request body from a matcher to make authorization decisions: the body may only be readable once, breaking downstream controllers/parsers, wasting resources, and opening a DoS risk. Authorization based on business content should usually happen after parsing/validation at the service/method layer.

## 4. Understanding RequestURI, contextPath, servletPath, pathInfo, and query

### 4.1. Example of an Application Running Under a Context Path

Suppose the public URL is:

~~~text
https://example.test/shop/api/items/42?include=stock
~~~

The application is deployed with `contextPath=/shop` and Spring MVC `DispatcherServlet` is typically mapped at `/`. A common view:

~~~text
getRequestURI()   -> /shop/api/items/42
getContextPath()  -> /shop
getServletPath()  -> /api/items/42
getPathInfo()     -> null
getQueryString()  -> include=stock
~~~

This is an **example for default-style servlet mapping**. With a servlet mapped to `/app/*` or other mapping styles, `getServletPath()` and `getPathInfo()` may differ. If the application runs behind a reverse proxy that rewrites paths, the external URL in the browser and the path seen by the container may also differ.

**Common mistake:** taking `getRequestURI()` and comparing it directly with `"/api/items/42"` when the context path is `/shop`. The result does not match because the request URI contains `/shop`. When using a matcher that supports Spring MVC or an appropriate path matcher, the framework can handle this according to the matcher's rules; a custom matcher must examine the exact path API it uses.

### 4.2. Query String Is Not Part of the Path

~~~text
GET /api/items?sort=price
GET /api/items?sort=date
GET /api/items?sort=price&limit=100
~~~

A path matcher for `/api/items` typically treats these requests as **the same path**, despite the different queries. `request.getRequestURI()` and `getServletPath()` do not include `?sort=...`.

If you need matching by query, do so intentionally using `getParameter(...)` or an appropriate custom matcher; however, **never grant permissions based on client-chosen parameters** such as `?role=ADMIN` or `?isOwner=true`.

### 4.3. URL Encoding and Path Normalization

Paths containing encoded parts such as `%2F`, `%2E`, `..` sequences, semicolons, consecutive slashes, or spaces may be handled differently across browsers, reverse proxies, Servlet containers, and Security matchers.

Spring Security typically uses `HttpFirewall` (such as `StrictHttpFirewall`) inside `FilterChainProxy` to enforce acceptance/normalization rules before filters see the request. **Do not write your own matcher based on custom URL decoding**, and do not relax the firewall just to make an awkward endpoint match without a security review.

Avoid discrepancies between:
- The URL used by the reverse proxy for routing;
- The URL normalized by the Servlet container;
- The URL matched by Spring Security;
- The URL used by Spring MVC or the controller.

If these layers interpret paths differently, authorization bypasses or false rejections of legitimate requests can occur. Keep paths canonical, and test encoded characters, trailing slashes, and semicolons in a real environment.

## 5. Common Types of RequestMatcher

Spring Security has multiple implementations, and the `requestMatchers(...)` DSL may choose an implementation based on the Spring MVC/servlet mapping context. Do not assume pattern strings are always regular expressions or always have identical semantics across every version.

### 5.1. Path-based Matcher

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/public/**` describes a group of URLs; the wildcard symbols are interpreted according to the selected **matcher implementation**. Pattern expressions of MVC-aware matchers, Ant-style matchers, PathPattern-based matchers, and regex matchers are not completely equivalent. When upgrading Spring Security or changing servlet mappings, test the actual patterns again.

With Spring MVC on the classpath, the DSL may choose an MVC-appropriate matcher; sometimes a project needs to explicitly specify the servlet path or matcher type to avoid ambiguity. If there are multiple servlets, Spring Security may require specifying which servlet a matcher belongs to. **Do not assume `requestMatchers(String...)` always matches like `String.startsWith()`.**

### 5.2. Method-based Matcher

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .requestMatchers(HttpMethod.POST, "/api/articles").hasAuthority("article:write")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

This is an `HttpSecurity` snippet importing `org.springframework.http.HttpMethod`. A path can allow public GET while requiring different permissions for POST/DELETE. Test all methods supported by the application, not just GET. For "safe" methods like HEAD/OPTIONS, do not assume they always match the same rule as GET: behavior can vary depending on the matcher and infrastructure.

### 5.3. RequestHeaderRequestMatcher and Header-based Matching

Spring Security has a dedicated matcher for certain header conditions; or you can write a readable lambda:

~~~java
RequestMatcher apiVersionTwo = request ->
    "GET".equals(request.getMethod())
    && "/api/reports".equals(request.getServletPath())
    && "v2".equals(request.getHeader("X-Api-Version"));
~~~

This snippet requires importing `RequestMatcher` and placing it in an appropriate Java scope. It only matches GET on path `/api/reports` with the exact v2 version header. Checking a header **is a way to classify a route**, **not proof of permission**: callers can send `X-Api-Version: v2` themselves.

In a runnable example, the v2 rule will require a **trusted authority** `report:v2` provided to the user by the server after authentication. If a client spoofs the v2 header without having the permission, the request still gets 403. This is a better design than simply looking at the header and allowing access.

### 5.4. Regex and Custom Matchers

When routing patterns are complex, a regex matcher can be useful, but watch out for escaped paths, separators, query handling, performance, and regex denial-of-service. Do not turn all path patterns into regex when the default matcher already expresses them clearly.

When checking multiple conditions, you can use `AndRequestMatcher`, `OrRequestMatcher`, `NegatedRequestMatcher`, or a `request -> ...` lambda. Focus on clear conditions, and avoid writing matcher logic that is hard to verify or depends on the response/body.

~~~java
RequestMatcher securedReportRead = request ->
    "GET".equals(request.getMethod())
    && "/api/reports".equals(request.getServletPath())
    && "v2".equals(request.getHeader("X-Api-Version"));
~~~

In real code, the matcher's job is only to select the rule that requires `report:v2`. Whether `Authentication` has the `report:v2` authority must be checked by AuthorizationManager.

### 5.5. Dispatcher Type Matcher

A Servlet request can transition through `DispatcherType.REQUEST`, `FORWARD`, `ERROR`, `ASYNC`, and `INCLUDE`. You can use:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

This is a snippet requiring `jakarta.servlet.DispatcherType` to be imported. Some applications need to permit error/forward rendering, but **do not blindly enable permitAll for all dispatcher types**; evaluate carefully because forward/error paths may lead to sensitive content or different flows. Dispatcher matching and authorization also depend on how filters are invoked during request dispatch.

### 5.6. Matchers by Host, Scheme, Remote Address, and Time

In some multi-domain, reverse proxy, or internal endpoint scenarios, a custom matcher may check `Host`, `getServerName()`, scheme, or remote address. However, **this data can be altered by proxies and client-sent forwarded headers**, so it is only safe when a clear trust boundary has been established.

Do not use client-supplied `X-Forwarded-For` as proof that a request comes from an internal network; do not grant ADMIN based on `User-Agent` or `Referer`. IP checks can serve as an auxiliary layer, but are usually insufficient to replace authentication/authorization.

## 6. Matchers Do Not Automatically Check User Permissions

Suppose an API wants to allow admins to view reports:

~~~java
.requestMatchers("/admin/reports/**").hasRole("ADMIN")
~~~

Flow:

1. The matcher checks the URL.
2. If the URL matches, AuthorizationManager checks `Authentication` and the required authority.
3. If the user does not have `ROLE_ADMIN`, access is denied.
4. **The next rule is not tried** even if there is a broader matcher below it such as `"/admin/**"` or `anyRequest().authenticated()`.

A very dangerous mistake:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/api/admin/users` already matches the first `/api/**` rule, so it gets `permitAll`. The admin rule below is never used. Fix this by placing narrower matchers first:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

**Fundamental rule:** `RequestMatcherDelegatingAuthorizationManager` chooses the **first matching matcher**, not the matcher with the strictest permissions, nor does it try a second manager if the first manager denies access.

### 6.1. Fallbacks Need to Be Explicit

`anyRequest().denyAll()` helps establish a **deny by default** design for URLs without a specific rule. `anyRequest().authenticated()` is also valid, but it means any logged-in user can access all remaining URLs — which is a different policy.

If you place a broad `/**` matcher before specific rules, they become unreachable; if you omit a catch-all chain in a multi-chain config, URLs outside every chain's matcher may not be protected by Spring Security.

## 7. Untrusted Request Data: A Critical Boundary

In many systems, request information can be controlled by the caller:

- URL path and query string;
- Headers such as `X-Role`, `X-User`, `X-Tenant-Id`, `X-Api-Version`;
- HTTP method sent by the client;
- Cookies set by the client;
- JSON body/form parameters;
- `Origin`, `Referer`, `User-Agent` headers;
- Some network metadata if a reverse proxy is misconfigured.

**You can use this data to SELECT the policy to check**, but **you must not use it as proof that the user has permission** without a trusted verification step.

### 7.1. A Serious Anti-Pattern

~~~java
// WRONG: anyone can send X-Role: ADMIN themselves.
RequestMatcher "admin" = request ->
    "ADMIN".equals(request.getHeader("X-Role"));
~~~

This is **intentionally non-compilable pseudo-code**, illustrating the danger of trusting client-supplied headers. If the system then applies `permitAll()` to this matcher, an attacker can set the header themselves to gain access.

Correct approach:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

The `ROLE_ADMIN` authority must come from a verified `Authentication` or a token whose signature/claims have been validated, not from a self-declared `X-Role` header on the request.

### 7.2. Query Parameters Do Not Equal Ownership

~~~text
GET /api/orders/123?ownerId=alice
GET /api/orders/123?isOwner=true
~~~

Even if the URL falls under an `authenticated()` rule, the application **cannot trust** `ownerId=alice` or `isOwner=true` sent by the client. You must verify the actual authenticated account and the owner/tenant of order 123 from a trusted data source, typically at the service/method policy level.

### 7.3. Use Matchers to Raise Requirements, Not to Bypass Them

A safe option is to use a version header to **elevate permission requirements**:

~~~java
.requestMatchers(v2Matcher).hasAuthority("report:v2")
.requestMatchers(HttpMethod.GET, "/api/reports").hasAuthority("report:read")
~~~

If the caller chooses `X-Api-Version: v2`, they must have `report:v2`; if not, `report:read` is required. Modifying the header **does not create an authority itself**, it only selects a serving mode with different permissions.

**Caution:** if v2 contains more sensitive data but the fallback path allows the client to access that same data another way, the system still has a design flaw. Service-layer authorization should protect the actual data; do not rely solely on header variants.

### 7.4. Method Override and Request Wrappers

If the app has `HiddenHttpMethodFilter` or a custom filter that modifies/wraps the request, a matcher may see the transformed HTTP method depending on **filter order**. Do not assume `getMethod()` is always the original method on the wire in every deployment.

Test the actual HTTP method seen by the security filters, especially when supporting `_method=DELETE`, reverse proxy rewrites, or an API gateway. Prevent bypasses caused by method overrides behaving differently from what the controller applies.

## 8. Path-Based Matchers: Pitfalls to Test

### 8.1. Wildcards Are Not Universal Regular Expressions

The string pattern `"/api/**"` expresses a path group according to the matcher in use, not a direct Java regex. The pattern `"/api/{id}"` often has different semantics from `"/api/*"`. Verify the Spring Security version, Spring MVC version, servlet mapping, and parser being used.

### 8.2. Trailing Slash, Case, and Semicolons

~~~text
/api/items
/api/items/
/API/items
/api/items;v=1
/api/items%2F42
~~~

These URLs may be processed differently by the framework or proxy. Do not assume uniform behavior, and do not relax `StrictHttpFirewall` too broadly to accept encoded slashes/semicolons just because one client sends non-standard URLs. Standardize on canonical URLs and test end-to-end from proxy to controller.

### 8.3. Context Path and Servlet Mapping

In an application with `server.servlet.context-path=/shop`, a custom matcher comparing `getRequestURI()` directly to `"/api/reports"` will fail. In a Boot MVC root servlet setup, `getServletPath()` is usually suitable for app-relative paths, but with other servlet mappings you must analyze `getPathInfo()`, `HttpServletMapping`, and how the chosen matcher handles paths.

### 8.4. Query and Fragment

Browsers do not send the URL fragment `#section` in an HTTP request; Servlet `HttpServletRequest` does not receive fragments as part of the URI for a matcher to inspect. A query like `?page=2` is sent, but **it is not part of the path**. Do not use `request.getRequestURI().contains("?")` to match queries.

### 8.5. Static Resources and Actuator

If the application permits `/css/**`, `/js/**`, or `/health` publicly, declare them explicitly. Do not fix a 403 asset error with `anyRequest().permitAll()` and accidentally expose the entire API. For an actuator on a different management port/context, dedicated matchers and a separate security chain may be needed.

## 9. Runnable Project: Matchers by Path, HTTP Method, and Header

This example uses **Java 17**, **Spring Boot 3.3.13**, **Spring Security 6**, and HTTP Basic for straightforward matcher testing. The project demonstrates:

- `GET /health` is public.
- `GET /api/reports` **without the v2 header** requires `report:read`.
- `GET /api/reports` with `X-Api-Version: v2` requires `report:v2`.
- `POST /api/reports` requires `report:write`; CSRF remains enabled by default.
- `GET /api/profile` requires authentication.
- `GET /admin/status` requires `ROLE_ADMIN`.
- Unlisted URLs are rejected by `anyRequest().denyAll()`.

**Never use a client-set header to grant an authority**. The version header only **selects the rule** requiring the corresponding permission. Logging in with demo in-memory users/passwords is only for practice; do not deploy directly to production.

### 9.1. Project Structure

~~~text
request-matcher-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/matchdemo/
    │   ├── MatcherApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/matchdemo/
        └── RequestMatcherTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>request-matcher-demo</artifactId>
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

**`src/main/java/com/example/matchdemo/MatcherApplication.java`**

~~~java
package com.example.matchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/matchdemo/SecurityConfig.java`**

~~~java
package com.example.matchdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Custom matcher ONLY selects the API variant: GET + path + header.
        // Header is client-controlled data, NOT an authority.
        RequestMatcher reportsV2 = request ->
            "GET".equals(request.getMethod())
            && "/api/reports".equals(request.getServletPath())
            && "v2".equals(request.getHeader("X-Api-Version"));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()

                // Place the narrower matcher before the general GET for the same path.
                .requestMatchers(reportsV2).hasAuthority("report:v2")
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")

                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")

                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()

                .requestMatchers("/admin/**").hasRole("ADMIN")

                // All requests outside the routes above are denied.
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF enabled by default; POST requires a valid token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .authorities("ROLE_USER", "report:read")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .authorities("ROLE_USER", "report:v2")
                .build(),
            User.withUsername("writer")
                .password(hash)
                .authorities("ROLE_USER", "report:write")
                .build(),
            User.withUsername("admin")
                .password(hash)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Why rule order matters:** the `reportsV2` matcher must come before `requestMatchers(HttpMethod.GET, "/api/reports")`, because the URL and method are the same. If swapped, v2 requests would be caught first by the general GET matcher, causing the `report:v2` permission check to be skipped.

In this example, alice has `report:read` but not `report:v2`, while bob has `report:v2` but not `report:read`. The user is selected via HTTP Basic authentication verified by Spring Security, **not** by the `X-Api-Version` header. `POST` must also pass the CSRF filter, so a user with `report:write` can still receive 403 if the CSRF token is missing.

**`src/main/java/com/example/matchdemo/DemoController.java`**

~~~java
package com.example.matchdemo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(HttpServletRequest request) {
        String version = "v2".equals(request.getHeader("X-Api-Version"))
            ? "v2" : "v1";
        return Map.of("version", version);
    }

    @PostMapping("/api/reports")
    public ResponseEntity<Map<String, String>> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("result", "created"));
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin/status")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }

    @GetMapping("/unlisted")
    public Map<String, String> unlisted() {
        return Map.of("status", "should-not-be-visible");
    }
}
~~~

`/unlisted` has an MVC mapping but is not permitted by the HTTP policy. This is a way to test the `denyAll` fallback. If a request reaches the controller in practice, it is a sign that the security rule was bypassed or misconfigured.

### 9.2. Testing with MockMvc

**`src/test/java/com/example/matchdemo/RequestMatcherTests.java`**

~~~java
package com.example.matchdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestMatcherTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPathIsAccessible() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void queryParameterDoesNotChangePathMatch() throws Exception {
        mvc.perform(get("/api/reports")
                .param("page", "2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value("v1"));
    }

    @Test
    void headerSelectsStricterVersionPolicy() throws Exception {
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value("v2"));

        // Alice has read permission for v1 but does NOT have report:v2.
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Bob has report:v2 but does not have report:read.
        mvc.perform(get("/api/reports")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedVersionTwoNeedsLogin() throws Exception {
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void methodRuleAndCsrfAreIndependent() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.result").value("created"));

        // Has write permission, but missing CSRF token is still blocked.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Has CSRF token, but missing write authority is also denied.
        mvc.perform(post("/api/reports")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRuleAndFallback() throws Exception {
        mvc.perform(get("/admin/status")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin/status")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

The tests demonstrate:

- **Path**: `GET /api/reports?page=2` still matches GET `/api/reports` without the v2 header; the query is not used to select the path matcher.
- **Header**: callers can switch to the v2 variant, but must actually have the `report:v2` authority.
- **Method**: POST uses the write rule, not the GET rule.
- **CSRF**: an authorized POST request without a CSRF token still returns 403. Do not confuse a 403 from CSRF with a 403 from the authorization manager.
- **Negative tests**: anonymous 401 with HTTP Basic, missing permission 403, undeclared URL denied.
- **Authentication**: tests use `httpBasic` to go through the authentication mechanism, rather than self-declared headers or `@WithMockUser` to fake password verification.

### 9.3. Running and Expected Results

Requires JDK 17+, Maven, and dependency download on first run. In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Expected result:** tests succeed when the project, versions, and environment are set up properly. This is an **example design and expected output**, not a Maven log executed inside this document.

Test with curl (for localhost only; HTTP Basic contains credentials, production must use HTTPS):

~~~bash
curl -i http://localhost:8080/health
# Expected 200: {"status":"ok"}

curl -i http://localhost:8080/api/reports
# Expected 401 HTTP Basic challenge

curl -i -u alice:demo-pass \
  'http://localhost:8080/api/reports?page=2'
# Expected 200: {"version":"v1"}

curl -i -u bob:demo-pass \
  -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports
# Expected 200: {"version":"v2"}

curl -i -u alice:demo-pass \
  -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports
# Expected 403

curl -i -u admin:demo-pass http://localhost:8080/admin/status
# Expected 200: {"status":"admin-ok"}

curl -i -u admin:demo-pass http://localhost:8080/unlisted
# Expected 403
~~~

To test POST with curl while CSRF is enabled, the client needs a **valid CSRF token tied to the token/cookie/session storage mechanism**. Do not send `curl -X POST` without CSRF and conclude that 403 is due to wrong permissions. MockMvc tests use `.with(csrf())` to simulate a valid request and distinguish the two error types.

In PowerShell on Windows, you can use `curl.exe` when `curl` is a different alias.

## 10. Key Differences When Using Multiple SecurityFilterChains

Suppose a system has both web sessions and an API using Basic or Bearer authentication:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

This is an **illustrative configuration snippet**; for production use, you need to decide on CSRF, sessions, authentication providers, and complete routes. The second chain has no explicit `securityMatcher(...)`, so it typically acts as a catch-all. `FilterChainProxy` evaluates chains in order and **selects the first matching chain**, rather than combining filters from both chains.

**Distinguishing the two first-match layers:**

| Layer | Matcher | Result |
| --- | --- | --- |
| Filter chain selection | `securityMatcher(...)` + chain order | Selects **one** SecurityFilterChain |
| Authorization rule selection | `requestMatchers(...)` inside the chain | Selects **one** matching AuthorizationManager |
| Authorization decision | Selected `AuthorizationManager` | Allows/denies the request |
| Controller/service permission | Policy based on business data | Can check ownership, tenant, resource-level permissions |

`@Order` on a chain does **not** control the order of `requestMatchers` inside the chain. And `anyRequest().denyAll()` on the API chain **does not protect** requests outside `/api/**` when those requests do not enter the API chain.

## 11. Debugging Matchers Without Exposing Sensitive Information

When an endpoint returns an unexpected 401/403/404, do not immediately replace everything with `anyRequest().permitAll()` as a "quick fix". Check in order:

1. What are the **actual request's** method, path, contextPath, servletPath, query, headers, and dispatcher type?
2. **Which SecurityFilterChain** did the request enter? Is an `@Order`/`securityMatcher` catching the request early?
3. Inside that chain, **which rule matched first**? Is a broad matcher shadowing a narrow matcher?
4. What role/authority does that rule's manager require? What authorities does `Authentication` actually have?
5. Was the request blocked by the CSRF filter, CORS, or an earlier filter?
6. If the request passed authorization but returned 404, is the MVC endpoint mapped?
7. If a proxy/context path is in use, do all layers interpret the path and HTTP method the same way?

You can selectively increase Spring Security logging in a **test environment**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Do not enable TRACE/DEBUG indefinitely in production, and do not log full Authorization headers, session cookies, passwords, tokens, or personal data. Some security logs may contain paths and authentication information, so access control and retention policies must be applied.

### Troubleshooting Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `/api/admin/**` is accessible anonymously | Rule `/api/**.permitAll` appears earlier, or another chain caught the request | Matcher/chain ordering |
| User has the role but receives 403 | Wrong authority prefix, another rule matched first, missing CSRF | Authentication authorities, selected rule, CSRF |
| `GET /shop/api/items` does not match custom matcher | Comparing `getRequestURI()` with app-relative path | ContextPath/ServletPath/PathInfo |
| v2 header matcher never runs | General GET matcher is placed earlier or header value differs | Rule order, header, and case |
| GET succeeds but POST returns 403 | POST authority differs or CSRF token is missing | HTTP method rule and CSRF separately |
| A URL outside the chains still returns a public response | No catch-all chain | Chain coverage and securityMatcher |
| `/error` is blocked | Dispatcher/error path is not handled | Dispatcher rule or error endpoint |
| Unusual encoded URL produces 400/403 before controller | HttpFirewall or proxy/container normalization | Firewall, canonical path, reject policy |
| Query `?role=admin` has no effect on policy | Path matcher ignores queries; this may be intended behavior | Never grant permissions based on queries |
| CORS preflight OPTIONS returns 401/403 | Order of CORS handling, authentication, or method matcher | CORS config and OPTIONS handling |

## 12. Best Practices for Designing Safe RequestMatchers

### 12.1. Prefer Clear Matchers and Limit Complexity

Use `requestMatchers(HttpMethod.GET, "/api/items/**")` instead of complex regex when you only need path and method. Custom regex/lambdas should have a concrete reason, positive/negative tests, and comments describing the condition. Avoid duplicating path-parsing logic across multiple layers.

### 12.2. Do Not Use Easily Spoofed Data as Access Permissions

Headers, queries, cookies, and IPs are request metadata; they do not authenticate an identity on their own. Use `hasRole`, `hasAuthority`, or a service policy based on trusted sources and a verified Authentication. For Bearer/JWT, verify signature, issuer/audience, expiry, and configured scopes/claims; never trust a payload merely because it can be decoded.

### 12.3. Always Write Tests for Overlapping Matchers

For the v2 rule and general GET, write a test "v2 + user with only report:read must return 403" to catch anyone accidentally reversing the order. Test "v1 + user with only report:v2 must return 403" to ensure permissions are not mistakenly treated as implying each other.

### 12.4. Choose Deny by Default When Required

An explicit fallback reduces the risk of newly created endpoints being left out of policy. However, you must explicitly declare public assets, health, login, error, and management paths as appropriate. Never fix every 403 with `anyRequest().permitAll()`.

### 12.5. Data-Based Authorization Belongs in the Business Layer

`RequestMatcher` excels at classifying requests by URL/method; it does not know whether a user owns object `order-123`. Check at the service/method level with `@PreAuthorize` (when method security is enabled) or a dedicated policy, based on the loaded object and trusted tenant/user.

### 12.6. Define a Test Matrix Before Production

The matrix should include:
- Normal URLs and URLs with trailing slashes.
- Appropriate HTTP methods: GET/POST/PUT/DELETE/HEAD/OPTIONS.
- Different query parameters on the same path.
- Correct, incorrect, or missing headers/versions.
- Anonymous, low-privilege user, user with permission, admin.
- ContextPath/ServletPath when not deployed at root.
- CSRF/CORS, dispatcher/error/forward where applicable.
- URL-encoded paths and proxy rewrites according to allowed policy.
- Unlisted endpoints and chain fallbacks.
- Negative tests for cross-tenant/ownership at the service layer.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| RequestMatcher authenticates the user | The matcher only checks whether the request falls within scope |
| RequestMatcher is always URL-based | A matcher can inspect method, header, query, dispatcher, etc. |
| `getRequestURI()` only contains the app-relative path | Usually includes contextPath; you need to understand servlet mapping |
| Query string is part of `getServletPath()` | No; queries have their own API |
| Header `X-Role: ADMIN` proves ADMIN permission | False, clients can set headers themselves |
| Matching the v2 header lets the user use API v2 | No; the manager must still verify permission |
| A broader matcher placed later will "rescue" an earlier denied rule | No; the first matching matcher is chosen |
| `securityMatcher` and `requestMatchers` are the same | One selects the chain, one selects the rule |
| Having only an API chain protects all URLs | URLs outside the chain may bypass Spring Security |
| `permitAll()` disables CSRF and all filters | No; the request still passes through the chain |
| 403 always means a missing role | It can be caused by CSRF, authorization, or another filter |
| Query, URI, and headers are always normalized identically to MVC | They can differ across container, proxy, and firewall |
| `GET /api/items` and `POST /api/items` share the same permission | Method policies must be declared and tested |
| `hasRole("ADMIN")` accepts any authority containing ADMIN | By default it checks for exact `ROLE_ADMIN` |
| Having HTTP authorization removes the need for ownership checks | Service/method authorization is still needed for specific data |

## 14. Self-Check

**1. What question does `RequestMatcher` answer?**

It checks whether the current HTTP request matches the defined criteria; it **does not** verify whether a password is correct or grant permissions itself.

**2. How do `getRequestURI()`, `getServletPath()`, and `getQueryString()` differ?**

Request URI typically includes the context path but not the query; ServletPath represents the path related to servlet mapping, usually app-relative in an MVC root servlet; the query has its own accessor. With different servlet mappings, PathInfo/ServletPath may change.

**3. Does the `/api/reports` path matcher automatically distinguish `?page=1` and `?page=2`?**

Usually not. The query is not part of the path; to distinguish queries, you must choose a matcher that inspects parameters and evaluate the security of doing so.

**4. Does `X-Api-Version: v2` prove the user has `report:v2`?**

No. A client-sent header only selects the policy; the authority must come from Authentication or a trusted source after verifying credentials or tokens.

**5. Why must the v2 header matcher be placed before the general GET matcher for `/api/reports`?**

Because `RequestMatcherDelegatingAuthorizationManager` selects the first rule whose matcher matches. If the general GET rule comes first, the v2 rule is shadowed.

**6. Can a user with `report:write` still receive 403 on a POST missing a CSRF token?**

Yes. CSRF checks the request independently of authorization rules and can reject it before the manager checks permissions.

**7. Does `securityMatcher("/api/**")` protect `/admin/**`?**

No. It only specifies that the API chain handles `/api/**`; another chain or catch-all chain is needed to protect URLs outside that scope.

**8. Should `?role=ADMIN` be used to select a permitAll rule?**

No. Query data is controlled by the client and is not proof of permission. Use verified authorities.

**9. Why might a custom matcher comparing `getRequestURI()` directly with `"/api/reports"` fail after deploying under `/shop`?**

Because `getRequestURI()` may be `/shop/api/reports`. You must account for context path and servlet mapping, or use an appropriate framework matcher.

**10. Does a blocked `DispatcherType.ERROR` mean the user lacks a role?**

Not necessarily. Authorization may run again during the error dispatch and be blocked by a fallback. Inspect the selected chain/rule, dispatcher, and error flow.

**11. Why are both positive and negative tests needed for matchers?**

Positive tests prove valid requests are allowed; negative tests prove broad/overlapping matchers or client headers do not accidentally bypass permissions, and that the fallback actually denies access.

**12. Is a URL-based RequestMatcher enough to protect multi-tenant data?**

No. An HTTP matcher does not know the ownership/tenant of a specific record. Service/method policies based on trusted identity and actual data are required.

**Key takeaway:** **`RequestMatcher` is a predicate on `HttpServletRequest`; a matcher can inspect path, method, header, query, dispatcher, and many other attributes. `securityMatcher` selects the filter chain, and `requestMatchers` selects the first matching authorization rule. Never treat client-declared data as permissions; only `AuthorizationManager` and policies grounded in a trusted identity decide access.**