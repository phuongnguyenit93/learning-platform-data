# Controlling SNAPSHOTs, Dynamic Versions, and Replaceable Dependencies

A Spring Boot build is only genuinely **reproducible** when the exact same set of controlled inputs yields the same dependency graph and artifact under defined policies. Even when source code and `pom.xml`/`build.gradle` remain unchanged, results can differ across two machines or two days because a `1.4.0-SNAPSHOT` dependency was republished, a dynamic version expression `1.+` selected a newer release, a repository replaced a file under the same coordinate, or Maven/Gradle caches hold stale metadata.

This lesson explains how to **identify and control three sources of variability**: **Maven SNAPSHOTs**, **Gradle dynamic/changing dependencies**, and **replaceable dependencies/metadata during resolution**. You will build a Java 17 Spring Boot example using fixed release dependencies; learn to use Maven Enforcer, Maven repository policies, Gradle dependency locking, fail-on-nonreproducible resolution, dependency verification, dependency reports, and CI/CD rules. The goal is not blocking every update, but **turning updates into intentional decisions with logs, diffs, testing, and rollback capability**.

The examples use **Spring Boot 3.3.13, Java 17, Gradle 8.x, and Maven 3.9.x** as an illustrative configuration, not implying they are the latest versions or current vendor support policies. In practice, use plugin/tool versions compatible with your organization and consult documentation for your exact branch.

## 1. Why Can the Same Commit Produce Two Different Builds?

Suppose an application has the dependency:

```text
com.acme:policy-client:1.4.0-SNAPSHOT
```

At 09:00, an internal repository serves JAR content A. By 15:00, the `policy-client` team publishes a new SNAPSHOT under the same base coordinate, containing JAR content B. If developer X uses a cache holding A while CI pulls fresh metadata and downloads B, **the same `pom.xml` or `build.gradle` can compile/test differently**.

Another scenario:

```groovy
dependencies {
    implementation 'org.example:codec-lib:2.+'
}
```

At time 1, Gradle resolves `2.+` to `2.4.1`; at time 2, the repository releases `2.5.0` and Gradle may pick the newer release once the cache expires or is refreshed. Although the module resolves to a **concrete version coordinate** at build time (`2.4.1` or `2.5.0`), the **selector in the build script remains dynamic**.

A third, more dangerous case: a repository or mirror allows **overwriting a release artifact** `com.acme:policy-client:1.4.0` with different bytes without changing the version. In that case, **pinning a version string is insufficient**; you need immutability policies and content/origin verification.

**Three different scenarios with similar symptoms:** failures reproducing only in CI, machine A passes while machine B fails, a hotfix “disappears,” JAR checksums change despite unchanged source, or runtime throws `NoSuchMethodError`/`ClassNotFoundException` after a fresh build.

## 2. Distinguishing Fixed, Dynamic, and Changing Dependencies

| Concept | Example | What can change? | How to control |
| --- | --- | --- | --- |
| **Fixed release version** | `com.acme:policy-client:1.4.0` | Version is explicit; **bytes can still be replaced if repository allows overwrite** | Immutable repository, dependency verification/checksums, CI logs |
| **Maven SNAPSHOT** | `com.acme:policy-client:1.4.0-SNAPSHOT` | Final artifact contents can change while base version stays the same | Avoid in releases; pin/promote immutable artifacts; Enforcer, snapshot repository policy |
| **Gradle dynamic version** | `com.acme:policy-client:1.+`, `[1.0,2.0)`, `latest.release` | **Selected version** can change with new metadata | Switch to explicit release versions or dependency locking |
| **Gradle changing module** | `1.4.0-SNAPSHOT`, or dependency with `changing = true` | **Artifact/metadata at the same coordinate** can change | Avoid in releases, control TTL during development, convert to immutable release |
| **Maven version range** | `[1.4,2.0)` | Resolver can choose another valid version as repository changes | Avoid open ranges in releases; manage concrete versions via parent/BOM |
| **Substitution/replacement rule** | Replacing external module with project/local module | **Selected source/target module** can change via rules/configuration | Review substitutions, inspect dependency graph, use locks/CI guards |
| **Transitive dependency** | Library A pulls library B | Version B can change due to graph conflicts/BOM/repository | Dependency tree/insight and lock all resolved versions when needed |

It is essential to distinguish **dynamic** from **changing**:
- **Dynamic**: the selector has not pinned the *final version*; for example, `2.+` can pick a newer version.
- **Changing**: the version string is fixed, yet **the JAR/POM/metadata contents** under that coordinate can change.
- A dependency can exhibit **both properties**, such as a dynamic selector resolving to a snapshot module.
- **Dependency locking** pins the version of dynamic dependencies, **not** the bytes of a changing module.

In Maven, `-SNAPSHOT` is the familiar signal of mutable contents; in Gradle, the changing concept is broader and includes artifacts marked `changing = true`.

## 3. Which Layers Must a “Reproducible” Build Stabilize?

Do not treat `version = '1.0.0'` or `<version>1.0.0</version>` as enough. Independent layers include:

1. **Source code:** commit, submodules, generated sources, build scripts, config files.
2. **Version selection:** direct and transitive versions of Java dependencies, plugins/parents/BOMs, JDK/toolchain.
3. **Artifact identity:** even for identical group:artifact:version, **JAR/POM bytes can differ** if sources allow replacement.
4. **Repository metadata and repository order:** mirrors, repository policies, artifact publication, and caches.
5. **Resolution logic:** Gradle constraints, platforms, forced versions, substitutions, Maven `dependencyManagement`, and scopes.
6. **Build environment:** JDK/Gradle/Maven versions, OS/locale/time zone, environment variables, profiles.
7. **Archive output:** timestamps, file ordering, filtered resources, and build-info metadata can alter hashes even with equivalent code.

