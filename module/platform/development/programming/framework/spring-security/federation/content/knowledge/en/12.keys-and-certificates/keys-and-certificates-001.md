# Saml2X509Credential: Distinguishing signing, verification, encryption, and decryption in Spring Security SAML 2.0

## 1. The problem: one X.509 certificate, four different roles

In SAML 2.0 federated login, the **Service Provider (SP/Relying Party)** and the **Identity Provider (IdP/Asserting Party)** exchange messages through the browser. Neither party should trust an XML `SAMLResponse` merely because it was successfully Base64-decoded: the SP must verify the signature and SAML conditions. When a party requires encryption, the receiving side must possess the correct decryption key. Therefore, configuring **private keys, public keys, certificates, and the role of each credential** is the foundation of federation.

Spring Security provides the class:

~~~java
org.springframework.security.saml2.core.Saml2X509Credential
~~~

This class holds the **public `X509Certificate`**, the **`PrivateKey` if required by the role**, and the **credential types**. Four roles:

- **`SIGNING`:** uses the sender's private key to **sign** data/messages.
- **`VERIFICATION`:** uses the sender's trusted certificate/public key to **verify** signatures.
- **`ENCRYPTION`:** uses the **recipient's** public key to **encrypt** data so that only the intended recipient can read it.
- **`DECRYPTION`:** uses the **recipient's** private key to **decrypt** the correspondingly encrypted data.

Even though all use X.509, **who owns the private key**, **signature vs. encryption**, **which direction it travels**, and **which side of `RelyingPartyRegistration` it goes on** are completely different. Mixing up credentials causes login failures, inability to decrypt assertions, or worse, establishing incorrect trust.

### Learning outcomes

After this lesson, the reader will be able to:

1. Correctly map all four roles onto the SP ↔ IdP flow, distinguishing **integrity/authenticity** from **confidentiality**.
2. Instantiate `Saml2X509Credential.signing/verification/encryption/decryption` with the proper inputs.
3. Understand the purpose of `signingX509Credentials`, `decryptionX509Credentials` on the SP side, and `verificationX509Credentials` on the IdP side in `RelyingPartyRegistration`.
4. Use Spring Boot YAML or Java to configure keys/certificates, knowing clearly which parameters must reside on each side.
5. Read SAML metadata `KeyDescriptor use="signing"` and `use="encryption"` without confusing private and public keys.
6. Determine when to sign an AuthnRequest, verify a Response/Assertion, have the IdP encrypt an Assertion, and have the SP decrypt it.
7. Handle certificate rollover, multiple coexisting keys, key mismatch, misconfigured trust, and private key loading issues.
8. Write/read a **standalone Java 17** program simulating signing, verification, encryption, and decryption at a basic cryptographic level, without mistaking it for a SAML provider.

The Spring examples target **Spring Boot 3.x / Spring Security 6.x, Java 17+, Servlet/MVC**. With Spring Security 7.x, the role concepts remain the same, though some OpenSAML APIs/mechanisms may change; always check the documentation for the **running version**.

## 2. Fundamental cryptographic concepts to know

### Public key, private key, X.509 certificate

A **private key** is used only by its owner and is never shared with the IdP/partner or published on a website. A **public key** can be provided to the other party to verify signatures or encrypt messages sent to the private key owner. An **X.509 certificate** contains the public key and certificate metadata in a standard format; a certificate **does not contain a private key**.

For SAML, certificates are typically distributed in **trusted metadata**, through vetted files, or in SP/IdP configuration. Never treat every certificate appearing in XML from an unverified sender as trustworthy. **Trust comes from the federation relationship and verified metadata**, not from the fact that "a file has a .crt extension".

Two different goals:

| Property to protect | Digital signature | Encryption |
| --- | --- | --- |
| Who issued the message? | Verifiable **against a trusted key** | Does not by itself prove origin |
| Was the message altered? | Detects data tampering within the signed scope | Does not replace signature/issuer checks |
| Can someone without the key read it? | Signing **does not hide** content | Encryption is designed to protect confidentiality |
| Whose key matters? | **Signer's private key**, verifier's public key | **Recipient's public key**, recipient's private key |

In Web Browser SSO, **TLS/HTTPS** also protects the transport channel through the browser; TLS does not replace SAML signatures, and SAML signatures do not make XML confidential.

### Key pair and certificate do not automatically "pair up"

The two files `sp-signing.key` and `sp-signing.crt` must belong to the **same key pair**. Simply having the same filename does not mean they match. For RSA, you can compare the corresponding public modulus using dedicated tools or test signing/verification in a test environment. If private key A is paired with certificate B, the configuration might load successfully, yet signature verification on the IdP side will fail.

A system may have:
- A dedicated key/certificate for signing.
- A dedicated key/certificate for decryption.
- A single key pair used for both signing and decryption if policy allows; however, you should consider **separating purposes, lifecycles, and permissions**.

Do not confuse the **SP's private key** with the **IdP's public certificate**. An IdP certificate file used solely for verification does not need—and must not be accompanied by—the IdP's private key on the SP.

## 3. Four-role matrix: who holds what?

In a typical SP-initiated SSO flow:

| Role | Operation | Performing entity | Material needed at entity | Purpose |
| --- | --- | --- | --- | --- |
| `SIGNING` | SP signs `AuthnRequest` | **SP** | **SP private key** + SP public certificate | IdP verifies the AuthnRequest sent by SP when required by policy |
| `VERIFICATION` | SP verifies `SAMLResponse/Assertion` | **SP** | Trusted **IdP public X.509 certificate** | Confirms the signature and integrity of the IdP message |
| `ENCRYPTION` | IdP encrypts Assertion sent to SP | **IdP** | **SP public X.509 certificate** | Only the intended SP can decrypt the Assertion |
| `DECRYPTION` | SP decrypts EncryptedAssertion | **SP** | **SP private key** + matching SP certificate | Extracts the Assertion for validation and authentication |

In the reverse direction—for example, if the SP must encrypt a message sent to the IdP—the **SP uses the IdP's public encryption certificate**; the **IdP uses its own private decryption key**. Therefore, never say "encryption is always the IdP" or "verification is always the SP": **the role depends on the sender/receiver and the message type**. The table above describes the common Web Browser SSO use case.

### An easy-to-remember symmetry rule

~~~text
      SIGNED MESSAGE ISSUER                    RECEIVER
      private key signs ---------------------> public certificate verifies
                 SIGNING                             VERIFICATION

      ENCRYPTED MESSAGE ISSUER                 RECEIVER
      recipient's public certificate --------> recipient's private key decrypts
                 ENCRYPTION                          DECRYPTION
~~~

The private key is not always on the sender's side. **Signing** uses the **signer's** private key; **decryption** uses the **recipient's** private key. This is the central distinction.

## 4. What does Saml2X509Credential contain?

In Spring Security, the `Saml2X509Credential` type holds these core pieces of data:

- `X509Certificate certificate` (required in common factory methods).
- `PrivateKey privateKey` when the credential is used for SIGNING or DECRYPTION.
- Set of `Saml2X509CredentialType`: `SIGNING`, `VERIFICATION`, `ENCRYPTION`, `DECRYPTION`.

Four static factory methods express programming intent:

~~~java
Saml2X509Credential signing =
        Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);

Saml2X509Credential verification =
        Saml2X509Credential.verification(idpSigningCertificate);

Saml2X509Credential encryption =
        Saml2X509Credential.encryption(idpEncryptionCertificate);

Saml2X509Credential decryption =
        Saml2X509Credential.decryption(spDecryptionPrivateKey, spDecryptionCertificate);
