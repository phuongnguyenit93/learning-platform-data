# Configuring AuthnRequest Signing and Signature Algorithm Selection in Spring Security SAML 2.0

## 1. Lesson Objectives

When a Spring Boot application acts as a **Service Provider (SP / Relying Party)** in SAML 2.0 federation, it can send `<samlp:AuthnRequest>` to an **Identity Provider (IdP / Asserting Party)** to initiate login. Many IdPs require the SP to **digitally sign the AuthnRequest** to verify the request genuinely comes from the registered SP and has not been altered.

This lesson belongs to the **AuthnRequest Customization** group and focuses on two tightly coupled decisions:

1. **When and with which key must the SP sign the AuthnRequest?**
2. **Which signature algorithm do the SP and IdP agree upon, and where is the signature placed per binding?**

After this lesson, learners should be able to distinguish the SP's private key from the IdP's public certificate, configure signing credentials in Spring Boot, understand `WantAuthnRequestsSigned` and `AuthnRequestsSigned`, choose RSA-SHA256 or another algorithm with sound justification, inspect Redirect/POST signatures, and troubleshoot signing issues safely.

**Foundational principle:** an AuthnRequest signature **proves the sender possesses the SP's private key** corresponding to the certificate/key the IdP trusts. It **does not authenticate the user by itself**, does not guarantee the returning SAML Response is valid, and does not replace replay protection, audience, issuer, recipient checks, or business authorization.

## 2. Login Flow and Where the Signature Appears

In SP-initiated Single Sign-On:

```text
User / browser                 SP: Spring application       IdP
          |                          |                       |
          | Open protected page      |                       |
          |------------------------->|                       |
          |                          | Create AuthnRequest   |
          |                          | select registration   |
          |                          | sign with SP private key
          |                          |---------------------->|
          |                          |  Redirect or POST     |
          |                          |                       | verify signature
          |                          |                       | IdP authenticates user
          |        SAMLResponse/Assertion from IdP           |
          |<-------------------------------------------------|
          | POST to ACS              |                       |
          |------------------------->|                       |
          |                          | verify Response/      |
          |                          | Assertion, create session
          |<-------------------------|                       |
```

In HTTP-Redirect binding, the browser is redirected to the IdP with query parameters such as `SAMLRequest`, `RelayState`, `SigAlg`, and `Signature`. In standard HTTP-POST binding, the AuthnRequest sits in the `SAMLRequest` form field and the signature may reside **inside the XML** as `<ds:Signature>`.

Choosing Redirect or POST determines **how the signature is created and verified**. Though both are called “signing an AuthnRequest,” the two methods **do not share the same signed bytes** and one cannot be taken and reused verbatim for the other.

### 2.1. Which Risks Does Signing Help Mitigate?

An AuthnRequest can contain:

- `ID`: request identifier for binding to the SAML Response.
- `Issuer`: **SP Entity ID**.
- `Destination`: IdP SSO URL.
- `AssertionConsumerServiceURL`: address where the SP wants to receive the Response.
- `ProtocolBinding`, `NameIDPolicy`, `RequestedAuthnContext`, `ForceAuthn`, and other options depending on integration.
- `IssueInstant`: timestamp when the request was issued.

If an IdP accepts unauthenticated requests, an attacker might attempt to alter fields related to the response destination, SP identity, or policy. Signing helps protect the signed content from tampering. **The IdP must still verify the request matches a registered SP, the ACS is in an allowlist, timestamps, and its own policies**; digital signing does not make an arbitrary ACS safe.

If parameters are transmitted through the browser, take special care to protect `RelayState` and avoid turning it into an open redirect after login. With Redirect binding, `RelayState` is included in the signed data if present. Upon receiving the response, the SP must also **correlate the request/response with the initiating session**, rather than relying solely on a browser-supplied RelayState.

## 3. Three Easily Confused Key/Certificate Types

| Credential Type | Who Holds the Private Key? | Who Uses the Public Key/Certificate? | Purpose |
| --- | --- | --- | --- |
| **SP signing credential** | SP or a signing service/HSM authorized by the SP | **IdP** | SP signs `AuthnRequest` and certain other messages per configuration |
| **IdP verification credential** | IdP | **SP** | SP verifies `SAMLResponse`/`Assertion` signatures |
| **Metadata signing credential** | Metadata publisher / federation operator | Partner consuming metadata | Verifies integrity/origin of the **metadata document** |

All of them can involve X.509 certificates, but their purpose and private key owners differ:

- When the **SP signs an AuthnRequest**, the SP needs the **SP private key** and matching certificate. **The IdP must know and trust the SP public certificate** from SP metadata or an approved onboarding configuration.
- When the **SP verifies a Response**, the SP uses the **IdP public certificate**, not the SP private key to “check the IdP's signature.”
- When importing **signed metadata**, trust in the metadata signer must be established via a separate process; do not treat a newly appearing certificate inside unverified metadata as sufficient to establish trust.

A single certificate can be used for multiple purposes in some systems, but that must be a deliberate choice. Operationally, separating SP **signing** and **decryption** keys typically limits blast radius and permits independent key rotation when partners support it.

**Never send the SP's private key to the IdP.** The IdP only needs the certificate/public key and SP identity details. Never store the SP private key in git, wikis, shared docs, logs, or public configuration examples.

## 4. Who Requires the AuthnRequest to Be Signed?

Two related metadata attributes exist:

1. On the **IdP** side, it may publish `WantAuthnRequestsSigned="true"` on `<md:IDPSSODescriptor>`: the IdP wants/requires the SP to send signed AuthnRequests per the trust relationship.
2. On the **SP** side, it may publish `AuthnRequestsSigned="true"` on `<md:SPSSODescriptor>`: the SP declares that its AuthnRequests are signed.

