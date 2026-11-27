# Handling Locked, Expired, or Disabled Accounts

## 1. Context: Why Does Account Status Matter to an Authorization Server?

In a Spring Boot application using **Spring Security** and **Spring Authorization Server** to provide OAuth 2.0/OpenID Connect (OIDC), the Authorization Server does more than check passwords or other authentication methods. Before letting a user finish logging in and approve an authorization request, the system must also decide **whether the account is permitted to operate at that moment**.

For example, Alice signs into the Authorization Server so that `orders-web` can obtain an Authorization Code and an access token for the Orders API. Alice enters the right password, yet her account is locked due to suspicious activity. If the system merely matches the password and issues an authorization code, the account lock fails to protect anything. Conversely, if Alice signed in yesterday and is disabled today, blocking new logins **does not automatically block her existing session and tokens**.

This lesson focuses on how to design, configure, secure, test, and operate handling for **locked, account expired, credentials expired, or disabled accounts** in Spring Security, as well as how those states affect OAuth 2.0/OIDC flows.

After this lesson, you should be able to:

1. Distinguish the four account states supported by <code>UserDetails</code>, their corresponding exceptions, and the check order when authenticating with <code>DaoAuthenticationProvider</code>.
2. Map domain status from a database into <code>UserDetails</code> without confusing account expiration with credentials expiration.
3. Configure interactive Authorization Server login using <code>SecurityFilterChain</code>, understanding when requests should redirect to the login page.
4. Handle status changes when **the user already holds a session, authorization code, access token, or refresh token**.
5. Design lock/unlock, disable, recovery, and monitoring policies without leaking account existence.
6. Write unit and integration tests for status flags, OAuth/OIDC requests, and access revocation.

## 2. Distinguishing the Four States in Spring Security

### 2.1. The <code>UserDetails</code> Contract

<code>UserDetails</code> represents a principal authenticated with username/password through <code>UserDetailsService</code> and corresponding providers. The four methods below return **<code>true</code> when the account condition remains valid**:

| Method | What <code>false</code> Means | Typical Exception with Default Provider |
| --- | --- | --- |
| <code>isAccountNonLocked()</code> | Account is currently locked. | <code>LockedException</code> |
| <code>isAccountNonExpired()</code> | Account has expired. | <code>AccountExpiredException</code> |
| <code>isCredentialsNonExpired()</code> | Credentials, such as a password, have expired. | <code>CredentialsExpiredException</code> |
| <code>isEnabled()</code> | Account has been disabled. | <code>DisabledException</code> |

An easy pitfall is the double-negative naming of the first three methods: <code>isAccountNonLocked() == false</code> indicates a locked account. Meanwhile, Spring Security's builder methods—<code>accountLocked(true)</code>, <code>accountExpired(true)</code>, <code>credentialsExpired(true)</code>, and <code>disabled(true)</code>—express the adverse condition directly.

### 2.2. Four States Serve Distinct Business Purposes

| State | Typical Scenario | Appropriate Handling Path |
| --- | --- | --- |
| **Locked** | Multiple failed login attempts, suspected takeover, or temporary security hold. | Do not issue a new session; rate-limit retries, investigate, or unlock per duration/policy. |
| **Account expired** | Contractor/trial account past its end date or lapsed entitlement. | Disallow standard login; renew via a controlled workflow. |
| **Credentials expired** | Aged-out password, signing/auth key rotation needed, or forced credential reset. | Do not complete standard login; route to a separately protected credential-update flow. |
| **Disabled** | Admin disabled account, employee departure, policy violation, or pending activation. | Block usage, handle session/token revocation, and re-enable only when authorized. |

Do not collapse <code>locked</code>, <code>expired</code>, and <code>disabled</code> into a single boolean flag. An account can be locked and expired at the same time; recovery, monitoring, and auditing still need to distinguish the causes.

**Note:** These methods belong to the **End-User** authentication model. They are not <code>RegisteredClient</code> status flags and do not replace validating <code>client_secret</code>, <code>client_secret_expires_at</code>, or OAuth 2.0 client authentication.

### 2.3. Check Order in <code>DaoAuthenticationProvider</code>

For standard username/password authentication, <code>DaoAuthenticationProvider</code> inherits the flow from <code>AbstractUserDetailsAuthenticationProvider</code>:

1. Look up <code>UserDetails</code> via <code>UserDetailsService</code>.
2. Run **pre-authentication checks**: account is not locked, is enabled, and has not expired.
3. Verify credentials (e.g., compare password with <code>PasswordEncoder</code>).
4. Run **post-authentication checks**, including checking that credentials have not expired.
5. Produce a successful <code>Authentication</code> only if every required condition passes.

In the default implementation, pre-checks typically evaluate **locked → disabled → account expired**; post-checks evaluate **credentials expired**. If an account has multiple adverse flags, the thrown exception reflects whichever check failed first. Do not rely on exception ordering as a permanent business-priority contract or expose raw exception differences directly to end users.

