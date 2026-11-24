# Translating SAML to OIDC at a Broker System and Each Party's Responsibilities

> **Module:** Spring Security – federation. **Group:** OIDC and Brokering. This lesson describes the **upstream SAML IdP → Identity Broker → downstream OIDC Relying Party (RP)** model. Each leg has distinct trust boundaries, signatures, audiences, sessions, and responsibilities. Examples use **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x** on the OIDC client side; broker configuration is explained using product models such as Keycloak. Enabling both `saml2Login()` and `oauth2Login()` in the same Spring Security application **does not automatically turn the application into an OpenID Provider (OP)**.

## 1. Learning Objectives and Prerequisites

After this lesson, learners can:

1. Distinguish the roles: **Corporate SAML IdP**, **Broker as SAML SP**, **Broker as OIDC OP/Authorization Server**, **OIDC RP**, and **OAuth2 Resource Server**.
2. Explain SAML→OIDC as a process of **verify upstream identity → account linking → issue new OIDC authentication**—not "convert XML to JSON" or "wrap a SAML assertion inside a JWT".
3. Trace the OIDC Authorization Code flow from the RP, into the SAML AuthnRequest, SAMLResponse verification at the broker, authorization code issuance, code exchange for an ID Token, and RP token validation.
4. Show how **SAML Issuer and Audience** differ from **OIDC `iss` and `aud`**; understand who holds which private key and who trusts which party's public certificate/JWKS.
5. Design policies mapping `NameID`/attributes/`AuthnContext`/`AuthnInstant` to external identity links, broker users, `sub`, `email`, `email_verified`, `auth_time`, `acr`, and `amr` without inflating trust.
6. Understand how `state`, `nonce`, PKCE, `InResponseTo`, `RelayState`, and broker sessions protect separate transactions.
7. Distinguish ID Tokens, Access Tokens, and Refresh Tokens; enforce exact issuer, audience, and API/tenant access permissions.
8. Configure a Spring Boot application as an **OIDC RP** trusting the broker; run a Java 17 identity-linking example and verify exact output.
9. Design negative tests, auditing, key rotation, logout, session revocation, and IdP/tenant onboarding/offboarding.
10. Explain **each party's responsibility** on login failures without mixing SAML trust into OIDC token validation.

Prerequisites: SAML Web Browser SSO, IdP/SP metadata, `RelyingPartyRegistration`, `SAMLResponse`/`AuthnRequest`/`Assertion`, XML signatures; OAuth2 Authorization Code, OIDC Discovery, JWS/JWK; HTTP redirects/POST, TLS, cookies, and Spring Security `SecurityFilterChain`.

## 2. Overall Architecture: The Broker Plays Two Protocol Roles

A company has a Corporate IdP emitting **SAML 2.0**, while a modern Portal supports **OpenID Connect**. To avoid making the Portal a SAML SP itself, we introduce a broker.

~~~text
                   User's browser
                         |
                         | OIDC /authorize
                         v
               Portal Web (OIDC RP)
               client_id = portal-web
                         |
                         v
          +------------------------------------+
          |       Identity Broker              |
          |                                    |
          |  Downstream side: OIDC OP          |
          |  issuer=https://broker.example.org |
          |  /authorize /token /jwks /userinfo |
          |  client registry, OP session       |
          |  signs ID Token with BROKER key    |
          |                                    |
          |  Upstream side: SAML SP            |
          |  entityID=urn:broker:saml:sp       |
          |  ACS=/saml/acs/corporate           |
          |  trusts SAML IdP public cert       |
          |  receives + validates SAMLResponse |
          |                                    |
          |  Identity mapping / Account link   |
          +------------------------------------+
                         |
                         | SAML AuthnRequest
                         v
               Corporate SAML IdP
               - checks account/MFA
               - signs SAML Assertion
               - emits NameID/Attributes
~~~

The **Broker SP** is the "SAML customer" of the Corporate IdP. The **Broker OP** is the "OIDC identity provider" of the Portal. One software component can perform both roles, yet **they remain two independent trust contracts**.

### Naming and Data-Flow Table

| Name | In This Example | Role |
| --- | --- | --- |
| Upstream SAML IdP | `https://idp.corp.example.org/saml` | Authenticates users and emits signed Assertions |
| Broker SAML SP entity ID | `urn:broker:saml:sp` | Entity permitted to consume the SAML assertion |
| Broker ACS | `https://broker.example.org/saml/acs/corporate` | Callback receiving `SAMLResponse` from the upstream IdP |
| Broker OIDC issuer | `https://broker.example.org/realms/workforce` | `iss` value in OIDC ID Tokens issued by the broker |
| Downstream RP | Portal Web | Signs in via OIDC code flow and verifies broker tokens |
| OIDC client ID | `portal-web` | Expected `aud` value in Portal ID Tokens |
| RP redirect URI | `https://portal.example.org/login/oauth2/code/broker` | Callback carrying the OIDC authorization code |
| Resource Server | Reports API | Verifies **Access Tokens** scoped to the API; never uses raw `SAMLResponse` |

These URLs and IDs are illustrative only. In production, obtain them from admin-approved metadata and registrations.

## 3. Who Is Responsible for Which Step?

| Actor | Receives Message | Must Verify | Owns Keys and Data |
| --- | --- | --- | --- |
| **Corporate SAML IdP** | SAML `AuthnRequest` from broker | SP entityID, ACS, request signature per policy, session/user/assurance | IdP holds **SAML signing private key**, signs Response/Assertion, and emits contracted stable identifiers |
| **Broker as SAML SP** | `SAMLResponse` via browser | IdP signature, Issuer, Audience broker SP, Destination/Recipient broker ACS, Conditions/time, `InResponseTo`/replay | Broker trusts IdP public signing cert from metadata; holds SP signing/decryption private keys if needed |
| **Broker identity layer** | Verified upstream identity | Entity ID + NameID/format/qualifiers, tenant, account status, external link, claims/assurance policy | Manages broker local user ID, account links, session, and claim mapper |
| **Broker as OIDC OP** | OIDC `/authorize`, `/token`, and client requests | Registered client, exact redirect URI, code+PKCE, client auth, scopes, consent, session, nonce | Holds **OIDC token signing private key**, issues ID/Access Tokens, publishes JWKS |
| **Portal OIDC RP** | Authorization response + broker ID Token | `state`, token `issuer=broker`, signature via broker JWKS, `aud=Portal client_id`, nonce, expiry, required claims | Creates Portal HTTP session; checks Portal user/tenant/roles |
| **Reports API** | Access Token sent by client | Token issuer, signature/introspection, `audience=API`, scopes, expiry, tenant/resource entitlements | Enforces API authorization; never uses ID Token as access token |