Practical definition:

```text
reproducible output
  = fixed source + controlled resolved graph + immutable/verified inputs
    + controlled build tools/environment + deterministic packaging
```

If you only apply dependency locking while still consuming a republished SNAPSHOT, you only pin the **logical version**, not its contents. If you only track the output JAR's SHA-256 without retaining dependency sources and toolchain details, explaining why a hash changed becomes very difficult.

## 4. How Do Maven SNAPSHOTs Actually Work?

### 4.1. `-SNAPSHOT` Is an In-Development Version

Maven dependency:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>policy-client</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

This is an **illustrative snippet for a hypothetical internal dependency**, runnable only if your organization actually hosts `com.acme:policy-client` and its repository. Do not add it to the runnable sample project below.

In a remote Maven snapshot repository, `1.4.0-SNAPSHOT` can map via `maven-metadata.xml` to a **timestamped snapshot** like:

```text
policy-client-1.4.0-20261109.031522-7.jar
```

This is merely an illustration of the timestamp/build-number format, **not a real filename**. Two publishes can create different snapshot builds within the same base version. Consumers still declare `1.4.0-SNAPSHOT`; repository metadata decides the active build on update.

**Snapshots are not releases:** using A yesterday and B today **does not** mean the source repository was silently altered; that is the expected behavior of snapshot policies. Problems arise when trying to build a release or debug history without recording/pinning the exact artifact.

### 4.2. Local Repository and Metadata

Maven caches downloaded artifacts in `~/.m2/repository` (or the location configured in settings). The same base snapshot can have metadata/local copies updated at different times. The build tool does not automatically check the remote every run unless repository policy/cache settings require it.

Two machines with:
- the same source commit,
- the same `pom.xml`,
- the same JDK,
- **but different snapshot metadata refresh times**

can still run different dependency bits. Thus “it works locally” does not prove CI will repeat the exact bit-level inputs.

### 4.3. Distinguishing Snapshot Dependencies from Project Version

A project's own `<version>1.0.0-SNAPSHOT</version>` is distinct from a `1.4.0-SNAPSHOT` dependency. There are two separate release policies:
- Do not publish the project as a SNAPSHOT when building an official release.
- Do not allow a release project to pull any SNAPSHOT dependency (direct **or transitive**).

Maven Enforcer provides separate rules for these two goals: `requireReleaseVersion` and `requireReleaseDeps`.

## 5. Maven Repository Policy: `snapshots`, `updatePolicy`, and `checksumPolicy`

Maven allows configuring repositories separately for releases and snapshots. Example of a **hypothetical internal snapshot repository**, placed in `<repositories>` in the POM or managed equivalently via organization profiles/settings:

```xml
<repositories>
    <repository>
        <id>internal-snapshots</id>
        <url>https://repo.example.invalid/maven-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </snapshots>
    </repository>
</repositories>
```

**This is an illustrative POM snippet; `repo.example.invalid` is intentionally not a live endpoint.** Do not insert it into the runnable project; in real environments use your organization's repository URL/credentials securely.

`updatePolicy` accepts:
- `always`: checks metadata updates frequently, suitable for dev workflows tracking latest snapshots.
- `daily`: common default, checks once per day.
- `interval:X`: checks every `X` minutes.
- `never`: does not proactively check for updates under normal policy; **does not create a version pin or immutable checksum guarantee**.

`checksumPolicy` can be `fail`, `warn`, or `ignore`. Setting `fail` makes Maven stricter about remote checksums, yet **does not replace** verifying against trusted reference hashes: a publisher authorized to overwrite both the artifact **and its checksum** can still alter inputs.

Two namespaces to note:
- `<repositories>` supplies **project dependencies**.
- `<pluginRepositories>` supplies **Maven plugins**. Plugin governance is also part of reproducibility, not just Java library pinning.

**Release repositories should be immutable after publishing.** A repository manager can be configured to block redeploying/overwriting release coordinates, using provenance/signatures and promotion policies. Consumer POMs cannot fully protect themselves if the organization permits overwriting published artifacts.

## 6. Maven Flags `-U` and `-o`: Useful, Not Locks

Command:

```bash
./mvnw -U dependency:tree
```

`-U` forces Maven to check for snapshot/metadata updates per Maven version semantics; it helps when suspecting a local machine holds an outdated snapshot. **It does not guarantee reproducibility**: it can itself pull a **newer SNAPSHOT** than the previous build.

Offline mode:

```bash
./mvnw -o test
```

`-o` uses only what is already in the local repository; if a dependency/plugin is uncached, the build can fail. **Offline does not prove artifact immutability**, nor does it ensure two machines have identical local repositories.

When debugging, compare:
- snapshot timestamp/source,
- Maven repository config and mirrors,
- actual resolved versions,
- POM and JAR bytes/checksums,
- Maven/JDK versions.

Never “fix” errors by telling everyone to pass `-U` or `-o` permanently. Those are diagnostic tools, not release policies.

## 7. Maven Sample Project Using Fixed Release Versions

To provide a **runnable example requiring no private repository**, create a small Spring Boot project using a public Apache Commons Lang3 release dependency.

Structure:

```text
repro-demo/
├── pom.xml                       (Maven option)
├── settings.gradle               (Gradle option)
├── build.gradle                  (Gradle option)
└── src/
    ├── main/java/com/example/repro/
    │   └── ReproApplication.java
    └── test/java/com/example/repro/
        └── ReproApplicationTest.java
```

Use **Maven or Gradle** as the build tool for one practice run; there is no need to configure both simultaneously. The Java code below is shared.

### 7.1. Java 17 Application

`src/main/java/com/example/repro/ReproApplication.java`:

```java
package com.example.repro;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ReproApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ReproApplication.class, args)) {
            System.out.println("result=" + StringUtils.reverse("repro"));
        }
    }
}
```

In this example, `spring-boot-starter` (without web starter) runs a non-web application context. After calling the Commons Lang method and closing the context, the JVM exits. The line printed by application code:

```text
result=orper
```

Other Spring Boot logs may appear; do not assume stdout contains only one line. `StringUtils.reverse("repro")` deterministically returns `"orper"` with a compatible Commons Lang version.

### 7.2. JUnit Jupiter Test

`src/test/java/com/example/repro/ReproApplicationTest.java`:

```java
package com.example.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.apache.commons.lang3.StringUtils;
import org.junit.jupiter.api.Test;

class ReproApplicationTest {

    @Test
    void dependencyHasExpectedBehavior() {
        assertEquals("orper", StringUtils.reverse("repro"));
    }
}
```

This is a **unit test without Spring context**, as the goal is simply verifying the resolved library's behavior. The test runs via Maven Surefire/JUnit Jupiter or Gradle `useJUnitPlatform()` in their respective configs. It is not a checksum check of the dependency, though it serves as a useful smoke test if a version update changes API/behavior.

### 7.3. Complete POM with Explicit Release Dependency

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The POM uses the Spring Boot starter parent to manage starter versions and compatible build plugins. Commons Lang `3.14.0` is pinned **directly** to illustrate a fixed release; other projects may manage it centrally via `dependencyManagement` aligned with a BOM, yet must still verify the actual **resolved version**.

Run:

```bash
./mvnw clean verify
./mvnw dependency:tree
java -jar target/repro-demo-1.0.0.jar
```

Use `mvn` if the project lacks a Maven Wrapper. In Windows PowerShell use `.\mvnw.cmd`. When tests and the build succeed, Maven `package`/`verify` produces an executable JAR via `spring-boot-maven-plugin` and the application prints `result=orper`.

**Limitation:** pinning Commons Lang directly does not automatically lock every transitive dependency, parent, plugin, or the bytes of an artifact overwritten remotely. Additional controls are needed.

## 8. Maven Enforcer: Forbidding SNAPSHOTs at Release Time

Maven Enforcer provides at least two helpful rules:
- `requireReleaseVersion`: the current project (and by default its parent) **must not** use a SNAPSHOT version.
- `requireReleaseDeps`: **forbids** SNAPSHOT dependencies in the dependency graph, checking transitives by default.

Example profile dedicated to releases. **Add the following inside `<project>` in the POM from Section 7**; do not create a second POM file:

```xml
<profiles>
    <profile>
        <id>release-check</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-enforcer-plugin</artifactId>
                    <version>3.6.3</version>
                    <executions>
                        <execution>
                            <id>block-snapshot-release</id>
                            <phase>validate</phase>
                            <goals>
                                <goal>enforce</goal>
                            </goals>
                            <configuration>
                                <rules>
                                    <requireReleaseVersion/>
                                    <requireReleaseDeps>
                                        <searchTransitive>true</searchTransitive>
                                    </requireReleaseDeps>
                                </rules>
                                <fail>true</fail>
                            </configuration>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Check the release build:

```bash
./mvnw -Prelease-check clean verify
```

If the project version is `1.0.0-SNAPSHOT` or the dependency graph contains `1.4.0-SNAPSHOT`, the corresponding rule can fail the build in the validate phase. If you want the policy enforced on **every** build, put the Enforcer plugin/execution directly under `<build><plugins>` without a profile. Remember to activate the profile in the **CI release job** if using the profile approach.

**Note:** `requireReleaseDeps` forbids SNAPSHOTs under Maven rules, yet **does not prove every release JAR is immutable** or block all Maven version ranges. Releases must combine fixed versions, immutable repositories, managed plugin/parent versions, checksums/provenance, and releasing only from passing CI.

In multi-module reactors, the profile/rule must exist on all released modules, usually managed in the parent so child modules are not missed.

## 9. Maven dependencyManagement, Version Ranges, and BOM

### 9.1. Centralized Version Management Does Not Equal Locking Bytes

Example in a parent POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Child modules then declare the dependency without a version:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
```

When the dependency is actually used, its version is controlled by management. **Do not** confuse `dependencyManagement` with a dependency declaration: management **does not add the library to the classpath**. Nor can it prevent a repository from replacing bytes under coordinate `3.14.0`.

### 9.2. Maven Version Ranges

Explanatory example—**do not use for releases in this lab**:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>policy-client</artifactId>
    <version>[1.4,2.0)</version>
