# How Does SecurityContext Hold Authentication and Current Identity?

> **A core idea:** Once Spring Security has processed authentication for a request, information about **the principal making that request** is typically represented by an `Authentication` object, held inside a `SecurityContext`, and application code accesses the current context through `SecurityContextHolder`. Do not think of `SecurityContext` as a "browser session" or a "database user"; it is a container for security state within an execution scope, loaded and cleared according to Spring Security's lifecycle.

This lesson belongs to Spring Security's **Component Map** series, focusing on the Spring MVC/Servlet model and Spring Security 6.x. Examples run on Java 17 and Spring Boot 3.5.x. For WebFlux/reactive applications, context propagation relies on the **Reactor Context**, not the Servlet `ThreadLocal` model as the default assumption.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Diagram the relationship between `SecurityContextHolder`, `SecurityContext`, `Authentication`, `principal`, `credentials`, and `GrantedAuthority`.
2. Explain how an authentication is created after login/Basic/Bearer, where it is placed into the context, and how long it lives.
3. Safely retrieve the username/principal/authorities in a controller or service; distinguish `authentication.getName()` from the object type inside `authentication.getPrincipal()`.
4. Understand why `isAuthenticated() == true` is **not sufficient** to conclude that a request came from a real logged-in user, and why a role differs from permissions on a specific resource.
5. Distinguish between **holding the context for the currently running request** and **persisting identity across requests** via a session, cookie, or re-authenticating from a token.
6. Avoid context leakage across thread pools, wrong assumptions with `@Async`, and manually setting an unverified `Authentication`.

## 2. Component Map

```text
                      Authentication mechanism
             (form login, HTTP Basic, JWT, OAuth2...)
                              |
                              v
                 AuthenticationManager / Provider
              [verify credentials / identity source]
                              |
                              v
                    Authentication (result)
                name | principal | credentials
                 authorities | details | authenticated
                              |
                              v
                      SecurityContext
                 [authentication = object above]
                              |
                              v
                    SecurityContextHolder
                [current context of execution thread]
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
    URL/method authorization             Controller/Service
    (read authorities, identity)        (read current principal)
```

Each component has a distinct role:

| Component | What is it? | What is it used for? |
| --- | --- | --- |
| `SecurityContextHolder` | API that holds/retrieves the current context via `SecurityContextHolderStrategy`, defaulting to `ThreadLocal` in Servlet | Returns the `SecurityContext` for the thread currently processing |
| `SecurityContext` | An object containing an `Authentication` | Groups security information attached to the current execution |
| `Authentication` | Interface representing an authentication request or an authenticated result | Carries principal, credentials, authorities, details, and authentication status |
| `principal` | The subject represented by the authentication, whose type depends on the mechanism | Identifies the user/service account; e.g. `UserDetails`, `Jwt`, `OAuth2User` |
| `credentials` | Data used to prove identity, such as a password or token | Usually used during authentication; may be erased afterward |
| `GrantedAuthority` | Permission/role/scope granted to the principal | Input for authorization such as `ROLE_USER`, `SCOPE_read` |
| `AuthenticationManager` | Contract for performing authentication | Accepts an authentication token, returns a result token or throws an exception |
| `AuthenticationProvider` | A specific way of verifying credentials | Validates a password, token, or corresponding mechanism |
| `SecurityContextRepository` | How the context is read/written across request/response | Can associate the context with an HTTP session, request attribute, or not persist it |

