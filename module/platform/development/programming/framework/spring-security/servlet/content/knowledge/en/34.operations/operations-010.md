# Rotating Keys, Updating Permissions, Managing Accounts, and Access Revocation in Spring Security Servlet

## 1. Objectives and Operational Context

In Spring Security Servlet, a request may be authenticated via **HttpSession**, HTTP Basic, Bearer JWT, opaque tokens, OAuth2 login, API keys, or an identity assertion from a gateway. Rotating a key, reducing permissions, or disabling an account **does not automatically invalidate every previously issued access credential**. The system must have procedures to verify that access is actually revoked within the allowed time window.

Example: an administrator removes `ROLE_ADMIN` from `alice` in the database. If `alice` still holds an `HttpSession` storing the old `Authentication` with `ROLE_ADMIN`, or an unexpired JWT access token carrying the admin claim, an endpoint checking only authorities from the old `Authentication` **may still allow access**. Similarly, changing a password does not automatically destroy all session cookies, refresh tokens, or API keys.

Lesson objectives:
- Distinguish **JWT signing keys**, TLS/mTLS keys, OAuth2 client secrets, API keys, and passwords.
- Master **signing-key rotation, JWKS overlap, `kid`, and key retirement**, especially distinguishing scheduled rotation from a compromised key.
- Understand **roles/permissions/scopes**, enabled/disabled accounts, resource-level permissions, and propagation delay for permission changes.
- Distinguish **session invalidation**, **refresh-token revocation**, **JWT access-token revocation**, **opaque introspection**, and account deprovisioning.
- Design change runbooks, emergency revocation procedures, rollbacks, testing, and auditing.
- Apply Spring Security 6 on the Servlet stack, understand stateless JWT limitations, and run a Java 17 example showing how permissions and account state affect access.

**Operational principle:** A change is considered complete only when the actual access-granting paths have updated—not merely when the database or admin UI shows the new state.

## 2. Artifacts with Independent Lifecycles

| Artifact | Function | Where changes take effect |
| --- | --- | --- |
| **JWT signing key / JWK** | Signs and verifies JWT access tokens | Authorization Server, JWKS, Resource Server `JwtDecoder`, and key caches |
| **TLS/mTLS certificate** | Protects transport channel, identifies server/service | Truststore, keystore, certificate chain, certificate reload, TLS termination |
| **OAuth2 client secret** | Client authentication with Authorization Server | Client registration, service config, secret manager, token endpoint |
| **API key** | API call credential or service identifier | Lookup store, scopes, issuer, consumers, expiration/revocation |
| **Password** | Login credential | Identity provider, password encoder, password reset flow |
| **Role/GrantedAuthority** | Grants authorities in Spring Security | Authentication/authorities mapper, session, token claims, authorization rules |
| **Permission/scope** | Permission for actions/APIs | JWT scopes, server-side ACLs, method security, and policy engines |
| **User/service account** | Access principal | IAM directory, enabled/locked flags, ownership, sessions, grants, credentials |
| **HttpSession / cookie** | Maintains web login on the server | Session repository across one or more nodes, SSO, remember-me |
| **Access token** | Accesses resources at the Resource Server | JWT validation, introspection, or revocation layer |
| **Refresh token** | Requests new access tokens at the Authorization Server | AS revocation store, rotation, token family, and client |
| **Delegated grant** | Lets an app/service act under granted permissions | OAuth2 consent/grant, client authorization, third-party access |

**Changing one artifact does not automatically change another.** Rotating a TLS key does not revoke JWTs. Changing a password does not automatically clear sessions. Removing a role in the database does not guarantee active sessions updated their authorities. Revoking a refresh token does not necessarily invalidate existing access tokens immediately.

## 3. HTTP Flow and Control Points

~~~text
Client / Browser / Service
    |
    | Cookie / Authorization: Bearer / Basic / API key
    v
Gateway / Reverse Proxy / SSO
    |
    v
Spring Security FilterChainProxy
    |
    +-- SecurityContextHolderFilter
    +-- Authentication filter
    |     BasicAuthenticationFilter
    |     UsernamePasswordAuthenticationFilter
    |     BearerTokenAuthenticationFilter
    |
    +-- Provider / JwtDecoder / OpaqueTokenIntrospector
    |     verify password, token, or introspection result
    |
    +-- SecurityContext: Authentication + GrantedAuthority
    |
    +-- AuthorizationFilter / @PreAuthorize
    |     roles, scopes, policy
    v
Controller -> Service -> ACL / Repository
~~~

