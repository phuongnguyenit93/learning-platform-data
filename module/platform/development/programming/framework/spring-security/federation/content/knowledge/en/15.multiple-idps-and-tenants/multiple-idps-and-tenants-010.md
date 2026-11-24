# Managing Metadata Changes and Independent Key Rotation per Tenant in SAML 2.0

> **Topic:** Spring Security – Federation · **Section:** Multiple IdPs and Tenants. This lesson focuses on operating **multiple SAML Identity Providers (IdPs)** inside one Spring Security Service Provider (SP): fetching and verifying metadata, detecting changes, protecting each tenant's trust boundary, rotating IdP and SP certificates/keys on **independent** schedules, safely publishing/updating metadata, atomic multi-node rollouts, rollbacks, monitoring, and negative testing. Examples mainly target Spring Boot 3.x / Spring Security 6.x Servlet; version-dependent APIs are explicitly noted. Pure Java examples run on JDK 17+.

## 1. Real-World Problem: Each Tenant Has Its Own IdP and Key Schedule

A B2B SaaS application acts as a SAML **Service Provider** for multiple enterprise customers. Each customer is a **tenant** and may use its own IdP:

| Internal Tenant | Registration ID | IdP `entityID` | IdP SSO Endpoint | IdP Key Trusted by SP |
| --- | --- | --- | --- | --- |
| Company A | `tenant-a` | `https://idp-a.example.org/entity` | `https://idp-a.example.org/sso` | `A-old` |
| Company B | `tenant-b` | `https://login-b.example.net/issuer` | `https://login-b.example.net/saml/sso` | `B-2026` |
| Company C | `tenant-c` | `https://sso-c.example.com/idp` | `https://sso-c.example.com/saml` | `C-current` |

This is **simulated data**; names like `A-old`/`B-2026` are lesson key labels only, **not real public-key fingerprints or private keys**.

On Monday, tenant A prepares to rotate its IdP signing certificate. Tenant B stays unchanged; tenant C changes its `SingleSignOnService` URL after maintenance. If the app uses **one shared key pool**, a global metadata cache without tenant isolation, or blindly accepts "latest metadata" from outside, A's change can break or weaken logins for B and C.

**Design goal:** a metadata update for tenant A changes **only registration A** after verification and propagates cleanly to instances serving A; B/C keep their existing issuers, endpoints, keys, policies, and sessions untouched. Every `SAMLResponse` must be verified using **only the chosen registration's IdP key**.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `registrationId`, `tenantId`, SP `entityID`, and IdP `entityID` to avoid cross-tenant trust confusion.
2. Read `EntityDescriptor`, `IDPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `validUntil`, and `cacheDuration`.
3. Design a **fetch → authenticate metadata → validate policy → stage → approve → publish atomically → monitor → retire** pipeline per tenant.
4. Perform **IdP signing-key rollover** using an old+new overlap window without widening trust to other tenants.
5. Distinguish IdP verification keys, SP private signing keys, SP private decryption keys, and the **metadata signing trust anchor**.
6. Use `RelyingPartyRegistrationRepository` and Spring Security SAML2 configurations with version caveats.
7. Control endpoint, issuer, algorithm, certificate, and multi-node SP changes without failing open.
8. Test zero-downtime rotation, rollback, compromised keys, in-flight AuthnRequests, and tenant isolation.

## 2. Identifiers That Must Be Strictly Separated

| Component | Who Sets/Manages It? | Meaning | Automatically Equal to Tenant? |
| --- | --- | --- | --- |
| `tenantId` | SaaS application | Data/permission boundary and customer contract | Internal ID |
| `registrationId` | SP/Spring Security | Key to look up `RelyingPartyRegistration` | May map 1-to-1, **not required** |
| SP `entityId` | SP | SP identifier appearing as AuthnRequest `Issuer` and SAML audience | May be shared or per-tenant; must align with metadata |
| IdP `entityId` | IdP | `Issuer` of Response/Assertion to verify | Never take from raw XML as source of truth |
| `NameID` | IdP | Subject identifier per contract | Not guaranteed unique across all IdPs/tenants |
| Certificate fingerprint/key ID | SP inventory | Represents an approved public key/cert | Does not replace registration/issuer mapping |

For example, a user has `alice@example.com` in tenant A and a different account with the same email in B. If the app maps identities by email alone, a valid assertion for tenant B could accidentally grant access to A's data. Identity mapping should be namespaced such as **`(tenantId, IdP issuer/registration, NameID or stable subject key)`**; grant access only after trust, claims, and tenant relationship are verified.

**Never** pick the final tenant solely because the browser sends `?tenant=tenant-a` or self-asserted XML `Issuer`. Request routing may use a registration ID from the URL to locate an **allowlisted** configuration; callbacks must bind to registration/trust, request state, and issuer. When one IdP serves multiple tenants, the same `entityID` may appear across multiple registrations, making issuer-only lookup **ambiguous**. Build an explicit resolution mechanism—never "pick the first record."

## 3. What Does SAML2 Metadata Contain?

SAML 2.0 metadata is an XML document describing **entities, endpoints, bindings, keys/certificates, and policy requirements**. For an IdP, it may include:

- `md:EntityDescriptor entityID=...`: IdP/partner identifier.
- `md:IDPSSODescriptor`: IdP role for SAML SSO.
- `md:KeyDescriptor use="signing"`: public key/certificate for SPs to verify IdP signatures.
- `md:KeyDescriptor use="encryption"`: public key for encryption per role/profile; does not by default replace signing trust.
- `md:SingleSignOnService Binding=... Location=...`: where the IdP receives `AuthnRequest`.
- `md:SingleLogoutService`: endpoint for `LogoutRequest`/`LogoutResponse` if supported.
- `WantAuthnRequestsSigned`: IdP requirement for signed AuthnRequests from the SP.
- `validUntil` and `cacheDuration`: metadata validity and caching hints, **not** certificate expiration dates or SAML assertion TTLs.

### 3.1. Reading the XML Structure

The snippet below illustrates **two signing keys during a rollover window**; it is not production-ready metadata because the certificate strings are dummy placeholders.

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp-a.example.org/entity"
    validUntil="2026-12-31T00:00:00Z"
    cacheDuration="PT6H">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_OLD_TEST_CERT</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_NEW_TEST_CERT</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp-a.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Two `KeyDescriptor use="signing"` elements represent **multiple public signing keys accepted by the SP** while the IdP rotates keys, provided the updated metadata itself has been verified as trustworthy. In real metadata, `ds:X509Certificate` holds a Base64-encoded DER certificate; never copy placeholder strings.

**Key security point:** having two keys in metadata does not mean trusting arbitrary keys sent by the browser. The SP uses only keys present in a registration accepted by admins or the metadata trust chain, and strictly for that IdP.

### 3.2. `KeyDescriptor` Is Not Metadata Signature

A `ds:Signature` signing **the metadata document itself** (when metadata is signed) is separate from `KeyDescriptor use="signing"`, which lists **keys used to sign SAML Response/Assertion messages**. A certificate appearing inside metadata **does not self-authenticate that metadata document**.

When verifying signed metadata, you must have a **bootstrapped metadata verification trust anchor** (such as a federation operator/IdP cert pinned out-of-band). Never implement logic like:

```text
Fetch new metadata → extract new certificate from KeyDescriptor
→ immediately use that certificate to verify the downloaded metadata's signature
→ accept all changes.
```

That is **uncontrolled trust-on-first-use**; an attacker who swaps metadata can embed their own key and self-sign a forged document. Rotating the metadata-signing trust anchor requires an out-of-band distribution/approval workflow or an already-approved trust chain.

### 3.3. `validUntil` and `cacheDuration` Are Not the Same

| Field | Meaning | Action Required |
| --- | --- | --- |
| `validUntil` | Upper bound for which the metadata producer asserts the metadata remains valid | Never keep trusting past expiration outside an approved policy |
| `cacheDuration` | Suggested caching interval when no other changes/limits apply | Schedule refreshes, still capped by `validUntil` |
| Certificate `NotAfter` | X.509 certificate expiration date | Track separately; certificate expiration in SAML has nuances |
| Pending `AuthnRequest` TTL | Duration a login transaction waits for callback | Never conflate with metadata cache |
| SP authenticated session TTL | User session duration | Never conflate with metadata or key rollover |

**Nuance:** in SAML metadata, an X.509 certificate can serve simply as a **public-key container**, not necessarily as a PKIX client/server certificate. The SAML Metadata Interoperability Profile details how metadata keys may be used even when a certificate has attributes a TLS PKIX verifier would treat differently. Enterprise policy may still require checking `NotBefore`/`NotAfter` and key usage, but never treat "PKIX certificate expiry = SAML metadata validity" as a protocol identity. More importantly: **trust comes from authenticated metadata and registration policy**, not merely an unexpired certificate.

## 4. Multi-Tenant Trust Boundary in Spring Security

### 4.1. Each Tenant Has a Trusted Registration

`RelyingPartyRegistration` is Spring Security's model holding SP/IdP entityIDs, endpoints, bindings, and credentials. `RelyingPartyRegistrationRepository` looks up configurations by `registrationId`. With multiple IdPs, the app provides multiple registrations:

```text
RelyingPartyRegistrationRepository
  |
  +-- tenant-a
  |     SP entityID / ACS / signing / decryption config A
  |     IdP entityID A
  |     IdP verification certificates A-old, A-new
  |     IdP SSO/SLO endpoints A
  |
  +-- tenant-b
  |     SP entityID / ACS / signing / decryption config B
  |     IdP entityID B
  |     IdP verification certificate B-current
  |     IdP endpoints B
  |
  +-- tenant-c
        ... isolated C
