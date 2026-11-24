# Testing Metadata Refresh, Key Rotation, and Multiple Registrations

> **Topic:** Spring Security – federation. **Knowledge track:** SAML2 Testing. This Knowledge article walks through testing the full configuration lifecycle of a SAML 2.0 **Relying Party (RP / Service Provider – SP)** when an Identity Provider (IdP / Asserting Party – AP) **refreshes metadata**, **rotates certificates/keys**, and the Spring Security application operates **multiple `RelyingPartyRegistration` entries**. The focus is ensuring **uninterrupted authentication during valid rollovers** while always **failing closed** on forged metadata, untrusted keys, mismatched issuers/registrations, assertions with wrong audience/recipient, and unapproved changes. Primary scope: Java 17+, Spring Boot 3.x / Spring Security 6.4–6.5, and OpenSAML 5-based repository approaches on supported releases; all version differences are explicitly noted.

## 1. Learning Objectives and Outcomes to Verify

After this lesson, you will be able to:

1. Explain the roles of `IdP metadata`, `SP metadata`, `RelyingPartyRegistration`, `registrationId`, `EntityID`, `ACS`, `SSO/SLO endpoints`, and `KeyDescriptor`.
2. Distinguish **loading metadata once at startup**, **reloading upon cache expiration**, and **metadata resolvers refreshing per `cacheDuration`/`validUntil`**. Never assume configuring a metadata URL automatically enables hot reload.
3. Design tests for metadata signatures/trust anchors, TLS/PKIX, temporal validity, XML size limits, redirects/SSRF, issuer/`entityID`, cache versions, and network-failure fallbacks.
4. Distinguish the **IdP signing certificate** used by the SP to verify Response/Assertion signatures, the **SP signing certificate** used to sign `AuthnRequest`/`LogoutRequest`, the **SP decryption key** used to decrypt Assertions, the **metadata-signing certificate** verifying metadata XML, and the **HTTPS certificate** protecting metadata transport.
5. Test an IdP rollover featuring **simultaneous old + new verification keys** during overlap, followed by timely removal of the old key; verify updated state actually takes effect across all pods.
6. Test rotating **SP signing/decryption credentials** without assuming an IdP key change implies an SP key change; confirm the IdP received updated SP metadata before switching keys.
7. Configure **two or more `RelyingPartyRegistration` entries** and test end-to-end isolation across `registrationId → IdP EntityID → SP EntityID → ACS → signing/decryption credentials → tenant authorization`.
8. Design **meaningful negative tests**: validly signed fixtures with wrong issuer/audience/recipient; forged/expired metadata; unpublished new keys; metadata rollback; cross-tenant assertions; ambiguous IdP-initiated SSO.
9. Use Spring Security SAML2 `SecurityFilterChain`, `saml2Metadata`, and a controlled reloading repository; understand the limits of `InMemoryRelyingPartyRegistrationRepository` and `CachingRelyingPartyRegistrationRepository`.
10. Write and run a **standalone Java 17** example modeling policy gates for refresh, key overlap, monotonic versions, and registration isolation with deterministic stdout. The example does not replace XML Signature verification.
11. Establish pre/post-cutover verification runbooks, cache TTL monitoring, per-tenant fault containment, and approved rollbacks.
12. Define separate QA criteria for **right metadata**, **right keys**, **right registration**, **right SAML validation**, and **right session/authorization**.

**Overarching principle:** Metadata is a source of **configuration and trust policy**, not self-validating proof of a user. Downloading new metadata **does not mean it is trusted or activated**. Only promote a snapshot after verifying provenance, policy, validity windows, EntityID/registration consistency, and change approvals; never dynamically learn SAML signing keys from unverified assertions.

## 2. Context: One SP with Two IdPs and Two Tenants

Suppose portal `https://portal.example.org` serves two independent partners:

| Component | Tenant North | Tenant South |
| --- | --- | --- |
| Internal `registrationId` | `north` | `south` |
| IdP EntityID (expected `Issuer`) | `https://idp-north.example.net/saml` | `https://idp-south.example.net/saml` |
| IdP metadata URL | `https://idp-north.example.net/metadata` | `https://idp-south.example.net/metadata` |
| SSO endpoint | `https://idp-north.example.net/sso` | `https://idp-south.example.net/sso` |
| SP EntityID (expected `Audience`) | `https://portal.example.org/saml/sp/north` | `https://portal.example.org/saml/sp/south` |
| ACS / Recipient | `https://portal.example.org/login/saml2/sso/north` | `https://portal.example.org/login/saml2/sso/south` |
| IdP trusted signing keys | `North-K1`, later `North-K2` | `South-S1` |
| SP keys | `SP-North` (if signing/decryption needed) | `SP-South` |
| Business tenant | `tenant-north` | `tenant-south` |

**Strings `North-K1` and `South-S1` are illustrative identifiers only**, not real certificates or keys. A production setup requires managed certificates, staging IdP access, valid metadata, HTTPS, browsers, and a complete Spring Boot project.

Diagram:

```text
                Browser and Spring Security RP
                            |
                  /saml2/authenticate/north
                  /saml2/authenticate/south
                            |
              +-------------+-------------+
              |                           |
          IdP North                   IdP South
     entityId=https://.../north     entityId=https://.../south
     signing key N1/N2               signing key S1
              |                           |
          SAMLResponse                SAMLResponse
              |                           |
              v                           v
     POST /login/saml2/sso/north   POST /login/saml2/sso/south
              |                           |
              +------------+--------------+
                           |
         Saml2WebSsoAuthenticationFilter
                           |
            RelyingPartyRegistration lookup
                           |
                  OpenSAML verification
                           |
              local account + tenant policy
```

From the diagram, note three distinctions:

- `registrationId` is Spring's **internal key**, such as `north` or `south`; it **does not have to equal** the IdP's `Issuer`/EntityID.
- `SP EntityID` is the assertion's audience and the ID the IdP uses to identify the SP. It can be any registered URI, **not necessarily an HTTP-reachable URL**.
- `ACS` is the real HTTP URL receiving `SAMLResponse`; it must match `Destination` and `SubjectConfirmationData.Recipient` per profile/validator. Never treat `registrationId` in the URL as proof the user belongs to that tenant before verifying issuer, signature, audience, and correlation.

## 3. SAML Metadata: Structure and What Must Be Checked

IdP metadata is an XML document following the SAML 2.0 Metadata specification, abbreviated example:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp-north.example.net/saml"
    validUntil="2030-01-10T00:00:00Z"
    cacheDuration="PT1H">

  <!-- METADATA signature may appear here when used.
       Do not confuse with SAML Response signature. -->

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_NORTH_K1</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_NORTH_K2</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp-north.example.net/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

**The XML above illustrates structure only**, not usable metadata: certificates are placeholders, XML is unsigned, and IdP hostnames do not exist in a live lab automatically. Never put this sample payload into production to bypass metadata signature policies.

### 3.1. Fields That Must Be Interpreted by Role

| Metadata element | What to check | Risk |
| --- | --- | --- |
| `EntityDescriptor@entityID` | Matches the IdP EntityID approved for the registration | Importing metadata for the wrong tenant/issuer |
| `EntitiesDescriptor` | May wrap multiple entities; select the single exact entity | Picking the wrong IdP entity across partners |
| `IDPSSODescriptor` | Supports SAML2 protocol and required bindings | HTTP-POST/Redirect incompatibility |
| `SingleSignOnService@Location` | Allowlisted IdP HTTPS endpoint matching binding | SSRF/redirect to an unexpected host |
| `SingleLogoutService` | SLO endpoint and binding if used | Logging out to the wrong partner / DoS |
| `KeyDescriptor use="signing"` | Public key/certificate used to verify SAML Response/Assertion | Trusting the wrong key, failure or impersonation |
| `KeyDescriptor use="encryption"` | IdP public cert for encryption if profile requires | Confusing encryption trust with response signing |
| Missing `use` on `KeyDescriptor` | Per metadata spec, usable for both signing/encryption per policy | Importing for unintended purpose in custom parsers |
| `validUntil` | Until when the metadata instance remains valid | Accepting expired metadata |
| `cacheDuration` | Hint for how long to cache before attempting refresh | Confusing cache expiration with XML invalidity |
| Metadata `ds:Signature` | Verified via a **metadata trust anchor** configured outside metadata | Metadata poisoning / key substitution |
| SP `<md:SPSSODescriptor>` | SP EntityID, ACS, and SP public signing/encryption certs | IdP uses stale SP metadata, breaking SP key rollover |

**Metadata signing keys differ from response signing keys.** A metadata document may be signed by a federation authority/aggregator rather than the IdP key currently signing assertions. Extracting a certificate found inside the metadata and using it to verify that same metadata is **unapproved trust-on-first-use**, creating a circular trust flaw.

### 3.2. Commonly Confused "Certificates" and "Keys"

| Entity name | Who holds private key? | Who needs public cert/trust? | Purpose |
| --- | --- | --- | --- |
| **IdP Response/Assertion signing** | IdP | SP/RP | Verifies XML Signature of `SAMLResponse`/Assertion |
| **IdP metadata signing** | IdP or trusted metadata publisher | SP/RP holding metadata verification trust anchor | Verifies metadata XML |
| **IdP TLS HTTPS certificate** | IdP HTTPS server/ingress | JVM/HTTP client fetching metadata | TLS server authentication / PKIX / hostname |
| **SP `AuthnRequest` signing** | SP/RP | IdP | Verifies signature of SP-sent `AuthnRequest`/`LogoutRequest` |
| **SP assertion decryption** | SP/RP | IdP needs SP public encryption cert | IdP encrypts, SP decrypts `EncryptedAssertion`/`EncryptedID` |
| **SP TLS HTTPS certificate** | SP ingress/backend | Browser / IdP HTTP client depending on connection | HTTPS ACS/metadata endpoints |
| **Trusted CA / metadata publisher** | PKI / metadata authority | SP metadata trust store / verification credentials | Supplies trust anchors; not a SAML issuer itself |

Never import an IdP private key into the SP. The SP needs only the **public verification cert** to verify IdP signatures; SP signing/decryption private keys must live in an SP-managed KMS/keystore/secret mount. Even if a certificate serves multiple purposes, verify each usage/policy independently without assuming all trust is equivalent.

## 4. OASIS Semantics of `validUntil` and `cacheDuration`

This is the easiest area to get wrong in tests.

