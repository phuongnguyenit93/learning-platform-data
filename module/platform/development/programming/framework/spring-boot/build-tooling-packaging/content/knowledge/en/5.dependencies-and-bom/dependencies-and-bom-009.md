# Overriding Managed Versions and Evaluating Compatibility in Spring Boot

## 1. Objectives and Real-World Problem

Spring Boot provides the `spring-boot-dependencies` **Bill of Materials (BOM)** to manage versions across many libraries, ensuring components are used together in combinations tested for each Spring Boot release. In a typical project, you declare dependencies by `groupId:artifactId` and let the BOM supply the version.

However, sometimes you need to **override** a BOM-managed version—for example, due to a security vulnerability with an available patch, a compatibility issue with an external system, or a needed new library feature. Doing so alters part of the version set Spring Boot tested, so it must be accompanied by **compatibility evaluation and test evidence**.

After this lesson, you will be able to:

1. Distinguish the **BOM-managed version**, **requested version** in configuration, and **actual selected version** in the dependency graph.
2. Identify your project's dependency management style: Maven inheriting `spring-boot-starter-parent`, Maven importing the BOM, Gradle using `io.spring.dependency-management`, or Gradle native `platform()`.
3. Override properly in each setup, control scope, and avoid bumping all related libraries arbitrarily.
4. Use the dependency tree, `dependencyInsight`, effective POM, and build/test results to verify the actual version.
5. Decide whether to accept or revert an override based on compatibility, security, blast radius, and Spring Boot upgrade options.

**Example convention:** version numbers in snippets only **illustrate syntax**, and are not claims that those versions are security patches or compatible with every Spring Boot release. In real work, use project-approved versions and check documentation for your exact Spring Boot release.

## 2. What Does a BOM Manage, and What Does It Not?

A Maven BOM is a POM with `<dependencyManagement>`, aggregating library coordinates and recommended/managed versions. The Spring Boot BOM manages many components such as Spring Framework, Jackson, logging, HTTP clients, JDBC drivers, and other library suites (the list varies by Spring Boot release).

Example of *declaring usage* of an already-managed library:

~~~xml
<!-- pom.xml: Maven using Spring Boot Parent or importing BOM -->
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

~~~groovy
// build.gradle: Spring Boot dependency management already configured
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Neither declaration specifies the starter's version: version management is configured elsewhere. **A BOM does not automatically add every library** to the classpath. A dependency appears only if declared directly or pulled in *transitively* by another dependency.

Distinguish three concepts:

| Concept | Meaning | Evidence |
| --- | --- | --- |
| **Managed version** | Version specified by a BOM or `dependencyManagement` when a module appears | BOM, effective POM, dependency management report |
| **Requested version** | Version/constraint asked for by a direct or indirect dependency | `pom.xml`, `build.gradle[.kts]`, dependency tree |
| **Resolved/selected version** | Final version picked by the build tool per configuration/classpath | Maven `dependency:tree`; Gradle `dependencies`, `dependencyInsight` |

**A BOM is not a lockfile** and does not replace dependency graph verification. Maven and Gradle have different conflict resolution rules; the same BOM can yield different results if projects declare different constraints.

**Build plugin configuration is also a separate concern:** a BOM primarily manages **library dependencies**. Do not assume adding an override to the dependency BOM automatically upgrades the Maven Compiler Plugin, Gradle plugins, or the Spring Boot plugin itself.

## 3. When Should You Override, and When Should You Avoid It?

Reasons that are typically acceptable when backed by evidence:

- An advisory/CVE directly affects a version **actually used by the project**, an upstream patch exists, and your current Spring Boot release has not updated yet.
- A bug has been confirmed by library maintainers and a minimal patch fixes it, backed by an issue/release note.
- Compatibility with an external system's protocol, server, driver, or API requires it, and the new version set has been verified.
- A required feature exists in a newer version, and the team accepts the regression testing and operational cost.

Questions you must answer **before editing**:

1. Why not upgrade to a **Spring Boot patch/minor release** containing the dependency fix? Upgrading Spring Boot along official support paths preserves inter-library coordination better.
2. Is that dependency **actually used** or merely present in a report? Is it on `compileClasspath`, `runtimeClasspath`, test classpath, or build plugin classpath?
3. Is overriding a single artifact safe, or does it belong to a **family that must move together** (e.g., Jackson modules, Netty, Spring Framework, Spring Security, Spring Data)?
4. Does the new version change **minimum Java version**, API/ABI, package names, configuration, transitive dependencies, server/database requirements, or license?
5. Is there a rollback plan and a milestone to remove the override once the official BOM is upgraded?

