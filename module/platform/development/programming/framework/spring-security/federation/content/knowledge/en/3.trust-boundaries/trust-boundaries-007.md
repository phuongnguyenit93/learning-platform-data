# Threat Model: IdP Spoofing, Assertion Theft, and Session Hijacking

> **Module:** Spring Security – Federation. **Topic Group:** Trust Boundaries. This lesson analyzes the threat model for a Java/Spring Security application acting as a **SAML 2.0 Service Provider (SP)** when using SSO login via an Identity Provider (IdP). Differences from OpenID Connect (OIDC) are highlighted in the corresponding section; never equate a SAML assertion with an OIDC ID token or an OAuth access token.

## 1. Learning Objectives and Core Principles

After this lesson, you should be able to:

1. Trace the path of a SAML Response, identify who controls each point, and determine which data must be verified before trusting it.
2. Distinguish **IdP spoofing / trust substitution** (forging a trusted source), **assertion theft / replay** (stealing signed login credentials), and **session hijacking / fixation** (taking over an application session).
3. Place each defense at the right layer: trust/certificate configuration, SAML Response and assertion verification, single-login-session binding, replay protection, HTTP session protection, and authorization.
4. Apply these principles to Spring Security's `saml2Login()`, `RelyingPartyRegistration`, and session configuration without disabling default validations.
5. Design negative tests, monitoring logs, and incident response procedures when compromise indicators appear.

**Foundational rule:** An assertion with a valid signature only proves the signature matches **the key used to check it**. What the SP actually needs to know is: *is that the key of an IdP the SP explicitly trusts, was the assertion issued specifically for this SP, in the right login transaction, at the right time, not yet reused, and then bound to a protected application session?*

## 2. System Model, Assets, and Trust Boundaries

### 2.1. Minimal SAML Web SSO Flow

In an **SP-initiated** flow using HTTP Redirect/POST bindings:

```text
┌───────────────┐                     ┌──────────────────────┐
│ User's        │                     │ Spring App (SP)      │
│ Browser       │                     │ ACS + HttpSession    │
└───────┬───────┘                     └──────────┬───────────┘
        │ GET /dashboard                         │
        ├───────────────────────────────────────>│
        │   redirect to IdP with AuthnRequest    │
        │<───────────────────────────────────────┤
        │                                        │
        │         ┌──────────────────────┐       │
        └────────>│ IdP / login page     │       │
                  │ signs Response/Assert│       │
        ┌─────────┴──────────────────────┘       │
        │ HTML form POST SAMLResponse            │
        └───────────────────────────────────────>│ ACS
                                                 │
                   [1] IdP trust + XML sig       │
                   [2] Recipient binding         │
                   [3] Time window + anti-replay │
                   [4] Create SecurityContext    │
                   [5] Create/rotate session ID  │
        │<───────────────────────────────────────┤
        │ Set-Cookie JSESSIONID + redirect       │
        │                                        │
        ├──── Cookie JSESSIONID; GET /dashboard >│
        │                          [6] Authorization
```

**ACS** (Assertion Consumer Service) is the SP endpoint that receives `SAMLResponse` from the browser. The browser is an **untrusted transport channel**: a user or attacker can craft arbitrary HTTP requests. The SP must not trust a payload simply because it was "POSTed to ACS". IdPs are trusted per the SP's explicit configuration, never by whatever domain name or certificate the sender claims.

### 2.2. Assets to Protect

| Asset | Why It Matters | Typically Managed By |
| --- | --- | --- |
| Trust configuration: IdP entity ID, SSO endpoints, public signing keys, metadata | Determines who has authority to assert user identities | SP administrator / deployment config |
| IdP private SAML signing key | If compromised, an attacker can mint validly signed assertions | IdP/HSM/operator |
| `AuthnRequest` and correlation state | Binds a response to a login the SP actually initiated | SP, session/request store |
| `SAMLResponse` / `Assertion` / `NameID` / attributes | Authentication proof and claims carried through browser | Issued by IdP; consumed by SP |
| `entityID`, ACS URL, `Audience`, `Recipient`, `Destination` | Prevents misuse across other SPs/services | SP config and signed data |
| Assertion/response IDs and replay cache | Prevents accepting the same credential twice | SP / shared cache |
| Principal, `SecurityContext`, roles | Determines which user is attached to the request | Spring Security / application |
| Session ID, session store, cookies | Post-SSO session credential with its own lifecycle | SP and browser |
| Audit events, secret/config distribution | Detects spoofing, enables incident recovery | Operations team |

### 2.3. Boundaries to Protect

- **Boundary A – Trust configuration:** External IdP metadata/signing keys entering the list of IdPs accepted by the SP. Never allow arbitrary requests to choose a trust source or substitute a public key.
- **Boundary B – Browser → ACS:** XML/SAMLResponse submitted by the browser into the SP. Every security semantic of the message must be validated before creating `Authentication`.
- **Boundary C – Claims → account/permissions:** `NameID`/email/groups entering the internal user model. Must map accurately by issuer/tenant and enforce separate authorization checks.
- **Boundary D – Authentication → HttpSession:** Successful login turns short-lived SSO proof into a cookie-backed application session. Must rotate session ID after login, protect cookies, and manage timeout/logout.
- **Boundary E – Session → data:** An authenticated session does not mean permission to read/edit all data. Authorization must be enforced per endpoint, tenant, object, and action.

