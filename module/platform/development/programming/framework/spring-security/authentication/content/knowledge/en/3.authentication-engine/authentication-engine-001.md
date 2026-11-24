# AuthenticationManager and the authenticate Contract in Spring Security

**`AuthenticationManager`** is the central interface defining how an authentication request is processed in Spring Security. Its core method is **`authenticate(Authentication authentication)`**: it receives an `Authentication` object carrying the information to verify, and either **returns a fully authenticated `Authentication`** on success or **throws an `AuthenticationException`** on failure.

The most important part of this lesson is not memorizing method names, but understanding **the contract between the authentication requester, the authentication engine, providers, the result, and the security context**. Calling `authenticate` successfully does not by itself mean that a subsequent HTTP request is logged in, has a session created, or is authorized to access resources.

## 1. Position of AuthenticationManager in the Authentication Engine

In a Servlet application using Spring Security, components typically collaborate as follows:

~~~text
Client sends request + authentication credentials
        |
        v
SecurityFilterChain
        |
        v
Authentication Filter (Basic / form login / bearer / custom...)
        |
        | creates request Authentication, usually not yet authenticated
        v
AuthenticationManager.authenticate(request)
        |
        v
ProviderManager (common implementation)
        |
        +--> AuthenticationProvider A: supports? -> process / reject
        |
        +--> AuthenticationProvider B: supports? -> process / reject
        |
        +--> ... / parent manager if configured
        |
        v
Authenticated result Authentication
        |
        | authentication filter/handler manages SecurityContext
        v
SecurityContextHolder / SecurityContextRepository if needed
        |
        v
AuthorizationManager / method security / business logic
~~~

The diagram illustrates the **conceptual flow**; the filter, context setup mechanism, and session persistence configuration depend on the login method.

Three interfaces/objects to distinguish:

| Component | Role | What is it responsible for? |
|---|---|---|
| `AuthenticationManager` | API orchestrating a single authentication operation | Receives an `Authentication` request; returns an authenticated result or throws an error |
| `AuthenticationProvider` | Handler verifying a specific type of `Authentication` | Selects supported token types, verifies proof, returns a success result, returns `null` if unable to decide, or throws an error |
| `Authentication` | Request data **and** result data | Carries principal, credentials, authorities, details, and the `authenticated` flag; the object before and after the call may differ |

**Do not confuse `AuthenticationManager` with `AuthorizationManager`.** The former handles *identity verification* (AuthN), while the latter supports *access permission decisions* (AuthZ). Returning `ROLE_USER` or `orders:read` from AuthN does not mean every request from that user will be permitted.

### 1.1. The Actual Interface

Abbreviated from the contract of `org.springframework.security.authentication.AuthenticationManager`:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

This is an **API signature excerpt for learning**, not a standalone Java class to create when using the Spring Security library. Key points:

- **Parameter:** `Authentication` representing the authentication request. For example, username/password typically uses `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`.
- **Return value:** an authenticated `Authentication`, containing the principal and trusted `GrantedAuthority` instances according to the provider.
- **Errors:** the method throws `AuthenticationException` or a subclass if the request cannot be authenticated.
- **Trust level:** unauthenticated input data is still just a **claim** from the requester, including the `principal` or authorities self-declared by the client.
- **No implicit authorization step:** returning an authenticated result merely gives the next layer a basis to check permissions.

Spring Security uses an `Authentication` implementation for both input and output, but they have **different states and semantics**. Never read a user identity from an unverified request token and treat it as a trusted principal.

## 2. Before and After Calling authenticate

### 2.1. Unauthenticated Request Object

Java example with username/password:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "secret-demo");
~~~

At this point, `request.getPrincipal()` is typically the string `"linh"`; `request.getCredentials()` is the submitted password; and `request.isAuthenticated()` is `false`. No proof has yet verified that the sender is truly “linh”.

