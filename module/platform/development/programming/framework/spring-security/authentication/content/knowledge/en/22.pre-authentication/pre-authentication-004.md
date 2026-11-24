# RequestHeaderAuthenticationFilter and Identity Data from Headers

> **Scope:** Spring Security Servlet, **pre-authentication** mechanism. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x. An identity header is trustworthy only when **an upstream system has already authenticated the user and controls all ingress paths to the application**.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why `RequestHeaderAuthenticationFilter` only reads an identity from an HTTP header and **does not verify passwords, signatures, or tokens**.
2. Describe the flow `header → PreAuthenticatedAuthenticationToken → AuthenticationManager → PreAuthenticatedAuthenticationProvider → UserDetails/authorities → SecurityContext`.
3. Distinguish between **authentication at the gateway/SSO**, **accepting pre-authenticated identity in the application**, and **resource access authorization**.
4. Configure a servlet example with the `X-Authenticated-User` header, restrict recognized users, and handle missing or invalid headers.
5. Identify risks such as header spoofing, direct backend access, stale identity in sessions, and misassigned permissions; design tests across both Java and proxy infrastructure.

## 1. What Is Pre-authentication?

In a **pre-authentication** architecture, another system has already performed authentication before the request reaches the Java application. For example, an organization uses an identity-aware reverse proxy, enterprise SSO gateway, web access manager, or container that has verified the caller's identity. Upon success, that component forwards the verified identity to the backend.

```text
Browser / HTTP client
     │ 1. Send cookie/token/credentials to the upstream system
     ▼
Gateway / SSO / reverse proxy
     │ 2. PERFORM authentication: verify session/token/certificate...
     │ 3. Strip client-sent headers, set verified identity header itself
     │    X-Authenticated-User: lan
     ▼
Spring Boot backend (accepts traffic only from trusted gateway)
     │ 4. RequestHeaderAuthenticationFilter reads username="lan"
     │ 5. PreAuthenticatedAuthenticationProvider looks up user & authorities
     │ 6. SecurityContext holds authenticated Authentication
     ▼
AuthorizationFilter / controller
     │ 7. Check ROLE_READER, ROLE_ADMIN... per endpoint
     ▼
HTTP response
```

**Core point:** `RequestHeaderAuthenticationFilter` **does not perform step 2**. It does not know whether upstream verified a cookie, password, JWT, or MFA. The filter **merely extracts the name** from the request header, then passes through Spring Security's `AuthenticationManager` infrastructure to load account information and permissions. If someone can send a forged header directly to the application, they can impersonate another user.

For instance, the following request is **not proof of login** if sent directly by an unverified client:

```http
GET /api/me HTTP/1.1
Host: app.example.org
X-Authenticated-User: admin
```

The header is meaningful only after **a trusted proxy** strips every client-supplied value and sets the value from an **actual authentication result**. Do not use this mechanism for a public application that accepts headers directly from the Internet.

### Three Layers of Responsibility

| Layer | Action | Who Owns It? |
|---|---|---|
| **Upstream authentication** | Prove who the user is, verify credential/token/session, MFA if required | SSO/gateway/IdP or infrastructure |
| **Pre-authentication in Spring Security** | Accept verified identifier, look up account, load authorities, populate `SecurityContext` | `RequestHeaderAuthenticationFilter`, provider, and user service |
| **Authorization** | Decide which APIs and actions that account may invoke | Application authorization rules |

Looking up a user by username and producing `Authentication.isAuthenticated() == true` on the backend does not prove that the backend itself verified a password. The proof rests in **the upstream system** and in how infrastructure prevents forged headers from entering.

## 2. How Does RequestHeaderAuthenticationFilter Work?

`org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter` extends `AbstractPreAuthenticatedProcessingFilter`. It provides two extraction hooks from `HttpServletRequest`:

- `getPreAuthenticatedPrincipal(request)`: reads the header value containing the **username/principal**.
- `getPreAuthenticatedCredentials(request)`: returns the dummy string `"N/A"` by default because passwords are typically handled externally; if `credentialsRequestHeader` is configured, it can read another header, though it **does not verify** that value itself.

