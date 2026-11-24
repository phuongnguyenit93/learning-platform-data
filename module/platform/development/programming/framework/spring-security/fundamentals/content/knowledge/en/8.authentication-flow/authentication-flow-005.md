# DaoAuthenticationProvider Connecting UserDetailsService with PasswordEncoder

> **Context:** Spring Security for Servlet/Spring MVC, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This topic explains **DaoAuthenticationProvider** as the bridge between **looking up an account** via `UserDetailsService` and **verifying the password** via `PasswordEncoder`. It walks through execution flow, interface contracts, explicit provider configuration, a complete runnable Spring Boot example, authentication failure testing, and real-world deployment issues such as account status, hash migration, caching, and multiple providers.

## 1. The Problem to Solve

An account-management application may store the following fields:

| username | password_hash | enabled | locked | authorities |
| --- | --- | --- | --- | --- |
| alice | Stored BCrypt hash | true | false | ROLE_USER, profile:read |
| admin | Stored BCrypt hash | true | false | ROLE_ADMIN |
| locked | Stored BCrypt hash | true | true | ROLE_USER |
| disabled | Stored BCrypt hash | false | false | ROLE_USER |

The client sends `username` and a **raw password** to log in. Spring Security must locate the corresponding account, verify the password, reject locked/disabled accounts, and build a trusted identity if the credentials are valid.

We have three distinct roles:

- **`UserDetailsService`**: looks up an account by username and returns `UserDetails` containing username, password hash, authorities, and account status.
- **`PasswordEncoder`**: compares the raw password in the request against the stored encoded password/hash using `matches(raw, encoded)`.
- **`DaoAuthenticationProvider`**: an `AuthenticationProvider` that uses both components above, checks account status, and creates an authenticated `Authentication` upon success.

**DaoAuthenticationProvider is not a repository.** It does not know whether you use JPA, JDBC, in-memory, an LDAP adapter, or an HTTP client to an identity service. The account source sits behind `UserDetailsService`. Nor does it decide who owns a specific document; access control happens at the authorization/domain policy step.

## 2. Component Connection Diagram

With HTTP Basic or form login using username/password, the typical path is:

~~~text
HTTP request
    |
    | username="alice", rawPassword="alice123"
    v
Authentication Filter
    BasicAuthenticationFilter / UsernamePasswordAuthenticationFilter
    |
    | Creates UsernamePasswordAuthenticationToken
    | principal="alice"; credentials="alice123"
    | authenticated=false
    v
AuthenticationManager (usually ProviderManager)
    |
    | Finds provider supporting Authentication type
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername("alice")
    |           |
    |           +--> AccountRepository/database
    |           +--> UserDetails
    |                 username="alice"
    |                 password="$2a$..." (stored hash)
    |                 authorities=[ROLE_USER, profile:read]
    |                 account flags
    |
    +--> Check account status
    |       enabled / locked / account-expired
    |
    +--> PasswordEncoder.matches("alice123", "$2a$...")
    |
    +--> Check credentials not expired
    |
    v
Authenticated UsernamePasswordAuthenticationToken
    principal=UserDetails
    authorities=[ROLE_USER, profile:read]
    authenticated=true
    |
    v
Authentication Filter sets result into SecurityContext
    |
    v
AuthorizationFilter or method security
    |
    +--> ALLOW / DENY by permissions and resource
~~~

**Read the diagram by responsibility**, not as a promise of exact ordering across all filters or providers. `DaoAuthenticationProvider` inherits account-checking logic from `AbstractUserDetailsAuthenticationProvider`. Inside the provider, there may be `UserDetails` caching, pre/post credential-matching status checks, and hash upgrade handling depending on configuration.

Key verifiable facts:

1. The filter creates an untrusted **Authentication request**; having a username in the request **does not mean the user is logged in**.
2. `ProviderManager` tries suitable `AuthenticationProvider` instances per its mechanism. `DaoAuthenticationProvider` is the provider for username/password via `UserDetailsService`.
3. `UserDetailsService` loads the hash and status; it **has no raw password parameter**, so it cannot decide whether the password is right or wrong.
4. `PasswordEncoder.matches` checks the raw password against the stored hash; it does not decrypt BCrypt.
5. The provider returns a result `Authentication` with verified principal and authorities.
6. The authentication filter places the result into `SecurityContext`; **authorization** later allows or denies the request.

## 3. What Does Each Component Receive and Return?

| Component | Primary input | Output | On failure |
| --- | --- | --- | --- |
| `UserDetailsService` | `String username` | `UserDetails` | `UsernameNotFoundException` |
| `PasswordEncoder.encode` | Raw password on creation/change | New encoded password | Encoder error or invalid data |
| `PasswordEncoder.matches` | Request raw password and stored encoded hash | `boolean` | false when credentials mismatch; invalid format may throw exception |
| `DaoAuthenticationProvider.authenticate` | `Authentication` supporting username/password | Authenticated `Authentication` | Appropriate `AuthenticationException` |
| `ProviderManager.authenticate` | Request `Authentication` | Result from chosen provider | AuthenticationException if unsuccessful |
| `AuthorizationManager` | Authentication/context and protected target | Permission decision | Deny / route to appropriate handler |

### 3.1. `UserDetailsService` only performs lookup

Contract:

~~~java
// Simplified signature for learning, not library source code.
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

An implementation must:

- Look up **the exact account** from a trusted source.
- If absent, throw `UsernameNotFoundException`; never return null and never fabricate a default user.
- If present, return `UserDetails` with the **stored password hash**, authorities, and four accurate status flags.
- Not read raw passwords from the request, not match passwords itself, and not mark SecurityContext as authenticated itself.

