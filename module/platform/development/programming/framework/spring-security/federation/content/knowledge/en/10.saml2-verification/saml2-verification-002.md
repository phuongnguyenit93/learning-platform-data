# Verifying Signatures with the Correct Identity Provider's Key in SAML 2.0

In SAML 2.0 federation, the **Service Provider (SP/Relying Party)** does not merely need to know whether a SAML Response signature matches **some public key**. It must prove that the public key used for verification **belongs to the exact Identity Provider (IdP/Asserting Party) configured and expected for this login attempt**. After that, the application must still verify Issuer, Audience, Recipient, validity period, InResponseTo, and access permissions.

**Core rule:** Never try every key belonging to every registered IdP and accept the first signature that passes. You must bind the right set of trusted keys to a **RelyingPartyRegistration**, verify the SAML message under that registration, and reject when the issuer, recipient, or tenant context mismatches.

This lesson focuses on the Web Browser SSO flow with **Spring Security SAML2 Login**. The Java 17 example demonstrates signature verification with the right public key; real SAML implementations use Spring Security/OpenSAML rather than building a custom XML Signature parser.

## 1. Why Is a Valid Signature Not Enough to Prove the Right IdP?

Suppose a Portal supports two IdPs:

| Association | Registration ID | IdP entity ID | Allowed public key |
| --- | --- | --- | --- |
| Internal employees | company-a | https://login-a.example.test/saml | Key-A |
| Partner customers | company-b | https://login-b.example.test/saml | Key-B |

A user from IdP B does not automatically have permission to log into an area reserved for employees of A. If the code tests Key-A and then Key-B for the same Response and grants login when **any** key succeeds, the system can suffer **cross-IdP token substitution** or tenant confusion. An attacker does not necessarily have to break cryptography; they only need to exploit a bug binding the IdP/key identity to the usage context.

A SAML login is accepted when these verification layers succeed together:

1. **Registration selection:** the SP determines which SP–IdP pair is allowed to process the current request.
2. **Cryptographic verification:** the signature protects the right Response/Assertion, verified using a trusted key **of the IdP within that registration**.
3. **Identity binding:** the message's Issuer matches the configured IdP entity ID.
4. **Relying-party binding:** the Response/Assertion is intended for the right SP entity ID, ACS, Audience, and Recipient.
5. **Time & request binding:** still valid, not replayed, and matches AuthnRequest when correlation is required.
6. **Application authorization:** the authenticated user has permissions on the specific tenant/resource.

**A signature valid under B's key on a Response claiming Issuer A must be rejected**, even though B belongs to another registration that the SP also supports.

## 2. IdP Key Trust Model in Spring Security

~~~text
                   Administrator / federation operator
                                |
                  Verify IdP metadata / cert
                                |
                 RelyingPartyRegistrationRepository
                                |
              +-----------------+------------------+
              |                                    |
          company-a                             company-b
      expected issuer A                    expected issuer B
      verify credentials A                  verify credentials B
      SP entity ID and ACS A                SP entity ID and ACS B
              |                                    |
              +------------------+-----------------+
                                 |
                        Browser POST SAMLResponse
                                 |
                   Select matching registration
                   based on trust context
                                 |
                Verify signature with that IdP's key
                                 |
                Check Issuer, Audience, Recipient...
                                 |
                         PASS -> Authentication
                         FAIL -> Reject
~~~

Concepts to distinguish:

- **registrationId** is an internal name, such as company-a; not necessarily equal to the SAML entity ID.
- **IdP entity ID** is the protocol identifier the SP expects in the Issuer of the response/assertion.
- **verificationX509Credentials** on the asserting party side hold the certificates allowed to verify IdP messages.
- **SP signing credentials** hold the private key used to sign AuthnRequest if the IdP requires it; **not the key for the SP to verify IdP signatures**.
- **SP decryption credentials** hold the private key to decrypt EncryptedAssertion when needed; also **not the key to verify IdP signatures**.

The repository holds trust configuration; it does not directly authenticate users. Spring Security/OpenSAML uses the resolved registration to process the SAMLResponse.

## 3. What Does XML Signature Actually Check?

