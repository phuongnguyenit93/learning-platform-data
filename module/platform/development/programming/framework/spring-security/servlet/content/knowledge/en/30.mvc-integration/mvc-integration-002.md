# @CurrentSecurityContext and Reading Authentication in Spring MVC

## 1. Lesson Objectives

In Spring Security on the Servlet stack, Spring MVC controllers often need to know **who is making the request**, how the request was authenticated, and what authorities are present. Spring Security stores this information in **SecurityContext** and **Authentication**. The **@CurrentSecurityContext** annotation lets you obtain the SecurityContext, or extract properties inside it using Spring Expression Language (SpEL), directly as a controller method parameter.

After this lesson, you will be able to:
- Explain the SecurityContext lifecycle in a Servlet request.
- Use @CurrentSecurityContext to receive **SecurityContext** or **Authentication**; retrieve **authentication.name** and authorities.
- Compare it with **@AuthenticationPrincipal**, Java Servlet's **Principal**, and **SecurityContextHolder**.
- Distinguish logged-in users, anonymous users, and resource access permissions.
- Run examples with Java 17, Spring Boot 3.4.5, Spring MVC, MockMvc, and security tests.
- Avoid leaking Authentication data or using the wrong context during asynchronous processing.

**Scope:** Spring Security Servlet + Spring MVC. Do not mix with WebFlux reactive SecurityContext.

## 2. How Does SecurityContext Hold Authentication?

**SecurityContext** is the object holding the active **Authentication**. In code:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

**Authentication** represents the principal and authentication state of the request. Key APIs:

| Method | Meaning | Notes |
| --- | --- | --- |
| getName() | Identifier name of the principal provided by the provider | Not guaranteed to always be an email or username |
| getPrincipal() | Actual principal | Can be UserDetails, Jwt, OidcUser, String... |
| getAuthorities() | GrantedAuthority: ROLE_USER, ROLE_ADMIN, SCOPE_read... | Does not replace per-resource ownership checks |
| isAuthenticated() | Status of the Authentication implementation | **AnonymousAuthenticationToken can return true** |
| getCredentials() | Mechanism-specific credentials data | Do not log, return in JSON, or persist to a database |
| getDetails() | Supplementary info such as web request details | May contain sensitive data |

A SecurityContext can **exist with a null Authentication**. On unauthenticated requests, the anonymous filter may set an **AnonymousAuthenticationToken** to represent an anonymous user. Therefore, checking **authentication != null** or **authentication.isAuthenticated()** is **not sufficient** to know whether a user is genuinely logged in.

Authentication data is not self-declared by the client: it must come from properly configured authentication filters/providers. For example, HTTP Basic decodes credentials and verifies them against UserDetailsService; a JWT Resource Server validates the token according to policy; OIDC login verifies the authentication result from the identity provider.

### Authentication Is Not Authorization

A request with principal alice and ROLE_USER is not necessarily permitted to view bob's orders. **Authentication** answers who is calling; **authorization** decides whether access to an endpoint and a **specific resource** is allowed. A controller that reads Authentication must never bypass SecurityFilterChain, method security, or resource ownership checks.

## 3. When Is SecurityContext Created and Retrieved?

Basic flow:

~~~text
HTTP request
     |
     v
Servlet container
     |
     v
Spring Security FilterChainProxy
     |-- SecurityContextHolderFilter / context lifecycle
     |-- Authentication filters: Basic, form, JWT, OIDC...
     |-- AuthenticationManager / AuthenticationProvider
     |-- AuthorizationFilter
     |
     v
DispatcherServlet
     |
     +-- Select @RestController method
     +-- Argument resolver for @CurrentSecurityContext
     |
     v
Controller receives SecurityContext or Authentication
~~~

When Spring MVC invokes a controller, the current SecurityContext is supplied by Spring Security via **SecurityContextHolder**. The **@CurrentSecurityContext** annotation uses argument resolution to inject SecurityContext into the method. It **does not perform login itself** and does not verify passwords, JWT signatures, or OAuth2 authorization codes.

Under the default Servlet strategy, SecurityContextHolder binds context to the current **thread**, typically using a ThreadLocal. Depending on configuration, SecurityContext may be loaded from a session or constructed fresh per request in a stateless token model. At the end of the request, the security infrastructure is responsible for clearing the context so the thread can be safely reused.

