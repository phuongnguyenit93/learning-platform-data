# UsernamePasswordAuthenticationToken Before and After Authentication

> **Key idea:** `UsernamePasswordAuthenticationToken` can represent either an **unverified login request** or a **successful authentication result**. Before authentication, the token typically carries user-supplied username/password, `isAuthenticated() == false`, and no trusted permissions. After `AuthenticationManager` and `AuthenticationProvider` verify credentials, the result typically carries a `UserDetails` principal, a set of `GrantedAuthority` values from a trusted source, and `isAuthenticated() == true`. `ProviderManager` by default attempts to erase sensitive credential information from the result. Most importantly: **constructing a token with the flag set to true does not mean the password has been verified**.

This lesson is part of the **Identity** group in the **Spring Security – fundamentals** module, covering Spring Security 6.5 on **Servlet/Spring MVC** applications, Java 17, and Spring Boot 3.5.16. In WebFlux and in OAuth2/JWT, the "request → verify → current identity" concept still holds, though the `Authentication` type, reactive APIs, and context propagation mechanisms differ. The sample accounts/passwords are for local practice only.

## 1. Learning Objectives

You will be able to:

1. Distinguish a token **requesting authentication** from an **authenticated** token based on `principal`, `credentials`, `authorities`, and `isAuthenticated()`.
2. Know when to use `UsernamePasswordAuthenticationToken.unauthenticated(...)` and understand why `authenticated(...)` is reserved for code that already holds trusted authentication proof.
3. Describe the flow from `UsernamePasswordAuthenticationFilter`/`BasicAuthenticationFilter` to `AuthenticationManager`, `ProviderManager`, `DaoAuthenticationProvider`, `UserDetailsService`, and `PasswordEncoder`.
4. Understand why `AuthenticationManager.authenticate(...)` **returns** a verified authentication but **does not automatically save the result into `SecurityContextHolder`** when you call the manager directly outside a filter.
5. Explain what `CredentialsContainer.eraseCredentials()` does, why `getCredentials()` can become `null`, and why credentials must never be logged.
6. Run a Spring Boot demo with BCrypt-hashed in-memory users and a test suite checking tokens, valid/wrong passwords, HTTP statuses, roles, and CSRF.
7. Recognize token-usage patterns that cause privilege escalation: copying authorities from the request body, using the three-argument constructor unverified, or placing a self-built authentication into the context and bypassing providers.

## 2. Small Map: Authentication Is One Interface with Two Roles

In Spring Security, `Authentication` does not only mean "logged-in user". It is also the **object carrying an authentication request to an `AuthenticationManager`**.

```text
User/client sends username + password
                |
                v
UsernamePasswordAuthenticationToken.unauthenticated(...)
  - principal     = "alice" (client-supplied String)
  - credentials   = submitted password
  - authorities   = [] (no trusted permissions granted yet)
  - authenticated = false
                |
                v
AuthenticationManager.authenticate(request)
                |
                v
ProviderManager selects a matching AuthenticationProvider
                |
                v
DaoAuthenticationProvider
  -> UserDetailsService.loadUserByUsername("alice")
  -> PasswordEncoder.matches(rawPassword, storedHash)
  -> account checks per provider (enabled, locked, ...)
                |
           +----+----+
           |         |
        FAILURE   SUCCESS
           |         |
      Exception      v
      (no access  Result UsernamePasswordAuthenticationToken
       granted)     - principal     = Alice's UserDetails
                    - authorities   = [ROLE_USER, NOTES_WRITE]
                    - authenticated = true
                    - credentials   = typically null after erase
                           |
                           v
                  Filter attaches result to SecurityContext
                           |
                           v
                 Authorization + Controller/Service
```

This is the **username/password flow with `DaoAuthenticationProvider`**. Not every system uses this provider. Applications using JWT may receive `JwtAuthenticationToken`; applications using OIDC may receive `OAuth2AuthenticationToken`. Therefore, token types must be understood according to the **actual authentication mechanism**.

Important distinctions:

- **Authentication request:** "I claim I am Alice, and here are the credentials I submit for verification."
- **Authenticated result:** "The system checked via a trusted provider; here are the identity and permissions policy allows."
- **SecurityContext:** where the current execution flow holds the authentication accessed by filters/controllers/services.
- **Authorization:** the subsequent decision on whether Alice may view/edit a specific object; successful login alone is not enough to bypass all rules.

## 3. What Class Is UsernamePasswordAuthenticationToken?

