# Testing Cross-IdP or Cross-Tenant Access and Identity Collisions in SSO

## 1. The Problem: Two People Can Share a Username Without Being the Same Account

A Spring Boot application supports **Single Sign-On (SSO)** across multiple enterprises, branches, partners, or **Identity Providers (IdPs)**. For example:
- Company A uses OIDC issuer `https://idp-a.example.org`.
- Company B uses OIDC issuer `https://idp-b.example.org`.
- Partner C uses SAML IdP entityID `https://saml-c.example.org/metadata`.
- Each company is a **tenant** inside the same application.

Two completely different people can simultaneously hold:
- Username `alex`.
- Email `shared-address@example.org`.
- OIDC `sub=12345` under **two different issuers**.
- SAML `NameID=alex` yet different IdP entityIDs.
- Groups `Admins` or `Finance` in two independent directories.

If the application binds users to accounts by email, username, or `sub` **without the issuer**, a user logging in from IdP B can become A's account. If the application checks only `ROLE_ADMIN` without checking tenant/resource ownership, Company A's admin can access Company B's data.

This Knowledge article belongs to **Spring Security - federation → SSO Testing**, topic **“Testing Cross-IdP or Cross-Tenant Access and Identity Collisions.”**

> **Principle:** authenticating the right IdP is not enough; you must then chain *external identity → app account → tenant membership → resource permissions*. Entities sharing the same name string must never be merged automatically.

### Learning Objectives

After this lesson, you will be able to:
1. Distinguish **IdP**, **issuer/entityID**, **client/registrationId**, **tenant**, **app-local account**, and **resource owner**.
2. Construct OIDC identity keys using the **`(iss, sub)`** pair rather than email or bare `sub`.
3. Build SAML bindings using issuer and subject identifiers with matching format/qualifiers; avoid transient `NameID`s.
4. Test trust isolation across OIDC/SAML, CAS, Kerberos/SPNEGO, and proxy pre-auth where applicable.
5. Design negative tests for wrong IdP signer/issuer, wrong OIDC audience, callback mix-ups, IdP confusion, colliding group names, and tenant parameter tampering.
6. Test email/username/`NameID` collisions, account linking, JIT provisioning, and user invitations.
7. Distinguish **authentication failures** from **authorization failures**, testing at both layers.
8. Handle multi-tab/multi-IdP login sessions, UI tenant switching, and account switching.
9. Configure Spring Security OIDC/SAML with strict trust boundaries and verify APIs per version.
10. Run a standalone Java 17 demo covering scoped identity and tenant authorization.
11. Assess cross-tenant leaks in repositories, APIs, caches, background jobs, and file downloads.
12. Build a QA matrix with evidence covering both blocked conditions and valid paths.

**Illustrative context:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x; tenant data isolation may use a shared database, separate schemas, or separate databases. This guide uses `example.org` domains and synthetic data; never copy production keys/tokens into tests.

---

## 2. Distinguishing IdP, Tenant, and Account

| Concept | Example | Meaning |
| --- | --- | --- |
| IdP / OpenID Provider | `https://idp-a.example.org` | Authenticating party issuing ID Tokens/SAML Assertions |
| OIDC issuer (`iss`) | `https://idp-a.example.org` | Namespace and trusted source of the OIDC subject |
| OIDC subject (`sub`) | `12345` | User within that issuer; not globally unique |
| OIDC `clientId`/`registrationId` | `portal-a-client`, `corp-a` | App/client and Spring registration; **not** tenant user identity |
| SAML IdP `entityID` | `https://saml-c.example.org/metadata` | Registered asserting party |
| SAML `NameID` | `alex` | Subject identifier per IdP format/qualifiers |
| App account ID | `acct-abc-01` | Immutable internal key for ownership and auditing |
| Tenant ID | `tenant-a` | Authorization and resource boundary inside the app |
| Membership | `acct-abc-01 ∈ tenant-a` | Right to participate in a tenant; never self-asserted by user |
| Resource owner | `document-007 belongs to tenant-b` | Data requiring dedicated ACL/tenant checks |
| Login session | Browser-side `JSESSIONID` | App login state; grants no automatic access to other tenants |

**IdP and tenant need not map one-to-one.** One enterprise IdP may authenticate users belonging to multiple app tenants. One tenant may accept multiple IdPs during migrations or alliances. Therefore:
- Never assume `issuer = tenant`.
- Never assume `clientRegistrationId = tenantId`.
- Never treat an email domain `@company.com` as tenant authorization.
- Maintain a policy table defining **which tenant trusts which issuer/registration** and **which user holds membership in that tenant**.
- Enforce resource permissions **right at the resource boundary**.

### OIDC Scope

OpenID Connect Core mandates `sub` be unique and never reassigned within an issuer; the **`iss+sub` pair** is the stable identifier a Relying Party can rely upon. Claims like `email`, `preferred_username`, and `name` are not guaranteed stable or unique across issuers or over time.

Example:

~~~text
(https://idp-a.example.org, sub=12345) -> acct-A
(https://idp-b.example.org, sub=12345) -> acct-B

acct-A != acct-B
~~~

Querying solely `WHERE sub = '12345'` risks merging two different people.

### SAML Scope

SAML2 `NameID` must be evaluated alongside:
- Asserting Party / Response and Assertion `Issuer`;
- `NameID` `Format` (persistent, transient, `emailAddress`, unspecified...);
- `NameQualifier`/`SPNameQualifier` when used by the profile;
- IdP–SP/`RelyingPartyRegistration` relationship;
- Matching trust certificates/metadata.

A SAML transient `NameID` is not a long-term account key. A persistent `NameID` may be scoped to a specific IdP–SP pair, not a global identifier across all IdPs/SPs.

## 3. Two Distinct Error Layers: Wrong Identity vs. Wrong Permission

A cross-tenant scenario has two rejection points:

**AuthN / federation:** IdP B attempts to feed a SAML Response into IdP A's registration or an OIDC code/token into client A. The provider must reject when issuer, signature, trust, audience, recipient, state/nonce, or binding mismatches.

**AuthZ / application:** IdP B **validly** authenticates user B, who then requests `/tenants/tenant-a/reports/42` despite holding membership only in tenant B. Rejection here must happen via **tenant/resource authorization**, not because IdP B's signature failed.

| Input | AuthN | AuthZ | Outcome |
| --- | --- | --- | --- |
| User A from IdP A, tenant A report, authorized | Pass | Pass | Allow |
| IdP B token fed into IdP A auth path | Fail | Never reaches business logic | Deny |
| User B from IdP B, tenant A report | Pass | Fail | Deny |
| User B shares email with A | Passes for B | B lacks tenant A grant | Deny |
| User A is Tenant A Admin, tenant B report | Pass | Fail | Deny |
| Unknown IdP emits A's issuer claim signed by rogue key | Fails cryptographic trust | Never reaches business logic | Deny |
| User belongs to both A and B with valid memberships | Pass | Per selected tenant's grants | Controlled Allow |
| User A uses old session after membership revoked | Session may remain | Must refresh/revoke | Deny |

**Do not write tests at the wrong layer:** to test **resource isolation**, have user B log in validly first and then request resource A. Sending an invalid-signature token fails at AuthN and **proves nothing** about repository/controller tenant ACLs.

---

## 4. Login Flow and Two-Stage Resource Checks

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring SP
    participant IDP as Selected IdP
    participant DB as Identity and membership store
    participant API as Business resource
    U->>SP: Choose SSO for tenant B
    SP->>SP: Pick only registration/IdP trusted by tenant B
    SP->>IDP: OIDC auth request or SAML AuthnRequest
    IDP-->>SP: Token or signed SAML Response
    SP->>SP: Verify issuer, signer, audience, state, timing...
    alt Protocol invalid
        SP-->>U: Authentication failure
    else Protocol valid
        SP->>DB: Resolve scoped external identity -> account
        DB-->>SP: Account B and tenant memberships
        SP->>SP: Create local Authentication/session
        U->>API: GET /tenants/tenant-A/documents/42
        API->>DB: Check account B membership and resource tenant
        alt No permission in tenant A
            API-->>U: 403 or deny by app policy
        else Proper A membership and resource grant
            API-->>U: Authorized response
        end
    end
~~~

A registration route such as `/oauth2/authorization/corp-b` or `/saml2/authenticate/corp-b` only selects how login **begins**. It is never proof of tenant ownership. Neither `?tenant=tenant-a`, `Host` headers, vanity domains, redirect URLs, nor `RelayState` values grant membership by themselves.

## 5. Minimum Data Model Against Identity Collisions

### 5.1 Separating External Identities from Accounts

~~~sql
CREATE TABLE app_accounts (
    account_id UUID PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    security_epoch BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE external_identities (
    identity_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    protocol VARCHAR(24) NOT NULL,
    issuer_namespace VARCHAR(512) NOT NULL,
    subject_value VARCHAR(512) NOT NULL,
    subject_format VARCHAR(255),
    active BOOLEAN NOT NULL,
    UNIQUE (protocol, issuer_namespace, subject_value, subject_format)
);

CREATE TABLE tenant_memberships (
    account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    tenant_id UUID NOT NULL,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE tenant_grants (
    account_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    permission VARCHAR(64) NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission)
);
~~~

This DDL is **illustrative**, not a production-ready migration. On PostgreSQL, a unique constraint containing nullable `subject_format` requires handling NULL semantics to prevent duplicates effectively (e.g., non-null/canonical formats or appropriate indexes). Define exact namespaces/qualifiers per SAML, CAS, SCIM, LDAP, and tenant policy rather than assuming one generic schema covers every protocol.

Rules:
1. Each **verified** external identity maps to at most one active app account.
2. One app account may hold multiple external identities **if linked via an adequately evidenced linking workflow**.
3. Never auto-map by unscoped email/username/`NameID`.
4. Tenant membership must never be inferred solely from the identity issuer.
5. Business resources must store **stable tenant IDs / owner account IDs**, never owner emails as access rights.

### 5.2 Tenant-Scoped Resources

~~~sql
CREATE TABLE documents (
    document_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    title VARCHAR(255) NOT NULL
);
~~~

When retrieving a document, the service must verify:
- Account active;
- Selected tenant has an active membership;
- `Document.tenantId` **matches** the current tenant;
- Permission on the document (role, owner, ACL);
- If team/project ownership applies, verify that scope too.

**Never query solely by `document_id` and rely on hidden UI buttons.** Guessable URLs or GraphQL node IDs allow cross-tenant access if services omit object-level checks.

### 5.3 Tenant Selection from Trusted Contexts

One person may genuinely belong to two tenants. Allowing UI switching between A and B is valid, provided the server verifies:
- The account currently holds active membership in the requested tenant;
- Tenant selection is bound to server-side session/context or revalidated on every request;
- All resource queries and grants are scoped to the selected tenant;
- Switching tenants never retains caches/roles from the prior tenant;
- Any tenant header/body parameter is merely **request context**, never authorization.

## 6. Identity Collision Matrix to Test

| What Collides? | Example | What Must Hold |
| --- | --- | --- |
| OIDC `sub` | A and B both `sub=001` | Scope `iss+sub` maps to two separate accounts |
| Email | A/B share `alex@example.org` | No auto-merge; B never sees A |
| `preferred_username` | A/B both `alex` | Never used as account lookup key |
| SAML `NameID` | Two IdPs both emit `NameID` `alex` | Scope by IdP/format/qualifiers |
| Misconfigured SAML `entityID` | A/B reuse same issuer label | Detect config conflict; never trust wildcards |
| AD `sAMAccountName` | Two domains both have `alex` | Scope directory/domain/immutable object |
| Kerberos principal | `alex@A.REALM` vs `alex@B.REALM` | Never drop realm when mapping users |
| CAS username | Two CAS servers both return `alex` | Scope CAS server/service + stable attr contract |
| Group name | A and B both have group `Admins` | Role applies solely to the right tenant |
| Tenant slug | `sales` in two organizations | Use registered tenant ID/namespace |
| Invitation email | B receives email previously owned by A | Cannot claim A's invite by email alone |
| SCIM `externalId` | Two provisioning clients both send `externalId=42` | Scope provisioning domain |
| App account alias | Username rename/reuse | Anchored on immutable app account ID; never reassigned |
| Cache key | `cache["report-42"]` | Must include tenant/subject/policy version |
| Session principal | Browser switches from IdP A to B | Never reuse A's local account/roles |

For these cases, **matching strings are intentional test fixtures**; random non-colliding values fail to catch missing scoping.

## 7. Multi-IdP OIDC: Checking Issuer, Client, State, and Nonce

Typical OIDC Authorization Code Flow:
1. Spring selects `ClientRegistration` from configured approved IdPs.
2. Redirects the browser to the Authorization Endpoint with `state` and `nonce`/PKCE per client/profile.
3. Browser returns to `/login/oauth2/code/{registrationId}` with the authorization code.
4. Client matches the callback against the saved authorization request and exchanges the code **with the right token endpoint/client credentials**.
5. Spring OIDC validates ID Token signature, `iss`, `aud`, expiry, `nonce`, and applicable constraints.
6. App maps verified `iss+sub` to the app account, then checks membership/resources.

**Never trust a JWT simply because Base64-decoding reveals an email and issuer.** Signatures, issuer metadata/JWKS, client audience, token type, and protocol constraints must be enforced by a trusted verifier.

### 7.1 Same `sub` from Two Issuers

~~~json
{
  "iss": "https://idp-a.example.org",
  "sub": "123",
  "aud": "portal-client-a",
  "email": "alex@example.org"
}
~~~

~~~json
{
  "iss": "https://idp-b.example.org",
  "sub": "123",
  "aud": "portal-client-b",
  "email": "alex@example.org"
}
~~~

These are **illustrative claim bodies**, not signed tokens and not trusted inputs. In real tests, issue validly signed tokens/authorization responses from the test IdPs and validate against the matching registrations.

Expectations:
- `(idp-a,123)` → `acct-A`.
- `(idp-b,123)` → `acct-B`.
- Never merge due to identical `sub` or email.
- Session B never inherits A's privileges.

### 7.2 Wrong Issuer with Valid Signature

A negative test can use **two separately signing test IdPs**:
- Login starts via client A.
- Callback carries B's response/token via the test harness.
- The app must not validate that token using B's JWKS for A.
- Must deny before creating an app session.

Do not just edit the `iss` string in a signed JWT and resend it. That breaks the signature and tests only tampering. To test issuer logic, mint a token with the wrong issuer **yet a valid signature** using the corresponding test key and assert **mismatch against expected issuer**.

### 7.3 Wrong Audience / `clientId`

IdP A may issue an ID Token for `portal-client-a2`. That token must be rejected by `portal-client-a1` because `aud` mismatches. When multiple audiences appear, enforce `azp` and applicable OIDC Core rules.

- Proper test case has valid signature, valid issuer, and valid timestamps, with **only audience/client wrong**.
- Never use an **ID Token** in place of an **OAuth2 access token** for APIs.
- For JWT access tokens at resource servers, validate `aud` intended for the API per token profile/contract; never treat `aud=frontend-client` as sufficient for all APIs.
- Test that app B's token cannot access app A's APIs even under the same issuer.

### 7.4 OAuth2 Mix-Up Attacks

When a client supports multiple Authorization Servers, it must preserve the exact binding **authorization request → expected issuer/token endpoint/client registration → authorization response**. If code origins are confused, an authorization code can be sent to the wrong token endpoint.

RFC 9207 defines the `iss` authorization response parameter to identify the Authorization Server and defend against **mix-up attacks**. Where supported by server/client, the client verifies the exact expected issuer alongside other protocol/profile countermeasures.

QA scenario:
1. Start login through IdP A.
2. Keep A's browser session/saved `OAuth2AuthorizationRequest`.
3. Inject a callback response from IdP B via the test IdP harness.
4. Ensure A's code is never sent to B's token endpoint and no wrong `Authentication` is created.
5. When `iss` is present per RFC 9207, verify it matches the expected issuer.
6. Prevent callers from swapping `registrationId` or `state` to switch server contexts.
7. Validate `state`, `nonce`, and PKCE per flow without bypassing validators.

**Spring Security handles OAuth2 Login per configured APIs and flows**, yet tests must prove custom resolvers, login links, dynamic tenant discovery, or custom success handlers never break issuer/registration associations.

## 8. Spring Security OAuth2 Login: Two Independently Configured Registrations

Spring Boot config looks like (assuming both providers support valid discovery and endpoints):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: corp-a
            client-id: portal-client-a
            client-secret: example-secret-from-secret-manager
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          corp-b:
            provider: corp-b
            client-id: portal-client-b
            client-secret: example-secret-from-secret-manager
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-a:
            issuer-uri: https://idp-a.example.org
          corp-b:
            issuer-uri: https://idp-b.example.org
~~~

**This is an illustrative config, not real secrets or live endpoints.** In production, pull secrets from a secret manager/controlled env, register exact redirect URIs at each IdP, use trusted issuer discovery, and never let users supply arbitrary issuer URIs. `registrationId` identifies a **client registration**, not proof the user belongs to a tenant.

Typical login links:
- `/oauth2/authorization/corp-a`.
- `/oauth2/authorization/corp-b`.

Typical callbacks:
- `/login/oauth2/code/corp-a`.
- `/login/oauth2/code/corp-b`.

If `tenant-a` permits only `corp-a`, enforce a **server-side allowlist** so a user choosing `tenant-a` cannot initiate `corp-b` and return to `tenant-a` unchecked.

### 8.1 Account Binding After OIDC Verification

In Spring Security Servlet, an app can customize `OidcUserService` to verify the local account after OIDC login.

~~~java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class TrustedOidcUserConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            ScopedAccountBindingService bindings) {

        var delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            String issuer = user.getIdToken()
                    .getIssuer().toString();
            String subject = user.getIdToken()
                    .getSubject();

            // Custom application service: exact verified (issuer,sub)
            // lookup, account enabled, and approved membership.
            // Must reject missing/disabled/ambiguous identity.
            bindings.requireActiveAccount(issuer, subject);

            return user;
        };
    }
}
~~~

**Limitations:** this is a **non-standalone** Spring config snippet; `ScopedAccountBindingService` is an application service you must implement, not a standard Spring API. It must return/throw appropriately for the authentication failure handler when unmapped. Requires OIDC `ClientRegistration`, trusted provider verification, `spring-security-oauth2-client`, `SecurityFilterChain`, and a database.

