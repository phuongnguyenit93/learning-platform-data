# Mapping OidcUser and Saml2AuthenticatedPrincipal into a Common Identity Model

> **Topic:** Spring Security – federation. **Group:** OIDC and Brokering. This lesson explains how a Java/Spring Security application accepts users from **OpenID Connect (OIDC)** and **SAML 2.0**, normalizes the authenticated attributes into a **common identity model**, binds them to local accounts without confusing issuers/tenants, and maps authorities in a controlled way. Includes Spring Security 6.x and 7.x Servlet examples and standalone Java 17 programs.

## 1. Why Normalize Both Principal Types?

An application may need to support simultaneously:

- **OIDC login:** the user picks an OpenID Provider (OP) and Spring Security authenticates via OIDC Authorization Code Flow; the principal is typically `OidcUser`.
- **SAML 2.0 login:** the user is sent to an Identity Provider (IdP), returns a SAML Response at the Assertion Consumer Service (ACS); Spring Security validates it and builds a `Saml2Authentication`, which in 6.x typically holds a `Saml2AuthenticatedPrincipal`.
- **Broker/identity federation:** an identity broker bridges protocols—for instance accepting SAML upstream while serving OIDC downstream to the application. Here the application sees only `OidcUser` from the broker rather than the original SAML Assertion.
- **Multi-tenant:** each tenant selects a different IdP/OP, or one IdP/OP exposes multiple realms/issuers, claims, and policies.

The business layer should not write protocol-specific `if/else` branches for every operation. Operations like "find account", "display name", "check report-viewing permission", or "read tenant" should operate on **one internal identity view**. Yet that identity view must never discard the security fields that establish **identity provenance**.

**Immediate takeaway:** You can **normalize how identity is consumed**, never **equate identity proofs**. Two users sharing an email from two different providers **do not automatically map to the same account**. Preserve issuer + subject alongside tenant/registration context, and keep **external identity**, **local account**, and **authorities** separate.

## 2. Three Architectural Layers to Distinguish

~~~text
                  Trusted Authentication Sources
                 /                              \
           OIDC Provider                     SAML IdP
           ID Token/UserInfo                 Response/Assertion
                 |                              |
                 v                              v
           Spring oauth2Login()          Spring saml2Login()
           OAuth2AuthenticationToken     Saml2Authentication
           principal: OidcUser            6.x: Saml2AuthenticatedPrincipal
                                          7.x: assertion accessor
                 \                              /
                  \                            /
                   v                          v
                    Validated identity adapter
                        (protocol-aware)
                               |
                               v
                     ExternalIdentityKey
                   tenant + issuer + subject
                   (+ SAML NameID semantics)
                               |
                               v
                     Explicit account link
                       / local user ID
                               |
                               v
                   CommonIdentity / UserContext
                  localUserId, tenant, display,
                  permissions, auth provenance
                               |
                               v
                    Business authorization
                  resource-level tenant checks
~~~

There are three distinct data artifacts:

1. **Source evidence (protocol-specific):** OIDC ID Token/claims or SAML Assertion/NameID/AttributeStatement. They differ in structure and security validation.
2. **External identity binding key (external identity key):** a **verified** identifier within an issuer domain with an explicit namespace; used to look up the mapping to a local account.
3. **Application account and session (CommonIdentity):** the application-managed `localUserId`, tenant, account status, granted permissions, and display fields. This is what the business layer should consume.

**Avoid** passing raw `OidcUser` or `Saml2AuthenticatedPrincipal` into every service and interpreting `email`/`groups` inconsistently everywhere. That causes divergent authorization logic across controllers and makes swapping IdPs/brokers painful.

## 3. OIDC and SAML Have Different Native Identifiers

| Aspect | OIDC | SAML 2.0 |
|---|---|---|
| Identity proof | ID Token issued by OP and verified | Assertion from IdP inside a verified SAML Response |
| Origin issuer | `iss` in ID Token | Assertion/IdP `saml:Issuer` per registration |
| Origin subject | `sub` in ID Token | `saml:NameID`, including value and Format/qualifier semantics |
| Basic safe binding key | **`(iss, sub)` pair** | **IdP Issuer + contracted NameID (Format/qualifiers) + required RP/tenant scope** |
| Can identifiers be pairwise? | Yes: `sub` can vary across clients/sectors | Yes: persistent NameID can be scoped to a specific SP |
| Attribute/claim map | `Map<String,Object>` | `Map<String,List<Object>>` in principal/accessor APIs |
| Email | `email` + `email_verified` (if present) | Email is typically an Attribute, with no universal `email_verified` equivalent |
| Display name | `name`, `given_name`... | `displayName`, `givenName`... per IdP attribute contract |
| Groups/roles | No mandatory `groups` claim in OIDC Core | No mandatory `groups` Attribute name in SAML |
| IdP session | `sid` if supported by provider, `auth_time`... | `AuthnStatement.SessionIndex` and SAML conditions |
| Local session | Spring Security session/Authentication | Spring Security session/Authentication |
| Federated logout | OIDC RP-initiated/back-channel logout if supported | SAML Single Logout (SLO) if supported |

**OIDC Core §5.7:** `iss` and `sub` together form the stable end-user identifier within the issuer scope; `email` and `preferred_username` **must not be trusted as unique/immutable keys**. Pairwise subjects can even differ between two clients of the same OP.

**SAML:** `NameID` is not inherently durable. A `transient NameID` can change per session; only a `persistent NameID` is suitable for account binding when IdP and SP agree on format/namespace. `NameQualifier`, `SPNameQualifier`, and other NameID fields affect semantics; if a framework adapter sees only `getName()`, rely on **federation-level contracts and validation** before treating it as a stable key.

## 4. What Does OidcUser in Spring Security Actually Contain?

`org.springframework.security.oauth2.core.oidc.user.OidcUser` extends `OAuth2User` and claim-accessor interfaces. In a successful OIDC login, it can provide:

| API | Contents | Notes |
|---|---|---|
| `getIdToken()` | `OidcIdToken` holding ID Token claims | Never expose the raw token to clients or logs |
| `getUserInfo()` | `OidcUserInfo` if present | May be `null` |
| `getClaims()` | Merged claims map from ID Token + UserInfo if present | Claims may conflict or be missing; policy must be clear |
| `getSubject()` | `sub` | Stable only within `iss` |
| `getIssuer()` | URL of `iss` | Use the verified issuer string; never guess from email domain |
| `getEmail()` | `email` claim if present | Not guaranteed unique |
| `getEmailVerified()` | Boolean `email_verified` if present | May be null; does not mean the user is authorized |
| `getFullName()` | `name` claim if present | Display only; mutable |
| `getPreferredUsername()` | `preferred_username` claim if present | Never use as primary subject key |
| `getAuthorities()` | GrantedAuthority from OIDC client login and any mapper | Not automatically equivalent to SAML groups |
| `getName()` | Principal name configured by implementation | Should not replace `(iss,sub)` in binding keys |

A common Authentication type is `OAuth2AuthenticationToken`. Call `getAuthorizedClientRegistrationId()` to learn which **OAuth2 ClientRegistration** participated in login; that is a Spring configuration key, not `iss` and not a tenant ID.

### 4.1. Example ID Token Claims After Validation

~~~json
{
  "iss": "https://oidc.example.org/realms/workforce",
  "sub": "account-9d7e",
  "aud": "portal-client",
  "exp": 1790000000,
  "iat": 1789996400,
  "email": "reader@example.org",
  "email_verified": true,
  "name": "Report Reader",
  "preferred_username": "reader"
}
~~~

This is **illustrative JSON**, not a signed JWT. Example timestamps must not be used for real validity checks. A production ID Token carries a signature/JWS and OIDC Core validations. When mapping, **never parse raw JSON from the browser**; accept only `OidcUser` from an Authentication validated by Spring Security.

### 4.2. Verify the ID Token Before Accepting Claims

Core checks in the OIDC Authorization Code Flow include:

- Signature/algorithm from JWKS or pinned key per OP trust.
- `iss` matches **the registered provider's issuer metadata**.
- `aud` includes the corresponding client ID; enforce `azp` per profile rules when required.
- `exp`, `iat`, and valid time windows within allowed clock skew.
- `nonce` verified when the request sent a nonce; OAuth2 `state`/redirect URI bound to session/browser.
- If UserInfo is used, `sub` in UserInfo must **match exactly** `sub` in the ID Token.
- HTTPS for discovery/JWKS/UserInfo/token endpoints, and protected client secrets.
- Never replace a trusted provider's issuer/JWKS URI with a free-form user-supplied URL (prevents SSRF/trust substitution).

