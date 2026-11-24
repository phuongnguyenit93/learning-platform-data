# Mapping SAML Groups to Internal Authorities via an Allowlist

## 1. Practical Problem: The IdP Returns Groups, the Application Must Decide Permissions

A Spring Boot application acting as a **SAML 2.0 Service Provider (SP)** receives a SAML Response from an Identity Provider (IdP). The IdP authenticates employees and may return AttributeStatements such as HR groups, departments, or group IDs from Active Directory/Entra ID. The application wants to grant report-reading, approval, or business-action permissions based on groups. This is an **authorization mapping** problem, not an operation to copy group names from the IdP into Spring Security roles.

Example information after the SAML Response has been verified:

~~~text
SAML IdP issuer   : https://idp-a.example.org/metadata
Registration ID   : corp-a
NameID            : persistent-employee-482
Attribute Name    : urn:example:claims:group-id
Attribute values  :
  - grp:finance-readers
  - grp:finance-approvers
  - grp:external-admin
Tenant            : tenant-a
~~~

The application only allows two governed mappings:

~~~text
(corp-a, tenant-a, grp:finance-readers)
       -> TENANT_A_REPORT_READ

(corp-a, tenant-a, grp:finance-approvers)
       -> TENANT_A_REPORT_APPROVE

grp:external-admin
       -> NO MAPPING
~~~

The result is `TENANT_A_REPORT_READ` and `TENANT_A_REPORT_APPROVE`, with **no** `ROLE_ADMIN` or `ROLE_SUPER_ADMIN`.

This knowledge article belongs to **Spring Security - federation → Comprehensive Practice** with the topic **"Mapping SAML Groups to Internal Authorities via an Allowlist"**.

### Learning Objectives

After this article, you will:

1. Distinguish **SAML Authentication**, **AttributeStatements**, **GrantedAuthority**, **role**, **permission**, **local account**, and **tenant**.
2. Understand why `groups`, `memberOf`, and `roles` are **data from the IdP**, not automatically application permissions.
3. Properly extract **all values** in a multi-valued SAML attribute, not just `getFirstAttribute()`.
4. Design an **exact-match allowlist**, scoped by IdP registration/issuer and tenant.
5. Use `SimpleGrantedAuthority` and `hasAuthority`/`hasRole` with the right prefixes, avoiding over-granting.
6. Never grant elevated privileges from strings like `Admin`, `ROLE_ADMIN`, wildcards, or unverified emails.
7. Bind verified external identities to stable app-local accounts, checking `active`, membership, and policy.
8. Distinguish granting **functional authorities** from access to **resources of a specific tenant or object**.
9. Integrate via a Spring SAML2 provider/response authentication converter suited to Spring Security 6.x/7.x.
10. Preserve XML signatures, Issuer, Audience, Recipient, timestamps, and request correlation when customizing authorities.
11. Design unit, integration, and negative tests for colliding group names, unknown groups, group spoofing, revoked groups, and multi-IdP.
12. Run a **standalone Java 17** program simulating the allowlist with deterministic stdout, without Spring.
13. Verify handling of group changes after login, stale sessions, provisioning events, and privilege revocation.
14. Have a security checklist, operations runbook, and pre-release QA criteria.

**Context:** Java 17+, Spring Boot 3.x, Spring Security Servlet SAML2 Login; two representative baselines are Spring Security 6.x with its corresponding OpenSAML provider and 7.x with `OpenSaml5AuthenticationProvider`. The `example.org` URLs, group IDs, and permission strings in this article are illustrative only; in real systems, use metadata and group catalogs supplied by your organization.

---

## 2. Data Flow: Map Only After SAML Verification

~~~mermaid
sequenceDiagram
  participant Browser
  participant IdP
  participant SP as Spring Security SP
  participant Policy as Group Allowlist + Account Policy
  participant App as Protected Resource
  Browser->>SP: GET /reports
  SP-->>Browser: Redirect SAML AuthnRequest
  Browser->>IdP: AuthnRequest + login
  IdP-->>Browser: SAMLResponse with AttributeStatement
  Browser->>SP: POST ACS /login/saml2/sso/corp-a
  SP->>SP: Verify trust, XML signature, Issuer, Audience, time, subject
  alt SAML invalid
    SP-->>Browser: Authentication failure
  else SAML verified
    SP->>Policy: Verified issuer/subject + group values
    Policy->>Policy: Account ACTIVE, tenant membership, explicit allowlist
    Policy-->>SP: Internal GrantedAuthority subset
    SP->>SP: Create Authentication/SecurityContext
    Browser->>App: GET /tenants/tenant-a/reports/42
    App->>App: Check current account + tenant + object permission
    App-->>Browser: 200 only when authorized
  end
~~~

**Three boundaries must stay strictly separated:**

- **AuthN trust:** The SAML Response/Assertion must pass through `Saml2WebSsoAuthenticationFilter`, token converter, `RelyingPartyRegistration`, and OpenSAML signature/issuer/audience/time/subject validators.
- **Group-to-authority mapping:** Only after the Response is valid are groups mapped through an **application-controlled allowlist**, never from unverified group names.
- **Resource AuthZ:** A permission may be issued as a GrantedAuthority, yet endpoints **must still check** resource ownership, active tenant membership, account state, and current policy.

If the XML signature is invalid, there is **no** step to "just read AttributeStatement anyway to see if the groups look valid". Group extraction from unverified XML is untrusted data.

### Is the Default Spring SAML Authority Equal to Groups?

Per the Spring Security SAML2 reference, the default response authentication converter creates a principal containing the SAML attributes and grants a basic authority such as `ROLE_USER` (and depending on version, factor markers). It does **not by default** turn every SAML `groups` entry into `ROLE_*`. Consequently:
- An SSO user can be authenticated while holding zero business permissions yet.
- You must configure **explicit mapping** to grant `TENANT_A_REPORT_READ`, `REPORT_EXPORT`, or application-designed roles.
- `isAuthenticated()` must not suffice to access sensitive endpoints.
- `ROLE_USER` does not mean the user belongs to any tenant or may view any document.

## 3. SAML AttributeStatement and Group Characteristics

An Assertion may contain attributes such as:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute
      Name="urn:example:claims:group-id"
      NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
      FriendlyName="groups">
    <saml:AttributeValue
        xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:type="xs:string">grp:finance-readers</saml:AttributeValue>
    <saml:AttributeValue
        xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:type="xs:string">grp:finance-approvers</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

**The XML above is illustrative structure only, not a signed SAML Response.** In integration tests, use a properly signed SAML Response/Assertion carrying this attribute within profile-protected content.

An `Attribute` element may include:
- `Name`: contractual name; may be a URI, OID, or string.
- `NameFormat`: attribute name format semantics, interpreted alongside metadata.
- `FriendlyName`: human-readable hint; should not be treated as a unique policy key.
- `AttributeValue`: may be **multi-valued**, and may be strings or XML structures depending on IdP/OpenSAML.
- `EncryptedAttribute`: some IdPs encrypt attributes; process only after valid decryption.

### Examples of Different IdPs Representing Groups Differently

| IdP | Attribute Name | Illustrative Value Style | Notes |
| --- | --- | --- | --- |
| SAML IdP A | `urn:example:claims:group-id` | `grp:finance-readers` | Stable group ID allowlisted by the app |
| SAML IdP B | `memberOf` | `CN=Finance,OU=Groups,DC=b,DC=example,DC=org` | DN contains commas; never split on commas |
| SAML IdP C | URI/OID per federation contract | Directory object GUID | Must normalize per agreed encoding |
| SAML IdP D | `groups` | `Finance Readers` | Mutable display name, collision-prone |
| SAML IdP E | `roles` | `ROLE_ADMIN` | Never adopt directly as a Spring authority |

**There is no universal SAML group attribute name across all IdPs.** Agree with each IdP on the exact `Name`, `NameFormat`, value type, and semantics it emits. If an IdP omits groups, enforce fail-closed policy: add no business permissions beyond what the local account service verifies.

## 4. Use Stable Group IDs, Not Display Names by Default

Display names:
- Can change when a department is renamed.
- Can collide across directories or OUs.
- Can differ in casing due to case normalization.
- Can contain Unicode, spaces, or delimiter characters.
- Can be reused for a new group after an old group is deleted.

Therefore, if the IdP directory provides an **immutable group object ID**, prefer that ID (after agreeing on semantics and namespace). If only DNs or role names exist, you must:
1. Identify the **IdP issuer** and directory scope.
2. Use the exact comparison defined in the contract.
3. Document normalization rules explicitly; avoid blindly calling `toLowerCase()` everywhere.
4. Review impacts whenever groups are renamed, reparented, or recreated.
5. Never substitute `FriendlyName` for `Name` if two names could collide.
6. Distinguish the string `"Finance"` in IdP A from `"Finance"` in IdP B.
7. Track mapping versions and change-approval ownership.

### Never Split a Group DN on Commas

Example:

~~~text
CN=Finance,OU=Groups,DC=corp,DC=example,DC=org
~~~

