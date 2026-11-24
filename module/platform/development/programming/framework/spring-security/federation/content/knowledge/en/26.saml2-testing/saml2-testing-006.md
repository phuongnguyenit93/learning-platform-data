# Testing Invalid Signatures, Wrong Issuers, and Untrusted Keys

**Module:** Spring Security – federation  
**Knowledge group:** SAML2 Testing  
**Scope:** SAML 2.0 Web Browser SSO, HTTP-POST to ACS, Spring Boot 3.x, Spring Security 6.5.x, OpenSAML 4/5 per version, Java 17+. Covers controlled negative testing, Relying Party trust configuration, a standalone Java 17 example, and an integration test skeleton with MockMvc.

## 1. Learning Objectives and Success Criteria

After this lesson, you must be able to distinguish and test **three distinct failure types**:

1. **Invalid signature:** XML or `SignatureValue` was modified after the IdP signed it, `Reference`/Digest no longer matches, or the signature algorithm/transform violates policy. Mere presence of a signature in XML is insufficient; cryptographic verification over the **exact signed element** must succeed.
2. **Wrong issuer:** XML is **validly signed with a trusted key**, yet the Response/Assertion `Issuer` does not match the Identity Provider registered for that flow. This test must **intentionally re-sign** the payload with the trusted test key after changing `Issuer` to separate issuer errors from signature errors.
3. **Untrusted key:** XML is validly signed with test-controlled key B, whereas the Service Provider (SP) is configured to trust only IdP signing key A. Even if `KeyInfo` inside the XML embeds public certificate B, the SP **must never self-promote B into a trust anchor**.

The **PASS** condition for the whole test suite is not merely "the endpoint returned HTTP 400/401." A SAML system may redirect 302 to a login page for all errors. To conclude testing is sound, you need a **positive control**: a valid Response signed by the trusted IdP must genuinely produce an `Authentication`; then each negative case must **create no `Authentication`, persist no new `SecurityContext` session, grant no roles, and deny access to protected resources**.

**Do not reuse the same broken fixture for every test.** For example, expired XML, wrong Audience, or missing `InResponseTo` can cause all three tests to error without ever proving signature/issuer/trust validation executed.

## 2. Data, Components, and Three Different Verification Layers

In the SAML flow:

~~~text
Browser POST /login/saml2/sso/corp-idp
    SAMLResponse = Base64(XML)
              |
              v
Saml2WebSsoAuthenticationFilter
    -> Saml2AuthenticationTokenConverter
    -> RelyingPartyRegistration: corp-idp
              |
              v
OpenSAML authentication provider
    [A] XML parsing, signature/reference validation
    [B] trusted verification credential / issuer policy
    [C] Destination/Audience/Conditions/InResponseTo/Subject
              |
              v
Saml2Authentication / local authorization
    -> SecurityContext / authenticated session
~~~

Provider names depend on version and dependencies: **`OpenSaml4AuthenticationProvider`** or **`OpenSaml5AuthenticationProvider`**. The Spring Security 6.5 line includes APIs supporting OpenSAML 5; do not write tests assuming every Spring Boot 3 build automatically picks the same provider.

### Three Identities to Distinguish

| Value | Example | Where checked? |
| --- | --- | --- |
| **IdP issuer/entity ID** | https://idp.example.test/metadata | Must match the registered asserting party |
| **SP entity ID/Audience** | https://sp.example.test/metadata | SP's `AudienceRestriction`/recipient policy |
| **IdP signing key/certificate** | cert A from trusted onboarding channel | Public key used to verify XMLDSig |
| **ACS/Destination** | https://sp.example.test/login/saml2/sso/corp-idp | Response receiving endpoint, properly configured |
| **Registration ID** | corp-idp | Selects the SP–IdP `RelyingPartyRegistration` |
| **NameID/Subject** | alice@example.test | Trusted only after SAML validation and local mapping |

**Issuer is not Audience.** If XML has the "right IdP" `Issuer` but an `Audience` for another SP, that is an Audience error, not an Issuer test. If certificate B is untrusted while the XML also has the wrong Issuer, the resulting failure cannot prove which boundary actually rejected it.

### SAML Response/Assertion Can Be Signed Differently

Depending on the IdP and policy, the **Response** may be signed, the **Assertion** may be signed, or both. In SAML Browser SSO, signature scope and assertion validation rules depend on profile, framework, and IdP contract. Tests must clearly specify **which object is signed**, which element `Signature` `Reference` targets, and which Assertion may be consumed after verification.

A signed Response enclosing an Assertion can cover integrity of the Assertion per profile. An individually signed Assertion must be verified using trusted IdP credentials. **This does not mean every XML element with the same tag name outside the signed scope is trustworthy.**

## 3. What Does XMLDSig Check?

An XML signature typically contains:

- **SignedInfo**: `CanonicalizationMethod`, `SignatureMethod`, `Reference`.
- **Reference URI="#id"**: points to the exact registered Response or Assertion ID.
- **Transforms**: e.g., enveloped signature and canonicalization; dangerous custom transforms must be disallowed.
- **DigestMethod/DigestValue**: verifies the referenced content was not altered.
- **SignatureValue**: signature value of canonicalized `SignedInfo` under the IdP's private key.
- **KeyInfo/X509Data** (if present): self-declared key metadata inside the document. **`KeyInfo` is not a trust anchor**.

~~~text
<samlp:Response ID="_resp123">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
    <ds:Signature>
        <ds:SignedInfo>
            <ds:Reference URI="#_resp123">
                ... digest/transforms ...
            </ds:Reference>
        </ds:SignedInfo>
        ... SignatureValue ...
        ... optional KeyInfo ...
    </ds:Signature>
    <saml:Assertion ID="_assert123">
        ... Subject, Conditions, AuthnStatement ...
    </saml:Assertion>
</samlp:Response>
~~~

**This is an XML diagram, not a validly signed fixture.** Abbreviated sections cannot be used directly in tests. Real fixtures must include standard XML namespaces, IDs, timestamps, ACS, Conditions, signatures, and SAML bindings generated by a test IdP or OpenSAML fixture factory.

