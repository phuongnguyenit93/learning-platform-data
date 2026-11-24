# Decrypting EncryptedAssertion and Selecting the Right Decryption Key in Spring Security SAML 2.0

## 1. Objective and Problem Statement

In SAML 2.0 federation, the **Identity Provider (IdP / Asserting Party)** may send login results to the **Service Provider (SP / Relying Party)** as **`<saml:EncryptedAssertion>`** rather than leaving `<saml:Assertion>` in readable plaintext.

This feature protects **assertion confidentiality** while traveling through the browser and intermediary systems. An assertion can carry NameID, user attributes, organization identifiers, and private data. TLS protects each HTTP connection, whereas assertion encryption protects the payload from parties that **do not possess the SP's decryption key**.

This lesson belongs to the **SAML2 Verification** track and focuses on two closely related tasks:

1. **Properly decrypting `EncryptedAssertion`** when the IdP actually sends an encrypted assertion.
2. **Selecting the right SP private key** based on registration, the certificate used by the IdP, rotation policy, and XML Encryption structure.

After this lesson, you need to understand:

- Why the IdP encrypts with the **SP's public key**, while the **SP decrypts with its corresponding private key**.
- The roles of `<xenc:EncryptedData>`, `<xenc:EncryptedKey>`, `<ds:KeyInfo>`, and how to pick a credential from a **managed trusted key set**.
- How to declare `decryption.credentials` in Spring Boot and `Saml2X509Credential.decryption(...)` in Spring Security.
- Why **successful decryption does not mean successful authentication**; you must still verify signature, issuer, audience, recipient, timestamps, and correlation.
- Decryption/signature verification ordering when an assertion is signed then encrypted, or when attributes inside an assertion are encrypted.
- How to handle multiple IdPs, multiple keys, key rollover, algorithm mismatches, Java/OpenSAML errors, and security tests.

**Core principle:** the system may only use **SP private keys approved for that registration**. A KeyName, certificate, or key hint inside a browser-delivered SAMLResponse **cannot grant access to a new key or alter trust policy on its own**.

## 2. SAML Assertion, EncryptedAssertion, and Confidentiality Boundaries

A normal SAML Response can contain `<saml:Assertion>` directly in XML:

```text
samlp:Response
  saml:Issuer
  saml:Assertion
    saml:Issuer
    saml:Subject / NameID
    saml:Conditions / AudienceRestriction
    saml:AuthnStatement
    saml:AttributeStatement
```

When the IdP encrypts the entire assertion, the assertion position is replaced by `<saml:EncryptedAssertion>`:

```text
samlp:Response
  saml:Issuer
  saml:EncryptedAssertion
    xenc:EncryptedData                  <- ciphertext of Assertion XML
      xenc:EncryptionMethod             <- AES, etc.
      ds:KeyInfo                        <- may reference EncryptedKey
      xenc:CipherData
    xenc:EncryptedKey                   <- wrapped AES content key
      xenc:EncryptionMethod             <- RSA-OAEP, etc.
      ds:KeyInfo                        <- recipient key hint
      xenc:CipherData
```

This is a **structural diagram**, not the sole XML layout used by all vendors. Per SAML/XML Encryption and errata, `EncryptedKey` may be linked via `KeyInfo` or other valid referencing mechanisms; never write rigid code requiring it to appear at **one fixed XPath**.

### 2.1. Three Layers to Distinguish

| Layer | What does it protect? | Relevant components |
| --- | --- | --- |
| **Assertion encryption** | Confidentiality of assertion content | `EncryptedAssertion`, `EncryptedData`, `EncryptedKey`, SP private key |
| **XML signature** | Integrity/origin of message or assertion | `ds:Signature`, IdP verification certificate |
| **SAML conditions** | Whether the assertion matches the right SP, session, and validity window | `Issuer`, `AudienceRestriction`, `Recipient`, `Destination`, `InResponseTo`, timestamps |

Encryption **does not prove the issuer on its own**. An attacker knowing the SP's public certificate can construct new ciphertext and send it to the SP; only a **properly verified** SAML Response/Assertion is permitted to become an `Authentication`.

## 3. Hybrid Encryption Mechanism

In common SAML/XML Encryption implementations, the IdP **does not use RSA directly to encrypt the whole XML assertion** due to size limits and performance. Instead, the IdP uses **hybrid encryption**:

1. The IdP generates a random symmetric **content-encryption key (CEK)** for a single encryption operation.
2. Uses the CEK and a symmetric algorithm like **AES** to encrypt the XML assertion, storing the ciphertext under `<xenc:EncryptedData>`.
3. Uses the **SP's public key** to **wrap/transport** the CEK via an algorithm such as **RSA-OAEP**, storing it under `<xenc:EncryptedKey>`.
4. Sends the SAML Response containing EncryptedAssertion to the **SP's ACS endpoint** via the browser.
5. The SP picks the **private key** matching the public key used by the IdP and decrypts EncryptedKey to recover the CEK.
6. The SP uses the CEK to decrypt EncryptedData, recover the Assertion XML, and **continue SAML verification**.

```text
                IdP                                  SP
       (holds SP public cert)                (holds SP private key)
                |                                   |
       Generate AES content key                     |
                |                                   |
       AES Encrypt(Assertion)                       |
                |                                   |
       ciphertext -> EncryptedData                  |
                |                                   |
       RSA-OAEP(SP public, AES key)                 |
                |                                   |
       wrapped CEK -> EncryptedKey                  |
                |                                   |
             SAML Response ------------------------>|
                                                    | select private key
                                                    | unwrap CEK
                                                    | AES Decrypt
                                                    v
                                               Assertion XML
                                                    |
                                                    v
                                       Verify signature / SAML policy
                                                    |
                                                    v
                                       Authentication if valid
```

**The SP's public certificate is not a secret.** The IdP needs to receive it via SP metadata or trusted integration configuration. **The SP's private key must stay at the SP**, inside a managed keystore/secret manager/HSM. Never send the private key to the IdP so "they can configure encryption", and never use the IdP's private key to decrypt assertions arriving at the SP.

### 3.1. When Is There No EncryptedKey?

Not every XML Encryption message carries `<xenc:EncryptedKey>` inside the payload. Some profiles use pre-established symmetric keys or local key-identification mechanisms. SAML errata describe how EncryptedKey/EncryptedData link when the key is carried in XML.

Therefore:

- **Do not assume** every `EncryptedAssertion` always has exactly one `EncryptedKey`.
- Never hardcode XPath by fixed position or accept only one structure your IdP has not committed to.
- If the application only supports hybrid RSA-OAEP/AES with EncryptedKey, **agree on the profile explicitly and reject unsupported forms** rather than guessing or silently falling back to a global key.

## 4. Keys and Certificates Have Distinct Roles

| Credential | Private key owner | Purpose | Common config location |
| --- | --- | --- | --- |
| **SP decryption** | **SP** | Decrypts `EncryptedKey`/assertions meant for SP | `RelyingPartyRegistration.decryptionX509Credentials` |
| **SP signing** | SP | Signs AuthnRequest/LogoutRequest per contract | `signingX509Credentials` |
| **IdP verification** | IdP (private key) | SP uses **IdP public cert** to verify Response/Assertion signatures | `assertingPartyMetadata.verificationX509Credentials` |
| **Metadata signer** | IdP or federation operator | Verifies signature on metadata documents, if required | Separately provisioned metadata trust anchor |

An organization can use the **same SP keypair** for signing and decryption, and Spring Security allows designating a credential for multiple purposes. Nevertheless, using **dedicated keys per duty** usually allows cleaner governance/rotation/revocation when supported by the IdP.

**Critical mistake:** configuring the IdP's certificate under `decryption.credentials` and expecting the SP to decrypt. The IdP certificate is the **IdP's** public key, not the SP's private key. Likewise, importing only the SP public certificate without its matching private key cannot decrypt anything.

### 4.1. SP Metadata and Encryption Certificate

The SP typically publishes its **encryption** certificate via:

```xml
<md:KeyDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    use="encryption">
  <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:X509Data>
      <ds:X509Certificate>BASE64_CERTIFICATE_DATA</ds:X509Certificate>
    </ds:X509Data>
  </ds:KeyInfo>
</md:KeyDescriptor>
```

This is an **illustrative snippet**; `BASE64_CERTIFICATE_DATA` is just an explanatory placeholder, not a real certificate. The IdP must import the exact **SP encryption certificate** into the registered SP app and encrypt for that public key. If the IdP holds a stale certificate, it will create an EncryptedKey the new private key cannot decrypt; keep the old key temporarily per rotation plan or synchronize configuration beforehand.

Metadata may list multiple `KeyDescriptor` elements with the same purpose for rollover. `use` may be omitted per SAML metadata, in which case one key may be described for multiple uses per profile/policy; confirm with the IdP before assuming "the first key" is the primary encryption key.

## 5. EncryptedData, EncryptedKey, KeyInfo: Which Field Selects the Key?

An `EncryptedAssertion` typically contains these concepts:

```xml
<saml:EncryptedAssertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <xenc:EncryptedData
      Type="http://www.w3.org/2001/04/xmlenc#Element">
    <xenc:EncryptionMethod
        Algorithm="http://www.w3.org/2009/xmlenc11#aes128-gcm"/>
    <ds:KeyInfo>
      <!-- reference or link to EncryptedKey per profile -->
    </ds:KeyInfo>
    <xenc:CipherData>
      <xenc:CipherValue>BASE64_ENCRYPTED_ASSERTION</xenc:CipherValue>
    </xenc:CipherData>
  </xenc:EncryptedData>
  <xenc:EncryptedKey>
    <xenc:EncryptionMethod
        Algorithm="http://www.w3.org/2009/xmlenc11#rsa-oaep"/>
    <ds:KeyInfo>
      <!-- may contain KeyName / X509Data hinting the recipient -->
    </ds:KeyInfo>
    <xenc:CipherData>
      <xenc:CipherValue>BASE64_WRAPPED_CONTENT_KEY</xenc:CipherValue>
    </xenc:CipherData>
  </xenc:EncryptedKey>
</saml:EncryptedAssertion>
```

This snippet is **solely for learning structure**, not valid decryptable XML Encryption: ciphertext is symbolic, parameters/directives are incomplete, and profile-specific namespaces/elements may be needed. Strictly never use it as a positive SAMLResponse test.

| Component | Function | Key selection note |
| --- | --- | --- |
| `EncryptedData/EncryptionMethod` | **Content** encryption algorithm (AES) | Does not identify which RSA private key |
| `EncryptedKey/EncryptionMethod` | **CEK wrapping** algorithm (RSA-OAEP, etc.) | Must be supported by private key/protocol |
| `EncryptedKey/CipherValue` | Encrypted CEK | Only the matching private key unwraps properly |
| `EncryptedData/CipherValue` | Assertion ciphertext | Uses unwrapped CEK to decrypt |
| `ds:KeyInfo` / `ds:KeyName` | Key/cert/recipient hint | **Not a trusted key source** |
| `xenc:EncryptedKey/@Recipient` if present | Recipient hint/identifier | Cross-check with exact SP; do not trust alone |
| `ds:RetrievalMethod` / `ReferenceList` when used | Links EncryptedKey to EncryptedData | Only per forms permitted by library and policy |

**KeyInfo is a hint, not an authorization command.** If the message states `KeyName=sp-2030`, the application may only treat it as a hint to find **a key already existing in the managed credential set for the right registration**. Never read `KeyName` as a file path, sender-chosen secret manager ID, or URL from which to download a private key.

## 6. Selecting the Right Private Key: Algorithms, Registration, and Key Ring

### 6.1. Safe Selection Order

1. Resolve the **`RelyingPartyRegistration`** handling the SAML Response per Spring Security config and trusted request/correlation context.
2. Retrieve **only** `Saml2X509Credential` entries of type **DECRYPTION** belonging to the **Relying Party** in that registration.
3. Based on `KeyInfo`/certificate identifier/recipient, you may **narrow down** candidate credentials within that trusted set.
4. Verify the `EncryptedKey` algorithm matches the key type, size, and cryptographic policy.
5. Attempt to unwrap the CEK with a matching private key within clear resource limits. If no unambiguous hint exists, the library may try allowed candidates in a sensible order, yet **never try keys from other tenants/registrations unboundedly**.
6. Use the CEK to decrypt `EncryptedData` with the right algorithm/mode/IV/tag.
7. Verify the output is valid assertion XML and run **all signature + SAML condition checks** before creating a login session.
8. If no suitable key exists or the algorithm is disallowed, **fail closed** with an operational error; never fall back to "skipping encryption" or accepting a self-asserted assertion.

