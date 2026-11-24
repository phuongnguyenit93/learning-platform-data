# SAML Attribute Mapping, NameID, and Local Accounts in Identity Linking

## 1. The Problem: SSO Succeeds, but Who Does the Application Recognize?

In an application using **Spring Security SAML 2.0 Service Provider (SP)**, the Identity Provider (IdP) authenticates a user and sends a `SAML Response` containing an `Assertion`. After the SP **verifies** the assertion, the application must answer an additional business question: **which local account does this IdP identity correspond to?** That process is *identity linking/account linking*.

For example, a learning management system has local account `user_id=u-42`. The IdP sends:
- `NameID`: `opaque-abc-789`, format `persistent`.
- `email`: `lan@old.example`.
- `displayName`: `Lan Nguyen`.
- `department`: `Training`.

After a few months, the user changes their email to `lan@new.example` while keeping the stable `NameID`. The system must sign them into **the exact `u-42`**, without silently creating another account. Conversely, if another IdP happens to send the same string `opaque-abc-789`, the system **must not** treat it as the same person.

After this lesson, you will be able to:
1. Properly read `NameID`, `Format`, `NameQualifier`, `SPNameQualifier`, and SAML attributes.
2. Choose a durable identity linking key with clear IdP/SP/tenant boundaries.
3. Separate **assertion authentication** from **looking up or linking a local account**.
4. Handle first-time login, email changes, NameID changes, key collisions, account deletion/locking, and permission group changes.
5. Understand the role of `Saml2AuthenticatedPrincipal`, `RelyingPartyRegistration`, and the mapping service in Spring Security.
6. Test linking logic with a Java 17+ program including important negative cases.

**Scope:** SAML 2.0 Web Browser SSO, Java/Spring Security servlet applications, and mapping identities to accounts of **the application itself**. This lesson is not about generating SAML signatures manually or writing a custom SAML parser.

## 2. Three Data Layers Not to Confuse

| Layer | Who Decides | Examples | How Much Is It Trusted? |
| --- | --- | --- | --- |
| **SAML authentication** | SP verifies assertion from a trusted IdP | `Issuer`, `Subject/NameID`, `AudienceRestriction`, `InResponseTo`, signature, validity | Only after verification succeeds per RP configuration |
| **Identity linking** | Application managing local accounts | External identity key → `local_account.id` | Governed by linking rules, approved data, and application unique constraints |
| **Application authorization** | Application + business policy | Can `u-42` view reports or administer tenant A? | Never inferred solely from a successful SSO event |

Standard flow:

~~~text
Browser -> Service Provider (Spring Security) -> Identity Provider
             ^                                  |
             |----- SAML Response (via browser)-|
             |
   [1] Verify Response/Assertion per IdP metadata/cert
             |
   [2] Create verified Authentication + read trusted NameID/attributes
             |
   [3] Resolve (tenant, SP, IdP, NameID) -> local_account.id
             |
   [4] Check local account is active and authorization policy
             |
   [5] Create app session / grant access to that account's data
~~~

**Never run [3] before [1].** Fields inside unverified SAML XML are merely self-asserted data from the sender. Only pass an identity object that has completed trusted SAML authentication to the linking component.

## 3. What Is NameID, and When Should It Be Used as a Key?

Inside a SAML Assertion, `<Subject><NameID>...` describes the principal's identifier under **a specific format and scope**. NameID is **not an email by default**, nor is it guaranteed to remain stable across sessions.

Fields to inspect:

- **Value**: the text content of NameID, which may be an opaque identifier, UPN/email, or another string.
- **Format**: URI indicating how to interpret the identifier.
- **NameQualifier**: identifier context attached by the namespace/IdP; for persistent identifiers, carries semantics about where the identifier was minted.
- **SPNameQualifier**: the service provider context toward which the identifier is scoped, important for *pairwise* identifiers.
- **SPProvidedID**: optional attribute per SAML that may appear in some identifier models; use only if explicitly designed with the IdP, never default to replacing the primary key.
- **Assertion/Response Issuer**: identity of the issuing/asserting party; **must be verified** against the registered IdP.
- **Relying party / SP entity ID**: target service provider identifier, preventing cross-environment and cross-application linking.

