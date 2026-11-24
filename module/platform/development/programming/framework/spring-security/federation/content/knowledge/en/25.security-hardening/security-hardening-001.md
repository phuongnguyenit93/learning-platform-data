# XML Signature Wrapping and the Principle of Using Only Verified Assertions

> **Topic:** Spring Security – federation. **Group:** Security Hardening. This Knowledge document explains XML Signature Wrapping (XSW) attacks against SAML 2.0, why a signature that verifies successfully can still lead to logging in as the wrong identity, how to properly bind the signed XML element to the element consumed by the application, and how to implement, test, and operate Spring Security SAML 2.0 Login securely. The standalone Java 17 examples only illustrate structural/policy checks, not a SAML signature verification library.

## 1. Key Takeaways

One-sentence definition:

**XML Signature Wrapping (XSW) occurs when a valid signature protects XML object A, while the application reads the NameID, Attributes, or permissions from XML object B, which is outside the scope of that trusted signature.**

Points to remember:
- A valid `SignatureValue` does **not automatically** mean the identity data the SP is using has been authenticated.
- `ds:Reference URI` points to the **signed object**. You must verify that the Reference resolves uniquely to the expected Response/Assertion.
- The **signed object** must be the **consumed object**, or the consumed assertion must be proven to reside within the **verified signed Response subtree**.
- **Duplicate IDs, malformed XML structure, overly broad XPath, untrusted KeyInfo, and out-of-policy transforms** are common risks.
- Either the **Response** or the **Assertion** may be signed, depending on the SAML profile/IdP–SP contract; not every assertion necessarily needs its own signature when the Response is verified and covers it.
- Never mix a NameID from Assertion A and Attributes from Assertion B and treat both as authenticated.
- Beyond the XML signature, you must also validate **Issuer, Audience, Destination, Recipient, InResponseTo, Conditions, SubjectConfirmationData, replay**, and local account policy.
- With Spring Security, prefer `saml2Login` and the default OpenSAML provider; do not manually parse raw SAMLResponse into the Spring SecurityContext.
- Business roles must only be derived from a validated principal/attributes and an explicit authorization policy.

**Consequence of missing signed/consumed binding:** An attacker can exploit the parser and verifier selecting two different nodes to create a local session for a user or permissions not signed by the IdP.

## 2. SAML Web Browser SSO Context

Roles:
- **IdP:** Identity Provider that authenticates the user and issues the SAML Response/Assertion.
- **SP:** Service Provider, for example a Spring application at `https://portal.example.org`.
- **ACS:** Assertion Consumer Service, where the browser POSTs the SAMLResponse back to the SP.
- **RelyingPartyRegistration:** Spring Security configuration binding the SP entityID, ACS URL, trusted IdP issuer, verification credentials, and protocol settings.
- **Assertion:** SAML evidence describing the subject/authentication statement/conditions/attributes.
- **Response:** Protocol message containing an Assertion or EncryptedAssertion and Response-level fields.
- **ds:Signature:** XML Digital Signature that may be placed on the Response or Assertion.

Standard SP-initiated flow:

~~~text
Browser             Spring SP                  Trusted IdP
   | GET /private      |                            |
   +------------------>|                            |
   |<-- 302 AuthnRequest                           |
   +---------------------------------------------->|
   |                      IdP authenticates user    |
   |<-------------- Response via Browser -----------+
   |                                              |
   | POST SAMLResponse to SP ACS                 |
   +------------------>|                         |
   |                    Secure XML parsing       |
   |                    Select expected RP       |
   |                    Verify signature+key     |
   |                    Check signed coverage    |
   |                    Validate SAML conditions  |
   |                    Extract verified subject |
   |                    Load app account/roles    |
   |                    Create Authentication    |
   |<------ response ---+                         |
~~~

**The browser is not a trust anchor.** The SAMLResponse passes through the browser and can be modified, swapped, or replayed. All evidence must be verified by the server-side provider before the application trusts the NameID or Attributes.

### 2.1. XML security and SAML protocol security are two layers

**XML layer:** which data is signed, with which key, which ID/Reference, which transforms, and which node the parser selects.

**SAML layer:** whether the message matches the right IdP, SP, ACS, audience, time window, login session, request correlation, and replay policy.

An assertion signed with the right key but for the wrong Audience must be rejected. A Response with the right Audience whose signature only protects another node must also be rejected.

## 3. XML Signature Structure to Understand

| Component | Role |
|---|---|
| `<ds:Signature>` | Container of the XML signature |
| `<ds:SignedInfo>` | List of References, canonicalization, and SignatureMethod |
| `<ds:Reference URI="#id">` | Identifies the signed resource/element |
| `<ds:Transforms>` | Processes content before digesting; may include enveloped-signature and C14N |
| `<ds:DigestMethod>` | Hash algorithm for the Reference |
| `<ds:DigestValue>` | Digest of the referenced content after transforms |
| `<ds:SignatureMethod>` | Signature algorithm |
| `<ds:SignatureValue>` | Cryptographic signature over SignedInfo |
| `<ds:KeyInfo>` | Key hint information; **not a trust decision** |
| `ID="_A1"` | ID of the SAML Response/Assertion, which can be the target of a Reference |
| XML C14N | Canonicalization rules for XML data for signing/verification |

Example **illustrative sketch only, without a real signature**:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_A1"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_A1">
        <ds:Transforms>
          <ds:Transform Algorithm="urn:example:illustrative-transform"/>
        </ds:Transforms>
        <ds:DigestValue>ILLUSTRATION_ONLY</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>ILLUSTRATION_ONLY</ds:SignatureValue>
  </ds:Signature>
  <saml:Subject>
    <saml:NameID>alice@EXAMPLE.ORG</saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

The example intentionally omits required XMLDSig/SAML fields and uses illustrative variant URIs. **It is not a production-ready assertion or an exploit payload.** It merely shows the Reference pointing to the ID of the assertion itself.

### 3.1. A signature only protects the scope of its Reference and transforms

A signature can sign:
- **The entire Response** when the Reference points to the Response ID.
- **One Assertion** when the Reference points to the Assertion ID.
- Another XML object per XMLDSig policy, which cannot be assumed by default to be a SAML Web SSO identity assertion.

It does not automatically sign every sibling, every element named Assertion, every HTTP URI, or every DOM node in the document. The parser/verifier must not return a generic “signature valid” without tying it to the **Reference target**.

### 3.2. A valid signature has two distinct conditions