The filter creates an untrusted `PreAuthenticatedAuthenticationToken` and invokes `AuthenticationManager.authenticate(...)`. `PreAuthenticatedAuthenticationProvider` typically resolves the username into a `UserDetails` and authorities via `AuthenticationUserDetailsService`. Spring Security then places the result in `SecurityContext` for request authorization.

### Notable Properties

| Property | Meaning and Default |
|---|---|
| `principalRequestHeader` | Header name containing the username; defaults to `SM_USER` (Siteminder compatibility). Can be changed to `X-Authenticated-User`. |
| `credentialsRequestHeader` | If set, the filter reads credentials from that header; **unset** by default so the dummy `"N/A"` is used. This is not a credential verification step. |
| `exceptionIfHeaderMissing` | Defaults to `true`: missing header throws `PreAuthenticatedCredentialsNotFoundException`. Setting `false` yields a `null` principal and lets the chain continue; authorization must ensure unauthenticated requests are ultimately denied. |
| `authenticationManager` | Required: receives `PreAuthenticatedAuthenticationToken` and runs the matching provider. |
| `continueFilterChainOnUnsuccessfulAuthentication` | Inherited from superclass, defaults to `true`: manager errors are handled and the chain can continue. Safe only when no weaker auth branch exists and authorization always denies unauthenticated requests. |
| `checkForPrincipalChanges` | By default does not re-check the principal if `SecurityContext` already holds an Authentication; can be enabled to handle identity changes across requests when using sessions. |
| `invalidateSessionOnPrincipalChange` | When principal-change checking is enabled, defaults to invalidating the old session when the identity changes. |

**Missing header vs. empty header:** the default condition in `RequestHeaderAuthenticationFilter` checks for `null`, which does not replace full validation of a "valid username." An existing header that is empty or invalid must be rejected by the gateway and/or the application's user lookup logic. Never map an empty header to a default account.

### Detailed Internal Flow

```text
HTTP request from trusted proxy
       |
       v
RequestHeaderAuthenticationFilter
  principal = request.getHeader("X-Authenticated-User")
  credentials = "N/A"
       |
       +-- principal == null? (behavior depends on exceptionIfHeaderMissing)
       |
       v
PreAuthenticatedAuthenticationToken(principal, "N/A")
       |
       v
AuthenticationManager
       |
       v
PreAuthenticatedAuthenticationProvider
       |
       v
AuthenticationUserDetailsService
       |
       +--> UserDetailsService / database / directory
       |      - does the user exist?
       |      - is the account status permitted?
       |      - which authorities are granted?
       |
       v
Authentication (authenticated=true, principal, authorities)
       |
       v
SecurityContext -> AuthorizationFilter -> Controller
```

`PreAuthenticatedAuthenticationProvider` does not verify passwords or header signatures itself. By default it can use `AccountStatusUserDetailsChecker` to evaluate `UserDetails` status, but that **does not** replace upstream authentication.

## 3. Spring Boot 3.x / Spring Security 6.x Example

Suppose the deployment environment has a **single proxy that authenticates users**, sets `X-Authenticated-User`, and the internal network blocks clients from reaching Spring Boot directly. This section illustrates the **application side**, without providing the upstream authentication mechanism.

### 3.1. Gradle Dependencies

In a Spring Boot 3.x project with plugin/versions managed by the BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Neither `spring-security-ldap`, OAuth2 client, nor a JWT decoder is needed in this example: upstream has already performed authentication; the application only performs pre-auth and authorization. In real deployments, `UserDetailsService` can query a database or enterprise account directory.

### 3.2. Configuring SecurityFilterChain and Pre-Auth Provider

Save to `src/main/java/com/example/demo/HeaderSecurityConfig.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class HeaderSecurityConfig {

    @Bean
    UserDetailsService users() {
        // Simulates an internal account/role store only.
        // This password is NOT used for verification in pre-auth.
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password("{noop}unused-in-preauth")
                .roles("READER")
                .build()
        );
    }

    @Bean
    AuthenticationManager preAuthManager(UserDetailsService users) {
        var userDetails =
            new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);
        provider.setThrowExceptionWhenTokenRejected(true);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http, AuthenticationManager preAuthManager) throws Exception {

        var headerFilter = new RequestHeaderAuthenticationFilter();
        headerFilter.setPrincipalRequestHeader("X-Authenticated-User");
        headerFilter.setAuthenticationManager(preAuthManager);

        // Missing header => do not create Authentication;
        // any unauthenticated request must be blocked at authorization.
        headerFilter.setExceptionIfHeaderMissing(false);

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me").hasRole("READER")
                .anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                headerFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
```