**Trust relationships are not automatically transitive.** The Portal may trust the Broker OP for authentication, yet the Portal **does not** thereby trust any SAML IdP the broker happens to connect to; the broker must restrict upstream providers and validate them. Nor does the broker trusting an IdP's SAML Assertion signature mean arbitrary SAML Attributes grant admin roles in the Portal.

### Signatures on the Two Legs Differ

~~~text
Corporate IdP private key
    └─ signs SAML Response/Assertion
        └─ Broker verifies with IdP public cert (SAML metadata)

Broker OIDC private signing key
    └─ signs ID Token (JWS)
        └─ Portal verifies with Broker public JWKS (OIDC Discovery)

Broker SP signing private key (if any)
    └─ signs SAML AuthnRequest sent to IdP
        └─ IdP verifies with Broker SP public certificate
~~~

**Never give the IdP's private signing key to the broker or Portal just to verify SAML.** The broker uses the IdP's **public** certificate. Never publish private broker keys in JWKS; JWKS contains only public key material. A broker-signed ID Token must carry **`iss=broker issuer`**, not the SAML IdP's issuer.

## 4. End-to-End Flow: OIDC Code Flow and SAML Web Browser SSO

Follow these 14 steps, where the browser transports requests and responses yet is **never a trust anchor**.

1. User opens `https://portal.example.org/private`; Portal has no local session yet.
2. Portal builds an OIDC authorization request to the Broker OP: `response_type=code`, `client_id=portal-web`, registered `redirect_uri`, `scope=openid profile`, random `state` and `nonce`, plus PKCE `code_challenge` if policy requires. Portal saves the pending request/`nonce`/`code_verifier` bound to the browser session.
3. Broker checks the registered OIDC client, exact redirect URI, and allowed scopes, and checks whether a valid OP session already exists.
4. If no identity exists yet, the broker selects an **approved SAML IdP** via tenant/domain/policy. Never accept arbitrary metadata/IdP URLs from query parameters.
5. Broker (now acting as SAML SP) creates an `AuthnRequest` with a unique ID, SP entityID, and ACS, and saves the request context in its repository. Signs the `AuthnRequest` if required by the IdP.
6. Browser is redirected/POSTed to the Corporate SAML IdP; the IdP authenticates the user/MFA, validates the request, and emits a validly signed `SAMLResponse`/Assertion.
7. Browser POSTs `SAMLResponse` to the **Broker ACS**. Broker verifies the signature with the trusted IdP cert, Issuer, `Audience=Broker SP entityID`, `Recipient/Destination=Broker ACS`, timestamps, `SubjectConfirmation`, `InResponseTo`, and replay.
8. Broker extracts NameID/Attributes/AuthnContext **only after validation**; it looks up `ExternalIdentityLink`, tenant policy, disabled user status, and first-broker-login/account verification.
9. Broker creates/restores the broker-local identity and OP session. Broker records authentication source/assurance and session mapping per policy, never using SAML `SessionIndex` as the OIDC subject.
10. Broker returns to the **pending OIDC transaction**, verifies client/redirect/nonce/PKCE context, and issues a single-use authorization code.
11. Browser is redirected to the registered Portal `redirect_uri` with `code` and `state`.
12. Portal verifies `state`; backend sends `code`, redirect URI, client authentication, and PKCE `code_verifier` to the Broker Token Endpoint.
13. Broker checks unused code/TTL/client/redirect/verifier and issues a **new ID Token** with `iss=broker`, `aud=portal-web`, `sub=broker-issued subject`, `iat`/`exp`, and matching `nonce`; optionally issues Access/Refresh Tokens per client policy.
14. Portal validates the ID Token via broker Discovery/JWKS and establishes a local session; when calling APIs, it uses only an Access Token issued with the API's audience/scopes and enforces business permissions.

~~~text
Browser         Portal (OIDC RP)          Broker (OIDC OP+SAML SP)         SAML IdP
   |                    |                            |                       |
   | GET /private       |                            |                       |
   |------------------->|                            |                       |
   | 302 /authorize?code,state,nonce,PKCE            |                       |
   |<-------------------|                            |                       |
   |------------------------------------------------>|                       |
   |                    |                 AuthnRequest ID=_req1             |
   |                    |                            |---------------------->|
   |<------------------------------------------------------------browser-----|
   |              SAMLResponse signed, InResponseTo=_req1                 |
   |---------------------------------------------------------------> Broker ACS
   |                    |                    validate SAML <---------------|
   |                    |                    map identity / broker session |
   | 302 RP redirect_uri?code=_code1&state=_state1   |                       |
   |<------------------------------------------------|                       |
   |------------------->|                            |                       |
   |                    | POST /token(code,client,verifier)                  |
   |                    |--------------------------->|                       |
   |                    | signed broker ID Token + access token              |
   |                    |<---------------------------|                       |
   |                    | verify issuer/JWKS/aud/nonce/exp                   |
   | 200 /private       |                            |                       |
   |<-------------------|                            |                       |
~~~

This is a logical diagram, not an exact HTTP trace of a specific product. When the broker or IdP already holds an active session, some user-interaction steps may be skipped while preserving security and correlation policies.

### SAML Transaction Protections Differ from OIDC

| Parameter | Created By | Verified By | Purpose |
| --- | --- | --- | --- |
| SAML `AuthnRequest/@ID` | Broker SAML SP | Broker compares `Response/@InResponseTo` | Correlates SAML Response with transaction |
| SAML `RelayState` | Broker SAML SP/binding | Broker | Preserves flow state; not an OIDC nonce |
| OIDC `state` | Portal OIDC RP | Portal | Prevents CSRF/mix-up at OIDC callback |
| OIDC `nonce` | Portal RP | Portal compares against ID Token | Prevents token substitution/replay |
| OIDC `code_challenge` | Portal RP | Broker OP at code exchange | PKCE binding code to initiating client |
| OIDC `code_verifier` | Portal RP | Broker OP at `/token` | Proves possession of verifier |
| Authorization code | Broker OP | Broker OP at `/token` | Single-use grant bound to client, redirect, TTL |

**Never replace SAML `InResponseTo` with OIDC `state`, and never use `RelayState` as `nonce`.** The broker must track two separate pending transactions. For IdP-initiated SAML SSO without an `AuthnRequest`, risks include login CSRF and missing OIDC request context; decide explicitly whether unsolicited responses are permitted and never issue an OIDC token to an unregistered client or missing transaction.

## 5. Reading the SAML Assertion at the Broker

