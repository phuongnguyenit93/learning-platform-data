# Handling Expired, Malformed SAML2 Metadata or IdP Outages

**SAML 2.0 metadata** is the dataset enabling a Service Provider (SP, called *Relying Party* in Spring Security) to identify and trust the right Identity Provider (IdP, or *Asserting Party*): `entityID`, SSO/SLO endpoints, bindings, signing/encryption certificates, and protocol policies. When metadata expires, arrives malformed, or fails to download due to an IdP outage, the application must **isolate the fault and respond according to its current trust state**. Never resolve it by skipping signature verification, accepting arbitrary issuers, or continuing to use expired metadata indiscriminately.

Three core messages:

1. **Cache expiration** and **metadata expiration** are two distinct states: `cacheDuration` generally indicates when to re-fetch; `validUntil` enforces a strict validity limit.
2. **An unreachable metadata endpoint** does not necessarily mean **IdP SSO is down**; conversely, IdP logins can fail even while the SP holds valid metadata.
3. **Last known good (LKG) metadata** may be used only within permitted bounds: source/signature/structure verified, matching the right IdP, and still valid per specification and policy. A copy whose `validUntil` has passed **must not continue to be used**.

This lesson focuses on **Spring Security SAML2 Web Browser SSO**, safe refresh design, failure testing, and recovery. Code examples illustrate policy; actual XML, signature, and TLS verification must rely on an appropriate SAML library.

## 1. What Is SAML2 Metadata Used For?

An IdP can publish a SAML 2.0 Metadata XML document. The SP consumes that document to initialize or update `RelyingPartyRegistration` and `AssertingPartyMetadata` configurations.

Key elements to recognize:

| XML Component | Typical Meaning | Risk When Wrong |
| --- | --- | --- |
| `md:EntityDescriptor` | Describes one SAML entity with `entityID` | Misidentifying the issuing system |
| `md:EntitiesDescriptor` | Aggregates multiple entities, possibly nested | Selecting the wrong entity or ignoring inheritance limits |
| `md:IDPSSODescriptor` | IdP role for SSO; describes protocol and services | SP cannot locate valid login configuration |
| `md:SingleSignOnService` | Endpoint with bindings such as HTTP-Redirect/HTTP-POST | Redirecting to a wrong URL or unsupported binding |
| `md:KeyDescriptor` | Key/certificate info by `signing`/`encryption` usage | Unable to verify signatures or using the wrong key |
| `validUntil` | Timestamp when metadata document/element expires | Relying on trust info beyond spec-allowed lifetime |
| `cacheDuration` | Duration to cache before attempting refresh | Retaining stale config too long after IdP changes |

**Do not confuse IdP metadata with SP metadata:** IdP metadata describes the authenticating side Spring Security will trust; SP metadata describes your application, entity ID, and ACS for registration at the IdP. `http.saml2Metadata(...)` publishes **SP metadata**; it cannot automatically fix broken IdP metadata during an IdP outage.

**Do not confuse metadata with SAML Responses:** metadata supplies trust configuration; responses/assertions arrive after the IdP authenticates a user. Every response must still be verified independently for issuer, signature, audience, recipient, timestamps, and required constraints.

## 2. The Difference Between validUntil and cacheDuration

Suppose an IdP issues metadata at 08:00 UTC:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/saml"
    validUntil="2026-11-08T00:00:00Z"
    cacheDuration="PT4H">
    <!-- Valid IDPSSODescriptor, SSO endpoints, and keys -->
</md:EntityDescriptor>
~~~

This is an **XML snippet for reading attributes**, not complete IdP metadata: it lacks `md:IDPSSODescriptor`, endpoints, and certificates. Never use this fragment directly to run SAML.

If the SP fetches the document at 08:00 UTC:

| Timestamp | Situation | Interpretation |
| --- | --- | --- |
| 08:00 | Metadata downloaded and verified successfully | Can establish a trusted snapshot |
| 12:00 | `cacheDuration=PT4H` elapsed since fetch | Should attempt reload; does not automatically invalidate metadata |
| 12:05 | Metadata endpoint has network error; old copy still has future `validUntil` | Per policy, may continue using verified copy and alert to refresh |
| 00:00 on 2026-11-08 | Reached `validUntil` | Metadata expired; must not be used to establish trust for new SSO |
| After 00:00 | Endpoint still failing and no other valid metadata exists | Suspend SSO for that registration; report error controllably |

**Important notes per OASIS SAML 2.0 Errata 05:**

