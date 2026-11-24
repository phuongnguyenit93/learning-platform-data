# Authentication.getDetails and Supplemental Request Data

## Objectives and Scope

In Spring Security, once you know **who is being authenticated** from `Authentication.getPrincipal()`, you sometimes need extra context about **the circumstances under which that authentication occurred**: the connection address submitting the login request, whether a session already existed at authentication time, a timestamp for auditing, or supplemental metadata. `Authentication.getDetails()` is the extension point for that data.

After this lesson, you will be able to:

1. Distinguish `principal`, `credentials`, `authorities`, and `details` on `Authentication`.
2. Understand the `Object` return type, possible `null` values, and why runtime type checks are required before use.
3. Read `WebAuthenticationDetails` in Servlet apps and understand the meaning and limits of `remoteAddress` and `sessionId`.
4. Grasp how filters create details, how `AuthenticationManager` processes authentication requests, and how providers can preserve/forward details onto the result.
5. Attach custom info via `AuthenticationDetailsSource` when genuinely required by business rules, along with security and lifecycle limits.
6. Handle differences in Spring WebFlux/reactive, where you cannot assume every `Authentication` carries `WebAuthenticationDetails`.

This lesson uses Spring Security 6.x with Spring Boot 3.x and Java 17+. Examples focus on HTTP authentication; this is not a full design guide for login flows, MFA, authorization, or audit logging.

## 1. What Does `Authentication.getDetails()` Actually Hold?

The `org.springframework.security.core.Authentication` interface represents either incoming authentication data or the authenticated identity returned by `AuthenticationManager`. Its core properties have distinct meanings:

| API | Question answered | Examples | Notes |
| --- | --- | --- | --- |
| `getPrincipal()` | Who is the person/application being identified? | username, `UserDetails`, `Jwt` | Type can vary by mechanism |
| `getCredentials()` | What proof was sent to verify the identity? | password, bearer token | May be erased after authentication; never log |
| `getAuthorities()` | Which rights are assigned to the authenticated identity? | `ROLE_USER`, `SCOPE_read` | Used for authorization |
| `getDetails()` | What supplemental info is attached to **this authentication**? | `WebAuthenticationDetails`, custom object | Not automatically user profile attributes |
| `isAuthenticated()` | Has the token been marked authenticated? | `true`/`false` | Do not use this flag alone to conclude a "real user" logged in: anonymous tokens can also be `true` |

The API signature is:

~~~java
Object details = authentication.getDetails();
~~~

The return type is **`Object`**, and it may be **`null`**. Spring Security does not promise one uniform schema across every `Authentication`: form login, HTTP Basic, JWT bearer tokens, OAuth2 login, pre-authentication, and custom providers can use different details values—or none at all.

**Do not confuse this with `UserDetails`.** `UserDetails` is the contract representing account data (username, encoded password, authorities, and account flags) in `UserDetailsService`-based authentication. `Authentication.getDetails()` holds supplemental metadata about the **authentication attempt or authentication result**. Durable account attributes (such as a server-verified tenant ID) should be modeled and governed in the appropriate principal/domain model rather than accidentally depending on a request-specific object.

Moreover, `getDetails()` is **not** `HttpServletRequest.getAttribute(...)`, `ServerWebExchange.getAttributes()`, MDC/trace context, or arbitrary session attributes. Those storage mechanisms have different lifecycles. Put only a minimal, intentional data set into `Authentication`.

## 2. Why Does Servlet Frequently Use `WebAuthenticationDetails`?

In several Spring Security Servlet HTTP authentication flows (especially standard form login), the object returned by `getDetails()` can be:

~~~java
org.springframework.security.web.authentication.WebAuthenticationDetails
~~~

This class is a small snapshot of the request at **the moment details were built**, containing:

- `getRemoteAddress()`: the peer address observed by `HttpServletRequest`. Behind a reverse proxy, this may be the proxy's address rather than the end client's IP; it depends on forwarded-header handling and trust boundaries.
- `getSessionId()`: the `HttpSession` ID **if a session already existed** when details were captured. This class **does not create a session** just to read an ID; the result can be `null`.

Safe reading example:

~~~java
Object raw = authentication.getDetails();
if (raw instanceof WebAuthenticationDetails details) {
    String remoteAddress = details.getRemoteAddress();
    String sessionId = details.getSessionId(); // May be null.
    boolean hadSessionWhenCaptured = sessionId != null;
    // Use only where authorized; never return sessionId to client.
}
~~~

This is an **illustrative snippet inside a method that received `Authentication authentication`**. Import `org.springframework.security.web.authentication.WebAuthenticationDetails`. Use `instanceof` instead of blind casting; other implementations do not have to conform to this Servlet type.

### 2.1. Snapshot from Authentication Time, Not the Current Request

Suppose a browser logs in via form at 09:00. The filter builds `WebAuthenticationDetails` for `POST /login`. The server saves `SecurityContext` in the session; at 09:20 the user sends `GET /me`. If `Authentication` is restored from the session, `getDetails()` may **still hold the data captured from `POST /login` at 09:00**. It does not automatically refresh on each new HTTP request.

Therefore, if you want the IP address or correlation ID of **the current request**, read metadata from the current request via the appropriate web API or request filter/tracing—do not mistake `authentication.getDetails()` for a per-request tracking system.

A session may also be created **after** details were captured; in that case `WebAuthenticationDetails.getSessionId()` can remain `null` even though the browser later has a session. Session fixation protection mechanisms can also rotate the session ID at login time, so never use the old session ID inside details to verify the current session.

### 2.2. Remote Address Is Not Authentication Proof

`getRemoteAddress()` describes the peer as observed by the server. NAT, VPNs, mobile networks, and reverse proxies all affect this value. `X-Forwarded-For` or `Forwarded` headers can be spoofed by clients if proxy boundaries are misconfigured. Never treat an IP, User-Agent, or client-asserted header as sufficient proof to log in or grant privileges. If risk scoring uses client addresses, you need trusted proxy configuration, source verification, and multi-signal evaluation.

## 3. How Are Details Created, Passed, and Saved?

Typical Servlet form-login flow:

~~~text
POST /login (username, password)
  -> UsernamePasswordAuthenticationFilter.attemptAuthentication(...)
     -> creates unauthenticated UsernamePasswordAuthenticationToken
     -> AuthenticationDetailsSource.buildDetails(request)
     -> authRequest.setDetails(details)
  -> AuthenticationManager.authenticate(authRequest)
     -> AuthenticationProvider checks credentials
     -> returns authenticated Authentication
        (provider may forward details from request to result)
  -> SecurityContext receives successful Authentication
     -> may be saved by SecurityContextRepository
  -> handler/controller reads authentication.getDetails()
~~~

`UsernamePasswordAuthenticationFilter`, a subclass of `AbstractAuthenticationProcessingFilter`, calls `setDetails(request, authRequest)` to attach details. The filter uses an `AuthenticationDetailsSource<HttpServletRequest, ?>` to build the object. Form login's default is `WebAuthenticationDetailsSource`.

In standard username/password mechanisms based on `AbstractUserDetailsAuthenticationProvider`/`DaoAuthenticationProvider`, details from the authentication request are copied onto the successful token. **This is behavior of those specific implementations**, not something every `AuthenticationProvider` or custom token is forced to do. If you build a custom provider returning a new token, you must decide whether to copy verified metadata.

Note two distinct methods:

- `Authentication#getDetails()`: **reads** supplemental info, part of the shared interface.
- `AbstractAuthenticationToken#setDetails(Object)`: **sets** details on `AbstractAuthenticationToken` subclasses; there is no universal `setDetails` method on every `Authentication` implementation.

Custom provider example, **only after credentials are genuinely verified**:

~~~java
// Illustrative code inside a successful AuthenticationProvider.
UsernamePasswordAuthenticationToken success =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedPrincipal, null, verifiedAuthorities);
success.setDetails(incomingAuthentication.getDetails());
return success;
~~~

This snippet is not a complete provider; `verifiedPrincipal` and `verifiedAuthorities` must come from valid authentication, never copied from untrusted input and marked `authenticated`. Never mark authentication successful just because details look valid.

### 3.1. Why Is `getDetails()` Sometimes `null`?

There are several legitimate reasons:

