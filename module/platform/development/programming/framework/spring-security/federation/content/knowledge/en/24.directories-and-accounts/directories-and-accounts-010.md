# Minimizing Shared Attributes and Limiting Personal Data Storage in Directories, Accounts, and Identity Links

> **Module:** Spring Security – federation. **Group:** Directories and Accounts. This document guides designing a federated login (federation) system that **collects, transmits, uses, and stores only the identity attributes genuinely required**. It applies to LDAP/Active Directory, SAML 2.0, OpenID Connect (OIDC), SCIM provisioning, and Spring Security applications. It focuses on attribute-release contracts between IdPs and Relying Parties, choosing low-disclosure identifiers, minimal authorization, personal-record lifecycles, logs/caches/backups, testing, and handling data when sources are no longer appropriate. All domains, users, and retention periods are illustrative; the pure Java 17 code at the end runs standalone.

## 1. The Problem: Login Needs Identification, Not Copying an HR Profile

An organization maintains a central HR directory. The IdP syncs from the directory and provides SSO login for multiple applications:

- **Internal portal:** only needs a stable identifier to establish a session, account status, and display name.
- **Reporting app:** only needs an identity and access to a set of reports; it does not need email, phone number, or home address.
- **Support app:** emails notifications to employees when they actively open a ticket, so only that workflow needs an approved email address.
- **External partner app:** only needs to know whether the user is eligible for the business action; it does not need birth date, `employeeId`, or the org chart.

A directory can hold dozens of attributes such as `cn`, `displayName`, `mail`, `telephoneNumber`, `homeAddress`, `dateOfBirth`, `manager`, `department`, `memberOf`, employee ID, cost center, salary band, and document verification data. **Being present in the directory does not mean every Relying Party should receive it.**

A "fetch the entire user object and serialize it into a JWT, SAML assertion, or session" configuration increases leakage risk, cross-system correlation, and retention/deletion burdens. There is no principle stating "because data is on the internal network, it can be shared with every service".

### 1.1. Learning objectives

After this lesson, you will:

1. Distinguish **identity attribute**, **authentication context**, **entitlement**, and **domain profile**.
2. Apply **purpose limitation, data minimization, and storage limitation** across data sources, federation protocols, applications, and stores.
3. Establish an **attribute release contract** per RP/client, tenant, purpose, and duration.
4. Understand what OIDC `openid`, `profile`, `email` scopes and the `claims` parameter affect, and avoid requesting overly broad data.
5. Choose `(iss, sub)`, pairwise subject identifiers, or an opaque stable ID instead of email as the account key.
6. Use SAML 2.0 `NameID` and `AttributeStatement` on an allowlist basis, avoiding sending full directory groups/permissions.
7. Restrict LDAP data via `SearchControls.setReturningAttributes` and SCIM data via `attributes`/schema `returned` policies.
8. Separate data needed **only in-session**, data **kept for operations**, and data serving **business records** under independent legal bases.
9. Handle provisioning, de-provisioning, subject deletion/correction, retention, backups, logs, analytics, and incident response.
10. Run a Java 17 demo covering pairwise pseudonymous IDs, per-RP allowlists, rejecting out-of-purpose attributes, TTLs, and unlinking.

## 2. Where Personal Data Sits in Federation

```text
Authoritative HR / Identity directory
  employeeId, preferredName, email, phone, address, groups, roles, status
             |
             | HR-to-IdP synchronization
             v
IdP / Identity Broker
  account + authentication + policy per RP
             |
             +-- OIDC ID Token/UserInfo (allowlisted claims)
             +-- SAML Assertion (allowlisted NameID/attributes)
             +-- SCIM provisioning (approved account attributes)
             v
Relying Party A: Portal       Relying Party B: Reports
  minimal account link          minimal account link
  local roles/session            local roles/session
             |
             v
Logs / metrics / caches / database / backups
             |
             v
Retention, de-provisioning, correction and deletion workflow
```

Each arrow represents **a separate data-sharing decision**. When an IdP emits a full employee profile inside a signed SAML Assertion or ID Token, that is still **data transmission** even if the RP reads only one attribute. Filtering DTOs after receipt **cannot undo a disclosure that already occurred**.

### 2.1. Roles: directory, IdP, RP, and user

| Component | Primary rights/responsibilities | Risks to prevent |
| --- | --- | --- |
| **Authoritative source** (HR/LDAP/AD) | Governs source truth, quality, and attribute classification | Over-populated directory, overly broad read permissions |
| **IdP / federation broker** | Authenticates users; releases subject/claims/attributes per RP | Default "release all" attribute policy, unisolated pairwise mappings |
| **RP — Relying Party** | Receives minimal identity; creates accounts/sessions and authorizes | Storing full assertions/profiles indefinitely, using email as identity key |
| **SCIM provisioning service** | Syncs lifecycle/authorized population | Provisioning every employee to every app, failing to deprovision |
| **Application domain storage** | Stores business records for approved purposes/durations | Using login attributes for unexpected secondary purposes |
| **Security/privacy owners** | Approve policies, threat/privacy assessments, and exceptions | Lack of ownership, unmeasurable retention/erasure |

This article covers **technical access and data-management design**, not legal assessments for specific jurisdictions. Consent is not always the appropriate legal basis; determine processing basis, purpose, notice rights, and retention limits under applicable regulations.

## 3. Three Distinct Principles: Purpose, Minimization, and Storage Limitation

### 3.1. Purpose limitation — defined purpose

Before an IdP/RP collects or transmits an attribute, ask:

- Which feature or decision **cannot function** without this attribute?
- Who processes this attribute, for how long, and under what notice/trust agreement?
- Is there a less-disclosing **derived value** alternative?
- What happens when the feature is retired, the user changes roles, the app shuts down, or the contract ends?
- Will it be reused for analytics, marketing, or cross-app tracking? If so, that requires an **independent purpose/basis and policy**, never inferred merely from login.

**Example:** a system only needs to know whether someone is at least 18 years old. If the IdP already verified age and policy permits, pass **`over18=true/false`** instead of a full birth date. That is a more minimal attribute, though not valid proof of age across all laws/contexts; assurance must still fit the requirement.

### 3.2. Data minimization — only needed data

For the same person, different RPs have different needs:

| Use case | Minimal attributes typically sufficient | Usually unnecessary |
| --- | --- | --- |
| Internal login | `iss`, `sub`; local account ID, allowed status | Address, birth date, phone, global employee number |
| Display greeting | Preferred/display name if actually shown | Legal name, middle name, gender, birth date |
| Report authorization | RP-specific permission/role, or policy decision | Full `memberOf`, manager chain, HR record |
| Send request receipt | Verified email if required and approved for the purpose | Phone number, home address, personal emails |
| Eligibility check | Boolean/claim of eligibility with issuer and assurance | Birth date/identity documents/raw evaluation data |
| Aggregate metrics dashboard | Aggregated counts at appropriate anonymity level | Unnecessary individual user lists |

**Not every table shares the same rules:** "must have email" may hold for a messaging app, yet not for an RP that only authenticates login. An attribute that is "handy for debugging" is rarely sufficient justification for default release.

### 3.3. Storage limitation — do not retain longer than necessary

Answer both **where it is stored** and **when it is deleted**:

1. Data used solely to decide login or roles at authentication: keep **in-request/short-lived session** or do not persist to DB.
2. Opaque account link `(issuer, subject)`: may persist while the RP account is active; delete/unlink upon deprovisioning per policy.
3. Email used for sending receipts: if the app needs an approved contact log, give it a dedicated retention limit; if single-use, **read on demand and do not keep a long-term copy**.
4. Security audits: keep **event code/timestamp/service/opaque correlation ID** instead of full claims, with independent retention.
5. Transaction/financial records: if legally required to retain, separate from the federated login profile with dedicated access/retention controls.
6. Backups/replicas: require deletion propagation, bounded retention, and restore rules that prevent resurrecting deleted profiles.

