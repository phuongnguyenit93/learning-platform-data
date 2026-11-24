# Reconciling Logout, MFA, and Session Lifetime Policies Before Migrating Spring Security Federation

## 1. Objective: SSO Migration Must Preserve Security Boundaries

When upgrading a Spring Security application from a legacy authentication mechanism to **SAML 2.0, OpenID Connect (OIDC), or CAS**, or changing framework/Identity Provider versions, a single successful login does not prove the migration is safe. Policies around **logout (logout/session revocation)**, **multi-factor authentication (MFA/step-up)**, and **session lifetimes (idle/overall/freshness)** can quietly be relaxed.

This lesson belongs to **Migration and Upgrade**. Its goal is to establish an approved **policy-parity contract**, verify exact protocol flows, write positive/negative tests, and set a **GO/NO-GO gate** prior to cutover. Learners must distinguish:

- **Local logout**, **RP/SP-initiated logout**, **IdP/OP/AP-initiated logout**, **Single Logout (SLO)**, and **administrator revocation**.
- **IdP SSO session**, **local `HttpSession`**, and **access/refresh tokens**: three independent lifecycles.
- **MFA occurred at some point** vs. **MFA occurred recently**: ACR/AMR/`AuthnContext` and `auth_time`/`AuthnInstant` timestamps.
- **Idle timeout** vs. **overall reauthentication timeout**, **MFA freshness**, **hard cap from session issuance**, and **JWT `exp`**.
- Spring Security Servlet `SecurityContextRepository`, session fixation, concurrency limits, OIDC back-channel logout, SAML SLO, and CAS SLO.
- When facing **UNKNOWN assurance** or missing event-delivery proof, **fail closed** for high-assurance operations.

**Principle:** a new policy achieves parity only when it never permits a user/session/action that the approved legacy policy would deny, unless a change is explicitly approved in writing by security and business owners.

## 2. Scenario Revealing Hidden Bugs

~~~text
Approved legacy policy:
  Local idle timeout             = 30 minutes
  Overall reauth timeout         = 8 hours
  Sensitive transfer MFA maximum = 10 minutes
  Admin sensitive MFA            = phishing resistant
  Active sessions per subject    = max 2
  Identity Provider logout       = must revoke related local sessions

Candidate migration:
  OIDC login succeeds, receives signed ID Token.
  App uses only HTTP session idle=60 minutes.
  ID Token has fresh iat, old auth_time; app mistakes iat for fresh MFA.
  /logout clears browser cookie without handling OP back-channel.
  Admin access still holds ROLE_ADMIN on old session.
  Mobile/API still uses unrevoked bearer tokens.

=> Staging login PASS, yet MFA/session/logout parity FAIL.
~~~

The numbers **30 minutes, 8 hours, and 10 minutes** are illustrative for one application; **they are not universal mandates** of SAML/OIDC/CAS. Evaluate only against real enterprise-approved policies.

## 3. Inventory Before Comparing

### 3.1. Questions That Must Have Answers

1. How many IdPs do users log in from? What are each provider's **issuer, `clientId`/`registrationId`, SP `entityId`, tenant, and subject identifier**?
2. Which groups require MFA: all logins, admin groups, sensitive data, MFA-method changes, funds transfers, or post-risk-event actions?
3. Which claims serve as MFA evidence? **OIDC `acr`/`amr`/`auth_time`**, **SAML `AuthnContext`/`AuthnInstant`**, CAS-specific attributes, or trusted gateway attestation?
4. Does the app have **local, global, IdP-initiated, admin revoke, inactivity, and overall** logout? Is the scope of each **one session, all user sessions, one application, or multiple applications**?
5. Are local sessions stored in the Servlet container, **Spring Session Redis/JDBC**, BFF cookies, stateless JWTs, or a dedicated session registry?
6. Are timeouts for browser cookies, server sessions, remember-me, access tokens, refresh tokens, and IdP SSO sessions being confused?
7. What happens when an IdP callback arrives late, a browser has two tabs, two sessions exist on two devices, multiple Spring replicas run, logout events retry, or revocations arrive after login?
8. Does legacy have special cases: break-glass, trusted devices, administrator sessions, long-lived remember-me, delegated/proxy users, or step-up?
9. During rollback, **can a logged-out session or locked user come back to life**?
10. Who confirms the policy baseline and who decides whether a discrepancy is acceptable?

Capture **both configuration and actual behavior**. A `singleLogout=true` flag does not prove the local session was cleared. A timeout property does not prove every replica enforces it.

### 3.2. Evidence Table to Build

| Policy Item | Legacy Evidence | Candidate Implementation | Test Proof | Owner |
| --- | --- | --- | --- | --- |
| Local logout | Controller/filter/logs | Spring `LogoutFilter` | Old cookie denied | App |
| Upstream/global logout | IdP/CAS contract | SAML SLO or OIDC RP logout | Other RP state | IAM |
| Remote logout | Signed callback logs | OIDC back-channel / SAML SLO / CAS SLO | Mapped sessions invalid | IAM + App |
| MFA classes | IAM policy + attributes | Verified claims adapter | Low assurance denied | Security |
| MFA freshness | Trusted authentication event | `auth_time`/`AuthnInstant` + state | Boundary tests | Security |
| Idle/overall timeout | Effective session config | Servlet + explicit policy | Frozen-clock tests | App |
| Concurrency | Session registry | Session management | Third login | App |
| Account disable/revoke | IAM events | Event/lookup/cache TTL | Time-to-deny SLA | Security |
| Browser+API token cleanup | Logout implementation | Cookie/session and revocation | Token replay tests | API |
| Rollback and migration | Old session store | Controlled expiry/re-auth | No resurrected user | Operations |

Mark **UNKNOWN**, **UNSUPPORTED**, or **NOT TESTED** when evidence is missing; never promote such rows to PASS.

## 4. Separating Three Session Types and Four Lifetime Types

~~~text
             Identity Provider / OP / CAS
                upstream SSO session
                         |
                  SAML/OIDC/CAS proof
                         |
            Spring Security Relying Party
                  local HttpSession
                         |
             API access/refresh tokens
~~~

- **IdP SSO session** lives on the IdP domain with its own cookie/session/reauth policies.
- **Local `HttpSession`** holds Spring `SecurityContext` or app session identity. Clearing the app cookie does not clear the IdP session.
- **Access tokens** are verified by resource servers and may remain valid even after the user logs out of the browser. **Refresh tokens** have their own lifecycle and revocation.

An OIDC **ID Token `exp`** only bounds the validity of that artifact at validation time; it is **not** the local `HttpSession` deadline. `iat` is when the token was issued, not when the user actually authenticated; `auth_time` describes the authentication event when supported/verified. Access token `exp` does not prove the user is still present.

