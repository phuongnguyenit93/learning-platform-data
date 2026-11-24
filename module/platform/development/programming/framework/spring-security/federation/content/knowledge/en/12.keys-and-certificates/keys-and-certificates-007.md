# Rotating IdP signing certificates with a dual-key acceptance window

> **Topic:** Spring Security – federation. **Group:** Keys and certificates. This lesson guides a Service Provider (SP/Relying Party) in maintaining SAML 2.0 Single Sign-On when an Identity Provider (IdP/Asserting Party) **rotates its signing key** without interrupting logins, by implementing a verified **simultaneous trust window for old and new keys**. Examples target Java 17+, Spring Boot, and Spring Security SAML2 Web Browser SSO.

## 1. Objectives and scope of the lesson

By the end of this lesson, you will be able to:

1. Distinguish **IdP signing certificates**, **SP signing certificates**, **SP decryption private keys**, **metadata signing keys**, and **TLS certificates**; understand which keys rotate and who owns the secret key.
2. Explain why switching an IdP signing certificate "in one shot" easily causes SPs to reject all SAMLResponses, even though users authenticated successfully at the IdP.
3. Design a schedule **prepublish → dual trust → IdP switch → observe → retire old key** with deadlines, owners, QA evidence, and rollback.
4. Declare **two public certificates** for the same IdP in Spring Security's `RelyingPartyRegistration` / `assertingparty.verification.credentials`.
5. Use trusted metadata to refresh the signing certificate set; understand the limits of cached/refreshable metadata and metadata signatures themselves.
6. Test SAMLResponses signed by each key at each stage, including wrong issuer, audience, recipient, expired assertion, unknown key, unapproved cert/metadata, and multi-tenant cases.
7. Handle **planned rotation** separately from **suspected private key compromise**; know when to skip overlap and block the old key immediately.
8. Confirm at the end that the application actually **removed the old key from its trust list**, not merely stopped using it at the IdP.

**Upfront takeaway:** **Overlap is strictly for approved public keys belonging to the trusted IdP**. It does not mean "accept any certificate the IdP sends in a message" or "skip SAML signature verification to avoid downtime".

## 2. Context: one IdP, multiple SPs, and a rotating signing key

Suppose an enterprise runs a SAML IdP with:

| Item | Illustrative example | Role |
| --- | --- | --- |
| IdP `entityID` | `https://sso.partner.example/issuer` | Logical identifier of the asserting party |
| IdP SSO endpoint | `https://sso.partner.example/saml/sso` | Where the browser sends `AuthnRequest` |
| SP `registrationId` | `partner` | Internal lookup key in Spring Security |
| SP `entityID` | `https://app.example.org/saml2/service-provider-metadata/partner` | Assertion audience targeting the SP |
| SP Assertion Consumer Service | `https://app.example.org/login/saml2/sso/partner` | Destination receiving SAMLResponse on the SP |
| Current IdP signing key | `K_old`, public certificate `C_old` | Currently signing SAMLResponse/Assertion |
| Upcoming IdP signing key | `K_new`, public certificate `C_new` | Will become primary signing key |
| SP verification trust set | `{C_old}` → `{C_old,C_new}` → `{C_new}` | Defines public keys SP allows for verification |

**The IdP holds private keys `K_old`/`K_new`.** The SP only needs **public X.509 certificates `C_old` and `C_new`** to verify signatures. The SP **never** needs to know the IdP's private signing key. Conversely, if the SP signs AuthnRequests or decrypts EncryptedAssertions, those belong to the **SP's own key set**, with separate rotation schedules and coordination requirements.

### 2.1. "Certificate" layers not to confuse

| Type | Private key owner | How does the SP use it? | Does rotating one force rotating another? |
| --- | --- | --- | --- |
| **IdP SAML signing certificate** | IdP | Verify XML Signatures on Response/Assertion and signed SAML messages | Not automatically |
| **IdP metadata signing certificate** | IdP/federation operator | Verify the signature on the **metadata document** before importing SAML signing keys | Not automatically; trust anchor must be independent |
| **IdP TLS server certificate** | IdP/web ingress | Establish HTTPS when browsers/SP access the IdP | Does not replace SAML signature verification |
| **SP AuthnRequest signing certificate** | SP | SP uses private key to sign AuthnRequests sent to IdP | Different from IdP signing certificate |
| **SP decryption certificate** | SP | IdP encrypts assertions for SP; SP uses private key to decrypt | May require dual-decryption during SP key rotation; outside this lesson |
| **SP TLS server certificate** | SP/web ingress | Protects ACS and HTTPS browser sessions | Not directly tied to IdP SAML signing keys |

**Principle:** The IdP's SAML signing certificate can appear in metadata under `<KeyDescriptor use="signing">`; its public key is trusted to verify signatures. Certificates in the HTTPS chain or `<ds:KeyInfo>` of a SAMLResponse **do not automatically become trust anchors**. Add a certificate to the trust set only after verifying its source and authorization to change federation config.

### 2.2. Signature verification is only one condition

Even when a signature verifies cleanly with `C_old` or `C_new`, the SP must still verify:

- IdP `Issuer` matches the approved registration.
- `AudienceRestriction` contains the exact SP `entityID`.
- `SubjectConfirmationData/@Recipient` and `Response/@Destination` match the HTTPS ACS.
- `InResponseTo` matches the AuthnRequest in SP-initiated flows, preventing replay and binding the session.
- `Conditions/NotBefore/NotOnOrAfter` and bearer confirmation times are valid, with small bounded clock skew.
- Status, exact signed message/assertion element, no XML signature wrapping, matching profile/binding.
- App permissions remain post-authentication authorization; a valid signing key **does not grant `ROLE_ADMIN`**.

**Never alter other validators** merely to "make certificate rotation go smoothly".

