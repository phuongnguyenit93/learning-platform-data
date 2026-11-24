# Extracting Path Variables to Match the Caller's Identity in Spring Security Servlet

## Objectives and Context

In a Servlet API with user-bound paths, such as `GET /users/alice/profile`, the `alice` part is usually called a **URI template variable** or **path variable**. The system needs to answer: is the current request sender allowed to view alice's profile? Simply accepting a `username` parameter in the controller creates no authorization mechanism: the client can trivially change the path to `/users/bob/profile`.

Spring Security 6 provides HTTP authorization via `authorizeHttpRequests`, `RequestMatcher`, and `AuthorizationManager`. When a `RequestMatcher` contains a path variable, Spring Security can pass the extracted variables into **`RequestAuthorizationContext.getVariables()`**, allowing comparison of the username in the URL with the **authenticated caller's `Authentication`**. This clearly expresses the policy **only the account owner or an administrator may access**, before the request reaches the controller.

After this lesson, you will be able to:

1. Distinguish path variables, query parameters, request data, and authenticated identity.
2. Understand how `requestMatchers` combines URI templates, `HttpMethod`, path variables, and `AuthorizationManager`.
3. Use `RequestAuthorizationContext.getVariables()`, `Authentication.getName()`, and `AuthorizationDecision` to block access by the wrong account owner.
4. Write a Java 17+ Spring Boot 3.x / Spring Security 6.x application with a `GET /users/{username}/profile` example.
5. Test anonymous, owner, other user, administrator, forged header, and query parameter cases.
6. Distinguish HTTP authorization from record-level business checks; prevent IDOR/BOLA when paths contain resource IDs.
7. Identify bugs with matchers, rule order, URL encoding, path normalization, renamed accounts, and multiple `SecurityFilterChain`s.
8. Choose between a lambda `AuthorizationManager`, `WebExpressionAuthorizationManager`, and service-layer protection.

The context applies solely to **Spring Security Servlet**. Spring WebFlux APIs such as `ServerWebExchange` and `ReactiveAuthorizationManager` are not the classes used in this lesson.

## 1. Permission Model: The Path Is Client-Supplied Data

Consider three users:

| Authenticated Identity | Requested URL | Expectation If Only Owner May View |
| --- | --- | --- |
| alice | GET /users/alice/profile | Allow |
| alice | GET /users/bob/profile | Deny |
| bob | GET /users/bob/profile | Allow |
| bob | GET /users/alice/profile | Deny |
| unauthenticated guest | GET /users/alice/profile | Require authentication |
| admin with ROLE_ADMIN | GET /users/alice/profile | May allow per administrative policy |

The path `/users/alice/profile` **does not prove** the request was sent by alice. Likewise, an `X-User: alice` header, `?username=alice` query parameter, or body containing `"owner":"alice"` are all supplied by the client and are not proof of identity.

Trusted information for authorization must come from the configured authentication mechanism: Spring Security creates or verifies `Authentication` via `SecurityContext` from session, HTTP Basic, bearer token, etc. The authorization layer reads this `Authentication`, without decoding passwords or verifying tokens itself in place of `AuthenticationManager`/`Provider`.

Ideally, systems use a stable internal identity, such as a UUID user ID. Using `username` in the URL is just an API-learning example. If usernames can change or have complex normalization rules, literal string comparison on `username` may no longer reflect business policy.

### Request Diagram

~~~text
Client: GET /users/bob/profile + alice's credentials
            |
     FilterChainProxy / SecurityFilterChain
            |
     Authentication filter verifies alice
            |
     RequestMatcher matches /users/{username}/profile
            |   -> variables = {"username": "bob"}
            |
     AuthorizationManager<RequestAuthorizationContext>
            |   -> Authentication.name = "alice"
            |   -> path variable username = "bob"
            |   -> alice != bob and lacks ROLE_ADMIN
            |
     AuthorizationDecision(false)
            |
     Returns 403; profile controller never executes
~~~

If the client lacks a valid identity, HTTP Basic typically returns 401 with `WWW-Authenticate`; form login typically redirects to the login page. If the client is authenticated but lacks permission, 403 is typically returned. Exact responses depend on the application's `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `SecurityFilterChain`; never use HTTP status alone to conclude whether a password was right or wrong.

## 2. Three Easily Confused Data Types

### 2.1. Path Variable

MVC definition example:

~~~java
@GetMapping("/users/{username}/profile")
public String profile(@PathVariable("username") String username) {
    return "PROFILE:" + username;
}
~~~

With `GET /users/alice/profile`, the framework can bind `username = "alice"`. This is routing data carried by the URL; the controller receives it **after** the request passes the security filter chain, if allowed.

