# Distinguishing SAML signing certificates from HTTPS certificates in Spring Security Federation

> **Topic:** Spring Security – federation. **Group:** Keys and certificates. This lesson explains the difference between **certificates used to sign/verify SAML 2.0 messages** and **certificates used in HTTPS/TLS connections**, especially when a Spring Security application acts as a **Service Provider (SP)** federated with an **Identity Provider (IdP)**. The goal is to avoid mixing up keys, trust models, configurations, and certificate rotation workflows.

## 1. Key takeaway before starting

**Same X.509 file format, different function and trust model.**

- **HTTPS/TLS certificates** bind a public key to a **hostname** in an HTTPS connection (e.g., `login.example.org` or `portal.example.org`). The browser/HTTP client verifies the TLS handshake, hostname (DNS SAN), certificate chain to a CA/trust anchor, validity, and related TLS policies. The TLS private key resides on the **HTTPS endpoint server** or TLS termination layer such as a load balancer/reverse proxy.
- **SAML signing certificates** are registered by the SP as the **IdP's verification credential** to verify XML signatures on **SAML Response/Assertion**. The private signing key resides at the **IdP**; the SP holds the public verification certificate. Trust typically comes from **verified trusted SAML metadata or explicit key/pin configuration**, not implicitly from the browser's trusted CA list.
- **SP AuthnRequest signing certificate** is another pair: the SP holds the private key to sign **AuthnRequest/LogoutRequest** when IdP policy requires it; the IdP registers the SP's public signing certificate.
- **SP encryption certificate** is a fourth role: the IdP uses the SP's public encryption certificate to encrypt Assertions; the SP uses its matching private decryption key to decrypt. **Encryption ≠ signature ≠ HTTPS.**

**Real-world example:** Accessing `https://login.example.org/metadata` over valid HTTPS **does not prove** that a subsequent SAML Response has a trusted signature. Conversely, a SAML Response with a valid IdP signature **does not prove** that `https://login.example.org` has an unexpired TLS certificate or matching hostname. Both checks must be performed **independently** and are each required in context.

## 2. Five key/certificate pairs that may coexist

Consider a system with a Spring MVC/Spring Security application portal and an external IdP.

| Role | Who holds the private key? | Who needs the public certificate/key? | What does it protect? |
|---|---|---|---|
| **SP's TLS server cert** | SP, ingress, or load balancer managing HTTPS | Browser/HTTP client connecting to SP | HTTPS channel to ACS, app pages, SP metadata |
| **IdP's TLS server cert** | IdP or proxy in front of IdP | Browser, SP HTTP client fetching metadata/introspection when needed | HTTPS channel to login page, SSO endpoint, IdP metadata |
| **IdP SAML signing cert** | **IdP** holds private signing key | **SP** trusts IdP public cert | XML signature of SAML Response/Assertion/Logout per agreement |
| **SP SAML signing cert** | **SP** holds private signing key | **IdP** trusts SP public cert | Signature of `AuthnRequest`, `LogoutRequest`, etc. issued by SP if applicable |
| **SP SAML encryption cert** | **SP** holds private decryption key | **IdP** uses SP public cert to encrypt | Confidentiality of Assertion/NameID/Attributes when SAML encryption is used |

A product might reuse the same keypair for multiple roles due to interop constraints, yet **do not infer that this is mandatory**. Separating keys by function usually reduces blast radius and helps manage rotation, authorization, and incident investigation; OWASP recommends separating signing and encryption in SAML. For production, use appropriate key usage/EKU and policy; never reuse a TLS private key for SAML merely to avoid creating another file.

### 2.1. Visual flow

~~~text
                         TLS server certificate (IdP)
Browser  ─── HTTPS ────────────────────────────────> IdP
  |                                                 |
  |              IdP SAML private signing key       |
  |              signs Response / Assertion         |
  |                                                 |
  | <───────── SAMLResponse (via browser) ──────────+
  |
  |             TLS server certificate (SP)
  └──── HTTPS POST SAMLResponse ──────────────────> Spring Security SP
                                                   |
                                                   | Verify XML signature
                                                   | using IdP PUBLIC SAML
                                                   | signing certificate
                                                   |
                                                   | Check Issuer, Audience,
                                                   | Destination, Recipient,
                                                   | Time, InResponseTo, Replay
                                                   v
                                               Authentication
~~~

**Observation:** There are at least two distinct TLS handshakes and one separate XML signature verification. HTTPS only protects each TLS channel; **the browser merely transports the SAMLResponse** and is not considered a trusted IdP. An HTTP POST form arriving over TLS can carry a forged payload crafted by the sender; XML signature along with SAML trust/validation decides whether the identity is accepted.

## 3. An X.509 certificate is a "wrapper" around a public key

An X.509 certificate typically contains:

- **Subject** and **Issuer** (Distinguished Name): describe the subject and issuing authority of the certificate.
- **Public Key** and algorithm: RSA, EC, etc., depending on software capabilities and policy.
- **Serial Number**: serial number assigned by the issuer.
- **Validity**: `notBefore`, `notAfter`.
- **X.509 extensions**: `Subject Alternative Name (SAN)`, `Key Usage (KU)`, `Extended Key Usage (EKU)`, `Basic Constraints`, `Authority Key Identifier`, `Subject Key Identifier`, etc.
- **Certificate Signature**: the CA/issuer's signature over the **certificate content**, distinct from the SAML XML signature.

Two signature layers that are frequently confused:

| Signature | Who creates it? | What is being signed? | Who verifies and with which key? |
|---|---|---|---|
| **X.509 certificate signature** | CA or the subject itself when self-signed | The TBSCertificate structure | TLS/PKIX validator or certificate consumer per trust policy |
| **XML signature of SAML Response/Assertion** | IdP using SAML private signing key | `ds:SignedInfo` linked to Response/Assertion XML via Reference/digest | SP using trusted **IdP SAML verification public key** |

A **self-signed** IdP certificate can be completely valid if the SP already trusts that public certificate via federation metadata/authenticated key exchange. A self-signed SAML cert is **not inherently an error**. However, a self-signed TLS certificate lacking a CA/trust anchor in the browser/HTTP client typically triggers warnings or connection failures. This is a **trust model** difference, not a file syntax difference.

X.509 certificates and related private keys can be stored as:

- `.pem` / `.crt` / `.cer`: may hold a public X.509 certificate in PEM or DER format; the extension **does not guarantee** the format.
- `.key`: usually a private key, though you cannot deduce this with certainty from the filename alone.
- `.p12` / `.pfx`: PKCS#12 archive that can contain a private key, certificate chain, trust material, and a password.
- Java `KeyStore` / `TrustStore`: widely used in TLS. A store does not itself tell whether a key inside was issued for SAML signing or a TLS server; **configuration and usage policy** decide.

**Protection principle:** Public certificates can be shared via metadata workflows; **private keys must never be put into metadata, committed, sent to partners, or logged**. A file labeled `BEGIN CERTIFICATE` does not contain a private key; a file labeled `BEGIN PRIVATE KEY` or equivalent contains data that must be protected.

## 4. What does HTTPS/TLS verify?

### 4.1. When the browser visits the IdP page

Suppose the browser opens `https://login.example.org/`.

The TLS client typically checks:

1. The expected DNS name `login.example.org` must be covered by an appropriate **Subject Alternative Name (SAN)**. Do not equate `CN` with DNS SAN in modern hostname verification.
2. The certificate chain leads to a **suitable trust anchor**, usually a public root CA in the browser/OS trust store, or a private CA approved by administrators.
3. Certificate validity (`notBefore`/`notAfter`) and PKIX requirements, key usage/EKU, algorithms, revocation/CT if enforced by platform/policy.
4. The TLS handshake proves the server has access to the **private key matching** the public key in the accepted certificate; the session derives symmetric keys to protect exchanged data.
5. Allowed TLS protocol versions and cipher suites (prefer TLS 1.3, configure secure TLS 1.2 when compatibility is needed; do not enable weak legacy TLS for legacy interop).

If TLS checks fail, the browser should reject or warn about the connection. Having the right SAML signing certificate on the SP **cannot fix** TLS errors on the IdP endpoint or ACS.

### 4.2. TLS protects the connection, not the SAML issuer identity

A TLS certificate with SAN `login.example.org` proves the HTTPS endpoint the client is connecting to is authorized to use the certificate for that hostname under the trust model. It **does not by itself assert**:

- That the Assertion's `saml:Issuer` is an IdP configured by the SP.
- That the TLS cert's public key is the **IdP SAML signing key**.
- That the Assertion was signed by the IdP, is still valid, and has an Audience matching the SP.
- That the user is authorized to enter the application or holds an admin role.
- That metadata fetched from that URL is allowed to **automatically replace all trusted IdP credentials** without going through a trust/rotation policy.

When using HTTPS to fetch IdP metadata, TLS helps prevent MITM on the connection to the **right trusted metadata URL**. Still, the application must enforce **rules for selecting issuer/entityID/registration**, governed metadata sources, and a key rotation plan so it does not trust an arbitrary different signing key.

### 4.3. SP HTTPS may terminate at ingress

Example:

~~~text
Browser --HTTPS--> Ingress / Load Balancer --internal HTTP--> Spring Boot
                      |
                      +-- TLS certificate, private key,
                          and SNI hostname at ingress
~~~

In this TLS termination setup, **Spring Boot does not necessarily have a TLS private key or `server.ssl.*`**. Ingress holds the TLS keypair. The Spring application must still hold the **IdP SAML verification credential** for `SAMLResponse` and may hold **SP SAML signing/decryption keys**. There is no contradiction if Spring only listens on HTTP inside a protected internal network while the **public** ACS is `https://portal.example.org/login/saml2/sso/corporate`.

With TLS termination, you must verify trusted forwarded headers, external scheme/host/port, `Secure` cookies, and SAML `Destination/Recipient`. Do not let clients send forged `X-Forwarded-Proto` headers that trick Spring into building incorrect metadata/ACS URLs.

## 5. What does a SAML signing certificate verify?

### 5.1. A SAML signature is an XML Digital Signature

The IdP signs `samlp:Response` or `saml:Assertion` per the SAML Web Browser SSO profile and federation agreement. Typical XMLDSig:

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="#_saml_assertion_id">
      <ds:Transforms>...</ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:KeyInfo>...</ds:KeyInfo>
</ds:Signature>
~~~

This is a **structural skeleton**, not a runnable valid signature; never use ellipsis placeholder values in real messages. On real data, the validator must:

1. Parse XML safely, defending against XXE/schema confusion/duplicate IDs.
2. Select the **exact Response/Assertion that will actually be used** to create Authentication.
3. Resolve `ds:Reference` and allowed transforms, verifying the digest and signature for the exact node.
4. Obtain the public verification key **from RelyingPartyRegistration/trusted IdP metadata**, never blindly trusting keys inside browser-supplied `KeyInfo`.
5. Enforce signature placement policy: a validly signed Response covering the used Assertion, or a validly signed Assertion; a present but invalid signature must fail.
6. Check SAML semantics: Issuer, Audience, Destination, Recipient, Conditions, NotBefore, NotOnOrAfter, InResponseTo, replay, principal/role policy.

A SAML signature proves **integrity and trusted signing origin of the signed XML region**; it **does not hide** NameID/email/groups. To keep assertion content confidential for the SP, `EncryptedAssertion` per policy is needed alongside TLS.

### 5.2. Which metadata does the public signing cert come from?

In SAML 2.0 metadata, the **IdP** can publish its signing certificate inside `IDPSSODescriptor/KeyDescriptor use="signing"`. The SP uses that public certificate to verify incoming SAML signatures.

**Simplified structural sample**, not real metadata and lacking complete X.509 base64 data:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_DATA</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Note:** The IdP's `entityID` can be a URI that does not open over HTTP; `SingleSignOnService.Location` is the IdP protocol URL; the TLS certificate on hostname `login.example.org` may have a Subject/SAN completely different from the SAML entityID. Never try to use a certificate SAN to infer the SAML issuer.

In metadata, `KeyDescriptor use="signing"` means **public signing material belonging to the party publishing the metadata**. In **IdP metadata**, the SP verifies the IdP's signature; in **SP metadata**, the IdP verifies the SP's signature. `use="encryption"` is a separate role; when the `use` attribute is absent, meaning/usability must be read per metadata specification and interop policy, never assumed to mean TLS.

### 5.3. Response signature vs. Assertion signature

Possible cases:

| Scenario | Signing condition | What the SP must do |
|---|---|---|
| Response signed, Assertion unsigned | Response signature **covers the exact inner Assertion** | Verify Response signature with IdP key, validate Assertion conditions |
| Assertion signed, Response unsigned | Each used Assertion **has a valid signature** per profile/policy | Verify Assertion signature and validate Response/request context |
| Both signed | Two signatures with two scopes | Verify both when present; reject invalid signatures |
| Neither Response nor Assertion signed | Insufficient integrity/authenticity for Browser SSO POST | Reject |
| Signed Response but converter reads Assertion outside signed scope | XML Signature Wrapping risk | Reject: signature valid but used data is unprotected |

Never write your own XML parser to hunt for a `NameID` tag and assign `ROLE_ADMIN`. Spring Security/OpenSAML exists to bind signature verification to the **exact Assertion being consumed**.

## 6. Trust model: CA/hostname vs. federation registration

| Question | HTTPS/TLS certificate | SAML signing certificate |
|---|---|---|
| What is being verified? | The TLS server currently serving the HTTPS connection | Signature on XML Response/Assertion/Request |
| Primary target identifier | DNS hostname/IP checked via SAN | IdP/SP `entityID`, `Issuer`, Audience, and trusted registration |
| Where is the private key? | Server/ingress terminating TLS | IdP signs SAML; SP signs requests if required |
| How is the public key trusted? | Trust store/CA chain, hostname verification, and TLS policy | Trusted SAML metadata, explicit verification credential, or verified federation policy |
| Can self-signed be used? | Only when clients are explicitly configured to trust it; public browsers usually error | Often possible if public cert/metadata trust is established securely |
| Where is the certificate used? | TLS handshake | XML Signature validation |
| Checked against SAN or entityID? | SAN matching connected hostname | EntityID/Issuer/Audience via SAML semantics; cert taken from trust registration |
| Common Spring configuration | `server.ssl.*` / `spring.ssl.bundle.*` / ingress | `spring.security.saml2.relyingparty.registration.*.assertingparty.verification.credentials` |
| Rotation management | ACME/CA/ingress/SSL bundle, browser trust | IdP metadata/cert rollover, SP trust updates, and partner coordination |
| On failure | HTTPS handshake, cert chain, hostname, TLS protocol | `Signature validation failed`, issuer/registration mismatch, wrong signing key |

**Subtle distinction:** A SAML certificate is an X.509 cert with a CA/self-signed signature and may carry KU/EKU/validity. However, many federation frameworks use **explicit public key trust** instead of WebPKI-style PKIX chain validation; checking KU, EKU, expiry, and revocation depends on the specific software/policy. Never claim "Spring always checks every X.509 expiry" or "when a SAML cert expires, every SP stops" without checking the implementation. System owners must still schedule rotation based on **certificate validity, cryptoperiod, and policy**.

Similarly, never claim "a SAML signing cert must be issued by a public CA"; a self-signed certificate trusted directly via a verified channel can be appropriate, quite unlike public browser HTTPS trust standards.

## 7. Three trust boundaries when loading IdP metadata over HTTPS

This is the scenario that causes the most confusion.

~~~text
[1] SP connects to https://idp.example.org/metadata
       -> TLS client checks certificate SAN + CA/trust

[2] SP parses downloaded IdP metadata
       -> Checks source URL, IdP entityID/registration,
          metadata trust policy / metadata signature if applicable
       -> Extracts IdP SAML signing public cert for the right role

[3] Browser delivers SAMLResponse to ACS
       -> SP verifies XMLDSig with trusted IdP signing cert
       -> SP checks Audience, Recipient, Issuer, time, request,
          conditions/replay before creating Authentication
~~~

All three steps are distinct:

1. **TLS transport trust** protects the metadata connection.
2. **Metadata/federation trust** decides whether the metadata content and signing certificate belong to the right IdP permitted by the SP.
3. **SAML message trust** verifies the Response/Assertion against trusted signing material and semantic validation.

A valid HTTPS metadata URL that **points to the wrong IdP tenant** can still supply another party's key. If the SP accepts replacing any certificate purely from a user-supplied URL, there is a risk of **trust substitution**. Thus metadata URLs and issuers must be configured/approved; if metadata is signed, verify only with a **known metadata trust anchor**.

**Incident example:** The IdP replaces the TLS cert of `idp.example.org` with one from a valid public CA. The SP can continue SAML logins **without changing the SAML verification credential**, provided the IdP still signs with the same SAML key. Conversely, if the IdP rotates its **SAML signing key** while the IdP website's TLS certificate stays unchanged: HTTPS still works, yet an SP holding the old signing cert will reject SAMLResponses.

## 8. Configuration in Spring Boot: what belongs to HTTPS, what belongs to SAML?

### 8.1. HTTPS terminating directly at Spring Boot

With modern Spring Boot, you can configure an **SSL bundle** containing the server TLS cert + private key (illustrative; paths must exist and be protected):

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        portal-tls:
          keystore:
            certificate: "file:/run/secrets/tls/portal-fullchain.pem"
            private-key: "file:/run/secrets/tls/portal-key.pem"
server:
  ssl:
    bundle: "portal-tls"
~~~

This is **embedded web server HTTPS configuration**; the certificate must be valid for the public hostname accessed by clients, with proper chain/trust/algorithms. If TLS terminates at ingress, **you typically configure the TLS keypair at ingress**, not in Spring Boot. Depending on Spring Boot version, you can also use `server.ssl.key-store` and `server.ssl.key-store-password` with PKCS#12.

**Do not confuse:** Providing `server.ssl.bundle=portal-tls` **does not** cause Spring Security to trust the IdP's SAML signatures; it only affects the web server's TLS channel.

### 8.2. Separate SAML verification, signing, and decryption

Example for a Spring Security Servlet application with a trust-verified IdP. This is an **illustrative** configuration showing the different key roles, without real private keys:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://portal.example.org/login/saml2/sso/corporate"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing-key.pem"
                  certificate-location: "file:/run/secrets/saml/sp-signing-cert.pem"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decrypt-key.pem"
                  certificate-location: "file:/run/secrets/saml/sp-decrypt-cert.pem"
            assertingparty:
              entity-id: "https://idp.example.org/entity"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing-cert.pem"
~~~

**Reading each branch:**