Changes take effect at different points:
1. **Key rotation:** takes effect when the decoder/verifier fetches keys and verifies the JWT **signature**.
2. **Permission downgrade:** takes effect when the provider/authorization layer loads **fresh permissions**. Authorities from old JWTs/sessions may remain unchanged.
3. **Disabling an account:** blocks **new logins** via `UserDetailsService`, yet an existing stateless JWT or active session does not necessarily re-check `isEnabled`.
4. **Token revocation:** requires both a revocation store and a verification check; if the API never checks that store, revoking has no effect at the API.
5. **Session invalidation:** prevents reusing the session cookie on subsequent requests per session-store semantics, without revoking independent Bearer tokens.
6. **Resource ACL changes:** the service must evaluate permissions against current resource state, not just global roles.

These boundaries must be documented in the application's **security contract**.

## 4. JWT Signing-Key Rotation: Zero-Downtime Workflow

### 4.1. Concepts

With asymmetrically signed JWTs, the **Authorization Server** holds the private signing key; the **Resource Server** uses public verification keys published in **JWKS**. A JWT header may include **`kid`**:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-b",
  "typ": "JWT"
}
~~~

**`kid` is a key-selection hint, not proof of trust.** The JWT must still be verified using a key from a managed JWKS/trust configuration, an allowlisted algorithm, and validators for **`iss`**, **`exp`**, **`nbf`**, and **`aud`**. Never treat an arbitrary client-supplied `kid` or JWK URL as a trust source.

### 4.2. Scheduled Key Rotation Steps

1. **Inventory:** identify issuer, JWKS URI, signing algorithms, Resource Servers trusting the issuer, maximum token TTL, clock skew, JWK caches/refresh intervals, client environments, and owners.
2. **Generate a new key** using KMS/HSM or secure secret storage. Restrict private key access; never commit to repositories or paste into tickets/logs.
3. **Publish the new public key** in JWKS while retaining the old public key. Verify Resource Servers see the new `kid`.
4. **Switch signing** on the Authorization Server to the new private key. New tokens must carry the new `kid` and valid signatures.
5. **Overlap verification:** during the validity window, Resource Servers accept tokens signed by both the old and new keys per policy.
6. **Wait for old tokens to expire:** calculate from the last signing timestamp under the old key plus max access-token lifetime, clock skew, and actual JWK caching. Never guess every token is 15 minutes.
7. **Retire the old public key** from the trusted set when allowed by policy; verify all nodes updated, then handle the old private key per retention/deletion policy.
8. **Test and audit** the entire change, including new keys, old keys during overlap, old keys post-retirement, unknown `kid`, wrong algorithm/signature, and JWKS outages.

~~~text
Time ----------------->

Trusted JWKS:   [A] -------- [A + B] ------------ [B]
Signing key:    [A] -------- [B] ---------------- [B]

JWT signed by A: issued ---- valid until exp ----- expired
JWT signed by B:              issued ------------- valid
~~~

**Overlap rule:** do not retire the old public key before valid tokens signed with it expire, unless performing **emergency revocation** or using a controlled replacement mechanism. Scheduled key rotation aims for both security **and** availability.

### 4.3. Compromised Keys Must Never Keep Normal Overlap

If a private signing key is or is suspected to be compromised, attackers can mint forged JWTs with valid signatures. Keeping that public key in trusted JWKS to avoid disruption leaves the door open for forged tokens.

Emergency runbook:
- Activate incident response; determine key scope, issuer, affected APIs, and potential exposure window.
- Stop signing with the old key; generate/use a clean new key.
- **Remove the compromised key from the trusted verification set** across all Resource Servers/gateways per emergency plan, handling caches and refreshes as well.
- Notify clients that old tokens may be rejected and must be re-acquired via secure login/token issuance.
- Revoke sessions, refresh tokens, or other client credentials when warranted by incident scope.
- Monitor 401 spikes, unknown `kid`s, JWKS refreshes, token validation errors, and anomalous access patterns.
- Preserve evidence, investigate, remediate, and conduct a post-incident review.

**Never roll back by re-accepting a compromised key.** Restore availability by safely re-issuing tokens/keys, never by dropping containment.

## 5. Key Rotation Does Not Automatically Revoke All JWTs

When a Resource Server performs offline JWT validation, it may keep the old public key cached and accept previously issued access tokens. Consequently:
- Unexpired, validly signed tokens with valid issuer/audience may still be accepted during overlap.
- If the old key is removed from trust while some nodes hold stale JWKS caches, revocation latency can differ from expectations.
- Revoking a refresh token does not invalidate already-issued access tokens if the API does not check revocation state.
- Key rotation is usually the wrong tool to revoke **one user**, because it impacts everyone else's tokens too.