1. **Cryptographic validity:** SignatureValue, SignedInfo, DigestValue, and transforms verify correctly.
2. **Trust validity:** the public key used for verification belongs to the trusted IdP signing credentials of the exact RelyingPartyRegistration.

If an attacker signs XML with their own private key, cryptographic verification using the attacker's public key can return true. However, the SP **must not trust** them as a valid IdP just because XML KeyInfo contains that certificate.

## 4. XSW Arises from Two Inconsistent Ways of Selecting XML Nodes

A conceptual mistake:

~~~text
XML document supplied through browser
       |
       +-- Signature library:
       |      resolves Reference URI="#_SIGNED_A"
       |      verifies Assertion A -> true
       |
       +-- Application:
              searches raw XML for first Assertion
              picks Assertion B (different object)
              reads NameID/roles from B
              creates authenticated session
~~~

This is a **signed-object vs consumed-object mismatch** flaw. There is no need to break RSA or know the IdP private key to cause this discrepancy if the application accepts XML structures with multiple node choices.

### 4.1. Why is it called XML Signature Wrapping?

One variant moves the signed element to another branch of the XML document (while preserving the signed content, depending on canonicalization/signature type), while placing an unsigned element in the branch the application prioritizes reading. The signature verifier can still resolve the ID of the signed node correctly, while the application parser finds a different object.

Related techniques to defend against:
- Duplicate IDs.
- Signed node nested inside an unexpected wrapper.
- Multiple Assertions.
- Overly broad XPath or selecting first/last.
- XML namespace/prefix confusion.
- Different parsers between the signature verifier and business code.
- Signed Reference pointing to an object other than the expected SAML Assertion.
- Untrusted KeyInfo or out-of-policy transform dereferencing.
- Reparsing data after verification without preserving the binding to the verified object.

### 4.2. XSW does not necessarily make the signature invalid

In some XSW scenarios, the signed element A itself remains intact and A's signature **still verifies as valid**. The vulnerability occurs because the application uses **object B**, which is outside the covered signed scope.

However, if the **entire Response is signed and the signature actually protects child Assertions**, modifying the content of children within the protected subtree **will normally cause signature/digest failure**. One should not wrongly claim that an assertion can be injected into any signed Response while keeping the signature valid; that is only exploitable when there is **scope, ID, XPath, or parser ambiguity**.

## 5. Security Invariant: Use Only Assertions Protected by a Signature

The acceptance condition should be stated explicitly:

~~~text
Accept a SAML subject/attribute as authenticated ONLY IF:

1. XML parsed under a secure SAML-aware parser/profile.
2. Expected XML Signature(s) verified cryptographically.
3. Signing credential is trusted for the selected IdP.
4. Reference URI uniquely resolves to an allowed signed object.
5. The consumed Assertion is EXACTLY the verified signed
   Assertion, or is demonstrably inside the verified
   signed Response's protected content.
6. No other unsigned/untrusted Assertion contributes to
   NameID, Attributes, Groups or application roles.
7. Issuer, Audience, Recipient, InResponseTo, time
   conditions, replay and local authorization checks pass.
~~~

**A valid signature on node A must not serve as a passport for node B.**

### 5.1. What must remain invariant between validation and business code

- **Object identity:** the assertion used for authentication is the exact instance/validated security object from the provider.
- **Document identity:** do not reparse a different XML with a different parser to extract the NameID.
- **Provider identity:** the signing key and issuer must belong to the trusted registration.
- **SAML protocol context:** correlation and conditions apply to the exact assertion being consumed.
- **Attribute provenance:** do not mix attributes from an unvalidated assertion.
- **Local identity and role policy:** role mapping is based on the verified subject and configured trust, not raw XML.

If the framework returns a `Saml2AuthenticatedPrincipal`, the controller uses that object instead of trying to select an Assertion directly from the DOM.

## 6. Signed Assertion and Signed Response Are Not the Same Thing

### 6.1. Assertion-signed model

~~~text
Response ID=R1
  |
  +-- Assertion ID=A1
        |
        +-- ds:Signature
        |      ds:Reference URI="#A1"
        |
        +-- Issuer / Subject NameID
        +-- Conditions / Audience
        +-- SubjectConfirmationData
        +-- AttributeStatement
~~~

When only Assertion A1 is signed, the SP must:
- Verify A1's signature using the right trusted IdP key.
- Verify A1 is the node consumed by the application.
- Check Response-level Issuer, Destination, Status, InResponseTo, and relevant SAML Web SSO rules.
- Check Assertion Conditions, Audience, Recipient, time window, and replay.
- Do not read NameID from a sibling unsigned Assertion A2.

### 6.2. Response-signed model

~~~text
Response ID=R1
  |
  +-- ds:Signature
  |      ds:Reference URI="#R1"
  |
  +-- Assertion ID=A1
        |
        +-- Subject, Conditions, Attributes
~~~

If R1 is genuinely signed and verified with a trusted IdP key, A1 is inside R1's covered subtree, and all SAML protocol checks pass, then A1 can be used **even when A1 does not have its own signature**. Do not apply a “every Assertion must be individually signed” rule to all SAML profiles.

### 6.3. Both Response and Assertion are signed

Many deployments sign both:
- Maintain all checks per the IdP–SP contract.
- Invalid signatures must not be silently ignored.
- Do not select another assertion after verifying one signature.
- Check between the Response issuer and Assertion issuer per policy.
- Multiple Assertions must have an explicit policy.

Current Spring Security documentation describes the OpenSAML provider verifying signatures on the Response/Assertion, and essentially **either the Response or all Assertions must be protected by a signature**. What matters is that the library only maps identity **after** verification.

### 6.4. A Signed Assertion can still not be meant for this SP

An assertion with a valid IdP signature must still be rejected when:
- `AudienceRestriction` does not contain the right SP entityID.
- `Recipient` is not the SP's ACS.
- `Destination` is wrong.
- `InResponseTo` does not match a pending AuthnRequest.
- `NotBefore` or `NotOnOrAfter` is invalid.
- `SubjectConfirmationData.NotOnOrAfter` is expired.
- `Issuer` does not belong to a trusted IdP.
- The Assertion ID has already been replayed.
- The local user is locked or lacks permission to access the tenant.

Signature validation is a mandatory part of verification; **it does not replace protocol checks**.

## 7. XSW Patterns to Include in the Threat Model

The models below are **illustrative structural XML for review**, not complete SAML messages or signed exploit payloads.

### 7.1. Signed object moved to another branch