~~~

**This is an illustrative snippet**; variables of type `PrivateKey` and `X509Certificate` must be loaded/initialized in practice, and the class is imported from `org.springframework.security.saml2.core.Saml2X509Credential`. This snippet cannot compile standalone without declaring the variables or having the Spring Security dependency.

Meaning:

- The factory `signing(privateKey, certificate)` requires the private key belonging to the SP's key pair, a credential used at the SP.
- `verification(certificate)` **only needs the public certificate** of the partner we trust to verify signatures.
- `encryption(certificate)` **only needs the public certificate** of the intended recipient of the encrypted message.
- `decryption(privateKey, certificate)` requires the recipient's private key and corresponding certificate.

A `Saml2X509Credential` can carry **multiple usage types** if constructed with the appropriate constructors. Modern APIs provide certificate-only constructors for `VERIFICATION/ENCRYPTION` or privateKey + certificate constructors for `SIGNING/DECRYPTION`. However, **the ability to attach multiple roles does not mean you should reuse the same key in production**. Certain policies/algorithms and X.509 KeyUsage extensions may restrict usage.

The credential class is **a container for keys and intended usage**; by itself it does not define the entire SAML trust policy, verify metadata, encrypt Assertions, or replace the OpenSAML provider.

## 5. Where credentials go in RelyingPartyRegistration

Spring Security models an SP–IdP relationship with `RelyingPartyRegistration`:

- **Relying Party (RP/SP) section:** entity ID, Assertion Consumer Service (ACS), SP signing credentials, SP decryption credentials.
- **Asserting Party (AP/IdP) section:** IdP entity ID, SingleSignOnService endpoint/binding, **IdP verification credentials** so the SP trusts signatures from the IdP, and certificates for cases where the SP needs to encrypt for the IdP.

Builder example for an SP registration, omitting variable declarations:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistration
        .withRegistrationId("corp")
        .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
        .assertionConsumerServiceLocation(
                "{baseUrl}/login/saml2/sso/{registrationId}")
        .signingX509Credentials(c -> c.add(spSigningCredential))
        .decryptionX509Credentials(c -> c.add(spDecryptionCredential))
        .assertingPartyMetadata(party -> party
                .entityId("https://idp.example.org/issuer")
                .singleSignOnServiceLocation("https://idp.example.org/saml/sso")
                .verificationX509Credentials(c -> c.add(idpVerificationCredential))
        )
        .build();
~~~

**This is only a configuration fragment**; the credential variables are not defined in this short snippet; a more complete Java class is shown below.

Role of each line:

1. `withRegistrationId("corp")`: local name to look up an IdP link, **not automatically synonymous with the entity ID**.
2. `entityId(... )`: SP issuer/identifier sent in AuthnRequest and registered with the IdP.
3. `assertionConsumerServiceLocation(... )`: where the SP receives the Response from the browser.
4. `signingX509Credentials`: **SP holds the private key** to sign AuthnRequest and SP-originated messages when required.
5. `decryptionX509Credentials`: **SP holds the private key** to decrypt data encrypted by the IdP for the SP.
6. `assertingPartyMetadata(...).verificationX509Credentials`: **SP trusts the IdP's public signing certificate** to validate SAML Response/Assertion.
7. The IdP may also provide a certificate for **encryption in the SP-to-IdP direction** in required use cases; do not put the SP signing certificate into the IdP's verification list.

**Important:** The SP **does not need the IdP's private key** to verify IdP signatures. If anyone asks you to import the IdP private key into the SP, that is a severe sign of broken privilege separation.

## 6. Mapping between operations and XML metadata

SAML 2.0 metadata distributes **public certificates**, never private keys.

For **IdP metadata**, you may see:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_IDP_PUBLIC_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/saml/sso"/>
</md:IDPSSODescriptor>
~~~

This is an **XML snippet explaining structure**, not a full valid IdP metadata document: the certificate is replaced by placeholder text and it lacks `EntityDescriptor`/issuer and deployment-specific elements. It cannot be used for login.

For **SP metadata**, you may have:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_SP_SIGNING_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:KeyDescriptor use="encryption">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_SP_DECRYPT_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
</md:SPSSODescriptor>
~~~

Read carefully:

- `use="signing"` in **IdP metadata**: SP uses this certificate for **verification**.
- `use="signing"` in **SP metadata**: IdP uses this certificate for **verification** of SP-signed messages.
- `use="encryption"` in **SP metadata**: IdP uses this public cert for **encryption**, SP uses the matching private key for **decryption**.
- `use="encryption"` in **IdP metadata**: an entity sending a message to the IdP can use that public cert for **encryption**, and the IdP decrypts with its own private key.
- If `KeyDescriptor@use` is **omitted**, SAML metadata specifies that the key can be used for both signing and encryption depending on context; check the federation agreement, algorithms, implementation, and trust policy rather than guessing arbitrarily.

**Where metadata is loaded from and whether it is trustworthy is a separate decision.** If an attacker replaces the entire IdP metadata, they can supply their own public key and cause the SP to trust signatures from the wrong source. A valid TLS URL does not by itself prove the IdP entity ID/certificate belongs to the right partner. You must verify the metadata source, metadata signature/trust anchor per policy, and manage changes.

### Metadata signatures differ from message signatures

An XML metadata document may be **signed to protect the configuration**. That signature is different from the signature on a SAML `AuthnRequest`, `Response`, or `Assertion`. Never use a certificate *self-declared inside untrusted metadata* to prove that the metadata itself is trustworthy. The trust anchor for a metadata signature must come from an independent source.

## 7. When is each credential truly needed?

### 7.1 Signing — SP signing AuthnRequest

The SP can sign `AuthnRequest` so the IdP can verify that the SP is a valid origin and that the request has not been tampered with. This is especially important for requests containing sensitive requirements such as `ForceAuthn`, `RequestedAuthnContext`, or ACS/issuer.

Flow:

~~~text
SP private signing key
    -> Spring/OpenSAML generates signature on AuthnRequest
    -> browser transports request
    -> IdP verifies signature against SP public signing certificate
~~~

- In the **HTTP-Redirect binding**, the binding signature typically resides in the query parameters `SigAlg` and `Signature`, signing the standardized formatted query string.
- In **HTTP-POST AuthnRequest**, if the request is signed, an **XML Signature** inside the XML may be used.
- `Saml2X509Credential.signing(privateKey, cert)` does not automatically enable signing requirements for every IdP; you must also check metadata/IdP policy (`WantAuthnRequestsSigned`) and how Spring Security is configured.
- Never sign with the IdP's private key on the SP; the SP must not possess the IdP's private key.
- Never disable signature verification on the IdP to "make login work" if the IdP requires signed AuthnRequests.

### 7.2 Verification — SP verifying IdP-signed Response/Assertion

This is usually the **minimum required credential** for the SP to trust a SAML login result. Spring Security uses the IdP public verification certificate **configured from trusted metadata** or a vetted file.

~~~text
IdP private signing key
    -> IdP signs Response or Assertion
    -> browser POSTs SAMLResponse to SP ACS
    -> SP verifies with IdP public verification certificate
    -> continues checking issuer, audience, time, subject, InResponseTo...
~~~

- A digital signature alone does not prove a user is authorized to access every route. After XML verification, the SP must still verify all SAML conditions and **business authorization**.
- Depending on the SAML profile and Spring Security provider, either the Response or the Assertion must be signed per policy; do not assume every deployment must sign **both**.
- Match against the key of the **approved IdP**; a certificate with a valid public key from another IdP cannot substitute for it.
- When the IdP rotates keys, update metadata/verification credentials as planned; do not accept every certificate appearing in a Response.
- `verification(certificate)` uses a **public cert**, never the `IdP private key`.

