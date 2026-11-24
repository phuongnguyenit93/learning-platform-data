# Response Signatures, Assertion Signatures, and Distinguishing Encrypted Assertions in SAML 2.0

> **Topic:** Spring Security – federation · **Group:** SAML2 Model. This lesson explains **XML signatures on `samlp:Response`**, **signatures on `saml:Assertion`**, **`saml:EncryptedAssertion`**, the signing–encryption relationship, and what a Service Provider (SP) checks before letting a user log in.

## 1. The Problem to Understand

When the Identity Provider (**IdP**, also called the Asserting Party) finishes login, the user's browser forwards a `SAMLResponse` to the **Assertion Consumer Service (ACS)** of the **Service Provider (SP)** application. The payload may contain:

- **`samlp:Response`:** protocol envelope carrying `ID`, `InResponseTo`, `Destination`, `Issuer`, `Status`, and one or more assertions.
- **`saml:Assertion`:** statements issued by the IdP about the user, timestamps, usage conditions, intended recipient (audience), authentication method, and attributes/groups.
- **`ds:Signature`:** XML signature (XML Digital Signature / XMLDSig) to verify a trusted issuer and the **integrity** of **the exact signed XML fragment**.
- **`saml:EncryptedAssertion`:** an assertion encrypted with XML Encryption (XMLEnc), typically to protect user information from intermediaries holding the message, including the browser.
- **Metadata and credentials:** trusted keys/certificates for verifying IdP signatures and decryption keys owned by the SP.

All data in a browser POST must be treated as **untrusted prior to verification**. HTTPS protects only the transport links; the browser itself carries the payload and can therefore alter the `SAMLResponse` parameter. Merely Base64-decoding the XML and reading `NameID` or `Role` is **not SAML authentication**.

**Central thesis:**
- **Signing** answers: “Was this message/XML fragment issued by the holder of a trusted signing key and is it intact?”
- **Encryption** answers: “Who is able to read the encrypted content?”
- **SAML condition checks** answer: “Is this authenticated Assertion permitted to be used **at this SP, for this request/session, at this time**?”
- No single step can replace all of the others.

## 2. XML Structure and Signature Placement

SAML 2.0 uses XML namespaces: `samlp` for protocol, `saml` for assertion, `ds` for XML Signature, and `xenc` for XML Encryption. Prefix names are just shorthand; validators must operate on real namespaces/schemas, not compare prefix strings.

### 2.1. Signature on Response

**Simplified** illustration, **not a valid SAML Response for live execution**: `...` stands in for complete fields, digital signatures, and identity data.

~~~xml
<samlp:Response ID="_resp001"
                Destination="https://sp.example.org/login/saml2/sso/corp"
                InResponseTo="_request001"
                xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <saml:Issuer>https://idp.example.org</saml:Issuer>

  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_resp001">
        <!-- Transforms/DigestMethod/DigestValue omitted -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue, KeyInfo per profile omitted -->
  </ds:Signature>

  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assert001">
    <!-- Subject, Conditions, AuthnStatement, AttributeStatement -->
  </saml:Assertion>
</samlp:Response>
~~~

Here `ds:Signature` is a **direct child of Response**, and `ds:Reference URI="#_resp001"` points to the Response. When the Reference, transforms, and signature are **properly verified**, the signature protects the signed XML region of the Response, including the nested assertion; the assertion is not required to have its own signature if the profile/SP policy permits Response signing.

**What must NOT be inferred:**
- Seeing a `ds:Signature` tag on Response **does not prove** the signature is valid.
- A signature is meaningful only after matching the signing key to the **trusted IdP in the SP registration** and binding the Reference to the exact Response being processed.
- If a developer manually pulls another `Assertion` outside the protected XML region, a valid Response signature can still be exploited via **XML Signature Wrapping**.
- A Response signature **does not keep confidential** `NameID`, email, or groups; the browser can Base64-decode and read plaintext assertions.

### 2.2. Signature on Assertion

Simplified illustration:

~~~xml
<samlp:Response ID="_resp002"
                Destination="https://sp.example.org/login/saml2/sso/corp"
                xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <saml:Issuer>https://idp.example.org</saml:Issuer>

  <saml:Assertion ID="_assert002">
    <saml:Issuer>https://idp.example.org</saml:Issuer>
    <ds:Signature>
      <ds:SignedInfo>
        <ds:Reference URI="#_assert002">
          <!-- Transforms, digest ... -->
        </ds:Reference>
      </ds:SignedInfo>
      <!-- SignatureValue ... -->
    </ds:Signature>
    <saml:Subject>...</saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Here the signature sits **inside the Assertion** and the Reference points to `_assert002`. It protects the assertion content under the applied transforms/canonicalization. **The outer Response envelope is not signed by the Assertion signature**. Therefore, the SP still must verify `Destination`, `InResponseTo`, issuer/registration, ACS, and request context per protocol rules; never trust Response fields blindly simply because the inner assertion has a valid signature.

If a Response contains **multiple assertions**, one assertion's signature cannot make another assertion trusted by default. Under Spring Security SAML2 defaults described in the documentation: **the Response is validly signed or every assertion must have a valid signature**; an invalid signature on an assertion is an error, even if another part is signed.

### 2.3. Both Response and Assertion Signed

The IdP can also do:

~~~text
Response [ds:Signature -> Response.ID]
└── Assertion [ds:Signature -> Assertion.ID]
    └── Subject / Conditions / AuthnStatement / Attributes
~~~

The two signatures protect **two different XML scopes**. The SP must verify the signatures it requires and never ignore a signature that is present yet **invalid**. A “sign both” configuration may serve federation contracts, partner mandates, or specific controls, but does not turn an expired assertion into a valid one or replace audience/recipient checks.

**Policy note:** Depending on binding/profile, metadata, and SP/IdP policy, a party may require “sign Response,” “sign Assertion,” or “both.” For **SAML Web Browser SSO HTTP-POST**, OASIS errata clarify that **either the Response or the Assertions within the Response must be signed**; a specific partner's policy may be stricter. Do not apply that rule mechanically to every SAML profile/binding.

## 3. What Does an XML Signature Actually Verify?

A `ds:Signature` is not an arbitrary attached signature string. XMLDSig includes:

1. **`ds:SignedInfo`** containing `CanonicalizationMethod`, `SignatureMethod`, and one or more `Reference` elements.
2. **`ds:Reference URI="#ID"`** identifies **the protected XML portion**. `Transforms` and `DigestMethod/DigestValue` describe how to canonicalize/hash the referenced content.
3. **`ds:SignatureValue`** is the signature value over the canonicalized `SignedInfo`.
4. **`ds:KeyInfo`** (if present) hints at the key/certificate; **never blindly trust a key supplied by an untrusted payload**.

Proper verification process: use a hardened XML parser; resolve ID references/transforms using a vetted library; verify digests and signature; **select the verification key from the SP's trusted IdP verification credentials**; bind the verification result to **the exact Assertion/Response node the business logic reads**.

Signing normally uses the **IdP's** private key; the SP holds the **IdP's public key/X.509 certificate** to verify. Certificates in SAML metadata are typically how federation trust is distributed and governed, rather than relying by default on TLS domain/CA checks. Managing key rotation and IdP metadata matters far more than merely seeing an `X509Certificate` inside browser-sent `KeyInfo`.

Distinguish these checks:

| Check | What problem does it solve? | What it does NOT replace |
|---|---|---|
| XML Signature + trusted IdP key | Issuer origin and integrity of the signed XML scope | Time, audience, recipient, state/replay |
| Issuer/registration trust | Verifies association with the right registered IdP | Signature validation |
| `AudienceRestriction` | Assertion is intended for this SP/`entityID` | Recipient/ACS and expiration |
| `Recipient`/`Destination` | Assertion/Response was delivered to the right endpoint | Expiration and request correlation |
| `InResponseTo` + session/request context | Response belongs to a pending login request in SP-initiated flows | Signature and overall anti-replay |
| `NotBefore`/`NotOnOrAfter` | Assertion is valid only within the time window | Signature and session lifecycle |
| `SubjectConfirmationData` | Subject may be accepted by SP under delivery/confirmation constraints | Other conditions |
| Replay detection | ID/response/assertion/ticket cannot be illegally reused | Digital signature verification |
| Assertion encryption | Content confidentiality from parties without the decryption key | Sender authentication |