Partial SAML Response **for syntax learning only; unsigned and therefore unacceptable**:

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  Version="2.0" ID="_resp1"
  IssueInstant="2030-01-01T09:58:00Z"
  InResponseTo="_req1"
  Destination="https://broker.example.org/saml/acs/corporate">
  <saml:Issuer>https://idp.corp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assert1" Version="2.0"
                  IssueInstant="2030-01-01T09:58:00Z">
    <saml:Issuer>https://idp.corp.example.org/saml</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format=
        "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        external-person-100
      </saml:NameID>
      <saml:SubjectConfirmation Method=
        "urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_req1"
          Recipient="https://broker.example.org/saml/acs/corporate"
          NotOnOrAfter="2030-01-01T10:03:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-01-01T09:57:00Z"
        NotOnOrAfter="2030-01-01T10:03:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:broker:saml:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
      AuthnInstant="2030-01-01T09:55:00Z"
      SessionIndex="_saml-session1"/>
  </saml:Assertion>
</samlp:Response>
~~~

The sample omits `ds:Signature` and may omit other profile elements; **never use it as a live `SAMLResponse`**. The broker needs trusted metadata, the right signer, timestamps, subject, correlation, and replay handling.

- **SAML Issuer** = Corporate SAML IdP entity ID.
- **SAML Audience** = Broker SP entity ID, **not the Portal's `client_id`**.
- **SAML Destination/Recipient** = Broker ACS, **not the OIDC redirect URI**.
- **SAML InResponseTo** = `AuthnRequest` created by the broker.
- **NameID** = upstream subject per IdP, **not yet an OIDC `sub`**.
- **AuthnInstant** = timestamp when the IdP asserts authentication occurred; usable to derive `auth_time` after policy checks and mapping.
- **SessionIndex** = SAML IdP session linkage for profile logout; never use as broker OIDC subject or session ID.

### An Unverified SAML XML Signature Must Never Be Trusted

Browsers can submit arbitrary XML. The broker must verify using the IdP public signing certificate from **admin-approved metadata**, validate the exact signed element being consumed, and defend against XML Signature Wrapping, issuer spoofing, and encrypted-but-unsigned confusion. Successful Assertion decryption does not imply a valid signature. Never build a session with a hand-rolled string/regex XML parser.

## 6. The Broker-Issued OIDC ID Token

After SAML authentication and identity mapping pass, the Broker OP emits a token with **its own issuer, audience, lifetime, and signature**.

**Illustrative JSON payload only—no JWS header/signature, unusable for real login:**

~~~json
{
  "iss": "https://broker.example.org/realms/workforce",
  "sub": "broker-pairwise-subject-portal-42",
  "aud": "portal-web",
  "iat": 1893459900,
  "exp": 1893460500,
  "auth_time": 1893459300,
  "nonce": "oidc-nonce-from-portal",
  "acr": "urn:example:assurance:verified",
  "email": "person@example.org",
  "email_verified": true
}
~~~

**Never copy assurance values blindly:** `email_verified=true` and `acr` may only be emitted when broker policy has verified upstream evidence, not merely because upstream sent an email string or the IdP is named "corporate".

**Explanation of required/important values:**
- `iss` is the **Broker OIDC issuer** from Discovery and client config, not the SAML IdP entity ID.
- `sub` is the subject within the Broker OP's namespace; stable, never reassigned to someone else, and either public or pairwise per policy.
- `aud` is the Portal's OIDC `client_id`; the RP must verify it contains `portal-web` and enforce multi-audience/`azp` per OIDC rules.
- `iat` is when the broker issued the token; `exp` is token expiration. Not the SAML Assertion expiry.
- `auth_time` is when the user actually authenticated per evidence/policy; never default to "when the broker received the Response".
- `nonce` must match the nonce from the **Portal's OIDC authorization request** (if sent); SAML does not issue an OIDC nonce on the Portal's behalf.
- `email` is a profile claim per scope/policy; `email_verified` must never be inferred from an email's existence.
- `acr`/`amr` have no automatic 1-to-1 conversion from SAML `AuthnContextClassRef`.

### Which Key Signs the ID Token?

The **Broker OP** signs a fresh JWT with the broker's private signing key. The Portal verifies using public keys from `jwks_uri` in the **broker's approved OIDC Discovery**. A SAML XML Signature may remain in the upstream Response, yet cannot be "forwarded" as the JWT's signature; the two signatures have different scopes and audiences.

### What Must the OIDC RP Verify?

Per OIDC Core / Authorization Code:
1. `iss` matches the configured broker issuer exactly; never accept arbitrary issuers dictated by a token.
2. `aud` contains `client_id`; for multiple audiences/`azp`, enforce OIDC policy.
3. JWS signature/`alg` using keys from the trusted issuer's JWKS; never trust `jku`, `x5u`, or embedded JWKs to establish new trust.
4. Unexpired `exp`, sensible `iat`/clock skew.
5. `nonce`, if sent, matched by the RP against its pending nonce; authorization response `state` checked separately.
6. Authorization code exchange matches client, redirect URI, and PKCE verifier; single-use short-TTL code.
7. `acr`, `auth_time`, and `amr` semantically verified if the RP requires MFA/re-authentication.
8. When using UserInfo, returned `sub` must match ID Token `sub` per OIDC.
9. Post-authentication, the Portal must still verify account enabled status, tenant, and resource permissions: a valid ID Token **does not automatically grant all business rights**.

## 7. Translating SAML NameID into Broker Identity and OIDC sub

This is often the most critical logic layer in a broker. Two IdPs can emit the same NameID or email. If the broker auto-links accounts by email, an identity at IdP B could attach wrongly to IdP A's account.

### 7.1. Safe External Identity Key

~~~text
ExternalIdentityKey:
    trusted IdP entityID
    + NameID Format
    + NameID qualifiers/context if any
    + stable NameID value
         |
         v
  Approved IdentityLink store
    ExternalIdentityKey -> brokerInternalUserId
         |
    User active? Tenant allowed?
    Account link approved?
         |
         v
  Broker local session / subject
         |
  OIDC subject policy (public/pairwise)
         |
    sub issued to OIDC Client
~~~

Never use a transient `NameID` as a durable external identity key when no other stable identifier is guaranteed by the IdP contract. Emails can change or be reassigned; email **is not a security principal identifier** across IdPs. Identity links should record the trusted IdP source, source identifier, format, tenant/membership, and approval history.

### 7.2. First Broker Login and Account Linking

