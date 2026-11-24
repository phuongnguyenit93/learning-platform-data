# validUntil, cacheDuration, and SAML 2.0 Metadata Refresh Policies

**Module:** Spring Security – federation  
**Topic Group:** SAML2 Metadata  
**Illustrative Environment:** Java 17+, Spring Boot 3.x, Spring Security 6.x. Sections using CachingRelyingPartyRegistrationRepository require **Spring Security 6.4+**.

## 1. Why Does Metadata Need Expiration and Refresh Policies?

In SAML 2.0 federation, the Service Provider (SP) and Identity Provider (IdP) exchange **metadata XML** to agree on identifiers (**entityID**), Single Sign-On endpoints, bindings, signing certificates, encryption mechanisms, and other protocol details. When an SP trusts an IdP, the IdP's metadata is part of **security configuration**: the SP relies on it to choose endpoints and keys for verifying SAML Responses/Assertions.

That information can change:

- IdP **rotates signing certificates**: stale metadata may omit the new key, breaking SSO.
- IdP changes SSO endpoints, bindings, entities, or policy config: stale metadata can point to wrong paths or wrong trust settings.
- Metadata files distributed by a federation aggregator: multiple entities appear together with varying validity lifetimes.
- Connectivity to the metadata source is interrupted, or fetched metadata is corrupted/has an invalid signature: active config cannot simply be replaced with new content.

Two common metadata attributes are **validUntil** and **cacheDuration**. They answer **two different questions**:

- **validUntil:** "Until what timestamp is this metadata still considered valid?" This is a **mandatory hard expiration**; at or after that timestamp, the metadata expires and **must no longer be used**.
- **cacheDuration:** "At most how long should a consumer wait before trying to fetch fresh metadata?" This is a **freshness/caching hint** for scheduling refresh attempts; it does not invalidate metadata when the cache duration elapses.

**Core rule:** Metadata can be **stale yet still valid** after cacheDuration, provided validUntil has not passed and local policy permits. Metadata past validUntil is **invalid**, even if the cache TTL hasn't expired, even if HTTP returns 304, and even if fetching a fresh copy fails.

## 2. XML Representation and Time Semantics

Example metadata for an IdP (real elements and certificates omitted):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/company"
    validUntil="2026-11-08T00:00:00Z"
    cacheDuration="PT6H">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

This is **XML for reading attributes**, not complete metadata to run Spring Security SAML2: it lacks certificates/details needed for signature verification and trust.

### validUntil – Absolute Timestamp

**validUntil="2026-11-08T00:00:00Z"** means the metadata **must be treated as expired starting at 00:00:00 UTC on 2026-11-08**. At the exact instant equal to validUntil, validity no longer holds.

- Schema data type is **xs:dateTime** (ISO 8601/XML Schema, optionally carrying timezone).
- This is the **metadata's** lifetime, not NotOnOrAfter in a SAML Assertion, nor automatically the HTTP session lifetime of a logged-in user.
- An X.509 certificate has its own **notAfter** timestamp; do not equate certificate expiration with metadata validUntil.
- Never extend validUntil by adjusting the local clock, editing old XML, or treating an HTTP cache as still fresh.
- Server clocks must be NTP-synchronized; handle UTC accurately and avoid arbitrary timezone conversions.

### cacheDuration – Relative Duration

**cacheDuration="PT6H"** is an **xs:duration**, meaning metadata suggests **attempting a refresh after about 6 hours** from when the metadata was consumed/received.

Syntax examples:

| Value | Meaning |
| --- | --- |
| **PT15M** | 15 minutes |
| **PT6H** | 6 hours |
| **P1D** | 1 day |
| **P7D** | 7 days |
| **P1DT2H** | 1 day 2 hours |
| **P1M** | 1 month per xs:duration; do not default to a fixed 30 days |

