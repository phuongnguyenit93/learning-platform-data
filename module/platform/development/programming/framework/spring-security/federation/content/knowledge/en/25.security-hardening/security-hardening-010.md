# Protecting Callbacks, Keys, Keytabs, and Partner Configuration Admin Endpoints

## 1. Problem Statement and Hardening Objectives

A **Spring Security - federation** application can authenticate users through multiple partners: OIDC OpenID Providers, SAML Identity Providers (IdPs), CAS Servers, Kerberos realms/KDCs, or an authenticating reverse proxy. These integrations rely on three sensitive asset groups:

1. **Callback endpoints**: where browsers or partner servers deliver authorization codes, SAMLResponses, CAS tickets, proxy-granting tickets, or logout notifications to the application.
2. **Keys and credentials**: OIDC client secrets, SAML Service Provider signing/decryption private keys, IdP verification certificates, JWKS, Kerberos keytabs, TLS private keys, and bearer tickets.
3. **Partner configuration admin endpoints**: changing issuers, IdP entityIDs, certs, token/JWKS/metadata URLs, redirect/ACS endpoints, SPN/keytab secret references, group-to-role mappings, or per-tenant policies.

A flaw in a callback can cause login CSRF, replay, token substitution, account takeover, or session confusion. A leaked keytab/private key can break service authentication boundaries. An admin API allowing unauthorized modification of verification certificates or issuers can cause the app to **trust an attacker-controlled IdP** even when the signature verification library itself works properly.

**Objective:** distinguish each callback and credential type, design protocol-accurate trust checks, store/rotate keys safely, block SSRF from metadata, enforce RBAC/MFA/CSRF/dual approval on configuration APIs, implement scoped Spring Security controls, and test dangerous cases with a Java 17 example.

> **Core principle:** callbacks may be **reachable before the user has a local Authentication**, yet must be verified by **protocol validators**. Conversely, **identity configuration modification endpoints** must be a management plane protected by authentication and administrative authorization—there is no reason to make them public just because callbacks are public.

## 2. Threat Model and Trust Boundaries

~~~text
Internet / Browser / Untrusted requests
         |
         +--> OAuth2/OIDC callback with code + state
         +--> SAML ACS with SAMLResponse + RelayState
         +--> CAS ST callback with ticket
         |
         v
 Spring Security authentication filters
   - resolve approved ClientRegistration / RelyingPartyRegistration
   - check state/PKCE/nonce or SAML signature/conditions
   - check issuer, audience, recipient, replay, expiry
   - create Authentication only after validation
         |
         v
       Local authorization / business APIs

 CAS Server -- trusted back-channel --> PGT receptor / SLO callback

 Admin / automation -- RBAC + MFA + approval --> Partner Config API
                                |
                                v
                  Immutable DRAFT, validation
                  Metadata fetch sandbox / trust review
                  Separate APPROVAL / ACTIVE versions
                                |
                                v
                 Approved config read by login filters

 Secret store/KMS -- scoped workload identity --> keytab/private keys
~~~

| Entry point / asset | Primary trust source | Key risks |
| --- | --- | --- |
| OIDC redirect callback | ClientRegistration + state/nonce/PKCE + verified tokens | Code injection, mix-up, open redirect, login CSRF. |
| SAML2 Assertion Consumer Service | RelyingPartyRegistration + IdP certificate + OpenSAML validation | XML signature wrapping, unsigned assertion, replay, audience mismatch. |
| CAS service ticket callback | CAS Server ticket validation + service binding | Ticket replay, login using ST from another service. |
| CAS PGT receptor | CAS Server back-channel + inbound trust + IOU correlation | Forged PGT callback, credential leak in URLs. |
| CAS Single Logout | CAS SLO transport trust + SessionIndex→local session | Forged logout or deleting the wrong sessions. |
| Kerberos acceptor | KDC/realm/SPN + keytab + GSS validation | Keytab leak, SPN/KVNO mismatch, downgrade. |
| SAML SP private key | Governed KMS/HSM/keystore | SP impersonation, decrypting SP-targeted data. |
| IdP certificate / OIDC JWKS | Approved issuer metadata, pinned/trusted keys | Accepting a spoofed issuer's cert/key. |
| Partner admin API | Admin identity, least privilege, step-up, dual control | Arbitrary changes to trust anchors, issuers, or role mappings. |
| Metadata URL fetcher | Approved destinations + egress sandbox + signature review | SSRF, DNS rebinding, XML XXE, auto-trusting malicious keys. |

**Do not equate network trust with identity trust.** TLS to a metadata endpoint authenticates the host per the CA system, yet does not authorize that host to become an IdP; a validly signed SAMLResponse with the right cert yet missing audience is not a ticket for the app; an already logged-in admin does not automatically have permission to change another partner's cert.

## 3. Inventorying Endpoints and Permissions Before Hardening

The URLs below are defaults/common in Spring Security Servlet; actual configurations vary by version and context path.

| Type | Example endpoint | Caller | Required protection |
| --- | --- | --- | --- |
| OIDC initiation | `/oauth2/authorization/{registrationId}` | Browser | Resolved client registration, generate state/PKCE/nonce. |
| OIDC callback | `/login/oauth2/code/{registrationId}` | Browser redirect | State/issuer/token checks; never raw code login. |
| SAML initiation | `/saml2/authenticate/{registrationId}` | Browser | Generate AuthnRequest, store correlation. |
| SAML ACS | `/login/saml2/sso/{registrationId}` | Browser HTTP POST | XML signature, conditions, issuer, recipient, replay. |
| Public SAML metadata | `/saml2/metadata/{registrationId}` | IdP/browser | May allow public GET, **exports public keys/certs only**, no edit rights. |
| SAML SLO | `/logout/saml2/sso` and variants | Browser/IdP | SAML logout protocol, signature/trust/correlation. |
| CAS ST callback | `/login/cas` | Browser | Validate ST at CAS Server for the exact service. |
| CAS PGT receptor | `/login/cas/proxyreceptor` | CAS Server | Inbound machine trust, HTTPS, store IOU→PGT. |
| CAS SLO | Service-configured endpoint | CAS Server or browser per mode | Back-channel source trust, exact ST→session. |
| Partner management | `/internal/federation/partners/**` | Admin/automation | MFA, RBAC, tenant, CSRF, two-person approval, audit. |

**Callbacks differ from admin endpoints:** first-time logging-in users lack a Spring session, so you cannot demand an admin role on ACS/OIDC callbacks—yet dedicated authentication filters must still run. `/internal/federation/partners/**` must block anonymous callers and any unprivileged actor, even if they hold a regular user account.

When changing callback URLs, synchronize **Spring registrations**, IdP/Authorization Server allowlists, reverse proxy public scheme/host, cookie/session correlation, and monitoring. Never use wildcard redirect URIs to “avoid updating configuration”.

## 4. OIDC/OAuth2 Callbacks: state, nonce, PKCE, and issuer

### 4.1. Valid flow

~~~text
Browser GET /oauth2/authorization/corp
    -> OAuth2AuthorizationRequestRedirectFilter
    -> known ClientRegistration("corp")
    -> generate transaction-specific state, PKCE, OIDC nonce
    -> redirect to trusted authorization endpoint

