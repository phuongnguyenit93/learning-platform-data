# Monitoring Certificate, Metadata, and Keytab Expiration

> **Module:** Spring Security – federation · **Parent topic:** Deployment and Operations. This Knowledge article explains how to build lifecycle monitoring for trust material in identity federation: **IdP/SP and HTTPS X.509 certificates**, **SAML2 metadata** with its refresh/validity bounds, and **Kerberos keytabs** holding service principal secret keys. The goal is not merely alerting "expiring soon," but ensuring the running configuration actually uses the right key set, keys rotate with overlap, end-to-end tests exist, and recovery runbooks **never disable signature verification or accept forged tickets**.

## 1. Learning Objectives

After this article, you will be able to:

1. Distinguish X.509 `notBefore/notAfter`, SAML metadata `validUntil/cacheDuration`, Kerberos ticket/TGT lifetimes, key age, and **the fact that keytabs have no certificate-style "expiration date" field**.
2. Inventory distinct certificates: IdP signing/verification, SP signing, SP decryption, HTTPS/TLS leaf/chain, and metadata-signing authority certificates.
3. Understand the difference between **SAML explicit-key trust** via metadata/registration and **PKIX certificate path validation**; never claim Spring Security automatically rejects every expired X.509 cert or checks OCSP/CRL by default.
4. Explain SAML metadata `validUntil` as a validity limit and `cacheDuration` as a caching/refresh policy, including attributes on parent/nested EntityDescriptors and metadata that is stale yet not invalid.
5. Distinguish the date metadata was downloaded from the date the **active RelyingPartyRegistration was replaced**; control HTTP/ETag/cache, signatures, issuers, endpoints, and trust anchors.
6. Monitor keytabs via principal/realm/SPN, KVNO, encryption types, file permissions/ownership, KDC sync state, and a GSS/`kvno -k` probe in authorized environments.
7. Understand why `klist -k -t` shows only the entry timestamp rather than when a Kerberos key "expires," and why `klist -K` must never enter logs.
8. Design metrics, 90/60/30/14/7/1-day thresholds, freshness/trust alerts, owner escalation, multi-replica rollouts, and expired-asset handling.
9. Execute SAML rollovers with **old+new verification keys** overlap, signed SP/IdP metadata updates, and verification; handle old SP decryption keys for in-flight ciphertexts.
10. Execute zero-downtime Kerberos key rotation, understanding `kvno` mismatches, KDC-issued tickets still using old keys, and the danger of admins running `ktadd` carelessly.
11. Build a standalone Java 17 program to evaluate certificate/metadata/keytab states with deterministic stdout; use JDK `CertificateFactory` to inspect real certs.
12. Use Spring Boot Actuator/`HealthIndicator` with an appropriate scheduled monitor: keep heavy network fetches out of liveness probes and never expose keys on public health pages.
13. Build a test matrix, signed SAML fixtures/valid Kerberos tickets, network failure scenarios, certificate expiry, clock skew, wrong SPNs, metadata replay, and rollout rollback.
14. Write runbooks to detect, classify, and recover when SAML/Kerberos SSO fails without lowering authentication standards.

**Platform:** Java 17, Spring Boot 3.3.x/Spring Security 6.3.x for illustration; in production choose a supported version and verify exact APIs. `openssl`, `keytool`, and MIT `klist`/`kvno` are investigative tools subject to environment and permissions; never modify a real KDC or keys ad hoc. Domains like `example.org` and dates in this article are examples, not real organizational configs.

## 2. Three Asset Types, Three Different Kinds of "Expiration"

| Asset | Time state to monitor | Other operational signals | Common mistake |
| --- | --- | --- | --- |
| X.509 IdP signing/verification | `notBefore`, `notAfter`; plus lifecycle per CA/trust contract. | SHA-256 fingerprint, key usage/algorithm, metadata source, overlap/revocation. | "Cert not expired ⇒ SAML signature must be valid." |
| X.509 SP signing | Validity dates, when partner stops trusting the key. | Matching private key, IdP knows public cert, signed AuthnRequest canary. | Swapping cert at SP before IdP imports it. |
| X.509 SP decryption | Validity dates and decryption capability per policy. | Readable private key, ciphertexts still using old key. | Deleting old decryption key as soon as new cert is issued. |
| HTTPS/TLS certificate | Leaf/chain notAfter, SAN hostname, key usage, CA path, OCSP/CRL per TLS policy. | Host, reverse proxy, client TLS handshake. | Assuming TLS cert and SAML signing cert are the same. |
| IdP/SP SAML metadata | `validUntil`; `cacheDuration`; last successful fetch/validate/reload. | XML signature trust, EntityID, ACS/SSO/SLO endpoints, KeyDescriptors, key overlap. | Treating expired `cacheDuration` as **invalid** metadata like `validUntil`. |
| Kerberos keytab | **No X.509 notAfter** for keys inside a keytab. | Service principal/realm, KVNO, enctype, file permissions, KDC agreement, successful ticket decryption. | Using keytab entry timestamp or file age as an expiration date. |
| Kerberos TGT/service ticket | Ticket `starttime/endtime/renew-till` if present. | KDC availability, clock skew, realm/SPN, service acceptor result. | Confusing ticket expiry with keytab expiry. |

**Conclusion:** a dashboard reading only `notAfter` from a PEM file is insufficient to protect a federation system. You need an inventory tracking **who issues keys → who uses them → which source publishes them → which process loads them → when partners will rotate**.

### 2.1. Trust Chain Diagram

~~~text
                      Approved IdP
                      /      |      \
           IdP metadata   Signed SAML   HTTPS endpoint
           <KeyDescriptor> Assertion     TLS certificate
                 |            |               |
                 v            v               v
             SP trust      SP verifies    Browser/proxy TLS
             repository    SAML signature  trust path
                 |
             registration reload/rollover
                 |
               SP Session

              KDC/AD realm
                   |
            Kerberos service key
              (principal, kvno)
                   |
        +----------+------------+
        |                       |
   Keytab on node A        Keytab on node B
        |                       |
        +-- GSS accept service tickets
~~~

Which configuration belongs to the IdP, which to the SP, and which to Kerberos must be explicitly documented. An IdP signing certificate may not be the one securing the IdP's HTTPS endpoint. Keytabs do not use X.509 certificates to decrypt standard Kerberos tickets.

## 3. Inventory: Design the Source of Truth Before Setting Alerts

A governance record should include:

| Attribute | Example / meaning |
| --- | --- |
| `asset_id` | Stable internal ID containing no secrets. |
| `asset_type` | `SAML_IDP_VERIFY`, `SAML_SP_SIGN`, `SAML_SP_DECRYPT`, `SAML_METADATA`, `TLS`, `KERBEROS_KEYTAB`. |
| `environment` | prod, staging, DR. |
| `registration_id` | `corp` in Spring `RelyingPartyRegistrationRepository` or IdP entity ID. |
| `owner_team` | IAM/Security/Platform/Partner owner and escalation channel. |
| `dependency` | SP nodes, IdPs, gateways, clients, KDCs. |
| `trust_source` | Signed metadata, pinned certificate, admin-approved file, PKIX policy. |
| `version_ref` | SHA-256 cert fingerprint, ETag/metadata digest, keytab KVNO; never export private keys. |
| `validity` | `notBefore/notAfter` or `validUntil/cacheDuration`, depending on type. |
| `last_observed_at` | UTC timestamp of last check confirming data freshness. |
| `last_refresh_success_at` | Last successful metadata/registration refresh. |
| `last_end_to_end_canary` | Last passing signed SAML login or Kerberos service-ticket decrypt test. |
| `next_rotation_at` | Owner-approved date, **not** inferred from keytab timestamps. |
| `change_id/runbook` | Ticket, rollout plan, rollback, partner, and SLA. |

Each asset can exist in **three versions**: the source-published version, the version loaded in process memory, and the version deployed on nodes. Keeping all three synchronized is the real operational task.

### 3.1. Defining Time Milestones

- `expires_at`: hard validity deadline if the asset type truly expires.
- `refresh_due_at`: when to fetch/refresh—**not** by default a hard expiry.
- `rotation_due_at`: organization-scheduled key rotation, distinct from expiry.
- `last_success_at`: last successful canary/metadata load; must be tracked to catch silently dead jobs.
- `grace_overlap_end_at`: when an old key may be retired after all partners and in-flight artifacts have transitioned.
- `criticality`: impact tier; critical systems require earlier alerts.

## 4. X.509 in Federation: Which Certificate Is Being Measured?

### 4.1. IdP Signing/Verification Certificate

The IdP signs SAML Responses/Assertions with its private key; the SP verifies them using the **public key** configured as a trusted verification credential in verified metadata or registration. Monitoring needs:
- serial/issuer/subject/SAN (if any), public key algorithm, and signature algorithm;
- `notBefore/notAfter` in UTC;
- SHA-256 fingerprint for version reconciliation, **never treating the fingerprint as a secret**;
- location published in IdP metadata `KeyDescriptor use="signing"` or cases where `use` is omitted per SAML profile;
- list of **all** currently trusted verification keys, not only the first key;
- timestamp when metadata/Spring registration updates were deployed;
- real signed-assertion canaries against a test IdP or synthetic authorized login.