This is the behavior of a **username/password provider that inspects <code>UserDetails</code>**. A custom <code>AuthenticationProvider</code>, federated login, pre-authenticated principal, or any mechanism not using <code>DaoAuthenticationProvider</code> **does not automatically** inherit all of these checks.

## 3. Modeling Account Status in the Database

### 3.1. Do Not Store Four Booleans Without Cause and Timestamps

A practical user model might include:

| Field | Meaning | Guidance |
| --- | --- | --- |
| <code>user_id</code> | Immutable identifier of the principal. | Use a stable ID, especially in multi-tenant systems. |
| <code>enabled</code> | Whether the user is allowed to use the account. | Managed through activation/deactivation workflows. |
| <code>manually_locked</code> | Manual lock for operational/security reasons. | Record reason, actor, and audit trail. |
| <code>locked_until</code> | End timestamp of a temporary lockout. | Compare using a reliable UTC clock. |
| <code>account_expires_at</code> | Timestamp when the account expires. | Do not confuse with password/token age. |
| <code>credentials_expires_at</code> | Timestamp when credentials expire. | Driven by password/credential rotation policy. |
| <code>failed_login_count</code> | Failed authentication counter. | Requires concurrency safety and reset rules. |
| <code>status_reason</code>, <code>status_changed_at</code> | Reason and timestamp of status change. | Supports helpdesk, auditing, and incident response. |

These are **domain modeling suggestions**, not a schema generated by Spring Authorization Server. In production systems, explicitly define boundary semantics for expiration timestamps; the standard convention is <code>now >= expiresAt</code> means expired.

Avoid relying solely on <code>username</code> or email as a security key when users can rename themselves or multiple tenants share login names. Even if the Authorization Server's <code>principalName</code> uses a display username, map consistently to an immutable ID when minting tokens, revoking sessions, and evaluating permissions.

### 3.2. Mapping Domain Data to <code>UserDetails</code>

Example using an application-defined domain repository and corresponding getters on the account record:

~~~java
@Configuration
class UserAccountAuthenticationConfig {

    @Bean
    Clock securityClock() {
        return Clock.systemUTC();
    }

    @Bean
    UserDetailsService userDetailsService(
            UserAccountRepository accounts,
            Clock securityClock) {

        return login -> {
            UserAccount account = accounts.findByLogin(login)
                .orElseThrow(() ->
                    new UsernameNotFoundException("Account not found"));

            Instant now = securityClock.instant();

            boolean locked =
                account.isManuallyLocked()
                || (account.getLockedUntil() != null
                    && now.isBefore(account.getLockedUntil()));

            boolean accountExpired =
                account.getAccountExpiresAt() != null
                && !now.isBefore(account.getAccountExpiresAt());

            boolean credentialsExpired =
                account.getCredentialsExpiresAt() != null
                && !now.isBefore(account.getCredentialsExpiresAt());

            return User.withUsername(account.getLogin())
                .password(account.getPasswordHash())
                // Demo: real apps must resolve roles/authorities from policy.
                .authorities("ROLE_USER")
                .disabled(!account.isEnabled())
                .accountLocked(locked)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
        };
    }
}
~~~

In this code:

- <code>UserAccount</code>, <code>UserAccountRepository</code>, and their getters are **illustrative domain types**, not built-in Spring Security classes.
- <code>Clock</code> is injected so tests can deterministically verify timestamps before and after <code>locked_until</code> or expiration boundaries.
- <code>locked_until == null</code> means no timed lock; <code>manually_locked</code> keeps the account locked until manually cleared.
- <code>passwordHash</code> must match the provider's <code>PasswordEncoder</code>, such as properly configured BCrypt/Argon2. Never store raw passwords.
- Hardcoding <code>ROLE_USER</code> is purely illustrative; real applications must resolve roles, tenants, scopes, and permissions from their own model.

When a status changes, **new** login requests normally fetch fresh state from the data store at authentication time. However, if <code>UserDetails</code> is cached or an existing session already holds an authenticated principal, the new status may **not** take effect immediately. That lifecycle gap is addressed in section 7.

### 3.3. Providers and Password Encoders

Spring Security pairs <code>UserDetailsService</code> with <code>DaoAuthenticationProvider</code> for a typical username/password setup. You can declare a <code>PasswordEncoder</code>:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

<code>DelegatingPasswordEncoder</code> uses prefixes like <code>{bcrypt}</code> to choose how stored hashes are verified. Real systems must plan password hash migrations, work-factor tuning, and credential protection. Never use <code>{noop}</code> or plaintext passwords in production data.

If your application registers custom <code>AuthenticationManager</code>, <code>AuthenticationProvider</code>, or multiple authentication sources, verify that the provider **actually selected** enforces the expected status checks. Never assume merely defining a <code>UserDetailsService</code> bean causes every login mechanism to invoke it.

## 4. User Login Flow in OAuth 2.0/OIDC

### 4.1. Choosing the Right Security Filter Chain

