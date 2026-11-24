# Two-sided metadata synchronization before removing old keys in SAML 2.0

**Objective:** Rotate SAML 2.0 certificates/keys of an Identity Provider (IdP, or Asserting Party) or Service Provider (SP, or Relying Party) without breaking SSO logins, signature verification, assertion decryption, or Single Logout. To achieve this, the **issuer of the new key must publish appropriate metadata first**, the **consumer must load, verify, and prove it can use the new key**, and only then switch operations to the new key. **Remove the old key only when no party or message still needs it** and the process is approved. The exception is a compromised key, which requires emergency response rather than scheduled overlap.

This lesson belongs to **Spring Security – federation → Keys and certificates**. Focus is on **two-sided metadata synchronization**: IdP metadata read by the SP and SP metadata read by the IdP; actions before, during, and after key rotation; practical verification; Spring Security config; common failures; and rollback plans.

**Important reminder:** Rotating signing keys, rotating decryption keys, and updating HTTPS/TLS certificates are **three distinct workflows**. Never conclude "metadata contains the new cert" means all instances/partners have loaded it and are ready; you must verify and obtain operational confirmation.

## 1. Core problem: two sides hold two trust configurations

In SAML Web Browser SSO, the SP uses IdP details, while the IdP uses SP details. Metadata may live in XML at a URL, in deployed configuration files, or in a partner admin UI.

~~~text
  SP / Spring Security                               IdP / SSO
  --------------------                               ----------
  Holds IdP metadata                                 Holds SP metadata
  - IdP entityID                                     - SP entityID
  - IdP SSO/SLO URL                                  - SP ACS/SLO URL
  - IdP signing cert(s) <--------------------------  - SP signing cert(s)
  - encryption preferences                            - SP encryption cert(s)
            |                                                    |
            | (1) AuthnRequest signed with SP private key ------>
            |                                                    | verified with SP cert
            | <---------- (2) SAMLResponse signed with IdP private key
            | verified with IdP signing cert                      |
            | <---------- (3) EncryptedAssertion using SP pubkey
            | decrypted with SP private key                       |
~~~

Both parties may refresh metadata on different schedules: one fetches online every few hours, one imports manually, one caches across nodes, or one pins certificates until the next deployment. Therefore **replacing a key on the issuer and immediately deleting the old key** easily causes messages to be rejected.

Example: the IdP signs assertions with **I-old**; the SP currently knows only I-old. If the IdP switches to signing with **I-new** before the SP loads I-new, new SAML Responses can fail with `invalid signature`. Conversely, if the SP switches AuthnRequest signing to **S-new** before the IdP loads S-new, the IdP rejects AuthnRequests.

**Design principle:** The receiving side must know and trust the new key **before** the sending side starts using it.

## 2. Three key flows to distinguish

| Key type | Who owns the private key? | Who needs the public certificate? | Role |
| --- | --- | --- | --- |
| **IdP signing key** | IdP | SP | SP verifies SAML Response/Assertion signatures and certain SAML messages from IdP |
| **SP signing key** | SP | IdP | IdP verifies AuthnRequest, LogoutRequest, or SP-signed messages per policy |
| **SP decryption key** | SP | IdP uses SP's public encryption key | SP decrypts assertions/NameIDs encrypted by IdP for SP |
| **IdP decryption key** | IdP | SP uses IdP's public encryption key when needed | IdP decrypts elements encrypted by SP |
| **Metadata signing key/trust anchor** | Metadata signer or federation operator | Metadata consumer | Verifies origin and integrity of XML metadata per trust policy |
| **HTTPS/TLS key** | Web server or reverse proxy | TLS client | Protects transport channel; does not replace SAML message signatures |

An X.509 certificate can be configured for multiple purposes in some federations, yet never assume "signing certificate" equals "encryption certificate" or "TLS certificate". When rotating, identify **exactly which flow is affected**.

**Terminology:** In this lesson, I-old/I-new are the IdP signing key pairs, S-old/S-new are the SP signing key pairs, and E-old/E-new are the SP decryption key pairs. These are illustrative labels; in practice use SHA-256 fingerprints and specific metadata versions to identify keys.

## 3. Metadata KeyDescriptor: publishing keys and usage scope

In SAML metadata, `KeyDescriptor` binds public-key info to a SAML role. Abbreviated example for an IdP during overlap:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>BASE64_IDP_OLD_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>BASE64_IDP_NEW_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <!-- SingleSignOnService and real metadata elements -->
</md:IDPSSODescriptor>
~~~

**Structural snippet only**, not valid usable metadata: lacks EntityDescriptor/entityID, real Base64 certificates, and SSO URLs. Never use `BASE64_...` strings as real certificates.

Rules:

- Multiple **KeyDescriptors** may be published, each holding a different public key during rollover.
- `use="signing"` applies to signature verification; `use="encryption"` applies to encryption; when `use` is omitted, follow SAML metadata rules accurately.
- Certificates inside metadata `ds:KeyInfo` are **public info**, never including private keys.
- IdPs/SPs may enforce policies on key selection order and dedicated endpoints; merely seeing two certificates in metadata **does not prove** the real application loaded or can use both.
- `EntityDescriptor entityID`, `IDPSSODescriptor`/`SPSSODescriptor`, SSO/ACS, bindings, signing requirements, and validity windows must remain accurate.
- Keys can be represented via `ds:KeyValue` or X.509; do not assume all federations use only one form. In Spring Security examples, X.509 certificates are standard.