**Abbreviated** metadata examples:

```xml
<!-- IdP metadata fragment -->
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    WantAuthnRequestsSigned="true">
    <!-- SSO endpoints and other elements -->
</md:IDPSSODescriptor>
```

```xml
<!-- SP metadata fragment -->
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true">
    <!-- KeyDescriptor, ACS, ... -->
</md:SPSSODescriptor>
```

These snippets illustrate **attribute placement**, not complete metadata XML. When verifying real integration, obtain actual SP/IdP metadata with real entityIDs and certificates.

### 4.1. Two Flags Are Not the Signature Itself

`WantAuthnRequestsSigned` and `AuthnRequestsSigned` are only **policies/declarations**. Without a valid private key or signing performed according to the right binding, the request still has no valid signature, even if metadata sets the flag to `true`.

In modern Spring Security, the decision to sign also relates to:

- **`RelyingPartyRegistration.isAuthnRequestsSigned()`**: the SP proactively chooses to sign (API varies by version).
- **`AssertingPartyMetadata.getWantAuthnRequestsSigned()`**: the IdP's policy/preference.
- **`RelyingPartyRegistration.signingX509Credentials`**: keys and certificates the SP can use to sign.

In versions supporting both flags, Spring Security may sign when **either the SP requires signing or the IdP requires signing**. Therefore, setting `WantAuthnRequestsSigned=false` **should not be interpreted as forbidding all signatures**: if the SP sets its own signing policy, it can still sign. When the IdP requires signed requests, valid signing credentials must be present and verified as suitable.

Spring Security documentation describes **a default toward signing AuthnRequests with HTTP-Redirect and RSA-SHA256**, while allowing configuration indicating the IdP does not require signing. Actual behavior depends on the version, registration metadata, and configured signing credentials; **inspect emitted requests** rather than merely guessing from YAML flags.

### 4.2. When Can Unsigned Requests Be Used?

Some IdPs do not require signed AuthnRequests and federation configurations allow unsigned requests. In that case the SP can configure accordingly, but you must:

- Confirm this is an **approved IdP/federation policy decision**, not a “temporary workaround” for a missing key.
- Ensure the IdP still restricts SP Entity ID, ACS allowlist, and SSO profile.
- Ensure the SP still verifies signature, issuer, audience, subject confirmation, timestamps, and other conditions of the **Response/Assertion**.
- Have tests against login CSRF, replay, and accepting out-of-policy unsolicited responses.

If the partner requires signed AuthnRequests, **do not turn off the signing requirement just to make login work**. Fix the mismatched signing key, binding, certificate, algorithm, or metadata instead.

## 5. HTTP-Redirect Binding: Signing on the Query String

This is a common pattern for SP-initiated SSO. Spring Security defaults to Redirect in many SAML configurations.

With HTTP-Redirect DEFLATE encoding, the conceptual process is:

1. Construct well-formed AuthnRequest XML with `Issuer=SP Entity ID` and `Destination=IdP SSO URL`.
2. **Do not** retain an XML `<ds:Signature>` on the SAML protocol message itself before applying DEFLATE encoding (SAML bindings require stripping message-level signatures in this encoding step).
3. Compress XML using **raw DEFLATE**, Base64-encode, then URL-encode into the `SAMLRequest` query parameter.
4. If `RelayState` is present, URL-encode it as a separate parameter.
5. URL-encode the signature algorithm URI into `SigAlg`.
6. Build the **exact byte sequence** in the specified order and sign with the SP private key.
7. Base64-encode the signature, URL-encode into the `Signature` parameter, and redirect the browser to the IdP SSO endpoint.

The **string used as signing input** takes the form:

```text
SAMLRequest=<URL-encoded-value>&RelayState=<URL-encoded-value>&SigAlg=<URL-encoded-value>
```

If there is **no RelayState**, omit the **entire** `&RelayState=...` segment:

```text
SAMLRequest=<URL-encoded-value>&SigAlg=<URL-encoded-value>
```

For AuthnRequest, the field name is `SAMLRequest`; do not swap it with `SAMLResponse`. Other fields in the query string **are not automatically included in the signing input**. The `Signature` parameter is appended **afterward** and is not part of the initial signing input.

Example Redirect URL structure:

```text
https://idp.example.test/saml/sso
  ?SAMLRequest=<deflated-base64-url-encoded>
  &RelayState=<opaque-state-url-encoded>
  &SigAlg=http%3A%2F%2Fwww.w3.org%2F2001%2F04%2Fxmldsig-more%23rsa-sha256
  &Signature=<base64-signature-url-encoded>
```

Values inside `<...>` are **structural placeholders**, not a sendable URL request. In a real URL, parameters sit on **one line**.

### 5.1. Three Very Easy-to-Mistake Details

**(1) Signed bytes use the original URL-encoded values.** The IdP must verify over the **exact URL-encoded values as received**, in the prescribed signing order. Decoding and re-URL-encoding with a different library can produce different bytes despite identical logical content. For example, `+` and `%20` may both represent a space in certain contexts, yet they are not identical in signature bytes.

**(2) Signing verification order is not the order parameters appear in the URL.** OASIS defines the input construction order: `SAMLRequest`, `RelayState` if present, `SigAlg`. On the URL, parameter order may vary; the verifier must reconstruct the signing data per the rules and **preserve the received encoded values**.

**(3) Do not sign XML content and embed `<ds:Signature>` into Redirect** as you would for POST. HTTP-Redirect DEFLATE binding signs the query-encoded `SAMLRequest/RelayState/SigAlg`; the signature lives in the **`Signature` URL parameter**.

For `RelayState`, classic SAML HTTP-Redirect binding limits size and requires preserving the value when the IdP returns it. Use a **short, opaque state token** stored/mapped server-side; do not place an unvalidated arbitrary URL in RelayState and redirect directly after login.

