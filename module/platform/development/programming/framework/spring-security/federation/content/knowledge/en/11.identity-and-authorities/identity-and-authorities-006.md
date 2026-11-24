# Converting SAML Attributes or Groups into GrantedAuthority with Controlled Mapping

When a Spring Security application uses SAML 2.0 federation, the **Identity Provider (IdP/Asserting Party)** often supplies user attributes in `AttributeStatement`: employee ID, email, department, groups, title, or tenant details. The **Service Provider (SP/Relying Party)** application can use some of those attributes as **inputs** for calculating access permissions. However, the application **must never convert every received group value verbatim into a `GrantedAuthority`**, especially privileged ones like `ROLE_ADMIN` or cross-tenant data access.

**Core principle:** Map only verified attributes from the **right IdP and right registration**, through an **SP-controlled allowlist policy**, combined with user/tenant/resource context and **least privilege**. When a group is unknown, an attribute is missing, the IdP is not authorized to grant that role, or data conflicts, default to **granting no extra permissions**. Successful login does not imply permission to perform every action.

This is a Knowledge lesson under **Spring Security – federation → Identity and authorities**. Content covers the trust model, mapping design, Spring Security APIs, a standalone Java 17 example, SAML response converter integration guidance, sessions/revocation, testing, and troubleshooting.

## 1. Where do authentication and authorization differ?

**Authentication** answers: *Who just logged in, which IdP authenticated them, and is the proof valid?* **Authorization** answers: *Which action may that person perform on which resource, in which tenant, and under what conditions?*

~~~text
User --------> IdP auth --------> SAMLResponse
                                        |
                                   Spring Security
                             verify XML signature,
                              Issuer/Audience/Time,
                             Recipient/InResponseTo
                                        |
                                        v
                            Saml2Authentication
                            + principal / attributes
                                        |
                             SP's policy mapping
                   IdP + registration + tenant + allowlist
                                        |
                                        v
                        Collection<GrantedAuthority>
                                        |
                        AuthorizationFilter / @PreAuthorize
                                        |
                                check resource
~~~

| Concept | Source | Meaning |
| --- | --- | --- |
| Valid `SAML Assertion` | Trusted IdP, verified by SP | Contextual proof of authentication/attributes |
| `Saml2AuthenticatedPrincipal` | Spring Security post-authentication | Principal, NameID, list of read attributes |
| `GrantedAuthority` | Built by SP from policy or entitlement store | A permission Spring Security can evaluate |
| `ROLE_REVIEWER`, `ROLE_ADMIN` | Application permission namespace | Internal role names, not IdP group values by default |
| `hasAuthority` / `hasRole` | Authorization expressions | Ways to require permissions protecting endpoints/methods |
| ACL, ABAC, ownership, and tenant policy | SP business logic | Binds permissions to specific domain objects |

Example: The IdP authenticates user An and sends group `portal-reviewers`. The SP maps this group to `ROLE_APPROVER` **only if the policy for that IdP/tenant permits approval authority**, and when approving an invoice still checks **which tenant the invoice belongs to, its status, and whether An is assigned**.

**Wrong:** believing that a valid IdP signature means every group published by the IdP can become an application admin role. **Right:** trusting the verified identity within the IdP's scope and then applying SP-owned authorization rules.

## 2. Where do SAML attributes come from and what shape do they have?

An assertion can contain multiple `AttributeStatement` elements, each holding one or more `Attribute` elements; an attribute can have multiple `AttributeValue` elements.

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="urn:example:claims:groups"
                  NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                  FriendlyName="groups">
    <saml:AttributeValue>portal-readers</saml:AttributeValue>
    <saml:AttributeValue>portal-reviewers</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:department">
    <saml:AttributeValue>finance</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

This is an **illustrative XML fragment** explaining structure, not a SAML Assertion/Response with valid signatures and conditions. The URI `urn:example:claims:groups` is an **example attribute name**, not a mandatory SAML standard name.

Points to check when aligning integration contracts with an IdP:

1. **`Attribute.Name`** is the attribute identifier; some IdPs use URIs/OIDs, while others use strings like `groups` or `memberOf`.
2. **`NameFormat`** can indicate the naming scheme. Never assume two Attributes with the same FriendlyName but different Name/NameFormat are identical.
3. **`FriendlyName`** is mainly for human readability; do not pick it as a security key if the integration contract specifies Name/OID.
4. **`AttributeValue`** can appear multiple times rather than always as a single string; some providers emit complex-typed values.
5. **Group values** may be display names, internal codes, OIDs, GUIDs, or LDAP DNs such as `CN=PortalReaders,OU=Groups,DC=example,DC=test`.
6. Some IdPs cap assertion size or returned group count; truncated groups will cause permission discrepancies if the app assumes always-complete lists.
7. `AttributeStatement` lives inside the assertion; it is only trustworthy after Spring Security/OpenSAML verifies the SAML message and matching registration.

**Recommendation:** use **stable group identifiers** supplied by the IdP with a clear semantic contract, rather than display descriptions that are easy to rename or collide.

## 3. Reading attributes in Spring Security

With Spring Security SAML2 Login, once `SAMLResponse` is verified, Spring can produce a `Saml2Authentication`. In branches using `Saml2AuthenticatedPrincipal`, the principal holds the name and attribute map.

Example reading attributes in a controller (code fragment inside a **Spring project**, not standalone Java):

~~~java
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/profile/groups")
    public List<Object> groups(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        List<Object> groups =
                principal.getAttribute("urn:example:claims:groups");
        return groups != null ? groups : List.of();
    }
}
~~~

**This only illustrates API access**, not a recommendation to expose a public endpoint returning group claims in production. `getAttribute(name)` returns a **list** of values; `getFirstAttribute(name)` fetches the first value when an attribute is known to be single-valued. When policy needs all groups, **do not take only the first value**.

Version compatibility note: Spring Security 6.x commonly uses `Saml2AuthenticatedPrincipal`; 7.x branches introduce assertion access via `Saml2ResponseAssertionAccessor` and change the default authentication model. Check the Javadoc/source **for your exact version** to read attributes from the right location; do not force every deployment to cast the principal to `Saml2AuthenticatedPrincipal` once upgraded to the newer API.

**Do not map permissions inside the controller example above.** Calculating `GrantedAuthority` belongs centrally at Authentication creation or in an authorization service, rather than letting each controller interpret groups differently.

## 4. GrantedAuthority, hasAuthority, and hasRole

In Spring Security:

- **`GrantedAuthority`** is the interface representing an authority; `getAuthority()` typically returns a string.
- **`SimpleGrantedAuthority`** is the common implementation for string-based authorities.
- **`hasAuthority("document:approve")`** matches the exact authority string.
- **`hasRole("ADMIN")`** by default looks for authority **`ROLE_ADMIN`** because the `ROLE_` prefix is applied. The role prefix mechanism can be customized in a project, so verify actual configuration.
- **`@PreAuthorize`** or an AuthorizationManager protects methods/endpoints with authorities and business conditions.

Example using the same privilege in two ways:

~~~java
@PreAuthorize("hasAuthority('ROLE_APPROVER')")
public void approveUsingAuthority(long paymentId) { /* service logic */ }

@PreAuthorize("hasRole('APPROVER')")
public void approveUsingRole(long paymentId) { /* service logic */ }
~~~

The snippet above shows **two illustrative methods in a service with method security enabled**, not standalone code. Under the default prefix, both expressions express the same role check. Neither **checks ownership/tenant** of `paymentId` yet; production requires pairing with an authorization service or domain policy.

**Never do this:** `new SimpleGrantedAuthority(groupValue)` for every `groupValue` emitted by an IdP, especially when an IdP can emit `ROLE_ADMIN`, `*:* `, or user-chosen internal permission names.

## 5. Threat model: privilege escalation paths