</dependency>
```

Maven can choose a different version within the allowed range when a new release appears in the repository. Vague declarations such as `LATEST` or `RELEASE` (unsuitable/restricted depending on Maven version) should also be avoided; do not apply syntax or expectations like Gradle's `latest.release`. **Simplest for releases:** pick a concrete version and upgrade deliberately via pull request, dependency report, and testing.

### 9.3. What Problem Does the Spring Boot BOM Solve?

The `spring-boot-dependencies` BOM keeps libraries across the Spring Boot ecosystem aligned to a tested, compatible version set. It is **version management**, not a byte lock, and does not protect against SNAPSHOTs or transitive artifacts replaced in a repository.

If you only **import the BOM** without inheriting `spring-boot-starter-parent`, you must additionally control plugin versions/executions (compiler, Surefire, Boot Maven Plugin). Non-reproducible builds can also arise from Maven plugins resolving to different versions, not just Java dependencies.

## 10. Maven: Finding Which Dependency Was Actually Selected

At the project root:

```bash
./mvnw dependency:tree
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw help:effective-settings
```

- `dependency:tree`: inspect **direct and transitive dependencies** and the versions selected via Maven conflict mediation.
- `help:effective-pom`: inspect the POM after inheritance, profiles, and plugin/`dependencyManagement`; essential when using the Spring Boot parent or a corporate parent.
- `help:effective-settings`: inspect actual repository/mirror/profile settings (be careful, as output can contain internal/environment details).

To target a specific module group, Maven Dependency Plugin supports filters like:

```bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

The output reveals the actual selected version and dependency path leading to it. When investigating:
- Verify source `pom.xml` and effective POM.
- Inspect dependency tree and repository mirrors.
- Compare local repository file bytes/checksums against trusted reference values.
- Check Maven Wrapper and JDK versions.
- Search for SNAPSHOTs/ranges in both child POMs and parent/imported BOMs.

Never conclude reproducibility just because `mvn dependency:tree` outputs one graph today; tomorrow, if snapshot metadata/ranges/repos change, the graph may no longer match.

## 11. Gradle Dynamic Versions Are Selectors, Not Concrete Versions

Several ways to declare them:

```groovy
dependencies {
    implementation 'com.acme:policy-client:1.+'
    implementation 'com.acme:policy-client:[1.4,2.0)'
    implementation 'com.acme:policy-client:latest.release'
}
```

**These are three alternative selector examples**, not three dependencies to add together. `com.acme:policy-client` is a **hypothetical internal artifact** and cannot be resolved from Maven Central in this example.

Explanation:
- `1.+` chooses a version in the 1.x branch based on what Gradle sees in repositories.
- `[1.4,2.0)` expresses a range with 1.4 inclusive and 2.0 exclusive.
- `latest.release` is Gradle's status-based selector, **not** equivalent to “always fetch the absolute latest regardless of all metadata.”
- After resolution, Gradle uses a concrete version, yet that choice can shift when new repository metadata is observed.

Dynamic versions can be convenient in **integration/nightly channels testing compatibility**. For production releases, they can cause two builds from the same commit to pull two different versions; pin releases or generate/commit a managed **lock state**. Keep in mind that Gradle version constraints/BOMs can also affect the final version.

## 12. Gradle Changing Dependencies: Same Version, Potentially Different Bytes

Example:

```groovy
dependencies {
    implementation 'com.acme:policy-client:1.4.0-SNAPSHOT'
}
```

Gradle normally treats Maven `-SNAPSHOT` as a **changing dependency**: same base version, yet remote artifacts/metadata can be republished.

You can also mark **a module without the SNAPSHOT suffix** as changing if the publisher genuinely allows updates:

```groovy
dependencies {
    implementation('com.acme:mutable-client:1.4.0') {
        changing = true
    }
}
```

This is an illustrative configuration for an **internal source with a real artifact**; do not use it on a release designated immutable by your organization. `changing = true` only changes **how Gradle caches/revalidates the dependency**; it **does not** make the dependency safe or freeze its bytes.

Other sources of variability:
- **Version ranges/direct dependencies** from changed external metadata.
- **Transitive changing dependencies** pulled in by another library.
- **Composite builds/included builds** replacing an external module with a local project.
- **Resolution rules** like `dependencySubstitution`, `force`, and `eachDependency` changing graph selections away from original declarations.
- **Repository ordering/mirrors** selecting metadata/artifacts from a different source.

Key distinction: a changing dependency is **same coordinate, mutable contents**; substitution is **changing the selected module/provider**. Both deserve monitoring, though their control mechanisms differ.

## 13. Gradle Dependency Cache and `--refresh-dependencies`

Gradle caches separately:
- Metadata for **dynamic version resolution**, e.g., `1.+` mapping to `1.4.2`.
- Metadata and artifacts for **changing modules**.
- Downloaded binary artifacts, cached based on appropriate metadata/checksums.

Gradle's typical default for dynamic/changing items is **24 hours**, with configurable TTLs. Consequently:
- Machine A resolved `1.+` yesterday and still holds the older version.
- Machine B builds for the first time and sees the newer version.
- CI runs with a wiped or revalidated cache and picks a different graph.

Example adjusting TTLs **strictly for dev/integration channels**, not as a release reproducibility policy:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 0, 'seconds'
}
```

`cacheDynamicVersionsFor` controls cache age for **dynamic version selector results**; `cacheChangingModulesFor` controls cache age for **changing module metadata/artifacts**. Short TTLs increase remote requests and can add build overhead/time.

Option:

```bash
./gradlew --refresh-dependencies dependencies
```

tells Gradle to revalidate cached dependency resolutions and applicable artifacts; it **does not necessarily re-download every JAR if verified unchanged**. It neither locks the newly resolved versions nor replaces a dependency lockfile.

`--offline` uses only existing cache contents; it helps when offline but **does not prove two machines share identical dependency bits**.

## 14. Gradle Sample Project Using Fixed Release Versions

Create `settings.gradle`:

```groovy
rootProject.name = 'repro-demo'
```

Create complete `build.gradle` (Groovy DSL) using **the same Java files from Section 7**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.repro.ReproApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Notes:
- Spring Boot Gradle plugin and dependency management plugin have **pinned versions**.
- Starter dependencies resolve via the appropriate BOM, and Commons Lang3 is explicitly declared as `3.14.0`.
- The Java toolchain requests a Java 17 compiler. The JVM running Gradle, toolchain, and artifact runtime do not automatically match unless you control them.
- There are no `1.+`, `latest.release`, or SNAPSHOTs in the example.
- `useJUnitPlatform()` is needed for Gradle to execute JUnit Jupiter tests.
- This configuration produces an executable JAR from `bootJar` without requiring another main class.

Run:

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
java -jar build/libs/repro-demo-1.0.0.jar
```