## 6. HTTP-POST Binding: XML Digital Signature Inside the Request XML

Some IdPs require AuthnRequests to be sent via **HTTP-POST**. In standard SAML HTTP-POST binding:

1. The SP constructs the AuthnRequest XML.
2. The SP can use **XML Digital Signature (XMLDSig)** to sign the AuthnRequest element.
3. The signed XML is Base64-encoded and placed in the `SAMLRequest` form field.
4. The browser POSTs the form to the IdP SSO endpoint.
5. The IdP decodes the XML and verifies `<ds:Signature>` using the registered SP certificate, per binding policy.

Illustration of an XMLDSig-signed AuthnRequest structure:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/sso">
    <saml:Issuer>urn:example:portal:sp</saml:Issuer>
    <ds:Signature>
      <!-- SignedInfo, Reference, SignatureValue, KeyInfo per XMLDSig -->
    </ds:Signature>
</samlp:AuthnRequest>
```

This example is **illustrative XML**, not a valid signature: actual XMLDSig elements, digests, canonicalization, and signatures are built by a specialized library. Do not copy verbatim to send to an IdP.

Points to check:

- `Reference` points to the exact AuthnRequest `ID` being protected; do not accept a signature on a different element (XML Signature Wrapping).
- Use allowed `SignatureMethod`, `DigestMethod`, and `CanonicalizationMethod` algorithms and appropriate transforms (typically including the enveloped signature transform).
- The IdP verifies using the **registered SP certificate**, never “blindly trusting” a certificate embedded in the request's `KeyInfo`.
- Standard HTTP-POST **does not use** the `SigAlg` and `Signature` query parameters of Redirect binding. Profiles/extensions such as POST-SimpleSign are special cases requiring specific agreement and support, not assumed identical to SAML HTTP-POST + XMLDSig.

**If the IdP reports “request unsigned” even though the XML contains `<ds:Signature>`**, first verify **the binding the IdP has registered and expects**. A valid POST signature does not satisfy a Redirect query-signature requirement, and vice versa.

## 7. Algorithms: Distinguishing Java Names from SAML/XMLDSig Algorithm URIs

In Java Cryptography Architecture (JCA), algorithms are named like `SHA256withRSA`. In SAML/XML Signature, algorithms are usually specified by a **URI**.

Examples:

| Option | Common JCA Name | XML Signature URI (SigAlg / SignatureMethod) | Notes |
| --- | --- | --- | --- |
| RSA-SHA256 | `SHA256withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256` | Common default choice in Spring Security |
| RSA-SHA384 | `SHA384withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha384` | Use when supported by the IdP/cryptosystem |
| RSA-SHA512 | `SHA512withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha512` | Use when both sides agree; not “automatically safer” if misimplemented |
| ECDSA-SHA256 | `SHA256withECDSA` | `http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256` | Choose only if IdP, EC key, and OpenSAML/provider are genuinely compatible |
| RSA-SHA1 | `SHA1withRSA` | `http://www.w3.org/2000/09/xmldsig#rsa-sha1` | Legacy algorithm; avoid for new integrations |
| RSA-MD5 | `MD5withRSA` | Corresponding URI | Do not use for modern SAML signatures |

**Do not put the literal string `SHA256withRSA` into `SigAlg` when the protocol expects a URI.** Conversely, when calling JCA's `Signature.getInstance(...)`, pass the provider-supported algorithm name, not the XMLDSig URI.

### 7.1. Why Not Simply Pick RSA-SHA512 for Every Partner?

Overall strength also depends on:

- Algorithm and key size (e.g., RSA 2048+; many organizations choose RSA 3072 for longer lifecycles depending on policy).
- Whether the Java/OpenSAML provider actually supports that algorithm and signature format.
- Whether the IdP accepts the **exact Algorithm URI**.
- Whether the IdP has the right RSA or EC certificate/public key type.
- Whether weak algorithms remain enabled in the signing/digest policy.
- Whether the signed data conforms properly to binding/canonicalization rules.

If an IdP recognizes only RSA-SHA256, forcing RSA-SHA512 can cause request rejection even when the cryptographic signature is valid. If the IdP advertises a `SigningMethod` list in metadata, select from the **intersection** of the trusted list, local policy, and actual signing capability.

**Recommendation:** use **RSA-SHA256** as a baseline when supported by both sides and allowed by policy. Use RSA-SHA384/512, ECDSA, or others after verifying metadata, IdP docs, key type, and interoperability test results. Never silently fall back to RSA-SHA1/DSA-SHA1/MD5 due to partner misconfiguration; resolve via an approved migration/technical contract.

### 7.2. SignatureMethod and DigestMethod Are Not the Same

For **XMLDSig in POST**, `SignatureMethod` specifies the algorithm signing `SignedInfo`, e.g., RSA-SHA256; `DigestMethod` specifies the hash algorithm of each reference, e.g., SHA-256. These are two separate fields to configure per profile/policy.

For **Redirect query signatures**, `SigAlg` specifies the algorithm signing the query byte string; there is no `SignedInfo/Reference/DigestMethod` structure in this binding's signed query. Do not apply POST XMLDSig canonicalization guidance to “fix” Redirect signature bytes.

### 7.3. Coordinating Algorithms with IdP Metadata

An IdP may publish `md:Extensions` containing `SigningMethod` extensions with preferred algorithm URIs. Spring Security can read/select algorithms from IdP metadata via `RelyingPartyRegistrations`, or allow manual configuration via `AssertingPartyMetadata.signingAlgorithms`.

This list must come from **trusted metadata**. Never accept user/HTTP-request-supplied algorithms; never let a token or query string re-enable SHA-1. If metadata changes algorithms, require compatibility testing and policy-backed rollback capability.

