# Identity Protection Responsibilities When a Partner or Intermediary Server Is Compromised

> **Topic:** Spring Security – federation. **Knowledge Group:** Trust Boundaries. This lesson explains who must protect identities, what each system may continue to trust, and what to do when an SSO integration partner, proxy, or intermediary server is compromised.

## 1. Core Problem: Trust Is Scoped and Revocable

In **federation**, multiple systems participate in one login journey. An **Identity Provider (IdP)** or **OpenID Provider (OP)** authenticates the user; a **Service Provider (SP)** in SAML or **Relying Party (RP)** in OIDC consumes that result; a **CAS service** relies on a CAS server to validate tickets; an **OAuth Resource Server (RS)** protects APIs based on access tokens. Between them may sit an API gateway, reverse proxy, identity broker, WAF, service mesh, or SaaS partner.

Each party should only be trusted **within a defined function**. A partner permitted to use identities to log into their own application **is not automatically permitted** to impersonate users at our APIs, modify administrative roles, mint tokens on behalf of the IdP, or assert that a user achieved a higher authentication level.

Model example:

```text
User
    |
    v
[IdP / OP / CAS server] -- assertion / ID token / ticket --> [SP / RP / CAS service]
          |                                                |
          | OAuth access token                              | app session
          v                                                v
 [Authorization Server] ---- access token ----> [Resource Server / API]
                                                ^
                                                |
                               [Gateway / Proxy / Broker]
                                     (intermediary)
```

This diagram illustrates **roles**, not necessarily deployment topology: an OP often also serves as the Authorization Server; a gateway may sit on multiple paths; CAS uses its own ticket/validation flow.

An identity transaction must answer five questions:

1. **Who is the identity-asserting source?** Which issuer/IdP/OP/CAS server is approved, for which tenant and user population?
2. **Who was the credential issued for?** Do SAML `AudienceRestriction`, OIDC `aud`, OAuth access token audience, or CAS `service` match the recipient?
3. **Who processed the credential along the path?** Is there any broker, proxy, or gateway able to read/modify headers or issue new credentials itself?
4. **What action does the credential authorize?** Signing into a web session, calling an API, reading personal data, or performing a sensitive transaction?
5. **When one link loses security, what can the recipient still trust?** A valid signature, HTTP 200, or an internal IP **does not by itself prove** user identity and intent are trustworthy when an issuer/intermediary has been compromised.

**Principle:** There is no "trust once, trust the whole chain". Design must constrain **issuer, recipient, permission scope, lifetime, transport path, and revocation conditions** at every boundary.

## 2. What Actually Happens When Each Party Is Compromised?

| Compromised Component | What the Attacker Can Control or Steal | Impact Scope to Assess | What Must Never Be Assumed |
| --- | --- | --- | --- |
| **Partner's SP / OIDC RP / CAS service** | App sessions, locally stored data, tokens remaining in system, client secret, refresh tokens, app admin accounts, redirect config | Partner's users; APIs and data accessible via the partner's tokens/permissions | Compromising an RP **does not automatically** enable minting valid SAML assertions or ID tokens under an uncompromised IdP private key |
| **Identity broker / SSO gateway** | Attribute mappings, upstream/downstream connections, translated tokens, SSO sessions, signing keys if broker is an issuer | Multiple apps relying on the broker; expanded risk when the broker signs new assertions/tokens itself | A validly signed token from the broker **does not prove** the upstream IdP wasn't spoofed or claim data wasn't escalated |
| **Reverse proxy / API gateway** | Forwarded headers, cookies/bearer tokens crossing TLS termination, request routing, auth policy at gateway | Downstream services trusting gateway headers or policies; token/PII leaks | `X-Forwarded-User` or `X-User-Role` is trustworthy simply because the request arrived from the internal network |
| **IdP / OP / Authorization Server** | Accounts, sessions, authentication workflows, signing keys, token issuance endpoints, authorization policies | All RPs/RSs/SPs still trusting the affected issuer or keys | A still-verifiable signature **does not prove** token issuance was authorized by the real user |
| **OAuth Resource Server / API** | Data, tokens in requests/logs/caches, downstream calling credentials, authorization logic | API resources and other services the API has rights to call | Compromising an API **does not necessarily** compromise the IdP; yet it can spread via leaked tokens and service keys |
| **CAS server or ticket validation channel** | Accounts, CAS sessions, Service Ticket issuance/validation rights, validation responses | Every CAS service relying on the server or its validation results | A CAS ticket valid for one service can be arbitrarily reused across all services |