Ways to control access tokens before `exp`:
- Short TTLs if the stale-permission window during that lifetime is acceptable.
- **`jti` denylist** for tokens with unique IDs, checked against shared state across all Resource Servers.
- **Account epoch/token version**, checked against server-side state per request or within an approved cache TTL.
- Opaque token **introspection** with the Authorization Server (and cache policy).
- Authorization service/gateway checking active account status and current ACLs/permissions.
- During widespread compromise, remove the signing key from trust rapidly per incident runbook.

No mechanism is free: state lookups add latency and dependency on availability; caches widen revocation delay; overly short TTLs increase refresh traffic. Measure and approve the trade-off.

## 6. Rotating Client Secrets, API Keys, and TLS/mTLS Keys

| Credential | Scheduled rotation path | Pitfalls |
| --- | --- | --- |
| OAuth2 client secret | Create new secret, update client, verify token requests, revoke old secret | AS may not support two active secrets concurrently; requires coordinated cutover |
| API key | Issue new key, migrate consumers, monitor, revoke old key | Keys shared across clients obscure ownership and complicate revocation |
| TLS certificate | Issue new cert, deploy chain/truststore, reload, test mTLS/TLS, retire old cert | SAN/chain/trust anchor drift across nodes |
| Signing private key | Generate, publish public JWK, switch signing, overlap, retire | Compromised keys must not keep normal overlap |
| Password | Reset per policy, force reauthentication if needed | Sessions, refresh/access tokens, and API keys are not automatically invalidated |

**Secrets must live in a proper secrets manager/KMS/HSM**, never committed to Java source, version-controlled YAML, images, or logs. API keys should be handled on the backend using safe constant-time/hashed comparisons with tracked owners, scopes, and expirations; avoid hardcoded plaintext.

If an OAuth2 AS accepts only one client secret at a time, schedule a planned cutover and availability plan instead of assuming old and new secrets always work together. With a **compromised secret**, never re-enable the old secret to roll back.

## 7. Changing Roles, Permissions, Scopes, and ACLs

Spring Security uses **`GrantedAuthority`** to represent authorities:
- **`hasRole("ADMIN")`** typically requires **`ROLE_ADMIN`**.
- **`hasAuthority("SCOPE_reports.read")`** matches that exact authority string.
- Resource Server JWTs can map `scope`/`scp` claims to **`SCOPE_`**-prefixed authorities via converters.
- Method security **`@PreAuthorize`** reads the current `Authentication`; it does not automatically know the database updated permissions.
- Resource ownership/tenant ACLs must still be enforced in the business layer.

**Changing the permission source differs from changing an already-created `Authentication`.** For example, `alice` has `ROLE_ADMIN` removed in IAM, yet:
- An existing `HttpSession` still holds a **`UsernamePasswordAuthenticationToken`** carrying `ROLE_ADMIN`.
- An existing JWT still holds role/scope claims signed by the AS before the removal.
- A policy cache still serves a stale check result.
- The user still holds equivalent privileges via group inheritance or another delegated grant.

Privilege-reduction procedure:
1. Verify requester/approver, identity + tenant + resource, and before/after permissions.
2. Check group hierarchies, inherited privileges, alternate service credentials, and delegated access.
3. Update the canonical permission source; log actor, reason, and timestamp.
4. Determine the **permission refresh mechanism**: session invalidation, token revocation, account epoch, policy cache invalidation, or dynamic ACLs.
5. Test the downgraded user against sensitive endpoints **using old sessions/tokens too**.
6. Verify users retaining permissions still operate normally.
7. Monitor 403/401s, data authorization, cache lag, and run post-change verification.

**Never re-grant privileges revoked for a security incident just to "fix" a 403 error.** Separate misconfigurations from security decisions.

### 7.1. Effective Propagation Latency

| Mechanism | Source of authorities | When do permission changes take effect? |
| --- | --- | --- |
| Form login + `HttpSession` | `Authentication` stored in session | May require session invalidation/refresh or dynamic policy checks |
| HTTP Basic + `UserDetailsService` | Provider loads user per auth, subject to caching | When user/authority source is re-read |
| Stateless JWT access token | Signed claims in token + converter | Old tokens keep claims until `exp`, unless checked against external revocation/ACLs |
| Opaque token | Introspection result from AS | Depends on AS state and introspection cache |
| API key | Key store and permission mapping | Depends on lookup/cache |
| ACL-based service authorization | DB/policy engine | Depends on transactions, replicas, and caches |

Operations teams must agree on a **revocation SLO**, e.g., "after disabling an account, sensitive requests with old credentials are rejected within N seconds". Spring Security has no fixed N; N comes from the threat model and system capabilities.

## 8. Disabled, Locked, Expired, and Deleted Accounts