The `credentials` value must be protected like a secret. `getDetails()` may contain request metadata (for example, certain web details), but it is not trusted proof of identity on its own. Do not log the raw input `Authentication`: the object may contain credentials.

### 2.2. Result After Successful Authentication

~~~java
Authentication result = manager.authenticate(request);

boolean ok = result.isAuthenticated();
Object principal = result.getPrincipal();
Collection<? extends GrantedAuthority> grants =
        result.getAuthorities();
~~~

This is an **API usage snippet**, assuming an existing `manager` variable and imports. `result` can be **a new object**, rather than `request` having its flag mutated in place. With a username/password provider, the principal may change from `String` to `UserDetails` or an application principal; authorities reflect the permissions established by the provider.

After success, do not rely on manually calling `request.setAuthenticated(true)` to “log in”. A new token with verified identity/authorities must be created by a trusted provider/manager. Many `Authentication` implementations do not allow turning an untrusted token into a trusted one via an arbitrary setter.

### 2.3. Information That Can Change After Authentication

| Field | Before `authenticate` | After successful `authenticate` |
|---|---|---|
| `principal` | Unverified username or credential subject | Trusted UserDetails, JWT, OIDC principal, or custom principal |
| `credentials` | Submitted password/proof | May be erased after verification; do not rely on whether it remains |
| `authorities` | Usually empty or untrusted | Permissions granted by the backend/provider after authentication |
| `isAuthenticated()` | Usually `false` | `true` for a successful authentication token |
| `details` | May contain request information | May be retained/transferred depending on the implementation |
| `getName()` | Name/subject supplied by the request | Name value determined by the result and principal type |

A complete `Authentication` object **does not have to keep the password intact**. `AuthenticationManager` returns the authenticated result; `ProviderManager` by default attempts to erase credentials on the result if the object supports `CredentialsContainer`. The API contract and the secret-erasure policy are two separate aspects.

## 3. The authenticate Contract on Failure: Exceptions, Not Creating a “Fake Success”

The Javadoc of `AuthenticationManager` requires verifying credentials and highlights key cases:

- **`BadCredentialsException`:** invalid credentials. The system must actually verify the credential; it must not allow access merely because a username exists.
- **`DisabledException`:** the account is disabled and the manager is able to check that status.
- **`LockedException`:** the account is locked and the manager is able to check that status.
- **`AuthenticationException`:** parent class for other authentication failures, such as an unsupported token, expired token, or an authentication service failure.

The Javadoc describes the check precedence as **disabled, locked, then credentials** when those states are detected; the goal is to avoid verifying credentials for an already blocked account. Individual providers/frameworks have their own status checks, and the detailed order may vary when multiple flags are set simultaneously; do not design business behavior based on an exception's internal message string.

In web applications, **an exception from `authenticate` is not an HTTP status code**. Filters, `AuthenticationEntryPoint`, failure handlers, or error-translation components decide whether to return 401, redirect to a login page, or send a protocol-appropriate response. Specific exceptions should usually be logged safely on the server, while user-facing responses can use a generic message to avoid leaking whether a username/account exists.

### 3.1. Do Not Return `null` from a Manager to Represent a Wrong Login

An easily confused distinction:

- **`AuthenticationManager.authenticate`:** the contract returns `Authentication` on success and throws `AuthenticationException` on failure.
- **`AuthenticationProvider.authenticate`:** may return **`null`** when the provider cannot decide and wants to let another provider handle it.

Therefore, a custom `AuthenticationManager` must not use `null` to mean “wrong password”; and a custom `AuthenticationProvider` must not abuse `null` to hide the fact that credentials for a token type it is responsible for failed verification. For wrong credentials that the provider is responsible for checking, throw the appropriate exception.

## 4. ProviderManager: The Common Implementation

`ProviderManager` is the standard implementation of `AuthenticationManager`. It holds a list of `AuthenticationProvider` instances and tries each provider in turn for the request. Conceptual logic:

~~~text
for each provider in configured order:
    if !provider.supports(request.getClass()):
        skip
    else:
        provider.authenticate(request)
        -> non-null Authentication: success, stop
        -> null: undecided, try next provider
        -> AuthenticationException: record failure; may continue trying
        -> AccountStatusException: stop early, do not try next

if no result yet:
    try parent AuthenticationManager if configured
if still no result:
    throw appropriate authentication error
on success:
    may erase credentials from result per configuration
    return authenticated Authentication
~~~

This is **pseudocode**, not compilable Java. The actual implementation has specific handling for exceptions, events, and the parent; consult the `ProviderManager` of the version in use when analyzing edge cases.

### 4.1. `supports(Class<?>)` Only Checks the Token Type

A provider supporting `UsernamePasswordAuthenticationToken` must declare:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
~~~

This is an **illustrative snippet inside a class implementing `AuthenticationProvider`**, not a standalone runnable program. `supports` only indicates that the provider *can handle this kind of object*; it does not prove that the username/password is valid. Another provider might support a different token type such as JWT or a one-time verification code.

**Dangerous mistake:** writing a custom provider with `supports(...) == true`, and then always returning an authenticated token without checking the password/signature/token expiration. That turns a client claim into a trusted identity.

### 4.2. Possible Outcomes with Multiple Providers

| First provider | Next provider | Meaning in ProviderManager |
|---|---|---|
| `supports == false` | May support | First provider is skipped |
| `supports == true` and returns `null` | May make a decision | First provider declines to decide |
| Returns a valid `Authentication` | Not called | Takes the success result |
| Throws `BadCredentialsException` | May succeed | ProviderManager may continue; a later success can supersede the prior error |
| Throws `DisabledException` / `LockedException` (AccountStatusException) | Not tried | Account status failure blocks fallback |
| No provider handles it, no parent | None | May receive `ProviderNotFoundException` |
| No child provider authenticates, has parent | Parent is consulted | Parent may authenticate per its own configuration |

**Fallback relationships are a security decision.** If two providers can both authenticate a username/password token type, clarify the policy to prevent “provider A rejects the password, provider B lets it through via a weaker method”. Treating `AccountStatusException` as a blocking case is a specific mechanism and does not replace an anti-bypass policy across providers.

### 4.3. Parent AuthenticationManager

A `ProviderManager` can have a parent `AuthenticationManager`. This model is useful when multiple `SecurityFilterChain`s have distinct authentication policies while sharing a common mechanism:

~~~text
SecurityFilterChain /admin -> Manager A -> Admin Provider
                           \-> Parent Manager -> Shared Provider

SecurityFilterChain /api   -> Manager B -> API Provider
                           \-> Parent Manager -> Shared Provider
~~~

Do not assume a parent is mandatory. If there is no matching provider and no parent, an error like `ProviderNotFoundException` is a signal to inspect the configuration and requested token type. Do not use an “always-success” provider to fix a missing-provider error.

### 4.4. Erasing Credentials and Caching

`ProviderManager` defaults to `eraseCredentialsAfterAuthentication = true`. If the result supports `CredentialsContainer`, it calls `eraseCredentials()` to reduce how long secrets remain in memory. For example, with username/password, the result typically no longer contains the raw password when returned to the caller.

Note: the principal may also be a `UserDetails` containing a password hash. An implementation might erase secret data inside the principal; if a provider/cache reuses the **same instance** across multiple requests, the cache can be affected. Cache design must copy data appropriately or ensure the credentials needed for verification remain available from a trusted source. Disabling credential erasure via `setEraseCredentialsAfterAuthentication(false)` increases risk and should not be the default fix.

### 4.5. Authentication Events

`ProviderManager` can use an `AuthenticationEventPublisher` to publish success/failure events. When instantiating a standalone `ProviderManager`, do not assume Spring application events will automatically be published completely: the implementation's default publisher does not publish events unless configured. In environments with a parent manager, avoid duplicate events if both parent and child publish.

