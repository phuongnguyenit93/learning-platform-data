# Authentication with Two Roles: Authentication Request and Authenticated Identity

## 1. Why Does One `Authentication` Interface Have Two Meanings?

In Spring Security, `org.springframework.security.core.Authentication` is **a single data contract used at two points in the authentication process**:

1. **Authentication request:** a mechanism receiving input from the client creates an `Authentication` object to say "I want to verify this identity using this proof." At that moment, the object is **not yet trusted** and usually has `isAuthenticated() == false`.
2. **Authenticated principal:** after `AuthenticationManager` and `AuthenticationProvider` validate it successfully, they return an `Authentication` representing the trusted identity under the mechanism just applied, usually with `isAuthenticated() == true` along with the resolved `GrantedAuthority` instances.

These are **two roles of the same interface**, not two mandatory distinct classes, and it does not mean the framework simply flips a flag on the input object itself. A provider typically **creates a new result object** with a richer principal, verified authorities, and processed credentials. On failure, the process normally **throws an `AuthenticationException`** rather than returning an authenticated identity.

Think of `Authentication` as **an envelope passed between security components**: at first it holds what needs to be proven, and after success it holds the result that can be used to enforce policy. The contents of the envelope depend on the authentication mechanism and are not limited to username/password.

### Lesson Objectives

- Distinguish a request token from an authenticated token by **creation time, creator, state, principal, credentials, and authorities**.
- Understand why `AuthenticationManager.authenticate(...)` typically accepts and returns **the same interface type** with different meanings.
- Use `UsernamePasswordAuthenticationToken.unauthenticated(...)` properly to construct a username/password request; observe the object returned by `DaoAuthenticationProvider`.
- Know when an `Authentication` is placed into `SecurityContext`, and why **"having an object" is not synonymous with "being authenticated"**.
- Avoid security mistakes such as manually setting `isAuthenticated = true`, fabricating trusted authorities, or logging passwords.

## 2. Properties Keep Their Names but Change Their Role

The `Authentication` interface extends `Principal`. Its commonly used methods are:

| Method | As an unauthenticated request | As an authenticated result |
| --- | --- | --- |
| `getPrincipal()` | What the client claims to identify as, such as the string `"lan"`. Not yet proven. | The verified subject; may be a `UserDetails`, `Jwt`, `OAuth2User`, or a mechanism-specific object. |
| `getCredentials()` | Proof used for verification, such as a password, bearer token, or other credential object. | May be erased/null after authentication; **must not be relied on to retrieve the password again**. |
| `getAuthorities()` | Usually empty initially for username/password; client-supplied authorities must never be treated as trusted. | List of authorities built/mapped by the provider, such as `ROLE_READER`. |
| `isAuthenticated()` | Usually `false`: has not passed the appropriate verification step. | Usually `true`: the provider has returned a trusted result under a specific mechanism. |
| `getDetails()` | May carry request metadata such as IP/session details if set by a filter. | Not proof of roles or identity; may be carried over depending on the provider. |
| `getName()` | Name derived from the claimed principal. | Name of the verified subject; should not be treated as a global identifier key when integrating with an IdP. |

`principal` is not always a `UserDetails`. Code that writes `(UserDetails) authentication.getPrincipal()` for every login type will fail when the application moves to a JWT resource server, OIDC, or pre-authentication.

`getAuthorities()` only supplies the authorities attached to the token; endpoint access still depends on **authorization rules**. Having `ROLE_READER` does not mean being allowed to read every user's data.

### Understanding `isAuthenticated()` Correctly

- `isAuthenticated() == false` on a request token means **the request has not been proven yet**.
- `isAuthenticated() == true` on a provider result indicates that the token has been authenticated under that mechanism. It **does not mean the user is allowed to perform every action**.
- An `AnonymousAuthenticationToken` can return `true` from this method because of how anonymous access is represented in the framework. Therefore, when checking for a genuinely logged-in user, **do not write only `authentication != null && authentication.isAuthenticated()`**. Spring Security uses additional mechanisms to distinguish anonymous/remember-me tokens, such as `AuthenticationTrustResolver` in `authenticated()` and `fullyAuthenticated()` checks.

