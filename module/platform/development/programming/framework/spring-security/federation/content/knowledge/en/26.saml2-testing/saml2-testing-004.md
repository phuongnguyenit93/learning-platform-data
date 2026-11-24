# Creating SAML Test Fixtures with Dedicated Test Signing Keys

> **Topic:** Spring Security – federation. **Group:** SAML2 Testing. This is a standalone Knowledge article on designing, generating, signing, verifying, and operating **SAML 2.0 test fixture suites** using **IdP signing keys dedicated exclusively to the test environment**. The document combines SAML Web Browser SSO, Spring Security/OpenSAML, Java 17, OpenSSL, metadata, mock IdPs, test clocks, request correlation, replay, XML Signature Wrapping, and secret-safe CI/CD.

## 1. Problem to Solve

To test a Spring Security SAML Service Provider (SP), it is not enough to craft an XML file with a `NameID` and Base64-encode it into a `SAMLResponse` parameter. A trustworthy test must prove:
1. The SAML XML is **genuinely signed by a test Identity Provider (IdP) using XML Digital Signature**, not a fake string.
2. The Spring SP verifies the signature using a **trusted test public certificate configured in the right `RelyingPartyRegistration`**.
3. The signed XML contains **matching Issuer, Audience, Recipient, Destination, Conditions, SubjectConfirmation, InResponseTo**, and valid IDs.
4. The user/attributes consumed belong to an **Assertion protected by a trusted signature**.
5. The test suite includes positive and negative cases distinguishing cryptographic failures, signer trust failures, SAML protocol failures, and local authorization failures.
6. No production IdP private key is used, no test signing certificate enters the production trust store, and no real employee accounts are used as sample data.

**Core principle:** The test IdP side **holds the private signing key**; the Spring test SP side **only trusts the public signing certificate**. Never give the test private key to Spring merely to verify assertions, and never bring a production signing key into a test environment.

## 2. Concepts to Distinguish

| Concept | Meaning |
|---|---|
| SAML Response | Protocol message sent by the IdP to the SP ACS via the browser |
| SAML Assertion | Evidence containing Subject/NameID, Conditions, AuthnStatement, Attributes |
| Test IdP | Simulated/isolated Identity Provider serving tests |
| SP | Spring Security SAML2 Relying Party that must verify the Response |
| ACS | Assertion Consumer Service receiving `SAMLResponse` |
| IdP signing private key | Secret on the IdP side used to generate XMLDSig signatures |
| IdP verification certificate | Public certificate the SP uses to verify signatures |
| SP signing private key | SP's own secret for signing `AuthnRequest`/`LogoutRequest` when needed |
| SP decryption private key | SP key for decrypting `EncryptedAssertion`/`EncryptedID` when needed |
| TLS certificate | HTTPS transport certificate, not interchangeable with the XMLDSig certificate |
| RelyingPartyRegistration | Mapping of SP entityID, ACS, trusted IdP issuer, and signing credentials |
| IdP metadata | EntityID, SSO endpoint, public signing certificates, bindings |
| XMLDSig | Reference/Digest/SignedInfo/SignatureValue mechanism over XML |
| KeyInfo | Certificate/key hint inside XML; does not become a trust anchor on its own |
| SignatureMethod | Signing algorithm, e.g., RSA-SHA256 |
| DigestMethod | Reference hash algorithm, e.g., SHA-256 |
| Reference URI | Binds the signature to the ID of a Response or Assertion |
| InResponseTo | Correlation with an SP-initiated `AuthnRequest` |
| NotBefore/NotOnOrAfter | Validity window for Assertion and bearer confirmation |
| Replay | Reuse of an already-issued token/assertion |
| Fixture manifest | Contract of scenario, signer, protocol fields, and expected outcome |
| Test clock | Controlled time for testing expiration/skew |
| Test IdP certificate rollover | Phase trusting A/B then retiring A to test rotation |

Using the same word "certificate" for IdP signing, SP decryption, and TLS easily causes confusion. Each key pair has its own purpose, owner, and trust policy.

## 3. Separating Test and Production Environments

A safe architecture:

~~~text
          ISOLATED TEST IDP / FIXTURE SIGNER
          ----------------------------------
          private: TEST_IDP_A.key
          public:  TEST_IDP_A.crt
          issuer:  urn:example:saml:test-idp:alpha
                          |
                          | Signed SAMLResponse
                          | browser / HTTP POST
                          v
          SPRING SERVICE PROVIDER - TEST
          ----------------------------------
          registrationId: fixture-idp
          trusted IdP cert: TEST_IDP_A.crt (public)
          expected issuer:  urn:example:saml:test-idp:alpha
          SP entityID:      urn:example:saml:test-sp:portal
          ACS:              https://portal.test.example/login/saml2/sso/fixture-idp

          PRODUCTION ENVIRONMENT (NO LINK)
          ----------------------------------
          production IdP signing private key
          production SAML verification trust
          production user accounts and sessions
~~~

**Never:**
- Export the production private signing key into CI or developer machines.
- Share one keypair across both test and production IdPs.
- Commit a test private key into Git, container images, docs, or public artifacts.
- Let a production SP trust a test public certificate "for convenience."
- Allow a test IdP to send a `SAMLResponse` to a production ACS with trusted credentials.
- Copy a raw production `SAMLResponse` as a fixture, as it may contain NameIDs, emails, groups, session indexes, and HR details.

**Allowed:** Commit a **public test X.509 certificate** in test resources if production does not trust it and it contains no private key. For secret test private keys, generate them in a temporary workspace/CI secret store with strict ACLs and clean up after the job.

### 3.1. Are Self-Signed Certificates Appropriate?

For SAML testing, **self-signed certificates are appropriate** because the SP normally trusts the signing certificate via configured IdP metadata or administratively approved verification credentials. However, **self-signed does not mean trust-all**. A mathematically valid signature made with an unknown public key must be rejected if that key does not belong to the right IdP registration.

