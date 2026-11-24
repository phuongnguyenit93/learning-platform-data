# Distinguishing trusted key identification from metadata vs. PKI chain validation

## 1. The real-world problem in Spring Security SAML2

When a **Spring Security** application is a **Service Provider (SP/Relying Party)** and receives a **SAMLResponse** from an **Identity Provider (IdP/Asserting Party)**, the SP must verify the digital signature using a public key the SP is **authorized to trust**. The hard question is not just "is the signature mathematically valid?", yet also:

- **Which public key** is permitted to verify messages from a **specific IdP**?
- Does that key come from **verified/accepted SAML metadata** or from a **certificate that chains to a Certificate Authority (CA)**?
- Must an **X.509Certificate** in metadata always be unexpired, have a subject matching the hostname, carry Extended Key Usage for TLS, and be signed by a public CA?
- Do **signatures on metadata**, **signatures on SAML Response/Assertion**, **TLS HTTPS**, **PKIX certification paths**, and **public-key pinning** mean the same thing?
- If the IdP rotates keys, replaces a certificate while keeping the public key, or changes CAs, should the SP accept the new messages?

**Core point:** in many SAML federations, **a certificate inside SAML metadata is a carrier for the partner's public key**, and the **trust decision** stems from **accepted metadata**. This differs from **PKIX path validation** (building and verifying an X.509 certificate chain from leaf to CA trust anchor). You should not treat the two models as equivalent or blindly impose one onto the other.

Per **OASIS SAML V2.0 Metadata Interoperability Profile 1.0 (24-10-2019)**, once a metadata instance has been accepted under the profile, the consumer **relies on the keys in KeyDescriptors belonging to the exact role**; the profile requires **not applying additional X.509 path/revocation/OCSP checks to those keys in runtime decisions**. That is a rule **of that specific profile**, not a claim that PKIX is useless or that every SAML product/organization must choose the same trust model. Systems using **PKIX-based trust policies** for metadata exchange, TLS, or another federation mechanism must identify exactly where and under what conditions it applies.

### What you must be able to explain afterward

1. How **EntityDescriptor/IDPSSODescriptor/KeyDescriptor** bind a public key to an IdP entityID.
2. The difference between **public key**, **X.509 certificate**, **certificate fingerprint**, **SPKI fingerprint**, **certificate chain**, **PKIX trust anchor**, and **SAML signature**.
3. What makes **metadata trustworthy** before the SP can trust the public keys inside it.
4. Why a **self-signed IdP SAML signing certificate** can still be validly used in the metadata trust model.
5. Why a **PKIX-valid certificate from an unknown IdP** is insufficient to log into the SP.
6. How to configure **Spring Security SAML2 SP** with metadata/certificates, test key rotation, and diagnose errors without disabling signature verification.

Exercises use **Java 17+**, with **Spring Boot 3.3.5 / Spring Security 6.x** examples. All `example.org` domains and simulated key data are strictly for learning.

## 2. First: valid signature differs from "trusted key"

A sound decision flow:

~~~text
Browser submits SAMLResponse to SP ACS
           |
           v
  Select RelyingPartyRegistration
  (exact SP/IdP per config and context)
           |
           v
  Retrieve APPROVED IdP public verification key
  from trusted metadata or matching static config
           |
           v
  Verify XML Signature with that key
           |
           +-- Invalid -> FAIL, do not create Authentication
           |
           v
  Check issuer, audience, destination, Recipient,
  time, InResponseTo, profile, replay...
           |
           +-- Invalid -> FAIL
           |
           v
  Valid Saml2Authentication -> local session/authorization
~~~

A **mathematically valid signature** means the signed bytes match the signature when checked with **a specific public key**. That alone **does not prove** that public key is authorized to represent the IdP the SP is logging into.

For example: an attacker generates their own RSA pair and signs a forged Assertion. **`Signature.verify()`** returns true when checked with the attacker's public key. Yet the SP must not treat it as IdP Corp if **the attacker's public key was not published by IdP Corp through an accepted trust channel**.

Conversely, even when a signature verifies against the trusted IdP key, the Response may still be rejected due to invalid **issuer, AudienceRestriction, Destination, SubjectConfirmationData.Recipient, InResponseTo, NotOnOrAfter**, or business rules.

### Four distinct security layers

| Layer | Subject | Question it answers |
| --- | --- | --- |
| **SAML metadata trust** | XML metadata received, source/signature verified, and accepted per policy. | Which partner, which role, and which public keys are permitted? |
| **XML Digital Signature** | Signature on Response, Assertion, AuthnRequest, or metadata. | Is the message unaltered and signed by the private key matching which public key? |
| **PKIX certificate path** | X.509 leaf → intermediate → CA trust anchor chain. | Is the certificate certified by a trusted CA under PKIX policy? |
| **TLS/HTTPS** | Connections between browser, SP, IdP, or when fetching metadata. | Is the channel to a valid hostname/certificate protected and authenticated per TLS policy? |

**Never substitute one layer for all the others.**

## 3. Where does metadata describe the IdP's keys?

In IdP metadata, **EntityDescriptor.entityID** identifies the entity; **IDPSSODescriptor** describes the IdP role; **KeyDescriptor** holds public-key info for signing or encryption purposes.

~~~text
md:EntityDescriptor entityID="https://idp.example.org/saml"
  └── md:IDPSSODescriptor
        ├── md:KeyDescriptor use="signing"
        │     └── ds:KeyInfo
        │           └── ds:X509Data
        │                 └── ds:X509Certificate
        ├── md:KeyDescriptor use="signing"       (if rotating)
        └── md:SingleSignOnService
~~~

Learning XML example:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>
            PUBLIC_X509_CERTIFICATE_BASE64_FROM_TRUSTED_IDP
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**This is only an illustrative fragment:** the certificate value is descriptive text, not valid Base64 DER X.509. Do not import this fragment as real metadata. **The SP never receives the IdP's private key**; the SP uses the public key to verify messages signed by the IdP.

### KeyDescriptor and the `use` attribute