Per the **OASIS Metadata Interoperability Profile**, a key intended for future use may be pre-published to prepare for rollover, and an unused old key removed after a policy-appropriate transition period. This **does not permit** keeping a compromised key merely for availability.

## 4. Standard timeline when IdP rotates Response/Assertion signing key

**Before switching**, the IdP signs with private key I-old and the SP trusts certificate I-old.

| Phase | What does the IdP do? | What does the SP do? | Transition condition |
| --- | --- | --- | --- |
| **P0 – Inventory** | Identify issuer, current signing cert, switch schedule, and consumer list | Identify each registrationId, trusted fingerprint, and instances | Both sides agree on scope |
| **P1 – Publish** | Generate I-new safely; publish **I-old + I-new** in trusted IdP metadata | Fetch candidate metadata; vet issuer/source/signature/time | Do not remove I-old |
| **P2 – Consumer ready** | Continue signing with I-old | Update trust config to accept signatures from **I-old or I-new** in exact registration | All SPs/consumers confirm |
| **P3 – Cutover** | Switch signing SAMLResponse/Assertion to **I-new** | Keep accepting I-new and I-old during approved window | New logins with I-new succeed |
| **P4 – Drain** | Stop issuing new signatures with I-old; let outstanding flows finish | Wait out valid message lifetime/replay window and verify in practice | No messages left needing I-old |
| **P5 – Retire** | Remove I-old from IdP metadata/trust state per policy | After verifying consumer readiness, remove I-old from trusted IdP credentials | Completion evidence and rollback path |

**Key point:** At P2, the SP must have I-new **before** the IdP signs with I-new. At P5, the IdP must not assume all SPs dropped I-old just because its metadata URL now displays only I-new.

**In multi-tenant environments**, each SP consumer may be an app group, staging/prod, a cloud region, a separate cluster, or a B2B partner. The rollout schedule must cover **every still-authorized consumer** of that IdP.

### If the SP already trusts both keys, will login automatically succeed?

Not necessarily. Every response must still match `Issuer`, `Audience`, `Recipient`, `InResponseTo`, Conditions, and signature requirements. If the IdP changes entityID, binding, or ACS at the same time as rotating keys, that is a separate **protocol change**, not merely swapping a certificate.

**Never try keys from another IdP** when signature fails; use only verification credentials belonging to the exact asserting party of the registration being processed.

## 5. When SP rotates AuthnRequest signing key: reversed order

In this flow the **SP is the signature issuer**, and the **IdP is the consumer**. So the synchronization order reverses:

1. SP creates S-new in HSM/KMS or governed secret store. Private key never enters metadata.
2. SP **publishes S-new public certificate in SP metadata** alongside S-old during overlap, or delivers the certificate to the IdP via supported admin channels.
3. IdP fetches/imports SP metadata and configures AuthnRequest signature acceptance for **S-old and S-new**, verifying both in a test environment.
4. Only after IdP readiness confirmation does the SP switch new AuthnRequest/LogoutRequest signing to S-new.
5. Monitor requests/callbacks still tied to the old key; preserve handling of valid messages over the validity window.
6. Once confirmed no consumer/protocol flow depends on S-old, remove S-old from SP metadata and IdP trust lists on schedule, and revoke/destroy the old private key per policy.

**Common ordering mistake:** SP updates keystore config to sign immediately with S-new while the IdP still checks only S-old. User clicks Login, and the IdP rejects AuthnRequest before authentication.

**Spring Security note:** `RelyingPartyRegistration.signingX509Credentials` holds the **SP's** credentials for signing. The matching public certificate must be received by the IdP before actual signing switches. **Do not assume based solely on Collection element ordering** that Spring Security definitely picked the new key; verify the actual algorithm and certificate of emitted requests on your deployed version.

Some IdPs allow configuring only **one** SP signing certificate at a time. In that case, metadata alone cannot provide seamless overlap; coordinate synchronized cutover timing, a maintenance window, rollback mechanics, or contingency plans with the IdP.

## 6. When SP rotates EncryptedAssertion decryption key: why keep the old private key?

The encryption flow differs from signing. The IdP encrypts data for the SP using the SP's **public encryption certificate**; the SP uses its matching **private decryption key** to decrypt.

A safe plan:

1. SP generates E-new and stores the private key securely; confirm SP instances can decrypt with E-new.
2. SP publishes the **E-new public encryption certificate** in SP metadata alongside E-old when supported.
3. IdP loads new metadata and is configured to **select E-new when encrypting new assertions**. Merely "seeing two encryption certs" does not tell which key the IdP actually uses.
4. SP keeps **both E-old private key and E-new private key** to decrypt in-flight responses and pending requests during transition.
5. Test login across every IdP, every SP node, `EncryptedAssertion`, `EncryptedID`, and SLO where applicable.
6. Confirm the IdP no longer encrypts with E-old, pending messages have expired, and no valid flow needs E-old; only then remove E-old from metadata and retire the old private key.

**Critical mistake:** Immediately after the IdP switches to E-new, the SP deletes E-old private key. Encrypted responses generated before the switch yet still sitting in the browser/network **cannot be decrypted**. Even though signatures remain valid, authentication fails.

**Distinction to remember:** Public certificates are published first so the other side can prepare; old private keys must be retained in controlled fashion for overlap decryption. Retention duration must reflect actual TTL/binding/flow lifetimes and key storage policy—never kept indefinitely.

