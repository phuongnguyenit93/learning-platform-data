# NameID, NameIDFormat, and Federated Identity in SAML 2.0

> **Scope:** Spring Security – federation / SAML2 Model. This lesson explains how SAML 2.0 represents user identity with `NameID`, the `NameIDFormat` values, how `NameIDPolicy` requests an identifier, and how a Service Provider (SP) maps an identity from an Identity Provider (IdP) to an internal account. Standalone Java examples use Java 17; the Spring Security section uses the Servlet model, Spring Boot 3.5.x, and Spring Security 6.5.x.

## 1. Objectives and Background Knowledge

After this lesson, the learner can:

1. Locate `NameID` in `Assertion/Subject` and distinguish it from `Issuer`, `Attribute`, `SessionIndex`, `InResponseTo`, `Audience`, and the application's internal account ID.
2. Read the exact URIs of `persistent`, `transient`, `emailAddress`, `unspecified`, and other formats; understand their durability, privacy properties, and applicability scope.
3. Explain `NameQualifier`, `SPNameQualifier`, and `SPProvidedID` along with the roles of IdP entity ID and SP entity ID.
4. Distinguish the `NameIDPolicy` sent by the SP in `AuthnRequest` from the actual `NameID` returned by the IdP; understand `Format`, `SPNameQualifier`, `AllowCreate`, and `InvalidNameIDPolicy` errors.
5. Design the mapping `(IdP, SP, Format, qualifier, NameID) → internal_user_id`, handling multiple IdPs, account linking, JIT provisioning, renames, migrations, and offboarding.
6. Use Spring Security to retrieve the authenticated principal, know the limits of `Saml2AuthenticatedPrincipal#getName()`, and implement independent business authorization.
7. Test at least the cases of colliding NameIDs across two IdPs, changing transient values, recycled email addresses, changed SP entity ID, unsupported NameIDPolicy, and invalid Assertions.

**Prerequisites:** HTTP redirect/POST and sessions, Spring Security `Authentication` and `SecurityFilterChain`, IdP–SP relationship and SAML Web Browser SSO, readable XML, and the role of digital signatures. This is a lesson on **federated identity**, not a substitute for XML signature verification and Assertion condition checks.

## 2. `NameID` in the SAML Web Browser SSO Flow

In SAML 2.0, the IdP authenticates a principal and issues an `Assertion` for the SP. `<saml:Subject>` describes the principal to whom the statements apply. `<saml:NameID>` is one way to describe the subject as a string; the specification also allows `BaseID` and `EncryptedID`.

~~~text
User                 Application SP                       IdP
    | GET /private       |                                 |
    |------------------->|                                 |
    |                    | build AuthnRequest              |
    |<-- Redirect -------| (optionally with NameIDPolicy)  |
    |------------------------- SAMLRequest -------------->|
    |                    |                 authenticate user
    |<--------------------- SAMLResponse ------------------|
    | POST to ACS        |                                 |
    |------------------->|                                 |
    |                    | VERIFY signature, Issuer,       |
    |                    | Audience, time, Subject,        |
    |                    | Recipient, InResponseTo, replay |
    |                    |                                 |
    |                    | read trusted NameID/Attributes  |
    |                    | look up external identity link  |
    |                    | create Authentication + session |
    |<-- logged-in page -|                                 |
~~~

**Ordering matters:** Do not extract `NameID` from a browser-submitted `SAMLResponse` and look up the user before verification. The SP must verify the Response/Assertion using approved IdP metadata and certificates, check the intended recipient, validity window, transaction state, and anti-replay protection. A SAML response carrying a “valid-looking” NameID is still forged without this trust chain.

A **structurally illustrative** excerpt, intentionally unsigned and not a complete Assertion:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.example.org/saml"
      SPNameQualifier="https://portal.example.org/sp">
      q7Xw9T-opaque
    </saml:NameID>
    <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
        InResponseTo="_request123"
        Recipient="https://portal.example.org/login/saml2/sso/corporate"
        NotOnOrAfter="2030-01-01T10:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
</saml:Assertion>
~~~

In this example, `Issuer` identifies the **issuing IdP**; `NameID` states the **principal**; `Format` indicates how to interpret the value; the qualifiers state the identifier scope; `SubjectConfirmationData` sets the conditions for accepting the bearer assertion at the SP and does not belong to `NameID`. Values and timestamps in the XML are hypothetical, not valid login data usable directly.

