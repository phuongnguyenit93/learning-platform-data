# Distinguishing a Mocked Principal from Verified Authentication Evidence

> **Module:** Spring Security – authentication. **Group:** Component Testing. Applies to Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet stack), JUnit 5, and Spring Security Test. The focus is distinguishing **pre-populating a principal/`Authentication` in tests** from **actually verifying passwords, tokens, sessions, or Identity Provider evidence**. A test showing `authenticated()` does not by itself prove a secure login mechanism.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `Principal`, `Authentication`, `SecurityContext`, `AuthenticationManager`, `AuthenticationProvider`, and how Spring Security executes authentication.
2. Know how `@WithMockUser`, `@WithUserDetails`, `user()`, `authentication()`, `jwt()`, `oauth2Login()`, and `opaqueToken()` create **test fixtures** with different scopes.
3. Identify precisely **what is proven** and **what is not proven** when a test uses a mocked principal.
4. Write **authorization** tests with mocked principals (fast, focused) and **real authentication tests through HTTP filters/providers** using `formLogin()` or `httpBasic()`.
5. Explain why `@WithUserDetails` can query the user store yet **does not replace password verification**, and `jwt()` **does not verify JWT signatures**.
6. Layer tests to verify password encoders, account flags, CSRF, authentication filters, session persistence, JWT signature/issuer/audience/time, and authorization.
7. Prevent false positives caused by `addFilters=false`, `standaloneSetup` without security, mocking `AuthenticationManager`, client-supplied roles, nonexistent mock principals, or fake tokens with `alg=none`.
8. Write "negative-first" tests: verify protection **rejects** missing/invalid evidence before accepting valid evidence.

## 2. Definition: A Principal Is Not Authentication Evidence

In Java, `java.security.Principal` is an abstraction representing **an identity**. In Spring Security, `Authentication` represents identity details, authorities, and authentication status, and can also serve as an authentication request before being processed by a provider.

- **Principal:** the "who" object or identifier; may be a username `lan`, `UserDetails`, `Jwt`, `OidcUser`, or domain principal.
- **Credentials:** evidence presented for verification, such as a password, bearer access token, or signed assertion; some authentication results erase credentials after success.
- **Authorities:** permissions/scopes confirmed by a trusted source at authentication time, e.g., `ROLE_USER` or `SCOPE_reports.read`.
- **`Authentication.isAuthenticated()`:** a state flag on the `Authentication` object, **not independent proof that a password/JWT was ever checked**.
- **`SecurityContextHolder`:** access point for the execution/thread-bound context in Servlet (managed per strategy). A test setting the context directly does not mean anyone actually logged in.

A production request using form password login typically flows through:

```text
Browser POST /login (username + password)
        │
        ▼
UsernamePasswordAuthenticationFilter
        │ Unverified Authentication object
        ▼
AuthenticationManager / ProviderManager
        │
        └── DaoAuthenticationProvider
              ├─ UserDetailsService.loadUserByUsername()
              ├─ PasswordEncoder.matches(raw, storedHash)
              ├─ account locked/disabled/expired checks
              └─ success → Verified Authentication
        │
        ▼
SecurityContext + session strategy/handlers
        │
        ▼
AuthorizationFilter / @PreAuthorize / business policy
        │
        ▼
Endpoint allowed or denied
```

Meanwhile, `@WithMockUser` or `user("lan")` can **pre-install an authenticated `UsernamePasswordAuthenticationToken`** into the test request/context:

```text
JUnit test method
        │
        │ @WithMockUser(username="lan",roles="USER")
        ▼
Spring Security Test creates a mocked Authentication
        │
        ▼
SecurityContext holds principal + ROLE_USER
        │
        ▼
AuthorizationFilter / protected method
        │
        ▼
Result may be 200 / 403
        │
        └─ NO password input step,
           NO PasswordEncoder.matches(),
           DOES NOT prove account exists.
```

**Key point:** both flows can result in **the same principal name and the same authorities**, yet the **evidence path** is completely different. Mocked tests are great for testing **authorization for a principal assumed to be authenticated**, yet you **cannot conclude the password/JWT verifier works** from that outcome.

## 3. Distinguishing Each Type of Test Fixture

| Setup | Real evidence actually verified in test? | What the test proves best | What cannot be concluded |
|---|---|---|---|
| `@WithMockUser(username="lan", roles="USER")` | No; test creates principal without requiring user to exist | Method/request authorization for given user/roles | Right password, user exists in DB, MFA passed |
| `@WithAnonymousUser` | No; simulates anonymous | Endpoint must deny/allow anonymous per policy | That a real authentication flow ran |
| `mvc.perform(get(...).with(user("lan")))` | No; injects user onto request | Access rules/handlers given an `Authentication` | That password was checked |
| `mvc.perform(...with(authentication(auth)))` | No, if `auth` was pre-constructed | Rules depending on `Authentication` shape/authorities | That `Authentication` came from a real verifier |
| `@WithUserDetails("lan")` | **Runs `loadUserByUsername`**, does not check password | Principal type, `UserDetails` mapping, method authorization | `PasswordEncoder.matches` and login filter succeeded |
| `.with(jwt())` | **Does not** verify signature/issuer/audience/exp like real token requests | Resource authorization for mocked `JwtAuthenticationToken`/scopes | Real JWT signed by issuer and accepted by decoder |
| `.with(oauth2Login())` / `.with(oidcLogin())` | Does not run real OAuth/OIDC redirects and token exchange | Authorization based on mocked OIDC principal/claims | Real code/state/nonce/issuer/token signature |
| `.with(opaqueToken())` | Does not require calling introspection server | Permissions for mocked introspected principal | Opaque token is real and introspection policy works |
| `.with(httpBasic("lan","password"))` | **Can**, when real `SecurityFilterChain`/manager/provider are active | Password auth via Basic filter, flag mapping, responses | Not valid if provider/encoder was mocked or filters disabled |
| `mvc.perform(formLogin().user(...).password(...))` | **Can**, when real login filter/provider run | POST form login, CSRF, password provider, success/failure | Does not prove token/session/SAML/OIDC flows |
| Real signed JWT in `Authorization: Bearer ...` header | Yes, when Resource Server uses real `JwtDecoder`/validators | Signature, claims/time/issuer/audience per configuration | Does not prove authorization if only asserting status without scopes |
| End-to-end browser + real IdP | Closest-to-real integration within environment scope | Redirects, login, cookies/sessions, external assertions | Does not guarantee all phishing/ops scenarios were tested |

