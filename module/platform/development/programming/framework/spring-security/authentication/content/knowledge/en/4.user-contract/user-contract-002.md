# UserDetailsService Only Loads Users, It Does Not Perform the Entire Login

## Lesson Objectives

In Spring Security, `UserDetailsService` is the contract for **reading user information by username**. It acts as the data source for username/password authentication, but merely returning a `UserDetails` **does not prove the caller has successfully logged in**.

After this lesson, you should be able to explain:

1. What `UserDetailsService.loadUserByUsername(...)` takes, returns, and how it handles a missing account.
2. How `UserDetails` differs from `Authentication`, and why account data is not yet a verified identity.
3. Which components actually receive credentials, compare passwords, check account status, produce the authentication result, and attach that result to `SecurityContext`.
4. How a custom service reading from a database is used in Spring Security 6.x / Spring Boot 3.x.
5. Why **calling `loadUserByUsername` directly does not log a user in**, and why not every authentication mechanism uses `UserDetailsService`.
6. Common pitfalls regarding password hashes, account status, caching, database errors, and Servlet vs. reactive integration.

This lesson belongs to the **User Contract** section of the Spring Security Authentication module. Main examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring MVC/Servlet. Cases like JWT, OIDC, and reactive are used to clarify contract boundaries rather than replacing dedicated topics for each mechanism.

## 1. What Exactly Is the UserDetailsService Contract?

The `org.springframework.security.core.userdetails.UserDetailsService` interface is very small:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

This is **a simplified signature to understand the API**, not a source file to create in a project. The interface has a single read task: given a `username`, find the full user record as a `UserDetails`.

- **Input:** the login name the authentication side wants to look up. This value does not by itself prove the validity of the account or password.
- **Output:** a `UserDetails` object containing username, stored password (usually a hash), `GrantedAuthority` instances, and account status flags. The result **must not be `null`**.
- **Not found:** throw `UsernameNotFoundException`; do not return `null` or a dummy `UserDetails` marked enabled to "avoid errors".
- **No password parameter:** the method does not receive the raw password just entered by the user, so it cannot perform the full password comparison step under this contract.
- **Read-only contract:** the interface does not define creating accounts, changing passwords, logging out, storing sessions, or issuing tokens. Account management operations belong to the business layer or `UserDetailsManager`, an extended interface adding CRUD.

Common implementations: `InMemoryUserDetailsManager`, `JdbcUserDetailsManager`, `JdbcDaoImpl`, a custom JDBC/JPA adapter, or a service fetching information from a trusted account store. They differ in **data source**, without replacing the role of the authentication provider.

> **Principle:** "Loading Alice" only means the system found Alice's profile. To "log in as Alice", the system must still verify evidence and authentication conditions and then create a trusted `Authentication`.

### 1.1. Distinguishing UserDetails, Authentication, and SecurityContext

| Object | Answers the Question | Created or Used By |
| --- | --- | --- |
| `UserDetails` | Account profile: username, password hash, authorities, flags | Returned by `UserDetailsService`; used as input by provider |
| Unauthenticated `Authentication` | What identity does the caller **claim** and what credentials do they present? | Filter/controller creates authentication request |
| Authenticated `Authentication` | Evidence has been verified—what are the trusted principal and authorities? | Returned by `AuthenticationManager` / `AuthenticationProvider` |
| `SecurityContext` | What is the current identity of the processing execution? | Security filters/integration points write and read context |
| `SecurityContextHolder` | How to access the context in the current Servlet application | Typically stored per-thread during a request |

A `UserDetails` record can exist in a database for months without a single login request. Another `Authentication` can be created after a JWT is verified without ever calling `UserDetailsService`. Do not equate creating `UserDetails` with putting a user into `SecurityContextHolder`.

### 1.2. How Are the Fields on UserDetails Used?

The `UserDetails` contract provides:

- `getUsername()`: username of the loaded profile; may be canonicalized differently in letter casing from the input.
- `getPassword()`: stored string, usually a **password hash/encoded password**, not a raw password.
- `getAuthorities()`: permissions/roles attached to the account, used during authorization once authentication succeeds.
- `isAccountNonExpired()`: account has not expired.
- `isAccountNonLocked()`: account is not locked.
- `isCredentialsNonExpired()`: account's credentials have not expired.
- `isEnabled()`: account is enabled.

It is `DaoAuthenticationProvider` (and its superclass checking status) that reads the flags and produces the appropriate authentication result. `UserDetailsService` is only tasked with loading and returning accurate data. An implementation **may** enforce data-read constraints (such as not exposing accounts outside the allowed tenant), but should not arbitrarily grant `authenticated` status, issue access tokens, or write HTTP responses.

## 2. The Complete Login Flow: The Service Is Just One Step

With Servlet and username/password authentication via HTTP Basic or form login, the high-level flow is:

~~~text
(1) Client sends username + password
         |
         v
(2) Matching security filter (BasicAuthenticationFilter,
    UsernamePasswordAuthenticationFilter, ...)
         |
         | creates an unauthenticated
         | UsernamePasswordAuthenticationToken
         v
(3) AuthenticationManager (usually ProviderManager)
         |
         v
(4) DaoAuthenticationProvider
         |
         +----> (5) UserDetailsService.loadUserByUsername(username)
         |             |
         |             +--> returns UserDetails with hash, authorities, flags
         |
         +----> (6) checks account status and credentials
         |             |
         |             +--> PasswordEncoder.matches(rawPassword, storedHash)
         |
         +----> (7) success: creates authenticated Authentication
         |             failure: throws AuthenticationException
         v
(8) Security filter handles result
         |
         +--> success: places Authentication into SecurityContext
         |    and saves/restores context via configured mechanism
         |
         +--> failure: HTTP 401 or appropriate login error flow
         v
(9) Authorization checks access rights before entering controller
~~~

The model above is for understanding responsibilities; exact check order may vary by provider and cache configuration. The key point is that **the service loads data**, while **the provider/manager authenticates** and **the filter handles the request, result, and context**.

### 2.1. AuthenticationManager and ProviderManager

`AuthenticationManager.authenticate(Authentication request)` is the contract for checking an authentication request and returning a resulting `Authentication`, or throwing `AuthenticationException`. `ProviderManager` typically selects an `AuthenticationProvider` suited to the token type. For username/password stored in a typical data source, the provider is `DaoAuthenticationProvider`.

A system may have multiple providers (password, pre-auth, custom token). Having a `UserDetailsService` bean does not automatically route every authentication request through it: only providers configured to use that service and selected for the request will call `loadUserByUsername`.

### 2.2. What DaoAuthenticationProvider Does That the Service Does Not

`DaoAuthenticationProvider` uses `UserDetailsService` and `PasswordEncoder`. For matching username/password requests, it:

1. Loads the corresponding account by username (or uses `UserDetails` from cache if present and valid per configuration).
2. Checks account flags such as locked/disabled/expired.
3. Uses `PasswordEncoder.matches(rawPassword, userDetails.getPassword())` to compare the caller's password against the stored hash.
4. When needed, checks credential status and applies additional provider checks.
5. If valid, creates an authenticated `UsernamePasswordAuthenticationToken` with the appropriate principal and authorities.
6. If invalid, raises an appropriate `AuthenticationException` (e.g., `BadCredentialsException`, `DisabledException`, or `LockedException`).

`PasswordEncoder` performs secret comparison/encoding; it is **not** `UserDetailsService`'s responsibility. Do not grab `getPassword()` from the account and compare strings with `equals(rawPassword)`: that breaks secure hashing and leads to storing plaintext passwords.

### 2.3. Filters and SecurityContext Continue the Work

