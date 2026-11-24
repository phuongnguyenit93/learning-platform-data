# Mocking a Principal Is Not Testing Real Authentication

## 1. The problem: an allowed request does not prove login works

In Spring Security, a test can pre-populate a **principal** or **Authentication** in `SecurityContext`, then send a request to a protected endpoint. If the request returns `200 OK`, that usually proves **the application code and authorization mechanism handle a pre-supplied identity**. It **does not automatically prove** that the system verified a username/password, validated a JWT signature, exchanged an authorization code, loaded an account from the database, or created a session properly.

This is a critical boundary in the **Testing** topic of *Spring Security - fundamentals*:

- **Principal**: the identity represented during processing, such as a username or `UserDetails`. A principal can be fabricated by a test.
- **Authentication**: an object typically holding principal, credentials, authorities, and authenticated status. In a test, you can create an `Authentication` marked authenticated without supplying a valid password.
- **SecurityContext**: where Spring Security stores the `Authentication` for the current request/thread. Test helpers can populate this context directly.
- **Authentication filter / provider / decoder**: the components that read real credentials from a request and verify them. These steps may **not run at all** when a test pre-populates `SecurityContext`.

For instance, `@WithMockUser(username = "phantom", roles = "ADMIN")` lets a test simulate an admin **who does not exist in the database at all**. An endpoint guarded with `hasRole("ADMIN")` can return 200. That is a **valid authorization test**, not proof that user `phantom` can log in with any password.

**Learning objectives:** distinguish mock identities from real authentication; choose the right test level for `@WithMockUser`, `user()`, `httpBasic()`, form login, Bearer JWT, OIDC, and WebFlux; build positive/negative tests through the filter chain; spot false positives; and design a complete test matrix without forcing every test to spin up an identity provider.

## 2. Distinguishing authentication, authorization, and what tests prove

| Component / behavior | Question it answers | What should the test prove? |
| --- | --- | --- |
| **Authentication** | Is the caller who they claim to be? | Valid passwords/credentials/tokens are accepted; invalid/expired/revoked ones are rejected |
| **Authorization** | What is the authenticated identity allowed to do? | Having the right role/scope permits access; lacking permission returns 403; owner/tenant checks are enforced |
| **SecurityContext** | Which Authentication does the app see? | Principal, authorities, and username propagate properly through the request |
| **Session / token lifecycle** | How is identity stored/restored across requests? | Login/logout/timeout/rotation/revocation work as designed |
| **HTTP security integration** | How does a real request traverse filters and entry points? | 401, 403, redirects, cookies, CSRF, `WWW-Authenticate`, and security headers match the design |

A test cannot assert more than what it actually exercises:

```text
Test A: @WithMockUser("admin")
    |
    v
Pre-populated SecurityContext
    |
    v
AuthorizationFilter / controller
    |
    v
200 OK
=> Provides evidence for AUTHORIZATION RULES on a mock identity
=> No evidence for password, UserDetailsService, login, or JWT decoder


Test B: real request with Authorization: Basic ...
    |
    v
BasicAuthenticationFilter
    |
    v
AuthenticationManager -> AuthenticationProvider
    |
    v
UserDetailsService + PasswordEncoder
    |
    v
SecurityContext -> AuthorizationFilter -> controller
    |
    v
200 / 401 / 403
=> Tests the HTTP Basic pipeline configured in the test


Test C: request with really signed Bearer token
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtDecoder: signature + validators (issuer/time/audience if configured)
    |
    v
JwtAuthenticationConverter -> authorization
=> Tests the verification steps the test actually configures/executes
```

**Note:** `MockMvc` is still a simulated Servlet environment and opens no real HTTP socket. When `MockMvc` is configured with Spring Security filters, it can still invoke authentication through `BasicAuthenticationFilter` and the application context's real provider. Tests with `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client traverse a real HTTP listener, though even they do not prove integration with a production IdP/DB if the test uses stubs or in-memory data.

## 3. Commonly misunderstood helpers

