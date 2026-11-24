# Verifying SAML 2.0 Metadata Signatures with Out-of-Band Trusted Keys

## 1. Objective and Real-World Scenario

In SAML 2.0 federated login, the **Service Provider (SP)** is the application consuming the login result, while the **Identity Provider (IdP)** is the system authenticating users and issuing SAML Assertions. Before exchanging AuthnRequests and SAML Responses, the SP typically downloads the IdP's **metadata** to learn:

- **IdP Entity ID**: identifier of the issuer.
- **SingleSignOnService**: URL and binding where the SP sends login requests.
- **KeyDescriptor**: key/certificate information published by the IdP so partners can verify SAML Response/Assertion signatures or encrypt data.
- Other policies or capabilities: `WantAuthnRequestsSigned`, NameID format, Single Logout, `validUntil`, and `cacheDuration` if published.

Metadata is part of **federation security configuration**. If someone alters metadata before the SP trusts it, they can swap the IdP SSO endpoint or the assertion verification key. The SP then risks redirecting users to a rogue IdP or trusting an assertion signed by the attacker's key.

This lesson focuses on **verifying the XML signature of SAML 2.0 metadata itself** using **a trusted key provisioned and verified over a channel independent of the metadata being downloaded**.

**Core principle:** a cryptographically valid XML signature proves only that the document was signed with a particular key. To accept metadata, the SP must also know **that key belongs to an authorized metadata publisher**. If the key is chosen solely because it appears inside the unverified document itself, the check can be tricked.

Learning outcomes: distinguish metadata-signing keys from assertion-signing keys, understand the trust anchor establishment process, grasp XML Signature scope, configure Spring Security properly, and handle key updates/revocation safely.

## 2. What Is SAML 2.0 Metadata and Where Is the Signature?

SAML metadata documents use the `urn:oasis:names:tc:SAML:2.0:metadata` namespace and typically take one of two forms:

- **`<md:EntityDescriptor>`**: describes a single SAML entity such as an IdP or an SP; carries `entityID`.
- **`<md:EntitiesDescriptor>`**: aggregates multiple `EntityDescriptor` elements and may nest groups, common for federation operators or metadata aggregators.

SAML metadata can contain an **XML Digital Signature (XMLDSig)** in the `<ds:Signature>` element. The signature may protect an individual `EntityDescriptor` or an `EntitiesDescriptor` containing many entities. Content beneath a **validly signed** element is protected according to the signature's actual reference scope.

Conceptual map example:

```text
md:EntitiesDescriptor (ID="_federation", validUntil="...")
  ds:Signature
    ds:SignedInfo
      ds:Reference URI="#_federation"
      ds:DigestMethod
      ds:SignatureMethod
    ds:SignatureValue
    ds:KeyInfo                  <- key hint info, not self-trustworthy
  md:EntityDescriptor (entityID="https://idp-a.example.test/saml")
    md:IDPSSODescriptor
      md:KeyDescriptor          <- key used for SAML messages, distinct function
      md:SingleSignOnService
  md:EntityDescriptor (entityID="https://idp-b.example.test/saml")
    ...
```

This diagram is a **relationship illustration**, not complete XML. When verifying the signature of the root `EntitiesDescriptor` per the SAML profile, child entities within the signed scope inherit integrity assurance from the root. Still, the SP must check **which entities are authorized**, which `entityID` is expected, which IdP role is used, expiration, and trust config.

### 2.1. Three Locations Easily Mistaken for a "Trusted Key"

| Location / Object | Function | Does it automatically become a trust anchor? |
| --- | --- | --- |
| `ds:KeyInfo` inside metadata's `ds:Signature` | May contain or hint at the **metadata signer's** public key/certificate | **No**; key must be verified through an independent trust policy |
| `md:KeyDescriptor` inside `IDPSSODescriptor` | Publishes the IdP's key for **signing SAML messages/assertions** or encryption | **Trusted only after the metadata source has been authenticated** |
| Key/certificate provisioned out-of-band | Basis for the SP to identify **an authorized metadata signer** | **Can serve as a trust anchor** once verified and bound to the right partner |

An organization might reuse one certificate across roles, yet you must never **assume** that. Metadata signed by an aggregator with a federation operator's key does not mean the enclosed IdP uses that same aggregator key to sign SAML Assertions.

### 2.2. Metadata Signature Differs from SAML Response Signature

These are **two distinct moments and two distinct objects**:

1. **When importing/refreshing metadata:** verify the metadata XML document's signature using a **pre-established metadata trust anchor**. Only afterward use the IdP info inside.
2. **When a user logs in:** verify the SAML Response/Assertion signature using **the IdP's key authenticated via trust configuration/metadata**; also check issuer, audience, timestamps, destination, recipient, and other conditions.

An SP can verify SAML Responses strictly and still be compromised if it **loaded a spoofed response-verification key from forged metadata**.

## 3. Why Must the Key Be Provisioned Out-of-Band?

Suppose the SP downloads metadata from `https://login.example.test/saml/metadata`. If it merely does:

```text
1. Download metadata XML.
2. Read ds:KeyInfo/X509Certificate in the downloaded XML.
3. Use that exact certificate to verify the XML's ds:Signature.
4. If valid, trust the entire metadata.
```

