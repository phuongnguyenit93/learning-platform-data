# Do Not Automatically Trust Certificates Embedded in Unverified Messages

> **Module:** Spring Security – federation · **Group:** Security Hardening. This Knowledge document explains how to establish a **trust boundary** when a SAML Response/Assertion, JWT/JWS/JWK, XML Signature, SAML metadata, or HTTP request carries an X.509 certificate or public key. Core rule: **an adversary-controlled message can carry a key/certificate created by the adversary themselves**, so “verifying a signature with the attached key and getting true” **does not authenticate the IdP/issuer**. You must verify against keys/certificates trusted **from an independent channel** and bind them to the right issuer, tenant, RP, message type, algorithm, audience, and freshness. The Java 17 example can run standalone; the Spring Security snippets are illustrative configurations that must be checked against your exact release.

## 1. Attack Scenario: The Sender Supplies Its Own Proof

A Portal SP application trusts only the IdP `https://idp.example.org/saml`. The browser sends a `SAMLResponse` containing an Assertion named `admin` and `ds:Signature`. Inside `ds:KeyInfo` is `ds:X509Data/ds:X509Certificate`.

Suppose a developer writes this flow:

```text
1. Receive SAMLResponse from the browser.
2. Read X509Certificate directly inside SAMLResponse.
3. Extract the public key from that certificate.
4. Verify ds:Signature using that extracted public key.
5. If Signature.verify() = true, log the user in.
```

**Flaw:** an attacker can generate their own RSA keypair, self-issue an X.509 certificate containing their public key, sign a forged Assertion with the matching private key, embed the certificate in `KeyInfo`, and submit the response. Step 4 still returns **mathematically valid** because the signature and public key belong to the **same attacker**.

**The question to answer is not just “is the signature valid for this key?” but “is this key actually authorized by the IdP for this exact relying party/tenant at this time?”**

### 1.1. Two distinct checks

| Check | Question | If skipped |
| --- | --- | --- |
| **Cryptographic signature verification** | Were the selected bytes signed by the private key corresponding to the selected public key? | Cannot tell if data was tampered with |
| **Trust establishment / key authorization** | Is the selected public key trusted **for this issuer/purpose/tenant** by a source not controlled by the message? | A self-signing attacker can impersonate the IdP |
| **Protocol validation** | Does the signed message have the right issuer, audience, recipient, InResponseTo, status, time, replay, and user context? | A validly signed message can still be abused in the wrong context |
| **Application authorization** | Is the authenticated user permitted to perform this specific action? | Signed `role=admin` does not automatically mean admin privileges |

All four checks can be independent. A “signed” payload does not automatically authorize trusting every claim inside it or every privilege asserted by the issuer.

### 1.2. Learning outcomes

After this lesson, you will:

1. Explain public-key trust sources and why an **embedded certificate is not inherently trustworthy**.
2. Distinguish signature validity, certificate validity, chain/path trust, identity binding, and authorization.
3. Understand `ds:KeyInfo`, `ds:X509Certificate`, `RetrievalMethod`, and XML Signature Wrapping (XSW).
4. Configure Spring Security SAML2 `RelyingPartyRegistration` with IdP verification credentials from verified sources.
5. Distinguish **SAML metadata trusted onboarding** from **certificates embedded in a SAMLResponse**.
6. Apply the same principle to JWT `kid`, `jwk`, `x5c`, `jku`, `x5u`, and server-side trusted JWKS.
7. Know when to use certificate pinning vs PKIX certificate path validation, TLS/mTLS, and trusted reverse proxies.
8. Handle key rollover, multi-tenant issuers, chain expiry/revocation, algorithm confusion, SSRF, and signature wrapping.
9. Run a Java 17 demo showing an **attacker-signed message verifies with the embedded key yet is rejected by the trusted-key verifier**.
10. Design negative tests for untrusted signing keys and release processes.

## 2. The Trust Anchor Must Come from Outside the Message Under Inspection

```text
UNTRUSTED SIDE
browser / HTTP client / SAMLResponse / JWT / XML KeyInfo
      |
      +-- claims issuer = "trusted-idp"
      +-- embedded cert = attacker-generated certificate
      +-- signature = signed with attacker's own private key
      |
      v
Service / Relying Party
      |
      +-- Step A: resolve preconfigured RP/issuer trust context
      |             by server-side configuration and safe routing
      +-- Step B: obtain authorized verification keys
      |             from trusted metadata / pinned cert / authenticated JWKS
      +-- Step C: cryptographically verify SIGNED bytes
      |             with authorized key, not arbitrary embedded key
      +-- Step D: validate issuer, audience, recipient,
      |             time, InResponseTo, replay, assertion semantics
      +-- Step E: map trusted identity to local authorization
      |
      v
Authenticated user (only if every required step passed)
```

A claim inside the message like `Issuer=idp.example.org` **does not prove** the message came from the real IdP. It can only serve as a **selector/hint** to pick an **approved trust configuration**, after which the signature must verify against an authorized key belonging to that configuration.

### 2.1. Which sources can establish trust?

- An IdP certificate obtained by an administrator via an **authenticated channel** and stored in configuration/RelyingPartyRegistration.
- SAML metadata fetched from a **trusted IdP address**, protected by TLS and onboarding governance; if policy requires signed metadata, **verify the metadata signature with a pre-existing trust anchor**, never self-supplied from that metadata.
- OIDC discovery `issuer` **preconfigured by the RP/Resource Server**, where the metadata's `jwks_uri` is accessed under HTTPS/hostname/egress policy and issuer binding.
- A server-side fixed JWKS URL bound to a trusted issuer. Keys fetched from that endpoint are not automatically valid for other issuers.
- An organization-managed local truststore/PKIX trust anchors, with appropriate certificate chain, identity binding, EKU/KU, and revocation policies.
- An independent trust-management service/KMS/certificate manager with auditing and change approval.

**Not trust sources:** an arbitrary PEM in SAMLResponse, raw `x5c` in a JWT header, unverified `iss` claim, HTTP request body `certificate`, browser-sent mTLS certificate headers, or an adversary-chosen `jku` URL.

### 2.2. TOFU and automated onboarding

“Trust On First Use” can fit specific controlled protocols/scenarios, yet is **not a safe default for SAML IdP signing keys or JWT issuers**. If you accept a cert on the first unverified login request and pin it automatically, an attacker can hijack initial trust.

If an organization automates onboarding IdPs/tenants, there must be **administrative approval of issuer/entityID and key source**, domain ownership verification, trust-policy checks, egress controls, and auditing—never let any browser POST add a trusted issuer.

## 3. X.509 Certificates: Four Frequently Confused Layers

### 3.1. A certificate containing a public key does not equal trust

An X.509 certificate typically contains subject, issuer, public key, validity period, serial, extensions, and a CA signature. You can parse it into an `X509Certificate` and call `getPublicKey()` to verify a signature. Successful parsing **is not trust validation**.

**A self-signed certificate** can contain:

```text
Subject: CN=Corporate Identity Provider
Issuer:  CN=Corporate Identity Provider
Validity: 2026-01-01 to 2030-01-01
Public key: attacker-owned RSA key
Signature: signed by attacker's same private key
```

Names and validity can all be chosen by the attacker. Calling `cert.verify(cert.getPublicKey())` on a self-signed certificate only proves the cert's signature structure matches **its own self-supplied public key**, not that it is a CA/IdP trusted by the RP.

### 3.2. Meaningful vs meaningless checks

| Java/PKIX operation | What it proves | What it does NOT prove |
| --- | --- | --- |
| `CertificateFactory.generateCertificate` | Input parses as a certificate | The cert's issuer is trusted |
| `x509.checkValidity()` | Current time falls inside the cert's interval | The cert belongs to a registered IdP |
| `x509.getPublicKey()` | Extracts the public key | The key is authorized to sign login Assertions |
| `x509.verify(x509.getPublicKey())` | For self-signed certs, cert signature matches self key | The cert has a trusted issuer |
| `Signature.verify(signatureBytes)` with embedded key | Payload signature matches that key | The key belongs to a trusted IdP |
| `CertPathValidator` with server-configured trust anchors | Builds/validates a trust path per PKIX and params | Payload matches app's audience/issuer |
| Exact trusted SPKI/cert pin vs registry | Key/cert was approved for partner per pin policy | SAML assertion is protocol- and replay-valid |

