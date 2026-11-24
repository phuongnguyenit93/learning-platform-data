# Using Dependency Locking and Dependency Verification in Gradle

## 1. Two Complementary Mechanisms for Reproducible Builds

In a Spring Boot project, plugins, starters, and transitive libraries can form a large dependency graph. A declaration in `build.gradle` does not necessarily tell you the **final version** Gradle selects. At the same time, even when the selected version stays unchanged, JAR contents downloaded from a repository can differ from the artifact your team approved.

Gradle addresses those two problems with two distinct mechanisms:

1. **Dependency locking** persists **selected versions** after dependency resolution, per configuration. Lock state keeps the graph stable across builds, helping detect or block dependency version changes outside an approved process.
2. **Dependency verification** checks the **integrity/provenance** of artifacts and metadata downloaded by Gradle via checksums (e.g., SHA-256) and, where available, trusted PGP signatures.

| Question | Locking | Verification |
| --- | --- | --- |
| Which version of `spring-core` was actually selected? | Records and enforces the resolved version. | Does not select versions by itself. |
| Did a transitive dependency silently change versions? | Helps detect/prevent graph drift using lock state. | Accepts a new artifact only if verification policy has matching metadata. |
| Same version, yet JAR bytes were replaced? | **Cannot verify bytes.** | Compares checksums/signatures to catch mismatches. |
| Key configuration | `dependencyLocking`, `--write-locks`, `--update-locks`. | `gradle/verification-metadata.xml`, `--write-verification-metadata`. |
| Files to commit to Git | `gradle.lockfile` of locked projects. | `gradle/verification-metadata.xml` and public keyring if using PGP. |
| Does not replace | Hash checks, vulnerability scanning, runtime tests. | Version locking, vulnerability scanning, provenance of your own application source. |

**Conclusion:** version locking and file verification are two **cooperating** defense layers, not two names for the same feature. For a truly reproducible build, you must also control the Gradle Wrapper, plugin versions, JDK/toolchain, repositories, build inputs, packaged outputs, and CI workflows.

### 1.1. Which Environment Does This Lesson Use?

The examples use **Gradle Groovy DSL**, **Java 17**, **Spring Boot 3.3.13**, and **Gradle Wrapper 8.10.2** as an illustrative version set. Do not treat them as the latest versions at the time of reading. In real projects, choose versions supported by your organization and verify compatibility and repository policies.

We will build **a multi-project Gradle build** with two modules:

~~~text
repro-demo
├── core: internal Java library
│   └── commons-lang3: external dependency
└── app: Spring Boot Web app
    ├── core: project dependency
    └── spring-boot-starter-web: Spring MVC and web runtime
~~~

The app's `GET /state` endpoint calls code in `core`, and `core` uses Commons Lang's `StringUtils.capitalize`. Therefore verification requires not only Spring Boot startup, but actually loading both the **internal dependency and transitive dependency**.

## 2. Foundational Concepts: Requested Version, Selected Version, Artifact Bytes

### 2.1. From Declaration to Resolved Graph

Example:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

`3.+` is a **dynamic version**: today it may pick one 3.x release, and in the future if a repository publishes a newer release, the resolved version can change. Similarly, even when requesting a fixed version, Gradle constraints, platforms/BOMs, or conflict resolution may select another version on a given configuration.

Distinguish:

- **Requested version**: the version or range requested by the build script or dependency metadata.
- **Selected version**: the version actually chosen after resolution.
- **Artifact bytes**: the real contents of the JAR/POM/module metadata downloaded from a repository.
- **Runtime classpath**: the dependencies a module needs at runtime.
- **Packaged classpath**: the dependencies actually bundled inside the Spring Boot executable JAR, typically under `BOOT-INF/lib`.

Dependency locking protects **selected versions**. Dependency verification protects **artifact bytes/identity against trust metadata**. Neither automatically verifies that the executable archive was packaged properly or that endpoints work.

### 2.2. Dynamic vs. Changing Dependencies

A **dynamic version** such as `3.+` or `latest.release` can resolve to a new version; a lockfile is effective for stabilizing the selected version.

A **changing dependency**, especially `-SNAPSHOT` or a module marked `changing = true`, can be republished under the **same version coordinate with different bytes**. Per Gradle documentation, dependency locking is **unsuitable as a mechanism to guarantee reproducibility for changing versions**. Use immutable release artifacts, manage internal repositories/provenance, and maintain separate verification processes.

This does not mean creating verification XML automatically makes snapshots safe: Gradle dependency verification does not treat changing artifacts the same as immutable release files; do not rely on these two mechanisms to guard against snapshot overwrites without repository policies.

### 2.3. Checksums Are Not Vulnerability Scans

- SHA-256 compares a downloaded file against an **approved digest**. If an attacker alters contents later, a checksum mismatch catches it.
- If you initially bootstrap checksums from an **already poisoned** file, the new checksum will match the malicious file. Hence **trust establishment and review** are mandatory.
- PGP signatures verify a signer/key according to trust rules rather than merely comparing bytes. Not every library is signed.
- An artifact with a valid hash and signature can still contain CVEs or license issues. Use dedicated security/SBOM tools as well.

