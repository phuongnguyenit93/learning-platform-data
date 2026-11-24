# Dependency Hardening and Version-Based Vulnerability Advisory Checks — Spring Security Reactive

## 1. Objective

A Spring Security application running on Spring WebFlux may have sound authentication and authorization configurations yet still face risk from vulnerable libraries: Spring Security, Spring Framework, Reactor Core, Reactor Netty, Netty, JWT/OAuth2 libraries, JSON parsers, HTTP clients, logging, or transitive dependencies.

This lesson shows how to:
1. Identify the **exact versions actually built, packaged, and running**; distinguish declared dependencies from resolved versions.
2. Look up security advisories by **artifact, version, support branch, exploitation conditions, and fixed versions**.
3. Upgrade safely following the Spring Boot BOM/compatibility matrix with WebFlux/Spring Security-specific regression tests.
4. Automate SBOM generation, Software Composition Analysis (SCA) scanning, alert triage, and proof that patches exist in the deployed artifact.

**Principle:** Never conclude a system is safe solely because a dependency scanner reports green, nor assume every CVE flagged by a scanner is exploitable in your system. Combine actual versions, advisory conditions, runtime configuration, exposure level, and test evidence.

## 2. Dependency Surface of a Reactive Application

A Spring Boot WebFlux service may use:
- **Spring Security:** spring-security-core, spring-security-config, spring-security-web, OAuth2 client/resource server modules, JOSE/JWT, and test modules.
- **Spring WebFlux / Framework:** spring-webflux, spring-web, supporting Spring Framework modules.
- **Reactive runtime:** reactor-core, reactor-netty-http, Netty transport, HTTP codecs, TLS/HTTP2, and transitive Netty modules.
- **HTTP clients and identity:** WebClient, JWT/JWK signature handling, OAuth2/OIDC/JOSE libraries pulled in via starters.
- **Serialization/observability:** Jackson, logging frameworks, Micrometer, tracing bridges, OTEL/Brave.
- **Deployment software:** JDK/JRE, base container images, native libraries, reverse proxies, ingress, API gateways. These require separate scanning pipelines outside Maven/Gradle.

**Note the stack distinction:** WebFlux commonly uses SecurityWebFilterChain, WebFilter, Reactor Context, and Reactor Netty. Vulnerabilities affecting Servlet filters, HttpSession, or Tomcat may not apply when a service does not use them; conversely, Reactor Netty, reactive security, or WebClient vulnerabilities can be missed if auditing only Servlet paths. An app carrying both Servlet and reactive libraries on the classpath does not automatically share the same exploit path: check the active web application type and runtime configuration.

Also inventory test/build and plugin dependencies; while absent from runtime, they still affect CI environments or the supply chain. Classify them clearly so you do not infer that a test-classpath-only library is packaged into production.

## 3. Discovering the Exact Resolved Versions

Declared dependencies can be governed by a parent POM, BOM, Gradle platform, constraints, resolution rules, or transitive dependencies. Therefore, declaring no version number does not mean the app uses the "latest version." CVE checks must rely on the **resolved dependency graph** of the exact commit and build being deployed.

### Maven: Listing Dependencies and Version Management Sources

Run from the project directory containing the Maven Wrapper:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

On Windows, use mvnw.cmd instead of ./mvnw. The first command displays direct and transitive dependencies, the second focuses on the runtime classpath, and the last generates the effective POM to inspect parents, dependencyManagement, and overrides. In multi-module projects, run in the packaged application module or inspect each relevant module's dependency tree; root-level output does not always match the deployed artifact.

Look for key coordinates such as:
- org.springframework.security:spring-security-web
- org.springframework.security:spring-security-config
- org.springframework:spring-webflux
- io.projectreactor:reactor-core
- io.projectreactor.netty:reactor-netty-http
- io.netty:netty-handler
- JWT/OAuth2 processing libraries appearing in the actual tree.

Find the **resolved version** and the dependency path pulling the library in, rather than merely grepping a string in pom.xml.

### Gradle: Inspecting runtimeClasspath and Resolution Paths

In a Gradle project with Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

The dependencyInsight command explains why a version was selected—for example via BOM, constraints, conflict resolution, or transitive dependency. For multi-project builds, run tasks on the relevant subprojects. On Windows, replace ./gradlew with gradlew.bat.