With the Java 17 sample, the line printed by the app is `result=orper`; Gradle may print build logs and Spring Boot logs around this line. In Windows PowerShell use `.\gradlew.bat` when using the Gradle Wrapper. For projects with different names/versions, look up the actual artifact in `build/libs` instead of guessing the filename.

This setup is **more predictable** than dynamic versions, though not yet an absolute guarantee of content immutability or deterministic archives. The following steps add those controls.

## 15. Gradle: Catching Dynamic/Changing Dependencies Fail-Fast

When you want a **release build strictly free of dynamic/changing resolution**, add this rule to the appropriate project:

```groovy
configurations.configureEach {
    resolutionStrategy {
        failOnNonReproducibleResolution()
    }
}
```

This is an **add-on snippet** for `build.gradle` or a convention plugin of a **release module** containing configurations to check. Gradle's `ResolutionStrategy.failOnNonReproducibleResolution()` combines:
- `failOnDynamicVersions()`;
- `failOnChangingVersions()`.

If the dependency graph has a dynamic selector or changing module making resolution unstable, Gradle fails during resolution. This serves as a **guardrail**, avoiding manual scans of dependency lists to catch every case.

Two selective policy modes:

```groovy
// Detect only dynamic version selection:
configurations.configureEach {
    resolutionStrategy.failOnDynamicVersions()
}
```

```groovy
// Detect only changing versions/artifacts:
configurations.configureEach {
    resolutionStrategy.failOnChangingVersions()
}
```

These three snippets are **alternatives** (the first already covers both individual guards); do not stack all three together.

**Scope:** applies to configurations resolved within the project. It **does not automatically inspect every settings plugin classpath, every included build, artifacts downloaded by external scripts, or every CI image**. Plugin versions, buildscript dependencies, toolchains, and repositories still need separate control.

**Do not confuse with `failOnVersionConflict()`:** that handles *two different versions of the same module*, not a specialized guard against SNAPSHOT/dynamic versions. A graph can have zero version conflicts yet still rely on `1.+` and remain unstable.

## 16. Gradle Dependency Locking: Pinning Resolved Versions

If a project needs dynamic selectors during a development phase while keeping builds stable, Gradle offers **dependency locking**: recording **resolved versions**, including transitives, in lock state.

Add to `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

**Step 1 — generate lock state** by resolving the configurations to lock. For a single project:

```bash
./gradlew dependencies --write-locks
```

Gradle creates `gradle.lockfile` in the corresponding project for resolved configurations, with lines like:

```text
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
...
```

This is an **illustrative excerpt**; the actual file contains more modules and configurations depending on the project. **Commit the lockfile to Git** and review diffs like source code. Never hand-edit the lockfile by guesswork.

**Step 2 — normal build:**

```bash
./gradlew clean test bootJar
```

When lock state exists, Gradle uses version constraints to ensure the graph does not silently shift to newer versions outside the lock. If dependency declarations change incompatibly with the lock, resolution can fail and require an intentional lock update.

**Step 3 — controlled updates:**

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

This command lets Gradle re-resolve the specified module in lock state within current **requested constraints and repositories**, updating related state; connected modules can still be affected. Review the **full lockfile diff** and rerun tests/builds/smoke tests. If the project has multiple configurations, ensure they are actually resolved when generating/updating locks.

**In multi-project builds:** `./gradlew dependencies --write-locks` does not necessarily resolve **every subproject**; invoke project-specific tasks, such as `./gradlew :app:dependencies --write-locks`, or a well-designed aggregate resolver workflow. Do not treat a root lockfile as proof the entire repository is locked.

### 16.1. Lockfiles Do Not Preserve SNAPSHOT Bytes

This is the most critical limitation of dependency locking:

```text
locked coordinate:
com.acme:policy-client:1.4.0-SNAPSHOT

Day 1: JAR sha256 = A...
Day 2: JAR sha256 = B... (same coordinate)
```

A lock state records the **same `1.4.0-SNAPSHOT` version string**, so it **cannot guarantee artifact bytes stay unchanged**. Gradle also warns when persisting locks for changing dependencies. For production, move to **immutable releases** or content-addressed/promoted artifacts with equivalent policies, and apply dependency verification/checksums where appropriate.

**Lockfiles solve version selection**, not complete artifact provenance. That is why locking must pair with repository publishing controls rather than thinking “we have `gradle.lockfile`, so SNAPSHOTs are safe.”

## 17. Gradle Dependency Verification: Checking Whether Received Files Are Authentic

Gradle provides **dependency verification** via checksums or signatures to verify received artifacts and metadata. The metadata file typically resides at:

```text
gradle/verification-metadata.xml
```

You can bootstrap SHA-256 checksums:

```bash
./gradlew --write-verification-metadata sha256 dependencies
```

Gradle resolves the relevant dependencies and creates/updates verification metadata. **Important:** bootstrapping trusts whatever the artifact repository serves at that moment; it **does not independently verify that the source is trustworthy**. Review the generated file, cross-check trusted publishers/repositories, and commit metadata only after approval.

Partial **illustrative structural example—not a complete metadata file**:

```xml
<components>
    <component group="org.apache.commons" name="commons-lang3" version="3.14.0">
        <artifact name="commons-lang3-3.14.0.jar">
            <sha256 value="VERIFIED_CHECKSUM"/>
        </artifact>
    </component>