Spring Security's OIDC login performs these verification steps by default per provider configuration; the mapper layer **must not rewrite JWT verification**. However, integrating a custom decoder or user-service must never bypass the checks above.

## 5. Saml2AuthenticatedPrincipal in Spring Security 6.x

In Spring Security **6.x** applications, a successful SAML login typically produces a `Saml2Authentication` with a principal of type `Saml2AuthenticatedPrincipal`, commonly implemented by `DefaultSaml2AuthenticatedPrincipal`.

Key getters:

| 6.x Getter | Meaning |
|---|---|
| `getName()` | Principal name, defaulting typically to the NameID of the verified Assertion |
| `getAttributes()` | `Map<String,List<Object>>` holding SAML attributes |
| `getAttribute("groups")` | List of all values for the attribute; may be null |
| `getFirstAttribute("mail")` | First single value; may be null |
| `getRelyingPartyRegistrationId()` | Active SP ↔ IdP registration key |
| `getSessionIndexes()` | Session indexes associated with the SAML AuthnStatement |

Unlike OIDC's `String → Object` map, SAML `getAttributes()` is `String → List<Object>` because a `saml:Attribute` can hold **multiple `AttributeValue` elements**. A `groups` claim might contain `reader` and `finance`, while email has one value. Do not force every SAML value to String or call `getFirstAttribute` for groups and drop the rest.

### 5.1. Example Library-Verified SAML Assertion

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion_123">
  <saml:Issuer>https://saml.example.org/entity</saml:Issuer>
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
      employee-4fa1
    </saml:NameID>
  </saml:Subject>
  <saml:AttributeStatement>
    <saml:Attribute Name="mail">
      <saml:AttributeValue>reader@example.org</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="displayName">
      <saml:AttributeValue>Report Reader</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="groups">
      <saml:AttributeValue>report-readers</saml:AttributeValue>
      <saml:AttributeValue>finance</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
~~~

This is an **illustrative XML fragment**, missing a full signed Response/Assertion, Conditions, Audience, Recipient, and protocol elements; it is **not a valid SAMLResponse**. In real execution, Spring Security/OpenSAML must verify signature/trust, Issuer, Destination/Recipient, NotBefore/NotOnOrAfter, SubjectConfirmation, Audience, and InResponseTo/replay.

**Specifically:** Having `mail=reader@example.org` in the fragment does not guarantee this person owns that email; SAML lacks a universal `email_verified` flag across all IdPs. Populate email into display/contact fields only when the IdP contract permits, never as an auto-link key.

### 5.2. Distinguishing SAML AuthenticationToken vs. Authentication

- `Saml2AuthenticationToken` represents a newly received SAMLResponse from the browser, **not yet authenticated**; never read NameID/roles from this token to establish a session.
- `Saml2Authentication` is the post-validation Authentication created by the provider; it carries the principal, authorities, and optionally raw XML via `getSaml2Response()`.
- Map identity only **after** provider validation; never Base64-decode raw `SAMLResponse` in a controller to extract claims.
- `getSaml2Response()` may contain PII and session data; never log it or return it directly from an API.

## 6. Spring Security 7.x: Do Not Cast Principal to Saml2AuthenticatedPrincipal by Default

Important version difference:

**In Spring Security 7.x**, `Saml2AuthenticatedPrincipal` and `DefaultSaml2AuthenticatedPrincipal` are marked **deprecated**. The framework decouples Assertion details from the principal to support custom principals and Single Logout cleanly.

Recommended access path in the documentation:

~~~text
Authentication
  └── Saml2AssertionAuthentication
        ├── getPrincipal()     = principal chosen by app/framework
        ├── getName()          = Spring principal name (customizable)
        ├── getRelyingPartyRegistrationId()
        └── getCredentials()
              └── Saml2ResponseAssertionAccessor
                    ├── getNameId()
                    ├── getAttributes()
                    ├── getAttribute(name)
                    ├── getFirstAttribute(name)
                    ├── getSessionIndexes()
                    └── getResponseValue() [SENSITIVE]
~~~

- `Saml2AssertionAuthentication` is a subclass of `Saml2Authentication`.
- `getCredentials()` on that subclass returns `Saml2ResponseAssertionAccessor`, **not a password**.
- `getNameId()` is the raw NameID provided by the accessor; `getName()` on the Authentication may be a local account name from a custom converter and **need not match**.
- `getRelyingPartyRegistrationId()` lives on `Saml2AssertionAuthentication`.
- `getResponseValue()` is the raw XML Response; **never expose it to the browser or logs**.
- If an app customizes `ResponseAuthenticationConverter` to return legacy `Saml2Authentication`, code expecting only `Saml2AssertionAuthentication` needs an explicit policy: reject or use a dedicated 6.x adapter.

**What does not change:** Spring Security must still verify SAML signatures/conditions before returning Authentication. Never use API migration as an excuse to bypass validation or parse Assertions manually from the request.

### 6.1. Comparing 6.x and 7.x APIs

| Purpose | Common SAML 6.x | Default SAML 7.x |
|---|---|---|
| Authentication | `Saml2Authentication` | `Saml2AssertionAuthentication` |
| Read NameID | `Saml2AuthenticatedPrincipal.getName()` | `Saml2ResponseAssertionAccessor.getNameId()` |
| Read attributes | `principal.getAttributes()` | `auth.getCredentials().getAttributes()` |
| Get first attribute | `principal.getFirstAttribute(name)` | `accessor.getFirstAttribute(name)` |
| Registration ID | `principal.getRelyingPartyRegistrationId()` | `auth.getRelyingPartyRegistrationId()` |
| SessionIndexes | `principal.getSessionIndexes()` | `accessor.getSessionIndexes()` |
| Custom principal support | Requires care with session/SLO dependencies | Assertion accessor separated; cleaner support |
| Read IdP Issuer | Selected from trusted RelyingPartyRegistration | Selected from trusted RelyingPartyRegistration |
| OIDC user | `OidcUser` | `OidcUser` (same API family) |

**Do not assume** `OidcUser` and `Saml2AuthenticatedPrincipal` implement a shared interface exposing identical issuer and attribute methods. `AuthenticatedPrincipal.getName()` can be shared, yet it is **insufficient** as a safe identity key.

## 7. Defining the Common Identity Model: What Must Be Preserved?

A practical model can be split into:

### 7.1. ExternalIdentityKey – Identity Provenance

| Field | Meaning | Required? |
|---|---|---|
| `protocol` | OIDC or SAML | Yes |
| `issuer` | Verified issuer of the OP/IdP | Yes |
| `subject` | OIDC `sub` or contracted SAML NameID | Yes |
| `tenantId` | Tenant resolved by the app from registration/trust context | Yes in multi-tenant systems |
| `nameIdFormat` | Format of SAML NameID (not applicable to OIDC) | Yes when affecting identity semantics |
| `nameQualifier/spNameQualifier` | SAML identifier qualifiers if used by the IdP | Per contract |
| `registrationId` | Spring configuration key for audit/routing | Recommended, never replaces issuer |
| `sourceClientId` | OIDC ClientRegistration/client ID if managing pairwise `sub` | Per contract |

For OIDC, the **`(iss,sub)` pair** is the standards-based end-user key; adding `tenantId` and `registrationId` provides **application scoping** to prevent unintended cross-tenant linking, not because OIDC requires them inside the subject key.

For SAML, `NameID` has varying formats/qualifiers, so `(issuer,getName())` alone can be **insufficient** across SP, NameID Format, or NameQualifier changes. Define stable keys under a **concrete NameID contract**, and **reject automatic linking** if the format is transient or lacks stability guarantees.

### 7.2. CommonIdentity – Application Identity After Account Linking

Possible model design:

~~~text
CommonIdentity
  localUserId       : UUID/String (issued by the application)
  tenantId          : String (data scope)
  displayName       : String (for UI; not unique)
  primaryEmail      : String? (contact info)
  emailProof        : VERIFIED_OIDC | CONTRACTUAL_SAML | UNVERIFIED | NONE
  accountStatus     : ACTIVE | LOCKED | DISABLED
  loginSource       : OIDC | SAML
  loginRegistration : String
  authorities       : Set<String> (from internal policy)
  authContext       : safe metadata, containing no raw tokens
