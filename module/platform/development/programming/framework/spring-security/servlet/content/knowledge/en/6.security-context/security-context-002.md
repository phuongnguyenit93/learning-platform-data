# Authentication Before and After Verification: Principal, Credentials, Authorities

In Spring Security Servlet, `Authentication` is the object describing either **an identity verification request** or **an identity verification result**. Although it is the same interface, the meaning of its data before verification and after verification is very different. Failing to distinguish these two states can lead you to mistake a client-claimed username for a logged-in user, confuse credentials with access permissions, or believe that `isAuthenticated() == true` always guarantees a real user has logged in.

This lesson focuses on the three components **principal – credentials – authorities** and their transformation in the Spring Security authentication flow on the Servlet stack. Examples apply to Java 17+, Spring Boot 3.x, and Spring Security 6.x; runnable code uses Spring Boot 3.3.5. Hardcoded accounts and passwords are for local testing only.

After this lesson, you will be able to:

- State accurately what `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `getDetails()`, `getName()`, and `isAuthenticated()` provide.
- Compare an **unauthenticated** `UsernamePasswordAuthenticationToken` with the **authenticated** `Authentication` returned by `AuthenticationManager`.
- Explain why an authoritative `AuthenticationProvider` must verify credentials before treating the result as trustworthy.
- Recognize the differences between anonymous, remember-me, and full authentication; avoid checking permissions with a simple boolean flag.
- Use `SecurityContextHolder`, HTTP Basic, and MockMvc to observe principal/authorities safely without exposing passwords.

## 1. What Information Does the Authentication Interface Hold?

`org.springframework.security.core.Authentication` is both a Java `Principal` and a carrier of authentication and permission data. Core members:

| Method | Meaning | Example before verification | Example after verification |
| --- | --- | --- | --- |
| `getPrincipal()` | The subject represented by the authentication; type depends on mechanism | String `"reader"` supplied by the request | Usually a loaded and verified `UserDetails` in username/password flows |
| `getCredentials()` | Evidence used to prove identity | Raw password, token, or corresponding credential | May be `null` after erasure to reduce leakage risk |
| `getAuthorities()` | `GrantedAuthority` instances attached to the authentication | Usually empty on an unverified login token | E.g. `ROLE_READER`, `REPORT_READ` granted by a trusted source |
| `getDetails()` | Additional information about the request/authentication source | May be request metadata | May hold relevant metadata; not permissions by default |
| `isAuthenticated()` | State flag of the authentication object | `false` for an unverified login token | `true` for a normal authentication result |
| `getName()` | Representative name derived from the principal | Usually the supplied username | Usually the username from the verified principal |

**There is no universal contract that principal is always a String or UserDetails.** In another mechanism, the principal may be a `Jwt`, `OAuth2User`, a custom object, or something else. In production code, check the actual type or use an abstract API like `getName()` if you only need the name.

**There is no contract that credentials are always a password.** With HTTP Basic, credentials are usually a password. With bearer authentication, credentials may be a token or already cleared. Credentials are *evidence*, while authorities are *determined permissions*; they solve two separate problems.

`getDetails()` is also not authorities. For example, IP address, session ID, or device metadata do not grant roles by themselves. Depending on the project, details may be absent or added by the application; they should not be treated as authentication evidence unless verified by design.

## 2. Before Verification: An Identity Claim Is Not a Trusted Identity

When a caller submits a username/password, the application only has **caller-claimed information**. At the Spring Security layer, a common representation is:

~~~java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    "reader",
    "reader-pass"
);
~~~

This is a snippet placed inside a method and requires importing `org.springframework.security.core.Authentication` and `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`. The `unauthenticated` factory creates a token with:

- `getPrincipal()` as `"reader"`: a **claim** provided by the caller, not yet proven.
- `getCredentials()` as `"reader-pass"`: raw credential needing verification; retaining it for long or logging it carries risk.
- `getAuthorities()` typically empty: `ROLE_READER` cannot be granted solely from the username.
- `isAuthenticated()` as `false`.

Do not read `request.getName()` and immediately log "reader logged in". Names appearing before verification are untrusted input. Similarly, a client sending role strings in JSON/body/headers does **not** mean the server should attach those roles to `Authentication`.

### Distinguishing Three Questions

1. **Who is claimed?** `principal` in the request token.
2. **What evidence is provided?** `credentials` in the request token.
3. **Is the evidence accepted?** Known only after a trusted authentication mechanism processes it successfully.

Suppose an attacker sends `username=admin` and a wrong password: before verification, the token still has principal `admin`, which in no way means the attacker is an admin. `isAuthenticated()==false` and the absence of trusted authorities reflect its unverified state.

### Why Shouldn't a Request Token Be Placed Directly into SecurityContext?

`SecurityContext` is used by security components to determine the current identity. If an application puts a self-constructed authentication into the context and treats it as trusted without verification, it breaks the trust boundary. In the standard flow, the filter receives credentials → calls `AuthenticationManager` → provider verifies → returns the resulting authentication → places the result into the context via the appropriate mechanism.

**Safety rule:** a token constructed from request data must be an *authentication request*, never turned into an "authenticated" object simply because the client claimed a name or authority.

## 3. How Do AuthenticationManager and AuthenticationProvider Transition State?

`AuthenticationManager` is the abstract entry point for verifying an unauthenticated `Authentication`. For typical username/password applications, Spring Security may use `ProviderManager`, which delegates to an `AuthenticationProvider` supporting the token type. `DaoAuthenticationProvider` is a familiar provider that uses `UserDetailsService` to load the user and `PasswordEncoder` to compare the raw password against the stored password hash.

Conceptual flow when calling HTTP Basic:

~~~text
HTTP request
  Authorization: Basic <base64(username:password)>
        |
        v
BasicAuthenticationFilter
  -> extracts username/password
  -> Authentication request (unauthenticated)
        |
        v
AuthenticationManager / ProviderManager
  -> finds AuthenticationProvider supporting token
  -> loads UserDetails from UserDetailsService
  -> PasswordEncoder.matches(rawPassword, encodedPassword)
        |
        +---- invalid / invalid user ----> AuthenticationException
        |                                  -> entry point, typically 401 for Basic
        |
        +---- valid ----> Result Authentication (authenticated)
                          identified principal
                          authorities from trusted source
                          credentials may be erased
                                |
                                v
                          Request SecurityContext
                                |
                                v
                          authorization
                                |
                           +----+----+
                           |         |
                         allow     deny
                           |         |
                        controller  403/...
~~~

The Basic header is merely Base64 encoding of username/password, **not secure encryption**. Always use HTTPS when transmitting real credentials. Filters, managers, and providers may differ when using form login, JWT, OAuth2, or custom authentication; however, the boundary between *self-claimed data* and *verified result* must always exist.

An important contract:

~~~java
Authentication verified = authenticationManager.authenticate(request);
~~~

This is an **illustrative snippet**; `authenticationManager` is an instance configured with an appropriate provider. `authenticate(...)` either returns a trusted result from the provider or throws `AuthenticationException`; do not treat the original `request` as the result merely because the method was called. The result can be a **new object** with a different principal and authorities than the input; code should not rely on `request == verified`.

Do not catch all exceptions and fabricate a successful authentication to "let the user in". Authentication exceptions must be handled by the HTTP/entry-point mechanism or a designed failure flow, and must never lead to unauthorized access.

## 4. After Verification: Principal Is Confirmed, Authorities Become Meaningful

For an account `reader` whose server-side record looks like:

~~~text
username:    reader
password:    <stored BCrypt hash>
authorities: [ROLE_READER]
~~~

when the password is correct, the provider typically returns a `UsernamePasswordAuthenticationToken` in the authenticated state. With Spring Security 6.x and standard `DaoAuthenticationProvider`:

| Property | Unauthenticated token | Token after successful verification |
| --- | --- | --- |
| Principal | Client-sent username, e.g., `"reader"` | Typically `UserDetails` containing the server-side username |
| Credentials | Raw password in request | May exist temporarily in provider, then typically erased by `ProviderManager` |
| Authorities | Empty or untrusted | `ROLE_READER` taken from trusted `UserDetails` |
| `isAuthenticated()` | `false` | `true` |
| Meaning | Authentication proposal | Result verified by provider |
| Should it be placed in context as authenticated principal? | No, while unverified | Yes, through the appropriate security flow |

`DaoAuthenticationProvider` usually uses the verified username to determine the principal; the principal type is configurable, so do not assume every provider always returns `UserDetails`. The result may also carry details or custom information depending on the application.

### Why Isn't the Password Reused to Prove Login?

After authentication, authorization **does not need to inspect the raw password**. It needs an authenticated authentication along with the required authorities. In standard setups, `ProviderManager` enables `eraseCredentialsAfterAuthentication` and erases credentials on results supporting `CredentialsContainer`. Therefore:

- `getCredentials() == null` after login can be completely normal behavior.
- Do not use "credentials != null" as a condition to determine whether a user is logged in.
- Do not treat erased credentials as a sign of failed authentication.
- Do not store/serialize the entire `Authentication` into responses or logs, because depending on the provider and configuration, some sensitive parts may remain.

Credential erasure depends on the token type, manager, and actual configuration; there is no guarantee that **every implementation** always erases all secrets. If the application uses a custom provider, audit sensitive data erasure separately. If a cache shares a user object containing a password and that object gets erased after authentication, subsequent authentication attempts can break; design caching/user objects properly rather than arbitrarily disabling credential erasure.

## 5. Authorities: Roles, Permissions, and Confusing Cases

`Authentication.getAuthorities()` returns `Collection<? extends GrantedAuthority>`. Each authority represents a resolved permission, usually named as a string, though its specific meaning belongs to the application's authorization scheme.

Example:

~~~text
principal: reader
authorities:
  ROLE_READER
  ARTICLE_READ
  REPORT_EXPORT
~~~

When using Spring Security with default conventions:

- `hasRole("READER")` typically checks for authority `ROLE_READER`.
- `hasAuthority("ROLE_READER")` checks for the exact authority `ROLE_READER`.
- `hasAuthority("ARTICLE_READ")` checks for the exact string `ARTICLE_READ`.
- `hasRole("ARTICLE_READ")` typically looks for `ROLE_ARTICLE_READ`, which is **different** from the `ARTICLE_READ` permission.

The factory `User.withUsername("reader").roles("READER")` creates authority `ROLE_READER`; whereas `authorities("ARTICLE_READ")` uses the exact declared authority string. The role prefix can be customized in an application, so always verify how permissions are granted and compared.

A user who **logs in successfully** is not necessarily **allowed** to call a specific endpoint. Authentication is the step of proving identity; authorization is the step of comparing that identity's authorities against the resource's requirements.

| Authentication | Required access | Outcome |
| --- | --- | --- |
| Reader with `ROLE_READER` | `authenticated()` | Allowed |
| Reader with `ROLE_READER` | `hasRole("ADMIN")` | Denied, typically 403 |
| Reader with `ROLE_READER` | `hasAuthority("ARTICLE_READ")` | Denied if lacking `ARTICLE_READ` |
| Admin with `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| No valid login | `authenticated()` | With HTTP Basic, typically receives 401/challenge |