## 3. Complete Multi-Module Spring Boot Project

### 3.1. File Tree

~~~text
repro-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── verification-metadata.xml     (generated after bootstrapping)
├── core/
│   ├── build.gradle
│   ├── gradle.lockfile               (generated after writing lock state)
│   └── src/main/java/com/example/core/LibraryMessage.java
└── app/
    ├── build.gradle
    ├── gradle.lockfile               (generated after writing lock state)
    ├── src/main/java/com/example/app/ReproApplication.java
    └── src/test/java/com/example/app/ReproApplicationTest.java
~~~

The lockfiles and verification metadata **do not exist at the initial step**; Gradle generates them via the corresponding commands. Wrapper files `gradlew`, `gradlew.bat`, and `gradle-wrapper.jar` must be properly created/stored via Gradle tooling—never fabricate dummy files to run the example.

### 3.2. Root `settings.gradle`

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repro-demo'
include('core', 'app')
~~~

`include` registers subprojects; it **does not** create an `app → core` dependency. `pluginManagement.repositories` serves external plugins, while `dependencyResolutionManagement.repositories` resolves library dependencies. In enterprise environments, use approved mirrors/repositories with proper authentication; repository order affects artifact sourcing.

### 3.3. Root `build.gradle`

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
~~~

`apply false` pins the selected plugin versions at the root without **applying the Spring Boot plugin to root or core**. When `app` applies the Boot plugin, Gradle creates `bootJar`; `core` still produces a plain library `jar`. Plugin versions must be managed/verified separately, because `lockAllConfigurations()` on a project **does not automatically lock every buildscript/plugin classpath**.

### 3.4. `core/build.gradle`: Library, Implementation, and Locking

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

`core` uses Commons Lang inside a method body and **does not expose Commons types in its public API**. Therefore `implementation` is the right choice with the Java Library plugin: consumer `app` does not need Commons on its compile API classpath just because `core` uses it internally, yet Commons **still propagates to `app`'s runtime graph**.

`lockAllConfigurations()` enables locking for all **resolvable configurations** of `core`. It does not immediately create a lockfile; you must run tasks with `--write-locks`.

### 3.5. `app/build.gradle`: Application and Locking

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

`implementation project(':core')` declares the actual project dependency. `io.spring.dependency-management` works with the Spring Boot plugin to manage starter/test library versions; the BOM neither replaces the **lockfile** nor adds Commons to the graph on its own.

Test-only dependencies are not packaged into a standard executable Boot JAR. `core` builds a library JAR, while `app`'s `bootJar` packages `core` and Commons Lang as nested runtime libraries according to graph resolution.

### 3.6. `core/src/main/java/com/example/core/LibraryMessage.java`

~~~java
package com.example.core;

import org.apache.commons.lang3.StringUtils;

public final class LibraryMessage {
    private LibraryMessage() {
    }

    public static String label() {
        return StringUtils.capitalize("locked");
    }
}
~~~

`StringUtils.capitalize("locked")` returns the Java String `"Locked"`. This module has no `main()` and is not a Spring Boot application. If Commons Lang were excluded from the runtime classpath, calling this method would throw `NoClassDefFoundError`.

### 3.7. `app/src/main/java/com/example/app/ReproApplication.java`

~~~java
package com.example.app;

import com.example.core.LibraryMessage;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReproApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
    }

    @GetMapping("/state")
    public String state() {
        return "dependency " + LibraryMessage.label();
    }
}
~~~

When running properly, `GET /state` returns the body `dependency Locked`: the request executes `app → core → Commons Lang`. This lets us verify the **packaged runtime** after locking and verifying dependencies.

### 3.8. JUnit 5/MockMvc Test

`app/src/test/java/com/example/app/ReproApplicationTest.java`:

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReproApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void stateUsesCoreAndCommonsLang() throws Exception {
        mvc.perform(get("/state"))
           .andExpect(status().isOk())
           .andExpect(content().string("dependency Locked"));
    }
}
~~~

This test uses MockMvc with the Spring test context; **it does not start an HTTP server on port 8080**. It proves the mapping and code path work on the **test runtime classpath**. You must also test `java -jar`, because the packaged runtime classpath can differ from the test classpath.

### 3.9. Wrapper Version and Java Toolchain