| Location / purpose | Proper interpretation |
| --- | --- |
| **IDPSSODescriptor → KeyDescriptor use="signing"** | **IdP** public key for the SP to verify signatures on Responses/Assertions/Logout messages issued by the IdP per agreement. |
| **IDPSSODescriptor → KeyDescriptor use="encryption"** | Key info for encryption involving the IdP role, not implicitly the Assertion signing key. |
| **SPSSODescriptor → KeyDescriptor use="signing"** | **SP** public key for the IdP to verify signatures on AuthnRequest/Logout messages sent by the SP. |
| **SPSSODescriptor → KeyDescriptor use="encryption"** | **SP** public key for the IdP to encrypt data that the SP decrypts with the SP private key. |
| **KeyDescriptor without `use`** | In SAML metadata, must not be assumed encryption-only or signing-only; check default semantics per spec/profile and deployment policy. |

Role matters greatly. **Never take a certificate from SPSSODescriptor to verify an IdP Assertion**, never grab the certificate from the IdP's HTTPS website out of habit, and never pick an arbitrary key merely because it shares a CA.

In SAML metadata, **ds:KeyInfo** can hold **ds:X509Certificate** or **ds:KeyValue**. Both can represent a **public key**. The OASIS Metadata Interoperability Profile emphasizes using X509Certificate as a **key carrier**, rather than requiring proof of a CA chain for that cert by default.

## 4. What is "identifying trusted keys from metadata"?

A system implementing **metadata-based trust** executes two distinct phases.

### Phase A: safely accepting metadata

First, establish that the metadata was issued by the **exact partner/federation operator** and is authorized to apply. Depending on design, the source may be assured via:

- **Metadata XML Signature**: verify the signature using a **pre-configured, out-of-band metadata signing key/trust anchor**.
- **HTTPS + approved origin**, paired with admin/provisioning controls; whether that suffices depends on the threat model.
- **Metadata file via secure change-management**, comparing fingerprints, signing approvals, or delivering over an authenticated channel.
- **Trusted federation aggregator**, with a signature chain and entity/role/trust filtering policies.

Even when metadata has **ds:Signature**, you cannot take a self-declared certificate inside that very XML and claim **the document proves itself trustworthy**. There must be an **independently configured trust anchor**, verifying signed bytes/references, preventing XML Signature Wrapping, checking expected entityID, and checking timestamps.

Metadata may contain **validUntil** and **cacheDuration**. Follow refresh policies, guard against replaying stale metadata holding removed keys, and never cache indefinitely to mask incidents.

### Phase B: using keys once metadata is accepted

Once the consumer **has accepted** metadata and selected the exact target:

~~~text
EntityDescriptor.entityID = IdP Corp
  -> IDPSSODescriptor supporting SAML2
      -> KeyDescriptor use=signing
          -> public keys K1, K2
~~~

then **K1/K2** are the candidate verification keys **authorized for IdP Corp in the signing role**, per the accepted metadata version/policy. At runtime, the SP verifies XML Signatures with those keys, then verifies all SAML constraints.

**It is NOT** the algorithm: fetch metadata from a browser-supplied URL → grab any certificate inside → automatically treat the issuer as trusted → allow login.

### When do two keys exist simultaneously?

IdP rotation can advertise **KeyDescriptor use=signing for K1 (old)** and **K2 (new)** during transition. Once the new metadata is approved, the SP can verify signatures using any key allowed for that role; still enforce issuer/response validity and signing algorithm policies.

Approved rotation schedules typically proceed:

1. IdP generates key K2 and keeps the private key secure.
2. IdP publishes K1 and K2 in new metadata.
3. SP receives/verifies source and accepts new metadata; monitors readiness.
4. IdP switches to signing messages with K2.
5. After the overlap window, IdP removes K1 from metadata.
6. SP refreshes and stops accepting K1 per policy; never retain K1 indefinitely.

**Multi-key KeyDescriptors are not an X.509 leaf/intermediate/root chain.** Each KeyDescriptor normally describes a usable key, never implicitly "the next step in a CA chain".

## 5. What is PKIX path validation?

**PKIX** (per **RFC 5280**, with Java providing **CertPathValidator/PKIXParameters**) applies a set of rules to validate an **X.509 certification path**:

~~~text
Leaf certificate (Subject = service)
   signed by Intermediate CA
        |
        v
Intermediate CA certificate
   signed by Root CA
        |
        v
Trust Anchor / Root CA installed in trust store
~~~

A PKIX check can include:

1. Building a **certification path** from leaf up to a trusted **trust anchor**.
2. Verifying **each certificate's signature** along the path and CA constraints.
3. Checking certificate **notBefore/notAfter** against validation time.
4. Checking **Basic Constraints**, **KeyUsage**, **path length**, and relevant critical extensions.
5. Checking **certificate policy/name constraints** and Extended Key Usage if required by use case.
6. Checking **CRL/OCSP** revocation status if required by deployment policy and revocation is enabled/configured cleanly.
7. After obtaining a valid chain, still verifying **identity binding**: which hostname/service/entity does the certificate represent in context?

**A valid PKIX path does not automatically confirm "this is IdP Corp authorized by the SP".** A public CA can issue a completely valid certificate for `attacker.example.org`; that does not turn the attacker into **`https://idp.corp.example.org/entity`**. You still need explicit issuer/entityID, role, and partner mapping policies.

### The TLS HTTPS case

When the SP fetches metadata from **`https://idp.example.org/metadata`**, the HTTPS client typically performs PKIX/TLS chain verification of the **server certificate** and validates hostname per TLS policy. This protects the HTTP connection to the metadata source.

**The TLS certificate of hostname `idp.example.org` is not necessarily the IdP's SAML signing certificate.** An IdP may use a public CA cert for TLS, a private/self-signed X.509 cert holding the SAML signing key, and a third key to sign metadata.

### Using PKIX to trust metadata

A federation may use **CA/PKIX** to verify the **metadata signer's certificate** or protect the metadata download channel, depending on workflow. That is PKIX **at the metadata acceptance step**, not necessarily PKIX on **KeyDescriptor signing** for every SAMLResponse verification.

