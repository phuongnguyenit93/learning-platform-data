# Certificate expiration, revocation policies, and limits of default checks

> **Module:** Spring Security – federation · **Parent topic:** Keys and certificates. This lesson explains how to evaluate expiration and revocation status of X.509 certificates when deploying SAML 2.0 Single Sign-On with Spring Security, the boundary between metadata/explicit-key trust and PKIX/CRL/OCSP, as well as what **must not be assumed** about default verification steps.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **X.509 certificates for SAML signing**, **SAML metadata signing certificates**, **TLS/HTTPS certificates**, and **SP signing/decryption keys**.
2. Explain why **digital signature verification**, **key trust**, **X.509 validity (`notBefore`/`notAfter`)**, **certificate revocation (CRL/OCSP)**, **metadata expiry**, and **Assertion expiry** are **distinct** checks.
3. Understand the SAML metadata-based / explicit-key trust model, where a key's presence in accepted metadata can establish trust without necessarily performing PKIX chain validation.
4. Know why you must not claim broadly that Spring Security checks SAML certificate expiration/revocation by default; actual behavior must be verified per version, configuration, and trust engine.
5. Design certificate expiry/revocation policies and rollover processes covering phases A → A+B → B, trusted metadata sources, refresh limits, and compromise actions.
6. Read `KeyDescriptor`, `X509Certificate`, `validUntil`, `cacheDuration`, and `Conditions.NotOnOrAfter` fields without substituting one timestamp for another.
7. Run a Java 17 utility that reads a real certificate, prints validity/fingerprint, and **explicitly states which checks it does not perform**.
8. Integrate certificate health alerting with Spring Security SAML2 at an observability level while keeping **login acceptance policy** separate from monitoring.
9. Create a test suite proving the system behaves properly when certs near expiry, expire, are revoked, rotate keys, metadata grows stale, or an IdP is compromised.

## 2. Scenario: certificate is "expired" yet SSO login still succeeds

Suppose the Orders Portal app is a Service Provider (SP). A partner IdP emits SAML Responses signed with its private key. The SP stores the IdP's public certificate to verify signatures.

At check time:

~~~text
IdP Signing Certificate A
  Subject:       CN=Partner A SAML Signing
  notBefore:     2024-01-01T00:00:00Z
  notAfter:      2026-06-01T00:00:00Z
  Public key:    key-A

IdP Response at: 2026-11-07T04:00:00Z
Signature with private key-A: mathematically valid
SP verification key: key-A is still in trusted registration
~~~

If you only call a **signature verification** function with key-A, the signature **can still be mathematically valid** even after the X.509 `notAfter` timestamp has passed. Because certificate expiration is a **trust/policy rule**, not a property that stops public-key signature math from working.

However, that **does not mean** production config should continue trusting A indefinitely. Allowing or rejecting must follow the **chosen trust model**, risk policy, approved metadata/key sources, and compromise status. In a PKIX configuration that enforces validity, the exact same certificate may be rejected.

**The right question is not** "can an expired certificate log in?" in absolute terms. **The right question is**: "Which keys does our SP accept as trust anchors at what time, via which source/method, and which expiry and revocation checks have we configured and tested?"

## 3. Distinguishing five types of checks and lifetimes

| Check | Question | What is checked | Do they substitute for each other? |
| --- | --- | --- | --- |
| **XML Signature verification** | Are signed bytes/XML objects intact and mathematically valid against the public key? | Signature value, digest/reference/transforms on Response/Assertion/metadata. | Does not prove the cert is unexpired or unrevoked. |
| **Key trust** | Does that public key/certificate belong to an IdP trusted by the SP? | Pinned verification credentials, accepted SAML metadata, or PKIX path. | Never rely solely on a cert carried inside request XML. |
| **X.509 validity** | Is the certificate within `notBefore`–`notAfter`? | X.509 certificate validity fields. | Does not replace SAML signature or metadata verification. |
| **Revocation check** | Has the certificate been revoked by the CA? | CRL, OCSP, or corresponding revocation policy. | Does not happen automatically just by checking `notAfter`. |
| **SAML protocol/metadata validity** | Are the Assertion/confirmation and metadata still valid? | `Conditions.NotOnOrAfter`, `SubjectConfirmationData.NotOnOrAfter`, metadata `validUntil`/`cacheDuration`. | Does not depend solely on cert `notAfter`. |

Additionally, **SP session/cookie timeout** is a separate policy. An Assertion accepted at login creates an SP session; revoking a local user's permissions must be handled by app/session policy, without waiting for a certificate to expire.

### 3.1. Illustrating four distinct clocks

~~~text
IdP X.509 Certificate:
  notBefore ---------------------------- notAfter

IdP Metadata:
  retrievedAt --- cacheDuration --- nextRefresh ... validUntil

SAML Assertion:
  Conditions.NotBefore ---- Conditions.NotOnOrAfter

Bearer SubjectConfirmation:
  issuedAt -------- SubjectConfirmationData.NotOnOrAfter

SP Session:
  loginAt ------------------------------ sessionExpiry
~~~

These intervals need not align. An `Assertion.NotOnOrAfter` only 3 minutes from now does not mean the IdP certificate expires in 3 minutes. Conversely, a cert's `notAfter` does not dictate how long a `SAMLResponse` remains valid.

## 4. Which certificates exist in a SAML2 integration?

### 4.1. IdP certificate used to sign Response/Assertion

- **IdP** holds the private key and issues signed Responses/Assertions.
- **SP** holds one or more IdP certificates/public keys trusted via metadata or manual config.
- In Spring Boot, the branch is typically `spring.security.saml2.relyingparty.registration.<id>.assertingparty.verification.credentials`.
- The certificate binds **a public key to a trust relationship**; never assume it is a TLS server certificate with a public CA chain.
- If the XML Response includes `<ds:KeyInfo>` carrying some certificate, **that is not automatically a trust anchor**. The SP must match against trusted IdP config.