**The directly queried relationship:**

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication != null) {
    String identityName = authentication.getName();
}
```

This snippet is illustrative code meant to run inside a flow managed by Spring Security, **not a standalone Java program**. It reads the context attached to the thread by Spring Security, then retrieves the authentication if present. Be especially careful with anonymous requests, background tasks, or code outside the security filter chain: `authentication` may be `null` or an anonymous token.

## 3. What Does SecurityContext Contain, and What Does It Not?

`SecurityContext` is a small interface with two primary operations:

```java
Authentication authentication = context.getAuthentication();
context.setAuthentication(authentication);
```

In practice, the context is usually `SecurityContextImpl`. It does not itself hold the entire user system; it references the current `Authentication`. User profiles, hashed passwords in the database, tenant information, and ACLs may live elsewhere. Do not assume all user information from the persistence layer is automatically loaded into the context.

### 3.1. Important Fields on Authentication

| API | Main meaning | Watch out for |
| --- | --- | --- |
| `getName()` | Principal name according to the authentication mechanism | With JWT/OIDC this may be `sub` or a mapped name; not an email by default |
| `getPrincipal()` | Object describing the subject | May be `UserDetails`, a string, `Jwt`, `OAuth2User`, or a custom principal |
| `getCredentials()` | Data proving identity | Often erased after authentication; **do not log, do not return from APIs** |
| `getAuthorities()` | High-level permissions of the principal | Does not replace owner/tenant/resource checks |
| `getDetails()` | Additional metadata by authentication type, e.g. request info | Do not treat client IP/metadata as proof of permission |
| `isAuthenticated()` | Status flag on the authentication object | **Can be true for `AnonymousAuthenticationToken`** |
| `setAuthenticated(...)` | Interface method on some implementations | Must not manually set `true` to "bypass login" |

For example, when Alice logs in using username/password with `UserDetailsService`, the authentication after success may look like:

```text
SecurityContextImpl
└── Authentication = UsernamePasswordAuthenticationToken
    ├── principal = UserDetails(username="alice", ...)
    ├── credentials = null                  (erased, depends on provider)
    ├── authorities = [ROLE_USER, PROFILE_READ]
    ├── details = WebAuthenticationDetails  (if present)
    └── authenticated = true
```

For an API using a JWT Resource Server:

```text
SecurityContext
└── Authentication = JwtAuthenticationToken
    ├── principal = Jwt (claims verified by decoder)
    ├── name = usually from "sub" claim, depending on configuration
    ├── authorities = e.g. [SCOPE_profile.read]
    └── authenticated = true
```

Both authentications above can carry the same "user Alice", yet **do not share the same principal class**. Therefore, casting every principal to `UserDetails` fails if the application supports OAuth2/JWT. In real systems, map the principal from the trusted mechanism to a **stable internal user ID** for ownership/tenant checks, avoiding mutable display names or emails as business keys.

### 3.2. Authentication Can Also Be an Unauthenticated Request

The `Authentication` interface serves **two roles**:

- **Input:** a token built from received credentials, such as an unverified username/password. `isAuthenticated()` is typically `false`.
- **Output:** after `AuthenticationManager.authenticate(...)` succeeds, the provider returns an authentication representing the verified principal, along with appropriate authorities.

A conceptual view (not code you need to write manually for default form login):

```java
// Conceptual illustration: authenticationManager, username, and password
// are inputs already provided in a custom handling flow.
Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified = authenticationManager.authenticate(pending);
// verified is the result accepted by the provider, or authenticate() throws an exception.
```

If authentication fails, Spring Security must not treat unverified credentials as a logged-in identity. Never write code like `new UsernamePasswordAuthenticationToken(username, null, authorities)` with arbitrary authorities taken from client JSON and place it in the holder; constructors accepting authorities usually produce a token already marked authenticated. An API must verify credentials/claims before granting authorities.

## 4. How Does SecurityContextHolder Access "Current"?

### 4.1. Default in Spring MVC/Servlet: ThreadLocal

By default, `SecurityContextHolder` uses the `MODE_THREADLOCAL` strategy. Once a request's context has been initialized by the filter chain, code running **on the same processing thread** can generally call `SecurityContextHolder.getContext()` without passing the context through every method. That is what **current** means: current **within the active execution context**, not a global variable for the entire JVM.

```text
Request Alice -> worker thread T1 -> Holder(T1) -> Context(Alice)
Request Bob   -> worker thread T2 -> Holder(T2) -> Context(Bob)
                                       |
                        No context shared by default
```

Servlet containers **reuse threads** to serve different requests. Spring Security is responsible for clearing the holder once the request finishes passing through the filter chain, preventing request A's authentication from leaking into request B reusing that thread. If you manually populate the holder outside the standard mechanism, you must manage its lifecycle and clear the context in a `try/finally` block within the scope you control.

**Do not** store the current user in a `static` variable, a singleton field on a controller/service, or a shared cache expecting each request to have its own value. Those locations can be shared across multiple threads and cause cross-user identity leakage.

### 4.2. Context Can Be Read in Many Layers, Choose the Right API

In a servlet service, you can use:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();

if (auth == null) {
    // No authentication in the holder at this point.
    return;
}

String name = auth.getName();
Collection<? extends GrantedAuthority> roles = auth.getAuthorities();
```

Corresponding imports:

```java
import java.util.Collection;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
```

