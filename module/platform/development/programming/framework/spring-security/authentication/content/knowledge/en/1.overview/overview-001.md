# What Is Authentication and How Does It Solve Principal Identification?

> **Scope:** Authentication concepts and how Spring Security identifies the principal sending a request in a Servlet web application. The lesson uses username/password for illustration; the same trust principles also apply to sessions, tokens, and service identities.

## 1. From an HTTP Request, How Does the System Know Who Is Calling?

A request like `GET /api/orders/501` does not by itself state who the sender is. HTTP transmits a URL, method, headers, and body; any fields arbitrarily supplied by the client, such as `?userId=42` or `X-User-Id: 42`, are merely **claims**. If the server immediately trusts such claims, person A could change the ID to person B's ID and impersonate B.

**Authentication** is the process of verifying evidence to decide whether a request can be bound to a **principal** that the system trusts. A principal can be a user account, a service account, or a workload. With password-based login, the system checks whether the caller knows the password matching the claimed account; with keys or tokens, the system checks the corresponding form of evidence. Only when verification succeeds is that identity considered authenticated.

A limitation to remember: authentication proves that the caller satisfies the **chosen verification mechanism**; it does not by itself prove who they are in real life, nor does it guarantee that the secret or device has never been stolen. The trustworthiness of the outcome depends on how credentials are issued, stored, verified, and protected.

For example, the client sends `username=an` and `password=...`. Before verification, `an` is only a claimed identity. After matching a valid password, the server can create an `Authentication` representing the account `an`. On the next request, the application needs a mechanism to re-verify the evidence or restore a valid session; it cannot assume by default that every subsequent request comes from `an`.

### Commonly Confused Terms

| Term | Meaning | Example |
| --- | --- | --- |
| **Identity** | A profile or identifier managed by the system | User ID `u-42` |
| **Claimed identity** | A value presented by the caller before verification | Username `an` in a form |
| **Credential** | Information or a possessed item used to prove the right to use an identity | Password, private key, session cookie, bearer token |
| **Principal** | The identity represented by the framework after processing the authentication mechanism; data type depends on the mechanism | `UserDetails`, username, `Jwt` |
| **Authentication (result)** | State/object describing who is regarded as the principal, along with related credentials and authorities | `Authentication` in Spring Security |
| **Authorization** | Checking whether an identified principal is allowed to perform a specific action | Is `an` allowed to read order 501? |
| **Authority** | An attribute used when making authorization decisions | `ROLE_USER`, `SCOPE_orders.read` |

Display names, emails, usernames, and stable identifiers are not necessarily the same thing. An email may change or remain unverified; in business logic, it is usually best to map the trusted principal to a **stable internal ID**, rather than using a client-supplied value as the resource owner.

## 2. Authentication and Authorization Solve Two Different Questions

- **Authentication:** "Who is calling, and has the evidence for that identity been verified?"
- **Authorization:** "Given this identity and context, what are they allowed to do on a specific resource?"

Suppose An logs in successfully. That only indicates the request is bound to An's account according to the system's authentication mechanism. It does **not** prove An has permission to read Binh's order. To return order 501, the server must still check permissions on that order, such as `order.ownerId == authenticatedUserId` or an equivalent business policy.

A common mistake is taking `ownerId` from a query parameter or body and comparing it with `order.ownerId`. An attacker controls that claimed value as well, rendering the check meaningless. The right approach is to obtain the principal ID from the **server-trusted authentication result**, and then perform a separate authorization check.

| Scenario | Authentication question | Authorization question |
| --- | --- | --- |
| Unauthenticated user reads a public page | No login identity needed | Does the route allow `permitAll`? |
| An sends the correct password | Is the evidence for An's account valid? | Which endpoints is An allowed to access? |
| An reads Binh's order | An is authenticated, but is not Binh | Does An have permission for **this order**? |
| An API service calls another API with a token | Is the token trustworthy and still valid? | Does the service have the appropriate scope/authority? |

## 3. Processing Pipeline to Turn a Claim into a Trusted Identity

At a conceptual level, an authentication flow has six steps. Implementation details differ across HTTP Basic, form login, session cookies, JWTs, and OAuth2/OIDC.