| Spring Security Test tool | What does it do? | What it does **not** test automatically |
| --- | --- | --- |
| `@WithMockUser` | Creates a `SecurityContext` containing a given user, roles, or authorities | Looking up users in DB, hashing/matching passwords, HTTP login |
| `@WithUserDetails("alice")` | Uses `UserDetailsService` to load a user and build a test `Authentication` | Password matching, Basic header checks, or end-to-end form login |
| `@WithSecurityContext` | Calls a factory you write to build a custom security context | Any authentication steps the factory does not invoke |
| `mvc.perform(...with(user("x")))` | Attaches a user to the `MockMvc` request | User existence or credential verification |
| `mvc.perform(...with(authentication(auth)))` | Attaches a test-supplied `Authentication` | Proof that a provider accepts it over HTTP |
| `mvc.perform(...with(jwt()))` | Supplies a mock `JwtAuthenticationToken` for authorization | JWT signature, `iss`, `aud`, `exp`, JWKS, or real decoder |
| `mvc.perform(...with(oauth2Login()))` | Creates mock OAuth2 login state for client tests | Redirects, state/nonce, code exchange, or real token endpoint |
| `mvc.perform(...with(httpBasic(user, pass)))` | Sets the `Authorization: Basic ...` header on the request | **Can** test the provider if security filters are actually wired and no mock identity overrides it |
| `mvc.perform(...with(csrf()))` | Adds a test CSRF token to pass configured CSRF checks | Server token/cookie/HTML form issuance and real client submission |

Read the table both ways: mocking a principal is **not wrong**; it is a great tool when the goal is testing policy or controllers. The mistake lies in describing a `@WithMockUser` test as "having tested login, password encoding, JWT validation, and the entire authentication flow."

### 3.1. `@WithMockUser`

Example:

```java
@Test
@WithMockUser(username = "administrator", roles = "ADMIN")
void mockAdminMayReadAdminEndpoint() throws Exception {
    mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
}
```

The annotation creates a mock user with `ROLE_ADMIN`. The username might never exist in the database; the helper's default password is never checked by a provider. With `@WithMockUser(roles = "ADMIN")`, Spring Security Test converts the role into the `ROLE_ADMIN` authority under the default convention. If you need an exact authority string such as `SCOPE_reports.read`, use `authorities = "SCOPE_reports.read"`.

### 3.2. `with(user(...))`

Example:

```java
mvc.perform(get("/api/admin")
        .with(user("ghost").roles("ADMIN")))
        .andExpect(status().isOk());
```

`user(...)` creates a per-request identity. It **does not prove** account `ghost` exists in `UserDetailsService` or that its password is valid. Use it when testing how an endpoint handles an already-authenticated user/role.

Helpers require the security context to be integrated with `MockMvc`. Common manual setup:

```java
mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

This snippet is a fragment for a test class with `WebApplicationContext context` and the appropriate imports. `@SpringBootTest` + `@AutoConfigureMockMvc` normally configures the filter chain automatically; if `@AutoConfigureMockMvc(addFilters = false)` or `standaloneSetup(...)` omits security filters, results can bypass protection.

### 3.3. `@WithUserDetails`

`@WithUserDetails("alice")` invokes a real `UserDetailsService` (or a bean replaced by a mock) to fetch the principal, then builds an authenticated context. It can catch missing users or broken authority mappings in the loader used, yet it **does not pass any password through `AuthenticationManager`/`PasswordEncoder.matches(...)`**. Therefore, you still need valid/invalid credential tests at the authentication layer.

### 3.4. `with(httpBasic(...))` is a request credential, not a pre-granted identity

Unlike `with(user(...))`, the HTTP Basic helper mainly writes a header:

```text
Authorization: Basic YWxpY2U6Y29ycmVjdC1wYXNzd29yZA==
```

The header merely Base64-encodes `alice:correct-password`; **it authenticates no one by itself**. If the real `BasicAuthenticationFilter`/`AuthenticationManager` runs in the filter chain, Spring Security reads the header and checks credentials with the provider. If filters are not running, a 200 response cannot serve as authentication proof.

Do not combine `@WithMockUser` with `with(httpBasic("alice", "wrong"))` and assume 401/200 reflects password verification: the mock identity can skew the precondition. Keep mock authorization tests and Basic credential tests in separate test methods, with no mock security context on login-checking requests.

## 4. Runnable Java 17+ example: simulating a user vs testing real HTTP Basic

The project below uses **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Maven, and Java 17+**. It intentionally stores users in memory so tests are repeatable; HTTP Basic authentication steps still go through the provider. Production systems must use an appropriate `PasswordEncoder` and secure user/secret stores instead of `{noop}`.

### 4.1. Test goals

- `GET /api/me` requires authentication and returns the logged-in username.
- `GET /api/admin` requires `ROLE_ADMIN`.
- Real accounts in `UserDetailsService`: `alice`/`correct-password` has USER, `administrator`/`admin-password` has ADMIN.
- `phantom` does not exist in the user store. With `@WithMockUser`, `phantom` can still access `/api/admin` if assigned ADMIN because the test builds the identity.
- HTTP Basic requests with `phantom` or a wrong password get **401** when running through the real filter chain.
- Valid Basic request from `alice` to `/api/admin` gets **403**; valid request from `administrator` gets **200**.

### 4.2. Structure

```text
security-test-boundary/
├── pom.xml
└── src/
    ├── main/java/demo/SecurityTestBoundaryApplication.java
    └── test/java/demo/
        ├── AuthenticationBoundaryMvcTest.java
        └── LiveHttpAuthenticationTest.java
