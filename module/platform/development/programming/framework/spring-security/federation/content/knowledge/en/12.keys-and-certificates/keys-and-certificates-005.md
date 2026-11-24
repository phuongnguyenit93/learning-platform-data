# Choosing signature algorithms, hash functions, and weak algorithm rejection policies in SAML 2.0

> **Context:** Spring Security – federation → **Keys and certificates**. This lesson is for Java/Spring Security applications acting as a SAML Service Provider (SP) and Identity Provider (IdP) administration teams. Content distinguishes **digital signature algorithms**, **hash functions (digests)**, **X.509 certificate signing algorithms**, key selection, allow/deny policies, applying them to SAML HTTP-Redirect/XML Signature, and verification points when Spring Security/OpenSAML integrates with multiple IdPs. Standalone examples use Java 17+; Spring snippets require real dependencies/configuration.

## 1. Why is a "valid signature" alone not enough?

In SAML 2.0, a browser can send a `SAMLResponse` containing an assertion to the SP. A digital signature may verify mathematically **yet still be unacceptable** because:

- The message specifies `rsa-sha1`, `hmac-sha1`, or `sha1` digest, violating policy against weak algorithms.
- The signature uses a key from an unregistered IdP, or mistakenly trusts a certificate supplied by untrusted XML `KeyInfo` itself.
- An Assertion outside the signature-protected region is still read by code to build a principal (XML Signature Wrapping).
- The RSA key is too short or the certificate/key violates policy.
- The signature protects part of the XML yet `Audience`, `Recipient`, `Destination`, `InResponseTo`, or time conditions are wrong.
- The SP confuses the **X.509 certificate signing algorithm** with the **SAML XML SignatureMethod** and accidentally allows a weak XML method.

Thus **authentication succeeds only when simultaneously** an approved algorithm is used, the key is trusted and strong enough, the signature covers the actual data consumed, and all SAML protocol checks pass. Parsing XML or a single library returning `signature.verify=true` is insufficient.

### Learning objectives

After this lesson, you will be able to:

1. Properly read `ds:SignatureMethod`, `ds:DigestMethod`, `ds:CanonicalizationMethod`, `ds:Reference`, and `ds:SignatureValue`.
2. Distinguish a **JCA name** like `SHA256withRSA` from an **XMLDSig URI** like `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256`.
3. Select a justified algorithm **allowlist**, typically taking RSA-SHA256 and SHA-256 as the compatibility baseline; evaluate RSA-SHA384/512, ECDSA, or RSA-PSS when supported by both sides.
4. Reject SHA-1/MD5 and unapproved options without automatic downgrade, even when technical verification succeeds.
5. Apply rules differently for **SP signing AuthnRequest** vs. **SP verifying IdP-signed Response/Assertion**.
6. Understand Spring Security config limits: **signingAlgorithms** options for **outbound AuthnRequests** do not automatically become an allowlist for **inbound SAMLResponse signatures**.
7. Set per-IdP/tenant acceptance policies, perform key rotation, write negative tests, and log safely.

## 2. Three algorithm layers to distinguish

| Layer | Location/field | What does it protect? | Example |
| --- | --- | --- | --- |
| **XML SignatureMethod / HTTP-Redirect SigAlg** | `<ds:SignatureMethod Algorithm="...">` or query `SigAlg` | Creates/verifies signature over binding-prepared data | RSA-SHA256 |
| **XML DigestMethod** | `<ds:DigestMethod Algorithm="...">` inside `ds:Reference` | Hashes referenced content after transforms before feeding into signature structure | SHA-256 |
| **X.509 certificate signature algorithm** | signatureAlgorithm field in certificate | Algorithm CA or self-signer used to sign the **certificate**, not the XML message | sha256WithRSAEncryption |
| **TLS cipher suite/certificate** | HTTPS between browser – IdP/SP | Protects transport connection; does not replace SAML message signatures | TLS 1.3 |
| **XML Encryption** | `EncryptedAssertion` / `EncryptedAttribute` | Content confidentiality; distinct from integrity and issuer authentication | AES-GCM per profile/support |

For example, an IdP can have a certificate self-signed with `sha256WithRSAEncryption` while a SAML Assertion still uses `rsa-sha1` in `ds:SignatureMethod`. A certificate signed with SHA-256 **does not make the SAML signature SHA-256**. The SP must inspect **both the certificate and XML Signature** per policy.

Conversely, an `rsa-sha256` XML Signature does not guarantee an adequately long RSA key: a 1024-bit RSA key does not equal 2048/3072-bit strength. Therefore policy must enforce **algorithm + digest + key strength + trust + signature coverage**.

## 3. Signature roles by SP/IdP direction

```text
SP                         Browser                         IdP
 |-- AuthnRequest ------------>|------------------------------>|
 |   SP private signing key   |                               |
 |   IdP verifies with SP public certificate                  |
 |                             |                               |
 |<----------------------------|<---- SAMLResponse/Assertion --|
 |                                  IdP private signing key   |
 |   SP verifies with trusted IdP public signing certificate  |
```

**AuthnRequest:** issued by the SP. When the IdP requires `WantAuthnRequestsSigned=true` or SP policy mandates signing, the SP must use the **SP's own** private signing key. HTTP-Redirect uses `SigAlg` and `Signature` in query parameters; HTTP-POST typically uses XML Signature inside the AuthnRequest.

**SAMLResponse/Assertion:** issued by the IdP. The SP must verify with the public certificate/key **registered for that IdP** before accepting identity. Depending on SAML profile and policy, the signature may be on `Response` or `Assertion`; crucially, **the assertion actually used to log in must lie within the signed and verified scope**. If the system requires each Assertion to be individually signed, do not accept a signed Response alone as satisfying that specific requirement.

**Do not swap:** SP `signing.credentials` are not verification credentials for the IdP; the IdP verification certificate has no private key for the SP to sign requests.

## 4. Anatomy of an XML Digital Signature in an Assertion

The example below is an **XML snippet illustrating algorithms**, not a valid assertion or verifiable signature. The `BASE64_SAMPLE_NOT_VALID` strings are dummy data:

```xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod
      Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
    <ds:SignatureMethod
      Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
    <ds:Reference URI="#_assertion_001">
      <ds:Transforms>
        <ds:Transform
          Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
        <ds:Transform
          Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      </ds:Transforms>
      <ds:DigestMethod
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
      <ds:DigestValue>BASE64_SAMPLE_NOT_VALID</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>BASE64_SAMPLE_NOT_VALID</ds:SignatureValue>
</ds:Signature>
```

Reading in order:

1. `Reference URI="#_assertion_001"` points to the SAML element with the matching ID. This is the **object whose content is digested**, not a filename or arbitrary network URL to fetch.
2. `Transforms` defines operations applied to the referenced content prior to hashing. `enveloped-signature` strips the embedded signature from the hashed target in that structural style; exclusive canonicalization normalizes XML representation.
3. `DigestMethod` specifies the hash function, e.g., SHA-256. `DigestValue` is the digest of the post-transform data.
4. `SignedInfo` contains digest references and algorithm metadata. `CanonicalizationMethod` governs canonicalization of `SignedInfo` before signing.
5. `SignatureMethod` specifies how `SignedInfo` is signed/verified, e.g., RSA with SHA-256. `SignatureValue` holds the encoded signature.
6. `KeyInfo` (if present) may hint at a key yet is **never a self-proving trust source**. The SP must match the signing key against an approved certificate/IdP registration.
7. The SP must confirm the **signed element is the exact Response/Assertion used to build Authentication**, preventing reading another unsigned Assertion in the same XML.

**Two distinct checks:** each reference's digest must match the post-transform content, and the signature over `SignedInfo` must validate under a trusted key. Checking only one step, or verifying one element while reading claims from another, still leaves the app vulnerable to spoofing.

### 4.1. Canonicalization is not a hash algorithm

XML allows multiple text representations with equivalent structure: namespace prefixes, attribute order, line breaks, or encodings. Canonicalization (`C14N`) determines the canonical bytes to sign/verify; `SHA-256` then hashes those bytes. `C14N` **does not** replace SHA-256 and does not produce a signature itself.

Choices of `CanonicalizationMethod`/`Transform` must also be restricted per SAML/XMLSig profile and threat model. An XML Signature containing excessive transforms, XSLT, or external references can cause parsing abuse/SSRF/altering checked data. In XML Security libraries, enable secure validation and restrict reference URIs, transform chains, and reference counts. Never write custom DOM/XPath parsers bypassing schema/ID uniqueness.

### 4.2. Reference URI, ID uniqueness, and XML Signature Wrapping

Suppose a valid signature covers only `Assertion ID="_signed_a"`, while the XML also contains `Assertion ID="_unsigned_b"` granting admin rights. If code arbitrarily picks the "first assertion" or calls `getElementsByTagName("Assertion")`, a passing verification does not make the unsigned data trustworthy.

Requirements: parse documents safely, enforce ID uniqueness/namespaces, ensure reference URI targets the **exact** object, confirm signature coverage of the object used for authentication, and reject signed/unsigned ambiguity. OWASP recommends hardening XML validation and avoiding loose XPath selection of security elements.

## 5. SAML/XMLDSig algorithm URI table

| Algorithm / mechanism | Example URI | Role | Typical policy |
| --- | --- | --- | --- |
| RSA-SHA256 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256` | XML SignatureMethod / Redirect SigAlg | **Allow** when key is strong enough and IdP/SP support it |
| RSA-SHA384 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha384` | SignatureMethod / SigAlg | Allow when genuinely supported and approved |
| RSA-SHA512 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha512` | SignatureMethod / SigAlg | Allow when compatible |
| ECDSA-SHA256 | `http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256` | XML SignatureMethod | Allow when EC cert/IdP/SP/libraries all support it |
| SHA-256 | `http://www.w3.org/2001/04/xmlenc#sha256` | XML DigestMethod | **Allow** |
| SHA-384 | `http://www.w3.org/2001/04/xmldsig-more#sha384` | XML DigestMethod | Allow if library and agreement support |
| SHA-512 | `http://www.w3.org/2001/04/xmlenc#sha512` | XML DigestMethod | Allow if supported |
| RSA-SHA1 | `http://www.w3.org/2000/09/xmldsig#rsa-sha1` | Legacy signature | **Reject** under modern policy |
| HMAC-SHA1 | `http://www.w3.org/2000/09/xmldsig#hmac-sha1` | Legacy MAC; cannot replace IdP X.509 trust | **Reject** in IdP/SP profiles requiring asymmetric signing |
| SHA-1 digest | `http://www.w3.org/2000/09/xmldsig#sha1` | Weak XML DigestMethod | **Reject** |
| RSA-MD5 / MD5 digest | Corresponding XML Signature/Encryption URIs | Obsolete, poor collision resistance | **Reject** |
| `null`/empty/unrecognized URI | Invalid/missing | No trusted algorithm identifier | **Reject** |

**Distinguish URIs from JCA names.** SAML/XMLDSig uses URIs; Java JCA typically uses `SHA256withRSA`, `SHA384withRSA`, `SHA512withRSA`, `SHA256withECDSA`. They are not interchangeable strings: use maintained library mappings. Never rewrite `SignatureMethod Algorithm` to a stronger URI after signing; altering `SignedInfo` breaks the signature.

### 5.1. SHA-256 is a baseline, not a performance/security ceiling

2048-bit RSA + SHA-256 is broadly compatible and still cited by OWASP as a baseline; when both parties support it, 3072-bit RSA or stronger modern algorithms may suit longer key lifetimes and compliance needs. Using SHA-512 with a weak RSA key does not rescue key weakness; ECDSA P-256/SHA-256 can be efficient yet some IdPs do not yet support that key type.

**RSA-PSS** has cryptographic advantages and may be supported by newer XMLDSig standards, yet do not assume every IdP/SAML binding handles RSA-PSS. Select algorithms from the **intersection of both parties' capabilities** and approved policy, rather than picking solely by "largest hash bit size".

