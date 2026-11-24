# Signing Certificates, Encryption Certificates, and KeyDescriptor Information in SAML 2.0

> **Context:** Spring Security – federation / SAML2 Metadata. This lesson focuses on how `<md:KeyDescriptor>` advertises keys used for signing and encryption; how to distinguish public certificates from private keys; how SPs and IdPs exchange metadata, configure Spring Security, verify signatures/decryption, rotate keys, and troubleshoot failures. Examples use Java 17+ and Spring Boot 3.5.x/Spring Security 6.x on the Servlet stack.

## 1. Objectives and Prerequisites

After completing this lesson, you will be able to:

1. Read `KeyDescriptor` inside `IDPSSODescriptor` and `SPSSODescriptor`, accurately understanding `use="signing"`, `use="encryption"`, and the case where `use` is omitted.
2. Identify the structure of `ds:KeyInfo`, `ds:X509Data/ds:X509Certificate`, `ds:KeyValue`, and `md:EncryptionMethod`, knowing that metadata publishes only **public key material**, never private keys.
3. Explain the four key flows: IdP **signs** → SP **verifies**; SP **signs** → IdP **verifies**; IdP **encrypts for SP** → SP **decrypts**; SP **encrypts for IdP** → IdP **decrypts** when required by protocol/integration.
4. Distinguish **SAML certificates**, **HTTPS/TLS certificates**, **signatures on metadata**, and **signatures on SAML Response/Assertion/AuthnRequest**.
5. Establish trust anchors properly using approved metadata/registrations, understanding the limits of CA, certificate expiration, and fingerprint checks.
6. Configure `signing`, `decryption`, and `assertingparty.verification` in Spring Boot or `Saml2X509Credential` in Spring Security with the right roles.
7. Design rotation procedures for signing/decryption certificates with overlap windows, cache/metadata refresh, and negative tests without causing mass login outages.
8. Diagnose wrong certificates, wrong key usages, entity ID/ACS mismatches, signature/decryption failures, and proxy issues.

**Recommended background:** SAML Web Browser SSO, `EntityDescriptor`, SP entity ID, IdP entity ID, `SingleSignOnService`, ACS, XML namespaces, public-key digital signatures, and basic Java/Spring Security. If you are unsure about public vs. private keys, clarify that first: **the signing party holds the private key; the receiving party uses a trusted public key to verify**.

## 2. Metadata Sets the Context; KeyDescriptor Publishes Keys

SAML metadata is XML describing **SAML entities** and their roles. An entity may be an IdP, an SP, or serve multiple roles simultaneously. In metadata, `<md:EntityDescriptor entityID="...">` identifies the entity, `<md:IDPSSODescriptor>` describes the IdP role, and `<md:SPSSODescriptor>` describes the SP role.

`<md:KeyDescriptor>` is the element describing keys of **the entity/role owning that metadata** and their intended purpose. It normally sits under the role descriptor alongside SSO/ACS endpoints, logout info, NameIDFormat, and other attributes. An IdP may advertise multiple signing keys; an SP may likewise advertise separate signing and encryption keys.