Do not attach authorities taken directly from untrusted HTTP body/query/headers. The authority source should be a user store, token claims **with verified signatures and appropriate bindings**, a trusted authorization service, or a verified custom provider.

## 6. Important Warning: isAuthenticated() Is Not Enough to Say "User Is Logged In"

In Spring Security, `AnonymousAuthenticationFilter` can create an `AnonymousAuthenticationToken` with a principal such as `anonymousUser`. Notably, an anonymous token typically has **`isAuthenticated() == true`** as the object's internal state, yet **it is still anonymous** and is not treated by `authenticated()` as a real logged-in user.

This sounds contradictory if you look only at the boolean. The reason is that the framework uses concepts like `AuthenticationTrustResolver` to distinguish anonymous, remember-me, and fully authenticated states when enforcing authorization policies.

Also distinguish:

- **Anonymous:** no real authenticated identity exists, even though the context holds an anonymous `Authentication`.
- **Remember-me:** may be restored from a cookie processed by the remember-me mechanism; this state may be permitted by `authenticated()` but does not satisfy `fullyAuthenticated()`.
- **Fully authenticated:** typically the result of authenticating through a mechanism requiring full credentials, per Spring Security policy definitions.
- **Pre-authenticated:** a provider/filter may trust an identity already authenticated by an upstream system; its verification and trust contract differ from username/password.
- **Bearer/JWT:** principal and authorities may be derived from a verified token, not necessarily `UserDetails` or a password.

