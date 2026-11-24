# UserDetails and UserDetailsService in Account-Based Authentication

> **Context:** Spring Security Servlet/Spring MVC, Java 17+, and Spring Boot 3.x. This lesson explains **UserDetails** and **UserDetailsService** in username/password authentication: loading an account from a data source, verifying the password, checking account status, building an identity, and testing the flow. The example uses HTTP Basic to observe each request, while the same account-loading mechanism is also used with form login when `DaoAuthenticationProvider` is configured.

## 1. The Problem: Spring Security Does Not Automatically Know Your Account Database

Suppose an application has columns **username**, **password_hash**, **enabled**, **locked**, and a relationship to a **roles** table. When a client sends a username/password, Spring Security needs to know:

1. **Does that username exist?** Is the account stored in a database, LDAP, an internal store, or another source?
2. **What is the stored password?** It must be an encoded password/hash used for verification, not plaintext.
3. **Is the account currently permitted to log in?** Is it locked, disabled, or expired?
4. **What authorities does the user have?** For example, **ROLE_USER**, **ROLE_ADMIN**, **report:read**.
5. **Where is the authentication result used?** Once valid, the Authentication is placed in SecurityContext to evaluate request permissions.

Spring Security defines two interfaces for supplying account data:

- **UserDetails:** describes account data in a structure Spring Security understands, including username, password hash, authorities, and four status flags.
- **UserDetailsService:** is responsible for **loading UserDetails by username**.

**UserDetailsService does not authenticate passwords.** It only loads data. **DaoAuthenticationProvider** works with **PasswordEncoder** to match credentials and check account status, then produces an **Authentication** upon success. **AuthorizationManager** or method security decides subsequent access rights.

| Component | Role | Not responsible for |
| --- | --- | --- |
| UserDetailsService | Look up an account by username, return UserDetails | Matching raw passwords, issuing access tokens |
| UserDetails | Carry password hash, authorities, account status | User CRUD management or sessions |
| DaoAuthenticationProvider | Use UserDetailsService and PasswordEncoder to authenticate username/password | Deciding who can view each document |
| PasswordEncoder | Hash passwords on storage, verify raw password against hash | Decrypting BCrypt to recover old passwords |
| AuthenticationManager | Dispatch authentication to a supporting provider | Querying the account database directly |
| Authentication | Result containing principal, authorities, authentication state | A default user database entity record |
| SecurityContextHolder | Allow processing code to access the current context | Automatically persisting context across sessions by default |
| AuthorizationManager | Decide allow/deny according to policy | Verifying passwords |

## 2. Seeing the HTTP Request Flow Clearly

Suppose a client calls **GET /me** with HTTP Basic:

~~~text
Client -> Authorization: Basic <encoded-username-password>
    |
    v
BasicAuthenticationFilter
    |
    | creates unauthenticated UsernamePasswordAuthenticationToken
    v
AuthenticationManager / ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |           |
    |           +--> repository / database / directory
    |           |
    |           +--> UserDetails
    |                   - username
    |                   - password hash
    |                   - GrantedAuthority
    |                   - account status flags
    |
    +--> PasswordEncoder.matches(rawPassword, storedHash)
    |
    +--> account / credential status checks
    |
    v
Authenticated Authentication
    |
    v
SecurityContextHolder
    |
    v
AuthorizationFilter -> Controller / Service -> HTTP response
~~~

**Two distinctions must be made:**

- **Loading an account does not mean authenticated:** `UserDetailsService` may find `alice` even if the client sends the wrong password. The provider will reject it at the password-matching step.
- **Being authenticated does not mean accessing everything:** `alice` may have logged in with `ROLE_USER`, yet a URL requiring `ROLE_ADMIN` can still return **403**.

Exact components and filter ordering depend on configuration. HTTP Basic uses **BasicAuthenticationFilter**; form login usually uses **UsernamePasswordAuthenticationFilter**; a Bearer JWT resource server uses a different provider/decoder and does not call `UserDetailsService` by default.