~~~text
EntityDescriptor (entityID = https://idp.example.org/metadata)
  └─ IDPSSODescriptor
       ├─ KeyDescriptor use="signing"
       │    └─ ds:KeyInfo → IdP's public signing key/certificate
       ├─ KeyDescriptor use="encryption" (when needed)
       │    └─ ds:KeyInfo → IdP's public encryption key/certificate
       ├─ SingleSignOnService
       └─ SingleLogoutService (if present)

EntityDescriptor (entityID = https://portal.example.org/sp)
  └─ SPSSODescriptor
       ├─ KeyDescriptor use="signing" (when SP signs requests/logout)
       │    └─ ds:KeyInfo → SP's public signing key/certificate
       ├─ KeyDescriptor use="encryption" (when SP receives encrypted data)
       │    └─ ds:KeyInfo → SP's public encryption key/certificate
       └─ AssertionConsumerService (ACS)
~~~

**Key point:** Seeing **IdP metadata + signing certificate** usually means the public key the **SP** needs to verify messages signed by the IdP. Seeing **SP metadata + encryption certificate** usually means the public key the **IdP** uses to encrypt Assertions/NameIDs/Attributes sent to the SP. The party publishing a certificate never sends its private key to the other party.

Metadata may be distributed over an HTTPS URL or XML file, yet **having metadata alone is not enough to trust it**: the SP must know that the source belongs to an approved IdP, which entity ID is acceptable, and how metadata is authenticated/distributed per policy. A certificate inserted into an untrusted XML document does not grant itself authority to sign SAML on the IdP's behalf.

## 3. Standard Structure of `KeyDescriptorType`

Element model per SAML 2.0 Metadata:

~~~text
md:KeyDescriptor
  @use = "signing" | "encryption" | [omitted]
  ds:KeyInfo                         (required by schema)
    ds:KeyValue or ds:X509Data/ds:X509Certificate ...
  md:EncryptionMethod                (optional, 0 or more)
~~~

| Component | Role | Warning |
| --- | --- | --- |
| `md:KeyDescriptor` | Describes a key for an SP/IdP role in metadata | Never contains a private key |
| `use="signing"` | Key used for signature verification or partner authentication per role/profile | Does not imply the key can be used for decryption |
| `use="encryption"` | Public key usable to encrypt data sent to this entity | Does not mean the sender possesses the private key |
| `use` omitted | Per spec, the key may apply to **both signing and encryption** | Must still align with allowed algorithms/profiles and cryptographic policies |
| `ds:KeyInfo` | Container representing a public key/key identifier per XML Signature | Can contain various info; not an independent "trust badge" |
| `ds:X509Data/ds:X509Certificate` | Contains a DER-encoded X.509 certificate encoded in Base64 | Content is a **public certificate**, without PEM headers |
| `ds:KeyValue` | Directly represents the public key in XML | Not all libraries/integrations support the same key formats |
| `ds:KeyName` | Hint/label identifying a key | Contains no key material on its own; never trust solely on matching name |
| `md:EncryptionMethod` | Describes supported encryption algorithms when declared in metadata | Must verify real compatibility and cryptographic policy |

`KeyDescriptor` may appear **multiple times** under the same `RoleDescriptor` to support rollover or distinct uses. Not every SAML message is signed with a single static key, and not every Assertion is encrypted. What matters is knowing **which keys are authorized** for **which partner** and **which purpose** when a message is processed.

### 3.1. Sample XML on the `use` Attribute

This XML excerpt illustrates **how KeyDescriptor and KeyName are declared**; `KeyName` alone carries no public key and is **insufficient for integration or signature verification**. Production metadata needs `KeyInfo` with a real public key/certificate supplied from a trusted source.

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/metadata">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:KeyName>idp-signing-2026</ds:KeyName>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:KeyDescriptor use="encryption">
      <ds:KeyInfo>
        <ds:KeyName>idp-encryption-2026</ds:KeyName>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

The **common production structure** instead of or alongside `ds:KeyName` is:

~~~text
md:KeyDescriptor use="signing"
  ds:KeyInfo
    ds:X509Data
      ds:X509Certificate
        [Base64 of DER-encoded X.509 certificate published by IdP]
~~~

The brackets above only denote where **actual certificate data** goes in the XML tree, not a valid string to paste into metadata. Certificates are commonly stored separately in PEM format:

~~~text
-----BEGIN CERTIFICATE-----
... Base64 DER data ...
-----END CERTIFICATE-----
~~~

Inside `ds:X509Certificate`, the content is Base64 of DER; **do not include** `-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----` lines inside the XML element. When copying the certificate into PEM config/secret files, PEM format normally has headers.

### 3.2. Decision Table When `use` Is Omitted or Metadata Has Multiple Keys

| Metadata for a role | Specification interpretation | Safe operational practice |
| --- | --- | --- |
| One `KeyDescriptor use="signing"` | Public key for signing/signature verification | Use only under that role's verification policy |
| One `KeyDescriptor use="encryption"` | Public key for encrypting data sent to that role | Do not use as a signing key just because it is RSA |
| One `KeyDescriptor` without `use` | Key may apply to both signing and encryption | Still respect allowed algorithms/profiles and organizational policy |
| Two `KeyDescriptor use="signing"` | Both public keys may be valid, common during key rotation | Support overlap; do not rigidly pick "the first cert" |
| Two encryption certs | Both public keys may be published for transition | Agree with the sender on which key to encrypt with and keep the receiving private key active |
| Metadata publishes new signing key while app trusts only old key | New signatures may be rejected | Sync metadata/registration before the IdP switches signers |
| Certificate has `KeyName` differing from SAML Response | Name is only a hint, never overrides trust decisions | Verify with trusted public keys and matching issuer |

**Limitation:** Do not infer that an application **must** use both signing and encryption merely because `use` is omitted. Metadata describes capabilities; the SSO profile, federation agreement, crypto policy, and implementation determine what actually happens.

## 4. Four Key Directions: Sign/Verify and Encrypt/Decrypt

| Action | Who holds the **private key**? | Who receives the **public key/certificate** from metadata? | Example messages |
| --- | --- | --- | --- |
| IdP signs login result | **IdP** | **SP** uses IdP signing cert to verify | `SAML Response` or `Assertion` |
| SP signs request/logout | **SP** | **IdP** uses SP signing cert to verify | `AuthnRequest`, `LogoutRequest` / `LogoutResponse` if required |
| IdP encrypts data for SP | **SP** holds decryption private key | **IdP** uses SP encryption cert | `EncryptedAssertion`, `EncryptedID`, `EncryptedAttribute` |
| SP encrypts data for IdP | **IdP** holds decryption private key | **SP** uses IdP encryption cert | Messages/elements sent to IdP if profile/system supports it |

### 4.1. Flow: IdP Signs, SP Verifies

~~~text
IdP                                               SP
   signing PRIVATE key
          |
          +-- signs Response or Assertion ------------>
                                  |
                       SP retrieves verifying PUBLIC key
                       from trusted IdP metadata
                                  |
                       verifies XML Signature
                       + Issuer/entity ID
                       + Destination/Recipient
                       + AudienceRestriction
                       + timestamps / correlation
                       + replay protections
                                  |
                       then creates Authentication
~~~

Never skip verification because HTTPS encrypts the transport. The browser carries the message and can tamper with it. Having an RSA/ECDSA signature match **some** public key is insufficient: that public key must belong to the exact **IdP entity ID/registration** the SP is permitted to trust.

The signature may sit on `Response`, `Assertion`, or both depending on profile/IdP. Validation must verify the exact signed element and its binding to the data consumed afterward to prevent XML Signature Wrapping. Let Spring Security/OpenSAML verify instead of running custom XPath queries and an isolated signature check.

### 4.2. Flow: SP Signs, IdP Verifies

~~~text
SP                                              IdP
   signing PRIVATE key
          |
          +-- signs AuthnRequest/Logout message ------>
                                   |
                       IdP retrieves verifying PUBLIC key
                       from registered SP metadata
                                   |
                       IdP checks signature, issuer,
                       SP entity ID, ACS, policy
~~~

Depending on the binding, signing mechanics differ: **HTTP-Redirect** usually carries the signature in query parameters (`SigAlg`, `Signature`), whereas **HTTP-POST** may carry an XML Digital Signature. Both rely on the SP's signing credential, while canonicalization/message signing must be performed by a standard protocol library.

In metadata, `IDPSSODescriptor/@WantAuthnRequestsSigned` indicates the IdP expects signed AuthnRequests; `SPSSODescriptor/@AuthnRequestsSigned` indicates the SP issues signed AuthnRequests. These declarations must match runtime behavior. Do not add an SP signing cert and assume every request is automatically signed across all versions and IdPs: inspect network requests and IdP logs.

### 4.3. Flow: IdP Encrypts for SP

~~~text
IdP                                                SP
        SP's public ENCRYPTION cert
          |
          +-- encrypts payload with symmetric key ----->
          |   and protects symmetric key using
          |   public key/transport agreement
          |
                                     SP uses
                                     matching DECRYPTION private key
                                     to decrypt
                                     |
                                     then enforces full
                                     SAML policy
~~~

In SAML/XML Encryption, the IdP can encrypt the entire Assertion, NameID, or Attributes; typical structures are `EncryptedAssertion`, `EncryptedID`, `EncryptedAttribute` and XML Encryption elements such as `EncryptedData`/`EncryptedKey`. The receiver needs the **private key** matching the public certificate used by the sender, along with supported XML Encryption algorithms.

**Encryption is not a signature:** Anyone possessing the public encryption key can encrypt payloads to the SP; merely decrypting successfully does not prove the message was issued by the trusted IdP. You must still verify signatures and all SAML conditions before granting login. When a message is both signed and encrypted, decryption/verification order can depend on how XML elements are wrapped; let a standard library handle the context properly.

### 4.4. When the IdP Publishes an Encryption Certificate

A `KeyDescriptor use="encryption"` in **IdP metadata** represents the public key for others to encrypt messages **sent to the IdP** when supported by the profile. It is **not** the key the SP uses to decrypt received Assertions. If the SP must decrypt an encrypted assertion, the decryption private key must reside **at the SP** and the matching public certificate must be in the **SP metadata/registration** used by the IdP.

## 5. Distinguishing SAML Certificates from HTTPS/TLS Certificates

Both are X.509 certificates, yet their operational semantics differ.

| Aspect | SAML signing/encryption certificate | HTTPS/TLS server certificate |
| --- | --- | --- |
| Purpose | Supplies public key to verify XML Signatures or encrypt payloads | Authenticates TLS server and protects HTTP transport |
| Where referenced | `md:KeyDescriptor/ds:KeyInfo` or registration | TLS endpoint/reverse proxy, Web PKI/trust store |
| Trust criteria | Approved metadata/partner relationship and profile/config | Domain validation, CA chain/trust anchor, validity window, and TLS policy |
| Self-signed certificates | Can serve as a public key container in SAML metadata when properly trusted | Usually untrusted by browsers unless a private root is installed |
| Secret to protect | Private key of the signer or decryptor | Server's TLS private key |
| On rotation | Requires updating metadata, verifying/decryption credentials, and overlap | Requires updating TLS endpoint/CA chain and client trust |

In many SAML deployments, the X.509 certificate in metadata is simply a **public key container**, and trust derives from **authenticated metadata**. You cannot assume Spring Security automatically applies CA chains, OCSP, CRLs, or `NotAfter` dates the way HTTPS browsers do. Implementations and interop profiles apply different certificate policies, so confirm the actual policy in use.

**Avoid oversimplifying to "an expired cert always invalidates all SAML signatures":** In SAML metadata interop profiles, accepting a public key from metadata can be independent of traditional PKI validity windows; nevertheless, safe operations still require monitoring certificate dates, internal policies, and rotation schedules. Whether a library enforces certificate expiry automatically must be tested and verified in configuration. If a certificate's private key is compromised, revoke trust immediately per incident policy rather than waiting for `NotAfter`.

### Fingerprints Verify Identity, They Do Not Self-Establish Trust

A SHA-256 fingerprint of a DER certificate is useful to confirm that a received cert file matches what a partner provided over an **independent authenticated administrative channel**. A fingerprint does not prove ownership if both the metadata and the fingerprint come from the same unauthenticated source. In particular, an XML carrying a cert and an email carrying its fingerprint sent by the same attacker establish no trust relationship.

## 6. Metadata Signatures Differ from Message Signatures

An `EntityDescriptor` / `EntitiesDescriptor` document may be **signed at the metadata level**. This signature validates the integrity and distribution origin of the metadata when the consumer has an independently provisioned **metadata-signing trust anchor**. It differs from:

- **IdP signing certificate** inside `KeyDescriptor` used to verify `Assertion`/`Response`.
- **SP signing certificate** inside `KeyDescriptor` used by the IdP to verify `AuthnRequest`/logout.
- **TLS certificate** of the metadata distribution URL.
- **Encryption certificate** used to protect confidentiality of messages sent to a recipient.

When receiving metadata:

1. Identify the exact **source** (registered partner URL, approved file, signed metadata feed) and expected **entityID**.
2. If policy requires metadata signatures, verify using the **metadata signing** trust anchor; never immediately trust certificates inside the downloaded XML.
3. Verify metadata `validUntil` / `cacheDuration` per source policy, SSO/ACS endpoints, entityID, partner scope, and public key set; govern changes with approvals.
4. Only after approving the metadata should you load the signing cert into the SP's trust config or the public encryption cert into the sending system.
5. Never automatically fetch metadata URIs or cert URLs suggested by a `SAMLResponse` or web request; prevent SSRF and unintended expansion of trusted IdPs.

Valid signed metadata from a federation operator still requires checking **whether that specific partner is authorized by your application**. Trusting a document's signer does not automatically grant every entity in that document permission to authenticate every tenant.

## 7. Start with a Clear Partner Profile

Before editing Spring Security, agree on these parameters:

| Property | Provided/Defined by IdP | Provided/Defined by SP |
| --- | --- | --- |
| Entity ID | IdP entity ID in IdP metadata | SP entity ID in SP metadata |
| Endpoints | `SingleSignOnService`, optionally `SingleLogoutService` | `AssertionConsumerService` (ACS), optionally `SingleLogoutService` |
| Signing cert | Public certificate/key in **IdP metadata** | Public certificate/key in **SP metadata** if SP signs requests |
| Encryption cert | IdP public encryption cert if receiving ciphertext | SP public encryption cert if IdP encrypts for SP |
| Private keys | IdP retains its own signing/decryption private keys | SP retains its own signing/decryption private keys |
| Signing policy | Does IdP require signed AuthnRequests? algorithms/bindings? | Does SP require signed Response/Assertions? algorithms? |
| Encryption policy | Does IdP encrypt Assertions/Attributes/NameID? | Does SP have compatible private key, algorithms, and rotation? |
| Operations | Metadata update URL/cadence, key rotation schedule | Config reload, session/cache, security logging, and rollback |

**Example of a sound technical agreement:** IdP A publishes two signing certificates to prepare for rollover; SP "portal" uses both public keys to verify IdP signatures, while publishing an encryption certificate for IdP A. IdP encrypts Assertions with the SP's public key; the SP decrypts using the matching private key. If the SP does not sign AuthnRequests per policy, an SP signing certificate is not a prerequisite for reading Assertions from the IdP. Actual policies must be verified against the specific profile and IdP.

## 8. Spring Security: Credentials Have Distinct Purposes

Spring Security defines `Saml2X509Credential` representing an X.509 certificate and, depending on purpose, a private key; a `RelyingPartyRegistration` pairs SP configuration with an asserting party/IdP. Key credentials:

| API / Concept | Owning Side | What it does |
| --- | --- | --- |
| `Saml2X509Credential.verification(X509Certificate)` | **IdP's** public signing cert in asserting party config | SP verifies signatures on messages from the IdP |
| `Saml2X509Credential.signing(privateKey, certificate)` | **SP's** private key + certificate | SP signs requests/logout when required by config |
| `Saml2X509Credential.decryption(privateKey, certificate)` | **SP's** private key + certificate | SP decrypts encrypted Assertion/NameID/Attributes sent to SP |
| `Saml2X509Credential.encryption(certificate)` | **Receiving partner's** public encryption cert | Used to encrypt payloads sent to the recipient in supported flows |
| `RelyingPartyRegistration` | One IdP/SP pair with `registrationId` | Binds entity IDs, SSO/ACS, bindings, verifying/signing/decryption credentials |

**Never swap roles:** `assertingparty.verification` must hold the **IdP's** verifying cert; `registration.signing`/`registration.decryption` hold the **SP's** private key and certificate. Placing an IdP private key in the SP breaks the security model. Placing the SP's public encryption cert in the IdP verification field likewise makes no sense.

### 8.1. Spring Boot 3.5.x Example Configured from Metadata

This example is a **Servlet SP** with one partner `corporate`, using Spring Security for SAML login. URLs and secret paths are illustrative; login works only when real IdP metadata, valid keys/certs, registered SP entity ID/ACS, and compatible algorithms are in place. Private keys belong in files managed by a secret manager, never committed to Git.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-keys</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/sp-decryption.key
                  certificate-location: file:/run/secrets/sp-decryption.crt
~~~

**Configuration explanation:**

- `metadata-uri` reads metadata of the **approved IdP**. When metadata contains proper signing `KeyDescriptor` elements, Spring obtains the IdP's verification keys. Never take the URL from user requests.
- `signing.credentials` are the SP's private key and matching public cert, used when the SP must sign AuthnRequest/logout. This config section **never receives the IdP's signing cert**.
- `decryption.credentials` are the SP's private key and matching certificate, used when the IdP encrypts content sent to the SP. The SP's public certificate must be **published in SP metadata/registration** so the IdP selects the right encryption key.
- `file:/run/secrets/...` files are mounted into the container/service by a secret manager; to run on Windows or other environments, update to valid Resource paths, enforce file permissions, and secure backups. Missing/mismatched private keys and certs will cause startup or decryption failures.
- If the IdP **does not require** the SP to sign requests or **does not encrypt** Assertions, configuring both credential groups is not mandatory. The example includes both to clearly illustrate each purpose; enable only what your actual contract requires.
- SAML setup must also satisfy SP `entity-id` and ACS, whether library defaults or explicit overrides. Never guess production URLs when running behind a reverse proxy.

**`src/main/java/demo/SamlKeysApplication.java`:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlKeysApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlKeysApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/")
        String home() {
            return "SAML 2.0 signing and encryption demo";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                    "registrationId", principal.getRelyingPartyRegistrationId(),
                    "authenticated", "true");
        }
    }
}
~~~

