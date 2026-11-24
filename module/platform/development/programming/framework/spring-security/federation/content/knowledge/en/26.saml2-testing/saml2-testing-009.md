# Testing Encrypted Assertions, Missing Attributes, and Multi-Valued Data in SAML 2.0

## 1. Objectives and Scope

In **SAML 2.0 Web Browser SSO**, the Service Provider (SP, a Spring Security application) receives a `SAMLResponse` from the Identity Provider (IdP), verifies issuer, signature, timestamps, recipient, audience, and other conditions, and only then establishes `Authentication`. An integration may work fine with an unencrypted Assertion, a single email string, and a simple group; yet once the IdP enables **`EncryptedAssertion`**, omits an attribute, or sends **multiple `AttributeValue` elements**, assumptions in application code easily trigger login failures, identity confusion, or incorrect privileges.

This article belongs to **SAML2 Testing** in the **Spring Security - federation** module. Three core goals:

1. **Encrypted assertions:** prove the SP decrypts using the right **SP private key** without skipping signature, recipient, or SAML condition checks; test wrong keys, unsupported algorithms, and key rotation.
2. **Missing attributes:** distinguish contract-required attributes (e.g., mandatory `tenant`), optional attributes (e.g., `displayName`), empty values, conflicting multiple values, and `NameID` itself; explicitly decide between **failing authentication** vs. **authenticating yet denying authorization**.
3. **Multi-valued data:** read `Attribute` value lists properly, process groups with least privilege, avoid `getFirstAttribute` when business rules must inspect the full list, and never turn complex XML types into roles via `toString()`.

**Safety conditions:** the XML examples below are diagrams/illustrations only, **not genuinely signed `SAMLResponse` payloads**. Use only controlled test IdP/signing keys to generate E2E fixtures; never edit raw XML and expect its signature to remain valid. The standalone Java 17 code later models only **attribute mapping after SAML has already been verified**—it does not decrypt or verify signatures itself.

## 2. Three Layers That Must Be Tested Separately

| Layer | What is being tested? | Typically responsible component |
| --- | --- | --- |
| **Cryptography & protocol authentication** | Decryption, signature, issuer, destination, recipient, audience, response correlation, time, replay | OpenSAML/Spring Security SAML2 provider |
| **Identity/attribute contract** | Valid `NameID`/subject ID, required attributes, exact `Name`/`NameFormat`, cardinality, and value types | IdP mappers and SP-side business mapping code |
| **Application authorization** | Active user? right tenant? approved group/role? which resources are accessible? | `UserDetailsService`/policy service/application authorization rules |

A properly decrypted and signed Assertion may still **carry no groups for the application**. That should not be treated as a decryption failure. Conversely, an Assertion containing group `APP_ADMIN` with an invalid signature **must never reach role-mapping code**.

### Overall Flow

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP
    participant A as Spring SP / ACS
    participant P as Local policy
    B->>I: AuthnRequest / SSO session
    I->>I: Create Assertion, sign per policy
    I->>I: Encrypt Assertion/Attribute with SP public key
    I-->>B: SAMLResponse POST form
    B->>A: POST /login/saml2/sso/corp
    A->>A: Resolve RelyingPartyRegistration
    A->>A: Verify applicable signatures + decrypt
    A->>A: Validate subject, issuer, audience, recipient, time, replay
    A->>A: Expose verified NameID + attribute lists
    A->>P: Identity link, required fields, tenant, and role allowlist
    P-->>A: Allowed authorities or deny
    A-->>B: Session/redirect or authentication/authorization failure
~~~

The order of signature verification vs. decryption depends on whether the **Response or Assertion is signed**, the binding, and the library. Never try to reinvent all of this with hand-rolled "decrypt XML first, check signature second" code. Use a properly configured Spring Security/OpenSAML provider.

## 3. SAML Response, Assertion, and Encrypted Elements

A response may carry plaintext `<saml:Assertion>` or `<saml:EncryptedAssertion>`. Inside an Assertion you can also encounter `<saml:EncryptedAttribute>` and `<saml:EncryptedID>`. These are **three distinct locations**:

| Element | Location | Meaning | Decryption context |
| --- | --- | --- | --- |
| **`EncryptedAssertion`** | `samlp:Response` | Encrypts the entire Assertion content | Response elements decrypter |
| **`EncryptedAttribute`** | `saml:AttributeStatement` | Only a single Attribute is encrypted | Assertion elements decrypter |
| **`EncryptedID`** | `saml:Subject` or allowed context | Encrypts identifier/`NameID` | Assertion elements decrypter |

Per Spring Security **7.1** documentation, `OpenSaml5AuthenticationProvider` uses **two decryption strategies**: `setResponseElementsDecrypter` for `EncryptedAssertion` and `setAssertionElementsDecrypter` for `EncryptedAttribute`/`EncryptedID`. By default, Spring can automatically decrypt using **decryption** `Saml2X509Credential` entries in `RelyingPartyRegistration`.

**Do not confuse:** encryption **does not replace** digital signing and verification. Signatures may sit on the Response or Assertion per trust policy/profile; XML Encryption provides confidentiality, while XML Signature protects integrity/origin after proper verification. A signed yet unencrypted SAML Assertion can still expose PII through browsers, logs, or WAFs.

### Minimal Structural XML (Not Valid Ciphertext)

~~~xml
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
                ID="_example-response" Version="2.0">
  <saml:Issuer>https://idp.example/metadata</saml:Issuer>
  <saml:EncryptedAssertion>
    <xenc:EncryptedData>
      <!-- Real ciphertext data generated by IdP; do not send fake XML to ACS -->
    </xenc:EncryptedData>
    <!-- EncryptedKey and algorithms supported by implementation -->
  </saml:EncryptedAssertion>
</samlp:Response>
~~~

This skeleton lacks required fields, XML Signature, encrypted ciphertext, and profile conditions, so **never use it as a login fixture**. It only illustrates why an SP cannot extract `AttributeValue` by grepping raw `SAMLResponse` when the IdP enables encryption.

## 4. Who Has the Public Key, Who Holds the Private Key?

SAML encryption in an IdP → SP scenario:

~~~text
Spring SP:
  owns private key + X.509 certificate for DECRYPTION
  exposes/shares matching public certificate (typically metadata)

IdP:
  reads trusted SP encryption certificate/public key
  encrypts Assertion/Attribute intended for that SP

Browser:
  carries encrypted SAMLResponse to SP

Spring SP:
  uses own PRIVATE key to decrypt
  verifies IdP signatures using IdP public verification certificate
  validates issuer/audience/recipient/time/replay
~~~

**Two key pairs serve distinct roles:**

- **IdP signing key:** IdP signs; **SP stores the public verification certificate** to check signatures.
- **SP decryption key:** IdP encrypts with the **SP's public certificate**; SP holds the **private decryption key**.
- If the SP also signs `AuthnRequest`, that is the **SP signing credential** (which may match or differ from the decryption key per policy).
- Never send the SP private key to the IdP and never commit it to Git, logs, test reports, or support tickets.
- X.509 signing and XML encryption may use different certificates; do not call every `idp.crt` file a "decryption cert."

