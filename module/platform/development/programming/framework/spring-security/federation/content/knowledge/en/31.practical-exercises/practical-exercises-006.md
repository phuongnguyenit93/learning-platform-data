# Rotating IdP and Service Provider Certificates While Preserving Login

> **Module:** Spring Security – federation. **Parent topic:** Comprehensive Practice. This lab handles the key/certificate rotation lifecycle of a **SAML 2.0 Identity Provider (IdP/Asserting Party)** and **Service Provider (SP/Relying Party)** with a Spring Security application. The goal is to stage new trust **before** switching the active message-signing key, support an OLD+NEW overlap, preserve in-flight transactions, and verify real federated login/logout without relaxing validation. Examples use **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x** on the Servlet stack. URLs, entityIDs, aliases, and certificate paths in this article are sandbox data; never use production private keys.

## 1. Objectives and Scope Principles

After this lesson, you should be able to:

1. Distinguish **IdP signing certificate**, **SP signing certificate**, **SP encryption/decryption certificate**, **metadata-signing certificate**, and **TLS HTTPS certificate**; know who holds each private key and who needs each public certificate.
2. Design the five stages **baseline → pretrust/prepublish → activate → stabilize → retire** for each key-rollover direction.
3. Ensure that when **the IdP switches signers**, the SP already trusts NEW; when **the SP switches signers**, the IdP already trusts NEW; when **the SP switches encryption certs**, all SP instances already hold private decrypt NEW before the IdP encrypts with NEW.
4. Inspect `EntityDescriptor/@entityID`, `KeyDescriptor use=signing/encryption`, `AssertionConsumerService` (ACS), `SingleLogoutService` (SLO), `SingleSignOnService` (SSO), bindings, `AuthnRequestsSigned`, and the actual signer.
5. Configure Spring Security `RelyingPartyRegistration`, `assertingparty.verification.credentials`, `signing.credentials`, and `decryption.credentials`; understand the difference between updated metadata on a URL and a reloaded runtime repository.
6. Distinguish rotating an **X.509 certificate with the same public/private key** from rotating an **actual keypair**; never assume changing Subject/NotAfter means verifiers are ready.
7. Verify SAML signatures, Issuer, Audience, Recipient, Destination, `InResponseTo`, `RelayState`, `NameID`, `SessionIndex`, SLO, time/replay, and encrypted Assertions during overlap.
8. Run Java 17 `SamlRolloverPlanner.java` simulating release gates with deterministic stdout, understanding the model does not replace real XML Signature validation.
9. Set up a sandbox IdP capable of signing messages with both OLD and NEW, running positive/negative tests across all nodes, tenants, browsers, and sign/decrypt directions.
10. Prepare canary, monitoring, rollback, and emergency key-compromise response; never trade security for a "zero downtime" slogan.

**Prerequisites:** SAML 2.0 Web Browser SSO, SP–IdP metadata, AuthnRequest/Response/Assertion, LogoutRequest/Response, HTTP POST/Redirect bindings, XML Signature/Encryption, X.509, Spring Security Servlet sessions, Java 17, and Kubernetes/secret management.

**Definition of "preserving login":** valid SSO/SLO transactions before/during/after rotation still validate when permitted by policy, existing HTTP sessions are not broken merely by deploying new trust, and rollback remains feasible within an approved window. It does **not** force accepting compromised keys, expired assertions, disabled users, or keeping every device logged in forever.

## 2. Key-Role Map in SAML Federation

~~~text
               IdP: https://idp.test.example.org/saml
                 owns PRIVATE IDP-SIGNING KEY
                            |
     signs SAMLResponse/Assertion/LogoutRequest/LogoutResponse
                            v
                      Browser roundtrip
                            |
                            v
               Spring SP: urn:portal:prod:sp
               verifies using IDP PUBLIC cert(s)

 Spring SP owns PRIVATE SP-SIGNING KEY
           |
           +-- signs AuthnRequest/LogoutRequest/LogoutResponse -->
               IdP verifies using SP PUBLIC cert(s)

 IdP encrypts Assertion using SP PUBLIC ENCRYPTION certificate
           |
           v
 Spring SP decrypts using SP PRIVATE DECRYPTION key
~~~

| Secret / Certificate | Private Key Owner | Public Cert Needed By | Direction to Test |
| --- | --- | --- | --- |
| IdP SAML signing | IdP | SP verification trust list | IdP-signed Response/Assertion, SLO messages → SP |
| SP SAML signing | SP | IdP SP-verification trust list | SP-signed AuthnRequest/LogoutRequest/LogoutResponse → IdP |
| SP SAML encryption | SP | IdP encryption config / SP metadata | IdP encrypts Assertion/NameID → SP decrypts |
| Metadata signing | Metadata publisher | Consumer metadata trust store | Trusted import/refresh of metadata |
| HTTPS/TLS server certificate | Ingress / web server | Browser / JVM PKI trust | HTTPS transport/hostname; does not replace SAML signer |

**Never conflate them:** A TLS certificate for `portal.test.example.org` does not by default sign AuthnRequests; the IdP SAML signing certificate may differ from `idp.test.example.org`'s TLS certificate. One keypair may serve both signing and decryption per IdP/SP design, yet rollover operations must still be tested in **two independent directions**.

**Never equate certificate with keypair:** A new X.509 certificate can wrap the **same public key** or a brand-new keypair. Providers may pin the exact certificate fingerprint rather than the public key, so even "renew cert with same key" still requires testing/trust updates. On key compromise, **rotate the keypair**, never just issue a new certificate around the same compromised public key.

## 3. Ordering Rule: Receiver Ready Before Producer Switch

**IdP signer:** The SP must trust the IDP-NEW public cert **before** the IdP signs with IDP-NEW.

**SP signer:** The IdP must trust the SP-NEW public cert **before** the SP signs with SP-NEW.

**SP encryption:** The SP must install the matching private ENC-NEW key and test decryption **before** the IdP encrypts with the SP ENC-NEW public cert. The SP keeps the ENC-OLD private key while older encrypted Assertions may still arrive.

~~~text
T0 BASELINE
  Producer uses OLD
  Receiver trusts/can-decrypt OLD

T1 PREPARE
  NEW keypair generated, secrets isolated, metadata approved
  Receiver trusts/can-decrypt OLD + NEW
  Producer still uses OLD

T2 ACTIVATE
  Producer switches to NEW
  Receiver still accepts OLD + NEW

T3 OBSERVE
  Test every IdP tenant, SP node, browser and SSO/SLO binding
  Keep OLD where in-flight messages/rollback require it

T4 RETIRE
  OLD no longer produced, no outstanding OLD messages
  Receiver removes OLD according to security policy
  Old secret revoked/removed after approval
~~~

**Do not rely on fixed arbitrary timers** such as "delete OLD after 24 hours". The overlap window must account for metadata cache TTL, IdP replication, SAML Response/LogoutResponse browser transit time, MaxAge/clock skew, session/request repository TTL, secret propagation across nodes, rollback capability, and certificate lifetime.

**Common misconception:** "Metadata contains the NEW cert" does **not** mean "the IdP is signing with NEW", "the SP reloaded and trusts NEW", or "every region is ready". Proof must come from effective trust sets and actual signature verification.