In the project directory, run `mvn spring-boot:run`. With valid IdP metadata, certs/keys, and accurate registration, opening `http://localhost:8080/` returns the exact string **SAML 2.0 signing and encryption demo**. Opening `/me` starts SAML login and, upon completion, returns JSON with `registrationId` depending on configuration (here typically `corporate`) and `authenticated=true`. The default manual initiation path is typically `/saml2/authenticate/corporate`.

This demo app **does not manually encrypt or sign messages in Java code**: Spring Security/OpenSAML handles that per `RelyingPartyRegistration`, profile, and metadata. The demo reflects a single registration; testing all four key flows requires an IdP capable of issuing signed/encrypted responses and verifying signed AuthnRequests per configuration. Never use `/me` as the sole proof of proper validation; run negative tests as well.

### 8.2. When Not Using a Metadata URL

If your organization prohibits loading metadata at runtime, you can configure the IdP entity ID, SSO URL, and verification certificate from an approved file. The sample below is an **alternative** to `assertingparty.metadata-uri`, not something to merge into the example above:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: https://idp.example.org/saml
              sso-url: https://idp.example.org/sso
              verification:
                credentials:
                  - certificate-location: file:/run/secrets/idp-signing-2026.crt
~~~

This snippet specifies only **IdP-side verification**. Endpoints, logout bindings, SP signing/decryption, entity ID, and ACS must still be configured completely to match metadata and contract. Do not arbitrarily combine a `metadata-uri` from one source with manual certs without confirming exactly which verifying keys are selected.