### 6.2. Key Ring Selection Example

Suppose an SP holds two decryption keys during a rotation window:

| Internal Key ID | Status | Private key at SP? | SP certificate known to IdP? |
| --- | --- | --- | --- |
| `sp-dec-2025` | Retained only to decrypt older payloads | Yes, still approved | IdP may still encrypt with old cert during transition |
| `sp-dec-2026` | Primary key for new ciphertext | Yes | IdP already imported new cert |

When EncryptedKey is wrapped with **public key 2026**, only private key 2026 can unwrap the CEK under that encryption. The SP may try 2025 first and fail, yet **not every first-key failure proves the assertion was forged**; if policy permits both keys, it can fall through safely to 2026 via the library. Conversely, once 2025 is revoked and removed from the key ring, **never reload it** just because a request carries a KeyName suggesting it.

An unsafe design:

```text
keyPath = "/secrets/" + userSuppliedKeyName
privateKey = load(keyPath)
decrypt(...)
```

A principled safe design:

```text
registration = trustedRegistrationResolver(responseContext)
allowedKeys = registration.decryptionCredentials
hint = parseUntrustedKeyHint(samlResponse)
candidateKeys = selectWithin(allowedKeys, hint)
decryptWithBoundedCandidates(candidateKeys)
verifyAssertionAndPolicy(...)
```

Pseudocode only illustrates **key-selection scoping**. All real XML parsing, lookup, and decryption must use OpenSAML/Spring Security, never a custom XML Encryption engine.

### 6.3. Relationships That Must Not Be Guessed

- `registrationId` is a local Spring config key; **not** a private key ID and not a SAML subject.
- SP `entityId` is the target system identifier of the assertion; **not** a private key filename.
- `IdP entityId` identifies the issuer **after validation**, not the SP's decryption key.
- `KeyInfo` may contain an IdP-sent certificate/KeyName and must be matched against config, never turned into a dynamic trust anchor.
- `NameID` is the user identity inside the decrypted assertion, **never used to select a private key** (NameID cannot even be known before decrypting).
- `RelayState`/callback URL must not arbitrarily select another tenant's key ring.
- Cryptographic decryption success does not prove valid issuer/audience; anyone knowing the SP's public certificate can encrypt data with it.

## 7. Encryption Algorithms: Compatibility and Policy

To process an EncryptedAssertion, both sides must align on **two algorithm layers**:

### 7.1. Content Encryption

| Typical algorithm / URI | Role | Considerations |
| --- | --- | --- |
| `http://www.w3.org/2009/xmlenc11#aes128-gcm` | AES-128-GCM for content | Includes cryptographic integrity tag; preferred when supported by IdP/OpenSAML and XML Encryption profile |
| `http://www.w3.org/2009/xmlenc11#aes256-gcm` | AES-256-GCM for content | Requires compatible provider/configuration |
| `http://www.w3.org/2001/04/xmlenc#aes128-cbc` | Legacy AES-128-CBC | Lacks its own authentication tag; assess risks and oracle mitigations |
| `http://www.w3.org/2001/04/xmlenc#aes256-cbc` | Legacy AES-256-CBC | Use when vetted interoperability requires; not automatically safer than GCM |

**Note:** Older SAML 2.0 stacks and different IdP products vary in XML Encryption 1.0/1.1 support. Never force all partners onto AES-GCM if your actual stack only supports AES-CBC; verify capability, OpenSAML version, metadata, IdP policy, and negative tests before switching. Yet also **never relax policy** to enable risky legacy algorithms just to mask a key mismatch.

### 7.2. Key Transport / Key Wrapping

| Typical algorithm / URI | Role | Considerations |
| --- | --- | --- |
| RSA-OAEP `http://www.w3.org/2001/04/xmlenc#rsa-oaep-mgf1p` | Key wrapping with XML Encryption 1.0 OAEP | Default parameters/digest must match message and profile |
| RSA-OAEP `http://www.w3.org/2009/xmlenc11#rsa-oaep` | XML Encryption 1.1 OAEP | Supports explicit DigestMethod/MGF config when present |
| RSA v1.5 `http://www.w3.org/2001/04/xmlenc#rsa-1_5` | Legacy key transport | Discouraged due to oracle risks; reject under modern security policy |

**Do not equate RSA-OAEP with "OAEP always uses SHA-256".** XML Encryption defines multiple URIs/ways to specify digests and MGFs. The decryptor must adhere to algorithms/parameters permitted by message/profile; mismatched `DigestMethod` or MGF can make the right private key fail unwrapping.

### 7.3. Safeguards

- Allowlist **specific algorithms** aligned with policy and IdP/SP capabilities; exclude RSA v1.5, weak ciphers, and unapproved downgrades.
- Limit **XML/SAMLResponse size**, number of `EncryptedKey` elements, candidate key count, CPU, and processing time; prevent DoS.
- XML parser must block **DTDs, external entities (XXE), XInclude, and disallowed external URIs/transforms**; use maintained SAML/XMLSec libraries.
- Never return detailed errors like "padding right/wrong", "key A matched", or "AES tag failed" externally, as these create a **decryption oracle**. Record operational error codes in secure internal logs only.
- Validate decrypted content against schema and SAML constraints; never use an XML string with an unverified signature for access decisions.

## 8. Decryption and Signature Verification Ordering: The Most Error-Prone Part

SAML permits combining **XML Encryption** and **XML Digital Signature** in multiple ways. Specifically:

### 8.1. Assertion Signed Then Encrypted

IdP flow:

```text
Assertion XML
   -> sign Assertion (ds:Signature inside Assertion)
   -> encrypt whole Assertion
   -> EncryptedAssertion inside Response
```

SP executes in **reverse order**:

```text
EncryptedAssertion
   -> decrypt with SP private key
   -> Assertion containing ds:Signature
   -> verify assertion signature with trusted IdP public cert
   -> validate SAML conditions
```

Here you cannot verify the signature **inside the assertion** before decrypting because the signature itself is encrypted with the body. If the outer Response is also signed, the Response signature (protecting the encrypted bytes) has its own verification step.

### 8.2. Attribute or NameID Inside Assertion Is Encrypted

IdP flow may be:

```text
Assertion
   -> encrypt one or more Attributes / NameID
   -> sign Assertion covering the encrypted elements
```

