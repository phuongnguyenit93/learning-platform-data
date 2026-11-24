# Anomalous Login Detection and Access Revocation Workflows

## 1. Why Can a Successful Login Still Be a Security Incident?

Spring Security can verify a valid password, OTP, passkey, or Bearer token, yet that **does not prove the person acting is the legitimate account owner**. For instance, an attacker might hold a leaked credential, stolen refresh token, or hijacked session cookie; signature/token checks still succeed. Applications need a **risk monitoring** layer (anomalous login detection) and an **access containment/revocation workflow** independent of credential verification logic.

This lesson belongs to the **Operations** section of **Spring Security - authentication**, focusing on behavior **during and after authentication**:

1. Collect signals from the right control points: successful/failed logins, MFA challenges, token refreshes, session activity, and security changes.
2. Detect anomalies while accounting for false positives: new devices, guessing velocity, risky IPs/ASNs, impossible travel, MFA fatigue, refresh token reuse, and account takeover signals.
3. Score risk to choose **observe, notify, require re-auth/step-up, restrict actions, or revoke**; never auto-lock every account solely over a new IP.
4. When revoking, handle **all related access mechanisms**: local sessions, remember-me, refresh-token families, access tokens, device grants, suspicious passkeys/credentials, and SSO sessions at the identity provider (where supported).
5. Practically distinguish **offline JWT validation**, **opaque introspection**, OAuth token revocation, session invalidation, and password/MFA resets.
6. Design transactions, audits/outboxes, multi-node propagation, race tests, and operational runbooks to prove an incident is contained.
7. Ensure legitimate users have a safe recovery path without causing denial-of-service or user enumeration via messages and auto-lockouts.

**Technical assumptions:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x Servlet, HTTP sessions, and/or OAuth2 Resource Server. Specific notes apply to WebFlux/IdPs. The Java code in section 8 is a **JDK-standalone** domain simulation, while Spring Security examples are scoped integration snippets, not a complete security platform.

### Distinguishing Four Concepts

| Concept | Meaning | Limitation |
| --- | --- | --- |
| **Authentication event** | An authentication attempt succeeded or failed | Does not prove the action is legitimate |
| **Risk/anomaly signal** | Fact appearing unusual against history or policy | Not conclusive proof of account takeover |
| **Risk decision** | Choice to allow, step-up, restrict, revoke, or review | Requires measuring false positives and override controls |
| **Revocation/invalidation** | Making a credential/session/grant no longer accepted | Must be enforced at the right resource servers and nodes; does not happen automatically for every token type |

Changing a password **does not by default** log out all sessions and does not invalidate issued JWTs if verifiers only check signatures/`exp`. Logging out the current browser **is not equivalent** to revoking other sessions, refresh tokens, or IdP sessions. Treat these as distinct actions in your incident playbook.

## 2. Event Sources and Telemetry Model

A typical operational pipeline:

~~~text
Login / MFA / token refresh / API activity / account settings
           |
           v
Spring Security hooks + application domain events
           |
           v
Normalize (strip credentials, attach request/trace/account refs)
           |
           v
Message queue / transactional outbox / security event store
           |
           v
Risk rules, velocity windows, device/session correlations
           |
        +--+--+
        |     |
      low    medium/high
        |     |
     audit  step-up / restrict / alert / revoke
              |
              v
       Incident record + immutable audit
              |
              v
       Notification + user recovery + review
~~~

No single filter sees **every** event. Password logins, OAuth2 logins, OTPs, JWT Resource Servers, refresh token endpoints (often on the Authorization Server), WebAuthn, logout, and password changes traverse different components. **Inventory every endpoint and owning service**: which service issues sessions/tokens, which verifies them, and which has authority to revoke them.

### Event Fields to Consider

| Field | Example | Purpose and Protection |
| --- | --- | --- |
| `event_type` | `AUTH_SUCCESS`, `AUTH_FAILURE`, `REFRESH_REUSE` | Distinguish scenarios |
| `time_utc` | Server timestamp | Sequence and velocity analysis |
| `request_id`, `trace_id` | UUID/opaque | Locate related requests/traces |
| `account_ref` | Stable internal ID or HMAC pseudonym | Correlate events without logging raw emails |
| `session_ref` / `token_jti_ref` | Hash/opaque reference, never raw token | Identify affected sessions/tokens |
| `factor_type` | PASSWORD, PASSKEY, TOTP | Distinguish factor assurance |
| `result` / `reason_internal` | SUCCESS, BAD_CREDENTIAL, LOCKED, SERVICE_ERROR | Internal operational reasons only |
| `network_context` | ASN, IP risk band, coarse country | Assists alerting; personal data requiring policy |
| `device_context` | Trusted device registration ID or bounded signals | Never treat browser fingerprints as authentication proof |
| `risk_decision` | ALLOW, STEP_UP, RESTRICT | Evaluate rule quality |
| `incident_id` | Opaque case ID | Link investigations, rollbacks/appeals |

**Never log** passwords, OTPs, recovery codes, Bearer/access/refresh tokens, ID tokens, `JSESSIONID` cookies, private keys, TOTP secrets, or full request headers/bodies. `Authentication.getCredentials()` can hold sensitive secrets; **never serialize the entire `Authentication` object onto an event bus**. A `principal.getName()` from a failed login may be attacker-supplied input; never treat it as a trusted account ID before lookup/normalization and log-injection controls.