### 7.3 Encryption — IdP encrypting Assertion sent to SP

When the IdP needs to conceal assertions/attributes from parties lacking the SP's private key, the IdP can encrypt the content for the SP to decrypt. The IdP needs the **SP public encryption certificate** (typically from SP metadata), never the SP private key.

~~~text
SP publishes public encryption cert
    -> IdP uses that cert to encrypt SAML XML data for SP
    -> browser transports EncryptedAssertion / EncryptedID
    -> SP uses matching private decryption key to decrypt
~~~

- Do not confuse **the IdP encrypting with the SP's public key** with **the SP using `Saml2X509Credential.encryption(idpCert)`**. The factory `encryption(idpCert)` on the SP describes the case where the **SP needs to encrypt for the IdP**; when the **IdP encrypts for the SP**, the `encryption(spCert)` action belongs to the **IdP**, while the SP registers **decryption(spKey, spCert)**.
- Encryption is typically hybrid encryption: a symmetric session key encrypts the payload and is wrapped using a public-key mechanism. The raw Java RSA example in the hands-on section **does not represent real XML Encryption**.
- Choose algorithms based on mutual capabilities and policy; do not downgrade to legacy algorithms merely to make decryption succeed.
- Encryption protects confidentiality; **it does not eliminate the requirement for signature and trust verification**.

### 7.4 Decryption — SP decrypting with private key

When receiving `EncryptedAssertion`, `EncryptedID`, or `EncryptedAttribute`, Spring Security/OpenSAML can use the SP's **decryption credentials** in `RelyingPartyRegistration`.

- If the SP lacks a decryption key, the IdP can generate a valid message, yet the SP **cannot read its contents**. That is a decryption error at the SP, not equivalent to the IdP reporting `AuthnFailed`.
- The SP key and certificate must match, and the IdP must encrypt for the right public certificate.
- When rotating decryption keys, **do not remove the old key too early** if in-flight messages/assertions encrypted with the old cert still exist. Plan an overlap and retirement period.
- Decryption is distinct from verification; decrypting XML does not make that assertion trustworthy.
- The OpenSAML provider performs signature verification and decryption in a safe order; depending on signature placement (Response/Assertion), **decrypting content before verifying the appropriate signature can break the signed structure**. Never manually decrypt, modify XML, and feed it into validation as if it were the original message.

## 8. Java Spring Security: loading a standard X.509 public certificate

The following helper uses the Java Standard Library and Spring `Resource` to read an X.509 certificate. The file lives on the classpath of a **Spring Boot project with the Spring Security SAML dependency**:

~~~java
package com.example.federation;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.core.io.Resource;
import org.springframework.security.saml2.core.Saml2X509Credential;

public final class SamlCertificateLoader {

    private SamlCertificateLoader() {
    }

    public static X509Certificate readCertificate(Resource resource)
            throws Exception {
        try (InputStream input = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(input);
        }
    }

    public static Saml2X509Credential idpVerificationCredential(
            Resource resource) throws Exception {
        return Saml2X509Credential.verification(
                readCertificate(resource));
    }

    public static Saml2X509Credential recipientEncryptionCredential(
            Resource resource) throws Exception {
        return Saml2X509Credential.encryption(
                readCertificate(resource));
    }
}
~~~

This is a **helper**, not a standalone Java `main()`. It requires the Spring JARs and a real certificate file where `Resource` points. A project using Spring Boot 3.x/Java 17+ must place the package under component scan if invoked from config. There is no fixed stdout.

A standard public X.509 PEM file looks like:

~~~text
-----BEGIN CERTIFICATE-----
...base64 DER content from the trusted partner...
-----END CERTIFICATE-----
~~~

The `...` is illustrative only, **not a valid certificate**. Use the **IdP cert provided through a trusted channel**; never copy an example from the Internet into a trust store.

`CertificateFactory` parses the certificate; it does not fully verify "this certificate belongs to the right IdP". In SAML configuration, public signing keys are typically pinned/obtained from approved metadata; checking certificate expiration, PKIX chain, key usage, and metadata validity must follow **product/federation policy**. Do not confuse this with CA/TLS validation of an HTTPS endpoint.

## 9. Java Spring Security: loading a PKCS#8 private key

Private keys must be protected. For an **unencrypted** PKCS#8 RSA key supported by Spring Security's converter, you can use `RsaKeyConverters.pkcs8()`. The file should be mounted from a secret store with minimal permissions and exposed only to the JVM at runtime.

~~~java
package com.example.federation;

import java.io.InputStream;
import java.security.interfaces.RSAPrivateKey;

import org.springframework.core.io.Resource;
import org.springframework.security.converter.RsaKeyConverters;

public final class SamlPrivateKeyLoader {

    private SamlPrivateKeyLoader() {
    }

    public static RSAPrivateKey readRsaPrivateKey(Resource resource)
            throws Exception {
        try (InputStream input = resource.getInputStream()) {
            return RsaKeyConverters.pkcs8().convert(input);
        }
    }
}
~~~

**This is a helper in a Spring project**, not a standalone Java 17 program. This converter works with RSA PKCS#8 per its API contract; if using EC/HSM/KeyStore/PKCS#11, you need the corresponding key-loading mechanism and appropriate Spring/OpenSAML configuration—never force every key into `RSAPrivateKey`.

### Distinguishing common file formats

| File content | Marker | Handling |
| --- | --- | --- |
| PEM public certificate | `BEGIN CERTIFICATE` | Read with `CertificateFactory("X.509")` |
| PEM PKCS#8 private key | `BEGIN PRIVATE KEY` | Read/decode with appropriate converter, protect the file |
| PEM PKCS#1 RSA private key | `BEGIN RSA PRIVATE KEY` | Do not assume PKCS#8 converter works directly; convert format or use appropriate library |
| Encrypted PEM private key | `BEGIN ENCRYPTED PRIVATE KEY` | Decrypt using secret/password and safe library; never log passphrase |
| KeyStore/PKCS#12 | `.p12`/`.pfx` file | Use `KeyStore` or suitable secret manager/HSM integration; do not treat directly as PEM |

**Never print private keys, and never put private key files into a Google Sheet or Git repository.** Even the password to decrypt an encrypted PEM is a secret; retrieve it from a secret manager and avoid writing it into a public `application.yml`.

## 10. Spring Boot YAML configuration using credential paths

Spring Boot can create a `RelyingPartyRegistrationRepository` from `spring.security.saml2.relyingparty.registration.*` properties. In the configuration below:

- **IdP verification certificate** is used by the SP to verify Response/Assertion signatures.
- **SP signing private key and cert** sign AuthnRequest when required by the IdP.
- **SP decryption private key and cert** decrypt assertions encrypted by the IdP for the SP.

Example `src/main/resources/application.yml` in a project that already has Spring Security SAML:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/corp"
            acs:
              location: "https://app.example.org/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decryption.key"
                  certificate-location: "file:/run/secrets/saml/sp-decryption.crt"
            assertingparty:
              entity-id: "https://idp.example.org/issuer"
              singlesignon:
                url: "https://idp.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
~~~

**Conditions:** This is a **reference configuration template for Spring Boot/Spring Security versions supporting these properties**, not a runnable system with fake files. You must supply real metadata, a public SP URL/ACS, and real files. `entity-id`/`acs.location` must match the registration created at the IdP. Some Boot versions auto-detect entity ID and ACS from templates; if hardcoded, replace them per environment.