### 5.2. "Present in library" differs from "allowed by policy"

A JCA/OpenSAML library may parse or verify RSA-SHA1 signatures for historical compatibility. That does not mean a production app must accept them. An allowlist at the application security boundary must reject **before creating a principal**, even if verification for the legacy algorithm returns true.

Conversely, never let an attacker pick a "fallback option" via `SigAlg` or `DigestMethod` in the message. Those fields are inputs to **check against policy**, never allowed to dictate policy.

## 6. Signature acceptance policy: explicit allowlist and fail closed

### 6.1. Rule set to define

An illustrative policy for RSA-based SPs/IdPs:

```yaml
# This is an illustrative policy document, NOT Spring Boot properties.
samlSignaturePolicy:
  outboundAuthnRequest:
    approvedSignatureMethods:
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    approvedKeyTypes:
      - "RSA"
    minRsaBits: 2048
  inboundSamlResponse:
    approvedSignatureMethods:
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384"
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512"
    approvedDigestMethods:
      - "http://www.w3.org/2001/04/xmlenc#sha256"
      - "http://www.w3.org/2001/04/xmldsig-more#sha384"
      - "http://www.w3.org/2001/04/xmlenc#sha512"
    minRsaBits: 2048
    rejectUnknownAlgorithms: true
    rejectSha1AndMd5: true
    requireTrustedIssuerAndCertificate: true
    requireSignedAuthenticationContent: true
    verifyReferenceCoverage: true
```

**Reading the policy:** the example uses an inbound allowlist with RSA-SHA256/384/512, SHA-2 digests, and sufficiently strong RSA keys. Another IdP might be approved for ECDSA P-256/SHA-256. The fields above **do not configure the framework automatically**; they must be implemented in the actual OpenSAML/XML Security policy/validation integration for your version and tested with real signed fixtures.

A system must never treat a custom YAML flag like `rejectSha1AndMd5=true` as "protected" without code/framework enforcement. Prove it with an integration test: a SAMLResponse mathematically validly signed with RSA-SHA1 **is still rejected**.

### 6.2. Scoping policy per IdP/registration

With multiple IdPs, define approved suites per **governed registration** rather than an overly broad global list:

| Registration | Trusted certificate | Inbound allowed suite | Outbound request suite |
| --- | --- | --- | --- |
| `corp` | Approved corp IdP signing certs | RSA-SHA256 + SHA-256 | RSA-SHA256 |
| `partners` | Approved partner IdP signing certs | RSA-SHA384 + SHA-384 when compatible | RSA-SHA256 per IdP |
| `legacy-test` | Dedicated test signing cert | Legacy fixture for **negative** tests only | Never in production |

**Never accept IdP A's signature for issuer B** simply because both registrations use RSA-SHA256. An algorithm does not authenticate signer identity; the public key/trust binding to the specific IdP does.

### 6.3. Rejection policy should check in a sound order

1. Enforce HTTP payload limits, Base64 decode, and hardened XML parsing: no external entity access or remote references.
2. Identify the registration from **trusted context**; never fetch an IdP metadata URL or verification key from browser input.
3. Identify signatures and security-critical data regions requiring validation; require signing coverage per SAML profile/policy.
4. Check `SignatureMethod`, all used `DigestMethod`/references, and canonicalization/transforms against the allowlist/profile; reject unknown/weak algorithms.
5. Check key type/length, certificate/trust binding, and signed reference targets; perform signature/digest verification via OpenSAML/XMLSec.
6. Verify `Issuer`/`Audience`/`Destination`/`Recipient`/`InResponseTo`, timestamps, subject confirmation, and replay defenses.
7. Only upon success construct principal/authorities and session.

This is a **logical control order**, not a line-by-line description of every Spring Security/OpenSAML release. Crypto verification and algorithm checks may be coordinated by the library in its own order; what is mandatory is that **no acceptance path** bypasses policy.

### 6.4. Reject rather than downgrade

If an IdP proposes supporting only `rsa-sha1`, the SP should not automatically allow SHA-1 to achieve "SSO success". Proper procedure:

- Check IdP metadata/docs and test what algorithm it actually emits.
- Require the IdP to enable RSA-SHA256 or an approved suite, updating metadata/certs accordingly.
- If no permitted overlap exists, **do not deploy that flow**; log an interoperability blocker instead of disabling policy.
- For genuinely unavoidable legacy exceptions, follow a risk-governance process: approval, narrow scope, expiration date, and retirement plan; never add SHA-1 to a global allowlist or claim equivalent safety.
- Never edit `SignatureMethod` in XML or `SigAlg` in the query to "switch to SHA-256" after signing: the signature will break. The **signer** must actually re-sign with the agreed algorithm.

**External error message:** "Unable to complete SSO login." Internally, record a reason code like `WEAK_SIGNATURE_ALGORITHM` or `UNSUPPORTED_DIGEST_ALGORITHM` without echoing XML/KeyInfo/private keys.

## 7. Choosing keys and certificates to match algorithms

### 7.1. RSA or EC?

| Criterion | RSA | Elliptic Curve / ECDSA |
| --- | --- | --- |
| General SAML compatibility | Broad; most IdPs/SPs support out of the box | Depends on IdP, XML Security stack, and certificate |
| Minimum size to consider | **RSA ≥ 2048 bit** baseline; consider 3072 for longer lifetimes | **P-256** or approved curve |
| Common signing algorithms | RSA-SHA256/384/512 | ECDSA-SHA256/384 when curve-compatible |
| Where is the private key? | HSM/keystore/secret store with least privilege | Same |
| Common errors | 1024-bit RSA key, certificate/key mismatch | Using EC key when IdP supports only RSA |

**Never** switch an SP signing key to EC while the IdP has an RSA certificate registered; the algorithm must match the **actual key type**. RSA-SHA256 on an EC certificate will not verify properly. Note that RSA-PSS requires specific parameters/URIs and must not be treated as identical to RSA PKCS#1 v1.5 merely because both "use SHA-256".