An account can be:
- **Disabled:** barred from authentication due to offboarding or administrative action.
- **Locked:** temporarily locked due to brute force or a security incident.
- **Expired credentials:** must rotate credentials before logging in per policy.
- **Deleted/deprovisioned:** identity removed from the IAM source, while retention/audits and resource ownership still need handling.

`UserDetails` flags—**`isEnabled()`**, **`isAccountNonLocked()`**, **`isAccountNonExpired()`**, **`isCredentialsNonExpired()`**—are checked by some `AuthenticationProvider`s during **new logins**. However, a **Bearer JWT Resource Server** does not call `UserDetailsService` on every request by default, and an already-authenticated session may not re-check `isEnabled` without additional logic.

### 8.1. Offboarding Procedure

1. Verify identity ID, tenant/issuer, secondary accounts, and approvers.
2. Disable the IAM source or service identity and block issuing new credentials.
3. Revoke refresh tokens, OAuth2 grants, delegated authorizations, and remembered devices as appropriate.
4. Invalidate the user's `HttpSession`s across all relevant apps and session stores; handle remember-me tokens/SSO cookies.
5. Control already-issued JWT access tokens: TTL, denylist, epoch, introspection, or policy checks per revocation commitments.
6. Revoke user-owned API keys, personal access tokens, SSH/certificate credentials, and service integrations.
7. Remove roles/groups/ACLs, data permissions, tenant access, shared secrets, and delegated access.
8. Audit running jobs, scheduled jobs, queue consumers, and data ownership requiring handover.
9. Test with old credentials/sessions/tokens to confirm access is rejected across all nodes/ingresses.
10. Record audit proof of completion without logging raw secrets/tokens.

**Simply deleting the user record is not enough.** Old tokens, session caches, or an external gateway might still accept that identity.

## 9. Layers of Access Revocation

### 9.1. HttpSession and Cookies

With web form login/OIDC login, `SecurityContext` may be saved in the session. To revoke:
- Delete/invalidate server-side sessions in the proper repository across the cluster.
- When using Spring Session/shared stores, verify session-index mappings, TTLs, and behavior across every node.
- Verify whether local app logout must synchronize with IdP/SSO logout per business requirements.
- Revoke persistent remember-me tokens or other sessions.
- Account for in-flight requests started before invalidation: already-executed actions cannot automatically be rewound.

**Logging out on one browser does not log out every device.** Admin account disablement and remote session revocation need dedicated mechanisms.

### 9.2. JWT Access Tokens

JWTs are self-contained and signed. When an API verifies only signature, `iss`, `aud`, and `exp`, it **does not know** an account was disabled or a `jti` was revoked without additional server-side checks.

Options include:
- **`jti` denylist** storing revoked token IDs until `exp` in a distributed state store.
- **Token version/account epoch** compared against a canonical record to reject older-epoch tokens.
- Short TTLs + refresh controls with an accepted revocation window.
- Introspection instead of offline JWTs, or adding policy/introspection checks.
- Dynamic account/authorization checks in services for sensitive endpoints.

Never trust **`jti`, `sub`, `roles`, or `kid`** claims from a merely Base64-decoded JWT string **before verifying its signature and validators**. Revocation checks must run only after token validation succeeds.

### 9.3. Refresh Tokens, OAuth2 Grants, and OIDC Logout

Refresh tokens are governed by the **Authorization Server**. Revoking a refresh token prevents obtaining new access tokens, yet does not force every Resource Server to immediately reject existing access tokens.

If refresh-token rotation is supported, implement reuse detection and token-family revocation per IdP. OIDC front-channel/back-channel logout can help terminate sessions across multiple clients, though it **does not exist automatically in every deployment**.

Web apps using OIDC login may need to clear **both the local session and the IdP session**. App-local logout and global SSO logout are two distinct behaviors requiring an explicit contract.

### 9.4. Password Reset

Changing a password blocks future authentication with the old password. It **does not by default** invalidate session cookies, Bearer tokens, API keys, or other authorization grants. For password compromise, the runbook must also clear sessions, revoke refresh tokens/grants, check for anomalous activity, and enforce MFA/step-up per policy.

## 10. Spring Security Servlet: JWT Resource Server Configuration

In Spring Boot 3.x with Java 17, relevant dependencies include **`spring-boot-starter-security`** and **`spring-boot-starter-oauth2-resource-server`**. Example configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
~~~

**`example.test` is only a placeholder**; configure a real issuer and trusted metadata/JWKS before running. `JwtDecoder` verifies tokens using allowed keys and algorithms; issuer/expiry are covered by standard validation, while **API-specific audience must be validated per contract** if not already covered by a validator.