In business code, a naive check like:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

boolean accepted = authentication != null && authentication.isAuthenticated();
~~~

is **insufficient** to conclude the caller is not anonymous. This illustrates an anti-pattern and should not be used as a guard for sensitive data.

**Prefer** declaring policies with `authorizeHttpRequests(auth -> auth.anyRequest().authenticated())`, `fullyAuthenticated()`, or appropriate authority rules. For special manual checks, use a consistent trust resolver/policy mechanism and verify appropriate boundaries. Avoid inventing custom authorization logic based on a single flag when the framework already provides authorization APIs.

## 7. SecurityContext: Where Does Post-Verification Authentication Appear?

In a typical Servlet flow, security filters load/create the appropriate `SecurityContext`, set the authentication after verifying credentials, and make that state visible to downstream filters and controllers.

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String name = current.getName();
    Collection<? extends GrantedAuthority> authorities =
        current.getAuthorities();
}
~~~

This is illustrative code requiring imports for `SecurityContextHolder`, `Authentication`, `GrantedAuthority`, and `Collection`. It is useful in controllers/services running within the same security context, but you must **not** infer from reading the context that every request always has a logged-in user: the context may have no `Authentication` or only an anonymous token.

In a Servlet application, `SecurityContextHolder` defaults to `ThreadLocal` to hold the active context. Spring Security includes filters responsible for setting up and clearing the context per request lifecycle. Do not manually call `SecurityContextHolder.getContext().setAuthentication(...)` from a controller with unverified data; doing so can make the application trust a false identity.