A sound workflow:
1. `SAMLResponse` is verified and the IdP is authorized for the tenant.
2. Look up the external identity link by **issuer + stable subject**, not email alone.
3. If linked: check user enabled status, tenant membership, and attribute update policy, then proceed.
4. If unlinked: enter a first-broker-login workflow with account verification, invitation/provisioning/approval, or account creation **strictly per explicit policy**; never attach to an existing account merely because emails match.
5. If two accounts share an email: never auto-merge; require proof of ownership or administrator approval.
6. When an IdP changes NameID format or a user moves tenants: run an audited migration procedure.
7. When a user is disabled/offboarded: revoke broker sessions, refresh tokens, and links per policy, and evaluate remaining token lifetimes.

Keycloak provides First Broker Login, identity provider mappers, and account linking; these features implement policy but do not replace security review. Keycloak documentation warns that enabling auto-linking of existing users by email in open setups can lead to account takeover.

### 7.3. Pairwise sub

A broker OP can emit **public** `sub` (same subject for a user across OIDC clients) or **pairwise** `sub` (subject varies per sector/client policy). Pairwise helps privacy when Portal and Payroll need not share the same identifier.

~~~text
Broker internal user: person-101

OIDC Client Portal:
  sub = pairwise-portal-7f0d

OIDC Client Payroll:
  sub = pairwise-payroll-5e31

=> Two OIDC clients cannot automatically infer this is the same person.
~~~

Never invent a naive `sub=SHA256(email)`; emails are guessable, mutable, and unsuitable for stability or privacy. Use an OP-supported subject generation policy and approved sector identifiers.

## 8. Claim Mapping: Never Inflate Trust

| Verified Upstream SAML | Mappable to OIDC? | Conditions and Risks |
| --- | --- | --- |
| IdP `Issuer` | **Never map to OIDC `iss`** | OIDC `iss` must be the Broker OP issuer; if upstream origin is needed, use a controlled internal audit/custom claim |
| `NameID` + format/context | Broker internal identity → OIDC `sub` | Requires stable link; avoid collisions and transient NameIDs |
| `mail` attribute | `email` | Minimize; honor client scopes/consent and source policy |
| Email verified under trusted contract | `email_verified` | True only with proof; presence of email never implies verified |
| `givenName`/`sn` | `given_name`/`family_name` | Versioned mapper, careful normalization, never as identity key |
| `AuthnInstant` | `auth_time` | Actual authentication time per IdP/broker policy, not token issuance time |
| `AuthnContextClassRef` | `acr` | Only with an agreed assurance-level mapping table |
| Trusted auth method/MFA assertion | `amr` | Never add `otp`/`mfa` unless upstream proves it |
| `SessionIndex` | Upstream session linkage inside broker | Never use as OIDC `sub` or `sid` |
| `AudienceRestriction` | Never map to OIDC `aud` | SAML audience is Broker SP only; OIDC `aud` is downstream client |
| SAML `NotOnOrAfter` | Never copy mechanically to OIDC `exp` | Assertion validity differs from ID Token lifetime |
| SAML `InResponseTo` | Never map to OIDC `nonce`/`state` | The two transactions have different creators and purposes |
| Group/role attributes | Client role claims (if approved) | Per-IdP/tenant allowlist; app/API still enforces authorization |

**Assurance spoofing:** An IdP emitting `AuthnContextClassRef=PasswordProtectedTransport` does not prove MFA. The broker must never emit `amr=["pwd","otp"]` just because the IdP's name contains "MFA". When the RP requests `max_age` or `prompt=login`, the broker must enforce `AuthnInstant`/re-authentication policies and matching upstream capabilities; if unprovable, never emit fabricated claims.

### MFA and Step-Up

When an RP requires higher assurance than the current broker session holds:
- Check `acr_values` or `claims` (if client/broker support them) and session age.
- Broker checks whether the upstream SAML IdP supports `ForceAuthn`/`RequestedAuthnContext` with a supported mechanism.
- If the IdP cannot furnish matching proof, the broker can run its own official OP step-up or **deny**—never fabricate `acr=high`.
- Write negative tests for downgrades (password-only when MFA is required), stale session replay, and false `auth_time`.

## 9. What Must the OIDC OP Do Beyond Signing JWTs?

To issue ID Tokens properly, the broker OP requires the **full OIDC/OAuth protocol**:

| Capability | Responsibility |
| --- | --- |
| Discovery `/.well-known/openid-configuration` | Publishes issuer, authorization endpoint, token endpoint, `jwks_uri`, supported metadata |
| Authorization Endpoint | Client ID, exact redirect URI, code flow, scopes, login session, state/nonce/PKCE requests |
| Token Endpoint | Single-use authorization code, TTL/client binding, redirect URI, PKCE verifier, client authentication |
| OP Signing/JWKS | Protected private signing key, public JWKS with right `kid`/alg, key rotation |
| Client Registration | Redirect/logout URI allowlists, client secrets/keys, allowed grants/scopes, consent |
| UserInfo (if used) | Returns claims per access token/consent; `sub` matches ID Token |
| OP Session | Tracks authenticated broker user, `auth_time`, re-authentication, logout, session TTL |
| Token Lifecycle | Access/Refresh Token expiry, refresh rotation/revocation, issuer/audience/scope |
| Security Events | Auditing, rate limiting, CSRF/replay defenses, trust config, key compromise handling |

Spring Security `oauth2Login()` only lets an application **log into an OIDC OP**; it **does not** expose `/authorize`, `/token`, or `jwks_uri` for other clients. If building an OP with Spring Authorization Server, configure those endpoints and wire the identity layer and SAML SP validated authentication into the authorization flow. Prefer an audited broker product unless architectural requirements mandate building one.

### OIDC Issuer and JWKS: Never Let Tokens Direct Key Fetching

The Portal's OIDC client has a configured, admin-approved `issuer-uri`. The RP uses OIDC Discovery to retrieve `jwks_uri` from that **trusted issuer**. It must never read `iss`/`jku` from an attacker's JWT and fetch arbitrary hosts "to see if the signature verifies". That creates SSRF and key-confusion vulnerabilities.

**OP keys** differ from the IdP's SAML signing keys. IdP rotation affects **broker upstream validation**, whereas OP signing/JWKS rotation affects **RP token validation**. Never collapse both lifecycles into a single "federation certificate" state.

## 10. ID Token, Access Token, and Refresh Token

The OIDC RP uses the **ID Token** to know the user was authenticated by the broker; an OAuth2 Resource Server/API uses the **Access Token** to decide whether a request may access resources. A Refresh Token, if issued, obtains new tokens per scope/session policy.

~~~text
Broker OP
  |
  +-- ID Token: iss=broker, aud=portal-web
  |       -> Portal OIDC RP validates for user login
  |
  +-- Access Token: aud=reports-api, scope=reports.read
  |       -> Reports API validates for data access
  |
  +-- Refresh Token (if allowed)
          -> Portal confidential backend keeps secret,
             OP enforces rotation/revocation/session policy