- `assertingparty.verification.credentials` holds the **public IdP SAML signing certificate**, used to verify incoming XML signatures. **Does not contain the IdP private key**.
- `signing.credentials` holds the **SP private key + SP certificate** to sign requests/logout when required by the IdP. The IdP must be given the matching public signing cert.
- `decryption.credentials` holds the **SP private key + SP certificate** to decrypt EncryptedAssertions. The IdP encrypts using the SP public encryption cert.
- `assertingparty.entity-id` and `singlesignon.url` are not TLS certificate names; they identify the **IdP issuer and SSO endpoint**.
- `entity-id` and `acs.location` are the SP's identity/endpoint; the HTTPS scheme in ACS does not make the ACS cert a SAML verification cert.

**Version compatibility:** The properties above reflect the common structure in Spring Boot 3.x/corresponding branches. When using Spring Boot 4/Spring Security 7, check `Saml2RelyingPartyProperties`, APIs, and field names of the locked version; do not copy YAML if a property was renamed or removed. If the IdP provides a trusted metadata URL, you can load issuer/SSO/signing cert via `assertingparty.metadata-uri` instead of manual entry while configuring SP private keys independently.

You must **merge** the TLS and SAML YAML groups under the appropriate branches in the same file if one app uses both; the snippets above are two standalone blocks for explanation. Avoid creating two duplicate `spring:` root nodes in the same YAML where the parser only retains one.

### 8.3. Java Spring Security SecurityFilterChain

File `src/main/java/com/example/portal/PortalSecurityApplication.java` for a **Spring Boot Servlet project** (web, security, SAML2 service provider dependencies):

~~~java
package com.example.portal;

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
public class PortalSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortalSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SP ready";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

The code is a Java class with complete import syntax, **not runnable with bare `javac`** because it requires the Spring Boot/Security classpath and an IdP with the SP registered. In a Maven project with Maven Wrapper and compatible dependencies:

~~~bash
./mvnw spring-boot:run
~~~

Once the application/SSL bundle/IdP are all configured and the server runs, `GET /` returns body `SP ready`. `GET /private` requires a valid SAML login to return `Authenticated`. This lesson does not promise specific stdout or redirect URLs since those depend on IdP/tenant, binding, network, and cookies/sessions.

### 8.4. Maven dependencies for SAML

The following snippet belongs inside `<dependencies>` of a Spring Boot project with parent/BOM; **it is not a full pom.xml**:

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

If the OpenSAML repository or dependency version has specific requirements, follow the corresponding Spring Security guide. Do not mix Spring Security 6 with documentation intended for 7 without verifying compilation and integration tests.

## 9. How Spring Security represents credential purposes

Spring Security provides `Saml2X509Credential` with **credential types**. Key factory methods:

| Factory / API | Input | Role |
|---|---|---|
| `Saml2X509Credential.verification(X509Certificate)` | Public certificate | Verify another party's SAML signature |
| `Saml2X509Credential.signing(PrivateKey, X509Certificate)` | Private key + certificate | Sign SAML messages issued by us |
| `Saml2X509Credential.decryption(PrivateKey, X509Certificate)` | Private key + certificate | Decrypt SAML content sent to us |
| `Saml2X509Credential.encryption(X509Certificate)` | Public certificate | Encrypt content sent to another party per role |
| `getCertificate()` | Public X509Certificate | Retrieve public cert |
| `getPrivateKey()` | Nullable | Present only for roles requiring a private key |
| `getCredentialTypes()` | Set of credential types | Check roles: verification, signing, decryption, or encryption |

The key point is that **credential purpose is declared explicitly**. Using the same `X509Certificate` type in Java does not turn an IdP verification credential into a server TLS certificate. `Saml2X509Credential` is a **SAML** API, not an HTTP server SSLContext configuration.

In `RelyingPartyRegistration`, IdP verification credentials belong to the **asserting party**; signing/decryption credentials belong to the **relying party**. For a SAMLResponse sent to the ACS, Spring Security/OpenSAML uses credentials from the matching registration to verify the IdP's signature. If an SP integrates with multiple IdPs, never use a single combined cert list for all tenants while dropping issuer/entityID trust binding.

### 9.1. Why KeyInfo is not enough to pick a trusted cert

An XML Signature may contain `ds:KeyInfo` or `ds:X509Certificate`. Yet if the browser sends the payload, an attacker can also embed **the attacker's certificate** and sign the XML with their own private key. Mathematically, the signature can verify against that public key; **that does not mean the SP trusts the signer**.

The SP must retrieve trusted certificates from **trusted registration/metadata** confirmed by an admin. Accepting a certificate presented inside the payload without trust verification is a critical authentication flaw.

## 10. Comparing security layers across incidents

| Symptom | TLS/HTTPS | SAML signature/trust | Diagnosis |
|---|---|---|---|
| Browser reports certificate hostname mismatch | **FAIL** | SAML key may still be valid | Fix TLS SAN/hostname/ingress; do not randomly swap IdP SAML cert |
| Browser reports untrusted CA cert | **FAIL** | Not directly related | Configure TLS certificate chain and trust anchor |
| IdP HTTPS works normally yet SP reports `Invalid Signature` | **PASS** | **FAIL** | Check IdP signing cert, metadata rotation, and XMLDSig |
| IdP rotates TLS cert while keeping SAML signing key | Can still PASS with new cert matching hostname | Usually still PASS | No need to change SAML cert just because TLS cert changed |
| IdP rotates SAML signing cert while keeping TLS cert | TLS still PASS | SP may FAIL if new key not yet trusted | Update SAML metadata/trusted signing keys before rollover |
| ACS HTTPS valid yet SAML Audience wrong | PASS | Signature may PASS | **FAIL SAML semantics**, fix SP entityID/Audience |
| SAML Response properly signed yet expired | TLS may PASS | Crypto signature PASS, conditions FAIL | Reject login |
| SAML Response carries new cert inside KeyInfo | Inconclusive | Not yet trusted | Never auto-trust client-supplied certs |
| TLS terminated at ingress | Browser ↔ ingress PASS | App must still verify SAML | SAML credentials are not inside the TLS bundle |
| `EncryptedAssertion` fails to decrypt | TLS may PASS | Encryption/decryption key mismatch | Check SP decryption key and IdP public encryption cert |
| SAML signed by self-signed cert safely pinned by SP | Unrelated to WebPKI TLS | Can PASS | Self-signed SAML cert is not inherently an error |
| IdP metadata HTTPS works yet points to wrong issuer | TLS PASS | Federation trust/issuer FAIL | Compare entityID and registration, not just URL |