## 3. `NameIDType` Structure and What Must Not Be Inferred

A `NameID` is based on SAML 2.0 Core `NameIDType`, comprising text content and optional attributes:

| Component | Practical meaning | What to watch out for |
| --- | --- | --- |
| String content | Value the IdP uses to identify the principal in the defined name domain | Not necessarily an email, username, UUID, or employee code |
| `Format` | URI indicating the name semantics, such as persistent or transient | Does not guarantee global uniqueness or access rights |
| `NameQualifier` | Security/administrative domain associated with the name | Helps distinguish two identity stores; follows format-specific rules |
| `SPNameQualifier` | SP or SP affiliation domain to which the name applies | Useful for pairwise/persistent name identifiers |
| `SPProvidedID` | Alternate identifier set by the SP or affiliation | Optional field and not automatically the internal user ID |

If `Format` is absent and nothing else specifies it, it defaults to `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified`. SAML does not automatically promise a `NameID` value is immutable for the lifetime of an account: you must inspect **the format, the IdP contract, namespace rules, and provisioning lifecycle**.

Distinguish similar-looking fields:

- `<saml:Issuer>`: entity ID of the system issuing the assertion, not the user.
- `<saml:NameID>` in `Subject`: the principal the Assertion speaks about.
- `<saml:Attribute Name="email">`: an attribute asserted about the principal; does not automatically replace `NameID`.
- `<saml:Attribute Name="groups">`: group/role claims per contract; does not automatically become internal permissions.
- `AuthnStatement/@SessionIndex`: reference to the IdP authentication session, used in some SAML Single Logout scenarios; not a long-term user ID.
- `SubjectConfirmationData/@InResponseTo`: binds the Assertion to the initiated `AuthnRequest`, not the external subject.
- `users.id`: primary key managed by the application, which should exist independently of an identity provider changing `NameID`.

## 4. Official `NameIDFormat` Catalog

**Format must be identified by its full URI.** Several SAML 2.0 formats retain URIs starting with `SAML:1.1`. That is standard-compliant and does not automatically make the message SAML 1.1.

| Format | Official URI | Usage and caveats |
| --- | --- | --- |
| Unspecified | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | No standard semantics. May be email, username, or ID depending on IdP; requires a separate contract on stability and scope |
| EmailAddress | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Email address formatted value; can change, be recycled, or collide across tenants |
| X509SubjectName | `urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName` | Subject name in X.509 syntax, commonly seen in PKI environments |
| WindowsDomainQualifiedName | `urn:oasis:names:tc:SAML:1.1:nameid-format:WindowsDomainQualifiedName` | `DOMAIN\\username` format in Windows/AD environments; names can still change |
| Kerberos | `urn:oasis:names:tc:SAML:2.0:nameid-format:kerberos` | Principal in `name[/instance]@REALM` syntax |
| Entity | `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | URI identifying a SAML entity (e.g. IdP/SP `Issuer`), rarely used as a user subject |
| Persistent | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Opaque and durable identifier, usually scoped to an IdP–SP pair or SP affiliation, suitable for controlled account linking |
| Transient | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Opaque, temporary identifier; should not be used as a long-term profile key |

For `persistent` and `transient`, SAML 2.0 Core specifies that the identifier value must not exceed **256 characters**. Persistent values are designed to be pseudonymous, avoiding revealing real names or usernames, hard to infer from real identity, and scoped to the IdP/SP. Transient identifiers must also be treated as opaque strings, without “decoding” them just because they look like a UUID.

**Special case:** `urn:oasis:names:tc:SAML:2.0:nameid-format:encrypted` is reserved for `NameIDPolicy/@Format` to request that the identifier be returned inside an `EncryptedID` element. It is not a regular cleartext format like `persistent`/`transient`. The SP must be able to decrypt properly with the matching private key when the IdP sends `EncryptedID`.

### Choosing a Format Based on Needs

| Requirement | How to decide |
| --- | --- |
| Need to recover the exact account across many years | Prefer `persistent` or a stable identifying attribute guaranteed by the IdP; always map to an internal user ID |
| Want to limit tracking a person across different applications | Use per-SP pairwise persistent IDs; do not broadcast a shared employee ID to every SP |
| Only need temporary session login with no persistent user profile | `Transient` may fit if the flow genuinely never needs future recognition |
| IdP only returns `emailAddress` | Require policies for email changes, recycling, ownership verification, and tenant isolation; avoid unsafe auto-linking |
| IdP only returns `unspecified` | Establish a dedicated agreement on meaning, uniqueness, mutability/revocation, and SP relationship |
| Identifier is considered sensitive in transit through the browser | Consider `EncryptedID`, HTTPS transport, logging/retention policy, and SP decryption |

## 5. Persistent NameID and IdP–SP Pairwise Identity

An IdP may issue **two different NameIDs for the same person** when they access two different SPs. That is a privacy protection feature, not a random bug.

~~~text
IdP A: internal employee=742
     |
     +--> portal.example.org   : persistent NameID=P-AX92
     |
     +--> finance.example.org  : persistent NameID=P-BK81

IdP B: internal employee=905
     |
     +--> portal.example.org   : persistent NameID=P-AX92
~~~

The last identifier at IdP B intentionally has the same text as at IdP A: the two people are not automatically the same, because **the IdPs differ**. Two values at two SPs from the same IdP can also differ because **the SPNameQualifier/SP entity IDs differ**.

A concrete example:

| IdP entity ID | SP entity ID | NameID value | Interpretation |
| --- | --- | --- | --- |
| `https://idp-a.example/saml` | `https://portal.example/sp` | `G92-opaque` | Identity #1 |
| `https://idp-a.example/saml` | `https://finance.example/sp` | `J18-opaque` | Could be the same person, but requires an authorized linking mechanism |
| `https://idp-b.example/saml` | `https://portal.example/sp` | `G92-opaque` | Identity #2, distinct from Identity #1 |