| Risk | Example | Control |
| --- | --- | --- |
| **Group-name collision** | Two IdPs both emit `admins`, yet only A is authorized to grant admin | Map by IdP/registration and tenant, never by global string |
| **Role injection** | An unexpected group is named `ROLE_ADMIN` | Exact allowlist; never let groups dictate authority names |
| **Tenant confusion** | IdP A emits group `finance`, yet the session is in tenant B | Check internal tenant membership and bind registration |
| **Ambiguous mapping** | `Finance`, `finance`, `CN=finance,...` treated identically despite being distinct groups | Use agreed identifiers and controlled normalization |
| **Attribute type confusion** | `AttributeValue` is an XML object yet code casts to String | Accept only defined data types; reject unexpected values |
| **Overprivileged group** | IdP group `all-employees` gets mapped to `ROLE_ADMIN` | Least privilege principle and mapping reviews |
| **Stale group** | User is removed from a group, yet the SP session retains old permissions | Session limits, reauth, refresh, or per-request lookups for sensitive ops |
| **Account linking error** | Matching users solely by mutable email | Use verified stable subject + issuer + tenant mapping |
| **Dynamic tenant URL** | `?tenant=finance` from browser drives role mapping | Tenant must be verified server-side, not just from query params |
| **Upstream IdP transitivity** | A signs attributes forwarded from an out-of-contract secondary IdP | Vet attribute source/assurance and federation policy |
| **Mapping drift** | IdP renames a group while the app maps it to another role | Versioned policy governance, tests, and auditing |

Key takeaway: A SAML signature proves a trusted IdP issued a message; **it does not prove every group value is appropriate to grant application privileges**.

## 6. Designing allowlist-based mapping

Each policy entry should have at least these fields:

| Component | Example | Control |
| --- | --- | --- |
| Registration/IdP | `corp` | Matches verified RelyingPartyRegistration |
| Tenant | `north` | Membership/tenant selection verified by SP |
| Attribute name | `urn:example:claims:groups` | Matches attribute contract |
| Attribute value | `portal-reviewers` | Exact match against approved group ID |
| Target authority | `ROLE_APPROVER` | Application-defined |
| Conditions | Active account, MFA/freshness requirements if needed | Additional security checks |
| Mapping owner | Application entitlement governance team | Reviewed, audited, and rollback-capable |

Example decision table:

| IdP / tenant | Input group | Granted authority |
| --- | --- | --- |
| `corp / north` | `portal-readers` | `ROLE_VIEWER` |
| `corp / north` | `portal-reviewers` | `ROLE_APPROVER` |
| `partner / north` | `partner-viewers` | `ROLE_VIEWER` |
| `corp / south` | `portal-reviewers` | **Do not grant**, no policy defined |
| `partner / north` | `portal-reviewers` | **Do not grant**, different IdP |
| Any | `ROLE_ADMIN` | **Do not grant**, no mapping for that value |

A group must never carry a `ROLE_...` name and be injected verbatim into authorities. Every authority must originate from an **SP-managed mapping table**.

### Handling input data

- If the attribute is absent: typically return an **empty additional authority set**, or **deny login** when the contract requires a group to use the SP.
- If the attribute contains multiple values: iterate **all** of them, deduplicate, and grant only authorities with an exact policy match.
- If a value is null, non-string, or abnormally long: ignore or fail per policy; never call `toString()` on arbitrary XML objects to match permissions.
- If both `allow` and `deny` groups exist: define clear precedence; sensitive permissions should prefer **deny** on conflicting data.
- If the tenant cannot be reliably identified: grant no tenant-specific permissions.
- If policy lookup/database fails: **fail closed** for sensitive permissions, never defaulting to admin or read-all.
- If an IdP emits a shared group used across multiple apps: ensure the group is scoped specifically to this SP rather than conflating generic groups with special privileges.

## 7. Standalone Java 17: mapping by IdP + tenant + allowlist

To decouple **business logic** from OpenSAML/Spring Security versions, the example below uses **pure JDK Java 17+**. It accepts a server-verified registration and tenant alongside a group list **extracted from a verified assertion**, returning the permitted authorities.

Create **SafeSamlAuthorityMappingDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class SafeSamlAuthorityMappingDemo {

    record Scope(String registrationId, String tenantId) {}

    private static final Map<Scope, Map<String, String>> POLICY = Map.of(
        new Scope("corp", "north"), Map.of(
            "portal-readers", "ROLE_VIEWER",
            "portal-reviewers", "ROLE_APPROVER"
        ),
        new Scope("partner", "north"), Map.of(
            "partner-viewers", "ROLE_VIEWER"
        )
    );

    static Set<String> mapAuthorities(String registrationId,
                                      String trustedTenant,
                                      List<String> groups) {
        Map<String, String> allowed =
                POLICY.get(new Scope(registrationId, trustedTenant));

        if (allowed == null || groups == null) {
            return Set.of();
        }

        Set<String> result = new TreeSet<>();

        for (String group : groups) {
            if (group == null) {
                continue;
            }
            String authority = allowed.get(group);
            if (authority != null) {
                result.add(authority);
            }
        }

        return result;
    }

    public static void main(String[] args) {
        System.out.println(mapAuthorities(
            "corp", "north",
            List.of("portal-readers", "portal-reviewers", "ROLE_ADMIN")
        ));
        System.out.println(mapAuthorities(
            "partner", "north", List.of("portal-reviewers")
        ));
        System.out.println(mapAuthorities(
            "corp", "south", List.of("portal-readers")
        ));
        System.out.println(mapAuthorities(
            "partner", "north", List.of("partner-viewers")
        ));
    }
}
~~~

Compile and run:

~~~bash
javac SafeSamlAuthorityMappingDemo.java
java SafeSamlAuthorityMappingDemo
~~~

**Exact stdout:**

~~~text
[ROLE_APPROVER, ROLE_VIEWER]
[]
[]
[ROLE_VIEWER]
~~~

**Explanation:**

1. For `corp/north`, the two allowlisted groups produce `ROLE_APPROVER` and `ROLE_VIEWER`. The unknown value `ROLE_ADMIN` **does not grant admin rights**.
2. `partner/north` has no authority to interpret `corp`'s `portal-reviewers`, so nothing is granted.
3. `corp/south` has no policy, so it cannot mistakenly reuse `corp/north` privileges.
4. `partner-viewers` under `partner/north` maps to `ROLE_VIEWER`.

`TreeSet` creates deterministic ordering for easy output verification; order does not imply authority precedence. `Map.of` and `record` are standard Java 17 features. The policy here is a **sample configuration** and excludes SAML verification, tenant membership checks, object authorization, revocation, and MFA assurance. In production, implement those separately.

**Never take `trustedTenant` directly from an unchecked query string** and pass it into this function. Tenant must be resolved through server-trusted session/subject mapping/membership permissions.

## 8. Turning policy into SimpleGrantedAuthority in Spring Security

Once a SAML Response has passed verification, the application can convert internal authorities into `SimpleGrantedAuthority`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// This runs inside a service/converter after SAML authentication succeeds.
// policy is the result of an SP-managed lookup, not a Map received from the client.
Set<String> permittedRoles = Set.of("ROLE_VIEWER", "ROLE_APPROVER");

List<GrantedAuthority> authorities = permittedRoles.stream()
    .map(SimpleGrantedAuthority::new)
    .collect(Collectors.toList());
~~~

This is a **code fragment using a policy-checked `permittedRoles` variable**, not a standalone class. Calling `new SimpleGrantedAuthority(value)` in mapping code does not mean allowing arbitrary input strings; the key is that `value` **must come from the application-decided role set**, not raw group strings.

### Structuring as a unit-testable service

Design a dedicated `SamlAuthorityMappingService`:

~~~text
Input:
  verified registrationId
  verified SAML AttributeStatement / principal
  trusted application account + tenant membership
  current policy version / allowlist

Mapping service:
  validate attribute key and data types
  normalize only by explicit contract
  match exact issuer+registration+tenant+group
  deduplicate
  apply deny constraints and least privilege

Output:
  Collection<GrantedAuthority>
  + source and policy version for audit
~~~

**The database and application are the final authority** whenever permissions carry business impact: the IdP may state "this person belongs to group X", while the SP decides "which invoices in which tenant may group X approve". For high privileges, require internal approvals or database-backed grants instead of relying solely on SAML groups.

## 9. Plugging mapping into the SAML Response authentication flow

Spring Security allows customizing **response-to-authentication conversion** in the OpenSAML provider. The recommended place is **after the library has verified the Response/Assertion**, reusing the default converter to extract the principal/attributes, and then replacing/supplementing authorities per policy.