## 8. Spring Boot Configuration: Private Key/Certificate for Signing

Example for **Spring Boot 3.x / Spring Security 6.x** (properties may vary by version; verify configuration metadata for your exact version). Spring Boot acts as the SP and the IdP is already properly registered.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            signing:
              credentials:
                - private-key-location: "file:/etc/secrets/saml/sp-signing-key.pem"
                  certificate-location: "file:/etc/secrets/saml/sp-signing-cert.pem"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "classpath:corp-idp-metadata.xml"
              singlesignon:
                sign-request: true
```

**Explanation:**

- `corp` is Spring Security's `registrationId`; it is not the SP Entity ID.
- `entity-id` is the **SP Entity ID**; the IdP must recognize that exact value and the corresponding SP certificate.
- `signing.credentials` loads the **SP private key** and matching X.509 certificate so the SP can sign AuthnRequests; these are two separate files provisioned by operations. **Paths in the example are illustrative structure only**; valid files/certs must be supplied.
- `assertingparty.metadata-uri` is the IdP metadata source. The IdP entityID, SSO endpoint, Response verification certificate, and algorithm hints originate from trusted metadata; being able to load XML does not by itself prove the metadata signature was verified.
- `assertingparty.singlesignon.sign-request: true` indicates the IdP expects signed AuthnRequests per Spring Boot configuration. The SP must have a signing credential to fulfill it.
- `acs.location` is the endpoint receiving the **SAML Response**, distinct from the IdP SSO endpoint receiving the **AuthnRequest**. `{baseUrl}` and `{registrationId}` expand in deployment context; inspect the URL emitted in actual SP metadata.

This is an **integration configuration sample**; it cannot log in on its own without a real IdP, key/certificate files, trust policy, and a built Spring Boot application.

### 8.1. Choosing Where to Store Keys

The SP private key must be protected commensurate with its role authenticating the SP:

1. Generate a key pair with the right algorithm/size per security policy and IdP capability.
2. Attach the corresponding public certificate; verify private/public keys match before deployment.
3. Store the private key in a secret manager, keystore, secure volume, or HSM per design; grant read permission only to the process that must sign.
4. Never package production private keys in `src/main/resources`, public container images, or source control.
5. Deliver the **SP public certificate** to the IdP over a verified admin/metadata channel; never send the private key.
6. Design certificate renewal, overlap, and incident revocation from the start.

If using an HSM/remote signer where the private key cannot be exported as a file, integrate a compatible credential/provider so Spring Security/OpenSAML signs via supported APIs. **Do not assume the `private-key-location` property can directly call every HSM**.

### 8.2. Key Formats and Common Mistakes

- Certificates are typically PEM `-----BEGIN CERTIFICATE-----` in X.509 format.
- PEM private keys typically need **PKCS#8** `-----BEGIN PRIVATE KEY-----` with the appropriate provider/converter; a PKCS#1 `RSA PRIVATE KEY` or encrypted key may require conversion or a different loader.
- Key and certificate must be a **matching pair**. Otherwise signing/verification will fail.
- Do not confuse `assertingparty.verification.credentials` (the **IdP** public certificate for the SP to verify responses) with `registration.corp.signing.credentials` (the **SP** private key and cert for signing requests).
- Do not use expired or policy-revoked certificates. Self-signed certificates may still be accepted by IdPs in certificate-pinning federation models, provided they are explicitly registered/trusted.

## 9. Java Spring Security: Selecting Algorithms via AssertingPartyMetadata

By default, Spring Security signs with **RSA-SHA256** in supported configurations when a signing credential is present. If an IdP requires **RSA-SHA512**, Spring Security provides `AssertingPartyMetadata.signingAlgorithms` to adjust the preferred algorithm list.

The following Java snippet **belongs in a Spring application that already has the `spring-security-saml2-service-provider` dependency**, registrations, and secure key sources. It is a repository-building excerpt, not a standalone program run with `javac`:

```java
import org.opensaml.xmlsec.signature.support.SignatureConstants;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

import java.security.PrivateKey;
import java.security.cert.X509Certificate;

// Place inside a @Bean method of a @Configuration class.
// privateKey and certificate are the securely loaded SP signing pair.
Saml2X509Credential spSigner =
    Saml2X509Credential.signing(privateKey, certificate);

RelyingPartyRegistration rp = RelyingPartyRegistrations
    .fromMetadataLocation("classpath:corp-idp-metadata.xml")
    .registrationId("corp")
    .entityId("urn:example:portal:prod:sp")
    .signingX509Credentials(credentials -> credentials.add(spSigner))
    .assertingPartyMetadata(party -> party
        .wantAuthnRequestsSigned(true)
        .signingAlgorithms(algorithms -> {
            algorithms.clear();
            algorithms.add(
                SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512);
        })
    )
    .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(rp);
```

**Accurate interpretation:**

- `Saml2X509Credential.signing(privateKey, certificate)` assigns the **SP** key for signing.
- `signingX509Credentials` is on the **RP/SP** side, not the IdP's certificate.
- `wantAuthnRequestsSigned(true)` sets the **IdP's** preference/requirement in the registration; it does not generate a private key.
- `signingAlgorithms` describes algorithms compatible with the IdP; the example calls `clear()` then adds RSA-SHA512 to **solely prefer** the agreed algorithm. Do this only when the IdP truly supports it, the private key is a suitable RSA key, the provider supports it, and signing tests succeed. If IdP metadata already includes the right algorithm list, **prefer using the verified list** to avoid unnecessary hard-coding.
- `SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512` is an **Algorithm URI** supplied by OpenSAML, not JCA's `"SHA512withRSA"`.
- `fromMetadataLocation(...)` loads metadata, **without automatically guaranteeing the metadata signature is trusted**; metadata verification itself requires configuring an appropriate trust chain/metadata repository.

When using Spring Boot YAML auto-configuration, you typically do not create a repository manually just to load signing credentials. Pick **one controllable configuration source** to avoid having two different repositories skewing the registration actually used by the filter.

### 9.1. AuthnRequest Customization Differs from Algorithm Customization

Spring Security provides `OpenSaml5AuthenticationRequestResolver` and `setAuthnRequestCustomizer` to modify fields such as `ForceAuthn`, `NameIDPolicy`, or `RequestedAuthnContext`. For example:

```java
RelyingPartyRegistrationResolver registrationResolver =
    new DefaultRelyingPartyRegistrationResolver(registrations);
