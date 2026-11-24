# Comparing SAML AuthnContext with OIDC acr, amr, and Re-Authentication Requirements

> **Topic:** Spring Security – federation. **Group:** OIDC and Brokering. This knowledge unit compares how SAML 2.0 expresses/requests **authentication context** via `AuthnContext`, `RequestedAuthnContext`, and `ForceAuthn` against OIDC claims and parameters such as `acr`, `amr`, `auth_time`, `acr_values`, `max_age`, and `prompt=login`. The focus is on how a Relying Party (RP)/Service Provider (SP) or **identity broker** makes safe step-up decisions rather than relying solely on claim names.

## 1. Framing the Problem: Successful Authentication Is Not Always Enough for Sensitive Transactions

A Spring Security application lets employees sign in via an IdP using SAML or OIDC. When a user merely opens an informational page, normal SSO login may suffice. Yet when a user approves a wire transfer, changes admin privileges, downloads sensitive records, or manages keys, the organization may require:

- A specific **authentication assurance level**, such as an approved policy for MFA or phishing-resistant methods.
- A **sufficiently fresh authentication**, for instance completed within the last five minutes.
- An **authorized authentication source** for that business action/tenant—not just any IdP with a valid signature.
- **Exact subject and transaction session binding**, preventing login CSRF, assertion/token replay, and account switching across steps.
- Corresponding **business permissions** after assurance is met, such as tenant membership, role, and approval rights.

The challenge: SAML and OIDC use **different languages** to convey or request evidence. A SAML `AuthnContextClassRef` does not automatically equal an OIDC `acr`; OIDC `amr=["pwd","otp"]` does not prove every policy an app calls "MFA" is satisfied. Both protocols also require separating **authentication strength** from **authentication freshness**.

**Safety principle:** First verify the entire SAML assertion or OIDC ID Token, then evaluate assurance policy separately by **issuer + RP/SP + tenant + business action + time**. Never grant `ROLE_ADMIN`, unlock sensitive transactions, or treat unverified claims as sufficient merely because a string contains `mfa`, `high`, or `2fa`.

## 2. Distinguishing Four Concepts

| Concept | Question | Common in SAML 2.0 | Common in OIDC |
| --- | --- | --- | --- |
| **Authentication method** | How did the user authenticate? | AuthnContext may describe class/declaration; IdPs sometimes add custom attributes | `amr` is a list of method references, e.g., `pwd`, `otp`, `mfa` |
| **Authentication assurance/context class** | Which policy class/context does the authentication satisfy per IdP rules? | `AuthnStatement/AuthnContext/AuthnContextClassRef` or `AuthnContextDeclRef` | `acr` in ID Token; semantics defined by profile/OP or federation contract |
| **Fresh authentication** | When did the user authenticate and is it recent enough? | `AuthnStatement/@AuthnInstant`; request fresh auth via `AuthnRequest/@ForceAuthn` | `auth_time`, `max_age`, `prompt=login` |
| **Session reuse** | May an existing SSO session be reused? | IdP handles `ForceAuthn`/`IsPassive` in `AuthnRequest` | OP handles `prompt`, `max_age`, session policy |

**Example:** A user signs in with password + OTP at 08:00, and by 15:00 their SSO session is still active. The IdP can still emit an assurance level showing MFA occurred, yet **an authentication seven hours ago** fails a "fresh within 5 minutes" rule for a wire approval. **Strength** and **freshness** are two independent conditions; an active app session does not substitute for them.

### 2.1. Do Not Confuse Authentication Assurance with Authorization

- An OIDC ID Token with `acr=high` does not automatically grant `ROLE_ADMIN`.
- A SAML Assertion with an acceptable `AuthnContextClassRef` does not automatically grant access to another tenant's data.
- An IdP emitting `amr=mfa` does not replace checking payment recipients, limits, separation of duties, or action-specific step-up.
- Authentication strength is an input to a **policy decision**; authorization still requires user, tenant, permission, action, resource, risk level, time, and account status.

## 3. SAML: `AuthnContext` Lives Inside the Assertion's `AuthnStatement`

In SAML 2.0, the IdP can convey authentication details inside `AuthnStatement`, which contains `AuthnContext`. Abbreviated XML example, **not a complete Assertion for login**:

```xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2030-04-05T09:55:00Z"
    SessionIndex="_session-123">
  <saml:AuthnContext>
    <saml:AuthnContextClassRef>
      urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken
    </saml:AuthnContextClassRef>
  </saml:AuthnContext>
</saml:AuthnStatement>
```

Fields:

- **`AuthnInstant`:** when the IdP authenticated the user, not when the SP received the assertion; not automatically equal to `IssueInstant` of the SAML Response/Assertion.
- **`SessionIndex`:** reference to the IdP authentication session, typically used for SAML Single Logout, **not** `JSESSIONID` or the SP's web session ID.
- **`AuthnContextClassRef`:** URI identifying an **authentication context class**; the value is a **class/category**, not a detailed list of authentication steps.
- **`AuthnContextDeclRef` / `AuthnContextDecl`:** can reference/describe a concrete authentication method per profile/contract, distinct from ClassRef; many apps handle only ClassRef, so confirm with the IdP.
- **`Conditions`, `SubjectConfirmationData`, `AudienceRestriction`:** separate validity/recipient constraints; never equate them with authentication time or strength.

For instance, `TimeSyncToken` only states the class asserted by the IdP under that class's semantics. **Do not assume** this class meets every application requirement for "MFA", "phishing-resistant", or "NIST AAL2". Standard SAML classes provide technical vocabulary, while **strength under organizational policy must be agreed upon and verified**.

### 3.1. Read AuthnContext Only After the Assertion Has Been Validated

SP sequence:

1. Resolve the right `RelyingPartyRegistration` and trusted IdP issuer.
2. Verify the signature protecting the exact SAML Assertion/Response used, preventing XML signature wrapping.
3. Verify `AudienceRestriction` = SP entityID, `Recipient`/`Destination` = ACS, `InResponseTo`, timestamps, and replay per profile.
4. Extract `AuthnStatement/AuthnContext` and `AuthnInstant` **from the verified assertion**, bound to the current subject.
5. Map the class/declaration per the specific IdP policy; check the assurance level and freshness required by the business action.
6. When unsatisfied, **deny the sensitive action** and trigger a new step-up/reauth flow if the IdP supports it.

If an IdP sends a validly signed assertion whose `AuthnContextClassRef` is disallowed for a transaction, the user may still be logged into the app under a lower policy, yet **must not execute the high-protection transaction**. Whether to block the entire login or only the action depends on design, yet authentication must never equal authorization.

### 3.2. An AuthnStatement Is Not Automatically a Guarantee of "Just Authenticated"

Many IdPs mint a fresh `SAMLResponse` from an existing SSO session. In that case:

```text
Assertion IssueInstant: 2030-04-05T10:01:00Z
AuthnStatement AuthnInstant: 2030-04-05T08:00:00Z
App time now:              2030-04-05T10:01:10Z
```

The newly issued `SAMLResponse` **does not prove the user just entered a password/MFA**. For a business rule requiring fresh authentication within 5 minutes, an `AuthnInstant` 121 minutes old fails, even though the assertion is unexpired and validly signed.

The IdP's authentication timestamp may involve a complex multi-factor or chained authentication session. Ask the IdP: does `AuthnInstant` update after step-up, or retain the initial login time? If the IdP makes no exact contract commitment, never rely on it mechanically for sensitive policies.

## 4. SAML: How an SP **Requests** Authentication Context in AuthnRequest

A SAML `AuthnRequest` can contain:

- **`ForceAuthn`:** asks the IdP to re-authenticate the presenter directly rather than relying solely on an existing authentication session, per protocol definition and IdP policy.
- **`IsPassive`:** instructs the IdP not to interact directly with the user. If unable to satisfy, the IdP returns an appropriate error.
- **`RequestedAuthnContext`:** contains one or more `AuthnContextClassRef` **or** `AuthnContextDeclRef` elements plus a `Comparison` attribute.
- **`RequestedAuthnContext/@Comparison`:** how the IdP should compare context values it can satisfy.
- **`NameIDPolicy`, `Scoping`, `AssertionConsumerServiceURL`, `Issuer`:** other protocol constraints; they do not replace assurance.