Authorization Server returns browser redirect:
  GET /login/oauth2/code/corp?code=...&state=...

OAuth2LoginAuthenticationFilter:
    -> load matching authorization request
    -> verify state/correlation and selected provider
    -> exchange code with correct token endpoint + verifier
    -> verify ID Token issuer/audience/signature/expiry/nonce
    -> map verified principal to local account/authorities
    -> create Spring Security Authentication/session
~~~

**`code` is not standalone login proof.** It must be exchanged at the exact token endpoint of the Authorization Server chosen in the initial transaction. Also never accept `?issuer=https://other.example` and use that URL to decide issuer/token endpoint/JWKS.

### 4.2. Separating the roles of controls

| Mechanism | What it guarantees |
| --- | --- |
| `state` | Binds the callback to the login transaction/browser, preventing login CSRF and flow confusion. |
| OIDC `nonce` | Binds the ID Token to the authentication request, preventing token replay/misbinding in OIDC profiles. |
| PKCE `code_challenge`/`code_verifier` | Prevents authorization code injection/theft without the verifier. |
| `iss` / AS mix-up defense | Ensures token/response matches the approved issuer, preventing attacker-driven provider switching. |
| `aud`, expiry, signature, alg | Ensures token matches RP/client and verifies under an approved issuer key. |
| Registered redirect URI | Exact match per OAuth Security BCP; prevents open redirects. |
| Authorization request repository | Preserves state/nonce/PKCE transaction context until callback, including across multi-node clusters. |

Per RFC 9700, **PKCE is mandatory for public clients** and recommended for confidential clients; clients must prevent CSRF on authorization responses using standard-permitted mechanisms. Never casually drop state/nonce when moving to multi-provider setups. **OIDC nonce/PKCE/state serve overlapping goals yet are not interchangeable substitutes.**

### 4.3. Multi-IdP and mix-up

Example:

~~~text
corp issuer:    https://login.corp.example
partner issuer: https://login.partner.example

User initiates login with corp.
Attacker submits partner's response/code to corp callback.

Required:
  - callback binds to exact initial authorization request
  - issuer/token endpoint cannot be switched via query
  - ID Token iss/aud match expected registration
  - code/PKCE only used in the matching transaction
~~~

When supporting multiple Authorization Servers, implement a **mix-up countermeasure** per RFC 9700: issuer indication in response/ID Token/JARM or distinct redirect URIs where profile permits; never rely on a browser-editable `registrationId` to switch trust.

### 4.4. SameSite, CSRF, redirects, and logs

- Default browser callbacks are normally top-level **GET**; `SameSite=Lax` can work so the authorization-request cookie travels along, depending on browser and setup.
- For **`form_post`** callbacks, SameSite/cross-site cookies behave differently; test real cookie policy.
- OIDC callbacks lack traditional form CSRF tokens yet carry protocol `state`/nonce/PKCE/correlation; **do not disable CSRF app-wide**.
- Admin POSTs using browser cookies must keep CSRF tokens/Origin checks.
- Never redirect the browser post-login to arbitrary `returnUrl`/`next`. Prefer validated internal paths or a strict destination allowlist.
- Never record raw `code`, `state`, ID/access/refresh tokens, or browser cookies in reverse proxy/APM/application logs.
- Never let an attacker control the callback base URI or Host/X-Forwarded-* headers used to build redirect URIs if the proxy lacks a trusted forwarded-header boundary.

**Spring Security `oauth2Login().redirectionEndpoint().baseUri(...)` only changes the URL matcher**; when customizing, ensure `ClientRegistration.redirectUri` matches and the IdP registered the exact redirect URI.

## 5. SAML2 ACS: XML Signatures, Audience, Correlation, and Replay

SAML Web SSO usually delivers responses through the browser:

~~~http
POST /login/saml2/sso/partner-a HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<opaque-encoded-xml>&RelayState=<opaque-state>
~~~

The browser **is not a trusted source** merely because it POSTs to the right ACS. Spring Security uses `Saml2WebSsoAuthenticationFilter` and the OpenSAML authentication provider to ingest/validate against an approved `RelyingPartyRegistration`. **Never manually create an Authentication from parsed `NameID` or XML.**

### 5.1. SAML Response verification checklist

| Check | Why is it mandatory? |
| --- | --- |
| Signed response/assertion | Accept only XML structures with properly scoped signatures per profile/trust. |
| Trusted IdP signing certificate | Valid signature with an untrusted public key still establishes no identity. |
| Issuer / asserting party | Must match the IdP entityID in the approved registration. |
| Destination / Recipient / ACS | Assertion must target the exact SP endpoint/destination. |
| AudienceRestriction / SP entityID | Token meant for this relying party; reject assertions from other apps. |
| InResponseTo/SubjectConfirmation | Bind assertion to AuthnRequest when required by SP-initiated flow. |
| Conditions: NotBefore, NotOnOrAfter | Reject outside time window + configured skew. |
| Replay cache | An Assertion ID/Response ID per policy must not grant login twice. |
| RelayState policy | Never turn into an open redirect or restore arbitrary external URLs. |
| Parser/size hardening | Defend against XXE, entity expansion, XML wrapping, and DoS. |

**HTTPS alone cannot replace signatures**, because a browser can submit any SAMLResponse over a valid TLS connection. Never disable audience/subject confirmation/in-response-to requirements to avoid integration errors.

### 5.2. Signing differs from encryption

- **IdP signing private key**: owned by IdP, signs assertions/responses.
- **IdP verification certificate**: SP holds the approved public cert to verify IdP signatures.
- **SP signing private key**: used by SP to sign AuthnRequest/LogoutRequest when required by profile.
- **SP decryption private key**: used by SP to decrypt SP-targeted EncryptedAssertion/EncryptedAttribute.
- **SP encryption public cert**: used by IdP to encrypt data for the SP.
- **TLS private key**: protects HTTPS; not automatically identical to signing/decryption keys.

A SAML assertion can be **encrypted without carrying a trusted signature**; encryption does not prove the issuer on its own. Conversely, a properly signed response declaring an `AudienceRestriction` for another app must also be rejected. Depending on the case, OpenSAML's verification/decryption order is critical; never swap decrypters casually and bypass validation.

### 5.3. ACS POST and CSRF exemptions

An IdP POST lacks the RP's form CSRF token, so the system may need a **CSRF exemption strictly on the SAML ACS endpoint** per Spring Security integration. That is not `csrf.disable()` for the whole web app. Ensure:
- The ACS still runs through full Spring Security filters and OpenSAML validators.
- The CSRF exemption matcher is tightly scoped by path/method, never covering `/internal/federation/**`.
- Admin actions still require CSRF/Origin, MFA, and RBAC.
- SAML SLO has its own profile; never treat arbitrary XML POSTs under `/login/**` as valid.

### 5.4. Metadata trust does not arise automatically from HTTPS fetches

IdP metadata typically includes entityID, SSO/SLO endpoints, verification certs, and bindings. Note Spring's `OpenSaml5AssertingPartyMetadataRepository` can accept **`verificationCredentials`** to verify metadata XML signatures; **without configured verification credentials, this repository does not validate metadata signatures** per documentation.

