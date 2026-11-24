# Boundaries for Propagating Authentication Assurance, Attributes, and Permissions Across Multiple Federation Hops

In an **OpenID Connect (OIDC) and identity brokering** architecture, a user may authenticate at a corporate IdP, pass through one or more **identity brokers**, and sign into a Java/Spring Security application. Along the way, each tier may convert a SAML assertion into an OIDC ID Token, swap issuers/subjects, refresh tokens, normalize user groups, or mint access tokens for APIs. Those transformations add convenience yet also introduce **trust boundaries**: authentication assurance, profile attributes, and access permissions in system A **do not automatically carry the same meaning or scope in system B**.

For example, the upstream IdP only proves the user signed in with a password, yet a downstream broker emits an ID Token carrying `acr=urn:enterprise:mfa` without performing another factor. A finance application trusting that string to approve a large transfer has **unjustifiably elevated assurance**. Or the upstream IdP sends `groups=["admins"]`, the broker copies it into `roles=["ADMIN"]`, and the application creates `ROLE_ADMIN` automatically—resulting in **privilege escalation via claim mapping**.

This lesson answers five questions:

1. How can **authentication assurance** (`acr`, `amr`, `auth_time`, SAML `AuthnContext`) be preserved, downgraded, or legitimately upgraded across a broker?
2. How can **identity attributes** (`sub`, NameID, email, groups, department, tenant) lose their origin, freshness, or meaning at each hop?
3. How do **application/API permissions** differ from IdP groups, OAuth scopes, and broker-issued tokens?
4. How do you build a **trust contract**, transformation policy, **step-up**, and **deny by default** across a multi-tier federation chain?
5. How can Spring Security and Java 17 enforce and test those boundaries without dropping default OIDC/SAML validation?

**Guiding principle:** never claim higher assurance by renaming a claim; never "pass through" data lacking a semantic contract; never grant permissions from upstream groups or a merely valid JWT; **each hop validates its inputs, issues outputs under its own policy, and the final RP enforces admission and authorization independently**.

## 1. Architecture Model: Multi-Hop Federation Is Not an Automatic Chain of Trust

~~~text
                 TRUST HOP 1                TRUST HOP 2                TRUST HOP 3
+-----------+   SAML/OIDC     +-----------+  OIDC downstream +---------+ OIDC/API +--------+
| Origin IdP| --------------> | Broker A  |----------------->|Broker B |--------->| RP/API |
| Employees |                 | RP or SP  |                  | OP / AS |          | Portal |
+-----------+                 +-----------+                  +---------+          +--------+
    |                             |                               |                   |
    | SAML AuthnContext           | verify signature/conditions   | verify broker A   | verify B issuer,
    | or OIDC acr/amr             | map identity+assurance        | map+mint tokens   | audience, time
    | auth_time, attributes       | issue new token               | choose claims     | local account,
    |                             |                               |                   | permissions
    +-----------------------------+-------------------------------+-------------------+
       "Having a signature at each hop" does NOT mean contents and permissions keep their semantics.
~~~

Each relationship has its own **issuer**, **audience/client**, signing keys, claim schema, intended purpose, auditability, and policy.

- When **Origin IdP → Broker A** is SAML, Broker A is a **SAML Service Provider**: it must validate signature, issuer, audience, destination/recipient, conditions, subject confirmation, `InResponseTo`, and replay resistance.
- When **Broker A → Broker B** is OIDC, Broker A is an **OpenID Provider (OP)** for Broker B: Broker B validates an ID Token issued **specifically for Broker B's `client_id`**.
- When **Broker B → Portal** is OIDC, Broker B can mint a **new ID Token** with B's `iss`, `sub` per B's rules, and `aud` for the Portal.
- The Portal **does not receive signed evidence directly from the Origin IdP** unless a broker supplies a separately verifiable provenance mechanism. The Portal trusts **Broker B per contract**, never assuming B and every upstream system share identical assurance.

**A signature proves the issuer signed the claim, not that the claim was soundly derived from upstream.** A validly signed broker token can still carry a semantically false `acr` if the broker's mapping/policy is misconfigured. The RP must evaluate both cryptographic trust **and** semantic trust.

### 1.1. Four Categories of Evidence That Must Never Be Conflated

| Evidence or Decision | Question Answered | Typically Responsible Component |
| --- | --- | --- |
| **Authentication event** | How and when was the user authenticated? | The IdP/OP that actually authenticated, or the broker if it performed step-up. |
| **Identity attributes** | Where did email, department, employee ID, and groups come from, and are they fresh and trustworthy? | Attribute sources (IdP, HR, SCIM, directory) and broker mapping. |
| **Application admission** | Is the user permitted into this app, unlocked/enabled, and in the right tenant? | Local RP/application. |
| **Resource authorization** | May this session perform `approve:payment` on transaction X? | API/resource server and business policy. |

A claim `amr=["pwd","otp"]` **does not grant** `finance:approve`. A claim `department="Finance"` does not prove the user is an appointed approver. An access token with `scope=read` does not necessarily allow reading documents across every tenant.

## 2. Three Axes of Assurance: Authentication, Identity, and Federation Protection

In federated architectures, **assurance level** is not a single number you add or subtract across brokers. There are at least three dimensions:

| Dimension | What Must Be Proven? | Example Limit |
| --- | --- | --- |
| **Authentication Assurance (AAL)** | Which quality/authenticator did the user authenticate with per policy? | A single password cannot be relabeled MFA merely by translating SAML to OIDC. |
| **Identity Assurance (IAL)** | Confidence in proofing and binding the identity to a real person. | Strong MFA does not itself prove legal name or identity proofing was performed. |
| **Federation Assurance (FAL)** | How strongly the federation transaction protects assertions, audience, replay/injection, and trust agreements. | An MFA login does not automatically ensure tokens at every hop resist injection/replay. |

The terms **IAL/AAL/FAL** are distinguished in **NIST SP 800-63**. They may be claimed only when the system satisfies all corresponding rules and trust agreements; **never mechanically translate `acr="mfa"` into "NIST AAL2" or "FAL2"**.

Examples:

- An origin IdP authenticating with a phishing-resistant authenticator produces a strong authentication event; yet if Broker A validates a SAML assertion with weak audience/correlation settings, that federation hop still carries risk.
- A user passed thorough HR identity proofing, yet their latest login used only a password; high IAL **never elevates** AAL.
- A broker mints a fresh token two hours later without re-authenticating the user; the new token's `iat` **does not turn an old `auth_time` into fresh**.

When a business rule demands "payments require MFA within 5 minutes", define **method strength, freshness, trusted source, and per-hop integrity**. You cannot inspect only an `acr` field and ignore the rest.

## 3. OIDC: Exact Meanings of acr, amr, auth_time, and Step-Up Requests

### 3.1. Core Claims