### 3.1. Important NameID Formats

| Format | Characteristics | Linking Policy |
| --- | --- | --- |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | IdP intends to provide a **stable, non-guessable** identifier, typically scoped to an IdP–SP relationship | **Preferred** for long-term linking keys when the IdP commits to lifecycle and scope |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Short-lived identifier that may change across sessions or transactions | **Never** use as a long-term linking key |
| `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Value represents an email address in SAML format | Not guaranteed permanently stable or unique; may change or be reassigned |
| `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Makes no specific commitment about the value's type/semantics | Use only if both parties have an explicit contract on attributes, uniqueness, and lifecycle |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | Typically an entity identifier, not a normal choice for user accounts | Do not automatically use to link individual accounts |

**Important:** a `persistent` NameID is expected to be stable, yet the application still needs a contract with the IdP regarding account recreation, tenants, configuration changes, IdP migrations, and SP entity ID changes. Never use the bare `NameID.Value` string as a global unique key.

### 3.2. Illustrative XML Example

This is an **unsigned Assertion snippet to illustrate field names**; it is not a valid SAML Response for login and must not be used to attempt bypassing verification.

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.training.example/saml"
      SPNameQualifier="https://app.training.example/saml">
    opaque-abc-789
  </saml:NameID>
</saml:Subject>
~~~

A standalone `AttributeStatement` may contain:

~~~xml
<saml:AttributeStatement xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="urn:example:claims:email" FriendlyName="email">
    <saml:AttributeValue>lan@new.example</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:department" FriendlyName="department">
    <saml:AttributeValue>Training</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:groups" FriendlyName="groups">
    <saml:AttributeValue>reader</saml:AttributeValue>
    <saml:AttributeValue>trainer</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

The SAML attribute **Name** (and potentially `NameFormat`) is the technical contract to agree upon; `FriendlyName` is only human-readable and should not be the default mapping key. An attribute can have **multiple `AttributeValue` elements**: group memberships are typically lists; never read just the first value and treat it as full membership.

## 4. Which Attributes Belong to Profile Data vs. Identity Keys?

| Attribute | Common Purpose | Should It Be Used as a Linking Key? |
| --- | --- | --- |
| Stable/persistent `NameID` matching issuer, format, qualifiers, SP | IdP–SP identification | Yes, when backed by a lifecycle contract |
| `employeeId`/immutable directory object ID guaranteed by IdP | Internal staff identification per org policy | Possible, but requires tenant/IdP scoping, uniqueness, and reassignment policy |
| `email` | Contact, notifications, display | **Not automatically**; may change, collide, be reassigned, or be unverified |
| `displayName`, `givenName`, `sn` | UI display | No; changes naturally and is not unique |
| `department` | Organizational metadata | No; may inform policy when the source is trusted |
| `groups`/`roles` | Group-based role hints from IdP | No; requires allowlists and per-IdP/tenant role mapping |
| Organization-agreed `tenantId` | Customer data isolation boundary | Not alone; should act as **key namespace** and be validated |
| `sessionIndex` | SAML session/logout correlation | No; not a long-term person identifier |

A secure system typically stores `local_account.id` as an immutable application identifier. SSO links are strictly **external identity → local account** relationships; email/profile attributes can change independently while `local_account.id` remains intact.

**Rule:** never call a "findByEmailAndLogin" helper and automatically join two accounts simply because emails match. If an attacker controls a less trusted IdP or an email address is recycled, this approach can grant them access to an existing account's data.

## 5. Designing an Identity Key from IdP to Local Account

The application key should clearly separate **external identity** from **internal identity**:

~~~text
External identity key
  tenant_id
  relying_party_entity_id     # or stable RP code managed by the application
  idp_entity_id               # taken from verified IdP configuration
  name_id_format
  name_qualifier              # preserve if present
  sp_name_qualifier           # preserve if present
  name_id_value               # opaque; preserve verbatim

                         UNIQUE
                            |
                            v
                     local_account.id