Avoid overriding solely to "clear dependency warnings," chase the latest version without need, or mask a core version error without finding its root cause. **Never equate "build succeeded" with "runtime compatible."**

## 4. Establish a Baseline Before Changing Versions

Before editing configuration, record: Spring Boot version, build tool type, Wrapper version, affected `group:artifact` coordinates, **selected version before the change**, and reason for changing. Use the repository's Wrapper so results are reproducible.

### 4.1 Maven

On Linux/macOS:

~~~bash
./mvnw --version
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd dependency:tree -Dincludes=org.slf4j:slf4j-api
.\mvnw.cmd help:effective-pom -Doutput=effective-pom.xml
~~~

`dependency:tree` shows which branch brings in the dependency and the currently selected version; `effective-pom.xml` shows configuration merged from parent, profiles, and dependency management. **The `effective-pom.xml` file is strictly inspection output**; it does not replace source `pom.xml` and should not be committed by accident.

If the library is not yet in the dependency tree, `dependencyManagement` only governs its version **when it appears**, rather than making it appear. In multi-module Maven builds, run in the application module or use `-pl` appropriately, and account for profiles actually active during builds.

### 4.2 Gradle

On Linux/macOS:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
~~~

`dependencyInsight` shows the selected version, dependency paths requesting it, and **selection reasons** (e.g., constraint/conflict resolution/forced). `runtimeClasspath` is suited for investigating libraries present when running; for compile errors also inspect `compileClasspath`, and for test errors inspect `testRuntimeClasspath`. A multi-module project may require a module prefix such as `:app:dependencyInsight`.

**Read the output before concluding:** a version listed in the BOM is not guaranteed to be on the classpath; a version written in a build file is not guaranteed to be the final version chosen by Gradle.

## 5. Maven: Overriding When Inheriting Spring Boot Starter Parent

If `pom.xml` has `<parent>` set to `org.springframework.boot:spring-boot-starter-parent`, Spring Boot allows adjusting many managed versions via **BOM properties**. For example, if your release provides the `slf4j.version` property:

~~~xml
<!-- Property snippet inside <project> of pom.xml -->
<properties>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

This is a snippet inside a POM already inheriting Spring Boot Parent, **not a standalone POM**. Check the *Dependency Version Properties* appendix for your exact Spring Boot release to confirm the **exact property name**. Do not assume every artifact has a similarly named property. A property can govern **a group of modules/BOM** rather than a single JAR, so its blast radius must be re-verified with the dependency tree.

If you only want to override the version of a directly declared dependency, Maven also accepts an explicit `<version>`:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.16</version>
</dependency>
~~~

**Scope difference:** writing a version directly controls that dependency at its direct declaration; a BOM property can affect multiple managed dependencies. If a library only appears transitively, adding it as a direct dependency purely to force a version can make the POM confusing; consider `dependencyManagement` to govern its version when it appears.

When using Maven Spring Boot Parent, prefer **properties published by Spring Boot** for dependency groups that should stay synchronized. If an override lacks a matching property, declare an explicit management entry in the current POM and verify with effective POM and dependency tree.

## 6. Maven: Overriding When Only Importing the BOM (No Starter Parent)

A project with its own corporate parent typically imports `spring-boot-dependencies` as a BOM. In this case, **setting `slf4j.version` in the project POM does not automatically alter values already processed inside the imported BOM**. This is a crucial difference from Starter Parent inheritance.

To override a module, add an entry in the **project's own `<dependencyManagement>`** before the BOM import entry. The example below illustrates the structure (Spring Boot and SLF4J versions are sample numbers):

~~~xml
<!-- Excerpt from <dependencyManagement> of pom.xml -->
<dependencyManagement>
    <dependencies>
        <!-- Override declared in project, before BOM import -->
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Use the **exact BOM version applied to your project**, rather than treating `3.3.13` as universal across every Spring Boot project. An entry in `dependencyManagement` **does not pull `slf4j-api` into the application by itself**; if the app directly uses the library, still declare the dependency normally in `<dependencies>`.

When overriding an **entire release train**, you typically import the corresponding BOM before the Spring Boot BOM and verify every related artifact. For example, Spring Data has its own BOM; do not pick independent versions for individual Spring Data modules. Imported BOMs follow precedence rules when managing the same artifact; do not rely on intuition that "whichever BOM is newer wins." Read the effective POM and tree for every module under control.