**Proving versions at deploy time:** A build log claiming a version is not enough. Reconcile the dependency graph/SBOM against the contents of the running JAR/WAR and container image; identical source built at different times can resolve different libraries. Record the commit SHA, build ID, artifact digest, base image digest, and SBOM. Never rely on version numbers logged in a manual spreadsheet without the matching build record.

## 4. BOMs and Compatibility: Upgrading Across the Spring Family Together

Spring Boot manages many dependencies via the spring-boot-dependencies BOM; the Maven starter parent and Gradle dependency-management/platform mechanisms use the BOM to align compatible versions. In Spring Security Reactive, upgrading a single JAR in isolation can skew versions across Spring Security, Framework, Reactor, and Netty.

**Maven (pom.xml snippet for a project already using the Spring Boot parent):**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

This is a **POM snippet**, not a complete POM. Starter versions are managed when an appropriate parent/BOM is configured elsewhere. If using only HTTP Basic or form login, do not add OAuth2 Resource Server unnecessarily; keep only truly needed dependencies. If managing versions via a BOM without the starter parent, import the BOM properly according to your build configuration.

**Gradle (Kotlin DSL, snippet for a build already applying the Spring Boot plugin):**

~~~kotlin
dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
~~~

Gradle also supports applying the io.spring.dependency-management plugin to import the BOM automatically. The Kotlin snippet above illustrates native Gradle platform usage, not a standalone build.gradle.kts file. Verify that the BOM was actually imported using dependencies and dependencyInsight.

**Version selection workflow:**
1. Identify the running Spring Boot branch and whether it still receives security support.
2. Look up affected Spring Security/Spring Framework/Reactor Netty versions in advisories; find the patch on a **compatible branch**.
3. Prefer a Spring Boot patch/minor release whose managed versions already include the fix; review release notes and Spring Boot-managed dependency versions.
4. If an emergency single-dependency override is needed before the BOM updates, document justification, override scope, binary compatibility, tests, and removal date. Avoid blanket forcing via resolutionStrategy.force or unconditional exclusions.
5. For major/minor upgrades, check Java baselines, migration guides, `SecurityWebFilterChain` API changes, OAuth2/JWT, and framework behavior.

Patch releases usually introduce fewer API changes than major/minor releases, but **zero behavior changes are not guaranteed**: security patches may intentionally tighten validation and expose pre-existing misconfigurations. Never defer indefinitely by staying on an end-of-life branch.

## 5. Security Information Sources and Reading Advisories