The specification recommends that persistent IDs **not expose a link to real identity**, and use distinct pseudonyms per relying party. Do not place persistent NameIDs in URLs, partner-shared logs, uncontrolled analytics tables, or data sent cross-SP.

**Persistent does not guarantee forever.** Changes such as changing SP entity ID, IdP tenant, user recovery, account deletion and recreation, IdP migration, or Name Identifier Management operations can cause `NameID` to change. Therefore, the SP should keep a link table mapping to `internal_user_id` and a verified migration workflow. Do not use a raw `NameID` as the primary key of orders, payments, or audit tables.

### Qualifiers with Persistent IDs

- `NameQualifier`: when present, normally identifies the **IdP that created the identifier** per persistent rules; sometimes omitted if implied by the message.
- `SPNameQualifier`: when present, must identify the **SP or SP affiliation** for which the identifier was created; sometimes omitted when the message is solely for that SP.
- `SPProvidedID`: alternate identifier established by the SP/affiliation for the principal; process only when governed by a contract and administrative rules.

Qualifiers may validly be omitted. The SP must determine the **verified context** from the registration, issuer, and recipient, never assigning qualifiers arbitrarily from emails or internal path strings. When an IdP broker relays a NameID across a federation tier, `NameQualifier` also helps preserve where the identifier was originally created according to format rules.

## 6. Transient NameID and Usage Limits

A transient NameID is **temporary and opaque**. The IdP may return different values across logins of the same person:

~~~text
Login 1: transient NameID=T-q7M2
Login 2: transient NameID=T-p8Z9
~~~

If the application creates a new account row for every transient value, the next login may look like an entirely different user. If the application searches by email to “fix” it, it may link the wrong person when an email changes or is recycled.

Architectural options:

1. Only need authentication for an ephemeral session: keep the application without persistent user profiles, or authorize based on the verified ephemeral context.
2. Need long-term profiles: require a persistent NameID or another stable attribute contractually guaranteed by the IdP, such as an employee identifier with explicit namespace/tenant.
3. Must link to an existing account: use a separate account-ownership verification flow, approval, or trusted provisioning; never rely on transient IDs or unverified emails.
4. Do not treat transient as `SessionIndex`. `SessionIndex` is an `AuthnStatement` value for session coordination (such as SLO); its lifetime, scope, and semantics differ from `NameID`.

## 7. `NameIDPolicy` in `AuthnRequest`

