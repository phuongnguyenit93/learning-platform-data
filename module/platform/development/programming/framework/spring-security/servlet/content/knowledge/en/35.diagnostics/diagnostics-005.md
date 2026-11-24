# `ProviderNotFoundException`, `BadCredentialsException`, and Account Status Errors

## 1. Learning Objectives and Spring Security Servlet Context

When protecting an API or web application with **Spring Security on the Servlet stack**, login-related failures commonly surface as an `AuthenticationException`. Two frequently confused exceptions are:

- **`ProviderNotFoundException`**: `AuthenticationManager` could not find an `AuthenticationProvider` that successfully handles **the incoming `Authentication` type**; this is usually a missing or miswired provider, not proof that the user entered the wrong password.
- **`BadCredentialsException`**: a provider accepted the authentication attempt but judged the credentials invalid. With `DaoAuthenticationProvider`, this usually means a wrong password; by default, non-existent usernames are also masked behind this exception.
- **Account status errors**: such as `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException`. An account can have a valid username/password yet still be denied due to account lifecycle policy.

This guide analyzes root causes, the `AuthenticationManager`/`AuthenticationProvider` lifecycle, interpreting HTTP `401`/`403` outcomes, safe log diagnostics, and testing with Java 17+ and Spring Boot 3.3.x / Spring Security 6.x. The diagnostic checks here are meant for **internal system analysis**, not for exposing user existence or detailed account status to external callers.

## 2. HTTP Basic Authentication Flow in a Servlet Application

Simplified flow:

```text
HTTP request
  Authorization: Basic ...
           |
           v
SecurityFilterChain
           |
           v
BasicAuthenticationFilter
  creates unauthenticated UsernamePasswordAuthenticationToken
           |
           v
AuthenticationManager (usually ProviderManager)
           |
           +-- Provider A: supports(token type)?
           |       no -> skip
           |
           +-- Provider B (e.g., DaoAuthenticationProvider)
           |       supports UsernamePasswordAuthenticationToken
           |       |
           |       +-- load UserDetails
           |       +-- check account status
           |       +-- verify password with PasswordEncoder
           |       +-- check credentials status
           |       |
           |       +-- success -> authenticated Authentication
           |       +-- failure -> AuthenticationException
           |
           v
SecurityContext (if authentication succeeded)
           |
           v
AuthorizationFilter / @PreAuthorize
  authorized -> Controller
  unauthorized -> AccessDeniedException -> typically 403
```

This is the conceptual flow for **HTTP Basic with a username/password provider**. Form login uses `UsernamePasswordAuthenticationFilter`; a JWT Resource Server uses `BearerTokenAuthenticationFilter` and `JwtAuthenticationProvider`; other token types use different providers/managers. Do not infer from a Basic-auth exception that every authentication mechanism uses `DaoAuthenticationProvider`.

Distinguish the boundaries:

1. **Authentication input**: the token object built by a filter or caller, such as `UsernamePasswordAuthenticationToken`.
2. **Authentication routing**: `ProviderManager` locates an appropriate provider.
3. **Credential/identity validation**: the provider and user store or identity provider evaluate the credentials.
4. **Account policy**: locked/disabled/expired checks depending on provider type.
5. **Authorization**: endpoint/object permission checks after authentication succeeds.

A failure at layer 2 is fundamentally different from one at layer 3, 4, or 5.

## 3. `Authentication`, `AuthenticationManager`, and `AuthenticationProvider`

Three core contracts:

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

These are **API signature excerpts for explanation**, not two interfaces you should redefine in your project.

`AuthenticationManager` is the entry point for authentication requests. `ProviderManager` is the common implementation: it iterates over `AuthenticationProvider` instances, checks `supports(...)`, invokes `authenticate(...)`, and may delegate to a parent manager if configured.

A provider may:

- Return an authenticated `Authentication`: success.
- Return `null`: decline to decide and give subsequent providers a chance.
- Throw `AuthenticationException`: handled the token, and authentication failed or encountered an internal issue.

Certain exceptions such as `AccountStatusException` and `InternalAuthenticationServiceException` cause `ProviderManager` to stop early; other exceptions may be remembered while continuing to try remaining providers. Therefore, do not assume “one provider throwing an error is always the final outcome” when an application registers multiple providers.

`supports(Class<?>)` only indicates that a provider **recognizes the token class**, not that it can authenticate every instance of that class. The right token class with wrong credentials leads to `BadCredentialsException`; an unsupported token class or no handling provider leads toward `ProviderNotFoundException`.

## 4. `ProviderNotFoundException`: No Provider Accepted the Work

Example scenario:

```text
Input token: UsernamePasswordAuthenticationToken
Configured provider: AnonymousAuthenticationProvider only

AnonymousAuthenticationProvider.supports(
    UsernamePasswordAuthenticationToken.class) == false
       |
       v
ProviderManager has no matching provider
       |
       v
ProviderNotFoundException
```

In practice, the exception message usually identifies the `Authentication` type the manager could not handle, such as `UsernamePasswordAuthenticationToken`. Never treat the exact exception message string as an HTTP API contract, because class names and configurations vary across environments and versions.

Common causes:

1. **Missing provider of the right type**: the filter creates a username/password token, yet the manager only has another provider type attached.
2. **Custom `AuthenticationManager` shadows default configuration**: after defining a custom manager bean or config, `DaoAuthenticationProvider` or another expected provider is no longer inside the active manager.
3. **Wrong token class**: a custom filter constructs an `Authentication` implementation unsupported by any configured provider.
4. **Wrong `SecurityFilterChain` or matcher order**: the request entered a different chain than expected, using a manager with a different provider list.
5. **Providers all return `null`**, and no parent manager succeeds.
6. **Custom integration misimplements `supports(...)`**, e.g. failing on an unexpected subclass or using `==` class equality inappropriately.
7. **Spring context/wiring mismatch**: a bean exists yet is never wired into the `ProviderManager` actually backing the filter.

Do not paper over this by turning every failure into `BadCredentialsException`, or adding a provider that “always returns authenticated” just to make tests pass. Fix the **authentication graph**: which token type the filter creates, which manager receives it, which provider supports that type, and which chain owns the manager.

### When Is It Not `ProviderNotFoundException`?

If `DaoAuthenticationProvider` supports `UsernamePasswordAuthenticationToken` and checks the password but finds it wrong, it throws `BadCredentialsException`, **not** `ProviderNotFoundException`. If the credentials are valid yet the user is locked, the result can be `LockedException`.

Diagnosing the actual root cause prevents adding extra providers when the real issue is credentials or account policy.

## 5. `BadCredentialsException`: Credentials Were Rejected

For username/password authentication, `BadCredentialsException` typically occurs when the password fails `PasswordEncoder.matches(...)`. Keep in mind:

- A non-existent username often produces **the same exception type** to prevent leaking an account list.
- Password encodings `{bcrypt}`, `{noop}`, or other IDs must match the configured encoder. Missing password encoder prefixes or config can throw other exceptions or configuration errors rather than a clean `BadCredentialsException`.
- If the user is locked or disabled, the provider may throw an account-status exception **before checking the password**.
- Token, API key, LDAP, and OAuth2/JWT authentication have different credential semantics; the same exception class does not guarantee the same root cause.

`AbstractUserDetailsAuthenticationProvider` provides `hideUserNotFoundExceptions` (enabled by default in common configurations), translating `UsernameNotFoundException` into `BadCredentialsException` for callers. Do not disable this in production just to show users “email does not exist”.

A safe public response is typically:

```json
{
  "error": "invalid_credentials",
  "message": "Unable to sign in with the provided credentials."
}
```

