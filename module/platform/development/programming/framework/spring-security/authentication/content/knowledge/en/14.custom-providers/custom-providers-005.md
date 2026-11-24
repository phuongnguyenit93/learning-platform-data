# Returning an Authenticated Result with a Verified Principal and Authorities

> Scope: **Spring Security - authentication → Custom Provider** (Servlet, Spring Boot 3.x / Spring Security 6.x, Java 17+). The focus is on the contract of `AuthenticationProvider.authenticate(...)` upon **successful authentication**: it must return a trusted `Authentication` object with a `principal` resolved from server data and verified `GrantedAuthority` instances. The lesson also tests failure cases so that client-asserted data is never accidentally turned into a valid identity or permissions.

## 1. Why Is the Return Value of AuthenticationProvider a Security Boundary?

When a client submits a username and password form, `UsernamePasswordAuthenticationFilter` creates an authentication request that can be represented as:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "alice-pass");
```

This is **not yet a trusted identity**. `request.isAuthenticated()` is `false`; the username/password in the request are merely claims submitted by the client. A custom provider must verify the login credentials, check the account status, and read authorities from a server-controlled source **before** returning an authenticated token.

A successful result must satisfy all of the following conditions:

| Property | Untrusted input | Result after verification |
| --- | --- | --- |
| `isAuthenticated()` | `false` | `true`, but **only after** the evidence has been verified |
| `getPrincipal()` | Usually just the client-supplied username | `VerifiedPrincipal`/`UserDetails` from the located and verified account |
| `getCredentials()` | Raw password received from the request | `null` or erased credentials; never put passwords into context/session |
| `getAuthorities()` | Client-sent roles/authorities must not be trusted | `GrantedAuthority` instances built from server-verified roles/permissions |
| `getName()` | Client-asserted name | Identity consistent with the verified principal |
| `getDetails()` | May contain IP/session/request metadata | Auxiliary information, **not** used to prove permissions |

**Principle:** `isAuthenticated = true` is a security assertion. Whoever creates an `Authentication` in this state is responsible for the authentication evidence and the granted permissions. Never treat the `true` flag as a “mark as checked” action without actually checking.

`Authentication` types can vary by mechanism (username/password, certificate, OAuth2, etc.). In this lesson, the input is `UsernamePasswordAuthenticationToken` and the provider returns the same token type with a verified principal and authorities.

## 2. Authentication Flow and Component Responsibilities

```text
Browser
  |
  | POST /login: username=alice, password=alice-pass, CSRF token
  v
UsernamePasswordAuthenticationFilter
  | creates UsernamePasswordAuthenticationToken.unauthenticated(...)
  v
AuthenticationManager (typically ProviderManager)
  | selects an AuthenticationProvider with matching supports(...)
  v
AccountAuthenticationProvider.authenticate(request)
  | 1. Read username + credential
  | 2. Look up account from server source (id, passwordHash, status, roles)
  | 3. PasswordEncoder.matches(rawPassword, storedPasswordHash)
  | 4. Check account enabled/locked/expired per policy
  | 5. Build VerifiedPrincipal without password
  | 6. Build ROLE_USER/ROLE_ADMIN from server-stored roles
  '-- 7. Return UsernamePasswordAuthenticationToken.authenticated(...)
  v
AuthenticationManager
  | receives authenticated Authentication
  v
UsernamePasswordAuthenticationFilter success flow
  | applies session strategy, sets SecurityContext, saves via repository
  '-- success handler (redirect/response)
  v
GET /me, GET /admin on subsequent request
  | authorization reads Authentication.getAuthorities()
  '-- ALLOW/DENY according to verified permissions