## 4. Baseline for an SP–IdP Registration

Sandbox fixture:

~~~text
registrationId          = corporate
SP entityID             = urn:portal:prod:sp
SP ACS                  = https://portal.test.example.org/login/saml2/sso/corporate
SP SLO                  = https://portal.test.example.org/logout/saml2/slo
IdP entityID            = https://idp.test.example.org/saml
IdP SSO                 = https://idp.test.example.org/sso
IdP SLO                 = https://idp.test.example.org/slo
IdP active signer       = IDP-OLD
IdP candidate signer    = IDP-NEW
SP active signer        = SP-OLD
SP candidate signer     = SP-NEW
SP decrypt OLD/NEW      = ENC-OLD / ENC-NEW
Signing verification    = exact SHA-256 fingerprints
Response binding        = HTTP-POST
AuthnRequest binding    = HTTP-Redirect (IdP policy)
SLO binding             = verify actual IdP metadata
Deployment              = 3 Spring Pods behind HTTPS ingress
Registration source     = in-memory/static at boot or refreshable repository
Session store           = shared or in-memory, document effective behavior
~~~

Each entry must list **issuer/entityID**, fingerprint, effective signing algorithm, NotBefore/NotAfter, current active status, tenant, trust metadata provenance, owner, target date, and test artifact ID. Never record private keys, raw SAMLRequest/SAMLResponse payloads, session cookies, real NameIDs, or tokens in workbooks or incident tickets.

### 4.1. Inventory of Sources

| Source | Content Taken | Never Taken |
| --- | --- | --- |
| IdP approved metadata | IdP issuer, SSO/SLO URLs, signing public certs, validUntil/cacheDuration | IdP private key |
| SP approved metadata | SP entityID, ACS/SLO URLs, public sign/encrypt certs | SP private keys |
| IdP admin registration | SP active/secondary trusted signers, encryption selection policy | Admin password |
| Spring effective RPR | Approved issuer, verifier fingerprints, SP signer/decrypt cert aliases | Raw credentials |
| Secrets manager | Secret version/alias, policy, mount path/permissions | Secret values put into logs |
| Browser + SP/IdP tests | Signed-by-OLD/NEW outcomes, correlation, session continuity | Raw bearer headers/cookies |
| Platform config | Nginx scheme/host, shared session store, replica versions | Access to unrelated tenant secrets |

**Metadata signatures:** If your organization uses signed federation metadata, verify the metadata signer/trust anchor **separately**. A new cert inside unverified metadata does **not** become trustworthy merely by appearing in XML. Even when fetched over HTTPS, verify the approved URL/entityID and metadata trust policy.

### 4.2. Properties That Must Stay Fixed When Only Rotating Certs

- SP `EntityDescriptor/@entityID` and IdP `EntityDescriptor/@entityID`—never change logical identity when Subject CN changes.
- IdP `SingleSignOnService.Location/Binding` and `SingleLogoutService.Location/Binding` unless intentionally migrating endpoints.
- SP `AssertionConsumerService.Location/Binding/index/isDefault` and `SingleLogoutService.Location`; public HTTPS host/port/path must remain accurate.
- `AuthnRequestsSigned`, `WantAssertionsSigned`, and actual signature requirements.
- `NameIDFormat`, AttributeStatements/groups, `AuthnContextClassRef`, and role mapping.
- Request correlation (`InResponseTo`/`RelayState`), time/replay checks, and session handling.
- IdP identity resolver per `registrationId`/tenant; never mix keys between IdP A and IdP B.

When only swapping keys, treat any other metadata difference as **drift**—never silently drop validation because a newer MetadataGenerator alters structure.

## 5. IdP Signing Certificate Rotation Procedure

### 5.1. Publish NEW While Keeping OLD Active

1. IAM generates the IDP-NEW keypair via an approved HSM/secret store, with a public certificate meeting crypto policy.
2. Verify SHA-256 fingerprint, NotBefore/NotAfter, key algorithm, signer alias/region, and approval.
3. Publish the IDP-NEW **public signing certificate** in IdP metadata/approved distribution if the provider supports dual certificates; keep IDP-OLD in trust overlap.
4. **The IdP continues signing with IDP-OLD** while SPs update trust.
5. The SP owner ingests IDP-NEW into the **matching `RelyingPartyRegistration`** of the registered issuer; never trust this cert for all IdPs or all tenants.
6. Every SP node reports an effective verifier set containing OLD+NEW and passes SSO/SLO tests signed by OLD and NEW.
7. Only when all SP nodes/tenants are ready does IAM activate the NEW signer on the IdP.

Illustrative IdP metadata (bytes omitted):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.test.example.org/saml">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate IDP-OLD -->
    </md:KeyDescriptor>
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate IDP-NEW -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.test.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**This is descriptive XML, not complete importable metadata**, as it lacks `ds:KeyInfo`/`ds:X509Certificate` and a metadata trust signature. In real metadata, `KeyDescriptor` can repeat. **Certificate order does not indicate which cert is active**; providers may track "active/secondary" in a separate UI/API.

### 5.2. Receiver SP Pretrust

~~~text
Before:
 SP approved IDP verification = [IDP-OLD]

During overlap:
 SP approved IDP verification = [IDP-OLD, IDP-NEW]

After safe retirement:
 SP approved IDP verification = [IDP-NEW]
~~~

The Spring Security verifier must use exact public keys from IdP metadata or approved static certificates. Never take `KeyInfo` from a browser-supplied SAMLResponse as a "new cert" to verify itself. A Response signed by IDP-NEW with the wrong Audience/Recipient must still be rejected even when the signer is trusted.

### 5.3. Active Switch and Observation

When the IdP switches to signing with NEW:
- New AuthnRequests still use approved SP issuer/ACS; the IdP returns signed `SAMLResponse`/`Assertion`, and the SP verifies IDP-NEW.
- If the IdP signs Response and Assertion with different keys during rollout, the SP must verify each signed element per policy.
- IdP-initiated `LogoutRequest` / RP `LogoutResponse` must be verified by the SP with approved IDP-NEW if the IdP uses the new signer for SLO.
- Existing authenticated Spring HTTP sessions are normally not invalidated solely because a verification cert changed; **new login tests** prove the new signer works.
- If a multi-region IdP has not converged, one region may still sign with OLD; trust overlap preserves continuity while per-region signer monitoring tracks convergence.

**Retire IDP-OLD** only when no issuer/node still signs with OLD, in-flight browser SAML POSTs/retries have drained, metadata refresh and SP trust have converged, rollback no longer needs OLD, and the Security owner approves. If OLD is compromised, prioritize revocation/incident response even if an outage occurs.

## 6. SP Signing Certificate Rotation

The SP signs `AuthnRequest` when required by the IdP, plus signed SLO messages per policy. Because the **IdP is the verifier**, the IdP must receive the NEW public SP cert **before** the SP signs with NEW.

### 6.1. Plan