SAML 2.0 typically relies on **XML Signature (XMLDSig)**. A signature consists of SignedInfo, References, DigestValue, SignatureValue, and optionally KeyInfo.

| Component | Role |
| --- | --- |
| SignedInfo | Structure of signed information, canonicalization and signature algorithms |
| Reference URI | Specifies the protected XML object; usually references the ID of Response or Assertion |
| Transforms, Canonicalization | Normalizes XML and transforms data before hashing/signing |
| DigestValue | Hash of the actual data pointed to by Reference |
| SignatureValue | Digital signature computed over canonicalized SignedInfo |
| KeyInfo | May carry a certificate or key hint; **not automatically trusted** |

An illustrative structural fragment (not a valid SAMLResponse):

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response-a"
    Destination="https://portal.example.test/login/saml2/sso/company-a">
  <saml:Issuer>https://login-a.example.test/saml</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_response-a">
        <!-- algorithms and digest omitted -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue omitted -->
  </ds:Signature>
  <saml:Assertion ID="_assertion-a">
    <saml:Issuer>https://login-a.example.test/saml</saml:Issuer>
    <!-- Subject, Conditions, AuthnStatement omitted -->
  </saml:Assertion>
</samlp:Response>
~~~

**Do not submit the XML fragment above to log in:** it lacks required fields, digest, signature, and assertion content. The example only shows Reference and element placement.

Two independent mandatory checks:

- **Cryptographic:** SignatureValue, Reference/digest, and transforms must be valid for the exact XML object.
- **Trust:** the public key used must be in the approved verification credentials **of the IdP that the SP expects**.

A cryptographic verify = true result with an untrusted key **does not** allow creating a principal. Finding a certificate inside the XML does not turn that certificate into an IdP trusted key.

## 4. Distinguishing Signatures and Key Usage Directions

| Signature type | Typical signer | Who verifies? | Trusted key used for verification |
| --- | --- | --- | --- |
| SAML Response signature | IdP | SP | Public signing certificate of the **right IdP** |
| SAML Assertion signature | IdP | SP | Public signing certificate of the **right IdP** |
| IdP metadata signature | IdP/federation operator | SP | Pre-configured metadata trust anchor |
| AuthnRequest signature | SP | IdP | Public signing certificate of the SP |
| SP metadata signature | SP/federation operator | IdP | Trust anchor on the metadata consumer side |

The **TLS certificate** of the IdP website generally protects the HTTPS connection; it may differ from the SAML signing certificate. Successful HTTPS verification does not automatically verify the SAML Response XML signature.

**EncryptedAssertion** needs the SP private key to decrypt, and then still requires verifying the signed content and related conditions. Encryption does not replace digital signatures or authorization.

### Signed Response, Signed Assertion, or Both?

According to Spring Security's OpenSAML flow description, the provider verifies the Response signature when present, Assertion signatures when present, and rejects when no appropriate signature exists. A setup can rely on Response-signed or signed assertions depending on profile; **there is no rule that every IdP must always sign both layers**.

However, an organization's policy may be stricter:

- Require the Response to be signed.
- Require every used Assertion to be signed.
- Require both in sensitive deployments.
- Reject any presented signature that is invalid.

When multiple Assertions exist, the application must not take login data from an unprotected/unverified Assertion. **The library must use the exact object within the signature's scope**, avoiding reading the wrong element.

## 5. Where Are Keys Obtained to Be Considered Trusted?

Common approaches:

1. **IdP metadata XML** loaded from an approved source and vetted per federation policy.
2. **Pinned certificates** verified by an administrator via an independent channel and placed in application configuration.
3. **Internal configuration store** maintaining allowed certificates per IdP entity ID with auditing/rotation.

A portion of metadata may contain the structure:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>
          <!-- IdP Base64 certificate omitted -->
        </ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
</md:IDPSSODescriptor>
~~~

This is a **structural fragment**, not complete metadata: it lacks EntityDescriptor/entityID, SSO endpoint, and real certificate.

**The source of trust lies in the metadata verification process**, not in the XML itself containing a public key. If an attacker can replace metadata and the SP automatically trusts every new certificate, the attacker can swap the trust root and self-sign a SAMLResponse.