**Debugging technique:** Identify whether failure occurs at **TLS handshake**, **metadata fetch**, **SAML XML Signature verification**, **SAML conditions**, or **application authorization**. Failures belong to five separate layers; replacing a TLS certificate cannot fix an `AudienceRestriction` error.

## 11. SAML signing certificate vs. encryption certificate: do not conflate them

For SAML signing:

~~~text
IdP private signing key --signs--> Response/Assertion XML
                    SP --uses IdP public verification cert--> verifies
~~~

For SAML encryption:

~~~text
IdP --uses SP public encryption cert--> EncryptedAssertion
                    SP --uses SP private decryption key--> decrypts
~~~

An encryption certificate is used for **confidentiality**; a signing certificate is used for **authenticity/integrity** of the XML document. Successful encryption **does not prove** the IdP issued the Assertion; you must still verify signatures and profile conditions. All of this still uses HTTPS for transport.

SAML metadata can use `KeyDescriptor use="signing"` and `use="encryption"` per entity, whereas a TLS cert appears in the hostname's TLS handshake. A file `sp-encryption.crt` used by the IdP to encrypt for the SP **is not** an IdP verification cert and is not the ACS TLS cert.

## 12. Different certificate lifetimes and rotation principles

### 12.1. HTTPS/TLS rotation

For example, when an IdP endpoint's TLS certificate is nearing expiration:

1. The IdP provisions a new TLS cert/chain with the right hostname SAN and compliant TLS policy.
2. Update the cert and private key on the web server or ingress/load balancer; check SNI, chain, cipher suites, and handshakes.
3. Ensure clients trust the new CA chain; monitor handshake errors from browsers and SP metadata fetches.
4. Can be automated with ACME/cert-manager or Spring Boot reloadable SSL bundles if supported by runtime/framework.
5. No need to change the IdP SAML signing key just because the TLS cert changed, unless the organization intentionally shares a key (requiring risk assessment).

TLS cert rotation is scoped to **hostname connections**. When multiple hosts/subdomains exist, verify SNI, SAN, and all relevant endpoints.

### 12.2. IdP SAML signing credential rotation

When the IdP rotates its signing key, all SPs trusting that IdP must prepare:

1. Generate a new SAML keypair inside the IdP/HSM; keep the private key secret.
2. Publish the **new public signing certificate** via metadata or a verified channel.
3. If supported, SPs simultaneously trust **old + new** signing certificates during the overlap phase; record issuer/registration and fingerprints.
4. Test SAML Responses signed with the new key in an authorized environment, covering both Response/Assertion signatures.
5. Once SPs are ready, the IdP switches to signing with the new key.
6. Monitor `Signature validation failed` and request/login failures; only remove the old key after rotation is confirmed complete and no valid messages depend on it.

**Important point:** TLS can remain completely healthy while a SAML key rollover fails. Public CA certificate lifetimes/mechanisms **do not** automatically update SP trust for SAML signing keys.

### 12.3. SP signing credential rotation

If the SP signs `AuthnRequest`:

1. Create a new SP signing keypair.
2. Register the new public cert at the IdP or update SP metadata so the IdP can trust it.
3. Check whether the IdP supports old/new overlap; do not switch the SP private key early before the IdP accepts it.
4. Switch the SP to sign requests with the new key, test SSO and logout flows if sharing the credential.
5. Remove the old public cert at the IdP after completion and once the transition window closes.

Do not confuse this with replacing the TLS cert for `portal.example.org`; the TLS cert can remain unchanged.

### 12.4. SP decryption credential rotation

If the IdP encrypts Assertions for the SP:

1. The SP generates a new decryption keypair and secures the private key with safe backup/DR.
2. Publish the new public encryption certificate to the IdP; confirm compatible algorithms/profiles.
3. Depending on the library, the SP may need to keep multiple private decryption keys while receiving assertions encrypted with the old cert.
4. The IdP switches to encrypting with the new cert on schedule; the SP verifies decryption and full signature/condition validation.
5. Only retire the old private key once all valid messages in the transition window have been processed.

**Do not** replace the SP decryption cert with a TLS cert in the IdP console unless **intentionally designed** to share one keypair permitted for both roles; normally that is an operational mistake.

### 12.5. General rules when tracking expiration

Track **three schedules** in parallel:
- Expiration and CA policy of **TLS certificates**.
- Expiration/cryptoperiod of **SAML signing keys/certs** for both IdP and SP.
- Expiration/cryptoperiod of **SAML encryption/decryption keys/certs**.

A certificate with a distant `NotAfter` whose private key is suspected compromised or whose algorithm violates policy must still be rotated. Conversely, renewing a certificate using the **same public/private key** does not mean the private key was rotated; threat models and cryptoperiods must be governed separately.

## 13. Inspecting real certificates with OpenSSL, keytool, and curl

This section helps **identify which file you are holding and where it belongs**; it does not replace a certificate-path validator or SAML security provider.

### 13.1. Viewing public X.509 certificate details

~~~bash
openssl x509 -in idp-saml-signing.crt -noout -subject -issuer -serial -dates -fingerprint -sha256
~~~

The command reads a PEM cert file and displays Subject, Issuer, serial, dates, and SHA-256 fingerprint. **Output depends on the actual certificate**, with no fixed stdout. Record the fingerprint in federation records; this identifies a specific cert, not proof of IdP trust without an independent verification channel.

### 13.2. Inspecting SAN/KU/EKU to assess purpose

~~~bash
openssl x509 -in portal-tls.crt -noout -text
~~~

Look for `X509v3 Subject Alternative Name`, `X509v3 Key Usage`, `X509v3 Extended Key Usage`, validity, and public key algorithm. A TLS server certificate normally needs the hostname in SAN and EKU serverAuth if the extension is present. A SAML signing certificate is typically governed by metadata/federation trust; if IdP/SP policy checks KU/EKU, issue it appropriately (e.g., digitalSignature and appropriate EKU if required).

**Do not infer solely from CN/filename:** A certificate without a matching SAN **should not** be accepted as a public TLS certificate for a hostname. Yet lacking a DNS SAN in a SAML signing certificate is not automatically a SAML error if federation trust policy does not require that hostname.

### 13.3. Checking the TLS certificate presented by a server

