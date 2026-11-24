# Reading the Current Identity via API Without Depending Directly on the Session

> **Topic:** Security context in Spring Security on the **Servlet stack**. Examples use Spring Security 6, Spring Boot 3, Jakarta Servlet, and Java 17+. The goal is to read the identity that Spring Security **has authenticated for the current request**, instead of manually looking up users in `HttpSession`, decoding cookies yourself, or trusting client-declared data.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain the path from an authentication mechanism to `Authentication`, `SecurityContext`, and `SecurityContextHolder`.
- Choose the right API to retrieve the username, principal, authorities, or a normalized identity view in a controller or service.
- Use `Principal`, `Authentication`, `@AuthenticationPrincipal`, or `@CurrentSecurityContext` without forcing business code to know whether the info is stored in an HTTP session, request attribute, or re-verified from a token.
- Handle unauthenticated users, anonymous principals, multiple principal types, and asynchronous processing safely.
- Distinguish **reading identity**, **authentication**, and **authorization**; avoid returning credentials/tokens and avoid taking identity from arbitrary client input.

## 2. SecurityContext Is the Request's Identity Access Point

Spring Security does not require controllers to manually read `JSESSIONID` or call `session.getAttribute("user")` to know who is requesting a resource. Security filters handle loading or creating the appropriate `Authentication` and expose it through `SecurityContext`.

```text
HTTP request
    |
    v
Spring Security filter chain
    |
    +-- context/repository mechanism for the current request
    |
    +-- if Basic/Bearer/form login is present:
    |      authentication filter processes the credential/token
    |      and creates Authentication on success
    |
    +-- if no suitable Authentication exists yet:
    |      may create AnonymousAuthenticationToken
    |
    +-- AuthorizationFilter decides access permission
    |
    v
Controller / Service
    |
    +-- Principal / Authentication method argument
    +-- @AuthenticationPrincipal / @CurrentSecurityContext
    +-- SecurityContextHolder.getContext().getAuthentication()
```

Key objects:

| Object | Meaning | Things to remember |
| --- | --- | --- |
| `Authentication` | Represents the identity and verification evidence/state processed during the request. | Provides `getName()`, `getPrincipal()`, `getAuthorities()`, `isAuthenticated()`; may be anonymous. |
| `SecurityContext` | Container holding a current `Authentication`. | Not an HTTP session object; it is the security context interface. |
| `SecurityContextHolder` | Access point to the context bound by Spring Security to the current execution. | Defaults to a thread-based strategy; requires care with async/thread reuse. |
| `SecurityContextRepository` | Source/destination for storing the context when the mechanism requires it. | May use HTTP session, request attributes, or another configuration. |
| `Principal` | Standard Java interface with `getName()`. | Suitable when only the authenticated name is needed, independent of specific principal types. |

Distinguish three concepts:

**Authentication** verifies who is sending the request; **identity lookup** reads the authentication result already stored in the context; **authorization** decides what that identity is allowed to do. Reading a username via `Authentication.getName()` **does not automatically check** access permissions for a resource.

### 2.1. Why Not Access the Session Directly?

An example coupling business logic to the session:

```java
// Approach that easily creates coupling to where identity is stored:
HttpSession session = request.getSession(false);
String username = session == null
        ? null
        : (String) session.getAttribute("username");
```

This is an **illustrative snippet**, not how to authenticate a user. The code relies on an arbitrary attribute name, has no guarantee that Spring Security populated it, does not work equivalently with stateless Basic/Bearer auth, and risks confusing application session data with an **authenticated identity**.