Use the same message for both non-existent users and wrong passwords when preventing account enumeration. With HTTP Basic, the default `BasicAuthenticationEntryPoint` returns `401` with `WWW-Authenticate`, rather than emitting the JSON above automatically. Returning JSON requires a custom entry point or failure handler that still preserves proper HTTP semantics.

**Never log** user passwords, Basic `Authorization` headers, or `Authentication` credentials to “find where it went wrong”.

## 6. Account Status Errors and Where Checks Occur

Common flags on `UserDetails`:

| `UserDetails` Property | Healthy Value | Failure Case | Typical Exception |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Account is locked | `LockedException` |
| `isEnabled()` | `true` | Account is disabled | `DisabledException` |
| `isAccountNonExpired()` | `true` | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Password/credentials expired | `CredentialsExpiredException` |

In `DaoAuthenticationProvider`, pre-authentication checks typically inspect locked, enabled, and account non-expired; credentials non-expired runs after password verification in the default post-authentication checker. This is **behavior of that specific provider/checker**, not a promise that every custom provider uses the same order.

These status exceptions belong to the `AccountStatusException` family in Spring Security. They **do not mean the user lacks permission for an endpoint**. An authenticated user lacking `ROLE_ADMIN` is blocked at authorization, typically via `AccessDeniedException` leading to HTTP 403—not `DisabledException`.

### Operational Design

- **Locked:** identify which policy triggered the lock; never auto-unlock accounts by allowing unlimited client retries.
- **Disabled:** may reflect admin action, HR lifecycle, or policy violation; return only a generic message to clients.
- **Account expired:** identity validity ended; may require renewal or profile updates.
- **Credentials expired:** the user must change or recover credentials through a protected flow; never mutate account state in a controller from unauthenticated input.
- **Multiple providers:** LDAP/IdP/DAO may emit different exceptions for similar conditions; map diagnostics internally without leaking internals.

Never misclassify an account-status exception as “wrong password” in internal operational logs, or support staff will tell users to re-type passwords needlessly. At the same time, avoid revealing `user exists, locked until ...` to unauthenticated callers if that enables account enumeration.

## 7. Quick Comparison of Commonly Confused Failures

| Exception / Event | Layer | Meaning | Typical HTTP Response |
| --- | --- | --- | --- |
| `ProviderNotFoundException` | `ProviderManager` | No provider authenticates the supplied token type | May be mapped to 401 by entry point; inspect internal config error |
| `BadCredentialsException` | Authentication provider | Invalid credentials or masked missing user | 401 with HTTP Basic; form login may redirect |
| `UsernameNotFoundException` | `UserDetailsService` | User not found | Often masked as `BadCredentialsException` by default DAO provider |
| `LockedException` | Account status check | Account is locked | Usually 401 or failure handler |
| `DisabledException` | Account status check | Account is disabled | Usually 401 or failure handler |
| `AccountExpiredException` | Account status check | Account expired | Usually 401 or failure handler |
| `CredentialsExpiredException` | Credentials check | Password/credentials expired | Usually 401 or password-change flow |
| `InternalAuthenticationServiceException` | Provider / `UserDetailsService` | Internal failure from backing auth system | Handler-dependent; alert backend team, do not treat as bad user input |
| `AccessDeniedException` | Authorization | Authenticated but lacking permission | Typically 403 |
| Missing authentication | `AuthenticationEntryPoint` | Route requires an authenticated caller | 401 or login redirect depending on flow |

**HTTP status alone does not uniquely identify the Java exception type.** Basic, form login, custom failure handlers, API gateways, method security, and error handlers can all reshape status and body. Analyze the request, filter type, safely captured root-cause exception, and active `SecurityFilterChain`.

## 8. Runnable Project: Spring Boot 3.3.5 + Java 17 + Servlet Security

Let's build a small app with:

1. Public `GET /public/ping`.
2. `GET /api/profile` requiring `ROLE_READER`.
3. In-memory users in active, locked, disabled, expired-account, and expired-credentials states.
4. HTTP Basic for the exercise; **loopback only**, using `{noop}` demo passwords.
5. MockMvc tests for HTTP status and direct `ProviderManager`/DAO provider tests to distinguish **exact exception types**.

### 8.1. Project Structure

```text
auth-exception-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/authdiag/
    │   │   ├── AuthDiagApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/authdiag/
            ├── AuthenticationHttpTest.java
            └── AuthenticationExceptionTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
```

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

The app listens on loopback only; never expose test accounts or HTTP Basic without TLS to the Internet. A Java 17-compatible Gradle wrapper is needed in the project directory; use `./gradlew` if present, or install Gradle and generate the wrapper first.

### 8.2. Java Main Class

Create `src/main/java/demo/authdiag/AuthDiagApplication.java`:

```java
package demo.authdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDiagApplication.class, args);
    }
}
```

### 8.3. UserDetailsService and SecurityFilterChain

Create `src/main/java/demo/authdiag/SecurityConfig.java`:

```java
package demo.authdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build(),
                User.withUsername("locked")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .accountLocked(true)
                        .build(),
                User.withUsername("disabled")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .disabled(true)
                        .build(),
                User.withUsername("expired")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .accountExpired(true)
                        .build(),
                User.withUsername("old-password")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .credentialsExpired(true)
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/api/profile").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`UserDetails` in the demo reproduces all four account states. `.roles("READER")` creates the `ROLE_READER` authority; that is **authorization**, separate from credentials and account status.

`{noop}` enables plaintext comparison for learning; **never store plaintext passwords in production**. Real apps must use strong hashing such as BCrypt/Argon2 with a managed `PasswordEncoder`, credential rotation, rate limiting, auditing, and proper user lifecycle policies.

If Spring Boot has multiple `SecurityFilterChain` beans, a request may enter a different chain than expected. Seeing a `UserDetailsService` bean alone does not prove every chain uses that provider; inspect the `AuthenticationManager` inside the actual chain.

### 8.4. Controller

Create `src/main/java/demo/authdiag/ProfileController.java`:

```java
package demo.authdiag;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Principal principal) {
        return Map.of("name", principal.getName());
    }
}
```

Never return passwords, detailed internal authorities, or raw authentication tokens. When Basic auth fails, the request never reaches `/api/profile`; the filter/entry point responds per HTTP policy.

## 9. Testing over HTTP and Reading Status Codes

Start the project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Call the public endpoint:

```bash
curl -i http://127.0.0.1:8080/public/ping
```

With the server running properly, the JSON body corresponds to:

```json
{"status":"ok"}
```

Active user signs in successfully:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/profile
```

Success JSON body:

```json
{"name":"alice"}
```

Wrong password:

```bash
curl -i -u alice:wrong \
  http://127.0.0.1:8080/api/profile
```

HTTP Basic normally returns `401 Unauthorized` with `WWW-Authenticate: Basic ...`. Non-existent, disabled, locked, and expired accounts in this example also typically receive 401 at the HTTP boundary. **Do not expect each account status to have a distinct HTTP status code** — that can create an account enumeration vulnerability.

Testing a disabled user:

```bash
curl -i -u disabled:demo-only \
  http://127.0.0.1:8080/api/profile
```

In the demo, the user does not reach the controller. To distinguish the exact Java exception as `DisabledException` rather than `BadCredentialsException`, **test `AuthenticationManager`/provider directly** as shown next.

`curl -u` commands can expose credentials in shell history or process listings in some environments. These are local-only examples; in CI or production use secret management and secure credential delivery without writing them to public transcripts.

## 10. MockMvc: Verifying Authentication Failures at the HTTP Boundary

Create `src/test/java/demo/authdiag/AuthenticationHttpTest.java`:

```java
package demo.authdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void validCredentialsReachController() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("ghost", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("disabled", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("locked", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredAccountIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("expired", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredCredentialsAreUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("old-password", "demo-only")))
                .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test
```

