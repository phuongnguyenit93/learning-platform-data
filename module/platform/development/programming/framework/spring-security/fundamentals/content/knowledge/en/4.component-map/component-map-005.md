# AuthenticationManager and AuthenticationProvider in the Servlet Authentication Flow

## 1. The Problem and Responsibilities

When a user sends a username/password or another credential to a Spring Boot application, three tasks must be kept distinct: reading credentials from HTTP, verifying those credentials, and deciding what resources that identity may access.

In Servlet-based Spring Security:

- **AuthenticationManager** is the interface that receives an authentication request and returns an authenticated result or throws an error. It provides a clean boundary between code that extracts credentials and code that verifies them.
- **AuthenticationProvider** is the interface of the component that actually validates a specific kind of `Authentication`, such as username/password against a database or a configured token type.
- **ProviderManager** is the common implementation of `AuthenticationManager`, coordinating an ordered list of `AuthenticationProvider`s.
- **Authentication filters** extract credentials from HTTP, construct an input token, invoke the manager, and handle the outcome within the request flow.
- **SecurityContext** holds the active `Authentication` for the request; **authorization** then evaluates access permissions for the known identity.

**`AuthenticationManager` differs from `AuthorizationManager`**: one verifies identity, while the other checks permission to use a resource. A user can log in accurately and still be rejected when requesting an `ADMIN` endpoint.

Examples in this lesson use Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, and Spring MVC/Servlet. WebFlux uses `WebFilter` and a reactive security context unlike Servlet; `DaoAuthenticationProvider` APIs also change across Spring Security versions, so always consult the Javadoc for your exact dependency version when upgrading.

After this lesson, you will be able to identify each component, trace Basic/form login request flows, understand `supports`/null/exception behavior across multiple providers, read explicit `AuthenticationManager` configurations, and predict HTTP 200, 401, and 403 outcomes.

## 2. Component Map

| Component | Input / Duty | Output or Boundary |
| --- | --- | --- |
| **Authentication** | Principal, credentials, authorities, authenticated | May be an unverified request or an authenticated identity |
| **AuthenticationManager** | `authenticate(Authentication)` method | Returns an authenticated `Authentication` or throws `AuthenticationException` |
| **ProviderManager** | List of `AuthenticationProvider`s | Selects a matching provider and handles the result |
| **AuthenticationProvider** | `supports(Class)` and `authenticate(Authentication)` | Validates one kind of `Authentication` |
| **DaoAuthenticationProvider** | Username/password, `UserDetailsService`, `PasswordEncoder` | Authenticates user/password, returns principal and authorities |
| **UserDetailsService** | `loadUserByUsername(username)` | Only loads user data; does not verify passwords itself |
| **PasswordEncoder** | `encode` and `matches` | Hashes/verifies passwords; does not decide API permissions |
| **BasicAuthenticationFilter** | `Authorization: Basic` header | Calls manager, handles Basic flow, and sets `SecurityContext` |
| **UsernamePasswordAuthenticationFilter** | Form login username/password | Calls manager, handles success/failure per configuration |
| **SecurityContextHolder** | `Authentication` context in Servlet | Exposes current identity; does not authenticate on behalf of providers |
| **AuthorizationFilter** | Request rules and current `Authentication` | Permits or denies invoking the Controller |

A short way to remember: **Filters know where to get credentials; the Manager knows whom to ask to verify; Providers know how to verify; Context holds the result; Authorization decides whether entry to the resource is allowed.**

## 3. Authentication: Both Input and Output

The `Authentication` interface is used by Spring Security at two moments.

**Before authentication:** `BasicAuthenticationFilter` or `UsernamePasswordAuthenticationFilter` may build a `UsernamePasswordAuthenticationToken` with principal set to the client-claimed name, credentials set to the password, and `authenticated=false`. This newly built token is **not yet trusted**.

Illustrative Java snippet, inside a method with the necessary Spring Security imports:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

This creates only an **authentication request**, not proof that `alice` is logged in. Never take client-claimed roles and construct a trusted `Authentication`.