The SP must **verify the assertion signature before modifying the signed XML tree**. If you decrypt an `EncryptedAttribute` before checking the enclosing assertion's signature, the XML tree changes and can cause the signature to mismatch.

Spring Security documents two strategies:

- **Response elements decrypter**: decrypts elements at the Response level, e.g. `EncryptedAssertion`.
- **Assertion elements decrypter**: decrypts `EncryptedAttribute` or `EncryptedID` inside the Assertion.

Separating these two decryption stages specifically prevents **premature decryption from breaking the signature of a signed Assertion**. <https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html>

### 8.3. Signed Response, Unsigned Assertion?

Some profiles permit a signature on **Response** instead of each Assertion, or sign both. The SP must enforce the **agreed signature coverage policy**: if only Response is signed, verify the exact signature covering the response holding encrypted data per structure; if the assertion is individually signed, verify its signature after decryption. Never treat "successfully decrypted" as a signature. Never disable signature validation because the inner XML has an expected `NameID`.

**Key takeaway:** operation ordering depends on **what was signed and what was encrypted**. Use Spring Security/OpenSAML's validation lifecycle rather than parsing/replacing XML manually in a controller.

## 9. Spring Boot Configuration: SP Decryption Credentials

In Spring Boot's SAML 2.0 Relying Party support, decryption credentials belong under **`decryption.credentials` of the registration**. Example environment holding two keys during a rollover window:

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-dec-2026.key"
                  certificate-location: "file:/etc/saml/sp-dec-2026.crt"
                - private-key-location: "file:/run/secrets/saml/sp-dec-2025.key"
                  certificate-location: "file:/etc/saml/sp-dec-2025.crt"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
```

**Reading it accurately:**

- `corp` is the local **registrationId**, so Spring Security resolves the right SP–IdP pair.
- `entity-id` is the **SP Entity ID**, which must match Audience in the assertion.
- Each `decryption.credentials` item pairs the **SP private key** with its **matching X.509 certificate**. File paths/names are illustrative; they must be provisioned by the real environment.
- `sp-dec-2026` is the new key, and `sp-dec-2025` is the old key still approved during the rollover window. Listing order is merely a configuration choice; **do not rely on "first item" as a protocol guarantee**.
- `assertingparty.metadata-uri` is the IdP metadata source, not the SP private key, and does not prove the metadata signature on its own. A local file source still needs a trusted IdP metadata ingestion/update process.
- `acs.location` is where the SP receives SAMLResponse; not where decryption keys live.

Config properties can vary by Spring Boot version, yet `spring.security.saml2.relyingparty.registration.<registrationId>.decryption.credentials[*].private-key-location` and `certificate-location` are documented by Spring Boot. Check property metadata/Javadoc **for your deployed version**.

### 9.1. Once You Have Decryption Keys, What Else Is Needed?

At minimum you still need:

- `spring-security-saml2-service-provider` alongside the project's Servlet/Security dependencies.
- Trusted IdP metadata/verification credentials to **verify the IdP signature**.
- SP Entity ID, ACS, and proper request-based registration selection.
- The IdP having imported the new **SP encryption certificate**, mapped to the exact registered SP.
- Encryption/transport algorithms supported by both sides.
- Session config, HTTPS, reverse proxy, key protection, and business authorization.

Do not publish the SP's secret private key inside `application.yml` or a shared container image's classpath; in the example they are referenced from mounted files with restricted read permissions. If using a secret manager or HSM, integrate via the appropriate API/provider instead of letting keys leak into logs or repositories.

### 9.2. Testing a Response with EncryptedAssertion

After configuring, enable `saml2Login()` and run an SP-initiated login in a test environment. The IdP must **actually enable assertion encryption**; merely having decryption credentials on the SP will not make the IdP encrypt Responses if the IdP has not been configured with the SP certificate.

Inspect the test SAMLResponse for `EncryptedAssertion` and matching `EncryptedData` and `EncryptedKey` algorithms, then confirm login via Spring Security. There is no need to write controllers calling AES or RSA directly in application code.

## 10. Java Configuration: Saml2X509Credential.decryption and RelyingPartyRegistration

Spring Security provides `Saml2X509Credential` for SIGNING, DECRYPTION, VERIFICATION, and ENCRYPTION purposes. For SP decryption, you need a `Saml2X509Credential` holding the **SP's private key**.

Example **snippet inside a Spring Boot project**, assuming `privateKey2026`, `privateKey2025` are `PrivateKey` and `certificate2026`, `certificate2025` are `X509Certificate`, all safely loaded and verified to match:

```java
Saml2X509Credential decrypt2026 =
    Saml2X509Credential.decryption(
        privateKey2026, certificate2026);

Saml2X509Credential decrypt2025 =
    Saml2X509Credential.decryption(
        privateKey2025, certificate2025);

RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-metadata.xml")
        .registrationId("corp")
        .entityId("urn:example:portal:prod:sp")
        .decryptionX509Credentials(credentials -> {
            credentials.add(decrypt2026);
            credentials.add(decrypt2025);
        })
        .build();
```

The snippet above is **not a standalone Java file**: it needs imports, real credentials, Spring Security classes, and a `RelyingPartyRegistrationRepository` storing the registration. `fromMetadataLocation` requires trusted IdP metadata; it does not replace verifying metadata per policy. Builder APIs can differ across Spring Security 5/6/7, so verify against your exact version.

**`decryptionX509Credentials` belongs to the SP/Relying Party**, whereas `verificationX509Credentials` normally sits under Asserting Party/IdP. Never swap the two lists.

### 10.1. Loading an RSA Private Key and X.509 Certificate

Per Spring Security docs, for common RSA cases you can use the `RsaKeyConverters.pkcs8()` utility to parse a PKCS#8 private key alongside the SP certificate:

```java
Resource keyFile = new FileSystemResource(
    "/run/secrets/saml/sp-dec-2026.key");
Resource certificateFile = new FileSystemResource(
    "/etc/saml/sp-dec-2026.crt");

RSAPrivateKey key;
try (InputStream in = keyFile.getInputStream()) {
    key = RsaKeyConverters.pkcs8().convert(in);
}

X509Certificate certificate;
try (InputStream in = certificateFile.getInputStream()) {
    certificate = (X509Certificate)
        CertificateFactory.getInstance("X.509")
            .generateCertificate(in);
}

Saml2X509Credential credential =
    Saml2X509Credential.decryption(key, certificate);