This is **one** DN, not five groups. Calling `value.split(",")` can fabricate bogus "groups" like `CN=Finance` and `OU=Groups`, causing misauthorized access. When an IdP returns multiple `AttributeValue` elements, each element is one group value per contract. If an IdP returns a serialized list string, parse **strictly according to the signed contract**, never guessing delimiters.

### Validate Group Value Types

Spring `Saml2AuthenticatedPrincipal#getAttribute(name)` / `Saml2ResponseAssertionAccessor#getAttribute(name)` may return `List<A>`, and `getAttributes()` returns `Map<String, List<Object>>`. When mapping:
- Iterate over the **entire list**.
- Map only values of the policy-allowed type, typically string IDs.
- For unexpected XML structures or invalid types, never call `toString()` and treat the result as a role.
- Cap attribute value count/size to guard against DoS if an IdP is compromised.
- Deduplicate with a `Set`, while never inventing permissions outside the allowlist.
- Never assume every `groups` attribute is non-empty or non-null.

## 5. An Allowlist Is a Decision Table, Not a "Group Prefix"

An allowlist should use an explicit mapping key:

~~~text
(relying-party registration / IdP issuer,
 app tenant,
 exact SAML attribute Name / NameFormat contract,
 exact external group identifier)
     -> approved internal authority set
~~~

Example:

| Registration | Tenant | Attribute Name | External Group ID | Authority |
| --- | --- | --- | --- | --- |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-readers` | `TENANT_A_REPORT_READ` |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-approvers` | `TENANT_A_REPORT_APPROVE` |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:auditors` | `TENANT_A_AUDIT_READ` |
| `partner-b` | `tenant-b` | `urn:example:claims:group-id` | `grp:finance-readers` | `TENANT_B_REPORT_READ` |
| `partner-b` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-readers` | **No mapping** |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:external-admin` | **No mapping** |

An identical group ID across two IdPs does **not** grant identical roles. Values not entered in the table are **unknown** and yield an empty authority addition.

### Policies to State Explicitly

1. **Deny by default** for every group absent from the allowlist.
2. Support no `*` wildcards, contains-matching, arbitrary regexes, or `startsWith("admin")`.
3. Never allow the IdP to send internal names like `ROLE_ADMIN` to bypass the table.
4. **Never auto-provision mappings** upon seeing a new group.
5. Never infer privileged authorities from email domain, department, or display name.
6. Global/system admin requires separate approval; ideally never map it directly from external groups without governance.
7. If the tenant/user is disabled, grant nothing even if a group matches.
8. Mapping changes must be versioned, reviewed, audited, and rolled out with tests.
9. Every authority must document its purpose and tenant/object scope.
10. Never unconditionally union all roles from multiple IdPs onto one account.

## 6. `GrantedAuthority`, `ROLE_`, `hasRole`, and `hasAuthority`

Spring Security uses `GrantedAuthority` to represent permissions inside `Authentication`.

Example:

~~~java
new SimpleGrantedAuthority("TENANT_A_REPORT_READ")
~~~

For a custom-authority permission style:

~~~java
@PreAuthorize("hasAuthority('TENANT_A_REPORT_READ')")
public Report readTenantAReport(...) { ... }
~~~

When using the role style:

~~~java
new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")
~~~

and:

~~~java
@PreAuthorize("hasRole('REPORT_VIEWER')")
public Report readReport(...) { ... }
~~~

`hasRole("REPORT_VIEWER")` normally matches authority `ROLE_REPORT_VIEWER` using the default role prefix. Calling `hasAuthority("REPORT_VIEWER")` performs an **exact string** match without prepending a prefix. A custom default role prefix can be configured; verify against your Spring Security version/config.

### Small Mistakes with Large Consequences

| Mapped To | Guard Used | Outcome |
| --- | --- | --- |
| `ROLE_REPORT_VIEWER` | `hasRole('REPORT_VIEWER')` | Matches default convention |
| `TENANT_A_REPORT_READ` | `hasAuthority('TENANT_A_REPORT_READ')` | Exact permission |
| `ROLE_REPORT_VIEWER` | `hasAuthority('REPORT_VIEWER')` | Usually fails due to string mismatch |
| IdP-sent `ROLE_ADMIN` | `hasRole('ADMIN')` | **Privilege escalation risk** |
| `TENANT_A_REPORT_READ` | Only `isAuthenticated()` | Permission unchecked |
| `TENANT_A_REPORT_READ` | `hasAuthority('TENANT_B_REPORT_READ')` | Wrong tenant |
| Default `ROLE_USER` | `hasRole('ADMIN')` | Insufficient |
| Default `ROLE_USER` | `isAuthenticated()` | May admit user to routes if guard is too broad |

**Default `ROLE_USER` must never serve as proof of permission to read all internal data.**

## 7. Security Responsibilities Before Mapping

A mapper **is not responsible for verifying XML signatures**. It must only run **after** the OpenSAML provider verifies:
1. Response/Assertion Signature against an IdP certificate trusted by the SP.
2. Response/Assertion Issuer and matching relying party registration.
3. Destination, AudienceRestriction, and Recipient.
4. NotBefore/NotOnOrAfter and bearer subject confirmation.
5. Request correlation / InResponseTo in SP-initiated flows.
6. SAML Status and valid assertions.
7. Decryption for encrypted assertions/attributes if used by the IdP.
8. XML structure and signature reference scope.
9. Additional validations/replay policy required by the application.

If a mapper directly runs `Base64.getDecoder().decode(request.getParameter("SAMLResponse"))` and extracts `groups`, **no trust boundary exists**. Anyone can craft XML containing `Admin` and attempt privilege escalation.

### Trust by Origin, Not by Value Alone

A group value `"grp:finance-approvers"` may be validly issued by IdP A, while IdP B might emit an identical string. The app should only let IdP B grant authorities that IdP B itself is authorized to delegate under the **approved policy**. A group string alone carries no proof of who is entitled to assert it.

## 8. Versioned and Governed Internal Authority Catalog

Policy example:

~~~yaml
# Example application data; not a built-in Spring Boot property.
saml-group-authority-policy:
  version: "2026-11-07"
  registrations:
    corp-a:
      expected-issuer: "https://idp-a.example.org/metadata"
      attribute-name: "urn:example:claims:group-id"
      tenants:
        tenant-a:
          "grp:finance-readers":
            - TENANT_A_REPORT_READ
          "grp:finance-approvers":
            - TENANT_A_REPORT_APPROVE
          "grp:auditors":
            - TENANT_A_AUDIT_READ
    partner-b:
      expected-issuer: "https://idp-b.example.org/metadata"
      attribute-name: "urn:example:claims:group-id"
      tenants:
        tenant-b:
          "grp:finance-readers":
            - TENANT_B_REPORT_READ
~~~

**This is an application-defined schema**; Spring Security has no default auto-binding mapper just from declaring this YAML. Developers must build `@ConfigurationProperties`/a policy service, validate config, and check against an approved list.

### Startup Configuration Constraints

- Reject conflicting duplicate mapping keys.
- Reject unknown internal authority strings if policy fixes the authority catalog.
- Reject unauthorized mappings from an external group to `ROLE_SUPER_ADMIN`.
- Reject blank issuers, blank group IDs, and unsafe wildcards.
- Never silently merge two registrations sharing a group ID into one namespace.
- Verify `expected-issuer` matches trusted SAML metadata/configuration.
- In production, only ops/security policy admins may edit mappings.
- Manage config via version control + PR review + CI tests; never accept config from untrusted IdP claims.
- Never persist mappings into sessions as immutable data forever.

### Should the Allowlist Live in a Database?

Yes, when an enterprise manages many tenants and policies change frequently:
- Table `external_group_authority_map` with `registration_id`, `issuer`, `tenant_id`, `attribute_name`, `external_group_id`, `internal_authority`, `approved_at`, `approved_by`, `version`, `active`.
- Composite unique key to prevent collisions.
- Admin UI with RBAC and dual control for privileged changes.
- Apply transactions/rollback and immutable audit logs.
- Cache policy with TTL/version and invalidation.
- Deny when the policy registry is unavailable per required security posture; never fall back to "grant everyone".

A database allowlist does **not** make an IdP group claim trustworthy if signatures/issuers are unverified.

## 9. Local Account Binding Is Required, Not Just `NameID`

A SAML `NameID` may be:
- A persistent identifier scoped to the IdP–SP relationship;
- A short-lived transient identifier;
- An email-style identifier that can change or be reassigned;
- An unspecified string with IdP-specific semantics.

An enterprise app should map the verified external identity to an immutable `appAccountId`. Scope it by:
- IdP issuer/entityID/registration trust context;
- NameID format and qualifiers if used by the profile;
- Subject value or stable directory ID per contract;
- Tenant/account linking governance.

Never use **unscoped** email/username/NameID text as the primary account key. Verify the account is **ACTIVE**, check current membership/roles, and verify tenant status **before granting authorities**.

### One IdP Serving Multiple Tenants

An IdP authenticating user A does not mean user A belongs to every tenant sharing that IdP. For example:
- `corp-a` is the IdP for both `tenant-a` and `tenant-c`.
- User holds group `grp:finance-readers` yet has membership only in `tenant-a`.
- The group mapping table for `tenant-c` may also list a similar group.

**You must verify local membership in `tenant-c`**, never treating the IdP name as membership. Every resource must independently verify `tenantId`/ACL.

## 10. Multi-Valued Group Attributes: Do Not Use Only the First Value

Spring Security 6.x may provide:

~~~java
Saml2AuthenticatedPrincipal principal = ...;
List<String> groups =
        principal.getAttribute("urn:example:claims:group-id");
~~~

This is a **Spring API snippet**, not standalone Java. `getAttribute` may return null and must be handled. `getFirstAttribute()` returns a single value, which is **unsuitable** when an IdP can emit multiple groups.

Spring Security 7.x introduces `Saml2AssertionAuthentication` alongside `Saml2ResponseAssertionAccessor`, and `Saml2AuthenticatedPrincipal` is deprecated in that branch; for new implementations, prefer reading attributes from the accessor:

~~~java
if (authentication instanceof Saml2AssertionAuthentication saml) {
    Saml2ResponseAssertionAccessor verifiedAssertion =
            saml.getCredentials();
    List<Object> groups = verifiedAssertion
            .getAttributes()
            .getOrDefault(
                "urn:example:claims:group-id",
                List.of());
    // Apply application-approved allowlist only.
}
~~~

This requires appropriate imports and Spring 7.x dependencies; it is **not a standalone javac test**. Avoid invoking it before `AuthenticationManager` has validated SAML. If using a compatibility layer, preserve SLO credential/accessor behavior.

### Value Type Checking

In `Map<String,List<Object>>`, each element may be a type other than `String`. Example:

~~~java
for (Object rawValue : groups) {
    if (!(rawValue instanceof String groupId)) {
        // Reject/ignore unsupported group value by policy.
        continue;
    }
    // Lookup exact allowlist by issuer/registration/tenant/groupId.
}
~~~

Do not:
- Call `rawValue.toString()` on arbitrary objects to grant permissions;
- Split on commas when the IdP emits a DN;
- Auto-trim/lowercase unless specified by the IdP contract;
- Concatenate every external group into `"ROLE_" + groupString`;
- Read `<Attribute FriendlyName="roles">` without verifying `Attribute Name`;
- Treat `groups=null` as "all groups".

## 11. Designing the Mapping Service: Inputs and Outputs

A pure business API does not need a direct dependency on OpenSAML:

~~~java
Set<String> resolveAuthorities(
        VerifiedSamlIdentity identity,
        ActiveAccount account,
        String requestedTenantId,
        Map<String, List<Object>> verifiedAttributes);
~~~

**`VerifiedSamlIdentity` and `ActiveAccount` are application-defined types**, not Spring classes. `VerifiedSamlIdentity` must only be constructed from a verified provider/callback, never from user-supplied request bodies or headers.

The service should:

1. Look up the exact external identity → local account, rejecting unknown/disabled accounts.
2. Confirm `requestedTenantId` is a tenant where the user has active membership.
3. Verify the IdP/registration is trusted by that tenant per approved policy.
4. Read only the Attribute Name approved for that registration.
5. Turn each group value into an exact lookup key scoped by issuer/tenant.
6. Union only **allowlisted internal authorities**.
7. Never synthesize system admin authorities from unknown/extra groups.
8. Deduplicate results and output an immutable set.
9. Emit an audit event recording accepted/rejected group counts and policy version; avoid logging raw sensitive group memberships unnecessarily.
10. Support policy revocation/refresh when a user changes groups or is offboarded.

### Why Not Just `map.get(groupId)`?

Because IdP A and IdP B may both have `Finance` or `Admins`. A bare `Map<String,String>` fails to distinguish:
- Trust domain / issuer;
- Tenant;
- Attribute semantics;
- Group identifier origin;
- Environment (prod vs. test);
- Approval history;
- Authority scope.

Collapsing namespaces into a single string is a common cause of **confused deputy** and cross-tenant privilege escalation.

## 12. Spring Security 7.x: Using the Response Authentication Converter

Per Spring Security documentation, `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter` is the customization point for `Authentication` after response/assertion validation. The default `ResponseAuthenticationConverter` can serve as a delegate to preserve framework extraction of principal, credentials, and attributes.

Example **Spring Security 7.x integration pattern** with an application-implemented policy service:

~~~java
package com.example.security;

import java.util.Collection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.*;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlGroupSecurityConfig {

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            VerifiedGroupAuthorityPolicy policy) throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        ResponseAuthenticationConverter defaults =
                new ResponseAuthenticationConverter();

        provider.setResponseAuthenticationConverter(responseToken -> {
            Saml2Authentication original = defaults.convert(responseToken);

            if (!(original instanceof Saml2AssertionAuthentication saml)) {
                throw new BadCredentialsException(
                        "Unsupported SAML authentication representation");
            }

            Collection<? extends GrantedAuthority> allowlisted =
                    policy.requireActiveAccountAndMap(
                            saml.getRelyingPartyRegistrationId(),
                            saml.getName(),
                            saml.getCredentials().getAttributes());

            return saml.toBuilder()
                    .authorities(existing -> {
                        existing.removeIf(authority ->
                                authority.getAuthority().startsWith(
                                        "TENANT_"));
                        existing.addAll(allowlisted);
                    })
                    .build();
        });

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated());

        http.saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

**Critical notes on this snippet:**
- This is Spring configuration **depending on project classes and application services**; it does not compile standalone. `VerifiedGroupAuthorityPolicy` must be implemented by you: resolve the verified registration/issuer, link the subject to an active local account, verify tenant membership, grant only allowlisted authorities, and reject `unknown/disabled`. `saml.getName()` is not automatically a durable local account key, so production must map by identity namespace with proper format/qualifiers.
- This snippet illustrates **7.x** (`Saml2AssertionAuthentication`, `toBuilder`, `authorities(Consumer)`); 6.x has different APIs. Cross-check the exact project source/Javadoc versions, especially when upgrading from 6.x.
- Calling `toBuilder()` on `Saml2AssertionAuthentication` preserves the framework representation/accessor, which benefits SLO. **Do not arbitrarily replace it with `new Saml2Authentication` that discards SAML assertion metadata** if your version needs the accessor for logout.
- In this example, `existing.removeIf` removes any prior custom authority starting with `TENANT_` and adds only allowlisted ones; production policies may choose which other trusted authorities to keep or strip per convention. **Do not rely solely on prefix filtering** if earlier code could inject dangerous authorities from untrusted sources: ensure `defaults` and other converters never inject elevated roles, or start from an explicit allowlisted baseline set.
- Default `ROLE_USER` or SAML factor authorities do not grant business permissions. Every sensitive route requires `hasAuthority`/policy-service checks.
- Never use a custom response converter to skip signature, issuer, recipient, audience, or condition validators: the converter runs **after** verification.
- The config requires `RelyingPartyRegistrationRepository`, valid IdP metadata/verification credentials, `spring-security-saml2-service-provider`, and compatible OpenSAML.
- If the app has multiple `AuthenticationProvider`s or SSO methods, ensure `AuthenticationManager` does not accidentally drop providers used by other mechanisms; design `ProviderManager` per your application architecture.

### Clarifying `authorities(...)` in Spring Security 7

`AbstractAuthenticationToken.AbstractAuthenticationBuilder` uses:

~~~java
.authorities(existingAuthorities -> {
    existingAuthorities.addAll(approvedAuthorities);
})
~~~

`authorities` accepts a **Consumer of the collection**; not every version provides an overload taking a `Collection` directly. `Saml2AssertionAuthentication` has its own builder; `saml.toBuilder().authorities(...).build()` preserves the Spring 7.x representation where that API is supported.

### Alternative: Local UserDetails / Account Authority Lookup

A system wanting backend-controlled permissions can:
1. Use the default SAML response converter to obtain the validated principal/attributes.
2. Look up `accountId` by verified external identity.
3. Load the active local account, tenant memberships, and grants from the DB.
4. Use SAML groups **only** to activate preapproved mappings, never letting them override revocations.
5. Build authentication authorities from trusted local grants + authorized mappings.
6. Revalidate permissions at the resource boundary.

Spring docs show combining a response converter with `UserDetailsService`. In Spring 7.x, `Saml2AssertionAuthentication` and its accessor help retain SAML metadata; when swapping the principal to a local user object, test SLO and principal conversion carefully. Never treat `UserDetailsService#loadUserByUsername(NameID)` as safe if NameID is not scoped by IdP.

## 13. Spring Security 6.x: Check the Exact Version API

