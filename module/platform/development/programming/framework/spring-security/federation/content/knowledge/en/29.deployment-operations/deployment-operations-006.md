# Metadata Exchange and Overlapping Key Rollover Procedure in Spring Security Federation

## 1. Why Should SSO Keys Not Be Replaced in a Single Deploy?

In a **Spring Security – federation** system using **SAML 2.0**, the Service Provider (**SP**, the Spring Security/Relying Party application) and Identity Provider (**IdP**, Asserting Party) exchange metadata to agree on each other's **entity ID, endpoints, bindings, public keys, algorithms, and trust conditions**. Each side holds its **own private key** and must never transfer its private key to the partner.

When the IdP's signing key or the SP's encryption key nears end-of-life, a "one-shot" swap usually causes an outage:

~~~text
Day T0:
  IdP signs SAMLResponse with K_IDP_OLD.
  SP trusts only public key K_IDP_OLD.
  Users log in successfully.

Day T1 - ABRUPT KEY SWAP:
  IdP switches to signing with K_IDP_NEW.
  SP has not fetched new metadata/cert yet, trusting only K_IDP_OLD.
  -> XML signature verification FAILS.
  -> Application rejects all logins using K_IDP_NEW.

Or:
  IdP switches to encrypting Assertions for K_SP_NEW.
  SP has not installed private key K_SP_NEW yet.
  -> EncryptedAssertion cannot be decrypted.
~~~

The operational practice that avoids downtime is **key rollover with overlap**: **publish the new key first**, ensure partners accept it, **only then switch the active key in use**, and continue **keeping the old key long enough** for cached metadata and in-flight messages to expire. Only at the end do you retire the old key per change plan.

This lesson belongs to **Deployment and Operations**, covering design, metadata exchange, key-ring operations, rollout, testing, monitoring, and rollback. After studying it, you will be able to:

1. Distinguish the **IdP SAMLResponse signing key** from the **SP AuthnRequest signing key**, the **SP EncryptedAssertion decryption key**, and the **metadata-signing trust anchor**.
2. Inspect `<md:KeyDescriptor use="signing">`, `use="encryption"`, and X.509 certificates carrying public keys in XML metadata.
3. Map **who owns the private key and who must update the public key** for each rotation type.
4. Build a **prepare → publish → propagate → activate → observe → retire** schedule, sizing the overlap window for caches, fetches, latency, and rollback.
5. Exchange metadata over an **authenticated channel**, never accepting a new certificate merely because it sits inside an untrusted document.
6. Understand the limits of Spring Security **`RelyingPartyRegistration`**, **`Saml2X509Credential`**, **`OpenSaml5AssertingPartyMetadataRepository`**, metadata endpoints, and caching/refresh.
7. Configure a phase where the SP supports **two decryption keys** and two IdP verification keys while explicitly choosing the **active signing key**.
8. Preserve **signature, issuer, audience, recipient, destination, InResponseTo, and replay** checks throughout rotation; never disable validation to "fix" certificate errors.
9. Build runbooks coordinating with the IdP, multi-tenant setups, CI/CD, Kubernetes, HSM/KMS, observability, and rollback.
10. Run a **standalone Java 17** demo simulating a public-key trust ring and encryption-key overlap using **JCA RSA-SHA256, RSA-OAEP, and AES-GCM**; distinguish it from real SAML XMLDSig/XML Encryption.

**Key takeaway:** *The new public key must be published and trusted by the receiving party **before** the new private key starts being used for live messages. The old public key must not be removed until every message that could use the old key has expired and partners have finished migrating—the sole exception being a key-compromise emergency.*

## 2. Scope: SAML Metadata Differs from OIDC JWKS and CAS

**SAML 2.0 metadata** is typically an XML `<md:EntityDescriptor>` or `<md:EntitiesDescriptor>` containing role descriptors:

- `<md:IDPSSODescriptor>`: IdP SSO/SLO endpoints and IdP signing/encryption key descriptors.
- `<md:SPSSODescriptor>`: SP ACS/SLO endpoints, plus optional SP signing/encryption key descriptors.
- `entityID`: stable identifier for each SAML entity.
- `<md:KeyDescriptor>` and `<ds:KeyInfo>`: public keys / X.509 certificates that the counterparty can use for signature verification or encryption.
- `validUntil` and `cacheDuration` (if present): metadata validity/caching hints, not an automatic grant of trust to unsigned metadata.

**OIDC/OAuth 2.0** uses a discovery document and **JWKS** for JWT signing keys, `kid`, `jwks_uri`, and token validation; the concept of **publish new key before switching signer, keep old until JWTs expire** is similar, yet **never use SAML KeyDescriptor/XML metadata rules to interpret JWKS**. A **CAS Service Ticket** is a one-time credential, not signed JWT/JWKS key rollover; CAS uses its own trust/PKI mechanisms.

Accordingly, this article **uses SAML2 in Spring Security as its primary scenario**, with a brief OIDC comparison table near the end to prevent mixing protocols.

## 3. Who Owns Which Key and Who Must Act?

| Purpose | Private key owner | Public key consumer | Message direction | During rotation |
| --- | --- | --- | --- | --- |
| **IdP signs SAMLResponse/Assertion** | **IdP** | **SP** stores cert for verification | IdP → SP | SP must trust new IdP signing public key **before** IdP signs with the new private key |
| **SP signs AuthnRequest/LogoutRequest** | **SP** | **IdP** stores SP's public signing key | SP → IdP | IdP must trust new SP signing public key **before** SP switches signer |
| **SP decrypts EncryptedAssertion** | **SP** | **IdP** encrypts using SP's public key | IdP → SP | SP must **install the new private decrypt key before** IdP encrypts to the new public key; retain old private key |
| **IdP decrypts messages from SP** | **IdP** | SP uses IdP encryption public key | SP → IdP | IdP must install new private key before SP switches encryption |
| **Signing SAML metadata** | Metadata publisher/federation operator | Metadata consumer with **independent trust anchor** | Metadata exchange | Rotate **metadata signing trust** on its own cycle; never confuse with assertion signing |
| **HTTPS metadata endpoint TLS** | Endpoint server/proxy | HTTP/TLS client trust store | Metadata fetch | Rotate TLS cert per PKIX/CA/server name; not itself a SAML signing cert |

**Private keys never appear in SAML metadata.** The metadata consumer needs only the **public key/certificate** for verification or encryption. If a "metadata export" contains a private key or keystore password, treat it as a security incident and halt publication.

### 3.1. Two Reversed Timelines

**When rotating a signing key:**

~~~text
1. Producer generates new private/public signing key.
2. Producer publishes new PUBLIC verification key alongside old PUBLIC key.
3. Consumers refresh + trust BOTH.
4. Producer begins SIGNING with new PRIVATE key.
5. Consumers verify both old/new during overlap.
6. Wait for in-flight/metadata cache/rollback margins to complete.
7. Consumers stop trusting old PUBLIC key; producer protects/retires old PRIVATE key per policy.
~~~

**When rotating the SP's decryption key:**

~~~text
1. SP generates new decrypt private/public key.
2. SP installs new PRIVATE decryption key while retaining old PRIVATE key.
3. SP publishes both old/new PUBLIC encryption keys in metadata.
4. IdP refreshes and verifies it can select the new public key.
5. IdP switches to ENCRYPTING with the new public key per plan.
6. SP decrypts using either new or old private key during overlap.
7. Wait for old messages/queues/replay windows to expire.
8. SP stops decrypting with old private key and removes old public key from metadata.
~~~

**Note:** merely "putting both encryption certificates in metadata" **does not guarantee the IdP will automatically pick the new key** or pick in your preferred order. SAML metadata can list multiple keys, yet **sender-specific selection behavior** must be confirmed through testing and operational agreement.

## 4. Reading Metadata XML: Entity, Role, KeyDescriptor

IdP metadata can carry **two simultaneously accepted signing keys**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <!-- ds:KeyInfo / ds:X509Data / ds:X509Certificate
         contains IdP PUBLIC CERTIFICATE old -->
  </md:KeyDescriptor>
  <md:KeyDescriptor use="signing">
    <!-- ds:KeyInfo / ds:X509Data / ds:X509Certificate
         contains IdP PUBLIC CERTIFICATE new -->
  </md:KeyDescriptor>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.test/sso"/>
</md:IDPSSODescriptor>
~~~

**This is an XML structural sketch, not valid metadata to import into an IdP/SP.** Comments merely indicate where `ds:KeyInfo` sits; real metadata requires full namespaces, `EntityDescriptor`, Base64 X.509 certificate content, attributes, and a metadata signature per profile.

For SP encryption:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="encryption">
    <!-- SP PUBLIC encryption CERTIFICATE old -->
  </md:KeyDescriptor>
  <md:KeyDescriptor use="encryption">
    <!-- SP PUBLIC encryption CERTIFICATE new -->
  </md:KeyDescriptor>
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://portal.example.test/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

### 4.1. Distinguishing the `use` Attribute

- `use="signing"`: key used to verify signatures/transport authentication per SAML metadata semantics.
- `use="encryption"`: key suitable for encrypting/wrapping content encryption keys sent to the entity.
- When **`use` is omitted**, metadata profiles may interpret the key as applying to **both signing and encryption**. Never assume a missing `use` means signing only.
- `ds:X509Certificate` carries the **certificate/public key**, never the private key.
- `md:KeyDescriptor` may include `EncryptionMethod` or algorithm constraints; senders must support matching algorithms.
- Metadata `entityID`, endpoints, bindings, and requirements must not change casually alongside key rotation unless governed as **a separate migration**.
- In multi-tenant setups, IdP A's metadata must never be trusted automatically for tenant B without explicit federation configuration.

### 4.2. SAML Certificates vs TLS Certificates

Both may use **X.509**, yet their roles differ:

| Certificate | Authority of trust | Where checked | Must not be confused with |
| --- | --- | --- | --- |
| SAML IdP signing cert | Public key bound to the IdP entity from **trusted metadata/config** | XMLDSig validator | Do not trust merely because of TLS CN/CA |
| SAML SP encryption cert | Public key used to encrypt assertions for the SP | IdP encryption producer | Not the browser HTTPS certificate |
| Metadata signing cert | Independent trust anchor verified by federation/operator | Metadata signature verifier | Never use a new key inside metadata to verify that same metadata |
| HTTPS server cert | PKIX/hostname/TLS trust | HTTP client/proxy | Valid HTTPS does not replace metadata provenance controls |
| SAML SP signing cert | Public key IdP uses to verify AuthnRequest | IdP SAML validator | Never give the private signing key to the IdP |

In many SAML profiles, certificates embedded in metadata serve as **public-key carriers / direct trust** rather than requiring a browser-style CA chain. The OASIS Metadata Interoperability Profile recommends consumers establish trust from **accepted metadata** rather than imposing an independent PKIX/OCSP policy on metadata keys by default. Organizations may still maintain internal policies on certificate validity, algorithms, key sizes, and HSMs. **Never assume a cert "before NotAfter" is automatically trustworthy, or that every implementation checks SAML cert NotAfter like HTTPS.** What matters most is **trust provenance + cryptographic algorithms + key continuity**.

## 5. Secure Metadata Exchange: Bootstrap Trust Before Rotation

Updating metadata is **an operation that alters a trust boundary**. An attacker who injects their own public key into IdP metadata accepted by the SP can make the SP trust SAMLResponses signed by the attacker; hence **automated refreshes without provenance checks can be riskier than approved static metadata**.

### 5.1. Through Which Channels Is Metadata Accepted?

Valid approaches depending on environment:

1. **Signed metadata from the federation/IdP**, where the consumer holds a **metadata signature verification trust anchor provisioned out-of-band**. Verify the signed root/chain/pin, freshness, expiration, and expected entityID.
2. **A trusted HTTPS endpoint** with upstream authentication, certificate chain, hostname, and provenance verification; organizations may add an **out-of-band verified fingerprint or checksum** before initial bootstrap.
3. **Metadata file/artifact delivered through a change-managed repository**: reviewed, signed artifact/attestation, checksums, provenance, version checks, and rollout deployment.
4. **A federation operator registry** with SLAs, metadata signatures, validity/cache controls, and documented trust anchors.

A metadata URL starting with `https://` does not imply **XML metadata signature** verification. It only means TLS transport can be verified; **initial trust and XML integrity** still depend on the provisioning model.

### 5.2. A Key Fact About Modern Spring Security

Spring Security 7.x documentation describes `OpenSaml5AssertingPartyMetadataRepository`:

- Can use an **OpenSAML MetadataResolver** to refresh metadata per expiry/cache policy.
- Can verify metadata signatures using `verificationCredentials(...)`.
- **If metadata verification credentials are not provided, the component will NOT perform metadata signature validation**.
- `fromTrustedMetadataLocation(...)` expresses a metadata source the organization already decided to trust; it **does not replace** provenance approval and does not turn an assertion certificate inside XML into the metadata trust anchor.
- Distinguish the **metadata-signing trust anchor** from the **IdP keys used to verify SAMLResponse**; they follow two separate rotation cycles.

Illustrative Spring Security 7.x example:

~~~java
// Spring Security 7/OpenSAML 5 integration fragment,
// cannot run standalone without project/dependencies.
Saml2X509Credential metadataSigner =
    Saml2X509Credential.verification(
        metadataSigningCertificateApprovedOutOfBand);

AssertingPartyMetadataRepository metadataRepository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.test/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataSigner))
        .build();
~~~

`metadataSigningCertificateApprovedOutOfBand` is loaded from a controlled trust provisioning system—**not an arbitrary certificate plucked from the metadata being verified**. This snippet only illustrates the API; add imports, bean wiring, repository cache refresh, and failure policies per your project version.

### 5.3. Exchange Procedure Before Rotation Day

A change request should specify:

- IdP and SP **Entity IDs**, registrationId, and tenant.
- Fixed **public metadata endpoint** or signed file location.
- **SP ACS, SSO, and SLO URLs** with exact public scheme/host/path.
- Key type: **IdP assertion signing**, **SP AuthnRequest signing**, **SP decrypt**, or **metadata signing trust**.
- **Current and new SHA-256 certificate/public-key fingerprints**, cross-checked over an independent authenticated channel.
- Who manages the private key, HSM/KMS/key vault alias, storage location, and access controls; never exchange private keys.
- **Publish** date, **propagation** window, **activate** date, **overlap** period, **retire** date, and rollback deadline.
- Metadata `validUntil`/`cacheDuration` if applicable, actual partner cache TTL, and fetch-failure backoff policy.
- SAMLResponse/Assertion/AuthnRequest lifetimes, in-flight queues, clock skew, logout messages, and regions/replicas.
- Who must **acknowledge**: IdP operator, SP operator, network/secret management, on-call, and security approver.
- Runbook/rehearsal, canary cohort, monitoring, rollback owner, and contacts during the change window.

**Never rely solely on "we emailed the new certificate"**; confirm the partner has **actually loaded and exercised** the new key before cutover.

## 6. Standard 6-Phase Process for Overlapping Key Rollover

<escape></escape>

| Phase | State | Required actions | Gate to next phase |
| --- | --- | --- | --- |
| **P0 Inventory** | K_old only | Record current metadata, fingerprints, issuer/ACS/roles, consumers, and cache behavior | Full visibility into who uses the key |
| **P1 Prepare** | K_old active, K_new offline | Generate new key pair, verify crypto, install/store private key inside its security boundary | Cert/key match verified and no private key leak |
| **P2 Publish** | Metadata has old + new | Sign/deploy metadata, verify signature/provenance, notify partners | New metadata distributed securely |
| **P3 Propagate/overlap** | Consumers trust old/new; old usually stays active | Refresh, verify fingerprints, canary both keys, record acknowledgements | All critical consumers ready |
| **P4 Activate** | Producer switches to new key; consumers still trust both | Canary rollout, live signed/encrypted flows, monitor, rollback ready | New-key flows pass stably |
| **P5 Retire** | Only new trusted/used | After TTL/in-flight/rollback window, remove old from metadata/trust/decrypt ring; run negative test | No valid traffic uses old key and security approves |

**Never create a "K_new only" gap at the consumer while the producer still uses K_old.** Phases P3/P4 must genuinely exist in runtime, not merely as two certificate files sitting on disk while the service has not loaded them.

### 6.1. Verifiable Timeline

~~~text
Time ---------------------------------------------------------->

Producer metadata:
  [ OLD key only ] [ OLD + NEW published ........ ] [ NEW only ]

Producer active signer:
  [ OLD signs ................................ ] [ NEW signs .... ]

Consumer trusted verification set:
  [ OLD only ]  [ OLD + NEW verified ............ ] [ NEW only .... ]

                                  ^
                             CUTOVER only after
                        all critical consumers updated

Overlap:
  T_publish_new ... T_retire_old
  includes propagation + retry/cache + response lifetime + rollback margin
~~~

**There is no single standard overlap duration.** It depends on partner count, metadata caching, SLAs, federation operators, rollback needs, and trust direction.

### 6.2. Sizing the Overlap Window

Variables to account for:

- `P`: the **max metadata cache freshness / refresh interval** limit consumers actually enforce.
- `D`: configuration distribution delay across replicas/regions and partner notifications.
- `M`: maximum lifetime of in-flight messages/artifacts, queues, browser redirects, and logout messages.
- `S`: allowed clock skew and safety margin.
- `R`: rollback/security-review decision window.

A **conservative operational upper bound** can be set as:

~~~text
overlap_window >= P + D + M + S + R
~~~

This is a **planning formula**, not a normative SAML standard rule. With independent confirmation from every partner that metadata updated, you can replace the cache assumption with **acknowledgment/observed key acceptance** per policy, while keeping appropriate M/S/R margins. If a consumer has unbounded cache TTL or cannot hold two keys, **you cannot blindly apply the formula and cut over safely**; coordinate a manual migration, maintenance window, or vendor-assisted transition.

### 6.3. Notes on Metadata `validUntil` and `cacheDuration`

- `validUntil` is the metadata instance's validity limit, if present.
- `cacheDuration` hints how long metadata may be cached; actual behavior depends on the consumer's resolver/config/cache/network.
- HTTP `Cache-Control`, ETags, CDN proxies, Spring cache TTLs, federation aggregators, and sidecar caches can be **independent layers**.
- `cacheDuration` **does not guarantee every partner refreshes on schedule**; verify in practice.
- When metadata refresh fails, **never auto fail-open to unverified metadata** or use expired snapshots forever. You may retain **last-known-good** within an approved bounded window with alerts; once expired, fail closed per policy.
- Do not delete the old verification key from the SP merely because the producer updated `validUntil`; ensure no in-flight messages or rollback constraints remain.

## 7. Rotating the IdP Signing Key: Most Common Case

### 7.1. Standard Steps

**Step 1 — IdP creates new signing key K_IDP_NEW.** Use RSA/ECDSA algorithms supported by SPs, keeping the private key in an access-controlled HSM/KMS/keystore. Never reuse a compromised key in an emergency rotation.

**Step 2 — IdP updates metadata:** same `entityID`, `IDPSSODescriptor` role, adding `<KeyDescriptor use="signing">` for the new public certificate alongside the old one. **Keep OLD as the active signer** initially.

**Step 3 — SP updates trust:** load **verified** metadata showing both OLD + NEW under the same IdP role. If the SP uses static certificates, update verification credentials to list old/new and deploy to **all instances**.

**Step 4 — SP confirms:** test signed assertions from both old and new in staging, checking issuer/audience/recipient/destination/time and local roles. SP sends **acknowledgement** of the new key hash/fingerprint and production readiness.

**Step 5 — IdP switches active signer to NEW:** only after critical SPs are ready. Use canary/traffic gating if supported by the IdP. All new SAMLResponses are signed with the NEW private key.

**Step 6 — Maintain overlap:** SP continues verifying old and new signatures. Do not alter metadata issuer trust or skip response checks. Monitor accepted/rejected message signing key fingerprints.