An illustrative value in `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
~~~

The Wrapper distribution version should be pinned alongside controlled wrapper binaries/scripts. When policy requires, verify the Gradle distribution SHA-256 and provenance. `java.toolchain` specifies Java 17, yet the machine/CI must still have a compatible JDK or valid provisioning setup. Dependency verification **does not** replace checking the Gradle distribution and JDK.

## 4. Enabling Dependency Locking with the Right Scope

### 4.1. What Does `lockAllConfigurations` Do?

Both build scripts above use:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Gradle enables locking on resolvable configurations belonging to **that project**. Unresolvable configurations do not become resolvable. A lockfile records selected versions for configurations that were actually resolved.

If you only want to lock a single configuration, you can use (an alternative, not needed when `lockAllConfigurations` is already set):

~~~groovy
configurations {
    runtimeClasspath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

In multi-module projects, never assume locking only the root project is enough: `core` and `app` maintain separate dependency graphs/configurations.

### 4.2. Generating Lockfiles for the First Time

From the project root, after confirming trusted build scripts and repositories:

~~~bash
./gradlew --version
./gradlew projects

# Resolve configurations in each subproject and write lock state
./gradlew :core:dependencies :app:dependencies --write-locks

# Run the real build/tests, also writing lock states triggered
# by configurations resolved by tasks or plugins.
./gradlew :app:build --write-locks
~~~

`--write-locks` only writes state for **configurations that were resolved** during the invocation. In a Gradle multi-project build, `./gradlew dependencies --write-locks` may run only the **root project** task, failing to cover `app`/`core`. Therefore, the example passes explicit project-scoped tasks.

Running `:app:build` can trigger extra resolutions via compile/test/`bootJar` tasks, helping verify coverage. Even then, unused custom configurations are not automatically locked. Inspect your project's actual plugins/tasks.

### 4.3. Generated Files and Their Meaning

Typically you get:

~~~text
core/gradle.lockfile
app/gradle.lockfile
~~~

A **format illustration** of a lockfile—not content to copy-paste:

~~~text
# This is a Gradle generated file for dependency locking.
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
empty=annotationProcessor
~~~

This snippet simply demonstrates the `group:name:version=configuration1,configuration2` syntax. Actual lockfiles for **core** and **app** can list different configurations: `core` uses Commons on compile/runtime; `app` may see it only on runtime because Gradle `java-library` separates `api` and `implementation`. The Spring Boot BOM/constraints can also cause the selected version to differ from requested `3.14.0`. Read the **actual files Gradle generated** rather than writing assertions from the example.

### 4.4. Why Must Lockfiles Be Committed?

A lockfile is a **reviewed input** of the project. When the entire team and CI check out the same commit, Gradle knows which versions were approved. If CI ran `--write-locks` every time, CI would overwrite state and destroy drift signals.

Commit lockfiles into Git alongside build scripts. Do not put them in `.gitignore` or treat them as caches. Only store lock state for the required projects/configurations, and never copy lockfiles from another repository.

## 5. Enabling STRICT Mode Once a Baseline Exists

Gradle offers `LockMode.STRICT`. When a configuration has locking enabled yet **has no lock state**, strict mode fails instead of letting resolution proceed unlocked.

After generating, inspecting, and committing lockfiles, update the locking block in both **core and app** to:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
~~~

Run:

~~~bash
# Do not rewrite lock state during normal builds
./gradlew :core:build :app:build

# Inspect app's selected graph
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath --dependency commons-lang3
~~~

If strict mode reports missing lock state for a configuration, identify which plugin/task created that configuration, whether it should be locked, and generate its state through a reviewed workflow. **Never** fix it by removing strict mode in CI and releasing anyway.

### 5.1. When the Build Script Changes a Version While the Lockfile Keeps the Old Version

Suppose you edit the Commons Lang declaration to another release version **without updating the lockfile**. Gradle may keep the locked selected version or fail due to unsatisfiable constraints; do not guess an exact error message without running it. Do the right thing:

1. Use `dependencyInsight` and the dependency graph to analyze requested vs. selected versions.
2. Decide whether you genuinely want the upgrade.
3. If yes, update the lock state intentionally.
4. Review transitive versions that changed.
5. Rerun tests, packaging, and executable smoke tests.
6. Commit changes in a PR with the upgrade rationale.

### 5.2. Locking Does Not Mean “One Version per Dependency Across All Configurations”

Gradle resolves each configuration individually: `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, and plugin-created configurations. A module can resolve to different versions depending on constraints/context. Lockfiles store selected versions **per configuration**, not as a single global number.

If you add a new integration-test source set/configuration, check whether it has locking enabled and lock state generated, especially with STRICT enabled.

## 6. Updating Lock State in a Controlled Way

### 6.1. `--write-locks`: Rewriting Resolved State

When planning a set of dependency upgrades:

~~~bash
./gradlew :core:dependencies :app:dependencies --write-locks
./gradlew :app:build --write-locks
~~~

Then review the diff:

~~~bash
git diff -- core/gradle.lockfile app/gradle.lockfile
~~~

`--write-locks` can rewrite lock state for every resolved configuration; therefore **never include it in routine CI checks**. Use it on an upgrade branch, followed by testing, security review, and commit.

### 6.2. `--update-locks`: Updating Specific Modules

To target resolution for a specific dependency:

~~~bash
./gradlew :core:dependencies :app:dependencies \
  --update-locks org.apache.commons:commons-lang3
~~~

`--update-locks` accepts `group:name` module notation (comma-separated for multiple modules). It keeps the remaining lock state as input while allowing target modules to re-select against **current requested constraints and repositories**, updating affected state.

