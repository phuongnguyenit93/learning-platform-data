# Distinguishing CAS Proxy Delegation from OAuth2 and Choosing Migration Options

**CAS Proxy** and **OAuth 2.0** can both appear in the “application A calls API B on behalf of the user” problem, yet they **do not share the same delegation model**. CAS Proxy primarily **delegates an existing authentication context** via a Proxy-Granting Ticket (**PGT**) and a Proxy Ticket (**PT**) issued for a specific service. OAuth 2.0 is a **resource-access authorization framework**: an Authorization Server (**AS**) issues an Access Token to a Client for a Resource Server (**RS**), potentially carrying **scopes**, **audiences/resources**, lifetimes, client identity, and proof of delegation.

**Never rename a PT into an OAuth Bearer token, treat a CAS username as an API permission, or let an API accept both credential types through a “permissive” validator.** Migrating from CAS Proxy to OAuth2 requires picking the exact target: user login, machine-to-machine without a user, calling an API **on behalf of** a user, or maintaining a legacy CAS app. Each goal has distinct grants, trust boundaries, and policies.

This lesson belongs to **Spring Security – federation → CAS Proxy**, covering protocol mechanics, similarities and differences, architecture evaluation, and options to **keep CAS**, **run in parallel**, **use a verified bridge**, **adopt greenfield OAuth2/OIDC**, and apply **RFC 8693 Token Exchange** where supported—alongside Spring Security examples, Java 17, a test matrix, and a migration runbook.

## 1. Real-World Scenario: Portal Calls Billing API on Behalf of a User

Suppose employee **Lan** logs into Portal A and clicks “View invoices.” Portal needs to call Billing B, and Billing must decide whether Lan is permitted to view the data.

~~~text
Lan's Browser
       |
       | Log in and view invoices
       v
   Portal A
       |
       | Call on Lan's behalf
       v
 Billing API B
       |
       v
  Check permissions:
   - Who is Lan?
   - Is Portal A allowed to act on her behalf?
   - Is the ticket/token scoped to Billing B?
   - Which invoices of which tenant may be read?
~~~

In the legacy CAS model, Portal holds a **PGT**, requests **`PT-B`**, and calls Billing. Billing asks the CAS Server to **`proxyValidate` `PT-B`**. In an OAuth2 architecture, Portal typically obtains or exchanges for an **access token scoped to Billing**, and Billing validates the token and applies domain authorization.

Both can supply user identity, yet **neither automatically grants permission to view all invoices**. Resource and tenant permissions still belong to the application/API.

## 2. Four Roles in CAS and Four Roles in OAuth2

| CAS | OAuth2 | Notes |
| --- | --- | --- |
| CAS Server | Authorization Server or OP in OAuth/OIDC | Roles may live in one product, yet protocols differ |
| User/browser | Resource Owner and user agent | Not every OAuth2 flow involves a user |
| Portal A, CAS Client/Proxy | OAuth Client | May be a confidential client/BFF |
| Billing B, CAS Client | Resource Server | B validates received evidence per its exact protocol |
| PGT | No standard 1-to-1 mapping | Used to request multiple PTs for target services |
| PT | Access Token (**not equivalent**) | PT is single-use validation; OAuth tokens have different lifecycles/types |
| CAS proxy chain | OAuth actor/delegation context when AS supports it | No automatic mapping |
| CAS service identifier | OAuth resource/audience | Similar “target” concept, yet semantics and validation differ |
| CAS principal attributes | OAuth token claims/scopes/entitlements | Never blindly copy raw attributes into permissions |
| CAS TGT/TGC | OIDC/AS session/refresh token (**not equivalent**) | Cannot be converted directly by name alone |

**OIDC** is the authentication layer atop OAuth2, supplying **ID Tokens** and `(iss, sub)` identity rules. **OAuth2 alone does not authenticate users the way an OIDC ID Token does.** When modernizing **web login**, evaluate OIDC; when modernizing **API calls**, use OAuth2 access tokens.

## 3. How Does CAS Proxy Work?

The CAS Server authenticates the user once. When Portal A validates a Service Ticket (**ST**) with CAS, it can request a PGT via a CAS-trusted **HTTPS `pgtUrl` callback**. CAS sends **`pgtId`** and **`pgtIou`** to the callback, then returns PGTIOU in the validation response so A correlates the right PGT.

Subsequently:

1. Portal A calls CAS `/proxy` with **PGT** and **`targetService=Billing B`**.
2. CAS checks PGT/service policy and issues **`PT-B`**.
3. A sends **`PT-B`** to Billing B.
4. Billing B calls CAS `/proxyValidate` with `ticket=PT-B` and **`service=B`**.
5. CAS verifies the ticket is unexpired, matches `service`, checks proxy chain and policy, and returns the validation result.
6. Billing uses the verified result to build an `Authentication` and enforce local permissions.

~~~text
Browser        Portal A                  CAS Server               Billing B
   |              |                          |                         |
   | Login -------|--- ST validation ------->|                         |
   |              |<-- Assertion + PGTIOU ---|                         |
   |              |<-- PGT via pgtUrl -------|                         |
   |              |                          |                         |
   | View invoice>|                          |                         |
   |              |--- /proxy(PGT,B) ------->|                         |
   |              |<-- PT-B -----------------|                         |
   |              |--- API request + PT-B ---------------------------->|
   |              |                          |<-- /proxyValidate ------|
   |              |                          |--- validated identity ->|
   |              |<--------------- API response ---------------------|
~~~

**A PGT can issue multiple PTs; each PT is bound to one target service.** Under the CAS protocol, a PT has **single-use validation** just like an ST. The CAS Server can return a **proxy chain** so Billing decides whether to accept A as a proxy.

### Distinguishing ST, PT, and PGT

| Type | Where Used? | Characteristics |
| --- | --- | --- |
| ST | Browser SSO to one service | Single-use validation, service-bound |
| PT | A calls B on user's behalf | Single-use validation, service-bound, includes proxy context |
| PGT | A requests fresh PTs | Reusable multiple times; protect as a high-value credential |
| TGT/TGC | SSO session at CAS/browser | Never sent directly to Billing as an API credential |
| Cached `CasAuthenticationToken` | Local state on B | Can reuse validated auth result if Spring `StatelessTicketCache` is enabled |

**CAS Proxy has a delegation element, yet is not an OAuth2 authorization grant.** It carries user identity and the proxy path; business rights like “`invoice.read` for tenant north” must be resolved by CAS policy, SP mapping, and especially **Billing domain authorization**.

## 4. How Does OAuth2 Solve a Different Problem?

OAuth2 cleanly separates roles:

- **Resource Owner:** user or entity authorized to grant access to a resource; in some flows no user participates directly.
- **Client:** application requesting resource access, e.g., Portal A.
- **Authorization Server:** system deciding and issuing access tokens.
- **Resource Server:** Billing B, validating tokens and protecting invoices.

An access token is typically used as follows:

~~~text
User/Portal A            Authorization Server              Billing B
      |                           |                              |
      | Authorization grant       |                              |
      |-------------------------->|                              |
      |<----- Access Token -------|                              |
      |                           |                              |
      |--- Authorization: Bearer ACCESS_TOKEN ------------------>|
      |                           |             Verify token and policy
      |<--------------------------- API data / 401 / 403 ---------|
~~~

**An OAuth2 Access Token does not have to be a JWT.** It can be an opaque token checked via introspection or a signed JWT carrying claims like `iss`, `aud`, `exp`, and `scope` per an applicable profile. For JWT access tokens under **RFC 9068**, the Resource Server must verify token type, issuer, and audience rather than accepting any JWT with a valid signature.

**OAuth2 grant does not equal OAuth2 scope:** the grant describes **how the client obtains a token**; scope describes **requested/granted permission ranges**; audience/resource describes **where the token may be used**. These constraints complement one another rather than replacing authorization at Billing.