**Location/IP data is not absolute truth:** VPNs, CGNAT, mobile handoffs, corporate NATs, travel, proxies/CDNs, and shared devices create events that look anomalous. Follow data minimization, retention, access control, transparency, and privacy risk assessments per NIST SP 800-63B-4. Never monitor keystrokes/behavioral biometrics without legal basis, impact assessments, and proper safeguards.

### Events Needed Beyond Login

- Many failures across **multiple accounts** from one source, or multiple sources probing **one account** (credential stuffing/spraying).
- `MFA_CHALLENGE_SENT`, `MFA_CHALLENGE_FAILED`, `MFA_CHALLENGE_APPROVED`, and abnormal push counts (MFA fatigue).
- Refresh token issuance/exchange and **reuse of an already-rotated refresh token**, when the authorization server supports detection.
- Concurrent session activity across suspicious contexts or unexpected device/token binding changes.
- Adding/removing passkeys or TOTP, changing recovery email/phone, regenerating recovery codes, password changes, API key creation, linking new IdPs.
- Requests to export sensitive data, modify admin roles, change payout methods, or hit high-risk endpoints right after an unfamiliar login.

**Key limitation:** never rely solely on failure counters in one node's RAM to protect a multi-node/multi-region system. Velocity counters need a shared store with proper expiry/consistency and defenses against attackers forcing mass user lockouts.

## 3. Anomaly Detection: Signals, Context, and Decisions

There is no magic threshold fitting every product. Risk frameworks typically combine **signal confidence**, **data value/impact**, **account history**, and **post-login actions**. A traveling user changing IPs is a frequent false positive; by contrast, refresh token reuse after rotation is a far stronger signal, though it still warrants investigation.

| Signal | Interpretation | False-Positive Risk | Typical Response |
| --- | --- | --- | --- |
| Unseen device | Missing device registration or different browser context | Private browsing, new phone | Notify + step-up on sensitive operations |
| Impossible geo-velocity | Two close-in-time events far apart | VPNs, mobile networks, bad IP geolocation | Flag for review, combine with other signals |
| High-risk IP/ASN | Tor/proxy/botnet/reputation | Corporate NAT or legitimate traffic | Rate limit, step-up, investigate |
| Repeated wrong passwords | Failed attempts per account/IP/window | User typos, password manager issues | Throttle/risk challenge; never leak account existence |
| MFA push spam and unusual approval | Many prompts followed by acceptance | Impatient real user tapping repeatedly | Restrict/revoke, require phishing-resistant factor |
| Refresh token reuse | Already-rotated token re-presented | Broken client race, retry after bad network | Quarantine token family, protect account, investigate |
| MFA change right after new login | Classic takeover pattern | User actually bought a new device | Fresh re-auth, delay/notify trusted channels |
| New login followed by bulk data download | Data exfiltration signal | Legitimate work | Step-up/limit by data sensitivity |
| Local/IdP account disabled yet still accessing | Identity state drift | Replication lag | Deny per policy, check propagation |

### Two Decision Layers

1. **Detection** gathers signals and scores risk: low/medium/high/critical. This is an **estimate** to be measured, never reduced blindly into a boolean `isBadUser`.
2. **Enforcement** maps risk to an assurance-appropriate action: allow, require re-auth, step-up MFA/WebAuthn, temporarily lock sensitive features, revoke one session, revoke the whole account, quarantine transactions, or route to manual review.

An illustrative example policy, **not a mandatory standard**:

~~~text
if verified_refresh_token_reuse:
    RESTRICT account and revoke affected token family immediately
else if credential_compromise_confirmed:
    revoke all sessions/grants; force secure recovery
else if known_bad_network && repeated_failures_above_threshold:
    rate limit / challenge / investigate; avoid blind lockout
else if new_device && sensitive_operation:
    demand fresh phishing-resistant step-up
else if new_device or unusual_location:
    notify and raise monitoring
else:
    allow subject to normal authorization and risk controls
~~~

Do not turn `MFA_FAILED` immediately into `ACCOUNT_LOCKED` if someone else might be spamming OTPs against the user. Use layered brute-force defenses: per IP/device/account limits, backoff, quotas, and abuse intelligence while preserving privacy and preventing DoS. When scoring, weight low-confidence signals like geolocation lightly.

### Evaluating Rule Quality

- **Precision:** how many alerts actually warrant investigation? **Recall:** how many real incidents were missed?
- Measure false positives across network regions/devices, user cohorts, or work patterns while avoiding discrimination on sensitive attributes.
- Track median/p95 time from detection to containment, sessions/tokens remaining usable after containment, retry storms, and wrongly flagged case rates.
- Run high-impact auto-revoke rules in `shadow mode` first; keep an audited kill switch/override.
- Separate operational errors (IdP/JWK timeouts) from bad credentials: an outage is not an attack.

## 4. Playbook from Alert to Revocation and Recovery