Explanation of the groups:
- `registration.corp.signing.credentials`: private key/cert belonging to the **SP**.
- `registration.corp.decryption.credentials`: private key/cert belonging to the **SP** (can be a different key pair from signing).
- `registration.corp.assertingparty.verification.credentials`: public cert of the **IdP**.
- `assertingparty.singlesignon.sign-request: true`: illustrates an IdP requiring signed requests; **do not enable arbitrarily** if the IdP contract specifies otherwise, and do not set it to mask an opposite error.
- In the use case where the **SP needs to encrypt for the IdP**, publishing the IdP encryption cert belongs to IdP metadata or API config, **not an SP decryption private key**.

If the IdP provides **approved XML metadata**, a simpler option is `assertingparty.metadata-uri`; Spring will extract the public certificate/SSO endpoint from metadata. In some environments, manual properties and `metadata-uri` have version-specific precedence/merge behavior; **pick one clear configuration source** and do not mix conflicting credentials.

### Secret files in containers

Paths like `file:/run/secrets/saml/...</BT> point to the **JVM/container filesystem** and must have compatible read permissions; they are not local paths on a developer's laptop. Public `.crt` certificates may be managed classpath artifacts; production private keys should be supplied via runtime secret mount/HSM and never packaged into an executable JAR.

### When all four roles are not needed

An SP doing standard login **may only need the IdP verification credential** and not yet need SP signing/decryption if:
- The IdP accepts unsigned AuthnRequests;
- The IdP sends unencrypted assertions;
- Policy/profile does not require SP-signed messages in other steps.

Conversely, when the IdP requires signed AuthnRequests or encrypted assertions, add the corresponding credentials. Do not add unnecessary private keys just to "have all four roles".

## 11. A more complete Java bean: registering the right three credential types on the SP

The following example shows a **manual registration** for Spring Boot Servlet when you want control over file loading. It uses the two helpers above and the same files/URLs as the YAML example. **Do not use this bean together with a Boot YAML registration of the same ID without understanding auto-configuration**.

File `src/main/java/com/example/federation/SamlRelyingPartyConfig.java`:

~~~java
package com.example.federation;

import java.security.cert.X509Certificate;
import java.security.interfaces.RSAPrivateKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class SamlRelyingPartyConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository()
            throws Exception {

        X509Certificate idpSigningCert =
                SamlCertificateLoader.readCertificate(
                        new ClassPathResource("saml/idp-signing.crt"));

        X509Certificate spSignCert =
                SamlCertificateLoader.readCertificate(
                        new FileSystemResource("/run/secrets/saml/sp-signing.crt"));
        RSAPrivateKey spSignPrivate =
                SamlPrivateKeyLoader.readRsaPrivateKey(
                        new FileSystemResource("/run/secrets/saml/sp-signing.key"));

        X509Certificate spDecryptCert =
                SamlCertificateLoader.readCertificate(
                        new FileSystemResource("/run/secrets/saml/sp-decryption.crt"));
        RSAPrivateKey spDecryptPrivate =
                SamlPrivateKeyLoader.readRsaPrivateKey(
                        new FileSystemResource("/run/secrets/saml/sp-decryption.key"));

        Saml2X509Credential spSigning =
                Saml2X509Credential.signing(spSignPrivate, spSignCert);
        Saml2X509Credential spDecryption =
                Saml2X509Credential.decryption(spDecryptPrivate, spDecryptCert);
        Saml2X509Credential idpVerification =
                Saml2X509Credential.verification(idpSigningCert);

        RelyingPartyRegistration registration =
                RelyingPartyRegistration.withRegistrationId("corp")
                        .entityId("https://app.example.org/saml2/service-provider-metadata/corp")
                        .assertionConsumerServiceLocation(
                                "https://app.example.org/login/saml2/sso/corp")
                        .signingX509Credentials(c -> c.add(spSigning))
                        .decryptionX509Credentials(c -> c.add(spDecryption))
                        .assertingPartyMetadata(party -> party
                                .entityId("https://idp.example.org/issuer")
                                .singleSignOnServiceLocation(
                                        "https://idp.example.org/saml/sso")
                                .wantAuthnRequestsSigned(true)
                                .verificationX509Credentials(
                                        c -> c.add(idpVerification)))
                        .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

**Compile/run requirements:** you need all three Java files in the `com.example.federation` package (the two helpers in sections 8–9 and this config), Java 17, the Spring Security SAML module, Spring Boot Web/Security, and OpenSAML transitive dependencies per BOM; **real** certificate/PKCS#8 key files must exist. This class is a Spring `@Configuration`, **not a standalone `main()`**; it is only instantiated by Spring Boot on app startup. No specific stdout.

Notes:
1. `ClassPathResource` is suitable for public certificates managed alongside the build.
2. `FileSystemResource` uses a secret mount so private keys are not packaged into the JAR.
3. `InMemoryRelyingPartyRegistrationRepository` holds a snapshot of credentials at startup. When files change, **do not assume the bean will auto-reload**.
4. `wantAuthnRequestsSigned(true)` describes the IdP policy in the registration; the real IdP must match the approved configuration.
5. The two private keys can be different, following separation of privileges and lifecycle principles. Each must match the **cert for that exact role**.
6. `verificationX509Credentials` goes inside `assertingPartyMetadata`; never place the IdP verification certificate into the SP signing list.
7. An application can have multiple registrations for multiple IdPs; each registration must specify the exact IdP entity ID/cert/SSO endpoint, avoiding trust bleed across tenants.
8. If an older Spring Security version uses `assertingPartyDetails` instead of `assertingPartyMetadata`, use the **exact API of that version** and do not mix old/new methods.

### A minimal SecurityFilterChain

File `src/main/java/com/example/federation/SamlSecurityConfig.java`:

~~~java
package com.example.federation;

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
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

With `saml2Login`, Spring handles AuthnRequest and receives SAMLResponse at the ACS; with `saml2Metadata`, the application can publish **SP metadata** so the IdP knows the entity ID, ACS, and public certificates. Having a public certificate in metadata does not automatically guarantee the IdP uses the right role: both sides must align on metadata and policy.

## 12. Dependencies and code placement in the project

When the project already has Spring Boot dependency management/BOM, the equivalent Gradle Groovy DSL snippet is:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**This is a snippet to insert into an existing `build.gradle`**, not a complete build: Boot plugin, Java toolchain, and versions depend on the project. If the organization manages repositories via `settings.gradle` or a Maven mirror, place the Shibboleth releases repository where policy requires. Do not randomly override OpenSAML 4/5.

In a Maven project that already imports the Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

Insert inside `<dependencies>` of a valid POM; Spring Web/Security starters must be present as required by the project. Key/cert files cannot be replaced by fake hostnames: the setup also requires real IdP metadata, a client registration at the IdP, and a public endpoint reachable by the browser.

### Why not manually add a newer OpenSAML version?

Spring Security SAML SP uses OpenSAML to parse, verify signatures, and decrypt XML. The OpenSAML version must be compatible with the running Spring Security version. `NoClassDefFoundError`, `NoSuchMethodError`, or missing modules can result from mixing versions. Do not "fix" issues by excluding signature verification libraries from the classpath.

## 13. Encryption credentials on the SP: when are they used?

A frequently confusing question: **Does the SP need to declare `Saml2X509Credential.encryption(idpCertificate)`?**

Not in the **flow where the SP receives an encrypted assertion from the IdP**. For the inbound direction:
- The IdP uses the **SP public encryption cert** to encrypt.
- The SP uses the **SP private decryption key** to decrypt.
- The Spring SP needs `decryptionX509Credentials` on the **Relying Party**, not an IdP encryption credential to decrypt Assertions.

The **`encryption(idpCertificate)`** factory makes sense when **an SP-side component emits a message that needs to be encrypted for the IdP**. Depending on the protocol and API, you place the IdP certificate with the proper role into metadata/asserting-party config that supports encryption, or into a message-processing library. Never assume Spring Security Web Browser SSO automatically produces encrypted AuthnRequests just because this factory exists.

Java snippet example:

~~~java
X509Certificate idpEncryptionCert = SamlCertificateLoader.readCertificate(
        new ClassPathResource("saml/idp-encryption.crt"));

Saml2X509Credential forEncryptingToIdp =
        Saml2X509Credential.encryption(idpEncryptionCert);
~~~

**This is a code fragment illustrating intended usage**, not a complete SAML encryption configuration. To actually send encrypted messages, you also need the appropriate protocol, endpoint, library, algorithm, and policy. Do not apply this snippet in place of `spDecryption` from the earlier example.

## 14. Distinguishing XML Signing and XML Encryption

### SAML Signing

A SAML Response/Assertion may carry `<ds:Signature>` with references, digests, transforms, and algorithms. The verifier must validate the XML signature **in the proper context**, defending against XML Signature Wrapping and ensuring the exact object used as the principal is the one protected/verified.

Safe approach: let the **Spring Security/OpenSAML authentication provider** handle it. Never Base64-decode XML, extract an email via XPath, and build a session yourself without checking signature, issuer, audience, time conditions, and request correlation.

### SAML Encryption

SAML may contain:
- `<saml:EncryptedAssertion>`: wraps an encrypted assertion.
- `<saml:EncryptedID>`: an encrypted identifier.
- `<saml:EncryptedAttribute>`: an encrypted attribute.

XML Encryption typically uses `EncryptedData` and `EncryptedKey` representing the encrypted data/session key. The recipient needs the private key matching the public certificate the sender used.

**Order of operations matters:** if an assertion contains an XML Signature, decrypting before/after in the wrong place can invalidate the signature. The Spring Security OpenSAML provider distinguishes decrypting Response-level elements from elements inside an Assertion. Only customize the decrypter with a clear reason and thorough signature validation testing.

### Three common false assumptions

1. "Once the Assertion is encrypted, signing isn't needed." — False; encryption provides confidentiality, not sufficient proof of origin/conditions of the Assertion.
2. "Once the SAMLResponse is signed, nobody can read the NameID." — False; signed XML is still readable if not encrypted.
3. "The certificate inside `KeyInfo` is trusted proof because it is in the Response." — False; an independent IdP trust anchor/metadata is required.

## 15. Standalone Java 17: signing/verifying and encrypting/decrypting with RSA

To distinguish the four actions **without needing an IdP/Spring**, here is a Java 17 program runnable with the JDK. It generates **two temporary RSA key pairs in memory**, one representing the IdP and one representing the SP. It demonstrates:
- The IdP signs with its private key; the SP verifies using the IdP's public key.
- The SP can detect that modified data no longer has a valid signature.
- The sender encrypts for the SP using the SP's public key; the SP decrypts using the SP's private key.
- Encryption does not replace verification.

**Mandatory limitation:** the code is a **byte-level cryptographic simulation**; it does not create X.509 certificates, does not use SAML XML Signature/EncryptedAssertion, does not build metadata, and does not verify issuers or perform real login. Do not use this code to replace Spring Security/OpenSAML in production.

File **`SamlKeyRolesDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.Cipher;