Example fragment:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-stepup-42"
    Version="2.0"
    IssueInstant="2030-04-05T10:00:00Z"
    Destination="https://idp.partner.example/saml/sso"
    ForceAuthn="true"
    IsPassive="false">
  <saml:Issuer>https://app.example.org/saml2/service-provider-metadata/partner</saml:Issuer>
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef>
      urn:example:contract:partner:strong-v1
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
```

This is an **illustrative fragment only**; IDs/dates/URIs/certificates must come from a real flow, `AuthnRequest` may require signing, and the snippet above must not be used as a valid test vector. The URI `urn:example:contract:partner:strong-v1` is a **hypothetical value defined by a private integration contract**, not a standard SAML class or inherent proof of MFA.

### 4.1. Meaning of `Comparison`

| Value | Meaning in SAML | Notes |
| --- | --- | --- |
| `exact` | Result must match one requested class/declaration exactly; default when omitted | Appropriate when the IdP requires exact URIs; never accept "similar" URIs |
| `minimum` | IdP may choose a context considered at least as strong as requested, **per the IdP's ordering/evaluation** | Safe only when both parties agree on how the IdP ranks contexts |
| `better` | IdP must choose a context considered strictly stronger, not merely equal | "Stronger" has no global total order across all classes |
| `maximum` | IdP may choose a context no stronger than the threshold per standard semantics | Unsuitable when the goal is enforcing a stronger minimum step-up |

**Never invent a universal ranking table** of all SAML URIs and assume every IdP interprets `minimum/better` identically. What counts as "stronger" depends on the responder/IdP, and many implementations impose restrictions. For instance, Microsoft Entra has specific rules: when sending `RequestedAuthnContext`, `Comparison` must be `exact`; check the **exact IdP's** documentation before requesting `minimum` or `better`.

If an IdP cannot satisfy a `RequestedAuthnContext`, SAML allows it to return `NoAuthnContext`. The SP must treat that as **unmet requirements**, never falling back to allow the sensitive transaction using the existing session.

### 4.2. `ForceAuthn=true` Does Not Equal "Require MFA"

`ForceAuthn` requests **re-authentication**, yet the authentication **method** may still be a password unless a context/assurance policy demands a higher level. For fresh + high-assurance authentication, you need all of:

1. IdP/SP agreement on allowed levels via `RequestedAuthnContext` and/or integration policy.
2. `ForceAuthn=true` when the transaction needs **genuine re-authentication**.
3. After the response, SP validation of the **received `AuthnContext`** and **fresh `AuthnInstant`**.
4. Application validation of **user/tenant/permissions and transaction binding**.

Setting `ForceAuthn=true` alone without checking authentication strength can force a password re-entry while still failing MFA policy.

### 4.3. `IsPassive=true` Is Non-Interactive Mode, Not Re-Authentication

`IsPassive=true` asks the IdP to display no UI or user interaction. It helps passive SSO flows, yet is **not** a way to force OTP or passkey step-up when UI is needed. Combining `ForceAuthn=true` and `IsPassive=true` creates a request many IdPs cannot satisfy; designs must handle failures explicitly rather than silently downgrading to a lower level.

### 4.4. Illustrative SAML Step-Up Flow

```text
Browser holds a basic-level App Session
             |
             | POST /payments/{id}/approve
             v
SP policy: high assurance + fresh <= 300 seconds?
       | YES                       | NO
       v                           v
   Continue                Save pending transaction
   authorization           and request correlation
                                   |
                                   v
                              AuthnRequest:
                              ForceAuthn=true
                              RequestedAuthnContext exact strong
                                   |
                                   v
                           IdP reauthenticate/step-up
                                   |
                                   v
                           SP validate Response:
                         signature, issuer, audience,
                         recipient, InResponseTo, replay
                                   |
                                   v
                         Check AuthnContext + AuthnInstant
                                   |
                              OK? /  \ FAIL?
                               v        v
                          Bind to     Deny action,
                          same user   do not weaken policy
                               |
                               v
                        Recheck permission, tenant,
                        resource, transaction details
                               |
                               v
                           Approve
```

**Never treat "HTTP 302 back to the app" as proof of successful step-up**. Confirmation requires full validation and a post-callback policy decision; the user may hold an active app session while the IdP returned `NoAuthnContext` or a different level.

## 5. OIDC: Three Claims `acr`, `amr`, and `auth_time` Are Not Synonyms

A signed OIDC ID Token from an OP might carry an abbreviated payload like:

```json
{
  "iss": "https://op.partner.example/realms/finance",
  "sub": "user-42",
  "aud": "web-portal",
  "iat": 1901613600,
  "exp": 1901613900,
  "acr": "urn:example:contract:finance:high-v1",
  "amr": ["pwd", "otp"],
  "auth_time": 1901613500
}
```

**This is an illustrative payload**, not a complete ID Token or a JWT usable for login (no real header/signature; timestamps are illustrative only). A real ID Token must pass Spring Security/OIDC client validation for signature, `iss`, `aud`, `exp`, `nonce`/state, and flow checks; **only then** inspect assurance claims.

### 5.1. `acr` — Authentication Context Class Reference

`acr` is a string describing the **authentication context class the OP asserts was satisfied**. The value may be a URI like `urn:example:contract:finance:high-v1`, an OP profile string, or a value defined by another standard.

- There is no universal `"acr=2"` guaranteeing NIST AAL2 across every OP.
- Two IdPs sharing an `acr` string do not automatically share equivalent policies, evidence, enrollment, recovery, or phishing resistance.
- An OP may support multiple `acr` values, yet their meaning and strength must be defined in a **contract with that specific OP/issuer**.
- An application can request `acr` as an **Essential Claim** if the OP supports the `claims` parameter; sending only `acr_values` makes it a **Voluntary** request (see section 6).
- Even upon receiving a valid ID Token, the RP must still **verify `acr`** against an approved allowlist and business purpose—never assume the OP honored the request blindly.

### 5.2. `amr` — Authentication Methods References

`amr` is an **array of authentication methods** used. RFC 8176/IANA defines reference values, for example:

| `amr` | General Meaning | What Must Not Be Inferred? |
| --- | --- | --- |
| `pwd` | Password authentication | Does not imply MFA or phishing resistance |
| `otp` | One-time password used | Does not reveal OTP channel/factor or phishing resistance |
| `mfa` | OP asserts multi-factor authentication | Does not prove specific methods, freshness, assurance level, or org policy |
| `fpt` | Fingerprint biometric used | Does not guarantee multi-factor auth or hardware-attested keys |
| `face` | Facial recognition used | Does not imply AAL3 or biometric quality certification |
| `hwk` | Proof of possession of a hardware-secured key | Does not prove full phishing resistance if policy requires extra provenance/attributes |
| `swk` | Proof of possession of a software-secured key | Not equivalent to hardware-backed by default |
| `sms` | SMS confirmation used | Does not ensure phishing resistance or protection against SIM swap |
| `rba` | Risk-based authentication ran | Does not mean the user faced an actual MFA challenge |
| Vendor-defined values | Defined by OP/broker | Require a contract; never treat the string as a permission |

`amr=["pwd","otp"]` suggests two methods participated. Yet an RP **cannot conclude from syntax alone that a specific MFA policy was met**: the OP must be trusted, methods well-defined, factors independent where policy requires, and authentication recent enough.

`amr` may be absent depending on OP/flow. When a policy depends on `amr`, if the array is missing or contains unknown values, **never fabricate `amr=["mfa"]`**. Fail closed or trigger step-up per policy.

### 5.3. `auth_time` — Actual Authentication Timestamp

`auth_time` is a **NumericDate**—seconds since Unix epoch UTC—reporting when the user was authenticated by the OP. It differs from:

- `iat`: when the ID Token was issued.
- `exp`: when the ID Token expires for acceptance.
- When the frontend just sent the request.
- When the server created the local `HttpSession`.
- When an access token was refreshed.
- `SAMLResponse/IssueInstant` when a broker emits downstream assertions.

OIDC Core specifies that when **`max_age` is sent**, the returned ID Token **must include `auth_time`**. When `auth_time` is requested as an Essential Claim, it is also required. The RP must check freshness against policy; **an ID Token with `exp` in the future does not guarantee `auth_time` is fresh**.

Example:

```text
OP authenticated user at:  09:00:00 UTC
RP requests new auth:      10:00:00 UTC
OP reuses old SSO session: 10:00:02 UTC
ID Token iat:              10:00:03 UTC
ID Token auth_time:        09:00:00 UTC
RP requires fresh <= 300 seconds
=> NOT satisfied, even though iat is fresh and signature/exp are valid.
```

An OP may perform re-authentication yet apply a proprietary rule to `auth_time` when MFA is upgraded; the RP must test actual behavior and align the contract if decisions depend on this timestamp.

## 6. OIDC: Different Parameters for **Requesting** Authentication

### 6.1. `acr_values` — Suggesting Authentication Classes in Preference Order

Example authorization request (abbreviated URL):

```text
GET /authorize?
  response_type=code
  &client_id=web-portal
  &scope=openid
  &state=<opaque-correlation>
  &nonce=<opaque-nonce>
  &acr_values=urn%3Aexample%3Acontract%3Afinance%3Ahigh-v1