1. **Collect evidence:** the client sends credentials according to a supported protocol. For example, HTTP Basic carries username/password in the `Authorization` header; form login receives login form data; an API may receive a bearer token. This data is always **untrusted** until verified.
2. **Verify:** the authentication component checks the evidence according to the proper rules. Passwords are checked against a hash using `PasswordEncoder.matches(...)`; tokens must have their signature/issuer, time conditions, and required claims verified per configuration; a session ID must map to a valid server-managed session.
3. **Identify the principal:** once the evidence is valid, the system links it to the corresponding account or service; it may load additional user details and authorities.
4. **Create a trusted result:** the framework creates/returns an authenticated `Authentication` carrying the `principal`, `authorities`, and relevant details. Never manually mark an object created directly from client data as "authenticated".
5. **Attach to request context:** the integration mechanism places the result into `SecurityContext` so downstream processing steps know the principal. Whether it is persisted for later requests depends on the session/token strategy; the mere presence of `SecurityContextHolder` does not mean a permanent login exists.
6. **Authorize and execute business logic:** the Security Filter Chain and/or method/service layer checks permissions; the controller/service reads the trusted principal and proceeds only when the access policy allows it.

Illustration of a common processing pipeline with username/password:

```text
HTTP request (untrusted credential from client)
    |
    v
Spring Security Filter Chain
    |
    v
Authentication filter
    |  creates authentication request token
    v
AuthenticationManager (typically ProviderManager)
    |
    v
AuthenticationProvider (e.g., DaoAuthenticationProvider)
    |-- UserDetailsService: looks up the account
    |-- PasswordEncoder: verifies password against hash
    |
    +-- Invalid --> rejects authentication / triggers error response mechanism
    |
    +-- Valid --> Authenticated Authentication
                         |
                         v
                  SecurityContext
                         |
                         v
                Authorization decision
                         |
                         v
                  Controller / Service
```

This is a **conceptual flow**, not a fixed filter order for every configuration. Each mechanism has its own filters/providers; in some cases the framework restores `SecurityContext` from a repository without requiring the password to be re-entered on every request.

### Why Is "Just Knowing the Username" Not Enough?

Usernames, emails, or user IDs are often guessable. If knowing an ID alone were enough to access data, the application would have turned a public identifier into a fake credential. **Identification answers "who do you claim to be"; authentication verifies "what evidence do you have to be treated as that principal".**

## 4. Key Spring Security Components to Know

### `SecurityFilterChain`

In a Spring MVC/Servlet application, Spring Security places filters in the path of HTTP requests. Filters read evidence according to the configured mechanism, manage the security context, handle related errors, and make or coordinate access decisions before the request reaches the controller. The specific filters and their order depend on the version, mechanism, and configuration; you should not assume a given filter name appears in every application.

### `Authentication`

This is the central interface representing an authentication result or request:

- `getPrincipal()`: the principal information; it is not guaranteed by default to be a `String` or a database entity.
- `getCredentials()`: the associated credential; after authentication it may have been erased from memory to reduce the risk of secret exposure.
- `getAuthorities()`: the collection of `GrantedAuthority` instances granted to the principal.
- `isAuthenticated()`: a status flag on the token; **it is not sufficient on its own to conclude this is an actual logged-in user**, because Spring Security also has anonymous tokens. Let the framework's authorization mechanisms, such as `authenticated()`, evaluate the request.
- `getName()`: the representative name of the principal; this may be the username or another value depending on the implementation.

Before verification, a `UsernamePasswordAuthenticationToken` may contain a username/password and is not yet trusted; after the provider verifies it successfully, the framework returns a valid authenticated token. Avoid creating a token from request data and manually setting the authenticated flag to `true`.

### `AuthenticationManager` and `AuthenticationProvider`

`AuthenticationManager` defines the `authenticate(...)` operation; `ProviderManager` is the common implementation, delegating across `AuthenticationProvider` instances. Each provider supports a specific type of authentication and can succeed, reject, or defer to another suitable provider. An application can use multiple providers without every provider checking the same kind of credential.

For example, `DaoAuthenticationProvider` is for username/password and relies on `UserDetailsService` and `PasswordEncoder`. `UserDetailsService` **loads user information** and does not check passwords itself; verification responsibility belongs to the provider and encoder.

### `SecurityContext` and `SecurityContextHolder`

`SecurityContext` holds the `Authentication` currently in use. In the synchronous Servlet model, `SecurityContextHolder` typically uses a strategy binding the context to the current thread; the framework sets up and clears the context around the request. Do not store the principal in a shared static variable, do not assume background/async threads inherit the context automatically, and do not read another request's `SecurityContextHolder`.

`SecurityContextRepository` determines how the context is read/saved across requests, typically tied to an HTTP session or a stateless strategy. **Authenticating the current request** and **persisting login across multiple requests** are two related but distinct concerns.

## 5. Spring Boot Example: Distinguishing Client Claims from an Authenticated Principal

