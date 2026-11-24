# Building a Refreshable Registration Repository and Evaluating Version-Specific APIs

> **Module:** Spring Security – federation. **Topic Group:** SAML2 Metadata. This lesson focuses on how to structure a `RelyingPartyRegistrationRepository` capable of updating Identity Provider (IdP) metadata while the application is running, how to ensure updates do not break trust relationships, and how to pick the exact API for your Spring Security version.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why loading SAML metadata once at startup **is not equivalent** to refreshing metadata continuously at runtime.
2. Distinguish **IdP-side metadata**, **SP-side registration**, **repository**, **cache**, **scheduler**, **last-known-good snapshot**, **signature/issuer trust**, **metadata expiration**, and **credential rotation**.
3. Design a validate-before-replace refresh mechanism: fixed source, matching issuer, immutable SP registration details, valid trusted certificate set, validity lifetime, and source-failure policy.
4. Use core APIs available since Spring Security 6.3 to implement an application-managed repository swapping snapshots with `AtomicReference`.
5. Know the APIs added in **Spring Security 6.4+**, including `IterableRelyingPartyRegistrationRepository`, `CachingRelyingPartyRegistrationRepository`, and `AssertingPartyMetadataRepository`, as well as when to use OpenSAML 5 metadata resolvers.
6. Never confuse **refreshing by cache TTL** with **refreshing by metadata `validUntil`/`cacheDuration`**, nor confuse "receiving a new certificate" with "verifying the trustworthiness of the new certificate".
7. Build a test suite proving accurate refresh, network fault tolerance, tenant isolation, misconfiguration rejection, and prevention of unauthorized access.

## 1. The Problem: IdP Updates Metadata While Logins Are Running

Suppose **Orders Portal** is a SAML2 Service Provider (SP) trusting partner A's IdP. Initially, the IdP metadata describes:

~~~text
IdP entityID:       https://idp.partner-a.example.org/saml
SingleSignOnService https://idp.partner-a.example.org/sso
Signing certs:      certificate A
Metadata source:    https://idp.partner-a.example.org/metadata
~~~

After some time, the IdP performs a **certificate rollover**: publishing metadata containing both certificate A and certificate B during the overlap window, and eventually only B. The IdP may also change its SSO or Single Logout endpoint. If the SP reads metadata only at startup, the repository keeps the old snapshot and verifies responses with certificate A; once the IdP stops signing with A, new logins fail.

A temporary workaround is restarting the SP after each metadata change. With many IdPs/tenants, however, that causes disruption, depends on manual action, and is error-prone. Controlled **refresh** is therefore needed.

Conversely, blindly fetching XML every 5 minutes and accepting any new content is dangerous. If metadata comes from an untrusted source, the new certificate could belong to an attacker, causing the SP to replace its **trust anchor**. A proper refresh mechanism must update promptly while preserving trust sources, tenant boundaries, consistency, and resilience.

**General rule:** fetch → verify source/validity → build new registration → verify invariants remain unchanged → swap the entire snapshot → observe results. On any error, **do not publish the new snapshot**.

## 2. Understand the Components Before Coding

| Component | Role | Who manages it? | Why does it matter during refresh? |
| --- | --- | --- | --- |
| **IdP metadata XML** | Describes IdP entity ID, SSO/SLO services, bindings, signing/encryption certs; may carry `validUntil`, `cacheDuration`. | IdP or delegated metadata publisher. | Dynamic input data that must be verified before consumption. |
| **`RelyingPartyRegistration`** | Configuration of one SP–IdP pair: registration ID, SP entity ID, ACS, SP credentials, IdP details. | SP combining its config with IdP trust data. | IdP metadata changes **must not accidentally wipe** SP keys/ACS/entity ID. |
| **`RelyingPartyRegistrationRepository`** | Interface looking up registrations by ID. | Application/Spring Boot. | Login, callback, and metadata filters query the active configuration here. |
| **`InMemoryRelyingPartyRegistrationRepository`** | Registrations stored in memory, iterable for login pages/metadata. | Provided by Spring Security. | A new instance acts as a clean snapshot, easy to swap atomically. |
| **Refresh source/loader** | Fetches, parses metadata, and builds candidate registrations. | Application or OpenSAML library. | Isolates network/parsing from the HTTP request path. |
| **Cache/metadata resolver** | Retains recent results and applies refresh policies. | Spring Cache or OpenSAML depending on version. | TTL, `validUntil`, retry, and eviction have different semantics. |
| **SP signing/decryption credentials** | Private keys/certificates used by the SP to sign or decrypt. | SP/secret manager. | Must never be lost or altered by refreshing **IdP** metadata. |
| **IdP verification credentials** | Public certificates used by the SP to verify assertions/responses. | Part of the trust contract with the IdP. | Rotation requires a verified trust source, overlap window, and testing. |

### Metadata URL Differs from Registration ID

`registrationId=partner-a` is an internal Spring key. `entityID=https://idp.partner-a.example.org/saml` is the IdP's protocol identity. `metadata URI=https://idp.partner-a.example.org/metadata` is the **data download location**. All three values can be completely different.

During refresh, never grab an arbitrary new issuer from XML and **silently change** the meaning of `partner-a`. If the business contract does not authorize changing the IdP entity ID, enforce the expected issuer and reject mismatched metadata.

## 3. Why Is Static Configuration Not Refresh?

In Spring Boot, simple configuration typically looks like:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}
~~~

When initializing the repository bean, Spring Boot uses this config/metadata to construct `RelyingPartyRegistration`. This config **does not promise that the bean reloads when the IdP updates metadata**, nor that Spring Boot updates certificates for existing login sessions.

Similarly, the Java snippet:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation("https://idp.partner-a.example.org/metadata")
    .registrationId("partner-a")
    .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

fetches/parses metadata to build **a registration at the moment of invocation**; `InMemoryRelyingPartyRegistrationRepository` does not watch the metadata URL. This works for rarely changing setups, whereas refresh requires organizing **subsequent fetches** and **a mechanism to update the registration set**, or using newer supporting APIs.

### Distinguishing Four "Automatic" Concepts

1. **Auto-load metadata at startup:** configuration is built once during initialization.
2. **Auto-reload on cache miss/eviction:** cache controls when the loader runs; this can be lazy (fetching only when a request arrives).
3. **Auto-refresh by metadata expiration:** a metadata resolver reads `validUntil`/`cacheDuration` and schedules/enforces bounds per library capabilities.
4. **Safe automated operations:** beyond refresh, includes trust validation, rollback/last-known-good, stale bounds, alerts, testing, and rotation coordination. Having one of the first three mechanisms **is not enough** to claim the fourth is achieved.

## 4. Designing a Refreshable Registration Repository

### 4.1. Data Flow Diagram

~~~text
                    Control plane (not on the HTTP request thread)