In Spring Security 6.x:
- Implementations may be `OpenSaml4AuthenticationProvider` or `OpenSaml5AuthenticationProvider` depending on version/dependencies.
- Authentication may be `Saml2Authentication` with `Saml2AuthenticatedPrincipal`.
- You can typically customize `setResponseAuthenticationConverter` using the converter for your provider.
- Nested types such as `ResponseToken`, `ResponseAuthenticationConverter`, and constructors differ; **do not assume 7.x syntax compiles verbatim on 6.x**.
- `Saml2AuthenticatedPrincipal#getAttribute(name)` returns multiple values; `getFirstAttribute` returns only one.
- `new Saml2Authentication(principal, original.getSaml2Response(), verifiedAllowlistedAuthorities)` is a pattern in older versions when the principal type/constructor matches, provided response verification has already completed.

A **6.x conceptual fragment**, not a standalone class:

~~~java
Saml2Authentication validated = defaultConverter.convert(responseToken);
Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) validated.getPrincipal();

List<Object> rawGroups =
        principal.getAttributes().getOrDefault(
                "urn:example:claims:group-id", List.of());

// mapExactAllowlist() must be written by the app and obtain issuer/tenant
// from trusted relying-party/account context, not from the request.
// Collection<GrantedAuthority> grants = ...

// On versions supporting this constructor:
// return new Saml2Authentication(
//         principal, validated.getSaml2Response(), grants);
~~~

In 7.x, `Saml2AuthenticatedPrincipal` is deprecated. When migrating, prefer `Saml2ResponseAssertionAccessor` and `Saml2AssertionAuthentication` per official docs so information needed for Single Logout is retained.

**Never confuse `Saml2AuthenticationToken`** (incoming unverified request) with `Saml2Authentication`/`Saml2AssertionAuthentication` (verified outcome). Mapping group authorities on an unverified token violates the trust boundary.

## 14. Standalone Java 17: Allowlist Scoped by Issuer and Tenant

This example uses **only the Java Standard Library**, with no Spring/OpenSAML dependencies. It simulates the group → authority logic **after SAML verification**.

Scenario:
- IdP A and IdP B share the subject string `"shared-001"` yet represent two distinct external identities.
- IdP A has finance readers + finance approvers + an unapproved `"external-superadmin"` group.
- IdP B has the same group string as IdP A, yet maps only to tenant B's authority.
- User A must not obtain tenant B permissions.
- Unknown group, unknown issuer, missing groups, and disabled account grant zero permissions.

