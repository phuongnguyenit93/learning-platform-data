# isAuthenticated Represents Internal State, Not a Replacement for Proof Verification

> **Topic:** Spring Security — Authentication → Identity Models. This lesson focuses on the exact meaning of `Authentication.isAuthenticated()`, how that value is produced in a trusted authentication flow, why `true` does not by itself prove a person or token is genuine, and how Spring Security handles anonymous, remember-me, and authorization. The complete example uses Java 17+, Spring Boot 3.3.x, and Spring Security 6.x (Servlet).

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `isAuthenticated()` as **state recorded on the `Authentication` object**; identify who is authorized to produce trusted state and why a boolean is not cryptographic proof.
2. Distinguish **unverified credentials**, **verified credentials**, **`Authentication` stored in `SecurityContext`**, and **granted access permissions**.
3. Understand the case where `AnonymousAuthenticationToken.isAuthenticated() == true` yet the `authenticated()` rule still rejects anonymous access.
4. Distinguish `authenticated()`, `fullyAuthenticated()`, and `hasAuthority(...)`, and why remember-me does not equal full authentication under framework conventions.
5. Avoid constructing an "authenticated" `Authentication` directly from HTTP input, unverified JWTs, self-asserted headers, or mock test results.
6. Build and test a Spring Security application illustrating the difference among the internal flag, trust levels, and access permissions.

## 2. Core Question: What Does That Boolean Actually Say?

In Spring Security, `Authentication` represents both an **authentication request** (before proof verification) and an **authentication result** (after processing by a trusted mechanism). The interface defines:

~~~java
boolean isAuthenticated();
~~~

A `true` value normally means: **the application's authentication component has marked this object as a trusted result for the framework to use downstream**, saving later steps from repeating the full authentication process on every check. It is part of an internal contract between the component producing `Authentication` and the components consuming `Authentication`.

That value **does not by itself answer**:

- Did the user enter the right password, complete MFA, use a passkey, or verify through some other mechanism?
- Was a JWT checked for signature, `iss`, `aud`, `exp`, `nbf`, and resource server conditions?
- Is the account still active, the session still valid, or were permissions just revoked?
- Is the subject allowed to modify the exact resource/tenant being requested?
- Was the `Authentication` object produced by a trusted authentication filter/provider, or manually assembled by untrusted code?

**Rule:** `isAuthenticated()` reflects **an authentication outcome the system currently trusts**, not a tool that verifies proof on its own. If the source creating the result is untrusted, the flag can be wrong; re-checking that same flag cannot fix a flawed origin.

### Common Fields of Authentication

| Property/Method | Meaning | Must not be misread as |
| --- | --- | --- |
| `getPrincipal()` | Subject or data representing the subject; concrete type depends on mechanism | A principal named "admin" means a password was checked |
| `getCredentials()` | Proof supplied in the request or still held in the token | Having a password/token in the object means it is valid |
| `getAuthorities()` | `GrantedAuthority` instances placed into the result by the security mechanism | An authority grants access to all data without context checks |
| `isAuthenticated()` | Internal state of `Authentication` | `true` is cryptographic proof, MFA, or blanket permission |
| `getDetails()` | Supplemental info, typically request context | Details are automatically trustworthy if copied directly from the request |

In some implementations, credentials may be erased after successful authentication to limit leakage. Thus `getCredentials() == null` also **does not** prove authentication never took place.

## 3. Proper Authentication Flow: Proof First, State Second

Example of username/password login via Spring Security Servlet:

~~~mermaid
sequenceDiagram
    participant Client
    participant Filter as Authentication Filter
    participant Manager as AuthenticationManager
    participant Provider as AuthenticationProvider
    participant Store as User Store / PasswordEncoder
    participant Context as SecurityContext
    Client->>Filter: Send username + password over HTTPS
    Filter->>Manager: Unauthenticated Authentication
    Manager->>Provider: authenticate(request)
    Provider->>Store: Look up account + verify credential, policies
    alt Valid proof
        Store-->>Provider: Verification succeeded
        Provider-->>Manager: Trusted result Authentication
        Manager-->>Filter: Successful Authentication
        Filter->>Context: Store Authentication for further processing
    else Invalid proof
        Provider-->>Manager: AuthenticationException
        Manager-->>Filter: Failure
        Filter-->>Client: AuthenticationEntryPoint/failure handler
    end