IdP metadata URL ---> [1] Fetch with TLS/timeouts/allow-list
                             |
                         [2] Parse XML
                             |
                  [3] Verify trust + metadata signature
                             |
                    [4] Validate issuer/expiry
                             |
                  [5] Attach SP entityID, ACS, keys
                             |
                  [6] Build candidate snapshot
                             |
              +------ success? -----------------+
              |                                 |
             YES                               NO
              |                                 |
      [7] Atomic publish                  Keep old snapshot
              |                            + alert + bound age
              v
         AtomicReference
              |
              v
  RelyingPartyRegistrationRepository
          /           |            \
   AuthnRequest      ACS/login      SP metadata
       lookup         lookup          lookup
~~~

The **control plane** handles fetching, building, and publishing registrations. The **data plane** handles SSO requests and only reads the published snapshot. As a result, user requests never block whenever the IdP network is slow.

### 4.2. Six Guarantees to Enforce

1. **Consistency:** every lookup observes a complete registration snapshot; never "half new cert, half old endpoint".
2. **Fail-safe:** fetch/parse/verify failures must never publish an empty snapshot or broaden permissions.
3. **Fixed trust:** fetch metadata only from admin-approved sources and issuers; never let requests pick fetch URLs.
4. **Bounded freshness:** an old snapshot may be retained during a recovery window, yet once past the allowed limit it must stop accepting new logins and raise an alert.
5. **Stable SP ownership:** SP entity ID, ACS, and signing/decryption keys are SP config; IdP metadata must never overwrite them.
6. **Observability and testability:** track last refresh success/failure, snapshot age, issuer, certificate count, and validity; never log private keys or raw assertions.

### 4.3. System Behavior During Refresh

| Event | Recommended Behavior | Avoid |
| --- | --- | --- |
| Valid new metadata, same issuer, trust passes | Build and swap the **entire** snapshot. | Mutating a collection currently being read by concurrent requests. |
| Metadata identical to current copy | May update last-checked-success timestamp while keeping config unchanged. | Treating every fetch as a key rotation. |
| HTTP timeout, malformed XML, invalid metadata signature | Keep last-known-good; log error event and retry with backoff. | Clearing the repository or accepting invalid XML. |
| Metadata returns a different issuer | Reject candidate; alert on trust contract change. | Silently changing `partner-a`'s issuer. |
| New cert appears during valid rollover window | Accept per trust policy; verify against both old/new certs during overlap. | Deleting old cert while the IdP still signs with it. |
| Metadata expired or last-known-good too old | Fail closed for new logins; alert and clarify recovery plan. | Trusting stale copies indefinitely. |
| AuthnRequest issued before refresh, response arrives after refresh | Check request/state correlation and handle cert/endpoint transition controllably. | Disabling signature, audience, or correlation checks to let login pass. |

## 5. Evaluating APIs by Spring Security Version

**Never read "current" Javadoc and assume the code compiles on an older version.** Check actual resolved versions from Spring Boot dependency management or Gradle/Maven dependency trees, then consult that exact branch's docs.

| Platform / API | Status and Role | How to Apply |
| --- | --- | --- |
| **Spring Security 5.4+** – `RelyingPartyRegistrations.fromMetadataLocation(String)` | Utility building `RelyingPartyRegistration.Builder` from a metadata location. | Use for a single fetch; **not a scheduler**. |
| **Spring Security 5.6+** – `RelyingPartyRegistrations.fromMetadata(InputStream)` | Builds a builder from an app-loaded metadata stream. | Fits XML from DB/blob; caller must close the stream. |
| **Spring Security 5.7+** – `collectionFromMetadataLocation` | Returns a collection of builders when metadata has multiple EntityDescriptors/IdPs. | Filter for the expected issuer before assigning a stable registration ID. |
| **Spring Security 6.3** (typically paired with **Boot 3.3**) | Has `RelyingPartyRegistrationRepository`, `InMemoryRelyingPartyRegistrationRepository`, builder/metadata utilities; lacks 6.4's dedicated caching/metadata repo classes. | Custom repository + atomic snapshot/scheduler or controlled reload. |
| **Spring Security 6.4+** (typically with **Boot 3.4**) – `IterableRelyingPartyRegistrationRepository` | Interface supporting both lookup and iteration, introduced in 6.4. | Supports login pickers/SP metadata and typed repo integration. |
| **Spring Security 6.4+** – `CachingRelyingPartyRegistrationRepository` | Lazy-loading wrapper via Spring Cache, introduced in 6.4. | Reloads based on eviction/TTL **of the configured cache**. |
| **Spring Security 6.4+** – `AssertingPartyMetadataRepository` and `RelyingPartyRegistration.withAssertingPartyMetadata(...)` | Decouples IdP metadata source from SP-side config. | Facilitates resolvers that refresh based on metadata validity. |
| **Spring Security 6.4+ / OpenSAML 5** – `OpenSaml5AssertingPartyMetadataRepository` | Provides a metadata resolver supporting expiry-based refresh and metadata signature verification options. | Choose when runtime actually uses OpenSAML 5 and trust is properly configured. |
| **Spring Security 7.x** | Continues 6.4-style APIs; updated OpenSAML baseline and added utilities in minors. | Check exact 7.x migration guide/Javadoc; do not blindly copy 6.3 code. |

**Three version notes:**

- Spring Boot `3.3.x` manages a typical `6.3.x` Spring Security baseline; Boot `3.4.x` manages `6.4.x`. BOM overrides, plugins, and explicit dependencies can shift the resolved version.
- `CachingRelyingPartyRegistrationRepository` has **Since: 6.4**. Copying it into a Spring Security 6.3 project fails with `cannot find symbol`; solve by using a custom repo as in Section 6 or upgrading dependencies together.
- `AssertingPartyMetadataRepository` also has **Since: 6.4**. `OpenSaml5AssertingPartyMetadataRepository` requires compatible OpenSAML 5 artifacts on the classpath; seeing a class name in docs does not prove your runtime has it.

### 5.1. How to Check the Active Version

With Gradle wrapper:

~~~bash
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat` if using the Windows wrapper. Inspect the **resolved version** output after dependency management, not just versions written in `build.gradle`.

You can check the presence of class files or dependency JARs for:

~~~text
org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository
org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository
org.springframework.security.saml2.provider.service.registration.AssertingPartyMetadataRepository
~~~

Verify class and method availability via version-matching Javadoc and compile tests in CI before committing to an architecture.

## 6. Runnable Java 17 + Spring Boot 3.3.x Example: Refreshable Snapshot Repository

This is a **complete Servlet SP application in terms of source/build**, built on APIs present in the Spring Security 6.3 line. Real SAML login requires valid IdP metadata, reachable endpoints, SP registration at the IdP, and matching certs/keys. The design illustrates **scheduled metadata reload, retaining the latest valid copy, and rejecting snapshots that are too stale**.

> **Security boundary:** This 6.3 sample demonstrates snapshot/atomic refresh with a **trusted admin-managed HTTPS metadata URL** and a **fixed expected issuer**. It does not itself implement **metadata XML signature verification** or XML-level `validUntil` and `cacheDuration` parsing. If your source requires metadata signature verification, verify metadata before building registrations or switch to a supporting resolver (Section 8); never take this sample straight to production to trust new certificates from an unverified source.

### 6.1. Project Layout

~~~text
refreshable-saml-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlrefresh/
    │   ├── SamlRefreshApplication.java
    │   ├── SecurityConfig.java
    │   ├── RefreshingRegistrationRepository.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'refreshable-saml-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

The Shibboleth Maven repository may be needed for certain OpenSAML dependencies in Spring Security; check the exact release version and dependency docs. **Do not pull Spring Security 6.4/7.x into a Boot 3.3 project just for a new API** without checking full dependency graph compatibility.

### 6.2. Spring Boot Main Enabling Scheduler

`src/main/java/com/example/samlrefresh/SamlRefreshApplication.java`:

~~~java
package com.example.samlrefresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class SamlRefreshApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlRefreshApplication.class, args);
    }
}
~~~

`@EnableScheduling` allows `@Scheduled` to run periodic refresh tasks. Without it, the scheduler annotation in this example will not activate.

### 6.3. Metadata Source and Policy Configuration

`src/main/resources/application.yml`:

~~~yaml
saml:
  partner:
    registration-id: partner-a
    metadata-location: ${PARTNER_A_METADATA_URL}
    expected-idp-entity-id: ${PARTNER_A_ENTITY_ID}
    sp-entity-id: ${SP_ENTITY_ID}
    acs-url: ${SP_ACS_URL}
    refresh-delay-ms: 900000
    refresh-initial-delay-ms: 900000
    max-stale-seconds: 86400
~~~

These environment variables must be supplied by an administrator:

| Variable | Example for understanding meaning |
| --- | --- |
| `PARTNER_A_METADATA_URL` | `https://idp.partner-a.example.org/metadata` |
| `PARTNER_A_ENTITY_ID` | `https://idp.partner-a.example.org/saml` |
| `SP_ENTITY_ID` | `https://orders.example.org/saml2/service-provider-metadata/partner-a` |
| `SP_ACS_URL` | `https://orders.example.org/login/saml2/sso/partner-a` |

`refresh-delay-ms` is the delay between scheduler runs (15 minutes). `max-stale-seconds` caps snapshot age based on **the latest successful refresh timestamp** (illustrative: 24 hours). This is an **SP-side operational limit**, **not a replacement for metadata `validUntil`**. For local URLs and HTTP, the example deliberately requires HTTPS to preserve security boundaries; use a test IdP with HTTPS to run real logins.

### 6.4. Repository: Never Mutate the Instance Serving Requests

`src/main/java/com/example/samlrefresh/RefreshingRegistrationRepository.java`:

~~~java
package com.example.samlrefresh;

import java.net.URI;
import java.time.Instant;
import java.util.Collections;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicReference;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.stereotype.Component;

@Component
public final class RefreshingRegistrationRepository
        implements RelyingPartyRegistrationRepository,
                   Iterable<RelyingPartyRegistration> {

    private static final Logger log =
        LoggerFactory.getLogger(RefreshingRegistrationRepository.class);

    private record Snapshot(
            InMemoryRelyingPartyRegistrationRepository repository,
            Instant loadedAt) {
    }

    private final String registrationId;
    private final String metadataLocation;
    private final String expectedIdpEntityId;
    private final String spEntityId;
    private final String acsUrl;
    private final long maxStaleSeconds;

    private final AtomicReference<Snapshot> current = new AtomicReference<>();

    public RefreshingRegistrationRepository(
            @Value("${saml.partner.registration-id}") String registrationId,
            @Value("${saml.partner.metadata-location}") String metadataLocation,
            @Value("${saml.partner.expected-idp-entity-id}") String expectedIdpEntityId,
            @Value("${saml.partner.sp-entity-id}") String spEntityId,
            @Value("${saml.partner.acs-url}") String acsUrl,
            @Value("${saml.partner.max-stale-seconds:86400}") long maxStaleSeconds) {

        this.registrationId = registrationId;
        this.metadataLocation = metadataLocation;
        this.expectedIdpEntityId = expectedIdpEntityId;
        this.spEntityId = spEntityId;
        this.acsUrl = acsUrl;
        this.maxStaleSeconds = maxStaleSeconds;

        requireHttps("metadata-location", metadataLocation);
        requireHttps("sp-entity-id", spEntityId);
        requireHttps("acs-url", acsUrl);

        if (maxStaleSeconds <= 0) {
            throw new IllegalArgumentException("max-stale-seconds must be > 0");
        }

        // Startup must obtain the first trusted metadata snapshot.
        // If fetch/parse/validate fails, do not build an empty repository.
        current.set(loadCandidate());
    }

    private static void requireHttps(String name, String value) {
        URI uri = URI.create(value);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                name + " must be an absolute HTTPS URI");
        }
    }

    private Snapshot loadCandidate() {
        // Each invocation builds a new registration from IdP metadata.
        RelyingPartyRegistration registration = RelyingPartyRegistrations
            .fromMetadataLocation(metadataLocation)
            .registrationId(registrationId)
            .entityId(spEntityId)
            .assertionConsumerServiceLocation(acsUrl)
            .build();

        // IdP must not silently change its contracted identity.
        String actualIssuer = registration.getAssertingPartyDetails()
            .getEntityId();
        if (!expectedIdpEntityId.equals(actualIssuer)) {
            throw new IllegalStateException(
                "Unexpected SAML IdP entity ID");
        }

        // Do not publish a registration with no verification credentials.
        if (registration.getAssertingPartyDetails()
                .getVerificationX509Credentials().isEmpty()) {
            throw new IllegalStateException(
                "SAML IdP has no verification credentials");
        }

        InMemoryRelyingPartyRegistrationRepository repository =
            new InMemoryRelyingPartyRegistrationRepository(registration);

        return new Snapshot(repository, Instant.now());
    }

    @Scheduled(
        fixedDelayString = "${saml.partner.refresh-delay-ms:900000}",
        initialDelayString =
            "${saml.partner.refresh-initial-delay-ms:900000}"
    )
    public synchronized void refresh() {
        try {
            Snapshot candidate = loadCandidate();

            // Publish only after the entire candidate passes validation.
            current.set(candidate);
            log.info("SAML registration {} refresh succeeded", registrationId);
        }
        catch (RuntimeException ex) {
            // Keep last-known-good; never replace with an empty repo.
            log.warn("SAML registration {} refresh failed: {}",
                registrationId, ex.getClass().getSimpleName());
        }
    }

    private Snapshot usableSnapshot() {
        Snapshot snapshot = current.get();

        if (snapshot == null) {
            return null;
        }

        Instant deadline =
            snapshot.loadedAt().plusSeconds(maxStaleSeconds);

        // Stop new logins if the latest snapshot exceeds the stale threshold.
        if (!Instant.now().isBefore(deadline)) {
            return null;
        }

        return snapshot;
    }

    @Override
    public RelyingPartyRegistration findByRegistrationId(String id) {
        Snapshot snapshot = usableSnapshot();
        return snapshot == null
            ? null
            : snapshot.repository().findByRegistrationId(id);
    }

    @Override
    public Iterator<RelyingPartyRegistration> iterator() {
        Snapshot snapshot = usableSnapshot();
        return snapshot == null
            ? Collections.emptyIterator()
            : snapshot.repository().iterator();
    }
}
~~~