**Do not confuse the letter M:** **PT15M** is minutes; **P1M** is months. XML Schema duration also supports years/months, so never assume every duration converts to a fixed number of seconds via **java.time.Duration.parse**. For months/years, use an appropriate parser and calendar arithmetic; the Java 17 example later intentionally uses **PT6H** to avoid that ambiguity.

To compute cache expiration, record **the time the metadata was fetched**. cacheDuration is not an absolute timestamp and must not be added arbitrarily to **validUntil**.

## 3. Comparing validUntil and cacheDuration

| Criterion | validUntil | cacheDuration |
| --- | --- | --- |
| Type | **xs:dateTime** | **xs:duration** |
| Meaning | Absolute timestamp when metadata ceases to be valid | Maximum duration to cache before **attempting refresh** |
| Strictness | **Hard expiration:** once expired, must not be used | **Freshness hint:** elapsed duration alone does not make metadata invalid |
| Reference clock | Compared against current time | Measured from when metadata was acquired |
| When fresh fetch fails | If past validUntil, must reject usage | May keep using stale copy while still valid and allowed by policy |
| Relationship | Can block usage before scheduled refresh | Must never exceed hard expiration |
| When attribute absent | No hard expiration from this attribute; requires local policy | No TTL hint from metadata; requires local refresh schedule |

**Example:** Metadata fetched at **08:00 UTC on 2026-11-07**, cacheDuration **PT6H**, validUntil **00:00 UTC on 2026-11-08**.

- **08:00:** metadata just received and verified; ready for use.
- **14:00:** should attempt to fetch a fresh copy per cacheDuration.
- **14:30:** network still failing; old metadata is **stale** yet **not expired**. Whether to keep using it temporarily depends on the organization's freshness/failure policy.
- **00:00 on 2026-11-08:** old metadata has **expired** and cannot be used further, even if the network is down and the last refresh failed.

If the organization enforces a stricter internal cap, such as **local max refresh interval of 2 hours**, try refreshing at **10:00**, earlier than the IdP's hint. That is an additional policy; it does not alter the XML's meaning.

## 4. Nested Metadata: EntitiesDescriptor and EntityDescriptor

In large federations, an XML file may wrap multiple **EntityDescriptor** elements inside an **EntitiesDescriptor**, each entity being an IdP or SP. Elements may declare validUntil/cacheDuration at different levels.

Example:

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Name="TrustedFederation"
    validUntil="2026-11-09T00:00:00Z"
    cacheDuration="PT12H">
  <md:EntityDescriptor
      entityID="https://idp-a.example.org/saml"
      validUntil="2026-11-08T06:00:00Z"
      cacheDuration="PT2H">
    <!-- IDPSSODescriptor, KeyDescriptor, endpoints... -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

- In this example, **entity A has an earlier validUntil than the aggregate**, so entity A's effective expiration is **06:00 UTC on 2026-11-08**.
- Entity A's **cacheDuration PT2H** is tighter than the group's **PT12H**; the smaller bound can drive refresh scheduling.
- If a child entity declares a validUntil **later** than its parent, the child metadata **cannot override the parent's expiration**.
- Enforce effective limits across **the entire path from root/ancestor down to the entity or role in use**; never read only the first or last element's attribute.

Per SAML metadata errata, child attributes can **tighten** a parent's bounds, never loosen them. When multiple limits exist, compute the **shortest effective validity limit** per standard rules. Distinguish metadata inheritance/bounds from TTLs imposed by HTTP CDNs or internal caches.

**Common bug:** Parser reads validUntil only on **EntityDescriptor** and ignores an earlier validUntil on **EntitiesDescriptor**. As a result, the app continues trusting an entity inside an expired aggregate.

## 5. Refresh Policy: From Trusted Metadata to Usable Registration

A sound policy has four independent parts:

1. **Source trust decision:** configure the approved list of IdPs/federations; downloaded metadata must satisfy source/integrity policies.
2. **Validity calculation:** determine effective validUntil, all ancestor/child bounds, current time, and internal lifetime policies.
3. **Refresh scheduling:** cacheDuration, local max refresh interval, pre-expiry safety margin, and jitter.
4. **Failure handling:** whether last-known-good is allowed, retry/backoff rules, when to fail closed, and operational alerts.