## 3. The UserDetails Contract: Seven Essential Points

Main method signatures of **org.springframework.security.core.userdetails.UserDetails**:

~~~java
// Excerpt of methods for study; not the entire interface.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isEnabled();
boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
~~~

These are illustrative signatures, **not a standalone Java program**.

### 3.1. Username

**getUsername()** returns the name used to identify the account during authentication. In real applications, username may be a login ID or email, but a consistent normalization policy is required. If there are multiple tenants, you must define whether username is unique per tenant or globally; never arbitrarily query an account with a colliding name from another tenant.

In business-layer principals, consider using a **stable accountId** for data queries instead of a mutable username.

### 3.2. Password

**getPassword()** returns the **stored encoded password**. For example with BCrypt, the value contains salt and hash, and the raw password cannot be recovered from it.

The provider executes logic equivalent to:

~~~java
boolean valid = passwordEncoder.matches(
    rawPasswordFromRequest,
    userDetails.getPassword()
);
~~~

This is a **snippet inside the authentication mechanism**, not a complete Java class. Never use **raw.equals(storedHash)**, never re-encode the hash every time `UserDetailsService` is called, and never write a custom BCrypt decryption function.

### 3.3. GrantedAuthority

**getAuthorities()** may contain:

~~~text
ROLE_USER
ROLE_ADMIN
profile:read
invoice:approve
~~~

In the default configuration:

- **hasRole("ADMIN")** checks for authority **ROLE_ADMIN**.
- **hasAuthority("ROLE_ADMIN")** also checks for the string **ROLE_ADMIN**.
- **hasAuthority("profile:read")** checks for the exact string **profile:read**.
- The **roles("USER")** builder prepends **ROLE_** automatically; the **authorities("ROLE_USER")** builder keeps the supplied string as-is.

Normalizing authorities in one place avoids bugs like **ROLE_ROLE_ADMIN**, or a database storing only **ADMIN** while rules expect **ROLE_ADMIN**. Roles in `UserDetails` express authority categories; ownership over **a specific resource** still requires appropriate domain policies.

### 3.4. Four Account Status Flags

| Method | Returning true means | Returning false means |
| --- | --- | --- |
| **isEnabled()** | Account is permitted to be used | Account is disabled |
| **isAccountNonExpired()** | Account has not expired | Account has expired |
| **isAccountNonLocked()** | Account is not locked | Account is locked |
| **isCredentialsNonExpired()** | Credentials have not expired | Credentials have expired |

Notice the double-negative naming: **isAccountNonLocked() == true** means **not locked**. If the database has a **locked** column, the mapping must be **accountNonLocked = !locked**. With Spring Security's builder, the **accountLocked(locked)** method takes the flag in the positive sense.

**DaoAuthenticationProvider** checks these statuses in standard username/password authentication. A custom provider might implement different logic; always test in practice when account locking policies matter.

### 3.5. Should UserDetails Be a Database Entity?

Not necessarily. Spring Security includes the built-in class **org.springframework.security.core.userdetails.User** implementing `UserDetails`. You can read an **AccountEntity** from JPA and convert it into **User.withUsername(...).password(...).authorities(...).build()**.

Avoid returning the entity itself as the principal by default: entities can hold private fields, lazy relationships, mutable state, and password hashes. If you need `accountId`/`tenantId` in the principal, build a **small, purpose-built** custom `UserDetails`, or a separate `CurrentUser` adapter. Never serialize a raw `UserDetails` as an endpoint's JSON body.

## 4. The UserDetailsService Contract and UsernameNotFoundException

Interface:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

This is a signature excerpt for reading, not a standalone Java file.

**loadUserByUsername(username)** must:

1. Query the right data source and identifier scope.
2. If the account exists, return a `UserDetails` with the password hash, authorities, and accurate statuses.
3. If not found, **throw UsernameNotFoundException**; never return null and never fabricate a default account.
4. Never set `SecurityContextHolder` itself, never manually "log in" the user, and never check the raw password because the method contract has no raw password.