**Important note:** `@WithUserDetails` queries `UserDetailsService`; that test **can prove** the user was looked up and mapped into the right principal type, yet **does not prove** the user's submitted password passed `matches`. Meanwhile, `formLogin()` and `httpBasic()` prove the real auth path only if **`AuthenticationManager`/provider, `UserDetailsService`, or the password encoder were not replaced with an always-succeeding mock**.

## 4. When Should You Mock the Principal?

Mocking is the right choice when the **direct goal of the test is not verifying passwords/tokens**. For example:

- Does `@PreAuthorize("hasRole('AUDITOR')")` reject `ROLE_USER`?
- Does the controller read `authentication.getName()` properly to query owner-scoped data?
- Can tenant A's data leak to a user in tenant B who has the same `ROLE_USER`?
- Does a service method reject a user lacking permissions when invoked outside HTTP?
- Does a DTO strip private fields based on role/owner?
- Do CORS/CSRF or headers apply properly to requests that already have a known `Authentication`?

In those tests, injecting a principal **isolates authorization and business logic**, avoids I/O/crypto overhead, and keeps tests fast and reproducible. Still, **name and scope them accurately**:

**Accurate names:**

```text
shouldAllowAuditorToReadReportWhenAlreadyAuthenticated()
shouldRejectViewerFromTenantB()
shouldRejectAnonymousRequestToPrivateEndpoint()
```

**Misleading names:**

```text
passwordLoginWorks()  // yet inside it is only @WithMockUser
jwtSignatureVerified() // yet inside it is only .with(jwt())
userWasAuthenticatedByIdp() // yet only .with(oidcLogin())
```

Useful rule of thumb: **If removing all passwords/JWTs/IdPs from a test still leaves it passing, that test probably proves only authorization given a pre-supplied principal.**

### 4.1. How does `@WithMockUser` work?

`@WithMockUser` belongs to `spring-security-test` and is processed by `WithSecurityContextTestExecutionListener` to populate `SecurityContext` before the test runs. Common defaults:

- username: `user`;
- fixture password: `password`;
- role: `USER`, creating authority `ROLE_USER`;
- principal: Spring Security `User`;
- `Authentication`: `UsernamePasswordAuthenticationToken` marked authenticated.

No `user` record is needed in any database; the `password` `"password"` in the annotation **is never compared against a password hash**. Role strings in `roles` receive the `ROLE_` prefix; `authorities` keeps strings verbatim. Never pass `roles={"ROLE_ADMIN"}` and end up with `ROLE_ROLE_ADMIN`. Use `roles={"ADMIN"}` or `authorities={"ROLE_ADMIN"}` accordingly.

Example:

```java
@Test
@WithMockUser(username = "lan", roles = "AUDITOR")
void auditorMayReadReport() {
    // Service must be a bean protected by a Spring AOP/proxy.
    assertThat(reportService.readSummary()).isNotBlank();
}
```

Passing means **the rule for `ROLE_AUDITOR` in a mocked context** worked (assuming method security is enabled). It does not prove user `lan` holds that role in the database or that password login works. **Role issuance** must be tested separately against the trusted user store/IdP.

### 4.2. Is `@WithUserDetails` more real than `@WithMockUser`?

`@WithUserDetails("lan")` calls the test context's `UserDetailsService` to fetch a real `UserDetails` per test config, then uses it as the principal of a mocked `Authentication`. Consequently:

- It can verify the user exists in the repository wired into the test.
- It can verify custom principal types (e.g., `CustomUserDetails` carrying a stable account ID).
- It can verify `getAuthorities()` mapping from DB/app config.
- It does **not** execute `DaoAuthenticationProvider.authenticate(UsernamePasswordAuthenticationToken)`.
- It does **not** invoke `PasswordEncoder.matches(raw, storedHash)` merely from `@WithUserDetails`.
- No POST login, no failure handler/session fixation/CSRF login flow.

If `UserDetailsService` in the test is a mock returning a hardcoded `UserDetails`, not even "user exists in DB" is proven. Always distinguish real beans/services from mocks.

Example:

```java
@Test
@WithUserDetails(value = "lan")
void principalTypeFromStoreIsUsed() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    assertThat(auth.getPrincipal()).isInstanceOf(UserDetails.class);
    assertThat(auth.getName()).isEqualTo("lan");
}
```

This is a **snippet** inside a Spring Test class with a `UserDetailsService` bean and static AssertJ imports; not standalone. It tests only **lookup + context setup**.

### 4.3. `@WithSecurityContext` for custom principals

`@WithSecurityContext` can build specialized `Authentication` fixtures: multi-tenant, authorities, MFA claims, scopes, or custom principals. This helps when the app requires complex principal shapes, yet it remains **mocked**. If the factory sets `authenticated=true`, that is a **test** decision, not proof of real MFA/sessions.

What to protect in production: **never let clients supply `Authentication`/`roles`/`isAuthenticated` via JSON/headers and have the server trust them**, because test fixtures making principal creation easy are a privilege of the test environment.