### 5.1. Refresh Schedule Calculation Rules

Notation:

- **tFetch:** timestamp when the newly downloaded and verified metadata was stored.
- **dCache:** effective cacheDuration from the XML.
- **dLocal:** organization-configured maximum refresh interval, e.g. 2 hours.
- **tExpire:** effective validUntil; if absent, apply an appropriate internal policy.
- **margin:** safety buffer to update ahead of expiration, e.g. 30 minutes.

Guiding formula for the next refresh **attempt**:

~~~text
tByCache  = tFetch + dCache
tByPolicy = tFetch + dLocal
tByExpiry = tExpire - margin

tNextRefresh = min(tByCache, tByPolicy, tByExpiry)
~~~

If dCache or tExpire is absent, drop that branch and apply the app's mandatory policy (for example: refresh at least every 2 hours; reject metadata lacking validUntil if organizational rules require it). If tByExpiry lies in the past or metadata is already expired, refresh immediately and **do not load expired metadata into the trust store**.

**The formula is an illustrative policy**, not an automatic built-in transformation in Spring. Add bounded jitter so multiple nodes do not refresh simultaneously; jitter must never push a refresh past tExpire. Do not treat margin as metadata becoming invalid early per specification; it is a preparation buffer to prevent outages.

### 5.2. Operational Algorithm

~~~text
1. Fetch from approved location/issuer.
2. Authenticate metadata source/integrity; parse XML safely.
3. Check entityID, endpoints, keys, and validUntil/cacheDuration limits.
4. If new metadata is invalid: do not publish; retain old valid
   version per policy and report error.
5. If valid: build new RelyingPartyRegistration; publish atomically.
6. Record fetchedAt, effectiveValidUntil, nextRefreshAt, metadata version/hash.
7. Refresh when due; on error, retry with bounded backoff.
8. After validUntil, do not continue using expired metadata.
~~~

**Publish atomically** means swapping the active configuration only after **all** parse/validate/build steps succeed; in-flight requests never observe a half-old, half-new state.

### 5.3. Managing Outages and Last-Known-Good

In practice, distinguish two states:

- **Stale:** tNextRefresh has arrived yet a fresh copy could not be obtained; old metadata is still before validUntil.
- **Expired:** current time has reached or passed tExpire; old metadata is no longer valid.

For stale-but-valid, an organization may **conditionally continue using** the cached copy briefly while alerting and retrying; or more strictly, reject after a dedicated stale cap. For expired, you must **stop trusting that metadata**, even if users temporarily cannot log in. No "emergency flag" should arbitrarily ignore validUntil just to keep SSO running.

If validUntil is absent, the standard does not impose a hard expiration; operations should enforce a **local maximum lifetime** or policies requiring validity and a system-appropriate max age. Never conclude from a missing validUntil that metadata is permanently safe.

## 6. Distinguishing TTLs Across Four Layers

In a Spring Security project, multiple timing mechanisms can coexist:

| Layer | Example | What to Understand |
| --- | --- | --- |
| **SAML XML validUntil** | 2026-11-08T00:00:00Z | Absolute metadata expiration per SAML |
| **SAML XML cacheDuration** | PT6H | Publisher's suggested schedule to re-fetch XML |
| **HTTP cache headers** | Cache-Control: max-age=3600, ETag | HTTP-layer caching guidance; does not make expired XML valid |
| **Spring Cache TTL** | Caffeine expireAfterWrite 30 minutes | When a repository entry is evicted and a new request arrives, reloads registration; **does not check** SAML validUntil |

**Repository TTL does not equal SAML cacheDuration unless you actively connect the two policies.** A 30-minute Caffeine cache merely evicts the entry after 30 minutes; the loader could re-fetch **the exact same expired metadata** without separate validation.

Similarly:

- **HTTP 304 Not Modified:** server states content hasn't changed; does not extend the **validUntil** signed or published in the old XML.
- **Certificate notAfter:** X.509 certificate lifetime, independent of metadata lifetime and SAML Assertion lifetime.
- **SAML Assertion Conditions.NotOnOrAfter:** assertion lifetime **for a single login**; not an IdP metadata refresh schedule.
- **HTTP session expiration:** how long the user stays signed into the app; expired metadata does not automatically log out browsers under a single universal rule, yet **new authentications** must not be accepted based on expired metadata.

## 7. Spring Security: Creating Registrations from Metadata and Limits of Static Config

Simple approach in Spring Security 6.x:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrations() {
    RelyingPartyRegistration company =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/company-idp.xml")
            .registrationId("company")
            .build();

    return new InMemoryRelyingPartyRegistrationRepository(company);
}
~~~

This is a **Spring Bean snippet** inside a **@Configuration** class, not a standalone class. Requires **spring-security-saml2-service-provider**. Meaning:

- **fromMetadataLocation** reads XML from the configured location to populate a builder.
- **build()** creates a registration containing SP and IdP settings.
- **InMemoryRelyingPartyRegistrationRepository** holds registrations in memory until replaced by another mechanism.

**A static repository does not reload metadata based on cacheDuration/validUntil.** If the app holds this bean for days while the IdP rotates its signing key, stale metadata causes signature validation failures or violates metadata time bounds. With classpath snapshots, updates typically require a new artifact/redeploy or a dedicated repository replacement mechanism.

**Responsibility boundary:** Spring Security handles the SAML2 login flow, yet loading metadata from a location does not automatically provide a **complete refresh + trust verification + validUntil enforcement policy**. That part must be explicitly designed and verified for your version/framework.

## 8. Spring Security 6.4+: CachingRelyingPartyRegistrationRepository

Starting in **Spring Security 6.4**, **CachingRelyingPartyRegistrationRepository** (package **org.springframework.security.saml2.provider.service.registration**) invokes a loader on cache miss and relies on **Spring Cache** for entry lifecycle.

### 8.1. Spring Boot Example Using Cache TTL

Dependencies in **pom.xml** (using a Spring Boot 3.x BOM/parent with compatible Spring Security **6.4+**):

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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
  </dependency>
  <dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
  </dependency>
</dependencies>
~~~

In **src/main/java/com/example/saml/SamlSecurityConfig.java**:

~~~java
package com.example.saml;

import java.time.Duration;
import java.util.function.Supplier;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.IterableRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        Supplier<IterableRelyingPartyRegistrationRepository> loader = () -> {
            RelyingPartyRegistration company =
                RelyingPartyRegistrations
                    .fromMetadataLocation(
                        "https://idp.example.org/company/metadata")
                    .registrationId("company")
                    .build();
            return new InMemoryRelyingPartyRegistrationRepository(company);
        };

        CachingRelyingPartyRegistrationRepository repository =
            new CachingRelyingPartyRegistrationRepository(loader);

        CaffeineCache cache = new CaffeineCache(
            "samlRegistrations",
            Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofMinutes(30))
                .build());
        repository.setCache(cache);

        return repository;
    }

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**True characteristics of this code:**

- Caffeine entries are evicted roughly **30 minutes after write**, depending on cache config and subsequent access timing.
- When a lookup occurs after eviction, the repository invokes **loader** and re-reads metadata from the URL. This is **lazy reload**, not guaranteed punctual background refresh.
- The URL **https://idp.example.org/company/metadata** is illustrative and must be replaced with an **organization-approved** metadata URL. Without a real IdP, login cannot complete.
- If the issuer is unreachable when the loader runs, fetching the new registration may throw an exception/impact logins; the snippet above **does not implement last-known-good, retries, validUntil validation, XML signature checks, or XML fetch controls**.
- **The 30-minute mark is a local TTL**; there is no automatic parsing of **validUntil/cacheDuration** to size cache TTLs in this snippet.
- For production, wrap fetching/verification in a **policy-enforcing, deadline-aware metadata layer** instead of the illustrative loader, and fail closed when no valid copy remains.