```

A change event for A must update **only A's config**. Never build a `List<X509Certificate> allTenantsCertificates` to verify responses for any issuer. If IdP B sends a `SAMLResponse` signed with A's certificate, even if mathematically valid, the result must **reject cross-tenant trust mismatch**.

### 4.2. Lookup/Routing Points That Can Cause Confusion

- `GET /saml2/authenticate/tenant-a` initiates login under registration A.
- `POST /login/saml2/sso/tenant-a` is the typical callback. The response filter/converter resolves the registration and validates the actual message.
- If the callback lacks `registrationId`, some resolver paths fall back to issuer or pending request. **When IdP `entityID` is not unique, issuer-only lookup is insufficient.** Maintain state/tenant binding and use a resolver with strict policy.
- A browser route `tenant-a` has no right to trigger fetching metadata from an arbitrary URL. Every metadata source must be a pre-configured, admin-approved ID.
- Post-SAML-authentication tenant/role mapping must never rely solely on `NameID`/email or user-supplied query parameters.

Spring Security documents `RelyingPartyRegistrationResolver` and `RelyingPartyRegistrationRepository` to govern resolution. If your app uses a shared callback or multiple IdPs sharing an issuer, test **registration mismatch** and **ambiguous issuer** rather than relying on default inference.

### 4.3. Difference Between Authentication and Authorization

A valid assertion from IdP A only proves **IdP A** authenticated the subject for that SP entityID. It never grants permission to read tenant B's data. Post-login, bind the principal to a **verified tenant context** and enforce authorization per resource/object.

If a user holds accounts in multiple tenants, UI tenant switching requires its own policy; never let a request swap `tenantId` in a cookie/query to reuse an `Authentication` from another issuer.

## 5. Four Key Types That Must Rotate Independently

| Key / Certificate | Who Holds the Private Key? | Who Uses the Public Key? | Purpose | When Rotating |
| --- | --- | --- | --- | --- |
| **IdP SAML signing key** | Tenant A's IdP | SP verifies Response/Assertion from IdP A | Inbound login trust | IdP A publishes new cert → SP A trusts old+new → IdP A switches signer → retire old |
| **SP AuthnRequest signing key** | SP, optionally per tenant A | IdP A verifies signed AuthnRequest | Outbound login request trust | SP publishes new public cert to IdP A → IdP A trusts → SP switches private signer → retire old |
| **SP decryption key** | SP, optionally per tenant A | IdP A encrypts assertions to SP cert A | Payload confidentiality | Publish new decryption cert → IdP A switches encryption → SP keeps old private decrypt key for in-flight messages → retire |
| **Metadata signing key / trust anchor** | IdP or federation metadata signer | SP verifies signed metadata | Trust **the config source itself** | Distribute/approve new anchor first; never self-trust a newly downloaded key |

Sometimes an SP keypair is reused for both signing and decryption by configuration, yet **the business purpose, risk, and rollover ordering of the two roles differ**. When strict tenant isolation is required, per-tenant keypairs and secret ACLs are worth adopting.

**Do not confuse:** the cert IdP A uses to sign `SAMLResponse` is **not** an SP private key; the metadata signer cert may differ from the SAML Response signer cert; and IdP A's signing cert must never enter tenant B's verification pool.

## 6. Per-Tenant Metadata Change Lifecycle

An operations pipeline should separate **candidate** from **active**:

```text
Change request for TENANT A
        |
        v
Resolve approved tenant + metadata source
        |
        v
FETCH with timeout, HTTPS, and XML size/SSRF limits
        |
        v
VERIFY provenance (signed metadata or admin channel)
        |
        v
VALIDATE: entityID, role, endpoints, keys, algorithms,
          validUntil/cacheDuration, policy & tenant boundaries
        |
        v
DIFF vs active A; classify routine vs high-risk changes
        |
        v
STAGE candidate A vNext (active unchanged)
        |
        v
TEST on isolated environment with signed SAML fixtures
        |
        v
APPROVAL (dual control for trust/issuer/key changes)
        |
        v
PUBLISH atomically A vNext with expected version
        |
        v
PROPAGATE / observe all nodes, measure login failures
        |
        v