### 8.3. `Saml2X509Credential` and Java Configuration

When dynamic configuration is needed, these factory methods have clear semantics:

~~~java
// API illustration snippet, placed in config code that has loaded valid cert/key.
Saml2X509Credential verifyIdp =
        Saml2X509Credential.verification(idpSigningCertificate);
Saml2X509Credential signAsSp =
        Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);
Saml2X509Credential decryptAsSp =
        Saml2X509Credential.decryption(spDecryptionPrivateKey, spDecryptionCertificate);
~~~

Input variables are provided by the application's secret/certificate loader; **this is a Java snippet, not a standalone runnable file**. In the builder API of the corresponding version, SP signing credentials belong to `RelyingPartyRegistration#signingX509Credentials`, SP decryption belongs to `decryptionX509Credentials`, and IdP verification belongs to asserting-party metadata/registration. When using the Spring Boot properties above, you do not need to write this conversion manually.

## 9. Java 17: Safely Inventorying KeyDescriptor and X.509 Fingerprints

The small utility below reads **a metadata file with root `EntityDescriptor`**, lists `KeyDescriptor` entries under `IDPSSODescriptor` or `SPSSODescriptor`, and prints the `use` purpose, SHA-256 fingerprint, subject, and certificate expiration. It uses only the Java 17 standard library, without Spring.