- The authentication mechanism does not collect supplemental metadata.
- A custom authentication token or provider did not transfer details.
- A token built from JWT, OAuth2, or pre-authentication has a different structure.
- Code is inspecting an `AnonymousAuthenticationToken` or a test-environment authentication.
- A new/transformed authentication result was created without retaining the original details object.

Shared services must never assume `getDetails() != null`, and certainly never cast every token to `WebAuthenticationDetails`.

## 4. Complete Example: Spring Boot Servlet Reading Form-Login Details

Create a Spring Initializr project with **Java 17+**, **Spring Boot 3.x**, **Spring Web**, and **Spring Security** (Maven). Place `src/main/java/com/example/demo/DetailsDemoApplication.java` as shown below. This example demonstrates the default details source from form login without creating a custom filter.

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class DetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DetailsDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @RestController
    static class DetailsController {

        @GetMapping("/")
        String home() {
            return "Open /me to log in and inspect authentication details.";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            Object raw = authentication.getDetails();
            WebAuthenticationDetails web =
                raw instanceof WebAuthenticationDetails details
                    ? details : null;

            return Map.of(
                "username", authentication.getName(),
                "detailsType", raw == null
                    ? "null" : raw.getClass().getSimpleName(),
                "remoteAddressAtLogin", web == null
                    ? "unavailable" : web.getRemoteAddress(),
                "hadSessionWhenCaptured", web != null
                    && web.getSessionId() != null
            );
        }
    }
}
~~~

### 4.1. How to Run

From the Maven project directory generated by Spring Initializr:

~~~bash
./mvnw spring-boot:run
~~~

With Windows PowerShell, use `.\mvnw.cmd spring-boot:run`. In a browser:

1. Open `http://localhost:8080/`: accessible without logging in.
2. Open `http://localhost:8080/me`: Spring Security redirects to the default login page (typically `/login`).
3. Log in as `alice` with demo password `demo-pass`.
4. After logging in, reopen `http://localhost:8080/me` and inspect the JSON.

Example **output shape** (not asserting identical IP/session values on every machine):

~~~json
{
  "username": "alice",
  "detailsType": "WebAuthenticationDetails",
  "remoteAddressAtLogin": "127.0.0.1",
  "hadSessionWhenCaptured": true
}
~~~

`remoteAddressAtLogin` may be an IPv6 loopback such as `0:0:0:0:0:0:0:1`; `hadSessionWhenCaptured` may be `true` or `false` depending on when the session was created. HTTP status after valid login is `200`, while unauthenticated requests under default form-login config typically receive a `302` redirect to `/login`. On failed login, Spring Security redirects to the default login error page; it returns no authenticated identity.

**Why doesn't the controller return the raw session ID?** A session ID is sensitive: if leaked, an attacker can exploit it under certain conditions. The example emits only a boolean showing whether metadata was present, without exposing the value. The password in the example is also strictly for local demo use; production environments need proper secret management, credential protection, and HTTPS.

### 4.2. Tracing the Lifecycle Accurately

- `formLogin(withDefaults())` configures form-login components, where the filter constructs a request token with details.
- `DaoAuthenticationProvider` verifies the password hashed by `BCryptPasswordEncoder` and creates the authenticated token.
- With default session-based form login, the login result can be retained in `SecurityContext` via `SecurityContextRepository`.
- The controller receives the `Authentication` bound to the authenticated user. `getDetails()` inspects metadata from that authentication event, not re-reading every HTTP header of `GET /me`.
- `Map.of` rejects `null` values; the example converts `null` to strings and returns only a boolean for session info.

You can open a private browser window, log in again, and observe the difference. If you want to inspect the current request, compare `HttpServletRequest.getRemoteAddr()` in a separate endpoint against `WebAuthenticationDetails.getRemoteAddress()`, keeping proxy boundaries and privacy in mind.

## 5. Customizing Details with `AuthenticationDetailsSource`

Customize only when the metadata genuinely supports a specific authentication flow or auditing need. For example, suppose you want to record **the timestamp** and **peer address** at login time instead of the default `WebAuthenticationDetails`. A good choice is a small, immutable object containing no passwords, tokens, cookies, or `HttpServletRequest`.