~~~

**Wrong:** sending an ID Token with `aud=portal-web` as a Bearer Access Token to `reports-api` because the signature happens to be valid. The API must reject mismatched audience/purpose. The broker must define clear resource audiences and scopes, the RP must send only the right token, and the API must enforce permissions on user/tenant/resource.

### Spring Boot Resource Server on a Separate API

Example **Reports API** configuration (not the Portal) when the API token is a JWT and the Spring Boot version supports `audiences`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://broker.example.org/realms/workforce
          audiences:
            - reports-api
~~~

The API must also check scopes/authorities and tenant/resource ownership. If access tokens are opaque, use introspection instead of a JWT decoder. Not every broker access token is a JWT; never try decoding an opaque token as JSON.

## 11. Keycloak Identity Brokering: Each Party's Setup

A reference setup using Keycloak as the broker. Admin Console menu names and options vary by version; follow your target system's documentation. The steps below are **configuration decisions**, not commands executed here.

### 11.1. Registering the Upstream SAML IdP

1. Decide the realm/tenant and the broker's public HTTPS hostname/issuer.
2. Add the SAML identity provider in the broker using approved metadata/sources; verify entity ID, `SingleSignOnService`, certificate rollover, and bindings.
3. Register the broker as a **SAML SP** at the Corporate IdP: broker SP entity ID, ACS, and public signing/encryption certificates if required.
4. Configure whether signed Response/Assertion, signed `AuthnRequest`, encrypted Assertion, and specific NameID formats are required.
5. Test SP-initiated login; verify SAML signature, issuer, audience, destination/recipient, timestamps, `SubjectConfirmation`, and `InResponseTo`/replay.
6. Configure First Broker Login: user creation/linking, duplicate emails, tenant membership, disabled/locked accounts, and multi-IdP policies.
7. Build claim mappers with allowlists, default-deny for admin roles, and account verification; never trust `email_verified` blindly.
8. Review `SessionIndex`/`LogoutRequest` support, `AuthnInstant`/`AuthnContext` assurance mapping, and SAML SLO.
9. Prepare playbooks for key rotation, IdP outages, user offboarding, and account-linking incidents.

### 11.2. Registering the Downstream OIDC Client

1. Create OIDC client `portal-web` as a confidential web client if the backend protects the client secret, or public+PKCE per your architecture.
2. Declare the **exact redirect URI** `https://portal.example.org/login/oauth2/code/broker` and approved post-logout redirect URIs; never enable broad wildcards.
3. Enable Authorization Code, client authentication/PKCE policy, and allowed scopes (e.g., `openid`, `profile`).
4. Issue only required claims/roles via mappers/client scopes; never dump every SAML assertion/attribute to every client.
5. Verify broker Discovery issuer, JWKS, ID Token `aud=portal-web`, and `sub` policy.
6. Verify OIDC session timeouts, token TTLs, refresh rotation/revocation, and logout; determine whether upstream SAML SLO is wired in.
7. Run negative tests with wrong redirects, wrong clients, unlinked identities, duplicate emails across IdPs, and MFA/assurance mismatches.

**Important:** When a client uses a Keycloak OIDC token, it sees the **Keycloak broker issuer**, not the SAML IdP as the OP issuer. Keycloak may record upstream provider aliases/identities in session notes or custom claims per policy, yet that does not alter `iss`.

## 12. Spring Boot 3.5 + Java 17: Portal as OIDC Relying Party

The sample below lets the Portal log in via an **already-configured** broker using Spring Security OAuth2 Client. It processes no SAML Responses; the broker handles the SAML SP side. This Maven app compiles with JDK 17 and dependencies, yet requires a real broker and registered OIDC client to run logins.

### Structure

~~~text
oidc-broker-client/
├── pom.xml
└── src/main/
    ├── java/demo/OidcBrokerClientApplication.java
    └── resources/application.yml
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>oidc-broker-client</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Do not add a SAML SP library merely because upstream uses SAML.** The RP speaks only OIDC with the broker. Conversely, if building the broker itself in Spring, it needs both upstream SAML SP and downstream OP/token-issuance infrastructure; `oauth2Login` on the Portal does not issue ID Tokens for other clients.

### src/main/resources/application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${BROKER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: https://broker.example.org/realms/workforce
~~~

**Meaning:**

- `spring.security.oauth2.client.provider.broker.issuer-uri` is the **fixed issuer of the broker OP**, not the SAML IdP entity ID.
- `client-id=portal-web` is pre-registered at the broker; the OIDC ID Token `aud` must contain this value.
- `client-secret` is read from `BROKER_CLIENT_SECRET` / secret store; never hardcode production secrets in Git or frontend code.
- `scope` includes `openid` for OIDC; `email`/`profile` are requests only and do not guarantee the broker emits every claim.
- `redirect-uri` must match the exact client registration at the broker; localhost demos apply only when allowed by the broker sandbox.
- `{baseUrl}` depends on scheme/host behind proxies; public HTTPS deployments require trusted forwarded headers to prevent Host-header poisoning.
- State/nonce have specific roles in OIDC login; **PKCE is recommended and should be verified in real requests/token exchanges**, especially for public clients. For confidential clients, never assume every framework version enables PKCE automatically; configure and integration-test per broker policy.

### src/main/java/demo/OidcBrokerClientApplication.java

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcBrokerClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcBrokerClientApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/")
        String home() {
            return "Open /me for OIDC login through the broker";
        }

        @GetMapping("/me")
        Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
            return Map.of(
                    "issuer", user.getIdToken().getIssuer().toString(),
                    "subject", user.getSubject(),
                    "audiences", user.getIdToken().getAudience(),
                    "authenticated", true);
        }
    }
}
~~~

**What the code does:** `oauth2Login` enables OIDC Authorization Code login. The Spring Security client performs callback handling, code exchange, and ID Token validation per configuration. `OidcUser` exists only after successful authentication. `/me` prints only the **broker issuer, broker-issued subject, and audience**, never touching `SAMLResponse` or IdP private keys. In production, avoid exposing unnecessary external subjects/claims and enforce authorization/tenant checks in APIs/services.

### Running

After setting the sandbox-issued secret environment variable, replacing the broker issuer with your real system, and configuring the matching OIDC client/redirect:

~~~bash
mvn spring-boot:run
~~~

`GET http://localhost:8080/` returns exact text:

~~~text
Open /me for OIDC login through the broker
~~~

`GET /me` when unauthenticated redirects to the broker's OIDC Authorization Endpoint. When the broker connects to an upstream SAML IdP and the user completes a valid flow, the JSON response takes **this form**:

~~~json
{
  "issuer": "https://broker.example.org/realms/workforce",
  "subject": "broker-issued-subject",
  "audiences": ["portal-web"],
  "authenticated": true
}
~~~

This is **illustrative output**, not fixed stdout: actual `subject`/`audiences` depend on the token. Unconnected example broker/IdP URLs will not complete login. Verify that `issuer` is the broker—**not** the SAML IdP—confirming the app is acting properly as an RP.

### When Enabling PKCE

Verify the broker OIDC client policy requires PKCE, the OIDC authorization request includes `code_challenge`/`code_challenge_method=S256`, the token request includes the matching `code_verifier`, and replayed/wrong verifiers are rejected. Spring Security 6.5 offers `DefaultOAuth2AuthorizationRequestResolver`/PKCE customizers if extra configuration is needed; verify with version-appropriate integration tests rather than rewriting token exchange.

## 13. Standalone Java 17: Testing IdentityLink Mapping

The following program runs directly on Java 17, demonstrating that the broker **does not automatically merge two SAML identities sharing the same NameID/email**. The two booleans represent validation results already produced by the library/protocol; they are **never trusted HTTP inputs**. The program creates no JWTs, parses no SAML, and does not replace an OpenSAML validator.

**File `BrokerIdentityLinkDemo.java`:**

~~~java
import java.util.Map;

public class BrokerIdentityLinkDemo {

    record ExternalIdentity(String trustedIssuer,
                            String nameIdFormat,
                            String nameIdValue) {}

    private static final Map<ExternalIdentity, String> APPROVED_LINKS =
            Map.of(
                new ExternalIdentity(
                        "https://idp-a.example.org/saml",
                        "persistent", "alex"), "broker-user-101",
                new ExternalIdentity(
                        "https://idp-b.example.org/saml",
                        "persistent", "alex"), "broker-user-202"
            );

    static String resolve(ExternalIdentity identity,
                          boolean samlValidated,
                          boolean requestCorrelated) {
        if (!samlValidated || !requestCorrelated) {
            return "DENY_UNVERIFIED";
        }
        String user = APPROVED_LINKS.get(identity);
        return user == null ? "DENY_UNLINKED" : user;
    }

    public static void main(String[] args) {
        ExternalIdentity a = new ExternalIdentity(
                "https://idp-a.example.org/saml", "persistent", "alex");
        ExternalIdentity b = new ExternalIdentity(
                "https://idp-b.example.org/saml", "persistent", "alex");
        ExternalIdentity unknown = new ExternalIdentity(
                "https://idp-c.example.org/saml", "persistent", "alex");

        System.out.println("a=" + resolve(a, true, true));
        System.out.println("b=" + resolve(b, true, true));
        System.out.println("unknown=" + resolve(unknown, true, true));
        System.out.println("badSignature=" + resolve(a, false, true));
        System.out.println("badCorrelation=" + resolve(a, true, false));
    }
}
~~~

Run:

~~~bash
javac BrokerIdentityLinkDemo.java
java BrokerIdentityLinkDemo
~~~

**Exact stdout:**

~~~text
a=broker-user-101
b=broker-user-202
unknown=DENY_UNLINKED
badSignature=DENY_UNVERIFIED
badCorrelation=DENY_UNVERIFIED
~~~

Both IdPs emit `NameID=alex`, yet the broker's external keys differ by issuer and resolve to **two distinct internal IDs**. When a user has no link, return `DENY_UNLINKED` instead of "looking up by email". If signature or `InResponseTo` fails, reject before mapping. Production must add NameID qualifiers, tenant/user status, subject longevity, link approval/assurance, and OIDC pairwise subject generation.

## 14. Multi-Tenancy and Approved Login Sources

A broker serving Acme/Payroll/Beta can bridge many upstream SAML IdPs and downstream OIDC clients. Never turn a tenant domain or query string into an arbitrary IdP metadata URL.

~~~text
(approved tenant, approved IdP alias)
            |
       configuration registry
            |
      trusted SAML IdP metadata/cert
            |
    SAML validation + IdentityLink
            |
       broker user + tenant
            |
    OIDC client registry + scopes
            |
         ID Token / Access Token
~~~

**Pre-auth:** tenant/IdP pickers allow selecting only aliases from an approved allowlist; never fetch `?idp=https://attacker.example/metadata`. Verify ownership of custom domains, reverse-proxy Host/SNI, forwarded headers, and egress SSRF controls.

**During auth:** `SAMLResponse` received at the broker ACS must match the exact SAML IdP registration, SP entity ID, audience, recipient, time bounds, and request correlation. The OIDC auth request must match the right client ID, redirect URI, and code/state/nonce/PKCE.

**Post-auth:** identity links and tenant memberships determine which tenants a user may access. A valid `iss=broker` token may be trusted by multiple RPs, yet **does not automatically grant roles in every tenant**. When an RP calls Beta resources with an Acme token/identity, the API must enforce tenant and data ownership.

## 15. Session Lifecycles and Logout Across Three Tiers

There are at least three distinct sessions:

~~~text
SAML IdP session:
    IdP knows the user is authenticated, may hold a SessionIndex

Broker OP session:
    Broker knows the external identity is verified; tracks link between
    SAML source, broker user, auth_time, and policy

Portal RP session:
    Portal holds browser cookie and SecurityContext after ID Token validation
~~~

**Local logout at the Portal** clears only the Portal session. **OIDC logout via the broker** can close the broker OP session if RP-initiated logout is supported, yet **does not automatically guarantee the Corporate SAML IdP performed SLO**. If the broker connects upstream SAML Single Logout, it requires the IdP's `SingleLogoutService`, signed `LogoutRequest`/Response, `NameID`/`SessionIndex` mapping, and partial/failure handling. Conversely, upstream IdP-initiated SLO is not guaranteed to notify every downstream RP session automatically.

### Token vs. Session TTL Differences

- `SAML Conditions/NotOnOrAfter` constrains whether the assertion may be accepted by the broker **at authentication time**; it need not equal ID Token `exp`.
- `OIDC ID Token exp` bounds the token, while the Portal HTTP session has its own lifetime.
- `Access Token exp`/scopes bound API calls; an API token may remain valid after browser logout.
- `Refresh Token`, if issued, has its own lifecycle, rotation, and revocation; protect it as a credential.
- `auth_time` must reflect authentic verification, never resetting arbitrarily when the broker refreshes tokens.
- When an upstream user is disabled, broker and Portal need session revocation/re-authentication policies—never wait for a SAML assertion to "expire" assuming the user is already blocked everywhere.

### Honest Logout UX

"Logged out of Portal" describes local state. "Requested federated session termination" describes broker/IdP coordination. "Logged out of all devices and apps" may be stated only with matching controls and real verification—never from a single SAML `LogoutResponse` alone.