### 2.4. Adversary Capabilities and Assumption Limits

Model at least the following adversaries:

- An external actor can send arbitrary requests to ACS, host phishing pages, observe their own URLs/redirects, and attempt to replay captured payloads.
- A compromised user/device can leak assertions from the browser, proxies, logs, extensions, or monitoring tools.
- Someone with config/metadata modification rights or a supply-chain attacker can inject an unwanted IdP/key.
- A controlled tenant can try to inject tenant A's identity into tenant B if the SP supports multiple IdPs.
- XSS, CSRF, cookie theft, session fixation, or misconfigured reverse proxies can compromise an application session **even when SAML validation is completely accurate**.

Assume the **IdP signing private key has not been compromised** when analyzing standard spoofing. If the real signing key is stolen, signature verification alone cannot distinguish attacker-signed assertions; that requires incident response, key revocation/rotation, and mitigations beyond normal validation.

## 3. Threat Map

| Threat | Attacker Capability / Entry Point | Consequence | Core Mitigation |
| --- | --- | --- | --- |
| IdP spoofing | Injecting metadata/signing keys, altering `Issuer`, registering rogue IdP | SP trusts an unauthorized identity issuer | IdP/entity ID allowlist; out-of-band verified public signing keys; verify signature over right elements |
| Multi-IdP context confusion | Confusing registration/tenant, selecting keys from untrusted payload | User from IdP A accepted as belonging to IdP B | Bind registration to transaction and tenant; verify issuer/key/audience |
| XML signature wrapping | Crafting multi-assertion XML, exploiting gap between signed element and code-read element | Verified identity differs from consumed identity | Trusted parser/validator; signature-reference binding; consume only verified assertion |
| Assertion theft | Extracting `SAMLResponse` from browser/logs/proxy/telemetry | Reusing authentication proof before expiration | HTTPS, minimize credential exposure, `Recipient`/`Audience`/`InResponseTo`, short lifetime, anti-replay cache |
| SAML replay | Re-POSTing a still-valid assertion | Impersonated login or session takeover if SP reprocesses it | Atomically cache consumed IDs; enforce anti-replay even with `OneTimeUse` |
| Session fixation | Forcing victim to use a session ID known to attacker pre-login | Attacker reuses session after victim authenticates | Rotate session ID upon successful authentication |
| Session hijacking | Stealing cookies or acting via XSS/CSRF | Post-login account control without needing assertions | `Secure`, `HttpOnly`, proper `SameSite`, CSRF, XSS defenses, timeout, logout/revocation |
| Confused deputy / privilege escalation | Mis-mapping groups/emails, missing object authorization | Logged-in user acts beyond privileges | Separate authentication/authorization, issuer+subject mapping, RBAC/ABAC/object checks |

Do not assign absolute severity ratings across all systems. Prioritize based on exploitability and concrete impact: admin logins, customer data, multi-tenancy, ACS exposure, metadata governance, and session storage method.

## 4. Threat 1 – IdP Spoofing (Trust Substitution)

### 4.1. "IdP Spoofing" Has Multiple Layers

**Layer 1: IdP phishing** – attacker stands up a login page resembling the IdP and tricks users into entering passwords. The SP may still verify the real IdP when receiving an assertion, yet IdP credentials were compromised. Domain protection, phishing-resistant MFA, fake-page detection, and user awareness are required; SAML signature checks at the SP alone do not stop this password theft.

**Layer 2: SAML issuer/signing key spoofing** – attacker crafts an assertion with `Issuer=https://trusted-idp...`, attaches their own `ds:KeyInfo`/certificate, and signs it with their own private key. If the SP extracts the **verification key from the untrusted payload** or accepts an issuer not pinned to a registration, it can falsely authenticate. A signature mathematically valid under an attacker's key must still **be rejected**.

**Layer 3: metadata source substitution** – a metadata URL, config file, CI/CD pipeline, or admin privilege is compromised; attacker adds their signing key to the SP's trusted key set. This is a **trust bootstrap and operations** issue. If the SP's trust config is legitimately modified via admin mechanisms, normal runtime validation will not automatically detect malicious intent.

**Layer 4: IdP/tenant confusion** – SP has IdPs for tenant A and tenant B. Attacker tries to use an assertion from IdP A while tricking the SP into mapping it to tenant B's account/registration (issuer mix-up, wrong key set, or wrong account mapping). Right IdP with **wrong tenant** is also a breached trust boundary.

### 4.2. Illustrative Attack Chain

```text
Attacker -> ACS: SAMLResponse containing NameID=admin
                Issuer="https://idp.trusted.example"
                ds:KeyInfo = attacker-controlled key
                Signature = signature made with attacker private key

Weak SP: "XML signature valid" (using key from message itself)
         -> uses NameID=admin -> creates SecurityContext for admin

Proper SP: issuer is only a claim; verification key comes from
           trusted IdP registration and independent verification
           -> signature mismatch -> REJECT
```