In a Spring MVC controller, prefer parameters resolved by the framework, as dependencies are explicit and easier to test:

```java
// Illustration of a method inside a @RestController.
@GetMapping("/me")
String me(Authentication authentication) {
    return authentication.getName();
}
```

For a specific principal:

```java
// Only appropriate if the authentication mechanism actually provides UserDetails.
@GetMapping("/username")
String username(@AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

For the entire context:

```java
@GetMapping("/context")
String name(@CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth == null ? "(none)" : auth.getName();
}
```

`@AuthenticationPrincipal` and `@CurrentSecurityContext` belong to `org.springframework.security.core.annotation`. For a regular `Authentication` or `Principal` parameter, Spring MVC may retrieve the principal from `HttpServletRequest`. For an anonymous request, an `Authentication` parameter may be **null** even though `SecurityContextHolder` still holds an `AnonymousAuthenticationToken`. If you need to inspect the actual anonymous context, use `@CurrentSecurityContext` or the holder rather than relying on casting from `HttpServletRequest.getUserPrincipal()`.

### 4.3. Why Does SecurityContextHolder Only Return "Current Identity", Not Data Permissions?

Suppose:

```text
Authentication:
  name = alice
  authorities = [ROLE_USER, REPORT_READ]
Request:
  GET /reports/99
Database:
  report 99.owner = bob
```

`Authentication` is enough to know the actor is Alice and has the general `REPORT_READ` authority. It **does not answer** who owns report 99. The service/repository must check the owner, tenant, ACL, status, and trusted business constraints. Checking only `authentication.isAuthenticated()` or `hasRole("USER")` can lead to IDOR/BOLA vulnerabilities.

Think of the two responsibilities separately:

- **Authentication** provides the verified identity and authorities.
- **Authorization** applies policy to an action/resource, reading information from authentication **and** the database and validated inputs.

## 5. End-to-End Flow: From Request to Authentication in SecurityContext

Suppose a request uses HTTP Basic:

```text
GET /me
Authorization: Basic <Base64 value of username:password>
          |
          v
Servlet Filter Chain -> FilterChainProxy -> SecurityFilterChain
          |
          +-- SecurityContextHolderFilter
          |     loads SecurityContext (or deferred context) from repository
          |
          +-- BasicAuthenticationFilter
          |     creates authentication request from Basic credentials
          |     calls AuthenticationManager / provider
          |     if valid: sets Authentication on the current context
          |
          +-- AnonymousAuthenticationFilter (if needed)
          |     supplies anonymous authentication if no valid actor exists yet
          |
          +-- AuthorizationFilter
          |     decides whether GET /me is allowed to proceed
          v
Controller / Service
          |
          v
SecurityContextHolder.getContext().getAuthentication()
          |
          v
Response; Spring Security clears the context from the holder for the request
```

This is a conceptual model, not a dump of the exact filter order for every application. Actual filters depend on version, configuration, login/JWT mechanism, `SecurityFilterChain`s, and dispatcher type. For Basic, requests typically need to send credentials on every call to be authenticated; under a stateless configuration, a ThreadLocal context never stays alive into the next request.

Key steps:

1. **Request start:** Spring Security sets up the context access mechanism for the current execution. The context may be loaded from `SecurityContextRepository` or be new/without an authentication.
2. **Authentication:** the corresponding filter extracts credentials and invokes the provider. The provider verifies the password/token/certificate before creating a trusted authentication.
3. **Set on context:** when authentication succeeds, the current context carries the result for authorization filters and handlers to use.
4. **Authorization:** may rely on authorities, authenticated state, URL/method configuration, or custom policies.
5. **Request end:** the holder is cleared so another request does not inherit the wrong identity. If the application requires staying logged in across requests, persistence must be handled via the repository and corresponding session/token mechanism.

### 5.1. Form Login and Session

For web applications using session-based login, after a user logs in successfully, Spring Security can save the security context in the HTTP session via `SecurityContextRepository`. On subsequent requests, the session cookie serves to look up the corresponding server session; the framework loads the context for the new request. **The cookie is not a full copy of the SecurityContext**, and the new thread's context holder is not the exact ThreadLocal instance from the previous thread.

By the common default in Spring Security 6, `DelegatingSecurityContextRepository` combines `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. The request attribute component keeps the context available across certain dispatches such as ERROR within the same request; the HTTP session correlates the context across requests when sessions are used. However, session policy, authentication mechanism, and repository can all be replaced.