```

**Clear separation of responsibilities:**

- `AuthenticationProvider` verifies the evidence and creates a trusted `Authentication` result. The provider itself is **not** responsible for setting `SecurityContextHolder` or issuing cookies/sessions.
- `AuthenticationManager` coordinates providers. `ProviderManager` can query multiple providers; not every request belongs to the same provider.
- The filter/login success mechanism receives the result, sets `SecurityContext`, and persists it according to configuration. If writing your own custom login controller, you must integrate `SecurityContextRepository.saveContext(...)` and an appropriate session strategy yourself.
- `AuthorizationManager` subsequently uses the `Authentication`'s authorities to decide access. Successful authentication does not mean the user has every permission.

### Three Valid Outcomes of authenticate(...)

| Outcome | Meaning | Example |
| --- | --- | --- |
| Return an authenticated `Authentication` | Provider proved identity and granted authorities from a trusted source | Valid password, account enabled |
| Throw `AuthenticationException` | Processed, but evidence is invalid or account state disallows login | `BadCredentialsException`, `DisabledException`, `LockedException` |
| Return `null` | Provider **cannot handle this request type** and yields to the next provider | A token belonging to another mechanism |

Do not return `null` to represent “wrong password” in a provider responsible for username/password authentication: if other providers exist, the manager may keep trying. Do not return an `isAuthenticated=false` token as a “partial success” result. With multiple providers, certain exception types can still lead to trying the next provider; thus designing the provider chain and precedence policy is a separate concern that must be verified.

## 3. Where Do Principal and GrantedAuthority Come From?

**Principal** is the verified entity identity. In an application, the principal can be `UserDetails` or a custom domain type. The example below uses an immutable Java `record` containing only the **account ID** and **username** matched against the server record.

**Authority** is a granted permission. `SimpleGrantedAuthority("ROLE_USER")` is a permission object; it does not check passwords itself. In standard configuration, `hasRole("ADMIN")` checks for authority `ROLE_ADMIN` (default `ROLE_` prefix), while `hasAuthority("invoice:read")` checks the exact string `invoice:read`. The two expressions have different semantics.

For example:

| Server record after authentication | Generated authority | Corresponding check |
| --- | --- | --- |
| `roles = ["USER"]` | `ROLE_USER` | `hasRole("USER")` |
| `roles = ["USER", "ADMIN"]` | `ROLE_USER`, `ROLE_ADMIN` | `hasRole("ADMIN")` |
| `permissions = ["invoice:read"]` | `invoice:read` | `hasAuthority("invoice:read")` |

**Never take authorities from the request** such as `role=ADMIN`, header `X-Role: ADMIN`, JSON field `permissions`, or `authentication.getAuthorities()` of an untrusted input token. If the system uses an external authority source (LDAP, IdP, IAM), the provider must verify integrity/issuer and map permissions per server policy before placing them into the result.

Avoid setting the principal directly to an entity containing `passwordHash`/secrets or a mutable object whose permissions could be changed after authentication. Using a small, immutable principal reduces data leakage risk, especially when `Authentication` is kept in session or printed in logs/debug output.

## 4. Complete Spring Boot 3 / Java 17+ Example

The example uses standard form login to clearly show `UsernamePasswordAuthenticationFilter → AuthenticationManager → custom provider`. The in-memory account store is strictly practice data; it can be swapped for an application repository/database/identity service without changing the `Authentication` return contract.

In a Spring Boot 3.x application with the Gradle plugin, declare:

```groovy
// build.gradle - place inside dependencies of the Spring Boot application
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

All the following Java files use package `example.providerresult`.

### 4.1. Bootstrapping the Application

**`src/main/java/example/providerresult/ProviderResultApplication.java`**

```java
package example.providerresult;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProviderResultApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProviderResultApplication.class, args);
    }
}
```

### 4.2. Account Store and Authoritative Data

**`src/main/java/example/providerresult/AccountDirectory.java`**

```java
package example.providerresult;

import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

record AccountRecord(
        String id,
        String username,
        String passwordHash,
        boolean enabled,
        Set<String> roles) {
}

interface AccountDirectory {
    Optional<AccountRecord> findByUsername(String username);
}

final class InMemoryAccountDirectory implements AccountDirectory {
    private final Map<String, AccountRecord> accounts;

    InMemoryAccountDirectory(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice",
            new AccountRecord(
                "acct-101", "alice",
                encoder.encode("alice-pass"), true, Set.of("USER")),
            "admin",
            new AccountRecord(
                "acct-102", "admin",
                encoder.encode("admin-pass"), true,
                Set.of("USER", "ADMIN")),
            "disabled",
            new AccountRecord(
                "acct-103", "disabled",
                encoder.encode("disabled-pass"), false, Set.of("USER"))
        );
    }

    @Override
    public Optional<AccountRecord> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
```