**How this example works:**

- `current` holds **a single reference to a snapshot containing the repository and load timestamp**. Request threads reading via `AtomicReference.get()` observe either a complete old or complete new version, never a half-modified object.
- `loadCandidate()` creates a new `RelyingPartyRegistration`, binds **registrationId**, **SP entity ID**, and **ACS** from SP config, and verifies the IdP issuer and verification credential count.
- `refresh()` calls `current.set(candidate)` **only when every build/validation step succeeds**. When the metadata source fails, it logs an error without leaking XML/certificates and retains last-known-good.
- `usableSnapshot()` returns `null` once the latest snapshot exceeds max stale. When `findByRegistrationId` returns `null`, login handling fails safely along the missing-registration path; exact HTTP response depends on Spring Security config. Never treat this as "re-granting login automatically".
- `Iterable<RelyingPartyRegistration>` lets components that enumerate registrations (such as login pickers/metadata) view the active snapshot. `iterator()` iterates over the snapshot read at that instant, not a mutating map.
- The sample uses **one IdP entity descriptor/registration**. If source metadata has multiple entities, select the exact issuer deterministically; `collectionFromMetadataLocation` may be needed instead of `fromMetadataLocation` (Section 9).

**What this sample does not yet fully address for production:**

1. `RelyingPartyRegistrations.fromMetadataLocation` does not automatically apply enterprise metadata signature verification policies in this snippet. TLS/issuer checks **are not equivalent to verifying XML metadata signatures**.
2. Does not parse and enforce metadata `validUntil` or `cacheDuration`; `maxStaleSeconds` is only an independent cap. In production, expire at **whichever comes earlier** between verified metadata expiration and SP operational limits.
3. Does not tune read/connect timeouts/backoff on the default metadata loader. For network metadata, use a fetcher with timeouts, size limits, redirect allow-listing, rate limiting, circuit breakers, or a dedicated resolver.
4. Some SAML flows have requests created before refresh. When rotating certs or SSO endpoints, support an overlap window and test in-flight request compatibility; an "atomic repository swap" does not solve all state-correlation issues on its own.
5. Multi-instance deployments can refresh at slightly different times. Production needs versioned metadata/distribution or per-node status monitoring.
6. If the IdP requires the SP to sign AuthnRequests or decrypt Assertions, attach **SP signing/decryption credentials** on the builder rather than expecting them from IdP metadata. This example assumes the IdP allows unsigned requests and unencrypted responses in a matching test setup.

All limitations above must be addressed before concluding a system can refresh **safely in production**.

### 6.5. SecurityFilterChain

`src/main/java/com/example/samlrefresh/SecurityConfig.java`:

~~~java
package com.example.samlrefresh;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Because a `RefreshingRegistrationRepository` bean implements `RelyingPartyRegistrationRepository`, Spring Boot uses that repository instead of auto-configuring one. **Never declare a custom repository bean and expect Spring Boot to automatically merge it with registrations from `spring.security.saml2.relyingparty.registration`**. If you want multiple registrations, construct them inside your repository.

### 6.6. Controller to Inspect the SAML Principal

`src/main/java/com/example/samlrefresh/DemoController.java`:

~~~java
package com.example.samlrefresh;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Open /private to start SAML 2.0 login";
    }

    @GetMapping("/private")
    public Map<String, Object> privatePage(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameId", principal.getName());
        result.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        return result;
    }
}
~~~

This is a learning endpoint. `NameID`/registration ID is processed SAML identity info; never return raw `SAMLResponse`, private keys, or sensitive attributes. **An authenticated principal does not automatically hold business permissions**; in real systems, enforce local/tenant authorization at endpoints and services.

### 6.7. Running and Verifying in Practice

Requires a **trusted** test IdP publishing HTTPS metadata, valid SP entity ID/ACS, matching signing profile, and environment variables:

~~~text
PARTNER_A_METADATA_URL=https://idp.partner-a.example.org/metadata
PARTNER_A_ENTITY_ID=https://idp.partner-a.example.org/saml
SP_ENTITY_ID=https://orders.example.org/saml2/service-provider-metadata/partner-a
SP_ACS_URL=https://orders.example.org/login/saml2/sso/partner-a
~~~

These URLs only illustrate the structure. Replace them with real endpoints before running. With the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows you can run `.\gradlew.bat bootRun`. When the IdP/metadata URL does not exist or cannot be loaded, **the application refuses to finish startup**; this is intentional to avoid starting an SP without a trusted registration.

In a properly integrated environment:

1. Open `/` to check the public endpoint. The exact returned string is `Open /private to start SAML 2.0 login`.
2. Open `/saml2/metadata/partner-a` and verify SP entity ID, ACS, bindings, and SP certificates if present.
3. Open `/private`: Spring Security routes the browser through the SAML2 flow; the IdP returns a validly signed response and assertion to the ACS.
4. Check the `/private` JSON: `nameId` depends on the real account, `registrationId` is `partner-a`.
5. Perform certificate rollover **at the test IdP**, confirming the scheduler picks up the update; before production, test metadata signature checks, validUntil, and rollover procedures.

In this demo, a successful scheduler run means **a new registration was built and published from the configured source**; it is not proof that all production trust policies are enforced.

## 7. Why Use Atomic Snapshots Instead of Mutating In Place?

Suppose 100 AuthnRequest and SAMLResponse requests run concurrently with a refresh task. If a mutable map of registrations is updated piece by piece, request 1 may read cert B with an old ACS, request 2 may read the new IdP entity ID with an old tenant, or an iterator may fail mid-traversal.

**Never mutate a `HashMap`/`ArrayList` while request threads read it and expect consistency.** Build the new dataset **independently**, validate everything first, and then swap a single pointer.

~~~java
// Illustrates only the publish logic; not a standalone class.
AtomicReference<Map<String, RelyingPartyRegistration>> state =
    new AtomicReference<>(Map.of());

// On the refresh thread:
Map<String, RelyingPartyRegistration> candidates = loadAndValidate();
state.set(Map.copyOf(candidates));

// On the request thread:
RelyingPartyRegistration selected = state.get().get("partner-a");
~~~

This snippet expresses only **the strategy**; the runnable implementation is in Section 6. When managing multiple registrations, build the **entire** map and swap atomically once; do not patch individual tenants into an active map if global consistency is required. If tenants must refresh independently, design per-tenant versioning/validation and isolation boundaries so a failing IdP A does not break B.