Do not equate SAML signing credential validation with browser TLS PKI. Certificate validity and KeyUsage/EKU/chain processing depend on the trusted IdP policy and verifier implementation; never assume every library checks every PKIX constraint automatically.

## 4. Choosing Test Keys and Algorithms

A broadly compatible RSA profile:
- Use RSA 3072-bit for the test IdP where products support it; at least RSA 2048-bit if baseline permits.
- For XMLDSig, use SignatureMethod RSA-SHA256 or stronger per security policy.
- For signed References, use DigestMethod SHA-256 or stronger.
- Use canonicalization and enveloped-signature transforms per the SAML/XMLDSig profile.
- Block SHA-1/MD5, XSLT/external References, and weak algorithms per baseline.
- ECDSA P-256/P-384 can be used if both IdP and SP are compatible, though do not assume every vendor supports it.
- Set an appropriate test cert validity period and rotate keys when needed.
- Identify keys in the manifest as `TEST-IDP-A`, `TEST-IDP-B` and record certificate fingerprints.

**Distinguish two algorithms:** An X.509 certificate self-signed with SHA-256 does not prove an Assertion carries an RSA-SHA256 XML Signature. The generator must execute a separate XML signing operation after constructing the Response/Assertion.

### 4.1. Use Two Keys to Test Trust, Not Just One

Key A serves positive fixtures for test IdP alpha; Key B serves:
- Negative case "wrong signing key."
- Key rollover tests.
- Cross-IdP registration isolation.
- Proving Spring does not trust a self-declared `KeyInfo`.

Both A and B can share the **same issuer** in a rotation scenario, updating the trust set by phase; use **two distinct issuers** when testing IdP/tenant mix-ups.

## 5. Generating Test-Only Signing Keys with OpenSSL

The example commands below target Linux/macOS with OpenSSL 3.x and a restricted test directory. On Windows, you can use WSL or equivalent ACL/PowerShell commands. Paths reside in the test workspace, never production.

### 5.1. Create Directories and Restrict Access Permissions

~~~bash
umask 077

mkdir -p build/saml-fixtures/private
mkdir -p build/saml-fixtures/public

chmod 700 build/saml-fixtures/private
~~~

Use `build/` as transient output excluded from Git/artifacts. Successful directory creation commands typically produce no stdout; never write passwords/secrets into shell history.

### 5.2. Generate an RSA 3072-bit Test Signing Private Key

~~~bash
openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out build/saml-fixtures/private/idp-test-a.key.pem
~~~

`idp-test-a.key.pem` is a **private key**—never grant the Spring SP access to it just to verify signatures. The command may print progress dots to stderr depending on OpenSSL version; there is no fixed stdout to assert.

### 5.3. Create a Self-Signed Test X.509 Certificate

~~~bash
openssl req -new -x509 \
  -key build/saml-fixtures/private/idp-test-a.key.pem \
  -out build/saml-fixtures/public/idp-test-a.crt.pem \
  -sha256 \
  -days 30 \
  -subj "/CN=Isolated SAML Test IdP A" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature"
~~~

Explanation:
- `-key` uses the newly generated private key to issue the matching certificate.
- `-x509` outputs a certificate rather than a CSR awaiting a CA.
- `-sha256` is the certificate signing algorithm, distinct from the XMLDSig signing algorithm.
- `-days 30` provides an illustrative test cryptoperiod, not a production rule.
- `CA:FALSE` prevents the cert from acting as a CA.
- `digitalSignature` states the intended key usage.
- The X.509 CN is not automatically equal to the IdP SAML entityID.
- Extension flags depend on OpenSSL version; if a tool lacks support, fix via a verified configuration file rather than dropping TLS/SAML checks.

### 5.4. Inspect Fingerprint and Public Key Matching

~~~bash
openssl x509 \
  -in build/saml-fixtures/public/idp-test-a.crt.pem \
  -noout -subject -issuer -dates -fingerprint -sha256

openssl pkey \
  -in build/saml-fixtures/private/idp-test-a.key.pem \
  -pubout \
  -out build/saml-fixtures/public/from-private.pub.pem

openssl x509 \
  -in build/saml-fixtures/public/idp-test-a.crt.pem \
  -pubkey -noout \
  -out build/saml-fixtures/public/from-cert.pub.pem

cmp \
  build/saml-fixtures/public/from-private.pub.pem \
  build/saml-fixtures/public/from-cert.pub.pem
~~~

Both public-key exports share the same OpenSSL PEM format; if byte-identical, `cmp` exits 0 and normally prints nothing. If formats differ, compare DER `SubjectPublicKeyInfo` bytes rather than text. Actual fingerprints are **random per newly generated keypair**; never hard-code a fake fingerprint in test expectations.

### 5.5. Generate an Independent Test Key B

~~~bash
openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out build/saml-fixtures/private/idp-test-b.key.pem

openssl req -new -x509 \
  -key build/saml-fixtures/private/idp-test-b.key.pem \
  -out build/saml-fixtures/public/idp-test-b.crt.pem \
  -sha256 \
  -days 30 \
  -subj "/CN=Isolated SAML Test IdP B" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature"
~~~

Key B is not a copy of A. Never place A and B in the same production trust list unless specifically testing **test IdP key overlap** in an isolated test environment.

## 6. Fixture Suite Structure and Artifact Management

A recommended layout:

~~~text
saml-fixture-kit/
  README.md
  manifest.yaml
  public/
    idp-test-a.crt.pem
    idp-test-b.crt.pem
    idp-test-metadata.xml
  generated/
    signed-response-valid.xml
    signed-assertion-valid.xml
    signed-both-valid.xml
    bad-audience-but-valid-signature.xml
    expired-but-valid-signature.xml
    tampered-after-sign.xml
    signed-by-untrusted-key.xml
  private/
    idp-test-a.key.pem        (ephemeral, excluded from Git)
    idp-test-b.key.pem        (ephemeral, excluded from Git)
  ci/
    expected-results.json
    fixture-clock.txt
~~~