1. SP owner generates the SP-NEW private/public keypair and mounts the secret securely for canary; record the public fingerprint.
2. Public SP metadata or IdP registration advertises SP-NEW (alongside SP-OLD if supported by the provider). The IdP trusts OLD+NEW during overlap.
3. **SP stays active signing with SP-OLD** while the IdP loads metadata/trust.
4. Sandbox IdP verifies signed AuthnRequests using SP-OLD and SP-NEW; production IdP effective trust status confirms readiness.
5. SP canary switches active signer to SP-NEW and emits real signed AuthnRequests. Verify signer fingerprint / IdP verification and accurate Issuer/Destination/binding/RelayState.
6. Verify signed `LogoutRequest`/`LogoutResponse` using NEW (if SLO is used).
7. Roll out remaining SP nodes, keeping OLD trust at the IdP until OLD traffic drains and the rollback window closes; then retire OLD.

| Phase | SP Active Signer | IdP Trusted SP Signers | Outcome |
| --- | --- | --- | --- |
| Baseline | SP-OLD | SP-OLD | Stable |
| Pretrust | SP-OLD | SP-OLD+SP-NEW | Zero disruption |
| Canary | Some SP-NEW, others SP-OLD | SP-OLD+SP-NEW | Both must verify |
| Full switch | SP-NEW | SP-OLD+SP-NEW | Monitor OLD in-flight |
| Retire | SP-NEW | SP-NEW | Only after drain/approval |

**Do not assume adding two `signing.credentials` entries to YAML automatically advertises a "primary vs. secondary" policy or picks NEW for signing.** Inspect actual signed AuthnRequests/LogoutRequests and effective SP metadata; you may need to prepublish the new cert via an approved IdP admin UI/metadata generator depending on version. If the IdP trusts only one signer, a coordinated cutover/change window may be necessary. Never promise zero downtime without dual-key support.

### 6.2. SLO Can Break Even When SSO Passes

An IdP might not require signed AuthnRequests yet still require signed LogoutRequests. If the SP signer rotates before the IdP trusts NEW, RP-initiated logout may clear the local session while the IdP rejects SLO. IdP-initiated flows also involve SP-signed LogoutResponses that the IdP must verify. Always test:

~~~text
SP -> IdP: AuthnRequest signed SP-NEW
SP -> IdP: LogoutRequest signed SP-NEW
SP -> IdP: LogoutResponse signed SP-NEW

IdP -> SP: SAMLResponse signed IDP-NEW
IdP -> SP: LogoutRequest signed IDP-NEW
IdP -> SP: LogoutResponse signed IDP-NEW
~~~

Check actual bindings and signature locations. With HTTP-Redirect binding, the signature may live in `SigAlg`/`Signature` query parameters; do not look solely for XML `ds:Signature` as in HTTP-POST.

## 7. SP Encryption/Decryption Rotation

The IdP uses the SP **public encryption certificate** to encrypt Assertions/NameIDs; the SP uses the matching **private decryption key**. Ordering differs from signing: **the SP must install the NEW private decrypt key on every instance before the IdP uses the NEW public encrypt cert**.

~~~text
T0: IdP encrypts ENC-OLD
    SP decrypts ENC-OLD

T1: SP installs ENC-NEW private key
    SP decrypts ENC-OLD + ENC-NEW
    IdP still encrypts ENC-OLD

T2: SP publishes new public ENC-NEW cert
    IdP registers/selects ENC-NEW under approved policy
    SP remains able to decrypt OLD + NEW

T3: IdP encrypts ENC-NEW
    SP decrypts OLD + NEW

T4: All old encrypted messages drained
    SP retires ENC-OLD private key safely
~~~

### 7.1. Caution When Publishing an Encryption Cert

Some IdPs automatically pick the first/last cert in `KeyDescriptor use=encryption`, or switch immediately upon ingesting metadata. Therefore **never publish NEW before all Pods can decrypt NEW**, unless you verified the IdP does not auto-switch. If an IdP does not support multiple encryption certs, **preinstall the NEW private key** and coordinate a single switch; retaining overlapping private keys on the SP still lowers risk.

**Do not delete ENC-OLD immediately:** a browser may still hold a `SAMLResponse` carrying an `EncryptedAssertion` created before T3 and POST the callback after T3. If the SP already deleted private OLD, decryption fails even though the IdP switched to encrypting with NEW. The same applies to `EncryptedAttribute`/`EncryptedID` and certain SLO messages.

### 7.2. Real Dual-Decrypt Tests

| Test | IdP Encrypts For | SP Available Keys | Expected |
| --- | --- | --- | --- |
| E1 | ENC-OLD | ENC-OLD+ENC-NEW | Decrypt, then validate signature/issuer/audience |
| E2 | ENC-NEW | ENC-OLD+ENC-NEW | Decrypt, validate |
| E3 | ENC-NEW | ENC-OLD only | Reject; no plaintext fallback |
| E4 | ENC-OLD | ENC-NEW only | Reject; simulates premature retirement |
| E5 | Unknown public key | ENC-OLD+ENC-NEW | Reject |
| E6 | ENC-NEW while Pod B lacks key | A passes, B fails → rollout blocked |
| E7 | Encrypted NameID using OLD | OLD+NEW | Decrypt per profile/policy |
| E8 | Signing key = encryption key pair | Rotated together | Test both directions independently |

**A Response that is signed only and unencrypted does not prove decryption rotation succeeded.** The sandbox IdP must generate actual encrypted Assertions for each public key.

## 8. Spring Security: Trust Set, Metadata, and Runtime

Spring Security models the SP–IdP relationship via `RelyingPartyRegistration`. `assertingparty.verification.credentials` holds IdP public keys for verification; `signing.credentials` holds SP private/public signing keys; `decryption.credentials` holds SP private/public decryption keys.

### 8.1. IdP Dual Verification in Spring Boot YAML

Configuration fragment for a Servlet app (requires `spring-security-saml2-service-provider` and a matching sandbox IdP):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:prod:sp"
            assertion-consumer-service-location: >-
              https://portal.test.example.org/login/saml2/sso/corporate
            assertingparty:
              entity-id: "https://idp.test.example.org/saml"
              singlesignon:
                url: "https://idp.test.example.org/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: >-
                      file:/run/trust/saml/idp-signing-old.crt
                  - certificate-location: >-
                      file:/run/trust/saml/idp-signing-new.crt
            signing:
              credentials:
                - private-key-location: >-
                    file:/run/secrets/saml/sp-signing-active.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-signing-active.crt
~~~

- `verification.credentials[]` lists two **approved public IdP signers** for the same IdP entityID; it contains no IdP private keys.
- `signing.credentials[]` holds the SP private + public signing key. The example declares only one **active** SP signer because how multiple credentials are ordered/selected depends on the implementation; never assume a YAML list defines publish vs. activate policy.
- `entity-id` and ACS preserve the federation contract and never change accidentally during rotation.
- If the IdP provides `assertingparty.metadata-uri`, clarify whether the app uses **metadata import** or static verification credentials as its source of truth; never assume configs auto-merge across all Boot versions.
- If you define a custom `RelyingPartyRegistrationRepository` bean, Boot auto-configuration may not apply static YAML as expected; verify effective runtime registrations.
- `singlesignon.sign-request=true` illustrates an IdP requiring signed AuthnRequests, which requires the IdP to trust the SP signing cert. Never toggle it arbitrarily to silence errors.

