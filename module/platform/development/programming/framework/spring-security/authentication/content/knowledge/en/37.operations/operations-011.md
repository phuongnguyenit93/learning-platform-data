# Updating Dependencies and Verifying Vulnerability Advisories by Exact Version

> **Context:** Spring Security – authentication, **Operations** topic. This lesson is for operations engineers, security engineers, and backend developers using Java 17+, Spring Boot, Spring Security, Maven/Gradle, and CI/CD. The focus is not merely "running a CVE scanner", but **identifying the exact JAR running in production, cross-checking affected versions + exploit prerequisites + fix versions + support channels**, updating safely, and proving authentication/authorization remains intact. Illustrative patches/CVEs come from Spring advisories published on **August 20, 2026**; any real incident afterward must consult the live primary advisory and release schedule at the time of action.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference among **declared**, **BOM-managed**, **runtime-resolved**, **executable JAR/container-packaged**, and **actually running in production** dependencies.
2. Look up an alert in [Spring Security Advisories](https://spring.io/security/) and read its full product, affected version ranges, configuration prerequisites, fix versions, distribution channel, migration notes, and mitigations.
3. Prove whether a CVE applies using **version evidence + feature configuration + deployment runtime evidence**, rather than guessing from CVSS scores or artifact names.
4. Inspect Maven `dependency:tree`/effective POM, Gradle `dependencies`/`dependencyInsight`, dependency lockfiles, SBOMs, transitive versions, and BOM overrides.
5. Use OWASP Dependency-Check/SCA and OSV/GHSA/NVD feeds as **detection tools**, not replacements for vendor advisory verification.
6. Plan Spring Boot/Security upgrades along a **compatible release train**; avoid arbitrarily forcing a Spring Security 7.x JAR into a Boot 3.x app running Security 6.x.
7. Assess urgency using reachability, Internet exposure, data sensitivity, exploitability, SLAs, patch channels, and regression risk.
8. Test after upgrading: form login, Basic/Bearer, JWT validators, CSRF, role/method security, MFA, OTT, WebAuthn, sessions, and logout/revocation.
9. Retain change-management evidence: baseline, dependency graph, advisory URL, fix/mitigation decision, test results, new SBOM, image digest, and rollback plan.
10. Run a standalone Java 17 program simulating version-range and config-condition triage for a CVE and interpret its exact stdout.

## 2. Why Is "Which Spring Security Version?" Not a Simple Question?

A Spring Boot application has multiple dependency layers:

```text
build.gradle / pom.xml
    |
    +-- Spring Boot plugin / starter-parent
    |     |
    |     +-- spring-boot-dependencies BOM
    |              |
    |              +-- versions for spring-security-core/config/web/crypto
    |              +-- versions for spring-framework / jackson / tomcat ...
    |
    +-- direct dependencies (starters, security modules)
    +-- transitive dependencies (JOSE/JWT, servlet, JSON ...)
    +-- overrides / constraints / dependency locks / profiles
                        |
                        v
             Resolved runtime classpath
                        |
                        v
          bootJar / executable JAR / container
                        |
                        v
        Production deployment running digest X
```

**Key point:** seeing `implementation 'org.springframework.boot:spring-boot-starter-security'` in `build.gradle` **without a version** does not mean it has no version. The Spring Boot BOM pins a tested set of versions together. Conversely, a version written in a POM is not guaranteed to be the resolved version if dependency management, constraints, profiles, plugins, or transitive conflicts override it.

In practice, an app might have:

- Spring Boot `3.x` with Spring Security `6.x` (a common pairing; **never infer exact patches** from major numbers alone).
- Spring Boot `4.x` with Spring Security `7.x` on a compatible release line.
- Service A updated while Service B still runs an older Docker image.
- Tests running a different dependency graph from production due to `testRuntimeClasspath` or `-Pprofile`.
- Local Gradle cache holding a newer JAR while the production container image packaged an older one.
- `spring-security-web` bumped while `spring-security-config` or `spring-security-core` sits on another version due to an uneven override.
- A vulnerability residing in Spring Framework, Spring Session, Nimbus JOSE, Tomcat, or Jackson rather than Spring Security itself, even though everything arrives via `spring-boot-starter-security`.

**Accurate answer:** collect the **runtime-resolved** `group:artifact:version`, why that version won, the packaged artifact, and the deployed image digest.

### 2.1. "Running Version" Has at Least Five Layers

| Question | Data Source | Meaning |
|---|---|---|
| What did the project declare? | `build.gradle(.kts)` / `pom.xml` | Declared intent; may be overridden by BOM |
| What does the BOM/parent supply? | `spring-boot-dependencies`, `dependencyManagement` | Version constraints/management |
| What did the build actually pick? | Gradle `dependencyInsight` / Maven `dependency:tree` | **Resolved** dependency graph |
| Which JARs are inside the artifact? | `BOOT-INF/lib` in boot JAR, SBOM/image scan | Actual packaged contents post-build |
| What is production running? | CI artifact SHA/digest, Kubernetes image digest, deployment metadata | Determines whether the CVE exists in the live environment |

Never substitute `git main` or "CI passed today" for deployment evidence; production may still run an image with a different digest.

### 2.2. Direct vs. Transitive Dependencies

A **direct dependency** is one you declare explicitly, such as the security starter or OAuth2 Resource Server.

A **transitive dependency** is pulled in by another library, such as the JWT JOSE library used by Resource Server. When a scanner flags a CVE in a transitive module, trace who pulled it into the graph, verify the running version, and consider upgrading the **parent/BOM** before applying standalone overrides.

### 2.3. Do Not Confuse Build Tool Plugins with Runtime Libraries

An alert in a Maven plugin, Gradle plugin, test library, or dependency scanner may affect the **CI/build environment** without ever entering the web app's runtime classpath; conversely, a JAR on `runtimeClasspath` absent from `compileClasspath` still introduces a production vulnerability.

Do not ignore build-time CVEs if attackers can influence CI, artifact signing, or dependency resolution; just **classify the attack surface accurately**.

## 3. How to Read a Security Advisory Structurally

A reliable advisory usually provides:

1. **CVE / GHSA / identifier:** reference ID and publication/update dates.
2. **Product and module:** Spring Security, Spring Framework, Spring Session, Spring Authorization Server, or third-party.
3. **Description:** exact technical flaw and bypass/exposure behavior.
4. **Affected versions:** min–max ranges, inclusive/exclusive bounds, and differences across 6.4/6.5/7.0... branches.
5. **Exploit prerequisites:** Servlet-only vs. WebFlux, WebAuthn-only, specific config, storage, URL patterns, roles, or header/forwarded setups.
6. **Fix versions:** which patches fix it and whether they match your active release line.
7. **Availability:** OSS, Enterprise Support Only, repository/entitlement requirements; never confuse "a fix exists" with "our org has access to download that fix".
8. **Workaround / mitigation:** disabling a feature, changing config, restricting exposure, upgrading, or migrating data.
9. **Impact and severity:** CVSS, exploitability, affected data/privileges.
10. **References and history:** how the advisory evolved; check updates since prerequisites or affected ranges can be amended.

**Never read only the CVE ID and the "HIGH" badge.** For instance, a scanner might flag `org.springframework.security:spring-security-web:6.5.10` for a WebAuthn issue **that occurs only when `userVerification` is `REQUIRED` alongside distributed sessions**; verify whether your app actually uses that flow. Conversely, lacking config evidence **does not mean safe**: mark status `UNKNOWN / NEEDS_REVIEW`, not "not affected".

### 3.1. Source Precedence When Feeds Disagree

Prioritize:

- **Vendor advisory** at `https://spring.io/security/`: trigger conditions, versions, fixes, and migrations.
- **Release notes/changelogs/Spring support policy** for patches and LTS timelines.
- **Service build artifact metadata & SBOM:** exact module and version identification.
- **CVE/NVD, GHSA, OSV, OWASP Dependency-Check:** cross-checking IDs, CVSS, component matches, and extra evidence; feeds can lag or mis-match.
- **Security tests, feature flags, infrastructure config:** confirming reachability and app-specific prerequisites.

Never use an undated summary blog as the sole source to declare an issue applicable or not applicable. **NVD lag** or post-publication severity edits do not override the vendor advisory.

## 4. Real Example: CVE-2026-47841 and Proper Cross-Checking

**Official source:** [CVE-2026-47841 – WebAuthn User Verification Bypass via Session Serialization](https://spring.io/security/cve-2026-47841/), published **2026-08-20**.

This illustrates a vulnerability where **version-only matching is insufficient**. Per the advisory, an application can be affected if **all three** hold simultaneously:

1. Uses Spring Security's **WebAuthn/passkey authentication**.
2. Configures `userVerification = REQUIRED` (default `PREFERRED` is not subject to the described issue).
3. Uses a **distributed HTTP session store** such as Spring Session with Redis, JDBC, or Hazelcast; serialization/deserialization breaks identity verification checks.

When all three hold, someone possessing the authenticator device may complete WebAuthn without satisfying on-device user verification (PIN/biometric), violating UV enforcement. This is **not** a claim that every Spring Security app shares the same exposure. Inspect session storage and WebAuthn config **actually deployed**.

### 4.1. Version Ranges in the Advisory (2026-08-20 Snapshot)

| Spring Security Branch | Affected Versions (Inclusive) | Documented Fix | Availability in Advisory |
|---|---|---|---|
| 6.4 | `6.4.0 – 6.4.18` | `6.4.19` | **Enterprise Support Only** |
| 6.5 | `6.5.0 – 6.5.11` | `6.5.12` | **Enterprise Support Only** |
| 7.0 | `7.0.0 – 7.0.6` | `7.0.7` | **OSS** |
| 7.1 | `7.1.0` | `7.1.1` | **OSS** |

The advisory also lists `7.0.6.1` and `7.1.0.1` as **Enterprise Support Only** fixes. This is a sourced historical snapshot, **not a permanent "latest version" list**; check current versions and entitlements during every real triage.

### 4.2. Which Conditions Determine Applicability?

| Version Evidence | WebAuthn | UV Required | Distributed Session | Conclusion |
|---|---|---|---|---|
| 6.5.10 | Yes | Yes | Yes | **Affected configuration**; plan patching immediately |
| 6.5.10 | Yes | Yes | No | Does not meet all advisory prerequisites; document evidence |
| 6.5.10 | No | N/A | Yes | Does not use the described feature; still check other CVEs |
| 6.5.10 | Yes | **Unknown** | Yes | **Needs investigation**; cannot close as false positive |
| 6.5.12 | Yes | Yes | Yes | Outside this advisory's affected range; **verify Enterprise entitlement/channel** |
| 7.0.6 | Yes | Yes | Yes | Affected configuration |
| 7.0.7 | Yes | Yes | Yes | Outside affected range and a published OSS fix |

**Configuration evidence:** `SecurityFilterChain` registering `webAuthn`, `userVerification` resolver, source of WebAuthn options, Spring Session setup, `spring.session.store-type`, Redis/JDBC deployment, and actual session replication/serialization. If production config differs from staging, staging being "not affected" proves nothing about production.

### 4.3. Patches and Support Availability

If you run Spring Security 6.5.x and fix `6.5.12` is marked **Enterprise Support Only**, do not claim "just grab 6.5.12 from Maven Central" without verifying entitlement/repositories. Teams must choose **a supported OSS release line compatible with the full Spring Boot stack**, an Enterprise build the organization is licensed to use, or an approved risk-reviewed mitigation. **Never** override `spring-security-web` alone to `7.0.7` inside a Spring Boot 3 app using Security 6.

The advisory notes no extra mitigation steps are needed once upgraded to a fixed version. Still, every upgrade requires testing WebAuthn UV enforcement, session serialization, login, and rollback.

## 5. Second Example: CVE-2026-47842 Proves "Patching a JAR Is Not Enough"

**Official source:** [CVE-2026-47842 – Deterministic AES/CBC Encryption in Spring Security](https://spring.io/security/cve-2026-47842/), published **2026-08-20**.

The flaw involves **using `AesBytesEncryptor`** with the two-argument constructor or CBC with a null IV generator. A fixed IV causes identical plaintexts (with the same password/salt) to produce identical ciphertexts, enabling correlation if an attacker reads the ciphertext store.

**Critical point:** a scanner reporting Spring Security vulnerable does not know whether the app **uses that API, that constructor, or holds data encrypted in the old format**. Code paths and data migration govern remediation.

The advisory lists affected ranges including `6.5.0–6.5.11` and `7.0.0–7.0.6` (plus other branches), fixed in `7.0.7`/`7.1.1` OSS and `6.5.12` Enterprise Support Only. It warns that migrating to `AesCbcBytesEncryptor`/`AesGcmBytesEncryptor` may **require data migration/re-encryption** because IV handling and key derivation differ.

### 5.1. Practical Checklist for This CVE

1. Check the runtime-resolved `spring-security-crypto` version, not only `spring-security-web`.
2. Search for `AesBytesEncryptor`, `Encryptors.standard()`/`stronger()`/`text()`/`delux()`, and modes/constructors across real code, including internal wrapper libraries.
3. Compare constructors and IV generators against **advisory conditions**. GCM with a secure IV or CBC with explicit random IVs has a different threat profile than a null IV.
4. If stored ciphertexts exist, inventory the data, key access, and ability to decrypt legacy format; never upgrade the library and render existing data unreadable.
5. Follow the exact migration path documented in the advisory, test with anonymized realistic data, and prepare a rollback strategy.
6. Keep encryption passwords, keys, IVs, and plaintexts out of logs, CI artifacts, and incident tickets.
7. Mark `RESOLVED` only once the fixed version is deployed **and** data/operations pass required migration checks; or triage `NOT_APPLICABLE` with concrete evidence.

**Lesson:** a dependency upgrade can introduce **data-format and operational changes**, not just a build-file version bump. Sometimes remediation is a **migration project** with backup/restore and key rotation, not a one-line PR.

## 6. Collecting Exact Versions with Gradle

In Gradle projects, use the **Gradle Wrapper** committed in the repo so builds match configured versions. Commands below assume `./gradlew`; on Windows use `gradlew.bat`.

### 6.1. Reading Build Tool Versions

```bash
./gradlew --version
./gradlew help
```

Output shows Gradle/JVM versions, **not Spring Security versions**. Next, inspect `build.gradle(.kts)`, `settings.gradle(.kts)`, version catalogs (`gradle/libs.versions.toml`), `pluginManagement`, the Spring Boot plugin, and dependency lockfiles if present.

### 6.2. Actual Resolved Dependency Tree

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

For multi-module projects, add the project path:

```bash
./gradlew :api:dependencies --configuration runtimeClasspath
./gradlew :worker:dependencies --configuration runtimeClasspath
```

**Runtime is the primary production target**; `compileClasspath` and `testRuntimeClasspath` may pick or add different versions. Read Gradle markers such as `->` (version bumped via conflict/constraint), `(c)` (dependency constraint), and resolution reasons instead of merely grepping for "spring-security".

### 6.3. Dependency Insight for Suspect Modules

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-crypto \
  --configuration runtimeClasspath
```

To see why a version was chosen (BOM, direct dependency, constraint, transitive), `dependencyInsight` beats staring at a declared version line. If the app uses `oauth2ResourceServer`/`webAuthn`, also inspect `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, and related JOSE/WebAuthn libraries.

### 6.4. Handling Version Overrides or Lockfiles

Inspect carefully:

- `resolutionStrategy.force(...)`, `eachDependency`, constraints, `strictly`, `enforcedPlatform`, Spring dependency-management plugin.
- Version catalog aliases and Gradle dependency locking.
- Other platforms/imported BOMs competing with the Spring Boot BOM.
- `-SNAPSHOT` dependencies, dynamic versions like `6.+`, `latest.release`: break build reproducibility.
- Composite builds and `buildSrc`/plugin build logic: plugins can pull separate libraries into the build JVM.

Avoid forcing a single Spring Security module version just to silence a scanner if sibling Security modules become mismatched. **Prefer upgrading to a maintained Spring Boot version** so the BOM advances related modules together along the release train, unless vendor guidance specifies a thoroughly tested override.

### 6.5. Inspecting Packaged Artifacts

For an executable Boot JAR:

```bash
./gradlew bootJar
jar tf build/libs/app.jar
```

`build/libs/app.jar` is an **illustrative** filename, not guaranteed in every project. Check `BOOT-INF/lib/spring-security-*.jar` or generate an SBOM from the real archive/image; run `jar tf` against your build's actual JAR path. Match container layers/digests and deployments against CI artifacts rather than treating a laptop's resolved classpath as production.

## 7. Collecting Exact Versions with Maven

When using `spring-boot-starter-parent` or importing the `spring-boot-dependencies` BOM, many dependencies omit versions in the POM. Maven applies dependency management and mediation rules.

### 7.1. Dependency Tree

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
```

Use `mvnw.cmd` on Windows. For multi-module builds, pass `-pl :service-api` and `-am` as needed. Check `scope`, `version`, parent, and active profiles.

### 7.2. Effective POM and Dependency Management

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -DoutputFile=resolved-dependencies.txt
```

Note that `effective-pom.xml` and dependency trees are **diagnostic artifacts**—never commit environment secrets or credential-bearing URLs. Check `pom.xml` for `dependencyManagement` imports, property overrides like `spring-security.version` or `spring-framework.version`, `spring-boot-starter-parent`, and plugin versions. If Maven profiles differ between CI and developer machines, re-run with the deployed profile.

### 7.3. Maven Dependencies Without Explicit Versions

```xml
<!-- pom.xml excerpt managed by Spring Boot parent/BOM. -->
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
```

Omitting `<version>` here is **correct** when BOM-managed. Still, determining CVE relevance requires inspecting the resolved `spring-security-*` JARs and app conditions, not just seeing the starter.

## 8. BOMs, Release Trains, and Controlled Upgrades

### 8.1. Why Upgrade Spring Boot First?

Spring Boot ships a **Bill of Materials** of Spring modules and third-party libraries tested together by the release team. In most Boot apps, the safest upgrade path is:

```text
Baseline Boot version + resolved graph
         |
         v
Select supported Boot release
containing or compatible with the Spring Security fix
         |
         v
Review release notes / migration guides / support terms
         |
         v
Build / run tests / inspect resolved graph
         |
         v
Patch policy evidence & production deployment
```

**Never** assume Spring Boot `3.4` is compatible with arbitrary Spring Security `7.1` just because Maven resolves the JARs. Major/minor security DSLs, Spring Framework, Java baselines, servlet containers, and WebFlux/Servlet internals change. Verify compatibility via docs/BOM/CI, not merely whether one method compiles.

### 8.2. Gradle: BOM-Managed Versions

Dependency excerpt appropriate when the project applies the Spring Boot plugin and dependency-management plugin or equivalent platform setup:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Do not directly pin `org.springframework.security:spring-security-web:7.0.7` in Boot 3.x apps** to "fix the CVE". That creates dependency drift/mismatch against `spring-security-config`, `spring-security-core`, and Spring Framework. If a short-term override is required per vendor guidance, document rationale, scope, TTL, tests, and a plan to return to the BOM.

### 8.3. What Facts Are Needed When Picking a Version?

- Is the target branch still in **OSS support**, or does it require Enterprise Support?
- JDK, Spring Framework, Boot, Security, and plugin compatibility.
- Any behavioral changes in `SecurityFilterChain`, `AuthorizationManager`, `PasswordEncoder`, session handling, or OAuth2/OIDC?
- Major breaking changes (6 → 7), deprecations, or servlet API version shifts?
- Data/key/config migrations like `AesBytesEncryptor`?
- Multiple services/gateways sharing JWTs/schemas/sessions that must upgrade in coordination?
- Rollback path after altering session serialization or encrypted data formats?
- Are **other** vulnerabilities present in the target version, or were newer patches released since the advisory?

A "fix for CVE A" is not automatically **safe against CVEs B–Z**. Run SCA on the **final graph** and keep watching new advisories.

## 9. Dependency Scanners: Detection, Not a Substitute for Triage

### 9.1. OWASP Dependency-Check

OWASP Dependency-Check is a Software Composition Analysis (SCA) tool matching dependency metadata against public databases like NVD to spot **disclosed vulnerabilities**. It does not prove every code path is reachable, and can misidentify components/versions or miss items when metadata is weak.

Gradle example (published plugin ID; version `13.0.0` is an **example pinned as of 08/2026**—re-verify compatibility before applying):

```groovy
plugins {
    id 'org.owasp.dependencycheck' version '13.0.0'
}
```

Run on a project with the plugin and dependency metadata configured:

```bash
./gradlew dependencyCheckAnalyze
```

Reports typically land under `build/reports`, depending on plugin/config. In multi-project builds, inspect `dependencyCheckAggregate` or scan each deployable module. Never scan only `testImplementation` and declare runtime clean.

### 9.2. Never Tune Scanners to Force Desired Results

- Ensure NVD feeds are fresh, with valid API keys/rate limits, network access, CI caches, and current plugin versions.
- If a scanner **fails to download feeds**: status is `SCAN_FAILED/INCOMPLETE`, never `NO_FINDINGS`.
- If the scanner lacks Maven Central/private repo metadata, false positives or false negatives occur; inspect artifact coordinates/POM evidence.
- When suppressions are justified, require **owner, CVE, exact component+version+environment, evidence-backed rationale, expiration date, ticket link, and review**.
- Never adopt "ignore everything with CVSS < 9" as a blanket policy; exploitability and sensitive auth paths matter.
- After upgrading, re-scan and diff reports; a newer version can introduce or uncover different CVEs.
- Store reports alongside commit SHA, build ID, image digest, and feed timestamp for reproducibility.

### 9.3. NVD, GHSA, OSV, and Terminology

| Source | Useful For | Limitations to Remember |
|---|---|---|
| Spring official advisories | Spring/feature conditions, affected/fix versions, mitigations | Must read latest updates; distinguish Enterprise fixes |
| NVD/NIST | CVE descriptions, CVSS/CPE, public metadata | CPE matching can be wrong or delayed |
| GitHub Security Advisories (GHSA) | Affected package ranges, ecosystem, references | Depends on accurate ecosystem/package mapping |
| OSV | Vulnerabilities by package/version, API/bulk scans | Does not prove reachability |
| OWASP Dependency-Check | Scanning Java dependencies and generating reports | False positives/negatives and feed dependency |
| CycloneDX/SPDX SBOM | BOM inventory per build/artifact | An SBOM alone does not replace vulnerability analysis |
| Runtime/image scanners | JARs/base-image/OS packages inside artifacts | Must map installed runtime and context properly |
| SAST/DAST/fuzzing | Testing code/config behavior and attack surface | Does not replace version inventory/SCA |

A CVE is a vulnerability identifier, **not a package name**. One CVE can affect multiple artifacts in a project; one artifact can have multiple CVEs. Never deduce the exact fixed version from `CVE-2026-XXXX` without reading the affected/fix table.

## 10. SBOMs and Supply Chain: Tying Alerts to Exact Builds

An **SBOM (Software Bill of Materials)** inventories components in a build/image with coordinates and versions in standard formats like CycloneDX or SPDX. It helps:

1. Find every service depending on a CVE-affected module by querying the SBOM registry.
2. Reconcile source builds against deployed artifacts.
3. Prove post-patch that module versions changed rather than trusting a Git diff alone.
4. Retain version lineage for incident response.
5. Audit affected transitive modules never declared directly.

Metadata to record:

```text
service: payments-api
release: git-sha-abc123
buildId: ci-2026-11-06-001
imageDigest: sha256:<digest-from-registry>
javaRuntime: vendor/version
springBoot: resolved version
springSecurityModules:
  spring-security-core: <resolved version>
  spring-security-web: <resolved version>
  spring-security-config: <resolved version>
  spring-security-crypto: <resolved version>
sbom: CycloneDX file hash and generation time
scanner: tool/version/advisory-feed-timestamp
```

The strings above are a **representative schema**, not live system output. Populate real versions/digests from CI/repositories; avoid publishing sensitive internal identifiers publicly unnecessarily.

### 10.1. Lockfiles and Reproducible Builds

Gradle dependency locking, Maven wrapper, container base-image digests, artifact repository pinning, and CI cache policies prevent the same source SHA from resolving differently later. Pin plugin versions and JDK toolchains where possible. Never use dynamic dependency ranges as automatic production patching without testing.

**Note:** Dependency locks can keep a vulnerable version pinned when you bump only the BOM. After upgrading, refresh lockfiles properly, inspect diffs, and test; never confuse "BOM bumped" with "runtime upgraded".

### 10.2. Runtime JDK, Proxies, and Servlet Containers Also Need Patching

Authentication alerts can originate from:

- JVM/JDK TLS/security providers, CA stores, and crypto implementations.
- Tomcat/Jetty/Undertow, Netty/Reactor, Jackson.
- Spring Session/Redis/JDBC serialization.
- Gateways, reverse proxies, ingress, and session cookie handling.
- Nimbus JOSE JWT validation / WebAuthn libraries.
- OS/base image packages, TLS termination, and WAF/IdP integrations.

Never stop at `spring-security-web` during triage. Even if Java dependency scans are clean, a container base image can still be vulnerable; conversely, OS scanners may flag packages unused by the Java runtime.

## 11. Assessing Impact: Do Not Rely on CVSS Alone

When triaging a finding, use **evidence** instead of guesswork:

1. **Exact artifact/version** actually deployed (Maven coordinates, image digest).
2. **Affected range** from the advisory—does the version fall inside?
3. **Feature prerequisites:** Servlet/WebFlux, WebAuthn, BCrypt, method security, `AesBytesEncryptor`, OAuth2 Resource Server, session store.
4. **Code path/reachability:** is the flow exposed over Internet/VPN/tenant boundaries? Which feature flags and route guards exist?
5. **Attacker prerequisites:** anonymous vs. authenticated, device possession, DB read access, user role, race timing.
6. **Impact:** MFA bypass, data leak, RCE/DoS, admin escalation, secret/password exposure, integrity loss.
7. **Exploit maturity:** public PoC, weaponization, active exploitation, EPSS/CISA KEV where relevant.
8. **Mitigation:** guardrails, WAF, feature disablement, session isolation; are there tests proving it works?
9. **Fix availability:** OSS/Enterprise, support contract, migration path, time-to-ship.
10. **Compensating controls and deadlines:** accountable owner, timeboxed risk acceptance, and monitoring.

### 11.1. Clear Finding Status Model

| Status | Evidence Required |
|---|---|
| `AFFECTED` | Runtime version in range **and** exploit prerequisites evidenced |
| `POTENTIALLY_AFFECTED` | Version in range; config/reachability unknown |
| `NOT_APPLICABLE_BY_VERSION` | Runtime version proven outside affected range |
| `NOT_APPLICABLE_BY_CONFIGURATION` | Version in range, yet advisory conditions do not hold, backed by logs/config/tests |
| `MITIGATED_TEMPORARILY` | Controls applied and tested; patch deadline set |
| `FIX_AVAILABLE_NOT_DEPLOYED` | Compatible patch released, but production still runs older build |
| `PATCHED_AND_VERIFIED` | New production artifact, tests, and post-deploy checks passed |
| `SCAN_INCOMPLETE` | Tool/feed/repo failure; missing data must never be called clean |
| `RISK_ACCEPTED_UNTIL` | Authorized approver, rationale, compensating controls, expiration date |

**Avoid the trap:** `NOT_APPLICABLE_BY_CONFIGURATION` is not `PATCHED`. Enabling a new feature or swapping session stores can make a previously dormant finding applicable. Re-evaluate config-dependent suppressions whenever architecture changes.

### 11.2. SLAs and Response Times

Organizations should maintain risk-based patch SLAs. Illustrative examples, not mandatory standards:

- **Emergency:** active exploitation or Internet-exposed authn/authz bypass → top-priority action, shrink attack surface while patching.
- **High:** login/session/MFA product impacted with a fix available → rapid hotfix flow and heightened monitoring.
- **Medium/Low:** assess exploitability and exposure; schedule into maintenance windows.
- **Unknown:** investigate; do not wait for the scanner alert to vanish on its own.

Never replace triage with "high CVSS means bump everything to the newest major immediately"; untested major migrations can break the app or open security config bypasses.

## 12. Standalone Java 17: Checking Version Ranges and CVE Prerequisites

This program **compiles/runs on JDK 17+** without Spring or Maven. It simulates triaging **CVE-2026-47841**: published version ranges plus the three config conditions (`WebAuthn`, `UV_REQUIRED`, `distributedSessionStore`). All results model **the 2026-08-20 advisory snapshot**, not a general vulnerability scanner.

**Important:** the comparator parses only numeric `major.minor.patch` versions. It does not handle SemVer pre-releases, Maven qualifiers, four-part Spring Enterprise versions like `7.0.6.1`, SNAPSHOTs, OSGi metadata, support policies, or BOM resolution. For production, use ecosystem version resolvers and live advisory ranges rather than relying solely on demo code.

Save as `SpringSecurityAdvisoryTriageDemo.java`:

```java
import java.util.List;

public class SpringSecurityAdvisoryTriageDemo {

    record Version(int major, int minor, int patch)
            implements Comparable<Version> {
        static Version parse(String value) {
            String[] parts = value.split("\\.");
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                    "Only numeric major.minor.patch supported");
            }
            return new Version(
                Integer.parseInt(parts[0]),
                Integer.parseInt(parts[1]),
                Integer.parseInt(parts[2]));
        }

        @Override
        public int compareTo(Version other) {
            int byMajor = Integer.compare(major, other.major);
            if (byMajor != 0) return byMajor;

            int byMinor = Integer.compare(minor, other.minor);
            if (byMinor != 0) return byMinor;

            return Integer.compare(patch, other.patch);
        }
    }

    record AffectedRange(Version first, Version last) {
        boolean contains(Version value) {
            return value.compareTo(first) >= 0
                && value.compareTo(last) <= 0;
        }
    }

    enum Setting { YES, NO, UNKNOWN }

    record WebAuthnConfig(
        Setting usesWebAuthn,
        Setting requiresUserVerification,
        Setting distributedSessionStore) {}

    private static final List<AffectedRange> AFFECTED =
        List.of(
            new AffectedRange(
                Version.parse("6.4.0"), Version.parse("6.4.18")),
            new AffectedRange(
                Version.parse("6.5.0"), Version.parse("6.5.11")),
            new AffectedRange(
                Version.parse("7.0.0"), Version.parse("7.0.6")),
            new AffectedRange(
                Version.parse("7.1.0"), Version.parse("7.1.0"))
        );

    static String classify(String rawVersion, WebAuthnConfig config) {
        Version version = Version.parse(rawVersion);

        boolean inRange = AFFECTED.stream()
            .anyMatch(range -> range.contains(version));
        if (!inRange) {
            return "NOT_IN_AFFECTED_RANGE";
        }

        if (config.usesWebAuthn() == Setting.NO
                || config.requiresUserVerification() == Setting.NO
                || config.distributedSessionStore() == Setting.NO) {
            return "NOT_APPLICABLE_BY_CONFIG";
        }

        if (config.usesWebAuthn() == Setting.UNKNOWN
                || config.requiresUserVerification() == Setting.UNKNOWN
                || config.distributedSessionStore() == Setting.UNKNOWN) {
            return "NEEDS_CONFIG_REVIEW";
        }

        return "AFFECTED_CONFIGURATION";
    }

    public static void main(String[] args) {
        WebAuthnConfig affected = new WebAuthnConfig(
            Setting.YES, Setting.YES, Setting.YES);
        WebAuthnConfig noDistributed = new WebAuthnConfig(
            Setting.YES, Setting.YES, Setting.NO);
        WebAuthnConfig unknownUv = new WebAuthnConfig(
            Setting.YES, Setting.UNKNOWN, Setting.YES);

        System.out.println("6.5.10 + affected: " +
            classify("6.5.10", affected));
        System.out.println("6.5.10 + no distributed: " +
            classify("6.5.10", noDistributed));
        System.out.println("6.5.10 + unknown UV: " +
            classify("6.5.10", unknownUv));
        System.out.println("6.5.12 + affected: " +
            classify("6.5.12", affected));
        System.out.println("7.0.6 + affected: " +
            classify("7.0.6", affected));
        System.out.println("7.0.7 + affected: " +
            classify("7.0.7", affected));
        System.out.println("6.4.18 + affected: " +
            classify("6.4.18", affected));
        System.out.println("6.4.19 + affected: " +
            classify("6.4.19", affected));
    }
}
```

Compile and run:

```bash
javac SpringSecurityAdvisoryTriageDemo.java
java SpringSecurityAdvisoryTriageDemo
```

**Exact** stdout:

```text
6.5.10 + affected: AFFECTED_CONFIGURATION
6.5.10 + no distributed: NOT_APPLICABLE_BY_CONFIG
6.5.10 + unknown UV: NEEDS_CONFIG_REVIEW
6.5.12 + affected: NOT_IN_AFFECTED_RANGE
7.0.6 + affected: AFFECTED_CONFIGURATION
7.0.7 + affected: NOT_IN_AFFECTED_RANGE
6.4.18 + affected: AFFECTED_CONFIGURATION
6.4.19 + affected: NOT_IN_AFFECTED_RANGE
```

### 12.1. What the Code Proves and Does Not Prove

**It proves:**
- Given a numeric `major.minor.patch` version, inclusive range matching behaves accurately.
- One `NO` condition suffices to show **all three simultaneous prerequisites** of this advisory are not met.
- An `UNKNOWN` condition returns `NEEDS_CONFIG_REVIEW` rather than quietly claiming "not affected".
- `6.5.12` and `7.0.7` lie outside the affected range **of this specific CVE**.

**It does not prove:**
- Whether the build/production actually runs `6.5.10` or `6.5.12`.
- Whether `6.5.12` is on Maven Central or whether you hold Enterprise Support.
- Whether other CVEs affect the chosen version.
- Whether user verification in the app is actually `REQUIRED` and enforced across distributed sessions.
- Whether WebAuthn signatures actually verify or session serialization is intact.
- Whether the rest of your dependencies remain compatible on upgrade.
- Version qualifiers or Maven/Gradle resolution semantics.

**Never copy this comparator into production triage tools.** Use SCA/OSV ranges/official Spring advisories alongside resolved graphs and verified evidence.

## 13. Regression Testing After Updating Spring Security

### 13.1. Authentication

| Capability | Positive Test | Negative / Security Test |
|---|---|---|
| Username/password | Valid password verified through real provider | Wrong password, disabled/locked account cannot log in |
| Password hashing | `PasswordEncoder.matches` accepts stored hash | Rejects other passwords; legacy hash migration follows policy |
| HTTP Basic | Valid Basic credentials grant access | Missing/wrong credentials → 401 + Basic challenge |
| OAuth2 JWT Resource Server | Real signed JWT with valid issuer/audience/time | Bad signature, `alg`, issuer, audience, expired → 401 |
| Form login | Session context saved after POST + CSRF | Missing/invalid CSRF creates no session |
| Session management | Session fixation protection, logout/invalidate | Old/revoked cookies lose access |
| Authorization | Matching role and owner can access resource | Cross-tenant/BOLA/`@PreAuthorize` denied |
| OTT/magic link | Fresh token, TTL, single-use | Expired, replayed, concurrent consume, wrong purpose |
| WebAuthn/passkey | Assertion signed for right origin/RP/UV | UV=false when REQUIRED, stale challenge/wrong session |
| MFA/step-up | Current factors and freshness satisfied | Password only, wrong-owner/expired/removed factor |
| OIDC | Valid callback and accurate identity mapping | State/nonce/issuer mismatch, email collision/link hijack |

**Never rely solely on `@WithMockUser` or `jwt()` to claim you tested password verification or JWT signatures.** Those test fixtures pre-populate the principal; write at least one integration test running through the real filter/provider/decoder with real credentials or test-key signatures.

### 13.2. Crucial Tests for CVE-2026-47841

If the app uses WebAuthn `UV=REQUIRED` and distributed HTTP sessions:

1. Generate a WebAuthn challenge/options per real config, storing request context in the shared session.
2. Pass the request through serialize/deserialize across two nodes or session store integration.
3. Use a virtual authenticator or WebAuthn test key to produce a validly signed assertion **with `UV=false`**.
4. Assert **login is rejected** under `UV_REQUIRED`, even when signature/challenge/origin/RP ID are all valid.
5. Produce an assertion with `UV=true`, satisfy all checks, and assert login succeeds.
6. Verify replayed assertions/challenges and another user's credentials are rejected.
7. Run tests on **the new build and production-equivalent environment**, not just a unit test on one method that skips session serialization.
8. Confirm all nodes run the new image digest, with no rolling deployment leaving older versions serving traffic past allowed windows.

### 13.3. Tests for CVE-2026-47842

If the app uses the affected Spring Security crypto encryptors:

- Verify ciphertexts encrypted before upgrade decrypt cleanly after migration per documentation.
- Verify new ciphertexts use proper IVs/nonces so identical plaintexts do not produce exploitable identical outputs.
- Verify key rotation, backwards-compatibility windows, and data-format rollback.
- Test corruption/truncation/tampering under the new mode and format; AEAD/GCM enforces authentication tags.
- Never test with production personal data/keys on public CI.
- Keep migration verification alongside backup/restore runbooks rather than treating a green build as sufficient.

### 13.4. Non-Authentication Regressions

Upgrading Boot/Security can affect `SecurityFilterChain` matcher ordering, 401/403 exception handling, CSRF, CORS, cookie `SameSite`, Spring Session serialization, OAuth claim mappings, method security proxies, WebFlux vs. Servlet differences, resource-server auto-config, HSTS, and error responses.

A sudden spike in `401`s after deployment may come from issuer/audience validator or cookie changes rather than "the patch blocked attacks". Watch security metrics, canary traffic, and controlled synthetic login flows.

## 14. Recommended CI/CD Workflow

### 14.1. Before Opening a PR

```text
1. Inventory deployed version/image digest.
2. Look up CVE in Spring Advisory; read full conditions, affected/fix.
3. Log finding ticket: version evidence + feature + impact + severity.
4. Choose compatible patch branch, OSS/Enterprise entitlement.
5. Update Boot/BOM/lockfile or sanctioned override.
6. Check dependency diff and API migrations.
7. Run unit + Spring integration + security negative tests.
8. Scan resolved runtime dependencies and new SBOM.
9. Review source, release notes, repository, and provenance.
```

### 14.2. Inside CI

Illustrative pipeline logic (not complete YAML):

```text
CHECKOUT pinned commit
VERIFY JDK + Maven/Gradle Wrapper
VERIFY dependency lockfiles/repositories
RESOLVE runtime dependency graph
GENERATE build-scoped SBOM
RUN SCA (fresh advisory feed; fail on scanner errors)
TRIAGE relevant findings / check approved exceptions
RUN unit tests
RUN authentication/security integration tests
BUILD artifact and container image
SCAN artifact/container/image digest
SIGN/ATTEST artifact if organization policy requires
PUBLISH immutable artifact + SBOM + reports
```

**Never expose scanner API keys, signing keys, authorization tokens, or IdP credentials in logs.** Use secret managers/CI-scoped credentials. Pin action/plugin versions where appropriate and test how they are updated.

### 14.3. Before Deployment

- Review PR diff, Gradle/Maven resolved versions, SCA report, and advisory prerequisites.
- Run security canaries: login success/failure, role denial, JWT rejection, WebAuthn `UV=REQUIRED` on distributed sessions, logout.
- Verify rollback image digest **and** schema/serialized-session/data-migration rollback paths if formats changed.
- Approve a change window matching urgency with active on-call monitoring.
- If the patch requires irreversible migrations, binary rollback may be unsafe; prepare a forward-fix plan.

### 14.4. After Deployment

- Verify exact **image digest** on every pod/node; ensure canaries do not leave old builds serving auth routes.
- Check `BOOT-INF/lib`/runtime SBOM for exact resolved versions.
- Compare 401/403/5xx error rates, session login rates, WebAuthn UV errors, MFA completion, token refreshes, and latency.
- Run negative security tests against production-like synthetic accounts.
- Record patch deployment timestamp, CVE closure, and fresh evidence in the security registry.
- Keep monitoring for new advisories; never treat "patched this month" as permanent safety.

## 15. When Patches Are Unavailable or Incompatible

You may hit a situation where a fix is released only via **Enterprise Support** on an older release line while upgrading to a newer OSS release line requires major migration. Never fabricate versions/forks or claim a fix exists on public repositories.

Reasonable workflow:

1. Confirm **exact affected range** and **availability** from the live advisory.
2. Verify the organization's support contracts/repository access and compatibility matrix.
3. Estimate upgrading to a supported OSS branch; accept that 6.x → 7.x may not be a one-line bump.
4. Apply vendor-published **mitigations**; if none exist, consider temporarily disabling the exposed feature, restricting reachability, or adding provable server-side checks under policy/risk approval.
5. Never treat a WAF as a guaranteed fix for internal authentication bypasses.
6. Record owner/deadline, test the mitigation, and maintain monitoring and rollback plans.
7. Once a compatible patch is available, roll out through reviews/tests/SBOM/deployment verification.
8. Notify users/security stakeholders if exploitation occurred or legal rules apply.

**Special caution:** if WebAuthn user verification is a mandatory security layer, temporarily switching `REQUIRED` to `PREFERRED` to sidestep the CVE condition **can severely weaken assurance**. Never call that an equivalent remediation if your threat model mandates UV; obtain formal approval and verification.

## 16. Common Mistakes When Handling Advisories

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| "We use Boot 3 so Security is always safe" | Specific patches can fall inside affected ranges | Check BOM and resolved runtime versions |
| "We bumped the BOM so prod is patched" | Stale lockfile/image/missing redeploy | Inspect live artifacts and digests |
| "Scanner says HIGH CVE so every app is exploitable" | May require specific features/configs | Triage prerequisites per advisory and test |
| "We don't use WebAuthn, yet force-upgrade to Security 7" | Major upgrades bring migrations/regressions | Choose compatible patch paths by risk |
| "Fix 6.5.12 exists so anyone can download it publicly" | Advisory states Enterprise Support Only | Verify entitlements and distribution channels |
| "Only bumping `spring-security-web` is enough" | Sibling modules/trains drift out of sync | Use BOM and `dependencyInsight` |
| "Scan shows zero findings so no CVEs exist" | Broken feed or missed components | Verify scan completeness and primary advisories |
| "CVE in test scope means web runtime is exposed" | Different attack surfaces | Separate runtime/test/build/CI findings |
| "No call site in grep means unaffected" | Dynamic config/reflection/transitive use | Analyze runtime/config and trace with evidence |
| "Low CVSS so ignore it" | Exploitability and impact are app-specific | Combine CVSS/EPSS/KEV and attack paths |
| "Suppress scanner warning to turn pipeline green" | Hides real risk | Timeboxed suppression with approval + evidence |
| "`@WithMockUser` passes so password/JWT is verified" | Fixture bypasses auth providers | Integration test with real credentials/keys |
| "Upgraded crypto encryptor without migrating data" | Old ciphertexts may fail to decrypt | Read migration advisory, backup/migrate/test |
| "Changing admin password in DB revokes all JWTs" | Stateless tokens remain valid until expiry | Enforce versioning/introspection/revocation policies |
| "Checked only local build" | Deployed image may differ | Attested artifact SBOM + runtime digest |
| "Disabled `UV=REQUIRED` to dodge the CVE" | Downgrades assurance | Review threat model and vendor mitigations |
| "Old release notes suffice for current patching" | Advisories can expand affected ranges | Read live official advisory on triage day |

## 17. Periodic Operations Checklist

1. **Inventory:** maintain catalog of services, owners, deployed versions, SBOM/image digests, JDK, Spring Boot, Security, runtime, and transitive libraries.
2. **Advisory ingestion:** monitor Spring advisories/RSS, NVD/GHSA/OSV, and vendor security announcements.
3. **Applicability:** for each CVE, record package, exact version range, affected features/config, and evidence.
4. **Availability:** distinguish OSS, Enterprise, unsupported/EOL, and release-train compatibility.
5. **Prioritization:** severity + reachability + exploit maturity + sensitivity, with SLAs/owners.
6. **Patch design:** consistent Boot/BOM dependency graph, updated lockfiles, no blind module forcing.
7. **Security tests:** wrong passwords, 401/403, JWT issuers/audiences, CSRF, sessions, roles, OTT/WebAuthn/MFA.
8. **Crypto/data migration:** backups, restores, re-encryption, compatibility, viable rollbacks.
9. **CI gates:** scanner freshness/failure detection, timeboxed exceptions, per-release SBOMs, immutable artifacts.
10. **Production verification:** rollout/canary, exact image digests, metrics, rollbacks, and regression evidence.
11. **Incident handling:** on auth bypass, collect redacted audits, check session/token validity, identify affected customers per policy.
12. **Repeatability:** keep reproducible scripts/commands and artifact evidence for the next incident, not just a chat message saying "updated".

## 18. Self-Assessment Questions

**Q1.** A project declares `spring-boot-starter-security` with no version in Gradle. How do you find which Spring Security version actually runs?  
**A:** Inspect the Spring Boot BOM and `dependencyInsight --configuration runtimeClasspath` for the resolved JAR version; then verify `BOOT-INF/lib`/SBOM/production image digest.

**Q2.** A scanner flags `spring-security-web:6.5.10` for CVE-2026-47841. Can you immediately declare the entire site affected?  
**A:** Not yet. Verify whether the app uses WebAuthn, `userVerification=REQUIRED`, and distributed HTTP sessions per the advisory, alongside the live deployed version. Without evidence, status is `POTENTIALLY_AFFECTED`, not `NOT_APPLICABLE`.

**Q3.** Per the 2026-08-20 advisory, is fix `6.5.12` listed as OSS?  
**A:** No; the advisory marks it **Enterprise Support Only**. `7.0.7`/`7.1.1` are listed as OSS. Pick a compatible version and verify real download channels.

**Q4.** Why not override `spring-security-web` alone to `7.0.7` inside Spring Boot 3 to fix a CVE?  
**A:** Spring Security modules and Spring Framework have release-train compatibility constraints. Mixing majors can cause compile/runtime failures, config bypasses, or data migration issues; follow the BOM/vendor guidance and verify the whole graph.

**Q5.** SCA failed to download the NVD feed, yet the report shows zero findings. Is the build safe?  
**A:** No. The scan is incomplete; never turn a scanner failure into "No vulnerabilities".

**Q6.** Data was encrypted with `AesBytesEncryptor` before patching; why read the migration guide?  
**A:** CVE-2026-47842 changes IV/KDF behavior and replacement APIs; old ciphertexts may fail to decrypt under the new encryptor, requiring assessment and data migration.

**Q7.** A pull request has a clean dependency tree, yet production pods have not redeployed. Is the CVE closed?  
**A:** No. You must verify the new artifact/image digest is actually running with patched runtime dependencies and passing security regression tests.

**Q8.** Does `@WithMockUser` passing on `/admin` prove WebAuthn UV verification works after an upgrade?  
**A:** No. You need integration tests with real signed assertions having `UV=false`/`true`, distributed session serialize/deserialize, and challenge/origin/RP/credential ownership checks.

**Q9.** A scanner flags a CVE in a build-time Maven plugin. Can it be ignored simply because it is absent from the runtime JAR?  
**A:** Not automatically. Classify the attack surface as CI/build, evaluate attacker access and impact on artifacts/secrets, and handle by risk.

**Q10.** Does `NOT_APPLICABLE_BY_CONFIGURATION` stay valid forever?  
**A:** No. Enabling features, adding distributed sessions, or changing security configs can make the CVE conditions true. Suppressions need owners, expiration dates, and architectural-change reviews.

**Q11.** When a Spring Security upgrade changes encrypted-data formats, is binary rollback sufficient?  
**A:** Not necessarily; evaluate ciphertext compatibility, migrations/backups, and forward-fixes. Verify data rollback feasibility and key protection.

**Q12.** Should you keep monitoring advisories after one successful upgrade?  
**A:** Yes. A release fixing CVE A may still carry or later disclose CVE B; SBOM inventories, scanners, and advisory monitoring must run continuously.

## Official References

- [Spring Security Advisories – updated list](https://spring.io/security/): look up CVEs by project/generation, affected versions, and fix releases.
- [CVE-2026-47841 – WebAuthn UV bypass and session serialization](https://spring.io/security/cve-2026-47841/): affected versions, simultaneous prerequisites, and OSS/Enterprise fixes published 2026-08-20.
- [CVE-2026-47842 – AesBytesEncryptor deterministic CBC](https://spring.io/security/cve-2026-47842/): affected versions, fixes, replacement APIs, and data migration guidance.
- [Spring Boot – Build Systems / Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): BOMs, release trains, and Spring library version management.
- [Spring Boot – Managing Dependencies in the Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dependency-management plugin vs. native BOM and overrides.
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` and `dependencyInsight`.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved dependency graphs and parameters.
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/): SCA, data feeds, and limitations.
- [OWASP Dependency-Check Gradle Plugin](https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/index.html): plugin setup and `dependencyCheckAnalyze` task.
- [OSV.dev](https://osv.dev/): ecosystem/package vulnerability database.
- [NVD – National Vulnerability Database](https://nvd.nist.gov/): CVEs/CVSS and public metadata.
- [CycloneDX](https://cyclonedx.org/): SBOM standard for software and components.
- [OWASP – Vulnerable and Outdated Components](https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/): managing risks from outdated libraries.
