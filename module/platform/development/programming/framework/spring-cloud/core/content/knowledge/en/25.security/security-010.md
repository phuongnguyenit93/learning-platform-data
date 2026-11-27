# Testing Least Privilege for Administrative Operations

## 1. Purpose of This Testing Lesson

Administrative operations in a Spring Cloud system typically carry greater impact than ordinary read operations. For example, an operator can view a service list, drain an instance from traffic, register a new service, refresh configuration, or change registry status. If every logged-in user is permitted to perform these operations, the application grants broader permissions than their job requires.

The principle of least privilege requires each principal to hold only the exact permissions needed for their duties. Testing must prove both sides:

- Principals with appropriate permissions can perform their assigned operations.
- Principals without permission, even if logged in, cannot perform those operations and cause no side effects.

A single test confirming an administrator can call an endpoint successfully is not enough. You must test anonymous callers, authenticated users missing permission, read-only users, and principals holding the exact authority for a specific operation.

After this lesson, readers can:

- Design a permission matrix for administrative operations.
- Distinguish broad roles from fine-grained authorities.
- Protect both HTTP endpoints and service methods.
- Write tests for anonymous, authenticated, forbidden, and allowed cases.
- Test CSRF, JWT authority mapping, and per-tenant/resource permissions.
- Verify that rejected requests do not modify data or trigger side effects.

## 2. Least Privilege Starts with a Permission Matrix

Before writing annotations or security matchers, list all operations and required permissions. Do not infer permissions merely from user group names such as operator or administrator.

Example for a service managing service registrations:

| Operation | Suggested Authority | Typical Caller |
| --- | --- | --- |
| View registry | `registry:read` | Monitoring, operator |
| Drain an instance | `registry:drain` | On-call operator |
| Register instance | `registry:register` | Deployment agent |
| Deregister | `registry:deregister` | Registry administrator |
| Refresh configuration | `config:refresh` | Configuration operator |
| Shut down application | `application:shutdown` | Administrator with approval workflow |

The matrix should answer three questions:

1. Which actions are read-only, and which modify state?
2. Which authority does a user need to perform each action?
3. Are additional restrictions needed by tenant, service, environment, or resource owner?

Avoid creating a broad authority such as `admin:all` and assigning it to every operational account. The more granular the permissions, the clearer granting, revoking, and testing become.

### 2.1. How Do Roles and Authorities Differ?

Roles typically describe broad responsibility groups, whereas authorities describe specific permissions that code can check.

| Check | Matched Value |
| --- | --- |
| `hasRole("OPS")` | `ROLE_OPS` authority using the default prefix |
| `hasAuthority("registry:drain")` | Exact `registry:drain` authority |
| `hasAnyAuthority("registry:read", "registry:drain")` | Any of the listed authorities |

`@WithMockUser(roles = "OPS")` automatically prepends `ROLE_`. `@WithMockUser(authorities = "registry:drain")` preserves the authority name verbatim. When the application uses `domain:action` permissions, test with authorities to avoid role prefix mismatches.

A role hierarchy can grant inherited permissions, such as `ROLE_PLATFORM_ADMIN` including `registry:read` and `registry:drain`. When using a hierarchy, tests must verify both inherited permissions and non-inherited permissions; otherwise, a hierarchy change can inadvertently broaden access.

## 3. Protecting Both the Request Layer and Service Layer

Request-level authorization guards HTTP entry points. Method security guards operations at the service layer, even when the service is invoked from another controller, message listener, or another Spring component.

These two layers complement each other:

- HTTP security determines which requests can enter administrative routes.
- Method security determines whether the principal may execute a specific action.
- Resource-level checks determine whether the principal holds permission on the exact requested service, tenant, or instance.

Never guard only the URL and assume every call to the service arrives via that controller. Likewise, never omit a catch-all rule at the HTTP layer because method security protects only annotated methods.

## 4. Permission Design Example for Registry Admin

### 4.1. Enabling Method Security

Spring Security does not automatically enable method authorization simply because the application includes the Spring Boot Security starter. You must declare:

```java
@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Once enabled, Spring Security can apply `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` to Spring-managed beans. This relies on Spring AOP; always invoke services through Spring-managed bean proxies.

### 4.2. Declaring Permissions on Service Methods

The service allows only principals with the `registry:drain` authority to call drain:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class RegistryAdminService {

    private final RegistryRepository repository;

    public RegistryAdminService(RegistryRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('registry:drain')")
    public void drain(String instanceId) {
        repository.markDraining(instanceId);
    }

    @PreAuthorize("hasAuthority('registry:register')")
    public void register(RegistrationRequest request) {
        repository.register(request);
    }

    @PreAuthorize("hasAuthority('registry:deregister')")
    public void deregister(String instanceId) {
        repository.remove(instanceId);
    }
}
```