~~~xml
<p:Response xmlns:p="urn:oasis:names:tc:SAML:2.0:protocol"
            xmlns:a="urn:oasis:names:tc:SAML:2.0:assertion"
            ID="_R1">
  <a:Assertion ID="_UNSIGNED">
    <a:Subject>
      <a:NameID>untrusted-user@example.org</a:NameID>
    </a:Subject>
  </a:Assertion>
  <p:Extensions>
    <a:Assertion ID="_ORIGINAL_SIGNED">
      <a:Subject>
        <a:NameID>alice@example.org</a:NameID>
      </a:Subject>
    </a:Assertion>
  </p:Extensions>
</p:Response>
~~~

**Note:** This Response is not SAML Schema-compliant XML and contains no real XML signature. It only illustrates how a verifier could check the ID of an object in another branch while the application looks for a direct Assertion. Strict schema/profile validation must reject invalid structures.

### 7.2. Duplicate XML ID

~~~xml
<root xmlns:a="urn:oasis:names:tc:SAML:2.0:assertion">
  <a:Assertion ID="_same">...</a:Assertion>
  <a:Assertion ID="_same">...</a:Assertion>
</root>
~~~

This is also **not** a valid SAML Response. If the signature resolver and application differ in how they select an element for a duplicate ID, there is a risk of verifying one node and using another. **Reject the entire document** when a required ID is not unique.

### 7.3. Signed/unsigned Assertions coexisting

~~~text
Response
  Assertion A1: signed and verified
  Assertion A2: unsigned; NameID differs
App:
  picks A2 merely because it appears first
~~~

That is a bug. When the profile forbids it, reject multiple/mixed assertions. If the deployment supports multiple valid assertions, you must verify the coverage of each consumed assertion and **never mix claims** across objects.

### 7.4. Signature signs a different node

A valid signature may protect an XML element other than the SAML login Assertion. If the app still reads the username from an Assertion outside the signed scope, there is no proof of identity. Do not just check “the document contains a ds:Signature and verify returns true”.

### 7.5. Prefix and XPath confusion

XML namespace prefixes are not immutable element identities. Avoid:
- `getElementsByTagName("saml:Assertion")` on raw XML.
- `getElementsByTagName("NameID").item(0)`.
- Wildcard/local-name XPath missing the expected namespace.
- Searching for `Attribute Name=role` across arbitrary descendants.

You must parse namespace-aware, validate schema/profile, and only use SAML objects verified by the provider.

## 8. XML Reference URI and ID Resolution

### 8.1. Same-document ID reference

A typical enveloped signature uses:

~~~xml
<ds:Reference URI="#_A1"
              xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:Transforms>
    <ds:Transform Algorithm="urn:example:approved-transform"/>
  </ds:Transforms>
  <ds:DigestValue>ILLUSTRATION_ONLY</ds:DigestValue>
</ds:Reference>
~~~

In SAML verification, the Reference should point to the exact ID of the expected Response/Assertion per profile; external references are not allowed by default.

### 8.2. An ID attribute does not automatically become a typed XML ID

Depending on the DOM/parser, an attribute named `ID` is not automatically recognized as an XML ID without schema/ID registration. However, manually calling `setIdAttribute` is also dangerous without checking:
- Does the node belong to the expected namespace and position?
- Is there any duplicate ID value across the entire parsed document?
- Could the resolver find another node?
- Is the Reference target the exact object intended to be signed?
- Do the transforms alter the semantics of the signed content?

**Do not “fix” ID resolution errors by picking the first element.** Reject ambiguous references.

### 8.3. Use only appropriate transforms

W3C XML Signature Best Practices recommends applications enforce strict rules:
- Local ID references.
- Enveloped signature transform where applicable.
- Approved canonicalization.
- Restrict the transform chain; disallow arbitrary XSLT.
- Check what is signed, not just the signature in general.

External Reference URIs can be abused for SSRF/file read when the library allows file/network dereferencing. Use the library's secure validation and allowlist rules.

### 8.4. Canonicalization does not mean authenticated data selection

C14N resolves XML representation differences during signing/verification. It does not decide:
- Which node should provide the NameID.
- Which IdP is trusted.
- Whether Audience/Recipient are valid.
- Whether there are duplicate IDs.
- Whether business role mapping is safe.

A valid signed canonicalized subtree is meaningless if the application reads data from a different subtree.

## 9. Trusted IdP Signing Keys and KeyInfo

**Do not use a certificate in incoming KeyInfo as the sole source of trust.** An attacker can sign XML with their own private key and insert their certificate into KeyInfo. The signature will be mathematically valid under that public key, but the signer is not an IdP approved by the SP.

Trust sources:
- Configured Spring `RelyingPartyRegistration`.
- IdP metadata administratively verified over a trusted channel.
- Approved signing credentials/certificates for the IdP entityID.
- Metadata signature validation/certificate rollover per organization policy.
- Separate multi-tenant registrations when there are different IdPs.

### 9.1. Certificate rollover

During an IdP key rotation period, the SP may accept multiple approved signing credentials. However:
1. Update approved metadata through a trusted channel.
2. Do not automatically trust KeyInfo from a request.
3. Verify certificate/key association with the IdP issuer.
4. Enforce expiry and retirement per agreed policy.
5. Do not disable signature validation to “fix login errors”.

### 9.2. Signature algorithms

Signature and digest algorithms must be on an organizational cryptographic algorithm allowlist, such as RSA-SHA256 or a profile-appropriate equivalent. Reject SHA-1/MD5-based signatures or weak transforms when disallowed by the security baseline. **Do not check only SignatureMethod while ignoring DigestMethod/Transforms.**

## 10. Secure XML Parsing, Schema Validation, and XXE

XSW also exploits quirks when an XML parser accepts structures that violate the profile.

**Defensive steps:**
1. Limit HTTP request size, Base64 decoded size, and XML node count/depth.
2. Use a namespace-aware XML parser.
3. Enable JAXP secure processing/disable DTD/restrict external entities.
4. Disallow XXE or automatic downloading of external DTDs/schemas.
5. Perform schema validation using a **local, trusted, and hardened** SAML XSD when applicable.
6. Verify the exact `samlp:Response` root and SAML Web SSO-compliant child structure.
7. Check for duplicate IDs.
8. Verify XMLDSig Reference, transforms, digest, and signature.
9. Use the exact validated assertion object, not global DOM search.
10. Validate SAML protocol conditions and session security.

The OWASP SAML Security Cheat Sheet recommends schema validation before using XML for security decisions, using a local trusted schema and not downloading schemas from untrusted URLs.