```

In a live request, the URL must be properly encoded and built by the OAuth2/OIDC client framework; `state`/`nonce` values are randomly generated and protected. `acr_values` is a **space-separated list of strings in order of preference** that the RP asks the OP to use. Per OIDC Core, this parameter requests `acr` as a **Voluntary Claim**: the OP may fail to return the exact level or omit `acr` depending on capability/profile. **Always inspect the `acr` value in the returned ID Token**; never grant access merely because `acr_values` was sent.

When the environment requires preventing silent downgrades, use an appropriate OP/client policy or the `claims` parameter with `acr` marked as an Essential Claim with specific values per OIDC, and still validate the response. Do not mix both ways of requesting `acr` without understanding their combined semantics.

### 6.2. The `claims` Parameter and Essential `acr`

Example JSON **value for the `claims` parameter** in OIDC, which must be URL-encoded when sent:

```json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:contract:finance:high-v1"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
```

Per OIDC Core, when an OP supports the `claims` parameter and the RP requests Essential `acr` with a list of values, the OP must return a matching `acr` or treat failure to satisfy it as a failed authentication. **That still does not turn vendor-specific strings into universal assurance levels**; the RP must validate issuer, token, `acr`, and timestamps on receipt. Never assume every OP implements `claims` completely; check discovery and test against the real provider.

**Protocol note:** If both `acr_values` and `claims.id_token.acr` with explicit values are sent together, their combined behavior in OIDC Core is **somewhat underspecified**. Prefer one consistent mechanism per OP contract and test before production.

### 6.3. `prompt=login` — Asking the OP to Re-Authenticate

`prompt=login` tells the OP to **re-authenticate the user**, even if the browser has an SSO cookie. The OP must handle it per OIDC Core, returning an appropriate error if unable to re-authenticate. However:

- It **does not itself require MFA**; it may prompt only for a password or another OP-chosen method.
- It **does not prove** freshness to the RP without `auth_time` or an appropriate verification source.
- An OP/broker fronting an upstream IdP may interpret re-authentication differently; test whether upstream is genuinely re-prompted or if the broker merely re-authenticates via another method.
- A `prompt=login` query value from an unverified client is not security proof; what matters is the RP-initiated request and the ID Token validated by the RP afterward.

### 6.4. `max_age` — Bounding Authentication Age

`max_age=300` instructs the OP to accept only an authentication at most **300 seconds** old; otherwise, the OP must attempt active re-authentication. When `max_age` is sent, the response ID Token **must contain `auth_time`**. `max_age=0` effectively forces fresh authentication equivalent to `prompt=login` per OIDC Core.

Example:

```text
max_age=300
OP auth_time = 10:00:00Z
RP receives ID Token at 10:04:59Z
=> Freshness 299 seconds: satisfies policy if all other conditions pass

OP auth_time = 10:00:00Z
RP receives ID Token at 10:05:01Z
=> 301 seconds: expired; must deny action or require reauth
```

Clock-skew tolerance must be small and policy-governed. Never substitute `iat` for `auth_time`, and never inflate `max_age` to hours just to mask step-up failures. In multi-hop broker systems, verify whether `auth_time` reflects when the broker authenticated the user or when the upstream IdP did; document that rule in the contract.

### 6.5. `prompt=none` Is Not a Way to Force MFA

`prompt=none` requests **no UI display**. If the user lacks a suitable session, consent/assurance is unmet, or silent auth fails, the OP returns an error such as `login_required` or `interaction_required`. Never use `prompt=none` instead of `prompt=login`/`max_age` when a transaction requires fresh user interaction.

### 6.6. `prompt=select_account` Is Also Not Re-Authentication

`prompt=select_account` asks the OP to show an account chooser when supported; picking an account **does not prove the user re-entered a password or completed MFA**. For high-value transactions, verify that the post-callback account `sub` matches the original account, and enforce freshness and assurance per policy.

## 7. Core Comparison Table: SAML vs. OIDC

| Intent | SAML 2.0 Mechanism | OIDC Mechanism | Limits When Treating as Equivalent |
| --- | --- | --- | --- |
| **SP/RP requests context** | `RequestedAuthnContext` with ClassRef/DeclRef | `acr_values` or Essential `acr` in `claims` | Values and enforcement share no universal namespace/strength |
| **IdP/OP declares achieved context** | `AuthnStatement/AuthnContextClassRef` | `acr` in ID Token | Map only via issuer contract; never compare names naively |
| **Method details** | Class/declaration/attribute per IdP | `amr` list, e.g., `pwd`, `otp` | A SAML class does not automatically map to AMR methods |
| **User authentication time** | `AuthnStatement/@AuthnInstant` | `auth_time` | Must define which issuer/flow the timestamp belongs to |
| **Require active re-authentication** | `AuthnRequest ForceAuthn="true"` | `prompt=login` or `max_age=0` | Does not automatically demand a stronger method |
| **Bound authentication age** | No exact universal equivalent to `max_age` in all SAML AuthnRequests; SP can send ForceAuthn and check AuthnInstant | `max_age=N` and check `auth_time` | Never substitute `IssueInstant`/`iat` |
| **Disallow user interaction** | `IsPassive="true"` | `prompt=none` | Different error codes and IdP capabilities |
| **Report unmet assurance** | `NoAuthnContext` or SAML error status | OIDC error or insufficient/missing `acr` (when voluntary) | Fail closed; no silent downgrade |
| **Session alignment** | `SessionIndex` / SAML SLO, SP HttpSession | OP `sid` and logout specs, RP HttpSession | Session ID is not assurance proof |
| **Signed/trusted data** | Signed SAML Response/Assertion, issuer, audience, ACS, correlation | Signed ID Token JWT, `iss/aud/nonce`, exp, state | Full validation required before reading claims |
| **Step-up at broker** | Broker acts as SP to upstream SAML; checks AuthnContext then maps | Broker acts as downstream OP; signs ID Token `acr/amr/auth_time` | **Never** infer high level solely from login success |

**There is no universally valid automatic translation** such as `SAML AuthnContextClassRef = acr` or `ForceAuthn = max_age=300`. A broker may maintain a controlled mapping, yet the broker itself is accountable to the RP for evidence quality and risk level.

### 7.1. Examples of Two Invalid Comparisons

Wrong:

```text
SAML AuthnContextClassRef =
  urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
=> OIDC amr=["mfa"]           // NO automatic basis

OIDC acr="2"
=> SAML AuthnContextClassRef="urn:...:TimeSyncToken"
=> achieves phishing-resistant MFA  // NO automatic basis
```

Right:

```text
(verified issuer, class/method, timestamp, policyVersion, audience)
           |
           v
assurance mapping table with owner + contract + test/certification
           |
           v
internal level: BASIC / CONTRACT_STRONG
           |
           v
evaluate action/tenant, freshness, risk, step-up
```

Do not use example class URIs in this lesson to assert the actual assurance standards of a real IdP.

## 8. Broker Architecture: SAML Upstream → OIDC Downstream

In identity brokering, a broker plays both roles simultaneously:

```text
Browser        Upstream SAML IdP       Identity Broker (SAML SP + OIDC OP)       Downstream OIDC RP
   |                  |                            |                                    |
   | -- login to RP ------------------------------------------------------------->|
   |                  |                            |<--- authorize/acr_values/max_age -|
   |<------------------------------ redirect broker -----------------------------|
   |                  |<---- SAML AuthnRequest ------|                             |
   |                  |      ForceAuthn / context    |                             |
   |<---- authenticate / step-up at upstream -------|                             |
   |-------------------- SAMLResponse ------------->|                             |
   |                  |    broker validates assertion:
   |                  |    issuer, signing key,
   |                  |    audience, recipient, time,
   |                  |    InResponseTo, AuthnContext
   |                  |                            |
   |                  |                       policy mapping:
   |                  |                       SAML context + AuthnInstant
   |                  |                       -> allowed downstream acr/auth_time
   |                  |                            |
   |<--------------------------------------------- | ---- code response ---------->|
   |                  |                            |<- token request ------------|
   |                  |                            |-- signed ID Token ---------->|
   |                  |                            |   acr/amr/auth_time           |
   |                  |                            |                         RP verifies
   |                  |                            |                         issuer,aud,acr,time
```

**A broker issues ID Tokens under its own issuer**, e.g., `https://broker.example.org`. The downstream RP does not directly trust the upstream SAML IdP's public key; it trusts the broker via OIDC. Thus the broker must **substantiate and stand behind** the `acr` it emits as originating from a policy-compliant SAML authentication context.

### 8.1. Provenance Data Should Be Kept Internal

Illustrative record:

```text
VerifiedUpstreamEvidence:
  protocol: SAML2
  upstreamIdpEntityId: https://idp.partner.example/entity
  upstreamSubjectKey: qualified persistent NameID
  upstreamSpEntityId: broker SAML SP entityID
  classRef: urn:example:contract:partner:strong-v1
  authenticationInstant: 2030-04-05T10:00:00Z
  assertionId: _assertion123
  inResponseTo: _request-456
  validationSucceeded: true
  trustedSigningCredentialVersion: cert-v4

BrokerPolicyDecision:
  policyVersion: assurance-map-v7
  downstreamClientId: web-portal
  requiredAssurance: FINANCE_STEP_UP
  mappedAcr: urn:example:broker:finance-high-v1
  mappedAmr: (only if independently justified by contract)
  mappedAuthTime: upstream authenticationInstant (only if semantically valid)
  decision: ALLOW

Downstream ID Token:
  iss: https://broker.example.org
  aud: web-portal
  sub: stable pairwise subject for downstream RP
  acr: urn:example:broker:finance-high-v1
  auth_time: ...
```