~~~

This is a **recommended domain model**, not a built-in Spring Security class. `localUserId` appears **only after** `ExternalIdentityKey` has been matched against the link table/local accounts. The business layer uses `localUserId + tenantId` as identity rather than trusting email or NameID as a global ID.

### 7.3. AccountLink – Multi-Protocol Linking Table

~~~text
ExternalIdentityLink
  tenantId
  providerType     [OIDC / SAML]
  issuer
  subject
  nameIdFormat
  qualifiers
  registrationId
  localUserId
  verifiedAt
  provenance
  linkMethod       [ADMIN_APPROVED / REAUTHENTICATED_USER]
  enabled
~~~

**Database constraints:** The unique key must include the required identity namespace. The link table must never have a unique key on `email`, since emails can collide, change, or be recycled. One local account may hold **two link records**—one OIDC identity and one SAML identity—only after verification and approval.

### 7.4. Are Two People with the Same Email the Same User?

Not by default. Example:

- OIDC `iss=https://oidc-a.example.org`, `sub=100`, `email=reader@example.org`.
- SAML `Issuer=https://saml-b.example.org`, `NameID=other-100`, `mail=reader@example.org`.

Two distinct identities can share an email. One side might have controlled the email at registration as an attacker, while the other is a separate corporate account. **Auto-merging** risks **account takeover**. Email is only a hint for an **account-linking workflow with proof of ownership and/or approval**, never a unique key.

## 8. Normalization Pipeline per Source (Without Dropping Validation)

### 8.1. OIDC Pipeline

~~~text
Browser -> OAuth2 Authorization Code (+ state/PKCE/nonce per profile)
        -> OP/Token endpoint
        -> Spring Security OAuth2/OIDC authentication
        -> ID Token signature/iss/aud/exp/nonce validation
        -> UserInfo sub == ID Token sub (if used)
        -> OAuth2AuthenticationToken + OidcUser
        -> OIDC IdentityAdapter
        -> ExternalIdentityKey(protocol=OIDC, issuer=iss, subject=sub)
        -> AccountLink lookup / secure provisioning
        -> CommonIdentity
~~~

**Never include:** raw ID Tokens, refresh tokens, or access tokens in the CommonIdentity DTO or logs. They have separate lifecycles, audiences, and scopes of use.

### 8.2. SAML Pipeline

~~~text
Browser -> SAML SSO / AuthnRequest / IdP
        -> HTTP POST SAMLResponse at ACS
        -> Spring Security OpenSAML provider
        -> Verify signature + issuer/trust + audience/recipient
           + conditions/time + InResponseTo/replay
        -> Saml2Authentication (6.x) / Saml2AssertionAuthentication (7.x)
        -> SAML IdentityAdapter
        -> ExternalIdentityKey(protocol=SAML,
           issuer=configured IdP issuer, subject=NameID)
        -> AccountLink lookup / secure provisioning
        -> CommonIdentity
~~~

SAML attributes `groups`/`role` are data **signed by the IdP** and validated, yet still require a **mapping policy**. Never extract `ROLE_ADMIN` from browser-submitted XML before verification; nor trust any arbitrary IdP to dictate internal privileges directly.

### 8.3. Never Normalize by Reading Raw HTTP Bodies

**Anti-pattern:**

~~~java
// UNSAFE: name/role from browser input without IdP trust.
String email = request.getParameter("email");
String issuer = request.getParameter("issuer");
// Do not build CommonIdentity or GrantedAuthority from these values.
~~~

Another anti-pattern is Base64-decoding `SAMLResponse` manually, using XPath to extract `NameID` and groups, and creating a local session without OpenSAML. Likewise, Base64-decoding a JWT payload without verifying signature/issuer/audience/nonce and calling it OIDC login.

**Adapt data only from a successful Authentication** of the right type that passed framework validation. If the application uses custom converters or providers, write integration tests proving full validation remains intact.

## 9. Standalone Java 17: Cross-Protocol Identities and Explicit Account Linking

This is a **standalone Java 17+ program** illustrating how one local account can link **two different external identities** once the application owner approves. It **does not** verify OIDC/SAML cryptography; external keys are assumed already validated by the IdP/OP layer.

File `IdentityLinkDemo.java`:

~~~java
import java.util.Map;
import java.util.Objects;

public class IdentityLinkDemo {

    enum Protocol { OIDC, SAML }

    record ExternalKey(
            Protocol protocol,
            String tenant,
            String issuer,
            String subject,
            String subjectFormat) {

        ExternalKey {
            Objects.requireNonNull(protocol);
            require(tenant);
            require(issuer);
            require(subject);
            Objects.requireNonNull(subjectFormat);
        }

        static void require(String value) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("missing identity field");
            }
        }
    }

    public static void main(String[] args) {
        ExternalKey oidc = new ExternalKey(
                Protocol.OIDC, "team-a",
                "https://oidc.example.org", "sub-123", "");

        ExternalKey saml = new ExternalKey(
                Protocol.SAML, "team-a",
                "https://saml.example.org/entity", "employee-77",
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent");

        ExternalKey otherIssuer = new ExternalKey(
                Protocol.OIDC, "team-a",
                "https://other.example.org", "sub-123", "");

        Map<ExternalKey, String> approvedLinks = Map.of(
                oidc, "local-user-001",
                saml, "local-user-001");

        System.out.println("OIDC local=" + approvedLinks.get(oidc));
        System.out.println("SAML local=" + approvedLinks.get(saml));
        System.out.println("Other issuer=" + approvedLinks.get(otherIssuer));
        System.out.println("Keys equal=" + oidc.equals(saml));
    }
}
~~~

Run:

~~~bash
javac IdentityLinkDemo.java
java IdentityLinkDemo
~~~

Exact stdout:

~~~text
OIDC local=local-user-001
SAML local=local-user-001
Other issuer=null
Keys equal=false
~~~

**Explanation:**
1. Two different keys **do not auto-merge**, yet `approvedLinks` explicitly maps both to the same local account after an approved workflow.
2. Same subject text `sub-123` under a **different issuer** does not match the map.
3. OIDC and SAML have distinct protocol/issuer/subject semantics, so `oidc.equals(saml)` is false.
4. Email is absent from the unique key by deliberate design.
5. Java `record` provides field-wise equality/`hashCode`; in production, store data with database integrity/uniqueness constraints and prevent unauthorized link updates.

**Security limitation:** This program verifies no ID Tokens or SAML Assertions, checks no tenant ownership, NameID qualifiers, sessions, roles, or proof of user approval. It illustrates **post-authentication** logic, not a login module.

## 10. Java Spring Security 7.x: Adapting OIDC and SAML into a Unified Snapshot

This sample uses **Spring Security 7.x Servlet** to extract fields from `OAuth2AuthenticationToken/OidcUser` and `Saml2AssertionAuthentication/Saml2ResponseAssertionAccessor`. It builds a **classified external snapshot**, without looking up or provisioning local accounts itself.

File `src/main/java/com/example/federation/ExternalIdentityAdapter.java`:

~~~java
package com.example.federation;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;

public final class ExternalIdentityAdapter {

    private ExternalIdentityAdapter() {
    }

    public record ProviderPolicy(
            String protocol, String tenantId, String expectedIssuer) {
    }

    public record Snapshot(
            String protocol,
            String tenantId,
            String registrationId,
            String issuer,
            String subject,
            String displayName,
            String emailCandidate,
            boolean emailVerifiedByProtocol) {
    }

    // Demo policy: must stay aligned with admin-approved
    // ClientRegistration and RelyingPartyRegistration entries.
    private static final Map<String, ProviderPolicy> POLICIES = Map.of(
            "work-oidc", new ProviderPolicy(
                    "OIDC", "team-a",
                    "https://oidc.example.org/realms/workforce"),
            "work-saml", new ProviderPolicy(
                    "SAML", "team-a",
                    "https://saml.example.org/entity"));

    public static Snapshot extract(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new IllegalArgumentException("authentication required");
        }