**XXE and XSW are two different vulnerabilities:**
- XXE/DTD targets external entities, local files, SSRF, and DoS.
- XSW targets signed-node/consumed-node mismatch.

Blocking XXE does not replace checking signature coverage; checking signatures also does not justify enabling XXE.

### 10.1. Schema is not a silver bullet

Schema validation is very useful for rejecting misplaced signed assertions, nested extensions, and elements disallowed by the profile. However, Reference target checks, key trust, unique IDs, parser consistency, and protocol validation are also required; do not treat schema alone as sufficient against XSW.

## 11. Reasonable Validation Order

A secure high-level pipeline:

~~~text
1. Resolve trusted relying-party registration and ACS context
2. Decode POST body with size limits
3. Secure XML parse and schema/shape validation
4. Identify expected Response/Assertion signatures
5. Validate cryptographic signatures using approved IdP keys
6. Bind exact signed object(s) to selected Assertion(s)
7. Decrypt EncryptedAssertion/EncryptedAttribute in safe
   protocol-dependent order
8. Check Issuer, Destination, Status, Audience, Recipient,
   Conditions, SubjectConfirmation, InResponseTo
9. Reject replay and unsolicited flows outside policy
10. Map verified NameID and verified Attributes to local account
11. Load approved GrantedAuthority data and tenant membership
12. Create Spring Security Authentication
~~~

**Note on decryption order:** With a signed Response, decryption of encrypted assertions can happen after the Response signature has been verified; with a signed assertion and encrypted inner fields, decrypting before signature verification can alter the signed subtree. Use the default order managed by OpenSAML/Spring provider, and do not treat this checklist as code replacing the concrete algorithm.

### 11.1. Which object does the signature belong to?

Must prove:
- Reference URI = `#Response.ID` for a Response-signed profile or `#Assertion.ID` for an Assertion-signed profile.
- The resolved object is unique, belongs to the current document, and is the expected element.
- The signing key belongs to the right IdP registration.
- Consumed NameID/Attributes reside inside the protected object.
- No unsigned alternate assertion supplies data for local authentication.

### 11.2. Do not reparse and manually select nodes after verification

If the library verifies DOM A but the application reparses the XML into DOM B and uses `getElementsByTagName`, it is very difficult to prove that B uses the same verified node. Prefer a single SAML object graph inside the trusted provider and only pass `Saml2AuthenticatedPrincipal` to the business layer.

## 12. SAML Fields to Validate Alongside the Signed Assertion

| Field | Validation Condition |
|---|---|
| Response `Issuer` | Trusted IdP entityID in the right RP registration |
| Assertion `Issuer` | Matches trust context/profile |
| Response `Status` | Success; do not turn an error Response into login |
| Response `Destination` | Exact public HTTPS ACS URL |
| Response `InResponseTo` | Matches pending AuthnRequest when SP-initiated |
| Assertion `Conditions.NotBefore` | Not too early outside clock skew |
| Assertion `Conditions.NotOnOrAfter` | Not yet expired; exclusive boundary |
| `AudienceRestriction` | Contains permitted SP entityID |
| `SubjectConfirmation.Method` | Bearer/approved method per profile |
| `SubjectConfirmationData.Recipient` | Exact ACS endpoint |
| `SubjectConfirmationData.InResponseTo` | Correlate AuthnRequest if required |
| `SubjectConfirmationData.NotOnOrAfter` | Not yet expired |
| `AuthnStatement` | Present/compliant with profile and authentication context per policy |
| Assertion ID | Anti-replay scoped by trusted issuer and TTL |
| `RelayState` | State/correlation, safe return URL allowlist |
| NameID/AttributeStatement | Read only from the validated protected assertion |

**Do not mix Conditions from A, NameID from B, and groups from C.** Every business identity must have proof tied to the exact assertion consumed.

### 12.1. SP-initiated vs IdP-initiated

**SP-initiated:** The app sent an AuthnRequest and has a pending ID; it must verify InResponseTo and subject confirmation correlation per profile. If the IdP misbehaves, do not disable correlation to “make login easier”.

**IdP-initiated/unsolicited:** May lack an AuthnRequest/InResponseTo per its own profile. Only accept if the organization explicitly enables/permits it, with stricter issuer, signature, ACS, Audience, Recipient, replay, login-CSRF, and landing policy. If not needed, disable unsolicited login.

### 12.2. Replay and time

A valid signature does not mean a fresh assertion. Replay cache, TTL, duplicate IDs, and session correlation are still needed. Multiple replicas should use appropriate shared replay state. Clock skew should be small and justified, not extended excessively to pass failing tests.

## 13. Spring Security SAML 2.0 Login and OpenSAML

Components in Spring Security Servlet:
- `Saml2WebSsoAuthenticationFilter` receives the SAMLResponse at the ACS.
- `Saml2AuthenticationTokenConverter` creates the token and resolves the registration.
- `OpenSaml5AuthenticationProvider` (per current Spring documentation) uses OpenSAML to handle XML, signature, decryption, and conditions.
- `RelyingPartyRegistrationRepository` holds SP/IdP metadata.
- `Saml2Authentication` contains the authenticated principal/response per the API.
- `Saml2AuthenticatedPrincipal` provides the verified subject/attributes after provider verification.
- `SecurityContextHolder` holds the successful Authentication.
- HTTP authorization/method security enforces local roles.

According to Spring Security documentation, the authentication provider:
1. Unmarshals the Response.
2. Verifies the Response signature if present.
3. Decrypts EncryptedAssertion per strategy.
4. Validates Response Issuer/Destination.
5. Verifies Assertion signatures; ensures Response or Assertions are signed per policy.
6. Decrypts inner encrypted IDs/attributes at the appropriate step.
7. Validates Conditions, Subject, Audience, and required attributes.
8. Converts the verified assertion into Saml2AuthenticatedPrincipal/Authentication.

**Do not copy “take the first assertion” logic outside the provider before verification.** Even if the provider, after validating everything, may choose the first assertion as the principal, that does not guarantee a custom parser outside the provider can safely do the same.

### 13.1. Custom validators can silently weaken controls

Spring Security allows customizing ResponseValidator/AssertionValidator. When customizing:
- Prefer **adding** checks to defaults rather than replacing the entire default validator list.
- Do not drop Issuer, Destination, Audience, or BearerSubjectConfirmation.
- Do not drop InResponseTo just to support a non-profile-compliant test Response.
- Do not use an unverified response token to map NameID.
- Include negative tests for XSW and expired/redirected assertions.

### 13.2. Multi-IdP configuration