```

### 4.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-test-boundary</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

### 4.4. `src/main/java/demo/SecurityTestBoundaryApplication.java`

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityTestBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestBoundaryApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}correct-password")
                        .roles("USER")
                        .build(),
                User.withUsername("administrator")
                        .password("{noop}admin-password")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @GetMapping("/api/admin")
        Map<String, String> admin(Authentication authentication) {
            return Map.of(
                    "username", authentication.getName(),
                    "result", "allowed");
        }
    }
}
```

Key takeaways:

1. A real `UserDetailsService` exists in the application context containing only `alice` and `administrator`. `phantom` is created solely by test mocks.
2. `httpBasic` configures `BasicAuthenticationFilter` and username/password authentication with the appropriate provider. When a request carries a Basic header, Spring Security decodes and verifies the credentials.
3. `"{noop}"` is used **only in this demo** to avoid generating static hashes. Production uses salted hashes and password-upgrade policies such as BCrypt/Argon2 and a secrets store.
4. `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority. Account `alice` only has `ROLE_USER`, so an authenticated request from Alice to `/api/admin` gets 403.
5. There is no form login and no custom authentication controller. The setup keeps tests focused on Basic and authorization. The demo uses GET only, so no CSRF adjustments are needed.

### 4.5. `MockMvc` tests: one suite, two different kinds of evidence

Create `src/test/java/demo/AuthenticationBoundaryMvcTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AuthenticationBoundaryMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "phantom", roles = "ADMIN")
    void mockIdentityCanPassAuthorizationWithoutAnAccount() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("phantom"))
                .andExpect(jsonPath("$.result").value("allowed"));
    }

    @Test
    void requestPostProcessorAlsoInjectsIdentity() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("ghost").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("ghost"));
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nonExistentUserCannotAuthenticateWithBasic() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("phantom", "any-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejectedByAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordAuthenticatesOrdinaryUser() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "correct-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGetsForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "correct-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void realAdminCredentialsAllowAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("administrator", "admin-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("administrator"));
    }
}
```

**Evidence breakdown for the suite above:**

| Test | Meaningful flow exercised | Valid conclusion |
| --- | --- | --- |
| `@WithMockUser("phantom", ADMIN)` | Pre-populated SecurityContext | Authorization rule accepts ADMIN; does **not** prove login |
| `with(user("ghost").roles("ADMIN"))` | Mock principal on the request | Controller receives mock principal and policy permits |
| No credentials | HTTP chain entry point | Endpoint blocks anonymous callers |
| Basic `phantom:any-password` | HTTP Basic + provider + user store | Non-existent user gets 401 |
| Basic `alice:wrong-password` | HTTP Basic + provider + password check | Wrong password gets 401 |
| Basic `alice:correct-password` | HTTP Basic + provider + controller | Valid credentials authenticate into authenticated endpoint |
| Basic Alice to `/api/admin` | Authentication succeeds then authorization runs | Authenticated user lacking role gets 403 |
| Basic administrator to `/api/admin` | Both authentication and authorization succeed | Existing user with valid password/ADMIN gets 200 |

`@AutoConfigureMockMvc(addFilters = true)` keeps filters enabled in the test. If changed to `addFilters = false`, 401/403 assertions may change, and you must no longer call them authentication tests. Keep every authentication test **free of `@WithMockUser` or `with(user())`**.

### 4.6. Testing HTTP over a real port (a layer above `MockMvc`)

`MockMvc` opens no socket. When you need to verify the real HTTP path, create `src/test/java/demo/LiveHttpAuthenticationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpAuthenticationTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void wrongPasswordIs401OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "bad-password")
                .getForEntity("/api/me", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void validCredentialsAre200OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "correct-password")
                .getForEntity("/api/me", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("\"username\":\"alice\"");
    }

    @Test
    void ordinaryUserIs403OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "correct-password")
                .getForEntity("/api/admin", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }
}
```

`TestRestTemplate` is auto-configured by Spring Boot Test in a `RANDOM_PORT` context and calls HTTP over the server-assigned port. This is **real HTTP to the test server** with in-memory users. It still does not verify integration with a production DB, reverse proxy, TLS termination, or an external identity provider. Localhost tests use HTTP for convenience; never send Basic credentials over plain HTTP in real deployments.

### 4.7. Commands to compile, run tests, and probe with `curl`

Run in the root directory containing `pom.xml`, requiring Java 17+ and Maven:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/security-test-boundary-0.0.1-SNAPSHOT.jar
```