To conclude "signature verified," the validator must verify Signature/Reference/Digest **over the exact node consumed**. A valid signature on Assertion A does not make another Assertion B safe. That is why regression suites should include **XML Signature Wrapping**, duplicate IDs, and unsigned sibling Assertions.

### A Certificate Inside KeyInfo Can Be Self-Declared

If an attacker generates key pair B, signs the Response with B, and embeds certificate B in `KeyInfo`, the signature can be **cryptographically self-consistent** when verified with B. Yet if the registered IdP only uses key A, **the SP must reject it**. Never extract a public key/certificate from a response and trust it as an IdP credential by default.

**Rule:** Select verification credentials from **trusted `RelyingPartyRegistration`/metadata per policy**; never create trust anchors from untrusted XML or HTTP requests.

## 4. Preparing the Test Harness: Baseline First, Negatives Second

A good fixture suite requires:

- **Test IdP holding private key A**, with public certificate A trusted by the SP via out-of-band configuration.
- **Private key B** generated separately, **absent** from the SP's trust store.
- An **SP registration** with `registrationId=corp-idp`, right IdP EntityID, right ACS/public URL, and key A.
- Reasonable clock: fresh `IssueInstant`/`NotBefore`/`NotOnOrAfter` per test; never use expired assertions.
- Valid **Audience/Recipient/Destination**; SAML Status `Success`; synthetic user's NameID permitted by the local app.
- For **SP-initiated SSO**, create a real `AuthnRequest` and ensure `InResponseTo` points to the request ID still stored in the same session. If using IdP-initiated SSO, follow the unsolicited response policy; do not assume every configuration permits it.
- Unique Response ID/Assertion ID per run; do not reuse fixtures causing replay failures.
- Explicitly match signing on Response, Assertion, or both to the production contract.
- Prepare a **positive baseline fixture** and negative fixtures derived **from that same valid baseline**.

**Consistent example identifiers:**

~~~text
registrationId:     corp-idp
IdP entityID:       https://idp.example.test/metadata
IdP login URL:      https://idp.example.test/sso
SP entityID:        https://sp.example.test/metadata
ACS:                https://sp.example.test/login/saml2/sso/corp-idp
trusted key:        idp-signing-A.pem
untrusted key:      other-idp-B.pem
subject:            alice@example.test
~~~

The **example.test** domain is reserved for documentation and testing, not live services. The key files in the example are **public certificates** for verification. Private keys A/B live solely inside a controlled test IdP/fixture generator—**never give an IdP private key to a production SP**.

### What Must the Positive Control Prove?

Send a valid Response to the ACS through the exact same flow/session; verify:

1. XML decoding and parsing succeed.
2. The signature on the target node verifies with trusted cert A.
3. `Issuer` matches the registered IdP EntityID.
4. `Audience`, `Recipient`, `Destination`, timestamps, `InResponseTo`, and `SubjectConfirmation` are valid.
5. The user principal is created from the validated Assertion.
6. Spring Security creates `Authentication`, and `SecurityContext` is persisted via the app's session mechanism.
7. A follow-up GET to a protected endpoint with that session succeeds per local authorization.

If the baseline fails, **stop evaluating negative tests**. Any subsequent "unauthenticated" result could be a false positive caused by missing fixtures or misconfiguration.

## 5. Case A: Invalid Signature

**Test goal:** prove the SP rejects tampered XML or invalid `SignatureValue`/`DigestValue`.

An isolated test:

1. Create a valid Response for the right IdP/ACS/Audience/Subject with a valid XMLDSig from A.
2. After signing, **change a value inside the signed Reference**, such as changing NameID from `alice@example.test` to `admin@example.test`, **without re-signing**.
3. Keep `Issuer`, certificate A, timestamps, `Destination`, `InResponseTo`, and remaining attributes valid.
4. Submit through the ACS with the matching request/session.
5. Expect **authentication rejected**; internal logs/metrics record a sanitized signature/digest mismatch reason; **no authenticated session**.

Another test branch: flip one byte of **`SignatureValue`** after signing; XML still parses cleanly, yet cryptographic signature verification must fail. Do not only send syntactically broken XML: parser errors do not prove the signature validator works.

### Note on Canonicalization

XMLDSig canonicalizes XML. Certain whitespace/serialization edits might not change canonicalized bytes; conversely, adding namespaces or editing text-node whitespace can alter the digest depending on scope. Therefore, **edit content inside `NameID`/`AttributeValue`/`Conditions` clearly covered by the signed `Reference`** to guarantee a reliable negative case. Verify the fixture factory does not silently re-sign after mutation.

### Do Not Check Signatures by Searching for a Tag

~~~java
// Anti-pattern: only checking whether XML has a Signature tag.
boolean isSigned = xml.contains("<ds:Signature>");
~~~

**This is an anti-pattern—never use in production.** Attackers can insert arbitrary `Signature` tags. Spring/OpenSAML must perform digest/signature/trust validation on the right element. Never parse `SAMLResponse` with custom DOM code and create `Authentication` based on this boolean.

### Expected Result

No successful `Saml2Authentication`, no new authenticated `SecurityContext`, and no access to `/private`. The HTTP response may be 302/400/401 depending on the failure handler and UX. **Do not hard-code asserting HTTP 403 if the app intentionally redirects to `/login?error`.**

## 6. Case B: Wrong Issuer with Valid Signature

**Test goal:** prove the SP **binds a valid signature to the right IdP Identity/registration**, not merely checking cryptographic validity.

Steps to build an independent fixture:

1. Start from the valid baseline Response.
2. Change **Response `Issuer`** from `https://idp.example.test/metadata` to `https://other-idp.example.test/metadata`.
3. If the Assertion also has an `Issuer`, update it per scenario to avoid unintended conflicting issuers.
4. **Re-sign the Response/Assertion after changing `Issuer` using trusted private key A**.
5. Keep `Audience`, `Destination`, `Recipient`, timestamps, request correlation, and test subject valid.
6. Confirm offline cryptographic signature verification on the altered document **still succeeds under A**.
7. Submit through the ACS and verify **Spring/SAML issuer validation rejects** because `Issuer` mismatches `corp-idp`'s asserting party.