## 7. Additional flows: Logout, artifact, NameID, and IdP encryption

Beyond basic Web Browser SSO login, a federation may use:

- **Single Logout (SLO):** LogoutRequest/LogoutResponse may be signed; when SP or IdP rotates signing keys, verify SLO with the new certificate and handle in-flight messages.
- **Artifact binding:** may involve SOAP back-channel and dedicated trust/transport credentials; testing only HTTP-POST/Redirect is insufficient.
- **Encrypted NameID/Attribute:** the receiver needs the matching private decryption key; encryption is not limited to EncryptedAssertion.
- **IdP encryption key:** if the SP encrypts data sent to the IdP (per integration profile), the SP must load the IdP's new public encryption cert before encrypting with it; the IdP retains its old private decryption key for pending messages.
- **Metadata signed by federation operator:** if the metadata signing key rotates, handle trust anchor rotation **independently** before continuing to trust new metadata.

Build a **feature matrix** for your actual project; never assume every SAML federation uses SLO, encryption, or artifacts. Before retiring a key, assess **every place that key was used**, not just standard login.

## 8. Metadata lifetimes: validUntil and cacheDuration are not the same

A frequent source of outages is SP/IdP metadata caching, causing newly published keys **not to take effect immediately** on the consumer.

| Concept | Meaning | What to do during rollover? |
| --- | --- | --- |
| **cacheDuration** | Optimal cache interval before attempting refresh | Schedule publishing early enough for consumers to reload |
| **validUntil** | Timestamp when metadata becomes invalid per spec | Never use expired metadata to establish trust |
| **HTTP Cache-Control/ETag** | HTTP caching / conditional GET mechanisms | Check proxies/CDNs and actual caches |
| **Manual import** | Administrator uploads XML/cert once | Require explicit acknowledgement and deployment schedule |
| **Application-level cache** | Spring/cache provider holds registration snapshot | Require explicit cache eviction/refresh |
| **Cluster/node cache** | Nodes hold metadata snapshots from different times | Verify every single node before cutover |

Per OASIS Errata 05, an elapsed cache duration only means **it should be refreshed**; it does not invalidate metadata unless another validity bound applies. Conversely, once `validUntil` expires, metadata **must be treated as invalid**. Effective `validUntil` may also be constrained by a parent element in `EntitiesDescriptor`.

A safe planning sequence:

~~~text
T0: IdP publishes [I-old, I-new] in valid metadata
T1: SP/proxy/IdP consumers refresh per cacheDuration or manual import
T2: each consumer confirms I-new fingerprint is trusted and tests pass
T3: IdP switches signer from I-old to I-new
T4: in-flight/TTL window elapses and no new old-signed messages appear
T5: remove I-old from metadata/trust policy after approval
~~~

**Never set an arbitrary fixed wait like "after 24 hours all SPs must have refreshed".** Manually imported consumers may still be out of sync after 24 hours or several days. Time is only one factor; the decisive condition is **actual confirmation from every involved party**.

### Metadata passed validUntil while IdP is in outage?

Do not keep using metadata past `validUntil` merely to keep logins running. You may use **last-known-good** while metadata remains valid per spec/policy, yet never invent an arbitrary grace period past expiration. When trust is no longer valid, pause new logins for that registration and report a controlled error.

## 9. Metadata signatures: do not forget the trust source during key rotation

When one party publishes metadata announcing a new signing cert, the other must verify **the metadata came from an approved source**. If an attacker substitutes metadata containing their own public key, any attacker signature will verify against that bogus key if the consumer blindly treats the file as trusted.

Trust boundaries include:

1. **Metadata source:** controlled HTTPS URL, internal trust store, or signed artifact via federation operator.
2. **XML metadata signature (if required by policy):** verify using a **pre-configured metadata-verification credential/trust anchor**, never using a self-supplied certificate inside the metadata itself as its own trust anchor.
3. **EntityID and role:** exact IdP `IDPSSODescriptor` or SP `SPSSODescriptor`, never blindly picking the first entity.
4. **KeyDescriptor/use:** whether the new certificate is for signing or encryption must match its actual role.
5. **ValidUntil:** new metadata is unexpired and parent constraints apply.
6. **Binding to registration:** never take a key from tenant/IdP B and insert it into A's registration.

Modern Spring Security provides `AssertingPartyMetadataRepository` and OpenSAML implementations supporting metadata refresh and metadata signature verification with configured credentials. **If no verification credentials are supplied to the metadata signature validator, XML metadata signature verification does not happen automatically**. Trusting an admin-approved HTTPS endpoint is a distinct trust model and must be evaluated explicitly.

**Rotate metadata signing keys separately** from SAML Response signing keys. When the metadata signer rotates, distribute the new trust anchor to metadata consumers before they validate metadata signed by the new key.

## 10. What does "both sides synchronized" mean — verifiable criteria

Synchronized does not mean "sent an email notice" or "metadata URL updated". An SP–IdP pair reaches **READY_TO_SWITCH** when:

- **Publisher:** new metadata has the exact entityID, new certificate with proper usage, valid lifetime, and is reachable from a trusted source.
- **Consumer:** imported/updated the right metadata/cert version, recorded the expected **SHA-256 fingerprint**, and scoped it to the right registration.
- **Runtime:** every running instance picked up the config, not just one machine or pod.
- **Protocol:** tested signing/encryption/decryption with the new key across the real binding and flow.
- **Security:** signature, audience, issuer, recipient, InResponseTo, time, and replay validation remain enabled.
- **Rollback:** agreed on actions if a consumer fails, without reviving a compromised key.

