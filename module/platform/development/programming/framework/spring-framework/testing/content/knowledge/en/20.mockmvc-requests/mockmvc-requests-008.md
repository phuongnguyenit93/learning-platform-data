# Principal and Request Authentication Context

When testing Spring MVC endpoints with `MockMvc`, a request can carry information about the caller. A controller may read the username via `Principal`, receive an `Authentication` object, or extract the authenticated principal with `@AuthenticationPrincipal`. Spring Security also uses `SecurityContext` to hold authentication state while processing the request.

These concepts are related, yet they are not identical. `Principal` is a Java and Servlet API concept that typically represents the identity of the request sender. `Authentication` is a Spring Security object containing the principal, authentication status, and authorities. `SecurityContext` holds the current `Authentication`. When the Spring Security filter chain is configured, it bridges the security context with the Servlet request so controllers can access identity via the appropriate APIs.

In a MockMvc test, you must supply the exact kind of context used by the behavior under test. Attaching only a `Principal` to the request may suffice for a controller calling `request.getUserPrincipal()`, yet it will not necessarily populate an `Authentication` in `SecurityContextHolder` for Spring Security authorization checks or `@AuthenticationPrincipal` resolution.

## 1. Principal in a Servlet Request

`java.security.Principal` is a simple interface representing an identity. It provides `getName()` to return the identifier name. In the Servlet API, `HttpServletRequest` exposes related methods:

- `getUserPrincipal()` returns the principal attached to the request, or `null` if the request has no principal.
- `getRemoteUser()` returns the username identified for the request, or `null` if unauthenticated.
- `isUserInRole(String role)` checks whether the caller belongs to the specified role according to Servlet security rules.

A controller can accept `Principal` directly as a handler parameter:

```java
@RestController
public class ProfileController {

    @GetMapping("/request-principal")
    public String requestPrincipal(Principal principal) {
        return principal == null ? "anonymous" : principal.getName();
    }
}
```

Spring MVC supports resolving a `Principal` parameter from the current request. This is a Servlet/MVC-level way to read identity. If a controller only needs the principal name, it does not need to depend directly on Spring Security's `Authentication` type.

### Attaching a Principal Directly in MockMvc

Spring MVC Test lets you set a principal on the request builder using `.principal(...)`:

```java
@WebMvcTest(ProfileController.class)
@AutoConfigureMockMvc(addFilters = false)
class ProfileControllerPrincipalTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exposesPrincipalNameToController() throws Exception {
        Principal principal = () -> "alice";

        mockMvc.perform(get("/request-principal").principal(principal))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
```

In this example, the test puts an object implementing `Principal` directly onto `MockHttpServletRequest`. This suits testing controllers or Servlet components that read `request.getUserPrincipal()` or a `Principal` parameter.

`addFilters = false` disables registered filters for MockMvc in this test to focus on the Servlet request principal. If the goal is to test how Spring Security translates an `Authentication` into the request principal, keep the filter chain enabled and configure `Authentication` using the approaches shown later.

However, `.principal(...)` only sets the principal on the mock request. It does not create an authenticated `Authentication` in `SecurityContextHolder`. Therefore, this approach is insufficient for testing `hasRole`, `hasAuthority`, method security, or `@AuthenticationPrincipal` parameters backed by Spring Security.

## 2. Spring Security Authentication and SecurityContext

Spring Security represents authentication state using the `Authentication` interface, which also extends `Principal`. An `Authentication` typically contains:

- `getPrincipal()`: the object representing the user or identity. It may be a string username, a `UserDetails`, or a custom principal type.
- `getCredentials()`: the credentials used during authentication, such as a password before authentication finishes. Applications should never log credentials or expose them in responses.
- `getAuthorities()`: the granted permissions, usually `GrantedAuthority` instances like `ROLE_ADMIN` or `SCOPE_read`.
- `isAuthenticated()`: indicates whether the object is currently considered authenticated.
- `getDetails()`: additional details about the authentication process, depending on the mechanism used.

