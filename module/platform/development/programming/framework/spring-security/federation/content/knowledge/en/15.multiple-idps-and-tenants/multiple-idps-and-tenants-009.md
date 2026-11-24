# Limits of NameID and Email Uniqueness Across Multiple IdPs

**Module:** Spring Security – Federation  
**Parent Topic:** Multiple IdPs and Tenants  
**Illustrative Stack:** SAML 2.0 Web Browser SSO, Spring Boot 3.x, Spring Security 6.5, Java 17+.

## 1. Why Are NameID or Email Not Automatically Global Identifiers?

Suppose a Service Provider (**SP**) connects to two Identity Providers (**IdPs**): a company IdP and a partner IdP. Each IdP independently manages the identifier namespace of the users it authenticates. Consequently:

| Source | NameID | Email Attribute | Actual Person |
| --- | --- | --- | --- |
| Company IdP | **employee-42** | alex@example.org | Employee A |
| Partner IdP | **employee-42** | alex@example.org | Supplier B |
| Company IdP after staff turnover | **employee-88** | alex@example.org | Employee C newly assigned the email |

These three rows are **not one account** just because certain strings collide. The company IdP and partner IdP can emit the exact same NameID text while identifying **two completely different people**. Emails can be aliases, change with name changes, be shared, or be reassigned to newcomers.

A dangerous SP often does:

~~~text
SAML login succeeded
  -> read NameID or email
  -> SELECT * FROM app_users WHERE email = ?
  -> sign in with that matched user's privileges
~~~

If the partner IdP emits an email matching a company admin account, the SP may let the partner user take over the local admin. That is **account confusion / account takeover** at the federation boundary. A valid SAML signature only proves **which specific IdP issued the assertion**—it does not prove that email or NameID is globally unique across all IdPs.

**Principle:** Identify users with a **namespaced federated identifier** containing at minimum **a trusted issuer + a stable subject within an agreed scope**, adding **SP scope, NameID Format/qualifiers, and tenant boundary** where relevant. Then link to an approved **local user**, and finally evaluate **authorization**.

## 2. Three Independent Layers: Authentication, Linking, and Authorization

| Layer | Question | Trust Source |
| --- | --- | --- |
| **SAML Authentication** | Was this assertion genuinely issued by a trusted IdP for the right SP and is it still valid? | Spring Security SAML provider + IdP metadata/verification certificate |
| **Federated account resolution** | Which local user is this exact IdP's subject linked to? | Identity-link registry/DB, provisioning policy, and approvals |
| **Authorization** | Does this local user have permission for the resource/action in the current tenant? | DB grants, policy engine, account/tenant status |

Spring Security's **`Saml2Authentication`** may report authenticated while the local user is still unlinked or disabled. Never grant access to internal data simply because a user holds a valid assertion from another IdP trusted by the SP for basic login.

Example logic:

~~~text
ALLOW read(document 42)
  = valid SAML authentication
  AND correct issuer + stable subject + scope
  AND exact approved account link
  AND local user enabled
  AND document belongs to authorized tenant
  AND local grant READ(document 42)
  AND no explicit deny
~~~

This applies **deny by default** and **least privilege**: if a link is missing, status is unclear, or the DB cannot return a decision, grant nothing implicitly. The email attribute itself is absent from the decision expression because it is not an approved primary authentication binding.

## 3. NameID Structure in SAML 2.0

An **illustrative XML fragment**, not yet a signed assertion:

~~~xml
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    NameQualifier="https://idp.company.example/saml"
    SPNameQualifier="https://portal.example.org/saml/sp">
  pairwise-company-user-847
</saml:NameID>
~~~

Distinguish each part:

- **NameID value:** the string inside the element; may be opaque, email-like, or another code. Never assume it is an email or a globally unique user ID outside the IdP.
- **Format:** semantics of the value, such as `persistent`, `transient`, `emailAddress`, or `unspecified`.
- **NameQualifier:** namespace/authority associated with the identifier per SAML rules and format; may be omitted.
- **SPNameQualifier:** the SP or affiliation for which the identifier is intended, especially significant for pairwise persistent identifiers.
- **Assertion Issuer:** IdP `entityID` issuing the assertion, verified against the SP's trust policy. Issuer and `NameQualifier` are **two separate fields**; do not conflate them even when their text matches.
- **SP entityID:** SP identifier to which the assertion was issued; must match Audience/Recipient and trust config.

**Never** read only the NameID text and discard Format/qualifiers if the identity contract relies on those attributes. Equally, never use an unverified Qualifier value to manufacture trust; first validate the full SAML Response/Assertion.