~~~

**Before verification:** the request object can carry username and password yet has no basis for trust, so it normally holds `false`.

**After verification:** `AuthenticationManager` routes the request to an appropriate `AuthenticationProvider`. The provider checks proof and required conditions; on success, it returns an authenticated result object with authorities assigned from a trusted source. The filter mechanism places the result into `SecurityContext`. On failure, it throws `AuthenticationException` and never marks it successful.

**Illustrative integration snippet**, not a standalone program:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(username, password);

// authManager must be configured with a provider able to verify proof.
// authenticate(...) may throw AuthenticationException.
Authentication verified = authenticationManager.authenticate(request);

// Only the success path applies the result to SecurityContext.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

The snippet assumes `username`, `password`, and `authenticationManager` are wired inside a trusted authentication component. For standard web apps, let **Spring Security's standard filters and mechanisms** perform this work, including context management, sessions, and success/failure events. Never write a login controller that only checks a boolean.

**Distinguish proof sources:** passwords are checked via `PasswordEncoder.matches(...)` against a stored hash; JWT bearer access tokens need `JwtDecoder` and matching validators; opaque access tokens need introspection; mTLS needs certificate-chain validation and identity-mapping rules. `isAuthenticated()` does not perform any of those checks for any mechanism.

## 4. Why Does an Internal Flag Not Guarantee Security on Its Own?

Consider this conceptually flawed code:

~~~java
// WRONG ILLUSTRATION — do not put into application code!
Authentication trustedLooking =
        UsernamePasswordAuthenticationToken.authenticated(
                requestBody.username(),
                null,
                AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
~~~

If you build an object marked trusted **directly from caller-controlled `requestBody`**, the code skips proving account ownership and even invents `ROLE_ADMIN`. The `authenticated(...)` factory creates an object in the authenticated state; it **does not** verify passwords itself. This snippet is shown solely to recognize an anti-pattern, **not as a way to implement login**.

An `Authentication` object can be constructed by Java code. `SecurityContextHolder` also exposes an API to write to the context. If an untrusted layer is allowed to put an "authenticated" token into the context, the application can be misled. Some token implementations (such as `UsernamePasswordAuthenticationToken`) block calling `setAuthenticated(true)` directly; blocking that setter does not eliminate every way of creating a trusted token or prevent design flaws at the application layer. Therefore **the origin creating the object and the trust boundaries are what matter**.

Other flawed examples:

1. **Client sends `{"isAuthenticated": true}` in JSON.** This is purely caller-asserted data; the API must never treat it as an authentication result.
2. **Decoding a JWT and constructing `JwtAuthenticationToken` with authorities.** Base64-decoding a JWT payload does not check signature, issuer, audience, timestamps, or policy. Resource Server must verify the token before creating a trusted principal.
3. **Trusting an `X-Authenticated-User` header from the Internet.** A header can only be a pre-authentication source in a trusted proxy architecture that authenticates upstream, strips client-supplied headers, and blocks all paths bypassing the proxy.
4. **Saving `Authentication` in session/context and treating it as valid forever.** Session trust still depends on secure cookies, session store, timeouts, logout, account locks, authority revocation, and re-verification policies.
5. **Seeing `isAuthenticated() == true` and skipping authorization.** Authenticating a subject does not decide whether that subject may act on each report, invoice, or tenant.

The most useful audit question is: **Who verified the proof before this object was marked trusted, and what protects the path from the result to its point of use?**

## 5. Confusing Case: Anonymous Still Has an Authentication

When anonymous support is enabled (typically by default HTTP configuration), `AnonymousAuthenticationFilter` can insert an `AnonymousAuthenticationToken` into `SecurityContextHolder` if no user is logged in. The purpose is so filters, audits, and access mechanisms always have a principal representing a guest visitor.

**Notably:** `AnonymousAuthenticationToken.isAuthenticated()` can return **`true`**. This **does not** mean an anonymous user logged in with a password or has a verified human identity.

Spring Security does not rely solely on this raw value in the `authenticated()` rule. The framework uses `AuthenticationTrustResolver` to recognize anonymous and remember-me tokens, then determine the appropriate trust level.

### Comparing Three Ways to Read State

| Typical state | `auth.isAuthenticated()` | `trustResolver.isAuthenticated(auth)` | `trustResolver.isFullyAuthenticated(auth)` |
| --- | --- | --- | --- |
| No `Authentication` (`null`) | Cannot call directly | `false` | `false` |
| Newly created `UsernamePasswordAuthenticationToken.unauthenticated(...)` | `false` | `false` | `false` |
| `AnonymousAuthenticationToken` in standard config | `true` | `false` | `false` |
| `RememberMeAuthenticationToken` from trusted remember-me mechanism | `true` | `true` | `false` |
| Username/password token authenticated by provider | `true` | `true` | `true` |
| `JwtAuthenticationToken` created by Resource Server **after valid validation** | `true` | `true` | `true` by default classification |

The table describes **typical tokens created by standard Spring Security mechanisms**. If an application has custom tokens/custom trust resolvers, behavior depends on implementation; building a trusted token before verifying proof is already a bug.

- `Authentication.isAuthenticated()`: reads only **the flag on the object**.
- `AuthenticationTrustResolver.isAuthenticated(auth)`: checks that the object exists, the raw flag is true, and it is **not anonymous**.
- `AuthenticationTrustResolver.isFullyAuthenticated(auth)`: requires the level above and **not remember-me**.

**Fully authenticated does not mean a password was just entered, MFA was used, high-assurance identity proofing occurred, or admin rights exist.** It is simply the authentication-tier classification in Spring Security's anonymous/remember-me model. Requiring MFA or re-authentication for sensitive operations requires dedicated policies (such as checking `amr/acr/auth_time` claims from a verified issuer when applicable and a real step-up mechanism).

### Reading Anonymous Context Properly

In Spring MVC, a handler parameter of type `Authentication` typically comes through servlet `HttpServletRequest#getPrincipal()`, which can be **null when anonymous**, even while `SecurityContextHolder` holds an `AnonymousAuthenticationToken`. To inspect the actual context in the anonymous case, use `@CurrentSecurityContext` or `SecurityContextHolder`, then let `AuthenticationTrustResolver` classify it:

~~~java
@GetMapping("/state")
public Map<String, Object> state(@CurrentSecurityContext SecurityContext context) {
    Authentication authentication = context.getAuthentication();
    AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

    return Map.of(
            "rawFlag", authentication != null && authentication.isAuthenticated(),
            "recognizedAsAuthenticated", resolver.isAuthenticated(authentication),
            "fullyAuthenticated", resolver.isFullyAuthenticated(authentication));
}
~~~

This is an **integration method snippet** requiring Spring imports and a `@RestController` class; see the complete application example below. Use this status output only for appropriate learning/debugging, without exposing extra session details or credentials.

## 6. From Authentication to Authorization: Different Decision Gates

In Spring Security Servlet, the authentication mechanism establishes the principal; afterward `AuthorizationFilter` and/or method security enforce access policies. Common rules:

| Protection rule | Approximate meaning | Does it verify password/JWT itself? |
| --- | --- | --- |
| `permitAll()` | Public endpoint within the filter chain scope; no logged-in principal required | No |
| `authenticated()` | Requires a principal recognized by Spring Security as authenticated, **excluding anonymous** | No — relies on an existing authentication result |
| `fullyAuthenticated()` | Requires authenticated and **neither remember-me nor anonymous** | No — does not replace MFA |
| `hasAuthority("reports:read")` | Requires the exact authority supplied by a trusted mechanism | No — this is an authorization check |
| `hasRole("ADMIN")` | Under default prefix, checks `ROLE_ADMIN` | No — roles must come from a trusted source |
| Tenant/ownership check in service | Verifies the subject may act on **the specific record** | No — business authorization boundary |

With method security, `@PreAuthorize("isAuthenticated()")` is an authorization expression using framework semantics, not necessarily equivalent to a developer calling `auth.isAuthenticated()` directly. Likewise, `@PreAuthorize("isFullyAuthenticated()")` does not re-verify proof just sent at the HTTP layer.

**Do not confuse 401 and 403:**
- When a request lacks valid login proof, an endpoint requiring authentication usually returns **401** in HTTP Basic/Bearer APIs (or redirects to a login page in form-login web apps).
- When the identity is authenticated yet lacks permission, the response is usually **403**.
- Actual response codes depend on the entry point, filter chain, and application design.

Never use unverified permission data from the client to "upgrade" `Authentication`. Both principal and authorities must have clear provenance from a trusted authentication/authority-mapping process.

## 7. Runnable Demo App: Raw Flag, Anonymous, and Authorization Checks

This is a **standalone Spring Boot project** using Java 17, Gradle 8.x, and Spring Boot 3.3.5. It uses HTTP Basic and two accounts **for demo environments only**. Demo passwords are hashed with BCrypt at startup. Never use `InMemoryUserDetailsManager` or these static passwords in production.

Project structure:

~~~text
auth-flag-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authflag/
    │   ├── AuthFlagDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/authflag/
        └── AuthenticationBoundaryTest.java
~~~

### 7.1. Gradle Configuration

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-flag-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
~~~

### 7.2. Application Entry Point

`src/main/java/example/authflag/AuthFlagDemoApplication.java`:

~~~java
package example.authflag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFlagDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFlagDemoApplication.class, args);
    }
}
~~~