Wiring into login:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/health").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(oidcUserService)))
            .build();
}
~~~

**This snippet requires imports** for `HttpSecurity`, `SecurityFilterChain`, `@Bean`, and referenced types; the project must provide binding beans and account policies. It handles post-authentication account lookup and **does not** automatically enforce resource-level tenant authorization or session role revocation. With multiple login providers, verify the app checks the right `registrationId` or expected tenant context before issuing an account/session.

### 8.2 Never Create Accounts Solely by Email

Anti-pattern:

~~~java
// Never use for automatic identity linking:
String email = oidcUser.getEmail();
Account account = repository.findByEmail(email);
~~~

Risks:
- Two IdPs emit the same email;
- One issuer emits an unverified email;
- Email gets reassigned after an employee leaves;
- A user changes email or IdP tenant;
- A partner has a company-domain email without belonging to that tenant.

Use verified OIDC `iss+sub` and approved onboarding/JIT provisioning. When linking two identities to **one app account**, require verified account linking from both contexts or authoritative migration mappings, and log approval/evidence.

## 9. Multi-IdP SAML2: Registration Is Not Wildcard Trust

Spring Security creates a `RelyingPartyRegistration` per SP–IdP relationship. Each registration has:
- Distinct `registrationId`, e.g., `corp-a`, `partner-c`.
- Distinct Asserting Party `entityID`.
- Distinct trusted verification certificates.
- Matching `SingleSignOnServiceLocation`/binding.
- SP `entityId`, `AssertionConsumerServiceLocation`, and signing/decryption credentials as configured.
- A validation suite for Response/Assertion/`SubjectConfirmation`.

Typical default endpoints:
- `/saml2/authenticate/{registrationId}` to initiate SP-initiated login.
- `/login/saml2/sso/{registrationId}` (or supported callback pattern) to receive `SAMLResponse`.

Spring Security docs state `registrationId` resolves the `RelyingPartyRegistration`, while the validator checks **issuer, signature/trust, destination, audience, recipient, and conditions**. **Calling registration A's URL from the browser does not turn IdP B's XML into A's assertion.**

### 9.1 Example Configuration with Two Asserting Parties

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-a:
            assertingparty:
              entity-id: https://saml-a.example.org/metadata
              verification:
                credentials:
                  - certificate-location: classpath:saml-a-test.crt
              singlesignon:
                url: https://saml-a.example.org/sso
          partner-c:
            assertingparty:
              entity-id: https://saml-c.example.org/metadata
              verification:
                credentials:
                  - certificate-location: classpath:saml-c-test.crt
              singlesignon:
                url: https://saml-c.example.org/sso
~~~

This is a **test-oriented skeleton** needing real test registration metadata/ACS/`entityID` and certificates. The `classpath</BT> paths do not pre-exist; it will not run without those resources. Check compatible property keys, signature algorithms, request signing, and metadata trust for your exact Spring Boot/Security version. **Never copy the same verification cert across all IdPs for convenience** unless those IdPs genuinely share an approved trust model by deliberate design.

### 9.2 Cross-IdP Negative Tests with Valid Signatures

Setup:
1. IdPs A and C hold distinct keypairs; SP trusts cert A in registration A and cert C in registration C.
2. Test harness produces a signed `SAMLResponse` from C with `Issuer=C`, `NameID` `alex`.
3. POST that response to A's ACS with scenario-appropriate request state.
4. **Must be rejected**, creating no `Authentication` A or account A.
5. Even when both tenants have username `alex`, identity mappings do not collide.
6. Positive control: signed response A to ACS A with matching audience/correlation logs into account A.

Separate tests:
- `SAMLResponse` `Issuer=A` yet signed with key C (untrusted signer).
- `SAMLResponse` `Issuer=C`, key C trusted for C, yet posted to registration A.
- Signed Response A with `Audience=SP entityId of C`.
- Signed Assertion A with `Recipient`/ACS of C.
- Matching `NameID` between A and C with valid issuers—local account lookup must still separate them.

**Never edit XML after signing so that every negative case fails only signature verification.** To test audience or issuer checks, generate the fixture with the wrong field **and sign it validly with the test key**, keeping all other conditions valid.

### 9.3 IdP-Initiated vs. SP-Initiated

In SP-initiated SAML login, `AuthnRequest` and `InResponseTo` correlate the response with the prior flow. In IdP-initiated unsolicited SSO, correlation may be absent; login CSRF/account-confusion risks rise if permitted unrestricted.

QA needs:
- SP-initiated: preserve exact session/`RelayState`/Request ID.
- IdP-initiated (if supported): restrict trusted issuers, audience/recipient/time, tenant/account linking, and `RelayState` redirect policy.
- Never disable SP-initiated correlation just to test cross-IdP responses.
- Never treat an untrusted `RelayState` or `?tenant=A` query as authority to pick accounts/tenants.

## 10. SAML `NameID` Collisions and Account Linking

Example:
- IdP A issues persistent `NameID=alex` for SP A.
- IdP C issues unspecified `NameID=alex`.
- Both SAML assertions carry valid signatures under their **respective** registrations.

Right conclusion: **two distinct external subjects unless verified linking exists**.

A SAML key must reflect the federation contract:
- Protocol `SAML2`;
- Asserting Party issuer/`entityID`;
- `NameID` format;
- `NameQualifier`/`SPNameQualifier` when present;
- SP relationship/registration if pairwise name identifiers are SP-scoped;
- Subject value.

Never force a transient `NameID` into a durable account, and never treat `emailAddress`-format `NameID`s as immutable. If an IdP alters persistent `NameID`s after a migration, use a controlled migration/linking flow instead of email fallback.

### JIT Provisioning Rules

Just-in-time provisioning on first login is valid **only when tightly designed**:
1. After crypto/protocol verification, obtain the scoped identity.
2. Check the issuer/tenant allowlist.
3. Verify the user has an invite, SCIM pre-provisioning record, or onboarding-eligible policy.
4. Create a new app account with an immutable UUID; **never merge accounts by email**.
5. Insert the external identity binding atomically with uniqueness constraints.
6. Grant minimal default privileges; never auto-map `"Admins"` to global admin.
7. Log provisioning events with source IdP and tenant.
8. When two first-login requests race, handle unique constraint/concurrency safely.
9. If an account was disabled/tombstoned, never resurrect it via email reuse.
10. When multiple IdPs onboard one person, require an **explicit link flow**.

## 11. CAS, Kerberos, and Proxy-Auth Also Have Collisions

This risk is not unique to OIDC/SAML.

**CAS:**
- CAS Server emits service tickets and user identifiers per configuration.
- Two independent CAS Servers both returning `cas:user=alex` do not prove the same account.
- Validate tickets at the right CAS server/service URL and scope identities by issuer/server and stable attribute contracts.
- Never accept a service ticket from another server as a valid login.

**Kerberos/SPNEGO:**
- `alex@REALM-A` and `alex@REALM-B` are two principal namespaces.
- Never strip `@REALM` and look up only `alex`.
- AD domain migrations/UPN renames can alter principal strings; bind to stable directory objects when required.

**LDAP/Active Directory:**
- `uid`, `sAMAccountName`, `cn`, and DN can collide or change across directories/domains.
- AD `objectGUID` is directory-object scoped; scope alongside directory/domain IDs and migration policy.
- Never auto-link accounts merely because email or `userPrincipalName` matches.

**Proxy pre-authentication:**
- Header `X-Authenticated-User: alex` carries no trusted IdP/tenant provenance unless the proxy emits scoped assertions.
- Backends must trust only network/mTLS-authenticated proxies and receive canonical identities with issuer/workload provenance.
- If clients can call the backend directly with spoofed headers, that is an Authentication bypass, not merely a collision.

## 12. Tenant Permission Isolation: Roles Must Be Scoped

Wrong:

~~~java
// Wrong if ROLE_ADMIN is shared system-wide
// when per-tenant admin is required.
@PreAuthorize("hasRole('ADMIN')")
public Document getDocument(String tenant, String id) {
    return repository.findById(id).orElseThrow();
}
~~~

If the user is admin of A, checking only `ADMIN` role lets them fetch B's resources because the repository is not tenant-scoped.

Right mental model:
1. Authenticate user via issuer/subject.
2. App resolves immutable account ID.
3. User specifies target tenant in request, and server verifies **active membership**.
4. Retrieved object has matching `tenantId`.
5. Check specific grant on object/action; a tenant-local admin is not a global admin.
6. Audit tenant, account, resource, action, and decision.

**Illustrative** Spring service sample:

~~~java
package com.example.sso;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final ScopedDocumentRepository repository;
    private final TenantPermissionService permissions;

    public DocumentService(ScopedDocumentRepository repository,
                           TenantPermissionService permissions) {
        this.repository = repository;
        this.permissions = permissions;
    }

    @PreAuthorize("isAuthenticated()")
    public Document readDocument(String tenantId, String documentId) {
        String accountId = permissions.currentAccountId();
        permissions.requireActiveMembership(accountId, tenantId);
        permissions.requireGrant(accountId, tenantId, "DOCUMENT_READ");

        Document document = repository
                .findByTenantIdAndDocumentId(tenantId, documentId)
                .orElseThrow();

        permissions.requireObjectAccess(accountId, document, "READ");
        return document;
    }
}
~~~

This is **partial Spring code** without a standalone `main()`. `ScopedDocumentRepository`, `TenantPermissionService`, and `Document` must be implemented by the application. Enable `@EnableMethodSecurity`, configure proper principal mapping, and enforce transactional authorization. Map exceptions to 403/404 per policy to avoid leaking whether documents exist in other tenants.

**Key rule:** scope every query by tenant at the repository/data-access layer rather than fetching everything and filtering in the frontend. Keep tenant scoping across JPA, cached entities, native SQL, search engines, and object storage.

## 13. Tenant Headers, Hostnames, and Paths Are Untrusted Inputs

An API may receive:
- `GET /tenants/tenant-a/documents/123`;
- `X-Tenant-Id: tenant-a`;
- Subdomain `tenant-a.app.example.org`;
- GraphQL argument `organizationId=tenant-a`.

These values **carry no authority**. Users can alter them. Verify the tenant exists, active membership holds, grants exist, and the resource belongs to that tenant.

### `Host`/Forwarded Header Confusion

If a reverse proxy hosts A and B while the backend trusts browser-supplied `Host` or `X-Forwarded-Host`, requests can route to the wrong issuer/tenant. Countermeasures:
- Edge proxy strips/overwrites `Forwarded` and `X-Forwarded-Host`/`Proto`;
- Public hostname allowlist;
- `RelyingPartyRegistration`/`ClientRegistration` chosen from server-side policy/saved authorization requests;
- Exact per-tenant callback/ACS URIs, redirect URIs, and entity IDs;
- Never derive trusted issuers/JWK URLs from raw host/query values.

**Do not rely solely on a private network** if the backend permits direct access bypassing the authentication proxy.

## 14. One IdP Serving Multiple Tenants: Double Checks

Scenario:
- IdP `https://corporate-idp.example.org` serves both tenants A and B.
- User `sub=123` is a single identity at the IdP.
- User is a member of tenant A, not B.
- Token carries a valid issuer and signature.