### What Does a Wrong Key Normally Cause?

If the IdP encrypted with public key A while Spring holds only private key B, decryption must **FAIL** and grant no authenticated session. With two registrations/tenants, private keys must bind strictly to their `RelyingPartyRegistration`—never blindly try "every tenant's key" and end up assigning the wrong issuer.

**Never solve errors by disabling signature validation, skipping audience checks, or accepting raw XML to read `NameID`.**

## 5. Spring Security / OpenSAML Processing Pipeline

Spring Security SAML2 documentation describes the standard flow:

1. `Saml2WebSsoAuthenticationFilter` receives the HTTP POST containing `SAMLResponse` at the ACS, typically `/login/saml2/sso/{registrationId}`.
2. Resolver/`AuthenticationConverter` identifies the exact `RelyingPartyRegistration` and builds an initial authentication token.
3. `OpenSaml5AuthenticationProvider` processes the Response with appropriate signature-checking and decryption strategies.
4. If `EncryptedAssertion` is present, it is decrypted with the matching **SP decryption credential**.
5. The provider verifies Response/Assertion signatures per profile rules and registered issuer; decryption of `EncryptedAttribute`/`EncryptedID` happens at the right point relative to signatures.
6. Validates `Issuer`, `Destination`, `Recipient`, `InResponseTo`, `AudienceRestriction`, `Conditions`, and `SubjectConfirmationData` time windows per profile, plus replay protection if required by the app.
7. Only after valid authentication does the provider build `Authentication` and attribute data for local mapping code.
8. Local policy checks **account link + tenant/roles**; missing permissions must fail closed.

**Version note:** in Spring Security 6 many examples use `OpenSaml4AuthenticationProvider` and `Saml2AuthenticatedPrincipal`. Spring Security 7 uses `OpenSaml5AuthenticationProvider` in current reference docs and introduces `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor`, marking `Saml2AuthenticatedPrincipal` deprecated. Never copy classes/providers from a 5.x blog post into a 7.x project without checking the dependency tree.

### Why Are There Two Decryption Stages?

When an Assertion is signed, decrypting an `EncryptedAttribute` **before verifying the Assertion signature** can alter the signed XML content, breaking validation or opening an improper trust boundary. Spring separates the response decrypter and assertion decrypter to preserve the proper execution order. When only the Response is signed, decryption strategy may differ, yet **never write a custom pipeline skipping signatures** just to "grab attributes early."

## 6. Configuring the SP Decryption Credential in Spring Security

This is a **Java fragment inside a Spring Security SAML2 project**, not standalone Java 17; the project needs `spring-security-saml2-service-provider`, compatible OpenSAML dependencies, and real IdP metadata. The code illustrates the `RelyingPartyRegistration`/`Saml2X509Credential` API:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.X509Certificate;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

public class SamlDecryptionRegistrationExample {

    RelyingPartyRegistration registration(
            RSAPrivateKey spPrivateKey,
            X509Certificate spEncryptionCertificate) {

        Saml2X509Credential decryptCredential =
                Saml2X509Credential.decryption(
                        spPrivateKey, spEncryptionCertificate);

        return RelyingPartyRegistrations
                .fromMetadataLocation(
                    "https://idp.example/metadata")
                .registrationId("corp")
                .decryptionX509Credentials(
                    credentials -> credentials.add(decryptCredential))
                .build();
    }
}
~~~

**Must be completed in a real app:** load the private key from a secret manager/mounted secret with least privilege; load the matching certificate; trust and pin/review IdP metadata/signing certificates; create `RelyingPartyRegistrationRepository`; configure `SecurityFilterChain` with `saml2Login`; verify HTTPS, host/ACS/EntityID, and metadata/key rotation. This snippet does not create `AuthenticationManager` or IdP metadata itself, and **never copy private keys into source code**.

**Check APIs against Spring version:** `RelyingPartyRegistrations.fromMetadataLocation(...)` and `decryptionX509Credentials(...)` exist in current docs. Spring Boot also offers property-based credential locations, though property paths/loading modes vary by Boot version. Do not guess YAML properties from Java examples without checking your exact version.

### Components to Keep Separate

~~~text
SP's own decryption private key:
  file:/run/secrets/saml/corp-decrypt.pkcs8 (private)

SP matching X.509 public certificate:
  file:/etc/saml/corp-decrypt.crt (public)
  => IdP uses this certificate to encrypt for SP

IdP verification certificate:
  from reviewed IdP metadata / trusted signing keys
  => Spring uses it to verify IdP signature

IdP signing private key:
  stays on the IdP, NEVER in Spring SP
~~~

**Do not assume a certificate alone is enough to decrypt**: decryption requires the **private key**, not just the public certificate. When IdP and SP metadata both contain multiple `KeyDescriptor` elements, inspect `use="encryption"`/`use="signing"` attributes and product support rather than relying on matching file aliases.

## 7. Testing Decryption Across a Matrix of Keys, Algorithms, and Metadata

| Case | Fixture/setup | Expected |
| --- | --- | --- |
| E1 | IdP encrypts with SP public key A; SP holds private A | Decryption succeeds; **must still** validate SAML |
| E2 | IdP encrypts with A; SP holds only private B | Authentication FAILS, no session granted |
| E3 | Right private key yet misconfigured cert/metadata | Never pick wrong key; clear decrypt/registration error |
| E4 | Valid `EncryptedAssertion`, matching signature/Audience | Login + mapping within policy bounds |
| E5 | `EncryptedAttribute` for groups inside a signed Assertion | Decrypts in proper order after signature checks |
| E6 | `EncryptedID` carrying `NameID` | Principal identity extracted accurately after decrypt/validation |
| E7 | Bad IdP signature yet decryption succeeds | Authentication FAILS; decrypt success is not trusted auth |
| E8 | `EncryptedAssertion` with tampered ciphertext | Decryption/crypto integrity FAILS; no roles granted |
| E9 | IdP uses algorithm unsupported by baseline/stack | Rejected per policy; never enable weak crypto |
| E10 | Metadata lists encryption cert A; IdP not updated yet | Surface coordination/rotation error; never "decrypt ignoring errors" |
| E11 | Old+new decryption keys present during rollout | Accepts fixtures encrypted with policy-valid certs |
| E12 | Old cert retired | Never silently keep decrypting with a key that should be removed |
| E13 | Two SP tenants with distinct keys/EntityIDs | Never decrypt with another tenant's key or cross-link users |
| E14 | Unexpected plaintext Assertion when policy mandates encryption | Enforce policy at IdP/SP/edge; do not assume Spring rejects plaintext unconfigured |
| E15 | Response has multiple Assertions, one invalid | Never pick a valid one and ignore the other without profile-specific checks |