OpenSaml5AuthenticationRequestResolver resolver =
    new OpenSaml5AuthenticationRequestResolver(registrationResolver);

resolver.setAuthnRequestCustomizer(context ->
    context.getAuthnRequest().setForceAuthn(true));
```

This is a **configuration excerpt** assuming the `registrations` variable and corresponding Spring Security imports, not a standalone Java file. Changing `ForceAuthn` modifies **the authentication request content**; selecting signing credentials/algorithms/bindings lives in the registration and framework SAML processing. Let Spring Security/OpenSAML **sign after all signed data is finalized**. Never sign first and then modify Issuer/ACS/ForceAuthn, or the signature can become invalid.

If using a Spring Security version other than one with `OpenSaml5AuthenticationRequestResolver`, check the corresponding Javadoc and API. Never copy legacy Spring Security SAML Extension code into modern SAML2 Service Provider without migrating it.

## 10. SecurityFilterChain for a SAML 2.0 Web App

Minimal example of Spring Security Servlet responsibilities:

File `src/main/java/com/example/portal/SecurityConfig.java`:

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
```

`saml2Login()` instructs Spring Security to produce/receive SAML Web SSO; `saml2Metadata()` publishes SP metadata if the application registers with the IdP via metadata. This class requires a Spring Boot project, SAML2 dependencies, and real registrations; **it is not standalone code**.

With `registrationId=corp`, the common initiation endpoint is:

```text
GET /saml2/authenticate/corp
```

The IdP typically receives the AuthnRequest at the configured `SingleSignOnService`. The outgoing authentication URL, binding, and signature depend on `corp`'s actual registration; do not infer `SigAlg` from this path alone.

### 10.1. Inspecting SP Metadata Before Testing

If `saml2Metadata()` is enabled, commonly used endpoints include:

```text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
```

Inspect the emitted SP metadata to confirm:

- `EntityDescriptor/@entityID` matches the **SP Entity ID**.
- `SPSSODescriptor/@AuthnRequestsSigned` matches the chosen policy.
- `KeyDescriptor use="signing"` (if emitted) contains the **SP public certificate** that the IdP must trust.
- `AssertionConsumerService/@Location` has the right public HTTPS URL, not `localhost` or an internal hostname from a reverse proxy.
- If the IdP previously imported metadata, the IdP-side certificate and entityId must be updated when changed.

**Never publish the private key in metadata.** Public certificates/chains and URLs are the data used by both sides to configure trust; when distributing metadata, also verify document origin trust.

## 11. Standalone Java 17 Example: Creating and Verifying a Redirect Signature

To understand the **signed bytes** in HTTP-Redirect binding clearly, the following example:

- Builds an illustrative AuthnRequest XML.
- Compresses with raw DEFLATE, Base64-encodes, and URL-encodes into `SAMLRequest`.
- Concatenates `SAMLRequest`, `RelayState`, and `SigAlg` in the standard signing order.
- Uses Java 17 `SHA256withRSA` to sign that byte sequence.
- Verifies with the matching public key, then tests modifying RelayState, modifying SAMLRequest, or using another public key.

This is a **standalone educational program**, designed to compile with JDK 17+. It **does not** produce a signed AuthnRequest for a production IdP: key pairs are generated randomly at runtime, there is no X.509 certificate registered with an IdP, the XML uses sample values, and it does not handle request correlation/sessions, metadata, expiration, or responses. In real applications, **use Spring Security/OpenSAML**, rather than copying this simplified signer to replace a SAML library.

File `SamlRedirectSigningDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Base64;
import java.util.zip.Deflater;

public class SamlRedirectSigningDemo {
    private static final String SIG_ALG =
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256";

    static String encodedRequest(String xml) {
        byte[] input = xml.getBytes(StandardCharsets.UTF_8);
        Deflater deflater = new Deflater(Deflater.DEFAULT_COMPRESSION, true);
        deflater.setInput(input);
        deflater.finish();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        while (!deflater.finished()) {
            int n = deflater.deflate(buffer);
            output.write(buffer, 0, n);
        }
        deflater.end();
        return URLEncoder.encode(
            Base64.getEncoder().encodeToString(output.toByteArray()),
            StandardCharsets.UTF_8
        );
    }

    static String toSign(String encodedRequest, String relayState) {
        return "SAMLRequest=" + encodedRequest
            + "&RelayState=" + URLEncoder.encode(
                relayState, StandardCharsets.UTF_8)
            + "&SigAlg=" + URLEncoder.encode(
                SIG_ALG, StandardCharsets.UTF_8);
    }

    static String sign(String query, PrivateKey key) throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(query.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signer.sign());
    }

    static boolean verify(String query, String signature, PublicKey key)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(query.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(Base64.getDecoder().decode(signature));
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair sp = generator.generateKeyPair();
        KeyPair another = generator.generateKeyPair();
        String xml = "<samlp:AuthnRequest "
            + "xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol' "
            + "xmlns:saml='urn:oasis:names:tc:SAML:2.0:assertion' "
            + "ID='_req1' Version='2.0' "
            + "IssueInstant='2026-01-01T10:00:00Z' "
            + "Destination='https://idp.example.test/sso'>"
            + "<saml:Issuer>urn:example:portal:sp</saml:Issuer>"
            + "</samlp:AuthnRequest>";
        String signedInput = toSign(encodedRequest(xml), "state-42");
        String signature = sign(signedInput, sp.getPrivate());
        System.out.println("signedCorrectly="
            + verify(signedInput, signature, sp.getPublic()));
        System.out.println("modifiedRelayState="
            + verify(signedInput.replace("RelayState=state-42",
                "RelayState=other"), signature, sp.getPublic()));
        System.out.println("modifiedSamlRequest="
            + verify(signedInput.replace("SAMLRequest=",
                "SAMLRequest=X"), signature, sp.getPublic()));
        System.out.println("untrustedPublicKey="
            + verify(signedInput, signature, another.getPublic()));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 SamlRedirectSigningDemo.java
java SamlRedirectSigningDemo
```