**Why re-sign?** If you modify `Issuer` inside signed content without re-signing, you create an **invalid signature**. The test will fail at signature verification before issuer validation is ever exercised.

### Precision About Issuer

- **IdP Issuer** is an EntityID string, not just a hostname or TLS certificate subject.
- Compare per configured IdP entity ID semantics; avoid arbitrarily normalizing URLs by stripping trailing slashes, changing case, or dropping queries unless the framework does so.
- **Response `Issuer` and Assertion `Issuer`** may be validated at different stages; include test variants for both.
- With multiple `RelyingPartyRegistration` entries, selecting the registration via **`registrationId`/prior `AuthnRequest` state** may be needed to test wrong Issuer in context. If a resolver looks up registrations by the XML `Issuer`, a wrong Issuer may trigger **registration not found** before issuer validation—a distinct case. Use an ACS with a specific `registrationId` and matching session/request state to isolate what you measure.
- **Signed-by-trusted-key** with wrong `Issuer` must reject due to IdP identity mismatch. Conversely, matching `Issuer` with an untrusted signature must also reject.

### Negative Variants

| Test | Signature | Issuer | Expected |
| --- | --- | --- | --- |
| Baseline | A valid | valid | Accept if all other policies pass |
| Wrong Response Issuer, re-signed A | A valid | Response wrong | Reject |
| Wrong Assertion Issuer, re-signed A | A valid | Assertion wrong | Reject per SAML policy |
| Issuer differs by one trailing `/`, re-signed A | A valid | differs from configured EntityID | Reject unless exact configured ID matches |
| Empty or missing Issuer | A valid if protocol lets test sign payload | insufficient | Reject |
| Right Issuer, wrong Audience, re-signed A | A valid | valid | Reject for Audience; **do not mislabel as Issuer** |

**Never edit the registration to automatically trust the altered Issuer.** The goal is proving approved IdP configuration cannot be overridden by data inside the Response.

## 7. Case C: Untrusted Signing Key (Untrusted Verification Credential)

**Test goal:** prove the SP trusts only the configured **IdP signing certificate A**, never trusting cert B embedded in the XML.

Procedure:

1. Create a structurally valid SAML Response with **valid `Issuer`**, valid `Audience`/`Recipient`/`Destination`, and valid timestamps.
2. Sign the Response/Assertion with **private key B**, completing `DigestValue` and `SignatureValue` per XMLDSig.
3. Optionally embed **`X509Certificate` B** inside `ds:KeyInfo` specifically to test for self-trust `KeyInfo` vulnerabilities.
4. Keep the SP registration holding **only verification credential A**, without adding B.
5. Offline verification with public key B must succeed; with public key A must fail.
6. Submit Response B to the ACS; expect **unauthenticated**, with no session or access granted.
7. Verify logs record only controlled validation/trust failure without printing `SAMLResponse` or secrets.

**Highest risk:** Code tries verifying with A, fails, and **falls back to whatever public certificate is in `KeyInfo`**. That fallback turns any attacker into a self-signed IdP able to forge any subject.

### Differences Among TLS, IdP Signing, and SP Signing Certificates

| Credential | Location | Purpose |
| --- | --- | --- |
| IdP HTTPS/TLS certificate | HTTP client/browser connecting to IdP | Authenticates TLS hostname/transport |
| **IdP SAML signing X.509 certificate** | Asserting party verification credentials in SP | Verifies IdP XMLDSig |
| SP signing private key/certificate | Relying party signing credentials | Signs `AuthnRequest`/`LogoutRequest` if policy requires |
| SP decryption private key | Relying party decryption credentials | Decrypts `EncryptedAssertion`/attributes |
| Cert B appearing in `KeyInfo` | Untrusted `SAMLResponse` | Self-declared key material only; **not trusted by itself** |

**A valid HTTPS connection to the IdP does not make an XML Signature by cert B trusted.** Likewise, a certificate sharing the IdP's subject name or being unexpired is **insufficient** if outside the approved trust set.

### Key Rotation Scenario

While the IdP rotates signing keys, the SP may **temporarily trust both A and B** if B was verified/registered out-of-band under change control. Tests should cover:

- **Before rollout:** A accepted, B rejected.
- **During approved overlap window:** A and B accepted when issuer/policies are valid.
- **After retiring A:** A rejected, B accepted.
- **Unregistered Key C:** always rejected.
- **New metadata presenting B outside trust policy:** never auto-update trust solely because XML/URL contains B.

Never use an untrusted `SAMLResponse` to "learn" a new signing key. Trust anchors come from IdP onboarding or metadata verified via a trusted process.

## 8. Configuring Spring Security 6.5 for a Trustworthy Baseline

Spring Security uses **`RelyingPartyRegistration`** to bind IdP entity ID, SSO endpoint, SP entity ID, ACS URL, and verification certificates.

Example configuration **assuming the dependencies below and the public test certificate file are prepared**:

**src/main/java/com/example/saml/SamlSecurityConfig.java**