**It does not automatically upgrade everything to latest:** if the version declaration remains pinned to `3.14.0` with no other constraints, this command will not jump to a newer version. Update the declaration/BOM/version catalog **first**, then update locks. If upgrading Commons affects transitives, review the entire lockfile diff.

### 6.3. Version Catalogs/BOMs Do Not Replace Locking

- `gradle/libs.versions.toml` (if used) centralizes aliases and requested versions.
- Spring Boot BOM/platforms manage version constraints for dependencies in the graph.
- `gradle.lockfile` records actual selected versions **after resolution**.

An alias does not add a dependency by itself; a BOM does not freeze the full graph of every configuration. Thus projects with catalogs/BOMs still benefit from locking.

### 6.4. Avoiding Changing Dependencies in Releases

Do not treat `org.example:some-lib:1.0-SNAPSHOT` as immutable merely because it appears in a lockfile. For overwritable versions, enforce publication policies, artifact immutability, build IDs/digests, or dedicated provenance. Locking excels at stabilizing dynamic **version selection**, yet **cannot lock contents under the same coordinate**.

## 7. Dependency Verification: `verification-metadata.xml` and Trust Model

Gradle can verify JAR/ZIP, POM, Gradle Module Metadata, plugin artifacts, and other external artifacts processed by Gradle dependency resolution. Configuration lives at:

```text
gradle/verification-metadata.xml
```

This file applies to the **entire build**, including subprojects and plugin artifacts handled by Gradle verification rules. For included builds, Gradle shares verification policy across the invocation; do not assume an included build is completely isolated from the caller build's trust metadata.

**Important limitation:** verification does not treat **locally built source/`core.jar`** as a downloaded external artifact. Nor does it prove a library is free of CVEs, license issues, or malicious code if the baseline digest was poisoned from the start.

### 7.1. Generating a SHA-256 Baseline

After verifying repositories and resolved dependencies are trustworthy, run from root:

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build
~~~

Gradle creates or updates `gradle/verification-metadata.xml`. This flag resolves **resolvable configurations** to collect artifacts rather than only a single task's dependencies. However, downloads outside Gradle's dependency engine or artifacts used only in separate workflows still require coverage checks.

**Warning:** bootstrapping trusts the artifacts the repository serves **at that moment**. If a repository/mirror was already tampered with, generated checksums will match the compromised file. Learners must inspect coordinates, origins, hashes, and critical dependencies before accepting the XML.

### 7.2. Structure of Verification Metadata

The Gradle-generated file typically contains:

- `<configuration>`: policy for verifying metadata and signatures.
- `<components>`: module coordinates.
- `<component group="..." name="..." version="...">`: specific dependency.
- `<artifact name="...">`: JAR/POM/metadata files of the module.
- `<sha256 value="..."/>`: actual recorded SHA-256 digest.
- `<trusted-keys>` or `<pgp>` when signatures are used.

A **structural illustration**, not a usable complete XML file:

~~~xml
<components>
    <component group="org.apache.commons" name="commons-lang3" version="3.14.0">
        <artifact name="commons-lang3-3.14.0.jar">
            <!-- SHA-256 must be generated from the real artifact and reviewed. -->
        </artifact>
    </component>
</components>
~~~

Never fabricate a 64-character digest just to make a “runnable” example: checksums/signatures are trust data, not arbitrary placeholders. Never copy another project's `verification-metadata.xml`, because the file must match the **artifacts and repository policies of your build**.

### 7.3. When Is Verification Active?

Once an effective verification metadata file exists at root, Gradle enforces its rules to verify artifacts. **Creating an empty or minimal XML file** lacking digests for downloaded dependencies can immediately fail the build due to missing verification metadata.

After bootstrapping/review, build normally:

~~~bash
./gradlew :core:build :app:build
~~~

If an artifact lacks the required checksum, Gradle reports missing metadata. If bytes differ from the expected digest, it fails with a checksum mismatch. Those two cases **are not handled identically**.

### 7.4. Verification Modes: strict, lenient, off

| Mode | Meaning | Rule |
| --- | --- | --- |
| `strict` | Fails on any verification violation. | **Default and recommended for CI/releases.** |
| `lenient` | Logs errors but continues the build. | Use only for controlled temporary investigation. |
| `off` | Disables checks. | Never use as a workaround to ship past a checksum mismatch. |

**Diagnostic-only** example:

~~~bash
./gradlew --dependency-verification lenient :app:build
~~~

Never claim a build is “secure” when run in lenient/off mode. For detailed CI diagnostics, `gradle.properties` can set:

~~~properties
org.gradle.dependency.verification.console=verbose
~~~

This only adjusts reporting verbosity; it **neither weakens nor strengthens** trust rules.

## 8. SHA-256 and PGP Signatures: How Should They Be Used?

### 8.1. SHA-256 Verifies Integrity

SHA-256 computes a digest from an artifact's bytes. Gradle compares each artifact against its recorded expected digest. A file with altered bytes yields a different digest with overwhelming probability, causing Gradle to report a violation.

**However:** a checksum generated from an untrusted artifact becomes a “wrong baseline.” Verify the publishing source, repository, artifact write permissions, critical coordinates, and PR changes.

