# 29.3. Using `oidcLogin()` to Simulate an OIDC User

## Lesson Objectives

When testing a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** application built with Servlet/MVC, not every test needs to open a browser, redirect to an OpenID Provider (OP), enter a password, and exchange an authorization code for tokens.

When the goal is testing **controllers or authorization rules after a user has logged in with OIDC**, Spring Security Test provides the `oidcLogin()` request post-processor for `MockMvc`.

Shortest example:

~~~java
mvc.perform(get("/me").with(oidcLogin()))
        .andExpect(status().isOk());
~~~

`oidcLogin()` places a **simulated Authentication with an `OidcUser` principal** into the request context. It lets you quickly test business logic that depends on OIDC claims, roles, and registrations without needing a real OpenID Provider.

Important boundary: **`oidcLogin()` does not execute the OIDC Authorization Code flow, does not call the token endpoint, and does not verify a real ID token signature.** It tests behavior once an OIDC principal has been simulated as authenticated.

After this lesson, you will be able to:

1. Explain the purpose, API, and limits of `SecurityMockMvcRequestPostProcessors.oidcLogin()`.
2. Configure `spring-security-test` and `MockMvc` with the Spring Security filter chain.
3. Use `oidcLogin()` with `@SpringBootTest`/`@AutoConfigureMockMvc` or `@WebMvcTest`.
4. Simulate subject, issuer, email, and other ID token claims using `idToken(...)`.
5. Set UserInfo claims using `userInfoToken(...)`.
6. Assign explicit authorities/roles using `authorities(...)`.
7. Inject a custom `OidcUser` into the request via `oidcUser(...)`.
8. Select a specific `ClientRegistration` when the application supports multiple OIDC providers.
9. Test `@AuthenticationPrincipal`, `OAuth2AuthenticationToken`, and `SecurityContext`.
10. Test allowed/denied endpoints, method security, and CSRF with MockMvc.
11. Distinguish testing claims-to-authorities mapping from testing endpoints that already receive authorities.
12. Test tenant membership, ownership, and identity keyed by issuer + subject.
13. Distinguish `oidcLogin()` from `oauth2Login()`, `jwt()`, `opaqueToken()`, `user()`, and `@WithMockUser`.
14. Identify when real integration tests are required for `state`, `nonce`, PKCE, callbacks, issuer/JWKS validation, or token refresh.
15. Avoid false-green tests caused by over-granting permissions to test users or accidentally omitting `SecurityFilterChain`.

---

## 1. Practical Problem: A Controller Requiring an OIDC Principal

Suppose an Employee Portal has an endpoint that returns the current user's details:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getSubject(),
                user.getEmail());
    }

    record Profile(String subject, String email) {}
}
~~~

In production, `OidcUser` is created after Spring Security completes the OIDC Login steps.

~~~text
Browser -> Portal -> OpenID Provider
  -> Authorization Request with state
  -> OP authenticates user
  -> Callback with code + state
  -> Portal exchanges authorization code for tokens
  -> ID token is verified
  -> Builds OAuth2AuthenticationToken with OidcUser
  -> Controller reads Authentication
~~~

If you only need to verify the controller returns the right `subject` and `email`, spinning up a real OP makes tests slow and hard to control.

Use `oidcLogin()` to **skip the already-simulated protocol steps** and pass a specific OIDC principal directly into the request.

### 1.1. Test Goals and Appropriate Tools

| Question | How to test |
|---|---|
| Does the controller read subject/email properly from `OidcUser`? | `oidcLogin()` |
| Is the endpoint restricted to users with `ROLE_ADMIN`? | `oidcLogin().authorities(...)` |
| Does the controller display the right registration ID? | `oidcLogin().clientRegistration(...)` |
| Is a user lacking tenant membership blocked? | `oidcLogin()` + domain authorization |
| Does POST enforce CSRF protection? | `oidcLogin()` + `csrf()` |
| Is the browser redirected to the right OP? | Authorization endpoint/filter test |
| Is a callback with an invalid `state` blocked? | Login flow integration test |
| Is an ID token with invalid signature/issuer rejected? | OIDC validation integration test |
| Does the Resource Server reject a JWT with wrong audience? | Resource Server JWT tests |
| Is refresh token rotation stored properly? | Authorized-client manager/token endpoint integration test |

**An OIDC principal test is not a full OIDC Login test.**

## 2. Where Does `oidcLogin()` Live?

The API is a static factory method on:

~~~java
org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors
~~~

Static import:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Usage in a MockMvc request:

~~~java
mvc.perform(get("/me").with(oidcLogin()));
~~~

This is a Spring Security Test `RequestPostProcessor`. It configures the test request so `SecurityContext` contains a simulated OIDC authentication.

### 2.1. Components Simulated

~~~text
MockMvc request
  -> .with(oidcLogin())
      -> Simulated OAuth2AuthenticationToken
      -> Simulated OidcUser
      -> Simulated ID token claims
      -> Simulated UserInfo claims if configured
      -> Simulated GrantedAuthority set
      -> Simulated ClientRegistration context
  -> Spring Security filter chain
  -> MVC Controller / Method Security
  -> HTTP response assertion
~~~

In some helpers/versions, an authorized client test context is also prepared for the request. Even then, never treat test tokens as real access tokens issued and verified by an AS.

### 2.2. Steps That Are NOT Executed

`oidcLogin()` does not automatically:

- Call the OP authorization endpoint.
- Render a login form or MFA prompt.
- Execute a consent flow.
- Generate and verify a real authorization response.
- Exchange a code at the token endpoint.
- Fetch metadata/JWKS and verify the ID token signature.
- Validate `nonce` or a PKCE verifier with the OP.
- Call the UserInfo endpoint.
- Perform a refresh token grant or rotation.
- Revoke tokens at the Authorization Server.