**Distinguish two concepts:** "IdP enabled encryption" does not mean the SP automatically **requires** every Assertion to be encrypted. If the enterprise requires *mandatory encryption*, enforce and test an explicit policy at SP/gateway/IdP; configuring a private key merely makes the SP **able to decrypt**, without proving encryption is mandatory.

### XML Encryption Algorithms and Security

Choose an **XML Encryption** and key-transport combination supported by IdP/OpenSAML/SP per crypto baseline; prefer modern interoperable algorithms (e.g., RSA-OAEP for key wrap, AES-GCM when stack-supported). Avoid enabling weak legacy algorithms like RSA v1.5 key transport just to bypass interop errors without a security assessment.

**Never hand-roll XML Encryption using DOM + arbitrary `Cipher`.** SAML/XmlSec/OpenSAML must handle references, encrypted keys, algorithm allowlists, XML canonicalization, signatures, and safe parsing. Restrict XML parser external entities/DTD/XXE, request/ciphertext size, XML nesting depth, and element counts to prevent memory/CPU abuse.

## 8. Key Rotation and Multi-Instance: Often Hard-to-Spot Bugs

Rotating an SP decryption key usually requires an **overlap window**:

~~~text
T0: SP advertises encryption public cert A, holds private A
T1: SP publishes cert B along with A when supported
T2: IdP switches to encrypting with B
T3: SP replicas still hold A and B for in-flight messages
T4: After safe overlap and verification, retire A
~~~

Not every IdP handles multiple encryption certificates identically. Overlap duration must account for **metadata caching, `InResponseTo`/in-flight `AuthnRequest`s, assertion/ticket TTLs, deployment lag**, and security policy. Check during scaling:

- Pod A holds keys A+B while pod B holds only A → intermittent login failures behind the load balancer.
- IdP switched to cert B while the SP's metadata registry is stale.
- Admin rotated the **IdP signing cert**, yet the app team thought it was the **SP encryption key**.
- Tenants inadvertently share one private key, expanding blast radius.
- Private key leaked into container images/logs/build artifacts, not revoked simultaneously.

**Test E2E with both old/new keys during the transition window**, logging failures with high-level codes (`DECRYPTION_FAILED`/`KEY_MISMATCH`) without dumping raw `SAMLResponse` or key bytes.

## 9. AttributeStatement: SAML Supports Multiple AttributeValues

Per OASIS SAML Core, each `<saml:Attribute>` has a mandatory **`Name`**, optional `NameFormat`/`FriendlyName`, and **0..N `<saml:AttributeValue>`** elements. Multi-valued attributes should use a separate `AttributeValue` element per value. `AttributeValue` is typed as `xs:anyType`, so **never assume every value is a String**.

Illustration **inside an Assertion illustrating plaintext attribute structure only**—lacking signature/timestamps/subject confirmation, so never POST directly to an ACS:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <saml:Attribute Name="urn:example:claims:groups"
                  NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                  FriendlyName="groups">
    <saml:AttributeValue xsi:type="xs:string">APP_REPORT_VIEWERS</saml:AttributeValue>
    <saml:AttributeValue xsi:type="xs:string">FINANCE_EMPLOYEES</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:tenant">
    <saml:AttributeValue xsi:type="xs:string">reports</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:email">
    <saml:AttributeValue xsi:type="xs:string">lan@example.test</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

**Three classic traps:**

1. `FriendlyName="groups"` is a human-readable hint; application contracts must rely on **approved `Name`/`NameFormat`**, never trusting an arbitrary `FriendlyName` from an unverified assertion.
2. A group list is **not necessarily** represented as a comma-separated string; standard multi-valued SAML uses **multiple `AttributeValue` elements**. If your IdP emits `"role1,role2"` as one value, document that exact contract instead of blindly splitting every string.
3. `Name="groups"` and `Name="urn:example:claims:groups"` are two distinct identifiers unless the contract declares an alias. Never silently fall back to a similar-looking name.

### What Does XML with No AttributeValue Mean?

OASIS defines an `Attribute` with **no `AttributeValue`** inside an `AttributeStatement` as having distinct semantics; do not blindly treat it as `null`, empty string, default permission, or "the IdP wants all values." `AttributeQuery` has different rules for absent values. In application code, explicitly distinguish **missing vs. present-but-empty vs. blank value**.

## 10. Attribute Contract: Required, Optional, and Multi-Valued

A Reports service might define a contract like this (claim names are examples):

| Claim | Cardinality | Policy |
| --- | --- | --- |
| **`NameID`/subject ID** | 1 stable identifier per trusted IdP/`NameIDFormat` | Missing/invalid: fail authentication or identity link |
| **`urn:example:claims:tenant`** | **Exactly one** nonblank string | Missing/2 values/conflicting: deny, never pick first |
| **`urn:example:claims:groups`** | 0..N strings | Missing/empty: authenticated user may exist with **no app role** |
| **`urn:example:claims:email`** | 0..1 string | Missing: allow login if unneeded; never use as identity key |
| **`urn:example:claims:displayName`** | 0..1 string | Missing: display non-sensitive local fallback name |
| **`urn:example:claims:department`** | 0..1 or 0..N per contract | Never infer access privileges from unapproved data |
| **`urn:example:claims:roles`** | 0..N strings from trusted issuer | Map allowlisted roles only; ignore/deny unknown values per policy |

**"Required" in this table is a business contract**, not an assertion that SAML 2.0 Core automatically mandates every IdP return `email`/`groups`/`tenant`. An SP can validly authenticate SAML without an `AttributeStatement`, after which the app rejects the action due to missing authorization data. Agree on login vs. permission policy per use case so missing a display field does not break login.

### Null / Empty / Blank Matrix

| Observed post-validation data | Example | How the app handles it |
| --- | --- | --- |
| Attribute absent | No `tenant` in Map | Deny if required; fallback if optional |
| Attribute present with zero values | `tenant -> []` | Deny required; **distinct** from absent |
| Single empty string | `tenant -> [""]` | Deny required |
| Whitespace | `tenant -> ["   "]` | Deny; trim/canonicalize only if IdP contract allows |
| Single valid value | `tenant -> ["reports"]` | Accept if trusted issuer and policy match |
| Two identical values | `tenant -> ["reports", "reports"]` | **Deny cardinality** if field allows only 1; never silently deduplicate |
| Two conflicting values | `tenant -> ["reports", "finance"]` | Deny, never `getFirstAttribute` |
| Non-string typed XML value | `tenant -> [42]` | Deny if schema requires string |
| Multi-valued group list | `groups -> ["APP_REPORT_VIEWERS","OtherGroup"]` | Map approved group, ignore unknown group per policy |
| Group attribute missing | `groups -> null` | Grant no default role |
| Non-string/huge group | `groups -> [complex XML]` | Deny/record validation error per contract |

**Why test both missing and empty:** libraries or IdP mappers may represent a valueless `Attribute` differently from an omitted attribute; calling `getFirstAttribute("tenant").toString()` can throw `NullPointerException`, or return the first element while silently ignoring conflicting values.

## 11. Roles, Groups, and the Principle of Least Privilege