Spring Authorization Server exposes protocol endpoints such as <code>/oauth2/authorize</code>, <code>/oauth2/token</code>, and OIDC endpoints when enabled. A username/password login page typically belongs to a **separate web chain** with form login and appropriate session handling.

~~~java
@Configuration
@EnableWebSecurity
class SecurityChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(
            HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is an **illustrative configuration for Spring Authorization Server using the compatible Java DSL API**; imports and foundational beans are omitted. A real project requires <code>RegisteredClientRepository</code>, authorization service, keys/JWK, <code>JwtDecoder</code> when OIDC is enabled, a user store, encoder, and other supporting components.

<code>@Order(1)</code> places the Authorization Server chain first; <code>getEndpointsMatcher()</code> covers endpoints managed by the configurer. When an unauthenticated browser sends an authorization request, the entry point redirects to <code>/login</code>, where the web chain handles the form. **A request enters only the first matching chain**, not both sequentially.

This snippet does not disable CSRF globally. Cookie/session-backed <code>POST /login</code> requests must retain proper CSRF protection. A credential failure is never a reason to leave the token endpoint open or disable client authentication.

### 4.2. Path When an Account Is Locked

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Alice's Browser
    participant AS as Authorization Server endpoint
    participant W as Web login chain
    participant P as DaoAuthenticationProvider
    participant D as UserDetailsService/Database
    B->>AS: GET /oauth2/authorize (client_id, scope, state, PKCE)
    AS-->>B: Redirect /login if no Authentication
    B->>W: POST /login + username/password + CSRF
    W->>P: UsernamePasswordAuthenticationToken
    P->>D: loadUserByUsername(alice)
    D-->>P: UserDetails: accountNonLocked=false
    P-->>W: LockedException
    W-->>B: Login failure, no authenticated session created
    Note over W,AS: Do not issue authorization code or ID Token merely because password matched
~~~

Inside <code>DaoAuthenticationProvider</code>, a locked account is typically rejected **before comparing the password**, depending on pre-check ordering. Therefore, never rely on "password was right but locked" to infer whether password verification actually ran in the same attempt.

With OAuth 2.0 Authorization Code/OIDC, a user who has not authenticated successfully cannot complete steps requiring End-User authentication. The login screen may show only a generic error message. Do not force every login failure into OAuth <code>invalid_grant</code>: account status errors occur during interactive login, whereas the token endpoint has its own protocol error set.

### 4.3. Flow for the Remaining Three States

~~~mermaid
flowchart TD
    A["POST /login"] --> B["Load UserDetails"]
    B --> C{"Is account locked?"}
    C -- Yes --> X["LockedException"]
    C -- No --> D{"enabled = true?"}
    D -- No --> Y["DisabledException"]
    D -- Yes --> E{"Account not expired?"}
    E -- No --> Z["AccountExpiredException"]
    E -- Yes --> F{"Valid credentials?"}
    F -- No --> G["BadCredentialsException or matching credential error"]
    F -- Yes --> H{"Credentials not expired?"}
    H -- No --> J["CredentialsExpiredException"]
    H -- Yes --> K["Authentication succeeds; continue OAuth/OIDC policy"]
~~~

This diagram reflects the **check suite of the default username/password provider**, not a universal ordering guarantee across all authentication mechanisms. When using WebAuthn, LDAP, federation, or custom providers, ensure account status policies are enforced at the corresponding authentication point.

## 5. Safe and Useful Authentication Error Handling

### 5.1. Exceptions, UI Responses, and Disclosure Policy

| Server-Side Exception | Common Condition | Information Returned to User |
| --- | --- | --- |
| <code>LockedException</code> | <code>isAccountNonLocked() == false</code> | Safe notice, recovery path, or support link; avoid exposing investigative details. |
| <code>DisabledException</code> | <code>isEnabled() == false</code> | Policy-appropriate notice; optionally direct to support. |
| <code>AccountExpiredException</code> | <code>isAccountNonExpired() == false</code> | Organizational renewal or support workflow. |
| <code>CredentialsExpiredException</code> | <code>isCredentialsNonExpired() == false</code> | Protected credential-update workflow. |
| <code>BadCredentialsException</code> | Wrong username/password or masked as such. | Generic login error without confirming account existence. |
| <code>UsernameNotFoundException</code> | User not found in store. | Normally indistinguishable publicly from bad credentials. |

Spring Security typically masks missing-username errors inside <code>DaoAuthenticationProvider</code> as generic credential errors. Status exceptions can still be recorded internally. **Detailed technical reasons should not automatically appear on a public login page**, because attackers can exploit differences to enumerate accounts, lockout thresholds, or expiration dates.

Recommended design:

- **Externally:** generic message such as "Unable to sign in. Check your credentials or use account recovery," paired with support instructions when appropriate.
- **Internally:** log the classified error code, stable account ID, request correlation ID, and timestamp; never log passwords, MFA codes, authorization codes, access tokens, or refresh tokens.
- **Identity-verified recovery channels:** can provide more specific guidance once the user proves control over the account.

Do not insist that "every error must return HTTP 401" across all endpoints. Form login typically returns **302 back to the login page with an error flag**, APIs return JSON 401/403 per their contract, and OAuth 2.0/OIDC endpoints return protocol-defined responses/errors. Verify actual behavior per chain.

### 5.2. <code>AuthenticationFailureHandler</code> for Form Login

A handler can unify the UI response:

~~~java
@Bean
AuthenticationFailureHandler safeLoginFailureHandler() {
    return (request, response, exception) -> {
        // Classified internal audit; never return exception names to the browser.
        response.sendRedirect(
            request.getContextPath() + "/login?error");
    };
}
~~~

When configuring a custom handler, attach it to the web chain:

~~~java
http.formLogin(form -> form
    .failureHandler(safeLoginFailureHandler)
);
~~~

These two snippets belong to **the same example**; the <code>safeLoginFailureHandler</code> variable in the second snippet represents the injected bean, not an implicitly defined local variable. The application must prevent open redirects, properly encode URLs with the context path, and plan UX messaging. Never place <code>exception.getMessage()</code> in query parameters or rendered HTML.

On the backend, count only **genuine credential failures** toward failed-attempt lockout policies. Do not increment failure counters on <code>LockedException</code>, <code>AccountExpiredException</code>, or system outages in ways that make legitimate recovery harder.

### 5.3. Auditing and Authentication Events

Spring Security emits authentication events such as <code>AuthenticationFailureBadCredentialsEvent</code>, <code>AuthenticationFailureLockedEvent</code>, <code>AuthenticationFailureDisabledEvent</code>, and account/credential expiration events. Depending on configuration, <code>DefaultAuthenticationEventPublisher</code> maps <code>AuthenticationException</code> subclasses to these events.

Events provide a clean signal for auditing, alerting, and monitoring. However, **never build primary lockout enforcement solely on asynchronous listeners lacking ordering or durability guarantees**. Attempt counters require backing storage that handles concurrent requests, multiple instances, and retries safely.

## 6. Lockout, Expiration, and Unlock Policies

### 6.1. Temporary Lockout After Repeated Failures

Illustrative policy example:

~~~text
Within a time window:
  5 consecutive failed attempts -> locked_until = now + 15 minutes
  Attempts while locked -> rejected, no session issued
  After locked_until -> allow retries per policy
  Successful login -> reset failure counter if appropriate
~~~

These numbers are **examples only**, not Spring Security defaults. The framework does not automatically lock accounts at this threshold simply because you use <code>DaoAuthenticationProvider</code>.

Key implementation points:

1. **Normalize identifiers** per policy (Unicode/case/tenant) without accidentally merging two distinct accounts.
2. Update <code>failed_login_count</code> and <code>locked_until</code> **atomically/transactionally** so concurrent requests never drop increments.
3. Combine with **rate limiting by IP/device/ASN/risk** instead of pure account lockouts; attackers can deliberately submit bad passwords to lock out other people's accounts.
4. Distinguish non-existent accounts from wrong passwords in internal telemetry while keeping public responses uniform enough to limit user enumeration.
5. Auto-unlock policies must apply only to timed lockouts; **never automatically clear manual security locks**.
6. Retain lock reason, actor, and timestamp history for auditing.

For systems with MFA/WebAuthn, failed attempts on each factor need separate policies. "Correct password" does not equal successful login if an additional factor remains.

### 6.2. Account Expiration

Account expiration should derive from an authoritative source such as employee contracts, organization memberships, or trial account limits. Compare timestamps using <code>Instant</code>/UTC rather than relying on host local timezones. For renewals, define who has authority to extend accounts, whether approval is needed, and when changes take effect across instances.

Do not use <code>account_expires_at</code> to represent **access token expiration**. An account is a principal identity; <code>exp</code> on a JWT access/ID Token is a per-token property with its own lifecycle.

### 6.3. Credentials Expiration

When a password/credential expires, <code>DaoAuthenticationProvider</code> throws <code>CredentialsExpiredException</code> instead of returning a successful <code>Authentication</code>. If your application needs a "Force password change" flow, design a **dedicated recovery path**:

- The user must prove identity via an approved mechanism such as a recovery challenge, MFA, or a tightly scoped session.
- Grant permission only to update the credential within tight bounds and time limits; never issue a full-scope access token just so the user can change a password.
- Enforce password strength, password history rules if required, and store using a secure password encoder.
- After updating credentials, update status flags, invalidate the recovery challenge, and handle existing sessions/tokens per policy.

Never put an unauthenticated password-change endpoint under <code>permitAll()</code> simply because the provider rejected the account. A credentials-expired state does not prove the caller owns the account.

### 6.4. Disabled Accounts

Disabling an account is usually an administrative or organizational lifecycle action. Back it with strict authorization, re-authentication where needed, audit logging, and safeguards preventing administrators from accidentally disabling all admin accounts.

Once disabled, the account cannot create new logins; if the product requires **immediate access cutoff**, you must also address active sessions, refresh tokens, and circulating access tokens. Setting <code>enabled=false</code> in the database alone is insufficient for immediate termination.

## 7. The Hardest Part: Account Status Changes While Already Logged In

### 7.1. Existing Sessions Do Not Automatically Re-Read <code>UserDetails</code>

After a successful form login, the <code>SecurityContext</code> is typically saved in the HTTP session. On subsequent requests, Spring Security restores the authenticated principal from the session **without re-invoking <code>UserDetailsService.loadUserByUsername()</code>**.

Consequently, when an administrator sets <code>enabled=false</code> or locks an account:

~~~mermaid
flowchart TD
    A["User already signed in with active session"] --> B["Admin locks/disables account in DB"]
    B --> C{"Is there a session invalidation mechanism?"}
    C -- No --> D["Session may keep holding stale Authentication"]
    C -- Yes --> E["Invalidation / expiry / revalidation per design"]
    D --> F{"Does authorization endpoint check current status?"}
    F -- No --> G["Risk of continuing to issue new authorizations"]
    F -- Yes --> H["Deny when current status is invalid"]
    E --> H
~~~

<code>authorizeHttpRequests().anyRequest().authenticated()</code> only checks that the security context holds an authenticated <code>Authentication</code>; it **does not guarantee the account is still enabled in the database on every request**.

Solutions depend on consistency requirements and infrastructure:

- **Invalidate active sessions:** use a session registry or Spring Session capable of looking up sessions by principal, paired with a multi-node strategy.
- **Re-check status at authorization issuance seams:** re-verify account status before accepting authorization requests/consent and before minting tokens when required.
- **Shorten lifetimes and detect anomalies:** cap session age, require re-authentication for sensitive actions, broadcast status events across nodes, and balance DB/cache load.

A session marked "expired" may only be rejected on the **next request**; ending a session does not immediately erase an already-issued access token. When using a session registry, the principal key must be stable and uniform; multi-node apps need shared storage or distributed session events.

### 7.2. Already-Issued Authorization Codes and the Token Endpoint

Suppose Alice was issued an authorization code and then disabled **before the client exchanged the code for tokens**. Under default configuration, the token endpoint processes the code using the stored authorization and client authentication, without necessarily re-querying Alice's account record.

If policy requires blocking token issuance immediately after lock/disable, enforce checks at **authorization and token-minting seams**:

1. When processing authorization requests for users with existing sessions.
2. When processing consent and issuing authorization codes, if status could change mid-flow.
3. When exchanging an authorization code for tokens, if policy requires live End-User status verification.
4. When using a refresh token to mint a new access token.
5. When performing token exchange or extension grants acting on behalf of an End-User (if implemented).

Projects must design and integrate this policy using the authentication providers, authorization service, or extension hooks of the **exact Spring Authorization Server version in use**. Do not treat writing an <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> as a complete solution: customizers only run for certain token types/formats and do not revoke authorizations or refresh tokens.

### 7.3. Refresh Tokens Can Still Mint New Tokens

The <code>refresh_token</code> grant relies on a previously issued token, client authentication, and Authorization Server policy; it **is not an interactive End-User password login**.

Therefore:

- A disabled account **does not mean** refresh tokens are automatically deleted.
- A locked account **does not guarantee** every refresh request re-invokes <code>UserDetailsService</code>.
- To halt new token issuance, **revoke related refresh tokens/authorizations** or check End-User status in the refresh path per policy.
- For Client Credentials, the access token represents a **client/service**, typically with no End-User; never apply disabled-user rules blindly to every <code>sub</code> without checking the grant type.

<code>OAuth2AuthorizationService</code> persists authorization/token state, yet its standard interface **lacks a generic "find all tokens by username and revoke all" method**. Revoking all authorizations for a user requires designing appropriate queries, consistent mutations, and handling race conditions between concurrent refreshes and revocations.

### 7.4. Already-Issued JWT Access Tokens

A Resource Server verifying self-contained JWTs normally checks only signature, issuer, audience, expiration, and scope claims. While a JWT remains unexpired, disabling Alice's account in the Authorization Server's database **does not automatically invalidate the JWT**.

| Mechanism | Effect When Account Is Disabled | What to Add for Early Access Cutoff |
| --- | --- | --- |
| JWT access token, offline verification | Unexpired tokens may still be accepted. | Short TTL, centralized status checks, or denylist/revocation per design. |
| Opaque/reference token with introspection | Introspection can inspect live server-side token state. | Ensure authorization/account status reflects in <code>active</code> or verification policy. |
| Refresh token | Can continue to be used while valid. | Revoke refresh tokens and/or check account status on refresh. |
| Browser session | May retain stale `Authentication`. | Session invalidation or revalidation on critical requests. |
| New authorization | May rely on stale session if unchecked. | Re-check status before issuing permissions/tokens as appropriate. |

Never promise "disabling an account cuts access immediately across every API" if your architecture relies solely on offline-verified JWTs with no live status checks or instant revocation.

### 7.5. OIDC: ID Token, UserInfo, and Login Sessions

OIDC uses an ID Token to inform the client of an End-User authentication event. Disabling an account after an ID Token is issued **cannot alter claims inside the existing token**. Clients may also hold local sessions or sessions with third parties.

Keep these distinct:

- **Authorization Server session**: the user's session at the identity provider.
- **Relying Party (OIDC Client) session**: the local session created by the client app after receiving the ID Token.
- **Access token/refresh token**: OAuth credentials with independent lifecycles.

Logging out at the Authorization Server, OIDC RP-Initiated Logout, or front-channel/back-channel logout can synchronize sessions **when participating parties actually support and configure them properly**. Logging out of a session does not automatically revoke every access token, and flipping <code>enabled</code> does not automatically broadcast logout messages to every client.

## 8. Business Workflow for Account Status Changes

### 8.1. Lock or Disable Workflow

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Admin/Security Policy
    participant S as Account Lifecycle Service
    participant DB as Account Database
    participant H as Session Manager
    participant T as Authorization/Token Store
    participant API as Resource Server
    A->>S: Lock or disable user-42 (reason)
    S->>S: Check permissions, policy, idempotency
    S->>DB: Update status, version, audit
    DB-->>S: Success
    S->>H: Expire/invalidate sessions by principal
    S->>T: Revoke authorizations/refresh tokens per policy
    S->>API: Emit signal or update deny state if needed
    S-->>A: Result + status of applied steps
~~~

This diagram illustrates a **business workflow design**; Spring Authorization Server does not ship a turnkey "disable user and revoke every token across every Resource Server" API. When components span multiple systems, updating the account DB, session store, token store, and denylist **does not share a single atomic transaction**. Design retries, idempotency, auditing, reconciliation, and partial-failure handling.

For security policies requiring immediate access cutoff, define execution order, acceptable propagation windows, and fail-closed behavior. For example, before reporting "all access blocked," know whether APIs have received the lock state or whether offline JWTs remain valid.

### 8.2. Recovery and Unlocking

Unlocking must not mean "restoring all old refresh tokens and sessions":

1. Review the lock reason and recovery criteria (elapsed time, identity verification, support review, MFA, authorized admin).
2. Update account status via an audited change; decide whether to reset failed-attempt counters and credential flags.
3. If credentials may have been compromised, require credential rotation and revoke old sessions/tokens.
4. Require a fresh login where appropriate; never re-enable previously revoked tokens.
5. Ensure OIDC/OAuth consent is reused only within valid bounds; re-evaluate current user/account policies.

An account may be unlocked while still having <code>disabled=true</code> or being expired. Admin interfaces should display **independent conditions** separately to avoid mistaking "unlocked" for "fully active."

### 8.3. Business-Level State Machine

Express behavior using **composite evaluation** rather than forcing four independent flags into a single enum:

~~~text
ACTIVE:
  enabled=true
  manuallyLocked=false
  now >= lockedUntil (if set)
  now < accountExpiresAt (if set)
  now < credentialsExpiresAt (if set)

AUTHENTICATION_DENIED:
  disabled OR locked OR accountExpired OR credentialsExpired

RESTORED:
  Must re-evaluate all conditions;
  never automatically restore revoked sessions/tokens.
~~~

The rules above are conceptual notation. Specifically for <code>credentialsExpired</code>, a system may provide a **scoped recovery session** to rotate credentials; that is a distinct security flow from a normal authenticated session.

## 9. Consistency, Caching, and Multi-Instance Operation

An account might be disabled on node A while node B holds cached <code>UserDetails</code> or a stale security context. Implementation choices depend on your access-cutoff latency SLA:

| Approach | Strengths | Limitations |
| --- | --- | --- |
| Query account status on every critical authorization/refresh | Reads fresh state from the source of truth. | Increases load and latency; requires DB failure handling. |
| Cache account status with short TTL + event invalidation | Reduces load while propagating changes quickly. | Risk of cache/event inconsistency; must bound staleness window. |
| Centralized session registry/store | Can expire sessions across multiple nodes. | Does not handle already-issued tokens; requires consistent principal keys. |
| Reference tokens + introspection | Centralizes enforcement better than offline JWTs. | Adds coupling, latency, and introspection availability risk. |
| Short-lived JWTs + blocking refresh | Simpler for many APIs. | Already-issued JWTs remain valid until expiration. |

When the database or policy store is unavailable, explicitly choose **fail-open vs. fail-closed** per endpoint sensitivity. For sensitive actions or issuing new grants, never silently treat an "unknown" status as active. Pair fail-closed strategies with operational resilience and monitoring to prevent cascading outages.

Failure-counter increments and unlocks must also prevent **race conditions**. For example, two concurrent failed attempts must not both read count 3 and both write 4 when the true count should be 5; use atomic increments, optimistic locking, or properly isolated transactions.

## 10. Testing: From <code>UserDetails</code> to OAuth2/OIDC

### 10.1. Unit Testing Time-Based Status Mapping

Test <code>UserDetailsService</code> with a fixed clock and mocked repository to verify:

| Domain Data | Expected <code>UserDetails</code> |
| --- | --- |
| <code>enabled=false</code> | <code>isEnabled()==false</code> |
| <code>manually_locked=true</code> | <code>isAccountNonLocked()==false</code> |
| <code>locked_until</code> in the future | <code>isAccountNonLocked()==false</code> |
| <code>locked_until</code> in the past, not manually locked | <code>isAccountNonLocked()==true</code> |
| <code>account_expires_at <= now</code> | <code>isAccountNonExpired()==false</code> |
| <code>credentials_expires_at <= now</code> | <code>isCredentialsNonExpired()==false</code> |
| No expiry/lock and enabled | All four conditions pass |

Include boundary tests **at the exact expiration instant**, across DST/timezone boundaries, and across combined status flags. <code>Clock.fixed(...)</code> keeps tests deterministic regardless of host system time.

### 10.2. Unit Testing Provider Exceptions

Assuming the test constructs a real <code>AuthenticationManager</code> backed by <code>DaoAuthenticationProvider</code> and user <code>alice</code> with <code>accountLocked(true)</code>:

~~~java
@Test
void lockedAccountCannotAuthenticateWithCorrectPassword() {
    assertThatThrownBy(() -> authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "correct-password")))
        .isInstanceOf(LockedException.class);
}
~~~