**Severity distinction:** Exposing a public **public key/JWKS** is not equivalent to losing a signing key. However, if the issuer's **private signing key** or token-minting authority is compromised, forged tokens signed with that key will pass normal cryptographic checks. In that case, you must suspend trust in the affected issuer/key and investigate, rather than merely "turning on stricter signature checks".

## 3. Who Is Responsible? Division by Control Authority

### 3.1. Owner of the IdP / OP / CAS Server / Authorization Server

The credential issuer is responsible for protecting **the identity base and issuance capabilities**: user authentication, MFA/step-up policies, protecting signing keys and admin access, managing SSO sessions, configuring authorized applications, revoking/rotating credentials, detecting anomalous token issuance, and notifying affected relying parties of incidents. When using a broker, explicitly declare which broker **is authorized to issue its own tokens** and how that broker obtains upstream credentials.

When an issuer shows signs of compromise, the issuer owner must identify the intrusion vector, isolate token issuance, invalidate exposed credentials, rotate keys, and publish the list of affected issuers/clients/recipients/timeframes. **Key rotation is only part of remediation**: already-issued tokens, stolen tokens, active RP sessions, and recipient JWKS caches must still be addressed.

### 3.2. Relying Recipient: SP, RP, or CAS Service

The recipient remains responsible for **protocol-compliant credential verification** and protecting its own accounts/sessions/permissions. For example: accept only registered IdPs; verify signatures and recipients; apply `state`/`nonce`/PKCE in appropriate flows; prevent replay; protect session cookies; bound session lifetimes; never auto-escalate privileges from unvetted claims.

When a partner or issuer is suspected of compromise, the RP/SP must be able to **stop accepting the affected trust source**, reject new logins, invalidate related active sessions when needed, pause sensitive features, and inspect for account takeover indicators. You cannot shift all user-protection responsibility onto the IdP simply because the application uses SSO.

### 3.3. Resource Server and Data/API Owner

The Resource Server is the **final decision point** for API resources. The API must verify the token has an allowed issuer, the right API audience, valid expiration, compliance with token type/sender-constrained policies if applicable, proper scopes/roles **and** business permissions on the requested record.

A valid token only states that the issuer granted some permissions; the token **does not by itself prove** the user is allowed to read another person's order. The API must verify ownership/tenant/resource object. The API owner is responsible for scoping data exposed to partners, detecting anomalous activity, and temporarily blocking affected clients/tokens/routes during incidents.

### 3.4. Operator of Gateway / Proxy / Identity Broker

The gateway owner must protect request paths and the boundary between **client-sent data** and **data authenticated by a trusted component**. Identity headers like `X-Authenticated-User`, `X-User-Id`, or `X-Roles` may only be accepted by the backend if the gateway verifies identity itself, **strips same-named headers from the client**, injects trusted values, and secures the gateway–backend connection so it cannot be bypassed.

If the gateway terminates TLS or holds bearer tokens, the gateway owner is responsible for protecting logs, memory, credentials, and keys; restricting system privileges; segmenting paths; isolating services; and investigating token exposure indicators. If a broker **issues new tokens**, downstream services must have explicit policies on which claims the broker may assert; never grant the broker admin power merely because its token has a valid signature.

### 3.5. Owner of Federation Relationships and Incident Response

An organization operating federation needs a **trust relationship registry**: which partner, which issuer/entityID, which endpoints/keys, which clients/services, which data permissions, technical owners, and incident contact channels. Contracts/processes must define notification duties, evidence sharing, integration suspension, key rotation, recovery, and user support under applicable laws and obligations.

**Do not confuse "who caused the incident" with "who takes emergency action".** A partner may be the breached party, yet the API owner must still block dangerous access at the API; the IdP may be investigating, yet the RP must still protect its own local sessions and data.