**Example:** An Assertion is validly signed yet `Audience` is another SP, so it **must not be used** to log into the current SP. A valid assertion whose `NotOnOrAfter` has passed is also rejected. An assertion containing `role=admin` should map to privileges only when covered by a trusted signature and permitted by authorization policy.

## 4. What Is EncryptedAssertion? How Does It Differ from a Signature?

Instead of placing a readable `<saml:Assertion> ... </saml:Assertion>` in the XML, the IdP can produce:

~~~xml
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
                ID="_resp003">
  <saml:Issuer>https://idp.example.org</saml:Issuer>
  <saml:EncryptedAssertion>
    <xenc:EncryptedData Type="http://www.w3.org/2001/04/xmlenc#Element">
      <xenc:EncryptionMethod Algorithm="..."/>
      <xenc:CipherData>
        <xenc:CipherValue>BASE64_CIPHERTEXT_PLACEHOLDER</xenc:CipherValue>
      </xenc:CipherData>
    </xenc:EncryptedData>
    <!-- EncryptedKey/KeyInfo can be placed at the appropriate position -->
  </saml:EncryptedAssertion>
</samlp:Response>
~~~

This is an **illustrative skeleton, not complete valid XML Encryption**. The encryption standard uses a symmetric algorithm for content and usually protects the content key with the SP's public key (hybrid encryption). Only the SP holding the matching **decryption private key** can read the assertion. `EncryptedKey` can appear in XML Encryption structures as managed by the library; do not assume a fixed placement or parse Base64 strings manually instead of using a library.

### 4.1. Each Mechanism Serves One Purpose

| Aspect | Response Signature | Assertion Signature | EncryptedAssertion |
|---|---|---|---|
| Placement | `ds:Signature` on Response | `ds:Signature` on Assertion | `saml:EncryptedAssertion` replacing plaintext assertion |
| Primary purpose | Protect Response and content covered by signature | Protect specific assertion | Keep assertion confidential |
| Creator | IdP signs with signing key | IdP signs with signing key | IdP encrypts for SP using SP encryption key/certificate |
| Verifier/processor | SP uses IdP verification credential | SP uses IdP verification credential | SP uses decryption private key |
| Can someone holding SAML POST read NameID? | **Possibly**, if assertion is plaintext | **Possibly**, if assertion is plaintext | Normally **no**, if properly encrypted and private key is safe |
| Protects against forged/tampered assertions? | Yes, **if signature is valid and covers the right assertion** | Yes, **for the properly signed assertion** | **Insufficient** from confidentiality alone; still needs integrity/authentication and policy |
| Replaces audience/time checks? | No | No | No |

**Critical explanation:** “Encrypted” does not mean “signed.” An attacker can obtain the **SP's public certificate** (often published in metadata) and in principle construct ciphertext to send to the SP; the system **must not treat successful decryption as proof the IdP issued it**. Even when authenticated encryption guards against ciphertext tampering, **issuer/federation authentication** and SAML condition requirements still apply.

Similarly, “signed” does not mean “encrypted”: a signature does not hide the user's email, HR attributes, identifiers, or groups in the browser POST. HTTPS is necessary, yet distinct from **end-to-end assertion encryption to the SP** because the browser is an intermediary in the HTTP-POST binding.

### 4.2. Signing and Encryption Can Be Combined

Four common patterns:

| Pattern | Diagram | How the SP interprets it |
|---|---|---|
| A. Response signed; plaintext Assertion unsigned | `Signed(Response[Plain Assertion])` | Response signature protects the assertion inside the signed Response |
| B. Response unsigned; plaintext Assertion signed | `Response[Signed(Assertion)]` | Verify each assertion, then Response/request rules |
| C. Response signed; Assertion encrypted | `Signed(Response[EncryptedAssertion])` | Verify outer signature then decrypt; ciphertext is inside signed Response |
| D. Assertion signed **then** encrypted | `Response[Encrypt(Signed(Assertion))]` | Decrypt first to reveal assertion signature, then verify inner signature |

**C + D** can be combined: sign the assertion, encrypt the signed assertion, then sign the outer Response. This produces **two signatures at two different layers** and two corresponding verification operations.