### 8.2. SP Dual Decryption

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            decryption:
              credentials:
                - private-key-location: >-
                    file:/run/secrets/saml/sp-decryption-old.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-decryption-old.crt
                - private-key-location: >-
                    file:/run/secrets/saml/sp-decryption-new.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-decryption-new.crt
~~~

Spring/OpenSAML can use multiple registered `Saml2X509Credential` decryption credentials to decrypt encrypted SAML elements. **Always test actual encrypted Responses with both public keys**, not merely application startup. When merging this YAML fragment, preserve the rest of the registration config in the full file so IdP issuer, SSO location, and signing trust are not overwritten.

### 8.3. SP Signing Active OLD and NEW: Two Rollout Versions

**Old active fragment:**

~~~yaml
signing:
  credentials:
    - private-key-location: file:/run/secrets/saml/sp-signing-old.key
      certificate-location: file:/run/secrets/saml/sp-signing-old.crt
~~~

**New active fragment:**

~~~yaml
signing:
  credentials:
    - private-key-location: file:/run/secrets/saml/sp-signing-new.key
      certificate-location: file:/run/secrets/saml/sp-signing-new.crt
~~~

These are fragments **under `registration.corporate`**, not complete files. When switching to NEW:
- The IdP trusted verification set already contains SP-NEW.
- Verify SP metadata publishes public certs as planned; if OLD+NEW must be published while the framework only advertises the configured active credential, coordinate via approved IdP upload / metadata publisher.
- Verify actual outbound signed `AuthnRequest`/`LogoutRequest` uses NEW, not merely the alias in the Secret.
- Ensure Pods reloaded the private key rather than keeping the old key in application memory.
- Test idempotent config rollout without losing `RelyingPartyRegistration` across restarts.

### 8.4. A Changed Metadata URL Does Not Auto-Reload Registrations

Calling `RelyingPartyRegistrations.fromMetadataLocation(...)` to build an `InMemoryRelyingPartyRegistrationRepository` normally fetches metadata at registration build time. Publishing NEW on the IdP's web URL afterward **does not guarantee** every Spring Pod auto-refreshes.

Intentional options:
1. **Static reload:** update approved local metadata/public certs and perform a rolling restart; verify every Pod's effective trust.
2. **Refreshable repository/cache:** use an API supported by your Spring Security version, managing cache TTL, refresh integrity, known-good fallback, and alerts; some versions support `CachingRelyingPartyRegistrationRepository` via supplier + cache.
3. **Managed config service:** publish updated registrations as immutable/versioned snapshots after approval; swap atomically and monitor.
4. **Pipeline-driven IdP metadata import:** fetch signed metadata from an approved endpoint, verify issuer/fingerprint, stage deployment, and test before activation.

**Never fetch metadata from an arbitrary client URL, never use trust-all TLS, and never treat a cert inside response `KeyInfo` as a dynamic trust anchor.** If refresh fails, fall back to known-good policy within approved bounds or fail closed; never trust an unknown signer to "keep things running".

### 8.5. `SecurityFilterChain` for the Sandbox

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain samlChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults())
        .saml2Logout(Customizer.withDefaults())
        .build();
}
~~~

This is a **code fragment** for a `@Configuration` class in a Spring Boot project with the Spring SAML2 dependency, not a standalone Java app. SLO requires IdP `SingleLogoutService`, SP signing credentials, and supported bindings. Watch filter ordering, endpoints, and authentication policies if the app also has form/OIDC login; never treat presence of the DSL as a signed E2E pass.

## 9. Comparing Metadata and Certificate Fingerprints

Real IdP/SP metadata may have multiple `KeyDescriptor`s; **never** compare only the first element or compare raw Base64 text with whitespace. Extract the DER certificate, compute its SHA-256 fingerprint, and compare signer roles and provenance.

### 9.1. Read-Only Public Cert Commands

~~~bash
# Public X.509 certificate, do not print private key:
openssl x509 -in idp-old.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer

openssl x509 -in idp-new.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer

openssl x509 -in sp-signing-new.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer
~~~

- SHA-256 fingerprints are computed over the DER certificate, not literal PEM text. PEM line wrapping may differ for the exact same certificate.
- `NotBefore`/`NotAfter` help check validity bounds and activation timing; how the framework checks expiry may depend on provider/policy. Never assume an expired cert is always accepted or always rejected.
- Public certs may be self-signed in SAML. A PKIX `openssl verify` failure against a CA trust store does not by itself prove federation trust is broken when the model uses approved certificate pinning. Always test the **actual SAML verifier** and policy.
- Verify public key algorithm, key size, and signature digest meet policy; never enable SHA-1/weak ciphers just to satisfy an IdP.
- Never print private keys with `cat`, `openssl pkey -text`, or copy `.p12`/`.key` files into Git, tickets, or logged terminals.

### 9.2. Metadata Fields to Review

| Field | Why |
| --- | --- |
| `EntityDescriptor/@entityID` | Fixes SP/IdP logical identity |
| `KeyDescriptor@use=signing` | Receiver holds old+new approved public signing certs |
| `KeyDescriptor@use=encryption` | IdP knows which cert encrypts for the SP |
| `validUntil`/`cacheDuration` | Cache freshness and metadata expiry |
| `Metadata XML signature` | Provenance; prevents attacker-injected certs |
| `SingleSignOnService.Location/Binding` | AuthnRequest Destination and supported binding |
| `AssertionConsumerService.Location/Binding` | Response Recipient/Destination and browser POST |
| `SingleLogoutService.Location/Binding/ResponseLocation` | SLO signed requests/responses target the right party |
| `AuthnRequestsSigned`/`WantAssertionsSigned` | Signing/verification policy is never weakened |
| `NameIDFormat` | Identity mapping does not drift |
| X.509 NotBefore/NotAfter/fingerprint | Cert lifecycle |
| Multiple KeyDescriptors | Overlap, algorithm/key-use, and provider behavior |

**Certificate rollover must never silently alter `entityID` or ACS.** An IdP may pin a signing certificate to an SP `entityID`; a different certificate Subject CN does not require changing `entityID`. Entity ID/endpoint changes must be separate federation change requests.

## 10. Preserving SAML Validation During Key Rotation

When the SP trusts both IDP-OLD and IDP-NEW, trust is widened **only across approved public keys**, not across SAML protocol checks.

| Check | Still Mandatory During Overlap |
| --- | --- |
| `Response.Issuer`, `Assertion.Issuer` | Exact trusted IdP entityID/registration |
| XML signature | Approved OLD or NEW public signing cert; no `KeyInfo` self-trust |
| `Assertion.AudienceRestriction` | Exact SP entityID |
| `Response.Destination` | Exact SP public ACS |
| `SubjectConfirmationData.Recipient` | Exact SP public ACS |
| `InResponseTo`/`RelayState` | Matches pending request in SP-initiated flow |
| `Conditions.NotBefore/NotOnOrAfter` | Time/clock skew per policy |
| `NameID`/`NameIDFormat` | Maps user per trusted IdP/tenant |
| `AuthnContextClassRef` | Assurance requirement never downgraded |
| `AuthnStatement.SessionIndex` | Matches session for SLO if used |
| Replay cache / request ID | Prevents reuse of signed Assertions |
| Encryption | OLD/NEW private decrypt keys match what the IdP actually uses |