## 5. Comprehensive Comparison: CAS Proxy vs. OAuth2

| Dimension | CAS Proxy (PGT/PT) | OAuth2 |
| --- | --- | --- |
| Core goal | Delegate **authentication** across CAS clients/services | **Delegated access/authorization** to protected resources |
| Proof sent to API | Proxy Ticket | OAuth2 Access Token |
| Issuer | CAS Server | Authorization Server |
| User login | CAS SSO | Often OIDC if RP needs user authentication |
| Target receiver | `targetService`/CAS service identifier | `aud`/resource indicator and client/scope policy |
| Minting ticket/token | `/proxy` using PGT | Token endpoint via appropriate grant |
| Validation at B | `/proxyValidate` with CAS | Local JWT verification or introspection |
| Reuse | Single-use PT validation; Spring cache may reuse **auth result** | Access token typically reused across requests to valid audience within lifetime |
| Acting-party context | CAS proxy chain | Client identity; actor/`act` when token exchange supports it |
| Fine-grained rights | CAS service/access policies + app checks | Scopes/claims/policies + app checks |
| Consent | No standard OAuth consent in PTs | Authorization may involve user consent or enterprise policy; **UI consent not required in every flow** |
| Revocation | CAS ticket/session policies; separate app local session/cache | Token revocation, introspection, JWT TTL, AS/RS policies |
| Userless M2M | CAS proxy is unnatural | `client_credentials` fits directly |
| Modern web login | CAS login still works | OIDC Authorization Code + PKCE fits directly |
| Multi-hop delegation chain | CAS proxy chain | RFC 8693 token exchange/`act` when AS supports it |
| Spring implementation | `spring-security-cas` | `oauth2Login`, `oauth2Client`, `oauth2ResourceServer` |
| Conversion | No standard automatic PT → Access Token conversion | Requires a trusted, policy-governed AS/broker/gateway to mint a new token |

**Similarities:** both require HTTPS, trust configuration, target mismatch prevention, and service-level authorization. **Most important difference:** a PT proves an authentication/proxy context with CAS, whereas an access token represents an **authorization grant decision** inside OAuth2.

## 6. “Delegation/Authorization” Has Three Meanings That Must Not Be Mixed

In engineering systems, **delegation/authorization** can refer to three distinct things:

1. **Proxying authentication:** A proves to B that it is acting on behalf of a CAS-authenticated user. This is the focus of CAS Proxy.
2. **Delegated authorization:** Resource Owner/AS grants A permission to call B within defined scopes. This is a canonical OAuth2 pattern.
3. **Business authorization:** Billing decides whether the user/actor is permitted to view invoice #37 of tenant north. This is an application decision.

Example:

~~~text
CAS:
  "Lan was authenticated by CAS; request arrived via proxy Portal A."

OAuth2:
  "Portal A was granted an access token by AS for Billing,
   scope=invoice.read, subject=Lan, actor=A if delegated."

Billing:
  "Invoice 37 belongs to tenant north and Lan holds valid membership;
   Portal A is in the accepted proxy/client set;
   read allowed, modification denied."
~~~

Never treat “valid login” as “authorized to read everything,” and never substitute a machine-to-machine client identity for a user without explicitly modeling it.

## 7. Subject, Client, and Actor: Who Is Actually Acting?

In CAS Proxy, the validation response carries the user principal and optionally a **proxy chain**. The backend validates the user and permitted proxy chain.

In OAuth2, distinguish at minimum:

- **`sub`**: subject of the access token—either user or client depending on token type/profile.
- **`client_id` / `azp`**: involved client identity, when emitted by the AS/profile.
- **`aud`**: Resource Server(s) the token is intended for.
- **`scope`**: permissions/scopes granted to the token.
- **`act`**: structure representing the acting party in token exchange when the AS issues a composite delegation token.
- **`tenant`**: custom business claim per contract—**not automatically proof of current membership**.

Illustrative **sample JWT access token** from a trusted AS:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-57",
  "aud": ["billing-api"],
  "client_id": "portal-client",
  "scope": "invoice.read",
  "act": { "sub": "portal-service" },
  "tenant": "north",
  "exp": 1794045600
}
~~~

The payload above **is unsigned and not a usable token**. The `act` field is specific to RFC 8693 when applied and is **not required in every access token**; `tenant` is organization-defined. The backend trusts claims only after verifying signature, issuer, audience, expiry, and its own policies.

**Note that `sub` in a `client_credentials` access token may be the client itself**, not a human user. Never take an M2M token and silently execute business actions “on behalf of Lan” merely because the client is named portal.

## 8. CAS `targetService` vs. OAuth `audience`/`resource`

CAS Proxy:

~~~text
CAS /proxy?pgt=PGT-...&targetService=https://billing.example.test/cas
    -> CAS issues PT for exact targetService.
Billing /proxyValidate?service=https://billing.example.test/cas&ticket=PT-...
    -> CAS matches exact service.
~~~

OAuth2:

~~~text
AS issues access token:
  aud = billing-api
  scope = invoice.read

Billing:
  verify token
  require aud contains billing-api
  require scope contains invoice.read
  verify tenant + invoice ownership
~~~

**`targetService` and `aud` do not translate automatically.** During migration, maintain an approved mapping table from CAS service URLs to OAuth resource identifiers. Never strip hostnames/paths heuristically to guess an audience.

With multiple APIs, **RFC 8707 Resource Indicators** let clients specify the target resource via the `resource` parameter when supported by the AS. **RFC 9068** requires distinguishing access tokens per resource via audience. A token for Billing must never be accepted by Payroll or Admin APIs.

## 9. CAS Proxy Chain vs. OAuth Delegation Chain

CAS proxy validation can return the participating proxies:

~~~text
User Lan -> Portal A -> Aggregator C -> Billing B
             |              |
          Proxy A         Proxy C

CAS proxy chain: per CAS-verified history
Billing decides whether to accept chain A,C.
~~~

OAuth2 **Token Exchange (RFC 8693)** introduces `subject_token`, `actor_token`, and the `act` claim to represent an actor acting for a subject. The AS may reject requests or issue narrower-scoped tokens.

**There is no default conversion from CAS proxy chain → `act` chain.** An AS/bridge must specify how it verifies the CAS source, proxy identities, delegation rights, and identifier mappings. Multi-tier flows must ensure acting-party provenance is preserved and privilege escalation / impersonation is blocked.

**Impersonation differs from delegation:** a token naming only user Lan hides the fact that Portal A performed the operation. If audit policies or separation of duties require actor visibility, use an evidence-backed delegation/token exchange mechanism rather than minting a `sub=Lan` token that omits the actor.

## 10. Does CAS Proxy Have “Scopes”?

CAS has **Service Registry, access strategies, attribute release, and proxy policies** to control which services may issue/validate PTs, which proxy chains are trusted, and which attributes are released. Those are CAS Server-level authorization controls.

However, a CAS PT **is not an OAuth2 access token** and carries no **standard OAuth2 `scope` claim** like “`invoice.read`, `invoice.write`” issued by an AS and enforced by an RS. CAS can release principal attributes for apps to map into roles, yet that does not mean a PT natively carries fine-grained resource scopes.

Design the translation explicitly:

| CAS Source | OAuth2 / App Target | Rule |
| --- | --- | --- |
| Billing CAS service identifier | OAuth audience `billing-api` | Allowlist mapping approved by security owner |
| CAS proxy A | OAuth client/actor `portal-service` | Verify proxy chain and client identity |
| CAS principal `user-57` | OAuth subject `user-57` or internal ID | Evidence-backed account linking, never by email alone |
| CAS group `billing-viewers` | Scope `invoice.read` | Never blindly copy; constrain by policy and tenant |
| CAS authentication context | OAuth `acr`/`amr` or custom assurance | Only with an explicit contract and real AS verification |
| CAS TGT/PGT lifetime | Token `exp` and revocation | Lifetimes do not map 1-to-1 |
| CAS SLO | OAuth token revocation/session logout | Requires dedicated integration |