This models a **key-selection flaw**, not an exploitation guide. The SP must never treat `Issuer`, `KeyInfo`, or redirect parameters as authority to add a new IdP.

### 4.3. Protecting Boundaries A and B

1. **Trust from independent configuration:** maintain `RelyingPartyRegistration` for approved IdPs, checking `entityID` and corresponding signing keys. Ingest metadata only via authenticated channels; verify metadata ownership/trustworthiness outside the login transaction. A SAML signing certificate is typically an application trust anchor, not protected by default via CA chains alone.
2. **No trust-on-first-use from login requests:** never dynamically accept a new issuer, a metadata URL in a query string, a certificate in `KeyInfo`, or algorithm choices proposed by the client. When metadata carries multiple signing keys for rollover, every key must come from a **trusted source** and follow key-change policy.
3. **Verify signature over exact consumed data:** verify the XML signature of the Response/assertion using the key bound to the right IdP; never consume a different XML element than what was actually signed (**XML Signature Wrapping**). Block XML entity expansion/XXE, unintended schema fetching, and ambiguous structures; use OpenSAML integrated via Spring Security and keep patches current.
4. **Verify issuer/recipient per registration:** Response/assertion `Issuer`, Response `Destination`, assertion `AudienceRestriction`, and `SubjectConfirmationData.Recipient` must match values configured for that context. Do not match subdomains only or ignore scheme/host/path.
5. **Bind tenant → IdP → principal:** user keys should distinguish issuer/tenant plus stable subject; never automatically link two IdPs by display email. Groups/roles in an assertion become permissions only after passing through an application-approved mapping.
6. **Govern trust changes:** restrict metadata/key modification privileges; monitor audit logs, approve key rollovers, audit active key lists at deployment, and alert on unknown IdPs or unscheduled signing key changes.
7. **If a real IdP's signing key is compromised:** that key can mint accepted assertions; rotate keys rapidly, update SP trust via rollover, investigate created sessions, invalidate affected sessions, and review logs. Relying solely on `NotOnOrAfter` is insufficient.

**Note:** Metadata with a valid certificate is data needed for verification; *deciding whose metadata to trust* is an independent trust problem.

## 5. Threat 2 – Assertion Theft and Replay

### 5.1. Why Is a Valid Assertion Still Dangerous If Exposed?

SAML Web Browser SSO typically uses **bearer subject confirmation**. When an attacker obtains an acceptable SAML Response/assertion, they can try to POST it again to ACS. Unlike IdP spoofing, in this case the assertion **was signed by the real IdP**. Signature and issuer checks may both PASS.

Common exposure sources:

- Malicious browser extensions, compromised workstations, XSS with access to forms or authentication payloads.
- Reverse proxies/WAF/APM/tracing logging raw HTTP bodies at ACS or logging Base64 `SAMLResponse`.
- Recording requests into analytics systems, support tickets, screenshots, crash dumps, or real test fixtures.
- Weak TLS termination, proxies, or internal back-channel transport; overly broad request-capture/log configs.
- RelayState or post-login URLs misused to forward credentials to an attacker destination; never put assertions into URLs/redirects yourself.

**"Base64 encoding" cannot protect it:** `SAMLResponse` is Base64-encoded for transport, **not security encryption**. Encryption at the SAML layer protects confidentiality of assertion contents, but does not replace validation, log redaction, or replay protection.

### 5.2. Anti-Reuse Conditions Must Work Together

| Check | Purpose | Example to Reject |
| --- | --- | --- |
| XML signature on exact target | Ensures consumed data lies inside the element signed by a trusted IdP key | Asserts user A while reading user B from another assertion |
| `Issuer` | Confirms origin from the IdP configured for the registration | Issuer of another tenant/IdP |
| `AudienceRestriction` | Assertion issued for the exact SP `entityID` | Assertion issued for SP A sent to SP B |
| `Destination` / ACS | Response must arrive at the expected SP endpoint | POSTed to another ACS host/path |
| `SubjectConfirmationData.Recipient` | Bearer credential sent to the exact recipient | Recipient does not match SP's ACS |
| `InResponseTo` when SP-initiated | Response/confirmation must bind to an unconsumed `AuthnRequest` | No matching request; wrong/already-used request ID |
| `NotBefore`, `NotOnOrAfter`, `IssueInstant` | Accepted only within the policy time window | Not yet valid, expired, or anomalous issuance time |
| Assertion/Response ID + replay store | Prevents the same credential from succeeding multiple times | Second POST with the same assertion ID |
| `OneTimeUse` if present | Adds protocol-level single-use constraint | Assertion already accepted earlier |
| Login state and session binding | Prevents login A's assertion from mixing into login B's pending session | Request from another browser/tenant |

A sample policy (values are **illustrative**, not a mandatory standard config):

```text
issuer = https://idp.company.example/saml
spEntityId = https://portal.example/saml/sp
acs = https://portal.example/login/saml2/sso/corp
maxClockSkew = 60 seconds
requestLifetime = 5 minutes
replayCacheKey = (trustedIssuer, assertionId)
replayCacheTTL >= duration the assertion can still be accepted
```