Below are **changes applied to the project in section 4**, not a standalone Java program. Add these imports to `DetailsDemoApplication.java`:

~~~java
import java.io.Serializable;
import java.time.Instant;
~~~

Inside `DetailsDemoApplication`, add a nested record (if persisted via session, the object should be serializable):

~~~java
record LoginRequestDetails(
    String remoteAddress,
    Instant capturedAt
) implements Serializable {}
~~~

Replace the `security(...)` bean method with:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form.authenticationDetailsSource(
            request -> new LoginRequestDetails(
                request.getRemoteAddr(),
                Instant.now()
            )
        ))
        .build();
}
~~~

Configuring `formLogin(...).authenticationDetailsSource(...)` provides a custom `AuthenticationDetailsSource<HttpServletRequest, ?>` to the form-login filter. Whenever the filter processes a form authentication attempt, the lambda creates `LoginRequestDetails`. **By changing the source, you replaced the default details type**, so `getDetails()` for this login will be `LoginRequestDetails`, no longer `WebAuthenticationDetails`.

To display the custom object in the controller, replace the `raw`-reading logic in `me(...)` with:

~~~java
Object raw = authentication.getDetails();
LoginRequestDetails login =
    raw instanceof LoginRequestDetails details ? details : null;

return Map.of(
    "username", authentication.getName(),
    "detailsType", raw == null
        ? "null" : raw.getClass().getSimpleName(),
    "capturedAt", login == null
        ? "unavailable" : login.capturedAt().toString(),
    "hasRemoteAddress", login != null
        && login.remoteAddress() != null
);
~~~

When logging in again in a new session, `detailsType` will be `LoginRequestDetails` in the configured form-login flow, and `capturedAt` reflects when details were built. Never use `capturedAt` to enforce session/token lifetimes: it is merely illustrative audit metadata. If you need both remote address and session ID from `WebAuthenticationDetails`, define a record holding those fields or choose an explicit wrapper strategy; never cast a custom object to `WebAuthenticationDetails`.

### 5.1. When Metadata Might Affect Security Decisions

Never authenticate or grant privileges because a client sends `X-User-Role: admin`, `X-Tenant: foo`, `X-Trusted-IP`, or a self-asserted header attached to details. Any data a client can modify must be treated as **untrusted input** until independently verified. For example:

- A correlation/request ID can support tracing if established or normalized by a trusted point; never use it as user proof.
- An IP address serves only as an auxiliary signal after verifying a trusted forwarded-header source.
- Certificate metadata can be valuable for authentication when a TLS/mTLS boundary has verified the certificate and passed the outcome in a tamper-resistant way.
- If metadata is an OTP or security factor, use a proper authentication mechanism to verify and **erase** the secret immediately; never leave raw values in details or session.

An `AuthenticationProvider` may use verified metadata as supplemental input, yet the trusted result must originate from the authentication step itself. Never promote an authentication request to an authenticated token merely because `details` is present.

### 5.2. Never Store Request Objects Inside `SecurityContext`

`Authentication` can outlive a single HTTP request, held in a session, cache, or passed across another boundary. Never store `HttpServletRequest`, `HttpServletResponse`, streams, servlet container objects, large mutable maps, raw sessions/cookies/tokens, or unnecessary personal data in details. Metadata should be small, strongly typed, serializable when persistence requires it, and governed by an appropriate retention policy.

`AbstractAuthenticationToken.eraseCredentials()` inspects credentials/principal/details and calls `eraseCredentials()` on any of them implementing `CredentialsContainer`. That **does not mean** Spring Security automatically scrubs arbitrary fields in custom details objects. Avoid putting secrets in there in the first place.

## 6. What About HTTP Basic, Bearer Tokens, and WebFlux?

Do not guess what details type an `Authentication` object holds simply by looking at an HTTP request.

**HTTP Basic (Servlet):** a filter can create an authentication token and attach metadata for the current request, depending on implementation. Seeing `WebAuthenticationDetails` in form login does not guarantee every Basic setup maintains that exact structure.