**Signed-by-NEW cannot rescue a Response with the wrong Audience/Recipient.** To test Audience independently, the sandbox IdP must generate and **re-sign** a Response with the wrong Audience using the NEW private key. Editing XML after signing fails at signature checking first and does not prove the Audience validator works.

**Unsolicited/IdP-initiated SSO:** May omit `InResponseTo` per profile if the IdP initiates the flow; test under explicit policy. Never disable correlation across SP-initiated flows just because one IdP lacks request state.

**Metadata signing vs. message signing:** If metadata is signed by cert M while Assertions are signed by cert A, rotating A does not automatically rotate M. Metadata refreshes must verify the metadata trust anchor; never extract public key A from **unverified** metadata to bootstrap metadata trust.

## 11. Key Rotation and User Session Continuity

An authenticated HTTP session normally stores Spring's `SecurityContext`/`Authentication`; the server **does not re-receive a SAMLResponse on every HTTP request**. Consequently, an IdP signer rollover normally **does not log out existing sessions**. However, a redeploy/restart can drop HTTP sessions **if the app uses an in-memory session store**.

Tests must separate:
1. **Existing session continuity:** QA user logs in with IDP-OLD, retain an anonymized session fingerprint; deploy dual trust, and `GET /private` remains authorized if session-store policy allows.
2. **New login with OLD signer:** test sandbox IdP signing with OLD during overlap and verify.
3. **New login with NEW signer:** test sandbox signing with NEW and verify.
4. **In-flight AuthnRequest:** request ID created while OLD is active, Response signed with NEW after activation; the new verifier and request repository must still correlate.
5. **Logout:** RP/IdP-initiated `LogoutRequest`/`Response` signed properly, local session cleanup still works.
6. **Multi-node:** request issued by Pod A, callback hits Pod B; shared state/affinity and trust sets align.
7. **SameSite cookies:** cross-site browser SAML HTTP-POST may omit `SameSite=Lax` session cookies; test `SameSite=None; Secure` where required by profile alongside CSRF on other endpoints.
8. **Authorization:** a user with valid SAML Authentication lacking a role properly gets 403—do not try to "fix" it via certs.

### 11.1. In-Flight Example When IdP Signer Switches

~~~text
09:00:00 SP creates AuthnRequest ID _req-17
         Stores pending request in approved repository
09:00:02 IdP activates IDP-NEW signer
09:00:03 Browser posts signed SAMLResponse using IDP-NEW
         InResponseTo = _req-17

SP must:
  - trust IDP-NEW for expected IdP entityID
  - find pending _req-17 in same user/session context
  - check signature, issuer, audience, destination, recipient, time
  - enforce replay protection
  - authenticate if user account/policy is allowed
~~~

Getting 400 from missing `InResponseTo` or cookie is a **state/repository issue**, not automatically a bad NEW signer. Debug step-by-step with redacted logs; never disable `InResponseTo` as a "fix".

## 12. Multiple SPs, Multiple IdPs, Multiple Pods

In an organization with 20 SPs sharing one IdP, each SP updates trust on its own cadence. The IdP **must not switch to NEW** before mandatory SPs are ready, unless there is a verified fallback/partial-impact plan. Some IdPs support per-application signers while others use a tenant/global signer; never assume every provider shares the same capability.

For a multi-IdP Spring app:
- Each `registrationId` binds to its own IdP issuer/verification certs; IdP A's NEW cert must never verify IdP B.
- An identical `NameID` from A and B does not prove the same user; user mapping must bind issuer/tenant.
- Each IdP may rotate on a different date; never update a single global trust store without distinguishing entities.
- A shared SP signing key used across multiple IdPs requires **every relying party** to be ready to verify SP-NEW before a global switch—or split per-IdP signing credentials if the architecture supports it.
- All Pods must converge on the same effective verifier/decrypt keys across the lifecycle, even if the active signer rolls out canary OLD/NEW while the IdP trusts both.
- A Pod lacking the new key causes intermittent login failures behind the load balancer; report metrics per instance, not just an aggregate success rate.
- TLS ingress/metadata endpoints must preserve the canonical HTTPS scheme/host, never emitting `http://pod:8080` or accepting untrusted `X-Forwarded-Host`.

**Cluster request state:** SAML AuthnRequest/LogoutRequest repositories have TTLs; rolling deployments with in-memory sessions and no sticky routing can drop correlation even when certs are fine. Never fix by bypassing `InResponseTo`/replay.

## 13. Standalone Java 17: `SamlRolloverPlanner`

This program models **release gates**: the receiver must be ready for NEW before the producer switches; OLD retires only when zero in-flight messages remain. It **does not check XML Signatures, parse metadata, or process SAML tokens**, and must never be used as a production authenticator. Booleans represent verified QA evidence, not browser-supplied data.

**File `SamlRolloverPlanner.java`:**

~~~java
public class SamlRolloverPlanner {
    enum Direction {
        IDP_SIGNING, SP_SIGNING, SP_ENCRYPTION
    }

    record State(
        boolean oldAvailable,
        boolean newAvailable,
        boolean newAdvertised,
        boolean producerUsesNew,
        boolean oldInFlight,
        boolean probesPass) {}

    static String decide(Direction direction, State s) {
        if (direction == Direction.IDP_SIGNING) {
            if (s.producerUsesNew() && !s.newAvailable()) {
                return "BLOCK_IDP_NEW_UNTRUSTED";
            }
            if (!s.producerUsesNew() && !s.oldAvailable()) {
                return "BLOCK_IDP_OLD_UNTRUSTED";
            }
            if (s.oldInFlight() && !s.oldAvailable()) {
                return "BLOCK_OLD_MESSAGE_IN_FLIGHT";
            }
            if (!s.probesPass()) {
                return "HOLD_CANARY";
            }
            return s.producerUsesNew()
                ? (s.oldAvailable()
                    ? "IDP_NEW_ACCEPTED_KEEP_OLD"
                    : "IDP_NEW_ACCEPTED_CAN_RETIRE_OLD")
                : "IDP_OLD_ACCEPTED";
        }

        if (direction == Direction.SP_SIGNING) {
            if (s.producerUsesNew() && !s.newAdvertised()) {
                return "BLOCK_SP_NEW_UNADVERTISED";
            }
            if (s.producerUsesNew() && !s.newAvailable()) {
                return "BLOCK_SP_IDP_NOT_READY";
            }
            if (!s.producerUsesNew() && !s.oldAvailable()) {
                return "BLOCK_SP_IDP_OLD_UNTRUSTED";
            }
            if (!s.probesPass()) {
                return "HOLD_CANARY";
            }
            return s.producerUsesNew()
                ? "SP_NEW_SIGNING_ACCEPTED"
                : "SP_OLD_SIGNING_ACCEPTED";
        }

        // SP_ENCRYPTION: available means SP holds matching private key.
        if (s.oldInFlight() && !s.oldAvailable()) {
            return "BLOCK_INFLIGHT_OLD_DECRYPTION";
        }
        if (s.producerUsesNew() && !s.newAdvertised()) {
            return "BLOCK_NEW_ENCRYPTION_NOT_PUBLISHED";
        }
        if (s.producerUsesNew() && !s.newAvailable()) {
            return "BLOCK_NEW_DECRYPTION_KEY_UNAVAILABLE";
        }
        if (!s.producerUsesNew() && !s.oldAvailable()) {
            return "BLOCK_OLD_DECRYPTION_KEY_UNAVAILABLE";
        }
        if (!s.probesPass()) {
            return "HOLD_CANARY";
        }
        return s.producerUsesNew()
            ? "SP_NEW_ENCRYPTION_ACTIVE"
            : "SP_OLD_ENCRYPTION_ACTIVE";
    }