RETIRE old key/metadata after defined grace, or ROLLBACK
```

Never "fetch new metadata and replace the whole repository" without inspecting diffs. **An invalid candidate must be rejected without touching the active config.** Keep audit records explaining who approved, version/digest, timestamps, and tenant, without logging secrets.

### 6.1. Fetching Metadata Safely

- Source URL/file belongs to a **per-tenant allowlist**, e.g., from an admin-verified tenant onboarding workflow.
- Require valid HTTPS/TLS when fetching online, verify TLS hostnames/certs, enforce strict redirect policies, and **never** accept `?metadataUrl=...` from end users.
- Defend against SSRF: block arbitrary hosts, private networks, link-local, and localhost; validate DNS resolution, redirects, and endpoints; cap redirects, byte size, timeout, and concurrency.
- Harden XML parsing: forbid external entities/DTDs/XXE, entity expansion, and remote schema/reference fetching; cap depth/size; use a maintained parser.
- If metadata is signed, verify the signature against an appropriate **bootstrap trust anchor**; never use a new key inside the document to prove that document is trustworthy.
- If metadata is **unsigned**, HTTPS alone only secures transport to an already-trusted endpoint; governance must still confirm source authority, approve sensitive changes, and bound scope.
- An `EntitiesDescriptor` can contain multiple IdPs; extract only the entity with the tenant's configured `entityID`, never picking "the first entity" or a similar-looking issuer.
- Post-parse, check `validUntil`/`cacheDuration` and alignment with cache policy; never substitute session lifetimes for metadata freshness.

### 6.2. Classify Changes Instead of Auto-Accepting Every Diff

| Diff | Recommended Handling Level | Reason |
| --- | --- | --- |
| Add `KeyDescriptor use=signing` for exact IdP `entityID` with valid provenance | **Controlled key rollover** | Likely pre-publishing a new key |
| Remove old signing key after grace window expires | Planned retirement | May break in-flight callbacks if removed prematurely |
| Change SSO endpoint with same IdP issuer | Coordinated change + integration test | New redirect target; trust/endpoint allowlists must align |
| Change SLO endpoint/binding | Coordinated SLO test | May affect dedicated logout flows |
| Change `WantAuthnRequestsSigned` / algorithm suite | Configuration/security review | SP signing credentials and IdP expectations must align |
| Change IdP `entityID` | **High-risk identity change** | Not a routine key update; impacts trust and account namespaces |
| Certificate from another tenant appears | **Reject / investigate** | Trust isolation violation |
| Invalid metadata signature or wrong source URL | **Reject** | No trusted provenance |
| `validUntil` expired or metadata invalid | Reject candidate; operational remediation | Never let stale data self-extend trust |
| Signs of key compromise | Emergency revoke | Never retain old+new grace like routine rollover |
| Only contact/organization fields changed | Low-risk per governance | Does not alter authentication trust; still verify metadata |

**Never use another file's hash to assume "new metadata is safe."** Hashes/file digests track changes and versioning, not source trustworthiness. Metadata signatures or verified administrative channels establish authenticity.

### 6.3. Validated Immutable Snapshots

Each active registration should tie to an immutable version/snapshot:

```text
tenant-a / registrationId=tenant-a
  revision: 42
  metadata-source: approved IdP A endpoint
  fetched-at: 2026-11-07T04:00:00Z
  valid-until: 2026-12-31T00:00:00Z
  metadata-digest: SHA-256 of authenticated document
  entityID: https://idp-a.example.org/entity
  trust-verification-keys: [A-old, A-new]
  SP-signing-key-version: A-SP-2026
  SSO-endpoint: https://idp-a.example.org/sso
  status: ACTIVE
```

The block above is an **illustrative schema**; `metadata-digest` is not a substitute for signatures. Never log raw certificates/private keys, full `SAMLResponse` XML, or secret `RelayState`. Audits may retain **public** certificate fingerprints and encrypted storage references per policy.

When publishing A revision 43, update A's record atomically; B and C keep their own existing revisions. Enforce **optimistic locking / expected revision** so two admins or refresh jobs cannot overwrite each other. Across multiple pods, distribute revisions consistently or use a shared store with proper transactions.

## 7. Zero-Downtime IdP Signing-Key Rollover

### 7.1. Old + New Workflow for Tenant A

Assume initially the SP trusts only `A-old`:

| Stage | IdP A Actually Signs Responses With | SP A Accepts Keys | Action |
| --- | --- | --- | --- |
| T0 | `A-old` | `A-old` | Baseline, normal logins |
| T1: pre-publish | `A-old` | **`A-old` and `A-new`** | Authenticated IdP metadata contains new cert; SP stages/approves/deploys |
| T2: switch signer | **`A-new`** | `A-old` and `A-new` | IdP switches private signing key after confirming SP trusts new key |
| T3: stabilize | `A-new` | `A-old` and `A-new` | Monitor signing failures; wait for in-flight callbacks and replication |
| T4: retire | `A-new` | **`A-new` only** | Remove `A-old` after grace window/policy |
| B at all times | `B-current` | **`B-current` only** | Unaffected by A's rotation |

Precondition for T2 safety: **every active SP instance serving tenant A already trusts `A-new`**, including pods in other regions—not just one node's dashboard reporting an update. If the IdP switches too early, callbacks signed with `A-new` landing on pods still trusting only `A-old` will fail.

### 7.2. Why Is Overlap Needed?

IdP A may issue a `SAMLResponse` for an in-flight AuthnRequest right as SP rollout starts. If the SP retires `A-old` the instant it sees `A-new`, responses already signed with `A-old` still en route to the ACS will be rejected. Overlap permits both keys **belonging to that same IdP A** within a bounded window.

**Never extend overlap indefinitely.** Size the grace window around SAML response lifetimes, pending request TTLs, rollout completion, IdP timing, and audits; retire old keys once migration completion is evidenced.

**Critical exception:** if `A-old` is compromised, **never keep trusting `A-old` just for zero downtime**. Revoke/remove the exposed key per incident response, accepting forced re-logins or brief disruption rather than continuing to accept forged assertions.

### 7.3. One Signing Cert May Be Referenced in Multiple Places

Inspect `KeyDescriptor use="signing"` against the IdP role and metadata trust. Update only **IdP verification credentials** inside `RelyingPartyRegistration` A; never accidentally alter:

- SP private signing key used for AuthnRequests.
- SP private decryption key used for `EncryptedAssertion`.
- Tenant B/C signing keys.
- Metadata signing trust anchor.

A certificate might share a subject/issuer Common Name with another key yet still requires verifying the **exact key/certificate identity**; never trust based solely on a matching Common Name.

## 8. Per-Tenant SP Signing-Key Rotation

When the SP signs `AuthnRequest`s for IdP A:

```text
SP A private signing key (old/new)
      |
      +--> signs AuthnRequest
                    |