### 4.2. SP certificate used to sign AuthnRequest/SLO

- **SP** holds the private key; the IdP uses the registered SP public key/certificate to verify messages.
- Boot config typically sits at `registration.<id>.signing.credentials` with `private-key-location` and `certificate-location`.
- Partner IdPs may require an unexpired cert under their own policy; "the SP can still sign mathematically" does not guarantee IdP acceptance.
- An **SP signing** cert error can cause the IdP to reject **AuthnRequest**, completely distinct from the SP verifying **SAMLResponse**.

### 4.3. SP certificate used to decrypt Assertions

- The IdP encrypts assertions/identifiers for the SP's public key.
- The SP holds the decryption private key under `registration.<id>.decryption.credentials`.
- **Successful decryption does not replace digital signatures**, and an expired cert does not itself define success/failure of the decryption math.
- During rotation, synchronize the public cert the IdP encrypts with and the SP private key retained to decrypt in-flight responses.

### 4.4. Metadata signing certificate

- Metadata is signed with a trusted key per community or partner agreement.
- **Metadata signing trust** may differ from **Assertion/Response signing trust**.
- An unverified metadata file must never use its own internal `KeyDescriptor` to **self-approve a new certificate in that very file**.
- When implementing metadata signature verification, the trust anchor must be established via an independent/approved channel.

### 4.5. HTTPS/TLS certificates

- Used to authenticate HTTPS endpoints when the SP fetches metadata or browsers access SP/IdP.
- May use Java PKIX chains/trust stores, checking hostnames/validity/revocation per JSSE/provider/config.
- **A TLS server certificate is not inherently a SAML signing certificate**. They can differ in key pairs, lifetimes, rotation schedules, and owning teams.
- Never replace an IdP verification cert with a TLS cert just because the metadata URL hostname resembles the IdP's name.

## 5. Two common trust models and the meaning of expiry

### 5.1. Explicit-key / metadata-based trust

In many SAML2 federations, the SP treats signing keys inside **metadata accepted from a trusted source** as the keys authorized to verify SAML messages. The goal is to verify a specific public key published by the IdP, without necessarily building a PKIX chain up to a public CA.

~~~text
Verified trusted IdP metadata:
   EntityDescriptor entityID = IdP A
       IDPSSODescriptor
          KeyDescriptor use="signing"
              ds:X509Certificate contains public key A
          KeyDescriptor use="signing"
              ds:X509Certificate contains public key B
                    |
                    v
           SP trusted verification keys [A, B]
                    |
              SAML Response signature
                    |
              Verify with matching key
~~~

In this model, the OASIS metadata profile focuses on **key comparison** and **metadata** validity/origin. Thus you cannot assume `certificate.checkValidity()`, CRL, or OCSP are always invoked on signing certs. An X.509 certificate can serve as a **public key container**, distinct from a PKIX leaf certificate in TLS.

**Do not equate** "expiry is not enforced by default" with "expiry does not matter": an organization can still mandate a policy to warn or block expired certs, especially when partners/compliance require it. Verify whether that policy is enforced **in the actual authentication path** or merely monitored.

### 5.2. PKIX trust / certificate path validation

With PKIX, the SP validates a certificate path up to a pre-established trust anchor, checking certificate signatures, validity windows, key usage/policies, and revocation when configured:

~~~text
Trusted Root CA
    |
Intermediate CA (if any)
    |
IdP Leaf Signing Certificate
    |
CertPath building/validation
    + possible CRL/OCSP
    |
SAML XML Signature verification
~~~

PKIX is **one selectable trust model**, not the universal default for every SAML deployment. Using it requires exact trust anchors, path validation rules, revocation support, and a policy for UNKNOWN status.

Even within PKIX, never treat calling `CertificateFactory` or `X509Certificate.checkValidity()` alone as "full chain and OCSP checked". You must use `CertPathValidator` or a suitable trust engine with explicit **PKIXParameters**, trust anchors, and revocation settings; trust anchors in PKIX are normally handled differently from leaf certs.

### 5.3. Direct comparison

| Aspect | Explicit-key/metadata trust | PKIX chain trust |
| --- | --- | --- |
| Trust anchor | Verified metadata / pinned IdP key. | Accepted root/intermediate CA and cert path. |
| Leaf X.509 cert expiry | May **not** decide runtime acceptance. | Typically part of point-in-time path validation. |
| CRL/OCSP | Not automatic; governed by metadata/key removal or custom policy. | Can be checked when enabled and reachable. |
| Revocation on key compromise | Remove key from metadata/trust registry, refresh all consumers, terminate sessions if needed. | Revoke via CA/CRL/OCSP **and** update trust/config per procedure. |
| Rollover | Publish A+B in metadata, then drop A when complete. | Update chain/cert and coordinate trust/validity. |
| Risk if confused | Assuming CA revocation automatically blocks a still-pinned key. | Assuming a pinned cert suffices even when PKIX validation is required. |

Individual SP/IdP products can apply extra policies; thus **testing** proves actual deployment runtime behavior.

## 6. Metadata: where many SAML2 deployments "revoke keys"

### 6.1. Example of two signing keys during rollover

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.partner-a.example/saml"
    validUntil="2030-05-01T12:00:00Z"
    cacheDuration="PT30M">
    <md:IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo>
                <ds:X509Data>
                    <ds:X509Certificate>BASE64_DER_CERT_A</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo>
                <ds:X509Data>
                    <ds:X509Certificate>BASE64_DER_CERT_B</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>
        <md:SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://idp.partner-a.example/sso"/>
    </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