## 4. Four Common NameID Formats

| Format | Semantics | Suitable as a Long-Term Link Key? |
| --- | --- | --- |
| **persistent** | Stable opaque identifier scoped to an IdP–SP pair or SP affiliation; often pairwise | **Potentially**, if uniqueness, lifecycle, and qualifiers are confirmed |
| **transient** | Temporary identifier that can change across sessions | **No**, unless paired with an alternative stable subject |
| **emailAddress** | Value formatted as an email address | **Not by format alone**; email guarantees neither immutability nor global uniqueness |
| **unspecified** | Meaning defined by the integrating parties | Only with an **explicit contract** covering stability, scope, and non-reassignment |

Other formats include `WindowsDomainQualifiedName`, `X509SubjectName`, `Kerberos`, and `entity`. Each carries specific namespace semantics and is not automatically suitable as a human-account primary key.

### 4.1. Persistent Does Not Mean Shared Across All SPs

SAML permits an IdP to issue different **persistent pairwise identifiers** for the same person across different SPs. For example:

~~~text
IdP company / SP portal  / person A -> pairwise-p1
IdP company / SP reports / person A -> pairwise-r7

IdP partner / SP portal  / person B -> pairwise-p1
~~~

You cannot conclude person A at `portal` and `reports` are the same by comparing values alone; nor can you conclude person A and person B at `portal` are one person simply because `pairwise-p1` collides between two IdPs. Scoping by **Issuer + SP/affiliation** is essential.

### 4.2. Transient Must Not Be Forced into Long-Term Accounts

If an IdP emits a transient NameID, the user may receive a new value on the next sign-in. Storing transient values in a unique account-link table creates duplicate accounts or causes users to "lose their data" on every login.

The solution is requiring the IdP to release a **contracted stable subject attribute** (such as a never-reassigned internal ID) or using a secure linking workflow. Never auto-merge by email to "work around" a transient ID.

### 4.3. `emailAddress` Is Not Permanent Proof of Ownership

SAML NameID Format `emailAddress` describes the identifier's syntax, **not** proof that the email was verified, immutable, and never reassigned. Even if an IdP sends a separate `emailVerified` attribute, that must be governed by the **trust contract** and still does not prove every other account using that email belongs to the same human.

### 4.4. `unspecified` Requires an Explicit Contract

An IdP might emit `userPrincipalName`, `employeeNumber`, or a username string under Format `unspecified`. The SP may use it as a key only if IdP and SP have documented **namespace, uniqueness, lifetime, reassignment, multi-tenant semantics, and migration behavior**. Never guess from the UI that a value "looks like an ID" and is immutable.

## 5. Why Email Is Unsafe for Auto-Linking Accounts Across IdPs

### 5.1. Same Email, Different People

A partner IdP could emit a shared contact address or the same string as a corporate email. The partner IdP is authoritative for authenticating its own users; it has no authority to log someone into a local admin account managed by the corporate IdP.

### 5.2. Emails Change or Get Reassigned

An address can change due to marriage, name change, domain migration, or department transfer; it can be an alias or shared mailbox; or it can be reclaimed and assigned to a new hire. If local accounts are matched by email alone, the former employee's permissions can fall into the newcomer's hands.

### 5.3. Emails Are Not Guaranteed Verified or Authoritative

Depending on the IdP, an email might be admin-typed, user-entered, or synced from another directory. Never treat a SAML-signed payload as proof that an email was verified unless the IdP contractually guarantees it.

### 5.4. Arbitrary Email Normalization Can Collide Users

- Domains generally match case-insensitively per DNS; handle IDN/punycode properly.
- Local-parts may follow provider-specific rules; never blindly lowercase all addresses when used as an identity key.
- Never strip dots, plus signs, `+tag` suffixes, or aliases because one provider's rules do not apply to all domains.
- Never use `LIKE`, substrings, or "the name before `@`" to match users.
- Unicode and IDN/homograph tricks can make strings look identical while differing in bytes/identity.

**For opaque NameIDs, never arbitrarily lowercase, trim, or strip diacritics.** Values carry IdP-defined semantics; mutating them can accidentally equate two distinct subjects. Whenever normalization is required, normalize strictly per **contract and verified input**, storing both raw and canonical values with auditing.

## 6. Namespaced Federated Keys: Minimum and Extended

### 6.1. Foundational Key

When the IdP provides a clearly namespaced stable subject:

~~~text
FederatedIdentifier = (trustedIssuerEntityId, stableSubject)
~~~

NIST SP 800-63C stresses that IdPs manage subject IDs independently and **subject identifiers can collide across IdPs**, so a relying party must never process a subject without issuer context.

