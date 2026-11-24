# Distinguishing Authentication, Authorization, and Account Lifecycle Management

When designing a login system, three responsibilities often appear in the same flow yet answer three different questions:

- **Authentication:** Who is sending the request and what evidence allows trusting that identity?
- **Authorization:** Is the authenticated identity allowed to perform this action on a specific resource?
- **Account lifecycle management:** Under what policies are accounts created, activated, modified, locked, recovered, and terminated?

Within Spring Security, understanding this boundary helps avoid the "logged in means allowed to do everything" mistake, avoid mixing account management into security filters, and know how to invalidate sessions or tokens when an account changes state.

## 1. Comparing the Three Responsibilities

| Aspect | Authentication (AuthN) | Authorization (AuthZ) | Account lifecycle |
|---|---|---|---|
| Primary question | "Who are you?" | "What are you allowed to do, and on what?" | "Is this account currently valid and governed in the right state?" |
| Typical inputs | Username, password, MFA, certificate, session cookie, bearer token | Authenticated principal, authorities/roles, resource, action, owner, and context | Account profile, verification email, state, security history, change/lock/delete requests |
| Outcome | Establishes or rejects an identity for the request/session | Permits or denies an operation | Transitions state, updates profile/credentials, revokes access per policy |
| Timing | At login or when verifying credentials/tokens on each request | Every time a protected feature/resource is accessed | Before, during, and after the account's lifetime |
| Typical responsibility in Spring | `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext` | `AuthorizationManager`, `authorizeHttpRequests`, `@PreAuthorize` | Service/domain, account repository, verification/recovery workflows; integrates with Spring Security mechanisms |
| Failure example | Wrong password, expired token | Logged in but missing authority to read orders | Unverified account, suspended account, or sessions needing revocation after offboarding |

**Core point:** Successful authentication does **not** imply permission to access every resource. An account still existing in the database does **not** imply permission to log in. Locking an account does **not** automatically guarantee that every previously issued access token immediately becomes invalid.

Online store example: Linh enters the correct password and MFA to log in (AuthN); Linh can view orders belonging to her but cannot edit another customer's order (AuthZ); when Linh changes her password or has her account suspended, the system must execute the credential-change workflow, revoke sessions/tokens, and record the event (lifecycle).

## 2. Authentication: Establishing a Trusted Identity

### 2.1. Identity, Credentials, and Sessions Are Distinct Objects

- **Identity/principal** is the subject the system recognizes, such as an internal user ID, username, or service account ID. You should not take a client-sent `userId` parameter as proof of identity.
- **Credential** is the evidence used to authenticate: password, MFA code/device, private key, signed token, or session credential. A password is one kind of credential, not the entirety of authentication.
- **Authentication result** contains the principal and relevant security data after the authentication mechanism verifies the evidence. A request authenticated with a valid token did not necessarily just go through a login screen.
- **Session/token** helps persist or carry authentication state across requests. They have lifespans and revocation policies separate from the account profile's state.

The three authentication factors are commonly categorized as "something you know" (password/PIN), "something you have" (device, security key), and "something you are" (biometrics). MFA combines independent factors to reduce the risk of stolen credentials. A verified email is proof of mailbox control at the time of verification; it does not automatically prove a person's legal identity.

### 2.2. How Does Spring Security Represent Authentication?

Conceptually, a request passes through `SecurityFilterChain`. Depending on the login method, a mechanism such as HTTP Basic, form login, or OAuth2 Resource Server reads the evidence. `AuthenticationManager` delegates to an appropriate `AuthenticationProvider`; if successful, `Authentication` is attached to the request's `SecurityContext` for use by the authorization step and application code.

~~~text
HTTP request
  -> SecurityFilterChain
  -> Appropriate authentication mechanism (Basic / form / bearer ...)
  -> Verify credential, token, signature, expiration, and related policies
  -> Authentication / SecurityContext (principal, authorities)
  -> URL or method authorization check
  -> Controller / Service if permitted
