# UsernamePasswordAuthenticationToken Before and After Authentication

**Module:** Spring Security – authentication. **Topic group:** Identity Models.

## 1. The Core Problem to Understand

In Spring Security, the same Java type **`UsernamePasswordAuthenticationToken`** can carry **two very different meanings**:

- **Before authentication:** an *authentication request* holding the user identifier and credentials just supplied by the client. The system **does not yet trust** that identity.
- **After successful authentication:** an *authentication result* created by a trusted component, holding the verified principal and granted authorities. The system can place this result into `SecurityContext` for authorization.

The class name contains the word *Token*, yet this is **not a JWT/Bearer access token**, nor is it **a session ID**. It is an implementation of the **`Authentication`** interface, especially common in username/password flows. Understanding this object's lifecycle prevents a critical security flaw: **marking unverified client input as a logged-in user**.

~~~text
CLIENT SENDS USERNAME + PASSWORD
            |
            v
UsernamePasswordAuthenticationToken
      isAuthenticated() = false
      principal = username
      credentials = raw password
            |
            v
AuthenticationManager
            |
            v
AuthenticationProvider (e.g., DaoAuthenticationProvider)
      -> load UserDetails
      -> PasswordEncoder.matches(...)
      -> check account status
            |
            |-- failure --> AuthenticationException
            |
            v
UsernamePasswordAuthenticationToken (result)
      isAuthenticated() = true
      principal = UserDetails or verified identity
      authorities = authorities assigned by trusted system
      credentials = usually erased after authentication
            |
            v
SecurityContext -> request authorization
~~~

**Crucial point:** Normally these are **two separate objects** passed through `AuthenticationManager`. You should not picture Spring simply calling `setAuthenticated(true)` on the incoming password-bearing token and finishing.

## 2. Structure of a UsernamePasswordAuthenticationToken

`UsernamePasswordAuthenticationToken` lives in `org.springframework.security.authentication` and extends `AbstractAuthenticationToken`. It implements `Authentication`, with these members:

| Member | Meaning | Before authentication | After successful authentication |
| --- | --- | --- | --- |
| `getPrincipal()` | Claimed or verified identity | Usually the username string supplied by the client | Usually a `UserDetails` object from `UserDetailsService`; may be another type |
| `getCredentials()` | Proof used to verify identity | Usually the raw password just submitted | Usually `null` when `ProviderManager` erases credentials by default |
| `getAuthorities()` | `GrantedAuthority` items for authorization | Usually empty; clients cannot grant themselves rights | Trusted roles/permissions loaded and mapped by the provider |
| `isAuthenticated()` | Trust state of the authentication object | `false` | `true` upon successful authentication |
| `getDetails()` | Request-mechanism metadata | May be request details, remote address, session ID, etc. | May be carried over or re-processed |
| `getName()` | Identifier name extracted from the principal | Usually the `String` username | Usually still the username even though the principal changed type |

**Principal is not always a `String`.** Nor should you assume `getCredentials() == null` means not logged in. In an authenticated result, Spring typically proactively erases the password from the token.

**Authorities are not credentials:** `ROLE_READER`, `ROLE_ADMIN`, or permissions are used for authorization after AuthN; a valid password **does not automatically grant** arbitrary authorities. Authorities must come from a system-trusted source.

**Details are not substitute authentication proof:** Fields like IP address or session ID are metadata only; you must account for proxies and server settings, and never rely on them alone to decide identity or access rights.

## 3. Constructors and Factories: How You Create the Token Decides Its State

With Spring Security 5.7 and newer, prefer the two static factory methods to express intent clearly. The legacy constructors remain useful when reading existing code:

| Creation method | `isAuthenticated()` | Who should use it? |
| --- | --- | --- |
| `new UsernamePasswordAuthenticationToken(principal, credentials)` | `false` | Filter/controller creating an authentication **request** |
| `UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)` | `false` | Filter/controller creating an authentication **request**; clearer name |
| `new UsernamePasswordAuthenticationToken(principal, credentials, authorities)` | `true` | **Only** a trusted component that has verified identity, e.g., a provider |
| `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` | `true` | **Only** a trusted component creating an authenticated **result** |