Provider-level tests should use a real <code>PasswordEncoder</code> matching the stored hash and cover <code>DisabledException</code>, <code>AccountExpiredException</code>, and <code>CredentialsExpiredException</code>. Never use a pre-mocked <code>Authentication</code> with <code>authenticated=true</code> as proof that the provider enforces account status.

### 10.3. Form Login Integration Tests

With default Spring Security configuration using <code>/login</code> and the default <code>failureUrl</code>, you can test failed requests:

~~~java
@Test
void disabledAccountCannotCreateLoginSession() throws Exception {
    mockMvc.perform(post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "correct-password"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/login?error"));
}
~~~

This example assumes **default `formLogin`**; if your project uses a custom login page or failure handler, assert the corresponding URL or response format. Tests must also confirm **no authenticated <code>Authentication</code> is created** and any pending <code>/oauth2/authorize</code> request is not completed. Checking the redirect URL alone without verifying security state is insufficient.

### 10.4. End-to-End Integration Test Matrix

| Scenario | Expectation |
| --- | --- |
| Alice active, valid credentials | Login succeeds; authorization request proceeds per grant, scopes, and consent. |
| Alice locked, valid credentials | No authenticated login session created; new authorization does not complete. |
| Alice disabled, valid credentials | Rejected per policy; reason audited on backend. |
| Account expired | Normal login blocked; only allowed renewal workflow permitted. |
| Credentials expired | Does not issue standard session/full tokens; safe recovery flow if designed. |
| Consecutive failed passwords up to threshold | Counter and lock update accurately without lost concurrent increments. |
| Temporary lock expired | Verified via clock; still rejected if disabled/expired. |
| Account both locked and disabled | Cannot bypass by clearing only one flag. |
| Active browser session, then disabled | Session expired/revalidated per SLA; no new authorizations granted. |
| Disabled after authorization code issued | Token exchange rejected if policy requires live End-User status checks. |
| Held refresh token prior to disable | No new access token issued if policy requires immediate cutoff; verify revocation. |
| Held JWT access token prior to disable | Verify exact Resource Server behavior per revocation/TTL strategy. |
| Two instances sharing account and session store | Status synchronized within defined consistency bounds. |
| Service Client Credentials with no End-User | Do not confuse user account status with client authentication. |
| User in tenant A, same username in tenant B | Locking in tenant A never locks tenant B. |
| Unlocked while credentials remain expired | Must still handle credential expiration rather than auto-granting. |

For OAuth2/OIDC, write real integration tests exercising the authorization endpoint, login handler, client registration, authorization service, and token endpoint. Assert protocol responses, sessions, token issuance, and Resource Server enforcement; isolated <code>UserDetails</code> unit tests do not prove token-issuing seams enforce updated status.

## 11. Common Design Mistakes

### Mistake 1: Checking Password First and Skipping Status Checks

Writing custom logic like <code>if (passwordMatches) authenticated = true</code> without checking <code>enabled</code>, <code>locked</code>, <code>accountExpired</code>, and <code>credentialsExpired</code> lets blocked users sign in. Reuse Spring Security's standard providers wherever possible; if writing a custom provider, enforce equivalent status and policy checks.

### Mistake 2: Inverting the Booleans

Setting <code>accountNonLocked=false</code> for active accounts or <code>disabled=false</code> when an admin intended to disable an account reverses behavior. Write boundary tests for all four flags and give domain fields clear names.

### Mistake 3: Assuming <code>isEnabled=false</code> Revokes Every Token

<code>isEnabled()</code> is checked by the provider during username/password authentication. It does not automatically delete existing sessions, issued authorizations, or JWT access tokens. Add session/token lifecycle enforcement at the appropriate seams.

### Mistake 4: Protecting Only <code>/login</code> While Ignoring <code>/oauth2/authorize</code>

Users with an existing session may not pass through `/login` again. If your system must halt authorization issuance immediately once an account is disabled, revalidate at the authorization flow and invalidate existing sessions.

### Mistake 5: Refresh Tokens Ignoring Account Status

The refresh grant normally involves no password entry; if account checks exist only in the login provider, disabled accounts can keep minting fresh access tokens. Enforce revocation and/or status validation in the refresh path.

### Mistake 6: Returning "This Account Exists but Is Locked" to Any Caller

Overly specific responses, timing differences, or username-dependent error text enable user enumeration. Record exact causes internally and rely on identity-verified recovery flows to share account-specific details.

### Mistake 7: Locking After N Failures Using Only In-Memory RAM Variables

Simple in-memory counters diverge across instances, reset on restarts, and fail under concurrency. Use shared storage with atomic operations alongside rate limiting and DoS defenses.

### Mistake 8: Allowing Credential Resets on a Public Endpoint Without a Challenge

Having expired credentials does not prove a password-change request is legitimate. Verify account ownership, bind reset tokens/challenges to the user, enforce short expiration, and ensure single use.

### Mistake 9: Confusing Users with OAuth Clients

<code>UserDetails.enabled</code> and <code>RegisteredClient</code> secret status govern separate authentication paths. A batch job using <code>client_credentials</code> may have no End-User; validate client registration, auth method, grants, and scopes independently.

## 12. Pre-Production Design Checklist

| Area | Questions to Answer |
| --- | --- |
| Status policy | Are locked/disabled/accountExpired/credentialsExpired clearly defined and prioritized? |
| Data model | Do you track actor, reason, timestamps, tenant, immutable ID, version, and audit? |
| Providers | Does every login path enforce status per policy? |
| Form login | Are CSRF, session fixation protection, timeouts, and safe failure handlers enabled? |
| Active sessions | When disabled, how are existing sessions expired/revalidated across all instances? |
| New authorizations | Can a disabled/locked account still mint an authorization code via an old session? |
| Tokens/refresh | Are refresh tokens, stored authorizations, and active JWT access tokens handled? |
| Revocation SLA | Is the maximum access-cutoff delay defined and tested at Resource Servers? |
| Recovery | Are admin authorization, recovery challenges, MFA, and credential resets in place? |
| Abuse resistance | Are rate limits, atomic counters, and DoS-resistant lockout rules implemented? |
| Observability | Are audits keyed by immutable ID and logs scrubbed of sensitive data? |
| Testing | Are status flags, provider exceptions, OAuth requests, refreshes, sessions, and multi-node flows tested? |

## 13. Applied Exercise

You operate a shared Authorization Server for <code>sales-portal</code> and <code>reporting-ui</code>. Users sign in via form login and receive Authorization Codes and OIDC ID Tokens. Accounts live in PostgreSQL, authorizations/refresh tokens live in a separate store, and Resource Servers verify JWT access tokens offline.

1. Design the account table with <code>enabled</code>, <code>manually_locked</code>, <code>locked_until</code>, <code>account_expires_at</code>, <code>credentials_expires_at</code>, audit fields, and a stable primary identifier.
2. Write a <code>UserDetailsService</code> mapping all four <code>UserDetails</code> status methods accurately. Use <code>Clock.fixed(...)</code> to test instants before, equal to, and after <code>locked_until</code>.
3. When Bob enters a wrong password five times within one minute, propose an atomic counter policy, rate limiting, and safeguards against attackers intentionally locking Bob's account.
4. Bob logged in cleanly yesterday but is disabled today. Trace <code>GET /oauth2/authorize</code> while his session remains active and propose where to revalidate.
5. Bob already holds a refresh token. Explain why setting <code>enabled=false</code> alone is insufficient and choose a strategy to block refreshes and revoke authorizations.
6. The Orders API verifies JWTs offline only. Identify the window during which old tokens stay valid and propose a solution if access must be cut off within seconds.
7. Design a password-reset flow for <code>CredentialsExpiredException</code> that does not grant full OAuth permissions before Bob updates his password.
8. Write tests verifying locked, disabled, account-expired, and credentials-expired accounts cannot complete new logins, plus integration tests verifying status changes after a session and authorization code already exist.

A sound design answers **where account status is checked, when it changes, what gets revoked, how long propagation takes, and how errors are handled**.

## 14. Reference Documentation

- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): role of <code>UserDetailsService</code> and loading user records.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): username/password verification and <code>PasswordEncoder</code>.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): form login, failure handling, and login filters.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context, session lifecycle, and concurrency.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): authentication failure/success events and event publishers.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): storing credentials with secure password encoders.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): filter chains and OAuth 2.0/OIDC components.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>OAuth2Authorization</code>, authorization service, client registration, and consent.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code, token endpoint, and refresh tokens.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation and practical limitations.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): End-User authentication, ID Token, and relationship to OAuth 2.0.