This test suite verifies the **HTTP contract**, not the internal Java exception type. `@AutoConfigureMockMvc` uses the Spring application context to run the Spring Security filter chain; `httpBasic(...)` builds a real Basic header for the filter, **unlike** `.with(user("alice"))`, which injects an identity directly without checking passwords.

If you replace `httpBasic(...)` with `user(...)`, the test no longer proves the password check ran and can miss the diagnostic target.

## 11. Direct Unit Tests: Distinguishing Every Exception Precisely

HTTP tests returning 401 generally do not reveal the underlying cause. To verify the exact Java class, construct `DaoAuthenticationProvider` with the `UserDetailsService` fixture and invoke `ProviderManager.authenticate(...)` directly.

Create `src/test/java/demo/authdiag/AuthenticationExceptionTest.java`:

```java
package demo.authdiag;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationProvider;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class AuthenticationExceptionTest {

    @Autowired
    UserDetailsService userDetailsService;

    private AuthenticationManager daoManager;

    @BeforeEach
    void setup() {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(userDetailsService);
        dao.setPasswordEncoder(
                PasswordEncoderFactories.createDelegatingPasswordEncoder());
        daoManager = new ProviderManager(List.of(dao));
    }

    private static UsernamePasswordAuthenticationToken credentials(
            String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                user, password);
    }

    @Test
    void wrongPasswordYieldsBadCredentials() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("alice", "wrong")))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void missingUserIsMaskedAsBadCredentialsByDefault() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("ghost", "demo-only")))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void lockedAccountYieldsLockedException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("locked", "demo-only")))
                .isInstanceOf(LockedException.class);
    }

    @Test
    void disabledAccountYieldsDisabledException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("disabled", "demo-only")))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void expiredAccountYieldsAccountExpiredException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("expired", "demo-only")))
                .isInstanceOf(AccountExpiredException.class);
    }

    @Test
    void expiredPasswordYieldsCredentialsExpiredException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials(
                        "old-password", "demo-only")))
                .isInstanceOf(CredentialsExpiredException.class);
    }

    @Test
    void managerWithoutProviderForUsernamePasswordYieldsProviderNotFound() {
        AuthenticationManager wrongManager =
                new ProviderManager(List.of(
                        new AnonymousAuthenticationProvider("test-key")));

        assertThatThrownBy(() ->
                wrongManager.authenticate(credentials("alice", "demo-only")))
                .isInstanceOf(ProviderNotFoundException.class);
    }
}
```

**Important QA notes:**

- `AnonymousAuthenticationProvider` is not designed to support `UsernamePasswordAuthenticationToken`. Thus `wrongManager` intentionally demonstrates **provider mismatch** without affecting the app's `SecurityFilterChain`.
- `DaoAuthenticationProvider` is constructed **specifically in the test** to pinpoint the exact exception; the test does not assume HTTP responses must expose Java exception names.
- `createDelegatingPasswordEncoder()` supports prefixes like `{noop}` in demo data. Production must use attack-resistant hashing; keep `{noop}` strictly for study projects.
- A wrong password on an **active** user is the classic `BadCredentialsException` case; for locked/disabled users, the provider may stop before checking the password.
- The `ghost` test checks default **hiding of `UsernameNotFoundException`**; disabling user hiding is usually inappropriate for public-facing systems.

**Version note:** `new DaoAuthenticationProvider()` and `setUserDetailsService(...)` apply to the Spring Security 6.x line paired with Spring Boot 3.3.5; some APIs may be deprecated in newer releases. When upgrading Spring Security, adopt the constructor/configuration style supported by that version and rerun tests rather than forcing deprecated code onto an incompatible release.

This test suite proves the logic of the **DAO provider**, not LDAP/OIDC/JWT or a real database. When testing custom providers, verify their exact `supports(...)` and exception contracts.