### 2.2. Query Parameter

The request `GET /users/alice/profile?username=bob` still has URI path `/users/alice/profile`. Query parameters do not automatically replace `{username}` in the URI template.

~~~text
Path:   /users/alice/profile
Query:  username=bob
Path variable username: alice
~~~

Spring MVC can read the query via `@RequestParam`, but you must not turn the query `username` into the basis for identifying the account owner when the policy protects the path variable.

### 2.3. Authentication

`Authentication` typically has `getName()` returning the identifier supplied by the authentication mechanism. For example, an `InMemoryUserDetailsManager` account named `alice` logging in via HTTP Basic gives `Authentication.getName()` returning `alice`.

With JWT, OIDC, or custom principals, `getName()` may be `subject`, email, ID, or a configured claim; **do not assume** it always equals the display username in the URL. You must align canonical identity definitions and security data mapping.

Never construct an `Authentication` from a query/header `X-User` unverified by a trusted component and treat it as the real caller.

## 3. How Does Spring Security Authorize URI Templates?

In Spring Security 6 on Servlet, `authorizeHttpRequests` rules apply to requests matching a `RequestMatcher`. A parameterized pattern:

~~~text
/users/{username}/profile
~~~

Curly braces represent a URI template variable; when a request matches, the matcher can return the corresponding variable data. In `AuthorizationManager<RequestAuthorizationContext>`, `context` provides:

~~~java
Map<String, String> variables = context.getVariables();
String usernameFromUrl = variables.get("username");
~~~

This is an illustrative snippet placed inside an `AuthorizationManager` callback; not a standalone Java file. This context bridges **URI matching** and **HTTP authorization**, avoiding manual `split("/")` URL slicing and guessing where the username sits.

A callback typically looks like:

~~~java
(authentication, context) -> {
    Authentication current = authentication.get();
    String target = context.getVariables().get("username");
    boolean allowed = /* check policy */;
    return new AuthorizationDecision(allowed);
}
~~~

- `authentication` is `Supplier<Authentication>`, so Spring Security can defer retrieving authentication when unnecessary.
- `context` is `RequestAuthorizationContext`, containing `HttpServletRequest` and variables provided by the matcher.
- `AuthorizationDecision(true)` allows; `false` denies.
- Do not assume `context.getVariables()` always contains the `username` key. A rule without variable declarations, a matcher not supporting extraction, or a mismatched path can yield unexpected data. The safe policy is **missing variable -> deny access**, never skip the check.
- Never read `request.getParameter("username")` as a substitute for variables extracted by the matcher.

### MvcRequestMatcher and Alignment with Spring MVC

In Spring MVC, `MvcRequestMatcher` can use `HandlerMappingIntrospector` to follow MVC's matching behavior. Using the builder with a pattern containing `{username}`, you can extract variables from `RequestAuthorizationContext` inside HTTP authorization rules.

Example:

~~~java
MvcRequestMatcher profileMatcher =
        new MvcRequestMatcher.Builder(introspector)
                .pattern(HttpMethod.GET, "/users/{username}/profile");
~~~

This is a snippet inside `SecurityConfig`, with `HandlerMappingIntrospector` provided by Spring MVC. The complete code section below includes full imports and `@Bean`s.

In other versions/configurations, `requestMatchers(String...)` may pick an appropriate matcher based on Spring MVC and classpath factors. For applications with multiple Servlets/mappings or altered path-matching strategies, declare matchers explicitly and **test real URLs**, rather than guessing matcher behavior from pattern shape alone.

If the system uses a matcher that does not support variable capture, you may not receive the expected data. Do not write authorization logic that "allows if variable is absent" to fix a `NullPointerException`; fix the matcher or design another policy.

## 4. Owner-Only or ADMIN Policy

Example rule:

**Allow `GET /users/{username}/profile` when the request is authenticated and either condition holds:**

1. `username` in the path equals `Authentication.getName()`, with consistent comparison rules.
2. `Authentication` holds the `ROLE_ADMIN` authority.

If the caller is unauthenticated, never grant access even if the path is `/users/anonymousUser/profile`. This point is critical: in Spring Security, `AnonymousAuthenticationToken` can report `isAuthenticated()` as `true` per token mechanics, yet it still represents an anonymous user, **not** a real account.

A self-checking implementation:

~~~java
private static AuthorizationManager<RequestAuthorizationContext>
ownerOrAdmin() {
    return (authentication, context) -> {
        Authentication current = authentication.get();
        String requestedUser = context.getVariables().get("username");

        boolean actualLogin = current != null
                && current.isAuthenticated()
                && !(current instanceof AnonymousAuthenticationToken);

        boolean sameUser = actualLogin
                && requestedUser != null
                && requestedUser.equals(current.getName());

        boolean admin = actualLogin && current.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));

        return new AuthorizationDecision(sameUser || admin);
    };
}
~~~