### 7.2. Certificate checks

- Verify the certificate/key belongs to the **authorized trusted IdP** for the exact registration. `KeyInfo` inside XML is untrusted input, not a trust anchor.
- Per policy, check `notBefore/notAfter`, key usage/`digitalSignature`, certificate signing algorithm, key type, and rotation. In some SAML integrations, certificates may be self-signed yet pinned in trusted metadata; **HTTPS PKIX trust stores do not automatically verify SAML trust**.
- A certificate's signing algorithm may be SHA-256, yet XML `SignatureMethod` must still be checked **separately**.
- Certificate rollover should allow old + new keys during a monitored transition window; **never** accept an arbitrary certificate simply because a "new cert" arrived inside SAMLResponse.
- Never log private signing/decryption keys, return them in exceptions, or store them in Git source. If a private signing key leaks, treat as an incident and rotate trust per procedure.

### 7.3. Key rotation and algorithm migration are two independent migrations

An IdP may rotate its certificate while continuing to sign XML with RSA-SHA256; or retain a valid RSA key yet start emitting RSA-SHA384. Test **both dimensions**:

```text
Credential trust migration: old trusted cert → new trusted cert
Algorithm policy migration:  RSA-SHA256 → RSA-SHA384 (when approved)

Never infer one migration is complete merely because the other succeeded.
```

Monitor signature verification failures, unknown signing keys, unsupported algorithms, request/response compatibility, and certificates nearing expiry. Rollback plans must never re-enable SHA-1 or add trust for certificates of unknown origin.

## 8. Configuring Spring Security for signed AuthnRequests

### 8.1. What does Spring Security do by default?

Per Spring Security's documentation on "Producing AuthnRequests", Spring Security normally generates AuthnRequest signatures using **rsa-sha256** when signing is required; asserting party metadata can advertise supported signing algorithms and influence algorithm selection. To **actually sign**, the SP must hold a **private signing credential**. A flag in metadata **does not create a signature** if no key/cert exists.

When the IdP requires `WantAuthnRequestsSigned=true`, configure the SP accordingly; when the IdP does not require it, SP policy may still choose to sign proactively. Inspect **wire data** per binding rather than relying solely on YAML/metadata.

### 8.2. Spring Boot 3.x – illustrative YAML

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/idp"
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
```

This is a **simulated configuration**, requiring valid IdP registration/certificates/keys, the Spring Security SAML2 SP dependency, and matching binding/metadata. `{baseUrl}`/`{registrationId}` are **Spring Security URI template placeholders**, not tokens you must manually replace with copy-pasted literals.

Distinguish:

- `signing.credentials`: SP private key + public certificate to **sign AuthnRequest**.
- `assertingparty.verification.credentials`: IdP **public signing certificate** to **verify Response/Assertion**.
- `acs.binding=POST`: IdP sends response back to SP via POST; **does not dictate whether outbound request uses Redirect or POST**.
- `assertingparty.singlesignon.binding=REDIRECT`: browser transports AuthnRequest to IdP SSO via Redirect.
- `sign-request=true`: requests outbound signing; confirm actual key/cert/algorithm and compatibility with IdP metadata.

### 8.3. Minimal SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSignatureSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **Spring Security configuration class**, not a program runnable standalone with `java SamlSignatureSecurityConfiguration`. It enables SAML login and uses the configured RelyingPartyRegistration. **It does not by itself enforce an inbound SHA-1 deny policy** if the XML signature validator allows that algorithm. Check your version and algorithm configuration in the OpenSAML/XML Security layer.

### 8.4. Which direction does "signingAlgorithms" apply to?

Current Spring Security documentation shows how to **declare signing algorithms supported by the asserting party** so Spring Security picks the algorithm to sign **outbound AuthnRequests**; Java **version-dependent fragment**:

```java
import org.opensaml.xmlsec.signature.support.SignatureConstants;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

// Fragment inside registration config, not a standalone class.
// IdP metadata was already verified by an administrator before loading.
RelyingPartyRegistration rp =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .assertingPartyMetadata(party -> party
                .signingAlgorithms(algorithms -> algorithms.add(
                    SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512)))
            .build();
```

**Do not misunderstand this snippet:**

1. It updates **IdP algorithm support info for AuthnRequests sent from SP to IdP**; it **does not** configure Spring Security to reject `rsa-sha1` in **inbound SAMLResponse signatures from the IdP**.
2. Calling `add(RSA_SHA512)` is meaningful only if the IdP actually supports this algorithm and the SP has matching keys/config; do not use it to "force" an IdP that only accepts SHA-256.
3. You still need separate SP signing credentials, SP entityID/ACS, and IdP verification credentials via real metadata/config.
4. `assertingPartyMetadata(...)`, `SignatureConstants`, and OpenSAML options vary across versions; the code is a **reference fragment per current docs**—verify against your project's Spring Security release before using.
5. Adding an algorithm to the supported list **is not** a mechanism defining "allow only one algorithm"; do not infer priority order or actual emitted signature blindly. Inspect `SigAlg`/`SignatureMethod` on the emitted AuthnRequest.

If SP policy requires RSA-SHA256 yet the IdP only advertises RSA-SHA1, the right move is to **report an interoperability blocker and upgrade the IdP**, not add RSA-SHA1 to config as a "temporary workaround".

## 9. How HTTP-Redirect signatures and XML signatures differ

### 9.1. Signing AuthnRequest with HTTP-Redirect binding

Flow:

```text
AuthnRequest XML
  → raw DEFLATE
  → Base64
  → URL-encode into SAMLRequest
  → append RelayState (if present)
  → SigAlg URI + Signature (signs the formatted parameter string)
  → HTTP 302 to IdP SingleSignOnService