- `cacheDuration="PT1H"`: indicates how long a metadata consumer should cache before **attempting a refresh**. It does not declare that the metadata becomes invalid after one hour.
- `validUntil="2030-01-10T00:00:00Z"`: at that instant, the metadata instance **must no longer be used**; an earlier `validUntil` on a parent `EntitiesDescriptor` also caps validity.
- Metadata **past `cacheDuration` yet still before `validUntil`** is *stale for refresh* but may remain *valid for trust* per policy. Depending on risk, consumers may keep using the last valid snapshot temporarily when fetches fail.
- Metadata **at or past `validUntil`** must be treated as **invalid**. Never let cache TTLs or Redis entries keep metadata alive past its hard validity boundary.
- Omitting `validUntil` does not mean metadata lasts forever; enforce an **organizational hard max age**, signature trust, fetch policies, and alerts—yet do not falsely invent an OASIS rule that "all metadata without `validUntil` is invalid" if the contract does not require it.
- `cacheDuration` on `EntityDescriptor` may be overridden by policies on parent metadata. Never grep the first attribute with regex and ignore hierarchy.
- Keep UTC/NTP clocks synchronized; `validUntil` is an absolute instant, not a TTL measured from pod startup.
- Multiple metadata entities may each have distinct validity windows; test **effective validity** for the exact selected entity.

### 4.1. Timeline Example and Decisions

```text
Metadata North v1:
  retrievedAt = 09:00 UTC
  cacheDuration = PT1H
  validUntil = 13:00 UTC

09:30  -> cache age 30m; metadata still valid.
10:01  -> cacheDuration elapsed; attempt refresh.
10:02  -> DNS fetch error; v1 is still before validUntil.
          Can use LAST-KNOWN-GOOD per approved policy.
12:59  -> if not yet refreshed, still inside hard validity window;
          must emit alert and bound stale fallback.
13:00  -> validUntil reached: do NOT use v1 anymore.
13:01  -> fetch still failing: block NEW SAML logins / report incident,
          never enable unapproved keys to rescue login.
```

Never promise a resolver fires at exactly 10:01 under every framework or scheduler; refresh jitter, backoff, or async execution may apply. Test **policy properties** and observe actual refresh/activation timings rather than assuming from XML attributes alone.

### 4.2. When the IdP Metadata Endpoint Is Unreachable

| Scenario | Safe behavior | Notes |
| --- | --- | --- |
| Fetch times out while last-good metadata is still valid and trusted | Continue per approved stale tolerance, alert | Never auto-load unsigned/untrusted new metadata |
| Last-good passed `validUntil` | **Do not trust** expired snapshot to verify new logins | Fail closed, provide user support mechanism |
| Metadata changes `EntityID` to unknown host | Do not activate automatically; trust-boundary review | Possible tampering or misconfiguration |
| IdP emits unscheduled new `KeyDescriptor` | Block or quarantine per policy, require owner confirmation | Signed/trusted metadata is necessary but insufficient if process requires approval |
| Metadata DNS redirects to private IP/localhost | SSRF/network policy rejects | Never follow redirects blindly |
| IdP TLS certificate expired | Fetch fails PKIX checks | Never use `trustAll` |
| Signed metadata has invalid signature | Reject, retain last-known-good if still valid | Never use a new cert inside metadata to verify that same metadata |
| Simultaneous cache eviction across pods | Thundering herd / network storm | Jitter, single-flight, backoff, and shared validated snapshots |
| IdP returns HTTP 200 with unparseable XML | Reject candidate, do not replace current state | HTTP 200 != metadata trust pass |

## 5. Three Metadata-Loading Mechanisms to Distinguish in Spring Security

### 5.1. Approach A: Loading Metadata When Building an InMemory Repository

Spring Security supports:

```java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp-north.example.net/metadata")
        .registrationId("north")
        .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
```

A similar pattern uses `spring.security.saml2.relyingparty.registration.<id>.assertingparty.metadata-uri` in supported Boot versions (verify properties per version).

**However:** `InMemoryRelyingPartyRegistrationRepository` stores pre-built registration objects; **it does not periodically reload metadata merely because the initial metadata came from a URL**. If the IdP publishes N2 after app startup while the app still holds only N1, responses signed by N2 will fail until the repository is properly refreshed/restarted.

### 5.2. Approach B: `CachingRelyingPartyRegistrationRepository`

Since Spring Security 6.4, `CachingRelyingPartyRegistrationRepository` accepts a **loader** that rebuilds the repository and manages caching via Spring Cache. Per Spring docs, a cache configured without expiration can hold registrations indefinitely. **Your chosen cache TTL/eviction** dictates when the loader runs again.

Distinguish:

```text
Startup -> loader fetches trusted IdP metadata -> Registration snapshot v1
  |
  +--> Cache hit: use v1
  |
  +--> Cache eviction / expiry:
          loader fetches metadata again
          -> validate candidate according to your trust policy
          -> create registrations v2
          -> cache v2
```

If the loader simply calls `RelyingPartyRegistrations.fromMetadataLocation(url)`, it **does not automatically provide independent metadata-signature verification**. Distinguish "approved HTTPS URL" from "XML metadata with a trusted signature," and use an appropriate metadata signing/verification pipeline.

**QA note:** calling `cache.clear()` only forces a re-fetch; it proves neither that the new version is trusted nor that `validUntil` is enforced if the cache provider is unaware of it. Verify after updates: which registration is returned, which key fingerprint verifies Responses, and whether all pods converged.

### 5.3. Approach C: OpenSAML-Based Asserting Party Metadata Repository/Resolver

In supported Spring Security releases, `AssertingPartyMetadataRepository` decouples AP metadata from RP registrations, and `OpenSaml5AssertingPartyMetadataRepository` wraps an OpenSAML `MetadataResolver`, supporting expiry-based refresh and metadata signature verification when verification credentials are configured.

Conceptual flow:

```text
trusted metadata location or signed source
       |
       v
OpenSAML metadata resolver
       |
   parse / signature / validity / cache policy
       |
       v
AssertingPartyMetadataRepository
       |
       +--> AP metadata for North
       +--> AP metadata for South
       |
       v
RelyingPartyRegistrationRepository
       + fixed SP entityID, ACS, signing/decryption keys
       |
       v
SAML filter & provider
```

**Important point from the reference:** `OpenSaml5AssertingPartyMetadataRepository.withMetadataLocation(...).verificationCredentials(...)` can verify XML metadata signatures. **Without verification credentials configured, the component does not verify metadata signatures automatically.** `fromTrustedMetadataLocation(...)` relies on the location/transport trust model and must never be advertised as "auto-verifying XML signatures" unless checked.

Approach C does not eliminate the need for: trust anchor bootstrapping, SSRF defenses, max response size limits, timeouts, `validUntil` policies, stable `registrationId→entityID` mapping, SP keys/ACS, and multi-tenant tests. **Never mix APIs from Spring Security 6.5, 7.1, and OpenSAML 4/5 without aligning your exact version.**

### 5.4. Comparison Table

| Design | Refreshes? | Who decides trust/expiry? | Best fit |
| --- | --- | --- | --- |
| `InMemoryRelyingPartyRegistrationRepository` loading metadata at start | Not automatically | Config/release pipeline and startup load logic | Rarely changing IdPs, restart per runbook |
| `CachingRelyingPartyRegistrationRepository` + TTL cache | Per eviction/cache policy | Your loader, signed metadata verifier, and validation/approval service | One or a few partners with cache infra and release policy |
| `OpenSaml5AssertingPartyMetadataRepository` / `MetadataResolver` | Per resolver/expiry policy when properly configured | OpenSAML metadata trust/validity + RP mapping and external policy | Multiple IdPs/metadata documents needing stronger lifecycle |
| Custom dynamic DB/service repository | Implementation-dependent | App policy, DB consistency, signature verifier | Multi-tenant platforms with dedicated control plane, atomic snapshots, and audit |
| "GET XML on every login request and trust embedded keys" | Yes, dangerously | No trust anchor or DoS limits if naive | **Never use** |

## 6. Trust Paths When Updating Metadata

### 6.1. Never Learn Keys from a SAML Response

A classic attack:

```text
Attacker creates unsigned/fake SAMLResponse
   |
   +-- embeds KeyInfo containing attacker certificate
   +-- uses Issuer="https://idp-north.example.net/saml"
   |
   v
Vulnerable SP extracts key from XML
   |
   v
Verifies signature against that same attacker key
   |
   v
Forged login accepted
```

The right flow:

```text
Verified registrationId -> approved IdP entityID
     |
     v
Last-known-good trusted metadata / pinned certs
     |
     v
Trusted verification credentials for THAT IdP
     |
     v
Verify XML Signature over exact signed SAML nodes
     |
     v
Issuer + Audience + Destination + Recipient + Time
+ InResponseTo + request correlation + replay checks
     |
     v
Local account and tenant authorization
```

`KeyInfo` in SAML XML is only a **key-selection hint**, never a self-granting trust source. Updated metadata must be verified with a **pre-configured trust anchor** or approved management channel—never treat a public key inside the payload as proof of trustworthiness.

### 6.2. Verifying Metadata Signatures and TLS

- Fetch metadata over HTTPS with **hostname/SAN verification**, PKIX trust chain, validity, and strict checks. Never disable TLS verification for a missing CA.
- When metadata carries an XML signature, the SP verifies it using **metadata-signing verification credentials** configured out-of-band. Metadata aggregators may use a different signing key than IdP Responses.
- In deployments relying on pinning/allowlisting trusted locations instead of signed XML, understand the different trust risks and enforce contracts/audits. **HTTPS from the right hostname does not equal a publisher's XML metadata signature**.
- Pin expected `entityID`, SSO host/bindings, and permitted signing algorithms; require audit/approval for unexpected changes based on risk.
- If metadata contains multiple `EntityDescriptor` elements, select by exact registered ID—never grab the first entry arbitrarily.
- Block XML DTD/XXE, oversized payloads, deep nesting, and signed XML wrapping using a hardened parser resolver.
- Bound redirects, outbound connections, response sizes, DNS/IPs (block loopback/link-local/cloud metadata services), connect/read timeouts, and retry budgets.
- Never fetch a metadata URL supplied by the browser via `?metadataUrl=...` or HTTP `Host`.
- Never expose truststores/passwords/private keys in logs, metrics, or metadata HTTP responses.
- Define handling for valid metadata carrying an unapproved key: **quarantine** or staged rollout per security policy, never auto-switching all registrations.

### 6.3. Why Metadata Signatures Do Not Replace Response Signatures

A validly signed metadata document only attests that **IdP configuration was endorsed by that authority**, including its public verification key(s). Every individual `SAMLResponse` or `Assertion` must still carry a valid XML Signature per profile under an **authorized key in the registration**, plus issuer/audience/time/recipient checks. Never skip XML Signatures merely because metadata was signed or TLS-protected.