### 5.2. HTTP Basic/Bearer and Stateless APIs

For stateless APIs, each request carries Basic credentials or a Bearer token. Spring Security re-authenticates the credential/token per configuration and creates an `Authentication` for **the current request**. There is no server session remembering the user between two requests in this model.

- Basic: `Authentication` is typically `UsernamePasswordAuthenticationToken` with `UserDetails` as the principal after provider verification.
- Bearer JWT Resource Server: `Authentication` is typically `JwtAuthenticationToken` with `Jwt` as the principal and mapped scopes/roles. Signature/issuer/audience/expiry and required claims must be configured for validation properly.
- Opaque token Resource Server: introspection and principal type may differ from JWT. Do not assume all Bearer APIs have a `Jwt`.
- OAuth2 Login/OIDC for browsers can produce an `OAuth2AuthenticationToken` with `OAuth2User`/`OidcUser` depending on the flow. The context is usually persisted via the corresponding session.

### 5.3. When Building Custom Authentication, Understand Context Saving

In Spring Security 6, `SecurityContextHolderFilter` mainly **loads** the context and does not automatically save every modification to the session. If a custom filter/controller authenticates manually and wants login to persist on later requests, merely calling `SecurityContextHolder.setContext(...)` is usually **not enough**. You must call `SecurityContextRepository.saveContext(context, request, response)` according to your persistence design.

```java
// Illustrative code inside an existing custom login handler:
//  - AuthenticationManager authenticationManager
//  - SecurityContextRepository securityContextRepository
//  - HttpServletRequest request
//  - HttpServletResponse response
//  - String username, password
// Do not copy this snippet as a production login endpoint without designing
// CSRF, session fixation, failure handling, and session authentication strategy.
Authentication pending =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

Authentication verified = authenticationManager.authenticate(pending);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

In the snippet above, `createEmptyContext()` creates a new context rather than fetching a shared context and mutating it in place; that is the safer approach when multiple threads might share a reference. When custom login is needed, leverage built-in authentication filters/handlers so session fixation, remember-me, redirects, events, and error semantics are also handled properly.

**Remember:** `SecurityContextRepository` is how the context is associated across requests, whereas `SecurityContextHolder` is how running code accesses the context. They serve two different roles.

## 6. Anonymous Authentication: The `isAuthenticated()` Trap

When anonymous authentication is enabled (typically the default in HTTP Security), `AnonymousAuthenticationFilter` may place an `AnonymousAuthenticationToken` in the context for unauthenticated requests.

For example:

```text
SecurityContextHolder.getContext().getAuthentication()
  class: AnonymousAuthenticationToken
  name: anonymousUser
  authorities: [ROLE_ANONYMOUS]
  isAuthenticated(): true
```

This **does not mean an unauthenticated visitor should be treated as a valid user**. `isAuthenticated()` is a state flag on the token object, and `AnonymousAuthenticationToken` typically returns `true`. Spring Security provides `AuthenticationTrustResolver` to distinguish anonymous, remember-me, and fully authenticated according to each rule's requirements. When writing HTTP rules, use `authenticated()`/`fullyAuthenticated()`/`anonymous()` and corresponding authorization APIs; the framework knows how to evaluate anonymous tokens instead of trusting a raw Boolean check.

**Do not write endpoint protection logic like this:**

```java
// WRONG if relying solely on the Boolean flag as proof of a real user:
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
if (auth != null && auth.isAuthenticated()) {
    // This block can execute for AnonymousAuthenticationToken.
}
```

For code that needs to evaluate identity in a service without method rules, you can use an explicit policy or `AuthenticationTrustResolver`:

```java
// Illustrative snippet (not a standalone program).
AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