PKIX chain validation must also consider certificate validity, name/identity binding, key usage, extended key usage, revocation if required, and application certificate policies. Never treat “chain ends at **any public CA**” as sufficient for a certificate to sign SAML assertions for a **specific IdP**.

### 3.3. SAML certificate pinning differs from TLS PKI

In many SAML federations, IdPs use **self-signed X.509 signing certificates** published in metadata or exchanged directly with the SP. The SP may **trust a specific signing certificate** onboarded securely without requiring chaining to a public browser CA. This is **explicit key/certificate trust**, valid when governed and bound to the right IdP.

Conversely, forcing “public-CA certificate chain trust” on all signing certs can both **reject legitimate IdPs** and **open the door to unrelated certificates** unless key/subject are bound to the IdP. Choose the trust model explicitly.

### 3.4. Truststore, certificate store, and private key store

- **Truststore / approved verification credentials:** public certificates/keys permitted to **verify** messages from an IdP.
- **SP keystore / private keys:** used by the SP to **sign AuthnRequest/LogoutRequest** or **decrypt EncryptedAssertion**.
- **TLS server certificate:** authenticates the HTTPS origin on the network.
- **mTLS client certificate:** authenticates the client connection in a TLS handshake when actually verified by the gateway/server.
- **Certificate embedded in message:** message-supplied data; usable at most as a **hint**, never trusted on its own.

An RP's private key does **not** become an IdP verification credential. And `idp.example.org`'s public TLS cert is **not automatically** the IdP's SAML signing cert unless the trust contract specifies so.

## 4. SAML 2.0: KeyInfo Is Precisely Where Forgeries Can Be Placed

### 4.1. An XML Signature can carry a certificate

XML example—**not a complete assertion**, structural illustration only:

```xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <!-- CanonicalizationMethod, SignatureMethod,
         Reference URI, Transforms, DigestMethod, DigestValue -->
  </ds:SignedInfo>
  <ds:SignatureValue>BASE64_SIGNATURE</ds:SignatureValue>
  <ds:KeyInfo>
    <ds:X509Data>
      <ds:X509Certificate>BASE64_DER_CERT</ds:X509Certificate>
    </ds:X509Data>
  </ds:KeyInfo>
</ds:Signature>
```

`KeyInfo` is a vehicle for key-identification/related data. That an XML Signature parser can find a key inside `KeyInfo` does **not** mean the key is permitted by the app. W3C XML Signature Core separates key information from application trust policy.

### 4.2. Step-by-step forgery scenario

```text
Attacker:
  generate keypair K_attacker
  create X509 certificate containing public(K_attacker)
  build Assertion:
    Issuer = trusted IdP entityID
    NameID = admin@example.org
    Role = ADMIN
  sign Assertion with private(K_attacker)
  embed certificate in KeyInfo
  POST SAMLResponse to /login/saml2/sso/portal

Vulnerable SP:
  publicKey = KeyInfo.X509Certificate.publicKey
  Signature.verify(publicKey) == true
  accepts admin  <-- TRUST BOUNDARY BROKEN

Hardened SP:
  registration = server-side trusted configuration
  trustedKeys = verification credentials for expected IdP
  verify signature with trustedKeys
  K_attacker is not in trustedKeys => REJECT
```

An attacker-written `Issuer` name in XML cannot turn the attacker's private key into an IdP key. Never accept a new key just because the Subject DN looks right, the certificate has a CN matching the IdP, `KeyInfo` matches a filename, or the cert is “unexpired”.

### 4.3. Never use a message to self-register a trusted IdP

Flawed by design:

```java
// ANTI-PATTERN — do not use.
// X509Certificate supplied = parseCertFromSamlKeyInfo(untrustedXml);
// Signature signature = findSignature(untrustedXml);
// if (verifyWith(signature, supplied.getPublicKey())) {
//     authenticateNameId(readNameId(untrustedXml));
// }
```

The snippet above is illustrative flawed pseudocode, not a complete Spring Security API. The dual flaw is **adversary-chosen key** and **NameID read from XML unbound to the exact signed subtree**.

### 4.4. KeyInfo may be only a hint, never a trust anchor

An SP can:

1. Select a trusted `RelyingPartyRegistration` from server-side route/state or a mapped issuer candidate.
2. Retrieve the **approved set of IdP verification credentials** from the registration.
3. Verify the XML signature with a key in that set.
4. If `KeyInfo` carries a certificate/key name, use it solely to **pick a candidate within the already trusted set**; never add keys to the set from the message.
5. After verification, check whether the key is allowed to sign this SAML document type at this time, plus claims/protocol rules.
6. Handle session/authorization from the **verified assertion**.

Some SAML implementations ignore `KeyInfo` altogether; that avoids confusion when trusted signing keys are fixed. The OWASP SAML Security Cheat Sheet recommends using keys stored in a local trusted source and ignoring untrusted KeyInfo.

## 5. XML Signature Wrapping: Even a Valid Signature Can Yield the Wrong Assertion

### 5.1. Two independent questions

Even when verifying with the **right trusted IdP key**, an app can still fail if its XML parser/handler reads the user name from a **different XML node** than the node protected by the signature.

```text
SAMLResponse
  Assertion[@ID="signed-1"]
    Subject/NameID = normal-user
    ds:Signature references #signed-1  [VALID]

  malicious wrapper/another node
    Subject/NameID = admin
    [NOT SIGNED]
```

If code calls `getElementsByTagName("NameID")[0]` or queries unbound to the verified assertion, an attacker can exploit XML Signature Wrapping (XSW). Libraries defend against XSW differently; **never manually parse and wire an XML Signature check to a business mapper via unchecked DOM queries**.

### 5.2. Hardened SAML validation rules

- Use a maintained OpenSAML/Spring Security version; never hand-roll XMLDSig with regex.
- Disable DTD/external entities/XXE; bound size, depth, and assertion count.
- Perform schema validation with a **local, trusted** schema when required by threat model/implementation; never auto-download schemas from untrusted URIs.
- Accept only policy-approved canonicalization/signature/digest algorithms and transforms; avoid weak algorithms.
- Verify unique IDs; signature Reference URI must point to the exact expected element; disallow duplicate ID masquerading.
- Bind subject/attributes/conditions to the **actually verified assertion**, never selecting nodes by global search.
- Verify `Response`/`Assertion` signatures per security profile; never accept unsigned data outside the signed subtree.
- Validate `Issuer`, `AudienceRestriction`, `Recipient`, `Destination`, `NotBefore`, `NotOnOrAfter`, `InResponseTo`, `SubjectConfirmationData`, and replay.
- Never trust `NameID` or `Role=ADMIN` before all signature/protocol checks complete.
- Disable remote retrieval via `RetrievalMethod`/external References when unneeded and tightly control sources.

**Note:** “verifying an XML signature” does not guarantee you verified the **document/element the application actually consumes**. This security boundary is just as critical as not trusting embedded certificates.

## 6. Spring Security SAML2: Verification Credentials on Registration

### 6.1. Defining trust explicitly

Spring Security SAML2 service provider configures **IdP verification certificates** in `RelyingPartyRegistration.assertingPartyMetadata.verificationX509Credentials`. These certificates must come from a **trusted onboarding process**, never replaced dynamically with certificates extracted from POSTed `SAMLResponse`.

Spring Boot YAML example (requires other SAML2 application components):

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:trusted-idp-signing.pem"
```

The file `trusted-idp-signing.pem` is **onboarded and verified via an independent channel**, not uploaded by users at callback. `sign-request: false` is only an illustrative profile choice, not a general security recommendation: production must follow IdP and SP AuthnRequest signing requirements.

### 6.2. Java registration fragment with trusted certificate

Per the Spring Security SAML2 reference, you can configure:

```java
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
    .Saml2X509Credential;