Second terminal:

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong-password http://localhost:8080/api/me
curl -i -u alice:correct-password http://localhost:8080/api/me
curl -i -u alice:correct-password http://localhost:8080/api/admin
curl -i -u administrator:admin-password http://localhost:8080/api/admin
curl -i -u phantom:any-password http://localhost:8080/api/admin
```

The expected statuses in order are **401, 401, 200, 403, 200, 401**. The `GET /api/me` request with valid credentials returns JSON containing `"username":"alice"`; the valid admin request contains `"result":"allowed"`. JSON whitespace/key ordering, headers, and error bodies can vary by version/config; assert the status and the fields you actually need. Do not report Maven output as "observed passing" unless you have executed it in an environment with Maven/Java.

## 5. Testing method security: mock principals are the right tool for the job

When your goal is proving `@PreAuthorize` protects a service, a mock principal is an effective way to isolate the policy. **Service fragment** example in an application with `@EnableMethodSecurity` enabled:

```java
@Service
public class BillingService {

    @PreAuthorize("hasAuthority('INVOICE_APPROVE')")
    public String approve(long invoiceId) {
        return "approved-" + invoiceId;
    }
}
```

A method-security test can use:

```java
@Test
@WithMockUser(authorities = "INVOICE_APPROVE")
void approverCanApprove() {
    assertThat(billingService.approve(42L)).isEqualTo("approved-42");
}

@Test
@WithMockUser(roles = "USER")
void readerCannotApprove() {
    assertThatThrownBy(() -> billingService.approve(42L))
            .isInstanceOf(AccessDeniedException.class);
}
```

These are **fragments** requiring the proper imports and a real context containing the service/proxy with method security enabled. Such tests prove the method policy against a supplied `Authentication`; they do not prove passwords, login, or user lookup. Also verify object/tenant access inside the service if `invoiceId` is authorization-sensitive: the `INVOICE_APPROVE` role alone may not suffice to approve any arbitrary invoice.

Ensure calls pass through the Spring proxy; self-invocation within the same bean can bypass the AOP proxy and prevent `@PreAuthorize` from running. Tests should invoke the Spring-managed bean rather than manually instantiating `new BillingService()` and inferring real protection.

## 6. JWT Resource Server: the `jwt()` helper skips real token verification

In Spring Security Test for Servlet, `with(jwt())` (or `with(authentication(jwtAuthenticationToken))`) supplies a mock `JwtAuthenticationToken` to the request. These APIs are **ideal** for testing roles/scopes in controllers and authorization, yet they do not run:

- JWT signature verification or signing algorithm checks;
- JWK loading, key rotation handling, or issuer trust;
- `iss`, `aud`, `exp`, `nbf` validation via real validators;
- Parsing malformed Bearer headers from clients;
- Real converter/claim mapping if the test assigns authorities directly.

### 6.1. Example authorization test with mock JWT (fragment)

Suppose a Resource Server API configures `/api/reports` with policy `hasAuthority("SCOPE_reports.read")`:

```java
mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
```

This fragment needs static `jwt` from `SecurityMockMvcRequestPostProcessors` and `SimpleGrantedAuthority`, plus a matching endpoint/config. The test **creates no signed token**. It only verifies that the endpoint accepts a `JwtAuthenticationToken` already carrying `SCOPE_reports.read`.

If the real converter must extract `app_roles` from claims and turn them into `ROLE_ADMIN`, a mock test assigning `ROLE_ADMIN` directly **will not catch converter bugs**. Separate tests for mapping claims to authorities (unit-testing the converter) from authorization tests using those authorities.

### 6.2. How to test a Bearer token going through the pipeline?

To test **real decoder and validation** of a Resource Server:

1. Use HTTP or MockMvc requests with an `Authorization: Bearer <token>` header (generated by a real signing test fixture).
2. Ensure the configured `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, and `JwtDecoder` actually participate in the request.
3. Use dedicated test public/private keys, allowed signing algorithms, and fixture issuer/audience values.
4. Send tokens that are: valid, bad signature, wrong issuer, wrong audience, expired `exp`, future `nbf`, and missing scope.
5. Assert 401 for invalid tokens, 403 when authentication succeeds but permissions are missing, and 200 when all conditions are met. For Bearer tokens, also verify `WWW-Authenticate` and protocol error codes.