**Do not pick one blanket TTL** for sessions, account links, legal documents, audit logs, and analytics. Maintain a **per-data-type, per-purpose retention schedule** approved by privacy/security/legal owners.

## 4. Classifying Attributes Before Releasing to an RP

A **data inventory** should record: source field name, meaning, sensitivity, authoritative owner, intended purpose, recipients, release conditions, update mechanism, retention, and deprovisioning action.

| Source attribute | Example | Risk | Release decision |
| --- | --- | --- | --- |
| `directoryObjectId` | internal ID | Enables cross-RP linking | Do not send globally; use pairwise/opaque RP IDs |
| `uid` / `employeeNumber` | user/HR number | Easy correlation/re-identification | Avoid when only a subject is needed |
| `mail` | corporate email | Direct identifier, mutable | Only when communication is required; never as primary login key |
| `displayName` | display name | Personal data | Only for UIs that genuinely display it |
| `givenName`, `sn` | first/last name | Often not both needed | Use display name if sufficient |
| `telephoneNumber` | phone number | Context-sensitive | Do not release by default in every token |
| `homePostalAddress` | address | Sensitive, high risk | Never release on routine logins |
| `birthDate` | date of birth | Potentially sensitive | Convert to derived eligibility if appropriate |
| `memberOf` / groups | hundreds of group DNs | Exposes org chart, excessive privilege | Translate to minimal RP-specific roles/entitlements |
| `manager` / department | org structure | Enables internal inference/cross-linking | Release only when a feature requires it |
| `accountEnabled` / `active` | true/false | Critical status | Use for login authorization when needed |
| `salary` / health / IDs | financial/health/gov IDs | High risk | Never share without dedicated purpose and controls |
| Password hashes/private keys | secrets | Extremely sensitive | **Never put into federation assertions/claims** |

**Multi-valued attributes** like `memberOf`, `emails`, and `roles` frequently leak far more than intended. If a group list contains 200 project and department names, compute a specific permission like `canViewReport=true` or an RP-specific role instead of shipping the whole list.

### 4.1. Classification labels are only a starting point

Do not rely merely on "email = low sensitivity" or "department = non-sensitive". Risk shifts with recipient, combined datasets, processing location, and applicable law. Even an opaque subject remains personally relatable data if the system retains a reverse mapping table. **Pseudonymization is not automatically anonymization.**

### 4.2. Attribute derivation beats raw data transmission

```text
Directory:
  birthDate = 1995-xx-xx
        |
        v
IdP/verified attribute processor
  policy: isEligibleForService = true
        |
        v
RP:
  sees only eligible=true, issuer, subject, assurance context
  cannot recover birthDate from the assertion
```