The demo data has three accounts: `alice` has only the USER role; `admin` has USER + ADMIN; `disabled` is disabled. Passwords are hashed using `PasswordEncoder`, never stored as plaintext in the record. In a real system, replace the in-memory store with a trusted repository; define clear username normalization rules, check account locked/expired when applicable policies exist, and never return passwordHash to the client.

### 4.3. Verified Principal Without Password

**`src/main/java/example/providerresult/VerifiedPrincipal.java`**

```java
package example.providerresult;

import java.security.Principal;

public record VerifiedPrincipal(
        String accountId,
        String username) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

`VerifiedPrincipal` holds the stable ID and username from the `AccountRecord` looked up by the server. `getName()` is consistent with `Authentication.getName()`. It contains no raw password, password hash, CSRF token, session ID, or self-asserted role claims from the request.

### 4.4. Custom AuthenticationProvider

**`src/main/java/example/providerresult/AccountAuthenticationProvider.java`**

```java
package example.providerresult;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Comparator;
import java.util.List;

public final class AccountAuthenticationProvider
        implements AuthenticationProvider {

    private final AccountDirectory directory;
    private final PasswordEncoder encoder;

    public AccountAuthenticationProvider(
            AccountDirectory directory,
            PasswordEncoder encoder) {
        this.directory = directory;
        this.encoder = encoder;
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return null; // This provider does not support other token types.
        }

        String username = request.getName();
        Object credential = request.getCredentials();
        String rawPassword = credential instanceof String value ? value : null;

        if (username == null || username.isBlank()
                || rawPassword == null || rawPassword.isEmpty()) {
            throw new BadCredentialsException("Invalid credentials");
        }

        AccountRecord account = directory.findByUsername(username)
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid credentials"));

        // Verify password against the server-stored passwordHash.
        // DO NOT compare two plaintext strings or roll your own hash algorithm.
        if (!encoder.matches(rawPassword, account.passwordHash())) {
            throw new BadCredentialsException("Invalid credentials");
        }

        if (!account.enabled()) {
            throw new DisabledException("Account disabled");
        }

        // Only use the role list taken from the verified server record.
        List<SimpleGrantedAuthority> verifiedAuthorities =
            account.roles().stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .sorted(Comparator.comparing(
                    SimpleGrantedAuthority::getAuthority))
                .toList();

        VerifiedPrincipal principal = new VerifiedPrincipal(
            account.id(), account.username());

        // Three-argument factory creates an isAuthenticated() == true token.
        // Called ONLY AFTER verifying credentials/status/authorities.
        return UsernamePasswordAuthenticationToken.authenticated(
            principal,
            null, // Do not retain rawPassword in the result.
            verifiedAuthorities);
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }
}
```

**Explanation of each choice:**

1. `supports(...)` only advertises the request type it can handle. `authenticate(...)` still guards against other tokens by returning `null`. The provider only verifies username/password, rather than blindly accepting every `Authentication` type.
2. `request.getName()` and `request.getCredentials()` are input data. The provider uses them to **look up and verify** the account, not treating them as trusted results upfront.
3. `PasswordEncoder.matches(raw, hash)` verifies the password, avoiding plaintext comparison or re-hashing with BCrypt and comparing strings. BCrypt uses a salt, so two `encode(...)` calls normally produce different hashes for the same password.
4. `account.enabled()` is checked before creating an authenticated token. The example has one enabled state; production typically also checks locked, account expired, credential expired, MFA/step-up, and other policy decisions.
5. `verifiedAuthorities` are generated from server-side `account.roles()`. Never copy `request.getAuthorities()`; never accept roles declared in forms/cookies/headers.
6. `VerifiedPrincipal` uses the ID/username of the located `account`, rather than merely echoing what the user typed. Passwords and passwordHash do not become attributes of the principal.
7. The `UsernamePasswordAuthenticationToken.authenticated(principal, null, authorities)` factory returns an authenticated token. Setting credentials to `null` avoids keeping the raw password in the result. `ProviderManager` also has post-authentication credential erasure, but you should avoid putting sensitive data into the principal in the first place.
8. The example intentionally does not copy `request.getDetails()`. If you need IP, session ID, or metadata for auditing, evaluate its source and sensitivity; `details` is auxiliary metadata, not proof for granting permissions.

**Note on verifying non-existent accounts:** the example throws the same `Invalid credentials` message whether the username does not exist or the password is wrong. In production, timing differences between the two branches can leak whether a username exists; consider dummy password hash verification, rate limiting, monitoring, and anti-enumeration policies. Do not expose internal causes in login responses.

### 4.5. Registering the Provider in SecurityFilterChain

**`src/main/java/example/providerresult/SecurityConfig.java`**

```java
package example.providerresult;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountDirectory accountDirectory(PasswordEncoder encoder) {
        return new InMemoryAccountDirectory(encoder);
    }

    @Bean
    AccountAuthenticationProvider accountAuthenticationProvider(
            AccountDirectory accounts, PasswordEncoder encoder) {
        return new AccountAuthenticationProvider(accounts, encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountAuthenticationProvider provider)
            throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll());

        // CSRF is kept at default for form login using session cookies.
        return http.build();
    }
}
```

`http.authenticationProvider(provider)` puts the custom provider into this chain's flow. `formLogin(...)` uses Spring Security's filters, session strategy, context persistence, and success/failure handlers; the provider only returns the authentication object. In applications with multiple providers/chains, check registration ordering and scope so you do not accidentally establish an unintended authentication mechanism.

**`src/main/java/example/providerresult/IdentityController.java`**

```java
package example.providerresult;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        VerifiedPrincipal user =
            (VerifiedPrincipal) authentication.getPrincipal();
        return user.accountId() + ":" + user.getName();
    }

    @GetMapping("/admin")
    String adminArea() {
        return "admin-area";
    }
}
```

After logging in successfully as `alice`, `GET /me` returns:

```text
acct-101:alice
```

`GET /admin` returns `403` for `alice`, but succeeds for the `admin` account because only `admin` has the verified `ROLE_ADMIN` authority. Logging in with the wrong password does not yield a “low-privilege” token: it is an **authentication failure**.

## 5. Testing: Verify Both the Returned Object and the HTTP Path

Directly testing `AuthenticationProvider` verifies the `Authentication` return contract. `MockMvc` integration tests verify that form login consumes this result and authorization actually enforces the right permissions.

**`src/test/java/example/providerresult/AccountAuthenticationProviderTest.java`**

```java
package example.providerresult;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import jakarta.servlet.http.HttpSession;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AccountAuthenticationProviderTest {

    @Autowired
    AccountAuthenticationProvider provider;

    @Autowired
    MockMvc mvc;

    private static Set<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void successReturnsVerifiedPrincipalAndServerAuthorities() {
        Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice-pass");

        assertFalse(input.isAuthenticated());

        Authentication result = provider.authenticate(input);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertInstanceOf(VerifiedPrincipal.class, result.getPrincipal());
        VerifiedPrincipal principal = (VerifiedPrincipal) result.getPrincipal();
        assertEquals("acct-101", principal.accountId());
        assertEquals("alice", principal.username());
        assertEquals("alice", result.getName());
        assertNull(result.getCredentials());
        assertEquals(Set.of("ROLE_USER"), authorities(result));
    }

    @Test
    void rejectsWrongPasswordAndUnknownAccount() {
        assertThrows(BadCredentialsException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong")));

        assertThrows(BadCredentialsException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "no-such-user", "any-password")));
    }

    @Test
    void disabledAccountDoesNotReceiveAuthenticatedResult() {
        assertThrows(DisabledException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "disabled", "disabled-pass")));
    }

    @Test
    void inboundClaimedAuthorityIsNotTrusted() {
        // Intentionally construct a forged token ONLY in unit tests.
        // The application must never accept this token from a request.
        Authentication forged = new UsernamePasswordAuthenticationToken(
            "alice", "alice-pass",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

        Authentication result = provider.authenticate(forged);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals(Set.of("ROLE_USER"), authorities(result));
        assertFalse(authorities(result).contains("ROLE_ADMIN"));
    }

    @Test
    void supportsOnlyUsernamePasswordTokens() {
        assertTrue(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(
            AnonymousAuthenticationToken.class));
    }

    @Test
    void formLoginPersistsTrustedPrincipalAndRejectsAdminAccess()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession rawSession = login.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("acct-101:alice"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void verifiedAdminRolePermitsAdminResource() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "admin")
                .param("password", "admin-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("admin"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-area"));
    }

    @Test
    void csrfStillAppliesToFormLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