</components>
```

`VERIFIED_CHECKSUM` is purely an **explanatory placeholder**, **not a valid hash to copy into a real file**. Let Gradle generate the metadata, verify the hashes, and use Gradle's full schema. Never copy this abbreviated XML snippet as `verification-metadata.xml`.

**Special limitation:** Gradle dependency verification **does not verify changing dependencies like SNAPSHOTs** in the way it verifies immutable modules, since their contents can change continuously; nor does it verify locally built artifacts through this dependency verification mechanism. Never use verification as an excuse to allow SNAPSHOTs in releases.

Checksums and signatures serve different roles:
- **SHA-256 checksum:** detects bytes differing from the reference value.
- **Signature:** proves provenance under properly configured keys/trust.
- Combining them lowers risk, yet does not replace code review, vulnerability scanning, or release policies.

On a checksum mismatch, **never delete metadata and regenerate new hashes just to make CI green**; investigate whether the publisher legitimately altered an artifact, a cache corrupted, a mirror swapped sources, or an attack occurred.

## 18. Gradle Substitutions, Version Conflicts, and “Replaced Dependencies”

Beyond mutable artifacts, some builds swap **dependency targets** via rules:

```groovy
// Example only when the same build HAS a ':policy-client' subproject.
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('com.acme:policy-client') using project(':policy-client')
    }
}
```

This is a **conditional snippet**; do not insert it into `repro-demo`, which has no `:policy-client` subproject. In a valid multi-project/composite build, rules can cause a consumer to use **local project output** instead of a Maven repository module. They are **two different byte sources**, even when the dependency name typed by developers stays unchanged.

Similar situations:
- `includeBuild(...)` in composite builds can apply **dependency substitution** matching included build coordinates, depending on settings.
- `resolutionStrategy.force(...)` forces a version, potentially masking library conflicts.
- `eachDependency` rules and component selection rules can alter selected versions/modules.
- `platform(...)`, BOMs, version constraints, and Gradle variant-aware selection can change the final graph relative to individual dependency strings.

**Do not equate substitution with SNAPSHOTs:** substitution chooses a **different producer/module**, while a changing dependency is one producer/coordinate with **changing bytes**. Both impact reproducibility, requiring inspection of the **resolved component graph**, not just reading a single `implementation` line.

Diagnostic commands:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew buildEnvironment
```

`dependencies` shows the graph; `dependencyInsight` shows why a version was chosen; `buildEnvironment` inspects buildscript dependencies within scope. In multi-project builds, run on the right module, such as `:boot-app:dependencies`, rather than assuming the root project represents everything.

## 19. How Do Fixed Versions, BOMs, Version Catalogs, and Lockfiles Differ?

| Tool/Technique | What problem does it solve? | What does it NOT solve? |
| --- | --- | --- |
| **Fixed version literal** | Selects an explicit version coordinate for one dependency | Overwritten bytes, transitive conflicts, plugin environment |
| **Maven dependencyManagement / BOM** | Manages/aligns versions across a set | Does not lock bytes or block mutable repositories |
| **Gradle version catalog** | Centralizes aliases/versions for teams, reducing copy/paste | Does not lock transitive graphs or artifact contents |
| **Gradle dependency locking** | Pins **resolved module versions**, including transitives in locked configurations | Does not pin bytes of changing modules |
| **Gradle dependency verification** | Compares hashes/signatures of supported immutable dependencies/artifacts | Does not verify changing snapshots like immutable artifacts; does not select versions for you |
| **Maven Enforcer release rules** | Fails when project/dependencies contain SNAPSHOTs per policy | Does not prove remote release JARs are not overwritten |
| **Immutable artifact repository** | Prevents changing bytes of a published release coordinate | Does not pick a stable version if the build still uses `1.+` |
| **Java toolchain/Wrapper + deterministic packaging** | Reduces environmental and archive output differences | Does not fully pin the dependency graph |

**There is no single “enable reproducible builds” switch.** You must combine versioning, artifact immutability, resolution policies, and testing the exact deployed output.

## 20. Safe Dependency Upgrade Workflow

Instead of using `1.+` to auto-fetch new releases daily, organizations can follow this cycle:

1. **Detect updates** via tooling/renovation bots or official release notes.
2. **Open a PR** changing an explicit version or a BOM-managed version group.
3. **Keep base/plugin/JDK versions unchanged** outside the change scope unless intentionally upgrading.
4. **Update Gradle lockfiles** if using locking; do not hand-edit files to trick the resolver.
5. **Update dependency verification metadata** via approved processes; review checksums/signatures from trusted sources.
6. **Inspect the dependency graph diff**: direct and transitive, explaining unexpected version changes.
7. **Run unit/integration tests and smoke-test the executable JAR**, checking manifest and nested libraries.
8. **Review SBOM/provenance** and security scans per policy.
9. **Promote the immutable release artifact** to the deployment registry, recording checksum, build ID, and commit reference.
10. **Allow rollback** to the published artifact rather than rebuilding from a mutable SNAPSHOT.