In multi-IdP/tenant applications:
- Registration must be selected from trusted routing/session context.
- Signing keys are bound to the corresponding issuer.
- Assertion Issuer and Response Issuer must match trust configuration.
- Audience/Recipient and ACS match the SP registration.
- Identity-linking creates local users in the right tenant.
- Do not accept “valid key of IdP A, attributes of IdP B”.

## 14. Spring Security Java 17: Minimal Secure Configuration

File `src/main/java/com/example/security/SamlSecurityConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Explanation:** `saml2Login(Customizer.withDefaults())` uses the Spring Security SAML authentication path instead of manually parsing XML to extract the user. This is a **Spring configuration class**, not standalone Java; it requires a Spring Boot app/project, RelyingPartyRegistration, IdP metadata/certificates, ACS URL, HTTPS, and business authorization. Do not run `javac SamlSecurityConfiguration.java` without dependencies.

### 14.1. Spring Boot properties fragment

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          portal:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

The value is a **simulated IdP endpoint**. Production must only connect to organization-approved/pinned metadata with TLS/metadata signatures per policy; never read metadata URIs from arbitrary user requests. Check exact property names for the Spring Boot release used in your project.

### 14.2. Maven dependencies fragment

In a `pom.xml` that already has a Spring Boot parent/BOM:

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
</dependencies>
~~~

Manage compatibility across Spring Security/OpenSAML/Apache Santuario/XMLDSig/JDK. Do not mix jars across versions or disable secureValidation because of signature parsing errors. This fragment is not a standalone POM.

## 15. Reading the Principal Properly After Spring Authentication

File `src/main/java/com/example/web/MeController.java`:

~~~java
package com.example.web;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MeController {

    public record CurrentUser(String verifiedName) {
    }

    @GetMapping("/me")
    public CurrentUser me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Source: authenticated SAML principal created by provider.
        // NEVER re-read NameID from raw SAMLResponse XML.
        return new CurrentUser(principal.getName());
    }
}
~~~

This is a **Spring MVC class** requiring the framework runtime, not standalone. It only reads user identity after Spring Security SAML provider authentication. Never read raw SAMLResponse from the request.

**Not every verified NameID is a stable local user ID.** There are transient/persistent/email NameID profiles. Local account linking must rely on trusted issuer + stable subject contract, unique local mapping, tenant, and account lifecycle.

### 15.1. Attributes and permissions

A verified SAML AttributeStatement may contain groups/department. However, a `groups=Admin` claim does not automatically grant `ROLE_ADMIN`. Only map authorities via a trusted IdP/tenant allowlist and local policy. An assertion signed with the right key can still contain a claim insufficient for business privileges if the IdP contract does not authorize that claim.

## 16. Standalone Java 17: Checking the Policy signed object = consumed object

This program runs on JDK 17+. It **assumes** a trusted signature verifier has already produced `SignatureProof`. It is an exercise on **correct object/coverage**, **not a real XML signature verification program**.

File `SignedAssertionBoundaryDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class SignedAssertionBoundaryDemo {

    enum Coverage { ASSERTION, RESPONSE }

    record Assertion(String id, String nameId) {
    }

    record SignatureProof(
            Coverage coverage,
            boolean cryptographicallyValid,
            boolean trustedKey,
            String signedObjectId,
            Set<String> coveredAssertions) {
    }

    static String consume(
            SignatureProof proof,
            List<Assertion> directAssertions,
            String selectedId) {

        if (!proof.cryptographicallyValid() || !proof.trustedKey()) {
            return "REJECT_SIGNATURE";
        }

        if (directAssertions.size() != 1) {
            return "REJECT_ASSERTION_SHAPE";
        }

        Assertion selected = directAssertions.get(0);
        if (!selected.id().equals(selectedId)) {
            return "REJECT_SELECTION";
        }

        boolean covered = switch (proof.coverage()) {
            case ASSERTION ->
                    selected.id().equals(proof.signedObjectId());
            case RESPONSE ->
                    proof.coveredAssertions().contains(selected.id());
        };

        if (!covered) {
            return "REJECT_NOT_COVERED";
        }

        return "AUTHENTICATED:" + selected.nameId();
    }

    public static void main(String[] args) {
        Assertion alice = new Assertion("a1", "alice");
        Assertion alternate = new Assertion("a2", "other");

        SignatureProof signedAssertion = new SignatureProof(
                Coverage.ASSERTION, true, true, "a1", Set.of());

        SignatureProof signedResponse = new SignatureProof(
                Coverage.RESPONSE, true, true, "r1", Set.of("a1"));

        SignatureProof untrusted = new SignatureProof(
                Coverage.ASSERTION, true, false, "a1", Set.of());

        System.out.println("verified=" +
                consume(signedAssertion, List.of(alice), "a1"));
        System.out.println("swapped=" +
                consume(signedAssertion, List.of(alternate), "a2"));
        System.out.println("multiple=" +
                consume(signedAssertion,
                        List.of(alice, alternate), "a1"));
        System.out.println("untrusted=" +
                consume(untrusted, List.of(alice), "a1"));
        System.out.println("response-signed=" +
                consume(signedResponse, List.of(alice), "a1"));
    }
}
~~~

Commands:

~~~bash
javac SignedAssertionBoundaryDemo.java
java SignedAssertionBoundaryDemo
~~~

**Exact stdout:**

~~~text
verified=AUTHENTICATED:alice
swapped=REJECT_NOT_COVERED
multiple=REJECT_ASSERTION_SHAPE
untrusted=REJECT_SIGNATURE
response-signed=AUTHENTICATED:alice
~~~

**Explanation:**
- `verified`: model assumes signed Assertion A1 and consumed A1 match.
- `swapped`: A1 is signed but app picks A2 → reject.
- `multiple`: model only supports a single direct Assertion → reject.
- `untrusted`: signature is mathematically valid but key does not belong to a trusted IdP → reject.
- `response-signed`: simulates A1 protected by trusted signed Response R1.

**Absolute limitations:** the booleans and coveredAssertions in this demo do not come from a real SAML/XMLDSig verifier. If supplied by the browser, an attacker could arbitrarily set them to true. Do not use this class as real authentication logic, do not replace `OpenSaml5AuthenticationProvider`, and do not skip verification of issuer, signature, conditions, replay, and local user policy.

## 17. Standalone Java 17: Safe XML Parsing and Duplicate ID Detection

This exercise uses JDK JAXP DOM to teach a **preliminary XML shape guard**; it does not check cryptography and does not claim that accepted XML is a valid full SAML Response.