**This is an inventory tool, NOT a SAML metadata signature validator, and MUST NOT be used to make trust decisions.** It does not replace verifying metadata signatures, certificate sources, issuer/entityID, or runtime XML Signatures. The program disallows DTD/external entities to reduce XXE risk when reading files.

**File `InspectSamlKeys.java`:**

~~~java
import java.io.ByteArrayInputStream;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.HexFormat;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public class InspectSamlKeys {
    private static final String MD =
            "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String DS =
            "http://www.w3.org/2000/09/xmldsig#";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java InspectSamlKeys <metadata.xml>");
            System.exit(2);
        }

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities", false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document document = factory.newDocumentBuilder()
                .parse(Path.of(args[0]).toFile());
        Element root = document.getDocumentElement();
        if (!MD.equals(root.getNamespaceURI())
                || !"EntityDescriptor".equals(root.getLocalName())) {
            throw new IllegalArgumentException(
                    "Expected a single SAML EntityDescriptor");
        }

        System.out.println("entityID=" + root.getAttribute("entityID"));
        CertificateFactory certFactory =
                CertificateFactory.getInstance("X.509");
        for (String role : new String[] {
                "IDPSSODescriptor", "SPSSODescriptor"
        }) {
            NodeList roles = root.getElementsByTagNameNS(MD, role);
            for (int i = 0; i < roles.getLength(); i++) {
                Element roleElement = (Element) roles.item(i);
                NodeList keys = roleElement.getElementsByTagNameNS(
                        MD, "KeyDescriptor");
                for (int j = 0; j < keys.getLength(); j++) {
                    Element key = (Element) keys.item(j);
                    String use = key.getAttribute("use");
                    if (use.isBlank()) {
                        use = "both (use omitted)";
                    }
                    NodeList certificates = key.getElementsByTagNameNS(
                            DS, "X509Certificate");
                    if (certificates.getLength() == 0) {
                        System.out.println(
                                role + " use=" + use
                                + " certificate=not-present");
                    }
                    for (int k = 0; k < certificates.getLength(); k++) {
                        String base64 = certificates.item(k).getTextContent();
                        byte[] der = Base64.getMimeDecoder().decode(base64);
                        X509Certificate cert = (X509Certificate)
                                certFactory.generateCertificate(
                                    new ByteArrayInputStream(der));
                        byte[] sha256 = MessageDigest.getInstance("SHA-256")
                                .digest(cert.getEncoded());
                        System.out.println(role + " use=" + use);
                        System.out.println(
                                "SHA256=" + HexFormat.of().formatHex(sha256));
                        System.out.println(
                                "subject=" + cert.getSubjectX500Principal());
                        System.out.println(
                                "notAfter=" + cert.getNotAfter());
                    }
                }
            }
        }
    }
}
~~~

