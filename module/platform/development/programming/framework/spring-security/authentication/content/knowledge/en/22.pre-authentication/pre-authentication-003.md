# PreAuthenticatedAuthenticationProvider and Loading Application Permissions

In **pre-authentication**, a trusted system external to the application has already verified the user's identity. When a request reaches the Spring Security application, the primary question is no longer "is the password correct?" but rather: **is this identity trustworthy, who is the corresponding user in the application, and what are they permitted to do?** `PreAuthenticatedAuthenticationProvider` is a component that handles **loading user information and application permissions** after the external identity has been authenticated.

This lesson focuses on the pre-authentication flow for **Spring Security Servlet**, specifically the roles of `PreAuthenticatedAuthenticationToken`, `PreAuthenticatedAuthenticationProvider`, `AuthenticationUserDetailsService`, `UserDetailsService`, and `GrantedAuthority`. The illustrative examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x; the upstream identity-receiving mechanism must be implemented and protected separately.

## 1. Problem Statement: External Identity, Internal Permissions

Suppose a company uses a central login system (an SSO reverse proxy, servlet container authentication, or a trusted gateway). After logging in there, requests arriving at the application carry a normalized identity, such as `linh`.

The application has its own rules:

- `linh` can view reports and view profiles;
- `minh` can administer reports;
- someone who exists in the SSO system **does not necessarily** have an account or permissions in this application.

Separating the two responsibilities:

| Task to Perform | Primary Owner |
| --- | --- |
| Verify password, certificate, MFA, or initial login session | External authentication system |
| Ensure the identity passed to the application is not spoofed | Network/trust-boundary infrastructure and integration mechanism |
| Convert verified identity into a Spring Security `Authentication` | Pre-authentication filter + authentication provider |
| Look up local user, status, roles, and business permissions | `AuthenticationUserDetailsService`/`UserDetailsService` and application data store |
| Allow or deny endpoint access | Authorization mechanism, e.g., `hasAuthority`/`hasRole` |

**Successful identity verification does not automatically imply granting all permissions.** If the application only accepts a username without loading proper permissions, endpoints may be denied or, worse, granted broader access than intended. Spring Security does not infer `ROLE_ADMIN` just because an identity came from SSO.

### Terms to Distinguish

- **Principal:** the identity verified upstream, usually a username, normalized email, or stable subject ID.
- **Credentials:** an object/marker used inside the pre-authentication token. It is not a password to be verified again; many filters use a placeholder value such as `N/A`.
- **Authentication:** the object holding the principal, credentials, authentication status, and set of `GrantedAuthority` items.
- **GrantedAuthority:** a specific permission read by Spring Security during access checks, such as `REPORT_READ` or `ROLE_ADMIN`.
- **UserDetails:** user information loaded by the application itself, potentially including username, account status, and authorities.

Do not equate "externally authenticated" with "authorized inside the app."

## 2. Processing Flow from Request to Application Permissions

Logical diagram:

~~~text
User
  │ logs in via upstream/SSO
  ▼
External authentication system
  │ forwards protected identity: "linh"
  ▼
Application: AbstractPreAuthenticatedProcessingFilter
  │ creates PreAuthenticatedAuthenticationToken
  │ principal="linh", credentials="N/A"
  ▼
AuthenticationManager (typically ProviderManager)
  │ selects AuthenticationProvider supporting the token type
  ▼
PreAuthenticatedAuthenticationProvider
  │ delegates loadUserDetails(token)
  ▼
AuthenticationUserDetailsService
  │ looks up user/roles from application data
  ▼
UserDetails(username="linh", authorities=[REPORT_READ, PROFILE_VIEW])
  │ returns result
  ▼
Authenticated Authentication + GrantedAuthority
  │ stored in SecurityContext
  ▼
Authorization: hasAuthority("REPORT_READ")
  ├── permitted  → allow
  └── missing permission → 403 Forbidden
~~~

Key steps:

1. **Ensure requests genuinely pass through a trusted authentication layer.** This prerequisite lies outside the provider's scope.
2. **The filter extracts the principal.** For example, `J2eePreAuthenticatedProcessingFilter` reads the name from `HttpServletRequest.getUserPrincipal()` authenticated by the servlet container. Another filter might read from a request attribute or a gateway-controlled header.
3. **The filter builds an unauthenticated token** of the form `PreAuthenticatedAuthenticationToken(principal, credentials)` and passes it to `AuthenticationManager`.
4. **`ProviderManager` selects `PreAuthenticatedAuthenticationProvider`**, because this provider supports `PreAuthenticatedAuthenticationToken`.
5. **The provider calls `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`** to load the corresponding `UserDetails`. The application can check account status and policies during this step.
6. **The provider creates an authenticated result** with the identity and authorities from user details; the filter stores the result into `SecurityContext`.
7. **The authorization step enforces loaded permissions.** Rules like `authenticated()`, `hasAuthority(...)`, and `hasRole(...)` evaluate that result.

A valid pre-authentication request can still be rejected if the application account does not exist, is locked, or lacks permissions. This is the desired behavior when the business rule is "only internally provisioned users may enter."

## 3. What Does PreAuthenticatedAuthenticationProvider Actually Do?

`PreAuthenticatedAuthenticationProvider` is an `AuthenticationProvider` for the `PreAuthenticatedAuthenticationToken` token type. Its core behavior **differs** from `DaoAuthenticationProvider`:

| Criterion | `PreAuthenticatedAuthenticationProvider` | `DaoAuthenticationProvider` |
| --- | --- | --- |
| Scenario | Identity already verified by an external system | Username/password login inside the app |
| Typical input token | `PreAuthenticatedAuthenticationToken` | `UsernamePasswordAuthenticationToken` |
| Verifies user password | **No** | Typically checks via `PasswordEncoder` |
| Loads user/authority | Via `AuthenticationUserDetailsService` | Via `UserDetailsService` |
| Source of identity assurance | Upstream system, filter, and trust boundary | Credential proof verified by the provider |
| Result | `Authentication` containing principal and app permissions | `Authentication` containing principal and permissions after credential check |

The provider does not verify SSO signatures, call the IdP to re-check sessions, validate request headers, or turn arbitrary usernames into trusted identities. If an untrusted component creates `PreAuthenticatedAuthenticationToken("admin", "N/A")` and sends it to the provider, the provider may load admin permissions. **Controlling token creation sources is therefore a mandatory security requirement.**

### Configuration Properties

- `setPreAuthenticatedUserDetailsService(...)`: required to supply a way to load `UserDetails` from the token; without it, the provider is insufficiently configured to operate.
- `setThrowExceptionWhenTokenRejected(true)`: when the token lacks principal or credentials, the provider throws `BadCredentialsException` instead of passing so another provider can try. This is an important setting in a pre-auth-only model.
- `setUserDetailsChecker(...)`: customizes how `UserDetails` status is checked after loading; by default a checker inspects common account status flags. Do not bypass locked/disabled checks.
- `supports(PreAuthenticatedAuthenticationToken.class)`: the provider identifies the token type it supports; this does not validate principal trustworthiness.

An `AuthenticationManager` can contain multiple providers. If combining pre-auth with form login or HTTP Basic, clearly design entry points, filter order, fallback behavior, and paths that must not bypass SSO. The model below intentionally focuses on pre-auth.

### Why Can Credentials Be "N/A"?

Filters such as `J2eePreAuthenticatedProcessingFilter` have no original password to pass to the provider and use a dummy value instead. This makes sense: upstream already verified the proof; the provider only loads user and authorities. However, the credentials object generally **must not be null** on a valid request because the provider may treat the token as invalid. Never treat the `N/A` value as a password with security meaning.

## 4. Loading Permissions from Application Data

Two common approaches:

### 4.1. UserDetailsByNameServiceWrapper — Using Local Permissions

Spring Security provides `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>`. The wrapper takes the token, extracts the principal name, and invokes a standard `UserDetailsService`:

~~~text
PreAuthenticatedAuthenticationToken("linh", "N/A")
            │
            ▼
UserDetailsByNameServiceWrapper
            │ loadUserByUsername("linh")
            ▼
UserDetailsService ── application repository
            │
            ▼
UserDetails(username="linh", authorities=[REPORT_READ])
~~~

Advantage: existing repositories and permission-mapping policies can be reused. Example business table:

| user_id | external_subject | enabled | application_permission |
| --- | --- | --- | --- |
| 17 | `linh` | `true` | `REPORT_READ` |
| 17 | `linh` | `true` | `PROFILE_VIEW` |
| 28 | `minh` | `true` | `REPORT_ADMIN` |

The permissions in this table are **application data**, not authentication proof. In production, `UserDetailsService` must look up the user by verified key, check account status, and map permissions to `GrantedAuthority`. If upstream uses a durable subject ID instead of a mutable username, the integration layer should map that ID to the internal account by explicit rules.

