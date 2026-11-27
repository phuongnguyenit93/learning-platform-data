# Policies for Locked Accounts, Compromised Credentials, and Hijacked Sessions

An Authorization Server must handle three scenarios that are often conflated: an account is no longer allowed to sign in, credentials have been exposed, and an active login session is being used by someone else. Each scenario affects a different layer. Locking an account prevents new authentications; revoking an authorization grant invalidates tokens issued from that grant; terminating sessions clears browser login state. Performing one action does not automatically complete the other two.

This lesson establishes incident-handling policies for Spring Boot applications using Spring Security and Spring Authorization Server. Examples focus on end users signing in via Authorization Code and OpenID Connect. For client credentials, service accounts, or server signing keys, apply dedicated policies tailored to each credential type.

## 1. Distinguishing Security States

Before writing code, identify which resource is being protected and which operation alters its state.

| Component | Examples | How it is controlled |
|---|---|---|
| Account | `ACTIVE`, `LOCKED`, `DISABLED` | State in the user store; checked during authentication |
| Credential | Password, passkey, recovery codes, client secret | Revoke or replace the credential; re-verify identity |
| Login session | SSO session cookie, `HttpSession`, session stored in Spring Session | Expire or delete the session in the session store |
| Authorization grant | Permissions a user granted to a client | Delete or mark the authorization invalid |
| Access token | JWT or reference token | Revoke, introspect, denylist, or wait for expiration per policy |
| Refresh token | Credential used to obtain new access tokens | Revoke and detect reuse of rotated tokens |
| Signing key | Private key signing access tokens or ID Tokens | Rotate key, remove compromised key from trusted key set |

A user can be locked in the database while still holding a valid SSO cookie. A refresh token can remain usable after a password change if the application fails to revoke old grants. A signed JWT can continue being accepted by a Resource Server even after the Authorization Server deletes the authorization record if the Resource Server verifies only the JWT's signature and expiration.

Therefore, policies must define exact impact scope:

- **Prevent new authentications:** account locked or disabled.
- **Prevent new token issuance:** reject authorization requests and refresh grants when the account is ineligible.
- **Terminate sessions:** invalidate the SSO session and associated application sessions.
- **Revoke granted permissions:** invalidate authorization grants, refresh tokens, and access tokens per token strategy.
- **Secure recovery:** verify the user, replace credentials, and require re-authentication.

## 2. Account Lockout Policy

### 2.1. Distinguish Temporary Lockouts from Incident Lockouts

Do not represent every scenario with a single boolean flag. An account model should store at least status, lock reason, and lock timestamp:

| Field | Meaning |
|---|---|
| `status` | Account state such as `ACTIVE`, `LOCKED`, or `DISABLED` |
| `lockReason` | `FAILED_ATTEMPTS`, `SUSPECTED_COMPROMISE`, or `ADMINISTRATIVE` |
| `lockedAt` | Timestamp when the lock began |
| `lockedUntil` | Automatic unlock timestamp; `null` can indicate a lock requiring authorized manual intervention |
| `failedAttempts` | Count of failed authentication attempts in the tracking window |
| `securityVersion` | Security version incremented after incidents or credential changes |
| `passwordChangedAt` | Timestamp of the most recent password change |

Lockouts caused by repeated wrong passwords are typically temporary. Lockouts triggered by suspected credential compromise must persist until verification and recovery complete. Never automatically unlock an account under investigation merely because a temporary lockout timer expired.

### 2.2. Connecting Account State to Spring Security

Spring Security models core user account conditions via `UserDetails`, including `isAccountNonLocked()`, `isEnabled()`, and `isCredentialsNonExpired()`. Default implementations may return `true`; therefore, database-backed implementations must map real persisted state accurately.

Condensed example:

```java
public final class AccountPrincipal implements UserDetails {

    private final Account account;

    public AccountPrincipal(Account account) {
        this.account = account;
    }

    @Override
    public String getUsername() {
        return account.username();
    }

    @Override
    public String getPassword() {
        return account.passwordHash();
    }

    @Override
    public boolean isAccountNonLocked() {
        return !account.isLocked();
    }

    @Override
    public boolean isEnabled() {
        return account.isEnabled();
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return !account.areCredentialsExpired();
    }

    // Implement getAuthorities() according to application permissions.
}
```

`account.isLocked()` must enforce lockout expiration rules accurately. If a temporary lockout has expired, a service should update the status in a controlled transaction before permitting login. Never leave a lock expired in memory while remaining `LOCKED` in the database.