~~~java
package com.example.saml;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    private X509Certificate trustedIdpCert() throws Exception {
        // Public certificate A distributed via trusted IdP
        // onboarding/test CA, not taken from SAMLResponse KeyInfo.
        try (InputStream stream =
                new ClassPathResource(
                    "saml/trusted-idp-signing-A.pem")
                        .getInputStream()) {

            CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
            return (X509Certificate)
                factory.generateCertificate(stream);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingParties()
            throws Exception {

        Saml2X509Credential idpVerifyA =
            Saml2X509Credential.verification(trustedIdpCert());

        RelyingPartyRegistration corp =
            RelyingPartyRegistration
                .withRegistrationId("corp-idp")
                .entityId("https://sp.example.test/metadata")
                .assertionConsumerServiceLocation(
                    "https://sp.example.test/login/saml2/sso/corp-idp")
                .assertingPartyMetadata(party -> party
                    .entityId("https://idp.example.test/metadata")
                    .singleSignOnServiceLocation(
                        "https://idp.example.test/sso")
                    .wantAuthnRequestsSigned(false)
                    .verificationX509Credentials(
                        certs -> certs.add(idpVerifyA)))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Run prerequisites:** Compatible Spring Boot 3/Spring Security 6.5; `saml/trusted-idp-signing-A.pem` provided as the test IdP's public X.509 certificate; issuer, SP entity ID/ACS, IdP SSO, and external browser HTTPS routing matching configured values. This is an **integration sample**, not a claim you can log in to `example.test` or that cert fixtures already exist before creating them.

### Maven Dependencies

In a Maven Spring Boot project with a Spring Security 6.5-compatible BOM:

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
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Version note:** OpenSAML dependencies may require the repository/supported versions from your active Spring Security BOM; verify your dependency tree and version docs. Never mix OpenSAML 2 or legacy SAML Extension libraries with Spring Security 6.5.

### Key Registration Properties

- **`.withRegistrationId("corp-idp")`**: identifier linking SP–IdP in the application.
- Top-level **`.entityId(...)`**: SP EntityID, used as the assertion `Audience` per policy.
- **`.assertionConsumerServiceLocation(...)`**: public ACS URL; browsers POST here.
- **`.assertingPartyMetadata(...).entityId(...)`**: **expected IdP EntityID**; foundation of the `Issuer` check.
- **`.singleSignOnServiceLocation(...)`**: IdP endpoint receiving `AuthnRequest`.
- **`.wantAuthnRequestsSigned(false)`**: example where test IdP does not require SP-signed `AuthnRequest`; **does not weaken `SAMLResponse` verification**.
- **`.verificationX509Credentials(certs -> certs.add(idpVerifyA))`**: trusted certificate for verifying IdP signatures. Include only A in untrusted-key negative tests.

**Do not confuse** `.verificationX509Credentials` with SP `.signingX509Credentials`. One is the **IdP's trusted public key**; the other is the **SP's private signing key** for `AuthnRequest` per contract. Adding B to `verificationX509Credentials` "to make the test stop failing" turns an untrusted-key test into a positive case and defeats the test objective.

## 9. Process for Generating Fixtures with Clear Failure Causes

Fixtures should be produced by a **test IdP or OpenSAML XMLDSig signer** using test-controlled keys. Never randomly edit signed XML and call it a properly scoped test case.

Define fixture files:

~~~text
src/test/resources/saml/fixtures/
  baseline-valid.xml
  signature-tampered.xml
  issuer-wrong-resigned-A.xml
  untrusted-signed-B.xml
  audience-wrong-resigned-A.xml
  response-signed-only.xml
  assertion-signed-only.xml
~~~

**This lists the resource layout to create**, not a claim the files already exist. Running integration tests requires generating real XML from a fixture factory/test IdP with matching IDs, timestamps, ACS, and `RelayState`/`InResponseTo` per run.

### Fixture Factory Algorithm (Pseudocode)

~~~text
Setup:
  trusted key pair A; untrusted key pair B
  SP trusts A only
  issuer = https://idp.example.test/metadata
  audience = https://sp.example.test/metadata
  acs = https://sp.example.test/login/saml2/sso/corp-idp
  now = fixed clock/test clock synchronized with SP

baseline:
  create correct Response/Assertion and unique IDs
  set issuer, audience, destination, recipient, time
  if SP-initiated: correlate InResponseTo with saved AuthnRequest
  sign configured Response and/or Assertion with private key A
  verify signed XML offline; send to ACS; expect authenticated

signature-tampered:
  copy baseline signed XML
  change a text value inside signed Reference after signing
  do NOT sign again
  verify offline signature fails; expect unauthenticated

issuer-wrong-resigned-A:
  copy pre-sign baseline XML
  set wrong Response Issuer, and Assertion Issuer if tested
  sign with private key A AFTER the change
  verify offline signature with A succeeds
  SP still configured expected issuer; expect unauthenticated

untrusted-signed-B:
  copy pre-sign baseline XML with correct issuer/audience
  sign with private key B
  optionally embed certificate B in KeyInfo
  verify offline with B succeeds
  SP still trusts A only; expect unauthenticated

audience-wrong-resigned-A:
  copy pre-sign baseline, set wrong Audience
  sign with A; ensure cryptographic signature passes
  expect unauthenticated because Audience fails
~~~

**Key technique:** When both Response and Assertion are signed, re-sign in the **proper order and scope** so every signature not under test stays valid. For example, editing and re-signing an Assertion changes the enclosed signed Response; in that case, the Response signature must be re-applied last. Before submitting any fixture, verify intended signatures offline so a "wrong Issuer" test never fails early due to an unintentionally broken signature.

### SAMLResponse POST Binding

Normally the application receives **Base64-encoded** XML bytes when the browser POSTs:

~~~http
POST /login/saml2/sso/corp-idp HTTP/1.1
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_OF_TEST_XML
~~~

This illustrates HTTP structure; **`BASE64_OF_TEST_XML` is a placeholder label**, not a valid XML signature fixture. With MockMvc, pass the `SAMLResponse` parameter as shown next; the framework decodes/unmarshals it and invokes the real authentication provider.

**Do not send raw XML directly as `application/xml`** to a standard ACS and wonder why the parser rejects it; that is a binding error, not proof of signature validation.

## 10. MockMvc Integration-Test Skeleton: Actually Going Through the ACS

A trustworthy test must traverse **`Saml2WebSsoAuthenticationFilter`**, never call a mock boolean helper directly, and must use a security config holding **trusted cert A**.

The JUnit 5/MockMvc sample below illustrates test structure using **validly pre-generated fixture files**. It **does not generate SAML fixtures itself**, because XMLDSig, IdP keys, timestamps, Request IDs, and signed elements must be carefully built by a fixture factory/test IdP.

**src/test/java/com/example/saml/SamlNegativeAuthenticationIT.java**

~~~java
package com.example.saml;

import java.io.InputStream;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class SamlNegativeAuthenticationIT {

    @Autowired
    MockMvc mvc;

    private String base64Fixture(String filename) throws Exception {
        try (InputStream in = new ClassPathResource(
                "saml/fixtures/" + filename).getInputStream()) {
            byte[] xml = in.readAllBytes();
            return Base64.getEncoder().encodeToString(xml);
        }
    }

    @Test
    void baselineValidResponseAuthenticates() throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("baseline-valid.xml")))
            .andExpect(authenticated());
    }

    @Test
    void tamperedSignatureNeverAuthenticates() throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("signature-tampered.xml")))
            .andExpect(unauthenticated());
    }

    @Test
    void wrongIssuerWithValidSignatureNeverAuthenticates()
            throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("issuer-wrong-resigned-A.xml")))
            .andExpect(unauthenticated());
    }

    @Test
    void untrustedSigningKeyNeverAuthenticates()
            throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("untrusted-signed-B.xml")))
            .andExpect(unauthenticated());
    }
}
~~~