For an internal dependency without a stable release yet, SNAPSHOTs can be used in **integration/dev pipelines** to surface issues early. However, **production inputs** should be immutable promoted versions/contents or revisions governed by an equivalent control process.

### 20.1. Do Not Replace the Upgrade Process with `--refresh-dependencies` or `-U`

Both flags can force the resolver to check fresh metadata, yet they create no PR, preserve no record of old versions, attach no trusted checksums, and perform no regression tests. During hard-to-reproduce bugs, casually “refreshing” can even overwrite the faulty snapshot cached locally.

## 21. CI: Separating Nightly Integration from Releases

A clear policy should define at least two modes:

| Environment | Allow SNAPSHOT/dynamic? | Goal |
| --- | --- | --- |
| **Developer sandbox** | Controlled, if integrating with active modules | Fast feedback, accepting changing inputs |
| **Integration/nightly** | Can test latest/snapshots, with full logs | Catch incompatibilities early; failures do not release directly |
| **Pull request validation** | Prefer fixed resolved versions/lockfiles | Relatively stable re-runs and dependency diff reviews |
| **Release candidate/production** | **Never** allow mutable SNAPSHOT/dynamic selectors | Verifiable versions, checksums/provenance, and immutable artifacts |

For **Maven release jobs**:

```bash
./mvnw -B -Prelease-check clean verify
./mvnw dependency:tree
```

Ensure the `release-check` Enforcer profile exists as in Section 8. These commands do not prevent repository overwrites by themselves; external repository policies and artifact verification are required.

For **Gradle release jobs**:

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
```

Use `failOnNonReproducibleResolution()` and/or dependency locking and committed verification metadata per policy. For modules with their own sources, run the proper tasks/configurations; **running root `dependencies` alone does not prove all subprojects are clean**.

In both cases, record:
- Source commit and build ID.
- JDK/Maven/Gradle Wrapper and Spring Boot plugin/parent versions.
- Resolved dependency graph/SBOM.
- Artifact filename and SHA-256.
- Test reports and resource/packaging metadata.
- Repository/mirror policy used at build time (without logging secrets).
- Exact artifact path delivered to deployment.

Warn in the pipeline if snapshot dependencies, dynamic versions, snapshot plugins, or out-of-policy dependency substitutions appear. Never print repository secrets to logs.

## 22. Verifying the Spring Boot Executable JAR Received the Right Dependencies

Even when a build passes, inspect the **actual artifact**. For the Gradle demo:

```bash
jar tf build/libs/repro-demo-1.0.0.jar
```

For the Maven demo:

```bash
jar tf target/repro-demo-1.0.0.jar
```

A standard Spring Boot executable JAR will contain:
- `META-INF/MANIFEST.MF`;
- `BOOT-INF/classes/com/example/repro/ReproApplication.class`;
- `BOOT-INF/lib/commons-lang3-3.14.0.jar`;
- required Spring Boot runtime dependencies in `BOOT-INF/lib`.

**These filenames are example expectations**, not observed measurements. Use `jar tf` to verify. The Java runtime classpath of a Boot JAR is constructed by the Boot launcher from application classes and nested JARs.

If the artifact is missing Commons Lang:
1. Check Gradle `runtimeClasspath` or Maven `dependency:tree`.
2. Verify dependency scopes/configurations and exclusions.
3. Confirm you inspected the `bootJar` / Maven repackage output rather than a plain JAR.
4. If dependency substitution exists, check whether it redirected the dependency to another project.
5. Run `java -jar` to reproduce and locate the root cause.

For Gradle:

```bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

For Maven:

```bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Note that **the presence of one nested JAR does not guarantee every transitive dependency version is compatible**. Inspect the graph, run tests, and store checksums of the deployed artifact.

## 23. Keeping Archive Outputs Reproducible Too

Stable dependency versions do not guarantee a **byte-identical JAR** if packaging injects varying timestamps, build host/user, absolute paths, or file ordering.

Additional principles:
- Use fixed Java toolchains/Wrappers and plugin versions.
- Control locale/timezone/time sources when programs generate environment-sensitive resources.
- Enable **reproducible file order** and **normalized entry timestamps** per your archive plugin; do not enable blindly on signed or specialized archive formats.
- If Maven plugins support `project.build.outputTimestamp` / reproducible build features, check exact version docs and set explicitly for byte-identical outputs.
- Avoid embedding `Instant.now()`, hostnames, or machine paths into build resources unpredictably unless intentionally designed as controlled metadata.
- Check SHA-256 digests between **two builds with normalized environments and inputs**; do not assume `mvn clean` or `gradle clean` alone guarantees identical bytes.

Linux/macOS checksum example:

```bash
sha256sum build/libs/repro-demo-1.0.0.jar
sha256sum target/repro-demo-1.0.0.jar
```

These commands are for **two different build approaches**; do not expect the Maven JAR and Gradle JAR to share the same SHA-256, as plugin/layout/metadata differ. Compare only two runs of **the same toolchain, same config, and same source/input set**.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\build\libs\repro-demo-1.0.0.jar
```

The checksum of the executable JAR differs from that of a dependency JAR. To detect whether a dependency's bytes changed, inspect the dependency artifact itself or stored trust metadata rather than guessing from the final JAR's hash.