Authentication auth = SecurityContextHolder.getContext().getAuthentication();
if (auth == null || trustResolver.isAnonymous(auth)) {
    throw new AccessDeniedException("Authentication required");
}
```

In production, prefer letting Spring Security enforce access at the boundary with `@PreAuthorize` or `authorizeHttpRequests`, then verifying business owner/tenant constraints. When returning errors, adhere to the 401 (unauthenticated) / 403 (forbidden) contract, and never serialize the Authentication object for debugging through a public API.

## 7. Runnable Example: Observing Identity from SecurityContext in Spring Boot

We build a small API:

- `GET /public/context` is public, reads the context via `@CurrentSecurityContext`, and shows the difference between anonymous and authenticated.
- `GET /me` requires login, retrieves `Authentication` and `@AuthenticationPrincipal UserDetails` from Spring MVC, and returns only name + authorities.
- `GET /owner/{username}` demonstrates a service reading the context via `SecurityContextHolder` and denying access to another user's data.
- `GET /admin` requires `ROLE_ADMIN`, demonstrating an authority used for a URL rule.

This lesson uses **Spring Boot 3.5.16**, a real release in the Spring Boot 3.5 line, Java 17, and Spring Security 6.x. In-memory identity handling is strictly for local/testing use. New projects should verify the supported Spring Boot line and latest patches.

### 7.1. File Structure

```text
security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/SecurityContextDemoApplication.java
    └── test/java/demo/context/SecurityContextDemoApplicationTests.java
```

### 7.2. Maven Dependencies

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-context-demo</artifactId>
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

### 7.3. Complete Application Code

Create `src/main/java/demo/context/SecurityContextDemoApplication.java`:

```java
package demo.context;

import java.util.List;
import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Allow only servlet container ERROR dispatches for error rendering.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/context").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/owner/*").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            // Every request must carry its own credentials; no session persistence for login.
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
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
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "PROFILE_READ")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "PROFILE_READ")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build());
    }
}

@RestController
class IdentityController {
    private final PrivateNoteService notes;

    IdentityController(PrivateNoteService notes) {
        this.notes = notes;
    }

    @GetMapping("/public/context")
    ContextView publicContext(@CurrentSecurityContext SecurityContext context) {
        Authentication auth = context.getAuthentication();
        return new ContextView(
            auth == null ? "(none)" : auth.getName(),
            auth != null && auth.isAuthenticated(),
            auth instanceof AnonymousAuthenticationToken
        );
    }

    @GetMapping("/me")
    MeView me(Authentication authentication,
              @AuthenticationPrincipal UserDetails principal) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new MeView(
            authentication.getName(),
            principal.getUsername(),
            authorities
        );
    }

    @GetMapping("/owner/{username}")
    String privateNote(@PathVariable String username) {
        return notes.readMine(username);
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }
}

@Service
class PrivateNoteService {
    @PreAuthorize("hasAuthority('PROFILE_READ')")
    public String readMine(String requestedOwner) {
        // Do not take the "calling user" from a query parameter or request body.
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || !requestedOwner.equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "note-of-" + requestedOwner;
    }
}

// DTO returning only the fields needed for observation, without exposing credentials/details.
record ContextView(String name, boolean authenticatedFlag, boolean anonymous) {}

record MeView(String name, String principalUsername,
              List<String> authorities) {}