```

If RelayState is present, the signed binding payload is:

```text
SAMLRequest=<URL-encoded>&RelayState=<URL-encoded>&SigAlg=<URL-encoded>
```

When RelayState is absent, omit that component. `Signature` is not part of the signed string. The algorithm in `SigAlg` must be in the IdP's allowlist; signing with RSA-SHA256 does not mean the inner XML must carry `<ds:Signature>`.

A sent URL with `SigAlg=rsa-sha1` when the SP intends SHA-256 signals **policy mismatch/unsupported downgrade**; never "fix" it by altering the query parameter while keeping the old signature. The IdP must reject unapproved algorithms even if the signature bytes verify under SHA-1.

### 9.2. With HTTP-POST binding

AuthnRequest is typically signed via XML Digital Signature inside the XML and then Base64-encoded into the `SAMLRequest` form field. `SignatureMethod` and `DigestMethod` are declared in `ds:SignedInfo`/`ds:Reference`. The IdP must verify the XML signature and algorithms per IdP policy; do not treat a `SigAlg` query parameter as the sole check for POST.

SAMLResponse at the ACS also typically arrives via HTTP-POST containing XML signed on the Response or Assertion; the SP must verify XML signature coverage and digests. Redirect query signatures and POST XML Signatures are **two binding-specific message protections** and must not have their logic mixed.

## 10. Inbound SAMLResponse verification policy with Spring Security/OpenSAML

### 10.1. What the default provider does and policy gaps

Spring Security uses `Saml2WebSsoAuthenticationFilter`, authentication token converters, and the OpenSAML authentication provider to verify SAMLResponse/Assertion. The provider validates signatures, issuer, destination, assertion conditions, and protocol constraints per version. Recent Spring Security releases may rely on OpenSAML 5; Spring Security 6.x uses OpenSAML 4 or 5 depending on release/dependencies.

**Verify independently:** whether the provider and XML Security library in your application's version **actually reject SHA-1-based `SignatureMethod` and `DigestMethod`**. Never assume JVM/JCA defaults, the `sign-request` flag, or outbound `signingAlgorithms` automatically create an inbound denylist.

If the framework/library does not enforce the needed policy yet, configure **OpenSAML/XML Security supported algorithm policy/secure validation** or validation extensions **inside the authentication boundary before accepting a principal**, while keeping all default checks intact. Exact implementation must follow your release's API; never add a filter that manually parses raw SAMLResponse just to "peek at the algorithm" and bypass verification.

### 10.2. Secure algorithm pseudocode

```text
Input: HTTP POST ACS, SAMLResponse from browser (UNTRUSTED)
  -> enforce input size, parse XML securely and validate structure
  -> select TRUSTED RelyingPartyRegistration
  -> identify every signature/reference protecting authentication content
  -> reject disallowed SignatureMethod / DigestMethod / dangerous transforms
  -> reject weak/incorrect signing key; trust only registered IdP key(s)
  -> cryptographically verify signature and digest of signed XML objects
  -> reject missing/ambiguous coverage and XML signature wrapping
  -> verify issuer, audience, recipient, destination, time, InResponseTo,
     subject confirmation and replay controls
  -> only then create Authentication and map authorized roles
If any step fails:
  -> no SAML principal/session authentication
  -> generic browser error; internal allowlisted reason code
```

This is a **policy/validation design**, not literal Java code inside every `OpenSaml5AuthenticationProvider`. Never reorder checks across steps in a way that turns untrusted values into the user's key/issuer/role.

### 10.3. Checking both SignatureMethod and DigestMethod

An attacker can submit XML with:

- `SignatureMethod=rsa-sha256` yet `DigestMethod=sha1`.
- `SignatureMethod=rsa-sha1` and `DigestMethod=sha256`.
- A `Response` signature using RSA-SHA256, alongside an extra unprotected `Assertion`.
- Multiple `ds:Reference` elements where one reference is weak or has a URI pointing outside the document.

Policy must inspect **every signature/reference relevant to authentication data**, not just string checks like `SignatureMethod.contains("sha256")`. Never rely on arbitrary prefixes, suffixes, or case-insensitivity; compare against **exact approved URIs** and use proper parsers/schemas.

### 10.4. Secure validation does not replace full SAML policy

Apache Santuario (XML Security for Java) supports **secure validation** limiting transforms, reference resolution, and forbidden algorithms such as MD5. However, exact limits and default on/off state can vary by version/call path. Enable protective mode in the XML Security library if supported by the framework and keep dependencies updated, **then still explicitly test SHA-1 rejection**.

Specifically, XML Signature secure validation by itself **does not know** which issuer the SP trusts, which ACS is valid, or which assertion the app uses as principal. SAML profile checks, reference coverage, SAML trust, and audience/destination must be enforced **alongside** XML signature security.

### 10.5. Never customize the verifier by dropping default validation

The following is an **anti-pattern**:

```java
// Wrong: using a raw getter on unverified XML to grant access.
// String issuer = xml.getElementsByTagName("Issuer").item(0).getTextContent();
// if (issuer.contains("trusted")) return createAuthenticatedAdmin();
```

Never implement "algorithm checks" with regex before granting roles. Given XML canonicalization, namespaces, signed references, and signature wrapping, that skips core invariants. If you must customize the OpenSAML provider, use version-appropriate extension hooks/docs and **delegate signature/trust/condition verification to the standard provider**.

## 11. Migrating from weak to strong algorithms

### 11.1. Per-IdP integration inventory

Maintain a table to govern migration:

| Field | Example to record | Reason |
| --- | --- | --- |
| Registration | `corp` | Distinguish key/policy per IdP |
| XML signature algorithm currently emitted by IdP | RSA-SHA1 or RSA-SHA256 | Identify mandatory changes |
| XML digest algorithm | SHA-1 or SHA-256 | Avoid overlooking a weak reference |
| IdP signing certificate key type/size | RSA-2048 | Assess key strength |
| SP AuthnRequest binding/signing | Redirect + RSA-SHA256 | Verify SP→IdP direction separately |
| IdP supported algorithms from metadata/docs | RSA-SHA256, RSA-SHA384 | Know interoperability capabilities |
| Rollover plan | New cert trusted prior to switch | Avoid downtime |
| Deadline/owner/test result | Date, owner, test harness | Track and retire exceptions |

Manage this data in an access-controlled config/secret governance repository; never publish key aliases or keystore passwords publicly.

### 11.2. Verifiable migration steps

1. **Inventory:** measure actual algorithms in a test environment via verifier/audit records free of raw assertions.
2. **Agree:** lock down signature/digest algorithms, key type/size, signature placement, and binding with the IdP/SP.
3. **Prepare:** provision new certificates/keys if needed; register SP public signing cert at IdP and IdP public signing cert at SP.
4. **Deploy support:** ensure the verifier supports **strong** algorithms without widening to weak ones. Configure outbound requests per IdP agreement.
5. **Test:** SAML fixtures signed with RSA-SHA256/SHA-256 must pass; SHA-1, MD5, mismatch/downgrade, and weak-key fixtures must be rejected.
6. **Cutover:** IdP begins emitting strong algorithms and rotates keys on schedule; SP monitors login failure rates.
7. **Enforce:** once integrations are compatible, lock the allowlist, remove legacy exceptions, and alert on weak algorithm detection.
8. **Document:** record test results, OpenSAML/Spring versions, certificate expirations, and ongoing procedures.

Distinguish failures caused by **algorithm** from failures caused by **certificate rollover**. Replacing a certificate alone does not automatically change XML SignatureMethod; conversely, switching RSA-SHA256 to RSA-SHA512 does not replace keys/certificates.

### 11.3. If a vendor still emits SHA-1

Never silently fail-open or "temporarily allow login" by turning off signature verification. If internal policy forbids SHA-1, **blocking is the right outcome**. The remediation is upgrading the IdP, switching providers, confining integration to non-production, or obtaining a formal time-bound risk exception (if permitted by the organization). One exception must never bleed over to other IdPs.

Never advise spoofing the signer or rewriting `SigAlg`/`DigestMethod` in transit: the **message issuer must re-sign** with the proper private key, verified per agreement.

## 12. Java 17+: checking an allowlist before verifying a signature

The following example uses **pure Java SE 17**, requiring no SAML libraries. It illustrates that a policy will:

- Accept only the approved **RSA-SHA256** and **SHA-256 digest URI** pair.
- Check that the RSA public key is at least 2048 bits.
- Verify the signature on a mock byte array using JCA `Signature`.
- Reject altered payloads and reject `rsa-sha1` or `sha1` **even if the object carries some signature**.

**This is NOT a SAML/XMLDSig verifier**: it does not canonicalize XML, resolve signed references, verify SAML Issuer/Certificate, or check Conditions/`InResponseTo`. In real SAML, reference hashing, canonicalization, signature coverage, and trust must be handled by the OpenSAML/XML Security provider.

Save file `SamlAlgorithmPolicyDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;