### Context Is Not Synonymous with Session

`SecurityContext` describes the current identity state; `SecurityContextRepository`/session policy determines how the context is loaded/saved across requests where applicable. Seeing an `Authentication` in a controller during **one** request does not prove it is persisted to the next request.

With HTTP Basic, the client normally resends credentials on each request. With session login, cookies and sessions help reload the context. With bearer tokens, the client sends the corresponding token on each request. Those mechanisms determine how the data is established and its trustworthiness, while code reading the context after authentication uses the same contract.

When code executes in an executor, `@Async`, or a new thread, the context does not automatically transfer accurately to every thread simply because the original request had an identity. Use Spring Security's appropriate propagation mechanisms and clear the context along its lifecycle; never store per-user `Authentication` in a static field.

## 8. Java 17+/Spring Boot Example: Observing States on Servlet Requests

The example includes a Spring MVC application with HTTP Basic, two in-memory accounts, and endpoints to observe the authenticated identity. The goal is to clearly distinguish **a pre-verification request token** in a unit test from **a verified result** in a controller, while testing authorization.

### 8.1. File Structure

~~~text
authentication-states-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authstate/
    │   ├── AuthenticationStatesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── IdentityController.java
    └── test/java/example/authstate/
        └── AuthenticationStatesTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'authentication-states-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

Spring Boot manages Spring Security module versions via appropriate dependency management. Do not force a separate version of `spring-security-core` while other artifacts remain on the Boot BOM.

### 8.2. Bootstrap Class

File `src/main/java/example/authstate/AuthenticationStatesApplication.java`:

~~~java
package example.authstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationStatesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationStatesApplication.class, args);
    }
}
~~~

### 8.3. Authentication and Authorization Configuration

File `src/main/java/example/authstate/SecurityConfiguration.java`:

~~~java
package example.authstate;

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
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

Here `UserDetailsService` stores server-defined users and authorities. HTTP Basic receives username/password, the provider verifies the hash with the encoder, and only after success are authorities placed into the trusted `Authentication` result.

The strings `reader-pass` and `admin-pass` are strictly for local learning examples. In real deployments, use a proper user store and secure secret management.

### 8.4. Observing Principal and Authorities in a Controller

File `src/main/java/example/authstate/IdentityController.java`:

~~~java
package example.authstate;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public String currentIdentity() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return "name=" + authentication.getName()
            + ";authenticated=" + authentication.isAuthenticated()
            + ";authorities=" + authorities;
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }
}
~~~

`/api/me` requires `authenticated()` via the fallback rule, so when the controller is invoked under this configuration, a normal real `Authentication` has already passed verification. The endpoint outputs only **name, the authenticated flag, and authorities**, not the principal object, credentials, details, or full token. In a real application, even the list of authorities should be evaluated before exposing to clients; here it is purely educational.

`authentication.isAuthenticated()` in the response is an **observed value**, not a controller permission guard. The Spring Security filter chain already enforced `authenticated()` before allowing the request to reach the handler. This avoids confusing the boolean with "not anonymous".