### 7.1. Do Not Keep Old Repository Instances Forever

`AtomicReference` guarantees only **visibility and pointer atomicity**, not cross-request SAML transactions. At T0 the SP sends an AuthnRequest using registration A, at T1 metadata updates, and at T2 the Response returns; if the SP already removed certificate A entirely, responses signed with A can fail. That may be intended by policy or cause disruption.

Therefore during rollover, coordinate carefully:

- IdP metadata publishes **both old and new certs** during the transition window if permitted by procedure.
- SP receives the new certificate from a trusted source and tests response signatures under both keys during overlap.
- Never keep old keys past `validUntil`/trust policy just to "avoid disruption".
- Plan removal of the old cert after the IdP retires it, testing in-flight requests, SLO, and unrefreshed instances.

## 8. Spring Security 6.4+: Dedicated Cache and Metadata Repository APIs

This section **is not runnable code for the Boot 3.3/Spring Security 6.3 example in Section 6**. Apply it only once your dependency tree genuinely uses Spring Security 6.4+ and a compatible OpenSAML version.

### 8.1. `CachingRelyingPartyRegistrationRepository`: Refresh by Eviction

In Spring Security **6.4+**, you can provide a loader creating a repository from metadata and wrap it in `CachingRelyingPartyRegistrationRepository`:

~~~java
// Spring Security 6.4+ example, inside a @Configuration; do not combine directly
// with the RefreshingRegistrationRepository bean from the 6.3 example.
@Bean
RelyingPartyRegistrationRepository samlRegistrations(CacheManager cacheManager) {

    CachingRelyingPartyRegistrationRepository registrations =
        new CachingRelyingPartyRegistrationRepository(() ->
            new InMemoryRelyingPartyRegistrationRepository(
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example.org/metadata")
                    .registrationId("partner-a")
                    .build()
            )
        );

    registrations.setCache(cacheManager.getCache("samlRegistrations"));
    return registrations;
}
~~~

Imports needed in this `@Configuration` class are `org.springframework.cache.CacheManager` and Spring Security's SAML registration classes. This is a **configuration snippet for a 6.4+ app** with an already-configured cache manager, not a standalone Java file.

**Crucially:** the default cache may be a `ConcurrentMapCache` **that never expires**. Without configuring TTL/eviction, the code above still risks holding stale metadata forever. The loader runs when the cache demands new data; **cache expiration does not necessarily trigger a proactive refresh before a user arrives**.

Deciding how to handle reload failures, stale windows, and multiple tenants belongs to cache/controller design, not a universal guarantee of the API. Never use `NoOpCache` in production and allow every login to fetch metadata over the network.

An operational configuration should specify:

~~~text
Cache key            registrationId / issuer per trust model
TTL                  cache duration acceptable to operations
Eviction             timing/event triggering reload
Refresh semantics    lazy on next lookup or proactive refresh
Failure behavior     retain LKG? fail closed? retry/backoff?
Metadata validity    must not exceed validUntil; respect cacheDuration
Trust                HTTPS + metadata signature/anchor if required by profile
Metrics              hit/miss, last-success, last-failure, stale-age
~~~

`CachingRelyingPartyRegistrationRepository` solves **lookup/loader caching**; it does not enforce all of your organization's SAML trust policies by itself.

### 8.2. `AssertingPartyMetadataRepository`: Decoupling IdP Side from SP Side

Since Spring Security 6.4, the `AssertingPartyMetadataRepository` API specifically manages **IdP metadata**, while `RelyingPartyRegistrationRepository` combines that metadata with **SP-owned** details.

Benefits:

- One IdP metadata source can construct registrations per matching SP policy, avoiding mixing IdP trust data with SP private keys/ACS.
- Metadata resolvers can be swapped without modifying SAML login flows.
- Dedicated metadata resolvers can inspect validity bounds and perform background refreshes per implementation capabilities, rather than a single manual fetch.
- Metadata signatures can be verified when an accurate trust anchor is supplied.

Example in **Spring Security 6.4+ with OpenSAML 5 properly on the classpath**:

~~~java
// Code snippet illustrating 6.4+ API; SP settings still need completion.
AssertingPartyMetadataRepository assertingParties =
    OpenSaml5AssertingPartyMetadataRepository
        .fromTrustedMetadataLocation(
            "https://idp.partner-a.example.org/metadata")
        .build();

AssertingPartyMetadata metadata =
    assertingParties.findByEntityId(
        "https://idp.partner-a.example.org/saml");

if (metadata == null) {
    throw new IllegalStateException("Expected IdP metadata missing");
}

RelyingPartyRegistration registration =
    RelyingPartyRegistration
        .withAssertingPartyMetadata(metadata)
        .registrationId("partner-a")
        .entityId("https://orders.example.org/saml2/sp/partner-a")
        .assertionConsumerServiceLocation(
            "https://orders.example.org/login/saml2/sso/partner-a")
        .build();
~~~

This is an **educational API composition snippet**, not a standalone login app. In production, building the registration must preserve SP signing/decryption credentials, SLO, bindings, and policies. You must also manage metadata resolver/cache lifecycles (including closing resources if required by the implementation) and handle missing expected issuers.

#### `fromTrustedMetadataLocation` vs. `withMetadataLocation(...).verificationCredentials(...)`

Distinguish clearly:

- `fromTrustedMetadataLocation(url)` states that **the source/metadata is considered trusted by the organization** to fetch. Do not assume this method **verifies an XML metadata signature with a pinned key**.
- `withMetadataLocation(url).verificationCredentials(credentials -> ...)` lets you supply trusted credentials **to verify the metadata signature**; per Spring Security documentation, if no credentials are provided, the implementation **does not perform metadata signature validation**.
- **Metadata signer certificates** may be managed separately from certificates the IdP uses to sign SAML Assertions. Define trust contracts and rotation strategies for both.

Boundary diagram:

~~~text
Approved trust anchor (metadata signer cert)
                |
                v
       Verify signed IdP metadata
                |
                v
   New IdP SSO endpoints / signing certs
                |
                v
   Update trusted RelyingPartyRegistration
                |
                v
      Verify SAML Response/Assertion
~~~

Never self-prove trust by taking a certificate "just published" inside an unverified document and using that certificate to verify the same document.

### 8.3. Comparing the Three Refresh Approaches

| Approach | When to use | Strengths | What you still manage yourself |
| --- | --- | --- | --- |
| **Custom atomic snapshot** (6.3+) | On Boot 3.3/Sec 6.3, needing compatibility and explicit policy control. | Clear commit/rollback point, easy state inspection. | Fetch timeouts, metadata signature, expiry, retries, multi-node sync, ops. |
| **CachingRelyingPartyRegistrationRepository** (6.4+) | Want lazy loading/eviction via Spring Cache. | Less boilerplate for caching and lookups. | TTL, eviction, refresh timing, cache-miss failures, metadata trust. |
| **AssertingPartyMetadataRepository/OpenSAML resolver** (6.4+) | Want decoupled IdP data and expiry-based metadata refresh; can verify signed metadata. | Fits metadata model closely, supports complex refreshes. | Trust anchors, SP-specific config, lifecycle, tenant isolation, library versions. |