In an **SP-initiated SSO** flow, the SP can ask the IdP to issue a name according to policy using the `<samlp:NameIDPolicy>` element. This is **an SP request**, not an automatic property of every assertion.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-123"
    Version="2.0"
    IssueInstant="2030-01-01T10:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://portal.example.org/sp</saml:Issuer>
  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/sp"
      AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

The XML above illustrates structure; it lacks binding and signatures per IdP policy and uses hypothetical timestamps, so it is **not a directly issuable request**. Meaning:

| Attribute | Explanation |
| --- | --- |
| `Format` | Proposes the identifier type the SP wants; the IdP must honor it per profile/policy or return an error if unsupported |
| `SPNameQualifier` | Proposes the SP/affiliation namespace for the returned identifier |
| `AllowCreate="true"` | SP permits the IdP to establish **a new identifier** if none exists yet; does not mean the IdP grants an app account or role |
| `AllowCreate="false"` | SP only wants an existing identifier; the standard defines `false` as the default when omitted |
| Omitted Format/unspecified | IdP may choose a suitable format constrained by other policies; SP must verify the returned type is usable |
| `Format="...:encrypted"` | Requests returning the subject identifier in `EncryptedID`; SP needs the decryption private key |

If the IdP does not understand or accept the policy, it may return an `InvalidNameIDPolicy` error in `Response`. In particular, with `persistent` and `AllowCreate=false`, a user who has never been provisioned a pairwise ID for the SP may be rejected even with valid credentials. Changing `AllowCreate` is a **policy/onboarding decision**, not a way to bypass authentication.

**Distinguishing requested format from returned format:** a request asking for persistent does not prove the NameID in the Assertion is persistent. The SP must inspect the **verified Assertion** and apply the IdP–SP contract. Conversely, if the app sends no `NameIDPolicy`, the IdP may still issue `persistent` per partner configuration.

### `NameIDPolicy` and IdP-initiated SSO

In **IdP-initiated SSO**, no SP `AuthnRequest` is created for that transaction, so the SP cannot specify `NameIDPolicy` at that step or check `InResponseTo` as in SP-initiated SSO. The SP must maintain a dedicated IdP-initiated acceptance policy checking issuer, audience, recipient, signature, time, replay, and actual format. When strongest state/format guarantees are needed, prefer SP-initiated SSO or build an equivalent mutually supported verification mechanism.

### `NameIDFormat` in Metadata

`<md:NameIDFormat>` in SAML metadata advertises **the formats an SP/IdP supports**, distinct from `NameIDPolicy` in `AuthnRequest` and `NameID/@Format` in `Assertion`.

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:NameIDFormat>
    urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
  </md:NameIDFormat>
  <md:NameIDFormat>
    urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress
  </md:NameIDFormat>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/sso"/>
</md:IDPSSODescriptor>
~~~

This is only a **metadata excerpt**, without `EntityDescriptor`, signing keys, or metadata signature. Metadata advertises supported formats; it does not guarantee the IdP will issue any given format for every user/SP. Coordinate specific settings with the partner.

## 8. Data Model for Federated Identity

An SP should maintain **two identity layers**:

- **External identity**: ID from a verified IdP, with exact namespace/format and SP scope.
- **Internal user**: application-managed user ID, serving as primary key for business data, permissions, and audit.

Practical model:

~~~text
Validated SAML Assertion
       |
       +--> trusted IdP entity ID / registration
       +--> SP entity ID / affiliation
       +--> effective NameID Format
       +--> qualifiers per contract
       +--> exact NameID text
       |
       v
ExternalIdentityKey ----> saml_identity_link ----> app_user.id
                                  |
                                  v
                       tenant + role policy + status
~~~

An initial table design:

~~~sql
CREATE TABLE app_user (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE saml_identity_link (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app_user(id),
    provider_id VARCHAR(200) NOT NULL,
    sp_entity_id VARCHAR(512) NOT NULL,
    name_id_format VARCHAR(256) NOT NULL,
    name_qualifier VARCHAR(512),
    sp_name_qualifier VARCHAR(512),
    name_id_value VARCHAR(1024) NOT NULL,
    status VARCHAR(20) NOT NULL,
    verified_at TIMESTAMP NOT NULL
);
~~~

This is an **illustrative schema**: it omits unique constraints, indexes, NULL handling policies, tenant, encryption, transactions, and production auditing. In production, enforce a unique constraint on the **canonical external identity**. `provider_id` must map to the trusted IdP/entity ID in the registration; never take this value from form input or unverified claims.

The logical key to get right is:

~~~text
(
  trustedIdpEntityId,
  trustedSpEntityIdOrAffiliation,
  effectiveNameIdFormat,
  effectiveNameQualifier,
  effectiveSpNameQualifier,
  exactNameIdValue
)
~~~

In a system where `registrationId` is administered separately per IdP–SP pair, the key can fold part of that context into the registration. Crucially, the application must **not use raw NameID value alone** and must have consistent rules when qualifiers are allowed to be absent. Do not automatically `trim()`, lowercase, case-fold, or Unicode-normalize opaque persistent/transient values unless the IdP contract specifies it, because two distinct identifiers could be conflated.

**When there are multiple IdPs or tenants:** the same `NameID="abc"` can belong to different people. Even from the same IdP, different `SPNameQualifier` values do not automatically mean the same identity. If a broker issues assertions for multiple tenants, verify which IdP generated the NameID and who is signing/vouching for the assertion; require a trust context with sufficient proof.

## 9. Identity Link Lifecycle and Preventing Account Takeover

### 9.1. First Login and Subsequent Logins

**First time:** Spring verifies the SAML Response; the application builds the external identity key and searches for a link. If none is found, decide on JIT provisioning per tenant policy or route to a verification/approval flow. Create the link and user in a transaction with a unique constraint preventing two concurrent requests from creating duplicates. Never automatically search for an existing account by email and attach to it.

**Subsequent times:** look up the active link; check account status and tenant; create the application session and then check authorities for the resource. Never create a second account when the ID is already linked. Update display attributes per contract, but avoid mutating the external identity key simply because the user's email or display name changed.

**When NameID changes:** an IdP may generate a new identifier upon tenant change, provider migration, SP entity ID change, retirement of old identifier key pairs, or Name Identifier Management operations. You must have a verified link-transfer workflow, audit logging, a rollback plan, and handling for existing sessions. “Persistent” does not eliminate the need for migration.

**Offboarding:** revoke or disable the link when a user leaves the organization or a partner contract ends; terminate privileges/sessions per policy. Deleting a link does not mean immediately deleting business records; maintain a separate retention policy.

### 9.2. Why Auto-Linking by Email Is Dangerous

Suppose the app already has `user_id=1001`, email `an@example.org`, and a trusted link from IdP A. IdP B issues a SAML Assertion **validly signed by B itself** containing the same email, but whose subject belongs to someone else. If the app does:

~~~text
link by NameID not found -> search user by email
-> found an@example.org -> attach B to user_id=1001
~~~

then B can log into A's account. IdP B's signature proves **B made that statement**, not that B has authority to attach a new identity to an account owned by IdP A.

The right approach is to use existing links; if none exists, require proving account ownership (re-authenticating into the existing account, audited administrator approval, or trusted IdP/HR provisioning), scoped by tenant and recording the full decision. Email may be used as a **hint** in the UI if policy permits, never as sole proof.

### 9.3. Authorization Is Distinct from Authentication

A valid `NameID` only answers **who is logging in within this identity domain**. It does not inherently carry `ROLE_ADMIN`, permission to view financial reports, or API call rights. Even if the IdP returns `groups` or `roles` as SAML Attributes, the application must still map them by partner, tenant, and business permissions. A disabled account must be denied or restricted even if the Assertion is valid.

## 10. Standalone Java 17: Avoiding Merging Two Identical NameIDs

The following program only simulates the **step of building a link key after SAML verification**. It does not parse XML, verify signatures, or replace Spring Security. Its goal is to show clearly that IdP A and IdP B can issue the exact same NameID text for two different accounts.

**File `NameIdIdentityKeyDemo.java`:**

~~~java
import java.util.HashMap;
import java.util.Map;

public class NameIdIdentityKeyDemo {
    record ExternalIdentity(
            String issuerEntityId,
            String spEntityId,
            String format,
            String nameQualifier,
            String spNameQualifier,
            String value
    ) {
        ExternalIdentity {
            if (issuerEntityId == null || issuerEntityId.isBlank()
                    || spEntityId == null || spEntityId.isBlank()
                    || format == null || format.isBlank()
                    || value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing identity context or NameID");
            }
        }
    }

    public static void main(String[] args) {
        String persistent =
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";

        ExternalIdentity idpA = new ExternalIdentity(
                "https://idp-a.example/saml",
                "https://portal.example/sp",
                persistent,
                "https://idp-a.example/saml",
                "https://portal.example/sp",
                "same-name-123");

        ExternalIdentity idpB = new ExternalIdentity(
                "https://idp-b.example/saml",
                "https://portal.example/sp",
                persistent,
                "https://idp-b.example/saml",
                "https://portal.example/sp",
                "same-name-123");

        Map<ExternalIdentity, Long> links = new HashMap<>();
        links.put(idpA, 1001L);
        links.put(idpB, 2002L);

        System.out.println("IdP A -> user " + links.get(idpA));
        System.out.println("IdP B -> user " + links.get(idpB));
        System.out.println("Same external identity? " + idpA.equals(idpB));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac NameIdIdentityKeyDemo.java
java NameIdIdentityKeyDemo
~~~

**Exact stdout:**

~~~text
IdP A -> user 1001
IdP B -> user 2002
Same external identity? false
~~~

Java `record` generates `equals()` and `hashCode()` from all components; a different `issuerEntityId` makes the two identities distinct even when the NameID text is identical. Qualifier fields may be `null` when absent from the message, but a real system must enforce canonicalization rules per IdP contract before constructing the key.

**Limitations:** `HashMap` is not persistent storage, has no unique index/transaction, does not handle federation brokers, does not evaluate qualifiers or formats on its own, and performs no validation. In production, construct this object only from a **verified assertion** and approved registration/metadata.

## 11. Spring Security: SAML Principal and Application ID

In Servlet-based Spring Security 6.5.x, `Saml2Authentication` has a principal of type `Saml2AuthenticatedPrincipal`. `principal.getName()` usually retrieves the **NameID value from the first verified assertion**; `principal.getRelyingPartyRegistrationId()` indicates which registration was used; `principal.getAttributes()` and `getFirstAttribute("...")` return mapped Attributes.

**Important limitation:** the high-level principal API **does not guarantee exposing `NameID/@Format`, `NameQualifier`, and `SPNameQualifier`** via dedicated getters. If your domain model requires the full identity key, integrate at the verified Assertion processing step using customization/APIs appropriate for your Spring Security/OpenSAML version; never parse client-submitted raw `SAMLResponse` in a controller and trust the XML directly.

### 11.1. Spring Boot 3.5.x, Java 17 Example

The example below compiles when Maven can fetch the relevant dependencies and repositories; actual login requires real IdP metadata, a valid SP registration, and a test user. This is a **demo application with one SAML partner**, without business identity linking or authorization yet.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>saml-nameid</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <name>Shibboleth Releases</name>
            <url>https://build.shibboleth.net/maven/releases</url>
            <snapshots><enabled>false</enabled></snapshots>
        </repository>
    </repositories>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

`metadata-uri` is an illustrative URL. Replace it with the URL provided by the approved IdP itself. The IdP must be configured with the application's SP entity ID and ACS URL (obtainable from SP metadata when `saml2Metadata()` is enabled). If the IdP requires signed `AuthnRequest`s, add SP signing credentials and configure the public certificate at the IdP; do not skip verification or swap IdP metadata arbitrarily.

**`src/main/java/demo/SamlNameIdApplication.java`:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlNameIdApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlNameIdApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/")
        String home() {
            return "Open /me to start SAML login";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                    "registrationId", principal.getRelyingPartyRegistrationId(),
                    "nameId", principal.getName());
        }
    }
}
~~~