For users without application permissions, throw `UsernameNotFoundException` or return a disabled user so the system denies access per policy; **never grant a broad default role** or auto-create privileged accounts.

### 4.2. PreAuthenticatedGrantedAuthoritiesUserDetailsService — Permissions Passed by Upstream

`PreAuthenticatedGrantedAuthoritiesUserDetailsService` extracts authorities from `token.getDetails()` **when details implement `GrantedAuthoritiesContainer`**. Unlike loading from a repository, the primary source of authorities is data attached to the request token rather than an application permission table.

~~~text
Trusted upstream roles
    → pre-auth filter/details source
    → token.details implements GrantedAuthoritiesContainer
    → PreAuthenticatedGrantedAuthoritiesUserDetailsService
    → UserDetails + authorities
~~~

If details are only an ordinary `WebAuthenticationDetails`, which does not implement `GrantedAuthoritiesContainer` as required by the API, you cannot assume the provider will read roles from it. You can use `PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails` or a suitable details source to supply the data, but only when **the role source is protected and mapped transparently**. Directly accepting a client-supplied `X-Role: ADMIN` header is unsafe.

**Which to choose?** If the application owns authorization decisions, prefer the wrapper + `UserDetailsService` backed by the app's data store. If upstream roles are centrally governed and the application has a specific trust contract, you may read permissions from pre-auth details while still validating role names, tenant, expiration, and permission status. Do not merge both sources via default additive union without precedence and revocation rules.

## 5. Java Configuration Example: Container Authenticates, Application Loads Permissions

This example uses **Spring Security Servlet**. It assumes the container/deployment architecture has already authenticated the request, so `request.getUserPrincipal()` contains the container-issued identity. If run standalone on an embedded Spring Boot server without container authentication configured, the principal may be `null` and all protected routes will be blocked. The example **does not provide an SSO login screen itself**.

### 5.1. Dependencies

In a Spring Boot 3.x application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The application requires the Spring Boot plugin, dependency management, and an appropriate Java toolchain managed by the project. `spring-boot-starter-security` provides Spring Security for servlet web and `PreAuthenticatedAuthenticationProvider`; no separate "preauth provider" library is needed.

### 5.2. Configuration Class

File `src/main/java/example/preauth/PreAuthSecurityConfig.java`:

~~~java
package example.preauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
public class PreAuthSecurityConfig {

    @Bean
    UserDetailsService applicationUserDetailsService() {
        // Illustrative data. Production: replace with application permission repository.
        return username -> {
            if ("linh".equals(username)) {
                return User.withUsername(username)
                        .password("{noop}not-used")
                        .authorities("REPORT_READ", "PROFILE_VIEW")
                        .build();
            }
            if ("minh".equals(username)) {
                return User.withUsername(username)
                        .password("{noop}not-used")
                        .authorities("REPORT_ADMIN")
                        .build();
            }
            throw new UsernameNotFoundException("No application account");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService applicationUserDetailsService)
            throws Exception {

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<>(
                        applicationUserDetailsService));
        provider.setThrowExceptionWhenTokenRejected(true);

        AuthenticationManager preAuthManager = new ProviderManager(provider);

        J2eePreAuthenticatedProcessingFilter preAuthFilter =
                new J2eePreAuthenticatedProcessingFilter();
        preAuthFilter.setAuthenticationManager(preAuthManager);

        // Re-check identity on each request; do not store in session.
        NullSecurityContextRepository contextRepository =
                new NullSecurityContextRepository();
        preAuthFilter.setSecurityContextRepository(contextRepository);
        http.securityContext(context -> context
                .securityContextRepository(contextRepository));
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Register the filter only inside SecurityFilterChain.
        http.addFilterBefore(preAuthFilter,
                UsernamePasswordAuthenticationFilter.class);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
                .requestMatchers("/manage/**").hasAuthority("REPORT_ADMIN")
                .anyRequest().authenticated());
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint(new Http403ForbiddenEntryPoint()));

        return http.build();
    }
}
~~~

**Explanation by responsibility layer:**