**Exact stdout** (signature contents and key pairs are randomly generated, but the Boolean outputs remain as follows):

```text
signedCorrectly=true
modifiedRelayState=false
modifiedSamlRequest=false
untrustedPublicKey=false
```

**Explanation of results:**

- `signedCorrectly=true`: the public key matching the SP private key verifies the exact bytes signed.
- `modifiedRelayState=false`: changing RelayState alters the signature input.
- `modifiedSamlRequest=false`: altering the URL-encoded SAMLRequest data changes the signature input.
- `untrustedPublicKey=false`: a different public key cannot verify the SP's signature.

`URLEncoder` produces a URL-encoded string from the given values; in the example, all signed values are produced and consumed consistently. Production integrators must follow exact encoding rules, validate original HTTP inputs, SAML binding constraints, and algorithm policies. For a real signature, after generating `signature`, you can append query parameter `&Signature=` plus the **URL-encoded Base64 signature** to the Redirect URL; this program **does not perform an HTTP redirect**.

Using two RSA key pairs in the demo proves the verification key must match. In practice, the IdP does not “pick” an arbitrary public key from the AuthnRequest; it must look up the **registered and trusted SP certificate** for the right SP Entity ID/registration.

## 12. Guide to Verifying Signing in an Integration Environment

A configuration is considered done only when a **real request is sent to the IdP** over the right binding and the IdP verifies the signature.

### Step A — Finalize the SP–IdP Contract

Collect/record:

1. Exact SP Entity ID and IdP Entity ID.
2. IdP SSO URL and allowed HTTP binding (Redirect or POST).
3. Whether the IdP requires signed AuthnRequests; whether the SP sets `AuthnRequestsSigned`.
4. Algorithms accepted by the IdP, preference order, and weak-algorithm exclusion policy.
5. SP public certificate and SHA-256 fingerprint imported by the IdP.
6. ACS URL and SP metadata registered at the IdP.
7. Certificate rotation plan, unsigned request rejection rules, and separate dev/prod environments.

### Step B — Inspect Application Configuration

Inspect the actual `RelyingPartyRegistration` (not only the YAML file):

- Does the selected `registrationId` match the right IdP?
- Does the SP's `entityId` match the record at the IdP?
- Does `signingX509Credentials` contain a signing credential with a valid private key?
- Do `getWantAuthnRequestsSigned()` and the SP's signed policy align with the partner?
- Does `getSigningAlgorithms()` include an algorithm supported by both sides?
- Is the effective SSO binding `REDIRECT` or `POST`?

If using multiple IdPs, each registration can have its own signing requirements, certificates, and algorithms. Do not blindly apply one algorithm/cert across all registrations if contracts differ.

### Step C — Send a Real AuthnRequest

Open the login entry point `/saml2/authenticate/{registrationId}` in a test environment and use network/SAML inspection tools under secure conditions.

For **Redirect**:

- Check that the IdP URL contains `SAMLRequest`, `SigAlg`, and `Signature`; `RelayState` may or may not be present.
- Verify `SigAlg` after URL-decoding is the agreed algorithm URI (e.g., RSA-SHA256).
- The IdP verifies the signature using the **SP public certificate**. When re-verifying manually, use the exact encoded bytes from the query; **do not** decode and arbitrarily re-encode.
- Do not infer “Signature param present = valid signature”; verify with the trusted key.

For **POST**:

- The form contains Base64 `SAMLRequest`; decode it to inspect `<ds:Signature>` on the AuthnRequest.
- Verify the signed reference, XMLDSig `SignatureMethod`/digest, SP certificate, schema, and binding constraints.
- Do not expect Redirect-style `Signature` query parameters when using standard POST XMLDSig.

### Step D — Verify the Response Independently

Once the IdP accepts the AuthnRequest, the SP **still needs** to verify the Response/Assertion: IdP signature, issuer, audience, `Recipient`/`Destination`, `InResponseTo`, and timestamps. Never assume “the request was signed, so any returned Response is trustworthy.”

Spring Security typically saves the pending AuthnRequest for correlation with the Response; if replacing the request storage mechanism or using a distributed cache, preserve login CSRF/replay protection and user session binding rather than looking only at an easily guessed `RelayState`.

## 13. Real-World Errors and Investigation Guide