Run `mvn spring-boot:run`; opening `http://localhost:8080/` shows the exact string **Open /me to start SAML login**. Visit `/me` or `/saml2/authenticate/corporate` to initiate SSO. Once the IdP authenticates and returns a valid assertion, `/me` returns JSON containing `registrationId` and the IdP-issued `nameId`; there are no fixed hardcoded output values. This endpoint is for learning/testing only: production should not expose raw NameIDs externally without a clear requirement and access controls.

Spring performs SAML verification at the filter/provider layer; the controller receives the principal **after authentication succeeds**. However, the internal registration name `corporate` is not the SAML `Issuer` itself. To record an identity link, map the registration to the exact IdP entity ID and SP entity ID, extract the verified format/qualifiers via appropriate custom integration, and then look up `internal_user_id` and authorize.

### 11.2. If the IdP Requires a Persistent NameIDPolicy

Spring provides `Saml2AuthenticationRequestResolver` and OpenSAML AuthnRequest customizers; exact class names and APIs depend on the Spring Security/OpenSAML version (6.x and 7.x differ). The desired protocol output in the request is:

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    AllowCreate="true"/>
~~~

This snippet is **only the XML portion to generate inside AuthnRequest**, not complete Java code. To implement it, consult the AuthnRequest customization docs for your exact version, add the policy via the OpenSAML object, and inspect the actual `SAMLRequest` in a test environment. Do not assume Spring always sends a persistent policy by default merely because `principal.getName()` returns a stable-looking string.