**Least-privilege rule:** the newly minted token may receive only the **intersection** of the user's rights, client/actor rights, verified CAS delegation policy, target resource, and permitted tenant.

## 11. Which OAuth Grant Replaces Which Scenario?

| Real Requirement | Usually Sensible Choice | Avoid |
| --- | --- | --- |
| Browser visits Portal needing SSO | **OIDC Authorization Code + PKCE**; keep CAS if legacy | `client_credentials` in place of user auth |
| Portal holds user context and calls Billing for user | User-scoped OAuth2 access token for Billing; **RFC 8693 Token Exchange** if AS supports | M2M token pretending to be a user token |
| Billing cron job syncs data with no user | OAuth2 `client_credentials` | CAS PT faking a user |
| Backend B accepts only CAS PTs and cannot change yet | **Keep CAS Proxy** or gateway/adapter | Sending JWTs directly to `/proxyValidate` |
| User has CAS login, new API uses OAuth | OIDC federation/AS or validated trusted bridge | Self-signed “JWT signed with custom key” by Portal |
| Multi-hop system A→C→B | Token exchange with `act`/policy or CAS proxy chain during legacy phase | Dropping intermediary actor identity |
| Need near-instant permission revocation | Opaque token introspection, short JWT TTL + revocation checks | Long-lived JWTs with no revocation |
| Mobile/native app login | Authorization Code + PKCE via system browser | Password grant / unnecessary embedded browsers |
| Third-party delegation per resource owner | OAuth2 AS policy + consent/contract + resource scoping | CAS proxy chain as a substitute for OAuth consent |

**Consent** may be a user-facing approval screen or an enterprise authorization policy configured at the AS; OAuth2 **does not require a consent popup for every token**. `client_credentials` does not represent user consent.

## 12. When Should You Keep CAS Proxy?

**Keeping CAS Proxy is sensible** when:

- Only a small set of mature legacy services exists, and the protocol and CAS integration are well controlled.
- The CAS Server and Java CAS clients remain maintained, with governed security patches and service registries.
- Downstream APIs require **proxy chains**, no trusted OAuth AS exists, or migration would require sweeping rewrites.
- User session lifecycles are tightly bound to CAS with no new M2M or external partner requirements.
- The team can monitor PT/PGTs, TTLs, SLO, and per-service authorization effectively.
- Conversion cost and operational risk outweigh near-term benefits.

Add these guardrails:

1. Never accept arbitrary proxy chains; configure **`allowedProxyChains`** and never enable `acceptAnyProxy=true` just to bypass errors.
2. Keep CAS PGTs strictly server-side, protecting secret stores and `pgtUrl` callbacks.
3. Mint PTs for exact `targetService` values and run `/proxyValidate` over HTTPS.
4. Verify user identity and local entitlements inside Billing.
5. If Spring `StatelessTicketCache` reuses `Authentication`, enforce separate TTLs, scopes, and revocation—never confuse it with CAS single-use PT validity.
6. Revoke sessions/permissions via SLO or backend revocation policy rather than waiting solely for CAS TGT expiry.
7. Plan CAS Client/Spring Security dependency upgrades and replacement if legacy components approach end-of-life.

**Keeping CAS does not mean halting security improvements**, nor is CAS “inferior to OAuth” in every case. The choice depends on capabilities, trust boundaries, and cost.

## 13. Moving Userless M2M Calls to `client_credentials`

When a batch service calls an API under an **application identity** with no active resource owner, OAuth2 **Client Credentials Grant** fits better than CAS Proxy.

~~~text
Job A           Authorization Server             API B
 |                    |                            |
 | -- client auth --->|                            |
 | <--- token --------|                            |
 |                   aud=B,scope=report.write      |
 | -- Bearer token -------------------------------->|
 |                                verify client, audience, scope
~~~

The AS authenticates client A via client secret, `private_key_jwt`, mTLS, or equivalent, enforces access policy, and issues a token for B.

**Never turn `client_credentials` into silent user impersonation.** If B needs to know “Lan approved the invoice” or check Lan's permissions, `client_credentials` **carries no proof of user delegation in a user-centric flow**.

For service-owned data governed by machine policy, B checks **client identity + machine scope + tenant/service ownership**, needing no fake username at all.

## 14. Modern Web Login with OIDC Authorization Code + PKCE

If the goal is upgrading **web login** from CAS to a modern protocol, use **OIDC Authorization Code Flow** (with PKCE per RFC 9700) rather than trying to convert a CAS Service Ticket into an Access Token in the browser.

~~~text
Browser
    |
    v
Portal Web / Spring Security oauth2Login
    |
    v
OIDC Provider / Authorization Server
  authenticate user
  authorization code + PKCE/state/nonce
    |
    v
Portal backend receives code
  exchanges at token endpoint
  validates ID Token iss/aud/exp/nonce/signature
    |
    v
Portal local session + verified identity link
    |
    v
OAuth Access Token for APIs (when authorized)
~~~

**The ID Token authenticates the RP**, while the **Access Token calls protected APIs**. Never send an ID Token to Billing as an Access Token. Bind OIDC user identity by **`iss, sub`**, never using email as the primary account-linking key.

If an organization wishes to retain the CAS login screen, it can configure an **OIDC Provider/Broker** backed by upstream CAS/LDAP/SAML to issue OIDC tokens to new clients. That depends on actual IdP product modules and capabilities; never assume every CAS Server automatically becomes an OP by toggling a flag on Portal.

## 15. On-Behalf-Of (OBO) with OAuth2 Token Exchange (RFC 8693)

When Portal A **already holds a valid user token** and needs to call Billing B, it can ask the AS for a new token **scoped to Billing** with narrower permissions and actor metadata when the AS supports **Token Exchange**.

**Illustrative** POST to the token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_AUTH

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SIGNED_OR_OPAQUE_USER_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=billing-api
&scope=invoice.read
~~~

In delegation setups requiring an explicit actor, the request may add `actor_token` and `actor_token_type` if the AS supports them; many AS implementations infer the actor from client authentication per policy. **Token exchange does not automatically return an `act` claim or enforce identical delegation semantics everywhere**: the AS decides whether to issue, downscope, populate actor/subject, or deny.

Sample **output access token payload** after AS policy:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["billing-api"],
  "sub": "user-57",
  "act": { "sub": "portal-service" },
  "scope": "invoice.read",
  "tenant": "north",
  "exp": 1794045600
}
~~~

This is an **unsigned sample payload**. Billing must validate the token and domain authorization rather than trusting claims just because they look like sample JSON.

### Limitations That Must Be Understood

- **Token Exchange is an extension**; not every AS supports it.
- The AS **must validate** the input token according to its token type; any `actor_token` must also be validated.
- The client must be **registered and authorized for exchange** by policy.
- `subject_token` does not equal a CAS PT. **RFC 8693 does not standardize passing an arbitrary CAS PT as an input token accepted by all ASs.**
- Output tokens have their own lifetime/revocation. Per RFC 8693, exchange **does not automatically create bidirectional revocation coupling** between input and output tokens.
- If accountability for both user and actor is required, AS and RS must agree on `act` representation and delegation enforcement.
- Never use `client_credentials` and manually copy `sub=Lan` into a JWT to fake OBO.

## 16. CAS → OAuth2 Bridge Option: Requires a Transparent Trust Boundary

Many organizations cannot replace all CAS clients at once. A **trusted bridge** can validate CAS first and then ask a **real AS** to issue a fresh access token.

~~~text
Legacy Portal A
    |
    | CAS Proxy Ticket PT-BRIDGE
    v