`SecurityContext` holds the current `Authentication`. `SecurityContextHolder` is where Spring Security exposes the context to executing code. The default strategy typically stores the context per thread via `ThreadLocal`, allowing security components to read the same state within a processing thread.

Overview of the relationship:

```text
MockMvc request
      |
      v
Spring Security filter chain
      |
      +--> SecurityContextHolder
      |        |
      |        v
      |    SecurityContext
      |        |
      |        v
      |    Authentication
      |        +--> principal
      |        +--> authorities
      |        +--> authenticated state
      |
      v
DispatcherServlet --> controller
                         |
                         +--> Principal / Authentication
                         +--> @AuthenticationPrincipal
```

The diagram illustrates the typical flow when tests integrate the Spring Security filter chain. Real configurations may include additional filters for authentication, context persistence, exception handling, and authorization.

### How Do Principal and Authentication Differ?

| Concept | Role | Example |
| --- | --- | --- |
| `Principal` | Represents identity and provides a name | `principal.getName()` returns `alice` |
| `Authentication` | Authentication state in Spring Security | Holds principal `alice` and authorities `ROLE_USER` |
| `SecurityContext` | Holds the current Authentication | `context.getAuthentication()` |
| `SecurityContextHolder` | Exposes SecurityContext to running code | `SecurityContextHolder.getContext()` |
| `GrantedAuthority` | A granted permission | `ROLE_ADMIN`, `invoice:read` |

`Authentication` is a subtype of `Principal`, yet an arbitrary `Principal` is not necessarily an `Authentication`. That is why setting a request principal and setting a security context serve different testing purposes.

## 3. How Does Spring Security Connect the Servlet Request to SecurityContext?

When an application uses Spring Security, the filter chain reads or creates a `SecurityContext`, performs authentication according to configuration, and places the `Authentication` into the current context. A Servlet API integration filter also ensures methods such as `getUserPrincipal()`, `getRemoteUser()`, and `isUserInRole()` reflect the identity and permissions from the security context.

In a controller, you can receive `Authentication` directly:

```java
@RestController
public class AccountController {

    @GetMapping("/account/name")
    public String accountName(Authentication authentication) {
        return authentication.getName();
    }
}
```

Or use `@AuthenticationPrincipal` to receive the principal inside `Authentication`:

```java
@RestController
public class AccountController {

    @GetMapping("/account/principal")
    public String principalName(
            @AuthenticationPrincipal UserDetails userDetails) {
        return userDetails.getUsername();
    }
}
```

`@AuthenticationPrincipal` is provided by Spring Security in package `org.springframework.security.core.annotation`. Its argument resolver extracts the principal from the current `Authentication`. If there is no matching `Authentication` or the principal is incompatible with the parameter type, the result may be `null` or fail to bind depending on resolver configuration.

If your code uses `@AuthenticationPrincipal` or reads `SecurityContextHolder`, set up `Authentication` in the test. Simply calling `.principal(...)` on the request builder does not satisfy that requirement.

## 4. Using user() to Create an Authenticated User in MockMvc

Spring Security Test provides the `user(...)` request post-processor. It is a convenient way to simulate a request with an authenticated user without running a real login flow.

Example of endpoints requiring authentication:

```java
@RestController
public class CurrentUserController {

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin area";
    }
}
```

Suppose the security configuration requires a logged-in user for `/profile` and the ADMIN role for `/admin`:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .requestMatchers("/profile").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Tests can configure a user per request:

```java
@WebMvcTest(CurrentUserController.class)
@Import(SecurityConfig.class)
class CurrentUserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void authenticatedUserCanReadProfile() throws Exception {
        mockMvc.perform(get("/profile").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void userWithoutAdminRoleCannotOpenAdminPage() throws Exception {
        mockMvc.perform(get("/admin").with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        mockMvc.perform(get("/admin").with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin area"));
    }
}
```

`user("alice")` creates a test user named `alice`. `roles("USER")` adds the `ROLE_USER` authority; Spring automatically prepends `ROLE_`. Thus, when configuration uses `hasRole("ADMIN")`, the test needs `roles("ADMIN")`, without passing the `ROLE_ADMIN` prefix into `roles`.