Therefore:
- Bootstrap IdP entityID/trust anchors through partner approval.
- If signed metadata is available, verify it with a trusted **approved metadata signing cert**.
- Otherwise, use fingerprints/out-of-band approval and staged key rotation.
- Never “auto-accept a new cert” just because content was fetched over an HTTPS URL.
- Metadata URLs are SSRF/XXE inputs, even when entered by an admin role.

## 6. CAS: Three Callbacks with Distinct Purposes

### 6.1. Browser carrying Service Ticket

~~~text
Browser -> GET /login/cas?ticket=ST-...
Portal -> CAS /serviceValidate or /proxyValidate
CAS Server verifies ticket against exact service URL
Portal accepts principal only on successful validation
~~~

An ST is a **one-time, service-bound ticket**. Never log in just because the query contains `ticket`, never accept an ST meant for another service, and never replay an ST after validation. Spring `CasAuthenticationFilter` and the version's provider/validator implement this mechanism. CAS server URL and `ServiceProperties.service` must align across reverse proxies.

### 6.2. Proxy-granting ticket receptor

When CAS Proxy is enabled, the CAS Server can issue an HTTPS GET:

~~~http
GET /login/cas/proxyreceptor?pgtId=PGT-opaque&pgtIou=PGTIOU-opaque HTTP/1.1
Host: portal.example.org
~~~

- `pgtId` is a **bearer credential** and must remain secret.
- `pgtIou` is the correlation key; the CAS ticket validation response returns the IOU, **not the real PGT**, in the standard callback flow.
- The receptor stores IOU→PGT, then the validator looks up the exact IOU to attach the PGT to the authenticated principal; **never match by username or latest timestamp**.
- The callback is server-to-server, **with no browser JSESSIONID**.
- While the CAS Server checks the receptor's HTTPS certificate when delivering PGT, **the receptor must enforce its own inbound trust** via mTLS/allowlisted gateway/network controls.
- The receptor should ACK only after persisting to shared storage in multi-node clusters; on store timeout, never return a fake 200.
- Redact `pgtId`, `pgtIou`, and `pgt` from query logs across gateways, APM, and backend.

### 6.3. CAS Single Logout

CAS can send `logoutRequest` to terminate app sessions. In CAS SLO, `SessionIndex` typically maps to the service ticket ID used to locate the local HttpSession—**never delete all sessions by username**.

Do not infer from SAML-namespaced XML that a CAS logoutRequest is a signed SAML 2.0 SLO message. Enforce CAS-appropriate transport/source trust, version-matching `SingleSignOutFilter`/session mapping, idempotency, and protection against forged callbacks. When callbacks arrive late or are lost, app sessions can remain active; SLO is **best effort**, requiring TTL/revocation/audits.

## 7. Key and Credential Stores: Clear Role Separation

| Credential | Who holds the secret? | How must it be protected? |
| --- | --- | --- |
| OIDC client secret | OAuth RP and Authorization Server | Secret manager, rotate/revoke, never expose to frontend. |
| private_key_jwt client-auth private key | OAuth Client | KMS/HSM, signed auth, publish approved public key. |
| OIDC issuer JWT signing private key | Authorization Server | Never share private key with RP; RP uses trusted public JWKS. |
| SAML SP signing private key | SP | KMS/keystore, non-exportable where appropriate, role-isolated. |
| SAML SP decryption private key | SP | Retain long enough to decrypt in-flight encrypted assertions during rotation. |
| SAML IdP verification certificate | Public cert trusted by SP | Pin/approve per entityID and signing role; never auto-trust. |
| HTTPS TLS private key | Ingress/service endpoint | Certificate chain/hostname, independent rotation, not shared by default with SAML keys. |
| Kerberos keytab | Kerberos acceptor with SPN | Read-only secret mount, file ACLs, KVNO/enctype/realm. |
| CAS PGT/ST/PT | CAS and respective parties | Bearer secret, TTL/one-time semantics, log redaction. |
| Keystore/KMS access credentials | Approved workloads | Scoped workload identity, audit secret read/use/rotation. |

**Public JWKS or SAML metadata may contain public keys/certificates for verification/encryption. They must never contain private keys, JWK private members, keytabs, or client secrets.**

### 7.1. Secret management practices

1. Use **workload identity** rather than sharing one service-account secret across all pods.
2. Grant access by environment/tenant/partner/key purpose; only the SP needing a decryption key may read it.
3. Use KMS/HSM and secret vaults with audited lifecycles: create, use, rotate, revoke, expire.
4. Never commit keytabs/private keys to Git, CI artifacts, Kubernetes ConfigMaps, Docker image layers, bug reports, or docs.
5. Secrets in environment variables can leak via logs/process diagnostics; prefer platform-protected secret delivery and runtime memory controls.
6. When mounting secret files, apply minimal owner/group/mode, read-only mounts, and container least privilege; protect backups and crash dumps.
7. Never allow actuator `/env`, `/configprops`, heap dumps, debug pages, or admin config downloads to expose credentials.
8. Never log raw `Authorization`, `Cookie`, SAMLResponse, OIDC codes/tokens, CAS tickets, PGT, keytabs, or PEM private keys.
9. Establish owners, expiration dates, rotation windows, peer change notifications, and emergency revocation playbooks.

**Base64-encoded Kubernetes Secrets are not secure by themselves**: RBAC, etcd encryption, kubelet/pod access control, secret backup retention, and service identity policies are required.

## 8. Rotating SAML Keys, JWKS, and Client Credentials

### 8.1. Each direction switches at a different point

- **IdP signs, SP verifies**: IdP publishes the new public cert before signing with the new private key; SP accepts the **approved** cert set during an overlap window; then retire the old cert on schedule or revoke immediately on compromise.
- **SP signs, IdP verifies**: SP publishes the new public signing cert, partner updates trust, and only then does SP switch to the new private key. Never switch signing before the partner is ready.
- **IdP encrypts, SP decrypts**: SP publishes the new encryption public cert while carefully retaining the old decryption private key to handle in-flight assertions.
- **OIDC/JWT signing**: AS publishes the new public JWK in trusted JWKS with proper key ID/algorithm before signing with the new key; RP refreshes cache per policy and keeps old verification keys for remaining valid tokens unless compromised.
- **OIDC client secret**: rotate at Authorization Server + RP runtime secret store, using overlap if provider supports it to avoid downtime, then revoke old secret promptly once complete.

### 8.2. A safe rotation schedule

~~~text
Inventory active partner version and cryptographic key roles
  -> Generate new key (KMS/HSM or approved key service)
  -> Publish public verification/encryption material
  -> Confirm counterpart readiness and trusted metadata
  -> Stage new config as immutable DRAFT
  -> Independent reviewer checks issuer/cert/fingerprint/expiry
  -> Run partner integration test + canary
  -> Atomically activate new version
  -> Monitor issuer/signature/JWKS/KVNO failures
  -> Retire old key after the agreed overlap
  -> Audit and update incident response records
~~~

Overlap windows depend on assertion/token lifetimes, clock skew, cache refresh, in-flight callbacks, and contracts. **Never retain a compromised old key to preserve availability.** When compromise is suspected, evaluate emergency disable/revocation even if it causes disruption.

### 8.3. OIDC JWKS and JWT algorithm confusion