`BASE64_DER_CERT_A` and `BASE64_DER_CERT_B` are **structural placeholders**; the XML above lacks valid certs and a metadata signature. **Do not deploy** this example as real IdP metadata.

When loading real metadata, you must:

1. Accept metadata only from **registered sources and issuers**, never from a browser-supplied URL.
2. Verify metadata signatures if required by the trust contract, using an independent trust anchor.
3. Validate `entityID`, `IDPSSODescriptor` role, endpoints, KeyDescriptor usage, certificates, and related conditions.
4. Enforce `validUntil` and `cacheDuration` policies; apply a maximum operational age if absent.
5. Only then publish a new `RelyingPartyRegistration`/credential set.
6. If fetch/parsing/validation fails, retain last-known-good **only within an allowed grace window**, with alerts. Never keep stale data forever.

### 6.2. Distinguishing `validUntil` and `cacheDuration`

- **`validUntil`**: timestamp until which the metadata is considered valid per profile/policy. Do not confuse this with each cert's `notAfter` inside the document.
- **`cacheDuration`**: hint for how long to cache before refreshing. It does not automatically create caches/schedulers in every app.
- **`notAfter`**: belongs to each X.509 certificate, independent of both metadata fields.
- **`Assertion.Conditions.NotOnOrAfter`**: validity limit of the SAML Assertion for authentication.
- **`SubjectConfirmationData.NotOnOrAfter`**: validity limit for presenting a bearer assertion to the SP, usually short.
- **Session timeout**: cookie/session lifetime decided by the SP.

Fresh metadata with a future `validUntil` does not prove internal certs have not passed `notAfter`. Conversely, an unexpired cert `notAfter` does not permit the SP to keep using replaced/compromised metadata.

### 6.3. Standard rollover: A → A+B → B

~~~text
T0:  Metadata has key A         IdP signs with A
T1:  Metadata has key A + B     SP refreshes, accepts both per policy
T2:  IdP switches signing to B  New responses verify with B
T3:  Overlap / in-flight ends   IdP removes A from metadata
T4:  SP refreshes completely    SP stops trusting A per policy
~~~

Crucial: **publish public key B before the IdP signs with private key B** so SPs have time to refresh. Once confident no in-flight responses use A, remove A per approved procedure. Never extend overlap indefinitely.

If A is **compromised**, this is **no longer** a normal rotation: prioritize removing A immediately from trusted registries/verified metadata, notify partners, and audit sessions created with A. Never keep A merely to avoid login disruption.

### 6.4. OASIS Metadata Interoperability Profile and revocation

The OASIS Metadata Interoperability Profile states that **compromised keys must be removed from metadata**; metadata publishers must not rely on consumers querying CRL/OCSP to detect them. This is especially important in explicit-key trust federations: a key still present in metadata or stale repositories **may continue to be trusted** even after a CA places the certificate on a CRL.

Therefore revocation workflows must include **distributing new metadata/trusted key sets**, refreshing, and verifying that **every SP instance stops trusting the old key**. Define maximum stale windows, health metrics, and emergency channels if a metadata feed fails.

## 7. CRL, OCSP, and the meaning of "revoked"

### 7.1. Certificate Revocation List (CRL)

A CRL is a CA-signed list of revoked certificates carrying `thisUpdate`/`nextUpdate` timestamps and typically accessible via `CRL Distribution Points`. In PKIX with revocation checking, the client must know how to fetch/cache/verify the list from the right CA.

Limitations:

- Not all SAML signing certs are issued by public CAs; many are self-signed or exchanged directly.
- Not every cert contains CRL Distribution Points.
- Absence of a certificate from an expired or unverifiable CRL **does not prove good status**.
- CRL revocation only works if the runtime actually checks it along the proper trust path.
- Federations using explicit-key pinning may not consult CRLs for trust decisions; you must remove the key from metadata/registration.

### 7.2. Online Certificate Status Protocol (OCSP)

OCSP queries a responder for a certificate's status and receives a signed reply. Typical statuses are **good**, **revoked**, and **unknown**; "good" in the protocol does not guarantee a private key wasn't leaked, only reflecting what the responder knows within its scope.

Issues:

- OCSP responders can be slow/unreachable; explicitly choose **fail-open/fail-closed** based on risk.
- HTTP 200 from an OCSP server **is not enough**; verify the OCSP response signature, validity window, and issuer.
- HTTPS OCSP stapling is a separate topic; do not assume Java TLS config automatically applies to SAML signature validators.
- A self-signed certificate used as a public-key container may lack OCSP AIA and belong to no responder-backed PKI.
- A CA-revoked cert still accepted by an SP under metadata key pinning **does not prove** OCSP checking ran.

### 7.3. Three statuses to separate

~~~text
VALIDITY:
  BEFORE_VALIDITY | WITHIN_VALIDITY | AFTER_VALIDITY

REVOCATION:
  GOOD | REVOKED | UNKNOWN_OR_UNAVAILABLE | NOT_CHECKED

TRUSTED_KEY:
  IN_TRUSTED_REGISTRATION | REMOVED_FROM_TRUST | UNTRUSTED
~~~

When diagnosing failures, never collapse all three statuses into one `certificateValid=true` flag. A cert within `notBefore`/`notAfter` can still be revoked. An expired cert may still appear in trusted metadata. A mathematically valid key outside trusted registrations must be rejected.

### 7.4. Policy when revocation sources are unavailable

- **PKIX requiring CRL/OCSP:** if status is unreachable, policy must decide whether to reject. For sensitive flows, consider fail-closed and operational alerts.
- **Explicit-key SAML trust:** the source of truth is usually trusted metadata and key approval/removal; do not pretend CRL/OCSP was checked when no such mechanism exists.
- **Compromised key:** remove the key immediately per agreement, force metadata refresh/rollout, and isolate potentially affected sessions/paths.
- **Unrefreshable metadata:** monitor age and validity; once past the allowed window, fail closed per designed policy rather than using stale data forever.