The application must require appropriate assurance (verifying the result's source, expiry, and user consent/legal basis), never accepting a browser-submitted boolean.

## 5. Per-RP Attribute Release Contracts

An **attribute release policy** should never just be "OIDC/SAML enabled". It must specify exact RP, tenant, protocol, audience, purpose, claims, and retention.

Design contract example (**not default Spring Security YAML**):

```yaml
identity_attribute_release:
  portal:
    issuer: "https://idp.example.org"
    audience: "portal-client"
    purpose: "authentication_and_greeting"
    identifier: "pairwise_subject"
    allowed_claims:
      - "sub"
      - "active"
      - "display_name"
    denied_claims:
      - "birth_date"
      - "home_address"
      - "salary"
      - "phone"
    retention:
      session_claims: "until_session_end"
      account_link: "until_unlink_with_approved_retention"

  reports:
    issuer: "https://idp.example.org"
    audience: "reports-client"
    purpose: "report_authorization"
    identifier: "different_pairwise_subject"
    allowed_claims:
      - "sub"
      - "report_entitlement"
    retention:
      authorization_cache: "short_ttl_with_revocation"

  support:
    issuer: "https://idp.example.org"
    audience: "support-client"
    purpose: "requested_email_notification"
    allowed_claims:
      - "sub"
      - "verified_email_when_needed"
    retention:
      notification_delivery_record: "approved_short_period"
```

These values describe policy; the application needs real enforcement code/configuration. **Deny-by-default**: when a new RP is registered, it receives no group lists, phone numbers, or HR attributes by default. Releasing email requires an approved purpose, not "it's convenient for debugging".

### 5.1. Fields to approve in a contract

1. **RP identity:** `client_id`/OIDC audience or SAML `entityID`; prevents attackers from impersonating a higher-privilege RP.
2. **Tenant and issuer:** never mix directories across organizations.
3. **Purpose code:** allows administrators to audit and control usage.
4. **Allowed attributes:** canonical names + aliases + transformations.
5. **Mandatory vs. optional:** missing optional fields must not trigger pulling all attributes; missing mandatory fields must fail safely.
6. **Consent/lawful basis/notice:** reviewed by privacy/legal.
7. **Subject strategy:** pairwise, persistent, or transient ID per business need.
8. **Session/retention:** where data lives after login.
9. **Downstream sharing:** may the RP forward claims to APIs/analytics?
10. **Revocation/correction/deletion:** when to update, disable, unlink, or purge.
11. **Monitoring/exceptions:** who approves and who monitors policy drift.
12. **Versioning:** contract edits are security/privacy changes; never deploy silently.

### 5.2. Sending only "what was requested" is not enough if requests are too broad

Per NIST SP 800-63C-4, an RP should request only minimal information, and the IdP should transmit only information matching the trust agreement/request. Yet an RP can be misconfigured to request `profile email phone address`. Thus **both sides must enforce controls**: the RP requests minimally, the IdP enforces an attribute allowlist, and the RP limits local persistence.

### 5.3. When multiple RPs share an owner

Being in the same enterprise **does not automatically grant correlation rights** across RPs. If business genuinely requires a shared identifier, design a contracted sector/shared PPI with a privacy risk assessment—never broadcast a global employee ID to every service just because they share AD.

## 6. Choosing Identifiers: Email Is Not a Durable Account Key

### 6.1. Safe linking key at the RP

With OIDC, user account linking should rely on the **`(iss, sub)` pair**:

```text
(issuer, subject) =
("https://idp.example.org", "opaque-sub-for-portal")
```

`sub` **only has meaning within the issuer's scope**. Two IdPs may emit identical subject strings representing two different people. The RP should store issuer/provider registration and subject in the account link; never use email as the primary key since emails change, get recycled, may be unverified, or may be shared.

With SAML 2.0, `NameID`, qualifier/format, and IdP `entityID` serve an analogous role; know the actual `NameID` format in use and verify against the right asserting party. Never assume `NameID` equals email or is persistent across all IdPs.

### 6.2. Public vs. pairwise subject identifiers

OIDC Core defines:

- **`public` subject:** same `sub` for a user across clients receiving public subjects, enabling correlation.
- **`pairwise` subject:** provider emits different `sub` values per **sector identifier** to limit cross-RP correlation.

NIST SP 800-63C-4 likewise recommends/specifies **pairwise pseudonymous identifiers** by Federation Assurance Level and trust context. Pairwise IDs must be unguessable and contain no plaintext username/email/employee number; they can be produced via keyed derivation or random mapping at the IdP.

```text
IdP user internal ID: employee-0042

Portal RP    sees sub = ppi-portal-8d...
Reports RP   sees sub = ppi-reports-2a...
Support RP   sees sub = ppi-support-f3...

All three represent one person at IdP,
but independent RPs cannot directly link by sub alone.
```

**Note:** pairwise `sub` does not prevent correlation if the IdP simultaneously sends the **same email, name, and phone number** to all three RPs. Minimize accompanying attributes. Pairwise IDs remain **pseudonymous personal data** in many privacy contexts—do not claim they are anonymous.

### 6.3. Designing PPIs without guessable hashes

Wrong:

```text
sub = SHA256(email)
```

Emails have low entropy/predictability, attackers can run dictionary lookups, and the same hash is emitted across RPs. Better is an **IdP-only keyed HMAC with a secure secret**, scoped by sector/RP, issuer, and immutable internal ID, or a controlled random opaque mapping. Key rotation/sector migration must preserve account-linking or use a reliable migration flow so users do not lose accounts or get mis-linked.

### 6.4. When intentional correlation is required

Some business domains need the same identity across Portal and Reports. Options include:

- An **authorization broker** translating subjects across scopes with auditing and purpose checks.
- A shared sector group when aligned with OIDC subject rules and trust agreements.
- User-initiated consented/verified account linking.

Never expose a `globalEmployeeId → all RP subjects` mapping table to RPs that do not need it. That mapping table is **personal data and a high-value correlation asset**.

## 7. OIDC: Request Few Claims Up Front

### 7.1. Scope `openid` does not mean "ask for the entire profile"

OIDC Core 1.0 specifies `openid` to request OIDC authentication. Additional scopes mean:

| Scope | Claims that may be requested | Notes |
| --- | --- | --- |
| `openid` | OIDC authentication with `sub` and core protocol claims in ID Token | Does not imply needing email/phone/address |
| `profile` | Bundle of profile claims like `name`, `nickname`, `picture`, **gender, birthdate**, `locale`, etc. | **Broader than many realize**; do not request just for `displayName` if a narrower option exists |
| `email` | `email`, `email_verified` | Only if the app genuinely sends emails or verifies ownership |
| `phone` | `phone_number`, `phone_number_verified` | Never default for sign-in |
| `address` | `address` | Distinct risk; rarely needed for basic SSO |

In OIDC, scopes are **requests**, not guarantees that every provider returns every claim. `email_verified=true` carries the OP's verification semantics, but does not turn email into an immutable unique subject. The `claims` request parameter can ask for individual claims, though support is **optional** per OP metadata; the RP must handle missing optional claims.

### 7.2. Minimal Spring OAuth2 Client scope configuration

Example Spring Boot config fragment for a login-only client:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: portal-client
            scope:
              - openid
        provider:
          corporate:
            issuer-uri: https://idp.example.org
```

This is only a **fragment**: client authentication secret/config, TLS, redirect URIs, provider metadata, and session controls are still needed. Crucially, **do not blindly add `profile`/`email`/`phone`/`address`**. For a UI that genuinely needs a display name, coordinate with the IdP for a **dedicated release policy** rather than enabling broad `profile` and storing the entire ID Token.

An OP might still emit certain claims beyond requested scopes due to other policies; the RP must also control storage/logging. However, **filtering only at the RP cannot undo a disclosure already sent**, so blocking at the IdP is the primary layer.

### 7.3. Requesting individual claims with `claims` when supported by the OP

Example OIDC request parameter (only the `claims` JSON portion, not a complete authorization URL):

```json
{
  "userinfo": {
    "preferred_username": null
  }
}
```

An app needing only a greeting can request one specific claim instead of all of `profile` if the OP advertises `claims_parameter_supported`. Still, `preferred_username` can identify a user; prefer an RP-specific `display_name` or derived greeting where possible, and never turn username into a globally shared key.

**Do not stuff all PII into the ID Token:** the ID Token is received directly by the RP/client and may traverse the browser/backchannel depending on flow. Use UserInfo over TLS with a protected Access Token and release policy, remembering **UserInfo is also personal data**—never return "all" just because it is a separate endpoint.

### 7.4. Token validation is mandatory; minimization never replaces security

The RP must still validate issuer, audience, signature/JWK, expiration, and nonce/state/PKCE per flow and requirements; only validated `sub` may serve as the subject. Never accept a browser-provided `sub` or raw UserInfo from an unverified endpoint. NIST minimization never permits dropping integrity or authentication controls.

## 8. Spring Security OIDC: Map the Minimum Attributes Necessary

Spring Security provides `OidcUser`, `OidcUserService`, `OAuth2UserService`, and `GrantedAuthoritiesMapper`. Just because `OidcUser.getClaims()` returns a map does not mean the application should copy it into a `users` table, session, audit log, or DTO.

### 8.1. Use issuer + subject as the account link

Example Java fragment in a Spring Security app configured for OIDC:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Fragment: this OidcUser has already been authenticated by Spring Security.
public record FederatedAccountRef(String issuer, String subject) {}

public FederatedAccountRef accountRef(OidcUser user) {
    var token = user.getIdToken();
    return new FederatedAccountRef(
        token.getIssuer().toString(),
        token.getSubject()
    );
}
```

Never use `user.getEmail()` as primary key and never persist the full `user.getClaims()`. In multi-tenant apps, add the trusted tenant/registration ID to the link key if your architecture requires it.

### 8.2. Domain-specific processing diagram

```text
OidcUser (validated; may contain many claims)
   |
   +-- (iss, sub) -> AccountLink
   +-- approved entitlement -> local RoleMapping
   +-- optional display_name -> View DTO / short session
   |
   X-- DO NOT serialize the entire OidcUser/ID Token into DB
   X-- DO NOT log claims/JWT
   X-- DO NOT return tokens/PII to frontend unnecessarily
```

**Technical note:** A custom mapper only shrinks **domain entities/DTOs**; it does not remove claims the IdP already placed in the signed ID Token, and Spring Security's security context may still retain `OidcUser` in-session. Reducing data at the source requires an IdP attribute release policy; reducing data at the RP requires controlling how `SecurityContext`/sessions are stored and serialized per framework/version. Never tamper with a signed ID Token as arbitrary JSON.

### 8.3. Permissions are not every group

Spring provides `GrantedAuthoritiesMapper` and delegating `OAuth2UserService` to map OIDC claims/groups to authorities. Yet a raw `groups` claim may carry hundreds of DNs. Fetch an **RP-specific entitlement** from the IdP/authorization service, or map server-side to ``ROLE_REPORT_VIEWER``; never copy the raw group map into user profiles or browser-facing sessions.

Every "group -> ADMIN" rule must be bound to a trusted issuer, exact tenant/audience, and role policy; **never trust browser JSON claims**. Fail closed if required permissions are missing or stale.

## 9. SAML 2.0: Minimal NameID and AttributeStatement

### 9.1. Sharing boundary of a SAML Assertion

A SAML IdP sends a `Response/Assertion` containing `Subject/NameID`, authentication context, and optionally `AttributeStatement`:

```xml
<saml:AttributeStatement
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="active">
    <saml:AttributeValue>true</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="appRole">
    <saml:AttributeValue>REPORT_VIEWER</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
```

This XML snippet illustrates only two attributes; production still requires issuer, audience restriction, Recipient, signature validation, and protocol metadata. **A signed/encrypted assertion can still over-share PII.** Encryption protects transport/confidentiality, not data minimization at the RP.

### 9.2. Attribute release policy at the IdP

The IdP should configure per-SP/RP `entityID`:

- SP Portal receives only an opaque/persistent or transient `NameID` as needed, plus display name if approved.
- SP Reports receives an app-specific role/entitlement instead of all groups.
- Do not release `mail`/`telephoneNumber`/`employeeNumber`/`homeAddress` by default to every SP.
- For partner SPs, use scoped/pairwise `NameID`s and derived attributes where appropriate.
- SP A must never request extra PII on behalf of SP B by modifying `AttributeConsumingService` outside IdP policy.
- Attribute names and `NameFormat`/URIs should be fixed and versioned to avoid collisions or misread aliases.

If the IdP sends all groups in the assertion, even if Spring reads only the first element, the data has already been transmitted to the RP. **Minimize at the issuer first**, then filter DTOs and limit retention at the receiver.

### 9.3. Spring Security reading SAML2 attributes

After successful SAML Response validation, Spring's principal may be `Saml2AuthenticatedPrincipal`. Example:

```java
import org.springframework.security.saml2.provider.service.authentication
    .Saml2AuthenticatedPrincipal;

// Fragment in a Spring MVC application with saml2Login enabled.
public String labelFor(Saml2AuthenticatedPrincipal principal) {
    String displayName = principal.getFirstAttribute("displayName");
    return displayName != null ? displayName : "Signed in";
}
```

SAML permits **multi-valued attributes**. `getFirstAttribute` retrieves only the first value; never use it on a multi-valued `groups` claim to infer permissions. And an app displaying only a name does not stop the IdP from sending extra info. Configure attribute release at the IdP—never use controller code as your sole privacy control.

### 9.4. SAML NameID should not be email when unnecessary

A persistent opaque `NameID` preserves the account link even when email changes. Transient `NameID`s fit short sessions needing no persistent account, but cannot act as stable account links if values change continuously. Choose the `NameID` format per purpose and trust agreement, verifying IdP behavior and migrations.

## 10. LDAP/AD: Read Only Necessary Attributes

Risk often begins **before** an OIDC/SAML assertion is created: the IdP or application queries LDAP with a default "get all user attributes" and accidentally logs, caches, or re-emits every field.

### 10.1. LDAP RFC 4511: explicit projection

LDAP `SearchRequest.attributes` defines what the server returns:

- An **empty** list or `*` may request **all user attributes**.
- Passing only `1.1` means **no attributes requested** (used when only checking entry existence).
- A specific list like `uid`, `accountStatus`, or `entryUUID` requests only those attributes.
- Server-side LDAP ACLs can restrict further.
- Operational attributes often must be named explicitly; attribute names/fields differ between OpenLDAP and AD.

Per RFC 4511, **an empty projection list does not mean "return nothing"**. This is a common mistake when developers invoke search APIs without specifying `returningAttributes`.

### 10.2. JNDI SearchControls selecting attributes

Java fragment using JNDI, assuming a `DirContext ctx` already protected with LDAPS/StartTLS and a read-only bind account:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

// Fragment: ctx must be built with TLS, a truststore, and narrow read permissions.
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
        new String[] {"entryUUID", "accountStatus"});