The example below is a Servlet application using **HTTP Basic** and an in-memory account to observe the flow. Requirements: Java 17+, a Spring Boot project with Spring Web (MVC) and Spring Security, using Gradle or Maven generated by Spring Initializr. This is a learning demo; sample passwords must not be used in production.

Create `src/main/java/com/example/authdemo/AuthDemoApplication.java`:

```java
package com.example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails an = User.withUsername("an")
                .password(passwordEncoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(an);
    }
}

@RestController
class IdentityController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }
}
```

**How to run:** use the wrapper included in the Spring Boot project:

```bash
./gradlew bootRun
```

On Windows PowerShell you can use `.\gradlew.bat bootRun`; if the project uses Maven, run `./mvnw spring-boot:run` (Windows: `.\mvnw.cmd spring-boot:run`). Do not invoke `javac` directly on the file above because the Spring imports require dependencies from the build tool.

Open another terminal and run:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
```

The first two commands return **bodies respectively** `pong` and `principal=an`. The latter two, under this Basic configuration, receive **HTTP 401** because credentials are missing or invalid. Use `curl.exe` instead of `curl` if PowerShell aliases `curl` to another command. Error headers and bodies may vary depending on version/configuration; do not rely on a specific error string to determine the outcome.

**Explanation:** `/public/ping` is configured with `permitAll()`, so it does not require a logged-in principal. `/me` requires `authenticated()`. When receiving Basic credentials, Spring Security looks up the `an` account via `UserDetailsService` and matches the password against the BCrypt hash; if valid, the controller receives an `Authentication` and uses `getName()`. Even if the client tries adding `?userId=admin` to the URL, the controller still reads the name from the authentication result and does not trust the self-claimed parameter.

**What the demo proves and does not prove:** It proves the authentication path and that the principal is verified. It does not yet include resource-ownership checks on endpoints, dedicated role-based authorization, MFA, real user persistence, rate limiting, or brute-force protection. HTTP Basic sends credentials encoded in Base64 (not secret encryption); real deployments **must use HTTPS**.

## 6. Identifying the Principal Across Different Mechanisms

| Mechanism | Evidence verified | How the trusted identity is formed | Notes |
| --- | --- | --- | --- |
| **Form login + session** | Username/password at login; valid session ID on subsequent requests | Server authenticates at login and then restores the context from the session/repository when appropriate | Cookies must be protected; must manage CSRF, session fixation, expiration, and logout |
| **HTTP Basic** | Username/password sent in the request header | Provider verifies whenever Basic credentials need to be processed | Base64 does not replace TLS; browsers/clients may cache credentials |
| **Bearer JWT** | Token is checked for signature and conditions such as issuer, audience, and expiration per configuration | Resource server builds `Authentication` from a **verified** token | Merely seeing a `Bearer` header or decoding the payload is not authentication |
| **Opaque access token** | Token is looked up/introspected at a trusted source per configuration | Principal/authorities are derived from the token verification result | Must consider validity, token revocation, and verification-source failures |
| **OIDC login** | Login flow with an Identity Provider and verified protocol response | Application trusts the subject authenticated by the configured identity provider | Distinguish ID token, access token, and local session; verify issuer/subject |

There is no way for simply "receiving a token-like string" to be enough. Each type of evidence has its own verification rules and trust scope. For service-to-service calls, the principal may be a **client/service identity**, not necessarily an end user; all downstream authorization must understand that principal type properly.

## 7. What Happens When Authentication Fails or Authorization Is Missing

- **Missing or invalid evidence:** a request requiring authentication is routed into the login-prompt/challenge flow. For REST using HTTP Basic in the demo, the typical result is `401 Unauthorized` with an appropriate challenge. For form login, the response may be a redirect to the login page or a form error.
- **Authenticated but unauthorized:** an endpoint or service may return `403 Forbidden`. For example, An's account logs in with valid credentials, but an admin endpoint requires a different authority.
- **Public resource:** a `permitAll` route can operate without a logged-in account.
- **Request with an anonymous token:** Spring Security may place an `AnonymousAuthenticationToken` into the context for internal purposes; the presence of an `Authentication` or the `isAuthenticated()` flag on the token **does not by itself prove a real user has logged in**. Spring Security uses a mechanism to distinguish anonymous tokens when applying `authenticated()`.

The distinction table below assumes protected endpoints are appropriately configured; it does not imply every system always returns the exact same HTTP codes:

| Caller | Endpoint | Typical outcome |
| --- | --- | --- |
| Anonymous | Public | Allowed |
| Anonymous or invalid credentials | Requires login | 401 or initiates login flow |
| Authenticated, sufficient permissions | Permitted resource | Continues processing; typically 2xx if business logic succeeds |
| Authenticated, insufficient permissions | Restricted resource | 403 or corresponding denial decision |

## 8. Mistakes That Cause a System to Misidentify the Principal

1. **Trusting client-sent user IDs/emails/headers.** These values may describe a desired identity, not evidence. Trust identity only from a configured and protected authentication mechanism; if using headers from a reverse proxy, establish a trust boundary and prevent clients from calling the backend directly or spoofing headers.
2. **Finding a user in the database and treating it as a successful login.** `findByUsername` only looks up a profile; having an account does not mean the caller owns that account. Credential verification is still mandatory.
3. **Checking `isAuthenticated()` alone.** Anonymous tokens are an easily misunderstood exception. Use `authenticated()`, `hasAuthority(...)`, or official authorization mechanisms.
4. **Equating authentication with permission to access every record.** An endpoint requiring login can still leak data if it fails to check order ownership, tenant, role, or appropriate scope.
5. **Using raw passwords, `{noop}`, or comparing hashes incorrectly.** Store passwords using an appropriate encoder such as BCrypt/Argon2 with managed parameters; during login use the encoder's matching method, never compare plaintext directly against a hash string.
6. **Accepting a JWT because it decodes.** Base64URL is just encoding; you must verify the signature, issuer, audience, expiration, and required protocol/configuration conditions. A token with a valid signature issued for another API can still be invalid for this API.
7. **Ignoring credential and session lifecycles.** Leaked cookies, stolen tokens, or phished passwords let attackers act as a valid principal according to the verification mechanism. HTTPS, secret protection, expiration/revocation policies, MFA where appropriate, monitoring, and password-guessing defenses are needed. For cookie-based authentication automatically sent by browsers, evaluate CSRF protection.
8. **Logging credentials or passing context across threads improperly.** Never log plaintext passwords, bearer tokens, or session cookies. Request/thread-bound context must be managed by the framework; asynchronous tasks must propagate context intentionally.

A subtle point: `Authentication.getName()` is often a username, but many systems need an **immutable user ID** for ownership checks. Design the principal/custom user object so that services can obtain a reliable ID; do not take the ID from HTTP parameters just because the controller doesn't already have it.

## 9. How to Verify Whether a System Truly Identifies the Caller Correctly

Test each scenario below in sequence in a learning environment:

1. Send a request to a public endpoint while unauthenticated: allowed.
2. Send a request to a protected endpoint without credentials: authentication is required.
3. Send a wrong password: rejected, no authenticated identity is created for that account.
4. Send valid credentials: the controller observes the corresponding principal.
5. Keep A's credentials unchanged while changing the `userId` parameter or `X-User-Id` header to B: the server-side principal **must still be A**.
6. Have A read a resource owned by B: allowed only when **business authorization rules** permit it; A's successful login does not replace this step.
7. Observe logs at an appropriate level: see authentication results and access decisions, without exposing passwords, tokens, or cookies.

When diagnosing failures, ask in order: **what kind of evidence did the client provide? did the right filter run? how did the provider/validator verify it? where were the principal/authorities created from? was the context set/restored for the current request? finally, what did authorization rely on?** These questions help distinguish authentication failures, session-persistence issues, and authorization failures.

## 10. Knowledge Self-Check

**Question 1.** A client sends `X-User-Id: 42`. Can the server assert that the caller is account 42?  
**Answer:** No. A header set by the client is a claim; only a trusted authentication mechanism provides appropriate evidence.

**Question 2.** `UserDetailsService.loadUserByUsername("an")` returns an account. Is login complete?  
**Answer:** No. That is only the data-loading step; the password/token still must be verified by an appropriate provider/validator.

**Question 3.** An logs in with valid credentials, but accessing Binh's private order is blocked. Was authentication "wrong"?  
**Answer:** Not necessarily. Authentication may have succeeded; authorization for that specific resource denied access.

**Question 4.** Why is the presence of `Authentication` in `SecurityContextHolder` not enough to say a user is logged in?  
**Answer:** The context may contain an anonymous authentication; Spring Security's distinction/trust resolver or authorization policy is needed.

## Key Takeaways

**Trusted identification = claimed identity + verified evidence + result properly bound to the request.** Spring Security provides components to do this consistently: filters handle the login mechanism, manager/providers verify evidence, `Authentication` represents the principal, and `SecurityContext` carries the principal to the processing layer. **Authentication answers "who"; authorization must next answer "what can be done with this resource".**

### References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)