- For SP-initiated flows, store the `AuthnRequest` ID with registration/session in a trusted store, verify `InResponseTo`, and mark the request as processed. If **IdP-initiated / unsolicited responses** are allowed, `InResponseTo` may be absent; a separate policy is required, enforcing issuer/audience/ACS bindings and **independent replay protection**, while recognizing the higher login CSRF/session confusion risks.
- Time window checks may allow reasonable clock skew; wider skew widens the replay window. `NotOnOrAfter` is an **exclusive** upper bound.
- The replay cache must perform an **atomic mark-on-first-use** operation across all SP nodes, combined with an appropriate TTL. Checking "not seen" then writing in two separate steps invites race conditions; per-replica local caches fail to stop replays across replicas.
- Avoid unbounded caches that exhaust memory; retain used IDs for at least the duration an assertion could remain acceptable. On cache failure, the fail-safe policy must be decided upfront (never silently fail-open).
- `OneTimeUse` in XML **does not automatically** guarantee single use; the SP must enforce it or use a validator/store that enforces it. Check the exact behavior of the Spring Security version and extensions in use.
- Do not treat assertion IP binding as a primary control: NAT, proxies, and mobile networks change IPs. If risk signals exist, use them as supplementary signals rather than dropping protocol validation.

### 5.3. Variants Not to Confuse

**Response replay:** resending an entire old SAML Response. **Assertion replay:** reusing a valid assertion inside a different message or at another SP. **Cross-SP replay:** presenting SP A's assertion to SP B. **Login CSRF/session confusion:** attacker forces a victim's browser to log into the attacker's account or binds a response to the wrong session. These variants are related, so never assume one check covers all of them.

**XML Signature Wrapping:** attacker exploits discrepancies between what the XML parser passes to signature verification and what application code selects to extract `NameID`/attributes. Even a Response/assertion with a "valid" signature is invalid if the object used for login is outside **the part protected by the verified signature**. Avoid parsing XML manually with regex, arbitrary XPath, or `getElementsByTagName(...)` to extract the principal.

### 5.4. Reducing Assertion Exposure

- HTTPS/HSTS across **the entire** application and redirect chain, especially ACS; secure TLS termination through to the app per topology.
- Redact/drop `SAMLResponse`, cookies, `Authorization`, and session IDs from access logs, proxies, WAF, APM, distributed traces, analytics, and bug reports. Log only **non-sensitive metadata**: correlation ID, verified issuer ID, validation outcome, error code, timestamp, and non-credential fingerprints.
- Never place assertions, login codes, or session IDs into queries, fragments, or `RelayState` arbitrarily; `RelayState` serves navigation/state correlation, must bind to the transaction, and must prevent open redirects.
- Use short lifetimes balanced with UX, restrict log access, and set retention plus incident procedures when credentials appear in logs.
- On user endpoints, mitigate XSS and malware; a secure server endpoint cannot prevent every leak inside a compromised browser.

## 6. Threat 3 – Post-SSO Application Session Hijacking

### 6.1. A Valid Assertion Does Not Guarantee a Secure Session Afterward

```text
Valid SAML Response
     -> Spring Security Authentication (principal + authorities)
     -> SecurityContext bound to request / stored per app mechanism
     -> HttpSession + session cookie (e.g., JSESSIONID)
     -> subsequent requests carry only cookie; usually no assertion resent
```

The boundary shifts at session creation: **the session ID becomes the SP's credential**. An assertion expiring at 10:00 does not automatically expire an `HttpSession` created at 10:00. IdP logout also does not automatically terminate all SP sessions without an SLO/synchronization mechanism and proper application handling.

Three problem classes:

1. **Session fixation:** attacker knows/presets a session ID, victim signs into that session, and attacker tries to reuse the known ID. Must **rotate the session ID on successful login**.
2. **Session theft/hijacking:** attacker steals the post-login cookie (via logs, MITM, browser compromise, XSS if cookie lacks `HttpOnly`) or compromises the session store. Protect transport/storage/timeouts and invalidate sessions upon anomalies.
3. **Session riding (CSRF) / XSS:** attacker tricks the victim's browser into performing actions under a valid session **without needing to know the cookie value**. `HttpOnly` prevents JS from reading cookies, **not actions caused by XSS/CSRF**. CSRF protection, output encoding, appropriate CSP, and server-side authorization checks are needed.

### 6.2. Cookies and Session Lifecycle

| Mechanism | Effect | Limitation to Remember |
| --- | --- | --- |
| `Secure` | Cookie sent only over HTTPS | Does not prevent XSS or leaks from server logs |
| `HttpOnly` | Page JavaScript cannot read cookie via `document.cookie` | Browser still sends cookie on requests; XSS can still perform actions |
| `SameSite` | Restricts certain cross-site requests | Does not replace CSRF tokens; `Lax`/`Strict` can affect SAML POSTs from IdP |
| Minimal `Path` / `Domain` | Narrows where cookie is sent | Cookies shared across subdomains widen attack surface |
| Strong random Session ID | Hard to predict/brute-force | Leaked IDs remain usable |
| Rotate ID after authentication | Mitigates session fixation | Does not rescue a stolen new cookie |
| Idle + absolute timeout | Limits abuse window | Requires server-side enforcement and appropriate policy |
| Invalidate server session on logout | Revokes session credential | Clearing cookies client-side alone does not invalidate stolen copies |
| Re-auth/MFA for sensitive actions | Limits blast radius of session theft | Must bind to recent authentication/assurance level |