## 24. Common Mistakes and Misconceptions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Same commit, passed yesterday, failed today | Republished snapshot, dynamic selector picked new release, repository/mirror changed | Inspect resolved graph, snapshot metadata, cache policy, checksums |
| `1.+` resolved to `1.5` today | Dynamic version selector, expired metadata cache/TTL | Pin version or commit reviewed lockfile |
| `1.4.0-SNAPSHOT` keeps version, runs differently | Changing module received new artifact bytes | Avoid in releases, promote immutable releases |
| Maven `-U` changes build dependencies | Resolver checked newer metadata/snapshots | Use purposefully for debugging, not as a pin |
| Maven `-o` only works on machine A | Local repository/cache differs from CI | Fix inputs and repos, do not rely on offline alone |
| Maven Enforcer fails to block snapshot release | Profile inactive, rule missing from module, policy unapplied | Enable `-Prelease-check`, inspect effective POM |
| `requireReleaseVersion` passes despite snapshot dependency | It only checks the project version | Add `requireReleaseDeps` |
| `requireReleaseDeps` passes yet release artifact was overwritten | Rule catches SNAPSHOTs, does not prove immutability | No-redeploy release repository + checksum/trust |
| Gradle has lockfile yet SNAPSHOT still differs | Lock pins version, not changing module bytes | Remove SNAPSHOTs from releases, govern artifact registry |
| Gradle `--refresh-dependencies` assumed to re-download all | It revalidates metadata/cache and downloads only when needed | Use appropriately for investigation |
| Gradle `failOnDynamicVersions()` does not block fixed SNAPSHOT | Dynamic and changing are distinct conditions | Use `failOnNonReproducibleResolution()` or guard both |
| Gradle verification misses changed SNAPSHOT | Changing deps sit outside standard immutable checksum verification | Do not treat verification as a SNAPSHOT lock |
| Version catalog pins `3.14.0` yet transitives shift | Catalog manages declarations, does not lock the entire resolved graph | Lock dependencies and inspect insight |
| Spring Boot BOM active yet module has different version | BOM/constraints/conflicts/substitutions affected resolution | Inspect Gradle `dependencyInsight` / Maven `dependency:tree` |
| Local build differs from CI despite pinned versions | Plugin, JDK, repository, environment, generated metadata differ | Pin Wrapper/toolchain and compare logs |
| `NoSuchMethodError` appears at runtime | Version conflict/incompatible dependency or replaced artifact | Inspect graph and nested JAR contents, run tests |
| Gradle local project replaces remote module | Dependency substitution/composite build | Review `includeBuild`, substitution rules, selected components |
| Release manifest/metadata changes on every build | Timestamps, build-info, file order unnormalized | Apply appropriate reproducible archive settings |
| Maven dependency tree stable today, different next month | Snapshots, version ranges, mutable repository | Pin fixed versions, enforcer/repository policies |
| CI picks `-plain.jar` by mistake | Wildcard artifact selection | Specify the exact executable Boot JAR and test with `java -jar` |

## 25. Pull Request and Release Checklist

- [ ] No `-SNAPSHOT`, version ranges/dynamic selectors, or `latest.*` declared in the **release dependency graph** unless explicitly permitted by policy.
- [ ] Maven release jobs enable `requireReleaseVersion` and `requireReleaseDeps` on the right modules/POMs.
- [ ] Maven parent/BOM/plugin versions are managed and verified via `help:effective-pom`.
- [ ] Release repository blocks overwriting/redeploying the same coordinate; snapshot repository is separate with clear TTL/policy.
- [ ] Maven `-U`/`-o` are used intentionally and never treated as reproducibility proof.
- [ ] Gradle releases have `failOnNonReproducibleResolution()` **or** appropriate locking/policy controlling dynamic/changing dependencies.
- [ ] Gradle lockfiles are generated from real configurations, committed, and reviewed across the full diff.
- [ ] Gradle lockfiles are never used as a mechanism to pin `-SNAPSHOT` **bytes**.
- [ ] Dependency verification metadata/checksums are reviewed from trusted sources; never blindly accept new hashes on mismatch.
- [ ] Any dependency substitutions/composite builds and Gradle resolution rules affecting releases have been reviewed.
- [ ] JDK, Gradle/Maven Wrapper, Spring Boot plugin/parent, and BOM versions are recorded.
- [ ] Dependency tree/insight, test reports, and artifact checksums are stored with build provenance.
- [ ] Deployed JAR actually contains the right `BOOT-INF/classes`, `BOOT-INF/lib`, and passes smoke tests.
- [ ] Version upgrades use PR/CI with rollback capability, never replacing old artifacts under the same release coordinate.
- [ ] Build outputs from identical inputs and normalized environments can be compared/explained when checksums differ.

**Remember:** **Fixed versions** help stabilize *version selection*, **lockfiles** preserve the *resolved dependency graph*, **immutable repositories + checksums/provenance** protect *artifact contents*, and **toolchains + deterministic packaging** stabilize *outputs*. SNAPSHOTs, dynamic selectors, and substitutions can be helpful during development, but **must not leak silently into release pipelines** when reliable reproducibility and rollback are the goal.

## Official References

- [Apache Maven — Settings Reference, repositories/snapshots/updatePolicy/checksumPolicy](https://maven.apache.org/settings.html)
- [Apache Maven Enforcer — Require Release Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseDeps.html)
- [Apache Maven Enforcer — Require Release Version](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseVersion.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Gradle — Declaring Versions and Ranges](https://docs.gradle.org/current/userguide/dependency_versions.html)
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — ResolutionStrategy](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.ResolutionStrategy.html)
- [Gradle — Resolution Rules and Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)