### 11.3. Account Linking and Authorization in Spring

The proper processing pipeline is usually:

~~~text
SAMLResponse
  -> SecurityFilterChain / OpenSAML validation
  -> Saml2Authentication + trusted RelyingPartyRegistration
  -> external identity (issuer, SP, NameID format, qualifiers, value)
  -> IdentityLinkRepository.findActive(...)
  -> AppUser (status + tenant)
  -> GrantedAuthority/authorization per business rules
~~~

An `Attribute` containing groups does not automatically grant `ROLE_ADMIN`; there must be a policy-driven group/tenant mapping. If an external identity has no link yet, perform approved onboarding/JIT provisioning or deny/require additional verification. Do not use `principal.getName()` alone as the user key in your data store.

## 12. Operating Identity Linking and Identifier Changes

SAML Core describes the **Name Identifier Management Protocol** (`ManageNameIDRequest` / `ManageNameIDResponse`) for replacing or terminating name identifiers when both parties support it. The existence of the protocol does not mean an IdP or Spring app implements the full lifecycle automatically; verify partner capabilities and build dedicated procedures when needed.

| Event | How to handle |
| --- | --- |
| User changes email while persistent NameID stays unchanged | Update display attributes only; keep the internal user and link intact |
| IdP changes persistent NameID after migration | Verify old–new relationship over a trusted channel, update link with audit trail |
| SP changes entity ID or affiliation | May cause the IdP to issue a different pairwise NameID; coordinate and run migration before go-live |
| Tenant migrates IdP | Do not assume old and new users are the same person by email; require linking proof |
| Account locked/offboarded | Disable link/privileges/sessions per policy even if the IdP still issues valid Assertions |
| IdP continues issuing transient NameID for an app needing profiles | Negotiate a stable ID or redesign as session-only; never store transient as primary key |
| Metadata advertises a new format | Test semantics, qualifiers, and trust source before changing app mapping |

**Privacy and retention:** Pairwise NameIDs can constitute user-identifying data within the SP's scope. Restrict log read access, mask or keyed-hash when needed for analytics, and do not send NameIDs to third parties without a valid purpose and authorization. Never dump full `SAMLResponse` payloads or assertions containing attributes into public logs for diagnostics.

## 13. QA / Security Test Matrix

| Scenario | Expected outcome |
| --- | --- |
| IdP A and B issue the same persistent NameID text | Two distinct identities due to different issuer/context |
| Same IdP issues NameIDs to two different SPs | Do not auto-merge without a valid linking mechanism |
| Using transient NameID on subsequent login | Must not accidentally resolve an old account from transient text |
| Email changes while persistent stays unchanged | Internal user is still found via the durable link |
| Colliding emails across tenant A/B | Do not auto-merge or grant cross-tenant access |
| IdP returns unspecified while SP requires persistent | Handle mismatch per policy; do not relabel the format string |
| `AllowCreate=false` and no existing ID yet | May receive a policy error; do not auto-create accounts out of band |
| `AllowCreate=true` and IdP supports persistent | IdP may create a new ID; SP still executes full SAML validation |
| Assertion with a known NameID but invalid signature | Reject before querying or writing identity links |
| Assertion with wrong `Issuer` / `AudienceRestriction` | Reject; no mixing between IdPs/SPs |
| Wrong `Recipient`, `Destination`, `InResponseTo`, or expired token | Reject; do not create a session |
| Reusing an already processed valid Response/Assertion | Reject per anti-replay mechanism |
| NameID in `EncryptedID` form | SP decrypts with matching credential, then validates and maps properly |
| Link exists but internal user is `DISABLED` | Grant no application permissions |
| Login succeeds without admin privileges | Admin endpoints return 403 |
| SP entity ID changes, IdP issues a different NameID | Controlled migration, no mass creation of duplicate accounts |
| Logging out a SAML session | Handle `SessionIndex`/SLO per protocol; do not treat as an identity change |