**Important limitations of the skeleton:**

- **Fixture-dependent**, not a standalone runnable test just by copying; fixture files must exist, be unexpired, and match SP config.
- If the app uses **SP-initiated SSO** and requires `InResponseTo`, you must perform **`GET /saml2/authenticate/corp-idp`** to generate a fresh `AuthnRequest`, capture the request ID, retain the `MockHttpSession`, and generate a matching fixture for that session. Never use stale `InResponseTo` XML and ignore a baseline failure.
- If the app allows unsolicited/IdP-initiated Responses by policy, fixtures must follow that policy; **never relax `InResponseTo` validation in production just to make testing easier**.
- **`SAMLResponse` binding** normally goes through an ACS POST. SAML flow CSRF exemptions are managed by framework config; tests must keep the right filter chain rather than disabling CSRF globally to fix a misrouted endpoint.
- **`authenticated()`/`unauthenticated()`** are Spring Security MockMvc result matchers. Depending on security context persistence and failure handlers, add a follow-up GET to a protected endpoint with the session to prove access is denied.
- Asserting **`unauthenticated()`** alone cannot distinguish the three root causes. Pair it with fixture QA/offline verification and sanitized error diagnostics/metrics; avoid asserting literal exception message strings tied to a specific OpenSAML version.
- Tests run in a test environment with SAML registration and IdP cert A; never place the production IdP private key in the test suite.

### Verifying No Session Access Is Granted After Failure

In the integration harness, run each negative test with a **clean session**. After an ACS failure, reuse the resulting session/cookie to GET a protected resource and confirm there is no authenticated user. Never reuse an already-authenticated baseline session for negative tests; if a session was previously authenticated, a later failure may not always clear prior privileges in every config, muddying test interpretation.

### HTTP Status Alone Is Incomplete Evidence

| HTTP result | May occur when | What else to assert |
| --- | --- | --- |
| 302 to login/error page | failure handler redirects | No new `Authentication` created |
| 401 | API/browser policy demands login | Unauthenticated + no authorization |
| 400 | malformed/invalid SAML message | If testing signatures, prove XML structure is still valid |
| 403 | `AccessDenied`/local policy | Confirm whether rejected at SAML validation or local role |
| 200 | Public error page | Do not infer login succeeded |
| 500 | Runtime parser/certificate/config failure | Never count as a security PASS; fix baseline/fixture/config |

**A test returning 500 still has "no `Authentication`" but indicates an operational bug**, not policy-driven attack rejection. Separate data errors, trust errors, and config errors when debugging.

## 11. Standalone Java 17: Testing Signature, Issuer, and Trust Separately

This program uses **JDK 17 `java.security.Signature`** with RSA-2048/SHA-256, **without Spring, OpenSAML, an IdP, network, or certificate files**. It cleanly demonstrates separation logic:

- Signature/payload altered after signing → fails verification with public key A.
- Wrong issuer **re-signed with A** → cryptography passes, issuer policy fails.
- Valid payload signed with private key B → verification with trusted public key A fails.
- Wrong audience signed with A → audience policy fails.

**This is not an XMLDSig/SAML implementation.** The program signs a test string of three simply canonicalized fields; production must never replace OpenSAML by concatenating issuer/nameId strings or running `SHA256withRSA` over raw XML bytes. XMLDSig involves canonicalization, namespaces, `Reference` URIs, digests/transforms, signed-element selection, and SAML profile validation.

**File: SamlSignatureNegativeCases.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class SamlSignatureNegativeCases {
    record Claims(String issuer, String audience, String subject) {
        byte[] testBytes() {
            return (issuer + "\n" + audience + "\n" + subject)
                .getBytes(StandardCharsets.UTF_8);
        }
    }

    enum Verdict {
        ACCEPTED,
        REJECTED_SIGNATURE_OR_TRUST,
        REJECTED_ISSUER,
        REJECTED_AUDIENCE
    }

    static byte[] sign(Claims claims, PrivateKey key)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(claims.testBytes());
        return signer.sign();
    }

    static Verdict verifyPolicy(Claims claims, byte[] signature,
            PublicKey trustedIdpKey, String expectedIssuer,
            String expectedAudience) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedIdpKey);
        verifier.update(claims.testBytes());
        if (!verifier.verify(signature)) {
            return Verdict.REJECTED_SIGNATURE_OR_TRUST;
        }
        if (!expectedIssuer.equals(claims.issuer())) {
            return Verdict.REJECTED_ISSUER;
        }
        if (!expectedAudience.equals(claims.audience())) {
            return Verdict.REJECTED_AUDIENCE;
        }
        return Verdict.ACCEPTED;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair trusted = generator.generateKeyPair();
        KeyPair outsider = generator.generateKeyPair();

        String issuer = "https://idp.example.test/metadata";
        String audience = "https://sp.example.test/metadata";
        Claims correct = new Claims(issuer, audience, "alice");
        byte[] correctSignature = sign(correct, trusted.getPrivate());

        Claims changedSubject = new Claims(issuer, audience, "admin");
        Claims wrongIssuer = new Claims(
            "https://other-idp.example.test", audience, "alice");
        Claims wrongAudience = new Claims(
            issuer, "https://other-sp.example.test", "alice");

        System.out.println("baseline=" + verifyPolicy(correct,
            correctSignature, trusted.getPublic(), issuer, audience));
        System.out.println("tampered=" + verifyPolicy(changedSubject,
            correctSignature, trusted.getPublic(), issuer, audience));
        System.out.println("wrongIssuer=" + verifyPolicy(wrongIssuer,
            sign(wrongIssuer, trusted.getPrivate()),
            trusted.getPublic(), issuer, audience));
        System.out.println("unknownKey=" + verifyPolicy(correct,
            sign(correct, outsider.getPrivate()),
            trusted.getPublic(), issuer, audience));
        System.out.println("wrongAudience=" + verifyPolicy(wrongAudience,
            sign(wrongAudience, trusted.getPrivate()),
            trusted.getPublic(), issuer, audience));
    }
}
~~~