IdP A trusts SP public signing certificate(s) from metadata/contract
```

The sequence differs from inbound IdP key rotation:

1. SP generates a new keypair `A-SP-new` in HSM/secret manager; public cert is prepared.
2. SP publishes the **new SP signing certificate** in A's SP metadata or delivers it via an IdP-A-approved channel, keeping the old public cert during transition if the IdP supports multiple certs.
3. Wait until IdP A confirms the new certificate is trusted across **all nodes** receiving AuthnRequests.
4. SP begins signing **new requests** with the new private key; monitor for IdP "invalid AuthnRequest signature" rejections.
5. Once older requests no longer need verification and IdP A finishes switching, retire the old trust/private key per policy.
6. B/C see zero key or metadata changes when tenant independence is required.

**Never reverse the order:** if the SP signs with the new key before the IdP trusts the new public certificate, tenant A logins will be rejected.

In architectures where one SP shares an `entityID`/keypair across multiple tenants, **fully independent** rotation is not immediately supported by the design. Split the SP `entityID`/registration/cert per tenant and re-register with the IdP; never claim tenant isolation while sharing a private key whose blast radius covers every tenant.

## 9. SP Decryption-Key Rotation Also Differs from Signing Rotation

When IdP A issues `EncryptedAssertion`s encrypted to the SP's public encryption certificate:

1. SP A generates a new encryption keypair first, retaining the **old private decryption key** to decrypt in-flight assertions.
2. SP A publishes the new **public encryption cert** to IdP A (via metadata/contract).
3. IdP A begins encrypting with the new cert **only after** SP A can decrypt with the new private key.
4. During overlap, the SP keeps both old and new private decryption credentials per policy because ciphertexts under the old key may still arrive.
5. Once no in-flight ciphertexts remain and the IdP confirms migration, remove the old private key.
6. Isolate read access to old/new decryption secrets per tenant and retain rotation audits.

**Do not confuse:** the SP private decryption key is not the IdP public signing cert. An IdP signing rollover does not require rotating the SP private decryption key unless mandated by a separate policy or contract.

## 10. Metadata-Signing Trust Anchor Rotation: The Trust-Bootstrap Problem

This is the most commonly overlooked part of automated metadata refresh systems.

### 10.1. Trusted Metadata Differs from Trusted `SAMLResponse`

An organization may publish metadata signed by a **metadata signer**. The SP needs an initial anchor delivered through an admin channel to verify that metadata's signature. Only after metadata is authenticated may the SP accept `KeyDescriptor` entries containing the IdP's SAMLResponse signing keys.

**Rotating the metadata anchor** must never work like: "the fetched metadata has a new cert, so use that cert to trust the metadata." Doing so lets an attacker craft fake metadata and sign it themselves.

### 10.2. Anchor Rollover Workflow

1. Admin or federation authority publishes the metadata signer's new cert via an **authenticated channel** (signed notice / secure admin workflow).
2. SP adds the new metadata verification cert to the trust list for **specifically tenant A's metadata source** with approval and versioning.
3. During overlap, signed metadata may be signed by either the old or new signer per policy.
4. Metadata producer switches to signing with the new private key; SP verifies cleanly.
5. After cutoff, remove the old metadata trust anchor from source A.
6. If the old signer is compromised, revoke immediately and audit historical metadata and all affected registrations.

One IdP vendor may share a metadata signer across many customers; in that case, rotating the metadata trust anchor has a broader blast radius than a single tenant and must be governed at the **true signer scope**, rather than pretending each tenant has independent keys when sharing one federation signature key.

### 10.3. Spring Security / OpenSAML Version Notes

Newer Spring Security documentation covers `OpenSaml5AssertingPartyMetadataRepository` with `verificationCredentials(...)` to validate **metadata signatures**. Official docs explicitly warn: if no metadata verification credentials are provided, this component **performs no metadata signature validation**. Understand that behavior clearly; never treat an HTTPS endpoint as automatically equivalent to signed metadata.

This API belongs to OpenSAML 5 releases; Spring Security 6.3/6.4 and OpenSAML 4 releases may use different metadata builder paths. Check the **exact Javadoc/release you are running**. Never copy OpenSAML 5 classes into a 6.3 project and weaken security just to make it compile.

Even with auto-refresh enabled, **automatic metadata retrieval does not guarantee authentication or provenance**, nor does it replace approval workflows or entityID/tenant trust checks.

## 11. Spring Security: Basic Multi-Registration Configuration

### 11.1. YAML for Two Tenants

A Spring Boot 3.x app can declare two separate registrations, each pointing to an admin-vetted local IdP metadata file:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          tenant-a:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/tenant-a-sp-signing.key"
                  certificate-location: "file:/run/config/tenant-a-sp-signing.crt"
            assertingparty:
              metadata-uri: "classpath:saml/tenant-a-idp.xml"
          tenant-b:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/tenant-b-sp-signing.key"
                  certificate-location: "file:/run/config/tenant-b-sp-signing.crt"
            assertingparty:
              metadata-uri: "classpath:saml/tenant-b-idp.xml"
```

**Preconditions:** `tenant-a-idp.xml` and `tenant-b-idp.xml` are vetted and governed from trusted sources; public SP `entityID`/ACS match the IdPs; and valid signing credentials and IdP trust exist. This is a **static configuration example**; it does not live-reload modified metadata files while running.

Using `classpath:...` avoids fetching arbitrary web URLs at startup, yet **does not itself prove metadata is signed or admin-approved**. Build/deploy pipelines must distribute verified, tenant-separated files. Paths under `/run/secrets` are placeholders requiring a real secret manager and ACLs.

### 11.2. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiTenantSamlSecurity {

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

This is a **Spring configuration class** and cannot run standalone with `java MultiTenantSamlSecurity`. With a `RelyingPartyRegistrationRepository` holding A and B, the browser can visit:

```text
GET /saml2/authenticate/tenant-a
GET /saml2/authenticate/tenant-b
```

Each URL must construct the AuthnRequest using **that exact registration's** IdP/SP metadata. Callback `POST /login/saml2/sso/{registrationId}` must verify issuer/signature/audience/state against the matching registration's trust. Never build a one-size-fits-all verifier using a union of all tenants' public keys.

### 11.3. Building a Repository from Vetted Metadata

When code is preferred over YAML, Spring Security 6.x provides `RelyingPartyRegistrations.fromMetadataLocation(...)`. Example **Spring config class** loading classpath XML metadata:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

@Configuration
public class TenantRegistrationConfiguration {