~~~

This is a conceptual diagram: the actual filters and order depend on configuration. With internal username/password, `UserDetailsService` may load the account, `PasswordEncoder` checks the password hash, and the provider checks states such as enabled/locked/expired. With a bearer JWT, the application may verify signature, issuer, audience, and expiration and convert claims into authorities; it does not necessarily call `UserDetailsService` on every request.

**Note on anonymous users:** Spring Security may place an `AnonymousAuthenticationToken` in the context even when the user has not logged in. Therefore, merely checking `SecurityContextHolder.getContext().getAuthentication() != null` or calling `isAuthenticated()` on an arbitrary token is not sufficient criteria to conclude a real user is present. Use Spring Security's `authenticated()`/`permitAll()` rules or an appropriate anonymous-detection mechanism.

### 2.3. Protecting Credentials

Passwords must be stored as salted one-way hashes using a suitable algorithm such as bcrypt, scrypt, or Argon2 via `PasswordEncoder`; never store plaintext or use fast hashes like plain SHA-256 for password storage. Rate-limit login attempts, enforce appropriate MFA policies, protect the transport channel with HTTPS, and never log raw passwords or tokens. HTTP Basic in the example below is for illustration only; it must be used over HTTPS and is not a complete login design for production.

When authenticating via an Identity Provider (IdP), the application must still verify the token/response according to the protocol; receiving a "logged in" string from the frontend is not authentication.

## 3. Authorization: Deciding Whether an Action Is Permitted

Suppose a request has been authenticated as principal `reader`. When handling `GET /orders/42`, the system needs to answer at least three questions: does the principal have permission to read orders, is order 42 within the accessible scope, and are there additional rules (tenant, order status, time, organizational policy)?

Several ways to represent permissions:

| Approach | Idea | Example |
|---|---|---|
| Role-based (RBAC) | Assign responsibility groups, mapped to authorities | `ROLE_ADMIN`, `ROLE_SUPPORT` |
| Permission/authority | Action/feature-level permissions | `orders:read`, `orders:refund` |
| Object/attribute-based | Consider the resource and request context | Only the order owner or authorized support agent can view the order |
| Tenant/scope-based | Restrict data within an organization/token scope | Tenant A staff cannot read tenant B data |

In Spring Security, `GrantedAuthority` is the data representation commonly used for permission checks. `hasAuthority("orders:read")` matches the authority string exactly. `hasRole("ADMIN")` by default convention looks for the authority `ROLE_ADMIN` (with the `ROLE_` prefix). Roles are a way to group permissions; a role by itself does not solve "who owns this order".

Rules can be placed at two complementary layers:

1. **HTTP layer:** `authorizeHttpRequests` protects URL groups, blocking unauthenticated callers or those lacking coarse-grained permissions.
2. **Method/business layer:** `@PreAuthorize` or checks inside services protect actual operations and specific objects. If an API has `GET /orders/{id}`, checking only `orders:read` is not enough to prevent IDOR: you must also verify that the caller is allowed to access that specific order `id`.

Do not rely on showing/hiding UI buttons, having the client send `role=admin`, or previously filtered lists as a substitute for server-side authorization. A resource can be called via a direct URL, another API, or a background job. Apply "deny by default" for undefined paths and "least privilege" for granted permissions.

### 3.1. Distinguishing HTTP 401 and 403

| Scenario | Typical REST API response |
|---|---|
| No valid credentials for a resource requiring authentication | **401 Unauthorized**: authentication or re-authentication required |
| Authenticated but insufficient permissions | **403 Forbidden**: not allowed to perform the operation |
| Endpoint allowing public access | **200** or business-appropriate status code |
| Do not want to reveal whether a resource exists to unauthorized callers | May use **404** per anti-enumeration policy |

These codes depend on how `AuthenticationEntryPoint`, `AccessDeniedHandler`, and the application type are configured. With form login on the web, unauthenticated users typically get a **302 redirect** to the login page instead of a direct 401. "Unauthorized" in the name of code 401 does not mean authorization failed; in terms of HTTP flow, this is the case where valid authentication information is required.