**Step 7 — Retire OLD:** once all partners have updated and max in-flight+skew and rollback windows expire, remove the old signing public key from trusted metadata/trust stores; revoke/delete/archive the old private key per policy. Verify messages signed solely with OLD are rejected after retirement (unless a break-glass policy demands temporary restoration).

### 7.2. What Breaks If You Reverse the Order?

| Action | Likely failure |
| --- | --- |
| IdP signs with NEW before SP trusts NEW | `Signature validation failed` / untrusted credential |
| SP removes OLD while IdP still signs OLD | Logins fail for users hitting old-key flows |
| IdP metadata updated yet Spring consumer cache did not refresh | `RelyingPartyRegistration` still holds OLD only |
| SP trusts NEW cert via unauthenticated email without provenance | Key substitution; attacker can sign assertions SP accepts |
| IdP changes `entityID` on key-rotation day without SP update | Issuer mismatch even when signature is valid |
| `SigningAlgorithms` changed simultaneously to one SP/IdP lacks | AuthnRequest/response signature algorithm mismatch |
| SP promotes NEW cert automatically as metadata trust anchor | Metadata injection / circular trust |
| Only testing happy path after cutover | In-flight old-key, replay, or tenant bugs go undetected |

### 7.3. Model of SP Trusting Two Keys

~~~text
IdP metadata:
  entityID = https://idp.example.test/saml
  signing public keys = [K_IDP_OLD, K_IDP_NEW]

SP verification key ring for registration "corp":
  allowedSigners = [K_IDP_OLD, K_IDP_NEW]
  expectedIssuer = https://idp.example.test/saml

Incoming SAMLResponse:
  verify XMLDSig using a credential associated with expected issuer
  if verify succeeds -> still validate audience/recipient/destination/
                        InResponseTo/time/replay/account mapping
  otherwise -> FAIL CLOSED
~~~

SAML certificates are not necessarily selected via a `kid` like JWT JWKS; XMLDSig `KeyInfo` may hint at a candidate key, yet **never trust a self-asserted certificate inside an untrusted response merely because `KeyInfo` includes it**. Candidate public keys must come from the **trusted configured set for that exact issuer**.

## 8. Rotating the SP Signing Key: Reversed Trust Direction

The SP signs `AuthnRequest` or `LogoutRequest`; the IdP uses the **SP signing public certificate** from SP metadata/registration to verify.

Order:

1. SP generates `K_SP_SIGN_NEW`, keeping `K_SP_SIGN_OLD` active.
2. SP **publishes OLD + NEW public signing certs** in metadata for that exact SP entity.
3. IdP imports and confirms it trusts NEW; if the IdP permits only **one** SP signing certificate, plan a dedicated migration/maintenance window.
4. SP switches its **active signing credential** to NEW. In runtimes with multiple signing credentials, check which API **picks the signer** rather than assuming every IdP tries all signing keys on outbound messages.
5. IdP continues verifying OLD + NEW while old signed requests/logout messages or rollback remain possible.
6. After the safety window, SP metadata and IdP trust keep NEW only.

Never send OLD or NEW private keys to the IdP. The IdP needs only the **public certificate**. If the IdP requires uploading a certificate in a portal instead of a metadata URL, record **import date, fingerprint, and confirmation of effective configuration**, not merely form submission.

**A dangerous rollout scenario:** two SP replicas share one entityID while replica A signs with OLD and replica B signs with NEW. This is safe only while the IdP **trusts both**. If the IdP trusts only NEW, traffic hitting replica A fails. Avoid rolling deployments without verifying key overlap.

## 9. Rotating the SP Decryption Key: Opposite Order to Signing

With encrypted SAML, the IdP retrieves the SP's public encryption cert from SP metadata and encrypts `EncryptedAssertion`. The Spring Security SP needs the **matching private key** to decrypt.

### 9.1. Safe Order

~~~text
P0: SP decrypt private: [OLD]; IdP encrypt public: [OLD]
    -> old-encrypted assertion works.

P1: SP generates NEW private/public.
    SP installs private: [OLD, NEW].
    SP metadata publishes public encryption keys: [OLD, NEW].
    IdP still selects OLD.
    -> both old and new decrypt at the SP.

P2: IdP confirms metadata refresh + ability to choose NEW.
    IdP starts encrypting with NEW.
    SP private remains [OLD, NEW].
    -> new-encrypted assertion works.
    -> old encrypted in-flight still works.

P3: After in-flight/rollback:
    IdP stops using OLD.
    SP removes public OLD from metadata and private OLD from runtime.
    -> only NEW works.
~~~

**Never publish the NEW public certificate in metadata before every SP replica has the matching private key**: the IdP may pick NEW immediately upon refresh and break logins on un-updated replicas.

**Never delete the OLD private key the moment the IdP switches to NEW**: browsers/queues may still hold encrypted assertions for OLD, and rollback may need OLD decryption. While retaining old, restrict permissions and audit private-key access.

### 9.2. If the IdP Does Not Support Dual Encryption Keys

Not every IdP:

- Can import multiple `KeyDescriptor use="encryption"` entries;
- Selects the new encryption public key automatically after metadata refresh;
- Supports SP-preferred candidate keys or algorithms;
- Refreshes metadata without a restart.

When a partner selects only one encryption key, **establish a time-coordinated runbook**: SP installs both old/new private keys first, IdP cuts over to new at an agreed time, and SP retains old private keys for in-flight assertions. You may need to adjust metadata representation/order per the **specific IdP vendor's documentation**. **The order of `KeyDescriptor` elements is not a standardized guarantee that the IdP picks the first entry.**

### 9.3. Signature, Encryption, and Metadata Are Three Separate Matters

- **SP decryption**: local private key unwraps content encryption keys and decrypts assertions.
- **IdP signing verification**: SP uses the trusted IdP public key to verify XMLDSig.
- **Metadata signature verification**: SP uses an independent trusted federation/metadata signing key to verify the metadata document.

An assertion that **decrypts cleanly** is not yet enough to create an `Authentication`: you must still validate XML signature, issuer, audience, recipient, destination, subject/time conditions, `InResponseTo`, and replay; decrypted data remains **untrusted until validated**.

Spring Security 7.x `OpenSaml5AuthenticationProvider` includes response/assertion decrypters using registered `decryptionX509Credentials`. Writing custom decrypters with the wrong ordering of signature checks and decryption can break XMLDSig correctness; prefer defaults or test rigorously before changing.

## 10. Rotating the Metadata-Signing Key Itself: A Separate Trust Layer

Sometimes the federation operator's **metadata signing certificate** itself is about to change. This is **not** merely "adding a new IdP assertion signing cert."

If consumers currently trust metadata signer `M_OLD`:

1. The metadata operator distributes **M_NEW public key/trust anchor over an independent authenticated channel**.
2. Consumers configure the metadata verifier to trust **M_OLD + M_NEW** during overlap, still accepting only metadata validly signed by **trusted anchors**.
3. The metadata publisher switches to signing XML metadata with private `M_NEW`.
4. Consumers refresh and confirm signed metadata verifies.
5. Keep `M_OLD` until metadata caches/in-flight/rollback windows expire, then retire per policy.

**Never extract a new metadata-signing certificate from unverified XML metadata** and use that certificate to verify the same XML. That is **circular/self-declared trust**. Bootstrap new metadata-signing trust via an independent root/anchor or a security-reviewed rollover signature chain.

If metadata signature verification fails:

- **Never "try disabling signature validation"** just to restore logins.
- Never auto-add certificates found inside metadata to the trusted signing set.
- Retain **last-known-good** only within approved freshness bounds, mark degraded/alert, and fail closed once expired.
- Check signature algorithm, namespaces, canonicalization, signed element/`Reference`, and exact entityID; never edit raw XML after signing.
- Separate metadata signature errors from `SAMLResponse` signature errors in logs and metrics.

## 11. Spring Security: Configuring Credentials with Overlap

### 11.1. Configuration Areas

In Spring Boot, the configuration paths are typically:

~~~text
spring.security.saml2.relyingparty.registration.<registrationId>
  .entity-id
  .assertion-consumer-service-location
  .signing.credentials[]
  .decryption.credentials[]
  .assertingparty
      .metadata-uri
      .verification.credentials[]
      .entity-id / sso-url (when manual)
~~~

Exact property paths and API names depend on **Spring Boot/Spring Security version**. Current Spring Boot 4.1 docs show `signing.credentials[]`, `decryption.credentials[]`, and `assertingparty.verification.credentials[]`. When using `metadata-uri`, metadata can supply verification keys; precedence and caching must be tested with your actual configuration.

### 11.2. Illustrative YAML: SP Decrypts Both OLD+NEW; Verifies IdP OLD+NEW

This is an **example for file-based public/private key configuration in Spring Boot** using descriptive filenames and containing no real secrets. It illustrates a **manually provisioned** deployment with IdP verification credentials; **do not simultaneously declare `metadata-uri` in this example** to avoid confusion over precedence between two trust sources.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://portal.example.test/saml2/metadata/corp"
            assertion-consumer-service-location: "https://portal.example.test/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/saml-keys/sp-sign-active.key"
                  certificate-location: "file:/run/saml-keys/sp-sign-active.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/saml-keys/sp-dec-old.key"
                  certificate-location: "file:/run/saml-keys/sp-dec-old.crt"
                - private-key-location: "file:/run/saml-keys/sp-dec-new.key"
                  certificate-location: "file:/run/saml-keys/sp-dec-new.crt"
            assertingparty:
              entity-id: "https://idp.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "file:/run/saml-trust/idp-sign-old.crt"
                  - certificate-location: "file:/run/saml-trust/idp-sign-new.crt"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: true
~~~

**Version warning:** some Spring Boot versions nest SSO properties under `singlesignon.url`, while others have variant property keys. Validate startup **against the exact version deployed**, using the Spring Boot configuration properties reference and integration tests. This is a **config sketch**, not a claim every property exists across every Boot branch or IdP.