Likewise, a `SAMLResponse` validly signed with North's key does not prove it belongs to South; **registration isolation** must still run before creating `Authentication` or granting tenant roles.

## 7. IdP Signing-Key Rollover: Modeling Before, During, and After Cutover

Suppose North currently signs Responses with private key `N1` and plans to migrate to `N2`. The SP **holds only public certs** `N1-cert` and `N2-cert`.

### 7.1. Standard Timeline with an Overlap Window

```text
T0: IdP North signs SAMLResponse with N1.
    Metadata publishes only N1.
    SP trusts N1.              -> Login with N1 PASS.

T1: IdP publishes metadata containing BOTH N1 and N2
    while still signing with N1.
    SP fetches/trusts new metadata; verifies N1 and N2 are approved.
    SP trusts [N1,N2].         -> Login with N1 PASS; N2 ready.

T2: IdP switches to signing with N2.
    SP already trusts [N1,N2]. -> Login with N2 PASS.
    Some in-flight N1 responses may still arrive during overlap.

T3: After agreed grace period and in-flight lifetime,
    IdP removes N1 from metadata.
    SP refreshes and removes N1. -> N2 PASS; N1 FAIL.

T4: Audit and cleanup: N1 retired, caches/nodes verified,
    no stale trust of N1 remains.
```

If key `N1` is **compromised**, do not apply a grace period just to avoid login errors. Follow incident revocation for response/metadata trust, block `N1` as quickly as possible, and coordinate an emergency IdP/SP cutover.

### 7.2. Non-Negotiable Test Cases

| State | Signed with N1 | Signed with N2 | Signed with unknown NX |
| --- | --- | --- | --- |
| SP trusted set `{N1}` | PASS if full SAML valid | **FAIL** | FAIL |
| SP trusted set `{N1,N2}` | PASS while under contract | PASS | FAIL |
| SP trusted set `{N2}` | **FAIL** | PASS | FAIL |
| Metadata holds `{N1,N2}` yet metadata signature invalid | Must not activate snapshot | Must not activate snapshot | FAIL |
| Metadata has expired `validUntil` | Must not serve as trust source | Must not serve as trust source | FAIL |
| North response sent to South registration | **FAIL even though N1 is valid at North** | FAIL | FAIL |

Every PASS in the table **further assumes** the XML Signature was verified on the exact node and all SAML checks (issuer/audience/recipient/time/correlation) passed. Never test by editing Base64 of a signed message post-signing and calling it a "key mismatch."

### 7.3. Why "Metadata Loaded Successfully" Does Not Prove Rotation Worked

Common failure modes:

- Fetch pulls new XML, yet `InMemoryRelyingPartyRegistrationRepository` still holds old registration objects.
- Cache refreshed on one pod while other pods still cache `N1`.
- New metadata includes `N2`, yet custom code reads only the **first `KeyDescriptor`**.
- Parser drops `KeyDescriptor` due to `use` flags or trust policy mismatches.
- IdP switches to `N2` before cache TTL expires; SP has not fetched yet.
- Metadata signature verification fails, so the loader falls back to last-known-good `N1`; **safe behavior, yet availability fails**.
- Proxy/CDN caches stale metadata even after the origin IdP updated.
- New `validUntil` is ignored or misparsed across time zones.
- Static certificate bundles in YAML override dynamic metadata keys.
- IdP signs the **Response** with `N2`, yet the SP checks `N2` only on the **Assertion** (or vice versa per provider); verify signed-node policy.

**Rotation PASS definition:** After T2, valid `N2`-signed Responses are verified by **the right pod/registration** and create principals for the right tenant; after T3, `N1`-signed Responses are rejected; unknown keys are always rejected; zero unsigned fallbacks exist.

## 8. SP Signing/Decryption Rotation: An Independent Axis

When the SP rotates its **`AuthnRequest` signing** or **Assertion decryption** key, rollout order is typically the reverse of IdP signing rotation.

### 8.1. SP Signing AuthnRequest

- The SP holds the private signing key; the IdP holds the public verification certificate via **SP metadata**/partner config.
- Before the SP begins signing with `SP-New`, **the IdP must already trust the new public cert** and update the exact SP EntityID/registration policy.
- Overlap phase: the IdP may accept both `SP-Old` and `SP-New` per policy; the SP can deliberately switch to the new signing key.
- Verify the IdP genuinely validates signed `AuthnRequest`s with the new key—do not merely check that SP `/saml2/metadata/{registrationId}` lists the new certificate.
- Post-cutover, the IdP retires `SP-Old` on schedule; on compromise, follow incident procedures.
- With HTTP-Redirect binding, the signature lives in URL query params `SigAlg`/`Signature` per binding, not an embedded XML `<ds:Signature>`. Never substitute an arbitrary XML verifier for the IdP's binding check.

### 8.2. SP Decrypting EncryptedAssertion

- The IdP uses the **SP public encryption certificate** to encrypt assertions; the SP holds the matching private decryption key.
- Before the IdP begins encrypting with `SP-New`, the SP must deploy the new private decryption key across **all pods**, while optionally retaining the old key for in-flight messages.
- Post-cutover, the IdP encrypts with `SP-New`; test SP decryption succeeds. Once older assertion lifetimes expire, retire `SP-Old` per risk/policy.
- Test with a real encrypted fixture from the IdP; **passing Response signature verification does not guarantee decryption works**.
- `Saml2X509Credential.decryption(...)` differs from `verification(...)`. A public certificate alone **cannot** decrypt.
- With PKCS#11/HSM/KMS, verify key aliases/identifiers and algorithm support; never assume swapping a `.crt` file swaps the private key.

### 8.3. One Certificate Serving Multiple Purposes?

Some systems reuse one keypair for signing and decryption, though you should not assume that by default. When keys are separated, rotations can occur on different dates. Tests must clearly specify:

```text
IdP North signing response: N1 -> N2
SP North signing request:  SN1 -> SN2
SP North decrypting assertion: DN1 -> DN2
Metadata publisher signing: MN1 -> MN2
HTTPS server cert IdP:    TN1 -> TN2
```

**Five distinct rotation tracks.** A script comparing "old vs. new SHA-256 fingerprints" is helpful, yet **does not** prove trust, key usage, or tenant correctness. Metadata-signing key rollover has its own bootstrap workflow; never trust a new metadata-signing cert found inside unverified metadata.

## 9. Multiple Registrations: Fixed Mapping Keys and Tenant Isolation

`RelyingPartyRegistration` models an **SP ↔ IdP pair**, not merely a hostname. In Spring, `registrationId` keys the exact pair. An app may define:

```text
north:
  idpEntityId = https://idp-north.example.net/saml
  spEntityId  = https://portal.example.org/saml/sp/north
  acs         = https://portal.example.org/login/saml2/sso/north

south:
  idpEntityId = https://idp-south.example.net/saml
  spEntityId  = https://portal.example.org/saml/sp/south
  acs         = https://portal.example.org/login/saml2/sso/south
```

### 9.1. Pairs That Must Be Verified Together

1. `registrationId` matches the configured value, never taken from a browser query parameter to grant a tenant.
2. `Issuer` of the SAML Response/Assertion matches the registration's **expected IdP EntityID**.
3. XML Signature is verified using **that registration's trusted verification credentials**, never a union of all IdPs' keys.
4. `AudienceRestriction` contains the matching **SP EntityID**; a North assertion does not gain South's audience merely by hitting South's ACS.
5. Response `Destination` and `SubjectConfirmationData.Recipient` match the registered **public ACS URL** across scheme/host/path/binding.
6. `InResponseTo` correlates with the `AuthnRequest` belonging to that session/registration (when SP-initiated); never accept another tenant's request ID.
7. `NotBefore`/`NotOnOrAfter`, conditions, replay/`OneTimeUse`, and subject confirmation pass per profile.
8. Any decryption key belongs strictly to that SP registration; never try every tenant's private key and accept the payload into an arbitrary tenant.
9. When building the principal, map `(issuer, stable NameID/subject) → internal account ID`; tenant rights must come from an authoritative business source.
10. `registrationId` in URLs can be guessed or edited: **it never bypasses issuer/audience/recipient/signature checks**.
11. When one IdP shares an EntityID across registrations, IdP-initiated SSO becomes ambiguous. Use an explicit ACS/registration mapping or require SP-initiated correlation—never pick "first match."
12. SLO metadata/`LogoutRequest` must also match the exact registration and session, not just an issuer string.

### 9.2. Distinguishing `EntityID` from Hostname

An EntityID is usually a URI identifier and **does not automatically require being HTTP-GET reachable**. For example, one SP public host can carry two EntityIDs if configured on the IdP registration. The ACS is the actual HTTPS URL receiving POSTs. Having a single hostname does not imply the application has only one registration.

Conversely, an IdP may publish `EntitiesDescriptor` metadata containing multiple `EntityDescriptor` elements. Integrators must pick the exact approved `entityId`, never the first entity or one with a similar-looking certificate.

### 9.3. IdP-Initiated SSO Is Especially Sensitive

In unsolicited IdP-initiated responses, **`InResponseTo` may be absent**. If a single IdP EntityID serves multiple tenants/registrations and shares an ACS route:

- There is no SP-initiated request state to identify the expected registration.
- Matching by `Issuer` alone yields multiple candidates.
- Inferring from browser-supplied `RelayState` is also unsafe.
- Either **disallow ambiguous cases** or use a deliberately designed ACS/issuer-specific binding enforcing signed audience/recipient.
- Never grant tenant access from a NameID/email domain suffix or a raw query param like `tenant=south`.
- Test simultaneous logins from both tenants and cross-posted responses; confirm zero tenant confusion.

## 10. Spring Boot 3.x: Static Config of Two Registrations with Separate Keysets

**Sample scope:** Spring Boot 3.5.x + Spring Security 6.5.x, Servlet, Java 17+; project needs a test IdP, certificate files, and valid credentials. This section's config is **static/loaded at application startup** and does not claim metadata URL refresh. Section 12 covers refreshing repositories.

### 10.1. Maven Dependencies

In a POM with Spring Boot parent/BOM, Java 17:

```xml
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
```

This is a **fragment**, not a standalone POM. Spring Security SAML2 depends on OpenSAML; depending on distribution/build repositories, Shibboleth Releases may be needed via a trusted artifact proxy per Boot docs. Run `./mvnw dependency:tree` to check the resolved OpenSAML version and avoid mixing OpenSAML 4/5 or Spring Security 6/7.

