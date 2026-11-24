# DelegatingAuthenticationEntryPoint for Request-Based Response Selection in Spring Security Servlet

**Scope:** Java 17+, Spring Security 6.x, Spring Boot 3.x, and Jakarta Servlet. This topic belongs to the **Error Responses** group. The lesson explains how to use <code>DelegatingAuthenticationEntryPoint</code> to select the response when a request is unauthenticated or fails authentication requirements: APIs typically need 401 JSON, AJAX needs machine-readable data, while HTML browsers typically need a redirect to the login page. The focus is on the <code>RequestMatcher</code> mechanism, **matching order**, the default entry point, the <code>ExceptionTranslationFilter</code> flow, and distinguishing 401 from 403.

**Core principle:** <code>AuthenticationEntryPoint</code> decides **how to ask the client to start or re-perform authentication** when protection mechanisms require it. It is not an access-granting resource policy. Whether an API receives JSON or a web page receives a redirect is solely a **response format/flow** and must never become a condition for bypassing authorization.

## 1. The Problem: Same Backend, Multiple Client Types

Imagine a Servlet application simultaneously serving:
- A browser opening <code>GET /app/profile</code> and expecting a login page when no session exists.
- A JavaScript frontend calling <code>GET /api/data</code> and needing HTTP 401 with JSON to display a prompt/login guidance.
- An AJAX request calling <code>/app/profile</code> with header <code>X-Requested-With: XMLHttpRequest</code>; JavaScript wants 401 JSON instead of receiving the login form's HTML.
- A logged-in user lacking `ROLE_ADMIN` calling <code>GET /api/admin/summary</code>; this case must be denied by authorization, **not** confused with being unauthenticated.

If a single default entry point is used for all paths, the UI can suffer issues:
- APIs return 302 to <code>/login</code>; `fetch` follows the redirect automatically and tries to parse HTML as JSON.
- Browsers visiting web pages see a JSON body <code>{"error":"unauthorized"}</code> instead of a login page.
- An HTTP Basic client fails to receive an appropriate <code>WWW-Authenticate</code> header and does not know how to supply credentials.
- Conflating 401 and 403 causes frontends to retry login endlessly even when the user is logged in and simply lacks permissions.

<code>DelegatingAuthenticationEntryPoint</code> allows an application to **route authentication failure responses according to request characteristics** within the same <code>SecurityFilterChain</code>.

### Desired Behavior Matrix

| Request | Authentication | Outcome |
| --- | --- | --- |
| GET /public | Anonymous | 200 — public endpoint |
| GET /api/data | Anonymous | 401 JSON |
| GET /api/admin/summary | Anonymous | 401 JSON — authentication required first |
| GET /app/profile | Anonymous, normal browser | 302 redirect to /login |
| GET /app/profile, X-Requested-With: XMLHttpRequest | Anonymous | 401 JSON |
| GET /api/data | Logged-in user | 200 JSON |
| GET /api/admin/summary | User ROLE_USER | 403 — has identity but lacks ROLE_ADMIN |
| GET /api/admin/summary | User ROLE_ADMIN | 200 JSON |

The table above is the **demo's contract**; it does not imply every application must use 302 or the same JSON body. For SPAs, a different API auth endpoint and login flow may be more suitable. Define the contract before writing matchers.

## 2. What Interface Is AuthenticationEntryPoint?

Spring Security Servlet provides the interface:

~~~java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.core.AuthenticationException authException
    ) throws java.io.IOException, jakarta.servlet.ServletException;
}
~~~

The signature above is reproduced to illustrate the contract, not as an interface file learners need to create. The <code>commence</code> method initiates a response for a client that needs to authenticate.

Some common implementations:

| Entry point | Typical behavior |
| --- | --- |
| <code>LoginUrlAuthenticationEntryPoint</code> | Redirects the browser to a login URL |
| <code>HttpStatusEntryPoint</code> | Returns a fixed HTTP status without building a JSON body itself |
| <code>BasicAuthenticationEntryPoint</code> | Sends 401 with a <code>WWW-Authenticate: Basic ...</code> challenge |
| <code>BearerTokenAuthenticationEntryPoint</code> | Supports Bearer challenges per OAuth2 Resource Server/RFC 6750 |
| <code>Http403ForbiddenEntryPoint</code> | Returns 403 in certain authentication models; not the default choice for anonymous APIs needing 401 |
| <code>DelegatingAuthenticationEntryPoint</code> | Selects another entry point based on an ordered list of <code>RequestMatcher</code>s |

This interface **does not perform login itself**. For example, redirecting to <code>/login</code> merely directs the browser to the authentication flow; processing username/password belongs to the corresponding authentication filter/provider.

An <code>AuthenticationEntryPoint</code> can send a redirect, write a JSON body, set headers, or return a challenge. If implementing one yourself, handle responses consistently and never expose sensitive exception details to clients.