## 8. What does Spring Security SAML2 check by default?

### 8.1. Spring Security Servlet flow

~~~text
Browser POSTs SAMLResponse
    |
    v
Saml2WebSsoAuthenticationFilter
    |
    v
Saml2AuthenticationToken + trusted RelyingPartyRegistration
    |
    v
OpenSAML AuthenticationProvider
    |
    +-- Verify signature using trusted IdP credentials
    +-- Check Issuer/Destination/Status per profile
    +-- Check Assertion/Subject/Conditions/Audience
    +-- Decrypt if present and configured
    |
    v
Saml2Authentication / Saml2AuthenticatedPrincipal
    |
    v
SP-local authorization
~~~

Exact provider class names vary across Spring Security/OpenSAML lines; **Spring Security 6.3** typically uses OpenSAML 4, while newer releases use OpenSAML 5. Check your exact version's dependency tree and Javadoc. This diagram shows **SAML authentication responsibilities**, not a guarantee that every cert automatically undergoes PKIX/CRL/OCSP checks.

### 8.2. Three assumptions not to make by default

**False assumption 1: "Adding a cert to YAML makes Spring check CA chains and OCSP."**  
`Saml2X509Credential.verification` supplies the certificate used to verify signatures in an IdP trust relationship. It is not by itself an instruction to run `CertPathValidator`, `checkValidity`, CRL, and OCSP on every request.

**False assumption 2: "An expired certificate means Spring definitely blocks login."**  
In an explicit-key trust deployment, an expired certificate may remain a pinned trusted public key; mathematical signatures can continue verifying. In PKIX-based trust or custom checking policies, it may be blocked. **Never make absolute assertions without testing your exact version/config.**

**False assumption 3: "Spring checked CRL/OCSP because the HTTPS metadata fetch succeeded."**  
HTTPS/TLS path validation and SAML XML signature verification use **two separate trust pipelines**. A valid HTTPS channel does not make signing certs inside metadata "not revoked" or prove the XML metadata itself was signed.

### 8.3. Default scope vs. additional responsibilities

| Check | Spring Security/OpenSAML SAML login | Additional policy/setup needed |
| --- | --- | --- |
| SAML Response/Assertion XML signatures | Built-in processor/validator using trusted registration's verification credentials. | Pick right IdP, trusted metadata/certs, signed-object selection, algorithm policy. |
| SAML Issuer/Recipient/Audience/time/request correlation | Profile-based validators depending on version and customization. | Test failure cases and clock skew; never disable to bypass integration errors. |
| X.509 `notBefore/notAfter` of IdP signing cert | **Must not be assumed** always enforced as an acceptance gate. | Define explicit policy and implement checks/gates per trust model if needed. |
| CRL/OCSP for IdP signing cert | **Must not be assumed** enabled automatically. | Appropriate PKIX/revocation engine or metadata key removal per federation policy. |
| Metadata XML signature | Depends on metadata loader/trust config; **having a metadata URI does not guarantee XML signature verification**. | Configure signer trust anchor if required; verify in practice. |
| Metadata `validUntil`/`cacheDuration` | Depends on loader/caching/resolver. | Design expiry-aware refresh; avoid infinite stale snapshots. |
| Expiring SP signing/decryption certificates | Library may keep using key pair; partners enforce their own policies. | Monitor, schedule cert replacement, publish SP metadata, coordinate with IdP. |
| Local user/tenant permissions | Not inferred automatically from certs or assertions. | Application authorization, ownership checks, session revocation. |

In newer Spring Security lines, the `Authenticating SAML Responses` docs describe extension points for customizing response/assertion validators. **Never replace the entire validator with a lambda that only checks cert expiry**: doing so can accidentally drop signature/issuer/condition checks. When adding policy, **compose/delegate to the default validator** per your version's API and write regression tests for every check.

## 9. Spring Boot configuration: verification keys vs. SP signing keys

### 9.1. Using IdP metadata

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}
~~~

`PARTNER_A_METADATA_URI` must come from a governed trusted source. Metadata may list multiple certificates for rollover. Loading metadata at startup **does not imply automatic refresh in every version**; understand your actual repository/resolver/caching behavior.

### 9.2. Declaring verification certs manually

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example/saml2/sp/partner-a"
            acs:
              location: "https://orders.example/login/saml2/sso/partner-a"
              binding: POST
            assertingparty:
              entity-id: "https://idp.partner-a.example/saml"
              sso-url: "https://idp.partner-a.example/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/idp-a-signing.crt"
                  - certificate-location: "classpath:certs/idp-b-signing.crt"
~~~

This is an **illustrative Spring Boot 3.3 config example**; certificate files must genuinely exist and be verified, and URLs replaced for your real environment. Two certificates represent **two IdP keys trusted during overlap**, not automatic revocation-list checking.

Specifically:

- `assertingparty.verification.credentials` are **trusted IdP public certs**.
- `signing.credentials` are **SP private key/certificate** for signing outbound SAML.
- `decryption.credentials` are **SP private key/certificate** for decrypting inbound assertions if the IdP encrypts them.
- Never take a certificate from an attacker-supplied `<ds:KeyInfo>` inside a response and treat it as an authorized verification credential.

### 9.3. Switching IdP certificate A to B

When configuring files manually, update the files/registration/beans and **ensure all instances receive the new version**. When running from metadata, verify the system genuinely refreshes and publishes the new trusted set; never assume changing a metadata file updates an in-memory repository automatically.

## 10. Hands-on Java 17: reading certificate validity honestly

A useful learning exercise is writing a JDK 17 program that reads a public certificate (PEM or DER) and reports **only the facts directly determinable**.