**Crucial limitation:** in many SAML deployments, signature verification uses **explicit public key trust** from metadata/registration. A certificate whose `notAfter` has passed **does not guarantee** every SP's signature verification will reject it automatically if the pipeline checks signatures by key alone without running PKIX validity checks. Conversely, an unexpired certificate does not prove metadata/trust/issuer/audience are valid. Policies checking X.509 dates, PKIX paths, and CRL/OCSP revocation must be explicitly designed/implemented and verified on the **actual Spring Security/OpenSAML version**.

### 4.2. SP Signing Certificate

The SP can use a private key to sign AuthnRequests/LogoutRequests, publishing the public certificate in SP metadata for the IdP. Monitor:
- the certificate signing on **each node**, and whether the private key loads cleanly;
- which old/new fingerprints the IdP currently trusts and the cutover deadline;
- whether real AuthnRequests are signed when required by the partner;
- whether SP metadata publishes the right certificate;
- key rotation overlap, never swapping private keys/aliases arbitrarily on a single node;
- keystore/secret permissions and Vault source.

### 4.3. SP Decryption Certificate

The IdP can encrypt Assertions/NameIDs with the SP public encryption certificate; the SP uses its private key to decrypt. When rotating:
1. Publish the **new public encryption key** to the IdP; confirm partner update.
2. Begin receiving ciphertexts encrypted for the new key.
3. Retain the **old private key** only for the transition window needed for in-flight responses.
4. Track last successful decryption by key version.
5. After the transition window closes and no dependencies remain, retire the old private key via an approved process.

Deleting the old decryption key too early can leave validly signed Responses **unable to decrypt**.

### 4.4. HTTPS TLS Certificate Is an Independent Verification Path

Browsers/HTTP clients check TLS chains, hostnames, SANs, expiry, and revocation per policy; SAML signatures check XML signatures/trust at the application layer. An ingress proxy's TLS certificate can expire even while the IdP signing cert remains valid. Alert on both paths separately, including intermediate chains and which certificate the reverse proxy actually serves.

### 4.5. Local Inspection with OpenSSL/JDK

~~~bash
# Inspect public certificate; contains no private key.
openssl x509 \
  -in /etc/federation/idp-signing.pem \
  -noout -dates -subject -issuer -serial -fingerprint -sha256

# An SP public cert used to sign AuthnRequest.
openssl x509 \
  -in /etc/federation/sp-signing.pem \
  -noout -dates -fingerprint -sha256

# Java tool can also display certificate validity dates.
keytool -printcert -file /etc/federation/sp-signing.pem

# TLS live endpoint: inspect the actual certificate served by the proxy.
# Use an approved TLS tool; do not disable hostname verification.
~~~

Compare against the **running certificate**, not only files on disk. A new PEM copied into an image/volume before the Java process reloads can make file-based dashboards show OK while the SP still trusts the old certificate.

**Never** inspect by printing private keys, running `openssl pkey -text` into console/CI logs, or pasting truststores/keytabs into support tickets.

## 5. Monitoring Certificates with Java 17

Standard Java APIs `CertificateFactory` and `X509Certificate` can read public certs and check `getNotBefore()/getNotAfter()` and `checkValidity()`. The complete example below reads a PEM/DER certificate file and displays dates and warning thresholds **without reading private keys**.

### 5.1. `X509ExpiryAudit.java`

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public final class X509ExpiryAudit {

    enum Status { OK, WARN, CRITICAL }

    static Status evaluate(
            X509Certificate cert, Instant now, int warnDays) {
        Instant notBefore = cert.getNotBefore().toInstant();
        Instant notAfter = cert.getNotAfter().toInstant();

        if (now.isBefore(notBefore) || now.isAfter(notAfter)) {
            return Status.CRITICAL;
        }
        if (!now.plus(Duration.ofDays(warnDays))
                .isBefore(notAfter)) {
            return Status.WARN;
        }
        return Status.OK;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java X509ExpiryAudit <public-cert.pem>");
            System.exit(2);
        }

        Path path = Path.of(args[0]);
        try (InputStream in = Files.newInputStream(path)) {
            X509Certificate cert = (X509Certificate)
                CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);

            Instant now = Clock.systemUTC().instant();
            long daysLeft = Math.floorDiv(
                Duration.between(now,
                    cert.getNotAfter().toInstant()).getSeconds(),
                86_400
            );

            System.out.println("notBefore=" +
                cert.getNotBefore().toInstant());
            System.out.println("notAfter=" +
                cert.getNotAfter().toInstant());
            System.out.println("daysLeftFloor=" + daysLeft);
            System.out.println("status=" +
                evaluate(cert, now, 30));

            // Distinction: checkValidity checks only validity dates.
            try {
                cert.checkValidity(Date.from(now));
                System.out.println("x509TimeValidity=PASS");
            } catch (java.security.cert.CertificateException e) {
                System.out.println("x509TimeValidity=FAIL");
            }
        }
    }
}
~~~

### 5.2. Run

~~~bash
javac --release 17 X509ExpiryAudit.java
java X509ExpiryAudit /etc/federation/idp-signing.pem
~~~

Output varies with the **actual certificate and current time**, so do not assume a fixed stdout as guaranteed. Illustrative example (not executed output):

~~~text
notBefore=2026-01-01T00:00:00Z
notAfter=2027-01-01T00:00:00Z
daysLeftFloor=<derived-from-current-time>
status=OK
x509TimeValidity=PASS
~~~

**Limitations:** This sample reads **one** public certificate. It does **not** check PKIX chains, CRL/OCSP, issuer trust, public/private key pairing, certificate usage, SAML metadata signatures, or runtime Spring registrations. Production must check all certificate entries/chains/key versions in each registration/keystore and monitor live runtime state.

### 5.3. NotBefore Also Causes Outages

An issued cert with a future `notBefore` or nodes with skewed clocks can fail PKIX validation against system time. A distant `notAfter` alone does not prove validity. Monitoring needs states:
- `NOT_YET_VALID` if now < notBefore;
- `EXPIRING_SOON` if within the alert window;
- `EXPIRED` if past notAfter;
- `TRUST_NOT_VERIFIED` if only reading a file without PKIX/metadata trust validation;
- `KEY_MISMATCH` if private key and cert public key do not match;
- `RUNTIME_STALE` if the process still uses the old certificate.

Never print raw key material—only fingerprints, public cert metadata, and canary results.

## 6. SAML Metadata: validUntil Differs from cacheDuration

This is one of the most common deployment mistakes.

### 6.1. `validUntil`

In SAML metadata, `validUntil` defines when a metadata instance **ceases to be valid**. OASIS Errata 05 specifies that metadata must be treated as invalid once `validUntil` is reached, and an enclosing parent element with an earlier deadline can shorten effective expiration.

Example:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml"
    validUntil="2026-12-31T00:00:00Z">
  <!-- IDPSSODescriptor, KeyDescriptor, SSO endpoints ... -->
</md:EntityDescriptor>
~~~

**Once effective `validUntil` has passed**, never use that metadata instance as a valid trust source merely because HTTP returned 200 or the cache still holds XML. Fetch/validate fresh metadata and follow fail-closed policy.

If metadata contains a parent `EntitiesDescriptor`:

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    validUntil="2026-11-20T00:00:00Z">
  <md:EntityDescriptor
      entityID="https://idp.example.org/saml"
      validUntil="2026-12-31T00:00:00Z">
      <!-- ... -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

For the inner IdP, the effective deadline cannot simply be taken as Dec 31 if the parent expires Nov 20. Inspection tools must traverse the hierarchy and apply the proper effective validity bound (typically the earliest deadline).

### 6.2. `cacheDuration`

`cacheDuration` indicates **the maximum duration metadata should be cached before attempting a refresh** (with parent precedence per profile); it does not necessarily render metadata invalid once cache age exceeds it. Per OASIS Errata E94, metadata past `cacheDuration` is **stale**; it may remain valid if `validUntil` has not elapsed and policy permits temporary fallback when network refresh fails.

Example:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml"
    cacheDuration="PT6H"
    validUntil="2026-12-31T00:00:00Z">
  <!-- ... -->
</md:EntityDescriptor>
~~~

If fetched at 08:00 UTC, refresh should be attempted per `cacheDuration` around 14:00 UTC. If still unrefreshed at 15:00:
- **`CACHE_STALE`**: alert and retry;
- **do not automatically infer `METADATA_INVALID`** if effective `validUntil` is still in the future;
- **do not use old metadata indefinitely**: define a maximum stale bound based on risk and trust state;
- if `validUntil` has actually elapsed → **invalid**; never use it as a valid trusted configuration.

**Two distinct aspects:** metadata cache freshness ensures timely pickup when the IdP revokes/rolls keys; metadata validity is a hard validity boundary.

### 6.3. When `validUntil` or `cacheDuration` Is Absent

Never assume metadata is permanently trustworthy. Organizations should enforce:
- a local maximum metadata age;
- mandatory signed metadata when source/channel is untrusted;
- expiry/refresh cadence per IdP contract;
- manual approval/trust pinning for static metadata;
- alerts when `validUntil` is missing if policy requires it;
- checks on refresh results and runtime reloads;
- approved fallback/cutover—never blindly trusting arbitrary metadata from a new URL.

### 6.4. XML Duration Is Not Always a Fixed "Number of Days"

`cacheDuration` uses `xs:duration`, which may contain days, hours, or other components per profile. Use a proper XML Schema duration parser anchored to the **metadata fetch timestamp**, avoiding naive regexes that grab digits before `D` while ignoring months or timezones. Keep NTP/UTC clocks synchronized across sources and consumers.