- If using metadata over HTTPS, verify the URL/host and TLS from an approved source.
- If the federation requires signed metadata XML, verify using a **separate pre-established metadata-signing trust anchor**, rather than trusting a key embedded in the metadata itself.
- If the application retrieves metadata from a database, govern update permissions, integrity, auditing, and expiration/rotation.
- In the SAMLResponse itself, **ds:KeyInfo is only sender-supplied data**; it can serve as a hint to pick a key from the trusted list, **never as an automatic trust anchor**.

Many SAML certificates are trusted via pinning/federation metadata rather than necessarily chaining to a public WebPKI CA. Certificate evaluation must follow the **specific trust policy**, not merely checking whether it is self-signed.

## 6. Selecting the Right Registration Before Verification

In SP-initiated login, a safe sequence typically looks like this:

~~~text
1. Browser hits /saml2/authenticate/company-a
2. SP retrieves registration company-a
3. SP creates AuthnRequest, stores request ID + registration context
4. Browser goes to IdP A, user authenticates
5. IdP A returns SAMLResponse to ACS
6. SP resolves registration by trusted request/state
7. Verify signature with IdP A's verification credentials
8. Confirm issuer A, audience SP A, recipient ACS, timestamps
9. Verify InResponseTo, subject confirmation, replay
10. Only upon success create Authentication and evaluate business permissions
~~~

**Do not use Issuer from unverified data to automatically download new keys from the Internet.** In some flows, Spring Security may read Issuer to **look up a candidate registration in the configured set**, but signature validation must prove the key truly belongs to that candidate's IdP; reading Issuer alone creates no trust.

**IdP-initiated SSO:** may have no AuthnRequest/InResponseTo correlation. If permitted, an explicit policy is needed for registration selection, issuer, audience, recipient, replay, and login CSRF protection. Do not simply strip out all request-binding checks just to "make login work".

**Same IdP issuer across two registrations:** if multiple SP entity IDs or tenants share the same IdP, reading Issuer alone is insufficient to uniquely pick a registration; trusted request context, audience/recipient, and tenant mapping are needed.

## 7. Spring Boot Configuration: Binding a Separate Certificate per IdP

Example **Spring Boot 3.x / Spring Security 6.x** in application.yml:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company-a:
            assertingparty:
              entity-id: "https://login-a.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/company-a.crt"
              singlesignon:
                url: "https://login-a.example.test/sso"
                sign-request: false
          company-b:
            assertingparty:
              entity-id: "https://login-b.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/company-b.crt"
              singlesignon:
                url: "https://login-b.example.test/sso"
                sign-request: false
~~~

**Meaning:**

- **company-a** and **company-b** are registration IDs of the two SP–IdP pairs.
- **assertingparty.entity-id** defines the expected IdP issuer.
- **verification.credentials.certificate-location** points to the corresponding IdP public certificate; this is the key source the SP uses to verify assertion/response signatures.
- **singlesignon.url** is the IdP endpoint where AuthnRequest is sent.
- **sign-request: false** only means this sample assumes the IdP **does not require the SP to sign AuthnRequest**; it **does not disable verifying the IdP's signature when returning SAMLResponse**.

Working prerequisites: requires Spring Web/Security/SAML service provider dependencies, real X.509 certificates at the resources paths, SP Entity ID/ACS registered at the IdP, and an IdP supporting the declared configuration. Domains under example.test are illustrative only; real login is impossible without replacing them and setting up the IdP. For other Spring Boot versions, check the property namespace in that version's documentation.

If the IdP provides vetted metadata, you can configure **assertingparty.metadata-uri** instead of declaring each issuer, SSO endpoint, and certificate, but **the metadata must belong to the right IdP and come from a trusted source**.

### Comparing Valid and Invalid Cases

| Scenario | Expected Registration | Conclusion |
| --- | --- | --- |
| Issuer A, signed by A, valid Audience/Recipient, not expired | company-a | Can log in after all other checks |
| Issuer A, signed by B | company-a | **Reject** even though B is also a configured IdP |
| Issuer B, signed by B, but Response intended for SP A | company-b | **Reject** because audience/recipient is invalid |
| Issuer A, signed by A, but response expired | company-a | **Reject** because signature does not replace time checks |
| Issuer A, signed by A, but lacks tenant permission | company-a | Identity can authenticate, but **do not grant tenant permission** |