## 3. Who Creates the Request, and Who Returns the Result?

A typical Servlet username/password flow:

```text
Client sends username/password
     |
     v
Authentication filter (HTTP Basic, form login, or an appropriate filter)
     |
     | creates UsernamePasswordAuthenticationToken.unauthenticated(...)
     |   principal = "lan"                 [UNAUTHENTICATED]
     |   credentials = password
     |   isAuthenticated = false
     v
AuthenticationManager.authenticate(request)
     |
     v
ProviderManager selects an AuthenticationProvider supporting the token
     |
     v
DaoAuthenticationProvider
     |---- UserDetailsService loads the user from the identity store
     |---- PasswordEncoder matches the submitted password against the hash
     |---- checks account status and provider policies
     |
     +--- invalid: throws AuthenticationException
     |
     +--- valid: returns an authenticated Authentication
                     principal = UserDetails for "lan"
                     authorities = [ROLE_READER]
                     isAuthenticated = true          [AUTHENTICATED]
     |
     v
Filter receives the result and places it into SecurityContext
     |
     v
Authorization checks access permissions
     |
     v
Controller/service handles the permitted request
```

**Note 1 — input and output:** the common signature is:

```java
Authentication authenticated = authenticationManager.authenticate(request);
```

Both variables have the same `Authentication` interface type, but **they do not have the same level of trust**. Do not use the unauthenticated request object as though it were the result. A provider may return a different implementation and is not required to mutate the original object.

**Note 2 — the orchestrator:** `AuthenticationManager` is the contract; `ProviderManager` is the common implementation, trying `AuthenticationProvider` instances that support the token type. `DaoAuthenticationProvider` is used for username/password; JWT/OIDC authentication uses different mechanisms and providers/tokens.

**Note 3 — filter responsibilities:** calling `authenticationManager.authenticate(...)` directly inside a service **does not automatically guarantee** that the result will be placed in `SecurityContext`, persisted across requests, or trigger the full success/failure handling of a login filter. When using a standard filter mechanism, the framework manages that according to configuration.

## 4. `UsernamePasswordAuthenticationToken`: One Class, Two States

`UsernamePasswordAuthenticationToken` is a classic example of this model.

**Creating an unauthenticated request:**

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan",
        "DemoPass123!"
    );

System.out.println(request.isAuthenticated()); // false
```

The `unauthenticated(principal, credentials)` factory builds a token containing **unverified** data. For standard username/password requests, the authorities list in this state is empty.

**The provider creates the result after verification:**

```java
Authentication result = authenticationManager.authenticate(request);
System.out.println(result.isAuthenticated()); // true if no exception is thrown
```

A provider that authenticates successfully can create a trusted token via the appropriate internal API, such as `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)`. **Business code must not call this factory to unilaterally "recognize" a user who just entered a username and password without verification.**

Do not use `request.setAuthenticated(true)` to bypass `AuthenticationManager`: token implementations may reject it with `IllegalArgumentException`; more importantly, flipping a flag does not make a password valid, does not prove an identity, and does not make client-supplied authorities legitimate.

A very common point of confusion:

```text
BEFORE: request.isAuthenticated() == false
AFTER : result.isAuthenticated()  == true
```

Do not write code assuming or expecting that:

```text
request.isAuthenticated() automatically turns into true
request == result is always true
request.getPrincipal() and result.getPrincipal() always have the same class
result.getCredentials() always retains the original password
```

## 5. Standalone Java 17+ Demo with Spring Security 6.5

The example below uses **Java 17+, Spring Security 6.5.11, and Gradle**. It runs in the console so you can clearly observe the state before and after authentication, without needing a web server or touching sessions. `InMemoryUserDetailsManager` serves as the test user store; `DaoAuthenticationProvider` together with `BCryptPasswordEncoder` performs real verification.

File structure:

```text
authentication-two-roles/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AuthenticationRolesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authentication-two-roles'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.AuthenticationRolesDemo'
}
```

`src/main/java/demo/AuthenticationRolesDemo.java`:

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class AuthenticationRolesDemo {

    public static void main(String[] args) {
        // (1) Identity store and credential verification logic.
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails user = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();
        UserDetailsService users = new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        // (2) Input: an authentication request, not yet a trusted user.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.name=" + request.getName());
        System.out.println("request.authorityCount=" + request.getAuthorities().size());
        System.out.println("request.hasCredentials=" + (request.getCredentials() != null));

        // (3) Provider verifies the hash and returns a new authenticated result.
        Authentication result = manager.authenticate(request);

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("result.hasReaderRole="
                + result.getAuthorities().stream().anyMatch(
                        authority -> "ROLE_READER".equals(authority.getAuthority())));

        // (4) Demo places the result in the context; web filters normally handle this.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);

        try {
            Authentication current =
                    SecurityContextHolder.getContext().getAuthentication();
            System.out.println("context.name=" + current.getName());
        } finally {
            SecurityContextHolder.clearContext();
        }
        System.out.println("context.cleared="
                + (SecurityContextHolder.getContext().getAuthentication() == null));

        // (5) No successful result when the password is wrong.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }
    }
}
```