When using `DaoAuthenticationProvider` with `UserDetailsService`, Spring Security checks account state during authentication. If using a custom authentication provider, ensure equivalent checks for locked, disabled, and expired credentials are enforced. See [Spring Security UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html).

### 2.3. Defending Against Brute Force Without Enabling Denial of Service

Locking accounts after repeated failures limits password guessing, yet counting solely by username can be abused to lock out victims. Combine controls:

- Multi-dimensional rate limiting: account, network address, device, or client; never rely solely on IP.
- Progressive delays after consecutive failures.
- CAPTCHA or additional verification steps as risk signals rise.
- Generic login failure messages to avoid leaking whether usernames exist or why an account is locked.
- Event logging and alerts when many accounts are probed from the same source.
- Reset counters per policy only after successful authentication or a verified recovery workflow.

Counter increments must be safe under concurrent requests. Use atomic updates or database row locking so two concurrent requests cannot read the same count and overwrite each other.

### 2.4. Locking an Account Does Not Automatically Revoke Sessions and Tokens

When an account transitions to `LOCKED`, Spring Security rejects new authentications provided state is mapped accurately. However, that status does not delete an existing `SecurityContext` stored in `HttpSession`, nor does it invalidate already-issued access tokens.

Define actions by cause:

- Temporary lockout from wrong passwords: may block only new logins while monitoring active sessions. If additional hijacking signals appear, escalate to the incident workflow and revoke sessions/tokens.
- Lockout from suspected credential compromise: lock the account, terminate sessions, and revoke all user grants.
- Administrative lock or permanent deactivation: block new authentications and apply grant revocation policies matching administrative requirements.

When using refresh tokens, ensure the refresh grant also checks current account status and revoked authorizations. Do not assume `UserDetails` checks from initial login re-run automatically on every refresh. Spring Authorization Server lets you customize token-endpoint providers via `OAuth2TokenEndpointConfigurer.authenticationProviders(...)`; use this extension point to verify account status and `securityVersion` before minting new tokens.

## 3. Handling Compromised Credentials

### 3.1. Identify Which Credential Was Compromised

"Compromised credential" can refer to several distinct secrets. Identify the credential type before choosing actions.

| Compromised credential | Priority actions |
|---|---|
| User password | Lock or mark account for recovery; reset password; revoke sessions and grants per policy |
| Passkey or device authentication key | Revoke affected credential; require re-enrollment after verification |
| Recovery code or backup MFA code | Invalidate remaining codes in the set; issue a new set after verification |
| Refresh token | Revoke the authorization grant holding the token; check for replay signs and related access tokens |
| Access token | Revoke token or grant; assess remaining lifetime and Resource Server status-check capability |
| Client secret | Disable or rotate the client's secret; revoke authorizations issued to the client if at risk |
| Private signing key | Emergency signing key rotation; remove compromised key from accepted keys; handle key caches and tokens signed by old key |

Client credentials and Authorization Server signing keys have wider blast radii than a single user account. Never treat a client secret incident by merely locking the user who owns that client. For a compromised private signing key, coordinate updating JWKS, `kid`, Resource Server caches, and acceptance policies for older tokens.

### 3.2. Exposed Password Remediation Workflow

A recovery workflow should execute in this order:

1. Flag the account for incident handling and block new authentications.
2. Verify the requester via an independent channel, such as MFA or an identity-verified support workflow.
3. Revoke active SSO sessions and authorization grants per incident severity.
4. Require setting a new password; enforce password policy and block known-breached passwords if checking sources are available.
5. Revoke or replace recovery codes, trusted devices, and secondary credentials that may also be compromised.
6. Increment `securityVersion`, record an audit event, and require re-authentication across devices.
7. Monitor failed refresh attempts, new-device logins, and anomalous activity post-recovery.

Passwords must be stored only using appropriate hashes. With Spring Security, use `PasswordEncoderFactories.createDelegatingPasswordEncoder()` to construct a `DelegatingPasswordEncoder`; it records an encoder identifier alongside the hash and supports upgrading algorithms over time.

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Never use reversible encryption for passwords to recover plaintext. Never log passwords, tokens, MFA codes, session cookies, or `Authorization` headers. See [Spring Security Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html).

### 3.3. Refresh Token Rotation and Mitigating Replay