## 3. Incident flow when rotating keys without overlap

Faulty scenario:

```text
Before T1:
  IdP signs with K_old
  SP trusts only C_old
  => SAML login succeeds

At T1:
  IdP immediately switches to signing with K_new
  SP not yet updated, still trusts only C_old
  => SAMLResponse from K_new is rejected (signature verification failure)

At T2:
  Some SPs/nodes trust C_new while other nodes still trust C_old
  => Intermittent login failures depending on load balancer / tenant / pod

At T3:
  SP deletes C_old while IdP still emits old messages
  => Some in-flight responses or SLO messages may be rejected
```

Merely seeing the browser return to the login page is not enough to identify the cause: distinguish **IdP authenticating the user** successfully from **SP verifying the SAMLResponse** successfully. Error messages such as "signature validation failed", "unknown signing certificate", or metadata trust errors can appear in different components depending on framework and logging setup.

A rejected SAMLResponse does not become valid by increasing session timeouts or opening `permitAll("/**")`. The fault lies in key/issuer/cert trust relationships, not URL authorization.

## 4. Zero-downtime rotation process: prepublish → overlap → switch → retire

### 4.1. Standard state model

```text
Phase 0: STEADY
  IdP signs:          K_old
  SP trusts:          {C_old}

         |
         | IdP creates K_new; public C_new approved/distributed
         v

Phase 1: PREPARED / DUAL TRUST
  IdP signs:          K_old
  SP trusts:          {C_old, C_new}

         |
         | Verify every SP, every pod/region/tenant has applied it
         v

Phase 2: SWITCHED / OBSERVING
  IdP signs:          K_new
  SP trusts:          {C_old, C_new}

         |
         | Wait for in-flight messages, cache TTLs, rollback window;
         | confirm no valid messages arrive from K_old
         v

Phase 3: RETIRED
  IdP signs:          K_new
  SP trusts:          {C_new}
  K_old:              IdP stops using; old private key destroyed/locked per policy
```

This is a **trust overlap strategy**: in Phase 1 and Phase 2, the SP expands **only the accepted public key set for the same IdP**, never expanding issuers, tenants, ACS, or application privileges. An assertion signed by any key in the set **must still** pass all other SAML checks.

### 4.2. Step-by-step execution

**Step 0 — Inventory and lock agreement.** List all SPs/tenants/clusters connected to the IdP; record current certificates, SHA-256 fingerprints, `NotBefore/NotAfter`, key algorithm/length, metadata retrieval path, cache TTL, IdP and per-SP owners, config refresh capabilities, and rollback. Record the IdP's scheduled signing switch time and final cutoff date for the old key. Never assume an arbitrary SP refreshes metadata automatically.

**Step 1 — Generate new key at IdP.** The IdP generates a new private key via HSM/secret manager/approved governance, sets usage rights and policy-compliant signature algorithm, and exports **only the public certificate**. The new certificate must bind to the exact IdP `entityID` and approved distribution channel; never send the private key to the SP.

**Step 2 — Publish old and new certificates simultaneously.** In IdP metadata, publish two public signing certificates (depending on product), or deliver a verified certificate bundle through change control. Keep `entityID` and SSO URL unchanged unless that is a **separate** approved change. If metadata is signed, the new metadata must carry a valid signature from the known metadata signing trust anchor.

**Step 3 — SP loads C_new while still accepting C_old.** Spring Security can declare multiple `verification.credentials` for the same IdP. Push configuration to all nodes, inspect the *effective* runtime config (not just intended files), refresh caches/repositories per procedure, and run smoke tests.

**Step 4 — Verify dual trust actually works.** Using a test IdP or controlled test environment, emit SAMLResponses signed with `K_old` and `K_new`; both must be accepted by the SP **provided issuer/audience/recipient/time/correlation are all valid**. Responses from unknown keys must be rejected. If any node/region lacks C_new, **do not switch the IdP yet**.

**Step 5 — IdP switches to signing new messages with K_new.** Execute only after sufficient evidence that all SPs are ready. Monitor authentication errors, login success rates, and signs of metadata refresh/clock drift. The IdP may retain C_old in metadata during this phase yet **must not keep creating new messages with K_old** unless performing a controlled rollback.

**Step 6 — Maintain bounded overlap.** Keep `{C_old,C_new}` for an approved interval to handle in-flight SAMLResponses, session/SSO/logout messages still signed with the old key (if any), cache TTLs, configuration propagation, and the rollback window. Do not pick the duration arbitrarily; see section 4.3.

**Step 7 — Remove C_old from all SPs.** Confirm the IdP no longer uses `K_old`, no valid messages remain needing C_old verification, and the rollback window has closed. Update metadata/trust stores to `{C_new}`, roll out across all nodes/tenants, run negative tests with old signatures, and ensure caches/remote metadata do not reintroduce C_old.

**Step 8 — Close change and retire old key.** The IdP locks/destroys/archives private key K_old per policy and records evidence of the final trust set; the SP closes the incident/change ticket, hands over monitoring for the new cert, and schedules the next cycle.

### 4.3. How long should two keys be kept?

**There is no universal fixed overlap number for all IdPs/SPs.** Consider:

- SP configuration rollout duration across all nodes, regions, tenants, and app versions.
- Metadata TTL, scheduled refresh intervals, ETag/caching, and retry behavior when IdP metadata is unavailable.
- Maximum SAML validity window of assertions/Responses, `NotOnOrAfter`, and clock skew (plus in-flight message transit).
- Other SAML Single Logout/Artifact/auxiliary flows still using the old signing key (if in scope).
- Certificate validity dates—whether sufficient time remains before expiry.
- Permitted IdP rollback window and safe recovery capability.
- Real alerts/metrics proving no new messages signed by K_old arrive after cutover.