Run from the project root directory using Gradle and JDK 17+ (or a compatible Gradle Wrapper):

```bash
gradle run --quiet
```

The `System.out.println` lines from the program, in exact order:

```text
request.authenticated=false
request.name=lan
request.authorityCount=0
request.hasCredentials=true
result.authenticated=true
result.name=lan
result.principalIsUserDetails=true
result.hasReaderRole=true
context.name=lan
context.cleared=true
wrongPassword=BadCredentialsException
```

If a logger dependency emits its own output, those log lines may vary; the above is the stdout printed by the demo program itself. `BCryptPasswordEncoder` generates hashes with a random salt, so **do not print or compare literal hashes**.

### Step-by-Step Analysis

**(1) Preparing the identity store:** `UserDetailsService` only loads the user; `PasswordEncoder` compares the submitted password against the hashed password. `DaoAuthenticationProvider` combines both components and checks account conditions.

**(2) Creating the request:** `request.getName()` is already `lan`, but **this is only the name claimed by the client**. `getCredentials()` holds the demo string; having credentials does not prove they are valid. The initial authority count is 0.

**(3) Receiving the result:** `manager.authenticate(request)` only returns a result if a supporting provider authenticated successfully. `isAuthenticated()` is `true`, `principal` is a `UserDetails` object, and the `ROLE_READER` authority comes from the configured source. Do not write code that depends on `result.getCredentials()`, because `ProviderManager` by default can erase credentials after authentication.

**(4) Using `SecurityContext`:** the demo manually places the verified authentication into the context purely to show how retrieval works. This is a console example; in real HTTP requests, security filters are responsible for managing the context as configured. `clearContext()` in `finally` avoids leaving context on the console thread after completion.

**(5) Wrong password:** the provider does not return an authenticated token and throws `BadCredentialsException`. This is not an authorization error: the request failed to prove its identity.

### Why Doesn't This Demo Need Spring Boot?

`Authentication`, `AuthenticationManager`, `ProviderManager`, `DaoAuthenticationProvider`, and `SecurityContextHolder` belong to **Spring Security**. Spring Boot can auto-configure/wire these components in a web application, but **the two request/result roles of the interface** exist independently of Boot. When placed inside Spring Boot, standard filters typically call the manager and maintain the context per request, rather than calling it manually as in the console demo.

## 6. Using `Authentication` in a Real Spring Boot Application

In an HTTP endpoint that has passed through the security filter chain, a controller can receive the current `Authentication`:

```java
// Illustrative snippet inside a @RestController of an application already
// configured with Spring Security; not a standalone runnable class.
@GetMapping("/me")
public Map<String, Object> me(Authentication authentication) {
    if (authentication == null) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
    return Map.of(
        "username", authentication.getName(),
        "authorities", authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

Imports for `Map`, `Authentication`, `GrantedAuthority`, `GetMapping`, `ResponseStatusException`, and `HttpStatus` are required; this route must be protected by an appropriate `SecurityFilterChain`. The code above **only demonstrates how to use principal/authorities**, does not replace `authorizeHttpRequests(...)` rules, and does not make authorization decisions from a name passed in the request body.

In Spring MVC/Servlet, you may encounter:

- `Authentication authentication` in a controller method: represents the current security context when the framework supplies this parameter.
- `SecurityContextHolder.getContext().getAuthentication()`: how to access the current context when needed outside a controller; it can be `null` or an anonymous token.
- `@AuthenticationPrincipal`: injects the **authenticated principal** into a parameter of the appropriate type; not every principal is required to be a `UserDetails`.
- `hasRole(...)` / `hasAuthority(...)`: decides **whether access is permitted**, which is different from `isAuthenticated()`.

Do not turn `getName()` into the sole resource-ownership check if the endpoint handles multi-user objects; match a stable principal against the resource and business rules.

## 7. Other Authentication Mechanisms Still Use the Same Idea

The two roles are not tied to `UsernamePasswordAuthenticationToken`:

| Mechanism | Untrusted input representation | Representation after verification |
| --- | --- | --- |
| Username/password | Username + password in a request token. | Authenticated principal (typically `UserDetails`), authorities from the provider. |
| HTTP Basic | Filter reads `Authorization: Basic ...` and creates a username/password request token. | Provider result used in the request's `SecurityContext`. |
| Form login | Filter reads form parameters and creates an authentication request. | Result used to establish the session/context according to login configuration. |
| JWT bearer token | Filter/manager receives an untrusted bearer token. | After verifying signature, issuer, expiration, and configured conditions, may produce `JwtAuthenticationToken` with principal/claims and mapped authorities. |
| OIDC/OAuth2 login | Involves an authorization flow, callback, and verification of proof from an IdP, not just a username/password pair. | Authenticated principal of the OAuth2/OIDC mechanism, potentially with attributes/claims and authorities. |

Each mechanism has its own way of creating and verifying tokens. **Do not force every token into `UsernamePasswordAuthenticationToken`** or assume `principal` always has a password. With JWT, the access token can serve as the input to verify and does not need to call `UserDetailsService` on every request; that does not change the core principle "untrusted input → verification → trusted result".

The trust gained after authentication has **a scope**: for example, an authenticated JWT does not mean its bearer can view every invoice. Authorization, account policy checks, and data-level permission checks remain separate decisions.

## 8. `Authentication` and `SecurityContext`: Separating Two Responsibilities

`Authentication` is **the object describing an identity request/result**. `SecurityContext` is **the holder storing the authentication for the current execution context**; `SecurityContextHolder` provides access to that context.

In a Servlet HTTP request, Spring Security typically reads/creates the context at the start of the filter chain, updates the context after a successful authentication mechanism, and then finishes and clears the context appropriately. **Persistence across subsequent requests** may rely on a session and `SecurityContextRepository`, or be rebuilt from credentials/tokens on each new request, depending on configuration and the security mechanism.

Three distinctions to keep separate:

1. `AuthenticationManager.authenticate(request)` **returns a result object**; calling it manually does not by itself guarantee the web context is updated.
2. `SecurityContextHolder.getContext().setAuthentication(result)` **sets the result for the current execution context**; this operation does not implicitly save a session or send a login cookie.
3. **Authentication is not authorization**: once a trusted result exists, the authorization layer still decides whether the request is allowed to proceed.

When building a custom authentication filter, you must understand the filter contract, success/failure handling, session/context repository, concurrent request issues, and clearing the context. Do not assume that calling a setter inside a service completes a secure "login".

## 9. Common Mistakes and How to Fix Them

### Mistake 1: Creating an "authenticated token" directly from unverified input

```java
// Flawed in security principle: neither password nor token was verified.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
```

The code above grants trust/authorities based on client-controllable data. Only a trusted authentication component, after completing the required checks, should create a result with `isAuthenticated() == true` and authorities.

**Correct:** create a request using `unauthenticated(...)`; pass it to a configured `AuthenticationManager`, and only use the returned value after success.

### Mistake 2: Assuming `request` was mutated in place

```java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    username, password);
Authentication result = manager.authenticate(request);
// Use result; do not assume request itself is result.
```

If you keep `request` as the current authentication, you may retain an unauthenticated token or sensitive credentials. Always use the **returned result**.

### Mistake 3: Checking only `isAuthenticated()` to identify a real user

You must distinguish anonymous and remember-me access according to policy. `AuthenticationTrustResolver` provides the corresponding checks; in Spring Security HTTP configuration, `authenticated()`, `fullyAuthenticated()`, and role rules are far more context-appropriate than a naive flag check.

### Mistake 4: Treating request-supplied data as granted authorities

Clients can send `role=ADMIN`, forged claims, or arbitrary usernames. Trust only data that has passed verification, and map authorities on the server side. Checking "logged in" does not replace per-resource permission checks.

### Mistake 5: Logging `getCredentials()` or the entire token

Tokens/requests can contain passwords or bearer tokens. Even when the result has erased credentials, logging the original object or uncontrolled metadata still leaks secrets. Log only safe audit fields such as outcome, mechanism type, generic error codes, and correlation ID; never log raw secrets.

### Mistake 6: Using `getPrincipal()` without considering token type

With username/password using `DaoAuthenticationProvider`, the principal after authentication is typically `UserDetails`. With OIDC it may be `OidcUser`; with a resource server it is `Jwt` or a converter-produced principal. Use the appropriate abstractions or `getName()` alongside a stable identity mapping rule.

### Mistake 7: Ignoring failure handling

`AuthenticationManager.authenticate(...)` can throw `BadCredentialsException`, `DisabledException`, `LockedException`, or another subclass of `AuthenticationException`. Never catch all exceptions and return an authenticated token "so the app keeps running". For web login, let the filter handle exceptions according to the login mechanism and avoid leaking details that distinguish "user does not exist" from "wrong password".

## 10. Self-Check Questions

**Question 1.** A token has `principal="lan"` and `getCredentials()!=null`. Has it been authenticated?

**Answer:** Not enough information to conclude that. A request token can hold a completely wrong username and password. You must check the state and the provider verification flow, not infer authentication from the mere presence of data.

**Question 2.** After `manager.authenticate(request)` succeeds, should you read `request.getAuthorities()` for authorization?

**Answer:** No. Use `result.getAuthorities()` from the authenticated object and enforce authorization policies.

**Question 3.** `AnonymousAuthenticationToken.isAuthenticated()` can return `true`. Should you conclude the user has logged in successfully?

**Answer:** No. Spring Security distinguishes anonymous/remember-me from genuine authentication using trust-level checks.

**Question 4.** Does a console method calling `manager.authenticate(...)` successfully automatically create an HTTP login session?

**Answer:** No. Producing an authentication result and attaching/persisting `SecurityContext` are two separate responsibilities. Web sessions belong to filter/repository configuration and mechanisms.

**Question 5.** Does a verified JWT mean the user can call every API?

**Answer:** No. Token authentication only provides trusted identity/claims under the configured checks; authorization decides specific permissions.

## 11. References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): relationship among `Authentication`, `AuthenticationManager`, `ProviderManager`, and `SecurityContextHolder`.
- [Spring Security — Authentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html): contract, principal, credentials, authorities, `isAuthenticated()`.
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): the two factories `unauthenticated(...)` and `authenticated(...)`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): verifying credentials with `UserDetailsService` and `PasswordEncoder`.
- [Spring Security — AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): distinguishing authenticated, anonymous, and remember-me.

**Key takeaway:** the same `Authentication` interface can represent both an **untrusted authentication request** and a **verified authentication result**. The transition of trust happens inside `AuthenticationManager`/`AuthenticationProvider`. Afterward, the framework places the **result**—not the unverified request—into the security context for authorization policies to use.