`UsernamePasswordAuthenticationToken` belongs to:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
```

It extends `AbstractAuthenticationToken` and implements `Authentication` and `CredentialsContainer`. Key properties across the API:

| Property/method | Before authentication | After provider succeeds |
| --- | --- | --- |
| `getPrincipal()` | Usually a `String` username, not yet proved | With `DaoAuthenticationProvider`, usually the loaded `UserDetails` |
| `getName()` | May already return the client-claimed username | Usually the username/identity from the authenticated principal |
| `getCredentials()` | User-entered password, potentially the raw password | May be `null` after the manager erases credentials |
| `getAuthorities()` | Normally empty | Authorities/roles verified and returned by the provider |
| `isAuthenticated()` | `false` | `true` |
| `getDetails()` | Metadata depending on filter/request, may be null | May be forwarded depending on provider/filter |
| `eraseCredentials()` | Can clear sensitive info inside the token | Used to shorten credential lifetime in memory |

**Pay attention to the word "usually".** The API allows principal and credentials to have type `Object`; a custom provider can return different types, different properties, or not erase credentials. A result from `DaoAuthenticationProvider` through `ProviderManager` with default credential erasure differs from a token manually constructed by a developer. Do not rely on `getCredentials()` always being null as a security check; the security guarantee is the **trusted authentication path** producing the result.

### 3.1. Two Most Readable Factory Methods

Spring Security 6.x provides:

```java
UsernamePasswordAuthenticationToken request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-submitted-by-user");
```

The token above has `isAuthenticated() == false` and is not yet considered valid access. It is **input data** to submit to `AuthenticationManager`. Do not put this object directly into `SecurityContextHolder` and grant permissions.

After the provider actually verifies the password, trusted code can create the result via another constructor/factory:

```java
// ILLUSTRATION ONLY INSIDE A TRUSTED AUTHENTICATION PROVIDER.
// Never call using role input sent by the client.
UsernamePasswordAuthenticationToken trusted =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedUserDetails,
        null,
        verifiedAuthorities
    );
```

In the second snippet, `verifiedUserDetails` and `verifiedAuthorities` are variables already present **within the provider's scope**, built from verified evidence. The `authenticated(...)` factory **does not call PasswordEncoder or query the database**; it merely constructs an object with the authenticated flag set to true. If a controller reads `authorities` from JSON and calls this factory, the backend can grant forged permissions to an attacker.

**Two corresponding constructors:**

```java
// Unauthenticated input: flag false.
new UsernamePasswordAuthenticationToken(username, password);

// Trusted result: flag true. Use only in verified code.
new UsernamePasswordAuthenticationToken(
    verifiedPrincipal, null, trustedAuthorities);
```

Factory methods express intent more clearly: `unauthenticated(...)` for requests, `authenticated(...)` for results decided by a trusted system. Both styles are supported by Spring Security; method names alone cannot replace the real authentication process.

### 3.2. Why Not Call setAuthenticated(true)?

`UsernamePasswordAuthenticationToken` has the `setAuthenticated(boolean)` API inherited from the `Authentication` interface. This implementation **disallows** simply flipping an unauthenticated token to trusted via `setAuthenticated(true)`; doing so throws `IllegalArgumentException`. It allows setting `false` to mark it as no longer trusted.

```java
UsernamePasswordAuthenticationToken pending =
    UsernamePasswordAuthenticationToken.unauthenticated("alice", "pw");

// pending.setAuthenticated(true) => IllegalArgumentException.
pending.setAuthenticated(false); // supported, still untrusted
```

However, this **does not prevent** application code from calling the three-argument constructor or `authenticated(...)` to create an object with flag true. Security cannot verify the validity of code running with the server's own privileges; developers must guard the trust boundary and construct trusted results only after provider verification.

### 3.3. getName() Before Authentication Is Not Yet a Trusted Identity

Even when only a request token exists:

```java
UsernamePasswordAuthenticationToken pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "admin", "wrong-password");