An attacker can generate a new keypair, swap the endpoint/KeyDescriptor in metadata, **sign the metadata with the new key**, and embed the new public key in `ds:KeyInfo`. The signature will match **the key chosen by the attacker**. `signatureValid=true` in step 3 does not prove the metadata came from the real partner.

This is a **circular trust bootstrapping flaw**: using untrusted content to decide who is trusted, then using that entity to verify the same content.

Proper flow:

```text
                   AUTHENTICATED OUT-OF-BAND CHANNEL
IdP / Federation operator --------------------> SP Administrator
             Certificate or public key        |
             + partner identity                 | approves and stores trust anchor
             + SHA-256 fingerprint              v
                                                SP Trust Store
                                                     |
                                                     | trusted key
                                                     v
METADATA SOURCE                                XML Signature Verifier
https://.../metadata ------------------------> verifies signature
                                                     |
                                             PASS + policy checks
                                                     |
                                                     v
                                        Metadata permitted for use
                                         Entity ID, SSO URL, keys
                                                     |
                                                     v
                                        SAML login configuration
```

**"Out-of-band channel"** does not necessarily require a second physical network. It is an **independent trust provisioning and verification chain** not controlled by the unverified metadata payload. For example:

- IdP admins publish the **certificate's SHA-256 fingerprint** in an authenticated, protected admin portal; the SP team compares it against the certificate received over another distribution mechanism.
- The metadata-signer certificate is placed in a change-controlled/code-reviewed config repository or enterprise certificate/secret vault after verifying the issuer.
- In a federation with an organization-trusted operator, the SP receives the **operator's** certificate during official onboarding; the operator's aggregate metadata is verified against that certificate.
- Partners exchange certificates via a security procedure that authenticates the contact person and confirms the fingerprint over a pre-established channel.

**Receiving a certificate in an unverified email/link and comparing it to a fingerprint in that same email/link is not an out-of-band channel.** If an attacker can alter both the certificate and the fingerprint at the same source, the comparison is meaningless.

## 4. Which Keys Must Actually Be Pinned/Trusted?

In a metadata signature verification model, the SP can use:

1. **Pinned signing certificate/public key**: one or more public keys approved for metadata of that exact IdP/operator.
2. **Constrained PKIX trust anchor**: one or more policy-approved CAs/chains/certificates, combined with checks on partner identity, usage, and validity/revocation where applicable.
3. **Federation operator trust**: SP trusts the aggregate metadata signer; accepts only entities signed by the operator within the agreed federation scope.

Every choice must answer:

- **Who** is authorized to sign this metadata?
- **Which key** is permitted?
- **For what scope**: a specific IdP, group of entities, tenant, federation, or environment?
- **Until when**: validity period of the trust anchor and metadata?
- **Who** can add/remove keys and audit those decisions?

**Never automatically treat the JVM's entire HTTPS CA trust store as the list of partners permitted to sign metadata.** Trust for TLS server identity and trust for signing metadata documents serve different purposes; if using PKIX for metadata, enforce a policy binding the signer and partner identity rather than accepting any publicly trusted certificate.

### 4.1. What Is a SHA-256 Fingerprint?

X.509 certificates are commonly stored as PEM or DER. A fingerprint is the **hash of the certificate**; for example, inspect with OpenSSL:

```bash
openssl x509 -in metadata-signer.pem -noout -fingerprint -sha256
```

This command only **computes the fingerprint** from an existing file; **it does not prove the certificate is trustworthy**. An admin must compare the output against a fingerprint received from an **independently authenticated source**. Renewing a certificate while keeping the same public key still changes the certificate fingerprint; document clearly whether you pin the **certificate** or the **public key** so rotation works properly.

Do not use MD5/SHA-1 fingerprints for new verification checks. Verify the full fingerprint value, and bind approval to the right IdP or federation operator.

## 5. Metadata Verification Process Before Use

Separate **trust anchor provisioning** from **metadata download/verification**.

### Phase A — Bootstrap Trust

1. Verify the organization/provider identity and the role of the administrator issuing the key.
2. Receive the metadata signer certificate/public key via an approved process.
3. Cross-check the SHA-256 fingerprint using an independent verification channel.
4. Store the key where only authorized teams/systems have write access, such as a managed trust store or deployment config.
5. Bind the trust anchor to **the exact publisher/metadata source, environment, and allowed entity list**.
6. Record owner, expiration, refresh method, and rotation/rollback procedures; confirm the SP can load that key at startup.

### Phase B — Import Signed Metadata

1. Download metadata from a **preconfigured source** over valid HTTPS; apply timeouts, size limits, and redirect policies.
2. Parse XML safely, blocking DTD/external entities (XXE), XInclude, external references, and dangerous transforms; use a maintained SAML/XMLDSig library.
3. Locate the signed **`EntityDescriptor` or `EntitiesDescriptor` element**, `ds:Signature` position, `ID`, and `ds:Reference`.
4. Retrieve the **verification key from the external trust store**; never take trust decisions from `ds:KeyInfo` or `md:KeyDescriptor` inside the unverified document.
5. Verify XMLDSig: SignedInfo, allowed algorithms and canonicalization, references/digests, cryptographic signature, and **exact scope of protected content**. Reject invalid signatures or unmet trust conditions.
6. Verify **expected entityID and role**, that the signing publisher is authorized to publish that entity, and that target elements reside within the verified scope.
7. Check `validUntil`, `cacheDuration`, and version/status per policy; block expired or revoked data.
8. **Only after passing the steps above**, extract SSO/SLO endpoints, signing/encryption certificates, and IdP attributes to update `RelyingPartyRegistration`.
9. Log audit records of signer, trust anchor fingerprint, entityID, timestamp, outcome, and failure reason. Do not log secret keys or full metadata containing unnecessary sensitive data.