| Symptom | Typical Cause | Investigation / Resolution |
| --- | --- | --- |
| IdP reports “unsigned AuthnRequest” | SP lacks signing credential configuration, or wrong signing binding | Check SP key/cert, signed flag, Redirect `Signature` vs. POST `ds:Signature` |
| IdP reports signature invalid | IdP uses stale/wrong SP cert, private key does not match cert, or query bytes changed | Compare public cert fingerprint, keypair, and raw signed query |
| `SigAlg` is RSA-SHA1 and rejected by policy | Legacy algorithm left in configuration | Select IdP-supported RSA-SHA256+, remove weak fallbacks |
| IdP supports only RSA-SHA256, but SP sends RSA-SHA512 | `signingAlgorithms` list forced incorrectly | Restore supported intersection; test with IdP |
| `InvalidKeyException` / key mismatch error | Certificate/private key type incompatible with algorithm | Verify RSA/EC keypair, PKCS#8 format, provider |
| Cannot read private key | Wrong path/file permissions, invalid PEM format, or unsupported encrypted key | Check mount/permissions, supported converter/keystore |
| Set `sign-request:false` yet request is still signed | SP itself requires signing, or another signed flag is set in policy | Check both `AuthnRequestsSigned` and `WantAuthnRequestsSigned` and live metadata |
| Changed `Destination` or `ForceAuthn` after signing | Signed data altered after signing | Perform customization **before** framework signing |
| Redirect URL modified by intermediary | Proxy/gateway/URL normalizer altered encoded query | Preserve query bytes verbatim; check safe logs and redirect chain |
| POST has XML Signature, but IdP only accepts Redirect signature | Binding mismatch | Align Redirect/POST and signing format with IdP |
| IdP accepts request, but Response goes to wrong ACS | Wrong public base URL / registered ACS | Check reverse proxy/forwarded headers and SP metadata |
| Login “fails only in prod” | Environment-specific cert/algorithm/Entity ID mismatch | Isolate trust and credentials per environment; inspect live registration |
| Valid signature, yet IdP still rejects request | Invalid Issuer, ACS, NameIDPolicy, AuthnContext, or clock skew | Identify exact IdP error type; do not disable signing |
| Login fails after SP certificate rotation | IdP still holds old key or cutover happened too early | Coordinate overlap/metadata update and planned cutover |
| No response or Response fails validation | Signing request succeeded only as step one | Inspect SAML Response signature/issuer/audience/time/subject confirmation |

**Layered diagnosis:** “unable to sign” is an SP key/config error; “IdP cannot verify” is a certificate/binding/algorithm/bytes error; “SP does not accept response” is an IdP verification or ACS/session error. Never fix one layer by disabling protections on another layer.

## 14. Key Rotation Strategy for AuthnRequest Signing

SP signing key rotation must be coordinated **before the new private key is put into active service**:

1. Inventory the SP Entity ID, affected IdPs, current certificate, expiration date, and algorithms.
2. Generate a new key pair/certificate per policy; verify IdP compatibility.
3. Deliver the **new public certificate** to the IdP via a verified onboarding/metadata channel. If the IdP supports multiple certificates, register both old and new during the transition window.
4. Confirm the IdP already trusts the new certificate **before** the SP begins signing with the new private key.
5. Test flows per IdP and across active Redirect/POST bindings; monitor error rates.
6. Cut over to the new key in a controlled manner, recording change history/fingerprints for investigation.
7. After the transition window, remove the old certificate from the IdP and revoke/retire the old key from storage.
8. Keep a recovery plan if a partner lags in syncing; do not default to recovering by sending unsigned requests.

**Distinction:** the SP's AuthnRequest signing certificate and the IdP's SAML Response signing certificate can rotate independently. Do not use an IdP certificate change as a reason to rotate the SP private key unless related.

If the SP private key is suspected compromised, do not just “change the key file password”: replace the key pair, revoke trust in the old certificate at the IdP, audit potentially forged AuthnRequests, and investigate related events.

## 15. Functional and Security Testing

| Test Case | Configuration / Input | Expectation |
| --- | --- | --- |
| Standard signed Redirect | SP signs query with RSA-SHA256, IdP has right SP cert | IdP verifies signature and processes request per policy |
| Standard signed POST | SP XML-signs AuthnRequest, IdP supports POST | IdP verifies XML signature |
| Wrong SP certificate | Request validly signed with a key other than IdP-trusted cert | IdP rejects |
| Wrong algorithm | SP uses RSA-SHA512, IdP accepts only RSA-SHA256 | IdP rejects with clear error |
| Tamper `SAMLRequest` after signing | Alter encoded request | Signature invalid |
| Tamper `RelayState` after signing | Alter encoded relay | Redirect signature invalid |
| Tamper `SigAlg` | Algorithm URI no longer matches signature | Rejected |
| Missing `Signature` | IdP requires signed AuthnRequest | Rejected |
| Missing private key | Signing flag enabled, signing credentials absent | Fails fast with clear error; does not send unsigned when disallowed |
| Key rollover | Both old and new certs trusted by IdP during overlap | Key switch succeeds; old cert retired after window |
| Change `ForceAuthn` before signing | Customizer runs before signing | Signature remains valid |
| Alter XML after signing | `Issuer`, `Destination`, or `NameIDPolicy` modified | Signature invalid |
| Re-encode Redirect URL | Percent-encoding mutated | Verifier rejects if signed bytes changed |
| Different IdP | Request for `registrationId=partner` signed with `corp` cert | Rejected under partner's trust |
| Same SP, multiple IdPs | Each registration has distinct signing policy | No leaking/mixing certs, algorithms, or endpoints |
| Reverse proxy | `{baseUrl}` resolves to internal HTTP host | Metadata/ACS tests fail; fix trusted proxy/public URL |
| Forged Response | Signed AuthnRequest, but Response lacks valid IdP signature | SP rejects |
| Replayed response | Previously used Response resubmitted | SP rejects per correlation/replay policy |
| Key load error | Private key file has wrong read permissions | Fails safely; does not log private key or continue unsigned |
| Weak algorithm | IdP metadata requests RSA-SHA1 | Do not auto-enable weak algorithm; plan compatibility/migration |