In SAML persistent pairwise identifiers, SP scope also affects the value. In multi-tenant apps, identity linking and authorization additionally require a tenant boundary.

### 6.2. Defense-in-Depth Key

A reference logical structure:

~~~text
(tenantId,
 verifiedIssuerEntityId,
 spEntityIdOrAffiliation,
 nameIdFormat,
 nameQualifier,
 spNameQualifier,
 nameIdValue)
      -> localUserId
~~~

Why each part exists:

- **`tenantId`:** prevents mixing permissions across two organizations/partners.
- **`verifiedIssuerEntityId`:** keeps company and partner namespaces distinct.
- **`spEntityIdOrAffiliation`:** preserves exact pairwise identity scope.
- **`nameIdFormat`:** prevents treating a transient value that happens to match a persistent value as the same subject.
- **`nameQualifier` / `spNameQualifier`:** preserves namespace qualifiers per SAML/IdP contract.
- **`nameIdValue`:** identifier content, keeping exact semantics from the verified source.

This is a conceptual model, not a mandate that every SP must store exactly seven columns. If an IdP uses a stable employee ID attribute instead of NameID, substitute an equivalent namespace/issuer/scoping representation and prove that attribute is guaranteed unique and immutable within the approved scope.

### 6.3. Spring's `registrationId` Is Not the Issuer

`registrationId` (such as `company`/`partner`) is the **SP's local identifier** for a `RelyingPartyRegistration`. It tells Spring which metadata, certificates, and endpoints to use, yet it is not necessarily an immutable IdP issuer:

- A registration can be renamed across deployments.
- A registration can be reconfigured to point to a different issuer.
- Multiple registrations can point to the same issuer with different SP entityIDs/tenants.
- `registrationId` does not itself encode NameID Format or qualifiers.

Use `registrationId` strictly as a **trusted lookup key** to server-side configured issuer/SP scope/tenant; if stored in an identity link, plan migrations when renaming. Never let the browser specify an arbitrary issuer or tenant and treat it as a verified identity.

## 7. Two Illustrative Assertions: Same NameID Text, Two People

XML Fragment A (unsigned, explanatory only):

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.company.example/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/saml/sp">
      same-opaque-id
    </saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

XML Fragment B:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.partner.example/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/saml/sp">
      same-opaque-id
    </saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

**Result:** different issuer → different federated key, even with identical NameID text. Neither sample XML is a usable login token. With real XML, Spring Security must verify signature, issuer, audience, recipient, timestamps, and SAML request correlation before the identity resolver reads the principal.

## 8. Safe Account Resolution Diagram

~~~text
Browser
  |
  | SAMLResponse
  v
Spring Security Saml2WebSsoAuthenticationFilter
  |
  | signature, trusted Issuer, Audience, Recipient, time, InResponseTo
  v
Saml2Authentication / Saml2AuthenticatedPrincipal
  |
  | trusted registration -> issuer, SP scope, tenant
  | stable subject + Format/qualifiers per contract
  v
FederatedIdentityResolver
  |
  | exact lookup by composite key
  v
FederatedIdentityLink DB
  +-- 0 links: deny / pending onboarding
  +-- 1 link: local account (if enabled)
  +-- conflict: deny and audit; requires admin review
  |
  v
Business authorization (tenant, role, resource grants)
  |
  v
Allow or deny request
~~~

**Never fall back to email** when no exact link exists. If you need to link two federated identities to one local account, implement a dedicated workflow with authentication, explicit consent/approval, auditing, and uniqueness constraints.

## 9. Multi-IdP / Multi-Tenant PostgreSQL Schema

The following reference schema maintains an identity key with issuer/tenant/SP scope/Format/qualifiers, avoiding email primary keys:

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    display_email VARCHAR(320)
);

CREATE TABLE federated_identities (
    tenant_id VARCHAR(100) NOT NULL,
    issuer_entity_id VARCHAR(500) NOT NULL,
    sp_scope VARCHAR(500) NOT NULL,
    name_id_format VARCHAR(250) NOT NULL,
    name_qualifier VARCHAR(500) NOT NULL DEFAULT '',
    sp_name_qualifier VARCHAR(500) NOT NULL DEFAULT '',
    name_id_value VARCHAR(700) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        tenant_id, issuer_entity_id, sp_scope,
        name_id_format, name_qualifier,
        sp_name_qualifier, name_id_value
    )
);

CREATE TABLE document_permissions (
    tenant_id VARCHAR(100) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    document_id BIGINT NOT NULL,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, app_user_id, document_id)
);
~~~

**Limitations of this illustrative schema:**