**Difficulty with SAML POST binding:** Responses typically travel from an IdP origin to the SP's ACS origin via a **cross-site POST**. An SP session cookie set to `SameSite=Lax`/`Strict` may not accompany that POST, preventing the SP from locating the stored request/session to check `InResponseTo`. Never "fix" this by disabling request binding checks or disabling CSRF globally. Choose a state/correlation design and cookie policy that fit—possibly `SameSite=None; Secure` for cookies required to traverse the POST—then test on real browsers and maintain CSRF defenses on other endpoints. Compatibility also depends on browsers, topology, proxies, and IdP configuration.

**Cookie prefix `__Host-`**, when topology-compatible, requires `Secure`, `Path=/`, and no `Domain`, reducing certain subdomain cookie-forging risks. If an app spans SSO across multiple domains, do not assume the same cookie works across domains; each SP's session is separate.

### 6.3. Do Not Skip Authorization and Privilege Limits

An assertion with `groups=["admins"]` must never automatically grant `ROLE_ADMIN` across all tenants just because the group name matches. Manage mappings by issuer/tenant, verify claim provenance, enforce least privilege, check object ownership on every endpoint, and audit privilege changes.

**Notable risk:** exposing a high-privilege user's session lets an attacker access the application without going through SAML/IdP again. Re-authentication policies for sensitive operations and session revocation are an independent line of defense.

## 7. Attack Chains and Corresponding Blocking Points

### Scenario A – Rogue IdP Wrongly Trusted by SP

1. Attacker controls untrusted metadata/certificate or activates an out-of-allowlist IdP config.
2. Attacker signs an assertion containing a target account's `NameID`.
3. SP uses the signing key supplied by the attack payload instead of the trusted registration's key.
4. SP creates an impersonated session.

**Blocks:** govern IdP enrollment, bind `RelyingPartyRegistration`, configure signing keys by trusted issuer, never pick a trust anchor from the payload, and consume only validated assertions. **Signals:** unknown registration, unscheduled metadata/key changes, logins from unapproved issuers.

### Scenario B – Real Assertion Exposed in APM

1. User signs in successfully; proxy logs the raw `SAMLResponse` form field into traces.
2. Attacker with trace read access obtains the payload.
3. Attacker tries to re-POST the still-valid payload to ACS.
4. SP lacks request binding, lacks consumed-ID caching, or caches only per isolated node, allowing another session to be created.

**Blocks:** redact at every logging point; verify `Recipient`/`Audience`/`InResponseTo`, short TTL, atomic shared one-use/replay store. **Signals:** repeated assertion IDs, one response ID used from multiple sources, anomalous request correlation failures. A valid signature **is not enough to stop replay**.

### Scenario C – Valid SAML Yet Hijacked Session

1. User signs in with a completely valid assertion.
2. Application fails to rotate session ID or leaks the cookie via logs/JS/proxy.
3. Attacker reuses the cookie on application requests.
4. API relies on the SP session and allows actions under the victim's identity.

**Blocks:** rotate session ID, appropriate `Secure`/`HttpOnly`/`SameSite`, session limits, XSS/CSRF defenses, re-auth for sensitive actions, server-side revocation. **Signals:** same session used from anomalous devices/contexts, high-privilege actions post-login, shifting risk signals. IP/User-Agent are only **risk signals**, not sole hard bindings due to mobile networks, NAT, and corporate proxies.

### Scenario D – Valid Trust Yet Wrong Cross-Tenant Authorization

1. IdP A is a valid IdP and issues an assertion for a user with email `admin@example.org`.
2. Application maps accounts globally by email, ignoring issuer and tenant.
3. User gets linked to tenant B's account sharing the same email.
4. App allows viewing tenant B's data.

**Blocks:** key identities by (tenant, issuer, stable subject), verified account linking, tenant/object authorization, test overlapping emails. Technical authentication "PASS" does not substitute for business isolation.

## 8. Applying Spring Security 6+ with Servlet

### 8.1. Choose the Right Mechanism and Keep Default Validators

For a SAML 2.0 SP, include the appropriate libraries (`spring-security-saml2-service-provider` via the matching Spring Boot starter/dependency set) and configure `RelyingPartyRegistration` binding approved IdPs with trusted certificates/metadata, SP entity ID, and ACS URL.

