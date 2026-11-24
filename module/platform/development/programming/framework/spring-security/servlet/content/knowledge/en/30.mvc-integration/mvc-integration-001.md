# @AuthenticationPrincipal and Mapping the Principal to Controller Parameters (Spring Security Servlet)

> **Scope:** Spring Security 6.x + Spring MVC on the Servlet stack, e.g., Spring Boot 3.x / Java 17+. This lesson explains how `@AuthenticationPrincipal` obtains the **principal already authenticated by Spring Security** and injects it directly into Controller method parameters; how to map a principal to a domain object, property, or DTO; differences between form/HTTP Basic, JWT Resource Server, and OAuth2/OIDC; and key security pitfalls and testing practices. The complete example uses HTTP Basic **only to simulate** an Authentication with a custom principal, not as a recommendation to make Basic the default choice for every system.

## 1. The Problem @AuthenticationPrincipal Solves

After login or Bearer token verification, Spring Security typically stores the caller's information in `SecurityContext`, including the `Authentication` object. Inside a controller, we may need to know **who is calling** in order to:

- return the user's own profile;
- query orders belonging to `currentUser.id`, without relying on a self-reported ID from the request;
- record an audit event or check account-based authorization conditions;
- display the logged-in user's name without manually querying credentials;
- map a claim from a `Jwt` or `OidcUser` into an appropriate parameter.

A verbose approach is to read the security context manually:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication.getPrincipal();
~~~

This is an **illustrative snippet in Java with Spring Security**, not a standalone runnable program. It requires handling `authentication == null`, determining the principal's type, and avoiding invalid casts. In an MVC controller, Spring Security can perform **argument resolution** for us:

~~~java
@GetMapping("/api/me")
public MeResponse me(@AuthenticationPrincipal AppPrincipal currentUser) {
    return new MeResponse(currentUser.getId(), currentUser.getUsername());
}
~~~

When a request enters the handler, Spring MVC collaborates with `AuthenticationPrincipalArgumentResolver` to extract the principal from the security context and pass it to the annotated parameter. As a result, controller code expresses its intent more clearly: **"this parameter is the current principal provided by Spring Security"**.

**Core principle:** `@AuthenticationPrincipal` **does not perform login, does not verify JWTs/signatures/passwords on its own, and does not grant permissions**. It only reads an **existing authentication result**. Authentication and authorization must be configured beforehand using the appropriate security filter chain, provider, decoder, entry point, and policy.

## 2. Distinguishing SecurityContext, Authentication, and Principal

Conceptual model:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |
    +--> form login / Basic / OAuth2 login / JWT Resource Server ...
    |
    v
Authentication created after successful authentication
    |
    +--> isAuthenticated()
    +--> getName()
    +--> getAuthorities()
    +--> getCredentials()
    +--> getDetails()
    +--> getPrincipal()    <--- principal whose type depends on the mechanism
    |
    v
SecurityContextHolder / request SecurityContext
    |
    v
DispatcherServlet -> Controller method
    |
    +--> @AuthenticationPrincipal AppPrincipal current
    +--> @AuthenticationPrincipal Jwt jwt
    +--> @AuthenticationPrincipal OidcUser oidcUser
~~~