Each method requires the exact authority for its action. Holding `registry:read` does not automatically grant drain or deregister permissions.

### 4.3. Protecting HTTP Routes

The request layer can enforce the same matrix:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class AdminHttpSecurityConfiguration {

    @Bean
    SecurityFilterChain adminSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/admin/registry/**")
                .hasAuthority("registry:read")
            .requestMatchers(HttpMethod.POST, "/admin/registry/*/drain")
                .hasAuthority("registry:drain")
            .requestMatchers(HttpMethod.POST, "/admin/registry")
                .hasAuthority("registry:register")
            .requestMatchers(HttpMethod.DELETE, "/admin/registry/**")
                .hasAuthority("registry:deregister")
            .anyRequest().denyAll()
        );
        // HTTP Basic illustrates the authentication entry point for APIs.
        // Applications using JWT can configure oauth2ResourceServer instead.
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`anyRequest().denyAll()` establishes a default-deny rule for unlisted routes. If the application serves other business routes, separate security chains or add required matchers before the catch-all; never let a new route accidentally fall back to requiring only `authenticated()`.

HTTP Basic here merely illustrates an entry point returning 401 for unauthenticated requests. A real application still needs an appropriate `AuthenticationProvider`, `UserDetailsService`, or OAuth2 Resource Server to validate credentials; enabling `httpBasic` alone does not create user identities or permissions.

### 4.4. Controller Delegating to the Service

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/registry")
public class RegistryAdminController {

    private final RegistryAdminService adminService;

    public RegistryAdminController(RegistryAdminService adminService) {
        this.adminService = adminService;
    }

    @PostMapping("/{instanceId}/drain")
    ResponseEntity<Void> drain(@PathVariable String instanceId) {
        adminService.drain(instanceId);
        return ResponseEntity.noContent().build();
    }
}
```

Both the HTTP matcher and `@PreAuthorize` require `registry:drain`. Repeating the policy across both layers is intentional: routes are constrained at the HTTP boundary while the service stays protected if invoked through another path.

## 5. Designing Tests from the Permission Matrix

For a drain operation, a baseline matrix can look like this:

| Principal | Authority | Expected HTTP Result | Service Invoked? |
| --- | --- | --- | --- |
| Anonymous | None | `401 Unauthorized` | No |
| Viewer | `registry:read` | `403 Forbidden` | No |
| Deployer | `registry:register` | `403 Forbidden` | No |
| Operator | `registry:drain` | `204 No Content` | Yes |
| Admin | `registry:read`, `registry:drain`, `registry:deregister` | `204 No Content` | Yes |

For write operations, confirm rejected requests do not alter the registry. Asserting 403 alone is insufficient if code can mutate data before checking permissions.

Include both positive and negative tests for every action. If a route only tests that an administrator succeeds, that test will miss a bug where the route allows any authenticated user.

## 6. Testing Service Methods Directly

Method-security tests verify permissions directly at the service layer without going through an HTTP controller.

### 6.1. Testing Allowed Authority

These imports and tests use JUnit 5, AssertJ, Spring Test, and Spring Security Test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
```

```java
@SpringBootTest
class RegistryAdminServiceSecurityTests {

    @Autowired
    RegistryAdminService adminService;

    @Test
    @WithMockUser(authorities = "registry:drain")
    void operatorWithDrainAuthorityCanDrain() {
        assertThatCode(() -> adminService.drain("instance-17"))
            .doesNotThrowAnyException();
    }
}
```

### 6.2. Testing a Principal Missing Authority

```java
@Test
@WithMockUser(authorities = "registry:read")
void readOnlyUserCannotDrain() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));
}
```

### 6.3. Testing a Similar but Incorrect Authority

```java
@Test
@WithMockUser(authorities = "registry:register")
void registerAuthorityDoesNotGrantDrain() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));
}
```

These tests must inject the `RegistryAdminService` bean from the ApplicationContext. If you instantiate the object with `new RegistryAdminService(...)`, the Spring AOP proxy is bypassed and `@PreAuthorize` will not run.

`@WithMockUser` places a mock Authentication into SecurityContext for the test. `roles` automatically prepends `ROLE_`; `authorities` uses the exact declared strings. The mock user does not need to exist in a database, so this focuses on testing authorization rules rather than login flows.

`@WithMockUser` fits tests calling Spring beans directly on the test thread. With MockMvc, you can use the `user()` request post-processor to attach Authentication to an HTTP request. For end-to-end tests sending requests to a server running on another thread, authenticate requests using real HTTP Basic or bearer tokens.