~~~

**Note on Spring Security `registrationId`:** `RelyingPartyRegistration` uses `registrationId` as a configuration index, useful for reading principals and routing. If `registrationId` can be renamed across deployments, **do not use it alone as a long-term identifier**. Use a stable internal ID for the SP/IdP relationship while checking both IdP and RP entity IDs against configured metadata. If `registrationId` is part of the key, maintain a data migration plan for configuration renames.

When comparing opaque NameIDs:
- Preserve the received value verbatim; do not automatically `trim()`, lowercase, Unicode-normalize, or strip prefixes/suffixes without an explicit contract with the IdP.
- Enforce appropriate length, non-null/non-blank, and type constraints; avoid writing raw NameIDs into logs.
- Do not rely on an **unsalted/unkeyed** hash as a complete security control; if storage privacy is needed, consider a keyed hash and evaluate key rotation/migration.
- `NameQualifier` and `SPNameQualifier` may be omitted per standard in some cases. Define **contract-based** canonicalization rules rather than implicitly filling in values that "look right".
- Never share one key space across production, staging, different tenants, or two IdPs. Matching strings do not prove two accounts are the same person.

### 5.1. Data Schema Sketch

Illustrative SQL (PostgreSQL) storing link values per the identity contract:

~~~sql
CREATE TABLE local_account (
    id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED'))
);

CREATE TABLE external_identity_link (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES local_account(id),
    tenant_id TEXT NOT NULL,
    sp_entity_id TEXT NOT NULL,
    idp_entity_id TEXT NOT NULL,
    name_id_format TEXT NOT NULL,
    name_qualifier TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    name_id_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    linked_by TEXT NOT NULL,
    UNIQUE (
        tenant_id, sp_entity_id, idp_entity_id,
        name_id_format, name_qualifier, sp_name_qualifier, name_id_value
    )
);
~~~

The unique constraint prevents **one external identity from pointing to two local accounts**. Depending on business rules, one local account may link multiple approved IdPs, but uncontrolled bidirectional linking must be prevented. In multi-tenant environments, foreign keys and lookups must also verify `local_account`'s tenant to prevent cross-tenant account takeover; the schema sketch above only illustrates the concept and needs tenant constraints in production.

**Atomicity:** if concurrent logins or two processes try to link the same NameID, a transaction + unique index is the final safeguard. Never rely solely on `SELECT first, INSERT later` without handling conflicts.

## 6. Linking Workflows: Account Creation, First Link, Subsequent Access

### Case A — Pre-provisioning (recommended for high-privilege access)

1. An administrator or HR/SCIM system already holds `local_account.id=u-42`.
2. Through an approved identity verification workflow, pre-record external identity key → `u-42`.
3. User SSO: the SP validates the SAML Response, reads the stable key, resolves the unique link, verifies the local account is active, and creates an app session.
4. Attributes such as `email`/`displayName` can be synced under separate rules without changing the key.

**Pros:** reduces account confusion for sensitive data. **Trade-off:** requires upfront link provisioning and data maintenance.

### Case B — User Self-Linking While Logged Into a Local Account

1. The user has a strongly authenticated local session and initiates "Link SSO".
2. The application builds a SAML request with proper state/relay state/correlation, applies CSRF/session binding, and fully validates the response.
3. Determine the unique external identity and confirm/record the user's linking intent per design.
4. Inside a transaction, verify the key does not belong to another account and bind it to the **currently logged-in account**.
5. Record an audit entry: actor, timestamp, provider, link type, outcome; avoid logging raw assertions, private keys, or sensitive NameIDs.

**Shortcuts forbidden:** an SSO callback must never determine the target account from a user-supplied `accountId` field in query parameters or `RelayState`.

### Case C — Just-in-Time Provisioning (JIT)

A **new account** may be created when the assertion is verified, the NameID meets stability policy, the tenant/IdP allows JIT, and no link exists yet. Creation must use transactions and uniqueness constraints. If email matches an old account while the key does not match, **do not auto-merge**: route to additional verification, pre-provisioning, or manual handling.