This explains why in the same application, `loadUserByUsername("alice")` can still return the right UserDetails **even when the client entered the wrong password**. Rejection for a wrong password happens afterward inside `DaoAuthenticationProvider`.

### 3.2. `UserDetails`: account security data

Key methods:

~~~java
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isEnabled();
boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
~~~

The signatures above belong to the interface, shown as a reading snippet. Specifically:

- `getPassword()` should be the **stored encoded hash**, not a raw password.
- `getAuthorities()` holds trusted `GrantedAuthority` instances, such as `ROLE_USER`.
- `isAccountNonLocked() == true` means the account is **not locked**.
- `isCredentialsNonExpired() == false` means credentials have expired.
- `isEnabled() == false` means the account is disabled.

The flag name `isAccountNonLocked` is easily inverted when mapping from a DB column named `locked`. If the DB stores `locked=true`, UserDetails must indicate **the account is no longer non-locked**.

### 3.3. `PasswordEncoder` matches instead of String comparison

Contract:

~~~java
// Important signatures, for studying the interface only.
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
boolean upgradeEncoding(String encodedPassword);
~~~

`encode(raw)` is usually used **when creating or changing a password**, before saving the password hash. `matches(raw, encoded)` is used **during login**. `upgradeEncoding(...)` is a signal supporting hash upgrade strategies, and does not mutate the database itself when called.

With BCrypt, two calls to `encode("alice123")` can produce different hashes because of salt. Therefore:

~~~java
// Wrong: re-encode and compare encoded strings
encoder.encode(rawPassword).equals(storedHash);

// Correct: PasswordEncoder checks raw against stored hash
encoder.matches(rawPassword, storedHash);
~~~

This is a snippet requiring `encoder`/`rawPassword`/`storedHash` variables in a real program. **Never reverse-decrypt a hash to recover a password.**

## 4. What Does DaoAuthenticationProvider Do with Both Dependencies?

`DaoAuthenticationProvider` is a concrete `AuthenticationProvider` implementation built upon the common logic of `AbstractUserDetailsAuthenticationProvider`.

In Spring Security 6.5, explicit configuration looks like:

~~~java
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(userDetailsService);

provider.setPasswordEncoder(passwordEncoder);
~~~

This snippet assumes both dependencies are already declared. Using the constructor taking `UserDetailsService` makes the account source explicit, then attaches the `PasswordEncoder` matching the stored hash format. Older constructors or setters for the service are deprecated in the 6.5 API line; when reading older tutorials, check the version you use.

### 4.1. `supports(...)` and ProviderManager

A `ProviderManager` can hold multiple providers. Each provider has a `supports(Class<?>)` method indicating which Authentication types it can handle.

~~~text
ProviderManager
  |
  +--> DaoAuthenticationProvider
  |      typically handles UsernamePasswordAuthenticationToken
  |
  +--> Other provider
  |      handles its corresponding Authentication type
  |
  +--> Another provider...
~~~

`supports(...) == true` **does not guarantee username/password are valid**; it only means the provider can evaluate this request type. `authenticate(...)` is what checks credentials. If no provider can handle the type, the system may throw `ProviderNotFoundException`.

Do not arbitrarily add providers just because a project has a `UserDetailsService` class. When there is a custom AuthenticationManager, multiple providers, or multiple SecurityFilterChain beans, verify the chain uses the right provider and encoder.

### 4.2. User lookup flow

The provider receives an unauthenticated `UsernamePasswordAuthenticationToken`, extracts the username, and calls `loadUserByUsername(username)` via the registered service. The result is mapped to UserDetails.

If the service throws `UsernameNotFoundException`, standard `DaoAuthenticationProvider` by default **masks the missing-username detail into a generic BadCredentials error**, helping reduce the risk of leaking account lists via responses. Depending on configuration and handlers, HTTP clients usually see `401` with Basic; do not return messages distinguishing "username not registered" from "wrong password" to untrusted callers.

### 4.3. Account status checks

`DaoAuthenticationProvider` also uses the superclass's `UserDetails` status checking mechanism.

| UserDetails status | Meaning when false | Common internal exception |
| --- | --- | --- |
| `isEnabled()` | Account disabled | `DisabledException` |
| `isAccountNonLocked()` | Account locked | `LockedException` |
| `isAccountNonExpired()` | Account expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials expired | `CredentialsExpiredException` |

These status errors can be detected **before or after** password checking depending on the flag and provider. With standard username/password, basic account status is checked before the password; credential expiration is a separate check. APIs should not reveal locked/disabled status to callers not allowed to confirm identity.

**Do not drop status flags just because login still runs**: a boolean mapping bug can allow locked accounts to keep authenticating, or cause every account to be rejected.

### 4.4. Password verification and creating the result

After obtaining UserDetails and passing necessary checks, the provider runs logic equivalent to:

~~~java
boolean passwordCorrect =
    passwordEncoder.matches(
        rawPasswordFromAuthentication,
        userDetails.getPassword()
    );
~~~

This is a **snippet for explanation**, not a request to write it in a service yourself. If the password does not match, the provider rejects with `BadCredentialsException` per standard behavior.

If valid, the provider creates an **Authentication result** whose principal is typically the loaded UserDetails, with matching authorities and authenticated state. Controllers do not need to manually build an `authenticated(...)` token from client-sent roles.

### 4.5. Provider and Filter have different roles

`DaoAuthenticationProvider.authenticate(...)` **does not send HTTP 200 or 401 itself** and **does not store SecurityContext like an authentication filter**. The filter calls `AuthenticationManager`, receives the result, and places the Authentication into the context according to Spring Security's mechanism.