Do not rely on MD5/SHA-1 as primary security checksums in modern builds due to collision-resistance weaknesses; prefer SHA-256/SHA-512.

### 8.2. PGP Verifies Signer/Provenance

A PGP signature verifies that an artifact was signed by a key whose fingerprint is trusted. Verify:

- Is the `.asc` signature available and valid?
- Does the public key fingerprint match the publisher verified via an independent channel?
- Has the key been revoked, rotated, or compromised?
- Do unsigned artifacts have reviewed checksum fallbacks?

You can also bootstrap PGP with:

~~~bash
./gradlew --write-verification-metadata sha256,pgp \
  :core:dependencies :app:dependencies :app:build
~~~

When using a PGP keyring, store the **public keyring** per Gradle guidance if required by policy, e.g., `gradle/verification-keyring.keys`. **Never** commit private signing keys. Automatically bootstrapping signatures/keys does not replace a reviewer deciding whether the signer is genuinely trustworthy.

### 8.3. Verification Is Not an SCA/CVE Scan

An old library version with a CVE can still have a completely valid checksum. Therefore Gradle verification protects the supply chain **within its configured scope**, whereas vulnerability analysis, license compliance, SBOMs, and patch management remain separate gates.

## 9. Updating Verification Metadata Properly

When the dependency graph changes (adding a starter, upgrading Spring Boot, upgrading a plugin or transitive library), new artifacts or metadata may be absent from the committed XML.

Workflow:

1. **Verify why the new dependency appeared.** Read the PR's build scripts, dependency report, source repository, and publisher.
2. **Distinguish missing metadata from an incorrect checksum.** Missing is normal during planned updates; mismatch demands investigation.
3. **Only after verifying the source**, rerun `--write-verification-metadata sha256` or options matching your signature policy.
4. **Inspect the diff** of `gradle/verification-metadata.xml`: new components, JAR/POM artifacts, digests, signing keys.
5. Cross-check the **lockfile diff** to see how selected versions/configurations changed.
6. Rerun the build **without verification-writing flags**, checking JUnit/packaging/runtime.
7. Commit declarations + lockfiles + verification metadata in the same PR with reviewer approval per policy.

Illustrative update commands:

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build

git diff -- gradle/verification-metadata.xml \
            core/gradle.lockfile app/gradle.lockfile

# Normal verification build after reviewing state
./gradlew :app:build
~~~

**Never** run bootstrap to accept a new checksum right after a **checksum mismatch**. If file bytes differ from the expected digest, a repository may have been rewritten, a mirror may be serving inconsistent files, a cache may be corrupted, or tampering may have occurred. Investigate and document the trust decision before updating the baseline.

### 9.1. Why Does the XML File Grow Over Time?

Gradle verification metadata bootstrapping is typically **incremental**: it adds new entries without automatically knowing an older artifact is no longer used in any configuration/feature. Hence the XML may accumulate stale entries. Clean up deliberately when justified, rather than wiping the whole file just to shrink a diff.

### 9.2. Do Not Abuse Trusted-Artifacts Wildcards

Gradle allows declaring trusted artifact exceptions when intentional. A rule trusting an entire group/artifact or all sources JARs weakens security gate coverage. If an exception is unavoidable, scope it tightly by file/group/reason under policy with a review expiration; never use broad wildcards just to turn CI green.

## 10. End-to-End Workflow Combining Locking and Verification

### Step A — Understand the Runtime Graph

~~~bash
./gradlew --version
./gradlew projects
./gradlew :core:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath --dependency commons-lang3
~~~

App `runtimeClasspath` must contain project `:core` and transitive Commons Lang, along with Spring Boot runtime dependencies. Do not treat `app`'s `compileClasspath` as evidence Commons Lang is unnecessary: Java Library `implementation` hides it from consumer compilation while still shipping it to runtime.

### Step B — Enable Locking and Generate Lock State

Add `dependencyLocking { lockAllConfigurations() }` to project build scripts, then run:

~~~bash
./gradlew :core:dependencies :app:dependencies --write-locks
./gradlew :app:build --write-locks
~~~

Review `core/gradle.lockfile` and `app/gradle.lockfile`. Once state is complete, enable `LockMode.STRICT` and run a normal build.

### Step C — Generate Verification Metadata from Trusted Repositories

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build
~~~

Review the XML, repository/publisher metadata, and hashes/keys. Commit the baseline.

### Step D — CI Verifies Only, Never Rewrites Baselines

~~~bash
./gradlew --no-daemon :core:clean :app:clean :app:build
~~~

**Never add** `--write-locks` or `--write-verification-metadata` to regular CI commands. If CI can auto-refresh baselines, unexpected dependency graph changes could be accepted without review.

### Step E — Inspect the Artifact and Runtime Behavior

~~~bash
./gradlew :app:bootJar

# Inspect the exact executable JAR; expected example filename
jar tf app/build/libs/app-0.1.0.jar

# Terminal 1: start the packaged app
java -jar app/build/libs/app-0.1.0.jar --server.port=18085
~~~