This program **only** parses the X.509 certificate, checks `notBefore/notAfter`, and computes the SHA-256 fingerprint. It **does not**:
- verify SAML XML signatures,
- verify X.509 certification paths or certificate authorities,
- query CRL/OCSP,
- check metadata trust or local permissions.

### 10.1. File `CertificateValidityInspector.java`

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;
import java.util.HexFormat;

public class CertificateValidityInspector {

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println(
                "Usage: java CertificateValidityInspector <cert-file> [ISO-8601-instant]");
            System.exit(2);
        }

        Instant at = args.length == 2
            ? Instant.parse(args[1])
            : Instant.now();

        X509Certificate cert;
        try (InputStream in =
                 Files.newInputStream(Path.of(args[0]))) {
            CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
            cert = (X509Certificate) factory.generateCertificate(in);
        }

        String validity;
        try {
            cert.checkValidity(Date.from(at));
            validity = "WITHIN_VALIDITY";
        }
        catch (CertificateExpiredException ex) {
            validity = "EXPIRED";
        }
        catch (CertificateNotYetValidException ex) {
            validity = "NOT_YET_VALID";
        }

        byte[] fingerprint = MessageDigest.getInstance("SHA-256")
            .digest(cert.getEncoded());

        System.out.println("at=" + at);
        System.out.println("subject=" +
            cert.getSubjectX500Principal().getName());
        System.out.println("issuer=" +
            cert.getIssuerX500Principal().getName());
        System.out.println("notBefore=" +
            cert.getNotBefore().toInstant());
        System.out.println("notAfter=" +
            cert.getNotAfter().toInstant());
        System.out.println("sha256=" +
            HexFormat.of().formatHex(fingerprint));
        System.out.println("validity=" + validity);

        // Definitive conclusions NOT provided by checkValidity():
        System.out.println("samlSignature=NOT_CHECKED");
        System.out.println("pkixPath=NOT_CHECKED");
        System.out.println("revocation=NOT_CHECKED");
        System.out.println("samlMetadataTrust=NOT_CHECKED");
    }
}
~~~

### 10.2. Compile and run

Prepare a real **public** certificate file `idp-signing.pem` (never a private key):

~~~bash
javac --release 17 CertificateValidityInspector.java
java CertificateValidityInspector idp-signing.pem
~~~

You can test at a fixed point in time:

~~~bash
java CertificateValidityInspector idp-signing.pem 2030-05-01T10:00:00Z
~~~

Output lines for `subject`, `issuer`, `sha256`, `notBefore`, `notAfter`, and `validity` depend on the supplied file/timestamp. **There is no fixed stdout** for an unspecified certificate. However, the last four lines of every successful run are **exact**:

~~~text
samlSignature=NOT_CHECKED
pkixPath=NOT_CHECKED
revocation=NOT_CHECKED
samlMetadataTrust=NOT_CHECKED
~~~

Explanation:

- `CertificateFactory` parses the certificate; it does not establish trust with the IdP.
- `X509Certificate.checkValidity(Date)` only checks the **time interval** at `at`. It does not validate certificate chains or CRL/OCSP.
- `MessageDigest SHA-256` computes the public certificate fingerprint for inventory/partner comparison. It **does not** prove the certificate is trusted.
- `HexFormat` requires JDK 17; older JDKs need an alternative hex formatter.
- If the certificate is self-signed, that **does not automatically make it trusted or untrusted** across all models; evaluate per trust registry/metadata and agreement.
- Never replace Spring Security's SAML validation with this program.

### 10.3. Using `keytool` for quick inspection without writing Java

~~~bash
keytool -printcert -file idp-signing.pem
~~~

`keytool -printcert` shows issuer, subject, fingerprint, validity, and certain certificate extensions. **This is an inspection action**, not proof that the SAML system enforces revocation checking. `NotAfter` is an operational alert milestone, whereas whether **the key belongs to trusted metadata** must be verified separately.

## 11. Spring Boot 3.3/Spring Security 6.3: monitoring certs without conflating authn policy

To avoid unexpected certificate expiration, add a **monitor** to the SP. The code below targets **Java 17, Spring Boot 3.3.x, Spring Security 6.3.x**. It reads verification credentials from `RelyingPartyRegistrationRepository` for a specific `registrationId` and logs warnings.

### 11.1. Gradle dependencies and structure

~~~text
saml-cert-health/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlcert/
    │   ├── SamlCertHealthApplication.java
    │   ├── SecurityConfig.java
    │   └── SamlCertificateMonitor.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-cert-health'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Configuration `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}

app:
  saml:
    cert-monitor-interval-ms: 3600000
    cert-warning-days: 30
~~~

`PARTNER_A_METADATA_URI` must be a **real, trusted** IdP metadata source. This example does not auto-create an IdP, accounts, or certificates.

### 11.2. Main application

`src/main/java/com/example/samlcert/SamlCertHealthApplication.java`:

~~~java
package com.example.samlcert;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class SamlCertHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlCertHealthApplication.class, args);
    }
}
~~~

### 11.3. Enabling SAML2 Login

`src/main/java/com/example/samlcert/SecurityConfig.java`:

~~~java
package com.example.samlcert;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This code uses default SAML2 handlers and adds no debug endpoints. `authenticated()` only checks that the user signed in, **not** business authorization. Real applications must verify local permissions and tenant when accessing resources.

### 11.4. Compilable monitor

`src/main/java/com/example/samlcert/SamlCertificateMonitor.java`:

~~~java
package com.example.samlcert;

import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Component;

@Component
public final class SamlCertificateMonitor {

    private static final Logger log =
        LoggerFactory.getLogger(SamlCertificateMonitor.class);

    private final RelyingPartyRegistrationRepository registrations;
    private final int warningDays;