If you replace `JwtDecoder` with `@MockitoBean JwtDecoder` and stub it to always return a valid `Jwt`, that test verifies the filter/integration path with a **mock decoder**, not real signatures or validators. A mock decoder is useful for targeted tests as long as you state the scope of evidence clearly.

**Warning:** `jwt().jwt(jwt -> jwt.claim("roles", ...))` or `Jwt.withTokenValue(...)` fixtures can contain arbitrary claims you set yourself; that does not prove claims came from a trusted issuer. Never describe a mock token as "verified for real."

### 6.3. JWT and authentication success have multiple layers

A 200 JWT response can be a false positive if the test:

- Pre-populates `Authentication` via `jwt()`, skipping the decoder.
- Assigns authorities directly instead of running the converter production uses.
- Disables security filters or bypasses the corresponding `SecurityWebFilterChain`.
- Mocks the entire provider/decoder without separate validation tests.
- Checks only 200 without testing missing/invalid/expired tokens or insufficient permissions.

Therefore, test reports should distinguish **mock token**, **mock decoder**, and **really signed token with real decoder**.

## 7. OAuth2 Login/OIDC: mock users do not test the login protocol

Helpers like `oauth2Login()` and `oidcLogin()` (Servlet MockMvc) create an `OAuth2AuthenticationToken`/`OidcUser` and related state for authorization/controller tests. They do not verify the full Authorization Code/OIDC flow:

```text
Browser -> /oauth2/authorization/{registrationId}
           -> redirect to identity provider
           -> callback with code and state
           -> verify state, token exchange, ID token, nonce
           -> load user/claims, map authorities
           -> create session, redirect back to application
```

A `with(oidcLogin())` test can let a controller read `email` or `sub` claims without any request to the token or user-info endpoints. That is a valid test for code handling a **post-login** principal, not proof of OAuth2 state CSRF protection, nonce replay checks, issuer validation, client credentials, redirect URIs, or real provider mapping.

**Sensible test design:**

- **Controller/authorization**: use `oauth2Login()`/`oidcLogin()` with mock claims/authorities.
- **Login mapping**: unit-test `GrantedAuthoritiesMapper`, `OAuth2UserService`, and `OidcUserService` with contract payloads.
- **Protocol**: integration test with a mock IdP supporting discovery, authorization, token, JWKS, and user-info if used; check redirects, state/nonce, cookies/sessions, and errors.
- **Real end-to-end**: staging environment with provider/registration config matching production, authorized access, and dedicated test accounts.

Never rely on mock OAuth2 login as the sole proof that SSO works properly.

## 8. Real authentication flow in form login

When an application uses `formLogin`, mock principals also bypass critical steps:

- `POST /login` must route through `UsernamePasswordAuthenticationFilter` per matcher/config.
- `AuthenticationManager` selects an `AuthenticationProvider`, calls `UserDetailsService`, and checks the password with the encoder.
- CSRF configuration may require a token on POST; tests must supply a valid token.
- Successful login may rotate the session ID, store the security context, and invoke the success handler/redirect.
- Failed login must invoke the failure handler and must not store an authenticated session.

Example **fragment for an app with `formLogin` and a matching user store enabled**:

```java
mvc.perform(formLogin().user("alice").password("correct-password"))
        .andExpect(authenticated().withUsername("alice"));

mvc.perform(formLogin().user("alice").password("wrong-password"))
        .andExpect(unauthenticated());
```

This snippet requires static imports `formLogin` (`SecurityMockMvcRequestBuilders`), `authenticated`/`unauthenticated` (`SecurityMockMvcResultMatchers`), and `MockMvc` wired with Spring Security filters. `formLogin()` constructs a POST to the default login endpoint along with a valid test CSRF token; if the app customizes the login URL or parameter names, configure the request builder accordingly.

Unlike `@WithMockUser`, `formLogin()` exercises the login mechanism inside `MockMvc` when real filters/providers run. Still, a passing response does not prove an external browser form submits tokens/cookies/redirects properly or that production uses the same auth provider.

## 9. CSRF, sessions, and logout: mock contexts also have limits

A request with `@WithMockUser` and `with(csrf())` can reach a POST endpoint and be authorized. That proves **the filters and policy configured in the test accept a valid test CSRF token**, not that:

- Real pages/forms issue tokens properly;
- CSRF cookies or headers from browsers survive the reverse proxy;
- Session IDs rotate after login;
- Logout clears cookies/sessions and blocks reuse of credentials/tokens as designed;
- Session timeouts or concurrent-session controls work across multiple nodes.

Add HTTP-flow tests whenever those behaviors are requirements. For Bearer-token APIs **that do not use cookie authentication**, CSRF may be configured differently; never disable CSRF across all systems simply because "the API uses JSON."

One data-protection rule: never log raw `Authorization` headers, cookies, passwords, access tokens, refresh tokens, or session data in test output/snapshots. When tests fail, logs should identify error codes and failing steps without exposing credentials.

## 10. WebFlux/reactive: same distinction, different test API

In WebFlux, the HTTP pipeline uses `SecurityWebFilterChain`, `AuthenticationWebFilter`, and `ReactiveAuthenticationManager` instead of Servlet `SecurityFilterChain` and servlet filters. Tests typically use `WebTestClient` with Spring Security test support:

- `mutateWith(mockUser("alice"))`: builds a reactive security context with a mock user.
- `mutateWith(mockJwt())`: supplies a mock JWT for authorization.
- Requests with `Authorization: Basic ...` or `Authorization: Bearer ...` traverse the authentication pipeline **if** `WebTestClient` is bound to the real application/security config.
- `@WithMockUser` can be helpful for reactive security tests; it still checks no real credentials.

**Illustrative fragment for WebFlux given a `WebTestClient client` and `hasRole("ADMIN")` policy:**

```java
client.mutateWith(mockUser("phantom").roles("ADMIN"))
        .get().uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
```

This tests a simulated authorized principal; it does not verify that `phantom` can log into the reactive application. Another fragment for JWT:

```java
client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
```

These fragments require `mockUser`/`mockJwt` imports from `SecurityMockServerConfigurers` and an application that applied Spring Security to `WebTestClient`; they are not standalone. `mockJwt()` does not verify JWT signatures. When testing a reactive JWT converter, test the appropriate `ReactiveJwtAuthenticationConverter`/adapter and add an integration test with a real `ReactiveJwtDecoder`. Never confuse Servlet filters and extension points with reactive ones.

## 11. Minimum test matrix by confidence level

Not every feature needs a real IdP running in every test. Divide tests into layers with clear goals:

| Test layer | Typical tools | Scope proven | Insufficient to conclude |
| --- | --- | --- | --- |
| Converter / provider unit test | JUnit, mock repository, real encoder/validator where needed | Logic turning credentials/claims into outcomes and errors per input | HTTP filters/redirects/sessions |
| Controller and policy test | `@WithMockUser`, `user()`, `jwt()`, `MockMvc` | Authorization, responses, controller principal mapping | Passwords, token signatures, login protocols |
| HTTP authentication test in Spring context | `@SpringBootTest` + `@AutoConfigureMockMvc` + `httpBasic()` / `formLogin()` | Filters, providers/encoders/user stores configured in context, 401/403/200 | Sockets, reverse proxies, real external IdP |
| HTTP integration test over port | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/HTTP client | Requests through the test app's real web server | Production infrastructure if still using mock DB/IdP |
| External identity integration | Locally signed JWT + real decoder, or protocol-compliant IdP stub | Signature/issuer/audience/claims/redirects per stub fidelity | Exact match with production issuer config |
| Staging E2E | Real client, TLS, IdP/test accounts, network/proxy/session | End-to-end client flow through target infrastructure | High-load behavior or production-only changes |

In every layer, always test **failure paths**. Authentication is not just "valid credentials return 200"; missing, wrong, locked, expired, malformed credentials, wrong issuer/audience tokens, and insufficient permissions are high-value security cases.

### 11.1. Status matrix for the example HTTP Basic API

| Caller and request | Expected | Deciding step |
| --- | --- | --- |
| Anonymous `GET /api/me` | 401 | Unauthenticated |
| Non-existent username + any password | 401 | User lookup / provider |
| `alice` + wrong password | 401 | Password check |
| `alice` + right password to `/api/me` | 200 | Authentication succeeds |
| `alice` + right password to `/api/admin` | 403 | Authorization lacks ADMIN |
| `administrator` + right password to `/api/admin` | 200 | Authentication + authorization |
| `@WithMockUser("phantom", ADMIN)` to `/api/admin` | 200 in mock test | Simulated context, **no credential validation** |

A system's final outcome might be a 302 redirect instead of 401 for form login, or include a Bearer challenge header for JWT; never apply one status table across every authentication mechanism while ignoring configuration.

## 12. Dangerous false positives and how to catch them

1. **Testing all controllers with `@WithMockUser` and reporting "login works."** Add Basic/form/JWT request tests through the filter chain plus invalid-credential cases.
2. **Creating a mock user with ADMIN role who does not exist in the DB.** A 200 result applies to authorization; test the user store/provider in separate tests.
3. **Setting `@AutoConfigureMockMvc(addFilters = false)` to avoid 403.** Tests can skip all security filters; fix test setup to keep filters and supply CSRF if the endpoint requires it.
4. **Using `MockMvcBuilders.standaloneSetup` and assuming Spring Security is integrated.** Register security filters/configurers when testing the pipeline; prefer `webAppContextSetup(...).apply(springSecurity())`.
5. **Granting `ROLE_ADMIN` via `jwt().authorities(...)` and concluding role claim mapping works.** Unit-test the converter on realistic issuer claims, then test JWT through a decoder.
6. **Mocking `JwtDecoder` to always return a valid token and claiming JWT signatures are verified.** Use a real decoder + signed fixtures + invalid signature/issuer/audience tests.
7. **Using `@WithUserDetails` and assuming password matching was tested.** The helper loads `UserDetails` and populates context; add tests with wrong credentials.
8. **Having no anonymous or invalid-credential tests.** An accidentally `permitAll()` route can let happy-path tests keep passing.
9. **Asserting only response JSON without checking 401/403/302 or headers.** Easy to miss authentication entry points, CSRF, and Bearer challenges.
10. **Putting `@WithMockUser` on the test thread while hitting a live server with an HTTP client.** Test-thread `SecurityContext` does not cross the network to server threads; send credentials on the request.
11. **Not testing sessions across requests.** A single mocked authenticated request does not prove login creates a session or logout invalidates it.
12. **Mixing up roles and scopes in tests.** `roles = "ADMIN"` grants `ROLE_ADMIN` by default, not `SCOPE_admin`; `hasAuthority(...)` policies require exact strings.
13. **Writing a custom `AuthenticationProvider` while only testing controllers with mocked contexts.** Bugs in `supports()`, password hashing, exceptions, or lock states are never exercised.
14. **Passing tests on 200 when no security filter chain matched the request.** Tests must verify matchers, fallbacks, multiple chains, and chain order. A 200 response can come from an unprotected endpoint.
15. **Omitting tests for disabled/locked/expired-password users.** Account-status flags are completely bypassed by mocks; test the real provider and user store.
16. **Seeing 401 on a bad request and assuming the signature was checked.** 401 could come from a missing Bearer header or mock decoder; verify which code path actually ran.