**Important:** CachingRelyingPartyRegistrationRepository by default may use a non-expiring cache if you **do not configure a cache TTL**; having "Caching" in the class name does not prove metadata is continually refreshed.

### 8.2. When On-Time Refresh Is Required Without Waiting for User Logins

For strict operational requirements, build a **metadata refresh service** or custom repository:

1. Run scheduled jobs calculated from cacheDuration, validUntil, and local caps.
2. Fetch in a background thread/task without blocking user requests indefinitely on network I/O.
3. Verify new metadata and build complete registrations in staging memory.
4. Publish the new version via atomic swap only after all checks pass.
5. Keep serving the old copy **while stale-yet-valid** if policy allows; retry with backoff and alert.
6. Stop trusting the old copy at validUntil, even if background refresh fails.
7. Track and alert on remaining validity; prepare ahead of time for certificate rotation.

For example, **do not hardcode a 30-minute @Scheduled interval** and assume it is safe for every IdP. Across different metadata files, scheduling should consider the **minimum bound** among cache hint, policy, and hard expiration.

### 8.3. Multi-IdP Support

Each IdP may have different **validUntil**, **cacheDuration**, certificates, and SLA levels. A multi-IdP repository should track each registration/entity separately; broken metadata for one IdP should not necessarily halt SSO for the whole system. Serve only registrations whose metadata remains valid. If a single signed bundle (**EntitiesDescriptor**) contains multiple IdPs, enforce expiration/limits on both the aggregate and each child.

## 9. Java 17: Runnable Example Calculating Refresh Deadlines

The program below **only illustrates how to compute timestamps** from values already extracted by a parser/trust validator. It **does not download XML, verify XML signatures, or build a RelyingPartyRegistration**. Fixed UTC timestamps are used so stdout is deterministic.

**File: MetadataRefreshPolicy.java**

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

public final class MetadataRefreshPolicy {

    private MetadataRefreshPolicy() { }

    public static Instant nextRefresh(
            Instant fetchedAt,
            Duration cacheDuration,
            Duration localMaxInterval,
            Instant effectiveValidUntil,
            Duration safetyMargin) {

        if (cacheDuration.isNegative()
                || cacheDuration.isZero()
                || localMaxInterval.isNegative()
                || localMaxInterval.isZero()
                || safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Invalid refresh policy");
        }
        if (!fetchedAt.isBefore(effectiveValidUntil)) {
            throw new IllegalArgumentException("Metadata already expired");
        }

        Instant byCache = fetchedAt.plus(cacheDuration);
        Instant byPolicy = fetchedAt.plus(localMaxInterval);
        Instant byExpiry = effectiveValidUntil.minus(safetyMargin);

        Instant planned = List.of(byCache, byPolicy, byExpiry)
                .stream()
                .min(Instant::compareTo)
                .orElseThrow();

        return planned.isBefore(fetchedAt) ? fetchedAt : planned;
    }

    public static boolean isUsable(
            Instant now, Instant effectiveValidUntil) {
        return now.isBefore(effectiveValidUntil);
    }

    public static void main(String[] args) {
        Instant fetchedAt =
            Instant.parse("2026-11-07T08:00:00Z");
        Instant validUntil =
            Instant.parse("2026-11-08T00:00:00Z");

        Instant next = nextRefresh(
            fetchedAt,
            Duration.parse("PT6H"),
            Duration.ofHours(4),
            validUntil,
            Duration.ofMinutes(30));

        System.out.println("refreshAt=" + next);
        System.out.println("validAtRefresh="
            + isUsable(next, validUntil));
        System.out.println("validAtExpiration="
            + isUsable(validUntil, validUntil));
    }
}
~~~

Compile and run (requires JDK 17+):

~~~bash
javac MetadataRefreshPolicy.java
java MetadataRefreshPolicy
~~~

**Exact stdout:**