~~~bash
openssl s_client -connect login.example.org:443 \
  -servername login.example.org \
  -verify_hostname login.example.org \
  -verify_return_error
~~~

The `-servername` flag sends SNI for the right vhost; `-verify_hostname` enforces hostname matching. Run in an environment/OpenSSL version supporting these options and an appropriate chain/trust store. This command checks the **TLS endpoint**, not SAML XML signatures. Lines like `Verify return code`/certificate chain depend on the real server, so there is no fixed sample output.

Another simple command to test browser/HTTP client access to a URL:

~~~bash
curl -vI https://login.example.org/
~~~

Curl displays TLS/HTTP details for the environment; an HTTP status of 200/302/404 for a given path **does not by itself determine** whether SAML login works. Avoid `curl -k`/`--insecure` in production checks because it disables TLS verification and hides certificate errors.

### 13.4. Inspecting PKCS#12/Java keystore

~~~bash
keytool -list -v -storetype PKCS12 -keystore portal-tls.p12
~~~

Java `keytool` can prompt for the password; never put passwords in command lines/logs/chats. The command reads subjects, aliases, chains, fingerprints, and key lengths. Verify the alias has the private key needed for TLS, but **never use that alias as a SAML signing credential** unless the role/key has been explicitly configured and approved.

### 13.5. Comparing public keys between private key and certificate

You can extract the SHA-256 fingerprint of SubjectPublicKeyInfo (SPKI) from the certificate:

~~~bash
openssl x509 -in sp-signing.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
~~~

And from the private key:

~~~bash
openssl pkey -in sp-signing.key -pubout -outform DER \
  | openssl dgst -sha256
~~~

Both SPKI digests **must match** if the public/private key form a pair and OpenSSL parses the format cleanly. This command only proves **keypair consistency**; it does not prove the certificate is trusted under SAML metadata or TLS hostname/CA trust.

**Warning:** Never print private keys, and never store passphrases in shell history via `-passin pass:secret`; for HSM/PKCS#11, use vendor tools/APIs and protect secret stores.

## 14. Standalone Java 17: inspecting X.509 without verifying trust

The program below reads a PEM/DER X.509 certificate file using the Java standard library and displays details for **certificate inventory**. It **does not** conclude whether a cert is trusted for TLS or SAML, as those require a trust store/hostname or trusted IdP registration.

File `CertificateInspector.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public class CertificateInspector {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertificateInspector <certificate.pem>");
            System.exit(2);
        }

        Path certificateFile = Path.of(args[0]);
        X509Certificate cert;

        try (InputStream input = Files.newInputStream(certificateFile)) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            cert = (X509Certificate) factory.generateCertificate(input);
        }

        byte[] fingerprint = MessageDigest.getInstance("SHA-256")
                .digest(cert.getEncoded());

        System.out.println("Subject: " + cert.getSubjectX500Principal());
        System.out.println("Issuer: " + cert.getIssuerX500Principal());
        System.out.println("NotBefore: " + cert.getNotBefore());
        System.out.println("NotAfter: " + cert.getNotAfter());
        System.out.println("PublicKey: " + cert.getPublicKey().getAlgorithm());
        System.out.println("FingerprintSHA256: "
                + HexFormat.of().withUpperCase().formatHex(fingerprint));
    }
}
~~~

Compile with **JDK 17 or later**:

~~~bash
javac CertificateInspector.java
java CertificateInspector idp-saml-signing.crt
java CertificateInspector portal-tls.crt
~~~

The program **compiles standalone** (Java 17 includes `HexFormat`) and runs when given a real X.509 file. Subject, Issuer, NotBefore/NotAfter, PublicKey, and SHA-256 fingerprint lines vary by input, so **there is no fixed stdout**. The program only performs inventory; it does not call `cert.checkValidity()` to reject or run a PKIX chain; even with `checkValidity()`, it cannot verify hostname, CA chain, federation issuer, or XML Signature.

**Never use this program as a SAML validator**: it does not parse Response/Assertion, compute XMLDSig Reference/digest, check IdP metadata trust, replay, or SAML conditions.

### 14.1. Role decision exercise in Java 17, fixed stdout

File `CertificateRoleDecisionDemo.java` models organizational logic: a cert file approved for TLS **is not automatically** approved as a SAML signing cert.

~~~java
public class CertificateRoleDecisionDemo {

    record CertificateApproval(
            String label,
            boolean tlsHostnameAndCaTrusted,
            boolean pinnedAsIdpSamlSigner) {
    }

    public static void main(String[] args) {
        CertificateApproval tls = new CertificateApproval(
                "IdP TLS", true, false);
        CertificateApproval saml = new CertificateApproval(
                "IdP SAML signing", false, true);

        System.out.println("TLS can serve HTTPS: "
                + tls.tlsHostnameAndCaTrusted());
        System.out.println("TLS can verify SAML: "
                + tls.pinnedAsIdpSamlSigner());
        System.out.println("SAML key can verify SAML: "
                + saml.pinnedAsIdpSamlSigner());
        System.out.println("SAML key can serve public HTTPS: "
                + saml.tlsHostnameAndCaTrusted());
    }
}
~~~

Run:

~~~bash
javac CertificateRoleDecisionDemo.java
java CertificateRoleDecisionDemo
~~~

**Exact stdout:**

~~~text
TLS can serve HTTPS: true
TLS can verify SAML: false
SAML key can verify SAML: true
SAML key can serve public HTTPS: false
~~~

**Explanation:** The boolean values are **assumed trust decisions** for learning the two roles, not results the program verified from a certificate. If anyone could set `pinnedAsIdpSamlSigner=true` from untrusted input, the exercise would no longer be safe. In production, Spring Security must enforce trust from `RelyingPartyRegistration` and signature validation; TLS uses the TLS stack's certificate path/hostname validation.

## 15. KeyUsage, EKU, algorithm, and expiration: similarities and differences

### 15.1. Key Usage / Extended Key Usage

**TLS server certificates** are typically issued under CA/Browser Forum and WebPKI profiles, with matching hostname SAN, EKU serverAuth, and appropriate KU/algorithms. Dedicated certificates for **SAML XML signing** should follow a policy designating the digital signature role; they do not necessarily need DNS SAN/serverAuth if not used as TLS server certs. SAML KU/EKU policy depends on IdP/SP software and organizational rules.

**Never use "certificate has KU digitalSignature" as proof of trust**: anyone can create a self-signed certificate carrying that extension. You must verify **which IdP issued/published the certificate and through which channel the SP trusted it**.

### 15.2. Certificate signature algorithm differs from XML signing algorithm

There are two separate algorithm choices:

- **Certificate's signature algorithm:** e.g., the CA signs the X.509 certificate using SHA-256 with RSA.
- **XMLDSig SignatureMethod/DigestMethod:** e.g., the IdP signs the SAML Assertion with the corresponding XML Signature algorithm. The URIs inside the XML govern how SAML digests/signatures are verified, not inferred from the certificate issuer signature.

Do not assume a cert with a SHA-256 signature means the XML Signature used SHA-256. The SP must enforce an **algorithm allowlist** for XMLDSig, blocking legacy algorithms like RSA-SHA1/SHA1 digest per security policy. Prefer RSA 2048+/SHA-256 or stronger and EC algorithms if supported by both IdP/SP; product compatibility must be tested before switching algorithms.

### 15.3. Cert validity does not replace SAML time checks

An X.509 cert with an unexpired `NotAfter` **does not mean** the SAML Assertion is unexpired. SAML uses `Conditions.NotBefore/NotOnOrAfter`, `SubjectConfirmationData.NotOnOrAfter`, and profile-specific constraints. Conversely, an unexpired Assertion whose signing cert is no longer trusted by the SP or whose key usage policy has ended must still be rejected per trust/security policy.

Do not extend SAML assertion validity simply because the signing certificate is valid for 3 years. Web session duration, assertion conditions, signing key lifecycle, and TLS handshake lifetime are four **distinct** lifetimes.

## 16. Deployment case: IdP metadata HTTPS OK yet SAML login FAILS

**Assumed state:**

- SP: `https://portal.example.org`, Spring Boot Servlet with `saml2Login`.
- IdP: `https://login.example.org` and metadata at `https://login.example.org/metadata`.
- SP's HTTP client fetches metadata successfully over HTTPS; browser opens IdP without TLS warnings.
- Browser completes MFA yet SP returns a signature validation error.