In a second terminal, once the server is ready:

~~~bash
curl -i http://localhost:18085/state
~~~

Expect **HTTP 200** with exact body `dependency Locked`.

Inside the executable archive, expect:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/app/ReproApplication.class
BOOT-INF/lib/core-0.1.0.jar
BOOT-INF/lib/commons-lang3-<selected-version>.jar
BOOT-INF/lib/spring-boot-<selected-version>.jar
...
~~~

`<selected-version>` is a placeholder for reading, not a literal filename to pass to the shell. Check actual versions with `jar tf`/`dependencyInsight`. Never mistakenly deploy `*-plain.jar` created by Gradle's `jar` task.

**Reason for the runtime step:** locking/verification do not guarantee Spring Boot `bootJar` bundled all required libraries. If test classpath has Commons Lang while packaged runtime lacks it, MockMvc tests can pass while `java -jar` fails. Only running the actual artifact catches that discrepancy.

## 11. A QA Table for Code Review and CI

| Evidence | Meaning | What cannot be concluded |
| --- | --- | --- |
| `build.gradle` and `settings.gradle` | Requested graph, plugin/registry policy. | Final selected versions or artifact integrity. |
| `core/gradle.lockfile`/`app/gradle.lockfile` | Approved selected versions and locked configurations. | Authentic artifact bytes or absence of CVEs. |
| `gradle/verification-metadata.xml` | Artifact checksums/PGP trust policy. | Whether runtime dependencies are bundled into the JAR. |
| `:app:dependencies --configuration runtimeClasspath` | Runtime graph chosen by resolution. | Whether the JAR binary actually contains the right files. |
| `:app:dependencyInsight` | Why a version was selected; constraints/conflicts. | Checksum/artifact provenance. |
| `jar tf app.jar` | Actual entries inside the executable JAR. | Whether endpoints/jobs actually execute properly. |
| JUnit/MockMvc report | Test assertions passed on test runtime. | Whether packaged runtime also passes. |
| `java -jar` and HTTP smoke | Executable JAR works in the test environment. | Comprehensive security/compliance/production readiness. |

### 11.1. Files to Commit in the Example

~~~text
settings.gradle
build.gradle
core/build.gradle
app/build.gradle
core/gradle.lockfile
app/gradle.lockfile
gradle/verification-metadata.xml
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
gradlew
gradlew.bat
~~~

Java source, test, and resource files must also be committed. **Never commit the entire `.gradle/caches`** as a substitute for lockfiles/verification XML; caches are environment data that can be rebuilt from trusted sources per policy.

### 11.2. When Upgrading a Dependency

A version upgrade PR should include:

1. Diff of requested versions in build scripts/version catalog.
2. Diff of **selected versions** in lockfiles (only affected files/configurations).
3. Diff of checksum/signature metadata after reviewers confirm repository/publisher trustworthiness.
4. Test reports for `core`/`app` and relevant integration tests.
5. Archive inspection and packaged smoke test.
6. Compatibility/CVE/license notes, if impacted.
7. Artifact/provenance identification per release policy.

A PR changing only source code should not automatically rerun metadata bootstrapping; baseline-writing commands are used only with justification.

## 12. Common Errors and Resolutions

| Symptom | Likely cause | Evidence-based resolution |
| --- | --- | --- |
| No `app/gradle.lockfile` after running lock command. | Locking not enabled in `app`, ran `dependencies` only at root, or configuration unresolved. | Check `app/build.gradle` and invoke `:app:dependencies --write-locks`; inspect actual output. |
| Strict mode reports missing lock state. | Configuration marked locked yet lacks state. | Generate baseline via workflow, review, and commit; do not unconditionally disable strict mode. |
| Changed version yet still uses old version. | Lock state/BOM/constraints retain the selected version. | Run `dependencyInsight`, update declaration intentionally, then `--update-locks`. |
| New starter changes many locks at once. | BOM/transitive graph/selected versions shifted. | Review full dependency report and diff; test compatibility before committing. |
| Lockfile has Commons Lang yet `bootJar` lacks it. | Task/classpath/exclusions differ from runtime graph. | Check `runtimeClasspath` and `bootJar.classpath`, not just the lockfile. |
| Gradle plugin version changed, project lockfile unchanged. | Plugin/buildscript classpath is outside project lock state. | Manage plugin versions and verification; consider buildscript locking for legacy plugins. |
| Build fails with “checksum is missing.” | New artifact lacks approved metadata. | Verify source, update verification metadata with review. |
| Build fails with “checksum expected differs from actual.” | Bytes deviate from trust baseline—possible repo rewrite/cache/tampering. | Halt release and investigate; never blindly rebootstrap. |
| PGP key not trusted. | New key/unverified signer. | Verify fingerprint via independent publisher channel, then update policy. |
| Invalid PGP signature. | Artifact/signature/key mismatch. | Treat as integrity incident; never use lenient/off to release. |
| Local passes while CI fails verification. | Repository/mirror/plugin version/cache mismatch. | Compare exact coordinates, repo order, Gradle Wrapper, metadata, and logs. |
| `--offline` fails despite complete lockfile. | Lockfile **does not store JAR bytes**; offline cache lacks artifact. | Populate trusted cache or mirror; do not treat locks as binary storage. |
| `-SNAPSHOT` keeps version yet bytes differ. | Changing dependency; locking does not freeze content. | Use immutable releases and repository/provenance policies. |
| Different Gradle Wrapper/JDK produces different output. | Locking/verification do not lock the environment. | Pin Wrapper/JDK/toolchain and reproducible archive settings if bit-for-bit is needed. |
| Verification metadata XML grows huge with old entries. | Incremental bootstrapping does not auto-prune. | Perform intentional reviewed cleanup; do not wipe all metadata. |
| Runtime throws `NoClassDefFoundError`. | Missing transitive dependency in packaged runtime, wrong scope/exclusion. | Compare graph and `BOOT-INF/lib`; fix dependency config, do not alter hashes as a workaround. |
| Tests report `NO-SOURCE` despite build success. | Wrong test source path/Gradle task wiring. | Inspect `src/test/java`, JUnit, `useJUnitPlatform`, and report. |