In this code:

- If `requestedUser` is null, `sameUser` is false; only an authenticated admin can pass. When the policy intends access only when the path variable exists, **you can require `requestedUser != null` for ADMIN too** to fail closed. The complete program section applies this condition.
- Real authentication is required for both owner and admin; never rely solely on `isAuthenticated()` on anonymous tokens.
- `ROLE_ADMIN` is the authority created by `User.withUsername(...).roles("ADMIN")` in the demo app.
- `ADMIN` is permitted according to the **defined policy**. If the product forbids admins from viewing others' personal data, omit the admin branch; matcher mechanics do not force admins to have access.

This is an `AuthorizationManager` at the **HTTP layer**. For sensitive resources, the data-accessing service should also enforce ownership/tenant controls so other code paths cannot bypass the HTTP layer.

## 5. Complete Example: Java 17 + Spring Boot 3.x + Spring Security 6.x

We build a minimal Spring MVC API:

- `GET /users/{username}/profile` returns a profile-identifying string when permitted.
- Identity comes from HTTP Basic, not from self-asserted URLs/headers.
- User `alice` may view `alice`; user `bob` may view `bob`.
- Other users get 403; anonymous gets 401 via HTTP Basic.
- `ADMIN` may view profiles per the illustrative requirement.
- Other URLs hit `denyAll` to avoid accidentally exposing data when extending controllers.

HTTP Basic is only for easy testing with `curl` and MockMvc; it is not a recommendation to use demo passwords in production. Real APIs require HTTPS and can use sessions, OAuth2 Resource Server, or an evaluated mechanism.

### 5.1. Project Structure

~~~text
path-identity-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (if Gradle Wrapper is generated)
  src/main/java/dev/example/pathidentity/
    PathIdentityApplication.java
    SecurityConfig.java
    ProfileController.java
  src/test/java/dev/example/pathidentity/
    PathIdentityIntegrationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'path-identity-demo'
~~~

File `build.gradle` (example Spring Boot 3.3.5 version with Java 17):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

When using Spring Boot dependency management, compatible Spring Security versions are selected by Spring Boot. Do not force an incompatible `spring-security-web` version manually.

### 5.2. Entry Point

File `src/main/java/dev/example/pathidentity/PathIdentityApplication.java`:

~~~java
package dev.example.pathidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathIdentityApplication.class, args);
    }
}
~~~

### 5.3. SecurityFilterChain and AuthorizationManager

File `src/main/java/dev/example/pathidentity/SecurityConfig.java`:

~~~java
package dev.example.pathidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, HandlerMappingIntrospector introspector)
            throws Exception {

        MvcRequestMatcher profileGet =
                new MvcRequestMatcher.Builder(introspector)
                        .pattern(HttpMethod.GET,
                                "/users/{username}/profile");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(profileGet)
                        .access(ownerOrAdmin())
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    private static AuthorizationManager<RequestAuthorizationContext>
    ownerOrAdmin() {
        return (authentication, context) -> {
            Authentication current = authentication.get();
            String requestedUser = context.getVariables().get("username");

            boolean loggedIn = current != null
                    && current.isAuthenticated()
                    && !(current instanceof AnonymousAuthenticationToken);

            boolean sameUser = loggedIn && requestedUser != null
                    && requestedUser.equals(current.getName());

            boolean hasAdminRole = loggedIn
                    && current.getAuthorities().stream()
                    .anyMatch(authority ->
                            "ROLE_ADMIN".equals(authority.getAuthority()));

            boolean allowed = requestedUser != null
                    && (sameUser || hasAdminRole);

            return new AuthorizationDecision(allowed);
        };
    }
}
~~~

Explanation of the configuration:

1. `MvcRequestMatcher.Builder` uses `HandlerMappingIntrospector` and explicitly declares `HttpMethod.GET` with the `/users/{username}/profile` pattern.
2. When the URL matches, `RequestAuthorizationContext` has key `username`; `ownerOrAdmin` reads that exact variable.
3. `Authentication` is received from Spring Security's `Supplier`, never constructed manually from a query or `X-User` header.
4. Actual login is determined by rejecting `AnonymousAuthenticationToken` in addition to checking `isAuthenticated()`.
5. If the path variable has no value, `allowed=false` for everyone, including admin, preventing a missing variable mapping from being treated as valid permission.
6. `/users/alice/profile` can be viewed by `alice` or `admin`; `bob` is denied before the controller.
7. `anyRequest().denyAll()` is a fail-closed gate for URLs without policies. This differs from `anyRequest().authenticated()`: a logged-in user still cannot view endpoints outside the rule scope.
8. `httpBasic()` enables HTTP Basic authentication for the demo. CSRF protection is not disabled, though since the sample only has GETs, no CSRF token is needed for these requests.
9. Demo accounts reside in `InMemoryUserDetailsManager`; this is not a production user store or password policy solution.