**After authentication:** The provider may return an `Authentication` with principal set to the verified `UserDetails`, `authenticated=true`, and trusted authorities such as `ROLE_USER`. Sensitive credentials may be erased after authentication.

| Attribute | Meaning | Example |
| --- | --- | --- |
| principal | Identity | `UserDetails` alice |
| credentials | Authentication evidence | Request password |
| authorities | Granted permissions | `ROLE_USER` |
| details | Additional metadata, mechanism-dependent | Auxiliary request data |
| `isAuthenticated()` | Token status | `true` after verification |

In typical configuration, **roles("USER")** produces **ROLE_USER**. Rule **hasRole("ADMIN")** checks for authority **ROLE_ADMIN**. Logging in validly does not imply permission for every endpoint or record.

## 4. Servlet Flow: HTTP Request to AuthenticationManager

Suppose a client calls a private endpoint with HTTP Basic:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6bGVhcm4xMjM=
~~~

The example header contains Base64 of `alice:learn123`. Base64 is encoding, **not security encryption**; real credentials must use HTTPS over networks.

High-level flow:

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
Matching SecurityFilterChain
    |
    v
BasicAuthenticationFilter
    |-- Reads Authorization: Basic ...
    |-- Builds unauthenticated UsernamePasswordAuthenticationToken
    v
AuthenticationManager.authenticate(...)
    |
    v
ProviderManager
    |-- Picks AuthenticationProvider with matching supports
    v
DaoAuthenticationProvider
    |-- UserDetailsService.loadUserByUsername("alice")
    |-- PasswordEncoder.matches(raw, encoded)
    |-- Checks account status flags
    |-- Returns authenticated Authentication
    v
ProviderManager -> BasicAuthenticationFilter
    |-- Handles post-authentication credentials
    |-- Filter places result into SecurityContext
    v
AuthorizationFilter
    |-- /private requires authenticated()
    +-- Permit -> DispatcherServlet -> Controller -> 200
    +-- Deny -> denial handling mechanism
~~~

This is a **responsibility diagram**, not an exhaustive or absolute ordering of every security filter. Real flows also include filters for `SecurityContext`, CSRF, exception translation, anonymous authentication, and other configured mechanisms.

### Who Writes the SecurityContext?

**`BasicAuthenticationFilter`** receives the authenticated `Authentication` and sets it on the request's `SecurityContext`. **`ProviderManager` does not automatically place the result into `SecurityContextHolder` just because `authenticate` returned successfully**.

A standalone Java statement:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

only returns the authentication result or throws an exception. It **does not create an HTTP session**, does not save the result for future requests, does not send a redirect, and does not issue an access token.

### When a Request Has No Credentials

If an endpoint requires `authenticated` and no valid identity is present, the authorization layer can reject it; with Basic, `AuthenticationEntryPoint` typically responds with HTTP 401/challenge. With form login, the user may receive a 302 redirect to the login page. These HTTP status codes are the responsibility of **filters and handlers**, not the return value of `AuthenticationManager`.

## 5. What Contract Is AuthenticationManager?

The `AuthenticationManager` interface has one core method:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

It receives an `Authentication` that needs verification. On success, it returns a trusted `Authentication` with the appropriate identity and authorities; on failure, it throws `AuthenticationException`.

What the interface **does not do itself**: read HTTP requests, pick a login page, create cookies, populate `SecurityContext`, save sessions, authorize URLs, or check a record's `ownerId`. Those tasks belong to other components.

Separating the manager from filters allows multiple credential collectors (forms, Basic, or tokens) to share verification logic. Separating the manager from providers also lets you swap authentication mechanisms without rewriting HTTP filters.

## 6. How Does ProviderManager Handle Multiple AuthenticationProviders?

`ProviderManager` maintains an ordered list of `AuthenticationProvider`s and follows this contract:

1. Check **`supports(authentication.getClass())`** to see which provider can handle the token type.
2. Skip providers that do not support it.
3. Call **`authenticate(authentication)`** on a supporting provider.
4. A **non-null `Authentication`** result means the provider succeeded; `ProviderManager` uses that result.
5. If the provider returns **`null`**, it abstained from this request and the next supporting provider may be tried.
6. If the provider throws **`AuthenticationException`**, the manager handles it according to the exception type; some exceptions are remembered while remaining providers are tried, whereas others stop immediately.
7. If a parent `AuthenticationManager` is configured, the parent may be consulted when current providers cannot resolve the request.
8. If no provider supports the token, `ProviderNotFoundException` may occur.

### `supports()` Does Not Check the Password

`supports` only answers whether a provider **can handle a given `Authentication` class**. A provider supporting `UsernamePasswordAuthenticationToken` can still reject a wrong password. Returning `supports=true` **never** makes the request authenticated.

### Returning Null and Throwing Exceptions Are Two Different Behaviors

**Returning `null`**: the provider offers no authentication result for this token, allowing another mechanism to try per the contract.

**Throwing `AuthenticationException`**: the provider determined authentication failed. For wrong passwords, `BadCredentialsException` is typical. Certain types such as **`AccountStatusException`** cause `ProviderManager` to stop trying remaining providers as designed.

Never construct a fallback chain where a strict provider rejects a wrong password only for another provider to accept it via a weaker mechanism.

### Parent Manager and Provider Order

Two providers may both return `supports=true` for the same class. In that case, **order** and how they return results matter greatly. Multiple `SecurityFilterChain`s can also have separate managers or share a parent manager when configured. Always identify the exact manager used by the filter handling the request.

### Credential Erasure and Events

`ProviderManager` tries by default to erase credentials from a successful `Authentication` if the object implements **`CredentialsContainer`**. Do not retain passwords in `SecurityContext` for later reuse. If a `UserDetails` cache shares the same reference whose credentials get erased, fix the cache design rather than hastily disabling credential erasure.

`ProviderManager` can pair with an `AuthenticationEventPublisher` for authentication events. A manually constructed manager must verify event publisher configuration if auditing is required; do not assume every event appears automatically or logs raw credentials.

## 7. DaoAuthenticationProvider, UserDetailsService, and PasswordEncoder

**`DaoAuthenticationProvider`** is a common `AuthenticationProvider` for username/password. It loads user data from `UserDetailsService` and delegates password verification to `PasswordEncoder`.

~~~text
UsernamePasswordAuthenticationToken("alice", rawPassword)
                  |
                  v
DaoAuthenticationProvider
      |               |
      |               +--> UserDetailsService.loadUserByUsername("alice")
      |                            |
      |                            +--> UserDetails:
      |                                 username=alice
      |                                 encodedPassword=<hash>
      |                                 authorities=[ROLE_USER]
      |
      +--> PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +--> Account enabled/non-locked/expiry checks
      |
      v
Authenticated Authentication or AuthenticationException
~~~

**`UserDetailsService` only loads users**, it does not verify passwords itself. Finding a username in the database does not prove the caller actually owns that account.

**`PasswordEncoder`** uses **`encode(raw)`** when creating a stored hash and **`matches(raw, storedHash)`** during login. Never compare raw passwords to `storedHash` with `equals`; never store plaintext passwords.

Algorithms like BCrypt and Argon2 hash passwords with appropriate computational cost. Consider algorithm choice, cost factor, hash upgrades, and account lifecycle policies. When a user is locked, disabled, or expired, the provider may reject login even when the password matches.

### Providers Beyond DaoAuthenticationProvider

| Provider | Typical mechanism |
| --- | --- |
| `DaoAuthenticationProvider` | Username/password and `UserDetailsService` |
| `LdapAuthenticationProvider` | Configured LDAP integration authentication |
| `JwtAuthenticationProvider` | JWT verification in OAuth2 Resource Server via decoder and validators |
| Custom `AuthenticationProvider` | Purpose-built, verified credential mechanism |

