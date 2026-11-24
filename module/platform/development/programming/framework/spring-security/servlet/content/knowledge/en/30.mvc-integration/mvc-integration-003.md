# HttpServletRequest.getUserPrincipal(), getRemoteUser(), and isUserInRole in Spring Security Servlet

## 1. Overview

In Spring MVC (Servlet stack), `HttpServletRequest` provides three methods related to the identity and roles of the caller:

~~~java
Principal principal = request.getUserPrincipal();
String name = request.getRemoteUser();
boolean admin = request.isUserInRole("ADMIN");
~~~

These are three illustrative calls inside a method that already has an `HttpServletRequest request` variable; `java.security.Principal` must be imported. All three methods **belong to the Servlet standard**, not APIs invented by Spring Security. However, Spring Security links them to the `Authentication` stored in `SecurityContext`, enabling MVC applications or legacy Servlet code to read authentication state in a familiar way.

This lesson applies to Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring MVC. WebFlux has a different SecurityContext and request model, so these Servlet examples do not apply directly.

After this lesson, you should accurately understand the three return values, anonymous request behavior, the difference between `Principal` and `Authentication`, `ROLE_` prefix rules, `SecurityFilterChain` configuration, and testing with MockMvc.

## 2. Comparison Table of the Three Methods

| Method | Return Type | Meaning | When Unauthenticated |
| --- | --- | --- | --- |
| getUserPrincipal() | java.security.Principal | Identity object per Servlet request | Typically null |
| getRemoteUser() | String | Principal name of the request | Typically null |
| isUserInRole("ADMIN") | boolean | Whether the ADMIN role is present in the Servlet context | false |

**Remote user is not remote address.** `getRemoteUser` returns the username/principal name; `getRemoteAddr` returns the IP address from the container's perspective. When a request traverses a proxy, the remote address also depends on topology and forwarded-header trust policies.

In a default Spring Security Servlet setup, `getUserPrincipal` usually returns `Authentication`, `getRemoteUser` usually returns `Authentication.getName()`, and `isUserInRole` relies on `GrantedAuthority` along with the role prefix. This is the behavior of the **Spring Security servlet request wrapper**. If a request bypasses Spring Security or uses a custom wrapper, results may differ.

## 3. Principal, Authentication, and the Inner Principal

Spring Security's `Authentication` is an interface that **extends `Principal`**. `Authentication` carries more information than a plain `Principal`:

~~~text
Authentication
  getName()           -> subject's identifier name
  getPrincipal()      -> inner principal object
  getAuthorities()    -> list of GrantedAuthority
  getCredentials()    -> credentials, may have been erased
  getDetails()        -> auxiliary data
  isAuthenticated()   -> status flag of Authentication
~~~

Important distinctions:

- **request.getUserPrincipal()**: the `Principal` returned by the Servlet request; with the Spring Security wrapper, this is usually the `Authentication` itself.
- **authentication.getPrincipal()**: the object **inside** `Authentication`, which may be `UserDetails` when using username/password login, `Jwt` when using a JWT Resource Server, or a custom object.
- **authentication.getName()**: a `String` representing the principal name, not guaranteed to be an email or system-wide user key.

Illustrative snippet with type checking:

~~~java
Principal principal = request.getUserPrincipal();

if (principal instanceof Authentication authentication) {
    String name = authentication.getName();
    Object innerPrincipal = authentication.getPrincipal();
    Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
}
~~~

Imports for `Principal`, `Collection`, `Authentication`, and `GrantedAuthority` are required. This snippet belongs inside a method, not as a standalone Java file.

**Common cast error:**

~~~java
UserDetails user = (UserDetails) request.getUserPrincipal();
~~~

With Spring Security, the value returned by the Servlet request is typically `Authentication`, not `UserDetails` directly. To obtain `UserDetails`, call `Authentication.getPrincipal()` and check its type, or use `@AuthenticationPrincipal` with the appropriate authentication mechanism. If the request uses `JwtAuthenticationToken`, the inner principal is usually `Jwt`, not `UserDetails`.

## 4. SecurityContextHolderAwareRequestFilter

Spring Security stores the request's `Authentication` in **SecurityContext**. `SecurityContextHolder` allows parts of the application to access the security context within the appropriate processing scope. Meanwhile, the standard Servlet API defines the three user and role methods. To bridge both worlds, Spring Security uses **SecurityContextHolderAwareRequestFilter**.