All claims added by the test are **trusted as mock data** for the request.

### 2.3. Why Is `SecurityFilterChain` Still Needed?

The purpose of a MockMvc security test is to send the simulated Authentication through real authorization rules:

~~~text
authenticated()
hasRole(...)
hasAuthority(...)
@PreAuthorize(...)
CSRF protection
~~~

If you disable filters or run the controller in a setup without security, many tests will still return HTTP 200 without proving security rules are enforced.

## 3. Dependencies for Servlet Testing

### 3.1. Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
~~~

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-security-test` should match the Spring Security version used by the application. Projects using the Spring Boot BOM usually do not need to specify a separate version.

### 3.3. Key Classes to Know

| Class/API | Package/meaning |
|---|---|
| `MockMvc` | Spring Test Servlet MVC |
| `oidcLogin()` | Spring Security Test request post-processor |
| `OidcUser` | OIDC principal |
| `OidcIdToken` | ID token object |
| `OidcUserInfo` | UserInfo claims |
| `OAuth2AuthenticationToken` | Authentication after OAuth2/OIDC Login |
| `ClientRegistration` | OAuth client configuration |
| `SimpleGrantedAuthority` | Test authority |
| `csrf()` | CSRF request post-processor |

## 4. MockMvc with Spring Boot

Two common options:

- `@SpringBootTest` + `@AutoConfigureMockMvc`: loads a broad application context.
- `@WebMvcTest`: loads an MVC slice, well suited for controller tests.

### 4.1. Full Context Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loggedInOidcUserCanReadProfile() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()))
                .andExpect(status().isOk());
    }
}
~~~

Advantage: loads many production components, including `SecurityFilterChain` configuration when properly component-scanned or imported.

Disadvantage: large context; may be affected by DB, messaging, or OIDC discovery if the app initializes external integrations.

### 4.2. Controller Slice Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsOidcAuthentication() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()))
                .andExpect(status().isOk());
    }
}
~~~

If the controller requires a service, supply a test dependency matching your Spring Boot version (mock/test bean). If you want to test the **production `SecurityFilterChain`**, you may need `@Import(...)` for the specific security configuration.

### 4.3. Do Not Assume a Test Slice Has Every Bean

`@WebMvcTest` may omit:

- Service implementations outside MVC.
- Custom `GrantedAuthoritiesMapper`.
- Some OIDC Client/`ClientRegistration` beans depending on configuration.
- Method-security proxies on services if the service is mocked.
- Persistence/database beans.

This is intentional. Use a full context when the test goal spans multiple layers.

### 4.4. Avoid Calling the Production OP During Context Startup

Configuring `issuer-uri` can trigger metadata discovery when creating a registration.

To keep tests independent, use a test configuration with a fake `ClientRegistration`, fake issuer endpoints, or a mock discovery server. Never let unit tests hit the production OP.

## 5. Testing a Controller with Explicit ID Token Claims

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getSubject(),
                user.getEmail());
    }

    record Profile(String subject, String email) {}
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsSubjectAndEmail() throws Exception {
        mvc.perform(get("/me")
                        .with(oidcLogin()
                                .idToken(token -> token
                                        .claim("sub", "alice-123")
                                        .claim("email",
                                                "alice@example.test"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("alice-123"))
                .andExpect(jsonPath("$.email")
                        .value("alice@example.test"));
    }
}
~~~

### 5.1. What Does This Test Verify?

- The controller receives an OIDC principal.
- `sub` and email are read properly from test data.
- The JSON response contains the expected values.
- The request passes through the security rules configured in the test context.

### 5.2. What Does This Test NOT Verify?

- That Alice actually exists at the OP.
- That the email was verified by the OP.
- That the ID token has a valid signature.
- That the Authorization Code callback succeeded.
- That the portal holds an access token with the right audience for downstream APIs.

### 5.3. Do Not Rely on Helper Defaults

`oidcLogin()` provides a default test principal/claims. Set claims explicitly whenever they affect business logic so tests stay readable and do not depend on implicit dummy defaults.

## 6. Customizing `idToken(...)`

Creating simulated ID token claims:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("sub", "alice-123")
                .claim("email", "alice@example.test")
                .claim("email_verified", true)))
~~~

### 6.1. Subject

If code calls:

~~~java
user.getIdToken().getSubject()
~~~

then test `sub`.

### 6.2. Custom Claims

If the application calls:

~~~java
user.getIdToken().getClaimAsString("department")
~~~

test:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("sub", "alice-123")
                .claim("department", "finance")))
~~~

### 6.3. Issuer and Audience

You can simulate:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("iss", "https://login.test.example")
                .claim("sub", "alice-123")
                .claim("aud", java.util.List.of("portal-web"))))
~~~

**`iss`/`aud` values in a mock are not verified by a real JWT decoder.**

If you set `iss=https://untrusted.test`, the request is still treated as authenticated because `oidcLogin()` does not replay token validation. Use an OIDC integration test to verify untrusted-issuer rejection.

### 6.4. Claims Reference

| Claim | Meaning | Notes for mocks |
|---|---|---|
| `sub` | Subject within the issuer namespace | Not globally unique |
| `iss` | OP issuer | `oidcLogin()` does not verify issuer |
| `aud` | RP audience | Not the API access-token audience |
| `email` | Email | May be absent |
| `email_verified` | Email verified per OP | Do not infer from `email` alone |
| `preferred_username` | Display username | Not necessarily a stable identity |
| `groups` | Custom group claim | Does not automatically become Spring authorities |
| `auth_time` | Authentication time | Relevant when app checks freshness |
| `acr`/`amr` | Authentication context/method | Provider-specific semantics |