## 4. Four Typical Scenarios and Propagation Limits

### Scenario A — A Partner's OIDC RP Is Compromised

**Progression:** A partner's RP is infected with malware; tokens in storage or logs are exposed. An attacker can call our APIs if they obtain a **valid Access Token for the API**, even while the IdP account remains safe. If refresh tokens/client credentials leak, persistent access can outlast the initial access token.

**Boundaries to hold:**

- An **Access Token for API A** must not be usable to call **API B** if `aud` differs.
- Grant only minimal scopes to partner clients; scopes do not replace per-resource permission checks.
- Reduce token reuse risk via short lifetimes, token rotation where appropriate, and sender-constrained tokens (mTLS/DPoP) if the ecosystem supports them; never assume every Bearer token is device-bound.
- Register exact redirect URIs, use Authorization Code + PKCE per client type and policy, protect client secrets, and minimize token storage in browsers/logs.
- Upon incident detection: suspend the partner's client, revoke refresh tokens/revocable tokens, close related API access, inspect accessed sessions and data, coordinate credential rotation, and re-verify the integration.

**Limitation to understand:** If a partner can mint sessions in their own application, we cannot rely on that session as independent proof that the real user authorized calling our API. Accept only tokens/claims issued by an authorized party under an explicit trust contract.

### Scenario B — Proxy or Gateway Compromised, Backend Trusts Identity Headers

**Progression:** The backend uses `X-User-Email` and `X-User-Role` from a reverse proxy to create accounts and grant permissions. An attacker controlling the proxy can inject `X-User-Role: admin`; upstream ID Token signatures do nothing if the backend **merely reads the altered header**.

**Layered defenses:**

1. Explicitly specify which proxies the backend **is allowed to accept** identity headers from; block direct connections from the internet or untrusted sidecars.
2. The proxy strips client-sent identity headers, **verifies tokens/sessions before generating headers itself**, and uses an authenticated channel to the backend (mTLS or equivalent in the deployment model).
3. For critical transactions, prefer having the backend verify end-to-end cryptographic credentials itself or an internal assertion with specific issuer/audience/expiration rather than trusting plain text headers alone.
4. Never turn `X-Forwarded-For`, `X-Forwarded-Proto`, or client IP into identity authentication. Network headers serve routing/origin and require dedicated trusted-proxy configuration.
5. If a proxy/broker has been compromised, suspend the integration path, clear sessions and credentials traversing that point per risk level, audit escalated actions, and restore only after re-establishing a trusted channel.

**Subtle point:** If a broker signs downstream tokens with **the broker's own** valid key, downstream signature verification still succeeds. Therefore, define strictly which claims the broker may issue, which mappings are approved, and how identity provenance is audited.

### Scenario C — IdP/OP or Signing Key Compromised

**Progression:** An attacker can use valid token-minting privileges or a leaked signing key to forge ID Tokens/SAML Assertions with fabricated contents. An SP/RP performing proper signature checks **can still be deceived** by an issuer that is no longer trustworthy.

**Response:** Suspend or narrow the trust relationship with the affected issuer/key/client; block new logins/federation; evaluate session termination and require independent additional verification for sensitive tasks. The issuer owner isolates affected accounts/keys, re-issues keys from a trusted environment, and publishes a transition procedure; RPs/RSs sync trust stores, manage JWKS/metadata caches, and re-evaluate issued tokens and local sessions.

**Do not fall into false comfort:** Merely changing `kid`, updating JWKS, or shortening future `exp` **does not immediately revoke** all already-issued JWTs or already-created application sessions. Self-contained JWTs typically have no instant revocation if verifiers only check signatures and expiration. You may need a `jti`/session denylist, token introspection where applicable, gateway/API policy updates, clearing sessions, or disabling the entire issuer during investigation.

### Scenario D — CAS Service or CAS Validation Component Compromised

**Progression:** A compromised CAS service can expose application sessions and tickets in logs/redirects. When properly configured, a **Service Ticket** is single-use and bound to `service`; the service must call the CAS server to validate the ticket. If the CAS server or validation responses are spoofed, services relying on those answers are impacted too.