Distinguish clearly:

~~~text
PKIX/TLS proves metadata source is an authorized endpoint
               |
               v
Verify metadata XML Signature when required by policy
               |
               v
ACCEPT metadata for exact IdP/entity/role
               |
               v
Extract authorized IdP public signing key
               |
               v
Verify SAMLResponse/Assertion XML Signature
               |
               v
Check issuer, audience, time, subject confirmation...
~~~

If an enterprise chooses **PKIX-based signature trust** outside the Metadata Interoperability Profile, it must design dedicated validators and name/entity bindings. Never assume Spring Security SAML2 SP performs PKIX path/revocation checks for every KeyDescriptor by default.

## 6. Comparing the two models: metadata trust vs. PKIX

| Criterion | **Metadata-based trust** | **PKIX trust model** |
| --- | --- | --- |
| **Trust source** | Approved metadata, exact entityID/role, trusted distribution process. | CA trust anchors + certification path and certificate policy. |
| **Object verified** | Public key for signing/encryption published for a specific entity/role. | Leaf/intermediate certificates and chain to CA. |
| **Confirming IdP Corp's key** | Key resides in **signing KeyDescriptor of exact IDPSSODescriptor** in trusted metadata. | Valid chain **plus** mapping key/certificate to exact IdP Corp. |
| **Self-signed certificate** | Can be appropriate if the key is in accepted metadata. | Normally builds no path to external CA; valid only if configured as trust anchor/trusted per policy. |
| **Certificate past notAfter** | Per Metadata IOP, that detail is not used to reject an accepted key at runtime; requires governed rotation/metadata lifecycle. | Usually causes path validation to fail at current time (barring trust-anchor/policy specifics). |
| **CA chain and certificate issuer** | Not a runtime basis in Metadata IOP. | Core component of path validation. |
| **CRL/OCSP** | Per Metadata IOP, no online/offline revocation checks on role keys; instead update/remove key from metadata. | May be a mandatory component of cert revocation policy. |
| **New key** | Accepted once metadata is trusted and valid KeyDescriptor is added. | Must chain to trusted CA and bind to exact identity per policy. |
| **Common pitfall** | Trusting unverified metadata or caching stale metadata forever. | Trusting any CA-issued leaf cert without binding IdP entityID/role. |
| **Spring Security SP default** | Typically configures verification credentials loaded from IdP metadata or specified certs. | **Never assume** built-in PKIX path/revocation for SAML signing certs; verify implementation/config. |

### Why can the same certificate yield two different conclusions?

Suppose **cert S** is X.509 **self-signed** with `notAfter` passed, yet holds public key K published by IdP Corp in verified, unreplaced metadata:

- Under the **OASIS Metadata Interoperability Profile**, once metadata is accepted, the SP can use **K to verify SAML signatures** and **add no runtime PKIX/date/OCSP checks for the role key**. This is an interoperability rule of the profile, **not a license to abandon certificate lifecycle management**: expired certificates should still be rotated operationally.
- Under **PKIX path validation** to a private corporate CA, this self-signed/expired certificate may **fail to build a valid chain** and be rejected. That is a different trust mechanism, not automatically equivalent.

Conversely, cert T has a valid chain to a public CA and is unexpired, yet is **absent from trusted IdP Corp metadata**:

- PKIX may validate T as a valid leaf cert for some name.
- **The SP still must not use T to trust an Assertion claiming to be Corp**, absent a trusted binding between T and IdP Corp in the deployed SAML model.

## 7. Special rules of the OASIS Metadata Interoperability Profile

**SAML V2.0 Metadata Interoperability Profile Version 1.0** (OASIS Standard, 2019) defines a trust model built on **metadata acceptance**:

1. Metadata is distributed and accepted via an **authenticated/governed mechanism**. The profile does not mandate HTTPS, XML Signature, or a specific approval method; that is an operational prerequisite.
2. **KeyDescriptor** per role is the authoritative source designating keys an entity/role is allowed to use.
3. For **ds:X509Certificate**, per the profile, the certificate primarily **transports the public key**; runtime decisions for role keys do not rely on certificate Subject, Issuer, validity, or EKU.
4. Once metadata is accepted, the consumer **does not add X.509 path validation, CRL, or OCSP checks** when accepting/using role keys at runtime. **This is an obligation when strictly implementing this profile**, not a rule that "all PKIX applications must disable revocation".
5. Compromised keys must be **removed from metadata**, and metadata **refreshed** per policy; `validUntil` prevents replaying old metadata. **`cacheDuration` alone is not a strong enough anti-replay control**.

A misconception is "SAML doesn't need certificate validation, so load any metadata". Wrong: if unverified metadata is trusted, an attacker can **swap KeyDescriptor and self-grant trust**, causing forged signatures to verify against the attacker's key. **Trust at metadata ingestion becomes more critical**, not less.

Another misconception is "without PKIX, expired certificates can be used forever". Wrong: even though the profile does not use **`notAfter`** to reject runtime role keys, organizations must still govern key lifecycles, key compromise, algorithms, key lengths, metadata validity, and rotation checks. Distinguish **profile runtime rules** from **operational/key-hygiene policies**.

### When is PKIX still used?

- **TLS HTTPS** when fetching metadata or exchanging SOAP/back-channel traffic: carries its own TLS trust, hostname validation, and policy.
- **Verifying metadata signers**: may use key pinning or PKIX with proper trust anchors and bindings, decided before accepting metadata.
- **Other federations not using Metadata IOP**: may use PKIX message-signature trust if all parties agree and implement exact issuer/role mapping; this behavior is never inferred automatically from KeyDescriptor.
- **Organizations with internal private CAs**: PKIX may be one layer in onboarding, yet SAML-specific entityID/role trust is still required.

Do not force TLS **CRL/OCSP** policies onto all **SAML signing certificates** if the stack follows Metadata IOP; conversely, never disable TLS CRL/OCSP merely because SAML metadata uses a public-key trust model.