### Phase C — Periodic Refresh

Every newly fetched metadata version must undergo the same verification as the initial load. Metadata validly signed yesterday **does not make today's downloaded version automatically trustworthy**. If new metadata introduces a new IdP key, it may be used only after the new metadata passes verification against a valid trust anchor.

**Fail-closed policy:** never import and activate unverified metadata. If refresh fails, you may continue serving the **previously verified, still-valid** metadata if operational policy allows. Never keep using expired data indefinitely or fall back to disabling signature validation to keep login running.

## 6. XMLDSig Fields to Understand

| Component | Role | Mistake to Avoid |
| --- | --- | --- |
| `ds:Signature` | XML signature attached to metadata element | Checking only for a tag named Signature and assuming the whole XML is signed |
| `ds:SignedInfo` | Algorithms, canonicalization, and reference list | Trusting SignedInfo before validating with the trust key |
| `ds:Reference URI="#..."` | Points to the protected XML element | Accepting a reference pointing to the wrong element or unused XML |
| `ds:DigestMethod` / `DigestValue` | Hash of transformed content | Allowing legacy SHA-1 or skipping digest checks |
| `ds:SignatureMethod` / `SignatureValue` | Cryptographic signature over SignedInfo | Signed by an unknown key yet trusted because the signature matches that unknown key |
| `ds:CanonicalizationMethod` | Normalizes XML before verification | Comparing raw XML text instead of standard canonicalization |
| `ds:Transforms` | Input transformations for the reference | Permitting arbitrary transforms that access the network/execute XSLT |
| `ds:KeyInfo` | Hint for signer's key/certificate | Treating KeyInfo in untrusted metadata as a trust anchor |
| `md:EntityDescriptor/@ID` | Element ID used in XML references | Confusing `ID` with `entityID` or unsafely handling duplicate IDs |
| `md:EntityDescriptor/@entityID` | Logical entity identity | Treating entityID as proof of signature/trust |

The **SAML Metadata Signature Profile** requires an enveloped signature on signed metadata elements; the signed element must carry an `ID` attribute, and the reference must point to that exact ID, such as `URI="#_metadata_001"`. Do not assume a generic `Reference URI=""` for the entire document complies with the **SAML metadata profile**. Signing scope on `EntitiesDescriptor` also differs from individually signing a child `EntityDescriptor`.

### 6.1. Preventing XML Signature Wrapping

One attack pattern places in the XML:

- One element that is **validly signed**, yet is not the element the application reads.
- **Another unsigned element** with a name/ID/structure crafted to trick the processor into picking it.
- A `ds:Reference` pointing to an ID that does not match the element used in config, or duplicate IDs/improperly registered ID types.

If an application merely calls `getElementsByTagName(...)` and grabs the first element, it may consume **content different from what was verified**.

Mitigations:

1. Use a secure XML parser and a dedicated SAML metadata/XMLEnc/XMLDSig library.
2. Bind references to the **expected metadata element**; verify path, position, unique IDs, and the exact XML tree used to extract data.
3. Extract entities/keys/endpoints only from the **verified DOM or verified object**, never re-parsing another copy.
4. Restrict algorithms, reference URIs, transforms, document size, and element counts.
5. For aggregate metadata, confirm the target entity resides **within the signature scope of the trusted aggregator**, not merely inside the same file.

**A valid signature on "some part" does not prove the entire configuration in the file is trustworthy.** This is about verifying *what was signed*, not just *who signed it*.

## 7. Distinguishing Metadata Signatures, TLS, and Assertion Signatures

| Control | What it protects | What it cannot replace |
| --- | --- | --- |
| **HTTPS/TLS** when downloading metadata | Authenticates the TLS endpoint per TLS trust and protects transport | Does not guarantee metadata was signed by the right metadata signer/federation operator per policy |
| **Metadata XMLDSig** + out-of-band trust anchor | Integrity and origin of **signed metadata content** | Does not authenticate users or replace expiry/authorized-partner checks |
| **SAML Response/Assertion signature** | Verifies login messages signed by a trusted IdP | Does not prove initial metadata came from the right source if bootstrapping was compromised |
| **Entity ID, Audience, Recipient, timestamp checks** | Ensures response matches issuer, SP, request, and validity window | Does not replace signature validation |
| **Application authorization** | Decides whether a user has permissions on features/resources | Cannot fix trusting forged metadata or a spoofed IdP |

The SAML metadata spec **does not mandate XML Signatures on all metadata across every exchange model**: direct trusted channels and independent source authentication exist. However, **if your integration policy requires "signed metadata with an out-of-band key"**, the SP must **reject metadata lacking a trusted signature**, even when HTTPS works.

Never merge the two options into "HTTPS is always enough, skip signatures" or "XML signatures are always enough, skip transport protection". They are two controls with distinct scopes.