**JWT/bearer resource server:** the authentication token may be `JwtAuthenticationToken` or another implementation. Claims `iss`, `sub`, `aud`, and `scope` belong to the verified token; they are not automatically `Authentication.getDetails()`. Use the `Jwt`/principal or token API to read claims after verification. Never extract claims from an unverified bearer string or treat `getDetails() == null` as failed authentication.

**Pre-authentication, mTLS, and custom mechanisms:** metadata can be a custom type per filter/converter/provider. Check that mechanism's contract. Only `Authentication#getDetails()` is a shared API; no rule forces every provider to populate the same type.

### 6.1. Reactive: Same `Authentication`, No Servlet Request

Spring WebFlux uses `ServerWebExchange` and stores the security context in the Reactor Context. It does not use Servlet `HttpServletRequest` or create `WebAuthenticationDetails` by default. If a reactive mechanism needs details, `ServerAuthenticationConverter` and corresponding auth components can construct the token and attach appropriate data; reactive providers must preserve them if the result needs them.

Example **method snippet inside a `@RestController` in a WebFlux project**, where the security chain has already authenticated:

~~~java
@GetMapping("/me")
Mono<Map<String, String>> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> Map.of(
            "username", auth.getName(),
            "detailsType", auth.getDetails() == null
                ? "null"
                : auth.getDetails().getClass().getSimpleName()
        ));
}
~~~

This illustrative snippet needs imports for `java.util.Map`, `reactor.core.publisher.Mono`, `org.springframework.web.bind.annotation.GetMapping`, `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext`, and `org.springframework.security.core.Authentication`. It is not standalone: it requires Spring WebFlux/Security, a controller, and login configuration. It checks whether details exist without casting to a Servlet class.

To get **the address/connection of the current WebFlux request**, use `ServerWebExchange` or `ServerHttpRequest` under trusted proxy policies, independent of `Authentication.getDetails()`. `ReactiveSecurityContextHolder` uses Reactor Context and must not be replaced with Servlet/ThreadLocal `SecurityContextHolder.getContext()`.

## 7. When to Use Details, and When Not To

| Need | Appropriate location | Why |
| --- | --- | --- |
| Know authenticated username/account | `Authentication.getPrincipal()` / `getName()` | Identity data |
| Check role/scope/permission | `getAuthorities()` + authorization rules | Authorities granted by authentication mechanism |
| Metadata of **the login event**: peer IP, capture time | `getDetails()` if supported by mechanism | Supplemental, authentication-time snapshot |
| Read IP/header/trace ID of **the current request** | Servlet request/WebFlux exchange/tracing | Independent of login time |
| Store durable user/tenant profile | Verified user/domain model | Longer lifecycle than a single request/login |
| Store session state and expiration | Session infrastructure / security context repository | Manages state and lifecycle |
| Write audit logs for every request | Filter/interceptor/observability pipeline | Login-time details alone are insufficient |
| Secret factor/password/token data | Dedicated authentication mechanism | Secrets must be verified and protected separately |

In session-based apps, details can be serialized or appear in `Authentication.toString()`, logs, debug dumps, or monitoring if you inadvertently log the whole object. Never return `authentication.getDetails()` directly in a JSON API for "easy debugging". Design responses to pick only disclosable fields, avoiding sensitive identifiers—especially session IDs, raw client tokens, internal addresses, and authentication headers.

## 8. Common Mistakes and How to Fix Them

### Mistake 1: Blind casting

~~~java
WebAuthenticationDetails details =
    (WebAuthenticationDetails) authentication.getDetails();
~~~

This can throw `ClassCastException` or yield `null` when another mechanism is configured. Use a type check and fallback matching the data contract:

~~~java
Object raw = authentication.getDetails();
if (raw instanceof WebAuthenticationDetails details) {
    // Use specifically typed Servlet info.
} else {
    // Absent or a different details type.
}
~~~

### Mistake 2: Treating `sessionId` in details as the current session

`getSessionId()` was captured when `WebAuthenticationDetails` was built; a session may be created or its ID rotated afterward. For current session logic, use proper session management rather than treating the details snapshot as the source of truth.

### Mistake 3: Reading IP address and using it as an access permission

An IP does not prove identity. Behind a proxy, the connection address depends on forwarded-header configuration. Never use an unverified `X-Forwarded-For` value in place of principal/authorities or to skip authentication.