- `kid` is **only a selector** among keys belonging to an **approved issuer/JWKS endpoint**. A new `kid` does not make a key trusted.
- `alg` must be in the issuer/client allowlist; disallow `none` or HS/RS confusion against profile.
- Never fetch `jku`/`x5u` from an arbitrary JWT header to pick keys.
- Protect JWKS endpoint HTTPS/DNS, enforce response size limits, timeouts, and cache failure handling.
- Tokens must verify issuer/audience/expiry and protocol claims; **a valid signature is not enough** if the token was meant for another app.

## 9. Kerberos Keytabs: SPN, KVNO, File Permissions, and Multi-Node

For HTTP Negotiate, a web service typically uses:

~~~text
Public URL:   https://portal.example.org
Kerberos SPN: HTTP/portal.example.org@CORP.EXAMPLE.ORG
Keytab:       /etc/security/keytabs/portal-http.keytab
~~~

**`HTTP/` is the Kerberos service class, not permission for cleartext HTTP.** Users should use HTTPS to protect cookies and token exchanges. Kerberos service tickets for the public host must be accepted using the matching key in the service's keytab.

### 9.1. Keytab rules

- The SPN must bind to the **exact service account**, with no duplicate SPNs or wrong aliases.
- Keytabs hold long-term secrets; never publish/download them through admin UIs or docs.
- Mount read-only, block anonymous pod/host access, and enforce filesystem ACLs and container privileges.
- Verify **Key Version Number (KVNO)**, encryption types, and realm when rotating account passwords/keys.
- Multiple pods accepting `HTTP/portal.example.org` need matching keys for new tickets during rollout; test every node and failover.
- Never place keytabs in Git, container images, traces, stdout, or startup debug logs.
- Clock skew/KDC DNS/realm trust must follow Kerberos policy; never disable GSS validation over KVNO errors.
- If a keytab is suspected leaked, rotate the service-account key in KDC/AD, issue a new keytab, revoke old keys, and assess impact on active sessions.
- If a proxy terminates Kerberos and sets a principal header, Spring must protect the trusted gateway and strip spoofed headers; that model **differs** from Spring verifying GSS tickets directly.

### 9.2. Operational errors