Events are suitable for auditing and observability, **not a substitute** for brute-force protection, rate limiting, session management, or authentication decisions.

## 5. Runnable Example: Calling authenticate with Java 17 and Spring Security 6.3

This example intentionally separates from HTTP so you can directly observe the **method contract**. We manually create a `ProviderManager` containing `DaoAuthenticationProvider`, handling three account scenarios and one unsupported token type.

`DaoAuthenticationProvider` uses `UserDetailsService` to load account details, `PasswordEncoder` to verify passwords, and built-in account status checks. `InMemoryUserDetailsManager` only holds illustrative data in memory, not a production database.

### 5.1. Project Structure

~~~text
auth-manager-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/AuthManagerDemo.java
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'auth-manager-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.7'
    implementation 'org.springframework.security:spring-security-crypto:6.3.7'
}

application {
    mainClass = 'example.AuthManagerDemo'
}
~~~

A pinned version is used in the example so methods like `DaoAuthenticationProvider()` and `setUserDetailsService(...)` match Spring Security 6.3. In newer versions, `DaoAuthenticationProvider`'s constructor may be recommended to take `UserDetailsService` directly; check the Javadoc for your project's version. The sample uses only Spring Security Core/Crypto libraries, requiring no web server or Spring Boot.

### 5.2. Complete Java Code