### Mistake 4: Custom provider builds a new token and drops details

A custom provider can return a new authentication result without details. If metadata genuinely needs to be kept, the provider must intentionally preserve appropriate data after verifying credentials, under a no-secrets policy. Missing details is not automatically a `SecurityContextHolder` bug.

### Mistake 5: Stuffing request objects or secrets into details

`HttpServletRequest` and request streams are unsuitable for long-lived session/context storage. Raw passwords, OTPs, cookies, or bearer tokens are not safe metadata. Choose small, immutable objects with reasonable data retention.

### Mistake 6: Using login-time details for per-request audit logs

A browser may send hundreds of requests after one login; stored details remain an old snapshot. Use request filters/interceptors and per-request trace/correlation IDs if you want to track ongoing activity.

### Mistake 7: Using Servlet types in reactive handlers

`WebAuthenticationDetails` depends on `HttpServletRequest`. WebFlux uses `ServerWebExchange`; details may be null or a different type. Use `ReactiveSecurityContextHolder` and verify the actual data contract of your converter/provider.

## 9. Reasoning Exercises

**Scenario A.** A user logs in via form at 08:00 from a connection with remoteAddress `192.0.2.10`. At 08:30, they visit `/profile` from another network using the same session. Will `authentication.getDetails()` reflect the new IP?

**Answer:** Do not assume so. If the context and old authentication are restored from the session, details may still hold the address captured at login. To inspect the current request, read the current request through a trusted mechanism.

**Scenario B.** `WebAuthenticationDetails.getSessionId()` is `null`, yet subsequent requests are still logged in. Is there a contradiction?

**Answer:** No. When details were built, a session may not have existed yet; a session was created or its ID changed afterward. The snapshot does not sync backward from session management.

**Scenario C.** A controller accepts a valid JWT, `authentication.getPrincipal()` is `Jwt`, yet `getDetails()` is null. Is this a sign the JWT wasn't verified?

**Answer:** No. The details field is optional. Inspect the authentication flow/resource server and the claims on the verified token; never use details as a default indicator of JWT validation.

**Scenario D.** An app wants to record a per-request HTTP request ID. Should it be placed into session-stored details at login?

**Answer:** Inappropriate, because the request ID changes on every request. Use request context and logging/observability; attach data to authentication only if it truly describes the authentication event.

**Scenario E.** A frontend sends `X-Role: ADMIN` and the backend stores it in `authentication.getDetails()`. May that be treated as a user authority?

**Answer:** No. Client headers are untrusted input; roles must come from a trusted authority source after authentication or server policy, and be represented/checked properly in the authorization pipeline.

## 10. Adoption Checklist

1. Have you identified the active authentication mechanism (form login, Basic, JWT, OAuth2, pre-auth, custom) and whether the stack is Servlet or reactive?
2. Could `getDetails()` be null or a different type? Do you have `instanceof` checks and sensible fallbacks?
3. **When** was the metadata created? Is it a login snapshot, current HTTP request info, or durable data?
4. Is the data source trustworthy? Could IP/headers be spoofed by a proxy or client?
5. Are any secrets, session IDs, raw JWTs, cookies, or personal data logged, serialized, or returned by an API?
6. If a custom provider/converter builds a new token, is needed metadata preserved properly only after verifying credentials?
7. Is per-request auditing required? If so, are you using request-scoped observability instead of a stale snapshot?
8. If working in WebFlux, are you using Reactor Context properly without casting to Servlet types?

**Key takeaway:** `Authentication.getDetails()` is an **optional authentication metadata field**, not the default place to store identity or authorities. In Servlet form login, it is typically `WebAuthenticationDetails` holding the peer address and a potentially null session ID from authentication time. Read it according to the exact type, lifecycle, and trust level of the mechanism in use.

## Official References

- [Spring Security 6.5 API — Authentication](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security 6.5 API — AbstractAuthenticationToken](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Spring Security 6.4 API — WebAuthenticationDetails](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/web/authentication/WebAuthenticationDetails.html)
- [Spring Security 6.5 API — FormLoginConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 API — AuthenticationWebFilter (WebFlux)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