        if (authentication instanceof OAuth2AuthenticationToken oauth
                && oauth.getPrincipal() instanceof OidcUser oidc) {
            String registrationId = oauth.getAuthorizedClientRegistrationId();
            ProviderPolicy policy = policy(registrationId, "OIDC");

            String issuer = Objects.requireNonNull(
                    oidc.getIssuer(), "OIDC issuer required").toString();
            if (!policy.expectedIssuer().equals(issuer)) {
                throw new IllegalArgumentException("unexpected OIDC issuer");
            }

            String subject = require(oidc.getSubject(), "OIDC sub");
            return new Snapshot(
                    "OIDC", policy.tenantId(), registrationId,
                    issuer, subject, oidc.getFullName(),
                    oidc.getEmail(),
                    Boolean.TRUE.equals(oidc.getEmailVerified()));
        }

        if (authentication instanceof Saml2AssertionAuthentication saml) {
            String registrationId = saml.getRelyingPartyRegistrationId();
            ProviderPolicy policy = policy(registrationId, "SAML");

            // Spring SAML provider already validated the issuer against
            // the matching RelyingPartyRegistration. Read issuer from
            // SERVER POLICY, never from a query parameter.
            Saml2ResponseAssertionAccessor accessor = saml.getCredentials();
            String subject = require(accessor.getNameId(), "SAML NameID");
            Map<String, List<Object>> attrs = accessor.getAttributes();

            return new Snapshot(
                    "SAML", policy.tenantId(), registrationId,
                    policy.expectedIssuer(), subject,
                    firstString(attrs, "displayName"),
                    firstString(attrs, "mail"),
                    false);
        }

        throw new IllegalArgumentException("unsupported auth mechanism");
    }

    private static ProviderPolicy policy(
            String registrationId, String expectedProtocol) {
        ProviderPolicy result = POLICIES.get(registrationId);
        if (result == null || !expectedProtocol.equals(result.protocol())) {
            throw new IllegalArgumentException("unknown federation registration");
        }
        return result;
    }

    private static String require(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("missing " + field);
        }
        return value;
    }

    private static String firstString(
            Map<String, List<Object>> values, String name) {
        List<Object> items = values.get(name);
        if (items == null || items.size() != 1) {
            return null;
        }
        Object first = items.get(0);
        return first instanceof String str && !str.isBlank() ? str : null;
    }
}
~~~

### 10.1. Why Is the Code Written This Way?

1. **Accepts only authenticated `Authentication`**, checking types before casting. In apps with anonymous, form-login, or other auth types, the adapter **rejects** instead of guessing.
2. **OIDC:** reads `getIssuer()` and `getSubject()` from `OidcUser` and verifies the issuer matches the registered policy to catch misconfigurations. `getAuthorizedClientRegistrationId()` is only a lookup key into client config and does not replace `iss`.
3. **SAML 7.x:** reads NameID from `Saml2AssertionAuthentication.getCredentials().getNameId()`. The IdP issuer comes from the **server-side mapping aligned with the provider-validated registration**, never from a form or browser string.
4. **Attributes:** `getAttributes()` maps to lists, so `firstString` accepts only an exact single String. For group arrays, use a dedicated helper iterating over the list.
5. **Email:** OIDC has `email_verified`; the SAML demo sets `emailVerifiedByProtocol=false` since SAML has no universal equivalent flag. Raising proof level for SAML email requires an out-of-protocol **IdP contract**, never an assumption that it is verified.
6. **Grants no permissions:** Snapshot is classified source data. It **is not a local account** and creates no `GrantedAuthority`.
7. **Omits raw tokens:** The code never reads `getIdToken().getTokenValue()` or `getResponseValue()`. This protects privacy and prevents token leakage.
8. **Careful with IdP issuer:** The Spring SAML validator is assumed intact; if a custom provider drops issuer/signature checks, this sample is unsafe. In production, generate/reconcile the policy catalog from an **authoritative federation registry** alongside the registration repository rather than two configs that can drift apart.
9. **NameID Format:** The accessor API used here does not surface full format/qualifiers in the snapshot. This code alone **is insufficient for durable automatic account linking** without a persistent NameID contract enforced at IdP/SP.
10. **Spring dependencies:** This Java file requires Spring Security 7.x, a Servlet app, and SAML2 SP/OAuth2 Client dependencies. It will not compile with standalone `javac`.

### 10.2. From Snapshot to Local Account Is a Separate Step

A business service can proceed as:

~~~text
Snapshot (validated, protocol-aware)
   |
   | Build ExternalIdentityKey per federation policy
   v
AccountLinkRepository.findExact(key)
   |
   +-- approved link -> load localUserId -> check account ACTIVE
   |
   +-- no link -> deny or route to provisioning/approval
   |
   +-- ambiguous/disabled -> deny
   |
   v
CommonIdentity(localUserId, tenantId, rolesFromApplication)
~~~

**Note:** The Spring 7 example above neither writes to a database nor treats `emailVerified` as permission to link. Account linking must be an **independent, approved action where the user proves ownership of both identities**, with auditing and safe unlinking.

## 11. If Your Project Still Runs Spring Security 6.x

In 6.x, the OIDC branch can keep similar `OAuth2AuthenticationToken/OidcUser` handling, while SAML needs a branch for `Saml2AuthenticatedPrincipal`. Example **method fragment** (place inside a class with matching imports):

~~~java
if (authentication instanceof Saml2Authentication saml
        && saml.getPrincipal() instanceof Saml2AuthenticatedPrincipal p) {
    String registrationId = p.getRelyingPartyRegistrationId();
    String nameId = p.getName();
    List<?> groups = p.getAttribute("groups");
    Object mail = p.getFirstAttribute("mail");

    // Use registrationId only after Authentication passed through
    // the SAML provider; look up IdP issuer from trusted registration.
    // Never link local accounts solely by mail.
}
~~~

`Saml2AuthenticatedPrincipal` can hold multi-valued attributes, and the principal may be a custom implementation; `instanceof` prevents `ClassCastException`. This is an **illustrative fragment**, not a standalone compilable class, and should not be used verbatim with the Spring Security 7.x default flow.

### 11.1. Upgrade Path 6 → 7

- Search for all `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` usages and direct casts.
- Verify the default Authentication class in integration tests after upgrading.
- On Spring 7, prefer `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor`.
- Check whether custom `ResponseAuthenticationConverter` implementations still return legacy `Saml2Authentication`.
- Ensure SAML Single Logout still has NameID/SessionIndex when custom principals no longer implement the legacy SAML interface.
- Never replace shifted fields with a hand-rolled XML parser.
- Keep unit/integration tests covering the adapter, issuer/tenant identity keys, authorities, and logout.

**Specifically:** `Saml2AuthenticatedPrincipal` is **deprecated in 7.x**, which does not mean the interface vanishes immediately; it signals time to migrate APIs. `Saml2Authentication` remains in the hierarchy, with `Saml2AssertionAuthentication` as a subclass in 7.x.

## 12. Configuring Spring Security to Accept Both OIDC and SAML

A **Servlet** application can enable both entrypoints. Example full application-level Java class:

File `src/main/java/com/example/federation/FederationApplication.java`:

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FederationApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String index() {
        return "Federation demo";
    }

    @GetMapping("/private")
    String protectedPage() {
        return "Authenticated";
    }
}
~~~

This is a Spring Boot class with full imports, yet **cannot run with pure `javac`**. It requires Spring Boot Web/MVC, Security, OAuth2 Client, and SAML2 Service Provider, plus real configured OPs/IdPs. `oauth2Login()` and `saml2Login()` are **two login mechanisms** and do not automatically enable account linking or produce the same Authentication type.

### 12.1. Maven Dependencies

Inside `<dependencies>` of a Spring Boot `pom.xml` with BOM or parent:

~~~xml
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
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

This Maven block is only a **dependencies fragment**, not a standalone `pom.xml`. Spring Security SAML2 may depend on specific OpenSAML repositories per version/BOM. Never copy Spring Security 7 Maven/Java snippets into a 6.x project without checking compatibility.

### 12.2. Two Registrations with Distinct Purposes

In Spring Boot, OIDC clients use `spring.security.oauth2.client.registration`, whereas SAML RPs use `spring.security.saml2.relyingparty.registration`.

Illustrative configuration **containing no secrets**; secrets must be supplied via environment management/secret store before running:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          work-oidc:
            provider: workforce-op
            client-id: portal-client
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          workforce-op:
            issuer-uri: "https://oidc.example.org/realms/workforce"
    saml2:
      relyingparty:
        registration:
          work-saml:
            entity-id: "https://portal.example.org/saml/sp"
            acs:
              location: "https://portal.example.org/login/saml2/sso/work-saml"
            assertingparty:
              metadata-uri: "https://saml.example.org/metadata"