## 3. ExceptionTranslationFilter Decides When to Invoke the Entry Point

On a protected request, <code>ExceptionTranslationFilter</code> serves as the bridge between Java security exceptions and HTTP responses.

~~~text
HTTP request
    |
    v
Spring SecurityFilterChain
    |
    v
Authorization / downstream protected component
    |
    +-- Allow ----------------------------> Controller
    |
    +-- AuthenticationException ----------> ExceptionTranslationFilter
    |                                        |
    |                                        v
    |                                AuthenticationEntryPoint.commence(...)
    |                                        |
    |                               JSON 401 / login redirect
    |
    '-- AccessDeniedException
           |
           +-- Anonymous or authentication
           |   not meeting required level
           |       |
           |       v
           |   AuthenticationEntryPoint.commence(...)
           |
           '-- Authenticated but lacking permissions
                   |
                   v
              AccessDeniedHandler
                   |
                  403
~~~

The actual mechanism also involves <code>AuthenticationTrustResolver</code>, remember-me, policies requiring full authentication, and <code>RequestCache</code>. The key point is never to use a simplistic rule like "every `AccessDeniedException` is 403" or "every 401 comes from the same exception".

**An anonymous user** accessing <code>/api/admin/summary</code> is denied by the <code>hasRole("ADMIN")</code> rule; <code>ExceptionTranslationFilter</code> can invoke the authentication entry point instead of returning 403 directly, because the user is not yet authenticated.

**A logged-in `ROLE_USER` user** lacking ADMIN fails authorization; normally <code>AccessDeniedHandler</code> returns 403 without calling the delegating authentication entry point. These two flows must be tested separately.

### Important Boundary

<code>DelegatingAuthenticationEntryPoint</code> does not necessarily handle **every** login error. For instance, a form-login failure may be handled by <code>UsernamePasswordAuthenticationFilter</code>'s <code>AuthenticationFailureHandler</code>; HTTP Basic failure may be handled by <code>BasicAuthenticationFilter</code> calling its own entry point; an OAuth2 Resource Server has its own handlers and challenges. Do not conclude that replacing one entry point replaces all error handlers of every authentication mechanism.

## 4. How Does DelegatingAuthenticationEntryPoint Choose?

The implementation <code>org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint</code> takes an **ordered** mapping from <code>RequestMatcher</code> to <code>AuthenticationEntryPoint</code>.

Selection flow:

~~~text
DelegatingAuthenticationEntryPoint.commence(request, response, exception)
         |
         v
Check first matcher
         |
         +-- matches? YES --> entryPoint #1.commence(...)
         |
         '-- NO --> check second matcher
                              |
                              +-- YES --> entryPoint #2.commence(...)
                              |
                              '-- NO --> ... keep checking
                                           |
                                           v
                                     defaultEntryPoint
~~~

Core API:

~~~java
LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings =
    new LinkedHashMap<>();

mappings.put(apiMatcher, jsonEntryPoint);
mappings.put(ajaxMatcher, jsonEntryPoint);

DelegatingAuthenticationEntryPoint selected =
    new DelegatingAuthenticationEntryPoint(mappings);

selected.setDefaultEntryPoint(
    new LoginUrlAuthenticationEntryPoint("/login"));
~~~

**Use <code>LinkedHashMap</code>** to preserve insertion order. When multiple matchers match simultaneously, the **first matching** entry point is invoked. <code>HashMap</code> makes no guarantee of insertion order, so it must not be used when matcher priority is part of the behavior.

Always set an explicit **default entry point** for requests matching none of the listed matchers. Without an appropriate fallback, configuration/initialization may fail; even if validation passes, unclassified requests will lack the desired response contract.

### A Matcher Is Not an Authorization Rule

These two ideas are distinct:
- <code>requestMatchers("/api/**").authenticated()</code>: the request requires authentication to access.
- <code>apiMatcher -&gt; jsonEntryPoint</code>: if authentication needs to be initiated on this request, send the response in JSON format.

Having a matcher choose JSON does not grant permission to call the API. Never write conditions like "if it's AJAX then `permitAll` because the frontend will handle it"; clients can forge AJAX headers themselves. **Client-side UX is not authorization.**

## 5. Choosing Matchers: Path, Header, Accept, and Order

Request attributes commonly used to choose response formatting:
- **Path:** <code>/api/**</code> uses JSON, <code>/app/**</code> is for web pages.
- **Header:** <code>X-Requested-With: XMLHttpRequest</code> for AJAX requests from some frontends.
- **Accept:** <code>Accept: application/json</code> can signal a preference for JSON.
- **Content negotiation:** <code>MediaTypeRequestMatcher</code> can be configured to handle more complex `Accept`/media-type rules.

In the demo, two predictable matchers are chosen: <code>/api/**</code> first, the <code>X-Requested-With</code> header second, and the login redirect default last. Choosing path as the primary criterion ensures APIs always return JSON even when clients send <code>Accept: */*</code> or omit headers.