Refresh tokens are high-value because they mint new access tokens. For public clients, [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html) requires Authorization Servers to detect replay via sender-constrained refresh tokens or refresh token rotation. With rotation, each refresh issues a new token and invalidates the old one; if an old token reappears, the server gets a signal of potential cloning.

In Spring Authorization Server, disable refresh token reuse:

```java
TokenSettings tokenSettings = TokenSettings.builder()
    .reuseRefreshTokens(false)
    .build();
```

Set short access token lifetimes matched to risk, restrict scopes and audiences, and protect refresh tokens in transit and at rest. RFC 9700 also recommends sender-constrained access tokens, such as DPoP or mutual TLS, to reduce the utility of stolen tokens.

## 4. Revoking Authorization Grants and OAuth Tokens

### 4.1. Using the Token Revocation Endpoint

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html) defines OAuth 2.0 Token Revocation. A client sends an HTTP POST to the revocation endpoint, authenticates per client configuration, and submits the token to revoke. The Authorization Server verifies the token belongs to the requesting client and invalidates it. The RFC mandates supporting refresh token revocation and recommends supporting access token revocation. When a refresh token is revoked, if the server supports access token revocation, it should also revoke access tokens derived from the same grant.

Spring Authorization Server provides `OAuth2TokenRevocationEndpointConfigurer` to configure the endpoint and extension points for converters, providers, and response handlers. Use the standard endpoint when a client revokes its own tokens. For administrative actions like user lockouts or incident response, invoke an appropriately authorized internal service to revoke the principal's authorizations rather than impersonating an external client.

Example request per RFC 7009:

```http
POST <revocation_endpoint>
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token>&token_type_hint=refresh_token
```

Obtain the endpoint URL from Authorization Server Metadata or published configuration rather than hard-coding arbitrary URLs. A successful response from the revocation endpoint does not permit the client to continue using the token; the client must purge the token from its own storage.

### 4.2. Revoking Authorizations in Spring Authorization Server

`OAuth2Authorization` represents an authorization grant and links the tokens issued under that grant. `OAuth2AuthorizationService` persists and queries authorizations, exposing `findByToken`, `findById`, `save`, and `remove`.

Example revoking an entire grant located via a compromised refresh token:

```java
@Service
public class AuthorizationRevocationService {

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationRevocationService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    public void revokeGrantByRefreshToken(String refreshToken) {
        OAuth2Authorization authorization = authorizationService.findByToken(
            refreshToken,
            OAuth2TokenType.REFRESH_TOKEN
        );

        if (authorization != null) {
            // Removing the authorization deletes the grant record and its associated tokens.
            authorizationService.remove(authorization);
        }
    }
}
```

For a user-level incident, multiple grants across multiple clients often must be revoked. `OAuth2AuthorizationService` does not provide a query for all authorizations by `principalName`. Applications should maintain a dedicated principal index/repository or implement an authorization persistence service supporting that query. When saving an authorization, index by `OAuth2Authorization.getPrincipalName()`; when deleting an authorization, update the index within the same transaction boundary. The revocation workflow can then fetch the principal's authorization IDs, call `findById`, and `remove` each record.

Never use `InMemoryOAuth2AuthorizationService` in production for multi-instance systems or systems requiring durable state. Spring Authorization Server provides `JdbcOAuth2AuthorizationService`; use the JDBC implementation or a durable persistence implementation matching your architecture. See [Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html) and [Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html).

### 4.3. JWTs and the Limits of Immediate Revocation

Choose a token verification strategy based on revocation requirements:

| Verification approach | When grant is revoked | Trade-off |
|---|---|---|
| Reference/opaque token + introspection | Resource Server observes token is no longer active once introspection reads fresh state | Network overhead; introspection caching introduces revocation lag |
| Self-contained JWT checking only signature and `exp` | Already-issued JWTs may remain valid until expiration | Fast verification, minimal runtime coupling to Authorization Server |
| JWT + `jti` denylist | Resource Server rejects tokens whose `jti` is in the denylist | Must share revocation state and prune entries upon expiration |
| JWT + `securityVersion` check | Resource Server rejects tokens carrying an older version | Requires looking up or caching account version per request |

If immediate access token revocation is required during incidents, deleting the authorization record in the database alone is insufficient for Resource Servers validating JWTs completely offline. Implement a denylist or security-version check on Resource Servers, or use reference tokens with introspection. For introspection, [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html) defines the `active` field; expired, revoked, or unauthorized tokens for a resource server must return inactive. Keep cache lifetimes short enough to meet your acceptable revocation latency.