~~~

For a live OIDC confidential client, `client-secret` must come from a secret manager/environment alongside matching client authentication policy; the YAML above **is insufficient** to connect to a confidential provider and shows structure only. For SAML, the IdP must register the SP entityID/ACS and signing certificates, and the metadata URL must be trusted. These are not live endpoints reachable over the internet.

**Two separate registration types:**
- OIDC `work-oidc` belongs to `ClientRegistrationRepository`, with OP issuer verified via the ID Token.
- SAML `work-saml` belongs to `RelyingPartyRegistrationRepository`, with IdP issuer verified via the SAML Response/Assertion.
- Never reuse the same `registrationId` as an issuer or `localUserId`.
- In multi-tenant apps, client/RP registration IDs must also bind to a verified tenant context.

### 12.3. Initiating Login URLs Intentionally

Normally:
- OIDC: `/oauth2/authorization/{registrationId}`.
- SAML: `/saml2/authenticate/{registrationId}`.

An application can render a login picker determining allowed tenant/providers prior to redirect. Never allow a user to alter a query parameter to force an IdP/OP outside their tenant; on callback, preserve state/request correlation and re-verify issuer/tenant scope.

## 13. Broker Model: SAML Upstream, OIDC Downstream

An **identity broker** can play both roles simultaneously:

~~~text
Upstream enterprise SAML IdP
      |
      | SAML Response / Assertion
      v
  Identity broker
      | - Validate SAML signature/conditions/trust
      | - Match upstream NameID to broker identity
      | - Map attributes by approved rules
      | - Create broker SSO session
      | - Issue NEW OIDC ID Token as broker issuer
      v
Downstream Spring application
      | oauth2Login()
      v
  OidcUser
    iss = broker issuer
    sub = broker subject
~~~

**Protocol translation does not mean** the application receives a `Saml2AuthenticatedPrincipal`. If the broker emits OIDC downstream, the Spring app **sees only OIDC Authentication/`OidcUser`**, unless the broker attaches custom claims describing upstream identity.

### 13.1. Identities at Two Different Layers

| Layer | Source / Issuer | Subject |
|---|---|---|
| SAML upstream | Enterprise IdP issuer | NameID per SAML contract |
| Broker account | Broker internal identity store | Broker local subject |
| OIDC downstream | **Broker OIDC issuer** | Broker `sub`, potentially pairwise per client |

The downstream application should authenticate **`(broker iss, broker sub)`** as its direct identity. If upstream provenance is needed, the broker can emit contracted provenance claims, yet never treat `upstream_issuer`/`upstream_nameid` claims as equivalent to the raw SAML Assertion when the app **did not directly verify SAML**.

### 13.2. A Broker Is Not a Format-Swapping Token Converter

An anti-pattern is:
- Decode SAML Response.
- Copy `NameID` into OIDC `sub`.
- Copy `email` and `groups` and sign an arbitrary JWT.
- Expect downstream apps to trust it without an issuer registry, trust framework, or claims policy.

A proper broker must:
1. Act as SP toward upstream SAML; validate signed Response/Assertion and SAML conditions.
2. Link the upstream subject to a broker account via a stable key/approved linking.
3. Apply claim/role mapping policies (never blindly pass every group as a downstream privilege).
4. Act as an OIDC Provider with its own issuer/JWKS/audience/ID Token and standard OIDC checks.
5. Manage sessions and logout on both sides, with documented propagation limits.
6. Maintain clear auditing, unlinking, and account lifecycle controls.

**Separate the two sources of truth:** The enterprise IdP vouches for the upstream subject; the broker vouches to the downstream app for the **broker subject**. A downstream app cannot derive the upstream NameID by string transformation unless the broker provides a contract and verifiable provenance mechanism.

## 14. Claim Mapping: Preserve Semantics, Not Just Names

### 14.1. Suggested Mapping Table

| Common Field | OIDC Source | SAML Source | Rule |
|---|---|---|---|
| `protocol` | `OIDC` | `SAML` | Keep provenance explicit |
| `issuer` | ID Token `iss` | Trusted IdP issuer in RP registration | Never read from client-supplied email/URL |
| `subject` | ID Token `sub` | Validated NameID | Never treat as a global ID |
| `registrationId` | `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` | SAML RP registration ID | Use for auditing/routing |
| `tenantId` | Looked up from trusted OIDC registration | Looked up from trusted SAML registration | Never trust a self-asserted `tenant` claim without policy |
| `displayName` | `name` or allowed nickname | `displayName`/`givenName` per contract | UI only; not unique |
| `emailCandidate` | `email` | `mail`/URI claim per IdP contract | May be absent or mutable |
| `emailProof` | `email_verified=true` if OP is trusted | Separate contract; no universal standard | Never use email as unique key |
| `groups` | Provider-specific claim | Multi-value SAML attribute | Validate type + issuer/tenant mapping |
| `authorities` | Spring/OIDC mapper and app policy | Spring/SAML converter and app policy | Result of local policy |
| `authTime` | `auth_time` if present | `AuthnInstant` if present | Distinct from session creation time |
| `sessionHandle` | `sid` if present | `SessionIndex` per AuthnStatement | Used for logout, not as user ID |
| `localUserId` | Not provided by OP by default | Not provided by IdP by default | Issued by internal account linking |

### 14.2. Data Types Differ Too

OIDC:
- `getClaims()` is `Map<String,Object>`.
- A provider-specific `groups` claim may be a `List<String>`, `String`, or nested JSON structure.
- `getEmailVerified()` is Boolean or null.
- `getUserInfo()` may be absent.

SAML:
- `getAttributes()` is `Map<String,List<Object>>`.
- Can hold multiple `AttributeValue` elements, not just one `String`.
- Attribute names may be URI claims like `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress` instead of `mail`.
- NameID Format/qualifiers determine identity semantics beyond raw text.
- `SessionIndexes` is a list, not the local HttpSession.

**Common mistake:** serializing the SAML map into a flat JSON object by taking the first value of every attribute; if `groups` has two values, one role disappears, and if `email` has two values, an arbitrary one gets picked. When a field is expected to be single-valued, **reject ambiguity** per contract; when multi-valued, read all elements and validate types.

### 14.3. Before-and-After Illustration

Before normalization:

~~~text
OIDC:
  iss=https://oidc.example.org
  sub=user-A1
  email=reader@example.org
  email_verified=true
  roles=["finance-readers"]

SAML:
  Issuer=https://saml.example.org/entity
  NameID=persistent-user-9
  mail=["reader@example.org"]
  groups=["finance-readers", "operations"]
~~~

After adapter and approved account linking:

~~~text
CommonIdentity:
  localUserId=local-user-001
  tenantId=team-a
  displayName=Report Reader
  authorities=["ROLE_REPORT_VIEW"]
  linked identities:
    - protocol=OIDC, issuer=https://oidc.example.org, subject=user-A1
    - protocol=SAML, issuer=https://saml.example.org/entity,
      subject=persistent-user-9, nameIdFormat=persistent
~~~

This is an **illustrative business outcome**, not proof that the two sources above must merge because they share an email. `local-user-001` appears only after an **approved linking workflow**.

## 15. Mapping Groups/Roles to GrantedAuthority

An application may use `@PreAuthorize`, `hasRole("ADMIN")`, or `hasAuthority("ROLE_REPORT_VIEW")`. Those expressions inspect Spring Security **`GrantedAuthority`** instances—they **do not automatically read** `OidcUser.getClaims().get("groups")` or SAML `AttributeStatement`.

### 15.1. Proper Mapping Model

~~~text
Trusted IdP/OP + validated claim/group
                 |
                 v
    Tenant/provider-specific allowlist
                 |
                 v
       Internal business entitlement
                 |
                 v
       GrantedAuthority instances
                 |
                 v
      Controller/Service authorization
~~~

Example policy:

| Protocol | Issuer Scope | Source Claim/Group | Granted Authority |
|---|---|---|---|
| OIDC | Corporate OP | `report-readers` | `ROLE_REPORT_VIEW` |
| SAML | Corporate IdP | `report-readers` | `ROLE_REPORT_VIEW` |
| OIDC | External partner OP | `report-readers` | Not granted unless tenant allows |
| SAML | Any unknown IdP | `ROLE_ADMIN` | **Not granted** |
| Any | Disabled user account | Any claim | **Not granted** |