A workflow needs **confidence triage**, **minimal evidence logging**, **containment**, **eradication/recovery**, and **verification**. Avoid both extremes: failing to revoke on clear proof, or locking out innocent users over one unfamiliar IP.

### 4.1. Tiered Response Sequence

| Level | Example | Recommended Action | When to Close Case |
| --- | --- | --- | --- |
| LOW | New device with valid strong MFA, no other signals | Record, notify per policy | No further signals appear |
| MEDIUM | Unfamiliar device/IP right before sensitive data export | Fresh step-up, hold high-risk actions | Challenge passed and activity verified |
| HIGH | MFA fatigue, abnormal recovery contact change, refresh reuse | Block factor changes, revoke affected sessions/family, alert SOC | Account owner verifies, post-check access permissions |
| CRITICAL | Proof of stolen session/token, unauthorized MFA change | Contain entire account, revoke/disable affected credentials and sessions, run incident response | Zero old credentials usable, safe recovery complete |

NIST SP 800-63B-4 states that when session monitoring detects fraud risk, the RP should coordinate to require reauthentication, terminate sessions, or notify responsible parties. This is a risk-based principle, **requiring no specific scoring algorithm**.

### 4.2. Suspected Takeover Response Runbook

1. **Triage:** assign `incident_id`, UTC timestamp, account reference, related login/session/token IDs, evidence, and confidence; enforce view permissions and retention.
2. **Contain:** if severe, disable sensitive actions first; revoke affected sessions/tokens. Pay special attention to admin accounts with downstream privileges.
3. **Notify via trusted channels:** previously verified email/phone or trusted support/device channels—not just a contact an attacker just changed. Never put reset tokens in logs/analytics.
4. **Control recovery:** the user must re-prove identity with sufficiently strong independent factors, preferring passkeys/security keys; if MFA is lost, use a dedicated anti-social-engineering recovery process. Never let support unlock accounts with just a `requestId`.
5. **Eradication:** rotate exposed credentials, remove rogue factors, rotate recovery codes, revoke suspicious OAuth grants/API keys/devices, and inspect modified rules/roles.
6. **Verify:** replay old test requests/tokens from a controlled test harness to prove 401/403 or step-up per policy; check every node/region and authorized service.
7. **Restore:** issue fresh sessions/tokens after strong authentication, notify the account owner; audit who approved recovery, why, and log access permissions.
8. **Post-incident:** tune detection rules, false-positive metrics, runbooks, residual JWT windows, and multi-region support.

**Do not expose detailed reasons** on anonymous login pages: "this email exists and logged in from X" leaks user existence and history. Clients should receive safe responses and support guidance when needed; technical details stay in access-controlled audits/logs.

## 5. Revoking Access: Right Place, Right Lifecycle

A system may simultaneously hold local session cookies, authorization-server refresh tokens, API JWT access tokens, remember-me cookies, WebAuthn credentials, OAuth authorized clients, and IdP sessions. **Revoking each is a distinct operation.**

| Asset | How to Block Access | Common Limitations |
| --- | --- | --- |
| **Local `HttpSession`** | Invalidate session in the session store; remote logout or per-request `security_version`/revocation check | `SecurityContextLogoutHandler` on the current request does not automatically revoke sessions on other nodes |
| **Session registry** | `SessionRegistry` + concurrent session support marks `SessionInformation.expireNow()` | In-memory registries are not global multi-node kill switches; proper cluster integration is needed |
| **Remember-me token** | Delete server persistent token and cookie on logout; rotate remembered device keys per policy | Cookies on stolen devices must be blocked server-side |
| **Refresh token/family** | Revoke grant/token family at Authorization Server; block reuse after rotation | Does not automatically expire existing JWT access tokens |
| **Offline JWT access token** | `jti` denylist, check `security_version`/user status at every resource server, or short TTL accepting residual lifetime | Changing passwords or deleting refresh tokens alone does not invalidate already-signed `JWT`s |
| **Opaque access token** | Authorization Server returns `active=false` on introspection; Resource Server rechecks per cache TTL | Introspection caches can delay effect |
| **OAuth grant at IdP** | RFC 7009 token revocation / IdP admin API or client logout profile | Provider cascade support varies; does not delete the user at the IdP |
| **IdP SSO session** | RP-initiated logout, back-channel logout, or IdP API if supported | IdP and RP sessions are independent and must be coordinated |
| **Authenticator/passkey/TOTP** | Revoke device/credential mapping and securely rebind | Clearing sessions alone does not remove a compromised credential |
| **API keys/service credentials** | Rotate/revoke keys and scopes in the key store | Live outside `HttpSession` and are often long-lived |

### 5.1. Spring Security Logout Only Handles the Current Session in Scope

In Servlet apps, `POST /logout` (with CSRF token when CSRF is active) typically invokes `SecurityContextLogoutHandler` to invalidate the `HttpSession`, clear `SecurityContext`, and run logout handlers. That is useful, yet **never guarantees revoking all sessions, refresh tokens, or JWTs across services**.

To support "Log out all devices", build a reliable session store, track device/session IDs, expire/revoke in the shared store, or enforce an **account security version** checked on incoming requests. When using `SessionRegistry`:

~~~java
// Pseudocode in a service with SessionRegistry and a verified principal:
// SessionInformation: org.springframework.security.core.session.SessionInformation
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
~~~

This is **not a complete service**: it requires concurrent session management/filters recognizing expired sessions, a registry that sees all sessions across nodes, and multi-node support; `expireNow()` only flags the session and does not remotely delete cookies held on other nodes. Never scan `getAllPrincipals()` loosely by display name; identifiers must be stable and tenant-scoped.

### 5.2. JWT Access Tokens and "Statelessness"

If a Resource Server validates only signature + `iss`/`aud`/`exp`, a validly signed JWT stays usable until `exp` even if the account was locked or the refresh token was revoked. For near-real-time revocation, Resource Servers must enforce **a state-checking policy**:

- Check `account.security_version`/`session_version` from a trusted data source against the value bound at token issuance; if bumped, reject old tokens.
- Or maintain a `jti` denylist with TTL matching token expiry; validate exact audience/issuer and never leak raw tokens.
- Or use opaque introspection, token binding, or short-lived access tokens paired with refresh-token rotation; weigh latency/availability/consistency trade-offs.
- For access JWTs issued by an **external IdP**, the local app cannot inject `security_version` into old tokens itself; rely on supported protocols, custom denylists/claims policies, or remote checks.

**Crucial condition:** any Resource Server that skips version/denylist checks **will not** enforce revocations made only in the user database. Caching account status too long creates an exposure window. Document and test your **upper bound revocation lag** per threat model. In severe incidents, fail closed on sensitive endpoints if revocation state cannot be queried rather than silently bypassing on store errors.

### 5.3. OAuth2 Token Revocation and RFC 7009

RFC 7009 specifies a token revocation endpoint. Authorization Servers are required to support revoking **refresh tokens** and recommended to support revoking **access tokens**; revoking a token may also invalidate related grants/tokens per AS policy. Clients call the trusted HTTPS revocation endpoint with proper client authentication and **never log raw tokens**.

**Never claim that revoking a refresh token immediately invalidates all access tokens** if the AS does not revoke access tokens or resource servers validate JWTs completely offline. NIST also notes IdP and RP sessions are independent: logging out of an RP does not guarantee logging out of the IdP, or vice versa.

### 5.4. Scoped Revocation

- **Revoke one session/device** when proof shows one device was lost while other sessions remain trustworthy.
- **Revoke one refresh token family** when reuse or token theft is detected in that family.
- **Revoke all user sessions/grants** on severe account takeover, password/MFA compromise, or legal mandates.
- **Temporarily disable the account** when no safe recovery method is ready, while guarding against attackers triggering lockouts via spoofed signals.
- **Rotate credentials** addresses the root compromise, distinct from revoking issued sessions/tokens.

Which level to pick depends on signal confidence and business impact. Actions like deleting the last MFA factor, changing recovery email, and granting admin privileges must stay protected even after a user passes normal login.

## 6. Multi-Node Revocation Architecture and Race Conditions

Suppose a login created two sessions across two nodes plus a refresh-token family minting 15-minute JWT access tokens. A "Logout all" command calling `invalidate()` only on the current request's session leaves the other node accepting its cookie and JWTs on other devices still valid. Therefore, you need a **shared state source** or revocation channel enforced by **every verifier**.

### Reference Schema for App-Owned Sessions