JIT does not suit every service; financial, HR, or high-privilege admin systems typically require prior approval or pre-provisioning.

## 7. Email Changes, Name Changes, IdP Migrations, NameID Changes: How to Handle?

| Situation | Handling Rule | Expected Outcome |
| --- | --- | --- |
| User changes email, NameID stays stable | Look up external key as before; update profile per policy | Still resolves to the right local account |
| Name/department change | Sync display attributes if permitted | Data ownership unchanged |
| IdP changes `NameID.Value` due to migration | Verified migration mapping, approval, audit, and uniqueness check | New link is bound in a controlled way to the same local account |
| Another IdP emits the same value | `idp_entity_id` in the key differs | Does not resolve to the old IdP's account |
| Staging and production emit the same value | RP/tenant/environment namespace differs | No cross-linking |
| `transient` NameID | Never create a persistent link | Reject long-term linking; choose another mechanism |
| Local account disabled | Link may remain for audit, but login is blocked | Never re-enable access merely because the IdP returns "success" |
| External identity bound to account A requested for account B | Unique conflict; requires explicit resolution process | Never silently transfer ownership |
| Account deleted/merged by business process | Govern links, permissions, data, and history | Never leave stale links enabling takeover |
| User deleted at IdP and username/email recycled | Rely on non-reused IDs or IdP lifecycle controls | Never mistake a new person for the former user |

When an IdP renames `entityId`, changes the SP entity ID, or alters NameID policy, **that is an identifier change** that can break matching for all existing links. Execute an evaluated, audited migration; never fall back to email to "fix login errors".

## 8. Mapping AttributeStatement to Internal Data

A technical contract should specify attribute names, types, cardinality, sources, and update rules:

| SAML Attribute Name (internal example) | Type / Expectation | Local Field | Rule |
| --- | --- | --- | --- |
| `urn:example:claims:email` | 0..1 string, email format | `local_account.email` | Update only per verified-contact policy; never use to join accounts |
| `urn:example:claims:displayName` | 0..1 string | `display_name` | Enforce max length, escape on output; not a key |
| `urn:example:claims:department` | 0..1 string | `department_code` | Map through valid code table; does not grant admin privileges |
| `urn:example:claims:groups` | 0..N strings | external groups / derived roles | Use per-IdP and per-tenant allowlists; define revocation rules |
| `urn:example:claims:employeeId` | 0..1 string, uniqueness/immutability guaranteed | external staff identity if used | Use for linking only with an explicit data contract |

**Cardinality:** when a supposedly single-valued attribute returns two emails or two employee IDs, do not arbitrarily take the first element. That may indicate an IdP misconfiguration or bad data; fail closed or quarantine per policy.

**Display handling:** profile attributes can include diacritics, Unicode, and HTML characters. Store and render with proper charsets and context-aware escaping; never concatenate IdP attributes directly into SQL, query filters, or unescaped HTML templates.

**Mapping groups → roles:** never map every group name blindly into `ROLE_*` and trust it inside the application; establish an explicit mapping table:
- IdP A / tenant training / group `training-readers` → `REPORT_READ`.
- IdP A / tenant training / group `training-admins` → `REPORT_ADMIN` only if that role has been approved.
- Other groups grant no default permissions.

Permissions may need updating on every login, via short-lived caches, or via provisioning sync. Choose an appropriate strategy and revocation window because active sessions may retain old permissions unless the application refreshes them.

## 9. Security: Preconditions Before Trusting Any NameID/Attribute

Because the SAML Response traverses the user-agent, the backend may only consume NameID/attributes **after SP verification succeeds**. Validate according to IdP configuration and protocol:

1. **Signature and trust:** verify signatures on the response/assertion per profile using certificates and issuer from managed IdP metadata; never enable "accept unsigned assertion".
2. **Destination/Recipient:** the response and bearer SubjectConfirmation must target the SP's exact ACS.
3. **Issuer and audience:** issuer must match the registered IdP; audience restriction must match the SP entity ID.
4. **Timestamps:** enforce `NotBefore`, `NotOnOrAfter`, issue instant, and bounded clock skew; reject expired tokens.
5. **Request correlation:** for SP-initiated SSO, correlate `InResponseTo` with an initiated transaction; unsolicited/IdP-initiated SSO requires a separate policy rather than accepting arbitrary responses.
6. **Replay:** prevent reuse of assertion/response IDs when required by profile and risk; test that replaying a callback does not create invalid extra sessions.
7. **Signature wrapping/XML:** use a vetted SAML library; never parse XML manually and extract NameID via XPath from an assertion that might not be the authenticated one.
8. **Encryption and data protection:** enforce TLS, decrypt if assertions/attributes are encrypted, and protect private keys and truststores.
9. **Right IdP selection:** never trust a client-supplied `Issuer` to dynamically download metadata from an arbitrary URL; metadata/certs must come from a configured allowlist.
10. **Local authorization:** after SSO succeeds, still verify account active status, tenant, policy, and business permissions; profile attributes never become roles on their own.

**Identity linking does not replace SAML validation.** Being able to "read NameID" by Base64 decoding does not mean SSO is valid. If you customize Spring Security converters/validators, preserve all default checks or prove equivalence and test negative cases.

## 10. Applying in Spring Security SAML2 (Servlet)

Spring Security 6.x supports SP functionality via `org.springframework.security:spring-security-saml2-service-provider`; Spring Boot supports configuring `RelyingPartyRegistration` from IdP metadata. For WebFlux/reactive, configuration APIs and support levels are not equivalent to the servlet code below; use these examples strictly for Spring MVC/Servlet.

### 10.1. SP Configuration Pattern

Excerpt from `build.gradle` in a Spring Boot 3.3.x application with the corresponding dependency management plugin:

~~~groovy
repositories {
    mavenCentral()
    // Depending on the OpenSAML version, the official Shibboleth repository may be needed.
    maven { url 'https://build.shibboleth.net/maven/releases' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

`SecurityFilterChain` bean (a Java class that compiles when the project includes the dependencies above):

~~~java
package demo.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

`application.yml` snippet for a **lab IdP** (entityId, SSO URL, and certificate are examples to replace with real managed metadata):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-lab:
            assertingparty:
              entity-id: https://idp.training.example/saml
              singlesignon:
                url: https://idp.training.example/sso
                binding: POST
              verification:
                credentials:
                  - certificate-location: classpath:corp-lab-idp.crt
~~~

Across specific Spring Boot versions/configurations, nested property names for SSO URL/binding may vary; verify against the documentation for your exact version and IdP metadata in real setups. Using an IdP metadata URL or building `RelyingPartyRegistration` via the official API is also supported.

SP-initiated login typically starts at `/saml2/authenticate/{registrationId}`; ACS is typically `/login/saml2/sso/{registrationId}`. Here `corp-lab` is the **SP-side** registration key, not the user's NameID.

### 10.2. Reading the Principal After Spring Security Authenticates

After a valid SAML authentication, Spring Security creates `Saml2Authentication` with a `Saml2AuthenticatedPrincipal`. Example service extracting several attributes to pass to the business layer:

~~~java
package demo.saml;

import java.util.List;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;

@Component
public class SamlClaimsReader {

    public SamlProfile read(Saml2AuthenticatedPrincipal principal) {
        String nameIdValue = principal.getName();
        String registrationId = principal.getRelyingPartyRegistrationId();
        String email =
                principal.getFirstAttribute("urn:example:claims:email");
        String displayName =
                principal.getFirstAttribute("urn:example:claims:displayName");
        List<String> groups =
                principal.getAttribute("urn:example:claims:groups");

        return new SamlProfile(
                registrationId, nameIdValue, email, displayName,
                groups == null ? List.of() : List.copyOf(groups));
    }

    public record SamlProfile(
            String registrationId,
            String nameIdValue,
            String email,
            String displayName,
            List<String> groups) {}
}
~~~

`getFirstAttribute` returns `null` if absent; a claim can be multi-valued, so `getAttribute` returns a list suitable for `groups`. Do not query attribute name `email` if the IdP configured a different URI; mappings must match the contract.

**Critical point:** in the default flow, `principal.getName()` typically comes from `NameID.Value`, yet `Saml2AuthenticatedPrincipal` **does not by itself expose every verified Format/qualifier/issuer field required for a composite key**. The service above reads only **part** of the data; it is **not safe to auto-link accounts** using just `registrationId + getName()`. You need a protected adapter at the SAML validation result layer to gather NameID metadata/issuer from the verified assertion and cross-check `RelyingPartyRegistration`. Use the converter/provider API matching your Spring Security version; never take Format from browser-supplied request parameters and never re-parse untrusted XML.

Once you have a `VerifiedExternalIdentity` produced by the trusted adapter, invoke `AccountLinkService.resolve(...)`, obtain the local ID, block disabled accounts, and apply mapping rules. Integrate into a success handler or principal mapper per system contract; never alter the SAML provider's cryptographic checks merely to change the principal name field.

## 11. Standalone Java 17+ Example: Mapping Verified SAML Identity to an Account

The example below simulates **the linking layer after the SAML assertion has been verified by the library**. `VerifiedIdentity` is manually constructed test data and **performs no signature verification or SAML parsing**; in production, only a trusted backend adapter may construct equivalent data. The logic intentionally permits only `persistent` NameIDs, never joins by email, and does not JIT-create accounts.

Create `SamlAccountLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class SamlAccountLinkDemo {
    private static final String PERSISTENT =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
    private static final String TRANSIENT =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:transient";

    record ExternalKey(
            String tenant,
            String spEntityId,
            String idpEntityId,
            String nameIdFormat,
            String nameQualifier,
            String spNameQualifier,
            String nameIdValue) {}

    record VerifiedIdentity(ExternalKey key, String email) {}

    record LocalAccount(String id, String email, boolean active) {}

    static final class LinkDirectory {
        private final Map<String, LocalAccount> accounts = new HashMap<>();
        private final Map<ExternalKey, String> links = new HashMap<>();

        void addAccount(LocalAccount account) {
            if (accounts.putIfAbsent(account.id(), account) != null) {
                throw new IllegalStateException("Duplicate local account");
            }
        }

        void linkApproved(ExternalKey key, String localId) {
            requireStableKey(key);
            if (!accounts.containsKey(localId)) {
                throw new IllegalArgumentException("Unknown local account");
            }

            String previous = links.putIfAbsent(key, localId);
            if (previous != null && !previous.equals(localId)) {
                throw new IllegalStateException("Identity already linked");
            }
        }

        Optional<LocalAccount> resolve(VerifiedIdentity identity) {
            Objects.requireNonNull(identity);
            requireStableKey(identity.key());
            String localId = links.get(identity.key());
            if (localId == null) {
                return Optional.empty();
            }
            LocalAccount account = accounts.get(localId);
            if (account == null || !account.active()) {
                return Optional.empty();
            }
            return Optional.of(account);
        }

        private static void requireStableKey(ExternalKey key) {
            Objects.requireNonNull(key);
            if (!PERSISTENT.equals(key.nameIdFormat())) {
                throw new IllegalArgumentException("Unsupported NameID format");
            }
            if (blank(key.tenant()) || blank(key.spEntityId())
                    || blank(key.idpEntityId()) || blank(key.nameIdValue())
                    || key.nameQualifier() == null
                    || key.spNameQualifier() == null) {
                throw new IllegalArgumentException("Incomplete SAML identity");
            }
        }

        private static boolean blank(String value) {
            return value == null || value.isBlank();
        }
    }

    private static String resolvedId(
            LinkDirectory directory, VerifiedIdentity identity) {
        return directory.resolve(identity)
                .map(LocalAccount::id)
                .orElse("NONE");
    }

    public static void main(String[] args) {
        ExternalKey stable = new ExternalKey(
                "tenant-a",
                "https://app.training.example/saml",
                "https://idp.training.example/saml",
                PERSISTENT,
                "https://idp.training.example/saml",
                "https://app.training.example/saml",
                "opaque-abc-789");

        LinkDirectory directory = new LinkDirectory();
        directory.addAccount(new LocalAccount(
                "u-42", "lan@old.example", true));
        directory.addAccount(new LocalAccount(
                "u-77", "other@example.test", true));

        // Pre-approved link; does not rely on email.
        directory.linkApproved(stable, "u-42");

        System.out.println("Initial: " +
                resolvedId(directory,
                        new VerifiedIdentity(stable, "lan@old.example")));
        System.out.println("Email changed: " +
                resolvedId(directory,
                        new VerifiedIdentity(stable, "lan@new.example")));

        ExternalKey anotherIdp = new ExternalKey(
                stable.tenant(), stable.spEntityId(),
                "https://idp.other.example/saml", PERSISTENT,
                stable.nameQualifier(), stable.spNameQualifier(),
                stable.nameIdValue());
        System.out.println("Other IdP: " +
                resolvedId(directory,
                        new VerifiedIdentity(anotherIdp, "lan@new.example")));

        ExternalKey transientId = new ExternalKey(
                stable.tenant(), stable.spEntityId(),
                stable.idpEntityId(), TRANSIENT,
                stable.nameQualifier(), stable.spNameQualifier(),
                "session-only-id");
        try {
            directory.resolve(new VerifiedIdentity(
                    transientId, "lan@new.example"));
            System.out.println("Transient: ALLOWED");
        } catch (IllegalArgumentException expected) {
            System.out.println("Transient: REJECTED");
        }

        try {
            directory.linkApproved(stable, "u-77");
            System.out.println("Conflicting link: ALLOWED");
        } catch (IllegalStateException expected) {
            System.out.println("Conflicting link: REJECTED");
        }
    }
}
~~~

Run with JDK 17+ (no external libraries required):

~~~bash
javac SamlAccountLinkDemo.java
java SamlAccountLinkDemo
~~~

Exact stdout matching program logic:

~~~text
Initial: u-42
Email changed: u-42
Other IdP: NONE
Transient: REJECTED
Conflicting link: REJECTED
~~~

Explanation:
- The first two lookups share the same composite key, so both resolve to `u-42` even though the email in the simulated assertion changed.
- When `idpEntityId` changes, the composite key differs and no link is found.
- `transient` is rejected because it is unsuitable as a long-term key.
- A key already bound to `u-42` cannot also be bound to `u-77`.

**This is a logic test, not a production implementation.** `HashMap` supports neither concurrency nor durability; production uses a database, transactions, unique constraints, auditing, and active/tenant checks. This example does not attempt to handle clock skew, certificates, or SAML assertions; those belong in SAML authentication prior to constructing `VerifiedIdentity`. If using an immutable identifier from an attribute instead of `persistent NameID`, update the policy and tests based on the corresponding IdP contract.

## 12. Testing Strategy from Unit Mapping to End-to-End SSO

**Unit tests for linking policy** (no IdP needed):
- Same persistent NameID with a new email still returns the same local ID.
- Same NameID value with a different issuer/tenant/SP **does not** resolve to the wrong account.
- `transient` or missing issuer/qualifier data violating policy is rejected.
- One external key cannot bind to two accounts.
- Disabled or unprovisioned local accounts cannot sign in.
- If the role allowlist only contains `reader`, an unknown `super-admin` claim does not become a permission.

**Integration tests with a test IdP**:
- Generate a **properly signed** SAML Response per test metadata; verify the SP processes `NameID`, attributes, and builds the principal per contract.
- Responses with wrong signature/cert, issuer, audience, recipient/destination, validity window, or `InResponseTo` are rejected before invoking the linking service.
- Replaying an old response must not create unauthorized sessions; test cases with multiple assertions/attributes to eliminate ambiguity.
- IdP changes email/profile between logins while the link preserves the same internal ID.
- IdP changes NameID/format: must require valid linking or migration, never email fallback.
- Duplicate attributes, multi-valued groups, and missing required attributes are handled per policy.
- Concurrent linking creates at most one external key record; conflicts do not overwrite.
- Metadata/cert rotation follows a trusted workflow; never accept certificates straight from a request.

**E2E with dedicated staging accounts**:
- Login before/after the IdP changes email.
- Logout, disable internal account, disable IdP account, and verify actual session/SSO effects (SP logout and IdP logout may differ).
- Account A's data cannot be accessed using B's assertion.
- Multi-tenant: an IdP account in tenant B cannot open tenant A's data.
- Record outcomes without printing raw SAML, sensitive NameIDs, tokens, or credentials in logs.

Never use "login returns HTTP 200" as proof of correct linking. Verify the **local account ID** and permissions across every scenario, including negative ones.

## 13. Operational Implementation Checklist

1. **Agree on the IdP contract:** entity ID, metadata URL/cert, SP entity ID, NameID Format, qualifiers, NameID lifecycle, attribute names/types, and when they change.
2. **Choose key and uniqueness:** always include IdP/tenant/SP context; never use email as the default key.
3. **Authenticate before linking:** use the Spring Security SAML provider, keeping signature, issuer, audience, timestamp, recipient, and correlation checks; never hand-roll XML verification.
4. **Account provisioning:** pre-provision or controlled JIT; verify account binding and prevent duplicates.
5. **Separate profile mapping:** update email/name/department from trusted sources without arbitrarily overwriting user-owned internal attributes.
6. **Group-to-role mapping:** allowlists, tenant scoping, revocation policies, and local authorization checks.
7. **Account lifecycle:** disabled, deleted, merged, reactivated, IdP/NameID changes, and unlinking all require audited workflows.
8. **Privacy:** limit storage, usage, and sharing of persistent NameIDs; log minimal metadata with role-based access and retention limits.
9. **Negative testing:** collisions, transient IDs, stale assertions, missing claims, wrong issuer/audience, tenant mismatches, races, and replays.
10. **Resilience:** if the IdP changes metadata or NameID policy, follow an approved migration procedure rather than bypassing checks.

## 14. Self-Check Questions

**Question 1.** The same SAML `NameID.Value` arrives from two different IdPs. Is it the same user?  
**No.** Partition by issuer and RP/tenant context. Matching strings do not prove a link.

**Question 2.** A user changes their email while keeping the same `persistent NameID`. Should a new account be created?  
**No.** If a valid link already points to `u-42` and the account is active, email is only a profile attribute.

**Question 3.** A SAML Response has a valid signature, yet `AudienceRestriction` targets a different SP. May the account be linked?  
**No.** An invalid audience makes the assertion invalid for the current SP.

**Question 4.** Can `transient NameID` be used to bind to a local account for all future logins?  
**No.** Transient identifiers carry no durability guarantee; use a contracted stable identifier or another linking mechanism.

**Question 5.** `getFirstAttribute("groups")` returns "reader", while the assertion also contains "admin". Is the mapping complete?  
**No.** Groups are multi-valued; read all values and apply an allowlist rather than blindly granting admin.

**Question 6.** The SP has finished authenticating SAML. Is that enough to grant access to the local account's data?  
**No.** You still must resolve the unique link and verify active account status, tenant, roles, and data permissions.

**Question 7.** When an IdP changes NameID configuration and everyone gets "unlinked" errors, can you match old accounts by email?  
**No, you should not.** Use an approved migration plan because emails can be recycled or unverified.

## 15. Authoritative References

- [OASIS — SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `NameIDType`, `NameID Format`, persistent/transient identifiers, `SubjectConfirmation`, and `AttributeStatement`.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): SP SSO flow, post-authentication principal, and endpoints.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): assertion validation, custom validation, and authority mapping.
- [Spring Security API — Saml2AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getName()`, `getAttribute()`, `getFirstAttribute()`, and `getRelyingPartyRegistrationId()`.
- [Spring Boot 3.3 — SAML 2.0 Configuration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.saml2): relying party / IdP configuration.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature, trust, callback, and assertion validation guidance.

**Key takeaway:** NameID is an identifier with a **format and scope**, not a default "login email". The application must verify the assertion first, look up the unique external identity key within the IdP/SP/tenant context, and then check the local account and business permissions. Valid SSO does not by itself prove that account linking and authorization are correct.