controls.setCountLimit(1);
controls.setTimeLimit(2000);

// JNDI filter arguments avoid concatenating input into the LDAP filter.
NamingEnumeration<SearchResult> results = ctx.search(
        "ou=people,dc=example,dc=org",
        "(uid={0})",
        new Object[] {uid},
        controls);
```

`entryUUID`/`accountStatus` are **schema examples** only; AD may use `objectGUID`, `userAccountControl`, and different active-account calculations. Never read all AD attributes "because we're unsure of the schema" in production; inventory and request exact fields.

### 10.3. Safe filters and directory permissions

- Prevent LDAP injection: use JNDI filter arguments or schema-appropriate escaping.
- Use a search/bind account with **read-only permissions** restricted to required OUs/attributes; if directory ACLs lack fine-grained field control, place a directory broker in front.
- Use LDAPS or StartTLS with certificate validation, never plain LDAP over untrusted links.
- Never keep connection/debug logs containing user passwords, bind DN secrets, or full `SearchResult` dumps.
- Restrict subtree, size/time limits, and pagination as needed; never cron-scan the entire directory and copy HR profiles.
- For group memberships, query permissions **within app scope**; never dump all of `memberOf` into sessions/JWTs.

### 10.4. Distinguish login lookup from directory synchronization

A login check needing `active` + subject may require only 1–2 attributes. A provisioning connector might need email/department for an approved workflow; that is a **separate pipeline and contract**. Never use provisioning needs as an excuse to bloat every OIDC ID Token.

## 11. SCIM: Limiting Provisioning and Response Fields

SCIM (RFC 7643/7644) is an account/provisioning lifecycle protocol, distinct from SSO login. A SCIM client can create/update/disable users at an RP before they ever log in, carrying higher risk of **long-term personal data storage** than transient login claims.

### 11.1. Partial resource representations

RFC 7644 defines query parameters:

- `attributes=userName,active`: requests specific fields (in addition to schema fields marked `returned=always`).
- `excludedAttributes=...`: omits certain fields from the default representation.
- Never send both `attributes` and `excludedAttributes` in the same request.
- Servers enforce schema `returned` policies; attributes like SCIM `id` have `returned=always` and are still included.
- Subtracting via `excludedAttributes` easily misses newly added schema fields; **an `attributes` allowlist** is usually safer to control.

Illustrative SCIM query:

```http
GET /scim/v2/Users/opaque-account-id?attributes=id,active HTTP/1.1
Host: directory-api.example.org
Authorization: Bearer REDACTED_ACCESS_TOKEN
Accept: application/scim+json
```

For an app that only needs to know if an account is active, do not request `emails`, `phoneNumbers`, `addresses`, `manager`, or the full enterprise extension. SCIM responses also depend on server schema and contract; never treat query projection as a substitute for read authorization controls.

### 11.2. SCIM `returned` and `mutability`

RFC 7643 describes schema metadata:

| `returned` | Meaning |
| --- | --- |
| `always` | Returned regardless of request projection, e.g., resource ID |
| `default` | Returned by default unless the request selects a subset |
| `request` | Returned only in specified request contexts |
| `never` | Never returned in responses |

`mutability=writeOnly` typically pairs with `returned=never` for write-only secrets that must not be read back. Never expose passwords/tokens as default SCIM attributes just because a server supports extensions.

### 11.3. De-provisioning differs from mandatory audit retention

When a user leaves the organization or is no longer permitted to use an RP:

1. The IdP/provisioning service sends deactivate, delete, or unlink per contract.
2. The RP immediately revokes access and active sessions/tokens per policy.
3. Delete or strip synced profile fields that are no longer needed.
4. If business records must be kept under legal obligations, store them in a **restricted domain record** with dedicated retention, disallowing login or secondary email use.
5. Delete/audit subject mappings per policy and handle backups.

NIST SP 800-63C-4 emphasizes limiting **subscriber accounts provisioned to an RP** and deprovisioning terminated accounts, subject to retention requirements/policy/regulations. Never provision all 100,000 employees into an RP that only has 100 authorized users.

## 12. Authorization: Reducing Group/Role Data Safely

### 12.1. "Give all groups" is not what the RP needs

An IdP might see `memberOf` containing:

```text
CN=Project-Secret-A
CN=Project-Secret-B
CN=Finance-Staff
CN=HR-Benefits
CN=VPN-Admins
...
```

The Reports RP only needs to know `REPORT_VIEW`. Sending all 200 groups leaks org structure and invites mistaken privilege mappings. One solution:

```text
IdP/Authorization Broker
  directory groups / HR roles
             |
             v
Policy: can user view Reports?
             |
             v
RP-specific claim: reportAccess=VIEW
             |
             v
Reports app uses allowlisted authorization mapping
```

**Security caveat:** Roles/entitlements must come from trusted sources and update when groups change. Reducing attributes does not mean the RP can trust an arbitrary client-sent boolean. Still verify `iss`, `aud`, signature, expiry, tenant, and freshness.

### 12.2. Recompute when needed instead of caching forever

Frequently changing entitlements may need a policy decision service or short-TTL cache; if an RP holds `isAdmin=true` in a 30-day session, a revoked user keeps access. Design `authorization_ttl`, invalidate on deprovisioning/role changes, and re-evaluate sensitive operations. That addresses **freshness and revocation**, not an excuse to store the full directory group list.

### 12.3. Separate Authentication and Authorization

`Authenticated` means the IdP verified the user; `Authorized` means the app permits a specific action. A valid `sub` does not automatically grant `ADMIN`. Minimal identity claims can combine with local resource-based policies to avoid releasing excessive attributes.

## 13. Post-Receipt Minimization: Requests, Sessions, DB, and APIs

### 13.1. Avoid "copy all claims" into entities

Anti-pattern:

```java
// WRONG: persisting every claim of the OIDC principal into the database.
// userEntity.setProfileJson(serialize(oidcUser.getClaims()));
// logging.info("claims={}", oidcUser.getClaims());
```

Risk: birth dates, addresses, and groups persist long-term, becoming searchable, replicated, and backed up; when the IdP tightens its release policy, stale copies stay in the DB.

Better approach:

```text
AccountLink {
  rpAccountId          (random internal ID)
  trustedIssuerId
  scopedSubject        (RP-specific)
  status
  createdAt/lastLoginAt
}