**What not to do:** Replace the TLS certificate at the SP's ingress or disable SAML signature validation, as no evidence points there as the cause.

**Correct procedure:**

1. Retrieve the SAML provider layer error log: is the Response signature or Assertion signature invalid?
2. Verify `RelyingPartyRegistration` resolves the right `registrationId` and IdP entityID/Issuer.
3. Check the IdP public signing certificate in metadata trusted by the SP: fingerprint, old/new rollover, right tenant, not confused with `login.example.org`'s TLS cert.
4. Check XMLDSig signer, SignatureMethod/DigestMethod/Reference, and whether the Response/Assertion was altered passing through a proxy/browser.
5. Check whether the signature is valid yet rejected on **Audience, Recipient, Destination, time, InResponseTo, or replay**; logs distinguish cryptographic errors from semantic errors.
6. If the IdP just rotated its SAML signing key, update metadata/credentials with verification and test the new key in a suitable environment.
7. Re-run positive/negative tests with test IdP and browser; ensure certs carried inside payload KeyInfo are never accepted.

**Conclusion:** TLS PASS only says the HTTPS endpoint works; SAML signature FAIL points to federation trust or XML signature failure. The two issues are not identical.

## 17. Converse case: SAML key is right yet HTTPS fails

Suppose the SP still holds a valid IdP signing cert per the trust registry, yet the browser shows a warning:

~~~text
ERR_CERT_COMMON_NAME_INVALID
or hostname mismatch / unknown CA error
~~~

Those errors normally belong to **TLS hostname verification/CA chain**, not the Response signing credential. You cannot use SAML metadata to prove the browser must trust a TLS server cert.

Troubleshooting steps:

1. Check the public hostname, DNS, SNI, and cert chain presented by ingress/IdP.
2. Compare SAN against the hostname accessed by the browser/HTTP client; if using a private CA, distribute the trust anchor per policy.
3. Check cert validity, OCSP/revocation/CT, and TLS config if required by the platform.
4. For applications fetching metadata via a Java HTTP client, inspect the JVM truststore or SSL bundle of the **HTTP client in use**; never set `trustAll`.
5. Once TLS is fixed, **SAML signature/trust must still be verified separately** before login.

**Caution:** SP HTTPS and IdP HTTPS are two different ends. An expired SP TLS certificate affects browser access to ACS/portal; an expired IdP TLS cert affects the SSO page and possibly metadata fetching. Both remain distinct from SAML signing certs.

## 18. Security checklist for code review and operations

### 18.1. HTTPS/TLS checklist

- [ ] DNS/SAN matches the real hostname in the browser/HTTP client, including SNI and ingress routing.
- [ ] Certificate chain and trust anchor are valid; never skip hostname validation or use `trust-all`.
- [ ] Secure TLS 1.3/1.2 and allowed ciphers; private keys at TLS termination are protected.
- [ ] Monitor `notAfter`, automate renewal where appropriate, and control cert rollout and rollback.
- [ ] IdP metadata URL is fetched over HTTPS with exact hostname from an approved source.
- [ ] If a reverse proxy terminates TLS, external ACS/metadata URLs remain HTTPS and forwarded headers are properly trusted.
- [ ] Never use `curl -k` or disable JVM certificate validation to "fix" prod errors.

### 18.2. SAML signing checklist

- [ ] SP is configured with the **IdP verification public certificate** matching the exact IdP entityID/registration.
- [ ] Trusted signing cert is taken from approved metadata/channel, never from untrusted `KeyInfo`.
- [ ] XML Signature protects the **exact Response/Assertion consumed**, defending against duplicate IDs and XML Signature Wrapping.
- [ ] XML signature algorithms/digests comply with policy; weak algorithms are disallowed.
- [ ] Checks SAML issuer, audience, recipient, destination, validity window, `InResponseTo` where applicable, and replay.
- [ ] Do not confuse Response-signed with Assertion-signed; validate fully per profile/policy.
- [ ] If SP signs `AuthnRequest`, IdP holds the **SP public signing cert** matching the SP private key.
- [ ] If IdP encrypts Assertions, IdP holds the **SP public encryption cert** and SP holds the **matching decryption private key**.
- [ ] Have a key/cert rotation plan, trust overlap, documented fingerprints, and mutual sign-off.
- [ ] Never log raw SAML Responses, attributes/PII, or private keys to public logs.

### 18.3. Responsibility matrix