// pending.getName() may already be "admin".
// pending.isAuthenticated() is false.
```

If code logs `pending.getName()` and claims "admin logged in", that is the mistake of **confusing a client-claimed name with an authenticated identity**. To know whether a user is allowed to act, policies must use the authentication verified by the framework/provider, never the raw token from a form.

## 4. How AuthenticationManager and DaoAuthenticationProvider Turn Input into Result

### 4.1. What Does AuthenticationManager Do?

`AuthenticationManager` has the core contract:

```java
Authentication verified = authenticationManager.authenticate(pending);
```

When successful, it returns a trusted `Authentication`. If credentials are wrong, the account is invalid, no provider supports the token, or an authentication error occurs, it throws an appropriate `AuthenticationException`. **There is no rule that it always returns null on bad login.** On error paths, never fabricate a "good enough result" to let the request proceed.

In many setups, the manager is `ProviderManager`. It consults configured `AuthenticationProvider` instances in turn, finds a provider capable of handling the token type, and uses the accepted result. A provider that does not support the token type can decline by returning null so another provider is tried. This enables an application to support multiple authentication mechanisms, though provider ordering and scope must be designed carefully.

### 4.2. What Does DaoAuthenticationProvider Do?

With traditional username/password:

1. `DaoAuthenticationProvider` receives an unauthenticated `UsernamePasswordAuthenticationToken`.
2. Calls `UserDetailsService.loadUserByUsername(username)` to look up the account from a trusted source (memory/database/service).
3. `UserDetails` holds username, password hash, authorities, and account status flags.
4. Uses `PasswordEncoder.matches(rawPassword, encodedPassword)` to compare, **never decrypting the hash to plaintext**.
5. Checks applicable account statuses (locked, disabled, expired, ...), per provider design.
6. If valid, the provider builds a successful authentication with trusted principal/authorities and returns it to the manager.
7. `ProviderManager` by default erases credentials on the result when possible and returns the result to the caller.

**Do not confuse `UserDetailsService` with a password checker.** `UserDetailsService` primarily loads user data; `PasswordEncoder`/provider verifies passwords. Likewise, do not take authorities from the client-submitted input token: the system must derive permissions from a trusted store or verified claims mechanism.

### 4.3. Before/After Table for the Same Username

| Step | Principal | Credentials | Authorities | Authenticated |
| --- | --- | --- | --- | --- |
| Client sends form/Basic | `"alice"` (claim) | Submitted password | No trusted permissions | Not authenticated |
| Filter creates request token | `"alice"` | Raw password inside input token | `[]` | `false` |
| Manager/provider looks up user | Loaded `UserDetails("alice")` | Password matched against BCrypt hash | Permissions loaded from user store | Processing |
| Manager returns result | `UserDetails("alice")` | Usually erased, becoming `null` | E.g. `ROLE_USER`, `NOTES_WRITE` | `true` |
| Filter places into context | Result Authentication | No need to keep raw password | Permissions ready for HTTP/method rules | Scoped to current request |
| Request completes | Depends on session/repository or re-auth on next request | Should not store plaintext | Permissions have separate validity/revocation policy | Thread context cleared per lifecycle |

The transition is not an arbitrary "flip false bit to true" on one object. In the standard flow with `DaoAuthenticationProvider`, the manager **returns a result object** built from trusted sources. Do not depend on `pending == verified`; use the value returned by the manager.

## 5. Filter Creates the Token Before, Who Puts the Token After into SecurityContext?

### 5.1. With Form Login

```text
POST /login (username, password, csrf...)
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
UsernamePasswordAuthenticationToken.unauthenticated(...)
      |
      v
AuthenticationManager / ProviderManager
      |
      v
DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
      |
      +-- Wrong credentials -> failure handler / clear context / reject
      |
      +-- Valid -> authenticated Authentication
                          |
                          v
                Filter attaches to SecurityContext
                and handles persistence if using session
                          |
                          v
                   Success handler / redirect
```

`UsernamePasswordAuthenticationFilter` is commonly used in Servlet form login. It extracts username/password from the HTTP request, builds the initial token, delegates verification to the manager, and handles success/failure. Depending on configuration, session authentication strategy, remember-me, CSRF, login success handlers, and `SecurityContextRepository` may participate. **`AuthenticationManager.authenticate(...)` by itself does not perform all these HTTP steps**.

### 5.2. With HTTP Basic

```text
Authorization: Basic <base64(username:password)>
      |
      v
BasicAuthenticationFilter
      |
      v
UsernamePasswordAuthenticationToken request
      |
      v
AuthenticationManager -> provider -> Authentication result
      |
      v
Request's SecurityContext
      |
      v
AuthorizationFilter -> Controller / Service
```

Basic Auth only Base64-encodes credentials in the header; it **does not encrypt secrets over the network**. For clients outside localhost, HTTPS is mandatory. In stateless API applications, each request typically brings its own credentials; the context is created and cleared per request, with no "Java token" living forever across all requests.

### 5.3. Calling manager.authenticate Yourself Outside a Filter

Suppose a test or service calls:

```java
Authentication verified =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "demo-pass"));
```

The `verified` result is a checked authentication, **yet `SecurityContextHolder` is not automatically populated** merely because you called the manager. If code you manage truly needs the result as the current authentication, you must set the context in the appropriate scope, for example in an illustrative snippet **inside a safely designed flow**:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
```

Putting it into the holder only serves currently running code and does not create persistence across requests. In Spring Security 6, custom login must use `SecurityContextRepository.saveContext(context, request, response)` when saving authentication into a session is required; at the same time, session fixation protection, CSRF, logout, failure handling, and context lifecycle must be designed. **Do not use this snippet as a DIY login endpoint** without properly handling all those steps. When managing the context manually outside a filter, clear it in a `finally` block.

### 5.4. SecurityContextHolder Is Not a Place to "Store Passwords"

`SecurityContextHolder` normally accesses the current Servlet thread's `SecurityContext` (`ThreadLocal` by default). It allows rules/controllers/services to read the authenticated principal. It is **not** a user database, password vault, or HTTP session. A session can store a security context through a repository; in a stateless API, each new request typically re-authenticates credentials/tokens.

Do not attach a `UsernamePasswordAuthenticationToken` with a raw password to the session just to "avoid logging in again". Use Spring Security's supported login/session mechanisms or standard identity protocols with proper credential-lifetime policies.

## 6. How Are Credentials Erased?

`UsernamePasswordAuthenticationToken` implements `CredentialsContainer`. When `eraseCredentials()` runs:

- Direct credentials on the token can be cleared (set to null).
- `AbstractAuthenticationToken` also calls `eraseCredentials()` on the principal and details if those objects implement `CredentialsContainer`.
- `ProviderManager` enables `eraseCredentialsAfterAuthentication` by default and invokes the erasure method on successful authentications when possible.