This is a target layout; `generated/*.xml` filenames only exist after the SAML generator/IdP actually signs them. Never treat a filename containing "signed" as proof of a valid signature; every fixture must be **run through the verifier**.

### 6.1. Synthetic Data, Never Real Accounts

Consistent example data:

~~~text
Test IdP A issuer: urn:example:saml:test-idp:alpha
Test IdP B issuer: urn:example:saml:test-idp:beta
Test SP entityID:  urn:example:saml:test-sp:portal
Test ACS URL:     https://portal.test.example/login/saml2/sso/fixture-idp
Test SSO URL:     https://idp.test.example/sso
NameID:           synthetic-user-001@test.invalid
Local test user:  test-user-1001
Local test tenant: tenant-alpha
Mapped role:      ROLE_REPORT_VIEW
Unapproved group: UntrustedAdmin
~~~

Never use `employeeNumber`, real SIDs, real emails, production tenant IDs, or signed assertions from real users. Even a synthetic NameID needs a **stable identity-link policy** in the local test database to test role mapping.

### 6.2. Manifest Recording Key Sources and Expected Outcomes

~~~yaml
suite: isolated-saml2-fixtures
version: 1
profile: web-browser-sso
testIdp:
  entityId: "urn:example:saml:test-idp:alpha"
  keyRef: "test-secret-store:idp-a-private"
  verificationCertificate: "public/idp-test-a.crt.pem"
  signatureAlgorithm: "rsa-sha256"
  digestAlgorithm: "sha256"
testSp:
  entityId: "urn:example:saml:test-sp:portal"
  acs: "https://portal.test.example/login/saml2/sso/fixture-idp"
  registrationId: "fixture-idp"
clock:
  unitTestStrategy: fixed
  fixedInstant: "2026-06-01T12:00:00Z"
cases:
  - id: positive-response-signed
    signer: TEST_IDP_A
    signaturePlacement: RESPONSE
    subject: synthetic-user-001@test.invalid
    expected: AUTHENTICATED
  - id: positive-assertion-signed
    signer: TEST_IDP_A
    signaturePlacement: ASSERTION
    expected: AUTHENTICATED
  - id: bad-audience-signed
    signer: TEST_IDP_A
    audience: urn:example:saml:test-sp:other
    expected: REJECT_AUDIENCE
  - id: tampered-after-sign
    signer: TEST_IDP_A
    mutateAfterSigning: true
    expected: REJECT_SIGNATURE
  - id: wrong-signing-key
    signer: TEST_IDP_B
    expected: REJECT_UNTRUSTED_SIGNER
~~~

**This is the input contract for the project's fixture generator**, not Spring Security YAML autoconfiguration. `keyRef` should point only to a secret store/test volume; never embed literal private keys in the manifest. Error labels represent test-layer expectations; the HTTP failure handler may redirect or return a different HTTP status.

## 7. Public Metadata of the Test IdP

IdP metadata must contain:
- `EntityDescriptor.entityID` matching the test issuer.
- `IDPSSODescriptor` with supported SAML 2.0 protocol.
- `SingleSignOnService` URL/Binding matching the test environment.
- `KeyDescriptor use="signing"` with the **public X.509 certificate** corresponding to A.
- When testing rotation, `KeyDescriptor` entries for A/B per policy.

Illustrative SAML metadata skeleton:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="urn:example:saml:test-idp:alpha">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data/>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.test.example/sso"/>

  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

This is an **incomplete sketch**: the `X509Data` element is empty and therefore **cannot be used as real trust metadata**. The test IdP/metadata generator must populate `ds:X509Certificate` with the Base64 DER of the public cert, complying with XML schema and metadata trust. **Private keys must never appear in metadata.**

### 7.1. PEM Certificate vs. KeyInfo

A PEM certificate contains public material only. SAML metadata `ds:X509Certificate` uses a Base64 DER certificate without PEM header/footer lines inside XML. A `ds:KeyInfo` inside an incoming `SAMLResponse` **never grants trust to an unknown certificate**; the SP must compare against the registration's approved verification credentials.

### 7.2. Key Rollover Metadata

Scenario for the same test IdP:
1. SP currently trusts A.
2. Test IdP publishes cert B; SP trusts A+B.
3. IdP begins signing with B.
4. Verification of B passes during overlap; verification of A passes while not yet retired.
5. SP removes A under change control.
6. Signatures from A are rejected.

When testing a **different IdP/tenant**, never add B to registration alpha just because issuer beta's signature is mathematically valid.

## 8. Spring Boot Test Configuration: SP Installs Only the Public Cert

The example below is an **`application-saml-test.yml`** activated only in the test profile. Verify property names against your Spring Boot version, as naming varies between releases.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          fixture-idp:
            entity-id: "urn:example:saml:test-sp:portal"
            assertingparty:
              entity-id: "urn:example:saml:test-idp:alpha"
              singlesignon:
                url: "https://idp.test.example/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-test-a.crt.pem"
~~~

In Spring Boot/Spring Security:
- `fixture-idp` is the registration ID.
- Top-level `entity-id` is the SP entityID.
- `assertingparty.entity-id` is the trusted test IdP entityID.
- `verification.credentials[].certificate-location` points to the **test IdP public certificate**, never a PEM private key.
- `singlesignon.url` is the IdP endpoint receiving `AuthnRequest`; a real test IdP or protocol-capable test double is required.
- The default SP ACS is typically `/login/saml2/sso/{registrationId}`; check your actual deployment.
- The test profile **must never merge** these trust credentials into production.
- If the test SP must sign `AuthnRequest`, configure a **separate SP signing key** in the signing section; never copy the IdP private key.

### 8.1. Spring SecurityFilterChain

File `SamlSecurityConfig.java` in a Spring Boot project:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

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

The code above is a **Spring configuration class**, not standalone Java. It intentionally uses the default SAML provider/validators rather than manually Base64-decoding and creating an `Authentication`. It requires real dependencies, registration, metadata, test IdP, and ACS. For HTTP-POST `SAMLResponse`, Spring Security applies its own filter/CSRF policy; never disable CSRF across the entire application.