Short API illustration:

~~~java
// Unauthenticated: data the user just submitted.
UsernamePasswordAuthenticationToken request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", "raw-password-from-login"
        );

// Verified result: ONLY create inside trusted provider code.
// principal is verified; authorities come from the system, not the client.
UsernamePasswordAuthenticationToken success =
        UsernamePasswordAuthenticationToken.authenticated(
                verifiedPrincipal, null, verifiedAuthorities
        );
~~~

The snippet above is an **API usage illustration**, not a standalone program: `verifiedPrincipal` and `verifiedAuthorities` must come from a trusted verification process. **Never** pass username/roles from an HTTP request into `authenticated(...)` for a "quick login".

**Why not call `request.setAuthenticated(true)`?** In the `UsernamePasswordAuthenticationToken` implementation, that call is rejected with `IllegalArgumentException`. The method accepts `false` to mark a token no longer trusted, yet that is **not a logout flow**, and does not replace clearing `SecurityContext`/invalidating the session properly.

**The three-argument constructor trap:** The constructor taking an authorities collection immediately creates a token with `isAuthenticated() = true`. Passing an empty list **does not turn it** into an unauthenticated token. Therefore, never use the three-argument constructor to build a request from client data.

## 4. Who Performs the Before → After Transition?

In a **Spring Security Servlet** form-login flow, responsibilities are separated:

1. **Authentication filter** (such as `UsernamePasswordAuthenticationFilter`) reads the login credentials and creates an unauthenticated `UsernamePasswordAuthenticationToken`.
2. **AuthenticationManager** receives the request token. The common implementation is `ProviderManager`, orchestrating one or more `AuthenticationProvider`s.
3. **DaoAuthenticationProvider** supports username/password, uses `UserDetailsService` to look up the registered user; `PasswordEncoder` matches the raw password against the stored password hash and checks account status.
4. **If valid**, the provider constructs an authenticated `Authentication`, typically still a `UsernamePasswordAuthenticationToken` but with a richer principal and trusted authorities.
5. **ProviderManager** by default erases sensitive credentials on the result if the object implements `CredentialsContainer`.
6. **On filter success**, the authentication result is placed into `SecurityContextHolder`; `SecurityContextRepository`/session handles persistence for subsequent requests if configured.
7. **Authorization** uses the authenticated `Authentication` along with authorities/policies to decide whether an endpoint is accessible.

~~~text
HTTP POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    | request = unauthenticated(username, rawPassword)
    v
AuthenticationManager / ProviderManager
    |
    +--> DaoAuthenticationProvider
              | UserDetailsService.loadUserByUsername(username)
              | PasswordEncoder.matches(rawPassword, storedHash)
              | check disabled/locked/expired ...
              v
          create trusted Authentication + authorities
    |
    +--> ProviderManager.eraseCredentialsAfterAuthentication (default true)
    v
Authentication result
    |
    +--> SecurityContextHolder for current request
    +--> SecurityContextRepository if persisted to subsequent requests
    v
AuthorizationManager / SecurityFilterChain
~~~

**The authentication result is not the user record:** `UserDetailsService` is responsible for loading data, `AuthenticationProvider` verifies credentials, and `Authentication` represents the identity inside the security processing context.

**Failure throws an exception, not a new "false" token:** Invalid credentials cause `AuthenticationManager.authenticate(...)` to throw `BadCredentialsException`; locked/expired accounts produce the corresponding `AuthenticationException`. The system must never put an unauthenticated request token into the context as if logged in.

A request token having `isAuthenticated() = false` before calling the manager is **by design**; it is not a bug to fix with a setter.

## 5. Runnable Demo: Same Input, Two Distinct States

The example below runs standalone as a Java 17+ application with Spring Security Core **6.5.11** and Spring Security Crypto. It uses `InMemoryUserDetailsManager` to avoid a database and focus on the `UsernamePasswordAuthenticationToken` lifecycle. Demo passwords are for learning only.

Create the directory structure:

~~~text
token-lifecycle/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── TokenLifecycleDemo.java
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.TokenLifecycleDemo'
}
~~~

File **src/main/java/demo/TokenLifecycleDemo.java**:

~~~java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class TokenLifecycleDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails account = User.withUsername("lan")
                .password(encoder.encode("learn-only-password"))
                .roles("READER")
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // 1) Request: holds only client-supplied info.
        UsernamePasswordAuthenticationToken request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "learn-only-password"
                );

        System.out.println("before.authenticated=" + request.isAuthenticated());
        System.out.println("before.principal=" + request.getPrincipal());
        System.out.println("before.authoritiesCount=" + request.getAuthorities().size());
        System.out.println("before.credentialsPresent=" + (request.getCredentials() != null));

        // 2) Wrong credentials: manager throws exception, creates no trusted result.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"
                    )
            );
            System.out.println("badPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("badPassword=BadCredentialsException");
        }

        // 3) Valid credentials: result created by trusted provider/manager.
        Authentication result = manager.authenticate(request);

        boolean hasReaderRole = result.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));

        System.out.println("after.authenticated=" + result.isAuthenticated());
        System.out.println("after.type=" + result.getClass().getSimpleName());
        System.out.println("after.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("after.name=" + result.getName());
        System.out.println("after.hasReaderRole=" + hasReaderRole);
        System.out.println("after.credentialsErased=" + (result.getCredentials() == null));

        // 4) Manager erases credentials from the RESULT, not guaranteeing
        // automatic erasure of the request object still held by the caller.
        System.out.println("request.credentialsStillPresent="
                + (request.getCredentials() != null));
    }
}
~~~

Run from the directory containing `build.gradle` with JDK 17+ and Gradle installed:

~~~bash
gradle -q run
~~~

Or use the Gradle Wrapper if the project includes one:

~~~bash
./gradlew -q run
~~~

On Windows use `gradlew.bat -q run`. **stdout emitted by `TokenLifecycleDemo`** (excluding Gradle or library logs if enabled):

~~~text
before.authenticated=false
before.principal=lan
before.authoritiesCount=0
before.credentialsPresent=true
badPassword=BadCredentialsException
after.authenticated=true
after.type=UsernamePasswordAuthenticationToken
after.principalIsUserDetails=true
after.name=lan
after.hasReaderRole=true
after.credentialsErased=true
request.credentialsStillPresent=true
~~~

### Why Does This Output Matter?

- `before.authenticated=false`: the request constructor/factory **does not** authenticate the user merely from knowing a username and password string.
- `before.authoritiesCount=0`: the system has not assigned authorities yet because it does not know whether the credentials are valid.
- `badPassword=BadCredentialsException`: wrong credentials result in failure, with no authenticated object returned.
- `after.authenticated=true`: only after the provider matches the password against the stored hash does the manager return a trusted result.
- `after.principalIsUserDetails=true`: the post-authentication principal is typically the object from `UserDetailsService`, unlike the initial username string.
- `after.hasReaderRole=true`: the `ROLE_READER` authority came from the stored account, not from the HTTP request.
- `after.credentialsErased=true`: `ProviderManager` by default erases credentials from the result. This **does not revoke the authenticated status**.
- `request.credentialsStillPresent=true`: the request object can still hold the raw password. Do not retain it longer than needed and never log it.

**Version note:** The `unauthenticated(...)` and `authenticated(...)` factory APIs were introduced in Spring Security 5.7. The demo pins dependency 6.5.11 to explain output consistently. In an existing Spring Boot app, let the project's BOM/dependency management control Spring versions rather than mixing versions arbitrarily.

## 6. Where Does the Transition Happen in Real Web Code?

In a Spring Security application configured with **`formLogin(...)`**, most of the flow above is already executed by Spring's filters and providers. Application controller authors normally **do not need** to create trusted tokens themselves. A conceptual flow sketch for reading code is:

~~~java
// SKETCH CODE: variables already wired in the Servlet application.
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
        submittedUsername, submittedPassword
);

Authentication result = authenticationManager.authenticate(request);