For instance, if metadata refreshes once every 24 hours, SP rollouts take up to 2 days, and multiple unsynchronized nodes exist, an overlap of a few minutes has no basis. Yet keeping C_old indefinitely **extends the acceptance window for the old key**, which is especially dangerous if the key is weak or at risk of exposure. Size the duration to risk and **set an explicit deadline**, never "keep two keys forever just to be safe".

**Separate the two intervals:** prepublication lead time (before the IdP signs with K_new) and post-switch grace period (after the IdP switches). Do not merge them since their goals differ.

## 5. How does the SP know both certificates belong to the right IdP?

### 5.1. Metadata with matching issuer and trusted certificate source

An IdP metadata `EntityDescriptor` contains `entityID` and an `IDPSSODescriptor`. During overlap there can be two `KeyDescriptor use="signing"` elements, each publishing one public certificate. Abbreviated XML shape illustrating the relationship:

```xml
<md:EntityDescriptor
  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
  entityID="https://sso.partner.example/issuer">
  <md:IDPSSODescriptor
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <!-- KeyDescriptor use=signing #1 carrying C_old in X.509 format -->
    <!-- KeyDescriptor use=signing #2 carrying C_new in X.509 format -->
    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://sso.partner.example/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

**The snippet above is not importable metadata** because it intentionally omits real X.509 certificate contents, attributes, and potentially mandatory metadata signatures. Obtain **real verified metadata issued by the IdP**. If metadata contains a `KeyDescriptor` without `use`, SAML metadata may interpret that key as usable for multiple purposes per profile; read the exact semantics rather than guessing "the first key is signing".

**An XML file containing two certificates does not prove both belong to the right IdP.** Verify the distribution source, metadata signing policy/trust anchor, expected issuer, and change approval. Never use certificates embedded directly in a SAMLResponse or URLs passed by the browser to auto-update the trust set.

### 5.2. Certificate fingerprint, issuer, validity, and key usage

When receiving C_new, the integration team must record at least:

- SHA-256 fingerprint of the **DER certificate** (do not rely on SHA-1 alone).
- Subject, issuer DN, serial number, `NotBefore`, `NotAfter`, and key algorithm/size.
- Certificate receipt source, timestamp, approver, and IdP owner.
- Purpose: SAML signing verification; never repurpose automatically as TLS server trust or SP decryption credential.
- Planned activation and retirement dates, config/metadata version.
- Evidence from an independent channel whenever signing keys change: approved ticket, metadata signed by a known trust anchor, or authenticated IdP operator channel.

Command to inspect public certificates:

```bash
keytool -printcert -file idp-signing-old.crt
keytool -printcert -file idp-signing-next.crt
```

`keytool` ships with the JDK; output varies by real certificate and JDK version, so this lesson fixes no static stdout. This command **only inspects structural/fingerprint details**; it does not verify that the new certificate was approved by an **authorized IdP**. To check whether two certificates share the same key, compare their public-key/SPKI fingerprints; **two certificates with different serials/fingerprints do not necessarily have two different private keys** if the IdP reused a key. Effective rotation should consider generating a **new key pair** when required by policy.

### 5.3. X.509 expiration and SAML signature validity are two separate stories

Verifying an XML signature with a public key does not automatically mean the library ran **every** PKIX/path validation and certificate expiry check like a TLS browser. Some SAML deployments treat certificates as metadata-pinned public keys without validating X.509 chains under the TLS model. Therefore:

- Verify clearly how Spring Security/OpenSAML and your organization's policy handle certificate `NotBefore/NotAfter`; if blocking expired certs is required, **implement and test** that policy.
- Never infer "certificate is unexpired" from "SAMLResponse signature passed", nor "SAML assertion signing valid" from "TLS certificate valid".
- Rotation schedules must have **milestones ahead of certificate expiry**, never waiting until the final day to issue C_new.
- Each key in the trust set should carry a policy-managed state `ACTIVE/OVERLAP/RETIRED/REVOKED`; never rely solely on certificate ordering in metadata.

## 6. Spring Boot configuration: accepting C_old and C_new for the same IdP

### 6.1. Configuration via application.yml

Assuming a Spring Boot/Spring Security servlet stack compatible with Java 17+, dependency `spring-security-saml2-service-provider`, a valid IdP, and two approved **real public certificate files** under `src/main/resources/saml/`.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/partner"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/partner"
            assertingparty:
              entity-id: "https://sso.partner.example/issuer"
              singlesignon:
                url: "https://sso.partner.example/saml/sso"
                binding: REDIRECT
                sign-request: false
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing-old.crt
                  - certificate-location: classpath:saml/idp-signing-next.crt
```

**Configuration meaning:**

- Both `verification.credentials` entries let the SP **verify signatures from the same asserting party**. These are two distinct **public certificates**, not private keys.
- `registration.partner` scopes the exact IdP–SP relationship. With multiple IdPs, each registration must hold **only that IdP's verify credentials**; never merge certificates from all issuers into one shared list.
- The SP's `entity-id` is what the IdP should put in `AudienceRestriction`. `assertion-consumer-service-location` is the URL for `Recipient`/`Destination`. Adding a new key **does not change** these values.
- `assertingparty.entity-id` is the IdP identifier; it must match the approved source. Never add extra issuers or loosen audience checks to "compensate" for rotating a signing certificate.
- `singlesignon.url` is the IdP endpoint receiving AuthnRequest, not where the SP receives SAMLResponse. `sign-request: false` merely illustrates a test IdP allowing unsigned AuthnRequests; if the IdP requires signed requests, separate **SP signing credentials** are needed.
- Using classpath for illustration: replacing a certificate inside an artifact requires redeploy/restart unless the app has a proper reload mechanism. **Never assume editing a file on disk makes Spring automatically reload an immutable bean.**
- Never place an IdP private key into the classpath or SP repository.