### 6.5. Metadata Status Table

| Scenario | Monitor status | Action |
| --- | --- | --- |
| Signature/trust invalid | `UNTRUSTED`/CRITICAL | Do not promote; investigate source/keys. |
| EntityID/SSO endpoint changed unexpectedly | `DRIFT_REVIEW` | Block auto-promotion per policy; verify change ticket. |
| Effective validUntil elapsed | `INVALID_EXPIRED`/CRITICAL | Stop using expired metadata; restore a valid trusted source. |
| CacheDuration elapsed, validUntil valid | `STALE_REFRESH_DUE`/WARN | Retry refresh and alert per SLA. |
| HTTP 200 fetch, XML parse failed | `FETCHED_NOT_VALIDATED` | Never replace a good snapshot with broken XML. |
| HTTP 304 Not Modified and cache still valid | `UNCHANGED` | Honor cache semantics; never extend trust age indefinitely beyond policy. |
| New metadata trusted, runtime still uses old key | `RUNTIME_STALE`/CRITICAL per deadline | Reload registration and run SAML canary. |
| New metadata has old+new keys | `ROLLOVER_OVERLAP` | Track both fingerprints and verify signed fixtures for each. |
| Missing validUntil | `LOCAL_MAX_AGE_POLICY` | Apply org-defined limit; never treat as never-expire. |

## 7. Metadata Trust: Fetchable Does Not Mean Trustworthy

A metadata URL returning HTTP 200 only proves the server returned bytes. Before loading into `RelyingPartyRegistration`:
1. Fetch metadata from an **allowlisted source URL** with HTTPS/pinned trust as appropriate—never take `metadataUrl` from a browser query.
2. Harden XML parsing against XXE/DTD/entity expansion, enforcing size limits and timeouts.
3. When signed metadata is required: verify the XML signature against an **approved metadata-signing trust anchor outside the new metadata**—never blindly trust a key self-published inside the unverified file itself.
4. Select the right EntityDescriptor/EntityID, IDPSSODescriptor/SPSSODescriptor, SSO/SLO endpoints, supported bindings, and KeyDescriptors.
5. Evaluate effective `validUntil`/`cacheDuration`, signer/endpoint/key changes, and policy.
6. Validate certificate types/algorithms and rollover keys per security contract.
7. Stage the new version, test signing/verifying SAML Response/AuthnRequest, and test logout/decryption if used.
8. Promote atomically across the cluster or via a controlled transition; update `last_applied_at` only upon success.
9. Keep **trusted, non-expired** backup metadata/certificates per policy for rollback—never use signed-but-expired XML.
10. Audit source fingerprints/metadata digests, ETags, and accept/reject reasons without logging full assertions.

**Note:** TLS protects transport but does not replace trust policy when metadata comes over mutable channels or requires signed metadata. Signed XML alone does not authorize trusting any signer; the trust anchor must be governed.

### 7.1. Distinguish Source / Cache / Runtime

~~~text
IdP metadata endpoint
       |
       | fetch, TLS, signed metadata verification
       v
Approved snapshot (digest, validUntil, key set)
       |
       | cacheDuration/refresh policy
       v
RelyingPartyRegistration repository
       |
       | actual reload / cache invalidation
       v
Spring Security runtime verification credentials
       |
       | signed SAML login canary
       v
Observed authentication behavior
~~~

Monitor every arrow. If only `metadata_http_status=200` is checked while the registry retains an old snapshot from a load-once repository, signed Assertions will fail once the IdP rotates keys.

## 8. Spring Security: Managing Runtime RelyingPartyRegistration

Spring Security SP relies on `RelyingPartyRegistrationRepository`. A registration holds SP EntityID/ACS, IdP EntityID/SSO, and signing/decryption/verification credentials.

### 8.1. Static Spring Boot YAML

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "file:/etc/federation/idp-sign-current.pem"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/etc/federation/sp-signing.pem"
~~~

**Illustrative YAML must be checked against the property schema of your exact Boot version.** Key point: IdP certificates for verification and SP private keys for signing/decryption must be governed separately. If a file is replaced on disk, **do not assume** in-memory `RelyingPartyRegistration` instances reload automatically. Verify config/repository lifecycle or run a planned application rollout.

**Never include private key paths in health responses, logs, dashboards, or exported actuator details.**

### 8.2. Load-Once Metadata URLs and Refresh

Spring provides `RelyingPartyRegistrations.fromMetadataLocation(...)` to build registrations from metadata. That does **not** mean every request fetches fresh metadata. Depending on version/config, `InMemoryRelyingPartyRegistrationRepository` is an in-memory snapshot. Newer Spring Security releases document `CachingRelyingPartyRegistrationRepository` and cache-eviction-based refresh; older versions may lack this API or behave differently.

**When designing refresh**, do not merely schedule an hourly fetch cron; ensure you:
- validate trusted XML/keys before replacing configuration;
- verify cache eviction actually invokes the loader;
- track `last_refresh_success_at` and `last_registration_applied_at`;
- monitor **each replica**, not just one node;
- distinguish HTTP 304, fetch failure, parse failure, signature failure, and no-change;
- enforce staleness caps, backoff/jitter, and alerts;
- run a signed login canary through the ACS after reload;
- prevent replacing registrations with data carrying the wrong EntityID/issuer.

### 8.3. Published SP Metadata

Spring Security offers `saml2Metadata(...)` to publish SP metadata (endpoint varies by version, commonly `/saml2/metadata` or a path including `registrationId`). Monitoring must verify:
- public `entityId` is accurate;
- ACS URL has the right public HTTPS hostname/port behind the reverse proxy;
- published signing/encryption certificates match runtime;
- the SP metadata endpoint responds cleanly;
- the IdP partner has imported/synced the new version;
- reverse proxies do not cache XML for too long;
- metadata is signed or unsigned per partner trust contract.

An SP metadata endpoint returning 200 does not prove the partner trusts the new certificate. Obtain partner confirmation or run an end-to-end signed AuthnRequest/SAML Response test.

### 8.4. Explicit-Key Trust vs PKIX

Monitoring `notAfter` has operational value, yet when Spring/OpenSAML verifies SAML signatures via trusted keys, **certificate validity checks may not sit on the same verification path** as TLS/PKIX. Never assume "expired cert => login definitely fails" or "login passes => cert isn't expired." Read the version-specific validator implementation, design a policy for checking certificate dates/revocation, and test real expired/not-yet-valid/untrusted-key cases.

### 8.5. Old/New Certificate Rollover

~~~text
T-60d:  inventory old key fingerprint + expiry/owner
T-30d:  IdP publishes signed metadata with old+new certs
T-14d:  SP validates metadata and trusts both old+new, tests pass
T-7d:   IdP begins signing with new key (coordinated)
T+0:    monitor confirms all SP nodes accept new signatures
T+N:    retire old key after overlap & delayed messages expire
~~~

Milestones are illustrative; adapt to real vendor lifetimes/lifecycles. If an IdP does not support dual `KeyDescriptor`s, plan a clean migration/cutover window with rollback. Never delete an old key merely because the new cert was downloaded before a canary confirms it.

## 9. Kerberos Keytabs: No X.509-Style notAfter

**A keytab is a file holding secret keys for a Kerberos principal** (often SPN `HTTP/portal.example.org@EXAMPLE.ORG`), potentially with multiple entries by KVNO and encryption type. When a browser fetches a service ticket from the KDC, the acceptor/GSS-API application needs the matching key to decrypt/verify the ticket.

### 9.1. Distinguish the Timestamps

| Concept | Has an expiration? | Inspection method |
| --- | --- | --- |
| Keytab entry | No X.509-like `notAfter` field. | Principal, realm, KVNO, enctype, access/rotation status. |
| Keytab entry timestamp | Usually when the record was created/written to the keytab; **not an expiry**. | `klist -k -t` for metadata observation only. |
| KDC principal key | Governed lifecycle/rotation/KVNO; policy may impose key lifetime. | Authoritative KDC admin view or approved monitoring API. |
| Service ticket | Has `starttime/endtime`; tickets expire per KDC policy. | `klist` credentials cache, SPNEGO/GSS test. |
| TGT | Has lifetime/renew-till. | `klist` ticket cache; never infer keytab expiration. |
| Password/account/service principal disabled | Can be locked/deleted/revoked per AD/KDC policy. | Authoritative Directory/KDC status + canary. |

A "newly created" keytab can still have the wrong `KVNO` or wrong SPN. A keytab with an old mtime can still hold the right key if the KDC has not rotated. **File modification date does not replace a decryption test.**

### 9.2. What Must Be Monitored

- `principal` and realm in the keytab match the service hostname/Kerberos SPN clients actually request.
- `KVNO` entries in the keytab are compatible with key versions the KDC may issue and in-flight tickets.
- Encryption types (enctypes) comply with KDC/service/JDK policy—never enable legacy DES/RC4 as a "quick fix."
- File exists and is readable only by the authorized service account, never world-readable.
- Ownership and secret distribution across nodes A/B, with governed manifest/hash versions (protect keytab hashes as sensitive data—never publish them).
- `krb5.conf`, DNS SRV, SPN registration, KDC reachability, and time synchronization.
- Canary using an **authorized test TGT/principal** to acquire a service ticket and attempt decryption via the keytab/acceptor, without printing tickets/keys.
- Alert when KDC KVNO changes before keytab rollout; track supported overlap versions.
- Keytab rotation change tickets and owner acknowledgements; **never infer deadlines from file age**.