Full Java **configuration class** example for a Servlet application with Spring Security on the classpath. It is only the **filter chain protection layer**; actual login still requires a valid SAML IdP registration config:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

        return http.build();
    }
}
```

- `saml2Login()` enables the SAML login flow and SAML Response verification provider. In current Spring Security versions, validation relies on OpenSAML: signature, issuer, destination, and assertion conditions/subject/audience per configuration; **do not assume all replay/OneTimeUse policies and ID storage are enabled automatically**.
- `changeSessionId()` makes the fixation defense explicit; on Servlet 3.1+ this is also Spring Security's default strategy. Never use `sessionFixation().none()`.
- `authorizeHttpRequests` is the post-authentication authorization layer. Replace broad rules with the application's concrete endpoint/role/object policies.
- Never add `csrf(csrf -> csrf.disable())` application-wide just to "make SAML POST work". SAML callback endpoints require framework-managed compatible exemption/state correlation; other state-changing POSTs must remain CSRF-protected.
- When behind a reverse proxy, configure forwarded headers and HTTPS origin **only from trusted proxies** so the SP computes the right public ACS URL; avoid trusting `X-Forwarded-*` sent directly by Internet clients.

### 8.2. Cookie/Session Example in Spring Boot

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

This is an **example for an application needing a Lax session cookie**. With **SAML cross-site POST**, `same-site: lax` may prevent the SP's session cookie from being sent to ACS; test in practice first and choose `None; Secure` or an appropriate dedicated correlation design. `timeout: 30m` is an example idle/session timeout, not a universal security guarantee across all environments. If using a shared session store, TTL/replication and logout/invalidation configs must be consistent across all instances.

Verify in actual responses: `Set-Cookie` has `Secure` and `HttpOnly`, `SameSite` policy matches protocol needs, and no session ID appears in URLs. At ingress, ensure the app knows the original request was HTTPS when required. Do not just look at the YAML file and assume browsers receive cookies as intended.

### 8.3. RelyingPartyRegistration and Protecting IdP Sources

Every SAML integration requires configuring **IdP metadata with clear provenance**, signing credentials, registration/entity ID/ACS, and controlled certificate rollover. Spring Security uses `RelyingPartyRegistration` to bind SP and asserting-party details. Only read metadata from administrator-controlled locations; never let users enter an arbitrary metadata URL and immediately treat it as a trusted IdP.

Dangerous configuration signs:

- Accepting the signing certificate from `ds:KeyInfo` inside `SAMLResponse` as the trust anchor.
- Disabling signature or skipping `Issuer`/`Destination`/`Audience` checks to "fix integration errors".
- Selecting a registration solely from the payload's `Issuer` without binding to tenant/request context.
- Renaming ACS/entity ID without reviewing validation and proxy headers.
- Assigning `ROLE_ADMIN` directly because an assertion has an `email`/`department` claim without verified mapping.
- Treating successful SAML login as access to all endpoints, or using the SP session as a bearer credential for other APIs.

### 8.4. Replay Protection Is a Deployment Requirement to Verify

Spring Security/OpenSAML performs many validations by default, yet **cross-node one-time/replay cache guarantees** must be verified by version, extensions, SP-initiated/IdP-initiated flow, and deployment setup. If default validators do not satisfy policy, add checks via the provider's official extension API, **chaining after default validation** rather than replacing everything with a permissive validator.

Conceptual replay store design:

```text
after cryptographic + protocol validation PASSES:
    key = stableTrustedIssuer + ":" + verifiedAssertionId
    if atomicInsertIfAbsent(key, expiresAt + allowedSkew) == false:
        REJECT as replay
    else:
        continue creating Authentication/session