## 8. Spring Security: Using Metadata Signer Credentials for the Right Purpose

### 8.1. Mechanism to Understand

Modern Spring Security provides `RelyingPartyRegistration` to model SP–IdP pairs, and the **`AssertingPartyMetadataRepository`** API to manage IdP-side metadata. Spring Security documents support for metadata signature verification via **`OpenSaml5AssertingPartyMetadataRepository`** when supplied with a list of `Saml2X509Credential` instances for metadata verification.

Key point from the Spring Security documentation:

> With `OpenSaml5AssertingPartyMetadataRepository`, if verification credentials are **not** provided, the component **does not perform metadata signature validation**.

Therefore, calling `RelyingPartyRegistrations.fromMetadataLocation(...)` to load metadata or merely setting `assertingparty.metadata-uri` in YAML **does not prove** you enforced a policy verifying **metadata signatures with an out-of-band trust anchor**. A library may parse metadata without necessarily enforcing sufficient trust to accept it.

**Distinguish two credential sets in the application:**

- **Metadata-verification credential:** used by the SP to verify **the metadata document** it downloads or refreshes; provisioned independently.
- **Asserting-party verification credential:** used by the SP to verify **SAML Responses/Assertions** when users log in; typically the IdP's key published inside trusted metadata.

The metadata signer certificate and the assertion signing certificate can be different. Never misconfigure a metadata signer where only SAML responses are checked and assume the metadata XML itself was verified.

### 8.2. `verificationCredentials` Configuration Pattern

The snippet below shows **the API usage documented by Spring Security**. It belongs **inside an appropriate Spring configuration class**, where `trustedMetadataSignerCertificate` is an `X509Certificate` loaded from **a trust store provisioned and verified outside the metadata download channel**:

```java
// Snippet in an application using a Spring Security version with this API.
// trustedMetadataSignerCertificate: java.security.cert.X509Certificate
Saml2X509Credential metadataVerificationCredential =
    Saml2X509Credential.verification(trustedMetadataSignerCertificate);

AssertingPartyMetadataRepository metadataRepository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.test/saml/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataVerificationCredential))
        .build();
```

This snippet **is not a standalone Java file**; it requires corresponding Spring Security imports and compatible SAML Service Provider/OpenSAML dependencies. `OpenSaml5AssertingPartyMetadataRepository` and this configuration style may not exist in older Spring Security versions. Before adopting it, check your project's **exact Javadoc/version**.

The crucial part in this lesson is the **source** of `trustedMetadataSignerCertificate`: the SP must **already trust it before** downloading XML. If the loader reads this certificate from `ds:KeyInfo` inside metadata at the same URL, the configuration defeats out-of-band trust.

`metadataRepository` is the IdP-side metadata store. The application still needs to wire it into supplying `RelyingPartyRegistration`, setting SP Entity ID, ACS, SP credentials, and the SAML security filter chain. Creating a metadata repository alone **does not complete login integration**.

### 8.3. Spring Boot `application.yml` Sample Describing Location

Example configuring one SAML registration:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            assertingparty:
              metadata-uri: "https://idp.example.test/saml/metadata"
```

The YAML only illustrates **metadata source and SP entityId**. It **does not prove** metadata signature verification is enabled with an out-of-band trust anchor. To meet this lesson's policy, configure a repository/metadata resolver that verifies signatures in your Spring Security version, or import metadata already verified by a controlled pipeline.

When configuring a custom repository, ensure the application uses **that exact verified repository** rather than leaving another metadata loading path silently bypassing checks.

### 8.4. If Using a Version Without the API Above

When a project uses a Spring Security/Spring Boot version differing from the documented API:

1. Read the Javadoc and provider/metadata resolver classes for your **actual version**.
2. Configure OpenSAML MetadataResolver with a **SignatureValidationFilter** and `SignatureTrustEngine` backed by independently provisioned trust credentials, or validate signed metadata beforehand in a controlled pipeline.
3. Pass only already-verified XML/objects to Spring Security builders/repositories.
4. If using local metadata, govern **the source and refresh of local contents**; sitting on the classpath alone does not prove XML was validly signed.
5. Ensure all updates/refreshes go through the same validation as the initial import.
6. Do not carry over configurations from the **legacy Spring Security SAML Extension** (such as `ExtendedMetadataDelegate`) without checking differences from modern Spring Security SAML 2.0 Service Provider.

**Do not write a custom SAML/XMLDSig parser from scratch** just to get a "signature valid" check. Maintained SAML libraries handle protocol details like ID/reference tracking, signing profiles, canonicalization, and trust engines that short examples easily miss.

## 9. Standalone Java 17: Valid Signature, Tampered XML, and Untrusted Signer

The example below uses the **built-in XML Digital Signature API in JDK 17** to demonstrate three outcomes:

- Metadata signed with **the trusted signer's private key**, verified with a **pre-provisioned public key** ⇒ PASS.
- Metadata whose `entityID` is modified after signing ⇒ FAIL.
- Another party self-signs metadata with its own private key while the SP verifies with its trusted public key ⇒ FAIL.

To reflect the SAML metadata profile concept, the signature uses an **enveloped transform** and **Reference `#_entity001` pointing to the `ID` attribute** of the metadata element. The code places `ds:Signature` before the role descriptor.