## 16. Security Testing per Trust Boundary

| Test Case | Sandbox Simulation | Correct Result |
| --- | --- | --- |
| Happy path | SAML IdP A signs Response validly; broker issues OIDC code/token to Portal | Portal login succeeds if all policies pass |
| SAML wrong signer | XML self-signed with attacker key | Broker rejects |
| SAML wrong Issuer | IdP B emits Response for registration A | Broker rejects |
| SAML wrong Audience | Validly signed Assertion targeted at another SP | Broker rejects |
| SAML wrong Destination/Recipient | Response targeted at another ACS | Broker rejects |
| SAML `InResponseTo` mismatch | Response for a different `AuthnRequest` | Broker rejects |
| SAML replay/expiry | Replayed or expired Response | Broker rejects |
| IdP-initiated unsolicited | Response without pending request when policy forbids | Never issues OIDC token automatically |
| Unlinked external identity | New NameID with matching email | First broker login verifies or denies; no auto-link |
| Two IdPs sharing NameID/email | IdP A/B both use `alex@example.org` | Never auto-merge accounts |
| Disabled user / tenant denied | Valid SAML yet locked internal broker account | Mints no tokens, grants no access |
| MFA downgrade | SAML password-only while RP requires MFA | Never emits `acr=mfa` automatically |
| Unregistered OIDC redirect | Client sends attacker's redirect URI | Broker rejects |
| Wrong OIDC client secret | Wrong `/token` authentication | Broker rejects |
| OIDC PKCE mismatch | `code_verifier` does not match challenge | Broker rejects |
| OIDC authorization code reuse | Second attempt to exchange code | Broker rejects |
| OIDC `state` mismatch | RP receives callback not matching pending request | RP rejects |
| OIDC `nonce` mismatch | Broker ID Token carries wrong nonce | RP rejects |
| Wrong OIDC `iss` | Token signed by unconfigured issuer | RP rejects |
| Wrong OIDC `aud` | Token with `aud=payroll-web` sent to Portal | RP rejects |
| Invalid OIDC `kid`/`alg` | JWT signed with unknown key/alg | RP rejects; never fetches arbitrary JWK URLs |
| Expired OIDC token | Past `exp` | RP rejects |
| UserInfo `sub` mismatch | UserInfo `sub` differs from ID Token | RP rejects |
| Wrong token purpose | ID Token `aud=portal-web` sent to Reports API | API rejects |
| Wrong Access Token scope | Reports token lacks `reports.read` | API denies / 403 |
| Wrong Access Token audience | Payroll API token sent to Reports API | API rejects |
| Cross-tenant resource | Acme user reads Beta data | 403/deny at API/service |
| JWKS rotation | Broker rotates signing key within overlap window | RP refreshes keys per policy |
| SAML cert rotation | IdP switches to approved new public signing cert | Broker validates cleanly |
| Broker outage | OIDC `/token` unavailable | Fails safely with proper retries/circuit breaking |
| SLO `PartialLogout` | One federated SP fails to log out | Never claims global logout |
| Upstream user offboarded | Broker still holds stale refresh token/session | Revokes/short TTL/re-auth per policy |

**Proper testing technique:** Mutating SAML XML or a JWT payload **after signing** breaks the signature. That failure does not prove the Audience validator works. To test audiences, have a sandbox IdP/broker issue **validly signed messages targeted at another client/SP**. Never use production private keys or real users' raw assertions in labs.

### Four Testing Tiers

1. **Pure Java unit tests** for mappings like `BrokerIdentityLinkDemo`, identity collisions, and fail-closed logic.
2. **SAML integration** Broker SP ↔ IdP sandbox: Issuer/Audience/Recipient/`InResponseTo`/signatures, Attributes, and `AuthnContext`.
3. **OIDC integration** Portal RP ↔ Broker OP: Discovery, JWKS, Code/PKCE, state/nonce, ID Token, subject/assurance.
4. **Browser/E2E/API**: SameSite cookies, TLS/proxies, tenant resource checks, logout, refresh-token revocation, metadata/key rotation, and cluster/session failover.

## 17. Common Errors and Troubleshooting

| Symptom | Suspect Layer | Resolution |
| --- | --- | --- |
| SAML login fails at broker | IdP signing key, issuer, ACS, audience, timestamps | Check broker SP registration and IdP metadata |
| SAML passes yet broker issues no OIDC token | IdentityLink/tenant/first-login policy, OP session | Check broker link/consent/errors; never link by email |
| Portal redirects to wrong IdP | Broker identity provider selection/tenant hint | Allowlisted IdP aliases; check default flow |
| Portal reports invalid issuer | Config `issuer-uri` differs from OIDC `iss` | Compare against broker Discovery |
| Portal reports invalid audience | OIDC ID Token `aud` omits `portal-web` | Check client registration and token issuer |
| Unknown `kid` | OP JWKS rotation/cache out of sync | Check JWKS endpoint and key overlap |
| Login callback state mismatch | RP browser session/CSRF/context | Cookies, proxy, browser tabs, OAuth2 `AuthorizationRequestRepository` |
| Nonce mismatch | ID Token not bound to authorization request | Check broker nonce issuance and RP pending state |
| `invalid_grant` | Expired/reused code, redirect, or PKCE mismatch | Check code, token request, and clock skew |
| OIDC login passes yet API returns 401 | Access Token issuer/audience/signature | Check API token validation; never use ID Token |
| API returns 403 | Scope/tenant/resource permission | Identity link, role mapping, and authorization policy |
| Wrong MFA claims | `AuthnContext` → `acr/amr` mapping | Stop inflating assurance without evidence |
| User logs in via another IdP and merges accounts | Dangerous email auto-linking | Disable policy; run incident/revoke/approved re-link |
| Logout immediately SSOs back in | IdP/broker session still active | Distinguish RP logout, OP logout, and SAML SLO |
| SSO fails on only one node | Out-of-sync session repository/key/metadata cache | Shared state, NTP, consistent releases |
| Metadata URL blocked | Egress/TLS/cert/SSRF policy | Use approved sources; never disable the policy |

**Investigation order:** OIDC client/redirect/state → Broker upstream IdP selection → SAML response validation → IdentityLink/tenant/assurance → Broker OP code/token issuance → RP ID Token verification → API access token/authorization. Separating layers prevents "fixing SAML" when the real bug is an OIDC client secret, or "disabling JWT audience checks" when an ID Token was issued for the wrong client.

## 18. Operations, Key Rotation, Auditing, and Incidents

### Independent Key Rotation

