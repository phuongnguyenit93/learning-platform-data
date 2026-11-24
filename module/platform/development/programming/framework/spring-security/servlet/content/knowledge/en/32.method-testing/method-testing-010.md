# Distinguishing Simulated Identities from Testing a Real AuthenticationProvider

> **Scope:** Spring Security on the Servlet stack (Spring Boot 3.x, Spring Security 6.x, Java 17+, JUnit Jupiter, MockMvc). This article focuses on testing **method security** and **authentication** mechanisms: an identity pre-populated in `SecurityContext` can test authorization, yet **does not prove `AuthenticationProvider` verified passwords, account status, tokens, or real identity sources**.

## 1. Why Are These Two Types of Testing Often Confused?

Suppose you have a method:

```java
@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
public String approve(String paymentId) {
    return "approved:" + paymentId;
}
```

A test writes:

```java
@Test
@WithMockUser(username = "alice", authorities = "PAYMENT_APPROVE")
void aliceCanApprove() {
    assertEquals("approved:123", paymentService.approve("123"));
}
```

This test is useful: it shows **the method-security rule allows** an `Authentication` carrying authority `PAYMENT_APPROVE`. However, it **does not prove** user `alice` exists, her password is right, her account is unlocked, an LDAP bind succeeded, a JWT signature is valid, or MFA was satisfied.

In practice, separate two questions:

1. **Authorization:** *Given* Spring Security already holds a principal with a certain set of authorities, which methods may that principal call? This is the natural target of `@WithMockUser`, `@WithUserDetails`, `user(...)`, or `jwt()` test fixtures.
2. **Authentication:** Given **unauthenticated credentials** (username/password, bearer token, certificate...), do `AuthenticationManager`/`AuthenticationProvider` or the corresponding filter actually verify credentials, account status, and required policies?

These two test groups **complement each other** rather than replacing each other. A system can pass all `@WithMockUser` tests while production login fails or admits locked accounts. Conversely, a provider that verifies passwords properly while method security misconfigures `permitAll` still leaves an authorization flaw.

## 2. Four Spring Security Layers to Observe Separately

For web MVC, a basic flow is:

```text
HTTP request: Authorization: Basic ...
      |
      v
SecurityFilterChain / authentication filter
      |    extracts unauthenticated credentials
      v
AuthenticationManager (typically ProviderManager)
      |    selects AuthenticationProvider supporting token type
      v
AuthenticationProvider
      |    loads user / verifies password / checks status
      v
Authenticated Authentication + GrantedAuthority
      |
      v
SecurityContextHolder (request context)
      |
      v
Spring MVC Controller -> Bean method-security proxy
      |    evaluates @PreAuthorize/@PostAuthorize
      v
Business method or AccessDeniedException
```

Separating responsibilities clearly:

| Component | Responsibility | Appropriate Test |
|---|---|---|
| `Authentication` | Carries principal, credentials, authorities, and authenticated flag | Assertions on principal/authorities; not self-proving credential validity |
| `SecurityContextHolder` | Supplies the security context for the current thread/request | `@WithMockUser` and method-security tests |
| `AuthenticationManager` | Coordinates authentication requests | Call `authenticate(...)` with an unauthenticated token |
| `AuthenticationProvider` | Executes concrete credential/identity verification | Provider-level integration tests with valid/invalid/locked data |
| HTTP authentication filter | Turns HTTP headers/forms/cookies into input `Authentication`; handles success/failure | `MockMvc` through `SecurityFilterChain`, without mocking the principal |
| `SecurityFilterChain` | Selects filters, CSRF, session, authentication entry point, and URL authorization | `MockMvc` with filters enabled |
| Method security interceptor | Protects method calls via proxy per `@PreAuthorize` | Tests calling an **injected Spring bean**, not `new` |
| User store/IdP/LDAP/JWT decoder | Supplies data needed for verification | Integration/E2E tests with safe fixtures or contracted mock external systems |

In Spring Security, `ProviderManager` picks providers whose `supports(authentication.getClass())` matches; a provider may return an authenticated `Authentication`, abstain (null), or throw `AuthenticationException`. Provider ordering, exception handling, and parent manager policies must be tested when a system uses multiple mechanisms.