**Defenses:** Register exact service URLs; use HTTPS; validate tickets through the trusted server; never treat an `ST-...` string appearing in query params as an authenticated identity; never log tickets; handle replay and session fixation; suspend CAS login if the validation endpoint cannot be trusted. When a service is breached, invalidate sessions at that service and audit tickets/logs; when the CAS server is breached, expand assessment scope to all connected services.

## 5. Protocol-Accurate Credential Verification at Boundaries

| Protocol and Receiving Role | What Must Be Verified | When Suspecting Issuer or Intermediary |
| --- | --- | --- |
| **SAML SP** | Trusted IdP/entityID, signature in the right element, time conditions, `AudienceRestriction`, `Recipient`/`Destination`, `InResponseTo` for SP-initiated SSO, anti-replay, controlled certificate rollover | Suspend suspected IdP metadata/keys, reject assertions from unregistered sources, audit ACS and application sessions |
| **OIDC RP** | OP `issuer`, ID Token signature, `aud`/`azp` when applicable, `exp`, `nonce` when used, `state`, proper authorization code + PKCE, registered redirect URI | Suspend suspected registration/issuer, revoke or assess RP sessions, audit account links by `iss` + `sub` |
| **CAS service** | Service Ticket returned to exact `service`, validated with CAS server, ticket valid/unused, secure validation source | Stop accepting validations from suspected CAS server and invalidate affected app sessions |
| **OAuth Resource Server** | Access Token has trusted signature/issuer, API-targeted `aud`, valid lifetime, token type policy, scopes/permissions, and ownership/tenant | Narrow/block client, issuer, route, or scope; handle leaked tokens and investigate data access |
| **Gateway / identity broker** | Request origin, upstream tokens/claims, identity mapping policy, downstream token issuer/audience, integrity of backend channel | Isolate broker path/signing keys, stop trusting affected identity headers or downstream tokens |

**Do not substitute an ID Token for an Access Token**: an ID Token is an authentication assertion **for the OIDC RP**; a Resource Server needs an **Access Token intended for the API** per the OAuth contract. **Do not match solely by email** across issuers/tenants when linking accounts: email addresses can change, be reassigned, or go unverified. Use issuer/tenant-scoped stable identifiers, typically `iss` + `sub` in OIDC, and a linking workflow with appropriate proof of ownership.

When supporting multiple issuers, **never unconditionally select verification keys based on an `iss` self-reported by an unverified token**. Dispatch only against an **approved issuer allowlist** and ensure each issuer has its own audience, algorithms, claim mapping, scopes, tenant, and policy configuration. Never automatically fetch JWKS from an arbitrary URL taken from a client-sent token.

## 6. Controls to Design Before an Incident Occurs

### 6.1. Technical Trust Contract

For each partner, explicitly document and approve: environment (dev/staging/prod), issuer/entityID and certificate/JWKS, metadata endpoints, audience/service/ACS/redirect URI, valid tenants, client ID, scope/claim mapping, required authentication assurance, data permissions, logout/revocation method, key lifetimes/rotation cadence, owner, and incident contacts.

Do not allow trust to expand implicitly by accepting wildcard redirect URIs, any issuer, any audience, any signing algorithm, or any proxy address. Public signing keys may rotate legitimately; manage authenticated rollovers and maintain an emergency trust-kill path.

### 6.2. Least Privilege and Limiting Blast Radius

- Separate issuers, clients, and keys/credentials by **environment and partner**; avoid sharing clients across multiple partners.
- Grant minimal scopes, audiences, and roles; Resource Servers check permissions on **specific objects**, not only at the route layer.
- Avoid sending unnecessary PII in tokens, headers, redirects, or logs. Encrypt sensitive data at rest and in transit; protect secrets with a secret management mechanism.
- Set appropriate token/session lifetimes; constrain refresh tokens, and bind tokens to clients or senders where possible. Protect cookies with `Secure`, `HttpOnly`, `SameSite` where appropriate, CSRF, and session fixation defenses.
- For high-risk requests (changing recovery email, funds transfer, granting admin privileges), use **reauthentication/step-up via a still-trusted source** and independent business checks; never blindly trust `amr`/`acr` claims relayed by a suspected broker.
- Design an operational kill switch to disable **one partner/issuer/route** without bringing down all other integrations; test this procedure periodically.