public class SamlAlgorithmPolicyDemo {

    private static final String SIG_RSA_SHA256 =
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256";
    private static final String SIG_RSA_SHA1 =
        "http://www.w3.org/2000/09/xmldsig#rsa-sha1";
    private static final String DIGEST_SHA256 =
        "http://www.w3.org/2001/04/xmlenc#sha256";
    private static final String DIGEST_SHA1 =
        "http://www.w3.org/2000/09/xmldsig#sha1";

    static String inspect(String signatureUri, String digestUri,
                          PublicKey trustedKey, byte[] data, byte[] signed) 
            throws Exception {

        if (!SIG_RSA_SHA256.equals(signatureUri)
                || !DIGEST_SHA256.equals(digestUri)) {
            return "REJECT_ALGORITHM";
        }
        if (!(trustedKey instanceof RSAPublicKey rsaKey)
                || rsaKey.getModulus().bitLength() < 2048) {
            return "REJECT_KEY";
        }

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedKey);
        verifier.update(data);
        return verifier.verify(signed)
                ? "ACCEPT"
                : "REJECT_SIGNATURE";
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keys = generator.generateKeyPair();

        byte[] original = "test-payload".getBytes(StandardCharsets.UTF_8);
        byte[] altered = "test-payload-changed"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(keys.getPrivate());
        signer.update(original);
        byte[] signature = signer.sign();

        System.out.println("strong: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA256,
                          keys.getPublic(), original, signature));
        System.out.println("tampered: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA256,
                          keys.getPublic(), altered, signature));
        System.out.println("sha1 signature URI: "
                + inspect(SIG_RSA_SHA1, DIGEST_SHA256,
                          keys.getPublic(), original, signature));
        System.out.println("sha1 digest URI: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA1,
                          keys.getPublic(), original, signature));
        System.out.println("unknown signature URI: "
                + inspect("urn:example:unknown", DIGEST_SHA256,
                          keys.getPublic(), original, signature));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SamlAlgorithmPolicyDemo.java