### Why Be Careful with Accept?

Some browsers and HTTP clients send:
- <code>Accept: */*</code>, meaning any media type is accepted.
- <code>Accept: text/html,application/xhtml+xml,...</code> for navigation.
- <code>Accept: application/json</code> for JavaScript `fetch`.
- Multiple media types with <code>q</code> quality factors.

String checking via <code>header.contains("application/json")</code> can mishandle complex headers. When true content negotiation is needed, use an abstraction such as <code>MediaTypeRequestMatcher</code> with a version-appropriate <code>ContentNegotiationStrategy</code>; test <code>*/*</code>, quality factors, malformed headers, and defaults.

Never use `Accept` to alter resource access permissions. It is merely a signal for **representation**, not a trustworthy user indicator.

### Is the X-Requested-With Header Trustworthy?

<code>X-Requested-With</code> can be set arbitrarily by any client. Therefore it should only choose JSON vs. redirect, **never** serve as a security boundary to skip CSRF, bypass authentication, or elevate roles. Newer AJAX clients may not send this header automatically either; define an explicit frontend contract.

## 6. Define the Response Contract Before Implementing

In the demo system:

| Unauthenticated request type | Matcher | Response |
| --- | --- | --- |
| Any <code>/api/**</code> | API path | 401; <code>Content-Type: application/json</code>; body <code>{"error":"unauthorized"}</code> |
| Non-API with standard AJAX header | `X-Requested-With` header | 401 with same JSON body |
| Normal web navigation | Matches neither matcher above | 302 with <code>Location: /login</code> or context-equivalent URL |
| <code>/public</code> endpoint | `permitAll` authorization | Entry point not called; 200 |
| Authenticated user missing role | `AccessDeniedHandler` | 403; body per configuration |

The JSON example is intentionally kept **stable and free of exception messages**:

~~~json
{"error":"unauthorized"}
~~~

In production, you may include a non-sensitive <code>code</code>, <code>message</code>, <code>traceId</code>, or a shared error envelope, but never return stack traces, guessed usernames, raw tokens, login credentials, or internal details.

**Do not redirect APIs and return a 200 HTML login page**, because a `fetch` client may follow the redirect automatically and never see the 401. Conversely, browser navigation to an HTML page requiring login generally has a better UX with an intentional redirect.

## 7. Complete Sample Project with Spring Boot and Spring Security

The example uses **Java 17, Spring Boot 3.3.5, Spring Security 6.x, and Maven**. The application has form login with two demo accounts, plus public, API, web page, and admin API endpoints. The goal is to demonstrate the delegating entry point working inside **a single `SecurityFilterChain`**.

Structure:

~~~text
delegating-entry-point-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/entrypoint/
    │   ├── EntryPointApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/entrypoint/
        └── DelegatingEntryPointTest.java
~~~

Demo accounts:
- <code>alice</code>: `ROLE_USER`, password <code>alice-local-1234</code>.
- <code>admin</code>: `ROLE_USER` and `ROLE_ADMIN`, password <code>admin-local-1234</code>.

These passwords are for localhost only; never use them in real deployments.

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>delegating-entry-point-demo</artifactId>
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

### 7.2. EntryPointApplication.java

Create <code>src/main/java/com/example/entrypoint/EntryPointApplication.java</code>:

~~~java
package com.example.entrypoint;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EntryPointApplication {
    public static void main(String[] args) {
        SpringApplication.run(EntryPointApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Create <code>src/main/java/com/example/entrypoint/SecurityConfiguration.java</code>:

~~~java
package com.example.entrypoint;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-local-1234"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-local-1234"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Prioritize requests with path /api/**.
        RequestMatcher apiMatcher = new AntPathRequestMatcher("/api/**");

        // Some frontends identify AJAX via X-Requested-With.
        RequestMatcher ajaxMatcher = request ->
            "XMLHttpRequest".equals(
                request.getHeader("X-Requested-With"));

        // Response for API/AJAX when requiring authentication.
        AuthenticationEntryPoint json401 =
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setCharacterEncoding(
                    StandardCharsets.UTF_8.name());
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
                // Do not return exception.getMessage() to the client.
                response.getWriter()
                    .write("{\"error\":\"unauthorized\"}");
            };

        LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mapping =
            new LinkedHashMap<>();
        mapping.put(apiMatcher, json401);
        mapping.put(ajaxMatcher, json401);

        DelegatingAuthenticationEntryPoint delegated =
            new DelegatingAuthenticationEntryPoint(mapping);

        // Regular web requests forward to the login form.
        delegated.setDefaultEntryPoint(
            new LoginUrlAuthenticationEntryPoint("/login"));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/api/admin/**", "/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/**", "/app/**")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(delegated))
            .build();
    }
}
~~~

**Ordered analysis:**
1. <code>apiMatcher</code> relies solely on the <code>/api/**</code> path, so APIs receive JSON 401 even if the request omits <code>X-Requested-With</code>.
2. <code>ajaxMatcher</code> is evaluated after the API matcher and applies to remaining URLs when the header equals <code>XMLHttpRequest</code>.
3. <code>LinkedHashMap</code> keeps priority explicit; do not use <code>HashMap</code>.
4. <code>delegated.setDefaultEntryPoint(...)</code> provides the redirect fallback for web navigation.
5. <code>.exceptionHandling(errors -&gt; errors.authenticationEntryPoint(delegated))</code> configures the entry point for errors translated by <code>ExceptionTranslationFilter</code> into authentication-start requests.
6. <code>.formLogin(...)</code> provides the username/password flow and default login page.
7. <code>/login</code> is permitted (`permitAll`) to prevent redirect loops and let the login page render for anonymous visitors.
8. <code>/api/admin/**</code> is listed **before** <code>/api/**</code> in authorization rules so `ROLE_ADMIN` remains a distinct condition. Do not reverse those two URL rules and assume an entry point choosing JSON will preserve admin permissions on its own.
9. <code>.anyRequest().denyAll()</code> denies undeclared paths; in a real application you must also classify static resources, health checks, and valid routes.
10. <code>json401</code> writes minimal JSON, status 401, UTF-8 charset, and `Cache-Control: no-store`, leaking no exception details externally.

**Technical note:** <code>AntPathRequestMatcher</code> is present in Spring Security 6.3.x of Spring Boot 3.3.5; in newer Spring Security lines, some matcher APIs may recommend switching to path-pattern-based request matchers. When upgrading versions, use the version-accurate matcher API and verify path semantics. Do not mechanically apply newer-version code to 6.3 or vice versa.

### 7.4. DemoController.java

Create <code>src/main/java/com/example/entrypoint/DemoController.java</code>:

~~~java
package com.example.entrypoint;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/data")
    public Map<String, String> apiData(Authentication auth) {
        return Map.of("name", auth.getName(), "data", "sample");
    }

    @GetMapping("/app/profile")
    public Map<String, String> appProfile(Authentication auth) {
        return Map.of("name", auth.getName());
    }

    @GetMapping("/api/admin/summary")
    public Map<String, String> adminSummary() {
        return Map.of("status", "admin-only");
    }

    @GetMapping("/admin/panel")
    public Map<String, String> adminPanel() {
        return Map.of("status", "admin-panel");
    }
}
~~~

In the demo, both <code>/app/profile</code> and <code>/api/data</code> return JSON once authenticated so tests focus on **responses when authentication is insufficient**. A real HTML application might render a template at <code>/app/profile</code>; that does not change the entry point's responsibility.

Anonymous users do not reach private route controllers: <code>ExceptionTranslationFilter</code> routes the authentication-initiation request to the appropriate entry point.

## 8. Testing with MockMvc — Verify Every Matcher Branch

Create <code>src/test/java/com/example/entrypoint/DelegatingEntryPointTest.java</code>:

~~~java
package com.example.entrypoint;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DelegatingEntryPointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteDoesNotInvokeAnEntryPoint() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousApiRequestGetsJson401() throws Exception {
        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.error").value("unauthorized"))
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void anonymousApiAdminStillGets401BeforeLogin() throws Exception {
        mvc.perform(get("/api/admin/summary"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void anonymousBrowserNavigationRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/app/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void ajaxRequestToWebPathGetsJson401() throws Exception {
        mvc.perform(get("/app/profile")
                .header("X-Requested-With", "XMLHttpRequest"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void apiMatcherWinsEvenWithoutAjaxHeader() throws Exception {
        mvc.perform(get("/api/data")
                .header("Accept", "text/html"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void authenticatedWithoutAdminRoleGets403NotLoginRedirect()
            throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUsersCanAccessAllowedResources()
            throws Exception {
        mvc.perform(get("/api/data")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/admin/summary")
                .with(user("admin").roles("USER", "ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-only"));
    }

    @Test
    void defaultLoginPageIsReachableWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }
}
~~~

The tests prove several things independently:
- `permitAll` authorization genuinely skips the entry point for `/public`.
- Anonymous access to an API requiring auth gets 401 JSON, not 302/HTML.
- Anonymous access to the admin API still requires initiating authentication rather than returning 403 just because the URL requires `ADMIN`.
- A browser hitting a web path gets the login redirect from the default entry point.
- AJAX hitting the same web path gets 401 JSON, demonstrating the per-request selector works.
- The API path always takes priority, even when `Accept` is `text/html`.
- An authenticated user lacking `ROLE_ADMIN` gets 403 via the access-denied flow.
- Users with valid permissions receive 200 and endpoint data.
- The login page is `permitAll` to avoid loops.

Spring Security Test's <code>.with(user(...))</code> sets a user on the MockMvc request. It is suitable for testing authorization/entry points in tests; it does **not** prove form-login databases, password hashing, or real session cookies work. For those, add tests for `POST /login` with CSRF, session persistence, and the login failure handler.

**Scope of results:** the test code was reviewed for API and logic accuracy, not executed live during authoring of this lesson. Run <code>mvn test</code> with JDK 17+ and the corresponding dependencies to verify every assertion on your active framework version; redirect URLs and generated login pages can also vary by context path depending on deployment.

## 9. Manual Testing with curl and Browser

Run:

~~~bash
mvn test
mvn spring-boot:run
~~~

Example unauthenticated requests:

~~~bash
# Public: 200 JSON.
curl -i http://localhost:8080/public

# API: 401 JSON.
curl -i http://localhost:8080/api/data

# API still returns JSON even when Accept hints at HTML.
curl -i -H "Accept: text/html" http://localhost:8080/api/data

# Browser-style request: redirect to /login.
curl -i http://localhost:8080/app/profile

# AJAX request to web path: 401 JSON.
curl -i -H "X-Requested-With: XMLHttpRequest" \
  http://localhost:8080/app/profile

# Spring Security login page.
curl -i http://localhost:8080/login
~~~

For form login, hitting <code>GET /login</code> renders HTML. When testing login via `POST /login` with `curl`, you must send a valid CSRF token and corresponding cookie; sending only username/password without CSRF will rightly yield 403. Never disable CSRF just to make manual requests convenient.

| Request | Expected | Explanation |
| --- | --- | --- |
| GET /public anonymous | 200 JSON | `permitAll` |
| GET /api/data anonymous | 401 JSON | API matcher |
| GET /api/data, Accept text/html | 401 JSON | API path still takes priority |
| GET /app/profile anonymous | 302 /login | Default `LoginUrlAuthenticationEntryPoint` |
| GET /app/profile, X-Requested-With | 401 JSON | AJAX matcher |
| GET /login anonymous | 200 HTML login | Form-login page |
| GET /api/admin/summary, user ROLE_USER | 403 | `AccessDeniedHandler` |
| GET /api/admin/summary, user ROLE_ADMIN | 200 JSON | Sufficient permissions |

To test the authenticated rows in a browser, log in via the form and use the session cookie. Do not assume `curl -u username:password` will log in successfully when the demo configures only **form login** without enabling <code>httpBasic()</code>. To use HTTP Basic in a project, configure it explicitly and understand `BasicAuthenticationFilter`/entry-point semantics before testing.

## 10. 401 Differs from 403: Do Not Use DelegatingAuthenticationEntryPoint for Every Error

**401 Unauthorized** in real HTTP typically means the client is not yet validly authenticated to access the resource; depending on the authentication scheme, the response may require a <code>WWW-Authenticate</code> challenge. In particular, HTTP Basic and OAuth2 Bearer have protocol requirements beyond this JSON-only demo.

**403 Forbidden** means the request was understood but the server refuses access; in Spring Security it typically occurs when an `Authentication` exists yet authority/policy forbids the action. Another 403 can come from CSRF blocking the request, even when the user is not logged in; never deduce that 403 guarantees a missing role.

Example:

~~~text
Anonymous -> GET /api/admin/summary
    |
    v
hasRole(ADMIN) fails
    |
ExceptionTranslationFilter sees unauthenticated
    |
DelegatingAuthenticationEntryPoint
    |
401 {"error":"unauthorized"}


Alice logged in (ROLE_USER) -> GET /api/admin/summary
    |
    v
hasRole(ADMIN) fails
    |
AccessDeniedHandler
    |
403 (body per config)
~~~

If you want **consistent JSON 403** for APIs, configure <code>AccessDeniedHandler</code> separately, optionally using a matching matcher/delegation pattern; never force <code>AuthenticationEntryPoint</code> to handle both situations.

An illustrative snippet (not a standalone runnable file):

~~~java
AccessDeniedHandler apiForbidden = (request, response, denied) -> {
    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
    response.getWriter().write("{\"error\":\"forbidden\"}");
};

// This is an access denied handler, not an AuthenticationEntryPoint.
// Combine with a path matcher if you only want JSON for /api/**.
~~~

If you apply <code>apiForbidden</code> across the entire application, HTML pages may also return JSON 403. Like the authentication entry point, access-denied responses need policies matching client contracts. However, **the missing-permission decision** must come from authorization, not from the `Accept` or `X-Requested-With` headers.

## 11. Why Does a Failed Login Request Not Necessarily Go Through the Delegate?

There are several error sources that look like "not logged in" yet are handled by other components:

| Scenario | Component involved |
| --- | --- |
| Anonymous hitting protected URL | `ExceptionTranslationFilter` + `AuthenticationEntryPoint` |
| Authenticated user missing role | `AccessDeniedHandler` |
| `POST /login` wrong password | `UsernamePasswordAuthenticationFilter` + `AuthenticationFailureHandler` |
| `POST` missing CSRF token | `CsrfFilter` + `AccessDeniedHandler`/exception translation depending on scenario |
| Invalid HTTP Basic credentials | `BasicAuthenticationFilter` and appropriate authentication entry point |
| Wrong/expired JWT Bearer token | Bearer token filter/handler and OAuth2 resource-server entry point |
| Controller throwing business exception itself | MVC exception resolver / error handling, not auth entry point by default |

In the demo, <code>.formLogin(Customizer.withDefaults())</code> also has its own behavior on form-login failure, typically redirecting to <code>/login?error</code>. Configuring <code>DelegatingAuthenticationEntryPoint</code> alone will not make a `POST /login` with a wrong password automatically return JSON like an anonymous `GET /api/data`.

If an application has a dedicated login API, define a failure handler/exception handling for **that exact endpoint**, while preserving appropriate CSRF/session policies.

## 12. HTTP Basic and OAuth2 Bearer: Challenges Are Not Just JSON

HTTP Basic specifies that clients can receive a challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

For OAuth2 Bearer, headers can carry the `Bearer` scheme and error metadata per RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

These headers are formatting examples; real values depend on the authentication server/filter and token state. For an OAuth2 resource server, <code>BearerTokenAuthenticationEntryPoint</code> and <code>BearerTokenAccessDeniedHandler</code> are designed to satisfy Bearer semantics. Do not replace all of them with a bare custom JSON 401 if doing so drops <code>WWW-Authenticate</code> or required challenge details.

Similarly, <code>BasicAuthenticationEntryPoint</code> does not merely pick status 401—it also emits the Basic challenge. If both <code>httpBasic()</code> and <code>formLogin()</code> are enabled, the framework has default logic selecting entry points by request media type and authentication flow; that selection does not necessarily mirror a simple selector you write yourself.

**Rule:** if a client must follow an authentication protocol (Basic, Bearer/OAuth2, OIDC), prefer the standard handler/entry point for that scheme and assert both headers and status. Only use custom JSON when the application's contract allows it, and configure it so it does not break the authentication filter's independent error path.

## 13. RequestCache and SavedRequest: Side Effects of Redirect/Login

In a form-login application, Spring Security can save a request requiring authentication into <code>RequestCache</code>, typically via <code>HttpSessionRequestCache</code>-related mechanics, to redirect the user back to the original page after login.

Example:

~~~text
Anonymous browser: GET /app/profile
    |
    v
Security requires login
    |
RequestCache may save /app/profile
    |
    v
Redirect /login
    |
User logs in
    |
    v
Redirect back to pre-login page (if configured that way)
~~~

This can be desirable UX for web navigation. However, API requests returning JSON 401 normally **do not need** the server to create a session merely to store a failed API request. When sharing one security chain between browser and API, verify whether request-cache logic creates unwanted `HttpSession`s for anonymous API calls.

One design approach is configuring <code>RequestCache</code> with a matcher that saves only browser navigations, or splitting API/web into separate <code>SecurityFilterChain</code>s with dedicated session/request-cache policies. <code>NullRequestCache</code> is an option for flows that should not save requests; **do not replace the entire request cache with `NullRequestCache`** if the product still needs post-login return to the prior page.

Choosing JSON vs. redirect responses does not automatically change session creation policy. Test <code>Set-Cookie</code>, session storage, and saved requests when operational requirements demand a stateless API.

## 14. One Chain with a Delegate or Multiple SecurityFilterChains?

<code>DelegatingAuthenticationEntryPoint</code> is useful when requests share the same security chain and most authentication/session behavior, differing only in **the response when initiating authentication**.

When API and HTML web diverge significantly in:
- Authentication mechanism (Bearer JWT vs. session form login).
- Session policy (`STATELESS` vs. `IF_REQUIRED`).
- CSRF rules.
- Request cache and CORS.
- Authorization rules and failure handlers.
- OAuth2 protocol challenges.

then splitting into multiple <code>SecurityFilterChain</code>s with <code>securityMatcher("/api/**")</code> for the API and a fallback chain for web can be cleaner.

~~~text
Incoming request
        |
        v
FilterChainProxy picks the first matching SecurityFilterChain
        |
        +--> API chain: Bearer, STATELESS, API entry point
        |
        '--> WEB chain: formLogin, sessions, login redirect
~~~

**Distinguish two levels of selection:**
1. <code>FilterChainProxy</code> picks a `SecurityFilterChain` by chain-level matcher and <code>@Order</code>.
2. Inside a chain, <code>DelegatingAuthenticationEntryPoint</code> picks an `AuthenticationEntryPoint` by matcher when authentication must start.

A delegate in chain B has **no** effect on requests already claimed by chain A. And never use an authentication entry point in place of policies that select authentication filters.

## 15. Custom Error Responses Must Be Safe

When implementing a JSON entry point yourself:
- Keep the body generic; never expose <code>AuthenticationException.getMessage()</code>, stack traces, user existence, or internal config details.
- Use status codes fitting the scheme/contract; APIs needing auth in the demo return 401, while browsers redirect 302.
- Keep <code>Content-Type</code> consistent and JSON valid; never write half a JSON body and then redirect.
- You can use <code>Cache-Control: no-store</code> for cacheable auth-related responses.
- Never echo tokens, passwords, cookies, or raw `Authorization` headers into error bodies/logs.
- If generating a trace ID, ensure it leaks no secrets and correlates cleanly with security logs.
- Never blindly trust <code>X-Requested-With</code> or <code>Accept</code> headers; they only select response format.
- Never take <code>returnUrl</code> from a query parameter to <code>sendRedirect</code> to an arbitrary external URL, which easily enables open redirects/phishing. If return-to is needed, validate against an allowlist and store safe paths.

Align the response envelope across gateways, Spring MVC exception handlers, authentication entry points, and access-denied handlers. These layers handle different exceptions; **no single handler covers every error automatically**.

## 16. CSRF, CORS, and AJAX Are No Excuse to Skip Authentication

An SPA frontend may use the `fetch` API and send <code>Accept: application/json</code> and <code>X-Requested-With</code>. Those headers **do not** grant extra permission to access resources. CORS only controls browser cross-origin access; it does not replace authentication/authorization. APIs called from browsers with cookies/sessions may still need CSRF protection on `POST`/`PUT`/`DELETE`.

In the demo, `GET` is read-only and CSRF stays at its default. If adding:

~~~java
@PostMapping("/api/update")
public void update(@RequestBody UpdateBody input) {
    // Mutates state; must have proper policy, validation, and CSRF.
}
~~~

that is only an illustrative snippet; `UpdateBody` and authorization must be defined in a real system. Do not disable CSRF app-wide just because the API wants JSON 401; CSRF failures are a distinct branch from anonymous `GET`s. For Bearer-only stateless APIs not relying on auto-sent cookies, the threat model may differ; analyze how credentials are transmitted.

### Responses After Session Timeout

A user on a web page whose session expires:
- Browser navigation to a private page can receive a login redirect.
- Background `fetch` to an API can receive 401 JSON.
- The frontend must handle 401 to update UI, avoid infinite retries, and never treat error JSON as valid data.

However, if the user is authenticated and gets 403, the frontend should show an insufficient-permissions notice or guide the user to a permission-request flow rather than trapping them in infinite re-login loops.

## 17. Common Configuration Mistakes

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| API receives 302/HTML login | API matcher did not match, default redirect won | Check path, context/servlet mapping, and matcher order |
| Web navigation receives JSON 401 | Header/path matcher too broad | Narrow matchers; test requests without AJAX headers |
| Switching to `HashMap` changed responses | Insertion order lost | Use `LinkedHashMap`, specific matchers first |
| Unmatched requests handled strangely | Missing or wrong default entry point | Set an explicit fallback |
| `GET /login` redirect loop | `/login` not accessible to anonymous | `permitAll` login page and supporting paths |
| Logged-in API user missing role gets 403 instead of JSON 401 | That is `AccessDeniedHandler`, not entry point | Configure separate 403 handler if JSON needed |
| Form login wrong password still redirects `/login?error` | Separate `AuthenticationFailureHandler` | Configure login failure contract if required |
| API `POST` missing CSRF gets 403 | Blocked by CSRF filter | Design proper CSRF/token handling; do not disable blindly |
| HTTP Basic client shows no challenge | JSON entry point omitted `WWW-Authenticate` | Use `BasicAuthenticationEntryPoint` matching scheme |
| Bearer client lacks challenge/`invalid_token` semantics | Overrode resource server entry point too broadly | Keep `BearerTokenAuthenticationEntryPoint` |
| Anonymous API unexpectedly creates `HttpSession` | `RequestCache` or stateful session policy | Adjust request cache/chain/sessions |
| Matcher checks only `Accept` and sends HTML to API | `Accept */*` or unexpected header | Prioritize API path or proper content negotiation |
| AJAX header enables authorization bypass | Confused response selection with access policy | Headers only pick representation, never grant access |
| API and web use multiple chains, delegate on wrong chain | `FilterChainProxy` chose another chain | Verify chain-level `securityMatcher`/`@Order` |
| MockMvc test uses `@WithMockUser` for anonymous test | Test is no longer anonymous | Separate anonymous and authenticated tests |
| All 401s replaced with 403 | Used 403 entry point for anonymous API | Review authentication challenge contract |
| JSON body has encoding bugs or leaks exception details | Custom entry point wrote unescaped output | Fixed body, UTF-8, `no-store`, and safe logging |
| Proxy/gateway bypasses cause wrong path matching | Different servlet path, context path, or forwarded headers | Test actual deployment URIs and configure proxy properly |

## 18. Testing and Operations Checklist

1. Inventory client types: HTML browser, SPA AJAX, machine API, Basic/Bearer/OIDC, and each client's response requirements.
2. Define the authentication/authorization boundary: entry point for **initiating auth**, access-denied handler for **missing permissions after auth**.
3. Pick `RequestMatcher`s deliberately; prefer stable paths for APIs and headers/media-types to refine representation.
4. Use <code>LinkedHashMap</code> to preserve priority; specific matchers before broad matchers.
5. Configure a default entry point for unmatched requests.
6. Verify login pages/public resources are `permitAll` to avoid redirect loops.
7. Keep URL policies ordered: <code>/api/admin/**</code> must be evaluated before <code>/api/**</code>.
8. Test JSON 401: status, content type, body, cache headers, and **no redirect**.
9. Test browser redirects: 3xx status and `Location` to login under the right context path.
10. Test AJAX to a web path to prove the header branch triggers.
11. Test anonymous on admin API receives 401, `ROLE_USER` on the same endpoint receives 403, and admin receives 200.
12. Test form-login failures separately; do not assume the delegate handles every credential failure.
13. If HTTP Basic/OAuth2 Bearer are enabled, verify protocol-compliant `WWW-Authenticate`/challenges.
14. Check `RequestCache`/session creation for anonymous API calls if zero session creation is required.
15. With multiple `SecurityFilterChain`s, verify chain-level matchers and chain selection order.
16. Never use client headers as conditions to skip CSRF, authentication, or authorization.
17. Never return raw exceptions, tokens, passwords, session IDs, or stack traces in JSON responses or logs.
18. When changing context paths, reverse proxies, matcher frameworks, or Spring Security versions, re-run end-to-end integration tests.

## 19. Self-Check Questions

**Question 1:** Does <code>DelegatingAuthenticationEntryPoint</code> decide whether a user has permission to view a document?  
**Answer:** No. It only chooses how to respond when authentication needs to start. Authorization is decided by separate request/method policies.

**Question 2:** Why use <code>LinkedHashMap</code> instead of <code>HashMap</code> when declaring matchers?  
**Answer:** Because the first matching entry point is chosen; insertion order must be preserved.

**Question 3:** Should an anonymous call to <code>/api/admin/summary</code> receive 401 or 403 in the demo?  
**Answer:** 401 JSON because the caller is not yet authenticated; only after logging in yet lacking `ADMIN` does it receive 403.

**Question 4:** A logged-in `ROLE_USER` calls an `ADMIN` API and gets 403. Is the delegating authentication entry point broken?  
**Answer:** No. That is the access-denied flow due to missing permissions; to get JSON 403, configure `AccessDeniedHandler` separately.

**Question 5:** Is a `POST /login` with a wrong password guaranteed to go through <code>DelegatingAuthenticationEntryPoint</code>?  
**Answer:** No. Form login has its own <code>AuthenticationFailureHandler</code>, typically redirecting to `/login?error`; other authentication filters also have their own handlers.

**Question 6:** Does an API receiving JSON 401 guarantee no `HttpSession` is ever created?  
**Answer:** No. `RequestCache`/session policy is independent of the response entry point; test and configure separately if statelessness is required.

**Question 7:** If a client sends <code>X-Requested-With: XMLHttpRequest</code> itself, can it bypass the `ROLE_ADMIN` check?  
**Answer:** No. That header only changes the response format when authentication is insufficient; it has zero effect on granting permissions.

**Question 8:** Why must HTTP Basic or Bearer be weighed carefully before replacing with a bare JSON 401?  
**Answer:** Because those schemes may require standard <code>WWW-Authenticate</code>/challenge semantics; a custom body must not drop required headers.

**Question 9:** When two `SecurityFilterChain`s exist, does a delegate in the web chain decide responses for the API chain?  
**Answer:** No. `FilterChainProxy` selects the matching chain first; a delegate only runs inside the chain that uses it.

**Question 10:** When should you use multiple chains instead of one chain with a delegate?  
**Answer:** When API and web differ substantially in authentication mechanism, sessions, CSRF, request cache, or protocol; a delegate fits best when the main difference is how authentication is requested.

**Remember:** <code>DelegatingAuthenticationEntryPoint</code> is **a selector for authentication-commencement responses using ordered `RequestMatcher`s**, not an authorization engine. In Spring Security Servlet, understand <code>ExceptionTranslationFilter</code>, distinguish 401/403, set a clear fallback, keep protocol-compliant challenges, and test API, AJAX, browser, and authenticated user states alike.