| Symptom | Suspect | What to check |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` | Keytab wrong SPN/account/KVNO, duplicate SPN. | KDC registry, service account, and key material version. |
| `KRB_AP_ERR_SKEW` | Clock drift. | NTP on KDC/client/server; never disable time checks. |
| Service principal unknown | KDC lacks `HTTP/public-fqdn`. | DNS canonicalization, SPN registration. |
| Pod A logs in, B fails | Staggered keytab version/credential rollout. | Secret mounts, KVNO/enctype, and rollout policy. |
| Browser does not send `Authorization: Negotiate` | Browser trust/SSO policy not enabled. | Domain/KDC/TGT, URL allowlist; never casually enable Basic. |
| NTLM accepted despite Kerberos-only policy | SPNEGO fallback unrestricted. | Inspect GSS-selected mechanism and OS policy. |

## 10. Partner Config Admin Plane: Higher Security Than User Login

Admin config endpoints can affect:
- OIDC issuer, client ID, redirect URI, authorization/token/JWKS URLs, client secret references.
- SAML IdP entityID, ACS/SLO URLs, verification certs, metadata sources, signing/decryption keys.
- CAS Server URL, service identifier, PGT receptor URL, logout delivery.
- Kerberos realm/SPN/keytab references.
- Attribute/claims mapping, trusted groups/roles, default authorities, and tenant memberships.

**Anyone able to alter a trust anchor or map an external group to local admin can control authentication and authorization for large numbers of users.** Therefore, an ordinary “content administrator” role must never hold this privilege.

### 10.1. Separating permissions by operation

| Permission | Action |
| --- | --- |
| `federation:read` | View redacted partner status/metadata, audits, expiry; cannot read private keys/keytabs. |
| `federation:propose` | Create an immutable config draft. |
| `federation:validate` | Run validators/metadata fetch sandbox and integration tests. |
| `federation:approve` | Independent approval after checking issuer/cert/tenant. |
| `federation:activate` | Activate an approved config version. |
| `federation:rotate-secret` | Invoke an authorized KMS/vault workflow; never download raw keys. |
| `federation:emergency-disable` | Revoke trust relationship on compromise. |

Do not check only HTTP `hasRole('ADMIN')`: the service layer must enforce **tenant ownership, draft version, distinct proposer/reviewer, fresh MFA/step-up, and exact operation scope**. An approver must not approve their own draft when dual control is required.

### 10.2. Configuration state machine

~~~text
DRAFT
  | schema, URL, issuer, cert, algorithm, risk validation
  v
VALIDATED
  | independent reviewer + fresh MFA + change ticket
  v
APPROVED
  | compare-and-swap version + canary + atomic publish
  v
ACTIVE
  |
  +-- ROLLBACK to an earlier approved and still-secure version
  +-- EMERGENCY DISABLE when compromise is suspected
~~~

Never let request JSON supply `status=APPROVED`, `approvedBy=security-team`, or `isAdmin=true` directly into the DB. Approval must be a **genuinely authenticated action** with time/actor/policy checks and auditing.

### 10.3. Multi-node administration and in-flight login transactions

Configurations must have immutable versions. When an OIDC/SAML login transaction starts on version 6 and an admin activates version 7:
- Preserve the initial login's transaction context.
- Do not pick the “latest” JWKS/issuer to validate an old callback unless part of an approved overlap policy.
- Never mix an old issuer, a new token endpoint, and a new cert into an inconsistent registration.
- Use atomic publishing or versioned cache invalidation across pods.
- Use optimistic locking/`expectedVersion` when operators activate concurrently.
- Roll back the **entire config version**, never overwriting individual fields piecemeal.
- Never roll back to a compromised key/issuer just to reduce login errors.

## 11. Metadata Fetcher: SSRF and XML XXE

An admin may enter a seemingly harmless metadata URL:

~~~text
https://idp.partner.example/metadata
~~~

However, the server then becomes an HTTP client fetching that URL. Unprotected, the URL could target private services, Kubernetes APIs, or cloud instance metadata. Even when the initial hostname is valid, **DNS rebinding or HTTP redirects** can steer the request to an internal IP.

### 11.1. Cases to block

- Loopback `127.0.0.1`, `::1`, localhost aliases.
- Link-local/cloud metadata such as `169.254.169.254`.
- Private IPv4/IPv6, Kubernetes cluster DNS/services, internal management networks.
- URLs with userinfo, encoded hosts, disallowed schemes/ports, or redirects to internal IPs.
- DNS A/AAAA changing between check and actual connect.
- Oversized/slow responses, excessive redirects, recursive metadata, parser abuse.
- XML DOCTYPE/external entities/XXE, DTD/network fetches, entity expansion.
- Metadata signed with an **unapproved** cert or declaring an issuer different from expected entityID.

### 11.2. Multi-layered defenses

1. Prefer exact **approved partner hostname/metadata paths** over a generic “admin can type any URL”.
2. Allow HTTPS only, verify TLS chain/hostname; forbid userinfo and unusual URL forms.
3. Resolve/check all IPs at connect time, blocking private/loopback/link-local/metadata IPs for both IPv4 and IPv6.
4. Defend against DNS rebinding via connector/egress proxy or IP pinning with connection policy; **never do one DNS check and then let the HTTP client resolve again**.
5. Disable automatic redirect following; if mandatory, re-validate every hop and stay strictly within approved destinations.
6. Egress firewall/service-mesh policy permitting only required hosts/services and blocking internal/cloud metadata.
7. Bound read/connect timeouts, response size, XML depth, and concurrent fetches.
8. XML parser hardening: disable DTD/external entities, disallow external schema downloads, block XXE.
9. After fetching: verify expected issuer/entityID, metadata signature if the profile has an approved signer, cert fingerprints/validity, and allowable algorithms/bindings.
10. Never auto-activate a new cert simply because metadata is valid XML or fetched over HTTPS; require staged approval/trust bootstrap.
11. Audit URL refs and metadata content hashes without logging raw secrets.

**Checking the URI host once in Java is only a preliminary layer.** Production needs a dedicated metadata-fetch service with **deny-by-default egress**, DNS/connect/redirect checks, and separate trust activation records.

### 11.3. Trust bootstrap for signed metadata

Spring Security supports metadata signature verification when proper verification credentials are given to `OpenSaml5AssertingPartyMetadataRepository`. Without approved metadata signing keys, there is no proof that “this metadata was signed by a trusted partner”.

A sound bootstrapping workflow:
1. Confirm the partner over a contractual/approved channel.
2. Verify entityID, TLS endpoint, and approved trust fingerprint.
3. Store the trust anchor/fingerprint in a versioned registry.
4. On every metadata refresh, verify signer, expiry, issuer, and change policy.
5. If a cert changes off-schedule, keep the old approved config or fail closed and alert for review.
6. Only after approval promote verification credentials into the active Spring registration.

## 12. Spring Security Pattern Separating Admin Plane and Callback Plane

The Spring Boot Servlet sample below protects only the **admin API**; it does **not** implement OAuth2/SAML/CAS callbacks, KMS, metadata fetchers, or MFA inside the same snippet.

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FederationAdminSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/internal/federation/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/internal/federation/**")
                    .hasAuthority("federation:read")
                .requestMatchers(
                    HttpMethod.POST, "/internal/federation/**")
                    .hasAuthority("federation:manage")
                .requestMatchers(
                    HttpMethod.DELETE, "/internal/federation/**")
                    .denyAll()
                .anyRequest().denyAll());
        // CSRF is NOT disabled; browser sessions must remain protected.
        // Admin authentication and fresh-MFA checks live elsewhere.
        return http.build();
    }
}
~~~

This is a **configuration fragment** requiring Spring Security/Servlet dependencies; it is not a standalone Java SE app. A real application also requires:
- Separate chains for OIDC/SAML/CAS login/callbacks with approved `ClientRegistrationRepository` or `RelyingPartyRegistrationRepository`; ordering/matchers must not overlap improperly.
- Admin Authentication (enterprise OIDC or machine mTLS) and an independent step-up policy.
- Method/service authorization, tenant scoping, 2-person approval, and version compare-and-swap.
- CSRF protection on admin browser POSTs, CORS allowlists, rate limiting, and request size limits.
- Strict metadata fetch/egress service, secrets manager, and redacted audits.
- Alignment of Spring Security/APIs with your exact version (6/7, Jakarta Servlet).

**Never use `web.ignoring()` to remove callbacks from the SecurityFilterChain altogether.** Depending on protocol, `permitAll` on a callback allows filters to execute before local Authentication exists; callbacks still need validators. Never add app-wide `csrf.disable()` just because SAML ACS uses POST.

### 12.1. Mandatory policy layer beyond HTTP matchers

~~~text
propose(actor, tenant, draft):
  require actor has federation:propose for tenant
  require verified login and fresh MFA for risk-level
  validate schema and metadata target, no raw private key
  persist immutable DRAFT + expected active version

approve(reviewer, draft):
  require reviewer has federation:approve for tenant
  require reviewer != proposer
  require metadata issuer/key material verified
  record signed approval decision and timestamp

activate(operator, draft):
  require operator has federation:activate for tenant
  require APPROVED + healthy canary
  require expectedVersion == currentVersion
  atomically publish entire config, KMS key references only
  audit before/after version and rollback pointer
~~~

**Never allow users to alter issuer/JWKS/cert via callback query parameters**, and never let an overprivileged service account create, approve, and activate alone when policy requires separation of duties.

## 13. Partner Configuration via a Versioned Draft

Internal design example (not actual Spring configuration):

~~~json
{
  "partnerId": "partner-a",
  "tenantId": "finance-vn",
  "protocol": "SAML2",
  "idpEntityId": "https://idp.partner.example/saml",
  "metadataUrl": "https://idp.partner.example/metadata",
  "metadataSignerRef": "kms://trust/partner-a-metadata",
  "verificationCertRefs": [
    "secrets://partner-a/saml-verification-current"
  ],
  "allowUnsignedAssertions": false,
  "requireAudienceRestriction": true,
  "requireRequestCorrelation": true,
  "allowUnsolicitedSso": false,
  "replayStoreRef": "internal-replay-store",
  "spSigningKeyRef": "kms://sp/finance-vn/signing",
  "status": "DRAFT",
  "version": 7,
  "changeRequestRef": "chg-2026-1107"
}
~~~

The `kms://` and `secrets://` values in JSON are **symbolic references**, not real secrets or URLs. The API must never treat `status` inside incoming JSON as authoritative: DRAFT/APPROVED/ACTIVE state is governed by the business workflow. Never allow uploading PEM private keys via a general JSON endpoint; if actual import is needed, use a dedicated controlled process.

## 14. Runtime Hardening, Logs, and Audit

### 14.1. Multi-node systems

- Share/synchronize session state, OIDC authorization request state, SAML replay caches, and CAS PGT IOU storage per consistency requirements.
- Atomic consume with appropriate TTL; never let Node A accept a SAML assertion and Node B accept it again due to local caches.
- Pin or resolve the exact approved partner config version; never handle a callback with an inconsistent mix of old issuer and new JWKS.
- NTP for SAML Conditions, OIDC exp/iat, and Kerberos skew.
- Uniform multi-node keytab/decryption key rollout per rotation plan.
- When a store/revocation service fails, never fail open just to raise login success rates.
- Reverse proxies preserve exact Host/scheme/ACS/redirect URI, trusting forwarded headers only from configured proxies.
- Public callback paths enforce rate limiting, request size limits, and safe error responses; admin routes enforce network-level controls.

### 14.2. Never log credentials at any layer

Redact:
- OAuth `code`/`state`/`id_token`/`access_token`/`refresh_token`.
- Sensitive SAML `SAMLResponse`/`RelayState` and XML attributes carrying PII.
- CAS `ticket`/`pgtId`/`pgtIou`/`pgt` in URLs.
- `Authorization`, `Cookie`, `Set-Cookie`, and Kerberos `Negotiate` tokens.
- PEM private keys, keystore passwords, keytabs, and JWK private members.
- Admin config API JSON if it reveals secret reference policies.
- Credentials in debug exceptions, JVM heap dumps, CI logs, and backups.