## 7. `userInfoToken(...)`: Simulating UserInfo

Sometimes the OP provides email, name, or profile in UserInfo instead of the ID token.

~~~java
mvc.perform(get("/me")
                .with(oidcLogin()
                        .idToken(token -> token
                                .claim("sub", "alice-123"))
                        .userInfoToken(info -> info
                                .claim("email", "alice@example.test")
                                .claim("name", "Alice Example"))))
        .andExpect(status().isOk());
~~~

### 7.1. Does It Call the HTTP UserInfo Endpoint?

No. `userInfoToken(...)` constructs a simulated `OidcUserInfo` so the principal contains UserInfo claims.

### 7.2. When Code Reads `OidcUser.getEmail()`

`OidcUser` can expose combined claims from the ID token and UserInfo. Tests should put claims in the same source used by the production OP.

If a claim exists in both the ID token and UserInfo, test precedence/semantics against the actual implementation whenever logic depends on which source wins.

### 7.3. UserInfo Differs from an OAuth Access Token

`OidcUserInfo` is claims data. It is not an access token and cannot be sent as a Bearer header.

### 7.4. Test the UserInfo HTTP Flow Elsewhere

To be certain the app handles 401/500 responses from the UserInfo endpoint, write an authentication integration test with a mocked OP/UserInfo HTTP endpoint.

## 8. `authorities(...)`: Granting the Principal Specific Authorities

Example `SecurityFilterChain`:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
~~~

In a test:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_ADMIN"))))
        .andExpect(status().isOk());
~~~

### 8.1. Negative Test

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_VIEWER"))))
        .andExpect(status().isForbidden());
~~~

### 8.2. `authorities(...)` Does Not Run Custom Mappers

If production mapping is:

~~~text
OIDC groups=[finance-admins]
  -> GrantedAuthoritiesMapper
  -> ROLE_FINANCE_ADMIN
~~~

then:

~~~java
.with(oidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_FINANCE_ADMIN")))
~~~

only states that the user **already has** the authority. The test does not prove the mapper from OP groups works properly.

### 8.3. Distinguishing Roles and Scopes

~~~text
ROLE_ADMIN
ROLE_VIEWER
SCOPE_orders.read
SCOPE_orders.write
~~~

`hasRole("ADMIN")` typically checks `ROLE_ADMIN`; `hasAuthority("SCOPE_orders.read")` checks the exact authority string.

A mock OIDC principal with `SCOPE_orders.read` does not itself prove the Orders API accepts a real access token.

### 8.4. Test Both Sufficient and Insufficient Permissions

Never create every fake user with `ROLE_ADMIN` by default. If every test gets broad permissions, authorization regressions are easily missed.

## 9. Passing a Custom `OidcUser` with `oidcUser(...)`

When you need synchronized token, UserInfo, and authorities or a custom principal implementation, construct `OidcUser` yourself.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

final class OidcTestUsers {

    private OidcTestUsers() {}

    static OidcUser alice() {
        Instant now =
                Instant.parse("2026-11-16T09:00:00Z");

        OidcIdToken idToken = new OidcIdToken(
                "fake-id-token",
                now,
                now.plusSeconds(3600),
                Map.of(
                        "iss", "https://login.test.example",
                        "sub", "alice-123",
                        "aud", List.of("portal-web")));

        OidcUserInfo userInfo = new OidcUserInfo(
                Map.of(
                        "sub", "alice-123",
                        "email", "alice@example.test"));

        return new DefaultOidcUser(
                List.of(new SimpleGrantedAuthority("ROLE_USER")),
                idToken,
                userInfo,
                "sub");
    }
}
~~~

Using in MockMvc:

~~~java
mvc.perform(get("/me")
                .with(oidcLogin()
                        .oidcUser(OidcTestUsers.alice())))
        .andExpect(status().isOk());
~~~

### 9.1. When Is This Approach Appropriate?

- You have a custom OIDC user wrapper.
- Both UserInfo and ID token claims need to be combined.
- You are testing the principal name attribute.
- You need a complex fixture reused in multiple places.
- You want to verify how the controller handles specific authorities.

### 9.2. Never Use Real Tokens

`fake-id-token` is a dummy value. Never copy production ID tokens/access tokens into test sources.

### 9.3. Expiry in a Fixture Does Not Prove Validation

`oidcLogin()` does not cryptographically validate tokens, so an ID token object with a past expiry can still be placed into `Authentication`. Test real expiry checks at the OIDC authentication/JWT decoder boundary.

## 10. Testing Multiple `ClientRegistration` Configurations

An application may support:

~~~text
corporate-login
partner-login
~~~

and a controller reads:

~~~java
authentication.getAuthorizedClientRegistrationId()
~~~

When you want to test a specific registration explicitly, use `clientRegistration(...)`.

### 10.1. Registration Fixture

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

final class OidcTestRegistrations {

    private OidcTestRegistrations() {}

    static ClientRegistration corporate() {
        return ClientRegistration
                .withRegistrationId("corporate-login")
                .clientId("portal-test-client")
                .clientSecret("test-only-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri(
                        "https://login.test.example/authorize")
                .tokenUri(
                        "https://login.test.example/token")
                .jwkSetUri(
                        "https://login.test.example/jwks")
                .issuerUri("https://login.test.example")
                .scope("openid", "profile")
                .clientName("Corporate Test")
                .build();
    }
}
~~~

All URLs here are fixtures and must never be used to call a production OP.

### 10.2. Attaching the Registration

~~~java
mvc.perform(get("/me/provider")
                .with(oidcLogin()
                        .clientRegistration(
                                OidcTestRegistrations.corporate())))
        .andExpect(status().isOk());
~~~

### 10.3. Do Not Treat `clientRegistration` as Verified Identity

`clientRegistration(...)` tells the test which registration is being simulated. It does not cause Spring Security to check the simulated ID token's issuer against the registration's issuer.

### 10.4. Two Registrations Sharing the Same Issuer

Two OAuth clients can share a single issuer while having different client IDs or scopes. Tests must specify the exact registration ID when logic depends on registration.

## 11. Reading `OAuth2AuthenticationToken`

Controller:

~~~java
import org.springframework.security.oauth2.client.authentication
        .OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProviderController {

    @GetMapping("/me/provider")
    ProviderInfo provider(
            OAuth2AuthenticationToken authentication) {

        return new ProviderInfo(
                authentication.getAuthorizedClientRegistrationId(),
                authentication.getName());
    }

    record ProviderInfo(
            String registrationId,
            String principalName) {}
}
~~~

Test:

~~~java
mvc.perform(get("/me/provider")
                .with(oidcLogin()
                        .clientRegistration(
                                OidcTestRegistrations.corporate())
                        .idToken(token -> token
                                .claim("sub", "alice-123"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
                .value("corporate-login"));
~~~

### 11.1. Registration Is Not a Role

`registrationId=corporate-login` does not automatically grant `ROLE_ADMIN`. User authentication and domain authorization are two separate layers.

### 11.2. Subject Is Not Email

`authentication.getName()` may be the subject or a configured principal name attribute. Do not assume it is an email address.

### 11.3. Never Take Registration from Arbitrary Query Parameters

Production code must read the registration from the `OAuth2AuthenticationToken` built by Spring Security, never trusting `?registrationId=...` as proof of successful login.

## 12. Testing Allowed and Denied Endpoints

Suppose:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/me").authenticated()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll())
~~~

### 12.1. Authenticated User Accessing `/me`

~~~java
mvc.perform(get("/me").with(oidcLogin()))
        .andExpect(status().isOk());
~~~

### 12.2. Admin Allowed

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_ADMIN"))))
        .andExpect(status().isOk());
~~~

### 12.3. Viewer Denied

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_VIEWER"))))
        .andExpect(status().isForbidden());
~~~

### 12.4. Anonymous Request

~~~java
mvc.perform(get("/admin/dashboard"))
        .andExpect(result -> {
            int status = result.getResponse().getStatus();
            org.assertj.core.api.Assertions.assertThat(status)
                    .isIn(302, 401);
        });
~~~

The anonymous snippet is illustrative because browser apps usually redirect to login whereas bearer-only APIs usually return 401. **Real tests should assert the exact status/`Location` matching your project's `SecurityFilterChain`**, rather than keeping a loose assertion as in the example.

### 12.5. Unknown Endpoints

If `anyRequest().denyAll()` is configured, test a mapped route that is not on the allowlist. Do not confuse a 404 from MVC having no handler with a 403 from security authorization.

## 13. Method Security and `@PreAuthorize`

Example service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportsService {

    @PreAuthorize(
            "hasAuthority('ROLE_REPORT_READER')")
    public String report() {
        return "report-ok";
    }
}
~~~

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsService service;

    public ReportsController(ReportsService service) {
        this.service = service;
    }

    @GetMapping("/reports")
    String report() {
        return service.report();
    }
}
~~~

### 13.1. Allowed

~~~java
mvc.perform(get("/reports")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "ROLE_REPORT_READER"))))
        .andExpect(status().isOk());