Compile/run on Java 17+:

~~~bash
javac InspectSamlKeys.java
java InspectSamlKeys idp-metadata.xml
~~~

**Output depends on real metadata**: the program prints `entityID`, role, `use`, SHA256 fingerprint, subject, and `notAfter` of each certificate (if present). Since no file or certificate is bundled in this lesson, there is no valid fixed stdout. If `KeyInfo` contains only `KeyValue` or `KeyName`, the tool prints `certificate=not-present`; that **does not prove metadata is invalid**, only reflects the tool's scope. If the file is an aggregated `EntitiesDescriptor`, the tool throws an error because it handles only single-entity metadata.

**Safety limits:** `getElementsByTagNameNS` only extracts XML contents; it does not verify metadata signatures, CA chains, or trusted issuers. Never treat the printed fingerprint as a reason to self-trust the data; compare it against the fingerprint confirmed by your partner over an independent channel. When handling multiple roles/entities or KeyInfo without X509Certificate, extend the inventory with dedicated tests and never silently skip keys in runtime deployments.

### Command to inspect a standalone certificate

If a partner provides a standalone X.509 certificate file, the JDK can display its details:

~~~bash
keytool -printcert -file idp-signing.crt
~~~

Output includes issuer/subject, serial, validity, and fingerprints depending on the certificate. Before applying it, compare the certificate against authenticated metadata rather than comparing filenames alone. `keytool` reads certificates without needing a private key; strictly avoid emailing private keys or pasting them into online tools.

## 10. Lifecycle Management: Signing and Decryption Key Rollover

Key rotation is a critical operational requirement that differs between **signing keys** and **decryption keys**. For signing, the message issuer must retain the ability to sign with the new private key while the receiver already holds the matching public key. For encryption, the **receiver** must retain decryption private keys for any ciphertexts that may still arrive or remain stored.

### 10.1. Rotating the IdP's Signing Key

1. IdP generates a new signing keypair, secures the private key in an HSM/KMS/secret store, and schedules the signing cutover.
2. IdP publishes the **new public signing certificate** in metadata alongside the old certificate, using the appropriate `KeyDescriptor use="signing"`.
3. SP updates or refreshes metadata/`RelyingPartyRegistration`, confirming it trusts both keys. If registrations are built statically at startup, know whether a restart/redeploy is required to pick up changes.
4. IdP switches its signer to the new private key on schedule; SP verifies using the matching public key.
5. Monitor signature errors, login rates, across SPs/tenants and instances; maintain an appropriate overlap window for in-flight messages and caches.
6. After all consumers have updated, old tokens/assertions have expired, and the old key is no longer needed, the IdP removes the old key/cert from metadata under change control.

**Never replace an old signing cert with a new cert instantaneously without coordination.** When the SP caches old metadata, messages signed with the new private key fail. Conversely, if the SP drops the old key too early, valid in-flight messages still within their lifetime can fail. The overlap schedule must account for Assertion lifetime, metadata cache/refresh, clock skew/latency, and each partner's policies.

### 10.2. Rotating the SP's Decryption Key

1. SP generates a new encryption/decryption keypair, storing the new public cert and private key in its secret store.
2. SP publishes the new encryption certificate in **SP metadata** for the IdP to prepare; confirm the IdP received the metadata.
3. SP loads **both old and new decryption private keys** if supported by the implementation, keeping the old key active during transition.
4. IdP switches to encrypting for the new public key once confirmed the SP can decrypt.
5. Test both ciphertexts: payloads encrypted with the old public key and the new key must both decrypt during overlap. Monitor `DecryptionException`, unknown key errors, and endpoint failures.
6. Once the sender no longer uses the old cert, old messages no longer need processing, and stored data has been migrated per policy, the SP removes the old private key and old metadata.