For testing, use a test IdP/tenant and synthetic accounts. When inspecting HTTP traces or SAML tracers, redact NameIDs, emails, attributes, assertions, session cookies, and authentication evidence before saving or sharing. Use your chosen library's SAML validator; never validate XML signatures with regex or string comparisons.

### Troubleshooting Common Failures

- **NameID changes after every login:** the IdP is issuing `transient`, or using a session-scoped identifier. Inspect the actual verified `Format`, fix the IdP contract and mapping.
- **Login succeeds but the account “disappeared”:** the IdP changed persistent NameID, SP entity ID, `NameQualifier`, or tenant. Check partner config and migration schedule; never search by email and auto-merge.
- **`InvalidNameIDPolicy`:** unsupported `Format`, wrong `SPNameQualifier`, or `AllowCreate=false` when no identifier exists yet. Inspect the actual request and IdP policy.
- **Two people got merged:** the app used raw `NameID`, username, or email as a global unique key. Build a canonical identity key with IdP/SP scope and audit previously conflated links.
- **Someone else's account can be logged into:** auto-linking by email or attribute from an untrusted/unauthorized IdP. Lock down the linking workflow, audit, and require account ownership verification.
- **NameID is present but 403 is returned:** authentication succeeded; the issue is in internal permissions/tenant/role mapping, not `NameIDFormat`.
- **Cannot read `EncryptedID`:** SP lacks or has the wrong decryption private key, or IdP encrypted for a different SP cert. Check registration and credentials; do not bypass encryption.
- **SAMLResponse has an identifier but is rejected:** could be signature, issuer, audience, expiration, recipient, correlation, or replay failure. Never disable the validator as a “fix.”

## 14. Exercises and Pass Criteria

**Exercise 1 – XML analysis.** Given an Assertion with `Issuer=https://idp-a`, `NameID Format=persistent`, `NameQualifier=https://idp-a`, `SPNameQualifier=https://sp-one`, and text `X123`, identify each role; explain why IdP B also issuing `X123` does not mean it is the same person.

**Exercise 2 – Choosing a format.** An HR system needs to retain profiles for many years. Compare `emailAddress`, `transient`, and `persistent`; choose an approach and describe how to handle email changes and IdP migrations.

**Exercise 3 – NameIDPolicy.** The IdP supports persistent, but a new user has not yet been issued a pairwise ID. The SP sends `AllowCreate=false`. Predict the error and describe a safe provisioning workflow without granting app permissions automatically.

**Exercise 4 – Java code.** Compile `NameIdIdentityKeyDemo.java` and verify the three lines of stdout. Change `idpB`'s issuer to `idpA` while changing its SP entity ID; predict and explain the `equals()` result.

**Exercise 5 – Spring.** Configure a test IdP in the Spring project from section 11, log in, and observe `registrationId` and principal name. Use a tool to inspect the **verified** Assertion to confirm the actual `NameID/@Format`, rather than guessing from `getName()`.

**Exercise 6 – Data safety.** Write tests for two IdPs sharing an email, an offboarded user, an Assertion with wrong audience, and a persistent NameID changed after migration. Prove the application never conflates users or grants unauthorized roles.

**Pass criteria:** accurately explain NameID/Format/qualifiers, the persistent vs. transient distinction, `NameIDPolicy` and `AllowCreate`, design an IdP–SP scoped link key, integrate Spring post-authentication, and cover at least five rejection or migration cases.

## 15. Primary References

- OASIS SAML 2.0 Core, ``2.2, 3.4.1.1, 3.6, 8.3: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authentication Responses / Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Authentication Requests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – Spring Security / SAML2: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