Merely registering an `AuthenticationProvider` bean does not guarantee every filter will automatically use it as expected. Verify the manager, filter chain, token type, and scope of application.

## 8. Runnable Example: Wiring ProviderManager and DaoAuthenticationProvider Manually

This example uses **Spring Boot 3.3.x, Spring Security 6.3.x, Java 17+, Spring MVC/Servlet**. Two in-memory accounts are strictly for study. We intentionally declare `AuthenticationManager` explicitly so you can see exactly which provider the manager contains.

### Dependency

In a Spring Boot project with Gradle Groovy DSL, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is the dependencies block of an **already-initialized Boot project**, not a full `build.gradle`. Starter versions are managed by Spring Boot.

### Complete Java File

Create **src/main/java/com/example/authflow/AuthFlowApplication.java**:

~~~java
package com.example.authflow;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthFlowApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        // Spring Security 6.3: constructor accepts PasswordEncoder.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(encoder);
        dao.setUserDetailsService(users);
        return new ProviderManager(dao);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

The public class matches the file name; `DemoController` lives in the same package so Spring Boot component scanning detects it. The controller receives the `Principal` authenticated by the filter.

**How the beans work:**

1. `PasswordEncoder` creates a `BCryptPasswordEncoder`.
2. `UserDetailsService` creates `alice` with `ROLE_USER` and `admin` with `ROLE_ADMIN`; passwords are hashed before storing in memory.
3. `AuthenticationManager` is a `ProviderManager` holding one `DaoAuthenticationProvider` wired with `UserDetailsService` and `PasswordEncoder`.
4. `HttpSecurity.authenticationManager(manager)` binds that manager to the `SecurityFilterChain` being built.
5. HTTP Basic is enabled; form login is disabled so the exercise observes 401 instead of a redirect.
6. `GET /public` allows anonymous access, `GET /private` requires `authenticated`, `GET /admin` requires `ROLE_ADMIN`, and everything else hits `denyAll`.

**Version note:** Spring Security 6.3 provides the `DaoAuthenticationProvider(PasswordEncoder)` constructor and `setUserDetailsService(UserDetailsService)` method. Some newer Spring Security versions have different constructors; always check the Javadoc for your exact dependency version before upgrading. This code is designed for Spring Boot 3.3.x / Security 6.3.x.

### Running from the Project Directory

~~~bash
./gradlew bootRun
~~~

In PowerShell, use **.\gradlew.bat bootRun**. Once the server starts on `localhost:8080`, test:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

In PowerShell you can use **`curl.exe`** if `curl` is an alias. Never use demo passwords or HTTP Basic over unencrypted HTTP on real networks.

| Request | Expected status | Content / cause |
| --- | --- | --- |
| `/public` no credentials | 200 | Body: `public OK` |
| `/private` no credentials | 401 | Missing authentication |
| `/private` with `alice:wrong` | 401 | Provider rejects credentials |
| `/private` with `alice:learn123` | 200 | Body: `hello alice` |
| `/admin` with `alice:learn123` | 403 | Valid credentials, missing `ROLE_ADMIN` |
| `/admin` with `admin:admin123` | 200 | Body: `admin OK` |

The outcomes above are **derived from the configuration**, not logs of a live run captured in the article. If you add custom filters, chains, handlers, or proxies, verify actual runtime behavior with tests.

## 9. Three Key Paths

### 9.1. Valid Login with Sufficient Authority

~~~text
curl -u alice:learn123 GET /private
     |
     v
BasicAuthenticationFilter reads header
     |
     v
Unauthenticated UsernamePasswordAuthenticationToken
     |
     v
ProviderManager -> DaoAuthenticationProvider
     |
     +-- loadUserByUsername("alice")
     +-- PasswordEncoder.matches(...) = true
     |
     v
Authentication(principal=alice, ROLE_USER, authenticated=true)
     |
     v
Filter sets SecurityContext for the request
     |
     v
AuthorizationFilter checks authenticated()
     |
     v