### 9.3. MIT Kerberos Commands Without Leaking Keys

~~~bash
# List principal/KVNO; -e displays enctypes.
klist -k -e /run/secrets/http-service.keytab

# -t displays entry timestamps (NOT expiry).
klist -k -t /run/secrets/http-service.keytab

# With KDC network connectivity and an authorized client TGT:
# -k attempts to decrypt the service ticket using the local keytab.
kvno -k /run/secrets/http-service.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG

# For test credential cache only:
klist
~~~

**Never log `klist -K`:** MIT Kerberos explicitly documents that `-K` displays **the actual encryption key values** in the keytab. Never use it in monitors, CI, tickets, or shared terminals. Never attach keytab files to bug reports.

`kvno -k` is a useful check yet requires a valid credential cache/TGT, reachable KDC, and matching service ticket; **failure alone does not prove the keytab is corrupt** if DNS, clocks, networking, or client credentials failed. Separate root causes via diagnostics rather than "fixing" by disabling ticket validation.

### 9.4. Keytab/KVNO Drift

Example:

~~~text
KDC principal: HTTP/portal.example.org@EXAMPLE.ORG
KDC issues tickets with KVNO=7

Node-A keytab:
  principal correct
  enctypes supported
  KVNO=7
  ticket decryption PASS

Node-B keytab:
  principal correct
  only KVNO=6
  ticket decryption FAIL

Effect:
  Some login requests work on Node-A but fail on Node-B,
  creating intermittent 401 Negotiate / GSS failures.
~~~

Some deployments retain old keys/tickets during overlap, so a **KVNO mismatch does not always mean an instant outage**. What matters most is **KDC issuance behavior + acceptor canary + rotation policy**, not mechanically comparing numbers alone. Test each node and ticket version.

### 9.5. Warning on `kadmin`/`ktadd`

MIT Kerberos `kadmin ktadd` can **randomize principal keys** by default when extracting a keytab, bumping the KVNO and breaking service nodes that have not yet received the new key. "Re-running `ktadd` just to grab a fresh keytab" is **not** a read-only operation.

Safe procedure:
1. Open a change ticket, confirm realm/KDC implementation (MIT/AD), admin privileges, and the proper rotation method.
2. Generate/provision the keytab via the approved workflow for that KDC; understand whether the command alters principal passwords/keys and KVNO.
3. Distribute the new keytab via Vault/secret manager with strict file permissions—never over email/chat.
4. Roll out with overlap/rolling restarts as permitted by the KDC, verifying both old and new tickets.
5. Verify `klist -k -e` on every node and run `kvno -k`/GSS acceptor canaries.
6. Once verified stable and old keys are no longer needed, retire old secrets via an approved process.
7. Ensure realistic rollback: reverting to an old keytab does **not** always recover service if the KDC rotated keys and purged the old KVNO; coordinate with KDC/AD admins.

**Never** run `ktadd`, `cpw -randkey`, or principal password resets inside a monitoring job. Monitoring is read-only; rotation must be a controlled action.

## 10. Monitoring Kerberos via Spring Security and GSS

Spring Security Kerberos is typically provided via the separate **Spring Security Kerberos extension** with its own provider/filter, not bundled in `spring-boot-starter-security`. When integrating with Boot 3.x/Jakarta Servlet, confirm actual compatibility and versions.

Common components:
- `SpnegoAuthenticationProcessingFilter` receives `Authorization: Negotiate`;
- `KerberosServiceAuthenticationProvider`/`SunJaasKerberosTicketValidator` verifies the service ticket using the keytab;
- `SpnegoEntryPoint` emits `WWW-Authenticate: Negotiate`;
- GSS-API/JAAS alongside `krb5.conf`, SPN, and KDC.

Monitoring must cover:
- **control plane:** file/keytab/KDC metadata, KVNO, enctypes, NTP;
- **data plane:** an authorized test browser/service client actually acquires a ticket and SPNEGO accept succeeds;
- **local authorization:** the user principal maps to the right local account and policy—never grant roles merely because a ticket was accepted.

Avoid treating a `401 WWW-Authenticate: Negotiate` response as a Kerberos error: it can simply be the **valid initial challenge**. True failures appear when the challenge-response fails, the ticket is wrong, keytab/clocks mismatch, or the account is blocked.

### 10.1. Failures to Distinguish