// Fragment: trustedCertificate is an X509Certificate read
// from a TRUSTED/PINNED source, never from an inbound SAMLResponse.
Saml2X509Credential verifying =
        Saml2X509Credential.verification(trustedCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistration
    .withRegistrationId("corporate")
    .assertingPartyMetadata(party -> party
        .entityId("https://idp.example.org/saml")
        .singleSignOnServiceLocation("https://idp.example.org/sso")
        .verificationX509Credentials(c -> c.add(verifying)))
    .build();
```

This is a Spring Security application fragment, not a standalone Java file: it requires the `spring-security-saml2-service-provider` dependency, trusted certificate loading, RP entityId/ACS, and full filter chain/metadata registration per deployment. The `assertingPartyMetadata` API reflects current docs; older Spring Security versions use different builder/metadata method names—check your release.

**Never write a replacement `AuthenticationProvider` just to call `Signature.verify(certFromKeyInfo)`.** Use the default OpenSAML provider and verify registered IdP trust credentials; if customizing, keep all protocol validators intact.

### 6.3. Do not confuse certificate roles

| Credential in Spring SAML2 | What is it for? |
| --- | --- |
| `assertingParty.verificationX509Credentials` | Trusted public certs used to verify IdP SAML messages |
| `relyingParty.signingX509Credentials` | SP private key + cert used to sign AuthnRequest/SLO requests if required |
| `relyingParty.decryptionX509Credentials` | SP private key used to decrypt encrypted assertions |
| `assertingParty.encryptionX509Credentials` | IdP's public cert used to encrypt outbound SP messages if profile requires |

Never add a **certificate embedded in an inbound Assertion** into `verificationX509Credentials` during request handling. That literally promotes untrusted data into trust state.

### 6.4. Multi-tenant IdPs

Both IdP A and IdP B may send assertions to a shared ACS endpoint. Never pool all certificates into one global trust set and verify only “signed by any IdP”; you must bind **registration/tenant/expected issuer and audience**.

```text
tenant-A:
  issuer = https://idp-a.example.org
  trustedSigningKeys = [A1, A2]
  serviceProviderEntityId = https://portal.example.org/sp/a

tenant-B:
  issuer = https://idp-b.example.org
  trustedSigningKeys = [B1]
  serviceProviderEntityId = https://portal.example.org/sp/b
```

If a message claims issuer A yet is signed by key B, never accept it merely because B is also a trusted IdP in the system. A tenant selector from path/request acts as a candidate to resolve configuration; **never let a string in an unverified assertion pick an arbitrary trust root**. For IdP-initiated SSO, require an onboarded IdP↔RP mapping plus appropriate replay/recipient/audience checks.

## 7. SAML Metadata Also Needs Trust Bootstrapping

### 7.1. Where does metadata come from?

SAML metadata can contain `EntityDescriptor`, `IDPSSODescriptor`, `KeyDescriptor use="signing"`, and `ds:X509Certificate`.

Metadata is **not automatically trusted** just because it contains `KeyDescriptor`. Before using it to build a `RelyingPartyRegistration`:

- The metadata URL must belong to an onboarded IdP, never taken from `?metadataUrl=...` in a request.
- Check the HTTPS TLS endpoint/certificate chain and DNS; defend against SSRF and redirect/host confusion.
- If policy requires signed metadata: verify the metadata signature with a **pre-existing metadata signing certificate/trust anchor**, never with an unverified certificate embedded in the metadata itself.
- Check entityID, SSO endpoints, signing roles, validUntil/cacheDuration, size, refresh frequency, and rollout procedures.
- Changing signing keys in metadata is a **trust configuration change**, requiring audit, alerts, and proper approval.

### 7.2. Conditional Spring Security metadata signature verification

Spring Security SAML metadata docs provide `OpenSaml5AssertingPartyMetadataRepository` with `verificationCredentials`. Important caveat: **if no metadata verification credentials are supplied, this component does not perform metadata signature validation** per docs; you must configure your trust policy accordingly.

```java
// Fragment per Spring Security SAML2 metadata reference.
// metadataVerificationCredential comes from trusted admin configuration,
// never from the XML metadata currently being verified.
OpenSaml5AssertingPartyMetadataRepository repository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.org/metadata")
        .verificationCredentials(
            credentials -> credentials.add(metadataVerificationCredential))
        .build();
```

This is a directional fragment needing proper imports/version/dependencies. If the federation metadata signing cert differs from the IdP SAML Assertion signing cert, manage them separately; **never confuse the two trust anchors**.

### 7.3. Why a TLS metadata endpoint is not everything

HTTPS authenticates the server origin via Web PKI per the TLS truststore, yet a mismanaged HTTPS endpoint or compromised IdP can still publish a malicious key. For high-assurance federations, metadata also needs signed metadata/trust registries or manual approval, certificate-change alerts, contract-based pinning, and rollback controls.

Never fetch any metadata URL supplied by the SAMLResponse itself; doing so creates both **SSRF** risk and lets the adversary pick their own signing key.

## 8. Certificate Rollover: Time-Bounded Trusted Old + New

### 8.1. Valid rotation

The IdP needs to rotate its signing key from `K_old` to `K_new`. The SP must receive keys via an **authenticated metadata/trust registry** and support a time-bounded overlap:

```text
T0  SP trusts K_old; IdP signs K_old
T1  IdP announces K_new through verified metadata/trust channel
T2  SP trusts [K_old, K_new] for IdP A only
T3  IdP starts signing K_new; SP accepts it
T4  Valid old messages expire, caches drained, tests pass
T5  SP retires K_old and records audit
```

**Never use inbound KeyInfo to auto-add K_new:** an attacker can mimic a rollover request. While holding two keys in the trust set, keep issuer/registration scoping and allowed algorithms intact.

### 8.2. Compromise differs from routine rotation

If `K_old` is compromised, **do not keep a long overlap** just to reduce 401s. Remove the compromised key, revoke affected sessions/messages if policy dictates, publish new trust config via admin channels, limit replay, investigate, and accept reauthentication/disruption.

An expired certificate is not necessarily equivalent to a compromised one; SAML pinned-cert policies govern validity per federation, yet never silently waive critical trust and signature protections. Any decision to accept an expired certificate must be explicit—never “auto-trust certs from messages to avoid expiry errors”.

### 8.3. Key ID/KeyInfo hints during rollover

A message may carry a key name/id/certificate to help pick between two trusted keys. Hints may only be used to **filter candidates within the trust set**:

```text
incoming KeyInfo says "new-kid"
      |
      v
Select trusted key IDs registered for IdP A
      |
      +-- If "new-kid" belongs to IdP A set: try verification
      +-- Else: reject or try policy-approved keys
      |
      X-- Never fetch/adopt arbitrary new key by this hint
```

Matching `kid` text is not guaranteed unique across issuers/tenants; namespace by IdP. If verification fails, never fall back to “whatever key is embedded”.

## 9. JWT/JWS: Applying the Same Principle to jwk, x5c, and jku

A JWT can be a **signed JWS**. The sender-controlled JOSE header may contain:

```json
{
  "alg": "RS256",
  "kid": "key-2026-11",
  "jwk": {
    "kty": "RSA",
    "n": "UNTRUSTED_BASE64URL_MODULUS",
    "e": "AQAB"
  }
}
```

`jwk` in the header is a **message-embedded public key**. If an app uses it as the verification key and accepts the JWT, an attacker who self-signs a token with `sub=admin` passes the math check. Many JWT libraries have sound defaults; bugs usually stem from custom key resolvers or dynamic trust logic rather than every decoder itself.

### 9.1. JOSE header parameters requiring caution

| Header | Meaning | Security Rule |
| --- | --- | --- |
| `alg` | Algorithm declared by message | Permit only **server-configured acceptable algorithms**; never trust attacker-requested algorithms |
| `kid` | Key identifier | Only **lookup** within issuer-specific trusted keyset; bound input, never pass directly to SQL/file paths |
| `jwk` | JWK public key supplied in JOSE header | Never treat as an authorized issuer key by itself |
| `x5c` | X.509 certificate chain in header | Never treat self-attached chain as trust anchor; validate per trust policy |
| `jku` | URL to JWKS | Never fetch arbitrarily from header; SSRF and key substitution |
| `x5u` | URL to X.509 cert/cert chain | Never fetch arbitrarily from header; SSRF and key substitution |
| `crit` | Critical extensions | Reject extensions not properly understood/supported |
| `typ` | JWT type indicator | Enforce profile to avoid confusing ID Tokens, access tokens, and logout tokens |

RFC 8725 specifically warns against **algorithm confusion** (`alg=none`, RS256↔HS256), header-controlled key selection, issuer/key binding, audience validation, and SSRF when following `jku`/`x5u`.

### 9.2. Which parts of a JWT may be read before verification?

The Base64URL header/payload may be **tentatively parsed** to read `kid` or a candidate issuer/alg per decoder architecture, yet **must not** be used as authenticated identity or to open arbitrary trust sources. Only after signature verification with an authorized issuer key may claims like `iss`, `aud`, `sub`, `exp`, and `nbf` be evaluated as authentication results.

Never use raw `iss` from a token to call `https://{iss}/.well-known/openid-configuration` against any attacker-supplied host. In multi-issuer setups, the resolver must pick from an **issuer registration allowlist** and load discovery/JWKS from trusted config.

### 9.3. Trusted JWKS is not untrusted jku

Two URLs that look similar have completely different trust:

```text
Trusted configuration:
  issuer = https://idp.example.org
  jwks_uri = https://idp.example.org/.well-known/jwks.json
  approved through OIDC discovery / admin trust

Untrusted JWS header:
  jku = https://attacker.example/keys.json
  x5u = http://169.254.169.254/latest/meta-data/...
```

Only server-configured `jwks_uri`/trusted discovery may be called, with HTTPS, SSRF/egress restrictions, and cache/rotation controls. Token-supplied `jku`/`x5u` must not drive network fetches. Even with HTTPS to an attacker host, it is still an attacker-controlled public key.

### 9.4. Trust only keys of the exact issuer and token purpose

If a system trusts IdP A and IdP B, never accept a token claiming `iss=A` signed with a valid key from B. RFC 8725 requires cryptographic keys to belong to the confirmed issuer and `aud` to match the recipient. Also distinguish OIDC-client ID Tokens, API access tokens, logout tokens/SETs, and service-to-service tokens using dedicated validation rules.

**Wrong:** `Signature.verify() == true` against “any key in a global truststore” and trusting every `sub`. **Right:** verify with the **expected issuer/token-type trust set** along with aud/alg/lifetime/nonce or state requirements.

## 10. Spring Security Resource Server: Keys and Issuers from Trusted Config

### 10.1. YAML config for approved issuer/JWKS

Spring Boot Resource Server example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org"
          jwk-set-uri: "https://idp.example.org/.well-known/jwks.json"
          audiences:
            - "portal-api"
```

`issuer-uri` binds the token's `iss` to the configured issuer. `jwk-set-uri` is supplied by **server config**, not read from the JWT header. Configuring both values can allow runtime startup without an immediate discovery call depending on Spring Boot/Security version. `audiences` is a Spring Boot JWT resource server property in supporting versions; on other versions, add an explicit audience validator. Either way, verify TLS/JWKS sources and configure allowed algorithms appropriately.

### 10.2. Java JwtDecoder fragment: issuer + audience validation

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.core.ClaimAccessor;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.OAuth2Error;

// Fragment: issuer URL is supplied by trusted server configuration.
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.org";
    NimbusJwtDecoder decoder = (NimbusJwtDecoder)
        JwtDecoders.fromIssuerLocation(issuer);

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = token ->
        token.getAudience().contains("portal-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
```

This is a **Spring Bean fragment**, not a standalone runnable file and does not replace a full `SecurityFilterChain`. The `ClaimAccessor` import in the sample may be removed if your IDE flags it unused. Declare exact Spring Security/Boot versions and JWK source trust; when setting validators, **do not accidentally drop other default checks**. JWT validation should cover issuer, audience, timestamp, signature, and allowed algorithms; `JwtDecoders.fromIssuerLocation` binds discovery to a **server-configured** issuer.

### 10.3. Do not configure an arbitrary decoder from a token header

Anti-pattern:

```java
// WRONG — PSEUDOCODE.
// String jku = parseUntrustedJwtHeader(token).get("jku");
// JwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jku).build();
// return decoder.decode(token);
```

The bug is letting the attacker choose the JWKS URL, enabling SSRF to internal endpoints and self-supplying “valid” keys. Instead, issuers/registrations must be server-managed and **key sources must follow an allowlist/trust contract**.

### 10.4. Algorithm allowlist

Spring Security's `NimbusJwtDecoder` supports builder methods to permit only supported JWS algorithms, e.g. `.jwsAlgorithm(SignatureAlgorithm.RS256)` depending on version. Never accept `alg=none` or switch automatically to symmetric HMAC just because the token header says so. RFC 8725 recommends binding each key to its exact algorithm and enforcing algorithm policy independently of attacker input.

**Never use a valid signature to ignore `aud`:** a genuinely signed token meant for another application must be rejected.

## 11. TLS and mTLS: Certificates in Messages Differ from Handshake Certificates

### 11.1. Server TLS certificates and self-sent headers

When the app calls `https://idp.example.org/metadata`, the TLS client verifies the server certificate chain and hostname against the truststore. The certificate **of the TLS connection** is not the same thing as a PEM inside an **HTTP response body**.

Similarly, when a gateway terminates mTLS:

- The TLS handshake verifies the client certificate chain/policy.
- The gateway determines the authenticated client identity.
- The gateway may forward that identity over an authenticated internal channel to Spring.
- Spring must not treat an `X-Client-Cert` header sent directly by an internet client as proof of mTLS.

If the edge uses `X-Forwarded-Client-Cert`, strip untrusted incoming headers, authenticate the connection to the backend, restrict hops/gateways, and configure trusted headers per deployment. A self-signed certificate sent inside a JSON body never becomes a TLS client certificate.

### 11.2. Certificate identity binding

Even when the PKIX chain is valid and unexpired, the app must still match the **exact identity**: hostname for TLS servers; allowed workload/service identity, EKU/KU, or SPIFFE ID in mTLS systems; IdP entityID/key roles in SAML. Never treat “issued by a public CA” as a license to sign assertions for any IdP.

### 11.3. Preventing SSRF in certificate retrieval

A signature handler that automatically follows `ds:RetrievalMethod`, `x5u`, `jku`, or `URI` in XML References can reach internal metadata endpoints, loopback, cloud instance metadata, or redirect URLs. Disable external retrieval if unneeded; if required, enforce host/scheme allowlists, DNS/IP/redirect restrictions, TLS validation, egress controls, and size/time limits, without forwarding credentials/cookies.

## 12. Do Not Mix Certificates Across Protocols

| Protocol/scenario | Primary trust source | Untrusted data not trusted automatically |
| --- | --- | --- |
| **SAML 2.0 browser SSO** | IdP verification credentials in registered trust configuration or verified metadata | `ds:KeyInfo`, `ds:X509Certificate`, unverified Issuer |
| **SAML metadata ingestion** | Trusted HTTPS location + signed metadata trust anchor when required, operator approval | `KeyDescriptor` inside unverified metadata |
| **OIDC ID Token** | Issuer-configured discovery/JWKS, client_id/nonce rules | `jwk`, `x5c`, `jku`, `x5u` in untrusted JWT |
| **OAuth2 API access token** | Trusted AS/issuer JWKS and API audience/token profile | Attacker-chosen token header key/issuer |
| **mTLS service authentication** | Validated TLS peer certificate chain/identity, trusted ingress path | PEM/HTTP `X-Client-Cert` unprotected by gateway |
| **Signed webhook** | Public key/HMAC secret pinned per webhook provider and payload context | Request-supplied webhook key URL/header |
| **CAS native back-channel logout** | Trusted CAS endpoint/network/message verification per CAS client deployment | `logoutRequest` XML containing SAML namespace does not auto-carry SAML signature trust |

**Flows are not interchangeable:** a SAML `KeyInfo` public key is not an OIDC JWKS registration. A CAS logout XML namespace resembling SAML2 does not make it a signed SAML2 SLO profile. Spring Security must apply the exact protocol handler/validator for each case.

## 13. Standalone Java 17: A Valid Signature with a Self-Supplied Key Still Gets Rejected

The example creates three RSA keypairs: old IdP (`trustedOld`), admin-approved new IdP (`trustedNew`), and attacker (`attacker`). Each can sign an envelope with its own key. The envelope includes `advertisedPublicKey` — a **simplified model for a public key from X.509 `KeyInfo` or JWT `jwk`**. The program intentionally avoids generating X.509 certificates because plain JDK 17 lacks a convenient public API for self-issuing X.509 certs; the trust principle is identical.

The program illustrates two verifiers:

- **Naive:** extracts the key from the envelope itself and verifies. Attacker forges a signature and embeds their own key → returns `true`.
- **Hardened:** ignores the embedded key as a trust source; verifies only against **public keys registered by a trusted admin for the expected issuer**, while also checking issuer, audience, and expiry. Attacker → `false`.

**Security limitations:** this is not SAML XMLDSig, JWS/JWT, PKIX, JGSS, or Spring Security; it uses plain JCA RSA signatures to clarify the relationship between signature math and trust. The `canonical` string in the demo is not XML canonicalization or JWT signing input. Never use this `Envelope`/`trustedVerify` directly for production authentication.

Save file `UntrustedCertificateDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.List;

public class UntrustedCertificateDemo {

    record Envelope(
            String issuer,
            String audience,
            String subject,
            Instant expiresAt,
            PublicKey advertisedPublicKey,
            byte[] signature) {}

    static byte[] signedBytes(Envelope e) {
        String canonical = e.issuer() + "\n"
                + e.audience() + "\n"
                + e.subject() + "\n"
                + e.expiresAt().toString();
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    static KeyPair rsaKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static Envelope issue(
            KeyPair signer, String issuer, String audience,
            String subject, Instant expiresAt)
            throws GeneralSecurityException {

        Envelope unsigned = new Envelope(
                issuer, audience, subject, expiresAt,
                signer.getPublic(), new byte[0]);
        Signature signing = Signature.getInstance("SHA256withRSA");
        signing.initSign(signer.getPrivate());
        signing.update(signedBytes(unsigned));

        return new Envelope(issuer, audience, subject, expiresAt,
                signer.getPublic(), signing.sign());
    }

    static boolean verifyWith(Envelope message, PublicKey publicKey)
            throws GeneralSecurityException {
        Signature check = Signature.getInstance("SHA256withRSA");
        check.initVerify(publicKey);
        check.update(signedBytes(message));
        return check.verify(message.signature());
    }

    // WRONG in production: public key supplied by the message.
    static boolean naiveVerify(Envelope message)
            throws GeneralSecurityException {
        return verifyWith(
                message, message.advertisedPublicKey());
    }

    // RIGHT in trust principle: only keys configured
    // for the expected issuer, plus context checks; never auto-trust
    // advertisedPublicKey. This is still only a demo.
    static boolean trustedVerify(
            Envelope message,
            String expectedIssuer,
            String expectedAudience,
            Instant now,
            List<PublicKey> authorizedKeys)
            throws GeneralSecurityException {

        if (!expectedIssuer.equals(message.issuer())
                || !expectedAudience.equals(message.audience())
                || !now.isBefore(message.expiresAt())) {
            return false;
        }

        for (PublicKey pinned : authorizedKeys) {
            if (verifyWith(message, pinned)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPair trustedOld = rsaKeyPair();
        KeyPair trustedNew = rsaKeyPair();
        KeyPair attacker = rsaKeyPair();

        String idp = "https://idp.example.org";
        String audience = "portal-sp";
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Instant future = Instant.parse("2027-01-01T00:00:00Z");
        Instant past = Instant.parse("2026-01-01T00:00:00Z");

        Envelope valid = issue(
                trustedOld, idp, audience, "alice", future);
        Envelope forged = issue(
                attacker, idp, audience, "admin", future);
        Envelope wrongAudience = issue(
                trustedOld, idp, "another-sp", "alice", future);
        Envelope expired = issue(
                trustedOld, idp, audience, "alice", past);

        Envelope tampered = new Envelope(
                valid.issuer(), valid.audience(), "admin",
                valid.expiresAt(), valid.advertisedPublicKey(),
                valid.signature());

        List<PublicKey> originalTrust =
                List.of(trustedOld.getPublic());

        System.out.println("Trusted message with embedded key: "
                + naiveVerify(valid));
        System.out.println("Attacker self-signed message accepted naively: "
                + naiveVerify(forged));
        System.out.println("Trusted message under pinned key: "
                + trustedVerify(
                    valid, idp, audience, now, originalTrust));
        System.out.println("Attacker under pinned key rejected: "
                + !trustedVerify(
                    forged, idp, audience, now, originalTrust));
        System.out.println("Wrong audience rejected: "
                + !trustedVerify(
                    wrongAudience, idp, audience, now, originalTrust));
        System.out.println("Expired signed message rejected: "
                + !trustedVerify(
                    expired, idp, audience, now, originalTrust));
        System.out.println("Tampered subject rejected: "
                + !trustedVerify(
                    tampered, idp, audience, now, originalTrust));

        Envelope rotated = issue(
                trustedNew, idp, audience, "alice", future);
        List<PublicKey> rolloverTrust = List.of(
                trustedOld.getPublic(), trustedNew.getPublic());

        System.out.println("New authorized key during rollover: "
                + trustedVerify(
                    rotated, idp, audience, now, rolloverTrust));
        System.out.println("Old key after retirement rejected: "
                + !trustedVerify(
                    valid, idp, audience, now,
                    List.of(trustedNew.getPublic())));
    }
}
```

Compile and run with JDK 17+:

```bash
javac UntrustedCertificateDemo.java
java UntrustedCertificateDemo
```

**Exact** stdout (RSA keypairs differ per run, yet boolean outcomes stay identical):

```text
Trusted message with embedded key: true
Attacker self-signed message accepted naively: true
Trusted message under pinned key: true
Attacker under pinned key rejected: true
Wrong audience rejected: true
Expired signed message rejected: true
Tampered subject rejected: true
New authorized key during rollover: true
Old key after retirement rejected: true
```

### 13.1. Line-by-line explanation

- `Trusted message with embedded key: true`: the signature produced by the old key matches the attached public key, yet **that is not a trust check**.
- `Attacker self-signed message accepted naively: true`: the exact same check lets the attacker pass. This directly proves mathematical signature success does not authenticate the issuer.
- `Trusted message under pinned key: true`: the key in trusted config matches the IdP signer.
- `Attacker under pinned key rejected: true`: the attacker's private key does not match the pinned public key, so verification fails.
- `Wrong audience rejected: true`: a message signed by the real IdP for another RP is still invalid at Portal.
- `Expired signed message rejected: true`: a valid signature does not override expiration.
- `Tampered subject rejected: true`: the signature over `alice` cannot remain valid when changed to `admin`.
- `New authorized key during rollover: true`: only once the new key is added to the trust set by an admin can the IdP sign with the new key.
- `Old key after retirement rejected: true`: after retiring the old key, old signatures are no longer accepted.

### 13.2. Additional limitations

- Attaching `PublicKey` only simulates a `KeyInfo` certificate: real X.509 has chains, extensions, validity, revocation, and identity policies.
- `trustedVerify` performs simple issuer/audience/expiry checks without SAML `InResponseTo`, `Recipient`, `NotBefore`, SubjectConfirmation, replay stores, or browser flows.
- No JWT JOSE header/alg/kid, XMLDSig canonicalization/reference URI, metadata onboarding, or issuer token-type isolation.
- `authorizedKeys` is a pinned test set; production must load from **server-side trusted storage** namespaced per issuer/tenant.
- `SHA256withRSA` is a simple JCA algorithm, not representative of every XML Signature/JWS profile.
- No PKIX chain validation or remote certificate fetching.
- No private keys are exported or persisted long-term in the demo; production needs key lifecycle management, KMS/HSM/secret stores.
- Key rotation must be approved and verified out-of-band; never construct `authorizedKeys` from `advertisedPublicKey`.

## 14. Why Is a “Valid Certificate” Still Insufficient?

### 14.1. Self-signed certificate: vouching for itself

An attacker can generate an unexpired cert with CN/Organization matching the IdP and self-sign it. `checkValidity()` and self-signature verification may pass, yet there is no **approved trust anchor**. If the IdP genuinely uses a self-signed cert, the SP accepts it only when the **cert/key was pinned through onboarding**.

### 14.2. A public CA certificate does not prove SAML signing authority

Someone can buy/obtain a TLS cert for a domain they own; that cert's public CA chain may be valid. However, it is not an SP-approved signing certificate for `https://idp.example.org/saml`. Authentication requires **issuer-key binding**, not “signed by any CA”.

### 14.3. X.509 Key Usage and Extended Key Usage

Depending on the profile, inspect certificate `KeyUsage`/`ExtendedKeyUsage`, key algorithms, validity, and purpose suitability (TLS server, TLS client, SAML signing, encryption). SAML federations may use self-signed keys where PKIX-style EKUs are not required, so choose checks matching the **accepted contract**—never skip all checks or apply an out-of-context public-webPKI policy.

### 14.4. Valid signature yet still wrong claims authorization

An IdP might emit `role=ADMIN` for a user while RP policy forbids the IdP from granting admin rights unilaterally. After trusting the signer/issuer, map claims to **local roles** per allowlist, tenant, and resource scope. A signature does not turn every claim value into an access policy.

## 15. Attack Tree: Indicators and Blocking Points

| Attack | How the attacker exploits it | Defense |
| --- | --- | --- |
| **Embedded certificate substitution** | Self-signs Assertion, inserts own X509Certificate | Verify with IdP pinned verification credentials |
| **JWKS header substitution** | JWS contains attacker's `jwk` | Never auto-trust header JWK |
| **SSRF jku/x5u** | Header points to metadata/internal URL | Only trusted issuer JWKS URI, egress restrictions |
| **Algorithm confusion** | `alg=none` or RS256→HS256 | Server-configured algorithm allowlist/key-type binding |
| **Issuer/key confusion** | Signed by IdP B while claiming IdP A | Scope trust keys to trusted issuer/tenant |
| **Cross-audience token** | Real IdP token meant for another RP | Verify `aud`, `azp`/client binding per profile |
| **XML Signature Wrapping** | Signature on benign Assertion while app reads forged node | Bind consumed assertion to verified signed element/ID |
| **Untrusted metadata adoption** | Self-submitted metadata carries attacker key | Trust onboarding, signed metadata verification when required |
| **Key rollover hijack** | Inserts new cert into inbound KeyInfo | Approved metadata/trust-store changes only |
| **Expired/revoked cert bypass** | Sees cert invalid, falls back to embedded key | Fail closed, incident/rotation procedure |
| **mTLS header spoofing** | Client sends `X-Client-Cert` itself | Gateway-verified mTLS handshake, strip incoming headers |
| **External XML Reference** | URI/KeyInfo RetrievalMethod points to internal service | Disable external resolver, strict URI/transforms |
| **Replay valid signed assertion** | Resends old assertion while key is still valid | InResponseTo/Recipient/time/replay cache checks |
| **Weak/legacy signature** | RSA-SHA1/MD5 or insecure key size | Approved algorithms & minimum key strength |
| **Tenant mix-up** | B uses A's key due to global trust set | Namespace per tenant/entityID/issuer |
| **Unknown kid auto-fetch** | “kid not found” → fetch key from message URL | Reject until trusted JWKS refresh is approved |
| **Truststore poisoning** | Admin endpoint accepts cert file from user | Authenticated config management, review/audit |

## 16. Secure SAML Response Processing Workflow

### 16.1. Processing sequence

```text
1. Browser POST SAMLResponse (tainted/untrusted).
2. Spring resolves RelyingPartyRegistration:
   request-associated state / approved registration / safe issuer candidate.
3. Pull trusted verifying credentials for expected IdP.
4. XML parser hardened: DTD/XXE/size/IDs/transforms constrained.
5. Verify signature over proper Response/Assertion element.
6. Confirm verifier key belongs to expected IdP.
7. Validate Issuer, Destination, InResponseTo,
   AudienceRestriction, Recipient, SubjectConfirmationData,
   clock validity, replay, status.
8. Read NameID/attributes from precisely verified Assertion.
9. Map identity to permitted local principal and authorities.
10. Create SecurityContext/session and audit success without raw XML.
```

**Never skip step 6:** “Signature.verify() true” only means anything when verified against an authorized key. **Never skip step 8:** if the parser reads an AttributeStatement outside the signed subtree, XSW can occur.

### 16.2. Checks requiring care

- **Issuer:** matches expected entityID, not just same hostname or organization name.
- **Audience:** assertion is intended for the current RP entityID.
- **Recipient:** bearer subject confirmation specifies a valid ACS.
- **Destination:** Response arrived at the exact endpoint, handling trusted proxy forwarded headers properly.
- **InResponseTo:** matches pending AuthnRequest, or an approved IdP-initiated profile; never drop checks casually.
- **Lifetime:** Conditions and SubjectConfirmationData NotOnOrAfter/NotBefore within reasonable clock skew.
- **Replay:** message/assertion IDs must not be accepted multiple times.
- **Signature coverage:** Response or Assertion signatures must satisfy the profile; exact verification criteria depend on framework/version/IdP contract.
- **Decryption:** SP decryption private key differs from IdP trusted signing key.
- **Multi-tenant:** only one verified registration context is used for both auth and authorization.

### 16.3. Do not write a custom DOM parser as a login path

A shortcut like:

```java
// ANTI-PATTERN — ILLUSTRATIVE CODE FRAGMENT.
// Node node = doc.getElementsByTagName("NameID").item(0);
// String principal = node.getTextContent();
// if (isSignatureValidSomewhere(doc)) authenticate(principal);
```

easily confuses a verified node with an unverified node. Use a maintained Spring Security/OpenSAML provider, intentional customizations, XSW tests, and schema validation. Never trust a signed metadata key based on an uploaded filename.

## 17. JWT Verification: Token-Type-Specific Validation Profiles

### 17.1. Access token is not an ID token

An API Resource Server typically must verify:

- Trusted issuer and JWKS source per configuration.
- Signature with an authorized key/allowed alg.
- Exact `iss`, `aud` containing the API resource identifier.
- `exp`/`nbf`/`iat` when required by profile.
- Scopes/roles per issuer and audience, avoiding self-declared client `ROLE_ADMIN`.
- `typ` or token classification when token types could be confused.
- Replay/`jti`/revocation per application requirements.

An OIDC client handling an ID Token also needs `client_id` audience, `nonce` when present, `azp` as applicable, and OIDC Core checks. Never use a Resource Server access-token validator as a general ID Token verifier.

### 17.2. Multi-issuer JWT strategy

A Resource Server can accept multiple approved issuers. Yet **never do**:

```text
unverified token.iss -> network discovery on arbitrary URL
-> auto-add all keys -> verify -> trust
```

Instead:

```text
trustedIssuers:
  https://idp-a.example.org -> JWKS URL A, allowed audience A, key policies
  https://idp-b.example.org -> JWKS URL B, allowed audience B, key policies

unverified iss only selects existing entry (or REJECT)
decoder bound to that entry verifies token
audience, type, tenant, expiry validated separately
```

Spring Security offers issuer-based resolvers like `JwtIssuerAuthenticationManagerResolver` with a trusted issuer allowlist/manager repository depending on version. Populate the resolver only with onboarded issuers; a callback must never register a new issuer because a token self-declares it.

### 17.3. Refreshing JWKS on a new kid

A `kid` missing from the cached trusted JWKS may reflect a **legitimate IdP key rotation**, yet does not permit the token to pull a new `jku`. Safe process:

1. Refresh the **trusted issuer's configured JWKS endpoint** per cache/refresh policy.
2. Enforce rate limits, timeouts, response size caps, and HTTPS/redirect/egress controls.
3. Verify key parameters and allowed algorithms.
4. Retain old/new authorized issuer keys during a bounded rollover window.
5. Reject if `kid` still does not exist or signature fails.
6. Audit key lifecycle changes; alert on unexpected key churn.

If a JWKS endpoint is compromised, run incident/issuer key revocation; HTTPS having succeeded in the past does not mean every new key should be trusted without oversight.

## 18. Checklist for Establishing Trust Sources Without Letting Attackers Define Them

### 18.1. Identity metadata/issuer onboarding

- [ ] Every IdP/OP has an owner, issuer/entityID, and trusted metadata/JWKS source.
- [ ] Metadata/JWKS URLs come from admin configuration, never SAML Response or JWT `jku`.
- [ ] HTTPS TLS with trusted hosts/truststore; signed metadata has an independent trust anchor when required.
- [ ] X.509 certificate/key uses are clearly distinguished: signing vs encryption vs TLS.
- [ ] Multiple tenants do not share a global “any cert” trust set.
- [ ] Self-signed certificates are accepted only when **pinned via a trusted channel**.
- [ ] PKIX chain validation, when applicable, uses trusted roots and identity binding/KU/EKU/revocation policies.
- [ ] Key changes are versioned, approved, logged, and have overlap/rollback plans.

### 18.2. Signature processing

- [ ] SAML XML uses a hardened parser with DTD/XXE/size/transforms/unique ID checks.
- [ ] Verify the exact signed element with trusted IdP credentials, never taking untrusted keys from KeyInfo.
- [ ] Never use global DOM NameID/attributes outside the verified Assertion.
- [ ] Validate Issuer, audience, ACS recipient/destination, time, InResponseTo, and replay.
- [ ] JWT accepted algorithms are server-configured; no `alg=none` or algorithm confusion.
- [ ] JWT keys are scoped per issuer; `kid` only looks up, `jku`/`x5u` never auto-fetch.
- [ ] Token type/issuer/audience/tenant/expiry validation is complete.
- [ ] mTLS identity comes solely from the TLS handshake/trusted gateway, never self-trusted `X-Client-Cert`.
- [ ] Failed verification **rejects**; never fall back to “unsigned” or embedded certs.

### 18.3. Operations

- [ ] Logs contain no full SAMLResponse/JWT/KeyInfo, session tokens, or private keys.
- [ ] Alerts fire on invalid signatures, unknown trusted keys, unexpected kids, metadata updates, and XSW attempts.
- [ ] Test fixtures cover trusted IdP, attacker-generated self-signed key, and retired key.
- [ ] Metadata/JWKS caches are monitored, with timeouts/rate limits and rollover processes.
- [ ] Compromised signing keys are removed per incident response, without extending grace periods.
- [ ] Spring Security/OpenSAML/Nimbus configs are kept updated and regression tests run every release.

## 19. Negative Test Matrix

| Test case | Required behavior |
| --- | --- |
| Attacker self-signs Assertion and embeds X509Certificate in KeyInfo | **REJECT**, even if signature verifies with embedded key |
| Message signed with trusted IdP key but different `Issuer` | **REJECT** |
| IdP B signs message claiming issuer IdP A | **REJECT**, never trust global set |
| Message `aud` meant for another app | **REJECT** |
| Expired Assertion with valid signature | **REJECT** |
| Duplicate Assertion ID/replay of valid signed response | **REJECT** |
| XML has two Assertions, one signed, app reads the other | **REJECT** and test for XSW |
| XML Reference URI points to untrusted remote resource | **REJECT** or deny remote resolution |
| Self-signed X509Certificate with Subject CN “Trusted IdP” | **REJECT** if not pinned |
| Valid cert chain to public CA yet unauthorized by IdP A | **REJECT** |
| Unsigned metadata where attacker swaps KeyDescriptor | Do not auto-adopt; **REJECT** when policy requires signed metadata |
| Metadata signed by key embedded inside the untrusted metadata itself | **REJECT** self-validating bootstrap |
| Legitimate IdP rotates signing key via verified channel | **ACCEPT** exact old/new set during rollover |
| New key present only in inbound KeyInfo, unapproved | **REJECT** |
| Retired key signs a new Assertion | **REJECT** |
| Compromised old key still in truststore | Security incident; remove, revoke sessions/replay as needed |
| JWT header carries attacker `jwk`, payload admin | **REJECT** via issuer-configured JWKS |
| JWT header `jku` points to localhost/cloud metadata endpoint | Do not fetch, **REJECT** |
| JWT `alg=none` | **REJECT** |
| JWT RS256↔HS256 confusion | **REJECT** |
| JWT `kid` attempts traversal/SQL injection | Reject/sanitize; no arbitrary file/key lookup |
| JWT signed by key B while `iss=A` | **REJECT** |
| Real JWT signature with wrong audience | **REJECT** |
| ID Token used as API access token | **REJECT** per token profile |
| Proxy forwards browser-supplied `X-Client-Cert` | **REJECT** without a verified gateway |
| Valid mTLS chain with unexpected client identity | **REJECT** |
| Only `checkValidity()` on untrusted cert then allowing login | Security QA **FAIL** |
| SAML encryption certificate confused with signer key | Security QA **FAIL** for wrong role |
| Spring tests check signature only without checking auth/session identity | QA incomplete; add end-to-end checks |
| Java 17 demo output differs from section 13 | Content QA FAIL |

### 19.1. E2E tests for Spring Security SAML2

1. Configure trusted IdP A certificate in `RelyingPartyRegistration` via admin channel.
2. Log in via A and verify signed Response/Assertion, context + local session.
3. In the lab, generate an attacker keypair/cert and sign a forged Assertion with A's `Issuer`/ACS/audience.
4. Embed the attacker cert in `KeyInfo`; **the SP must reject**, creating no `Authentication`.
5. Test a signature-wrapping fixture with a benign signed node and malicious unsigned node; disallow admin login.
6. Test signed wrong audience/expired/replay/InResponseTo mismatch and IdP B issuer/key swap.
7. Rotate the IdP key via approved metadata, test old/new overlap, then retire old.
8. Verify logs never print raw `SAMLResponse` or private certificates.
9. Repeat across multiple registrations/tenants and pods to catch global trust mix-ups.

### 19.2. E2E tests for JWT Resource Server

1. Configure issuer and trusted JWKS URL server-side; set API audience per profile.
2. Obtain a real access token from the issuer, verify it, and grant minimal scopes.
3. Craft a test JWT signed by an attacker key with attacker `jwk/x5c` headers; reject.
4. Add a `jku` URL pointing to a test server/loopback; verify the Resource Server **never fetches** the header-specified URL.
5. Test unknown `kid`: refresh only the trusted JWKS; if key absent, reject.
6. Test issuer B token substituted into API A, wrong audience, expired, `alg=none`.
7. Test authorized key rollover from trusted JWKS with cache timing/old+new.
8. Observe unauthenticated 401 and an empty SecurityContext principal.
9. Ensure auth errors never expose raw JWT/header/PII in logs/responses.

## 20. Troubleshooting and Operations

| Symptom | What could it be? | Check |
| --- | --- | --- |
| SAML invalid signature after IdP cert rollover | SP has not received trusted new cert | Metadata trust update, trusted cert versions |
| “Signature valid” yet app logs in wrong user | XSW or reading unsigned claims | Signed element binding, XML IDs, OpenSAML pipeline |
| SAML carries KeyInfo cert differing from trusted metadata | Expected during attacker forgery or uncoordinated IdP rotation | **Never auto-trust**; verify admin trust channel |
| Metadata validly signed yet attacker-supplied | Verifier used cert embedded in metadata | Independent metadata verification trust anchor |
| SAML wrong issuer/audience after multi-tenant setup | RP registration mix-up | Namespace keys per IdP/RP/tenant |
| JWT unknown kid after legitimate rotation | Stale trusted JWKS cache | Refresh **configured JWKS**, not header jku |
| Self-signed JWT with x5c passes custom code | Decoder uses untrusted key in token | Replace custom resolver, use trusted JWKS |
| JWT with valid signature returns 401 | Wrong aud/iss/exp/type or authorization | Check validators; never loosen trust |
| JWT jku triggers internal network requests | SSRF via resolver | Disable header-controlled URL fetch |
| mTLS auth accepts spoofed header | Proxy fails to strip incoming headers | TLS gateway identity and trusted headers config |
| Signing cert expired | Pinning/PKIX policy and rotation failure | Approved replacement; never bypass expiry casually |
| New SAML key in metadata yet old runtime behavior | Cache/refresh/rollout | Observe metadata cache policy, atomic config update |
| Valid self-signed SAML cert rejected | Public-CA PKIX mistakenly applied to pinned SAML trust | Configure exact federation trust model |
| Any browser-CA cert accepted | Missing IdP-key binding | Pin/metadata verify expected IdP |
| SAML encrypted assertion fails to decrypt | Wrong SP private decryption credential | Decryption key, not IdP verification key |
| SAML signature valid yet wrong role | Wrong business authorization mapping | Local policy/tenant, never trust raw role |

### 20.1. Log enough to investigate without exposing data

```json
{
  "event": "federation_signature_rejected",
  "protocol": "saml2",
  "registration": "corporate",
  "reason": "key_not_in_approved_trust_set",
  "candidate_key_id": "opaque-approved-or-untrusted-hint",
  "message_type": "SAMLResponse",
  "result": "rejected",
  "correlation_id": "request-internal-id"
}
```

This is an **illustrative** event; never put raw certs/public keys/trust anchors, message XML, NameID, JWTs, session IDs, or passwords in metric labels/log entries. If key fingerprints must be logged for operations, use only an **approved, non-sensitive representation** and limit correlation/PII per policy; never print private keys.

### 20.2. Responding to suspicious key substitution

If many messages suddenly carry unrecognized certificates/keys:

- Stay **fail closed**; never auto-update the truststore.
- Confirm with IdP operations whether a rollover was announced on the registered channel.
- Cross-check trusted metadata/JWKS change events, network/egress logs, and tenant routing.
- Watch login failures, unexpected `jku/x5u` and SSRF attempts, and XSW parsing exceptions.
- If a real IdP signing key was compromised: revoke trust, revoke affected sessions/tokens as required, audit, and reissue via trusted channel.
- Distinguish availability incidents from attacker forgeries; never “quick fix” by trusting all embedded certificates.

## 21. Review Questions

**1. Why is verifying a signature with an attached public key insufficient to authenticate an IdP?**  
Because an attacker can also generate a private/public keypair, sign a forged message, and attach their own public key. The signature will match that key.

**2. Where should IdP SAML signing keys come from?**  
From trusted RelyingPartyRegistration/metadata onboarded and verified via an independent channel—never self-determined by inbound `KeyInfo`.

**3. Does an unexpired X.509 certificate mean the organization trusts it?**  
No. `checkValidity` checks only dates; an appropriate trust anchor/issuer-role binding is required.

**4. Are self-signed SAML certificates always forbidden?**  
No. They can be valid when pinned/trusted via verified IdP metadata/admin channels. The issue is that they **are not trustworthy merely by appearing in a message**.

**5. Does a public CA cert authorize signing Assertions for any IdP?**  
No. Keys/certs must bind to the exact IdP entityID and sign messages in the right role/protocol.

**6. What is KeyInfo good for when not trusted on its own?**  
It can indicate a candidate key name/cert to help select among registered trusted verification credentials, or it can be ignored.

**7. Can XSW happen even when the signature uses a trusted key?**  
Yes. If the app reads attributes/NameID from a **different XML node** than the signed/verified assertion.

**8. Why not use a JWT's `jku` to download JWKS?**  
An attacker can point to their own server or an internal metadata endpoint, causing key substitution/SSRF.

**9. Is a JWT's `kid` trustworthy?**  
It is an untrusted selector; look it up only inside the trusted issuer keyset, never creating new keys/issuers.

**10. Is a JWT validly signed by IdP B yet claiming `iss=A` acceptable?**  
No. Keys must belong to the expected issuer, and token audience/type must match.

**11. Does adding a new certificate to KeyInfo mean rotation succeeded?**  
No. Only keys placed into trust config by admins/verified metadata are permitted to verify.

**12. Can mTLS certificates in HTTP headers be trusted?**  
Only when forwarded from a gateway that authenticated the TLS client, stripped incoming spoofed headers, and uses a trusted backend link; never trust browser headers.

**13. What about a signed SAML Response with the wrong audience?**  
Reject. A valid signature does not mean the response was meant for this SP.

**14. Should signature/PKIX validation be disabled when a certificate expires to avoid an outage?**  
No. Investigate the trust model, coordinate replacement over an approved channel, and handle the incident rather than failing open.

**15. If SAML metadata contains KeyDescriptor, can keys be auto-imported from any URL?**  
No. The metadata source must be trusted; metadata signatures, when required, must verify against an independent anchor.

**16. What differs between the IdP signer key and the SP decryption key?**  
The IdP signing public key verifies issuer SAML messages; the SP private decryption key decrypts encrypted assertions. Never swap roles.

**17. Why does a Spring Security OIDC Resource Server still need issuer and audience validators?**  
Because a signature only proves an authorized signer; a token may belong to another app, be expired, or have a different token type.

**18. When receiving an unknown `kid`, what should you do?**  
Refresh the issuer-specific configured trusted JWKS per policy; if no authorized key is found or signature fails, reject without fetching from token-controlled URLs.

## 22. Standards and Official Sources

- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): verify keys from local trusted sources, ignore untrusted KeyInfo, prevent XML Signature Wrapping, protocol validation.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, `assertingPartyMetadata.verificationX509Credentials`, SAML Response/Assertion signature validators.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `OpenSaml5AssertingPartyMetadataRepository.verificationCredentials`, warning that metadata signatures are not verified without verification credentials.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): `SignedInfo`, `Reference`, `SignatureValue`, `KeyInfo`, and why key discovery does not replace trust policy.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer-key binding, audience, `jku`/`x5u` SSRF, token confusion.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JOSE header params `alg`, `kid`, `jwk`, `x5c`, `jku`, `x5u`.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): trusted JWK Set representation, key parameters.
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer/metadata location and trust binding.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, `jwk-set-uri`, `JwtDecoders.fromIssuerLocation`, algorithms, and claim validators.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federation trust agreements, assertions, keys, and authentication assurance.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hardened XML parsing.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): URL-fetch allowlists and blocking internal network access.
- [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS trust anchors and mTLS deployment considerations.

**Remember:** `X509Certificate`, `KeyInfo`, `jwk`, or `x5c` inside an **unverified message** are merely untrusted data, never trust anchors automatically accepted by an RP/Resource Server. A signature matching an **attacker-supplied key** can still be mathematically valid. You must obtain authorized verification keys from **trusted issuer registration/verified metadata/JWKS/configuration**, verify the exact signed bytes/element with that key, and then check **issuer–audience–recipient–time–replay–tenant–token type–authorization**. For rotation, add keys only through a verified change process; if verification fails, **reject** without falling back to embedded certificates.