    @Bean
    RelyingPartyRegistrationRepository samlRegistrations() {
        RelyingPartyRegistration tenantA = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/tenant-a-idp.xml")
            .registrationId("tenant-a")
            .build();
        RelyingPartyRegistration tenantB = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/tenant-b-idp.xml")
            .registrationId("tenant-b")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(
            tenantA, tenantB);
    }
}
```

**Important limitations:**

- Metadata files must be **authenticated and validated beforehand** prior to packaging in the classpath. `fromMetadataLocation` is a registration builder, not a full approval/metadata-signature trust mechanism.
- The illustrative builder reads only IdP metadata settings. If an IdP requires signed AuthnRequests, add **SP private signing credentials** per registration; if encrypted assertions are required, add SP decryption credentials.
- Avoid declaring this bean **alongside** auto-configured Boot registration YAML without understanding bean override behavior. Pick **one primary registration source**.
- `InMemoryRelyingPartyRegistrationRepository` is built at bean-creation time and **has no live rotation pipeline** if classpath files change. Dynamic updates require reload/rebuild/repository/caching architecture with version coordination.
- When one IdP issuer is shared across multiple registrations, configure callback resolvers/state so tenants are never confused.

### 11.4. `CachingRelyingPartyRegistrationRepository` and Auto Refresh

Per Spring Security API docs, `CachingRelyingPartyRegistrationRepository` was introduced in **6.4**. It wraps and **lazily loads and caches** an `IterableRelyingPartyRegistrationRepository` from a loader, supporting `setCache(...)` with Spring Cache. The default cache is a non-expiring **`ConcurrentMapCache`**. Consequently:

- `setCache` backed by Redis/Cache with appropriate TTL/invalidation can assist with refresh and state sharing.
- **Cache TTL does not verify metadata signatures**, entityIDs, or tenant policies.
- A shared cache is insufficient if pods build different registrations or revisions are not distributed consistently.
- When updating **only tenant A**, choose a per-tenant config/revision design and invalidate/publish only that tenant or snapshot; never abruptly refresh the entire repository with unvetted metadata.
- Do not reference this class in Spring Security 6.3 if absent; never assume Spring Security 7.x APIs are identical to 6.x.
- When a loader fetches metadata online, never run arbitrary network waits/SSRF risks on the live request path; validate metadata in staging/control plane and publish to runtime.

Newer Spring Security releases add OpenSAML 5 metadata repositories with refresh/validation capabilities. **Pick the exact API for your release and test it**, rather than attributing refresh/signature/atomic-update guarantees to a class that lacks that contract.

## 12. Control Plane and Data Plane Structure

### 12.1. Separating Metadata Governance from Login Traffic

Split the architecture into two planes:

```text
CONTROL PLANE
  Approved tenant IdP metadata sources
        |
  Fetch + authenticate + validate + diff + approval
        |
  Versioned tenant configs (A:v43, B:v8, C:v15)
        |
  Publish/canary/rollback + audit
        |
        v
DATA PLANE (Spring Security SP instances)
  POD 1 -- local validated snapshots/cache
  POD 2 -- local validated snapshots/cache
  POD 3 -- local validated snapshots/cache
        |
  AuthnRequest generation + SAMLResponse verification
```

Login requests **must not depend directly** on a live HTTP fetch to the IdP's metadata URL on every login. An IdP metadata outage or timeout must never block SP requests indefinitely or trigger reckless trust fallbacks.

The control plane fetches, approves, and versions; the data plane consumes **active validated snapshots only**. Even with automated refresh, candidates must pass all validation gates before becoming active.

### 12.2. Versioned Updates and Optimistic Concurrency

Suppose:

```text
Active:
  tenant-a: revision 42, trust=[A-old]
  tenant-b: revision 8,  trust=[B-current]

Admin X prepares tenant-a revision 43: trust=[A-old,A-new].
Job Y also starts from revision 42.

Publish X succeeds only if expectedRevision=42.
After X publishes, tenant-a revision=43.
Publish Y with expectedRevision=42 must conflict and fail.
Tenant-b remains at revision=8.
```

Never mutate a multi-threaded global `HashMap` via `clear()/putAll()`: concurrent logins during an update could see missing credentials or a mix of old issuer + new SSO URL. Use **immutable snapshots + atomic swaps** per tenant, or a config store with transactions and version gating.

### 12.3. Multi-Pod Rollout

A successful control-plane commit does not mean every pod already holds the new key. Before IdP signer cutover, track:

- Desired revision per tenant.
- Applied revision/health per pod/region.
- Smoke tests using a signed fixture for the new key in every deployment cluster.
- Cache invalidation/refresh intervals and metadata expiration (`validUntil`).
- Drift alerts if any pod remains on an older revision.
- In-flight request constraints: a `SAMLResponse` for a request created on pod A may land on pod B after an update, requiring compatible repository state and trust overlap.
- Rollback to **last-known-good trusted revision** only if it does not re-enable a revoked/compromised key.

If eventual-consistency caches introduce a version-skew window, **never** convert signature validation failures into successes. Pause cutover until rollout is safely complete.

## 13. Java 17: Multi-Tenant Registry with Revisions and Independent Key Rotation

The following example runs on **pure Java 17**. It models **trusted signing-key identifiers** using strings `A-old`, `A-new`, and `B-current`, and uses immutable `Map`s with `AtomicReference` for atomic per-tenant publication. Updates succeed **only when the expected revision matches**; other tenants remain untouched.

**Crucial note:** this program **does not** fetch/parse metadata XML, decode certificates, or verify cryptographic/SAML signatures. `accepts` only simulates **matching issuer and key labels in an already-trusted registry**. Production must verify signatures via Spring Security/OpenSAML using real public certificates and full protocol checks.

Save as `TenantMetadataRotationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public class TenantMetadataRotationDemo {

    record TenantTrust(
            String registrationId,
            String idpIssuer,
            long revision,
            Set<String> acceptedSigningKeys) {

        TenantTrust {
            acceptedSigningKeys = Set.copyOf(acceptedSigningKeys);
        }
    }

    static final class Registry {
        private final AtomicReference<Map<String, TenantTrust>> active;

        Registry(Map<String, TenantTrust> initial) {
            this.active = new AtomicReference<>(Map.copyOf(initial));
        }

        boolean accepts(String registrationId,
                        String issuer, String signingKeyLabel) {
            TenantTrust t = active.get().get(registrationId);
            return t != null
                    && t.idpIssuer().equals(issuer)
                    && t.acceptedSigningKeys().contains(signingKeyLabel);
        }

        boolean rotate(String registrationId,
                       long expectedRevision,
                       Set<String> nextTrustedKeys) {
            if (nextTrustedKeys == null || nextTrustedKeys.isEmpty()) {
                return false;
            }

            while (true) {
                Map<String, TenantTrust> oldSnapshot = active.get();
                TenantTrust existing = oldSnapshot.get(registrationId);

                if (existing == null
                        || existing.revision() != expectedRevision) {
                    return false;
                }

                TenantTrust updated = new TenantTrust(
                    existing.registrationId(),
                    existing.idpIssuer(),
                    existing.revision() + 1,
                    nextTrustedKeys);

                Map<String, TenantTrust> copy =
                        new HashMap<>(oldSnapshot);
                copy.put(registrationId, updated);

                if (active.compareAndSet(
                        oldSnapshot, Map.copyOf(copy))) {
                    return true;
                }
            }
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry(Map.of(
            "tenant-a", new TenantTrust(
                "tenant-a", "https://idp-a.example.org/entity",
                42, Set.of("A-old")),
            "tenant-b", new TenantTrust(
                "tenant-b", "https://login-b.example.net/issuer",
                8, Set.of("B-current"))
        ));

        System.out.println("A old initially: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-old"));

        System.out.println("A overlap published: " + registry.rotate(
            "tenant-a", 42, Set.of("A-old", "A-new")));

        System.out.println("A new accepted: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-new"));

        System.out.println("B rejects A key: " + registry.accepts(
            "tenant-b", "https://login-b.example.net/issuer", "A-new"));

        System.out.println("B old unaffected: " + registry.accepts(
            "tenant-b", "https://login-b.example.net/issuer", "B-current"));

        System.out.println("Stale A revision rejected: " + registry.rotate(
            "tenant-a", 42, Set.of("A-new")));

        System.out.println("A old retired: " + registry.rotate(
            "tenant-a", 43, Set.of("A-new")));

        System.out.println("A old after retirement: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-old"));

        System.out.println("A new after retirement: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-new"));
    }
}
```

Run with JDK 17+:

```bash
javac TenantMetadataRotationDemo.java
java TenantMetadataRotationDemo
```

**Exact** stdout:

```text
A old initially: true
A overlap published: true
A new accepted: true
B rejects A key: false
B old unaffected: true
Stale A revision rejected: false
A old retired: true
A old after retirement: false
A new after retirement: true
```

### 13.1. Explaining the Output

- Initially tenant A trusts `A-old` at revision 42.
- `rotate("tenant-a", 42, {A-old,A-new})` creates revision 43, maintaining overlap; the app can now accept the new key for **A** once metadata/trust was verified by the control plane.
- Tenant B continues trusting only `B-current`, rejecting A's key even if using the same signature algorithm.
- A job starting from revision 42 cannot overwrite revision 43; `Stale A revision rejected` is `false` (rotation call returns `false`).
- Once IdP A finishes switching, revision 44 keeps only `A-new`, retiring `A-old`.
- `AtomicReference.compareAndSet` guarantees atomic snapshot swaps **inside the demo JVM**; it does not replicate across pods or provide distributed CAS transactions in Redis.
- `Set.copyOf`/`Map.copyOf` keep snapshots immutable, yet **do not verify SAML provenance, issuers, or signatures**.

**Never use `accepts(...)` in place of production signature verification:** an attacker can self-assert `signingKeyLabel="A-new"`. Real systems must verify **the cryptographic signature on the signed Response/Assertion** using registration A's IdP public key, plus issuer, audience, destination, recipient, timestamps, `InResponseTo`, and tenant mapping. The demo illustrates only version/trust isolation.

### 13.2. What Is Missing for a Production System

A production implementation needs:

1. Source-pinned metadata fetcher, signed metadata verification/approval, and hardened XML parsing.
2. Constructing `Saml2X509Credential.verification(...)` from real PEM/DER certs for the right IdP registration.
3. Transactional config storage and per-tenant snapshot distribution across SP nodes, not just a local `AtomicReference`.
4. Consistent full rebuild of `RelyingPartyRegistration` A: issuer, endpoints, bindings, credentials, and algorithm policies.
5. Storing metadata signer anchors separately from IdP signing keys so metadata never self-authenticates.
6. Grace windows, emergency key revocation, last-known-good version/rollback, and drift monitoring.
7. Integration with Spring Security's version-appropriate request/response filters and providers without custom trust bypasses.
8. Protecting key material with secret stores/HSMs and least privilege; never store private keys in a demo registry.

## 14. Turning Metadata Records into Spring Security Configuration

When updating tenant A:

```text
Verified candidate metadata for tenant-a v43
  |
  +-- ensure entityID still https://idp-a.example.org/entity
  +-- validate SSO/SLO endpoints/bindings and allowed hosts
  +-- extract IDPSSODescriptor signing certificates
  +-- ensure key strengths/algorithms per A policy
  +-- create versioned RelyingPartyRegistration for tenant-a
  +-- preserve SP A signing/decryption credentials unless separately rotated
  |
  v