    static void show(String label, Direction d, State s) {
        System.out.println(label + "=" + decide(d, s));
    }

    public static void main(String[] args) {
        show("idpBaseline", Direction.IDP_SIGNING,
            new State(true, false, false, false, false, true));
        show("idpPretrust", Direction.IDP_SIGNING,
            new State(true, true, true, false, true, true));
        show("idpSwitchWithoutTrust", Direction.IDP_SIGNING,
            new State(true, false, true, true, true, true));
        show("idpSwitched", Direction.IDP_SIGNING,
            new State(true, true, true, true, true, true));
        show("idpRetireTooSoon", Direction.IDP_SIGNING,
            new State(false, true, true, true, true, true));
        show("idpComplete", Direction.IDP_SIGNING,
            new State(false, true, true, true, false, true));

        show("spNoAdvertise", Direction.SP_SIGNING,
            new State(true, true, false, true, true, true));
        show("spIdpNotReady", Direction.SP_SIGNING,
            new State(true, false, true, true, true, true));
        show("spSwitched", Direction.SP_SIGNING,
            new State(true, true, true, true, false, true));

        show("decryptMissingOld", Direction.SP_ENCRYPTION,
            new State(false, true, true, true, true, true));
        show("decryptNewOK", Direction.SP_ENCRYPTION,
            new State(true, true, true, true, true, true));
        show("probesFail", Direction.SP_SIGNING,
            new State(true, true, true, true, false, false));
    }
}
~~~

**Run:**

~~~bash
javac SamlRolloverPlanner.java
java SamlRolloverPlanner
~~~

**Expected stdout after successful compilation:**

~~~text
idpBaseline=IDP_OLD_ACCEPTED
idpPretrust=IDP_OLD_ACCEPTED
idpSwitchWithoutTrust=BLOCK_IDP_NEW_UNTRUSTED
idpSwitched=IDP_NEW_ACCEPTED_KEEP_OLD
idpRetireTooSoon=BLOCK_OLD_MESSAGE_IN_FLIGHT
idpComplete=IDP_NEW_ACCEPTED_CAN_RETIRE_OLD
spNoAdvertise=BLOCK_SP_NEW_UNADVERTISED
spIdpNotReady=BLOCK_SP_IDP_NOT_READY
spSwitched=SP_NEW_SIGNING_ACCEPTED
decryptMissingOld=BLOCK_INFLIGHT_OLD_DECRYPTION
decryptNewOK=SP_NEW_ENCRYPTION_ACTIVE
probesFail=HOLD_CANARY
~~~

**Demo limits:** `oldAvailable`/`newAvailable` have different meanings by Direction: for `IDP_SIGNING`, SP verification certs; for `SP_SIGNING`, IdP verification certs; for `SP_ENCRYPTION`, SP private decryption keys. `producerUsesNew` is the IdP signer, SP signer, or IdP encryption selector. `newAdvertised` must be confirmed from provider metadata/trust registry, and `probesPass` must come from real IdP/SP sandbox tests. The demo must never be used to conclude real login works merely because it prints a PASS line.

## 14. Integration Tests: Signatures, Issuer, and Encryption

A real suite needs a **sandbox IdP holding separate OLD/NEW private keys** and public certificates trusted by the SP. Each negative case varies one variable and **re-signs the message with a valid test signer** to test each validator independently. Editing XML after signing fails on signature verification first and proves nothing about `Audience`/`Recipient`/`InResponseTo` validation.

### 14.1. IdP Signer Tests

~~~text
IDP-OLD signs valid Response/Assertion  -> SP OLD+NEW trusts: ACCEPT
IDP-NEW signs valid Response/Assertion  -> SP OLD+NEW trusts: ACCEPT
UNKNOWN signs valid-looking Assertion   -> REJECT
IDP-NEW signs wrong Audience            -> REJECT
IDP-NEW signs wrong Destination         -> REJECT
IDP-NEW signs wrong Recipient           -> REJECT
IDP-NEW signs wrong InResponseTo        -> REJECT
IDP-NEW signs expired/replayed Response -> REJECT
~~~

**Never use `KeyInfo` self-trust.** If IdPs A and B share a subject, only the IdP signer for the matching registration/Issuer is permitted to verify.

### 14.2. SP Signer Tests

~~~text
SP-OLD signs AuthnRequest -> IdP trusts OLD: ACCEPT
SP-NEW signs AuthnRequest -> IdP trusts OLD+NEW: ACCEPT
SP-NEW signs AuthnRequest -> IdP trusts only OLD: REJECT
SP-NEW signs wrong Issuer -> IdP rejects
SP-NEW signs LogoutRequest -> IdP verifies
SP-NEW signs LogoutResponse -> IdP verifies
SP-UNKNOWN signer -> IdP rejects
~~~

### 14.3. Encryption Tests

~~~text
IdP encrypts for ENC-OLD -> SP decrypt OLD+NEW: PASS
IdP encrypts for ENC-NEW -> SP decrypt OLD+NEW: PASS
IdP encrypts for ENC-NEW -> SP only OLD: FAIL
IdP encrypts for ENC-OLD -> SP only NEW: FAIL
IdP encrypts for unknown public key -> SP rejects
~~~

After decryption, full Assertion signature/Issuer/Audience/Recipient/time validation must run; successful decryption alone does not mean authenticated.

## 15. Final Acceptance Test Matrix