## 12. `ProviderManager` with Multiple Providers and a Parent Manager

A configuration may include multiple providers:

```text
ProviderManager
  |
  +-- Provider A (supports UsernamePasswordAuthenticationToken)
  |     -> returns null or throws AuthenticationException
  |
  +-- Provider B (supports UsernamePasswordAuthenticationToken)
  |     -> succeeds or fails
  |
  +-- Parent AuthenticationManager (if configured)
        -> attempts authentication per its own policy
```

Key rules:

1. If Provider A returns `null`, Provider B can continue handling the token.
2. Provider A throwing `BadCredentialsException` might not be final if Provider B or a parent manager succeeds per contract.
3. `AccountStatusException` and `InternalAuthenticationServiceException` typically halt `ProviderManager` early so other providers cannot bypass account policy or backend failures.
4. If no provider handles the token and no parent resolves it, the manager can throw `ProviderNotFoundException`. If another authentication exception was retained, the manager can rethrow that instead.
5. An overly broad `supports(...)` can mistakenly claim tokens it does not own; an overly narrow `supports(...)` causes valid tokens to be skipped.
6. With multiple `SecurityFilterChain` beans, each chain can reference its own manager. Adding a provider to one bean does not guarantee filters in another chain use it.

**Never** fix a provider mismatch by adding an `AuthenticationProvider` that always returns `authenticated=true` for every request. That is a severe vulnerability, especially if placed ahead of password verification.

## 13. Exception Translation: 401, 403, and Form Login

In Spring Security Servlet, exceptions can be handled directly inside authentication filters (such as Basic or form-login filters) or by `ExceptionTranslationFilter` on the authorization path.

### Authentication Failure

When credentials are invalid, the account is disabled/locked, or no provider handles the token, the request normally never reaches the controller. An `AuthenticationEntryPoint` or authentication failure handler determines the response.

**HTTP Basic**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Actual headers and realm depend on configuration. The body may be empty or a default message; do not expect the response body to state the Java exception class.

**Form login**: failure may redirect to the login page with an error indicator. A `302` in this flow **does not** imply authentication succeeded; check the session, target URL, and events.

### Authorization Failure

If a user is authenticated yet lacks permission:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

an `alice` holding `ROLE_READER` accessing `/api/admin/report` normally receives **403 Forbidden**. That is not a password error.

Some configurations represent an anonymous token as an authentication object flagged authenticated at the implementation level, yet authorization still identifies anonymous callers via a trust resolver. Therefore, never infer that a caller is logged in solely from `Authentication.isAuthenticated()`.

### A Practical Interface Guideline

Public HTTP responses should provide just enough information for clients to know whether to sign in again, change passwords via the proper flow, or contact support. **Lockout details, user existence, provider names, and stack traces belong in internal audit/monitoring channels** with restricted access, never in open responses.

## 14. Methodically Diagnosing `ProviderNotFoundException`

When logs show `ProviderNotFoundException`, inspect in order:

1. **Incoming token type**: e.g., `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken`, `PreAuthenticatedAuthenticationToken`, OAuth2 login token; never inspect or log `credentials`.
2. **Filter producing the token**: Basic, form login, bearer, custom filter... Confirm the request traverses the expected filter.
3. **Active `SecurityFilterChain`**: check `securityMatcher(...)` and chain order. A request may match an earlier chain and bypass the one you are reading.
4. **`AuthenticationManager` invoked by the filter**: distinguish a global manager bean, an `HttpSecurity`-scoped manager, a per-request manager resolver, and a parent manager.
5. **Providers inside that manager**: which provider types exist, and which token classes their `supports(...)` methods accept.
6. **Custom provider implementation**: does `supports` accept subclasses properly; does `authenticate` return `null` appropriately or throw?
7. **Context wiring**: is the bean Spring-managed and registered in the exact manager in use?
8. **Negative tests**: pass an unsupported token type to verify the failure, then wire the right provider and verify success.