Suppose the IdP emits groups:

~~~text
["Domain Admins", "APP_REPORT_VIEWERS", "UnrelatedTeam"]
~~~

The Reports app only has an approved mapping:

~~~text
IdP attribute Name: urn:example:claims:groups
value "APP_REPORT_VIEWERS" -> ROLE_REPORT_VIEWER
value "APP_REPORT_EDITORS" -> ROLE_REPORT_EDITOR
value "Domain Admins" -> NO APP AUTHORITY
unknown values -> NO APP AUTHORITY, optionally audit safe code
~~~

**Never do:** any string containing `Admin` → `ROLE_ADMIN`, grabbing the first value in the list as the role, or running `String.join(",", groupValues)` and substring-matching `"ADMIN"`. If groups use DNs, URI identifiers, or GUIDs, normalize within an **approved namespace**, never arbitrary regexes.

**Identity-critical** attributes (stable subject, tenant) should enforce strict cardinality; groups typically allow **0..N** with allowlist mapping. Having 20 groups does not mean 20 logins, yet you must bound list size, value length, and handle duplicates/nested memberships.

### Group Claims Do Not Grant Authorities on Their Own

Spring Security's SAML2 provider may assign `ROLE_USER` or a factor authority by default depending on version. That is **not** permission to view reports. **Application-specific roles** require explicit mapping or local entitlement lookup. Test that a user with SAML `Authentication` but no approved group **cannot access** an endpoint requiring `ROLE_REPORT_VIEWER`.

## 12. Spring Security 6 vs. 7: Where Are Attributes Read?

**Spring Security 5/6:** after SAML login, many codebases use `Saml2AuthenticatedPrincipal`, exposing:

~~~java
// Spring Security 5/6 pattern; fragment inside app with valid SAML auth.
Saml2AuthenticatedPrincipal principal = ...;
String email = principal.getFirstAttribute("email");
java.util.List<String> groups = principal.getAttribute("groups");
// getAttributes() has type Map<String, List<Object>>.
~~~

**Note:** `getFirstAttribute` is convenient for fields **guaranteed by contract to have one value**; never use it to "sanitize" `tenant` when an IdP sends two tenants or to read only one group when all must be evaluated.

**Spring Security 7:** migration docs mark `Saml2AuthenticatedPrincipal` deprecated in favor of **`Saml2AssertionAuthentication`** with **`Saml2ResponseAssertionAccessor`**. The accessor keeps `getAttributes()` returning `Map<String, List<Object>>`, `getAttribute(name)` returning a list, and `getFirstAttribute(name)` returning the first value (or null). Per API 7, the accessor may live on `Authentication.getCredentials()`; applications should match the exact contract/type rather than forcing principals into the old type.

~~~java
// Illustrative fragment in Spring Security 7 post-authentication:
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;

void inspectVerifiedAttributes(Authentication authentication) {
    Object credentials = authentication.getCredentials();
    if (credentials instanceof Saml2ResponseAssertionAccessor accessor) {
        java.util.Map<String, java.util.List<Object>> attrs =
                accessor.getAttributes();
        java.util.List<Object> groups =
                attrs.get("urn:example:claims:groups");
        // Only map after authentication is produced by a validated provider;
        // required/optional policy at the application layer.
    }
}
~~~

This is an **integration fragment**, not standalone Java. Depending on converters, custom `Authentication`, and minor versions, credential/principal types may vary; **check actual classes and Javadocs of your resolved dependencies**. Never cast every `Authentication` to `Saml2AssertionAuthentication` when the app supports multiple login mechanisms.

**Avoid anti-patterns:** calling `authentication.getCredentials().toString()` or `authentication.getSaml2Response()` in logs/debugging; payloads may contain raw Assertions and PII. Never deserialize unverified XML from request bodies to extract groups ahead of Spring Security's provider.

## 13. Technique for Mapping Attributes After Validation

Design the mapper to accept input already verified by the provider:

~~~text
Authenticated context (trusted SP/IdP registration + NameID)
  + Map<String, List<Object>> verified attributes

Step 1: require expected trusted issuer/registration
Step 2: validate stable subject and identity-link
Step 3: require tenant cardinality=1, string nonblank
Step 4: allow optional email/displayName absent
Step 5: validate group list 0..N, values typed strings and bounded
Step 6: exact-match approved group IDs -> application authorities
Step 7: consult local active user, tenant and business permission
Step 8: deny if no entitled authority or wrong resource tenant
~~~

Never use a **custom attribute mapper** to replace provider signature/audience/timestamp/replay validation. Custom mapping must run **after** trusted authentication context establishment or inside a converter invoked by the provider only after documented checks pass.

To distinguish **signing failures** from **business attribute failures**, use error codes:

~~~text
SAML_SIGNATURE_INVALID
SAML_DECRYPTION_FAILED
SAML_AUDIENCE_MISMATCH
SAML_TIME_INVALID
SAML_REPLAY_DETECTED
ATTR_REQUIRED_MISSING
ATTR_CARDINALITY_INVALID
ATTR_VALUE_TYPE_INVALID
APP_GROUP_NOT_APPROVED
APP_TENANT_ACCESS_DENIED
~~~

**Never write `SAMLResponse` values, keys, `NameID`, full group lists, or decoded XML to audit logs**; log a safe error class, verified registration ID, independent correlation ID, and latency.

## 14. Standalone Java 17: Attribute Contract After SAML Validation

The following example uses **standard Java 17 with no external libraries**, simulating `Map<String,List<?>>` after SAML is **assumed** to have passed signature/issuer/audience/time checks and decryption. **This is not a SAML verifier or XML decrypter.** Goal: test required tenant vs. optional email, multi-valued groups, data types, and authorization.