If the server maps `issuer=corporate-idp` to “allowed into every tenant of that IdP,” cross-tenant access occurs.

Design:
- External identity mapping yields the account ID.
- Tenant membership lookup is **independent** of issuer trust.
- Roles/grants are scoped per tenant.
- A UI-selected default tenant grants **no** permission to skip checks.
- On membership revocation, bump `securityEpoch` and invalidate sessions/caches/tokens per SLA.
- Verify resource owner tenant separately in domain/repository layers.

This test is critical because **IdP trust is 100% valid**, yet data can still leak.

## 15. One Tenant Allowing Multiple IdPs: No Auto-Merging

Scenario:
- Tenant A lets employees log in via Corporate OIDC A.
- Contractors log in via Partner SAML C.
- Both users share email `alex@company.example.org`.

Right design:
- Each verified external identity keeps its own binding.
- Allowlist specifies which registrations Tenant A accepts.
- Local account linking runs via invites or identity governance when evidenced.
- One external identity cannot map to two accounts; one account with multiple bindings requires approval.
- Tenant A memberships/roles are tracked per account.
- Partner C never receives corporate privileges from email domain or username alone.

Tests:
1. OIDC A logs into employee account; positive.
2. SAML C logs into contractor account; positive.
3. C uses same email as employee; does not hijack employee account.
4. C has group `Admins` in its own directory; does not become tenant global admin.
5. Account linking succeeds only via verified proof and auditing; negative when proof is missing.
6. Revoking identity C does not accidentally revoke A unless business policy links them.

## 16. Group/Role Collisions: “Admins” Is Not Global Admin

IdPs/tenants may emit:
- `groups = ["Admins"]`.
- SAML Attribute `memberOf=Admins`.
- OIDC custom claim `roles=["Admin"]`.

If the app maps every `"Admins"` string to `ROLE_SUPER_ADMIN`, a partner IdP can unintentionally grant system-wide privileges.

Authority design:
- Verify trusted issuer + registration context.
- Scope group identifiers by issuer/directory/tenant, preferring immutable group IDs.
- Map per tenant: `(tenant-a, group-a-id) → REPORT_ADMIN_A`.
- Separate system operator roles granted independently by the app-operating organization.
- Never confuse global admin accounts with tenant-local admins.
- Never use IdP B's groups to authorize Tenant A resources without an explicit cross-tenant grant.
- Token authorities can go stale when users switch tenants; enforce live checks/revocation.

### Group Collision Tests

| User | Issuer | Group Claim | Target | Result |
| --- | --- | --- | --- | --- |
| A | IdP A | Admins | Tenant A reports | Allow if A mapping grants |
| A | IdP A | Admins | Tenant B reports | Deny |
| B | IdP B | Admins | Tenant A reports | Deny |
| B | IdP B | Admins | Tenant B reports | Allow if B mapping grants |
| C | Partner C | Admins | System admin API | **Deny** unless system grant exists |
| A | IdP A | Viewers | Tenant A admin API | Deny |

## 17. JIT Provisioning, Invitations, and SCIM

JIT provisioning on first SSO login typically requires:
1. Verified protocol identity.
2. Tenant–IdP association allowlist.
3. Invite/SCIM pre-provisioning or onboarding-eligible policy.
4. Atomic creation of app account and external binding.
5. Default least-privilege membership.
6. Audit of issuer, stable subject, tenant, and source.
7. No auto-linking by email.
8. No resurrection of deleted accounts solely via email reuse.
9. DB-level collision checks.
10. Clear failure mode when the same external subject has conflicting bindings.

SCIM fields:
- `id` is service-provider-issued within the provider scope.
- `externalId` is assigned by the provisioning client, scoped to the provisioning domain.
- `userName`/`email` can change.
- SCIM `active=false` does not automatically revoke all active sessions/tokens.
- Group memberships can sync via SCIM `Group` resources; never treat `department` as authorization proof.

### Email Invite Collisions

Example:
- Tenant A invites `alex@example.org`.
- Person B from IdP B logs in with that exact email.
- The invite was created for a specific corporate identity.

**Never auto-claim an invite solely by matching email.** Verify:
- The invite binds to an issuer/directory, or follows an appropriate verified email/proof workflow.
- Invite tokens are short-lived, single-use, and bound to tenant and target identity where applicable.
- Prevent someone reusing A's old email from claiming historical data.
- If self-service uses email proof, evaluate account-takeover/migration risks first.

### Concurrency

Two concurrent JIT login attempts can both see “no account yet.” Enforce unique identity constraints + safe transactions/retries instead of creating two accounts and merging by email later.

## 18. Browser Sessions and Account Switching

Multi-IdP logins often share **the same browser**:
- Tab 1 logs into IdP A.
- Tab 2 logs into IdP B.
- Browser holds the Spring session cookie.
- A request in Tab 1 calls Tenant A resources after Tab 2 finishes logging in.

If the app keeps **one `HttpSession` authentication** on that cookie, login B overwrites the active principal. Even if Tab A's UI still shows old data, subsequent requests must be evaluated under the **current identity**, never assuming Tab A is still user A.

Test cases:
1. Log into A then B in the same browser; verify session current identity per design.
2. Tab A sends request after B logs in; never uses stale A privileges.
3. Log out A—does B's session stay alive? Follow SSO/local-session policy without accidental mixing.
4. IdP B callback arrives while A's state is pending; never cross-bind.
5. Saved requests/`RelayState` across two login flows never mix.
6. Session fixation: post-auth session ID behavior matches policy.
7. Users A/B share local email/`sub`; never reuse accounts.
8. Account switching clears/rotates security context and tenant-specific caches.
9. “Remember me” / authorized client records stay scoped to account/client/issuer.
10. Separate browser profiles never mix tenant data.

**Never trust a client-set `HttpSession` attribute `currentTenant`** as authorization. Every resource call still verifies account, selected tenant, active membership, and ACLs.

## 19. Token Exchange and Callback Mix-Up

For multi-provider OIDC Authorization Code Flow:
- `state` binds to the saved authorization request and expected client registration.
- Redirect URI must match the client/authorization server registration.
- Token exchange goes to the matching token endpoint with matching client credentials.
- ID Token issuer/audience/nonce are verified per profile.
- When the authorization response includes `iss` per RFC 9207, compare it against the expected issuer.
- PKCE protects the code flow per client requirements but **does not replace issuer/client matching**.
- Never construct token endpoint URLs from unsanitized `Host` or query parameters.
- Changing `registrationId` in the callback must never send A's code to B.
- Failure paths never leak authorization codes or tokens in logs or error redirects.

### Protocol-Level Test Template

~~~text
Given:
  Authorization request initiated for corp-a
  Expected issuer = https://idp-a.example.org
  Saved state = state-A, nonce-A, client-a

When:
  Browser callback carries response from corp-b
  or wrong issuer response param, or state-B

Then:
  Reject
  No account A/B session created from wrong response
  No authorization code sent to wrong token endpoint
  Correlation/log records incident code without leaking code/token
~~~

This is a **test design**; executing it requires test IdPs/authorization servers and an HTTP/browser harness rather than hand-written JWT bodies as success tokens.

## 20. Multi-Issuer JWT Resource Server: Distinct from OAuth2 Login

A backend API may accept **Bearer JWT access tokens** from two authorization servers. Spring Security supports selecting validators per issuer via `AuthenticationManagerResolver`, such as `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` in releases providing it.