**Never copy raw upstream `NameID`, certificates, or sensitive user attributes straight into downstream tokens** unnecessarily. Each RP needs stable subject mapping, right audience, and consent/privacy policy compliance. `auth_time` must reflect **user authentication time** per contract, not when the broker minted the ID Token.

### 8.2. Mapping Must Be a Versioned Allowlist

Example **hypothetical internal contract**:

| Verified Upstream Issuer | Confirmed SAML Value | Allowed Downstream `acr` | Additional Conditions |
| --- | --- | --- | --- |
| `https://idp.partner.example/entity` | `urn:example:contract:partner:strong-v1` | `urn:example:broker:finance-high-v1` | Fresh AuthnInstant, verified assertion, policy v7 |
| Same IdP | `urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport` | `urn:example:broker:basic-v1` | Never emit `amr=mfa` automatically |
| Approved second IdP | Class URI proven under second IdP's contract | Second IdP's own mapping | Requires separate policy review |
| Unknown IdP | Any URI/identifier | **Do not map; reject** | Never auto-provision trust sources |
| Upstream missing AuthnContext | Missing | **Never map to high** | Use only evaluated fallback policy |

**Provenance is mandatory:** record issuer, protocol, registration, key/trust version, context, AuthnInstant, mappingVersion, policyVersion, and downstream audience, and bound lifetimes. If the broker knows only that a `SAMLResponse` was signed without a verified context class, never emit downstream `acr=high` for "compatibility".

### 8.3. Do Not Fabricate `amr` When Upstream Omits Concrete Methods

If a SAML IdP asserts only a "strong" class without **explicitly specifying concrete methods**, the broker may emit a downstream `acr` under an evaluated contract, yet **must not invent `amr=["pwd","otp"]`** without evidence that password + OTP were truly used. Separate:

- `acr`: achieved level/context per trusted issuer policy.
- `amr`: list of methods **actually substantiated by evidence**.
- `auth_time`: user authentication timestamp per trust policy.
- `iat`: when the broker issued the token; cannot replace `auth_time`.

**Warning:** Some parties emit `acr`/`amr` as custom SAML attributes; they still require a verified issuer, defined semantics, and signature verification. An `acr` string inside an arbitrary SAML attribute **cannot** be copied blindly into OIDC.

### 8.4. Re-Authentication Across Multiple Hops Has No Automatic Guarantee

When a downstream RP sends `prompt=login` or `max_age=0` to a broker, the broker must determine:

- Should it re-authenticate at the broker to satisfy the contract, or must it force the upstream IdP to refresh?
- If the broker bridges to SAML, does it send a **fresh `AuthnRequest` with `ForceAuthn=true`** upstream, keeping correlation with the exact downstream request?
- Does the upstream IdP genuinely re-authenticate and emit a fresh `AuthnInstant`?
- Does the broker validate `RequestedAuthnContext`, returned class, signature, and freshness **before** minting the downstream ID Token?
- If upstream returns `NoAuthnContext` or ignores `ForceAuthn`, does the broker reject per policy rather than downgrading silently?
- If the downstream user switches accounts during step-up, does the broker block completing the original user's action?

**Never assume:** `prompt=login` at RP → broker = `ForceAuthn=true` upstream unless the broker is explicitly configured and tested to perform that mapping.

## 9. Building Assurance Policies by Source and Action, Not Generic Strings

An internal policy table might look like:

| Business Action | Internal Level | Freshness | Permitted Sources | When Unsatisfied |
| --- | --- | --- | --- | --- |
| Read public page | ANONYMOUS | Not required | None | No SSO needed |
| Read standard reports | BASIC | Per web session | Allowlisted IdP | Log in if unauthenticated |
| View sensitive personal info | VERIFIED | ≤ 30 minutes | IdP supporting assurance mapping | Step-up if lacking |
| Approve large disbursement | FINANCE_STEP_UP | ≤ 5 minutes | IdP with strong class/acr contract | Reauth + assurance + approval permission |
| Change MFA method | ACCOUNT_RECOVERY_STRONG | Freshness per risk policy | Approved IdP/OP | Dedicated reauth, audit, and alerts |
| Grant admin privileges | ADMIN_STEP_UP | ≤ 5 minutes or stricter | Enterprise policy | Step-up, separation of duties, admin approval |

**Each row is an independent policy decision.** A user holding `FINANCE_STEP_UP` must still hold approval rights for that disbursement and belong to the right tenant. High-level evidence earned for action A is not automatically reusable indefinitely for action B.

### 9.1. Defining a Minimal Evidence Record

```text
VerifiedAssurance:
  protocol               = OIDC | SAML2
  sourceIssuer            = verified iss / IdP entityID
  subjectKey              = verified subject
  registrationId          = Spring registration actually used
  contextReference        = verified acr / SAML AuthnContextClassRef
  methodReferences        = verified amr if present (OIDC)
  authenticationInstant   = auth_time / AuthnInstant, if contract supports
  issuedAt                = token/assertion issue time (separate)
  sessionId               = local session reference
  evidenceHashOrId        = server-side audit reference, not raw token
  assurancePolicyVersion  = server-approved version
  evaluatedAt             = current instant UTC
```

**Source data must already be validated**, never passed straight as a DTO from the browser. Having an RP receive `{"acr":"high"}` JSON from the frontend does not make the claim trustworthy.

### 9.2. Step-Up Decision Sequence

```text
Request business action
     |
     v
Is session/local principal valid? user/tenant/action allowed?
     |
     v
Does assurance evidence still match the user, issuer, registration, session?
     |
     v
Is ContextRef in the allowlist for this source + policyVersion?
     |
     +--- NO ---> STEP_UP_REQUIRED
     |
     v
Is AuthenticationInstant present and fresh enough?
     |
     +--- NO ---> REAUTHENTICATE
     |
     v
Any additional risks (tenant, device, amount, policy upgrade)?
     |
     +--- NO ---> stronger step-up / deny
     |
     v
Authorize exact action/resource; consume pending transaction binding
```

If the user just logged in yet assurance is too low, require **step-up**. If assurance is sufficient yet authentication time is stale, require **re-authentication**. If the issuer source is unapproved, **deny** rather than looping login forever.

### 9.3. Avoiding Infinite Step-Up Loops

Wrong:

```text
User -> /approve
 -> redirect login with high acr
 -> OP returns low acr
 -> app redirects to same login again
 -> OP returns low acr
 -> infinite loop
```

Right: cap attempts, record the unmet reason, display clear messaging/support paths, and **refuse the action**. If the OP cannot support the high level, update the IdP contract or policy—never delete the `acr`/ClassRef check. Separate "insufficient assurance" errors from signature, issuer, audience, nonce, CSRF, or session errors.

## 10. Spring Security OIDC: Requesting `max_age` / `acr_values` at Login

Spring Security Servlet provides `DefaultOAuth2AuthorizationRequestResolver` and `OAuth2AuthorizationRequest.Builder#additionalParameters` to add OIDC parameters to the Authorization Request. This is the standard extension point for adding `max_age`, `acr_values`, or `prompt`.

**This example applies the same parameters to every OIDC login**. It works well for labs, yet is **not** the ideal way to perform action-specific step-up because every login carries identical parameters. In production, select policies by route/risk, keep request context on the server, and ensure callbacks correlate to the exact step-up transaction.

File `src/main/java/com/example/federation/OidcAssuranceLoginConfig.java`:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAssuranceLoginConfig {

    @Bean
    SecurityFilterChain oidcWeb(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(params -> {
                params.put(
                    "acr_values",
                    "urn:example:contract:finance:high-v1");
                params.put("max_age", "300");
            }));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)))
            .build();
    }
}
```

**Build prerequisites:** This class belongs in a Spring Boot Servlet app with Java 17+, Spring Security, and `spring-security-oauth2-client`/`spring-boot-starter-oauth2-client`. Configure `ClientRegistrationRepository` with `issuer-uri`, client ID, client secret/PKCE, registered HTTPS callback, and a real OP; it is not standalone Java compilable with bare `javac`.

Explanation:

- `resolver` builds the Authorization Request when the browser hits `GET /oauth2/authorization/{registrationId}`.
- `additionalParameters` preserves Spring's standard parameters while adding `acr_values` and `max_age`; **never populate `state`, `nonce`, `code_challenge`, or `redirect_uri` from untrusted data**.
- `max_age=300` asks the OP to return `auth_time`; the RP **must verify** that claim in the flow/authorization policy.
- `acr_values` is a voluntary request; the RP must still check the actual `acr`. The sample URI is an **illustrative** contract value with no universal meaning.
- When an environment requires essential `acr`, use the `claims` request parameter per OIDC Core and OP support; never combine `acr_values` + essential `acr` arbitrarily since combined semantics are underspecified.
- This example **does not automatically refresh an existing Authentication on every request**. If the user already holds a local session and requests `/approve`, Spring serves the page directly without an OIDC round-trip. Step-up logic must **explicitly initiate** a new OAuth2 authorization flow when required, rather than merely configuring the resolver.
- With multiple `ClientRegistration` entries, scope policies by issuer/client inside the resolver and policy service; never send a `"finance-high"` URI to an OP that does not support it.

### 10.1. Adding `prompt=login` When Needed

If **every login** in a test environment must force OP re-authentication, you can add:

```java
resolver.setAuthorizationRequestCustomizer(builder ->
    builder.additionalParameters(params -> {
        params.put("prompt", "login");
        params.put("max_age", "0");
    }));