~~~

### 13.2. Denied

~~~java
mvc.perform(get("/reports")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_USER"))))
        .andExpect(status().isForbidden());
~~~

### 13.3. Method Security Must Be Enabled

`@EnableMethodSecurity` must be active in the test context. If you use `@WebMvcTest` and mock `ReportsService`, the method interceptor on the real service may not execute.

**A 200 response when calling a mocked service does not prove the service's `@PreAuthorize` was enforced.**

### 13.4. Test at the Right Layer

- Controller security rules: MockMvc with `SecurityFilterChain`.
- Service method security: context containing the real proxied service.
- Business authorization: service/domain tests with specific identities and roles.

## 14. Claims Do Not Automatically Become Authorities

Production may map:

~~~text
ID token/UserInfo:
  groups=["finance-admins"]

Custom GrantedAuthoritiesMapper:
  finance-admins -> ROLE_FINANCE_ADMIN
~~~

If a test writes:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("groups",
                        java.util.List.of("finance-admins"))))
~~~

do not expect Spring Security Test to automatically run the entire custom OIDC user loading/`GrantedAuthoritiesMapper` pipeline.

### 14.1. Test Mapping Separately

Verify the real mapping component:

~~~text
Input: validated OIDC claims, issuer
Mapping: finance-admins -> ROLE_FINANCE_ADMIN
Output: granted ROLE_FINANCE_ADMIN
~~~

### 14.2. Test Endpoints Separately