1. `applicationUserDetailsService()` maps a verified principal to an account + list of business permissions. The two users in the example merely simulate a repository. `password("{noop}not-used")` is a required placeholder value on `UserDetails` in this example and **is not used to authenticate passwords**.
2. `UserDetailsByNameServiceWrapper` adapts `UserDetailsService` to the `AuthenticationUserDetailsService` required by `PreAuthenticatedAuthenticationProvider`.
3. `ProviderManager(provider)` contains only the pre-auth provider. This application does not enable form login or Basic as an alternative access path.
4. `J2eePreAuthenticatedProcessingFilter` reads `HttpServletRequest.getUserPrincipal()` from the servlet container. The filter does not verify passwords or SSO tokens itself. The principal name exposed by the container must be established by a trusted authentication layer.
5. `NullSecurityContextRepository` and `SessionCreationPolicy.STATELESS` cause the example to re-verify identity and load authorities per request instead of maintaining an application login session. Data lookup cost increases; add caching with an appropriate eviction policy for high traffic.
6. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the filter in the authentication phase of the Security Filter Chain. Because the filter is created solely as a local variable inside the configuration, the example avoids accidentally registering the same filter twice via Spring Boot's servlet auto-registration.
7. `hasAuthority("REPORT_READ")` checks the exact authority string. `hasAuthority("REPORT_ADMIN")` works the same way without prepending `ROLE_`. Having only `REPORT_ADMIN` without `REPORT_READ` means `minh` **is not automatically allowed to view `/reports/**`** under this configuration.
8. `Http403ForbiddenEntryPoint` returns 403 when an unauthenticated request accesses a protected resource; when authenticated but lacking an authority, Spring Security also blocks with 403. Test explicitly if the system needs to distinguish 401 from 403.

**Limitation of the example:** no container authentication mechanism is configured in the code above. Running standalone on a default embedded Tomcat, a request like `curl http://localhost:8080/reports/summary` **does not prove pre-auth succeeded**, because no container principal exists and no controller is defined. To run end-to-end, integrate real SSO/container authentication or build a test harness simulating the principal at the trust boundary.

### 5.3. Loading Permissions from a Database Instead of Hard-Coding

In a real application, the core of `UserDetailsService` might look like this; this is **Java pseudocode using application-defined repository APIs**, not a standalone runnable class:

~~~java
return verifiedSubject -> {
    ApplicationAccount account = accountRepository
            .findByExternalSubject(verifiedSubject)
            .orElseThrow(() ->
                    new UsernameNotFoundException("No application account"));

    if (!account.isEnabled()) {
        throw new DisabledException("Application account disabled");
    }

    var authorities = permissionRepository
            .findPermissionCodesByAccountId(account.getId())
            .stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

    return User.withUsername(account.getExternalSubject())
            .password("{noop}not-used")
            .authorities(authorities)
            .build();
};
~~~

Classes `ApplicationAccount`, `accountRepository`, `permissionRepository`, and imports `DisabledException`/`SimpleGrantedAuthority` are provided by the project. In practice, handle deleted users, expired permissions, tenants, duplicate records, and consistent caching. When implementing `UserDetailsService`, never infer permissions from the username such as `username.startsWith("admin")`.

To avoid misattributing accounts, the lookup identifier must be agreed upon with upstream and unique within the relevant domain. Emails can change or collide across tenants; when SSO provides a stable subject ID, you can combine `issuer + subject` as the identifier rather than relying only on a display name.

## 6. Testing Provider Logic Directly with JUnit

Because upstream authentication depends on infrastructure, you can independently test the **application permission-loading** logic with unit tests: construct a simulated post-verification pre-auth token, invoke the provider, and assert the returned authorities. This test verifies provider/role mapping; it **does not replace** upstream trust-boundary security tests.

File `src/test/java/example/preauth/PreAuthProviderTest.java`:

~~~java
package example.preauth;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class PreAuthProviderTest {

    private PreAuthenticatedAuthenticationProvider provider() {
        UserDetailsService userStore = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not registered in app");
            }
            return User.withUsername(username)
                    .password("{noop}not-used")
                    .authorities("REPORT_READ", "PROFILE_VIEW")
                    .build();
        };

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<>(userStore));
        provider.setThrowExceptionWhenTokenRejected(true);
        return provider;
    }

    @Test
    void existingApplicationUserReceivesApplicationPermissions() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("linh", "N/A");

        Authentication result = provider().authenticate(token);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("linh", result.getName());
        Set<String> actual = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
        assertEquals(Set.of("REPORT_READ", "PROFILE_VIEW"), actual);
    }

    @Test
    void unknownApplicationUserIsRejected() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("stranger", "N/A");

        assertThrows(UsernameNotFoundException.class,
                () -> provider().authenticate(token));
    }

    @Test
    void missingCredentialsIsRejected() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("linh", null);

        assertThrows(BadCredentialsException.class,
                () -> provider().authenticate(token));
    }
}
~~~