## 4. Account Lifecycle Management: Policies Across the Usage Lifetime

Authentication and authorization process a single request; the account lifecycle manages the existence and state of a principal over time. Systems often have states and transitions like the following, though this is a **business design example**, not a mandatory Spring Security enum:

| State | Meaning | Common rules |
|---|---|---|
| `PENDING_VERIFICATION` | Registered/invited, awaiting verification | Normal access not yet granted; verification token is short-lived and single-use |
| `ACTIVE` | Activation conditions completed | Can authenticate; must still be authorized on each request |
| `LOCKED` | Temporarily locked due to risk or repeated wrong passwords | Reject new logins; unlock only after predetermined verification/workflow |
| `SUSPENDED` | Suspended by an administrator or policy | Block usage, revoke sessions/tokens according to risk level |
| `CLOSED` / `DELETED` | No longer in use | Disable access, handle data and auditing per retention policy |

A complete workflow typically includes:

1. **Creation/invitation:** Check duplicate identity, input data, invitation eligibility, and permission to grant accounts. Do not grant privileged roles just because the client asks.
2. **Verification/activation:** Verify email or an appropriate possession method; activation tokens have an expiration and single use; state transitions validate eligibility.
3. **Usage:** Login, MFA, profile updates, password changes, adding/removing devices, adjusting roles and permissions under proper authority.
4. **Recovery:** Forgotten password/MFA or suspected account takeover. Require expiring recovery tokens, attempt limits, verification of the rightful subject, and invalidation of old credentials/sessions per policy.
5. **Locking/suspension:** Block new authentication, consider revoking access tokens, refresh tokens, sessions, and related service access rights; log the administrative event.
6. **Closing/deletion:** Revoke roles/permissions, tokens, API keys, and third-party connections; execute deletion/anonymization or data retention per policy and applicable law.

**Account state differs from session state.** Setting an account to `SUSPENDED` does not automatically destroy a session cookie stored on the server. A self-contained JWT that is valid in signature and expiration may still be accepted by a resource server if the server only validates the token and does not check current state or a revocation mechanism. Therefore, the locking workflow must specify when and how existing access is blocked.

Examples of technical options: server-side sessions can be deleted/invalidated; refresh tokens can be revoked at the issuing store; access tokens can be short-lived, or use introspection or a revocation list when immediate reaction is needed; credential changes sometimes require incrementing a "security version" and checking sessions/tokens against that version. Each option has its own cost, synchronization latency, and trade-offs.

### 4.1. What Spring Security Supports vs. What the Application Must Build

In the username/password model using `UserDetails`, the properties `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()` help reject authentication when an appropriate provider checks state. This is useful for blocking **new login attempts**. However, Spring Security does not design your account table, registration flow, verification emails, password reset, permission approval, state history, or data deletion rules.

The application typically needs an `AccountService`, data store, consistent transactions, auditing, token issuance/revocation mechanisms, or session management. With OAuth2/OIDC, the IdP may hold many lifecycle responsibilities, but the resource server remains responsible for validating incoming tokens and enforcing permissions on the resources it manages. Do not assume that locking a user in the IdP will instantly reject every previously issued access token.

Distinguish **lockout from repeated failed logins** from **business suspension**: the reason, who has authority to act, duration, reopening workflow, and degree of access revocation can differ greatly.

## 5. Typical Flow from Registration to Access and Suspension

Suppose an application has endpoints `POST /accounts`, `POST /auth/login`, and `GET /orders/{id}`:

1. A user registers. `AccountService` creates a `PENDING_VERIFICATION` record and sends a verification link with a single-use token.
2. After valid verification, the account transitions to `ACTIVE`. No order-reading request is allowed merely because the account is active.
3. The user logs in. The AuthN mechanism checks credentials, MFA where applicable, and account state; the authentication result establishes the principal.
4. The user calls `GET /orders/42`. AuthN processes the cookie/token on the request. AuthZ checks the `orders:read` authority, tenant, and owner of order 42. Only when all conditions hold does the controller/service return data.
5. An administrator suspends the account. The account service records `SUSPENDED`, audits the action, revokes sessions/refresh tokens, and enforces the policy for non-expired access tokens.
6. Requests after suspension are rejected per policy. Both new logins **and** sessions/tokens issued prior to suspension must be tested.

In this design, `POST /accounts` is not an authentication filter; `GET /orders/42` should not handle passwords directly; and suspension should not merely flip a database flag while leaving still-valid tokens unattended.

## 6. Spring Boot 3.x / Java 17+ Example: A Request Passing Through AuthN Then AuthZ

The minimal example below uses HTTP Basic and two in-memory accounts to clearly observe the three outcomes 401, 403, and 200. It illustrates AuthN/AuthZ; the lifecycle workflows described above require persistence and dedicated services in a real system.

Create a Gradle project with `settings.gradle`:

~~~groovy
rootProject.name = 'authn-authz-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Create a single file `src/main/java/example/authdemo/DemoApplication.java`:

~~~java
package example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/public/status").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("change-me"))
            .authorities("orders:read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("change-me"))
            .authorities("profile:read")
            .build();

        return new InMemoryUserDetailsManager(reader, viewer);
    }
}

@RestController
class DemoController {
    @GetMapping("/public/status")
    String status() {
        return "OK";
    }

    @GetMapping("/orders/{id}")
    @PreAuthorize("hasAuthority('orders:read')")
    OrderView getOrder(@PathVariable String id) {
        return new OrderView(id, "READABLE");
    }
}

record OrderView(String id, String status) {}
~~~

**Explanation following the responsibility boundaries:**

- `httpBasic()` enables reading HTTP Basic credentials and authenticating the user. `UserDetailsService` provides the two principals; `PasswordEncoder` stores/checks passwords in bcrypt format. Both `reader` and `viewer` can authenticate with the sample password.
- `requestMatchers(HttpMethod.GET, "/orders/**").authenticated()` requires an authenticated identity before entering the API; `/public/status` allows unauthenticated access; remaining paths are denied by default.
- `@EnableMethodSecurity` activates method-level checks; `@PreAuthorize("hasAuthority('orders:read')")` decides the caller's permission. `viewer` is authenticated but lacks the authority, so it is denied.
- `DemoController` does not compare passwords itself or read client-sent roles. The example does not yet check the order owner: a real application must add object-level policies in the service/repository to prevent IDOR.
- The two users in `InMemoryUserDetailsManager` are only fixtures. They do not provide registration, email verification, locking, recovery, or token revocation flows. The password `change-me` is only for local testing. Spring Security's default CSRF protection is not disabled in the example; write operations using cookies/sessions need an appropriate CSRF policy.

Run with the project's Gradle Wrapper (if a wrapper has been generated), or use a compatible Gradle installation:

~~~bash
./gradlew bootRun
~~~

Open another terminal and run the following commands in a shell with `curl` (each command prints only the HTTP status code):

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/status
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/orders/42
curl -s -o /dev/null -w '%{http_code}\n' -u viewer:change-me http://localhost:8080/orders/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:change-me http://localhost:8080/orders/42
~~~

Expected output, in order, with the configuration above:

~~~text
200
401
403
200
~~~

You can call `curl -s -u reader:change-me http://localhost:8080/orders/42` to receive JSON with `id` as `42` and `status` as `READABLE`. Code 401 comes from an unauthenticated request; 403 comes from an authenticated principal lacking the authority; 200 comes from a principal with permission. Do not use sample passwords or HTTP Basic over unencrypted HTTP on a real network.

## 7. Commonly Misunderstood Cases

**"Once logged in, you can view any order."** False: authenticated only proves the principal; authorization must evaluate the action and resource. `orders:read` does not imply owning every order.