**Commonly overlooked point:** Metadata may contain multiple encryption certs while the IdP picks only one. Selection behavior is inconsistent across products; agree explicitly with the partner on which cert is active. If the SP rotates its private key while the IdP still encrypts with the old public key, the app cannot decrypt once the old key is deleted.

### 10.3. Handling Compromised Keys

If a signing private key is compromised, an attacker can forge messages carrying valid signatures within that scope; do not continue normal overlap just to avoid downtime. Immediately revoke trust in the compromised key, issue a replacement, assess session/user impact, coordinate with IdP/SP, update metadata, and log forensic data per incident response. If the SP decryption private key is compromised, confidentiality of payloads encrypted with that public key may be affected; rotate keys and assess data in transit/at rest per threat model.

## 11. Verification Layers Beyond `KeyDescriptor`

**A valid `KeyDescriptor` alone is never enough to accept a SAMLResponse.** The receiver must:

- Select the exact `RelyingPartyRegistration` from trusted context and check `Issuer`/IdP entity ID.
- Verify the appropriate signature on Response or Assertion using trusted signing verification credentials.
- Check `AudienceRestriction` targeting the exact SP entity ID, and `Destination` and `Recipient` matching the ACS.
- Check `NotBefore`, `NotOnOrAfter`, `InResponseTo` for SP-initiated requests, and replay protection policies.
- If encrypted, decrypt using the **correct SP decryption key**, then apply validation according to actual message/protection structure; never let decrypted data implicitly become a principal.
- Only afterward map NameID/attributes to a user and internal authorization policies.
- Monitor metadata `validUntil`, `cacheDuration`, trust sources, key rotation, clock skew, cert dates, and TLS proxies.

Prevent **XML Signature Wrapping**: never call "verify some signed element" and then read NameID from a separate unprotected XML element. Never write custom XML parsers/signature verifiers to replace Spring Security/OpenSAML; rely on up-to-date libraries.

## 12. Pre-Production Testing Matrix

| Case | Correct Behavior | Component Tested |
| --- | --- | --- |
| IdP A Response/Assertion signed by registered key | SP accepts when all conditions are valid | `IdP signing KeyDescriptor` and validator |
| Message signed by IdP B key claiming Issuer A | Rejected | Signer ↔ issuer ↔ registration binding |
| IdP A message signed by unpublished/unapproved key | Rejected | Trust anchor |
| Message modified after signing | Rejected | XML Digital Signature |
| Response carries embedded cert claiming to be IdP A | Do not auto-add key to trust store | Never trust keys from messages |
| SP publishes new public signing cert, IdP caches old cert | Newly signed AuthnRequests may fail until synced | SP signing rotation |
| IdP publishes both old and new signing certs, switches signer | SP continues verifying if updated properly | Multi-key verification |
| SP publishes new encryption cert, IdP still encrypts with old cert | SP can still decrypt during designed overlap | Multi-key decryption |
| IdP encrypts with public key not matching SP private key | Decryption fails; never skip encryption to allow login | Certificate/key pairing |
| Reading `KeyDescriptor use="encryption"` as verification cert | Never use for signature verification against policy | Credential usage |
| `KeyDescriptor` omits `use` | Interpret as both per spec and local policy | Metadata parsing |
| Metadata from unknown URL carries new cert | Never auto-accept entity/keys without approval | Trust bootstrap |
| Metadata signature invalid when required by policy | Reject trust update | Metadata signature validation |
| SAML Signature valid yet wrong audience | Rejected | SAML assertion conditions |
| SAML Signature valid yet expired/replayed | Rejected | Time/correlation/replay |
| Metadata endpoint HTTPS certificate changes | Handle via TLS trust; do not alter IdP signer unnecessarily | Separating TLS/SAML certificates |
| IdP metadata passes `validUntil` or fails to refresh | Alert/stop using per policy | Metadata lifecycle |
| SP lacks decryption private key when receiving EncryptedAssertion | Cannot log in; identify root cause accurately | Decryption credentials |
| User logs in yet lacks role | Denied resource with 403 | Authorization separate from authentication |

**Test in test environments** with simulated IdPs/SPs without interfering with production SSO flows. Never log full `SAMLResponse`, `EncryptedKey`, assertions, secrets, NameIDs, or session cookies. For deep troubleshooting, use selective logging with strict access controls.

## 13. Symptoms and Root-Cause Fixes