```

This is an **alternative** to the parameter config above—do not call `setAuthorizationRequestCustomizer` twice expecting them to merge; the later call overwrites the earlier customizer. In production, trigger re-authentication only for actions that require it. `prompt=login`/`max_age=0` **does not** itself enforce MFA; if a transaction requires high assurance, inspect `acr`/contract separately.

### 10.2. Validating Effective Claims After OIDC Login

Spring Security provides `OidcUser` and `OidcIdToken` to read claims validated by the framework. `IdTokenClaimAccessor` exposes:

- `getAuthenticationContextClass()` → `acr`, may be null.
- `getAuthenticationMethods()` → `amr` list, may be null.
- `getAuthenticatedAt()` → `auth_time` as an `Instant`, may be null.
- `getIssuedAt()` → `iat`, **never** replaces `auth_time`.
- `getIssuer()`, `getAudience()`, `getSubject()` → use for proper validation/identity context.

**Example controller reporting only the check result, granting no permissions and exposing no sensitive claims**. File `src/main/java/com/example/federation/OidcAssuranceStatusController.java`:

```java
package com.example.federation;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OidcAssuranceStatusController {

    private static final String TRUSTED_ISSUER =
        "https://op.partner.example/realms/finance";
    private static final String REQUIRED_ACR =
        "urn:example:contract:finance:high-v1";

    @GetMapping("/assurance-status")
    public Map<String, Boolean> status(
            @AuthenticationPrincipal OidcUser principal) {
        if (principal == null) {
            return Map.of("meetsExamplePolicy", false);
        }

        var idToken = principal.getIdToken();
        var issuer = idToken.getIssuer();
        String acr = idToken.getAuthenticationContextClass();
        Instant authTime = idToken.getAuthenticatedAt();
        Instant now = Instant.now();

        boolean trustedIssuer = issuer != null
            && TRUSTED_ISSUER.equals(issuer.toString());
        boolean correctAcr = REQUIRED_ACR.equals(acr);
        boolean fresh = authTime != null
            && !authTime.isAfter(now)
            && Duration.between(authTime, now)
                .compareTo(Duration.ofMinutes(5)) <= 0;

        return Map.of(
            "meetsExamplePolicy",
            trustedIssuer && correctAcr && fresh);
    }
}
```

**Important note:** This is a boolean-reporting demo endpoint that **assumes Spring already validated the ID Token, registration, and session**. With multiple issuers/clients, resolve the expected issuer and policy for the active registration instead of hardcoding one issuer app-wide. Production must run the policy service **before the protected action** rather than letting the frontend gate access from an endpoint boolean. If `auth_time` lies slightly in the future due to minor clock skew, a policy may allow bounded approved skew; the demo is intentionally strict.

The demo does not check `amr` to infer MFA; because `amr` has OP-dependent semantics, high assurance here is anchored to an approved `acr` contract and freshness. In high-risk systems, verify enrollment, phishing resistance, session revocation, and transaction binding per policy beyond these two values.

**Do not expose `/assurance-status` to unauthenticated users** in production; the security chain must require authentication and avoid leaking account/session details needlessly.

## 11. Spring Security SAML: Requesting `ForceAuthn` When Building AuthnRequest

Spring Security Servlet includes `Saml2WebSsoAuthenticationRequestFilter`. When the browser initiates `GET /saml2/authenticate/{registrationId}`, the framework can use `OpenSaml5AuthenticationRequestResolver` (Spring Security 7.x/OpenSAML 5) to construct the `AuthnRequest`. Spring's reference shows using `setAuthnRequestCustomizer` to set `ForceAuthn=true`.

File `src/main/java/com/example/federation/SamlForceAuthnConfig.java` for **Spring Security 7.x with OpenSAML 5**:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlForceAuthnConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
            new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
            new OpenSaml5AuthenticationRequestResolver(
                registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
            context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }
}
```

**Explanation:**

- The resolver uses Spring's `RelyingPartyRegistrationRepository`, which must contain **valid** IdP metadata, ACS, entityID, and signing/verifying credentials.
- `setForceAuthn(true)` instructs the IdP to re-authenticate when the `AuthnRequest` is sent. It does not automatically add `RequestedAuthnContext` or guarantee the IdP uses MFA.
- The sample enables `ForceAuthn` on **every** `AuthnRequest` handled by this bean; do that only in labs or when system-wide policy genuinely requires it. For action-level step-up, build a request customizer backed by a trusted policy source and correlation—**never let the browser toggle `ForceAuthn`**.
- In Spring Security 6.x/OpenSAML 4, the API may use `OpenSaml4AuthenticationRequestResolver` with a different package/version; **never rename classes blindly**. Consult the reference for your exact version.
- The configuration above is not a complete `SecurityFilterChain`; the app still needs `saml2Login`, RP registrations, and filters for `SAMLResponse`/ACS processing. Never drop signature, audience, recipient, `InResponseTo`, or replay validation just to "test ForceAuthn".
- If the IdP requires a signed `AuthnRequest`, configure the **SP's** private signing credential and the right algorithm/binding; the IdP decides whether the `ForceAuthn`/context request is honored.

### 11.1. What About `RequestedAuthnContext`?

When a specific class is needed, construct the appropriate OpenSAML `RequestedAuthnContext` and `AuthnContextClassRef` objects inside the same `setAuthnRequestCustomizer` and attach them to the `AuthnRequest`. That requires the builder/namespace/`AuthnContextComparisonTypeEnumeration` matching your **running OpenSAML version**; never copy Java builders from another major version without compiling.

Verify the generated `AuthnRequest` against a test IdP in decoded XML form:

```xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
  <saml:AuthnContextClassRef>
    urn:example:contract:partner:strong-v1
  </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
```

Confirm the IdP supports that URI and `Comparison=exact`. **Do not assume a custom URI is a standard class**. For IdPs accepting only standard classes, pick a supported class per documentation while still verifying whether that class satisfies your organization's assurance policy. Spring's customizer builds the outbound request; it **does not verify assurance in the inbound `SAMLResponse`** for custom business policies unless you add enforcement.

### 11.2. Reading AuthnContext/Instant When the SP Needs Custom Enforcement

Spring Security uses OpenSAML to validate `SAMLResponse` and build `Saml2Authentication`. `Saml2AuthenticatedPrincipal` exposes NameID/attributes via its API, yet **AuthnStatement/`AuthnContextClassRef` is not automatically surfaced as a standard authority or claim on the principal**.

To enforce business assurance policy, pick an extension point **after OpenSAML validation** in the version-specific authentication provider/response conversion, extract `AuthnContext`/`AuthnInstant` from the **signed/verified assertion**, and save a separate `VerifiedAssurance` record in the authenticated session. Never:

- Re-parse `SAMLResponse` from the HTTP parameter in a controller to read `AuthnContextClassRef`.
- Read `ClassRef` from XML whose signature was not verified.
- Grant `ROLE_ADMIN` solely from a context URI name.
- Substitute `AuthnStatement/SessionIndex` for `AuthnInstant`.
- Use a "recent `IssueInstant`" to ignore a stale authentication timestamp.
- Skip SAML response validation when the IdP omits the expected context.

In Spring Security 7.x, the OpenSAML 5 provider exposes validation/conversion customization APIs per reference; Spring Security 6.x maps to a different OpenSAML version. Test your bridge with validly signed `SAMLResponse` messages from a test IdP carrying the right contexts.

## 12. Standalone Java 17: Assurance Level and Freshness Policy

To learn decision logic without running a live IdP, build a **Java 17 console program**. Its inputs represent **mocked evidence already verified by a trusted OIDC/SAML layer**; it does not parse JWT/SAML, verifies no signatures, and **must never be used as a production federation validator**.

Illustrative policy:

- Trusted OIDC OP: `https://op.example.org`. Only `acr=urn:example:policy:oidc:strong-v1` counts as strong.
- Trusted SAML IdP: `https://idp.example.org/entity`. Only `AuthnContextClassRef=urn:example:policy:saml:strong-v1` maps to strong.
- Freshness: `authenticationTime` must not be older than 5 minutes or in the future relative to the test UTC time.
- The `amr` array only describes methods and **cannot elevate** a weak class/`acr`.
- Unknown issuers are rejected without creating new trust sources.