~~~text
Saml2WebSsoAuthenticationFilter
                |
                v
         Saml2AuthenticationToken
                |
                v
    OpenSAML AuthenticationProvider
       signature + issuer + destination
       assertions + time + audience
                |
          Default converter
                |
      Principal + SAML attributes
                |
       SP's mapping service
                |
   Saml2Authentication / Authentication
      with controlled authorities
                |
        SecurityContextHolder
~~~

### Spring Security 6.x: OpenSAML provider converter

In Spring Security 6.x versions using `OpenSaml4AuthenticationProvider`, a common integration pattern is:

~~~java
OpenSaml4AuthenticationProvider provider =
        new OpenSaml4AuthenticationProvider();

Converter<OpenSaml4AuthenticationProvider.ResponseToken,
          Saml2Authentication> defaults =
        OpenSaml4AuthenticationProvider
            .createDefaultResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication verified = defaults.convert(responseToken);

    Saml2AuthenticatedPrincipal principal =
            (Saml2AuthenticatedPrincipal) verified.getPrincipal();

    // Invoke the application's service here with principal, registrationId,
    // and server-verified account/tenant.
    Collection<GrantedAuthority> mapped =
            mappingService.mapVerifiedSamlPrincipal(principal);

    return new Saml2Authentication(
            principal, verified.getSaml2Response(), mapped);
});
~~~

**This illustrates the integration point**, not a standalone Java class; `mappingService` is a real service built by the application. Add appropriate Spring Security imports, register the provider bean in your SAML configuration and wire it into `saml2Login`'s authentication manager, and verify against your **exact Spring Security/OpenSAML version**. Some 6.x releases include an OpenSAML 5 provider with different class and converter names.

**Mandatory safety point:** invoke the default converter and keep default validators so you never accidentally drop signature, issuer, audience, timing, and subject confirmation checks. If the mapping service fails, never fall back to `ROLE_ADMIN` or arbitrary authorities. The call into mapping from this snippet must see **only verified information**, never raw XML from an HTTP request.

### Spring Security 7.x: API differences

Spring Security 7.x centers on `OpenSaml5AuthenticationProvider` and `ResponseAuthenticationConverter`, while separating assertion details from the principal via **`Saml2ResponseAssertionAccessor`**; details around `Saml2AuthenticatedPrincipal` are adjusted in the migration path.

Safe approach:

1. Use the matching **OpenSAML 5 provider** and response converter for your version.
2. Start from the **default converter**; never replace validators with a hand-rolled parser.
3. From verified assertions/attributes, call the **mapping policy service**.
4. Construct an Authentication with vetted authorities using the version-appropriate API (e.g., `Saml2AssertionAuthentication` or the class recommended in that branch).
5. Wire the provider into `saml2Login(authenticationManager(...))` or the equivalent configuration for your release.
6. Compile/test with the exact Spring Boot/Security BOM in use.

**Do not copy-paste the previous section's OpenSaml4 snippet into Spring Security 7.** APIs and assertion storage have changed; review the official migration documentation before upgrading.

## 10. Should default authorities be kept?

Depending on the branch and provider, Spring Security may grant a baseline authority like `ROLE_USER`, and newer versions may represent authentication factors via dedicated authorities. When replacing authorities with a custom mapping, make an **explicit decision** whether to keep or drop baseline authorities.

Two strategies:

- **Replace:** keep only permissions in the SP allowlist. Pro: fewer unintended permissions; con: the app may need a baseline authority to protect ordinary pages.
- **Controlled merge:** retain an **approved** baseline authority set after SAML login, and add mapped authorities on top. Never unconditionally copy every existing authority if policy intends to restrict privileges.

**Do not treat `ROLE_USER` as `ROLE_APPROVER`.** Permission to log into the Portal only proves the user is a valid subject; privileged actions must be granted separately and checked per object.

A practical rule: **default-deny sensitive privileges**. If group/tenant/policy cannot be resolved, you may still allow viewing a landing page with minimal permissions per org policy, while forbidding approvals, data exports, or administration.

## 11. Do not confuse SAML groups with OAuth2 scopes/JWT authorities

SAML Federation and OAuth2 Resource Server can coexist in one system, but their mapping mechanisms differ:

| Source | Input data | Typical tool |
| --- | --- | --- |
| SAML2 Login | `AttributeStatement` from SAML Assertion | Response authentication converter / policy mapping |
| OAuth2/JWT Resource Server | JWT claims such as `scope`, `scp`, `roles` | `JwtAuthenticationConverter` |
| OIDC Login | ID token/UserInfo claims | OIDC/OAuth2 user authority mapper per version |
| LDAP login | LDAP group membership | LDAP authorities mapper |
| Internal database | Tenant roles/entitlements | `UserDetailsService`, PermissionEvaluator, or domain authorization service |

**Do not use `JwtGrantedAuthoritiesConverter` to process SAML XML.** It is built for JWTs, not SAML Assertions. If a backend serves both web SAML login and JWT APIs, share a common business permission policy while keeping **distinct adapters/validators per token type**.

A group `finance` from IdP A does not automatically equal OAuth scope `finance.read` or `ROLE_FINANCE_ADMIN`. Every translation must have an owner and an explicit permission contract.

## 12. Tenant, account linking, and identity lifecycle

SAML principals typically carry **NameID** and an email attribute. They assist identification, yet are not automatically immutable unique keys across all partners.

For multi-tenant setups:

1. Verify **registration/IdP issuer** first.
2. Resolve the internal account via the agreed **issuer + stable subject identifier**; emails can change, be reused, or go unverified per IdP policy.
3. Load the list of tenants the account may access from an internal store or approved source.
4. If the browser picks an active tenant, verify it against memberships; never trust tenant solely from query/header.
5. Map groups to authorities **scoped to that tenant**.
6. On object access, verify the object belongs to the current tenant and the user has the matching permission.

**Scenario:** the same account has `ROLE_VIEWER` in tenant X and `ROLE_APPROVER` in tenant Y. If a flat set of authorities is stored in the session without tenant scope, bare `hasRole('APPROVER')` could accidentally grant approval in X. Fix this with **tenant-scoped authorities** (e.g., permissions embedding tenant) or **domain-level authorization checks** accepting tenant/object IDs on every operation.

You may store roles like `tenant:Y:payment:approve`, provided the permission format is defined by application architecture; never concatenate a client-supplied tenant string directly into `SimpleGrantedAuthority` and trust it blindly.

## 13. When the IdP changes groups, do SP session permissions update immediately?

Normally, authorities are built at successful SAML login and stored in `Authentication`/SecurityContext inside the **SP session**. If an IdP administrator removes a user from a group mid-session, authorities in the SP are **not automatically revoked instantaneously** just because the IdP group changed.

Define **permission lifetimes**:

- **Session timeout:** limit how long an SP session may be reused.
- **Reauthentication/step-up:** require fresh authentication before sensitive actions, re-checking `AuthnInstant` and `AuthnContext`.
- **Server-side entitlements:** look up current permissions in the database/authorization service on each critical request.
- **Revocation events:** synchronize permission revocation via SCIM, event bus, back-channel, or a custom mechanism; plain SAML login does not provide real-time entitlement updates.
- **Periodic refresh:** refresh permissions per policy and TTL where appropriate; never trust stale SAML claims indefinitely.

Example: an employee leaves at 11:00, while a session created at 09:00 remains valid until 17:00. If the application only checks authority snapshots from SAML without a revocation strategy, the employee can keep acting. For sensitive permissions, handle revocation lifecycles rather than relying solely on updating IdP groups.

**Note:** SAML Single Logout is a session protocol, not a substitute for updating roles/permissions across all applications. If SLO fails or is unimplemented, SP sessions may persist per local policy.

## 14. Missing, unknown, or malformed group data: how to handle it?

| Verified input | Recommended behavior |
| --- | --- |
| `groups` absent | Grant no extra roles, unless policy mandates the attribute and rejects login |
| `groups=[]` | Grant no extra roles |
| `groups=[portal-readers]` with matching corp/north | Grant `ROLE_VIEWER` |
| `groups=[ROLE_ADMIN]` not in allowlist | Ignore, audit at appropriate level |
| `groups=[portal-readers,portal-readers]` | Deduplicate, grant authority once |
| `groups` contains unexpected Object | Never cast blindly; reject/ignore per policy |
| Abnormally long group or huge list | Enforce bounds and DoS protections, handle cleanly |
| Attribute name/OID mismatches contract | Do not assume equivalence with another field |
| User belongs to another tenant | Grant no roles for the current tenant |
| Policy database timeout | Grant no sensitive permissions; return controlled error or minimal policy permissions |
| Group differs in casing | Exact match unless both sides agreed on normalization |
| IdP sends a new group after rename | Grant no permissions until mapping is approved and deployed |