**Do not assume** that because a controller can read Authentication, the application is using HttpSession: stateless JWT APIs also create a per-request SecurityContext.

## 4. @CurrentSecurityContext Syntax

Annotation:

~~~java
import org.springframework.security.core.annotation.CurrentSecurityContext;
~~~

### 4.1. Receiving the Full SecurityContext

~~~java
@GetMapping("/api/me")
String me(@CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth.getName();
}
~~~

### 4.2. Receiving Authentication via SpEL

~~~java
@GetMapping("/api/me/auth")
String authName(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
~~~

### 4.3. Receiving the Username Directly

~~~java
@GetMapping("/api/me/name")
String name(
        @CurrentSecurityContext(
                expression = "authentication.name") String name) {
    return name;
}
~~~

The snippets above are **method fragments** and must be placed inside a `@RestController` with an appropriate security configuration. The complete project is in section 7.

**Important point about expression:** The SpEL root in `@CurrentSecurityContext` is **SecurityContext**, not Authentication itself. Therefore:
- **expression = "authentication"** accesses `SecurityContext.getAuthentication()`.
- **expression = "authentication.name"** accesses `Authentication.getName()`.
- **expression = "authentication.principal"** accesses the runtime principal.
- **expression = "authentication.authorities"** accesses authorities.

Do not confuse this with **@AuthenticationPrincipal**, where the injected target is the principal and any expression is evaluated according to that annotation's resolver mechanism.

The annotation provides an **errorOnInvalidType** option; if the method parameter type does not match the expression result, test the behavior appropriately. Do not cast a `Jwt` principal to `UserDetails` just because a legacy application used `UserDetails`.

## 5. Comparing Ways to Obtain Identity in a Controller

| Usage | Purpose | Limitations |
| --- | --- | --- |
| @CurrentSecurityContext SecurityContext | Obtain full context | Still need to read Authentication and handle anonymous/null when needed |
| @CurrentSecurityContext(expression = "authentication") Authentication | Obtain Authentication directly | Should not serialize Authentication into JSON |
| @CurrentSecurityContext(expression = "authentication.name") String | Obtain name from Authentication | No guarantee that name is an email or immutable identifier |
| @AuthenticationPrincipal UserDetails | Obtain principal; suitable for UserDetails | Type mismatch if principal is Jwt, OidcUser, or String |
| java.security.Principal | Obtain principal name per MVC/Servlet | Not a full API for authorities |
| SecurityContextHolder.getContext() | Imperative access in layers without argument resolvers | Depends on request thread / context propagation |

Example with `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/profile")
String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

In HTTP Basic or form login backed by `UserDetailsService`, the principal is typically `UserDetails`. In an OAuth2 Resource Server with JWT, the principal is typically **Jwt**; with OIDC Login it is typically **OidcUser**; with anonymous callers it may be a `String`. Thus, the code above is **only valid when the authentication mechanism is known**.

Example using the servlet request:

~~~java
@GetMapping("/api/who")
String who(HttpServletRequest request) {
    Principal principal = request.getUserPrincipal();
    return principal == null ? "guest" : principal.getName();
}
~~~

This snippet requires importing **jakarta.servlet.http.HttpServletRequest** and **java.security.Principal**. When you need authorities and the Authentication type, `@CurrentSecurityContext` is more direct.

Never trust **X-User**, **X-Authenticated-User**, or query parameters as identity unless you have a pre-authentication architecture with a trusted gateway and anti-header-spoofing protections. Caller-supplied headers do not by themselves prove who the caller is.

## 6. Anonymous Does Not Mean Logged-In User

A very common security mistake:

~~~java
// Not sufficient to conclude this is a genuinely logged-in user.
if (authentication != null && authentication.isAuthenticated()) {
    // ...
}
~~~

`AnonymousAuthenticationToken` can return `isAuthenticated() = true` even though its principal is typically **anonymousUser**. Spring Security distinguishes anonymous, remember-me, and fully authenticated users through its framework mechanisms.

If you only need to display status, you can use `AuthenticationTrustResolver`:

~~~java
AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

boolean loggedIn = authentication != null
        && !trustResolver.isAnonymous(authentication);
~~~

This is a **fragment** requiring `AuthenticationTrustResolver` and `AuthenticationTrustResolverImpl` imports. If you need stricter policies around remembered logins, understand remember-me and **fullyAuthenticated()**. For API protection, use **authorizeHttpRequests** or **@PreAuthorize** with **@EnableMethodSecurity** rather than an `if` check inside the controller.

On public endpoints, code reading the context must tolerate null/anonymous; on endpoints properly protected with **authenticated()**, the controller can expect a valid Authentication when the handler runs.

## 7. Complete Java 17 Example with Spring Boot 3 and MVC

The project uses **Java 17**, **Spring Boot 3.4.5**, Maven, Spring MVC, and Spring Security HTTP Basic. This is a simple setup for observing SecurityContext, not a production password configuration. The endpoints:

- **GET /public/ping** is a public endpoint illustrating anonymous access.
- **GET /api/me/context** receives the full SecurityContext and reads Authentication.
- **GET /api/me/name** uses the `authentication.name` expression.
- **GET /api/me/auth** receives Authentication.
- **GET /api/me/principal** uses `@AuthenticationPrincipal` for comparison.
- **GET /api/me/direct** uses `SecurityContextHolder`.
- **GET /api/admin** is restricted to `ROLE_ADMIN`.

Structure:

~~~text
mvc-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/mvcsecurity/MvcSecurityContextApplication.java
    └── test/java/demo/mvcsecurity/MvcSecurityContextTests.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-security-context-demo</artifactId>
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

### 7.2. Runnable Application File

Save to **src/main/java/demo/mvcsecurity/MvcSecurityContextApplication.java**. Java allows one public class alongside other package-private classes in a single file.

~~~java
package demo.mvcsecurity;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcSecurityContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSecurityContextApplication.class, args);
    }
}

@Configuration
class DemoSecurityConfiguration {
    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}password")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-password")
                        .roles("ADMIN", "USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {
    @GetMapping("/public/ping")
    Map<String, String> ping(
            @CurrentSecurityContext SecurityContext context) {
        Authentication a = context.getAuthentication();
        boolean guest = a == null
                || a instanceof AnonymousAuthenticationToken;
        return Map.of("viewer", guest ? "guest" : a.getName());
    }

    @GetMapping("/api/me/context")
    Map<String, Object> context(
            @CurrentSecurityContext SecurityContext context) {
        Authentication a = context.getAuthentication();
        List<String> authorities = a.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return Map.of(
                "name", a.getName(),
                "authenticationType", a.getClass().getSimpleName(),
                "authorities", authorities);
    }

    @GetMapping("/api/me/name")
    Map<String, String> name(
            @CurrentSecurityContext(
                    expression = "authentication.name") String username) {
        return Map.of("name", username);
    }

    @GetMapping("/api/me/auth")
    Map<String, Object> auth(
            @CurrentSecurityContext(
                    expression = "authentication") Authentication a) {
        return Map.of(
                "name", a.getName(),
                "authenticated", a.isAuthenticated());
    }

    @GetMapping("/api/me/principal")
    Map<String, String> principal(
            @AuthenticationPrincipal UserDetails user) {
        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/me/direct")
    Map<String, String> direct() {
        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
        return Map.of("name", a.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(
            @CurrentSecurityContext(
                    expression = "authentication.name") String name) {
        return Map.of("admin", name);
    }
}
~~~

**Important explanations:**

1. **SecurityFilterChain** defines who may call each endpoint. **GET /api/admin** requires `ROLE_ADMIN`; other API requests require `authenticated`; **GET /public/ping** allows anonymous access.
2. **HttpSecurity.httpBasic(...)** enables authentication via Basic credentials. The example uses `InMemoryUserDetailsManager` for easy testing.
3. **@CurrentSecurityContext SecurityContext** receives the context automatically without writing `SecurityContextHolder` in the controller; **expression = "authentication"** extracts Authentication.
4. **expression = "authentication.name"** returns the name supplied by Authentication. It does not query user records or prove an email is verified.
5. **@AuthenticationPrincipal UserDetails** works in this example because HTTP Basic authenticates against `UserDetailsService`. With JWT/OIDC, a different principal type may be needed.
6. **context()** only outputs `name`, `authenticationType`, and `authorities`. These are illustrative fields; in production you should also minimize exposed fields. **Do not return the entire Authentication** because it can contain credentials/details.
7. **AnonymousAuthenticationToken** illustrates why anonymous must be distinguished from authenticated. If an application disables anonymous or has multiple chains, the state can differ.
8. The project only has GET endpoints, so default CSRF is preserved. If you add POST/PUT/DELETE with browser cookie authentication, evaluate CSRF; do not disable it globally just for a demo.
9. **{noop}** and hardcoded passwords are for training environments only; production requires proper password encoding, HTTPS, secrets management, and credential policies.

### 7.3. Running and Observing Responses

From the root directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Once the application is running:

~~~bash
# Public request
curl -i http://localhost:8080/public/ping

# Without Basic credentials -> 401
curl -i http://localhost:8080/api/me/name

# Log in with the demo account
curl -i -u alice:password \
  http://localhost:8080/api/me/name

# Read SecurityContext and authorities
curl -i -u alice:password \
  http://localhost:8080/api/me/context

# Ordinary user is not allowed to access admin
curl -i -u alice:password \
  http://localhost:8080/api/admin

# Admin has permission
curl -i -u admin:admin-password \
  http://localhost:8080/api/admin
~~~

Expected results table:

| Request | Status | Meaning |
| --- | --- | --- |
| /public/ping, unauthenticated | 200 | Example JSON **{"viewer":"guest"}** |
| /api/me/name, unauthenticated | 401 | Protected endpoint, HTTP Basic challenge |
| /api/me/name, alice | 200 | Example **{"name":"alice"}** |
| /api/me/context, alice | 200 | Contains name, authenticationType, ROLE_USER |
| /api/admin, alice | 403 | Missing ROLE_ADMIN |
| /api/admin, admin | 200 | Example **{"admin":"admin"}** |

These are the **expected outputs of the example code** and should be verified in a real Java/Maven environment. Key ordering in JSON is not guaranteed. Never use demo passwords, Basic over HTTP, or commands that save credentials in shell history in production.

## 8. Testing with Spring Security Test and MockMvc

Spring Security provides **spring-security-test** to create simulated Authentication in MockMvc. Place the file at **src/test/java/demo/mvcsecurity/MvcSecurityContextTests.java**:

~~~java
package demo.mvcsecurity;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcSecurityContextTests {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReachPublicEndpoint() throws Exception {
        mvc.perform(get("/public/ping").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.viewer").value("guest"));
    }

    @Test
    void protectedEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me/name").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nameExpressionResolvesAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/me/name")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void contextContainsAuthority() throws Exception {
        mvc.perform(get("/api/me/context")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_USER"));
    }

    @Test
    void authenticationExpressionResolvesAuthentication()
            throws Exception {
        mvc.perform(get("/api/me/auth")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));
    }

    @Test
    void userDetailsPrincipalWorksWithTestUser() throws Exception {
        mvc.perform(get("/api/me/principal")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void ordinaryUserIsDeniedAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanUseAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void imperativeContextMatchesResolvedName() throws Exception {
        mvc.perform(get("/api/me/direct")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }
}
~~~

The test suite covers **9 test cases**, verifying public access, anonymous 401, 200 responses, authorities, UserDetails, 403 forbidden, and direct `SecurityContextHolder` access. Run:

~~~bash
mvn test
~~~

**Test limitations:** `.with(user(...))` attaches a simulated user to SecurityContext inside MockMvc; it does not verify passwords, test real HTTP Basic parsing, validate JWT signatures, or connect to an OIDC provider. If you need to exercise the HTTP Basic credential path, write tests using `spring-security-test`'s **httpBasic("alice", "password")** through the real filters. For JWT, add tests covering issuer/audience/expiry/signature and converters so mock principal tests are not mistaken for production token validation.

### 8.1. Why Are 401 and 403 Tests Different?

- **401 Unauthorized:** unauthenticated or rejected credentials; HTTP Basic typically sends `WWW-Authenticate`.
- **403 Forbidden:** user is authenticated but lacks sufficient permissions; e.g., `alice` has `ROLE_USER` while `/api/admin` requires `ROLE_ADMIN`.
- With browser `formLogin` or OAuth2 Login, an unauthenticated request may return a **302 redirect**, not necessarily 401.
- If a test unexpectedly returns 200 due to `@WithMockUser` or custom MockMvc setup, verify the intended security chain is running; never change an endpoint to `permitAll` just to "pass a test".

## 9. When the Application Replaces HTTP Basic with JWT/OIDC

**@CurrentSecurityContext** still reads SecurityContext regardless of where Authentication originated. However, the **principal type** and authorities can change.

| Mechanism | Typical Authentication | Typical Principal |
| --- | --- | --- |
| Username/password / HTTP Basic | UsernamePasswordAuthenticationToken | UserDetails |
| Resource Server JWT | JwtAuthenticationToken | Jwt |
| OAuth2/OIDC Login | OAuth2AuthenticationToken | OAuth2User or OidcUser |
| Pre-authenticated gateway | PreAuthenticatedAuthenticationToken | Depends on provider |
| Anonymous | AnonymousAuthenticationToken | Typically String anonymousUser |

With JWT, **getName()** usually relies on **sub** or a claim configured by `JwtAuthenticationConverter`, not necessarily an email. With OIDC, subject/issuer can be a more durable identifier than display name. **Do not store data ownership by email alone without establishing an identity contract across tenants and providers**.

If an endpoint genuinely needs JWT claims, you can use **@AuthenticationPrincipal Jwt jwt** (when the principal is a `Jwt`) or check whether Authentication is a `JwtAuthenticationToken`. Never cast `Authentication.getPrincipal()` to `UserDetails` in a JWT-backed API.

Short example using generic Authentication:

~~~java
@GetMapping("/api/current-subject")
String currentSubject(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
~~~

This is a controller fragment without full imports. It relies on the common **Authentication.getName()** contract, making it less coupled to a specific principal implementation.

If an application has **multiple SecurityFilterChains** (one chain for Bearer APIs and one for web login), check the order of **securityMatcher** rules. Spring Security selects the matching chain as configured; `@CurrentSecurityContext` only reads the outcome and cannot fix an API accidentally routed through a login chain.

## 10. Reading Authentication Does Not Replace Authorization

An anti-pattern:

~~~java
// WRONG: isAuthenticated does not prove the user has permission for the record.
if (authentication.isAuthenticated()) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Necessary safeguards:

1. Configure **authorizeHttpRequests** on the security filter chain; e.g., **hasRole("ADMIN")** requires `GrantedAuthority` **ROLE_ADMIN**.
2. If using method security, enable **@EnableMethodSecurity** and enforce **@PreAuthorize** per policy.
3. In services, check the record's **owner/tenant/ACL** against the verified principal ID.
4. Never trust roles sent by the client in headers, request parameters, or JSON.
5. Only read Authentication as input for a verified authorization decision.

In Spring Security, **hasAuthority("SCOPE_read")** matches `SCOPE_read` literally, whereas **hasRole("ADMIN")** prepends the `ROLE_` prefix by default. If an IdP mapper issues a different format, configure the converter and write tests rather than inferring permissions from name strings alone.

**Do not return the raw Authentication or SecurityContext as JSON.** These objects can contain credentials, principal attributes, details, and internal information not meant for clients. The example code intentionally exports only three fields: `name`, `authenticationType`, and `authorities`; in production you may also want to omit `authorities` if they are not part of the API contract.

## 11. ThreadLocal, @Async, and Request Lifecycle

By default, `SecurityContextHolder` serves Servlet processing using context bound to the request thread. The code below does not automatically have the right context when executed on an arbitrary thread:

~~~java
executor.execute(() -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    // May be null or not the expected identity.
});
~~~

- **new Thread(...)**, custom Executors, or **@Async** do not always inherit SecurityContext.
- Passing the same context into a long-lived thread pool risks privilege leakage or holding stale identities.
- Spring Security provides wrappers such as **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor**, and **DelegatingSecurityContextAsyncTaskExecutor**, depending on the execution model.
- Spring MVC async `Callable` has built-in integration, but do not assume every `DeferredResult` or custom task has equivalent propagation.
- A sound design is to extract an **immutable, verified principal ID** at the request boundary, pass it into the service/job, and verify permissions when the action actually executes.

Never call `SecurityContextHolder.setContext()` or `setAuthentication()` in a controller to "bypass login". If the system programmatically creates an Authentication, it must be part of an authentication flow with proper credential/token verification and accurate context lifecycle/clear/save management.

## 12. Common Errors and How to Diagnose Them

| Error / Symptom | Cause or What to Check |
| --- | --- |
| Context exists but Authentication is null | Request unauthenticated, anonymous disabled, chain not matched, or different lifecycle |
| getName() is anonymousUser | `AnonymousAuthenticationToken` rather than a logged-in account |
| isAuthenticated() is true yet user is anonymous | Semantics of `AnonymousAuthenticationToken` |
| @AuthenticationPrincipal UserDetails is null/wrong type | Runtime principal is `Jwt`, `OidcUser`, `String`, etc. |
| SpEL expression returns wrong value | Root is `SecurityContext`, not `Authentication`; check the expression |
| Unauthenticated API returns 302 instead of 401 | API accidentally routed through web login chain/entry point |
| User logged in but gets 403 | Missing authorities, wrong `ROLE_`/`SCOPE_` prefix, or insufficient resource permission |
| MockMvc passes, production returns 401 | Mock principal does not prove real token/password validation works |
| @Async does not see Authentication | ThreadLocal does not propagate automatically across all executors |
| User A appears in User B's request | Custom filter/executor leaks SecurityContext or fails to clear it |
| Browser POST returns 403 even though GET works | Could be CSRF or authorization, not solely `@CurrentSecurityContext` |
| Curl works, browser hits CORS error | CORS/preflight is a separate mechanism, not a controller argument resolver |
| Token/password leaked during debugging | Credentials logged or Authentication serialized |
| Authenticated user can view others' data | Missing ownership check/ACL in the service layer |

**Debugging workflow:** confirm the request hits the intended `SecurityFilterChain` → identify the authentication filter/provider → inspect the actual `Authentication` type → read principal/name and authorities → verify `AuthorizationFilter`/method security → verify permissions on the target data. Never use `permitAll()` to mask an unexplained 401/403.

## 13. Production Checklist

- [ ] Confirm you are using Spring MVC Servlet, not mixing with WebFlux.
- [ ] Endpoints have the proper authentication mechanism and security chain.
- [ ] Use **@CurrentSecurityContext** when you need the context or Authentication, and **@AuthenticationPrincipal** when you need a specific principal type.
- [ ] Do not infer login state from `Authentication != null` or `isAuthenticated()` alone.
- [ ] Clearly determine `getName()`, principal type, and authorities for the active provider.
- [ ] Use `authorizeHttpRequests`/`@PreAuthorize` and resource-level authorization instead of checking name strings manually.
- [ ] Never serialize `SecurityContext`/`Authentication`; return DTOs with only necessary fields.
- [ ] Do not pass credentials or `SecurityContext` arbitrarily across background tasks.
- [ ] Include tests for 200/401/403, anonymous access, principal types, authorities, and Web MVC argument resolution.
- [ ] Include dedicated integration tests for real Basic/OIDC/JWT flows if the app uses those mechanisms.
- [ ] Check CSRF whenever browsers use cookies/sessions and perform state-changing requests.

## 14. Self-Check Questions

1. What does **@CurrentSecurityContext SecurityContext context** retrieve? The current `SecurityContext` provided by Spring Security for the MVC request.
2. What do you write to receive `Authentication` directly? **@CurrentSecurityContext(expression = "authentication") Authentication authentication**.
3. What do you write to receive the name? **@CurrentSecurityContext(expression = "authentication.name") String name**.
4. Why is **@AuthenticationPrincipal UserDetails** not right for every API? Because the principal may be a `Jwt`, `OidcUser`, or `String`.
5. Is **isAuthenticated()** enough to exclude anonymous users? No, `AnonymousAuthenticationToken` can return `true`.
6. Does `SecurityContext` always imply an `HttpSession` exists? No, stateless JWT APIs also create a context.
7. Does reading a role mean the user can view any record? No, object-level/tenant authorization is still required.
8. Does `@CurrentSecurityContext` verify passwords or JWTs itself? No; that is the responsibility of the authentication infrastructure.
9. Should you return a raw `Authentication` as JSON? No, select only the fields permitted for exposure.
10. Is `SecurityContextHolder` automatically propagated to every `@Async` task? No; propagation or passing an appropriate principal ID is required.

**Summary:** **@CurrentSecurityContext** provides a clear declarative way for Spring MVC controllers to obtain `SecurityContext` or values inside it such as `Authentication` and `authentication.name`. Choose the right annotation for your needs, understand principal types and anonymous tokens, maintain the authentication–authorization boundary, expose minimal public data, and test against the real security filter chain.