### 8.5. Testing Both States and HTTP Branches

File `src/test/java/example/authstate/AuthenticationStatesTests.java`:

~~~java
package example.authstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationStatesTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginRequestTokenIsNotYetAuthenticated() {
        Authentication before = UsernamePasswordAuthenticationToken
            .unauthenticated("reader", "reader-pass");

        assertFalse(before.isAuthenticated());
        assertEquals("reader", before.getPrincipal());
        assertEquals("reader-pass", before.getCredentials());
        assertTrue(before.getAuthorities().isEmpty());
    }

    @Test
    void publicRequestWorksWithoutLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void missingCredentialsReturnBasicChallenge() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void badCredentialsAreRejected() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validReaderCredentialsCreateTrustedIdentity() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=reader;authenticated=true;authorities=ROLE_READER"));
    }

    @Test
    void validAdminCredentialsCarryAdminRole() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=admin;authenticated=true;authorities=ROLE_ADMIN"));
    }

    @Test
    void verifiedReaderStillLacksAdminAuthority() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void verifiedAdminMayAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    @WithMockUser(username = "synthetic", roles = "READER")
    void testIdentityIsNotProofOfPasswordAuthentication() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=synthetic;authenticated=true;authorities=ROLE_READER"));
    }
}
~~~

The first test proves that an object freshly created from a username/password only carries an **unauthenticated** state. The MockMvc tests use `httpBasic(...)` to send credentials through the filter and verify that the controller receives only valid requests; the response body observes the principal name, authenticated flag, and authority.

The `@WithMockUser` test deliberately uses the name `synthetic`, which **does not exist in UserDetailsService**. It proves that Spring Security Test can attach a trusted test identity to verify controllers/authorization without **running real password verification**. Therefore, never rely on `@WithMockUser` alone to claim your password encoder or provider works properly.

### 8.6. Running Tests and Making Manual HTTP Calls

In the project directory with a compatible Gradle installed:

~~~bash
gradle test
gradle bootRun
~~~

If a Gradle wrapper is present, prefer `./gradlew test` / `./gradlew bootRun`; on Windows use `gradlew.bat test` / `gradlew.bat bootRun`. The Java files have Spring dependencies, so they cannot be run with just `javac`/`java` without setting up the appropriate classpath.

In another terminal:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:wrong http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
~~~

With the configuration above, the main results to observe:

| Request | Expected status | Body on success |
| --- | --- | --- |
| GET `/public/ping` without credentials | 200 | `pong` |
| GET `/api/me` without credentials | 401 | Error body not constrained |
| GET `/api/me` with reader and valid password | 200 | `name=reader;authenticated=true;authorities=ROLE_READER` |
| GET `/api/me` with reader and wrong password | 401 | Error body not constrained |
| GET `/api/admin` with reader and valid password | 403 | Error body not constrained |
| GET `/api/admin` with admin and valid password | 200 | `admin-only` |

The `WWW-Authenticate` header typically appears on HTTP Basic branches that require a challenge; exact error headers and bodies also depend on configuration/version. Passwords never appear in successful responses. If you want to observe credentials being erased after authentication, use a debugger in a learning environment inside the appropriate security code rather than printing them to logs or returning them to clients.

## 9. From Authentication to Authorization: Where Do 401/403 Come From?

Path for a successful request:

1. `BasicAuthenticationFilter` (when HTTP Basic is configured) reads the username/password.
2. Creates an unauthenticated authentication request, typically with a String principal and raw credentials.
3. `AuthenticationManager` selects a provider; the provider checks the user/password.
4. The provider returns an authenticated `Authentication` with a trusted principal/authorities.
5. `SecurityContext` holds the resulting authentication for the current request.
6. Authorization rules evaluate `authenticated()` or `hasRole(...)`.
7. If permitted, the request reaches the controller; if denied, security handles the denial branch.

Difference between **401** and **403** in the example:

- **401**: missing or unacceptable credentials for a URL requiring authentication. The HTTP Basic entry point typically returns a challenge.
- **403**: `reader` is authenticated, but its authorities do not include `ROLE_ADMIN`. Valid authentication does not grant all permissions.

In another application, 403 could also be caused by CSRF, while unauthenticated requests could receive a 302 redirect to a login page instead of 401 when using form login. Inspect the actual authentication mechanism and policy before drawing conclusions from a single status code.