~~~java
.with(oidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_FINANCE_ADMIN")))
~~~

This tests endpoint authorization **post-mapping**.

### 14.3. Integration Tests Are Required to Verify OP-to-Role End-to-End

Mock OP ID token/UserInfo per issuer-specific policy, run the OIDC authentication flow, and assert the real `SecurityContext` authorities after login.

### 14.4. Risk of False-Green Tests

If every test assigns `ROLE_ADMIN`, role-mapping logic could be broken while endpoint tests remain green. Keep test scopes distinct.

## 15. CSRF When Testing POST/PUT/DELETE

A portal using browser cookies has a different CSRF threat model than a bearer-only API. OIDC authentication does not disable CSRF protection.

### 15.1. Authenticated POST Without a CSRF Token

~~~java
mvc.perform(post("/profile/update")
                .with(oidcLogin())
                .contentType("application/json")
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
~~~

Assumes the endpoint exists and `SecurityFilterChain` enables CSRF.

### 15.2. POST with a Valid CSRF Token

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/profile/update")
                .with(oidcLogin())
                .with(csrf())
                .contentType("application/json")
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isOk());
~~~

A `200` result assumes controller, validation, and domain policy all permit the update.

### 15.3. Never Remove CSRF to Silence 403s

If a POST fails, check:

1. Is OIDC Authentication present?
2. Are authorities sufficient?
3. Is a CSRF token included?
4. Is the endpoint failing validation or business denial?
5. Is the right `SecurityFilterChain` matched?

### 15.4. OAuth `state` Does Not Replace the App's CSRF Token

`state` binds the callback within the OAuth flow. It does not replace CSRF protection for every POST using session cookies.

## 16. Request-Scoped Authentication and Sessions

`with(oidcLogin())` creates Authentication for **that specific MockMvc request**.

~~~java
mvc.perform(get("/me").with(oidcLogin()));
mvc.perform(get("/me")); // Not logged in by default
~~~

### 16.1. Testing Two Requests with a Session

If you need to simulate a browser retaining a session across multiple requests, use `MockHttpSession` and the `SecurityContext` persistence mechanism matching your app.

Do not treat the post-processor as an automatic test of the entire session lifecycle.

### 16.2. Testing Logout and Session Fixation

Logout, session invalidation, session fixation protection, and SSO cookie behavior require tests at the right flow/session layer.

### 16.3. Testing Unauthorized Requests

Send requests without `oidcLogin()` and verify the browser login redirect or 401 according to contract.

### 16.4. Do Not Attach an Authenticated User to the Entire Test Suite

If default request customization always adds `oidcLogin()`, anonymous tests lose their meaning.

## 17. Helpers for Multiple Test Users

Fixture:

~~~java
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;

final class OidcTestRequests {

    private OidcTestRequests() {}

    static RequestPostProcessor loginAs(String subject) {
        return oidcLogin()
                .idToken(token -> token.claim("sub", subject));
    }
}
~~~

Usage:

~~~java
mvc.perform(get("/me")
                .with(OidcTestRequests.loginAs("alice-123")))
        .andExpect(status().isOk());

mvc.perform(get("/me")
                .with(OidcTestRequests.loginAs("bob-456")))
        .andExpect(status().isOk());
~~~

### 17.1. Each User Needs a Distinct Identity

Never reuse a single default mock ID token to test ownership between Alice and Bob without changing `sub`.

### 17.2. Multiple Issuers

If different OPs both issue `sub=user-123`, the application must distinguish identities by `iss` + `sub` or an internal user mapping.

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("iss", "https://partner.test.example")
                .claim("sub", "user-123")))
~~~

This is still only fake identity claims, not issuer validation.

### 17.3. Never Use Email as the Sole Identity

Emails can change or be unverified. Identity/ownership tests should rely on the system's stable identity key.

## 18. Tenant Membership and Object Ownership

A user can have a valid OIDC login yet not belong to the requested tenant.

Example:

~~~text
OIDC principal:
  issuer = company-op
  sub = alice-123

Membership:
  alice-123 belongs to Acme
  alice-123 does not belong to Globex
~~~

### 18.1. Essential Test Cases

| Case | Outcome |
|---|---|
| Alice belongs to Acme, accesses Acme | Allow if authorized |
| Alice belongs to Acme, accesses Globex | Deny |
| Alice's membership was revoked | Deny |
| Alice requests Bob's order | Deny |
| Two issuers share the same `sub` | Do not auto-merge |
| Token claims `tid=globex` but membership forbids it | Deny |

### 18.2. Use a Real Domain Service or a Meaningful Mock

If the controller calls a mocked service that returns 200 for any principal, the test does not prove tenant/owner authorization.

When testing ownership policies, use the real service or a stub configured to enforce ownership rules.

### 18.3. Do Not Equate OIDC Login with Domain Permission

`oidcLogin()` only makes the request authenticated. It does not determine which orders Alice is allowed to view.

### 18.4. Accept 403 or 404 Per Contract

Some APIs return 404 instead of 403 to avoid disclosing resource existence. Tests should reflect the exact policy and ensure unauthorized data is never returned.

## 19. `@AuthenticationPrincipal` and `Authentication`

Controllers can read the principal in several ways.

### 19.1. `@AuthenticationPrincipal OidcUser`

~~~java
@GetMapping("/me/subject")
String subject(@AuthenticationPrincipal OidcUser user) {
    return user.getIdToken().getSubject();
}
~~~

Test with `oidcLogin().idToken(...)`.

### 19.2. `Authentication`

~~~java
@GetMapping("/me/name")
String name(Authentication authentication) {
    return authentication.getName();
}
~~~

`getName()` is not email by default. It depends on the principal name attribute, typically `sub` in OIDC.

### 19.3. `OAuth2AuthenticationToken`

~~~java
@GetMapping("/me/registration")
String registration(OAuth2AuthenticationToken auth) {
    return auth.getAuthorizedClientRegistrationId();
}
~~~

Test with `oidcLogin().clientRegistration(...)`.

### 19.4. `SecurityContextHolder`

Inside the Servlet security filter chain, `SecurityContext` holds `Authentication` on the request thread. `oidcLogin()` lets you test controllers/services reading this context.

Never store `Authentication` in static/singleton fields where user A's session could affect user B.

## 20. `oidcLogin()` and `OAuth2AuthorizedClient`

Production OIDC Login can produce:

~~~text
OAuth2AuthenticationToken:
  User authenticated at the Portal.

OAuth2AuthorizedClient:
  ClientRegistration + access token + refresh token (if issued).
~~~

### 20.1. Controller Only Needs `OidcUser`