- `name_qualifier=''` represents an **absent** qualifier under a normalized contract; if an IdP distinguishes absent from present-empty, add a presence flag column or an unambiguous canonical encoding.
- The foreign key `app_user_id` alone does not enforce matching `tenant_id`; production apps should add **composite foreign keys** or constraints/triggers so an identity link cannot point to another tenant's `app_user`. Example queries verify tenant explicitly.
- Documents must be tenant-bound in real data tables; permissions are only half of object-level tenant isolation.
- Write access to the link table should be restricted strictly to governed account-linking/provisioning flows with auditing and transactions.
- You can add `createdBy`, `approvedBy`, `revokedAt`, provenance, and migration history; never overwrite or lose history when an issuer changes.

### Intentionally Colliding Seed Data

~~~sql
INSERT INTO app_users (id, tenant_id, enabled, display_email)
VALUES
    (1001, 'company', TRUE, 'alex@example.org'),
    (2001, 'partner', TRUE, 'alex@example.org');

INSERT INTO federated_identities (
    tenant_id, issuer_entity_id, sp_scope,
    name_id_format, name_qualifier, sp_name_qualifier,
    name_id_value, registration_id, app_user_id
) VALUES
    ('company',
     'https://idp.company.example/saml',
     'https://portal.example.org/saml/sp',
     'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
     '',
     'https://portal.example.org/saml/sp',
     'same-opaque-id', 'company', 1001),
    ('partner',
     'https://idp.partner.example/saml',
     'https://portal.example.org/saml/sp',
     'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
     '',
     'https://portal.example.org/saml/sp',
     'same-opaque-id', 'partner', 2001);

INSERT INTO document_permissions (
    tenant_id, app_user_id, document_id, can_read
) VALUES
    ('company', 1001, 42, TRUE),
    ('partner', 2001, 42, FALSE);
~~~

Both users have **identical email and NameID text**, yet distinct federated identity keys. The company user holds a grant on document 42, while the partner user does not. There is zero reason for the partner user to inherit the company user's document permissions.

## 10. Standalone Java 17: Proving Keys Differ

The following is a **compilable/runnable Java 17+ program** with no Spring or IdP dependencies. It simulates identities already verified by a trusted authentication layer; **it is not a SAML signature validator**.

**File: `FederatedKeyDemo.java`**

~~~java
import java.util.Map;

public final class FederatedKeyDemo {

    record Key(
        String tenant,
        String issuer,
        String spScope,
        String format,
        String nameIdValue) { }

    public static void main(String[] args) {
        String format =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
        String sp = "https://portal.example.org/saml/sp";

        Key company = new Key(
            "company", "https://idp.company.example/saml",
            sp, format, "same-opaque-id");
        Key partner = new Key(
            "partner", "https://idp.partner.example/saml",
            sp, format, "same-opaque-id");
        Key transientKey = new Key(
            "company", "https://idp.company.example/saml",
            sp,
            "urn:oasis:names:tc:SAML:2.0:nameid-format:transient",
            "same-opaque-id");

        Map<Key, Long> links = Map.of(
            company, 1001L,
            partner, 2001L);

        String emailA = "alex@example.org";
        String emailB = "alex@example.org";

        System.out.println(
            "sameNameId=" + company.nameIdValue()
                .equals(partner.nameIdValue()));
        System.out.println(
            "sameEmail=" + emailA.equals(emailB));
        System.out.println(
            "sameFederatedKey=" + company.equals(partner));
        System.out.println("companyUser=" + links.get(company));
        System.out.println("partnerUser=" + links.get(partner));
        System.out.println(
            "transientLinked=" + links.containsKey(transientKey));
    }
}
~~~

Compile and run:

~~~bash
javac FederatedKeyDemo.java
java FederatedKeyDemo
~~~

**Exact stdout:**

~~~text
sameNameId=true
sameEmail=true
sameFederatedKey=false
companyUser=1001
partnerUser=2001
transientLinked=false
~~~

The Java `record` compares all key fields by value; matching name/email is insufficient when issuer/tenant differ. `transientKey` has a different Format and therefore does not match the persistent link. This abbreviated program omits qualifiers, uniqueness constraints, and transactions; production requires full namespacing per contract and SAML validation prior to lookup.

## 11. Spring Security 6.5: Reading the Principal Properly

After Spring Security verifies the `SAMLResponse`, `Saml2Authentication` usually carries a `Saml2AuthenticatedPrincipal`. In Spring Security **6.5**:

~~~java
if (authentication instanceof Saml2Authentication saml
        && saml.getPrincipal() instanceof
            Saml2AuthenticatedPrincipal principal) {

    String registrationId =
        principal.getRelyingPartyRegistrationId();
    String nameId = principal.getName();

    // Look up strictly by registration -> verified issuer/SP scope
    // and a contract-guaranteed stable subject.
}
~~~

This is a snippet inside a Java method, not a standalone class; it requires Spring Security imports for `Authentication`, `Saml2Authentication`, and `Saml2AuthenticatedPrincipal`.

**Important API limitation:** `principal.getName()` does not pack NameID Format, `NameQualifier`, and `SPNameQualifier` into one `String`. `getRelyingPartyRegistrationId()` returns the local registration key, not the raw SAML Issuer directly.

Therefore, **`registrationId` + `principal.getName()`** is only a **convenient identity lookup under a strict contract**, not a complete pre-verified composite SAML identity. Production needs a post-verification adapter/policy inspecting NameID Format/qualifiers or another contract-compliant stable subject attribute emitted by the IdP.

**Version note:** Principal APIs in Spring Security **7.x** have deprecations/replacements; this code intentionally targets **6.5**—consult the exact version's documentation when upgrading.

## 12. Spring Boot 3 + Java 17: Two Registrations, One Local Grant Policy

This example combines **SAML2 authentication** with a **DB authorization policy** instead of relying on email. It requires a Spring Boot 3.x Maven project compatible with Spring Security 6.x, two real IdPs with metadata and SP registrations, PostgreSQL with created/seeded tables, and Java 17+.

**Security limitations of the example:** The policy below assumes both IdPs have been contractually verified to **emit only persistent NameIDs** with **`SPNameQualifier=SP scope`** and **`NameQualifier` absent**, matching the seed data. The code does not parse SAML XML itself to enforce Format/qualifiers; enforce that via a **SAML identity adapter/validation contract** before production use. Never use this snippet to link users if an IdP emits `transient`, `unspecified`, or `emailAddress` NameIDs outside contract.

### 12.1. Dependencies

Inside `<dependencies>` of a `pom.xml` using a compatible Spring Boot parent/BOM:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Do not mix OpenSAML versions outside the range managed by Spring Security/Boot.

### 12.2. `application.yml`

**`src/main/resources/application.yml`**

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
server:
  servlet:
    session:
      timeout: 30m
~~~

Supply DB credentials via a secret manager or environment variables. Apply schema migrations/seeds separately; YAML does not create the `federated_identities` table.

### 12.3. Main Class

**`src/main/java/com/example/fed/FederationApplication.java`**

~~~java
package com.example.fed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
~~~

### 12.4. `SecurityConfig`: Defining Two Trust Relationships

**`src/main/java/com/example/fed/SamlSecurityConfig.java`**

~~~java
package com.example.fed;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "classpath:metadata/company-idp.xml")
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "classpath:metadata/partner-idp.xml")
                .registrationId("partner")
                .entityId("https://portal.example.org/saml/sp")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/partner")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(
            company, partner);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

- Both `company` and `partner` have **separate** metadata and verification credentials. An assertion signed by `partner` cannot be accepted as `company` when issuer/registration validation is intact.
- The SP `entityID` may be shared for the same logical SP, though pairwise persistent NameIDs can depend on `entityID`/affiliation per contract.
- Metadata on the classpath must be real IdP documents; `example.org` domains are illustrative only and do not provide SSO by themselves.
- **`@EnableMethodSecurity`** enables `@PreAuthorize` on controllers/services.
- With multiple IdPs, users can choose login at **`/saml2/authenticate/company`** or `partner`; registration selection must remain bound to server-side metadata/trust.
- If the app exposes other endpoints with sensitive data, enforce identity linking and tenant authorization there too rather than protecting only one specific resource.

### 12.5. `DocumentPolicy`: Querying Composite Key Instead of Email

**`src/main/java/com/example/fed/DocumentPolicy.java`**

~~~java
package com.example.fed;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("documentPolicy")
public class DocumentPolicy {

    private record Source(
        String tenant, String issuer, String spScope) { }

    private static final Map<String, Source> SOURCES =
        Map.of(
            "company", new Source(
                "company", "https://idp.company.example/saml",
                "https://portal.example.org/saml/sp"),
            "partner", new Source(
                "partner", "https://idp.partner.example/saml",
                "https://portal.example.org/saml/sp"));

    private final JdbcTemplate jdbc;