**Phased changes:** Phase 0 has only the `idp-signing-old.crt` entry; Phases 1–2 keep both entries; Phase 3 keeps only `idp-signing-next.crt`. Each change must roll out to all nodes, be tested, and avoid any brief window where the SP does not trust the key the IdP is actively using.

Domains here are **examples**, not real endpoints you can use out of the box. When running against a test IdP, use certificates supplied by the IdP from a verified source and update real entityIDs/ACS/SSO URLs.

### 6.2. When IdP metadata is the configuration source

Spring Security can build `RelyingPartyRegistration` via `RelyingPartyRegistrations.fromMetadataLocation("https://...")`. When IdP metadata is properly governed and publishes two signing certificates, the parser can populate both into verification credentials.

Still, distinguish:

1. **Loading metadata at startup** does not mean an automatic refresh mechanism exists when the IdP updates XML.
2. **HTTP metadata with a valid TLS certificate** does not automatically authorize every new key inside XML as trusted without source/policy checks.
3. **Metadata XML containing a Signature element** does not guarantee Spring verified the signature if you have not configured verification credentials/trust anchor for the metadata itself.
4. **A caching/refreshing repository** must be empirically tested for TTL, reload, outage fallback, signature validation, and atomic updates.
5. **Metadata URIs** must never come directly from browser/tenant input for backend fetching; control URLs, redirects/SSRF, and network egress.

Spring Security docs provide `AssertingPartyMetadataRepository` and `OpenSaml5AssertingPartyMetadataRepository` implementations backed by metadata resolvers that refresh per expiry. The docs also warn that when calling metadata signature verification APIs **without supplying verification credentials**, metadata signatures may **not be verified**. Thus `fromTrustedMetadataLocation`/a trusted URL is no magic wand guaranteeing all XML signatures are checked per your policy.

**Recommended policy:** Use signed metadata and an independently managed trust anchor when required by federation; pin issuer, source URL/egress; review diffs and require change approval when a new signing key appears. Metadata refresh results must map to the **exact tenant's registration**, never updating keys from IdP A into IdP B.

## 7. Java 17+/Spring Security example: two verification credentials

In a Java 17+ Spring Boot app with `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-security-saml2-service-provider`, you can construct `RelyingPartyRegistrationRepository` explicitly.

File `src/main/java/com/example/federation/SamlTrustConfig.java`:

```java
package com.example.federation;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTrustConfig {

    static X509Certificate certificate(String resource) throws Exception {
        try (InputStream in =
                 new ClassPathResource(resource).getInputStream()) {
            return (X509Certificate)
                CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() throws Exception {
        X509Certificate oldCert =
            certificate("saml/idp-signing-old.crt");
        X509Certificate newCert =
            certificate("saml/idp-signing-next.crt");

        // Both certificates must be approved for the SAME IdP.
        Saml2X509Credential oldVerification =
            Saml2X509Credential.verification(oldCert);
        Saml2X509Credential newVerification =
            Saml2X509Credential.verification(newCert);

        RelyingPartyRegistration partner =
            RelyingPartyRegistration.withRegistrationId("partner")
                .entityId(
                    "https://app.example.org/saml2/service-provider-metadata/partner")
                .assertionConsumerServiceLocation(
                    "https://app.example.org/login/saml2/sso/partner")
                .assertingPartyMetadata(idp -> idp
                    .entityId("https://sso.partner.example/issuer")
                    .singleSignOnServiceLocation(
                        "https://sso.partner.example/saml/sso")
                    .verificationX509Credentials(credentials -> {
                        credentials.add(oldVerification);
                        credentials.add(newVerification);
                    }))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**How to read it:**

- `Saml2X509Credential.verification(...)` creates a credential **for verification**; it does not create an AuthnRequest signing key.
- `verificationX509Credentials(...)` takes a collection; add both `oldVerification` and `newVerification` to the registration of the right IdP. Spring Security/OpenSAML uses the credential set during message verification per implementation/version.
- Default `saml2Login` filters and ACS continue working; changing the certificate set **does not require writing a controller to parse Base64 XML manually**.
- This snippet reads files **when constructing the bean**; during retirement, replace the bean/redeploy per procedure. Never merely delete `idp-signing-old.crt` on disk while the bean still holds the certificate in memory.
- Real certificate files and an approved test IdP are needed; this is **integration code inside a Spring project**, not a standalone program compiling with `javac` without Spring dependencies.
- If `AuthnRequest` signing is needed per IdP policy, add a dedicated **SP signing credential** and matching protocol config; **never** take one of the IdP's verification credentials to sign.
- `SecurityFilterChain` here illustrates enabling SAML; real apps must expose required login/AuthnRequest/ACS/metadata endpoints and protect business resources per policy. Spring SAML filters run before assigning Authentication; **never bypass** signature/issuer/audience validation.
- Across Spring Security major versions, builder/provider APIs can change; check your exact version's Spring Security reference/API and run integration tests before deploying.

### 7.1. What does the Spring code above NOT do?

It **does not**:

- Automatically verify the new SHA-256 fingerprint against change management tickets.
- Automatically fetch or verify metadata signatures, refresh caches, or enforce rollback/retirement dates.
- Enforce custom policies for X.509 expiry, key strength/algorithms, or issuer DNs if required by the organization.
- Guarantee every pod/region receives the update at the exact same moment.
- Invalidate SAML sessions already established before a certificate was revoked.
- Distinguish IdP-initiated flows lacking `InResponseTo`; the SP must decide that separately.

Those belong to **operations, governance, and additional security policy**. A two-certificate list is merely the **technical mechanism** for overlap, not a replacement for a key rotation plan.

## 8. Standalone Java 17: the principle of accepting two public keys

To understand precisely how "both old and new keys verify", the example below uses RSA/SHA-256 from JDK 17. The program generates two **simulated** key pairs, signs the same test string with each private key, and verifies against the public key set across each phase.

**This is purely a cryptographic signature illustration**; **it does not build SAMLResponses, parse XML Signatures/canonicalization, use real certificates, or act as a SAML validator**. Never use this class in place of OpenSAML.

File `DualKeyVerificationDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.List;