`oidcLogin()` is a great fit.

### 20.2. Controller Uses `@RegisteredOAuth2AuthorizedClient`

If an endpoint needs an access token to call downstream APIs, tests must also verify:

- Authorized client test setup.
- Repository/service/manager configuration.
- Token value attached to the right outbound API request.
- Never using an ID token or refresh token as a Bearer access token.
- 401/403 and refresh handling.

The `oidcLogin()` helper does not replace these outbound OAuth2 Client tests.

### 20.3. Test Authorized Clients Separately

Use token fixtures and a mocked HTTP client/token endpoint when needed. A mock principal with a valid `sub` claim does not guarantee an access token was issued with the right audience.

### 20.4. Do Not Test Refresh via `oidcLogin()`

Refresh token grants, rotation, persisting new refresh tokens, and concurrency require component/integration tests with an authorized-client manager and a fake AS token endpoint.

## 21. Comparing Spring Security Test Helpers

| Helper | Simulated authentication | Used for |
|---|---|---|
| `oidcLogin()` | OIDC Login, `OidcUser` | Portal/RP after OIDC Login |
| `oauth2Login()` | OAuth2 Login, `OAuth2User` | OAuth2-only provider or non-OIDC principal |
| `jwt()` | Bearer JWT Authentication | Resource Server JWT API |
| `opaqueToken()` | Opaque Bearer Authentication | Resource Server opaque API |
| `user("alice")` | Username/password Authentication | Form-login style tests |
| `@WithMockUser` | Mock user SecurityContext | Role checks not needing OIDC claims |
| `authentication(...)` | Custom Authentication | Custom auth scenarios |

### 21.1. `oidcLogin()` vs. `oauth2Login()`

When a controller calls `OidcUser.getIdToken()`, use `oidcLogin()`.

If an OAuth2-only Login app relies on UserInfo without an ID token, `oauth2Login()` simulating `OAuth2User` is more appropriate.

### 21.2. `oidcLogin()` vs. `jwt()`

`oidcLogin()` is a **browser login principal on an OAuth2/OIDC Client**.

`jwt()` is **incoming Bearer Authentication on a Resource Server**.

Never use `oidcLogin()` to claim an API verified a JWT access token.

### 21.3. `@WithMockUser`

`@WithMockUser` is quick for simple authorization rules, but it does not create an OIDC ID token, UserInfo, or registration ID by default.

### 21.4. `jwt()` Also Skips Real Signature Validation

`jwt()` lets you test Resource Server authorization after a JWT is simulated as authenticated. Testing signatures/issuers/audiences requires real decoder/integration tests.

## 22. Resource Server Test Example Using `jwt()`

If the Orders API is protected with:

~~~java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
~~~

tests can use:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders")
                .with(jwt()
                        .jwt(token -> token
                                .claim("sub", "alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders.read"))))
        .andExpect(status().isOk());
~~~

### 22.1. Two Different `SecurityContext`s

~~~text
Portal OIDC Client:
  OAuth2AuthenticationToken
  principal = OidcUser

Orders API Resource Server:
  JwtAuthenticationToken
  principal = Jwt
~~~

### 22.2. Access Token Audience

`jwt()` in a test does not prove the production `JwtDecoder` rejects a token with `aud=billing-api`. Test the decoder/integration separately to verify audience validation.

### 22.3. Never Send an ID Token to an API

ID tokens are meant for the Relying Party; a Resource Server requires a valid OAuth access token matching its audience/scope/API contract.

## 23. Limits of `oidcLogin()` to Keep in Mind

| What you want to verify | Is `oidcLogin()` enough? | Recommendation |
|---|---|---|
| Controller reads `OidcUser` claims | Yes | MockMvc |
| Endpoint checks role/authority | Yes, if filters/method security run | MockMvc + authorities |
| Membership/ownership | Possibly, if domain logic runs | Domain integration |
| Custom role mapping in OIDC service | Does not run automatically | Test mapper/authentication pipeline |
| Authorization Request redirect URI | No | OAuth2 Login filter test |
| State correlation | No | Callback integration |
| PKCE challenge/verifier | No | Authorization Code integration |
| OIDC nonce | No | OIDC authentication integration |
| ID token signature/JWKS | No | OP/JWT validation test |
| Real issuer/audience validation | No | OIDC/JWT decoder integration |
| HTTP UserInfo request | No | Test user service + mock OP |
| Token refresh/save/rotation | No | Authorized client manager tests |
| RP-Initiated Logout | No | Logout protocol integration |
| Outbound API Authorization header | Not sufficient alone | HTTP client/token store test |

## 24. When Do You Need an OIDC Login Integration Test?

An application may have dozens of controller tests using `oidcLogin()` plus a handful of deeper tests for the login flow.

### 24.1. Redirect

Verify `/oauth2/authorization/{registrationId}` redirects to the right OP with `client_id`, `scope`, `redirect_uri`, and `state`.

### 24.2. Callback

Using the Authorization Request repository and a fake AS:

- Valid state matching the original request -> proceed.
- Missing/invalid/reused state -> reject.
- Invalid/reused code -> token endpoint error.
- Callback registration/issuer mismatch -> reject per validation.

### 24.3. ID Token Validation

Using test JWKS/OP:

- Invalid signature.
- Wrong issuer.
- Audience missing the matching client ID.
- Expired token.
- Nonce mismatch when applicable.
- Claims failing OIDC profile requirements.

### 24.4. UserInfo

Test the UserInfo endpoint returning 401/500, insufficient claims, or wrong user-name attribute mapping.

### 24.5. Token Lifecycle

Verify saving/refreshing/removing authorized clients, `invalid_grant`, logout, and rotation per AS policy.