Prioritize sources in order:
1. **Vendor advisories:** [Spring Security Advisories](https://spring.io/security/), describing trigger conditions, affected versions, fixed versions, and availability.
2. **Release notes and support policies:** Spring Boot, Spring Security, and Reactor/Netty for the active branch.
3. **Vulnerability databases:** [NVD](https://nvd.nist.gov/), [GitHub Advisory Database](https://github.com/advisories), and [OSV](https://osv.dev/) to cross-reference CVEs, GHSAs, package ecosystems, and metadata.
4. **Active exploitation intel:** [CISA Known Exploited Vulnerabilities](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) when prioritizing; never substitute a raw CVSS score for deployment context.

An advisory typically includes:
- **CVE/GHSA and publication date**: tracking identifiers and dates, not library versions.
- **Affected products/versions**: affected version ranges; read inclusive bounds, branches, and numbering carefully. Never compare versions as plain strings (e.g., 1.3.10 differs from 1.3.7).
- **Conditions/prerequisites**: required components, invocation patterns, enabled features, configurations, and external exposure.
- **Fix versions/availability**: corresponding branches and patched releases; distinguish OSS from Enterprise Support Only.
- **Mitigation/workaround**: temporary controls and their limits; never treat a workaround as a permanent patch.
- **Migration/behavior changes**: may require config, API, or encrypted-data changes; not just bumping a version number.

Save a dated snapshot of your assessment, and re-verify before release because advisories can be amended, gain new branches, or be retracted.

## 6. Correlating CVEs Against Exact Versions and Usage Conditions

For **each flagged dependency**, follow this chain:

**Actual artifact → resolved version → official advisory → impact conditions → same-branch fixed version → upgrade/test evidence → decision.**

Investigation table template:

| Field | What to Record |
| --- | --- |
| Artifact and scope | Maven coordinates, module, runtime/test/build, transitive dependency path |
| Actual version | Version in lockfile/SBOM/JAR or image by build ID |
| Advisory | CVE/GHSA, vendor URL, verification date |
| Impact conditions | WebFlux vs. Servlet, features, runtime config, attacker privileges, involved data |
| Conclusion | Affected and reachable; affected but feature unused; false positive; under verification |
| Remediation | Fixed version, support branch, interim mitigation, tests, deadline, owner |
| Evidence | PR, dependency tree diff, new SCA report, regression test results, artifact digest |

Never assume "not exploitable" just because you see no direct API call: transitive dependencies, auto-configuration, library reflection, or framework entry points may invoke it on the app's behalf. Reachability conclusions require code/config review or reliable tooling; lacking evidence, mark status "unverified" and apply appropriate mitigations.

## 7. Real Example: CVE-2026-47844 in Reactor Netty

According to the [official CVE-2026-47844 advisory](https://spring.io/security/cve-2026-47844/) published on **2026-08-20**, Reactor Netty HTTP Server may leak exception details across unrelated requests **under certain conditions when the server is configured with Brave Tracing**. The advisory lists affected branches:
- Reactor Netty **1.3.0 through 1.3.6**.
- Reactor Netty **1.1.0 through 1.2.18**.
- Reactor Netty **1.0.52 and earlier**.

The advisory identifies the fix as **1.3.7 (OSS)**. Several other fixes listed are exclusive to Enterprise Support; never infer that every version listed is available in public OSS repositories.

Suppose a WebFlux service's resolved dependency graph contains reactor-netty-http 1.3.6. Check:
1. Is the app actually running Reactor Netty HTTP Server, or was the module pulled in for another reason?
2. Is Brave Tracing used under the advisory's conditions? Inspect tracing-bridge dependencies, active beans/configs, and production state.
3. Does the deployed artifact carry this exact version? Verify in the dependency tree and SBOM.
4. If version and impact conditions match, upgrade to the compatible fixed release per the verified BOM/branch; test concurrent access, exception handling, tracing propagation, logs, and latency.
5. If conditions remain uncertain, never downgrade the alert to "safe"; mark it "needs verification" and prioritize patching.

**Takeaway:** A CVE specifying a trigger feature does not mean every app holding that JAR is exploitable; however, scanners cannot replace human runtime verification. At the same time, a package absent from pom.xml can still be pulled in indirectly by a starter.

Another example: [CVE-2026-47842](https://spring.io/security/cve-2026-47842/) affects specific uses of `AesBytesEncryptor` in Spring Security; the advisory warns that some crypto API upgrades also require **migrating already-encrypted data**, because the patched version may not read legacy data under the old config. Therefore, never reduce every security fix to "bump the dependency and restart."

## 8. Automated SCA Scanning for Maven

[OWASP Dependency-Check](https://owasp.org/projects/Dependency-Check) analyzes known dependencies for published vulnerabilities. Example configuration **to add under build/plugins** in Maven pom.xml (plugin version 13.0.0 matches official documentation checked on 2026-11-07):

~~~xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>13.0.0</version>
    <configuration>
        <failBuildOnCVSS>7.0</failBuildOnCVSS>
        <failOnError>true</failOnError>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Run:

~~~bash
./mvnw verify
~~~

The check goal binds to verify; by default the report is written to target/dependency-check-report.html. The 7.0 threshold here means the build fails if a vulnerability meets or exceeds that CVSS score, though **this threshold is an illustrative policy** that must be tuned to your project's risk appetite and triage process. Note that the plugin defaults to failBuildOnCVSS=11—scanning without failing since CVSS runs 0–10—so gating requires setting it explicitly.

Analysis requires up-to-date vulnerability data. Initial NVD syncs can take a while; in CI, configure caching/mirrors or an NVD API key, store the key in secrets, and keep it out of logs. Data download failures must never turn into "zero CVEs found" reports. With failOnError=true, the pipeline fails closed if the scanner cannot run.

**Reading the report:** Cross-check artifact/CPE/PURL, actual version, transitive root cause, upstream advisory, and fix status. Tools can mismatch CPEs, lag behind new advisories, or report CVEs whose exploit conditions the app does not meet; scan output is an investigative signal, not a final verdict.

## 9. Automated SCA Scanning for Gradle

Example using **Groovy DSL build.gradle**, adding the plugin to the existing plugins block and configuring the task (OWASP Dependency-Check plugin 13.0.0 verified in docs/plugin portal at time of writing):

~~~groovy
plugins {
    id 'org.owasp.dependencycheck' version '13.0.0'
}

dependencyCheck {
    failBuildOnCVSS = 7.0
    failOnError = true
}
~~~

If build.gradle already has a plugins block, merge the plugin line into it; never create two conflicting blocks. Run:

~~~bash
./gradlew dependencyCheckAnalyze
~~~

Reports are generated under build/reports by default; for multi-project builds, consider dependencyCheckAggregate to cover all subprojects properly. Verify plugin compatibility with your exact Gradle/JDK version before integrating. Never leave scan tasks manual-only and skipped on release branches.

Both Maven and Gradle can combine multiple scanners, such as OSV-Scanner or your CI platform's native dependency manager. Each scanner uses different feeds and matching rules: aggregate results and verify upstream advisories rather than counting duplicate CVEs as separate incidents.

## 10. SBOM: Recording Build Components for Ongoing Lookup

An SBOM (Software Bill of Materials) lists the components and dependency relationships tied to an artifact. For reactive apps, an SBOM quickly answers "which deployed services shipped reactor-netty-http 1.3.6?" when a new advisory drops.

**Maven: generate a CycloneDX SBOM** (illustrative command for projects with Maven Wrapper; 2.9.3 is published on Maven Central):

~~~bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
~~~

**Gradle: add CycloneDX plugin 3.5.1 to the plugins block of the relevant Gradle project**:

~~~groovy
plugins {
    id 'org.cyclonedx.bom' version '3.5.1'
}
~~~

~~~bash
./gradlew cyclonedxBom
~~~

With CycloneDX Gradle 3.x, cyclonedxBom generates an aggregate SBOM across participating subprojects; depending on release needs, a direct SBOM for the exact deployed module can be more accurate than a repo-wide aggregate SBOM. Never assume a broad aggregate SBOM equals the exact contents of each JAR. Validate contents by confirming Spring Security, Spring WebFlux, Reactor Netty, and Netty runtime modules appear before archiving.

**Metadata to attach to the SBOM:** service name, app version, commit SHA, build ID, dependency lock, build timestamp, artifact/image digest, and target environment. Store the SBOM alongside the artifact in an access-controlled repository. An SBOM captures composition at build time; it does not replace re-scanning when new advisories appear, nor prove the artifact was built from trusted sources or carries signed provenance.

## 11. Version Locking and Dependency Verification Against Drift

Two distinct problems must be solved:
- **Reproducibility:** builds today and tomorrow resolve the exact same approved set of artifacts.
- **Integrity/provenance:** downloaded artifacts match expected contents without tampering or fetching from untrusted repositories.

With Gradle, enable dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or intentionally update the lockfile:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit gradle.lockfile after reviewing changes; when a patch is approved, update the lock in the same PR and inspect the diff. Lockfiles stop transitive dependencies from silently shifting, **yet also lock in vulnerable versions** without a regular update cadence. Also lock buildscript/plugin configurations when they are critical to build integrity.

Alongside locking, enable [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/securing_dependencies.html) where appropriate to verify library checksums/signatures via gradle/verification-metadata.xml. Audit repository sources, disallow uncontrolled snapshots/dynamic versions, pin plugins, and avoid untrusted repositories. With Maven, rely on dependencyManagement/BOMs, fixed versions, Maven Wrapper, repository policies, and reproducible build controls. Locking versions and verifying checksums are two independent layers; neither fixes CVEs by itself.

## 12. Version-by-Version Dependency Patching Workflow

### Step 1 — Receive Alert and Scope Impact

Receive advisories via Spring RSS, SCA tools, Dependabot/Renovate, or vulnerability management systems. Identify impact by artifact, resolved version, running product, config, and exposure. Check live deployed images and older release branches still serving traffic—not just main's HEAD.

### Step 2 — Prioritize by Real Risk

Assess CVSS, CISA KEV, public exploits, remote exploitability, authentication prerequisites, affected data/resources, and Internet exposure. Auth bypass/RCE on public endpoints usually demands urgent action. Never treat CVSS as the sole ranking; a medium-severity bug that is definitely reachable may outrank a high-severity bug whose preconditions do not exist.

### Step 3 — Choose an Upgrade Path

Prefer a patched and still-supported Boot/Security/Reactor release. For branches without OSS patches, evaluate upgrading to a supported branch or an actual active commercial support contract; **never pick an Enterprise-only version assuming you can download it**. Read release notes, migration guides, and changelogs—especially when patches touch cryptography, session handling, proxy headers, or authorization.

### Step 4 — Make Reviewable Changes

Open a small PR: bump BOM/parent/plugin versions and lockfiles, remove obsolete overrides, and link the advisory. Run automated tests; avoid mass-upgrading hundreds of unrelated dependencies when a focused update solves the issue. If a major upgrade is unavoidable, break it into stages backed by regression tests and rollback plans.

### Step 5 — Verify Build and Runtime

After building, run dependency:tree/dependencyInsight and re-scan SCA, diff old vs. new SBOMs, and verify artifact digests. Deploy to a staging environment matching production config; test auth flows, WebClient, tracing, and the HTTP server. Never treat a passing build as proof the CVE is gone if a constraint dragged the version back down or the deployed image wasn't updated.

### Step 6 — Release and Monitor

Use phased/canary rollouts where appropriate, watching 401/403s, 5xxs, token validation failures, session issues, throughput, latency, and memory. Prepare artifact-level rollback, though never revert to an actively exploited version if a safer mitigation exists. Archive evidence and close alerts against the exact deployed artifact.

## 13. Regression Testing Specific to Spring Security WebFlux

Upgrading Spring Security, Spring Framework, Reactor Netty, or OAuth2/JWT libraries can alter reactive-layer behavior even when the service compiles cleanly.

| Scenario | What to Verify |
| --- | --- |
| Unauthenticated requests | Protected endpoints return 401; public endpoints still work. |
| Badly signed, expired, or wrong-issuer/audience tokens | Resource Server rejects per actual config; modified tokens are never accepted. |
| Authenticated with insufficient permissions | Endpoints return 403 or designed behavior; `SecurityWebFilterChain` rules are never bypassed. |
| CSRF, CORS, session/cookies | Rules match browser vs. token auth model; allowed origins never silently widen. |
| Reactive context propagation | `SecurityContext` is neither dropped nor leaked across requests across scheduler/concurrency hops. |
| WebClient/downstream | TLS, timeouts, retries, OAuth2 client credentials, and HTTP status mappings behave as expected. |
| HTTP/2, Netty, and tracing | Test under real usage, especially when advisories involve Brave/OTel tracing or specific protocols. |
| Observability | Logs/traces never leak tokens, cookies, or personal data during exceptions, retries, and timeouts. |

Use `WebTestClient` with a test application context and version-appropriate Spring Security test utilities; exercise real requests through the filter chain. Never write tests that merely assert a class loads: that does not prove a vulnerability is fixed. For advisories with concrete exploit patterns, craft safe negative tests in an isolated environment; never test exploits against production.

## 14. Designing CI/CD Quality Gates

An effective pipeline includes auditable checks:

~~~text
Pull request
  -> Resolve dependency graph + verify lock/checksum
  -> Unit/integration tests (SecurityWebFilterChain, OAuth2/JWT, WebClient)
  -> SCA scan (OWASP Dependency-Check / OSV / org platform)
  -> Triage: version + conditions + fix + risk
  -> Build artifact, publish SBOM and digest
  -> Staging deploy + smoke/regression tests
  -> Approve/rollout + archive running artifact evidence
  -> Re-scan SBOM/artifacts when new advisories emerge
~~~

Policy suggestions:
- **Explicit gates:** Block unapproved vulnerabilities above a defined risk threshold or with active exploitation evidence; fail if the scanner cannot refresh required vulnerability data.
- **No suppression abuse:** For false positives or non-reachable findings, suppressions must specify CVE/artifact/version, rationale/evidence, approver, and review expiry. Never suppress entire `org.springframework` or `Netty` groups to greenwash reports.
- **Keep decision data fresh:** NVD/OSV/advisories can be updated after an artifact ships. Schedule periodic scans of running releases and subscribe to new alerts.
- **Protect the pipeline:** Pull repo/NVD scanner credentials from a secret store with least privilege; never print tokens to logs, trust unapproved repositories, or disable failOnError to bypass release gates.
- **Separate false positives from non-reachable:** A false positive is a wrong artifact/version match; non-reachable means the advisory genuinely applies to the component, yet evidence proves the exploit condition does not exist. Both decisions require distinct evidence.

## 15. Common Mistakes to Avoid

1. Checking only the Spring Boot version in pom.xml without verifying resolved Spring Security and Reactor Netty versions.
2. Auditing only direct dependencies while ignoring transitives pulled in by starters or other libraries.
3. Bumping a single Spring Security JAR alone, skewing versions across config/web/oauth2 modules or Framework.
4. Seeing a CVE with the same package name and assuming "exploitable" without checking affected ranges, conditions, and Servlet vs. Reactive stack.
5. Using string comparison for versions, missing that 1.3.10 is greater than 1.3.7.
6. Assuming every fix listed in an advisory is OSS, ignoring Enterprise Support Only and EOL labels.
7. Editing build.gradle/pom.xml without updating the Gradle lockfile, container image, deployment manifest, or live traffic workloads.
8. Treating a green SCA report as sufficient when NVD data is stale, the scanner failed, or actual dependencies weren't scanned.
9. Disabling entire rule sets because alerts are noisy, without recording owners, evidence, and expiry dates for exceptions.
10. Applying security upgrades without testing 401/403s, JWT validation, reactive context, tracing, WebClient, and the HTTP server.
11. Publishing wrongly scoped aggregate SBOMs that obscure which specific JAR/service contains the vulnerable version.
12. Ignoring older live deployments; `main` is patched while production traffic still runs on a vulnerable image.

## 16. Practical Release Checklist

- [ ] Commit, build ID, artifact/image digest, and resolved runtime dependency graph are known.
- [ ] Spring Security, Spring Framework, Spring WebFlux, Reactor Core/Netty, Netty, OAuth2/JWT, and transitives are audited.
- [ ] Active Spring Boot/Security branch support status and version-specific official advisories are checked.
- [ ] Every CVE has an analysis of affected range, runtime conditions, fix branch, and evidence.
- [ ] Patches align with the BOM/stack; any overrides are justified and tested.
- [ ] Build, security integration tests, SCA scan, and staging smoke tests all pass.
- [ ] SBOM and lockfiles match the artifact slated for deploy; scanner reports use fresh vulnerability data.
- [ ] No broad suppressions; exceptions have rationale, owners, expiry dates, and remediation plans.
- [ ] Rollout is monitored, with rollback/mitigation evaluated for security risk.
- [ ] Continuous advisory monitoring covers already-released artifacts.

## 17. Official Reference Documentation

- [Spring Security Advisories](https://spring.io/security/) — list of advisories and fixes by branch.
- [CVE-2026-47844 Reactor Netty](https://spring.io/security/cve-2026-47844/) — example of version ranges and Brave Tracing conditions, published 2026-08-20.
- [CVE-2026-47842 Spring Security](https://spring.io/security/cve-2026-47842/) — example showing patches can entail API/encrypted-data migration.
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html) — versioning and dependencies.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — BOM, Gradle platform/dependency-management.
- [Spring Boot — Supported Versions](https://github.com/spring-projects/spring-boot/wiki/Supported-Versions) — support policy and upgrade principles.
- [OWASP Dependency-Check Maven](https://dependency-check.github.io/DependencyCheck/dependency-check-maven/) and [Gradle](https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/) — commands, configuration, and reports.
- [CycloneDX Maven plugin](https://github.com/CycloneDX/cyclonedx-maven-plugin) and [Gradle plugin](https://github.com/CycloneDX/cyclonedx-gradle-plugin) — SBOM generation.
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) and [Dependency Verification](https://docs.gradle.org/current/userguide/securing_dependencies.html).

**Point-in-time note:** Specific version numbers in examples/advisories and plugins were verified against documentation published as of **2026-11-07**. Before each release, re-check upstream pages and verify actually downloaded artifacts; new releases, supported branch lists, and advisories may change.

**Remember:** Dependency hardening does not stop at bumping a version number. An evidence-based patch proves **the right package, the right version, the right support branch, the right impact conditions, and the right deployed artifact**, backed by tests confirming reactive security flows continue working.