    public SamlCertificateMonitor(
            RelyingPartyRegistrationRepository registrations,
            @Value("${app.saml.cert-warning-days:30}")
                int warningDays) {
        this.registrations = registrations;
        this.warningDays = warningDays;
    }

    @Scheduled(
        fixedDelayString =
            "${app.saml.cert-monitor-interval-ms:3600000}"
    )
    public void inspect() {
        RelyingPartyRegistration registration =
            registrations.findByRegistrationId("partner-a");

        if (registration == null) {
            log.error("SAML certificate monitor: registration missing");
            return;
        }

        Instant now = Instant.now();
        Date checkedAt = Date.from(now);
        var credentials = registration.getAssertingPartyDetails()
            .getVerificationX509Credentials();

        if (credentials.isEmpty()) {
            log.error("SAML certificate monitor: no verification keys");
            return;
        }

        for (Saml2X509Credential credential : credentials) {
            X509Certificate cert = credential.getCertificate();
            try {
                cert.checkValidity(checkedAt);
                long daysLeft = ChronoUnit.DAYS.between(
                    now, cert.getNotAfter().toInstant());
                if (daysLeft <= warningDays) {
                    log.warn(
                        "IdP signing cert near expiry: registration={}, daysLeft={}",
                        registration.getRegistrationId(), daysLeft);
                }
            }
            catch (CertificateExpiredException ex) {
                log.error(
                    "IdP signing cert after X.509 notAfter; registration={}",
                    registration.getRegistrationId());
            }
            catch (CertificateNotYetValidException ex) {
                log.error(
                    "IdP signing cert before X.509 notBefore; registration={}",
                    registration.getRegistrationId());
            }
        }
    }
}
~~~

**What it actually does:**

- `@EnableScheduling` activates scheduling; `@Scheduled` periodically inspects the verification certificates **currently held** by the repository.
- `getAssertingPartyDetails().getVerificationX509Credentials()` retrieves IdP certificates present in a registration.
- The monitor calls `checkValidity` to **observe** notBefore/notAfter and log warnings. It **does not** check CRL/OCSP or validate any SAMLResponse.
- `warningDays=30` is an illustrative policy value, not a mandatory SAML default.
- Never log private keys, raw assertions, NameIDs, or user data.
- If the metadata loader does not refresh, the monitor will only inspect the **old certificate in RAM**; a separate refresh/rollover mechanism is required.
- If the business decides to **block logins** via an expiry check, install the gate directly in the trust/verification flow with regression tests; **never pretend an ERROR log in a monitor blocks SSO**.

### 11.5. Running the demo

With Java 17+, a compatible Gradle wrapper, and real IdP metadata:

~~~bash
./gradlew bootRun
~~~

The default SP-initiated login path is typically `/saml2/authenticate/partner-a`, and the default ACS is typically `/login/saml2/sso/partner-a`. When testing, SP entity ID and ACS must be properly registered at the IdP.

**There is no fixed stdout** for the scheduler: logs depend on run time, certificate count, and metadata contents. Never treat successful app startup as proof that CRL/OCSP checks ran.

## 12. Enforcing expiry and revocation policies without breaking the SAML validator

When an audit requires "reject expired/revoked signing certificates", clarify **which certificate types and trust model** this applies to:

1. **IdP signing cert pinned via metadata:** Do you want to enforce `notAfter`, or apply a separate key-acceptance lifetime from trusted metadata? Is there a temporary acceptance policy if technically expired yet uncompromised?
2. **IdP PKIX-signed leaf certificate:** Are exact trust anchors and reliable revocation sources available? Is OCSP/CRL required, and what happens when a responder is offline?
3. **Metadata signing certificate:** Has it been revoked/expired, and over which trusted channel is metadata distributed? Does accepting new metadata require dual approval?
4. **SP signing/decryption certificates:** Does the IdP reject expired certs? How do you publish new certs and retain old private keys for in-flight decryption without trusting compromised credentials?
5. **TLS certificates:** handled separately by JSSE/HTTP clients; never use them to prove signing cert status.

### 12.1. Login blocking architecture (conceptual)

~~~text
Trusted metadata / out-of-band approved keys
              |
        Fetch and verify source
              |
    Validate issuer, metadata expiry
              |
     Apply certificate acceptance policy
       - key allowed for IdP role?
       - X.509 validity required?
       - revocation check required?
       - key explicitly compromised?
              |
       +------+------+ 
       |             |
      PASS          FAIL/UNKNOWN per policy
       |             |
Publish trusted    Reject candidate /
registration       alert / stop new trust
       |
Spring Security normal SAML validator
       |
Only valid SAML Response becomes Authentication
~~~

**Keep all SAML checks intact** after applying policy to the certificate: signature over the right element, issuer, audience, recipient, InResponseTo, Conditions, and replay. Avoid writing a new `AuthenticationManager` that merely calls `checkValidity` and grants login.

### 12.2. Never build trust solely from a certificate inside XML

An attacker can generate their own key pair, sign a SAML Assertion, and embed the public certificate in `ds:KeyInfo`. If the SP trusts that certificate simply because the signature matches mathematically, the SP loses its trusted IdP boundary.

Properly, **the IdP certificate must come from a pre-identified trusted source**: signed metadata/trust registry/governed certificate pin, or a PKIX chain to a policy-approved trust anchor. "Signature valid with provided key" differs from "signature valid with **trusted IdP key**".

### 12.3. Handling a cert that is expired yet still in metadata

There are at least two sound policies depending on the agreement:

- **Metadata-key-trust policy:** The key remains in verified metadata and was not removed for compromise; the SP may decide to keep using the key even past X.509 `notAfter`, paired with alerts/rollover requests. That decision must be explicitly documented and bounded.
- **Strict-X.509-validity policy:** The SP requires certs to be within `notBefore`/`notAfter` to enter the verification key set, even if metadata still advertises them. Rotation overlap must happen before expiry, with a remediation plan if the IdP cert expires without a new key published.

There is no single "SAML always mandates PKIX" answer for every federation. If compliance documents **mandate strict validity**, it cannot be solved by changing an explanation message; it must be explicitly implemented and tested.

### 12.4. Handling UNKNOWN revocation status

If PKIX/CRL/OCSP is chosen and GOOD status is mandatory, the runtime must handle `UNKNOWN`, `TRY_LATER`, responder timeouts, stale CRLs, and invalid OCSP signatures. "Unable to look up" **is not** "GOOD". For sensitive systems, test fail-closed policy to ensure no session is created when status cannot be verified.

However, **do not call CRL/OCSP on every SSO request if it risks mass timeouts** without caching, timeouts, circuit breakers, and privacy analysis. Status can be checked in the control plane to decide the trusted key set and bound validity per policy; coordinate the exact model with the security team.

## 13. Key loss, compromise, and emergency response

A leaked signing key is completely different from a certificate past its expiration date. With a **private signing key compromise**, an attacker can forge valid signatures using the key the SP currently trusts. If the SP still pins that public key in its registration, forged signatures **will verify mathematically**.

Minimum incident procedure:

1. **Triage incident:** routine expired cert or suspected/confirmed private key compromise? Never lump everything together as a "cert issue".
2. **Activate IdP/SP contact channels:** verify partner identity and use approved out-of-band channels for emergency action.
3. **Stop trusting compromised key A:** remove from trusted metadata/registration, invalidate caches, and propagate to every node. Do not wait for `notAfter`.
4. **IdP issues new key B:** register the public cert via a source with independent trust proof; never pull from unverified metadata.
5. **Enforce session policy:** assess invalidating sessions created during the exposure window, logout/step-up, and audit investigation; removing the key only blocks **new authentications**, not existing SP sessions.
6. **Monitor:** metadata version/hash, trusted fingerprints per node, failed signatures, trust-change events, and stale alerts.
7. **Controlled rollback:** only with proof the old key was not compromised; never reintroduce A to "restore service" if the private key may be exposed.
8. **Postmortem:** document timeline, root cause, approval roles, lessons learned, and automated rotation checks.

In explicit-key trust models, **CA revocation alone** does not prove SPs have stopped trusting key A. Empirically verify that SAML Responses signed with A are rejected on every SP node.

## 14. QA matrix: what must be tested?

| ID | Scenario | Expected / what to prove |
| --- | --- | --- |
| C01 | Response signed with trusted IdP key A, assertion unexpired. | Login succeeds only if signature and all SAML conditions pass. |
| C02 | Response signed with key not in trusted registration. | Rejected, even if signature matches a cert embedded in XML. |
| C03 | IdP cert A `notAfter` passed, key A still pinned. | **Measure actual behavior**; verify against explicit-key or strict-validity policy rather than guessing from library. |
| C04 | IdP cert before `notBefore`. | Monitor detects; under strict policy, do not accept key early. |
| C05 | Unexpired cert revoked under PKIX. | If PKIX revocation is required, rejected; under metadata trust, remove key per incident policy. |
| C06 | OCSP timeout/unknown or expired CRL. | Enforces approved fail-closed/fail-open behavior and alerts; never treats UNKNOWN as GOOD. |
| C07 | Validly signed metadata with A+B during rollover. | SP accepts A/B during approved overlap with full SAML checks. |
| C08 | After IdP retires A, metadata has only B and SP refreshed. | A is no longer trusted; B works. |
| C09 | Key A confirmed compromised. | Immediate removal of A, cache/node update, test Responses signed with A are rejected. |
| C10 | Metadata XML signature invalid or different issuer. | Do not publish new trusted registration; alert. |
| C11 | Metadata past `validUntil` or cache stale beyond policy. | Do not use stale data indefinitely to trust old keys. |
| C12 | Assertion `Conditions.NotOnOrAfter` passed while cert is unexpired. | Reject Assertion; cert validity does not extend it. |
| C13 | SubjectConfirmationData expired while metadata is valid. | Reject invalid bearer confirmation. |
| C14 | SP AuthnRequest signing cert rejected by IdP per policy. | Identify outbound signing error without disabling IdP response checks. |
| C15 | New SP decryption key B not yet updated at IdP. | EncryptedAssertion may fail decryption; coordinate public/private key rollout. |
| C16 | Metadata TLS succeeds yet metadata trust not verified per policy. | HTTPS does not replace XML metadata signature/trust approval. |
| C17 | IdP supplies self-signed cert under explicit-key contract. | Verify pinned key/metadata policy properly without assuming CA is mandatory. |
| C18 | Two IdPs have different certs/issuers yet same NameID value. | No cross-tenant/trust-anchor mix-up; SP authorization stays independent. |
| C19 | Monitor reports expired cert yet SSO still succeeds. | Recognize monitor is not a login gate; review effective policy. |
| C20 | User already logged in, then SP removes compromised trusted cert. | Evaluate session invalidation/revocation; do not treat key removal as automatic logout. |

### 14.1. Verifying without attacking production

Use a **test IdP** and test cert set in an isolated environment. Prepare:

- Valid cert A, A-expired, A-not-yet-valid, and B to test rotation.
- Metadata V1 (A only), V2 (A+B), V3 (B only) signed by a pinned test metadata signer.
- Tampered/wrong-issuer metadata, expired metadata, or invalid signatures.
- Responses signed by A/B/attacker cert carrying the same test Format/NameID yet different SAML conditions.
- Mock/test CRL/OCSP responders if PKIX requires them; never pretend a self-signed test cert has a CA revocation source when none exists.