**Do not label any single API "the best" out of context.** If you only have one static IdP, Boot YAML may suffice. If metadata changes frequently, an expiry-aware resolver is worth considering when your version supports it; if on 6.3, a transparent custom repo is the practical engineering path.

## 9. Multi-IdP and Multi-Tenant Metadata

A metadata XML file may contain an `EntitiesDescriptor` with many `EntityDescriptor` elements. Using `fromMetadataLocation` while assuming "there is always only one IdP" can select the wrong entity or break registrations when a partner expands its metadata.

With collection-capable APIs:

~~~java
// Illustrates selecting the right issuer; this is a method
// placed inside a config management class, not a standalone Java file.
RelyingPartyRegistration selectPartnerRegistration(String metadataLocation) {

    return RelyingPartyRegistrations
        .collectionFromMetadataLocation(metadataLocation)
        .stream()
        .map(builder -> builder.registrationId("partner-a").build())
        .filter(reg -> "https://idp.partner-a.example.org/saml"
            .equals(reg.getAssertingPartyDetails().getEntityId()))
        .findFirst()
        .orElseThrow(() ->
            new IllegalStateException("Expected IdP not found"));
}
~~~

This snippet requires importing Spring Security registration classes; when handling metadata with duplicate issuers, **detect duplicate/ambiguous descriptors** and fail closed rather than calling `findFirst()`. Reattach SP entity ID, ACS, and credentials to the final result per policy; the snippet only illustrates issuer filtering.

### 9.1. Multi-Tenant Registry Design

~~~text
trusted_partners
---------------
registration_id     expected_idp_entity_id             metadata_url
partner-a           https://idp-a.example.org/saml      https://idp-a.example.org/meta
partner-b           https://idp-b.example.org/saml      https://idp-b.example.org/meta

runtime_snapshot
----------------
version
created_at
registrations[partner-a] -> trusted RP-A
registrations[partner-b] -> trusted RP-B
~~~

In the management DB, `registration_id`, `expected_idp_entity_id`, and metadata URLs must require change control and approval; **never accept arbitrary URLs from HTTP requests**. Before every refresh:

1. Resolve the approved partner list.
2. Fetch metadata separately per trusted partner/issuer.
3. Verify signature/source/expiration and invariants of each entry.
4. Attach corresponding SP data for each registration ID; never share wrong tenant signing/decryption keys.
5. Publish an immutable map with version and timestamp; if one IdP fails, apply an explicit policy to update tenants independently or reject the batch deliberately.
6. Lookups use the published version/snapshot, never mixing certs or issuers between partner A and B.
7. Bind each local account to **issuer + subject identifier + tenant context**, never using NameID/email alone for access control.

## 10. Metadata Validity: `validUntil`, `cacheDuration`, and Last-Known-Good

Example metadata with these attributes:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.partner-a.example.org/saml"
    validUntil="2030-05-01T12:00:00Z"
    cacheDuration="PT30M">
    <!-- IDPSSODescriptor, KeyDescriptor, endpoints... -->
</md:EntityDescriptor>
~~~

This is **structural illustrative XML** without a real metadata signature.

- `validUntil` states the metadata **should no longer be considered valid after this instant** per SAML metadata rules and consumer policy. When present on both `EntitiesDescriptor` and `EntityDescriptor`, enforce appropriate bounds rather than reading just one arbitrary level.
- `cacheDuration="PT30M"` is a **cache duration hint**; it does not mean metadata self-destructs at second 1800, nor does it force the scheduler to poll strictly every 30 minutes regardless of expiration.
- Spring Cache's **Cache TTL** is a separate policy; too long a TTL can retain expired metadata, while too short a TTL can cause heavy load or outages.
- **Last-known-good** is a transient source-outage resilience strategy. It is **not a license** to keep trusting expired metadata indefinitely. Once a signed document passes `validUntil`, enforce strict rejection and controlled recovery.

Suggested logic for computing next timestamps:

~~~text
next_check_at   = min(now + operational_refresh_interval,
                      metadata_recommended_refresh_time)

latest_usable_at = min(metadata_valid_until,
                       last_success_at + max_operational_staleness)
~~~

This is a **design formula**, not a built-in Java API returning those two values directly. When metadata omits `validUntil`/`cacheDuration`, apply appropriate bounding policies and IdP contract limits; never assume infinity. On network failures, retry with backoff and jitter without crossing `latest_usable_at`.

### 10.1. Why Not Fetch Metadata on Every HTTP Request?

- The IdP metadata endpoint may be slow or temporarily down; logins suffer constant latency and timeouts.
- High traffic creates a request storm against the IdP.
- An attacker could induce load if the app constructs metadata URLs from requests.
- Authenticating requests cannot observe a consistent snapshot if registrations are rebuilt mid-flight.

Therefore use a cache/snapshot with TTL, proactive refresh, and trusted sources. Metadata fetching is a **control plane** operation, not something executed on every API call.

## 11. Certificate Rollover Policy

New metadata may contain multiple `KeyDescriptor` entries, with `use="signing"` or omitted `use` depending on profile. The SP must understand which certificate verifies SAML responses/assertions, which handles encryption, and which signs **metadata XML** if metadata is signed.

A sound sequence:

~~~text
T0: IdP metadata contains cert A; IdP signs with A.
T1: IdP metadata contains A + B; SP refreshes/verifies, trusts A + B per policy.
T2: IdP starts signing with B; SP still verifies validly.
T3: Overlap and in-flight requests finish; IdP removes A on approved schedule.
T4: SP refreshes/verifies; stops trusting A once retirement criteria are met.
~~~

Never switch directly A → B in one step while the IdP still signs with A. Conversely, never retain A indefinitely once the IdP announces A is compromised or retired from trust.

**Metadata verification is a separate layer** from assertion verification: you must trust the source publishing the new certificate, otherwise an attacker-controlled metadata URL could trick the SP into accepting responses signed with a rogue key.

### 11.1. SP Private Keys Do Not Live in IdP Metadata

An application may use an SP signing key for AuthnRequests and an SP decryption key for EncryptedAssertions. When refreshing **IdP** metadata, never drop:

- Registered SP entity ID and ACS URL.
- SP signing credentials (private key + certificate).
- SP decryption credentials.
- Policy requiring signed AuthnRequests, SLO, and hostname/tenant restrictions.
- Local authorization mappings and business permissions.

When using `RelyingPartyRegistration.Builder` from IdP metadata, re-attach/preserve SP info on every candidate build. "Builder from metadata" is not "a complete production registration".

## 12. Operational Failures and Isolation