In production, internal logs may record **token class name**, normalized filter/chain names, correlation ID, and error category; never log `Authentication#getCredentials()` or raw bearer tokens / `Authorization` headers.

If you declare `@Bean AuthenticationManager`, check whether it overrides Spring Boot/Security auto-configuration paths. When constructing a `ProviderManager` manually, wiring providers for every supported token is your responsibility.

## 15. Diagnosing `BadCredentialsException` and Password Encoders

When users report “my password is right but the API still returns 401”, do not rush to swap encoders. Check:

1. Which endpoint/chain received the request, Basic or form login, and whether the client actually sent credentials.
2. Whether `UsernamePasswordAuthenticationToken` carries the expected username (trimming/case normalization per contract, without altering secrets).
3. Whether `UserDetailsService` connects to the right user source and reads account status accurately.
4. Password hash storage, prefixes (`{bcrypt}`, `{noop}` in tests), algorithm, and configured `PasswordEncoder`.
5. Whether the provider compares passwords with `matches(raw, encoded)`, rather than string comparison or double-hashing.
6. Whether legacy records were migrated without prefixes; plan a safe migration if needed.
7. Account lock/disabled/expired policies and rate limiting that may produce separate errors.
8. Whether a reverse proxy/gateway stripped or overwrote the `Authorization` header or altered the route.

**Never put raw passwords into exception messages or logs.** Handle bad credentials in the authentication channel rather than recording them in audit payloads. If inspecting a hash format, stick to non-sensitive metadata like encoder ID or hash format (carefully vetted), avoiding pasting full hashes into public tickets.

### Error `There is no PasswordEncoder mapped for the id "null"`

When using `DelegatingPasswordEncoder` and stored passwords lack a valid prefix ID, you can hit an encoder mapping failure (usually indicating inconsistent hash/encoder configuration). This is a **configuration or migration bug**—do not report “wrong password” and ignore fixing the stored data or encoder.

The `"demo-only"` password works only in tests because `{noop}` is in the demo project. Production must store proper hashes rather than “quick-fixing” the database with `{noop}`.

## 16. User Store Failures and Provider Reliability

`UserDetailsService.loadUserByUsername(...)` can fail because of:

- Database timeouts or unreachable connections.
- Unavailable LDAP/IdP.
- Bugs mapping a user record to `UserDetails`.
- Duplicate/inconsistent records returned from the user store.
- Exhausted transaction or connection pools.
- Stale user caches failing to reflect recent locks or disablements.

Providers can use `InternalAuthenticationServiceException` to represent backend failures while querying the user service. This is **not** evidence that the user entered bad credentials. Operations should distinguish “credential mismatch” from “authentication backend unavailable” so alerts fire accurately and outages do not trigger account lockouts.

Some systems implement short retries or failover for backends, yet never retry infinitely on a single password/lockout attempt. Never ignore disabled/locked flags when LDAP/DB transiently fails, and never default to allowing logins when the primary provider disconnects (*fail-open*) without an explicitly approved recovery policy.

## 17. Error Message Mapping and Account Enumeration Defense

### Public API / Browser

Return messages that **do not reveal whether an account exists**. For example:

```json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Unable to authenticate the provided credentials."
}
```

For password resets, route to a safe flow that does not require a public API to confirm user existence (e.g., “If the account is valid, recovery instructions will be sent”).

### Internal Diagnostics

You may log:

```text
event=authentication_failed
correlation_id=req-7f3
mechanism=http_basic
category=account_locked
principal_hash=<pseudonymized-id>
```

`principal_hash` here is only an **illustrative label**, not a real value, and you should not use unsalted username hashes vulnerable to brute force. Use a governed internal user ID or a keyed pseudonymous ID per data-security policy.