Trusted CAS Validation Bridge
    | 1. CAS /proxyValidate with exact service
    | 2. Check proxy chain, principal, TTL, policies
    | 3. Map verified CAS identity to local account
    | 4. Determine requested client/tenant/resource rights
    | 5. Pass authenticated evidence over trusted AS channel
    v
OAuth2 Authorization Server
    | Verify bridge identity, client policy,
    | issue fresh token aud=Billing, narrow scope
    v
OAuth Access Token
    |
    v
Billing Resource Server
    | JWT verification/introspection + business authorization
~~~

**The bridge must never be “an API that signs JWTs from a raw CAS username string.”** It must be an AS-trusted component with source validation, service binding, actor identity, and auditing. Architecture docs must specify who issues tokens, who owns signing keys, who evaluates scopes/tenants, and who revokes tokens.

### When Can a Bridge Issue a Token?

Only after:

1. The CAS PT is validated **once** with the CAS Server for the **exact bridge service ID**.
2. Portal's proxy chain/PGT path is allowed and the principal is authenticated.
3. Subject maps to a local account from an authoritative source, never unverified email.
4. Client Portal proves its server-to-server identity (mTLS/private key or equivalent).
5. The AS enforces policy across user + actor + resource + tenant + requested scope.
6. The token is minted **by an accountable AS** with appropriate audience, lifetime, and delegation metadata where supported.
7. The bridge logs correlation/audits without raw PT/PGT/access tokens.
8. Revocation/expiry policies and fail-closed handling exist if CAS or AS is unavailable.

**Never treat an arbitrary CAS ST/PT as a standard RFC 8693 `subject_token_type`.** If an AS supports a custom CAS token-type extension, that is a **bespoke contract** requiring its own validator, namespace, threat model, and tests. A far simpler alternative when feasible is having users reauthenticate via an OIDC broker and issuing OAuth tokens cleanly.

## 17. Bridge vs. Re-Signing In via OIDC?

| Criterion | CAS→OAuth Bridge | Fresh OIDC Sign-In |
| --- | --- | --- |
| Legacy frontend changes | Potentially smaller | May require updating login/callback/logout |
| Source of user session | CAS | OIDC OP/broker |
| How does AS learn CAS identity? | Trusted validation/mapping/bridge contract | Direct OIDC authentication or via broker |
| Must user log in again? | Not necessarily, if CAS session is valid and policy permits | Possible SSO if broker uses upstream CAS, depending on config |
| API authorization | Fresh OAuth access token | Fresh OAuth access token |
| Risks | Bridge becomes a high-privilege choke point for token minting/mapping | Migrating user identities, sessions, and redirects |
| Medium-term lifecycle | Adds operational complexity running two protocols | Easier to unify client ecosystem |
| Pick when | Migrating backends piecemeal while legacy portal is hard to alter | Clients and IdP/broker can migrate together |

**Long-term view:** if targeting a multi-client API ecosystem, OIDC/OAuth2 simplifies grant/scope/audience semantics. **Short-term view:** a bridge helps when CAS is the sole auth source and legacy apps must stay intact. Never keep a bridge indefinitely without an owner and review schedule, as it adds a trust boundary and hard-to-maintain migration logic.

## 18. Migrating Layer by Layer: Authentication, API Tokens, Authorization

All three layers do not have to change simultaneously.

**Layer 1 — Authentication:** CAS login → OIDC login when ready, preserving verified account links during transition.

**Layer 2 — Service-to-service credential:** CAS PT/PGT → OAuth access token scoped to Billing, with client authentication and audience.

**Layer 3 — Business authorization:** CAS groups/attributes → app roles/entitlements/resource policies; never port roles verbatim across protocols.

~~~text
Before:
 CAS login -> Portal session -> PGT/PT -> Billing CAS validation
                                 |
                          CAS groups -> local roles

During parallel phase:
 CAS/OIDC login -> Local account identity link
                     |
               trusted bridge / AS
                     |
              OAuth access token -> Billing Resource Server
                     |
              local entitlements, tenant checks

After:
 OIDC login -> OAuth2 Client -> AS/token exchange -> Billing OAuth2 RS
                                              |
                                        domain authorization
~~~

**Never confuse “access token issued” with “user authorized.”** Even if a token carries `scope=invoice.read`, Billing must still verify the invoice belongs to an allowed tenant and the user holds current rights.

## 19. Architecture Decision Matrix

| Dominant Condition | Preferred Path | Rationale |
| --- | --- | --- |
| Legacy Portal↔Billing only, minimal changes, no external APIs | **Keep CAS Proxy** with hardening | Lower change risk; CAS flow already fits |
| New APIs serving multiple clients/partners | **OAuth2 Resource Server** | Standard access tokens, scopes/audiences, client policies |
| Userless machine-to-machine | **`client_credentials`** | Explicit machine identity and machine permissions |
| User acting across multiple backends | **User-delegated OAuth2 token / Token Exchange** | Narrow audience, subject+actor where needed |
| Cannot alter Portal yet while Billing needs OAuth | **Trusted CAS→OAuth bridge** | Preserves CAS login temporarily; migrates backend incrementally |
| Building a new browser application | **OIDC Authorization Code + PKCE** | Standard authentication and clean identity mapping |
| Need multi-hop delegation and actor auditing | **RFC 8693 if AS supports**, or keep CAS proxy temporarily | Preserves actor lineage and policy |
| No real AS yet, tight budget | **Never build a DIY AS/token service** | Better to keep hardened CAS than deploy fake OAuth |
| Need rapid API revocation | **Opaque token introspection / short JWT TTL + revocation** | Controls freshness; requires cache design |
| High account/tenant mapping risk | **Defer authorization cutover**; solve identity migration first | Prevents account takeover and cross-tenant leaks |

A sound decision weighs **security, compatibility, change cost, developer experience, observability, outage modes, and long-term operations**—not merely “OAuth2 is newer.”

## 20. Spring Security: CAS Client vs. OAuth2 Client / Resource Server

In Spring Security Servlet:

| CAS Component | OAuth2 / OIDC Component | Responsibility |
| --- | --- | --- |
| `CasAuthenticationFilter` | `OAuth2LoginAuthenticationFilter`, `BearerTokenAuthenticationFilter` | Extracts protocol-specific credentials/responses |
| `CasAuthenticationProvider` | OAuth2/OIDC authentication provider or JWT/opaque provider | Protocol validation |
| `Cas20ProxyTicketValidator` | `JwtDecoder` or `OpaqueTokenIntrospector` | Backend validation |
| `ServiceProperties.service` | OAuth resource identifier / `aud` | Target must match |
| `AuthenticationUserDetailsService` | `OidcUserService`, `JwtAuthenticationConverter` | Identity/authorities mapping |
| `StatelessTicketCache` | Access token validation/cache policies | Separate lifecycles; never share caches |
| `spring-security-cas` | `spring-security-oauth2-client`, `spring-security-oauth2-resource-server` | Distinct dependencies |

**Key point:** `oauth2ResourceServer` protects **APIs receiving Bearer tokens**, `oauth2Client` helps an app **acquire and send tokens to call other APIs**, and `oauth2Login` handles OIDC/OAuth provider login. None of them automatically stands up an **Authorization Server**. Issuing real tokens requires a dedicated AS/OP with real policies and key management.

During migration, never swap `saml2Login` or `CasAuthenticationFilter` for `oauth2ResourceServer` expecting browser users to log in. Those are **different security flows**.

## 21. Spring Boot 3 / Spring Security 6: Billing Accepting JWT Access Tokens

A new Billing API can be configured as an OAuth2 Resource Server. Example using **Spring Boot 3.x, Spring Security 6.x, Java 17+** with Spring Web, Spring Security, and `spring-boot-starter-oauth2-resource-server`:

**`application.yml`**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          audiences: "billing-api"
~~~