### Maven Version Selection Rules

- For a dependency declared directly with `<version>`, the direct version applies to that dependency.
- `<dependencyManagement>` applies managed versions to dependencies lacking a version or appearing transitively, helping reduce conflicts across branches.
- If no version management intervenes, Maven typically chooses the **nearest definition** in the dependency tree; if two branches are at equal depth, the declaration appearing first usually wins.
- **The final merged configuration is the source of truth**, because parents, profiles, and imported BOMs can change outcomes. Always confirm with `dependency:tree` + `help:effective-pom`.

## 7. Gradle with `io.spring.dependency-management`: Adjusting Managed Version Properties

If a Gradle project applies both `org.springframework.boot` and `io.spring.dependency-management`, the Spring Boot plugin auto-imports the matching BOM. This mechanism supports overrides via **Gradle extra properties** when the Spring Boot BOM exposes a property.

In Groovy DSL `build.gradle`:

~~~groovy
// Placed in build.gradle with the corresponding plugins applied
ext['slf4j.version'] = '2.0.16'
~~~

In Kotlin DSL `build.gradle.kts`:

~~~kotlin
// Placed in build.gradle.kts with the corresponding plugins applied
extra["slf4j.version"] = "2.0.16"
~~~

These two snippets are **alternative syntaxes**. Setting the property must happen before dependency management resolves versions; place it near general build configuration and verify after reloading Gradle.

Verify:

~~~bash
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew clean build
~~~

If multiple SLF4J versions or related logging libraries already exist on the classpath, inspect the whole group rather than `slf4j-api` alone. Verify at runtime because mismatches between SLF4J API and provider/binding often surface only when starting the app.

**Warning:** `ext['slf4j.version']` / `extra["slf4j.version"]` is a feature of the Spring dependency-management plugin; **it has no equivalent effect** when using Gradle native `platform()` alone.

## 8. Gradle Native BOM: Distinguishing `platform`, Constraints, and `enforcedPlatform`

Gradle can import a BOM via `platform()` without `io.spring.dependency-management`. Example **snippet** for `build.gradle` with the Spring Boot plugin already applied:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

`platform()` brings BOM versions into the dependency graph as **constraints**. They act as recommendations/constraints for Gradle's version conflict resolver; **it does not guarantee every BOM version is always chosen** if another dependency requests a higher version or has a stronger constraint.

When a specific artifact needs a targeted decision, native Gradle should use a **dependency constraint with a clear rationale**, such as:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    constraints {
        implementation('org.slf4j:slf4j-api') {
            version {
                strictly '2.0.16'
            }
            because 'Compatibility decision verified for the application'
        }
    }
}
~~~

This requests a specific version **if that module is used in the corresponding configuration**. A constraint **does not add the module to the classpath by itself**. `strictly` can cause resolution to **fail** if incompatible strict requirements exist; in that case investigate the cause instead of blindly adding `force` to hide conflicts. If you only need a minimum version floor, an ordinary constraint or `require` may fit better, though Gradle may still choose a higher version. **Always read `dependencyInsight` to prove the final version.**

When using a native BOM, **do not assume** extra properties like `ext['slf4j.version']` alter versions inside the BOM's POM. Native Gradle processes metadata/constraints and does not re-interpolate Maven BOM properties for overrides.

### How Is `enforcedPlatform()` Different?

- `platform()`: BOM versions are constraints that can participate in conflict resolution with other versions.
- `enforcedPlatform()`: enforces platform versions more aggressively and can affect **even consumers' dependency graphs**, especially for libraries reused by other projects.
- `resolutionStrategy.force` and `eachDependency { useVersion(...) }`: strong resolution-level hooks that easily defeat declared constraints; typically a last resort with clear justification and thorough testing.

Do not switch the entire Spring Boot BOM to `enforcedPlatform` just to override one library; doing so locks down many unrelated versions. To keep management transparent, pick one **primary dependency management style** for the project instead of mixing the Spring plugin and native BOMs arbitrarily.

## 9. Why Can't You Just "Change One Version Number"?

### 9.1 Source, Binary, and Runtime Compatibility

A library may compile cleanly against current APIs yet throw `NoSuchMethodError`, `NoClassDefFoundError`, or `ClassCastException` at runtime if APIs/ABIs across JARs mismatch. Java bytecode must also match the production JVM: a library compiled for Java 21 will not run on Java 17 if class files require a newer bytecode version.