Only when these conditions hold may the **signature issuer** activate the new key. For **RETIRE_OLD**, additionally ensure:

- No new messages are signed/encrypted with the old key.
- In-flight messages, browser sessions, and related pending requests have completed/expired appropriately.
- Every consumer has evidence it continues working when **the old key is simulated removed from trust** in test or monitored canary.
- SSO/SLO/encryption test results comply with policy, with no spike in signature/decryption errors.
- SP and IdP owners confirm rollback window closure, ownership, and retirement time.
- When handling a compromised key, follow **emergency revocation procedures**, never waiting for normal overlap conditions.

**Identifying by fingerprint** prevents confusion when `idp-cert-new.pem` is silently swapped while keeping the same filename. Fingerprints alone do not prove trust origin; still verify the certificate was approved for the exact IdP.

## 11. Spring Security: which registration holds which credentials?

In Spring Security SAML2 Login, `RelyingPartyRegistration` describes an SP–IdP link. Key points:

| API/configuration | Whose credential? | Purpose |
| --- | --- | --- |
| `assertingPartyMetadata(...).verificationX509Credentials` | **IdP** public certificates | SP verifies Response/Assertion signatures from IdP |
| `assertingPartyMetadata(...).encryptionX509Credentials` | **IdP** public encryption certs | SP encrypts data sent to IdP when profile requires |
| `RelyingPartyRegistration.signingX509Credentials` | **SP** private key + certificate | SP signs AuthnRequest/SLO messages |
| `RelyingPartyRegistration.decryptionX509Credentials` | **SP** private key + certificate | SP decrypts EncryptedAssertion/NameID |
| `RelyingPartyRegistrations.fromMetadataLocation` | Trusted IdP metadata | Builds registration from IdP metadata |
| `InMemoryRelyingPartyRegistrationRepository` | Constructed SP/IdP config | Does not auto-poll/update IdP metadata when IdP changes |
| `saml2Metadata` | Exports **SP** metadata | Used by IdP to register/accept SP certificates and ACS |

Do not confuse SP `signingX509Credentials` with IdP `verificationX509Credentials`. Nor assume Spring auto-picks an active signer by certificate start date or metadata order; verify actual provider/version behavior.

### Versions

Java examples below target **Spring Boot 3.x / Spring Security 6.5.x, Servlet, Java 17+**. Spring Security 7.x continues using RelyingPartyRegistration with changes in providers/OpenSAML; compile and test against your real BOM dependencies. Spring Security 5.x has a different API—do not paste modern code verbatim.

## 12. Spring Security example: trusting two signing certificates of the same IdP

Suppose the SP currently trusts `idp-old.crt` and wants to prepare to trust `idp-new.crt`. **Both files are real approved X.509 certificates for the same IdP**; code never accepts files from the browser. They are not private keys and do not belong in SP signing credentials.

File **src/main/java/com/example/security/SamlRolloverConfig.java**:

~~~java
package com.example.security;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlRolloverConfig {

    private static X509Certificate readCertificate(Resource resource)
            throws Exception {
        try (InputStream in = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository(
            @Value("classpath:saml/idp-old.crt") Resource oldCert,
            @Value("classpath:saml/idp-new.crt") Resource newCert)
            throws Exception {

        Saml2X509Credential oldVerifier = Saml2X509Credential
                .verification(readCertificate(oldCert));
        Saml2X509Credential newVerifier = Saml2X509Credential
                .verification(readCertificate(newCert));

        RelyingPartyRegistration corp = RelyingPartyRegistration
                .withRegistrationId("corp")
                .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                .assertionConsumerServiceLocation(
                    "{baseUrl}/login/saml2/sso/{registrationId}")
                .assertingPartyMetadata(idp -> idp
                    .entityId("https://idp.example.test/entity")
                    .singleSignOnServiceLocation(
                        "https://idp.example.test/sso")
                    .wantAuthnRequestsSigned(false)
                    .verificationX509Credentials(credentials -> {
                        credentials.add(oldVerifier);
                        credentials.add(newVerifier);
                    }))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

**Requirements for the app to run:** Spring Web, Spring Security, compatible `spring-security-saml2-service-provider`; real cert files in `src/main/resources/saml/`; a real IdP; SP Entity ID/ACS registered and signing/encryption configured per agreement. The sample has no SP private key to sign AuthnRequests or decrypt assertions; `wantAuthnRequestsSigned(false)` illustrates an IdP **not requiring signed AuthnRequests**. If the IdP requires signing or encrypts assertions, add SP credentials. Domain `example.test` is illustrative, not a live endpoint.

**The code is a configuration class inside a Spring app**, not a standalone program with fixed stdout. It only expands **IdP verification credentials** from I-old to I-old + I-new. This is the **preparation phase before the IdP switches signers**.

**Critical boundary:** Both keys in the sample must belong to the **same IdP**. Never insert partner B's certificate into partner A's assertingPartyMetadata just to avoid an `invalid signature` error.

### After cutover completes

Once the IdP signs with I-new, consumers succeed with I-new, old flows have drained, and retirement is approved, remove `oldVerifier` from the list and deploy/refresh config on schedule. **Never edit early just because I-new's certificate appeared in metadata**.

### If IdP metadata is loaded from a URL

Instead of specifying certs directly, `RelyingPartyRegistrations.fromMetadataLocation("https://...")` can read IdP metadata and build a registration. Yet when paired with `InMemoryRelyingPartyRegistrationRepository`, the built registration is an in-memory snapshot; **it does not auto-refresh metadata every time the IdP updates**.

Spring Security also offers `AssertingPartyMetadataRepository` supporting load/refresh by metadata expiry, and `OpenSaml5AssertingPartyMetadataRepository` in the matching API branch. When using refresh/caching, define source trust, cache eviction/TTL, error fallback, and metadata expiry; never assume a new metadata URL means every node is running the new version.

## 13. Extending to SP signing and decryption: differing key-usage order

Code illustrating builder setup with SP keys:

~~~java
// signing credentials: SP owns both private key and certificate.
// Variables spOldSigningKey, spOldSigningCert, spNewSigningKey,
// spNewSigningCert were loaded from a trusted secret store.
builder.signingX509Credentials(creds -> {
    creds.add(Saml2X509Credential.signing(
            spNewSigningKey, spNewSigningCert));
    creds.add(Saml2X509Credential.signing(
            spOldSigningKey, spOldSigningCert));
});

// decryption credentials: during overlap,
// SP retains both private keys to read in-flight messages.
builder.decryptionX509Credentials(creds -> {
    creds.add(Saml2X509Credential.decryption(
            spNewDecryptKey, spNewDecryptCert));
    creds.add(Saml2X509Credential.decryption(
            spOldDecryptKey, spOldDecryptCert));
});
~~~

**This is a configuration snippet where `builder` and credential variables are supplied by the app from KMS/HSM/secret manager**, not standalone Java and not compilable alone. It illustrates **two collections with different roles**, not a directive that automatically selects the active signing key.

**Version-specific check:** In many implementations, only **one** signing credential is used for new messages (potentially by configuration order); for decryption, multiple credentials may be tried. Never assume key selection in Spring Security 6.x matches every 5.x/7.x branch or every IdP. **After changing ordering/active keys, generate a real SAMLRequest and verify which public certificate actually validates the signature**.

**Never publish SP private keys** in metadata, and never log private-key PEM values. SP metadata publishes only public certificates. The old private decryption key must remain in a secure secret store until pending messages finish processing, then be retired with auditing.

### Avoid merging signing and encryption rotation unless necessary

If the same certificate is currently used for SP signing and encryption, you might update the public cert once, yet **usage still involves two separate cutovers**:

- Signing cutover: SP begins signing new requests with the new private key; IdP must trust the new public signing cert.
- Encryption cutover: IdP begins encrypting new responses with the new public encryption cert; SP must retain the matching private decrypt key.

Therefore coordinate both items separately whenever possible. Avoid deleting the old private key merely because the signing path cut over; it may still be needed for decryption.

## 14. Inspecting actually emitted SP metadata

Spring Security can publish SP metadata via:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Typical paths:

- `GET /saml2/metadata`: SP metadata for registrations when enumeration is appropriate.
- `GET /saml2/metadata/{registrationId}`: SP metadata for the specified registration.
- `GET /saml2/service-provider-metadata/{registrationId}`: supported compatible path.

You can run:

~~~bash
curl -fsS https://portal.example.test/saml2/metadata/corp
~~~

This is an **illustrative command**; `example.test` URLs will not work without replacing with a real SP. In production, apply appropriate authentication/authorization if policy restricts metadata exposure, and ensure reverse-proxy URL/HTTPS/Host headers are properly governed.

**Checks to run against real XML:**

1. Does `EntityDescriptor entityID` match the exact SP identifier registered at the IdP?
2. Does ACS `Location` point to the exact public HTTPS URL?
3. Does `SPSSODescriptor` display the right signing/encryption KeyDescriptors?
4. During overlap, are both old and new public certificates published with the **exact purpose**?
5. Which certificates are emitted when multiple `RelyingPartyRegistration` entries exist?
6. Is metadata signed per a trust policy the IdP actually supports?
7. After each deployment/refresh, did the IdP actually **import the new version** or is only the metadata URL updated?

Never assume every Spring Security version serializes credential lists into metadata identically. **Check actual output** and what the IdP imported; if the IdP imports certificates manually, updating the SP metadata endpoint does not mean the IdP was updated.

## 15. Standalone Java 17: "gate" model before removing old keys

The example below models **retirement preconditions for a normal signing key**; it does not perform SAML/XML Signatures or prove remote partner state. Inputs `confirmed` and `trustedKeyFingerprints` must represent **operationally verified evidence** from each consumer, never self-reported by a browser.

Create file **SamlKeyRetirementGateDemo.java**:

~~~java
import java.util.List;
import java.util.Set;

public class SamlKeyRetirementGateDemo {

    record Consumer(String name,
                    Set<String> trustedKeyFingerprints,
                    boolean confirmed) {}

    static String decide(List<Consumer> consumers,
                         String newKey,
                         boolean newSignerActive,
                         boolean oldMessagesDrained) {

        if (consumers.isEmpty() || consumers.stream().anyMatch(
                c -> !c.confirmed()
                    || !c.trustedKeyFingerprints().contains(newKey))) {
            return "WAIT: consumers not ready";
        }

        if (!newSignerActive) {
            return "WAIT: new signer not active";
        }

        if (!oldMessagesDrained) {
            return "WAIT: old messages in flight";
        }

        return "READY: planned retirement permitted";
    }

    public static void main(String[] args) {
        Consumer sp1 = new Consumer(
                "sp1", Set.of("I-old", "I-new"), true);
        Consumer sp2 = new Consumer(
                "sp2", Set.of("I-old", "I-new"), true);
        Consumer staleSp2 = new Consumer(
                "sp2", Set.of("I-old"), false);

        List<Consumer> ready = List.of(sp1, sp2);

        System.out.println(decide(ready, "I-new", true, true));
        System.out.println(decide(
                List.of(sp1, staleSp2), "I-new", true, true));
        System.out.println(decide(ready, "I-new", false, true));
        System.out.println(decide(ready, "I-new", true, false));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SamlKeyRetirementGateDemo.java
java SamlKeyRetirementGateDemo
~~~

**Exact stdout:**

~~~text
READY: planned retirement permitted
WAIT: consumers not ready
WAIT: new signer not active
WAIT: old messages in flight
~~~

Explanation:

- Case 1: both consumers confirmed trusting I-new, new signer is active, old flows drained → **simulated** criteria met to schedule retirement.
- Case 2: SP2 has not loaded I-new → must wait, even though SP1 works fine.
- Case 3: signer not yet switched to I-new → cannot remove I-old yet.
- Case 4: old messages still in transit → must wait before deleting I-old.

**Never use the demo's READY output as automated approval in production.** Real systems still require metadata trust validation, issuer/tenant scope, expiration, SSO/SLO tests, canary rollouts, revocation policies, partner confirmation, and auditing. Fingerprints in the demo are symbolic strings, not real fingerprints. Never apply this "wait" logic when a key is compromised: that requires dedicated incident response and may require rejecting logins until trust is restored.

## 16. Deployment runbook: before, during, and after cutover

### A. Before publishing the new key

1. Inventory **IdP signing, SP signing, SP decryption, IdP encryption, metadata signing, SLO** per federation link.
2. Record `registrationId`, IdP `entityID`, SP `entityID`, ACS, bindings, hostnames, and every consumer/proxy/node.
3. Record SHA-256 fingerprints, key IDs, usage purpose, expiration dates, metadata validity, and owners.
4. Identify private key storage: KMS/HSM/keystore and backup/restore policies.
5. Agree on **planned publish**, deadline for metadata consumers to be ready, cutover time, drain window, and rollback criteria.
6. Verify the new certificate meets policy algorithms/key sizes/usage; never weaken security.
7. Test cert rotation in staging with the same SSO/SLO/encryption layout and issuer/tenant routing.

### B. Publishing and synchronizing metadata

1. Publisher adds the new public certificate alongside the old certificate in metadata or sends via IdP/SP-supported import mechanics.
2. If metadata is signed, sign the new version with the metadata-signing key consumers currently trust; if the metadata signer is also rotating, handle trust anchors separately.
3. Consumers reload metadata and verify **source, entityID, signature if required by policy, key purpose, validity, and fingerprint**.
4. Consumers load and apply config across all nodes/services/regions; clear old caches per policy or rebuild registrations.
5. Each consumer returns acknowledgement with key fingerprint, metadata version/hash, apply timestamp, and test results.
6. **Never switch signer/encryption targets** merely because publishing finished; pass readiness checks first.

### C. Monitored cutover

1. Pick a canary flow/consumer if architecture permits.
2. Switch active signing/encryption behavior at the publisher; **do not delete the old key immediately**.
3. Emit sample AuthnRequest/SAMLResponse/SLO/EncryptedAssertion in a controlled environment to verify the new key.
4. Monitor `SignatureException`, `InvalidSignature`, recipient/audience errors, decryption errors, login latency, and redirect loops.
5. Compare the fingerprint/certificate actually used to sign/encrypt rather than merely reading filenames in config.
6. On failure, halt rollout expansion; roll back to the old key only if the old key is **uncompromised** and still permitted to be trusted.

### D. Post-cutover and pre-retirement

1. Confirm no publisher instance still creates new messages with the old key.
2. Wait for valid in-flight requests/responses to finish their processing window.
3. Monitor new logins and logouts across all IdP/SP consumers, tenants, deployment regions, browser bindings, and encrypted assertions if used.
4. Rehearse removing the old key in staging/canary or a test config snapshot; never break config across all traffic without a backup.
5. Obtain sign-off from SP/IdP owners and change management.
6. Remove the old key from metadata/trust config in the right direction; delete the old private key from secret stores when retention no longer requires it; update audits and runbooks.
7. Continue monitoring errors during the post-change window.

**Completion criteria:** Not merely "rollout timer elapsed", but **issuer no longer uses old key + receiver trusts and uses new key + no valid messages remain needing old key + metadata reflects final state + test evidence recorded**.

## 17. Common incidents when synchronization is insufficient

| Symptom | Likely cause | Safe resolution |
| --- | --- | --- |
| SP reports invalid signature right after IdP rotates cert | SP still trusts only I-old | Load I-new from trusted IdP source into right registration; verify rollout |
| Only some users fail login | Some SP nodes run old metadata | Verify fingerprint on every instance/region |
| IdP rejects AuthnRequest after SP rotates signing key | IdP has not imported S-new | Sync SP metadata, confirm IdP trusts S-new, then retry |
| EncryptedAssertion fails decryption post-cutover | SP deleted E-old too early or IdP still encrypts with E-old | Retain permitted private decrypt keys for overlap; coordinate with IdP |
| SP metadata has both S-old/S-new yet IdP reports unknown key | IdP manual import not updated | Inspect IdP's actual trust store, not just metadata URL |
| New metadata has new cert yet metadata signature fails | Metadata trust anchor not ready | Do not replace trusted metadata before verification |
| `validUntil` expired | Consumer uses invalid expired metadata | Suspend trust based on expired copy; fetch valid new metadata |
| SSO succeeds yet SLO fails | Forgot signed LogoutRequest/Response flows | Add SLO to test matrix; keep right signing/verification keys |
| Staging works, production fails | Different entity IDs, ACS, certs, or tenants across envs | Match fingerprint + metadata per exact environment |
| IdP A works, IdP B breaks | SP updated trust for one IdP but not all | Track per-registration matrix; never mix two IdPs' keys |
| SP switched signing key yet old signatures still seen | Some nodes/keystores/order not updated | Verify actually emitted signatures on every node |
| After rotating certs, an app returns HTTP 403 | Authentication succeeded yet authorization/role mapping failed | Check business permissions; never disable SAML signature validation |
| Metadata endpoint returns HTTP 200 yet consumer does not refresh | Cache/ETag/manual import holds old snapshot | Inspect cache policy and consumer apply evidence |
| Same key shared for signing and decryption | Deleting key after signing cutover breaks decryption | Assess every usage separately; retain key until all flows drain |

**Never fix errors by:** disabling SAML signature verification; trusting certificates from `ds:KeyInfo` of an unverified response; accepting any issuer/audience; using IdP B's certificate as backup for A; relaxing metadata `validUntil`; or putting private keys into public metadata.

## 18. Compromised keys: emergency procedure differs from routine rollover

If a private signing/decryption key **shows signs of compromise**, keeping an overlap "until every consumer syncs" may allow an attacker to keep exploiting the old key.

Appropriate response depending on scope and severity:

1. Activate incident response; identify affected key IDs/fingerprints, SP/IdP, and involved messages/registrations.
2. **Stop using and revoke trust in the compromised key** as soon as deployable; prioritize authentication integrity over uninterrupted SSO.
3. Rotate keys via an independent approval channel, vet new metadata, and instruct consumers to update urgently.
4. You may need to **pause login/SLO/encryption** depending on that key until safe trust is restored.
5. Investigate replay and sessions created during the exposure window, revoke sessions, and audit access per policy.
6. Delete old secrets via emergency procedure without writing them to logs or tickets.
7. Afterward, review compromise root cause, rotation procedures, and detection capability.

**Distinction:** **Planned rollover** prioritizes overlap and continuity; **compromise revocation** prioritizes eliminating spoofing capability. Never conflate the two and never use "old messages drained" to delay revoking a leaked key when policy demands immediate invalidation.

## 19. Monitoring, evidence, and accountability

Every rotation should have a change/audit record including:

| Field | Purpose |
| --- | --- |
| Federation pair | IdP entityID, SP entityID, registrationId |
| Direction & purpose | IdP signing / SP signing / SP decryption / metadata signing |
| Key fingerprints | Old/new SHA-256 fingerprints, excluding private keys |
| Metadata source | Approved URL/path, version/hash, signature verification result |
| Metadata validity | Effective validUntil and cache refresh status |
| Publisher active key | Key actually used in new messages |
| Consumers readiness | List of partners/nodes imported + test pass |
| Cutover timestamps | Publish, import, switch, drain complete, retire |
| Test evidence | Response/Request signing, ACS, SLO, decryption, tenant checks |
| Rollback status | How rollback was tested if key was uncompromised |
| Owners and approvals | IdP/SP owners, change/incident ticket |

Several **app-defined** metrics (not built into Spring Security by default):

- `saml_rotation_peer_ready`: count of ready consumers per federation link.
- `saml_metadata_last_refresh_success_timestamp`: last metadata load time.
- `saml_metadata_valid_until_timestamp`: remaining metadata validity timestamp.
- `saml_signature_verification_failures_total`: signature errors per registration.
- `saml_decryption_failures_total`: decryption errors from key mismatch/cipher.
- `saml_signing_fingerprint_observed`: observed actual signer key fingerprint (with security-safe labels/hashes).
- `saml_sso_login_failures_total`: new SSO errors categorized by issuer/registration.
- `saml_slo_failures_total`: Single Logout errors.

Never write raw `SAMLResponse`, NameID, email, attributes, or private keys to production logs. When fingerprints are needed, use SHA-256 over admin-approved public certificates; never send secret keystores/truststores to monitoring systems.

## 20. Pre-approval test matrix before deleting old keys

| Case | Scenario | Expected |
| --- | --- | --- |
| A | IdP signs I-old, SP trusts I-old + I-new | Response verified if other SAML conditions are valid |
| B | IdP signs I-new, SP loaded I-old + I-new | Response verified if other conditions are valid |
| C | IdP signs I-new, one SP node lacks I-new | Test must detect this node; **do not retire I-old yet** |
| D | SP signs AuthnRequest with S-new, IdP trusts only S-old | IdP rejects; do not cut over until IdP is ready |
| E | SP signs S-new, IdP trusts S-old + S-new | AuthnRequest valid when signature/binding are right |
| F | IdP encrypts with E-old, SP retains E-old + E-new private keys | Valid message decrypts |
| G | IdP encrypts with E-new, SP holds E-new private key | Decrypts; then validate SAML signature |
| H | SP deletes E-old while E-old encrypted responses are still in flight | Detected as failure; do not retire early |
| I | SLO message signed with new key | Right partner trusts and verifies signature |
| J | Metadata past `validUntil` | Never use expired metadata for trust |
| K | Metadata has unauthorized cert/issuer change | Reject new candidate; never accept bogus key |
| L | Two IdPs share same Portal yet have different certificates | Trust only keys of the exact registration |
| M | User holds old SP session after IdP rotates key | Check session policy/step-up; do not extend privileges automatically |
| N | All peers report ready yet new signer is not active | Do not delete old key yet |
| O | Old key compromised | Run incident revocation; do not use normal overlap |

**Testing method:** Use a test IdP/SP and real approved certificates in staging; verify signatures on requests/responses per exact binding, compare audience/issuer/recipient, and route through the reverse proxy. Never treat a single `curl` fetching metadata or a mocked-signature unit test as end-to-end proof.

## 21. Self-check questions

**1. The IdP published a new certificate in metadata; can the old certificate be deleted immediately?**  
No. You must confirm all SP consumers loaded and verified the new key, the IdP switched signers, and no valid messages remain needing the old key.

**2. Why does rotating the SP signing key require the IdP to load SP metadata first?**  
Because the IdP verifies SP-signed AuthnRequests. If the IdP knows only S-old while the SP already signs with S-new, requests will be rejected.

**3. Why must the SP retain both old and new private decryption keys when the IdP rotates encryption certificates?**  
Because in-flight assertions may still be encrypted with the old public key; only the old private key can decrypt them.

**4. Does an elapsed cacheDuration automatically mean metadata is invalid?**  
Not automatically. It is a signal to refresh, unlike `validUntil` which is a hard validity limit.

**5. HTTPS metadata shows a new public key; can it be trusted immediately without checking entityID and source?**  
No. Vet source/trust policy, exact entityID, role, key usage, validity, and XML signature if required by federation.

**6. One SP node logged in with I-new; is that enough evidence to retire I-old?**  
Not yet. Check every supported node/consumer, auxiliary flows, and pending messages.

**7. IdP A has a certificate error; can IdP B's certificate be used to verify?**  
No. Signatures must be verified using the authorized keys of that exact IdP/registration.

**8. If an old key is leaked, do we keep overlap to avoid an outage?**  
Not by default. Follow emergency revocation per incident policy; pausing SSO may be necessary to protect identities.

**9. If only the signing key changed, must SLO still be tested?**  
Yes, if your system's SLO uses the same signing credential; every flow using the key must be inventoried and tested.

**10. In Spring Security, whose metadata does `saml2Metadata` publish?**  
It publishes **SP metadata**, helping the IdP learn SP details; it does not auto-sync IdP metadata stored at the SP.

## 22. Completion checklist

- [ ] Distinguished IdP signing, SP signing, SP decryption, IdP encryption, metadata signing, and TLS credentials.
- [ ] Identified all SP/IdP consumers, instances, tenants, environments, and bindings in use.
- [ ] Collected old/new SHA-256 fingerprints, metadata sources, entityIDs, ACS/SLO, owners, and rollout schedules.
- [ ] Published new public keys under the right KeyDescriptor `use`, **never publishing private keys**.
- [ ] New metadata has accurate issuer/role/endpoints, valid source/signature/trust, and unexpired `validUntil`.
- [ ] Every consumer loaded new metadata/certs into the exact registration and confirmed fingerprints.
- [ ] Tested signed AuthnRequests and signed Responses/Assertions before switching the active signer.
- [ ] If encrypted assertions/NameIDs exist, retained old/new private decryption keys across transition.
- [ ] Never assumed browsers/caches/apps/nodes update metadata instantly when a URL changes.
- [ ] When IdP/SP switched signers, verified fingerprints on **actual new messages**.
- [ ] Tested Single Logout, tenant routing, recipient/audience, InResponseTo, and expiry per config.
- [ ] Never deleted old keys before all consumers were ready and old messages drained.
- [ ] Monitoring covers signature/decryption failures, refresh age, and certificate/metadata expiry.
- [ ] Rollback and change approvals ready for planned rollover; dedicated incident response ready for key compromise.
- [ ] Never disabled signature checks, mixed keys across IdPs, or extended expired metadata.
- [ ] Post-retirement, updated trust configs and metadata on both sides, purged old secrets safely, and archived QA evidence.

## 23. Conclusion

**Two-sided metadata synchronization before removing old keys** is a multi-phase process: **publish new key → verify metadata and import at consumers → test consumer readiness → switch signing/encryption to new key → wait for pending messages → retire old key under control**. For IdP signing, the SP must trust the new key first; for SP signing, the IdP must trust the new key first; for SP decryption, the SP must retain both private keys until the IdP stops encrypting with the old key.

In Spring Security, `RelyingPartyRegistration` and metadata repositories are where trust is configured, yet **every system must still design its own ownership, cache refresh, cutover, and monitoring**. Never treat a metadata endpoint showing a new certificate as proof that all partners have updated; remove old keys only after confirmation across real protocol traffic, except during key compromise requiring emergency revocation.

### Official documentation

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata / AssertingPartyMetadataRepository: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing AuthnRequests, signing credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 Javadoc — RelyingPartyRegistration.Builder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html
- OASIS — SAML 2.0 Metadata Interoperability Profile (key rollover): https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.html
- OASIS — SAML 2.0 Errata 05 (cacheDuration vs validUntil): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- OASIS — SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