If the application checks custom authorities instead of roles, use `.authorities(...)`:

```java
mockMvc.perform(get("/reports")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("report:read"))))
        .andExpect(status().isOk());
```

`authorities(...)` uses the exact authority names supplied without prepending `ROLE_`. Distinguish `hasRole("ADMIN")` from `hasAuthority("ROLE_ADMIN")` or `hasAuthority("report:read")` to avoid configuring the wrong authorities in tests.

`user(...)` is a mechanism for creating an `Authentication` for tests. It does not test password encoders, user lookup, LDAP, OAuth login, or production authentication flows. If the goal is to test real login steps, write separate tests for the filter or authentication provider with the corresponding credentials.

## 5. Using Custom UserDetails or Custom Principals

If the application uses a principal type carrying extra fields such as account ID, tenant, or employee code, you can pass a `UserDetails` instance into `user(...)`:

```java
public class AppUser implements UserDetails {

    private final Long accountId;
    private final String username;
    private final Collection<? extends GrantedAuthority> authorities;

    public AppUser(Long accountId, String username,
                   Collection<? extends GrantedAuthority> authorities) {
        this.accountId = accountId;
        this.username = username;
        this.authorities = authorities;
    }

    public Long getAccountId() {
        return accountId;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return "unused-in-this-test";
    }

    @Override
    public String getUsername() {
        return username;
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
```

Controller accepting the custom principal type:

```java
@GetMapping("/account/id")
public Long accountId(@AuthenticationPrincipal AppUser user) {
    return user.getAccountId();
}
```

Test creating the principal:

```java
AppUser appUser = new AppUser(
        42L,
        "alice",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

mockMvc.perform(get("/account/id").with(user(appUser)))
        .andExpect(status().isOk())
        .andExpect(content().string("42"));
```

In this way, the test confirms the controller uses the expected data from the application's principal. If the custom principal does not implement `UserDetails`, build an appropriate `Authentication` and use `authentication(...)` or `securityContext(...)` as shown in the next section.

## 6. Setting Authentication or SecurityContext Directly

When you need exact control over the `Authentication` type, authorities, details, or principal, use the corresponding Spring Security Test post-processors.

### Using authentication(...)

Example creating an authenticated `UsernamePasswordAuthenticationToken`:

```java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "alice",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

mockMvc.perform(get("/profile").with(authentication(authentication)))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
```

The constructor accepting authorities creates an authenticated token. The constructor taking only principal and credentials without authorities usually creates an unauthenticated token; do not pick the wrong constructor when testing an authenticated request.

### Using securityContext(...)

When a test needs full control over the `SecurityContext`, create a context and attach the `Authentication` to it:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);