Compile/run:

~~~bash
javac SamlSignatureNegativeCases.java
java SamlSignatureNegativeCases
~~~

**Exact stdout (verified with a JDK in the execution environment):**

~~~text
baseline=ACCEPTED
tampered=REJECTED_SIGNATURE_OR_TRUST
wrongIssuer=REJECTED_ISSUER
unknownKey=REJECTED_SIGNATURE_OR_TRUST
wrongAudience=REJECTED_AUDIENCE
~~~

### Why Do "Wrong Signature" and "Unknown Key" Share the Same Rejection Code?

From the perspective of a verifier holding only **trusted public key A**, both conditions make **`Signature.verify() == false`**:

- Payload was altered while signature remained A's.
- Payload was unaltered and carries a valid signature by **B**, yet the SP does not trust B.

You cannot distinguish the exact cause from **a single boolean `verify(A)=false`**. The test harness knows the fixture provenance ("tampered" vs. "B-signed"); the production app simply needs to **fail closed** and record appropriate metrics without leaking excessive detail to an attacker.

**If an attacker supplies `KeyInfo` B** and the verifier uses B to verify, the math returns true—yet **trust verification must still reject B**. The standalone code intentionally **uses only `trustedIdpKey` supplied by the SP**, never reading a public key from the payload.

### Additional Safeguards for Real Code

The test string-signing sample **does not check** XML Signature References, XML ID uniqueness, signed nodes, certificate chain policies, `Destination`/`Recipient` bindings, timestamps, or replay. Those live in the SAML authentication provider. Never use this example to authenticate real users, as it lacks mandatory defense layers.

## 12. Testing Untrusted Keys in Metadata and Key Rotation

Do not only test XML Responses containing `KeyInfo` B. **IdP metadata** can also carry a `KeyDescriptor` holding B. If the SP auto-loads metadata, distinguish:

1. **Verified/trusted metadata** established via onboarding or metadata signature trust.
2. **Signing certificates in metadata used to verify `SAMLResponse`s** after metadata trust is approved.
3. **Keys embedded inside `SAMLResponse`**—merely message-supplied data that never expand the trust set.

**Common misconception:** Some **metadata repositories** verify metadata signatures only when **verification credentials** are configured on the repository; otherwise, they may parse metadata without checking the metadata signature. Never assume "fetched over HTTPS" implies the metadata XML contains a policy-approved signing key update.

### Rotation Matrix

| Phase | Key A | Key B | Key C | Expected |
| --- | --- | --- | --- | --- |
| Before rotation | Trusted | Untrusted | Untrusted | Only A-signed Responses accepted |
| Approved overlap | Trusted | Trusted | Untrusted | A/B accepted if Issuer/Audience/Conditions valid |
| After rotation | Untrusted | Trusted | Untrusted | A rejected, B accepted |
| Unverified metadata B | Trusted | Unapproved | Untrusted | Never auto-accept B |
| Key revoked per incident | Revoked | Per policy | Untrusted | Never accept revoked key |

**Bind tests to policy, not matching certificate subject strings.** Certificate B can share the exact same Subject DN as A with a different public key. Even an unexpired certificate is not automatically a trusted IdP credential.

### Generating Fingerprints for Inventory

Administrators use SHA-256 certificate fingerprints/subject/public key metadata to audit trust changes, never logging full private keys or spreading key material. A fingerprint is a **comparison identifier**; it does not prove a certificate is trustworthy if originally obtained from an untrusted source.

## 13. Variants Required in the Test Suite

| # | Test case | Signature/Issuer/Trust | Right outcome |
| --- | --- | --- | --- |
| 1 | Valid baseline Response | A, right Issuer, trust A | **Accept** if all other checks pass |
| 2 | Edit NameID after signing | Signature digest invalid | Reject |
| 3 | Edit `SignatureValue` bytes | Crypto signature invalid | Reject |
| 4 | Edit `DigestValue` | Reference digest/signature inconsistent | Reject |
| 5 | Swap payload while keeping signature | Tampered signed data | Reject |
| 6 | Signed Response with `Reference` URI pointing to non-existent ID | Invalid reference | Reject |
| 7 | Signed Response with duplicate XML IDs | ID ambiguity/Signature Wrapping | Reject |
| 8 | Signed Assertion A + unsigned Assertion B "admin" | Wrong node selection | Never authenticate as B |
| 9 | Wrong Response Issuer, re-signed A | Valid crypto, wrong issuer | Reject Issuer |
| 10 | Wrong Assertion Issuer, re-signed A | Valid crypto, wrong issuer | Reject per policy |
| 11 | Issuer differs by one slash, re-signed A | Different EntityID | Reject unless exact match |
| 12 | Missing required Issuer | Missing IdP identity | Reject |
| 13 | Signed by Key B, right Issuer | Valid under B, B untrusted | Reject |
| 14 | Signed by Key B, includes `KeyInfo` B | Self-consistent untrusted key | Reject |
| 15 | Signed by Key B, no `KeyInfo` | B untrusted | Reject |
| 16 | SP auto-adds `KeyInfo` B as trusted | Broken test harness/policy | Fail code review |
| 17 | Certificate B shares Subject with A | Different public key | Reject until B is trusted |
| 18 | Signing key A revoked | Trust set removes A | Reject |
| 19 | A+B rotation overlap | Both approved | Accept both per policy |
| 20 | Key C during A+B overlap | C untrusted | Reject |
| 21 | Right Issuer, wrong Audience, signed A | Valid crypto, wrong Audience | Reject |
| 22 | Destination differs from ACS, signed A | Valid crypto, wrong Destination | Reject |
| 23 | Wrong Recipient, signed A | Invalid `SubjectConfirmation` | Reject |
| 24 | `NotOnOrAfter` past, signed A | Expired assertion | Reject |
| 25 | `NotBefore` in future, signed A | Not-yet-valid | Reject |
| 26 | `InResponseTo` mismatch, signed A | Request correlation failure | Reject |
| 27 | Replay same Response ID, signed A | Replay | Reject per policy |
| 28 | Unsigned Response and Assertion against policy | No acceptable signature | Reject |
| 29 | Malformed XML / XXE | Parser rejects | Do not classify as invalid signature |
| 30 | SHA-1 or forbidden algorithm | Crypto policy disallows | Reject |
| 31 | Valid Issuer of another tenant IdP | Wrong registration/tenant binding | Reject |
| 32 | Key from same IdP in unverified metadata | Unknown trust anchor | Reject |
| 33 | Multiple registrations sharing a cert | Issuer/registration binding | Accept only matching IdP+SP contract |
| 34 | Valid SAML, local account disabled | SAML valid but app policy fails | Grant no business access |
| 35 | Invalid fixture returns 500 | Runtime/config exception | Must fix; **never** pass QA |
| 36 | SAML failure + old authenticated session | Isolate test sessions | Never infer new result from old session |

