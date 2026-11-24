# Adding AuthnRequest Signing, Encrypted Assertions, and Recipient Verification

**When completing SAML2 SSO integration in Spring Security, "login works" is not enough.** The Service Provider (SP/Relying Party) application must send a signed `AuthnRequest` when required by the IdP partner, receive an `EncryptedAssertion` that only an SP with the matching private key can decrypt, and strictly verify **Response Destination**, **SubjectConfirmationData Recipient**, **AudienceRestriction**, **InResponseTo**, issuer, signature, validity window, and replay protection. If any constraint fails, **no Authentication must be created**, even if the assertion decrypts successfully or a signature from another IdP is still valid.

This exercise belongs to **Spring Security – federation → Comprehensive Practice**. It builds a scenario with two simulated parties: IdP `urn:corp:idp` and SP `urn:portal:sp:corp` at `https://portal.example.test`. The examples describe an OpenSAML-based Spring Boot/Spring Security SAML2 Service Provider, YAML snippets, SAML formats, negative testing, key lifecycles, operations, and a standalone Java 17 program demonstrating signatures, AEAD encryption, and recipient conditions.

**Three boundaries that must never be conflated:**

1. **The SP signs the AuthnRequest** with the *SP private signing key* so the IdP can verify the request genuinely comes from the registered SP. This is not the signature on the SAML Response.
2. **The IdP encrypts the Assertion** with the *SP public encryption certificate*; the SP uses the *SP private decryption key* to open the content. Encryption protects confidentiality; **it does not by itself prove the IdP is trustworthy**.
3. **The SP verifies the decrypted content and the signature of the right IdP**, including `Destination`, `Recipient`, and `AudienceRestriction` pointing to the intended recipient, along with request correlation and replay protection.

All domains, keys, users, and certificates below are **lab data**. Do not write real private keys, SAMLResponses, session cookies, or user attributes into documentation/chats/logs.

## 1. Practical Objectives

Upon completion, engineers will be able to:

- Explain which party **signs**, which **verifies**, which **encrypts**, and which **decrypts** in Web Browser SSO.
- Separately configure `signing.credentials`, `decryption.credentials`, and `assertingparty.verification.credentials` for Spring Boot SAML2.
- Issue and verify a signed `AuthnRequest` using HTTP-Redirect or HTTP-POST binding properly.
- Publish **SP metadata** so the IdP uses the right SP signing and encryption certificates.
- Receive an `EncryptedAssertion` at the ACS and decrypt it using the private key of the selected registration.
- Verify the signed SAML Response/Assertion using the **IdP verification certificate**, not the SP certificate.
- Verify `Response.Destination`, `SubjectConfirmationData.Recipient`, `Conditions.AudienceRestriction`, and `InResponseTo` accurately.
- Distinguish a signed-and-encrypted assertion from encryption-only, XML signature wrapping, and endpoint mismatch.
- Run smoke tests, cross-IdP/tenant tests, negative security tests, and key rotation tests.
- Understand where the Java 17 demo aids reasoning while **never replacing OpenSAML cryptographic validation**.

## 2. Fixed Lab Parameter Set

| Property | Illustrative Value | Meaning |
| --- | --- | --- |
| `registrationId` | `corp` | Internal Spring key for the trust profile |
| SP entityID | `urn:portal:sp:corp` | Expected Audience |
| SP base URL | `https://portal.example.test` | Public HTTPS origin |
| SP ACS | `https://portal.example.test/login/saml2/sso/corp` | Endpoint processing SAML Responses |
| IdP entityID | `urn:corp:idp` | Trusted Asserting Party / Response Issuer |
| IdP SSO URL | `https://idp.corp.test/saml/sso` | Endpoint receiving AuthnRequest |
| HTTP request binding | Redirect (example) | Browser carries SAMLRequest to IdP |
| HTTP response binding | POST | Browser POSTs SAMLResponse to ACS |
| AuthnRequest ID | `_req901` | Unique request ID |
| RelayState | `R-901` | Opaque transaction reference |
| SP signing cert | `sp-sign.crt` | Public cert for IdP to verify AuthnRequest |
| SP signing private key | `sp-sign.key` | SP signs AuthnRequest |
| SP encryption cert | `sp-enc.crt` | Public cert for IdP to encrypt Assertion |
| SP decryption private key | `sp-enc.key` | SP decrypts Assertion |
| IdP signing cert | `idp-sign.crt` | SP verifies signed Response/Assertion |
| NameID | `alice@corp.test` | Extracted only after trusted validation |
| Expected tenant | `north` | Application authorization after SAML |

**Do not assume `registrationId` equals IdP entityID or tenant ID.** In practice, a single SP may have multiple registrations; each registration must specify its exact IdP, ACS, SP entityID, and credentials.

## 3. Four Key Types and Direction of Use

| Key / Certificate Type | Who Holds the Private Key? | Who Trusts the Public Key / Cert? | Purpose |
| --- | --- | --- | --- |
| **SP signing** | SP | IdP | IdP verifies AuthnRequest, LogoutRequest signatures per policy |
| **SP encryption/decryption** | SP | IdP | IdP encrypts Assertion, SP decrypts it |
| **IdP signing** | IdP | SP | SP verifies Response/Assertion signature |
| **TLS HTTPS** | Respective server | Browser / HTTP client | Secures transport channel; does not replace XML signature |

The same key pair can be used for signing and encryption in some deployments, but **roles should be separated** when IAM/security policy and interoperability allow: rotation, access permissions, and blast radius become clearer.

**Common mistake:** configuring `idp-sign.crt` under `decryption.credentials`, or supplying `sp-enc.crt` as the IdP verification certificate. They represent different trust relationships; do not swap their roles simply because both are X.509 files.

## 4. Enhanced SAML Web SSO Flow Diagram

~~~text
 Browser                Spring Security SP                     Corp IdP
    |                           |                                  |
    | GET /saml2/authenticate/corp                                |
    |-------------------------->|                                  |
    |                    Generate ID=_req901                       |
    |                    Sign AuthnRequest with SP signing key      |
    |                    Save pending ID + RelayState + session     |
    |<----- Redirect SAMLRequest + RelayState + SigAlg + Signature|
    |------------------------------------------------------------->|
    |                                              Verify SP request
    |                                              Authenticate user
    |                                              Sign Assertion/Response
    |                                              Encrypt Assertion to
    |                                                SP encryption cert
    |<---------------------------- Browser HTML POST form ----------|
    | POST ACS: SAMLResponse + RelayState                          |
    |-------------------------->|                                  |
    |                    Resolve trusted registration               |
    |                    Verify signed SAML with IdP cert            |
    |                    Decrypt EncryptedAssertion using SP key     |
    |                    Verify signatures per profile              |
    |                    Check Issuer, Destination, Recipient        |
    |                    Check Audience, InResponseTo, time, replay  |
    |                    Map verified subject + tenant permissions  |
    |<-------------------- Local session or security error --------|
~~~

**The order of signature verification and decryption depends on the profile and signature placement**: an outer signed Response may be verified before decrypting the EncryptedAssertion, whereas an Assertion that was signed and then encrypted must have the **Assertion decrypted before verifying the inner signature**. Spring/OpenSAML distinguishes decryption strategies to preserve XML signature integrity.

## 5. When Does AuthnRequest Need to Be Signed?

SAML Web Browser SSO does not force every IdP to require or accept the same AuthnRequest signing behavior. IdP metadata may declare **`WantAuthnRequestsSigned`**, or an integration policy may mandate signed requests. When signing is required:
- The SP has a **private signing key** and matching X.509 certificate.
- The IdP registers the **SP public signing certificate**.
- The SP signs the request according to the **binding** (HTTP Redirect query signature or XML signature inside POST).
- The IdP verifies the signature and trusts the **SP entityID** before processing the request.
- Signature algorithms and certificate lifecycles must be agreed upon by both sides.

**Do not assume setting `WantAuthnRequestsSigned=false` on the SP bypasses IdP policy.** If the IdP requires signing, an unsigned request must be rejected by the IdP. This condition is distinct from the **IdP signing the SAML Response/Assertion** on return.

Current Spring Security documentation states that `Saml2WebSsoAuthenticationRequestFilter` constructs, signs/serializes the request per registration, and supports signed Redirect requests when `signingX509Credentials` are present. Cases not requiring signing must be configured consistently with IdP metadata and the bilateral contract.

## 6. HTTP-Redirect Signature: Signing on the Query String

An illustrative URL, **not a URL containing an immediately verifiable signature**:

~~~http
GET /saml/sso?SAMLRequest=ENCODED_DEFLATED_REQUEST&RelayState=R-901&SigAlg=RSA_SHA256_URI&Signature=ENCODED_SIGNATURE HTTP/1.1
Host: idp.corp.test
~~~

With the SAML HTTP-Redirect binding:
1. The SP constructs XML `AuthnRequest` with `ID`, `IssueInstant`, `Issuer`, `Destination`, and `AssertionConsumerServiceURL`.
2. Deflates/encodes and URL-encodes `SAMLRequest` per the binding specification.
3. If RelayState is present, places the encoded value in the proper position.
4. Appends `SigAlg` using an allowed algorithm.
5. Signs **the exact canonicalized query string specified by the binding**, typically ordered `SAMLRequest=...&RelayState=...&SigAlg=...` when RelayState is present.
6. Appends the encoded signature in the `Signature` query parameter.
7. The IdP reconstructs the signed input per specification and verifies it with the trusted SP signing certificate.

**Do not sign the XML and expect the IdP to verify it as an HTTP-Redirect signature**, and do not manually parse/re-encode query parameters in a way that alters the signature's exact format. Always use the Spring/OpenSAML binding implementation rather than building URLs by string concatenation.

**RelayState** is part of the signed input in a signed Redirect binding when present. However, it does not represent an authenticated session in the browser.

## 7. HTTP-POST AuthnRequest and XML Signature

If the IdP requires AuthnRequests via POST, SAMLRequest is an encoded XML document submitted by the browser; the request signature typically appears as an **XML Signature** inside the XML message per the profile/binding.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req901"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.corp.test/saml/sso"
    AssertionConsumerServiceURL="https://portal.example.test/login/saml2/sso/corp">
    <saml:Issuer>urn:portal:sp:corp</saml:Issuer>
    <!-- Signed XML has a namespace-aware ds:Signature element
         at the profile-defined position. Omitted for readability. -->
</samlp:AuthnRequest>
~~~

**The XML above only illustrates structure and is an unsigned fixture**—do not feed it into tests claiming valid signatures. In SAML XML Signature, element ordering and canonicalization/ID references matter. Use OpenSAML/Spring to emit signed messages per binding instead of inserting `<ds:Signature>` manually.

**Do not skip TLS** merely because XML signatures exist: browser cookies, endpoints, and metadata still require transport protection.

## 8. Creating Separate Credentials for SP Signing and Decryption

In a lab, key pairs can be generated with approved PKI/secret management tools. OpenSSL examples are **for staging/testing only** and contain no real secrets:

~~~bash
# SP signing private key (RSA key pair for compatibility lab)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out sp-sign.key

# Self-signed certificate for test metadata exchange only
openssl req -new -x509 -sha256 -days 30 \
  -key sp-sign.key -out sp-sign.crt \
  -subj "/CN=portal-signing-lab"

# Independent SP decryption key pair
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out sp-enc.key
openssl req -new -x509 -sha256 -days 30 \
  -key sp-enc.key -out sp-enc.crt \
  -subj "/CN=portal-encryption-lab"

# Inspect identity/certificate metadata only; do not print private key
openssl x509 -in sp-sign.crt -noout -subject -fingerprint -sha256
openssl x509 -in sp-enc.crt -noout -subject -fingerprint -sha256
~~~

In production:
- Use CA/PKI/HSM/KMS/secret vault per policy; if federation policy permits self-signed certs, they must be **pinned/trusted out-of-band**, never implicitly trusted over the Internet.
- Store private keys in secret mounts, never committed to Git or container images; grant the service process least-privilege read access.
- Published SP metadata contains only **public certificates**; the IdP must never receive `sp-sign.key` or `sp-enc.key`.
- Verify signing/encryption algorithms and key lengths across both products, avoiding weak legacy algorithms.
- Record an inventory of issuer/SP entityID, certificate fingerprints, key lifecycles, rotation owners, and deployment versions.

## 9. Exchanging Information with the IdP in the Right Direction

Send to the authenticated IdP administrator:
- Exact SP entityID `urn:portal:sp:corp`.
- SP ACS URL and HTTP-POST binding.
- SP public **signing certificate** for verifying AuthnRequests.
- SP public **encryption certificate** for encrypting Assertions.
- SP metadata URL or metadata XML from Spring.
- Whether the IdP requires signed AuthnRequests, which binding, and allowed signature algorithms.
- Whether the IdP **signs Response, signs Assertion, or both**; and encryption policy.
- Independently verified IdP issuer/entityID and signing certificate/metadata URI.
- Allowed NameID formats, attributes, assertion lifetime, forced reauthentication, and RelayState policy.

**Never send** private keys, raw user SAMLResponses, session cookies, or user passwords. If the IdP lacks Assertion encryption support or only supports prohibited algorithms, fix the interoperability/contract rather than silently relaxing security policy.

## 10. What Evidence Does the SP Receive from the IdP?

A SAML Response payload may look like:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
    ID="_resp901"
    InResponseTo="_req901"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:15Z">
    <saml:Issuer>urn:corp:idp</saml:Issuer>
    <samlp:Status>
      <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    <saml:EncryptedAssertion>
      <!-- xenc:EncryptedData / xenc:EncryptedKey from IdP -->
    </saml:EncryptedAssertion>
</samlp:Response>
~~~

**The structure is illustrative only**, has no ciphertext/signature, and is not a valid SAMLResponse. A real Response may be signed by the IdP at the Response level or have the Assertion inside EncryptedAssertion signed per policy; **the SP must verify valid signatures per configuration and never accept unsigned identity data**.

Do not assume `<EncryptedAssertion>` exposes readable `NameID`/`AudienceRestriction` before decryption. Do not log decrypted assertions/PII without strict need and authorization.

## 11. Encrypted Assertion: Confidentiality, Not Authentication

An Assertion may contain:
- `NameID` or `EncryptedID`, identifying the user.
- `AuthnStatement` and `AuthnInstant`.
- `AttributeStatement` such as department/groups.
- `Conditions` including validity times and `AudienceRestriction`.
- `SubjectConfirmationData`, including `Recipient`, `InResponseTo`, and `NotOnOrAfter`.

The IdP may encrypt the assertion body with a **symmetric content-encryption key**, then wrap the content key using the **SP public encryption key** per XML Encryption; the SP uses the corresponding private key to unwrap it and verify integrity per profile.

**Algorithm note:** XML Encryption supports multiple methods and versions; do not assume every IdP supports the same AES-GCM/RSA-OAEP configuration. Choose modern, organization-approved combinations and test actual interoperability. Avoid downgrading to RSA1_5/legacy CBC/weak algorithms just to "get past errors".

**If an encrypted assertion decrypts successfully but the signature is invalid, it must be rejected.** If the signature is valid but Recipient/Audience is wrong, it must also be rejected.

## 12. Spring Boot SAML2 Configuration with All Three Credential Types

Example for **Spring Boot 3.x/4.x with `spring-security-saml2-service-provider`**—corresponding properties must be verified against the deployed BOM version:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:portal:sp:corp"
            acs:
              location: "https://portal.example.test/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign.key"
                  certificate-location: "file:/run/secrets/saml/sp-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-enc.key"
                  certificate-location: "file:/run/secrets/saml/sp-enc.crt"
            assertingparty:
              entity-id: "urn:corp:idp"
              singlesignon:
                url: "https://idp.corp.test/saml/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml-trust/idp-sign.crt"
~~~

**Interpretation:**
- `signing.credentials`: **SP** private key/cert to sign AuthnRequests; the IdP needs the public cert.
- `decryption.credentials`: **SP** private key/cert to decrypt encrypted Assertions; the IdP needs the public cert.
- `assertingparty.verification.credentials`: **IdP** public signing cert so the SP can verify Responses/Assertions.
- `assertingparty.singlesignon.sign-request: true`: instructs Spring to emit signed requests matching IdP config.
- SP `entity-id` differs from IdP `assertingparty.entity-id`.
- `acs.location` must match the public HTTPS URL, not an internal pod URL.
- `registrationId=corp` is an internal key; it is not itself a trusted entityID.

**Version note:** API/property names have changed across Spring Boot/Security releases. **Do not copy a Spring Security 5.x snippet and assume Spring Security 7.x compatibility**; use the BOM and inspect Spring Boot configuration metadata/Javadoc. Do not mix legacy `identityprovider` properties with `assertingparty` on newer releases.

## 13. Declaring the Dependency and SecurityFilterChain

Add the appropriate dependency to the Spring Boot Maven project:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

OpenSAML artifacts may require the Shibboleth repository per the Spring Security guide for your BOM. Do not manually hardcode mixed OpenSAML generations and Spring Security dependency versions.