- `cacheDuration` is a **recommendation for cache duration before the next refresh**. Measure it from **when metadata was actually fetched**, not from a SAML Response's `IssueInstant`.
- Reaching cache expiration does not prove metadata is invalid. When `validUntil` is absent, a cache-expired copy may still be protocol-valid; organizations can enforce a stricter maximum age policy.
- `validUntil` is a **hard** validity limit: at that timestamp, metadata must be treated as invalid. If a parent `EntitiesDescriptor` has an earlier expiration than a child, effective validity is constrained by the parent.
- **Never tack on a "grace period" after `validUntil`** just because the IdP is down. To maintain continuity, prepare a **still-valid**, verified backup metadata source ahead of time.

### What if metadata omits validUntil or cacheDuration?

Not every document carries both attributes. Missing `validUntil` does not mean "trusted forever", and missing `cacheDuration` does not mean "never update". Consumers must have **operational policies** covering refresh cadence, maximum metadata age, trusted sources, key rotation windows, and error handling.

For example, an organization caps snapshot age at 24 hours when `validUntil` is absent. That is a **custom deployment rule**, not a SAML mandate. Whenever an internal limit arrives before a protocol limit, apply the stricter limit.

## 3. Classify the Failure Before Acting

Very different failures can surface to users as simply "Cannot log in with SSO":

| Failure Type | Example Causes | Must discard old copy? |
| --- | --- | --- |
| **Metadata past `validUntil`** | IdP failed to publish updated expiration in time | **Yes**, do not continue trusting expired copy |
| **Cache due for refresh** | `cacheDuration` elapsed | Not automatically; check validity limit and policy |
| **Malformed XML** | Broken XML, wrong namespace, missing `IDPSSODescriptor`, missing required endpoint | Reject new copy; may retain still-valid old copy |
| **Invalid metadata signature** | Content altered, trust cert mismatch, signature validation failed | Reject new copy; never skip verification |
| **Metadata unreachable** | HTTP 404/5xx, DNS, TLS handshake, timeout, proxy | New content unknown; consider retaining verified still-valid copy |
| **IdP SSO endpoint down** | IdP maintenance, auth service error, or broken redirect | Valid metadata cannot make new logins succeed |
| **IdP rotated keys/certificates** | Unsynchronized rotation between metadata and SAMLResponse | Sync trust before accepting new signatures |
| **Misconfigured SP** | ACS, Entity ID, binding/issuer, reverse proxy URL mismatch | Must fix registration/config; blind refresh won't help |

For accurate diagnosis, separate **metadata retrieval**, **metadata validation**, **SAML request initiation**, **IdP authentication**, and **SAML Response validation**. They map to distinct system stages and failure signals.

## 4. Safe Metadata Fetch and Refresh Flow

~~~text
                  Need to create/update SAML registration
                               |
                     Fetch from approved source
                               |
                +--------------+--------------+
                |                             |
           Fetch succeeded                Fetch failed
                |                             |
         Security checks             Is trusted cached copy
          XML / signature             still valid and allowed by policy?
          entityID / endpoints               |
          validUntil / keys             +-----+-----+
                |                       |           |
            +---+----+                 Yes          No
            |        |                  |           |
          Pass      Fail          Keep old copy,  Suspend SSO for
            |        |             alert and       that registration
            |        |             bounded retry
            v        |
       Atomic replace|
       trusted config|
                     v
               Reject new copy
                     |
           Old copy still valid?
              |           |
             Yes          No
              |           |
          Keep old,     Suspend
          alert         new logins
~~~

Execute these steps in order:

1. **Control the source:** IdP metadata URLs must come from trusted administrative configuration/processes. Enforce valid TLS, domain allowlists if URLs vary, timeouts, and size limits.
2. **Stage downloads off the live path:** fetch the new document outside the active serving config; download failures must never wipe the active copy while it remains valid.
3. **Parse safely:** use the SAML library's XML parser, block unnecessary external entities/DTDs, bound document size/depth, and catch malformed documents.
4. **Check correctness:** select the right `entityID`, `IDPSSODescriptor` role, SAML 2.0 protocol, supported/approved endpoints and bindings, and required credentials.
5. **Check trust:** verify the metadata signature **if required by policy** against an independently configured trust anchor. Never extract an untrusted certificate from inside the metadata and call that verifying the publisher.
6. **Check expiration:** compute effective `validUntil` across the target element and ancestors, plus internal age and refresh policies.
7. **Replace only after validation:** build candidate `RelyingPartyRegistration`, validate SP/IdP config, and update the entire snapshot cleanly; avoid pairing new keys with old endpoints.
8. **Record audit & metrics:** last successful timestamp, snapshot age, expiration time, failure count, and sanitized reason; protect against credential leaks.
9. **Controlled retries:** exponential backoff with jitter and request caps; if the IdP is down, never let every login request flood metadata fetches.