Run in a Spring Boot Gradle project with JUnit Platform:

~~~bash
./gradlew test --tests example.preauth.PreAuthProviderTest
~~~

On Windows use `gradlew.bat test --tests example.preauth.PreAuthProviderTest`. When successful, Gradle reports `BUILD SUCCESSFUL`; the exact line count and log output depend on Gradle/project settings, so no fixed stdout is claimed. The three tests verify: a valid user receives two permissions, a user without an application account is rejected, and a token missing credentials is rejected when `throwExceptionWhenTokenRejected` is set.

**Testing limitation:** anyone in the same process can construct token `("linh", "N/A")`. The test does so intentionally to isolate provider logic. Do not infer from this that requests from the Internet passed through SSO.

## 7. hasAuthority, hasRole, and Permission Scope

In Spring Security, an authority is a string; `hasAuthority("REPORT_READ")` checks for an authority with that exact name. Meanwhile, `hasRole("ADMIN")` by default checks for an authority with the `ROLE_ADMIN` prefix.

Example:

| Authorities in `Authentication` | Rule | Result |
| --- | --- | --- |
| `REPORT_READ`, `PROFILE_VIEW` | `hasAuthority("REPORT_READ")` | Allowed |
| `REPORT_READ` | `hasRole("ADMIN")` | Denied, lacks `ROLE_ADMIN` |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| `REPORT_ADMIN` | `hasAuthority("REPORT_READ")` | Denied unless `REPORT_READ` is also present |
| No authorities | `authenticated()` | Allowed if principal is authenticated, though granular rules will still deny |

An authenticated account missing `REPORT_READ` must receive 403 when accessing a resource requiring `REPORT_READ`. If `@PreAuthorize("hasAuthority('REPORT_READ')")` is used at the method layer, `@EnableMethodSecurity` must be enabled; URL configuration and method security are two separate enforcement points.

Avoid using all IdP groups directly as roles without normalization. For example, an IdP group `finance-team` can be mapped to application permission `INVOICE_READ` under an owner-defined policy, rather than granting `ROLE_ADMIN` by default.

## 8. Secure Integration Scenarios with an SSO Gateway

Pre-auth relies on the assumption that **the caller of the application cannot choose its own trusted identity**. This is the easiest part to get wrong in real-world integrations.

### Receiving Username via HTTP Header

`RequestHeaderAuthenticationFilter` can read a header such as `SM_USER` or `X-Verified-User`. It **only reads the header and does not itself verify signatures, passwords, or sessions**. If a direct request sends:

~~~http
GET /manage/overview HTTP/1.1
Host: app.example.org
X-Verified-User: minh
~~~

then the filter can treat `minh` as the principal if no external protection layer exists. Therefore, never use client-supplied headers to construct a pre-auth token. When using a trusted gateway, you must:

1. Block all direct access paths from clients to the backend application; allow traffic only through the gateway or controlled network/identity paths.
2. Have the gateway strip all client-sent identity headers before setting the header from a verified session/token.
3. Protect the gateway → application connection with TLS/mTLS or equivalent network controls according to the threat model.
4. Clearly define identity format, issuer, tenant, and anti-duplication/anti-spoofing rules.
5. Test requests with no identity, spoofed headers, gateway-bypass requests, logged-out upstream sessions, and revoked users.

You can use a mechanism based on `HttpServletRequest.getUserPrincipal()` if the servlet container genuinely guarantees principal authenticity; do not treat an arbitrary request attribute as secure proof merely because an in-app component assigned it.

### Sessions, Caching, and Permission Changes

If permissions are loaded from a database on every request as in the stateless example configuration, permission changes can take effect on the next request (depending on caching). When using `HttpSessionSecurityContextRepository` or caching `UserDetails`, stale permissions may persist until the session/cache expires or is invalidated. You must explicitly design:

- when permission grant/revocation changes take effect;
- the ability to lock an account immediately even after SSO login;
- checks for principal changes across requests, especially when sharing a browser/session;
- TTL policies, session invalidation, cache eviction, and authoritative data sources.