Example `SecurityFilterChain` (snippet, not a standalone file):

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/**")
                        .hasAuthority("SCOPE_reports.read")
                    .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
}
~~~

**`STATELESS`** means the API does not use `HttpSession` to keep `Authentication` across subsequent requests. It **does not automatically revoke old JWTs** after an account is disabled. CSRF configuration must match the actual authentication method: if browsers send credentials automatically via cookies/sessions, do not blindly disable CSRF.

### 10.1. Audience Validator

The illustrative snippet below belongs inside a `@Configuration` class with complete imports, Java 17/Spring Security 6. Reading issuer/audience from the environment is only for configuration injection; never hardcode production issuers in source.

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = System.getenv("JWT_ISSUER");
    String audience = System.getenv("JWT_AUDIENCE");
    if (issuer == null || issuer.isBlank()
            || audience == null || audience.isBlank()) {
        throw new IllegalStateException(
                "JWT_ISSUER and JWT_AUDIENCE must be configured");
    }

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceRule = token ->
            token.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    standard, audienceRule));
    return decoder;
}
~~~

**Note:** this is a `JwtDecoder` configuration snippet without full imports/class wrapper. It demonstrates **audience** and **issuer** validators, without account/`jti` revocation. If adding a validator querying a user-status/token-version store, define timeouts, caching, fail-closed behavior, cluster-wide consistency, and test with genuinely signed tokens.

## 11. Runnable Java 17 Example: Updating Permissions, Accounts, Tokens, and Keys

This example is a pure-Java **policy simulator**, not a real JWT implementation. It shows how **access decisions** change as the server updates permissions, account state, revocations, epochs, and trusted key IDs.

**Important:** the `Token` record below has no cryptographic signature and is created by the program itself. In a production API, never accept client-asserted subjects, `kid`s, `jti`s, or permissions and feed them into this logic. Every token must first pass `JwtDecoder`/issuer/audience validation or trusted introspection.

### 11.1. AccessLifecycleDemo.java

~~~java
import java.util.HashSet;
import java.util.Set;

public final class AccessLifecycleDemo {
    private AccessLifecycleDemo() {
    }

    // Trusted simulated data, NOT a real JWT.
    record Token(
            String jti,
            String subject,
            String kid,
            int epoch,
            long expiresAt,
            Set<String> permissionsAtIssue) {
    }

    static final class Account {
        boolean enabled = true;
        int epoch = 1;
        final Set<String> permissions =
                new HashSet<>(Set.of("reports.read", "reports.export"));
    }

    static final class Policy {
        final Account account = new Account();
        final Set<String> revokedIds = new HashSet<>();
        final Set<String> trustedKeys =
                new HashSet<>(Set.of("key-A"));
        String signingKey = "key-A";

        Token issue(String jti, long exp) {
            return new Token(
                    jti, "alice", signingKey, account.epoch, exp,
                    Set.copyOf(account.permissions));
        }

        String decide(Token token, String action, long now) {
            // Production must verify signature/issuer/aud first.
            if (!trustedKeys.contains(token.kid())) {
                return "DENY_KEY";
            }
            if (now >= token.expiresAt()) {
                return "DENY_EXPIRED";
            }
            if (!account.enabled) {
                return "DENY_DISABLED";
            }
            if (token.epoch() != account.epoch) {
                return "DENY_EPOCH";
            }
            if (revokedIds.contains(token.jti())) {
                return "DENY_REVOKED";
            }
            if (!account.permissions.contains(action)) {
                return "DENY_PERMISSION";
            }
            return "ALLOW";
        }
    }

    public static void main(String[] args) {
        Policy p = new Policy();
        long now = 100;

        Token first = p.issue("jti-001", 500);
        System.out.println("01 read=" +
                p.decide(first, "reports.read", now));
        System.out.println("02 export=" +
                p.decide(first, "reports.export", now));

        p.account.permissions.remove("reports.export");
        System.out.println("03 downgraded=" +
                p.decide(first, "reports.export", now) +
                "; oldClaimExport=" +
                first.permissionsAtIssue().contains("reports.export"));

        p.revokedIds.add(first.jti());
        System.out.println("04 revoked=" +
                p.decide(first, "reports.read", now));

        Token second = p.issue("jti-002", 500);
        System.out.println("05 newToken=" +
                p.decide(second, "reports.read", now));

        p.account.enabled = false;
        System.out.println("06 disabled=" +
                p.decide(second, "reports.read", now));

        p.account.enabled = true;
        p.account.epoch++;
        System.out.println("07 epochChanged=" +
                p.decide(second, "reports.read", now));

        p.trustedKeys.add("key-B");
        p.signingKey = "key-B";
        Token third = p.issue("jti-003", 500);
        System.out.println("08 rotated=" +
                p.decide(third, "reports.read", now));

        p.trustedKeys.remove("key-A");
        System.out.println("09 oldKeyRetired=" +
                p.decide(second, "reports.read", now));

        System.out.println("10 expired=" +
                p.decide(third, "reports.read", 500));
    }
}
~~~

### 11.2. Compile, Run, and Exact Stdout

Using JDK 17, save the code into **`AccessLifecycleDemo.java`**:

~~~bash
javac AccessLifecycleDemo.java
java AccessLifecycleDemo
~~~

The program prints:

~~~text
01 read=ALLOW
02 export=ALLOW
03 downgraded=DENY_PERMISSION; oldClaimExport=true
04 revoked=DENY_REVOKED
05 newToken=ALLOW
06 disabled=DENY_DISABLED
07 epochChanged=DENY_EPOCH
08 rotated=ALLOW
09 oldKeyRetired=DENY_KEY
10 expired=DENY_EXPIRED
~~~

Analysis:
- **01/02:** the first token is unexpired, the account is active, and server permissions are sufficient.
- **03:** the server removed `reports.export` so it denies access, even though the token snapshot from issuance still contains `reports.export`.
- **04:** the token ID is denylisted, so reading is blocked even though the token has not expired.
- **05:** the second unrevoked token still reads successfully.
- **06:** disabling the account causes immediate denial in the **policy simulator**.
- **07:** incrementing the account epoch invalidates older tokens, even after re-enabling the account.
- **08:** key B is added to the trusted set, `signingKey` switches to B, and a new token is issued.
- **09:** key A is retired; older tokens are rejected at the key ID check.
- **10:** a token with `exp=500` is rejected at `now=500`.

**Do not use this demo as a real security filter:** `trustedKeys` is just a `Set<String>` with no **cryptographic signature verification**; `Account` and `revokedIds` live inside a single JVM rather than a distributed store; `subject` is hardcoded with no authentication proof. In production, integrate trusted mechanisms into Spring Security authentication/authorization and enforce state consistency across all nodes.

## 12. Propagation Across Multi-Node Systems and Caches

To guarantee "revoked within N seconds", understand the latency components:
- Writing account disabled/role removed to the IAM/source store.
- Propagating events to application databases, replicas, or policy services.
- Deleting `HttpSession`s in the shared repository.
- Refreshing/updating JWT public keys and JWK caches.
- Updating the `jti` denylist/token-version store across every Resource Server.
- Invalidating authorization/permission caches in gateways and microservices.
- Time for in-flight requests to finish.

A 10-minute cache TTL **cannot meet a 30-second revocation target** without an invalidation mechanism. Yet checking state on every request can create bottlenecks and extra dependencies. Operations teams must define SLOs/reliability and outage handling explicitly.

**Fail closed:** if revocation status is mandatory to protect a sensitive API, lookup errors must not be interpreted as "token allowed". Approved degraded modes may apply to low-sensitivity routes, but never skip revocation checks automatically just to boost availability.

**Long-running jobs:** a previously scheduled task may keep acting under a service identity after the user is disabled. Store actor IDs, tenants/resources, enforce policy authorization at execution time, ensure idempotency, and audit; never synthesize authenticated tokens from caller-supplied usernames.

## 13. Standard Change Runbook

### 13.1. Before the Change

Clearly document:
- Scope: issuer, audience, key ID, account ID, client ID, tenants, endpoints, systems.
- Change type: scheduled rotation, compromised key, account offboarding, role downgrade, client-secret revocation.
- Requester, approver, system owner, and on-call engineer.
- Access revocation SLO, cutover/overlap timing if permitted.
- TTLs and cache/repository dependencies, plus safe rollback options.
- Positive/negative test plan, observability, and alerting.

**Never deploy a rotation without knowing who still uses the old key/secret.** An uninventoried client can break or keep using a revoked credential.

### 13.2. During the Change

1. Use official secrets-management channels; never paste private keys or passwords in chat.
2. For normal rotations: publish the new trust anchor before cutting over signing/consumers.
3. For compromises: contain rapidly and block continued use of exposed credentials.
4. For role/account revocations: update the identity source and revoke tokens/sessions/grants/caches per contract.
5. Run canary and per-node/region verification; do not rely solely on an IAM dashboard saying "disabled".
6. Monitor 401/403/login/refresh errors, JWKS validation, token usage, and access-denied events.
7. If an outage occurs, diagnose root cause and roll back **only if it does not re-grant credentials/privileges revoked for an incident**.

### 13.3. After the Change

- Run negative tests with old credentials to prove they are rejected per policy.
- Run positive tests with new credentials/authorized identities to prove valid flows still work.
- Verify session stores, AS refresh-token stores, denylists/epochs, and gateway caches.
- Check scheduled jobs, service integrations, delegated grants, and data ownership.
- Record audit timestamp, actor, action, scope, verification results, ticket/reference, and verified systems.
- Never log raw access tokens, refresh tokens, private keys, passwords, Authorization headers, or cookies.

## 14. Emergency Revocation on Suspected Compromise

**Containment:** assess blast radius, halt issuing new credentials, disable compromised accounts/services, revoke tokens/sessions/grants, block compromised keys at verifiers, and restrict high-risk endpoints.

**Investigation:** examine exposure timing and scope, IAM changes, IP/device signals, token usage by verified IDs, exercised permissions, background jobs, and potentially accessed data.

**Recovery:** issue new keys/credentials, confirm all clients/Resource Servers updated, re-enable accounts only after verification and approval, and require MFA/step-up if needed.

**Review:** measure time-to-detect, time-to-disable, time-to-revoke, cache propagation, and token/session lifetimes, then update playbooks. A system still accepting old tokens past its revocation SLO is a defect to fix, not just an alert.

Do not delete audit trails when deleting accounts if retention policies require keeping records for investigation; apply masking/minimization per data policy.

## 15. Test Matrix for Keys, Permissions, Accounts, and Revocation

| Case | Expected |
| --- | --- |
| JWT signed by new key, valid issuer/aud/exp/scope | Accepted at APIs with matching permissions |
| Old key still in normal overlap, token unexpired | Accepted if permitted by policy |
| Old key retired | Old tokens rejected once verifiers/caches update |
| Compromised key revoked | All verifiers reject tokens from the affected key |
| Unknown `kid`, bad signature/alg, wrong issuer/aud/exp | 401; never trust arbitrary keys |
| Active user, right role, resource owned by user | 200 and owner-appropriate body |
| Missing role/scope or removed ACL | 403 or matching policy response; no data leaked |
| `ROLE_ADMIN` just removed, old session still alive | Admin privileges blocked within revocation SLO |
| Disabled account, new login | Rejected per mechanism |
| Disabled account, unexpired JWT | Blocked **if** required by contract with stateful revocation |
| Refresh token revoked | Cannot obtain new tokens from AS |
| `jti` added to denylist | That token rejected across all Resource Servers |
| Account epoch incremented | Older-epoch tokens rejected during policy check |
| Retired API key/client secret | Old credential no longer authenticates |
| Session invalidated | Session cookie can no longer access protected endpoints |
| IdP/JWKS/revocation store failure | Designed fail-closed or degraded behavior |
| Multiple nodes/regions, cache latency | Revocation SLO met on every node |

**Layered testing:** unit-test policies, integration-test decoders with real signed tokens, HTTP-test through Spring Security `FilterChainProxy`, E2E-test through gateway/IdP/session stores, and test object-level permissions. MockMvc with **`.with(jwt())`** or **`@WithMockUser`** creates fake `Authentication` objects—**it does not verify key rotation, signatures, or real token revocation**.

Example MockMvc authorization test (snippet, requiring matching controller and imports):

~~~java
mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other.read"))))
    .andExpect(status().isForbidden());
~~~

To test signing-key rotation, test a real `JwtDecoder` with tokens signed by test key pairs and a controlled JWKS. Test key A before cutover, A+B during overlap, retiring A, unknown `kid`, bad signatures, and caching. To test account revocation, test the shared state store and real HTTP path; merely editing a mock principal in a test does not prove account disablement works.

## 16. Metrics, Logging, and Auditing

Observe:
- 401/403 counts by endpoint/issuer/client/verified `kid` where available and safe.
- JWKS fetch/refresh errors, key cache age, and tokens still using old `kid`s after retirement.
- OAuth2 token refresh failures, `invalid_client`, `invalid_grant`, login errors.
- Invalidated session counts and distributed session store errors.
- Revocation denylist/epoch lookup latency, outages, and propagation lag.
- Time from account disablement/role downgrade until old requests are rejected on every node.
- Rate of admin privileges still exercised after downgrade; resource-ownership anomalies.
- Events from offboarded users, revoked `jti`s, and revoked API keys.

Illustrative audit event example, not a real executed event:

~~~json
{
  "event": "ACCESS_REVOKED",
  "identity": "tenant-A:alice",
  "changeType": "ACCOUNT_DISABLED",
  "actor": "iam-operator-17",
  "approvedChange": "CHG-123",
  "verifiedSystems": ["idp", "web-session", "api"],
  "result": "VERIFIED"
}
~~~

Record `VERIFIED` only with **test evidence**. Audits must enforce access controls, retention, and exclude raw tokens, passwords, client secrets, session cookies, or private keys.

## 17. Common Mistakes

1. **Changing a password logs out all devices.** Not by default: sessions/JWTs/refresh tokens may remain active.
2. **Deleting a user immediately revokes JWTs.** False if Resource Servers only validate tokens locally without checking account status.
3. **Removing a role updates every existing `Authentication`.** False; `HttpSession`/JWTs may hold old authorities.
4. **Revoking a refresh token instantly revokes access tokens.** Not necessarily; Resource Servers need their own check.
5. **Rotate to a new key and immediately delete the old key in every case.** Scheduled rotations usually need TTL-based overlap.
6. **Keep overlap on a compromised key to avoid disruption.** Dangerous: attackers can still sign forged tokens.
7. **`kid` proves the signature.** False; `kid` only selects a key from the trusted set.
8. **A valid JWT signature is sufficient for authorization.** False if `issuer`/`aud`/`exp`/`scope`/account/ACLs fail.
9. **Passing mock JWT tests means revocation is tested.** False; mock tests skip real signed-token verification.
10. **One node reporting revocation succeeded means the cluster succeeded.** False if session/JWK/permission caches are out of sync.
11. **Local browser logout revokes tokens on all other devices.** Not by default.
12. **Restoring an exposed key to roll back an incident.** Unsafe.
13. **Printing raw tokens to logs for debugging.** Creates a second leak channel.
14. **403 always means permissions were revoked.** Could be CSRF or another policy; inspect the chain and root cause.
15. **Checking only the IAM database to confirm.** Insufficient; test requests against all real systems.

## 18. Safe Deployment Checklist

- [ ] Maintain an inventory of keys, token issuers, client credentials, APIs, owners, TTLs, and caches.
- [ ] Distinguish scheduled key rotation from security incidents with separate runbooks.
- [ ] Keep private signing keys and client secrets out of source, logs, and tickets.
- [ ] Validate JWT signatures, algorithms, issuers, expiration, and API-specific audience.
- [ ] Follow publish/switch/overlap/retire timelines for JWKs and measure cache refreshes.
- [ ] Maintain dedicated procedures for OAuth2 client secrets, API keys, and TLS/mTLS certificates.
- [ ] Manage roles/permissions at a canonical source and enforce least privilege.
- [ ] Enforce ownership/tenant/ACL checks, not just broad JWT scopes.
- [ ] Define SLOs for revoking accounts and sensitive permissions.
- [ ] Implement mechanisms to invalidate sessions/remember-me and revoke refresh tokens/grants.
- [ ] For stateless JWTs, define explicit TTL/revocation-state/epoch policies.
- [ ] Revoke user-owned secondary credentials, delegated access, and scheduled jobs.
- [ ] Test old/new tokens, invalid signatures/`kid`/`aud`, role downgrades, disabled accounts, and `jti` revocation.
- [ ] Test across multiple nodes/regions and cache/revocation store failures.
- [ ] Use canaries, alerts, approvals, and rollbacks that never restore keys/privileges revoked for compromise.
- [ ] Audits store verification evidence without raw secrets/tokens.

## 19. Self-Check Questions

1. **Does rotating a signing key automatically revoke old tokens?** Not if verifiers still trust the old key and tokens have not expired.
2. **Why does scheduled rotation need overlap?** So valid tokens signed by the old key can expire safely.
3. **Should a compromised private signing key keep overlap?** No; contain immediately and remove trust on an emergency basis.
4. **Does disabling a user in `UserDetailsService` block existing stateless JWTs?** Not by default; check status/revocation at the Resource Server or an appropriate control point.
5. **Does removing `ROLE_ADMIN` automatically update old `HttpSession`s?** Not by default; you may need session invalidation/refresh or dynamic permission checks.
6. **Does revoking a refresh token immediately expire JWT access tokens?** Not necessarily.
7. **Where should a `jti` denylist live in a cluster?** In a trusted shared state store with matching TTL/consistency.
8. **Should a validly signed JWT with an audience for another API be accepted?** No.
9. **Why is `.with(jwt())` not a key-rotation test?** It mocks `Authentication` without verifying real signatures/JWKS.
10. **What evidence does successful offboarding require?** New logins, refreshes, old sessions/tokens, and all alternate credentials are handled per the revocation contract.
11. **What if the revocation store errors?** Follow the approved fail-closed/degraded policy rather than silently granting access.
12. **Why never roll back with a compromised key?** Doing so restores the attacker's ability to forge tokens.

**Conclusion:** In Spring Security Servlet, key, permission, and account changes are complete only when **every legacy access path is controlled per its lifecycle and target revocation SLO**. Treat JWKS/signing-key rotation, JWT/opaque tokens, `HttpSession`, refresh tokens, roles, account state, and resource authorization as distinct layers; test old tokens/sessions across multiple nodes; audit accurately; and maintain containment runbooks for real incidents.