### 6.3. Observing and Investigating Without Leaking More Secrets

Log structured authentication/authorization events: normalized timestamp, issuer, `client_id` or `azp` when present, audience, tenant, request correlation ID, validation result, endpoint, and allow/deny decision. Identifiers like `sub` must be handled under data protection policies; consider pseudonymization and log access controls.

**Never log raw** Access Tokens, ID Tokens, SAML Assertions, CAS tickets, passwords, refresh tokens, session cookies, or Authorization headers. Exposed logs can themselves become a source of attack tokens. Restrict log access and retain incident evidence per retention policy.

Useful alert signals include: spikes in token issuance, multiple tokens for the same subject from unfamiliar clients, unusual scopes/audiences, tokens from new issuers, logins to different tenants, unexplained role transitions, surges in signature/nonce failures, ticket/assertion replays, bulk API calls, and unscheduled JWKS/metadata changes.

## 7. Applying in Spring Security: API Verifying Tokens at Its Own Boundary

Suppose a Spring Boot backend protects `/partner-api/**` and trusts only **JWT Access Tokens** from a registered partner issuer. The example below uses **Spring Security servlet with Java 17+**, Spring Web, Spring Security, OAuth2 Resource Server, and JOSE dependencies (or corresponding Spring Boot starters). This is a **configuration class of a Spring Boot application**, not a standalone Java file runnable via `javac` without dependencies and a real issuer.

```yaml
# application.yml — illustrative URI/identifier; replace with approved configuration
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.partner.example/realms/partners
          audiences:
            - api://profile
```

Declaring `issuer-uri` enables Spring Security to obtain the appropriate validation configuration and verify issuer when processing JWTs; `audiences` requires tokens intended for **this API**. JWTs must still pass signature, timestamp, and decoder constraints. Endpoints open only to the intended scope:

```java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PartnerApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/partner-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/partner-api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain defaultDeny(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
    }
}
```

**Protection semantics:** The API verifies the JWT itself before serving data, checking `iss` and `aud` per configuration; GET `/partner-api/profile` requires `SCOPE_profile.read`. Other routes under `/partner-api/**` are denied; the default chain denies remaining routes in this minimal example. `STATELESS` and disabling CSRF apply solely to the Bearer-token API chain not relying on session cookies; **never copy that choice onto web pages using cookie login**. For multi-user data, the controller/service **must still check** that the caller is authorized to read that exact profile.

**Limitation not to overlook:** If the partner issuer itself is compromised and issues forged Access Tokens with valid `iss`, `aud`, scope, signature, and lifetime, the config above **can accept those forged tokens** because the asserting source lost security. You must have a process to **suspend acceptance of the affected issuer or route**, update trust configuration, and deploy containment at the API/network layer. Merely rotating public keys in config without handling old sessions/tokens is insufficient.

For web applications using **`oauth2Login`**, Spring Security handles OIDC RP flows per client registration; constrain issuers, redirect URIs, scopes, sessions, and `iss`/`sub` linking. For **SAML**, use `saml2Login`/`RelyingPartyRegistration` and verify assertions per SAML. For **CAS**, use the project-compatible CAS ticket validation mechanism. These three SSO types **cannot be replaced** by manually parsing JWTs in a controller.

### Integration-Level Verification Examples

In a test environment with an issuer and sample data, verify these cases:

| Request Data | Expected Outcome |
| --- | --- |
| Valid Access Token, right `iss`, `aud`, unexpired, has `profile.read`, proper record permission | Allowed to access declared endpoint |
| Token signed by another issuer or JWT with another API's `aud` | Authentication rejected |
| Expired token or invalid signature | Authentication rejected |
| Valid token missing `profile.read` | Endpoint permission denied |
| Token with right scope accessing another user's/tenant's profile | Denied by business authorization check |
| OIDC ID Token sent instead of Access Token | Rejected by API token type/audience policy; test explicitly to ensure issuer config does not inadvertently accept the wrong token type |
| Partner placed in suspended state | All requests relying on that trust are blocked, even with unexpired tokens |