A basic `SecurityFilterChain`:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasAuthority("ROLE_ADMIN")
                .anyRequest().authenticated())
            .saml2Login(withDefaults())
            .saml2Metadata(withDefaults());
        return http.build();
    }
}
~~~

**This is a project-level class and does not compile standalone with plain JDK.** It depends on Spring/SAML, trusted registrations, and metadata. `/admin/**` is illustrative only; `ROLE_ADMIN` requires server-side mapping and object-level authorization rather than being taken blindly from an Assertion.

**Important:** when customizing `SecurityFilterChain`, preserve the SAML filters/ACS matchers and protect login endpoints per the framework. Never disable CSRF system-wide just because the IdP needs to POST to the ACS; evaluate and configure per the Spring Security SAML2 profile without exempting business POST routes from CSRF.

## 14. Published SP Metadata and Out-of-Band Verification

With `saml2Metadata(withDefaults())` enabled, Spring Security can serve SP metadata at:

~~~text
https://portal.example.test/saml2/metadata/corp
https://portal.example.test/saml2/service-provider-metadata/corp
~~~

Verify the metadata includes:
- SP `entityID=urn:portal:sp:corp`.
- `SPSSODescriptor` and `AssertionConsumerService` with the right public ACS/binding.
- `KeyDescriptor use="signing"` with the **SP signing certificate**.
- `KeyDescriptor use="encryption"` with the **SP encryption certificate** if published completely.
- `AuthnRequestsSigned` matching policy.
- No private keys.
- Only approved public endpoints; no leaked internal host/HTTP port.

**Do not treat metadata reachability as proof of trustworthiness.** The IdP admin must verify source/certificate fingerprints/ownership out-of-band. When rotating the SP encryption certificate, synchronize metadata with the IdP before the IdP starts encrypting with the new cert, or maintain approved overlapping decryption keys.

## 15. IdP Metadata vs. SP Metadata

Comparison table:

| IdP Metadata | SP Metadata |
| --- | --- |
| `IDPSSODescriptor` | `SPSSODescriptor` |
| IdP entityID | SP entityID |
| IdP SSO service endpoint | SP ACS endpoint |
| IdP signing verification certificates | SP request-signing certificates |
| IdP binding/signature requirements | SP declaration of signed AuthnRequests |
| IdP logout endpoints | SP logout endpoints |
| May include encryption info for the IdP | SP encryption certificates for the IdP |

**Never register every certificate as a "shared trusted key".** Each key is bound to a purpose, entityID, registration, algorithm, and owner. With two IdPs `corp` and `partner`, never verify a Corp Assertion with Partner's cert simply because they share a `kid`/CN.

## 16. Using the RelyingPartyRegistration Java API When Needed

In the Spring Security Java DSL, the core concepts are:
- `RelyingPartyRegistration.withRegistrationId("corp")`.
- `entityId("urn:portal:sp:corp")`.
- `assertionConsumerServiceLocation("https://portal.example.test/login/saml2/sso/corp")`.
- `signingX509Credentials(...)` with `Saml2X509Credential.signing(spPrivateKey,spCert)`.
- `decryptionX509Credentials(...)` with `Saml2X509Credential.decryption(spPrivateKey,spCert)`.
- `assertingPartyMetadata(...)` with `entityId("urn:corp:idp")`, `singleSignOnServiceLocation(...)`, `verificationX509Credentials(...)`, and `wantAuthnRequestsSigned(true)`.
- `InMemoryRelyingPartyRegistrationRepository` or a dynamic repository backed by trusted metadata.

**Fragment** example, with credential objects loaded from a verified secret store/certificate store:

~~~java
RelyingPartyRegistration rp =
    RelyingPartyRegistration.withRegistrationId("corp")
        .entityId("urn:portal:sp:corp")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/corp")
        .signingX509Credentials(keys ->
            keys.add(spRequestSigningCredential))
        .decryptionX509Credentials(keys ->
            keys.add(spAssertionDecryptionCredential))
        .assertingPartyMetadata(party -> party
            .entityId("urn:corp:idp")
            .singleSignOnServiceLocation(
                "https://idp.corp.test/saml/sso")
            .wantAuthnRequestsSigned(true)
            .verificationX509Credentials(keys ->
                keys.add(corpIdpVerificationCredential)))
        .build();
~~~

**Not runnable standalone**: requires Spring Security SAML types, `Saml2X509Credential` built from proper keys and X.509 certs, imports, and `@Configuration`. This separates **SP signing/decryption** from **IdP verification** while still requiring policy validators.

**Never pass a browser-supplied metadata URI directly into `fromMetadataLocation`** and auto-trust it. The IdP metadata source must be approved; signing key rotation requires change control.

## 17. Verifying AuthnRequest Is Actually Signed

Do not just look at `sign-request: true`. Inspect the artifact on the wire:

1. GET `/saml2/authenticate/corp` (initiating session).
2. Spring generates a unique `AuthnRequest.ID` and stores the request for `InResponseTo` correlation.
3. The HTTP Redirect Location to the IdP contains `SAMLRequest`, optionally `RelayState`; when Redirect signing is active, `SigAlg` and `Signature` must be present.
4. Use a test IdP trusting the exact **SP signing certificate** to verify the query signature; modified SAMLRequest/RelayState must fail.
5. If using POST request binding, verify the XML Signature on AuthnRequest with the IdP validation library.
6. SP `Issuer` matches entityID; `Destination` matches IdP SSO URL.
7. `AssertionConsumerServiceURL` matches the registered HTTPS ACS.
8. The IdP rejects unsigned requests when policy requires signing.
9. Old requests cannot be reused after callback; test replay/expiry.
10. Do not log raw SAMLRequest/RelayState outside authorized test environments.

**Do not use a simple "base64 decode" tool on a Redirect request, see no `ds:Signature` in the XML, and conclude the request is unsigned.** Redirect binding signatures live in **query parameters**, not inside the XML.

## 18. What Must Be Checked for EncryptedAssertion?

**IdP side must:**
- Use the exact **SP public encryption certificate** from approved SP metadata.
- Select XML Encryption algorithms compliant with interoperability and security policy.
- Sign the Assertion or Response per the contract **actually verified by the RP**.
- Preserve Response Destination / Assertion Recipient / Audience / InResponseTo.
- Avoid sending sensitive Attributes outside the assertion when confidentiality is required by policy.

**SP side must:**
- Select the right `RelyingPartyRegistration`.
- Load the matching **SP decryption private key** and cert.
- Decrypt EncryptedAssertion, EncryptedAttribute, or EncryptedID via the OpenSAML/Spring strategy.
- Verify valid SAML signature(s), with the key belonging to the right IdP registration.
- Validate all protocol constraints; never accept an assertion solely because decryption succeeded.
- Prevent XML attacks, oversized payloads, replay, and decrypt-oracle diagnostics.
- Avoid logging plaintext NameID/attributes after decryption.

**If the IdP uses an older certificate after rotation:** the SP may temporarily keep old decryption credentials within an approved overlap window to decrypt in-flight assertions; however, a **compromised key** must follow incident protocol rather than being kept indefinitely.

## 19. Encryption vs. XML Signature vs. TLS

| Protection | Target | Risk Mitigated | Does Not Replace |
| --- | --- | --- | --- |
| AuthnRequest signature | SP → IdP message | Request forgery/tampering per binding | Assertion signature |
| Response/Assertion signature | IdP → SP assertion/response | SAML claim forgery/alteration | Recipient/Audience/Replay |
| Assertion encryption | Identity attribute contents | NameID/attribute exposure in transit | IdP authentication & authorization |
| TLS HTTPS | HTTP endpoints/browser transit | MitM/credential/cookie leakage | SAML XML signature |
| Replay cache + InResponseTo | Transaction/session | Replay/login fixation | Cryptographic validation |
| SP/IdP entityID + audience/recipient | Protocol context | Token/assertion meant for wrong party | Local tenant permissions |

**Cryptography solves only part of the problem:** a validly signed assertion from IdP A **must not be accepted** at a tenant/registration trusting only IdP B, and an EncryptedAssertion meant for SP A **must not be accepted** at SP B even if keys are shared.

## 20. Response.Destination: Which Endpoint Is Allowed to Receive It?

Valid example:

~~~xml
<samlp:Response
  Destination="https://portal.example.test/login/saml2/sso/corp"
  InResponseTo="_req901">
  <!-- Signed or encrypted content according to agreed profile -->
</samlp:Response>
~~~