## 8. How X.509 certificates, public keys, and fingerprints differ

An X.509 certificate holds many fields:

~~~text
X.509 Certificate
  - Subject
  - Issuer
  - Serial Number
  - notBefore / notAfter
  - SubjectPublicKeyInfo (SPKI) -> PUBLIC KEY
  - Signature Algorithm / Certificate Signature
  - KeyUsage / ExtendedKeyUsage / SAN / BasicConstraints ...
~~~

A **certificate fingerprint** is usually SHA-256 over the **entire DER-encoded certificate bytes**. An **SPKI fingerprint** is SHA-256 over **DER SubjectPublicKeyInfo**, i.e., the public key representation. The two fingerprints **differ** and have different matching semantics.

| Operation | What is compared | What it establishes |
| --- | --- | --- |
| **Exact certificate pin** | SHA-256 over entire DER certificate. | Certificate matches the approved certificate byte-for-byte. |
| **Public key/SPKI pin** | SHA-256 over encoded SubjectPublicKeyInfo. | Public key is identical even if the certificate is reissued with different fields/serial/expiry. |
| **PKIX validation** | X.509 chain up to CA trust anchor. | Path and policies are valid; does not prove binding to a SAML issuer without a dedicated step. |
| **XML Signature verification** | Signed XML bytes + signature + candidate public key. | Signed content corresponds to the matching private key. |
| **SAML trust decision** | Metadata acceptance, entityID/role, verification key, profile policies. | Accepts only messages issued by the right partner and intended for the right SP. |

**Never compare MD5/SHA-1 certificate fingerprints for new trust decisions.** Prefer **SHA-256** when recording audit fingerprints; SAML signature algorithms and key sizes must still follow current policy.

### Same public key, different certificate

An IdP may be issued a **new cert B** with different serial, validity, and issuer from cert A while keeping the **same public key**:

- **Certificate fingerprint A ≠ B**, so an exact-certificate pin detects a difference.
- **SPKI fingerprint A = B**, so a public-key pin still matches.
- Under Metadata IOP, trusting a key concerns the accepted **public key** in metadata, yet operations must check cert rollover per policy; never use a matching key as an excuse to ignore metadata expiry/compromise.
- PKIX paths for certs A and B may yield different results because issuer/validity/CA differ, even though the public key is identical.

Conversely, two certificates sharing a Subject like "CN=Corporate IdP" **do not prove** they share a key or trust relationship. Matching solely on subject name is far too weak.

## 9. Never trust ds:KeyInfo from SAMLResponse circularly

An XML Signature inside SAMLResponse/Assertion may include **ds:KeyInfo**, sometimes containing a sender-attached certificate.

**Safety rules:**

- **KeyInfo from an unverified message** can be a **lookup hint for finding a key**, never authorization for the runtime to auto-"add a trusted certificate".
- The SP must bind the candidate key to a **registered IdP / RelyingPartyRegistration / approved metadata**.
- Only after locating the trusted key does the SP verify the cryptographic signature and SAML conditions.
- Never do: extract cert from `Assertion.KeyInfo` → test verify gets true → treat an arbitrary issuer as a trusted partner.
- If a message omits KeyInfo or uses a different certificate than metadata while sharing the public key, key-resolution policies and libraries may still locate the key; do not assume identical Base64 certificate strings are always required if the trust model is public-key-based.

Attack thought experiment:

~~~text
Attacker:
  generates RSA keypair A
  crafts Assertion Issuer="https://corp-idp.example.org"
  signs Assertion with private key A
  embeds public cert A into ds:KeyInfo

Broken SP:
  verifies using cert A taken straight from message -> true
  grants login without checking trusted IdP metadata -> SPOOFED

Proper SP:
  looks up registered Corp IdP
  retrieves K1/K2 from Corp IdP's trusted metadata
  signature by A fails to match -> REJECT
~~~

**A valid signature with an unauthorized key = untrusted response.**

## 10. Signing metadata vs. signing Assertions: two distinct assets

At least three types of keys commonly appear:

1. **IdP SAML signing key:** signs Assertions/Responses issued by IdP; SP checks via IdP's signing KeyDescriptor.
2. **SP SAML signing key:** signs AuthnRequest/LogoutRequest issued by SP; IdP checks via SP's signing KeyDescriptor.
3. **Metadata signer key:** signs the metadata file or federation aggregate; SP/IdP checks via the **metadata source's** trust anchor.

The metadata signer may be a **federation operator**, not the IdP. Never substitute an **Assertion signing certificate** for a **metadata signing certificate** by default, and never treat the HTTPS server's certificate as a metadata signer without an agreement.

### A metadata signature does not mean keys inside remain valid forever

Metadata requires:

- Exact **entityID/role** and an approved distribution source.
- **Valid metadata signature** when required by policy, using a previously known credential.
- Unexpired **validUntil** and proper caching/refresh; guard against stale metadata rollback/replay.
- No unexpected keys/roles, strange SSO/ACS endpoints, or unscheduled key changes.
- Monitoring key changes against organizational **approved/pending/revoked** states.
- Immediate removal of compromised keys from metadata, publishing updated metadata, and updating consumers—never merely waiting for X.509 certificate expiry.

A metadata file **still validly signed by a trusted signer** yet **past `validUntil`** cannot be used indefinitely by default. This situation differs from the `notAfter` of a **role key** certificate under Metadata IOP.

### Why is HTTPS insufficient when using federation aggregate metadata?

HTTPS protects the connection to the host requested by the client. Yet aggregate metadata may pass through mirrors, CDNs/proxies, or contain hundreds of entities. Metadata signatures using the federation operator's key plus entity filtering distinguish "content approved by a federation source" from "XML just downloaded from some HTTPS server". The exact model depends on the organization.

## 11. Spring Security SP: where do verification credentials live?

With **Spring Security Servlet**, **RelyingPartyRegistration** links SP to IdP; the **asserting party metadata** section holds **IdP entityID, SSO URL, and verification X.509 credentials**.