public final class SamlKeyRolesDemo {

    static KeyPair newRsaKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static byte[] sign(byte[] data, KeyPair signer) throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(signer.getPrivate());
        signature.update(data);
        return signature.sign();
    }

    static boolean verify(byte[] data, byte[] signed, KeyPair signer)
            throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(signer.getPublic());
        signature.update(data);
        return signature.verify(signed);
    }

    static byte[] encryptForRecipient(byte[] plaintext, KeyPair recipient)
            throws Exception {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.ENCRYPT_MODE, recipient.getPublic());
        return cipher.doFinal(plaintext);
    }

    static byte[] decryptAtRecipient(byte[] ciphertext, KeyPair recipient)
            throws Exception {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.DECRYPT_MODE, recipient.getPrivate());
        return cipher.doFinal(ciphertext);
    }

    public static void main(String[] args) throws Exception {
        KeyPair idp = newRsaKeyPair();
        KeyPair sp = newRsaKeyPair();

        byte[] message = "saml-demo".getBytes(StandardCharsets.UTF_8);
        byte[] signed = sign(message, idp);

        System.out.println("IdP signature valid: "
                + verify(message, signed, idp));

        byte[] modified = "saml-tampered"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Tampered signature valid: "
                + verify(modified, signed, idp));

        byte[] encrypted = encryptForRecipient(message, sp);
        byte[] decrypted = decryptAtRecipient(encrypted, sp);
        System.out.println("Ciphertext differs: "
                + !Arrays.equals(message, encrypted));
        System.out.println("SP decrypted original: "
                + Arrays.equals(message, decrypted));
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac SamlKeyRolesDemo.java
java SamlKeyRolesDemo
~~~

**Exact stdout** (keys/ciphertext are random, but the program only prints Booleans):

~~~text
IdP signature valid: true
Tampered signature valid: false
Ciphertext differs: true
SP decrypted original: true
~~~

Output explanation:
- First line: the same public key from the IdP pair verifies the IdP private signature.
- Second line: modifying message bytes causes the signature to no longer verify.
- Third line: ciphertext does not share the same bytes as plaintext; it is not proof of sender authenticity.
- Fourth line: the SP's private key decrypts ciphertext encrypted with the SP's public key.

**Technical warning:** Pure RSA-OAEP can only encrypt small data depending on key size; **real SAML XML Encryption uses a hybrid model and XML structures**. Do not use `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` here as an automatic production algorithm choice; IdP/SP must agree on XML Encryption algorithms per policy and framework capabilities. The Java transformation name does not mean ECB mode is actually used for RSA.

## 16. SAML metadata: who must receive which public certificate?

The trust relationship requires information in the **right direction**:

| Party receiving certificate | Whose certificate is it? | Why is it needed? |
| --- | --- | --- |
| SP receives IdP metadata | **IdP signing cert (public)** | SP verifies Response/Assertion signed by IdP |
| IdP receives SP metadata | **SP signing cert (public)** | IdP verifies AuthnRequest signed by SP |
| IdP receives SP metadata | **SP encryption cert (public)** | IdP encrypts assertion sent to SP |
| SP receives IdP metadata when encrypting messages to IdP | **IdP encryption cert (public)** | SP encrypts data sent to IdP |
| SP private key storage | **SP signing/decryption keys** | SP signs/decrypts — never sent to IdP |
| IdP private key storage | **IdP signing/decryption keys** | IdP signs/decrypts — never sent to SP |

In practice, signing AuthnRequest depends on IdP policy/metadata. For example, if the IdP has `WantAuthnRequestsSigned="true"`, the SP needs the proper signing credential; some IdPs may allow unsigned requests per agreement and profile. For **IdP-signed Responses**, the SP must hold trust to the exact certificate per policy; never implicitly trust a signer certificate simply because it appears in the XML.

