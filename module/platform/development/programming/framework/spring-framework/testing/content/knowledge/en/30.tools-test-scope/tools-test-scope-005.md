# Spring Security Test Is a Separate Integration When Verifying Authentication and Authorization

Spring MVC and WebFlux can process requests without enabling Spring Security. When an application has authentication or authorization, tests need to bring the security filter chain and `SecurityContext` into the request flow. The `spring-security-test` module provides dedicated tools to prepare user identities, tokens, CSRF tokens, and to integrate Spring Security with MockMvc or WebTestClient.

This is a separate test dependency. `spring-boot-starter-test` provides the common testing foundation, but does not automatically substitute for declaring `spring-security-test`. Add this module only when tests need to verify the application's security behavior.

## 1. What Problem Does Spring Security Test Solve?

A typical controller test might only check the returned data. However, when an application uses security, the outcome of a request also depends on the authenticated identity, authorities, CSRF tokens, and access control rules.

Spring Security Test helps tests simulate or supply those details in a controlled manner:

- Create an authenticated user with specific username, roles, or authorities.
- Use the test context's real `UserDetailsService` to load a user.
- Prepare an anonymous user, JWT, or OAuth2 authentication within the scope of the test.
- Send valid or invalid CSRF tokens.
- Wire the Spring Security filter chain into MockMvc or WebTestClient.
- Populate `SecurityContext` for a test method to verify method security such as `@PreAuthorize`.

These tools let you test the security decisions the application makes. Distinguish tests using a mock identity from tests verifying the actual login flow or token verification; each answers a different question.

## 2. Adding the Separate Dependency

With Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
```

With Maven:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Keep the `spring-security-test` version aligned with the Spring Security version used in the application. If the project uses Spring Boot dependency management or the Spring Security BOM, let the BOM manage the version to avoid API mismatches across modules.

`spring-security-test` is a test-scoped dependency. Do not include it on the production application's runtime classpath.

## 3. Integrating Spring Security with MockMvc

In a Spring MVC application, MockMvc must run through the security filter chain if you want to verify authentication and authorization at the HTTP layer. When building MockMvc manually from `WebApplicationContext`, apply the `springSecurity()` configurer:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` connects MockMvc to the Spring Security components configured in the application context, including the filter chain and security context saving/restoring appropriate for tests.

With Spring Boot, `@AutoConfigureMockMvc` normally registers servlet filters from the application context with MockMvc by default:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AccountControllerSecurityTests {

    @Autowired
    MockMvc mockMvc;
}
```

If you set `@AutoConfigureMockMvc(addFilters = false)`, servlet filters in the context will not participate in MockMvc requests. That setting can be useful for MVC tests that ignore filters, but it prevents the test from verifying the behavior of the Spring Security filter chain. Do not disable filters in tests checking security.

With `@WebMvcTest`, check whether the security configuration is included in the slice. You may need to import the application's security configuration with `@Import(SecurityConfig.class)` so the test runs the real rules.

## 4. Creating a Mock User with @WithMockUser

`@WithMockUser` places a mock `Authentication` into `SecurityContext` before the test method runs. It is a concise way to test authorization without performing a login flow.

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanReadReports() throws Exception {
    mockMvc.perform(get("/admin/reports"))
            .andExpect(status().isOk());
}
```

In this example, Spring Security Test creates user `alice` with authority `ROLE_ADMIN`. The `roles` attribute automatically prepends the `ROLE_` prefix. Thus `roles = "ADMIN"` corresponds to `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`.

You can declare multiple roles:

```java
@WithMockUser(username = "alice", roles = {"ADMIN", "AUDITOR"})
```

Or declare exact authorities:

```java
@Test
@WithMockUser(username = "report-reader",
        roles = {},
        authorities = {"reports:read", "orders:view"})
void userWithReportAuthorityCanReadReports() throws Exception {
    mockMvc.perform(get("/reports"))
            .andExpect(status().isOk());
}
```