After receiving a successful `Authentication`, the corresponding filter puts the result into `SecurityContextHolder` (Servlet) and performs the appropriate success actions. With session-based form login, the context can be saved via `SecurityContextRepository`. With HTTP Basic, the browser/client typically sends credentials on every request; the user does not need to write a separate "login" endpoint.

`UserDetailsService` does not create cookies, redirect to a login page, return `401`/`302`, or decide endpoint permissions. Those tasks belong to the security filter chain, authentication entry point, success/failure handlers, session management, and authorization.

## 3. Reading UserDetails Is Not a Successful Login

Suppose you call directly:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("alice");
String name = user.getUsername();
boolean enabled = user.isEnabled();
~~~

This is **illustrative code inside a method with an injected `UserDetailsService userDetailsService`**, not a standalone program. After these three lines:

- The account may have been loaded successfully.
- The caller's raw password **has not been checked**.
- `AuthenticationManager.authenticate(...)` **has not been called**.
- `SecurityContext` **has not been updated**.
- The caller **does not yet have** a trusted identity to access protected endpoints.

Never create an authenticated token just because loading the user succeeded:

~~~java
// WRONG: dangerous snippet, never use for real login.
UserDetails user = userDetailsService.loadUserByUsername(username);
// A client-supplied username does not prove the caller owns the account.
// Do not set authenticated=true or attach a token to the context here.
~~~

If building a custom login mechanism, pass credentials to the configured `AuthenticationManager`/provider and only handle **the successful result**. If implementing login outside built-in filters, you must also establish/save the context, handle session fixation, CSRF, and related steps properly with Spring Security; calling the manager alone does not complete the entire HTTP login lifecycle.

## 4. Runnable Java 17+ Example: Spring Boot Using UserDetailsService Only for Lookup

The example below creates a Spring MVC web application with HTTP Basic and three endpoints `/public`, `/me`, `/admin`. We explicitly provide a `UserDetailsService` bean backed by a `Map`, and a `PasswordEncoder` bean. Spring Security uses the service via the username/password authentication mechanism when supporting configuration is present; we **do not write password comparison code inside the service**.

### 4.1. Initializing the Project

Create a Maven project on Spring Initializr with:

- Java 17 (or Java 21), Spring Boot 3.x.
- Dependencies: **Spring Web** (`spring-boot-starter-web`) and **Spring Security** (`spring-boot-starter-security`).
- Package: `com.example.demo`.

Create the file **`src/main/java/com/example/demo/UserDetailsLookupApplication.java`**:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class UserDetailsLookupApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsLookupApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .disabled(true)
            .build();

        Map<String, UserDetails> records = Map.of(
            "alice", alice,
            "disabled", disabled
        );

        return username -> {
            UserDetails account = records.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Account not found");
            }
            return account;
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "Hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin only";
        }
    }
}
~~~

The components have clear separation of roles:

- The `userDetailsService(...)` bean only looks up the `Map`, returning `UserDetails` or throwing `UsernameNotFoundException`.
- The `passwordEncoder()` bean defines how to hash/match passwords; the demo uses BCrypt.
- `SecurityFilterChain` configures accessible areas, enables HTTP Basic so Spring Security has a credential entry point.
- The username/password provider wired by Spring Security will use the service and encoder to verify credentials.
- Controller `/me` receives `Authentication` **after** the authentication filter succeeds; it does not call the service to assume the client is logged in.
- `/admin` requires role `ADMIN`; `alice` only has `ROLE_READER` so she will be rejected even with the right password.
- Account `disabled` has the right password, but `isEnabled() == false`, so the provider will reject it when checking account status.

Version note: the example targets Spring Boot 3.x and Spring Security 6.x. If you explicitly register another `AuthenticationManager` or `AuthenticationProvider`, how the service is wired into the manager may change; in that case inspect the application's own configuration. Do not treat the mere existence of a `UserDetailsService` bean as a guarantee that all authentication types use it.

### 4.2. Running and Verifying Results