| ID | Condition | Expected |
| --- | --- | --- |
| I01 | IdP active OLD, SP verifier OLD | New SSO works |
| I02 | IdP active OLD, SP verifier OLD+NEW | SSO works |
| I03 | IdP active NEW, SP verifier OLD+NEW | SSO works |
| I04 | IdP active NEW, SP verifier OLD only | Reject; rollout gate fails |
| I05 | IdP still signs OLD, SP retires OLD early | Reject; not allowed |
| I06 | IdP-NEW signer in metadata but Spring not reloaded | Detect drift before activation |
| I07 | Multi-region IdP signs OLD/NEW simultaneously | SP trusts both; track per region |
| I08 | Unknown signer or wrong tenant | Reject |
| I09 | IdP-NEW signed wrong Audience | Reject |
| I10 | IdP-NEW signed wrong Recipient/Destination | Reject |
| I11 | IdP-NEW signed wrong InResponseTo | Reject |
| I12 | IdP-NEW signed expired Assertion | Reject |
| I13 | Replayed signed SAMLResponse | Reject |
| I14 | IdP-NEW signed LogoutRequest | SP verifies |
| I15 | IdP-NEW signed LogoutResponse | SP verifies |
| P01 | SP-OLD signs, IdP trusts OLD | Pass |
| P02 | IdP trusts OLD+NEW, SP still signs OLD | Pass |
| P03 | SP switches NEW, IdP trusts OLD+NEW | Pass |
| P04 | SP switches NEW, IdP trusts OLD only | Fail; stop rollout |
| P05 | SP NEW cert not published to IdP | Block activation |
| P06 | SP private key mismatches public cert | Fail; no unsigned fallback |
| P07 | SP-NEW with wrong Issuer/Destination | Reject |
| P08 | SP-NEW signs LogoutRequest/Response | IdP verifies each |
| P09 | One SP Pod still signs OLD in overlap | IdP accepts during window |
| P10 | IdP removes OLD before SP full switch | Detect, stop/rollback |
| P11 | IdP supports single cert only | Coordinated cutover; no false zero downtime |
| E01 | IdP encrypts ENC-OLD; SP holds OLD+NEW | Decrypt |
| E02 | IdP encrypts ENC-NEW; SP holds OLD+NEW | Decrypt |
| E03 | IdP encrypts ENC-NEW; Pod B lacks NEW | Fail; rollout blocked |
| E04 | IdP encrypts ENC-OLD after SP removed OLD | Fail; retired too soon |
| E05 | Unknown public encryption key | Reject |
| E06 | Encrypted NameID/Attribute uses OLD | Dual decrypt during overlap |
| E07 | IdP picks NEW immediately after metadata publish | SP NEW decrypt preinstalled on all nodes |
| E08 | Signing and encryption share a keypair | Test both directions independently |
| S01 | Existing user session during trust deploy | Continues per session-store policy |
| S02 | New login IDP-NEW after active switch | Authentication+authorization as expected |
| S03 | AuthnRequest before switch, Response after | Correlation and NEW signature pass |
| S04 | Pod A issues request, Pod B receives callback | Shared state or safe failure |
| S05 | SAML POST callback cookie SameSite | Real browser session works |
| S06 | SP entityID, IdP entityID, ACS unchanged | Metadata diff stable except approved certs |
| S07 | Metadata signature trust/validUntil fail | Reject invalid update |
| S08 | Cert rotation alters NameID/role mapping | QA fail; fix mapping |
| S09 | User authenticated yet role denied | Proper 403, not crypto fault |
| S10 | Compromised OLD signing key | Remove trust per incident plan |
| S11 | SLO PartialLogout during rollout | Do not report global success |
| S12 | TLS cert rotated concurrently | Test TLS separately |
| S13 | Direct backend forged Host/X-Forwarded | No attacker callback/trust |
| S14 | SP verification certs mixed across tenants | Reject cross-tenant message |
| S15 | Debug logs contain raw assertions/private keys | Security QA fail |

**Minimum pass evidence:** case ID, registrationId/issuer alias, sender key fingerprint alias, receiver effective trust aliases, node ID, signed message type, SAML protocol verdict, session result, user authorization verdict, redacted correlation ID, deployment version, expected/actual, and reviewer. Never store raw SAML XML, real NameIDs, private keys, or bearer cookies.

## 16. Common Operational Errors

| Symptom | Possible Cause | Investigation |
| --- | --- | --- |
| 400/401 right after IdP switch | SP verifier does not trust IDP-NEW yet | Effective RPR/trust vs. metadata URL |
| Only one Pod fails | Static metadata/key secret not reloaded | Fingerprints/restarts per Pod |
| Metadata has NEW yet runtime still uses OLD | Repository built at startup | Refresh/restart with approved metadata |
| SP NEW AuthnRequest rejected by IdP | IdP does not trust SP-NEW yet | IdP effective trust / active signer |
| Login passes yet SLO fails | SLO signer/binding untested | Signed LogoutRequest/Response |
| EncryptedAssertion decrypt error | SP private ENC-NEW missing/mismatched | Mount/keypair/pod parity |
| Old encrypted Response fails after switch | Removed ENC-OLD too early | Restore approved OLD decrypt if safe |
| Signing key cert expired | Late renewal / cert policy | Expiry alerts / change window |
| SAML Audience changed unexpectedly | Entity ID drift in metadata | Compare SP/IdP registrations |
| Recipient mismatch | ACS/public HTTPS/proxy drift | Fix canonical URL; never bypass |
| InResponseTo mismatch | Lost request state / SameSite / shared session | Browser and session repository |
| 403 after successful SAML auth | User role/tenant mismatch | Authorization mapping |
| Unexpected cert in metadata | Compromised metadata provenance or unapproved change | IAM verification / security incident |
| Old KeyDescriptor still present months later | Incomplete retirement | Audit trust removal with approval |
| IdP metadata signature cert rotated too | Separate metadata trust-anchor switch | Never trust unverified XML |
| SP signer key changed with no evidence | YAML/secret alias differs from runtime | Actual signed AuthnRequest verification |
| Existing browser session works yet new login fails | Existing sessions do not re-verify Assertions | Test new SSO transactions |
| SAML signature algorithm mismatch | SP/IdP crypto policy drift | Algorithm capability tests |
| IdP supports only one signing cert | Lacks dual-trust feature | Coordinated change window |
| TLS cert swapped yet SAML fails | TLS certificate ≠ SAML signer | Diagnose separate trust layers |
| Compromised OLD key still trusted | Delayed incident response | Remove trust per security decision |

Never "quick-fix" by accepting any signer, pulling certs from untrusted `KeyInfo`, disabling Audience/Recipient/`InResponseTo`/replay/Signature validation, disabling TLS hostname verification, or applying `csrf.disable()` across the whole app.

## 17. Rollback and Emergency Rotation

### 17.1. IdP Signing Rollback

Rolling back to IDP-OLD is possible only when:
- The OLD key is not compromised and remains permitted;
- The IdP still holds the private OLD signer and the SP still trusts public OLD;
- Nodes/regions are synchronized and SSO/SLO tests pass;
- The rollback window and approvals remain valid.

If the SP already retired OLD from trust, rolling the IdP signer back to OLD **will fail** unless verified trust is restored first. If OLD leaked, never roll back even to prevent an outage: prioritize emergency recovery with a new key and reauthentication as needed.

### 17.2. SP Signing Rollback

The IdP must still trust SP-OLD. Rolling back a JAR or switching `sp-signing-active.key` back to OLD after the IdP removed the OLD public cert causes downtime. Rollback requires coordinating **application version, IdP trust, secrets, metadata, public TLS URLs, and the session repository**, not merely redeploying an old container image.

### 17.3. SP Encryption Rollback

Once the IdP encrypts for ENC-NEW, rolling back to an SP image holding only the ENC-OLD private key will fail. Keep both decryption keys during the overlap window if security policy permits; if the IdP must revert to encrypting with OLD, account for in-flight `SAMLResponse`s already encrypted with NEW. Never bake private keys into build artifacts to make rollback easier.