Create **`SamlAttributesContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class SamlAttributesContractDemo {

    static final String TRUSTED_IDP = "https://idp.example/metadata";

    record Identity(
            String issuer,
            String subject,
            Map<String, List<?>> attrs) { }

    static Map<String, List<?>> attrs(
            List<?> tenant,
            List<?> groups,
            List<?> email) {
        Map<String, List<?>> result = new HashMap<>();
        if (tenant != null) result.put("tenant", tenant);
        if (groups != null) result.put("groups", groups);
        if (email != null) result.put("email", email);
        return result;
    }

    static Identity user(Map<String, List<?>> values) {
        return new Identity(TRUSTED_IDP, "user-041", values);
    }

    static String decide(Identity input) {
        // The real SAML provider MUST validate this before mapping.
        if (!TRUSTED_IDP.equals(input.issuer())) {
            return "DENY: issuer";
        }
        if (input.subject() == null || input.subject().isBlank()) {
            return "DENY: subject";
        }

        List<?> tenant = input.attrs().get("tenant");
        if (tenant == null || tenant.isEmpty()) {
            return "DENY: tenant missing";
        }
        if (tenant.size() != 1
                || !(tenant.get(0) instanceof String value)
                || value.isBlank()) {
            return "DENY: tenant cardinality";
        }
        if (!"reports".equals(value)) {
            return "DENY: tenant mismatch";
        }

        List<?> groups = input.attrs().get("groups");
        if (groups == null || groups.isEmpty()) {
            return "DENY: no approved role";
        }
        if (groups.size() > 16) {
            return "DENY: group list too long";
        }

        boolean hasApprovedGroup = false;
        for (Object element : groups) {
            if (!(element instanceof String group)
                    || group.isBlank()
                    || group.length() > 128) {
                return "DENY: invalid group value";
            }
            if ("APP_REPORT_VIEWERS".equals(group)) {
                hasApprovedGroup = true;
            }
        }
        return hasApprovedGroup
                ? "ALLOW: ROLE_REPORT_VIEWER"
                : "DENY: no approved role";
    }

    public static void main(String[] args) {
        Map<String, List<?>> basic = attrs(
                List.of("reports"),
                List.of("APP_REPORT_VIEWERS"),
                List.of("lan@example.test"));

        System.out.println("Valid: " + decide(user(basic)));

        System.out.println("Missing optional email: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("APP_REPORT_VIEWERS"),
                    null))));

        System.out.println("Multi-valued groups: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins", "APP_REPORT_VIEWERS"),
                    null))));

        System.out.println("Missing tenant: "
                + decide(user(attrs(
                    null, List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Two tenants: "
                + decide(user(attrs(
                    List.of("reports", "finance"),
                    List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Wrong tenant: "
                + decide(user(attrs(
                    List.of("finance"),
                    List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Unapproved groups: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins"), null))));

        System.out.println("Non-string group: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of(7), null))));

        System.out.println("Wrong issuer: "
                + decide(new Identity(
                    "https://other.example/metadata",
                    "user-041", basic)));

        System.out.println("Blank subject: "
                + decide(new Identity(
                    TRUSTED_IDP, "", basic)));

        System.out.println("External admin promoted: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins"), null))
                    .contains("ROLE_ADMIN"));
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac SamlAttributesContractDemo.java
java SamlAttributesContractDemo
~~~

**Exact stdout:**

~~~text
Valid: ALLOW: ROLE_REPORT_VIEWER
Missing optional email: ALLOW: ROLE_REPORT_VIEWER
Multi-valued groups: ALLOW: ROLE_REPORT_VIEWER
Missing tenant: DENY: tenant missing
Two tenants: DENY: tenant cardinality
Wrong tenant: DENY: tenant mismatch
Unapproved groups: DENY: no approved role
Non-string group: DENY: invalid group value
Wrong issuer: DENY: issuer
Blank subject: DENY: subject
External admin promoted: false
~~~

**Analysis:**

- **Valid:** right tenant and entitled group → application role granted in the **model**.
- **Missing optional email:** does not block authorization when email is display-only.
- **Multi-valued groups:** does not promote the first value `Domain Admins` to `ROLE_ADMIN`; still finds the permitted value.
- **Missing/Two tenants:** missing or multiple values for a cardinality-1 field both deny.
- **Wrong tenant:** even an approved group cannot view another tenant's resources.
- **Unapproved groups:** group data present without app entitlement → deny.
- **Non-string group:** never calls `toString()` on a non-string value to invent a role.
- **Wrong issuer/Blank subject:** fails in the model, though in production `issuer` must be **verified by the OpenSAML provider using signing certificates**, not simple string equality as in the demo.
- **External admin promoted:** `Domain Admins` does not automatically become admin in the Reports app.

This tests the **mapping contract**, not actual `EncryptedAssertion`. To test cryptography, use SAML fixtures signed/encrypted with **lab keys** through the real Spring filter/IdP—never call a demo function and claim decryption PASSED.

## 15. How to Build Meaningful SAML2 Test Fixtures

**Never edit signed plaintext XML** to build a "missing attribute" case. Doing so invalidates the signature, so the test fails at signature validation **before** running attribute logic; that proves nothing about missing-attribute handling.

Proper workflow with a test IdP:

1. Create a test SP EntityID/ACS and a dedicated lab public encryption certificate.
2. Configure the test IdP to issue `SAMLResponse` with the proper signing policy and SP public cert.
3. Create a **base fixture** with subject, valid `Conditions`, `SubjectConfirmationData`, audience, response correlation, signature, and attributes matching contract.
4. For each attribute case, modify the **IdP mapper/test data before the IdP signs/encrypts**, or use a SAML test library to rebuild and re-sign/re-encrypt the entire `SAMLResponse`.
5. Send real HTTP POSTs to Spring's ACS in staging through the same reverse proxy/binding as production.
6. Verify whether the Spring provider authenticates or rejects, then inspect local roles/tenant.
7. For encryption failure cases, keep attributes/signature valid yet encrypt with a **different SP public certificate** in the lab to isolate key-mismatch errors.
8. Never use production signing/decryption private keys in CI pipelines or public fixtures.
9. Never commit raw `SAMLResponse` payloads containing real NameIDs/PII; use dedicated test identities, secrets, and time-limited certificates.
10. After testing, purge credential artifacts from logs/HARs/test reports per policy.

### Four Main Fixture Groups

| Group | How generated | What it tests |
| --- | --- | --- |
| **Crypto positive** | IdP signs + encrypts with right SP public key | SP decrypts, verifies, authenticates, and maps permissions properly |
| **Crypto negative** | IdP signs validly yet encrypts with key mismatching SP | Fails at decryption; creates no session |
| **Attribute positive** | IdP issues valid signed encrypted assertion with missing **optional** field or multiple groups | Authenticates cleanly; mapper policy handles properly |
| **Attribute negative** | IdP issues valid signed encrypted assertion missing **required** field or with wrong type/cardinality | Crypto succeeds, yet local policy rejects |

**You must prove where the failure occurred**: "SAML failed" is merely a generic symptom. A missing-tenant test achieves its goal only if **signature/decryption succeeded** and the app rejected for missing tenant; if the signature broke, that test **did not test** missing tenant.

## 16. Layered Testing: Unit, Provider Integration, End-to-End

### Unit Tests for Business Mapping

Input: a typed `Map<String,List<Object>>` or interface, subject, and trusted IdP registration **assumed already authenticated**.

- Missing optional email → no NPE.
- Missing tenant → deny.
- Two tenants → deny.
- Group list with multiple values → processed completely.
- Wrong data type → deny per schema.
- Unknown group → no role.
- Duplicate groups → no privilege escalation.
- Blank `NameID`/identity key → deny.
- Test null list, empty list, whitespace, Unicode, and oversized inputs.

**Mock business mapping tests do not replace crypto tests** because no signature, encryption key, or XML parser is exercised.

### Provider / Spring Integration Tests

- Use the **real Spring Security SAML2 provider** and a test IdP/OpenSAML fixture builder.
- Test `RelyingPartyRegistrationRepository`, verification/decryption credentials, and ACS endpoint.
- POST Base64 `SAMLResponse` via exact HTTP binding into `Saml2WebSsoAuthenticationFilter`.
- Verify user authentication context, failure redirect/status, and that `SecurityContext` remains unset when decryption/signature fails.
- Verify local authority mapping and `requestMatchers` on resources.
- Never log `SAMLResponse`, decoded Assertion XML, or private keys in test output.
- Verify tests run against **resolved Spring Security/OpenSAML versions** rather than relying on outdated imports.

### E2E Browser + IdP

- Real browser/IdP, SAML HTTP POST auto-submit, reverse proxy, key rotation, and metadata discovery.
- Verify `SameSite` cookies across cross-site POSTs to ACS, `Secure`/`HttpOnly`, and proper SAML CSRF handling.
- Inspect network path from proxy/WAF to Spring to ensure no component logs raw `SAMLResponse`.
- Test multi-instance deployments sharing secret/key versions.
- Verify browser sessions are denied when identity/tenant is invalid.
- Test replay of the same Assertion ID/Response ID within the test window.

**Do not assume every missing required claim must return HTTP 401.** If the SAML provider authenticated the user yet the app lacks a role, the route may return **403**. If a custom authentication converter rejects the contract during authentication, it may trigger a login failure/redirect or 401. Tests must assert the expected stage **without hard-coding HTTP statuses before checking failure handler config**.

## 17. Detailed Integration Matrix: Encryption and Keys

| ID | Test case | PASS criteria |
| --- | --- | --- |
| C01 | `EncryptedAssertion` with right key and valid signature | Decrypts + verifies + validates, then authenticates |
| C02 | `EncryptedAssertion` with wrong SP key | Creates no `Authentication`/session; logs safe decrypt error |
| C03 | Missing private decryption key | Fails closed; never falls back to plaintext parser |
| C04 | SP certificate mismatches private key | Config/crypto fails; keypair mismatch diagnosed |
| C05 | IdP signing certificate not in trust set | Fails signature check even if decryption succeeds |
| C06 | Signed Response + `EncryptedAssertion` | Verifies per profile/issuer then processes |
| C07 | Signed Assertion that is encrypted | Decrypts to obtain Assertion, verifies signature properly |
| C08 | `EncryptedAttribute` inside a validly signed plaintext `Assertion` | Verifies + decrypts in the provider's proper order |
| C09 | `EncryptedID` carrying `NameID` | Subject mapping succeeds after decryption |
| C10 | Corrupted `CipherValue` / `EncryptedKey` | Never falls back to authenticated |
| C11 | Prohibited legacy encryption algorithm | Rejected per security baseline |
| C12 | Unsupported AES/key transport | Rejected, surfaces compatibility error; never enables weak crypto |
| C13 | Old/new decryption keys during rotation | Accepts only certs/keys permitted by policy |
| C14 | Pod A and Pod B hold differing keysets | E2E test catches drift before rollout |
| C15 | Tenant A's key decrypts tenant B | Prevents wrong realm/registration assignment and cross-tenant leakage |
| C16 | Plaintext Assertion when org mandates encryption | Policy enforcement detects/denies if configured mandatory |
| C17 | Response decrypted yet wrong audience | Fails protocol validation |
| C18 | Response expired or `NotBefore` in future | Fails per time/skew policy |
| C19 | `InResponseTo` mismatches login request | Rejected per SP-initiated flow policy |
| C20 | Replay old signed Assertion/Response | Rejected with proper replay detection |
| C21 | XML with DTD/external entity/oversized structure | Parser limits and rejects per policy |
| C22 | Missing key in secret mount or wrong permissions | Fails + alerts; never widens file permissions |

**Never feed plaintext XML to the provider post-decryption while bypassing signature verification** in a test helper. Tests must exercise **the actual library pipeline**.

## 18. Matrix for Missing, Empty, and Multi-Valued Attributes

| ID | Validly signed IdP data | Expected local mapping |
| --- | --- | --- |
| A01 | Tenant 1 value, approved group 1 value | Viewer role, right tenant |
| A02 | Email missing, tenant/group valid | Login does not fail merely because unneeded email is absent |
| A03 | DisplayName missing | Approved UI fallback, subject preserved |
| A04 | `AttributeStatement` completely absent | SAML auth may succeed; app lacks permissions per contract |
| A05 | Required tenant absent | Deny |
| A06 | Required tenant present with 0 values | Deny |
| A07 | Tenant value `""` | Deny |
| A08 | Tenant value whitespace-only | Deny |
| A09 | Tenant has 2 different values | Deny, no first-wins |
| A10 | Tenant has 2 identical values | Deny if strict cardinality 1 |
| A11 | Tenant 1 value outside allowlist | Deny |
| A12 | Group field missing/empty | Grant no `ROLE_REPORT_VIEWER` |
| A13 | Group has 2 values, approved value in second slot | Still grants `ROLE_REPORT_VIEWER` |
| A14 | Group list contains "Domain Admins" and approved group | Grants no `ROLE_ADMIN` |
| A15 | Group list contains only unknown values | Grants no app authorities beyond defaults |
| A16 | Duplicate group values | No privilege escalation, input bounded |
| A17 | Group value is a complex XML object | Deny/handle per schema; no blind cast |
| A18 | Group has 1000 values | Bounded input size/mapping policy |
| A19 | Group contains leading/trailing whitespace | Normalize only per contract; no substring role matching |
| A20 | Same `FriendlyName`, different `Name` | Never conflate two attributes |
| A21 | Same `Name` with different `NameFormat` | Never merge unless business contract allows |
| A22 | Repeated `Attribute` blocks with same Name | Handle duplicates/lists per policy; no silent overwrite |
| A23 | Email has 2 values when field is 0..1 | Never pick randomly; enforce ambiguous-email contract |
| A24 | `NameID` empty/missing | Deny identity link |
| A25 | Mutable email `NameID` when local ID uses email | Test email changes and prevent account collisions |
| A26 | Attribute encrypted and absent in plaintext post-decrypt | Maps as missing field; decrypt success does not imply full fields |
| A27 | Local account disabled after IdP SAML auth | Deny application access |
| A28 | Wrong tenant resource | Deny object/tenant access even with approved group |
| A29 | Old session keeps role after group revoked | Bound cache/session/revalidation per SLA |
| A30 | Multiple IdPs share `groups` name with different semantics | Map per issuer/registration contract |

## 19. AttributeValue Differences vs. Arbitrary Role Strings

SAML `AttributeValue` types can be `xs:string`, `xs:boolean`, `xs:integer`, or structured XML defined by extensions. When Spring returns `Map<String,List<Object>>`:

- **Never cast `(String) list.get(0)`** without checking cardinality/type, as `null`/non-strings throw exceptions.
- **Never call `String.valueOf(object)` to derive privileges**: Java Object/DOM `toString()` is not a safe claim value.
- **Never auto-split on commas/semicolons** unless the contract specifies that representation.
- **Never map by `FriendlyName`** when the IdP uses URI claim names as standard identifiers.
- **Never merge attributes across two Assertions** without verifying signatures, subject equality, conditions, and profile semantics.
- **Never default to "first assertion" or "first attribute"** to handle multi-assertion or duplicate-attribute ambiguity; the provider enforces validation policy, and the app adds business checks.

This matters especially in **multi-tenant SSO**: if `tenant` carries two values—one `reports` and one `payments`—reading the first while granting roles from the second creates **authorization confusion**. For identity-critical claims, requiring **exactly one value** is the conservative choice.

## 20. Authenticate Properly Before Mapping Data

A common broken test:

~~~text
Input: raw base64 SAMLResponse
Test helper: base64 decode -> XML parser -> find <Attribute Name="groups">
Test: groups contains admin => login success
~~~

This is **not** a SAML2 security test because it bypasses signatures, trust anchors, decryption, XML signature reference protections, audience, replay, timestamps, and recipient checks.

The right flow:

~~~text
Real signed/encrypted test response
  -> Spring SAML filter + OpenSAML provider validation
  -> authenticated principal + verified attribute Map
  -> role mapper tests
  -> application requestMatchers/tenant policy
~~~

If a test only targets mapping logic, **you do not need SAML XML**; unit-test it like the Java 17 section, explicitly documenting "input assumed authenticated." If a test targets cryptography, **never mock the provider to return true**; execute through the real provider.

### XML Signature Wrapping and XML Parsers

SAML has a history of **XML Signature Wrapping (XSW)** flaws when apps search for an Attribute/Assertion in the DOM outside the signature-protected subtree. OpenSAML handles signature reference details per config/profile. Avoid writing XPath like "grab the first Assertion anywhere" over request XML. Add negative tests with duplicate IDs/extra unsigned Assertions and confirm the framework rejects or never consumes unsigned/unvalidated values.

**Never enable XXE/DTD/external entity resolution** when parsing SAML XML. Cap request body size, XML nesting depth, and element counts; use actively maintained libraries with security patches applied.

## 21. Logs, PII, and Test Fixture Hygiene

Decrypted assertions can hold emails, employee IDs, groups, `NameID`, tenant, and sensitive identity data. Even in staging:

- Never log Base64 `SAMLResponse` or decoded XML to application logs, WAFs, APMs, HARs, CI artifacts, or public bug trackers.
- Never print private keys or full PEMs into test reports.
- Use synthetic identities and **lab-only certificates/keys**; never use production IdP keys.
- Log event codes such as `SAML_DECRYPTION_FAILED`, `ATTR_REQUIRED_MISSING`, and `APP_ROLE_DENIED`.
- When correlation is needed, use an **independent random ID**, never raw AssertionID/`NameID` or tokens without cause.
- Restrict access to heap dumps, exception attachments, network traces, and backups.
- On key mismatches, verify **fingerprints/cert metadata** through administrative channels instead of pasting private keys into chat.
- Keep log/fixture retention minimal and run cleanup scripts after test executions.

**Do not rely on XML Encryption to protect logs:** once decrypted, Spring holds plaintext assertions in memory; a careless debug statement can dump sensitive data in full.

## 22. Runbook When Tests Fail

| Symptom | Primary suspect | What NOT to do |
| --- | --- | --- |
| `EncryptedAssertion` fails to decrypt | Wrong private key/cert, key rotation, algorithm mismatch | Do not disable encryption/signature validation |
| Sporadic login failures per pod | Key/cert secrets drifted across replicas | Do not share one "backup" key across all tenants |
| Plaintext test PASSES, encrypted test FAILS | SP lacks decryption credential or algorithm interop | Do not blame the Attribute mapper |
| `EncryptedAssertion` PASSES, `EncryptedAttribute` FAILS | Different assertion decrypter/key config | Do not parse encrypted fields as plaintext |
| Signed Assertion verification fails after custom decryption | Wrong decrypt/verify ordering or XML mutation | Do not alter signature bytes or skip checks |
| `SAMLResponse` signature FAILS | IdP verification cert/issuer/key rollover | Do not trust arbitrary certificates |
| Issuer/Audience/Recipient fails | Wrong metadata/ACS/entity ID | Do not bypass conditions |
| Assertion expired/`NotBefore` | Clock/time profile issues | Do not widen skew indefinitely |
| SAML auth PASSES, app missing tenant | IdP mapper/claim `NameFormat`/expected name | Do not assign a default tenant |
| SAML auth PASSES, groups list empty | IdP group mapper/filter or user lacks entitlement | Do not assign `ROLE_ADMIN` by default |
| Multi-valued group reads only first value | `getFirstAttribute` used against contract | Read full list, allowlist exact values |
| Missing optional email throws NPE | Code assumed email is always present | Optional fallback and null-safety |
| Non-string object causes `ClassCastException` | Mapper casts to String without type checking | Type validation and safe errors |
| `FriendlyName` matches yet `Name` differs | Looks right in UI yet claim identifier differs | Fix `Name`/`NameFormat` contract |
| User sees another tenant's data | Tenant cardinality/mapping confusion | Fail closed + incident review |
| XML-editing test fails signature before mapper | Fixture was not re-signed/re-encrypted | Regenerate at test IdP or lab signer |
| Decrypted Assertion leaked in logs | Debug formatter / HTTP body capture | Disable capture, purge/revoke per policy |

**Diagnostic order:** (1) registration/ACS/issuer; (2) signing trust; (3) decrypt key/algorithm; (4) assertion validation; (5) name/attribute extraction; (6) business mapping; (7) local authorization. Never use a "user lacks permissions" error as an excuse to swap decryption keys.

## 23. Practical Case Studies

### Case A — Unencrypted SAML Works, Enabling Encryption Fails

The IdP team turns on `EncryptedAssertion`. Spring has the IdP's public certificate to verify signatures, but lacks the **SP private decryption key**.

**Conclusion:** configuring the IdP verification certificate is **not** a decryption credential. Supply the SP's matching `Saml2X509Credential.decryption(privateKey, cert)`, ensure the IdP encrypts with the corresponding public cert, and re-test E2E. Never disable encryption or signatures just to restore login.

### Case B — Missing Email with Stable NameID

The IdP omits `email` because it is unverified. SAML validation and tenant/groups are valid, and the app does not need email for authorization.

**Conclusion:** allow authentication/role mapping to proceed if email is **optional** per contract, with a UI fallback. Do not treat every missing attribute as a security incident, and never fabricate `email="admin@example"`.

### Case C — Two Tenant Values

The IdP emits `tenant=["reports","payroll"]` while the app expects exactly one. Legacy code calls `getFirstAttribute` and grants roles based on the Payroll group.

**Conclusion:** **deny** due to ambiguous tenant. Never pick the first value and never union two tenants, especially when tenant is a security boundary.

### Case D — Multi-Valued Groups and Domain Admins

The IdP sends `groups=["Domain Admins","APP_REPORT_VIEWERS"]`. The Reports app trusts only mapped group `APP_REPORT_VIEWERS`.

**Conclusion:** grant only `ROLE_REPORT_VIEWER`; `Domain Admins` is not an application role. If `getFirstAttribute("groups")` returned `"Domain Admins"`, fix business code to iterate the full list rather than rewriting IdP claims to rely on lucky ordering.

### Case E — "Missing Groups" Fixture Fails Signature Check

An engineer copies raw SAML XML from a test and deletes the group `Attribute` after the IdP already signed it.

**Conclusion:** signature failure is **expected**; the test **never reached** the business mapper. Regenerate/re-sign/re-encrypt using the test IdP or unit-test the mapper separately from a verified attribute Map.

### Case F — Key Rotation Causes Intermittent Failures

Pod A has private keys A+B, pod B has only A, and the IdP begins encrypting with B.

**Conclusion:** inspect secret/mount rollout across replicas; maintain key overlap per policy and metadata timing. Never print raw keys to logs for comparison; use managed fingerprints/cert IDs.

### Case G — `EncryptedAttribute` Fails Decryption While NameID Remains Valid

The Response Assertion is validly signed and `NameID` is readable, yet groups were encrypted with a mismatched cert/key.

**Conclusion:** never treat groups as absent and grant default roles. Provider decryption failures must be handled properly—**never establish an authenticated session on incomplete data** when a decryption failure signals a security/config error.

## 24. Testing Plan for IdP/SP Handoff

**Step 1 — Lock down the business contract:** which attributes are required, 0..1 or 0..N, `Name`/`NameFormat`, issuer, subject ID, group/role mapping, tenant, and active status.

**Step 2 — Lock down the crypto contract:** Response vs. Assertion signing, whether Assertion/Attribute/`NameID` are encrypted, public/private certs, algorithms, metadata, and rollover.

**Step 3 — Build lab identities:** no real PII; create normal users, multi-group users, users missing optional claims, wrong-tenant users, and disabled users.

**Step 4 — Generate valid fixtures:** test IdP signs/encrypts **after** changing mapper fields; never edit signed XML directly.

**Step 5 — Test the Spring provider:** positive encrypted login, wrong key/signature, wrong audience, timeout/replay, encrypted attribute/ID.

**Step 6 — Test the mapper:** missing/empty/multi-valued/type/cardinality cases; no role escalation; stable identity linking.

**Step 7 — Test authorization:** authenticated without app group → 403/deny per design; tenant mismatch → deny.

**Step 8 — Test operations:** key rotation, multi-node consistency, logging/privacy, metrics, and alerting; never post real keys/XML in tickets.

**Step 9 — Test cross-version:** resolved Spring Security 6/7, OpenSAML 4/5, and IdP XML encryption algorithms; compile/run integration tests.

**Step 10 — Record evidence:** test ID, fixture class, expected stage, outcome, secret-free correlation ID, provider version, and key certificate IDs/fingerprints.

Never claim "SAML encryption passed" merely because `<EncryptedAssertion>` appears in XML; **you must prove Spring decrypts, verifies, and enforces local policy properly**.

## 25. Final Checklist

- [ ] Distinguish `EncryptedAssertion`, `EncryptedAttribute`, and `EncryptedID`.
- [ ] Understand the IdP encrypts with the **SP public key**, and the SP decrypts with its **private key**.
- [ ] Distinguish the SP decryption private key from the IdP signing public certificate.
- [ ] Spring has exact `RelyingPartyRegistration` and decryption `Saml2X509Credential`.
- [ ] Signature, issuer, destination, audience, recipient, time, and replay checks are never bypassed.
- [ ] Decryption success and wrong-key failure are tested on the real provider.
- [ ] Signed/encrypted fixtures are generated **after** the test IdP mapper alters attributes.
- [ ] Signed XML is never edited directly and called a "missing attribute test."
- [ ] Required/optional claims have clear contracts and cardinality tests.
- [ ] Missing, empty list, blank, wrong type, and duplicate cases are all tested.
- [ ] Optional email/`displayName` never triggers NPEs or account collisions.
- [ ] Identity-critical subject/`NameID`/tenant never fall back to defaults or first-wins.
- [ ] `AttributeValue` is handled as 0..N and never assumed to be String.
- [ ] Multi-valued groups are iterated completely and mapped via allowlist.
- [ ] `Domain Admins` is never mapped to application `ROLE_ADMIN`.
- [ ] `Name`/`NameFormat` follow contract without blindly trusting `FriendlyName`.
- [ ] Values from multiple unverified Assertions are never merged.
- [ ] Spring Security 6/7 and OpenSAML provider/credential APIs are verified for the active version.
- [ ] Disabled local accounts, tenant/object authorization, and session lifecycles are tested.
- [ ] XSW/XXE/oversized XML/replay negative cases are tested.
- [ ] Overlap and rollback procedures exist for encryption certificate rotation.
- [ ] All SP pods share the same policy-approved keysets; tenant keys stay isolated.
- [ ] `SAMLResponse`, decoded Assertions, `NameID`/PII, and private keys are never logged.
- [ ] Metrics/error codes distinguish crypto failures from mapping/authorization failures.
- [ ] Unit, provider integration, and E2E browser/IdP tests are all executed.

## 26. Official References

1. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP flow, OpenSAML, `RelyingPartyRegistration`, and decryption credentials.
2. [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `OpenSaml5AuthenticationProvider`, response/assertion decrypters, attributes, authorities, and validation.
3. [Spring Security — SAML2 Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html): Spring Security 7 transition to `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor`.
4. [Spring Security — Saml2ResponseAssertionAccessor Javadoc](https://docs.spring.io/spring-security/site/docs/7.0.x/api/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html): `getAttributes()` and `getAttribute(String)`.
5. [Spring Security — Saml2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): legacy/7.x-deprecated API, `getFirstAttribute`, and list values.
6. [Spring Security — Saml2X509Credential Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html): signature verification, signing, and decryption credentials.
7. [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `EncryptedAssertion`, `EncryptedAttribute`, `Attribute`/`AttributeValue` cardinality, types, and semantics.
8. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO/`SubjectConfirmation` and SP obligations.
9. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): SP entity ID/ACS, `KeyDescriptor` signing/encryption.
10. [W3C — XML Encryption Syntax and Processing 1.1](https://www.w3.org/TR/xmlenc-core1/): XML encryption representation and algorithm considerations.
11. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML Signature, XSW, replay, and SP validation.
12. [OWASP — XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): secure XML parsing, XXE, and resource limits.
13. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): integration tests for security filters/authorization.
14. [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): preventing caching of sensitive info after SAML login.

**Summary:** SAML2 testing must prove **proper decryption using the SP's private key**, **complete signature/protocol condition verification**, and only then enforce **attribute and permission contracts**. `AttributeValue` may be absent, single-valued, or multi-valued; **a missing optional email differs from a missing required tenant**, and multi-valued groups must be evaluated via allowlists without granting admin privileges from arbitrary strings. Spring Security 6 and 7 differ in assertion-reading APIs; applications must verify their active version and test both the **provider crypto path** and the **local mapping/authorization path**, avoiding "false PASSes" from mocked validation or edited XML with broken signatures.