## 7. Testing HTTP with MockMvc

HTTP tests run through the Spring Security filter chain to verify that request matchers, authentication, and method security work together properly.

### 7.1. Test Setup

Add the `spring-security-test` dependency in test scope. To avoid version mismatches with the Spring Security runtime, let the Spring Boot BOM or Spring Security BOM manage the version rather than picking a standalone version. With Spring Boot 4, the `@AutoConfigureMockMvc` package resides in the webmvc test module:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

### 7.2. Testing Anonymous and Unauthorized Authenticated Users

```java
@SpringBootTest
@AutoConfigureMockMvc
class RegistryAdminHttpSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotDrain() throws Exception {
        mockMvc.perform(post("/admin/registry/instance-17/drain")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readOnlyUserCannotDrain() throws Exception {
        mockMvc.perform(post("/admin/registry/instance-17/drain")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("registry:read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

The anonymous test still includes a valid CSRF token so the result reflects authentication. If you omit the token, the CSRF filter may return 403 before the request reaches authentication; the test would then fail to prove anonymous callers are rejected for lacking login.

In the HTTP Basic example in section 4.3, anonymous receives 401 because no Authentication is present. Logged-in users lacking the required authority receive 403. If your application uses form login, OAuth2 Resource Server, or a custom entry point, the anonymous response may be a redirect or another status; assert against your API's actual entry point.

### 7.3. Testing Permitted Authority

```java
@Test
void operatorWithDrainAuthorityCanDrain() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(user("operator").authorities(
                new SimpleGrantedAuthority("registry:drain")
            ))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
```

### 7.4. Testing That a Role Does Not Automatically Become a Permission

```java
@Test
void genericOpsRoleDoesNotGrantDrainPermission() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(user("ops").roles("OPS"))
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

This test holds only when the application does not configure a `RoleHierarchy` mapping `ROLE_OPS` to `registry:drain`. If a hierarchy exists, test inheritance policies according to your actual configuration.

The test snippets above illustrate individual methods in the same test class; when assembling them, place them inside `RegistryAdminHttpSecurityTests`.

## 8. CSRF Is a Separate Testing Dimension

Spring Security protects unsafe HTTP methods such as POST, PUT, PATCH, and DELETE with CSRF tokens by default in standard session-based configurations.

Therefore, tests for a state-changing administrative operation must distinguish:

- Missing CSRF token: the request may be rejected at the CSRF filter.
- Valid CSRF token but unauthenticated: rejected by the authentication layer.
- Authenticated but missing authority: rejected by the authorization layer.
- Sufficient authority and valid CSRF token: request is processed.

Example confirming CSRF protection remains active:

```java
@Test
@WithMockUser(authorities = "registry:drain")
void postWithoutCsrfTokenIsRejected() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain"))
        .andExpect(status().isForbidden());
}
```

Keep this test separate from missing-authority tests. Never disable CSRF globally just to make POST tests easier to run. For stateless APIs using bearer tokens, the CSRF decision depends on how credentials are transmitted and whether a browser can attach credentials automatically; configure according to your threat model and test that exact configuration.

## 9. Testing JWTs and Authority Mapping

If the API uses OAuth2 Resource Server with JWT, permissions inside the token are typically converted to `GrantedAuthority` instances by a `JwtAuthenticationConverter`. Test the claim-to-authority mapping as well.

### 9.1. Using jwt() to Test Authorization

Spring Security Test's `jwt()` creates a mock `JwtAuthenticationToken` for MockMvc. Authorities can be assigned directly:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void jwtWithDrainAuthorityCanDrain() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("registry:drain")
            ))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
```

This tests authorization once an Authentication already exists. It does not verify JWT signatures, issuer, audience, expiry, or decoder configuration.

### 9.2. Testing the Converter Separately

If tokens carry a `permissions` claim listing `registry:read` and `registry:drain`, test that the converter produces the exact expected authorities. Include tests for:

- Claim containing full permissions.
- Claim containing read-only permissions.
- Missing claim.
- Malformed claim type or invalid values.
- Default scopes not inadvertently turning into administrative permissions.

### 9.3. Integration Tests for Real Bearer Tokens

To verify the entire authentication pipeline, write integration tests using JWTs signed with a test key or test issuer. Verify the decoder, issuer/audience validators, converter, and filter chain together in one request flow. `jwt()` is great for isolating authorization, yet does not replace token verification tests.

## 10. Testing Resource-Level Permissions and Preventing IDOR

Holding the `registry:drain` authority does not necessarily mean a user may drain every instance. In multi-tenant systems, permissions must be further scoped by tenant, service, or resource owner.

Example:

```java
// Add resource-level condition to the drain method declared in section 4.2.
@PreAuthorize("hasAuthority('registry:drain') and " +
        "@registryAuthorization.canManage(authentication, #p0)")