DemoController returns "hello alice" -> HTTP 200
~~~

### 9.2. Wrong Password

~~~text
curl -u alice:wrong GET /private
     |
     v
BasicAuthenticationFilter -> ProviderManager
     |
     v
DaoAuthenticationProvider: password mismatch
     |
     v
AuthenticationException
     |
     v
AuthenticationEntryPoint / error-handling filter -> HTTP 401
~~~

The controller is never invoked. Authentication failure can also result from a locked/expired account, wrong `UserDetailsService`, or wrong `PasswordEncoder`, not only a mistyped password.

### 9.3. Right Password, Insufficient Authority

~~~text
curl -u alice:learn123 GET /admin
     |
     v
ProviderManager and DaoAuthenticationProvider succeed
     |
     v
Authentication has ROLE_USER
     |
     v
AuthorizationFilter requires ROLE_ADMIN
     |
     v
Denied -> HTTP 403
~~~

`AuthenticationManager` did its job properly on this branch. A 403 error is an authorization decision, not evidence that the provider failed to verify the password.

## 10. Can Form Login and HTTP Basic Share a Manager?

Yes. Both typically pass a `UsernamePasswordAuthenticationToken` to `AuthenticationManager`. The primary differences are **which filter extracts credentials** and **post-authentication HTTP behavior**.

| Property | HTTP Basic | Form login |
| --- | --- | --- |
| Credential source | `Authorization: Basic` | Form POST login |
| Filter | `BasicAuthenticationFilter` | `UsernamePasswordAuthenticationFilter` |
| Typical token | `UsernamePasswordAuthenticationToken` | `UsernamePasswordAuthenticationToken` |
| Typical provider | `DaoAuthenticationProvider` | `DaoAuthenticationProvider` |
| When unauthenticated | 401/challenge | May 302 redirect to login page |
| On success | Continue request | Success handler, usually redirect |
| Login state | Client usually sends Basic on every request | Usually persisted via session and `SecurityContextRepository` |

Do not say HTTP Basic is **always stateless** just because `httpBasic()` is enabled. Sessions, request caches, or other filters still depend on policy. If a stateless API is required, configure `SessionCreationPolicy` and related components explicitly.

A form login flow also involves CSRF, session fixation protection, login success/failure handlers, and context persistence. `AuthenticationManager` only verifies credentials; it does not replace those pieces.

## 11. Configuring Multiple Managers, Multiple Providers, and Chains

A system might have an admin area using form login, an API using JWT Bearer, and internal services using another mechanism. You can design `SecurityFilterChain`s with separate managers, or a shared manager where appropriate.

When debugging, always ask:

1. Which `SecurityFilterChain` matched the request?
2. Which filter read the credentials?
3. Which `Authentication` class did the filter build?
4. Which `AuthenticationManager` is that filter referencing?
5. Which `AuthenticationProvider`s does the manager hold, and in what order?
6. Which provider returned `supports=true`?
7. Did it succeed, return `null`, or throw `AuthenticationException`?
8. Did the filter place the result into `SecurityContext`?
9. Which authority does `AuthorizationFilter` require?

Registering an `AuthenticationProvider` bean while forgetting to attach it to the active manager, or misordering filter chains, can prevent your provider from ever being invoked despite correct code.

### Should You Write a Custom AuthenticationProvider?

Only when built-in mechanisms do not fit the required authentication protocol. The interface has two main methods:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
~~~

These are **illustrative signatures**, not a Java file redeclaring Spring Security's existing interface.

If building a custom provider, verify trusted credential sources, never read roles from the client, handle credential expiry/revocation where applicable, protect keys/secrets, clearly define `null` vs. exception semantics, avoid insecure fallbacks, and test failure branches.

Never write a provider that sets `authenticated=true` from a self-asserted username or hardcoded API key. For LDAP, OAuth2, JWT, and standard login, prefer Spring Security's supported mechanisms.

## 12. SecurityContext and Login Sessions