// After authentication, never pull authorities from client request/body.
// Standard Spring Security web filters handle context management,
// session strategy, saveContext, and success/failure handlers.
~~~

This is illustrative code, **not a standalone Java class**; `submittedUsername`, `submittedPassword`, and `authenticationManager` come from the configured web environment.

### AuthenticationManager Does Not Mean Login Persists Across All Requests

`authenticate(...)` returns **an authentication result**, yet calling it in a custom controller does not automatically ensure the browser retains a login session. With Servlet, you must set the result into `SecurityContext` for the request lifecycle and, if using sessions, **save** it via `SecurityContextRepository` matching your Spring Security version.

~~~text
authenticationManager.authenticate(request)
    -> authenticated result
    -> SecurityContext.setAuthentication(result)
    -> SecurityContextHolder.setContext(context)
    -> SecurityContextRepository.saveContext(...) when persistence is needed
    -> response and session/cookie handled by web infrastructure
~~~

In real environments, login flows also involve session fixation protection, session strategy, CSRF, success/failure handlers, and logout mechanics. Use `formLogin`/built-in filters if they fit requirements; do not skip those links when writing custom endpoints.

**On subsequent requests:** Spring can restore `Authentication` from `SecurityContextRepository`, such as from the HTTP session. That does not mean username/password must be resent or `DaoAuthenticationProvider` must run again on every protected URL visit.

## 7. Common Misunderstandings About Authenticated, Principal, and Authorities

### `isAuthenticated()` Is a Trust State, Not Independent Proof

An object created with `authenticated(...)` has the flag `true` from the moment of creation. **The flag does not prove the password was checked**: safety depends on only trusted server components creating such tokens after verifying credentials.

A client sending JSON `{"username":"lan","authenticated":true}` has zero security value; never bind that directly into a trusted `Authentication`.

### `isAuthenticated() == true` Does Not Mean All Permissions

Authorization must still evaluate `GrantedAuthority`, roles, and resource-level policies. An authenticated token can exist without the required authority. Furthermore, other `Authentication` implementations (like anonymous) represent state differently; for web policies, use Spring's authorization APIs rather than treating the `isAuthenticated()` boolean as the complete definition of "a real logged-in user".

### `getPrincipal()` Changing Type Is Normal Behavior

Before login, the principal is usually a username string. After login, the principal is usually a `UserDetails` or custom domain principal verified by the provider. Hence `(String) authentication.getPrincipal()` can throw `ClassCastException` after authentication. If you need the username, `authentication.getName()` is more consistent; if you need other fields, check the type explicitly.

### Erased Credentials After Auth Still Leave a Valid Identity

`ProviderManager` by default calls `eraseCredentials()` on results implementing `CredentialsContainer` to shorten secret exposure. Erasure can also affect `principal`/`details` if they implement `CredentialsContainer`. With custom `UserDetails` or shared caches, avoid letting erasure accidentally wipe data needed for the next authentication.

Never disable `eraseCredentialsAfterAuthentication` purely for debugging convenience; design principal/cache boundaries and pipelines properly.

### Not Every Mechanism Produces UsernamePasswordAuthenticationToken

Form/password login may return this token type, whereas JWT Bearer, OAuth2/OIDC, passkeys, remember-me, or X.509 can use different `Authentication` implementations. What matters in **identity models** is the `Authentication` contract, `SecurityContext`, and trust boundaries—not forcing every request into one class.

## 8. Common Mistakes and How to Fix Them