| Symptom | Possible Cause | Inspection and Fix |
| --- | --- | --- |
| SAML login works after restart then fails days later | Metadata loaded only once; cert rotated. | Check snapshot/rotation timestamps; design proper refresh. |
| Boot 3.3 project reports missing `CachingRelyingPartyRegistrationRepository` | Class introduced in Spring Security 6.4. | Keep 6.3 custom repo or upgrade Boot/Security in lockstep. |
| Using caching repo yet cert never updates | Default cache lacks TTL or eviction never triggers. | Check cache implementation/TTL and when loader runs. |
| IdP metadata changed yet SSO filter sees old copy | Another repository/bean is injected, or current snapshot didn't swap. | Verify exact `RelyingPartyRegistrationRepository` bean and refresh success. |
| Refresh ran, then logins start failing | Issuer/ACS/SSO/binding/cert mismatch; bad metadata. | Check candidate validation, diff approved fields; rollback if invalid. |
| Post-rollover response signed with new key fails | Verification cert not updated, no overlap, stale metadata. | Coordinate A+B rollout and inspect trusted certificates. |
| Metadata blocked by proxy/timeout | Endpoint/timeout/TLS/network issue. | Use fetcher with timeouts, retry/backoff, alerts; retain bounded LKG. |
| `validUntil` passed yet cache still serves registration | Cache TTL exceeds metadata validity. | Enforce expiry-aware policy outside the cache. |
| Used `fromTrustedMetadataLocation` assuming XML Signature was verified | Confused "trusted source" with signature verification. | Configure metadata signature credentials if required; verify in tests. |
| Multi-IdP cache returns wrong issuer | Cache key/registration ID does not isolate tenants; wrong mapping. | Use stable keys, exact entity ID validation, isolated trust contracts. |
| Metadata returns HTML login page | Wrong URL or IdP requires browser interaction. | Use machine-readable metadata endpoint; verify XML/bindings. |
| Reload unexpectedly drops SP signing key | Candidate builder included only IdP details, omitting SP-owned config. | Keep immutable SP config separate and re-attach on every refresh. |
| Refresh succeeded yet local user has wrong permissions | Conflated metadata with authorization system. | Keep identity linking and authorization separate; never blindly map external groups. |
| XML has multiple entity descriptors | Parser picked wrong entry. | Filter exact expected issuer and detect duplicates. |
| IdP sends unsigned metadata, HTTPS endpoint compromised | Trust anchor relied solely on endpoint. | Build trust contracts, pin sources, sign and verify metadata, or approve cert changes out-of-band. |
| All instances slow down every 15 minutes | Synchronized schedulers causing fetch storms. | Add jitter, coordinated scheduling, or snapshot distribution. |
| New logins blocked due to max-stale | Refresh failed past allowed limit; fail-closed triggered. | Fix source/trust and resolve incident; never raise max-stale indefinitely. |

### Distinguishing Authentication Errors from Authorization Errors

If metadata is wrong, the SP typically cannot verify assertions; that is a **SAML authentication/federation failure**. If the assertion is valid yet the local account lacks permission to read orders or belongs to another tenant, returning 403 is an **authorization decision**, not a metadata refresh failure. Never escalate local permissions to mask metadata bugs or weaken SAML checks to mask permission bugs.

## 13. Testing the Refresh Mechanism Properly

A meaningful QA suite tests behavior **before, during, and after refresh**, not merely confirming the scheduler logged a line.

### 13.1. Test Matrix

| ID | Condition | Expected |
| --- | --- | --- |
| R01 | Startup with valid metadata, right issuer/ACS, trusted certificate. | Repository builds initial snapshot; `partner-a` resolves via lookup. |
| R02 | IdP publishes valid new metadata, same issuer and added cert B. | Candidate refresh succeeds; new snapshot serves lookups after publish. |
| R03 | Burst of concurrent lookup requests during refresh. | Every request sees a complete registration from one version; no concurrent modification errors. |
| R04 | Metadata URL times out, returns 5xx, or returns malformed XML. | Does not publish bad copy; keeps latest valid copy up to allowed bound; raises alert. |
| R05 | Metadata returns another partner's entity ID. | Candidate rejected; old registration remains untouched. |
| R06 | Metadata lacks required verifying credentials. | Candidate rejected per policy; never builds a registration trusting arbitrary signatures. |
| R07 | Metadata passes `validUntil`. | Never uses expired metadata for authentication, even if cache still holds an entry. |
| R08 | Metadata has `cacheDuration` shorter than Spring Cache TTL. | Expiry-aware policy enforces the tighter bound. |
| R09 | During A+B cert window, IdP signs sequentially with A then B. | Both responses validate during approved overlap; A stops being trusted on schedule. |
| R10 | In-flight request/response pair straddles a refresh. | Never bypasses `InResponseTo`, Recipient, Audience, or signature checks; rollover behavior is deterministic. |
| R11 | `partner-a` and `partner-b` share the same NameID. | Lookup preserves issuer/registration/tenant boundaries without cross-granting access. |
| R12 | SP entity ID/ACS altered inside IdP metadata. | SP-owned fields still come from SP config; never overwritten. |
| R13 | LKG exceeds max-stale or metadata expiration. | Fails closed for new logins with alert; never falls back to arbitrary issuers. |
| R14 | Boot 3.3/Sec 6.3 project compiling code using 6.4 classes. | Build fails with missing API error; never swap a single JAR arbitrarily. |
| R15 | Spring Cache enabled without cache TTL. | Test detects metadata does not refresh automatically. |
| R16 | Metadata response replaced with attacker's certificate. | Metadata signature/trust policy blocks candidate publication. |

R07/R08/R16 **are not satisfied by the 6.3 sample in Section 6** because that sample code does not implement signature/`validUntil` parsing. They are mandatory QA gates when hardening for production or adopting a capable resolver.

### 13.2. Building Controlled Test Fixtures

You do not need to attack a real IdP. In an isolated test environment:

1. Set up a test IdP or metadata fixtures **signed with test keys having a known trust anchor**.
2. Prepare V1 with cert A, V2 with A+B, V3 with B only. Keep **issuer fixed**.
3. Prepare failure fixtures: V4 wrong issuer, V5 malformed metadata, V6 expired `validUntil`, V7 invalid XML signature.
4. Point the loader at an allow-listed test metadata endpoint and deliberately swap served contents.
5. Trigger refresh via scheduler or integration-test hook; observe snapshots before/after and real SAML responses via the test IdP.
6. Confirm failure cases never relax signature, recipient, audience, replay, or authorization checks.

For concurrency tests, run multiple lookup threads while the refresh thread publishes verified snapshots; verify zero mixed state. In production, monitor **per-node** versions and when nodes adopt new certs so one node doesn't accept B while another accepts only A.

## 14. Version Upgrades: Decisions Driven by Real Requirements

### When on Boot 3.3 / Spring Security 6.3

You can continue using:

- `RelyingPartyRegistrationRepository`, `InMemoryRelyingPartyRegistrationRepository`.
- `RelyingPartyRegistrations.fromMetadataLocation` or `fromMetadata(InputStream)` when the loader controls source and bytes.
- Application-managed schedulers, `AtomicReference`, or safely published immutable snapshots.
- Dedicated metadata/expiry validation policies or a trusted fetch+verify layer prior to building.

Do not copy 6.4 APIs into a 6.3 project and treat compiler errors as library bugs. If you need deep expiry-aware support without building it yourself, plan a coordinated upgrade.

### When on Boot 3.4+ / Spring Security 6.4+

Evaluate first:

1. `CachingRelyingPartyRegistrationRepository` if your primary need is lazy lookup with cache TTL.
2. `AssertingPartyMetadataRepository` + OpenSAML metadata resolver if you need metadata expiry tracking or signature verification.
3. `IterableRelyingPartyRegistrationRepository` for sources needing both lookup and enumeration.
4. `RelyingPartyRegistration.withAssertingPartyMetadata` to build RP registrations from decoupled metadata while attaching SP-owned fields cleanly.
5. Spring Cache/metadata resolver configuration and tests for eviction, expiry, and trust; never treat the mere presence of an API as proof the mechanism works.

### When Moving to Spring Security 7.x

Check the exact **7.x migration guide, Java baseline, OpenSAML dependency, and Javadoc**. Examples in this lesson use a 6.3 baseline so learners clearly separate **long-standing core APIs** from **new 6.4+ APIs**; do not assume all 6.3 source compiles untouched across every 7.x release.

Decision tree:

~~~text
Need automatic refresh?
  |
  +-- No --> Boot metadata-uri / static repository
  |
  +-- Yes --> Using Spring Security < 6.4?
               |
               +-- Yes --> custom repository + scheduler + strict trust checks
               |
               +-- No --> Need expiry-aware metadata?
                            |
                            +-- Yes --> AssertingPartyMetadataRepository/
                            |           OpenSAML metadata resolver
                            |
                            +-- No --> Cache eviction may suffice:
                                       CachingRelyingPartyRegistrationRepository
                                       + bounded TTL + failure policy
~~~

This is an **architecture selection diagram**; testing trust, rollover, expiry, multi-tenancy, and authn request correlation remains mandatory across every option.

## 15. Misconceptions to Avoid

**"`fromMetadataLocation` auto-reloads when the URL changes."** No. That call builds a registration at one point in time; updates require re-invoking load and swapping the repository, or using a supporting cache/resolver API.

**"Wrapping in `InMemoryRelyingPartyRegistrationRepository` rotates certs automatically."** No. An in-memory repository simply stores registrations you created; it is not a background metadata fetcher.

**"`CachingRelyingPartyRegistrationRepository` auto-refreshes every 15 minutes by default."** False. The default cache may never expire; eviction timing and behavior are governed by your cache configuration.

**"`AssertingPartyMetadataRepository` exists since Spring Security 6.3."** False. That interface was introduced in **6.4**, alongside the dedicated caching and iterable repositories.

**"`fromTrustedMetadataLocation` guarantees metadata XML is validly signed."** Do not infer that. Configure metadata signing policies and verification credentials whenever your trust model requires them.

**"HTTPS is enough to make any new signing cert safe."** TLS protects the channel to a trusted endpoint; if the endpoint/CDN or metadata governance is compromised, trust can still be subverted. Metadata signatures/approvals and monitoring provide additional assurance as required.

**"On fetch failure, just clear the cache so the system reloads."** Doing so can send every request onto the network or leave zero registrations. Use bounded last-known-good, backoff, and fail-closed policies.

**"`cacheDuration` is the same as `validUntil`."** No. One is a caching recommendation, the other is a hard metadata validity limit.

**"Refreshing IdP certs also refreshes SP private keys."** No. IdP verification credentials and SP signing/decryption credentials have distinct ownership and rotation workflows.

**"IdP signing a valid assertion means all business permissions are granted."** No. Spring Security authenticates SAML identity; local accounts, tenants, roles, permissions, and resource access are decided by your application.

## 16. Operational Checklist and Target Outcomes

- [ ] Confirmed exact Spring Security, Spring Boot, and OpenSAML **runtime versions**, verified against version-specific Javadoc.
- [ ] Every `registrationId` has an **authorized, approved** metadata URL/issuer; never take URLs from requests.
- [ ] Authenticated metadata sources, TLS, and XML signatures/trust anchors if applicable; bounded redirects, payload size, and timeouts.
- [ ] Never automatically treat new certificates from unverified metadata as trusted.
- [ ] When building candidates, verify IdP entity ID, SSO/bindings, verification credentials, expiry, and custom policies.
- [ ] SP entity ID, ACS, signing/decryption credentials, and SLO config are re-applied on every refresh.
- [ ] New snapshots publish atomically; request threads never observe half-updated config.
- [ ] Fetch/parse/verify failures never overwrite a good snapshot; alerts and backoff are active.
- [ ] Last-known-good has a bounded max lifetime; expired metadata is never accepted indefinitely.
- [ ] Multi-tenant configs isolate keys, issuers, and certificates; trust boundaries never mix.
- [ ] A+B cert rollover maintains proper overlap; in-flight requests and callbacks are tested.
- [ ] Every node tracks version/last refresh; restart or failover runbooks exist.
- [ ] Tests R01–R16 or equivalents exist; unimplemented gates are explicitly marked.
- [ ] SP metadata endpoint, AuthnRequest, ACS response signature, and app authorization are tested independently.
- [ ] SAMLResponses, private keys, raw assertions, or sensitive identity data are never logged.

### Key Takeaway

**A refreshable SAML2 registration repository is a trust-management component, not just an HTTP cache.** Proper refresh requires separating IdP metadata from SP-owned registration settings, verifying candidate sources and validity, publishing consistent snapshots atomically, enforcing failure policies, and picking APIs matching your actual runtime version. **Spring Security 6.3** achieves this with an application-managed repository; **6.4+** adds caching and metadata repository abstractions to reduce boilerplate.

### Official References

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistrationRepository`, Boot bean overrides, caching, and multi-tenancy.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `AssertingPartyMetadataRepository`, OpenSAML resolvers, signature verification, and SP metadata.
- [Spring Security 6.4 – CachingRelyingPartyRegistrationRepository API](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): Javadoc noting `Since: 6.4` and default cache behavior.
- [Spring Security 6.4 – AssertingPartyMetadataRepository API](https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadataRepository.html): `Since: 6.4`.
- [Spring Security 6.3 – InMemoryRelyingPartyRegistrationRepository API](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html): repository iterable via `Iterable`.
- [Spring Security – RelyingPartyRegistrations API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): `fromMetadataLocation`, `fromMetadata(InputStream)`, and `collectionFromMetadataLocation`.
- [Spring Boot 3.3 – SAML2 Configuration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): property namespaces and Boot SP auto-configuration.
- [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `EntitiesDescriptor`, `validUntil`, `cacheDuration`, `KeyDescriptor`.