Never copy all SAML group names straight into authorities, and never prefix all OIDC `roles` with `ROLE_`. Maintain an allowlist scoped by issuer, tenant, and business policy. An IdP may authenticate identity yet **lacks authority to dictate internal business permissions**.

### 15.2. Separating Authentication and Authorization

- **Authentication:** proves which OP/IdP authenticated the user and under what conditions.
- **Identity mapping:** selects the external key, resolves the local account, and prevents user collisions.
- **Authorization:** checks active account status, tenant membership, roles, resource ownership, and contextual policy.

When login succeeds yet the local account is unapproved, the application should **deny resource access** or route to onboarding rather than granting `ROLE_USER` with tenant access automatically. In multi-tenant apps, a request to `/tenants/beta/reports` still requires verifying tenant from the authenticated `CommonIdentity` and permissions on beta resources.

### 15.3. Spring Security Extension Points

**OIDC:** Spring Security supports `GrantedAuthoritiesMapper` and delegation-based `OidcUserService`. Use `OidcUserAuthority`, claims from ID Token/UserInfo, and `OidcUserRequest` context to map after authentication. When registrationId, tenant, or external API lookups are needed, a delegation-based `OidcUserService` usually fits better than a mapper that inspects only authorities.

**SAML:** customize the OpenSAML provider's `ResponseAuthenticationConverter` after Response/Assertion validation to attach authorities to the Authentication. In Spring Security 7, preserve `Saml2AssertionAuthentication` with `Saml2ResponseAssertionAccessor` so SLO remains intact. Never replace the provider with a converter that parses raw `SAMLResponse` manually.

**Common rule:** Mapping only inside a controller for display while leaving default Authentication authorities untouched means `hasAuthority("ROLE_REPORT_VIEW")` in `SecurityFilterChain` **will not recognize** that role. For Spring authorization based on internal roles, attach authorities to Authentication via a version-supported extension point or build an `AuthorizationManager`/service policy consuming a trusted `CommonIdentity`.

## 16. Standalone Java 17: Authorization Policy Without Email