`AbstractPreAuthenticatedProcessingFilter` offers `setCheckForPrincipalChanges(true)` to detect principal changes against an existing `Authentication`; this does not automatically solve cases where database permissions change while the principal remains the same. Do not treat a Spring Security session as a substitute for IdP session lifetimes and status checks.

## 9. Common Errors and Troubleshooting

| Symptom | Possible Cause | Check / Resolution |
| --- | --- | --- |
| Always 403 before reaching application | Servlet container did not supply principal; request bypassed SSO | Verify `getUserPrincipal()` at ingress boundary, upstream setup, entry point config |
| Valid principal but `UsernameNotFoundException` | Missing app user mapping, username format mismatch, or tenant mismatch | Check subject→account mapping, normalization, active status |
| App recognizes user but lacks roles | `UserDetailsService` returned no authorities, wrong mapping, or stale cache | Inspect `result.getAuthorities()` in tests/safe logs, DB permissions, and cache policy |
| `hasRole("ADMIN")` always denies | DB returns `ADMIN`/`REPORT_ADMIN` while rule expects `ROLE_ADMIN` | Normalize prefixes or use exact `hasAuthority` |
| Provider ignores request | Token is not `PreAuthenticatedAuthenticationToken` or manager lacks provider | Check token class, `supports`, and `ProviderManager` wiring |
| Provider fails due to null principal/credentials | Filter failed to extract identity or returned null credentials | Fix trusted identity source; for valid pre-auth use a non-null credentials marker |
| Calls bypassing SSO still succeed | Backend directly reachable or proxy fails to strip spoofed headers | Lock down backend, enforce trusted ingress, write header-spoofing tests |
| Revoked permissions still accepted | Session/cache retains old authorities | Check `SecurityContextRepository`, TTL, invalidation/reload |
| Disabled account still works | User source did not update status or custom checker is wrong | Ensure account status is loaded and checked before granting authentication |

Troubleshoot in order: **did upstream authenticate and protect the identity → did the filter extract the principal → is the token the right type/non-null → did the provider call the user details service → did the app return the right authorities → which authority is the authorization rule checking**. In production, never log raw tokens, cookies, credentials, or secret headers; log only controlled events and error codes.

## 10. Self-Check Knowledge Questions

1. Why can `PreAuthenticatedAuthenticationProvider` not replace IdP session/signature verification?
2. In a pre-auth flow, why might a user already logged into SSO still be unable to access `/reports/**`?
3. When should you use `UserDetailsByNameServiceWrapper`, and when `PreAuthenticatedGrantedAuthoritiesUserDetailsService`?
4. If a user has `REPORT_ADMIN` but an endpoint requires `REPORT_READ`, will access succeed? Why?
5. The provider receives a token with principal `linh` and credentials `N/A`. Does the value `N/A` prove the user is `linh`?
6. Name two reasons why revoked permissions might still remain active on the next request.

**Suggested answers:** (1) The provider trusts proof already verified by an external layer; (2) the app has not provisioned/loaded the user or permissions; (3) permissions from app DB versus authorities supplied by upstream via valid details; (4) no, because `hasAuthority` matches the exact string name; (5) no, the dummy value merely satisfies token structure; (6) stale session/cache and lack of reload/eviction policy.

## 11. Pre-Production Checklist

- [ ] Explicit trust contract established with the upstream system, covering principal, issuer/tenant, and anti-spoofing measures.
- [ ] Clients cannot access the backend bypassing the gateway or fabricate trusted principals/headers.
- [ ] Filter constructs `PreAuthenticatedAuthenticationToken` solely from verified identities.
- [ ] Provider is wired into the right `AuthenticationManager` and loads `UserDetails` from the intended permission source.
- [ ] Missing/disabled/locked users are rejected; no broad default roles are auto-granted.
- [ ] Application permissions are normalized, with tests verifying `hasAuthority`/`hasRole` prefixes.
- [ ] Plan in place for permission revocation, session/cache invalidation, and principal changes.
- [ ] Integration tests cover missing identity, spoofed headers, unauthorized users, and authorized users.
- [ ] Logging is sufficient for diagnostics without recording credentials or sensitive data.

## 12. References

- [Spring Security Reference: Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html)
- [PreAuthenticatedAuthenticationProvider API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [AbstractPreAuthenticatedProcessingFilter API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html)
- [J2eePreAuthenticatedProcessingFilter API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html)
- [UserDetailsByNameServiceWrapper API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html)
- [PreAuthenticatedGrantedAuthoritiesUserDetailsService API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html)