This filter wraps `HttpServletRequest` in a request wrapper that implements `getUserPrincipal`, `getRemoteUser`, and `isUserInRole` based on Spring Security's `Authentication`.

High-level flow:

~~~text
Client request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy -> SecurityFilterChain
    |
    +--> SecurityContext management
    |
    +--> HTTP Basic / form / Bearer authentication
    |         |
    |         v
    |     SecurityContext holds Authentication
    |
    +--> SecurityContextHolderAwareRequestFilter
    |         |
    |         v
    |     Servlet request wrapper
    |
    +--> AuthorizationFilter
    |
    v
DispatcherServlet -> Controller
       |
       +--> request.getUserPrincipal()
       +--> request.getRemoteUser()
       +--> request.isUserInRole("ADMIN")
~~~

This diagram illustrates functional roles and does not attempt to list every filter or guarantee the exact order of additional filters in all configurations. A request rejected by a filter may never reach the controller.

There is no need to manually add this filter via a custom `GenericFilterBean` just to read the principal. Standard Spring Security Servlet configuration already provides the necessary integration. Never set `Authentication` manually inside a controller just to make these three APIs work.

## 5. getUserPrincipal() and Anonymous Requests

In a request authenticated via form login or HTTP Basic, `getUserPrincipal` typically returns **UsernamePasswordAuthenticationToken**, an implementation of `Authentication`. Its `getName()` is the username and its inner `getPrincipal()` may be `UserDetails`.

In an OAuth 2.0 Resource Server JWT application, `getUserPrincipal` may return **JwtAuthenticationToken**. JWT claims must be read from the inner `Jwt` and are only trustworthy after the decoder verifies signature, issuer, audience, and expiration.

For unauthenticated requests, the Servlet API typically returns null:

~~~java
Principal principal = request.getUserPrincipal();

if (principal == null) {
    // No authenticated principal from the Servlet perspective.
} else {
    String name = principal.getName();
}
~~~

Spring Security may hold an **AnonymousAuthenticationToken** in `SecurityContext` even when the Servlet request returns `null`. `AnonymousAuthenticationToken` does not represent a genuinely authenticated account. The request wrapper recognizes anonymous tokens and typically does not return them from `request.getUserPrincipal()`.

Therefore, never conclude that a non-null `SecurityContextHolder.getContext().getAuthentication()` means a user is logged in. You must distinguish anonymous tokens, real authentication, and authorization rules.

## 6. getRemoteUser() and Identity

**getRemoteUser()** typically returns `Authentication.getName()` for an authenticated user, or `null` if the request has no principal recognized by the Servlet API.

~~~java
String remoteUser = request.getRemoteUser();

if (remoteUser == null) {
    // May be an anonymous request.
}
~~~

For a logged-in user `alice`, `request.getUserPrincipal().getName()` and `request.getRemoteUser()` are both typically `"alice"`. However, the value is not inherently an immutable username or email.

With JWT, `getName` usually comes from the `sub` claim or is customized by `JwtAuthenticationConverter`. If issuer A and issuer B both issue `sub="42"`, two users across two organizations could both have `getRemoteUser()="42"`. Never use this single string alone to link accounts or enforce multi-tenant authorization. Distinguish callers using issuer+subject or a mapped and verified internal ID.

When auditing, record the request ID, trusted principal, issuer/tenant, and action per security policy; never log raw Bearer tokens, `Authorization` headers, or passwords.

## 7. isUserInRole() and the ROLE_ Prefix

In default Spring Security Servlet integration, the `ADMIN` role corresponds to the authority **ROLE_ADMIN**. An `Authentication` containing:

~~~text
ROLE_USER
ROLE_ADMIN
SCOPE_reports.read
~~~

typically produces:

~~~java
request.isUserInRole("USER");   // true
request.isUserInRole("ADMIN");  // true
request.isUserInRole("AUDIT");  // false
~~~

Passing **"ADMIN"** is the natural convention of the Servlet role API. Do not treat every `GrantedAuthority` as a role: a JWT with authority `SCOPE_admin` does not automatically have `ROLE_ADMIN`; `isUserInRole("ADMIN")` is typically `false` without the corresponding role authority.

Side-by-side comparison of rule styles:

~~~java
// Servlet API role check in a method with a request variable:
request.isUserInRole("ADMIN");

// Request authorization rule in HttpSecurity:
auth.requestMatchers("/admin/**").hasRole("ADMIN");

// Exact authority check:
auth.requestMatchers("/reports/**")
    .hasAuthority("SCOPE_reports.read");
~~~