Use correlation IDs or HMAC references (with a dedicated audit secret) and reason codes like `SAML_AUDIENCE_MISMATCH`, `OIDC_STATE_MISMATCH`, `METADATA_FETCH_BLOCKED`.

### 14.3. Useful metrics

~~~text
federation_callback_received_total{protocol,partner}
federation_callback_rejected_total{protocol,reason}
federation_oidc_state_mismatch_total{partner}
federation_saml_signature_invalid_total{partner}
federation_saml_replay_rejected_total{partner}
federation_cas_pgt_callback_failed_total{service}
federation_key_rotation_failed_total{partner,key_role}
federation_secret_expiry_days{partner,key_role}
federation_admin_change_total{action,outcome}
federation_metadata_fetch_blocked_total{reason}
federation_active_config_version{partner}
~~~

Never put raw user identifiers, tickets, JWTs, IPs, or unbounded input in metric labels (high cardinality and data leakage). Alert on spikes in signature failures after cert rotation, unapproved admin config activations, or metadata fetches attempting to reach internal networks.

### 14.4. Audit event

~~~text
event=FEDERATION_PARTNER_ACTIVATION
time_utc=2026-11-07T09:00:00Z
partner_ref=partner-a
tenant_ref=finance-vn
from_version=6
to_version=7
proposer_ref=ops-17
reviewer_ref=security-42
mfa_step_up_validated=true
trust_material_reviewed=true
metadata_hash_ref=sha256:...
decision=ACTIVATE
result=SUCCESS
correlation_id=change-17
~~~

This is an illustrative audit schema; protect audits from unauthorized deletion/modification, enforce view permissions, data minimization, and retention. **Auditing does not replace preventive controls.**

## 15. Incident Response Plan When Keys or Trust Are Compromised

### 15.1. Unexpected new IdP signing certificate

1. Verify signed metadata and fingerprint via an approved channel; never auto-trust a new URL.
2. Stage the version; retain current trusted certs if uncompromised and policy permits.
3. Confirm rotation timeline and overlapping verification window with the partner.
4. Run canary real SAML login, wrong-audience, and replay tests.
5. If a cert was leaked or changed without authorization, **revoke trust** rather than merely adding the new cert to an allowlist.
6. Report potentially affected logins/account changes.

### 15.2. OIDC client secret leak

- Revoke/rotate at the Authorization Server, update the reference in the secret store, and deploy.
- Hunt for leaks in Git, pipeline logs, CI artifacts, config snapshots, and tickets.
- Inspect anomalous token-endpoint/refresh-token usage and bound overlap.
- Changing a client secret does not automatically invalidate issued access tokens: run token/session revocation per architecture.
- Add policies preventing secrets from entering logs/source after the incident.

### 15.3. Kerberos keytab leak

- Isolate the affected workload/host, identifying SPN, account, and environment.
- Rotate the service account key in KDC/AD and update keytab/KVNO across pods.
- Monitor SPN mismatches and failover; never “roll back” to a compromised keytab.
- Evaluate active web sessions and Kerberos tickets per lifetime/revocation rules.
- Purge copies of the keytab from images/logs/backups per incident playbook.

### 15.4. Admin API compromise

- Freeze/disable modified partners and lock related admin credentials/automation tokens.
- Diff issuer, metadata URL, verification certs, JWT algorithms, role mappings, and ACS/redirect endpoints.
- Roll back only to an **approved, uncompromised** version, or fail closed if none exists.
- Audit actor/reviewer/step-up/canary records; investigate accounts, permissions, and sessions created during the compromise window.
- Inspect backend egress and error logs for SSRF/secret reads.

## 16. Runnable Java 17: Simulating Callback Trust and Dual Approval

The standalone program below uses neither Spring nor networking. It simulates **security conditions already confirmed by a real verifier** and config governance logic. **Never** accept booleans like `signatureVerified`, `issuerTrusted`, or `stepUpVerified` from request JSON in production.

File **`FederationBoundaryDemo.java`**:

~~~java
import java.net.URI;

public final class FederationBoundaryDemo {

    record Callback(
        String protocol,
        boolean issuerTrusted,
        boolean correlationValid,
        boolean cryptoValid,
        boolean audienceValid,
        boolean replaySeen) {}

    static String verifyCallback(Callback c) {
        if (!c.issuerTrusted()) return "DENY_ISSUER";
        if (!c.correlationValid()) return "DENY_CORRELATION";
        if (!c.cryptoValid()) return "DENY_CRYPTO";
        if (!c.audienceValid()) return "DENY_AUDIENCE";
        if (c.replaySeen()) return "DENY_REPLAY";
        return "ACCEPT_" + c.protocol();
    }

    record Change(
        boolean operatorAuthorized,
        boolean recentMfaVerified,
        String proposer,
        String reviewer,
        String metadataUrl,
        boolean trustReviewed) {}