~~~text
refreshAt=2026-11-07T12:00:00Z
validAtRefresh=true
validAtExpiration=false
~~~

Interpretation: IdP suggests a 6-hour cache, organization caps at 4 hours, deadline is 16 hours away; hence **12:00 UTC** is the earliest refresh target. At the exact validUntil instant, **isUsable** returns false.

**Intentional limitations of the example:** the method takes a normalized **Duration**. Java's **Duration.parse("PT6H")** works for ISO-8601 hours/minutes/days as appropriate; do not pretend it parses all of **xs:duration** (especially month-based **P1M**). A production system must use an appropriate XML Schema parser and define calendar semantics before passing converted durations. When metadata omits validUntil, enforce a dedicated policy rather than passing an infinite timestamp. For nested metadata, **effectiveValidUntil** is the bound properly resolved across ancestor/child elements.

## 10. Production Refresh Sequence

~~~mermaid
flowchart TD
    A[Receive metadata from approved source] --> B{Source and signature valid?}
    B -- No --> F[Retain old version if still valid, alert]
    B -- Yes --> C{XML, issuer, and time conditions valid?}
    C -- No --> F
    C -- Yes --> D[Build new registration]
    D --> E[Publish atomically, schedule refresh]
    F --> G{Old version still before validUntil?}
    G -- Yes --> H[Policy may allow stale use, retry backoff]
    G -- No --> I[Reject expired metadata, alarm]
~~~

Carry out these specific steps.

### Phase 1 – Safe Fetch

- Connect only to **pre-approved metadata locations**; never use arbitrary URLs sent by browsers to prevent SSRF and unintended trust expansion.
- Use **HTTPS**, verify TLS certificate/hostname, limit redirects, timeouts, response size, and download rate.
- If metadata carries XML signatures, verify the **metadata signature** against the trust anchor/federation process; never assume HTTPS from some URL means content is validly signed or self-trust certificates inside that XML.
- Block **XXE**, external entities, and dangerous XML constructs via a securely configured parser.
- Audit fetch timestamp, source, version/hash, and verification status.

### Phase 2 – Validate

- Select the exact approved IdP **entityID**; check endpoints, bindings, key usages, verification certs, and SP policies.
- Parse **validUntil** with timezone; compute effective validity across ancestor/child elements rather than taking only root or child.
- Parse **cacheDuration** as xs:duration. Apply the smaller bound between metadata and internal policy.
- Reject metadata that is **already expired**, missing required certificates/endpoints, or violating trust policies.
- Verify whether changes to certificates, endpoints, or issuers align with approved rotation plans; do not trust unexpected changes simply because XML parsed cleanly.
- If using HTTP conditional requests, **304** must still be checked against the cached XML's remaining validUntil.

### Phase 3 – Publish and Schedule

- Build **RelyingPartyRegistration** from trusted XML.
- Ensure **registrationId, SP entityID, ACS, and signing/decryption credentials** remain stable and are not inadvertently altered by IdP metadata.
- Atomically replace the repository/cache entry with the new version; never delete the active entry before attempting to load the new one.
- Compute **nextRefreshAt** from cacheDuration, local cap, and validUntil-margin with safe jitter.
- Rate-limit retries using exponential backoff with a cap; never let backoff cross hard expiration without alerting.
- Emit metrics: last successful refresh, metadata age, seconds remaining until validUntil, consecutive error count, and certificate rollover.

### Phase 4 – On Error or Expiration

- Transient error **before validUntil:** old version may remain valid; apply stale-while-revalidate per policy, log/emit metrics, and retry.
- Signature error or issuer mismatch: do not publish the new version; investigate source/security incident, never auto-swap trust anchors.
- **Reached validUntil:** stop using that metadata for new authentications; requires intervention or a newly validated metadata source.
- When the IdP provides multiple certificates during overlap, retain all approved verification keys to avoid breaking SSO mid-rotation.
- When a metadata refresh changes endpoints, coordinate with the IdP and verify SAML Response validation; never turn refresh into a shortcut bypassing signatures/Audience.