| OIDC Claim | Meaning | Limits Across a Broker |
| --- | --- | --- |
| **`acr`** | Authentication Context Class Reference: class/context name asserted satisfied by the OP. | Class names **have no global scale**; require agreed semantics, mapping, and evidence. |
| **`amr`** | Authentication Methods References array describing methods used. | Detail can be lost in mapping; `["mfa"]` does not prove phishing resistance. |
| **`auth_time`** | Time when **the user actually authenticated** (Unix seconds). | Must not be replaced by token issuance time if the broker merely reused an SSO session. |
| **`iat`** | Time **the token was issued**. | A fresh token with recent `iat` can still rest on a stale `auth_time`. |
| **`max_age`** (request) | Maximum acceptable age of authentication requested. | Broker must enforce or ensure upstream enforces; RP verifies `auth_time`. |
| **`acr_values`** (request) | Preferred authentication classes in priority order. | Per OIDC Core, this is a **voluntary request**, not guaranteed to succeed. |
| **`claims` requesting essential `acr`** | Demands mandatory `acr` claim matching accepted values when supported by the OP. | OP must satisfy per spec if supported; RP must still verify token and policy. |
| **`prompt=login`** | Instructs the OP to require the user to re-authenticate. | **Does not itself prove MFA**; verify how OP handles it and inspect returned claims. |
| **`nonce`, `state`** | Binds transaction/token to the request; prevents substitution/CSRF. | Conveys nothing about strength/MFA; still required across brokers. |

OIDC Core states that `acr` is a string whose semantics are agreed between parties and **is not required** in every ID Token. `amr` may also be absent. A value like `urn:corp:aal-high` has meaning only when **the issuer is trusted** with a concrete policy definition; never treat a longer string or the word "high" as stronger proof.

### 3.2. Example Tokens for One Person at Two Timestamps

The user's actual authentication happened at 08:00 UTC, while the broker minted a token for the Portal at 09:30 UTC:

~~~json
{
  "iss": "https://broker.example.org",
  "sub": "pairwise-user-81",
  "aud": "portal-web",
  "iat": 1794043800,
  "exp": 1794044100,
  "auth_time": 1794038400,
  "acr": "urn:corp:password",
  "amr": ["pwd"]
}
~~~

This is an **illustrative payload, not a signed JWT**; timestamps merely illustrate fields and must not be used as real test tokens. In a real transaction, `auth_time` must reflect the corresponding event per the OIDC contract, never copying `iat` just to make a token "look fresh".

If the transaction hops across two brokers:

~~~text
IdP      authenticates at 08:00 UTC with password
Broker A verifies at 09:20 UTC, mints new token at 09:20
Broker B receives token at 09:25 UTC, mints new token at 09:30
Portal   receives Token B at 09:30

No new authentication step:
  originating auth event time = 08:00 UTC
  downstream issuance time    = 09:30 UTC
  requirement "MFA within 5 minutes" => NOT SATISFIED
~~~

If Broker B **genuinely conducts step-up** with a new recognized policy authenticator, B creates a new authentication event and matching claims, yet must **accurately record that event's method, subject binding, and assurance level**. B must never elevate strength merely via `claims.put("acr","mfa")`.

### 3.3. Requesting Step-Up from RP to Broker

Suppose the Portal requests MFA using an agreed semantic class:

~~~text
GET https://broker.example.org/authorize?
    response_type=code
    &client_id=portal-web
    &scope=openid
    &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
    &state=<opaque-state>
    &nonce=<opaque-nonce>
    &code_challenge=<S256-challenge>
    &code_challenge_method=S256
    &acr_values=urn%3Acorp%3Amfa
    &max_age=300
~~~

Values inside `<...>` are placeholders for secret/random transaction data, not a runnable login URL. The client must use **Authorization Code + PKCE**, store state/nonce/verifier per transaction, check redirect URIs, and follow standard OIDC rules.

**`acr_values` alone is a voluntary request.** If the Portal requires a hard `acr` condition, OIDC supports a `claims` request with `id_token.acr` set to `essential=true` and `values` when the OP supports it. Even then, the RP must still **verify the final `acr`**, `auth_time`, issuer, audience, signature, and expiry—never treat sending the request as proof step-up succeeded.

Example `claims` structure:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": ["urn:corp:mfa"]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Never arbitrarily mix `acr_values` and `claims.id_token.acr` with `values` in the same request and guess the outcome; OIDC Core notes combined behavior is **unspecified** in some cases. Pick a mechanism supported by your OP/broker and test that exact configuration.

### 3.4. Step-Up Is a Decision at Resource-Usage Time

Suppose a user signed into the Portal to view a dashboard and then clicks "Approve payment". Not every page needs MFA, yet the payment approval endpoint must enforce:

1. **Identity authenticated** via trusted issuer/audience/nonce/signature.
2. **Effective assurance satisfies the mandatory class** per trust contract.
3. **Authentication freshness** meets the bound, e.g., `now - auth_time <= 300 seconds`.
4. **Authorized business permissions** such as `payments:approve` with exact limits, user status, and tenant.
5. **Replay and CSRF protection** on the approval transaction; never allow a POST solely based on `acr`.

If the token omits `auth_time` or the broker cannot confirm upstream MFA, the app can trigger a step-up flow or deny. **Never default "missing claim means strongest method"**. Step-up cannot cure missing permissions: a user with MFA still cannot approve payments without `payments:approve`.

## 4. SAML 2.0 on the Upstream Hop: RequestedAuthnContext Is Not a Certificate of Achieved Strength

When a broker accepts upstream SAML, an `AuthnRequest` can request an authentication class via `RequestedAuthnContext`:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-701"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/sso"
    ForceAuthn="true">
  <saml:Issuer>urn:example:sp:broker-a</saml:Issuer>
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef>urn:example:authn:mfa</saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

This XML is **abbreviated to teach structure**, not a complete/signed request for a live federation. `urn:example:authn:mfa` is a **contract-specific custom class**, not a standard SAML class universally understood by all IdPs. `ForceAuthn="true"` asks the IdP to re-authenticate rather than relying on an existing session per profile; **it does not create MFA itself** unless the right class is requested and verified. Both the class ref and `ForceAuthn` must be verified against live IdP behavior.

SAML Core defines `RequestedAuthnContext` with `Comparison` values `exact`, `minimum`, `maximum`, and `better` (`exact` is the default); comparison depends on **semantics/ordering** between authentication classes understood by both parties. Never guess which class is "better" by comparing URI strings lexicographically.

**The post-authentication source of truth** is `AuthnStatement/AuthnContext` and validated fields of the assertion—not whatever parameters the broker sent in `AuthnRequest`.

### 4.1. What Must Be Verified Before Translating SAML → OIDC

| Upstream SAML Element | Broker Verification / Interpretation | Downstream OIDC Output |
| --- | --- | --- |
| `Issuer`, signature, trust credential | Exact registered IdP for this transaction; signature over exact consumed node. | Enables broker to sign its own ID Token. |
| `AudienceRestriction` | Assertion targets **Broker SP**, not downstream Portal. | Broker issues **new `aud` = Portal `client_id`**. |
| `Destination`, bearer `Recipient`, `InResponseTo` | Matches ACS and SSO transaction; defeats assertion injection. | Never copy these values verbatim into downstream tokens. |
| `Subject/NameID` | Subject per format/qualifiers and issuer; trusted mapping. | Broker-issued `sub`, potentially pairwise; never assume equal to NameID. |
| `AuthnStatement/AuthnContextClassRef` | Achieved level per specific IdP contract. | Map to `acr` **only if mapping is approved**. |
| `AuthnStatement@AuthnInstant` | Authentication timestamp declared by the IdP. | `auth_time` only if aligned with contract and trusted source. |
| Other authentication methods/profiles | Not every SAML response carries an OIDC `amr` equivalent. | Never invent `amr=["mfa"]` without sufficient evidence. |
| `Conditions/NotOnOrAfter` | Validity window for using the upstream SAML assertion. | Never copy that window as downstream session/token lifetime. |