## 5. At Which Step Does Real Credential Verification Differ from a Mocked Principal?

For username/password, the minimal production path needs:

1. Request sends username/password to the configured filter: `POST /login` or HTTP Basic.
2. Filter builds an **unauthenticated** `Authentication` with the raw credential to verify.
3. `AuthenticationManager` invokes the matching provider, e.g., `DaoAuthenticationProvider`.
4. Provider uses `UserDetailsService` to load the user, checks account status (enabled/locked/expired), and verifies credentials with `PasswordEncoder.matches`.
5. If invalid, returns failure/challenge without creating a privileged session.
6. If valid, produces an authenticated `Authentication` and applies the session/context strategy.
7. Authorization checks authorities/roles/ownership of the verified principal.
8. With MFA, a right password **is not enough** if the resource requires an additional factor; tests must exercise the second-factor flow.

**For JWT bearer:**

```text
HTTP Authorization: Bearer eyJ...
        ↓
BearerTokenAuthenticationFilter
        ↓
JwtAuthenticationProvider / JwtDecoder
        ├─ verify signature and allowed algorithms
        ├─ verify issuer, audience, exp, nbf per policy
        ├─ verify key/kid, trust metadata
        └─ map claims/scopes to authorities
        ↓
Authentication succeeded
        ↓
Authorization proceeds
```

**With `.with(jwt())`:** Spring Security Test **pre-installs a `JwtAuthenticationToken`**, typically without sending an HTTP bearer token for the decoder to verify signatures. Having `alg=none` or `sub=user` in a fixture neither proves the app accepts `alg=none` in production nor **proves the app rejects `alg=none`**. Test the real decoder/HTTP headers for those conclusions.

## 6. Designing a Test System Around Different Questions

| Test layer | Input | Real components that must run | Question the test answers |
|---|---|---|---|
| Domain unit test | Assumed identity/roles + resource metadata | Domain policy, no Spring needed | "Is this user allowed to read this document?" |
| Method security test | `@WithMockUser`/`@WithUserDetails` | `@PreAuthorize` proxy/interceptors | "Does the method security rule block unauthorized roles?" |
| MVC authorization slice | `MockMvc` `user()`/`jwt()` | Controller + `SecurityFilterChain` + authorization | "Does the endpoint map authorities to responses properly?" |
| Authentication component test | HTTP Basic/form login request | Real auth filter + `AuthenticationManager` + configured `PasswordEncoder`/`UserDetailsService` | "How are right/wrong/disabled passwords handled?" |
| JWT decoder/security test | Real signed JWT (test key) in `Authorization` header | Bearer filter + real `JwtDecoder`/validators | "Are invalid signatures and bad iss/aud/exp rejected?" |
| OIDC/SSO integration | Authorization code/state/nonce, test IdP | OAuth2 login client, callback/token verification | "Are real callbacks and user linking secure?" |
| E2E browser | Real browser, cookies, CSRF, login and logout | App/proxy/IdP/DB in test environment | "Does the entire user journey operate safely?" |

Layers **complement** each other; no single layer replaces all others. Overusing E2E to test a `hasRole` check is slow and flaky; relying solely on `@WithMockUser` with zero real password/JWT tests creates a **false sense of security**.

### 6.1. Two coverage dimensions to measure separately

**Authorization coverage**: who is allowed to do what, blocking other users/tenants, role/scope/ownership checks, method-level protection, object-level authorization.

**Authentication coverage**: where credentials are issued, whether the verifier actually checks or is mocked, proper token types, password hashes/status, JWT signature/audience/issuer/time, refresh/MFA/sessions, failure paths.

A test file with 100 `@WithMockUser` cases can provide great authorization coverage while giving near **0 coverage of credential verifiers**. Test reports should state both dimensions to avoid misunderstandings.

## 7. Spring Boot 3 + Spring Security 6: A Small App to Compare

This example creates a **form login + HTTP Basic** app with internal account `lan` having role `READER`. The goal is running two suites **against the same endpoint**: one injecting a mocked principal, one sending credentials through the filter/provider. The classes compile and run in a Spring Boot 3.x project with JDK 17+, matching Gradle/BOM, and the dependencies below.

### 7.1. Gradle dependencies

`build.gradle` (`dependencies` section; Spring Boot plugin and repositories are declared in the project):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

No database is needed for the example; `InMemoryUserDetailsManager` serves as a **real user store within the test suite**, not a production database. What must be proven is that the provider uses hashes and verifies passwords. Production requires persistence and policy-compliant account/session management.

### 7.2. Main Spring Boot app

File `src/main/java/example/learning/auth/SecurityTestApplication.java`:

```java
package example.learning.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
```

### 7.3. SecurityConfig — keeping real provider and real hashes

File `src/main/java/example/learning/auth/ExampleSecurityConfig.java`:

```java
package example.learning.auth;

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
public class ExampleSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("correct-password-123"))
            .roles("READER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("disabled-password-123"))
            .roles("READER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(lan, disabled);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/reports/**").hasRole("READER")
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

**Why this configuration fits the lesson:**

- `PasswordEncoder` is a real bean, not a Mockito mock always returning `true`.
- `UserDetailsService` returns two real users from the in-memory store. The `disabled` account submits the right password yet login must still be rejected.
- `DaoAuthenticationProvider` is integrated via the configured user store and encoder; through Basic/Form, passwords genuinely pass through the verifier.
- `/reports/**` requires `ROLE_READER`; users without this role receive 403 or an auth challenge depending on state.
- Both Basic and Form are enabled to compare both request styles. Entrypoint/status selection depends on `Accept`/content negotiation; in Basic tests you can send `Accept: application/json` to avoid HTML UX.
- This configuration is a **learning sample**, not a recommendation to enable Basic auth by default for every production frontend. Never put example passwords into real source or use `InMemoryUserDetailsManager` in multi-user production systems.

### 7.4. Endpoint simply reflects the supplied identity

File `src/main/java/example/learning/auth/ReportController.java`:

```java
package example.learning.auth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/reports/me")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
```

This endpoint **does not verify passwords**. It merely reads the `Authentication` provided by security filters/context. Therefore, if a test injects a mocked `Authentication`, the controller can return `ghost` even though no `ghost` exists in the user store. That is a **feature of test fixtures**, not proof of production login for ghost.

### 7.5. MockMvc test suite — contrasting mocks and real credentials

File `src/test/java/example/learning/auth/AuthBoundaryTests.java`:

```java
package example.learning.auth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AuthBoundaryTests {

    @Autowired MockMvc mvc;

    @Test
    void mockedPrincipalCanAccessWithoutAnAccountRecord()
            throws Exception {
        mvc.perform(get("/reports/me")
                .with(user("ghost").roles("READER")))
            .andExpect(status().isOk())
            .andExpect(content().string("ghost"));
    }

    @Test
    void actualHttpBasicRejectsUnknownAccount()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualHttpBasicRejectsWrongPassword()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualHttpBasicAcceptsCorrectPassword()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("lan", "correct-password-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("lan"));
    }

    @Test
    void actualHttpBasicRejectsDisabledAccount()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("disabled", "disabled-password-123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void simulatedRoleWithoutPermissionGetsForbidden()
            throws Exception {
        mvc.perform(get("/reports/me")
                .with(user("ghost").roles("VIEWER")))
            .andExpect(status().isForbidden());
    }
}
```

**Fix imports when copying into a Java file:** In Markdown, the first two `import static` lines above wrap between package and class names for readability. Java **allows whitespace after a dot**, yet for clean syntax in an IDE, put each import on one line:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

The test suite can be run with:

```bash
./gradlew test --tests example.learning.auth.AuthBoundaryTests
```

On Windows, you can use `gradlew.bat test --tests example.learning.auth.AuthBoundaryTests`. Never copy fixed test counts/CI output as "stdout" unless you actually ran it in your environment.

**Explaining the expected results:**

1. `ghost + user("ghost").roles("READER")` is placed into **test `SecurityContext`**, so `/reports/me` returns `ghost`: **authorization with a mocked principal passed**.
2. `ghost + httpBasic("ghost","whatever")` must fail because `UserDetailsService` has no `ghost`: **real provider participated**.
3. `lan` sending the wrong password must return 401: **`PasswordEncoder.matches` rejected it**.
4. `lan` sending the right password can read `/reports/me` and receives `lan`.
5. `disabled` has the right password yet is still blocked due to account flags.
6. `ghost` assigned mock `ROLE_VIEWER` lacks `ROLE_READER` and gets 403 (still only an authorization test).

Do not draw the wrong conclusion that "ghost passing the test means there is a login vulnerability": `user()` takes effect **only inside the `MockMvc` test**, not on HTTP requests sent by an attacker in production. Conversely, if you use mocked fixtures to test login, the tests will miss password-provider bugs.

## 8. @WithMockUser and @WithUserDetails in Method Security

With method security, `@EnableMethodSecurity` must be enabled and protected methods must be invoked **through a Spring-managed proxy**. If you instantiate the service with `new` or invoke an annotated method within the same class (self-invocation), tests can bypass method security.

Service example:

```java
package example.learning.auth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasRole('READER')")
    public String summary() {
        return "report-visible";
    }
}
```

Method security must be enabled:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Corresponding imports: `org.springframework.context.annotation.Configuration` and `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`. This is an application integration snippet.

Tests:

```java
@Test
@WithMockUser(username = "ghost", roles = "READER")
void mockedReaderCanCallProtectedService() {
    assertThat(reportService.summary()).isEqualTo("report-visible");
}

@Test
@WithUserDetails("lan")
void realUserDetailsCanBeLoadedWithoutPasswordCheck() {
    assertThat(reportService.summary()).isEqualTo("report-visible");
}
```

These snippets assume a test context with the `ReportService` bean, `UserDetailsService`, and imports from Spring Security Test, JUnit 5, and AssertJ. `@WithMockUser` does not require `ghost` to exist. `@WithUserDetails` requires `lan` to be loaded by `UserDetailsService`; **there is still no password-check step**. Both are suited for testing method authorization. To test passwords, send requests through `formLogin()`/`httpBasic()` or call `AuthenticationManager.authenticate(...)` directly with a real provider/encoder.

### 8.1. What if method security is not enabled?

A test with `@WithMockUser(roles="USER")` calling `service.sensitiveOperation()` and succeeding might pass solely because `@PreAuthorize` was never intercepted. Tests must include both **positive** and **negative** cases:

- Authorized role is allowed.
- Missing role must raise `AccessDeniedException`/`AuthorizationDeniedException` or return 403 over HTTP.
- Missing context must be rejected.
- Different ownership/tenant must be blocked even with the same role.

Positive-only tests easily create a false sense of security: an unprotected method also "passes" when an admin user calls it.

## 9. RequestPostProcessor jwt(): Dangers of Misinterpretation

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.jwt()`, which constructs a `JwtAuthenticationToken` without creating a real JWT. Example snippet in a `MockMvc` test for Resource Server route `GET /api/reports` requiring `SCOPE_reports.read`:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

If the application endpoint/controller actually exists and authorization is configured properly, this test proves **assuming a `JwtAuthenticationToken` with `SCOPE_reports.read` exists, the rule allows access**. However:

- It does not prove the JWT has a valid signature or rejects `alg=none`.
- It does not prove issuer/audience are configured and validators run.
- It does not prove the token is unexpired or unrevoked.
- It does not prove real `scope` claims map properly if the test assigns authorities directly.
- It does not prove the `Authorization` header protocol or Bearer failure handler was tested.
- It does not prove ID tokens, access tokens, refresh tokens, and reset tokens are distinguished.

A test can pass even if the project **never configured `issuer-uri`**, when `JwtAuthenticationToken` is mocked upfront. That is a **limitation of the test method**, not proof that the Resource Server is insecure by default.

### 9.1. `jwt().jwt(...).claim(...)` vs `jwt().authorities(...)`

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(builder -> builder
            .claim("sub", "lan")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

This builds a mock `Jwt` with claims and passes it through the test helper's converter when authorities are omitted; it still **does not verify signatures**. If the app uses a custom `JwtAuthenticationConverter`/user mapping, test the converter separately with a mock `Jwt` and run integration tests with real signed tokens to ensure claim-to-authority mapping works in production.

### 9.2. Testing real JWTs via HTTP Authorization header

A true JWT integration test should:

1. Boot the Spring Boot Resource Server with a **real `JwtDecoder`** and production-equivalent validators.
2. Generate a test-only RSA/EC key pair and trusted test JWKS/issuer fixture, or run a test Authorization Server.
3. Mint an access token **genuinely signed** with the test private key; configure the decoder to trust the issuer's public key.
4. Send the raw string in `Authorization: Bearer <signed-token>`, **never using `.with(jwt())`**.
5. Assert valid tokens succeed and wrong signatures/algorithms/`kid`s are rejected.
6. Assert bad issuer/audience/expiry/`nbf` are rejected; tokens missing scopes return 403 after authentication.
7. Assert `WWW-Authenticate` and HTTP statuses, not just controller bodies.
8. If the app requires revocation/introspection or session versioning, test real interactions with that verifier/shared store.

Example request-sending point in a test (snippet; `signedToken` supplied by fixture, never hardcode real tokens):

```java
mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedToken))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tamperedToken))
    .andExpect(status().isUnauthorized());
```

This snippet needs static imports `get`, `status`, `org.springframework.http.HttpHeaders`, and test fixture variables. **Do not assume "passed with a mocked `JwtDecoder`" means signatures were verified.** A Mockito mock decoder focuses on token wiring/filter error handling without testing cryptography.

### 9.3. Standalone `JwtDecoder` tests are also useful

You can unit/integration-test a real `JwtDecoder.decode(String token)` with test keys. When decoding invalid tokens, it must raise an appropriate `JwtException`/`JwtValidationException` and create no `Authentication`; when decoding valid tokens, assert claim values and validator mappings. Still, testing the decoder alone **does not yet** prove `BearerTokenAuthenticationFilter`, chain matchers, header extraction, and authorization paths are wired properly. At least one full HTTP integration test is needed.

## 10. Testing Real Login with formLogin() and httpBasic()

### 10.1. Form login request post processor

`formLogin()` creates a POST to `/login` with username/password and a valid CSRF token per Spring Security Test:

```java
mvc.perform(formLogin()
        .user("lan")
        .password("correct-password-123"))
    .andExpect(authenticated().withUsername("lan"));

mvc.perform(formLogin()
        .user("lan")
        .password("wrong"))
    .andExpect(unauthenticated());
```

Static imports for assertions:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
```

These are snippets inside a `MockMvc` test that already has a Spring Security filter chain and real `UsernamePasswordAuthenticationFilter`/provider. Form login can redirect on success or failure; tests can assert `redirectedUrl`/flash/session per app config. If login URL/parameter names change, `formLogin("/auth").user("u","lan").password("p","...")` must match the login processing configuration.

**Do not forget CSRF:** if writing `post("/login").param(...)` manually in tests, add `.with(csrf())` for session-based apps with CSRF enabled. A test omitting CSRF can receive 403 before the password provider ever runs; merely seeing "login failed" does not prove a wrong password was rejected.

### 10.2. HTTP Basic request post processor

`httpBasic("lan", "...")` builds a properly formatted Basic header; it does **not** inject an already-authenticated `Authentication`:

```java
mvc.perform(get("/reports/me")
        .accept(MediaType.APPLICATION_JSON)
        .with(httpBasic("lan", "wrong")))
    .andExpect(status().isUnauthorized());

mvc.perform(get("/reports/me")
        .accept(MediaType.APPLICATION_JSON)
        .with(httpBasic("lan", "correct-password-123")))
    .andExpect(status().isOk());
```

In the Section 7 app, the Basic test traverses the real filter/manager/encoder. If you mocked `AuthenticationManager.authenticate(...)` to return a principal regardless of password, **the HTTP request is real while the credential verifier is fake**. Test quality depends on the entire dependency chain, not `httpBasic()` alone.

### 10.3. Direct `AuthenticationManager` tests: useful yet insufficient for HTTP

A component test can call `AuthenticationManager.authenticate(...)` directly with `UsernamePasswordAuthenticationToken.unauthenticated(username,password)` and assert success/`BadCredentialsException`. That tests the provider and encoder, yet skips filter URLs, CSRF, session fixation, failure handlers, redirects/cookies, and security chain matchers. Combine it with `MockMvc` HTTP tests.

## 11. Standalone Java 17 Lesson: Difference Between Mock Roles and Real Passwords

This program **compiles/runs with JDK 17+** and needs no external libraries. It uses JDK PBKDF2 as a **simple illustration of secret verification**; it does not replace Spring Security's `PasswordEncoder` and is not a production template. All outputs are booleans so they are deterministically reproducible despite random salt generation.

Save file `PrincipalEvidenceBoundaryDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Map;
import java.util.Set;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PrincipalEvidenceBoundaryDemo {

    record Account(
        String username, byte[] salt, byte[] passwordHash,
        Set<String> trustedRoles) {}

    record Principal(String username, Set<String> roles) {}

    // Illustrates verifier only; production uses PasswordEncoder
    // with organizationally managed algorithm and configuration.
    static byte[] hash(char[] password, byte[] salt) {
        PBEKeySpec spec =
            new PBEKeySpec(password, salt, 120_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        } finally {
            spec.clearPassword();
        }
    }

    static Principal authenticate(
            String username, char[] suppliedPassword,
            Map<String, Account> accounts) {

        Account account = accounts.get(username);
        if (account == null) {
            return null;
        }
        byte[] suppliedHash =
            hash(suppliedPassword, account.salt());

        if (!MessageDigest.isEqual(
                account.passwordHash(), suppliedHash)) {
            return null;
        }
        return new Principal(
            account.username(), account.trustedRoles());
    }

    static boolean mayRead(Principal principal) {
        return principal != null
            && principal.roles().contains("READER");
    }

    public static void main(String[] args) {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);

        Account lan = new Account(
            "lan",
            salt,
            hash("correct-password".toCharArray(), salt),
            Set.of("READER")
        );
        Map<String, Account> accounts = Map.of("lan", lan);

        Principal injected =
            new Principal("ghost", Set.of("READER"));

        System.out.println("Mock ghost may read: " +
            mayRead(injected));
        System.out.println("Ghost real login: " +
            (authenticate("ghost",
                "anything".toCharArray(), accounts) != null));
        System.out.println("Wrong password: " +
            (authenticate("lan",
                "wrong".toCharArray(), accounts) != null));

        Principal verified = authenticate(
            "lan", "correct-password".toCharArray(), accounts);
        System.out.println("Verified login: " +
            (verified != null));
        System.out.println("Verified read: " +
            mayRead(verified));
        System.out.println("Injected login proof: " +
            (authenticate(injected.username(),
                "anything".toCharArray(), accounts) != null));
    }
}
```

Commands:

```bash
javac PrincipalEvidenceBoundaryDemo.java
java PrincipalEvidenceBoundaryDemo
```

Exact stdout:

```text
Mock ghost may read: true
Ghost real login: false
Wrong password: false
Verified login: true
Verified read: true
Injected login proof: false
```

**Analysis:**

- `Mock ghost may read: true`: the authorization function accepts a `Principal` assumed to hold `READER`. Since it does not know the history of identity verification, it permits access. That models authorization tests with an injected principal.
- `Ghost real login: false`: `authenticate` requires an account in the store and cannot verify `ghost` even though a mock principal is trivial to construct.
- `Wrong password: false`: the verifier actually computes PBKDF2 with the account's salt and compares results.
- `Verified login: true`: only when the secret matches does it build a `Principal` from **trusted account roles**.
- `Verified read: true`: after credential verification, authorization succeeds.
- `Injected login proof: false`: a mocked principal cannot be submitted as evidence to the verifier.

**Guarantees and limits:** the demo provides no web login/HTTP sessions/JWT/MFA/CSRF, account flags, brute-force protection, or password hash migration. Cost `120_000` is solely so the demo runs cleanly, **not a production PBKDF2 recommendation**; use `PasswordEncoder`, policy-defined algorithms/costs, random salts, and request rate controls. In a JDK test program, creating a `Principal` inside test code creates no production vulnerability unless the app has an endpoint that **trusts client-supplied principals/roles**.

## 12. Signs Your Test Is Proving the Wrong Thing

### 12.1. A test uses `@WithMockUser` yet is named `passwordLoginWorks`

```java
@Test
@WithMockUser(username="lan", roles="USER")
void passwordLoginWorks() {
    // Directly tests a service that already has a principal.
}
```

**Problem:** No POST login request, no raw password, no `PasswordEncoder.matches`. The test name misrepresents its scope. Rename it to `authenticatedUserCanAccessService` and write a separate form-login test.

### 12.2. `.with(jwt())` followed by claiming `alg=none` tokens are blocked

```java
mvc.perform(get("/api/resource").with(jwt()))
    .andExpect(status().isOk());
```

**Problem:** `jwt()` builds a mock token for authorization tests. This test never runs the JWT signature decoder. To test `alg=none`, send a raw malformed/unsigned JWT in the `Authorization` header against a real `JwtDecoder` and expect 401. Test issuer/audience/time too.

### 12.3. A disabled account is mocked as ACTIVE

```java
mvc.perform(get("/reports/me")
        .with(user("disabled").roles("READER")))
    .andExpect(status().isOk());
```

This test passes even if the user store marks the account disabled. Because `user()` bypasses provider account-status checks, never use this test to prove "locked users cannot log in". Use `httpBasic()` or `formLogin()` with a real provider to verify disabled/locked policies.

### 12.4. `MockMvc` skips security filters

```java
@AutoConfigureMockMvc(addFilters = false)
```

This configuration intentionally **omits filters** from `MockMvc`; if a test returns 200 for a protected URL, it **does not prove Spring Security permits it properly**. It can be handy for controller unit tests, yet must be named clearly and backed by separate security integration tests.

Similarly, `MockMvcBuilders.standaloneSetup(controller)` without `.apply(springSecurity())`/appropriate `FilterChainProxy` can bypass security filters. `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` or `@AutoConfigureMockMvc(addFilters=true)` is appropriate when enforcing request-level security. Do not equate `@WebMvcTest` with the full application: slices may mock many beans, so inspect which filters/providers are actually constructed.

### 12.5. `@MockBean AuthenticationManager` returns success unconditionally

If Mockito is stubbed so `when(authenticationManager.authenticate(any())).thenReturn(verifiedAuthentication)`, an HTTP POST can return success without checking passwords at all. That tests filter wiring with a **replaced verifier**. Keep a separate test without mocking `AuthenticationManager`/provider/encoder for the "wrong password rejected" hypothesis.

Likewise, `@MockitoBean`/`@MockBean` is a test tool; if you stub `JwtDecoder` to return a `Jwt` for every token, you cannot conclude the app verifies real signatures.

### 12.6. Happy-path-only tests

```text
Admin role → HTTP 200
```

Not enough. An endpoint that **bypasses `SecurityFilterChain` completely** can also return 200. Negative tests are required:

```text
anonymous → 401/302 (per mechanism)
wrong password → 401/redirect failure
disabled account → failed authentication
valid account but missing role → 403
cross-tenant same role → 403/404 per policy
tampered JWT → 401
expired JWT → 401
wrong issuer/audience → 401
correct role + correct token → 2xx
```

## 13. SecurityContextHolder, Threads, and Test Isolation

Spring Security Test provides `WithSecurityContextTestExecutionListener` to populate/clear `SecurityContext` across the test lifecycle. When modifying context manually in unit tests, clear it via `SecurityContextHolder.clearContext()` in `@AfterEach` or `finally` to prevent state leaking across thread reuse.

**However, test cleanup does not replace real session lifecycles.** For web/sessions, Spring Security uses `SecurityContextRepository` and session strategies to save/load context. A test directly setting `SecurityContextHolder` and calling a service **does not verify**:

- Whether the `JSESSIONID` cookie is issued properly with `Secure`/`HttpOnly`/`SameSite`.
- Whether session fixation protection rotates the session ID after login.
- Whether logout performs real invalidation.
- Whether a session revoked on another node is still accepted.
- Whether stateless JWT verification runs on the next request.

These questions require HTTP integration tests, session repositories, proxies, or E2E tests. An injected `Authentication` is purely **test state**, offering no intrinsic security guarantee.

## 14. The Gap Grows Even Larger with MFA and SSO

### 14.1. MFA

A `@WithMockUser(roles="ADMIN")` test can let an admin endpoint pass even when the production app requires MFA. If MFA policy relies on factor authorities, assurance claims, or session state, tests must construct the right **verified factor representation** and separately test factor enrollment, OTP/WebAuthn verifiers, replay, freshness, and recovery bypasses.

Never treat `authorities={"FACTOR_TOTP"}` set in a test as proof that TOTP is verified in production. Any authority name or MFA flag can be **mocked** in tests; you must test their real issuance and verification paths.

### 14.2. OIDC login

`.with(oidcLogin())` can supply a pre-built test `OidcUser`. It is helpful for testing principal mapping and post-SSO authorization, yet it does not prove:

- `state`/`nonce` are generated and validated properly;
- authorization codes are single-use;
- ID Tokens pass signature/issuer/audience/expiry verification;
- external identities `(iss, sub)` link safely to local accounts;
- IdP logout/revocation works.

Test the OAuth client/provider exchange and callback against a test IdP or mock web server that verifies real protocol steps rather than using a mocked principal to "prove" SSO.

### 14.3. Opaque tokens

`opaqueToken()` tests support authorization with mocked principals/attributes; they do not prove the introspection endpoint is called, client authentication to the authorization server is valid, or `active=false` responses are rejected. Add integration tests with a trusted introspection simulator or test IdP service, plus token expiration/revocation.

### 14.4. API gateway preauthentication

If the architecture trusts `X-Authenticated-User` set by a gateway, a test manually setting that header simulates the trusted proxy path yet **does not prove** the backend blocks spoofed headers from the Internet. Network/proxy tests must confirm the gateway strips/overwrites client headers, the backend is unreachable publicly, and account binding plus permission sources are trustworthy.

## 15. Suggested QA Matrix for an Authentication Module

| Test | Use mock principal? | Need real verifier? | Value |
|---|---|---|---|
| Method `@PreAuthorize` allows only `ROLE_READER` | Yes | No, if test scope is authorization only | Verifies role policy |
| Controller returns exact identity from `Authentication` | Yes | No | Verifies principal mapping |
| User without role gets 403 | Yes | No | Negative authz |
| Nonexistent account `ghost` cannot log in | **No** | Yes | Anti-account-confusion |
| Wrong password still logs in | **No** | Yes | Verifies password provider |
| Locked/disabled account cannot log in | **No** | Yes | Verifies account flags at verifier |
| Password hash strategy works | No | Yes | Verifies `PasswordEncoder` |
| Wrongly signed JWT gets accepted | **No** | Yes | Verifies cryptographic `JwtDecoder` |
| Wrong audience/issuer/expired JWT | **No** | Yes | Verifies token validators |
| Real JWT missing scope gets 403 | Can supplement with mock authz, yet need ≥1 integration | Yes for end-to-end | Token mapping + permission |
| Form login missing CSRF | **No** | Full request filter | Verifies browser CSRF path |
| Cookie/session fixation after login | **No** | Needs login filter + session | Verifies lifecycle |
| MFA OTP replay | **No** | Needs real MFA verifier/store | Verifies single-use |
| Wrong-tenant object despite matching role | Yes | Not mandatory for unit policy | Verifies object ownership |
| OIDC ID Token with wrong nonce | **No** | Needs real protocol/validator | Verifies SSO security |
| Email/OTT/reset token purpose confusion | **No** | Needs purpose-specific verifier | Verifies token confusion protection |

### 15.1. Honest test naming conventions

**Authorization with mocked principal:**

```text
givenAuthenticatedReader_whenReadOwnReport_thenAllowed()
givenAuthenticatedReader_whenReadOtherTenantReport_thenForbidden()
givenMockAdmin_whenInvokeProtectedMethod_thenAllowed()
givenAnonymous_whenOpenPrivateEndpoint_thenUnauthorized()
```

**Authentication with verified evidence:**

```text
givenWrongPassword_whenHttpBasic_then401()
givenDisabledAccount_whenFormLogin_thenAuthenticationFails()
givenValidPassword_whenFormLogin_thenSessionIsEstablished()
givenUnsignedJwt_whenBearerRequest_then401()
givenExpiredJwt_whenBearerRequest_then401()
givenWrongAudienceJwt_whenBearerRequest_then401()
givenValidSignedJwt_whenBearerRequest_thenPermissionsApplied()
givenInvalidOtp_whenStepUp_thenAccessDenied()
```

This naming makes it obvious to readers **which evidence was actually processed** without inferring it from test fixtures.

## 16. Checklist Before Concluding Authentication Is Tested

1. **State each test's goal:** authentication, authorization, principal shape, HTTP filter, account status, session, or token validation.
2. **Know fixture scopes:** `@WithMockUser`/`user()` do not log in; `@WithUserDetails` looks up the user without checking passwords.
3. **Do not count mocked JWTs as crypto coverage:** `jwt()`/`oidcLogin()`/`opaqueToken()` only populate security context for testing.
4. **Run real filters:** `@AutoConfigureMockMvc(addFilters=true)` or `springSecurity()`; never confuse with `addFilters=false`.
5. **Run real verifiers for login tests:** never mock `AuthenticationManager`/`DaoAuthenticationProvider`/`PasswordEncoder` to always succeed.
6. **Test negative password cases:** wrong password, nonexistent user, disabled/locked, expired credentials, anti-enumeration.
7. **Test negative JWT cases:** bad signature, disallowed `alg`, bad issuer/audience/time, insufficient scope, wrong token type.
8. **Check status codes:** missing auth → 401/302; invalid token → 401; authenticated lacking permission → 403; authorized → app response.
9. **Keep CSRF enabled:** browser form login and state-changing POSTs must have tested CSRF policies.
10. **Real method security:** `@EnableMethodSecurity`, Spring proxy beans, negative tests catching self-invocation/bypass.
11. **Sessions/cookies:** test success handlers, session fixation, logout, and revocation when sessions exist rather than inferring from test context.
12. **SSO/MFA:** always test issuance, signing/verification, factor origin/binding, and recovery rather than inferring from mock authorities.
13. **Threat model:** test cross-tenant principals, role escalation, stale authorities, and BOLA/IDOR, not just login happy paths.
14. **Separate reporting:** distinguish mock authorization test counts, authentication integration, JWT crypto, and E2E instead of lumping them into "security tested".
15. **Check devices and infrastructure:** if using preauth/gateways, verify headers cannot be spoofed; for OIDC, test callback issuer/state/nonce; for JWT, test JWKS rotation.
16. **Test data:** use test accounts/keys/credentials only; never commit production secrets or log raw tokens/passwords.

## 17. Self-Assessment Questions

**Question 1.** `@WithMockUser(username="ghost",roles="ADMIN")` lets an admin method succeed. Can we conclude account `ghost` can log in with a password?  
**Answer:** No. The annotation creates a mocked principal context for a user that may not even exist. The test proves only authorization with the role supplied in the fixture.

**Question 2.** Does `@WithUserDetails("lan")` guarantee `PasswordEncoder.matches` ran?  
**Answer:** No. It loads `UserDetails` from the service and builds an authenticated context without sending a password through the provider. If the lookup hits a real DB, only the lookup itself is real.

**Question 3.** Why can `.with(jwt())` pass when no JWT was ever signed?  
**Answer:** It is a Spring Security Test request post-processor that creates a `JwtAuthenticationToken` for authorization; it needs neither a validly signed JWT nor a real decoder.

**Question 4.** How do you test that a wrong password is genuinely rejected?  
**Answer:** Send `httpBasic("lan","wrong")` or `formLogin().user("lan").password("wrong")` through a real `SecurityFilterChain`/`AuthenticationManager`/`DaoAuthenticationProvider` and real `UserDetailsService`+`PasswordEncoder`; assert no `Authentication` is produced.

**Question 5.** A login test sends a real Basic header yet mocks `AuthenticationManager` to always succeed. Has it tested passwords?  
**Answer:** No. The HTTP filter received credentials, yet the verifier was replaced with a mock unconditionally returning an authenticated object.

**Question 6.** Why is testing an admin role with only HTTP 200 insufficient?  
**Answer:** If security filters or method security are disabled, the request can still return 200. Negative tests blocking anonymous callers, other roles, and other tenants are required.

**Question 7.** Does Spring Security Test's `jwt()` verify audience/issuer?  
**Answer:** No. Real `JwtDecoder` validators and signed-token HTTP integration tests are needed.

**Question 8.** Is a `@WebMvcTest` test always identical to full production authentication?  
**Answer:** No. It is an MVC slice; beans/providers may be mocked or omitted. Inspect the actual chain and add `@SpringBootTest` integration tests as needed.

**Question 9.** Does calling `SecurityContextHolder.setAuthentication` in a unit test issue a real session cookie?  
**Answer:** No. It sets context only for the execution; login filters, session repositories, and HTTP cookie lifecycles must be tested separately.

**Question 10.** In the real system, a logged-in user just had their admin role revoked—will `@WithMockUser(roles="ADMIN")` catch stale sessions?  
**Answer:** No. It assumes the `ADMIN` authority is present; integration tests for revocation, role versioning, or live permission checks are needed.

## References

- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser`, and test listeners.
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` and `FilterChainProxy`.
- [Spring Security 6.5 — Running Tests as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `authentication()`, `securityContext()`.
- [Spring Security — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()`, CSRF, and form login.
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): `httpBasic()` building Basic headers for the filter to verify.
- [Spring Security — Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `oauth2Login()`, and mocked principals.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, failure/success handlers.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService`, `PasswordEncoder`, and account flags.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer/audience/time, and signature validation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, proxy authorization.