**Never confuse `AccessDeniedException` with `AuthenticationException`.** The first normally means the user already has an identity yet **lacks permission**; the second relates to **failing to verify credentials or account status**. Over HTTP, 401/302/403 also depend on filters, entry points, CSRF, anonymous/remember-me, and configuration, so never guess solely from status codes.

## 3. Quick Comparison of Fixtures and Testing Paths

| Testing Approach | Where Identity Comes From | Checks Password/Provider? | Good For Verifying |
|---|---|---|---|
| `@WithMockUser(username="alice", roles="ADMIN")` | Annotation creates test `SecurityContext` | **No** | `@PreAuthorize`, `hasRole`, authorities, authorization logic |
| `@WithUserDetails("alice")` | `UserDetailsService` loads principal in fixture | **Does not verify password**; calls user-loading service | Authority mapping from user fixture, principal type, user lookup |
| Custom `@WithSecurityContext` factory | Factory builds principal/`Authentication` | No, unless the factory itself is built to perform real checks (not recommended as default provider test) | Custom principals, tenants, simulated claims/attributes |
| MockMvc `.with(user("alice"))` | Request post-processor creates identity | **No** | HTTP authorization and method security with a fixed user |
| MockMvc `.with(jwt())` | Helper builds a JWT authentication fixture | **Does not verify real JWT signatures** in typical setups | Claims/authority mapping in layers consuming the auth fixture |
| MockMvc `.with(httpBasic("alice","password"))` | Adds HTTP Basic header to request | **Yes, if request passes through real Basic filter and manager/provider** | HTTP authentication, password/account status, and 401/403 |
| `AuthenticationManager.authenticate(unauthenticatedToken)` | Credential input passed directly to manager | **Yes**, at the selected provider | Credential rules, encoder, disabled/locked accounts, provider selection |
| Browser E2E/HTTP through real container | Real request over network and infra | Yes, depending on flow | TLS, reverse proxies, cookies, sessions, MFA/SSO, full end-to-end |

The two most important rows: **`@WithMockUser` is an authenticated fixture**, whereas **`httpBasic(...)` only attaches unauthenticated credentials to a request**. The latter actually reaches the provider **only if** `MockMvc` has Spring Security filters enabled and endpoints/chains use an HTTP Basic provider matching the system under test.

### 3.1. Why Can @WithMockUser "Log In" a Non-Existent User?

`@WithMockUser` is processed by Spring TestContext's `WithSecurityContextTestExecutionListener`. The listener creates a `SecurityContext` with a simulated `Authentication` and installs it before the test. It never checks a user store.

Therefore:

```java
@Test
@WithMockUser(username = "nonexistent-user", roles = "ADMIN")
void authorizationRuleCanStillAllowThisMockIdentity() {
    // If the method only requires ROLE_ADMIN, the test can still PASS.
}
```

That is **not a framework bug**. The purpose is isolating permission rules from the login process. To prove an unknown username is rejected, run through a real manager/provider or HTTP filter with that username's credentials.

### 3.2. @WithUserDetails Is Not a Password Test Either

`@WithUserDetails("reader")` calls `UserDetailsService.loadUserByUsername("reader")` to retrieve the fixture; the listener then creates the context. It **does not pass a raw password through `PasswordEncoder.matches(...)`** and does not run full `DaoAuthenticationProvider` pre/post login checks.

Thus a `@WithUserDetails` test can show that a user fixture carries `REPORT_READ`, yet it does not prove passwords are right, locked users are blocked on login, or expired credentials are handled.

## 4. Real Authentication Signal: Raw Credentials Must Pass Through a Provider