**Protocol translation must never whitewash upstream properties.** If Broker A has no contract stating `AuthnContextClassRef=X` means phishing-resistant MFA, Broker A can record only "upstream asserted class X"; it must never promote X to a higher class based on similar naming. If upstream provides no verifiable context, downstream assurance must fall back to **unknown/baseline** per policy or require step-up.

## 5. The "Claim Provenance" Model: Where Did an Attribute Come From, When, and With What Meaning?

A federated system does more than rename fields. Every business claim has at least **source**, **semantics**, **subject**, **scope**, **update timestamp**, and **verification method**.

For instance, `department="Finance"` could come from:

- HR master data maintained, verified, and synced by HR to the broker.
- IdP `groups` inferred into departments via a mapping rule.
- Self-edited `preferred_username` or user profile fields.
- An `X-Department` header forwarded by an unprotected proxy.
- A 7-day-old cache from a stalled sync job.

These sources are **not equivalent** for granting financial approval rights.

### 5.1. Attribute Quality Check Table

| Attribute | Purpose-Fit Trusted Source | Limits to Record |
| --- | --- | --- |
| `sub` / subject | Specific issuer, verified signature/token, and account link. | **Unique only within issuer namespace**; may be pairwise across clients. |
| `email` | OP/IdP provided, optionally with `email_verified`. | Mutable/recyclable; neither an account primary key nor permission proof. |
| `name`, `preferred_username` | Directory/profile for display. | Never use for identity binding or permissions. |
| `employee_id` | HR or source contracted for uniqueness and status. | May be sensitive and vary by organization/tenant. |
| `department` | HR/SCIM/directory with provenance and freshness timestamp. | Not automatically an entitlement. |
| `groups` | Curated group catalog per issuer/tenant. | Group names can collide, be missing, or go stale; never convert straight to roles. |
| `tenant_id` | Mapping from administrative source and linked identity. | Never trust query params/`RelayState` to pick tenants. |
| `role`, `entitlement` | App admin/approval or explicit delegation contract. | Must carry app/resource scope and validity lifetime. |
| `acr` / `amr` | Authentication event verified by the responsible party. | Never infer from email, groups, or token signing algorithm. |
| `auth_time` | Authentication event attested by OP/broker per contract. | Never replace with `iat` to fake freshness. |

If the broker merges claims from multiple sources, define **source precedence and conflict rules**: for example, a local app `DISABLED` status overrides an `active-users` group sent lazily by an IdP. **Never pick "whichever value looks strongest"** across multiple claims while dropping provenance, since an attacker may control a lower-trust source.

### 5.2. Internal Envelope with Provenance, Not a Standard JWT

An architectural model for the broker (this is an **illustrative schema**, not a standard OIDC claim):

~~~json
{
  "effective_subject": "broker-user-42",
  "source_authentication": {
    "upstream_issuer": "urn:example:idp:employees",
    "upstream_subject_ref": "idp-subject-key-77",
    "upstream_protocol": "SAML2",
    "validated_at": "2026-11-07T03:00:00Z",
    "auth_time": "2026-11-07T02:58:00Z",
    "source_context": "urn:example:authn:password",
    "mapped_assurance": "urn:corp:password",
    "mapping_policy_version": "assurance-v7"
  },
  "attributes": {
    "department": {
      "value": "Finance",
      "source": "HR_DIRECTORY",
      "updated_at": "2026-11-06T08:00:00Z"
    }
  },
  "local_account_status": "ACTIVE"
}
~~~

The broker stores this envelope **in a trusted, controlled store** to drive downstream claim decisions and auditing. It is neither necessary nor **advisable** to dump full provenance or sensitive source subjects into ID Tokens for every RP. If an enterprise needs RPs to verify provenance independently, design a **signed claim contract with audience, consent/minimization, key management, and semantic standardization**—never assume arbitrary custom JSON becomes trustworthy just by sitting inside a token.

**Every time the broker mints a token**, decide which fields are allowed to cross the boundary. Attributes that are stale, unknown, or unpermitted for sharing are **omitted or marked "unknown"**, never defaulted to authorized.

## 6. Passing Subjects Across Multiple Brokers: Never Link Accounts by Email Alone

A subject at a SAML IdP may be a persistent `NameID` with qualifiers; Broker A emits its own `sub`; Broker B emits a pairwise `sub` for the Portal.

~~~text
SAML IdP        issuer = urn:example:idp:employees
                NameID = permanent-77 (scoped by IdP/SP)

Broker A OIDC   issuer = https://broker-a.example.org
                sub    = a-user-123

Broker B OIDC   issuer = https://broker-b.example.org
                sub    = pairwise-for-portal-9