File `FederatedAssurancePolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

public final class FederatedAssurancePolicyDemo {

    enum Decision {
        ALLOW,
        STEP_UP_REQUIRED,
        REAUTHENTICATE,
        DENY_SOURCE,
        DENY_TIME
    }

    record VerifiedEvidence(
        String protocol,
        String issuer,
        String contextReference,
        Set<String> methods,
        Instant authenticatedAt
    ) { }

    private static final String OIDC_ISSUER =
        "https://op.example.org";
    private static final String SAML_ISSUER =
        "https://idp.example.org/entity";

    private static final String OIDC_STRONG =
        "urn:example:policy:oidc:strong-v1";
    private static final String SAML_STRONG =
        "urn:example:policy:saml:strong-v1";

    static Decision evaluate(
            VerifiedEvidence evidence,
            Instant now) {

        if (evidence == null || now == null) {
            return Decision.DENY_SOURCE;
        }

        String requiredContext;
        if ("OIDC".equals(evidence.protocol())
                && OIDC_ISSUER.equals(evidence.issuer())) {
            requiredContext = OIDC_STRONG;
        } else if ("SAML2".equals(evidence.protocol())
                && SAML_ISSUER.equals(evidence.issuer())) {
            requiredContext = SAML_STRONG;
        } else {
            return Decision.DENY_SOURCE;
        }

        if (!requiredContext.equals(evidence.contextReference())) {
            return Decision.STEP_UP_REQUIRED;
        }

        Instant authenticatedAt = evidence.authenticatedAt();
        if (authenticatedAt == null) {
            return Decision.REAUTHENTICATE;
        }
        if (authenticatedAt.isAfter(now)) {
            return Decision.DENY_TIME;
        }

        Duration age = Duration.between(authenticatedAt, now);
        if (age.compareTo(Duration.ofMinutes(5)) > 0) {
            return Decision.REAUTHENTICATE;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2030-04-05T10:00:00Z");

        VerifiedEvidence oidcStrong = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("pwd", "otp"), now.minusSeconds(120));

        VerifiedEvidence oidcStale = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("pwd", "otp"), now.minusSeconds(601));

        VerifiedEvidence oidcWeak = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, "urn:example:policy:oidc:basic-v1",
            Set.of("pwd"), now.minusSeconds(30));

        VerifiedEvidence oidcOnlyAmr = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, "urn:example:policy:oidc:basic-v1",
            Set.of("mfa"), now.minusSeconds(30));

        VerifiedEvidence samlStrong = new VerifiedEvidence(
            "SAML2", SAML_ISSUER, SAML_STRONG,
            Set.of(), now.minusSeconds(40));

        VerifiedEvidence samlWeak = new VerifiedEvidence(
            "SAML2", SAML_ISSUER,
            "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport",
            Set.of(), now.minusSeconds(40));

        VerifiedEvidence unknownIssuer = new VerifiedEvidence(
            "OIDC", "https://op.unknown.invalid", OIDC_STRONG,
            Set.of("mfa"), now.minusSeconds(40));

        VerifiedEvidence missingTime = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("mfa"), null);

        VerifiedEvidence futureTime = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("mfa"), now.plusSeconds(30));

        System.out.println("oidcStrong=" +
            evaluate(oidcStrong, now));
        System.out.println("oidcStale=" +
            evaluate(oidcStale, now));
        System.out.println("oidcWeak=" +
            evaluate(oidcWeak, now));
        System.out.println("oidcOnlyAmr=" +
            evaluate(oidcOnlyAmr, now));
        System.out.println("samlStrong=" +
            evaluate(samlStrong, now));
        System.out.println("samlWeak=" +
            evaluate(samlWeak, now));
        System.out.println("unknownIssuer=" +
            evaluate(unknownIssuer, now));
        System.out.println("missingTime=" +
            evaluate(missingTime, now));
        System.out.println("futureTime=" +
            evaluate(futureTime, now));
    }
}
```

Compile and run on JDK 17+ from the directory containing the file:

```bash
javac --release 17 FederatedAssurancePolicyDemo.java
java FederatedAssurancePolicyDemo
```

Exact stdout:

```text
oidcStrong=ALLOW
oidcStale=REAUTHENTICATE
oidcWeak=STEP_UP_REQUIRED
oidcOnlyAmr=STEP_UP_REQUIRED
samlStrong=ALLOW
samlWeak=STEP_UP_REQUIRED
unknownIssuer=DENY_SOURCE
missingTime=REAUTHENTICATE
futureTime=DENY_TIME
```

**Explanation:**

1. `oidcStrong` has the right OP issuer, strong class, and sufficiently fresh timestamp.
2. `oidcStale` has the strong class yet was authenticated 601 seconds ago, exceeding the 300-second limit.
3. `oidcWeak` is fresh yet lacks the strong class.
4. `oidcOnlyAmr` includes `mfa` in methods yet its class remains basic, so it is not promoted.
5. `samlStrong` uses the **SAML issuer's own policy URI**, not the OIDC `acr` URI.
6. `samlWeak` carries a common SAML class that is not in the approved strong mapping.
7. `unknownIssuer` is never treated as a trusted source merely for presenting a strong context.
8. `missingTime` is not allowed to "fall back to `iat`".
9. `futureTime` is rejected; in production, clock-skew tolerance must be bounded and tested by policy.

**Mandatory limitation:** `VerifiedEvidence` is a **mocked** record. In production it must be constructed from a **library-validated token/assertion**, along with subject, audience, transaction ID, session, tenant, expiry, and trust metadata. Never construct `VerifiedEvidence` from browser-supplied JSON. `evaluate` demonstrates one check inside an authorization engine and does not replace permission or object-ownership checks.

## 13. Step-Up Flows in Multi-IdP and Multi-Tenant Applications

A SaaS may connect to both an enterprise OIDC OP and a partner SAML IdP. For the same disbursement approval action, each source has a **different assurance contract**:

| Tenant | Authentication Source | Level Requirement | Freshness | Expected Behavior |
| --- | --- | --- | --- | --- |
| Finance A | Corporate OIDC | `acr` in Corporate high allowlist | 5 minutes | If missing, require OIDC step-up |
| Finance A | Partner SAML | ClassRef in Partner strong allowlist | 5 minutes | If missing, SAML ForceAuthn + RequestedAuthnContext |
| Finance B | Corporate OIDC | May require a different level per Policy B | 5 minutes or stricter | Never reuse A's permissions or policy |
| Finance B | Unknown IdP | No contract/registration | N/A | Reject; never send arbitrary issuer/metadata requests |

**The broker must know the true upstream source.** Two partners emitting the same `acr` or SAML class string are not equivalent if their MFA verification, account recovery, or phishing-resistance procedures differ.

### 13.1. Preventing Account-Switching During Step-Up

Suppose account A holds an active session and begins approving an invoice. During the redirect round-trip, the OP lets the browser choose account B. If the app checks only high assurance and then finishes A's pending action, that is a vulnerability.

Proper sequence:

1. Before step-up, store a pending action server-side: `actorAccountId=A`, `tenantId`, `resourceId`, content hash/version of the transaction, CSRF/correlation, and a short expiration.
2. Initiate the OIDC/SAML request with protected `state`/`nonce` or Request ID/`RelayState`, linked to the pending action.
3. Receive the response and validate issuer, signature, audience, `nonce`/`state`, or SAML `InResponseTo`, timestamps, and replay.
4. Resolve the proven subject to the **exact same local account A** or an approved account-linking mechanism; **never** auto-link by email.
5. Check context + `AuthnInstant`/`auth_time`, issuer allowlist, policy version, and device/session relationship.
6. Re-verify tenant membership, role, and resource permissions at commit time.
7. Verify payload/amount/payee still match the approved transaction to prevent TOCTOU.
8. Consume the pending action once; prevent callback replay or duplicate approval.

### 13.2. "MFA Is Turned On at the IdP" Is Not Enough

An IdP may have a policy stating "all users must complete MFA at sign-in", yet the RP still needs to know:

- **Which IdP** issued the evidence and whether it belongs to the trust contract.
- **When the most recent MFA/reauth** occurred when an action requires freshness.
- That the OP/IdP did not silently downgrade via fallback methods, account recovery, or remembered devices.
- To block logins/assertions missing a policy-compliant context.
- To enforce business authorization independently.
- How to handle IdP outages, incomplete enrollment, or `NoAuthnContext` **without** dropping the requirement.

**Phishing-resistant** is a separate requirement from "has OTP". An `amr` value of `otp` does not prove phishing resistance; if policy requires FIDO/WebAuthn with proper `rpId`/origin/attestation checks or a specific AAL, establish an explicit OP/IdP agreement and evidence.

## 14. Negative Scenarios: Valid Claims Yet Policy Still Fails