In the username/password model, unauthenticated input typically looks like:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "reader", "reader-password");
```

This snippet only constructs an input token, **not yet authenticated**. Pass it via:

```java
Authentication result = authenticationManager.authenticate(request);
```

When the manager has a matching `DaoAuthenticationProvider`, the provider typically:

1. Looks up `UserDetails` via `UserDetailsService`.
2. Checks account status flags like disabled, locked, and expired per provider rules.
3. Calls `PasswordEncoder.matches(rawPassword, storedEncodedPassword)` to verify.
4. Builds an authenticated `Authentication` with authorities from the user store on success.
5. Throws an appropriate `AuthenticationException` when invalid. Many providers intentionally mask differences between unknown usernames and wrong passwords to mitigate enumeration.

**Never construct an authenticated token manually** and claim the provider ran. Also never call `SecurityContextHolder.getContext().setAuthentication(...)` in production from unverified client data: that bypasses the authentication boundary.

Upon success, `ProviderManager` may erase credentials on the resulting `Authentication` to minimize leaks. Therefore tests should assert **`result.isAuthenticated()`**, principal, and authorities, without assuming the raw password remains in `result.getCredentials()`.

### 4.1. Provider-Level Tests Do Not Represent All of HTTP

Calling `authenticationManager.authenticate(...)` directly measures core authentication behavior, yet **does not test** Basic header parsing, filter chains, security context persistence, sessions, CSRF, authentication entry points, or cookies. To verify the API is properly protected, add HTTP `MockMvc` tests.

Conversely, a `MockMvc` test using `@WithMockUser` passes through authorization filters and method proxies yet **skips password authentication**. Pick tests based on the question being verified, not on whether the test is short or long.

## 5. Three-Layer Testing Model

A high-confidence strategy usually comprises:

**Layer A — Method authorization:** create identity fixtures with `@WithMockUser`, call the Spring-proxied bean, and assert users with/without authorities succeed/fail. Very fast, easy to pinpoint faults.

**Layer B — Provider authentication:** submit unauthenticated input to `AuthenticationManager`, asserting right passwords succeed, wrong passwords/unknown usernames/disabled/locked accounts fail, and authorities map properly. Needs no network.

**Layer C — MVC security integration:** send `MockMvc` requests through the filter chain with real credentials (e.g. `httpBasic(...)`); assert 401 for missing/invalid credentials, 403 for valid users lacking permission, 200 for authorized users, 403 for POSTs missing CSRF, and 200 for valid credentials + permission + CSRF.

```text
Method test:
 @WithMockUser → SecurityContext → method proxy → authorize

Provider test:
 unverified username/password → AuthenticationManager
                             → DaoAuthenticationProvider
                             → UserDetailsService + PasswordEncoder

MVC integration:
 httpBasic(...) → SecurityFilterChain → AuthenticationManager
                → SecurityContext → Controller
                → method proxy → authorize
```

These three layers catch three distinct classes of bugs. Testing only Layer A misses misconfigured `PasswordEncoder`s and disabled accounts. Testing only Layer B misses missing `@EnableMethodSecurity` or services instantiated with `new`. Testing only Layer C with one admin account may leave under-privileged user rules under-tested.

## 6. Spring Boot 3.3.x + Java 17 Project: Runnable Illustrative Code

The goal is a small Servlet project with a **real provider** and a **real method-security proxy** to contrast the test types. It uses `InMemoryUserDetailsManager` as an **in-memory account store strictly for learning**, without calling a production database or IdP.

### 6.1. Gradle

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
```

File layout:

```text
src/
  main/java/demo/authcheck/
    AuthCheckApplication.java
    SecurityConfig.java
    ApprovalService.java
    ApprovalController.java
  test/java/demo/authcheck/
    MethodAuthorizationTest.java
    AuthenticationManagerTest.java
    HttpAuthenticationIntegrationTest.java
```

Classes use package `demo.authcheck`; create the Gradle project with a matching wrapper. All password strings below are **test fixtures** and must never be used in production.

### 6.2. Entry Point

`src/main/java/demo/authcheck/AuthCheckApplication.java`:

```java
package demo.authcheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthCheckApplication.class, args);
    }
}
```

### 6.3. Configuring Security and a Real AuthenticationManager

`src/main/java/demo/authcheck/SecurityConfig.java`:

```java
package demo.authcheck;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-local-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails approver = User.withUsername("approver")
            .password(encoder.encode("approver-local-pass"))
            .authorities("PAYMENT_APPROVE")
            .build();

        UserDetails blocked = User.withUsername("blocked")
            .password(encoder.encode("blocked-local-pass"))
            .authorities("PAYMENT_APPROVE")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(reader, approver, blocked);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http,
                                    AuthenticationManager manager)
            throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/payments/*/approve")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Key points:**

- `UserDetailsService` stores **BCrypt hashes**; raw passwords appear only in test fixtures. `DaoAuthenticationProvider` checks passwords via the encoder.
- User `blocked` has the right password yet `disabled(true)`. The provider must **reject** rather than admit it just because the password matches.
- `AuthenticationManager` is a `ProviderManager` bean wrapping a `DaoAuthenticationProvider`. The same manager is plugged into `HttpSecurity`, so direct provider tests and HTTP Basic integration tests exercise the exact same config.
- URL rules require only `authenticated()` on both endpoints. **Specific permissions** are enforced in the service with `@PreAuthorize`. Thus tests can catch the difference between "valid login" and "insufficient authority".
- `@EnableMethodSecurity` enables `@PreAuthorize` enforcement. Never use `new ApprovalService()` to test security because that skips the Spring proxy.
- CSRF stays at its default; POSTs require a CSRF token in `MockMvc` tests. Never disable CSRF just to make the demo POST pass.

This configuration is a baseline tailored to the example. Real applications with multiple providers/chains, IdPs, password migrations, or custom user stores must test their own wiring and failure modes.

### 6.4. Service with Two Independent Permissions

`src/main/java/demo/authcheck/ApprovalService.java`:

```java
package demo.authcheck;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ApprovalService {
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-for-test";
    }

    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    public String approve(String paymentId) {
        return "approved:" + paymentId;
    }
}
```

No real transactions or data mutations happen in the example. It intentionally returns fixed strings to focus on security rules rather than side effects. In a production system, even a user holding `PAYMENT_APPROVE` must be checked for **permissions on the specific resource**, such as organization, monetary limit, transaction state, and ownership.

### 6.5. Servlet/MVC Controller

`src/main/java/demo/authcheck/ApprovalController.java`:

```java
package demo.authcheck;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApprovalController {
    private final ApprovalService service;

    public ApprovalController(ApprovalService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String report() {
        return service.readReport();
    }

    @PostMapping(value = "/api/payments/{id}/approve",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String approve(@PathVariable String id) {
        return service.approve(id);
    }
}
```

Here, `GET /api/reports` and `POST /api/payments/123/approve` enter the security filter chain before the controller; the service is **Spring-injected**, so `@PreAuthorize` takes effect. The API returns plain text for learning simplicity; real apps need structured responses, auditing, and proper business error handling.

## 7. Test A: Simulating Identities to Test Method Security

File `src/test/java/demo/authcheck/MethodAuthorizationTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodAuthorizationTest {
    @Autowired
    ApprovalService service;

    @Test
    @WithMockUser(username = "ghost", authorities = "PAYMENT_APPROVE")
    void nonexistentMockIdentityCanPassAuthorizationRule() {
        // ghost does not exist in UserDetailsService.
        // The test only asks: is the authority sufficient to call the method?
        assertEquals("approved:123", service.approve("123"));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCanReadReport() {
        assertEquals("report-for-test", service.readReport());
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCannotApprove() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve("123"));
    }

    @Test
    @WithUserDetails("reader")
    void userDetailsFixtureCarriesReportPermission() {
        assertEquals("report-for-test", service.readReport());
    }

    @Test
    @WithUserDetails("reader")
    void userDetailsFixtureLacksApprovalPermission() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve("123"));
    }
}
```

**What this test proves:** the method-security proxy receives the context and enforces authority checks properly. User `ghost` does not exist yet the fixture grants the authority, so `approve` succeeds: this directly demonstrates that **mock auth is not an authentication-provider test**.

**What this test does not prove:** that password `reader-local-pass` is valid, that account `reader` is not disabled at the provider, that the Basic filter parses headers properly, that sessions/TLS/cookies are secure, or that a real database/LDAP works.

`@WithUserDetails("reader")` fetches the user from the fixture, yet skips `PasswordEncoder.matches`; to catch disabled accounts being blocked at the provider, use Test B.

## 8. Test B: Real AuthenticationManager and DaoAuthenticationProvider

File `src/test/java/demo/authcheck/AuthenticationManagerTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AuthenticationManagerTest {
    @Autowired
    AuthenticationManager manager;

    @Autowired
    UserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void storedPasswordIsEncodedAndMatchesExpectedRawPassword() {
        String stored = users.loadUserByUsername("reader").getPassword();

        assertFalse("reader-local-pass".equals(stored));
        assertTrue(encoder.matches("reader-local-pass", stored));
    }

    @Test
    void correctPasswordIsActuallyAuthenticatedByProvider() {
        Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-local-pass");
        assertFalse(input.isAuthenticated());

        Authentication result = manager.authenticate(input);

        assertTrue(result.isAuthenticated());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("REPORT_READ")));
    }

    @Test
    void wrongPasswordIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "reader", "wrong-password")));
    }

    @Test
    void nonexistentAccountIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "ghost", "any-password")));
    }

    @Test
    void disabledAccountIsRejectedEvenWhenPasswordMatches() {
        assertThrows(DisabledException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "blocked", "blocked-local-pass")));
    }
}
```

Now each call to `authenticate(...)` passes an **unauthenticated token** through the configured `ProviderManager` and `DaoAuthenticationProvider`:

- Right password → authenticated result carrying authorities from `UserDetailsService`.
- Wrong password → `BadCredentialsException`.
- Non-existent user → `BadCredentialsException` in standard provider config; hiding the exact reason mitigates user enumeration.
- Disabled account → `DisabledException` even when the password matches.

This test layer **genuinely proves the provider executed**, yet still does not prove Servlet filters, error handlers, HTTP status codes, CSRF, or cookies. When using LDAP, OAuth2, X.509, or custom providers, switch token types, providers, and fixtures to match the protocol; never use `UsernamePasswordAuthenticationToken` to stand in for JWT verification.

### 8.1. When Providers Cache or Multiple User Sources Exist

If a provider caches `UserDetails`, user lockouts or password changes may not take effect immediately. A thorough test suite also tests password rotation, disabled/locked checks after cache invalidation, and multiple providers where more than one `supports(...)` a token class. Distinguish a provider returning `null` (abstaining) from one throwing an exception, along with fallback/parent manager policies.

In multi-provider systems, do not assert only "an authenticated result was returned"; assert **which trusted provider/issuer authenticated** and that principal/authorities came from the right source. Never configure a permissive provider as a fallback when the primary provider errors out.

## 9. Test C: MockMvc with Real Credentials Passing Through the HTTP Basic Filter

File `src/test/java/demo/authcheck/HttpAuthenticationIntegrationTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthenticationIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerGets401ForProtectedReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "REPORT_READ")
    void mockIdentityCanReadEvenWithoutRealAccount() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-for-test"));
    }

    @Test
    void httpBasicWithValidCredentialRunsRealProvider() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-local-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-for-test"));
    }

    @Test
    void badPasswordFailsBeforeController() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "bad-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserFailsBeforeController() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("ghost", "any-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledUserCannotUseCorrectPassword() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("blocked", "blocked-local-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderWithoutApprovalAuthorityGets403()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("reader", "reader-local-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validApproverStillNeedsCsrfTokenOnPost()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("approver", "approver-local-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validApproverWithCsrfCanApprove()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("approver", "approver-local-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("approved:123"));
    }

    @Test
    void approverWithoutReportAuthorityCannotReadReport()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("approver", "approver-local-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Reading the results accurately:**

- `httpBasic(...)` is a request post-processor that sets the `Authorization: Basic ...` header. It **does not authenticate by itself**. Because `MockMvc` has the Spring Security filter chain enabled, `BasicAuthenticationFilter` parses credentials and delegates to the **real manager/provider**.
- `@WithMockUser("ghost")` helps test rules yet **bypasses account existence checks**; the `ghost` case can return 200 when granted simulated authorities.
- User `reader` is authenticated by the provider when the password is valid, yet still denied by `@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")` for approvals.
- User `approver` has approval permission yet is blocked by the CSRF filter on a POST missing a token. `.with(csrf())` is needed to test the **authorization** branch; never treat a CSRF 403 as proof of authorization rules.
- The 401 responses on wrong/disabled cases are HTTP translations of authentication failures via the Basic entry point. In Test B, they appear as `BadCredentialsException`/`DisabledException`; Test A does not test these exceptions at all.

To test the HTTP Basic filter properly, avoid `@AutoConfigureMockMvc(addFilters=false)`, `MockMvcBuilders.standaloneSetup(...)` without Spring Security, or pure Mockito controller unit tests. Those serve other purposes and do not represent the authentication pipeline.

## 10. Running Tests, Triaging Failures, and Differences Across Layers

In a Gradle project with wrapper and Java 17:

```bash
./gradlew test
```

Run individual classes:

```bash
./gradlew test --tests demo.authcheck.MethodAuthorizationTest
./gradlew test --tests demo.authcheck.AuthenticationManagerTest
./gradlew test --tests demo.authcheck.HttpAuthenticationIntegrationTest
```

These are test commands; exact Gradle console output depends on wrapper version, cache, JDK, and logging settings, so never assume every console line matches identically. Tests **expecting 401, 403, or exceptions** still **PASS** when the system returns the expected status.

If failures occur, classify before fixing:

| Symptom | Causes to Inspect | What Not to Conclude |
|---|---|---|
| Method test allows everyone | Missing `@EnableMethodSecurity`, bean not proxied, wrong annotation | Do not immediately blame `@WithMockUser` |
| `@WithUserDetails` fails before `@Test` runs | Username or `UserDetailsService` bean not found | Do not conclude the password is wrong |
| Direct manager test with wrong password succeeds | Wrong provider/encoder/wiring, fallback provider, broken fixture | Do not accept just because `MockMvc` `@WithMockUser` passes |
| HTTP Basic with right password gets 401 | Basic not enabled on filter chain, provider not selected, encoder mismatch | Do not switch to mock principal to hide the failure |
| HTTP Basic with wrong password gets 200 | Security filters skipped, fallback provider, pre-populated context | This is a release-blocking flaw |
| POST by authorized user gets 403 | Missing CSRF, wrong role, method security denial | Do not conclude immediately from status alone |
| Mock principal "ghost" can approve | Characteristic of fixture authority | Do not treat as proof user `ghost` can actually log in |
| JWT test using `jwt()` passes | Fixture token injected by helper | Do not treat as proof JWK/signature/audience are valid |

### 10.1. Why Shouldn't Provider Tests Mechanically Be Called "Pure Unit Tests"?

The direct `AuthenticationManager` test in the demo uses the **real `ApplicationContext`** and `InMemoryUserDetailsManager`, making it a **lightweight application-scoped integration test**. A pure unit test of a custom `AuthenticationProvider` can mock its dependencies to isolate algorithms, yet it will not prove encoder/user store/bean wiring work together properly.

Classify by **what actually executes**, not merely by file name or `@SpringBootTest`.

### 10.2. Watch Out for @WithMockUser Inherited Across Tests

Annotations can live on classes or methods. If a provider test accidentally carries `@WithMockUser` as well, HTTP requests can receive a pre-authenticated mock security context, causing wrong-password tests to stop exercising the expected logic. Therefore `AuthenticationManagerTest` and `HttpAuthenticationIntegrationTest` in the demo **do not put `@WithMockUser` at the class level**; only one test case uses it intentionally for comparison.

For tests using request post-processors `user(...)`, `jwt()`, or `oauth2Login()`, similarly avoid mixing those fixtures into cases meant to test real filters/providers. Name tests clearly ("mock identity" vs. "real credential") and always include negative cases.

## 11. Distinctions in Systems Using JWT, OIDC, LDAP, MFA, or Certificates

Even though the example uses `DaoAuthenticationProvider`, the same principles hold when the authentication mechanism changes.

### 11.1. JWT Resource Server

`jwt()` in `spring-security-test` typically supplies a `JwtAuthenticationToken` fixture with customizable claims/authorities; this is helpful for testing `@PreAuthorize` or scope-based authorization policies.

However, that fixture **does not prove** `JwtDecoder` verified signatures, issuer, audience, `exp`, algorithm allowlists, or JWK rotation. To test token validation, send real bearer tokens through the filter in a test environment using contracted decoders/test keys, or test the configured `JwtDecoder`/authentication provider directly. Test bad signatures, unknown issuers, wrong audiences, expired tokens, and missing required scopes.

### 11.2. OIDC/SAML and SSO

`oauth2Login()` or principal-creating helpers in tests can bypass redirects, authorization code exchange, ID token validation, SAML assertion signatures, and account linking. SSO integration tests require a test IdP environment/contract or dedicated validation modules; test `state`, `nonce`, redirect URIs, issuer/audience, and certificate/key rotation. Never test using real production user credentials.

### 11.3. LDAP and Account Status

`@WithUserDetails` can load a `UserDetails` from a directory adapter/fixture yet **does not bind to LDAP with the user's password**. To prove LDAP auth, use the real provider with a test directory container or authorized integration environment, proper TLS, user/group fixtures, wrong passwords, disabled accounts, and downtime handling. Never treat a passing user lookup as proof that bind authentication passed.

### 11.4. X.509 and Pre-Auth

Manually creating an `Authentication` containing a name resembling a Subject DN does not prove a client certificate was verified at the TLS endpoint. Test mTLS/PKI at the appropriate container/proxy, covering valid/expired/revoked certificates, SAN/subject mapping, and upstream bypass prevention. Client-supplied headers are not authentication evidence.

### 11.5. MFA and Step-Up

`@WithMockUser(roles="ADMIN")` does not prove two independent factors were checked or that the user just completed step-up authentication. If an endpoint requires MFA, test the policy with valid/invalid factor-state fixtures **and** test the real authentication flow that produces the factor state per contract. Never just attach an authority like `MFA_VERIFIED` and assume TOTP/WebAuthn/IdP was tested.

## 12. Designing a Test Matrix for Real Applications

| Security Question | Primary Test Method | PASS Condition |
|---|---|---|
| Does a method requiring `REPORT_READ` block other authorities? | `@WithMockUser` calling injected bean | Throws `AccessDeniedException` when lacking authority |
| Does the mapper build proper authorities from the user store? | `@WithUserDetails` | Principal/authorities from fixture are accurate |
| Do right passwords work? | `AuthenticationManager.authenticate(...)` | Provider returns authenticated result |
| Wrong password or unknown user? | Direct provider + HTTP Basic filter | Matching exception and HTTP 401 |
| Disabled/locked accounts? | Direct provider + HTTP integration | Not authenticated even with right password |
| Does the HTTP filter actually invoke the manager? | `MockMvc` `httpBasic(...)`/`formLogin()` | Valid 200 and invalid 401 per config |
| Logged-in user lacking business permission? | Valid HTTP Basic + method-security | 403 |
| POST missing CSRF? | `MockMvc` without `with(csrf())` | 403 before operation |
| POST with permission and CSRF? | `MockMvc` valid credentials + `with(csrf())` | 200 and expected business outcome |
| Is the method security proxy active? | Inject Spring service, `@EnableMethodSecurity` | Deny cases are not bypassed |
| Real JWT validation? | Signed/invalid JWT through decoder/filter | Bad signature/issuer/audience tokens rejected |
| Real SSO flow? | IdP integration/contract test | Redirects, state/nonce, token/assertion checks succeed |
| MFA step-up? | Policy tests + real factor flow | User without factor cannot perform sensitive actions |
| Permission changes in user store? | Provider refresh/session lifecycle | Permissions are not retained beyond SLA |
| Multiple providers? | Direct + filter tests across types/failures | No fallback to permissive provider |
| Logout/session? | MVC integration/E2E | Current session invalidated properly; do not confuse with token revocation |

### 12.1. Practical Test Distribution Pattern

Not every test needs to spin up a browser, directory, or IdP. For a typical project:

- Many small `@WithMockUser` method-security tests covering the allow/deny matrix across roles, tenants, and resource permissions.
- A group of provider integration tests with controlled data verifying password encoders, account flags, identity lookup, provider selection, and credential errors.
- A group of MVC filter integration tests covering entry points, valid/invalid credentials, CSRF, sessions, exception translation, and URL mappings.
- A small set of E2E tests for TLS/proxies, IdPs, cookies/redirects, refresh/revocation, and critical recovery flows.

Keep test fixtures and secrets isolated; never commit production passwords or tokens to repositories or logs. Database-backed flows should run with transaction cleanup/isolated fixtures; cached flows must test invalidation so tests do not accidentally pass against stale user state.

## 13. Common Mistakes and Root Causes

**1. "`@WithMockUser` PASS means login is secure."** False: it only populates `Authentication` in `SecurityContext`. You need separate provider tests and filter integration tests.

**2. "`@WithUserDetails` called `UserDetailsService`, so passwords were checked."** False: user lookup is not equivalent to `PasswordEncoder.matches` or provider account-status checks.

**3. "`httpBasic(...)` authenticates by itself."** False: the helper only adds a header; the application's filter and manager/provider process credentials. If filters are disabled, the test no longer proves anything.

**4. "403 always means missing permission."** False: CSRF also commonly returns 403; include valid CSRF in authorization tests to distinguish them.

**5. "200 on a mock request means a real user logged in."** False: the principal may come from an annotation or post-processor, even for a non-existent username.

**6. "Having the right authority is enough security."** False: the user must be authenticated by a trusted mechanism, and object/tenant permissions and business rules must still be checked.

**7. "Instantiating the service with `new` tests method security."** False: `@PreAuthorize` can be backed by a proxy; calling a fresh object outside the container skips security advice.

**8. "If one provider fails, try the next provider until one passes."** Dangerous if the fallback is weaker. Review provider selection policies, token types, issuers, and failure handling.

**9. "Testing JWT with `jwt()` means signatures were tested."** No. You need decoder/filter tests with signed tokens plus bad signature, issuer, audience, and expiry cases.

**10. "A disabled account with mock role `ADMIN` still passes, so the framework is broken."** No: mocks do not enforce account status. Direct provider tests must reject disabled accounts, and real endpoints must block accordingly.

**11. "Calling `AuthenticationManager` tests sessions, CSRF, and HTTP status too."** False: direct manager calls do not cover the Servlet filter chain, entry points, logout, sessions, or CSRF.

**12. "We already have integration tests, so negative cases are unnecessary."** False: wrong passwords, unknown users, disabled accounts, missing permissions, and missing CSRF are essential to catch bypasses.

## 14. Acceptance Checklist

- [ ] Clearly identified which tests only mock `Authentication` and which run a real `AuthenticationManager`/`AuthenticationProvider`.
- [ ] Verified `spring-security-test` matches the Spring Security version.
- [ ] Method-security tests enable `@EnableMethodSecurity` and invoke proxied Spring beans.
- [ ] `@WithMockUser`/`@WithUserDetails` are used solely to verify authorization/fixtures, never password validity.
- [ ] Provider tests start with an unauthenticated `Authentication`; verify right/wrong passwords, unknown/disabled/locked accounts, and authority mapping.
- [ ] `MockMvc` includes Spring Security filters; test credential-based paths via HTTP Basic or the appropriate real filter mechanism.
- [ ] HTTP integration tests do not accidentally inherit mock principals from class-level annotations.
- [ ] Authorization POST tests include valid CSRF; missing-CSRF tests are separate.
- [ ] Coverage includes unauthorized, unauthenticated, authenticated-but-forbidden, and authorized cases.
- [ ] For JWT/SSO/LDAP/X.509/MFA, test the actual identity-source provider/protocol instead of merely constructing lifelike fixtures.
- [ ] Provider failures do not open weak fallbacks or leak credentials/tokens/secrets in logs.
- [ ] Account/tenant permission state, sessions, and revocation are tested against real SLAs.
- [ ] Results are explained by layer: fixture, manager/provider, filter/entry point, method security, or E2E infra.

**Summary:** Use `@WithMockUser`, `@WithUserDetails`, and mock request helpers to test **given an authenticated principal with specific authorities, whether authorization decides correctly**. Use **unauthenticated** tokens with `AuthenticationManager` or send credentials through **real filters** to test **whether accounts/passwords/tokens are actually verified**. A trustworthy system needs both forms of evidence, especially on sensitive paths.