```

Address concurrently: checking all relevant IDs, preventing external actors from choosing tenant context in the key, TTL and skew, concurrency, cache failures, and multi-replica testing. Never copy this pseudocode into a filter running before SAML signature verification; untrusted payloads must not control cache quota to cause DoS.

### 8.5. OIDC Equivalent Concepts, Different Terminology

In OIDC, the app is the **Relying Party**, and the OP issues **ID tokens**; issuer mix-up/token substitution threats require `iss`, `aud=client_id`, signature/JOSE validation, `state`, `nonce` when used, PKCE, and exact redirect URIs. An ID token is not a SAML assertion; it has no XML `AudienceRestriction` or SAML `Recipient`. For OAuth APIs, an **access token** requires the resource server as its intended audience. **Session hijacking** can still occur after OIDC login, so cookie, session rotation, and CSRF/XSS defenses are equivalent.

## 9. Defensive Testing: Must Test Invalid Paths Too

Create dedicated test fixtures/identities; never use real production assertions/cookies. For every test, specify **input**, **expected outcome**, and **evidence** (HTTP status, event, no principal/session created). Never log raw credentials in test output or logs.

| Negative Test | Expected Secure Outcome |
| --- | --- |
| Unsigned SAML Response or invalid signature | Reject; no new principal |
| Assertion signed by a key not trusted by the SP | Reject, even if `Issuer` string matches real IdP |
| IdP A's issuer with tenant/registration B | Reject or never map to tenant B |
| `Audience` is another SP | Reject |
| `Destination`/`Recipient` points to wrong ACS | Reject |
| `InResponseTo` invalid/no pending request (SP-initiated) | Reject; do not create session from unlinked response |
| `NotBefore` in the future or `NotOnOrAfter` in the past | Reject |
| Resending same assertion/response ID | Reject second attempt; test concurrently and cross-replica |
| XML with multiple assertions, only part signed | Only the properly signature-protected principal may be used; reject ambiguous cases |
| `RelayState` contains an unapproved external URL | No open redirect to attacker domain |
| Valid response mapped to different role/tenant | Authentication does not grant out-of-policy permissions |
| Session ID before and after login | Different (anti-fixation) |
| Cookie missing `Secure`/`HttpOnly` or invalid `SameSite` | Flag misconfiguration; fix and verify on real browser |
| Server-side logout, timeout, revocation | Old cookie cannot access protected resources |
| State-changing request missing CSRF token | Reject per policy, aside from specifically handled callback |
| Cross-site SAML POST on supported browsers | Login still binds to right request/session; never drop validation to pass test |
| XSS attempt to read `HttpOnly` cookie | Cannot read cookie value from `document.cookie`; must still mitigate XSS at other layers |

**What to test:** "Invalid → reject" tests carry more value than testing only normal "valid → 200" logins. For multi-tenancy, add cases with two users sharing the same email across two different issuers. Behind a load balancer, run replay tests across **two different pods/instances**.

### 9.1. Verifying via Structured Logs

Fields to include when appropriate and after verification/minimization:

```text
event=saml_auth_rejected
request_correlation_id=...
registration_id=corp
reason_code=INVALID_AUDIENCE
remote_context=...            # IP data normalized per trusted proxy
timestamp=...
```

Include values from untrusted payloads only in escaped, length-bounded fields that are never used for decisions. Never log `SAMLResponse`, assertion XML, cookies, or sensitive `NameID`/emails by default. Log clear reason codes, yet **never return internal trust key/validator details in HTTP errors to an attacker**.

Suggested metrics: rates of `INVALID_SIGNATURE`, `UNTRUSTED_ISSUER`, `WRONG_AUDIENCE`, `EXPIRED_ASSERTION`, `REPLAY_DETECTED`, `IN_RESPONSE_TO_MISMATCH`; unscheduled signing key changes; surges in new sessions for the same user/tenant; anomalous privilege changes after SSO. Some errors (clock drift/wrong ACS config) may be operational issues rather than attacks; investigate root cause before concluding.

## 10. Java 17+ Illustration: Post-Validation Replay Policy

The example below models an **acceptance rule after the XML signature and full protocol validation have succeeded in the SAML library**. The `VerifiedAssertion` class data is constructed manually for demo purposes; the class name **does not mean** it actually verifies signatures. This is **not a SAML parser, provider, or production cache mechanism**.

Save file `ReplayBoundaryDemo.java`:

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class ReplayBoundaryDemo {
    record VerifiedAssertion(
            String issuer,
            String audience,
            String id,
            Instant notBefore,
            Instant notOnOrAfter) {}

    static boolean acceptAfterProtocolValidation(
            VerifiedAssertion assertion,
            String trustedIssuer,
            String expectedAudience,
            Instant now,
            Set<String> consumedIds) {

        if (!trustedIssuer.equals(assertion.issuer())) {
            return false;
        }
        if (!expectedAudience.equals(assertion.audience())) {
            return false;
        }
        if (now.isBefore(assertion.notBefore())
                || !now.isBefore(assertion.notOnOrAfter())) {
            return false;
        }
        return consumedIds.add(assertion.issuer() + "|" + assertion.id());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        Instant from = now.minusSeconds(30);
        Instant until = now.plusSeconds(120);

        VerifiedAssertion valid = new VerifiedAssertion(
                "https://idp.example", "sp-portal", "_assertion-1",
                from, until);
        VerifiedAssertion wrongAudience = new VerifiedAssertion(
                "https://idp.example", "sp-other", "_assertion-2",
                from, until);
        VerifiedAssertion expired = new VerifiedAssertion(
                "https://idp.example", "sp-portal", "_assertion-3",
                from, now.minusSeconds(1));

        Set<String> consumed = new HashSet<>();
        System.out.println("first: " + acceptAfterProtocolValidation(
                valid, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("replay: " + acceptAfterProtocolValidation(
                valid, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("other SP: " + acceptAfterProtocolValidation(
                wrongAudience, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("expired: " + acceptAfterProtocolValidation(
                expired, "https://idp.example", "sp-portal", now, consumed));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ReplayBoundaryDemo.java
java ReplayBoundaryDemo
```

Stdout:

```text
first: true
replay: false
other SP: false
expired: false
```

**Reading the demo accurately:**

- The line `first: true` only means **the simple rules in the example PASS** on a code-constructed object; it is not proof of a valid real SAML assertion.
- `replay: false` because `HashSet.add` rejects an already-seen ID. In production, use an **atomic store shared across replicas**, TTL, failure policy, and concurrency handling; `HashSet` is insufficient.
- `other SP: false` because audience does not match; `expired: false` because `NotOnOrAfter` has passed.
- The demo intentionally **does not** validate signature, `Destination`, `Recipient`, `InResponseTo`, `SubjectConfirmation`, schema, `OneTimeUse`, or key rotation. Never use this class as a real auth filter.

## 11. Incident Response by Threat Type

### 11.1. Suspected IdP Spoofing or Compromised Signing Key