**Important scope limit:** the XML document in this program only suffices to illustrate XMLDSig and signature placement; it is **not complete IdP metadata per the SAML schema** (lacks SingleSignOnService, full certificates/roles, validUntil). It also **does not** provide schema validation, trusted entity policy, duplicate-ID/wrapping protection on arbitrary XML, or SAML Response authentication. **Never use `verify` from this example as a production metadata importer.**

File `MetadataSignatureDemo.java`:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.Transform;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.crypto.dsig.spec.TransformParameterSpec;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public class MetadataSignatureDemo {
    private static final String MD_NS =
        "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final XMLSignatureFactory XML_SIG =
        XMLSignatureFactory.getInstance("DOM");

    static Document newMetadata() throws Exception {
        DocumentBuilderFactory builder =
            DocumentBuilderFactory.newInstance();
        builder.setNamespaceAware(true);
        builder.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        builder.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true);
        builder.setXIncludeAware(false);
        builder.setExpandEntityReferences(false);

        Document doc = builder.newDocumentBuilder().newDocument();
        Element entity = doc.createElementNS(
            MD_NS, "md:EntityDescriptor");
        entity.setAttribute("ID", "_entity001");
        entity.setIdAttribute("ID", true);
        entity.setAttribute(
            "entityID", "https://idp.example.test/saml/issuer");
        doc.appendChild(entity);

        Element role = doc.createElementNS(
            MD_NS, "md:IDPSSODescriptor");
        role.setAttribute("protocolSupportEnumeration",
            "urn:oasis:names:tc:SAML:2.0:protocol");
        entity.appendChild(role);
        return doc;
    }

    static void sign(Document doc, PrivateKey key) throws Exception {
        Reference reference = XML_SIG.newReference(
            "#_entity001",
            XML_SIG.newDigestMethod(DigestMethod.SHA256, null),
            List.of(
                XML_SIG.newTransform(
                    Transform.ENVELOPED, (TransformParameterSpec) null),
                XML_SIG.newTransform(
                    CanonicalizationMethod.EXCLUSIVE,
                    (TransformParameterSpec) null)
            ), null, null);

        SignedInfo signedInfo = XML_SIG.newSignedInfo(
            XML_SIG.newCanonicalizationMethod(
                CanonicalizationMethod.EXCLUSIVE,
                (C14NMethodParameterSpec) null),
            XML_SIG.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
            List.of(reference));

        Element entity = doc.getDocumentElement();
        DOMSignContext context = new DOMSignContext(
            key, entity, entity.getFirstChild());
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(entity, null, "ID");
        XML_SIG.newXMLSignature(signedInfo, null).sign(context);
    }

    static boolean verify(Document doc, PublicKey trustedKey)
            throws Exception {
        Element entity = doc.getDocumentElement();
        Node first = entity.getFirstChild();
        if (!(first instanceof Element signatureNode)
                || !XMLSignature.XMLNS.equals(
                    signatureNode.getNamespaceURI())
                || !"Signature".equals(
                    signatureNode.getLocalName())) {
            return false;
        }

        DOMValidateContext context =
            new DOMValidateContext(trustedKey, signatureNode);
        context.setIdAttributeNS(entity, null, "ID");
        context.setProperty(
            "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);

        XMLSignature signature =
            XML_SIG.unmarshalXMLSignature(context);
        if (signature.getSignedInfo().getReferences().size() != 1) {
            return false;
        }
        Reference reference = (Reference)
            signature.getSignedInfo().getReferences().get(0);
        if (!("#" + entity.getAttribute("ID"))
                .equals(reference.getURI())) {
            return false;
        }
        return signature.validate(context);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair approvedSigner = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        Document original = newMetadata();
        sign(original, approvedSigner.getPrivate());
        System.out.println("trusted=" +
            verify(original, approvedSigner.getPublic()));

        original.getDocumentElement().setAttribute(
            "entityID", "https://evil.example.test/idp");
        System.out.println("tampered=" +
            verify(original, approvedSigner.getPublic()));

        Document forged = newMetadata();
        sign(forged, attacker.getPrivate());
        System.out.println("otherSigner=" +
            verify(forged, approvedSigner.getPublic()));
    }
}
```

Compile/run with JDK 17+:

```bash
javac MetadataSignatureDemo.java
java MetadataSignatureDemo
```

Exact stdout:

```text
trusted=true
tampered=false
otherSigner=false
```

**Explanation:**

- `KeyPairGenerator` creates two 2048-bit RSA pairs for learning purposes. In production, the SP **does not generate trusted keys per run**: the metadata signer's public key/certificate must be provisioned and confirmed from **an external source outside metadata**.
- `sign` uses the signer's private key to create `ds:Signature`; `verify` uses **a public key passed in** from the verifier side. In this demo, that public key represents the assumed trust anchor.
- `Reference="#_entity001"` and registering the `ID` attribute demonstrate XMLDSig signing the exact element. `DigestMethod.SHA256` and `SignatureMethod.RSA_SHA256` avoid legacy SHA-1 in the example.
- When modifying `entityID` in signed XML, the digest mismatches ⇒ `tampered=false`.
- When another party generates its own keypair to sign, the signature may be valid **under their key**, yet fails verification against the public key trusted by the SP ⇒ `otherSigner=false`.
- The demo intentionally **omits** `KeyInfo`: this underscores that the verification key is pre-selected by the receiver, not supplied by the document itself.
- `secureValidation` restricts XMLDSig, yet **does not replace** SAML schema, trust policy, certificate lifecycle, size limits, wrapping/duplicate ID checks, and entity allowlists when processing XML from the Internet.

Production models use provisioned X.509 certificates and the OpenSAML trust engine; the JDK demo illustrates only low-level signature mechanics.

## 10. Verifying an Aggregate Metadata Bundle with Multiple IdPs

Sometimes an SP downloads **aggregated metadata** from a federation operator instead of individual files per IdP.

```text
Federation operator
    |
    | signs md:EntitiesDescriptor with OP metadata signing key
    v
  md:EntitiesDescriptor
      md:EntityDescriptor IdP A (KeyDescriptor A)
      md:EntityDescriptor IdP B (KeyDescriptor B)
      md:EntityDescriptor IdP C (KeyDescriptor C)
    |
    v