`Destination` is the target URL to which the IdP sends the Response. The SP must compare it against the configured/valid ACS URL for the registration and binding—not merely an approximate hostname or prefix.

**Negative cases:**
- Response issued for `https://other.example.test/login/saml2/sso/corp`.
- Same host but wrong registration path `/partner`.
- HTTP scheme instead of HTTPS.
- Wrong port/proxy/public origin.
- IdP response with empty `Destination` when required by profile.
- Response delivered to endpoint A while `Destination` names endpoint B.

**Proxy note:** a Spring deployment behind a load balancer may internally see `http://app:8080`. Configure trusted forwarded headers / `ForwardedHeaderFilter` or equivalent proxy settings, **never accepting arbitrary client-supplied `Host`/`X-Forwarded-Host` headers** to "fix" Destination mismatches.

## 21. SubjectConfirmationData.Recipient: Who Is Confirmed as the Recipient?

In an Assertion, bearer `SubjectConfirmationData` typically carries `Recipient` set to the ACS URL:

~~~xml
<saml:SubjectConfirmation Method=
    "urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_req901"
      Recipient="https://portal.example.test/login/saml2/sso/corp"
      NotOnOrAfter="2026-11-07T03:05:15Z"/>
</saml:SubjectConfirmation>
~~~

`Recipient` **is not an email recipient**; it identifies the endpoint receiving the bearer assertion. If Recipient is another application's ACS, the SP must reject it.

**Do not collapse Destination and Recipient into a single check:** Destination sits on Response while Recipient sits inside SubjectConfirmationData; both must match per profile/validation strategy.

An Assertion may contain multiple SubjectConfirmations. The provider must evaluate them according to profile semantics, **never blindly taking the first element and ignoring security constraints**.

## 22. AudienceRestriction: Which SP EntityID Is the Assertion Intended For?

Example:

~~~xml
<saml:Conditions
    NotBefore="2026-11-07T02:59:15Z"
    NotOnOrAfter="2026-11-07T03:05:15Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:portal:sp:corp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Audience** is normally the **SP entityID**, not necessarily the ACS URL. An identity assertion signed by Corp with `Audience=urn:other:sp` cannot be used by Portal.

Evaluate SAML Conditions per specification when multiple `AudienceRestriction` elements exist—do not implement "pass if it contains any audience" when multiple restriction blocks carry cumulative semantics. Delegate to the appropriate OpenSAML provider release and add application validators rather than replacing them with XML string searches.

**Watch out with multiple registrations:** if `corp` and `partner` use two SP entityIDs, never configure a global `trustedAudiences={"all"}`. Audience mapping must belong to the registration.

## 23. InResponseTo and AuthnRequest Correlation

For **SP-initiated SSO**, the SP emits an AuthnRequest with `ID=_req901` and stores the pending transaction in a repository. The Response must reference that ID:

~~~text
Pending:
  session/browser context = S-31
  registrationId          = corp
  AuthnRequest ID         = _req901
  RelayState              = R-901
  expected ACS            = https://portal.example.test/login/saml2/sso/corp
  TTL                     = short, bounded

SAML Response:
  Response.InResponseTo   = _req901
  SubjectConfirmationData.InResponseTo = _req901
  RelayState              = R-901
~~~

**Verify:** the request is still pending, belongs to the right session/context, is neither expired nor consumed, matches the registration, and both response and subject confirmation match. If another tab issues request B and overwrites A depending on the repository, response A must not be "forgiven" simply because its signature is valid.

**IdP-initiated/unsolicited SAML** has no AuthnRequest to correlate. Accept it only under an explicitly approved policy with signature/issuer/recipient/audience/time/replay/login-CSRF checks. Never use unsolicited mode as a fallback to bypass pending-session errors.

## 24. RelayState and Login CSRF

`RelayState` is a binding parameter typically holding an opaque handle for the request/return URL, not an identity credential. OASIS SAML HTTP Redirect/POST bindings specify an 80-byte limit per profile. In signed Redirect bindings, RelayState may be part of the signed query; in POST bindings, the XML signature does not by default sign the RelayState form field.

Tests:
- RelayState matches the issued value.
- Change one byte → deny/missing pending.
- Use flow B's RelayState with Response A → deny.
- Omit RelayState → fail closed if the repository depends on it.
- Use raw RelayState as an external redirect URL → block open redirect.
- Session cookie omitted on cross-site POST (SameSite/Domain/Path) → do not silently accept login.

**Security trade-off:** Spring defaults to storing AuthnRequests in `HttpSessionSaml2AuthenticationRequestRepository`, providing natural browser-session binding. A cache repository keyed by RelayState enables multiple pending requests/cross-site scenarios in some versions, but **does not by itself prove the callback belongs to the initiating browser**, increasing login fixation risk without extra constraints.

## 25. Timestamps, Replay, and SubjectConfirmation

Beyond cryptography and recipient, verify:
- `IssueInstant` is valid per policy.
- `Conditions.NotBefore` and `NotOnOrAfter`, with bounded clock skew.
- `SubjectConfirmationData.NotOnOrAfter` for bearer confirmation.
- `AuthnInstant`, `SessionNotOnOrAfter`, and `SessionIndex` per use case.
- `Response.ID` and `Assertion.ID` have not been replayed.
- `InResponseTo` matches the pending request.
- Recipient/Audience match the registration and current public ACS.
- Exact IdP entityID and signing credentials.
- Session cookie/relay binding unaltered.
- Local account active, tenant membership, and role mapping after authentication.

**Never widen clock skew substantially just to mask NTP drift.** A signed Assertion replayed within its TTL is still a replay, not a valid fresh login.

## 26. Spring: Response Processing Path and Decryption

At the ACS, Spring Security:
1. `Saml2WebSsoAuthenticationFilter` receives the SAMLResponse (typically POST).
2. `Saml2AuthenticationTokenConverter` resolves the trusted `RelyingPartyRegistration` and pending request.
3. `OpenSaml5AuthenticationProvider` (per Spring Security 7.x reference) handles decryption/validation using IdP verification credentials and SP decryption credentials.
4. If EncryptedAssertion/EncryptedAttribute/EncryptedID is present, decryption strategies inside the provider process them by position.
5. OpenSAML verifies signature/issuer/conditions/confirmation per policy/version.
6. The Response becomes `Saml2Authentication` with verified principal/attributes.
7. Application authorities/tenant policy are applied after SAML validation.
8. Failures must produce no authenticated SecurityContext.

**Earlier versions:** Spring Security 6.x may use `OpenSaml4AuthenticationProvider` or other APIs; do not use newer names if your BOM does not support them yet. Spring docs distinguish **Response elements decrypter** (EncryptedAssertion) from **Assertion elements decrypter** (EncryptedAttribute/EncryptedID) because decryption can affect XML signature integrity.

## 27. Why Should You Not Arbitrarily Decrypt Before Verifying Signatures?

A Response may:
- Be **signed by the IdP at the Response level**, with an EncryptedAssertion inside.
- Contain a **signed-then-encrypted Assertion**, with no outer Response signature.
- Have both a signed Response and a signed Assertion.
- Encrypt only an Attribute/NameID inside an Assertion carrying an XML Signature.

If a custom handler:
1. Parses XML unprotected and locates EncryptedAssertion elements.
2. Decrypts all nested elements immediately.
3. Verifies signatures on another node.
4. Extracts NameID from an unsigned XML element.

...it can introduce **XML Signature Wrapping** or alter canonicalization of signed XML. For a signed assertion containing EncryptedAttribute, Spring docs emphasize **not decrypting encrypted Assertion elements before signature verification if doing so breaks the signature**.

**Solution:** use the standard OpenSAML provider, preserve profile-compliant validation/decryption order, extend hooks only when truly necessary, and require signed negative fixtures. Never use regex or hand-rolled XML DOM parsing to construct Authentication.

## 28. A Failure Case: "Decrypts Successfully" Yet Wrong Recipient

Suppose an IdP issues an encrypted assertion for `urn:portal:sp:corp`. Reusing the same private decryption key at another SP lets application B open the ciphertext. Yet `Recipient` is:

~~~text
https://portal.example.test/login/saml2/sso/corp
~~~

While B runs at:

~~~text
https://billing.example.test/login/saml2/sso/billing
~~~

**B must reject** because the bearer assertion was issued for Portal's ACS, even though decryption and signature verification succeeded. Checking B's `AudienceRestriction` (e.g., `urn:billing:sp`) adds an independent layer.

This prevents **confused deputy / assertion substitution**. Sharing a key never authorizes sharing assertions across SPs.

## 29. Multi-IdP and Multi-Tenant: Key Isolation