## 11. Retry/Backoff, Jitter, and Monitoring Strategy

Suppose a federation has 50 SP replicas. If all fetch metadata at 00:00 on the same cacheDuration, the IdP service can be overloaded. Distribute **attempt** times:

- Schedule with **small controlled jitter** without pushing refreshes past validity limits.
- When downloads fail, retry at intervals like 1, 2, 4, 8 minutes... up to an app-defined cap, with jitter and timeouts.
- After several consecutive failures, escalate alert severity; as the deadline nears, page on-call rather than logging INFO.
- Never equate HTTP 200 with success: increment **refresh_success** only after validating XML, validity window, and building the registration.
- Never force refreshes on every HTTP request; use a policy-driven cache/repository to avoid continuous network fetches and XML parsing.

Suggested metrics:

| Metric | Meaning | Usage |
| --- | --- | --- |
| **saml_metadata_last_success_timestamp** | Timestamp of last successful fetch/verify/build | Detect stale sources failing to update |
| **saml_metadata_validity_seconds_remaining** | Seconds remaining until effective validUntil | Alert ahead of hard expiration |
| **saml_metadata_refresh_failure_total** | Total failed refreshes | Measure network/IdP/validation health |
| **saml_metadata_stale_seconds** | Time elapsed past scheduled refresh | Track allowed staleness duration |
| **saml_metadata_current_version/hash** | Identifier of approved metadata version | Audit rotation and rollback |
| **saml_metadata_certificate_rotation_pending** | Whether the IdP is preparing a key change | Monitor overlap before retiring old keys |

These metric names are **illustrative suggestions**, not built-in Spring Security default metrics.

## 12. Scenarios and Exercises

### A. cacheDuration Elapsed Yet Before validUntil

Metadata fetched at 08:00, cacheDuration PT2H, validUntil 23:00. At 10:05 fetching fresh metadata fails.

**Analysis:** The active copy is stale per cache hint yet still before hard expiration. The organization **may** permit using last-known-good within bounded limits while retrying; confirm that copy was previously verified. Never declare metadata invalid merely because 10:00 passed.

### B. validUntil Elapsed Yet Cache Not Expired

Metadata has validUntil 11:00 and cacheDuration PT12H; copy received at 08:00. At 11:00 no new copy is available.

**Analysis:** Metadata is **invalid from 11:00 onward**; do not keep it for new SSO until 20:00 just because cache TTL hasn't elapsed. Hard expiration overrides every cache policy.

### C. Aggregator Expires Earlier Than Child IdP

EntitiesDescriptor validUntil 18:00; IdP A's EntityDescriptor has validUntil 23:00.

**Analysis:** The parent's limit is stricter, so IdP A cannot be used after 18:00 based on that aggregate.

### D. IdP Certificate Rotated Overnight

Old metadata had verification key K1, new metadata includes K1 and K2 for rotation; later the IdP signs only with K2.

**Analysis:** The SP should refresh and verify metadata **before** K2 becomes active; plan certificate overlap and monitoring. Holding an old snapshot until validUntil without ever refreshing can cause an outage even though that metadata hasn't expired.

### E. HTTP 304 When XML Is Expired

IdP returns 304 Not Modified after the old XML's validUntil of 00:00.

**Analysis:** 304 does not mint a new validUntil. The old content remains expired; the SP must stop trusting it or obtain valid new metadata from an approved source.

### F. Metadata Lacks validUntil

An IdP publishes only cacheDuration PT1H without validUntil. Is it valid forever?

**Analysis:** Per the validUntil attribute, there is no corresponding hard expiration; however, systems should not treat that configuration as indefinitely trustworthy. Policy may **mandate validUntil** or enforce a max lifetime/refresh cadence and max stale window. Never add cacheDuration to create a spec validUntil.

### G. 30-Minute Caffeine Cache vs. IdP Metadata cacheDuration PT6H