**What is each component's responsibility?**

1. `users()` is a **simulated** account store containing only `lan` and `ROLE_READER`. In production, replace it with a `UserDetailsService` querying active users and real role policies. Do not accept arbitrary header strings and automatically grant `ROLE_ADMIN`.
2. `UserDetailsByNameServiceWrapper` adapts an `Authentication` to a `UserDetailsService.loadUserByUsername` call; the provider uses the looked-up data to recognize the identity and authorities. It **does not** execute `PasswordEncoder.matches` in this flow.
3. `ProviderManager` contains `PreAuthenticatedAuthenticationProvider`, with no `DaoAuthenticationProvider` for an alternate password login path.
4. `RequestHeaderAuthenticationFilter` reads the username from `X-Authenticated-User`, and does not treat that header value as a password or JWT.
5. `setExceptionIfHeaderMissing(false)` is an **intentional choice of this example**: if the header is absent, the filter skips pre-auth; combined with `anyRequest().authenticated()`, `Http403ForbiddenEntryPoint`, and no other login mechanism, access is blocked. The filter's default remains `true` (throw exception).
6. `SessionCreationPolicy.STATELESS` requires every request to carry an identity freshly verified upstream, without relying on a prior Spring Security login session.
7. `formLogin` and `httpBasic` are disabled so the example does not expose another authentication path bypassing the gateway architecture. `Http403ForbiddenEntryPoint` returns 403 when the application lacks a valid Authentication.
8. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the pre-auth filter in the filter chain before authorization. Do not register `headerFilter` itself as a separate Servlet `Filter` bean: that avoids running it twice outside `SecurityFilterChain`.

The example illustrates only the **mechanism**, without providing a production user store, SSO infrastructure, or network restriction policy. **Do not deploy publicly as-is** and rely on an obscure header name to protect the system.

### 3.3. Endpoint Reading Identity and Permissions

Save to `src/main/java/com/example/demo/MeController.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    public record MeResponse(String username, List<String> authorities) {}

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new MeResponse(authentication.getName(), roles);
    }
}
```

`Authentication` is present in the controller because the endpoint requires `ROLE_READER`. The value `authentication.getName()` comes from the principal forwarded by the proxy and accepted by `UserDetailsService`; the authorities list is permission data loaded by the application.

To run the demo application, you need a `@SpringBootApplication` class in `com.example.demo` (or a parent package) with `SpringApplication.run(...)`, built with the Spring Boot Gradle plugin and launched via `./gradlew bootRun`; on Windows use `gradlew.bat bootRun`. Do not run the config file with standalone `javac` because it requires the Spring Boot runtime and dependencies.

## 4. Mandatory Conditions at the Reverse Proxy / SSO

The example above is secure only if the infrastructure satisfies **all three conditions**:

1. **Every request** to the backend must go through an authenticated gateway; the backend has no public ingress or port, and no side/health/debug route bypasses controls outside policy.
2. The gateway **strips or overwrites** every client-sent copy of the identity header (including variants, duplicate headers, and other headers the application might interpret as identity). Only generate `X-Authenticated-User` from the **upstream authentication result**.
3. The gateway → backend channel is protected by a controlled private network, TLS/mTLS where appropriate, and least-privilege access. Never use client IP lists or `X-Forwarded-For` as proof of login.

A valid scenario: the client sends `X-Authenticated-User: admin` while the actual SSO authentication is `lan`. The gateway must **discard the `admin` value** and forward `X-Authenticated-User: lan` to the application. If the client is unauthenticated, the gateway rejects immediately and never forwards the request under an arbitrary identity.

### Nginx Sample with auth_request (Deployment Illustration)

Nginx can call an internal auth service to decide 2xx/401/403; the abbreviated example below is **only valid** when `auth-service` genuinely verifies the session/token and returns the identity header from that authentication result:

```nginx
location = /_auth {
    internal;
    proxy_pass http://auth-service.internal/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";

    # Do not let clients pre-supply an identity to the auth service.
    proxy_set_header X-Authenticated-User "";
}

location / {
    auth_request /_auth;

    # Username returned by the auth service AFTER verification.
    auth_request_set $verified_user $upstream_http_x_authenticated_user;

    # Overwrite any identity header sent by the client.
    proxy_set_header X-Authenticated-User $verified_user;

    proxy_pass http://spring-backend.internal:8080;
}
```

Explanation: `auth_request` permits passage only when the auth subrequest is approved; `auth_request_set` captures the header provided by the **trusted auth service**, and `proxy_set_header` rewrites the identity before forwarding to Spring Boot. If the auth service returns no username, the variable is typically empty and the backend rejects it per account policy. You must accurately configure URIs/upstreams, cookie/token forwarding, timeouts, and error handling for your environment. This configuration **does not create SSO by itself** and is meaningless if `spring-backend.internal` remains reachable from untrusted networks.

### Why Can't You "Just Trust Headers" Because HTTPS Is Enabled?

HTTPS encrypts the transport; it **does not authenticate header contents supplied by the client**. A request over valid TLS can still carry `X-Authenticated-User: ceo` fabricated by the caller. Only when authentication and a trust relationship between gateway and backend are established can the application use that header as an identity.

## 5. Request States and Responses

Assuming the exact Java example from section 3, with requests sent through a **gateway-protected path**:

| Request State at Backend | Spring Security Processing | Expected Outcome |
|---|---|---|
| `X-Authenticated-User: lan`; active user | Looks up user `lan`, grants `ROLE_READER` | `GET /api/me` returns 200 and identity `lan` |
| Missing header | Filter skips pre-auth due to `false` config; endpoint requires authentication | 403 |
| `X-Authenticated-User: unknown-user` | `UserDetailsService` finds no user; no valid `Authentication` | 403 in a config with no other fallback |
| Empty header | No account found with empty username | Rejected; should be stripped early at gateway |
| `X-Authenticated-User: lan` but account disabled | `AccountStatusUserDetailsChecker` rejects account per `UserDetails` status | 403 in the example configuration |
| Valid header but lacks `ROLE_READER` | Identity authentication may succeed, authorization is denied | 403 for `/api/me` |
| Upstream authentication fails | Gateway does not forward request | Usually 401/403 from gateway, system-dependent |
| Request reaches backend directly and sets `X-Authenticated-User: lan` | **Filter cannot distinguish forged request from valid request** | Identity spoofing risk: critical infrastructure flaw |

**Do not treat an API returning 200 when sending a header directly via curl as proof that the system is secure.** That only proves the filter works; it also demonstrates the spoofing risk if the application port is directly exposed to end users.

### Behavior on Missing Header: Do Not Infer Statuses of Other Configs

With the default `exceptionIfHeaderMissing=true`, the filter throws `PreAuthenticatedCredentialsNotFoundException`. The actual HTTP status depends on filter ordering and the application's exception handling; do not claim every configuration automatically returns 401 or 403. The example intentionally set `false` and paired `authenticated()` with `Http403ForbiddenEntryPoint`, yielding a clear 403 path for unauthenticated requests.

Similarly, `setContinueFilterChainOnUnsuccessfulAuthentication(false)` causes the filter to rethrow `AuthenticationException` if the manager rejects; inspect exception handling according to the application's filter order rather than assuming every error automatically translates to 403. Keeping the default `true` in the example is **safe only** because no fallback login mechanism exists and every route requires Authentication.

## 6. Testing the Application with MockMvc