If choosing offline JWTs, keep access token TTLs short and narrow scopes/audiences to limit exposure if leaked. Document clearly in policy that JWTs remain valid until `exp` without an online revocation check. Never advertise "instant logout" when Resource Servers have no channel to learn revocation state.

## 5. Handling Hijacked Login Sessions

### 5.1. Browser Sessions and Tokens Are Distinct States

An Authorization Server's SSO session is typically maintained in `HttpSession` or a shared session store. A client application can simultaneously hold its own login session. Access tokens and refresh tokens have yet another independent lifecycle. Consequently, "logging out of the Authorization Server" does not automatically guarantee every client cleared its own session or every Resource Server rejected access tokens.

When a session hijack is confirmed:

- Identify the session ID, principal, client, timeframe, and related authorizations.
- Flag the session as compromised and terminate it in the session store.
- Revoke refresh tokens/grants linked to the session or principal per incident scope.
- Revoke access tokens if the token strategy allows; for offline JWTs, apply denylists/version checks or wait out TTL per response plan.
- Require re-authentication and MFA before establishing a new session.
- Notify the user via a verified channel and record an audit event.

Never treat a single IP address change as sole proof of session hijacking. Evaluate device, user-agent, approximate location, timing, credential changes, and access patterns together.

### 5.2. Managing HttpSession with Spring Security

Spring Security supports tracking sessions via `SessionRegistry` and limiting concurrent sessions. Concurrent-session configuration typically registers `HttpSessionEventPublisher` and sets limits in `sessionManagement`:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}

@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    http.sessionManagement(session ->
        session.maximumSessions(5)
    );
    return http.build();
}
```

The limit `5` is illustrative; choose a cap suited to your application's usage model. When expiring sessions for an identified principal, mark them expired via `SessionRegistry`:

```java
public void expireSessions(
        SessionRegistry sessionRegistry,
        Object principal) {

    sessionRegistry.getAllSessions(principal, false)
        .forEach(SessionInformation::expireNow);
}
```

`expireNow()` marks the session as expired. Spring Security's session management filter enforces expiration on the next request hitting the application. If sessions must be deleted immediately even without another request arriving, use the underlying session store's delete API—such as a shared Spring Session repository—and confirm the session ID is gone.

The default `SessionRegistryImpl` stores data in a single instance's memory. Across multiple nodes, use a shared session registry/session store or broadcast revocation events to every node. With custom `UserDetails`, implement stable `equals()` and `hashCode()` so `SessionRegistry` identifies principals reliably. See [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).

### 5.3. OpenID Connect Logout

Spring Authorization Server can enable OIDC and configure `OidcLogoutEndpointConfigurer` for RP-Initiated Logout:

```java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(Customizer.withDefaults())
);
```

This endpoint handles logout requests from Relying Parties. By default, the provider uses `SessionRegistry` to locate the End-User's session information. On clients using Spring Security OAuth2 Client, `OidcClientInitiatedLogoutSuccessHandler` supports initiating RP-Initiated Logout.

Per [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html), the Authorization Server must verify `id_token_hint` if sent and redirect only to an exact registered `post_logout_redirect_uri`. Never accept arbitrary redirect URLs supplied by requests.

RP-Initiated Logout, Front-Channel Logout, and Back-Channel Logout are related mechanisms with distinct purposes. RP-Initiated Logout asks the OP to end its session; Front-Channel/Back-Channel Logout propagate logout notifications from the OP to RPs. To terminate local sessions at individual clients, those RPs must support and handle the corresponding logout mechanism. OIDC logout also does not replace revoking OAuth authorization grants when incident policy requires token revocation.

## 6. Decision Matrix by Incident Type

| Incident | Account | SSO session | Authorization grant/token | Recovery conditions |
|---|---|---|---|---|
| Failed passwords exceed threshold | Temporary lock, rate-limit retries | Monitor; terminate only if hijacking signals appear | Usually kept unless compromise indicators exist | Lockout timer expires or additional verification |
| Suspected password compromise | Lock or mark requiring verification | Terminate all user sessions | Revoke grants and refresh tokens; handle access tokens by token type | Reset password, verify MFA and secondary credentials |
| Refresh token replay | Optionally lock account depending on severity | Terminate affected or all sessions | Revoke grant holding the refresh token and linked tokens | Re-authenticate and issue new grants |
| Stolen cookie/session | May stay `ACTIVE` if isolated to one session; lock if broad | Terminate affected session IDs | Revoke tokens tied to session; widen if scope unclear | MFA and establish new session |
| Client secret exposure | Not necessarily lock users | Not necessarily terminate user sessions | Disable/rotate secret and revoke client grants | Update client secret and verify connectivity |
| Private signing key compromise | Not necessarily lock all users | Evaluate by scope | Rotate key, remove exposed `kid` from accepted set, handle old tokens | Resource Servers have adopted new key policy |

This matrix is a baseline. Organizations must define who may lock/unlock accounts, who may revoke grants, which severity levels mandate terminating all sessions, and maximum propagation SLAs for revocation state to reach Resource Servers.

## 7. Designing the Incident-Handling Workflow

Consolidate actions into a domain service rather than letting controllers update multiple tables directly:

```text
SecurityIncidentService
  ├── lockAccount(reason, until)
  ├── revokeBrowserSessions(principal)
  ├── revokeAuthorizations(principal, clientScope)
  ├── rotateOrInvalidateCredentials(principal, credentialType)
  ├── requireReauthentication(principal)
  └── writeAuditEvent(incidentId, actor, target, reason)