HTTP `401` typically indicates invalid authentication; `403` typically indicates authenticated but insufficient permissions. Exact results depend on exception handling, endpoints, and authorization checks; test actual behavior rather than guessing from token templates.

## 8. Incident Response Playbook When Intrusion Is Detected

### Phase 1 — Identify and Immediately Constrain Trust Scope

1. Record signals, timestamps, partner, issuer/tenant/client, services, and potentially exposed artifact types; open a unified incident coordination channel.
2. **Close exploitable paths**: suspend clients/issuers/routes, disable affected keys or trust stores, isolate compromised gateways/brokers. Choose the narrowest block scope **that still protects** the entire attack path; if scope is unclear, apply the safer broader restriction.
3. Revoke tokens/refresh tokens and sessions as feasible; where JWTs lack instant revocation, block at the resource server, gateway, issuer trust, or authorization policy. Force re-authentication where appropriate.
4. Preserve evidence and protect related services: take forensic snapshots per procedure, retain necessary logs, and avoid writing new secrets/tickets into suspected compromised systems.

### Phase 2 — Investigate Actual Impact

1. Determine **what was exposed**: private signing keys, client secrets, refresh/access tokens, session cookies, CAS tickets, personal data, identity headers, or claim-editing privileges.
2. Determine **propagation paths**: which tokens had which API audiences, which scopes, which tenants, validity windows, and which downstream services were called.
3. Correlate logs across issuer, RP/SP, CAS server, gateway, APIs, and business data. Success/failure logs alone may be insufficient; check anomalous operations and data mutations.
4. Assess account links, automatic account creation (JIT), role grants, recovery-info changes, active sessions, and sensitive actions within the impact window.
5. Coordinate notifications with partners and data owners; determine user/regulator notification duties per applicable contracts and regulations rather than assuming one universal legal deadline for every case.

### Phase 3 — Conditional Trust Restoration

1. Re-enable only after the partner proves root-cause isolation, rotated necessary credentials/keys, remediated configs/apps, audited unauthorized access vectors, and provided test evidence.
2. Update issuer metadata/JWKS/trust stores via authenticated channels; confirm all consumers handled caches and old keys/credentials per plan.
3. Re-test all valid flows **and** spoofing flows: wrong-audience tokens, old tokens, signature/nonce/replay, client-injected headers, cross-tenant, excess scopes, and service tickets for wrong services.
4. Evaluate invalidating old sessions, requiring users to re-login, confirming all anomalous privileges were revoked, and verifying data integrity.
5. Re-open per client/route/tenant, closely monitor for recurrence indicators; document decisions, owners, and post-incident lessons.

**Critical practice:** Verify **both issuer behavior and consumer behavior** after remediation. Simply saying "the partner patched their server" is not enough to prove previously stolen access tokens, RP sessions, or wrong roles have ceased to work.

## 9. Strengths, Evidence, and Limits of Each Control

| Control | What It Solves Well | What It Does Not Solve on Its Own |
| --- | --- | --- |
| HTTPS/mTLS between hops | Reduces eavesdropping and connection spoofing; authenticates peers when properly deployed | A **compromised** endpoint can still read/modify data it is permitted to handle |
| Signing assertions/JWTs | Detects in-transit tampering while the issuing key remains trustworthy | A **compromised** issuer or private signing key can produce forged credentials with valid signatures |
| `issuer` + `audience` | Restricts token origin and intended recipient | Tokens issued by a trusted yet compromised issuer can still pass checks |
| `scope`/roles + record-level checks | Limits accessible operations and resources | If elevated claims are wrongly issued by a trusted broker, strict claim policies and internal permission cross-checks are needed |
| Short-lived tokens + rotation/revocation | Shrinks abuse window for leaked tokens, aids response | Self-contained JWTs and local sessions can persist without an active enforcement block |
| `state`, `nonce`, PKCE, and replay protection | Mitigates CSRF/login injection, response swapping, authorization code abuse, and assertion/ticket reuse in their respective flows | Cannot defend against all actions from a genuinely compromised IdP/OP |
| Network segmentation and stripping forged identity headers | Limits gateway bypass or identity manipulation from untrusted clients | Insufficient if the trusted gateway itself is compromised |
| Logging, alerts, and incident coordination | Shortens detection time, scopes impact, and drives response | Does not replace access checks at request time |