### 7.3. Authentication and Authorization Configuration

`src/main/java/example/authflag/SecurityConfig.java`:

~~~java
package example.authflag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/state").permitAll()
                .requestMatchers("/reports").hasAuthority("reports:read")
                .requestMatchers("/self").authenticated()
                .requestMatchers("/confirm").fullyAuthenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demoPass!"))
                .authorities("reports:read")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demoPass!"))
                .authorities("profile:read")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Explanation:** the HTTP Basic filter extracts credentials from the `Authorization` header and uses Spring Security's authentication mechanism. `PasswordEncoder` checks passwords against hashes. Both users are authenticated by the provider based on password and account status; authorities are assigned solely by server-side configuration.

The `authenticated()` rule on `/self` relies on the request's authentication result. The `hasAuthority("reports:read")` rule on `/reports` additionally requires the matching permission. `fullyAuthenticated()` on `/confirm` illustrates the authentication-tier classification; with standard HTTP Basic and no remember-me enabled, a valid Basic request falls under fully authenticated by this classification. It **does not** prove MFA.

### 7.4. Controller Exposing Only Study State

`src/main/java/example/authflag/DemoController.java`:

~~~java
package example.authflag;

import java.util.Map;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/state")
    public Map<String, Object> state(
            @CurrentSecurityContext SecurityContext context) {
        Authentication auth = context.getAuthentication();
        AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

        return Map.of(
                "kind", auth == null ? "none" : auth.getClass().getSimpleName(),
                "rawFlag", auth != null && auth.isAuthenticated(),
                "recognizedAsAuthenticated", resolver.isAuthenticated(auth),
                "fullyAuthenticated", resolver.isFullyAuthenticated(auth));
    }

    @GetMapping("/self")
    public String self(Authentication auth) {
        return auth.getName();
    }

    @GetMapping("/reports")
    public String reports() {
        return "REPORT_OK";
    }

    @GetMapping("/confirm")
    public String confirm() {
        return "NON_REMEMBER_ME";
    }
}
~~~