```

Run from the example application directory containing the Gradle wrapper:

```bash
./gradlew test --tests example.providerresult.AccountAuthenticationProviderTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. The test suite above has **8 `@Test` methods**. When properly configured in a working environment, all should pass; this is the designed behavior in the example, **not executed test results**.

### Why Are Both Kinds of Tests Needed?

- Unit-style tests calling `provider.authenticate(...)` check the **returned object**: `isAuthenticated()`, principal type, ID/name, `null` credentials, and exact authorities. They do not need to execute HTTP requests.
- Negative tests ensure wrong passwords, nonexistent accounts, and disabled accounts cannot receive an authenticated token. The test building a “forged-authority” token is strictly a unit-test scenario to verify the provider **does not copy** input authorities.
- MockMvc tests perform `POST /login` with a password and CSRF token, then use the newly created session to call `GET /me` and `GET /admin`. `alice` getting `403` on `/admin` while `admin` gets `200` proves authorization receives the right authorities after authentication.
- `authenticated().withUsername(...)` is a matcher observing real login outcomes. **Do not use `@WithMockUser` to prove a provider flow**, because that utility places a mock user into SecurityContext and bypasses provider credential verification.

### Boundaries of These Tests

This is a Spring MVC + Spring Security example and does not fully simulate a distributed session store, real browser cookies, reverse proxies, or MFA flows. MockMvc tests show Spring Security behavior on a mock server; end-to-end HTTP testing is needed for deployment. When using a real repository/database, add tests confirming that updated roles in the authoritative source take effect per policy (reauthentication, refresh, or session revocation).