In the Maven project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell use `.\mvnw.cmd spring-boot:run`. Open another terminal and call:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong-password http://localhost:8080/me
curl -i -u nobody:demo-pass http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/admin
~~~

If `curl` in PowerShell is an alias, use `curl.exe`. Main results:

| Request | Expected HTTP Status | Observable Content |
| --- | --- | --- |
| `GET /public` without credentials | `200 OK` | Body `public` |
| `GET /me` without credentials | `401 Unauthorized` | HTTP Basic challenge; no `Hello alice` body |
| `GET /me` with `alice:demo-pass` | `200 OK` | Exact body: `Hello alice` |
| `GET /me` with `alice:wrong-password` | `401 Unauthorized` | Wrong password rejected |
| `GET /me` with `nobody:demo-pass` | `401 Unauthorized` | Account not found |
| `GET /me` with `disabled:demo-pass` | `401 Unauthorized` | Account disabled despite right password |
| `GET /admin` with `alice:demo-pass` | `403 Forbidden` | Authenticated but missing `ROLE_ADMIN` |

Headers, error response bodies, and header ordering may differ by servlet container, config, and client. Do not assume `UsernameNotFoundException` will be exposed to the HTTP client; providers typically turn wrong username and wrong password into a generic error to prevent account enumeration.

**What this test proves:** with `UserDetailsService`, the `alice` account is loaded; yet there must be a path through the authentication filter, manager, provider, and encoder for the HTTP request to receive `200`. The `disabled` account shows that "read succeeded" does not equate to "valid authentication". The `/admin` endpoint shows that "valid authentication" is still distinct from "authorized".

### 4.3. What If You Only Call the Service Without Going Through the Filter?

You can call the bean directly in a `CommandLineRunner` or test:

~~~java
// Illustrative code inside a method with UserDetailsService injected.
UserDetails alice = userDetailsService.loadUserByUsername("alice");
System.out.println(alice.getUsername());
System.out.println(alice.isEnabled());
~~~

When the service uses the data in the example above, the two printed lines will be:

~~~text
alice
true
~~~

Those two lines only verify lookup data. They **do not** create a session, issue a token, guarantee `SecurityContextHolder.getContext().getAuthentication()` contains Alice, or create a logged-in request. If you already have an HTTP request from another user, reading Alice's data also confers no right to "switch" that request to Alice.

## 5. Changing Data Sources: Repository/Database Does Not Change the Contract

In a real application, `UserDetailsService` typically converts an account entity into `UserDetails`, for example:

~~~text
POST /login / Authorization header
         |
         v
DaoAuthenticationProvider
         |
         +--> AccountRepository.findByUsername(username)
                 |
                 +--> AccountEntity
                        username
                        passwordHash
                        enabled
                        locked
                        authorities
                 |
                 v
              UserDetails
         |
         +--> PasswordEncoder.matches(...)
         +--> account status checks
         |
         v
     Authenticated Authentication
~~~

The repository layer should not know about filters or HTTP sessions; the `UserDetailsService` layer acts as an **adapter** between domain users and Spring Security. A sensible division of work:

| Component | Should Be Responsible For |
| --- | --- |
| `AccountRepository` | Querying domain accounts from the database |
| `UserDetailsService` | Looking up by username and transforming account data to `UserDetails` |
| `PasswordEncoder` | Hashing and matching passwords |
| `DaoAuthenticationProvider` | Checking raw credentials against hash and account status |
| `AuthenticationManager` | Coordinating providers and returning authentication result |
| Filter + `SecurityContext` | Receiving HTTP requests and holding the authentication result in the proper scope |
| Authorization layer | Checking roles/authorities to protect endpoints/methods |

Do not take a raw password from an HTTP request and pass it into `loadUserByUsername` via a concatenated string like `username + ":" + password`. The contract only expects the username; putting passwords into lookups can leak secrets in logs, queries, or cache keys. For tenanted systems, the lookup key may need to be structured via an appropriate authentication mechanism rather than blindly trusting an unverified tenant header.