**UsernameNotFoundException** is an authentication-layer detail. In **DaoAuthenticationProvider**, username-not-found errors are normally masked into a generic bad-credentials error by default to curb user enumeration. Do not turn the distinction between "username does not exist" and "wrong password" into an exploitable public message.

**UserDetailsService is not an account registration or password-change API.** Creating users, locking users, granting roles, resetting passwords, MFA, email verification, and revoking sessions/tokens belong to other workflows and components. **UserDetailsManager** is a separate interface adding some user-management operations, which still does not equate to a complete IAM system.

## 5. Complete Demo: Spring Boot 3, Java 17+, and HTTP Basic

To clearly observe valid users, wrong passwords, missing authorities, locked accounts, and disabled accounts, we build a small Spring Boot application with an in-memory account repository. This organization stays the same when replacing the repository with Spring Data JPA.

Demo accounts:

| User | Password for localhost use | Authorities | Status |
| --- | --- | --- | --- |
| alice | alice123 | ROLE_USER, profile:read | Active |
| admin | admin123 | ROLE_ADMIN, profile:read | Active |
| locked | locked123 | ROLE_USER | Locked |
| disabled | disabled123 | ROLE_USER | Disabled |

Hardcoded passwords are strictly for hands-on practice. Production requires proper credential/secret management, brute-force protection, and TLS.

### 5.1. Dependencies and Packages

Create a **Spring Boot 3.x + Java 17+** project with the Gradle Wrapper, adding to the existing **build.gradle** (Spring Boot plugin and dependency management already declared):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create files with the following structure:

~~~text
src/main/java/com/example/accountauth/
  AccountAuthApplication.java
  DemoAccount.java
  DemoAccountRepository.java
  AccountUserDetailsService.java
  SecurityConfig.java
  AccountController.java

src/test/java/com/example/accountauth/
  AccountAuthTest.java
~~~

### 5.2. AccountAuthApplication.java

~~~java
package com.example.accountauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountAuthApplication.class, args);
    }
}
~~~

### 5.3. DemoAccount.java: Application's Own Domain Model

~~~java
package com.example.accountauth;

import java.util.Set;

public record DemoAccount(
    String username,
    String passwordHash,
    boolean enabled,
    boolean accountNonExpired,
    boolean accountNonLocked,
    boolean credentialsNonExpired,
    Set<String> authorities
) {
}
~~~

`DemoAccount` **does not implement UserDetails**. Separating the data model from the security abstraction avoids coupling the entire domain to Spring Security. In a real application, the account model may include ID, tenant, timestamps, additional statuses, and authority relationships.

### 5.4. DemoAccountRepository.java: Account Source

~~~java
package com.example.accountauth;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

@Repository
public class DemoAccountRepository {

    private final Map<String, DemoAccount> accounts;

    public DemoAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice", new DemoAccount(
                "alice", encoder.encode("alice123"),
                true, true, true, true,
                Set.of("ROLE_USER", "profile:read")
            ),
            "admin", new DemoAccount(
                "admin", encoder.encode("admin123"),
                true, true, true, true,
                Set.of("ROLE_ADMIN", "profile:read")
            ),
            "locked", new DemoAccount(
                "locked", encoder.encode("locked123"),
                true, true, false, true,
                Set.of("ROLE_USER")
            ),
            "disabled", new DemoAccount(
                "disabled", encoder.encode("disabled123"),
                false, true, true, true,
                Set.of("ROLE_USER")
            )
        );
    }

    public Optional<DemoAccount> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
~~~

In this demo, **encoder.encode(...)** is only called when initializing the in-memory repository. With a real database, the **password hash is already stored** when a user creates/changes a password; repository queries only read the hash. Because BCrypt uses a salt, the same raw password can yield different hash strings across runs, which is normal behavior.

### 5.5. AccountUserDetailsService.java: Converting Accounts into UserDetails