    public DocumentPolicy(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public boolean canRead(
            Authentication authentication, long documentId) {
        if (!(authentication instanceof Saml2Authentication saml)
                || !saml.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }

        String registrationId =
            principal.getRelyingPartyRegistrationId();
        Source source = SOURCES.get(registrationId);
        String nameId = principal.getName();

        if (source == null || nameId == null || nameId.isBlank()) {
            return false;
        }

        String sql = """
            SELECT COUNT(*)
              FROM federated_identities fi
              JOIN app_users u
                ON u.id = fi.app_user_id
               AND u.tenant_id = fi.tenant_id
              JOIN document_permissions dp
                ON dp.app_user_id = fi.app_user_id
               AND dp.tenant_id = fi.tenant_id
             WHERE fi.tenant_id = ?
               AND fi.issuer_entity_id = ?
               AND fi.sp_scope = ?
               AND fi.registration_id = ?
               AND fi.name_id_format = ?
               AND fi.name_qualifier = ''
               AND fi.sp_name_qualifier = ?
               AND fi.name_id_value = ?
               AND u.enabled = TRUE
               AND dp.document_id = ?
               AND dp.can_read = TRUE
            """;

        Long count = jdbc.queryForObject(
            sql, Long.class,
            source.tenant(),
            source.issuer(),
            source.spScope(),
            registrationId,
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
            source.spScope(),
            nameId,
            documentId);

        return count != null && count == 1;
    }
}
~~~

**Understanding the security boundaries of this code:**

1. **`SOURCES`** derives issuer/tenant/SP scope from server-side trusted registrations, never from query/header or email.
2. **SAML `AuthenticationProvider`** must have already verified the assertion before the principal reaches here.
3. The query intentionally enforces exact issuer, tenant, SP scope, Format, and qualifiers per contract, yet **`principal.getName()` does not itself prove the XML NameID Format/qualifiers matched**. Use a trusted adapter/validator to inspect NameID XML fields or use another contracted stable subject; otherwise **format confusion** risks arise when raw values collide.
4. **The `JOIN`** enforces matching tenant across user and permission; real document access still needs object-level tenant queries, not just a permission row.
5. **`JdbcTemplate` prepared parameter binding** prevents SQL injection; never concatenate `NameID` into SQL.
6. On DB errors, never fall back to allow; return a safe error and monitor rather than letting users in.
7. Checking **`count == 1`** guards against ambiguous data; uniqueness constraints and account-linking workflows must guarantee each external identity has one local owner.
8. On sensitive write operations, avoid **TOCTOU** by checking grants/resources inside a transaction or using tenant-scoped conditional `UPDATE`s.

### 12.6. Resource-Protecting Controller

**`src/main/java/com/example/fed/DocumentController.java`**

~~~java
package com.example.fed;

import java.util.Map;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    @GetMapping("/")
    public String home() {
        return "Federated identity example";
    }

    @GetMapping("/documents/{documentId}")
    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #documentId)")
    public Map<String, Object> readDocument(
            @P("documentId")
            @PathVariable("documentId") long documentId) {

        return Map.of(
            "documentId", documentId,
            "authorization", "passed");
    }
}
~~~

The controller returns stub data once policy allows, without querying real documents. In a real system, **business services and DB queries** must enforce tenant and grants alongside data retrieval rather than relying solely on a controller or hiding UI buttons.

### 12.7. Running and Integration Testing

In a complete Maven project with Java 17+, PostgreSQL, schema, real IdP metadata, and SP registrations:

~~~bash
mvn spring-boot:run
~~~

Once the app starts, the public endpoint:

~~~bash
curl -i http://localhost:8080/
~~~

Body from controller:

~~~text
Federated identity example
~~~

After a real SAML login, given the seed data and identity contract:

| Authenticated Identity | Local User | DB `READ` Grant on Document 42 | Expected |
| --- | --- | --- | --- |
| `company` + `same-opaque-id` | `1001` | `TRUE` | **200** |
| `partner` + `same-opaque-id` | `2001` | `FALSE` | **403** |
| `company` + unknown `NameID` | No link | None | **403** |
| `company` + disabled linked user | `1001` locked | `TRUE` | **403** |
| Unapproved issuer | Fails SAML validation | Any | Denied access |
| DB failure | No trusted decision | Unknown | Never returns **200** |

These are **expected behaviors**, not a claim of testing against live IdPs. If an IdP emits transient/unspecified NameIDs, test the Format policy/adapter directly; the illustrative code alone **is not proof of verified format handling**.

## 13. Linking Two IdPs to the Same Local Account

A local user may legitimately use both the corporate IdP and a joint-venture IdP. However, **matching email is not a license to auto-merge**. A secure account-linking workflow includes:

1. The user logs into their **existing local account** via an already trusted federated identity.
2. Verify the current session is sufficiently fresh; for high privileges, require re-authentication or appropriate step-up auth.
3. The user **explicitly initiates linking** the second approved IdP; the SP records CSRF-protected, time-limited state/correlation.
4. The browser authenticates at the second IdP; the SP verifies signature, issuer, audience, recipient, timestamps, and `InResponseTo` per SAML profile.
5. Construct the **complete** external identity key from verified issuer + stable subject + scope/format/qualifiers.
6. Verify the external key is **not already linked to another local account**. If already linked, never overwrite on browser request.
7. Require user confirmation or admin approval per policy; prevent user enumeration and avoid disclosing other people's accounts.
8. Write the link in an **atomic transaction** under uniqueness constraints, auditing actor, tenant, issuer, approval, and timestamp.
9. Never auto-elevate internal roles just because a second IdP was added; authorization policy remains authoritative.
10. Provide unlink/recovery mechanisms while preventing users from deleting their last sign-in method or migrating admin accounts to unapproved IdPs.

NIST federation guidance treats account linking as an action requiring an **authenticated session**, not mere email matching. Email can serve as a UX **contact hint**, never as proof of account ownership.

## 14. JIT Provisioning and Account Takeover Risks

A broken policy:

~~~text
if (emailExistsInLocalDatabase(samlEmail)) {
    signInAsExistingLocalAccount();
} else {
    createLocalAccount();
}
~~~

Another IdP can emit the same email without representing the authorized person in the local DB. Because the assertion signature is valid for that IdP, the attack happens in **account resolution**, not signature validation.

**Replacement policy:**

- **Exact federated identity link** exists → resolve the approved local user.
- No link exists → create a **pending/no-rights account** or require admin/HR provisioning; never auto-match by email.
- Email collides with an existing privileged account → never auto-link; require a linking flow proving control of both sides.
- Ambiguous/conflicting link → deny and alert audit.
- Use SCIM/HR provisioning to create links from an authoritative source with explicit keys and lifecycles.
- Disabled local account → grant zero permissions even if IdP login succeeds.

## 15. Migration: When Issuer, SP Scope, Tenant, or Email Changes

### IdP Changes Issuer / `entityID`

When an organization switches IdPs, the issuer may change from an old `entityID` to a new one. **Never auto-map old subjects to the new issuer based solely on matching NameID/email.** Establish new metadata trust, an authoritative mapping source, an approved migration script, auditing, a parallel transition period, and user-lifecycle testing before retiring the old IdP.

### SP Changes `entityID`

When using **persistent pairwise NameIDs**, changing the SP `entityID` can cause the IdP to emit a different identifier for the same human. Plan a transition/alias mapping rather than using email as the sole bridge. Also check `NameQualifier`/`SPNameQualifier`.

### Email Changes or Gets Reassigned

With a stable federated identifier, an email change **does not change the local user**; only the contact attribute updates. When an old email is reassigned to someone else, the former owner's external link must never transfer to the newcomer.

### Splitting / Merging Tenants

A subject authorized in tenant A does not automatically carry permissions to tenant B. Tenant migration and authorization migration are two separate decisions requiring clear permissions, data scope, audits, and approvers.

### Changing NameID Format or Switching to Transient IDs

If an IdP unexpectedly switches from `persistent` to `transient`/`unspecified`, **never accept the new value as an already-linked stable identity**. Halt or route through a verified migration process, handle existing sessions, and notify operations.

## 16. Negative Tests for Multi-IdP Account Linking

Use a test IdP to issue **validly signed** assertions for each scenario. Simply mutating signed XML and observing a signature failure does not prove the account-linking policy protects against logic flaws.

| Scenario | Correct Outcome |
| --- | --- |
| Two IdPs emit the same NameID value | Two distinct federated identities |
| Two IdPs emit the same email | Local users are not auto-linked |
| Partner IdP emits company admin's email | Cannot access company admin account |
| Same IdP emits persistent NameID for two SP scopes | Identifiers are not treated as the same key |
| Transient NameID sent to establish long-term link | Denied or requires stable subject contract |
| `emailAddress` NameID collides with existing account | Never auto-links |
| Format changes while value stays identical | Policy rejects silent merge |
| `NameQualifier` or `SPNameQualifier` changes | Namespace difference preserved if meaningful per contract |
| IdP issuer changes | Requires approved migration |
| `registrationId` renamed | Requires audited server-side mapping/migration |
| Email changes while persistent NameID stays constant | Preserves local link; updates display email separately |
| Email reassigned to new hire | Does not inherit local grants |
| Same subject text in two tenants | Does not cross tenant boundary |
| Request carries `tenantId`/`issuer` in query | Client cannot choose identity namespace |
| Missing local link | Denied/pending; never falls back to email |
| External key already linked to another local account | Conflict/denied; never overwrites |
| Disabled local account | Zero business access |
| Invalid SAML issuer/signature/audience | Rejected prior to account resolution |
| Opaque NameID differs in casing | Never normalized arbitrarily |
| Email contains dots or `+alias` | Do not apply one provider's normalization rules globally |
| Same document ID in different tenants | Denied by tenant/resource scope |
| DB failure during identity-link lookup | Fails closed; never falls back to allow |
| Two concurrent linking requests for the same external key | Unique constraint/transaction prevents dual linking |
| IdP group revoked while SP session remains alive | Enforce revocation/refresh/session policy within SLA |