Tests must confirm **via real request behavior** or provider integration tests; merely seeing "loaded certificate" in logs does not prove whether a certificate is accepted or rejected.

### 14.2. Root-cause analysis before changing config

If login fails after rotation, ask in order:

1. Does metadata connectivity work? Are there proxy/TLS errors?
2. Was the new metadata verified and published? Are all nodes synchronized?
3. Which certificate is the IdP actually using to sign Response/Assertion?
4. Which fingerprints does the SP currently trust, under which registration/issuer?
5. Are SAML Status, Issuer, Destination/Recipient, Audience, Conditions, and InResponseTo valid?
6. Is a custom strict X.509 validity/PKIX/revocation policy active?
7. If Authentication succeeds yet API returns 403, check **local permissions** instead of certificates.

Never fix by disabling signatures, dropping issuer checks, expanding clock skew infinitely, or accepting any public key inside the Response.

## 15. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "An expired certificate definitely breaks SAML signature math." | Mathematical signatures and X.509 validity are two distinct checks. |
| "An unexpired certificate cannot be revoked." | CRL/OCSP or key removal can revoke before `notAfter`. |
| "Setting metadata-uri means metadata auto-refreshes forever." | Depends on repository/resolver/caching and actual configuration. |
| "HTTPS metadata works, so the SAML signing cert isn't revoked." | TLS and SAML trust are separate. |
| "The CA revoked the cert, so the SP's pinned cert stops trusting it automatically." | Not necessarily; explicit-key trust usually requires metadata/trust removal. |
| "`<ds:X509Certificate>` in the Response is a trusted certificate." | Sender-supplied certificates cannot serve as their own trust anchor. |
| "`X509Certificate.checkValidity` checks CRL/OCSP too." | That method only checks **`notBefore`/`notAfter`**. |
| "Metadata's `validUntil` is the cert's `notAfter`." | Metadata expiry differs from X.509 expiry. |
| "`cacheDuration` makes the app automatically fetch on a schedule." | It is caching guidance; refresh mechanics must be implemented/verified. |
| "A WARN log for expired certificate means SSO is blocked." | Monitoring does not alter the authentication pipeline. |
| "Once the SP removes a compromised key, old sessions end automatically." | SP sessions/authorization require separate handling. |
| "Legacy Spring SAML Extension and modern SAML2 Login share defaults." | Different codebases, trust engines, and APIs; never mix docs. |
| "Safe rollover means swapping A for B in one step." | Usually requires A+B overlap, whereas key compromise demands urgent removal. |
| "Successful SAML verification means local admin." | Authentication and authorization are two independent layers. |

## 16. Production readiness checklist

- [ ] Maintain an inventory of IdP/SP signing and decryption certificates by issuer/registration, fingerprint, owner, and validity dates.
- [ ] Know each partner's **trust model** (explicit-key/metadata or PKIX) without guessing from certificate names.
- [ ] Signature verifier uses **trusted keys**; never trust browser-supplied KeyInfo.
- [ ] Explicit policy exists on whether X.509 validity is mandatory, where it is checked, and failure behavior.
- [ ] Explicit policy exists for CRL/OCSP or metadata key removal; UNKNOWN status is never mistaken for GOOD.
- [ ] Metadata comes from approved sources, signature-verified when required by profile, with expiry/cache/refresh policies.
- [ ] Certificate rollover includes overlap, staging, testing responses with A and B, and a plan to remove A.
- [ ] Key compromise runbook covers rapid trust removal, IdP communication, node sync, and session revocation review.
- [ ] SP signing/decryption credentials are stored in a secret manager; private keys are never committed to Git.
- [ ] Monitor `notBefore/notAfter`, upcoming expiry, metadata age, last successful refresh, and active fingerprints.
- [ ] Monitoring is clearly distinguished from **runtime enforcement**; policy-violating certificates are tested to actually fail.
- [ ] TLS, metadata signing, Assertion signing, and decryption certificates are managed separately by role.
- [ ] Never treat valid certs as a substitute for `Conditions`, `SubjectConfirmationData`, Audience, Recipient, InResponseTo, or replay checks.
- [ ] Tests C01–C20 or equivalent run before and after rotation.
- [ ] Never log private keys, raw SAMLResponses, NameIDs, or sensitive assertions.
- [ ] Local authorization/tenant isolation remains enforced even when SAML authentication succeeds.
- [ ] When upgrading Spring Security/OpenSAML, verify Javadoc/baselines for the exact version and re-run regression tests.

## Takeaway

> **Valid signature ≠ unexpired certificate ≠ unrevoked certificate ≠ trusted public key.** In SAML2 federation, signing keys may be trusted by **metadata/explicit key** rather than PKIX; X.509 validity and CRL/OCSP must therefore **never be assumed** to be built-in enforcement gates. Use approved trust sources, operate metadata/rotation/revocation properly, test enforced policies on every Spring Security deployment, and keep application authorization in its own layer.

### References

- [OASIS — SAML V2.0 Metadata Interoperability Profile, 2019](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-os.html): metadata-based key trust, key rollover, and requirement to remove compromised keys without relying on consumer CRL/OCSP.
- [OASIS — Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `KeyDescriptor`, `validUntil`, `cacheDuration`.
- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertion/SubjectConfirmation lifetimes and protocol constraints.
- [RFC 5280 — X.509 PKI and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `notBefore`, `notAfter`, certificate paths, and CRLs.
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960): OCSP statuses and response verification mechanisms.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, verifying credentials, and SAML authentication.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): signature validation and extension points.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): metadata trust, signature verification, and metadata repositories.
- [Spring Boot 3.3 — Security/SAML2](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): SAML2 relying party configuration.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): certificate revocation risks, key compromise, and defenses.