The Response signature can cover the **ciphertext** of `EncryptedAssertion` without seeing plaintext. The Assertion signature resides **inside the ciphertext** if the assertion itself was signed prior to encryption.

### 4.3. Order of Sign/Encrypt and Verify/Decrypt

If the IdP performs:

~~~text
1. Create plaintext Assertion
2. Sign Assertion: Signed(Assertion)
3. Encrypt signed Assertion: Encrypt(Signed(Assertion))
4. Place EncryptedAssertion inside Response
5. (Depending on config) sign the outer Response
~~~

then the SP must execute in the **reverse** logical order:

~~~text
1. If Response has a signature, verify valid Response signature
2. Decrypt EncryptedAssertion using SP private key
3. Verify signature of decrypted Assertion (if present)
4. Check issuer, audience, subject confirmation, validity window, replay
5. Only last, create login session and grant permissions
~~~

Inside a library, the exact order of same-layer checks may be optimized, yet **unverified information must never be used to grant permissions**. Decryption must be paired with proper integrity/authenticity checks: OASIS errata warn about **malleability of certain CBC encryption modes** and recommend verifying ciphertext integrity **before processing**. For `EncryptedAssertion` using CBC encryption, OASIS Web Browser SSO errata state the Response **SHOULD** be signed to protect the ciphertext. Modern authenticated encryption algorithms must be compatible across IdP/SP and cryptographic policy; never pick unsupported algorithms yourself.

**Encrypting elements inside an already-signed Assertion:** If a `NameID` or `Attribute` is encrypted first and then the Assertion is signed, you must **verify the assertion signature before decrypting the inner element** so you do not alter signed XML content. This is why some libraries separate Response decrypters from Assertion decrypters.

## 5. Why Does a Signed Response Still Need Assertion Checks?

There are two separate points:

1. **Signature verification:** With the right profile and verifier, a Response signature protects the assertion content **inside the signed Response**, so that assertion does not necessarily need its own signature. Per Spring Security SAML2 Login documentation, by default **either the Response or all Assertions must be signed**, and a signature that is present yet invalid is rejected.
2. **Assertion condition verification:** A Response signature only guarantees data was not tampered with and came from a trusted signer; it **does not** guarantee the assertion is unexpired, meant for this SP, or authorized. Those exact conditions must be read and checked **after integrity is assured**.

Likewise, an Assertion signature does not exempt checking request/callback information on the Response. If the IdP does not sign the Response, fields outside the Assertion are not automatically covered by the Assertion signature; the SP must still validate per profile against trusted endpoint/registration/request data.

**Counterexample:** A validly signed Response contains a validly signed assertion whose `NotOnOrAfter` is in the past. The signature is valid **and** content integrity is intact; the result is still **login failure due to expiration**.

## 6. Trust, Certificates, and Putting Keys on the Right Side

In signed + encrypted SAML communication, there can be **three** distinct keypairs:

| Operation | Who holds the private key? | Who needs the public certificate/key? |
|---|---|---|
| IdP **signs Response/Assertion** | **IdP** | **SP** to verify |
| IdP **encrypts Assertion for SP** | **SP** holds decryption private key | **IdP** gets SP's public certificate to encrypt |
| SP **signs AuthnRequest/LogoutRequest** if needed | **SP** | **IdP** to verify requests from SP |

Do not confuse the **IdP verification certificate** with the **SP decryption certificate**: both can be X.509, yet their owners, roles, and private keys differ. Organizations sometimes reuse a keypair, but it is better to govern them separately by purpose, access control, lifetime, rotation, and partner requirements.

**SAML Metadata** typically distributes `entityID`, endpoints, bindings, and `KeyDescriptor use="signing"/"encryption"`. However:
- Trust metadata only from trusted channels/processes; never dynamically load an unverified metadata URL supplied by a request.
- Verification credential configuration can hold multiple certificates concurrently during **rotation**; each must still stay bound to the right IdP/issuer.
- Never put SP decryption private keys in Git, logs, public images, or web directories; grant minimal file permissions or use managed secret storage.
- Old/new cert overlap may be needed during rollout. “Certificate mismatch” errors must be diagnosed carefully; **never disable signature validation** to make login work.