SP verifies root signature with out-of-band OP key
    |
    v
SP allows only approved entity IDs/roles
```

This does not mean the SP must pin a separate metadata signing certificate for each IdP inside the bundle if it already has a **clear trust relationship with the aggregator** for that scope. However, the SP must know which entities the operator is authorized to publish and constrain trust accordingly. A valid operator signature **does not automatically authorize** arbitrary entities added to the metadata if the app only intends to federate with a specific list of IdPs.

When metadata has signatures at multiple levels:

- Verify the signature at **the level that actually protects the entity being used**.
- Do not mistake an unsigned child `EntityDescriptor` inside a signed and trusted root `EntitiesDescriptor` for an unsigned file.
- Never use an entity **outside** the signed subtree/object.
- Never take IdP C's cert and assume C is authorized to re-sign aggregate metadata meant for A/B.

**Rule:** verify *the signer*, *the signature scope*, *the allowed entity*, and *the validity period*—all four.

## 11. Distinguishing Two Certificate Rotation Operations

### 11.1. Rotating the IdP's Assertion Signing Key

The IdP needs to replace the certificate used to sign SAML Responses/Assertions. The IdP updates `KeyDescriptor use="signing"` in metadata. If the metadata is **signed by a trusted metadata signer**, the SP can verify the new metadata and update the assertion-signing certificate set per policy.

Flow:

```text
Trusted old metadata signer
   |
   v
Validly signed new metadata
   |
   +-- current assertion signing cert
   +-- next assertion signing cert
   |
   v