Internally, tracking `bad_credentials`, `account_disabled`, `provider_unavailable`, and `provider_mismatch` aids operations, provided logs have strict retention/access controls and zero credential leaks. Also guard exception stack traces, as custom code sometimes embeds raw credentials in exception messages.

### Relationship to HTTP Status Codes

Avoid returning `423 Locked` for every locked-account failure if doing so publicly discloses account state. If a product has a specific UX requirement for users verified through another factor, design a dedicated secure flow. In the HTTP Basic demo, returning a generic 401 is clear and limits information leakage.

## 18. Testing in Real Systems

Beyond the demo tests, a real application should include:

| Scenario | Test Layer | What It Must Prove |
| --- | --- | --- |
| Token class with no provider | Unit `ProviderManager` | Throws `ProviderNotFoundException`, unauthenticated |
| Wrong password | Provider/manager unit | `BadCredentialsException` |
| Non-existent username | Provider unit | Does not leak existence in public exceptions |
| Locked/disabled/expired | Provider unit | Exact account-status exception |
| Invalid Basic auth | MockMvc filter integration | 401, never reaches controller |
| Authorized user | MockMvc | 200 and correct principal |
| Authenticated user lacking role | MockMvc | 403 (if endpoint requires another role) |
| Invalid JWT signature/issuer | Resource Server integration | Rejected per policy; never rely on DAO provider to conclude |
| LDAP/DB down | Integration fault injection | Fail closed, accurate metric/alert category |
| Multiple `SecurityFilterChain`s | Spring integration | Request matches right chain/manager, no bypass |
| Account state changes between requests | Integration | Permissions and authentication do not stay stale past policy |
| Header/credential leaks in logs | Security test | No password, `Authorization`, or bearer token logged |

### Difference Between Three Test Types

**Authorization tests** can use `.with(user("alice").roles("READER"))` to inject an `Authentication` and verify permission rules. They do not verify passwords.

**Authentication tests** should send credentials through real filters, such as `.with(httpBasic("alice", "wrong"))`, or call `AuthenticationManager`/providers directly.

**End-to-end tests** exercise real HTTP servers/gateways, TLS, DB/LDAP/IdP, and cookies/sessions. MockMvc does not simulate components outside the JVM.

Separating these layers ensures a “green” test never hides broken provider wiring or account enumeration flaws.

## 19. Troubleshooting Checklist

- Identify the request's route, HTTP method, filter chain, and authentication mechanism.
- Confirm whether an incoming `Authentication` exists and its token class, without printing credentials.
- Locate the exact `AuthenticationManager` invoked by that filter/endpoint rather than guessing from similarly named beans.
- Verify at least one provider supports the token; check `supports()` and parent managers.
- If a provider exists, distinguish password mismatch, hidden missing user, locked/disabled/expired status, and backend outage.
- Confirm `PasswordEncoder` and stored hash formats match; never enable `{noop}` as a quick fix in production.
- Verify `401` is an authentication failure; `403` is typically authorization or CSRF depending on flow.
- Never treat `ProviderNotFoundException` as a user password mistake or add an always-authenticated provider.
- Ensure public HTTP responses never reveal user existence, lock status, provider details, or stack traces.
- Include negative tests for missing user, wrong password, all four account states, provider mismatch, and backend outage.
- Monitor internally categorized audit metrics/logs with correlation IDs and zero passwords/tokens.
- After modifying or upgrading Spring Security, rerun wiring tests for `AuthenticationManager`/providers and multi-chain matchers.

## Takeaways

`ProviderNotFoundException` means **the `AuthenticationManager`/`AuthenticationProvider` pipeline could not handle the token type**; it is primarily a provider selection/wiring issue. `BadCredentialsException` means **the credentials were rejected**, which may also mask a non-existent user. `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException` represent **account status policies**. All of these must be distinguished from **authorization denials** after authentication. Diagnose internal causes safely with provider tests and redacted logs, while keeping public HTTP error messages generic enough not to expose identities or account states to attackers.