**Tests 9, 13, and 21** demonstrate why you must **re-sign after mutation** when testing semantic/trust checks separately from cryptographic integrity. If every fixture is mutated without re-signing, you are only testing the exact same "invalid signature" condition.

## 14. Mistakes That Cause Negative Tests to False-PASS

### 14.1. Baseline Never Authenticated Successfully

If XML lacks `InResponseTo`, is expired, or uses the wrong IdP cert, all three negative tests end up unauthenticated—even if the app accidentally disabled issuer/trust verification. Therefore, assert the baseline authenticates first, and let the same test harness generate fixtures using current timestamps.

### 14.2. Tests Assert Only Status Codes

A 302 redirect or 403 does not prove signature validation. Failure could stem from CSRF, route mismatch, missing `RelyingPartyRegistration`, malformed XML, or an exception unrelated to the target check.

### 14.3. Test Edits Issuer Without Re-Signing

If `Issuer` is inside the signed Response/Assertion, the XMLDSig digest breaks immediately; the test never reaches Issuer logic. Re-sign with A and verify offline with A to prove the signature remains valid.

### 14.4. Test Uses Certificate B While Also Adding B to the SP Trust List

Once B is registered in the SP's `verificationX509Credentials`, B **becomes a trusted credential**, so B-signed Responses can be accepted if everything else passes. That cannot be called an untrusted-key rejection test.

### 14.5. Test Trusts Public Keys Inside SAML KeyInfo

`KeyInfo` sits inside an untrusted XML message. Treating `KeyInfo` as a trust root is equivalent to accepting an attacker's self-signed signature. A public key can help select/locate a credential **within the already-trusted set**, never originate trust.

### 14.6. Test Uses a Production Account with Admin Rights

Never use a production IdP signing private key or real user info to build negative fixtures. Use a test IdP, keys absent from production, synthetic subjects/tenants, and an isolated test environment.

### 14.7. Test Fails to Verify the Exact Signed Element

XML with a valid `SignedInfo` over element A while code reads the subject from B is an **XML Signature Wrapping** bug. The validator must check Reference URI/ID, and the application must use the exact validated object—never `getElementsByTagName("Assertion")` taking the first node.

### 14.8. Test Checks Key/Issuer While Ignoring Audience/Recipient

One IdP may use the same certificate to sign for multiple SPs. Even with valid Issuer and key, an Assertion issued for another SP **must not be accepted**. Check `AudienceRestriction`, `Recipient`, and `Destination` to prevent cross-service assertion replay.

## 15. Observing via Logging and Metrics Without Exposing Assertions

**Observe:**

- Security filter selected the right ACS/`registrationId`.
- Response parsed/unmarshalled cleanly vs. malformed.
- Cryptographic signature failure, trusted signing credential mismatch, issuer mismatch, audience/recipient/time failure, replay, or request correlation failure.
- IdP/tenant registration ID and certificate fingerprint **verified from trusted sources**, not untrusted `KeyInfo`.
- Test request correlation ID; session authentication success/failure; protected resource access decision.
- Error counts by category, provider version/config, and metadata key rotation window.

**Do not log:**

- Raw `SAMLResponse`/Base64, Assertion XML, sensitive NameIDs/attributes.
- IdP/SP private keys, keystore passwords, session cookies, `RelayState` carrying secrets.
- Full attacker-supplied malformed XML dumps.
- A "verified issuer" extracted from XML before the validator accepts `Issuer`.

**Client error:** return a generic message like **"SAML authentication failed"**. Specifics such as "unknown signing key" or "wrong issuer" belong in sanitized structured server logs aligned with privacy/abuse policies—never giving attackers configuration-probing hints.

### When to Investigate Instead of Retrying?

Never retry the same assertion/Response when validation fails. In SAML, replay protection, `InResponseTo`, and `NotOnOrAfter` have strict time bounds; replaying an old callback can trigger replay rejections. First check fixture freshness, clocks, trust certs, `Issuer`, `Audience`, proxy Host/Proto, and request/session correlation.

## 16. QA Rules for a Complete Test Run

A suite should express two kinds of assertions:

**A. No bypass:**

- No new authenticated `SecurityContext`.
- No new `Saml2Authentication`.
- No privileged session established.
- No local account auto-created or role added outside policy.
- Protected endpoints remain inaccessible with negative Responses alone.
- Gateway/ACS never redirects to an attacker-controlled destination.
- Error responses disclose no sensitive information.

**B. Prove the exact validation branch:**