| Mistake | Why is it dangerous or wrong? | Correct practice |
| --- | --- | --- |
| Creating the three-arg token directly from client username and role | Immediately sets `isAuthenticated() = true` without checking password | Use `unauthenticated(...)` then `AuthenticationManager.authenticate(...)` |
| Calling `setAuthenticated(true)` to "mark as logged in" | `UsernamePasswordAuthenticationToken` rejects with an exception; flawed trust model | Let the provider produce a trusted result after verification |
| Passing DB password hash into `credentials` of the request | Providers normally expect raw password for `PasswordEncoder.matches`; wrong semantics | Receive raw password from form over HTTPS; provider matches against server-stored hash |
| Expecting an authenticated token to always keep raw password | Retains secrets longer than necessary; log/heap/session leak risk | Accept default credential erasure |
| Putting an unauthenticated request token into user `SecurityContext` | Downstream code may mishandle trust state | Store only valid authenticated results |
| Calling manager and ignoring the return value | Original request token remains unauthenticated or lacks authorities | Use the returned `Authentication result` |
| Calling `authenticate(...)` in a controller and assuming automatic session | Missing context persistence, session strategy, or success handlers | Use standard login mechanisms or implement full web lifecycle |
| Reading `authorities` from the client body | Client can grant itself `ROLE_ADMIN` | Load authorities from `UserDetailsService`/provider or trusted source |
| Casting every `principal` to `String` | After login it is usually `UserDetails` | Use `getName()` or `instanceof` checks |
| Catching all errors as "wrong password" | Hides provider, configuration, or account-state failures | Handle `AuthenticationException` by type while keeping client messages safe |
| Using `setAuthenticated(false)` instead of logout | Fails to revoke session, cookies, or tokens | Follow logout flow, clear context, and invalidate session if present |
| Logging the whole token/request/password | Leaks credentials and personal data | Log minimal events, never log credentials |

## 9. Three Scenarios to Test Understanding

**Scenario A.** Client POSTs `{"username":"lan","password":"wrong-password","roles":["ADMIN"]}`. Server builds `UsernamePasswordAuthenticationToken.unauthenticated("lan", "wrong-password")` and calls the manager. What happens?

**Explanation:** The provider matches the password against the stored hash and fails; it must not return a trusted `Authentication` just because the client included a role. Roles in the body are not a trusted authority source. The request token must not be saved into `SecurityContext` as a logged-in user.

**Scenario B.** `manager.authenticate(request)` returns a token with `isAuthenticated() = true`, `getPrincipal()` as a `UserDetails`, and `getCredentials() == null`. Does missing password mean login failed?

**Explanation:** No. The password was verified and credentials were erased under security policy. Use the result's authorities for authorization and manage the context via the web mechanism.

**Scenario C.** A developer writes `new UsernamePasswordAuthenticationToken(username, password, List.of())` thinking "an empty authorities list means surely it is unauthenticated." Is that conclusion correct?

**Explanation:** Wrong. The **three**-argument constructor produces a trusted token with `isAuthenticated() = true` regardless of whether the list is empty. You must use the **two**-argument constructor or the `unauthenticated(...)` factory when sending a request to the manager.

## 10. Checklist When Reading or Writing Login Code

1. **Client input** contains only the needed username/credential; the request token must be **unauthenticated**.
2. **AuthenticationManager/Provider** actually verifies credentials and account state against a trusted data source.
3. **Returned result** carries the verified principal, system-derived authorities, and `isAuthenticated() = true` on success.
4. **Credential cleanup** keeps secrets short-lived; avoid logging and understand how `CredentialsContainer` interacts with caches.
5. **SecurityContext/session** is set and persisted properly only after authentication, with full session/CSRF handling as required.
6. **Authorization** continues enforcing permission policies on each request; authentication does not automatically grant permissions.
7. **Authentication errors** must never turn a request token into a trusted result or leak account details.

## 11. Official References

- [UsernamePasswordAuthenticationToken – Spring Security 6.5 Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): two/three-arg constructors, static factories, `isAuthenticated()`, and credential erasure.
- [Authentication Architecture – Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `AuthenticationManager`, `ProviderManager`.
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService` and `PasswordEncoder` in the username/password flow.
- [ProviderManager – Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): providers, exceptions, and `eraseCredentialsAfterAuthentication`.
- [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): persisting `SecurityContext` and session lifecycle.

**Remember:** An **unauthenticated token** describes *proof needing verification*. An **authenticated token** describes *a trusted identity after verification*. The transition between the two states must cross the trust boundary of `AuthenticationManager`/`AuthenticationProvider`, and only then reach `SecurityContext` and authorization.