The `/state` branch has `permitAll()` so we can observe how the framework represents anonymous access. On an ordinary request without Basic credentials, `AnonymousAuthenticationFilter` places an `AnonymousAuthenticationToken` into the context. Thus you can get `rawFlag = true` while `recognizedAsAuthenticated = false`. That is precisely the distinction this lesson highlights.

### 7.5. Automated Testing with MockMvc

`src/test/java/example/authflag/AuthenticationBoundaryTest.java`:

~~~java
package example.authflag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousFlagIsTrueButNotAuthenticatedForAuthorization() throws Exception {
        mvc.perform(get("/state"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rawFlag").value(true))
                .andExpect(jsonPath("$.recognizedAsAuthenticated").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false));
    }

    @Test
    void anonymousCannotReadReports() throws Exception {
        mvc.perform(get("/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validUserWithoutPermissionIsForbidden() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("bob", "demoPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void validUserWithPermissionCanReadReports() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("alice", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT_OK"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/self").with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**What the tests actually verify:** requests travel through the application's HTTP Basic filter and provider; demo passwords are checked by the encoder; the controller inspects the context state after the filter. The first test proves **a `true` raw flag is not enough to satisfy `authenticated()`**. The remaining tests separate credential verification from permission requirements.

A test using `@WithMockUser` or attaching `Authentication` directly via a test helper **does not test the real password-verification path**; it is useful for testing authorization rules at a separate layer, yet does not replace end-to-end or integration tests for authentication filters/providers/decoders.

### 7.6. Run and Expected Results

From the project directory, with JDK 17+ and Gradle installed or a matching Gradle Wrapper:

~~~bash
gradle test
gradle bootRun
~~~

If the project includes a Gradle Wrapper, use `./gradlew test` and `./gradlew bootRun` (Windows PowerShell can use `.\gradlew.bat test` and `.\gradlew.bat bootRun`).

In another terminal, execute:

~~~bash
curl -i http://localhost:8080/state
curl -i http://localhost:8080/reports
curl -i -u "bob:demoPass!" http://localhost:8080/reports
curl -i -u "alice:demoPass!" http://localhost:8080/reports
curl -i -u "alice:wrong-password" http://localhost:8080/self
curl -i -u "alice:demoPass!" http://localhost:8080/state
~~~

Expectations for **logic and HTTP status** (headers and JSON field order are not fixed):

| Command/scenario | Expected |
| --- | --- |
| `/state` without credentials | HTTP 200, `kind` is `AnonymousAuthenticationToken`; `rawFlag=true`, `recognizedAsAuthenticated=false`, `fullyAuthenticated=false` |
| `/reports` without credentials | HTTP 401 with Basic configuration |
| `/reports`, Bob with valid password | HTTP 403 because Bob lacks `reports:read` |
| `/reports`, Alice with valid password | HTTP 200, body `REPORT_OK` |
| `/self`, Alice with wrong password | HTTP 401 |
| `/state`, Alice with valid password | HTTP 200, authenticated token; all three booleans typically `true` |

No endpoint needs to manually touch `isAuthenticated` to achieve these results: filters/providers perform authentication, while authorization rules enforce permissions. That separation is intentional.

## 8. Comparing with JWT Resource Server and Session-Based Login

The demo app uses HTTP Basic, yet the lesson applies equally to bearer tokens and web logins.

### 8.1. An Unverified JWT Is Not a Trusted Authentication

A JWT typically has a header, payload, and signature encoded for transport. Splitting the token on dots and decoding the payload **only reads claims**: an attacker can embed self-invented `sub`, `roles`, or `scope` values.

With Spring Security's OAuth2 Resource Server, configure a JWT decoder based on a trusted issuer/JWK and appropriate validator policies. Before accepting a token as valid, verify signature (with the right asymmetric/symmetric key), issuer, timestamps, and audience intended for the API. **Illustrative config example, requires a real IdP**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          audiences: https://api.example.test
~~~

When using JWT Resource Server, add `spring-boot-starter-oauth2-resource-server` and configure `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` appropriately. `JwtAuthenticationProvider` works with the decoder and builds an `Authentication` from the **verified token**. Mapping `scope` to `SCOPE_...` authorities by default is a post-validation conversion step; never assign authorities directly from raw requests.

Do not mechanically combine this illustrative JWT configuration with the HTTP Basic demo into a production setup. When an API supports multiple mechanisms, each filter chain/endpoint needs clear boundaries and policies.

### 8.2. Web Sessions Preserve Post-Authentication Results

In apps using form login or OIDC, the user may have proven credentials in a **prior login request**. `SecurityContextRepository` / session stores the appropriate result to restore `Authentication` on later requests; passwords do not have to be re-entered on every request. `isAuthenticated=true` here is **state preserved by a trusted session mechanism**.

Still, session trustworthiness depends on secure cookies, session fixation protection, timeouts, logout, authority changes, and proper session invalidation. Once a token/session expires under policy, the system must deny access or require re-authentication; it cannot rely on the `true` flag forever.

### 8.3. Remember-Me, MFA, and Step-Up

Remember-me can permit automatic re-login via a cookie under configured mechanisms. The framework separates remember-me from fully authenticated; yet `fullyAuthenticated()` **does not mean** "entered a password within the last 5 minutes", nor does it prove MFA assurance.

If money transfers, changing recovery methods, or modifying admin roles requires step-up, design dedicated controls: verify authentication method/time claims from a trusted issuer when applicable, force a fresh login flow when needed, or validate a verifiable challenge. Never equate `isAuthenticated=true` with `mfa=true`.

## 9. Handling Discrepancies and Protecting Trust Boundaries

### 9.1. Client Data and Context Are Not the Same Thing

The HTTP layer receives untrusted input: username, password, bearer token, cookie, headers, JSON body, query parameters. The authentication layer's job is to **verify or reject** those inputs. The application layer may consume an `Authentication` result only when that result was built along a trusted path.

Never copy client-sent `authenticated`, `isAdmin`, or `authorities` values directly into `Authentication`. For custom `AuthenticationProvider`s, result tokens should clearly separate before/after state, minimize mutable fields, and prevent callers from marking unverified proof as trusted.

### 9.2. Locked Accounts, Authority Changes, and Stale Data

A token with a `true` raw flag does not imply re-checking account status on every request. With active sessions or issued self-contained JWTs, account locking or role changes may require session invalidation, short token lifetimes, revocation, introspection, event push mechanisms, or live policy checks at the resource server. The choice depends on security requirements and acceptable latency.

### 9.3. Record-Level and Tenant Authorization

Suppose Alice holds `reports:read` yet is allowed to view reports only within organization A. The `hasAuthority("reports:read")` rule checks only one permission signal; the service must still verify that **the subject belongs to tenant A and is permitted to read that specific report ID**. `isAuthenticated()` holds no data proving this.

### 9.4. Asynchronous Work and Other Threads

`SecurityContextHolder` by default uses a per-thread strategy. Never assume an authentication object stays intact or propagates automatically to an executor, scheduler, or asynchronous callback. Use Spring Security's `SecurityContext` propagation utilities when genuinely needed, manage context lifecycle, and avoid accidentally carrying a user's identity into background jobs. Background jobs normally need their own service identity.

## 10. Anti-Patterns and How to Fix Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| `if (auth != null && auth.isAuthenticated())` used as **the entire** policy | Anonymous tokens can have raw flag true; misses scope and tenant checks | Use Spring Security authorization managers and resource policies |
| Controller reads `isAuthenticated` from request body | Attacker asserts true themselves | Let filters/providers build results from verified credentials |
| Calling `UsernamePasswordAuthenticationToken.authenticated(...)` from client username | Legitimizes identity/authorities without proof | Build an unauthenticated request and call `AuthenticationManager` |
| Manually decoding JWT and attaching `JwtAuthenticationToken` | Trusts forged, wrong-issuer/audience, or expired tokens | Use Resource Server `JwtDecoder` and validators |
| Treating `fullyAuthenticated()` as MFA or recent auth | Allows risky actions without sufficient assurance | Dedicated step-up policy with explicit verification |
| Treating remember-me and anonymous the same as normal login sessions | Misjudges trust level | Use `AuthenticationTrustResolver` and matching rules |
| `hasRole("ADMIN")` on client-submitted authorities | Fake authorization | Grant authorities via verified backend/issuer mapping |
| Every endpoint uses only `authenticated()` | Any logged-in user can reach data they do not own | Combine authorities with ownership/tenant checks |
| Testing `@WithMockUser` and concluding password/JWT validation is safe | Misses bugs in auth filters/providers/decoders | Add integration tests for real credential paths |
| Logging raw tokens or passwords to debug the flag | Credential leakage | Log only decision status, token type, and safe reason codes |

## 11. Self-Check Exercises

**Exercise 1.** A public endpoint prints `auth.isAuthenticated() == true` even though the user has not logged in. Is authentication definitely bypassed?

**Answer:** Not enough to conclude that. If the object is an `AnonymousAuthenticationToken`, the raw flag can be true under how Spring Security represents anonymous access. Check `AuthenticationTrustResolver.isAnonymous(auth)`, `isAuthenticated(auth)`, and the endpoint's protection rules. If a protected endpoint allows anonymous access, that is a policy bug to fix.

**Exercise 2.** An endpoint only calls `if (authentication.isAuthenticated())` and then lets the caller delete a report. Where is the flaw?

**Answer:** This check can both misclassify anonymous users and skip verifying authorities, subject, tenant, or report ownership. You need proper authentication policy and deletion permission checks on the target resource, never treating a boolean as sufficient proof.

**Exercise 3.** A developer builds `UsernamePasswordAuthenticationToken.authenticated("admin", null, ROLE_ADMIN)` after receiving JSON `{"name":"admin"}`. Why is this dangerous?

**Answer:** The developer fabricated a trusted result and authority directly from client data without going through `AuthenticationManager`/`AuthenticationProvider` and credential verification. The fact that a constructor/factory can instantiate the object does not prove the sender is admin.

**Exercise 4.** An external JWT contains claims `{"sub":"alice","scope":"admin"}` and code decoded it successfully. Can we set `isAuthenticated=true` and grant admin access?

**Answer:** No. You must verify signature, issuer, audience, expiration, and required policies, then map claims to authorities under resource server rules. Decoding merely reads the payload.

**Exercise 5.** Bob entered the right password so `isAuthenticated=true`; why does `/reports` return 403?

**Answer:** Successful authentication does not automatically grant `reports:read`. Bob only has `profile:read` in the demo, so authorization blocks the request despite valid credentials.

**Exercise 6.** A remember-me session has `isAuthenticated=true` yet is blocked from an endpoint requiring `fullyAuthenticated()`. Does this make sense?

**Answer:** Yes. Spring Security distinguishes remember-me from fully authenticated via the trust resolver. If an app requires MFA or recent re-authentication, define a higher-assurance policy beyond this classification.

## 12. Summary and Checklist

Read `isAuthenticated` in strict causal order:

1. **Proof:** what credential/token/session did the request present?
2. **Verification:** which filter, provider, decoder, or session mechanism verified that proof?
3. **Internal result:** what trusted `Authentication` was produced and stored in `SecurityContext`?
4. **Classification:** is the token anonymous, remember-me, or recognized as authenticated/fully authenticated?
5. **Authorization:** does the subject genuinely hold the authority, policy, and access to the right resource/tenant?

**Key takeaway:** `Authentication.isAuthenticated()` is **a status flag inside a security object**. Real proof must be verified **before** the system grants trusted state, and access permissions must be decided **afterward** for the specific action and resource. Never "verify" by reading back a boolean that the client or untrusted code could have set.

### Official Sources for Reference

- Spring Security 6.5 — `Authentication` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html
- Spring Security — HTTP Request Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture and `AuthenticatedAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security — Remember-Me: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