Optional UserPreference {
  rpAccountId
  displayName         (only if needed by UI)
  updatedAt/retentionPolicyId
}

RoleAssignment {
  rpAccountId
  appRole
  expiresAt / policyVersion
}
```

If display name does not need to persist across sessions, store only the account link and look up a short-lived display name from an approved source at render time. **Never use account email as the foreign key across all business tables**, because email changes break identity links.

### 13.2. Sessions may hold more data than you think

Spring Security may keep `OidcUser`/`Saml2Authentication` in `SecurityContext`. If the framework serializes the entire principal into Spring Session Redis, full claims end up in the **session store**, even when JPA entities are minimal.

Check:

- Which claims are inside the serialized principal?
- Where are tokens/ID Tokens/`Authentication` stored, and with what TTL?
- Are Java session persistence/Redis backups encrypted and ACL-protected?
- Does session invalidation/logout actually delete the data?
- Is a custom principal created after **trusted authentication** with required context/authorities without breaking Spring semantics?
- Do diagnostics, heap dumps, or exceptions retain raw claims?

**Never edit `DefaultOidcUser` to strip claims from a signed ID Token**; signed ID Tokens must be verified intact. Prefer configuring the IdP not to emit unnecessary PII, and limit authorization/domain projections and retention at the RP.

### 13.3. Downstream APIs must not receive the raw principal

A backend that only needs `userId` and `canSubmit=true` should not be forwarded an entire `OidcUser`, SAML Assertion XML, or an access token carrying broad scopes/claims. Design **audience-restricted downstream tokens** or service-side authorization decisions to reduce propagation and accidental logging. Never dump the principal map straight into frontend JSON responses.

## 14. Lifecycle Data Retention Policies

Illustrative retention matrix (figures are for discussion only, **not legal mandates or default settings**):

| Data category | Where stored | Deletion/refresh trigger | Notes |
| --- | --- | --- | --- |
| OIDC/SAML raw authentication response | In memory during validation, framework session if needed | Per protocol/session lifecycle; avoid DB persistence | Never log raw tokens/assertions |
| Display name for rendering | Request/short session | Logout/TTL | Can be re-fetched when needed |
| `(iss, sub)` account link | RP account table | Unlink/deprovision/account termination | Protect linkage/pseudonymous data |
| RP-specific entitlement | Session/short authorization cache | TTL or revocation event | Fail closed when stale |
| Email for notifications | On-demand or minimal business record | Per delivery purpose/approved retention | Do not copy into analytics |
| Transaction data with retention obligation | Domain database separate from identity | Per legal/business retention schedule | Do not delete against obligations; restrict |
| Security audit | Audit store | Retention per policy/legitimate need | Opaque event IDs, no raw claims |
| Search/analytics index | Derived/minimized dataset | Reindex/purge synced with source deletion | De-identification is not automatically anonymous |
| Backups | Encrypted backup vault | Rotation/expiry + restore controls | Prevent "data resurrection" after restore |

### 14.1. TTL ≠ true deletion everywhere

Setting Redis `EX 3600` only expires the cache key in Redis; it does not erase audits, log streams, replicas, DB backups, dead-letter queues, trace captures, CSV exports, or browser storage.

To bound retention, maintain a **data lineage inventory** where every storage sink has a **deletion/retention policy**. When law mandates retaining part of a record, **segregate the retained record** and block secondary reuse.

### 14.2. Updates/corrections

When display name/email changes in the directory:

- The RP must never rely on a stale cached email as an identity key.
- If updates are needed, consume events/SCIM PATCH or re-fetch from the approved source.
- The stable subject mapping does not change just because email changed.
- When a user requests correction/deletion, propagate across relevant RP copies.
- Audit correction actions **without retaining unnecessary old values**.

### 14.3. Disabled, deprovisioned, and terminated accounts

- `Disabled`: block login/access; certain permitted records may stay.
- `Deprovisioned`: RP is no longer tied to the identity/provisioning population; remove access/links per trust agreement.
- `Terminated`: account closed/deleted per policy; handle remaining records and retention constraints.
- `Legal hold`: keep only genuinely required data with restricted access—never keep a full HR profile out of convenience.

Do not collapse all these states into a single `deleted` flag without defining impacts on sessions/tokens and data retention.

## 15. Logs, Metrics, APM, and Support Can Be the Biggest Leak Vector

Per the OWASP Logging Cheat Sheet, never log access tokens, session IDs, passwords, secrets, sensitive personal information, or data exceeding the logging system's classification.

### 15.1. Never log tokens or user objects

Wrong:

```text
DEBUG OIDC response = <all ID Token claims>
INFO newUser: email + phone + homeAddress + birthDate
TRACE LDAP SearchResult: <all attributes>
AUDIT authentication: raw SAML Assertion XML
METRIC login_total{email="user@example.org"}
```

Better:

```json
{
  "event": "federation_login_success",
  "rp": "reports",
  "idp": "corporate",
  "policy_version": "attr-release-v3",
  "disclosure_fields": ["sub", "report_entitlement"],
  "correlation_id": "request-opaque-id",
  "result": "success"
}
```

This is **illustrative** telemetry JSON: never log raw `sub`, `NameID`, email, LDAP DN, employee ID, groups, tokens, or full requests. `disclosure_fields` lists approved **field names**, not values. Each organization must evaluate whether IDs and field names themselves reveal sensitive information.

### 15.2. Layers requiring redaction

- Spring MVC/GraphQL request logs and security events.
- OAuth2 callback logs containing `code`, `id_token`, or `access_token`.
- Reverse proxy/Ingress `request_uri` and response bodies if traced.
- LDAP client debug logs, SAML XML/Assertions, OIDC UserInfo bodies.
- Redis/DB query logs and ORM `toString()`.
- Message bus payloads, dead-letter queues, and support exports.
- APM/distributed tracing, crash dumps, and heap dumps.
- Client-side browser analytics, HTTP response payloads, and local/session storage.
- KMS secret metadata and correlation tables.

**Hashing alone is not always enough:** unsalted hashes of emails are vulnerable to dictionary attacks. If logs must be correlated over a limited window, use **rotating keyed pseudonymous event identifiers** with bounded TTLs and assess correlation risk. Never send pairwise `sub` values to analytics as "fully anonymous".

## 16. Trust, Security, Individual Rights, and Lawful Basis

### 16.1. Identity minimization does not replace authentication verification

OIDC ID Tokens must still verify signature/issuer/audience/expiry/nonce; SAML Assertions must still verify trusted signing cert, issuer, audience/recipient/`InResponseTo`/replay/time. LDAP requires TLS, bind ACLs, and safe filters. **Never drop core verification fields** just to shrink claim counts; protocol security fields are not optional profile PII.

### 16.2. Derived attributes require a trustworthy source

If an app receives `eligible=true` instead of birth date, you must trust that the IdP computed eligibility accurately under the required assurance level. Never let the browser or an untrusted RP supply this flag. Likewise, `role=viewer` must come from a trusted authorization policy, not a username claim.

### 16.3. Individual rights and exceptions

A practical privacy governance program needs:

1. **Notice/transparency:** document which apps receive which data and why.
2. **Access/correction:** how to query, fix source attributes, and propagate updates.
3. **Erasure/deprovisioning:** remove account links, attributes, and caches when no longer needed.
4. **Consent/withdrawal where applicable:** revoke attribute release and handle downstream retention accordingly.
5. **Retention exceptions:** statutory records, security audits, and legal holds with owners, expiries, and access controls.
6. **Breach incident response:** identify which IdP/RPs received which fields, contain leaks, and notify as required.
7. **Third-party processors:** contracts, transfer/boundary controls, retention, and access protections.
8. **Periodic reviews:** attribute release policies, group-claim sprawl, unused fields, and deprovisioning errors.

Do not assume "encryption is enabled" satisfies **data minimization**. Encryption restricts unauthorized readers; it does not stop an RP from receiving excessive data.

## 17. Standalone Java 17: Release Allowlist, Pairwise ID, and TTL

This program needs no Spring, IdP, LDAP, or database. It illustrates:

- A **source directory** containing many attributes.
- **Each RP** having its own allowlist; an email request from Reports RP is rejected.
- The IdP issuing **distinct pseudonymous subjects per RP**, computed via a mock HMAC key.
- Never releasing `phone`/`birthDate` to Portal/Reports.
- An illustrative store keeping **only email** for Support RP for a bounded TTL, never storing the full claim map.
- Records past TTL becoming inaccessible and purged.
- Another RP unable to read Support's record; unlinking removes the copy.

**Important limitations:** this is a Java-level policy model—it does not mint or verify OIDC ID Tokens or SAML Assertions, and has no TLS, SQL, consent, KMS, key rotation/backups, or legal compliance logic. The HMAC key is hardcoded **solely for deterministic demo output** and must never be used in production; real keys belong in a secret manager/HSM with migration/recovery plans. Pseudonymous `sub` may still constitute personal data.

Save file `MinimalAttributeReleaseDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MinimalAttributeReleaseDemo {

    private static final String ISSUER = "https://idp.example.org";
    private static final byte[] DEMO_HMAC_KEY =
        "demo-only-not-a-production-secret".getBytes(
            StandardCharsets.UTF_8);

    record Policy(Set<String> allowed) {}
    record Saved(Map<String, String> data, Instant expiresAt) {}

    static final class AttributeBroker {
        private final Map<String, Policy> policies = Map.of(
            "portal", new Policy(Set.of("active", "displayName")),
            "reports", new Policy(Set.of("active")),
            "support", new Policy(Set.of("email"))
        );

        private String pairwiseSubject(String rp, String internalId)
                throws GeneralSecurityException {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                DEMO_HMAC_KEY, "HmacSHA256"));
            String input = ISSUER + "|" + rp + "|" + internalId;
            byte[] digest = mac.doFinal(
                input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, 24);
        }

        Map<String, String> release(
                String rp, Set<String> requested,
                Map<String, String> directory)
                throws GeneralSecurityException {
            Policy policy = policies.get(rp);
            if (policy == null ||
                    !policy.allowed().containsAll(requested)) {
                throw new SecurityException(
                    "Attribute request not approved for RP");
            }

            String internalId = directory.get("internalId");
            if (internalId == null || internalId.isBlank()) {
                throw new SecurityException(
                    "Missing trusted internal subject");
            }

            Map<String, String> out = new LinkedHashMap<>();
            out.put("iss", ISSUER);
            out.put("sub", pairwiseSubject(rp, internalId));
            for (String field : requested) {
                String value = directory.get(field);
                if (value != null) {
                    out.put(field, value);
                }
            }
            return Map.copyOf(out);
        }
    }

    static final class MinimalRetentionStore {
        private final Map<String, Saved> data = new HashMap<>();

        private String key(String rp, String sub) {
            return rp + "|" + sub;
        }

        void saveSupportEmail(Map<String, String> claims,
                              Instant now, Duration ttl) {
            if (ttl.isNegative() || ttl.isZero() ||
                    !claims.containsKey("email") ||
                    !claims.containsKey("sub")) {
                throw new IllegalArgumentException(
                    "Email and positive TTL required");
            }
            data.put(key("support", claims.get("sub")),
                new Saved(Map.of("email", claims.get("email")),
                          now.plus(ttl)));
        }

        boolean exists(String rp, String sub, Instant now) {
            Saved record = data.get(key(rp, sub));
            return record != null &&
                    now.isBefore(record.expiresAt());
        }

        boolean onlyEmailStored() {
            return data.values().stream().allMatch(
                v -> v.data().keySet().equals(Set.of("email")));
        }

        int purge(Instant now) {
            int before = data.size();
            data.entrySet().removeIf(
                e -> !now.isBefore(e.getValue().expiresAt()));
            return before - data.size();
        }

        void unlink(String rp, String sub) {
            data.remove(key(rp, sub));
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        Map<String, String> directory = Map.of(
            "internalId", "employee-0042",
            "active", "true",
            "displayName", "Lan",
            "email", "lan@example.org",
            "phone", "+84-000000",
            "birthDate", "1990-01-01",
            "homeAddress", "hidden-address",
            "salaryBand", "confidential"
        );

        AttributeBroker broker = new AttributeBroker();

        Map<String, String> portal = broker.release(
            "portal", Set.of("active", "displayName"),
            directory);
        Map<String, String> reports = broker.release(
            "reports", Set.of("active"), directory);
        Map<String, String> support = broker.release(
            "support", Set.of("email"), directory);

        System.out.println("Portal fields: " +
                new TreeSet<>(portal.keySet()));
        System.out.println("Reports fields: " +
                new TreeSet<>(reports.keySet()));
        System.out.println("Different RP subjects: " +
                !portal.get("sub").equals(reports.get("sub")));
        System.out.println("Stable Portal subject: " +
                portal.get("sub").equals(
                    broker.release("portal",
                        Set.of("active"), directory).get("sub")));

        boolean blocked = false;
        try {
            broker.release("reports", Set.of("email"), directory);
        } catch (SecurityException expected) {
            blocked = true;
        }
        System.out.println("Reports email request rejected: " +
                blocked);
        System.out.println("Portal phone disclosed: " +
                portal.containsKey("phone"));
        System.out.println("No birthDate released: " +
                !portal.containsKey("birthDate") &&
                !reports.containsKey("birthDate"));

        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        MinimalRetentionStore store = new MinimalRetentionStore();
        store.saveSupportEmail(support, now, Duration.ofDays(2));

        System.out.println("Support stored only email: " +
                store.onlyEmailStored());
        System.out.println("Other RP cannot read support data: " +
                !store.exists("reports", support.get("sub"),
                    now.plus(Duration.ofHours(1))));
        System.out.println("Available within TTL: " +
                store.exists("support", support.get("sub"),
                    now.plus(Duration.ofDays(1))));
        System.out.println("Expired at cutoff: " +
                !store.exists("support", support.get("sub"),
                    now.plus(Duration.ofDays(2))));
        System.out.println("Purge removed: " +
                store.purge(now.plus(Duration.ofDays(2))));

        store.saveSupportEmail(support, now, Duration.ofDays(2));
        store.unlink("support", support.get("sub"));
        System.out.println("Unlink removed record: " +
                !store.exists("support", support.get("sub"),
                    now.plus(Duration.ofHours(1))));
    }
}
```

Run:

```bash
javac MinimalAttributeReleaseDemo.java
java MinimalAttributeReleaseDemo
```

**Exact** stdout:

```text
Portal fields: [active, displayName, iss, sub]
Reports fields: [active, iss, sub]
Different RP subjects: true
Stable Portal subject: true
Reports email request rejected: true
Portal phone disclosed: false
No birthDate released: true
Support stored only email: true
Other RP cannot read support data: true
Available within TTL: true
Expired at cutoff: true
Purge removed: 1
Unlink removed record: true
```

### 17.1. Why does it produce this output?

- Portal is allowed `active` and `displayName`, plus simulated protocol identity fields `iss`/`sub`.
- Reports gets only `active` and `iss`/`sub`; requesting email exceeds its allowlist, so the broker **throws `SecurityException`** rather than silently emitting data.
- Same `internalId` with different RPs yields different HMAC inputs → different pairwise subjects; same RP+`internalId` yields a stable subject.
- `phone` and `birthDate` do not appear in RP output even though present in the source directory.
- Store saves only Support's `email`, omitting original claims, source employee ID, and `birthDate`.
- TTL checks `now.isBefore(expiresAt)`; **at the exact cutoff instant it is expired**.
- `purge` deletes expired records; `unlink` removes records even before retention expires.
- `Other RP cannot read` illustrates namespace isolation; the demo lacks real authentication/authorization and does not prove DB data is ACL-protected.

### 17.2. Limitations to address before production

1. HMAC keys must come from KMS/secret manager, never hardcoded; key versioning/rotation can shift subjects without a stable mapping/compatibility plan.
2. A real RP may serve multiple tenants; `issuer`, `tenant`, and `client registration`/`sector` must be trusted values, never taken from arbitrary user queries.
3. No OIDC token issuance/verification or SAML assertion signing/validation is present.
4. The program does not verify lawful basis/consent or notices; it models only purpose policies.
5. No encrypted DB/Redis, real TTL jobs, transactions, multi-node consistency, or backups exist.
6. `Map` holds source PII in memory for demo purposes; production needs memory-dump/serialization controls.
7. The `support` store has no actual caller authentication, only a namespace key; production must verify RP identity/server authorization.
8. Keyed pseudonymization **does not equal anonymization**; correlation/re-identification remains possible if accompanied by name/email.
9. Does not handle aliases, user merges/splits, account recovery, account linking, or data-subject requests.
10. Outside the storage layer, PII must also be excluded from logs/APM/search indices/backups per policy.

## 18. Testing: What Must Be Proven NOT to Leak?

### 18.1. Positive tests

| Test | Expected result |
| --- | --- |
| Portal RP requests only `openid` | ID Token contains only policy-approved protocol/identity fields; no unneeded email/phone |
| Portal requests approved display name | Only preferred name released per contract, not default full profile |
| Reports receives dedicated role | Only role/report entitlement, not full group DNs |
| LDAP projection specifies 2 attributes | Search response excludes all remaining fields |
| SCIM `attributes=id,active` | No email/phone/addresses unless schema/policy requires |
| Stable OIDC `(iss, sub)` | Same subject recognized across sessions on the same RP |
| Pairwise across RPs | Portal `sub` differs from Reports `sub` for the same user |
| Short-lived authorization cache | Permission changes/deprovisioning apply before approved TTL |
| Retention job | Expired records become unusable and are purged |
| Local logout/session destroy | Temporary profile/tokens are no longer accessible |

### 18.2. Privacy and security negative tests

| Scenario | Expected |
| --- | --- |
| Reports requests unapproved `email` | **Deny** release, audit field name/reason |
| New client with no contract | Release no optional profile attributes |
| RP tries forcing `scope=profile email phone address` | IdP release policy refuses to expand beyond contract |
| `claims` request unsupported by OP | App handles missing optional claim without falling back to full profile |
| SAML SP sends `AttributeConsumingService` asking for extra fields | IdP releases nothing outside allowlist |
| Signed SAML Assertion contains out-of-policy `birthDate` | Privacy QA **FAIL** even with valid signature |
| LDAP search with empty `returningAttributes` | Test detects that all user attributes could be returned |
| LDAP filter injection | Cannot access out-of-purpose users/attributes |
| SCIM `excludedAttributes` misses new field | Release regression test fails; use allowlist |
| SCIM provisions all employees to a small RP | Population policy fails; restrict to authorized accounts |
| RP uses email as primary key | Identity model QA FAILS if email changes/recycles |
| IdP A and IdP B share `sub` string | RP uses `(iss, sub)`, never merges two users |
| Pairwise `sub` emitted alongside identical email across RPs | Privacy correlation test flags exposure |
| Unkeyed `SHA256(email)` used for pairwise ID | Privacy QA FAILS for stable pairwise IDs |
| User deprovisioned | Revoke access, unlink identity, purge profile per policy |
| User changes email | Account link remains intact; stale copies handled |
| Retention TTL expires | Data no longer readable, cleanup runs |
| Backup restores deleted profiles | Replay deletion tombstones/policies; never resurrect accounts |
| Raw JWT/SAML/LDAP entry in debug logs | Security QA FAIL |
| Personal data in metric labels | Privacy QA FAIL |
| JWT UserInfo claim returned in out-of-purpose API response | Reject/strip before release |
| Session serializes full OIDC claims into Redis | Privacy QA flags if out-of-policy; fix IdP release/session storage |
| Cross-tenant PPI mapping | Cannot resolve subjects/data of another tenant |
| Stale authorization role | Fail closed/revalidate per criticality |
| Legal hold record | Retain only necessary subset, restricted purpose, explicit expiry/review |
| Consent withdrawn where applicable | Halt release/processing per policy and applicable rights |

### 18.3. Test both IdP and RP

**Inspecting only what landed in the RP database is not enough.** You must inspect:

- Decoded SAML Assertion payloads in test environments.
- Actual OIDC ID Token and UserInfo claims during login tests.
- Actual LDAP/SCIM server responses.
- Spring Security principal/session serialization.
- Downstream REST DTOs.
- Log pipelines/APM/search indices/backup snapshots.

A test asserting "portal DB only stores `displayName`" misses a signed ID Token still carrying `birthDate` over the wire or Redis session serialization storing the full JWT.

### 18.4. Data-flow regression tests

Whenever the IdP upgrades schemas or adds a claim, contract tests should enforce **deny-by-default**: new fields must not appear automatically at RPs. Whenever an app adds a new purpose (emailing, exporting reports), update approvals and retention. Never leave `profile` open permanently just because one past release needed it.

## 19. Project Implementation Runbook

### Step 1 — Map the data flow

Trace directory → IdP → protocol response → RP `SecurityContext` → DB/cache/log/API/backend. Annotate each arrow with issuer, RP/tenant, purpose, and data destination.

### Step 2 — Build an inventory and classify

List all LDAP attributes, OIDC claims, SAML `AttributeStatement`s, and SCIM fields currently in use. Categorize: protocol/security-required, authorization, UX, business-domain, sensitive/never-release. Closely audit multi-valued `groups`.

### Step 3 — Approve per-RP contracts

Create allowlists and **explicit deny lists**. Specify issuer/sector IDs, scopes, consent/trust agreements, TTLs, and deprovisioning triggers. Assign an owner and policy version for auditing.

### Step 4 — Filter at the source

Narrow LDAP `SearchRequest` projections; configure IdP attribute mappers/release rules; restrict OIDC scopes/claims; restrict SAML released attributes; restrict SCIM populations/fields. Never rely on RP-only filtering as your sole control.

### Step 5 — Limit RP persistence

Map subjects to random local account IDs; separate session-only fields from retained data. Configure Spring Session, caches, and JSON serialization. Keep raw principals/claims out of frontends, logs, and downstream APIs.

### Step 6 — Retention, correction, and deprovisioning

Design expiry/access checks, purge jobs, delete/unlink events, backup restore controls, and legal holds/restrictions. Verify role changes and account disables revoke appropriate sessions/tokens.

### Step 7 — Privacy/security integration tests

Test minimal positive requests and negative attribute-escalation cases; inspect actual ID Token/SAML/SCIM payloads; test pairwise IDs, cross-tenant isolation, logs, TTLs, deletion, and restores.

### Step 8 — Monitor for drift

Useful metrics: attribute-policy violations per RP, inactive accounts not yet deprovisioned, cache entries past TTL, unnecessary UserInfo call rate, and claim counts in issued assertions against allowlists. **Never** put raw emails/`sub`s/`NameID`s into metric labels.

## 20. Common Design Mistakes

| Anti-pattern | Why it is problematic | Better approach |
| --- | --- | --- |
| Requesting OIDC `profile email phone address` for every app | Broadens unnecessary disclosure | `openid` + approved per-RP claims |
| Putting every HR field into JWT/ID Token | Data spreads across systems, hard to govern/backup | IdP releases minimal claims |
| Using email as ID | Emails change, get recycled, enable correlation | Opaque/pairwise `(issuer, subject)` |
| Using `SHA256(email)` as pairwise `sub` | Guessable, correlates across RPs | Keyed/IdP-managed PPI per sector |
| Putting all of `memberOf` in tokens | Leaks group structure/roles | RP-specific derived entitlement |
| Relying on SAML signing instead of attribute policy | Signature only protects integrity/authenticity | Allowlist before signing |
| Calling default LDAP search with no projection | May return all user attributes | Specify explicit `setReturningAttributes` |
| Using SCIM `excludedAttributes` as primary control | Misses newly introduced fields | Allowlist query/schema + population policy |
| Syncing all employees to every RP | Duplicates data and accounts needlessly | Authorized account population, JIT provisioning |
| Keeping full profile in Spring Security sessions forever | Redis/backups prolong PII exposure | IdP minimization + session lifecycle controls |
| Logging `oidcUser.getClaims()` | Personal data/secrets leak in logs | Event codes and approved metadata only |
| Hashing email and calling it anonymous | Dictionary/linkage risk if mapping exists | Treat pseudonyms as protected personal data |
| Deleting JPA records without handling backups | Restores can resurrect deleted data | Backup retention/tombstones |
| Disabling app account while keeping tokens active | Access is not revoked | Token/session revocation per policy |
| Using one retention TTL for all data | Fails to reflect distinct purposes/obligations | Per-data-type retention schedule |
| Using consent as an excuse to collect everything | Consent has scope and separate lawful-basis rules | Purpose-specific necessity and transparency |

## 21. Production Checklist

- [ ] Every RP/client has an owner, purpose, issuer, tenant, and attribute allowlist.
- [ ] LDAP directories are queried with explicit `returningAttributes` and minimal bind ACLs.
- [ ] OIDC scopes/claims do not default to `profile`/`email`/`phone`/`address` unnecessarily.
- [ ] IdP release policy is enforced per RP, not just DTO filtering at the RP.
- [ ] SAML `NameID`/`AttributeStatement` fits purpose, with no group dumps.
- [ ] SCIM restricts provisioning population and `attributes`/`returned` policies.
- [ ] Subject keys at RPs use trusted issuer + scoped subject, never email.
- [ ] Pairwise PPIs leak no plaintext PII and never rely on unkeyed `SHA256(email)`.
- [ ] Multi-tenant and cross-RP mappings have zero leakage.
- [ ] Derived authorization/eligibility comes from trusted sources with freshness policies.
- [ ] Never store raw ID Tokens, SAML Assertions, or LDAP `SearchResult`s in account databases.
- [ ] Spring Session/Redis serialization is reviewed not to retain excessive profiles.
- [ ] Domain records containing PII have purpose, retention owner, and expiry/review.
- [ ] Token/session deprovisioning, logout, and role-change revocation are tested.
- [ ] Purge jobs cover caches, DB, logs, search indices, exports, and backups per policy.
- [ ] User correction/erasure/unlinking/withdrawal have clear workflows.
- [ ] Data retained under legal hold is segregated, restricted, and reviewed.
- [ ] Never log raw `NameID`/`sub`/email/access tokens/JWTs/attributes/passwords.
- [ ] QA includes negative tests for claim escalation, SCIM leakage, LDAP projection, and cross-tenancy.
- [ ] Contract versioning and monitoring detect new fields outside the allowlist.
- [ ] Permissions and retention periods are approved by privacy/security/legal owners as applicable.

## 22. Review Questions

**1. Just because the directory has `mail`, should every application receive email?**  
No. Each RP needs its own purpose and attribute release contract; login usually only requires a stable subject.

**2. Does data minimization just mean filtering JSON DTOs in the controller?**  
No. Once the IdP emits a claim, the data has already been shared. Reduce at the source, and restrict storage/logging at the receiver.

**3. Why can OIDC `profile` be overly broad?**  
Because it requests a bundle of standard profile claims potentially including birthdate/gender/picture, not just a display name.

**4. Should an RP use email or `(iss, sub)` to link accounts?**  
`(issuer, subject)` from a verified token; emails can change or be recycled.

**5. Does a pairwise subject prevent all correlation across apps?**  
No. If matching email/name/phone accompany it, RPs can still correlate. PPIs are also usually pseudonymous personal data.

**6. Why is `SHA256(email)` insufficient for generating PPIs?**  
Emails are guessable and unkeyed hashes are vulnerable to brute force, while identical values across RPs enable correlation. Use IdP-managed, keyed sector-specific derivation or random mappings.

**7. Does LDAP `attributes=[]` mean return no fields?**  
No. Per RFC 4511, an empty list requests all user attributes; only `1.1` indicates no attributes.

**8. Does SCIM `attributes=id,active` omit `id` if omitted from the parameter?**  
No, because schema `returned=always` fields (like `id`) are still returned, while `active` is explicitly requested.

**9. Why should sending all groups never be the default?**  
Because it exposes org structure and unrelated permissions; emit RP-specific entitlements or policy decisions instead.

**10. If you only need to know a user is over 18, does the RP need their birth date?**  
Usually not. Use a verified derived `over18` claim if assurance and policy match.

**11. When a user leaves the company, is disabling OIDC login enough to erase their data?**  
Not yet. RPs may still retain SCIM-provisioned accounts, caches, records, tokens, and backups; a deprovisioning/retention workflow is needed.

**12. Does a one-hour Redis TTL guarantee all personal data was deleted?**  
No. Logs, backups, replicas, DBs, analytics, and exports still remain.

**13. Does a signed SAML Assertion automatically guarantee data minimization?**  
No. A signature proves integrity/authenticity; it does not reduce the readable payload.

**14. Why can Spring Security `OidcUser` affect privacy even if JPA saves only `sub`?**  
Because `SecurityContext`/session serialization can retain tokens/profile claims; review framework storage and IdP release.

**15. When an email changes, what should the account link do?**  
Keep the link by immutable trusted subject if appropriate, update email per purpose, and never use email as a foreign key.

**16. Does consent mean data can be kept indefinitely?**  
No. Purpose, scope, obligations, and applicable limits still apply; handle withdrawal/deletion per policy/lawful basis.

## 23. Documentation and Standards References

- [NIST SP 800-63C-4 (2025) — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): data minimization, pairwise identifiers, derived attributes, provisioning/deprovisioning, and privacy safeguards.
- [NIST CSRC — SP 800-63C-4 Final](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): official July 2025 publication.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `sub`, claims, `profile`/`email`/`phone`/`address` scopes, `claims` parameter, and pairwise subject/sector identifiers.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, mapping authorities, claims processing.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticatedPrincipal`, `getAttribute`/`getFirstAttribute`.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchRequest.attributes`, `1.1`, `*`, and attribute selection semantics.
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643): attribute characteristics `returned`/`mutability`/`required`.
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): `attributes`/`excludedAttributes` parameters and partial resource representations.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding logging tokens, session IDs, and sensitive personal data.
- [OWASP — User Privacy Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html): privacy by design, minimizing data disclosure.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): protecting permitted stored data, key management, and storage.

**Remember:** A well-designed federation system **does not ship the entire directory profile to every application**. The RP requests only attributes needed for an approved purpose; the IdP **allowlists** at the source; subjects are namespaced by issuer and prefer pairwise/opaque forms to reduce correlation; LDAP/SCIM return only required fields; Spring Security maps minimal data for accounts/roles/sessions; stored data has dedicated TTLs/retention/deletion rules; and logs/backups follow that same lifecycle. **Signed/encrypted tokens do not automatically guarantee privacy**, and pseudonymous IDs are not anonymous by default.