**"Having role ADMIN in a JWT means the backend must trust it immediately."** The backend must validate the token (signature/issuer/audience/expiration per configuration) and map claims into authorities according to policy. Roles passed directly by the frontend are untrusted.

**"Changing the password immediately logs out every device."** Not automatically. Changing the password hash typically affects the next password-based authentication; existing sessions and access tokens need a separate policy to revoke/expire.

**"Setting account.enabled=false immediately invalidates issued JWTs."** Only true if the request-validation path checks state or an appropriate revocation mechanism. With self-contained JWTs verified offline, changing a DB flag does not modify the token.

**"You must use 403 for all login errors."** Missing/wrong credentials usually go through the authentication entry point, returning 401 for APIs (or redirecting for form login); 403 typically means authenticated but lacking permission. Do not let error codes reveal whether an account exists during login/recovery.

**"Authorizing once at the controller is enough."** Not necessarily: a service may be called from another endpoint, message consumer, or background job; sensitive policies, especially ownership and tenant boundaries, must be checked at the appropriate business point.

**"Account management is just a users table."** Not enough: you need state flows, reset/verify, authorization for state changes, auditing, credential revocation, and data handling per policy.

## 8. Design and Testing Checklist

Use a scenario matrix instead of testing only one normally working admin account:

| Test scenario | What to verify |
|---|---|
| Anonymous accesses an endpoint requiring login | Authentication required; no data leaked |
| Logged in but missing authority | Denied properly at URL/method layer |
| Has authority but accesses another user's/tenant's order | Denied at the object-check layer |
| Locked/unverified account attempts a new login | AuthN mechanism denies per policy |
| Account suspended after already logging in | Old sessions, refresh tokens, and access tokens are handled per commitment |
| Password change, MFA reset, role grant/revocation | Old credentials and old permissions do not continue working beyond the allowed timeframe/policy |
| Reusing an activation/reset token or expired token | Cannot be used twice and validity is not extended |
| Calling the API directly bypassing the UI | Backend still authenticates and authorizes |

In addition to testing for 200/401/403 responses, verify the **actual data** returned, test operations on both sides of tenant/ownership boundaries, audit sensitive actions without logging secret credentials, and simulate concurrent permission/state changes while tokens remain valid.

## 9. Knowledge Self-Check

**Question 1.** A user enters the right password, calls an admin API, and gets 403. Which component succeeded and which rejected?  
**Answer:** AuthN succeeded; AuthZ rejected the operation due to insufficient permissions.

**Question 2.** A user is suspended in the database, yet an old JWT can still call the API. Where is the gap?  
**Answer:** The lifecycle workflow and state-enforcement/token-revocation strategy are not properly connected to the current request authentication/authorization path. The validity contract and a way to reject already-issued tokens must be defined clearly.

**Question 3.** Two people both have `orders:read`; is person A allowed to view person B's order?  
**Answer:** You cannot conclude that from the authority alone. Ownership, tenant, or specific sharing policies must be checked.

**Question 4.** Are changing a password and changing a role the same responsibility?  
**Answer:** Changing a password is credential/account-lifecycle management; changing a role is permission administration within the identity lifecycle and affects AuthZ outcomes. Both require mechanisms to propagate their effect to sessions/tokens when policy demands it.

## 10. Takeaways to Apply

- **AuthN identifies the principal from trusted evidence.** Spring Security provides the filter chain, providers, authentication context, and authentication integrations.
- **AuthZ decides the action on a resource in context.** Use URL/method security as a barrier, and supplement with object/tenant checks in business logic.
- **Account lifecycle decides when an account exists, can be used, and must be revoked.** Design dedicated state machines, self-service/admin workflows, auditing, and session/token policies.
- **Account state changes must have a clearly defined effect on old credentials and tokens.** Test both new requests and requests using previously issued evidence.

The three responsibilities cooperate to protect the same system, yet each has its own inputs, control points, and test conditions.