Example:

| Registration | Trusted IdP | SP entityID | ACS | Tenant Policy |
| --- | --- | --- | --- | --- |
| `corp` | `urn:corp:idp` | `urn:portal:sp:corp` | `/login/saml2/sso/corp` | North |
| `partner` | `urn:partner:idp` | `urn:portal:sp:partner` | `/login/saml2/sso/partner` | South |

**Never pick a registration solely from an unverified XML Issuer and treat it as proof of trust.** An unverified XML Issuer can serve as a candidate hint; Spring's resolver must select from the approved repository, and OpenSAML then verifies using the corresponding IdP keys and recipient/audience.

One IdP may serve multiple tenants or one tenant may use multiple IdPs; real mappings can be many-to-many, but **tenant access is application authorization**—never infer it automatically from registration paths or Assertion group names.

**Never auto-link identical NameIDs/emails across Corp and Partner**; external identity namespaces must combine verified IdP entityID and stable subject.

## 30. Reverse Proxy, URL Rewriting, and ACS Mismatch

A real-world pitfall:

~~~text
Public URL:
  https://portal.example.test/login/saml2/sso/corp

Ingress -> internal backend:
  http://spring-app-01:8080/login/saml2/sso/corp

IdP Destination/Recipient:
  https://portal.example.test/login/saml2/sso/corp
~~~

If Spring computes base URLs from the internal request or trusts attacker-supplied forwarded headers, it easily produces wrong `Destination`/`Recipient` values or open redirects.

Mitigations:
- Declare the exact public ACS and SP entityID in the trusted registration.
- Have the proxy set Forwarded/X-Forwarded-* after **stripping client-sent headers**.
- Trust forwarded headers only from approved gateways, and whitelist public hosts.
- Enable end-to-end HTTPS or approved TLS termination, and protect session cookies.
- Do not delegate full validation to unchecked `request.getServerName()`.
- Test localhost/staging/prod domains separately with per-environment certs/metadata.
- If the IdP holds an old ACS URL, update approved metadata/partner config rather than creating wildcard recipients.
- Never change the ACS path only in the Spring filter while forgetting metadata/IdP.
- Verify query parameters and RelayState survive URL encoding/proxy traversal intact.

**Never fix URL errors by disabling Destination/Recipient validation.** A URL mismatch is an integration config defect, not a SAML check to relax.

## 31. Notes on X.509 Certificate Validity and Trust

SAML signing certificates are commonly used as **pinned verification credentials** in federation, unlike the TLS PKIX trust model. Depending on vendor/profile, a self-signed cert may be trusted when explicitly registered via metadata/trust processes, but you must never **auto-trust an arbitrary cert embedded in SAMLResponse**.

Verify:
- The certificate belongs to the **right IdP entityID/registration**.
- Key type/length and signature algorithm comply with policy.
- Cert/key rotation has an owner, overlap window, and old-key removal.
- Metadata comes from a trusted source with integrity checks and recorded fingerprints.
- The SP signing cert has its matching private key in the secret store.
- The SP decryption private key matches the encryption cert the IdP uses.
- Never borrow IdP private keys to decrypt SP Assertions.
- Never enable legacy cryptography to paper over unresolved incompatibility.
- If a private key leaks, run separate incident response rather than treating it as routine rotation.

**TLS certificate expiry** and **SAML verification certificate trust** may have independent lifecycles; do not lump every error under "certificate expired".

## 32. Rotation for SP Signing Key and SP Encryption Key

**SP signing key rotation:**
1. Generate a new signing key pair in the secret store.
2. Register the new public signing cert with the IdP out-of-band/via metadata.
3. Verify the IdP allows overlapping keys and signed AuthnRequests from the new key.
4. Switch the Spring signing credential via canary rollout.
5. Test that the IdP accepts newly signed requests and rejects unsigned/wrong-signer requests.
6. Remove the old key once safe and record audit logs.

**SP encryption key rotation:**
1. Generate a new private/public encryption key pair.
2. Ensure the SP can decrypt with the new key before the IdP begins encrypting with it.
3. Publish updated SP metadata and coordinate the IdP switchover to the new encryption cert.
4. For in-flight encrypted assertions using the old cert, retain the old decryption credential only during the approved overlap window.
5. Test both old and new encrypted responses through the real OpenSAML flow.
6. Remove the old key per policy; if compromised, consider rejecting old assertions and forcing reauthentication.

**IdP signing key rotation:** the SP updates `assertingparty.verification.credentials` from a trusted source; if a key is suspected compromised, **do not keep the old key trusted** merely to avoid an outage.

## 33. Deceptively Working but Dangerous Configurations

| Configuration / Defect | Why It Is Dangerous | Expected Outcome |
| --- | --- | --- |
| IdP expects signed request but SP lacks signing key | Login fails or IdP policy bypassed | IdP rejects / clear config error |
| SP signs with wrong account/key | IdP does not trust request signer | Reject |
| Redirect signature uses wrong canonical query | Signature mismatch | Reject |
| POST request XML unsigned when IdP requires signed | SP identity unproven | Reject |
| IdP encrypts with old cert whose private key SP deleted | Cannot decrypt | Fail closed |
| SP puts IdP public cert in decryption config | No matching private key | Fail closed |
| SP uses signing cert as IdP verification cert | Wrong signing party | Reject |
| IdP sends encrypted but unsigned assertion/response | Confidentiality does not provide authenticity | Reject per signature policy |
| Valid IdP signature but wrong Recipient | Assertion meant for another SP | Reject |
| Valid IdP signature but wrong Audience | Assertion meant for another SP | Reject |
| Valid RelayState but wrong InResponseTo | Response does not belong to request | Reject |
| XML Signature Wrapping | Reads unsigned subject/roles | Reject |
| Same NameID from different IdPs | Identity collision | Separate namespaces |
| Shared SP encryption private key across tenants | Larger blast radius | Isolate keys/policies |
| Spoofed Host/X-Forwarded-Host | Wrong ACS validation/routing | Reject untrusted headers |
| Overly wide clock skew | Expands replay window | Bound per policy |
| Missing assertion replay cache | Single signed assertion can be replayed | Reject repeats |

## 34. Layered Integration Test Scenarios

**Layer 1 — Registration configuration:**
- Verify `corp` has SP signing credential, decryption credential, and Corp IdP verification credential for their proper purposes.
- SP metadata publishes both public certs and exact ACS/entityID.
- Missing key file / invalid PEM → controlled startup or authentication failure, no insecure fallback.

**Layer 2 — AuthnRequest signing:**
- Capture Redirect Location / POST request from the SP.
- Test IdP verifies valid signature; tampered request/RelayState → reject.
- Verify signature algorithm allowlist and `Issuer/Destination/ACS`.

**Layer 3 — Encrypted signed assertion:**
- Test IdP issues EncryptedAssertion using SP public encryption cert.
- SP decrypts with private key and verifies Corp's signed Response/Assertion.
- Wrong private key, wrong algorithm, unsigned claim, corrupted ciphertext → deny.

**Layer 4 — Protocol recipient and correlation:**
- Valid Destination/Recipient/Audience/Issuer/InResponseTo → pass.
- Vary each field individually to an invalid value and re-sign with a valid test IdP key to prove **validation logic**, not just signature tampering.
- Expired Conditions, replayed Assertion ID, missing pending request → deny.

**Layer 5 — Business authorization:**
- Verified NameID → right local account; roles/tenant mapped server-side.
- Same email from Partner IdP does not auto-link to Corp account.
- Signed Assertion with admin group lacking authorized mapping → no `ROLE_ADMIN`.

## 35. Creating Signed/Encrypted Test Fixtures Properly

**Do not edit a signed SAMLResponse in a text editor and expect it to pass signature checks**, because modifying XML invalidates the signature before Recipient/Audience checks even run. Instead, using a test IdP with a test signer key:
1. Create a fresh AuthnRequest for the test session.
2. Select the test variant (wrong Recipient, wrong Audience, wrong InResponseTo, wrong issuer...).
3. Build the Assertion/Response for that variant.
4. Sign with the **exact test IdP signing key** after setting the fields.
5. Encrypt the Assertion with the **test SP encryption certificate**.
6. POST to the ACS with matching cookies/RelayState.
7. Assert the failure category and that **no authenticated SecurityContext exists**.
8. Re-run the happy path with the same signer/decryption settings and correct recipient to prove the difference.
9. Test duplicate/replayed IDs and different registrations/tenants with fresh sessions.
10. Never use real production keys, assertions, or NameIDs.