    // Demonstration of preliminary URI policy, NOT SSRF protection.
    static boolean approvedMetadataUrl(String value) {
        try {
            URI uri = URI.create(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                && "idp.partner.example".equalsIgnoreCase(uri.getHost())
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getPort() == -1
                && "/metadata".equals(uri.getRawPath());
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    static String review(Change change) {
        if (!change.operatorAuthorized()) return "DENY_ADMIN_RBAC";
        if (!change.recentMfaVerified()) return "DENY_STEP_UP";
        if (change.proposer().equals(change.reviewer()))
            return "DENY_SELF_APPROVAL";
        if (!approvedMetadataUrl(change.metadataUrl()))
            return "DENY_METADATA_URL";
        if (!change.trustReviewed()) return "DENY_KEY_REVIEW";
        return "APPROVED_DRAFT";
    }

    static final class ConfigRegistry {
        private long version = 1;

        synchronized String activate(long expectedVersion, String approval) {
            if (version != expectedVersion) return "DENY_VERSION_CONFLICT";
            if (!"APPROVED_DRAFT".equals(approval))
                return "DENY_UNAPPROVED";
            version++;
            return "ACTIVE_VERSION_" + version;
        }

        synchronized long version() { return version; }
    }

    public static void main(String[] args) {
        System.out.println("OIDC_OK=" + verifyCallback(
            new Callback("OIDC", true, true, true, true, false)));
        System.out.println("OIDC_STATE=" + verifyCallback(
            new Callback("OIDC", true, false, true, true, false)));
        System.out.println("SAML_SIGNATURE=" + verifyCallback(
            new Callback("SAML", true, true, false, true, false)));
        System.out.println("SAML_REPLAY=" + verifyCallback(
            new Callback("SAML", true, true, true, true, true)));
        System.out.println("CAS_UNTRUSTED=" + verifyCallback(
            new Callback("CAS", false, true, true, true, false)));

        Change approved = new Change(true, true, "ops-a", "security-b",
            "https://idp.partner.example/metadata", true);

        System.out.println("NO_MFA=" + review(new Change(
            true, false, "ops-a", "security-b",
            "https://idp.partner.example/metadata", true)));
        System.out.println("SELF_REVIEW=" + review(new Change(
            true, true, "ops-a", "ops-a",
            "https://idp.partner.example/metadata", true)));
        System.out.println("BAD_URL=" + review(new Change(
            true, true, "ops-a", "security-b",
            "http://127.0.0.1/metadata", true)));
        System.out.println("BAD_KEY=" + review(new Change(
            true, true, "ops-a", "security-b",
            "https://idp.partner.example/metadata", false)));

        String result = review(approved);
        System.out.println("REVIEW=" + result);
        ConfigRegistry registry = new ConfigRegistry();
        System.out.println("ACTIVATE=" + registry.activate(1, result));
        System.out.println("STALE=" + registry.activate(1, result));
        System.out.println("VERSION=" + registry.version());
    }
}
~~~

Compile/run:

~~~bash
javac FederationBoundaryDemo.java
java FederationBoundaryDemo
~~~

**Exact stdout:**

~~~text
OIDC_OK=ACCEPT_OIDC
OIDC_STATE=DENY_CORRELATION
SAML_SIGNATURE=DENY_CRYPTO
SAML_REPLAY=DENY_REPLAY
CAS_UNTRUSTED=DENY_ISSUER
NO_MFA=DENY_STEP_UP
SELF_REVIEW=DENY_SELF_APPROVAL
BAD_URL=DENY_METADATA_URL
BAD_KEY=DENY_KEY_REVIEW
REVIEW=APPROVED_DRAFT
ACTIVATE=ACTIVE_VERSION_2
STALE=DENY_VERSION_CONFLICT
VERSION=2
~~~

Explanation: requests lacking issuer trust, state correlation, cryptographic proof, or anti-replay fail authentication; config changes lacking MFA/independent approval/permitted metadata URI or key review cannot be approved; config version increments only after approval, and a second activation request with the old `expectedVersion` is rejected.

**Limitations:** the demo does not verify real JWT/SAML/CAS/Kerberos, and has no TLS/mTLS, signed metadata, DNS/SSRF, database, MFA service, or multi-node transactions. Boolean fields are simulated verifier outputs. `approvedMetadataUrl` does not defend against DNS rebinding/redirects/private IPs; production must protect network egress/HTTP clients and trust material. `synchronized` applies only within one JVM; production needs DB version locks/CAS and atomic publishing. `DENY_ISSUER` for CAS models general source trust; real CAS callbacks rely on server-to-server CAS channels rather than an OIDC issuer claim.

## 17. Security Test Matrix

| Area | Scenario | Expected |
| --- | --- | --- |
| OIDC | Callback missing/wrong state. | Do not log in. |
| OIDC | Authorization code from issuer A sent to issuer B callback. | Reject mix-up. |
| OIDC | ID Token wrong signature/issuer/audience/expiry/nonce. | Reject, create no local session. |
| OIDC | Replayed code or wrong PKCE verifier. | Reject. |
| OIDC | Open redirect via `next=https://evil.example`. | Do not redirect credentials to external domain. |
| SAML | Unsigned/modified SAMLResponse. | Reject. |
| SAML | Wrong AudienceRestriction/Destination/Recipient. | Reject. |
| SAML | Replayed assertion across two pods. | Atomic shared replay store rejects. |
| SAML | Missing InResponseTo when required by policy. | Reject. |
| SAML | Malicious RelayState open redirect. | Reject/allow only safe destination. |
| SAML | XML with DOCTYPE/XXE/oversized body. | Reject safely, resource limits. |
| SAML | Metadata carries new unapproved cert. | Stage only, never auto-trust. |
| CAS | ST used for wrong service or already validated. | Reject. |
| CAS PGT | Fake receptor callback from browser. | Blocked by trust boundary. |
| CAS PGT | Node A receives PGT, Node B validates ST. | Shared IOU→PGT mapping works properly. |
| CAS SLO | Forged logoutRequest using victim's username. | Do not destroy by username. |
| Kerberos | Wrong SPN/KVNO/enctype. | GSS fails, do not accept identity. |
| Kerberos | Keytab leaked in image/CI logs. | Security QA FAIL, rotate/revoke. |
| Keys | SAML private key published in metadata. | Security QA FAIL. |
| JWKS | JWT `kid`/`alg` outside approved keys/policy. | Reject. |
| Management | Viewer calls POST activate. | 403/deny. |
| Management | Proposer self-approves. | Deny dual control. |
| Management | Actor lacks fresh MFA. | Deny high-risk change. |
| Management | Admin modifies another tenant's issuer/cert. | Deny tenant ownership. |
| Management | Metadata URL is loopback/link-local/private. | Egress/URL checks block. |
| Management | DNS rebinding or redirect to internal IP. | Block, never connect internally. |
| Management | Concurrent activate using stale version. | Revision conflict, no partial publish. |
| Management | Rollback to compromised config. | Deny/disable, never re-enable bad key. |
| Management | Admin CSRF POST without token. | Reject, even though SAML ACS has its own exemption. |
| Secrets | Vault unavailable. | Fail safely; no hardcoded fallback. |
| Logging | Gateway logs contain `pgtId`/OIDC code. | QA FAIL, redact + incident review. |
| Runtime | Callback during key rotation/multi-node. | Only approved trust versions, consistent session correlation. |

Tests in this table must run **on staging** with test IdPs/KDCs, private networks, dummy credentials, and rollback plans. **Happy-path login success does not prove hardening.**

## 18. Symptom-Based Troubleshooting

| Symptom | Root cause | Investigation path |
| --- | --- | --- |
| OIDC callback gets state mismatch after scale-out. | Out-of-sync state/session cookie, wrong SameSite/ingress. | Authorization request repository, cookies, proxy. |
| OIDC login fails after changing issuer. | Mismatched client registration/issuer/JWKS. | Config version, issuer/audience; never drop checks. |
| SAML ACS POST returns 403. | Wrong CSRF matcher or route/WAF. | Narrow ACS exemption, keep OpenSAML filters. |
| SAML signature fails after rotation. | Cert unapproved or nodes unrefreshed. | Check trust anchor, overlap, issuer, cache. |
| SAML replay accepted on another node. | Pod-local replay cache. | Shared atomic replay store/TTL. |
| CAS PGT IOU lookup miss. | Unreachable receptor, non-shared store, ACK before persist. | TLS, inbound trust, mapping store. |
| CAS SLO logs out wrong device. | Deleting by username instead of ticket→session. | Fix session correlation. |
| Kerberos `KRB_AP_ERR_MODIFIED`. | SPN/account/KVNO/keytab mismatch. | AD/KDC, keytab distribution/rotation. |
| User still enters after IdP logout. | Local session/API token lives independently. | Revocation/session TTL; never confuse login with logout. |
| Admin can self-approve config. | Checked only ROLE_ADMIN, missing dual control. | Approval state machine, reviewer identity. |
| Metadata fetch hits cloud metadata. | SSRF redirects/DNS bypass. | Egress isolation, no redirects, IP checks. |
| IdP metadata auto-swaps signing cert. | Auto-trust without signer/approval. | Disable auto activation, pin trust material. |
| Secret appears in actuator or logs. | Missing runtime/ingress redaction. | Containment, rotation, remove exposure. |
| Two pods validate SAML differently. | Out-of-sync trust version/rotation. | Versioned registry, canary, atomic publish. |
| Rollback restores login yet old key was leaked. | Insecure rollback. | Emergency disable, issue safe new key. |

**Read logs via reason codes, not raw tokens.** Trace from callback matcher → protocol verification → issuer/cert/JWKS/key version → state/replay cache → active config version → local account authorization; for the admin plane also inspect MFA, RBAC, approval, egress, and audits.

## 19. Common Pitfalls

1. **“Callbacks are public so drop all Spring Security.”** Wrong: local Authentication is not needed yet, but protocol verifiers must run.
2. **“SAML POST is a direct server call from the IdP.”** Usually a browser POST; signature/trust prove origin.
3. **“HTTPS replaces SAML signatures.”** Wrong: client→SP TLS does not verify the XML issuer.
4. **“An OIDC code means the user is logged in.”** Wrong: state/PKCE/token validation remain required.
5. **“`registrationId` in the callback can pick any issuer.”** Wrong: look up only approved registrations.
6. **“JWT `kid` can fetch JWKS from a URL in the token.”** Wrong: must use approved issuer/JWKS.
7. **“IdP public cert can be replaced by the SP's private key.”** Wrong: different owners and roles.
8. **“SAML encrypted assertions do not need signatures.”** Wrong: encryption is not identity proof.
9. **“CAS PGT receptor has a browser session.”** Wrong: normally a server-to-server CAS callback.
10. **“Signatures in CAS SLO match SAML2 SLO.”** Not by default; depends on protocol/trust.
11. **“Rotating the TLS cert rotates the SAML signing cert.”** Wrong when they are two separate key roles.
12. **“A keytab is just a username.”** Contains long-term service secret keys.
13. **“K8s Secrets use Base64 so private keys are safe.”** Wrong: etcd/RBAC/mounts/backups matter.
14. **“Logged-in admins should be able to add issuers themselves.”** Wrong: requires scope, MFA, and approval.
15. **“SAML metadata over HTTPS is automatically trustworthy.”** Wrong: trust bootstrap/signer/approval are required.
16. **“Blocking localhost URLs stops all SSRF.”** Wrong: DNS rebinding, redirects, private IPv6, and egress.
17. **“If ACS is CSRF-exempt, admin POST is exempt too.”** Wrong: different trust boundaries.
18. **“Deleting the old cert immediately upon rotation is safe.”** Can break in-flight tokens; use overlap unless compromised.
19. **“Roll back to a compromised key to restore login.”** Wrong: must revoke, never re-enable.
20. **“HTTP 200 on callback proves local Authentication/Logout succeeded.”** Wrong: verify state/readback.
21. **“A single-pod replay cache suffices for multi-node.”** Wrong when other nodes lack shared state.
22. **“With ROLE_ADMIN, changing role mappings needs no tenant check.”** Wrong: enforce tenant scope/dual control.
23. **“With a secret manager, logs cannot leak tokens.”** Wrong: ingress/APM/apps may capture raw payloads.
24. **“Valid JWT signature with wrong audience still allows login.”** Wrong: validation must verify full token semantics.

## 20. Acceptance Checklist

1. Inventory all OIDC/SAML/CAS callbacks, methods, hostnames, proxy routes, and service registrations.
2. OIDC enforces state, nonce, PKCE, exact redirect/issuer/audience/signature/expiry, and mix-up defenses.
3. SAML enforces trusted signing certs, issuer/destination/recipient/audience/Conditions/SubjectConfirmation/InResponseTo/replay.
4. SAML ACS POST passes through the OpenSAML provider; narrow CSRF exemption, never open admin plane.
5. CAS ST callback validates service binding/one-time; PGT receptor enforces inbound trust, IOU store, and log redaction.
6. CAS SLO enforces source trust and exact ticket→local session mapping.
7. OIDC client secrets, SAML SP signing/decryption keys, TLS keys, and Kerberos keytabs reside in RBAC-protected secret management.
8. JWKS `kid/alg` select only approved issuer keys; never auto-trust arbitrary `jku`.
9. Kerberos SPN, keytab KVNO/enctype/realm tested across multiple nodes.
10. Public metadata exports only public material; admin edit APIs are non-public and leak no secrets.
11. Admin plane enforces tenant-scoped RBAC, MFA step-up, dual approval, CSRF, method restrictions, and audits.
12. Metadata fetcher blocks SSRF/DNS rebinding/redirects/private IPv4/IPv6, XXE, DoS, and trust swaps.
13. Configs are versioned immutable, atomically activated/rolled back, never re-enabling compromised material.
14. Rotation has approved overlap, canary/login tests, and an emergency revocation plan.
15. Runtime state/replay/nonce/PGT mappings are consistent and fail closed on store errors.
16. Ingress/APM/logging all redact credentials, not just application logs.
17. Audit secret reads, key rotations, config reviews/activations, rejected callbacks, and tenant ownership.
18. Adversarial QA tests exact boundaries and runs periodic incident exercises.

## 21. Self-Check Knowledge Questions

1. **OIDC callbacks may lack a prior local session—why are they still safe?** — Because Spring verifies state/PKCE/nonce/issuer/tokens before creating Authentication.
2. **What authenticates a SAMLResponse?** — Trusted IdP XML signature plus issuer/audience/recipient/time/correlation conditions.
3. **Is HTTPS metadata automatically a trust anchor?** — No; an approved signer/cert or verified channel and approval are required.
4. **How do `pgtId` and `pgtIou` differ in CAS?** — PGT is the credential; IOU is the key correlating the callback with the trusted validation response.
5. **Why does the CAS PGT receptor need inbound trust?** — The receptor's TLS certificate used when CAS delivers PGT does not authenticate who is calling the receptor.
6. **What is a keytab for?** — Holds Kerberos service keys to accept tickets for the right SPN/realm.
7. **Are the TLS key and SAML SP signing private key the same?** — Not necessarily; govern their roles separately.
8. **Does JWKS `kid` establish new trust?** — No; it only selects a key from trusted issuer keys.
9. **Why require dual approval for changing an issuer?** — Because changing issuer/cert changes the trust boundary itself and can lead to account takeover.
10. **Does a host allowlist block all SSRF?** — No; DNS, redirects, egress, and private IPs must also be controlled.
11. **Should admin POSTs be CSRF-exempt like SAML ACS?** — No; admins use browser sessions and require CSRF.
12. **Why is rolling back to a compromised key dangerous?** — It reactivates an unsafe secret/trust anchor.
13. **After rotating a signing key, can the old verification key be deleted immediately?** — Depends on token/assertion lifetimes, overlap, and compromise risk.
14. **Is a replay cache inside one pod enough?** — No, if callbacks can hit other nodes.
15. **What acceptance criteria prove sound hardening?** — Forged callbacks/wrong issuers/replays/SSRF/admin self-approval/secret exposure are all rejected alongside working happy-path login.

## References

- [Spring Security — OAuth2 Login Advanced Configuration, Redirection Endpoint](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Authorization Grants and PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0 — Issuer, Audience, Nonce and ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — SAML2 Login Overview, ACS/OpenSAML Validation](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML2 Response Authentication and Decryption](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Metadata Signature Verification](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — Servlet CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Authorizing HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security Kerberos — Project Source](https://github.com/spring-projects/spring-security-kerberos)
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SSRF_Prevention_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [RFC 4120 — Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120.html)