### 8.2. Maven Dependencies

Fragment inside a Spring Boot POM with parent/BOM:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Do not guess OpenSAML, Santuario, and Spring versions from a snippet; use a compatible dependency set. Some releases require the Shibboleth Maven repository. `spring-security-test` helps with MockMvc/business authorization tests, **but does not replace verifying genuinely signed `SAMLResponse` payloads**.

## 9. An Unsigned SAML XML Scaffold for Testing Negative Cases

The example below illustrates only the field structure the fixture generator must build. It has **no XML Signature**, so when submitted to an SP requiring a trusted signature it **must be rejected**, even though the remaining fields look valid.

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_r1"
    Version="2.0"
    IssueInstant="2026-06-01T12:00:00Z"
    Destination="https://portal.test.example/login/saml2/sso/fixture-idp"
    InResponseTo="_request_001">

  <saml:Issuer>urn:example:saml:test-idp:alpha</saml:Issuer>

  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_a1" Version="2.0"
      IssueInstant="2026-06-01T12:00:00Z">

    <saml:Issuer>urn:example:saml:test-idp:alpha</saml:Issuer>

    <saml:Subject>
      <saml:NameID
          Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">synthetic-user-001</saml:NameID>

      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.test.example/login/saml2/sso/fixture-idp"
            InResponseTo="_request_001"
            NotOnOrAfter="2026-06-01T12:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-06-01T11:59:00Z"
        NotOnOrAfter="2026-06-01T12:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:saml:test-sp:portal</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-06-01T11:59:55Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>

  </saml:Assertion>
</samlp:Response>
~~~

**Key observations:**
- Response and Assertion must have unique IDs.
- `Issuer` must be a genuinely trusted test IdP.
- `Destination` and `SubjectConfirmationData.Recipient` must match the ACS.
- `AudienceRestriction` must match the SP entityID.
- `InResponseTo` must match the **pending `AuthnRequest`**, not an arbitrary constant in E2E.
- `NotOnOrAfter` expires, so this static assertion cannot serve as a positive fixture after June 2026 on a real clock.
- The synthetic NameID must map to a local test account.
- **Missing Signature** → expected reject. For a positive case, the generator must sign with XMLDSig, never paste a fake `SignatureValue`.

## 10. Generating Real SAML Signatures with a Test IdP or OpenSAML

A SAML XML Signature is not JCA signing directly over the whole XML string. You need to:
- Build SAML `Response` and `Assertion` objects per schema/profile.
- Populate issuer, subject, audience, recipient, times, correlation, and attributes.
- Attach `ds:Signature` on the appropriate Response or Assertion.
- Set approved SignatureMethod, DigestMethod, canonicalization, and transforms.
- Reference the exact ID of the signed Response/Assertion.
- Use the **test IdP private key** to generate the signature.
- Marshall the XML and invoke the signer via supported OpenSAML APIs.
- Never mutate signed XML nodes after signing.
- Send the Base64 `SAMLResponse` via HTTP-POST binding to the ACS.
- Have the Spring SP use the test public cert to verify XMLDSig.

**Never create a signature by inserting raw Base64 bytes into XML** or running `SHA256withRSA` over an uncanonicalized XML string. OpenSAML/the SAML test IdP library should own XMLDSig because marshaling APIs, algorithms, and object models differ across versions.

### 10.1. Response-Signed, Assertion-Signed, and Both-Signed

| Fixture | Signature placement | Expected |
|---|---|---|
| valid-response-signed | Reference to `Response.ID` | Accept when assertion lies inside verified Response subtree |
| valid-assertion-signed | Reference to `Assertion.ID` | Accept when consumed assertion is signed |
| valid-both-signed | Both Response and Assertion | Accept when signatures and rules all pass |
| unsigned | No trusted signature | Reject |
| wrong-key | Signed by test key B while SP trusts only A | Reject untrusted signer |
| tampered | Signed content modified after signing | Reject signature |
| multiple-assertions | Signed A1 while app tries to use unsigned A2 | Reject XSW or schema/policy |

Spring Security/OpenSAML typically require the Response or all Assertions to be signed per policy; never disable checks just to make a "fixture pass."

### 10.2. Signature References and IDs

- XMLDSig `Reference URI="#_r1"` signs Response ID `_r1`.
- `Reference URI="#_a1"` signs Assertion ID `_a1`.
- IDs must be unique with no duplicate ID resolution.
- No external URI/file references or transforms outside the allowlist.
- Never accept a `KeyInfo` certificate as a trust anchor on its own.
- Never read raw XML via `getElementsByTagName("NameID")` after verifying a different node.
- Consumed NameID/Attributes must come from the **exact validated protected assertion**.

## 11. Three Categories of Negative Fixtures to Keep Separate

### 11.1. Cryptographic Negative: Modify After Signing

Build a valid `SAMLResponse`, sign with key A, **then** change one byte inside signed content (e.g., `NameID`). Do not re-sign. Expect XMLDSig digest/signature verification to FAIL. This is not an Audience validation test.

### 11.2. Trust Negative: Signer Differs from Approved Key

Build a `SAMLResponse` with all valid fields, but sign it with private key B. When the SP trusts only certificate A, the signature may be mathematically valid under public key B, yet the **signer is not authorized by the IdP registration** → reject.

Do not solve this by reading certificate B from `ds:KeyInfo` and treating it as trusted. This is a core control.

### 11.3. Protocol Negative: Validly Sign Invalid Fields

To test Audience:
1. Build an Assertion with a wrong Audience.
2. Keep Issuer, Recipient, Destination, time, and request correlation valid.
3. Sign the **wrong-Audience Assertion** with test private key A.
4. Spring signature verification PASSES, but `AudienceRestriction` validation FAILS.

Do the same for Recipient, Destination, `InResponseTo`, expired/future Conditions, `SubjectConfirmation`, Response Status, and wrong issuer. **If you modify Audience after signing, the first failure will be signature verification**, failing to prove the audience validator works.