```

Typical execution flow:

1. **Triage:** identify affected principals, credentials, sessions, clients, and tokens; assign an incident ID.
2. **Stop new privilege issuance:** update account/client status and block refresh grants based on updated state.
3. **Revoke:** delete sessions and authorizations per chosen scope; publish events to nodes and Resource Servers that need to know.
4. **Rotate credentials:** reset passwords, rotate client secrets, MFA credentials, or signing keys as required.
5. **Recover:** verify identity, require MFA, and issue fresh sessions/grants.
6. **Monitor:** watch for refresh token reuse, failed logins, new devices, and post-revocation rejected requests.

Operations should be idempotent: re-running the same incident handler must not mint extra tokens, accidentally unlock accounts, or resurrect revoked sessions. Across distributed services, use a transactional outbox or durable event publishing so lockouts, grant revocations, and node notifications are not lost during transient service outages.

Audit events should include incident ID, actor, target principal/client, action type, reason, timestamp, request/correlation ID, and outcome. Never log raw passwords, raw access/refresh tokens, session cookies, client secrets, or private keys. If token correlation is needed, record a safe identifier such as a token hash or `jti` alongside issuer and expiration.

## 8. Testing Policies

Test happy paths, failure paths, and propagation latency. Minimum test cases include:

- A `LOCKED` account cannot complete login even with the correct password.
- A `DISABLED` account cannot obtain new authorization codes.
- A locked account cannot exchange a refresh token for a new access token.
- Temporary locks expire per policy; incident locks never auto-unlock.
- A revoked refresh token cannot be reused; linked authorizations are handled per policy.
- Introspection returns `active=false` for revoked or expired tokens.
- Offline-JWT Resource Servers reject revoked tokens via denylist/version checks, or operational docs explicitly state tokens expire only at `exp`.
- Sessions marked expired are rejected on the next request; with a shared session store, every node sees the session deleted.
- OIDC logout from a valid client terminates the OP session; unregistered post-logout redirect URIs are rejected.
- Password changes or credential rotations increment `securityVersion` and enforce the expected revocation scope.
- Replaying the same incident remediation leaves state consistent with no unintended side effects.

You can test endpoints with MockMvc and services with mock repositories, but integration tests must use the same authorization/session storage type as production. In particular, a test running only on `InMemoryOAuth2AuthorizationService` does not prove that multiple production instances synchronize revocation state.

## 9. Operational Checklist

- [ ] Separate policies exist for temporary locks, suspected-compromise locks, and account deactivation.
- [ ] `UserDetails` accurately maps `isAccountNonLocked()`, `isEnabled()`, and `isCredentialsNonExpired()`.
- [ ] Login, authorization requests, and refresh grants all check current security state.
- [ ] Procedures exist to revoke SSO sessions, authorization grants, refresh tokens, and access tokens.
- [ ] Offline-JWT revocation limits and introspection cache lag are explicitly documented.
- [ ] Production uses durable, cross-instance synchronized authorization and session stores.
- [ ] Refresh token rotation or sender constraining is configured appropriately per client type.
- [ ] OIDC logout redirects only to registered URIs and RPs handle logout notifications properly.
- [ ] Credentials never appear in logs, traces, exceptions, or audit events.
- [ ] Designated owners approve unlocks and confirm post-incident recovery.

## 10. References

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html)