| Signed/Verified Input | Scenario | Correct Outcome |
| --- | --- | --- |
| Valid OIDC ID Token, `acr=basic` | RP requires `high` | **Deny action**; step-up or reject |
| Valid OIDC ID Token, `amr=["mfa"]`, no `acr` | RP requires class `high` | Do not treat `amr` alone as sufficient |
| Valid OIDC ID Token, `acr=high`, `auth_time` 2 hours ago | Action requires fresh ≤5 minutes | Re-authenticate |
| Fresh OIDC ID Token with recent `iat` yet stale `auth_time` | Token minted via SSO | Never substitute `iat` for `auth_time` |
| OIDC request sent only `acr_values=high` | OP returns `acr=low` or omits `acr` | Evaluate response and fail closed |
| OIDC `prompt=login` | OP prompts for password re-entry without MFA | Still fails if action requires MFA |
| OIDC `max_age=300` | ID Token lacks `auth_time` | Response violates OIDC request; deny action |
| OIDC `prompt=none` | OP cannot satisfy assurance silently | Return error/interactive flow; never weaken policy |
| SAML `ForceAuthn=true` | IdP re-auths via password and returns basic context | Fails if action requires strong |
| SAML `RequestedAuthnContext exact strong` | IdP returns `NoAuthnContext` | Deny action; report unsupported cleanly |
| Stale SAML `AuthnInstant` | Strong `AuthnContext` class | Fails freshness |
| SAML context URI emitted by IdP B matches IdP A's URI | Mapping contract approves only IdP A | Do not trust IdP B automatically |
| SAML assertion fails signature/issuer/audience/recipient | Strong context URI | Reject before entering assurance policy |
| OIDC token from a different issuer than expected client | `acr=high` | Reject; never apply another issuer's mapping |
| Broker upstream SAML lacks context | Broker downstream emits `acr=high` | **Broker bug**; RP should not trust unsubstantiated mapping |
| Broker sets `auth_time=iat` fresh despite old upstream auth | Broken provenance/freshness | Must not count as fresh; fix broker |
| Step-up response authenticates account B | Pending transaction belongs to A | Reject; never auto-link by email |
| User completed step-up yet lost tenant access | Membership revoked | Deny action; assurance does not replace authorization |
| Different Session ID or replayed request | Broken correlation | Reject; do not permit action |

**Testing approach:** For SAML, have a test IdP issue and **validly re-sign** assertions carrying wrong contexts/instants to isolate the assurance validator—never just mutate raw XML and break signatures. For OIDC, have a test OP mint validly signed ID Tokens with varying `acr/amr/auth_time` to prove the application policy actually inspects them beyond signature verification.

## 15. Detailed Test Matrix for OIDC, SAML, and Brokers

### 15.1. OIDC Authorization Request

1. Perform normal login with test OP; capture browser Network **without pasting tokens into public tickets**.
2. Send `acr_values=contract-high`: verify the parameter is actually sent, accepted by the OP, and `acr` returns in the ID Token per test fixture.
3. Send `max_age=300`: OP returns `auth_time`, and RP checks authentication age in UTC.
4. Send `max_age=0` / `prompt=login`: verify re-authentication occurs per contract, rather than inferring from a fresh-looking screen.
5. Send `claims` Essential `acr` on a supporting OP: when the level cannot be met, the OP must not emit an accepted high result per policy.
6. Test `prompt=none` when the IdP session expired: handle error and interactive UI appropriately.
7. Test OP `amr` arrays per RFC 8176 or vendor claims; unknown values must never grant permissions automatically.
8. Test `state`/`nonce` and client/issuer/audience validation through Spring Security: any foreign/mismatched callback must fail.
9. Test a browser holding a valid local session when an action requires new step-up: the system must genuinely initiate a new OIDC flow rather than serving the logged-in page.
10. Test user switching accounts at the OP mid-flow: pending transaction for user A must never complete for B.

### 15.2. SAML AuthnRequest and Response

1. Verify `registrationId`, SP entityID, ACS URL, and IdP signing certificate from approved metadata.
2. When fresh auth is needed, verify `AuthnRequest` is generated with `ForceAuthn=true` (decoded XML in secure tests).
3. When strong context is needed, verify `RequestedAuthnContext Comparison=exact` and ClassRef matches the IdP-accepted URI.
4. Test request signing if required by the IdP: signature, Redirect/POST binding, and `Issuer` match.
5. Have test IdP return an `AuthnStatement` with strong context and fresh `AuthnInstant`: assurance policy allows (if all SAML validations pass).
6. Have test IdP return weak context and fresh `AuthnInstant`: deny action on level.
7. Have test IdP return strong context and stale `AuthnInstant`: deny on freshness.
8. Have IdP return `NoAuthnContext`: deny; never fall back to the basic session for high-risk actions.
9. Test `IsPassive=true` when interactive MFA is needed: handle failure rather than accepting silently.
10. Test signed assertions from an untrusted IdP or with wrong `AudienceRestriction`/`Recipient`/`InResponseTo`: must be rejected before reading assurance.
11. Test that SAML HTTP-Redirect `AuthnRequest` paired with HTTP-POST `SAMLResponse` works cleanly; binding does not dictate assurance.
12. Test SP sessions across a cluster, cookie SameSite, and request correlation; a lost session is no reason to disable `InResponseTo`.

### 15.3. Broker SAML → OIDC

1. Downstream RP requests strong `acr` and `max_age`; the broker must receive both properly.
2. Broker selects an approved upstream SAML IdP and knows the exact `ClassRef → downstream acr` mapping.
3. If an upstream session already exists, the broker knows when to send `ForceAuthn` for freshness/step-up.
4. Upstream assertion must have valid signature, issuer/audience/recipient/timestamps/correlation.
5. Broker checks `AuthnContext`/`AuthnInstant`, applies issuer/contract mapping, and rejects unapproved classes.
6. Broker **never** emits `amr` methods unsupported by upstream evidence.
7. Broker signs and issues an ID Token with the broker issuer, downstream audience/client, mapped subject, and `acr/auth_time`.
8. Downstream RP validates the ID Token, strength policy, and freshness—not just an SSO success redirect.
9. When upstream cannot satisfy context or lacks `ForceAuthn`, the broker never fabricates high `acr`.
10. When multiple tenants/IdPs share a ClassRef string, mapping remains isolated by source and `policyVersion`; never leak trust.
11. When step-up for account A returns a token for B, broker/RP must reject.
12. Test logout/SLO after step-up and local session expiry: an active browser session never implies assurance stays fresh forever.

## 16. Common Implementation Pitfalls and Fixes

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `acr_values` sent yet ID Token lacks `acr` | Voluntary request only; OP omitted or policy unsupported | Confirm OP contract; use Essential `acr` if available; inspect response and fail closed |
| RP receives `acr=2` without knowing what level it means | Vendor-defined value lacking per-issuer mapping | Agree on semantics, assurance profile, and source allowlist |
| `amr=["mfa"]` yet RP still rejects | Policy requires specific `acr` or fresh auth, not methods alone | Check strength/time; never derive roles from `amr` |
| OP `prompt=login` shows no MFA | Re-authentication does not imply strong auth | Add `acr`/IdP method policy and verify result |
| `max_age` set yet ID Token omits `auth_time` | OP non-compliant or config inactive | Check version/discovery/authorization URI; deny action |
| After fresh login, `auth_time` remains old | OP reused session or broker failed to propagate reauth | Check OP logs/contract, `prompt`, upstream `ForceAuthn`; never use `iat` |
| SAML `ForceAuthn=true` still skips password prompt | IdP used another interactive method, ignored it, or session behavior | Check IdP policy, `AuthnInstant`, and context; fail action if unmet |
| SAML `RequestedAuthnContext` returns `NoAuthnContext` | IdP rejects URI/comparison or policy insufficient | Pick supported class per contract; never strip requirement to allow action |
| Strong SAML context yet stale `AuthnInstant` | Step-up did not trigger a new authentication event | Re-auth via proper flow; verify authentication time |
| Spring OIDC app skips re-login when visiting `/approve` | Local `HttpSession` is still authenticated | Build explicit step-up entrypoint/authorization flow with correlation |
| Spring SAML resolver sets `ForceAuthn` yet custom class is missing | `RequestedAuthnContext` not set with matching OpenSAML builder | Customize per version; verify `AuthnRequest` XML in tests |
| Broker emits downstream `acr=high` despite basic upstream | Overbroad mapping, missing origin check, or dangerous fallback | Exact issuer/class/freshness allowlist and provenance audit |
| RP reads `amr` from UserInfo when absent in ID Token | OP emits `amr` elsewhere or claims lack a contract | Use only approved sources, match `sub`, never trust arbitrary UserInfo strings |
| Infinite OIDC login loop | OP always returns a lower class than policy requires | Stop loop cleanly; report IdP policy mismatch |
| `auth_time` skew from NTP | OP/RP clock drift | Sync UTC/NTP; bounded skew instead of infinite |
| Browser switches account during step-up | OP account chooser selected a different subject | Match issuer+subject/localAccountId with pending transaction |
| MFA present yet transaction still denied | User lacks role/tenant permission or authorization policy | Inspect authorization/business rules separately |
| SAML filter errors before assurance check | Assertion fails signature/audience/recipient/`InResponseTo` | Fix federation config; never disable SAML validation |
| Same SAML `AuthnContextClassRef` across multiple IdPs | Matched by URI alone without distinguishing issuer | Map by issuer + URI + contract version |
| Reading `iat` to compute freshness | Confused token issuance time with authentication time | Use `auth_time`/`AuthnInstant` verified by source |
| "Spring logged in so high assurance is met" | Spring SSO validation knows nothing of domain action policies | Add assurance enforcement in services/before protected actions |