~~~sql
CREATE TABLE account_security (
    user_id VARCHAR(64) PRIMARY KEY,
    security_version BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE app_session (
    id_hash VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES account_security(user_id),
    security_version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_session_user_active
    ON app_session(user_id, revoked_at);

CREATE TABLE security_incident (
    incident_id UUID PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES account_security(user_id),
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    decision_reason VARCHAR(120) NOT NULL
);

CREATE TABLE security_outbox (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES security_incident(incident_id),
    event_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ
);
~~~

This schema is purely illustrative; `id_hash` stores no raw session cookies. Real products need tenant isolation, unique constraints, expiry cleanup, migrations, indexes, logging, and concurrency policies. Do not assume every app needs custom tables if already using Spring Session/Redis with proper indexing and invalidation.

### Transactions, Propagation, and Race Control

~~~text
Incident accepted (authorized actor / verified policy)
      |
      v
DB transaction:
  lock account security row
  increment security_version
  mark affected local sessions/grants revoked
  record incident + outbox event atomically
  commit
      |
      v
Workers deliver revocation events / clear caches / call AS & IdP APIs
      |
      v
All verifiers check new state on requests
      |
      v
Audit evidence of confirmed acknowledgments and failures
~~~

**Separate local transactions from external side effects:** a DB transaction cannot atomically span remote IdPs/Authorization Servers. Use **outboxes + idempotent retries + deadlines + dead-letter queues + alerts** for external cleanup. A revocation request may succeed locally while staying `PENDING_EXTERNAL_REVOKE`; never report "everything revoked" before confirmation.

**Race to test:** Token refresh executing concurrently with revocation. Check account version/security status **in the same transaction** as issuing/rotating refresh tokens or use equivalent version concurrency control. Checking only before revocation lets an in-flight request mint **a fresh token after the account was revoked**. Multi-region systems must define consistency/replication lag; eventual consistency leaves a token-reuse window.

**Idempotency:** revocation events may be replayed by queues; bumping `security_version` repeatedly can kick out newly recovered valid sessions. Store unique `incident_id`/`action_id` keys and mark processed so the same decision takes effect once. Restore accounts only after reauthentication and policy-compliant state reset.

### Handling Unreachable Caches / Revocation State

An API should enforce a risk-tier policy:

- High-risk endpoints (password changes, adding MFA, money transfers, fetching PII): if `session`/`securityVersion` cannot be verified reliably, **fail closed** or switch to read-only/reauth.
- Low-risk endpoints: may apply an approved availability policy with strict cache TTLs, yet **must never silently pretend the revocation check passed**.
- Offline-JWT APIs: design an explicit max time-to-revoke when no online check exists, measure it, and publish it operationally.
- When revocation spans multiple systems, track per-step status and alert on SLA breaches.

## 7. Spring Security Servlet: Signal Collection Points and Hook Boundaries

### 7.1. Authentication Events

Spring Security provides `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent` subclasses, and `AuthenticationEventPublisher`. When a publisher is wired and used by the authentication flow, the app can use `@EventListener` to observe events. Spring Security documentation notes `DefaultAuthenticationEventPublisher` maps exceptions via **exact class match**, so custom `AuthenticationException` subclasses may need extra mapping configuration.

Bean configuration (snippet inside a `@Configuration` class with imports):

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

If Spring Boot/the app already supplies a publisher bean, **do not create a duplicate**. Remember one event listener may not cover every mechanism; verify coverage across OAuth2 login, JWT Resource Server, passwords, MFA, and custom filters.

An illustrative listener (compiled **inside a project with Spring dependencies**, package `example`). It pushes work to an **internal sink**, never sending the `Authentication` object onto an event queue:

~~~java
package example;

import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class AuthenticationSignalsListener {

    private final AccountRefResolver resolver;
    private final SecuritySignalSink sink;

    public AuthenticationSignalsListener(
            AccountRefResolver resolver,
            SecuritySignalSink sink) {
        this.resolver = resolver;
        this.sink = sink;
    }

    @EventListener
    public void succeeded(AuthenticationSuccessEvent event) {
        String accountRef = resolver.safeRef(event.getAuthentication());
        sink.enqueue("AUTH_SUCCESS", accountRef);
    }

    @EventListener
    public void failed(AbstractAuthenticationFailureEvent event) {
        String accountRef = resolver.safeRef(event.getAuthentication());
        sink.enqueue("AUTH_FAILURE", accountRef);
    }
}

// App-defined interfaces: implement and register corresponding beans.
// Resolver returns a safe, stable internal ref only after account mapping;
// if not known, it returns an opaque UNKNOWN reference, not raw username.
interface AccountRefResolver {
    String safeRef(Authentication authentication);
}
interface SecuritySignalSink {
    void enqueue(String eventType, String accountReference);
}
~~~

**Limitations:** this is a wiring snippet; implement both interfaces as Spring beans and guard against slow sinks, rate limits, and queue latency. Listeners should never synchronously block login on slow risk-scoring APIs; if using async handling, manage context propagation, retries/outboxes, and deliberate fail-open/fail-closed choices. The resolver must never log/serialize `Authentication` since credentials/details can be sensitive; for unknown users, never assign a misleading local user ID.

### 7.2. Events Do Not Automatically Carry Trusted Network Context

`AuthenticationSuccessEvent` normally holds `Authentication`, yet **does not guarantee** verified client IPs, device attestation, or canonical tenants. Capture network context at a trusted request boundary/gateway, validate `Forwarded`/`X-Forwarded-For` against trusted proxies, and never trust arbitrary client-sent headers. Attach request IDs, UTC timestamps, and controlled session refs. Avoid calling `request.getRemoteAddr()` blindly behind reverse proxies.

To enforce policy **before issuing a session**, hook directly into the authentication pipeline or access decision rather than merely listening to an event and asynchronously "revoking afterward", which leaves an access window. For unbypassable enforcement, combine pre-issue checks, step-up, authorization guards, and post-issue monitoring.

### 7.3. SessionManagement, SessionRegistry, and Spring Session

- `SessionCreationPolicy.STATELESS` means the security chain **does not maintain an HTTP session**, so `HttpSession.invalidate()` does not revoke standalone Bearer JWTs.
- `SecurityContextRepository` saves/reads `Authentication` for session requests; with custom auth filters in Spring Security 6.x, understand `requireExplicitSave` and save points.
- `SessionRegistry`/concurrent sessions help track registered sessions, though they do not replace system-wide shared revocation.
- With Spring Session + Redis/JDBC and indexed sessions, remote session management can be built per library version APIs; **never assume you can delete all sessions for a user if the store lacks a user index**.
- `LogoutHandler` runs only inside configured logout flows; out-of-band password changes/revocations must invoke dedicated domain services rather than assuming token verifiers trigger automatically.

### 7.4. Role-Controlled Audits and Event Traces

Minimum logs include `incident_id`, `request_id`, `account_ref`, `event_type`, `outcome`, `action_target`, `actor_ref`, UTC timestamp, policy version, and external revocation status. Logs should be immutable/tamper-evident as required, enforce retention/least privilege, and omit raw tokens and unnecessary PII.

**Never embed tokens/passwords in error messages** of `AuthenticationException` or business exceptions that get serialized/traced. In HTTP responses, return only generic public codes (e.g., `REAUTH_REQUIRED`, `AUTH_FAILED`) and a correlation ID, hiding detection heuristics and protecting account existence from anonymous callers.

## 8. Standalone Java 17 Example: Signal Scoring and Version-Based Revocation

This is an **educational model** testing two rules: risk signals must map to appropriate decisions, and on account-wide revocation, old sessions/refresh grants are rejected. The program **uses no Spring, DB, or HTTP**, issues no real JWTs, and calls no IdP. `securityVersion` is checked inside a single JVM's memory; production needs shared stores, atomic transactions, and race/replication-lag defenses.

Create `LoginIncidentDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class LoginIncidentDemo {

    enum Decision { ALLOW, STEP_UP, RESTRICT }

    record Signals(boolean newDevice,
                   boolean unfamiliarLocation,
                   boolean highRiskNetwork,
                   int recentFailures) {
        Signals {
            if (recentFailures < 0) {
                throw new IllegalArgumentException("negative failures");
            }
        }
    }

    static Decision assess(Signals input) {
        Objects.requireNonNull(input);
        // Thresholds are synthetic lesson data only.
        if (input.highRiskNetwork() && input.recentFailures() >= 5) {
            return Decision.RESTRICT;
        }
        if (input.newDevice()
                || input.unfamiliarLocation()
                || input.recentFailures() >= 3) {
            return Decision.STEP_UP;
        }
        return Decision.ALLOW;
    }

    record Grant(String userId, long version) {}

    private final Map<String, Long> accountVersion = new HashMap<>();
    private final Map<String, Grant> sessions = new HashMap<>();
    private final Map<String, Grant> refreshGrants = new HashMap<>();

    private long currentVersion(String userId) {
        return accountVersion.getOrDefault(userId, 0L);
    }

    synchronized void issueSession(String userId, String sessionRef) {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(sessionRef);
        sessions.put(sessionRef, new Grant(userId, currentVersion(userId)));
    }

    synchronized void issueRefresh(String userId, String tokenRef) {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tokenRef);
        refreshGrants.put(
            tokenRef, new Grant(userId, currentVersion(userId)));
    }

    synchronized boolean sessionValid(String sessionRef) {
        Grant grant = sessions.get(sessionRef);
        return grant != null
            && grant.version() == currentVersion(grant.userId());
    }

    synchronized boolean refreshValid(String tokenRef) {
        Grant grant = refreshGrants.get(tokenRef);
        return grant != null
            && grant.version() == currentVersion(grant.userId());
    }

    synchronized long revokeAll(String userId) {
        Objects.requireNonNull(userId);
        long nextVersion = currentVersion(userId) + 1;
        accountVersion.put(userId, nextVersion);
        sessions.entrySet().removeIf(
            e -> userId.equals(e.getValue().userId()));
        refreshGrants.entrySet().removeIf(
            e -> userId.equals(e.getValue().userId()));
        return nextVersion;
    }

    public static void main(String[] args) {
        System.out.println("low=" + assess(
            new Signals(false, false, false, 0)));
        System.out.println("medium=" + assess(
            new Signals(true, false, false, 1)));
        System.out.println("high=" + assess(
            new Signals(true, true, true, 7)));

        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "session-old");
        store.issueRefresh("alice", "refresh-old");

        System.out.println("sessionBefore="
            + store.sessionValid("session-old"));
        System.out.println("refreshBefore="
            + store.refreshValid("refresh-old"));

        long version = store.revokeAll("alice");

        System.out.println("newVersion=" + version);
        System.out.println("sessionAfter="
            + store.sessionValid("session-old"));
        System.out.println("refreshAfter="
            + store.refreshValid("refresh-old"));

        store.issueSession("alice", "session-new");
        System.out.println("newSession="
            + store.sessionValid("session-new"));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac LoginIncidentDemo.java
java LoginIncidentDemo
~~~

**Exact stdout:**

~~~text
low=ALLOW
medium=STEP_UP
high=RESTRICT
sessionBefore=true
refreshBefore=true
newVersion=1
sessionAfter=false
refreshAfter=false
newSession=true
~~~

### Interpreting the Output

- `low/medium/high` illustrate varying decisions as failures, new devices, and network risk change. Thresholds 3/5 are only pedagogical, **not OWASP/NIST standards**.
- `sessionBefore=true` and `refreshBefore=true` represent active grants in the model; after `revokeAll`, old records are removed and the version increments.
- `sessionAfter=false` and `refreshAfter=false` show a verifier that **actually checks state** rejects old grants.
- `newSession=true` means the simulator **re-issued** a session post-revoke; a real system **must never re-issue sessions just by calling an issue method**—it must reauthenticate the account owner and pass recovery/step-up policies. This is purely a state simulator.
- There is no cryptographic JWT logic here: a self-contained JWT issued by an external issuer **does not lose validity automatically** because an `accountVersion` map changed.
- `synchronized` applies only within one JVM; production needs transactions/locking, token family semantics, and idempotent incident handling in shared stores.

### JUnit 5 for Domain Behavior

If the project uses JUnit Jupiter, place `LoginIncidentDemoTest.java` in the same package as the demo class:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoginIncidentDemoTest {

    @Test
    void noisyUnknownContextTriggersStepUpNotAutomaticLock() {
        assertEquals(LoginIncidentDemo.Decision.STEP_UP,
            LoginIncidentDemo.assess(
                new LoginIncidentDemo.Signals(
                    true, false, false, 1)));
    }

    @Test
    void highRiskNetworkPlusManyFailuresIsRestricted() {
        assertEquals(LoginIncidentDemo.Decision.RESTRICT,
            LoginIncidentDemo.assess(
                new LoginIncidentDemo.Signals(
                    true, true, true, 7)));
    }

    @Test
    void globalRevocationInvalidatesExistingSessionAndRefresh() {
        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "s1");
        store.issueRefresh("alice", "r1");
        assertTrue(store.sessionValid("s1"));
        assertTrue(store.refreshValid("r1"));

        assertEquals(1L, store.revokeAll("alice"));
        assertFalse(store.sessionValid("s1"));
        assertFalse(store.refreshValid("r1"));
    }

    @Test
    void otherUsersGrantsRemainValid() {
        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "s-a");
        store.issueSession("bob", "s-b");

        store.revokeAll("alice");
        assertFalse(store.sessionValid("s-a"));
        assertTrue(store.sessionValid("s-b"));
    }
}
~~~

This test suite checks domain logic in memory; add HTTP, Spring session store, OAuth token endpoint, multi-node, concurrency, and IdP coordination tests. Passing these unit tests does not prove the real system revokes remote sessions.

## 9. Integration Test Matrix

| Scenario | Outcome to Prove |
| --- | --- |
| Repeated wrong-password logins | Emits redacted events, enforces rate limits, hides account existence |
| Many users probed from one IP | Aggregates abuse signal without locking out all legitimate users |
| Login from new device | Accurate step-up/notify policy; accounts for VPNs/private browsing |
| MFA fatigue | Detects push/challenge floods, enforces limits and safe confirmation channels |
| Refresh token rotation reuse | Token family quarantined/revoked per policy; audits exact ID |
| Adding TOTP/passkey after unfamiliar login | Requires fresh existing-factor re-auth; cannot bypass using old session |
| Revoke local session on node A | Node B rejects that session via shared store |
| Revoke all user sessions | All old session refs denied without affecting other accounts |
| Revoke refresh grant | AS refuses to issue new access tokens; test concurrent refresh race |
| Pre-revoke JWT access token | Rejected when resource server enforces denylist/security-version; else within documented residual TTL |
| Revoked opaque token | Introspection returns `active=false`; cache does not exceed SLA budget |
| IdP logout | RP session is **not assumed** cleared automatically; verify back-channel integration if present |
| Security store outage | High-risk endpoints fail closed; clear alerts, no retry loops |
| Revoke vs. token issuance race | No post-containment usable token minted out of policy |
| Duplicate outbox event delivery | Handled idempotently; never invalidates a legitimately recovered session |
| Partial external revocation failure | Incident enters `PARTIAL`/`PENDING` state, alerts and retries |
| Login anomaly false positive | User has safe step-up/recovery path rather than permanent lockout |
| Anonymous API probing account | Generic public response; internal reasons hidden |
| Notification after recovery-contact change | Contact **verified prior to change** still receives warning |
| Log/trace audit | Zero raw passwords/sessions/Bearers/OTPs; incident/request IDs present |
| Closed incident | E2E proof old tokens/sessions are blocked and only re-authenticated sessions work |

**Policy tests must execute at real boundaries.** Spring Security Test's `MockMvc .with(user(...))` or `jwt()` injects synthetic `Authentication` into requests, **which does not test** session revocation, JWT signature/expiry/denylists, or OAuth2 introspection. To test those, use **real test cookies/tokens** against filter chains wired with real session stores/decoders/introspectors and verify exact status codes/headers. Never put production credentials in CI.

### Negative Test Cases to Include

- Concurrent `logout all` + `refresh` across two threads/nodes using a barrier and real DB transactions to reproduce races.
- Attacker attempting forced lockouts via fake failed logins; verify abuse mitigation without user DoS.
- Sessions from another site/app with the same username in a different tenant must not be revoked by mistake.
- IdP revoked grant while Resource Server validates JWT offline until `exp`: measure the residual usable window.
- Redis/event bus disconnected: check cache policy and retry caps; never auto-allow high-risk routes.
- Post-incident account recovery: old token families cannot be resurrected by stale queued messages.
- Duplicate incident trigger: idempotency avoids bumping version after a fresh safe session was granted.
- Token introspection cache: `active=false` takes effect within policy time rather than staying active indefinitely.
- Alert email to prior verified contact contains no public reset tokens or sensitive log data.

## 10. Concise Operational Runbook

### When an Alert Fires

1. Capture `incident_id` and confidence; verify trusted data sources, correlations, and blast radius.
2. Distinguish legitimate user travel/activity from takeover indicators; combine multiple signals when proof is weak.
3. Prioritize blocking high-risk actions and token refreshes as needed; decide full-account revocation per policy.
4. Persist the decision and outbox transactionally; execute session/token revocation across all relevant services.
5. Notify via trusted channels; never let a potentially compromised old session clear restrictions on its own.
6. Offer recovery backed by strong proof; verify/revoke any rogue factors or linked accounts.
7. Verify by testing old sessions/tokens in a controlled test check rather than trusting a 200 from the revoke API; mark `COMPLETED` or `PARTIAL_REVOKE`.
8. Close the incident with containment proof and access post-audit; document root cause, measured revocation lag, and lessons learned.

### Metrics to Watch

- Anomaly rate over logins and confirmed incident precision.
- False step-up/lockout rate for legitimate users and appeal/recovery success rate.
- `time_to_detect`, `time_to_contain`, and `revocation_lag_p95/p99` per credential/service type.
- Counts of refresh token reuse, unrevoked OAuth grants, and still-active stale sessions.
- Count of incidents in `PENDING_EXTERNAL_REVOKE`, retry counts, and IdP/revocation-store errors.
- Security event stream health, percentage of login flows emitting complete events, outbox backlog, and event loss.

Never put raw emails/user IDs or random high-cardinality JWT `jti` values into Prometheus labels. Use aggregated labels and access-controlled investigation logs. Protect event provenance and tamper resistance.

## 11. Common Mistakes

1. **Watching only failed logins**, ignoring MFA fatigue, refresh reuse, post-login session hijacking, and credential changes.
2. **Auto-locking accounts over unfamiliar IPs/geo** without accounting for VPNs, mobile networks, and false positives, causing DoS.
3. **Assuming one event listener covers every auth mechanism:** custom flows and separate AS instances need their own instrumentation.
4. **Serializing `Authentication` onto event buses:** can leak sensitive credentials/details.
5. **Trusting arbitrary `X-Forwarded-For` headers:** attackers spoof IP/geo; trust only known proxies.
6. **Logging out only the current request** and claiming "signed out of all devices".
7. **Changing passwords/revoking refresh tokens** and claiming JWT access tokens are dead while Resource Servers verify offline.
8. **Deleting one refresh token record without tracking family/reuse:** attackers holding sibling tokens keep refreshing.
9. **Incrementing `securityVersion` in the DB** while resource servers never check the version.
10. **Caching revocation state too long:** tokens stay usable after containment; enforce budgets/alerts.
11. **Ignoring races between token issuance and revocation:** leaves a window minting fresh credentials post-revoke.
12. **Assuming IdP logout automatically logs out RPs:** the two session types are separate.
13. **Accepting account IDs from request bodies to revoke another user:** require server-side trusted principals, roles/approvals, and audits.
14. **Having no recovery path:** legitimate users stay permanently locked out or support bypasses MFA.
15. **Auto-sending alerts only to the newly changed contact:** an attacker who changed contact info intercepts warnings silently.
16. **Skipping outbox/retries/idempotency:** remote revokes fail silently, or stale retries lock a freshly recovered account.
17. **Marking incidents "revoke success"** without testing old credentials against every verifier.
18. **Conflating suspicion with proof:** turning raw analytics into automatic permanent bans without review.
19. **Returning public messages like "account exists/compromised"** on anonymous login: leaks user existence and privacy.
20. **Having no security-store outage plan:** network errors make dangerous endpoints fail open.

## 12. Implementation Checklist

- [ ] Inventory all authentication flows, session stores, OAuth grants, refresh/access tokens, IdPs, and active verifiers.
- [ ] Redacted event schema, UTC timestamps, request/incident IDs, and privacy/retention/access controls in place.
- [ ] Risk signals have false-positive analysis, calibration, threat models, and appeal/recovery paths.
- [ ] Sensitive actions require step-up; compromised-suspect sessions cannot alter factors or trigger recovery.
- [ ] Revocation covers exact scope: local sessions, persistent remember-me, refresh families, JWT/opaque tokens, and IdP sessions where supported.
- [ ] Resource servers enforce revocation policies consistently; residual lifetime/lag is measured.
- [ ] DB transactions + outbox + idempotent retries + explicit `PARTIAL_EXTERNAL_REVOKE` tracking.
- [ ] Revoke commands enforce authorization, role/approval checks, and audits; never accept browser-supplied target IDs blindly.
- [ ] Zero secrets leaked in logs, events, metrics, notifications, or responses.
- [ ] Tested revoke/refresh races, multi-node propagation, cache lag, security-store outages, and false-positive recovery.
- [ ] Runbooks ready for on-call/SOC, support escalation, safe user notifications, and post-incident verification.

**Summary:** anomalous login detection is **fallible risk scoring**, whereas access revocation is a **trusted state transition enforced by every verifier**. Spring Security provides hooks, security contexts, and per-layer session/token management; your application must connect signals, policies, transactions, session/token revocation, IdP coordination, and recovery into one verifiable workflow.

## 13. Official References

- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Logout support: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Opaque tokens and introspection: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- NIST SP 800-63B-4 (2025) — Session monitoring, reauthentication: https://pages.nist.gov/800-63-4/sp800-63b/session/
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009.html
- RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