### 5.1. An Illustrative Database-Backed Adapter

The following example **is not a standalone file**: it assumes the application already has domain types `AccountRepository`, `Account`, and the methods listed in the comments. The goal is to illustrate the adapter boundary without tying the lesson to specific JPA/JDBC code.

~~~java
@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        // Assumed domain contract:
        // repository.findByUsername(username) -> Optional<Account>
        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!account.enabled())
            .build();
    }
}
~~~

Imports for this illustrative snippet include `org.springframework.stereotype.Service`, `UserDetailsService`, `UserDetails`, `User`, and `UsernameNotFoundException` from Spring Security. It assumes `account.authorities()` returns `Collection<? extends GrantedAuthority>`, matching the `User.UserBuilder.authorities(...)` overload; `account.passwordHash()` is the stored hash. Other lock/expiry fields if managed by the domain must be mapped accurately rather than defaulting everything to always valid.

For this snippet to compile/run, you must provide real `AccountRepository`/`Account` types and the project's persistence adapter. Do not place it alongside the `userDetailsService(...)` bean in the runnable example without explicitly picking one implementation; multiple beans of the same type can make authentication configuration ambiguous.

**Role mapping rule:** the builder's `roles("ADMIN")` auto-generates the `ROLE_ADMIN` authority; whereas `authorities(...)` uses the passed permission names as-is. If the domain already stores `ROLE_ADMIN`, use `authorities(...)` appropriately to avoid accidentally producing `ROLE_ROLE_ADMIN` by prefixing twice.

## 6. Error Cases: What Does the Service Report, What Does the Provider Report?

### 6.1. Username Does Not Exist

`UserDetailsService.loadUserByUsername("nobody")` must throw `UsernameNotFoundException`. However, `DaoAuthenticationProvider` under the default configuration of `AbstractUserDetailsAuthenticationProvider` typically hides this detail as a `BadCredentialsException`, grouped with a wrong password. That reduces the attacker's ability to enumerate valid usernames based on error content.

Do not return `null`, create an empty user with an arbitrary password, or let callers guess whether an account exists from public responses. If the backend has separate auditing, it can record a standardized internal error code without leaking identity or secrets.

### 6.2. Wrong Password Even Though Account Exists

The service can still return a completely valid `UserDetails`. The provider compares the password via `PasswordEncoder` and reports an error when it does not match. Therefore, **a successful lookup result does not guarantee a successful login result**.

Do not compare passwords with `String.equals` against a hash. If the service returns an improperly formatted hash, or the encoder is incompatible with the format, authentication fails even if the user enters the right raw password.

### 6.3. Account Locked, Expired, or Disabled

The service returns status data (usually inside `UserDetails`), while the provider evaluates it. `DisabledException`, `LockedException`, `AccountExpiredException`, and `CredentialsExpiredException` are the failures corresponding to the respective flags.

Do not ignore flags by always building `UserDetails` with `enabled(true)` just to make a test login succeed. If the account administration system allows unlocking, the state-change flow belongs to authorized account management logic, not inside `loadUserByUsername`.

### 6.4. Database/Identity Store Failure

Do not equate a database outage with "user does not exist". A connection error or timeout may need to be translated into an appropriate authentication infrastructure error and observed in monitoring. Never return a special account or skip password checks when the repository fails (fail-open). Also avoid exposing connection strings, SQL, or username lists in HTTP errors.

### 6.5. No GrantedAuthority

The JavaDoc contract requires a fully populated record and specifies `UsernameNotFoundException` when a user cannot be found or has no `GrantedAuthority`. For applications with users who have no roles, decide on an appropriate policy representation, avoiding implicitly granting permissions "just to load". Do not turn request permissions into arbitrary data inside the service.

## 7. Load Timing and the Cache/Session Story