- Equivalent baseline succeeds.
- **Tampered signature**: structurally valid XML, right Issuer, trusted A, yet crypto verification fails.
- **Wrong Issuer**: offline signature under A succeeds; issuer policy is what rejects.
- **Untrusted key**: offline signature under B succeeds; SP trust list holds only A; key B is not trusted via `KeyInfo`.
- No accidental side errors such as expired assertion, wrong Audience, missing `InResponseTo`, or invalid ACS.
- Exact assertion check over Response or Assertion per IdP contract.
- Fixture generation uses unique IDs and valid timestamps so repeated runs do not go stale or replay-fail.

**When changing libraries:** Spring Security/OpenSAML/IdPs may alter exception codes and validator order. Avoid asserting overly brittle error message strings that break on version bumps; rely on hard safety outcomes/invariants and application-controlled structured diagnostic categories.

## 17. CI/Staging Operational Workflow

1. **Generate test IdP keys** A and B in an isolated environment. Keep private keys in the fixture signer/test secrets; give the SP **certificate A only**.
2. Lock down IdP entity ID, SP entity ID, ACS URL, `registrationId`, signed element type, and `InResponseTo`/clock policies.
3. Build a fresh **positive control fixture**, verify offline, send through the ACS, and assert authenticated + protected GET.
4. Build the negative signature fixture by mutating **after signing**, keeping all other fields valid.
5. Build the wrong Issuer fixture by changing Issuer **before re-signing with A**, verifying offline validity.
6. Build the untrusted-key fixture with B, keeping Issuer valid, varying `KeyInfo` B present/absent, while the SP trusts only A.
7. Submit each fixture through the ACS with a **fresh matching session/request** and assert unauthenticated.
8. Expand the matrix to cover Audience/Recipient/`NotBefore`/`NotOnOrAfter`/`InResponseTo`/replay/wrapping.
9. Collect sanitized metrics without saving raw Assertions or private keys in CI reports.
10. Generate reports separating test-setup/fixture errors from actual security regressions.
11. Before key rotation, use CI to verify the approved trust window (A→A+B→B) and that unknown C is always rejected.
12. Re-run the suite after changes to metadata, OpenSAML, Spring Security, SAML signing algorithms, reverse proxies, IdP issuer/ACS, or truststores.

### Example Expected QA Outcomes

~~~text
baseline valid, signed by A:       ACCEPT
tampered signature, Issuer valid:  REJECT
wrong Issuer, re-signed by A:      REJECT
correct Issuer, signed by B:       REJECT
wrong Audience, re-signed by A:    REJECT
unknown signing key C:             REJECT
session after invalid Response:    NO NEW AUTHENTICATION
protected resource after failure:  NOT AUTHORIZED
~~~

These are **expected assertions**, not output from a live SAML server run. The Java 17 program in section 11 has its own deterministic stdout; integration results depend on your fixture generator, test IdP, and actual Spring Security config.

## 18. Production Checklist

- [ ] Spring Security uses **`Saml2WebSsoAuthenticationFilter`/OpenSAML provider** for the ACS, never creating `Authentication` from raw Base64/XML.
- [ ] Each **`RelyingPartyRegistration`** defines explicit expected IdP EntityID and SP EntityID.
- [ ] **`verificationX509Credentials`** contains only IdP certificates onboarded/trusted per policy.
- [ ] **`KeyInfo` inside Responses never elevates a certificate to a trusted signing credential**.
- [ ] Signed Response and/or Assertion scope, `Reference` URI scope, and XMLDSig transforms match profile.
- [ ] **Invalid signature** test uses a structurally valid fixture with corrupted signature/digest.
- [ ] **Wrong Issuer** test is re-signed with trusted A to isolate the Issuer check.
- [ ] **Untrusted key B** test carries a valid XMLDSig under B while the SP trusts only A.
- [ ] Positive baseline authenticates **before** evaluating negative cases.
- [ ] Verified `SAMLResponse` binding, ACS URL, `registrationId`, timestamps, and Audience/Recipient/Destination/`InResponseTo`/`SubjectConfirmation`.
- [ ] XML parser hardened against XXE and XML signature wrapping/duplicate IDs.
- [ ] Only the provider-validated signed Assertion is consumed; unsigned siblings are ignored.
- [ ] Local disabled user/tenant/resource authorization continues blocking even after valid SAML.
- [ ] Tests use clean sessions and fresh Response/Assertion IDs without reusing stale fixtures.
- [ ] Negative tests never count as PASS merely because of HTTP 500 or misconfigured baselines.
- [ ] Certificate rotation A→A+B→B follows approvals, lifetimes, and revocation.
- [ ] Metadata key updates are never trusted without provenance/signature policy checks.
- [ ] Test results/metrics are redacted and never print raw `SAMLResponse`, NameIDs, or private signing keys.
- [ ] Test suite re-runs after upgrading Spring Security/OpenSAML/IdP keys or proxy/callback configs.

**Conclusion:** Testing **invalid signatures, wrong Issuers, and untrusted keys** verifies three distinct boundaries: **content integrity**, **IdP identity**, and **signing key trust source**. Good tests keep the other two boundaries valid while deliberately breaking one, confirm the baseline succeeds, and verify **no new `Authentication` or access is granted**. In Spring Security, rely on `RelyingPartyRegistration`/OpenSAML for trust management; never build a verifier that trusts public keys from `KeyInfo` or parses unsigned Assertions.

## 19. Official References

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): `Saml2WebSsoAuthenticationFilter`, `RelyingPartyRegistration`, SAML authentication pipeline.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): OpenSAML 4/5 providers, Response/Assertion validators, Issuer/Destination.
- [Spring Security – RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): registration, `entityId`, asserting party metadata.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): metadata trust and verification credentials.
- [Spring Security – MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()` and `unauthenticated()`.
- [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML signatures, issuer/audience, trusted keys, wrapping, replay, and X.509 policies.
- [Oracle JDK 17 – java.security.Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `SHA256withRSA`, `initSign`/`initVerify`, and signature verification.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): `SignedInfo`, `Reference`, digest, `SignatureValue`, and `KeyInfo`.
- [OASIS SAML V2.0 Specifications](https://docs.oasis-open.org/security/saml/v2.0/): SAML Core, Bindings, Profiles, and Metadata.