## 6. Critical Mistakes When Constructing the Authentication Result

| Mistake | Why it is dangerous or incorrect | What to do |
| --- | --- | --- |
| `return UsernamePasswordAuthenticationToken.authenticated(request.getPrincipal(), request.getCredentials(), request.getAuthorities());` right upon receiving the request | “Legitimizes” an unverified username, password, and authorities | Only create an authenticated token **after** checking credentials and server authorities |
| Setting `isAuthenticated=true` just because the username was found | Knowing a username exists does not prove the sender owns the account | Verify password/MFA/authentication policy first |
| Copying `ROLE_ADMIN` from JSON, headers, or an inbound token | Clients can elevate their own privileges | Retrieve roles/permissions from a trusted database/IdP and apply granting policies |
| Returning `UsernamePasswordAuthenticationToken.unauthenticated(...)` as a successful result | The token remains an unauthenticated request; filters/authorization cannot treat login as complete | Use the `authenticated(...)` factory after verification |
| Returning an entity containing `passwordHash` as the principal | Can keep secrets in SecurityContext/session/logs | Create a minimal, immutable principal without credentials |
| Returning the raw password in `getCredentials()` | Credentials can linger in memory, sessions, or logs | Set `null` in the successful token and use appropriate credential erasure |
| Returning `null` when the password is wrong | ProviderManager may try another provider; confuses “unsupported” with “invalid evidence” | Throw `BadCredentialsException` for failures handled by the provider |
| Throwing `BadCredentialsException` for every token type | Blocks other mechanisms even when the provider has no responsibility | Implement `supports(...)` accurately; return `null` when the token type is out of scope |
| Assigning every account `ROLE_ADMIN` to simplify a demo | Authorization no longer checks permissions accurately | Map authorities from verified data and test `403`/`200` |
| Using `hasRole("ROLE_ADMIN")` as an already-prefixed string | By default `hasRole("ADMIN")` adds `ROLE_` itself and may cause confusion/misconfiguration | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Writing to `SecurityContextHolder` inside the provider and assuming it is persisted | The provider can be called outside HTTP; the context is bound only to the request/thread | Let the login mechanism handle it; custom controllers must call `saveContext` properly |
| Logging raw passwords, hashes, or session IDs in debug logs | Exposes credentials, risking account/session takeover | Log minimal audit info with no secrets; redact logs/tracing |