Create `src/main/java/example/AuthManagerDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class AuthManagerDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .build();

        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .disabled(true)
                .build();

        UserDetails an = User.withUsername("an")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .accountLocked(true)
                .build();

        UserDetailsService users =
                new InMemoryUserDetailsManager(linh, khoa, an);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(List.of(dao));

        attempt(manager, "linh", "learn-123");
        attempt(manager, "linh", "wrong");
        attempt(manager, "khoa", "learn-123");
        attempt(manager, "an", "learn-123");

        try {
            manager.authenticate(
                    new TestingAuthenticationToken("linh", "learn-123"));
        } catch (AuthenticationException ex) {
            System.out.println("unsupported -> "
                    + ex.getClass().getSimpleName());
        }
    }

    private static void attempt(AuthenticationManager manager,
                                String username, String password) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            Authentication result = manager.authenticate(request);
            String authority = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .findFirst()
                    .orElse("(none)");

            System.out.println(username + " -> OK: "
                    + result.getName()
                    + ", authenticated=" + result.isAuthenticated()
                    + ", authority=" + authority
                    + ", credentials=" + result.getCredentials());
        } catch (AuthenticationException ex) {
            System.out.println(username + " -> FAIL: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

All imports and the main class reside in a single file. `BadCredentialsException` in the imports is not needed directly because the program catches the superclass `AuthenticationException`; that import can be removed while keeping the exact same behavior.

### 5.3. Running and Explaining the Output

In the `auth-manager-demo` directory, use the Gradle Wrapper if one has been created, or a compatible installed Gradle:

~~~bash
./gradlew run
~~~

On Windows PowerShell you can use `.\gradlew.bat run` if the project has a Gradle Wrapper. If there is no wrapper yet but Gradle is installed, use `gradle run`. The Java program's own output is:

~~~text
linh -> OK: linh, authenticated=true, authority=notes:read, credentials=null
linh -> FAIL: BadCredentialsException
khoa -> FAIL: DisabledException
an -> FAIL: LockedException
unsupported -> ProviderNotFoundException
~~~

**Line-by-line explanation:**

1. `linh` with the right password: the provider loads `UserDetails`, verifies bcrypt, and returns an authenticated authentication with authority `notes:read`; the manager performs credential erasure so `getCredentials()` is `null`.
2. `linh` with the wrong password: does not return a success result; throws `BadCredentialsException`.
3. `khoa` has an account record but `disabled=true`: throws `DisabledException`, showing that an existing account does not equate to being able to log in.
4. `an` has a record but `accountLocked=true`: throws `LockedException`.
5. `TestingAuthenticationToken` is not of the `UsernamePasswordAuthenticationToken` type supported by `DaoAuthenticationProvider`: no provider handles it, throwing `ProviderNotFoundException`.

In the example, `BCryptPasswordEncoder` is used to store hashes instead of plaintext passwords. `learn-123` is only a demonstrative password and must not be used in real environments. The password encoder generates a random salt, so hash values may differ across runs, while the authentication results and stdout lines above remain unchanged.

**Why is testing `TestingAuthenticationToken` useful?** It demonstrates that `ProviderManager` does not “blindly try” passwords against a provider that does not support the token type, and that a configuration/token-type error is distinct from wrong credentials.

### 5.4. From the Example to a Spring Boot App with HTTP

In a Servlet application, you do not need to call `manager.authenticate(...)` manually in every controller. Filters such as HTTP Basic or form login build the input token, call the manager per configuration, handle success/failure, and coordinate updating `SecurityContext`.

An **illustrative configuration inside a `@Configuration` class**, assuming appropriate imports and `UserDetailsService`, `PasswordEncoder` beans already exist:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http, AuthenticationManager authenticationManager)
        throws Exception {
    return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

The snippet above is **not a standalone program**; it is a configuration fragment integrated into a Spring Boot 3.x application using `spring-boot-starter-security` and Spring MVC. Depending on the configuration, Spring Security can construct the authentication manager via `AuthenticationConfiguration` and security configurers; you do not always need to define an `AuthenticationManager` bean manually. When there are multiple `SecurityFilterChain`s, the manager used per chain and the global manager may differ; you must verify the actual configuration rather than guessing from bean names.

## 6. Calling authenticate Manually: What Work Remains Unfinished?

A common anti-pattern is creating a `POST /login` endpoint and writing:

~~~java
Authentication result = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
return "login success";
~~~

This is an **illustrative snippet, not a complete controller**. It proves the credentials are valid, but **does not guarantee** that a subsequent HTTP request carries an identity.

Why? `AuthenticationManager` does not by default store `Authentication` in `SecurityContextHolder`, does not create an HTTP session, does not issue cookies, does not issue JWTs, does not handle CSRF/session fixation on its own, and does not execute the full login/logout strategy.

If you write a custom login flow instead of using standard filters and handlers, you must deliberately design the appropriate steps:

1. Receive input over a secure channel, apply login attempt limits and validation; do not log raw passwords.
2. Build an unauthenticated `Authentication`; call the manager; handle `AuthenticationException` properly.
3. If login succeeds and the application uses sessions: create a new `SecurityContext`, attach the result, apply an appropriate session authentication strategy/session fixation protection and `SecurityContextRepository.saveContext(...)` so subsequent requests can restore the context; consider CSRF.
4. If the application issues access/refresh tokens: establish rules for issuance, signing, expiration, rotation, revocation, and secure token storage. The result of `authenticate` is not yet an API token that the client can send on subsequent requests.
5. On failure: do not establish a success context; clear/discard any invalid context, return a safe response, and audit the event appropriately.

To illustrate creating the context at the API level (not including session strategy and persistence):

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);
~~~

This snippet **does not automatically save the session**; in modern Spring Security configurations, if the context must persist across requests, it must be saved via an appropriate `SecurityContextRepository`. In real applications, prefer standard login/filter mechanisms if they meet requirements because many security steps are already built in.

### 6.1. Why Can `authenticate` Succeed While the Request Still Gets 403?

After authentication, the request also goes through authorization rules. The `Authentication` result might contain `notes:read` while the endpoint requires `notes:write`. In that case AuthN succeeds and AuthZ rejects. Missing-permission errors should not be fixed by modifying the authentication provider to return extra authorities without an authorization grant policy.

### 6.2. Why Not Store an “isLoggedIn” Boolean in the Database?

`AuthenticationManager` verifies current proof; it does not manage a permanent “logged-in” state on an account row. Sessions/tokens have their own lifecycle. An account can be locked after login while an old session/JWT still exists if the application lacks a revocation or current-status check mechanism. That is an account lifecycle and session/token strategy problem, not the contract of a single `authenticate` call.

## 7. When Should You Write a Custom AuthenticationProvider or AuthenticationManager?

Normally, **configuring standard providers** is easier to test and less risky than implementing the engine yourself. For example:

- Username/password with a database: `DaoAuthenticationProvider` + `UserDetailsService` + `PasswordEncoder` or a compatible mechanism.
- JWT resource server: filter/manager/provider mechanisms for bearer JWTs per resource-server configuration.
- OAuth2 Login/OIDC: the corresponding authentication providers and filters supplied by Spring Security.
- System-specific custom credentials: consider a custom `AuthenticationProvider` with a clear token type, thorough verification of proof and status, and principal/permissions issued from a trusted source.

A custom `AuthenticationManager` can make sense when you genuinely need an orchestration strategy different from `ProviderManager`, but most extensibility needs lie in providers, token converters, user-details services, authentication success/failure handlers, or account management policies.

### 7.1. Minimum Contract for a Custom AuthenticationProvider

| Method | Correct outcome | Example |
|---|---|---|
| `supports(type)` | `true` if the provider is capable of handling that `Authentication` type | Supports an API key token, does not claim JWTs |
| `authenticate(request)` | Returns an authenticated token **when credentials are valid** | Verified that the API key exists, is unexpired, and not revoked |
| `authenticate(request)` | Throws `AuthenticationException` when authentication fails | API key is revoked or secret is wrong |
| `authenticate(request)` | Returns `null` when unable to decide and allows another provider to try | Provider only handles one variant of the token |
| Authenticated result | Server-side principal/authorities | Does not copy an `admin` role self-declared by the client |

With OTP/MFA, “correct password” may be only one authentication **step**; you must not issue a final authentication with full access permissions before required MFA steps are completed. Use an appropriate authentication flow/state rather than treating every successful provider as completing all factors.

### 7.2. Notes on Login Errors, Caching, and Account Enumeration Prevention

- **Do not reveal whether a username exists via public APIs** through careless error messages or timing differences. `DaoAuthenticationProvider` by default has a mechanism to hide `UsernameNotFoundException` as an invalid-credential error in typical cases.
- **Do not leave weak fallbacks open** after another provider confirms the login credentials are invalid. Provider order affects the outcome.
- **Do not keep credentials in caches longer than necessary**; avoid printing `Authentication` to logs and control secret erasure.
- **Do not use BCrypt or ordinary password hashes to verify JWT signatures**: each token/proof type has its own verification mechanism.
- **Do not turn `AuthenticationException` straight into 200** or return full stack traces; separate operational errors from user-facing responses.
- **Do not allow “login success” solely from `supports=true`**; the provider must verify secrets, account status, and related conditions.

## 8. Test by Contract, Not Just by Login Screen

A good authentication test suite should cover inputs, outputs, exceptions, and context integration:

| Scenario | Outcome to verify |
|---|---|
| Correct username/password, active account | Authentication succeeds, principal and authorities are accurate |
| Valid username, wrong password | `BadCredentialsException` or appropriately normalized error |
| Non-existent username | No detailed information leaked in public responses |
| Disabled / locked account | Rejected and not bypassed via another provider |
| Unsupported token type | `ProviderNotFoundException` or appropriate configuration error |
| Provider A returns `null`, B supports | Provider B gets a chance to authenticate |
| Provider A succeeds | Provider B is not called |
| Provider A throws `BadCredentialsException`, B handles same type | Fallback policy is evaluated and tested against bypass |
| Provider throws `AccountStatusException` | Provider chain stops early per policy |
| Success with password | Credentials are erased or absent from returned result |
| Permissions change while session/token is still valid | Stale permissions do not persist beyond policy limits |
| Calling `authenticate` manually in a login API | Context and session/token are established, saved/revoked per strategy |
| AuthN succeeds, lacks resource permissions | AuthZ still denies |
| Anonymous request / expired session | Not treated as an authenticated user merely due to an object in context |
| Concurrent logins / backend identity store failure | Does not issue invalid authenticated tokens; proper logging and overload protection |

In particular, include tests proving **providers that do not support the token type are not called** and **client-supplied principals/authorities are not reused**. When multiple providers exist, explicitly test ordering and fallback outcomes rather than testing only a single valid user.

## 9. Self-Check Questions

**Question 1.** Does calling `manager.authenticate(request)` successfully automatically populate `SecurityContextHolder`?  
**Answer:** No. The caller/filter must manage the context; saving sessions or issuing tokens requires separate mechanisms.

**Question 2.** Does `AuthenticationProvider.supports(type)` returning `true` mean the token is valid?  
**Answer:** No. That only indicates capability to handle the token type. The provider's `authenticate` verifies the proof.

**Question 3.** A provider can return `null`, so should a manager use `null` to signal a wrong password?  
**Answer:** A provider may return `null` to abstain and let another provider try. The manager contract expresses success via an `Authentication` result and failure via `AuthenticationException`.

**Question 4.** When a `ProviderManager` has two providers both supporting username/password and the first throws `BadCredentialsException`, does the second still have a chance?  
**Answer:** Potentially yes. ProviderManager can continue after certain authentication errors; you must check the specific exception, order, and policy. `AccountStatusException` in particular can stop the chain.

**Question 5.** Why is `result.getCredentials()` typically `null` after `authenticate`?  
**Answer:** `ProviderManager` by default attempts to erase credentials from the result if it supports `CredentialsContainer`, reducing the risk of secrets lingering in memory.

**Question 6.** The username/password is right, yet the API returns 403. Did the manager fail to authenticate properly?  
**Answer:** Not necessarily. The manager may have authenticated successfully while `AuthorizationManager` or method security denied access due to missing permissions.

**Question 7.** Can you solve `ProviderNotFoundException` by always returning a successful authentication for every token?  
**Answer:** No. You must configure a provider that supports the right token type and thoroughly verify proof; returning success unconditionally is an authentication vulnerability.

## 10. Key Takeaways in Practice

1. **`AuthenticationManager.authenticate` is a verification boundary**: the request holds untrusted claims/credentials; a successful result carries verified principal and authorities.
2. **`ProviderManager` orchestrates providers**: `supports` selects the token type, `authenticate` decides; providers return `null`, return a result, or throw an error; ordering and fallback have security impact.
3. **Clear failure contract**: do not fabricate an authenticated token without verifying credentials; handle disabled/locked states and secret errors safely without leaking information.
4. **Context/session/token belong to a separate integration step**: calling the manager successfully does not inherently persist login across subsequent HTTP requests.
5. **AuthN differs from AuthZ**: having an authenticated principal is merely the basis for checking permissions; never grant permissions unconditionally from client input.
6. **Credential erasure and fallback testing** are part of the secure design of an authentication pipeline.

### Official Documentation

- [`AuthenticationManager` JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/AuthenticationManager.html): `authenticate` signature, return value, and exception contract.
- [`ProviderManager` JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/ProviderManager.html): trying providers, parent fallback, `AccountStatusException`, and credential erasure.
- [Servlet Authentication Architecture — Spring Security Reference](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): relationship between manager, provider, authentication filter, and security context.
- [`DaoAuthenticationProvider` — Spring Security Reference](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): username/password authentication using `UserDetailsService` and `PasswordEncoder`.