Does Spring automatically honor PT6H?

**Analysis:** No. The 30-minute cache TTL was configured by the developer, not derived from metadata XML. After eviction, the loader runs on lookup; if it fetches the same expired metadata or skips XML validation, the fresh cache entry can still hold unsuitable configuration.

### H. Last-Known-Good Expired, Yet Business Demands Zero SSO Downtime

**Analysis:** Uptime demands cannot justify disabling validUntil or signature validation. Operational solutions are early refreshes, multiple trusted distribution sources, pre-deadline alerts, coordinated rollovers, approved fallback IdPs, and clear policies for existing sessions. Never "fix" by manually editing XML expiry.

### I. validUntil Equals Exact Current Time

At **2026-11-08T00:00:00Z**, metadata validUntil is that exact timestamp.

**Analysis:** Already expired. Validity checks require **now.isBefore(validUntil)**, not **now <= validUntil**.

### J. New Metadata Has Unfamiliar Issuer Yet XML Signature Verifies with a New Key Embedded in That Metadata

**Analysis:** Never self-expand trust. Verify metadata via approved trust anchors/sources and entityID restrictions. An attacker crafting XML and self-signing with a key inside the XML does not establish a trusted federation relationship.

## 13. Pre-Deployment Checklist

- [ ] Identified approved **IdP metadata source and trust anchor**; TLS and XML signature/validation follow policy.
- [ ] Parser accurately handles **xs:dateTime**, **xs:duration**, timezones, and root/ancestor/entity validUntil/cacheDuration.
- [ ] **validUntil** enforced as hard expiration; cacheDuration used only to schedule refresh attempts.
- [ ] **Local max refresh interval** and rules/limits for metadata without validUntil defined.
- [ ] **Safety margin** set to refresh before expiry; jitter/backoff never cross hard deadlines.
- [ ] Spring Security repository genuinely supports **reloading**; InMemory repository is not mistaken for a metadata refresher.
- [ ] If using CachingRelyingPartyRegistrationRepository, configured cache TTL/eviction and accounted for **lazy reload**.
- [ ] On refresh failure, last-known-good used **only while still valid** and permitted by local stale policy.
- [ ] Publishing new registrations is **atomic**; unverified XML/certificates/issuers are never accepted.
- [ ] **Certificate rotation** plan, multiple valid keys during overlap, and approved rollback in place.
- [ ] Tested stale-but-valid, expired, missing validUntil, parent earlier expiry, HTTP 304, metadata signature errors, and IdP unavailability.
- [ ] Alerts configured **ahead of validUntil** with outage runbooks; tokens/SAMLResponses/private keys never logged.
- [ ] Distinguished **metadata lifetime**, **certificate lifetime**, **SAML Assertion lifetime**, and **browser session lifetime**.

**Final takeaway:** **validUntil is a limit that must not be crossed; cacheDuration is a reminder to refresh.** In Spring Security, calling **RelyingPartyRegistrations.fromMetadataLocation(...)** only builds configuration from metadata; resilient SSO requires a full lifecycle of fetching, verifying, caching, refreshing, retrying, and failing closed per specification.

## 14. Authoritative References

- [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): defines EntityDescriptor, EntitiesDescriptor, validUntil, and cacheDuration.
- [OASIS SAML 2.0 Errata 05 – HTML](https://docs.oasis-open.org/security/saml/v2.0/errata05/csd01/saml-v2.0-errata05-csd01.html): clarifies the distinction between cache expiration and metadata invalidity; parent/child limits.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistrations, repositories, and CachingRelyingPartyRegistrationRepository.
- [Spring Security 6.5 API – CachingRelyingPartyRegistrationRepository](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): caching, constructors, setCache, and defaults.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): IdP/SP metadata, registrations, and metadata endpoints.
- [Shibboleth Identity Provider – Metadata Management Best Practices](https://shibboleth.atlassian.net/wiki/spaces/IDP5/pages/3199507429): managing remote metadata, rotation, refresh, and expiration.