## 13. A balanced testing strategy for development teams

For a new security feature, follow this workflow:

1. **State the exact target under test.** Authorization policy, passwords, JWT signatures, role mapping, CSRF, sessions, or SSO redirects? Avoid vague "security test" labels.
2. **Use mock principals for business logic and authorization.** This keeps tests fast, expressive, and low-dependency.
3. **Include at least one request-level authentication path per supported mechanism.** HTTP Basic needs valid/invalid/missing credentials; form login needs success/failure; JWT needs valid/invalid signature/time/issuer/audience.
4. **Keep security filters enabled in integration tests.** Verify the test context wires the `SecurityFilterChain` and relevant providers/decoders.
5. **Separate mocked dependencies from integration dependencies.** If `UserDetailsService`, `AuthenticationManager`, or `JwtDecoder` is mocked, state explicitly what was not tested for real.
6. **Assert both status codes and side effects.** For denied requests, confirm no session is created and no state mutates; do not look solely at HTTP status.
7. **Test object-level permissions.** A valid role does not prove cross-tenant records are blocked; write IDOR/BOLA and ownership tests.
8. **Keep the test suite repeatable.** Use dedicated test fixtures, secrets, and signing keys; never depend on production accounts; control clocks when testing token expiration.
9. **Name tests after the evidence they provide.** `mockPrincipalCanReadAdminEndpoint`, `wrongPasswordRejectedByBasicAuth`, `invalidSignatureRejectedByDecoder` — names state the scope directly.
10. **Revisit tests when changing mechanisms.** Switching from Basic to JWT requires replacing credential tests with Bearer/decoder tests rather than keeping `@WithMockUser` as proof for the new mechanism.

### Before merging, ask

- Where do mock users come from? Is there any test that actually exercises the authentication filter/provider or JWT decoder?
- If the real password is changed to a wrong one, which test fails? If none, the password flow is untested.
- If a user is deleted from the DB, which test catches it? If all still pass, user lookup/integration is untested.
- If a token is expired or forged, which test catches it? If none, token validation is untested.
- If a caller has valid credentials yet lacks the role, which test verifies 403?
- If a filter chain has a bad matcher or disabled filters, which test catches it?
- If form login or SSO requires CSRF/state/nonce and sessions, which test walks through that behavior?

## 14. Practice exercises

1. `@WithMockUser(username="root", roles="ADMIN")` makes `GET /admin` return 200, yet `root` does not exist in the database. What did the test prove and what did it not prove?
2. Why is `with(httpBasic("alice","wrong"))` better for testing authentication than `with(user("alice"))` when real filters and providers are active?
3. A JWT test calls `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))`. Can it detect a misconfigured `issuer-uri` or audience?
4. When using `@WithUserDetails`, which component may be invoked? Which component still has not checked credentials?
5. A team uses only `@WebMvcTest` with mocked controllers and sees all requests return 200. What additional tests are needed to verify real filters/authorization?
6. Why does `@WithMockUser` on a JUnit thread not automatically authenticate HTTP requests sent to `RANDOM_PORT`?
7. What new tests must be added when migrating an app from form login/sessions to a JWT Resource Server?
8. If `ROLE_ADMIN` is still supplied by `@WithMockUser` while the production JWT converter is broken, what tests catch it? Distinguish converter unit tests from Bearer pipeline integration tests.
9. In a WebFlux app, how does `mockJwt()` differ from an HTTP request carrying a really signed token?
10. When an authenticated request receives 403, should you fix it by disabling CSRF or changing `hasRole` to `permitAll`? What should you diagnose first?

## 15. Official documentation

- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Testing OAuth 2.0 and JWT with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — WebFlux Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive Test OAuth 2.0 / JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html)

**Takeaway:** mock principals provide useful evidence about **behavior once an identity is established**. To prove **real authentication**, include at least one test layer that sends credentials/tokens through the right filter/provider/decoder and tests failure cases too. Naming tests after their scope prevents mistaking a `200 OK` response for a secure login system.