### 12.1. Separating Failure Layers

1. **Declaration:** what does the build script request?
2. **Resolution:** which versions and dependency graph does Gradle select?
3. **Locking:** does lock state match configurations and selected versions?
4. **Verification:** do artifact bytes/signatures match trust metadata?
5. **Packaging:** does `bootJar` contain the right nested dependencies?
6. **Runtime:** did the Java app call `core`/Commons Lang successfully?
7. **Security:** does the artifact satisfy CVE/license/trust policies?

Each layer needs its own evidence. Never “fix” a checksum mismatch by changing the HTTP port, or fix a missing runtime JAR by disabling verification.

## 13. Controlled Deviation Experiments

### 13.1. Experimenting with Changing Selected Versions

On a practice branch, edit the requested Commons Lang version. Do not run `--write-locks` immediately. Run dependency reports and build to observe how lock state affects resolution; when ready to accept the upgrade, run `--update-locks org.apache.commons:commons-lang3`, review the diff, and rerun tests. If the new version introduces unverified artifacts, inspect metadata/publisher before updating the XML.

### 13.2. Experimenting with Adding an Unchecksummed Artifact

On a separate branch, add a valid, source-checked dependency not yet present in the XML. In strict mode you should encounter missing verification metadata. Inspect the report, note which artifact is missing, and add the digest only after review. Never use `--dependency-verification off` as a shortcut.

### 13.3. Checksum Mismatch Scenario

You do not need to corrupt a cached JAR to simulate an attack. Read a sample “expected SHA-256 differs from actual” log and answer:

- Which coordinate and file are affected?
- Which commit/reviewer approved the baseline digest?
- Which repository/mirror served the current bytes?
- Are there trusted checksums or signatures from the publisher?
- Do you need to switch mirrors, check caches, or report a security incident?
- Who approves a new trust baseline, and with what evidence?

**Rule:** mismatches must be investigated before making any trust policy change.

### 13.4. Builds with Identical Dependencies Yet Different Output JAR Bytes

Identical lockfiles/verification metadata do not automatically make binary builds **bit-for-bit reproducible**. JDK toolchain, compiler options, generated timestamps, archive order, file timestamps, locale/time zone, and task inputs can affect outputs. For strict requirements, configure reproducible archives, deterministic generation, and compare file hashes across controlled builds.

## 14. Multi-Module and Included Builds

In the demo, `core` and `app` are **subprojects** of the same build. Each project maintains a lockfile for locked resolvable configurations. Root verification metadata acts as the build-wide policy, covering supported external artifacts/plugins.

If a repository uses `build-logic` as an **included build** providing convention plugins:

- Do not assume `core/gradle.lockfile` of the main build locks the `build-logic` classpath.
- Configure separate dependency locking in Gradle settings/included build if `build-logic` has external runtime/plugin dependencies.
- Dependency verification spans the entire build invocation per Gradle docs, so plugin/`build-logic` artifacts may require updating root verification metadata.
- Do not take the shortcut of “trusting all of com.mycompany” if internal artifact repositories are also at risk of overwrites/tampering; scope trust per policy.
- Use a Gradle version compatible with the included build's scripts.

An internal project dependency `project(':core')` is built from source within the same build, not an external artifact with a SHA-256 in verification metadata under the same mechanism. When publishing `core` to an external registry, consumers will need to verify the **published artifact** under their own trust policy.

## 15. CI Workflows and Upgrade PRs

For routine CI, commands should **verify only**, never regenerate trust/lock files:

~~~bash
# CI checkout already contains reviewed lockfiles and verification-metadata.xml
./gradlew --no-daemon --version
./gradlew --no-daemon :core:clean :app:clean :app:build
./gradlew --no-daemon :app:dependencies --configuration runtimeClasspath
jar tf app/build/libs/app-0.1.0.jar
~~~