### Review Questions

**1. Does identical NameID text at company and partner mean the same person?**  
No. Issuer and scope are part of the federated identifier.

**2. Does `Format=emailAddress` prove the email is verified and never reassigned?**  
No. Format only describes identifier syntax; provenance, verification, and lifecycle require a separate contract.

**3. Why can one person's persistent NameID differ between two SPs?**  
Because the IdP can issue pairwise identifiers scoped per SP or affiliation to protect privacy.

**4. Is `principal.getName()` alone sufficient as a composite key?**  
No. You must bind verified issuer, SP/tenant scope, and NameID semantics; code must enforce format/qualifiers per contract.

**5. If a user's email changes while their persistent NameID stays the same, do you need to create a new local user?**  
No, provided the exact federated link exists and identity lifecycle rules remain intact.

**6. To let the same user sign in via two IdPs, should you auto-link by email?**  
No. Require an authenticated session, verification of the new IdP, approval/confirmation, uniqueness constraints, and auditing.

## 17. Production Checklist

- [ ] `SAMLResponse` is fully verified against trusted metadata/certificates: signature, issuer, audience, recipient, timestamps, and `InResponseTo`.
- [ ] IdP contract specifies **NameID Format, qualifiers, stable subject, uniqueness scope, and non-reassignment**.
- [ ] Never use **email** or a raw NameID as a global primary key.
- [ ] Federated key includes **verified issuer + subject** plus SP/tenant scope where needed.
- [ ] Never arbitrarily lowercase/trim opaque NameIDs or apply provider-specific email normalization rules globally.
- [ ] `RelyingPartyRegistration`/`registrationId` maps server-side to trusted issuer, SP scope, and tenant.
- [ ] Never auto-link accounts by email collision alone; JIT onboarding defaults to pending/no-rights.
- [ ] Account linking requires an authenticated session, verification of the new IdP, and policy approval/auditing.
- [ ] Each federated key maps to at most one local owner via constraints/transactions; conflicts are rejected.
- [ ] Local roles, tenants, and resource grants are verified after resolving the exact user.
- [ ] Approved migration plans exist for issuer, SP `entityID`, NameID Format, or tenant changes.
- [ ] Disabled accounts and revoked roles are blocked within the required revocation SLA.
- [ ] Every business endpoint/service enforces account-linking and object-level authorization rather than UI-only checks.
- [ ] SQL uses bound parameters, least-privilege DB permissions, auditing, and fail-closed handling on DB outages.
- [ ] Test NameID/email collisions, wrong issuer/tenant, transient/format confusion, qualifiers, linking races, and revocations.
- [ ] Never log `SAMLResponse`, unnecessary NameID/PII, cookies/session IDs, or private keys.
- [ ] When upgrading from Spring Security 6 to 7, review principal APIs and verified identity adapters for that release.

**Conclusion:** A NameID identifies a subject **within the SAML issuer's namespace and scope**; email is an attribute that can change, be reassigned, or be emitted by multiple sources. Neither field guarantees **global uniqueness across IdPs**. To avoid account confusion and takeover, use **trusted issuer + stable subject + appropriate SP/tenant scope**, verified exact account linking, and independent business authorization.

## 18. References

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, Format, `NameQualifier`/`SPNameQualifier`, and NameID formats.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): persistent/transient NameIDs and per-SP pairwise identifiers.
- [NIST SP 800-63C-4 – Federation](https://pages.nist.gov/800-63-4/sp800-63c/Federation/): issuer + subject identity, account linking, and privacy.
- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): `RelyingPartyRegistration` and SAML authentication.
- [Spring Security 6.5 – `Saml2AuthenticatedPrincipal` API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getName`, `getRelyingPartyRegistrationId`, and `getAttribute`.
- [Spring Security 6.5 – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): SAML Response validators and attribute conversion.
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and resource-level permissions.