File `AuthorityPolicyDemo.java` runs standalone and simulates an issuer/tenant allowlist:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class AuthorityPolicyDemo {

    record Provider(String tenant, String issuer) {
    }

    static Set<String> authorities(
            Provider provider, List<String> upstreamGroups) {

        Map<Provider, Map<String, String>> approved = Map.of(
                new Provider("team-a", "https://oidc.example.org"),
                Map.of("report-readers", "ROLE_REPORT_VIEW"),
                new Provider("team-a", "https://saml.example.org/entity"),
                Map.of("report-readers", "ROLE_REPORT_VIEW"));

        Map<String, String> mapping = approved.get(provider);
        if (mapping == null || upstreamGroups == null) {
            return Set.of();
        }

        Set<String> result = new TreeSet<>();
        for (String group : upstreamGroups) {
            String authority = mapping.get(group);
            if (authority != null) {
                result.add(authority);
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        Provider trusted = new Provider(
                "team-a", "https://oidc.example.org");
        Provider untrusted = new Provider(
                "team-b", "https://oidc.example.org");

        List<String> groups = List.of(
                "report-readers", "ROLE_ADMIN");

        System.out.println("trusted view=" +
                authorities(trusted, groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("untrusted view=" +
                authorities(untrusted, groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("admin=" +
                authorities(trusted, groups).contains("ROLE_ADMIN"));
    }
}
~~~

Run:

~~~bash
javac AuthorityPolicyDemo.java
java AuthorityPolicyDemo
~~~

Exact stdout:

~~~text
trusted view=true
untrusted view=false
admin=false
~~~

Explanation:
1. Even with the same group name, only the approved issuer+tenant grants `ROLE_REPORT_VIEW`.
2. A provider belonging to `team-b` does not inherit `team-a`'s mapping.
3. The string `ROLE_ADMIN` in upstream groups does not grant admin privileges.
4. `TreeSet` deduplicates before `Set.copyOf` ensures immutability, though the exercise checks membership only.
5. The sample **verifies no SAML/OIDC signatures**; it demonstrates post-authentication allowlist logic. Production requires account status, tenant membership, resource scopes, and real API integration.

## 17. How Do You Link the Same Person Across OIDC and SAML?

### 17.1. Never Auto-Link by Email

Hazards:

- A user at IdP A shares an email with a user at IdP B without being the same person.
- Emails can be recycled after an employee departs.
- One IdP may allow users to set unverified emails while the app trusts the claim.
- OIDC `email_verified=true` confirms email control at a point in time under the OP's trust framework; it **does not authorize taking over a local account**.
- SAML `email`/`mail` attributes lack a standardized verification flag.
- A broker may emit an email from another upstream source while the downstream app lacks provenance visibility.

**Therefore:** Email may only **suggest** a candidate link for user/administrator review, never execute an automatic merge.

### 17.2. A Safer Linking Workflow

1. The user is already authenticated into an **existing local account** through a trusted method.
2. The user explicitly initiates linking a new provider/registration.
3. The application forces **re-authentication** at the new external provider with proper state/nonce/CSRF/binding.
4. Spring Security produces the verified Authentication and the adapter builds the new external key.
5. The application verifies the external key is not linked to another local account and that tenant/issuer are allowed.
6. For sensitive links, require step-up MFA or administrative approval per risk level.
7. Inside a transaction, enforce a unique constraint on the external key and audit provenance/`verifiedAt`; guard against concurrent linking races.
8. If linking fails or the key is already claimed, **never** replace the existing owner and never create a duplicate account under the same email.
9. Provide confirmed unlinking, preventing a user from deleting their final sign-in method if it would unintentionally lock them out.
10. When an IdP/OP migrates issuer/subject schemes, follow a **migration plan and audited administrative mapping**, never guessing links by email.

### 17.3. JIT Provisioning vs. Account Linking

**Just-in-Time (JIT) provisioning** creates a local account the first time a verified external identity signs in. **Account linking** attaches a new external identity to an **already existing local account**. They are distinct operations.

JIT should run only when:
- issuer/tenant/client is permitted;
- subject is stable and collision-free;
- IdP/OP grants an entitlement authorizing app access;
- no conflict exists with another local account/identifier;
- organizational approval/lifecycle gates permit it.

Never use matching email to assume "that's already the old account" during JIT.

## 18. Comparing Identity Across Three Real-World Topologies

### 18.1. Same Employee, Direct OIDC Login

~~~text
OP Corporate:
  iss=https://oidc.example.org/realms/company
  sub=9e4a-uuid
  email=reader@example.org

Spring app:
  OAuth2AuthenticationToken
  OidcUser
  ExternalKey=(OIDC, team-a, iss, sub)
  Local account mapping -> local-user-001
~~~

### 18.2. Same Employee, Direct SAML Login

~~~text
IdP Corporate:
  Issuer=https://saml.example.org/entity
  NameID=persistent-employee-77
  NameID Format=persistent
  mail=[reader@example.org]

Spring app:
  Saml2Authentication / Saml2AssertionAuthentication
  ExternalKey=(SAML, team-a, Issuer, NameID, Format)
  Approved account link -> local-user-001
~~~

Here the two external keys **differ** even though they belong to the same local account. The app knows they represent the same person **only if** linking has been proven and approved.

### 18.3. Same Employee, Upstream SAML via an OIDC Broker

~~~text
Corporate SAML IdP:
  NameID=persistent-employee-77
       |
       v
Broker account:
  broker-user-567
       |
       v
OIDC ID Token to Spring:
  iss=https://broker.example.org/realms/workforce
  sub=broker-sub-567
  email=reader@example.org
       |
       v
Spring:
  OidcUser (NOT Saml2AuthenticatedPrincipal)
  ExternalKey=(OIDC, team-a, broker issuer, broker-sub-567)
~~~

**Crucial point:** When the app trusts only the broker via OIDC, the downstream external key belongs to the **broker**, not automatically to the upstream SAML issuer. The broker owns verifying/binding the upstream identity; the app may inspect provenance claims if contracted, yet cannot substitute them for upstream validation the app did not perform.

## 19. Sessions, Logout, and Identity Preservation During Brokering

Beyond identity, the two protocols differ in **session and logout semantics**:

| Concern | OIDC | SAML |
|---|---|---|
| App browser session | Spring Security session | Spring Security session |
| Provider session | OP SSO session | IdP SSO session |
| Session identifier | `sid` if present, OP tokens/cookies | `SessionIndex` if emitted by IdP |
| Logout protocol | OIDC RP-initiated/back-channel/front-channel per support | SAML Single Logout per binding/support |
| Access token | May exist; needs separate revocation/lifecycle | Not part of standard SAML login |
| Local logout | Clears only app session unless federated logout runs | Clears only app session unless SLO runs |
| Federated logout via broker | Requires proper bridge/session mapping | Requires proper bridge/session mapping |

**Never conflate:** SAML `SessionIndex` is not OIDC `sid`, and neither is the app's `JSESSIONID`. Logging out of the Spring app does not automatically log out of the broker's upstream IdP or vice versa. If "log out of every connected app" is required, design explicit coordination, verify protocol support, and handle `PartialLogout`/timeouts.

In the common model, you may store an **auth provenance reference** for auditing and session revocation, while **never storing raw ID Tokens, refresh tokens, or `SAMLResponse`** in client-facing DTOs.

## 20. Personal Data Controls and Logging

`OidcUser` and SAML principals/accessors may contain:

- NameID/`sub` and issuer.
- Email, name, department, groups, employee ID.
- ID Token/claims and UserInfo.
- SAML attributes or raw `SAMLResponse`.
- Session identifiers and authentication timestamps.
- Hints about tenants and roles.

**Data minimization rules:**
- Include in `CommonIdentity` only the fields business logic genuinely needs.
- Never return all of `getClaims()` or `getAttributes()` in `/me` APIs.
- Never log `getIdToken().getTokenValue()`, refresh tokens, `Saml2Authentication.getSaml2Response()`, or `Saml2ResponseAssertionAccessor.getResponseValue()`.
- Encrypt or hash/restrict audit-store access for subject IDs if required by your threat model while preserving stable keys for lookup.
- Separate **`displayName`** from the subject key, and contact email from authorization.
- Never let raw groups permit clients to construct authorities themselves.
- For investigations, log registration ID, protocol, outcome, trusted issuer ID/tenant, and a policy-compliant correlation hash rather than token payloads.

**Do not let `toString()` accidentally dump secrets**: logging an object holding raw claims or a JWT can leak PII. Build dedicated DTOs for APIs.

## 21. Unit Tests for Adapters and Account Linking

### 21.1. OIDC Data

| Test | Input | Expected Result |
|---|---|---|
| O1 | Authenticated `OidcUser` with valid issuer and `sub` | Snapshot has accurate OIDC issuer/`sub`/registration |
| O2 | `getIssuer` differs from `expectedIssuer` | **Reject** |
| O3 | `sub` is null/blank | **Reject** |
| O4 | `email_verified` absent/false | `emailProof` is not verified |
| O5 | `email_verified` true yet external key differs | **Never auto-link** by email alone |
| O6 | `UserInfo.sub` differs from `IDToken.sub` | OIDC validation rejects before adapter |
| O7 | Same `sub`, different issuer | Two distinct `ExternalIdentityKey`s |
| O8 | Pairwise `sub` varies by OIDC client | Never auto-merge; use explicit linking policy |
| O9 | Role claim is String instead of List | Reject/normalize per provider contract; never cast blindly |
| O10 | OIDC non-user Authentication or anonymous | Adapter rejects |

### 21.2. SAML Data

| Test | Input | Expected Result |
|---|---|---|
| S1 | 6.x `Saml2AuthenticatedPrincipal` NameID + attributes | Extracts right issuer from registration and NameID |
| S2 | 7.x `Saml2AssertionAuthentication` + accessor | Extracts right NameID/registration without casting legacy principal |
| S3 | Transient NameID for persistent account link | **Reject auto-link** |
| S4 | Null/blank NameID | **Reject** |
| S5 | Multi-valued SAML `groups` attribute | Preserves all values; validates each Object |
| S6 | Missing email attribute | Does not crash or fail user if email is optional |
| S7 | Email attribute has two values when contract requires one | Reject ambiguity or omit from contact |
| S8 | Signed Assertion with wrong issuer/audience | Spring SAML provider rejects before adapter |
| S9 | Unvalidated `Saml2AuthenticationToken` | Never mapped |
| S10 | Same NameID text, different IdP issuer | Two distinct external keys |
| S11 | Spring 7 custom principal | Assertion accessor still provides NameID/session details |
| S12 | Admin role from IdP without entitlement | Does not grant `ROLE_ADMIN` |

### 21.3. Account Mapping and Tenants

| Test | Scenario | Expected Result |
|---|---|---|
| A1 | Two external keys approved for linking by owner | Same `localUserId` |
| A2 | Two keys with same email, unapproved | Two separate identities; no merge |
| A3 | External key owned by user X; user Y attempts link | Reject conflict |
| A4 | Tenant disabled or account locked | No session granted with business privileges |
| A5 | Tenant A key accesses tenant B resource | 403/deny |
| A6 | Same group name from untrusted OP | Role not mapped |
| A7 | IdP cert/JWKS rotation | Accepts only new trusted keys; never bypasses signature |
| A8 | Concurrent link race | Unique constraint/transaction prevents dual ownership |
| A9 | User unlinks last sign-in method | Policy prevents accidental lockout |
| A10 | Email recycled after offboarding | Cannot take over old local account |

Unit tests simulate only the adapter. Real **integration tests** with an OIDC OP/test IdP and signed SAML fixtures are needed to verify signatures, issuer/audience/time, and correlation.

## 22. Integration Tests with Spring Security and a Broker

### 22.1. OIDC

1. Authorization Code Flow with valid state/nonce/redirect URI.
2. ID Token signed by trusted issuer and audience contains client ID.
3. `sub` and `iss` read from the verified ID Token.
4. UserInfo optional; when present, `sub` matches ID Token.
5. `ClientRegistration` from a different issuer is rejected.
6. `email_verified` acts only as a bounded proof signal, never overriding account-link approval.
7. Resource Server JWT (if the app exposes APIs) enforces **separate** issuer/audience checks for access tokens rather than accepting ID Tokens as API bearer tokens.

### 22.2. SAML

1. Response/Assertion signature validates against the RP registration's IdP verification cert.
2. `Issuer`, `AudienceRestriction`, `Recipient/Destination`, timestamps, and `InResponseTo` validate.
3. Assertion used to build the principal is the **exact signed node**, defeating XML Signature Wrapping.
4. Both 6.x and 7.x adapters are tested on their respective versions.
5. Multi-valued attributes/group mappings are never truncated to one value.
6. SAML NameID persistent format/qualifiers align with the account-binding contract.
7. IdP-initiated unsolicited responses follow their own policy without dropping SP-initiated correlation.
8. Lost sessions/clock skew/missing cookies fail SSO safely without accepting a Response for the wrong tenant.
9. SAML Single Logout retains NameID/SessionIndex and is not broken by custom principals.

### 22.3. Broker SAML → OIDC

1. Broker verifies upstream SAML and links the right upstream subject.
2. Broker issues a **new** ID Token with `iss` = broker and `sub` = broker subject.
3. Downstream Spring maps solely by broker issuer/`sub`.
4. Broker translates upstream groups into downstream claims via a tenant-scoped allowlist.
5. If upstream email changes, the downstream local account's subject key does not mutate arbitrarily.
6. If the broker fronts multiple upstream IdPs, identities sharing an email are never merged.
7. Upstream and downstream logout are tested separately, including timeouts, live sessions, and revocation policies.
8. Tenant-level provisioning, offboarding, and disabled accounts stay consistent across tiers.

## 23. Common Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| `ClassCastException` casting `OidcUser` to `Saml2AuthenticatedPrincipal` | Different principal types | Use an adapter with type checks and protocol branches |
| `ClassCastException` on `Saml2AuthenticatedPrincipal` after 7.x upgrade | Default principal changed | Use `Saml2AssertionAuthentication.getCredentials()` and accessor |
| OIDC login works yet account mapping fails | Using `getName()` instead of `(iss,sub)` or unmapped registration | Check post-validation OIDC subject/issuer and provider registry |
| SAML login works yet account mapping fails | NameID Format/issuer differs from DB key, or transient ID | Standardize persistent NameID contract and migrate safely |
| Same email creates two accounts | Two distinct external keys | Often expected; use approved linking workflow |
| Two users accidentally merged | Auto-linking by email | Stop auto-linking, audit provenance, and roll back mapping |
| UserInfo returns claims differing from ID Token | UserInfo `sub` mismatch or provider bug | Reject mismatch; inspect OP provider |
| OIDC `email_verified` is null | Claim omitted or unverified | Never default to true |
| SAML groups missing values | Calling `getFirstAttribute` instead of `getAttribute` | Read all values and validate types |
| OIDC groups is a JSON array yet cast to String | Different provider-specific schema | Write contract-aware converter with typed validation |
| SAML `mail` attribute absent | IdP uses a URI claim name | Align `AttributeStatement` mapping contract |
| `hasRole("ADMIN")` fails despite admin claim | Authentication authorities unmapped | Add issuer/tenant-scoped mapper; never trust raw claims |
| Login has `ROLE_USER` yet accesses tenant B | Resource authorization lacks tenant check | Enforce tenant scope in service/data layer |
| Broker uses SAML upstream yet app sees `OidcUser` | App receives OIDC downstream from broker | Expected architecture; map broker `iss/sub` |
| Broker issuer changed after migration | Downstream identity key mismatch | Perform admin-approved issuer/key migration |
| OIDC pairwise `sub` differs in a new client | Sector/client changed | Perform proof-based account linking, not email merging |
| SAML SLO fails with custom principal | Framework lost NameID/SessionIndex | Use assertion accessor or version-appropriate converter |
| Updated group/role not reflected in session | Authorities snapshotted at login; stale session/cache | Implement reauthentication, session revocation, or refresh policy |
| Logs leak raw ID Token or `SAMLResponse` | Logging `toString()` or raw claims | Mask/minimize logs, rotate exposed secrets, and audit |
| Mixed OIDC + SAML app login picker confuses tenants | EntryPoint/callback not scoped by registration | Trusted tenant picker, path/host allowlist, and issuer checks |

## 24. Code Review and Deployment Checklist

- [ ] Clearly distinguish OIDC vs. SAML, direct login vs. brokered login.
- [ ] Consume claims/attributes solely from a **validated Authentication** produced by Spring's provider.
- [ ] Keep **`iss+sub`** as the OIDC external key; never replace it with email or custom `getName()`.
- [ ] Keep **IdP issuer + NameID with Format/qualifier semantics** as the SAML external key; never use transient IDs for durable linking.
- [ ] Enforce per-IdP/OP tenant/registration scoping and provider policies.
- [ ] Enforce `AccountLink` uniqueness, approval, and auditing; never auto-merge by email.
- [ ] Treat OIDC `email_verified` accurately as nullable and non-authoritative.
- [ ] Handle SAML `AttributeStatement` as multi-valued `Map<String,List<Object>>`.
- [ ] Type-check OIDC claims and verify UserInfo `sub` matches ID Token `sub`.
- [ ] On Spring Security 6.x SAML, read `Saml2AuthenticatedPrincipal` using the proper API.
- [ ] On Spring Security 7.x SAML, use `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor` instead of hard-casting legacy principals.
- [ ] Never expose raw ID Tokens, access/refresh tokens, raw `SAMLResponse`, `SessionIndex`, or private keys in JSON/logs.
- [ ] Map groups/roles via provider+issuer+tenant allowlists; never trust raw upstream roles.
- [ ] Base Spring Authorization only on properly mapped `GrantedAuthority`/local permissions.
- [ ] Enforce tenant and data ownership checks in business resource authorization.
- [ ] Broker issues its own OIDC issuer/`sub`; treat upstream SAML issuer/NameID as contracted provenance only if downstream does not verify it directly.
- [ ] Manage OIDC/SAML logout and revocation lifecycles independently without assuming broker propagation.
- [ ] Test identity collisions, email recycling, pairwise `sub`, SAML transient NameID, and multi-tenant role mix-ups.
- [ ] Test OIDC JWT signature/issuer/audience/state/nonce and SAML signature/issuer/audience/recipient/time/replay against real IdPs.
- [ ] Verify Spring Security/Spring Boot/OpenSAML/OAuth2 client versions and 6.x→7.x migration behavior.

## 25. Review Questions

1. **Are `OidcUser` and `Saml2AuthenticatedPrincipal` the same type?** No, they represent two distinct protocols and claim APIs.
2. **What should the OIDC account key be?** The `(iss,sub)` pair from a verified ID Token, plus application tenant policy.
3. **Why shouldn't OIDC email serve as the user ID?** It lacks uniqueness/stability guarantees; OpenID Connect Core emphasizes that only issuer+subject provides that guarantee.
4. **Is `email_verified=true` sufficient to auto-link an existing local account?** No; it is only an email verification signal under OP trust and does not prove ownership of the local account.
5. **Is a SAML NameID always stable?** No; transient NameIDs are unsuitable for long-term linking.
6. **Why do NameID Format and qualifiers matter?** Identical NameID text can have different semantics and scopes.
7. **In Spring Security 6.x, where do you read SAML attributes?** `Saml2AuthenticatedPrincipal.getAttributes/getAttribute` after authentication.
8. **In Spring Security 7.x, where should you read SAML attributes?** `Saml2AssertionAuthentication.getCredentials().getAttributes()` via `Saml2ResponseAssertionAccessor`.
9. **What type does SAML `getAttribute("groups")` return?** A list of values; elements are not guaranteed to be Strings.
10. **Does OIDC `getClaims()` include UserInfo?** It can combine ID Token + UserInfo, though UserInfo may be null.
11. **Why does a SAML → OIDC broker return `OidcUser` downstream?** Because the broker mints a new OIDC ID Token and acts as the OP.
12. **Which issuer serves as the key downstream of a broker?** **The broker's OIDC issuer** if the app does not consume upstream SAML directly.
13. **Does a SAML group `report-readers` automatically mean `ROLE_REPORT_VIEW`?** No. It requires a tenant/provider allowlist and mapper.
14. **Why is a custom principal risky during SAML 7 migration?** Legacy principal casts can fail; use the assertion accessor and test SLO.
15. **Does the Java Spring 7 adapter snippet create `localUserId` automatically?** No. The snapshot is only source data; `AccountLinkRepository` and account status checks are still required.
16. **Can a browser-supplied `tenant` claim select permissions?** No; tenant must come from trusted registration/routing and authorization.
17. **What if `UserInfo.sub` differs from `IDToken.sub`?** Reject that UserInfo response per OIDC Core.
18. **If two users share an email across different issuers, what should the system do?** Keep the external identities separate; link only with proof/approval.
19. **Does local app logout terminate broker/IdP sessions?** Not by default; dedicated logout protocol/coordination is needed.
20. **What is the most important distinction?** Normalize the shape for business logic, yet **never erase issuer/subject/tenant provenance and trust boundaries**.

## 26. Official References

- **OpenID Connect Core 1.0**, especially §5.3.2 UserInfo subject matching, §5.7 Claim Stability & Uniqueness, §8 Pairwise Subject: https://openid.net/specs/openid-connect-core-1_0.html
- **Spring Security OidcUser JavaDoc** (getClaims, getIdToken, getUserInfo, getSubject/getIssuer): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- **Spring Security OIDC OAuth2 Login Core**, ClientRegistration and issuer-uri: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- **Spring Security OAuth2 Login Advanced**, GrantedAuthoritiesMapper/OidcUserService: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- **Spring Security SAML2 Login Overview**, signatures/principal: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security Authenticating SAML2 Responses**, custom converter/authority mapping: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Security SAML 2.0 Migration to 7**, Saml2ResponseAssertionAccessor & deprecated Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- **Spring Security Saml2AssertionAuthentication JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
- **Spring Security Saml2ResponseAssertionAccessor JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
- **OASIS SAML 2.0 Core**, NameID Format, qualifiers, assertion/conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OWASP SAML Security Cheat Sheet**, issuer/trust/XML signature/conditions: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- **Spring Security Authorization**, authorities vs. domain access: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

**Summary:** `OidcUser` and `Saml2AuthenticatedPrincipal` can be mapped into **one `CommonIdentity`** so business logic stays protocol-agnostic, without discarding authentication provenance. **OIDC uses `(iss,sub)`; SAML uses the trusted IdP issuer paired with NameID under a Format/qualifier/tenant contract.** Local accounts and permissions arise only through **explicit account linking/provisioning and authorization policies**, never merely because emails or group text match. With Spring Security 7.x, replace legacy SAML principal reads with `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor` to avoid version mismatches.