**Point to remember:** public certificates can be published via metadata; private keys always stay with their owner. "Sharing a key" means the owner uses one key pair for multiple operations, not sharing a private key between SP and IdP.

## 17. Key rotation: keeping login working without losing trust

Certificates expire and keys may need replacement due to policy, algorithm updates, incidents, or rollover. Spring Security allows configuring **multiple credentials in a collection** per role, but how keys are selected for signing/decryption/verification depends on version/provider/metadata, so **never assume simply adding an entry completes rotation**.

### Rotating the IdP signing certificate (SP verification)

1. The IdP publishes the new public signing certificate through a **verified channel**.
2. The SP updates its **IdP verification credentials** list to trust both old and new keys during the transition window if policy allows.
3. Test receiving responses signed with both the old and new keys; verify issuer/metadata and other validations.
4. Monitor signature failure audits/metrics; ensure no certificate from another IdP slips into trust.
5. Once the IdP stops using the old key, remove the old key on schedule and test.
6. If metadata is a startup snapshot, perform a verified repository restart/reload; **never assume an InMemory bean refreshes automatically when files/URLs change**.

### Rotating the SP signing key (IdP verification)

1. Generate a **new SP signing key pair** in the secret manager/HSM; do not export the private key to the IdP.
2. Publish the **new public signing certificate** in SP metadata or the official registration channel.
3. Wait for the IdP to accept both old/new certs (if supported by the platform) and confirm the cutover plan.
4. Only then switch the SP's active signing key; when multiple signing credentials are present, verify **which key Spring actually uses to sign**.
5. Revoke/remove the old key once no transactions remain needing verification; update metadata and monitoring.

### Rotating the SP decryption key (IdP encryption)

1. Publish the SP's **new public encryption certificate**; the IdP must know in advance.
2. Retain **both old and new private decryption keys** during the window when the IdP may encrypt with either public cert, if supported by the product.
3. Test encrypted assertions for each relevant cert, checking algorithm/KeyInfo.
4. Monitor decryption failures at the SP before removing the old key.
5. Never break encryption by arbitrarily enabling plaintext assertions if policy requires encryption.

**Metadata timing and lifecycle** matter more than generating new files. In a multi-node system, all pods must have consistent credential versions per cutover; if one pod uses the old key and another only has the new key, logins may fail intermittently.

## 18. HSM, keystores, and private key secrecy

**PEM private key files on disk** are easy for demonstration but are not always suitable for production.

Options:
- **PKCS#12/JKS KeyStore**: manages keys/certs by alias, password, and lifecycle; loadable via Java `KeyStore`.
- **HSM/PKCS#11**: keeps private keys non-exportable, using an appropriate crypto provider if Spring/OpenSAML can operate via the `PrivateKey` interface or custom strategy.
- **Secret manager**: supplies files or key material at initialization time, with appropriate IAM/audit/rotation and TLS.
- **Kubernetes Secret or Docker secret mount**: reduces the risk of baking keys into images, yet still requires RBAC, encryption at rest, mount permissions, and safe logging.
- **Java `PrivateKey` object**: does not mean the key cannot be extracted from memory; infrastructure and authorization controls remain vital.

### Minimum operational rules

1. Grant private key read permissions only to the process that needs to sign/decrypt.
2. Never commit private keys or passphrases to source code, logs, tickets, or shared documents.
3. Restrict metadata sources, secret mount paths, configuration edit rights, and certificate issuance permissions.
4. Record fingerprints/public certificate versions for auditing, but never print private keys.
5. Maintain a recovery/revocation/cutover plan if a private key is compromised.
6. Choose algorithms supported by both IdP/SP and compliant with security policy; avoid weak signature algorithms.
7. Verify TLS separately from SAML trust: an mTLS/HTTPS certificate does not replace a SAML signing certificate even if they occasionally share a key pair.
8. Never transfer keys over insecure channels or embed secrets in query parameters via data URIs.

## 19. Common errors and troubleshooting steps

| Symptom | Error class | Resolution |
| --- | --- | --- |
| `InvalidKeySpecException` | Private key format | Check PKCS#1/PKCS#8, whether key is encrypted, provider/algorithm; never log key content |
| `InvalidKeyException` | Key object unsuitable for algorithm | Check RSA/EC, signature/encryption algorithm, whether key was loaded properly |
| `CertificateException` on parse | File is not an X.509 certificate or wrong encoding | Read valid PEM/DER certificate, verify source and supplied file |
| `FileNotFoundException` | Wrong key/cert path in container/classpath | Check mount, resource path, permissions; do not use host paths when running in a pod |
| Signed AuthnRequest rejected by IdP | SP signing key/cert or IdP trust mismatch | Compare SP metadata, private/cert pair, key IdP trusts, algorithm/binding |
| IdP reports unsigned request | SP lacks signing config, IdP requires signed request | Add SP signing credential and proper policy; do not disable IdP signature check |
| Spring SP reports invalid signature on Response | Old/wrong IdP verification credential, altered XML | Check issuer, trusted IdP signing cert, metadata rollover, OpenSAML provider |
| SP reports issuer/audience mismatch | Federation metadata/application config | Check IdP entity ID, SP entity ID, ACS; do not "fix" by adding every certificate |
| SP cannot decrypt EncryptedAssertion | Missing/wrong SP private decryption key, key rotation, or algorithm | Check SP cert used by IdP, matching key, algorithm, and provider |
| SP decrypts successfully yet login still fails | Invalid signature/issuer/audience/time/subject/correlation | **Decryption does not equal Authentication**; keep full validation |
| Encrypted assertion sent to wrong certificate | IdP used old/wrong SP public cert | Check SP encryption metadata, key rollover, and IdP config |
| New certificate replaced in file yet app still uses old cert | InMemory registration does not reload | Perform controlled restart/refresh and verify effective registration |
| SP registration not found | Wrong ACS path/registration ID | Check `/login/saml2/sso/corp` and config; do not tweak credentials arbitrarily |
| Spring startup passes yet login fails | Keys load fine, but trust/wire differs | Inspect metadata, signature, issuer, actual request, and logs |
| Inappropriate X.509 KeyUsage | Certificate issued for wrong purpose | Confirm profile/KeyUsage, generate policy-compliant cert/key |
| SSL handshake to IdP fails | TLS CA/hostname trust | Fix HTTPS truststore, **distinct from** SAML signing verification certificate |
| IdP private key found in SP repo | Trust boundary breach | Isolate secret, investigate incident and rotate; SP only needs IdP public cert |

### Technical errors are not absolute proof

The same `invalid signature` message can stem from a wrong key, cert rotation, wrong metadata, incompatible XML, algorithm/canonicalization, or a tampered message. Do not declare root cause based on a single log string. Compare redacted request/response, trusted metadata, and credential fingerprints/public keys.

## 20. Flow-based diagnostic workflow

~~~mermaid
flowchart TD
    A[SAML login fails] --> B{Did SP create AuthnRequest?}
    B -- No --> C[Check registration, dependencies, filters]
    B -- Yes --> D{Did IdP accept request?}
    D -- No --> E[SP signing, IdP public trust, request binding/policy]
    D -- Yes --> F{Did browser POST SAMLResponse to ACS?}
    F -- No --> G[IdP/network/cookies/ACS]
    F -- Yes --> H{Is there EncryptedAssertion/ID/Attribute?}
    H -- Yes --> I[SP decryption private key and algorithm]
    H -- No --> J[Verify XML Signature]
    I --> J
    J --> K{Are signature and trust valid?}
    K -- No --> L[IdP verification cert/metadata and signature policy]
    K -- Yes --> M[Issuer, audience, destination, time, InResponseTo]
    M --> N{All conditions met?}
    N -- No --> O[Reject SAML authentication]
    N -- Yes --> P[Create Authentication then check authorization]