| Concept | Purpose | Example |
| --- | --- | --- |
| `SecurityContext` | Holds the active `Authentication` in the request's security context. | Retrieved via `SecurityContextHolder.getContext()` |
| `Authentication` | Represents the authentication result, along with name, principal, and authorities. | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` |
| `Authentication.getPrincipal()` | The caller object provided by that authentication type. | `UserDetails`, `Jwt`, `OAuth2User`, custom `AppPrincipal` |
| `Authentication.getName()` | String name of the authentication according to its implementation. | username, JWT subject, or OIDC name |
| `Authentication.getAuthorities()` | Permissions attached to the authentication by the framework. | `ROLE_READER`, `SCOPE_orders.read` |
| `@AuthenticationPrincipal` | Selects the **principal**, not the entire authentication. | MVC handler parameter |
| `@CurrentSecurityContext` | Injects part of the security context via an expression, if needed. | `@CurrentSecurityContext(expression = "authentication")` |

An `Authentication` carries more information than just the principal. Therefore, a parameter like `@AuthenticationPrincipal Authentication auth` is **not the standard way to obtain the authentication**: the annotation looks up `getPrincipal()`, whereas the principal is usually not of type `Authentication`. If you need authorities, authentication state, or details, use `Authentication`/`Principal` directly or `@CurrentSecurityContext` as appropriate.

### A Principal Is Not Necessarily a User Entity

In HTTP Basic or form login configured with `UserDetailsService`, the principal is usually an object implementing `UserDetails` (or a custom principal). In a JWT Resource Server, the principal is usually `Jwt`. In `oauth2Login()`, the principal is usually `OAuth2User`/`OidcUser`.

**Do not assume by default that you can cast to `org.springframework.security.core.userdetails.User` or a JPA `UserEntity`.** It depends on the authentication mechanism and the principal type configured by the project itself.

## 3. Spring MVC Argument Resolver Mechanism

`@AuthenticationPrincipal` lives in the package:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
~~~

Spring Security MVC integration provides `AuthenticationPrincipalArgumentResolver`. Conceptually, when a Controller has a parameter carrying this annotation:

1. `DispatcherServlet` has already selected the handler method.
2. Spring MVC invokes its `HandlerMethodArgumentResolver`s to produce the value for each parameter.
3. The resolver for `@AuthenticationPrincipal` looks up the current `Authentication` from `SecurityContextHolder`.
4. If an authentication is present, the resolver calls `authentication.getPrincipal()`.
5. If the annotation declares `expression`, the resolver evaluates the SpEL expression against that principal.
6. The mapped value is checked against the parameter's Java type; if compatible, it is passed to the method, otherwise it is handled according to `errorOnInvalidType`.

**There is no second credential-verification step** here. For example, a Bearer token with an invalid signature must be rejected by `JwtDecoder` in the Spring Security filters before the controller ever has a chance to run.

### How the Annotation Differs from @RequestParam and @RequestBody

~~~java
public ResponseEntity<?> example(
    @RequestParam String username,
    @AuthenticationPrincipal AppPrincipal currentUser) {
    // username: client-supplied data (not a verified identity).
    // currentUser: obtained from the security context (if properly authenticated).
    return ResponseEntity.ok().build();
}
~~~

This is an illustrative fragment; imports such as `ResponseEntity`, `RequestParam`, and other annotations must be present in a real class. Never treat `username` from a query string, form, or JSON body as proof of who the caller is. Use `currentUser` or a verified authorization result when executing queries belonging to "me".

## 4. Three Ways to Obtain Identity Information in a Controller

### 4.1. Obtaining the Principal with @AuthenticationPrincipal

~~~java
@GetMapping("/me")
public String me(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

This snippet is valid **when the principal actually implements `UserDetails`** and the request is required to be authenticated. If the authentication carries a `Jwt` or `OidcUser` principal that is incompatible with `UserDetails`, the parameter may be `null` (under the annotation's default setting) or throw a cast exception when `errorOnInvalidType=true` is enabled.

### 4.2. Obtaining java.security.Principal or Authentication

~~~java
@GetMapping("/me/name")
public String name(java.security.Principal principal) {
    return principal.getName();
}
~~~

This is a simple approach when you only need the name and do not care about the concrete principal class. A method can also accept `Authentication authentication` to retrieve authorities or other information via Spring Security/MVC integration. Remember that `Authentication.getName()` depends on the implementation: for JWT it usually relates to `sub`, whereas for `UserDetails` it usually relates to the username.

### 4.3. Obtaining the Full SecurityContext or Authentication

~~~java
@GetMapping("/me/authorities")
public List<String> authorities(Authentication authentication) {
    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .sorted()
        .toList();
}
~~~

This is a controller fragment requiring `Authentication` and `GrantedAuthority` imports. Choose this option when you genuinely need authentication metadata. Never serialize an entire `Authentication` or `UserDetails` directly into a JSON response, as the object may contain credentials, claims, session details, or information that does not belong in the API contract.

**Rule of thumb:** need the "who is calling" object → `@AuthenticationPrincipal`; only need the name → `Principal`; need authorities/authentication metadata → `Authentication` or `@CurrentSecurityContext`.

## 5. Two Important Attributes of @AuthenticationPrincipal

The annotation lets you select a value from the principal and decide how type mismatches are handled.

### 5.1. expression: Property Mapping with SpEL

Example with a custom principal that exposes `getId()`:

~~~java
@GetMapping("/me/id")
public Map<String, String> currentId(
        @AuthenticationPrincipal(expression = "id") UUID id) {
    return Map.of("id", id.toString());
}
~~~

The resolver evaluates the `id` expression with the **principal as the root object**, equivalent to reading the `getId()` getter. The result can be a `UUID` rather than the whole `AppPrincipal`. This is an example of extracting **a property from the authenticated principal**, not reading an `id` request parameter.

Some expressions depend on the principal type:

~~~java
// Only applies when the principal is a Jwt with a tenant_id claim:
@AuthenticationPrincipal(expression = "claims['tenant_id']")
String tenantId

// Only applies when the principal is an OAuth2User with attributes.email:
@AuthenticationPrincipal(expression = "attributes['email']")
String email
~~~

The two lines above are **parameter fragments**, not complete Java methods. `Jwt.getClaims()` exposes the `claims` property; `OAuth2User.getAttributes()` corresponds to `attributes`. When a claim is missing or is not of type `String`, you must handle it with an explicit policy and never infer a valid identity from an optional field.

**SpEL note:** expressions are hardcoded by the developer in source code and must never be constructed from client-supplied request input. Keep expressions simple and side-effect-free; avoid invoking methods that mutate state or trigger unintended data queries.

### 5.2. errorOnInvalidType: Choosing null vs. a Cast Error

When `expression` is not used, or after the expression produces a result, a type mismatch can occur. By the annotation's contract:

- `errorOnInvalidType = false` (default): if the principal/result cannot be assigned to the parameter type, the resolver can return `null`.
- `errorOnInvalidType = true`: if the value has an incompatible type, the resolver throws `ClassCastException` so misconfigurations are caught early.
- If **there is no Authentication or no principal**: you typically receive `null`. Setting `errorOnInvalidType=true` does not automatically turn a public endpoint into an authenticated endpoint.
- If **the SpEL expression itself fails** due to a missing getter/claim or wrong data type, that is an expression evaluation error, not something `errorOnInvalidType=false` is guaranteed to swallow in all cases.

Fail-fast example for a protected area:

~~~java
@GetMapping("/api/me")
public MeResponse me(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        AppPrincipal principal) {
    // Wrong principal type (e.g., a JWT in a chain expecting AppPrincipal)
    // will surface during argument resolution instead of silently returning null.
    return mapToResponse(principal);
}
~~~

This is an illustrative fragment; `mapToResponse` must be defined by the application. **Do not rely on `ClassCastException` occurring in production as a standard 401/403 flow**; design consistent security chains/principal types and test each login mechanism. This attribute is not a substitute for authorization.

## 6. Complete Java 17+ / Spring Boot 3 Example: Custom Principal in MVC

The example includes one account, `alice`, using HTTP Basic to demonstrate that the password is verified before the controller receives the principal. We will configure Spring Security to create an authentication whose principal is an **`AppPrincipal` containing an internal UUID**, and then use `@AuthenticationPrincipal` to return a safe DTO.

**Run in a learning environment only.** The example password is a hardcoded value; HTTPS and secret/IdP management must be designed separately for production. The project uses Maven and Spring Boot 3.3.5 as a **specific released reference version**, without claiming it is the latest version.

### 6.1. Project Structure

~~~text
principal-demo/
  pom.xml
  src/
    main/
      java/com/example/principaldemo/
        PrincipalDemoApplication.java
        AppPrincipal.java
        CurrentUser.java
        SecurityConfiguration.java
        ProfileController.java
    test/
      java/com/example/principaldemo/
        ProfileControllerTest.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>principal-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Requires JDK 17+ and Maven with normal access to download dependencies from the repository. `spring-boot-starter-security` provides Spring Security web and configuration; MVC integration resolves `@AuthenticationPrincipal` when security and Spring MVC are properly wired. There is no need to call `SecurityContextHolder` manually in the controller in this example.

### 6.3. Main Application

**`src/main/java/com/example/principaldemo/PrincipalDemoApplication.java`:**

~~~java
package com.example.principaldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrincipalDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }
}
~~~

### 6.4. Custom Principal with Internal ID

**`src/main/java/com/example/principaldemo/AppPrincipal.java`:**

~~~java
package com.example.principaldemo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public final class AppPrincipal implements UserDetails {

    private static final long serialVersionUID = 1L;

    private final UUID id;
    private final String username;
    private final String passwordHash;
    private final Collection<? extends GrantedAuthority> authorities;

    public AppPrincipal(
            UUID id,
            String username,
            String passwordHash,
            Collection<? extends GrantedAuthority> authorities) {
        this.id = Objects.requireNonNull(id);
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.authorities = List.copyOf(authorities);
    }

    // SpEL expression = "id" will access this getter.
    public UUID getId() {
        return id;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

**Why use a DTO in the controller instead of returning AppPrincipal directly?** A `UserDetails` exposes `getPassword()` for authentication purposes. If you pass the raw principal to a JSON serializer, you risk leaking the password hash and server-only attributes. The response DTO only contains the **ID, username, and authorities permitted to be exposed** in the demo API. Real applications must minimize the permissions and IDs returned to clients according to requirements.

`getId()` returns an internal UUID distinct from `getUsername()`; this avoids using mutable emails/usernames as primary keys for business records. In multi-tenant systems, the internal ID must be paired with proper tenant and authorization checks.

### 6.5. SecurityConfiguration: Basic Authentication and Creating Authentication

**`src/main/java/com/example/principaldemo/SecurityConfiguration.java`:**

~~~java
package com.example.principaldemo;

import java.util.List;
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        // DelegatingPasswordEncoder defaults to a secure algorithm
        // under the current configuration, e.g., bcrypt for new passwords.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        AppPrincipal alice = new AppPrincipal(
            UUID.fromString("11111111-1111-4111-8111-111111111111"),
            "alice",
            encoder.encode("demo-pass-123"),
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        return username -> {
            if (!alice.getUsername().equals(username)) {
                throw new UsernameNotFoundException("Unknown account");
            }
            return alice;
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Keep default CSRF; this example only has GET endpoints.
            .build();
    }
}
~~~

**Explanation:**

1. `UserDetailsService` returns **AppPrincipal**. When HTTP Basic verifies the password via the authentication provider, the principal in the resulting authentication is typically this custom `UserDetails`.
2. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces a password hash prefixed with its scheme, avoiding storing plain passwords in `UserDetails`. The demo password in source code is for learning only; production uses an identity store and secret management.
3. `anyRequest().authenticated()` requires authentication on all paths except `/api/public`. **This is the endpoint protection rule**; `@AuthenticationPrincipal` does not decide whether a request is allowed to reach the controller.
4. `formLogin` is disabled in the example only to focus on Basic; this does not imply disabling form login in other applications.
5. `SessionCreationPolicy.STATELESS` reduces reliance on Spring Security's HTTP session. It does not by itself make endpoints safe against CSRF when a browser automatically sends credentials. For cookies/form login or Basic credentials cached and sent automatically by browsers, evaluate CSRF before removing protection. The example only uses GET endpoints and does not call `csrf.disable()`.
6. There is no need to construct `Authentication` in the controller or set `SecurityContextHolder` manually. That is the responsibility of Spring Security filters and authentication providers.
7. The example has a single `UserDetailsService` and a single `PasswordEncoder` bean; the default configuration suits username/password authentication. When multiple providers or filter chains exist, verify that `AuthenticationManager` is wired properly.

### 6.6. Creating a Meta-Annotation for Consistent Usage

In larger codebases, teams can use `@CurrentUser` instead of repeating a verbose annotation in every controller. Spring Security supports using `@AuthenticationPrincipal` as a meta-annotation.

**`src/main/java/com/example/principaldemo/CurrentUser.java`:**

~~~java
package com.example.principaldemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.core.annotation.AuthenticationPrincipal;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal(errorOnInvalidType = true)
public @interface CurrentUser {
}
~~~

`@CurrentUser` does not authenticate users on its own and does not create a new security filter. It simply standardizes how the **principal is injected** into controllers and makes the parameter's intent clear in API code. This annotation **assumes** every endpoint using it has a principal of type `AppPrincipal`. Do not reuse the same annotation on a chain that only produces a `Jwt` principal without changing the contract.

### 6.7. Controller with Three Mapping Styles

**`src/main/java/com/example/principaldemo/ProfileController.java`:**

~~~java
package com.example.principaldemo;

import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo(
            @AuthenticationPrincipal AppPrincipal user) {
        // permitAll endpoint: with an anonymous principal not of type
        // AppPrincipal, the default resolver may pass null.
        return Map.of("viewer", user == null ? "guest" : user.getUsername());
    }

    @GetMapping("/api/me")
    public MeResponse me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AppPrincipal currentUser) {

        List<String> authorities = currentUser.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new MeResponse(
            currentUser.getId(),
            currentUser.getUsername(),
            authorities
        );
    }

    @GetMapping("/api/me/id")
    public Map<String, String> id(
            @AuthenticationPrincipal(
                expression = "id",
                errorOnInvalidType = true)
            UUID currentUserId) {

        return Map.of("id", currentUserId.toString());
    }

    @GetMapping("/api/me/alias")
    public Map<String, String> alias(@CurrentUser AppPrincipal user) {
        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/me/name")
    public Map<String, String> principalName(Principal principal) {
        return Map.of("username", principal.getName());
    }

    public record MeResponse(
        UUID id,
        String username,
        List<String> authorities) {
    }
}
~~~

Explanation of the key techniques:

- **Whole object:** `@AuthenticationPrincipal AppPrincipal currentUser` receives Spring Security's custom principal.
- **Single property:** `@AuthenticationPrincipal(expression="id") UUID currentUserId` instructs the resolver to read `getId()` on the principal and pass it as the parameter.
- **Meta-annotation:** `@CurrentUser AppPrincipal user` uses the same resolver while following a codebase convention.
- **Without the annotation:** `Principal principal` provides the name via Servlet/Spring Security integration when only an identifier string is needed.
- **Anonymous:** `/api/public` allows unauthenticated access, so it must handle a `null` or mismatched principal instead of calling getters unconditionally.

Representative response for `GET /api/me` with valid demo credentials:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

The JSON above is a **representative output of the demo controller** and does not guarantee identical whitespace, property ordering, or headers across all environments.

### 6.8. Running the Project and Observing HTTP Behavior

Requires JDK 17+, Maven, and network access to download dependencies on the first run. In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Call the public endpoint:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Example body:

~~~json
{"viewer":"guest"}
~~~

Call a protected endpoint **without sending credentials**:

~~~bash
curl -i http://localhost:8080/api/me
~~~

**Expected:** HTTP `401 Unauthorized`, typically with `WWW-Authenticate: Basic …`. The body/error page depends on the server and error handling configuration.

Send demo credentials:

~~~bash
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/id
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/alias
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/name
~~~

Expected results respectively: profile JSON containing UUID/username/authority; the `id` endpoint returns the UUID; `alias` and `name` return `alice`. On PowerShell, use `curl.exe` if `curl` is aliased to another cmdlet; avoid putting real passwords in shell history and process lists. **HTTP Basic must go over HTTPS when used with real credentials.**

Do not attempt to turn this demo into a production account management system by adding new passwords in source code; you need a proper user store, hashing, policies, rate limiting, and auditing tailored to your application.

## 7. Testing Spring MVC: Real Values Come from Authentication

These tests include the Spring Security filter chain and send Basic credentials so requests actually pass through the authentication provider. Do not mock a different principal type and conclude that `AppPrincipal` was created properly.

**`src/test/java/com/example/principaldemo/ProfileControllerTest.java`:**

~~~java
package com.example.principaldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCanAccessPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.viewer").value("guest"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordDoesNotCreateCurrentUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bindsCustomPrincipalAndSafeProfile() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.id").value(
                "11111111-1111-4111-8111-111111111111"))
            .andExpect(jsonPath("$.authorities[0]").value(
                "ROLE_READER"));
    }

    @Test
    void extractsPrincipalPropertyWithSpel() throws Exception {
        mvc.perform(get("/api/me/id")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(
                "11111111-1111-4111-8111-111111111111"));
    }

    @Test
    void metaAnnotationResolvesSameCurrentUser() throws Exception {
        mvc.perform(get("/api/me/alias")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void servletPrincipalNameIsAvailable() throws Exception {
        mvc.perform(get("/api/me/name")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }
}
~~~

These tests verify:

1. `permitAll` still allows public access and the controller handles anonymous callers.
2. Protected endpoints without authentication return 401; wrong passwords also return 401.
3. The authentication provider retrieves the right `AppPrincipal` from `UserDetailsService`.
4. `@AuthenticationPrincipal` maps the object of the right type, SpEL `id`, and meta-annotation properly.
5. `Principal.getName()` works when Spring Security/Servlet integration is properly wired.

**Limitations:** these are example tests in a Spring Boot project. There is no fixed Maven output since different environments print different logs. These tests **do not prove** that a JWT has its signature verified, that an OAuth2/OIDC flow is configured properly, or that a backend resists header spoofing behind a proxy; dedicated tests are needed for each mechanism.

### Why Not Just Use @WithMockUser?

`@WithMockUser(username="alice")` or MockMvc `.with(user("alice"))` is useful when testing authorization policies, but it usually creates a principal of Spring Security's `User`/mock user type, **not the demo's custom AppPrincipal**. If the controller expects `AppPrincipal`, tests easily receive `null` or `ClassCastException`. To test custom principal mapping, use realistic HTTP Basic as shown above, or construct an `Authentication` with a principal of the **exact class**.

This also explains why a `@WebMvcTest` controller slice test without a fully wired resolver might not reflect the production security chain. Verify that Spring Security filters are applied to MockMvc and that the principal type matches the real application.

## 8. When the Principal Is Jwt, OAuth2User, or OidcUser

There is no single Java principal type across all authentication mechanisms. Under different configurations, the same annotation may require a different parameter type.

### 8.1. OAuth2 Resource Server with JWT

If the app configures `oauth2ResourceServer(oauth2 -> oauth2.jwt(…))`, `JwtAuthenticationToken` typically carries a principal of type `org.springframework.security.oauth2.jwt.Jwt`.

~~~java
@GetMapping("/api/jwt/me")
public Map<String, String> jwtMe(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("subject", jwt.getSubject());
}
~~~

This is a **fragment for a Resource Server application with a configured JWT decoder**; do not paste it directly into the HTTP Basic project in section 6. `JwtDecoder` must validate signature, issuer, timestamps, and audience according to policy before a token is considered authenticated. `@AuthenticationPrincipal Jwt` merely receives the JWT object **after the decoder succeeds** and performs no validation of its own.

You can map a single claim:

~~~java
@GetMapping("/api/jwt/tenant")
public Map<String, String> tenant(
        @AuthenticationPrincipal(
            expression = "claims['tenant_id']")
        String tenantId) {
    return Map.of("tenantId", tenantId);
}
~~~

This is an illustrative fragment. `tenant_id` must exist, be a string, and be issued/verified by the issuer per contract. `Map.of` does not accept `null` values; production code must handle missing claims with an explicit policy. **Never obtain a tenant from a claim that has not been verified by the decoder and token validator.**

In addition, `aud` and `scope` must still be enforced according to Resource Server policy. Knowing `sub` alone is not sufficient to decide whether a user can read all records of a tenant.

### 8.2. OAuth2 Login

With `oauth2Login()`, the principal is usually an `OAuth2User` and identity attributes may live inside `attributes`:

~~~java
@GetMapping("/account/oauth")
public Map<String, String> oauth(
        @AuthenticationPrincipal OAuth2User oauthUser) {
    return Map.of("name", oauthUser.getName());
}
~~~

This fragment uses `org.springframework.security.oauth2.core.user.OAuth2User`. `getName()` depends on the configured provider/user-name attribute; it may be a provider-specific ID rather than an email address. When mapping to an internal account, use a mapping service keyed by issuer/provider + stable subject rather than equating accounts by email automatically.

### 8.3. OpenID Connect Login

With OIDC login, the principal can be an `OidcUser`:

~~~java
@GetMapping("/account/oidc")
public Map<String, String> oidc(
        @AuthenticationPrincipal OidcUser user) {
    return Map.of("subject", user.getSubject());
}
~~~

This fragment uses `org.springframework.security.oauth2.core.oidc.user.OidcUser`. In OIDC, the subject must be scoped to its **issuer**, not treated as a globally unique ID string. Do not expose raw ID tokens or sensitive full claims in responses.

### 8.4. Principal Type Selection Table

| Common Authentication Type | Typical Principal | Parameter Type for @AuthenticationPrincipal |
| --- | --- | --- |
| Basic/form + `UserDetailsService` | `UserDetails`, custom user | `UserDetails` or corresponding custom class |
| JWT Resource Server | `Jwt` | `Jwt` or SpEL property/claim |
| Opaque token Resource Server | `OAuth2AuthenticatedPrincipal` | Corresponding principal/interface |
| OAuth2 login | `OAuth2User` | `OAuth2User`, custom OAuth2User |
| OIDC login | `OidcUser` | `OidcUser`, custom OIDC principal |
| Anonymous request | Typically string `anonymousUser` in `AnonymousAuthenticationToken` | When expecting `AppPrincipal`, usually null; must account for public endpoints |

The corresponding classes and dependencies must exist in the respective application. You cannot copy a `Jwt` fragment into an HTTP Basic project and expect Spring to synthesize a JWT principal.

## 9. When Should You Map to a Domain User Object?

A clean design separates these concerns:

~~~text
Authentication principal (authenticated)
        |
        | stable internalId / issuer+subject
        v
Application user lookup / authorization service
        |
        | verify tenant, account status, object permissions
        v
Domain User / business entity
        |
        v
DTO for response
~~~

Benefits:

- `UserDetails`/`Jwt` retains authentication responsibility; JPA entities retain persistence responsibility.
- You can change login mechanisms without rewriting every data-handling service.
- It is easier to avoid leaking password hashes, token claims, and security session details during serialization.
- You can check current account status, roles, tenant, and object-level policies instead of relying on stale principal data.

A controller following this pattern can pass the authenticated ID to a service:

~~~java
@GetMapping("/api/my-orders")
public List<OrderResponse> myOrders(
        @AuthenticationPrincipal(expression = "id") UUID accountId) {
    return orderService.findVisibleOrdersFor(accountId);
}
~~~

**This is an architectural fragment**, requiring `OrderResponse`, `orderService`, imports, and real methods; it is not part of the demo project in section 6. `findVisibleOrdersFor` must still enforce permissions, tenant isolation, and object ownership. If a service accepts a plain `accountId` from other callers, it cannot assume every caller was authenticated by a controller.

### Avoiding IDOR

Do not use:

~~~java
@GetMapping("/api/users/{userId}/orders")
public List<OrderResponse> unsafe(@PathVariable UUID userId) {
    return orderService.findAllFor(userId);
}
~~~

if the logic relies solely on the client-supplied `userId` to decide whose data can be viewed. This fragment illustrates an anti-pattern. For "my orders" endpoints, obtain the current subject from a trusted principal. For admin endpoints reading someone else's orders, enforce **explicit authorization** for the current actor on the target user/tenant.

**@AuthenticationPrincipal only helps retrieve a trusted actor; it does not perform object-level authorization.**

## 10. Anonymous Users, Null Principals, and Cast Errors

### 10.1. permitAll Endpoints

On public endpoints, Spring Security commonly creates an `AnonymousAuthenticationToken` with a principal of type `String` (`"anonymousUser"`). If a method expects `AppPrincipal`, the default resolver may pass `null`. Nothing is wrong here: the endpoint does not require login.

~~~java
@GetMapping("/api/greeting")
public String greet(@AuthenticationPrincipal UserDetails current) {
    return current == null ? "Hello guest" :
            "Hello " + current.getUsername();
}
~~~

This snippet is a fragment. On endpoints that must be authenticated, use `.authenticated()` to require a valid authentication before the controller touches the principal.

### 10.2. isAuthenticated Is Not Enough to Identify a Real End-User

`AnonymousAuthenticationToken` in Spring Security can report `isAuthenticated() == true` as part of its internal token design. Therefore, do not write policies like "if `auth.isAuthenticated()`, the user is logged in" without distinguishing anonymous, remember-me, and fully authenticated users. Use authorization request matchers such as `authenticated()`, `fullyAuthenticated()`, or `AuthenticationTrustResolver` according to your security requirements. The `@AuthenticationPrincipal` parameter by itself does not handle this distinction.

### 10.3. Multiple SecurityFilterChains and Type Mismatches

If `/api/**` accepts JWTs while `/admin/**` uses form login, the principal can have two different types. A controller reusing a shared `@CurrentUser AppPrincipal` may fail on the JWT chain. Design a unified mapping strategy, or use controllers/annotations appropriate for each chain. In a multi-auth application, you can build a service that normalizes the authenticated actor from trusted authentication types and test every path; **never assume every Object principal is an AppPrincipal**.

### 10.4. SpEL Missing a Property

If you use `expression = "id"` on a principal lacking a `getId()` getter, SpEL may throw an error because the property is not found; `errorOnInvalidType=false` does not guarantee suppressing expression errors. Whenever you change a principal class, test injection/expressions and preserve the API contract.

## 11. Interaction with Authorization, Method Security, and CSRF

### Authorization Must Run Before Relying on the Principal

Configuring `requestMatchers("/api/me").authenticated()` ensures only authenticated users can invoke the endpoint. If an endpoint requires specific permissions, add policies such as `hasAuthority("ROLE_READER")` or method security in the service layer, as required. Do not rely on the presence of an annotated parameter to protect a URL.

In Spring Security 6, you can use `@EnableMethodSecurity` and `@PreAuthorize` on services to protect operations, provided evaluators/permissions are designed properly and clients are never allowed to supply the actor ID themselves. The scope of this lesson is **mapping the principal into MVC methods**, not a complete guide to method-level authorization.

### CSRF Is a Separate Concern

`@AuthenticationPrincipal` reads authentication; it does not check CSRF tokens. A browser may automatically attach session cookies or Basic credentials in certain contexts; state-changing HTTP methods require CSRF protection according to your threat model. Never disable CSRF just because a controller already has a principal or because the app is "stateless" in Spring Security. For Bearer-only APIs that do not rely on ambient browser credentials, the CSRF policy may differ; evaluate the authentication mechanism carefully.

### Do Not Construct Authentication Inside a Controller

Code like `SecurityContextHolder.getContext().setAuthentication(...)` inside a controller just to "make @AuthenticationPrincipal work" is a sign of misconfiguration. Users must be authenticated by filters/authentication managers before the request reaches the controller. Setting a principal manually from request parameters creates an authentication bypass vulnerability.

## 12. Trust Boundaries and Sensitive Information

### 12.1. The Principal Comes from SecurityContext, but You Must Know Who Created It

`@AuthenticationPrincipal` trusts whatever is inside `SecurityContext`. If a project has a custom filter that takes `X-User: admin` from an HTTP header and sets authentication without verifying the proxy/transport, the annotation will dutifully return that forged "admin". The resolver cannot fix an untrusted authentication pipeline.

If an authenticating proxy sits in front, the backend must block bypass paths, verify the trusted proxy/service identity, strip client-supplied headers, and attach identity only after the proxy has authenticated the caller. Or use a digitally signed JWT assertion whose issuer/audience/signature/timestamps the backend verifies, depending on the architecture.

### 12.2. Avoid Logging and Serializing the Entire Principal

A principal may carry password hashes, internal authorities, JWT claims, tokens, or personally identifiable information. Never return `Authentication`, `Jwt`, or a JPA entity directly from a public API. Return only DTOs containing permitted fields. Do not log tokens or credentials; when debugging type mismatches, log the class name and a sanitized request ID rather than dumping the entire object.

### 12.3. A Principal Can Be Staler Than Current Data

If an account is disabled, changes roles, or moves tenants after a token or session is issued, the request's principal may reflect stale state depending on authentication and caching strategies. For sensitive permissions, the backend may need to look up the latest user/entitlement state or combine short token lifetimes, revocation, and consistent policies.

### 12.4. Async/Thread Context Does Not Propagate Everywhere Automatically

Spring MVC requests run within a security context; however, `@Async` work, executor threads, or queue consumers do not inherit the same `SecurityContext` by default in every scenario. Do not try to use `@AuthenticationPrincipal` on ordinary service methods or background workers — it is an **MVC argument resolver**. Pass a verified `accountId` into the service, or use Spring Security's context propagation mechanisms when truly needed.

## 13. Common Errors and Diagnostic Table

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `@AuthenticationPrincipal UserDetails` is always null despite successful login | Actual principal is `Jwt`/`OAuth2User`/custom type or unauthenticated. | Inspect `authentication.getPrincipal().getClass()` with safe logging; choose the right type. |
| `errorOnInvalidType=true` throws ClassCastException | Principal type is incompatible with parameter type. | Right security chain and principal class? Add tests. |
| `expression="id"` fails SpEL | Principal lacks `getId()` getter or expression is wrong. | Check class and expression; test the code path. |
| Public endpoint throws NullPointerException | `permitAll` does not guarantee an application principal type. | Handle null or require authenticated access before calling getters. |
| Response accidentally exposes password hash | Returning `UserDetails` or authentication object directly. | Create a minimal DTO; never serialize secrets. |
| `@AuthenticationPrincipal Jwt` is null with Basic | Principal is `UserDetails`, not `Jwt`. | Use the matching authentication mechanism or mapper. |
| Annotation does not work in MVC tests | Test skips security filters/resolver or mocks another principal type. | Use `@SpringBootTest + @AutoConfigureMockMvc` or configure mocks properly. |
| `@WithMockUser` does not bind AppPrincipal | Mock user is not the custom principal. | Use the real Basic provider or a custom Authentication. |
| `@AuthenticationPrincipal` mistaken for authorization | The annotation does not check permissions. | Configure `authorizeHttpRequests`/method authorization. |
| `@AuthenticationPrincipal` yields admin when header is spoofed | Custom filter/proxy trusts raw header. | Check boundaries, network/mTLS, token validation, and ingress stripping. |
| Using `getName()` as a tenant key | Name is unstable or collides across IdPs/tenants. | Use issuer+subject or an internal stable ID. |
| Async service does not see SecurityContext | Context is not automatically propagated to other threads/jobs. | Pass actor ID explicitly or use proper context propagation. |
| Authenticated yet action still returns 403 | Missing authority, CSRF token, or object permission. | Distinguish validation/authentication/authorization/CSRF. |
| Returns 401 without hitting Controller breakpoint | SecurityFilterChain blocked the request before MVC. | Check security rules, credentials/decoder, and entry point. |

### Step-by-Step Debug Checklist

1. Confirm the request goes through the **right SecurityFilterChain** and the endpoint has the intended authentication policy.
2. Confirm login / JWT decoder produced a valid `Authentication` before the request reached the controller.
3. Inspect the type of `Authentication.getPrincipal()` and value of `Authentication.getName()` — log only filtered information, never dump tokens.
4. Check the Java type of the `@AuthenticationPrincipal` parameter and the SpEL expression (if any).
5. On public endpoints, handle `null`/anonymous callers; do not assume a user is always present.
6. If authorities/permissions are needed, use authorization policies and services rather than mistaking them for resolver properties.
7. Ensure DTOs contain no password hashes, credentials, tokens, or sensitive claims.
8. Write tests that actually exercise filters/authentication providers; add tests for anonymous, wrong credentials, mismatches, and multi-chain setups if applicable.

## 14. Applied Scenarios and Self-Check Questions

**Scenario A — "My orders."** A controller accepts both `@PathVariable UUID accountId` and `@AuthenticationPrincipal AppPrincipal user`. A customer edits `accountId` to someone else's, and the service does not check permissions. Is this safe?

**Answer:** No. Client-supplied parameters do not verify the actor. Use the principal ID to fetch the user's own resources, or perform explicit authorization checking whether the current actor may read the target account; do not rely on the annotation alone.

**Scenario B — App migrates to JWT Resource Server.** Previously the controller accepted `@AuthenticationPrincipal UserDetails user`, and after switching to JWT `user` becomes null. Why?

**Answer:** A JWT Resource Server typically stores a `Jwt` principal rather than `UserDetails`. You need `@AuthenticationPrincipal Jwt jwt` or a mapper layer that normalizes the verified JWT into an application principal.

**Scenario C — Public method.** A `permitAll` endpoint uses `@AuthenticationPrincipal(errorOnInvalidType=true) AppPrincipal` and an unauthenticated user calls it. Will Spring necessarily return 401 automatically?

**Answer:** No. The annotation does not create an authorization rule. For anonymous callers, the principal may not match and the resolver will not supply an `AppPrincipal`; the endpoint must handle null or change its policy to authenticated.

**Scenario D — SpEL.** Is `@AuthenticationPrincipal(expression="id") UUID id` safer than `@RequestParam UUID id` for identifying the caller?

**Answer:** With a trusted authentication pipeline, SpEL extracts the internal ID from the verified principal rather than a client-declared ID. However, the service must still enforce permissions/tenant isolation; the annotation does not replace business authorization.

**Scenario E — Testing.** `@WithMockUser("alice")` passes for an endpoint reading `Authentication.getName()` but fails for `@CurrentUser AppPrincipal`. Is this a framework bug?

**Answer:** Not necessarily. The mock principal is usually Spring Security's `User`, not a custom `AppPrincipal`. Tests must construct the right principal or go through the real authentication provider.

**Scenario F — Spoofed header.** The backend has a custom filter converting `X-User: admin` into an Authentication and the controller uses `@AuthenticationPrincipal`. Does the annotation make that header trustworthy?

**Answer:** No. The resolver merely reads whatever principal is already in the security context. You must establish a trust boundary with the gateway, block direct access, and/or verify assertions instead of trusting raw headers.

### Short Questions

1. **What object does `@AuthenticationPrincipal` read?** The `Authentication.getPrincipal()` value of the authentication currently placed in the security context by Spring Security.
2. **What should you use if you need all authorities?** `Authentication.getAuthorities()` or method security/authorization policies; this annotation primarily reads the principal.
3. **What does `expression="username"` do?** Evaluates the SpEL `username` property on the principal, typically calling `getUsername()` if present.
4. **Does `errorOnInvalidType=true` guarantee login authorization?** No; it only raises an error when the resolved value's type does not match.
5. **When the principal is a JWT, which class is appropriate?** Usually `org.springframework.security.oauth2.jwt.Jwt` in a JWT Resource Server.
6. **Does a `@CurrentUser` meta-annotation require a separate filter?** No; it reuses `AuthenticationPrincipalArgumentResolver`.
7. **Should you return a raw `UserDetails` from an API?** No; create a minimal DTO so credentials or internal fields are not exposed.
8. **Why do MockMvc tests need the right principal type?** Because the annotation extracts the real principal from the authentication in the test context; a mock `User` does not turn into a custom `AppPrincipal`.
9. **Does the annotation work in an `@Async` service?** It is not a general argument injection mechanism; it applies to MVC handlers. Async code needs the actor/context passed intentionally.
10. **If `Authentication.getPrincipal()` was created by an untrusted filter, can the annotation protect you?** No; you must fix the authentication mechanism and trust boundary.

**Conclusion:** `@AuthenticationPrincipal` is a tool for **mapping Spring Security's authenticated identity into MVC Controller parameters**. Used properly, it eliminates boilerplate `SecurityContextHolder` lookups, reduces manual casts, and simplifies building "current user" endpoints. However, **the principal type depends on the authentication mechanism**, SpEL requires valid getters/claims, anonymous callers can yield null, and every access decision must still rest on a **trusted authentication pipeline plus authorization at the URL, method, and business-object levels**.