`roles` and `authorities` are two different ways to declare authorities; do not use them simultaneously in the same annotation. `authorities` keeps the exact names supplied without automatically adding `ROLE_`.

If username is not specified, Spring Security Test uses the default name `user`; the default role is `USER`. Declare the identity and permissions explicitly in tests so the test's intent is easy to read.

## 5. Testing Both Allowed and Denied Cases

A solid authorization test typically covers both permitted and unauthorized cases. For example, an endpoint restricted to ADMIN:

```java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanOpenAdminPage() throws Exception {
    mockMvc.perform(get("/admin"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(roles = "USER")
void regularUserCannotOpenAdminPage() throws Exception {
    mockMvc.perform(get("/admin"))
            .andExpect(status().isForbidden());
}
```

A 403 result indicates the user is authenticated but lacks sufficient permissions. If a request has no authenticated identity and the endpoint requires login, the result is typically 401 or a redirect to the login page depending on the authentication mechanism and application configuration.

Distinguishing these two scenarios helps the test describe the rules accurately:

| State | Common meaning | Typical outcome |
|---|---|---|
| Unauthenticated | No valid Authentication present | 401 or redirect to login |
| Authenticated, insufficient privileges | Authentication exists but authorities do not satisfy the rule | 403 Forbidden |
| Authenticated, sufficient privileges | Authentication and authorities satisfy the rule | Endpoint processes normally |

Do not check only the status of a single happy path. An authorization rule needs to prove that an authorized user is allowed and an under-privileged user is rejected.

## 6. Using @WithUserDetails When a User Must Come from UserDetailsService

`@WithMockUser` creates a mock `User` directly. If the test needs a user loaded from the application's `UserDetailsService`, use `@WithUserDetails`:

```java
@Test
@WithUserDetails("alice")
void usesUserLoadedByUserDetailsService() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isOk());
}
```

The test context must contain a `UserDetailsService` and user `alice` must exist in the data source that service reads. This is useful when authorities are assigned dynamically from test data or when the application uses a custom `UserDetails`.

You can specify the bean name if the context has multiple `UserDetailsService` beans:

```java
@WithUserDetails(value = "alice", userDetailsServiceBeanName = "accountUserDetailsService")
```

`@WithAnonymousUser` can be used to run a method with anonymous authentication, for example when the class has `@WithMockUser` but one test needs to verify anonymous access:

```java
@Test
@WithAnonymousUser
void anonymousUserCannotOpenProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
}
```

The exact status also depends on the application's entry point; if the application redirects to a login page, assert according to that redirect contract.

## 7. Setting a User Directly per Request with user(...)

Instead of annotating the test method, you can use a `RequestPostProcessor` to attach an identity to a specific request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/admin").with(user("alice").roles("ADMIN")))
        .andExpect(status().isOk());