**Backward compatibility does not mean absolute compatibility:** semver helps estimate risk, yet minor/patch releases can still change behavior, default configurations, module names, or accompanying dependencies.

### 9.2 Related Library Ecosystems

| Group | Risk When Overriding a Single Artifact | Required Verification |
| --- | --- | --- |
| Spring Framework / Spring Security | Spring Boot auto-configuration may invoke specific APIs/behaviors; modules must stay synchronized | Version matrix, application context, security flows |
| Spring Data / Hibernate / JDBC | Dialects, entity mapping, transactions, and queries can change | Repository/service integration tests, migrations, real DB or testcontainers |
| Jackson | `jackson-databind`, `jackson-core`, `jackson-annotations`, or the Jackson BOM may need alignment | JSON serialize/deserialize, custom modules, HTTP payloads |
| Reactor / Netty / HTTP | Nonblocking APIs, SSL/TLS, event loops, transport, and native dependencies can change | WebClient/WebFlux integration tests, networking, load tests as needed |
| SLF4J / Logback | Mismatched logging API and provider cause warnings/runtime failures | App startup, log output, MDC, logging configuration |
| DB / Kafka / Redis drivers | Protocol compatibility with deployed servers | End-to-end integration tests against actual server versions |

If a release train publishes its own BOM, **upgrading the module suite via a compatible BOM** is usually safer than picking independent versions module by module.

### 9.3 Security and Operations

A security advisory does not automatically mean every application containing those coordinates is exploitable. Verify whether the artifact is actually on the runtime classpath, the affected version, reachable call paths, and mitigating configuration. Still, for serious risks, prioritize timely remediation via a **Spring Boot patch update, compatible BOM, or tested temporary override**.

When overriding, also track license changes, artifact provenance, signatures/checksums if required by organizational policy. A scanner report is only one signal; decisions must tie back to the artifact's **actual dependency graph**.

## 10. Controlled Change Workflow

Follow this cycle for **each proposed override**:

1. **Record baseline:** Boot version, JDK, Wrapper, current BOM, dependency tree, and selected version. For a CVE, save the advisory link and scope of impact.
2. **Choose strategy:** prefer updating to a Spring Boot release containing the fix; if not feasible yet, pick the override mechanism matching Maven Parent, Maven BOM import, Gradle dependency-management plugin, or Gradle native platform.
3. **Make the minimal edit:** one property, one managed entry, or one justified constraint. Do not change JDK, framework version, and dozens of libraries simultaneously.
4. **Re-resolve dependencies:** save the dependency tree/insight after the change; compare related artifacts across **runtime**, **compile**, and **test** classpaths. One version line in a build file is never enough.
5. **Verify the build:** run compile, unit tests, integration tests, and packaging using the Wrapper locally and in CI. Run on supported JDK and runtime environments.
6. **Verify behavior:** start the app, exercise flows touching that dependency, inspect logs, serialization, HTTP, persistence, security, or messaging as applicable.
7. **Review the release:** read changelogs, compatibility notes, breaking changes, and scanner/analyzer output. Check whether the new dependency pulls in different versions of other libraries.
8. **Document the decision:** rationale, old/new versions, tests run, results, approver/scope, and condition for removing the override.
9. **Define rollback criteria:** if runtime linkage errors, regressions, or incompatibilities surface, roll back to the verified BOM/version; do not blindly downgrade when an unmitigated security risk remains.
10. **Clean up overrides when no longer needed:** once an official Spring Boot BOM manages a suitable version, remove the temporary property/constraint/managed entry and verify the dependency graph again.

An easily reviewable decision record can go right into the PR:

| Field | Example Entry |
| --- | --- |
| Artifact | `org.slf4j:slf4j-api` |
| Old / new version | Taken from before/after dependency tree reports, not inferred from POM |
| Reason | Specific advisory or upstream issue |
| Override type | BOM property / Maven `dependencyManagement` / Gradle constraint |
| Verification scope | Direct modules, related transitives, runtime, and tests |
| Evidence | Wrapper commands executed and CI/integration test results |
| Review trigger | Next Spring Boot upgrade or upstream release with proper fix |

## 11. Sample Scenario: Needing a Newer Library Version for a Confirmed Bug

**Context:** `org.slf4j:slf4j-api` is brought in via starters and the Spring Boot BOM. The team confirmed a compatibility need and chose to test `2.0.16`. The version numbers below only simulate the workflow; **they do not imply this version fixes any specific CVE**.