~~~

The diagram illustrates diagnostic branches; it **does not dictate the exact internal decryption/verification order** across all OpenSAML versions. An Assertion can be both encrypted and signed; signature and element placement can affect check ordering. Let the framework handle it per its safe contract.

## 21. Integration testing on a SAML test environment

### Test A — IdP verification certificate

1. Register matching partner SP and IdP metadata in the test environment.
2. Place the correct IdP public signing cert into SP verification credentials.
3. Log in with a validly signed SAMLResponse; expect Spring to verify and create `Authentication`.
4. With a test IdP using a different key **not in trust** or an environment intentionally using wrong test metadata, confirm the SP rejects it.
5. Never try adding untrusted certs to "get a PASS"; the goal is to prove the trust boundary works.

### Test B — Signed AuthnRequest

1. IdP requires signed AuthnRequests and has imported the SP public signing certificate.
2. SP generates requests using the corresponding SP private key.
3. Observe the IdP receiving, verifying the request, and continuing login.
4. Try misconfiguring a mismatched SP signing key/cert in a safe test environment; the IdP must reject the invalid request per policy.
5. For Redirect binding, inspect query Signature/SigAlg; for POST, inspect XML Signature per protocol/IdP version.

### Test C — Encrypted assertion

1. Provide the SP public encryption certificate to the IdP.
2. Configure the IdP to encrypt Assertions for the SP and send a response.
3. SP has the right private decryption key; Spring decrypts and then verifies SAML/issuer/audience/time.
4. Temporarily remove the test decryption key from registration in a **lab environment** and expect login to fail when the response is encrypted.
5. Restore the test key and re-verify; never switch production to plaintext just to avoid errors.

### Test D — Key rotation

1. Have the IdP issue a new public signing key alongside the old key in metadata/trust overlap (per policy).
2. SP temporarily trusts both keys; test assertions signed with each key.
3. Switch the active key and confirm the application has reloaded registration on all replicas.
4. Remove the old key on schedule after proving it is no longer in use.
5. Repeat separate procedures for the SP signing key and SP decryption key (**different** cutover times).

### Test E — SSL trust and SAML trust

1. An HTTPS metadata URL has a valid TLS certificate, but its XML issuer/key was replaced by an unapproved partner: the SP **must not update trust** based solely on HTTP 200.
2. An IdP SAML signing public certificate is correct, yet the endpoint's TLS certificate expired: handle the TLS error separately; do not replace the IdP verification key with the TLS CA.
3. Record the trust source and metadata version before drawing conclusions.

## 22. Inspecting files, certificates, and keys with operational tools

In authorized environments, several OpenSSL commands help inspect public certificates/keys **without printing private keys**:

~~~bash
openssl x509 -in sp-signing.crt -noout -subject -issuer -dates -fingerprint -sha256
openssl x509 -in idp-signing.crt -noout -subject -issuer -dates -fingerprint -sha256
openssl pkey -in sp-signing.key -pubout -out sp-signing-public.pem
openssl x509 -in sp-signing.crt -pubkey -noout -out sp-cert-public.pem
~~~

**Run only on files you are authorized to handle** and in a secure environment; the two generated temporary public files can be compared with appropriate diff/hash tools. Filenames and outputs vary by real certificate, so there is no fixed stdout. `openssl pkey` may require a passphrase if the key is encrypted. Do not use `-text` on a private key or output keys to shared logs; avoid leaving passphrases in command history.

### Is a fingerprint a trust anchor?

A certificate's SHA-256 fingerprint is an **identifier** to compare against a value confirmed **via an independent channel**. Simply having a program compute the fingerprint of a newly downloaded untrusted certificate does not establish trust. Comparison requires an expected fingerprint/metadata signing key approved in advance.

### Checking expired certificates

X.509 has `notBefore/notAfter`, but the extent of CA/PKIX and validity checks on a SAML signing cert depends on the product/federation config. A SAML trust binding may be managed via metadata and differ from TLS certificate validation; **do not assume every expired certificate inevitably throws the exact same exception**. Per organizational security policy, rotate/update certificates on schedule and test end-to-end.

## 23. Handling multi-IdP and multi-tenant

When one SP integrates with multiple IdPs, `RelyingPartyRegistrationRepository` can hold multiple registrations:

~~~text
registrationId = corp-a
  assertingParty.entityId = https://idp-a.example.org/issuer
  verificationCerts = [IdP-A signing certs]
  spSigningKey = tenant A key (per policy)
  spDecryptionKey = tenant A key (per policy)

registrationId = corp-b
  assertingParty.entityId = https://idp-b.example.org/issuer
  verificationCerts = [IdP-B signing certs]
  spSigningKey = tenant B key (per policy)
  spDecryptionKey = tenant B key (per policy)
~~~

The SP may choose to share certain SP keys at the infrastructure level, but it must **segregate permissions and bind trust to the exact IdP**. If a response from IdP B is used to authenticate a user in tenant A, beyond the signature, `Issuer`, `Audience`, `Recipient`, `InResponseTo`, and registration must match.

**Do not build a "global verification list" containing every certificate of every IdP without binding issuer/registration.** A valid public key of partner B must never allow impersonating partner A. Similarly, do not mix decryption private keys across tenants when legal/policy separation requires it.

## 24. When a system uses the same key for multiple roles

Spring Security allows one credential to have multiple intended usages in appropriate constructors. The documentation notes examples where the same key pair can be used for signing and decryption, and the same public key can serve verification/encryption.

However, consider:

- A compromised private key affects **both signing and decryption** if shared.
- Rotating the signing key forces changing the decryption key and may render assertions still using the old key undecryptable.
- Certificates may carry `KeyUsage` or policies prohibiting certain uses.
- Algorithms: an ECDSA signing key is not inherently compatible with RSA encryption mechanisms per policy.
- Separating keys makes permission management, auditing, HSM slots, and rotation clearer.

**Practical rule:** only reuse when supported by both IdP/SP and backed by a clear operational reason; prefer separating roles when designing new systems with high security requirements. Never replace a `verification` credential with `encryption` simply because both share the same certificate file.

## 25. Paying attention to less obvious details

### 25.1 Certificates are not the TLS truststore

Java `cacerts` or a TLS truststore verifies HTTPS metadata endpoints. The IdP SAML signing certificate verifies signatures on SAML messages under federation trust. The two **can be different certificates**, and importing the IdP cert into the TLS truststore does not automatically configure `verificationX509Credentials` in Spring Security.

### 25.2 Rotating a cert does not necessarily change the entity ID

An IdP can keep its `entityID` unchanged while replacing its public signing certificate. Update trust credentials per procedure; do not create a new registration or change the issuer without reason. Likewise, the SP entity ID can remain unchanged when rotating signing/decryption keys.

### 25.3 Encrypt-then-Verify is not an immutable rule

Messages may be signed before encryption or partially encrypted; the exact validation/decryption order depends on signature placement and target element. The Spring Security OpenSAML provider has strategies for response elements and assertion elements; improper manual intervention can break signature validation.

### 25.4 Signing AuthnRequest does not replace Assertion signatures

The SP's signature on a request helps the **IdP** verify the request came from the SP. The **IdP's signature on the response/assertion** helps the **SP** trust the authentication result. The two signatures belong to **different directions and subjects**. Never treat a signed AuthnRequest as proof of a valid user login.