```

Key design details explained:

1. **`@CurrentSecurityContext SecurityContext`** lets the controller observe the authentication even when the request is anonymous. When the anonymous filter is active, `name` is typically `anonymousUser`, `authenticatedFlag` can be `true`, and `anonymous` is `true`.
2. **`Authentication authentication`** in the `/me` method is resolved by the framework for an authenticated request. In this example using Basic + `UserDetailsService`, the `principal` received from `@AuthenticationPrincipal UserDetails` corresponds to the same user.
3. **`SecurityContextHolder`** inside the service reads the exact identity bound to the incoming request. This is how you look up the current context when not passing the actor explicitly to the service; in complex domains, you can wrap it in a `CurrentUser` adapter and pass a verified user ID into business logic for easier testing.
4. `@EnableMethodSecurity` enables `@PreAuthorize("hasAuthority('PROFILE_READ')")` for calls from the controller through the service proxy. Bob has the permission to read profiles, yet cannot read Alice's profile because the service also verifies **the exact owner**.
5. `hasRole("ADMIN")` is equivalent to checking `ROLE_ADMIN` with the default prefix, unlike `hasAuthority("ADMIN")`. Authority names must match how they were assigned to the principal.
6. **`SessionCreationPolicy.STATELESS`** is used intentionally so the example does not persist identity across sessions. Each new request using HTTP Basic must resend credentials to get an authenticated context. `SecurityContextHolder` still works **within the request**.
7. `DispatcherType.ERROR` is permitted so the servlet container renders 404 errors properly, while not allowing clients to freely reach undeclared endpoints. Initial requests must still match the rules.
8. The example uses only **GET** to read data. If adding POST/PUT/DELETE, you must properly design CSRF/session/cookies, authorization for the new methods, validation, and transactions. Do not assume CSRF is unnecessary for every type of API.

### 7.4. Integration Test with MockMvc

Create `src/test/java/demo/context/SecurityContextDemoApplicationTests.java`:

```java
package demo.context;

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
class SecurityContextDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void currentAuthenticationFollowsEachRequest() throws Exception {
        // Anonymous requests can still have AnonymousAuthenticationToken in the holder.
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("anonymousUser"))
            .andExpect(jsonPath("$.anonymous").value(true))
            .andExpect(jsonPath("$.authenticatedFlag").value(true));

        // Endpoints requiring auth block anonymous requests.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        // Real HTTP Basic: Spring Security authenticates via InMemoryUserDetailsManager.
        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.principalUsername").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("PROFILE_READ"))
            .andExpect(jsonPath("$.authorities[1]").value("ROLE_USER"));

        // Another request uses Bob's identity, not inheriting Alice's.
        mvc.perform(get("/me").with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("bob"));

        // Same public endpoint, but the context is now authenticated via Basic.
        mvc.perform(get("/public/context")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.anonymous").value(false));

        // No credentials sent on the next request -> anonymous again.
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.anonymous").value(true));

        // Having the right context is only the first condition; the service also checks owner.
        mvc.perform(get("/owner/alice").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("note-of-alice"));

        mvc.perform(get("/owner/alice").with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isNotFound());

        // URL authorization relies on current authorities.
        mvc.perform(get("/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Undeclared paths are denied; never opened automatically even when logged in.
        mvc.perform(get("/unknown").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

The test runs a verification sequence in a single method: anonymous, real Basic authentication, switching users between requests, no context leakage, URL authorization, and owner check. Using `httpBasic(...)` exercises the real authentication path through Spring Security. In contrast, `@WithMockUser`/`user(...)` primarily creates a simulated principal for authorization testing and **does not verify real passwords**.

### 7.5. Commands to Run and Expected Results

In the directory containing `pom.xml`, JDK 17+ and Maven 3.6.3+ are required:

```bash
mvn test
mvn spring-boot:run
```

When the environment has all dependencies and compatible configuration, `mvn test` runs the test above; HTTP calls are expected to return the defined status codes and JSON, without relying on a fixed stdout line from Spring Boot.

In another terminal:

```bash
curl -i http://localhost:8080/public/context
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u bob:demo-pass http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/owner/alice
curl -i -u bob:demo-pass http://localhost:8080/owner/alice
curl -i -u alice:demo-pass http://localhost:8080/admin
curl -i -u admin:demo-pass http://localhost:8080/admin
```

| Call | Expected status | Illustration |
| --- | --- | --- |
| `GET /public/context` no credentials | `200` | `anonymous=true`, `name=anonymousUser` |
| `GET /me` no credentials | `401` | Anonymous does not pass `authenticated()` |
| `GET /me` as Alice | `200` | `name=alice`, Alice's authorities |
| `GET /me` as Bob | `200` | `name=bob`, independent of previous request |
| `GET /owner/alice` as Alice | `200` | Body `note-of-alice` |
| `GET /owner/alice` as Bob | `404` | Owner check from current authentication |
| `GET /admin` as Alice | `403` | Lacks `ROLE_ADMIN` |
| `GET /admin` as Admin | `200` | Body `admin-ok` |

Note: `curl -u` with HTTP Basic sends the password Base64-encoded in a header, **not encrypted**. The `http://localhost` examples are strictly for local development with no traffic over untrusted networks. Production must run over HTTPS and replace sample accounts/passwords with a managed identity source.

## 8. SecurityContext and Async Processing / Thread Pools

### 8.1. Why Might `@Async` Not See the User?

Under the default `MODE_THREADLOCAL`:

```text
HTTP worker thread T1       async worker thread T2
SecurityContext(Alice)      does not automatically have SecurityContext(Alice)
         |
         +----- submit task -----> Runnable runs on T2
```

If a service invokes `@Async`, `CompletableFuture.supplyAsync(...)`, or a separate `Executor`, code calling `SecurityContextHolder.getContext().getAuthentication()` on the new thread may get `null`. This follows the ThreadLocal model; it is not a sign that "Spring Security randomly forgot the login".

You can use wrappers provided by Spring Security, such as `DelegatingSecurityContextRunnable` or `DelegatingSecurityContextExecutor`, to attach the appropriate context for the task and clean it up in `finally`. An example illustrating how to wrap a Runnable:

```java
// Illustrative snippet inside an authenticated request flow.
// Related imports: java.lang.Runnable,
// org.springframework.security.concurrent.DelegatingSecurityContextRunnable.
Runnable businessTask = () -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "(none)" : auth.getName());
};

Runnable delegated =
    new DelegatingSecurityContextRunnable(businessTask);

// In practice, submit `delegated` to an Executor managed by the application.
// Calling run() directly here only demonstrates the wrapped object.
delegated.run();
```

In real applications, do not spawn unbounded threads per request. Use `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` with a configured executor, or pass the **trusted actor ID and required permissions** as explicit inputs to the task. For delayed jobs running minutes or hours later, a snapshot authentication context may have expired or permissions may have been revoked. Design your policy to re-verify permissions at execution time and avoid putting raw tokens/passwords into queues.

### 8.2. Do Not Abuse `MODE_INHERITABLETHREADLOCAL` or `MODE_GLOBAL`

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` allows **newly created** threads to inherit the context from a parent thread in certain situations, but with thread pools reusing workers, that mechanism easily causes confusion and identity leakage if unmanaged. `MODE_GLOBAL` shares the context across the entire JVM and is generally **unsuitable** for multi-user web servers. Normally, keep `MODE_THREADLOCAL` and use Spring Security's supported integrations for async work.

### 8.3. WebFlux Does Not Use the Same Model

In reactive applications, processing steps may hop across threads and there is no single fixed ThreadLocal representing the request from start to finish. Spring Security uses `ReactiveSecurityContextHolder` backed by the Reactor Context. Do not copy a Servlet service calling `SecurityContextHolder.getContext()` into WebFlux and assume it will always return the right principal. Consult the reactive APIs when working on WebFlux modules.

## 9. Common Mistakes

### Mistake A — "Holder = HttpSession"

**Wrong:** calling `SecurityContextHolder.getContext()` and expecting the data to be available on every subsequent request.

**Right:** the holder serves the current execution scope; persisting authentication across requests requires `SecurityContextRepository`/sessions or re-validating a token. In Spring Security 6 with custom login, be sure to understand **explicit save**. Stateless Basic can produce a fresh Authentication on each request.

### Mistake B — Casting principal to UserDetails in every flow

**Wrong:**

```java
// Only valid if the authentication actually has UserDetails as its principal:
UserDetails user = (UserDetails) authentication.getPrincipal();
```

**Right:** check the configured authentication type and extract the appropriate identifier. For JWT, typically use the principal/claims from `Jwt` or the configured name; for OIDC, use `OidcUser`; for Basic + `DaoAuthenticationProvider`, `UserDetails` applies. Map to a server-established `CurrentUser` or application principal so the domain does not depend on multiple token types.

### Mistake C — Relying solely on `isAuthenticated()`

**Wrong:** `auth.isAuthenticated()` can be true on an `AnonymousAuthenticationToken`.

**Right:** use `authenticated()`/`fullyAuthenticated()`, `AuthenticationTrustResolver`, or an explicit server policy. Do not place a lone Boolean check inside a controller and assume it is complete protection.

### Mistake D — Using `getName()` as an unstable ownerId

**Wrong:** using email or display name as a resource key in multi-tenant applications without understanding how the identity provider defines the principal name.

**Right:** map `sub`/account ID from a trusted source to a stable user ID, and check tenant and owner in the database. Test cases where an email changes, two identity providers share a username, and subjects are scoped by issuer.

### Mistake E — Leaking credentials when logging authentication objects

**Wrong:** returning a raw `Authentication`/`SecurityContext` via an API or unconditionally logging `toString()`. This can expose details, claims, session metadata, or objects holding secrets.

**Right:** build a DTO containing only necessary fields (e.g. stable user ID, sanitized display name, policy-permitted public authorities). Never log passwords, bearer tokens, refresh tokens, or session cookies; mask sensitive data in monitoring/tracing.

### Mistake F — Using the context as a global singleton

**Wrong:** storing authentication in a mutable field of a singleton service:

```java
// WRONG: the same service instance serves multiple requests.
class UnsafeService {
    Authentication currentUser;
}
```

**Right:** obtain identity scoped properly to the request/thread, or pass a verified actor ID/`CurrentUser` into the service. For asynchronous code, use managed propagation and never share context across users.

### Mistake G — Assigning authorities to Authentication from client data

**Wrong:** trusting `role=ADMIN` or `X-User` sent by the client, creating an authentication with `authenticated=true`, and skipping verification.

**Right:** the filter/provider/decoder must verify credentials/claims across the trust boundary before assigning authorities. Resource authorization must still be enforced separately even when authentication is valid.

### Mistake H — Using `@PreAuthorize` when calls bypass the proxy

**Wrong:** assuming `@PreAuthorize` always executes when calling a method on the same bean via `this.method()`, or forgetting to enable `@EnableMethodSecurity`.

**Right:** architect clear enforcement points, invoke through the interceptor-managed bean, and test from the real entrypoint. For sensitive logic, constraints at the data/domain layer must also be ensured.

## 10. Quick Distinction Table to Self-Check Understanding

| Statement | True/False | Explanation |
| --- | --- | --- |
| `SecurityContextHolder` holds one context for every user in the JVM | False | Defaults to per-thread in Servlet; other strategies exist if configured |
| `SecurityContext` typically holds the current `Authentication` | True | The context's main API is getting/setting authentication |
| `Authentication` always has a principal of type `UserDetails` | False | May be `Jwt`, `OAuth2User`, a string, or a custom principal |
| `getCredentials()` is always a plaintext password | False | Depends on the flow and is often erased after authentication |
| `Authentication.isAuthenticated() == true` guarantees a real logged-in user | False | `AnonymousAuthenticationToken` can also return true |
| `getAuthorities()` tells you the user can view every object | False | Authorities are typically coarse-grained permissions; data policies are needed |
| `SecurityContextHolder` automatically persists logins forever | False | Request lifecycle differs from session/token persistence |
| A stateless API can still use `SecurityContextHolder` during a request | True | Each request is authenticated and gets its own context |
| `@Async` newly spawned threads always inherit the request's principal | False | Context propagation requires appropriate configuration/mechanisms |
| Servlet and WebFlux use the same current ThreadLocal mechanism | False | WebFlux uses `ReactiveSecurityContextHolder` |
| Spring Security always clears the holder at the end of a request through the filter chain | True in standard Spring Security flows | Custom threads/filters must manage their own lifecycle |
| HTTPS automatically creates an `Authentication` for the user | False | TLS protects transport; user authentication is a separate mechanism |

## 11. Checklist When Using Current Identity in a Real API

1. **Input authentication:** are credentials/tokens/sessions verified properly on the server from a trusted identity source?
2. **Principal type:** does code mistakenly depend on `UserDetails` while the system uses JWT/OIDC?
3. **Stable identity:** is `getName()` a suitable user ID for owner/tenant policies, or should `subject` be mapped to an internal ID?
4. **Authorizations:** do rules rely on authorities from a trusted source and also check the specific resource in the service?
5. **Anonymous:** does the API properly distinguish anonymous/remember-me/fully authenticated when sensitive operations are requested?
6. **Session/stateless:** is it clear that current request and persistence across requests are two different scopes? Does custom login save the context properly?
7. **Concurrency:** is user context used in `@Async`/queues/callbacks? If so, is it propagated intentionally and cleared on time?
8. **Response/logging:** are only minimal DTOs returned, without leaking credentials, sensitive claims, tokens, or session cookies?
9. **Negative tests:** anonymous calling private endpoints; user A accessing user B's resource; user lacking a role; two consecutive requests using two different principals?
10. **Infrastructure:** does the API transmit credentials over HTTPS, with session/cookie flags and token lifetimes managed properly?

## 12. Takeaways

- **`SecurityContextHolder` → `SecurityContext` → `Authentication`** is the standard path to obtain the currently active identity in Spring Security Servlet.
- `Authentication` consists of **principal, credentials, authorities, details**, and status, though actual types depend on the login mechanism; never cast blindly.
- **Current context ≠ HTTP session.** The holder tells you who is active in the current execution; repositories/sessions/tokens decide how identity is restored on later requests.
- **`AnonymousAuthenticationToken` is not a real logged-in user**, even though `isAuthenticated()` may be true.
- **Identity does not equal permission on every object.** Obtain the principal from a trusted source and enforce policies by actor/action/resource/tenant/state.
- **ThreadLocal does not automatically cross async/thread pools.** Use managed propagation and context cleanup, or pass the actor explicitly and re-check permissions.

## References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html)
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security — Testing with Spring MVC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Boot 3.5.16 artifact](https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-starter-parent/3.5.16/)