SP verifies metadata -> accepts overlapping IdP certs per policy
```

The new assertion-signing certificate **does not automatically become a metadata-signing trust anchor** unless policy allows it. It only becomes a trusted credential for verifying assertions after a valid metadata import.

### 11.2. Rotating the Metadata Signing Key

This changes the **trust anchor protecting the metadata itself**. If the publisher rotates the metadata signer from key A to B, merely advertising key B inside new metadata signed by B creates a circular trust bootstrapping deadlock.

Proper procedure:

1. Partner announces the change through an authenticated administrative process.
2. SP receives certificate/public key B and its SHA-256 fingerprint via an **independent channel**, verifying owner and validity.
3. SP adds B to the trust anchor per transition plan; it may trust both A and B **during an approved overlap window**.
4. Publisher issues metadata signed by B; SP verifies using B and runs normal entity/validUntil checks.
5. Monitor refreshes across all SPs and partners; after cutover, remove A from the trust store and audit.
6. Never turn on "accept any signer" mode when rotation fails.

If metadata signed by A publishes certificate B inside `KeyDescriptor`, that **does not implicitly** authorize B to sign future metadata: `KeyDescriptor` normally declares keys for the entity's SAML protocol messages. Authority for B to sign metadata must be explicitly defined in trust policy and provisioning procedures.

### 11.3. Lost or Suspected Compromised Key Scenario

If the metadata signer's private key is stolen, a new document still showing "signature valid" under the old key **no longer guarantees trustworthy data**. The SP must:

- Revoke the trust anchor per incident response guidance and notify relevant parties.
- Inspect/audit metadata imported during the suspect window, identifying altered endpoints or certificates.
- Restore from a verified baseline/valid contract and provision a new key out-of-band.
- Review sessions/tokens, IdP assertion keys, and downstream systems if trust was manipulated.

Never treat a mathematically valid signature as absolute proof after a signer's private key has been compromised.

## 12. Metadata Expiration and Safe Refresh

SAML metadata supports:

- **`validUntil`**: timestamp when metadata expires; may appear on `EntityDescriptor` or `EntitiesDescriptor`.
- **`cacheDuration`**: hint limiting cache duration; does not mean "signature stays valid forever".
- **Signature**: protects metadata integrity, yet an old validly signed file can still be **expired or superseded**.

Example: a metadata file has `validUntil=2026-11-01T00:00:00Z` and a valid signature. When checked on 2026-11-07, **that file must not be treated as currently valid metadata** simply because `SignatureValue` still verifies.

In production, every refresh should record:

```text
metadata_source
expected_entity_id
signer_fingerprint_sha256
signature_validation_result
document_valid_until
last_successful_refresh
next_refresh_due
last_refresh_error
active_metadata_version
```

The stored/cached copy must be **an already-verified copy**. When a new download fails:

- Never activate any unverified data.
- You may retain the previous version **if still within validity and policy**.
- Alert ahead of `validUntil` early enough for partners to remediate.
- Never assume "last known good" means usable forever after expiration.
- Enforce timeouts, retry/backoff, and prevent metadata fetch errors from causing DoS loops.

### 12.1. HTTPS and Redirects During Refresh

Even with signed metadata, still enforce HTTPS, registered hostnames, timeouts, redirect limits, and payload bounds. Never let the metadata loader follow arbitrary URLs from request queries or XML with external references, preventing SSRF and oversized payloads. Use an XML parser that blocks external entities and schema fetches from untrusted sources.

## 13. Attack Scenarios and Misconfigurations

| Scenario | Error / What Can Happen | Correct Outcome |
| --- | --- | --- |
| Metadata SSO URL altered after signing | Digest or signature mismatch | Reject new metadata |
| Metadata self-signed by a stranger | Signature valid under unknown key yet signer not in trust store | Reject |
| `KeyInfo` self-embeds unknown certificate | App treats KeyInfo as trust anchor | Reject; always use an out-of-band trust anchor |
| Metadata lacks signature | Policy requires signed metadata | Reject even if downloaded over HTTPS |
| Metadata signed yet wrong signer | Key not on authorized list | Reject |
| Metadata has valid signature yet wrong `entityID` | IdP config differs from approved partner | Reject or process only authorized entities |
| `EntityDescriptor` A signed, endpoints used from unsigned B | Signed content scope confused | Reject B; never consume content outside signed scope |
| Duplicate IDs or wrapping | Processor may extract XML outside signed content | Reject invalid structure; validate reference and consumed element |
| Metadata past `validUntil` | Signature still valid on old file | Reject per expiration policy |
| Assertion certificate rotation | New metadata signed and trusted | May update assertion verification keys per policy |
| Metadata signing key rotation | New key lacks out-of-band approval | Do not auto-trust new key; require onboarding/rotation |
| Metadata signer revoked | Old key can still produce cryptographically valid signatures | Revoke trust and respond to incident |
| Valid TLS certificate, self-signed XML | TLS authenticates channel only, not metadata signing policy | Reject if signature is not from a trusted metadata signer |
| `verificationCredentials` left empty | Documented repository does not validate metadata signature | Tests/deployment policy must detect and reject |
| Metadata aggregation | Root signed, child IdP entity inside signed subtree | Verify root signer, scope, entity allowlist |
| Malicious external Reference | XMLEnc/XMLDSig fetches external data | Block external URIs/transforms via secure processing |

**Distinguish two QA outcomes:** "XML Signature cryptographically valid" and "metadata trusted and safe to activate" are two separate conditions. Both must pass.

## 14. Testing Matrix for a Metadata Importer

You can build integration tests with a simulated IdP and test metadata signed by dedicated test keypairs:

| Test case | Config / Input | Expected |
| --- | --- | --- |
| Proper signer | Metadata signed by pinned key A, valid entity and expiration | PASS, allowed to import |
| Tampered payload | SSO Location modified after signing | FAIL |
| Different signer | Metadata signed by untrusted key B | FAIL |
| Self-signed KeyInfo | Attacker embeds cert B in KeyInfo and signs with B | FAIL even though self-check with B passes |
| Missing signature | Schema-valid IdP XML without signature | FAIL when policy requires signed metadata |
| Wrong entityID | Validly signed metadata yet entity not in allowlist | FAIL |
| Wrong signing scope | Signature protects A while importer selects data B | FAIL |
| Duplicate IDs | Two elements share the referenced ID | FAIL |
| Signature wrapping | Unsigned element used as configuration | FAIL |
| XML with DTD/XXE | Parser asked to fetch external entity | FAIL, zero outbound fetches |
| External Reference URL | `ds:Reference` pointing to external HTTPS | FAIL per local-only reference policy |
| Expired metadata | Valid signature yet `validUntil` passed | FAIL |
| Nearly expired metadata | Valid signature, very short remaining lifetime | Import or warn per freshness policy |
| Transient refresh failure | Source unreachable, old version still valid | Use previously verified copy only if policy allows, emit alert |
| Metadata B signed under approved key rotation | Both A and B pinned during transition | PASS with B per plan |
| B signs before approval | B not yet provisioned out-of-band | FAIL |
| Key A revoked | Metadata still signed with A | FAIL after A removed from trust |
| Assertion cert rollover | New metadata signed by trusted signer, KeyDescriptor has new key | Import new assertion key per policy |
| Signed aggregate root | Target entity resides in signed root subtree | PASS when scope/allowlist/expiry valid |
| Unknown aggregate root signer | Multi-IdP XML with untrusted signer | FAIL |
| Two IdPs | Metadata signer keys A and B differ | Never accept B under trust policy A |

It is essential to test **from fetching metadata through activating runtime config**. A unit test calling only `signature.validate()` on pre-selected XML can miss a "picked the wrong signed element" bug.

## 15. Operational Checklist When Configuring SAML2 Metadata

- [ ] Know who the metadata publisher/signer is for each IdP or federation operator.
- [ ] Have the metadata signer's certificate/public key and SHA-256 fingerprint verified out-of-band.
- [ ] Trust anchor lives in managed config; never auto-learn keys from `ds:KeyInfo` or `KeyDescriptor` of unverified XML.
- [ ] Policy for pinned keys vs. PKIX documented explicitly; signers scoped by partner/environment.
- [ ] Importer **enforces metadata signature validation** whenever policy requires signed metadata.
- [ ] Never treat `RelyingPartyRegistrations.fromMetadataLocation` or `metadata-uri` alone as proof metadata signatures were checked.
- [ ] Verified Spring Security code uses the exact metadata repository/resolver configured with trust credentials.
- [ ] XML parsed safely without arbitrary DTD/external URI fetches, using an XMLDSig/OpenSAML library supporting SAML profiles.
- [ ] Signature protects the right `EntityDescriptor` or `EntitiesDescriptor`, and the target entity lies within signed scope.
- [ ] Checked entityID, IdP role, key usages, endpoints, `validUntil`, `cacheDuration`, and change policies.
- [ ] Metadata signing certificates and assertion signing certificates are managed for **separate purposes**.
- [ ] Key rotation, bounded overlap, old-key revocation, and compromised-key incident plans exist.
- [ ] Refresh never activates metadata with missing/invalid signatures; last-known-good cache is time-bounded and alerted.
- [ ] Tests for tampered metadata, self-signed keys, wrapping, expiry, and cross-IdP confusion have passed.
- [ ] Business application still enforces user mapping and resource authorization after valid SAML login.

## 16. Self-Check Questions

**1. Metadata has `ds:Signature` and `ds:KeyInfo` containing a certificate. Is verifying with that certificate enough to conclude it is trustworthy?**

No. The signature could verify against a certificate provided by an attacker. The trust anchor must be verified **independently** and bound to an authorized publisher.

**2. What is the key in `md:KeyDescriptor use="signing"` used for?**

Usually to publish the key verifying the IdP's **SAML Response/Assertion** signatures. It is not automatically authorized to sign **metadata**. It is trusted only after metadata is verified through an appropriate trust policy.

**3. Metadata is downloaded over authenticated HTTPS; can signature validation be skipped?**

Depends on policy and trust model. The SAML metadata spec includes trusted distribution models that do not always require XML signatures. **However, this scenario requires signed metadata with an out-of-band key**, so HTTPS does not replace the required signature check.

**4. An XML has a valid signature, yet `entityID` does not belong to a registered IdP; should it be imported?**

No. Beyond the signature, verify that the signer is authorized to publish that specific **entity** and that the entity is on the allowed list.

**5. Why verify `ds:Reference URI="#ID"` and element position?**

Because a signature might protect a **different** element than the one consumed by the program, enabling XML Signature Wrapping. Verify the exact signed subtree and extracted data.

**6. Why must metadata signer keys rotate separately from assertion signing keys?**

The two keys protect **two different objects at two different stages**. Metadata signer key changes require out-of-band approval; assertion keys can rotate via **trusted signed metadata**.

**7. Does Spring Security automatically validate metadata signatures when only `metadata-uri` is configured?**

Never assume so. `OpenSaml5AssertingPartyMetadataRepository` documentation states that without verification credentials, the component **does not** perform signature validation. Configure trust mechanisms matching your version.

**8. Should metadata with a valid signature yet an expired `validUntil` be accepted?**

Not under standard freshness policy: a signature proves content was not tampered with, not that the document remains valid at the current time.

**9. If the IdP rotates its SAML Response signing key, can the SP automatically pick up the new key from metadata?**

Yes, when the **new** metadata is verified against the metadata signer trust anchor and policy allows key rollover. Never consume new KeyDescriptors from unverified metadata.

**10. What is the single most important test to catch broken trust bootstrapping?**

Create metadata signed by an **attacker's key** with the attacker's certificate embedded in KeyInfo, and ensure the system **rejects** it even though self-checking with that embedded key would pass. This proves the verifier uses an independently provisioned trust key.

## 17. Technical References

- Spring Security, **SAML 2.0 Metadata – Verifying Metadata Signatures**; documents `OpenSaml5AssertingPartyMetadataRepository` and `verificationCredentials`: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **SAML 2.0 Login Overview**; `RelyingPartyRegistration` structure and SP/IdP credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS, **Metadata for SAML V2.0**, especially Sections 2, 3 (Signature Processing), and 4 (Publication/Resolution): https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C, **XML Signature Best Practices**, especially trust key establishment, reference scope, external URIs, and wrapping: https://www.w3.org/TR/xmldsig-bestpractices/
- OWASP, **SAML Security Cheat Sheet**, signature trust, static trusted keys, and XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OpenSAML, **SignatureValidationFilter** and trust engines for metadata: https://javadoc.io/static/org.opensaml/opensaml-saml-impl/4.0.1/org/opensaml/saml/metadata/resolver/filter/impl/SignatureValidationFilter.html

**Key takeaway:** merely having `ds:Signature` and a valid `SignatureValue` **is not enough**. The consumer needs a **metadata signer trust anchor provisioned out-of-band**, verifies the exact **signed portion of metadata**, checks signer/entity/time/policy, and **only then** allows using the IdP endpoints and keys inside the metadata.