`SecurityContextHolder` is the access point for the active `SecurityContext` in the Servlet stack. Authentication filters may update `Authentication` in the context; how the context is saved/restored across HTTP requests depends on **`SecurityContextRepository`, session policy, and corresponding filters**.

A standalone call:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

**does not create cookies, does not issue JWTs, does not save sessions, and does not populate the context**. A custom login endpoint must implement post-authentication handling, error handling, sessions/tokens, browser CSRF protection, logout, and credential security.

When using Spring Security's built-in flows, let filters manage the lifecycle properly rather than manually setting `SecurityContextHolder` in a Controller and expecting the next request to remember the identity.

## 13. Common Mistakes and What to Check

| Symptom / Misconception | What to inspect |
| --- | --- |
| `UserDetailsService` finds a user so assume logged in | Password not yet verified; need `DaoAuthenticationProvider`/`PasswordEncoder` |
| `supports=true` means the token is valid | `supports` only indicates class handling capability |
| `ProviderManager` always tries every provider | Success and certain exception types halt iteration |
| `AuthenticationManager` bean exists yet is never called | The filter/chain may be using another manager |
| User enters right password yet gets 403 | Check authorities and authorization rules |
| `/private` returns 401 | Check credential header, provider, account status, encoder |
| Password hash mismatch | Check `encode`/`matches` and stored hash algorithm |
| `Authentication` created in Controller yet next request is anonymous | `SecurityContextRepository`/session persistence not handled |
| Confusing roles with resource ownership | Check `ownerId` and business data |
| Credentials erased from cached `UserDetails` | Inspect cache references and credential erasure |
| Using `HttpSecurity` in a WebFlux application | Need `ServerHttpSecurity` and reactive security context |
| Logging raw credentials in debug logs | Remove password/token logging and protect logs |

When enabling debug logging in development, avoid printing raw `Authorization` headers, passwords, tokens, cookies, or secret-bearing objects. Better to log **provider name, Authentication type, and outcome** at an appropriate level without logging credentials.

## 14. Self-Check Exercises

**Q1.** How do the HTTP Basic filter and `DaoAuthenticationProvider` differ?  
**A:** The filter reads the header, creates a token, invokes the manager, and manages HTTP/context; the provider verifies username/password using a user source and encoder.

**Q2.** Does `ProviderManager` returning null mean authentication succeeded?  
**A:** No. A provider may return null so another provider can try; only a non-null successful `Authentication` is a verified result.

**Q3.** If a provider throws `AccountStatusException`, is it always skipped to try the rest of the list?  
**A:** No. That is an exception group that can halt the process.

**Q4.** Alice has `ROLE_USER` and logs in cleanly to `/admin`, which requires `ADMIN`. Why 403?  
**A:** Authentication succeeded; authorization denied access for lacking `ROLE_ADMIN`.

**Q5.** Does calling `manager.authenticate()` directly in a Controller automatically log the browser in on the next request?  
**A:** No. You must persist and restore `SecurityContext` or use an appropriate session/token mechanism along with other security steps.

**Q6.** Why not call `loadUserByUsername()` directly and return success?  
**A:** That only finds the user without verifying the client's credentials.

**Q7.** Why might `DaoAuthenticationProvider` code need edits when changing Spring Security versions?  
**A:** Constructors and APIs can change. This lesson uses 6.3 APIs, and you should check the Javadoc for your actual dependency version.

**Q8.** An API authenticates Alice properly yet returns Bob's order. Where is the manager wrong?  
**A:** There is not enough evidence to blame the manager; most likely record-level authorization is missing in the Service layer.

## 15. Official Documentation

- Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Username/Password Authentication: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/index.html
- DaoAuthenticationProvider API 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- ProviderManager API 6.3.x: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authentication/ProviderManager.html
- AuthenticationProvider API 6.3.9: https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authentication/AuthenticationProvider.html
- BasicAuthenticationFilter API 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/web/authentication/www/BasicAuthenticationFilter.html
- Authorization Architecture: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/architecture.html