1. Block acceptance of assertions from the suspicious registration/key as deployment permits; secure config-admin accounts and metadata update pipelines.
2. Compare live trust configuration against approved IdP/key lists and recent changes. Verify metadata via an independent channel.
3. Coordinate with the IdP to rotate keys/revoke related credentials and update the SP safely via rollover; avoid unnecessarily disrupting other IdPs.
4. Locate sessions created from the affected issuer/key/time window, assess activity/privileges, and revoke affected sessions.
5. Remediate root cause: config edit permissions, trust-on-first-use, vulnerable dependencies, certificate management, and monitoring.

### 11.2. Suspected Assertion Exposure or Replay

1. Stop the leak at the source (APM, body logs, proxies, support shares); restrict access to records containing credentials.
2. Investigate using hashed correlation/IDs, time window, and SP/tenant; never redistribute raw assertions in tickets/chat.
3. Enable/tune anti-replay cache and request/recipient bindings; if needed, temporarily tighten validity or block anomalous logins per policy.
4. Revoke affected sessions and require re-login when abuse is evidenced.
5. Re-test concurrent replay, cross-replica replay, and IdP-initiated flows if supported.

### 11.3. Suspected Session Hijacking

1. Invalidate affected sessions **server-side**, not merely asking the client to delete cookies; revoke related tokens per application model.
2. Identify the cause—cookie leak, fixation, XSS, CSRF, user device, session store, or proxy—and fix the exact layer.
3. Audit session activity and accessed endpoints; enforce re-auth/MFA for sensitive operations.
4. Review idle/absolute timeouts, cookie flags, logout, session rotation, and SLO policies.
5. After remediation, run end-to-end browser tests and monitor for recurring signals.

**Core distinction:** Revoking a trusted certificate responds to IdP trust; blocking replay responds to **SAML login credentials**; revoking `HttpSession` responds to **SP sessions**. One action does not automatically replace the other two.

## 12. Pre-Production Review Checklist

- [ ] Only approved IdPs/metadata/signing keys appear in `RelyingPartyRegistration`; audit trail and rollover process exist.
- [ ] Validator verifies the signature of **the exact consumed data**; resists XML wrapping/XXE and weak algorithms per policy.
- [ ] `Issuer`, `Destination`, `Audience`, `Recipient`, and time conditions match the SP/tenant, never bypassed to fix config errors.
- [ ] For SP-initiated flows, `InResponseTo` and state match the request; IdP-initiated if allowed has its own policy/threat model.
- [ ] Replay detection runs with a shared atomic store and appropriate TTL; tested for single-use and multi-instance concurrency.
- [ ] Never log SAMLResponse, assertion XML, credentials, or session cookies; HTTPS end-to-end.
- [ ] Account linking distinguishes issuer + subject + tenant; role/object authorization operates independently of login.
- [ ] Session ID rotates on login; `Secure`/`HttpOnly`/`SameSite` cookies tested on browsers and SAML POST binding.
- [ ] Timeout, logout, session invalidation, and CSRF/XSS protections tested; never rely on expired assertions to end sessions.
- [ ] Negative tests, audit events, alerts, and key-compromise / session-compromise plans are in place.

## 13. Self-Check Questions

**Question 1.** The SP verified the XML signature, but used a public key embedded inside `SAMLResponse` itself. Why is this still dangerous?  
**Answer:** An attacker can self-sign with a key they control. The SP must verify using the **independently trusted** IdP key bound to an approved registration/issuer.

**Question 2.** Assertion signature is valid, issuer is right, and it is unexpired; is re-POSTing the same Response a second time safe?  
**Answer:** No, that is insufficient. Request correlation, recipient/audience, and atomic one-time ID tracking must be enforced; a valid signature does not prove first use.

**Question 3.** Spring Security authenticated SAML successfully, yet `JSESSIONID` was leaked. Does an attacker need to spoof the IdP to hijack the session?  
**Answer:** No. The SP session cookie can be reused independently of the assertion; server-side session revocation and fixing the leak source are required.

**Question 4.** Is enabling `SameSite=Lax` always the safest choice for SAML?  
**Answer:** No. SAML HTTP POSTs from the IdP may be cross-site, blocking the correlation cookie. Real browser testing, an appropriate cookie/state strategy, and CSRF protection on other POSTs are required.

**Question 5.** A user signed in via a trusted IdP; is the claim `groups=admin` enough to allow editing any account?  
**Answer:** No. Claims must be mapped per tenant/issuer policy and endpoints must enforce authorization, especially object ownership.

## 14. Standards and Practical Guides

- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – SAML architecture, assertion structure, browser SSO.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – signed XML, trust, replay, recipient/issuer/audience, and XML signature wrapping.
- [Spring Security: SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – `AuthnRequest`/ACS flow and `RelyingPartyRegistration`.
- [Spring Security: Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – default OpenSAML authentication provider and validator customization.
- [Spring Security: Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) – session fixation, lifecycle, and `changeSessionId`.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet) – cookies, timeouts, hijacking/fixation, logout.
- [Spring Boot: Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) – `server.servlet.session` and cookie properties.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) – if federation architecture uses OIDC, verify issuer/audience/nonce per OIDC protocol.