**Do not confuse 401 with "null principal".** A pre-verification token may already have principal `reader` claimed by the client; it still lacks authorization. Nor confuse 403 with "wrong credentials": credentials may be completely valid while authorities fail the rule.

## 10. Common Pitfalls and How to Diagnose Them

| Symptom | Common misconception | Correct check |
| --- | --- | --- |
| Username visible in authentication before login | Thinking the user is already logged in | Check username source, token state, and whether provider verified it |
| `isAuthenticated()` returns true for anonymous token | Thinking there is a logged-in user | Use `authenticated()`/trust resolver policies; distinguish anonymous and full auth |
| After login `getCredentials() == null` | Thinking authentication failed | Check provider/manager credential erasure; rely on authorities and trusted state |
| Sending username `admin` still returns 401 | Thinking principal should be trusted by name | Check password/provider; never trust client identity claims |
| Reader can log in but `/api/admin` returns 403 | Thinking authentication failed | Compare `ROLE_READER` against `ROLE_ADMIN` |
| `ROLE_READER` and `READER` do not match | Confusing role with authority string | Check `hasRole`, `hasAuthority`, and default prefix |
| Logs do not show raw password | Thinking debugging is impossible | Use status, username, provider type, and safe error codes; never log secrets |
| `@WithMockUser` test passes but real HTTP Basic returns 401 | Confusing mock identity with real authentication | Add `httpBasic(...)` tests to exercise provider/password encoder |
| Request has authentication but another thread's service sees none | Assuming context auto-propagates to all threads | Check SecurityContext propagation and lifecycle |
| Current request has authentication, next request gets 401 | Assuming context always persists | Check session/repository and whether client resends credentials |
| Custom filter manually sets authenticated token for client data | Bypassing trust boundary | Route credentials through manager/provider and use only verified result |
| Serializing entire Authentication into response | Leaking sensitive credentials/details/principal | Expose only the minimum data permitted publicly |

A note on logging and operations support: recording **request path, auth mechanism, result status, and error category** can be sufficient for diagnostics. Never blindly log the `Authorization` header, passwords, credentials, intact tokens, or `Authentication.toString()`. Even if one implementation masks passwords in its string output, another implementation or custom details may not be safe.

## 11. Comprehension Verification Exercises

1. Construct `UsernamePasswordAuthenticationToken.unauthenticated("admin","wrong")`. Record the principal, credentials, authorities, and authenticated flag. Why can you not conclude this is an admin?
2. For a user with `ROLE_READER` and `ARTICLE_READ`, predict the outcomes for `authenticated()`, `hasRole("READER")`, `hasRole("ADMIN")`, and `hasAuthority("ARTICLE_READ")`.
3. Explain the path from raw password through `PasswordEncoder.matches` to the resulting `Authentication`. Is the provider required to reuse the exact same request token object?
4. Check code calling `getCredentials()` after authentication. Why shouldn't you rely on non-null credentials to infer login state?
5. If on a public request the context contains an `AnonymousAuthenticationToken` with `isAuthenticated()==true`, why can the `authenticated()` rule still reject anonymous access?
6. Write separate MockMvc tests for HTTP Basic with wrong password, right password without role, and right password with role. What statuses do you expect?
7. Use `@WithMockUser(username="ghost", roles="ADMIN")` for an admin endpoint. Why does this test not prove `ghost` has a real account in the system?
8. In a controller, change `authentication.getName()` to `(String) authentication.getPrincipal()`. In which cases could this throw `ClassCastException`, and what is a safer way to write it?
9. Compare a request carrying a session cookie with a request carrying a Basic header. By what mechanisms can they restore or create `Authentication`, and what still ends up in `SecurityContext`?
10. When adding a custom filter, identify the appropriate place to invoke `AuthenticationManager`, handle failures, and store the trusted result. Why must you never create `authenticated(...)` based on roles sent by the caller?

**Mental model to remember:** before verification, `principal` is the **claimed identity**, `credentials` are **unverified evidence**, and authorities are untrusted. After successful verification, the provider/manager produces a trusted result, the principal is confirmed, authorities are used for authorization, and credentials are typically erased once no longer needed. `SecurityContext` carries that result into request processing; authorization must still enforce the proper policy. The mere presence of an `Authentication` object, or an enabled `isAuthenticated()` flag, does not replace verification and permission checks.