```

This is useful when a single test sends multiple requests with different identities:

```java
@Test
void comparesTwoUsers() throws Exception {
    mockMvc.perform(get("/reports").with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk());

    mockMvc.perform(get("/reports").with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
}
```

You can pass a pre-built `UserDetails`:

```java
UserDetails account = User.withUsername("alice")
        .password("unused")
        .authorities("reports:read")
        .build();

mockMvc.perform(get("/reports").with(user(account)))
        .andExpect(status().isOk());
```

`user(...)` sets up an authentication for the test. It does not run the password encoder, verify passwords, or test form login or HTTP Basic authentication mechanisms. Use it to focus on authorization rules once the identity is established.

## 8. Testing CSRF Tokens

When CSRF protection is enabled, state-changing requests such as POST, PUT, PATCH, or DELETE normally require a valid CSRF token. Spring Security Test provides `csrf()` to add a token to a MockMvc request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf())
        .param("displayName", "Alice"))
        .andExpect(status().is3xxRedirection());
```

You can place the token in a header instead of a request parameter:

```java
mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf().asHeader())
        .param("displayName", "Alice"))
        .andExpect(status().is3xxRedirection());
```

Testing requests with a missing or invalid token:

```java
mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
```

When a POST test receives 403, determine whether the cause is CSRF or authorization. If the test's goal is endpoint authorization and CSRF is enabled, supply a valid token with `csrf()` so the request passes the CSRF check before evaluating authorization rules. Write a separate test for missing or invalid CSRF tokens.

## 9. Testing HTTP Basic and Real Authentication Mechanisms

If the goal is to verify that the HTTP Basic authentication filter processes credentials, use the `httpBasic(...)` processor instead of `user(...)`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;

mockMvc.perform(get("/account").with(httpBasic("alice", "correct-password")))
        .andExpect(status().isOk());
```

The request is sent with HTTP Basic credentials so the security filter chain performs authentication according to the application's configuration. The test requires an `AuthenticationManager` and a `UserDetailsService` or appropriate provider in the context.

Comparison:

| Preparation method | What is set up | What the test can verify |
|---|---|---|
| `user("alice")` | Mock authentication on the request | Authorization rules for the given identity and privileges |
| `@WithMockUser` | Mock SecurityContext around the test method | Method security or logic relying on SecurityContext |
| `httpBasic("alice", "...")` | HTTP Basic credentials on the request | Basic authentication filter and credential verification in the chain |
| `@WithUserDetails("alice")` | User loaded via UserDetailsService | Authorities and custom user details from the test user store |

Even with `httpBasic(...)`, MockMvc tests still do not open a real HTTP port. They test the filter chain and authentication provider within the test context. If you need to test TLS, reverse proxies, or network behavior, use an integration test against a real server.

## 10. Testing JWT and OAuth2

For a Resource Server using JWT, Spring Security Test provides `jwt()` to create a mock JWT authentication for the request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

You can customize claims or the subject:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().jwt(token -> token
                .subject("alice")
                .claim("tenant", "tenant-42"))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

For OAuth2 Login, processors such as `oauth2Login()` exist; for opaque token resource servers, `opaqueToken()` is available. They set up the corresponding authentication to test the authorization part of the request.

A JWT created by the test processor does not prove the application verifies signatures, issuers, audiences, or invokes the right `JwtDecoder`. If the goal is to test real token verification, test the `JwtDecoder`/authentication converter or send a token signed with a test key against the real resource server configuration.

## 11. Integrating with WebTestClient for WebFlux

WebFlux applications using `WebTestClient` have a separate set of configurers in Spring Security Test. When building the client from an application context, apply `springSecurity()`:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .build();
```

You can attach a mock user to a request:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/admin")
        .exchange()
        .expectStatus().isOk();
```

In WebFlux tests, use `mutateWith(...)` to apply WebTestClient configurers. Do not pass MockMvc's `RequestPostProcessor` to WebTestClient because the two APIs belong to different stacks.

When using a Spring Boot test with a reactive server, you can inject the `WebTestClient` configured by Boot. When verifying the security filter chain, ensure requests actually pass through the application's security configuration; a test bound directly to a controller without adding security config will not enforce those rules.

## 12. Testing Method Security

Spring Security Test is also useful when the application protects service methods with `@PreAuthorize` or `@PostAuthorize`. The test must enable method security in the Spring configuration:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Service:

```java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('reports:read')")
    public Report loadReport(String id) {
        return new Report(id);
    }
}
```

The test uses `@WithMockUser` to populate `SecurityContext` before calling the service:

```java
@SpringJUnitConfig(classes = {MethodSecurityConfig.class, ReportService.class})
class ReportServiceSecurityTests {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(roles = {}, authorities = "reports:read")
    void userWithAuthorityCanLoadReport() {
        assertThat(reportService.loadReport("R-42").id()).isEqualTo("R-42");
    }