Therefore, in the example using `DaoAuthenticationProvider` and default `ProviderManager`, after authentication you will typically see `verified.getCredentials() == null`. This is a **sign of sensitive-data erasure**, not "wrong password" or "lost identity": principal and authorities remain usable for authorization.

**A deeper note on caching:** If the result holds the exact reference to a cached `UserDetails` and erasure runs on the principal, the password field inside the cached object can also be cleared. Subsequent logins will fail to match the password if the cache retains that mutated object. Design caches with proper defensive copies or sound password-hash storage rather than hastily disabling credential erasure.

**Never:**

- Return `getCredentials()` or the entire `Authentication` as JSON to a client.
- Write plaintext passwords, Basic headers, tokens, refresh tokens, or session cookies into logs or metric labels.
- Add raw passwords to `getDetails()`, custom principals, or exception messages.
- Treat "credentials erased" as solid proof the authentication provider was used properly; custom token-creation code can pass null credentials without ever checking a password.

The right way to observe this is to assert flags, principal types, authorities, and `getCredentials()` in **tests**, not by logging secrets on the server.

## 7. Complete Demo: Java 17, Spring Boot 3.5.16, Real Authentication via Provider

The demo provides **a Spring Boot Servlet app** with explicit configuration:

- `AuthenticationManager` is a `ProviderManager` containing `DaoAuthenticationProvider`.
- In-memory `UserDetailsService` with BCrypt-encoded passwords.
- `UsernamePasswordAuthenticationToken.unauthenticated(...)` is used in tests for the pre-authentication stage.
- `AuthenticationManager.authenticate(...)` returns a result token with trusted principal/authorities.
- HTTP Basic filter uses the same manager to protect `/me`, `/admin`, and `POST /notes`.
- `SessionCreationPolicy.STATELESS` demonstrates not persisting login across requests; CSRF stays enabled to test POST separately.

**Versions:** Java 17+, Spring Boot `3.5.16`, Spring Security 6.5.x from the Boot BOM. Spring Boot 3.5.16 was released on June 25, 2026 and is the final OSS release in the 3.5 line; new production deployments in 2026 should choose a supported Boot 4.x line, apply patches, and follow its corresponding API docs. User/password data in this lesson is for local use only.

### 7.1. Structure

```text
username-password-token-demo/
├── pom.xml
└── src/
    ├── main/java/demo/token/PasswordTokenApplication.java
    └── test/java/demo/token/PasswordTokenApplicationTests.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>username-password-token-demo</artifactId>
    <version>1.0.0</version>
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
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Application Java Code

Create `src/main/java/demo/token/PasswordTokenApplication.java`:

```java
package demo.token;

import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordTokenApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordTokenApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class PasswordTokenSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // ProviderManager erases credentials on success by default.
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            AuthenticationManager authenticationManager)
            throws Exception {

        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF enabled, separate from authentication.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    MeView me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        // Do not expose raw Authentication, principal, or credentials in JSON.
        return new MeView(auth.getName(), authorities);
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }

    @PostMapping("/notes")
    String createNote(Authentication auth) {
        // Demo: no DB write; illustrates operation permission only.
        return "created:" + auth.getName();
    }
}