Add `src/test/java/com/example/demo/HeaderPreauthTests.java`. This is a **Spring Security layer test**, intentionally simulating requests *that have already passed through the gateway*; this test **does not verify the security of the real-world reverse proxy**.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HeaderPreauthTests {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedHeaderLoadsPrincipalAndRoles() throws Exception {
        mvc.perform(get("/api/me").header("X-Authenticated-User", "lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("lan"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"));
    }

    @Test
    void missingHeaderIsDenied() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownUserIsDenied() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Authenticated-User", "nonexistent"))
            .andExpect(status().isForbidden());
    }

    @Test
    void emptyHeaderIsDenied() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Authenticated-User", ""))
            .andExpect(status().isForbidden());
    }
}
```

**Test execution note:** the program requires `@SpringBootApplication` in a compatible package, the dependencies from section 3.1, and Spring Boot 3.x/Spring Security 6.x. Run with `./gradlew test --tests com.example.demo.HeaderPreauthTests` or the equivalent on Windows. There is no fixed stdout beyond the pass/fail test result of the corresponding Gradle environment.

There must be **separate gateway integration tests**, for example:

- Unauthenticated client sends an arbitrary header from the Internet → gateway blocks (cannot become `lan`/`admin`).
- Client authenticated as `lan` tries sending `X-Authenticated-User: admin` → backend sees only the gateway-verified username `lan`.
- Direct access to backend IP/port from public network or untrusted environment → blocked by network/ingress.
- Auth service times out/is down or returns no identity → no path bypasses SSO.
- Multiple header copies or encoding/casing variants → proxy normalizes and sends only one controlled identifier.
- Upstream user switch/logout/account revocation → authentication on subsequent requests updates accordingly; backend does not retain sessions against policy.

MockMvc only tests **processing after the header arrives**, not whether the identity in the header was spoofed between the client and the gateway.

## 7. Managing Identity, Authorities, and Sessions

### 7.1. Identity Header vs. Permission Header

`X-Authenticated-User: lan` only describes **who is accessing** according to upstream. It contains no `ROLE_ADMIN` rule. For example, `UserDetailsService` returns `ROLE_READER`, so the application can use:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasRole("READER")
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

This is a **replacement configuration snippet** for the authorization section of the sample above, not a standalone Java program. With `hasRole("READER")`, Spring Security looks for authority `ROLE_READER`. Never grant all roles to every forwarded username, and never treat client headers like `X-Role: ADMIN` as a trustworthy permission source.

If upstream passes groups/scopes via headers, read them only when infrastructure has authenticated, signed/bound the data properly, and prevented client tampering. For critical permissions, prefer the application's own policy/role store or an explicit claim-verification mechanism; standardize revocation and synchronization rules.

### 7.2. Stable Identifiers and Tenant Scope

`lan` could collide across organizations. If the gateway serves multiple IdPs/tenants, define the principal unambiguously—such as a stable ID guaranteed unique by upstream within the domain, or an `issuer + subject` pair. Never turn a free-form display username into a primary key for authorization. Enforce length limits, charset rules, Unicode normalization, case folding, and allowed identities in the system.

Even when a username is present in the header, user lookup must still verify the account is active, the tenant matches, and permissions remain valid. This is **user data/authorization processing**, not equivalent to re-verifying the upstream session.

### 7.3. Stateless vs. Sessions

The example uses `SessionCreationPolicy.STATELESS` so Authentication is not retained across multiple backend requests. Each request must be authenticated upstream and carry its identity. If the application instead stores `SecurityContext` in an HTTP session, `AbstractPreAuthenticatedProcessingFilter` may skip authentication once a principal exists; when the user switches accounts at SSO while the browser retains an old session, the application must intentionally design synchronization or session invalidation.

When sessions are required, consider `setCheckForPrincipalChanges(true)` and invalidation handling, along with login/logout, session fixation, CSRF, and identity revocation timing. Do not flip a single flag and assume all gateway logout, network race, or user-switch cases are solved.

## 8. Common Pitfalls

| Pitfall | Why It Is Wrong | Fix |
|---|---|---|
| Trusting any `X-Authenticated-User` from the Internet | Clients can set any name arbitrarily | Gateway authenticates, strips/overwrites header, blocks direct backend connections |
| Assuming sending header `admin` grants admin rights | A header is just a string | Separately managed user/authorities store and explicit rules |
| Thinking `PreAuthenticatedAuthenticationProvider` verifies JWT/passwords | Provider only loads `UserDetails` for a principal already deemed verified upstream | Verify tokens at gateway or use `JwtDecoder`/resource server if backend must verify |
| Treating `X-Forwarded-For` or a source IP as a "logged-in username" | Forwarding/IP does not prove an individual | Authenticate real identity before setting the header |
| Disabling `exceptionIfHeaderMissing` then setting `permitAll()` on all routes | Requests missing the header are allowed through | Require auth on protected routes and leave no unintended fallback open |
| Enabling HTTPS without stripping client-sent headers | TLS does not validate header contents | Require proxy to overwrite header from auth result |
| Reusing old session when upstream switches users | Principal might not be re-evaluated | Stateless mode or explicit principal-change/session-invalidation design |
| Logging all headers | Can leak identity, tokens/cookies, or PII | Structured logging keeping only necessary operational fields |
| Seeing MockMvc tests pass and skipping proxy tests | MockMvc has no real network/SSO infrastructure | End-to-end tests against header spoofing and direct backend access |

## 9. Production Readiness Checklist

1. Identify exactly **who authenticates upstream** (SSO proxy, auth service, IdP) and under what conditions the proxy sets the identity header.
2. Ensure **100% of backend access paths** traverse the proxy and cannot be reached directly from untrusted sources, including admin ports or secondary ingresses.
3. Have the gateway strip/overwrite `X-Authenticated-User` and all equivalent client-supplied headers; test duplicates, casing, and unusual request forms.
4. Secure the proxy → backend segment: network policy, TLS/mTLS if appropriate, restricting which upstreams may connect.
5. Accept only usernames with a uniform format, unique within the managed domain; reject empty values or uncontrolled special values.
6. Have the user service reject non-existent, disabled, locked, or cross-tenant accounts and never auto-grant permissions solely from a header.
7. Apply `SecurityFilterChain` to the right routes; guard all protected resources with `authenticated()` / `hasRole(...)`; verify no bypass exists via form/basic login.
8. Align cookies/sessions with the upstream identity lifecycle. For stateless APIs, never reuse a principal from a stale session.
9. Test both Java and network layers: missing header, invalid user, identity spoofing, duplicate headers, upstream failure, permission revocation, direct backend access.
10. Monitor pre-auth errors, user lookup failures, and 403s by correlation ID; never log secrets or expose internal details in HTTP responses.

## 10. Self-Check

**Question 1.** Does `RequestHeaderAuthenticationFilter` verify the user's password?  
**Answer:** No. It reads the principal from a header. Identity proof must occur in the upstream system; the provider typically only loads `UserDetails` and permissions.

**Question 2.** Why is `X-Authenticated-User: admin` untrustworthy when arriving over a direct Internet connection?  
**Answer:** Any client can craft that header itself. Direct backend access must be blocked and an authenticated proxy must strip/overwrite the header.

**Question 3.** Is `exceptionIfHeaderMissing=false` always a security bug?  
**Answer:** Not automatically, though it is safe only when requests missing an identity are still blocked at authorization and no fallback branch grants access. The example uses `anyRequest().authenticated()`, a 403 entry point, and no alternative login mechanism.

**Question 4.** Why does `UserDetailsByNameServiceWrapper` not replace an SSO gateway?  
**Answer:** It only uses the username in `Authentication` to look up `UserDetails` and authorities; it cannot tell whether upstream actually proved the identity.

**Question 5.** Under what circumstance can a backend request with a valid username and valid role still be dangerous?  
**Answer:** When the caller chose the header themselves or a direct path bypassed the gateway. Then the application "authenticates" an identity that was never proven.

## References

- [Spring Security 6.5 — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): pre-auth model and role of `RequestHeaderAuthenticationFilter`.
- [Spring Security — RequestHeaderAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.1.x/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): headers, `SM_USER` default, missing-header exception.
- [Spring Security 6.5 — AbstractPreAuthenticatedProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): `SecurityContext`, continue chain, principal change.
- [Spring Security — PreAuthenticatedAuthenticationProvider Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html): provider only loads user info, does not authenticate credentials itself.
- [Spring Security — UserDetailsByNameServiceWrapper Javadoc](https://docs.spring.io/spring-security/site/docs/6.0.2/api/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html): mapping name from `Authentication` to `UserDetails`.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): order and roles of security filters.