Publish A v43 atomically into registration repository
  |
  +-- tenant-b registration unchanged
  +-- existing sessions not automatically remapped to B
  +-- in-flight requests handled by overlap/state policy
```

Use Spring Security's supported builders/metadata APIs rather than hand-parsing `SAMLResponse` or swapping signing keys from a header. With a dynamic store, only **validated configuration** may enter the live repository. Rebuilding the whole registration avoids hybrid broken states like "old issuer + new endpoint + missing cert" inside a mutable object.

### 14.1. Avoid Partial Updates

A single update may alter multiple fields:

- IdP `entityID` / SSO URL.
- IdP `verificationX509Credentials`.
- SLO endpoints/bindings.
- `wantAuthnRequestsSigned` and algorithm metadata.
- SP `entityID`/ACS metadata when both sides coordinate a contract update.

Never mutate fields individually on an object concurrently read by live requests. **Atomic per-tenant snapshots** ensure every request sees a consistent configuration set. If login starts under an older version and the callback arrives under a newer version, rely on proper overlap and correlation—never "try every tenant's keys" to make a response pass.

### 14.2. Never Overwrite Trust Config from an IdP Payload

An IdP may embed `ds:KeyInfo` or a self-described issuer inside a `SAMLResponse`. Those fields are **not** approved candidate metadata. Never update `RelyingPartyRegistrationRepository` from a browser-delivered `SAMLResponse`, and never let users supply certificates via a login form.

## 15. Caching, Refresh, Last-Known-Good, and TTL

### 15.1. Different Caches, Different Risks

| Cache / Store | Data | Risks |
| --- | --- | --- |
| **Active tenant registration cache** | `RelyingPartyRegistration` / verified IdP metadata | Stale trust, wrong IdP keys/endpoints, cross-node drift |
| **SAML pending AuthnRequest repository** | ID/`RelayState`/context of in-progress login | Lost `InResponseTo`, login failure/injection if browser binding is weak |
| **Replay cache** | Already-processed SAML Response/Assertion IDs | Replay across pods if local-only |
| **`HttpSession` store** | Browser session / `SecurityContext` | Lost authentication state when callback hits another node |

Metadata cache TTLs do not replace logout/session TTLs or replay windows; sharing Redis does not mean every record type shares the same lifecycle rules.

### 15.2. Last-Known-Good Must Have Bounds and Provenance

If IdP A's metadata endpoint suffers a temporary network error:

- Never overwrite active A with empty or unverified metadata.
- You may continue serving **last-known-good authenticated config** within limits allowed by `validUntil` and your **stale-use policy**; this is a threat-reviewed availability choice, not permission to ignore expiration indefinitely.
- Once metadata truly expires or key compromise is confirmed, fail closed per policy even if it interrupts A's SSO.
- Tenants B/C continue using their active snapshots while valid.
- Alert on A's fetch failures, time-to-`validUntil`, key rollover windows, and version-drifted pods.

### 15.3. Do Not Treat `cacheDuration=PT6H` as an Absolute SLA

`cacheDuration` is a SAML metadata caching hint, not a guarantee that the IdP will wait six hours to rotate keys or that certs remain valid for six hours. Agree separately on **advance key-rollover notice**, refresh schedules, and propagation deadlines. An unexpired `validUntil` does not mean a **key compromise requiring immediate revocation** cannot happen.

Separate fetch interval, cache TTL, maximum stale grace, manual revoke pushes, in-flight SAML request TTL, and incident response thresholds.

## 16. Security Threat Model for Multi-Tenant Metadata/Rotation

| Threat | Attack / Failure Mode | Defense |
| --- | --- | --- |
| Metadata substitution | Attacker alters A's metadata file/URL and injects their key | Authenticated source/metadata signature, approved bootstrap trust, staged validation |
| SSRF / XML external entities | Arbitrary metadata URL/DTD/XML refs | URL allowlist, network egress policy, XML parser hardening and limits |
| Cross-tenant key trust | Key A gets added to B's allowlist | Per-registration verification credentials + negative tests |
| Tenant confusion | Callback A resolves to B due to shared issuer or missing registration in URL | Request/tenant binding, explicit registration selection, reject ambiguity |
| Premature key rollover | IdP switches to `A-new` before all SP nodes trust it | Pre-publish, readiness gates, rollout dashboard |
| Old key never retired | `A-old` stays trusted indefinitely after migration | Time-boxed overlap, signed change tickets, retirement plan |
| Compromised old key kept in overlap | Attacker signs SAML assertions with `A-old` | Emergency revoke, invalidate impacted sessions, zero grace |
| Key type / algorithm downgrade | New metadata requests RSA-SHA1 or weak key | Explicit signature/key-strength allowlist; reject unsupported |
| SP signing key leaked | Attacker signs AuthnRequests posing as SP | HSM/secret ACL/rotation, incident response, and IdP trust update |
| SP decrypt key leaked | Assertions decrypted without authorization | Rotate decryption cert/key and assess data exposure |
| Metadata signing trust hijack | SP trusts anchor embedded in untrusted metadata | Out-of-band trust bootstrap/approval |
| Cache poisoning / race | Stale revision job overwrites newer tenant config | Immutable versions, CAS/optimistic lock, audit |
| Inconsistent nodes | Pod A trusts `A-new`, Pod B does not | Desired/applied version tracking, health checks, rollout guards |
| Replay / correlation bypass | Validly signed Response submitted against wrong pending request | Validate `InResponseTo`, audience/recipient/time, replay cache |
| Trust broadening on failure | Retry verification against every tenant's cert | Fail closed; never fall back globally |
| Excessive logging | Full assertion/metadata key material in traces | Log only event IDs/public fingerprints + redaction, protected audit |
| Account collision | Two tenants share email/`NameID` | Composite subject namespace + tenant authorization |
| Unapproved endpoint migration | New SSO `Location` points to attacker host | Allowed domain/policy diff + human approval |

**Specifically:** a valid RSA-SHA256 signature from IdP B must never be accepted as tenant A identity. **A valid cryptographic algorithm does not mean a valid issuer or tenant.**

## 17. End-to-End Testing When Tenant A Rotates

### 17.1. Functional Tests

| Case | Expected Outcome |
| --- | --- |
| `A-old` signs `SAMLResponse` at baseline | SP login for tenant A succeeds |
| `B-current` signs `SAMLResponse` at baseline | SP login for tenant B succeeds |
| Publish `A-new` in authenticated metadata A | Candidate builds cleanly; does not alter active before approval |
| After deploying A overlap, `A-old` signs response | PASS within A's grace window |
| After deploying A overlap, `A-new` signs response | PASS within A's grace window |
| `A-new` key sent claiming issuer B | **REJECT** |
| `B-current` continues logging in across all A rollout steps | PASS; B's revision/keys unchanged |
| IdP A switches to `A-new` after all pods are ready | Zero-disruption login for A |
| `A-old` retired after grace | `A-old` is **REJECTED**; `A-new` still PASSES |
| A rolls back from bad endpoint metadata | Reverts only to approved trusted A version; B/C untouched |
| Tenant C updates SSO endpoint independently | Tested for C separately; A/B unchanged |
| Temporary A metadata refresh failure | Does not wipe active A; follows stale policy |
| A metadata past `validUntil` | Does not relax trust just to let login pass |
| A signer compromised | Revoked immediately per incident workflow without waiting for grace |
| IdP A key/cert outside proper `KeyDescriptor` | Reject |
| Invalid signed metadata | Candidate rejected, not deployed |
| Certificate rolled over on pod A while pod B lags | Readiness gate blocks IdP signer cutover |
| User login in flight during key switch | Callback uses right registration/state and accepted overlap keys |

### 17.2. Negative Tests for Registration / Tenant Isolation

- Request initiated at `/saml2/authenticate/tenant-a`, yet response carries B's issuer → reject.
- Response signed with A-key yet audience targets another SP → reject.
- Response signed with B-key yet issuer claims A → reject.
- Two tenants share an issuer and callback lacks clear request state → reject ambiguity; never pick randomly.
- Identical `NameID`/email in A and B → never grant cross-tenant resource access.
- Tenant A metadata changes issuer without approval → reject candidate / flag high-risk migration.
- Metadata URL redirects to private IP / local network → fetch rejected.
- Metadata XML contains DTD / external entity → parser rejects / XXE hardened.
- Oversized metadata file or abnormal `EntityDescriptor` nesting → rejected per limits.
- Candidate uses RSA 1024 or SHA-1 violating signature policy → reject.
- Revoked old key submitted after emergency revocation → rejected on every pod.
- Validly signed authentication response with mismatched/expired `InResponseTo` → reject.
- Stale metadata cache with new key unpropagated → never fall back to trusting `KeyInfo`.

### 17.3. Race and Rollback Tests

1. Two jobs read A revision 42 concurrently. Only one publishes revision 43; the other hits a version conflict.
2. Publishing A revision 43 leaves B revision 8's map/snapshot untouched.
3. Roll out to cluster 1 before cluster 2; IdP A must not switch signing keys while cluster 2 is unready.
4. Attempt to inject a candidate with an invalid certificate/issuer; active A preserves last-known-good.
5. Rollback after a bad candidate uses only an older revision **still trusted by policy**, never restoring a revoked/compromised key.
6. Across multiple pods, callbacks landing on a different pod still verify A's keys and request state; test real signatures/digests/audiences/correlation.
7. Test concurrent in-flight transactions during IdP key switches; confirm pending request repositories and session cookies stay intact.

### 17.4. Acceptance Criteria

- **Security:** zero cross-tenant/issuer/key acceptance; verified metadata provenance; SAML protocol validation never bypassed.
- **Availability:** routine key rollover causes zero login outage when following overlap/pre-publish, or only contracted maintenance downtime.
- **Consistency:** desired/applied revisions converge across SP nodes before switchover.
- **Isolation:** an error or refresh in A never breaks logins or changes trust in B/C.
- **Observability:** clear visibility into tenant, revision, and key status without logging raw assertions or private keys.
- **Recovery:** tested rollback, emergency revocation, config history, approval audits, and alerting.

## 18. Minimal Dashboard and Logging

A metadata update event may look like:

```json
{
  "event": "saml_tenant_metadata_activated",
  "tenant": "tenant-a",
  "registration": "tenant-a",
  "previous_revision": 42,
  "new_revision": 43,
  "change_class": "IDP_SIGNING_KEY_OVERLAP",
  "approval_id": "change-741",
  "result": "ACTIVE",
  "timestamp": "2026-11-07T04:00:00Z"
}
```

This JSON is an **illustrative mock**. Never log full `SAMLResponse`, `SAMLRequest`, `NameID`/email/groups, session cookies, `RelayState` secrets, private keys, or exceptions containing XML. Public certificate fingerprints may be logged per policy when helpful operationally, yet never use raw untrusted subjects/issuers from payloads as log labels.

Monitoring should track:

- `metadata_fetch_success/failure` and `metadata_signature_invalid` per registration.
- `metadata_valid_until_seconds_remaining` and elapsed time since the last validated refresh.
- `saml_registration_desired_revision` vs. `applied_revision` on every node.
- `idp_signing_key_rollover_state`: `PREPARED` / `OVERLAP` / `SWITCHED` / `RETIRED` / `EMERGENCY_REVOKED`.
- `saml_response_signature_invalid_total`, `issuer_mismatch_total`, and `authentication_success_rate` per tenant.
- Callback failure rate due to missing pending AuthnRequest/session (to distinguish signature errors from state errors).
- Certificate expiry, algorithm weaknesses, key usage policy violations, and signing method distributions observed in **test/validated telemetry**.

Never place raw browser tenant names, account emails, or unbounded algorithm URIs into metric labels; use allowlisted registration IDs to prevent log injection and cardinality explosions.

## 19. Recommended Operational Runbook for One Tenant

### 19.1. Before Change

- Confirm tenant ID, owner, IdP `entityID`, metadata source, and verified IdP admin contact.
- Inspect active version, keys, and expiration dates; classify as IdP signing, SP signing, decryption, or metadata signer rotation.
- Is the issuer, endpoint, or policy changing, or only a key being added? Assess blast radius and approvals.
- Test fetching/verifying metadata in staging without modifying active configs.
- Prepare test fixtures signed with old/new keys; never use real customer assertions for debugging.
- Schedule the IdP switch **after** SP readiness, with rollback and revocation plans ready.

### 19.2. During Change

- Publish A's validated candidate version with old+new certs under the exact registration.
- Wait for all pods to confirm applied version; test `SAMLResponse`s under `A-old` and `A-new`.
- IdP switches signer to `A-new`; monitor errors and latency.
- Tenants B/C must continue operating normally; avoid full app restarts if architecture supports safe hot-swapping.
- Keep overlap time-boxed; never extend automatically if compromise is suspected.
- Audit change ID, version, outcome, and IdP admin confirmation.

### 19.3. After Change

- Wait out the SAML in-flight window and IdP propagation, confirming `A-old` is no longer used.
- Remove `A-old` from A's trusted verification keys and verify B/C are unchanged.
- Test that `A-old` **rejects**, `A-new` **accepts**, and `B-current` **accepts**.
- Confirm new expiration/rotation reminders, metadata `validUntil`, and monitoring alerts.
- Close the ticket and config history so no stale pod continues trusting `A-old`.
- If a key compromise is discovered, execute emergency incident response rather than closing a routine change ticket.

## 20. Review Questions

**1. Why can't you put every IdP's public certificates into one shared list to verify all `SAMLResponse`s?**  
Because a valid signature under certificate A does not prove IdP B or tenant B issued the message. Trust must bind to the **approved registration and issuer**.

**2. Are `registrationId`, `tenantId`, and IdP `entityID` always identical?**  
No. `registrationId` is Spring Security's key; `tenantId` is the business boundary; IdP `entityID` is defined by the IdP. You need verified mappings.

**3. When IdP A's metadata contains `A-new`, should you immediately add that key to the trusted set?**  
Only when the metadata/source is verified against your bootstrap trust and the candidate passes policy and approval. Never trust a key merely because it appeared in newly downloaded XML.

**4. Why does a rollover need an `A-old` + `A-new` overlap phase?**  
So the IdP can switch signers while the SP still verifies in-flight responses after all SP nodes have received the new key. This phase must be time-bounded.

**5. If `A-old` is compromised, should you keep an overlap window for zero downtime?**  
No. Revoke per incident response, accept fail-closed behavior, and coordinate re-login and rotation.

**6. Can metadata signed with a new cert embed that same cert inside `KeyDescriptor` to self-verify?**  
No. Metadata signatures require a **trust anchor bootstrapped outside the current metadata**, never arbitrary trust-on-first-use.

**7. If the SP signs AuthnRequests for A, does rotating IdP A's verification key change the SP's private signing key?**  
No. The two directions and credential roles are independent and rotate separately.

**8. Do `validUntil`, `cacheDuration`, and certificate `NotAfter` mean the same thing?**  
No. Metadata validity, caching guidance, and X.509 certificate lifetimes are distinct concepts.

**9. Does `CachingRelyingPartyRegistrationRepository` automatically handle metadata signature validation and safe per-tenant refresh?**  
No. Its contract covers caching and lazy loading; signature provenance, per-tenant validation, version approvals, and rollouts must still be designed and tested. Per API docs, this class arrived in Spring Security 6.4.

**10. Why do metadata updates need compare-and-swap / revisions?**  
So a job starting from an older version cannot overwrite a newly approved version, and other tenants avoid partial updates.

**11. Can you use email from a `SAMLResponse` to pick the tenant instead of request state/issuer?**  
No. Emails can collide across tenants and are just assertion claims; always verify signatures, registration, and tenant mapping.

**12. How do you confirm a key rotation has finished safely?**  
All pods report the right revision, `A-new` logins pass, `A-old` is rejected post-retirement, B/C continue passing, SAML error metrics are normal, and the change audit is recorded.

## 21. Standards and API References

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): multiple `RelyingPartyRegistration`s, builders, metadata loading, credential roles, and request/response filters.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parsing/trusting IdP metadata, metadata signature verification with OpenSAML 5, and SP metadata endpoints.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): verifying IdP signatures, issuer, audience, conditions, and customization.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): outbound signing and IdP binding/metadata.
- [Spring Security API – `CachingRelyingPartyRegistrationRepository`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): introduced in 6.4, caching loader/`setCache`, and default no-expiry behavior.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `IDPSSODescriptor`, `KeyDescriptor`, endpoints, `validUntil`/`cacheDuration`.
- [OASIS SAML 2.0 Metadata Interoperability Profile](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.pdf): `KeyDescriptor` details, metadata trust/rollover, compromised vs. retired key behaviors.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Response`, `Assertion`, `Issuer`, `Audience`, `InResponseTo`, `SubjectConfirmation`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): SAML signature trust, XML hardening, response validation, and replay.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): blocking unauthorized metadata URL fetches, redirects/DNS controls.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle, rotation, compromise, and secret storage.

**Conclusion:** In multi-tenant federation, **metadata is trust configuration**, not an XML file to overwrite unconditionally. Each tenant needs isolated registrations, issuers/endpoints, IdP verification keys, SP signing/decryption credentials, and policies—or explicitly governed sharing. Rotate keys safely via **pre-publish → validate → stage/approve → publish old+new → IdP/SP switch → observe → retire**, keeping emergency revocation separate from routine overlap. Updates require immutable revisions, verified metadata provenance, all-pod readiness, and cross-tenant regression testing; never open global key trust or disable SAML validation to mask rollout errors.