### 16.1. Debugging by Root-Cause Order

```text
1. Was SAML/OIDC evidence verified for issuer, key, audience,
   nonce/state or InResponseTo, Recipient/Destination, and timestamps?
2. Did the request actually send ForceAuthn/RequestedAuthnContext
   or acr_values/claims/max_age/prompt over the wire?
3. Did the provider re-authenticate or reuse a session?
4. Which context and auth time did the ID Token/AuthnStatement report?
5. Is that URI/context in the mapping for that exact issuer?
6. Is freshness still valid against UTC clock and action policy?
7. Does the post-step-up subject match the original account/pending action?
8. Is the user authorized on that tenant/resource/transaction?
9. Did the broker distort provenance or silently downgrade?
10. When high assurance cannot be met, does the app fail closed and stop loops?
```

Never enable debugging by logging full ID Tokens, cookies, `SAMLResponse`, or private keys in production. In labs, decode for inspection while outputting only non-sensitive/summary fields, and purge logs/test artifacts per policy.

## 17. Self-Check Questions

**Q1.** An OIDC OP returns an ID Token with `acr=high`, `amr=["pwd","otp"]`, recent `iat`, yet `auth_time` is one hour ago. The app requires freshness within 5 minutes. Is it satisfied?

**Answer:** No. Strength/`amr` cannot compensate for staleness; check verified `auth_time`, not `iat`.

**Q2.** A SAML SP sends `ForceAuthn=true`. The IdP re-authenticates with password and returns `AuthnContextClassRef=PasswordProtectedTransport`; the business action requires a specific strong class. Can the action proceed?

**Answer:** No, if the returned class is not in the policy for that action. `ForceAuthn` requests only re-authentication and does not guarantee strong methods.

**Q3.** The RP sends `acr_values=strong` and the OP omits `acr`. Can the RP assume the OP complied because no error occurred?

**Answer:** No. `acr_values` is voluntary. Inspect the ID Token and use Essential `acr`/contracts when mandatory, or fail closed.

**Q4.** A broker receives SAML class `urn:example:contract:partner:strong-v1` from issuer A and issuer B; only A has a strong-assurance contract. Can both map to OIDC high?

**Answer:** No. Mapping must key on **issuer + class + contract**, not class string alone.

**Q5.** Is OIDC `amr=["mfa"]` enough to infer phishing-resistant WebAuthn across every policy?

**Answer:** No. `mfa` states generally that multiple factors ran per OP, without confirming factor type, FIDO/WebAuthn evidence, or anti-phishing guarantees.

**Q6.** The OP holds an SSO session; the RP sends `prompt=none` while needing interactive UI step-up. The OP returns `interaction_required`. What should the RP do?

**Answer:** Launch an allowed interactive flow (`prompt=login`/`max_age` and `acr` policy), or deny with a clear message; never approve silently on the weak session.

**Q7.** After step-up, the client switches to account B at the OP. Can the system use B's strong assurance to approve the pending transaction created by account A?

**Answer:** No. Bind subject/local account, tenant, session, correlation, and transaction before committing.

**Q8.** Spring Security `oauth2Login()` and `saml2Login()` ran cleanly; does that mean `acr` and `AuthnContext` map automatically to app roles?

**Answer:** No. The framework authenticates the protocol; per-action assurance and tenant permissions are separate policies that require explicit enforcement.

## 18. Production Deployment Checklist

- [ ] Define **authentication strength**, **freshness**, and **business authorization** separately—never collapse them into one `isMfa` flag.
- [ ] Every IdP/OP/broker has an approved issuer/registration, key/metadata trust, and authentication context contract.
- [ ] SAML `AuthnStatement` `AuthnContextClassRef` / `AuthnInstant` are read only after assertion signature, issuer, audience, recipient, and `InResponseTo`/replay pass validation.
- [ ] OIDC `acr/amr/auth_time` are consumed only from ID Tokens validated for `iss/aud/signature/nonce/state/exp` per flow.
- [ ] `acr_values` is treated as voluntary; when exact assurance is required, use OP-supported mechanisms and check returned `acr`/Essential claims.
- [ ] `amr` is evaluated against RFC 8176/issuer contracts; never treat `mfa` or `otp` as satisfying every security level or phishing resistance.
- [ ] `auth_time`/`AuthnInstant` govern freshness; never substitute `iat`/`IssueInstant` or web session creation time.
- [ ] SAML `ForceAuthn` and `RequestedAuthnContext` are wired properly with IdP-supported `Comparison`/classes and `NoAuthnContext` handling.
- [ ] OIDC `prompt=login`/`max_age` are configured in explicit step-up flows when needed with spec-compliant error handling.
- [ ] Brokers maintain an allowlist mapping **issuer + class/acr + version**, preserve provenance, and never emit downstream assurance higher than real evidence.
- [ ] If a broker receives `prompt=login`/`max_age=0`, it genuinely re-authenticates upstream or fails closed.
- [ ] Never emit fabricated `amr` or set `auth_time=iat` when upstream authentication occurred earlier.
- [ ] Step-up flows enforce CSRF, `state`/`nonce` or SAML `InResponseTo`, session correlation, replay protection, and single-use pending transactions.
- [ ] Post-step-up, the subject remains the same local account; tenant, permission, resource, and amount/payee/operation are re-verified at commit.
- [ ] Never redirect in a loop when an IdP lacks the required level; block the action and surface diagnosable errors.
- [ ] App session/logout, OP SSO, and MFA age are tracked independently; an active session never keeps evidence fresh indefinitely.
- [ ] Synchronize UTC/NTP clocks with tight clock-skew policies; never loosen timestamp checks to pass QA.
- [ ] Tests include validly signed ID Tokens/SAML assertions carrying wrong contexts/freshness to isolate assurance validators.
- [ ] Never put private keys, raw `SAMLResponse`, ID Tokens, OTPs, session cookies, or sensitive data into logs/tickets.
- [ ] Audit logs record minimal required details: policy ID, verified issuer, context decision, freshness, tenant, and business action.

**Conclusion:** In SAML, `AuthnContext` describes the achieved class/context, `RequestedAuthnContext` requests a class, `ForceAuthn` requests re-authentication, and `AuthnInstant` records authentication time. In OIDC, `acr` describes the class, `amr` describes the methods, `auth_time` records authentication time, while `acr_values`/Essential `acr`, `max_age`, and `prompt=login` are ways to **request** strength and freshness with distinct semantics. When an identity broker is involved, **never translate claims by naive string matching or inflate MFA**; preserve provenance and evidence, map per contract, verify freshness, and enforce authorization on the final action.

## 19. References

1. [OpenID Connect Core 1.0 – Authentication Request, `acr`, `auth_time`, `max_age`, `claims`](https://openid.net/specs/openid-connect-core-1_0.html): defines claims, `prompt`/`max_age`/`acr_values` parameters, Essential ACR, and RP validation rules.
2. [IETF RFC 8176 – Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176.html): standardized `amr` strings such as `pwd`, `otp`, `mfa`, `hwk`, `fpt`.
3. [IANA – Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/): current AMR registry and governing authorities.
4. [OASIS SAML 2.0 Core – Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `AuthnStatement`/`AuthnContext`, `RequestedAuthnContext`, `ForceAuthn`/`IsPassive`, `NoAuthnContext`.
5. [OASIS SAML 2.0 AuthnContext](https://docs.oasis-open.org/security/saml/v2.0/saml-authn-context-2.0-os.pdf): authentication context classes and terminology.
6. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, `AuthnRequest`/Response, correlation.
7. [Spring Security – Producing SAML AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): OpenSaml authentication request resolver, `ForceAuthn` customizer, request storage.
8. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validating `SAMLResponse`/Assertion and provider extension points.
9. [Spring Security – OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `DefaultOAuth2AuthorizationRequestResolver` and adding OIDC authorization parameters.
10. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): custom authorization endpoint/authorization request resolver.
11. [Spring Security API – IdTokenClaimAccessor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html): `getAuthenticationContextClass()`, `getAuthenticationMethods()`, and `getAuthenticatedAt()`.
12. [Microsoft Entra – SAML protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): provider-specific example, including `RequestedAuthnContext Comparison` support and limits.