**Why does `signing.credentials` list only active?** For outbound AuthnRequests, the SP must actively select one **private signer**. Passing two signing credentials in the list does not make the SP "sign with both"; many implementations pick one credential by order or policy. Overlap actually lives on the **IdP side trusting both old/new public keys**, while the SP signs each request with one active key.

### 11.3. Java DSL: Explicit Key Rings per Registration

Spring Security API example, assuming certificate/private-key variables were loaded securely beforehand:

~~~java
// Integration fragment (requires imports, Spring Security dependencies,
// PEM/PKCS#8 loader, and project tests).
Saml2X509Credential spActiveSign =
    Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);

Saml2X509Credential spOldDecrypt =
    Saml2X509Credential.decryption(spOldDecryptPrivateKey, spOldDecryptCert);
Saml2X509Credential spNewDecrypt =
    Saml2X509Credential.decryption(spNewDecryptPrivateKey, spNewDecryptCert);

Saml2X509Credential idpOldVerify =
    Saml2X509Credential.verification(idpOldSigningCertificate);
Saml2X509Credential idpNewVerify =
    Saml2X509Credential.verification(idpNewSigningCertificate);

RelyingPartyRegistration corp =
    RelyingPartyRegistration.withRegistrationId("corp")
        .entityId("https://portal.example.test/saml2/metadata/corp")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/corp")
        .signingX509Credentials(credentials -> {
            credentials.add(spActiveSign);
        })
        .decryptionX509Credentials(credentials -> {
            credentials.add(spOldDecrypt);
            credentials.add(spNewDecrypt);
        })
        .assertingPartyMetadata(party -> party
            .entityId("https://idp.example.test/saml")
            .singleSignOnServiceLocation("https://idp.example.test/sso")
            .verificationX509Credentials(credentials -> {
                credentials.add(idpOldVerify);
                credentials.add(idpNewVerify);
            }))
        .build();
~~~

If using a builder initialized from an **existing registration/metadata**, inspect existing credentials before adding to avoid duplicates or retaining a stale signer accidentally. This code omits `@Bean`/imports/keystore loaders because it is an **explanatory fragment**, not a standalone Java program. Production also requires signature/ACS/issuer/profile/endpoint controls and metadata trust provenance.

### 11.4. Spring SP Metadata Endpoint

A `SecurityFilterChain` can enable SP metadata:

~~~java
@Bean
SecurityFilterChain samlFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/health").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults());
    return http.build();
}
~~~

Current Spring Security docs list the endpoints:

~~~text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
~~~

Send partners the SP metadata endpoint **actually served by the new configuration**, never a hand-edited XML that diverges from runtime. Behind a reverse proxy, ensure `entityID`/ACS are **public HTTPS URLs**, not `http://pod:8080`. Verify exported metadata contains **old/new public certs with the right `KeyDescriptor use`**; automatic metadata generation may not express key roles/algorithms exactly as operators expect, so inspect the generated XML and test IdP import.

### 11.5. IdP Metadata Refresh with Spring Security 7.x

Documentation for `OpenSaml5AssertingPartyMetadataRepository` describes expiry-aware refresh backed by an OpenSAML metadata resolver. For **metadata already trusted by the organization over HTTPS/provenance**:

~~~java
AssertingPartyMetadataRepository idpMetadata =
    OpenSaml5AssertingPartyMetadataRepository
        .fromTrustedMetadataLocation(
            "https://idp.example.test/metadata")
        .build();
~~~

When **XML metadata signature verification** is required, construct the repository with an independent trust credential:

~~~java
AssertingPartyMetadataRepository idpMetadata =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation(
            "https://idp.example.test/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataSignerCredential))
        .build();
~~~

Both snippets are **integration patterns from the Spring Security 7.x reference**; wire the repository to `RelyingPartyRegistrationRepository`/registration mapping/secret sourcing and match dependency versions. If writing a custom `MetadataResolver`, refresh/freshness/expiration may not behave like the default implementation; verify scheduler/cache and failure policies.

**Crucially:** `verificationCredentials` in this example **verifies the XML metadata signature**—it is not `assertingparty.verification.credentials` used to verify **SAMLResponse/Assertion** inside a `RelyingPartyRegistration`.

## 12. Operating Keys and Certificates on Kubernetes/VMs/HSMs

### 12.1. Key Generation and Distribution

Minimum requirements:

- Generate the **new private key** via CSPRNG inside an HSM/KMS or approved environment, meeting key-size, algorithm, and rotation policies.
- Keep separate private keys for **signing** and **decryption** where architecture permits; separate permissions to limit blast radius.
- Record the **internal key identifier**, owner, creation/activation/retire timestamps, certificate serial/fingerprint, and lifecycle status.
- Public certs may be published in metadata; private keys must live in a **protected Kubernetes Secret volume, vault, KMS/HSM, or OS keystore**.
- **Never commit private PEMs**, and never paste private keys into tickets, Slack, email, CI logs, or metrics.
- Enforce least privilege, file permissions, encrypted storage at rest, protected secret mount paths, and access auditing.
- Verify the **private key actually matches the certificate public key**; many "invalid signature" incidents come from pairing a key and cert from two different rotations.
- With HSM/PKCS#11, verify Spring's provider/decrypter supports non-extractable key operations properly; never assume every API accepts only extractable private keys.
- If a certificate is compromised, run **emergency revocation** separate from normal overlap; keeping a compromised key solely for availability is dangerous.

### 12.2. Kubernetes Rolling Deployment

~~~text
Release A:
  idpTrust = [IDP_OLD]
  spDecrypt = [SP_OLD]

Release B (pre-stage):
  idpTrust = [IDP_OLD, IDP_NEW]
  spDecrypt = [SP_OLD, SP_NEW]
  spActiveSigner = SP_SIGN_OLD

IdP/partner acknowledgment:
  all critical instances support new keys

Release C (activate):
  spActiveSigner = SP_SIGN_NEW
  still idpTrust = [IDP_OLD, IDP_NEW]
  still spDecrypt = [SP_OLD, SP_NEW]

Release D (retire):
  idpTrust = [IDP_NEW]
  spDecrypt = [SP_NEW]
~~~

If pods sharing an entityID hold **different trust rings**, login success depends on which pod the load balancer picks. A canary passing on one new pod **does not prove** old pods already support the new key.

Safeguards:

- Deploy pre-stage **to all pods/regions** before any issuer signs with the new key.
- Tie readiness probes to accessible key material/metadata freshness, not HTTP 200 alone.
- Updating a Secret volume mount atomically does not guarantee a running Java `RelyingPartyRegistration` **reloads keys automatically**. Many components load keys into beans once at startup; require a rolling restart, explicit repository reload, or tested dynamic resolver.
- If using Spring Session/Redis for AuthnRequest correlation, avoid dropping sessions during rollout; test SP-initiated SAML callbacks hitting two different pods.
- Do not delete old secret data while old private decryption is still needed for unprocessed messages.
- Verify key read permissions on non-root containers, volumes, file rotation, and filesystem ACLs.
- SP metadata endpoints may be cached by CDNs/proxies; check metadata content and fingerprints through the **real public path**.
- For multi-tenant apps, scope keyrings and private keys to each **registration/issuer/tenant**; never mix IdP A's cert into B's trust merely because they share a hostname.

### 12.3. Safe Rollback

A rollback after signer cutover requires:

1. Proving the **old private signer** remains uncompromised and safe to reactivate under approval.
2. Proving peers still trust the **old public signing key** within overlap.
3. Halting/preventing new signer activation if metadata is not ready; rolling back the signer when conditions hold.
4. Never rolling SP private decryption back to OLD-only once the IdP **has sent EncryptedAssertions for NEW**. When rolling back the app, **keep both OLD+NEW decrypt keys**.
5. Once the old key has been retired and deleted from metadata/trust, rolling back may require **a fresh staged rotation**, not simply flipping an environment variable.
6. Document rollback deadlines, owners, and clear "abort the change" criteria.

**Never perform a rollback by disabling signature validation, accepting any SAMLResponse, or trusting all certificates.**

## 13. OpenSSL: Verifying Public Certs, Fingerprints, and Key Matches

Run the commands below in an **authorized environment** with test/staging files or governed secrets. They do not create a trust chain; their purpose is confirming physical files match the plan.

### 13.1. Inspecting an X.509 Certificate

~~~bash
openssl x509 -in idp-sign-new.crt -noout -subject -issuer -serial -dates
openssl x509 -in idp-sign-new.crt -noout -fingerprint -sha256
openssl x509 -in sp-dec-new.crt -noout -fingerprint -sha256
~~~

The SHA-256 fingerprint is a tool to **confirm the exact artifact approved by the partner**; it does not prove the certificate belongs to the IdP if both fingerprint and file came over **the same untrusted channel**.

### 13.2. Comparing the Public Key of a Private Key and Certificate

~~~bash
# Public key DER extracted from private key; avoid printing the private key.
openssl pkey -in sp-dec-new.key -pubout -outform DER \
  | openssl dgst -sha256

# Public key DER extracted from certificate.
openssl x509 -in sp-dec-new.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
~~~

The two **SubjectPublicKeyInfo DER** SHA-256 digests must match if the private key and certificate form a pair. For non-extractable keys inside an HSM, use a **sign/verify challenge or HSM vendor tool**—never try exporting the private key to check.

### 13.3. Handling pem/der/pkcs12

- `PEM` is simply Base64/text armoring with `-----BEGIN ...-----`, which can hold a certificate, PKCS#8 private key, or other key types.
- `DER` is binary ASN.1, commonly used for certificates/keys.
- `PKCS#8` is a private key format, encrypted or unencrypted—not a keystore.
- `PKCS#12` is a container holding private keys/certificate chains, readable via Java `KeyStore.getInstance("PKCS12")`.
- `JKS` is an older Java keystore format; `PKCS#11` is an interface for tokens/HSMs, not a PEM file equivalent.
- `X.509 certificate` contains the public key and certificate metadata; it **never contains the private key**.

Example inspecting PKCS#12 **without printing private keys**:

~~~bash
keytool -list -v -storetype PKCS12 \
  -keystore sp-keys.p12
~~~

Never hardcode keystore passwords on the command line or in CI logs; use secure prompt/secret input facilities appropriate to the tool and environment. Avoid `openssl pkcs12 -nodes` on shared machines because it outputs private keys in plaintext.

### 13.4. Spring Configuration Notes

Spring Security `Saml2X509Credential.signing(...)` requires **private key + certificate**; `verification(...)` needs only **certificate/public key**; `decryption(...)` requires **private key + certificate**. Never pass a public verification cert to a signing credential expecting the SP to sign.

When copying PEMs from Vault/Kubernetes:

- Preserve exact PEM boundaries/newlines and encoding.
- Ensure the PKCS#8 private key format matches what the loader accepts.
- Verify key/cert pairing via SHA-256 SPKI fingerprint.
- Check secret mount paths and file permissions.
- Confirm an actual restart/reload occurred.
- Verify the right `SIGNING/DECRYPTION/VERIFICATION` role and runtime key selection order.

## 14. Standalone Java 17: Signing and Decrypting During Overlap

This program **compiles and runs on JDK 17+** without Spring, CAS, an IdP, or OpenSAML. It illustrates the two distinct rotation directions:

- **IdP signing:** the producer signs a simulated assertion string with an RSA private key; the SP holds a keyring of trusted public keys and rejects mismatched signatures, keys, issuers, or audiences.
- **SP decryption:** the sender encrypts an **AES content key** with the SP's public key using RSA-OAEP and encrypts the payload with AES-GCM; the SP holds both OLD+NEW private keys during overlap.
- Before publication, the new signer is untrusted. After publication/refresh, both OLD+NEW are accepted. After retiring old, only new is accepted.
- Before installing the new SP private key, ciphertexts for NEW cannot be decrypted. After pre-staging, both decrypt. After retiring old, old ciphertexts can no longer be decrypted.
- The cutover gate opens only once **all critical peers** reach the required metadata epoch.

**Do not confuse this with real XMLDSig/XML Encryption:** the code uses `SHA256withRSA` and a custom `Cipher` envelope strictly for **educational purposes**. Real SAML requires XML signature/encryption standards, key resolution, RSA-OAEP parameter compatibility, signed XML canonicalization, certificate trust, metadata signature verification, and Recipient/Destination/Audience/InResponseTo/replay validation. This demo **does not parse metadata**, **does not verify certificate chains or metadata XML signatures**, and does not prove any real SAMLResponse is valid. In the comments, `stageKeys` accepts a **simulated keyring approved out-of-band by a test admin**, never keys from browsers or unverified metadata. Never use this program to replace Spring Security's provider.

File **SamlMetadataRolloverDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SamlMetadataRolloverDemo {
    static final String ISSUER = "https://idp.example.test/saml";
    static final String SP = "https://portal.example.test/saml2/metadata/corp";
    static final SecureRandom RANDOM = new SecureRandom();

    record SignedAssertion(String issuer, String audience, String subject,
                           String keyId, byte[] signature) {}
    record EncryptedAssertion(String recipientKeyId, byte[] wrappedKey,
                              byte[] iv, byte[] ciphertext) {}

    static KeyPair rsa() throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048, RANDOM);
        return g.generateKeyPair();
    }

    static byte[] payload(String issuer, String audience, String subject) {
        return (issuer + "\u001f" + audience + "\u001f" + subject)
            .getBytes(StandardCharsets.UTF_8);
    }

    static SignedAssertion sign(String keyId, PrivateKey key,
            String issuer, String audience, String subject)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(key, RANDOM);
        s.update(payload(issuer, audience, subject));
        return new SignedAssertion(issuer, audience, subject,
            keyId, s.sign());
    }

    static boolean verify(SignedAssertion assertion,
            Map<String, PublicKey> trustedIdpKeys) {
        if (assertion == null || !ISSUER.equals(assertion.issuer())
                || !SP.equals(assertion.audience())) return false;
        PublicKey key = trustedIdpKeys.get(assertion.keyId());
        if (key == null) return false;
        try {
            Signature s = Signature.getInstance("SHA256withRSA");
            s.initVerify(key);
            s.update(payload(assertion.issuer(),
                assertion.audience(), assertion.subject()));
            return s.verify(assertion.signature());
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }

    static EncryptedAssertion encrypt(String keyId,
            PublicKey spEncryptionPublicKey, String text)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey secret = generator.generateKey();

        byte[] iv = new byte[12];
        RANDOM.nextBytes(iv);
        Cipher data = Cipher.getInstance("AES/GCM/NoPadding");
        data.init(Cipher.ENCRYPT_MODE, secret,
            new GCMParameterSpec(128, iv));
        data.updateAAD(keyId.getBytes(StandardCharsets.UTF_8));
        byte[] ciphertext = data.doFinal(
            text.getBytes(StandardCharsets.UTF_8));

        Cipher rsa = Cipher.getInstance(
            "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        rsa.init(Cipher.ENCRYPT_MODE, spEncryptionPublicKey);
        byte[] wrapped = rsa.doFinal(secret.getEncoded());
        return new EncryptedAssertion(keyId, wrapped, iv, ciphertext);
    }

    static String decrypt(EncryptedAssertion envelope,
            Map<String, PrivateKey> spPrivateKeys) {
        PrivateKey key = spPrivateKeys.get(envelope.recipientKeyId());
        if (key == null) return null;
        try {
            Cipher rsa = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
            rsa.init(Cipher.DECRYPT_MODE, key);
            byte[] rawAes = rsa.doFinal(envelope.wrappedKey());
            javax.crypto.spec.SecretKeySpec secret =
                new javax.crypto.spec.SecretKeySpec(rawAes, "AES");

            Cipher data = Cipher.getInstance("AES/GCM/NoPadding");
            data.init(Cipher.DECRYPT_MODE, secret,
                new GCMParameterSpec(128, envelope.iv()));
            data.updateAAD(envelope.recipientKeyId()
                .getBytes(StandardCharsets.UTF_8));
            return new String(data.doFinal(envelope.ciphertext()),
                StandardCharsets.UTF_8);
        } catch (GeneralSecurityException ex) {
            // Production must log a redacted reason, not plaintext/key data.
            return null;
        }
    }

    static void stageKeys(Map<String, PublicKey> trust,
            Map<String, PublicKey> independentlyVerifiedMetadata) {
        // Caller must verify the metadata transport/signature OUTSIDE here.
        // In this lab the input is a trusted test-admin approved map.
        trust.clear();
        trust.putAll(independentlyVerifiedMetadata);
    }

    static void check(String name, boolean ok) {
        System.out.println(name + "=" + ok);
        if (!ok) throw new AssertionError(name);
    }

    public static void main(String[] args) throws Exception {
        KeyPair idpOld = rsa(), idpNew = rsa(), attacker = rsa();
        KeyPair spOld = rsa(), spNew = rsa();

        Map<String, PublicKey> idpTrust = new HashMap<>();
        stageKeys(idpTrust, Map.of("idp-2025", idpOld.getPublic()));
        SignedAssertion oldMessage = sign("idp-2025",
            idpOld.getPrivate(), ISSUER, SP, "alice");
        SignedAssertion newMessage = sign("idp-2026",
            idpNew.getPrivate(), ISSUER, SP, "alice");

        check("oldSignatureAcceptedInitially",
            verify(oldMessage, idpTrust));
        check("newSignatureRejectedBeforeMetadata",
            !verify(newMessage, idpTrust));

        // Publish both trusted signing keys, then wait for all SPs to load.
        stageKeys(idpTrust, Map.of(
            "idp-2025", idpOld.getPublic(),
            "idp-2026", idpNew.getPublic()));
        check("bothSigningKeysPublished", idpTrust.size() == 2);
        check("oldSignatureAcceptedDuringOverlap",
            verify(oldMessage, idpTrust));
        check("newSignatureAcceptedDuringOverlap",
            verify(newMessage, idpTrust));
        check("tamperedSubjectRejected", !verify(
            new SignedAssertion(ISSUER, SP, "mallory",
                newMessage.keyId(), newMessage.signature()), idpTrust));
        check("wrongIssuerRejected", !verify(
            sign("idp-2026", idpNew.getPrivate(),
                "https://fake-idp.example.test", SP, "alice"), idpTrust));
        check("wrongAudienceRejected", !verify(
            sign("idp-2026", idpNew.getPrivate(), ISSUER,
                "https://other-sp.example.test", "alice"), idpTrust));
        check("unapprovedKeyRejected", !verify(
            sign("unapproved", attacker.getPrivate(),
                ISSUER, SP, "alice"), idpTrust));
        check("wrongKeyForTrustedIdRejected", !verify(
            sign("idp-2026", attacker.getPrivate(),
                ISSUER, SP, "alice"), idpTrust));

        // Switch active IdP signer only after consumers acknowledge refresh.
        SignedAssertion afterSwitch = sign("idp-2026",
            idpNew.getPrivate(), ISSUER, SP, "bob");
        check("newSignerAcceptedAfterSwitch",
            verify(afterSwitch, idpTrust));
        check("inFlightOldStillAccepted",
            verify(oldMessage, idpTrust));

        // After cache TTL + in-flight time + confirmed partner cutover.
        stageKeys(idpTrust, Map.of(
            "idp-2026", idpNew.getPublic()));
        check("retiredOldSignerRejected",
            !verify(oldMessage, idpTrust));
        check("newSignerRemainsAccepted",
            verify(afterSwitch, idpTrust));

        // Independent SP encryption-key rotation: receiver retains old key.
        Map<String, PrivateKey> spDecrypt = new HashMap<>();
        spDecrypt.put("sp-dec-2025", spOld.getPrivate());
        EncryptedAssertion encryptedOld = encrypt("sp-dec-2025",
            spOld.getPublic(), "saml-assertion-for-alice");
        EncryptedAssertion encryptedNew = encrypt("sp-dec-2026",
            spNew.getPublic(), "saml-assertion-for-bob");
        check("oldCiphertextDecryptsInitially",
            "saml-assertion-for-alice".equals(
                decrypt(encryptedOld, spDecrypt)));
        check("newCiphertextFailsBeforeNewPrivateKeyInstalled",
            decrypt(encryptedNew, spDecrypt) == null);

        // Install new private key BEFORE telling senders to encrypt to it.
        spDecrypt.put("sp-dec-2026", spNew.getPrivate());
        check("oldCiphertextDecryptsDuringOverlap",
            "saml-assertion-for-alice".equals(
                decrypt(encryptedOld, spDecrypt)));
        check("newCiphertextDecryptsDuringOverlap",
            "saml-assertion-for-bob".equals(
                decrypt(encryptedNew, spDecrypt)));

        byte[] tampered = encryptedNew.ciphertext().clone();
        tampered[0] ^= 1;
        EncryptedAssertion forged = new EncryptedAssertion(
            encryptedNew.recipientKeyId(), encryptedNew.wrappedKey(),
            encryptedNew.iv(), tampered);
        check("tamperedGcmCiphertextRejected",
            decrypt(forged, spDecrypt) == null);

        check("oldAndNewPrivateKeysPresent",
            spDecrypt.size() == 2);
        // Retire old only after all old-encrypted in-flight messages expire.
        spDecrypt.remove("sp-dec-2025");
        check("retiredOldCiphertextUnavailable",
            decrypt(encryptedOld, spDecrypt) == null);
        check("newCiphertextDecryptsAfterRetirement",
            "saml-assertion-for-bob".equals(
                decrypt(encryptedNew, spDecrypt)));

        // Operational gate: metadata propagation is a prerequisite.
        Map<String, Integer> partnerMetadataEpoch = Map.of(
            "sp-a", 7, "sp-b", 6, "sp-c", 7);
        int requiredEpoch = 7;
        check("stalePartnerPreventsUncoordinatedSigningCutover",
            partnerMetadataEpoch.values().stream()
                .anyMatch(epoch -> epoch < requiredEpoch));
        Map<String, Integer> refreshed = Map.of(
            "sp-a", 7, "sp-b", 7, "sp-c", 7);
        check("confirmedPartnersAllowCutover",
            refreshed.values().stream()
                .allMatch(epoch -> epoch >= requiredEpoch));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SamlMetadataRolloverDemo.java
java SamlMetadataRolloverDemo
~~~

**Verified stdout compiled/run on JDK 17:**

~~~text
oldSignatureAcceptedInitially=true
newSignatureRejectedBeforeMetadata=true
bothSigningKeysPublished=true
oldSignatureAcceptedDuringOverlap=true
newSignatureAcceptedDuringOverlap=true
tamperedSubjectRejected=true
wrongIssuerRejected=true
wrongAudienceRejected=true
unapprovedKeyRejected=true
wrongKeyForTrustedIdRejected=true
newSignerAcceptedAfterSwitch=true
inFlightOldStillAccepted=true
retiredOldSignerRejected=true
newSignerRemainsAccepted=true
oldCiphertextDecryptsInitially=true
newCiphertextFailsBeforeNewPrivateKeyInstalled=true
oldCiphertextDecryptsDuringOverlap=true
newCiphertextDecryptsDuringOverlap=true
tamperedGcmCiphertextRejected=true
oldAndNewPrivateKeysPresent=true
retiredOldCiphertextUnavailable=true
newCiphertextDecryptsAfterRetirement=true
stalePartnerPreventsUncoordinatedSigningCutover=true
confirmedPartnersAllowCutover=true
~~~

### 14.1. Analyzing the Result Groups

- **Before publication:** old verification key is valid; new signer is untrusted → **rejected**. That is right, not a bug.
- **Overlap publication:** once the trust ring is **verified out-of-band**, the SP accepts both old/new signers, while forged/tampered signatures or wrong issuers/audiences remain rejected.
- **Activate:** producer uses the new private key, new messages verify, and old signed messages still verify under overlap policy.
- **Retirement:** old signing key is removed from the trust ring → old signatures are no longer accepted while new continues passing.
- **Decrypt preparation:** new ciphertexts cannot decrypt before the SP installs the new private key; once both are installed, both old/new ciphertexts decrypt.
- **Decrypt retirement:** old private key removed → old ciphertexts fail decryption. This is safe only after **old in-flight messages have been processed or expired**.
- **Operational gate:** one partner still on an old metadata epoch means **shared signer cutover is not yet permitted** if that partner is critical; once all reach the new epoch, the change gate opens.

**This demo does not replace signed SAML metadata, XMLDSig, XML Encryption, HSM integration, or issuer/conditions protocol checks.** Use it only to visualize overlap invariants; production validation must run Spring/OpenSAML with real IdP fixtures.

## 15. Pre-Cutover Integration Testing

### 15.1. Four Testing Dimensions

| State | IdP signs with OLD | IdP signs with NEW | IdP encrypts to OLD SP pub | IdP encrypts to NEW SP pub |
| --- | --- | --- | --- | --- |
| Current SP, OLD only | PASS | FAIL before staged trust | PASS | FAIL before new private |
| SP pre-staged trust/decrypt for both | PASS | PASS | PASS | PASS |
| SP after signer switch, before retiring trust/decrypt | PASS | PASS | PASS | PASS |
| SP after retiring OLD | FAIL per new policy | PASS | FAIL once old private removed | PASS |

**Never test signing and encryption in a suite that skips message signatures**: signing with the IdP key and decrypting with the SP key are **two separate cryptographic operations**. When testing encrypted assertions, verify signature/issuer/audience/recipient/time after decryption and preserve proper XML processing order.

### 15.2. Minimum Test Cases

| Case | Condition | Expected outcome |
| --- | --- | --- |
| S01 | Valid IdP OLD signature before publication | PASS |
| S02 | Valid IdP NEW signature before SP refresh | FAIL |
| S03 | Metadata contains OLD+NEW, verified | SP trusts both |
| S04 | Old signature during overlap | PASS |
| S05 | New signature during overlap | PASS |
| S06 | Signed XML assertion modified without re-signing | FAIL |
| S07 | Forged metadata with attacker's signing key, invalid metadata signature | Metadata **REJECTED** |
| S08 | Unsigned metadata when policy requires signed | Metadata **REJECTED** |
| S09 | New metadata signature yet unapproved anchor | Metadata **REJECTED** |
| S10 | IdP B's signing key used for IdP A | FAIL issuer/trust |
| S11 | Right key yet wrong Audience/Recipient/Destination/InResponseTo | FAIL |
| S12 | Same X.509 cert yet unapproved changed entityID | FAIL |
| S13 | IdP NEW active, old SP replica unrefreshed | FAIL on old replica → cutover blocked |
| S14 | SP OLD active signing, IdP does not trust NEW yet | PASS with OLD |
| S15 | SP signs NEW before IdP imports NEW | FAIL → cutover blocked |
| S16 | SP signs NEW while IdP trusts OLD+NEW | PASS |
| E01 | IdP encrypts for SP OLD; SP OLD private installed | PASS |
| E02 | IdP encrypts for SP NEW before private key installation | FAIL |
| E03 | SP holds OLD+NEW decrypt keys, IdP encrypts OLD | PASS |
| E04 | SP holds OLD+NEW decrypt keys, IdP encrypts NEW | PASS |
| E05 | SP drops OLD private while old message still in flight | FAIL → unsafe retirement |
| E06 | Ciphertext integrity/auth tag failure | Decryption FAILS |
| E07 | IdP picks different encryption key than metadata expects | Detect + coordinate, no silent fallback |
| M01 | Metadata expired/failed refresh | Fail closed or last-known-good per approved bounded policy |
| M02 | Metadata XML signature fails against wrong trust anchor | Metadata **REJECTED** |
| M03 | Metadata key rollover with old/new anchor overlap | Accept valid signed metadata per pinned anchors |
| M04 | Metadata changes endpoint/entityID outside approved change | Detect drift, require approval |
| D01 | Multi-pod rollout: every pod has OLD+NEW decrypt | PASS all pods |
| D02 | One pod missing NEW private | FAIL on that pod → pre-stage incomplete |
| D03 | Browser AuthnRequest pre-cutover, response post-cutover | PASS when trust/session intact |
| D04 | Multiple tenants with IdP keys sharing alias name | No cross-trust |
| D05 | Rollback active signer to OLD during overlap | PASS if peer still verifies OLD |
| D06 | Rollback decrypt to OLD-only after IdP encrypted NEW | FAIL → unsafe rollback |
| D07 | Retire OLD signer after validity/rollback window | Old signature FAILS; new PASSES |
| D08 | Emergency revocation (private key compromised) | Apply incident response; never keep compromised key just for overlap |

### 15.3. Testing with Real Spring Security

In a controlled test environment:

1. Generate OLD and NEW **IdP test keys**, place public certs into trusted metadata, and **sign metadata with an independent metadata signer** when policy requires.
2. Generate OLD and NEW **SP signing/decryption keys**; supply private keys to the test runtime.
3. Enable `saml2Login` and `saml2Metadata`, exposing SP metadata via the proper public endpoint.
4. Trigger a real AuthnRequest via `/saml2/authenticate/{registrationId}` and retain the request in the matching browser/session.
5. Use a **test IdP/OpenSAML helper** to build and sign SAMLResponses with OLD/NEW IdP private keys, encrypted for OLD/NEW SP public certs as needed.
6. Submit fixtures through the **actual Spring ACS filter**; never inject a fake `Authentication` via test post-processors when the goal is testing XMLDSig/decryption.
7. Assert both **cryptographic outcomes** and policy guards: issuer, audience, recipient, destination, InResponseTo, conditions, replay, and local authority mapping.
8. For negative tests, do not mistake a leftover session Authentication for callback success; assert **no new principal/role assignment occurred**.
9. Test a browser whose AuthnRequest started pre-cutover and whose SAMLResponse returns post-cutover.
10. Test callbacks hitting every pod/node and the token/session store when using a distributed request repository.
11. Exercise metadata refresh across cache/federation/CDN layers in staging rather than relying on restarting a single pod.
12. After retirement, verify old-only signatures are rejected and old encrypted payloads are no longer accepted as valid traffic.

**Important:** swapping a certificate inside XML after signing creates a **false signature failure** rather than proving key-ring rotation works. To test old/new signing credentials, generate **validly signed fixtures** with the respective private keys before sending them to Spring's ACS.

## 16. Observing Rollout Progress and Diagnostics

### 16.1. Valuable Logs/Metrics

Log at a level **containing no raw SAMLResponse, private keys, assertions, or session IDs**:

~~~text
event=SAML_METADATA_REFRESH
registrationId=corp
expectedIssuer=https://idp.example.test/saml
metadataSource=approved-idp-endpoint
metadataVersion=rollover-7
signatureValidated=true
trustedSigningKeyCount=2
metadataFresh=true
traceId=trace-7a12
~~~

~~~text
event=SAML_SIGNING_KEY_ROLLOVER
registrationId=corp
phase=ACTIVATE
activeSignerFingerprint=sha256:...
acceptedVerificationKeys=2
partnersAcknowledged=3
partnersRequired=3
traceId=trace-7b34
~~~

~~~text
event=SAML_DECRYPT_FAILURE
registrationId=corp
reason=NO_MATCHING_PRIVATE_KEY
credentialVersion=rollover-7
metadataVersion=rollover-7
node=auth-pod-3
traceId=trace-7c56
~~~

Hash/fingerprint values here are **illustrative log examples**, not real fingerprints. For sensitive partners, log a short **approved key alias** instead of raw issuer URLs; avoid PII. Never log raw `ds:KeyInfo` if it contains sensitive data beyond the public cert.

Useful metrics:

- `saml_metadata_refresh_success_total`, `saml_metadata_refresh_failure_total`.
- `saml_metadata_age_seconds`, `saml_metadata_remaining_validity_seconds`.
- `saml_trusted_signing_keys_count` per registration.
- `saml_response_signature_reject_total` by safe reason category.
- `saml_decrypt_failure_total` per registration/node.
- `saml_authn_success_total` and `saml_authn_failure_total` per IdP/registration.
- `saml_active_signing_key_generation` or deployment epoch.
- `saml_partner_ack_remaining` on the change dashboard.
- `saml_rollover_phase` (P0–P5) and rollback readiness flag.
- `saml_assertion_replay_reject_total`: monitor independently—never drop replay validation during key rotation.
- `saml_cert_expiry_days` strictly for certificate-file observability; never equate it with metadata trust/freshness.

**Never use full Base64 certificates, private keys, NameIDs, tickets, SAMLResponses, or session cookies as metric labels or log fields.**

### 16.2. Common Root Causes

| Symptom | Likely cause | Check and fix |
| --- | --- | --- |
| NEW signatures rejected, OLD still passes | IdP switched before SP loaded new cert | Refresh trusted metadata; block cutover |
| Signature rejections on only some pods | Rolling deploy left verification rings out of sync | Check each pod/repository and restart/reload |
| IdP metadata fetch OK yet XML metadata unverified | Metadata repository lacks `verificationCredentials` | Configure independent anchor; check signature policy |
| New metadata signer rejected | Metadata trust anchor M_NEW not pre-staged | Out-of-band metadata signer rotation |
| Certificate right yet wrong issuer | EntityID/tenant/registration drift | Fix issuer/registration mapping |
| Cert NotAfter passed yet login still passes | SAML direct metadata key trust differs from browser PKIX | Review org policy; do not assume runtime is safe |
| Signed SAMLResponse right cert yet fails | Audience/Recipient/Destination/InResponseTo/time/replay | Never disable security validators |
| EncryptedAssertion fails after publishing SP metadata | IdP picked new pub while one SP pod lacks new private | Pre-stage decryption key on all replicas |
| EncryptedAssertion fails after removing OLD | IdP still sending old encrypted messages | Restore old decrypt within approved overlap if uncompromised |
| SP metadata endpoint shows old only | Metadata resolver/cache missed config | Fetch public endpoint, compare fingerprints |
| IdP does not auto-refresh metadata | Vendor requires manual import/restart | Confirm per vendor + evidence |
| IdP client picks OLD despite NEW published | Sender encryption selection differs from expectation | Vendor behavior, explicit coordination |
| Login fails only behind load balancer | Public/internal ACS mismatch, forwarded headers | Fix trusted proxy public URL |
| Key in PEM does not match cert | Wrong secret alias mounted / versions mixed | Compare SPKI pubkey digests |
| Metadata refresh loses source | Network/DNS/TLS/expired cache | Last-known-good within approved bounded policy; alert |
| JWKS rotated while issue is SAML | Confusing protocols/endpoints | Separate SAML XML metadata from OIDC JWKS |
| Forged metadata accepted | Missing bootstrap provenance/signature trust | Incident; restore approved trust anchors |
| Rollback after retirement fails old signatures | Consumers already removed old | Do not roll back in one step; run staged trust update |
| TLS cert rotation breaks metadata fetch | HTTPS trust chain/hostname failure | Fix TLS trust; never import untrusted XML |
| KMS/HSM key non-exportable | Code assumed PEM PrivateKey file | Use provider/PKCS#11 integration and tests |
| Runtime secret volume changed yet behavior stays old | Beans cached credentials | Restart/reload repository per explicit plan |
| Metadata lists multiple KeyDescriptors yet a consumer rejects | Partner lacks multi-key role support | Agree on vendor-specific migration |

## 17. Cross-Team Runbook

### 17.1. Information Each Side Must Deliver

**IdP side sends to SP:**

- IdP entityID and SSO/SLO endpoints (**unchanged** if rotating certs only).
- Signed/verified metadata XML location or signed file.
- Old/new signing public cert **SHA-256 fingerprints** confirmed out-of-band.
- Metadata signer trust anchor version and TTL/`validUntil`.
- Planned time IdP switches active signing key.
- How to canary/test the new signing cert; rollback contact.
- Confirmation that the old signing key stays active during overlap and retirement deadline.

**SP side sends to IdP:**

- SP entityID/registrationId and public ACS/SLO URLs.
- Old/new SP signing public certs and active switch date (if SP rotates signer).
- Old/new SP encryption public certs plus SP capability to decrypt with both old+new.
- Metadata endpoint/signed metadata checksum/version and refresh/import instructions.
- How the IdP selects encryption keys and whether multi-key metadata is supported.
- Acknowledgement that SP pods have staged the private key/verification ring.
- Rollback policy, stop conditions, and monitoring.

### 17.2. Approval and Handshake Flow

~~~text
Change owner -> open key rotation change request
Security     -> approve key sizes, algorithms, metadata signer provenance
Key owner    -> generate new key, protect private material
Metadata pub -> publish OLD + NEW through signed/trusted channel
Peer operator-> refresh/import; verify expected entityID + fingerprints
Peer operator-> confirm "ACCEPTS NEW, STILL ACCEPTS OLD"
Change owner -> check ALL critical peers acknowledged
Change owner -> authorize cutover active signer / encryption sender
On-call      -> run canary + synthetic SAML flow tests
On-call      -> observe errors and session/user login outcomes
Change owner -> mark stable after overlap and rollback window
Key owner    -> remove OLD from metadata/runtime safely
Security     -> verify retirement and audit close-out
~~~

If a peer does not respond, never assume "metadata is published so the peer must know." Critical vs noncritical partners may be tiered per SLA, yet dropping a partner must be an **approved risk/business decision**, never an implicit timeout.

## 18. Emergency Rotation Differs from Planned Rotation

**Planned rotation** assumes the OLD private key remains safe; keep OLD during overlap to prevent downtime.

**Emergency rotation** occurs when:

- Private signing key is exposed, risking attacker-signed forged SAMLResponses.
- SP decrypt private key is stolen, risking disclosure of encrypted assertions.
- Metadata signer key is compromised, letting an attacker distribute forged metadata.
- Secret store/HSM is breached or key custody can no longer be trusted.

In that event:

1. Trigger incident response and **stop trusting/revoke the compromised key per severity**, even if it causes an outage.
2. Never keep a compromised key trusted until cache TTL expires just to preserve availability.
3. Distribute new keys over an **independently authenticated emergency channel**.
4. Rapidly replace metadata signing anchors, IdP verification certs/SP encryption keys, and revoke sessions/tokens if the threat model demands it.
5. Audit logs for forged assertions, metadata substitution, data exposure, and logins under wrong identities.
6. For a compromised decryption key, assess **past ciphertext exposure**; rotating to a new key does not make previously encrypted data confidential again.
7. Choose a recovery/rollback strategy **that never reintroduces the compromised key**.
8. Document change exceptions and post-incident corrective actions.

**Overlap is solely an availability strategy while the OLD key remains trustworthy.** It is never a safety rule for delaying compromise response.

## 19. Operational Comparison: SAML, OIDC JWKS, and TLS

| System | Metadata producer | Public key set | Token/message | What must not be confused |
| --- | --- | --- | --- | --- |
| **SAML IdP** | `EntityDescriptor/IDPSSODescriptor` | `KeyDescriptor use="signing"` | XMLDSig on Response/Assertion | Never trust a cert merely from untrusted `KeyInfo` |
| **SAML SP** | `SPSSODescriptor` | Signing/encryption KeyDescriptors | Signed AuthnRequest, EncryptedAssertion recipient | Never send private SP keys to IdP |
| **SAML metadata signer** | Federation/operator | Independent metadata verification anchor | Signed metadata XML | Distinct from IdP assertion signing key |
| **OIDC Provider** | OpenID configuration + JWKS | Issuer's JWKs/`kid` | JWT ID Token/access token per profile | Never equate SAML EntityID with OIDC issuer casually |
| **HTTPS server** | TLS certificate chain | TLS client trust anchors | HTTP/TLS connection | HTTPS trust does not mean XML metadata signature validation |
| **CAS Server** | Registered service/ticket infrastructure | Service-specific trust mechanisms | Single-use Service Ticket | ST is not signed SAML/JWT; does not use SAML KeyDescriptor |

In OIDC JWKS rollover, the usual pattern is **publish new JWK/kid first, switch signer, retain old JWK until all issued JWTs expire + cache TTL**, then retire. Yet JWKS signature verification and SAML XMLDSig have distinct token formats, libraries, and attack surfaces, so test them separately.

## 20. FAQ / Self-Check

**1. When the IdP rotates its signing key, which side generates the new private key?**

**The IdP.** The SP needs only the IdP's **public signing certificate** obtained from trusted metadata/configuration.

**2. Can the SP automatically accept a new IdP signing certificate from SAMLResponse/`KeyInfo`?**

No. `KeyInfo` may suggest a candidate, yet the verification public key must be **trusted from provenance-verified metadata/config**, never trusted solely because a message carried it.

**3. Why must the NEW public signing key be published before using the NEW private key?**

Because consumers/SPs must load the trust ring containing NEW first; otherwise, new signatures are rejected.

**4. Must the SP sign an AuthnRequest with both private signing keys?**

Not in standard workflows. The SP picks one active signer; **the IdP verifies both OLD and NEW** during overlap. Multi-signature behavior depends on specific protocol/product support.

**5. Why must SP decryption key rotation install private NEW before publishing public NEW in metadata?**

Because the IdP may start encrypting with NEW right after refreshing metadata; the SP must be able to decrypt it.

**6. Once the IdP switches encryption to NEW, can private OLD be deleted immediately?**

Not if old-encrypted messages remain in flight or within the rollback window. Retain OLD per plan until safe retirement.

**7. Does listing both OLD+NEW KeyDescriptors in metadata force the IdP to choose NEW?**

No. Algorithm/key selection can vary by implementation/vendor; coordinate and test.

**8. Do the metadata XML signature and SAMLResponse XML signature share the same trust anchor?**

Not by default. Metadata trust must be bootstrapped independently; IdP assertion verification keys come from trusted IdP metadata after it is accepted.

**9. Does `fromTrustedMetadataLocation` automatically verify XML metadata signatures?**

Do not assume so. Spring Security 7.x docs state **metadata signature validation runs when verification credentials are supplied** to the repository; without them, the component does not validate metadata signatures. Trusting an approved source/TLS is a separate model.

**10. Why doesn't metadata refresh success prove runtime is using the new key?**

Because Spring beans/caches/repositories/replicas may not have reloaded or updated the active `RelyingPartyRegistration`. Test signature verification on every pod/registration.

**11. Is a SAML certificate past NotAfter guaranteed to be rejected by the framework?**

Cannot be stated universally. Under direct metadata key trust, X.509 may act purely as a public-key carrier; verify framework, IdP, and organizational policies instead of assuming browser TLS PKIX rules.

**12. If the new signer works yet the app reports Audience mismatch, did key rollover fail?**

Not necessarily. The signature passed, while **SAML semantic validation** hit another issue. Keep issuer/audience/recipient/InResponseTo checks intact—never disable them to "fix certs."

**13. Can rollback after the SP received NEW-encrypted assertions simply restore the OLD deployment?**

Unsafe if rollback drops private NEW. During overlap, rollback must still decrypt **OLD+NEW**.

**14. How long before retiring OLD?**

Once partners acknowledge refresh and metadata cache/propagation/in-flight/clock skew and rollback windows have been verified—never pick an arbitrary fixed day count.

**15. What if a partner supports only a single certificate?**

You cannot assume key overlap works automatically. Execute a vendor-specific migration/maintenance plan or coordinate cutover/trust per actual support.

**16. Should a certificate fingerprint fetched from the IdP URL serve as proof of identity?**

Not if both fingerprint and certificate come from the same potentially compromised channel. Require **out-of-band confirmation** or a metadata signature verified by a pre-existing trust anchor.

**17. Can a compromised old key be kept in trust to avoid downtime?**

Never under normal overlap rules. Upon compromise, prioritize incident response and block forged identities.

**18. Why must tests cover both OLD and NEW?**

To confirm **true overlap**, rather than a producer switching to NEW just as consumers dropped OLD or before they loaded NEW.

## 21. Standard Implementation Checklist

- [ ] Inventoried SP/IdP entityIDs, registrations, owners, and both metadata directions.
- [ ] Identified each key's purpose: assertion signing, AuthnRequest signing, SP decryption, metadata signing, or TLS.
- [ ] Opened a planned maintenance/change record with security/operations approvals and partner contacts.
- [ ] Generated NEW private key via CSPRNG/HSM/KMS and scoped its protection; private keys never appear in metadata.
- [ ] Confirmed NEW public certificate/fingerprint via an independent channel.
- [ ] Fetched/imported metadata under a verified trust model; when policy requires signed metadata, verified metadata signature.
- [ ] Independently bootstrapped any new metadata-signer trust anchor if metadata signing also rotates.
- [ ] Confirmed metadata `entityID`, SSO/ACS/SLO URLs, bindings, and tenant scope do not change unintentionally.
- [ ] Verified metadata `KeyDescriptor use`, certificate serials, and fingerprints for both OLD and NEW.
- [ ] Documented metadata `validUntil`/`cacheDuration`/HTTP caches/federation aggregators and partner refresh SLAs.
- [ ] Confirmed all critical consumers loaded OLD+NEW verification keys before active signer switch.
- [ ] Confirmed all SP nodes installed OLD+NEW private decryption keys before allowing IdP to encrypt with NEW.
- [ ] Verified IdP key selection with multi-key encryption metadata and canaried sender behavior.
- [ ] Explicitly selected active outbound SP signing credential; IdP trusts OLD+NEW signing public keys during overlap.
- [ ] Verified private key/certificate pairs via SPKI public digest, role, permissions, and secret mounts.
- [ ] Confirmed Spring Security `RelyingPartyRegistration` loads the exact credentials per registration.
- [ ] Confirmed Spring metadata repository refresh/expiry behavior; supplied independent `verificationCredentials` for signed metadata.
- [ ] Verified **live** runtime across all nodes, not merely staging or a single canary pod.
- [ ] Preserved SAML signature, decryption, issuer, audience, recipient, destination, InResponseTo, time, and replay checks.
- [ ] Passed OLD/NEW signed+encrypted response fixtures during overlap; tampered/untrusted credentials fail.
- [ ] Never used test post-processors to fake `Authentication` and claim crypto validation passed.
- [ ] Preserved AuthnRequest correlation across browser SSO flows hitting multiple nodes/regions.
- [ ] Sized overlap window >= cache/propagation/in-flight/clock skew/rollback budget per policy.
- [ ] Configured metrics for metadata refresh, key activation, unknown signers, decrypt failures, and login failures per registration.
- [ ] Ensured logs exclude private keys, SAMLResponses/Assertions/NameIDs/session cookies, or raw secrets.
- [ ] Ensured rollbacks retain both old/new decrypt keys and never reintroduce compromised private keys.
- [ ] Retired OLD only after partner confirmation, end of in-flight/rollback windows, and zero remaining valid OLD traffic.
- [ ] Confirmed post-retirement that OLD-only signed messages fail, new messages pass, and old ciphertexts are no longer needed.
- [ ] Maintained emergency compromise response separate from planned rollover, with revocation/notification runbooks.
- [ ] Updated only business/status deployment fields per change approval; never mixed key rotation with out-of-scope entityID/ACS migrations.
- [ ] Completed post-change report: fingerprints, epochs, owner sign-offs, tests, timings, and rollback outcomes.

## 22. Official Documentation and Further Reading

- Spring Security, **SAML 2.0 Metadata**: parsing/publication, metadata repositories, expiry-aware refresh, metadata signature verification, and `/saml2/metadata` endpoint: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **SAML 2.0 Login Overview**: `RelyingPartyRegistration`, verification/signing/decryption credentials, and Web Browser SSO: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**: `OpenSaml5AuthenticationProvider`, signature/decryption/issuer/conditions validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**: SP signing private keys, algorithms, and request signing: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot, **SAML 2.0 Relying Party auto-configuration**: `signing.credentials`, `decryption.credentials`, and `assertingparty.verification.credentials`: https://docs.spring.io/spring-boot/reference/security/saml2.html
- OASIS, **SAML V2.0 Metadata Interoperability Profile**: trusted metadata, key rollover, metadata keys as public-key carriers, metadata validity/caching: https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.html
- OASIS, **SAML 2.0 Metadata specification**: `EntityDescriptor`, `KeyDescriptor`, `validUntil`, and metadata signatures: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS, **SAML 2.0 Core**: signatures/subjects/conditions, encrypted assertions, issuer/audience/time: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Shibboleth historical note, **IdPKeyRollover**: publish new signing key in metadata, wait propagation, then switch signer and retire old key (documentation for EOL Shibboleth 2; underlying principles remain useful): https://shibboleth.atlassian.net/wiki/spaces/SHIB2/pages/2577072227/IdPKeyRollover
- OWASP, **Cryptographic Storage Cheat Sheet**: key lifecycle, least privilege, and secure cryptographic storage: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP, **SAML Security Cheat Sheet**: signature verification, trusted metadata, audience, recipient, InResponseTo, and replay controls: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- Kubernetes, **Secrets**: volume/config updates and access control: https://kubernetes.io/docs/concepts/configuration/secret/

**Conclusion:** To rotate SAML 2.0 keys **without downtime**, know which side **signs**, which **verifies**, which **encrypts**, which **decrypts**, and **how the metadata source is trusted**. For signing, **publish public NEW → consumers trust OLD+NEW → activate private NEW → retire OLD**. For SP decryption, **install private NEW while keeping OLD → publish public encryption NEW → IdP switches encryption to NEW → retain decrypt OLD+NEW → retire OLD**. The overlap window must span **cache refreshes, partners, in-flight messages, multiple pods, and rollback**; metadata-signer trust is an independent boundary. Never disable signature/metadata/replay validation to get past a rotation error, and never keep a compromised key merely to maintain availability.