One metadata URL may serve multiple entities inside `EntitiesDescriptor`. Always pick the exact admin-approved entity rather than blindly taking the first entry.

## 5. Malformed Metadata: More Than Just XML Parse Errors

Distinguish at least three failure classes:

### 5.1. Unparseable XML

Examples: truncated files, mismatched tags, wrong namespaces, invalid encoding, abnormal entities/DTDs, or an HTTP 500 HTML error page returned instead of XML.

Response: **reject the new document and log a source/parse error**; if the previously verified snapshot remains valid, continue serving it per policy. Never try to auto-repair XML by guessing missing tags or disabling parser validation in production.

### 5.2. Syntactically Valid XML with Wrong SAML Semantics

Examples:

- `EntityDescriptor` lacks the expected `entityID`.
- Missing a SAML 2.0-compliant `IDPSSODescriptor`.
- Missing a usable `SingleSignOnService`, or only exposing an unsupported binding.
- Returning metadata for another IdP, another tenant, or staging instead of production.
- Missing verification credentials required by policy.
- `validUntil` already passed or restricted earlier by parent elements.
- Published signing/encryption certificate incompatible with the SP's key/algorithm policy.

Response: mark **VALIDATION_FAILED**, and do not add registrations or replace trusted config. Never "fix" by dropping issuer/audience checks.

### 5.3. Semantically Valid XML That Is No Longer Trustworthy

Metadata tampered with, invalid signature, metadata signer cert outside the trust anchor, TLS trust failure, or source chain violating the IdP agreement. The file might look clean with plausible SSO URLs and certificates, yet **must be rejected**.

A `KeyDescriptor` inside the file supplies public keys for the SP to verify future SAML signatures; it **does not prove the metadata file itself came from the real IdP**. You need a trusted source/transport and/or **metadata signature verification with a preconfigured trust anchor**.

**Important policy:** When new metadata is invalid, retain the trusted snapshot (while permitted) and raise alerts. Never allow a SAML response to verify against a new cert solely because that cert appeared in an unvetted document.

## 6. When the IdP's Metadata Endpoint Is Temporarily Unreachable

For example, HTTPS `https://idp.example.test/metadata` returns HTTP 503 when the SP needs to refresh.

**Scenario A — valid trusted snapshot available:** continue using **the previously authenticated IdP configuration** until `validUntil` and internal limits; schedule retry/backoff. Note this prevents outage **only if the actual SSO endpoint still works**. Without a valid cache or valid expiry, never fabricate IdP config.

**Scenario B — no snapshot or snapshot expired:** refuse to establish trust/registration for that IdP and fail logins cleanly. A Spring Boot app may fail to start if the `RelyingPartyRegistration` bean fetches metadata at startup and fails; define clear startup behavior in operations, keeping a policy-compliant trusted snapshot if startup resilience is required.

**Scenario C — cert rotated while metadata endpoint is broken:** the cached snapshot may still be before `validUntil` and within cache limits, yet if the IdP signs responses with a new cert absent from trusted verification certs, responses **must be rejected**. Never disable signature verification. Operations must contact the IdP or apply an out-of-band verified certificate update per approved procedure.

**Scenario D — network issue isolated to one SP:** check DNS/proxy/firewall/TLS from that exact app environment; do not conclude "the entire IdP is down" just because one server cannot fetch metadata.

### Cached Metadata Can Be Stale Yet Still Valid

Failing to reload after `cacheDuration` is a "**stale for refresh**" state, not "**invalid**" while `validUntil` hasn't elapsed. Still, organizations need max-age bounds, alerts, and explicit awareness of stale-config risks (e.g. if the IdP switches endpoints or rotates keys mid-cache).

Conversely, a copy past `validUntil` is **expired/invalid**; never cite an "outage grace period" to keep accepting new SSO logins.

## 7. When the IdP SSO or Authentication Service Itself Is Down

Clearly distinguish three endpoints:

| Component | Symptom | What Can Be Done? |
| --- | --- | --- |
| **IdP metadata endpoint** | SP cannot refresh configuration | Use still-valid trusted snapshot; retry and alert |
| **IdP SingleSignOnService** | Browser redirect fails, times out, or IdP login page errors | New logins via that IdP fail; display outage message |
| **IdP SingleLogoutService** | SAML SLO cannot complete | Handle local logout and session state per policy; never pretend global SLO succeeded |

**Even with perfectly loaded metadata, if IdP SSO is down, browsers cannot complete new authentications** through that IdP. There is no "cached login success" to substitute for live authentication.