If the pipeline adds a `java -jar` smoke test, launch the HTTP server with proper lifecycle/timeout handling, invoke `GET /state`, then stop the process. Never run `java -jar` in the foreground in CI expecting a web server to exit on its own. Passing classpath tests/`BUILD SUCCESSFUL` alone does not prove the packaged JAR runs.

In dependency-upgrade PRs, reviewers should have **four diffs/pieces of evidence**: requested versions, resolved lock state, verification metadata/key trust, and test/packaged runtime results. Never accept auto-updated lockfiles/XML without explanation.

## 16. Practice Exercises and Completion Criteria

### Exercise A — Create Lock State

1. Set up all Gradle/Java files from Section 3 with a suitable Wrapper.
2. Run `./gradlew :core:dependencies :app:dependencies --write-locks`.
3. Inspect `core/gradle.lockfile` and `app/gradle.lockfile`, comparing configurations.
4. Run `./gradlew :app:build --write-locks` to cover task-induced resolutions.
5. Review diffs, then enable `LockMode.STRICT` once state is complete.
6. Rerun `./gradlew :app:build` **without lock-writing flags**.
7. Explain cases where selected versions differ from requested versions due to graph/BOM conflicts.

### Exercise B — Create Verification Metadata

1. Verify repositories, plugin versions, and trusted dependency sources.
2. Run `./gradlew --write-verification-metadata sha256 :core:dependencies :app:dependencies :app:build`.
3. Open `gradle/verification-metadata.xml`; locate entries for Commons Lang and Spring library/plugin artifacts.
4. Explain how downloaded file hashes differ from lockfile versions.
5. Review the XML and commit it alongside lockfiles.
6. Run a normal strict build and observe reporting.
7. If adding PGP, distinguish trusted signers from checksum fallbacks.

### Exercise C — Upgrade a Dependency Properly

1. Change the requested Commons Lang version in `core/build.gradle` on a separate branch.
2. Observe resolution/locking behavior before allowing the update.
3. Run `--update-locks org.apache.commons:commons-lang3`, inspect selected versions and diff.
4. Verify the new artifact and update the XML via controlled bootstrapping.
5. Run tests, packaged JAR smoke tests, and review compatibility/security.
6. Revert if purely an experiment; never release unreviewed artifacts.

### Exercise D — Verify the Product

1. Run `./gradlew :app:bootJar`.
2. Inspect `jar tf app/build/libs/app-0.1.0.jar` for the core JAR, Commons Lang JAR, and Boot runtime libraries in `BOOT-INF/lib`.
3. Run `java -jar app/build/libs/app-0.1.0.jar --server.port=18085`.
4. Call `curl -i http://localhost:18085/state`, expecting HTTP 200 and body `dependency Locked`.
5. Record test reports, exact artifact path, reviewed lockfiles, and verification metadata.

### Checklist

- [ ] Distinguish dependency locking from dependency verification.
- [ ] Understand requested version, selected version, and artifact bytes are three distinct concepts.
- [ ] Know `lockAllConfigurations()` must be paired with controlled lock-state generation.
- [ ] Have lockfiles in the right subprojects, not just root tasks.
- [ ] Know when to enable `LockMode.STRICT` and why a baseline is needed first.
- [ ] Know `--write-locks` vs `--update-locks`, and why neither belongs in routine CI.
- [ ] Explain why dynamic versions and changing/`-SNAPSHOT` are not the same.
- [ ] Generate/review `gradle/verification-metadata.xml` with SHA-256.
- [ ] Never blindly trust a checksum mismatch or use lenient/off to release.
- [ ] State the role of PGP signatures/public keys and limits of unreviewed bootstrapping.
- [ ] Understand BOMs/version catalogs do not replace lockfiles.
- [ ] Know Gradle plugin artifacts/Wrapper/JDK must be managed outside project dependency locks.
- [ ] Compare `runtimeClasspath` against `BOOT-INF/lib`; confirm `core` and transitive Commons Lang are present.
- [ ] Have JUnit/MockMvc reports and packaged `java -jar` smoke tests.
- [ ] Know verification does not replace CVE scanning/SBOMs, testing, or deterministic packaging.

**Completion criteria:** a repository with a controlled Gradle Wrapper, lockfiles for `core`/`app`, reviewed root verification metadata, normal builds running without rewriting baselines, runtime graph and Boot executable JAR containing all dependencies, passing JUnit tests, and `GET /state` on the real JAR returning `dependency Locked`. If lacking JDK, repository access, or unexecuted smoke tests, explicitly list unverified items rather than marking PASS based on expectation.

## Official Documentation

- [Gradle 8.10.2 — Locking Dependency Versions](https://docs.gradle.org/8.10.2/userguide/dependency_locking.html)
- [Gradle 8.10.2 — Dependency Verification](https://docs.gradle.org/8.10.2/userguide/dependency_verification.html)
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot 3.3 — Gradle Plugin Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.3 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)

**Remember:** lockfiles prevent silent shifts in **resolved versions**, while verification metadata confirms **artifact bytes/PGP signatures match your trust baseline**. Both require workflows for generation, review, committing, and CI verification; final validation still requires checking the actual executable JAR and runtime behavior.