Reading via Spring Security:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth == null ? null : auth.getName();
```

Controllers/services now care about **"who is authenticated for this request?"**; deciding whether the context comes from session, Basic, Bearer, OAuth2, or another mechanism lives in security filter configuration. Code must still handle anonymous callers appropriately; checking `auth != null` is not enough to conclude a user is logged in.

## 3. Four Common Ways to Retrieve Identity

### 3.1. `Principal` as a Controller Parameter

Spring MVC can pass the request's principal to a handler:

```java
@GetMapping("/me/name")
public String myName(Principal principal) {
    return principal.getName();
}
```

This is a **method snippet** inside a `@RestController` importing `java.security.Principal`. The handler should be protected by `authenticated()` if you want to guarantee a logged-in principal. On public endpoints, do not assume `principal` is always non-null.

Pros: code only cares about the name. It also continues to work when the login mechanism changes as long as an appropriate principal exists.

Limitations: does not directly provide authorities, token type, or specialized principal fields. On the Servlet stack, `HttpServletRequest#getUserPrincipal()` is a related mechanism; Spring Security integrates the request principal with the context processed by its filters.

### 3.2. `Authentication` as a Controller Parameter

When both name and authorities are needed:

```java
@GetMapping("/me/roles")
public List<String> myRoles(Authentication authentication) {
    return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
}
```

This method snippet requires importing `org.springframework.security.core.Authentication`, `org.springframework.security.core.GrantedAuthority`, and `java.util.List`. `Authentication` is a subtype of `Principal`, so Spring MVC can supply it via principal resolution. If you need to specify explicitly that the value must come **from SecurityContext**, use `@CurrentSecurityContext(expression = "authentication")` as shown below.

`getName()` returns the display/identifier name per the `Authentication` type's contract; it is not automatically a database primary key. `getAuthorities()` represents security-layer authorities, not a list of features a user can access without further resource-policy checks.

### 3.3. `@AuthenticationPrincipal` to Retrieve a Normalized Principal

When you know the application uses a specific principal type:

```java
@GetMapping("/me/details")
public String details(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

This example fits authentication mechanisms where `Authentication.getPrincipal()` returns `UserDetails`, such as the HTTP Basic setup using `DaoAuthenticationProvider` and `UserDetailsService` in the hands-on example below.

Pros: the controller does not need to accept the entire `Authentication` object. Limitation: the principal is **not necessarily** `UserDetails` in every mechanism. Bearer JWT may use `Jwt`, OAuth2/OIDC may use `OAuth2User` or `OidcUser`, and custom filters may create custom principals. Choosing the wrong type can inject `null` or raise a type-check error if enabled; know which chain is in use.

You can access a principal property using an expression, provided the principal type exposes it:

```java
@GetMapping("/me/details-name")
public String detailsName(
        @AuthenticationPrincipal(expression = "username")
        String username) {
    return username;
}
```

This fits `UserDetails`; do not copy the expression verbatim to `Jwt` or `OidcUser` without verifying their data structures.

### 3.4. `@CurrentSecurityContext` to Retrieve the Context or Authentication

If a handler wants to declare the dependency explicitly:

```java
@GetMapping("/me/context")
public String fromContext(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
```

Import `org.springframework.security.core.annotation.CurrentSecurityContext`. This accurately expresses reading the authentication result from `SecurityContext`. As with the previous approaches, call `getName()` directly only when the route guarantees a suitable principal or after checking for null/anonymous.

### 3.5. Which API to Choose?

| Need | Preferred API | Scope |
| --- | --- | --- |
| Need only username in a controller | `Principal` or `Authentication#getName()` | Protected HTTP handler. |
| Need roles/authorities in a controller | `Authentication` / `@CurrentSecurityContext` | No manual session querying required. |
| Need `UserDetails`-specific properties | `@AuthenticationPrincipal UserDetails` | Only when the principal is genuinely `UserDetails`. |
| Need `Jwt` or `OidcUser` | `@AuthenticationPrincipal` with exact type | Only when the security chain uses that principal type. |
| Service code independent of Spring MVC | `SecurityContextHolder` (or custom abstraction) | Must be in the right execution context. |
| Code preferring standard Servlet API | `HttpServletRequest#getUserPrincipal()` | Depends on Servlet request, not directly on HTTP session. |

There is no need to write a custom filter that reads `HttpSession` and attaches a username request attribute when the security chain already supplies the principal. If multiple services need identity, an interface such as `CurrentIdentity` can encapsulate reading the holder so anonymous policy and user ID mapping live in one place.

## 4. Identifying Anonymous and Unauthenticated States

A common mistake is:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
boolean loggedIn = auth != null && auth.isAuthenticated();
```

This condition **can evaluate an anonymous caller as authenticated** because `AnonymousAuthenticationToken` can return `isAuthenticated() == true` per its internal token semantics. Therefore, never use that expression as a security boundary.

In business code requiring an optional identity, you can exclude anonymous callers:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

if (auth == null
        || !auth.isAuthenticated()
        || auth instanceof AnonymousAuthenticationToken) {
    return Optional.empty();
}
return Optional.of(auth.getName());
```

This is a **method body** importing `Authentication`, `AnonymousAuthenticationToken`, `SecurityContextHolder`, and `java.util.Optional`. The runnable section below implements this logic in full inside a service.

To **protect endpoints**, configure `.authenticated()` or rules like `hasRole`, `hasAuthority`, and resource-level policies rather than inventing `getName()` checks in controllers. The anonymous filter, remember-me, session state, authority mapping, and authentication trust resolver can all influence how Spring Security evaluates the user.

A `permitAll()` endpoint can be accessed without a real principal, and Spring Security's deferred context loading can surface null/anonymous depending on where code runs. For predictable responses, **represent guest state explicitly** instead of casting or throwing a `NullPointerException`.

## 5. Session Independence Does Not Mean No Context

### 5.1. Session-Based Login

```text
Request A: user logs in
  -> authentication filter creates Authentication
  -> SecurityContextRepository saves if configuration requires
  -> browser receives/holds session cookie

Request B: browser resends cookie
  -> security filter provides SecurityContext from repository
  -> controller reads Authentication through the same APIs
```

The controller does not need to know where the container stores the context. In Spring Security 6, `SecurityContextHolderFilter` can prepare a deferred context, and saving context changes generally must be performed explicitly by the appropriate authentication mechanism—unlike older setups using `SecurityContextPersistenceFilter`.

### 5.2. Stateless HTTP Basic

```text
GET /api/me
Authorization: Basic <base64(username:password)>

BasicAuthenticationFilter authenticates credentials for the request
  -> SecurityContextHolder holds Authentication
  -> AuthorizationFilter checks access
  -> controller still uses @CurrentSecurityContext / Principal
```

With `SessionCreationPolicy.STATELESS`, the application does not use an HTTP session to load/save authentication across requests. On the next request, the client must prove identity again using the required mechanism, such as the Basic header. **HTTPS is mandatory in real environments** because Base64 is not password encryption. Basic is used here purely for a self-contained, easily testable example.

### 5.3. Stateless Bearer Token

```text
GET /api/me
Authorization: Bearer <access-token>

BearerTokenAuthenticationFilter
  -> verifies token via resource server mechanism
  -> creates Authentication per configuration
  -> places into current SecurityContext
  -> controller reads Authentication / principal
```

Across all three flows, **reading identity does not require the controller to access the session directly**. The differences lie in when the context is supplied, how credentials are verified, and whether state is persisted between requests.

Do not infer from `SessionCreationPolicy.STATELESS` that `SecurityContextHolder` will always be empty: the holder still holds the authentication for the **current request**. Likewise, do not infer from seeing a cookie that a user is authenticated; the cookie may be expired, invalid, or unused by the selected chain.

## 6. Runnable Example: Spring Boot 3 + Java 17, Stateless HTTP Basic

This application defines one principal `alice` with role `READER`, one endpoint open to guests, and four endpoints restricted to logged-in users. It demonstrates `Principal`, `Authentication` via `@CurrentSecurityContext`, `@AuthenticationPrincipal UserDetails`, and a service using `SecurityContextHolder` side by side.

**Important:** the example never calls `request.getSession()` or uses `HttpSession`; the stateless policy forces the client to send credentials on every request. Using only HTTP GET leaves default CSRF enabled without interfering with this identity lesson.

### 6.1. Structure

```text
current-identity/
├── pom.xml
└── src/
    ├── main/java/example/currentidentity/
    │   ├── CurrentIdentityApplication.java
    │   ├── CurrentIdentityService.java
    │   └── IdentityController.java
    └── test/java/example/currentidentity/
        └── CurrentIdentityApplicationTests.java
```

**`pom.xml`**:

```xml
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

    <groupId>example</groupId>
    <artifactId>current-identity</artifactId>
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
```

**`src/main/java/example/currentidentity/CurrentIdentityApplication.java`**:

```java
package example.currentidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class CurrentIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(CurrentIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/optional").permitAll()
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // {noop} ONLY so this hands-on exercise can run immediately.
        // Production must use a proper PasswordEncoder and secret storage.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo-pass")
                    .roles("READER")
                    .build());
    }
}
```

Configuration explanation:

- `/api/optional` permits anonymous callers; all other `/api/**` URLs require authentication; all other URLs are denied.
- `httpBasic` enables Basic authentication, and `STATELESS` prevents request auth from depending on an HTTP session.
- `formLogin` is omitted so unauthenticated API behavior is clearly observed via HTTP 401, and CSRF is left enabled because the demo uses only GET.
- The account uses `{noop}` and a sample password for learning; **do not carry this account into real environments**.

**`src/main/java/example/currentidentity/CurrentIdentityService.java`**:

```java
package example.currentidentity;

import java.util.Optional;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentIdentityService {
    public Optional<String> currentUsername() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.of(auth.getName());
    }
}
```

This service has no dependency on Spring MVC and does not know whether the user came from a session or a token. For APIs using custom token types or different anonymous policies, you can implement checks via `AuthenticationTrustResolver` and identity normalization rules here.

**`src/main/java/example/currentidentity/IdentityController.java`**:

```java
package example.currentidentity;

import java.security.Principal;
import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    private final CurrentIdentityService currentIdentityService;

    public IdentityController(CurrentIdentityService currentIdentityService) {
        this.currentIdentityService = currentIdentityService;
    }

    public record IdentityView(String username, List<String> authorities) {
    }

    @GetMapping("/api/optional")
    public String optional() {
        return currentIdentityService.currentUsername().orElse("guest");
    }

    @GetMapping("/api/me")
    public IdentityView me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new IdentityView(authentication.getName(), authorities);
    }

    @GetMapping("/api/principal")
    public String byPrincipal(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/details")
    public String byUserDetails(@AuthenticationPrincipal UserDetails user) {
        return user.getUsername();
    }

    @GetMapping("/api/service")
    public String byService() {
        return currentIdentityService.currentUsername()
                .orElseThrow();
    }
}
```

Explanation:

- `/api/optional` demonstrates an API accepting both guests and users. Do not use `auth != null` to determine login.
- `/api/me` intentionally creates a **small DTO** containing only `username` and `authorities`. Never return the raw `Authentication` because it may hold credentials/details/tokens or information that should not be exposed.
- `/api/principal` uses standard `Principal` and reads only `getName()`.
- `/api/details` demonstrates `@AuthenticationPrincipal` with `UserDetails` in the **example's Basic configuration**. Do not assume principals from JWT/OIDC are `UserDetails`.
- `/api/service` demonstrates the service layer reading identity without `HttpServletRequest`, `HttpSession`, or the controller passing the username manually. The route already requires authentication; `orElseThrow()` is merely a secondary safeguard, not an authorization policy.

### 6.2. Testing Through the Real BasicAuthenticationFilter

Rather than merely injecting a mock principal with `with(user(...))`, the test example uses `httpBasic(...)` from `spring-security-test` so requests carry a real Basic header in MockMvc. Credentials are processed by the security filter; the tests highlight the difference between **a request without credentials**, **wrong password**, and **right password**.

**`src/test/java/example/currentidentity/CurrentIdentityApplicationTests.java`**:

```java
package example.currentidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentIdentityApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void optionalEndpointShowsGuest() throws Exception {
        mvc.perform(get("/api/optional"))
                .andExpect(status().isOk())
                .andExpect(content().string("guest"));
    }

    @Test
    void optionalEndpointShowsUserAfterBasicAuthentication()
            throws Exception {
        mvc.perform(get("/api/optional")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void privateEndpointWithoutCredentialsReturns401()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationIsAvailableInSecurityContext()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_READER"));
    }

    @Test
    void principalArgumentReadsCurrentIdentity()
            throws Exception {
        mvc.perform(get("/api/principal")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void authenticationPrincipalReadsUserDetails()
            throws Exception {
        mvc.perform(get("/api/details")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void serviceReadsHolderWithoutHttpSession()
            throws Exception {
        mvc.perform(get("/api/service")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
```

Run with JDK 17+ and Maven in the `current-identity` directory:

```bash
mvn test
mvn spring-boot:run
```

These are **eight tests**, with expected HTTP outcomes under the sample configuration:

| Test request | Expected result |
| --- | --- |
| GET `/api/optional` without Basic header | 200, body `guest` |
| GET `/api/optional` with valid Basic | 200, body `alice` |
| GET `/api/me` without Basic | 401 |
| GET `/api/me` with wrong Basic password | 401 |
| GET `/api/me` with valid Basic | 200, JSON with `"username":"alice"` and `"authorities":["ROLE_READER"]` |
| GET `/api/principal` with valid Basic | 200, body `alice` |
| GET `/api/details` with valid Basic | 200, body `alice` |
| GET `/api/service` with valid Basic | 200, body `alice` |

You can test independently once the application is running:

```bash
curl -i http://localhost:8080/api/optional
curl -i http://localhost:8080/api/me
curl -i --user alice:demo-pass http://localhost:8080/api/me
curl -i --user alice:demo-pass http://localhost:8080/api/principal
curl -i --user alice:demo-pass http://localhost:8080/api/details
curl -i --user alice:demo-pass http://localhost:8080/api/service
```

`curl --user` generates the corresponding Basic header. The example data is designed for **localhost**; use TLS/HTTPS in real environments. Request ordering in tests is not guaranteed; do not rely on them sharing a session, and authenticated endpoints must continue requiring credentials on every request per the stateless configuration.

### 6.3. Why Does the Example Still Have a SecurityContext Without a Session?

When the Basic filter verifies valid credentials, it creates an `Authentication` for the current request. Readers in the controller or service access that same identity. When the request finishes, the context bound to the current execution is cleared per the filter lifecycle; the next request must resend Basic credentials. `SecurityContextHolder` is not "turned off" by `STATELESS`.

If switching to form login/session in another application, `byPrincipal` or `currentUsername()` can remain unchanged; what changes is the authentication/context-persistence configuration, not calling `session.getAttribute(...)` inside services.

## 7. From Username to Business Identifier: Separating Two Layers

The name from `authentication.getName()` is not automatically an **immutable database ID**. With HTTP Basic in the demo, it is `alice`; with JWT, the name may come from `sub` or a configured claim; with OAuth2/OIDC, the name may be a value returned by the identity provider.

When a system has internal user IDs, a safer approach is one of two options:

1. Create a verified custom principal, e.g. `AppPrincipal(userId, username, tenantId)`, constructed in the authentication layer; the business layer only reads fields with a clear contract.
2. Use the verified name/subject as a lookup key mapping from the identity provider to an internal account in a service; verify tenant, account status, and resource access permissions.

**Never accept `userId` from a query parameter/body and treat it as the current user.** For example, `GET /api/orders?userId=42` is merely client-supplied input, not proof that the caller is user 42. For an operation like "view my own orders", the current user ID must come from the trusted authentication context or identity mapping layer; object-level authorization must still check ownership, tenant, and business policy.

A response DTO should output only necessary fields. Do not directly serialize `Authentication`, custom `Principal` objects, or tokens, as they may contain credentials, provider attributes, internal claims, session details, or private data.

## 8. Principals Differ by Authentication Mechanism

### 8.1. `UserDetails`

In applications using `DaoAuthenticationProvider`, `Authentication.getPrincipal()` is typically `UserDetails`. You can read the username, account flags, and custom properties. Even so, `UserDetails` is not the universal interface for every authentication type.

### 8.2. JWT Resource Server

In Spring Security Resource Server using JWT, the principal can be `org.springframework.security.oauth2.jwt.Jwt`, and the authentication is typically `JwtAuthenticationToken`. In a controller of an **application configured as a Resource Server**:

```java
@GetMapping("/api/jwt-subject")
public String jwtSubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
```

This is only an **illustrative method**; it requires OAuth2 Resource Server dependencies/configuration and an appropriate JWT decoder, and **is not a runnable endpoint in the HTTP Basic project from section 6**. `getSubject()` returns the `sub` claim, which does not necessarily equal an internal account ID. `Authentication.getName()` can also be configured to read from a different claim.

If you want to avoid all direct coupling to token formats, use `Authentication.getName()` only after the application normalizes what that name means; subject → user ID mapping logic should live in a dedicated service.

### 8.3. OAuth2/OIDC Login

With OAuth2/OIDC login, the principal can be `OAuth2User` or `OidcUser`. Claims/attributes must be read per the provider's contract and verified mappings; email can change and should not be assumed as an immutable primary key. User-facing controllers can use a `CurrentIdentity` abstraction so both session login and Bearer APIs query "the current internal user" uniformly.

### 8.4. Anonymous and Remember-Me

Anonymous authentication can be placed into the context by Spring Security so components process requests uniformly. Remember-me can also restore an identity with a different level of assurance than direct login. If an operation requires **fresh login / full authentication**, never inspect `Authentication.getName()` alone; use policies like `fullyAuthenticated()` and appropriate additional authentication requirements.

## 9. Threads, Async, and Safe Scope of SecurityContextHolder

On the Servlet stack, `SecurityContextHolder` defaults to `ThreadLocal`. When code runs directly within the request/filter chain, reading the holder makes sense. However, execution can switch threads when using `@Async`, `CompletableFuture`, thread pools, or Servlet async processing.

```java
// Illustrates the issue only; NO guarantee of automatic context propagation:
CompletableFuture.supplyAsync(() ->
        SecurityContextHolder.getContext().getAuthentication());
```

In a thread running from an executor, the result can be `null` or the wrong context if threads/contexts are managed improperly. Do not fix this by setting `MODE_INHERITABLETHREADLOCAL` globally and assuming it is safe for all thread pools. Spring Security provides wrappers such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, and `DelegatingSecurityContextExecutor` to propagate/wrap contexts according to policy; Spring MVC integrates with certain async flows such as `Callable`, though this does not generalize to all executors.

**Two strategies to consider:**

- If the asynchronous task needs to run with the current user's privileges, use an official security context propagation mechanism and ensure the context is restored/cleared at the right time.
- If a background task only needs the ID of the user who triggered the action, pass a **verified and authorized ID** into the command/event with clear audit intent. Never retain raw request/session references or push sensitive credentials onto a queue for convenience.

You should also avoid reading the holder at application startup or inside a bean constructor and storing it in a singleton field. Identity is a **property of the current execution context**, not global state permanently attached to a service instance.

## 10. Common Integration Issues

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| `getAuthentication()` returns null | Request bypassed matching chain; context not populated; different thread. | Check security chain, execution phase, thread, and dispatcher type. |
| `getName()` returns `anonymousUser` | Public endpoint where the anonymous filter provided a guest principal. | Check for anonymous using an appropriate mechanism before treating as logged-in user. |
| `@AuthenticationPrincipal UserDetails` returns null | Actual principal is `Jwt`, `OidcUser`, or custom type. | Check the authentication class and principal class in development. |
| Browser sends cookie but controller sees guest | Invalid/expired cookie or chain does not use sessions. | Inspect SecurityContextRepository, session policy, and authentication filters. |
| API uses Bearer but code calling `session.getAttribute("user")` returns null | Application couples business logic to session while auth is stateless. | Replace with APIs reading `SecurityContext` / principal; map identity explicitly. |
| Request after login loses context | Context not saved to repository; cookie not resent; different session policy. | Check context-saving mechanism and response/login flow. |
| Identity lost inside `@Async` | `ThreadLocal` does not auto-propagate to executor threads. | Use supported context propagation or pass verified ID. |
| Logged-in user can view another user's data | Controller reads identity properly, but misses resource permission checks. | Add object-level authorization; never use username as a substitute for authorization. |
| Endpoint returns JSON containing credentials | Serialized raw `Authentication` or principal. | Use a DTO with only required fields; never log tokens/secrets. |
| Multiple `SecurityFilterChain` beans behave unexpectedly | First matching chain has a different session/policy. | Check `securityMatcher`, chain order, and filters in the active chain. |

### Short Debugging Workflow

1. Identify method, URL, dispatcher type, matching chain, and actual authentication mechanism; never print full credentials/tokens.
2. Inspect authentication at the right **request stage after security filters**, unlike reading the holder before filters.
3. Distinguish `null`, `AnonymousAuthenticationToken`, verified principals, and custom authentication types.
4. Verify whether `getName()` matches its intended contract; if an internal ID is needed, inspect the mapping layer.
5. If a subsequent request loses login, check session policy, `SecurityContextRepository`, and whether the client resends credentials.
6. If an async task misses identity, check propagation or immutable data passed into the task.
7. For permission errors, separate authentication (who) from authorization (allowed actions); add integration tests for guest, regular user, and user lacking permissions.

## 11. Self-Check Questions

**1.** Why shouldn't you retrieve identity via `session.getAttribute("username")` in a service?  
Because the service becomes coupled to a specific attribute name/session mechanism and will not work equivalently with Basic, Bearer, or other authentication mechanisms. Spring Security already provides `Authentication` for the request.

**2.** What API should an endpoint use if it only needs the username?  
It can use `Principal#getName()` or `Authentication#getName()` in the controller; `@CurrentSecurityContext` retrieves it explicitly from the context.

**3.** Does `auth != null && auth.isAuthenticated()` guarantee a logged-in user?  
No. `AnonymousAuthenticationToken` can return `authenticated=true`; evaluate anonymous/trust level with an appropriate mechanism.

**4.** Does `SessionCreationPolicy.STATELESS` render `SecurityContextHolder` useless?  
No. The context still holds the authentication for the current request; it simply avoids relying on a session to retain authentication state across requests.

**5.** Should you use `@AuthenticationPrincipal UserDetails` for every JWT endpoint?  
No. A JWT Resource Server may use `Jwt` as the principal; pick the matching type or normalize identity in a service.

**6.** Why might `Authentication.getName()` not be the database user ID?  
Because the name depends on the authentication type, claim mapping, or identity provider. Internal user IDs require an explicit contract/mapping.

**7.** Is a method that reads the current user accurately enough to protect `GET /orders/{id}`?  
No. You must verify that the user is authorized to view that order (owner/tenant/policy) in the service/resource layer.

**8.** Why can the context disappear when using `CompletableFuture.supplyAsync()`?  
Because the default holder is bound to the thread, while the task may run on a different thread; explicit context propagation or passing a verified ID intentionally is required.

**9.** Should you return the raw `Authentication` as JSON so the frontend can extract email, roles, and tokens?  
No. Return a minimal DTO and avoid exposing credentials, claims, or unnecessary security properties.

**10.** How do `Principal`, `@AuthenticationPrincipal`, and `SecurityContextHolder` mainly differ?  
`Principal` provides a common interface for the current user; `@AuthenticationPrincipal` extracts the principal object by type; `SecurityContextHolder` reads the authentication/context from any code in the proper execution context. None of the three require direct HTTP session access.

**Key takeaway:** read identity from **the source authenticated by Spring Security**. Let security filters and repositories decide how the context is supplied; controllers and services simply consume an identity API with a clear contract, handle anonymous callers, minimize returned data, and always authorize resources separately.