```

**This is only an in-application snippet requiring imports/dependencies**, not a standalone runnable Java file. The loading code assumes the key is in **PKCS#8 format supported by the converter**. Password-encrypted keys, PKCS#1 keys, or keys stored in HSM/PKCS#11 may require a different loader/provider. Spring Security docs show equivalent `RsaKeyConverters` examples; Spring Boot can load keys automatically when using supported property files.

Do not treat successfully loading two files as proof that they form **the same keypair**. Verify the keypair during provisioning/deployment via a safe cryptographic check or certificate/keystore tooling; if mismatched, decryption will fail at runtime.

## 11. What Does Spring Security Decrypt Automatically?

In modern Spring Security SAML 2.0, **`OpenSaml5AuthenticationProvider`** authenticates SAMLResponses. Per official documentation, the provider automatically decrypts:

- `<saml:EncryptedAssertion>` at the **Response** level, via the response-elements decrypter.
- `<saml:EncryptedAttribute>` and `<saml:EncryptedID>` inside **Assertion**, via the assertion-elements decrypter.

It uses the decryption `Saml2X509Credential` entries registered on `RelyingPartyRegistration`, provided the structures/algorithms are compatible.

This means **in ordinary cases you only need to declare the right decryption credentials**, without writing a custom `EncryptedAssertion` parser and RSA/AES decryptor.

### 11.1. When Is a Custom Decrypter Needed?

It may be needed when:

- The private key lives in an **HSM/remote crypto service** and cannot be exported into the JVM; you must integrate a decryption path compliant with trust policy.
- A partner uses a specialized XML Encryption profile not supported by the default decrypter, yet a vetted and maintained alternative exists.
- Organizational architecture requires changing the key/algorithm lookup strategy without losing signature validation order.

Spring Security docs provide APIs to replace the strategy:

```java
OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();

// Snippet: decryptionService designed by the application.
// This callback handles elements at the Response level,
// including EncryptedAssertion.
provider.setResponseElementsDecrypter(responseToken ->
    decryptionService.decrypt(responseToken.getResponse()));
```

This is an **integration snippet**, not runnable standalone. You must import and supply a protocol-compliant `decryptionService`, and wire the provider into the `AuthenticationManager` used by `saml2Login()`. **Declaring a provider bean without wiring it into the filter chain does not guarantee Spring Security uses it.**

If customizing decryption of **EncryptedAttribute/EncryptedID**, Spring Security provides `setAssertionElementsDecrypter(...)` separately. You must preserve **assertion signature verification before altering elements inside the signed scope**.

**Warning:** never swap in a custom decrypter and bypass defaults for signature, audience, SubjectConfirmation, and Request correlation. Even when a custom service returns decrypted XML, Spring Security still must fully validate that assertion per policy.

Technical source: <https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html>.

## 12. Standalone Java 17: Simulating Key Selection and Detecting Tampered Ciphertext

The JDK 17+ runnable example below illustrates **hybrid cryptography** and choosing a key from an approved key ring:

- Generates two SP RSA keypairs: old key `sp-2025`, new key `sp-2026`.
- Simulated IdP uses the **new public key** to wrap an AES CEK with **RSA-OAEP (SHA-256 and MGF1-SHA256)**.
- AES-128-GCM protects an **illustrative payload string**, not a valid SAML Assertion.
- The receiver only reads private keys from a pre-supplied `Map`.
- Tests right key, old-key-only, right key name with wrong private key, and tampered ciphertext.

**Important limitation:** the program does not create or parse `saml:EncryptedAssertion`, does not implement an XML Encryption serializer, does not handle real `EncryptedKey/KeyInfo`, does not verify XML/SAML signatures, and does not create `Authentication`. Use it to understand **RSA-OAEP + AES-GCM + key ring relationships**, while production SAML must use Spring Security/OpenSAML.

File `SamlDecryptionKeySelectionDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class SamlDecryptionKeySelectionDemo {
    record Envelope(String keyHint, byte[] wrappedAesKey,
                    byte[] nonce, byte[] ciphertext) {}

    static KeyPair rsaKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static Cipher rsaOaep(int mode, Key key) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        OAEPParameterSpec params = new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT
        );
        cipher.init(mode, key, params);
        return cipher;
    }

    static Envelope encrypt(String payload, String keyHint,
                            PublicKey spPublicKey)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey contentKey = generator.generateKey();
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, contentKey,
                 new GCMParameterSpec(128, nonce));
        byte[] encryptedPayload = aes.doFinal(
            payload.getBytes(StandardCharsets.UTF_8));

        byte[] wrappedKey = rsaOaep(
            Cipher.ENCRYPT_MODE, spPublicKey).doFinal(
                contentKey.getEncoded());
        return new Envelope(keyHint, wrappedKey, nonce, encryptedPayload);
    }

    static String decrypt(Envelope envelope,
                          Map<String, PrivateKey> approvedKeys)
            throws GeneralSecurityException {
        PrivateKey key = approvedKeys.get(envelope.keyHint());
        if (key == null) {
            throw new GeneralSecurityException("No approved key");
        }
        byte[] contentKeyBytes = rsaOaep(
            Cipher.DECRYPT_MODE, key).doFinal(envelope.wrappedAesKey());
        SecretKeySpec contentKey =
            new SecretKeySpec(contentKeyBytes, "AES");
        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.DECRYPT_MODE, contentKey,
                 new GCMParameterSpec(128, envelope.nonce()));
        return new String(
            aes.doFinal(envelope.ciphertext()), StandardCharsets.UTF_8);
    }

    static boolean matches(Envelope envelope,
                           Map<String, PrivateKey> keys,
                           String expectedPayload) {
        try {
            return expectedPayload.equals(decrypt(envelope, keys));
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair oldKey = rsaKeyPair();
        KeyPair newKey = rsaKeyPair();
        String payload = "opaque-assertion-payload";
        Envelope envelope =
            encrypt(payload, "sp-2026", newKey.getPublic());

        Map<String, PrivateKey> active = Map.of(
            "sp-2025", oldKey.getPrivate(),
            "sp-2026", newKey.getPrivate());
        Map<String, PrivateKey> oldOnly = Map.of(
            "sp-2025", oldKey.getPrivate());
        Map<String, PrivateKey> wrong = Map.of(
            "sp-2026", oldKey.getPrivate());

        System.out.println("correctKey="
            + matches(envelope, active, payload));
        System.out.println("oldKeyOnly="
            + matches(envelope, oldOnly, payload));
        System.out.println("wrongPrivateKey="
            + matches(envelope, wrong, payload));

        byte[] tampered = envelope.ciphertext().clone();
        tampered[tampered.length - 1] ^= 1;
        Envelope changed = new Envelope(
            envelope.keyHint(), envelope.wrappedAesKey(),
            envelope.nonce(), tampered);
        System.out.println("tamperingRejected="
            + !matches(changed, active, payload));
    }
}
```

Compile and run:

```bash
javac --release 17 SamlDecryptionKeySelectionDemo.java
java SamlDecryptionKeySelectionDemo
```

**Exact stdout** (RSA/AES values are randomly generated, yet the Booleans yield these outcomes):

```text
correctKey=true
oldKeyOnly=false
wrongPrivateKey=false
tamperingRejected=true
```

**Explanation:**

- `correctKey=true`: the allowed credential set contains private key 2026 matching the public key used to encrypt the CEK.
- `oldKeyOnly=false`: key ring only contains key 2025, lacking the key the ciphertext requires.
- `wrongPrivateKey=false`: a key hint named `sp-2026` **does not turn an old key into the right new key**. The name is a selection hint, not cryptographic proof.
- `tamperingRejected=true`: AES-GCM verifies the authentication tag and detects modified ciphertext. Yet this result **does not replace SAML signature verification** because many parties can know the SP public key and craft their own valid ciphertext.

The example uses a key-hint map for simplicity; a real system must select credentials by **registration + approved key ring + metadata/certificate policy**, with limits on algorithms and retry attempts. The algorithms and ciphertext encoding in this demo **are not wire-compatible with XML Encryption 1.1** without standard serialization, key info, and nonce/tag formatting.

## 13. Managing Multiple IdPs, Tenants, and Registrations

An application may have:

```text
RelyingPartyRegistration employee
    IdP A
    SP entityID = urn:example:portal:prod:sp
    decryption keys = {sp-employee-2025, sp-employee-2026}