mockMvc.perform(get("/profile").with(securityContext(context)))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
```

These two approaches are useful when `user(...)` cannot express the principal or `Authentication` structure used by the application. For common cases needing only a username and roles, `user(...)` is usually more concise.

## 7. Using @WithMockUser for a Test Method or Test Class

In addition to request post-processors, Spring Security Test supports the `@WithMockUser` annotation. This annotation populates `SecurityContext` for a test method or an entire test class.

```java
@WebMvcTest(CurrentUserController.class)
@Import(SecurityConfig.class)
class CurrentUserWithMockUserTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void exposesCurrentUser() throws Exception {
        mockMvc.perform(get("/profile"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void allowsAdmin() throws Exception {
        mockMvc.perform(get("/admin"))
                .andExpect(status().isOk());
    }
}
```

You can place `@WithMockUser` on the class if all tests in the class share the same default user. Place it on individual methods when each test requires a different identity or permission set.

`@WithMockUser` creates a mock user with Spring Security's default `UserDetails` principal type. If the application expects a custom principal, use `user(customUserDetails)`, `authentication(...)`, or a custom `@WithSecurityContext` mechanism.

This annotation does not perform form login, does not invoke a production `UserDetailsService`, and does not validate passwords. It establishes authentication state for testing purposes.

## 8. Configuring Spring Security for MockMvc

Examples using `user(...)`, `authentication(...)`, and `@WithMockUser` are meaningful when the test actually runs with the Spring Security configuration under test. The filter chain must be wired into MockMvc.

With Spring Boot and `@AutoConfigureMockMvc` or test slices such as `@WebMvcTest`, MockMvc is usually integrated with Spring Security by Boot when the appropriate security dependencies and beans are present. If building MockMvc manually via `MockMvcBuilders`, apply the security configurer:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` comes from `SecurityMockMvcConfigurers` in Spring Security Test. It registers `FilterChainProxy` and required components so mock requests flow through the Spring Security filter chain.

Without the filter chain, tests may fail to verify the application's authorization rules. An endpoint might return 200 in tests simply because security filters did not execute, even though in deployment it requires login or a specific role.

To properly test a protected request, ensure all of the following:

1. The security configuration is loaded into the test context.
2. The Spring Security filter chain is attached to MockMvc.
3. The test supplies the intended authentication state, or intentionally omits it to test anonymous access.
4. Assertions check the exact status and outcome specified by the security rules.

## 9. Testing Anonymous, Authenticated, and Authorized Requests

An authorization test suite should cover at least the distinct access states supported by the endpoint.

| State | Test setup | Usually expected result for protected endpoint |
| --- | --- | --- |
| Unauthenticated | No `user(...)` or `@WithMockUser` | 401 or redirect to login, depending on configuration |
| Authenticated, insufficient privileges | `.with(user("alice").roles("USER"))` | 403 when logged in without sufficient permissions |
| Authenticated, sufficient privileges | `.with(user("root").roles("ADMIN"))` | Request is permitted |
| Custom authority | `.with(user("alice").authorities(...))` | Depends on configured authority |

Anonymous example:

```java
@Test
void anonymousUserCannotReadProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
}
```

Asserting 401 is appropriate only if the application configures an authentication entry point returning 401, such as a stateless API. A web application using form login may return a 302 redirect to the login page. Base assertions on the application's anonymous-handling policy.

403 typically indicates an authenticated user lacking permission. If the request is unauthenticated, Spring Security usually invokes the authentication entry point first; exact behavior depends on configuration.

## 10. Specialized Authentication Mechanisms in MockMvc

`user(...)` is a general-purpose way to create a mock user. If the application uses specialized `Authentication` mechanisms, Spring Security Test provides corresponding post-processors in the feature-specific test modules.

### HTTP Basic

For endpoints using HTTP Basic, `httpBasic(username, password)` generates the Basic Authorization header:

```java
mockMvc.perform(get("/profile").with(httpBasic("alice", "password")))
        .andExpect(status().isOk());
```

This is useful when you want to test the filter and authentication provider handling HTTP Basic. Unlike `user(...)`, it sends credentials in the request for the configured filter-chain authentication mechanism to process. The test must have a matching user store or authentication provider.

### JWT for OAuth 2.0 Resource Server

If the endpoint is protected by a JWT bearer token and the application uses Spring Security OAuth2 Resource Server, `jwt()` can create a simulated JWT Authentication:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("scope", "orders.read"))))
        .andExpect(status().isOk());