**TLS** must still be used for ACS, IdP SSO endpoints, metadata fetches, and key exchanges. SAML signatures do not replace HTTPS, just as HTTPS does not replace SAML verification.

## 7. How Spring Security/OpenSAML Processes Response and Assertion

In a **Spring MVC/Servlet** application using `spring-security-saml2-service-provider`, Spring Security acts as the **SAML SP**. Spring Security documentation describes the flow:

1. HTTP POST to ACS with parameter `SAMLResponse` is received by `Saml2WebSsoAuthenticationFilter`.
2. `Saml2AuthenticationTokenConverter` builds the authentication token and resolves the configured IdP's `RelyingPartyRegistration`.
3. `OpenSaml5AuthenticationProvider` (in documentation branches using OpenSAML 5) decodes the XML serialization and **verifies the Response signature** if present; fails if invalid.
4. The provider **decrypts any `EncryptedAssertion`s**; fails on decryption error.
5. Validates Response-level values such as `Issuer` and `Destination`.
6. **Verifies each Assertion's signature**: fails if present and invalid; fails if both the Response and all Assertions lack signatures. A signed Response or **all** assertions signed is the documented default requirement.
7. Decrypts encrypted elements **inside the Assertion**, such as `EncryptedID` or `EncryptedAttribute`, at the proper stage so the assertion signature is not broken.
8. Validates expiration, `SubjectConfirmation`, `AudienceRestriction`, and related checks.
9. Only after all steps succeed does it create `Saml2AuthenticatedPrincipal` and `Saml2Authentication`, storing them in the security context.

This is an **overview of the default documented pipeline**, not a substitute for checking your active version's configuration. Customizing response/assertion validators, decrypters, resolvers, or `AuthenticationManager` can alter protections; never drop mandatory checks.

Documentation also separates two decryption extension points: `setResponseElementsDecrypter` for Response-level elements (including `EncryptedAssertion`) and `setAssertionElementsDecrypter` for elements inside an Assertion, because **decrypting elements inside a signed Assertion too early** can invalidate its signature. Never swap the order of these two decrypters casually when customizing.

## 8. Spring Boot 3/4 and Corresponding Spring Security Example

### 8.1. Dependencies and Java Application

A **Servlet** application needs at least web, security, and the SAML2 SP module (versions managed by Spring Boot BOM). The Maven dependency snippet below is **not a complete `pom.xml`**; place it inside `<dependencies>` of a Spring Boot project already configured for Java 17+ and dependency management:

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

Some OpenSAML versions have required an extra Maven repository per Spring Security/BOM guides. Use dependency versions and Maven repositories **required by your project's documentation branch**; do not mix Spring Security 6 and 7 by guesswork.