**IdP SAML signing rotation:** IdP publishes/switches to a new public cert via an approved metadata channel; broker adds the new verification certificate with overlap while checking issuer/certificate. Never accept a public key self-asserted inside an unknown `SAMLResponse`.

**Broker SAML SP signing/decryption rotation:** broker coordinates its public SP certificate with the IdP; decryption keys may need to keep the old key temporarily to decrypt in-flight ciphertexts.

**Broker OIDC signing/JWKS rotation:** broker adds the new public JWK, signs with the new key carrying the right `kid`, and retains the old public key long enough for RPs to validate unexpired tokens per policy. If an OP private signing key is compromised, run incident response, rotate urgently, and revoke sessions/refresh tokens within scope.

**OIDC client secret rotation:** Portal and broker rotate credentials per policy via secret manager/managed identity; never place secrets in frontend code, logs, or Git.

### Auditing Without Leaking Data

Record: upstream IdP alias, broker SAML registration ID, OIDC client ID, correlation trace ID, outcome, status/error category, policy version, key version, and latency. Never print raw `SAMLResponse`, XML Attributes containing PII, NameIDs, Authorization Codes, JWTs, Access/Refresh Tokens, client secrets, private keys, or session cookies in logs/traces. Use synthetic identities for sandboxes.

### Example Incident: Wrong Identity Link

If the broker accidentally linked an IdP B user to an IdP A account due to a shared email:
1. Disable/roll back the auto-link mapper, block risky logins, and revoke affected broker/Portal sessions.
2. Identify affected accounts/tenants/client tokens, revoke refresh tokens, and evaluate Access Token TTLs.
3. Inspect SAML signing/Issuer evidence; separate cryptographic verification issues from business identity-mapping bugs.
4. Rebuild external identity links using issuer + stable identifier with approval; never re-enable email auto-linking.
5. Add "same email across two issuers" regression tests and review audit logs/privileges.
6. Coordinate with IdP, RP/API owners, and security responders per incident process.

## 19. Go-Live Checklist

- [ ] Broker SAML SP entity ID, ACS, and trusted IdP metadata/signing cert match the partner.
- [ ] Full upstream SAML validation (signature, issuer, audience, recipient/destination, time, correlation/replay).
- [ ] Never fetch arbitrary IdP metadata URLs or trust signers from user input.
- [ ] `IdentityLink` never relies solely on email/raw NameID; clear policies for first login, disabled accounts, and tenants.
- [ ] Stable Broker OP issuer; Discovery and JWKS publish public keys only; signing private keys protected.
- [ ] OIDC client enforces exact redirect URI, code flow, client authentication, and PKCE/state/nonce policies.
- [ ] OIDC ID Token has `iss=broker`, `aud=client_id`, broker-issued `sub`; claims emitted only per scope/policy.
- [ ] RP verifies issuer/JWKS/aud/nonce/exp and never accepts arbitrary issuer/JWK URLs.
- [ ] API validates **Access Token audience/scope**; never accepts ID Tokens as API credentials.
- [ ] Per-client/tenant permissions enforced; never assume "logged in means admin".
- [ ] `AuthnContext`/`auth_time`/`acr/amr` mapping is evidence-backed; reauth/MFA downgrade tests pass.
- [ ] IdP session, broker session, RP session, refresh-token revocation, and SLO behavior are documented honestly.
- [ ] Key rotation, failover, audit/secret handling, and security incident runbooks tested.
- [ ] Negative tests for issuer/aud/signature/redirect/nonce/PKCE/linking/tenant pass.

## 20. Exercises and Self-Assessment Questions

**Exercise 1 – identify the two trust boundaries.** Diagram SAML IdP → Broker SAML SP → Broker OIDC OP → Portal. Label who signs and who verifies on each leg. Explain why the Portal does not need the IdP's SAML signing public certificate to verify the broker's ID Token.

**Exercise 2 – compare audiences.** The SAML IdP emits an Assertion with Audience `urn:broker:saml:sp`. The broker emits an ID Token with `aud` `portal-web`. Explain why both are right without having to match.

**Exercise 3 – Java 17.** Run `BrokerIdentityLinkDemo.java` and verify the 5 stdout lines. Change the IdP issuer/NameID format and predict which link is denied. Explain the limitation of boolean flags in the demo compared to actual signature verification.

**Exercise 4 – Spring Boot.** With a sandbox broker exposing an OIDC client and an upstream SAML IdP, run `OidcBrokerClientApplication`. Verify `/me` prints the broker issuer rather than the SAML IdP issuer. Misconfigure `client_id` or redirect URI and analyze the resulting error.

**Exercise 5 – account linking.** Two IdPs both emit email `alex@example.org` with different NameIDs/issuers. Design a First Broker Login workflow that does not auto-link by email, stating the approval conditions required.

**Exercise 6 – PKCE/state/nonce.** Specify what the RP creates and what the broker checks. Test a wrong `code_verifier`, `state`, or `nonce` in the sandbox; explain which party is responsible for rejecting each.

**Exercise 7 – assurance.** The IdP emits `PasswordProtectedTransport` while the RP requires MFA. May the broker emit `acr=mfa`? Describe step-up/reauth or denying when proof is lacking.

**Exercise 8 – API.** Send an ID Token with `aud=portal-web` to call Reports API expecting `aud=reports-api`. Explain why the API must reject it even with a valid broker signature.

**Exercise 9 – logout.** The user logs out of Portal while broker/IdP sessions remain. Diagram the three sessions and describe OIDC RP-initiated logout, the broker OP session, upstream SAML SLO, and `PartialLogout`.

**Exercise 10 – incident.** If the broker minted tokens from an insufficiently validated SAML Assertion, divide responsibilities among IdP, broker, RP, and API, and list containment/revocation/rotation/regression-test steps.

**Pass criteria:** The learner clearly articulates **SAML validation → controlled external identity linking → OIDC OP code/token issuance → OIDC RP ID Token validation → API authorization**, accurately identifies issuer/audience/key owners, and runs the Java 17/Spring Boot demos against an IdP/broker sandbox.

## 21. Official References

- OpenID Connect Core 1.0 – ID Token, claims, validation, auth_time, subject types: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0 – OP issuer, token endpoint, jwks_uri: https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
- Spring Security 6.5 – OAuth2/OIDC Client: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html
- Spring Security – OAuth2 Login Core/ClientRegistration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 Response validation: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Boot 3.5 – OAuth2 Client/Resource Server: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Authorization Server – OIDC OP configuration model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Keycloak Server Administration Guide – SAML Identity Providers, Brokering, First Login/account linking: https://www.keycloak.org/docs/26.8.0/server_admin/
- OASIS SAML 2.0 Core – Issuer/Audience/Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