### 10.2. `application.yml` for North/South

File `src/main/resources/application.yml`:

```yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

spring:
  security:
    saml2:
      relyingparty:
        registration:
          north:
            entity-id: "https://portal.example.org/saml/sp/north"
            acs:
              location: "https://portal.example.org/login/saml2/sso/north"
            assertingparty:
              entity-id: "https://idp-north.example.net/saml"
              sso-url: "https://idp-north.example.net/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/north-idp-N1.crt"
                  - certificate-location: "classpath:saml/north-idp-N2.crt"

          south:
            entity-id: "https://portal.example.org/saml/sp/south"
            acs:
              location: "https://portal.example.org/login/saml2/sso/south"
            assertingparty:
              entity-id: "https://idp-south.example.net/saml"
              sso-url: "https://idp-south.example.net/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/south-idp-S1.crt"
```

**QA points:**

- `registration.north` and `registration.south` are bound by Spring Boot into two RP configs.
- Registration-level `entity-id` is the **SP EntityID**; `assertingparty.entity-id` is the **IdP EntityID**. Never swap these two.
- `acs.location` must match the URL the IdP posts Responses to; `Destination` and `Recipient` validate against it.
- North lists **two public verification certificates** `N1`/`N2` to model overlap. South lists only `S1`; **never add `N1`/`N2` to South** to troubleshoot North.
- `classpath:...crt` certs in this example are test fixtures. Production may load from a secret/config store or signed metadata, with proper update and restart/refresh controls. Never embed SP private signing/decryption keys in Git/JARs.
- This config **does not require `AuthnRequest` signing** or Assertion decryption. If the IdP requires them, add SP `signing.credentials`/`decryption.credentials` with the right private key/cert per registration and verify IdP metadata/behavior. Never fall back to insecure downgrades.
- `forward-headers-strategy` is safe only when the reverse proxy strips/rewrites `Forwarded`/`X-Forwarded-*`. Never derive the public ACS from a browser-supplied `Host` header.
- In a SAML Response, valid `N1`/`N2` credentials are **only the signature check**, proving nothing on their own about audience, recipient, issuer, session/correlation, or tenant.
- **Do not** treat this example as dynamic metadata configuration; it is a static snapshot for testing rotation and tenant isolation with release-driven control planes.

### 10.3. `SecurityFilterChain` and SP Metadata