record MeView(String name, List<String> authorities) {}
```

**Reading the code along the path:**

1. `UserDetailsService` supplies two test accounts from a server source. `encoder.encode("demo-pass")` generates BCrypt hashes; the provider verifies with `matches`, never comparing plaintext directly against a hash.
2. `DaoAuthenticationProvider` specifically handles username/password. `ProviderManager` is the manager receiving request tokens and returning a successful result or throwing an authentication exception.
3. `HttpSecurity.authenticationManager(authenticationManager)` explicitly binds this manager to the chain, so the HTTP Basic filter and direct tests use the exact same authentication path. This avoids the misunderstanding of merely "simulating" tokens in tests unrelated to the HTTP filter.
4. `SecurityFilterChain` is the request boundary; `GET /me` requires authenticated, `GET /admin` requires `ROLE_ADMIN`, `POST /notes` requires `NOTES_WRITE` and a valid CSRF token.
5. `SessionCreationPolicy.STATELESS` ensures the app does not use HTTP sessions to carry security context between requests under a stateless policy. Each Basic request must bring credentials to be verified.
6. The `/me` endpoint serializes only name and authorities. It does not reveal raw passwords, hashes, or erased credentials.
7. `DispatcherType.ERROR` allows the servlet container's error dispatch to render responses when needed; the initial request remains subject to the chain's rules.

**Security note:** Do not use in-memory users or hard-coded passwords like this in production. Basic Auth does not encrypt passwords without HTTPS. In real APIs, choose an appropriate identity provider/credential policy, protect credentials in a secret store, and apply login throttling, rate limiting, and auditing as needed.

### 7.4. Testing Before and After Authentication, Plus Real HTTP Requests Through the Filter

Create `src/test/java/demo/token/PasswordTokenApplicationTests.java`:

```java
package demo.token;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordTokenApplicationTests {

    @Autowired
    AuthenticationManager authenticationManager;

    @Autowired
    MockMvc mvc;

    @BeforeEach
    void clearBeforeTest() {
        SecurityContextHolder.clearContext();
    }

    @AfterEach
    void clearAfterTest() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void requestTokenIsNotYetAuthenticated() {
        UsernamePasswordAuthenticationToken pending =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");

        assertFalse(pending.isAuthenticated());
        assertEquals("alice", pending.getPrincipal());
        assertEquals("alice", pending.getName());
        assertEquals("demo-pass", pending.getCredentials());
        assertTrue(pending.getAuthorities().isEmpty());

        // Cannot turn input token into trusted via setter.
        assertThrows(IllegalArgumentException.class,
            () -> pending.setAuthenticated(true));

        // Nobody has placed an authentication into the current context yet.
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void providerReturnsVerifiedTokenWithTrustedAuthorities() {
        UsernamePasswordAuthenticationToken pending =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");

        Authentication verified =
            authenticationManager.authenticate(pending);

        assertTrue(verified.isAuthenticated());
        assertInstanceOf(
            UsernamePasswordAuthenticationToken.class, verified);

        // DaoAuthenticationProvider loads UserDetails from the user store.
        UserDetails principal =
            assertInstanceOf(UserDetails.class, verified.getPrincipal());

        assertEquals("alice", principal.getUsername());
        assertEquals("alice", verified.getName());

        List<String> authorities = verified.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("NOTES_WRITE", "ROLE_USER"), authorities);

        // ProviderManager erases credentials on the result by default.
        assertNull(verified.getCredentials());

        // Manager.authenticate returns the result; does not auto-install into holder.
        assertNull(SecurityContextHolder.getContext().getAuthentication());

        // Only after explicitly attaching to current context does identity appear.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        assertEquals("alice",
            SecurityContextHolder.getContext()
                .getAuthentication().getName());
    }

    @Test
    void wrongPasswordNeverCreatesAnAuthenticatedResult() {
        UsernamePasswordAuthenticationToken wrong =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "not-the-password");

        assertThrows(BadCredentialsException.class,
            () -> authenticationManager.authenticate(wrong));

        assertFalse(wrong.isAuthenticated());
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void basicFilterUsesVerifiedPrincipalOnEveryRequest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("NOTES_WRITE"))
            .andExpect(jsonPath("$.authorities[1]")
                .value("ROLE_USER"));

        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        // Admin has role, Alice lacks role.
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Successful authentication does not replace CSRF protection.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:alice"));

        // Admin lacks NOTES_WRITE even with a valid CSRF token.
        mvc.perform(post("/notes")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Stateless: next request without credentials does not reuse Alice.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Meaning of each test group:**

- `requestTokenIsNotYetAuthenticated` confirms the input token carries only a claim; `getName()` can be "alice" even before verification, while `isAuthenticated` is false.
- `providerReturnsVerifiedTokenWithTrustedAuthorities` uses the **real manager/provider**, verifying the `UserDetails` principal, authorities from the user store, credential erasure, and the "manager does not auto-set context" behavior.
- `wrongPasswordNeverCreatesAnAuthenticatedResult` confirms bad credentials throw `BadCredentialsException`; no authenticated token is returned to "keep going".
- `basicFilterUsesVerifiedPrincipalOnEveryRequest` passes through Spring Security's HTTP Basic filter via MockMvc, checking 200/401/403, roles, and CSRF, while proving subsequent requests do not inherit identity from earlier ones.
- `httpBasic("alice", "demo-pass")` sends credentials like a real client in the test; by contrast `@WithMockUser`/`user()` creates a simulated principal to test authorization **without checking passwords**.
- `@BeforeEach` and `@AfterEach` clear `SecurityContextHolder` because the test deliberately sets context manually; in production, let Spring Security filters manage the per-request lifecycle.

### 7.5. Running Tests and Running the Server

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Test expectations:** `mvn test` completes when assertions match Spring Security 6.5/Boot 3.5 and dependencies download successfully. The demo describes expected outcomes, not claiming these logs were run on your machine. Do not treat stdout text or log line ordering as mandatory parts of a test.

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u admin http://localhost:8080/admin
curl -i -u alice http://localhost:8080/admin
```

When curl prompts for the local account password, enter `demo-pass`. Expected results:

| Command | HTTP status | Description |
| --- | --- | --- |
| `GET /public` without credentials | 200 | Public |
| `GET /me` without credentials | 401 | Basic authentication required |
| `GET /me` as valid Alice | 200 | JSON name `alice` and authorities |
| `GET /admin` as valid admin | 200 | Body `admin-ok` |
| `GET /admin` as valid Alice | 403 | Authenticated but missing `ROLE_ADMIN` |

**Do not try Basic Auth over plain HTTP on a real network**: the `localhost` URLs in the lab are illustrative only. In staging/production, HTTPS is required and hard-coded passwords must not be used. `POST /notes` requires a valid CSRF token under the current configuration; to demonstrate a positive POST, use the defined `MockMvc.with(csrf())` test rather than arbitrarily disabling CSRF.

## 8. Reading the Experiment Results: Why Can the Two Tokens Differ in Object and Data?

After running the tests, you can visualize:

```text
INPUT
  class         = UsernamePasswordAuthenticationToken
  principal     = String("alice")
  credentials   = raw password (DO NOT LOG REAL VALUES)
  authorities   = []
  authenticated = false

OUTPUT via ProviderManager/DaoAuthenticationProvider
  class         = UsernamePasswordAuthenticationToken
  principal     = UserDetails(username="alice", ...)
  credentials   = null [with default eraseCredentialsAfterAuthentication]
  authorities   = [NOTES_WRITE, ROLE_USER]
  authenticated = true
```

The lines above are **state descriptions for learning**, not a suggestion to log whole objects. Points to understand:

1. The class may **remain unchanged** along the username/password path; what changes are the authentication source, principal type, authority set, credentials, and flag.
2. `principal` changing from String to `UserDetails` is the outcome of `DaoAuthenticationProvider`; a custom provider may return a different principal.
3. `getName()` can match in both states, so you cannot use the username alone as proof of authentication.
4. `authorities` are the input evaluated by rules like `hasAuthority("NOTES_WRITE")` or `hasRole("ADMIN")`. They normally come from the user store, not a `roles` field in an HTTP body.
5. `credentials == null` on the result does not hinder authorization because permissions use principal and authorities, not re-checking passwords on every service line.
6. The manager does not decide resource ownership: if Alice has `NOTES_WRITE`, modifying Bob's note must still be blocked by owner/tenant/ACL checks in the service or repository.

## 9. When Authentication Fails

### 9.1. Wrong Password

`AuthenticationManager.authenticate(pending)` throws an exception, such as `BadCredentialsException`. In an HTTP Basic application, Spring Security returns a `401` challenge response depending on the entry point. Do not construct an authentication with `true` and empty authorities and treat it as a "restricted successful login". A locked/expired account can throw a different exception per provider policy.

### 9.2. Non-Existent Username

`UserDetailsService` can throw `UsernameNotFoundException`. `DaoAuthenticationProvider` by default hides the distinction so outsiders cannot probe which usernames exist; HTTP messages should avoid revealing which accounts are valid. Do not record raw passwords in exceptions or return stack traces with sensitive data.

### 9.3. No Provider Handles the Token

`ProviderManager` needs an `AuthenticationProvider` supporting the `Authentication` type. Passing a `JwtAuthenticationToken` to a manager that only has a username/password provider leaves the request unauthenticated and triggers an error like `ProviderNotFoundException`. That is not "wrong password"; it is a mismatched authentication-mechanism setup. Choose the right provider/decoder for each `SecurityFilterChain`.

### 9.4. Flag True Without Verification Evidence

This is a severe risk:

```java
// DANGEROUS ANTI-EXAMPLE — DO NOT USE.
Authentication fake =
    UsernamePasswordAuthenticationToken.authenticated(
        requestBody.getUsername(),
        null,
        List.of(new SimpleGrantedAuthority(
            requestBody.getRequestedRole())));
SecurityContextHolder.getContext().setAuthentication(fake);
```

This is a warning snippet; `requestBody`, imports, and the enclosing class are intentionally omitted. It **does not verify a password**; the role is trusted straight from the client. If that token is placed into the context before authorization, the app can grant unintended privileges. Always let a trusted authentication mechanism verify credentials or signatures/claims before accepting authorities.

## 10. Authentication vs. Authorization: A Logged-In Token Is Not Enough to Modify Data

Suppose Alice logs in properly and the result has:

```text
principal.name = alice
authorities    = [ROLE_USER, NOTES_WRITE]
authenticated  = true
```

Alice calls `PATCH /api/notes/42`, and in the database note 42 has `owner=bob`. `NOTES_WRITE` grants the **note-writing capability**, yet it does not prove Alice is allowed to edit **note 42**. Domain services must verify owner/tenant/note state before acting; transactions and conditional updates may also be needed to avoid race conditions.

```java
// Service snippet, not a complete program.
public Note updateNote(long id, EditNoteRequest request) {
    String actorId = currentUserProvider.currentUserId(); // from trusted identity
    Note note = repository.findByIdAndOwnerId(id, actorId)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));

    note.applyAllowedFields(request); // disallow changing owner/role directly
    return repository.save(note);
}
```

Takeaways:

- **Authentication** determines who is calling, based on a verified provider/decoder result.
- **HTTP authorization** determines the role/authority required for the method/path.
- **Object authorization** decides whether the actor may operate on this specific resource.
- **State validation** checks whether the action is allowed in the current state.

Never use an unverified `getName()` to set `ownerId`; never use authorities from the body; never update data before checking permissions.

## 11. Sessions, Statelessness, and Reusing Authentication

### 11.1. Form Login Using Sessions

After username/password authentication, the filter can save `SecurityContext` via `SecurityContextRepository`/HTTP session depending on configuration. Subsequent requests use the session cookie to restore the authenticated identity without resending the password on every URL. The `UsernamePasswordAuthenticationToken` stored in context may already have its credentials erased to minimize sensitive data in the session.

Do not confuse session restoration of `Authentication` with keeping **one Java object in ThreadLocal forever**. Different requests run on different threads; Spring Security loads/clears the holder according to the request lifecycle. Session revocation, logout, password changes, and role changes require appropriate validity/refresh policies.

### 11.2. Stateless HTTP Basic

In the demo, `SessionCreationPolicy.STATELESS` is intentional. Every new Basic request needs credentials; the filter builds a new request token, the provider verifies it, and produces a result for that request. If the following request omits the Basic header, it must not reuse Alice just because the prior request returned 200. This behavior should be tested, because leaking `SecurityContext` across threads/users causes severe vulnerabilities.

### 11.3. JWT and OAuth2 Do Not Necessarily Produce UsernamePasswordAuthenticationToken

Verified Bearer JWTs typically create `JwtAuthenticationToken`; OIDC login may use `OAuth2AuthenticationToken`; SAML has its own type as well. `getPrincipal()` is not always `UserDetails`; it can be `Jwt` or `OAuth2User`. Applying `UsernamePasswordAuthenticationToken` assumptions to all authentication mechanisms leads to `ClassCastException` and broken policies.

### 11.4. Background Jobs Do Not Automatically Keep Current Authentication

In Servlet stacks, `SecurityContextHolder` uses `ThreadLocal` by default. Moving into `@Async` or a thread pool does not safely carry context automatically in all cases. Use `DelegatingSecurityContextExecutor`/proper propagation or pass the verified actor as explicit data; for delayed jobs, also account for revoked permissions. Do not enable `MODE_GLOBAL` so all threads share one user.

## 12. Common Mistakes When Working with UsernamePasswordAuthenticationToken

| Mistake | Why it is dangerous/wrong | How to handle it |
| --- | --- | --- |
| Treating `getName() == "admin"` as authenticated | Before auth it can also be a client-claimed string | Check via manager/provider and trust boundary |
| Calling `authenticated(username, null, clientRoles)` straight in a controller | Self-grants permissions from client data without verification | Only trusted providers construct trusted results after authentication |
| Calling `setAuthenticated(true)` on a pending token | Implementation rejects with an exception; wrong flow | Use `AuthenticationManager.authenticate(...)` |
| Placing a pending token into `SecurityContext` | Leaves unverified identity in the current context | Only use a trusted authenticated result |
| Treating `getCredentials() == null` as valid password | Null could be set manually, proving nothing about a provider | Verify the flow through providers/tests |
| Logging the whole `Authentication` or raw passwords | Leaks secrets/principal details | Log minimally; mask credentials |
| Comparing raw password to BCrypt hash with `equals` | Cannot authenticate properly and breaks security | `PasswordEncoder.matches(raw, hash)` |
| Allowing client to send `ROLE_ADMIN` in the input token | Privilege escalation | Derive authorities solely from verified data/claims |
| Assuming `authenticate()` always populates context | Manager only returns the result | Filter/custom login flow manages holder and repository |
| Assuming `isAuthenticated()==true` proves human login | Anonymous tokens can also be true; trusted tokens can be forged in code | Use proper authorization policies and trust resolvers |
| Treating a role as ownership of every record | BOLA/IDOR | Enforce actor + action + resource/tenant policy |
| Disabling credential erasure because cache broke | Increases password exposure risk | Design cache copying and hash lifecycle properly |
| Casting `(UserDetails) auth.getPrincipal()` for all auth schemes | JWT/OIDC use different principal types | Handle principal per configured mechanism |
| Storing authentication in a singleton service field | Mixes identities across requests | Use scoped context or explicit actor |
| Setting context in a thread pool and forgetting cleanup | Leaks identity to other tasks | Use context propagation with explicit cleanup |

### 12.1. The isAuthenticated() Trap

In Spring Security Servlet with anonymous authentication enabled, `AnonymousAuthenticationToken` typically returns `isAuthenticated() == true` even though it does not represent a logged-in user. Therefore code like:

```java
if (auth != null && auth.isAuthenticated()) {
    allowSensitiveOperation();
}
```

is **insufficient** to protect sensitive operations. The example above is an anti-example (variables/methods omitted). Spring Security provides `authenticated()`, `fullyAuthenticated()`, and `AuthenticationTrustResolver` to distinguish anonymous/remember-me; authorities and resources must still be evaluated as well. In the demo, `HttpSecurity.authorizeHttpRequests(...authenticated())` is how Spring Security enforces this properly at the HTTP boundary.

### 12.2. Do Not Try to "Read the Pre-Auth Token" in a Controller After the Filter

Once a request reaches the `GET /me` controller in the demo, the authentication passed into the method is the **result already verified by the filter**, not the raw input token. To observe **before**, write a test that directly creates `unauthenticated(...)` and calls the manager; to observe **after** in a request, accept `Authentication` in a controller or read `SecurityContextHolder`. Do not set a breakpoint and conclude the same single token object flows unchanged through the entire pipeline.

## 13. Self-Assessment Exercises

**Exercise 1.** A token is created with `unauthenticated("alice", "pw")`. `getName()` returns `alice`. Do we know yet whether the password is correct?

**Answer:** No. The username is an input claim; `isAuthenticated()` is false. The token must be sent to the manager/provider and its result handled.

**Exercise 2.** `AuthenticationManager.authenticate(...)` returns a result with `isAuthenticated()==true` yet `getCredentials()==null`. Did login fail?

**Answer:** No. `ProviderManager` erases sensitive credentials by default after successful authentication. Authorization relies on the verified principal/authorities.

**Exercise 3.** A developer calls `UsernamePasswordAuthenticationToken.authenticated("admin", null, List.of(ROLE_ADMIN))` in a controller without checking any password, then sets it into `SecurityContext`. Can that bypass admin rules?

**Answer:** Very high risk. The factory merely creates an object marked trusted without verifying credentials. Never put client-controlled permission data into a token; use results only from a trusted authentication mechanism.

**Exercise 4.** Why does the provider return a `UserDetails` principal instead of a username string?

**Answer:** With `DaoAuthenticationProvider`, the user is loaded from `UserDetailsService` and the result typically retains the verified `UserDetails`, including username/authorities/account state. Other providers may choose different principals.

**Exercise 5.** If a test calls the manager directly and succeeds, why is `SecurityContextHolder.getContext().getAuthentication()` still null?

**Answer:** The manager only returns the result. Setting the context is the responsibility of a filter or custom login flow. If persisting a session across requests is needed, `SecurityContextRepository` and corresponding session protections are also involved.

**Exercise 6.** Alice has `NOTES_WRITE`. Is that sufficient grounds to edit Bob's note?

**Answer:** No. An authority is a feature-level permission; the service must check owner/tenant/ACL and data state.

**Exercise 7.** A `@WithMockUser("alice")` test passes; can we conclude the password `"demo-pass"` was verified by BCrypt?

**Answer:** No. `@WithMockUser` creates a simulated authentication. Only tests using `AuthenticationManager.authenticate(...)` or `httpBasic("alice", "demo-pass")` exercise the password provider path in the example.

**Exercise 8.** Should we always serialize `Authentication` back to the client so the frontend knows every permission?

**Answer:** No. It may contain principals/metadata/claims that should not be public. Design a minimal DTO from data permitted to be exposed; the server always remains the authority on permissions.

## 14. Checklist for Production Code

Before using `UsernamePasswordAuthenticationToken` in an application:

1. **Is the token an input or a result?** Is it created via `unauthenticated(...)` and passed to `AuthenticationManager.authenticate(...)`?
2. **Who verifies the credentials?** Do the provider/decoder have a clear data source, hash, account status checks, and trust boundary?
3. **Where do permissions come from?** Are authorities loaded from a verified user store/claims or from client JSON/headers?
4. **After auth, what is the principal type?** `UserDetails`, String, `Jwt`, `OAuth2User`? How does the domain obtain a stable user ID?
5. **Are credentials erased and kept out of logs?** Never return passwords, raw tokens, Basic headers, or cookies in responses/traces.
6. **Does the manager auto-set the context?** If writing custom login, are context setup, persistence, session fixation, CSRF, failure handling, and cleanup all handled properly?
7. **Session or stateless?** What authenticates subsequent requests? What happens when tokens/sessions expire or permissions are revoked?
8. **Is the HTTP policy explicit?** Are anonymous callers, wrong passwords, wrong roles, wrong methods, and missing CSRF rejected?
9. **Is the resource policy explicit?** Can a user invoke a feature without being able to access another user's or tenant's data?
10. **Do tests run through the real provider?** Are before/after states, wrong credentials, exact authorities, and credential erasure tested?
11. **Do tests run through the real filter?** Are there MockMvc/HTTP Basic integration tests covering 401, 403, 200, and cross-request isolation?
12. **Does custom code use the right APIs/versions?** Are Boot, Security, Servlet vs. WebFlux, beans, and providers compatible?

## 15. Summary to Remember

- `UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)` represents an **authentication request**. `principal` may just be a client-claimed string, `authorities` are empty, and `isAuthenticated` is false.
- `AuthenticationManager` and `DaoAuthenticationProvider` **verify real credentials** using the user store and `PasswordEncoder`, then return a result `Authentication` with trusted authorities and flag true.
- `ProviderManager` by default attempts to **erase credentials** on the result; `getCredentials()==null` does not erase identity/authorities.
- `UsernamePasswordAuthenticationToken.authenticated(...)` and the three-argument constructor **do not verify passwords on their own**; use them only from trusted provider code.
- `AuthenticationManager.authenticate(...)` **does not automatically set SecurityContextHolder** when called directly; filters or a proper login flow must manage context and persistence.
- Successful authentication is only the first gate; **roles, permissions, owner/tenant, and business state** must still be authorized separately.
- Thorough tests need **before/after tokens**, valid/wrong passwords, HTTP statuses, CSRF, and independent requests.

## Official References

- [Spring Security 6.5 — UsernamePasswordAuthenticationToken Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 — Release, June 25, 2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