For invalid signature tests, intentionally alter bytes **after signing** or use a wrong signer. For recipient validation tests, keep the cryptographic signature valid while changing Recipient. Without separating these cases, a test can PASS via signature failure without **actually testing recipient validation**.

## 36. Browser E2E: Signed Request and Encrypted Response

A reliable browser E2E test requires:
- A fresh browser session with no stale Spring session.
- SP `GET /saml2/authenticate/corp` producing a signed AuthnRequest.
- Test IdP configured to trust SP signing cert and sign+encrypt responses.
- HTTP POST callback to the public ACS URL.
- Browser sending the session cookie required for the pending AuthnRequest; verify SameSite/Secure/Domain/Path if applicable.
- SP verifying signature, decrypting Assertion, checking recipient/audience.
- Asserting verified principal and local `GrantedAuthority`.
- Checking logout/reauthentication, replay, and session fixation.
- Checking malformed/oversized XML, invalid bindings, and redirect errors.
- Testing across browsers/proxy routes/IdP accounts/tenants where applicable.
- Not judging success solely by HTTP 302 (error handlers also redirect).
- Not sharing HAR files containing raw signed assertions/cookies/trust secrets outside the security test team.

**Never disable CSRF globally to handle the POST ACS**, nor disable signature checks to "make tests pass". Use standard Spring Security and OpenSAML integration support.

## 37. Runnable Java 17: Practicing Signatures, Ciphertext Confidentiality, and Recipient Policy

To understand all three boundaries in one runnable program, the example below uses **JDK 17 JCA/JCE**:

- RSA/SHA256 signs and verifies an **illustrative string** analogous to Redirect signed input.
- AES-GCM encrypts/decrypts simulated data; the integrity tag detects AAD changes.
- Policy checks exact Issuer, Destination, Recipient, Audience, InResponseTo, Conditions, and replay.

**Important limitations:** this program **does not produce real SAML XML Signatures/Redirect bindings**, does not use XML Encryption or SAML certificate validation, and does not use RSA-OAEP to wrap an AES key for IdP→SP. **The AES key resides in the same program**, unlike real key transport. The signature/decryption booleans in the policy model must come *after* verification by the OpenSAML provider. **Do not copy this program as a Spring AuthenticationProvider**.

Create **`SamlSigningEncryptionRecipientDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SamlSigningEncryptionRecipientDemo {

    static final String SP = "urn:portal:sp:corp";
    static final String IDP = "urn:corp:idp";
    static final String ACS =
            "https://portal.example.test/login/saml2/sso/corp";
    static final String REQUEST_ID = "_req901";

    record Evidence(boolean signatureValid, boolean decrypted,
                    String issuer, String destination, String recipient,
                    String audience, String inResponseTo,
                    boolean timeValid, boolean unused) {}

    static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] sign(PrivateKey key, String data)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(key);
        s.update(bytes(data));
        return s.sign();
    }

    static boolean verify(PublicKey key, String data, byte[] signed)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initVerify(key);
        s.update(bytes(data));
        return s.verify(signed);
    }

    static byte[] encrypt(SecretKey key, byte[] iv, String plain, String aad)
            throws GeneralSecurityException {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        c.updateAAD(bytes(aad));
        return c.doFinal(bytes(plain));
    }

    static String decrypt(SecretKey key, byte[] iv, byte[] cipher, String aad)
            throws GeneralSecurityException {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        c.updateAAD(bytes(aad));
        return new String(c.doFinal(cipher), StandardCharsets.UTF_8);
    }

    static String validate(Evidence e) {
        if (!e.signatureValid()) {
            return "DENY_IDP_SIGNATURE";
        }
        if (!e.decrypted()) {
            return "DENY_DECRYPTION";
        }
        if (!IDP.equals(e.issuer())) {
            return "DENY_ISSUER";
        }
        if (!ACS.equals(e.destination())) {
            return "DENY_DESTINATION";
        }
        if (!ACS.equals(e.recipient())) {
            return "DENY_RECIPIENT";
        }
        if (!SP.equals(e.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!REQUEST_ID.equals(e.inResponseTo())) {
            return "DENY_IN_RESPONSE_TO";
        }
        if (!e.timeValid()) {
            return "DENY_CONDITIONS";
        }
        if (!e.unused()) {
            return "DENY_REPLAY";
        }
        return "PASS_PROTOCOL_GATES";
    }

    static Evidence evidence(boolean sign, boolean decrypted,
            String issuer, String destination, String recipient,
            String audience, String requestId, boolean time, boolean unused) {
        return new Evidence(sign, decrypted, issuer, destination,
                            recipient, audience, requestId, time, unused);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair signingPair = generator.generateKeyPair();

        String redirectInput =
                "SAMLRequest=encoded&RelayState=R-901&SigAlg=rsa-sha256";
        byte[] signed = sign(signingPair.getPrivate(), redirectInput);
        System.out.println("SP AuthnRequest signature: "
                + verify(signingPair.getPublic(), redirectInput, signed));
        System.out.println("Changed RelayState signature: "
                + verify(signingPair.getPublic(),
                        "SAMLRequest=encoded&RelayState=R-X&SigAlg=rsa-sha256",
                        signed));

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128);
        SecretKey aes = keyGenerator.generateKey();
        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        String plaintext = "NameID=alice|aud=urn:portal:sp:corp";
        byte[] ciphertext = encrypt(aes, iv, plaintext, SP);
        System.out.println("Encrypted assertion demo: "
                + plaintext.equals(decrypt(aes, iv, ciphertext, SP)));

        try {
            decrypt(aes, iv, ciphertext, "urn:other:sp");
            System.out.println("Wrong encryption context: UNEXPECTED_ACCEPT");
        } catch (GeneralSecurityException rejected) {
            System.out.println("Wrong encryption context: DENY_GCM_AUTH");
        }

        Evidence good = evidence(true, true, IDP, ACS, ACS,
                                 SP, REQUEST_ID, true, true);
        System.out.println("Protocol valid: " + validate(good));
        System.out.println("Missing IdP signature: " + validate(evidence(
                false, true, IDP, ACS, ACS, SP, REQUEST_ID, true, true)));
        System.out.println("Cannot decrypt: " + validate(evidence(
                true, false, IDP, ACS, ACS, SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Issuer: " + validate(evidence(
                true, true, "urn:partner:idp", ACS, ACS,
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Destination: " + validate(evidence(
                true, true, IDP, "https://other.test/acs", ACS,
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Recipient: " + validate(evidence(
                true, true, IDP, ACS, "https://other.test/acs",
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Audience: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                "urn:other:sp", REQUEST_ID, true, true)));
        System.out.println("Wrong InResponseTo: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, "_req-other", true, true)));
        System.out.println("Expired Assertion: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, REQUEST_ID, false, true)));
        System.out.println("Replayed Assertion: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, REQUEST_ID, true, false)));
    }
}
~~~

Run with **JDK 17 or higher**:

~~~bash
javac SamlSigningEncryptionRecipientDemo.java
java SamlSigningEncryptionRecipientDemo
~~~

**Exact stdout:** RSA/AES keys and GCM IV are generated randomly each run, yet the program **never prints keys/ciphertext**—only boolean checks and deterministic decisions.

~~~text
SP AuthnRequest signature: true
Changed RelayState signature: false
Encrypted assertion demo: true
Wrong encryption context: DENY_GCM_AUTH
Protocol valid: PASS_PROTOCOL_GATES
Missing IdP signature: DENY_IDP_SIGNATURE
Cannot decrypt: DENY_DECRYPTION
Wrong Issuer: DENY_ISSUER
Wrong Destination: DENY_DESTINATION
Wrong Recipient: DENY_RECIPIENT
Wrong Audience: DENY_AUDIENCE
Wrong InResponseTo: DENY_IN_RESPONSE_TO
Expired Assertion: DENY_CONDITIONS
Replayed Assertion: DENY_REPLAY
~~~

**Why it works accurately:** `Signature` verification checks identical bytes and public key; altering RelayState changes the bytes, returning `false`. AES-GCM uses consistent key, IV, and AAD so decryption succeeds; altering AAD invalidates the authentication tag and throws a classified exception. The policy model checks **each constraint independently**. This **only illustrates security properties**, not a production SAML protocol stack.

## 38. Testing the Java Program and Traps When Applying It

If you change `SP`, `ACS`, or `REQUEST_ID` in the demo, update fixtures accordingly; otherwise you will see `DENY_AUDIENCE`, `DENY_RECIPIENT`, or `DENY_IN_RESPONSE_TO`. This highlights that the validator needs **server-configured expected values**, never values pulled from the assertion itself where an attacker can control them.

**Never turn `boolean signatureValid` or `boolean decrypted` into browser-supplied parameters.** In a real application, they are produced only by OpenSAML when verifying signatures/certs/decryption against a trusted registration. The JCA model also does not cover:
- XML ID references and canonicalization.
- XML signature wrapping.
- RSA-OAEP content key transport.
- SAML NameID/subject confirmation semantics.
- IdP signature placement/profiles.
- Clock skew and distributed replay caches.
- Session/RelayState/IdP-initiated flow security.
- Binding-specific encodings.

Therefore, the Java exercise **serves to build conceptual understanding, not to authenticate SAML in production**.

## 39. Layered Diagnostic Error Table

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| IdP reports unsigned request | SP lacks signing private key or sign-request is false | Configure signing, check IdP policy |
| IdP reports invalid AuthnRequest signature | Wrong SP signing cert, encoding, SigAlg | Check binding, registered cert, and signature |
| IdP reports unknown SP entityID | Issuer/metadata not registered | Synchronize SP metadata |
| IdP sends plain Assertion | IdP encryption policy disabled | Configure encryption with SP cert, test |
| SP reports cannot decrypt EncryptedAssertion | Wrong private key, cert rollover, or algorithm | Match SP decryption credential with IdP encryption cert |
| Decryption succeeds but login fails | Wrong signature/issuer/recipient/audience/time | Inspect validation category |
| Invalid Signature/Checksum | IdP signing cert changed or XML altered | Check trust metadata/key rotation |
| Verified with Partner key on Corp flow | Registration confusion | Key isolation/strict issuer |
| `Destination` mismatch | ACS URL differs from public origin, reverse proxy | Fix ACS/forwarded headers/IdP metadata |
| `Recipient` mismatch | SubjectConfirmationData targets another SP | Fix IdP recipient or reject |
| `AudienceRestriction` mismatch | Wrong SP entityID | Fix exact audience, no wildcards |
| `InResponseTo` mismatch | Missing/overwritten pending AuthnRequest | Check session/repository/RelayState |
| Callback missing HTTP session | SameSite/cookie TTL/load balancer | Test browser/session store |
| Expired assertion | IdP/SP clock drift, Conditions TTL | Sync NTP, check policy |
| Replayed assertion | Assertion ID/Response ID or AuthnRequest reused | Reject, inspect replay cache |
| `ROLE_ADMIN` granted mistakenly | Faulty attribute-to-authority mapping | Restrict privileged roles via allowlist |
| Login passes via HTTP 302 yet anonymous | Failure handler redirect | Assert Authentication/subject |
| Missing user NameID after encrypted assertion | Decryption/NameID format/Attribute handling | Inspect decrypted signed assertion and profile |

**Never debug by printing private keys, raw assertions, or cookies.** Use correlation IDs, hashed request/response IDs, cert fingerprints, registrationId, failure category, and test data.

## 40. Security QA Matrix — Request Signing and Encryption

| # | Test Case | Result |
| --- | --- | --- |
| 01 | Signed Redirect AuthnRequest, valid SP cert | IdP accepts |
| 02 | Unsigned request when IdP requires signing | IdP rejects |
| 03 | Redirect signature signed with wrong SP key | IdP rejects |
| 04 | Alter SAMLRequest bytes after signing | Verification fails |
| 05 | Alter RelayState in signed query | Verification fails |
| 06 | Alter SigAlg after signing | Verification fails |
| 07 | Redirect signature with wrong canonicalization | Verification fails |
| 08 | POST binding with only Redirect SigAlg | Not treated as signed XML |
| 09 | Valid signed POST XML AuthnRequest | IdP accepts per policy |
| 10 | Wrong SP Issuer entityID | IdP rejects |
| 11 | AuthnRequest Destination points to wrong IdP endpoint | IdP rejects |
| 12 | Wrong AuthnRequest ACS | IdP rejects or policy error |
| 13 | IdP encrypts with SP public encryption cert | SP decrypts |
| 14 | IdP encrypts with another SP's cert | SP rejects/cannot decrypt |
| 15 | SP has only public cert, missing decryption private key | Cannot decrypt |
| 16 | SP key rotation while IdP still uses old cert past overlap | Reject/controlled failure |
| 17 | EncryptedAssertion ciphertext tampered | Decrypt/integrity fails |
| 18 | Decrypted assertion yet unsigned | Reject per signature policy |
| 19 | Signed Assertion with wrong IdP certificate | Reject |
| 20 | Valid signed+encrypted Assertion | Passes when protocol checks succeed |

## 41. Security QA Matrix — Recipient, Replay, and Tenant

| # | Test Case | Result |
| --- | --- | --- |
| 21 | Response Destination matches ACS | Passes check |
| 22 | Destination points to another SP | Reject |
| 23 | Destination uses http instead of public HTTPS | Reject |
| 24 | Destination matches host but wrong registrationId | Reject |
| 25 | SubjectConfirmationData Recipient matches | Passes check |
| 26 | Recipient points to another app's ACS | Reject |
| 27 | Valid Recipient but wrong Audience | Reject |
| 28 | AudienceRestriction contains right SP entityID | Pass |
| 29 | Audience contains only ACS URL instead of SP entityID | Reject per profile |
| 30 | Audience belongs to Partner SP during Corp flow | Reject |
| 31 | InResponseTo matches pending AuthnRequest | Passes check |
| 32 | InResponseTo points to request B | Reject |
| 33 | Response InResponseTo matches but SubjectConfirmationData wrong | Reject |
| 34 | Missing pending AuthnRequest in SP-initiated flow | Fail closed |
| 35 | Missing RelayState when repository requires it | Reject |
| 36 | Replay Assertion ID after success | Reject |
| 37 | Expired Response/Assertion NotOnOrAfter | Reject |
| 38 | Signed by Corp, XML issuer claims Partner | Reject |
| 39 | Valid signed assertion but wrong NameID linking | No auto-account-link |
| 40 | Verified user not in tenant North | 403 |
| 41 | Verified user with admin group not in allowlist | Admin not granted |
| 42 | Callback via untrusted Host/X-Forwarded-Host | Does not alter expected recipient |
| 43 | Assertion signature wrapping | Does not use unsigned subject |
| 44 | Malformed/oversized/XXE XML | Controlled rejection |
| 45 | Decryption succeeds but IdP signing cert revoked | Reject |
| 46 | SP encryption private key exposed | Incident response/rotate/revoke |
| 47 | Two login tabs with different request IDs | No mismatched InResponseTo |
| 48 | IdP-initiated SAML when prohibited by policy | Reject |
| 49 | Same NameID from two IdPs | No identity merging |
| 50 | Multi-node concurrent POST replay | At-most-once policy |

**All negative tests must assert no authenticated session is created.** For wrong Recipient/Audience, the fixture must be **validly re-signed by the test IdP**, otherwise you are only testing signature failure.

## 42. Ordered Deployment Runbook

### Phase A — Preparation

1. Lock Spring Boot/Security BOM, OpenSAML generation, and IdP product/version.
2. Create separate test key pairs/certificates for SP signing and encryption.
3. Verify the IdP signing certificate and metadata over an approved channel.
4. Lock SP entityID, IdP entityID, SSO URL, and public HTTPS ACS URL.
5. Lock Redirect/POST request binding, signature requirements, and algorithms.
6. Lock IdP Response vs. Assertion signature policy.
7. Lock encrypted assertion/attribute policy and supported XML Encryption algorithms.
8. Lock clock skew/replay/RelayState/session policy.
9. Create dedicated test IdP users, test tenant, SP local accounts, and role mappings.
10. Verify secret store, private key file permissions, and key rotation owners.

### Phase B — Configuration

1. Update Spring signing/decryption/verification credentials by exact purpose.
2. Set `sign-request: true` when the IdP requires signed AuthnRequests.
3. Publish SP metadata and verify signing/encryption certificates contain no private keys.
4. Register SP metadata on the IdP and enable Response/Assertion sign+encrypt per contract.
5. Verify exact `RelyingPartyRegistration` and URL mappings.
6. Enable default Spring/OpenSAML validation and add profile-specific controls via documented APIs.
7. Verify trusted proxy headers and public ACS.
8. Keep session/RelayState correlation, CSRF policy, and replay cache intact.
9. Verify mapping of verified NameID/groups to local roles/tenant permissions.
10. Enable safe logs/metrics without logging SAMLResponses.

### Phase C — QA and Canary

1. Happy-path login with signed AuthnRequest + signed EncryptedAssertion.
2. Tamper with Redirect signature/RelayState.
3. Wrong SP encryption private key.
4. Wrong IdP signing certificate/issuer.
5. Wrong Destination, Recipient, Audience, and InResponseTo **one field at a time**.
6. Test expired/replayed Assertion.
7. Test browser cross-site POST cookies, session loss, two tabs, and multi-node.
8. Test wrong IdP/tenant/account linking and role escalation.
9. Test signing/decryption key rollover, metadata cache, and old-key removal.
10. Canary by tenant/IdP, monitor failure categories; roll out upon security owner approval.

### Phase D — Operations

1. Monitor cert fingerprints, expiration, private key access, and configuration drift.
2. Monitor Destination/Recipient/Audience/InResponseTo mismatches without relaxing validation to reduce errors.
3. Keep account/tenant authorization server-side.
4. Schedule rotations and staged drills with the IdP.
5. If an IdP signer or SP decryption key leaks, trigger the incident runbook, quarantine trust, and revoke sessions.
6. Review metadata fetch/renewal and cache invalidation.
7. Protect session cookies, KMS/secret vault, and TLS proxy.
8. Re-run the E2E negative matrix after every IdP, DNS, load balancer, cert, or Spring Security upgrade change.
9. Maintain fail-closed behavior on missing credentials or invalid SAML responses.
10. Keep interoperability documentation updated for every distinct registration.

## 43. Selective Observability

Suggested custom metrics to instrument:

| Metric | Meaning |
| --- | --- |
| `saml_authnrequest_signed_total` | Successful request signings per registration |
| `saml_authnrequest_signature_error_total` | Signing key/algorithm errors |
| `saml_encrypted_assertion_total` | Processed SAML encrypted assertions |
| `saml_decryption_failed_total` | Wrong key/ciphertext/policy |
| `saml_idp_signature_failed_total` | Signature/trust key mismatch |
| `saml_destination_mismatch_total` | Response delivered to wrong ACS |
| `saml_recipient_mismatch_total` | Wrong SubjectConfirmationData |
| `saml_audience_mismatch_total` | Assertion targeted wrong SP |
| `saml_inresponseto_mismatch_total` | Request correlation mismatch |
| `saml_replay_rejected_total` | Response/Assertion replay |
| `saml_tenant_denied_total` | Authentication passed but authorization denied |
| `saml_key_rotation_drift_total` | Nodes/IdP metadata drift |
| `saml_authentication_success_total` | Successful authentication from approved source |

**Do not assume Spring provides the metric names above out of the box.** Logs should include correlation ID, registrationId, policy/certificate fingerprint, error code, and node; never include raw SAMLResponse, NameID/PII, decrypted assertions, private keys, session IDs, or sensitive RelayState in logs. Bound cardinality and protect audit access.

## 44. Self-Assessment Questions

**1. Who signs the AuthnRequest?**  
The SP/Relying Party, using the SP private signing key; the IdP verifies with the SP public signing cert.

**2. Who encrypts the Assertion?**  
The IdP, using the SP public encryption certificate; the SP decrypts with the corresponding private key.

**3. Who signs the SAML Response/Assertion?**  
The IdP per profile; the SP verifies with trusted IdP verification credentials.

**4. Once the SP successfully decrypts an assertion, is authentication complete?**  
No; signature/issuer/recipient/audience/time/InResponseTo/replay checks and local authorization are still required.

**5. What is Destination?**  
The target URL receiving the SAML Response, normally the public ACS.

**6. How does Recipient differ from AudienceRestriction?**  
Recipient is the ACS endpoint in SubjectConfirmationData; AudienceRestriction identifies the SP entityID in Conditions.

**7. What is InResponseTo used for?**  
Binding the Response/SubjectConfirmation to the stored AuthnRequest in an SP-initiated flow.

**8. Is the Redirect binding signature always inside the XML?**  
No. It typically appears as `SigAlg`/`Signature` query parameters outside the XML.

**9. What signature type can a POST-binding AuthnRequest use?**  
XML Signature per the protocol/binding profile.

**10. Should the same certificate be used for SP signing and IdP verification?**  
No. Those are two distinct trust directions.

**11. Why not fix a Recipient mismatch by disabling the validator?**  
Because that could accept an assertion issued for another SP, causing confused deputy/account takeover.

**12. Why do reverse proxies easily cause mismatches?**  
The backend may see an internal HTTP host/port different from the public HTTPS ACS, or forwarded headers may be spoofed.

**13. Why can't you test Audience by editing XML after the IdP has signed it?**  
Because the signature breaks; tests must construct the wrong Audience value before the test IdP signs and encrypts.

**14. Can an expired signed SAML assertion be reused?**  
No. Conditions, SubjectConfirmationData timestamps, and replay guards must still pass.

**15. Is the Java 17 demo in this article a SAML implementation?**  
No. It illustrates JCA signatures/AES-GCM and policy gates; Spring/OpenSAML must perform real SAML verification.

## 45. Final QA Checklist

- [ ] AuthnRequest is signed per binding with the right SP signing key.
- [ ] IdP trusts the SP signing certificate and enforces signed requests per policy.
- [ ] SP signing private key is secured and absent from metadata.
- [ ] IdP uses the right SP public encryption certificate for Assertions.
- [ ] SP holds the matching decryption private key; XML Encryption algorithms are approved.
- [ ] IdP signs Response/Assertion per policy; SP verifies with IdP verification credentials.
- [ ] Encryption-only is never used in place of an authentication signature.
- [ ] Signing, decryption, and IdP verification keys are never mixed up.
- [ ] Spring SAML2 registrationId, SP entityID, IdP entityID, and ACS are accurate.
- [ ] Destination, Recipient, and AudienceRestriction are validated independently.
- [ ] Response/SubjectConfirmationData InResponseTo matches the pending AuthnRequest.
- [ ] RelayState and browser session binding are protected.
- [ ] Conditions timestamps, clock skew, and replay validation are enforced.
- [ ] XML Signature Wrapping, XXE, oversized XML, and malformed SAML are rejected.
- [ ] Reverse proxy trusted forwarding, public HTTPS ACS, and cookie policies are correct.
- [ ] Each IdP/tenant has proper registrations/keys/source identity namespaces.
- [ ] NameID/attributes are used only after full protocol validation.
- [ ] Group/GrantedAuthority and tenant/object permissions are enforced by the app.
- [ ] Key rotation and compromised-key removal are rehearsed.
- [ ] Test suites include signed fixtures for wrong Recipient/Audience/InResponseTo.
- [ ] Positive tests prove both authentication and correct local account mapping.
- [ ] Negative tests prove no authenticated SecurityContext is created.
- [ ] Raw SAML assertions, keys, and session cookies are never logged.
- [ ] Monitoring covers mismatch/decryption/signature/replay along with canary rollback.
- [ ] APIs/properties are cross-checked against the actual Spring Boot/Security BOM.

## 46. Conclusion

To take SAML2 SSO practice from "login works" to "login bound to the right trust context", remember:

**SP signs AuthnRequest → IdP verifies request → IdP signs and encrypts Assertion for SP → SP verifies right IdP and decrypts with SP private key → strictly checks Destination + Recipient + AudienceRestriction + InResponseTo + validity window + replay → resolves verified principal → application authorization.**

**Signatures prove origin/integrity under trust**, **encryption protects confidentiality**, and **Destination/Recipient/AudienceRestriction/InResponseTo prove the assertion is meant for the right party and transaction**. No single layer replaces the others.

Spring Security supports signing AuthnRequests via `Saml2WebSsoAuthenticationRequestFilter`/registration signing credentials and decrypting `EncryptedAssertion` via `OpenSaml5AuthenticationProvider`/SP decryption credentials, yet **configuring the right IdP signing cert, metadata, SP entityID, ACS URL, and security testing remains the deployment team's responsibility**. On a wrong recipient or invalid signature, **fail closed**—never fall back to disabling validators.

### Official Reference Documents

- Spring Security — SAML2 Login Overview, RelyingPartyRegistration, signing/decryption credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Producing AuthnRequests, signed Redirect/POST, signing keys: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating Responses, decryption and protocol validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Metadata publishing and trust: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot — SAML2 relyingparty signing/decryption/verification properties: https://docs.spring.io/spring-boot/reference/security/saml2.html
- Spring Security — SAML2 Login sample and dependencies: https://docs.spring.io/spring-security/reference/servlet/saml2/login/
- OASIS SAML V2.0 Technical Overview: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS SAML V2.0 Bindings: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML V2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML V2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C XML Encryption Syntax and Processing 1.1: https://www.w3.org/TR/xmlenc-core1/
- OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