File `src/main/java/com/example/saml/TwoTenantSamlSecurity.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TwoTenantSamlSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/tenant/north/**").authenticated()
                .requestMatchers("/tenant/south/**").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

This snippet enables SAML login and publishes SP metadata, **but does not yet provide full tenant authorization**: `authenticated()` only requires login, without proving a North user may access `/tenant/north/**`. In a real app, bind `AuthorizationManager`/`@PreAuthorize`/data permission checks to verified `issuer+subject` and local tenant memberships; requests to the wrong tenant must return 403/404 per policy.

Typical SAML endpoints:

```text
/saml2/authenticate/north
/saml2/authenticate/south
/login/saml2/sso/north
/login/saml2/sso/south
/saml2/metadata
/saml2/metadata/north
/saml2/metadata/south
/saml2/service-provider-metadata/north
/saml2/service-provider-metadata/south
```

`/saml2/metadata` can publish combined metadata when the repository is `Iterable`; per-registration endpoints must emit that partner's exact SP EntityID, ACS, and credentials. When metadata outputs the wrong hostname behind a reverse proxy, fix the canonical base URL or trusted forwarding—never hand-edit strings inside signed XML.

### 10.4. Maven/Runtime Verification

```bash
./mvnw dependency:tree
./mvnw test
./mvnw spring-boot:run
```

Commands succeed only with a real Maven wrapper/project/staging IdP/test certificates where placeholders are replaced by managed config; there is no way to mint valid signed SAML Responses from this YAML alone.

## 11. Spring Security 6.4–6.5: Reloading via `CachingRelyingPartyRegistrationRepository`

When IdP metadata must be re-fetched automatically upon **cache expiry**, you can build a repository backed by Spring Cache. Distinguish a **refresh demo model** from a **production metadata verification pipeline**.

### 11.1. Architectural Concept

```text
SecurityFilterChain
    |
    v
CachingRelyingPartyRegistrationRepository
    |
    +--> Spring Cache entry (lifetime configured)
    |
    +--> on miss:
            loader()
            -> fetch North metadata by approved URL
            -> fetch South metadata by approved URL
            -> parse and validate against trust policy
            -> construct immutable per-registration snapshots
            -> InMemoryRelyingPartyRegistrationRepository
    |
    v
findByRegistrationId("north" | "south")
```

**Warning:** If the loader skips verifying metadata signatures/`validUntil`/`entityID`/bindings and lacks last-known-good retention, a cache miss during an IdP outage can break logins or cache untrusted metadata. Never run demo code directly as a complete production security control.

### 11.2. Maven for Caffeine Cache

Alongside the dependencies in section 10, you can add:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
  <groupId>com.github.ben-manes.caffeine</groupId>
  <artifactId>caffeine</artifactId>
</dependency>
```

The Spring Boot BOM normally manages the matching Caffeine version; if using another BOM, align versions carefully. Caffeine in this sample is **in-process**, so each pod maintains its own cache and does **not** refresh simultaneously with other pods.

### 11.3. Java Config: TTL Without Built-in Metadata Signature Verification

File `src/main/java/com/example/saml/RefreshingSamlRegistrations.java`:

```java
package com.example.saml;

import java.time.Duration;
import java.util.concurrent.Callable;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.IterableRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class RefreshingSamlRegistrations {

    @Bean
    CacheManager samlCacheManager() {
        CaffeineCacheManager manager =
            new CaffeineCacheManager("trusted-saml-registrations");
        manager.setCaffeine(Caffeine.newBuilder()
            .expireAfterWrite(Duration.ofMinutes(15))
            .maximumSize(32));
        return manager;
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            CacheManager samlCacheManager) {

        Callable<IterableRelyingPartyRegistrationRepository> loader =
            () -> {
                // SOURCE LOCATIONS MUST BE FIXED AND PRE-APPROVED.
                // Production loader: verify metadata signature,
                // hard validUntil, expected entityIDs and endpoints,
                // trusted key changes and atomic publication.
                RelyingPartyRegistration north =
                    RelyingPartyRegistrations
                        .fromMetadataLocation(
                            "https://idp-north.example.net/metadata")
                        .registrationId("north")
                        .entityId(
                            "https://portal.example.org/saml/sp/north")
                        .assertionConsumerServiceLocation(
                            "https://portal.example.org/login/saml2/sso/north")
                        .build();

                RelyingPartyRegistration south =
                    RelyingPartyRegistrations
                        .fromMetadataLocation(
                            "https://idp-south.example.net/metadata")
                        .registrationId("south")
                        .entityId(
                            "https://portal.example.org/saml/sp/south")
                        .assertionConsumerServiceLocation(
                            "https://portal.example.org/login/saml2/sso/south")
                        .build();

                return new InMemoryRelyingPartyRegistrationRepository(
                    north, south);
            };

        CachingRelyingPartyRegistrationRepository registrations =
            new CachingRelyingPartyRegistrationRepository(loader);

        Cache cache = samlCacheManager.getCache(
            "trusted-saml-registrations");
        if (cache == null) {
            throw new IllegalStateException(
                "SAML metadata cache is not configured");
        }

        registrations.setCache(cache);
        return registrations;
    }
}
```

**Mandatory limitations to read:**

1. This class is a **reload-pattern sample** requiring dependencies, real IdP metadata, trust stores, and Spring Security; it does not compile/run standalone with `javac`.
2. `CachingRelyingPartyRegistrationRepository` uses a 15-minute TTL here. That is **not a Spring Security default** and **does not** automatically enforce XML `cacheDuration`/`validUntil`.
3. `fromMetadataLocation(...)` **does not demonstrate signed-metadata verification**. Production requiring signed metadata must replace the loader with a verified metadata-reading/trust pipeline or use `OpenSaml5AssertingPartyMetadataRepository` with verification credentials on supported releases.
4. On a cache miss, the demo fetches **both North and South**. One IdP outage can affect both registrations. Production can partition refreshes per registration to limit blast radius with isolated atomic snapshots/versions.
5. Caffeine is per-JVM; across four pods, each pod may refresh at a different instant. Plan convergence tests, jitter, alerts, reconciliation, and health metrics.
6. It omits stale last-known-good handling, snapshot failover, signature/EntityID reviews, auditing, and hard `validUntil` checks. Therefore, **never use the raw sample as a production metadata trust gate**.
7. Defining a `RelyingPartyRegistrationRepository` bean above **replaces** Boot's auto-configured repository from `spring.security.saml2.relyingparty.registration.*`; do not configure both expecting them to merge automatically.
8. `maximumSize(32)` is a cache-entry budget, not a registered-IdP cap; check exact key semantics of Spring's implementation.
9. To shrink stale windows, build controlled reload monitoring and invalidation—never drop TTL to milliseconds so every login hits the IdP metadata URL.
10. Never use `@Scheduled` to mutate fields of a live registration while authentication threads read it; build an immutable object graph and **publish atomically**.

### 11.4. Testing Cache Timing

Example with a 15-minute cache TTL:

```text
T0 = 10:00 app fetch North metadata v1 (N1)
T1 = 10:03 IdP publishes v2 (N1 + N2)
T2 = 10:05 login still uses cached v1 (N1 only)
T3 >= 10:15 cache may expire; loader can fetch v2 on use
T4 = after verified activation, login signed N2 may pass
```

**Never rely on a single `Thread.sleep(15m)`.** Use fake clocks/cache controls, and test eviction/refresh using metrics plus genuinely signed SAML responses. "Cache entry expired" is distinct from "trust list updated across all nodes."

## 12. OpenSAML Metadata Resolver and Signed-Metadata Validation

Spring Security docs on versions supporting `OpenSaml5AssertingPartyMetadataRepository` clearly describe `MetadataResolver`-driven metadata refresh and optional signature verification.

### 12.1. Metadata Signature Verification Fragment

```java
// FRAGMENT for supported Spring Security/OpenSAML versions.
// myMetadataVerificationCredential is the public verification
// certificate supplied via trusted trust-bootstrap, NOT taken
// from the newly downloaded metadata.

OpenSaml5AssertingPartyMetadataRepository metadata =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation(
            "https://idp-north.example.net/metadata")
        .verificationCredentials(credentials ->
            credentials.add(myMetadataVerificationCredential))
        .build();
```

Supply exact imports/classes/APIs for your active version. **This is not a standalone Java class**, and the credential variable represents an **out-of-band verified metadata-signing certificate**. Without verification credentials configured, Spring docs explicitly state the component **performs no metadata signature verification**.

An alternative is `fromTrustedMetadataLocation(...)`, where trust rests on an approved metadata location and fetch channel. Assess its trust guarantees **accurately** (TLS/server identity/pinning/allowlist), never mistaking it for automatic XML signature verification when none is configured.

### 12.2. Do Not Equate `entityId` with `registrationId`

When querying metadata via `AssertingPartyMetadataRepository.findByEntityId(entityId)`, the parameter is the **IdP EntityID**, **not** Spring's `registrationId` by default. For example:

```text
registrationId = north
expectedIdpEntityId = https://idp-north.example.net/saml

metadata.findByEntityId(
    "https://idp-north.example.net/saml")  -> candidate North
metadata.findByEntityId("north")           -> usually null
```

If code builds a new repository using `findByEntityId(registrationId)` assuming they always match, it breaks with real tenants. A dynamic repository needs an approved configuration mapping table:

```text
Map<String, TrustedIdpConfiguration>
  north -> (expected issuer/entityID, metadata location,
            SP entityID, ACS, SP credentials, trust anchors)
  south -> (...)
```

It fetches AP metadata by expected EntityID, then builds the RP registration with a **fixed `registrationId`** and fixed SP details. Fresh metadata must never arbitrarily rewrite SP `entityID`, ACS, or tenant.

### 12.3. Securing Rollout of New Metadata Snapshots

Production needs:

- **Candidate:** fetch XML with byte/timeout limits, parse securely, verify signature/TLS, check `validUntil`/allowed `EntityID`.
- **Validate:** inspect `KeyDescriptor` usage/algorithms, SSO/SLO endpoints, colliding/duplicate EntityIDs, and registration mapping.
- **Stage:** compute added/removed key fingerprints and policy diffs; require admin approval per risk.
- **Activate:** create an immutable metadata/registration snapshot and publish atomically per registration or synchronized generation.
- **Observe:** log version, fingerprint hashes/cert expiry, active registrations, refresh times, last-good age, and failures—**never** raw `SAMLResponse`/private keys.
- **Rollback:** revert only to a snapshot that is **still trusted and unexpired**, per version/approval. Never let a network glitch roll back to a key revoked for compromise.
- **Reconcile:** verify all pods/regions run the target generation within SLA; otherwise isolate faulty nodes and alert.

A metadata resolver may provide refresh/expiry logic, but **approval workflows and security policies are never replaced by the framework**. Refresh timing and trust sources must be verified with integration tests on your exact version.

## 13. The SP's Own Metadata: Publishing and Checking Each Registration

Spring Security `http.saml2Metadata(Customizer.withDefaults())` can publish SP metadata. Test:

1. `GET /saml2/metadata/north` emits **North SP EntityID**, North ACS, and North SP public certs if signing/decryption is registered.
2. `GET /saml2/metadata/south` emits South SP EntityID, South ACS, and South SP public certs; never place North's SP public key in South unless key sharing is explicitly approved.
3. `GET /saml2/metadata` may return a combined `<md:EntitiesDescriptor>` when the repository is `Iterable`. Never assume a single XML entity when multiple registrations exist.
4. Metadata must advertise public HTTPS URLs; if a reverse proxy downgrades scheme to HTTP, fix trusted headers or static canonical URLs.
5. When SP decryption cert changes, North metadata publishes the new public cert **before** the IdP begins encrypting with it.
6. When SP signing cert changes, the IdP already trusts the new cert; new signed `AuthnRequest` messages use the right key.
7. `SingleLogoutService`, if enabled, matches the exact route/registration, key, and IdP policy.
8. Metadata endpoints must never expose SP private keys; `KeyDescriptor` holds only the **public certificate** per spec.
9. If the IdP uses a remote metadata cache, verify the IdP actually refreshed SP metadata—do not rely solely on `curl GET` against the SP.
10. When a registration is removed, its endpoint returns not-found and users can no longer log in under the old config; existing local sessions/tokens follow their own lifecycle policies.

An RP architecture can share an SP EntityID/ACS across multiple IdPs, though this risks ambiguity if custom lookups are loose. Spring docs support multiple registrations; sharing an ACS does not alter SAML `Issuer`/`Audience`/Response `Destination` or correlation checks.

## 14. Key Overlap Is Not "Trust Every Certificate"

Cryptographically, an SP may accept multiple public IdP signing keys when they belong to **the same trusted IdP/registration**. That enables overlap. However:

- Every key must bind strictly to its IdP EntityID and certificate lifecycle.
- Never approve an arbitrary root CA and accept every SAML signing cert from that CA when policy demands exact IdP signing credentials. TLS X.509 chain trust and explicit SAML XML signing trust are distinct concepts.
- Never sweep every `KeyDescriptor` across all entities in a metadata aggregator into one global union.
- Never confuse `use="encryption"` with `use="signing"`.
- Never allow SHA-1/MD5 or weak signatures just to make `N2` "compatible"; signing algorithm policies must stay explicit.
- Never skip `NotBefore`/`NotOnOrAfter`/`AudienceRestriction` to let messages signed with the new key pass.
- Never accept a signed response from issuer A and map it into tenant B merely because A's certificate sits in a shared trust set.
- Never leave old key `N1` active indefinitely past T3, including in cached metadata.
- Never "fix" issues with `acceptAnyIssuer`, `verifySignature(false)`, or skipping conditions.

**An old key staying valid during overlap** is a time-bounded, policy-governed exception. Builds/tests must prove exactly when and how `N1` is removed—not only that both keys work.

## 15. Standalone Java 17: State Machine Modeling Refresh and Multi-Registration

The exercise below runs on **JDK 17** without Spring, OpenSAML, XML, or a real IdP. It models the **policy gate after a trusted component has already verified metadata and SAML signatures**. It does **not** perform XML/metadata signatures, HTTPS, replay/correlation, or SAML parsing; booleans/fingerprints in the example are **internal test fixtures**, never taken from browser requests.

### 15.1. File `SamlMetadataRolloverDemo.java`

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public final class SamlMetadataRolloverDemo {

    enum Verdict {
        PASS_POLICY_ONLY,
        DENY_NO_REGISTRATION,
        DENY_METADATA_EXPIRED,
        DENY_REGISTRATION,
        DENY_ISSUER,
        DENY_KEY
    }

    record Snapshot(
        String registrationId,
        String idpEntityId,
        Set<String> allowedSigningKeys,
        long version,
        long validUntilEpochSecond,
        boolean metadataTrusted
    ) { }

    static final class Repository {
        private final AtomicReference<Map<String, Snapshot>> active =
            new AtomicReference<>(Map.of());

        boolean activate(Snapshot candidate, long now) {
            if (candidate == null
                    || !candidate.metadataTrusted()
                    || candidate.version() < 1
                    || candidate.validUntilEpochSecond() <= now
                    || candidate.allowedSigningKeys() == null
                    || candidate.allowedSigningKeys().isEmpty()) {
                return false;
            }

            while (true) {
                Map<String, Snapshot> before = active.get();
                Snapshot old = before.get(candidate.registrationId());

                if (old != null && candidate.version() <= old.version()) {
                    return false;
                }

                Map<String, Snapshot> next = new HashMap<>(before);
                next.put(candidate.registrationId(), candidate);

                if (active.compareAndSet(before, Map.copyOf(next))) {
                    return true;
                }
            }
        }

        Verdict decide(
                String routeRegistrationId,
                String resolvedRegistrationId,
                String responseIssuer,
                String presentedKeyId,
                long now) {

            Snapshot snapshot =
                active.get().get(resolvedRegistrationId);

            if (snapshot == null) {
                return Verdict.DENY_NO_REGISTRATION;
            }
            if (snapshot.validUntilEpochSecond() <= now) {
                return Verdict.DENY_METADATA_EXPIRED;
            }
            if (!snapshot.registrationId().equals(
                    routeRegistrationId)) {
                return Verdict.DENY_REGISTRATION;
            }
            if (!snapshot.idpEntityId().equals(responseIssuer)) {
                return Verdict.DENY_ISSUER;
            }
            if (!snapshot.allowedSigningKeys().contains(
                    presentedKeyId)) {
                return Verdict.DENY_KEY;
            }

            // Simulates membership/key policy only.
            // Does NOT verify any real XML signature!
            return Verdict.PASS_POLICY_ONLY;
        }
    }

    public static void main(String[] args) {
        long now = 1_900_000_000L;
        long future = now + 600;

        Snapshot northV1 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N1"), 1, future, true);

        Snapshot northV2 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N1", "N2"), 2, future, true);

        Snapshot northV3 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N2"), 3, future, true);

        Snapshot southV1 = new Snapshot(
            "south", "https://idp-south.example.net/saml",
            Set.of("S1"), 1, future, true);

        Repository repo = new Repository();

        System.out.println("installNorth=" +
            repo.activate(northV1, now));
        System.out.println("installSouth=" +
            repo.activate(southV1, now));

        System.out.println("northOldBefore=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("northNewBefore=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("refreshOverlap=" +
            repo.activate(northV2, now));

        System.out.println("northNewOverlap=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("northOldOverlap=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("wrongRegistration=" +
            repo.decide("south", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("wrongIssuer=" +
            repo.decide("north", "north",
                "https://idp-south.example.net/saml", "N2", now));

        System.out.println("northKeyOnSouth=" +
            repo.decide("south", "south",
                "https://idp-south.example.net/saml", "N2", now));

        System.out.println("rollbackOldVersion=" +
            repo.activate(northV1, now));

        Snapshot untrusted = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("ATTACKER"), 3, future, false);

        System.out.println("untrustedRefresh=" +
            repo.activate(untrusted, now));

        Snapshot expired = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N2"), 3, now, true);

        System.out.println("expiredRefresh=" +
            repo.activate(expired, now));

        System.out.println("cutoverNewOnly=" +
            repo.activate(northV3, now));

        System.out.println("northOldAfterCutover=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("northNewAfterCutover=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("metadataExpiredAtBoundary=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", future));
    }
}
```

### 15.2. Compile Command and Stdout

```bash
javac --release 17 SamlMetadataRolloverDemo.java
java SamlMetadataRolloverDemo
```

Deterministic stdout:

```text
installNorth=true
installSouth=true
northOldBefore=PASS_POLICY_ONLY
northNewBefore=DENY_KEY
refreshOverlap=true
northNewOverlap=PASS_POLICY_ONLY
northOldOverlap=PASS_POLICY_ONLY
wrongRegistration=DENY_REGISTRATION
wrongIssuer=DENY_ISSUER
northKeyOnSouth=DENY_KEY
rollbackOldVersion=false
untrustedRefresh=false
expiredRefresh=false
cutoverNewOnly=true
northOldAfterCutover=DENY_KEY
northNewAfterCutover=PASS_POLICY_ONLY
metadataExpiredAtBoundary=DENY_METADATA_EXPIRED
```

**Explanation:**

- `installNorth`/`installSouth=true`: installs two candidate snapshots *assumed trusted*.
- `northOldBefore=PASS_POLICY_ONLY`: key ID `N1` is in North's key set; **not an XML Signature verification result**.
- `northNewBefore=DENY_KEY`: `N2` is not yet published/trusted in snapshot v1.
- `refreshOverlap=true`: activates North v2 holding `N1+N2`.
- `northNewOverlap`/`northOldOverlap=PASS_POLICY_ONLY`: models overlap.
- `wrongRegistration=DENY_REGISTRATION`: caller routed to South yet looked up North; rejects route/registration mismatch.
- `wrongIssuer=DENY_ISSUER`: response issuer mismatches North's IdP.
- `northKeyOnSouth=DENY_KEY`: North's key cannot serve as South's signing key.
- `rollbackOldVersion=false`: policy blocks equal or decreasing snapshot versions. Real SAML metadata **does not require monotonic versions**, so build dedicated control-plane generation/auditing to prevent rollbacks.
- `untrustedRefresh=false`: forged metadata cannot inject an attacker key into the active set.
- `expiredRefresh=false`: candidate already at `validUntil` cannot activate.
- `cutoverNewOnly=true`: activates `N2`-only snapshot.
- `northOldAfterCutover=DENY_KEY`: `N1` removed after cutover.
- `northNewAfterCutover=PASS_POLICY_ONLY`: `N2` remains active.
- `metadataExpiredAtBoundary=DENY_METADATA_EXPIRED`: when `now == validUntil`, fails closed.

**Extremely important limitation:** This class compares **string key IDs**, reads no X.509/PKIX, verifies zero XML Signatures, parses no SAML Assertions, and checks no `AudienceRestriction`/`Destination`/`Recipient`/`InResponseTo`/time/replay. `metadataTrusted` is a **simulated value**, never read from HTTP headers/queries/browsers. Production must use OpenSAML/Spring Security and version-accurate trusted metadata verification/authorization layers. `AtomicReference` demonstrates atomic publication **within one JVM**, not distributed consistency across pods.

## 16. Testing Refresh/Rotation with Real Signed Fixtures

### 16.1. Fixture Generation Principles

To prove **`N2` accepted after refresh**, generate a SAML Response **genuinely signed by private key `N2` in a staging IdP**, complete with:

- `Issuer` = North IdP EntityID;
- `AudienceRestriction` pointing to North SP EntityID;
- `Destination`/`Recipient` matching North ACS;
- `InResponseTo` matching North `AuthnRequest` (if SP-initiated);
- Valid `NotBefore`/`NotOnOrAfter` and bearer confirmation timestamps;
- XML Signature on the exact node/scope with an approved algorithm;
- `NameID`/attributes solely from the verified assertion;
- Optional `EncryptedAssertion` decrypted by SP North using the right key.

To test **wrong issuer with valid signature**, use a fixture signed by the test IdP with a known key where the wrong issuer/binding was placed **before signing**; never just edit the Issuer string post-signing, as doing so invalidates the signature and prevents isolating the trust boundary.

To test **invalid metadata signature**, mutate metadata XML post-signing to prove the metadata verifier rejects. To test `validUntil` or rollback policies, prepare validly signed metadata XML carrying the desired timestamp/version (or a fake trusted metadata repository with clock control). Never accidentally turn every negative test into "bad signature."

### 16.2. Two Distinct Testing Layers

**Layer A — Metadata repository / control plane**

- Use metadata files/HTTPS stubs, virtual clocks, and mock caches to test fetch TTL, expiry, backoff, signature verification, and candidate activation.
- Output is **trusted, mapped RP registrations**, not an authenticated user.
- Never allow browser-controlled external URLs in test/prod fetches.
- Test multi-pod/cluster convergence and explicit last-good fallback bounds.

**Layer B — SAML protocol / data plane**

- Use signed SAML Response fixtures and a staging IdP (SAML staging IdP only—never mix Kerberos).
- Test the real `Saml2WebSsoAuthenticationFilter` → `OpenSamlAuthenticationProvider` on the exact registration.
- Output is a `Saml2Authentication` with right principal/roles/tenant, or an authentication failure.
- Test message crypto, issuer/audience/recipient/correlation/time/replay separately from metadata fetching.
- Pre-rollout authenticated sessions may stay alive even after metadata drops the old key; key rotation primarily affects **new SAML authentications**, while session revocation follows its own policy.

### 16.3. When to Use MockMvc?

`MockMvc` fits:

- Request paths `/saml2/authenticate/{registrationId}` and ACS `/login/saml2/sso/{registrationId}`;
- Testing chooser pages and metadata resolver routes;
- Mocking repositories to prove the exact `registrationId` lookup;
- Testing 400/401/redirects per failure handler config;
- Testing multi-registration domain/tenant authorization given an already-authenticated principal.

However, MockMvc **does not** prove remote HTTPS metadata fetch trust, TLS/PKIX, pod cache expiry, real IdP signing keys, or message/metadata signature correctness if the provider is mocked. Dedicated end-to-end tests with a staging IdP and valid test keys are required.

## 17. QA Matrix: Metadata Refresh, Keys, and Multiple Registrations

For each case, record **registration, metadata generation/version, signing key fingerprint(s), IdP issuer, SP audience/ACS, signed test fixture ID, and expected HTTP + authentication outcome**. When testing key rollover, never log raw private keys, `SAMLResponse`, or bearer session cookies.

| Case | Condition | Expected outcome |
| --- | --- | --- |
| **N1 normal** | North v1 metadata trusts `N1`, SAML Response signed `N1` | PASS after full SAML validation |
| **N2 before metadata** | North v1 trusts only `N1`, Response signed `N2` | **FAIL** signature/key trust |
| **N1 after publish overlap** | North v2 verified metadata `N1+N2` | PASS during overlap per policy |
| **N2 after publish overlap** | North v2 activated on pod | PASS |
| **N1 after retirement** | North v3 `N2`-only, Response signed `N1` | FAIL |
| **N2 after retirement** | North v3 `N2`-only | PASS |
| **Unexpected N3** | Signer cert not in trusted metadata | FAIL, never auto-learn |
| **Metadata URL 200 yet invalid XML** | Candidate fails parsing | Current valid snapshot not replaced |
| **Metadata XML signature invalid** | XML mutated post-signing | Reject candidate |
| **Unsigned metadata when signing required** | Missing metadata `ds:Signature` | Reject candidate |
| **Metadata signing cert changed without bootstrap** | New metadata signed by untrusted cert | Reject; require approved trust-anchor rollover |
| **Metadata `validUntil` in future** | Signed metadata still valid | Can activate if all other checks pass |
| **Metadata `validUntil` exact now** | Current clock equals expiration | Reject |
| **Metadata `validUntil` past** | Expired document | Reject, never fall back to expired stale copy |
| **`cacheDuration` elapsed, still valid** | Fetch fails while hard validity holds | Last-good per approved policy; alert |
| **`cacheDuration` elapsed, hard expired** | Fetch fails past `validUntil` | Block new logins or safe fallback per standard/trust policy; never use invalid metadata |
| **No `validUntil`** | Metadata signature valid yet no explicit expiry | Bounded max-age policy if org requires |
| **Parent `EntitiesDescriptor` earlier validity** | Child `validUntil` later than parent | Apply effective earlier expiration |
| **Cache never expires** | Caching repository uses default/no expiry | QA FAIL if refresh required; configure TTL |
| **Cache expires yet new payload unapplied** | Loader fetched yet repository stayed stale | QA FAIL; debug cache/activation |
| **North cache refresh fails** | North IdP metadata 5xx | South keeps working if architecture isolates tenants |
| **All caches refresh simultaneously** | 20 pods hit IdP together | Rate/backoff/single-flight and SLA availability |
| **Cache race `N1-v3` vs. `N1-v2`** | Metadata responses arrive out of order | Never resurrect retired key; monotonic accepted generation |
| **One pod stale `N1`-only** | `N2` cutover yet old pod lingers | Detect drift, isolate/fail rollout; no silent bypass |
| **Metadata HTTPS cert wrong SAN** | Fetch redirect/host mismatch | TLS verification fails; no `trustAll` |
| **Metadata SSRF to localhost** | URL swapped to loopback/link-local | Egress allowlist rejects |
| **Oversized metadata XML** | Metadata body exceeds budget | Reject without OOM |
| **Metadata XXE** | External entity/DTD | Reject/fail parse without network fetch |
| **Metadata duplicate `entityID`** | Two entities with same issuer in aggregator | Reject/explicit disambiguation; no first-match |
| **Metadata silently switches issuer** | North URL returns South `entityID` | Quarantine/reject; do not swap tenant |
| **Metadata changes SSO endpoint host** | New host outside approved endpoints | Alert/review; no automatic unsafe switch |
| **Encryption-only `KeyDescriptor`** | New cert is `use=encryption` only | Never use to verify assertion signatures |
| **Two keys both verify North** | North `N1+N2` | PASS when signature/issuer/audience valid |
| **North key sent to South** | South ACS, Response signed `N1` | FAIL even though North trusts `N1` |
| **South key signed with North issuer** | North ACS, signed `S1` | FAIL |
| **North issuer in South registration** | South ACS + North Issuer | FAIL |
| **Valid North key, wrong audience** | Signed `N2`, Audience=SP South | FAIL |
| **Valid North key, wrong recipient** | Signed `N2`, Recipient=ACS South | FAIL |
| **Valid North key, wrong destination** | Signed `N2`, Destination=ACS South | FAIL |
| **Replay North response** | Re-submit identical response | Rejected per request correlation/replay policy |
| **`InResponseTo` from South used on North** | Matching key yet wrong request state | FAIL |
| **IdP-initiated with ambiguous registration** | Shared EntityID and no state | Reject/explicit mapping; never pick arbitrarily |
| **IdP-initiated with unique mapping** | Policy permits, exact ACS/issuer/audience | PASS only if all validations succeed |
| **SP signing rollover unpublished** | SP signs `SN2` while IdP trusts only `SN1` | IdP rejects `AuthnRequest`, staged rollout fails |
| **SP signing overlap** | IdP already trusts `SN1`/`SN2`, SP signs `SN2` | PASS |
| **SP decryption key missing on one pod** | IdP encrypts `DN2`, pod lacks key | Authentication/decryption fails; rollout gate catches |
| **SP decryption old ciphertext in flight** | Pod holds `DN1`/`DN2` per policy | Decrypts cleanly during overlap |
| **Per-registration SP metadata** | `GET /saml2/metadata/north` | Exact North EntityID/ACS/public certs |
| **Global SP metadata** | `GET /saml2/metadata` | `Iterable` repository emits metadata for exact registration set |
| **SP metadata wrong scheme** | Bad reverse proxy forwarded headers, HTTP ACS | QA FAIL; fix trusted headers/canonical URLs |
| **Unsigned SAML after refresh** | Metadata valid yet SAML Response unsigned | FAIL; no signature bypass |
| **Retired key still accepted** | T3 complete yet `N1` still passes on a pod | **Security QA FAIL**; invalidate/incident |
| **Unknown `registrationId`** | Browser POST `/login/saml2/sso/unknown` | No login; deny/failure path |
| **Same email, different issuer** | North/South share `NameID`/email | Never merge local accounts/tenants without approved mapping |
| **North role used in South** | North user sends North group claims to South tenant | Local authorization denies |
| **Metadata download logs** | Fetch/rotation debugging | Log no raw `SAMLResponse`/private keys; fingerprints/versions only |

**Composite PASS criteria:** After publishing `N2` + refresh, **North registration specifically** accepts `N2` across all nodes; `N1` is accepted only within the overlap window and then **rejected**; South continues trusting **only `S1`**; unsigned/invalid/expired metadata never activates; and every Response must still pass XML Signature, issuer/audience/recipient/time/request correlation, and tenant authorization.

## 18. Time-Phased End-to-End Scenario

A practical staging plan:

### Phase P0 — Baseline

1. Inventory IdP EntityIDs, metadata URLs, SP EntityIDs, ACS, SLO, registrations, and certificates.
2. Record SHA-256 **public** certificate checksums/fingerprints and generations; never log private keys.
3. Verify synchronized clocks, metadata fetch TLS truststores, and metadata signature trust policies.
4. Initialize North v1 trusting `N1`, South v1 trusting `S1`.
5. Run SP-initiated login for North and South with one test user each; verify issuer, audience, recipient, and tenant.
6. Collect login success/failure metrics by registration, pod, and key fingerprint label.
7. Run negative tests for unknown registration, wrong tenant, wrong key, and expired assertion.

### Phase P1 — Prepublish N2

1. IdP North publishes certificate `N2` in signed/trusted metadata while still signing `SAMLResponse` with `N1`.
2. SP fetches candidate and verifies XML signature/EntityID/validity/endpoint diffs.
3. Security owner approves `N2` per change record or approved policy.
4. Apply immutable North snapshot `N1+N2`; South remains untouched.
5. Verify all pods report generation v2 and expected fingerprints.
6. `N1` logins from IdP still pass; build an `N2`-signed fixture from staging IdP to prove `N2` is already trusted.
7. Verify unregistered key `NX` is rejected.

### Phase P2 — Actual Cutover

1. IdP North switches active signing key to `N2`.
2. Test North SP-initiated browser SSO with `N2`-signed response matching issuer/audience/recipient.
3. Confirm in-flight `N1` SAML responses still pass if overlap policy allows.
4. Confirm South is uninterrupted; North `N2` is never accepted as South `S1`.
5. Confirm metadata refresh/keys took effect on every pod, not just the test node.
6. Keep canary and security-bounded rollback routes ready; never disable signature verification to rescue login.

### Phase P3 — Retire N1

1. Wait out in-flight Response/`AuthnRequest` lifetimes per policy and confirm no partner still uses `N1`.
2. IdP publishes `N2`-only metadata; SP fetches and activates generation v3.
3. Test that North responses signed by `N1` **are rejected** on every pod while `N2` still passes.
4. Remove `N1` from pinned/static cert files, caches, and deployment manifests when no longer needed.
5. Verify South `S1` still passes, especially when sharing infrastructure/caches.
6. Close change record with audit evidence.
7. If `N1` was compromised, skip overlap grace per incident commander and block all `N1` immediately via trusted emergency revocation.

## 19. Negative Tests on Metadata Sources and Operations

### 19.1. HTTP Metadata Endpoint Returns Redirect

A metadata URL might return 301/302 to another hostname. Never follow redirects blindly. Require:

- Allowlist of exact hostnames/IP networks and permitted redirect targets.
- Distinction between valid proxy/CDN rewrites and DNS rebinding/SSRF.
- Strict HTTPS, TLS SAN/hostname verification, and timeouts.
- Rejection of HTTP downgrades, loopback, link-local, and cloud instance metadata endpoints.
- Metadata signing trust validation after download; never treat a redirect URL as the IdP EntityID.
- Tests confirming browser `?url=...` cannot alter server-side metadata locations.

### 19.2. Cache/Outages and Resiliency

During an outage:

- Cache TTL expires before hard `validUntil`: may serve **trusted, unexpired** last-known-good per stale fallback policy while alerting.
- Hard `validUntil` has passed: never use expired metadata; new logins must fail closed with a sanitized error page and support path.
- New metadata candidate fails signature/issuer: retain last-good if still valid and quarantine the candidate.
- Cache corruption / Redis outage: never rebuild trust config from user input or read keys from `SAMLResponse`.
- Metadata signing key rollover: requires an approved trust-anchor migration. Never set "allow any certificate" or disable metadata signature checks.

### 19.3. Diagnosing Errors at the Right Layer

| Error | Layer | Symptom | Resolution |
| --- | --- | --- | --- |
| `PKIX path building failed` on metadata fetch | HTTPS fetch | JVM does not trust metadata server TLS cert | Fix fetch CA/chain/truststore |
| `metadata signature invalid` | XML metadata trust | Candidate not activated | Check metadata publisher signing cert/trust |
| `metadata past validUntil` | Metadata validity | Candidate/current snapshot expired | Fetch valid copy or fail closed |
| `unknown entityID` | Mapping | Candidate issuer mismatches approved IdP | Fix registration mapping; never auto-reassign |
| `Unknown registrationId` | RP repository | Route/selector does not exist | Check URL/config; never fall back to another tenant |
| `SAML response signature invalid` | OpenSAML | `N2` key not trusted yet / bad fixture | Check active IdP signer and SP accepted key fingerprints |
| `InvalidDestination` / Recipient mismatch | Browser ACS/proxy | Public URL/config mismatch | Fix canonical ACS / trusted `Forwarded` headers |
| `InvalidAudience` | Assertion `Conditions` | SP EntityID differs from registered | Compare RP EntityID vs. IdP audience |
| `InResponseTo mismatch` | Request correlation | Wrong/stale saved request state | Check session, registration, and `AuthnRequest` ID |
| Decrypt error | SP private decryption key | `DN2` not deployed to all nodes | Sync secret aliases/private keys |
| Login fails on only one pod | Cache drift | Divergent key/metadata generations | Measure per-pod versions, gate rollout |
| Login fails only on North | Partner-specific metadata/cache | North IdP outage or key mismatch | Never alter South trust keys |
| IdP rejects `AuthnRequest` | SP signing key | IdP does not know `SN2` yet | Publish SP metadata, confirm at IdP |
| SP metadata endpoint emits wrong ACS | Outbound metadata | Wrong Proxy Host/Proto | Fix trusted headers/static URL, retest |
| `N1` signer still passes post-retirement | Stale cached trust | Old key still trusted on a pod | Safely invalidate, quarantine pod, investigate |
| Same IdP issuer in two regs | Lookup ambiguity | IdP-initiated response picks wrong reg | Require exact routing/request state; avoid arbitrary lookup |
| Metadata refresh storm | Synchronized cache TTL | IdP overload; pods fetch concurrently | Add jitter/backoff/shared validated snapshot |
| North user sees South tenant data | Business authorization | Claims mapped across tenants improperly | Fix local issuer+subject mapping / tenant auth |

**Never fix errors by loosening validation globally.** A valid `N2` Response with the wrong audience must never be accepted "because rotation is in progress." Updated North metadata must never switch `registrationId` to South. An untrusted certificate must never be imported into every registration to cut support tickets.

## 20. Observability and QA Reporting Without Leaking Secrets

Useful telemetry fields:

```text
utcTimestamp
registrationId (bounded allowlist)
approvedIdpEntityId (normalized)
metadataSourceId
metadataGeneration
metadataETag (only if trusted)
metadataFetchedAt
metadataCacheAgeSeconds
metadataValidUntil
metadataSignatureVerified
metadataTrustAnchorFingerprintSha256
keySetFingerprintSha256 (public certificates only)
keyCountAndUsage
activationDecision
refreshFailureReason
activePodOrRegion
samlResponseVerificationDecision
assertionIssuerMatch
audienceAndRecipientMatch
inResponseToCorrelation
localTenantAuthorizationDecision
changeTicketId
traceId
```

Do not log:

```text
Raw SAMLResponse / Base64 XML
Full Assertion and NameID/attributes with personal data
Private key PEM, PKCS#8, keystore password
SAML Response SignatureValue or replayable artifacts
Session cookie / JSESSIONID
AuthnRequest raw query/signature if audit leaks user/session context
Full signed metadata XML dump in ordinary request logs
```

SHA-256 public key fingerprints can compare old vs. new snapshots, but never turn arbitrary issuers/`NameID`s into unbounded-cardinality Prometheus labels. When reporting "refresh successful," specify that **fetched, verified, activated, and observed on pods** are distinct milestones.

### 20.1. Operational Metrics

- `saml_metadata_fetch_total{registration,outcome}`
- `saml_metadata_signature_failures_total{registration}`
- `saml_metadata_validity_seconds{registration}`
- `saml_metadata_age_seconds{registration,pod}`
- `saml_registration_generation{registration,pod}`
- `saml_signer_verification_failures_total{registration,keyCategory}`
- `saml_rollover_old_key_accept_total{registration}` (must drop to 0 after T3)
- `saml_login_failure_total{registration,reason}`
- `saml_audience_recipient_mismatch_total{registration}`
- `saml_metadata_refresh_lag_seconds{registration}`
- `saml_metadata_rollback_rejected_total{registration}`
- `saml_partner_key_change_alert_total{registration}`

**These are suggested metrics**, not built-in Micrometer/Spring names. Instrument the right layers with PII filtering, cardinality bounds, and proper retention.

## 21. Self-Check Questions and Answers

**Q1.** Spring calls `RelyingPartyRegistrations.fromMetadataLocation(url)` and stores it in `InMemoryRelyingPartyRegistrationRepository`. The IdP publishes key `N2` after startup. Does the app automatically know `N2`?

**Answer:** No. The repository holds a static built snapshot; a restart, rebuild, or designed cache/resolver refresh is required. Tests must verify trusted keys actually updated, not just HTTP 200 on the URL fetch.

**Q2.** `cacheDuration` has elapsed, yet `validUntil` is still in the future and the metadata endpoint is down. Must metadata be treated as invalid immediately?

**Answer:** No. `cacheDuration` is when to attempt refresh, distinct from hard validity. Last-known-good may continue per stale policy while still valid; once `validUntil` arrives, stop using it.

**Q3.** IdP North switches to `N2`, yet South's SP metadata accidentally also includes cert `N2`. Can a North Response log into South?

**Answer:** No. That is a trust-config leak. Keys must bind strictly to their IdP/registration; South Responses must pass South's issuer, signature, audience, recipient, correlation, and tenant policy.

**Q4.** Metadata XML contains certificate `N2` inside `KeyDescriptor`. Is that enough to trust `N2` automatically?

**Answer:** No. The metadata document/source must be verified per trust contract (signed metadata/trusted location), `validUntil`/issuer/EntityID/endpoints/key usage, and approvals. Never use a cert inside the metadata to self-validate that same metadata.

**Q5.** The IdP's HTTPS certificate rotates to `TN2` and browser TLS stays green. Did the Response signing cert `N1` also rotate?

**Answer:** No. HTTPS TLS certs and SAML signing certs are separate axes; check `KeyDescriptor`/Response Signatures specifically.

**Q6.** The IdP signs `SAMLResponse` with `N2` before the SP activates `N1+N2` metadata. What is the right behavior?

**Answer:** Reject the `N2`-signed Response per the active trust list. Fix via prepublish/verified refresh before switching—never disable signature verification.

**Q7.** When the SP rotates decryption keys `DN1→DN2`, the IdP does not yet know public `DN2`, yet the SP already deleted `DN1`. What breaks?

**Answer:** The IdP still encrypts with public `DN1`, and the SP lacks private `DN1` to decrypt; logins fail. Right order: SP deploys private `DN2` alongside `DN1`, IdP refreshes SP metadata and switches encryption, and only then does SP retire `DN1`.

**Q8.** Does `registrationId=north` equal `Issuer=https://idp-north.example.net/saml`?

**Answer:** No. One is Spring's internal key; the other is the IdP's SAML EntityID. Dynamic repositories calling `findByEntityId` must pass the real EntityID, not `registrationId` (unless coincidentally equal).

**Q9.** A Response validly signed by `N2` has `AudienceRestriction` targeting SP South and is POSTed to North's ACS. Should it be accepted?

**Answer:** No. XML Signature does not replace audience, recipient, destination, or request correlation checks.

**Q10.** Spring Security publishes updated `/saml2/metadata/north`—can we conclude the IdP already uses the new SP signing key?

**Answer:** No. The IdP must fetch/refresh SP metadata and verify a real `AuthnRequest`. Post-switch E2E tests are mandatory.

**Q11.** Pod A's cache refreshed North `N2`, while pod B still holds only `N1`; 50% of logins fail. Can rollover be declared complete?

**Answer:** No. Verify per-pod convergence, isolate stale nodes, and tune cache/rollout—without broadening trust.

**Q12.** The metadata XML signer changed while the SAML message signer did not. Which trust setting needs updating?

**Answer:** Follow a dedicated **metadata-signing trust-anchor** rotation for the metadata resolver; never guess by swapping the IdP response verification key or TLS truststore.

**Q13.** An IdP-initiated response matches `Issuer` across two registrations with no `InResponseTo`. Should the first registration be picked?

**Answer:** No. Enforce unambiguous routing/ACS/audience policies or reject unsupported unsolicited flows; never pick arbitrarily by list order.

**Q14.** To unit-test metadata rotation, someone edits signed XML post-signing and observes Spring rejecting it; does that prove the new key works?

**Answer:** No. That only tests an invalid signature. Generate/receive a valid `N2`-signed fixture from the test IdP and verify full SAML policy post-refresh.

## 22. Production Checklist for This Test Suite

- [ ] Inventory every `RelyingPartyRegistration`: `registrationId`, expected IdP EntityID, SP EntityID, ACS, SLO, signing/decryption credentials, and tenant mapping.
- [ ] Source metadata locations are fixed/allowlisted; URLs are never taken from browser/`Host`/`RelayState`.
- [ ] HTTPS metadata fetches enforce PKIX/SAN/hostname verification, timeouts, limits, and redirect/SSRF controls; no `trustAll`.
- [ ] XML metadata parser forbids dangerous XXE/DTDs and enforces size/depth/complexity limits.
- [ ] Signed metadata verification or an approved trusted-location policy is defined; trust keys are never taken from unverified metadata.
- [ ] Metadata signature verification credentials are kept distinct from SAML Response verification credentials when policy separates them.
- [ ] Metadata `entityID` is pinned per registration; multi-entity `EntitiesDescriptor` never falls back to first-match.
- [ ] `validUntil` enforces hard expiry; `cacheDuration` schedules refresh attempts without confusing cache staleness with validity.
- [ ] Last-known-good is used only within the hard validity window per risk policy, with alerts.
- [ ] `InMemoryRelyingPartyRegistrationRepository` is never mistaken for hot-reloading metadata.
- [ ] `CachingRelyingPartyRegistrationRepository` has a real TTL/expiry; indefinite default caching does not satisfy refresh requirements.
- [ ] OpenSAML metadata resolver/signature verification is configured for the exact active version per docs/tests without mixing 6.x/7.x APIs.
- [ ] Repository/metadata snapshots publish atomically after verification/approval; live objects are never mutated mid-authentication.
- [ ] Pods/regions report version/fingerprint metrics and meet convergence SLAs with zero cache drift before IdP cutover.
- [ ] IdP signing rollover plans `N1→N1+N2→N2`; prepublish keys before switching and verify `N1` rejects after retirement.
- [ ] Unknown/unapproved SAML signing certificates are never auto-trusted via `KeyInfo` or XML regexes.
- [ ] Metadata signing certificate rollover uses independent trust-anchor bootstrapping; HTTPS/TLS cert rotation is never conflated with SAML signing.
- [ ] SP signing key rollover is confirmed by the IdP before switching; signed `AuthnRequest` is tested with the new key.
- [ ] SP decryption key rollover retains old/new private keys during the valid window, tested with `EncryptedAssertion` across all nodes.
- [ ] Each registration keeps an isolated verification key set; North's key cannot verify South responses.
- [ ] `SAMLResponse` passes XML Signature, issuer, audience, recipient, destination, `InResponseTo`, time, and replay checks before creating `Authentication`.
- [ ] IdP-initiated unsolicited flows are enabled only when routing/issuer/audience are unambiguous and risk-approved.
- [ ] Cross-tenant user identities map via `(issuer, stable subject)`, never email/name alone.
- [ ] Business role/tenant/resource authorization is independent of SAML trust, never granting access on login alone.
- [ ] SP metadata endpoints return exact `entityID`/ACS/public signing/encryption certs per registration with HTTPS schemes.
- [ ] Real signed fixtures exist for `N1`/`N2`/`S1`, including invalid issuer/audience/recipient and signed-metadata negatives.
- [ ] Tests cover cache TTL±1/`validUntil`±1 under controlled clocks, network outages, invalid new metadata, and rollback prevention.
- [ ] Tests cover multi-node stale caches, IdP cutover mid-flight during `AuthnRequest`/Response, clustered sessions, and security-safe rollbacks.
- [ ] Tests cover SAML SLO behavior, metadata endpoint errors, per-registration rotation, and unaffected neighbors.
- [ ] Audits log `metadataGeneration`, verified key fingerprints, activation decisions, refresh lag, and per-pod versions without secrets.
- [ ] On-call runbooks, change approvals, IdP/SP owners, freeze windows, and rollout completion metrics exist.
- [ ] Signature/issuer/audience/time checks are never weakened to make tests pass or rescue logins.
- [ ] After retiring a compromised or obsolete key, **negative old-key rejection** PASSES on all pods—not just one successful login with the new key.

**Conclusion:** Testing the SAML2 lifecycle does not end at an HTTP 200 metadata fetch or a single successful login. **Metadata refresh** requires trusted provenance, time/expiry/atomic activation; **key rotation** requires controlled overlap with multiple certificates scoped by **purpose and registration**; **multi-registration** must isolate issuer, SP EntityID, ACS, keys, session correlation, and tenant authorization. A secure pipeline proves both sides: **legitimate partners keep logging in seamlessly across valid key transitions**, while **forged metadata, unknown keys, revoked old keys, cross-tenant Responses, and invalid SAML conditions are always rejected**.

## 23. References

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, multiple asserting parties, metadata lookup, `CachingRelyingPartyRegistrationRepository`, and routes.
2. [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `AssertingPartyMetadataRepository`, `OpenSaml5AssertingPartyMetadataRepository`, metadata signature validation, `saml2Metadata`.
3. [Spring Security – Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response verification/decryption, assertion validation, registration lookup, and custom providers.
4. [Spring Security 6.5 – CachingRelyingPartyRegistrationRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): caching, loader, and `setCache` semantics.
5. [Spring Security 6.5 – RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): SP/AP pair, EntityIDs, ACS, signing/decryption credentials.
6. [Spring Boot – SAML 2.0 Relying Party Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): multiple registrations and Spring Boot YAML credentials.
7. [Spring Security – SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `AuthnRequest` signing, bindings, and metadata.
8. [OASIS – SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `KeyDescriptor`, `validUntil`/`cacheDuration`.
9. [OASIS – SAML V2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Response, Assertion, Signature, issuer, audience, conditions, and subject confirmation.
10. [OASIS – SAML V2.0 Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect bindings, signature, and `RelayState`.
11. [OASIS – SAML V2.0 Errata05, metadata caching/validity clarification](https://docs.oasis-open.org/security/saml/v2.0/errata05/csprd01/saml-v2.0-errata05-csprd01.html): distinguishing `cacheDuration` and `validUntil`.
12. [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML signatures, trust configuration, and signed-node verification.
13. [OWASP – SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): URL allowlists and external metadata fetches.
14. [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): metadata XML parser hardening.
15. [OWASP – Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS PKIX/trust/hostname verification.
16. [Java 17 – AtomicReference API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): atomic snapshot publication in the Java 17 demo.