Create **`SamlGroupAllowlistDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public final class SamlGroupAllowlistDemo {

    private static final String GROUP_ATTRIBUTE =
            "urn:example:claims:group-id";

    record IdentityKey(String issuer, String subject) {}

    record MappingKey(
            String issuer, String tenantId, String groupId) {}

    record Account(
            String accountId, boolean enabled,
            Set<String> activeTenants) {}

    record VerifiedSaml(
            String issuer,
            String subject,
            Map<String, List<String>> attributes) {}

    private static final String ISSUER_A =
            "https://idp-a.example.org/metadata";
    private static final String ISSUER_B =
            "https://idp-b.example.org/metadata";

    // In a real app, these values are application-managed policy.
    private static final Map<MappingKey, Set<String>> ALLOWLIST =
            Map.of(
                new MappingKey(ISSUER_A, "tenant-a",
                        "grp:finance-readers"),
                Set.of("TENANT_A_REPORT_READ"),

                new MappingKey(ISSUER_A, "tenant-a",
                        "grp:finance-approvers"),
                Set.of("TENANT_A_REPORT_APPROVE"),

                new MappingKey(ISSUER_B, "tenant-b",
                        "grp:finance-readers"),
                Set.of("TENANT_B_REPORT_READ")
            );

    // Demonstration only: account binding by scoped identity.
    private static final Map<IdentityKey, Account> ACCOUNTS =
            Map.of(
                new IdentityKey(ISSUER_A, "shared-001"),
                new Account("acct-a", true, Set.of("tenant-a")),

                new IdentityKey(ISSUER_B, "shared-001"),
                new Account("acct-b", true, Set.of("tenant-b")),

                new IdentityKey(ISSUER_A, "disabled-002"),
                new Account("acct-disabled", false,
                        Set.of("tenant-a"))
            );

    static SortedSet<String> authoritiesFor(
            VerifiedSaml verified,
            String requestedTenant) {

        // The caller must have verified this identity with
        // real SAML cryptography. This demo does not do that.
        Account account = ACCOUNTS.get(
                new IdentityKey(
                        verified.issuer(), verified.subject()));

        TreeSet<String> granted = new TreeSet<>();
        if (account == null || !account.enabled()
                || !account.activeTenants()
                        .contains(requestedTenant)) {
            return granted;
        }

        List<String> externalGroups =
                verified.attributes().getOrDefault(
                        GROUP_ATTRIBUTE, List.of());

        // Exact allowlist: unknown groups grant no authority.
        for (String externalGroup : externalGroups) {
            if (externalGroup == null || externalGroup.length() > 256) {
                continue;
            }
            Set<String> approved = ALLOWLIST.get(
                    new MappingKey(verified.issuer(),
                            requestedTenant, externalGroup));
            if (approved != null) {
                granted.addAll(approved);
            }
        }
        return granted;
    }

    public static void main(String[] args) {
        VerifiedSaml alice = new VerifiedSaml(
                ISSUER_A,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers",
                        "grp:finance-approvers",
                        "grp:external-superadmin")));

        VerifiedSaml bob = new VerifiedSaml(
                ISSUER_B,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        VerifiedSaml unknownGroup = new VerifiedSaml(
                ISSUER_A,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of("ROLE_SUPER_ADMIN")));

        VerifiedSaml noGroups = new VerifiedSaml(
                ISSUER_A, "shared-001", Map.of());

        VerifiedSaml unknownIssuer = new VerifiedSaml(
                "https://idp-rogue.example.org/metadata",
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        VerifiedSaml disabled = new VerifiedSaml(
                ISSUER_A, "disabled-002",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        System.out.println("A allowed: "
                + authoritiesFor(alice, "tenant-a"));
        System.out.println("B allowed: "
                + authoritiesFor(bob, "tenant-b"));
        System.out.println("A into B: "
                + authoritiesFor(alice, "tenant-b"));
        System.out.println("B into A: "
                + authoritiesFor(bob, "tenant-a"));
        System.out.println("Unknown group: "
                + authoritiesFor(unknownGroup, "tenant-a"));
        System.out.println("Missing groups: "
                + authoritiesFor(noGroups, "tenant-a"));
        System.out.println("Unknown issuer: "
                + authoritiesFor(unknownIssuer, "tenant-a"));
        System.out.println("Disabled account: "
                + authoritiesFor(disabled, "tenant-a"));
    }
}
~~~

Run on Java 17+:

~~~bash
javac SamlGroupAllowlistDemo.java
java SamlGroupAllowlistDemo
~~~

**Exact stdout:**

~~~text
A allowed: [TENANT_A_REPORT_APPROVE, TENANT_A_REPORT_READ]
B allowed: [TENANT_B_REPORT_READ]
A into B: []
B into A: []
Unknown group: []
Missing groups: []
Unknown issuer: []
Disabled account: []
~~~

### Why Does It Produce This Output?

- A has two approved groups → two authorities, sorted lexicographically by `TreeSet`.
- `grp:external-superadmin` is not in the allowlist → does not become admin.
- B has the same group ID string as A but a different issuer → B receives only `TENANT_B_REPORT_READ`.
- A requesting tenant B / B requesting tenant A → blocked due to lacking local active membership.
- `ROLE_SUPER_ADMIN` sent by the IdP is not in the allowlist → grants no permissions.
- Missing attribute → no permission.
- Unknown issuer with the same subject text as A → maps to no account.
- Disabled account → grants no permissions.

### Limitations of the Demo

1. `VerifiedSaml` is an **already-verified assumption**; this code **does not parse XML, verify signatures, or validate IdP trust**.
2. Account/group policy maps are hardcoded for learning; production uses a governed DB/config with transactions, cache invalidation, and audits.
3. The code demonstrates only tenant-level permissions, without object-level ACLs.
4. `Account.activeTenants` is a snapshot, with no session/token revocation.
5. All demo inputs are Java objects, not raw HTTP requests; never expose a method letting clients supply `issuer`.
6. Returns a mutable `TreeSet` for simplicity; production code should return `Collections.unmodifiableSortedSet` or `Set.copyOf` so callers cannot mutate results.
7. Even when authorities are granted, endpoints must still verify the active account, resource owner, and tenant scope.

## 15. Moving from Demo to `SimpleGrantedAuthority`

In Spring Security, convert allowlisted internal strings to `GrantedAuthority`:

~~~java
import java.util.Set;
import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Collection<? extends GrantedAuthority> convertApproved(
        Set<String> internalAuthorities) {
    return internalAuthorities.stream()
            .map(SimpleGrantedAuthority::new)
            .toList();
}
~~~

The snippet belongs inside an appropriate class, without a standalone `main`. The **most important factor** is not `.map(SimpleGrantedAuthority::new)`, but that `internalAuthorities` came from an exact allowlist **after verified SAML trust + local membership**.

### Never Do This

~~~java
// Anti-pattern: IdP group string becomes ROLE_...
for (String externalGroup : groupsFromSaml) {
    authorities.add(
            new SimpleGrantedAuthority("ROLE_" + externalGroup));
}
~~~

If the IdP emits `ADMIN`, `SUPERUSER`, or an unexpected string, the code can mint unapproved privileges—especially dangerous if the app has routes guarded by `hasRole('ADMIN')`.

### Never Use `contains("admin")`

~~~java
// Anti-pattern: substring-based authority granting
if (group.toLowerCase().contains("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Strings like `not-an-admin`, `external-admin`, `helpdesk-admin`, and `admin-readonly` do not share the same semantics. Authorities must come from **exact group ID keys and approved policy**, never from name heuristics.

## 16. Checking `hasAuthority` at Endpoints and Object ACLs in Services

If an app controls document reads per tenant, a coarse guard:

~~~java
@PreAuthorize("hasAuthority('TENANT_A_REPORT_READ')")
public Report getReport(String id) { ... }
~~~

only proves the user holds an authority; it does not prove report `id` actually belongs to tenant A or falls within the user's readable scope.

Safer design:

~~~java
@PreAuthorize("@reportAccess.canRead(authentication, #tenantId, #reportId)")
public Report read(String tenantId, String reportId) {
    return reportRepository
            .findByTenantIdAndId(tenantId, reportId)
            .orElseThrow();
}
~~~

This is a **Spring application snippet**, where:
- `reportAccess` is an application-implemented bean; the method must verify `Authentication`, active account status, tenant membership, current authorization policy, and object ACL.
- `reportRepository` must query by `tenantId` and `reportId` rather than finding globally by ID and filtering in the frontend.
- `@EnableMethodSecurity` must be enabled.
- Return HTTP 403 or 404 per privacy contract, never leaking cross-tenant data.
- Never let users tamper with the `tenantId` path variable while relying on an authority from another tenant.
- Check APIs, GraphQL, batch exports, file downloads, search indexes, and background jobs—not only controllers.

### When a System Has Thousands of Tenants

You do not need to mint `TENANT_X_*` authorities for every tenant in the session. You can keep permissions like `REPORT_READ`, while **every object decision** reads the trusted current tenant context and checks active membership. This article uses tenant-qualified strings to illustrate scoping; production can adopt a policy engine/ABAC/relationship-based authorization rather than generating unbounded `GrantedAuthority` strings.

## 17. Disabled Accounts or Missing Membership

Do not check only:
- Group `grp:finance-readers` is present;
- IdP is cryptographically trusted.

You must also verify:
- App-local account mapping is active;
- Not suspended/deleted/locked/offboarded;
- Tenant is active and membership is active;
- Target resource belongs to that tenant;
- Permission has not been revoked under the current local policy version;
- Local security state can override an IdP group claim;
- An employee in the group may still be blocked by legal hold/separation of duties;
- Never auto-create a privileged local account just because an admin group appeared.

On `unknown subject` or `missing group`, policy may either:
- Allow login with baseline `ROLE_USER` while **granting zero business permissions**;
- Or reject login/onboarding when the app requires pre-provisioning.

Either way, **never default to granting read access to everything**.

## 18. Business Roles and Segregation of Duties

In financial systems, `REPORT_READ` and `REPORT_APPROVE` may need separation:
- An approver cannot approve records they created.
- `PAYMENT_CREATE` and `PAYMENT_APPROVE` cannot reside on the same account if policy forbids it.
- `USER_MANAGE` and `AUDIT_DELETE` require distinct approvals.
- A tenant admin is not automatically a platform super admin.
- External directory groups express membership only, not workflow-specific approvals.

A group allowlist may grant a **candidate permission**, while ABAC/resource-level checks still make the final decision. For example, an account holding `TENANT_A_REPORT_APPROVE` still cannot approve a report it authored itself.

### System Admin Is a Separate Boundary

Recommendations:
- Have no `externalGroup=Admins → ROLE_SUPER_ADMIN` entry in generic SAML mappings.
- Grant global admin via internal IAM/PAM/local approval with MFA/step-up.
- If business rules strictly require delegating global admin via an IdP, use a dedicated issuer/group ID, dual control, time-bound grants, and separate approvals/audits.
- Never grant permissions based on role strings invented by an external partner IdP.
- Negative tests must prove unknown `ROLE_ADMIN`/`SuperAdmins` do not alter privileges.

## 19. Missing, Excessive, or Malformed Group Values

Abnormal cases:
- `groups` attribute is absent;
- Attribute has an empty list;
- Attribute contains `null`, binary, or XML objects instead of strings;
- List contains duplicate group IDs;
- Case mismatch (`grp:Finance-Readers` vs. `grp:finance-readers`);
- DisplayName/renamed group replacing the old ID;
- 10,000 group values (group overage);
- Attribute Names sharing a FriendlyName yet having different NameFormats;
- Signed response containing multiple assertions where the mapper reads only the verified subset;
- SAML AttributeValue containing nested XML outside the contract.

**Rules:**
- Approved group absent → do not grant the corresponding permission.
- Never auto-create roles from unknown values.
- On invalid input types, fail closed and classify the error per policy; never call arbitrary `toString()`.
- Duplicate values do not add extra privileges.
- Enforce size/count limits and fail/deny cleanly when exceeding resource limits.
- On group overage/claims truncation, never treat "did not receive admin group" as a reason to call an arbitrary directory API and blindly trust it; if supplemental group lookup is required, use dedicated service credentials, an IdP contract, response binding, authorization, and auditing.
- Never grant broad permissions to "help users when the IdP omits groups".

### Group Overage Is Not a Wildcard

Some enterprise IdPs cap the number of groups embedded in a token/assertion. A system may emit a product-specific reference mechanism or group overage indicator. This is not a universal standard across all SAML IdPs. When groups are missing, **fail closed on permissions**, log a structured indicator, and use a supported integration if approved.

## 20. IdP A and IdP B Sharing the Same Group Name

Example:
- IdP A (`corp-a`) has group `Finance`.
- IdP B (`partner-b`) also has group `Finance`.

You cannot infer that both groups carry the same permissions.

| Issuer | Group | Tenant | Permission |
| --- | --- | --- | --- |
| IdP A | `Finance` | tenant-a | `TENANT_A_REPORT_READ` if allowed by policy |
| IdP B | `Finance` | tenant-b | `TENANT_B_REPORT_READ` if allowed by policy |
| IdP B | `Finance` | tenant-a | Do not grant |
| Unknown IdP | `Finance` | tenant-a | Authentication failure / no account |
| IdP A | `SuperAdmins` | tenant-a | Do not grant unless approved |
| IdP A | `Finance` | tenant-a when account disabled | Do not grant |

Common bug: a global `Map<String,String>` mapping `Finance → ROLE_FINANCE_ADMIN`. That allows a partner IdP to grant internal privileges simply via matching group text. **The allowlist must be scoped by issuer/trust + tenant**, and role usage must be scoped by object access.

## 21. Colliding `NameID`, Colliding Emails, and Identity Binding

Two distinct IdPs can emit:
- The same NameID `"alex"`;
- The same email `"alex@example.org"`;
- The same group `"grp:finance-readers"`.

That does not prove the same account. When mapping:
1. Resolve the verified SAML `RelyingPartyRegistration`.
2. Extract the subject identifier per the IdP contract.
3. Build an external identity key scoped by issuer/NameID qualifiers/format.
4. Look up the immutable `appAccountId`.
5. Verify the local account is active.
6. Verify active tenant membership.
7. Look up the group allowlist by IdP/tenant/attribute/group ID.
8. Grant specific authorities; never auto-merge accounts.
9. When linking identities is required, require verified proof + audit.
10. When an email is reused after offboarding, never restore old grants by email.

**External group mapping must never be used as implicit account linking.** Group membership and subject identity have different meanings.

## 22. Updating Permissions When Groups Change

SAML login normally grants authorities into the session at login time. The IdP may change memberships **afterward**, while the app-local session still holds the old `Authentication`.

Example:
- 09:00 login, group `grp:finance-approvers` grants `REPORT_APPROVE`.
- 09:10 admin removes the user from the group.
- 09:11 browser still carries the Spring session holding the earlier authorities.
- 09:15 user attempts to approve a transaction.

If the app trusts only the 09:00 authority snapshot, revocation can lag until session expiry or reauthentication. Technical requirements:
- Define a **revocation SLA**.
- Enforce a current local account/permission gate on sensitive actions.
- Invalidate/expire sessions when IdP group changes arrive via SCIM/LDAP/events or admin actions.
- Store `policyVersion`/`securityEpoch` in the session and compare against the DB.
- Shorten session lifetimes / force reauthentication for elevated privileges.
- When mapping policy changes, invalidate/refresh affected sessions.
- If SAML Single Logout is used, **do not assume SLO guarantees all local sessions/API tokens are revoked** unless implemented.
- Across multiple nodes, revocation state must be shared/consistent.

### Do Not Keep Stale Roles in Cache

- Cache keys should include `accountId`, `tenantId`, and `policyVersion` or `securityEpoch` where applicable.
- Never cache `ROLE_ADMIN` globally keyed only by email/username.
- Never use long-lived `@Cacheable` group mappings without invalidation.
- Retries or out-of-order events must not resurrect old grants.
- Audit authorization decisions against the active source/policy version.

## 23. SCIM, LDAP, or HR Provisioning Alongside SAML

Many organizations sync group memberships via SCIM or LDAP. In that setup:
- SAML assertions authenticate the user at login.
- SCIM/LDAP/HR supplies entitlement data or account state per policy.
- The app still needs **provenance**: which source is authorized to grant group/tenant permissions.
- SCIM `externalId` is scoped per provisioning client; never apply it globally without source scoping.
- Group `displayName` can change and is not always a stable ID.
- Group removal/revocation events require idempotency and ordering.
- If SAML and SCIM disagree, choose a **source of truth** per security policy rather than blindly unioning permissions.
- Never let a partner IdP self-provision system-wide permissions via group assignments.
- When an identity is disabled, local policy must deny even if the SAML assertion has a valid signature.

### Should You Query LDAP on Every Request?

Depends on latency, availability, and SLA. Options include:
1. Login-time group snapshot only + short session lifetime.
2. Session snapshot combined with periodic refresh.
3. Locally materialized membership from SCIM/events plus a live gate on every critical action.
4. Live directory/entitlement lookup with protected caching and fail-closed deny for privileged actions.

There is no single universal choice. Choose based on target revocation latency, availability, regulatory requirements, and threat model.

## 24. Auditing: Explaining Why Access Was Granted or Denied

An audit record may include:
- Opaque `traceId`;
- Approved `registrationId` alias;
- Internal `accountId`;
- `tenantId`;
- `policyVersion`;
- `matchedMappingCount`;
- `grantedAuthorityNames` if classification permits;
- `decision`;
- `source` type (`verified-saml` / `local-grant`);
- `reasonCode` such as `NO_ALLOWLIST_MATCH`, `ACCOUNT_DISABLED`, `TENANT_NOT_MEMBER`.

Minimized event example:

~~~json
{
  "event": "saml_authority_mapping",
  "traceId": "opaque-trace-123",
  "registrationAlias": "corp-a",
  "accountRef": "acct-a",
  "tenantRef": "tenant-a",
  "policyVersion": "v12",
  "matchedMappingCount": 2,
  "unknownGroupCount": 1,
  "result": "MAPPED"
}
~~~

**This is an application-designed schema**, not a default Spring event. Never log raw SAML Responses, XML, attributes containing sensitive data, private keys, session IDs, or tokens. Group IDs can also reveal org structure; when direct logging is unnecessary, log only counts and categorical reasons.

### Useful Metrics

- `saml_group_mapping_success_total{registration,tenant}`
- `saml_group_mapping_unknown_groups_total{registration}`
- `saml_group_mapping_rejected_total{reason}`
- `saml_group_policy_version{cluster}`
- `saml_active_account_denials_total`
- `saml_tenant_permission_denied_total`
- `saml_privileged_grants_total`
- `saml_group_mapping_latency_seconds`

Avoid high-cardinality labels using raw userName/NameID/email/group IDs; use controlled enumeration aliases.

## 25. Unit Testing the Mapper with Collision Cases

Unit testing mapper logic **does not require** real SAML XML, yet tests must state their exact scope.

Core cases:

| ID | Verified Input | Expected |
| --- | --- | --- |
| U01 | IdP A, tenant A, reader group | `TENANT_A_REPORT_READ` |
| U02 | IdP A, tenant A, approver group | `TENANT_A_REPORT_APPROVE` |
| U03 | IdP A, multiple groups reader+approver | Both, no duplicates |
| U04 | IdP A, unknown group | No authority addition |
| U05 | IdP A, group `ROLE_ADMIN` | No admin |
| U06 | IdP A, group `Admin` | No admin |
| U07 | IdP B, same group text as A | B mapping only |
| U08 | IdP B with tenant A | No authority |
| U09 | User A no longer has tenant membership | No authority |
| U10 | Disabled user | No authority |
| U11 | Missing groups attribute | No authority |
| U12 | Empty attribute list | No authority |
| U13 | Duplicate group values | No duplicate authorities |
| U14 | Unsupported attribute value type | Reject/ignore per policy |
| U15 | NameFormat/FriendlyName differs from contract | Does not mismap |
| U16 | Whitespace/case variant | Does not auto-match if contract is exact |
| U17 | Long/oversized group ID | Not processed beyond limit |
| U18 | Local group policy registry unavailable | Fail closed per policy |
| U19 | Unknown identity / colliding NameID from another IdP | Does not resolve to account A |
| U20 | Mapping config version changed | Session/permissions refresh properly |

**U01–U20 test mapping logic**, not XML signature/issuer/audience verification. Never call a test using only mocked attributes a "SAML verifier test".

## 26. Real SAML Integration: Do Not Mock the Provider When Testing Trust Boundaries

A proper integration test should:
1. Run the real Spring `SecurityFilterChain` and SAML ACS filter.
2. Have a separate trusted test IdP signing certificate per registration.
3. Have the test IdP build a **validly signed SAMLResponse/Assertion** carrying group AttributeStatements per contract.
4. Use the exact SP entity ID, ACS Recipient/Destination, AudienceRestriction, and timestamps.
5. Preserve InResponseTo/RelayState when testing SP-initiated SSO.
6. Route the response through the real `AuthenticationManager`/OpenSAML provider.
7. After verification, assert the exact authorities granted per the allowlist.
8. Request protected routes verifying `hasAuthority` and object ACLs.
9. Negative signed fixtures with wrong group/issuer/tenant grant zero permissions.
10. Never treat HTTP 302 alone as proof of successful login.

### Integration Matrix

| ID | Scenario | Assertion Required |
| --- | --- | --- |
| I01 | A signed response, approved reader group | Login OK, READ only |
| I02 | A signed response, reader+approver | Login OK, READ+APPROVE |
| I03 | A signed response, unknown admin group | No ADMIN |
| I04 | A signed response, no groups | Authenticated per policy, no business permission |
| I05 | B signed response, same group ID as A | B mapping only |
| I06 | B signed response POSTed to ACS A | Authentication fails (trust/issuer) |
| I07 | Unsigned/modified SAML Response with admin group | Authentication fails |
| I08 | Wrong audience with valid signature | Authentication fails |
| I09 | Wrong recipient/time with valid signature | Authentication fails |
| I10 | Valid SAML A with disabled local account | Reject / no business permission |
| I11 | Valid SAML A with tenant membership removed | Deny tenant resource |
| I12 | Valid SAML A with multi-value attribute | Exact allowlisted union |
| I13 | Two assertions, malicious extra group in unverified assertion | No unverified authority |
| I14 | EncryptedAttribute containing groups | Decrypt/validate then map |
| I15 | IdP group removed, stale session | Revoke/deny within SLA |
| I16 | Two tenants sharing IdP, same group text | No cross-tenant grants |
| I17 | Multiple nodes with policy version drift | Detect / fail safe |
| I18 | Known group with changed displayName | Correct ID-based mapping |
| I19 | Attribute Name/FriendlyName collision | Approved Attribute Name only |
| I20 | Global super admin attempted via group name | Denied by policy |

### Negative Semantic Tests Must Preserve Valid Signatures

This point is often missed:
- If you edit group XML **after signing**, the signature breaks.
- The test then fails in the Signature Validator and **does not prove** the allowlist works.
- To test unknown groups, construct the fixture with the unknown group and then **sign it with the trusted test IdP key**; keep other fields valid.
- Positive controls must log in successfully with the same IdP and local account.
- For wrong issuer/recipient/audience, sign the corresponding fixture properly to isolate the exact rule.

Never disable signature verification to make a group-mapping test pass. The mapper sits downstream of cryptographic verification.

## 27. MockMvc / `@WithMockUser` Suits AuthZ Checks, Not SAML Trust

Example inside a Spring Boot project:

~~~java
@Test
@WithMockUser(
        username = "acct-a",
        authorities = "TENANT_A_REPORT_READ")
void userCanReadTenantAReport() throws Exception {
    mvc.perform(get("/tenants/tenant-a/reports/report-1"))
            .andExpect(status().isOk());
}
~~~

Prerequisite: the project has the endpoint, test data, authorization rules, and Spring Security Test. This is **not a standalone class**. `@WithMockUser` injects a synthetic user/authority into SecurityContext; **it bypasses XML Signature, IdP trust, and the group attribute converter**.

A valid negative test:

~~~java
@Test
@WithMockUser(
        username = "acct-a",
        authorities = "TENANT_A_REPORT_READ")
void cannotReadTenantBReport() throws Exception {
    mvc.perform(get("/tenants/tenant-b/reports/report-2"))
            .andExpect(status().isForbidden());
}
~~~

It may return 404 under a resource-hiding policy; adjust assertions to the contract. Ensure `report-2` **actually exists in tenant B**, user A is authenticated, and A lacks tenant B membership; if the resource does not exist, 404 does not prove the tenant ACL.

### Separating Two Kinds of Evidence

- Unit/MockMvc: "If a user holds `TENANT_A_REPORT_READ`, does the backend block tenant B?"
- Signed SAML provider/integration: "When IdP A presents a verified reader group, does the mapper grant only `TENANT_A_REPORT_READ`?"
- Browser E2E: "Do metadata/ACS/cookies/RelayState/IdP work end-to-end and does the real session hold the right authorities?"

Never conflate all three conclusions in one test using a fake principal.

## 28. Approval Permissions and Object-Level Access

Suppose `TENANT_A_REPORT_APPROVE` is among the authorities. You still must:
- Verify the report belongs to tenant A.
- Verify the report is in a pending-approval state.
- Ensure the approver is not the creator if separation-of-duties requires it.
- Verify limits/ownership/workflow stage.
- Re-check active account and current roles when revocation SLA is tight.
- Refuse approval of a canceled report merely because the role remains valid in the session.
- Audit action, tenant, object ID, policy source, and timestamp.
- Never trust a client request parameter `approved=true` to bypass policy.

**Authorities are an input to authorization, not the final verdict on every resource.**

## 29. Concurrency and Configuration-Race Testing

Rare yet impactful scenarios:
1. Two logins for the same subject occur while group policy is being updated.
2. One node runs policy version v12 while another runs v13.
3. A SCIM remove event and a login callback arrive concurrently.
4. An account is disabled after assertion verification yet before session commit.
5. User A in one tab and B in another share a browser session, mutating principal/tenant context.
6. Group mapping is rolled back after an incident while old sessions still hold v13 roles.
7. Group IDs are reused after directory recreation.
8. A stale Redis cache snapshot is restored after an outage.
9. Local membership is revoked while a scheduled export job continues running.
10. An oversized group attribute list exhausts mapper resources.

### Mitigations

- Immutable policy version per decision or atomic config reload.
- Rollout/health checks verifying all nodes run the same policy version.
- Account security epoch + permission cache invalidation.
- Revalidate sensitive actions at the business boundary.
- Stable group IDs and directory namespaces.
- Deny on unknown state/config conflict per threat model.
- Audit mapping decisions for root-cause analysis.
- Resource queries always use trusted tenant context.
- Test concurrency and eventual-consistency revocation against a clear SLA.
- Never mix anonymous/default permissions with elevated mapped authorities.

## 30. Choosing Where to Enforce Mapping: Converter or Downstream Policy?

| Location | Pros | Risks / Checks Needed |
| --- | --- | --- |
| SAML `ResponseAuthenticationConverter` | Authorities available immediately after login | Must preserve provider defaults, SLO accessor, and account checks |
| `AuthenticationSuccessHandler` | Access to session/HTTP context | Improperly mutating SecurityContext can lose persisted auth |
| Local account / user-details service | Combines SCIM/DB/current grants | Needs exact issuer+subject mapping; latency/cache |
| Custom authorization service per request | Fast permission updates, strong object ACL | Must optimize performance and availability |
| External policy engine | Separates policy and audit | Fail-closed, latency, trust boundary, tenant scope |
| Internal JWT minting after SAML | Convenient across microservices | Authorities stale until expiry/revocation; token audience |
| Gateway mapping | Centralizes mapping | Must not skip resource-level checks; trusted identity propagation |

**Never place all protection in the frontend/UI.** Even when the mapper emits exact authorities, the API/resource service must independently verify permissions and tenant/object ownership. A trusted gateway still does not replace backend object-level ACLs.

### If Minting a Local JWT After SAML

- Mint the JWT only after verified SAML login + allowlist mapping + active account.
- Claim `sub` should be the stable app account ID, not an unscoped email/NameID.
- `iss` is the app issuer and `aud` targets the right microservice.
- `scope/roles/tenant` are issued by app policy; never copy raw SAML groups into privileges.
- JWT TTL/refresh/revocation policy must match privileged-action SLAs.
- Backend Resource Servers verify signature, issuer, audience, expiry, and account/tenant state.
- If a user leaves a group, existing JWTs may remain valid until expiry unless a revocation gate exists.

## 31. Protecting Mapping Policy Against Partner IdP Actions

In multi-IdP B2B:
- A partner IdP can assign its users to any group in **its own directory**.
- That is administrative control on their side, not authority to grant admin on your tenant A.
- Mapping must define **which IdP/tenant is delegated which permissions**.
- With tenant-local self-service, a tenant admin may edit mappings for their own tenant without modifying global/system roles.
- Every change to privileged mappings requires local security review/approval.
- Never let an auto-discovered `"Admins"` group become app admin by heuristic.
- Enforce quotas, rate limits, and audits when an IdP repeatedly sends unknown group values.
- If an external group disappears from metadata or the directory, do not retain old grants indefinitely.
- Explicit deny rules or absence from the allowlist should take precedence over default grants.

**If an IdP is compromised:** a signed SAML Response may carry attacker-controlled groups **and still have a valid signature**. The signature proves the IdP emitted the attributes; the **allowlist** bounds the permissions delegated to that IdP. Still, if an allowlisted group holds high privilege, a compromised IdP can assert that group; use PAM/approvals/dual control for critical privileges.

## 32. Pre-Release QA Checklist

- [ ] `RelyingPartyRegistration` points to the exact IdP issuer, ACS, SP entity ID, and trusted verification credentials.
- [ ] SAML signature, issuer, audience, recipient, conditions, and InResponseTo validation remain intact.
- [ ] EncryptedAttributes (if used) are decrypted/verified before mapping.
- [ ] Attribute Name, NameFormat, value type, and data contract are confirmed with the IdP.
- [ ] Use **List values**, not just `getFirstAttribute()`, for multi-valued groups.
- [ ] Group identifiers are stable; do not rely on displayName/email when trusted IDs exist.
- [ ] Allowlist is keyed by IdP registration/issuer, tenant, attribute, and external group ID.
- [ ] Authorities are never generated dynamically from group names or prefixes from the IdP.
- [ ] `ROLE_ADMIN`/`SUPER_ADMIN` are never auto-granted from unknown groups.
- [ ] `hasAuthority`/`hasRole` rules and the `ROLE_` prefix are consistent.
- [ ] Default `ROLE_USER` never opens sensitive endpoints.
- [ ] Unknown/empty/malformed groups grant no permissions outside the allowlist.
- [ ] Duplicate group values do not duplicate authorities.
- [ ] Group overage/unsupported value types have a fail-closed policy.
- [ ] External identity links by issuer/subject/qualifiers, not email alone.
- [ ] Local app account ACTIVE status and tenant membership are verified before granting.
- [ ] Object-level resource ACLs are enforced in services/repositories.
- [ ] Mapping policy has an owner, change review, versioning, audit, and rollback.
- [ ] Permission cache/session invalidation meets the revocation SLA.
- [ ] Custom converter preserves `Saml2AssertionAuthentication` accessor/SLO behavior on Spring 7 if applicable.
- [ ] 6.x→7.x migration updated deprecations and APIs.
- [ ] Unit tests cover colliding group IDs across two IdPs, unknown admin groups, missing attributes, and disabled accounts.
- [ ] Provider/integration tests use **signed** fixtures; invalid-group tests still carry valid signatures.
- [ ] MockMvc `@WithMockUser` tests are not reported as SAML verifier tests.
- [ ] Tenant B resources exist and B sessions are valid in negative cross-tenant tests.
- [ ] Multi-node policy version consistency and group removal/session staleness are tested.
- [ ] Logs/metrics contain no raw SAML Responses, credentials, or PII.
- [ ] System admin grants have separate governance and are not auto-mapped from group names.
- [ ] Tests cover allow/no-allow, content parity, multi-valued groups, and request-time AuthZ.
- [ ] Browser SSO E2E runs against a real/staging IdP with accurate metadata/ACS/cookies.
- [ ] Runbook exists for IdP group renames, Attribute Name changes, or signing certificate rotation.

## 33. Review Questions and Answers

**Q1.** Should a SAML group `"ROLE_ADMIN"` automatically become `ROLE_ADMIN`?

**Answer:** No. An application-managed exact allowlist and scope/privileged-grant review are required.

**Q2.** Does a valid SAML signature prove the `"Admins"` group is authorized to be global admin?

**Answer:** No. The signature proves the IdP emitted the group, but the application decides delegated permissions.

**Q3.** Why avoid `getFirstAttribute("groups")` when groups are multi-valued?

**Answer:** It returns only one group and drops the rest; read `getAttribute()` / the attributes list and map all values per contract.

**Q4.** Does group name `"Finance"` from two IdPs mean the same permissions?

**Answer:** No. It must be scoped by issuer/registration/tenant and group ID.

**Q5.** Are `hasAuthority("TENANT_A_REPORT_READ")` and `hasRole("TENANT_A_REPORT_READ")` identical?

**Answer:** Not by default. `hasRole` usually prepends `ROLE_`, whereas `hasAuthority` performs an exact match.

**Q6.** If the `groups` attribute is missing, should `ROLE_REPORT_VIEWER` be granted for convenience?

**Answer:** No, unless policy defines an independent grant rule. Missing groups → do not grant the corresponding permission.

**Q7.** Can a partner emitting `"SuperAdmins"` access the system admin API?

**Answer:** No; the allowlist and local security governance must protect global/system roles.

**Q8.** A SAML group DN contains commas—should it be split on commas?

**Answer:** No. A DN is a single value; multiple `AttributeValue` elements are processed as a list.

**Q9.** Should an unknown group fail login or simply be ignored?

**Answer:** Depends on policy. However, it must fail closed **on permissions** and never grant them. If the group attribute is mandatory for onboarding, authentication may be rejected.

**Q10.** If a user no longer belongs to tenant A yet still carries reader group A, can they read report A?

**Answer:** No. Local active membership and object ACLs must be checked.

**Q11.** Can `Saml2AuthenticatedPrincipal` be used in Spring Security 7.x?

**Answer:** It may remain for compatibility yet is deprecated; 7.x recommends `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`.

**Q12.** Why avoid arbitrarily constructing a new `Saml2Authentication` on Spring 7.x?

**Answer:** It can discard the assertion accessor/registration metadata needed for SLO or framework behavior; prefer preserving the type produced by the default converter, e.g., via `toBuilder`.

**Q13.** Is the response converter invoked before or after OpenSAML verification?

**Answer:** In the default provider flow, response authentication conversion runs after response/assertion verification/validation steps; never replace it with a custom bypass.

**Q14.** Does a SAML Response whose group was edited after signing prove the allowlist works when rejected?

**Answer:** Not necessarily. It may simply fail signature validation; unknown-group tests must carry a valid signature.

**Q15.** Can email be used as the primary account key for mapping?

**Answer:** It should not. Email is mutable and can collide/be reused; use an issuer-scoped external identity and stable `appAccountId`.

**Q16.** Is default `ROLE_USER` sufficient to read all reports?

**Answer:** No. Business routes must verify explicit permissions and tenant/resource ownership.

**Q17.** Should groups `"admin"` and `"Admin"` be treated as identical?

**Answer:** Only if a normalization contract is explicitly defined and policy-approved; never blindly lowercase because it can cause collisions.

**Q18.** Do duplicate group values create duplicate permissions?

**Answer:** No; deduplicate using a `Set`, and never grant beyond the allowlist.

**Q19.** Can a tenant A admin view tenant B because of an identical group ID?

**Answer:** No. Tenant membership, group mapping, and object ACLs are scoped separately.

**Q20.** Immediately after an admin removes a group at the IdP, does an existing SAML session automatically lose the permission?

**Answer:** No. You need a revocation strategy, session expiry/re-authentication, policy refresh, or a local account gate meeting your SLA.

**Q21.** Does `@WithMockUser` prove a signed SAML group attribute was verified?

**Answer:** No. It populates a synthetic SecurityContext; provider integration with signed fixtures is required.

**Q22.** Can `ROLE_REPORT_VIEWER` be granted from unverified SAML?

**Answer:** No. Never read raw client-supplied XML and grant permissions.

**Q23.** Why audit `policyVersion`?

**Answer:** It explains why authorities were granted at login time and aids investigation during mapping changes or node drift.

**Q24.** If the IdP is compromised, does an allowlist completely neutralize every attack?

**Answer:** No. It bounds what permissions are delegated to the IdP, yet approved groups can still be abused; use governance/MFA/PAM for high privileges.

**Q25.** Why does a route guarded by `hasAuthority` still need a resource ACL?

**Answer:** An authority is only a coarse permission; access to a specific object depends on tenant, owner, workflow state, and current policy.

**Q26.** Why not write a single global `Map<String,String>`?

**Answer:** It fails to distinguish IdP issuer/registration, tenant, or attribute contract, letting identical group text grant cross-context permissions.

**Q27.** When the IdP changes `FriendlyName`, should the mapping automatically switch attribute keys?

**Answer:** No; use the agreed `Attribute Name`, verify `NameFormat`, and manage changes with migration/versioning.

**Q28.** When the policy database is temporarily unreachable, may the app grant every permission seen in the assertion?

**Answer:** No. Fail closed per policy and follow retry/incident runbooks; never bypass the allowlist.

**Q29.** Do we still need to verify IdP signing certs/metadata when the task is only about groups?

**Answer:** Yes, because groups are trustworthy only after SAML validation against the right asserting party.

**Q30.** Does demo output `Unknown group: []` prove Spring SAML2 is secure?

**Answer:** Not yet. It proves only the pure Java algorithm assuming verified inputs, not signed integration tests.

## 34. Runbook When a User Can Log In Yet Has No Permissions

**Step 1 — Separate AuthN vs. AuthZ.** Did SAML login succeed and create `Authentication`? If signature/issuer/audience/time failed, it is not a group-mapping bug.

**Step 2 — Check exact registration.** Did the user arrive from the right IdP/tenant? Do metadata and certificates match?

**Step 3 — Check attribute contract.** Exact `Attribute Name`, `NameFormat`, list value type? Any encrypted attributes or group overage? Inspect only redacted data.

**Step 4 — Check identity binding.** Did NameID/issuer map to the right `appAccountId`? Is the account ACTIVE? Is tenant membership active?

**Step 5 — Check allowlist.** Are the exact group IDs in the active mapping? Which policy version and approval? Was a group renamed or recreated?

**Step 6 — Check security context.** Are the post-login authorities in the allowed set? Do `hasRole`/`hasAuthority` use consistent prefixes?

**Step 7 — Check resource ACL.** Does the user have access to the specific tenant/report/action? Does the object exist and match policy?

**Step 8 — Check cache/session.** Was the user just added/removed from a group? Does the session hold an old snapshot? Is policy cache invalidation working?

**Step 9 — Check consistency.** Do all pods/regions run the same policy version and IdP trust config?

**Step 10 — Fix root cause.** Fix policy or the IdP attribute contract via change control; never temporarily grant `ROLE_ADMIN` or enable wildcard mappings just to let the user in.

**Step 11 — Regression.** Run positive, unknown-group negative, privileged-group negative, cross-IdP/cross-tenant signed fixtures, and object ACL tests.

**Step 12 — Monitor.** Track auth successes, mapping unknown-group counts, denials, and privilege changes without leaking PII/raw SAML.

## 35. Summary

**Safe mapping of SAML groups to internal authorities is a trust-bounded authorization problem:**

1. **Use only attributes from a provider-verified SAML Response.** SAML signatures prove origin and integrity within configured trust; they never auto-grant permissions.
2. **Use an exact allowlist namespaced by IdP/registration, tenant, and attribute contract.** Never map group strings by prefix, wildcard, contains, or arbitrary display names.
3. **Grant exact approved `GrantedAuthority` values.** `hasAuthority` matches exactly; `hasRole` follows the `ROLE_` convention.
4. **Verify local account ACTIVE status, tenant membership, and resource ACLs.** An allowed group does not automatically grant tenant-wide or system-admin access.
5. **Handle all group values, unknown/duplicate/missing values, and typed attributes.** Unknown groups must generate zero authorities.
6. **Preserve Spring Security provider verification and SAML accessor/SLO structures when customizing converters.** Cross-check Spring 6.x/7.x APIs.
7. **Test both AuthN and AuthZ with signed fixtures and local ACL cases.** Mock principals are useful but are not proof of SAML signatures.
8. **Enforce governance, auditing, revocation, and cache/session refresh.** Removed groups must not leave permissions active indefinitely in sessions.

A compliant exercise must prove that IdP A grants **only** delegated permissions, IdP B with identical group strings cannot hijack A's privileges, and an account lacking membership or disabled locally cannot bypass ACLs even with a validly signed SAML assertion.

### Official and Security References

1. Spring Security — Authenticating SAML Responses; `OpenSaml5AuthenticationProvider`, response authentication converter, principal, authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
2. Spring Security — SAML2 Login Overview, verification flow and default authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
3. Spring Security — SAML2 Migration 7, `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor`: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
4. Spring Security — `Saml2AuthenticatedPrincipal` API, multi-value attributes/deprecation: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
5. Spring Security — `Saml2AssertionAuthentication` API and builder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
6. Spring Security — `Saml2ResponseAssertionAccessor` API, `getAttributes()`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
7. Spring Security — Method Security and `@PreAuthorize`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
8. Spring Security — Authorization architecture, GrantedAuthority/roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
9. OASIS — SAML 2.0 Core, AttributeStatement/Attributes/NameID: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
10. OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
11. OWASP — Authorization Cheat Sheet, least privilege/deny-by-default/check every request: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
12. OWASP — Insecure Direct Object Reference Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
13. OWASP — Multi-Tenant Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html