    @Test
    @WithMockUser(roles = {}, authorities = "profile:read")
    void userWithoutAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.loadReport("R-42"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

This test verifies that the method security interceptor enforces rules on the service. It does not require MockMvc since it does not test an HTTP request; if you need to test both the endpoint and method security, you can combine a web context with MockMvc.

## 13. Creating Custom Security Annotations for Tests

If many tests share the same set of privileges, you can create a meta-annotation to reduce duplication:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "report-admin", roles = {}, authorities = "reports:admin")
public @interface WithReportAdmin {}
```

Usage:

```java
@Test
@WithReportAdmin
void reportAdminCanManageReports() throws Exception {
    mockMvc.perform(delete("/reports/42"))
            .andExpect(status().isNoContent());
}
```

For a more complex security context, you can create an annotation using `@WithSecurityContext` and a `WithSecurityContextFactory` to construct a domain-specific principal or authentication. This fits when the application uses a custom principal carrying tenant, organization, or user metadata.

## 14. Spring Security Test Does Not Verify Everything Automatically

Choose the test helper based on the question you need to verify:

| Question | Suitable tool |
|---|---|
| Can a user with authority A access the endpoint? | `@WithMockUser`, `user(...)`, or `mockUser()` |
| Is a user lacking the authority rejected? | Mock user with missing privilege and assert 403/AccessDenied |
| What authorities does a user loaded from UserDetailsService have? | `@WithUserDetails` |
| How does the HTTP Basic filter authenticate credentials? | `httpBasic(...)` with real security chain and provider in the test context |
| Is a request rejected when missing a CSRF token? | `csrf()` and `csrf().useInvalidToken()` |
| Which authorities does a JWT authentication carry? | `jwt()` for authorization; test the decoder separately when verifying tokens |
| Is a service method protected by @PreAuthorize? | `@WithMockUser` together with `@EnableMethodSecurity` |

`@WithMockUser`, `user(...)`, `jwt()`, and `mockUser()` typically create mock authentications. They are very effective for checking authorization rules, but do not prove that password handling, token signatures, OAuth2 redirects, or fetching users from a real store work properly.

## 15. Common Errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Request always returns 401/redirect despite @WithMockUser | MockMvc is not wired through Spring Security integration or the test context lacks security configuration | Use `.apply(springSecurity())` or Boot config with filter registration enabled |
| Request returns 403 even though user has the role | Confusing `roles` with `authorities`, or role missing `ROLE_` prefix | Check `hasRole`/`hasAuthority` and actual authority names |
| POST returns 403 in tests | CSRF protection is enabled and the request lacks a token | Add `.with(csrf())`; write a separate test for invalid/missing tokens |
| @WithUserDetails cannot find the user | User does not exist in the test context's UserDetailsService | Seed the user or use `@WithMockUser` if only testing authorization |
| `httpBasic(...)` still fails to authenticate | Basic authentication is not enabled or the provider rejects credentials | Check the filter chain, AuthenticationManager, password encoder, and test user |
| JWT test passes even with a bad signature | `jwt()` creates a mock authentication, bypassing decode/signature verification | Write decoder tests or integration tests with a JWT signed by a test key |
| WebTestClient ignores mock user | Using a MockMvc processor or forgetting to apply the reactive security configurer | Use `springSecurity()` and `mutateWith(mockUser())` |
| Method security does not block calls | `@EnableMethodSecurity` is not enabled or calling the method without going through the proxy | Enable method security and invoke the Spring-managed bean |

## 16. Summary

`spring-security-test` is a separate module used when tests need to verify authentication, authorization, CSRF, or method security. With MockMvc, integrate the filter chain using `springSecurity()` and prepare users with `@WithMockUser`, `@WithUserDetails`, `user(...)`, `httpBasic(...)`, or `jwt()`. With WebFlux, apply the reactive `springSecurity()` configurer and use `mutateWith(mockUser())`. Mock identities make checking authorization fast, whereas real authentication flows such as passwords, JWT signatures, or OAuth2 login require dedicated tests. Always test both allowed and denied cases to ensure security rules work properly.