### What about users with active Spring Security sessions?

An SP session authenticated before the IdP outage **may continue working** according to the SP's session, timeout, and authorization policies. This is not automatic across all apps: features depending on IdP APIs/tokens or re-authentication rules may become unavailable.

- Never forcibly log out all users simply because a metadata endpoint health check fails, unless security policy mandates it.
- Never extend existing sessions indefinitely or grant extra permissions just because the IdP cannot be re-verified.
- If an action requires **fresh authentication, MFA step-up, or reauthorization at the IdP**, wait for IdP recovery or use an approved fallback mechanism.
- Re-authentication after logout or session expiration will fail during the outage.

### Multiple IdPs: Conditional Failover

If the app has `corp` and `partner`, a `corp` IdP outage **does not permit** corp employees to log in through `partner`. A backup IdP may only be used when:

1. Preconfigured as a valid trust relationship.
2. Governed by verified account-linking and tenant-mapping rules.
3. Satisfying equivalent assurance, MFA, and authorization policies.
4. Introducing no cross-organization bypass or account-takeover path.

Never silently swap registrationIds and assume two IdPs represent the same identity.

## 8. Spring Security: Relevant Components

In a Spring Boot/Spring Security SAML2 application:

| Component | Role | What to Watch During Metadata Failures |
| --- | --- | --- |
| `RelyingPartyRegistration` | Configuration for one SP–IdP pair | Must be built from vetted data |
| `RelyingPartyRegistrationRepository` | Looks up registrations | Missing/invalid registration breaks login |
| `InMemoryRelyingPartyRegistrationRepository` | Holds registrations in-process | Does not auto-reload when metadata source changes |
| `RelyingPartyRegistrations.fromMetadataLocation` | Builds registration from IdP metadata | Fetches/parses during registration build; can fail startup |
| `CachingRelyingPartyRegistrationRepository` | Lazy-loads/caches registrations from backing repository | Refresh behavior depends on **cache eviction policy** |
| `AssertingPartyMetadataRepository` | Abstraction for accessing IdP metadata | Implementations can support refresh, expiry awareness, and metadata signature validation |
| `OpenSaml5AssertingPartyMetadataRepository` | OpenSAML 5-backed implementation | Supports metadata resolver refreshing by validity, depending on config/version |
| `saml2Login` | SAML login filters/flow | Cannot turn broken metadata into valid responses |
| `saml2Metadata` | Publishes **SP metadata** | Not a mechanism to repair IdP metadata |

Metadata repository and OpenSAML 5 APIs exist in specific Spring Security versions. Check documentation for your **exact app version** before using; never copy Spring Security 7 code onto Spring Security 5.

### 8.1. Simple Configuration: Static Metadata, Single IdP

Example for **Spring Boot 3.x / Spring Security 6.x, Java 17+**, Servlet Web app with `spring-security-saml2-service-provider`.