## 10. Scenario Exercises with Answers

**Scenario 1:** A SaaS partner leaked its client secret. Users still authenticate safely at the IdP. Can that client continue calling APIs since the IdP wasn't hacked?

**Answer:** You cannot conclude safety from IdP status alone. Determine whether the leaked secret can exchange authorization codes or use other grants, whether refresh/access tokens leaked, and which scopes/audiences were granted. Suspend or rotate the affected client's credentials, handle related tokens/sessions, audit logs, and restore only after closing the abuse path.

**Scenario 2:** A gateway sends `X-User-Role: admin` to the backend. The request travels over valid mTLS, yet the gateway was compromised. May the backend grant admin rights?

**Answer:** mTLS authenticates the gateway as a peer; it does not guarantee the gateway is asserting accurate claims. The backend must maintain its own authorization policy, restrict trusted claims, and require independent verification credentials or reject traffic from that path when the claim source is suspected of compromise.

**Scenario 3:** The IdP announces it rotated its signing key. An old token is still accepted by the API due to the JWKS cache and unexpired `exp`. Is the incident over?

**Answer:** No. Coordinate key and cache updates, revoke or block at-risk tokens, inspect local sessions, establish the compromise timestamp, and assess whether the issuer minted forged tokens before rotation. Temporary suspension of issuer/integration trust may be necessary.

**Scenario 4:** An API receives a JWT with a valid signature and `orders.read` scope, yet `aud` belongs to another API. Should it be allowed?

**Answer:** No. The token is not intended for the current Resource Server. Reject it despite valid signature/issuer/scope; also check specific order access permissions even when audience matches.

**Scenario 5:** A broker was compromised yet still signs downstream tokens with its valid private key while altering attribute `employee` to `administrator`. Can we rely on the signature to keep trusting the token?

**Answer:** No. The signature confirms the token was issued by the broker; it does not guarantee the broker remained faithful to upstream data. Isolate the broker, stop accepting affected claims, and audit mappings/permissions and executed actions.

## 11. Operational Checklist and Technical Conclusion

- [ ] Every federation link has an approved owner, issuer/entityID, audience/service, key, tenant, client, scope, and contact channel.
- [ ] SP/RP/CAS service/Resource Server validates the exact right artifact and never misuses tokens across purposes.
- [ ] All proxy identity headers are source-controlled, client-sent values are stripped, the proxy–backend channel is protected, and bypass is prevented.
- [ ] Data permissions are never granted solely from email, text role headers, or uncontrolled broker claims.
- [ ] Keys, tokens, sessions, and client credentials have appropriate rotation/revocation policies; logs contain no secrets.
- [ ] Individual partners/issuers/routes can be blocked and enforced at **the resource-consumption point**, even for unexpired tokens.
- [ ] Procedures exist for cross-party log correlation, impacted account/data assessment, partner outreach, recovery, and post-mortem review.
- [ ] Drills cover wrong issuer/audience/scope/tenant, replay, spoofed headers, and suspended issuers.

**Key takeaway:** In SSO/federation, each party protects **the boundary it controls**. When a partner or intermediary is compromised, previously issued credentials and assertions/tokens still traversing the compromised point must have their **trust re-evaluated**. Signatures, TLS, scopes, and SSO sessions are all valuable, yet no single mechanism protects identities if a system empowered to issue or transform credentials is compromised. Selective trust revocation, scoped permissions, and session/token revocation are indispensable parts of the architecture.

## References

- [NIST SP 800-63C-4 — Digital Identity Guidelines: Federation and Assertions (2025)](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): federation boundaries and assertion protection.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validation, issuer/audience, decoder, and scopes.
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `issuer-uri` and `audiences` in configuration.
- [Spring Security — SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): Service Provider configuration and assertion verification.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, validation, and Relying Party role.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): securing OAuth flows, clients, redirects, and tokens.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): separating token purposes, algorithms, and verification data.