Portal binding  (https://broker-b.example.org, pairwise-for-portal-9)
                -> local user-42
~~~

OIDC `sub` is **not globally unique**. The **`iss` + `sub`** pair identifies the subject within that trust relationship. Seeing the same email at Brokers A and B does not mean the two accounts should merge. If Broker B's pairwise subject changes because a client/sector identifier changed, the Portal needs a governed re-linking workflow—never fall back to `email` or `preferred_username`.

**Confused deputy risk:** a broker receives an assertion meant for client A yet issues a token to client B because routing relied on query params or `login_hint` without transaction binding. Pin client/registration/issuer/audience, protect `state`/`nonce`, check `InResponseTo` when upstream is SAML, and never let self-asserted inputs pick the trust anchor.

## 7. Permission Propagation Limits: Group, Role, OAuth Scope, and API Permission Are Four Different Things

| Data | Semantics | Must Never Be Assumed Equivalent To |
| --- | --- | --- |
| IdP `groups` | Membership in one or more groups **within that IdP/tenant**. | `ROLE_ADMIN` across all applications. |
| Broker `roles` | Roles published by the broker per realm/client policy. | Access to all business resources at the RP. |
| OAuth `scope` | Permissions granted by the AS to **an access token** per client, user, audience, consent, and policy. | Proof the user holds an HR role, or that other APIs will accept it. |
| App `GrantedAuthority` | Authority placed by Spring Security onto the app's `Authentication`. | Permission bypassing tenant, ownership, or specific resource checks. |
| App `permissions`/entitlements | Privileges approved for **app/resource/action/tenant**. | Assurance/MFA, identity proofing, or privileges in another app. |
| OAuth token-exchange `act` | Describes actor/delegation in a token-exchange context (if used). | Replacing subject authentication or automatically widening privileges. |

A group `finance-admin` at IdP-X does not necessarily equal `finance-admin` at IdP-Y. If a broker strips namespaces and maps both to `ROLE_FINANCE_ADMIN`, one tenant can accidentally gain rights in another tenant.

### 7.1. Controlled Permission Mapping Pattern

Example **business entitlement map**:

~~~text
(trustedIssuer = IdP-X,
 tenant = tenant-A,
 groupId = 6f4a-...,
 approvedMapping = v12)
     -> suggest role app:finance-viewer

LocalAppPolicy:
  localAccount.status == ACTIVE
  localAccount.tenant == tenant-A
  localAccount.entitlements contains payments:approve
  transaction.amount <= approvedLimit
  effectiveAssurance >= requiredAssurance
  authenticationAge <= requiredAge
  => ALLOW approval

If any condition fails => DENY or STEP-UP per policy.
~~~

Upstream groups are only a **signal** that may assist role assignment if the contract permits; final decisions belong to admins/SCIM/HR and app policy. High-risk roles (user admin, payment approval) usually warrant **explicit local approval/entitlements** and revocation workflows.

**Deny always takes precedence**: a local account that is `LOCKED`, `DISABLED`, license-revoked, outside the tenant, or permission-revoked **must never be reopened** simply because an upstream token still carries an old group.

### 7.2. Avoiding Audience Confusion Between ID Tokens and Access Tokens

Suppose Broker B issues an ID Token for the Portal:

~~~json
{
  "iss": "https://broker-b.example.org",
  "sub": "pairwise-for-portal-9",
  "aud": "portal-web",
  "acr": "urn:corp:password",
  "auth_time": 1794038400
}
~~~

While Reports API expects an access token:

~~~json
{
  "iss": "https://broker-b.example.org",
  "sub": "pairwise-for-api-9",
  "aud": "reports-api",
  "scope": "reports:read",
  "exp": 1794044100
}
~~~

These are **simulated payloads**, not valid JWTs or a guarantee that every OP issues distinct `sub` values across ID Tokens and access tokens. They illustrate **each token's audience** and API policy. **Never send the Portal's ID Token to an API**; the resource server must validate signature, issuer, expiration, **audience**, scope/permission, and tenant. Never forward an upstream access token issued for Broker A to a downstream API merely because both happen to be JWTs.

### 7.3. Delegation and OAuth Token Exchange

When Backend A calls Backend B **on behalf of a user**, that is **delegation**, not merely OIDC login. **RFC 8693 OAuth 2.0 Token Exchange** describes how a client requests another security token using `subject_token`, `actor_token`, `audience`/`resource`, and `scope` per AS capability. Claims `act` and `may_act` represent actor/delegation chains in applicable profiles.

Example:

~~~text
User -> Portal (OIDC Login)
Portal -> Authorization Server (token exchange, if supported)
      subject_token = token trusted by AS
      requested audience = reports-api
      requested scope = reports:read
AS -> Portal: access token for reports-api
Portal -> Reports API: Bearer access token
Reports API: check iss, aud, exp, scopes, tenant, resource
~~~

Successful token exchange **does not mean the AS grants every scope**; only privileges permitted by policy, subject, client, and consent are issued. `act` identifies the actor in supporting systems—it is **not step-up MFA proof**. Never grant broader permissions simply because the broker signed a new token; **least privilege and audience restriction** apply at every API.

## 8. Principles for Preserving Invariants and Preventing Escalation at Every Hop

### 8.1. Invariant 1: A Hop Cannot Fabricate Higher Assurance

If an upstream hop proved only `PASSWORD`, a **plain token translation** must never emit `MFA` merely because a role or attribute name sounds strong. Claiming a higher level requires a **genuine additional authentication event** satisfying policy rules.

**There is no universal `max(acr_A, acr_B)` across issuers.** If no mapping is configured, the result must be **UNKNOWN** or a contracted baseline—never guess `LOW < MEDIUM < HIGH` from string names.

### 8.2. Invariant 2: Freshness Does Not Refresh on Token Re-Issuance

Brokers A and B may update `iat` whenever issuing a token, yet without re-authentication the **underlying `auth_time` event does not become newer**. If a valid step-up occurs and the broker emits a newer `auth_time`, record that new event and which issuer/OP proved it. Never accidentally treat a refresh token issuance timestamp as an MFA timestamp.

### 8.3. Invariant 3: Attributes Carry Provenance and Intended Purpose

If downstream needs `department` for UI display, a profile source may suffice; if needed to approve payments, require a trusted HR/entitlement source, freshness, and ownership. **A broker's signature over a copied claim does not make the originating data source trustworthy.**

### 8.4. Invariant 4: Permissions Are Namespaced, Scoped, and Deny-Precedent

An `admin` role from a Partner IdP is not automatically `app:admin`; `read` scope for service A does not grant service B; tenant A has no privileges in tenant B. Downstream permissions must be **explicitly allowed** by mappings and local policy, never taking the union of all groups/roles across hops.

### 8.5. Invariant 5: Every Hop Issues Tokens for the Exact Target Audience and Validates Transactions

When Broker A receives a SAML assertion addressed **to Broker A**, the Portal must never consume that assertion directly. When Broker B mints an ID Token, the Portal must verify `iss`, `aud`, signature/JWKS, expiration, `nonce`, and `state`/transaction correlation. Even a valid upstream token **lacks the downstream audience**.

### 8.6. Invariant 6: Policies Must Handle UNKNOWN Explicitly

Never adopt fallbacks like `missing acr -> treat as MFA`, `missing groups -> admin`, `userInfo unavailable -> assume active`, or `broker timeout -> accept last elevated token`. Missing sources, undefined claims, unmapped contexts, or stale attributes exceeding SLA must produce **step-up, deny, or pending** per business rules—never fail open.

## 9. Trust Contract for Each IdP–Broker and Broker–RP Pair

A minimal technical contract document should cover:

| Contract Section | What to Specify |
| --- | --- |
| Partner identification | Canonical issuer/entityID, `client_id`/audience, signing keys, metadata, allowed algorithms, rotation. |
| Authentication assurance | Meaningful SAML `AuthnContext` / OIDC `acr` list, approved mappings, methods/`amr`, when step-up applies. |
| Authentication freshness | How `auth_time` is determined; SSO/reauth rules, clock skew, TTL, `max_age`, failure handling. |
| Identity binding | `iss+sub`, SAML NameID + qualifiers, pairwise subjects, issuer changes/migrations. |
| Claim provenance | HR/directory/self-service sources, verification, freshness, schema version, null/unknown handling. |
| Claim release/privacy | Which claims the RP receives, permitted uses, retention/consent, encryption if required. |
| Authorization mapping | Group IDs/tenant namespaces, local entitlements, deny precedence, who approves privileges. |
| Session lifecycle | OP/RP session lifetimes, revocation, logout propagation, disabled-account behavior. |
| Error/fallback | IdP unreachable, missing `acr`, stale attributes, invalid signature, unknown mapping → deny/step-up. |
| Operations and auditing | Correlation IDs, policy versions, audit/provenance, drift detection, and key rotation. |

**Note:** signing a token does not replace a **trust agreement**. An app may trust that Broker B checked upstream evidence per contract; without a provenance contract, the RP should rely only on claims Broker B attests to and **never claim to have directly verified upstream methods**.

### 9.1. Per-Issuer Assurance Mapping Table

Example **internal policy**:

| Verified Upstream Issuer | Claimed Upstream Context | Effective Contract Class | Permitted When |
| --- | --- | --- | --- |
| `urn:example:idp:employee` | `urn:example:authn:password` | `PASSWORD` | Valid signature and SAML conditions; approved mapping version. |
| `urn:example:idp:employee` | `urn:example:authn:mfa` | `MFA` | IdP enforces 2 factors per contract with auditing. |
| `https://partner.example.org` | `urn:partner:otp` | `UNKNOWN` | No contract yet proving equivalence to app's MFA standard. |
| `https://partner.example.org` | `urn:partner:phish-resistant` | `UNKNOWN` | Name sounds strong, yet is not self-proving evidence. |
| Any other issuer | Any `acr` | `UNKNOWN` | No trust relationship; reject high-assurance claims. |
| Broker executes step-up | Method verified directly by broker | Level permitted by broker policy | Fresh event, time/subject binding, audit, spec-compliant. |

Never force a comparison between `MFA` and `PHISHING_RESISTANT` alphabetically. For phishing-resistant requirements, **verify the actual authenticator type and context**, not merely that two factors ran.

## 10. Runnable Java 17 Policy: Valid Authentication Does Not Imply Sufficient Assurance or Permissions

The following program models **results already verified by OIDC/SAML protocols**, then applies assurance mapping **scoped to registered issuer and context values** plus local resource permissions. It does not parse/verify JWTs, XML signatures, or run an IdP; it cannot serve as a real authentication provider.

File **`FederationBoundaryPolicyDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;

public final class FederationBoundaryPolicyDemo {

    enum Assurance { UNKNOWN, PASSWORD, MFA }

    record Evidence(String trustedSourceIssuer,
                    String sourceContext,
                    Instant authenticationTime) {}

    record Account(boolean active,
                   String tenant,
                   Set<String> approvedPermissions) {}

    private static Assurance effectiveAssurance(Evidence evidence) {
        if (!evidence.trustedSourceIssuer().equals(
                "urn:example:idp:employee")) {
            return Assurance.UNKNOWN;
        }
        return switch (evidence.sourceContext()) {
            case "urn:example:authn:password" -> Assurance.PASSWORD;
            case "urn:example:authn:mfa" -> Assurance.MFA;
            default -> Assurance.UNKNOWN;
        };
    }

    static String decide(Evidence evidence,
                         Account account,
                         String requestedTenant,
                         String permission,
                         Assurance required,
                         Instant now,
                         Duration maxAuthenticationAge) {

        if (!account.active()) {
            return "ACCOUNT_BLOCKED";
        }
        if (!account.tenant().equals(requestedTenant)) {
            return "TENANT_DENIED";
        }
        if (!account.approvedPermissions().contains(permission)) {
            return "PERMISSION_DENIED";
        }

        Assurance level = effectiveAssurance(evidence);
        if (level == Assurance.UNKNOWN) {
            return "ASSURANCE_UNVERIFIED";
        }
        if (level.ordinal() < required.ordinal()) {
            return "STEP_UP_REQUIRED";
        }

        if (evidence.authenticationTime() == null
                || evidence.authenticationTime().isAfter(now)
                || Duration.between(evidence.authenticationTime(), now)
                           .compareTo(maxAuthenticationAge) > 0) {
            return "REAUTH_REQUIRED";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Duration freshness = Duration.ofMinutes(5);

        Evidence mfaFresh = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:mfa", now.minusSeconds(60));
        Evidence password = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:password", now.minusSeconds(60));
        Evidence mfaStale = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:mfa", now.minusSeconds(600));
        Evidence unknownIssuer = new Evidence(
                "urn:example:idp:partner",
                "urn:example:authn:mfa", now.minusSeconds(60));

        Account approved = new Account(true, "tenant-A",
                Set.of("payments:approve"));
        Account blocked = new Account(false, "tenant-A",
                Set.of("payments:approve"));
        Account noPermission = new Account(true, "tenant-A",
                Set.of("reports:read"));

        System.out.println(decide(mfaFresh, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(password, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaStale, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, blocked, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, noPermission, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(unknownIssuer, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, approved, "tenant-B",
                "payments:approve", Assurance.MFA, now, freshness));
    }
}
~~~

Run with Java 17:

~~~bash
javac FederationBoundaryPolicyDemo.java
java FederationBoundaryPolicyDemo
~~~

**Exact stdout:**

~~~text
ALLOW
STEP_UP_REQUIRED
REAUTH_REQUIRED
ACCOUNT_BLOCKED
PERMISSION_DENIED
ASSURANCE_UNVERIFIED
TENANT_DENIED
~~~

Explanation:

1. Contracted MFA, 60 seconds fresh, `ACTIVE` account, matching permission and tenant → `ALLOW`.
2. Password only despite a validly signed token → `STEP_UP_REQUIRED`.
3. MFA 600 seconds old against a 300-second limit → `REAUTH_REQUIRED`.
4. Blocked account: local deny overrides every authentication claim.
5. Has MFA yet lacks `payments:approve`: business permission denied.
6. Different issuer even with identical MFA class string: mapping is **untrusted**, so MFA is not inferred.
7. Permission in tenant A does not authorize approving a tenant B transaction.

**Demo limitations:** The `Assurance` enum defines an ordering **specific to this example and contract**, **not a universal global ranking for every `acr`**. In real systems, `Evidence` must be constructed from **framework-validated assertions/tokens and broker-governed provenance**, never straight from request JSON/headers. You also need bounded clock skew, re-authentication policy for new levels, disabled-account checks, transaction limits, and resource ownership; the demo does not replace SAML/OIDC validation.

### 10.1. Cases the Code Intentionally Disallows

- Never treat `unknownIssuer` as MFA because the context string contains `mfa`.
- Never compare `acr` with `String.compareTo` or regex `contains("high")`.
- Never use token `iat` as `authenticationTime`.
- Never read unapproved `groups` straight into `approvedPermissions`.
- Never skip tenant or disabled local account checks merely because the user completed MFA.
- Never construct `new Authentication(..., ROLE_ADMIN)` straight from self-asserted claims.

## 11. Spring Security OAuth2/OIDC Integration: Keep Framework Validation, Add Policy in the Right Place

In a **Spring Boot Servlet** app, `oauth2Login()` runs Authorization Code/OIDC login and validates ID Tokens against registration/issuer. Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          broker:
            issuer-uri: https://broker.example.org
~~~

This is an illustrative config. A real OP requires working discovery/JWKS, client registration, and a real redirect URI. Never commit client secrets to source control. If the app requires PKCE S256, verify and enable it via `ClientRegistration.ClientSettings.requireProofKey` or your version's equivalent config; never assume every Spring Security version enables PKCE automatically on confidential clients.

File `src/main/java/example/portal/SecurityConfig.java`:

~~~java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasAuthority("app:admin")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This code is **part of a Spring Boot project with `spring-boot-starter-oauth2-client`**, not a standalone Java SE class. This config **does not yet enforce business assurance/provenance/entitlements**; `oauth2Login` validates the OIDC token without automatically enforcing "MFA within 5 minutes to approve payments".

### 11.1. Extension Points After OIDC Authentication

Spring Security supports:

- `oauth2Login(...userInfoEndpoint(...oidcUserService(...)))` with `OAuth2UserService<OidcUserRequest, OidcUser>`.
- Delegating to the default `OidcUserService` to load `OidcUser`, then checking local identity/account status and mapping authorities per policy.
- `GrantedAuthoritiesMapper` to map authorities on login completion, without turning every scope or IdP group into app roles.
- `@EnableMethodSecurity` and `@PreAuthorize`/authorization services to check permissions per method/resource.

**Order to preserve:** framework validates **ID Token signature, issuer, audience, expiry, nonce, and authorization transaction** → admission by `iss+sub` and local account status → map **approved authorities** → establish session → enforce authorization and **freshness/step-up** at sensitive endpoints.

Pseudocode pattern (**not specific Spring APIs to copy-paste**):

~~~text
verifiedUser = springOidcUserService.loadUser(oidcUserRequest)
issuer  = verifiedUser.idToken.iss
subject = verifiedUser.idToken.sub
account = localIdentityBindingRepository.lookup(issuer, subject)

if account is missing, LOCKED or DISABLED:
    throw AuthenticationFailure

approvedAuthorities = accountEntitlements.forAppAndTenant()
effectiveAssurance = localContract.evaluateVerifiedBrokerClaims(
    issuer, acr, amr, auth_time, policyVersion)

authentication = principalWithApprovedAuthorities(
    verifiedUser, localAccountId, effectiveAssurance)

On sensitive endpoint:
    require account ACTIVE
    require permission and tenant/resource ownership
    require assurance policy and max authentication age
    else request step-up or deny
~~~

In a custom `OidcUserService`, always **delegate to the default implementation** and keep ID Token validation, `UserInfo.sub` matching, `state`/`nonce`, and token checks intact. If assurance must be enforced at login, check it before publishing the authenticated session; if step-up is needed only for sensitive actions, re-check at the resource/service boundary and **ensure the post-step-up token/session actually updates**.

### 11.2. Method Security Example and Its Limits

~~~java
package example.portal;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PreAuthorize("hasAuthority('payments:approve')")
    public String approvePayment() {
        return "Accepted for further policy checks";
    }
}
~~~

This snippet belongs in a Spring project with `@EnableMethodSecurity` enabled; **`hasAuthority` alone is insufficient** to approve financial transactions. The service/controller must still check **the exact account, tenant, limits, recipient, effective assurance, and real `auth_time`**, while blocking replay, session logout/revocation, and domain constraints. Returning `"Accepted for further policy checks"` underscores that no real money transfer executes here.

If claims arrive via a brokered ID Token, the application needs a **trust contract** with the broker specifying how assurance is derived. **Spring Security cannot infer an origin IdP's NIST AAL/FAL** from a broker-signed ID Token.

## 12. API Resource Server: Policies Follow Token Audience, Not UI Roles

In multi-tier applications, an RP calls another API with an access token. The API enforces its own policy:

~~~text
Portal (OIDC RP)
  user authenticated by Broker
  local account admitted
      |
      | access token for reports-api only
      v
Reports API (OAuth Resource Server)
  1. verify token issuer/signature/expiration
  2. verify audience == reports-api
  3. verify approved scope/entitlements
  4. verify tenant/owner/resource
  5. if action sensitive: verify assurance/freshness via trusted contract
  6. deny otherwise
~~~

In Spring Security Resource Server, `oauth2ResourceServer(jwt)` processes JWTs with a decoder/validator; **configure audience validation** matching the token contract rather than checking only `iss`/signature and letting every API accept shared tokens. Spring maps scopes to `SCOPE_...` authorities, yet **scopes never replace business permissions or resource ownership**.

When a resource server receives opaque tokens, use introspection against a trusted AS; never assume every access token is a JWT. When using token exchange, new requests must be **constrained by subject, actor, client, audience, scope, tenant, and policy**. Never forward an ID Token as an API bearer token.

## 13. Permission and Claim Limits with Two or More Brokers

A multi-broker chain amplifies risks of:

- **False assurance inflation** when one hop translates `acr=X` into a stronger `Y`.
- **Loss of provenance** when downstream brokers see only claims signed by the previous broker.
- **Loss of freshness** when `iat` is new yet `auth_time` is stale or dropped.
- **Loss of identifier uniqueness** when pairwise `sub` changes or emails get recycled.
- **Permission creep** from automatic `group` → `role` → `scope` → `authority` chaining.
- **Scope bleed** when tenant A/B is not pinned per transaction or cache entry.
- **Token confusion** when an ID Token or upstream access token hits a downstream API with the wrong audience.
- **Lost revocation state** when upstream groups/SCIM/account status change while downstream tokens remain unexpired.
- **Inconsistent logout** as OP/Broker/IdP/RP sessions outlive one another independently.
- **Data overexposure** when every hop packs excessive PII, groups, and auth methods into JWTs/logs.

Think in terms of a **per-hop risk contract**:

~~~text
IdP --> Broker A --> Broker B --> Portal --> API

Hop A:
  validate upstream issuer+signature+context
  map identity and attributes with provenance
  decide allowable assurance/claims

Hop B:
  validate Broker A issuer+audience+signature
  apply B-specific contract (cannot invent lost evidence)
  mint own token for Portal audience
  preserve trustworthy freshness or mark UNKNOWN

Portal:
  validate Broker B ID Token
  map iss+sub -> local account
  deny if locked/unprovisioned
  map only approved authorities

API:
  validate access token for its own audience
  enforce tenant/resource+scope+permission
  require step-up evidence for sensitive operations
~~~

**A later broker cannot "recover" lost evidence merely by rewriting claim strings.** If Broker A omitted a trusted `auth_time` while Broker B needs freshness, B must trigger re-authentication or fetch from a trusted source, or fail the requirement—never silently set `auth_time=now`.

### 13.1. Stale Attributes and Deprovisioning Risks

An employee leaves at 10:00 and HR/SCIM marks them `DISABLED`, yet Broker A caches an "active" group until 11:00 and Broker B minted a long-lived access token valid until 17:00. Even with a cryptographically valid ID Token, **permissions are no longer valid**.

Mitigations:
1. Establish the **authoritative source for account status** (HR/SCIM, local entitlement service).
2. Use event-driven invalidation plus cache TTLs aligned with revocation SLAs.
3. Have resource servers verify live status/permissions for sensitive operations.
4. Implement session/JWT revocation, token introspection, or system-wide `securityVersion` checks.
5. During upstream outages, never enable infinite caching that keeps stale privileges alive indefinitely.

Neither SAML logout nor OIDC logout **guarantees every API token is revoked**, especially stateless JWTs. Authentication assurance must also refresh independently of token/session lifetimes.

## 14. Data Minimization Design: Do Not Propagate Every Attribute Across Every Hop

In federation, profile data can reveal far more than login requires: employee IDs, departments, addresses, gender, MFA methods, and internal group lists. Never pack everything into downstream ID Tokens or send it to every app just because the broker can access it.

A sound policy:

| RP / API | Minimal Data Required | Should Not Receive |
| --- | --- | --- |
| Portal dashboard | Opaque `sub`, display name if consented, auth status. | Full HR records, private groups, SAML assertion XML. |
| Time-tracking app | Stable subject binding, timekeeping entitlement, approved fields. | Unrelated system admin groups, access tokens for other APIs. |
| Finance app | Account binding, tenant, policy-approved finance entitlement, contracted assurance. | Personal bank numbers, unrelated HR data. |
| Reports API | Audience-scoped access token, scopes/permissions, tenant/ref, approved claims. | Portal ID Token, upstream SAML assertion, refresh token. |
| Security audit | Correlation ID, verified issuer/ref, policy version, decision, timestamp. | Raw assertions/ID Tokens/NameIDs/emails unless strictly required. |

OIDC `scope` and `claims` can request attributes, yet release remains governed by OP/broker policy; **requesting a claim from an RP does not guarantee its release**. The broker should release the minimum needed, considering `pairwise sub`, data retention, consent/lawful purpose, and encryption where required.

**Key distinction:** "attribute omitted" is not "attribute equals false". If downstream needs `department` and the broker omits it, treat it as **UNKNOWN** and consult another trusted source; never default membership/roles to true or false without a contract.

## 15. Operations: Logging, Metrics, and Investigating Assurance Drift

Suggested fields to store **in protected audit logs**:

~~~text
event=FEDERATED_ASSURANCE_POLICY_EVALUATION
time_utc=2026-11-07T03:00:00Z
transaction_ref=txn-7a31
downstream_issuer=https://broker-b.example.org
upstream_source_ref=idp-contract-employee
mapping_policy_version=assurance-v7
requested_class=urn:corp:mfa
effective_class=urn:corp:password
authentication_age_seconds=420
decision=STEP_UP_REQUIRED
local_entitlement_policy_version=finance-v12
~~~

This is an illustrative format, not a built-in Spring Security metric. Keep secrets, PII, and raw tokens out of logs: `id_token`, `access_token`, refresh tokens, assertion XML, cookies, private keys, emails, and internal group lists. Use hashed references and restrict audit read access.

Metrics to track: rates of `assurance_missing`, `assurance_mismatch`, `freshness_reauth`, `step_up_success/failure`, `claim_mapping_unknown`, `issuer_audience_reject`, `entitlement_denied`, `broker_upstream_timeout`, and `token_exchange_reject`. Observe per hop to pinpoint whether upstream omitted a claim, a mapping broke, a broker dropped it, or an RP enforced a new policy.

### 15.1. How Should the App React When the Broker Fails or Omits Claims?

| Scenario | Safe Behavior |
| --- | --- |
| Broker omits `acr` on a baseline-login-only endpoint. | Allow login at baseline level **if policy permits**; never label it MFA. |
| Broker omits `acr` on an MFA-required action. | Require step-up or deny; never assume satisfied. |
| `auth_time` missing when `max_age` is needed. | Step-up/re-auth or deny; never substitute `iat`. |
| Upstream groups empty or source stale. | Never auto-grant roles; use approved local entitlements and error policy. |
| Invalid issuer/audience/signature. | Reject authentication; skip JIT provisioning. |
| Uncontracted context mapping. | `UNKNOWN`; never promote by similar naming. |
| Upstream IdP cannot satisfy requested level. | Report unmet requirement, pick another allowed IdP, or deny; never inject fake claims. |
| Local account status store unavailable. | Fail closed on privileged operations; show friendly operational error. |
| UserInfo `sub` differs from ID Token `sub`. | Reject UserInfo data; investigate token/OP. |
| Broker lost SSO session while RP retains session. | Enforce local session/step-up policy; never assume IdP logged out everywhere. |

## 16. Test Matrix: Proving Zero Assurance Inflation and Zero Privilege Bleed

| Test Case | Expected Result |
| --- | --- |
| Upstream SAML class `password`, broker translates to OIDC. | Downstream never receives `MFA` without a new event. |
| Upstream ran MFA yet broker lacks a verified mapping. | Effective assurance is `UNKNOWN`/low policy level; never auto-elevated. |
| Upstream MFA with `auth_time` 30 minutes ago; payment requires 5 minutes. | Step-up/re-auth required; never relies on new token's `iat`. |
| Broker mints fresh token with `iat=now` without re-authenticating. | Freshness remains anchored to the old authentication event. |
| `acr_values` requests MFA yet response omits `acr`. | RP enforces policy; never treats request as fulfilled. |
| `claims.id_token.acr` essential MFA yet OP cannot meet it. | Authentication flow fails per contract; RP never downgrades silently. |
| `amr=["pwd","otp"]` yet partner committed no semantics. | Never infers phishing-resistant or specific NIST AAL automatically. |
| SAML `ForceAuthn=true` yet `AuthnContext` remains weak. | Never grants MFA; denies/steps up per actual response. |
| Unknown upstream issuer uses context text matching a trusted issuer. | Rejects mapping or marks `UNKNOWN`. |
| Upstream ID Token `aud=broker-a` sent to Portal. | Portal rejects; never drops audience check. |
| Broker B ID Token has wrong `iss`, `aud`, signature, or nonce. | Portal rejects prior to account/role mapping. |
| Same email at two IdPs with different `iss+sub`. | Never auto-merges accounts. |
| Email recycled after prior user was disabled. | Never revives old privileges via email. |
| Group named `admin` from unallowlisted partner IdP. | Never creates `ROLE_ADMIN`. |
| Valid group for tenant A requesting tenant B resource. | Denies cross-tenant access. |
| Local account `LOCKED` despite valid OIDC `acr=MFA`. | Denies admission; never unlocks automatically. |
| Token has `scope=reports:read` yet wrong API `aud`. | Resource server rejects. |
| Valid scope yet user does not own the report. | Backend authorization denies resource access. |
| Broker issues token with `act` yet subject lacks requested permission. | Token exchange / resource operation denied. |
| HR attribute stale beyond policy TTL. | Never used to grant high privileges. |
| Downstream receives no `department`. | `UNKNOWN`; never defaults to entitled. |
| UserInfo `sub` differs from ID Token `sub`. | Rejects UserInfo result. |
| Broker refreshes token after one hour. | Never refreshes `auth_time` or restores revoked permissions. |
| Broker A loses upstream connectivity during step-up. | Fails closed; never emits fake MFA claims. |
| Policy mapping updates from `assurance-v7` to `v8`. | Clear audit/version; regression-tested per partner and class. |
| Local account logged out/disabled while RP session lives. | Revocation/status checks block actions within SLA. |
| Duplicate/replayed callback for same transaction. | Rejects repeated transaction per state/nonce/replay policy. |

**Real testing** requires test IdPs/OPs, validly signed SAML/JWT messages, and isolated trust configs. The Java mapping unit test above proves decision logic only—it **does not** prove signatures, audiences, nonces, `InResponseTo`, or step-up flows are properly enforced. Run integration tests across all broker hops, web sessions, API/resource servers, and multiple nodes.

## 17. Dangerous Misconceptions

1. **"The broker can rewrite `acr=low` to `acr=high` to satisfy the Portal."** Not without event/contract proof of the higher level.
2. **"Sending `acr_values` means MFA ran."** No; the RP must check the returned `acr` and its semantics.
3. **"An ID Token with `amr=mfa` definitely meets NIST AAL2."** No; that requires a contract and meeting full standard criteria.
4. **"The broker's signature proves the upstream IdP truly ran MFA."** The signature proves the broker issued the claim; upstream provenance requires a contract and operational controls.
5. **"The token was issued at 09:30 so the user authenticated at 09:30."** False; `iat` is not `auth_time`.
6. **"SAML `ForceAuthn` automatically triggers MFA."** False; it requests re-authentication, and the resulting context still needs checking.
7. **"A group named `admin` means the same privilege at every IdP."** False; namespace and map by issuer/tenant/app.
8. **"An email with `email_verified=true` is a safe system-wide identity key."** False; bind by issuer + subject with controlled migration.
9. **"If a claim is missing, reuse the previous token's value indefinitely."** False; cached entitlements need SLAs and fail-closed policies.
10. **"OAuth scopes can be forwarded across every API."** False; each token, audience, and resource server has distinct policies.
11. **"An ID Token is a JWT so it works as an API bearer token."** False; ID Tokens target the RP, not APIs.
12. **"Having the broker forward the upstream ID Token to the Portal is enough."** False; upstream `iss/aud` do not target the Portal.
13. **"An IdP role can override a locked local account."** False; local deny must win.
14. **"Passing MFA implies permission to approve payments."** False; resource/tenant/limit permissions are independent.
15. **"Spring `oauth2Login` automatically understands every broker's `acr` mappings."** False; the framework authenticates OIDC, while assurance policy is a separate business contract.
16. **"More signing hops automatically improve claim trustworthiness."** False; transformations require provenance/semantic contracts and assurance does not accumulate.
17. **"SAML NameID, broker subject, and OIDC `sub` are always identical."** False; each issuer has its own namespace and pairwise mappings.
18. **"A fresh refresh token means authentication stepped up."** False; refreshing creates no new authentication event.
19. **"During broker outages, skip checks to preserve uptime."** Violates mandatory safety; fail closed deliberately.
20. **"RP logout revokes all API tokens and upstream sessions."** False; session and token lifecycles are separate.

## 18. Production Readiness Checklist

1. Is there an inventory of every **trust hop**, issuer, audience/client, signing key, metadata, and per-hop policy?
2. Is there an approved **per-issuer** mapping document for **SAML `AuthnContext` ↔ OIDC `acr/amr`** and their semantics?
3. Is **authentication event time** captured accurately and freshness preserved across token re-issuance?
4. When an RP demands high assurance, are appropriate `acr_values`/essential claims and `max_age` sent and **final claims verified**?
5. Is there a **genuine step-up** path when upstream is weak rather than relabeling claims as MFA?
6. Are IAL, AAL, and FAL distinguished without claiming compliance levels solely from an `acr` name?
7. Do authorization-critical attributes carry provenance and freshness, preferring HR/SCIM/approved sources?
8. Is **`issuer+subject`** used for identity binding—never merging emails, mismatched-namespace NameIDs, or pairwise subs automatically?
9. Does claim release enforce data minimization, consent/purpose limitation, TTL/retention, and PII controls?
10. Are roles/groups mapped per issuer/tenant/client with deny precedence and a local entitlement service?
11. Are local account `LOCKED/DISABLED`, tenant, and resource authorizations enforced after OIDC login?
12. Do APIs validate exact access token audience/scope and reject Portal ID Tokens?
13. When using token exchange, are subject/actor/scope/audience restricted without escalating privileges on re-issuance?
14. Are session/token revocation and permission refresh wired to HR/SCIM changes?
15. Are policies tested for missing claims, stale attributes, wrong issuers, unapproved mappings, and broker failover/timeouts?
16. Do audits log policy version, requested/effective assurance, and deny reasons without logging raw assertions/tokens/PII?
17. Are full-chain integration tests run across SAML → Broker A → Broker B → OIDC Portal → API?
18. Is there clear ownership for every claim definition and a safe contract-change workflow?

## 19. Self-Check Questions

1. **Why can a broker sign a valid ID Token yet still emit the wrong MFA level?** — The signature proves only that the broker minted the token; semantic claims depend on upstream evidence and approved policy.
2. **How do `acr` and `amr` differ?** — `acr` states the achieved context/class; `amr` lists methods used without defining a standardized class itself.
3. **How do `iat` and `auth_time` differ?** — One is when the token was issued, the other is when the user authenticated.
4. **Does sending `acr_values=urn:corp:mfa` guarantee the OP uses MFA?** — No; that request is voluntary, and the RP must inspect the outcome.
5. **When `auth_time` is missing and "within 5 minutes" is required, what should happen?** — Trigger step-up/re-auth or deny; never substitute `iat`.
6. **Does SAML `ForceAuthn=true` mean the user completed MFA?** — No; it requests re-authentication per profile, and you must still verify the returned context.
7. **Why isn't an upstream `admin` group enough to grant `ROLE_ADMIN` downstream?** — Different namespaces/apps/tenants require explicit approved mapping and local entitlements.
8. **Can Broker B's new token rely directly on Broker A's signature?** — The Portal must verify the token **issued by B for the right audience**, never trusting Broker A's upstream token blindly.
9. **If `sub` differs between the Portal and another app, is that necessarily a bug?** — No; it may be a pairwise subject.
10. **Does MFA replace local permission `payments:approve`?** — No; authentication assurance and authorization are two independent conditions.
11. **What is required to call Reports API from the Portal?** — An access token scoped to the API's audience/scopes, validated by the API, and permitted by resource policy.
12. **If a broker lacks provenance for `department`, can it grant department-based access?** — No if access requires a verified source; treat as UNKNOWN/deny per policy.
13. **Does NIST FAL equal AAL?** — No; FAL protects federation transactions, whereas AAL governs authentication.
14. **Can you sum assurance levels of two tokens across two hops?** — No; each needs its own contract, event evidence, and valid mapping.
15. **Why include `policyVersion` in audits?** — To track which definition governed a session/claim evaluation, aiding change control and incident investigation.

## References

- [OpenID Connect Core 1.0 — ID Token claims, acr/amr/auth_time, max_age, acr_values, and essential acr](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — issuer, endpoints, signing keys](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OASIS SAML 2.0 Core — RequestedAuthnContext, AuthnContext, AuthnStatement, and NameID](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML 2.0 Profiles — Web Browser SSO requirements](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [NIST SP 800-63-4 / SP 800-63C — Digital Identity Federation and Assertions, FAL](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [RFC 8693 — OAuth 2.0 Token Exchange, actor/delegation](https://www.rfc-editor.org/rfc/rfc8693.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Spring Security — OAuth2/OIDC Login Advanced Configuration, OidcUserService, and GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