So when debugging:
- Service is called yet controller does not run: check password/flags, exceptions, filters, and authorization.
- Authentication succeeded yet endpoint returns 403: check authorities, URL/method rules, CSRF, or domain policy.
- Request uses JWT Bearer and service is never called: the request may be entering a different provider/chain that does not use DaoAuthenticationProvider at all.

## 5. When Is This Provider Appropriate?

| Authentication type | Is DaoAuthenticationProvider the default mechanism? |
| --- | --- |
| Form login username/password with UserDetailsService | Usually appropriate |
| HTTP Basic username/password with UserDetailsService | Usually appropriate |
| OAuth2 Resource Server JWT | **No**; use JwtDecoder/JwtAuthenticationProvider and matching converter |
| Opaque bearer token | **Not by default**; use introspection and the corresponding provider |
| OAuth2 Login/OpenID Connect | **Not by default**; has dedicated flow/token/user services |
| Custom API key or magic link | Not by default; consider a specialized AuthenticationProvider |
| Spring WebFlux reactive | Does not use blocking Servlet DaoAuthenticationProvider this way; has reactive APIs |

Do not force every token into `loadUserByUsername` and call that "verifying a JWT". JWT authentication requires validating signature, issuer/audience, expiry, and claims per design.

## 6. Runnable Demo: Spring Boot 3, Java 17, and Explicit Provider

The example uses **Spring Boot 3.x**, **Spring Security 6.x**, **Spring MVC**, **Java 17+**, **HTTP Basic**. We register `DaoAuthenticationProvider` explicitly to observe its relationship with UserDetailsService and PasswordEncoder clearly.

The system has four demo accounts:

| Account | Localhost password | Authorities | Status |
| --- | --- | --- | --- |
| alice | alice123 | ROLE_USER, profile:read | Active |
| admin | admin123 | ROLE_ADMIN, profile:read | Active |
| locked | locked123 | ROLE_USER | Locked |
| disabled | disabled123 | ROLE_USER | Disabled |

**These are illustrative credentials**, not for production use. Real passwords must be protected on creation/change and their hashes persisted. In the demo, the repository holds accounts in memory and generates hashes at startup; the service **only reads hashes**.

### 6.1. Dependencies and structure

In a Spring Boot 3.x project with Gradle plugin, Java 17, and Gradle Wrapper already initialized, the dependencies block in **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is the **dependencies section** of a project, not a complete standalone build.gradle. Java files in the same package:

~~~text
src/main/java/com/example/daodemo/
  DaoDemoApplication.java
  Account.java
  DemoAccountRepository.java
  AccountUserDetailsService.java
  SecurityConfig.java
  AccountController.java

src/test/java/com/example/daodemo/
  DaoProviderTest.java
~~~

### 6.2. DaoDemoApplication.java

~~~java
package com.example.daodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DaoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoDemoApplication.class, args);
    }
}
~~~

### 6.3. Account.java: model independent of Spring Security

~~~java
package com.example.daodemo;

import java.util.Set;

public record Account(
    String username,
    String passwordHash,
    boolean enabled,
    boolean locked,
    Set<String> authorities
) {
}
~~~

`Account` is an application record, **not required to implement UserDetails**. When connecting JPA, this record can be replaced by an entity or domain model, while the service below translates data into UserDetails.

### 6.4. DemoAccountRepository.java: source of hashes/flags

~~~java
package com.example.daodemo;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

@Repository
public class DemoAccountRepository {

    private final Map<String, Account> accounts;

    public DemoAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice", new Account(
                "alice", encoder.encode("alice123"),
                true, false,
                Set.of("ROLE_USER", "profile:read")
            ),
            "admin", new Account(
                "admin", encoder.encode("admin123"),
                true, false,
                Set.of("ROLE_ADMIN", "profile:read")
            ),
            "locked", new Account(
                "locked", encoder.encode("locked123"),
                true, true,
                Set.of("ROLE_USER")
            ),
            "disabled", new Account(
                "disabled", encoder.encode("disabled123"),
                false, false,
                Set.of("ROLE_USER")
            )
        );
    }

    public Optional<Account> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
~~~

**The hashing happens in the repository constructor for the demo, not inside `loadUserByUsername`.** In a real application, when a user registers or changes a password, `encode(raw)` creates the hash stored in the database. During login, the repository reads the existing hash instead of re-encoding.

### 6.5. AccountUserDetailsService.java: adapter for the provider

~~~java
package com.example.daodemo;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final DemoAccountRepository repository;

    public AccountUserDetailsService(DemoAccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (username == null || username.isBlank()) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .build();
    }
}
~~~

Explanation:

- `@Service` makes Spring create a bean implementing `UserDetailsService`.
- `loadUserByUsername` receives **username**, not raw password.
- Account not found: throws `UsernameNotFoundException`, never returns null.
- `.password(account.passwordHash())` receives the **stored hash**; do not call encoder here.
- `.authorities(...)` preserves `ROLE_` and permission strings per application policy.
- `.disabled(!enabled)` and `.accountLocked(locked)` pass flags in the proper direction from the record.
- `accountExpired`/`credentialsExpired` flags are not stored in the demo model so the User builder uses defaults meaning active/unexpired. Production must map them fully if the data model tracks those states.

Important point: **The service returning UserDetails does not mean the password is correct**. Only `DaoAuthenticationProvider` performs that check.

### 6.6. SecurityConfig.java: wiring service, encoder, and filter chain