### 17.4. Compromise Is Always a Special Case

If a signing or decryption private key leaks, "keeping OLD so logins do not break" can be unsafe. Security incident response governs fast trust removal, credential rotation, auditing suspicious Assertions/SLO events, revoking sessions, and notifying stakeholders. An expired yet uncompromised certificate is a separate issue; never equate expiration with compromise.

## 18. Release Runbook by Responsible Team

**IAM/IdP team** prepares IDP-NEW, confirms active/secondary capability, metadata publication, trust signing policy, activation timestamp, and rollback options.

**SP/app team** inventories registrations and current verifiers/keys, deploys OLD+NEW trust/decryption, checks effective `RelyingPartyRegistration`, SSO/SLO validation, role mapping, and user sessions.

**Platform team** manages secret mounts, rolling reloads/restarts, cache TTL, shared session store, HTTPS ingress, per-node metrics, alerts, and rollback paths.

**Security team** verifies algorithms, fingerprints, public certificate provenance, expiry, least-privilege secrets, key-compromise procedures, and approves retirement.

### 18.1. Checkpoints

1. Change record exists with OLD/NEW fingerprints, owners, and exact IdP/SP entityIDs.
2. Baseline signed SSO/SLO pass, trust keys documented, private keys stored securely.
3. IdP NEW public cert approved and published; SP OLD+NEW verification staged.
4. SP NEW signing public cert approved by IdP before SP active key changes.
5. SP ENC-NEW private decrypt key deployed to every SP Pod before IdP encryption switch.
6. Browser HTTPS/public ACS and SLO endpoints unchanged; no internal URLs in metadata.
7. Metadata trust/refresh plan verified; all Pods hold effective new keys.
8. Signed-by-OLD/NEW sandbox positive tests and unknown-signer negative tests pass.
9. Canary runs under representative traffic with no new SAML signature/decryption/correlation failures.
10. Active switch signed-message evidence recorded, not just metadata status.
11. Old messages drained and rollback window closed; Security approves retirement.
12. Retired keys removed/revoked, metadata trust narrowed, alerts enabled, and logs sanitized.

### 18.2. Monitoring Without Leaking Sensitive Data

Log:
- environment, `registrationId`, IdP/SP alias, event type (SSO/LogoutRequest/LogoutResponse);
- SHA-256 public signer fingerprint **or approved alias**;
- signature verification outcome, decryption outcome, request ID fingerprint/correlation ID;
- wrong issuer/audience/recipient, replay/expiry category, HTTP status, and node ID;
- transaction latency, key expiry/metadata refresh errors, and user business authorization result.

Never log:
- private keys, `.p12`/`.key` files, raw `SAMLResponse`/`SAMLRequest`, plaintext XML assertions, real NameIDs;
- `JSESSIONID`, browser cookies, raw `RelayState` if carrying sensitive state, CSRF tokens;
- full HAR files, unredacted debug logs, or secret-manager credentials.

Test `KeyInfo`/signatures with the IdP sandbox/protocol validator; there is no need to collect raw browser Assertions in production logging systems.

## 19. Exercises and Self-Check Questions

**Exercise A – Three key directions.** Draw IdP→SP signatures, SP→IdP signatures, and IdP encrypt→SP decrypt. Mark which party must pretrust NEW in each case.

**Exercise B – IdP signer switched too early.** IdP already signs with NEW; SP Pods A/B trust OLD+NEW while C trusts only OLD. State the gate decision, how to measure impact per Pod, and the remediation plan without trust-all.

**Exercise C – SP signer prepublish.** IdP knows only SP-OLD; SP holds a NEW private signing key. Why can you not switch immediately? Lay out the publish/trust/activate/drain sequence and signed SLO tests.

**Exercise D – Encrypted response in flight.** IdP switches to encrypting with NEW at 10:00; a browser still holds an Assertion encrypted with OLD from 09:59. Which private keys should the SP retain, and what tests prove it?

**Exercise E – Java 17.** Run `SamlRolloverPlanner.java` and verify all 12 stdout lines. Add a case where the NEW encryption public key is advertised yet not all SP nodes hold the private key; explain the blocker.

**Exercise F – Spring YAML.** Read the `assertingparty.verification.credentials` OLD+NEW and active `signing.credentials` config. Distinguish verifier vs. signer, and explain why listing signing credentials does not itself determine which key is active.

**Exercise G – Metadata refresh.** The IdP metadata URL has the NEW signer, yet Spring's `InMemoryRelyingPartyRegistrationRepository` has not restarted. How do you check runtime trust and perform a safe rolling refresh?

**Exercise H – Negative signer.** Test IdP-NEW signing a wrong Audience. Should you re-sign the fixture or edit XML after signing? Why?

**Exercise I – Multi-tenant.** IdP A and IdP B both have user `alice`. How do you prove A's NEW cert cannot verify an assertion from B?

**Exercise J – Session continuity.** A user logged in with the OLD signer and the SP must restart a Pod. Explain what happens to in-memory sessions vs. shared sessions, `InResponseTo`, and browser callback cookies.

**Exercise K – SLO.** The SP signs LogoutResponse with NEW while the IdP does not trust SP-NEW yet. SSO succeeds because the IdP does not require signed AuthnRequests. Which test catches this bug?

**Exercise L – Compromised key.** The OLD signer leaks during overlap. List safe actions and explain why "keep OLD so logins don't break" is no longer valid.

**Exercise M – Cert fingerprints.** Run `openssl x509 -fingerprint -sha256 -dates` on public test certs; verify subject, NotAfter, and signer alias without printing private keys.

**Exercise N – Release gate.** Write a change report covering old/new fingerprints, metadata TTL, effective trust per node, key activation time, browser E2E, SLO, encrypted Assertions, rollback, and retirement approvals.

**Passing criteria:** Able to execute **IdP signing OLD→NEW with SP verification OLD+NEW staged beforehand**, **SP signing OLD→NEW with IdP verification ready**, and **SP encryption OLD→NEW after all SP decryptors hold NEW while retaining OLD for in-flight messages**; without breaking `entityID`/ACS/SLO, without bypassing signature/issuer/audience/correlation, and with clear tests and rollback.

## 20. Official References

- Spring Security 6.5 – SAML2 login overview, RelyingPartyRegistration and signing/decryption credentials: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – SAML2 Response authentication, signature and decryption: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Security 6.5 – SP metadata publication: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security 6.5 – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – RelyingPartyRegistration API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- Spring Boot 3.5 – Spring Security support: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML2 Metadata – KeyDescriptor, SPSSODescriptor, IDPSSODescriptor: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML2 Core – signatures, Issuer/Audience, encrypted Assertions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML2 Bindings – HTTP-POST/HTTP-Redirect: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- Microsoft Entra – Manage federation certificates and staged signing rollover: https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/tutorial-manage-certificates-for-federated-single-sign-on
- AWS IAM Identity Center – Rotate SAML certificates and provider limitations: https://docs.aws.amazon.com/singlesignon/latest/userguide/rotatesamlcert.html
- OWASP – Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