These are independent code snippets used in different contexts. When an application customizes the prefix, role hierarchy, or authority converter, these checkpoints may not always align identically. Always test against the application's actual `Authentication`.

**`isUserInRole` only returns a boolean.** Calling it in a controller and ignoring the result does not block the request. Security policies for sensitive endpoints belong in `SecurityFilterChain`, method security, or service authorization; controller role checks can be used for legacy Servlet API compatibility or choosing what content to display.

## 8. Complete Spring Boot 3, Spring Security 6 Example

The demo application uses HTTP Basic and two in-memory users:

- Alice: `ROLE_USER` and `ROLE_ADMIN`.
- Bob: `ROLE_USER`.
- `/mvc/public`: public, allowing observation of both anonymous and authenticated requests.
- `/mvc/secure`: requires authentication.
- `/mvc/admin`: requires `ROLE_ADMIN`.

### 8.1. Dependencies

In `build.gradle` of a Spring Boot project with the corresponding plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 8.2. Main Application Class

File `src/main/java/demo/servletapi/ServletApiDemoApplication.java`:

~~~java
package demo.servletapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletApiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletApiDemoApplication.class, args);
    }
}
~~~

### 8.3. SecurityFilterChain and Demo Users

File `src/main/java/demo/servletapi/SecurityConfig.java`:

~~~java
package demo.servletapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/mvc/public").permitAll()
                .requestMatchers("/mvc/secure").authenticated()
                .requestMatchers("/mvc/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .roles("USER", "ADMIN")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

This is strictly a demo, not how real accounts are stored in production. `User.withUsername(...).roles("ADMIN")` creates the `ROLE_ADMIN` authority by default. Demo passwords must never be used for real accounts; production requires a proper identity store and credential policy.

The example preserves default CSRF protection. Operations here are GET-only; for state-changing requests, evaluate CSRF against the actual browser/cookie/authentication model. HTTP Basic should only be used over HTTPS outside controlled localhost environments.

### 8.4. Controller Using All Three APIs

File `src/main/java/demo/servletapi/IdentityController.java`:

~~~java
package demo.servletapi;

import jakarta.servlet.http.HttpServletRequest;
import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mvc")
public class IdentityController {

    @GetMapping("/public")
    public Identity publicInfo(HttpServletRequest request) {
        return inspect(request);
    }

    @GetMapping("/secure")
    public Identity secureInfo(HttpServletRequest request) {
        return inspect(request);
    }

    @GetMapping("/admin")
    public Identity adminInfo(HttpServletRequest request) {
        return inspect(request);
    }

    private static Identity inspect(HttpServletRequest request) {
        Principal principal = request.getUserPrincipal();
        String remoteUser = request.getRemoteUser();

        return new Identity(
            principal == null ? "NONE" : principal.getName(),
            remoteUser == null ? "NONE" : remoteUser,
            request.isUserInRole("USER"),
            request.isUserInRole("ADMIN")
        );
    }

    public record Identity(
        String principal,
        String remoteUser,
        boolean userRole,
        boolean adminRole
    ) {}
}
~~~

Null values are converted to `"NONE"` **only to make the JSON output easy to inspect**. The Servlet API does not return `"NONE"` itself. The controller has no `if` check blocking `/mvc/admin` because `hasRole("ADMIN")` already protects the endpoint before the controller runs.

### 8.5. Running and Output

With the project's Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Call anonymously:

~~~bash
curl -s http://localhost:8080/mvc/public
~~~

Equivalent JSON:

~~~json
{
  "principal": "NONE",
  "remoteUser": "NONE",
  "userRole": false,
  "adminRole": false
}
~~~

With Alice:

~~~bash
curl -s -u alice:demo-password http://localhost:8080/mvc/public
~~~

Equivalent JSON:

~~~json
{
  "principal": "alice",
  "remoteUser": "alice",
  "userRole": true,
  "adminRole": true
}
~~~

With Bob:

~~~bash
curl -s -u bob:demo-password http://localhost:8080/mvc/public
~~~

Equivalent JSON:

~~~json
{
  "principal": "bob",
  "remoteUser": "bob",
  "userRole": true,
  "adminRole": false
}
~~~

JSON key ordering may vary depending on the serializer. To test authorization:

~~~bash
curl -i http://localhost:8080/mvc/secure
curl -i -u bob:demo-password http://localhost:8080/mvc/secure
curl -i -u bob:demo-password http://localhost:8080/mvc/admin
curl -i -u alice:demo-password http://localhost:8080/mvc/admin
~~~

Expected in this simple setup: unauthenticated call to `/mvc/secure` typically returns 401; Bob to `/mvc/secure` returns 200; Bob to `/mvc/admin` returns 403; Alice to `/mvc/admin` returns 200. Always use HTTPS when testing credentials on machines/hosts beyond localhost.

## 9. MockMvc Testing

Add `spring-security-test` as shown in the dependencies, then create `src/test/java/demo/servletapi/IdentityControllerTest.java`:

~~~java
package demo.servletapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAnonymous() throws Exception {
        mvc.perform(get("/mvc/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("NONE"))
            .andExpect(jsonPath("$.remoteUser").value("NONE"))
            .andExpect(jsonPath("$.userRole").value(false))
            .andExpect(jsonPath("$.adminRole").value(false));
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER", "ADMIN"})
    void loggedInAdminOnPublicEndpoint() throws Exception {
        mvc.perform(get("/mvc/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.remoteUser").value("alice"))
            .andExpect(jsonPath("$.userRole").value(true))
            .andExpect(jsonPath("$.adminRole").value(true));
    }

    @Test
    void secureEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/mvc/secure"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobIsForbiddenFromAdmin() throws Exception {
        mvc.perform(get("/mvc/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER", "ADMIN"})
    void aliceIsAllowedIntoAdmin() throws Exception {
        mvc.perform(get("/mvc/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.adminRole").value(true));
    }
}
~~~

These tests confirm the behavior of the Servlet request wrapper, anonymous access, role prefixing, and authorization. **@WithMockUser simulates Authentication**; it does not verify real passwords or validate JWT signatures. When you need to prove HTTP Basic from an HTTP client or Resource Server Bearer authentication works end-to-end, add integration tests with real credentials/tokens and an appropriate environment.

Run tests when the project has the Gradle wrapper:

~~~bash
./gradlew test
~~~

Expect five passing tests under the configuration above; actual Gradle console output depends on plugins and environment, with no fixed stdout.

## 10. Comparison with Principal, Authentication, and @AuthenticationPrincipal in MVC

Spring MVC supports other parameters and components besides `HttpServletRequest`:

| Approach | Contents | Guidance |
| --- | --- | --- |
| request.getUserPrincipal() | Principal, typically Authentication | Integrating with Servlet code |
| request.getRemoteUser() | Principal name | Displaying name or controlled auditing |
| request.isUserInRole() | Boolean role check | Legacy Servlet role APIs |
| Controller argument Principal | Principal | Need name, no need to know concrete Authentication |
| Controller argument Authentication | Authentication and authorities | Need Spring Security details |
| @AuthenticationPrincipal UserDetails | UserDetails inside Authentication | Username/password when principal is UserDetails |
| @AuthenticationPrincipal Jwt | Jwt inside JWT Authentication | Resource Server JWT |
| SecurityContextHolder | Authentication | Layers without HttpServletRequest that have a security context |

Example controller accepting `Principal`:

~~~java
@GetMapping("/greeting")
public String greeting(Principal principal) {
    return principal == null
        ? "Hello guest"
        : "Hello " + principal.getName();
}
~~~

Example controller accepting `UserDetails`:

~~~java
@GetMapping("/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

These are two separate methods placed inside a controller with the corresponding imports. Do not use `UserDetails` for JWT if the runtime principal is actually `Jwt`. Do not treat `getName` as a globally immutable ID across multiple issuers.

## 11. Distinguishing Role Checks from Mandatory Authorization

In Spring Security, `request.isUserInRole("ADMIN")` only returns `true` or `false`. An ignored return value does not protect data. Sensitive endpoints should be controlled using:

- **authorizeHttpRequests** in `SecurityFilterChain`;
- **@PreAuthorize** and method security when `@EnableMethodSecurity` is enabled;
- **object-level authorization** in the service/business layer, such as permissions on a specific order or document.

Method security example:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteOrder(long orderId) {
    // Service may also need to check permissions on orderId.
}
~~~

This is an illustrative method, not a standalone runnable file. `@PreAuthorize` only takes effect when method security is enabled and the method is invoked through the appropriate Spring proxy.

The `ADMIN` role does not automatically guarantee access to every record in a multi-tenant system. Likewise, an authenticated principal does not automatically gain permission to read another user's resources just because the endpoint requires `authenticated()`.

## 12. Common Pitfalls in Real-World Integration

**Public endpoints still have a principal:** `permitAll` allows guest access, but does not discard an existing `Authentication`. Alice sending credentials to a public endpoint can still see Alice's name and `ROLE_ADMIN`.

**SecurityContext holding AnonymousAuthenticationToken:** an anonymous token is not proof of a real logged-in user; the Servlet wrapper typically returns `null` for an anonymous principal.

**Requests bypassing Spring Security:** when configuring `ignoring` or servlet filter mappings that exclude a route, Servlet methods may reflect container authentication or another wrapper. For public URLs that should still run other security filters, prefer `permitAll` over bypassing the chain.

**Custom HttpServletRequestWrapper:** a custom filter that overrides `getUserPrincipal`/`getRemoteUser`/`isUserInRole` improperly can shadow the values supplied by Spring Security. Check filter ordering and delegation.

**Multiple SecurityFilterChains:** `/api/**` may use Bearer tokens while `/mvc/**` uses Basic or form login; the `Authentication` type in controllers will differ. Do not cast everything to `UsernamePasswordAuthenticationToken`.

**Async/background threads:** `SecurityContextHolder` is normally bound to the current processing context; `@Async`, `Executor`, or another thread does not inherit the same `Authentication` by default. Never retain `HttpServletRequest` for use after the request finishes. If you need to propagate security context, use Spring Security's delegation support or pass verified business data.

**X-Remote-User header:** a client can send arbitrary username headers itself. Never treat them as valid `getRemoteUser` values without a system-controlled trust boundary and genuine pre-authentication.

## 13. Common Mistakes

1. **Calling `getUserPrincipal().getName()` without a null check:** causes `NullPointerException` on anonymous requests. Fix by checking for null or safely using `getRemoteUser`.
2. **Casting `getUserPrincipal` to `UserDetails`:** in Spring Security Servlet you usually need `Authentication.getPrincipal()`, not the Servlet `Principal`.
3. **Confusing remote user with IP:** `getRemoteUser` is the username; `getRemoteAddr` relates to the network address.
4. **Using `remoteUser` as a global ID:** names/`sub` values can collide across issuers or change; use namespacing and internal mapping.
5. **Confusing `ROLE_` with `SCOPE_`:** OAuth scopes do not automatically become Servlet roles.
6. **Guarding only with `if` in a controller:** place authorization policies in `SecurityFilterChain`/methods/services to reduce mistakes.
7. **Treating `permitAll` as anonymous-only:** authenticated users still carry a principal.
8. **Trusting `isAuthenticated` on an anonymous token:** does not prove a real logged-in user.
9. **Overlooking custom wrappers/filter order:** check Servlet integration and the security chain.
10. **Using `@WithMockUser` to prove real JWT/Basic credentials work:** MockMvc post-processors do not exercise the full authentication pipeline.
11. **Accepting client-supplied identity headers:** do not trust `X-User` or `X-Remote-User` without trusted pre-authentication.
12. **Ignoring ownership:** generic roles do not replace per-object permission checks.

## 14. Checklist and Summary

- [ ] Distinguish the `Principal` returned by the Servlet API from `Authentication.getPrincipal()`.
- [ ] Check for null on `getUserPrincipal` and `getRemoteUser` for anonymous requests.
- [ ] Understand that `getRemoteUser` is an identity name, not an IP address.
- [ ] Understand `ROLE_ADMIN`, `ROLE_USER`, and how they differ from `SCOPE_x`.
- [ ] Verify that `SecurityContextHolderAwareRequestFilter` and `SecurityFilterChain` actually process the request.
- [ ] Never treat `AnonymousAuthenticationToken` as a logged-in user.
- [ ] Test `permitAll` with both anonymous and authenticated users.
- [ ] Test 401 when unauthenticated, 403 when lacking a role, and 200 when authorized.
- [ ] Apply authorization before business logic and enforce object-level checks when required.
- [ ] Never log credentials or use usernames as global tenant keys.
- [ ] Never retain `HttpServletRequest` past the request lifecycle or blindly trust pre-auth data from headers.

**Conclusion:** When Spring Security Servlet integration is active, `HttpServletRequest.getUserPrincipal()` typically returns `Authentication`, `getRemoteUser()` typically returns `Authentication.getName()`, and `isUserInRole("ADMIN")` checks roles based on `GrantedAuthority` following the `ROLE_` convention. Distinguishing anonymous from authenticated requests, outer Servlet `Principal` from the inner `Authentication` principal, and placing authorization policies in the right layer are the three core pillars of safe Spring MVC integration.