A common misconception is "every protected request runs `loadUserByUsername` exactly once". In reality it depends on the authentication mechanism and configuration:

- With **form login + session**, logging in may load the user, and subsequent requests restore the `SecurityContext` stored in the session. The service does not necessarily get called on every page.
- With **HTTP Basic**, the client typically resends credentials on every request; the security filter/provider may re-check, but do not write business logic relying on a fixed lookup count.
- `AbstractUserDetailsAuthenticationProvider` supports a `UserCache`; it defaults to `NullUserCache` in standard setups. If caching is used, the provider still has to process password checks and update rules; do not treat a cache lookup as proof of authentication.
- When changing passwords, locking/unlocking, or revoking permissions, you must design consistency across caches, sessions, and tokens. Changing repository data does not always immediately clear every previously stored `Authentication`.

**Important security point:** `ProviderManager` typically erases sensitive credentials on a successful authentication if the object supports `CredentialsContainer`. If `Authentication` holds a reference to the exact cached `UserDetails` object, credential erasure can affect the cached data unless copied appropriately. Manage caching and credential erasure intentionally; do not disable secret erasure just to treat the symptom when you can fix how the cache stores objects.

Do not let the service keep a global "currently logged-in user" variable or a static `SecurityContext`. Spring singleton beans serve multiple requests/users; login state belongs to the context appropriate for each request/session/token.

## 8. Not All Authentication Uses UserDetailsService

`UserDetailsService` is specifically tied to account-lookup-style username/password authentication. Several other mechanisms have their own identity sources or verification methods:

| Mechanism | Must It Call `UserDetailsService`? | Why |
| --- | --- | --- |
| Form login with `DaoAuthenticationProvider` | Yes, in the usual lookup path (barring valid optimizations/caches) | Needs user record and password hash |
| HTTP Basic using `DaoAuthenticationProvider` | Yes, per provider configuration supporting Basic username/password | Credentials are passed into the provider |
| JWT resource server | **No** by default | Token is decoded/verified for signature, issuer, expiration, and claims per resource server |
| OAuth2 login / OpenID Connect | **No** by default | Identity comes from OAuth2/OIDC flow and corresponding principal/token |
| SAML2 login | **No** by default | Identity is based on a verified SAML assertion |
| mTLS / X.509 or pre-auth | **No** by default | Proof may be a certificate or a trusted source |
| Custom API key provider | **Not** required | Provider may look up API keys using its own model |

You can combine `UserDetailsService` to *enrich account data* after another mechanism has authenticated, but that is **a custom-designed integration**: verify the mapping between token principal and internal account, without blindly trusting unverified usernames/claims. Do not turn all mechanisms into fake calls to `loadUserByUsername` just to "look like form login".

### 8.1. Reactive WebFlux Uses a Different Contract

With Spring WebFlux, the common variant is `ReactiveUserDetailsService`:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

This is the simplified signature of the reactive interface; `Mono<UserDetails>` represents an asynchronous result. `MapReactiveUserDetailsService` is an in-memory implementation. `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` and `PasswordEncoder` to authenticate username/password in the reactive stack.

Like Servlet, **the reactive service also only finds accounts**; it does not verify the entire HTTP authentication on its own. Do not call blocking JDBC `loadUserByUsername` directly on the WebFlux event loop and assume the API is non-blocking. Choose an appropriate repository/reactive bridge; attach authentication to the Reactor Context through the Spring Security reactive pipeline rather than defaulting to thread-bound `SecurityContextHolder` like Servlet.

## 9. Spring Boot Configuration: Why a UserDetailsService Bean Is Not All of Security

In Spring Boot with the Spring Security starter, when no suitable customization exists, Boot may provide an in-memory user for development purposes. When you register your own `UserDetailsService` bean, the default user auto-configuration usually backs off in favor of that bean. However:

- **The `UserDetailsService` bean** determines the account lookup source.
- **The `SecurityFilterChain` bean** determines which requests are protected, enables Basic/form login/resource server, and defines authorization rules.
- **`AuthenticationManager` and `AuthenticationProvider`** determine which credential mechanisms are accepted; custom managers/providers can alter default wiring.
- **The `PasswordEncoder` bean** determines how password hashes are matched; hashes in the database must match the encoder type/configuration.
- **Success/failure handlers, session management, CSRF, CORS**, and other policies remain the responsibilities of their respective components.

The example configuration in section 4 explicitly enables `httpBasic(withDefaults())`. If you omit HTTP Basic and form login without enabling any other authentication mechanism, simply creating a `UserDetailsService` bean **does not automatically create a working login endpoint**. Conversely, if you use a custom `AuthenticationProvider` that does not call the service, the service bean may exist without participating in the flow.

Spring Boot documentation also notes that when modules such as OAuth2 Client, Resource Server, or SAML2 Service Provider are present, user auto-configuration has specific back-off conditions. Therefore, verify the application's actual beans and providers rather than assuming "defining the service is enough".

### 9.1. If You Need to Wire Manager and Provider Manually

In a manual configuration serving username/password, the basic wiring can be written as:

~~~java
DaoAuthenticationProvider dao =
    new DaoAuthenticationProvider(userDetailsService);
dao.setPasswordEncoder(passwordEncoder);

AuthenticationManager manager =
    new ProviderManager(java.util.List.of(dao));
~~~

This is **an illustrative snippet within a configuration that already has `UserDetailsService userDetailsService` and `PasswordEncoder passwordEncoder`**, not a standalone Java file and not meant to be added to the section 4 example. In Spring Security 6.x, the `DaoAuthenticationProvider(UserDetailsService)` constructor is a clear choice; set the encoder with `setPasswordEncoder(...)`. `ProviderManager` coordinates the provider.

If you want to implement a custom login endpoint outside built-in mechanisms, you must receive credentials, call `manager.authenticate(...)`, and only upon a successful result attach the context, save the session, or issue a token per the appropriate contract. Calling `loadUserByUsername(...)` in a controller and returning "login success" yourself skips the core of authentication.

## 10. Common Errors and How to Fix Them

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| User exists in database but login always returns `401` | Malformed hash, encoder mismatch, wrong password, provider not configured | Check provider, `PasswordEncoder.matches`, `UserDetails` mapping |
| `loadUserByUsername` succeeds but request stays anonymous | Calling the service alone does not authenticate or update context | Use authentication filter/manager; do not "log in" from lookup |
| `ClassCastException` when casting principal | Principal is not always the expected custom `UserDetails` type | Check `Authentication.getPrincipal()` and the actual authentication mechanism |
| Account is disabled yet still enters the application | Wrong status flag mapping or provider not checking as expected | Return `isEnabled()` properly; check provider and test disabled account |
| Wrong username returns detailed error, aiding account enumeration | Config exposes `UsernameNotFoundException` or response leaks info | Return generic auth error; control internal logging |
| Returning `null` when account not found | Violates `loadUserByUsername` contract | Throw `UsernameNotFoundException` |
| BCrypt hash in DB but using `NoOpPasswordEncoder` | Wrong comparison or insecure configuration | Use proper encoder; do not store cleartext |
| Adding UserDetailsService bean has no effect | Another custom AuthenticationProvider/Manager took precedence | Check wiring, provider order, and actual filter chain |
| Too many DB queries per request | HTTP Basic or provider/cache/session causing repeated lookups | Measure/trace, optimize repository and cache properly; do not disable security checks |
| Password hash altered in UserDetails cache | Erase-credentials may affect shared cached object references | Use copies/proper cache design; avoid keeping credentials long-term |
| WebFlux code blocks or principal is missing | Using blocking `UserDetailsService` or wrong ThreadLocal model | Use `ReactiveUserDetailsService` and reactive security context |