An unmapped group is not necessarily a SAML authentication error; it can allow the user to **log in yet receive 403** when accessing a role-protected area. This honors the separation between authentication and authorization.

**Never choose "user lacks groups → temporarily grant ROLE_USER and ROLE_ADMIN to avoid 403".** If the system needs baseline access for general pages, define that baseline explicitly by policy while keeping sensitive permissions denied.

## 15. Required unit tests and integration tests

### Mapping service unit tests

| Case | Data | Expected result |
| --- | --- | --- |
| Valid group and scope | corp/north, portal-reviewers | `ROLE_APPROVER` |
| Two valid groups | corp/north, readers + reviewers | Viewer + Approver |
| Role injection | corp/north, ROLE_ADMIN | Do not grant Admin |
| Different IdP | partner/north, portal-reviewers | Do not grant corp permissions |
| Different tenant | corp/south, portal-reviewers | Do not grant north permissions |
| Empty data | groups null/empty | Add no permissions |
| Duplicate values | readers repeated twice | Only one Viewer |
| Wrong attribute name | `groupsX` instead of `urn:example:claims:groups` | Do not infer automatically |
| Unsupported type | XML object instead of String | Grant no permissions from unexpected types |
| Database failure | Cannot fetch tenant membership | Fail closed for privileged rights |
| Policy change | Group removed from allowlist | Corresponding role no longer granted on recompute |

### Integration tests with Spring Security and a test IdP

1. Generate a SAML Response with a valid signature from the right IdP; post-authentication, inspect `Authentication.getAuthorities()`.
2. Test a Response signed by IdP B attempting to trigger A's policy; must be rejected at protocol trust or fail to map A's roles.
3. Test attributes with multiple AttributeValues and real URI/OID names; verify the mapper processes all of them properly.
4. Test `hasRole`/`hasAuthority`, method security, and permissions on domain objects.
5. Test an active session after group revocation; verify that the revocation mechanism or domain authorization enforces it.
6. Test IdP metadata/key rotation; issuer/registration boundaries must remain intact.
7. Test multi-tenant isolation where the same user holds different permissions across two tenants.
8. Test missing/malformed data, mapping database timeouts, and oversized attributes; never grant privileges on error.
9. Test Spring Security 6.x → 7.x upgrades; verify converters, principal accessors, and authorities post-migration.
10. Verify logs do not expose sensitive group lists or entire assertions.

**Mocking the policy mapper alone is not enough:** include integration tests with real SAML Responses/IdPs to prove attributes are decrypted, verified, and mapped correctly.

## 16. Troubleshooting ROLE_ and 403 errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| SAML login succeeds, yet all APIs return 403 | No authority mapped, or lacking business permissions | Inspect allowlist policy and sanitized logs |
| `hasRole('ADMIN')` fails to match `ADMIN` | Default expects `ROLE_ADMIN` | Use consistent authority naming/prefix |
| IdP sends multiple groups, yet only one role is granted | Code uses `getFirstAttribute` instead of full list | Iterate all valid AttributeValues |
| Changing IdP preserves the same permissions | Mapping is not scoped by registration | Separate policy by issuer/registration |
| Readers group user gets reviewer rights | Mis-mapped or overly loose string normalization | Verify exact group IDs and policy owner |
| Tenant Y user approves tenant X documents | Global role used without checking resource tenant | Enforce authorization in service and tenant membership |
| Group removed at IdP, yet session keeps rights | Authentication snapshot not refreshed | Use session policy/revocation and server-side checks |
| `Saml2AuthenticatedPrincipal` cast fails after upgrade | Principal/authentication type changed | Use accessor/converter matching Spring Security version |
| `ROLE_USER` lost after customization | Converter replaces all authorities without keeping baseline | Define explicit merge/replace policy |
| Group value misinterpreted | IdP changed Name/NameFormat or value type | Check attribute contract; never rely on FriendlyName alone |
| Role gains admin after IdP emits `ROLE_ADMIN` string | Raw string passed into SimpleGrantedAuthority | Map only to internal roles via allowlist |