**Never call the production OP to execute negative/security tests.** Use a mock server/test OP and fake credentials.

## 25. Building MockMvc Manually

When not using `@AutoConfigureMockMvc`, you can use:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

class ManualMockMvcTest {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }
}
~~~

The test class also needs the appropriate Spring Test context annotations to inject `WebApplicationContext`.

### 25.1. Why Does `springSecurity()` Matter?

It attaches `FilterChainProxy` and security context test integration to MockMvc. Omitting it can prevent requests from passing through the filter chain as in production.

### 25.2. `standaloneSetup(...)`

`MockMvcBuilders.standaloneSetup(controller)` does not load `SecurityFilterChain` from the application context. Only use it for pure MVC testing or when you have explicitly attached a proper security configuration.

### 25.3. Never Fix Errors by Disabling Filters

If a MockMvc test fails because a security bean is missing, provide the needed bean. Disabling filters to make tests pass renders security assertions worthless.

## 26. Organizing Fixtures to Avoid False Positives

A helper can build OIDC requests per principal:

~~~java
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;

final class OidcFixtures {

    private OidcFixtures() {}

    static RequestPostProcessor alice() {
        return oidcLogin()
                .idToken(token -> token
                        .claim("sub", "alice-123")
                        .claim("email", "alice@example.test"));
    }

    static RequestPostProcessor admin() {
        return oidcLogin()
                .idToken(token -> token
                        .claim("sub", "admin-123"))
                .authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN"));
    }
}
~~~

### 26.1. Name Fixtures by Use Case

Provide clear fixtures such as `viewer()`, `admin()`, `tenantMember()`, and `tenantNonMember()`.

### 26.2. Do Not Grant `ROLE_ADMIN` by Default

If every mock user is an admin, endpoint security tests only prove the happy path.

### 26.3. Never Use Production Tokens

ID tokens in tests must be synthetic data. Never copy real credentials from production environments.

### 26.4. Separate Role-Mapping Tests from Endpoint Rule Tests

A fixture with `ROLE_ADMIN` only tests the endpoint post-mapping; the role mapper from ID token claims must be tested separately.

## 27. Servlet Testing Matrix

| Category | Scenario | Expectation |
|---|---|---|
| Principal | `oidcLogin()` with subject Alice | Controller reads Alice |
| Claims | ID token contains email | Correct JSON response |
| UserInfo | Email from UserInfo | Principal getter works |
| Registration | `corporate-login` | Correct registration ID |
| Authorities | `ROLE_ADMIN` | Admin route allowed |
| Authorities | `ROLE_VIEWER` | Admin route denied |
| Anonymous | Without `oidcLogin()` | 302/401 per app |
| CSRF | POST with OIDC user missing CSRF | 403 |
| CSRF | POST + `csrf()` | Processed if authorized |
| Method security | Sufficient authority | Proxy allows |
| Method security | Insufficient authority | Proxy denies |
| Tenant | Alice belongs to Acme | Allowed on Acme resources |
| Tenant | Alice does not belong to Globex | Denied |
| Owner | Bob requests Alice's order | Denied |
| OIDC role mapping | Group -> role | Test real mapper |
| API JWT | `jwt()` and scope | API auth rules |
| Actual ID token | Invalid issuer/signature | Integration rejects |
| Authorization callback | Invalid state/nonce | Login integration rejects |
| Outbound token | Simulated access token | Correct header/host |
| Session | Two requests | Session state matches design |

## 28. Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| `oidcLogin()` not found | Missing `spring-security-test`/import | Add dependency/static import |
| `OidcUser` is null | MockMvc `SecurityContext` not integrated | Keep Spring Security filters enabled |
| GET 403 despite `oidcLogin()` | Missing authority or method policy | Inspect roles/rules |
| POST 403 | Missing CSRF or authority | Try `csrf()` and inspect rules |
| `groups` claim present but no `ROLE_ADMIN` | Claims do not auto-map to authorities | Test mapper separately |
| `ROLE_ADMIN` test passes while production mapping fails | Test directly assigned authority | Test OIDC authentication pipeline |
| Wrong registration ID | Using default registration | Use `clientRegistration(...)` |
| Controller misses custom `SecurityFilterChain` | `@WebMvcTest` slice | Import the needed security configuration |
| Context calls production OP | `issuer` discovery | Use test `ClientRegistration`/mock metadata |
| `@PreAuthorize` not enforced | Method security disabled or service mocked | Test real proxied service |
| Test returns 200 with invalid `state` | `oidcLogin()` bypasses flow | Test callback/filter integration |
| Wrong ID token issuer still accepted | Mock principal does not verify tokens | Test JWT/OIDC validation |
| API test uses `oidcLogin()` | Confusing Client with Resource Server | Use `jwt()`/`opaqueToken()` |
| Two requests lose auth | Post-processor is per-request | Use `MockHttpSession` properly |
| Email appears from wrong source | ID token/UserInfo does not match OP | Test source/claims |
| Browser redirects instead of 401 | Login entry point | Inspect `SecurityFilterChain` |
| Tokens logged | HTTP debug/test fixtures | Use fake tokens and redaction |

## 29. Common Misconceptions

**"`oidcLogin()` tests real OIDC Login."**

No. It simulates an already logged-in user for the request.

**"`oidcLogin()` verifies a valid ID token signature."**

No. Test-built claims never go through a real decoder.

**"Adding `groups=admins` gives the user `ROLE_ADMIN`."**

Not automatically. You need a custom role mapper when production implements that logic.

**"`oidcLogin()` makes `state`/PKCE/nonce tests pass."**

No. Callback steps need separate integration tests.

**"`@WithMockUser` is the same as `oidcLogin()`."**

No. A default `MockUser` lacks an `OidcUser`/ID token/registration.