| Symptom | Common Cause | Check / Remediation |
| --- | --- | --- |
| `InvalidSignature` right after IdP rotates | SP caches old metadata, lacks new signing cert | Compare fingerprints in approved metadata vs. active key set; refresh/redeploy properly |
| `Signature validation failed` despite having cert | Wrong IdP entity ID/registration, signed element mismatch, unsupported alg | Check Issuer, trust config, XML signature placement, and signing algorithm policy |
| `DecryptionException` / cannot decrypt | IdP used public encryption cert not matching SP private key | Compare public cert in SP metadata with installed decryption private key; check rollover |
| IdP rejects signed AuthnRequest | SP signing cert unregistered, different binding, bad signature | Compare SP metadata and `WantAuthnRequestsSigned`, SigAlg/Signature or XML Signature |
| IdP demands signed request yet SP doesn't sign | SP lacks signing credentials / config | Configure SP signing private key + public cert, inspect outgoing request |
| SAMLResponse valid yet wrong Audience | Wrong SP entity ID or IdP registration | Align SP entity ID; never skip audience check |
| ACS mismatch behind proxy | Server sees internal HTTP or hostname | Configure forwarded headers from trusted proxy, HTTPS public URL, and IdP ACS |
| Certificate in metadata has past `NotAfter` | Missed rotation or unsynchronized policy | Check cert profile/policy, plan replacement and test; do not assume all libraries auto-fail |
| Metadata signed yet key untrusted | Metadata signing trust anchor unconfigured/unaccepted | Verify trust source through an independent channel |
| No `X509Certificate` found in KeyDescriptor | Metadata has only `KeyValue` or `KeyName` | Inspect KeyInfo structure and parser support; `KeyName` alone lacks key material |
| Login fails on only one instance | Inconsistent caches/credentials across nodes | Compare metadata versions, secret mounts, and deployment rollouts |
| New key works yet old key stays trusted forever | Rollover cleanup incomplete | Complete key rotation plan, remove compromised/retired keys on schedule |
| Signed logout request rejected | SLO keys/policy differ from login or SP cert out of sync | Check request/response signing and dedicated SLO config |

**Troubleshooting principle:** Never disable signature verification, drop audience/recipient/time checks, allow arbitrary certs from responses, or downgrade encryption requirements just to get a "successful login". Pinpoint the exact mismatched **entity + role + key purpose + timing + message**.

## 14. Checklist for Onboarding a New SAML Partner

- [ ] Verified IdP/SP entity IDs and metadata source via an approved administrative channel.
- [ ] Distinguished metadata signing trust anchor from IdP signing certificate used to verify Assertions.
- [ ] Inspected every `KeyDescriptor`, `use`, `KeyInfo`, certificate, and its intended purpose.
- [ ] Confirmed public/private key ownership; **never share private keys** with partners.
- [ ] Agreed on whether IdP signs Response or Assertion, and whether SP signs AuthnRequest/logout.
- [ ] Agreed on whether Assertions/NameID/Attributes are encrypted, supported algorithms, and SP decryption private key.
- [ ] Reconciled SP entity ID, ACS, bindings, HTTPS/proxy, and URLs published in metadata.
- [ ] Configured Spring Security `RelyingPartyRegistration` with verifying/signing/decryption credentials in the right roles.
- [ ] Tested unsigned/wrong-key/wrong-issuer/wrong-audience/expired/replayed/decryption-mismatch cases.
- [ ] Implemented rotation plans with old/new public keys and old/new private decryption keys where needed.
- [ ] Configured alerts/login failure monitoring, metadata refresh, certificate dates, and secret controls.
- [ ] Documented partner owner, key rotation schedule, change approval, fallback, and offboarding procedures.

## 15. Reinforcement Exercises

**Exercise 1 – Identify the four directions.** Given IdP A, SP B, and metadata containing `KeyDescriptor use="signing"` and `use="encryption"`, draw arrows showing who keeps the private key and who uses the public key when (i) IdP signs Response, (ii) SP signs AuthnRequest, (iii) IdP encrypts Assertion for SP, and (iv) SP encrypts a message to IdP. Compare against the table in Section 4.

**Exercise 2 – Inspect metadata.** Pick **test** metadata containing `IDPSSODescriptor` and at least one `ds:X509Certificate`. Identify the entity ID, KeyDescriptor count, each `use`, and fingerprints. Run `InspectSamlKeys.java`; compare the fingerprint via an authenticated admin channel. Explain why viewing a fingerprint **does not replace** metadata trust.

**Exercise 3 – IdP signing rollover.** IdP currently signs with A and wants to switch to B. Design a timeline publishing A+B, confirming all SPs have received B, switching the signer, monitoring logins, and retiring A. Predict errors that occur if an SP still caches A.

**Exercise 4 – SP decryption rollover.** IdP still encrypts with the old public cert after the SP rotated its private key. Explain the symptoms, how to support decrypting with both keys, and why the SP must not delete the old key too early during overlap.

**Exercise 5 – Spring Security.** Build the app from Section 8 with a test SAML IdP, store signing/decryption keys in secret files, and register SP metadata with the IdP. Test a validly signed Response; swap the verification certificate in staging to a different key and confirm login is rejected; restore the right key, test an encrypted assertion, and observe the mismatched private key case.

**Exercise 6 – Classify failures.** One SP receives a validly signed Response with the wrong `AudienceRestriction`; another SP successfully decrypts an EncryptedAssertion whose signature is invalid. Which of the two cases may be logged in? **Neither.** State the missing verification step and why encryption/decryption does not replace signature/trust validation.

**Mastery criteria:** you can explain KeyDescriptor/use/KeyInfo, distinguish the four key flows, read both IdP and SP metadata accurately, run the Java 17 tool, configure Spring SAML2 with credentials in the right roles, and describe signing/decryption rotation plus at least five fail-closed cases.

## 16. Authoritative References

- OASIS SAML 2.0 Metadata, `2.4.1.1 KeyDescriptor: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (Assertions, XML Encryption, Authentication): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML Metadata Interoperability Profile (trust management/rollover): https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-cd-01.html
- Spring Security – SAML 2.0 Login Overview / Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.x – Spring Security / SAML2 Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