**Minimal logging:** verified registrationId, policy version, attribute name, counts of valid/invalid values, granted authorities, and correlation ID; for sensitive data consider hashing/masking group names. Never recklessly log SAMLResponse, NameID/email, or sensitive entitlement lists.

## 17. Self-assessment questions

**Q1:** Why can't we use `groups.stream().map(SimpleGrantedAuthority::new)` on all SAML groups?  
Because IdP-supplied group labels do not automatically equal application permissions. Names like `ROLE_ADMIN` or colliding group names across IdPs can cause unintended privilege grants. A scoped allowlist is mandatory.

**Q2:** IdP A and IdP B both emit `admins`. Should that map globally to `ROLE_ADMIN`?  
No. Only approved IdPs/tenants may grant the corresponding authority; evaluate registration and internal policy.

**Q3:** If there are three AttributeValues, is calling `getFirstAttribute` enough to determine all roles?  
No. You must process the full list of permitted values.

**Q4:** Group `portal-reviewers` has been mapped to `ROLE_APPROVER`; can payment object checks be skipped?  
No. Roles are high-level checks; you still must verify tenant, ownership, business state, and object-level permissions.

**Q5:** A user loses a group at the IdP at 11:00; do SP session authorities disappear immediately?  
Not by default. Timeout, refresh/relogin, revocation, or server-side authorization is needed to update in time.

**Q6:** Are `hasRole('APPROVER')` and `hasAuthority('ROLE_APPROVER')` generally equivalent?  
Yes, when using the default `ROLE_` prefix, though you must confirm your project's configuration.

**Q7:** Can a JWT converter be used to map SAML groups?  
Not directly. JWT and SAML have separate converters/validators, even if they share a policy service.

**Q8:** If a required group for a sensitive permission is missing, what is the safe behavior?  
Do not grant that permission; if login itself requires the attribute, reject in a controlled manner per policy.

## 18. Checklist and conclusion

- [ ] Read attributes strictly from a **SAML Assertion verified by Spring Security/OpenSAML**.
- [ ] Bind exact `registrationId`, IdP issuer, tenant, and trusted account mapping.
- [ ] Explicitly define Attribute.Name/NameFormat, value types, and stable group IDs.
- [ ] Map only **groups in the SP allowlist** to **SP-defined authorities**.
- [ ] Never turn raw `ROLE_ADMIN` strings or unknown group names into privileges.
- [ ] Handle multiple AttributeValues, nulls, duplicates, unexpected types, and oversized group lists.
- [ ] Fail closed when policy/tenant membership is missing or lookups fail for sensitive permissions.
- [ ] Explicitly decide whether to retain `ROLE_USER` or baseline authorities when replacing the response converter.
- [ ] Verify `hasAuthority`, `hasRole`, method security, and object-level authorization.
- [ ] Design session TTL, key rotation, account lifecycle, revocation, and permission refresh.
- [ ] For Spring Security 6.x/7.x, choose the matching provider, converter, and principal/assertion accessor.
- [ ] Include tests for role injection, cross-IdP, cross-tenant, missing attributes, and stale groups.
- [ ] Maintain policy mapping owners, versioning, auditing, and rollback capability.

**Conclusion:** SAML groups/attributes are **input facts asserted by the IdP**, whereas `GrantedAuthority` represents **permissions the application chooses to grant by policy**. The boundary between them must be guarded by verified trust sources, per-IdP/tenant allowlists, least privilege, and object checks. For sensitive permissions, never rely solely on group snapshots in an SSO session; always incorporate revocation and server-side authorization.

### Official documentation

- Spring Security — SAML 2.0 Login Overview (authentication, principal, attributes): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses (response converter, authorities, extension points): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 migration notes (6.x/7.x changes): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OASIS — SAML 2.0 Core, AttributeStatement: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