public void drain(String instanceId) {
    repository.markDraining(instanceId);
}
```

`RegistryAuthorization` is a Spring bean with a `canManage(Authentication, String)` method. The `#p0` expression references the first parameter, avoiding reliance on whether the compiler preserves parameter names. This bean verifies whether the principal has permission to manage that specific instance. When writing tests, create at least two resources belonging to two different tenants:

1. User of tenant A drains an instance of tenant A: allowed.
2. User of tenant A drains an instance of tenant B: denied.
3. User lacking `registry:drain` yet belonging to tenant A: still denied.

Never check permissions solely on URLs or roles. If an API accepts `instanceId` from clients without checking resource-level authorization, callers can swap IDs in requests to access another tenant's resources.

`@PostAuthorize` can protect returned data by owner, yet is unsuitable for protecting state-mutating methods: the method has already executed its side effect before the post-condition is evaluated. For state-changing administrative operations, verify permissions before mutating state.

## 11. Testing Side Effects When Rejected

A thorough authorization test verifies that a rejected operation never calls the repository, emits events, or sends commands to providers.

Example with Mockito:

In integration tests, replace `RegistryRepository` with a mock bean to confirm write operations are never invoked:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@MockitoBean
RegistryRepository registryRepository;
```

```java
@Test
@WithMockUser(authorities = "registry:read")
void deniedDrainDoesNotChangeRegistry() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));

    verify(registryRepository, never()).markDraining("instance-17");
}
```

These assertions verify an invariant more important than status codes: no administrative action executes before permissions are confirmed.

For systems using message brokers, also confirm no command is published when a principal is denied. If a method includes retries, transactions, or audit events, specify which side effects are allowed on a denial and test them separately.

## 12. Common Pitfalls When Testing Least Privilege

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@PreAuthorize` has no effect | `@EnableMethodSecurity` not enabled | Check method security configuration |
| Method security test always passes | Service created with `new`, bypassing Spring proxy | Inject bean from ApplicationContext |
| User has `ROLE_OPS` but authority test mismatches | `roles` automatically prepends `ROLE_` | Use `authorities` for granular permissions |
| User lacks permission yet POST returns 403 due to CSRF | CSRF filter rejects before authorization | Send valid CSRF in authorization tests; keep CSRF tests separate |
| Controller test passes yet calling service elsewhere succeeds | Only HTTP routes protected | Add method security at the service boundary |
| New route defaults to allowing all logged-in users | Missing catch-all deny rule | Use `anyRequest().denyAll()` or equivalent fallback rule |
| Admin test passes yet viewer can also perform action | Only positive tests exist | Add negative tests for every authority |
| Tenant A user accesses tenant B data | Checked only role without object-level authorization | Check tenant/owner before side effects |
| `jwt()` test passes yet real tokens are rejected | Decoder, validator, or authority converter untested | Add integration tests with tokens signed by a test key |
| POST test fails despite having authority | Missing or invalid CSRF token | Use `csrf()` in authorization tests |
| Permissions expand after adding a role hierarchy | Role inherited unintended authorities | Test both inherited and ungranted permissions |
| Unannotated method can still be called | Method security does not automatically guard unannotated methods | Add request catch-all rules and audit service boundaries |

## 13. Least-Privilege Testing Checklist

1. List all administrative operations and dedicated authorities per action.
2. Deny unlisted routes by default.
3. Enable `@EnableMethodSecurity` when using method authorization.
4. Protect state-changing service methods, not just controllers.
5. Test anonymous callers, authenticated callers lacking permission, and principals with exact authorities.
6. Distinguish `roles` from `authorities` in tests.
7. Test CSRF independently from authorization for write requests.
8. When using JWT, test both authority mapping and token validation.
9. Verify tenant/resource ownership checks to prevent IDOR.
10. Confirm denied requests write no data, publish no events, and call no providers.
11. Test role hierarchies to catch unintended inherited permissions.
12. Invoke services through Spring proxies in method-security tests.
13. Use integration tests for real authentication flows and unit tests for individual authorization rules.

## 14. References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, authorities, request-level and method-level authorization.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and testing method authorization.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF tokens and testing unsafe requests.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/): MockMvc integration and request post-processors.

Least privilege is proven through a complete test matrix: each principal can perform only its granted actions, all remaining actions are denied, and rejected requests produce zero side effects. Verify the request boundary, service boundary, and resource-specific permissions so administrative policies remain intact as the application gains new controllers or call paths.