java SamlAlgorithmPolicyDemo
```

**Exact** stdout (keys are generated randomly, yet result strings are fixed):

```text
strong: ACCEPT
tampered: REJECT_SIGNATURE
sha1 signature URI: REJECT_ALGORITHM
sha1 digest URI: REJECT_ALGORITHM
unknown signature URI: REJECT_ALGORITHM
```

Explanation:

- `strong: ACCEPT`: signature was created and verified with the same RSA key; algorithm/digest URIs match the **simulated** policy.
- `tampered: REJECT_SIGNATURE`: differing bytes cause JCA verification to fail.
- `sha1 signature URI` and `sha1 digest URI` are **rejected before calling verify** thanks to the allowlist, even though the original JCA signature bytes are intact.
- `unknown signature URI` is rejected because it is not in the list.
- `REJECT_KEY` is an error branch triggered when supplying an undersized RSA key or non-RSA key; `main` only demonstrates algorithm/tampering cases.

**Important:** In the demo, `DIGEST_SHA256` is purely a **policy metadata input**, because JCA `SHA256withRSA` hashes the payload bytes itself and does not compute XML `ds:Reference` digests. **Do not infer that this code validates XML `DigestValue`**. Never replace OpenSAML with raw XML string verification on browser-supplied payloads; XML signatures demand canonicalization, transforms, ID references, trusted certificates, and SAML protocol validation.

## 13. Negative testing matrix

| Fixture / scenario | Expected |
| --- | --- |
| Response/Assertion RSA-SHA256 + SHA-256, trusted IdP key, all conditions met | PASS |
| Response RSA-SHA384 + SHA-384, allowed suite for specific IdP | PASS per policy/support |
| Response RSA-SHA1 + SHA-1, mathematically valid signature | **REJECT_WEAK_ALGORITHM** |
| RSA-SHA256 yet `DigestMethod=sha1` | **REJECT_WEAK_DIGEST** |
| Unknown or null `SignatureMethod` | Reject |
| Unknown `DigestMethod` on a reference | Reject |
| DSA-SHA1/HMAC-SHA1 in profile requiring trusted X.509 asymmetric key | Reject |
| 1024-bit RSA key, RSA-SHA256 signature verifies | Reject key strength |
| ECDSA-SHA256 on an IdP allowing only RSA | Reject unsupported key/algorithm |
| RSA-SHA512 with public cert that is actually EC | Reject key mismatch |
| IdP B certificate signing assertion claiming IdP A issuer | Reject trust/issuer mismatch |
| XML containing attacker's self-generated `KeyInfo` | Never auto-trust certificate from KeyInfo; reject |
| Valid Response signature yet app reads unsigned/uncovered assertion | Reject |
| Reference URI pointing to wrong ID or duplicate ID | Reject; prevents signature wrapping |
| XML with disallowed XSLT/remote reference | Reject transform/reference |
| One `ds:Reference` SHA-256, one `ds:Reference` SHA-1 | Reject per policy across all relevant references |
| `SigAlg=RSA-SHA1` in signed Redirect AuthnRequest | Test IdP rejects if policy forbids SHA-1 |
| `SigAlg=RSA-SHA256` yet invalid signature bytes | IdP rejects |
| Only rewriting `SigAlg` from SHA-1 to SHA-256 after signing | IdP rejects due to signature mismatch |
| Response with RSA-SHA256 signature yet wrong `Audience` | Reject SAML validation |
| Response with valid signature yet expired | Reject |
| Response with valid signature yet wrong/replayed `InResponseTo` | Reject |
| Both old/new signing certificates valid during rotation window | PASS only with keys trusted by IdP registration, matching issuer and policy |
| Attacker modifies certificate in metadata | Reject unapproved administrative change |
| Exception/log contains raw SAMLResponse or private key on rejection | **FAIL security QA**; do not check only auth rejection |

### 13.1. Two mandatory testing directions

**SP → IdP direction (outbound):** capture requests on Redirect/POST, inspect signature placement, `SigAlg`/`SignatureMethod`, binding, SP cert, and acceptance at the test IdP. Use a test IdP with a SHA-1 rejection policy rather than confirming solely that "the request went out".

**IdP → SP direction (inbound):** emit SAMLResponse/Assertion fixtures **signed with test keys** separately under SHA-256 and SHA-1. A mathematically valid RSA-SHA1 fixture must be rejected by policy if SHA-1 is forbidden. Also test SHA1 digest with RSA-SHA256 SignatureMethod, weak keys, wrong issuer, duplicate IDs, and unsigned assertions.

Merely editing a string inside a signed XML fixture breaks the signature and **does not prove the algorithm policy rejected a valid SHA-1 signature**. To truly test algorithm restriction, generate a fixture signed under the weak algorithm in a controlled test environment, never using production assertions.

### 13.2. Configuration/runtime verification

- Check Spring Security/OpenSAML/XML Security versions, secure-validation behavior, and supported algorithm policies **on the exact running build**.
- Document approved signature/digest URIs and key strengths in the security contract, stored in access-controlled configuration management.
- In multi-node setups, all pods must share identical algorithm allowlists and trusted IdP certificates. A single pod still allowing SHA-1 becomes a weak acceptance point.
- Test key rotation with both old/new trust for the exact window, never failing open when keys are missing or metadata is stale.
- Never place raw payloads/PEM private keys in CI logs; use only public test fixtures and controlled test keys.

## 14. Logging, operations, and response

### 14.1. Rejecting with internal reason codes without leaking messages

When policy rejects, the browser should see only a generic message such as:

```text
Unable to complete SSO login.
Please try again or contact support with the event code.
```

Internal audit logs may contain:

```json
{
  "event": "saml_auth_rejected",
  "event_id": "3c98b4af-52d3-4326-926f-a8d16be946c8",
  "registration": "corp",
  "reason_code": "WEAK_SIGNATURE_ALGORITHM",
  "result": "DENIED"
}
```

The sample above is dummy data. Never log raw `SAMLResponse`, `SAMLRequest`, XML `SignedInfo`, `SignatureValue`, private keys, secret `RelayState`, session cookies, or `exception.getMessage()` if it may contain SAML data. Nor should unverified algorithms/key aliases/issuers be returned in client error bodies.

### 14.2. Useful metrics

- `saml_signature_algorithm_rejected_total{registration,reason}` with labels taken from a controlled allowlist.
- Login success/failure rate per IdP registration during cert rollover.
- Counts of unsupported algorithm, invalid signature, untrusted key, XML reference coverage, and time mismatch errors.
- Certificate/key expiry/rotation alerts and instances experiencing configuration drift.

Avoid labels with `NameID`, emails, or unallowlisted `SignatureMethod` strings supplied by attackers to prevent data leaks or metric cardinality explosions. Error details stay restricted to authorized operational channels.

### 14.3. If SHA-1 acceptance is discovered

1. Confirm using a test fixture with a **genuinely valid** SHA-1 signature, and check whether it affects inbound Response/Assertion or outbound requests.
2. Identify the OpenSAML/XML Security version, IdP registration, and code/custom validation that allowed the algorithm.
3. Enforce restrictions at the exact authentication/signature verification boundary, not merely as a post-session condition.
4. Coordinate with the IdP to upgrade to SHA-256+, key/certificate strength, and rotation if needed.
5. Inspect logs, telemetry, existing sessions, and signs of abuse; trigger incident response if severe.
6. Add weak/strong regression tests and monitor rollout so no other pod or IdP continues supporting legacy algorithms.

Do not assume a `JDK disabledAlgorithms` change or an outbound AuthnRequest `SignatureMethod` property suffices to protect inbound XML Signatures: **test end-to-end on the actual version**.

## 15. Pre-deployment review checklist

- [ ] Distinguished XML `SignatureMethod`, `DigestMethod`, certificate signature algorithm, and TLS.
- [ ] Approved signature/digest URIs are **allowlisted** per registration/IdP and threat model, with no SHA-1/MD5 fallback.
- [ ] RSA keys are at least 2048 bits or approved EC curve/key strength; never accept weak keys just because a signature verifies.
- [ ] SP private signing key and IdP public verification cert match direction, managed/rotated safely.
- [ ] SAML Response/Assertion verified with registered trusted IdP key; never arbitrarily trust `ds:KeyInfo`.
- [ ] All signatures/references protecting authentication data are checked, with XML Signature Wrapping defenses.
- [ ] XML parser/schema/transform/reference security is enabled and bounded; no fetching external resources from untrusted XML.
- [ ] Algorithm policy is enforced **before creating Authentication**, preserving issuer/audience/recipient/time/`InResponseTo`/replay checks.
- [ ] Outbound AuthnRequest algorithm matches IdP capability; `signingAlgorithms`/`SigAlg` is not mistaken for an inbound verification allowlist.
- [ ] Callback XML Signatures and Redirect signatures are validated per their **distinct bindings**.
- [ ] All instances/nodes share identical policy and trust config; metadata/cert rotation is tested.
- [ ] A mathematically valid RSA-SHA1 test fixture is rejected; tested SHA1 DigestMethod paired with RSA-SHA256 SignatureMethod.
- [ ] Expired assertion, wrong audience, wrong issuer, duplicate ID, reference mismatch, and replay tests all fail closed.
- [ ] Error responses/logs/APM/WAF never disclose assertions, `SignatureValue`, private keys, or exception dumps.
- [ ] Retirement plan exists for IdPs supporting only weak algorithms, with clearly scoped/time-bound risk exceptions if permitted.

## 16. Review questions

**1. The IdP's certificate uses `sha256WithRSAEncryption`, yet the SAML `SignatureMethod` is `rsa-sha1`. Is this valid under a policy forbidding SHA-1?**  
No. The certificate signing algorithm and XML signing algorithm are two separate things. The SAML signature uses RSA-SHA1 and must be rejected.

**2. Is `SignatureMethod=rsa-sha256` enough to conclude signed XML is safe?**  
No. You must also check `DigestMethod`, trusted key/key size, reference coverage, transforms, issuer/audience/recipient/time, and replay.

**3. An XML has a valid signature, yet the assertion used as principal lies outside the signed region. What happens?**  
It must be rejected. This is an XML Signature Wrapping scenario; claims unprotected by a signature must never be used.

**4. Is `RSA-SHA512` always safer than `RSA-SHA256` for every IdP?**  
Not operationally. Both can be valid choices when keys are strong enough, yet IdP/SP must both support them. Switching algorithms does not make a 1024-bit key safe.

**5. Can `assertingPartyMetadata(...).signingAlgorithms(...)` make the SP automatically reject SHA-1 SAMLResponse signatures?**  
Do not assume so. That Spring Security option governs algorithms the **SP uses to sign AuthnRequests sent to the IdP**; inbound verification policy requires separate inspection/configuration.

**6. In Redirect binding, why can a request still be signed even without `<ds:Signature>`?**  
Because HTTP-Redirect binding signatures normally live in the `SigAlg` and `Signature` query parameters, not necessarily inside the AuthnRequest XML.

**7. What should you do if an IdP emits only RSA-SHA1?**  
Require the IdP to upgrade/change the integration, or follow a formal controlled exception process if the organization permits it. Never silently downgrade or disable signature verification.

**8. Why must you test with a genuinely signed RSA-SHA1 SAMLResponse?**  
Merely changing the URI on a signed RSA-SHA256 response also breaks the signature, which does not prove SHA-1 restriction works. A valid test must prove a **mathematically valid SHA-1 signature is still rejected by policy**.

**9. Is the public certificate inside `KeyInfo` enough to trust the source?**  
No. The certificate must be bound to a trusted IdP/registration through governed configuration/metadata, not taken from browser-supplied XML.

**10. Can raw `SAMLResponse` be logged in production when debugging algorithms?**  
No. Use event codes, test fixtures, protected telemetry, and controlled key/certificate metadata; raw assertions can carry personal data or replayable login tokens.

## 17. References

- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): signatures, key trust, RSA-2048/SHA-256 selection, recommendations to reject RSA-SHA1/HMAC-SHA1/SHA1 Digest and verify signed reference coverage.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request signing config, `signingX509Credentials`, default RSA-SHA256, and IdP-supported algorithms.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): provider verifying Response/Assertion, customization, and validation.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): distinguishing request/response filters and trust boundaries.
- [Apache Santuario – Java FAQ / Secure Validation](https://cwiki.apache.org/confluence/spaces/SANTUARIO/pages/24838162/java_faq): restricting XML Signature transforms, remote references, MD5, and secure validation.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `AuthnRequest`, `Response`, `Assertion`, XML Signature, and conditions structure.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect/POST and per-binding signatures.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): `SignedInfo`, `SignatureMethod`, `DigestMethod`, references/transforms/canonicalization.
- [NIST SP 800-131A Rev. 2](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final): cryptographic algorithm transitions and key size policies.

**Key takeaway:** To protect SAML federation, SP/IdP must choose an **approved signing suite** (signature algorithm + digest + key type/size), never accept SHA-1/MD5 merely because libraries still support them, and always verify **the exact signed Response/Assertion using a trusted IdP certificate**. Configuring outbound AuthnRequest signing and enforcing weak-signature rejection on inbound responses **are two separate tasks**; both require integration tests and disciplined key/certificate operations.