SAML **`Conditions@NotOnOrAfter`** and bearer `SubjectConfirmationData@NotOnOrAfter` limit **assertion acceptance**, not local session lifetime by default. `AuthnStatement@SessionNotOnOrAfter` is upstream session info that must be mapped by policy rather than automatically setting the Spring `HttpSession` timeout. A CAS **Service Ticket** is validated once, not a session cookie or TGT lifetime.

| Timer | Start Anchor | When Reset? | What It Checks |
| --- | --- | --- | --- |
| **Idle** | Latest valid activity | User activity | After X minutes of inactivity → session expires |
| **Overall reauth** | Latest successful authentication or reauthentication | Genuine reauth only | Even with activity, after X hours user must reauthenticate |
| **MFA freshness** | Latest trusted MFA event | Fresh verified MFA/step-up | Sensitive actions require proof no older than Y minutes |
| **Hard lifetime** | Session issued-at | Never reset if policy requires | Session cannot exist beyond Z hours |
| **OP/IdP session lifetime** | Upstream session | Per IdP policy | Never inferred automatically from local session |
| **Token expiry/rotation** | Token `iat`/`exp`/grant state | Per token server | Does not replace local session policy |

**NIST SP 800-63B-4 (2025)** distinguishes **overall** and **inactivity** reauthentication. For AAL2, guidance recommends overall ≤ **24 hours (SHOULD)** and inactivity ≤ **1 hour (SHOULD)**; this is not permission to loosen a stricter legacy 30-minute/8-hour policy. Revision 3 (2017) had different recommendations; always cite the exact revision, AAL scope, and applicable regulations. If the organization requires a hard cap that never resets even on reauth, design a **separate timer**.

## 5. Policy-Parity Matrix: Locking Down Testable Requirements

| Dimension | Hypothetical Legacy | Candidate No Weaker Than | Negative/Positive Test |
| --- | --- | --- | --- |
| Local logout | POST + CSRF, session invalid | Preserved accurately | Old cookie after POST → DENY |
| RP-initiated global | Option to log out upstream | Equivalent exists | OP session and other RPs tested |
| IdP-initiated logout | Revokes related sessions | Not dropped | Signed event → no access |
| User/admin revoke | Reflected within SLA | Not relaxed | Disable user mid-session |
| Basic login assurance | Trusted issuer/account | No issuer/tenant mix-up | Unknown IdP → DENY |
| Sensitive MFA | Fresh MFA ≤10 min | ≤10 min | 9m59s PASS, 10m STEP_UP |
| Phishing-resistant admin | Mandatory | Still mandatory | OTP-only denied |
| Idle session | 30 min | ≤30 min | Frozen clock boundary |
| Overall session | 8 hours | ≤8 hours | Active user still expires |
| Max simultaneous | 2 | ≤2 | Third login policy |
| Session fixation | Rotate session ID | Preserved | Old ID denied |
| Remember-me | Low risk only | Never grants high risk | Remember-me → STEP_UP |
| JWT/refresh token | Revocation with SLA | Not dropped | Old token after logout |
| Multi-node enforcement | Shared session view | Same or stricter | Node A/B |
| Failure handling | No fail-open | No fail-open | OP outage, unknown ACR |

### 5.1. Comparisons That Cannot Be Numeric Alone

**Time and count** can be compared directly:

~~~text
new.idle <= approved.idle
new.overall <= approved.overall
new.mfaMaxAge <= approved.mfaMaxAge
new.maxConcurrentSessions <= approved.maxConcurrentSessions
~~~

**Assurance** must use mappings validated by the IdP/security owner—never compare `acr` strings blindly. `acr="2"` at OP A does not automatically equal `acr="2"` at OP B, and `amr=["pwd","otp"]` does not automatically satisfy **phishing resistance**. Missing/unclear evidence → `UNKNOWN` and **deny/step-up**.

**Logout scope** must compare postconditions. If legacy cleared all application sessions on an IdP event, a candidate clearing only the current browser is a **regression**, even if both URLs contain "logout."

## 6. Local Logout: Foundational Invariants

In Spring Security Servlet, local logout via `LogoutFilter`/`LogoutHandler` clears Authentication and session per configuration. Example:

~~~java
// Spring Security Servlet fragment; requires imports/dependencies.
http.logout(l -> l
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID"));
~~~

With **CSRF enabled** (default on Spring Servlet), keep **`POST /logout` with CSRF**. Switching to unauthenticated GET logout "for link convenience" can introduce logout CSRF. When using Spring Session, the cookie name is typically `SESSION` rather than `JSESSIONID`; adjust for your real app.

After logout:

- The old local `HttpSession` is invalidated in the server store, not just deleted from browser cookies.
- Old cookies/headers/session IDs cannot fetch protected content.
- Spring `SecurityContextRepository` / custom authentication filters never retain stale context.
- The browser may re-authenticate via SSO if the upstream IdP session remains alive; that is a **fresh login**, not proof that local logout failed.
- Downstream tokens / refresh token families require separate policy handling: clearing a local cookie does not revoke still-valid JWTs.
- Multi-tab and multi-node requests see the same outcome; concurrent logout/reauth races never resurrect sessions.

**Never check only `HTTP 302` to `/login`.** Replay the old cookie against a protected endpoint and assert the security outcome.

## 7. OIDC Logout: Local, RP-Initiated, and Back-Channel

Modern Spring Security supports three use cases via OAuth2 Login.

### 7.1. RP-Initiated Logout

`OidcClientInitiatedLogoutSuccessHandler` can redirect the browser to `end_session_endpoint` from OP discovery:

~~~java
@Bean
SecurityFilterChain oidcChain(
        HttpSecurity http,
        ClientRegistrationRepository clients) throws Exception {
    OidcClientInitiatedLogoutSuccessHandler handler =
        new OidcClientInitiatedLogoutSuccessHandler(clients);
    handler.setPostLogoutRedirectUri("{baseUrl}");
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(l -> l.logoutSuccessHandler(handler));
    return http.build();
}
~~~

This is a Spring integration fragment requiring proper imports/client registrations; **it does not compile standalone with `javac`**. It requires OP discovery/`end_session` support and an allowlisted `post_logout_redirect_uri`. A successful redirect to the OP **does not guarantee** other RPs were logged out; IdP propagation is the responsibility of the OP and other clients. If the UI says "Sign out of all devices," verify the real scope.

### 7.2. OP-Initiated OIDC Back-Channel Logout

Spring Security Servlet:

~~~java
@Bean
SecurityFilterChain oidcBackChannel(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(o -> o.backChannel(Customizer.withDefaults()));
    return http.build();
}
~~~

The default endpoint is `POST /logout/connect/back-channel/{registrationId}`; the OP sends a signed **Logout Token** JWT. Validate signature/alg, `iss`, `aud`, `iat`/`exp`, `events`, `sub` or `sid`, `jti` replay, and **absence of `nonce`** per the OIDC Back-Channel Logout spec. Never accept user-controlled HTTP `?sub=alice` as a logout signal.

Scope:

- `sid` present: invalidates the matching **OP session** within that exact client/issuer; never destroys all browsers for the user when targeting one session.
- Only `sub` present: invalidates sessions matching **issuer/client/subject** per profile.
- Both `sid` and `sub` present: verify both belong to the same identity and never invalidate another user's session.
- Wrong issuer, audience, `jti`, or signature: reject.
- Duplicate event: replay controls / idempotency; never create new sessions or delete wrong ones.

**Spring Session cookie-name trap:** Spring Security's OIDC back-channel handler defaults to `JSESSIONID`, while Spring Session typically uses `SESSION`. Official docs instruct:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler(
        OidcSessionRegistry registry) {
    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(registry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Verify `HttpSessionEventPublisher`/session registry cleanup for your version and actual invalidation behavior. **A callback returning HTTP 200 while the old cookie still authenticates is a FAIL.**

## 8. SAML2 Single Logout: RP-Initiated, AP-Initiated

Spring Security supports `saml2Logout(Customizer.withDefaults())` with a `RelyingPartyRegistration` having `SingleLogoutService` metadata and matching verification/signing credentials.

~~~java
// Spring Security fragment
http.saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

**RP-initiated SLO:** local user POSTs logout to the configured endpoint; Spring invalidates the session, creates/signs a `saml2:LogoutRequest` to the IdP; may receive `saml2:LogoutResponse` and verify signature, issuer, request correlation, and status.

**AP/IdP-initiated SLO:** IdP sends a signed `saml2:LogoutRequest` to `/logout/saml2/slo`; Spring verifies issuer/signature/NameID/`SessionIndex`/request details, logs out the matching local session, and returns a signed response.

Local logout and SAML SLO can be separated:

~~~java
http.logout(l -> l.logoutUrl("/logout"))
    .saml2Logout(s -> s.logoutUrl("/saml2/logout"));
~~~

Never assume every `POST /logout` triggers global SLO if the app separated endpoints. A validly signed `SAMLResponse` at login **does not guarantee the IdP supports SLO**; verify `SingleLogoutService` metadata and run integration tests.

`SessionIndex`, `NameID`, registration/issuer, and browser/session context must map accurately; never log out Bob just because NameID/email resembles Alice. Front-channel SLO can depend on browser cookies/redirects; policies must test browser privacy/SameSite. Assertion `Conditions NotOnOrAfter` only bounds assertion acceptance, never local session TTL.

## 9. CAS Single Logout When Migrating Away from CAS

Apereo CAS maintains a **CAS SSO Session/TGC** on the CAS Server alongside local client sessions. **Local CAS app logout** and **central CAS logout** do not automatically terminate one another. CAS SLO notifies participating apps when the SSO session ends; delivery may be back-channel POST or front-channel depending on CAS version, service registry, and client support.

Tests:

1. CAS user holds multiple client applications and local sessions.
2. Central CAS logout dispatches notifications over the configured SLO channel.
3. The CAS client processes events binding **Service Ticket / Session identifier** to the exact local `HttpSession`.
4. Protected resources on each app cannot be accessed with the old cookie.
5. Offline apps, retries/timeouts, and best-effort delivery have explicit SLAs/monitoring.
6. CAS `renew=true` demands primary auth per CAS protocol and **does not automatically prove MFA**; map CAS-specific assurance attributes per IdP contract.

When migrating CAS → OIDC, do not change only the login URL. Replace **CAS SLO correlation** with OIDC logout tokens/session registry and verify equivalent effect. Never treat a CAS SLO payload as a SAML 2.0 IdP-initiated `LogoutRequest` for a SAML SP; each protocol has its own semantics and security validation.

## 10. MFA Evidence: OIDC ACR/AMR/Auth Time

### 10.1. Three Distinct Claims

- `acr`: **Authentication Context Class Reference**; values carry meaning only per IdP policy/contract. `acr="urn:example:mfa"` is merely an example.
- `amr`: **Authentication Methods References**; list of methods the OP claims were used. Not a universal assurance table; requires mapping and trust verification.
- `auth_time`: when the user **actually authenticated at the OP**, not `iat` (when the ID Token was issued). An OP may issue a fresh token from an old SSO session without a fresh `auth_time`.
- `exp`: token age bound, not an assurance or freshness claim.
- `sid`: OP session ID in certain profiles, not local `JSESSIONID`.

Example mapping **requiring security owner approval**:

~~~text
trusted issuer=https://idp.example.test/realms/corp
acr=urn:example:basic            => PASSWORD
acr=urn:example:mfa              => VERIFIED_MFA
acr=urn:example:phishing-resist  => VERIFIED_MFA + phishingResistant=true
acr missing / unknown            => UNKNOWN; sensitive action DENIED
~~~

Never auto-promote `amr=["pwd","otp"]` to **phishing-resistant MFA**, and never assume identical `acr` labels across two IdPs are equivalent.

### 10.2. OIDC Step-Up

A protected action can request fresh authentication and assured ACR in the authorization request:

~~~text
GET /authorize?response_type=code
  &client_id=portal-client
  &redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcorp
  &state=<fresh-random-state>
  &nonce=<fresh-random-nonce>
  &max_age=600
  &acr_values=urn%3Aexample%3Amfa
~~~

This is an illustrative structure only; production must generate `state`/`nonce` via the framework, use PKCE if applicable, bind transaction/browser, and validate the ID Token. OIDC Core defines:

- `max_age`: maximum authentication age in seconds since **active authentication** at the OP; when `max_age` is sent, the ID Token **must contain `auth_time`**.
- `max_age=0` equals `prompt=login`, which **does not automatically mean MFA**. Fresh password-only auth still fails sensitive policies.
- `acr_values` is normally voluntary; if the RP needs mandatory assurance and the OP supports `claims`, it may request **Essential `acr`** per OIDC Core, while still validating the returned claims.
- If `acr` is missing/wrong, `auth_time` is too old, `iss`/`aud`/`nonce` fails, or the user subject changed, **do not execute the sensitive action**.
- Custom `OAuth2AuthorizationRequestResolver`/`DefaultOAuth2AuthorizationRequestResolver` can add provider-specific parameters, yet must never drop `AuthorizationRequestRepository`/state correlation.

Step-up results may be accepted only for **the same trusted issuer+subject+tenant**, never allowing silent account switching or attacker-triggered account linking.

## 11. SAML MFA: `RequestedAuthnContext`, `ForceAuthn`, and `AuthnInstant`

A SAML `AuthnRequest` may carry:

- `ForceAuthn="true"`: asks the IdP for **fresh authentication** per SAML, not necessarily MFA if the IdP only uses passwords.
- `RequestedAuthnContext`/`AuthnContextClassRef`: SP states requested context; URN meanings depend on IdP/federation agreement.
- `Comparison="exact"` or other modes per SAML profile; never rank arbitrary vendor ACRs on your own.
- Resulting `Assertion/AuthnStatement/AuthnContext` and `AuthnInstant` must be verified (after XMLDSig/issuer/audience/subject validations).

**Unsigned** structural example showing element placement only:

~~~xml
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                   ForceAuthn="true">
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef
        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
      urn:example:mfa
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

Spring Security 7 / OpenSAML 5 provides `OpenSaml5AuthenticationRequestResolver.setAuthnRequestCustomizer`:

~~~java
@Bean
Saml2AuthenticationRequestResolver resolver(
        RelyingPartyRegistrationRepository registrations) {
    RelyingPartyRegistrationResolver r =
        new DefaultRelyingPartyRegistrationResolver(registrations);
    OpenSaml5AuthenticationRequestResolver x =
        new OpenSaml5AuthenticationRequestResolver(r);
    x.setAuthnRequestCustomizer(c ->
        c.getAuthnRequest().setForceAuthn(true));
    return x;
}
~~~

This is a Spring integration fragment, not standalone Java. Wire the resolver into the actual SAML filter. `ForceAuthn` on the request is only an **intent**; sensitive actions must check the **actual context and timestamp in the response**. **IdP-initiated SSO** has no SP `AuthnRequest`; for privileged operations, require trusted outcome assurance or an SP-initiated step-up flow.

CAS `renew=true` or Kerberos/SPNEGO automatic SSO likewise **does not automatically equal fresh MFA**. Trusted proxy headers may be used only when the proxy enforces auth and strips/overrides client-supplied headers.

## 12. Spring Session Policy: Idle, Overall, MFA Freshness

Illustrative Spring Boot Servlet config:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

`server.servlet.session.timeout` normally governs **idle session timeout**, not an 8-hour overall limit, an issuance hard cap, or 10-minute MFA freshness. With Spring Session/Redis, verify the real store TTL and cookie name. Cookie `Max-Age` cannot replace server invalidation; ID Token expiry does not clear `SecurityContext` automatically.

Spring Security session fixation/concurrency fragment:

~~~java
http.sessionManagement(s -> s
    .sessionFixation(f -> f.newSession())
    .maximumSessions(2));
~~~

You need a session registry/event publisher and real distributed-session enforcement when deploying multiple nodes. Never treat single-node `maximumSessions` as proof across two replicas.

A server-side policy service design should store:

~~~text
sessionEstablishedAt
lastVerifiedAuthenticationAt  (auth_time/AuthnInstant trusted)
lastActivityAt                (valid user activity per policy only)
lastVerifiedMfaAt             (not reset by token refresh)
verifiedAssuranceClass        (issuer-specific mapping)
phishingResistanceEvidence    (verified and scoped)
localUser/issuer/client/tenant/subject
sessionVersion, revokedAt, policyVersion
~~~

On every sensitive request:

1. Verify the local user is active and issuer/client/tenant bindings match.
2. Check idle, overall session, and hard cap if configured.
3. Check role/business permission.
4. Check trusted MFA evidence and freshness; if insufficient, **`STEP_UP`**.
5. Never accept client HTTP headers/claims directly as evidence.
6. Ensure step-up callbacks belong to **the same account**, with no replay/CSRF, and process the action once.
7. Session logout/revocation must invalidate local state and never be recreated from stale caches.

**User activity does not reset overall timeout or MFA freshness.** Only genuine reauthentication refreshes the corresponding proof.

## 13. Cutover Scenarios That Easily Go Wrong

### 13.1. Legacy Had MFA, New Has Only Matching Email

~~~text
Legacy CAS:
  alice, verified MFA, ROLE_APPROVER.

New OIDC:
  email=alice@example.test
  new iss/subject; acr missing; old auth_time.

DO NOT:
  copy lastMfaAt/ROLE_APPROVER from old session just because email matches.

MUST:
  verify IdP issuer/client/subject/tenant and account linking,
  map assurance evidence per policy, reload local authorization.
  If evidence is missing: step-up/re-auth, do not approve action.
~~~

### 13.2. Local Logout Succeeds Yet User Re-SSOs Immediately

If the logout contract is **`LOCAL_ONLY`**, this may be expected. If the contract is **`GLOBAL`**, you need OP `end_session` / SAML SLO / CAS central logout and verification that other sessions were cleared. Never guess from the login UI.

### 13.3. IdP Remote Logout and Two Browsers

Alice's Browser A and B hold two OP `sid`s; Bob holds another session. A Logout Token with `sid=A` revokes only session A. A token with only `sub=alice` may revoke all matching sessions for Alice under that same client/issuer. Never scope by email; never revoke Bob.

### 13.4. Sensitive Resource After Reused SSO

A new ID Token has `iat=now` yet `auth_time=now-2h`; app policy requires MFA within 10 minutes. **Deny/`STEP_UP`**, never mistaking fresh `iat` for fresh MFA. If `max_age` or Essential ACR is not satisfied by the OP, the sensitive action remains denied.

### 13.5. Session Expiration and Activity

With 30-minute idle and 8-hour overall:

~~~text
lastActivityAt=10:00Z
At 10:29:59Z: idle still valid
At 10:30:00Z: idle expired (inclusive boundary policy)

lastVerifiedReauthAt=02:00Z
At 10:00:00Z: 8-hour overall expired,
  despite an active HTTP request at 09:59:59Z.
~~~

Clock-skew handling, Redis TTL/`lastAccessedTime`, and browser cookies must be tested against **exact project criteria**, using clock injection rather than long `Thread.sleep()` calls in CI.

### 13.6. User Disabled Mid-Session

When IAM disables an account, a previously validated OIDC ID Token or SAML Assertion **does not vanish on its own**. Require logout/revocation events, local user-status checks, or another mechanism to meet the **revocation SLA**. If a JWT access token lacks introspection/revocation/sufficiently short lifetime, never promise "immediate revocation" when APIs still accept the token.

## 14. Regression Test Matrix

| ID | Input | Expected |
| --- | --- | --- |
| L01 | Local POST logout + valid CSRF | Old session cookie denied |
| L02 | Unintended cross-site GET logout | No unauthorized logout |
| L03 | OIDC RP `end_session` | Right OP/redirect, local session clean |
| L04 | OP Logout Token with valid `sid` | Only that mapped session revoked |
| L05 | OP Logout Token with only `sub` | Matching sessions for same issuer/client revoked |
| L06 | Forged OIDC Logout Token / wrong `iss`/`aud`/`events` | Reject, never revoke another user |
| L07 | Logout Token with mismatched `sid`/`sub` | Never revoke wrong session |
| L08 | OIDC `jti` replay | Idempotent / replay controls |
| L09 | Spring Session cookie named `SESSION` | Back-channel handler maps properly |
| L10 | Signed SAML AP `LogoutRequest` + `SessionIndex` | Corresponding session revoked |
| L11 | SAML wrong issuer/signature/`SessionIndex` | Reject |
| L12 | SAML RP `LogoutResponse` mismatch/replay | Reject per protocol; local cleanup intact |
| L13 | CAS SLO event | CAS client invalidates right local session |
| L14 | IdP/OP logout yet one node stays active | Parity FAIL |
| L15 | User disabled mid-session | Enforcement meets SLA |
| M01 | Fresh verified MFA | Sensitive action ALLOW |
| M02 | MFA expired while local session active | STEP_UP / DENY |
| M03 | Old OIDC `auth_time`, fresh `iat` | Never treated as fresh |
| M04 | OIDC Essential ACR not satisfied | Deny sensitive action |
| M05 | OIDC `max_age` sent yet ID Token lacks `auth_time` | Deny / validation failure |
| M06 | `prompt=login` with password-only | Never infer MFA |
| M07 | SAML `ForceAuthn` yet weak `AuthnContext` | Never grant sensitive authorization |
| M08 | CAS `renew` yet missing assurance claim | Unknown → step-up |
| M09 | Wrong issuer/tenant sharing email | Never share MFA/roles |
| M10 | Non-phishing-resistant MFA when policy requires it | Deny |
| T01 | 29m59s idle against 30-min limit | Pass if other limits valid |
| T02 | 30m00s idle | Expire |
| T03 | Overall 8h reauth with recent activity | Expire / reauth |
| T04 | Long cookie `Max-Age` yet expired server TTL | Deny |
| T05 | ID Token `exp` passed while app session alive | Do not conflate the two TTLs |
| T06 | Silent refresh issues new token | Does not reset `lastMfaAt` |
| T07 | Concurrent sessions exceed cap | Limit enforced across multiple nodes |
| T08 | Session fixation before/after login | Session ID rotated, old ID invalid |
| T09 | Remember-me user accesses admin | Requires fresh MFA |
| T10 | Token/API access after logout | Follows revocation policy, no fail-open |
| C01 | Legacy sessions exist at cutover | Force reauth or approved bridge design |
| C02 | Rollback after user logged out | Revoked session never resurrected |
| C03 | Late step-up callback after logout | Must not create a new authenticated session |
| C04 | Cross-tenant OP logout event | Must not affect other tenants |
| C05 | Canary passes on one node, other node misses logout | NO-GO |
| C06 | Wrong ACR mapping on mobile client only | High-risk NO-GO |
| C07 | IdP unavailable when step-up needed | Deny sensitive action with clear error |
| C08 | Positive baseline with validly signed assertion/token | Login and permissions accurate |

**Do not assert only HTTP 200/302/401.** A failure handler can redirect 302, and an old `SecurityContext` might linger; assert **exact subject/tenant/roles**, session registry state, revocation, and downstream authorization.

## 15. Standalone Java 17: Policy Parity, MFA Freshness, and Logout Scope

The following example **runs via `javac --release 17`** without IdP or Spring. It checks that a candidate policy is no weaker than the approved policy, modeling assurance evidence, session expiry, and remote/local logout.

**Important boundary:** `VerifiedLogout.proofVerified`/`Session.evidence` represent **trusted mock-verifier outcomes in tests**, never raw unverified HTTP request/JWT values in production. This code does not perform JWT/XML signatures, JWK, X.509, OAuth state/PKCE, CAS ticket validation, browser cookies, database concurrency, or distributed replay caches. `HashMap`/`HashSet` are not thread-safe, and the `UNKNOWN < PASSWORD < VERIFIED_MFA` ordinal scale is an **illustrative internal ranking**, not a universal ACR definition for every IdP.

File **`FederationPolicyMigrationDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class FederationPolicyMigrationDemo {
    static final Instant NOW = Instant.parse("2026-11-07T10:00:00Z");
    static final String ISSUER = "https://idp.example.test/realms/corp";
    static final String CLIENT = "portal-client";

    enum Assurance { UNKNOWN, PASSWORD, VERIFIED_MFA }
    enum Action { READ, TRANSFER }
    enum Verdict {
        ALLOW, NO_SESSION, WRONG_CONTEXT, IDLE_EXPIRED,
        OVERALL_EXPIRED, INSUFFICIENT_ASSURANCE,
        MFA_TOO_OLD, PHISHING_RESISTANCE_REQUIRED
    }

    record Policy(Duration idle, Duration overall,
                  Duration sensitiveMaxAge, Assurance baseline,
                  Assurance sensitive, boolean remoteLogoutRequired,
                  boolean phishingResistantForSensitive,
                  int maxConcurrentSessions) {}

    record Session(String localId, String providerSid, String issuer,
                   String client, String subject, String tenant,
                   Instant lastReauthAt, Instant lastActivityAt,
                   Instant lastMfaAt, Assurance evidence,
                   boolean phishingResistant, boolean revoked) {}

    record VerifiedLogout(String issuer, String client, String sid,
                          String sub, String jti, boolean proofVerified) {}

    static final Policy APPROVED = new Policy(Duration.ofMinutes(30),
        Duration.ofHours(8), Duration.ofMinutes(10),
        Assurance.PASSWORD, Assurance.VERIFIED_MFA, true, true, 2);

    static boolean noWeaker(Policy old, Policy candidate) {
        return candidate.idle().compareTo(Duration.ZERO) > 0
            && candidate.overall().compareTo(Duration.ZERO) > 0
            && candidate.sensitiveMaxAge().compareTo(Duration.ZERO) > 0
            && candidate.idle().compareTo(old.idle()) <= 0
            && candidate.overall().compareTo(old.overall()) <= 0
            && candidate.sensitiveMaxAge().compareTo(
                   old.sensitiveMaxAge()) <= 0
            && candidate.baseline().ordinal() >= old.baseline().ordinal()
            && candidate.sensitive().ordinal() >= old.sensitive().ordinal()
            && (!old.remoteLogoutRequired()
                || candidate.remoteLogoutRequired())
            && (!old.phishingResistantForSensitive()
                || candidate.phishingResistantForSensitive())
            && candidate.maxConcurrentSessions() >= 1
            && candidate.maxConcurrentSessions()
                <= old.maxConcurrentSessions();
    }

    static Policy changed(Duration idle, Duration overall,
            Duration mfaAge, Assurance baseline, Assurance sensitive,
            boolean remoteLogout, boolean phishingResistant,
            int maxSessions) {
        return new Policy(idle, overall, mfaAge, baseline, sensitive,
            remoteLogout, phishingResistant, maxSessions);
    }

    static Session testSession(String localId, String providerSid,
            String subject, Instant reauth, Instant activity,
            Instant mfa, Assurance evidence, boolean phishingResistant) {
        return new Session(localId, providerSid, ISSUER, CLIENT,
            subject, "tenant-A", reauth, activity, mfa, evidence,
            phishingResistant, false);
    }

    static Verdict access(Policy p, Session s, Action action,
            String issuer, String client, String tenant, Instant now) {
        if (s == null || s.revoked()) return Verdict.NO_SESSION;
        if (!issuer.equals(s.issuer()) || !client.equals(s.client())
                || !tenant.equals(s.tenant())) return Verdict.WRONG_CONTEXT;
        if (s.lastActivityAt() == null
                || !now.isBefore(s.lastActivityAt().plus(p.idle())))
            return Verdict.IDLE_EXPIRED;
        if (s.lastReauthAt() == null
                || !now.isBefore(s.lastReauthAt().plus(p.overall())))
            return Verdict.OVERALL_EXPIRED;
        Assurance needed = action == Action.TRANSFER
            ? p.sensitive() : p.baseline();
        if (s.evidence() == null
                || s.evidence().ordinal() < needed.ordinal())
            return Verdict.INSUFFICIENT_ASSURANCE;
        if (action == Action.TRANSFER) {
            if (s.lastMfaAt() == null
                    || !now.isBefore(
                        s.lastMfaAt().plus(p.sensitiveMaxAge())))
                return Verdict.MFA_TOO_OLD;
            if (p.phishingResistantForSensitive()
                    && !s.phishingResistant())
                return Verdict.PHISHING_RESISTANCE_REQUIRED;
        }
        return Verdict.ALLOW;
    }

    static final class LocalSessions {
        final Map<String, Session> sessions = new HashMap<>();
        final Set<String> seenJti = new HashSet<>();

        void add(Session s) { sessions.put(s.localId(), s); }
        boolean active(String id) {
            Session s = sessions.get(id);
            return s != null && !s.revoked();
        }
        void localLogout(String id) { sessions.remove(id); }

        int remoteLogout(VerifiedLogout e) {
            // proofVerified must come from complete trusted JWT verification!
            if (e == null || !e.proofVerified() || e.jti() == null
                    || e.jti().isBlank() || e.issuer() == null
                    || e.client() == null
                    || (e.sid() == null && e.sub() == null)
                    || !seenJti.add(e.jti())) return 0;
            int affected = 0;
            for (Session s : sessions.values()) {
                if (s.revoked() || !s.issuer().equals(e.issuer())
                        || !s.client().equals(e.client())) continue;
                boolean match = e.sid() != null
                    ? e.sid().equals(s.providerSid())
                        && (e.sub() == null || e.sub().equals(s.subject()))
                    : e.sub().equals(s.subject());
                if (match) {
                    sessions.put(s.localId(), new Session(
                        s.localId(), s.providerSid(), s.issuer(),
                        s.client(), s.subject(), s.tenant(),
                        s.lastReauthAt(), s.lastActivityAt(),
                        s.lastMfaAt(), s.evidence(),
                        s.phishingResistant(), true));
                    affected++;
                }
            }
            return affected;
        }
    }

    static void check(String name, boolean condition) {
        System.out.println(name + "=" + condition);
        if (!condition) throw new AssertionError(name);
    }

    public static void main(String[] args) {
        Policy p = APPROVED;
        check("samePolicyAccepted", noWeaker(p, p));
        check("stricterIdleAccepted", noWeaker(p, changed(
            Duration.ofMinutes(20), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedIdleRejected", !noWeaker(p, changed(
            Duration.ofMinutes(45), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedOverallRejected", !noWeaker(p, changed(
            p.idle(), Duration.ofHours(9), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedMfaAgeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), Duration.ofMinutes(20),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("mfaDowngradeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), Assurance.PASSWORD, true, true, 2)));
        check("missingRemoteLogoutRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), false, true, 2)));
        check("phishingResistanceDowngradeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, false, 2)));
        check("moreSessionsRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 3)));

        Session alice = testSession("local-A", "op-sid-A", "alice",
            NOW.minusSeconds(60), NOW.minusSeconds(30),
            NOW.minusSeconds(60), Assurance.VERIFIED_MFA, true);
        check("normalAllowed",
            access(p, alice, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.ALLOW);
        check("freshMfaAllowed",
            access(p, alice, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.ALLOW);

        Session password = testSession("local-P", "op-sid-P", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(5), null,
            Assurance.PASSWORD, false);
        check("passwordOnlyCannotTransfer",
            access(p, password, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.INSUFFICIENT_ASSURANCE);
        Session unknown = testSession("local-U", "op-sid-U", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(5), null,
            Assurance.UNKNOWN, false);
        check("unknownAssuranceNotMfa",
            access(p, unknown, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.INSUFFICIENT_ASSURANCE);

        Session oldMfa = testSession("local-M", "op-sid-M", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(5),
            NOW.minusSeconds(601), Assurance.VERIFIED_MFA, true);
        check("oldMfaRequiresStepUp",
            access(p, oldMfa, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.MFA_TOO_OLD);
        Session notResistant = testSession("local-O", "op-sid-O", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(5),
            NOW.minusSeconds(20), Assurance.VERIFIED_MFA, false);
        check("notPhishingResistantRejected",
            access(p, notResistant, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.PHISHING_RESISTANCE_REQUIRED);

        Session idle = testSession("local-I", "op-sid-I", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(1800),
            NOW.minusSeconds(20), Assurance.VERIFIED_MFA, true);
        check("idleBoundaryExpired",
            access(p, idle, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.IDLE_EXPIRED);
        Session overall = testSession("local-H", "op-sid-H", "alice",
            NOW.minus(Duration.ofHours(9)), NOW.minusSeconds(3),
            NOW.minusSeconds(3), Assurance.VERIFIED_MFA, true);
        check("overallExpiredDespiteActivity",
            access(p, overall, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.OVERALL_EXPIRED);
        check("issuerMismatchRejected",
            access(p, alice, Action.READ, "https://wrong.example.test",
                CLIENT, "tenant-A", NOW) == Verdict.WRONG_CONTEXT);
        check("tenantMismatchRejected",
            access(p, alice, Action.READ, ISSUER, CLIENT,
                "tenant-B", NOW) == Verdict.WRONG_CONTEXT);
        check("clientMismatchRejected",
            access(p, alice, Action.READ, ISSUER, "other-client",
                "tenant-A", NOW) == Verdict.WRONG_CONTEXT);

        LocalSessions registry = new LocalSessions();
        registry.add(alice);
        registry.add(testSession("local-B", "op-sid-B", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(10),
            NOW.minusSeconds(30), Assurance.VERIFIED_MFA, true));
        registry.add(testSession("local-C", "op-sid-C", "bob",
            NOW.minusSeconds(30), NOW.minusSeconds(10),
            NOW.minusSeconds(30), Assurance.VERIFIED_MFA, true));

        check("forgedLogoutRejected",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", null, "jti-fake", false)) == 0);
        check("forgedLogoutPreservesSession",
            registry.active("local-A"));
        check("wrongIssuerLogoutDoesNothing",
            registry.remoteLogout(new VerifiedLogout(
                "https://wrong.example.test", CLIENT,
                "op-sid-A", null, "jti-wrong-issuer", true)) == 0);
        check("wrongClientLogoutDoesNothing",
            registry.remoteLogout(new VerifiedLogout(ISSUER,
                "other-client", "op-sid-A", null,
                "jti-wrong-client", true)) == 0);
        check("sidSubMismatchDoesNothing",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", "bob", "jti-both", true)) == 0);
        check("sidLogoutRevokesOnlyTarget",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", null, "jti-sid", true)) == 1);
        check("sidLogoutLeavesOtherSession",
            registry.active("local-B"));
        check("sidLogoutLeavesOtherUser",
            registry.active("local-C"));
        check("logoutJtiReplayRejected",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-B", null, "jti-sid", true)) == 0);
        check("subjectLogoutRevokesRemainingAlice",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                null, "alice", "jti-sub", true)) == 1);
        check("subjectLogoutLeavesBobActive",
            registry.active("local-C"));
        registry.localLogout("local-C");
        check("localLogoutClearsOwnSession",
            !registry.active("local-C"));
        check("localLogoutIsNotGlobalLogout",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-C", null, "jti-local", true)) == 0);
    }
}
~~~

Run:

~~~bash
javac --release 17 FederationPolicyMigrationDemo.java
java FederationPolicyMigrationDemo
~~~

**Expected stdout after compile/run:**

~~~text
samePolicyAccepted=true
stricterIdleAccepted=true
relaxedIdleRejected=true
relaxedOverallRejected=true
relaxedMfaAgeRejected=true
mfaDowngradeRejected=true
missingRemoteLogoutRejected=true
phishingResistanceDowngradeRejected=true
moreSessionsRejected=true
normalAllowed=true
freshMfaAllowed=true
passwordOnlyCannotTransfer=true
unknownAssuranceNotMfa=true
oldMfaRequiresStepUp=true
notPhishingResistantRejected=true
idleBoundaryExpired=true
overallExpiredDespiteActivity=true
issuerMismatchRejected=true
tenantMismatchRejected=true
clientMismatchRejected=true
forgedLogoutRejected=true
forgedLogoutPreservesSession=true
wrongIssuerLogoutDoesNothing=true
wrongClientLogoutDoesNothing=true
sidSubMismatchDoesNothing=true
sidLogoutRevokesOnlyTarget=true
sidLogoutLeavesOtherSession=true
sidLogoutLeavesOtherUser=true
logoutJtiReplayRejected=true
subjectLogoutRevokesRemainingAlice=true
subjectLogoutLeavesBobActive=true
localLogoutClearsOwnSession=true
localLogoutIsNotGlobalLogout=true
~~~

### 15.1. Explaining the Meaning

- The policy gate rejects relaxing idle/overall/MFA max age/concurrent sessions and dropping remote logout or phishing resistance.
- Valid users are allowed READ/TRANSFER with sufficient proof. Password-only or unknown assurance never grants privileged actions.
- Active users still hit overall timeout; sensitive actions still require fresh MFA.
- Forged/wrong-issuer/wrong-client Logout Tokens never revoke sessions; mismatched `sid`+`sub` never mistakenly logs out Bob.
- `sid` logout revokes only one OP session; `sub` logout revokes matching sessions for that user/client/issuer.
- Replayed event `jti`s produce no further effect; local logout of one session never claims entire IdP SSO ended.

The demo **does not replace** Spring Security's real OIDC Logout Token verifier, SAML SLO, CAS client, business policy engine, or distributed session registry.

## 16. Phased Rollout Plan

**P0 — Baseline:** capture real legacy policies, endpoints, issuers/tenants, sessions, MFA settings, logout propagation, revocation SLAs, and business owners. Finalize the policy-parity matrix signed off by the security owner.

**P1 — Mapping:** define trusted assurance adapters per protocol, timeout sources of truth, local vs. global logout endpoints, and OIDC/SAML/CAS callback verifiers. Never turn unknown ACRs into MFA.

**P2 — Dual-run in test/canary:** execute the same user journeys on legacy and candidate stacks, comparing `ALLOW`/`DENY`/`STEP_UP`/`LOGOUT` verdicts and local session state. Use frozen clocks, synthetic IdPs, signed fixtures, two-tab browsers, multi-node/Redis, and risk-appropriate negative tests.

**P3 — Cutover:** migrate by client/tenant/role in a controlled way; never randomly split a single browser's requests across two stacks. Prefer **invalidating legacy sessions and requiring re-login** rather than importing assurance/roles by email. If bridging is unavoidable, require an explicit signed design, short TTL, and approval. Monitor logout event latency, forced reauth, MFA step-up success, unknown ACRs, and customer impact.

**P4 — Stabilize/retire:** wait for legacy sessions/tokens to be revoked or expire per plan, disable old callbacks/keys in a controlled way, archive test evidence, close the change, and update runbooks. **Rollback must never resurrect revoked or logged-out sessions.**

## 17. GO/NO-GO Before Shifting Traffic

**GO** when the policy matrix is approved and all evidence below passes:

- Local/upstream/IdP-initiated logout matches scope, callbacks are verified, and sessions are genuinely cleared across all nodes.
- Sensitive endpoints enforce trusted MFA assurance, freshness, and phishing resistance per policy.
- Idle/overall/hard-cap/MFA-freshness/concurrency limits are no weaker than baseline; boundaries are tested.
- A user/account/tenant cannot leverage claims or logout events from another issuer/client.
- Disabled users / revoked accounts / revoked tokens are denied within SLA.
- Real signed OIDC/SAML/CAS integrations pass positive and negative tests.
- Canary/metrics/log redaction, support escalation, and rollback strategies are ready.
- Old cookies/sessions/tokens are tested to create no backdoor.

**NO-GO** if any of the following are found:

- Only local logout is supported when legacy mandated global logout.
- OIDC Logout Token omits signature/`iss`/`aud`/`events`/`jti` validation.
- SAML SLO omits issuer/`SessionIndex` checks or logs out the wrong user.
- Unknown/expired MFA evidence still allows a privileged action to succeed.
- Token `iat` is used instead of `auth_time` when fresh auth is required.
- Idle time increased, overall timeout was dropped, or remember-me bypasses MFA.
- A Spring replica lacks the session registry or back-channel handler.
- Rollback resurrects old sessions, or logout callbacks are silently lost without alerts.

Intentional policy changes must be documented as an **approved risk exception**, never labeled parity PASS.

## 18. Error Observation and Runbook

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| Logs out of app then silently re-SSOs | IdP session remains alive | Local-only vs. global contract? |
| OP logout 200 yet old cookie still works | Wrong session cookie / registry mapping | `JSESSIONID` vs. `SESSION`, Redis invalidation |
| SAML SLO revokes another user | Wrong NameID/`SessionIndex` scope | Signed `LogoutRequest` + mapped session |
| CAS SLO never reaches app | Callback / client registry | CAS delivery logs / connection |
| Step-up loop | OP lacks `acr`/claims support or session state lost | ID Token `auth_time`/`acr`, `state`/`nonce` |
| MFA bypassed after migration | Unknown ACR trusted or `iat` used | Approved mapping and timestamps |
| Local session never expires | Timer reset/stored incorrectly | `lastActivityAt` vs. `lastReauthAt` |
| Revoked user still calls API | Bearer token still valid | API revocation/introspection controls |
| Error occurs on one node only | Session store / config drift | Replica policy version and store |
| Logged-out session revives itself | Race/stale cache or rollback | Atomic revoke / versioned sessions |
| Spike in 403s after cutover | Roles vs. MFA vs. local user status | Separate authorization reason codes |

Logs/metrics should carry only **policy version, registration alias, event type, reason category, elapsed time, and pseudonymous correlation ID**. Never log raw Logout Tokens, ID Tokens, `SAMLResponse`s, Service Tickets, NameIDs/emails, session cookies, or MFA secrets. Monitor:

~~~text
federation_logout_event_validated_total
federation_logout_session_invalidation_total
federation_remote_logout_failed_total
federation_stepup_required_total
federation_unknown_assurance_denied_total
federation_session_idle_expired_total
federation_session_overall_expired_total
federation_policy_parity_regression_total
~~~

**Runbook:** identify protocol/issuer/client and local sessions → pick the first event → verify source and mapping → inspect `SecurityContext`/session store → reconcile MFA/time policy → test old cookie/token against a protected endpoint → fix the right layer → run positive+negative+multi-node tests → obtain security owner sign-off.

## 19. Completion Checklist

- [ ] Legacy and candidate logout/MFA/timeout policies have owners and an approved baseline.
- [ ] Local `POST` + CSRF logout clears session and `SecurityContext` accurately.
- [ ] OP/SAML/CAS SLO matches protocol semantics, not just a UI redirect.
- [ ] Complete OIDC back-channel `sid`/`sub`/`iss`/`aud`/`jti`/signature validation.
- [ ] Session cookie `JSESSIONID`/`SESSION` matches handlers and Spring Session.
- [ ] SAML `SessionIndex`/NameID/issuer bind to the exact local session.
- [ ] CAS SLO notifications are handled with Service Ticket-to-session mapping.
- [ ] Admin revocation / disabled users / token denials meet SLA.
- [ ] OIDC ACR/AMR/`auth_time` mappings are approved by IdP/security owners.
- [ ] SAML `ForceAuthn`/`RequestedAuthnContext` are verified via output `AuthnContext`/`AuthnInstant`.
- [ ] `prompt=login`, `max_age`, and CAS `renew` are not automatically treated as MFA.
- [ ] Unknown assurance is never promoted to MFA.
- [ ] MFA freshness resets only after trusted fresh MFA.
- [ ] Phishing resistance is verified whenever required by policy.
- [ ] Idle timer and overall reauth timer operate independently; separate hard cap if required.
- [ ] Cookie `Max-Age`, ID Token `exp`, and SAML assertion TTL are never confused with local session TTL.
- [ ] Session fixation protection, concurrent sessions, remember-me, and multi-node behavior are accurate.
- [ ] Late step-up callbacks arriving after logout cannot recreate a session.
- [ ] External account keys use trusted issuer/client/tenant/subject, not email alone.
- [ ] Legacy sessions/roles/MFA evidence are not auto-copied onto new logins.
- [ ] Rollback never revives revoked sessions or old trusted access tokens.
- [ ] Positive tests, negative tests, exact boundary tests, and integration tests all pass.
- [ ] Zero credentials/PII in logs; session IDs never exposed in URLs.
- [ ] Go/No-Go gate, rollback, observability, and post-cutover ownership are in place.

## 20. Self-Check Questions

**1. Does local logout always end the IdP session?** No. The local session and upstream SSO session are two separate lifecycles.

**2. Is ID Token `exp` the local `HttpSession` deadline?** Not by default; token validity differs from local session timeout.

**3. How does `auth_time` differ from `iat`?** `auth_time` is when the user actually authenticated at the OP; `iat` is when the token was issued and can be much newer.

**4. Are `prompt=login` or SAML `ForceAuthn` guaranteed to mean MFA?** No. They request fresh authentication per protocol semantics; verify the resulting assurance class.

**5. What does an OIDC Logout Token's `sid` target?** One OP session; whereas `sub` can target all sessions for that user within the exact issuer/client per profile.

**6. Why does the local `SESSION` cookie name matter for OIDC back-channel logout?** Spring defaults to `JSESSIONID`; if named differently without configuration, mapping/invalidation can fail.

**7. Is CAS SLO the same as SAML2 SLO?** No. CAS protocol uses ticket-to-session notifications; SAML uses signed `LogoutRequest`/`LogoutResponse` and `SessionIndex`.

**8. Can a very active user continue after overall reauth expires?** No if policy requires reauth; activity resets only idle time.

**9. Can `lastMfaAt` be kept from a legacy session when email matches the new OIDC user?** Not automatically; verify trusted subject/issuer/tenant and fresh proof per policy.

**10. What does NIST SP 800-63B-4 specify for AAL2?** Guidance SHOULD overall ≤ 24h and idle ≤ 1h; never relax a stricter enterprise policy.

**11. Is testing that a logout callback returns 200 enough?** No. Replay old cookies and inspect local session state against protected endpoints across multiple nodes.

**12. Can a migration with PASS login yet FAIL remote logout/MFA cut over?** No, if those policies are critical requirements without an approved deviation.

## 21. Official Sources

- Spring Security **Servlet Logout**: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security **OIDC Logout, RP/Back-Channel, cookie name**: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security **SAML2 Single Logout**: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security **Session Management / fixation / concurrency**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security **OAuth2 Authorization Request Customization**: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security **SAML AuthnRequest ForceAuthn customization**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- **OpenID Connect Core 1.0** (`acr`, `amr`, `max_age`, `auth_time`, essential ACR): https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Back-Channel Logout 1.0** (Logout Token validation): https://openid.net/specs/openid-connect-backchannel-1_0.html
- **OpenID Connect RP-Initiated Logout 1.0**: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- **NIST SP 800-63B-4 Session Management (2025)**: https://pages.nist.gov/800-63-4/sp800-63b/session/
- **NIST SP 800-63B-4 Authentication Assurance Levels**: https://pages.nist.gov/800-63-4/sp800-63b/aal/
- **OASIS SAML 2.0 Core** (`AuthnContext`/`AuthnInstant`/`SessionIndex`): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OASIS SAML 2.0 Profiles** (SLO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- **Apereo CAS 8.0 Single Logout**: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
- **OWASP Session Management Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- **OWASP Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

**Conclusion:** Before migrating Spring Security federation, reconcile **logout and revocation scope**, **MFA/step-up with trusted and fresh proof**, and **idle/overall/hard-cap/concurrent-session limits**. Never confuse IdP SSO sessions, local `HttpSession`s, token expiry, and MFA freshness. Shift traffic only after the policy matrix is approved and signed protocol flows, boundary tests, multi-node invalidation, and a rollback that never revives revoked sessions are verified.