~~~java
// Spring Security Resource Server config fragment,
// not OIDC browser login or a standalone program.
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.org",
                "https://idp-b.example.org");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

**Prerequisites:** Resource Server + JOSE dependencies, trusted issuer config, `SecurityFilterChain`, and proper audience/token-type validation. This issuer list must be **fixed/governed**; never instantiate decoders from attacker-supplied issuer URLs.

### Why Trusted Issuers Alone Are Insufficient

A token can:
- Carry valid issuer A yet `aud` intended for API X rather than Y.
- Carry scope `reports.read` while the user lacks Tenant B membership.
- Belong to a different resource owner—matching token user alone is insufficient.
- Carry a Tenant A claim after the user was revoked from A.
- Carry group `Admins` meaningful only locally in IdP A.

Resource servers must:
1. Verify JWT signature against trusted issuer keys.
2. Verify `iss`, `exp`/`nbf` per profile, and exact API `aud`.
3. Validate trusted scopes/custom claims.
4. Resolve `issuer+subject` and verify active account.
5. Enforce membership/ACLs at the resource boundary.
6. Never let request `tenant` override verified entitlements.

**Never use a browser ID Token as a bearer API access token.** An ID Token's audience is typically the OIDC client; API access tokens require their own contract.

## 21. Checking Caches and Data Queries

An app can enforce permissions properly at the controller yet leak data through unscoped cache keys.

Wrong:

~~~java
@Cacheable("documents")
public Document find(String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

If `documentId` is unique only per tenant or the method runs across tenants, the cache can serve another tenant's data. Fix:
- Include `tenantId</BT> and resource ID in keys, plus access-scope/user version if responses vary by user.
- Still enforce authorization before returning cached objects; a cache hit never bypasses ACLs.
- Never place user-specific responses into a shared global cache.
- Scope database queries by tenant and ACL.
- Search indexes, object storage, and CDN caches also need namespaces and access checks.
- Asynchronous jobs must receive explicit trusted tenant context and verify service permissions.
- Never trust leftover `ThreadLocal` tenant values across pooled threads.

### Data Layers to Test

| Layer | Cross-Tenant Test |
| --- | --- |
| Controller/REST | Swap tenant path/header and request another tenant's document |
| GraphQL | Node ID from another tenant; nested resolvers never leak |
| Repository | Missing tenant filter caught by unit/integration tests |
| Caching | A warms cache, then B with same resource ID never receives A's data |
| Export/report | Async export from Tenant A cannot be downloaded by Tenant B |
| File/object storage | Signed URLs and object keys scoped by tenant and TTL |
| Event/queue | Consumers apply exact tenant context without stale `ThreadLocal` |
| Search index | Tenant B search never returns Tenant A snippets |
| Admin APIs | Tenant admin cannot act as global/system admin |
| Background jobs | Service identity holds only delegated permissions |

## 22. Standalone Java 17: Demonstrating Identity-Scoped and Tenant-Scoped Authorization

This program uses **only the Java Standard Library**, needing no Spring/IdP/DB. It models:
- `(issuer,subject)` sharing `sub` without colliding accounts.
- Matching emails without auto-linking.
- Accounts A/B viewing only their respective tenants.
- Unknown IdP or new subject with matching email rejected.
- Stale session version blocked after user moves tenants.
- Disabling an account blocks all access.

**Important boundary:** `VerifiedIdentity` in this demo simulates an **already-verified result**. Production must obtain the equivalent object from a real OIDC/SAML provider, never from client-supplied JSON, query params, or headers.

File `CrossTenantIdentityDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class CrossTenantIdentityDemo {

    record VerifiedIdentity(String issuer, String subject) {}

    record Session(String accountId, long securityEpoch) {}

    static final class Account {
        final String id;
        final String email;
        boolean enabled = true;
        long securityEpoch = 1;
        final Map<String, Set<String>> tenantRoles = new HashMap<>();

        Account(String id, String email, String tenant, Set<String> roles) {
            this.id = id;
            this.email = email;
            this.tenantRoles.put(tenant, Set.copyOf(roles));
        }
    }

    static final class Directory {
        private final Map<VerifiedIdentity, String> bindings =
                new HashMap<>();
        private final Map<String, Account> accounts = new HashMap<>();

        synchronized void register(
                VerifiedIdentity verified,
                Account account) {
            if (bindings.containsKey(verified)
                    || accounts.containsKey(account.id)) {
                throw new IllegalArgumentException("duplicate binding");
            }
            bindings.put(verified, account.id);
            accounts.put(account.id, account);
        }

        synchronized String resolve(VerifiedIdentity verified) {
            return bindings.getOrDefault(verified, "NO_MATCH");
        }

        synchronized Session sessionFor(VerifiedIdentity verified) {
            String id = bindings.get(verified);
            if (id == null || !accounts.get(id).enabled) {
                return null;
            }
            Account account = accounts.get(id);
            return new Session(id, account.securityEpoch);
        }

        synchronized String authorize(
                Session session, String tenant, String role) {
            if (session == null) {
                return "DENY_UNMAPPED";
            }
            Account account = accounts.get(session.accountId());
            if (account == null) {
                return "DENY_UNMAPPED";
            }
            if (!account.enabled) {
                return "DENY_DISABLED";
            }
            if (account.securityEpoch != session.securityEpoch()) {
                return "REAUTH_REQUIRED";
            }
            Set<String> roles = account.tenantRoles.get(tenant);
            if (roles == null) {
                return "DENY_TENANT";
            }
            if (!roles.contains(role)) {
                return "DENY_ROLE";
            }
            return "ALLOW";
        }

        synchronized void move(
                String accountId, String tenant, Set<String> roles) {
            Account account = accounts.get(accountId);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            account.tenantRoles.clear();
            account.tenantRoles.put(tenant, Set.copyOf(roles));
            account.securityEpoch++;
        }

        synchronized void disable(String accountId) {
            Account account = accounts.get(accountId);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            account.enabled = false;
            account.securityEpoch++;
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();
        VerifiedIdentity userA = new VerifiedIdentity(
                "https://idp-a.example.org", "123");
        VerifiedIdentity userB = new VerifiedIdentity(
                "https://idp-b.example.org", "123");

        directory.register(userA, new Account(
                "acct-A", "same@example.org",
                "tenant-a", Set.of("REPORT_READ")));
        directory.register(userB, new Account(
                "acct-B", "same@example.org",
                "tenant-b", Set.of("REPORT_READ")));

        Session sessionA = directory.sessionFor(userA);
        Session sessionB = directory.sessionFor(userB);

        System.out.println("A identity: " + directory.resolve(userA));
        System.out.println("B identity: " + directory.resolve(userB));
        System.out.println("A own: " + directory.authorize(
                sessionA, "tenant-a", "REPORT_READ"));
        System.out.println("B own: " + directory.authorize(
                sessionB, "tenant-b", "REPORT_READ"));
        System.out.println("A into B: " + directory.authorize(
                sessionA, "tenant-b", "REPORT_READ"));
        System.out.println("B into A: " + directory.authorize(
                sessionB, "tenant-a", "REPORT_READ"));

        VerifiedIdentity unknownIssuer = new VerifiedIdentity(
                "https://idp-rogue.example.org", "123");
        VerifiedIdentity reusedEmailOwner = new VerifiedIdentity(
                "https://idp-a.example.org", "999");

        System.out.println("Rogue issuer: " + directory.authorize(
                directory.sessionFor(unknownIssuer),
                "tenant-a", "REPORT_READ"));
        System.out.println("Reused email: " + directory.authorize(
                directory.sessionFor(reusedEmailOwner),
                "tenant-a", "REPORT_READ"));

        directory.move("acct-A", "tenant-c",
                Set.of("REPORT_READ"));
        System.out.println("A old session after move: "
                + directory.authorize(
                        sessionA, "tenant-a", "REPORT_READ"));

        Session newSessionA = directory.sessionFor(userA);
        System.out.println("A old tenant after move: "
                + directory.authorize(
                        newSessionA, "tenant-a", "REPORT_READ"));
        System.out.println("A new tenant: "
                + directory.authorize(
                        newSessionA, "tenant-c", "REPORT_READ"));

        directory.disable("acct-B");
        System.out.println("B after disabled: "
                + directory.authorize(
                        sessionB, "tenant-b", "REPORT_READ"));
    }
}
~~~

Compile/run:

~~~bash
javac CrossTenantIdentityDemo.java
java CrossTenantIdentityDemo
~~~

**Exact** stdout:

~~~text
A identity: acct-A
B identity: acct-B
A own: ALLOW
B own: ALLOW
A into B: DENY_TENANT
B into A: DENY_TENANT
Rogue issuer: DENY_UNMAPPED
Reused email: DENY_UNMAPPED
A old session after move: REAUTH_REQUIRED
A old tenant after move: DENY_TENANT
A new tenant: ALLOW
B after disabled: DENY_DISABLED
~~~

### Explanation

1. A and B share subject text `123` and email, yet differing issuers yield distinct app accounts.
2. Users A/B can view only resources in tenants where they hold roles.
3. Unknown issuers or new subjects cannot claim account A via email.
4. Moving A to tenant C increments `securityEpoch`; the old session is blocked.
5. After re-login, Tenant A membership is gone while Tenant C is permitted.
6. Disabling B blocks session B even before expiration.

### Strict Limitations

- No cryptographic verification, OAuth2/OIDC/SAML/LDAP, or HTTP.
- `VerifiedIdentity` is constructed manually in the demo; production accepts it **solely** from verified protocol validation.
- All state resides in `HashMap`s with no DB, distributed sessions, multi-node concurrency, or audits.
- No resource ACLs or URL IDOR checks: the example models tenant-role policy only.
- Performs no account linking or SCIM migration.
- Not a production security mechanism; it is an illustrative model for writing unit tests.

## 23. Writing Unit Tests for Identity Binding Without Faking SSO Verifiers

Use structured test fixtures:

~~~text
OIDC:
  A = (issuerA, sub=shared-123), email=shared@example.org
  B = (issuerB, sub=shared-123), email=shared@example.org
  C = (issuerA, sub=other-999), email=shared@example.org

Expected:
  resolve(A) == acct-A
  resolve(B) == acct-B
  resolve(C) == NO_MATCH
~~~

These assertions test **binding logic**, not whether ID Tokens were validly signed. They suit fast unit tests in Java/JUnit.

Similarly for SAML:

~~~text
SAML IdP A: issuer=entityA, NameID=alex, format=persistent
SAML IdP C: issuer=entityC, NameID=alex, format=persistent
Expected: two scoped identity records, no implicit link
~~~

Follow up with **integration tests** using real signed SAML fixtures or test OIDC servers to confirm the app builds bindings solely from **verified claims**, never self-asserted inputs.

## 24. Testing Tenant Authorization with MockMvc

The test below illustrates checking business endpoints **after an `Authentication` exists**:

~~~java
package com.example.sso;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CrossTenantAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "acct-A", roles = "TENANT_A_VIEWER")
    void userMustNotReadTenantB() throws Exception {
        mvc.perform(get("/tenants/tenant-b/documents/doc-42"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Limitations:** this is a test inside a Spring project, lacking `main` and depending on controllers, local authority naming, tenant/data fixtures, and exception contracts. The `/tenants/...` path is illustrative. It can prove route/ACL checks block Tenant B if app logic works, **not OIDC signature/SAML verifier behavior**.

To test real SSO:
- Use test OIDC IdPs issuing signed ID Tokens for A/B.
- Use test SAML IdPs signing responses with A/C certificates.
- Traverse the real login filter and provider.
- Assert exact external identity account mapping.
- Post-login, call cross-tenant resources and assert 403/404 per policy.

**A single test cannot cover both AuthN and AuthZ if it only injects a mock `Authentication`.**

## 25. OIDC Integration Testing: Independent Issuer and Audience Pairs

Use two test OpenID Providers with distinct keypairs:
1. A mints valid token `iss=A, sub=123, aud=client-a`.
2. B mints valid token `iss=B, sub=123, aud=client-b`.
3. Log in A → account A, tenant A.
4. Log in B → account B, tenant B.
5. Feed B's token into client A's flow → reject.
6. Token from A with `aud=another-client` and valid signature → reject.
7. Unknown issuer/unknown JWKS despite matching `sub`/email → reject.
8. Token with claims altered post-signing → reject signature.
9. Valid token while app account is disabled → login/action denied.
10. Test `state`/`nonce`/authorization response issuer mix-ups on callbacks.

**Do not just edit strings in an already-signed JWT to test wrong issuer/audience**: that breaks the signature. To test the validator itself, re-mint a JWT with wrong fields yet a valid signature under the test issuer setup.

For resource server JWTs:
- Test audiences intended for other APIs;
- Test ID Token vs. access token;
- Test issuer allowlists;
- Test tenant membership/permissions even for valid tokens;
- Test cache/revocation per SLA.

## 26. SAML Integration Testing: Signer, Issuer, Registration, Audience

Use two test IdPs, separate signing certs, and the real OpenSAML provider:
- Signed response A to registration A with valid audience/recipient/conditions → succeeds.
- Signed response C to registration C matching profile → succeeds.
- Signed response C to registration A → rejects.
- Signed response `Issuer=A` signed with key C → rejects signer/trust.
- Signed response A with `Audience=SP C` → rejects semantic validation.
- Signed response A with `Recipient=ACS C` → rejects.
- Signed response A with `NameID` matching C → **not the same account**.
- Signed response missing or mismatching `InResponseTo` in SP-initiated flow → rejects per policy.
- Replayed signed response → rejects per real correlation/replay policy.
- IdP-initiated unsolicited responses if supported: verify allowlist/trust/tenant mapping and `RelayState`.

**Ensure negative semantic fixtures keep valid signatures**, otherwise tests catch only signature tampering.

## 27. Multi-Layer Cross-Tenant Test Matrix

| ID | Scenario | Layer | Expected |
| --- | --- | --- | --- |
| T01 | OIDC A `sub=123` into account A | Real OIDC login | ALLOW A |
| T02 | OIDC B `sub=123` into account B | Real OIDC login | ALLOW B |
| T03 | OIDC A/B share email | Identity mapping | No merge |
| T04 | OIDC A token into client B | OIDC validator | DENY |
| T05 | OIDC B token validly signed yet wrong audience A | OIDC validator | DENY |
| T06 | Unknown issuer creates matching `sub`/email | AuthN trust | DENY |
| T07 | OAuth code/callback IdP mix-up | OAuth login flow | DENY; code not sent to wrong endpoint |
| T08 | Bad or stale callback `state` | OAuth login flow | DENY |
| T09 | Nonce mismatch | OIDC validation | DENY |
| T10 | IdP A unknown signer key yet matching claims | OIDC signature | DENY |
| T11 | SAML C signed response to ACS A | SAML provider/ACS | DENY |
| T12 | SAML A signed response `Issuer C` | SAML provider/issuer | DENY |
| T13 | SAML A wrong `Audience`, validly signed | SAML semantic validator | DENY |
| T14 | SAML A wrong `Recipient`, validly signed | SAML semantic validator | DENY |
| T15 | SAML A wrong `InResponseTo` | SAML correlation | DENY per flow |
| T16 | SAML A/C share `NameID` | Identity mapping | No merge |
| T17 | SAML transient `NameID` reuse | Account linking | No persistent collision |
| T18 | CAS servers share `cas:user` | CAS identity scope | No merge |
| T19 | Kerberos `user@REALM-A/B` | Realm scope | No merge |
| T20 | A requests B's document | App/resource ACL | DENY |
| T21 | Admin A calls B's admin API | Tenant-scoped role | DENY |
| T22 | B changes `X-Tenant-Id</BT> to A | API/authorization | DENY |
| T23 | One issuer serves two tenants, user only in A | Membership | DENY B |
| T24 | One tenant allows two IdPs, users share email | Provisioning/account binding | No auto-link |
| T25 | Recycled email post-offboarding | Rehire/account linking | No inherited data |
| T26 | SCIM `externalId` collides across two sources | Provisioning | Scoped; no merge |
| T27 | Cache A warmed, then B requests same ID | Cache/data access | No A leak |
| T28 | GraphQL node ID in tenant A requested by B | Object-level ACL | DENY |
| T29 | A's async export downloaded with B's token | Download authorization | DENY |
| T30 | Login A then B in same browser | Session isolation | No reused A privileges |
| T31 | A's membership revoked while logged in | Live AuthZ/epoch | DENY A resource |
| T32 | User holds valid memberships in both A and B | Membership switching | ALLOW scoped resources |
| T33 | B has group `Admins` like A | Role mapping | No global admin |
| T34 | Unknown `registrationId` in SAML/OIDC | Routing/trust | DENY |
| T35 | IdP cert rotation on different tenant | Configuration | Rejects foreign signers |
| T36 | Spoofed `Host`/Forwarded headers | Proxy/trust boundary | Does not pick wrong issuer/tenant |

This is a **reference catalog**; not every app must run all 36 cases if a protocol/architecture does not apply. Pick applicable cases **without dropping minimum negative AuthN+AuthZ coverage**.

## 28. Conditions for Tests to Reflect the True Root Cause

A test asserting “B cannot access A” can pass because:
- B's ID Token had an invalid signature;
- App lacked account B;
- Resource A did not exist;
- Test database was empty;
- No session was created;
- Authorization genuinely rejected Tenant B.

Only the final case (with B validly authenticated and resource A existing) provides strong proof of **cross-tenant authorization**.

**For meaningful tests:**
1. Include a positive control where B logs in via a real provider.
2. Resource A exists in the fixture DB and User A can access it.
3. User B has an account and B membership, not A.
4. User B requests A's resource using **B's valid session/token**.
5. Assert 403/404 per policy with **no data/existence leaks**.
6. Inspect query logs/audits for the decision rather than concluding from a missing-row 404.
7. Test B-admin roles, group collisions, email collisions, and IdP collisions.
8. Test caches pre-warmed with A's data.
9. When proving DB-level isolation, exercise repository queries with tenant predicates.
10. Never mock a permission service to return `false` when the goal is testing the real permission service.

### For Protocol Negative Tests

To test `aud`, a signed wrong-audience fixture must keep **valid signature, issuer, and timestamps**. To test signed SAML trust, IdP B's fixture must be validly signed with B's test key yet fail on registration A. Never build a completely broken XML/JWT and claim every validator was tested.

## 29. Security Boundaries for Account Linking

A product may need to link employee OIDC A and contractor SAML C onto **the same app account** representing one real person. That linking can be valid yet carries high risk.

A strict flow:
1. User reauthenticates current identity A.
2. Start the linking flow from app account A with CSRF/anti-session-fixation protection.
3. Redirect to IdP C under a trusted registration; verify SAML Response/OIDC ID Token.
4. Verify identity C is not already mapped to someone else's app account.
5. Require step-up/approval if the account holds sensitive or cross-tenant roles.
6. Link identity C to account A inside a transaction with uniqueness constraints.
7. Log actor, verification method, source IdP, timestamp, tenant scope, and evidence reference.
8. Never **auto-union roles** from A and C; manage memberships/roles separately.
9. Enforce controlled unlink/revocation flows leaving no orphan privileged bindings.
10. Test concurrency and rollbacks on persistence failures.

### Cases That Must Be Rejected

- Browser merely asserts two matching emails.
- IdP C emits an unverified email matching A.
- User fails to prove control over identity A while trying to link C into A.
- Identity C is already linked to another account.
- Link created via a callback lacking `state`.
- Issuer auto-discovered from a caller-supplied URL.
- Linking inadvertently grants Tenant A admin rights to principal C because of C's `Admins` group.

## 30. Distinguishing Authentication Errors from Authorization Denials

Systems need a clear error taxonomy:

| Layer | Example | Expected Handling |
| --- | --- | --- |
| OAuth/OIDC protocol | State/nonce mismatch, invalid signature, issuer/client mismatch | Auth fails, no session |
| SAML protocol | Untrusted signer, wrong Issuer/Audience/Recipient | Auth fails, no session |
| Identity binding | Valid IdP subject not yet onboarded | Login/onboarding denied or approved invitation flow |
| Account state | Account `DISABLED` | Deny despite valid IdP token |
| Tenant membership | Active account lacking target tenant membership | 403/404 per policy |
| Resource ACL | Tenant member lacking object permission | 403/404 per policy |
| Cache/serialization | Response A appears in session B | Security defect/incident |
| Logout/session | Session A keeps roles after switch/revocation | Revoke/reauth; security event |

Never use “401 everywhere” to hide that the backend actually built Authentication A from B's response. **Tests must inspect `SecurityContext`/account bindings**, not HTTP statuses alone.

### Do Not Leak Data Through Errors

A user outside Tenant A need not learn whether `doc-42` exists. Returning 404 instead of 403 per policy curbs enumeration, provided the backend **genuinely denies access**. Never put private tenant names, account emails, group memberships, SAML assertions, or raw ID tokens in error responses.

## 31. Multi-Node / Cache / Session and Race Conditions

A multi-pod SSO system can encounter:
- Node 1 processes IdP A's callback.
- Node 2 handles Tenant B's request.
- Distributed `HttpSession` holds an older principal/tenant context.
- Permission cache keyed by username instead of immutable account ID + tenant.
- Provisioning event revokes membership while cache remains stale.
- Two concurrent browser auth callbacks yield a nondeterministic final state.

### Mitigations

1. Key session security state by immutable app account ID and verified external issuer binding.
2. Revalidate tenant selection against current membership rather than trusting stale session claims.
3. Permission cache keys: account ID, tenant ID, policy/security epoch, and action where appropriate.
4. Apply session rotation/principal-change policies when logging in as another user.
5. Never store raw tokens/SAML assertions in shared caches unnecessarily.
6. Event-driven invalidation and TTLs aligned with revocation SLAs.
7. Async jobs carry trusted tenant context and service identity, never trusting mutable `ThreadLocal`s.
8. For SCIM/HR events, handle duplicates/out-of-order delivery without reopening revoked grants.
9. Test concurrency: two simultaneous login callbacks, account linking, tenant switching, and membership revocation.
10. Audit active sessions after IdP/tenant changes.

**Never assume IdP logout instantly destroys every local `HttpSession`/JWT/API key**, even when the IdP executes SLO/Logout. Immediate access cutoff requires an app-local account gate and revocation strategy.

## 32. Inspecting Logs and Monitoring Without Leaking Tokens

Minimal sample event:

~~~json
{
  "event": "cross_tenant_access_denied",
  "traceId": "opaque-trace-01",
  "authenticatedIssuerAlias": "corp-b",
  "accountRef": "acct-B",
  "requestedTenant": "tenant-a",
  "decision": "DENY_MEMBERSHIP",
  "resourceType": "document"
}
~~~

Never log raw JWTs, authorization codes, `SAMLResponse`, SAML Assertion XML, CAS service tickets, GSS tokens, session IDs, or unnecessary emails/PII.

Metrics:
- `federation_unknown_issuer_total`.
- `federation_wrong_registration_total`.
- `identity_collision_detected_total`.
- `cross_tenant_denied_total`.
- `account_linking_rejected_total`.
- `invalid_oidc_state_total`.
- `saml_untrusted_signer_total`.
- `tenant_membership_revocation_latency_seconds`.
- `unexpected_resource_tenant_access_total` if instrumented.
- `cache_tenant_scope_violation_total` if measurable.

Alert when:
1. Logins from unapproved issuers spike.
2. One verified identity attempts linking to multiple app accounts.
3. Same-email collisions trigger auto-link attempts.
4. Cross-tenant denials spike abnormally.
5. An external ID from Tenant A is used in B post-migration.
6. A disabled account still gets authorized.
7. Cached responses return another tenant's resources.
8. A new IdP certificate/metadata becomes trusted without approval.

Never use user emails, `sub`, or raw assertion IDs as high-cardinality metric labels. Restrict dashboard access and protect PII.

## 33. Bottom-Up QA Workflow

### A. Unit Tests for Keys and Local ACLs

- Create colliding subjects with distinct issuers.
- Create identical emails/usernames.
- Verify binding maps keep both accounts separate.
- Verify A's `Admins` role does not apply to B.
- Verify tenant membership and resource ACLs.
- Verify cache key / SCIM `externalId` namespacing.

### B. OIDC/SAML Provider Tests

- Real test OIDC JWTs with valid/wrong issuer, audience, signer, and `exp`.
- Real signed SAML fixtures A/C with distinct keys and registrations.
- Wrong SAML audience/recipient keeping valid signatures.
- Login callbacks with wrong `state`/`nonce`/`InResponseTo` rejected.
- Never mock the verification provider when concluding AuthN trust.

### C. Spring Boot HTTP Integration

- `@SpringBootTest` + MockMvc/`WebTestClient` per stack.
- Test filters, callback URLs, security context, and saved requests.
- Log in validly as A, request B's resources, and verify denial.
- Log in validly as B sharing email/`sub` text.
- Account switching, logout, and session revocation cases.
- Data access/GraphQL/cache integration with real fixtures.

### D. Staging E2E

- Two test IdPs with independent metadata/certificates.
- Real browser HTTPS, redirect URIs/ACS, cookies, and proxies.
- IdP A/B logins across same browser and separate browser profiles.
- Cross-tenant API calls via UI and network.
- Concurrent auth flows / multi-node.
- Certificate rotation, disabled users, and group changes.
- Downloads, exports, and async callbacks.
- Zero production keys or real PII.

**Layers complement rather than replace one another.** A unit test `with(user("A"))` does not prove JWKS/signature verification; a signed Response rejected on signature does not prove tenant data isolation.

## 34. Common Issues and Diagnosis

| Symptom | Possible Cause | How to Diagnose |
| --- | --- | --- |
| User B logs in as A | Lookup used only email/username/`sub` | Audit external binding key with issuer |
| B denied login when email matches A | Overly strict unique-email/JIT policy | Separate contact uniqueness from identity binding |
| Two IdPs log in with identical authorities | Group mapper not scoped by issuer/tenant | Check group identity mappings |
| Admin A sees B's documents | Global `ROLE_ADMIN` or repo query missing tenant | Check ACLs and query predicates |
| OIDC callback A receives B's code | `state`/registration mix-up | Inspect saved auth requests, issuers, token endpoints |
| JWT for API X accepted at API Y | Missing audience validator | Check `aud` and resource server config |
| SAML B accepted at ACS A | Wrong `RelyingPartyRegistration`/trust resolver | Check issuer/cert/audience/destination |
| Same `NameID` from two IdPs creates one account | Unscoped SAML subject | Add issuer/qualifiers/format |
| Partner gets global Admin via `Admins` group | Auto-role mapping by group name | Grant roles per tenant/directory group ID |
| Tenant A session reused after login B | Broken `SecurityContext`/session isolation | Test tab switching/rotation |
| Logout fails to revoke tokens | IdP logout ≠ app revocation | Current account gate / token invalidation |
| Cache A leaks to B | Key lacks tenant/account scope | Warm-cache cross-tenant test |
| GraphQL node ID permits cross-tenant read | Nested resolver skips authorization | Object-level ACLs in every resolver |
| Spoofed `Host` header swaps issuer | Dynamic resolver trusts client headers | Trusted proxy `Host`/`Forwarded` sanitization |
| JIT creates 2 accounts for one subject | Race without unique constraint | Transaction + unique identity binding |
| Recycled email revives old account | Auto-link by email | Disable fallback; use authoritative migration |
| Account moved tenants keeps old rights | Stale memberships/session roles | `securityEpoch` and live checks |
| SAML wrong-audience negative case fails only signature | Fixture edited after signing | Build wrong-audience fixture then re-sign |
| Unknown issuer auto-fetches JWKS | Dynamic issuer lacks allowlist | Trusted issuer registry |
| SAML/OIDC validation passes yet user gets 403 | App account/tenant/resource denied | Distinguish AuthN vs. AuthZ |

## 35. Self-Check Exercises with Answers

**Q1.** Two OIDC issuers share `sub=007`. Should they map to one account?

**Answer:** No. OIDC identity keys are `(iss,sub)`, never bare `sub`.

**Q2.** Users A and B share a verified email across two IdPs. Should they auto-merge?

**Answer:** No. Emails are mutable/reusable; a verified email does not prove the same historical subject.

**Q3.** User B is validly authenticated by IdP B yet requests Tenant A's resource—is this an AuthN or AuthZ failure?

**Answer:** AuthZ/membership/resource ACL must deny; it is not B's signature failing.

**Q4.** Should a signed `SAMLResponse` from IdP B sent to registration A be accepted if `NameID` matches?

**Answer:** No. Registration, issuer, signing cert trust, audience, and recipient must match.

**Q5.** If a SAML wrong-`Audience` test fails with an invalid signature, does it prove `AudienceRestrictionValidator` works?

**Answer:** Not reliably. You need a validly signed fixture with the wrong audience to isolate that rule.

**Q6.** One IdP serves two tenants. Is a valid issuer enough to unlock every tenant?

**Answer:** No. Membership/ACLs must be checked independently.

**Q7.** Tenant A allows login via IdPs A and C. Does someone from C sharing A's email become employee A automatically?

**Answer:** No; external identity bindings stay separate, using approved linking if needed.

**Q8.** IdP B has group `Admins`. Is granting system-wide `ROLE_SUPER_ADMIN` reasonable?

**Answer:** Not by default. Groups must be scoped by issuer/tenant, with global admin governed separately.

**Q9.** In multi-client OAuth2, does browser-supplied callback `registrationId` suffice to confirm the token issuer?

**Answer:** No. Correlate with the saved authorization request and validate state/nonce/issuer/audience and exact provider endpoints.

**Q10.** What does RFC 9207 defend against?

**Answer:** Authorization Server mix-up via the `iss` parameter in authorization responses, checked by clients against expected issuers where applicable.

**Q11.** A JWT from valid issuer A targets another API's audience. May the current API accept it?

**Answer:** No. Validate audience, scope, token type, and resource server trust.

**Q12.** Can a user-supplied tenant header grant access by itself?

**Answer:** No. It is merely target context; the server must check membership/grants and resource tenant.

**Q13.** User A legitimately belongs to both tenants A and B. May they access B?

**Answer:** Yes, provided membership and resource-specific permissions in B hold; not every cross-tenant switch is forbidden.

**Q14.** Why is caching solely by `documentId` risky?

**Answer:** Tenant A's data can be served to B without account/tenant scoping and authorization checks on cache hits.

**Q15.** If email changes while `issuer+subject` stays identical, should a new account be created?

**Answer:** No, update the profile; the stable binding still points to the same account.

**Q16.** Does IdP-initiated SAML SSO include `InResponseTo`?

**Answer:** It may omit it because it is unsolicited. If enabled, enforce dedicated trust/tenant/`RelayState` policies without dropping correlation for SP-initiated flows.

**Q17.** Should a transient SAML `NameID` be stored as a long-term account key?

**Answer:** No, because of its ephemeral/unstable nature.

**Q18.** Browser logs into A then B; should Tab A keep using A's old permissions?

**Answer:** Not automatically; the server must handle principal switches and revalidate context/tenant per request.

**Q19.** Why doesn't testing a bad-signature token prove cross-tenant ACLs?

**Answer:** The request stops at AuthN before business authorization executes. Log in validly as B and request an existing resource in A.

**Q20.** User C gets A's old email after account deletion. Should A's permissions auto-restore?

**Answer:** No. Rehires/migrations require verified account linking and approval, never email fallback.

**Q21.** Can different CAS servers return the same username?

**Answer:** Yes; scope CAS server/directory namespaces and validate the exact ticket service.

**Q22.** Can Kerberos users `alex@A.REALM` and `alex@B.REALM` merge because both say `alex`?

**Answer:** No. The realm is part of the principal namespace.

**Q23.** Do Tenant A admin and system admin hold identical privileges?

**Answer:** No. A tenant-local admin does not automatically control the system or other tenants.

**Q24.** If a user is legitimately a member of both A and B, should switching to B always be blocked as “cross-tenant”?

**Answer:** No. Allow per active membership and per-resource ACLs rather than hardcoding denials on all tenant switches.

**Q25.** Once frontend verification confirms Tenant B is hidden from User A, is the backend safe?

**Answer:** No. APIs, repositories, and data access must enforce authorization rather than relying on the UI.

## 36. Pre-Release Checklist

- [ ] Trust registry lists approved **IdPs/issuers/`entityID`s**.
- [ ] Every OIDC `ClientRegistration` has trusted issuer, `clientId`, redirect URI, and JWKS/discovery sources.
- [ ] OIDC ID Token checks signature, issuer, audience, nonce/state, and applicable constraints.
- [ ] OIDC account lookup uses **`iss+sub`**, never email, username, or bare `sub`.
- [ ] Authorization response issuer mix-up checked per RFC 9207 or supported profile countermeasures.
- [ ] ID Tokens are never used as API access tokens; Resource Server checks API-specific `aud`.
- [ ] SAML registrations keep independent trusted verification credentials.
- [ ] Signed `SAMLResponse`s from another IdP are never accepted cross-registration.
- [ ] SAML issuer/audience/destination/recipient/time/`InResponseTo` are tested.
- [ ] SAML `NameID` scoped by issuer/format/qualifiers; transient never used as stable ID.
- [ ] CAS/Kerberos/LDAP identity namespaces stay isolated without stripping realms/domains.
- [ ] Local app accounts use immutable IDs; external identities have uniqueness constraints.
- [ ] No auto-merging by email/username; linking requires verified proof and audit.
- [ ] Tenant membership is independent of issuer login trust.
- [ ] Permissions scoped by tenant/resource with no implicit global `ADMIN`.
- [ ] APIs, controllers, repositories, caches, search, and exports enforce tenant scope.
- [ ] Tenant inputs and `Host`/Forwarded headers are never treated as authority.
- [ ] Browser session/account switching never reuses prior principal's roles.
- [ ] Security epoch/session/token revocation runs when memberships change or disable.
- [ ] Multi-node, concurrent callbacks, replays, and provisioning races tested where applicable.
- [ ] Fixtures include intentionally colliding `sub`/email/`NameID`/group names.
- [ ] Negative protocol fixtures are validly signed to isolate issuer/audience checks.
- [ ] Cross-tenant authorization tests use a **valid logged-in user** and an existing resource in another tenant.
- [ ] Positive controls cover A→A, B→B, and dual-membership if permitted.
- [ ] Never log raw `SAMLResponse`, JWTs, authorization codes, session IDs, or excessive PII.
- [ ] Monitoring tracks unknown issuers, identity collisions, cross-tenant denials, and revocation latency.
- [ ] Staging E2E covers multiple IdPs, browsers, proxies, and certificate rotations.
- [ ] QA report documents AuthN/trust, identity binding, AuthZ/data isolation, session, and E2E coverage.

## 37. Conclusion

**Multi-IdP and multi-tenant SSO is secure only when three boundaries are verified independently:**

1. **IdP trust boundary:** OIDC tokens/authorization responses or SAML Responses must originate from the **right issuer, right client/registration, and right audience/recipient**, signed by trusted keys.
2. **Identity binding boundary:** users map via **scoped external identities** to exact app accounts, never by unscoped emails, usernames, `NameID`s, or bare subjects.
3. **Tenant/data authorization boundary:** accounts see only tenants and resources with active memberships/grants; global roles, request tenants, UI selections, and caches never replace ACLs.

Tests must include both **positive paths** (A into A, B into B) and **negative paths** (B into A, issuer/signer mix-ups, colliding email/`sub`, colliding `Admins` groups, stale sessions/caches). An SSO provider accepting a valid token does not prove the backend isolates data across tenants. And a MockMvc test with `@WithMockUser` does not prove token/SAML trust validation.

### Standards and Framework References

1. OpenID Connect Core 1.0, Claim Stability and Uniqueness — `iss+sub` pair: https://openid.net/specs/openid-connect-core-1_0.html
2. RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification (mix-up): https://www.rfc-editor.org/rfc/rfc9207.html
3. Spring Security — OAuth2 Login Core Configuration, multiple registrations and redirect URIs: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
4. Spring Security — OAuth2 Login Advanced, `OidcUserService`: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
5. Spring Security — SAML2 Login Overview, `RelyingPartyRegistration` and trust: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
6. Spring Security — SAML2 Authentication/validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
7. Spring Security — OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
8. Spring Security — Resource Server JWT, issuer/audience validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
9. OASIS SAML 2.0 Core, Issuer, NameID, Audience, and SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
10. IETF RFC 7643 — SCIM Core Schema, `id`/`externalId`: https://www.rfc-editor.org/rfc/rfc7643.html
11. OWASP — IDOR prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
12. OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