public class DualKeyVerificationDemo {

    static byte[] sign(byte[] data, PrivateKey privateKey)
            throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(privateKey);
        signer.update(data);
        return signer.sign();
    }

    static boolean verifyWithAnyTrustedKey(
            byte[] data, byte[] signature, List<PublicKey> trusted)
            throws Exception {
        for (PublicKey key : trusted) {
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(key);
            verifier.update(data);
            if (verifier.verify(signature)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair oldKey = generator.generateKeyPair();
        KeyPair newKey = generator.generateKeyPair();
        KeyPair unknownKey = generator.generateKeyPair();

        byte[] message =
            "trusted-saml-fixture".getBytes(StandardCharsets.UTF_8);
        byte[] altered =
            "tampered-saml-fixture".getBytes(StandardCharsets.UTF_8);

        byte[] signedOld = sign(message, oldKey.getPrivate());
        byte[] signedNew = sign(message, newKey.getPrivate());
        byte[] signedUnknown = sign(message, unknownKey.getPrivate());

        List<PublicKey> oldOnly = List.of(oldKey.getPublic());
        List<PublicKey> overlap = List.of(
            oldKey.getPublic(), newKey.getPublic());
        List<PublicKey> newOnly = List.of(newKey.getPublic());

        System.out.println("oldBefore=" +
            verifyWithAnyTrustedKey(message, signedOld, oldOnly));
        System.out.println("newBefore=" +
            verifyWithAnyTrustedKey(message, signedNew, oldOnly));
        System.out.println("oldDuring=" +
            verifyWithAnyTrustedKey(message, signedOld, overlap));
        System.out.println("newDuring=" +
            verifyWithAnyTrustedKey(message, signedNew, overlap));
        System.out.println("unknownDuring=" +
            verifyWithAnyTrustedKey(message, signedUnknown, overlap));
        System.out.println("tamperedDuring=" +
            verifyWithAnyTrustedKey(altered, signedNew, overlap));
        System.out.println("oldAfter=" +
            verifyWithAnyTrustedKey(message, signedOld, newOnly));
        System.out.println("newAfter=" +
            verifyWithAnyTrustedKey(message, signedNew, newOnly));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 DualKeyVerificationDemo.java
java DualKeyVerificationDemo
```

Exact stdout (although RSA keys are generated randomly, boolean outcomes are deterministic):

```text
oldBefore=true
newBefore=false
oldDuring=true
newDuring=true
unknownDuring=false
tamperedDuring=false
oldAfter=false
newAfter=true
```

Results illustrate the lifecycle:

- `oldBefore=true`: initial state trusting K_old.
- `newBefore=false`: IdP switching to K_new too early fails.
- `oldDuring=true` and `newDuring=true`: the genuine overlap window.
- `unknownDuring=false`: **dual trust does not mean trust all**.
- `tamperedDuring=false`: messages altered after signing fail.
- `oldAfter=false` and `newAfter=true`: K_old retired after the rotation window.

**Never treat "signature valid" as the entire login decision:** SAML XML must still pass issuer/audience/recipient/time/InResponseTo/replay and signed-structure checks. The demo program simulates none of those validators.

## 9. IdP metadata refresh approach: controlled key synchronization

When IdP metadata is the **source of truth**, the SP can update keys from approved XML instead of baking individual certificates into binaries. This works well for multi-partner federations, yet does not guarantee all security controls automatically.

### 9.1. Fetch/refresh model

```text
Scheduled job / metadata resolver
       |
       | GET fixed HTTPS metadata URI of the exact IdP
       v
[Restrict URL, redirects, DNS/egress, timeout, payload size]
       |
       v
[Safe XML parse + verify issuer/metadata signature]
       |
       v
[Compare C_old, C_new fingerprints against policy/approvals]
       |
       v
[Verify KeyDescriptor use=signing, SSO endpoint, validUntil]
       |
       v
[Staged trust set: {C_old,C_new}]
       |
       v
[Atomic publish/refresh RelyingPartyRegistrationRepository]
       |
       v
[Smoke tests and monitoring per tenant/region]
```

**Critical note on metadata signatures:** The SAML metadata's own signature must be verified using an **independent trust anchor** if using signed metadata. Never extract a new certificate from **unverified metadata** to verify that very metadata file; doing so lets an attacker self-sign a forged file. When not using signed metadata, enforce equivalent source authentication, approvals, and change controls per policy.

### 9.2. Related Spring Security APIs

- `RelyingPartyRegistrations.fromMetadataLocation(...)`: initializes from a metadata location; useful, yet **does not by default provide scheduled refresh and rollover risk controls**.
- `AssertingPartyMetadataRepository`: abstraction managing asserting-party metadata separately from SP registration.
- `OpenSaml5AssertingPartyMetadataRepository`: can use an OpenSAML MetadataResolver to refresh per expiry; verify exact version and builder.
- `CachingRelyingPartyRegistrationRepository`: can cache registrations, yet you must understand TTL/cache invalidation when metadata changes.
- `RelyingPartyRegistrationRepository`: each login must fetch the exact registration holding the **active key set**; avoid stale repository caches on some nodes.
- `saml2Metadata(...)`: publishes the **SP's** metadata; it does not auto-update IdP signing certificates.

Spring Security docs show you can configure verification credentials for metadata signatures while warning that if you do **not** supply credentials, the API may skip signature validation. Operations teams must verify actual behavior via integration tests, never guessing from an API name like "trusted".

### 9.3. Never accept every metadata change at once

Updating `KeyDescriptor use="signing"` is the intended rollover change. Yet if the same metadata update suddenly alters:

- the IdP's `entityID`,
- `SingleSignOnService` Location to a new domain,
- `SingleLogoutService` endpoints,
- other KeyDescriptor types,
- metadata signature trust anchors,
- tenant/registration mappings,

then **review each separately**. Never "approve all diffs" just because a cert is rotating. A valid metadata refresh does not mean a new issuer and new SSO endpoint are automatically trusted. This prevents abusing a rotation event to shift federation boundaries.

### 9.4. When refresh fails

If the metadata URL times out, returns an unexpected 30x, has invalid XML signatures, or is expired:

1. Never follow unapproved redirects or enable TLS trust-all.
2. Keep the last-known trust state **only when** policy allows using an approved and still-valid version; otherwise fail closed.
3. Alert with the exact partner, error, and node, without logging raw SAMLResponses/secrets.
4. Never arbitrarily drop C_old or accept an unverified C_new to "fix" logins.
5. Restore a previously approved metadata version or wait for the corrected metadata; enforce cache time bounds and rollback plans.

## 10. Testing the overlap phase: must emit both old and new signatures

### 10.1. Which layer to test at?

Calling `Signature.verify()` against two public keys only tests math. You need **real SAML integration tests** with a test IdP emitting SAMLResponses/Assertions signed with the corresponding private keys, while issuer, audience, recipient, request correlation, and timestamps remain valid.

Execute in a sandbox:

1. Create two separate test key pairs on the test IdP and deliver public certificates through a trusted channel.
2. Configure the SP to trust only the old cert; run SP-initiated login using the old key.
3. Add the new cert to the SP before the IdP switches; confirm **both old and new are accepted** on all nodes.
4. Switch the test IdP to sign with the new key; confirm SSO succeeds.
5. Remove the old cert from the test SP; confirm messages signed with the old key are rejected.
6. Sign with a key not belonging to the IdP; confirm the SP rejects even if `Issuer`/`Audience` look right.
7. Verify a valid signature with wrong `Audience`/`Recipient`/`InResponseTo` is still rejected.
8. If using SAML Single Logout, test LogoutRequest/LogoutResponse signed by the IdP's active key too, not just login.

**Never edit signed raw XML to test audience and draw conclusions from a signature error.** Change the claim at the test IdP or fixture builder and re-sign with the test private key; otherwise you only prove a broken checksum/signature.

### 10.2. Mandatory state matrix

| Phase | Message signing key | SP trust set | Outcome for otherwise valid assertion |
| --- | --- | --- | --- |
| Before overlap | K_old | `{C_old}` | **Accept** |
| Before overlap | K_new | `{C_old}` | **Reject** |
| During overlap | K_old | `{C_old,C_new}` | **Accept** |
| During overlap | K_new | `{C_old,C_new}` | **Accept** |
| During overlap | K_unknown | `{C_old,C_new}` | **Reject** |
| During overlap | K_old yet different SP issuer | `{C_old,C_new}` | **Reject** due to issuer/registration |
| During overlap | K_new yet different SP audience | `{C_old,C_new}` | **Reject** due to audience |
| During overlap | K_new yet wrong recipient/ACS | `{C_old,C_new}` | **Reject** due to destination/subject confirmation |
| During overlap | K_new with expired assertion | `{C_old,C_new}` | **Reject** due to time |
| During overlap | K_new with wrong InResponseTo | `{C_old,C_new}` | **Reject** per correlation |
| After retirement | K_old | `{C_new}` | **Reject**, even though old signature once worked |
| After retirement | K_new | `{C_new}` | **Accept** |
| Any phase | Self-signed K_new metadata with wrong metadata trust anchor | Metadata validation | **Do not update** trust set |
| Any phase | New cert from another tenant | IdP A trust set | **Do not accept** |
| Any phase | Unsigned SAMLResponse or invalid signature | Any | **Reject** |

"Accept" is valid only when **all other SAML checks** pass and the app's policy authorizes the user/claims. Never compare solely HTTP 302/200 statuses: failed logins can also redirect back to a login page. Evidence must be an **authenticated session properly created** or authentication failing as expected.

### 10.3. Checking across multiple nodes/regions/tenants

A multi-pod SP can end up with mismatched trust sets due to rolling deployments or caching. Tests must ensure:

- Every node loaded C_new before the IdP switch time.
- No region/tenant was missed in updates.
- Blue/green deployments and image rollbacks do not revert the trust set to `{C_old}` after T1.
- ConfigMap/secret/classpath/repository caches genuinely refreshed; verify effective runtime state rather than merely seeing a new file on disk.
- Background jobs handling SAML logout or other SAML messages also received updated certificates.
- Rollover deploys independently per IdP/tenant; updating IdP A's trust set must not affect IdP B.

If using canary rollouts, increase traffic only after testing both keys. Before the IdP starts signing with the new key, **all nodes serving real logins** must be ready, not just a 1% canary.

## 11. Logging and metrics sufficient to conclude "ready"

Record operationally useful fields:

```text
timestamp_utc
registration_id
verified_idp_entity_id
trust_set_version
approved_certificate_fingerprint_sha256
signature_verification_result
failure_category
deployment_version
node_or_region
authentication_result
metadata_refresh_age
```

**Never log** private keys, raw SAMLResponse/SAMLAssertion, sensitive NameIDs/emails, session cookies, or entire metadata documents if they contain non-public info. The **public** certificate fingerprint is helpful for seeing which key verified a request, yet recording "key used" must come from the provider that actually verified it, **not merely reading unverified KeyInfo from the request**.

Some Spring/OpenSAML APIs do not directly expose "selected certificate" on default authentication events; instrument at the appropriate provider/metadata/trust service layer, or rely on smoke tests and config trust-set versions. **Never infer which certificate was used solely from a fingerprint inserted by the sender into untrusted XML.**

Baseline metrics:

- Count/rate of **successful** SAML logins per registration/region.
- Signature/trust failures per IdP and key rotation window.
- Last successful metadata refresh, TTL, and count of nodes running the new trust-set version.
- Validity dates of old/new certificates and days remaining until retirement deadline.
- Count of valid SAML requests using the old key after cutover, if measurable reliably.
- Completion timestamp for removing C_old across all SPs and evidence that old-signed messages are rejected.
- High-severity alerts if an unknown certificate appears or metadata issuer/SSO endpoints change unexpectedly.

## 12. Critical distinction: scheduled rotation vs. key compromise response

### 12.1. Planned rotation

Overlap with a deadline is acceptable because K_old **is not considered compromised**. The goal is preserving availability while ensuring the trust set holds only two vetted keys. Upon completion, K_old must be retired.

### 12.2. Suspected compromise of old IdP private signing key

This is **not** a situation to keep both keys to avoid downtime. If K_old is suspected compromised, someone holding the private key can forge assertions. Prioritize **containment**:

1. Trigger incident response, verify scope/IdP systems, and notify all SP owners.
2. **Remove C_old from the SP trust set as rapidly as incident severity demands**, even if it temporarily disrupts SSO; never maintain indefinite overlap for a compromised key.
3. IdP stops using/revokes K_old and activates verified K_new; SP confirms C_old is no longer trusted in any node/cache.
4. Check whether IdP/metadata signing trust was also affected; if the metadata distribution trust anchor was exposed, replace/verify via an independent channel instead of trusting current metadata.
5. Audit sessions created with potentially forged assertions and consider revoking/forcing re-authentication per scope, logging evidence without PII.
6. Investigate IdP intrusion and preserve forensic evidence; avoid prematurely concluding "only K_old leaked" without proof.
7. Restore service once the new trust chain and all SAML checks are verified.

**Priority:** During a compromise, **authentication integrity outweighs avoiding all disruption**. Never enable "skip signature validation", "accept any certificate", or "trust XML-embedded certs" to reduce login errors.

### 12.3. Certificate nearing expiry without key compromise

An approaching certificate expiry is a signal to schedule rotation, not inherently a compromise. When an application is not yet ready for C_new and C_old is about to expire, a **planned maintenance window** may be needed instead of breaking policy. Never alter system clocks or indefinitely relax certificate-validity checks just to keep using an old key.

## 13. Common mistakes during rollover

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Only some users fail login after cutover | Different SP pods/regions/tenants still run the old trust set | Check trust-set version per node, rollout/cache/rollback |
| IdP rotated cert; SP reports invalid signature | C_new missing from `verification.credentials`, wrong cert, or assertion signed with another key | Compare IdP-confirmed fingerprint; check exact IdP/registration and real cert |
| Spring uses new cert yet still rejects | Issuer, audience, recipient, destination, time, replay, or signature algorithm failed | Diagnose each validator; do not blindly blame the cert |
| Metadata has two certs yet SP uses only one | Parser/config picks only first KeyDescriptor, cache/repository not refreshed, or code overwrote collection | Inspect effective registration, metadata parser, and verification credentials set |
| C_new added yet SAML login still fails before switch | SP signing key confused with IdP verification key, or YAML indented at wrong level | Separate SP signing/decryption from IdP verification |
| New certificate fingerprint differs from ticket | Wrong metadata version, spoofing, or wrong tenant | Halt key import, verify out-of-band, and require approval |
| XML metadata fetched over HTTPS yet trust changed oddly | Metadata signature/trust anchor unchecked, compromised source, or redirect | Govern trusted URLs/metadata signatures/egress; review diffs |
| Old cert removed yet old signatures still verify | A node/cache still holds C_old; rollback restored cert; test hit wrong SP | Test old-signed on every node; inspect caches and versions |
| IdP switched to new signing key yet SAML logout fails | SLO messages still use old key or separate handler | Include SLO in test matrix and decommission schedule |
| "Certificate expired" error | Validity policy blocks a cert, NTP drift, or rollover too late | Inspect X.509 timestamps, UTC time, and rotation schedule |
| Login succeeds yet permissions are wrong | Group/attribute mapping or app authorization bug, independent of certificate | Check permissions for the verified issuer/tenant |
| Switched to K_new yet used unsupported algorithm | Incompatible signature algorithm/KeyInfo/provider policy | Align on RSA/ECDSA, digest/signing algorithms, and profiles before cutover |
| Trust set contains the same cert twice | Duplicate metadata/unclean config merge | Dedupe by public cert fingerprint while preserving source audit |
| Old certificate remains in artifacts/source control | Incomplete decommission or build cache | Remove from config/classpath/repo, rebuild/redeploy, and check effective trust |

**Diagnostic flow:**

```text
Did the exact SAMLResponse reach HTTPS ACS?
    |
    v
Right registration + IdP entityID?
    |
    v
Does SP have approved C_old/C_new in its trust set?
    |
    v
Does signature on message/assertion pass key, algorithm, and XML checks?
    |
    v
Do Audience / Recipient / Destination / InResponseTo / time all pass?
    |
    v
Does app create Authentication/session?
    |
    v
Are permissions/tenant/roles right?
```

This order prevents confusing **key integration errors** with **user/authorization errors** or **reverse proxy issues**.

## 14. Operating multiple IdPs and protocols in one system

Spring Security can simultaneously accept SAML from multiple IdPs and OIDC from other OPs. Each discovers keys differently:

- **SAML IdP:** public X.509 signing certificates configured in metadata/registration; can carry **two `KeyDescriptor use="signing"`** during overlap.
- **OIDC/JWT:** OP publishes `jwks_uri` with multiple JWKs; verifiers typically pick keys by `kid`/alg/trusted issuer and still validate `iss`/`aud`/`exp`. Never apply JWT `kid` logic directly to SAML XML Signatures.
- **CAS:** service validation trusts dedicated server/certificate/transport, lacking SAML-style X.509 assertion signing by default.

In SAML, `<ds:KeyInfo>` inside a message may carry certificate/key identifier info, yet that is data **from the received message**. It can serve as a lookup hint, **never replacing** the trusted public key set for the issuer.

If the application acts as an identity broker, rotate **inbound** keys (verifying IdP assertions) and **outbound** keys (broker signing tokens/assertions for downstream RPs) on two separate schedules. Never build a single global trust set across all partners.

## 15. Repeatable hands-on lab

### 15.1. Preparation

1. Set up a test SAML IdP with two separate key pairs and public certificates `C_old`/`C_new`.
2. Set up a test Spring Boot SP with stable `entityID`, `ACS`, and IdP issuer configuration.
3. Register the SP at the IdP and enable Response/Assertion signing as needed.
4. Record SHA-256 fingerprints of both certificates via `keytool -printcert`.
5. Prepare test user data, isolated browser sessions, and logging that never leaks SAML assertions.
6. Define QA gates: all old-signed/new-signed tests behave right per phase, unknown keys are always rejected, and audience/recipient/correlation keep working.

### 15.2. Execution

**Phase 0:** SP trusts only C_old. Logins signed with old succeed; signed with new are rejected.

**Phase 1:** SP trusts both C_old+C_new. Test old-signed/new-signed across all nodes; users need not switch accounts and SP rejects other issuers.

**Phase 2:** IdP signs with K_new. Test full browser SSO, allowed in-flight old-signed messages, session continuity, and SLO. Monitor for at least the approved rotation window.

**Phase 3:** SP trusts only C_new. Test new-signed succeeds and old-signed fails. Audit repositories/classpath/caches/container images so C_old is completely gone from trusted lists; final metadata advertises only C_new.

### 15.3. Deliverables for sign-off

A complete record containing:

| Item | Evidence |
| --- | --- |
| IdP entityID, SP entityID/ACS | Values in verified metadata |
| SHA-256 fingerprints | `C_old` and `C_new` from authoritative sources |
| Timeline | Issue date, prepublish, SP dual trust, IdP switch, retirement |
| SP/node inventory | Before/after trust-set version status |
| Old-signed and new-signed tests | Pass/fail per phase, with method/binding |
| Unknown/unauthorized cert negative test | Rejected, no session created |
| SAML validation negative tests | Audience/recipient/issuer/time/replay rejected |
| Monitoring | No spike in auth failures after cutover |
| Metadata refresh/trust anchor | Confirmed metadata source and signature if applicable |
| Incident/rollback policy | Rollback criteria, stop-go gates, and owners |
| Retirement evidence | C_old absent from active trust set across all nodes |

## 16. Production checklist and completion criteria

- [ ] Verified exact IdP/registration/tenant for every certificate; never import certs from untrusted messages.
- [ ] Both `C_old` and `C_new` are the IdP's **public signing certificates**, with independently approved fingerprints.
- [ ] IdP prepublishes C_new while still signing with K_old, avoiding switching keys before SPs are ready.
- [ ] SP accepts C_old+C_new concurrently only during a **deadlined** window; never broaden issuer/ACS/permissions.
- [ ] Every pod/region/tenant/cluster runs the new trust-set version before IdP cutover.
- [ ] Tested actual old-signed and new-signed SAMLResponses, not just XML/YAML files.
- [ ] Signatures from unknown keys rejected; audience/recipient/issuer/time/InResponseTo remain enforced.
- [ ] Metadata refresh has a trusted source, URL/SSRF limits, proper signature/trust anchor, and diff auditing.
- [ ] Certificate validity, algorithms, key sizes, and clocks enforced per policy; never treat XML verification as full PKIX validation.
- [ ] Controlled rollback mechanism exists, distinguishing compromised-key cases (no overlap).
- [ ] After cutover + grace period, C_old removed from all trust sets, caches, and artifacts; old-signed negative test fails.
- [ ] Monitoring covers expiry/refresh/rotation, with clear owners and emergency runbook if IdP signing key leaks.
- [ ] Never log raw SAMLResponses, private keys, cookies, or personal data; audit only what is needed.
- [ ] Close change ticket with smoke test results and final state `{C_new}`.

**In short:** Safe IdP signing certificate rotation is a **two-party coordinated process**, not just renaming an X.509 file. The IdP **publishes the new key before using it**, the SP **accepts two verified public keys during the overlap window**, the IdP **switches signing**, and the SP **observes and finally retires the old key**. Key compromise must be handled as a security incident with immediate risk-based revocation, never an extended overlap. Spring Security supplies the multi-credential mechanism; **timing, trust sourcing, synchronization, testing, and retirement** remain operational responsibilities.

## 17. Reference documentation

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `RelyingPartyRegistration`, asserting-party verification credentials, metadata, and endpoints.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — parsing IdP metadata, `AssertingPartyMetadataRepository`, signature validation, and refresh.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — verifying assertions, providers, and extension points.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — differences between SP signing credentials and asserting-party keys.
- [Spring Boot — SAML2 Relying Party Configuration](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html) — `assertingparty.verification.credentials` syntax.
- [Microsoft Entra ID — Manage federation certificates](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/tutorial-manage-certificates-for-federated-single-sign-on) — guidance on preparing new keys, dual certificate rollover, and validity windows.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html) — protecting signing keys and metadata sources.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — `EntityDescriptor`, `KeyDescriptor`, and metadata trust.
- [Java 17 CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html) — reading public X.509 certificates.
- [Java 17 Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — API for signing and verifying signatures in the crypto demo.