| Task | Typical owner | Acceptance evidence |
|---|---|---|
| Renew IdP TLS cert | IdP infrastructure/web team | Browser/s_client HTTPS matches SAN/CA |
| Renew SP TLS cert | App/infrastructure/ingress team | ACS/portal HTTPS matches hostname |
| Rotate IdP SAML signing key | IdP security/federation team | SP verifies Response/Assertion with new cert |
| Update trusted IdP cert on SP | App/Spring Security team | IdP entityID + fingerprint + login test |
| Rotate SP SAML signing key | App security team and IdP admin | IdP verifies new AuthnRequest |
| Rotate SP encryption key | App security team and IdP admin | EncryptedAssertion decrypts successfully |
| Change SAML metadata URL | Both sides review trust/tenant | Metadata matches issuer/cert, SAML login succeeds |
| Update HTTPS Java truststore | SP infrastructure/HTTP client team | Metadata HTTPS fetch OK, no `trustAll` |

## 19. Testing: outcomes must be independent

| Test | Scenario | Expected |
|---|---|---|
| T1 | IdP TLS cert valid, SAML signing cert right | HTTPS PASS; SAML can PASS when conditions are met |
| T2 | IdP TLS cert valid, IdP SAML signing cert wrong | HTTPS PASS; SAML **FAIL** |
| T3 | IdP TLS cert wrong hostname, SAML signing key right | HTTPS client **FAIL**; must not bypass TLS |
| T4 | SP ingress rotates TLS keypair, IdP signing key unchanged | HTTPS stays PASS if configured right; SAML trust usually unchanged |
| T5 | IdP rotates SAML key, SP does not yet trust new public key | HTTPS may PASS; SAML **FAIL** |
| T6 | Self-signed IdP signing cert verified and trusted by SP | SAML signature can PASS, no public WebPKI CA required |
| T7 | Browser sends XMLDSig with attacker certificate in KeyInfo | SAML **FAIL** because certificate is untrusted |
| T8 | SAML Response signature valid, Assertion wrong Audience | SAML **FAIL** due to semantic validation |
| T9 | EncryptedAssertion uses mismatched SP public cert | SP **FAIL decryption** even though HTTPS/signature may pass |
| T10 | SP AuthnRequest requires signature yet IdP lacks SP public cert | IdP **FAIL request signature** |
| T11 | TLS and SAML both PASS yet user lacks business permission | App **403** for restricted resource |
| T12 | Update new SAML cert on SP, TLS cert unchanged | HTTPS independent; SAML PASS after trusted rollover |

Do not test only the **happy path**. Actively test wrong IdP/cert, hostname errors, wrong issuer, untrusted certificate, expired assertion, replay, altered XML, and signing-key rotation. The goal is to prove each protection layer **fails closed per its responsibility**, rather than one layer accidentally "masking" another's failure.

## 20. Review questions

1. **Must a SAML signing certificate be identical to the IdP's TLS certificate?** No. They serve two different roles/trust models; keypairs should usually be separated.
2. **Is a self-signed SAML cert inherently untrusted?** No. If the public key is trusted by the SP through verified metadata/federation channels, it can be used to verify SAML XML signatures.
3. **Is normal browser HTTPS access to the IdP enough for the SP to trust `SAMLResponse`?** Not yet. The SP must still verify the XML Signature with the trusted IdP signing key and all SAML conditions.
4. **When the IdP changes its TLS certificate, must the SP change its SAML verification cert?** Not automatically; only update SAML trust if the signing key/metadata trust actually changed.
5. **When the IdP changes its SAML signing certificate while TLS stays unchanged, can login fail?** Yes. An SP holding the old trusted cert will fail to verify the new signature.
6. **What is the SP signing cert used for?** The IdP verifies signatures on SAML requests issued by the SP, not for browsers checking HTTPS.
7. **What is the SP encryption cert used for?** The IdP encrypts assertions with the SP public key, and the SP decrypts with its private decryption key.
8. **Can a cert inside `ds:KeyInfo` be trusted immediately?** No. Credentials must come from verified IdP registration/metadata.
9. **Does `server.ssl.bundle` make Spring Security automatically trust the IdP SAML signing cert?** No. It configures the TLS server, not SAML verification credentials.
10. **Is the IdP entityID the DNS SAN of the TLS cert?** No. EntityID is a logical identifier in SAML, which can be a URI/URN.
11. **Why is checking a certificate's SHA-256 fingerprint not enough?** A fingerprint only identifies the cert bytes. You must know from which source that fingerprint was verified and which role/issuer it belongs to.
12. **Does an unexpired TLS certificate mean the Assertion is unexpired?** No. Assertions have their own `Conditions/SubjectConfirmationData` lifetimes.
13. **For `Signature validation failed`, which certificate should be fixed first?** Check SAML IdP signing verification credentials/issuer/trust first; only examine TLS if an actual handshake/metadata-fetch error exists.
14. **If TLS is at ingress, can Spring omit `server.ssl.*`?** Yes. Yet it must still verify SAML using the separate IdP verification cert.
15. **Can one key pair serve two purposes?** Technically sometimes possible, yet security/interop policies usually prefer separation; never infer reuse from certificates sharing a format.

## 21. Official documentation and authoritative references

- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Metadata/registration: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security JavaDoc – Saml2X509Credential and credential types: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot – SSL Bundles/HTTPS: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – SAML Relying Party properties: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OWASP – SAML Security Cheat Sheet, X.509 Certificate Considerations: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OWASP – Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- OASIS SAML 2.0 Metadata Specification: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (XML Signature and Conditions): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- RFC 5280 – X.509 Public Key Infrastructure: https://www.rfc-editor.org/rfc/rfc5280
- RFC 6125 / RFC 9525 – TLS Service Identity and name checking: https://www.rfc-editor.org/rfc/rfc9525

**Summary:** HTTPS certificates authenticate the **endpoint/transport channel** via DNS/CA/trust store; SAML signing certificates authenticate the **XML message signature of a trusted registered IdP/SP** via metadata/verification credentials. SAML encryption adds another dedicated keypair. In Spring Security, `server.ssl.*` (or ingress) configuration **does not replace** `RelyingPartyRegistration.assertingParty.verificationCredentials`. For secure federation, independently verify TLS, metadata trust, SAML signatures, Assertion conditions, and authorization, and plan key rotation for every role.