## 8. Java Configuration: RelyingPartyRegistration and verificationX509Credentials

Another approach is creating the repository bean in Java. The example below is for a **Spring Boot 3.x, Spring Security 6.x, Java 17+ application**, using real certificates in resources:

File **src/main/java/com/example/security/SamlTrustConfig.java**:

~~~java
package com.example.security;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTrustConfig {

    private static X509Certificate readCert(Resource resource)
            throws Exception {
        try (InputStream in = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("classpath:saml/company-a.crt") Resource certA,
            @Value("classpath:saml/company-b.crt") Resource certB)
            throws Exception {

        Saml2X509Credential verifyA =
                Saml2X509Credential.verification(readCert(certA));
        Saml2X509Credential verifyB =
                Saml2X509Credential.verification(readCert(certB));

        RelyingPartyRegistration a = RelyingPartyRegistration
            .withRegistrationId("company-a")
            .assertingPartyMetadata(party -> party
                .entityId("https://login-a.example.test/saml")
                .singleSignOnServiceLocation(
                    "https://login-a.example.test/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(c -> c.add(verifyA)))
            .build();

        RelyingPartyRegistration b = RelyingPartyRegistration
            .withRegistrationId("company-b")
            .assertingPartyMetadata(party -> party
                .entityId("https://login-b.example.test/saml")
                .singleSignOnServiceLocation(
                    "https://login-b.example.test/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(c -> c.add(verifyB)))
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(a, b);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This sample is **not standalone Java** runnable via javac/java because it requires Spring Boot, the Spring Security SAML module, real certificates, and a running IdP. It has no fixed stdout. When deploying, you must configure the SP Entity ID, ACS, AuthnRequest signing key, or assertion decryption key if the IdP requires them.

Key takeaways explained:

1. **CertificateFactory** only parses the X.509 file; it **does not prove** the file came from the right IdP. Controlling the certificate source is a configuration and operational responsibility.
2. **Saml2X509Credential.verification** marks the certificate as a verifying credential, not a private key for signing requests.
3. **company-a** only receives **verifyA** in A's asserting-party metadata; similarly company-b only receives **verifyB**.
4. **InMemoryRelyingPartyRegistrationRepository** stores registrations in memory; it **does not automatically reload** certificates when the IdP rotates keys.
5. **saml2Login** lets Spring Security/OpenSAML components decode and verify SAML per the protocol; do not build a simple custom XMLSignatureValidator to replace it.

**This is an alternative to Boot properties configuration**; do not declare both and assume Spring will automatically merge all registrations.

## 9. Metadata Signature and Response Signature Are Two Trust Boundaries

An attacker does not need to defeat RSA if they can trick the SP into trusting a **forged metadata XML** containing a public key controlled by the attacker. The attacker then self-signs the SAMLResponse with the corresponding private key, and signature verification will pass with the forged key if the SP accepted it as a trusted key.

Proper trust workflow:

~~~text
IdP metadata source approved by administrator
                    |
       Verify transport/source/signature
       per federation policy
                    |
        Metadata matches entityID and is still valid
                    |
          Extract signing KeyDescriptor
                    |
         RelyingPartyRegistration
                    |
      Verification credentials of the right IdP
                    |
       Verify SAML Response / Assertion
~~~

- **Metadata verification:** answers "are these keys and endpoints genuinely authorized to represent that IdP?".
- **Response/Assertion verification:** answers "was the current SAML message signed with a currently authorized key of the IdP, and was it issued for the right SP?".
- **TLS verification:** answers "does the HTTPS channel to the metadata/IdP endpoint match the verified certificate and hostname?".

These three questions do not replace one another.

Spring Security supports managing asserting-party metadata; some versions provide **OpenSaml5AssertingPartyMetadataRepository** with verificationCredentials to verify XML metadata signatures. **If verification credentials are not configured per that API, do not assume the XML metadata signature is checked.** When metadata is trusted via an internal/trusted HTTPS channel per policy, explicitly document the trust model. Never take a public key from a response's KeyInfo or a user-supplied URL to establish trust.

## 10. XML Signature Wrapping: Valid Signature but Wrong Principal

**XML Signature Wrapping (XSW)** exploits a situation where an application verifies the signature of XML object A yet reads login attributes from an unsigned XML object B.

Example illustrating the principle, **not an executable payload**:

~~~text
SAMLResponse
  Assertion A: subject = employee, valid signature
  Assertion B: subject = admin, unsigned
  Signature Reference: points to Assertion A

Faulty implementation:
  verify(A) = true
  -> XPath extracts element B
  -> creates principal admin
~~~

Preventive measures:

- Use up-to-date Spring Security/OpenSAML instead of writing a custom signature parser.
- Identify the exact XML object protected by Signature Reference, enforce ID uniqueness, and reject anomalous references.
- Only use subject/attributes from **assertions properly verified in context by the library**.
- Block DTDs, external entity expansion, XML parser attacks, and disallowed transforms per policy.
- With multiple assertions, ensure all used data resides inside the scope protected by a valid signature.
- Never just grab the first Assertion element with XPath and assume it is verified because a valid SignatureValue exists somewhere in the document.

**A valid signature with the right key is still insufficient** if the code consumes content outside the verified signature scope.

## 11. Key Rollover: Multiple Keys Allowed, but Only for the Same IdP

An IdP may publish its current signing certificate and next certificate during a key rotation window.

| Phase | Allowed keys for IdP A | Condition |
| --- | --- | --- |
| Before rotation | A-old | Old key is active |
| Transition period | A-old and A-new | Both keys verified per metadata/trust policy |
| After rotation | A-new | Old key removed from trust config |

**Never use Key-B of IdP B to fix a signature error from IdP A.** Even when one SP manages two IdPs, key sets must stay scoped to each asserting party.

Safe procedure:

1. The IdP/federation operator announces the key change over an administrator-approved channel.
2. The SP fetches the new metadata/cert from a trusted source, verifying entityID, certificate, KeyDescriptor, and metadata trust policy.
3. Add the new key to the right registration A, deploy consistently across instances, and test.
4. Once the IdP begins signing with A-new, verify Response/Assertion with the new key while still validating audience/issuer/timestamps.
5. At the agreed cutover time, remove A-old after confirming the IdP no longer uses it.
6. Audit log and alert on unexpected fingerprint changes; never auto-trust KeyInfo in SAMLResponse.

Metadata **validUntil** and X.509 certificate expiration dates are distinct timestamps; do not treat one as a substitute for the other. When metadata expires per standard, refresh trust material; when a certificate is revoked from trust policy, do not retain it indefinitely even if the app still has active sessions.

## 12. Standalone Java 17: Right Key Verifies, Wrong Key Does Not

This example uses **JDK 17+** to demonstrate RSA/SHA-256 signatures over byte arrays. It **is not a SAML XML Signature verifier**: XML canonicalization, Signature Reference, metadata/trust, and assertion validation must be performed by Spring Security/OpenSAML.

Create **CorrectIdpKeyDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class CorrectIdpKeyDemo {
    static byte[] sign(byte[] data, KeyPair pair)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(pair.getPrivate());
        s.update(data);
        return s.sign();
    }

    static boolean verify(byte[] data, byte[] signature,
                          PublicKey trusted)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initVerify(trusted);
        s.update(data);
        return s.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair idpA = generator.generateKeyPair();
        KeyPair idpB = generator.generateKeyPair();

        byte[] data = "issuer=A;subject=user123"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(data, idpA);
        byte[] modified = "issuer=A;subject=admin"
                .getBytes(StandardCharsets.UTF_8);

        System.out.println("Correct IdP key: "
                + verify(data, signature, idpA.getPublic()));
        System.out.println("Wrong IdP key: "
                + verify(data, signature, idpB.getPublic()));
        System.out.println("Modified data: "
                + verify(modified, signature, idpA.getPublic()));
    }
}
~~~

Compile and run:

~~~bash
javac CorrectIdpKeyDemo.java
java CorrectIdpKeyDemo
~~~

**Exact stdout**:

~~~text
Correct IdP key: true
Wrong IdP key: false
Modified data: false
~~~

**Explanation:**

- A signature created by IdP A can be verified with public key A.
- Public key B cannot verify the same signature.
- When the signed data is modified to subject admin, verification fails even with the right key A.
- Key pairs in the example are randomly generated at runtime and kept only in memory; the three boolean outcomes remain deterministic.
- In production SAML you must also prove **public key A belongs to the right IdP A** via trusted metadata/registration, then check issuer, audience, recipient, and other conditions. Never use this verify method to validate a raw SAMLResponse.

## 13. At Which Step Does Spring Security Verify?

Typical Servlet SAML2 Login flow:

1. **Saml2WebSsoAuthenticationFilter** receives SAMLResponse at the ACS.
2. **Saml2AuthenticationTokenConverter** extracts the message and resolves the matching **RelyingPartyRegistration**.
3. The **OpenSAML**-based authentication provider verifies the signature, processes encrypted elements if present, checks issuer/destination, and validates assertions/subject conditions per profile.
4. Upon success, Spring creates **Saml2Authentication** and **Saml2AuthenticatedPrincipal**.
5. **AuthorizationFilter**, method security, and business logic determine actual permissions.

Spring Security 7.x documentation refers to **OpenSaml5AuthenticationProvider**; 6.x releases may use a different provider depending on version and dependency. Therefore, check the docs and Javadoc for your running version before customizing the authentication provider.

A basic SecurityFilterChain, **without interfering with the signature verifier**:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .build();
}
~~~

This is a **configuration snippet inside a Spring class**; it will not compile standalone with javac without a project/dependencies, and has no fixed stdout.

When changes are needed:

- **Certificate trust:** update verificationX509Credentials for the right IdP.
- **Registration selection:** configure the SAML token converter / registration resolver for your version, preserving session/request and tenant bindings.
- **Additional assertion validation:** use version-appropriate Spring Security/OpenSAML extension points and **do not disable default verification steps**.
- **Metadata refresh:** use a trusted certificate/metadata governance mechanism to update the repository. An InMemory repository does not poll keys automatically.

## 14. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Message Issuer A but signature only matches B | Wrong trust binding or spoofing | Reject; do not try keys from all IdPs |
| Sudden invalid signature after certificate rotation | SP still holds old cert | Verify new cert from IdP, update the right registration |
| One instance logs in, another fails | Key sets out of sync | Check metadata/certs rollout across all instances |
| Metadata contains new cert from untrusted source | Trust substitution attack or weak config | Do not admit cert into trust until provenance is verified |
| Valid response signature but wrong Audience | Message intended for another SP | Reject; compare SP entityID and IdP registration |
| Valid signature but past NotOnOrAfter | Expired assertion | Reject; check bounded clock skew |
| InResponseTo mismatch | Lost request session / correlation or login injection | Inspect request repository, browser session, and ACS |
| SAMLResponse lacks valid signature | IdP not signing or policy mismatch | Fix IdP/SP signing configuration; do not disable signature validation |
| XML has signed assertion and another unsigned assertion | XML Signature Wrapping or multi-assertion mishandling | Do not read unprotected assertion; check library |
| Self-signed IdP certificate | Insufficient info to conclude | Check whether cert is approved by trust policy |
| SAML authentication succeeds but receives HTTP 403 | Insufficient role/tenant/resource permission | Handle authorization separately; do not alter signature policy |

**Safe logging:** registrationId, expected IdP entityID, SHA-256 fingerprint of trusted certificate, timestamp, correlation ID, and sanitized error. Do not log private keys, raw assertions containing personal data, raw SAMLResponse, or session cookies in production.

## 15. Security Testing Matrix

| Case | Input | Expected |
| --- | --- | --- |
| A | Issuer A, signed A, right audience/recipient/time | Signature passes, then remaining conditions pass |
| B | Issuer A but signed B | **Reject** |
| C | Issuer A and signed A, but Audience of another SP | **Reject** |
| D | Issuer A and signed A, but expired | **Reject** |
| E | Arbitrary certificate from KeyInfo, not in trusted registration | **Reject** |
| F | Metadata containing new certificate from forged source | **Reject metadata**, do not alter trust |
| G | IdP A rolling over approved A-old/A-new | Both keys work properly during transition |
| H | Response modified after signing | **Reject** due to signature/digest mismatch |
| I | XML Signature Wrapping causing principal from unsigned assertion | **Reject/do not use unsigned object** |
| J | Two registrations with same issuer, different tenant/ACS | Do not pick arbitrarily; check request context and audience |
| K | IdP-initiated without InResponseTo | Accept only if explicit policy permits and other checks are complete |
| L | Valid SAML login but user lacks tenant permission | **Reject at authorization** |

Tests should run on a staging environment with a **real IdP or test IdP**, where certificates, metadata, SP Entity ID, ACS, bindings, and signing policies are explicitly configured. You can write unit tests for registration/cert mapping, but **a test mocking a verify method = true cannot replace SAML integration testing**.

## 16. Self-Assessment Questions

**1. Can you take the public key from Response's ds:KeyInfo and trust it immediately?**  
No. KeyInfo is sender-supplied content; it must be matched against approved keys of the right asserting party.

**2. IdP B is also configured in the Portal. Can key B verify a Response claiming Issuer A?**  
No. Keys must belong to the exact chosen registration/IdP.

**3. Is a valid Response signature enough to skip AudienceRestriction?**  
No. A message can be validly signed yet issued for a different SP.

**4. Must the TLS certificate of the IdP URL be the SAML signing certificate?**  
No. They serve different purposes.

**5. Why might multiple keys be needed for the same IdP?**  
To perform controlled key rollover; only trust approved keys during the transition window.

**6. Why does a metadata signature differ from a message signature?**  
Metadata lets the SP determine **the allowed keys/endpoints**, while the message signature verifies **the current SAML Response/Assertion**.

**7. What if there is a valid signature on Assertion A but code reads an unsigned Assertion B?**  
Must not be accepted; that is a signed-object binding/XML Signature Wrapping issue.

**8. Does logging in via IdP A automatically grant admin privileges in tenant A?**  
No. Authentication and authorization are two separate verification layers.

## 17. Production Deployment Checklist

- [ ] Each registration has the right expected IdP entityID, SP entityID, ACS, and verification credentials.
- [ ] Certificates come from approved metadata/trust policy sources, never auto-adopted from Response's KeyInfo.
- [ ] Never try keys from all IdPs and accept the first passing result.
- [ ] Use updated Spring Security/OpenSAML; never write a custom XMLDSig verifier or XPath parser for principals.
- [ ] Verify Response/Assertion signatures per profile and policy, along with signed-object binding.
- [ ] Validate Issuer, Audience, Destination, Recipient, InResponseTo, Conditions, SubjectConfirmation, and replay.
- [ ] Distinguish SP signing key, IdP verifying certificate, and SP decryption key.
- [ ] Maintain a metadata trust/expiry policy and a safe certificate/key update plan.
- [ ] Maintain a rotation process with approved A-old/A-new overlap, without mixing in IdP B's keys.
- [ ] With multiple IdPs/tenants, select registrations via verified context, not arbitrary browser-supplied URLs.
- [ ] Protect against XML Signature Wrapping, duplicate XML IDs, and XML parser attacks.
- [ ] Test invalid signatures, issuer mismatch, audience mismatch, replay, multi-assertion, and rotation.
- [ ] Protect personal data and private keys; never log raw SAMLResponses.
- [ ] After creating Authentication, still enforce role, tenant, and specific resource permissions.

## 18. Conclusion

**Secure SAML2 signature verification means verifying with the right IdP's key, over the exact signed content, in the right SP–IdP context.** The relationship among registrationId, IdP entity ID, verification credentials, SAMLResponse issuer, and audience must be unambiguous, especially when an application supports multiple IdPs/tenants.

Spring Security provides RelyingPartyRegistration and OpenSAML structures to perform protocol checks. Use vetted trust metadata, configure keys per asserting party, manage rotation, and test wrong-IdP scenarios. **A valid signature never replaces checks for audience, validity period, request correlation, or business permissions.**

### Official Documentation

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