These two properties require JWTs matching **issuer** and **audience** via Spring Boot auto-configuration. Example hostnames are solely illustrative; real systems need live AS metadata, JWKS, and valid tokens.

**Billing `SecurityFilterChain`**:

~~~java
package com.example.billing.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BillingApiSecurityConfig {

    @Bean
    SecurityFilterChain billingApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice.write")
                .anyRequest().authenticated())
            .sessionManagement(sessions -> sessions
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**This class belongs inside a Spring Boot application**, not runnable with plain JDK `javac`. It validates only the JWT and **HTTP method/path scopes** under `/api/**`. It does **not yet enforce** tenant membership, user/actor distinction, object ownership, separation of duties, or revocation freshness—those checks belong in the domain service/authorization layer.

Spring Security by default maps JWT `scope`/`scp` claims to authorities prefixed with **`SCOPE_`**. If the AS uses another claim, configure a governed `JwtAuthenticationConverter`. Never map arbitrary `groups` claims to `ROLE_ADMIN` or trust a client-asserted `tenant`.

**CSRF:** if the API accepts only Bearer tokens in the `Authorization` header with no session cookies, a tailored CSRF policy is appropriate. Never disable CSRF site-wide if the same app also serves browser cookie sessions.

## 22. Opaque Tokens + Introspection: When Revocation Is Paramount

Not every access token is a JWT. Some enterprises prefer Backend B to query the AS on incoming requests for active status; OAuth **Token Introspection (RFC 7662)** fits well.

**Spring Boot YAML (alternative to JWT)**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://auth.example.test/oauth2/introspect"
          client-id: "${BILLING_INTROSPECTION_CLIENT_ID}"
          client-secret: "${BILLING_INTROSPECTION_CLIENT_SECRET}"
~~~

**Never enable both examples simultaneously as an automatic catch-all.** Choose the token format, issuer, target API, and policy upfront.

| JWT Verification | Opaque Introspection |
| --- | --- |
| RS verifies signature/exp/iss/aud without calling AS on every request | RS queries AS/introspection endpoint for active status |
| Suited to high throughput and offline verification | Convenient when rapid revocation is required |
| Must design revocation for unexpired JWTs | Freshness depends on AS/introspection/cache policy |
| Manage JWK rotation, allowed algs, and cross-JWT confusion | Manage introspection client secrets, TLS, and AS availability |
| Token may expose claims if decoded | Opaque string reveals no claims directly |
| Must enforce identical domain authorization | Must enforce identical domain authorization |

**If caching introspection responses**, revocation speed lags by the cache TTL; never promise “instant revocation” while caching remains active.

## 23. Spring OAuth2 Client: How Does Portal Call Billing?

Portal acts as an **OAuth2 Client** to obtain an access token and attach the header:

~~~http
GET /api/invoices/37 HTTP/1.1
Host: billing.example.test
Authorization: Bearer OAUTH_ACCESS_TOKEN
~~~

Spring Security provides **`OAuth2AuthorizedClientManager`** and `RestClient`/`WebClient` integrations to select an authorized client and attach Bearer tokens on outbound calls. The manager handles `authorization_code`, `client_credentials`, and refreshes per provider config.

**However:** this convenience **does not turn a CAS authentication into OAuth user delegation**. When Portal uses CAS login while calling Billing:

- If only machine identity is needed: configure **`client_credentials`** for Portal.
- If user-delegated access is needed: you must have a **user token/authorization grant or token exchange** accepted by the AS, or a trusted bridge.
- If the AS does not yet support CAS federation, **never pretend a `client_credentials` token represents Lan**.
- If using `setDefaultOAuth2AuthorizedClient(true)`, recognize every matching `WebClient` call can attach a user token; avoid sending tokens to endpoints outside intended audience/authorization policies.
- Tokens are secrets: store safely server-side, never pushing refresh tokens into browsers or logs unnecessarily.

Configure exact client registrations and AS trust; with multiple OPs/ASs, defend against mix-up and token substitution.

## 24. Migrating Identities from CAS to OIDC/OAuth: Never Link by Email

A CAS principal is typically a CAS-issued account name like `lan`. OIDC uses `(iss, sub)`. OAuth access tokens also have `sub`, though subject semantics depend on token type/grant.

**Never do this:**

~~~text
CAS principal = "lan"
OIDC email = "lan@example.test"
=> Must be the same account (WRONG)
~~~

**Correct:** build an evidence-backed identity-links table:

~~~text
local_account
  id = acct-57

external_identity
  (provider=corp-cas, subject=lan) -> acct-57
  (issuer=https://op.example.test, subject=oidc-u-901) -> acct-57
~~~

Link records only via verified identity migration proofs, user-linking workflows protected with MFA/step-up, or authoritative enterprise directory mappings. Never merge two people's accounts on matching emails, recycled emails, or reused usernames.

**With an identity broker:** apps trust the **broker issuer's** ID Token when the broker acts as the direct OP. Never combine the broker's `sub` with an upstream issuer. Mapping CAS principal → OIDC subject requires an explicit contract, auditing, and collision handling.

## 25. Permissions and Tenants During the Parallel Phase

Suppose CAS emits group `finance-readers` while the OAuth AS issues scope `invoice.read`. Never declare those two strings equivalent automatically.

Policy template:

~~~text
ALLOW Billing.read(invoice)
  IF token/ticket valid for Billing
  AND authenticated subject mapped to active local account
  AND actor/client allowed to call Billing
  AND required protocol permission granted
  AND account is member of requested tenant
  AND invoice belongs to tenant
  AND domain rules allow viewing
ELSE DENY
~~~

On the **CAS path**, “protocol permission” may be a service/proxy policy plus a mapped internal role. On the **OAuth path**, it may be scope `invoice.read` and token audience. Both paths must converge on the **same domain authorization layer** so “CAS users” never get broader access than “OAuth users” due to filter-chain differences.

**Critical issue:** A token carrying an AS-issued tenant claim does not prove the user still belongs to that tenant after access is revoked. For sensitive operations, verify current membership server-side or enforce revocation/versioning.

## 26. Preventing Credential Confusion During Parallel CAS and OAuth Operation

During transition, Billing may need to support both CAS PTs and OAuth access tokens. Keep **paths and validators strictly separate**:

~~~text
/api/legacy/cas/**  -> CAS PT filter + CAS proxyValidate
/api/v2/**          -> OAuth2 Bearer filter + JWT/introspection
            |
            v
    verified local principal / actor context
            |
            v
       Domain authorization
~~~

**Never** write a single filter saying “if the credential starts with `PT-` use CAS, otherwise try parsing JWT, and if that fails trust a username claim.” That invites credential confusion and auth bypasses on crafted inputs.

**Recommended design:**

1. **Separate `SecurityFilterChain` beans** with non-overlapping `securityMatcher`s and explicit ordering.
2. CAS endpoints accept only CAS PTs matching the exact service URL and chain.
3. OAuth endpoints accept only access tokens from trusted AS issuers and audiences.
4. Never fall back from an invalid JWT to a CAS guest login.
5. Isolate credential storage, caches, audit tags, and replay/revocation policies.
6. Each path produces a **typed internal identity context** containing protocol, issuer/provider, subject, client/actor, tenant, and assurance.
7. Domain services accept only verified identity contexts and apply uniform policy.
8. Once cutover finishes, retire the legacy CAS path after observation and with a rollback plan.

**Never alter a global filter chain without checking other URLs** when one app serves both browser cookie logins and stateless APIs.

## 27. `StatelessTicketCache` and OAuth Token Caching Are Not Equivalent

Spring Security CAS provides `StatelessTicketCache`: the backend caches the **authentication result of an already-validated PT**, allowing result reuse over the cache TTL.

OAuth2:

- JWT resource servers normally verify the access token on every request (or apply internal optimizations per implementation); there is no “CAS one-time obligation” to bypass.
- Opaque token introspection may cache an `active=true` response per policy, accepting staleness trade-offs.
- OAuth clients may store **`OAuth2AuthorizedClient`** to reuse/refresh tokens across their lifecycle.
- **Refresh tokens** are not CAS PGTs; they follow distinct issuance, revocation, and reuse-detection rules.
- Never share cache keys or namespaces between CAS PTs and OAuth access tokens, even if strings collide.

**If migrating while keeping long-lived PT caches**, users revoked at the AS/CAS might still authenticate at Billing via stale cache hits. Define revocation SLAs and cache eviction procedures before cutover.

## 28. Standalone Java 17: Choosing the Right Delegation Model and Enforcing Scope

The JDK 17+ example below models policy at Billing across both auth paths. It **processes no real CAS tickets or OAuth JWTs**, taking inputs **assumed already verified by trusted validators**. It catches errors like CAS PT sent to an OAuth endpoint, M2M token posing as a user, wrong audience, wrong scope, wrong tenant, and delegation missing an actor.

Create **`CasOAuthDecisionDemo.java`**:

~~~java
import java.util.Set;

public class CasOAuthDecisionDemo {

    enum Kind { CAS_PROXY, OAUTH_USER, OAUTH_CLIENT, OAUTH_EXCHANGED }

    record Evidence(
            Kind kind,
            String audience,
            Set<String> rights,
            String user,
            String actor,
            String tenant,
            boolean verified) {}

    record Request(
            String audience,
            String requiredRight,
            String tenant,
            boolean needsUser,
            boolean needsActor) {}

    static String decide(Evidence e, Request r) {
        if (!e.verified()) {
            return "DENY_UNVERIFIED";
        }

        boolean casEndpoint = r.audience().startsWith("cas:");
        if (casEndpoint != (e.kind() == Kind.CAS_PROXY)) {
            return "DENY_PROTOCOL";
        }
        if (!r.audience().equals(e.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!r.tenant().equals(e.tenant())) {
            return "DENY_TENANT";
        }
        if (!e.rights().contains(r.requiredRight())) {
            return "DENY_RIGHT";
        }
        if (r.needsUser() && e.user() == null) {
            return "DENY_USER_CONTEXT";
        }
        if (r.needsActor() && e.actor() == null) {
            return "DENY_ACTOR_CONTEXT";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Request legacy = new Request(
                "cas:billing", "invoice.read", "north", true, true);
        Request oauth = new Request(
                "oauth:billing", "invoice.read", "north", true, true);

        Evidence cas = new Evidence(
                Kind.CAS_PROXY, "cas:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence m2m = new Evidence(
                Kind.OAUTH_CLIENT, "oauth:billing",
                Set.of("invoice.read"), null, "portal-a", "north", true);
        Evidence delegated = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence noActor = new Evidence(
                Kind.OAUTH_USER, "oauth:billing",
                Set.of("invoice.read"), "lan", null, "north", true);
        Evidence wrongAudience = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:admin",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence wrongScope = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.write"), "lan", "portal-a", "north", true);
        Evidence wrongTenant = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "south", true);
        Evidence notVerified = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", false);

        System.out.println("CAS legacy: " + decide(cas, legacy));
        System.out.println("CAS as OAuth: " + decide(cas, oauth));
        System.out.println("M2M as user: " + decide(m2m, oauth));
        System.out.println("Exchanged token: " + decide(delegated, oauth));
        System.out.println("Missing actor: " + decide(noActor, oauth));
        System.out.println("Wrong audience: " + decide(wrongAudience, oauth));
        System.out.println("Wrong scope: " + decide(wrongScope, oauth));
        System.out.println("Wrong tenant: " + decide(wrongTenant, oauth));
        System.out.println("Invalid evidence: " + decide(notVerified, oauth));
    }
}
~~~

Run:

~~~bash
javac CasOAuthDecisionDemo.java
java CasOAuthDecisionDemo
~~~

**Exact stdout:**

~~~text
CAS legacy: ALLOW
CAS as OAuth: DENY_PROTOCOL
M2M as user: DENY_USER_CONTEXT
Exchanged token: ALLOW
Missing actor: DENY_ACTOR_CONTEXT
Wrong audience: DENY_AUDIENCE
Wrong scope: DENY_RIGHT
Wrong tenant: DENY_TENANT
Invalid evidence: DENY_UNVERIFIED
~~~

**Explanation:** a CAS PT works solely within the CAS trust boundary; M2M tokens lack user context; exchanged tokens can carry both user and actor; wrong audience, scope, tenant, or unverified evidence are all denied.

**Limitations:** `Evidence.verified=true` is an **educational assumption**, not real validation. Production requires CAS `TicketValidator`, OAuth JWT decoders/introspectors, client authentication, replay protection, account/tenant policies, and real token exchange. `rights` for CAS in this demo represent **app-granted internal permissions**, **not CAS OAuth scopes**. Never use this demo class as a security filter or Authorization Server.

## 29. Phased Migration Plan

### Phase 0 — Discovery and Success Criteria

1. Inventory CAS Server, client versions, service registry, PGT/PT consumers, `pgtUrl` callbacks, and proxy chains.
2. List APIs, endpoints, user/machine identities, tenants, and current authorization sources.
3. Identify which services genuinely need **user delegation** vs. userless M2M.
4. Measure baselines: CAS validation latency, ticket issuance rates, proxy failures, logins/logouts, and active sessions.
5. Select a governed OAuth AS/OP supporting token exchange/opaque/JWT/PKCE as needed.
6. Define token audiences, scopes, user/actor claims, tenant representations, and domain policies.
7. Define revocation, retention, compliance, and rollback requirements.

### Phase 1 — Trust and Identity Mapping Preparation

1. Register OAuth clients and Resource Servers.
2. Establish issuer/JWKS/introspection trust, signing key rotation, and TLS.
3. Build CAS principal ↔ local account ↔ OIDC `issuer+sub` identity links where needed.
4. Never auto-link solely on matching email.
5. Define AS scope-issuance policy as the **intersection of user + actor + audience + tenant rights**.
6. Choose the migration pattern per caller: `client_credentials`, OIDC login, token exchange, or bridge.
7. Assign separate owners for CAS session revocation and OAuth token revocation.

### Phase 2 — Build Parallel OAuth Path

1. Add `/api/v2/**` or a new route guarded by an OAuth Resource Server validator.
2. Keep CAS proxy `/api/legacy/**` unchanged and strictly scoped.
3. Implement the OAuth Client or trusted bridge and run end-to-end validators.
4. Enforce `aud`/scope/client actor/tenant/object checks alongside business policies.
5. Redact CAS tickets and OAuth tokens from logs.
6. Write integration tests and security tests covering both paths.
7. Add metrics broken down by protocol and outcome to spot privilege errors or failure spikes.

### Phase 3 — Canary and Traffic Ramp-Up

1. Pick a low-risk tenant/service and verified test/user accounts.
2. Run **shadow authorization decisions** without executing write/payment side effects twice.
3. Compare CAS vs. OAuth decisions on identical operations; investigate every permission mismatch.
4. Test JWT/opaque token expiry, CAS ticket replay, PGT rotation, and OIDC sessions.
5. Test outages across AS, CAS, JWKS, Redis/cache, and reverse proxies.
6. Ramp traffic based on agreed success, latency, and security criteria.
7. Keep a clean routing rollback switch—never temporarily accept all tokens.

### Phase 4 — Cutover

1. Shift routing via controlled feature flags or gateway rules.
2. Prevent legacy CAS PTs from calling new OAuth-only endpoints automatically.
3. Monitor 401 vs. 403 rates, audience mismatches, failed exchanges, and tenant denials.
4. Evaluate active sessions and surviving cached CAS `Authentication`s.
5. Set a cutoff date to stop issuing PGT/PTs for migrated APIs.
6. Restrict or remove legacy CAS filters/routes on schedule once zero active clients remain.

### Phase 5 — Retire and Maintain

1. Confirm all consumers migrated and clean up straggling clients.
2. Revoke retired CAS PGT credentials, unused service registrations, and old PT caches.
3. Maintain AS key lifecycles, token revocation, and client secret rotation.
4. Archive audits of migrated identity links/scopes and security approvals.
5. Update runbooks, SLOs/SLAs, and alerts for the new architecture.
6. Retire CAS login only if **zero** other apps depend on it; migrating Billing API alone does not mean you can shut down the entire CAS Server.

## 30. Migration Test Matrix

| Case | Scenario | Mandatory Outcome |
| --- | --- | --- |
| 01 | Valid CAS PT hits CAS endpoint | CAS validates exact service and proxy chain |
| 02 | PT sent to OAuth-only endpoint | Rejected, no fallback |
| 03 | OAuth token sent to CAS-only endpoint | Rejected, never parsed as PT |
| 04 | Billing CAS PT sent to Payroll | Rejected for wrong service |
| 05 | CAS PT replayed after CAS validation | Follows explicit single-use / cached-auth policy |
| 06 | CAS proxy chain contains unapproved proxy | CAS/backend rejects |
| 07 | PGT revoked yet bridge still receives request | Bridge fails closed |
| 08 | OAuth JWT has invalid signature | 401 |
| 09 | JWT has valid signature yet wrong issuer | 401 |
| 10 | JWT has valid signature yet wrong audience | 401 |
| 11 | JWT expired or `nbf` in future | 401 |
| 12 | Access token from another AS sent to Billing | Rejected (mix-up defense) |
| 13 | ID Token sent to Billing as Access Token | Rejected (token type/audience) |
| 14 | Access token has right `aud` yet lacks scope | 403 |
| 15 | User token used as M2M client token | Blocked by client policy |
| 16 | M2M `client_credentials` fakes user delegation | Never treated as Lan |
| 17 | RFC 8693 token exchange unsupported by AS | Controlled denial; never self-mint tokens |
| 18 | Token exchange receives forged `subject_token` | AS rejects |
| 19 | Token exchange actor violates policy | AS rejects or downscopes per policy |
| 20 | Bridge skips CAS PT validation | Never issues OAuth token |
| 21 | Bridge receives CAS PT for wrong service | Issues no token |
| 22 | CAS→OIDC identity link lacks proof | Never auto-links by email |
| 23 | Client granted `invoice.read` requests `invoice.write` | AS/RS rejects escalation |
| 24 | User in tenant north requests south | Domain policy rejects |
| 25 | User disabled after token issuance | Revocation/freshness policy enforced |
| 26 | JWT revoked before expiry | Enforced within denylist/version/introspection SLA |
| 27 | Opaque token introspection returns `active=false` | 401 |
| 28 | Introspection outage | Fails closed when no valid evidence exists |
| 29 | CAS logout while OAuth token remains valid | Documented behavior; never promise automatic revocation |
| 30 | OAuth logout while CAS TGT remains valid | Clear policy; avoid false global-logout claims |
| 31 | Two filter chains overlap on URLs | Tests catch and fix matchers/ordering |
| 32 | Gateway spoofs `Host`/`X-Forwarded` headers | Trusted service URL/issuer remains unchanged |
| 33 | Two-hop token exchange | Audit actor chain preserved where policy requires |
| 34 | Shadow traffic includes write requests | Never executes business mutations twice |
| 35 | Rollback to legacy route | Never uses credentials/caches across trust boundaries |
| 36 | Retire CAS service | Zero dependent active clients or tickets remain |

A test observing only **HTTP 200** is insufficient. Prove **exact identity, actor, audience, permission, tenant, object, and revocation**. Distinguish 401 (unauthenticated) from 403 (authenticated yet unauthorized).

## 31. Common Pitfalls When “Moving from CAS to OAuth2”

| Pitfall | Risk | Right Approach |
| --- | --- | --- |
| Putting a PT in `Authorization: Bearer` and calling it OAuth | Resource Server lacks AS/token contract | New token must be minted by AS and validated per protocol |
| Using CAS username as `sub` in app-signed JWT | Impersonation and broken trust boundaries | Evidence-backed mapping and trusted AS/broker |
| Using `client_credentials` for all user-initiated calls | Loss of user context and auditability | OIDC user grant or valid token exchange |
| Converting CAS groups to scopes via string replace | Over-permissioning and tenant collisions | Allowlisted policies and domain authorization |
| Letting Billing accept any validly signed JWT | Cross-audience / token confusion | Check issuer, `aud`, token type, expiry, and key trust |
| Using ID Token as an API Access Token | Wrong token purpose | Accept solely Access Tokens scoped for Billing |
| Long-lived unrevocable JWTs | Revoked permissions persist | Short TTLs / introspection / denylist / epochs per SLA |
| Keeping long-lived cached CAS `Authentication` during cutover | Stale permissions linger concurrently | Evict cache / enforce revocation policy |
| Conflating actor and subject | Hides which service acted | Token exchange/`act`, client auth, and audit |
| Changing `sub`/issuer while linking by email | Account takeover | Verified dual identity links |
| Forcing Token Exchange when AS lacks it | Unsupported grant and unsafe workarounds | Verify AS features or use an appropriate broker/flow |
| Skipping scope checks at the RS | Right audience yet overly broad access | Enforce scopes + domain/tenant checks |
| Dynamic redirect URIs from browser input | Open redirects / token leaks | Exact pre-registered redirects, PKCE/state |
| Enabling `acceptAnyProxy` during migration | Overly broad proxy trust | Approved proxy allowlists and strict targets |
| Disabling CSRF site-wide because APIs use Bearer | Weakens browser cookie flows | Separate `SecurityFilterChain`s and policies |
| “SAML/OIDC/CAS are all SSO” so share one validator | Confused deputy / cross-protocol injection | Dedicated validators and normalized trusted identity contexts |

**Conclusion:** Switching protocols must never weaken existing guarantees on **CAS service restrictions, proxy-chain restrictions, and local entitlement checks**. OAuth2 improves architecture only when those boundaries are explicitly represented and verified end-to-end.

## 32. Migration Incidents: Troubleshooting Runbook

### A. Billing Returns 401 When Portal Switches from CAS PT to OAuth Token

1. Verify whether Portal is calling the OAuth-only endpoint or the legacy CAS endpoint.
2. Check token issuance status without logging raw tokens.
3. Inspect JWT issuer/audience/key/expiry or opaque token introspection active state.
4. Verify the OAuth client is authorized by the AS for the current grant.
5. For Token Exchange, verify `subject_token`/`actor_token` types and AS trust.
6. Never fall back to accepting CAS PTs on the new endpoint just to avoid errors.
7. If rolling back, use approved routing back to the CAS endpoint with a fresh ticket—never reuse cross-protocol credentials.

### B. OAuth Token Is Valid, Yet Billing Returns 403

1. Check `invoice.read` or `invoice.write` scopes.
2. Check whether the actor/client is authorized to call Billing on the user's behalf.
3. Check local account linking, tenant membership, and object ownership.
4. Check role-mapping casing/formatting and stale data.
5. Never add `ROLE_ADMIN` as a temporary workaround.
6. Distinguish migration-induced authorization mismatches from token validation errors.

### C. User Logged Out of CAS, Yet OAuth Token Still Calls APIs

1. Check whether it is an unexpired JWT or an active opaque token.
2. Verify whether CAS logout propagates to AS/token revocation.
3. If not, acknowledge the **two independent lifecycles**.
4. Revoke refresh/access tokens via AS capabilities or bump account/session epochs.
5. Test resource server caches/TTLs and APIs that already accepted the token.
6. Adjust UX messaging if global logout cannot be guaranteed.

### D. CAS Proxy Breaks When Introducing a Bridge

1. Check PGT/`pgtUrl` certificates, CAS service registry, and the bridge's `targetService`.
2. Check `TicketValidator`/allowed proxy chains on the backend/bridge.
3. Check whether the one-time PT was already consumed elsewhere.
4. Ensure the bridge does not retry an old PT in a loop.
5. Verify the AS authorizes the bridge client and token exchange/issuance policy.
6. If any link fails, never self-issue an OAuth token by trusting a raw CAS username.

### E. Permissions Leak Across Tenants or Expand Beyond Prior Scope

1. Halt canary or roll back immediately per incident severity.
2. Invalidate improperly issued tokens/sessions via revocation/expiry policies.
3. Compare CAS principal+proxy chain, OAuth subject+actor, local account, and tenant.
4. Audit scope mappings, request tenant, and resource ownership.
5. Investigate cross-tenant exposure, audit affected objects, and notify per obligations.
6. Resume rollout only after security owners approve fixes and regression tests.

## 33. Self-Assessment Questions

**1. Is CAS Proxy an OAuth2 authorization grant?**  
No. CAS Proxy delegates authentication via PGT/PTs and proxy chains, whereas OAuth2 models authorization and AS-issued access tokens.

**2. Are a PT and an OAuth Access Token equivalent in lifecycle?**  
No. PTs follow CAS single-use validation; OAuth access tokens are normally reusable against the right audience within their lifetime. Spring's PT cache reuses `Authentication` only locally at the service.

**3. What should an app A calling B with no user choose?**  
Normally `client_credentials`, using client identity and scopes scoped to B—never a fake CAS user.

**4. What should Portal do when it has a user and wants to call Billing on the user's behalf?**  
Use a user-delegated token with Billing as audience—considering RFC 8693 Token Exchange if actor lineage is needed and supported by the AS, or a controlled trusted bridge while still on CAS.

**5. Can a CAS PT be converted into an access token by Base64 decoding or adding a `Bearer` prefix?**  
No. Fresh access tokens must be issued by a trusted AS per grant and policy.

**6. Is an OAuth2 Access Token always a JWT with a human user `sub`?**  
No. Opaque tokens exist; `sub` can be the client in `client_credentials`, and semantics depend on profile/AS.

**7. When the AS grants `scope=invoice.read`, can Billing skip checking tenant membership?**  
No. Scopes and audiences never replace domain authorization.

**8. What role does OIDC play during migration?**  
OIDC provides RP authentication with ID Tokens and `(iss, sub)`, suited to web login/federation; ID Tokens are not API Access Tokens.

**9. Does Token Exchange automatically revoke the output token when the input token is revoked?**  
Not by default. RFC 8693 states this is not automatic lifecycle coupling; implementations must handle revocation separately.

**10. Can you keep CAS login and migrate Billing API to OAuth first?**  
Yes, with an appropriate AS/bridge/trust mapping, isolated validator paths, and a phased migration plan.

**11. Why must the proxy chain be checked when receiving a PT?**  
Because PTs travel through acting services; Billing must trust only approved proxies.

**12. Why shouldn't `client_credentials` be used “on behalf of Lan”?**  
Because it proves only the client's identity/rights and carries no user-delegated authorization by default.

**13. Does local JWT verification enable instant permission revocation?**  
Not by default. It requires short TTLs, introspection/denylist/version checks, or matching policies.

**14. Does CAS logout automatically sign out OAuth apps and revoke all tokens?**  
No. The two systems have independent session/token lifecycles; synchronization requires explicit integration.

**15. What matters most during the parallel-run phase?**  
Separating trust boundaries, enforcing protocol/audience/actor/tenant checks, keeping domain authorization consistent, and maintaining safe rollback.

## 34. Pre-Cutover Production Checklist

- [ ] Understood CAS PGT/PT/ST, single-use validation, `targetService`, `pgtUrl`, and proxy chains.
- [ ] Clearly distinguished **proxy authentication** from **OAuth delegated authorization**.
- [ ] Inventoried all active CAS consumers, service registries, and proxy chains.
- [ ] Have a trusted AS/OP; never self-mint JWTs from unverified CAS usernames.
- [ ] Chose the right flow per use case: OIDC Authorization Code + PKCE, `client_credentials`, or RFC 8693 where supported.
- [ ] Token Exchange is formally supported by the AS; never assume a CAS PT is a standard `subject_token`.
- [ ] Any bridge validates CAS PTs for exact service and allowed proxy chain, authenticates actor/client, and follows AS issuance policy.
- [ ] CAS ↔ local account ↔ OIDC identity mappings are verified, never auto-linked by email.
- [ ] Defined OAuth audiences/resources, scopes, client IDs, and token types per API.
- [ ] Billing Resource Server validates issuer, signature/introspection, audience, expiry, and token type.
- [ ] Scopes never replace domain authorization: tenant membership, object ownership, and account status.
- [ ] Where a delegated actor is needed, subject/actor semantics and `act` claims have an end-to-end contract.
- [ ] Never substitute `client_credentials` for user delegation.
- [ ] JWT/opaque token lifecycles, refresh/revoke/introspection/caches, and SLAs are clearly defined.
- [ ] CAS logout/TGT/PGT revocation is never confused with OAuth token revocation.
- [ ] Legacy CAS filter and OAuth Bearer filter separate endpoints/matchers with no fallback on validation failure.
- [ ] CSRF/login, PKCE/state/nonce, redirect URIs, mTLS/TLS, and trusted proxy headers are verified.
- [ ] Zero logging of PT/PGTs, access/refresh tokens, raw assertions, or client secrets.
- [ ] Tests cover valid/invalid service, `aud`, scope, actor, tenant, expired/revoked credentials, and cross-protocol confusion.
- [ ] Canary/shadow authz, rollout metrics, security approvals, and rollback procedures are in place.
- [ ] Never retire the CAS Server while dependent clients remain, and never relax trust to bypass migration errors.

## 35. Conclusion

**CAS Proxy is not an older version of OAuth2 Access Tokens.** CAS Proxy uses PGT/PTs and proxy chains to propagate authentication context across CAS services; OAuth2 uses an AS, grants, access tokens, scopes, and audiences to authorize resource access. When a user is involved, distinguish **subject** from **acting client**; when no user is involved, `client_credentials` may fit. **OIDC** solves authentication/login for modern clients; **RFC 8693 Token Exchange** is one way to convey a delegated actor when supported by the AS.

**No single option fits every project.** You can **keep CAS** if legacy systems are stable and narrow; **move M2M to `client_credentials`**; **adopt OIDC Authorization Code + PKCE** for new web logins; **use Token Exchange** for user on-behalf-of; or **deploy a trusted CAS→OAuth bridge** to migrate APIs incrementally. Whichever path you pick must preserve or strengthen assurances: **trusted issuer/CAS, exact target/audience, verified user+actor, least privilege, tenant isolation, revocation, and auditing**.

### Official References

- Apereo CAS — CAS Protocol Specification: proxy callbacks, `/proxy`, `/proxyValidate`, PGT/PTs, and proxy chains: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Spring Security — CAS Authentication and Proxy Ticket Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 9700 (January 2025) — Best Current Practice for OAuth 2.0 Security, PKCE, mix-up, and token security: https://www.rfc-editor.org/rfc/rfc9700
- IETF RFC 8693 — OAuth 2.0 Token Exchange, `subject_token`, `actor_token`, and `act`: https://www.rfc-editor.org/rfc/rfc8693
- IETF RFC 8707 — Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- IETF RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP): https://www.rfc-editor.org/rfc/rfc9449
- OpenID Connect Core — ID Tokens and Authorization Code Flow: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 Client Authorized Clients and token use: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Resource Server JWT `issuer-uri` and `audiences`: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Token introspection: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