File `src/main/java/com/example/security/SamlSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
            .registrationId("corp")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Prerequisites:** requires a **valid, trusted** IdP metadata file at `src/main/resources/saml/corp-idp-metadata.xml`, registered SP Entity ID and ACS at the IdP, and compatible signing configuration. If the IdP requires signed AuthnRequests or sends encrypted assertions, add SP signing/decryption credentials. This class is a Spring Boot project config, **not a standalone program** runnable with `javac`/`java`; there is no fixed stdout.

**Example limitation:** when `fromMetadataLocation` reads the classpath at bean creation, Spring keeps a snapshot in the InMemory repository. If the IdP rotates keys at runtime, **it does not automatically track new metadata**. Malformed XML can break registration creation/startup; therefore manage metadata, validate pre-deploy, and maintain rollback plans.

### 8.2. CachingRelyingPartyRegistrationRepository: Conditional Refresh

Spring Security supports `CachingRelyingPartyRegistrationRepository`: supply a loader/supplier producing `IterableRelyingPartyRegistrationRepository`, and configure a cache with proper eviction.

Deployment diagram:

~~~text
Spring SAML filters
       |
       v
CachingRelyingPartyRegistrationRepository
       |
  Cache still valid per TTL?
       |                   |
      Yes                  No
       |                   |
   Registration        Configured metadata loader
       |                   |
       |             Fetch + validate + build
       |                   |
       +---------<---------+
                   |
           Lookup registrationId
~~~

**Never assume the Caching class enforces `validUntil` policies for all metadata.** The caching repository delegates eviction to Spring Cache; the default cache may not expire at all. If eviction occurs while the loader's metadata URL is down, lookups can fail without a compliant last-known-good mechanism. Design TTL and snapshot validation independently of cache logic; never use cache TTL to legitimize metadata whose `validUntil` has passed.

Design illustration (not full cache manager source code):

~~~text
trustedSource: https://idp.example.test/metadata
registrationId: corp
cacheTTL: per organizational policy, not exceeding metadata validity limits
onRefresh:
  fetch -> verify source/signature -> parse and validate
  if valid: publish new registration atomically
  if failed: keep previously verified snapshot only while still valid
  otherwise: make corp SSO unavailable with controlled error
~~~

**Key distinction:** a caching repository prevents continuous re-fetching and enables refresh opportunities, yet detecting expired/invalid metadata and managing last-known-good must still be guaranteed by an appropriate metadata/policy layer.

### 8.3. AssertingPartyMetadataRepository for Refresh and Signature Needs

Modern Spring Security docs describe `AssertingPartyMetadataRepository` for managing IdP metadata separately. OpenSAML-based implementations such as `OpenSaml5AssertingPartyMetadataRepository` can use a `MetadataResolver` to refresh per expiration and support verifying metadata signatures with **configured verification credentials**.

**Critical warning:** the method name `fromTrustedMetadataLocation` expresses an assumption that **the source is trusted**; it does not mean metadata undergoes cryptographic signature validation without further config. Docs explicitly state: if no verification credentials are provided, the component **does not perform metadata signature validation**. Even with an HTTPS source, evaluate against your trust policy.

In multi-tenant systems, ensure the repository knows how to map **registrationId → exact IdP entityID**, rather than assuming registrationId always equals entityID in metadata. Docs samples using the same string are illustrative, not a SAML rule.

## 9. Designing Last-Known-Good Properly

A **last-known-good (LKG)** copy is a metadata snapshot that passed all required validations at **an earlier point in time**. It helps only when the fresh source fails while the old copy remains trustworthy and unexpired.

The snapshot should record:

| Field | Role |
| --- | --- |
| `entityId` | Ensures it matches the approved IdP |
| `retrievedAt` | Computes cache duration and refresh timing |
| `validUntilEffective` | Hard SAML expiration bound for this metadata |
| `refreshAfter` | Re-fetch target from `cacheDuration` or policy |
| `verifiedSource` | Vetted HTTPS source or trust anchor |
| `signatureVerified` / `trustValidated` | Policy validation outcomes |
| `ssoEndpoints` and `verificationCredentials` | Config for building registrations |
| `metadataVersionHash` | Identifies version for auditing changes |
| `lastRefreshError` | Sanitized reason the latest fetch failed |

### Decision Rules

- **Valid new metadata available:** validate completely first, then swap snapshot atomically and update cache.
- **New metadata broken or unreachable, LKG still valid:** retain LKG per policy; alert and retry with backoff.
- **LKG passed cacheDuration yet before validUntil:** may still be used if policy allows; prioritize refresh and track snapshot age.
- **LKG passed validUntil or exceeded internal hard max age:** refuse to use for initiating new SAML logins. Recover via a verified valid metadata source.
- **No LKG on initial startup:** SP has no trust baseline for the IdP; never construct registrations from arbitrary Internet XML.
- **IdP SSO endpoint down:** LKG cannot enable new authentications; return controlled login errors per policy.

**Storage note:** LKG may live in deployment config or a protected internal store. If persisted long-term, enforce integrity, access controls, auditing, backup security, and expiration policies. Never let client browsers supply LKG metadata.

## 10. Standalone Java 17 Example: Deciding When Metadata Fails

The Java snippet below **compiles and runs on Java 17+**. It illustrates the decision layer **after a SAML library has verified source, structure, signature, and validUntil**. It is neither an XML parser nor a signature verifier. Simulated rules require a trusted snapshot prior to `validUntil` along with IdP SSO availability.

File **MetadataPolicyDemo.java**:

~~~java
import java.time.Instant;

public class MetadataPolicyDemo {

    record TrustedSnapshot(
            Instant validUntil,
            Instant refreshAfter,
            boolean trustValidated) {}

    static String decide(TrustedSnapshot snapshot,
                         Instant now,
                         boolean latestFetchSucceeded,
                         boolean idpSsoAvailable) {
        if (snapshot == null || !snapshot.trustValidated()) {
            return "BLOCK: no trusted metadata";
        }
        if (!now.isBefore(snapshot.validUntil())) {
            return "BLOCK: metadata expired";
        }
        if (!idpSsoAvailable) {
            return "BLOCK: IdP SSO unavailable";
        }
        if (!latestFetchSucceeded
                && !now.isBefore(snapshot.refreshAfter())) {
            return "ALLOW: valid cache, refresh failed, alert";
        }
        return "ALLOW: trusted metadata and SSO available";
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T12:05:00Z");

        TrustedSnapshot valid = new TrustedSnapshot(
                Instant.parse("2026-11-08T00:00:00Z"),
                Instant.parse("2026-11-07T12:00:00Z"),
                true);

        TrustedSnapshot expired = new TrustedSnapshot(
                Instant.parse("2026-11-07T12:00:00Z"),
                Instant.parse("2026-11-07T11:00:00Z"),
                true);

        System.out.println(decide(valid, now, false, true));
        System.out.println(decide(expired, now, false, true));
        System.out.println(decide(valid, now, true, false));
        System.out.println(decide(null, now, false, true));
    }
}
~~~

Compile and run:

~~~bash
javac MetadataPolicyDemo.java
java MetadataPolicyDemo
~~~

**Exact** stdout:

~~~text
ALLOW: valid cache, refresh failed, alert
BLOCK: metadata expired
BLOCK: IdP SSO unavailable
BLOCK: no trusted metadata
~~~

Explanation:

- Case 1: cache needed refresh at 12:00 and refresh failed, yet at 12:05 it is still before the next day's `validUntil`. Demo allows the snapshot **if policy supports it** and raises an alert.
- Case 2: current time has passed `validUntil=12:00`, so even a previously trusted snapshot must be blocked.
- Case 3: metadata is valid yet IdP SSO is unavailable; new logins through the IdP cannot proceed.
- Case 4: no trusted metadata exists; never self-trust an unverified IdP.

**Assumptions requiring real implementation in production:** the sample omits clock skew, `EntitiesDescriptor` cache hierarchy, internal max-age, DNS/network status, XML signatures, key rollover, and refresh workflows. The `trustValidated` flag represents **the verified outcome of a trusted component**, never a parameter from an HTTP request. In reality, IdP availability cannot be detected accurately by a single boolean; use timeouts, health checks, and SAML flow telemetry.

## 11. Monitoring and Alerting Before Outages Occur

Do not wait for customers to report login errors to discover metadata is about to expire. Track metrics such as:

| Metric / Event | Purpose |
| --- | --- |
| `saml_metadata_refresh_success_time` | Latest successful update timestamp |
| `saml_metadata_refresh_failures_total` | Fetch, parse, and trust validation failures by type |
| `saml_metadata_effective_valid_until` | Hard expiration timestamp |
| `saml_metadata_age_seconds` | Age of active snapshot |
| `saml_idp_sso_failures_total` | Signals of IdP login failures |
| `saml_assertion_signature_failures_total` | Detects broken trust/rotation or anomalous activity |
| `saml_metadata_cert_expiry_days` | Tracks managed X.509 certificate expiration |
| `saml_registration_active` | Whether registration has valid trust to accept new logins |

These are **illustrative custom metric names**, not built-in metrics provided automatically by Spring Security Actuator.

Configure alerts based on **remaining time before expiration**, not just a binary "valid/invalid" status:

1. Ahead of `validUntil` early enough to coordinate with the IdP, refresh, and verify signatures/certs.
2. When consecutive refresh failures rise or time since last successful refresh exceeds policy.
3. When new metadata alters issuer/endpoints/certificates significantly compared to the approved baseline, especially unscheduled changes.
4. When IdP SSO logins fail repeatedly while metadata fetches succeed; avoid mistaking it for a parser error.
5. When assertion signature validation failures spike after certificate rotation.

**Never log** full SAML assertions, private keys, session cookies, MFA evidence, or personal data in metadata/Responses; log registrationId, error category, timestamp, version hash, and sanitized correlation IDs.

## 12. Incident Response Runbook

### A. Metadata reached validUntil or expired

1. Identify `registrationId`, IdP entityID, effective `validUntil`, and metadata source.
2. Check server UTC clock and parent-element limits; avoid misreading `cacheDuration` as expiration.
3. Request the IdP to publish **fresh, valid metadata from a trusted source/signature**; verify issuer, endpoints, and certificates.
4. Update the registration atomically or deploy new configuration after QA.
5. Test a new login and verify response signature and audience/recipient; do not merely check that the metadata endpoint returns 200.
6. Until valid metadata is available, **suspend new SSO for that IdP** and display a clear message.

### B. Metadata downloads yet XML is malformed or semantically wrong

1. Record error type (`MALFORMED_XML`, `MISSING_IDPSSO_DESCRIPTOR`, `ENTITY_ID_MISMATCH`, `METADATA_SIGNATURE_INVALID`...).
2. Quarantine the new candidate; do not overwrite the active trusted snapshot.
3. Inspect HTTP Content-Type, status code, redirects, gzip/encoding, XML namespaces, entity structure, and bindings.
4. Contact the IdP to fix the artifact or source, checking for spoofing/misconfiguration.
5. Deploy only after the candidate passes validation.
6. If LKG remains valid, logins may continue per policy; if expired, suspend.

### C. Metadata endpoint returns 404/503 or times out

1. Check DNS, TLS, proxy, firewall, HTTP status, server certificates, and real IdP endpoints.
2. Check the IdP SSO endpoint independently: the metadata URL may be broken while logins still work using LKG.
3. If LKG is valid, enable backoff/circuit breaking with alerts and explicit max duration.
4. If LKG passes `validUntil`, stop trusting that metadata; never grant arbitrary "grace" extensions.
5. Check ongoing rotations; avoid sticking to an old cert once the IdP signs with a new cert the SP doesn't yet trust.
6. Once the source recovers, refresh and verify a new login before closing the incident.

### D. IdP SSO cannot authenticate users

1. Check redirect to IdP, IdP login page, bindings, and AuthnRequest.
2. Separate network/IdP 5xx errors from SP-side `InvalidSignature`, `NoAuthnContext`, `InResponseTo`, and `Audience` errors.
3. Inform users that new logins via this IdP are currently unavailable.
4. Existing SP sessions may continue only per designed session and authorization policies.
5. If a backup IdP exists, use it only if identity binding, assurance, and organizational policy permit.
6. After recovery, test end-to-end from AuthnRequest initiation through ACS callback and business permissions.

### E. Cert rollover causes validation failures

1. Compare the certificate the IdP currently **uses to sign SAML Responses** with verification certificates trusted in the SP registration.
2. Verify the new metadata has the right source, issuer, validity window, and approved key.
3. During transition, if permitted by the IdP, maintain both old and new certificates per plan.
4. Update trusted metadata/certs, refresh the repository, and test login.
5. Never choose to disable signature verification or skip audience checks.

## 13. Common Errors in Spring Security

| Symptom | Likely Analysis | Action |
| --- | --- | --- |
| App fails startup creating `RelyingPartyRegistration` | `fromMetadataLocation` hit unreachable URL or malformed XML | Use a trusted source with refresh plan; check startup config |
| `findByRegistrationId` returns null | No valid registration or wrong key | Check `registrationId` mapping and repository |
| Caching enabled yet metadata never refreshes | Cache has no eviction or loader reads stale snapshot | Configure TTL/eviction and refresh source |
| New metadata has past `validUntil` | IdP published expired metadata or wrong entity selected | Reject and request fresh metadata |
| Metadata URL returns XML yet no IdPSSODescriptor found | Confused SP metadata or wrong profile/entity | Point to the right IdP metadata |
| Metadata signature validation fails | Wrong trust anchor, tampered XML, or uncoordinated rotation | Quarantine candidate; verify metadata and certificates |
| Browser redirects to 503 | IdP SSO service is down | Do not "fix" by disabling verify; confirm IdP status |
| Assertion signature fails after rotation | SP verification key not yet updated | Refresh trusted metadata properly |
| `InResponseTo` or `Recipient` mismatch | Misconfigured state/callback URL/ACS | Check AuthnRequest, SP Entity ID, ACS, reverse proxy |
| Users with SP sessions work yet new logins fail | Local session active, IdP cannot issue new auth | Manage user messaging and sessions per policy |
| Login returns `403` after SAML auth | Application authorization denied access | Check role/tenant/object permissions; do not equate metadata with permissions |
| SP metadata endpoint returns 200 while IdP is down | SP metadata endpoint operates independently | Monitor IdP SSO and validation separately |

### Wrong Fixes to Avoid

- Disabling metadata signature verification just to accept a new document.
- Allowing untrusted certificates or skipping SAML Response signatures.
- Accepting any SAML entity with a similar name or picking the first entity.
- Dropping audience, recipient, InResponseTo, or timestamp checks.
- Continuing to use metadata past `validUntil` just because the IdP is having an outage.
- Disabling all authentication for APIs or admin consoles when the IdP goes down.
- Believing changing cache TTL automatically solves key rotation or IdP 503s.
- Reading arbitrary user-supplied metadata URLs without SSRF/trust-source controls.

## 14. Self-Assessment Scenarios

**Question 1:** Metadata fetched at 08:00, `cacheDuration=PT4H`, `validUntil=00:00` next day. At 12:05 reload fails. Can the old copy still be used?

**Answer:** The vetted copy has not passed `validUntil`; per OASIS, cache expiration alone does not invalidate metadata. It may continue to be used if organizational policy permits, alongside alerts/retries. Never use it after `validUntil`.

**Question 2:** IdP serves parseable XML whose `entityID` belongs to a staging IdP. Can it be accepted because SSL is valid?

**Answer:** No. TLS does not replace verifying the exact entityID, trust context, and issuer of the registration.

**Question 3:** SP has valid metadata and a new certificate, yet the IdP login page returns 503. Can cached metadata authenticate new users?

**Answer:** No. Metadata is only trust configuration; new logins still require the IdP to execute the SAML authentication flow or an approved fallback mechanism.

**Question 4:** Metadata omits `validUntil` and cacheDuration has elapsed. Is it strictly invalid per SAML?

**Answer:** Not solely due to cacheDuration. However, consumers must enforce refresh/max-age policies; omitting validUntil is not a grant of eternal trust.

**Question 5:** After certificate rotation, the IdP sends SAML Responses signed with a key absent from trusted metadata. Should signature verification be temporarily disabled?

**Answer:** No. Update the certificate from a trusted source and re-verify to preserve the trust boundary.

**Question 6:** A new metadata fetch returns malformed XML while LKG remains valid. Should the repository be replaced with the broken copy?

**Answer:** No. Keep the verified copy, log an alert, and retry; swap only when a new candidate satisfies all security requirements.

**Question 7:** A user logged into the Portal and holds a valid SP HttpSession when the IdP goes down. Must every SP session be terminated immediately?

**Answer:** Not by default. SP sessions have their own lifecycle and policy; operations requiring re-authentication or reauthorization may be blocked.

## 15. Production Deployment Checklist

- [ ] Fetch metadata only from approved IdPs/URLs and verify HTTPS or metadata signature with an appropriate trust anchor.
- [ ] Enforce exact `entityID`, `IDPSSODescriptor`, bindings, SSO endpoints, and X.509 verification credentials.
- [ ] Enforce effective `validUntil`; clearly separate it from `cacheDuration` and internal metadata age policies.
- [ ] Harden XML parser against XXE/DTD and bound document size; protect metadata URLs from SSRF.
- [ ] Pass new candidates through parse/semantic/signature/trust/time validation **before** replacing the active copy.
- [ ] Maintain a trusted LKG snapshot used only while valid, with alerts, TTL/retry/backoff.
- [ ] Separate metadata endpoint outages from IdP SSO outages; provide clear login failure messaging.
- [ ] Track certificate rollovers, configure signing/verification, and update metadata on time.
- [ ] When using InMemory, recognize it does not auto-refresh; when using Caching, configure separate eviction and expiry policies.
- [ ] With OpenSAML-based metadata repositories, select the trust model and metadata signature verification matching your API version.
- [ ] Never accept SAML Responses with wrong issuer, signature, audience/recipient, timestamp, or tenant even during an IdP outage.
- [ ] Never allow failover to another IdP without approved account mapping and authorization.
- [ ] Monitor refresh age, validUntil, parse/trust errors, login failures, certificate expiry, and IdP outages.
- [ ] Maintain runbooks and chaos tests: IdP 503, DNS/TLS failure, malformed XML, invalid signature, expired validUntil, key rotation, SSO endpoint down.
- [ ] Prepare recovery/downtime plans when no valid trusted metadata remains; never weaken security controls to boost availability.

## 16. Conclusion

In SAML2 federation, **metadata is security data governing trust relationships**. When **cache expires**, prioritize refreshing while using a verified, still-valid copy if policy allows. When **validUntil has passed**, never use expired metadata. When **metadata is malformed or has an invalid signature**, reject the new copy and retain only a still-valid LKG copy. When **IdP SSO is down**, cached metadata cannot substitute for fresh authentication; existing SP sessions are governed by application policy.

In Spring Security, `RelyingPartyRegistrationRepository` must always supply registrations built from trustworthy data. `InMemoryRelyingPartyRegistrationRepository` suits stable configurations; proactive refresh, caching policies, or `AssertingPartyMetadataRepository` with an appropriate metadata resolver are the right choices when IdP metadata changes frequently. Never trade away SAML/metadata verification for convenience during an incident.

### Official References

- **OASIS SAML 2.0 Metadata**: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- **OASIS SAML 2.0 Errata 05**, section E94 (distinguishing metadata caching and validity): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- **Spring Security – SAML 2.0 Login Overview**, registration, InMemory, and Caching: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security – SAML 2.0 Metadata**, AssertingPartyMetadataRepository and signatures: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- **Spring Security – Authenticating SAML Responses**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Security – CachingRelyingPartyRegistrationRepository API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html