```

The `jwt()` post-processor helps test authorization based on claims and mapped authorities in tests. It does not verify token signatures, issuer, audience, expiration, or key retrieval from an authorization server. To verify real JWT validation, write dedicated tests for the decoder configuration with valid and invalid tokens.

### CSRF Is a Separate Concern

If the application enables CSRF protection, state-changing requests such as POST, PUT, PATCH, or DELETE may require a CSRF token:

```java
mockMvc.perform(post("/profile/email")
        .with(user("alice"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"alice@example.test\"}"))
        .andExpect(status().isOk());
```

A CSRF token validates the request against CSRF protection rules; it does not replace `Authentication`. A request can be authenticated yet still rejected if a required CSRF token is missing.

## 11. Common Mistakes When Setting Up Principal and Authentication

### Using principal(...) and Expecting @AuthenticationPrincipal to Be Populated

`.principal(...)` sets `HttpServletRequest.getUserPrincipal()`. `@AuthenticationPrincipal` reads the principal from `Authentication` in the Spring Security context. The two can be linked when the filter chain runs, yet a plain mock request with only a principal does not create a `SecurityContext`. Use `user(...)`, `authentication(...)`, or `securityContext(...)` for the latter case.

### Using user(...) Without the Filter Chain Running

A post-processor can attach user details to the request, yet if MockMvc does not include the Spring Security filter chain, the test does not exercise the application's real authorization path. Use `@AutoConfigureMockMvc` with proper Boot setup or `.apply(springSecurity())` when building manually.

### Confusing Roles with Authorities

`roles("ADMIN")` prepends `ROLE_`, producing `ROLE_ADMIN`. `authorities("ADMIN")` or `hasAuthority("ADMIN")` operates on the literal authority name. If the application uses `hasRole("ADMIN")`, tests should produce `ROLE_ADMIN` via `roles("ADMIN")` or the exact equivalent authority.

### Using the Wrong Principal Type

An endpoint expecting `@AuthenticationPrincipal AppUser` requires an `Authentication` whose principal is an `AppUser`. Using `user("alice")` creates Spring Security's default `UserDetails` principal, not `AppUser`. Pass the custom `UserDetails` object or build an appropriate `Authentication`.

### Using One User for Every Test

A test class may need anonymous, USER, and ADMIN cases. Specify identity explicitly per test so each case is independent, readable, and free of leftover state. When placing `@WithMockUser` at the class level, override it at the method level or choose dedicated request post-processors for tests needing different scenarios.

### Assuming Identical Status Codes Across All Configurations

Anonymous callers may receive 401 or 302 depending on the entry point. Authenticated users lacking privileges typically receive 403. Base assertions on the application's API or web-login configuration.

### Returning Credentials in Responses or Logs

Principals and authorities are normally safe for access checks, whereas credentials must never be exposed. Tests should check only necessary fields such as username, account ID, or permissions; never serialize the entire `Authentication` or `SecurityContext` into a production response.

## 12. Choosing the Setup Based on Test Goal

| Goal | Appropriate setup |
| --- | --- |
| Controller only needs name from Servlet request principal | `.principal(principal)` |
| Controller reads `Authentication` or `@AuthenticationPrincipal` | `.with(user(...))` or `@WithMockUser` |
| Need a custom `UserDetails` principal | `.with(user(customUserDetails))` |
| Need a custom `Authentication` | `.with(authentication(authentication))` |
| Need full control over `SecurityContext` | `.with(securityContext(context))` |
| Want to test HTTP Basic filter and provider | `.with(httpBasic(username, password))` |
| Want to test authorization by simulated JWT claims/authorities | `.with(jwt())` |
| Want to test anonymous access | Do not set user or Authentication; assert per entry point |
| Want to test real application authorization | Load security config and wire the filter chain into MockMvc |

Workflow for implementing an authentication test:

1. Determine whether code reads `Principal`, `Authentication`, `SecurityContextHolder`, or `@AuthenticationPrincipal`.
2. Determine the permission required by the endpoint: authenticated, role, or specific authority.
3. Load the security configuration under test.
4. Ensure the Spring Security filter chain participates in MockMvc.
5. Choose the post-processor or annotation matching the principal and `Authentication` types.
6. Verify responses for anonymous, insufficient-privilege, and authorized cases whenever meaningful.

## 13. Conclusion

`Principal` represents identity at the Java/Servlet layer; Spring Security's `Authentication` carries the principal together with authentication status and authorities; `SecurityContext` stores the current `Authentication`. In MockMvc, `.principal(...)` fits tests that only need to set the Servlet request principal. `user(...)`, `authentication(...)`, `securityContext(...)`, and `@WithMockUser` fit tests requiring Spring Security authentication state.

To perform meaningful authorization checks, load the Spring Security configuration and route requests through the filter chain in MockMvc. Choosing the right principal source, `Authentication` type, and permissions ensures tests accurately reflect the endpoint behavior the application must enforce.