## 12. Key Rotation Fixtures

Use A/B across phases:

| Phase | Test SP trust set | Key signing Response | Expected |
|---|---|---|---|
| Baseline | A | A | Accept |
| Baseline | A | B | Reject |
| Overlap | A, B | A | Accept |
| Overlap | A, B | B | Accept |
| Retired A | B | B | Accept |
| Retired A | B | A | Reject |
| Cross IdP | Alpha trusts A | Issuer beta, signer B | Reject |
| Untrusted KeyInfo | A | Signer B, KeyInfo B | Reject |

Key rotation does not mean the IdP issuer changes. With **the same IdP rotating signing keys**, both A and B belong to issuer alpha during the approved window. With a **cross-IdP scenario**, issuers alpha/beta differ and trust must stay separated per registration.

## 13. Standalone Java 17: Verifying Signatures with the Right Test Key

The JDK 17 code below generates two random RSA keypairs in memory, signs a byte message with key A, verifies with public A, and tests tampering and wrong key B. **This is a JCA demo of key separation, not a SAML XMLDSig signer**, because it performs no XML Reference/canonicalization.

File `TestSigningKeysDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class TestSigningKeysDemo {

    static boolean verify(
            byte[] message,
            byte[] signedBytes,
            PublicKey trustedKey) throws Exception {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedKey);
        verifier.update(message);
        return verifier.verify(signedBytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair testIdpA = generator.generateKeyPair();
        KeyPair testIdpB = generator.generateKeyPair();

        byte[] data =
                "synthetic-test-response".getBytes(StandardCharsets.UTF_8);
        byte[] changed =
                "modified-test-response".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(testIdpA.getPrivate());
        signer.update(data);
        byte[] signed = signer.sign();

        System.out.println("valid-a=" +
                verify(data, signed, testIdpA.getPublic()));

        System.out.println("tampered=" +
                verify(changed, signed, testIdpA.getPublic()));

        System.out.println("wrong-b=" +
                verify(data, signed, testIdpB.getPublic()));

        System.out.println("real-saml-xmldsig=false");
    }
}
~~~

Run:

~~~bash
javac TestSigningKeysDemo.java
java TestSigningKeysDemo
~~~

**Exact stdout:**

~~~text
valid-a=true
tampered=false
wrong-b=false
real-saml-xmldsig=false
~~~

**Notes:**
- Private keys A/B are ephemeral and never printed to logs.
- This exercise uses RSA 2048 for fast execution in a JDK demo, whereas the OpenSSL commands above create RSA 3072 for full test keys.
- `valid-a` is true because public A matches private A.
- `tampered` and `wrong-b` are both false.
- This directly signs a byte string. Real SAML requires XMLDSig Signature/Digest/Reference/Transforms and IdP trust verification; never use this class as a SAML authentication provider.

## 14. Standalone Java 17: Testing SAML Fixture Policy on a Fixed Clock

The next demo **assumes** signature and IdP trust have already been verified by the framework. It models Audience, Recipient, `InResponseTo`, Conditions, and replay to show how independent negative fixtures are designed.

File `SamlFixtureRulesDemo.java`:

~~~java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class SamlFixtureRulesDemo {

    static final String ISSUER = "urn:example:saml:test-idp:alpha";
    static final String AUDIENCE = "urn:example:saml:test-sp:portal";
    static final String ACS =
            "https://portal.test.example/login/saml2/sso/fixture-idp";
    static final String REQUEST = "_request_001";

    record Fixture(
            String assertionId,
            String issuer,
            String audience,
            String recipient,
            String inResponseTo,
            Instant notBefore,
            Instant notOnOrAfter,
            String subject) {
    }

    static String validate(
            Fixture f, Instant now, Set<String> seen) {

        if (!ISSUER.equals(f.issuer())) {
            return "REJECT_ISSUER";
        }
        if (!AUDIENCE.equals(f.audience())) {
            return "REJECT_AUDIENCE";
        }
        if (!ACS.equals(f.recipient())) {
            return "REJECT_RECIPIENT";
        }
        if (!REQUEST.equals(f.inResponseTo())) {
            return "REJECT_CORRELATION";
        }
        if (now.isBefore(f.notBefore())
                || !now.isBefore(f.notOnOrAfter())) {
            return "REJECT_TIME";
        }
        if (!seen.add(f.assertionId())) {
            return "REJECT_REPLAY";
        }
        return "ACCEPT:" + f.subject();
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");
        Instant start = Instant.parse("2026-06-01T11:59:00Z");
        Instant end = Instant.parse("2026-06-01T12:05:00Z");

        Fixture good = new Fixture(
                "_a1", ISSUER, AUDIENCE, ACS,
                REQUEST, start, end, "synthetic-user-001");

        Set<String> seen = new HashSet<>();
        System.out.println("good=" + validate(good, now, seen));
        System.out.println("replay=" + validate(good, now, seen));

        Fixture wrongAudience = new Fixture(
                "_a2", ISSUER, "urn:example:other-sp", ACS,
                REQUEST, start, end, "synthetic-user-001");
        System.out.println("audience=" +
                validate(wrongAudience, now, new HashSet<>()));

        Fixture wrongRecipient = new Fixture(
                "_a3", ISSUER, AUDIENCE, "https://other.test.example/acs",
                REQUEST, start, end, "synthetic-user-001");
        System.out.println("recipient=" +
                validate(wrongRecipient, now, new HashSet<>()));

        Fixture expired = new Fixture(
                "_a4", ISSUER, AUDIENCE, ACS,
                REQUEST, start, now, "synthetic-user-001");
        System.out.println("expired=" +
                validate(expired, now, new HashSet<>()));

        Fixture wrongRequest = new Fixture(
                "_a5", ISSUER, AUDIENCE, ACS,
                "_wrong_request", start, end, "synthetic-user-001");
        System.out.println("correlation=" +
                validate(wrongRequest, now, new HashSet<>()));
    }
}
~~~

Run:

~~~bash
javac SamlFixtureRulesDemo.java
java SamlFixtureRulesDemo
~~~

**Exact stdout:**

~~~text
good=ACCEPT:synthetic-user-001
replay=REJECT_REPLAY
audience=REJECT_AUDIENCE
recipient=REJECT_RECIPIENT
expired=REJECT_TIME
correlation=REJECT_CORRELATION
~~~

**Limitations:**
- `validate` does not verify XML signatures, issuer trust, Destination/Status, full `SubjectConfirmationData`, encrypted Assertions, or schema.
- `HashSet` models replay within a single JVM only, not a distributed production replay cache.
- The fixed clock belongs to the exercise; it does not alter Spring/OpenSAML's clock unless a specific API/validator exposes a hook.
- An `ACCEPT` result in this class only means "passed simulated checks"—it does **not** mean Spring Security created a session.

## 15. Test Clock, Freshness, and Request Correlation

**For unit tests**, you can fix:
~~~text
now = 2026-06-01T12:00:00Z
NotBefore = 2026-06-01T11:59:00Z
NotOnOrAfter = 2026-06-01T12:05:00Z
~~~

However, such static data is **expired against a real clock after June 2026**. Never disable SAML time validation or stretch clock skew excessively just to make static fixtures "pass." Use:
- An injectable clock where supported by the component.
- Fresh timestamps generated from a UTC clock when E2E tests run.
- Unique `Response.ID` and `Assertion.ID` per positive transaction.
- `SubjectConfirmationData.NotOnOrAfter` aligned with the bearer validity window.
- Actual `AuthnRequest.ID` generated by the SP and stored in the session.

### 15.1. Do Not Hard-Code InResponseTo in Full HTTP E2E

SP-initiated SSO:
1. Browser requests a protected route.
2. SP generates an `AuthnRequest` with a fresh ID.
3. Test IdP receives the request and reads the exact ID after validating routing/signature when required.
4. `Response.InResponseTo` and `SubjectConfirmationData.InResponseTo` reference that ID.
5. SP verifies correlation.

If the fixture always sends `_request_001` while the SP expects `_request_999`, a correlation failure is expected. Do not "fix" it by disabling `InResponseTo`.

**IdP-initiated SSO** may omit `InResponseTo` per its own profile; test it only when the deployment explicitly enables unsolicited flows with a dedicated policy. Never treat it as a positive SP-initiated fixture.

### 15.2. Replay Cases Must Be Distinguished from Correlation

Submit the exact same signed assertion ID/Response bytes twice and verify rejection per replay policy. Note that a second submission often fails because `AuthnRequest` state was already consumed, which does not necessarily prove the replay cache itself works. Genuine replay tests must isolate:
- Provider/session correlation.
- Assertion ID replay store.
- TTL and multi-node consistency.

Do not assume a product blocks every replay variant unless configured and tested against contract.

## 16. Test Matrix Along Clear Boundaries

| Case | Data or mutation | Expected |
|---|---|---|
| P01 | Response signed with key A, valid claims/conditions | Authentication success |
| P02 | Assertion signed with key A, valid Response context | Authentication success |
| P03 | Both Response and Assertion properly signed | Authentication success |
| P04 | Key rotation overlap A+B, signed with B | Accept if B is in trusted credentials |
| P05 | IdP A valid, active local user belonging to tenant | Approved authorities only |
| N01 | Both Response and Assertion unsigned | Reject signature requirement |
| N02 | Modify NameID after signing | Reject digest/signature |
| N03 | Modify Audience after signing | Reject digest/signature |
| N04 | Wrong Audience then signed **after the edit** | Reject Audience |
| N05 | Wrong Recipient then validly signed | Reject Recipient |
| N06 | Wrong Destination then validly signed | Reject Destination |
| N07 | Wrong `InResponseTo` then validly signed | Reject correlation |
| N08 | Future `NotBefore`, validly signed | Reject time |
| N09 | Expired `NotOnOrAfter`, validly signed | Reject time |
| N10 | Expired `SubjectConfirmationData`, validly signed | Reject bearer confirmation |
| N11 | Non-Success Status, validly signed | Reject protocol |
| N12 | Issuer differs from registered IdP, validly signed | Reject issuer |
| N13 | Signed with Key B, SP trusts only A | Reject untrusted signer |
| N14 | `KeyInfo` contains attacker key, SP trusts A | Reject untrusted signer |
| N15 | Duplicate Response/Assertion IDs | Reject ambiguous ID |
| N16 | Signed A1 and unsigned A2, app uses A2 | Reject XSW |
| N17 | Reference URI signs an unused node | Reject signed target |
| N18 | External XML entity / DTD | Parser rejects |
| N19 | Huge XML / deep nesting | Reject limits |
| N20 | Replay same assertion ID | Reject replay per policy |
| N21 | IdP-initiated when disabled | Reject unsolicited |
| N22 | Issuer A under registration belonging to B | Reject multi-IdP mix-up |
| N23 | Valid SAML but disabled local account | Deny business access |
| N24 | Valid SAML group `UntrustedAdmin` | Does not automatically grant `ROLE_ADMIN` |
| N25 | `EncryptedAssertion` wrong SP key | Reject decryption |
| N26 | SHA-1/MD5 outside policy | Reject algorithm |
| N27 | Key A retired, response still signed with A | Reject |
| N28 | `RelayState` unapproved external URL | No open redirect |
| N29 | Same NameID at IdP B when unlinked | Does not merge accounts |
| N30 | Validly signed SAML Response for a different SP EntityID | Reject cross-SP replay |

**Critical technique:** For N04–N12, build the wrong field **before signing**, so signature verification still PASSES and the protocol validator is genuinely exercised. For N02–N03, intentionally mutate **after signing** to test digest/signature checks. For N13–N14, the signature is mathematically valid under B, yet the SP does not trust the signer. Never conflate these three groups.

### 16.1. XSW and Matching Signed Object to Consumed Object

XML Signature Wrapping can occur when the verifier validates Assertion A while the app reads NameID/Attributes from an unsigned Assertion B. Tests should verify:
- Reference URI points to the expected Response/Assertion.
- XML IDs are unique, with no duplicates.
- Strict XML structure and namespaces.
- Application code never calls `getElementsByTagName` or global XPath on raw XML to extract security claims.
- Only `Saml2AuthenticatedPrincipal` verified by OpenSAML/Spring is consumed.
- NameID and `AttributeStatement` are never mixed across Assertions.

A signed Response that truly covers the assertion subtree will fail digest verification if you alter that subtree's content. XSW exploits rely on **selection/scope/parser ambiguity**, not magic that breaks RSA.

## 17. Testing Against Real Spring Security/OpenSAML

Distinguish three layers:

**Unit tests**
- Java 17 JCA key separation.
- Fixture manifest, role mapping, fake-clock policy.
- Synthetic identity/tenant lookup.
- Do not prove real XMLDSig validity.

**Provider-level integration tests**
- Test generator produces genuinely signed SAML Response/Assertion XML.
- Spring `OpenSaml5AuthenticationProvider` (or version-appropriate provider) verifies using trusted `RelyingPartyRegistration`.
- Assert exact principal/attributes after validation.
- Test key trust, Audience, Recipient, Conditions, and Assertion signature coverage.

**HTTP end-to-end tests**
- Browser/test client triggers `/saml2/authenticate/{registrationId}` or GETs a protected resource.
- Spring generates `AuthnRequest`.
- Test IdP receives request and issues a signed `SAMLResponse` via HTTP POST.
- Browser POSTs Base64 `SAMLResponse` to `/login/saml2/sso/{registrationId}`.
- Spring processes ACS, cookies, state, and `InResponseTo`.
- Verify authenticated session or rejection.
- Test logout/expiration/replay per policy.

**Insufficient:** Mocking a Spring `Authentication` in MockMvc and saying "signed SAML responses were tested." MockMvc is great for business authorization, but does not replace XMLDSig/OpenSAML integration tests.

### 17.1. HTTP Status Is Not the Final Assertion

SAML Web SSO may return a 302 redirect to a login/success page and vary by failure handler. Tests should assert:
- Presence/absence of `SecurityContext.Authentication`.
- `Authentication.getPrincipal()` is a validated `Saml2AuthenticatedPrincipal`.
- Subject/NameID matches the expected synthetic user.
- Roles/authorities match policy only.
- No local session is created on invalid input.
- Clear error category in test logs without raw secrets.

Never assert HTTP status 200/302 alone.

## 18. Secret-Safe CI/CD for Fixture Generation

Pipeline:

~~~text
Checkout test code
      |
      v
Scan secrets + verify test-only environment
      |
      v
Generate ephemeral IdP test signing key/cert
      |
      v
Start isolated test IdP + Spring SP with test public cert
      |
      v
Generate fresh XMLDSig signed positive fixtures
      |
      v
Generate signed protocol-negative fixtures
      |
      v
Generate wrong-key and tamper-after-sign fixtures
      |
      v
Run OpenSAML provider tests + HTTP ACS E2E
      |
      v
Write sanitized JUnit reports
      |
      v
Delete ephemeral keys, tokens, SAML dumps and sessions
~~~

### 18.1. Preventing Secret Leakage in CI

- Test private signing keys reside only in an ephemeral secret volume/CI secret store.
- Never enable shell debug `set -x` when handling secrets.
- Never print PEM private keys into build logs.
- Never commit private keys, bake them into Docker layers, or publish them in public artifacts.
- Public test certs may be versioned once profile and scope are fixed.
- Restrict external forks and unprivileged CI jobs from accessing the test secret manager.
- Never mount production secrets into the test namespace.
- Never publish raw `SAMLResponse` payloads containing PII or access tokens.
- Clean up keyfiles after jobs, remembering that file deletion does not scrub already-uploaded artifacts or snapshots.
- Secret scanning and deployment guards must block test certs from appearing in production trust configs.

### 18.2. Production Guards Are an Independent Requirement

Before production rollout:
1. No `urn:example:saml:test-idp:alpha` issuer in production registrations.
2. No public test certificate fingerprint in the production trust list.
3. `application-saml-test.yml` is not active.
4. No `acceptAnySamlSignature` fallback or disabled validators in code.
5. Production IdP metadata is approved through a trusted channel.
6. Production SP signing/decryption secrets appear only where required.

If a guard fails, block deployment. Never expand trust just to make a SAML test login work on prod.

## 19. Symptom-Based Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| XML looks right but login fails | Missing XMLDSig | Use real OpenSAML/test IdP signer |
| `SignatureValue` fails | Signed content altered / wrong transforms | Check Reference, digest, canonicalization |
| Signer B verifies under B but Spring rejects | SP trusts only A | Expected trust negative |
| Wrong Audience test fails signature first | Audience edited after signing | Build wrong value first, sign afterward |
| Signed Response passes but Assertion-signed fails | Profile/Reference/conditions mismatch | Check signing mode and verifier |
| Static positive fixture expired | `NotOnOrAfter` is in the past | Fresh timestamps or injected clock |
| `InResponseTo` mismatch | Did not capture actual `AuthnRequest` ID | Test full SP-initiated choreography |
| Destination/Recipient mismatch | Wrong ACS URL or reverse proxy | Check HTTPS scheme/host/port/path |
| Unknown `registrationId` | Wrong URL routing/config profile | Check test `RelyingPartyRegistration` |
| Test IdP metadata cert differs from signer | Cert/key pair mismatch | Compare OpenSSL public keys/fingerprints |
| Key rollover B fails | B not yet added to trust | Check phase and approved certs |
| A still passes after retirement | Trust A not removed | Fail rotation test |
| Duplicate ID passes and picks wrong subject | XML Signature Wrapping | Harden parser/Reference checks |
| Test group Admin grants `ROLE_ADMIN` | Role mapping lacks allowlist | Check trusted attributes/policy |
| Single pod fails | Cert clock/cache out of sync | Synchronize nodes and replay store |
| XML with XXE still processed by parser | Missing secure parser config | Block DTD/external entities |
| Test cert accidentally in prod | Missing deployment guard | Block release, assess incident scope |
| Cert expired | Test cert lifecycle | Reissue cert; do not disable security checks |
| Logout test immediately SSOs again | IdP session still active | Distinguish local session from IdP SSO |

**Debug in order:** keypair → cert fingerprint → manifest/test profile → XMLDSig signature/Reference → IdP issuer trust → SAML conditions/correlation → session/replay → local account/role.

## 20. Fixture Suite Quality Checklist

- [ ] Test IdP private signing key is **distinct** from production keys and never present on the SP.
- [ ] Test private keys are protected in a secret store or ephemeral CI volume.
- [ ] Public test certificate is pinned to the exact relying-party registration.
- [ ] Metadata issuer, SSO endpoint, and ACS/SP entityID are consistent.
- [ ] Positive Response-signed and Assertion-signed fixtures both use **real XMLDSig**.
- [ ] NameID/Attributes come solely from assertions protected by trusted signatures.
- [ ] Negative tamper-after-sign test → signature rejected.
- [ ] Negative wrong-signing-key test → untrusted signer rejected.
- [ ] Negative wrong Audience/Recipient/`InResponseTo` tests have **valid signatures**.
- [ ] Negative `NotBefore`/`NotOnOrAfter` and `SubjectConfirmation` expiration tests exist.
- [ ] XSW/duplicate ID and unsupported multiple Assertions tests exist.
- [ ] Replay, unsolicited flow, multi-IdP, and tenant tests exist.
- [ ] Rotation overlap A+B and retirement of A are tested.
- [ ] Local disabled user and group-to-role allowlist tests exist.
- [ ] No PII, real emails, or production tokens appear in fixtures.
- [ ] Test clocks/IDs/correlation are managed explicitly.
- [ ] Full HTTP ACS integration runs with a real test IdP signer.
- [ ] Default Spring SAML validators are never disabled in tests.
- [ ] CI secret scanning and artifact cleanup are active.
- [ ] Production deployment guards reject test issuers/certs.
- [ ] Fixture documentation states purpose, signer, expected failure reason, and lifecycle.

## 21. Review Questions

1. **Why is a separate test IdP signing key required?** So CI never holds authority to sign as the production IdP.
2. **Does the SP use the test IdP's private key to verify?** No, the SP uses the public certificate.
3. **What is a test SP signing private key used for?** Signing `AuthnRequest`/`LogoutRequest` when needed, separate from the IdP key.
4. **Is the SP decryption private key the same as the IdP verification certificate?** No.
5. **Can a self-signed test certificate be used?** Yes, if trust is pinned/approved under the test registration.
6. **Does having a certificate mean XML is already signed?** No, XMLDSig is required.
7. **Does JCA `SHA256withRSA` over a UTF-8 string produce a SAML XML signature?** No, Reference/Digest/C14N/transforms are required.
8. **To test wrong Audience, edit before or after signing?** Before, then re-sign.
9. **To test signature tampering, edit before or after signing?** After, without re-signing.
10. **What does wrong key B with issuer A test?** Certificate trust on the exact registration.
11. **Does `KeyInfo` itself determine whether a key is trusted?** No.
12. **Can static positive XML be reused forever?** No, once timestamps expire or correlation/replay triggers.
13. **What value does `InResponseTo` require?** The exact pending `AuthnRequest` ID.
14. **Can a signed Response protect an individually unsigned Assertion?** Yes, if the Assertion lies within the signed Response scope and the profile permits it.
15. **When does XSW occur?** When the signature verifies object A but the app reads claims from object B.
16. **Does a mocked MockMvc principal test XMLDSig?** No.
17. **Should test certificate A be installed in production trust?** No.
18. **Which states do key rotation tests require?** A-only, A+B overlap, B-only.
19. **Local account disabled despite valid SAML?** The app must still deny business access.
20. **Why not assert HTTP 200 only?** SSO redirects and failure handlers may return 302; verify `SecurityContext`/principal.
21. **Is there any benefit to using real subjects in tests?** No; create synthetic identities.
22. **No signature but valid Audience—should login succeed?** No.
23. **Why must replay be tested?** A signature may still be valid on an old assertion, yet reuse must be blocked per policy.
24. **What is the core to passing QA?** Separate keys, real XMLDSig, accurate trust, protocol checks, expected negatives, and CI isolation.

## 22. Official References

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — Relying Party Registration and Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Spring Boot — SAML 2.0 Relying Party Properties: https://docs.spring.io/spring-boot/reference/security/saml2.html
- Spring Security — Servlet Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security — MockMvc Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP — XML External Entity Prevention: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
- W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C — XML Signature Best Practices: https://www.w3.org/TR/xmldsig-bestpractices/
- OASIS — SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS — SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OpenSSL — genpkey: https://docs.openssl.org/3.0/man1/openssl-genpkey/
- OpenSSL — req and self-signed certificates: https://docs.openssl.org/3.0/man1/openssl-req/
- OpenSSL — x509 inspection: https://docs.openssl.org/3.0/man1/openssl-x509/

**Summary:** A trustworthy SAML2 fixture suite must use an **isolated test IdP private key**, a public verification certificate pinned only to a **test `RelyingPartyRegistration`**, accurate IdP metadata, synthetic users, real XMLDSig signatures, fresh IDs/timestamps/correlation, explicit expected security outcomes, and secret-safe CI. Separate three failure classes: **tamper-after-sign → signature failure**, **wrong signer → trust failure**, and **invalid SAML field with valid signature → protocol validation failure**. Finally, only create a Spring Security `Authentication` from an assertion protected by a **trusted signature** that passes all audience/recipient/conditions/correlation/replay checks, then enforce local account/tenant/role checks independently.