**"`jwt()` and `oidcLogin()` are interchangeable."**

No. One helper is for a Resource Server JWT, the other for OIDC Client Login.

**"Once a user is logged in, POST requests do not need CSRF."**

No. Browser cookie-backed sessions still require CSRF protection.

**"`@WebMvcTest` always executes every `@PreAuthorize` on services."**

No. Services may not be loaded or may be mocked.

**"An `oidcLogin()` test proves access token refresh works."**

No. Refresh/token managers require separate tests.

**"An OIDC user with a valid subject can definitely view every order."**

No. Domain/tenant/owner authorization is still required.

## 30. Practice Scenarios

### A. Testing the `/me` Endpoint

The controller reads subject/email.

**Approach:** `oidcLogin().idToken(...)` and JSON assertions.

### B. Testing the Admin Role

Only `ROLE_ADMIN` may access `/admin`.

**Approach:** allowed test with `ROLE_ADMIN` and denied test with `ROLE_VIEWER`.

### C. Testing Claim Mapping

Production converts OIDC groups into authorities.

**Approach:** test the real mapper rather than just injecting `ROLE_ADMIN`.

### D. Testing Callback State Mismatch

Callback arrives with a nonexistent `state`.

**Approach:** test the OAuth2 Login filter with an Authorization Request repository and a fake OP; `oidcLogin()` does not check `state`.

### E. Testing ID Token Signature/Issuer

The OP returns an ID token with an invalid signature or wrong issuer.

**Approach:** OIDC authentication integration test with test JWKS/OP.

### F. Testing POST CSRF

An authenticated user sends an update without a CSRF token.

**Approach:** test 403 and the `csrf()` case according to session policy.

### G. Multiple OIDC Providers

The controller displays the current provider.

**Approach:** `oidcLogin().clientRegistration(...)` with a specific `ClientRegistration`.

### H. Tenant Isolation

Alice belongs only to Acme and requests Globex.

**Approach:** mock Alice's OIDC principal and test real membership/domain authorization.

### I. Outbound Bearer Token

The portal calls Orders API via `OAuth2AuthorizedClient`.

**Approach:** fake authorized client, mocked HTTP client, assert token/host/error handling. `oidcLogin()` alone is insufficient.

### J. Multi-Request Session

A second request needs the same principal/session.

**Approach:** explicitly simulate `MockHttpSession`/`SecurityContext` persistence.

## 31. Self-Check Questions

**1. Which dependency provides `oidcLogin()`?**

`spring-security-test`.

**2. What is the static import?**

`SecurityMockMvcRequestPostProcessors.oidcLogin`.

**3. Which principal does it simulate?**

`OidcUser` inside an OAuth2 Login Authentication.

**4. Does it call a real OpenID Provider?**

No.

**5. Does it verify the ID token signature?**

No.

**6. Which API modifies ID token claims?**

`idToken(token -> ...)`.

**7. Which API modifies UserInfo?**

`userInfoToken(info -> ...)`.

**8. Which API assigns authorities directly?**

`authorities(...)`.

**9. Can you inject a custom `OidcUser` into a request?**

Yes, using `oidcUser(...)`.

**10. How do you test a specific registration ID?**

`clientRegistration(...)` with a `ClientRegistration` fixture.

**11. Does a `groups` claim automatically become `ROLE_ADMIN`?**

Not by default.

**12. What is needed to test groups -> role mapping?**

Test the real `GrantedAuthoritiesMapper`/OIDC user loading logic.

**13. What does a session-cookie-based POST test need?**

`csrf()` when CSRF protection is enabled.

**14. How do you test anonymous access?**

Send a request without `oidcLogin()` and assert the app's entry point behavior.

**15. Does `oidcLogin()` retain Authentication across all subsequent requests?**

Not by default; it applies to that specific request.

**16. How should a Resource Server JWT API be tested?**

`jwt()` plus decoder/integration tests for real signature/issuer/audience validation.

**17. Why might `@WebMvcTest` fail to enforce `@PreAuthorize` on a service?**

The service is not loaded or is mocked, so the method security proxy may not run.

**18. Can PKCE/nonce/state be tested with `oidcLogin()`?**

No; login integration tests are required.

**19. Does an already-authenticated OIDC principal still need tenant/owner checks?**

Yes.

**20. What must outbound access token tests verify?**

Authorized client/token setup, `Authorization: Bearer` header, target host, and error handling.

## Key Takeaways

- **`oidcLogin()` is a Spring Security Test request post-processor for simulating an OIDC-logged-in user**, without running a real Authorization Code flow.
- **Use `spring-security-test`, MockMvc, and the Spring Security filter chain in the right context** to verify controller/security authorization.
- **`idToken(...)`, `userInfoToken(...)`, `authorities(...)`, `oidcUser(...)`, and `clientRegistration(...)`** make it easy to construct clear, repeatable OIDC principals.
- **OIDC claims and Spring `GrantedAuthorities` are two separate layers.** If production has a custom groups-to-role mapper, test the mapper separately.
- **`oidcLogin()` differs from `oauth2Login()`, `jwt()`, `opaqueToken()`, and `@WithMockUser`**; choose the helper matching the security boundary.
- **Test allowed, denied, anonymous, and CSRF cases**—never grant admin to every user or disable security filters just to make tests pass.
- **`oidcLogin()` does not verify real `state`, `nonce`, PKCE, callbacks, ID token signatures/issuers, or refresh tokens.** Those require integration tests with a mock/test OP.
- **Even after mock authentication, tenant membership and object ownership must still be enforced**; OIDC Login does not implicitly grant data access.
- **Test outbound `OAuth2AuthorizedClient` and token relay separately**, never treating an ID token as an API access token or exposing credentials in test logs.