| Symptom | Likely cause | Check |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` | Duplicate SPN, wrong key, wrong KVNO, service ticket decrypt failed. | SPN/KDC keytab entries, kvno canary, node correlation. |
| `Clock skew too great` | NTP/time drift. | UTC/NTP offset, ticket start/end, KDC time. |
| `Server not found in Kerberos database` | Wrong SPN/realm/DNS. | Service principal registration, DNS, realm mapping. |
| `No credentials provided` | Client browser lacks ticket/TGT or unsupported. | Browser/KDC flow; do not blame keytab automatically. |
| GSS accept fails on only one replica | Keytab/JAAS config/permissions drift. | Per-node versions/ACLs/rollout state. |
| Kerberos ticket accepted yet app returns 403 | Missing local role/tenant/account status. | Authorization audit; never tweak keytab blindly. |
| Keytab KVNO changed yet canary passes | Overlap/old tickets accepted. | Track transition; WARN with owner. |
| Keytab file readable yet canary fails | Wrong key/SPN/enctype/KDC/clock. | Triangulate client & KDC; never disable checks. |

## 11. Operational Monitoring Architecture

### 11.1. Agents and Pipeline

~~~text
Cert/metadata monitor (read-only)
      |       |
      |       +--> parse X509 dates/fingerprints
      |       +--> validate signed metadata, validUntil,
      |            cacheDuration, source fetch, runtime digest
      |
Keytab monitor (privileged, read-only)
      |
      +--> minimal klist -k -e (no -K)
      +--> approved ticket-decrypt canary
      +--> principal/kvno/enctype/status from KDC API
      |
      v
       Normalized signals/metrics
                 |
                 v
       Alert rules + incident routing
                 |
      +----------+-----------+
      |                      |
    IAM/Security          Platform SRE
      |                      |
    IdP keys              Spring runtime,
    metadata              keytab nodes
      \                      /
       \-- change plan/rollover --/
                 |
             Staging canary
                 |
             Prod rollout + readback
~~~

Never let the monitor modify trusted SAML keys or trigger KDC password resets. Monitoring's job is **observing and alerting**. Promoting trust material must go through approved policy and change control.

### 11.2. Suggested Cadences

| Asset / check | Reference cadence | Notes |
| --- | --- | --- |
| X.509 `notAfter` and source fingerprint | Daily and on config change. | Begin escalation ahead of deadline per tier. |
| Live TLS endpoint cert | Hourly or per SLA. | Track ingress serving cert and chain. |
| Metadata HTTP fetch/refresh | Per effective `cacheDuration` with backoff/jitter. | Never hardcode slower than provider contract. |
| Metadata effective `validUntil` | Hourly or every refresh. | Alert ahead of deadline; fail closed when invalid. |
| Applied metadata/runtime digest | After every reload + periodically. | Detect stale caches and unsynced rollouts. |
| Keytab `principal/KVNO/enctype` | After rotation + periodically. | Monitor is read-only. |
| Kerberos ticket acceptance canary | Per SLA and before/after keytab rollover. | Use authorized test principal; avoid brute force. |
| Backup/DR key availability | During every DR drill. | Permissions, secret sync, and decryption capability. |
| NTP offset/KDC health | Continuously per infrastructure. | Clock skew breaks both SAML and Kerberos. |

**Cadences are not framework defaults.** Tune them for metadata cache contracts, service criticality, short cert lifetimes, key rotation cadences, and operational capacity.

## 12. Alert Thresholds and Escalation

### 12.1. Deadline-Based Rule Pattern

| Time to deadline | Example alert level | Recipient / action |
| --- | --- | --- |
| 90 days | INFO / rotation backlog | Owner schedules with IdP/CA/KDC. |
| 60 days | WARN | Confirm coordinator and new cert/key. |
| 30 days | HIGH | Change ticket, staging test, rollout decision. |
| 14 days | HIGH / ESCALATE | Verify overlap and partner acknowledgement. |
| 7 days | CRITICAL pre-expiry | Rollback/incident plan and SRE/IAM on-call ready. |
| 1 day | PAGE | Incident commander and system owner. |
| Past validity deadline | CRITICAL | Fail closed on invalid metadata; recover per runbook. |

**This is an illustrative policy, not a mandatory standard.** An IdP signing cert with a 3-year `notAfter` whose partner unexpectedly rotates keys today is still an incident; monitor **key drift / trust mismatch** alongside deadlines. Keytabs do not have "cert expiring soon": use `rotation_due_at` and canary failures/mismatches instead.

### 12.2. Using Prometheus/Grafana

Suggested metrics, not emitted by Spring Security out of the box:

~~~text
federation_cert_not_after_timestamp_seconds{asset_id,usage,env}
federation_cert_seconds_until_expiry{asset_id,usage,env}
federation_cert_validity_state{asset_id,state}
federation_metadata_valid_until_timestamp_seconds{registration_id}
federation_metadata_refresh_due_timestamp_seconds{registration_id}
federation_metadata_age_seconds{registration_id}
federation_metadata_refresh_success_timestamp_seconds{registration_id}
federation_metadata_applied_timestamp_seconds{registration_id,node_group}
federation_metadata_trust_valid{registration_id}
federation_metadata_runtime_digest_mismatch{registration_id,node_group}
federation_keytab_canary_success{service_id,node_group}
federation_keytab_kvno_mismatch{service_id,node_group}
federation_keytab_principal_expected{service_id,node_group}
federation_keytab_enctype_allowed{service_id,node_group}
federation_keytab_rotation_due_timestamp_seconds{service_id}
federation_saml_login_success_total{registration_id}
federation_saml_signature_error_total{registration_id,reason_class}
federation_kerberos_accept_error_total{service_id,reason_class}
~~~

Labels must stay low-cardinality; never include raw usernames, `sub`/NameID, tokens, keytab contents, private keys, PII-containing certificate subjects, arbitrary IPs, or user-supplied metadata URLs. `asset_id/service_id/registration_id` are stable approved identifiers with bounded cardinality. Never export `keytab KVNO` in a structure containing secrets or key material logs.

### 12.3. Sample Rules

~~~yaml
groups:
  - name: federation-trust
    rules:
      - alert: FederationCertificateExpiring
        expr: federation_cert_seconds_until_expiry < 30 * 24 * 3600
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Federation certificate within 30 days of expiry"

      - alert: FederationMetadataInvalid
        expr: time() >= federation_metadata_valid_until_timestamp_seconds
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "SAML metadata validity expired"

      - alert: KerberosServiceTicketCanaryFailed
        expr: federation_keytab_canary_success == 0
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Kerberos service-ticket validation canary failed"
~~~

**Metric semantics note:** Never emit validity timestamp = 0 for an asset lacking `validUntil`, or the "metadata expired" rule will misfire. Missing `validUntil` needs its own policy metric; monitors missing fresh samples also need `up`/`absent`/last-success checks. Negative `federation_cert_seconds_until_expiry` means already expired, which can have a separate critical rule. Never auto-rotate via Prometheus alerts.

## 13. Spring Boot Actuator/HealthIndicator: Alerting Without Leaking Secrets

`spring-boot-starter-actuator` provides health/info/metrics; you can write a custom `HealthIndicator` backed by a snapshot updated by the monitor. Avoid running heavy XML fetches or KDC password/keytab decrypts **every time Kubernetes hits `/actuator/health/liveness`**. Liveness asks whether the process needs restarting—it must not fail because of an IdP network outage.

### 13.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Boot 3.x projects with SAML SP also require OpenSAML/Shibboleth artifacts from current dependency repositories/versions. Verify BOM and JDK support for your deployed release.

### 13.2. Illustrative HealthIndicator Fragment

~~~java
// SPRING BOOT FRAGMENT: not a standalone Java file.
// FederationSnapshot is updated by a scheduled monitor per policy.
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("federationTrust")
public final class FederationTrustHealthIndicator
        implements HealthIndicator {

    private final FederationSnapshot snapshot;

    public FederationTrustHealthIndicator(
            FederationSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @Override
    public Health health() {
        FederationStatus state = snapshot.status();
        if (state == FederationStatus.CRITICAL) {
            return Health.down()
                .withDetail("status", "critical")
                .build();
        }
        if (state == FederationStatus.WARN) {
            // Health UP here does not automatically clear metric alerts.
            return Health.up()
                .withDetail("status", "renewal_due")
                .build();
        }
        return Health.up()
            .withDetail("status", "ok")
            .build();
    }
}
~~~

**Important:** `FederationSnapshot`/`FederationStatus` above are **types your monitor module must implement**, not Spring Boot built-ins. Health details must never include private keys, sensitive keytab paths, raw cert subjects, or XML metadata. Secure Actuator access and set `management.endpoint.health.show-details=never` or `when-authorized` per policy.

If a "cert expiring in 30 days" warning flips **readiness DOWN**, the orchestrator may evict every replica even while authentication works → a self-inflicted outage. Map **hard failures/inability to authenticate** to readiness/incidents per risk policy; pre-expiry warnings should alert without restarting or evicting nodes.

### 13.3. Scheduled Monitor, Not a Request Handler

~~~text
@Scheduled job / external collector
  -> inspect trusted certs/metadata + keytab canary
  -> update immutable snapshot + metrics + last_success
  -> Actuator read-only exposes summarized status
  -> AlertManager routes to correct owner
~~~

Scheduled jobs must enforce timeouts, jitter/backoff, rate limits, secret access control, and atomic snapshots; when a run fails, emit **UNKNOWN / monitoring gap** rather than repeating OK indefinitely. Even when health reports UP, end-to-end signed SAML login/SPNEGO canaries per provider/node remain essential.

## 14. Standalone Java 17: Policy Monitor with Deterministic Stdout

This example reads no private keys and **does not pretend to verify SAML/Kerberos protocols**. It models evidence collected by a trusted monitor: certificate dates, metadata fetch/validUntil/cacheDuration, keytab usability, and KVNO.

### 14.1. `FederationAssetMonitorDemo.java`

~~~java
import java.time.Duration;
import java.time.Instant;

public final class FederationAssetMonitorDemo {

    enum Status { OK, WARN, CRITICAL, UNKNOWN }

    record CertificateState(
        boolean loaded,
        boolean approvedTrust,
        Instant notBefore,
        Instant notAfter) {}

    record MetadataState(
        boolean signedAndTrusted,
        Instant effectiveValidUntil,
        Instant lastFetchedAt,
        Duration cacheDuration,
        boolean lastRefreshSuccessful) {}

    record KeytabState(
        boolean readable,
        boolean expectedPrincipal,
        boolean allowedEnctype,
        boolean canDecryptServiceTicket,
        int localKvno,
        int observedKdcKvno) {}

    static Status certificate(
            CertificateState c, Instant now) {
        if (!c.loaded()) return Status.UNKNOWN;
        if (!c.approvedTrust()) return Status.CRITICAL;
        if (now.isBefore(c.notBefore())
                || !now.isBefore(c.notAfter())) {
            return Status.CRITICAL;
        }
        if (!now.plus(Duration.ofDays(30))
                .isBefore(c.notAfter())) {
            return Status.WARN;
        }
        return Status.OK;
    }

    static Status metadata(
            MetadataState m, Instant now) {
        if (!m.signedAndTrusted()) {
            return Status.CRITICAL;
        }
        if (m.effectiveValidUntil() != null
                && !now.isBefore(m.effectiveValidUntil())) {
            return Status.CRITICAL;
        }
        if (m.lastFetchedAt() == null) {
            return Status.UNKNOWN;
        }
        if (!m.lastRefreshSuccessful()) {
            return Status.WARN;
        }
        if (m.cacheDuration() != null
                && !now.isBefore(m.lastFetchedAt()
                    .plus(m.cacheDuration()))) {
            // CACHE_STALE != METADATA_INVALID.
            return Status.WARN;
        }
        if (m.effectiveValidUntil() != null
                && !now.plus(Duration.ofDays(7))
                    .isBefore(m.effectiveValidUntil())) {
            return Status.WARN;
        }
        return Status.OK;
    }

    static Status keytab(KeytabState k) {
        if (!k.readable() || !k.expectedPrincipal()
                || !k.allowedEnctype()
                || !k.canDecryptServiceTicket()) {
            return Status.CRITICAL;
        }
        if (k.observedKdcKvno() < 0) {
            return Status.UNKNOWN;
        }
        if (k.localKvno() != k.observedKdcKvno()) {
            return Status.WARN; // canary passed during overlap
        }
        return Status.OK;
    }

    static void print(String name, Status status) {
        System.out.println(name + "=" + status);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Instant started = Instant.parse("2026-01-01T00:00:00Z");

        print("certHealthy", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2027-02-01T00:00:00Z")), now));

        print("certExpiring", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2026-11-21T00:00:00Z")), now));

        print("certExpired", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2026-11-06T00:00:00Z")), now));

        print("certUnknownTrust", certificate(
            new CertificateState(true, false, started,
                Instant.parse("2027-02-01T00:00:00Z")), now));

        print("metadataHealthy", metadata(
            new MetadataState(true,
                Instant.parse("2026-12-07T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("metadataStale", metadata(
            new MetadataState(true,
                Instant.parse("2026-11-30T00:00:00Z"),
                Instant.parse("2026-11-05T00:00:00Z"),
                Duration.ofDays(1), true), now));

        print("metadataExpired", metadata(
            new MetadataState(true,
                Instant.parse("2026-11-06T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("metadataUntrusted", metadata(
            new MetadataState(false,
                Instant.parse("2026-12-07T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("keytabHealthy", keytab(
            new KeytabState(true, true, true, true, 7, 7)));

        print("keytabRollover", keytab(
            new KeytabState(true, true, true, true, 6, 7)));

        print("keytabBroken", keytab(
            new KeytabState(true, true, true, false, 6, 7)));

        print("keytabKdcUnknown", keytab(
            new KeytabState(true, true, true, true, 7, -1)));
    }
}
~~~

### 14.2. Run

~~~bash
javac --release 17 FederationAssetMonitorDemo.java
java FederationAssetMonitorDemo
~~~

**Exact stdout:**

~~~text
certHealthy=OK
certExpiring=WARN
certExpired=CRITICAL
certUnknownTrust=CRITICAL
metadataHealthy=OK
metadataStale=WARN
metadataExpired=CRITICAL
metadataUntrusted=CRITICAL
keytabHealthy=OK
keytabRollover=WARN
keytabBroken=CRITICAL
keytabKdcUnknown=UNKNOWN
~~~

### 14.3. Analysis

- `certExpired` is a hard deadline for the X.509 monitor policy; **never claim Spring SAML verification always rejects** expired certs automatically under explicit-key trust.
- `metadataStale=WARN` because `cacheDuration` elapsed while `validUntil` remains valid; do not merge the two states.
- `metadataExpired=CRITICAL` because effective `validUntil` has passed.
- `metadataUntrusted=CRITICAL` prioritizes trust failures ahead of validity dates.
- `keytabHealthy` and `keytabRollover` have no `notAfter` field; they use canary and KVNO. A mismatch where decryption still passes may represent overlap worth tracking.
- `keytabBroken=CRITICAL` because service ticket decryption failed.
- `keytabKdcUnknown=UNKNOWN` because current KDC evidence is missing even though the local canary passed; never "guess" OK.

Booleans `signedAndTrusted` and `canDecryptServiceTicket` are **simulated fixtures**. Production must obtain them from a real XML signature validator and GSS/Kerberos canary rather than reading browser/user-supplied flags. `Duration.ofDays` in the demo only applies a local policy; XML Schema `cacheDuration` needs a full parser as covered in section 6.

## 15. Testing and Reporting Metadata Expiration

### 15.1. `validUntil` vs `cacheDuration` Scenario

Suppose metadata was fetched at 00:00Z with `cacheDuration=PT6H` and `validUntil` 10 days out:
- 05:00Z: refresh not yet due.
- 07:00Z: cache is stale; job must attempt refresh and report WARN on failure; metadata is not automatically invalid merely because 6 hours passed.
- At `validUntil`: metadata is invalid per spec—stop using it.
- If a parent `EntitiesDescriptor` expires earlier than the child, apply the earlier effective `validUntil`.
- If XML metadata lacks a signature/trust contract, fetching a fresh copy does not make it trustworthy.

### 15.2. Data to Record on Refresh

~~~text
registration_id=corp
source_url_ref=approved-idp-metadata
http_result=200
xml_parse=PASS
metadata_signature=PASS
entity_id=EXPECTED
effective_valid_until=2026-12-31T00:00:00Z
cache_refresh_due_at=2026-11-07T06:00:00Z
signing_keys=old+new
candidate_digest=opaque-sha256
runtime_applied_digest=opaque-sha256
last_applied_at=2026-11-07T00:05:00Z
canary_signed_login=PASS
~~~

This is an example log **containing no private keys/SSO tokens**. When metadata fetch fails, keep a good snapshot only per policy; once the snapshot passes `validUntil`, stop using it. Keep alerts firing when `last_refresh_success_at` goes stale or promotion fails—never hide errors just because current requests still pass.

### 15.3. Metadata Replay/Downgrade Risks

An attacker could try serving an **old signed** metadata copy containing a revoked key if the system omits `validUntil`/version/anti-rollback checks. Enforce:
- signed metadata source trust;
- effective validity and anti-rollback/version rules per profile;
- blocking automatic reversion from a new key back to a compromised old key outside approved overlap;
- auditing key-set diffs, issuer/endpoint changes, and signed metadata validation results;
- ticket/approval for trust anchor changes;
- never trusting a new key published by an unverified document merely because its X.509 metadata dates look valid.

## 16. Zero-Downtime Rollover: SAML Certificates

### 16.1. IdP Rotates Signing Key

~~~text
Phase 1:  Preannounce + owner confirms fingerprints
Phase 2:  IdP metadata publishes old and new verification certs
Phase 3:  SP fetches, validates, promotes both keys
Phase 4:  SP canary accepts both signed fixture versions
Phase 5:  IdP starts signing with new key
Phase 6:  Prod SAML login success monitored per replica
Phase 7:  Old key retired after overlap agreed with partners
~~~

If the IdP signs with the new key **before** the SP trusts the updated metadata, users will hit login failures. Confirm every node applied the new key and test before switching.

### 16.2. SP Rotates Signing Key

- SP generates a new private/public key pair via Vault/PKI; protect the private key.
- SP publishes the new public certificate via metadata; IdP imports/verifies it.
- During overlap, IdP trusts both old+new SP signing certificates as supported by the provider.
- SP switches AuthnRequest/LogoutRequest signing to the new key once the partner confirms.
- Monitoring verifies actual signed AuthnRequests, not merely SP XML metadata.
- Old key is retired per agreement, never deleted before rollback windows close.

### 16.3. SP Rotates Decryption Key

- IdP encrypts to the new SP public key after publication/approval.
- SP retains the old private key for in-flight responses until expiry, per policy.
- Test fixtures encrypted with old and new certs to ensure the decryption path works.
- Monitor failures by encryption key fingerprint/registration without logging raw decrypted XML.

### 16.4. "Early" Certificate Replacement Without Key Change

An IdP may issue a new cert sharing the same public key with updated dates, or a brand-new key pair. Never rely solely on `subject CN`/`serial` to infer key rotation; compare SHA-256 cert fingerprints and **public key identifiers** per policy. A cert with a newer `notAfter` is not automatically trusted if its signer/metadata source is unapproved.

## 17. Keytab/Kerberos Rollover Across Multiple Replicas

### 17.1. Steps

1. Inventory service principal, KDC realm, current KVNO/enctypes, keytab versions on A/B/DR, and canary status.
2. Finalize the rotation plan with KDC/AD admins, key management policy, target enctypes, and whether old keys/tickets stay valid.
3. Create the new service key/keytab inside an authorized workflow; **never run `ktadd` ad hoc**.
4. Distribute secrets via Vault/service identity, verify owner/group/file mode, and never log keytab hashes publicly.
5. Update nodes sequentially per plan to prevent split-brain; verify the GSS acceptor truly uses the new file after restart/reload.
6. Test new KDC tickets and still-valid old tickets in an authorized environment; verify `kvno -k` alongside the app SPNEGO canary.
7. Confirm HTTP 401 Negotiate challenge/response succeeds and local authorization is unaffected.
8. Watch GSS errors and credential cache/ticket lifetimes during overlap.
9. Once KDC/IdP and all replicas are confirmed stable, retire old keys/tickets per policy.
10. For DR regions, update/canary keytabs on schedule with owner acknowledgement.
11. Store secret rotation audit/rollback plans **without** storing keytab contents in logs/tickets.
12. If rollback requires the KDC to restore an old KVNO, only authorized admins may do so—never copy an old keytab back expecting the KDC to issue old keys.

### 17.2. Specific Risks

- KDC bumps KVNO before rollout while production nodes hold only the old key → login failures.
- Node A restarts with the new key while Node B still uses old JAAS cached credentials → intermittent failures behind the load balancer.
- Wrong `HTTP/host@REALM` principal bound because proxy hostname differs from backend.
- Encryption types incompatible with Java runtime/KDC security policy.
- Excessive clock skew causes tickets to be rejected despite a valid keytab.
- Overly broad keytab permissions → risk of exposing long-term service key; a security incident, not just a rotation ticket.
- Keytab mtime changes from backup restore while key version stayed the same → false alarm.
- Canary runs on a single node and reports overall green while remaining nodes fail.

## 18. Tiering Alerts to Avoid Self-Inflicted Outages

### 18.1. Distinguish States

| State | Example | Response |
| --- | --- | --- |
| `OK` | Cert well within validity, metadata fresh/trusted, canary passes. | Normal monitoring. |
| `WARN` | Cert has 20 days left, metadata cache stale, KVNO mismatch yet canary passes. | File ticket and watch closely; do not take service down. |
| `CRITICAL` | Metadata `validUntil` expired; SAML signature untrusted; Kerberos decrypt canary fails. | Incident / fail closed on the trust path; recover. |
| `UNKNOWN` | Collector stopped reporting, KDC unreachable, runtime state undetermined. | Alert monitoring gap; probe carefully. |
| `IN_MAINTENANCE` | Approved rotation window with old+new overlap. | Never suppress hard auth failures/compromise; only tune alert noise. |
| `COMPROMISED` | Private key/keytab exposed. | Emergency revoke/rotate, incident response, forensics. |

**Never turn a "cert has 30 days left" warning into Spring readiness DOWN** while the SP still works. Conversely, invalid/untrusted metadata must never show "green" merely because a cache exists. Liveness probes should reflect process liveness; readiness can reflect ability to serve yet must measure true impact without taking down the entire cluster over a transient dependency blip.

### 18.2. Alert Ownership

- IAM/IdP owner owns IdP signing certs and metadata publication.
- Platform/SP owner owns runtime registrations, SP signing/decrypt keys, reloads, consumer metadata, and canaries.
- Security/PKI owner owns trust anchors, PKIX policies, and revoked/compromised keys.
- Kerberos/AD owner owns service principals, KDC keys/KVNOs, and enctypes.
- SRE owner owns alerting, deployments, node drift, dashboards, and incident response.
- Business owner approves SLAs, maintenance windows, and authorized fallback rules.

Every alert must include a **runbook link, asset ID, severity, deadline, owner, last-success/last-apply, and escalation timer**, not just a vague "cert expired" email.

## 19. QA Test Suite

| ID | Scenario | Expected result |
| --- | --- | --- |
| O01 | IdP signing X.509 has >90 days left. | OK; fingerprint/owner clear. |
| O02 | IdP signing cert has 30 days left. | WARN/escalation per threshold. |
| O03 | IdP cert is past `notAfter`. | Monitor CRITICAL; check runtime explicit-key vs PKIX policy. |
| O04 | Cert has future `notBefore`. | `NOT_YET_VALID`; do not check `notAfter` alone. |
| O05 | SP signing public cert rotated before IdP imported it. | Signed AuthnRequest canary fails, alert fires. |
| O06 | SP decryption key rotated while old ciphertexts still arrive. | Old key retained during overlap; decrypt canary passes. |
| O07 | TLS leaf cert expired while SAML cert valid. | Separate TLS alert; not conflated. |
| O08 | Intermediate CA expired/revoked while leaf valid. | PKIX/TLS chain failure detected per policy. |
| O09 | SAML explicit-key trust accepts expired cert in implementation. | QA documents exact behavior; never assume PKIX. |
| O10 | CRL/OCSP unavailable. | Handled per revocation policy; never falsely claim checked. |
| O11 | IdP metadata has `validUntil` 5 days away. | Alert per deadline. |
| O12 | IdP metadata `validUntil` has passed. | INVALID; stale invalid instance not used. |
| O13 | Metadata `cacheDuration` elapsed while `validUntil` valid. | STALE/WARN, retry refresh; not mistaken for invalid. |
| O14 | Parent `EntitiesDescriptor` expires before child. | Effective expiry picks the proper parent deadline. |
| O15 | Metadata has no `validUntil`. | Local max-age policy/alert when required. |
| O16 | Metadata has no `cacheDuration`. | Apply configured refresh cadence; never cache forever. |
| O17 | Metadata signed by untrusted key. | Rejected, not promoted. |
| O18 | Metadata XML contains XXE/oversized entity. | Parser rejects per policy. |
| O19 | Metadata HTTP 200 yet XML unparseable. | Keep trusted snapshot within bounds; report error. |
| O20 | Metadata HTTP 304. | Proper refresh semantics; trust not extended indefinitely. |
| O21 | New metadata unexpectedly changes EntityID/SSO endpoint. | Quarantined/reviewed, never auto-promoted. |
| O22 | New metadata has old+new verification keys. | Both validated/accepted per policy. |
| O23 | IdP starts signing with new key before SP trusts it. | Failures detected; rollback/coordinated cutover. |
| O24 | SP runtime on node B holds old metadata. | Runtime digest mismatch alert. |
| O25 | SP metadata public ACS URL wrong behind proxy. | Detects wrong hostname/HTTPS/port. |
| O26 | Cert updated on disk while Spring registration remains stale. | Detects runtime stale; controlled reload. |
| O27 | Metadata refresh job stopped running for 24h. | Monitoring gap/freshness alert. |
| O28 | Keytab mtime is one year old yet service ticket decrypt passes. | Do not conclude keytab is expired. |
| O29 | `klist -k -t` timestamp is old. | Never interpret as an expiration date. |
| O30 | Script accidentally runs `klist -K`. | Security QA FAIL; never log secret keys. |
| O31 | Keytab has wrong HTTP principal/realm. | Detects principal mismatch/canary failure. |
| O32 | Keytab KVNO=6, KDC issues 7, canary fails. | CRITICAL; never disable Kerberos validation. |
| O33 | KVNO mismatch yet overlap canary passes. | WARN, watch window; no false down. |
| O34 | Keytab contains only disallowed enctype. | Alert/security review; never enable DES/RC4 arbitrarily. |
| O35 | Keytab is world-readable. | Security incident / fix permissions. |
| O36 | Keytab file exists yet process lacks read access. | Canary fails / permission alert. |
| O37 | Only node A got new key while node B keeps old. | Per-node alert; complete rollout. |
| O38 | KDC offline causes `kvno -k` failure. | Classify as network/KDC failure, not broken keytab. |
| O39 | Clock skew causes GSS to reject ticket. | Separate NTP/time alert. |
| O40 | Duplicate SPN/host mismatch behind load balancer. | Diagnose SPN registration, not SAML cert. |
| O41 | Admin runs `ktadd` rotating KDC KVNO unexpectedly. | Change/incident alert; controlled rollout. |
| O42 | Old keytab rollback after KDC key reset. | Do not rely on file copy alone; coordinate with KDC. |
| O43 | Kerberos ticket valid yet local app role missing. | 403 authorization; do not blame keytab. |
| O44 | Cert far from expiry yet IdP key changed today. | Key drift/canary alert despite distant deadline. |
| O45 | Signed SAML Assertion has wrong audience/recipient. | Rejected; independent of cert expiry check alone. |
| O46 | IdP Response signed by revoked key. | Trust policy rejects/alerts; no stale metadata. |
| O47 | Metadata fetch succeeds yet SAML login canary fails. | Runtime/auth-path incident; do not mark green by HTTP. |
| O48 | Spring readiness DOWN when cert has 30 days left. | Test catches policy causing self-inflicted outage. |
| O49 | Spring `/actuator/health` leaks keytab path/private key. | QA FAIL; restrict details/secure endpoint. |
| O50 | Browser receives initial 401 Negotiate challenge. | Not counted as error until handshake fails. |
| O51 | Certificate expiry alerts fully suppressed during maintenance. | Hard failures/compromise must still alert. |
| O52 | IdP signing key compromised. | Emergency revoke, metadata update, session/security review. |
| O53 | SP decryption key leaked. | Emergency rotation, forensics, protect in-flight data. |
| O54 | Keytab/service account secret leaked. | KDC/AD coordinated rotation, ticket/incident response. |
| O55 | Expired metadata retained in cache. | Reject invalid instance; alert, never use indefinitely. |
| O56 | New metadata has wrong EntityID yet distant validUntil. | Reject trust/identity mismatch. |
| O57 | Prometheus collector stops emitting samples. | UNKNOWN/no-data alert; never hold last green forever. |
| O58 | DR site keytab/metadata out of sync after rotation. | DR readiness test fails; rollout/verification. |
| O59 | TLS reverse proxy cert new while backend trust old. | Distinguish TLS vs SAML trust and runbooks. |
| O60 | Upgrade Spring Security/IdP/KDC version. | Regression test trust, metadata refresh, and keytab canary. |

**In row O41, controlled rollout follows change management; never let a monitor "auto-rotate keys" on its own.**

### 19.1. Lab A — Certificates and Metadata

1. Create real public X.509 test certificates (never production keys) with near and far `notAfter` dates.
2. Run `X509ExpiryAudit` and confirm states.
3. Build test SAML metadata with distinct `validUntil` and `cacheDuration`, testing stale vs invalid.
4. Set a parent `EntitiesDescriptor` with an earlier deadline and confirm the effective deadline.
5. Simulate an HTTP fetch failure with a still-valid snapshot; confirm retry/alerting per policy.
6. Test metadata signed by trusted/untrusted keys and rotated old+new `KeyDescriptor`s.
7. Verify Spring `RelyingPartyRegistrationRepository` applied the new keys rather than checking metadata URL HTTP 200 alone.

### 19.2. Lab B — Keytab Without Leaking Secrets

1. Use a test Kerberos realm/AD service account and synthetic service principal.
2. Verify `klist -k -e` shows expected realm/KVNO/enctypes; **never use `-K`**.
3. With an authorized test TGT, run `kvno -k` and a GSS acceptor canary.
4. Leave node B on an un-updated keytab to observe intermittent login failures.
5. Simulate a KVNO transition with overlap, raising WARN while the canary passes.
6. Test wrong SPN, missing keytab, permission denied, KDC outage, and clock skew.
7. Verify the application never logs raw Negotiate tickets/keys.

### 19.3. Lab C — Rollback and Disaster Recovery

1. Test signed SAML Responses under old/new IdP certs during overlap.
2. Test SP decryption of Assertions encrypted under old/new private keys.
3. Check staging → prod → DR version manifests and owner signoff.
4. Test deployment rollback after the metadata issuer rotated keys, ensuring rollback does not break trust.
5. Revoke a key from the trust list and confirm fixtures signed by it are no longer accepted outside policy.
6. Test secret-compromise incident procedures, not only natural expiration.

## 20. Incident-Specific Runbooks

### 20.1. IdP Signing Certificate Expiring Soon

1. Identify the asset, IdP entityID/registration, SHA-256 fingerprint, `notAfter`, and all consumers.
2. Contact the IdP owner for rotation schedule, new cert, and signed metadata/trust announcement.
3. Validate source/trust and expected issuer; never load certs from unverified attachments.
4. Stage old+new verification keys and test signed fixtures in staging.
5. Deploy/update `RelyingPartyRegistration` across every node and verify runtime versions.
6. Wait for the IdP to switch signing to the new key; monitor login success and signature errors.
7. Close overlap and retire the old key per change ticket.
8. If already expired and policy forbids use, **do not bypass** validation; recover using approved trust material and conditional rollback.

### 20.2. Metadata Invalid or Stale

1. Compare `validUntil`/`cacheDuration` and UTC fetch time, including parent hierarchy.
2. If stale yet still valid: retry fetch with backoff/jitter and alert per max-stale policy.
3. If invalid/expired: never promote or keep using the invalid metadata instance; obtain a fresh trusted one.
4. Inspect TLS, DNS, HTTP, XML parsing, signature, issuer, endpoints, and KeyDescriptors.
5. Check which version the Spring repository/cache currently holds and whether reload succeeded.
6. Run canaries: AuthnRequest → IdP → signed SAMLResponse → ACS and SP SLO if used.
7. Separate partner outage/metadata endpoint errors from local config failures.
8. Never disable metadata signature checks or let clients pass `metadataUrl` via query parameters.

### 20.3. Kerberos SPNEGO Failure from Keytab/KVNO

1. Identify the node, principal/realm, browser-requested SPN, and UTC error timestamp.
2. Distinguish the initial 401 challenge from handshake/decryption failure; collect `reason_class` from redacted GSS/JAAS logs.
3. Run `klist -k -e` to inspect entries without printing keys; compare KDC KVNO/enctype via an authorized view.
4. Check NTP, DNS, KDC, duplicate SPNs, file permissions, and the right service account.
5. Using an approved test principal/TGT, run `kvno -k` and a live SPNEGO canary.
6. On key mismatch, coordinate with Kerberos admins to roll out a new keytab per change plan; avoid ad-hoc `ktadd`.
7. Verify all replicas + DR, login success, and local account/tenant permissions.
8. If the keytab leaked, escalate to incident response and rotate/revoke via the KDC process.
9. Never fall back to NTLM/Basic or "accept any Negotiate token" to work around failures.
10. Store an incident summary with key versions/owners/status containing no secrets.

### 20.4. Two Problems Occurring Simultaneously

Cert expiry, metadata refresh failure, and keytab canary failure can originate in different systems. Classify first:
- Is SAML ACS rejecting signatures or is the browser failing the TLS handshake?
- Is SPNEGO GSS failing ticket decryption or is SAML signing broken?
- Is metadata updated at the source while runtime failed to reload?
- Is it node-specific config drift or a full IdP/KDC outage?
- Is the local account disabled / returning 403 despite valid authentication?

A single aggregate `sso_login_failed` alert is insufficient; separate `reason_class` so you do not swap the wrong cert or keytab. Never use "disable all checks" as a rollback plan.

## 21. Common Mistakes

| Misconception | Why it is wrong | Replace with |
| --- | --- | --- |
| "Keytabs have an expiration date like certs." | Keytab entries lack X.509 `notAfter`. | Rotation due + KVNO/enctype/decrypt canary. |
| "`klist -k -t` shows when the keytab expires." | `-t` shows the entry timestamp. | Admin policy/rotation records and canaries. |
| "Running `klist -K` to debug is harmless." | `-K` prints secret key values. | `klist -k -e`; never log key material. |
| "When metadata `cacheDuration` elapses, validity ends." | Stale cache is not automatically invalid. | Separate `refresh_due_at` and `validUntil`. |
| "Keep using old cache indefinitely past `validUntil`." | Metadata instance is invalid per OASIS. | Fetch fresh signed trusted metadata / fail closed. |
| "HTTP 200 metadata = trust OK." | XML may have wrong issuer/key/signature. | Validate source/signature/EntityID/version. |
| "Updating PEM on disk makes Spring load it immediately." | Registration may be an in-memory snapshot. | Reload/promotion check + canary. |
| "Unexpired cert means the signature is valid." | Trust key/issuer/audience/algorithm may be wrong. | Protocol validation + approved trust. |
| "Every SAML SP rejects expired certs by default." | Explicit-key trust differs from PKIX validity. | Version-specific tests + explicit policy. |
| "Spring always checks OCSP/CRL automatically." | Depends on implementation/trust model. | Define revocation policy and test live. |
| "Use the same TLS cert for SAML signing." | Distinct purposes and trust boundaries. | Separate inventory/keys/permissions. |
| "KVNO mismatch guarantees an immediate outage." | Overlap/retained keys may still accept. | Correlate canary, KDC policy, and node state. |
| "Re-run `kadmin ktadd` just to fetch the file." | Can randomize keys and bump KVNO. | Controlled KDC/AD key rotation process. |
| "Putting keytabs in Git/images is fine if encrypted." | Long-term service secrets still leak via distribution. | Vault/secret mounts/permissions. |
| "SP public metadata has the new cert so IdP has it." | Partner must import/refresh it. | Partner signoff + signed request canary. |
| "Actuator warning should kill all pods." | Self-induced outage. | Alert pre-expiry; readiness reflects real capability. |
| "On KDC outage, skip ticket validation." | Opens impersonation vulnerabilities. | Approved fallback + fail-closed policy. |
| "One node's canary passed so the cluster is healthy." | Keytab/metadata drift across replicas. | Per-node/region canaries and digests. |
| "X.509 expiry equals SAML metadata expiry." | Two independent fields. | Monitor both cert dates and metadata validity. |

## 22. Production Checklist

- [ ] Complete inventory of IdP verify, SP signing, SP decryption, TLS leaf/chain, metadata, and Kerberos keytabs.
- [ ] Every asset has owner, environment, entityID/registrationId, trust source, fingerprint/digest, timeline, and runbook.
- [ ] X.509 `notBefore/notAfter` monitored for **every active certificate**, not only the first file.
- [ ] Explicit policy on SAML explicit-key trust vs PKIX/CRL/OCSP, never assumed from defaults.
- [ ] Metadata `validUntil`, `cacheDuration`, parent precedence, and local max-age handled properly.
- [ ] Metadata signature/trust source, XML parsing security, and EntityID/endpoint diffs verified.
- [ ] Alerts distinguish `CACHE_STALE`, `METADATA_INVALID`, `UNTRUSTED`, and `RUNTIME_STALE`.
- [ ] Monitors track both metadata source fetch success and Spring runtime `RelyingPartyRegistration` applied versions.
- [ ] Spring registration reload tested for your framework/version; never assume file edits auto-reload.
- [ ] Signed SAML login/AuthnRequest/ACS/logout canaries use approved test fixtures and trust keys.
- [ ] IdP signing rollover includes old+new verification overlap and partner signoff.
- [ ] SP signing rollover has IdP confirmation and tests live signed requests.
- [ ] SP decryption rollover retains old private key until the in-flight window closes.
- [ ] Live TLS endpoint cert/chain monitored independently of SAML certs.
- [ ] Keytab principal/realm/SPN, KVNO, enctype, ACL, and runtime secret version checked per node.
- [ ] **No** "keytab notAfter" metric; use rotation due/KDC policy/canaries instead.
- [ ] `klist -K` barred from monitors/CI/logs; keytabs never committed or attached to tickets.
- [ ] `kvno -k`/GSS acceptor canary runs with an authorized test principal/credential.
- [ ] No destructive `kadmin ktadd`/password resets inside monitor jobs.
- [ ] Alerts fire when KDC KVNO changes before nodes roll out, accounting for overlap/canaries.
- [ ] NTP/clock skew, DNS, KDC outages, and SPN mismatches have separate diagnostics.
- [ ] Tiered 90/60/30/14/7/1-day thresholds and owner escalation prevent silent expiry.
- [ ] Stale collector/`UNKNOWN` alerts exist rather than holding last-known OK forever.
- [ ] Health/Actuator leaks no secrets; liveness does not depend directly on IdP latency.
- [ ] Readiness policy tested to avoid evicting the entire cluster merely because a cert is expiring soon.
- [ ] DR/secondary regions keep metadata/certs/keytabs/secrets synced and canaried.
- [ ] Change/incident plans include rollback constraints, per-node readback, and partner communication.
- [ ] Fail closed when metadata is invalid/untrusted; never disable signature/SPNEGO verification to work around outages.
- [ ] Tests O01–O60 or equivalent coverage run in staging and on version upgrades.

## Remember

> **X.509 certificates have validity dates, SAML metadata has validity and refresh bounds, and keytabs hold Kerberos service keys without X.509-style expiration dates.** To operate safely, monitor **both deadlines and trust/actual runtime state**: certificate fingerprints, metadata `validUntil`/`cacheDuration` plus refresh/applied digests, and keytab principal/KVNO/enctypes alongside ticket-decrypt canaries. Always roll over on a plan and test end-to-end; never let "metadata fetched" or "keytab file exists" stand in for proof that live SSO remains secure.

### Official Documentation and References

- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, signing/decryption/verification credentials, and metadata handling.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parsing IdP metadata and publishing SP metadata.
- [Spring Boot — SAML2 Relying Party](https://docs.spring.io/spring-boot/reference/security/saml2.html): properties and configuring IdP/SP credentials.
- [Spring Boot Actuator — Endpoints/Health Indicators](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `HealthIndicator`, readiness/liveness, and controlling endpoint details.
- [OASIS SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `EntitiesDescriptor`, `KeyDescriptor`, `validUntil`, `cacheDuration`.
- [OASIS SAML V2.0 Errata 05, E94](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): distinguishing metadata cache staleness from metadata validity.
- [OASIS Metadata Interoperability Profile](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-cd-01.html): metadata trust, signed metadata, expiry, and rollover.
- [RFC 5280 — Internet X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `notBefore`/`notAfter`, PKIX path validation, and revocation.
- [MIT Kerberos — klist](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/klist.html): `-k` list keytab, `-e` enctypes, `-t` timestamps, `-K` prints secret key values.
- [MIT Kerberos — kvno](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/kvno.html): service ticket KVNO and `-k` keytab decryption test.
- [MIT Kerberos — kadmin](https://web.mit.edu/KERBEROS/krb5-1.21/doc/admin/admin_commands/kadmin_local.html): `ktadd` and its effect on principal keys/rotation.
- [Spring Security Kerberos Extension](https://github.com/spring-projects/spring-security-kerberos): SPNEGO provider/filter and keytab integration; verify Jakarta compatibility per version.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication failure handling and defense-in-depth.