~~~java
package com.example.daodemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DaoAuthenticationProvider daoProvider) throws Exception {

        http
            .authenticationProvider(daoProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

This is **explicit wiring**:

1. Spring provides the `PasswordEncoder` bean using BCrypt.
2. `AccountUserDetailsService` is a `UserDetailsService` bean declared via `@Service`.
3. `daoAuthenticationProvider(...)` receives both beans. The provider has **a service to look up users** and **an encoder to verify hashes**.
4. `.authenticationProvider(daoProvider)` registers the provider with the demo chain's HttpSecurity. This clarifies which provider is used, especially while learning.
5. `httpBasic(...)` enables BasicAuthenticationFilter so clients can send username/password.
6. `/public` is public, `/me` requires authenticated, `/admin` requires `ROLE_ADMIN`, other endpoints are denied.
7. `STATELESS` in the demo avoids using HttpSession to restore SecurityContext for later requests; Basic can be verified on every request. This is **not a mandatory requirement of DaoAuthenticationProvider**.
8. CSRF is not disabled because all demo endpoints are GET. When adding POST/PUT/DELETE, design CSRF based on client type and credential transport.

**Note on bean wiring:** When an application has only one compatible UserDetailsService and PasswordEncoder, Spring Security can auto-configure the DAO mechanism for standard username/password flows. This example registers it explicitly to make dependencies clear. In apps with multiple providers/chains, verify which AuthenticationManager and chain they are bound to, avoiding conflicting configurations.

### 6.7. AccountController.java: observing the resulting Authentication

~~~java
package com.example.daodemo;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + authorities;
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

The Controller **does not call `loadUserByUsername`** and does not re-check passwords. It receives the Authentication already verified by the filter/provider. Never return the raw Authentication/UserDetails in a response because the principal may contain password hashes and internal metadata.

With the demo data, `/me` returns the name and authorities as a string so learners can see the permissions. Production should normally return a dedicated public DTO and avoid exposing internal authorities if the client does not need them.

### 6.8. Running with Gradle

In the project root with Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows PowerShell or cmd:
gradlew.bat bootRun
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u locked:locked123 http://localhost:8080/me
curl -i -u disabled:disabled123 http://localhost:8080/me
curl -i -u nobody:somepass http://localhost:8080/me
~~~

Expected results with the exact configuration above, without proxies or custom error handlers:

| Request | Status | Reason or body |
| --- | --- | --- |
| Anonymous GET `/public` | **200** | `public` |
| Anonymous GET `/me` | **401** | Basic entry point requires credentials |
| Alice valid password GET `/me` | **200** | `alice ROLE_USER,profile:read` |
| Admin valid password GET `/admin` | **200** | `admin-only` |
| Alice accessing `/admin` | **403** | Authenticated, lacks ROLE_ADMIN |
| Alice wrong password | **401** | `PasswordEncoder.matches` rejects |
| Locked valid password | **401** | Account is locked |
| Disabled valid password | **401** | Account is disabled |
| Non-existent username | **401** | Lookup fails, cannot authenticate |

The `WWW-Authenticate` header normally appears in HTTP Basic 401 responses. Error bodies depend on the entry point/error handling; do not rely on a fixed body string. These statuses are **HTTP responses**, not Java program stdout.

**Credential security:** Basic uses Base64 for username/password, not secret encryption. Always use HTTPS outside localhost, never hardcode passwords in production, and avoid putting real passwords in shell history or logs.

## 7. Testing the Provider Directly and via HTTP Basic

To prove `UserDetailsService` and `PasswordEncoder` have separate responsibilities, test both layers:

- **Direct DaoAuthenticationProvider tests:** manually build UsernamePasswordAuthenticationToken, verify success and internal exceptions.
- **MockMvc via HTTP Basic:** verify filter/manager/provider/authorization combine into HTTP 200/401/403.

Create `src/test/java/com/example/daodemo/DaoProviderTest.java`:

~~~java
package com.example.daodemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DaoProviderTest {

    @Autowired MockMvc mvc;
    @Autowired DaoAuthenticationProvider provider;
    @Autowired UserDetailsService users;
    @Autowired PasswordEncoder encoder;

    @Test
    void serviceLoadsHashButDoesNotCheckRawPassword() {
        UserDetails alice = users.loadUserByUsername("alice");

        assertEquals("alice", alice.getUsername());
        assertFalse(alice.getPassword().equals("alice123"));
        assertTrue(encoder.matches("alice123", alice.getPassword()));
        assertFalse(encoder.matches("wrong", alice.getPassword()));

        assertThrows(UsernameNotFoundException.class,
            () -> users.loadUserByUsername("nobody"));
    }

    @Test
    void providerAcceptsCorrectPasswordAndPopulatesAuthorities() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123"
            );

        assertFalse(request.isAuthenticated());
        assertTrue(request.getAuthorities().isEmpty());

        Authentication result = provider.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void providerRejectsWrongPasswordAndUnknownUsername() {
        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong"
                )
            ));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "nobody", "somepass"
                )
            ));
    }

    @Test
    void providerRejectsLockedAndDisabledAccounts() {
        assertThrows(LockedException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "locked", "locked123"
                )
            ));

        assertThrows(DisabledException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "disabled", "disabled123"
                )
            ));
    }

    @Test
    void providerManagerErasesCredentialsOnSuccess() {
        ProviderManager manager = new ProviderManager(provider);

        Authentication result = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123"
            )
        );

        assertTrue(result.isAuthenticated());
        assertNull(result.getCredentials());
    }

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointNeedsValidCredentials() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER,profile:read"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void accountFlagsAndUnknownUserResultInUnauthorized() throws Exception {
        mvc.perform(get("/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("disabled", "disabled123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("nobody", "somepass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void loggedInUserMayStillLackAdminRole() throws Exception {
        mvc.perform(get("/admin").with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

### 7.1. What is verified?

- `serviceLoadsHashButDoesNotCheckRawPassword`: service returns the **stored hash**; `PasswordEncoder` checks the raw password. Missing username makes the service throw UsernameNotFoundException.
- `providerAcceptsCorrectPasswordAndPopulatesAuthorities`: provider builds an authenticated Authentication with permissions from a trusted source.
- `providerRejectsWrongPasswordAndUnknownUsername`: when calling the provider directly, wrong password and unknown username can both become BadCredentialsException by default. Distinguish internal exceptions from public responses.
- `providerRejectsLockedAndDisabledAccounts`: UserDetails status flags take effect.
- `providerManagerErasesCredentialsOnSuccess`: distinguishes `ProviderManager`'s credential erasure responsibility after the provider returns a result. **Do not rely on getCredentials() always holding the raw password after login**.
- HTTP tests prove Basic filter and provider work together, while the ADMIN rule occurs at **authorization**.

**Note on direct provider tests:** if calling `provider.authenticate` without going through `ProviderManager`, do not assume credential erasure behaves like the manager flow. The fifth test intentionally goes through ProviderManager to verify this boundary.

**Test results in this lesson are expectations based on the code.** To claim a build/test passes, execute Gradle on an actual project with matching dependencies and versions.

## 8. AuthenticationProvider, AuthenticationManager, and SecurityFilterChain

Three configuration layers are easily confused:

1. `DaoAuthenticationProvider` verifies username/password using service/encoder.
2. `ProviderManager` coordinates one or more AuthenticationProviders and returns the resulting Authentication.
3. `SecurityFilterChain` decides **which filters** and **which authorization rules** apply to HTTP requests.

~~~text
SecurityFilterChain
    |
    +--> BasicAuthenticationFilter
    |       |
    |       +--> AuthenticationManager
    |               |
    |               +--> DaoAuthenticationProvider
    |                      +--> UserDetailsService
    |                      +--> PasswordEncoder
    |
    +--> AuthorizationFilter
           |
           +--> authenticated / hasRole / hasAuthority
~~~

**It is wrong to declare a UserDetailsService and assume every request uses that provider.** With custom managers, multiple service beans, multiple chains, or an OAuth2 Resource Server, requests can use completely different providers.

### 8.1. When should you declare the provider as a bean?

For simple username/password setups, a single UserDetailsService and PasswordEncoder may suffice for Spring Security to auto-configure the DAO mechanism per framework capabilities and auto-configuration conditions. When you need to:

- Explicitly see which provider is used.
- Add a custom `UserDetailsPasswordService`.
- Add supported caching/customizations.
- Combine multiple AuthenticationProviders.
- Configure individual SecurityFilterChains separately.
- Diagnose authentication failures or complex migrations.

...declaring `DaoAuthenticationProvider` explicitly can make the architecture easier to control and test.

Do not set a custom AuthenticationManager that drops existing providers; doing so can break HTTP Basic or leave other providers unused.

### 8.2. Distinguishing 401, 403, and data errors

| Scenario | Primary decision layer | Common HTTP with Basic |
| --- | --- | --- |
| No credentials sent to protected endpoint | Authentication entry point | 401 |
| Username does not exist | UserDetailsService/Provider | 401 |
| Wrong password | PasswordEncoder/Provider | 401 |
| Account disabled/locked | Account status checks/Provider | 401 |
| Correct password, ROLE_USER accessing ADMIN | AuthorizationManager | 403 |
| POST without CSRF token when CSRF enabled | CsrfFilter | 403 |
| URL has no controller | Spring MVC | May be 404 after passing security |
| No provider supports token | ProviderManager | AuthenticationException; HTTP per entry point |

HTTP status and body also depend on entry point, AccessDeniedHandler, filter chain, exception mapping, and client. Never assume every 401 is a wrong password or every 403 is a missing role.

## 9. PasswordEncoder: BCrypt and DelegatingPasswordEncoder

### 9.1. Hash on save, matches on verification

With BCrypt:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("alice123");

boolean success = encoder.matches("alice123", storedHash);
boolean failure = encoder.matches("wrong", storedHash);
~~~

This is a snippet inside a program with Spring Security libraries and imports. **Expected logical values**: success is true, failure is false. `storedHash` is not a fixed literal because BCrypt generates salts.

Do not use:

~~~java
// Wrong: two encode calls may have different salts.
encoder.encode("alice123").equals(storedHash);
~~~

A BCrypt hash is not a string that can be decrypted back into a password.

### 9.2. DelegatingPasswordEncoder and prefixes

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` typically uses an algorithm prefix in stored hashes, such as:

~~~text
{bcrypt}$2a$...
{pbkdf2}...
{scrypt}...
~~~

These are **format examples**, not valid hashes to copy into a database. If the service returns a raw BCrypt hash like `$2a$...` while the provider uses DelegatingPasswordEncoder expecting `{bcrypt}`, matches can fail due to the missing algorithm id. Conversely, if stored data has a `{bcrypt}` prefix while the chosen encoder is plain BCryptPasswordEncoder, do not assume it handles the string like DelegatingPasswordEncoder.

**The provider's encoder must match the exact stored hash format**, not just "the same BCrypt name" by intuition. For migrations, define a transition path, test old/new data, and handle accounts with invalid hashes safely.

### 9.3. Why avoid NoOp or fast hashes?

Never store plaintext passwords, never use `NoOpPasswordEncoder`, and never treat plain MD5/SHA-256 as secure password storage. Password hashing should use an algorithm with tunable cost (BCrypt, Argon2, scrypt, PBKDF2 per policy and system capacity), managed salts, and an upgrade plan as security requirements evolve.

Increasing BCrypt cost affects CPU/login latency; balance against resources and brute-force risk rather than choosing work factors arbitrarily. Strong hashing also **does not replace rate limiting, credential stuffing alerts, MFA, or TLS**.

### 9.4. UserDetailsPasswordService and upgradeEncoding

DaoAuthenticationProvider can work with `UserDetailsPasswordService` to update the encoded password after successful authentication when the encoder signals an upgrade is needed.

Concept:

~~~text
UserDetailsService
    -> load old storedHash
PasswordEncoder.matches(raw, storedHash)
    -> true
PasswordEncoder.upgradeEncoding(storedHash)
    -> may be true
UserDetailsPasswordService.updatePassword(user, newEncodedPassword)
    -> save new hash via application-provided mechanism
~~~

This is a **conceptual model**, not a claim that Spring Security updates your database automatically just because a PasswordEncoder exists. You must provide `UserDetailsPasswordService` and proper transaction/update logic; watch out for races if the password was just changed from another session. Never retain the raw password after the upgrade step.

## 10. Integrating DaoAuthenticationProvider into a Database-Backed System

In production, `UserDetailsService` is often an adapter calling a Spring Data JPA repository.

Example repository:

~~~java
// Snippet: requires AccountEntity, JpaRepository/Optional imports
// and Spring Data JPA dependency in a real project.
public interface AccountJpaRepository
        extends JpaRepository<AccountEntity, Long> {

    Optional<AccountEntity> findByLoginName(String loginName);
}
~~~

In the service:

~~~java
// Snippet placed inside loadUserByUsername(...).
AccountEntity account = repository.findByLoginName(username)
    .orElseThrow(() ->
        new UsernameNotFoundException("Invalid credentials")
    );

return User.withUsername(account.getLoginName())
    .password(account.getPasswordHash())
    .authorities(resolveAuthorities(account))
    .disabled(!account.isEnabled())
    .accountLocked(account.isLocked())
    .build();
~~~

**resolveAuthorities(account)** is a helper you must implement to map roles/permissions from real data. The snippet above is not a complete file: it requires an entity, transaction strategy, imports, mappings, repository configuration, and JPA dependencies.

Key database requirements:

- **Unique login identifier:** add a proper unique constraint, and keep uppercase/lowercase and Unicode normalization consistent with policy. In multi-tenant apps, reliably determine the tenant; looking up solely by username risks matching a same-named user in another tenant.
- **Persistently stored hash:** `UserDetailsService` reads hashes rather than re-hashing on every login.
- **Account status:** map enabled/locked/account expiration/credential expiration in the right direction, and do not ignore flags missing from the entity.
- **Authorities:** avoid N+1 queries or lazy loading exceptions when reading roles; ensure transactions/read queries fit. Ensure `ROLE_ADMIN`/`ADMIN` matches rules consistently.
- **Do not leak entities:** UserDetails or principals can contain password hashes. Controllers should return dedicated DTOs.
- **Infrastructure errors:** a database timeout is not a wrong username/password. Maintain internal logging/auditing without masking database failures as success or falling back to a guest account.
- **Performance:** password hashing is CPU-intensive by design; size login throughput and apply rate limiting.

### 10.1. Account ID and tenant

`loadUserByUsername(String username)` takes only a single string. In multi-tenant systems, usernames may not be globally unique. Build a clear identity model, such as normalizing usernames under a verified tenant or using a custom provider handling tenant context.

Never trust a tenant ID sent by a client in a request body to look up a user without verifying tenant scope. Being able to log in does not grant access to every tenant/resource.

## 11. Caching UserDetails and Credential Erasure

`DaoAuthenticationProvider`/its superclass supports `UserCache` and can optimize repeated account reads. When caching is active, credential checks must still ensure wrong passwords are never accepted just because an account is cached.

Three facts to remember:

1. **PasswordEncoder.matches must verify valid credentials**, even when UserDetails comes from a cache.
2. Standard **ProviderManager** erases sensitive credentials from the result Authentication if the object implements `CredentialsContainer`, thanks to `eraseCredentialsAfterAuthentication` enabled by default.
3. If the cache shares the exact same UserDetails reference as the Authentication principal, erasing the password on the principal can corrupt the cached entry. Design copying/invalidation properly.

Do not assume every request hits `loadUserByUsername`: an active session or JWT may skip the service on subsequent requests, and a cached provider changes database hit counts. When roles/passwords/account status change, plan session, token, and cache invalidation.

### 11.1. Provider does not manage sessions itself

DaoAuthenticationProvider returns an authentication result. Whether Authentication is saved into HttpSession belongs to filters/security context strategies and the SecurityFilterChain's `SessionCreationPolicy`. HTTP Basic can authenticate per request; form login commonly uses sessions.

`STATELESS` **does not turn DaoAuthenticationProvider into a JWT provider**. If a project uses Bearer JWTs, the resource server has its own token validation mechanism; never build an API taking a JWT and passing the token string into a password encoder.

### 11.2. Does changing a password log out old sessions?

Not by default. Sessions can hold the Authentication created at login; issued tokens can remain valid until expiry. If business rules require revoking all sessions/tokens on password change, implement invalidation, revocation, or revalidation by design. Updating the hash in the database alone does not guarantee all already-logged-in requests are blocked immediately.

## 12. Error Handling, Anti-Enumeration, and Brute-Force Protection

### 12.1. Do not expose UsernameNotFoundException externally

In standard configurations, missing usernames and wrong passwords are usually surfaced to clients with a generic invalid credentials response. This helps reduce user enumeration, though response timing, logs, and rate limits must also be designed to avoid leaking account existence.

An application-defined login JSON response may use a generic error:

~~~json
{
  "error": "INVALID_CREDENTIALS"
}
~~~

This is a **contract example**, not the default body of every HTTP Basic response. With HTTP Basic, continue to respect `WWW-Authenticate` semantics where appropriate.

### 12.2. Account locking and status errors

On public APIs, evaluate policies to avoid revealing "this username exists and is locked" to attackers. Internally, unit-testing specific exceptions like `LockedException`/`DisabledException` is valuable to prove accurate mapping.

Never let client-supplied `locked=false` or `enabled=true` in a login request override account state stored in the trusted source.

### 12.3. Rate limiting, password spraying, and MFA

PasswordEncoder raises the cost of offline password guessing, but does not stop online attacks on its own. Depending on your threat model, apply:

- Rate limiting per principal/IP/device appropriately without locking out the entire system over a shared IP.
- Auditing failed login attempts without recording raw passwords/tokens.
- Alerting on credential stuffing, password spraying, and anomalous patterns.
- MFA or step-up authentication for higher-risk systems.
- Password changes and active sessions handled under explicit revocation policies.
- Protecting login endpoints and account stores from CPU-exhaustion denial-of-service caused by expensive password hashing.

Never "fix" 401 errors by disabling PasswordEncoder or switching to plaintext passwords.

## 13. Common Configuration Mistakes

### 13.1. Service returns plaintext instead of a hash

If the DB stores `"alice123"` while the provider uses BCryptPasswordEncoder, `matches` cannot authenticate the way it does with a BCrypt hash. Hash on storage and migrate legacy data properly; never use NoOp in production as a workaround.

### 13.2. Service re-encodes the hash on every load

Wrong:

~~~java
// Wrong: account.getPasswordHash() is already a hash.
.password(encoder.encode(account.getPasswordHash()))
~~~

Then the provider compares the raw password against a hash of a hash, so login fails. The service simply needs `.password(account.getPasswordHash())`.

### 13.3. Encoder format mismatches stored data

Plain BCryptPasswordEncoder and DelegatingPasswordEncoder have different format expectations. Stored hashes missing the right prefix or using an unsupported algorithm id can break all logins. Inspect actual stored data and encoder versions.

### 13.4. Forgetting to map `locked` status accurately

Database stores `locked=true`, while UserDetails must report `isAccountNonLocked=false`. With `UserBuilder`, call `.accountLocked(account.isLocked())`; do not double-invert the flag.

### 13.5. Thinking the provider manages URL permissions itself

The provider grants authorities after authentication, while `.requestMatchers("/admin").hasRole("ADMIN")` is a SecurityFilterChain authorization rule. A user can have authenticated=true and still get 403.

### 13.6. Assuming username is a role

An account with username `"admin"` does not automatically have `ROLE_ADMIN`. Only trusted GrantedAuthority values satisfy `hasRole("ADMIN")` per the default prefix.

### 13.7. Confusing `getCredentials()` with the DB-stored hash

In an authentication request, credentials are usually the temporary raw password. `UserDetails.getPassword()` is the stored hash. After authentication, `ProviderManager` may erase credentials; do not treat null as login failure.

### 13.8. Adding multiple providers without clear ordering

ProviderManager can contain multiple AuthenticationProviders. When multiple providers support the same token class, results depend on ordering and behavior, causing hard-to-debug bugs or unintended policies. Separate providers cleanly by mechanism and test with real requests.

### 13.9. Manually building `UsernamePasswordAuthenticationToken.authenticated` from input

A token marked trusted does not replace credential verification. Never accept `role=ADMIN` from the client and build an authenticated token; pass an unauthenticated request through AuthenticationManager.

### 13.10. Confusing 401 with 403

Wrong password/missing username/locked account are authentication failures returning 401 with Basic. Already logged in yet lacking ROLE_ADMIN is usually 403. CSRF can also produce 403 before reaching the controller. Read logs and the filter chain instead of randomly editing the service.

### 13.11. UserDetailsService is never called

Check the active filter chain, whether `httpBasic`/`formLogin` is enabled, which `AuthenticationManager` and provider receive the request, whether a custom provider replaced it, or whether the client actually sent a Bearer JWT instead of Basic.

### 13.12. Principal contains the entity and password hash

Controllers should never return raw UserDetails or Authentication. Create a small DTO and use account IDs when querying by owner/tenant.

### 13.13. Testing only the successful login case

A single `200` test does not prove security policy is sound. Add wrong password, missing username, locked/disabled, missing role, and unauthenticated credential tests.

### 13.14. Writing a custom AuthenticationProvider unnecessarily

If the use case is straightforward username/password + database, `DaoAuthenticationProvider` already handles the standard flow. Over-customizing providers easily omits status checks, credential erasure, user-enumeration protection, hash upgrades, or proper event handling.

## 14. Debugging the Authentication Flow Stage by Stage

When an application returns 401/403, inspect in order:

1. **Does the HTTP request carry the right credential type?** Basic Authorization header, form login username/password, or Bearer token?
2. **Which SecurityFilterChain matches the request?** Could another matcher and @Order send the request into a different chain?
3. **Is the authentication filter enabled?** Does `httpBasic`, `formLogin`, or resource server config match the credential type?
4. **Does AuthenticationManager include DaoAuthenticationProvider?** If multiple providers exist, what are their order and `supports()`?
5. **Which UserDetailsService bean does the provider use?** Is there a default bean, custom manager, or multiple services causing ambiguity?
6. **Does lookup return the right account?** Are username normalization, tenant, unique constraint, and transactions correct?
7. **Is the password hash in the expected format?** `$2a$...` or `{bcrypt}$2a$...`, and does the encoder match?
8. **Is PasswordEncoder.matches called with the right raw/hash?** Not re-encoding the hash or comparing strings directly.
9. **Are all four UserDetails status flags valid?** Disabled, locked, accountExpired, credentialsExpired?
10. **Authentication succeeds yet permissions fail?** Check authorities, ROLE_ prefix, endpoint rules, and owner/tenant.
11. **Old session or JWT still works?** Have invalidation/revocation/revalidation policies been implemented?
12. **401/403 caused by another filter?** CSRF, CORS preflight, error dispatch, and entry points can alter outcomes.

In development environments, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

DEBUG logs help reveal which chains/filters are selected, though not every internal value appears in logs. **Never log raw passwords, Authorization headers, access tokens, cookies, password hashes, or any credentials**.

### 14.1. Direct testing differs from HTTP testing

- **Direct provider tests** reveal internal exceptions and how the provider coordinates service/encoder.
- **MockMvc HTTP tests** show filters, manager/provider, and authorization producing real HTTP responses.
- **Service/JPA tests** confirm lookup, unique identity, status mapping, and schema permissions.
- **Security policy tests** confirm logged-in principals have accurate permissions on resources/tenants.

Do not treat a unit test of `PasswordEncoder.matches` as proof that the entire endpoint is secure.

## 15. Knowledge Check Exercises

**Question 1.** Where does DaoAuthenticationProvider obtain UserDetails?

**Answer:** From the configured UserDetailsService, typically looking up the account via `loadUserByUsername(username)`.

**Question 2.** Does UserDetailsService receive the raw password to authenticate by itself?

**Answer:** No. It takes the username and returns UserDetails containing the encoded password, authorities, and status. DaoAuthenticationProvider uses PasswordEncoder to check credentials.

**Question 3.** Why is `encoder.encode(raw).equals(storedHash)` wrong with BCrypt?

**Answer:** BCrypt uses salt so the same password produces different hashes. Use `encoder.matches(raw, storedHash)`.

**Question 4.** Will an account with the right password yet `isAccountNonLocked()==false` be allowed to log in?

**Answer:** No, with standard DaoAuthenticationProvider; locked accounts are rejected.

**Question 5.** When a username lookup finds nothing, should the service return null or throw an exception?

**Answer:** Throw `UsernameNotFoundException`. Never fabricate a dummy account or return null.

**Question 6.** Why can HTTP Basic return 401 for both a wrong password and a non-existent username?

**Answer:** Authentication failed; the provider masks unknown-user details with a generic credential error to limit enumeration. The entry point renders the response appropriately for the client.

**Question 7.** Alice's UserDetails has ROLE_USER, yet `/admin` requires ROLE_ADMIN. Is DaoAuthenticationProvider broken when `/admin` returns 403?

**Answer:** No. Authentication succeeded; authorization denied the request due to missing permissions.

**Question 8.** Does `new DaoAuthenticationProvider(userDetailsService)` automatically know which password encoder the database uses?

**Answer:** Do not guess. Configure `setPasswordEncoder` matching the stored hash format and test with real data.

**Question 9.** If the DB stores `locked=true`, what value should the UserDetails builder receive?

**Answer:** `.accountLocked(true)`, corresponding to UserDetails having `isAccountNonLocked()==false`.

**Question 10.** After login, does `Authentication.getCredentials()==null` mean the provider did not use a password?

**Answer:** No. ProviderManager usually erases credentials after successful authentication.

**Question 11.** Does changing a role in the database immediately update authorities in active sessions/JWTs?

**Answer:** Not by default. Session/token/cache invalidation or revalidation is required if policy demands immediate effect.

**Question 12.** Must a JWT Resource Server call DaoAuthenticationProvider to verify a Bearer token?

**Answer:** No. JWT uses its own provider/decoder and verification mechanism. DaoAuthenticationProvider is primarily for username/password.

**Question 13.** Why are both direct `provider.authenticate` tests and MockMvc HTTP tests useful?

**Answer:** Direct tests isolate lookup, matches, and exceptions; HTTP tests prove filter/manager/provider/authorization produce the right status on real requests.

**Question 14.** Why might a Custom AuthenticationManager prevent UserDetailsService from being called despite having a `@Service` bean?

**Answer:** The request may be routed to another provider or the manager never registered DaoAuthenticationProvider. Inspect wiring and the selected chain.

**Question 15.** If you only want a user to read their own invoices, is checking `invoice:read` authority alone enough?

**Answer:** Not enough. You must also check ownership, tenant, invoice state, and domain constraints.

## 16. Official Reference Documentation

- Spring Security 6.5 — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — **UserDetailsService**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html
- Spring Security — **Username/Password Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — **Password Storage**: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 API — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 API — **ProviderManager**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

**Remember:** `UserDetailsService` **looks up the account and returns hash/permissions/status**; `PasswordEncoder` **verifies the raw password against the hash**; `DaoAuthenticationProvider` **coordinates both, checks account state, and produces an authenticated Authentication**; `ProviderManager` **orchestrates providers**; the filter **sets the result into SecurityContext**; authorization **decides what is allowed**. Understanding those boundaries lets you replace in-memory repositories with JPA, upgrade hashes, and debug login errors without mixing up responsibilities.