~~~text
RelyingPartyRegistration(registrationId="corp")
  SP:
    entityId = https://app.example.com/saml2/service-provider-metadata/corp
    ACS = https://app.example.com/login/saml2/sso/corp
    signing credentials = SP's private key/cert (if needed)
  IdP:
    entityId = https://idp.example.org/saml
    SSO URL = https://idp.example.org/sso
    verification X509 credentials = IdP's public cert(s)
~~~

Upon receiving a Response, the OpenSAML provider uses the registered partner's verification credentials to validate signatures per policy. **Registering a `Saml2X509Credential.verification(cert)`** declares a **trusted certificate for verifying SAML messages**; **it is not automatically an instruction to run PKIX `CertPathValidator`** on that certificate.

### Approach A: reading IdP metadata via an approved URL

Example for **Spring Boot 3.3.5, Java 17**:

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-key-trust-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
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
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: 8080
~~~

**`SAML_IDP_METADATA_URI`** must be a real, approved IdP metadata URL. This config instructs Spring Boot to read metadata and build the registration. **Never infer from successfully reading metadata that its XML Signature was verified**, or that certificates underwent PKIX chain checks; verifying metadata signatures/refresh requires version- and framework-appropriate mechanics and config.

Certain newer features, such as **OpenSaml5AssertingPartyMetadataRepository** and metadata signature verifiers, belong to newer Spring Security releases. **Do not copy Spring Security 7.x imports/APIs into a Boot 3.3.5 project** without confirming compatibility.

### Approach B: specifying trusted IdP certificates via static configuration

If an organization governs IdP signing certs via an **approved onboarding workflow** rather than auto-fetching metadata, use the following configuration **instead**—never mix it indiscriminately with `metadata-uri` above.

**src/main/resources/application.yml (alternative)**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/corp-idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/sso"

server:
  port: 8080
~~~

**`corp-idp-signing.crt`** must be the IdP's public X.509 certificate **acquired/verified out-of-band** (never downloaded from browser input). The file path is a configuration example, not a real file. During cert rotation, update the static config and deploy in controlled fashion; avoid leaving compromised old certs around.

**Approaches A and B** are both ways to obtain **trusted verification credentials** for Spring. **Never describe them as a PKIX path validator**. If an organization mandates PKIX chain validation at some layer, configure and test that layer separately.

### Application and SecurityFilterChain

**src/main/java/com/example/samltrust/SamlTrustApplication.java**

~~~java
package com.example.samltrust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlTrustApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samltrust/SecurityConfig.java**

~~~java
package com.example.samltrust;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samltrust/ProfileController.java**

~~~java
package com.example.samltrust;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "SAML key trust SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID=" + principal.getName();
    }
}
~~~

Conditions required to run full SSO:

- A **real IdP and trusted IdP metadata/cert** exist;
- SP entityID and ACS are accurately registered at the IdP, with public HTTPS URLs in production;
- IdP signs Response or Assertion as required, and SP checks the right signing key;
- If IdP requires SP-signed AuthnRequests, add SP signing credentials and publish the SP public certificate;
- If using encrypted Assertions, add SP private decryption keys;
- No issuer, audience, destination, time, InResponseTo, Recipient, or replay errors.

Run:

~~~bash
mvn spring-boot:run
~~~

**Verifiable outcomes (no IdP needed to inspect public endpoints):**

- **GET http://localhost:8080/** returns exact **`SAML key trust SP ready`** when the app starts cleanly.
- **GET http://localhost:8080/saml2/metadata/corp** outputs **`SPSSODescriptor`** metadata for the `corp` registration.
- **GET http://localhost:8080/saml2/authenticate/corp** redirects the browser to the IdP SSO endpoint if IdP metadata/config is valid.
- **GET http://localhost:8080/me** requires SAML login; after a valid Response/Assertion, the body has form **`NameID=<value issued by IdP>`**, which cannot be predicted in advance.

Configuring verification credentials in Spring Security **does not mean PKIX path validation ran for SAML keys**. Actually completing login depends on verifying signatures and SAML conditions against a real IdP.

## 12. Standalone Java 17: checking authorized public keys and signatures

The Java example below uses pure **JDK 17**, requiring no Spring or IdP, to illustrate the difference between:

1. An **out-of-band accepted public key**, analogous to K1 in trusted IdP metadata;
2. A **different public key supplied by an unknown party**;
3. **Valid/invalid signatures** with each key.

The program **generates test RSA keys in memory**, signs a text message, and verifies with the public keys. It **is not a SAML XML Signature validator**, does not parse XML metadata, does not check PKIX, and uses no production private keys. Random key generation does not alter the boolean stdout shown below.

**KeyTrustDemo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;

public class KeyTrustDemo {
    static byte[] spkiHash(PublicKey key) throws Exception {
        return MessageDigest.getInstance("SHA-256")
                .digest(key.getEncoded());
    }