### Should Request Details Be Preserved in the Returned Authentication?

In some flows, `request.getDetails()` contains `WebAuthenticationDetails` such as remote address and session ID. If policy requires it for auditing, you may consider `result.setDetails(request.getDetails())` on `UsernamePasswordAuthenticationToken`. However, **details must never be used as authorities or principal**, and you should avoid accidentally logging session IDs, credentials, or sensitive info. The example intentionally omits it to emphasize the verified principal and authorities.

### What If Permissions Change After Login?

`Authentication.getAuthorities()` is a snapshot of permissions at the time the token was created. If a user's roles change in the database after login, an active session may still hold the old authorities. That does **not** prove the provider was wrong at login time; the application needs an explicit mechanism to refresh, reauthenticate, revoke sessions, or check permissions dynamically at access time. Never silently use client-sent roles to “update” them.

### Password Hashes and Timing Signals

`PasswordEncoder.matches(raw, encoded)` is Spring Security's API for verifying passwords. Do not compare a raw password with a stored hash using `equals`; do not call `encoder.encode(raw).equals(storedHash)` with BCrypt because hashes are salted. For nonexistent usernames, the example returns the same `Invalid credentials` message without equalizing processing time; real systems must evaluate account enumeration risk, dummy hash verification, and rate limiting.

## 7. How to Observe Behavior When Running the Application

With the local app running on `http://localhost:8080`, open `/login` in a browser. Enter `alice` / `alice-pass`, then visit `/me`. The result is `acct-101:alice`; accessing `/admin` is denied. Log out, log in with `admin` / `admin-pass`, then visit `/admin`; the result is `admin-area`.

In DevTools Network, take care not to collect or share real passwords, CSRF tokens, or session cookies. In production, always use HTTPS and secure cookie/session settings; the localhost demo only helps observe provider logic.

Safe way to inspect state mentally or in debug/logs when investigating:

```text
Before: UsernamePasswordAuthenticationToken
        authenticated=false
        principal="alice" (user input)
        authorities=[]
After:  UsernamePasswordAuthenticationToken
        authenticated=true
        principal=VerifiedPrincipal(accountId=acct-101, username=alice)
        credentials=null
        authorities=[ROLE_USER]
```

This is a **state interpretation pattern**, not stdout/logs automatically printed by the example code. Do not print actual request tokens containing credentials; use assertions in tests to verify.

## 8. Self-Assessment Checklist

- [ ] `supports(...)` accepts only the `Authentication` type the provider actually handles.
- [ ] Account records are retrieved from a server-controlled source; never trust client-submitted usernames alone.
- [ ] Credentials are verified using an appropriate API (`PasswordEncoder.matches` in the example).
- [ ] Account status is checked before creating an authenticated token.
- [ ] The returned `Authentication` has `isAuthenticated() == true` **only when** verification succeeds.
- [ ] `principal` contains the identity of the exact verified record; contains no password/hash.
- [ ] `getCredentials() == null` after successful authentication in the example.
- [ ] `getAuthorities()` contains only authorities mapped from a trusted source, following prefix rules.
- [ ] Wrong passwords, nonexistent accounts, or disabled accounts never return a successful token.
- [ ] Input tokens carrying forged authority claims cannot affect the resulting authorities.
- [ ] Form login actually passes through the provider; subsequent requests are authorized by verified permissions.
- [ ] Responsibilities of `AuthenticationProvider` are clearly separated from `SecurityContextHolder`, `SecurityContextRepository`, and session persistence.
- [ ] `403`/`200` authorization cases are tested, and CSRF is kept enabled for stateful form login.

### Official References for Cross-Checking

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — Authorization Architecture / GrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