File `src/main/java/com/example/sso/SamlSecurityApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP demo";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

The code has valid Java imports and structure for the matching Spring Security Servlet DSL; however, it **does not run with `javac` alone** because it depends on Spring Boot/Security and an IdP. In a Maven project with Maven Wrapper, after configuring credentials and SP at the IdP, run:

~~~bash
./mvnw spring-boot:run
~~~

`GET /` returns HTTP body `SAML SP demo` (once the server starts cleanly). `GET /private` requires SAML login and, if the IdP authenticates and the Response is accepted, returns `Authenticated`. Do not assume fixed console stdout, redirect URLs, or real users without a running IdP.

### 8.2. Signing and Decryption Configurations Are **Two Different Credential Types**

Example `src/main/resources/application.yml` (**illustrative paths**; use real certs/keys configured with the IdP, never commit private keys into the repo):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://sp.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://sp.example.org/login/saml2/sso/corporate"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml-sp-decrypt-key.pem"
                  certificate-location: "file:/run/secrets/saml-sp-decrypt-cert.pem"
            assertingparty:
              entity-id: "https://idp.example.org/entity"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing.crt"
~~~

**Property version note:** Configuration keys and where ACS/service-provider settings live depend on your Spring Boot version. Before using verbatim, check `Saml2RelyingPartyProperties` for your running Spring Boot release; the lower-risk approach when the IdP has trusted metadata is `assertingparty.metadata-uri` combined with `decryption.credentials`. The URLs, entityIDs, and file paths above are purely illustrative; if IdP/SP metadata or proxy callbacks differ, login will fail.

Meaningful sections:

- **`assertingparty.verification.credentials`:** the **IdP's** public cert for verifying signatures on incoming Responses/Assertions.
- **`decryption.credentials`:** SP private key + SP cert for decrypting incoming `EncryptedAssertion`s.
- **`signing.credentials`** (if configured): SP private key + cert used to **sign outgoing AuthnRequest/logout** messages. These are not certificates for verifying IdP Responses.
- **`assertingparty.metadata-uri`** (if used): loads and registers `entityID`, endpoints, signing certs, etc. from trusted IdP metadata.
- **`entity-id` and ACS URL** must match the IdP-side setup; behind a reverse proxy, handle scheme/host from trusted proxies properly.

Without an SP decryption private key, a valid Response containing `EncryptedAssertion` still **cannot log the user in** because it cannot be decrypted. If the decryption key works yet the IdP verification cert is missing, **never accept** the assertion as if ciphertext alone were a trusted origin.

**Never casually disable signature verification** in `OpenSamlAuthenticationProvider` or replace the converter with a parser reading raw XML directly. Spring Security/OpenSAML already handles canonicalization, signature validation, assertion conditions, and required extension points; misconfigured trust or custom validators introduce subtle security bugs.

## 9. Metadata Interoperability: What Must IdP and SP Agree On?

For successful deployment, both parties must agree on **distinct fields**:

1. **IdP entityID/Issuer:** SP accepts the exact right issuer.
2. **IdP signing certificate:** SP uses it to verify signatures. Add new certificates following rollover procedures.
3. **SP entityID/Audience:** Assertion targets this exact SP; do not pick based on an arbitrary hostname.
4. **ACS URL/binding:** HTTP-POST receives `SAMLResponse`, matching recipient/destination.
5. **Signature placement requirement:** response signed, assertion signed, or both per profile/partner policy.
6. **Encryption requirement:** plaintext vs. encrypted assertion; compatible algorithms/crypto policy; **SP decryption cert** shared with IdP.
7. **SP signing cert:** if the IdP mandates signing `AuthnRequest` or `LogoutRequest`.
8. **Clock skew, request correlation, replay:** acceptance limits; clocks synchronized across both systems.
9. **NameID/claims/groups:** which attributes are required, intended purpose, and authority mapping rules.

**Example when a partner says “your application must send a cert”**: ask whether it is the **SP signing certificate** for `AuthnRequest` or the **SP encryption certificate** so the IdP can encrypt assertions; they might also need both. Their purposes differ even if a sample config uses the same cert file.

## 10. Combinations and Expected Verification Outcomes

| # | Response signed? | Assertion signed? | Assertion encrypted? | Conditional expectation |
|---|---|---|---|---|
| 1 | Yes, valid | No | No | Acceptable if all SAML conditions, profile, and SP policy pass |
| 2 | No | Yes, valid on **all** assertions | No | Acceptable if all SAML conditions and policy pass |
| 3 | Yes, valid | Yes, valid | No | Acceptable when remaining conditions pass |
| 4 | No | No | No | **Reject** in default SAML Browser SSO HTTP-POST / Spring Security |
| 5 | Yes, but invalid signature | Yes, valid | No | **Reject**: a present yet invalid signature cannot be ignored |
| 6 | Yes, valid | Yes, but invalid signature | No | **Reject** per the documented Spring Security pipeline |
| 7 | Yes, valid | No | Yes | Decrypts cleanly and Response signature protects ciphertext, then check all conditions before accepting |
| 8 | No | Yes **inside ciphertext**, valid | Yes | Acceptable only after decryption, signature verification, and policy; protect ciphertext/integrity before decryption per algorithm and profile |
| 9 | No | No | Yes | **Never accept merely because decryption succeeded**; lacks trusted issuer proof |
| 10 | Yes, valid | No | Yes, but wrong private key | **Reject** due to decryption failure |
| 11 | Yes, valid | Yes, valid | No, yet expired / wrong Audience | **Reject** despite valid signatures |
| 12 | Yes, valid | Yes, valid | No, yet IdP key not trusted by SP | **Reject** due to trust verification failure |

Rows marked “**Acceptable**” always assume issuer, destination/recipient, `InResponseTo`, signature references, status, subject confirmation, conditions, anti-replay, and TLS/registration are all valid. This is a **security semantics matrix**, not a tool for relaxing profile or partner requirements.

### Two Easily Confused Scenarios

**Scenario A — Response signed, Assertion unsigned, still standard-compliant login:** The SP can accept it if the Response signature covers the right assertion, algorithms/certs are trusted, and the IdP plus all conditions pass. Do not falsely flag “missing signature inside assertion” when the system contract permits Response signing.

**Scenario B — Assertion encrypted, login fails despite “having a certificate”:** The IdP may be using a **new SP public certificate** while the SP still holds an **old private key**, or using an encryption keypair different from the signing keypair; inspect the exact keypair and metadata rather than swapping in the IdP signing certificate.

## 11. Systematic Troubleshooting

| Symptom | Possible cause | Verification step |
|---|---|---|
| `Signature validation failed` | Wrong/expired IdP cert, key rollover, altered signature/digest, mismatched signature Reference | Check trust metadata, issuer, cert fingerprints for the right environment, algorithms, and XML signature library |
| Response signature present, yet validator reports missing signature protecting assertion | Signature does not cover the consumed assertion, config requires Assertion signing, or multiple unsigned assertions exist | Check SP policy, assertion count, exact signed node, and Reference |
| `EncryptedAssertion` fails to decrypt | Wrong SP key, key location/permissions, unsupported algorithm, cert IdP encrypted with does not match key | Compare private key–public cert pair, check permissions and algorithms |
| Decryption succeeds yet login fails | Invalid Assertion signature, issuer/audience/time/subject confirmation error, replay | Inspect step-by-step validation error without removing security checks |
| Valid `NameID` present yet still 401/403 | Authentication not created, missing authority mapping, or application policy | Distinguish authentication failure from authorization failure |
| Intermittent failures around rotation | Multiple nodes hold different cert/key versions; metadata cache out of sync | Plan key overlap, rollout, and fingerprint/version logging |
| Timing anomalies | NTP drift, `NotBefore`/`NotOnOrAfter`, `InResponseTo` cache evicted | Sync clocks, check request store and minimal allowed clock skew |
| Wrong ACS URL behind reverse proxy | App sees internal HTTP/local hostname while IdP uses external HTTPS URL | Check trusted forwarded headers, entityID/ACS, `Recipient`/`Destination` |
| Login succeeds when old request is replayed | Weak replay cache/correlation or missing session handling | Enable request context and assertion/replay ID checks per profile |
| Security parser picks wrong Assertion | XML Signature Wrapping, duplicate IDs, or parser querying tags by name | Use hardened OpenSAML validator and verify the exact consumed node |

**Avoid troubleshooting by:** disabling signature validation, trusting all `KeyInfo`, setting huge clock skew, allowing any `Destination`/`Audience`, dumping full SAML assertions/PII to production logs, or storing private keys in public applications.

## 12. Integration Testing and Message-Reading Exercises

### 12.1. Meaningful Test Scenarios

Use a test IdP matching the right tenant and test environment to exercise:

- **Response signed only**: unsigned plaintext assertion; SP per config accepts valid Response signature.
- **Assertion signed only**: unsigned outer Response; validator must check signed assertion and protocol/subject conditions properly.
- **Both signed**: alter one character in Response or Assertion after IdP issuance; validator must reject.
- **Encrypted + Response signed**: valid SP decryption key configured → parses cleanly; wrong/missing key → fails.
- **Signed then encrypted assertion**: decrypt, verify inner signature, then check conditions; alter digest/signature → fails.
- **Encrypted but unsigned**: never treat decryption success as authentication proof.
- **Expiration & audience**: signature remains valid yet expired/wrong audience/recipient → fails.
- **Replay & wrong request**: replay a Response or mismatch `InResponseTo` against pending request → reject when profile rules require.
- **Key rollover**: IdP uses new cert, SP was provisioned trust properly; if not yet provisioned, fail closed.
- **XML Signature Wrapping**: response contains duplicate ID structures or an assertion outside signature protection → fails, never consumes an arbitrarily selected tag.

Tests should start with SAML responses emitted by a **real test IdP** or SAML test harness. Never hand-edit XML expecting the signature to stay valid; that is why negative tests must assert expected **FAIL** outcomes. Never write your own XML signature verifier using custom XPath.

### 12.2. Self-Check Exercises

**Exercise 1:** An assertion is encrypted, with no Response or Assertion signature. The SP decrypts the username cleanly. May it create a session?

**Answer:** No. Decryption proves the SP holds the matching private key, not that the assertion was signed by a trusted IdP or satisfies authentication conditions.

**Exercise 2:** The Response is validly signed, and the inner Assertion is unsigned. Is that automatically “non-standard”?

**Answer:** No. In HTTP-POST Web Browser SSO, the standard/errata and providers can accept a Response signature covering the assertion; SP/partner policy may additionally require Assertion signing.

**Exercise 3:** An Assertion has a valid `ds:Signature`, yet `AudienceRestriction` names a different application. Outcome?

**Answer:** Reject. Valid integrity does not mean the assertion is permitted at this SP.

**Exercise 4:** The IdP signs the Assertion and then encrypts the entire Assertion. Must the SP verify the inner signature before decrypting?

**Answer:** Impossible: the signature sits inside the ciphertext, so the SP must decrypt first and then verify the signature. If the outer Response is also signed, verify the outer signature first following the proper verification sequence.

**Exercise 5:** The IdP imported the SP certificate into metadata to encrypt assertions; does the SP need a private key?

**Answer:** Yes. The IdP uses the SP's public key/certificate to encrypt; the SP uses the corresponding private key to decrypt.

**Exercise 6:** When does the distinction between Response signature and Assertion signature become critical?

**Answer:** When there are multiple assertions, Response-level data outside the assertion, XML signature wrapping, policies requiring a specific signing layer, and when combined signing–encryption mandates a strict verification/decryption order.

## 13. Practical Checklist Before Taking SAML SSO to Production

1. Confirm **SP/IdP roles**, HTTP-POST/Artifact binding, `entityID`, ACS URL, issuer, and applicable profile.
2. Finalize integration docs on **sign Response, sign Assertion, or both**; never guess from a single base64 sample.
3. Configure **IdP verification credentials** from trusted metadata; never read keys from unverified requests.
4. If **EncryptedAssertion** is needed, give the **SP public encryption cert** to the IdP and keep the **SP decryption private key** secure. Agree on algorithms.
5. If **signed AuthnRequest** is needed, use a dedicated **SP signing key** in its proper role; do not confuse it with decryption credentials.
6. Verify response/assertion signatures over the right data scope; harden the XML parser and guard against wrapping/replay.
7. Check `Status`, `Issuer`, `Destination`, `InResponseTo`, `AudienceRestriction`, `SubjectConfirmationData`, `NotBefore`/`NotOnOrAfter`, and pending request context.
8. Map `NameID`/attributes/roles in a controlled way; never grant admin roles just because XML contains a role string.
9. Run full **positive/negative tests**, key rotation, clock drift, proxy callback bugs, and logout/session flows.
10. Log technical errors by event/code without logging full assertions, tickets, private keys, or sensitive attributes; alert before certificates/keys expire.

## 14. Standards and Spring Security Documentation

- **OASIS SAML 2.0 Errata 05** (Response/Assertion signing, sign+encrypt, integrity): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html
- **OASIS SAML Core** (Assertions and Protocols): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **Spring Security – SAML2 Login Overview** (signature → decrypt → assertion validation pipeline): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security – Authenticating SAML2 Responses** (custom validators/decrypters): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Boot – SAML2 Relying Party Properties**: https://docs.spring.io/spring-boot/reference/security/saml2.html
- **OWASP SAML Security Cheat Sheet** (signature wrapping, trust, assertions): https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Remember:** *Response signed* protects the signed Response scope; *Assertion signed* protects the individual assertion; *EncryptedAssertion* hides content for the SP. For secure login, you must **protect and verify the exact content consumed by the application**, **check SAML conditions**, and manage trust keys and sessions. All configuration examples must be cross-checked against your actual Spring Boot/Spring Security version.