Beyond signature unit tests, run **integration tests with an IdP or SAML test harness** because many failures appear only over real HTTP protocol handling: URL encoding, bindings, imported certificates, and ACS policies. Useful evidence to record includes algorithm URI, certificate fingerprint, request ID, registrationId, timestamp, and error category; avoid logging full SAML assertions or secrets.

## 16. Implementation Checklist

- [ ] Know whether the IdP genuinely requires signed AuthnRequests via metadata `WantAuthnRequestsSigned` and the technical contract.
- [ ] Know whether the SP declares `AuthnRequestsSigned` and has its own signing policy.
- [ ] Configured a matching **SP private key + X.509 certificate** pair in `signing.credentials`/`signingX509Credentials`.
- [ ] IdP has registered the **SP public certificate** for the right SP Entity ID and environment.
- [ ] Do not confuse SP signing certificates with IdP response verification or metadata signing credentials.
- [ ] Identified **HTTP-Redirect** vs. **HTTP-POST** and signature placement for the corresponding binding.
- [ ] For Redirect, confirmed `SAMLRequest`, `RelayState` if any, `SigAlg`, `Signature`, and signed byte order.
- [ ] For POST, confirmed XMLDSig `SignedInfo`, `Reference`, `SignatureMethod`, and `DigestMethod` are thoroughly verified.
- [ ] Signing algorithm has the **exact Algorithm URI**, compatible with key type, IdP, OpenSAML, and policy.
- [ ] RSA-SHA1/DSA-SHA1/MD5 are not re-enabled arbitrarily; no silent downgrades.
- [ ] SP key is protected in an appropriate secret manager/keystore/HSM; private keys are never committed to repositories or logs.
- [ ] SP metadata, ACS, IdP SSO endpoint, proxy URL, and public certificates are cross-checked.
- [ ] If using `OpenSaml5AuthenticationRequestResolver`, all AuthnRequest modifications happen **before signing**.
- [ ] Signing AuthnRequests does not skip full **SAML Response/Assertion verification** on the SP side.
- [ ] Negative cases tested: wrong key, wrong SigAlg, modified query, wrong binding, unsigned, wrong registration, replay.
- [ ] Have a key rollover plan, testing when the IdP caches old certs, and an incident response plan if the SP key is compromised.

## 17. Self-Check Questions

**1. Who signs the AuthnRequest and who verifies the signature?**

The SP signs using the **SP's private key**; the IdP verifies using the **SP's public key/certificate** provided and trusted in the partner configuration.

**2. Does setting `sign-request:true` automatically generate a private key to sign with?**

No. The flag expresses a signing requirement/preference; the SP still needs valid signing credentials, a certificate registered at the IdP, and compatible binding/algorithm.

**3. With HTTP-Redirect, is the signature inside XML `<ds:Signature>`?**

Not under standard SAML HTTP-Redirect DEFLATE binding. The signature is computed over the URL-encoded query bytes across `SAMLRequest`, `RelayState` if present, and `SigAlg`, then appended as `Signature` on the URL.

**4. If there is no RelayState, should you sign an empty `RelayState=`?**

No. Omit the RelayState parameter completely from the signing input per binding rules.

**5. Why does Java `Signature.getInstance("SHA256withRSA")` differ from the `SigAlg` URI?**

JCA uses **Java provider algorithm names**; SAML/XMLDSig uses **protocol-standardized URIs**. Integrators must map properly between the two forms.

**6. What default signing algorithm does Spring Security commonly use?**

Spring Security documentation describes **RSA-SHA256** when signing AuthnRequests, while allowing `signingAlgorithms` to pick an algorithm matching the IdP. Actual output should be verified on emitted requests.

**7. Should you automatically upgrade to RSA-SHA512 for every IdP?**

No. You must ensure IdP, key type, and provider compatibility; do not cause interoperability failures and do not permit downgrades to weak algorithms.

**8. Can you modify `ForceAuthn` after the request has already been signed?**

You should not: modifying signed content invalidates the signature. Perform customization before the framework's signing step.

**9. Is a validly signed AuthnRequest enough to accept any SAML Response?**

Not yet. The SP must verify the IdP signature, issuer, audience, destination/recipient, request correlation, validity window, subject confirmation, and replay protection.

**10. Why might an IdP see an RSA-SHA256 signature and still reject it?**

The SP certificate may not match, wrong bytes may have been signed, wrong binding used, request issuer/ACS unregistered, or IdP policy may reject the current configuration. Categorize the error before tweaking algorithms.

## 18. Authoritative Reference Documentation

- Spring Security, **Producing AuthnRequests** — signing requirements, `wantAuthnRequestsSigned`, `signingAlgorithms`, Redirect/POST, and customizers: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Login Overview** — credentials and `RelyingPartyRegistration`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Boot 3.5, **SAML 2.0 Relying Party Properties** — `signing.credentials[*].private-key-location`, `certificate-location`: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security Javadoc, **Saml2X509Credential** — `signing(privateKey, certificate)`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Security Javadoc, **AssertingPartyMetadata** — `getWantAuthnRequestsSigned`, `getSigningAlgorithms`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadata.html
- OASIS, **Bindings for SAML V2.0**, HTTP-Redirect/HTTP-POST sections: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS, **SAML V2.0 Metadata**, `AuthnRequestsSigned` / `WantAuthnRequestsSigned` flags: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OWASP, **SAML Security Cheat Sheet** — validation, trust, and XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Key takeaway:** to sign AuthnRequests securely, you must align **IdP/SP signing requirements + SP private key/certificate + supported algorithm + SAML HTTP binding**. HTTP-Redirect signs the **URL-encoded query**, while standard HTTP-POST signs the **XML**. In Spring Security, configuring signing credentials and signing algorithms must follow the federation contract; request signing never replaces full SAML Response/Assertion verification and application-side authorization.