~~~java
package com.example.accountauth;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final DemoAccountRepository accounts;

    public AccountUserDetailsService(DemoAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        if (username == null || username.isBlank()) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        DemoAccount account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountExpired(!account.accountNonExpired())
            .accountLocked(!account.accountNonLocked())
            .credentialsExpired(!account.credentialsNonExpired())
            .build();
    }
}
~~~

Explanation:

- **@Service** registers a `UserDetailsService` bean for Spring Security.
- **findByUsername(...)** only loads data; it receives no raw password from the request.
- **orElseThrow(...)** ensures the service never returns null for missing usernames.
- **password(...)** receives the **stored hash**, without re-hashing the hash.
- **authorities(...)** receives the exact authority strings decided by the application.
- **disabled(...)**, **accountExpired(...)**, **accountLocked(...)**, and **credentialsExpired(...)** reflect statuses properly with negation where required.
- **User.withUsername(...)** creates a Spring Security `UserDetails`. Returning `UserDetails` **does not mark login as successful yet**.

### 5.6. SecurityConfig.java: Basic and PasswordEncoder

~~~java
package com.example.accountauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me").authenticated()
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

With **one UserDetailsService bean** and a **PasswordEncoder** in standard username/password setup, Spring Security can configure a suitable **DaoAuthenticationProvider** using that service and encoder. When an application has multiple `UserDetailsService` beans, custom `AuthenticationProvider`s, or a custom `AuthenticationManager`, you must wire them explicitly and verify which provider is selected; do not assume Spring will guess your intent.

**SessionCreationPolicy.STATELESS** ensures the example does not use `HttpSession` to read/save `SecurityContext` for subsequent requests. HTTP Basic authenticates from the header on every request; `UserDetailsService` still works with form-login/session mechanisms when configured accordingly. Statelessness is not a requirement of `UserDetailsService`.

In practice, security configuration also needs to account for CSRF, CORS, error dispatches, health checks, and other endpoints; this demo uses only GET to study authentication.

### 5.7. AccountController.java

~~~java
package com.example.accountauth;

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

The controller **does not need to call `UserDetailsService` itself**. It receives the `Authentication` produced after authentication. In the demo, the principal is typically the `UserDetails` returned by the service; with JWT, OAuth2 login, or other mechanisms, the principal may be a different type, so do not cast every principal to `UserDetails`.

### 5.8. Running and Verifying Responses

From the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Send requests from another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u locked:locked123 http://localhost:8080/me
curl -i -u disabled:disabled123 http://localhost:8080/me
curl -i -u nobody:password http://localhost:8080/me
~~~

With the demo application running standalone, **expected** results:

| Request | Status | Body on success or explanation |
| --- | --- | --- |
| Anonymous → GET /public | **200** | **public** |
| Anonymous → GET /me | **401** | No valid credentials provided |
| alice + correct password → GET /me | **200** | **alice ROLE_USER,profile:read** |
| alice → GET /admin | **403** | Valid authentication, missing ROLE_ADMIN |
| admin → GET /admin | **200** | **admin-only** |
| alice + wrong password → GET /me | **401** | Rejected by PasswordEncoder |
| locked + correct password → GET /me | **401** | Account is locked |
| disabled + correct password → GET /me | **401** | Account is disabled |
| nobody → GET /me | **401** | Account does not exist |

**401** with HTTP Basic typically includes a **WWW-Authenticate** header requesting authentication. **403** here indicates an authenticated account lacking permissions. Error bodies and details have no fixed format unless an explicit exception handler is configured. HTTP responses are displayed by **curl -i**, not the Java app's stdout.

Never use demo passwords in production. **Basic encodes credentials with Base64, not security encryption**: HTTPS/TLS is mandatory over networks, and avoid placing real passwords in command history, logs, or source code.

## 6. Testing with MockMvc: Success, Bad Credentials, Locked, and Missing Authority

Create **src/test/java/com/example/accountauth/AccountAuthTest.java**:

~~~java
package com.example.accountauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountAuthTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void aliceAuthenticatesWithCorrectPassword() throws Exception {
        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER,profile:read"));
    }

    @Test
    void missingAndWrongPasswordAreRejected() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUsernameIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("nobody", "password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAndDisabledAccountsCannotAuthenticate() throws Exception {
        mvc.perform(get("/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("disabled", "disabled123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedDoesNotMeanAuthorized() throws Exception {
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

The tests go through **HTTP Basic filter → AuthenticationManager → DaoAuthenticationProvider → UserDetailsService → PasswordEncoder** and then authorization. **httpBasic(...)** in Spring Security Test adds a credential header to the request rather than injecting a pre-authenticated principal that bypasses password verification. Essential negative cases include wrong passwords, non-existent usernames, locked/disabled accounts, and insufficient permissions.

## 7. Moving from In-Memory to Spring Data JPA

With a real database, you keep the **UserDetailsService** interface. Simply replace the data source with a repository, then convert **AccountEntity** into `UserDetails`.

Example JPA repository (snippet requires appropriate entity and imports):

~~~java
public interface AccountJpaRepository
        extends JpaRepository<AccountEntity, Long> {

    Optional<AccountEntity> findByLoginName(String loginName);
}
~~~

Inside an adapter, you can read and map data as follows (**non-standalone** snippet; requires entity, repository, and `resolveAuthorities` definitions):

~~~java
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

**resolveAuthorities(...)** is a method you implement to map roles/permissions from your application's schema. If your data stores `account-expired`/`credentials-expired` flags, map all of those statuses as well; otherwise, define their defaults explicitly.

Additional concerns to address:

- **Unique identity:** username/email must be unique under defined rules; with multi-tenancy, uniqueness may be per **tenant_id + normalized_username**. `UserDetailsService` only receives a username string, so design a trustworthy way to determine the tenant or use a suitable provider.
- **Password storage:** the database stores hashes produced by BCrypt/Argon2 or an appropriate encoder. Never store raw passwords and never re-hash inside `loadUserByUsername`.
- **Role/permission relationships:** avoid lazy-loading errors outside transactions or N+1 queries; choose appropriate queries/fetching when loading accounts.
- **Account status:** lock/disable/expiration flags must be mapped consistently and tested individually.
- **Dynamic permissions:** changing roles in the DB does not automatically update an `Authentication` saved in a session or already-issued access tokens; use cache invalidation, session invalidation, or token revocation/revalidation as required by policy.
- **Sensitive data:** never return entities or `UserDetails` directly over JSON; use a public DTO containing only permitted fields.
- **Account ID:** use a stable ID when checking ownership/tenant rather than relying solely on a mutable username.

## 8. PasswordEncoder: Common Misconceptions

### 8.1. Hashes of the Same Password Are Not Necessarily Equal

BCrypt uses a salt, so encoding the same password twice can produce two different hashes. When checking, use **matches(raw, storedHash)**, never **encode(raw).equals(storedHash)**.

A **standalone Java 17 example without external libraries** to illustrate that a raw password does not equal a string representing a hash (this example **does not perform real authentication**):

**PasswordEqualityDemo.java**

~~~java
public class PasswordEqualityDemo {
    public static void main(String[] args) {
        String raw = "alice123";
        String stored = "a-password-hash-not-raw-password";

        System.out.println(raw.equals(stored));
    }
}
~~~

Run:

~~~bash
javac PasswordEqualityDemo.java
java PasswordEqualityDemo
~~~

Exact stdout:

~~~text
false
~~~

Use Spring Security's **PasswordEncoder** for actual verification. The standalone example only shows that **direct string comparison between raw string and hash string is not password verification**.

### 8.2. BCrypt and DelegatingPasswordEncoder

- **BCryptPasswordEncoder** uses the BCrypt algorithm with salt/work factor, suitable for demos.
- **PasswordEncoderFactories.createDelegatingPasswordEncoder()** supports multiple encoders via a prefix on the stored password, e.g. **{bcrypt}...**. If switching to `DelegatingPasswordEncoder`, your schema/migration must ensure stored hashes use the proper format; missing or wrong prefixes cause authentication failures.
- Never use **NoOpPasswordEncoder**, fast plain hashes like raw MD5/SHA-256, or plaintext to store production passwords.
- Password encoders can support hash-upgrade policies via **UserDetailsPasswordService** when configured on the provider; merely declaring a `PasswordEncoder` does not automatically re-hash every row in the database.

Never put **matches(...)** inside `UserDetailsService`; that interface does not receive the raw password and is not an `AuthenticationProvider`.

## 9. Caches, Sessions, and Tokens Are Related but Not Identical

A `UserDetailsService` is invoked when a provider needs to load an account, yet **you cannot assume every authenticated request will always call the service again**:

- HTTP Basic in standard configurations may authenticate each request, though providers/components may introduce caching.
- Form login may create an `Authentication` and store it in a session, with subsequent requests restoring `SecurityContext` without re-verifying the password.
- A JWT Resource Server typically validates the JWT and converts claims into an `Authentication`; it does not call `UserDetailsService` by default.
- Opaque tokens usually go through introspection/lookup; that mechanism also does not use `UserDetailsService` by default.
- Once a session or token has been issued, changing a password, locking an account, or modifying roles in the database does not necessarily block all existing sessions/tokens immediately.

Therefore, if business requirements demand **immediate effect when locking an account**, design session invalidation, token revocation/revalidation, and caching policies. Modifying **loadUserByUsername(...)** alone does not solve the full login lifecycle.

**Spring WebFlux reactive** uses **ReactiveUserDetailsService**, which is a different interface from Servlet's synchronous `UserDetailsService`. Never run blocking database queries directly on the event loop in a reactive application.

## 10. Common Pitfalls and How to Fix Them

### 10.1. "UserDetailsService Is Never Called"

Trace the exact chain:

~~~text
HTTP request
  -> Does SecurityFilterChain match?
  -> Which authentication filter is enabled?
  -> Which AuthenticationManager/Provider is selected?
  -> Does the provider use DaoAuthenticationProvider?
  -> Which UserDetailsService bean does DaoAuthenticationProvider use?
  -> Does the repository query the right username/tenant?
~~~

If the application only configures Bearer JWT, do not expect **loadUserByUsername** to execute. If there are multiple **UserDetailsService** beans or a custom `AuthenticationManager`, verify how they are actually wired together.

### 10.2. "Correct Password Still Returns 401"

Check the encoder and stored hash format, username normalization, disabled/locked/expired flags, client credentials, user lookup, and query exceptions. If using `DelegatingPasswordEncoder` without matching prefixes in data, or if a **locked** column is mapped backwards, requests can be rejected even with the right raw password.

### 10.3. "Login Succeeds Yet Still Returns 403"

At this point authentication may have succeeded. Check the **ROLE_** prefix, authorities list, URL/method rules, ownership/tenant checks, and other protections like CSRF. Never turn `UserDetailsService` into an "always allow" workaround to fix a 403.

### 10.4. "Returning Null to Treat as Anonymous"

Contract violation. **loadUserByUsername** must return `UserDetails` or throw `UsernameNotFoundException`. Anonymous authentication is handled by dedicated mechanisms/filters, not by a fake null result from a database lookup.

### 10.5. "Returning Raw AccountEntity as API Response"

This can leak password hashes or internal fields and trigger serialization loops or lazy-loading exceptions. Return a public DTO containing only fields needed by the client. With custom principals, avoid storing sensitive data and never cast OAuth2/JWT principals blindly to an entity.

### 10.6. "Having UserDetailsService Automatically Gives a Registration Endpoint"

The interface only loads users for authentication. Registration, password changes, locking, and role grants are business flows that must be implemented, validated, and audited separately.

### 10.7. "Once Logged In, All Authority Changes Apply Immediately"

Sessions, JWTs, and caches have their own lifecycles. For accounts whose permissions are revoked, design strategies for sessions, tokens, and cached authorization state. Explicitly test the case where **an account is locked while already logged in**.

### 10.8. "More Fields in Principal Is Better"

Keep only the data needed for authorization and identification. A principal may be stored across sessions, printed in logs, or appear in exceptions; minimize sensitive data inside it.

### 10.9. "Skipping Rate Limits Because Passwords Are Hashed"

Password hashing protects stored data at rest, but does not by itself stop credential stuffing and online brute-force attacks. Implement rate limiting, sensible account lockout policies, monitoring, MFA where needed, and error messages that do not aid username enumeration.

## 11. Systematic Debugging Approach

Enable Spring Security logging in development if needed:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

When debugging, check step by step: which chain the request enters; whether Basic/form login headers are valid; which provider runs; whether username lookup returns an account; whether the hash matches the encoder; the four status flags; authorities; and authorization rules. **Never log raw passwords, Authorization headers, tokens, or password hashes**.

When a test fails, distinguish:
- **401**: authentication has not succeeded or credentials were not accepted per the entry point.
- **403**: the request usually already has an `Authentication` but lacks permission, or another filter such as CSRF rejected it.
- **302**: form login may redirect to a login page instead of issuing an HTTP Basic challenge.

Status codes depend on `AuthenticationEntryPoint`/`AccessDeniedHandler` configuration, filter chains, and client type; never infer the root cause from the number alone.

## 12. Self-Check Questions

**Question 1.** Does `UserDetailsService` receive the password entered by the user?

**Answer:** No. The interface only receives the username and returns a `UserDetails` containing the hash and authorities. `DaoAuthenticationProvider` with `PasswordEncoder` checks the raw password.

**Question 2.** `alice` is found in the database, but the request's password is wrong. Should the service throw `UsernameNotFoundException`?

**Answer:** No. `alice`'s record exists, so the service returns `UserDetails`; the provider then rejects the password.

**Question 3.** The database has flag **locked=true**. What should **isAccountNonLocked()** return?

**Answer:** **false**. Spring Security's builder can use **accountLocked(true)**.

**Question 4.** Why might an account with authority **ADMIN** receive 403 under **hasRole("ADMIN")**?

**Answer:** With the default prefix, `hasRole("ADMIN")` requires the string **ROLE_ADMIN**.

**Question 5.** If the username does not exist, what should `loadUserByUsername` do?

**Answer:** Throw **UsernameNotFoundException**, never return null or a dummy user.

**Question 6.** Can `UserDetailsService` authenticate every Bearer JWT?

**Answer:** Not by default. A JWT Resource Server uses its own decoder/provider mechanism; integrate account lookup only if your design requires it.

**Question 7.** Why is a newly generated BCrypt password hash not equal to an older hash of the same password?

**Answer:** BCrypt uses a salt; comparison requires **matches(raw, storedHash)**.

**Question 8.** Does logging in successfully with `ROLE_USER` mean the user can read every document?

**Answer:** No. You need authorization by action, resource, ownership, and tenant.

**Question 9.** Does locking an account in the DB automatically invalidate already-issued JWTs/sessions?

**Answer:** Not always. You need appropriate revocation, re-verification, or lifetime limits.

**Question 10.** When does Spring Security obtain an `Authentication` from `UserDetailsService`?

**Answer:** `UserDetailsService` returns **data**; after the provider verifies credentials and account status, the resulting `Authentication` is created and placed into `SecurityContext` according to the authentication flow.

## Official References

- Spring Security — **UserDetailsService**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — **Password Storage**: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security API — **UserDetails**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html

**Remember:** **UserDetailsService looks up accounts; UserDetails carries hashes, status, and authorities; DaoAuthenticationProvider uses PasswordEncoder to verify passwords; Authentication records the valid identity; authorization decides whether the request is permitted to proceed.** Keeping these boundaries clear lets you move account storage from in-memory to a database without mixing up security responsibilities.