    static boolean verify(PublicKey key, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trustedIdp = generator.generateKeyPair();
        KeyPair untrusted = generator.generateKeyPair();

        byte[] data = "test-message".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(trustedIdp.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        // Simulate IdP public key obtained from approved metadata.
        PublicKey enrolledKey = trustedIdp.getPublic();

        boolean sameKey = MessageDigest.isEqual(
                spkiHash(enrolledKey), spkiHash(trustedIdp.getPublic()));
        boolean otherKey = MessageDigest.isEqual(
                spkiHash(enrolledKey), spkiHash(untrusted.getPublic()));
        boolean validTrusted = verify(enrolledKey, data, signature);
        boolean validOther = verify(untrusted.getPublic(), data, signature);
        boolean altered = verify(enrolledKey,
                "altered-message".getBytes(StandardCharsets.UTF_8),
                signature);

        System.out.println("trusted key match: " + sameKey);
        System.out.println("untrusted key match: " + otherKey);
        System.out.println("signature with trusted key: " + validTrusted);
        System.out.println("signature with other key: " + validOther);
        System.out.println("signature after alteration: " + altered);
        System.out.println("PKIX validation performed: false");
    }
}
~~~

Compile/run:

~~~bash
javac KeyTrustDemo.java
java KeyTrustDemo
~~~

**Exact stdout:**

~~~text
trusted key match: true
untrusted key match: false
signature with trusted key: true
signature with other key: false
signature after alteration: false
PKIX validation performed: false
~~~

Explanation:

- **trusted key match=true:** SPKI fingerprint matches the accepted public key in the simulation. In real SAML, **key acceptance depends on metadata/role/issuer trust**, not just hash comparison.
- **untrusted key match=false:** a different RSA public key cannot substitute for the key authorized by IdP Corp.
- **signature with trusted key=true:** digital signature is valid **for that key and those bytes**. It does not prove the Response has valid audience, timestamps, or issuer.
- **signature with other key=false:** the signature does not verify under an unknown key.
- **signature after alteration=false:** modifying signed data causes verification to fail.
- **PKIX validation performed=false:** there are no X.509 certificates/chains, CA stores, CRLs, or OCSP; the program intentionally demonstrates **only key trust and signature**.

**SHA-256 over `key.getEncoded()` in the program is the encoded SPKI fingerprint**, not SHA-256 over the entire X.509 DER certificate. **`Signature.getInstance("SHA256withRSA")`** verifies signatures on a plain byte string; SAML XML Signature additionally involves XML canonicalization, References, transforms, enveloped signatures, and wrapping risks, so **you cannot replace OpenSAML's XMLSig verifier with this `verify()` function**.

## 13. PKIX in Java: boundaries of the comparison example

Understanding **actual PKIX** requires different inputs from `KeyTrustDemo`:

- **Leaf X.509 certificate** of the subject being verified.
- **Intermediate certificates** if any, in order or via path builder.
- **TrustAnchor** (typically a governed root CA certificate).
- **PKIXParameters**, policies for validation date/constraints/revocation.
- A policy **binding the verified certificate's identity to a specific SAML entityID or hostname**, if needed.

Java provides **CertificateFactory**, **CertPathValidator**, **PKIXParameters**, **TrustAnchor**, and **CertPathBuilder**. Illustrative API fragment:

~~~java
// ILLUSTRATIVE API FRAGMENT, DOES NOT RUN STANDALONE:
// rootCa, leaf, intermediate are X509Certificates loaded from valid sources.
// Chain must match profile; trust anchor and revocation depend on policy.

CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath path = factory.generateCertPath(
        java.util.List.of(leaf, intermediate));
PKIXParameters params = new PKIXParameters(
        java.util.Set.of(new TrustAnchor(rootCa, null)));

// Configure CRL/OCSP and verify key usage/name policies properly
// rather than disabling revocation arbitrarily to make a test pass.
CertPathValidator.getInstance("PKIX").validate(path, params);
~~~

**This is not a standalone compilable Java file:** supply imports and real valid certificates before running. There is no fixed stdout since results depend on the certificate chain, timestamp, policy, and revocation status. The fragment illustrates **PKIX certification paths** for conceptual comparison, **not to suggest injecting PKIX into every role-key check when implementing the OASIS Metadata Interoperability Profile**.

### Passing PKIX is still not a passing SAML login

Even when a leaf cert chains cleanly to a CA, you must still verify that:

- The public key is authorized to represent the **exact SAML entityID/registration**;
- A valid SAML signature exists under that key;
- SAML issuer, audience, destination, recipient, time, InResponseTo, replay, and profile are all valid;
- The user holds app access rights per internal authorization.

In TLS, you must also validate the certificate against the hostname per the TLS stack. Never infer from a **leaf's Subject CN** that it is a **SAML issuer** without an independent binding agreement.

## 14. Key rotation, expiry, compromise, and safe handling

### Case A: IdP replaces certificate yet keeps public key

- **X.509 cert fingerprint changes** because serial/issuer/validity changed.
- **SPKI fingerprint stays identical** if the public key genuinely did not change.
- If trust policy trusts the **public key from metadata**, the key may still be recognized properly; verify the right metadata version was accepted and rotation schedules are respected.
- Never treat "same public key" as sufficient if new metadata came from an untrusted source or old metadata was tampered with.

### Case B: IdP generates a new key pair

- SPKI fingerprint changes.
- IdP publishes old and new keys in **trusted metadata** during the overlap window, or exchanges static certificates per procedure.
- SP refreshes metadata/trust before the IdP starts signing with the new key.
- Once the IdP removes the old key, the SP must stop accepting it per policy.

### Case C: self-signed or expired certificate

- **Metadata IOP:** certificates can act as public-key wrappers; being self-signed/expired does not by itself fail runtime signature validation once metadata is accepted and the key matches. Yet never treat that as healthy operations: maintain rotation, monitoring, and checks for integrated products' requirements.
- **PKIX:** self-signed certs do not chain to standard CAs and expired leaves fail path validation; requires dedicated trust anchors/validation date policies.
- **TLS:** an expired server certificate or hostname mismatch breaks HTTPS handshakes, regardless of whether SAML signing keys remain valid.

### Case D: IdP private key is compromised

This is a critical security event:

1. IdP stops using the compromised key.
2. Publish new signed/trusted metadata, **removing the compromised public key** from the role.
3. Notify SPs, push urgent refreshes, and inspect caches/stale instances.
4. Restrict and review previously established sessions per incident response policy.
5. Never merely wait for certificate CRL/OCSP because Metadata IOP does not rely on them for runtime key acceptance.

### Case E: metadata passes validUntil

Expired metadata **must not continue to be trusted indefinitely** merely because signing certs inside remain unexpired. Enforce a policy to **fail closed or use cached metadata only within an approved window**, monitor, and restore metadata sources. **Metadata `validUntil`** differs from **certificate `notAfter`** and from **Assertion `Conditions.NotOnOrAfter`**.

## 15. Security testing and expected outcomes

Use an **IdP/SP sandbox**, real signed SAMLResponses from a test IdP, and metadata created/registered through a trusted channel. If you manually edit a signed SAMLResponse XML, the broken signature prevents tests from distinguishing key-trust failures from issuer/audience failures.

| # | Scenario | Result to verify |
| --- | --- | --- |
| 1 | Corp IdP metadata verified; Assertion signed with published signing key | Signature verifies and SAML profile checks continue. |
| 2 | Assertion signed with attacker's key embedding attacker's cert in KeyInfo | **Reject**; never auto-trust keys from messages. |
| 3 | Assertion signed with Partner IdP's key yet claiming Corp IdP Issuer | **Reject** per registration/issuer/trust. |
| 4 | Self-signed IdP signing certificate whose key is in trusted metadata under Metadata IOP | Key usable; profile requires no CA path for role keys. |
| 5 | IdP role cert past notAfter yet key remains in accepted metadata under Metadata IOP | **Do not reject role key via PKIX expiry under profile**; still operate proper rotation. |
| 6 | Valid PKIX certificate from another site, absent from Corp IdP metadata | **Do not trust** as Corp's SAML signing key. |
| 7 | Certificate with identical Subject CN yet different public key | **Never equate keys** by CN. |
| 8 | Reissued cert with different DER yet same SPKI public key | Distinguish **cert fingerprint** vs. **public-key identity**; policy decides. |
| 9 | KeyDescriptor altered in metadata after signing | Metadata signature must **fail**; do not import unknown key. |
| 10 | Metadata signed by a key inside the document itself without independent trust anchor | **Do not self-grant trust** to metadata. |
| 11 | Metadata aggregate containing many entities | Extract **only exact entityID, IDPSSODescriptor, signing role keys**. |
| 12 | `KeyDescriptor use=encryption` selected as signing verifier | **Never pick wrong key purpose**. |
| 13 | IdP metadata advertises signing keys K1 and K2 during rotation | Both usable per policy once metadata is accepted. |
| 14 | K1 removed from new metadata yet SP still uses expired stale cache | **Stale trust defect**; requires refresh/expiry/incident handling. |
| 15 | IdP rotates key yet SP hasn't refreshed | **Reject new signature** until trust updates cleanly; never skip verification. |
| 16 | HTTPS metadata URL has expired TLS cert | Fetch may **fail TLS**, even though separate role signing cert is valid. |
| 17 | Metadata signer cert has valid PKIX chain yet invalid XML Signature | **Do not accept metadata**. |
| 18 | Metadata signature valid yet wrong `EntityDescriptor.entityID` | **Do not misbind partner**; reject or flag misconfiguration. |
| 19 | PKIX leaf chain passes yet Assertion Audience is wrong | **Reject SAMLResponse**; PKIX does not replace audience validation. |
| 20 | Assertion signed with right IdP key yet Recipient/Destination targets another SP | **Reject** per SAML profile. |
| 21 | Signed with right IdP key yet Response expired | **Reject** per expiry/conditions. |
| 22 | Certificate compromised and removed from accepted metadata | SP must stop trusting old key per refresh policy. |
| 23 | Metadata past validUntil | **Do not keep using indefinitely**; enforce expiry policy. |
| 24 | App configures certificate in `Saml2X509Credential.verification` | That declares a SAML verification key; **does not prove PKIX path ran**. |

A **successful negative test** is when the system **properly rejects trust or profile violations**. Never "fix" by enabling allow-all certs, disabling signature verification, trusting KeyInfo from responses, or accepting any issuer.

## 16. Troubleshooting: which layer to start at?

| Symptom | Possibility | Investigation path |
| --- | --- | --- |
| **Signature validation failed** | IdP signed with key absent from accepted metadata/verification credentials, or XML altered. | Compare IdP registration, actual signing key, rotation, and signature policy. |
| **Unknown issuer / mismatched issuer** | Assertion/Response Issuer does not match registered IdP entityID. | Fix partner/metadata; never trust a key merely because PKIX passed. |
| **Cert path does not validate / unable to find trust anchor** | A PKIX/TLS component or custom chain validator mismatched trust store/policy. | Pinpoint TLS vs. metadata signer vs. role key layer before acting. |
| **SAML cert expired** | Product/policy may enforce expiry differently from Metadata IOP. | Check deployed profile, version, and contract; schedule key rotation, never disable TLS expiry. |
| **Metadata download TLS handshake fail** | HTTPS cert hostname/chain/validity or proxy. | Inspect TLS truststore/hostname/CA separately; never blindly swap SAML signing keys. |
| **Metadata signature invalid** | Tampered content, untrusted signer, or wrong transform. | Verify metadata trust anchor and signed references before loading SAML keys. |
| **IdP rotation, logins suddenly fail** | SP hasn't fetched new metadata or still uses old cert. | Check old/new KeyDescriptors, cache/validUntil, refresh, and overlap. |
| **Using IdP website's certificate to verify Response fails** | TLS cert differs from SAML signing cert. | Obtain signing cert from approved IdP metadata. |
| **Multiple certs in metadata mistaken for CA chain** | Each KeyDescriptor is a key, not a cert chain. | Use right keys for right role; never build chains from KeyDescriptors. |
| **Still logging in with key removed from metadata** | Stale cache, broken refresh, or faulty key removal policy. | Force refresh, investigate sessions, and run incident procedure. |
| **Valid signature yet SAML login fails** | Wrong Audience, Destination, Recipient, InResponseTo, time, or logout/profile. | Debug SAML assertion conditions; do not blame every failure on certificates. |

**Never log private keys, full SAMLResponses, raw Assertions, session cookies, or personal data in public tickets.** Safely log: `registrationId`, verified IdP `entityID`, SHA-256 hash/fingerprint of **public certificates**, anonymized request ID, and error category. When recording fingerprints, explicitly state **`certificate SHA-256`** vs. **`SPKI SHA-256`** so reviewers never compare two different things.

## 17. Checklist for choosing a trust model

**Before deployment:**

1. Decide whether the organization uses **OASIS Metadata Interoperability Profile**, another PKIX-based trust, or a layered hybrid; document it clearly in design.
2. Identify approved **metadata sources/aggregators**, metadata signer trust anchors, or origin authentication mechanics; never accept arbitrary URLs from browsers.
3. Select the exact **IdP entityID/IDPSSODescriptor/KeyDescriptor use=signing**.
4. Register the exact **SP entityID/ACS**, separating SP signing certificates from IdP verification certificates.
5. Ensure Spring Security **`RelyingPartyRegistration`** holds verification credentials for the exact IdP; never try keys across all tenants hunting for "a match".
6. Ensure metadata signature validation if policy requires, **never confusing** it with SAML message signature validation.
7. Define **`validUntil`/`cacheDuration`**, refresh cadence, rollback/replay protection, and emergency key removal.
8. Plan **rotation**: add new key, verify readiness, cut over, remove old key; govern certificate lifecycles and algorithms.
9. If using PKIX at any layer, define CA anchors, name bindings, certificate constraints, and revocation policies for **that exact layer**; never merge arbitrarily with metadata-based role key trust.
10. Keep **HTTPS/TLS hostname verification** for metadata fetches and network traffic, even when SAML signing keys are trusted via metadata.
11. Test at minimum: valid key, unknown key, self-signed key, expired cert, metadata signature failure, dual-key rotation, stale metadata, wrong issuer, wrong audience, and wrong ACS.
12. Track your exact Spring Security/OpenSAML version; never claim Spring Security runs PKIX/OCSP on SAML signing keys by default without inspecting that version's code/config.

## 18. Review questions and answers

**Q1.** An IdP signs Assertions with a self-signed certificate. The SP fetched IdP metadata from a trusted source and signing KeyDescriptor publishes that exact public key. Under OASIS Metadata IOP, must the SP prove a cert chain to a public CA before accepting the signature?  
**Answer:** **No**. Under the profile, once metadata is accepted, runtime trust rests on keys authorized by role metadata, not PKIX path validation. However, the signature and all SAML conditions must still verify, and metadata must remain acceptable per policy.

**Q2.** An attacker's SAML signing cert has a valid chain to a public CA. Is that enough to prove the attacker is IdP Corp?  
**Answer:** **No**. A PKIX chain does not bind a certificate to SAML entityID Corp. The SP trusts only the approved IdP issuer/role/verification credentials.

**Q3.** The IdP changes the DER certificate while keeping the public key. Is the SHA-256 cert fingerprint identical? Can the SPKI fingerprint be identical?  
**Answer:** The certificate fingerprint usually **differs** because DER bytes changed; the SPKI fingerprint can stay **identical** if the public key didn't change. Always state which object is pinned/compared.

**Q4.** Why not use the certificate embedded in a Response's `ds:KeyInfo` as a trust anchor?  
**Answer:** Because an unverified message could be self-signed by an attacker embedding their own cert. Keys must first be bound to a trusted IdP via metadata/config before verifying.

**Q5.** Metadata is validly signed and contains key K1, yet `validUntil` expired long ago. Can K1 be trusted forever?  
**Answer:** **No**. Metadata lifecycle/refresh/expiry policies still apply; expired metadata differs from role-key certificate expiry under Metadata IOP.

**Q6.** The TLS server certificate of `idp.example.org` expired, while the SAML signing certificate remains trusted. Can the SP fetch metadata over HTTPS?  
**Answer:** The HTTPS handshake may fail due to TLS validation. Never disable TLS verification merely because SAML key trust uses a separate mechanism.

**Q7.** There are two `KeyDescriptor use=signing` entries in IdP metadata. Is that a leaf → intermediate CA chain?  
**Answer:** **No**. They normally represent **independent signing keys** for a role, e.g., during rotation. A CA certificate path is a separate PKIX construct.

**Q8.** The app uses `Saml2X509Credential.verification(idpCert)`, so Spring Security definitely checks CRL/OCSP and CA chains for `idpCert`?  
**Answer:** **Do not infer that**. It merely declares the SAML verification credential. To know whether PKIX/revocation runs, inspect your exact provider/version and policy. OASIS Metadata IOP even requires not running runtime PKIX on accepted role keys.

**Q9.** Can XML Signature validation be disabled because IdP metadata was fetched over valid HTTPS?  
**Answer:** **No**. Metadata source trust and SAML message signatures are two separate layers; Assertion/Response signatures per policy must still be verified.

## 19. References

1. [OASIS — SAML V2.0 Metadata Interoperability Profile Version 1.0, OASIS Standard 24 October 2019](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-os.html) — especially **2.3 Metadata Exchange and Acceptance**, **2.5.1 Key Representation**, **2.6.1 Key Processing**, **2.7 Security Considerations**; distinguishing acceptance/role-key trust from PKIX.
2. [OASIS — SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — EntityDescriptor, IDPSSODescriptor, SPSSODescriptor, KeyDescriptor, validUntil/cacheDuration.
3. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — XML Signature, Issuer, Assertion Conditions, and key-bearing constructs.
4. [IETF RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280) — PKIX certification paths, constraints, validity, and revocation.
5. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — RelyingPartyRegistration, asserting-party verificationX509Credentials, Saml2X509Credential, and SAML validation.
6. [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — reading IdP metadata, publishing SP metadata; newer versions offer repository refresh/metadata signature verification—check exact API version.
7. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — signature verification, issuer/audience/destination validation, and customization.
8. [Oracle Java Security — CertPathValidator and PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html) — JDK path validation API; distinct from `Saml2X509Credential`.
9. [Shibboleth — Keys and Certificates](https://docs.shib.ncsu.edu/docs/configure/keys.html) — practical example of public SAML signing certs published in metadata while private keys stay with the owner.

**One-sentence summary:** **PKIX validates a certificate chain to a CA under policy; SAML metadata trust authorizes public keys for an entity/role via accepted metadata.** Under the OASIS Metadata Interoperability Profile, verifying SAML messages with a trusted role key **neither requires nor permits attaching runtime PKIX/CRL/OCSP checks**, while **metadata exchange, metadata signatures, TLS, key rotation, and all SAML issuer/audience/time checks must still be kept secure**.