If adding management endpoints in a real app, add dedicated rules in proper order and test each rule. **Never copy `anyRequest().denyAll()` verbatim into an app with other endpoints without designing their policies.**

### 5.4. MVC Controller

File `src/main/java/dev/example/pathidentity/ProfileController.java`:

~~~java
package dev.example.pathidentity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/users/{username}/profile")
    public String profile(@PathVariable("username") String username) {
        return "PROFILE:" + username;
    }
}
~~~

The controller receives `username` from the MVC path; beforehand `SecurityFilterChain` checked the policy. Since the sample code only returns a string, there is no database or real data to leak. In production, the controller/service must also fetch the right record and verify authorization on real data.

Do not equate the controller receiving `@PathVariable` with proof the user was authenticated: the input username is not the request's identity.

### 5.5. Running and Observing with curl

In a project with the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Using another terminal:

~~~bash
curl -i -u alice:alice-demo-pass http://localhost:8080/users/alice/profile
curl -i -u bob:bob-demo-pass http://localhost:8080/users/alice/profile
curl -i -u admin:admin-demo-pass http://localhost:8080/users/alice/profile
curl -i http://localhost:8080/users/alice/profile
~~~

Key application/HTTP expectations:

| Request | Expected |
| --- | --- |
| alice -> /users/alice/profile | 200 and body `PROFILE:alice` |
| bob -> /users/alice/profile | 403 (authenticated, not owner/admin) |
| admin -> /users/alice/profile | 200 and body `PROFILE:alice` |
| anonymous -> /users/alice/profile | 401 Basic challenge |
| alice -> /users/bob/profile | 403 |
| alice -> /users/alice/profile?username=bob | 200, because path variable is `alice` |
| bob + header X-User: alice -> /users/alice/profile | 403 |

The table states **expected outcomes**, not verbatim HTTP headers: `WWW-Authenticate`, `Cache-Control`, and other security headers may appear. Never put demo passwords from code into real environments. With Basic, username/password travel in a Base64-encoded `Authorization` header rather than transport encryption: production **requires HTTPS**.

### 5.6. MockMvc Testing

File `src/test/java/dev/example/pathidentity/PathIdentityIntegrationTest.java`:

~~~java
package dev.example.pathidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathIdentityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerCanReadOwnProfile() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:alice"));
    }

    @Test
    void otherAuthenticatedUserIsForbidden() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadOtherUsersProfile() throws Exception {
        mvc.perform(get("/users/bob/profile")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:bob"));
    }

    @Test
    void anonymousUserReceivesAuthenticationChallenge() throws Exception {
        mvc.perform(get("/users/alice/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotPretendToOwnAnonymousUser() throws Exception {
        mvc.perform(get("/users/anonymousUser/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void queryParameterDoesNotReplacePathVariable() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .queryParam("username", "bob")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:alice"));
    }

    @Test
    void forgedHeaderDoesNotOverrideAuthenticatedIdentity()
            throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .header("X-User", "alice")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unmatchedRouteFailsClosed() throws Exception {
        mvc.perform(get("/users/alice/profile/extra")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isForbidden());
    }
}
~~~

Run in the project directory:

~~~bash
./gradlew test
~~~

The tests use HTTP Basic through `spring-security-test`, meaning they test the application's authentication and authorization pipeline rather than only mocking the `ownerOrAdmin` method directly. Testing owner success alone is not enough: you also need negative tests (another user blocked), anonymous, admin policy, forged query/header, and URLs outside matchers.

Tests are expected to pass with the sample config above. If a request is rejected by Spring Security, the controller does not return a `PROFILE:...` body for that request. When customizing `AuthenticationEntryPoint`/`AccessDeniedHandler` or running behind a proxy, HTTP status codes can change per app contract; update assertions to match the intended policy rather than loosening permissions arbitrarily.

## 6. Shorter Version with WebExpressionAuthorizationManager

Spring Security 6 supports HTTP authorization expressions via `WebExpressionAuthorizationManager`. When a `RequestMatcher` provides path variables, the expression can reference them (for example `#username`).

An equivalent way to express the owner-or-admin policy:

~~~java
MvcRequestMatcher matcher =
        new MvcRequestMatcher.Builder(introspector)
                .pattern(HttpMethod.GET, "/users/{username}/profile");

http.authorizeHttpRequests(auth -> auth
        .requestMatchers(matcher)
        .access(new WebExpressionAuthorizationManager(
                "isAuthenticated() and "
                + "(#username == authentication.name or hasRole('ADMIN'))"))
        .anyRequest().denyAll());
~~~

**This is an alternative snippet** for the rule in `SecurityConfig`, not a second configuration stacked on the same URL in the sample project. The corresponding import is `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager`.

Explanation:

- `#username` represents the URI variable supplied by the matcher, not a query parameter.
- `authentication.name` is the name provided by `Authentication`.
- `isAuthenticated()` under Spring Security's expression evaluation distinguishes anonymous from logged-in users; never write only `#username == authentication.name` because `anonymousUser` could be exploited without that guard.
- `hasRole('ADMIN')` checks `ROLE_ADMIN` under the standard role prefix.
- If the matcher does not extract variables or multiple mappings overlap, test the actual expression.

Pros: short, readable rules for simple conditions. Cons: string expressions can be harder to refactor, debug, and test than strongly typed Java code when policies grow complex. For multi-condition RBAC/ABAC or user/tenant/data lookups, a named `AuthorizationManager` or service-level authorization is usually easier to maintain.

Never concatenate untrusted user data directly into the **expression string** passed to `WebExpressionAuthorizationManager`. The expression is developer-configured policy; request data must enter the evaluation context as framework-handled variables.

## 7. Equivalent Protection at the Method Layer

Another option is checking permissions when invoking controllers or services via method security:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {
}
~~~

On a method with a `username` parameter, you can annotate:

~~~java
@PreAuthorize("isAuthenticated() and "
        + "(#username == authentication.name or hasRole('ADMIN'))")
@GetMapping("/users/{username}/profile")
public String profile(@PathVariable("username") String username) {
    return "PROFILE:" + username;
}
~~~

This is an **illustrative snippet** inside a controller with imports, and only works when you enable `@EnableMethodSecurity`, use `@PreAuthorize` with method security configured, proxies intercept the right bean/method, and parameter names are resolved properly (via `@P` or compiled parameter names). If placing annotations on interfaces or making internal self-calls within the same bean, understand proxy/AOP limitations.

Never blindly replace HTTP authorization and method security with two conflicting rules without understanding ordering. Usually an HTTP layer blocks early, while service-level protection secures data when methods are invoked from multiple paths.

With method-level SpEL, `#username` comes from the **Java method parameter**, not automatically from `RequestAuthorizationContext`. This is a key difference from `#username` in `WebExpressionAuthorizationManager` when an HTTP matcher extracted the URL variable.

### When to Prefer Service-Level Authorization?

Suppose `profile` is called from an HTTP API, a scheduled job, a message listener, and another service. Permissions on **data records** should not live solely in the HTTP `SecurityFilterChain`, because internal call paths bypass URLs.

The service should accept a trusted user ID and loaded resource, then check owner/tenant/permissions in the same transaction or right before querying data. You can use `@PreAuthorize`, method `AuthorizationManager`s, `PermissionEvaluator`, or an explicit policy service depending on complexity.

## 8. Preventing IDOR/BOLA When Paths Contain Record IDs

This is a key distinction to avoid creating **Insecure Direct Object Reference (IDOR)** or **Broken Object Level Authorization (BOLA)** vulnerabilities.

If the URL is:

~~~text
GET /documents/8ac4a1d0-59de-4803-b8f6-1ea6101eeabc
~~~

The path variable is `documentId`, **not `username`**. You cannot compare `documentId` with `Authentication.getName()` and treat it as a valid permission check.

You need to:

1. Authenticate the caller's identity from `SecurityContext`.
2. Fetch the document record by `documentId` via the repository.
3. Verify the record belongs to the same `ownerId`/`tenantId` or the caller holds specific read permission.
4. Only after satisfying policy return the content.
5. If intentionally hiding document existence, you may return 404 to unauthorized users instead of 403, consistently without leaking via timing/error messages.

Service-layer pseudocode example (repository/domain classes here are illustrative, not standalone compilable Java files):

~~~java
public DocumentDto getDocument(UUID documentId, String callerId) {
    Document doc = documentRepository.findById(documentId)
            .orElseThrow(NotFoundException::new);

    boolean owner = doc.getOwnerId().equals(callerId);
    boolean canRead = owner || policy.canReadDocument(callerId, doc);

    if (!canRead) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(doc);
}
~~~

Database queries can attach the owner condition in SQL to avoid returning the wrong user's data:

~~~sql
SELECT id, owner_id, title
FROM documents
WHERE id = :document_id
  AND owner_id = :authenticated_user_id;
~~~

`:authenticated_user_id` must come from the verified identity, **not** from a client-supplied query parameter or path variable. In multi-tenant systems, both tenant ID and sharing/internal role permissions are usually needed; checking user ID alone may not suffice.

A good path-matching rule still cannot replace access control on actual data. Conversely, a service that checks permissions properly should still have HTTP rules to block early, reduce wasted processing, and provide appropriate responses.

### Guarding Against "Confused Deputy" and Forged Headers

If the app sits behind an API gateway, sometimes the gateway forwards user info in headers. Trust a header only when protected by an internal authentication protocol, controlled by the gateway, impossible for public clients to overwrite, and explicitly verified in Spring Security config. Never add logic like self-asserted `X-User` header = `{username}` to grant access, even if the app "normally runs behind a proxy".

## 9. Rule Ordering and Path Pattern Breadth

In `authorizeHttpRequests`, rule order matters: a request is generally decided by the first matching rule of the corresponding `AuthorizationManager`.

Wrong:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/users/**").permitAll()
        .requestMatchers("/users/{username}/profile")
            .access(ownerOrAdmin())
        .anyRequest().denyAll())
~~~

The broad `/users/**` `permitAll` rule comes first and allows GET profile; the `ownerOrAdmin` rule below may never be evaluated. You cannot fix this by assuming "the last strictest rule wins".

Right: place specialized matchers first, check methods, and handle other paths as needed:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(profileGet).access(ownerOrAdmin())
        .anyRequest().denyAll())
~~~

If the API adds `/users/public-info`, declare a dedicated rule for it with a specific scope and method. Never carelessly drop `anyRequest().authenticated()` into an app with per-user data because it only requires login, **without** checking ownership.

### HttpMethod Matters

`GET /users/alice/profile` and `DELETE /users/alice/profile` do not carry the same impact. A matcher restricted to GET grants reading per the rule; DELETE does not automatically inherit access without another rule. In the example, all other methods hit `denyAll`.

If you add PUT/DELETE for state-changing operations:

- Define separate edit/delete permissions; usually stricter than read permissions.
- For browsers using cookie sessions, keep proper CSRF protection on unsafe methods; `permitAll` or owner equality does not turn off `CsrfFilter`.
- For APIs using bearer tokens in the `Authorization` header without relying on browser cookies, CSRF may be configured differently per threat model; never disable it globally without evaluation.
- Test both other users and anonymous users, along with mismatched methods/URLs.

## 10. MvcRequestMatcher, Path Normalization, and URL Encoding

Matchers and controllers must interpret URLs consistently. Situations to test:

| Scenario | Potential Issue |
| --- | --- |
| /users/alice/profile | Standard case, username is `alice` |
| /users/Alice/profile | Is comparison case-sensitive? Does the user store normalize? |
| /users/alice/profile/ | Does trailing slash match depending on MVC/version/config? |
| /users/alice%20smith/profile | Is percent-encoding/space decoded by MVC as expected? |
| /users/alice%2Fadmin/profile | Encoded slash may be rejected by container/proxy or decoded differently |
| /users/../bob/profile | Normalization/path traversal is typically blocked or normalized; ensure matcher/controller agree |
| /users/alice/profile?username=bob | Path variable stays `alice`; query is separate |
| /users/alice/profile;v=1 | Matrix parameters and semicolon handling depend on MVC/container/firewall config |

Spring Security includes `StrictHttpFirewall` in standard configurations, yet you must not skip testing by assuming "all weird URLs are already blocked". Proxies, servlet mappings, `securityMatcher`, and application routing can change the path seen at each layer.

**Never use `string.startsWith("/users/" + authentication.getName())` to grant access**, because `/users/alice-bad/profile` starts with `/users/alice` even though it belongs to another user. Never manually double-decode URLs or slice strings with `split("/")` to get the username when `RequestMatcher`/URI-template variables are available.

### Identity Normalization

Suppose usernames could be `"Alice"`, `"alice"`, or equivalent Unicode characters. `equals()` in the demo is an **exact string comparison**. If the identity provider/DB has canonicalization rules, store and compare a **stable internal ID** or canonicalized username from a trusted source, rather than calling `toLowerCase()` unconditionally on client data.

Never arbitrarily merge usernames via Unicode case folding if the user store does not enforce the same rule; that can grant access to the wrong owner.

## 11. Multiple SecurityFilterChains and Rule Scope

If the application has multiple chains:

~~~text
@Order(1): securityMatcher("/api/**")
           -> API bearer/basic policies

@Order(2): fallback web requests
           -> form login + web policies
~~~

`FilterChainProxy` selects the first chain matching the request. If `/users/{username}/profile` is not in the chain you expect, the `ownerOrAdmin` `AuthorizationManager` may not run.

For example:

- You configure the owner rule in a chain matching only `/api/**`, while the controller actually lives at `/users/**`: requests never enter that chain.
- A general catch-all chain precedes a specialized chain: later rules are shadowed.
- The API has its own servlet mapping; `MvcRequestMatcher` uses the wrong `servletPath`, so URI variables are not extracted as expected.
- One chain uses `STATELESS`, while a test sends a form-login cookie from another chain; `Authentication` in the active chain may not be what you assume.

Always trace **request -> `SecurityFilterChain` -> `RequestMatcher` -> `Authentication` -> `AuthorizationDecision` -> controller/service**, and write integration tests against real endpoints in the deployed app.

## 12. Common Mistakes

### 12.1. "Any logged-in user can view another user's profile"

Cause: using only `.authenticated()` on `/users/**` without an owner condition. Fix: use a URI-variable access policy or service ownership check. Add a test where `bob` accessing `alice`'s profile must return 403.

### 12.2. "Used a path variable yet still vulnerable to IDOR"

Cause: comparing the wrong target. If the path holds `documentId`, you cannot compare `documentId` with `username`; query the database for the true `ownerId`/`tenantId` and match against the verified caller ID.

### 12.3. "Anonymous could view /users/anonymousUser/profile"

Cause: `AnonymousAuthenticationToken` has name `anonymousUser` and can have `isAuthenticated()` true. Fix: check authenticated per Spring Security semantics and exclude `AnonymousAuthenticationToken`, or use an appropriate `isAuthenticated()` expression.

### 12.4. "context.getVariables().get('username') is null"

Cause: matcher does not capture variables, variable name typo, another path rule matched earlier, `securityMatcher` did not apply, or servlet path mismatch. Fix: inspect the actual matcher used, pattern, and variables; missing-variable policies must fail closed.

### 12.5. "Controller has @PathVariable yet Spring Security does not know that variable"

Controller mapping and security matching are two separate layers. `@PathVariable` does not automatically share variables with every custom `RequestMatcher`. Use a matcher supporting URI template variables and `RequestAuthorizationContext.getVariables()`, or method-level authorization taking explicit parameters.

### 12.6. "User bob forged X-User: alice and gained access"

Cause: app trusted an unverified header. Fix: `Authentication` must come from a trusted security mechanism; trust proxy headers only when the gateway/signed headers and network boundary are genuinely secured.

### 12.7. "admin is still denied"

Check actual authorities: `.roles("ADMIN")` generates `ROLE_ADMIN`; if the system uses `.authorities("ADMIN")` without prefix, align the policy. Never remove checks just to make tests pass.

### 12.8. "Path /users/alice/profile?username=bob was treated as bob"

You read `request.getParameter("username")` instead of `variables.get("username")`, or the controller used query instead of path. Distinguish `@PathVariable` from `@RequestParam` and test requests containing both.

### 12.9. "Owner rule has no effect because permitAll comes first"

A broad matcher like `/users/**.permitAll()` before the owner rule can immediately permit the request. Audit order and scope of every matcher, and use `denyAll` for undefined paths.

### 12.10. "Switched to JWT and Authentication.getName() is no longer the username"

The JWT principal name may come from `sub` or a configured claim; the display username does not necessarily equal `sub`. Move the policy to a stable ID or trusted mapping; never ask the client to send a username claim as proof.

### 12.11. "@WithMockUser tests pass yet production fails"

Mock `Authentication` tests have test-defined `getName` and roles, while the production authentication principal differs. Add integration tests through the real mechanism (Basic, bearer, session), verifying principal name semantics and role mapping.

### 12.12. "Only protected URLs, yet the service is still called by jobs/message consumers"

HTTP authorization does not run on direct non-MVC invocations. Critical resources need service-level authorization or a business policy system, along with tests for those entry points.

### 12.13. "Comparing raw username strings across tenants"

The same username can exist across multiple tenants. Check both tenant ID and user ID; never use username as a global owner key in multi-tenant systems.

### 12.14. "Not receiving the expected AuthorizationDecision"

Inspect method rules, selected `RequestMatcher` and `SecurityFilterChain`, auth state, actually captured variables, and role prefixes. When debugging, never print raw `Authorization` headers, session cookies, or access tokens to public logs.

## 13. Production Design and Testing Checklist

1. **Identify the subject:** Is `Authentication.getName()` a username, subject, or ID? Is it canonicalized per policy?
2. **Identify the resource:** Is the URI variable a username, `userId`, or `resourceId`? If it is a record ID, look up owner/tenant in the data store.
3. **Choose a `RequestMatcher` aligned with MVC/Servlet mapping** and `HttpMethod`; verify variables are captured properly.
4. **Never trust client-supplied path/query/headers** as the request's identity; use only `Authentication` from a trusted verification mechanism.
5. **Explicitly check for anonymous**, including paths with value `anonymousUser`.
6. **Fail-closed policy:** missing path variables, matcher errors, or undefined URLs must deny access.
7. **Order rules properly:** specific rules before broad rules; never let broad `permitAll` or `authenticated` bypass ownership.
8. **Authorize real roles:** align `ROLE_ADMIN`, `hasRole`/`hasAuthority`, and data privacy policies.
9. **Separate HTTP permissions from data ownership:** every sensitive service access path still needs appropriate protection.
10. **Test both positive and negative cases:** owner, other user, admin, anonymous, forged header, query differing from path, and unmatched URLs.
11. **Test edge-case URLs:** encoding, trailing slash, casing, Unicode, matrix parameters, `servletPath`, and reverse proxies.
12. **Multiple security chains:** ensure endpoints land in the intended chain; test safe and unsafe methods separately.
13. **When using JWT/OIDC**, verify subject/claim mapping from the authentication provider and tenant semantics.
14. **Never leak sensitive data:** log authorization decisions with a correlation ID, never raw credentials/cookies/tokens.
15. **Track errors and changes:** after upgrading Spring Boot/Spring Security, re-test matcher/path-mapping behavior on real endpoints.

## 14. Self-Practice Questions

**Question 1.** `GET /users/bob/profile` is called by `alice`; can you take `bob` from `@PathVariable` and conclude the request was sent by `bob`?

**Answer:** No. Path variables are chosen by the client. `Authentication` from Spring Security represents the caller's identity. To enforce ownership, compare `bob` against the authenticated identity.

**Question 2.** Where does `RequestAuthorizationContext.getVariables().get("username")` get `username` from?

**Answer:** From the corresponding `RequestMatcher` matching the URI template `{username}`, not from an `X-User` header or a query parameter of the same name.

**Question 3.** Why can using only `current.isAuthenticated()` be dangerous in a custom policy?

**Answer:** `AnonymousAuthenticationToken` can report `true`, even though the caller is actually anonymous. You must exclude anonymous or use an appropriate authenticated check.

**Question 4.** What is wrong with `.requestMatchers("/users/**").permitAll()` placed before an owner rule?

**Answer:** The broad rule can match first, permitting the request without ever evaluating the owner rule behind it.

**Question 5.** If `/documents/{id}` contains a document ID, can you compare `id` with `Authentication.name`?

**Answer:** No. You must load the document data and check `ownerId`/`tenantId` and permissions against the verified caller ID.

**Question 6.** For `GET /users/alice/profile?username=bob`, what value does the matcher capture?

**Answer:** With pattern `/users/{username}/profile`, variable `username` is `alice`; query `username=bob` is separate data.

**Question 7.** What should you do if `ADMIN` needs to view every user's profile?

**Answer:** Add an explicitly defined role/authority branch, verify the caller is authenticated and the URL variable is valid, and test admin, non-admin, and anonymous cases.

**Question 8.** If a service is called from a scheduled job without passing through the HTTP `SecurityFilterChain`, does the HTTP owner rule run?

**Answer:** No. Sensitive data requires a service/domain-layer policy or an authorization mechanism suited to that entry point.

**Question 9.** When switching from HTTP Basic to OIDC, is `getName()` guaranteed to remain the username?

**Answer:** No. It may be `subject` or another claim; determine principal name semantics before comparing against the URL.

**Question 10.** In an app with multiple `SecurityFilterChain`s, why might the owner `AuthorizationManager` fail to run?

**Answer:** The request may be routed into another chain by `securityMatcher`/`@Order`, or an earlier rule in the chain matched first. Check chain/matcher/method/variables with integration tests.

## Summary

**Extracting path variables is reading routing data, not verifying identity.** Spring Security Servlet lets `RequestMatcher` pass URI template variables into `RequestAuthorizationContext`, so `AuthorizationManager` can compare **the URL value** against the **authenticated `Authentication`** and roles such as `ROLE_ADMIN`.

The practical formula of the example is: **right HTTP method + right route + genuinely authenticated caller + valid username variable + (caller is owner or admin)**. If unsatisfied, deny before the controller; undefined URLs should fail closed.

In real applications, do not stop at comparing username strings. Use **stable user IDs/tenant IDs**, verify ownership of the **database record**, test requests forged by other users, and keep policies consistent across HTTP, services, and non-web flows.