**Protect secrets when debugging:** never log raw passwords, Basic Authorization headers, session cookies, raw JWTs, or full hash strings. Only log minimal metadata (request ID, auth mechanism, status code) with proper read access and retention. HTTP Basic requires HTTPS in real environments.

## 11. Self-Check Questions and Exercises

**Question 1.** Code calls `UserDetailsService.loadUserByUsername("alice")` and gets a valid `UserDetails`. Can `SecurityContextHolder` immediately be set to Alice?

**Answer:** No. Credential and account policy verification has not happened yet. A valid authentication mechanism must be used, and the context must only be written from a trusted success result.

**Question 2.** Alice is in the database, but enters the wrong password. Must the service method throw `UsernameNotFoundException`?

**Answer:** No. The service can still return Alice; `DaoAuthenticationProvider` calls `PasswordEncoder.matches(...)` and rejects the invalid credentials.

**Question 3.** The account is disabled, but the password is right. Should the service return the record or treat it as a successful login?

**Answer:** The service returns the record with `isEnabled() == false`. The provider checks the status and does not grant a successful authentication. The service does not create a `SecurityContext`.

**Question 4.** There is a JWT Resource Server with no `UserDetailsService` registered. Can bearer tokens be authenticated?

**Answer:** Yes, if the resource server and decoder/introspector are configured properly. The JWT mechanism does not require performing username/password account lookup under this contract.

**Question 5.** A user changes their password in the database, but already has a logged-in session. Why might the user still be treated as authenticated?

**Answer:** Requests may restore the stored `Authentication` from the session without necessarily re-checking the password on every request. If logging out all sessions after a password change is required, that is a session/token revocation policy that must be implemented separately.

**Question 6.** `getUsername()`, `getPassword()`, and `getAuthorities()` all exist on `UserDetails`. Does that mean `UserDetailsService` has already checked roles and decided access to `/admin`?

**Answer:** No. The service provides data; the provider checks authentication; authorization uses authorities to decide endpoint access.

**Question 7.** You implement `loadUserByUsername` and inside it call `PasswordEncoder.matches(...)`, issue a JWT yourself, and write the session. What is the problem?

**Answer:** Three responsibilities have been mixed into a read-only lookup contract that does not even receive the raw password per its API, easily bypassing the authentication lifecycle, error handling, and security hooks. Separate lookup, authentication, and token/session handling into their proper components.

## 12. Practical Implementation Checklist

1. `loadUserByUsername` only looks up the username, returning a complete `UserDetails` or throwing `UsernameNotFoundException`, never returning null.
2. The password in `UserDetails` is a valid hash; the encoding method when creating/changing passwords is compatible with the `PasswordEncoder` used at login.
3. Map authorities following the `ROLE_` convention and map account status accurately to domain data.
4. `SecurityFilterChain` enables the required authentication mechanism, protects the right URLs, and avoids overly broad rules.
5. `AuthenticationManager` actually uses a provider backed by the declared service; check when other custom providers/managers exist.
6. Test non-existent account, wrong password, disabled/locked, right password, and insufficient role.
7. Do not log credentials or return detailed errors to unauthenticated users; have monitoring for account store infrastructure errors.
8. Cache/sessions have appropriate strategies when an account is locked, changes password, changes permissions, or is disabled.
9. With WebFlux, choose the proper reactive API and avoid blocking database calls on the event loop.
10. Never assume a user is logged in merely because `UserDetailsService` returned a result.

**Key takeaway:** `UserDetailsService` is **an account data loader**, not the entire login system. `DaoAuthenticationProvider` together with `PasswordEncoder` verifies credentials and account status; `AuthenticationManager` coordinates the outcome; security filters place the successful identity into `SecurityContext` and protect HTTP requests. Maintaining this boundary keeps code testable, secure, and able to swap data sources without breaking the authentication flow.

## References

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 API — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)
- [Spring Security 6.5 API — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Boot — Spring Security auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security 6.5 API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html)