RelyingPartyRegistration partner
    IdP B
    SP entityID = urn:example:portal:prod:sp
    decryption keys = {sp-partner-2026}
```

Two registrations may share an SP Entity ID when contracts permit, yet **that is no reason to merge all private keys**. Decryption capability belongs to a **specific trust relationship and technical configuration**:

- Responses from IdP A must be processed under the selected registration and then have **Issuer/Signature/Audience** verified accordingly. Never let an attacker-controlled header/query pick a tenant and open the entire key ring.
- `employee`'s key ring may be intentionally reused on `partner` if SP ownership is shared and policy permits; such reuse must **be explicitly configured**.
- `ds:KeyInfo` inside a response must not force the system to look up another tenant's private key. Isolate key rings and cap candidate counts.
- Before decrypting an assertion, you cannot trust `NameID`, groups, or email inside it to determine which tenant's key to use.
- After decryption and authentication, authorization still relies on the **local user**, memberships, tenant, and business permissions, not on the fact that a private key unlocked ciphertext.

An identity broker is a different case: the SP trusts keys/issuers from the configured **broker**, while the broker handles trust with upstream IdPs. Do not assume an upstream IdP's key should directly decrypt assertions issued by the broker to the SP.

## 14. Decryption Key Rotation Without Breaking SSO

Changing the SP's encryption certificate is a **two-sided** operation: the SP holds private keys; the IdP selects the public cert to encrypt with.

A safe plan:

1. **Inventory current state**: registration, SP Entity ID, active SP certificate, key type/algorithm, which certificate the IdP imported, and expiration timestamps.
2. **Generate a new keypair** via an approved process, storing the private key in a secret manager/HSM/restricted volume. Deliver the public certificate to the IdP or publish verified SP metadata.
3. **Add the new key at the SP before the IdP switches**. During the overlap window, the SP keeps both old and new private keys as decryption credentials, if policy allows.
4. **Provision the new public certificate at the IdP**, so the IdP wraps CEKs with the new key on the cutover schedule. If the IdP cannot hold two certificates, coordinate an explicit cutover time and rollback plan.
5. Test Responses encrypted with **both certificates** while the overlap window is approved. Monitor unwrap/decrypt errors, issuer, and audience validation.
6. Confirm the IdP **no longer sends ciphertext encrypted with the old key** and in-flight sessions/responses have cleared a reasonable window.
7. **Remove the old key** from registration/keystore, stop publishing the old cert, and revoke or archive offline per policy. Do not leave old keys online indefinitely just because a few requests fail.
8. Maintain an incident response plan if the private key is compromised: revoke/rotate the key, notify the IdP, investigate potentially decrypted ciphertext, and assess exposed sensitive data.

### 14.1. Why Not Delete the Old Private Key Immediately?

The IdP may still be encrypting with the old certificate from a metadata cache or an unsynchronized config version. If the SP removes the old key before the IdP switches over, EncryptedKey cannot be unwrapped.

### 14.2. Why Not Keep Only the Old Key?

Once the SP publishes the new cert, the IdP may start encrypting with the new key. If the SP has not loaded the new private key yet, the SP itself cannot decrypt data encrypted for the new public cert it just published.

**Usually safest practical order:** provision new private key at SP → publish/register new public cert at IdP → switch IdP to new cert → monitor → remove old key. Test the IdP's actual behavior instead of assuming it supports multiple certificates merely because XML metadata allows multiple `KeyDescriptor`s.

## 15. Common Decryption Errors and Analysis

| Symptom | Possible cause | Useful check |
| --- | --- | --- |
| `EncryptedAssertion` present yet SP reports no decryption key | Missing `decryption.credentials` on the right registration | Inspect RP credentials; do not confuse with IdP verification cert |
| Unable to unwrap EncryptedKey | IdP encrypted with a public cert not matching SP private key | Compare cert fingerprint at IdP vs SP cert; check rotation |
| `BadPaddingException`/wrong key | RSA private key mismatch or different OAEP parameters/algorithm | Check keypair and XMLSec `EncryptionMethod`; do not attempt downgrade |
| Cannot decrypt AES content | Improper CEK unwrap, incompatible IV/tag/algorithm/XML ciphertext form | Verify AES mode URI and XML Encryption profile with IdP |
| Error reading private key file | Wrong path, permissions, PKCS#1/PKCS#8 format, unsupported key password | Check secret mount, converter, and keystore |
| IdP keeps old cert after rollover | New cert configured on SP, IdP still encrypts for old key | Keep bounded overlap; sync IdP before removing old key |
| `KeyName` looks right yet decryption still fails | KeyName is only a hint, does not prove matching keypair | Verify actual public/private key and approved key ring |
| Decryption succeeds yet login still rejected | Invalid assertion signature/issuer/audience/time | Investigate the **validation layer**, do not disable signatures |
| Assertion signed then encrypted, SP tries verifying assertion before decrypting | Assertion signature is encrypted inside | Use response decrypter then assertion validation in order |
| Attribute encrypted then Assertion signed, custom service decrypts before verify | Mutates XML inside signed scope | Verify assertion signature before assertion-elements decryption |
| Wrong multi-IdP registration picked | Decryptor uses another IdP/tenant's key ring | Check registration resolver and request correlation |
| SAML Response sent to wrong ACS | Wrong Destination/Recipient/public URL | Check proxy, ACS metadata, registration |
| `EncryptedKey` in different spot than custom code expects | XML Encryption supports multiple key/data linking forms | Use OpenSAML XMLSec and agreed profile |
| Legacy RSA v1.5 or AES-CBC encountered | Legacy IdP/profile | Evaluate upgrade/interop per policy; never lower security unconditionally |
| Request causes high CPU | Too many encrypted keys, candidate keys, or huge XML | Limit input size, algorithms, attempt counts, timeouts, and memory |
| Logs leak decrypted assertion | Debug logs full XML, NameID/attributes | Turn off logging of sensitive content; log only error codes and safe metadata |
| App uses HSM yet converter wants private key file | Loader API incompatible with key storage | Use HSM-capable provider/adapter; never export keys against policy |

### 15.1. Do Not Turn Decryption Errors into an Oracle

If the application returns distinct messages to clients such as "key A matched", "OAEP padding invalid", or "AES tag valid yet XML invalid", an attacker can use the differences as **cryptanalytic signals**. On a public ACS endpoint, return a unified authentication failure and log an **internal classification code** (containing no plaintext/key material) for operations.

### 15.2. Never Fix by Disabling Encryption

When an IdP requires encrypted assertions, enabling plaintext assertions to "temporarily log in" can expose attributes across processing paths/logs or violate contracts. If you want to change the profile, conduct a security review and coordinate both IdP and SP; never change it silently.

## 16. Essential Test Matrix

| Test case | Scenario | Expected outcome |
| --- | --- | --- |
| Valid ciphertext | IdP encrypts with current SP cert, SP has matching private key | Decrypt, then verify SAML; authenticate only if all conditions pass |
| Missing private key | SP holds only public certificate | Fail closed, reject assertion |
| Mismatched private key | SP has old key, IdP uses new public cert | Cannot decrypt |
| Dual keys during rollover | IdP encrypts with old or new cert, SP trusts both | Both decrypt within approved overlap |
| Old key revoked | Request encrypted with old cert after cutoff | Reject, do not auto-reload key |
| Spoofed `KeyName` | Hint requests key outside credential set | Do not access secrets outside allowlist; reject/do not pick |
| EncryptedKey elsewhere | Layout allowed by XML Encryption/SAML profile | Library parser supports or clearly rejects as incompatible |
| Disallowed AES mode | XML specifies algorithm outside policy | Reject |
| RSA v1.5 forbidden by policy | IdP sends EncryptedKey using RSA v1.5 | Reject, no fallback |
| Mismatched OAEP digest/MGF | Right key yet different parameters | Reject/diagnose algorithm; do not disable validation |
| Tampered ciphertext | AES-GCM tag mismatch | Does not decrypt to trusted plaintext |
| Attacker self-encrypted assertion | Uses SP public cert to build new ciphertext | Decryption may succeed; **signature/issuer policy must reject** |
| Validly signed assertion with wrong audience | Decrypted content meant for another SP | Reject |
| Expired assertion | `NotOnOrAfter` passed | Reject |
| Wrong recipient | `SubjectConfirmationData/Recipient` is not valid ACS | Reject |
| Wrong correlation | `InResponseTo` mismatches request when profile requires | Reject |
| Signed then encrypted | EncryptedAssertion wraps signed Assertion | Decrypt first then verify assertion signature |
| Attribute encrypted then signed | Signed Assertion has EncryptedAttribute | Verify assertion before replacing attribute |
| Multiple IdPs | Response from IdP B yet registration A picked | Do not mis-authenticate; apply right registration/trust |
| Multi-tenant | Tenant A sends key hint of tenant B | Do not widen key ring access |
| Malicious XML | DTD/XXE, external reference, or huge XML | Block/limit, do not decrypt arbitrarily |
| HSM error | Remote decryptor unavailable | Fail safely, alert; never log private key |
| Unsynchronized key rotation | IdP still encrypts with old cert after SP deleted key | Test fails, requiring planned sync recovery |

You should run integration tests against a **real SAML IdP or mock IdP capable of issuing EncryptedAssertions**, not rely solely on AES/RSA unit tests. The Java unit test in this lesson proves keypair and tag behavior; it does not prove Spring Security properly validates SAML.

## 17. Controlled Debugging Workflow in Test Environments

A diagnostic workflow that avoids leaking data:

1. Confirm the request hits the ACS endpoint of the **expected registration**, not merely the vendor display name.
2. Check that exported SP metadata has the **encryption certificate** the IdP is using, with fingerprint cross-checked via admin config.
3. Confirm the SP has the **matching private key** for that cert inside `decryption.credentials`, not just the certificate.
4. Inspect key/cert format and filesystem/HSM permissions; never print private keys to logs.
5. Use SAML inspection tools inside a test environment to examine the **structure** of `EncryptedAssertion`, `EncryptedKey`, and algorithms; avoid pasting real assertions into public services.
6. Compare `EncryptionMethod` between IdP and OpenSAML/JCE supported policy; inspect OAEP digest/MGF and content cipher.
7. Separate whether the failure is in **decryption** or **SAML validation**. If decryption succeeds yet the assertion fails issuer/audience, fix metadata/trust/IdP rather than touching keys.
8. During rotation, check which old/new certificate the IdP is actually using; check metadata caches and overlap windows.
9. Verify signed/encrypted element ordering if the app uses a custom decrypter.
10. Record safe evidence: registrationId, permitted SP/IdP entityIds, algorithm URIs, public cert fingerprint, error code, and timestamp; **never log plaintext assertions, sensitive NameIDs/attributes, or CEK/private keys**.

When troubleshooting in production, never dump the entire `SAMLResponse` to console, because it may contain personal data or encrypted/unencrypted assertions exploitable in another context.

## 18. Deployment Checklist

- [ ] IdP and SP agree assertions must be encrypted, without confusing this with signing AuthnRequests.
- [ ] SP generated a dedicated **decryption** keypair and certificate; private key is protected at the SP.
- [ ] IdP imported the exact **SP encryption certificate** bound to the right SP entityId and environment.
- [ ] `RelyingPartyRegistration` holds the right `decryptionX509Credentials`; never mixed with IdP verification certs.
- [ ] CEK transport (e.g. RSA-OAEP) and content encryption (e.g. AES-GCM) algorithms are actually supported by both sides.
- [ ] Processor picks private keys only within the **trusted registration's key ring**, never loading/decrypting with keys arbitrarily named by `KeyInfo`.
- [ ] Never use NameID/email or unverified values to choose tenant/private key.
- [ ] XML Encryption parser blocks XXE, external references, weak algorithms, and enforces resource limits.
- [ ] Distinguish `EncryptedAssertion` from `EncryptedAttribute`/`EncryptedID` when customizing decrypters.
- [ ] Enforce **sign-then-encrypt ⇒ decrypt-then-verify-signature** order for encrypted signed Assertions.
- [ ] For encrypted attributes inside a signed Assertion, verify signature **before** replacing signed XML with plaintext.
- [ ] After decryption, Spring Security still performs signature, issuer, audience, recipient, time, subject confirmation, and request correlation/replay checks.
- [ ] Accept plaintext vs encrypted assertions per explicit policy; never silently lower security.
- [ ] Key rotation has a valid overlap window, old-key retirement, and rollback plan; tested with both certificates.
- [ ] Private keys, CEKs, and plaintext assertions never leak into source control, logs, traces, or user-facing errors.
- [ ] Integration/negative tests cover wrong key, wrong recipient, wrong algorithm, tampered ciphertext, wrong issuer/audience, malicious XML, and multi-IdP.
- [ ] Incident plan exists if the SP private key is compromised or the IdP rotates certificates ahead of schedule.

## 19. Self-Check Questions

**1. Which key does the IdP use to encrypt an assertion for the SP?**

Typically the IdP uses the **SP's public certificate** and a random AES content key. The SP uses its **corresponding private key** to unwrap the content key and decrypt.

**2. Can the SP decrypt with only its public certificate and no private key?**

No. The public certificate lets the IdP encrypt; asymmetric decryption requires the corresponding private key.

**3. Is `ds:KeyInfo` containing KeyName `sp-2026` enough proof to load key `sp-2026`?**

No. It is merely a hint from the message. The SP may only select **from the decryption credentials configured for that registration**, never loading keys specified arbitrarily by the request.

**4. Why are both EncryptedData and EncryptedKey usually present?**

EncryptedData holds the ciphertext of the AES-encrypted XML assertion; EncryptedKey holds the CEK wrapped with the SP's public key. That is the standard hybrid encryption design.

**5. Does successful decryption mean the user is authenticated?**

No. The SP's public key is public, so an untrusted party can also produce ciphertext. The SP must independently verify the IdP signature and SAML conditions.

**6. When does Spring Security decrypt EncryptedAssertion?**

Per `OpenSaml5AuthenticationProvider` documentation, the **Response**-level decrypter handles `EncryptedAssertion`; the assertion-elements decrypter handles encrypted Attributes/IDs inside an Assertion.

**7. If an Assertion was signed and then encrypted, when is the assertion signature verified?**

After **decrypting the entire assertion** and recovering the assertion element containing the signature; then verify using the trusted IdP key.

**8. What if an Attribute was encrypted before the Assertion was signed?**

Verify the assertion signature **before decrypting and modifying** XML containing EncryptedAttribute, so as not to break the signed scope.

**9. When the IdP transitions to a new SP certificate, what must the SP do?**

Provision the new private key **before** the IdP encrypts with the new certificate; maintain an old/new key overlap during an approved window, then remove the old key on schedule.

**10. If RSA-OAEP decryption fails even though the SP has the right private key, what are possible causes?**

Mismatched OAEP digest/MGF parameters, tampered ciphertext, the cert actually used by the IdP does not match, wrong key format/proxy/profile, or an algorithm unsupported by the library.

**11. Should you automatically fall back to RSA v1.5 or AES-CBC when AES-GCM/OAEP fails?**

Never silently downgrade security. Check policy and interoperability, assess risks, and get explicit approval if legacy algorithms must be supported.

**12. Does a passing Java AES-GCM test suffice to prove SAML federation is secure?**

Not yet. You must test XML Encryption serialization and full Spring Security signature/SAML Response validation against a real IdP and negative cases.

## 20. Authoritative References

- Spring Security, **SAML 2.0 Login Overview** — `decryptionX509Credentials`, `Saml2X509Credential.decryption`, SP private key: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses — Customizing Decryption** — `OpenSaml5AuthenticationProvider`, response/assertion decrypters, and signature ordering: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Saml2X509Credential API** — credential types and `decryption(privateKey, certificate)` factory: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot, **SAML 2.0 Relying Party** — `decryption.credentials[*].private-key-location` / `certificate-location`: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- OASIS, **SAML 2.0 Core** — `EncryptedAssertion`, XML Encryption, and combining signatures/encryption: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Errata 05**, Section E43 — `EncryptedKey`/`EncryptedData` referencing: https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- W3C, **XML Encryption Syntax and Processing 1.1** — structure of `EncryptedData`, `EncryptedKey`, algorithms: https://www.w3.org/TR/xmlenc-core1/
- OWASP, **SAML Security Cheat Sheet** — signature validation, XML wrapping, and federation security: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Key takeaway:** `EncryptedAssertion` protects **confidentiality**, not **authentication**. The IdP encrypts with the **SP's public certificate**, and the SP decrypts with the **matching SP private key**, chosen from the **right registration's decryption credentials**; any `KeyInfo` is only a hint. After decryption, Spring Security/OpenSAML must still verify **the IdP signature, issuer, audience, timestamps, recipient, and SAML conditions** before the user is logged in.