### 25.5 Certificate chains do not replace issuer/audience

Even if a certificate has a valid chain, the SP must ensure the message's issuer, audience, and conditions match the registration. **SAML key trust is not merely PKIX certificate chain validation**.

### 25.6 Keep only "active" secrets

Putting multiple private keys into configuration without a selection and retirement plan increases the attack surface. Every key should have an owner, role, createdAt, activation/retirement schedule, source, and audit trail.

## 26. Exercises with answers

**Exercise 1.** The SP needs to verify the signature of a SAMLResponse sent by the IdP. Does the SP need the IdP's private key or which public certificate?

**Answer:** The SP needs the **trusted IdP public signing certificate** under `Saml2X509Credential.verification(idpCert)`, attached to `assertingPartyMetadata(...).verificationX509Credentials`. The IdP private key is not needed.

**Exercise 2.** The IdP requires signed AuthnRequests. Where does the key material reside?

**Answer:** The SP holds the **SP private signing key** and matching certificate; configure `Saml2X509Credential.signing(spKey, spCert)` on the Relying Party side. The IdP receives the SP public signing cert for verification.

**Exercise 3.** The IdP sends an EncryptedAssertion to the SP, but the SP only has `Saml2X509Credential.encryption(spCert)`. Is that enough to decrypt?

**Answer:** No. The SP needs the **private decryption key** matching the SP public certificate used by the IdP; configure `Saml2X509Credential.decryption(spKey, spCert)` in RP decryption credentials.

**Exercise 4.** A development team uses `Saml2X509Credential.decryption(idpPrivateKey, idpCert)` on the SP to "decrypt assertions". What is wrong with this?

**Answer:** The IdP must never give its private key to the SP. The IdP must encrypt for the **SP's public cert**, and the SP decrypts with the **SP's private key**.

**Exercise 5.** Login fails with invalid signature after the IdP announces a cert rollover. What are the right steps?

**Answer:** Verify the new metadata/cert through a trusted source, configure trusted verification credentials including the keys allowed during overlap, check issuer, signature, repository refresh, and all replicas; never disable verification.

**Exercise 6.** An encrypted assertion has been decrypted into plaintext XML. Can you manually create an authenticated user yet?

**Answer:** No. Spring Security/OpenSAML must verify signature, issuer, audience, recipient/destination, timestamps, subject confirmation, and request correlation/replay.

**Exercise 7.** The line `KeyDescriptor use="encryption"` appears in SP metadata. Who uses that public cert and who holds the private key?

**Answer:** The IdP uses the **SP public encryption cert** to encrypt assertions sent to the SP; the SP holds the **private decryption key**.

**Exercise 8.** The SP uses one key pair for signing and decryption. Should this approach be recommended by default for every system?

**Answer:** No. The API may support reuse, but separation of duties, algorithms/KeyUsage, blast radius on key compromise, and rotation plans are reasons why they should generally be separated.

**Exercise 9.** Can a certificate just downloaded from HTTPS IdP metadata be trusted automatically because the website has valid TLS?

**Answer:** No. TLS proves the connection to the host against the truststore; you must verify the exact endpoint/issuer/certificate/metadata policy with the partner, and metadata signature if required.

**Exercise 10.** A team configures `assertingparty.verification.credentials` with the SP certificate. What will happen?

**Answer:** If the IdP signs with a different key, SP verification fails; logically, this trusts the wrong source. Fix it to the approved **IdP public signing certificate**; do not skip signatures.

**Exercise 11.** Can the same IdP private key be used to sign AuthnRequests on the SP to pass IdP policy?

**Answer:** No. The SP signs with the **SP private key**; the IdP uses the SP public cert to verify. Sharing the IdP private key breaks ownership boundaries and is a security incident.

**Exercise 12.** Browser Network shows the HTTPS POST to the ACS succeeded, yet Spring reports cannot decrypt assertion. Is this a TLS or SAML error?

**Answer:** The HTTPS part succeeded; the error is in **SAML XML decryption**, requiring inspection of the SP private key/certificate/algorithm, metadata, and key rollover.

**Exercise 13.** A SAMLResponse signed with IdP B's key is sent to IdP A's registration. Can the SP accept it merely because cert B is valid somewhere in the system?

**Answer:** No. Registration, issuer, verification credentials, and audience/recipient must bind to the exact partner; never share trust globally in an arbitrary way.

**Exercise 14.** Why can the same public certificate be used for verification/encryption in some APIs, yet is insufficient for signing/decryption?

**Answer:** Verification/encryption only require the **public key**, whereas signing/decryption must use the owner's matching **private key**.

## 27. Configuration and operations checklist

- [ ] Accurately identified SP/IdP, messages needing signing/decryption, and transmission direction.
- [ ] Configured `signingX509Credentials` with **SP private signing key + SP cert** when IdP requires signed requests.
- [ ] Configured `assertingPartyMetadata.verificationX509Credentials` with the **trusted IdP public signing certificate**.
- [ ] Configured `decryptionX509Credentials` with **SP private decryption key + cert** if receiving encrypted assertions.
- [ ] If the SP needs to encrypt for the IdP, obtained the **IdP public encryption certificate** with protocol/binding support; never used the IdP private key.
- [ ] Public certificate and private key for each role genuinely match as a pair, with policy-compliant algorithm/KeyUsage.
- [ ] Metadata source and certificates independently verified, audited, and signature/trust checked where applicable.
- [ ] SP metadata published with accurate public entity ID, ACS, and SP signing/encryption certificates for the IdP.
- [ ] Secret file paths are runtime/container paths with minimal read permissions, excluded from source control and logs.
- [ ] No mixing of Spring Security/OpenSAML versions; API classes/methods match current dependencies.
- [ ] Planned **rotation overlap** for IdP verification, SP signing, and SP decryption in the proper sequence.
- [ ] If using InMemory registration, changing certificate files does not auto-refresh; tested controlled restart/refresh.
- [ ] Tested signed AuthnRequest and IdP verification, encrypted assertion/decryption, key mismatch, and cert rollover.
- [ ] Never disabled checks for signature, issuer, audience, time, recipient/destination, InResponseTo, or replay to bypass errors.
- [ ] Never displayed/logged raw assertions, private keys, session cookies, or personal data.

## 28. Summary

**Signing belongs to the sender; encryption targets the receiver:** the sender uses its **private key** to sign, and the receiver uses the **sender's public cert** to verify; the sender uses the **receiver's public cert** to encrypt, and the receiver uses its **own private key** to decrypt.

In a Spring Security SP, the core credentials are usually the **IdP verification cert**, the **SP signing key/cert** if the IdP requires signed AuthnRequests, and the **SP decryption key/cert** if the IdP sends encrypted assertions. The `encryption(certificate)` factory only applies when **encrypting for the subject that owns that certificate's private key**; it cannot substitute for decryption on the SP.

### Reference documentation

- Spring Security — SAML 2.0 Login Overview, RelyingPartyRegistration, and Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — `Saml2X509Credential` API (four factories and credential types): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Security — Authenticating SAML Responses, decryption providers, and validation order: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 API — `Saml2X509CredentialType`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/saml2/core/Saml2X509Credential.Saml2X509CredentialType.html
- Spring Boot — SAML 2.0 Security properties and auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OASIS — SAML V2.0 Metadata Specification, `KeyDescriptor` and KeyInfo: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C — XML Encryption Syntax and Processing 1.1: https://www.w3.org/TR/xmlenc-core1/