### Before the Change

1. Run Maven `dependency:tree -Dincludes=org.slf4j:slf4j-api` or Gradle `dependencyInsight --dependency slf4j-api --configuration runtimeClasspath`.
2. Record the actual selected version and dependency paths bringing SLF4J into the application.
3. Identify the dependency management style rather than guessing from build file extensions.

### Apply the Matching Mechanism

- Maven inheriting Boot Parent: add `<slf4j.version>2.0.16</slf4j.version>` in `<properties>`, provided the BOM release defines that property.
- Maven importing Boot BOM: add a managed entry for `org.slf4j:slf4j-api` in the project POM before the BOM import, or manage the proper release train when synchronizing a whole group.
- Gradle with `io.spring.dependency-management`: `ext['slf4j.version'] = '2.0.16'` (Groovy) or `extra["slf4j.version"] = "2.0.16"` (Kotlin).
- Gradle native `platform()`: add an appropriate constraint and verify with `dependencyInsight`; do not use the Spring plugin's extra property.

### After the Change

Re-run the **exact same commands** to capture and compare the dependency tree. Confirm no other logging module drifted to an incompatible version. Build and run Spring Boot, verify logging actually works, watch for provider warnings, and exercise primary business flows. If the original issue persists or incompatibilities appear, **roll back** and pick another approach.

**Expected outcome:** do not just see `2.0.16` in config—see the selected version in the dependency graph on the right classpath, confirm tests pass, and document rationale and residual risks in the PR.

## 12. Common Errors

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Maven property set, yet version unchanged | Project only imports BOM instead of inheriting Spring Boot Parent; property is not interpolated into imported BOM | Switch to a managed entry in project `dependencyManagement` and inspect effective POM |
| Gradle `ext['...version']` set, yet version unchanged | Project uses Gradle native `platform()` only | Use Gradle native constraints or mechanisms; verify with `dependencyInsight` |
| Gradle shows a version higher than the BOM version | Another dependency or constraint asks for a higher version; regular platform does not force versions | Read selection reason and dependency paths; consider appropriate rules/constraints |
| Maven classpath does not match newly added version | Version declared in wrong place, another profile/module, or another management rule dominates | Run `help:effective-pom` and `dependency:tree` in the right module/profile |
| Build succeeds, yet runtime throws `NoSuchMethodError` | Binary incompatibility among JARs in the same library family | Align related module versions, roll back, or upgrade the whole BOM per upstream support |
| JSON/logging/networking behaves differently | Library behavior/defaults/API changed even though compilation succeeded | Run integration/regression tests on affected functionality |
| `No matching version` / resolution conflict | `strictly` constraint conflicts with another requirement | Read `dependencyInsight`, fix the real requirement; do not default to `force` |
| Scanner report still warns after editing build file | Artifact still resolves to another version, scanner inspects a different image, or dependency sits on another classpath | Compare trees, runtime JAR/container image, and scan metadata |
| "Fixed," yet upgrading Spring Boot later breaks the build | Old override shadows the new BOM version or becomes incompatible | Include removing overrides on your Spring Boot upgrade checklist and re-test |

## 13. Hands-On Exercise and Completion Criteria

Try this on a **practice branch** in a Spring Boot project with a Wrapper. No production library upgrade is needed.

1. Pick an artifact already present in the dependency graph and managed by the BOM. Record Boot version, build tool, and selected version.
2. Pick **one** override method matching your project style. State a clear reason and select a version that actually exists in the repository, not a fictional number.
3. Re-run Maven `dependency:tree` or Gradle `dependencyInsight`. Verify the selected version changed as intended and identify related modules.
4. Run `clean verify` with Maven or `clean build` with Gradle. Run the app and at least one integration test exercising the changed library.
5. Observe the difference between "version in config," "selected version," and "runtime behavior." Record both success and any failure evidence.
6. Revert the override and prove the dependency graph returns to its initial baseline.

You have mastered the lesson when you can answer: **Why is the override needed? Which version is actually selected? How many artifacts are affected? How was compatibility verified? When can the override be removed?**

## Official Documentation

- [Spring Boot – Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot – Maven plugin: Using the Plugin / Dependency Management](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot – Dependency Versions Properties](https://docs.spring.io/spring-boot/appendix/dependency-versions/properties.html)
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html)
- [Gradle – Platforms and Maven BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle – Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)