File `SamlXmlShapeDemo.java`:

~~~java
import java.io.StringReader;
import java.util.HashSet;
import java.util.Set;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public class SamlXmlShapeDemo {

    static final String P =
            "urn:oasis:names:tc:SAML:2.0:protocol";
    static final String A =
            "urn:oasis:names:tc:SAML:2.0:assertion";

    static Document parse(String xml) throws Exception {
        DocumentBuilderFactory f =
                DocumentBuilderFactory.newInstance();

        f.setNamespaceAware(true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        f.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return f.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }

    static boolean uniqueIds(Element e, Set<String> ids) {
        if (e.hasAttribute("ID")
                && !ids.add(e.getAttribute("ID"))) {
            return false;
        }

        for (Node n = e.getFirstChild();
                n != null; n = n.getNextSibling()) {
            if (n instanceof Element child
                    && !uniqueIds(child, ids)) {
                return false;
            }
        }
        return true;
    }

    static String inspect(String xml) throws Exception {
        Element root = parse(xml).getDocumentElement();

        if (!P.equals(root.getNamespaceURI())
                || !"Response".equals(root.getLocalName())) {
            return "REJECT_ROOT";
        }

        if (!uniqueIds(root, new HashSet<>())) {
            return "REJECT_DUPLICATE_ID";
        }

        int count = 0;
        for (Node n = root.getFirstChild();
                n != null; n = n.getNextSibling()) {
            if (n instanceof Element child
                    && A.equals(child.getNamespaceURI())
                    && "Assertion".equals(child.getLocalName())) {
                count++;
            }
        }

        return count == 1
                ? "SHAPE_ONLY_NOT_AUTHENTICATED"
                : "REJECT_ASSERTION_SHAPE";
    }

    public static void main(String[] args) throws Exception {
        String start =
                "<p:Response " +
                "xmlns:p='" + P + "' " +
                "xmlns:a='" + A + "' ID='R1'>";

        String good = start
                + "<a:Assertion ID='A1'/>"
                + "</p:Response>";

        String duplicate = start
                + "<a:Assertion ID='R1'/>"
                + "</p:Response>";

        String nested = start
                + "<p:Extensions><a:Assertion ID='A1'/>"
                + "</p:Extensions></p:Response>";

        System.out.println("good=" + inspect(good));
        System.out.println("duplicate=" + inspect(duplicate));
        System.out.println("nested=" + inspect(nested));
    }
}
~~~

Run:

~~~bash
javac SamlXmlShapeDemo.java
java SamlXmlShapeDemo
~~~

**Exact stdout:**

~~~text
good=SHAPE_ONLY_NOT_AUTHENTICATED
duplicate=REJECT_DUPLICATE_ID
nested=REJECT_ASSERTION_SHAPE
~~~

**Boundary explanation:**
- `good` only passes the shape guard demo; it has no signature, Issuer, SubjectConfirmation, or Conditions. **Do not log in**.
- `duplicate` has the same ID on Response and Assertion → reject.
- `nested` has no direct Assertion and instead a nested Assertion → reject per demo policy.
- The demo only checks the literal `ID` attribute and does not replace OpenSAML's schema-aware XML ID resolution/uniqueness checking.
- The parser blocks DTDs/external entities via JAXP features in an assumed JDK 17 environment. Production must verify the concrete parser implementation, exceptions, and limits.
- The XML examples are not complete SAML-compliant Responses, so do not use them as SAML authentication success integration tests.
- **A shape check does not prove identity.** Only the full SAML provider may create a SecurityContext.

## 18. EncryptedAssertion and Verify/Decrypt Order

SAML can use:
- `EncryptedAssertion`.
- `EncryptedID`.
- `EncryptedAttribute`.

**Encryption solves confidentiality, not signature authenticity.**

If a signed Assertion has encrypted elements inside it, decrypting before verifying the signature over the signed bytes/canonicalized structure can invalidate the signature. Spring Security documentation distinguishes response-level decrypters and assertion-level decrypters to process them in a safe order.

Required checks:
1. The decryption key belongs to an authorized SP.
2. Response/Assertion signatures are verified at the right layer.
3. Decrypted data remains inside the validated object graph.
4. Do not mix unsigned decrypted data with another signed assertion.
5. Check Audience/Recipient/Conditions after decryption per the SAML profile.
6. Have a policy for multiple EncryptedAssertions and mixed Assertions; reject unsupported forms.

**Do not conclude:** “Since it decrypted, it must have been sent by the IdP.” A ciphertext can be encrypted to the SP's public key by an untrusted party if there is no signature/protocol proof.

## 19. Apache Santuario Secure Validation

Apache Santuario supports XMLDSig verification and a secure validation mechanism. According to the Santuario FAQ, secure validation in supported versions:
- Limits the number of transforms and references.
- Prohibits XSLT transforms.
- Prohibits arbitrary filesystem/HTTP dereferencing.
- Blocks recursive RetrievalMethod patterns.
- Checks uniqueness of dereferenced IDs.
- Blocks DTDs and the MD5 algorithm.

A JSR-105 context can support the property:

~~~java
XMLValidateContext context =
        new DOMValidateContext(trustedKey, signatureElement);
context.setProperty(
        "org.apache.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
~~~

This is a **code fragment**; it requires imports, trustedKey, and signatureElement created within the proper XML security pipeline. Setting a flag to true alone does not verify SAML/KeyInfo trust/subject selection. Confirm default secureValidation and APIs for your exact Santuario/JDK versions.

### 19.1. Signature/digest policy

- Allowed SignatureMethod and DigestMethod values must be enumerated by the organization.
- Do not enable SHA-1-based signatures or MD5 when prohibited by the security baseline.
- Do not allow XSLT or external URI references outside policy.
- Do not accept all algorithms merely because the crypto library supports them.
- Audit changes to metadata keys/algorithms during IdP rollover.

## 20. Identity Linking and Authorization After Assertion Verification

Even with a verified protected assertion, the SP must still:
1. Bind to the approved IdP issuer/registration.
2. Select a stable identity key per NameID format/qualifiers or an attribute allowed by the IdP–SP contract.
3. Link to the right localUserId, never auto-merging on matching email alone.
4. Check account status (active/disabled/locked) and tenant.
5. Load GrantedAuthorities per approved group/role mapping.
6. Enforce resource-level permissions.

Example:
- Verified Assertion says `NameID=alice@example.org`.
- The app has a local user Alice belonging to tenant A.
- Tenant B also has a similar email.
- **Do not** automatically allow tenant B's local user to log in from the same subject merely because the email matches.

If the IdP sends the attribute `groups=Admin`, the app does not automatically grant `ROLE_ADMIN`; that is a separate authorization policy requiring an allowlist/identity authority contract.

### 20.1. An authenticated session still has a lifecycle

SAML signature verification at login does not guarantee the local session remains permitted forever. User disabling/group revocation requires handling session invalidation/role cache TTL and sensitive action rechecks. SAML assertions have their own validity window, while HttpSession lifetime is separate; never reuse a raw SAMLResponse to create a new session.

## 21. Positive Test Suite

| Case | Scenario | Expected Result |
|---|---|---|
| P1 | Trusted IdP signs Response, single Assertion inside signed subtree | Accept if protocol conditions pass |
| P2 | Trusted IdP signs Assertion, exact assertion consumed | Accept if Response context is valid |
| P3 | Both Response and Assertion signed properly | Verify per configured policy |
| P4 | Local Reference URI points to unique expected ID | Signature reference OK |
| P5 | Key rollover in approved trust set | New cert accepted per policy |
| P6 | Audience and Recipient match SP | Protocol validation passes |
| P7 | InResponseTo matches pending AuthnRequest | SP-initiated passes |
| P8 | Decrypt/verify EncryptedAssertion in proper order | Extract validated attributes |
| P9 | SAML valid but local user disabled | Deny business access |
| P10 | Proper multi-tenant issuer/registration mapping | Subject not confused across tenants |
| P11 | Verified assertion and allowlisted group | Correct GrantedAuthority |
| P12 | Valid Assertion ID/replay cache | Allowed use accepted |

## 22. Negative Test Suite Against XSW

| Case | Malformed / Attack Input | Result |
|---|---|---|
| N1 | Sign Assertion A1, app reads unsigned A2 | Reject |
| N2 | Sign A1 but app selects another first/last node | Reject |
| N3 | Duplicate XML IDs | Reject |
| N4 | Reference URI points outside expected Response/Assertion | Reject |
| N5 | External HTTP/file Reference URI | Reject |
| N6 | XSLT/unknown transforms | Reject |
| N7 | Signature valid using attacker KeyInfo certificate | Reject |
| N8 | Out-of-policy SHA-1/MD5 | Reject |
| N9 | Missing required trusted signature | Reject |
| N10 | Invalid signature on Response | Reject |
| N11 | Multiple signed/unsigned Assertions mixing claims | Reject |
| N12 | Raw DOM getElementsByTagName picks NameID | Security test fails |
| N13 | Audience does not belong to SP | Reject |
| N14 | Recipient does not match ACS | Reject |
| N15 | Destination does not match HTTPS/public host | Reject |
| N16 | InResponseTo mismatch | Reject SP-initiated |
| N17 | Expired Assertion Conditions | Reject |
| N18 | Expired SubjectConfirmationData | Reject |
| N19 | Assertion ID replay | Reject |
| N20 | Unknown issuer/key | Reject |
| N21 | Signed Response for tenant A used for tenant B | Reject |
| N22 | Parser reparses DOM B after verifying DOM A | Disallow identity from B |
| N23 | XML DTD/XXE/external entity | Reject |
| N24 | XML bomb/too many nested elements | Reject |
| N25 | Empty/invalid Response Status | Reject |
| N26 | Unsigned AttributeStatement carrying ROLE_ADMIN | Ignore/reject |
| N27 | Unexpected EncryptedAssertion mix | Reject |
| N28 | Custom validator drops Audience | Regression test fails |
| N29 | IdP-initiated when unsolicited is disabled | Reject |
| N30 | RelayState open redirect | Reject |
| N31 | Transient NameID auto-links to local admin | Deny account link |
| N32 | Valid signed assertion but local account disabled | Deny |

### 22.1. Regression tests must run against a real SAML provider

A mocked `assertTrue(signatureOk)` unit test does not prove XSW is blocked. The integration suite needs:
1. Test IdP signing keys/metadata and SP registration.
2. Valid signed baseline SAMLResponse.
3. Real HTTP POST to the Spring ACS.
4. Wrapped/multiple/duplicate ID cases in XML.
5. Reference/issuer/audience/correlation/timing failures.
6. Assert no authenticated SecurityContext is created on rejection.
7. Assert final principal/authorities come from the **exact accepted signed assertion**, not an unsigned alternate.
8. Certificate rollover/multi-IdP tests.
9. Replay/CSRF/session handling.
10. Log redaction and privacy checks.

There is no need to expose real payloads to end users. Test SAML messages and credentials should stay in a protected test harness, not in public logs/docs.

## 23. Symptom-Based Troubleshooting

| Symptom | Likely Cause | Diagnostic Direction |
|---|---|---|
| Signature valid but wrong user | Signed object differs from consumed object | Trace Reference and parsed object identity |
| Login succeeds despite unsigned Assertion | Custom converter/bypass | Restore defaults, add negative tests |
| Multiple Assertions lead to another user | Wrong policy/node selection | Validate all required signatures/coverage |
| Inconsistent duplicate ID lookup | ID registration/parser resolver | Reject duplicates, enable secure validation |
| KeyInfo contains unknown cert | Wrong trust selection | Use only approved registration signing credentials |
| Response signed but wrong Audience | Assertion validators dropped | Restore audience checks |
| Assertion signed but wrong Destination | Response protocol validators dropped | Check issuer/destination |
| Unsolicited/Replay login | Missing correlation/replay checks | Enforce InResponseTo, assertion ID cache |
| Signature fails after decrypt | Wrong verification order | Use library default pipeline |
| XML DTD blocked and IdP fails | IdP sends non-compliant XML | Fix IdP, never enable XXE |
| Different tenant gets same user | Multi-IdP registration mix-up | Match issuer/key/tenant scope |
| Certificate rollover breaks login | Unapproved metadata | Update trusted keys under change control |
| Unexpected admin role appears | Wrong raw attrs/mapper | Use only validated attrs and allowlist |
| One node accepts, one node rejects | Out-of-sync time, certs, or cache | Sync deployments |
| RelayState redirects to external URL | Open redirect | Enforce return URL allowlist |
| Disabled user can still access | Local account/session policy | Revoke sessions/roles |
| Spring login fails after custom validator | Default validations replaced | Compare with OpenSAML defaults |

## 24. Monitoring, Data Protection, and Incident Response

Metrics/logs to use:
- `saml_signature_validation_failed`.
- `saml_signature_untrusted_key`.
- `saml_reference_target_mismatch`.
- `saml_duplicate_id_rejected`.
- `saml_assertion_shape_rejected`.
- `saml_issuer_mismatch`.
- `saml_invalid_audience`.
- `saml_recipient_mismatch`.
- `saml_in_response_to_mismatch`.
- `saml_replay_rejected`.
- `saml_role_mapping_rejected`.

You may store correlation ID, RP registration ID, issuer category, latency, failure reason, and hashed principal per privacy policy. **Never log raw SAMLResponse, Base64 tokens, SignatureValue, PII attributes, private signing keys, or session cookies.**

If XSW is suspected:
1. Isolate recently changed custom XML parsers, SAML converters, or validators.
2. Identify exact Spring Security/OpenSAML/Santuario versions and advisories.
3. Cross-check logged-in principals against subjects in trusted signed assertions per incident process.
4. Revoke suspicious sessions and audit elevated permissions.
5. Restore strict signature/protocol validation and trusted keys.
6. Write regression tests for signed/consumed mismatch.
7. Ensure replay cache and metadata/tenant policies are active.
8. File a report/security review and monitor related events.

## 25. Secure Code Review Checklist

- [ ] SAML parsing uses OpenSAML/framework or a thoroughly reviewed parser.
- [ ] Namespace-aware and secure XML parsing; DTD/XXE disabled.
- [ ] Appropriate request/XML size/depth limits.
- [ ] Schema/shape validation from local trusted SAML schemas where applicable.
- [ ] No global DOM/XPath to extract security NameID from raw XML.
- [ ] Reference URI binds to exact unique expected Response/Assertion ID.
- [ ] Reject duplicate IDs and ambiguous dereferencing.
- [ ] Transforms/digest/signature algorithms are in the allowlist.
- [ ] No external Reference URI/filesystem/HTTP dereferencing.
- [ ] Trusted signing keys belong to the right RelyingPartyRegistration.
- [ ] Do not trust self-declared certificates in KeyInfo.
- [ ] Consumed assertion is the signed assertion or belongs to the verified signed Response subtree.
- [ ] Do not mix Attributes/NameID from different assertions.
- [ ] Validate Issuer, Destination, Status, Audience, Recipient, and Conditions.
- [ ] SubjectConfirmationData and InResponseTo comply with the profile.
- [ ] Replay detection and appropriate clock skew are enabled.
- [ ] Encrypted assertions are processed in the proper verify/decrypt order.
- [ ] Default validators are not dropped when customizing Spring Security.
- [ ] Multi-IdP/tenant does not mix issuer/cert/registration.
- [ ] Identity linking and role mapping use trusted validated data.
- [ ] Disabled accounts and tenant/resource authorization are enforced.
- [ ] No logging of SAML XML/tokens/PII/private keys.
- [ ] Test cases exist for XSW/duplicate ID/unsigned claims/reference mismatch.
- [ ] Checks exist for metadata signing certificate rotation.
- [ ] Any authentication failure does not create an authenticated session.
- [ ] Dependency versions and security advisories are kept up to date.

## 26. Self-Check Questions

1. **What is XSW?** The signature verifies node A while the app consumes node B.
2. **Why is a valid signature not enough?** The key might be untrusted, the signed target might differ from the consumed object, or SAML conditions might be invalid.
3. **What does Reference URI do?** Identifies the XML object protected by the signature.
4. **Why is a duplicate ID dangerous?** The resolver and the app may select two different objects.
5. **Is KeyInfo itself a trust anchor?** No.
6. **Can a signed Response protect an individually unsigned Assertion?** Yes, if the Assertion belongs to the covered verified subtree and protocol checks pass.
7. **Does a signed Assertion require the Response to always be signed?** Not in every profile; it must match the SP/IdP contract.
8. **Can you take the first Assertion before verification?** No.
9. **Can you read NameID with getElementsByTagName on raw XML?** Not for security decisions.
10. **Are XXE and XSW the same thing?** No.
11. **Is schema validation enough to stop XSW?** Not yet; signed scope, references, and key trust are also needed.
12. **Does C14N automatically map the right principal?** No.
13. **How must multiple Assertions be handled?** Only use validated protected assertions under a strict policy, or reject.
14. **Does encryption replace signatures?** No.
15. **What does the current Spring provider use?** OpenSAML/Spring SAML2 Login, for example OpenSaml5AuthenticationProvider.
16. **Where does a controller get the verified identity?** Saml2AuthenticatedPrincipal from the Spring SecurityContext.
17. **Why not override validators completely?** It is easy to drop Issuer, Audience, Destination, or InResponseTo.
18. **Response signed but wrong Audience?** Reject.
19. **When is InResponseTo important?** SP-initiated authentication correlation.
20. **Is IdP-initiated valid by default?** No, it requires an explicit unsolicited flow policy.
21. **What is a replay cache for?** Preventing reuse of assertions/responses within expiry/profile bounds.
22. **What must RelayState check?** State/correlation and a redirect URL allowlist.
23. **Does an Admin group in the assertion automatically grant ROLE_ADMIN?** No, app authorization mapping is required.
24. **Does the SignedAssertionBoundaryDemo verify real signatures?** No, it simulates proof to teach the invariant.
25. **Does SamlXmlShapeDemo returning SHAPE_ONLY mean the user is logged in?** No.
26. **What is the most severe design mistake?** Verifying node A and then reading identity from node B.
27. **Overarching principle?** Only create an Authentication from an assertion protected by a trusted IdP signature that has passed all SAML conditions.

## 27. Official References

- OWASP SAML Security Cheat Sheet, XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- W3C XML Signature Best Practices — Check what is signed: https://www.w3.org/TR/xmldsig-bestpractices/
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- Apache Santuario Secure Validation FAQ: https://cwiki.apache.org/confluence/spaces/SANTUARIO/pages/24193195/faq
- Spring Security SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security SAML 2.0 Relying Party configuration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP XML External Entity Prevention: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Summary:** XML Signature Wrapping exploits a **mismatch between the verified node and the node consumed by the application**. A valid signature is only trustworthy when the key belongs to the right IdP, the Reference URI points to the exact unique object, and the NameID/Attributes belong to the signed Assertion itself or a subtree protected by a trusted signed Response. Spring Security/OpenSAML must also validate issuer, audience, recipient, destination, time, InResponseTo, subject confirmation, and replay before creating an Authentication. Do not manually reparse raw SAMLResponse or select assertions with global XPath; always use the validated Saml2AuthenticatedPrincipal and continue enforcing local account, tenant, and business permissions.
