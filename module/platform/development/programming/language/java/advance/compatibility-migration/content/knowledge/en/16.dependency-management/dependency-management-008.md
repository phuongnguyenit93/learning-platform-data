# Version constraints, dependency locking, and build reproducibility

When upgrading Java, choosing the right JDK version is only part of the problem. The same commit may build successfully today but fail next week if a transitive dependency is updated, a repository returns a different artifact, a build plugin changes version, or CI and a personal machine use different toolchains. More dangerously, a newly selected dependency may be compiler-compatible yet change runtime behavior: a different API, different algorithm, different module metadata, or requiring a higher Java version.

**Version constraints**, **dependency locking**, and **reproducible builds** are three related tools, but they are not synonymous. Constraints describe which versions are accepted or preferred; locking records the specific version resolution result; reproducible builds control many inputs and packaging so the result can be recreated under a defined contract.

This lesson places those three mechanisms in the context of **Java Advance Compatibility Migration**: from inventorying legacy dependencies, controlling upgrades, generating lockfiles, and aligning BOMs to reproducing artifacts and testing runability on the target JDK. Examples use Gradle and Maven for illustration; actual syntax and features must be applied according to the build tool version chosen by the project.

## 1. Three goals that must be kept separate

First, distinguish three questions:

1. **Which versions are permitted to be used?** This is the scope of constraints, version ranges, BOMs, and version conflict rules.
2. **Which exact versions did a build select?** This is the scope of the resolved dependency graph and dependency locks.
3. **Does rerunning the same source produce the expected artifact and behavior?** This is the scope of reproducibility and compatibility testing.

Example of an application with two libraries:

```text
application
  |
  +-- business-client:2.5.0
  |      |
  |      +-- json-core:2.2.0
  |
  +-- web-adapter:4.1.0
         |
         +-- json-core:2.4.0
```

The project directly declares two libraries, yet must choose one version of `json-core` in the runtime configuration. If Gradle or Maven applies a different resolution mechanism, the selected version may also differ.

Suppose `json-core:2.4.0` changes an API or switches to bytecode requiring a newer JDK. An application upgrading from Java 17 to 21 might suddenly use this version without editing a single direct dependency declaration line. Conversely, if a version with a security vulnerability stays locked for too long, the build may be reproducible yet still **unsafe**.

Therefore, do not equate:

| Concept | Answers the question | Does not guarantee |
|---|---|---|
| Version constraint | Which versions are accepted, preferred, or rejected? | That the selected version is always the same across builds |
| BOM/dependency management | Which modules should use aligned versions? | That the entire dependency graph is strictly locked |
| Dependency lock | What is the resolution result for managed dependencies? | That artifact bytes, plugins, JDK, and environment are all identical |
| Checksum/signature verification | Does the artifact match the expected content/trusted source? | That the version is compatible with the code or free of vulnerabilities |
| Reproducible artifact build | Can the same inputs produce identical output bytes? | That the artifact functions properly for business logic in production |
| Compatibility test | Does the application work under a specific JDK/dependency combination? | That repositories do not change in other builds |

The first three layers are the core focus, but a reliable migration needs to combine the subsequent layers as well.

## 2. Direct dependencies, transitive dependencies, and resolution results

### 2.1. Direct and transitive dependencies

A project typically declares direct dependencies:

```groovy
dependencies {
    implementation 'org.example:business-client:2.5.0'
    implementation 'org.example:web-adapter:4.1.0'
}
```

These modules may declare their own dependencies. Gradle or Maven builds a graph, resolves version conflicts, and then constructs the classpath/module path for compile, test, and runtime.

An application can have multiple configurations:

- Compile classpath.
- Runtime classpath.
- Test compile classpath.
- Test runtime classpath.
- Annotation processor path.
- Plugin/buildscript classpath.
- Custom configurations for code generators, native tooling, or integration tests.

Do not inspect only runtime dependencies and conclude that every configuration uses the same version. A compiler plugin, annotation processor, or test runner may be compatible with one JDK but incompatible with another JDK.

### 2.2. Resolution differences between Gradle and Maven

**Gradle** typically uses rule/metadata-based version selection and conflict resolution; when multiple compatible version requests exist, the default usually prefers the higher version unless adjusted by constraints, capabilities, or other rules. The actual mechanism also depends on the platform, metadata, and how dependencies are declared.

**Maven** typically uses **nearest definition** dependency mediation: a dependency closer to the root in the graph may be selected; at the same depth, declaration order can take effect. `dependencyManagement` can govern the version used when a dependency is referenced.

Example:

```text
app
  +-- A:1.0 -> X:1.5
  +-- B:1.0 -> X:2.0
```

Do not assume the two build tools will definitely yield the same version of `X`. Run a dependency graph report using the exact tool and version being used.

### 2.3. The resolved graph is the actual input

When encountering `NoSuchMethodError`, `ClassNotFoundException`, or `UnsupportedClassVersionError`, information in source declarations is not enough. You must know:

- Which module and version are actually on the classpath.
- Which version was replaced by conflict resolution.
- Which dependency branch brought that module in.
- Which repository supplied the actual artifact.
- Whether compile and runtime selected the same version.
- Which minimum class-file version/JDK the new module requires.

A dependency graph stored in CI alongside build metadata helps reproduce errors and reliably supports rollback.

## 3. Version constraints are policy, not a lockfile

### 3.1. Fixed versions, dynamic versions, and version ranges

Some declaration styles:

| Style | Example | Meaning |
|---|---|---|
| Fixed version | `2.3.4` | Requests a specific version in the declaration, yet resolution is still subject to conflict rules |
| Gradle dynamic version | `2.+` or `latest.release` | Can pick a newer version when metadata changes |
| Version range | `[2.0,3.0)` | Allows a range of versions |
| Changing module | `2.3.4-SNAPSHOT` or a module marked changing | Artifact/metadata may change even though the identifier does not |
| Strict constraint | `strictly("2.3.4")` in Gradle | Strictly restricts acceptable versions |
| Preferred version | `prefer("2.3.4")` in Gradle | Expresses preference, though stronger requirements can override it |

A version string that looks fixed does not guarantee a fixed result: if a repository allows overwriting artifacts at the same version, the same coordinates can still receive different bytes. Conversely, a dependency using a range can still be selected consistently thanks to a lockfile, until the lock is updated by a controlled process.

### 3.2. SemVer is only a publisher's promise

A library versioned `2.3.4` under Semantic Versioning may promise that patch releases do not break the API. However:

- Not every library applies SemVer strictly.
- "Not breaking the API" may refer only to source compatibility, excluding Java serialization, bytecode, configuration, or behavior.
- A minor release may raise the minimum JDK.
- A new dependency release may change native libraries or module metadata.
- A bug fix may impact business logic that depends on old behavior.

Treat versioning as a useful signal; only testing and specific compatibility contracts reveal whether a build fits your project's migration.

## 4. Constraints in Gradle

### 4.1. Declaring constraints for transitive dependencies

In a Gradle module using the Groovy DSL:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'com.example:application-client:4.0.0'

    constraints {
        implementation('org.example:json-core') {
            version {
                strictly('2.4.3')
            }
            because 'Phiên bản này đã được kiểm thử với JDK mục tiêu'
        }
    }
}
```

`constraints` specifies version selection rules when the `org.example:json-core` module participates in a configuration. A constraint does not add that dependency to the classpath on its own if nothing requests it. It is a policy for the graph, not necessarily a new direct dependency.

`strictly` can cause resolution to fail when another module requires an incompatible version. This is sometimes the right outcome: instead of silently picking an untested version, the build reports the conflict for the developer to decide.

### 4.2. How prefer, require, and strictly differ

Gradle rich version constraints can express multiple levels of policy. Illustrative example:

```groovy
dependencies {
    constraints {
        implementation('org.example:codec') {
            version {
                require('[3.1,4.0)')
                prefer('3.4.2')
                reject('3.2.0')
            }
            because 'Chỉ dùng nhánh 3.x đã được xác nhận'
        }
    }
}
```

General meaning:

- `require` sets a version requirement, which may allow conflict resolution to select a higher version when compatible.
- `prefer` expresses a desired version without the same binding strength as strict.
- `strictly` limits acceptable versions, making conflicts surface more visibly.
- `reject` excludes one or more disallowed versions.

These declarations can be combined according to the Gradle syntax in use, but avoid overusing complex rules without a clear business or compatibility reason.

### 4.3. Force should not be the first reflex

Some projects use:

```groovy
configurations.configureEach {
    resolutionStrategy {
        force 'org.example:json-core:2.4.3'
    }
}
```

`force` can force the version selection outcome, but it can also hide the real needs of other dependencies and push conflicts out of sight.

During migration, prioritize:

1. Inspecting the path bringing the dependency in.
2. Understanding why modules require different versions.
3. Selecting supported versions according to the compatibility matrix.
4. Using BOMs/platforms and constraints with clear justification.
5. Using force only with a tested decision and documenting how to remove it.

Do not use `force` to fix `NoSuchMethodError` without verifying the binary compatibility of callers.

### 4.4. Constraints do not replace a version lock

Suppose only the range `[2.0,3.0)` is declared. Today Gradle picks `2.4.3`; after the repository publishes `2.5.0`, a new resolution may pick a different version. A lockfile records the chosen **result** so subsequent builds do not accidentally self-update.

This is why version policy and dependency locking must be combined.

## 5. Gradle platforms, BOMs, and alignment

### 5.1. Using a platform for a module family

When a library consists of multiple artifacts that must use mutually compatible versions, consider a BOM or platform.

Example:

```groovy
dependencies {
    implementation platform('org.example:framework-bom:5.2.0')

    implementation 'org.example:framework-core'
    implementation 'org.example:framework-http'
    implementation 'org.example:framework-json'
}
```

`platform` lets you import dependency constraints from a BOM. If the BOM manages module versions, consumers can omit specific versions in individual dependency declarations.

Benefits:

- Avoids having the core module on one version and the HTTP module on another.
- Simplifies upgrading a dependency family.
- Propagates version policy to related modules.
- Makes it easy to see which BOM version was selected for the migration.

However, a BOM does not prove that transitive dependencies outside the BOM are safe with a new JDK.

### 5.2. `platform` and `enforcedPlatform`

In Gradle, `enforcedPlatform` expresses a stronger requirement and can affect consumers of a library when published. This is not the right default choice for every library.

Example:

```groovy
dependencies {
    implementation enforcedPlatform(
        'org.example:framework-bom:5.2.0'
    )
}
```

If a project is a library consumed by many applications, enforcing versions across an entire module family can reduce consumer choices. Prefer `platform` and appropriate constraints, using `enforcedPlatform` only once you understand the consequences on consumer graphs.

### 5.3. Platforms do not solve every kind of conflict

Libraries can carry capability metadata, variants, native classifiers, or different JVM target requirements. Aligning versions does not guarantee all variants are compatible.

When upgrading the JDK, inspect:

- Module metadata and Gradle attributes.
- JVM target of artifacts.
- Optional dependencies and annotation processors.
- Native classifiers for OS/architecture.
- Removed or relocated APIs across modules.
- Runtime configurations, not just compile configurations.

## 6. Version catalogs: an easy-to-manage declaration location, not a lock

A Gradle version catalog is typically placed at `gradle/libs.versions.toml`:

```toml
[versions]
framework = "5.2.0"
json = "2.4.3"
junit = "5.11.0"

[libraries]
framework-core = { module = "org.example:framework-core", version.ref = "framework" }
json-core = { module = "org.example:json-core", version.ref = "json" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }

[plugins]
# Plugin versions can be managed separately here.
```

In the build file:

```groovy
dependencies {
    implementation libs.framework.core
    implementation libs.json.core
    testImplementation libs.junit.jupiter
}
```

Catalogs help unify declarations in multi-project builds and reduce duplicate version literals. However:

- A catalog does not lock every transitive dependency.
- A catalog does not record the resolved graph per configuration.
- A catalog does not guarantee a repository will not swap bytes.
- A catalog does not automatically lock the Gradle distribution/JDK/build plugins.
- Updating only the catalog without updating locks can create conflicts under locking policies.

Treat catalogs, BOMs, and lockfiles as three complementary layers rather than mutually exclusive replacements.

## 7. Dependency locking in Gradle

### 7.1. Lockfiles preserve resolution results

Gradle provides dependency locking to record resolved versions and use them in subsequent resolutions. This is especially important if dynamic dependencies remain or the graph shifts across build tool versions.

Groovy DSL example:

```groovy
plugins {
    id 'java'
}

dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation 'org.example:business-client:4.0.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

The example above applies locking to the corresponding configurations when resolved; configurations not resolved during lock generation may require a separate step. Lockfile contents and how locking is enabled may vary across Gradle versions. Do not assume every configuration is locked simply because the block above is present.

### 7.2. Generating lockfiles

A common flow:

```shell
./gradlew :app:dependencies --configuration runtimeClasspath --write-locks
```

In the example configuration, Gradle resolves `runtimeClasspath` and can write or update lock state for resolved configurations. If you want to lock compile/test/annotation processor or other configurations, run tasks that resolve them according to your chosen strategy.

In a multi-project build, establish a standardized step to generate/update locks for key projects and configurations. Modern lockfiles may be named `gradle.lockfile` in each project depending on the Gradle version and configuration.

**Do not manually edit entire lockfiles using find/replace.** Use the official resolution mechanism to change the graph and then review the diff.

### 7.3. Reading a lockfile properly

A lockfile contains the set of module versions selected for the locked scope, not a copy of all JARs. Illustrative example:

```text
org.example:business-client:4.0.0=runtimeClasspath
org.example:json-core:2.4.3=runtimeClasspath
empty=testCompileClasspath
```

This is only an example of expressing lock state; the exact format and content belong to the Gradle version. When encountering an `empty` state or configuration name in the file, interpret it according to the tool's locking mechanism rather than treating it as a dependency.

Do not infer from a lockfile that **artifact bytes** have been verified. Dependency verification or appropriate checksums/signatures are still required.

### 7.4. Controlled dependency updates

When wanting to upgrade a specific module, Gradle supports selective lock updates, for example:

```shell
./gradlew :app:dependencies \
    --configuration runtimeClasspath \
    --update-locks org.example:json-core
```

The example uses Unix shell line continuation characters. On Windows PowerShell, run a single-line command or use appropriate line continuation syntax.

If the module gets a new version selected, the lock diff shows the changes produced by resolution. Other transitive dependency changes may occur; review the entire diff, not just the primary module line.

A sensible upgrade process:

1. Create a branch modifying dependency and version declarations.
2. Run resolution to intentionally update locks.
3. Inspect the diff in the lockfile.
4. Check licenses, CVEs, release notes, and compatibility.
5. Run unit/integration tests and test on the target JDK.
6. Commit declarations, lockfiles, and related metadata in a single change.

### 7.5. Locks must be committed

If every developer keeps lockfiles locally and fails to commit them, CI will not have the same set of dependencies. Put lockfiles under version control alongside build scripts and the version catalog.

A lock diff is not meaningless noise: it is proof that the resolved graph changed. During code review, ask:

- Why did this version change?
- Is this a security patch or a major/minor upgrade?
- Which transitive modules came along?
- Does the new version support the target JDK?
- Did any artifact change metadata or classifiers?
- Are there related tests and a rollback path?

### 7.6. Locks have scope limits

Gradle dependency locking does not automatically imply that all build inputs are immutable. Examine separately:

- Plugin versions and plugin resolution.
- Buildscript classpath/custom plugin builds.
- Toolchains/JDK distribution.
- Gradle Wrapper version.
- Native toolchains and other compilers.
- Remote data or code generation fetched directly via URL.
- Generated artifacts and annotation processors.
- Environment variables and timestamps.
- Whether repositories allow overwriting the same version.

Scopes outside the locked graph must be managed with separate policies.

## 8. Maven: dependencyManagement, BOMs, and explicit versions

### 8.1. Maven has no native lockfile equivalent to Gradle by default

In Maven, common strategies to control versions include:

- Pinning versions of direct dependencies.
- Using `dependencyManagement` in a parent POM.
- Importing a BOM.
- Using Maven Enforcer rules.
- Recording the dependency tree/effective POM for auditing.
- Using extensions/plugins if the organization requires dependency locking with specific behavior.

Do not present `dependencyManagement` as an absolute dependency lock. It manages the version policy of referenced artifacts, yet build results can still be affected by changes in POMs, dependency ranges, SNAPSHOTs, plugins, repositories, and the environment.

### 8.2. Configuring dependencyManagement

Example POM with pinned versions:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>json-core</artifactId>
      <version>2.4.3</version>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>json-core</artifactId>
  </dependency>
</dependencies>
```

`dependencyManagement` selects the version when the module is brought into the dependency graph. It does not automatically add the `json-core` module to the application just because an entry exists in the managed block.

If a JDK upgrade requires `json-core:2.5.0`, you can update the managed version and run regression tests. However, check whether other dependencies require different APIs.

### 8.3. Importing a Maven BOM

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>platform-bom</artifactId>
      <version>5.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```

A BOM can centralize versions tested together. When upgrading from one framework line to another, swapping the BOM is usually clearer than editing dozens of individual libraries.

Still, a BOM needs to be combined with:

- Inspecting the dependency tree.
- Pinning plugin versions.
- Toolchain/JDK policy.
- Checking artifact integrity.
- Build reproducibility and compatibility tests.

### 8.4. Nearest-wins can bring surprises

In Maven, if two branches bring in different versions of a transitive dependency, mediation may choose the version based on distance to the root. Adding a direct dependency or changing order in the POM can change the outcome in an equal-depth scenario.

To diagnose:

```shell
mvn dependency:tree
```

Filters and verbose output can be used depending on the Maven Dependency Plugin version. Pin the plugin version in official builds, since shorthand invocations like the one above may depend on environment plugin resolution.

Do not treat the dependency tree as merely a reference file; it reflects the intended classpath and must be reviewed when switching Java versions.

## 9. Maven Enforcer and checking dependency convergence

### 9.1. Why fail instead of "if it builds, it's enough"?

A dependency graph with two conflicting versions may still resolve to one version and compile successfully. Yet binary compatibility errors only surface at runtime.

The Maven Enforcer Plugin can help block unwanted configurations using rules such as:

- `dependencyConvergence`: detects paths bringing different versions of the same dependency into the graph.
- `requireUpperBoundDeps`: verifies that selected versions meet upper-bound constraints.
- `requireMavenVersion`: controls the minimum Maven version.
- `requireJavaVersion`: requires a certain JDK range.
- Other rules from organization-approved plugins or extensions.

An example configuration:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.5.0</version>
      <executions>
        <execution>
          <id>enforce-dependencies</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <dependencyConvergence/>
              <requireUpperBoundDeps/>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

The version in the example is solely to illustrate syntax; the project must use its chosen plugin version and test it against real builds. Rules may fail on the current graph and require remediation; do not disable them en masse just to turn CI green.

### 9.2. Enforcer does not replace testing

A graph that converges on a single version can still be incompatible:

- The JAR contains bytecode too new for an older JDK.
- Methods/constructors have been removed.
- Module encapsulation causes reflection to fail.
- A native dependency lacks a matching classifier.
- Default configurations or serialization behavior changed.

Enforcer is a gate for dependency policy. Compatibility testing is a separate gate.

### 9.3. Plugin versions also need pinning

Example configuration:

```xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

Control the plugins actually used during the lifecycle. Configuration under `pluginManagement` is where versions/configs are managed; not every plugin placed there is automatically executed.

## 10. Dynamic versions and SNAPSHOTs: sources of non-repeatable builds

### 10.1. Gradle dynamic versions

A declaration:

```groovy
dependencies {
    implementation 'org.example:codec:2.+'
}
```

lets Gradle pick the latest matching release in a group, subject to caching and current metadata. When the repository updates, the same commit can resolve to a different version.

Dynamic versions can be useful in experiments or certain automated update workflows, but are not suitable as a default policy for releases without locks and review.

### 10.2. Maven version ranges

Maven has version range syntax such as:

```xml
<dependency>
  <groupId>org.example</groupId>
  <artifactId>codec</artifactId>
  <version>[2.0,3.0)</version>
</dependency>
```

If the repository publishes another matching version, resolution results can change. For release builds requiring traceability, usually choose a specific version and perform reviewed upgrades.

### 10.3. SNAPSHOT and changing modules

`1.0-SNAPSHOT` in Maven or a dependency marked changing in Gradle can represent an artifact rebuilt multiple times under the same logical version.

This causes:

- Updated snapshot metadata.
- Artifacts with the same logical version yet different bytes.
- Cache differences across machines/CI.
- Hard-to-trace rollbacks.
- Passing tests today not guaranteeing the same artifact tomorrow.

In production releases, prefer immutable versions/digests. If using SNAPSHOTs for development, clearly separate snapshot and release pipelines, and do not promote snapshots as long-term reproducible releases.

### 10.4. Caches can hide changes

Gradle, Maven, and repository proxies have metadata/artifact caching mechanisms. Two build machines can receive different results because:

- One machine cached a previous version.
- One machine hit a fresh repository.
- Dynamic version metadata cache expired.
- A proxy mirror synchronized slowly.
- CI has offline mode enabled or an old local repository.

A build that happens to succeed thanks to cache does not prove dependency resolution is deterministic. When investigating, compare the resolved graph, repository sources, checksums, and cache state; do not simply wipe the entire cache and ignore the root cause.

## 11. Repository and artifact immutability

### 11.1. One set of coordinates must identify one release content

A Maven artifact is typically identified by:

```text
groupId:artifactId:version[:classifier][@extension]
```

If a release repository allows overwriting `org.example:codec:2.4.3` with new bytes, a lockfile preserving the same version still does not guarantee downloading the same content as before. That is why an **immutable release artifacts** policy is critical.

What is needed:

- Do not overwrite release versions.
- Verify checksums/signatures if infrastructure supports it.
- Restrict publish permissions.
- Maintain auditing and provenance of build sources.
- Use a managed repository proxy/mirror.
- Preserve original artifacts of critical releases.

### 11.2. Repository order can change results

A project may use both public and private repositories:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/releases')
    }
    mavenCentral()
}
```

If the same artifact coordinates appear in multiple repositories with different content, the build tool's repository selection rules and metadata become critical. Clearly define the origin for internal artifacts, avoid public namespace collisions, and apply repository content filters where appropriate.

The `example.invalid` URL is only an illustrative address. Real systems must enforce TLS, credentials, and access control.

### 11.3. Dependency confusion is not solved by locking alone

A lockfile can record a version, yet is insufficient to guarantee the artifact comes from a trusted repository. If an attacker publishes a package with the same name/coordinates into a source prioritized by the build, or if a repository is misconfigured, supply chain risk remains.

Measures can include:

- Clear internal group namespaces.
- Repository content policies.
- Artifact verification via checksum/signature/trust policy.
- Managed private repositories.
- Preventing CI from arbitrary publishing rights.
- Release SBOM and provenance.

## 12. Dependency verification differs from dependency locking

### 12.1. Version locks do not verify bytes

Two builds may both resolve `org.example:codec:2.4.3` yet download different JARs if upstream is overwritten or the repository is tampered with. A lockfile only controls **version resolution**, not byte-level binary contents.

Gradle supports dependency verification via metadata, which can include checksums and signatures. An illustrative workflow:

```shell
./gradlew --write-verification-metadata sha256 help
```

Depending on configuration and resolved dependencies, the tool may generate a metadata file such as `gradle/verification-metadata.xml`. Afterwards, review whether the sources and checksums are genuinely trustworthy before committing.

**Warning:** do not automatically run the verification metadata generation command and blindly accept every checksum freshly downloaded from an unverified source. That only records the current state rather than creating trust out of thin air.

### 12.2. Maven and artifact verification

Maven uses repository metadata and has checksum policies, though the level of assurance varies depending on repository/client configuration and how checksum failures are handled. An organization needing high assurance can use a repository manager, signature verification, artifact checking policies, and dedicated provenance.

Do not claim that fixed POM versions alone protect the supply chain.

### 12.3. Ordering of assurance layers

```text
Version declaration / BOM
          |
          v
Version constraints
          |
          v
Resolved dependency graph
          |
          v
Lockfile
          |
          v
Artifact checksum/signature verification
          |
          v
Pinned build tool + JDK + environment
          |
          v
Reproducible archive + compatibility tests
```

Each layer reduces a different kind of variation or risk. No single layer can replace all the others.

## 13. Build reproducibility has multiple levels

### 13.1. Repeatable dependency resolution

A build can be called "dependency resolution repeatable" when the same declarations/locks and repository policy select the same set of module versions.

This is a necessary condition, yet not sufficient for **byte-for-byte reproducibility**.

### 13.2. Repeatable build environment

Things to control:

- JDK vendor and version/patch level.
- Java toolchains for compilers and test runtimes.
- Gradle/Maven Wrapper or the Maven version supplied by CI.
- OS/architecture and native tools.
- Locale, timezone, and file encoding.
- Environment variables affecting the build.
- Plugin versions and external generators.
- System properties injected into compilation/packaging.
- Remote inputs and system clock time.
- Repository mirrors and dependency caches.

A JDK upgrade can change `javac` output, warnings, generated metadata, or tool behavior even when the dependency graph stays unchanged.

### 13.3. Byte-for-byte reproducible artifacts

Two builds from the same inputs are considered artifact-reproducible if the output files have identical bytes (within the declared scope).

For JAR/ZIP archives, common sources of drift include:

- Timestamps of archive entries.
- File ordering inside the JAR.
- Generated manifests.
- Build timestamps/hostnames in resources.
- Unstable iteration order of maps.
- Non-deterministic code generators.
- Unpinned commit information.
- Differences across JDK compiler/archiver versions.

The goal is not merely two files that execute identically, but being able to compute identical checksums and accurately trace artifact provenance.

### 13.4. Reproducible does not imply deterministic runtime

Two JARs with identical bytes can still behave differently if:

- The OS or native libraries differ.
- Clock time, locale, or timezone differ.
- External APIs/servers return different results.
- Thread scheduling and concurrency differ.
- JVM flags or GC configuration differ.
- Production data differs.

Therefore, reproducible builds aid diagnostics and the supply chain, while runtime compatibility still requires testing and operational observability.

## 14. Creating reproducible archives with Gradle

A common Groovy DSL configuration:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Two ideas:

- Do not retain individual file source timestamps as a factor varying the archive.
- Use a stable entry order inside the archive.

Depending on the Gradle version, some behaviors may already have suitable defaults, though explicit configuration helps express the policy.

Still inspect tasks that generate resources or manifests. If a task generates `build-info.properties` containing the current timestamp, the JAR bytes will differ even when ZIP timestamps and entry order are stabilized.

An example that easily breaks reproducibility:

```groovy
tasks.register('generateBuildInfo') {
    doLast {
        file("$buildDir/generated/build-info.txt")
            .text = "builtAt=" + System.currentTimeMillis()
    }
}
```

The illustrative snippet points out a cause of variation, **not a recommended configuration**. If a build timestamp is genuinely needed, define how that data is used in release provenance outside the JAR or establish a clear policy for rebuilding.

## 15. Maven and reproducible builds

Maven supports several techniques for creating reproducible archives, though plugins/archivers and sources of variation must be controlled.

A commonly used property:

```xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

This property is used by supporting plugins/archivers to fix the timestamps of ZIP/JAR entries; there is no guarantee every plugin in the build reads that property.

In real builds, the value can be bound to a timestamp controlled by the source/release process rather than the "current" timestamp of each build.

Points to manage:

- Versions of `maven-jar-plugin` and packaging plugins.
- Version of `maven-compiler-plugin`.
- Generated sources/resources having stable ordering.
- Manifest metadata, timestamps, and file order.
- Runtime JDK used by Maven.
- Repository release immutability.
- Plugin dependencies and extensions.

Do not merely set `outputTimestamp` and claim the entire build is guaranteed to be reproducible across every operating system.

## 16. Pinning build tools and Java toolchains

### 16.1. Gradle Wrapper

A Gradle project should commit wrapper files and control the Gradle distribution version. This avoids situations where a personal machine uses Gradle 8.x while CI uses 9.x.

Common launch command:

```shell
./gradlew build
```

On Windows:

```text
gradlew.bat build
```

The wrapper controls which Gradle distribution is downloaded per configuration, yet you still need to verify the source and distribution integrity per policy. The Gradle Wrapper does not automatically pin the JDK running the daemon or compile/test toolchains.

### 16.2. Gradle Java Toolchains

Example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

This pattern illustrates using the compiler from a Java 21 toolchain while targeting the Java 17 API/class-file level for Java sources where appropriate. To truly support Java 17, you must check runtime dependencies, annotation processors, and tests on Java 17. `options.release` does not make external libraries Java 17 compatible on its own.

Toolchain resolution can select different JDK vendors or patch levels if no policy exists. For strict reproducibility, specify the vendor/version and how CI supplies the JDK.

### 16.3. Maven Toolchains and Compiler Plugin

In Maven, `maven-toolchains-plugin` and compiler configuration can help decouple the JDK running Maven from the JDK used to compile. `maven-compiler-plugin` supports `release` when the corresponding toolchain/compiler allows it.

Illustrative example:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

This constrains the API/bytecode target of Java sources within the scope supported by the compiler plugin. It **does not lock transitive dependencies**, does not ensure Maven automatically picks the right JDK if toolchains are unconfigured, and does not replace runtime tests.

### 16.4. Maven Wrapper

A Maven project can use Maven Wrapper to pin the Maven distribution. CI should use the managed wrapper command:

```shell
./mvnw verify
```

If not using the wrapper, pin the Maven version via the CI image or build environment configuration. When upgrading the JDK, confirm that both the Maven/Gradle version and plugins support the new JDK.

## 17. Dependency locking in multi-project setups and microservices

### 17.1. Multi-project Gradle

In a monorepo:

```text
root/
  settings.gradle
  build.gradle
  gradle/libs.versions.toml
  core/
  api/
  worker/
  integration-tests/
```

Subprojects can share constraints, a version catalog, and a BOM. Yet resolved graphs can still differ by configuration.

Decisions to make:

- Lockfiles in which projects?
- Which configurations are locked?
- Which task generates locks in CI?
- How to handle a subproject resolved only when running integration tests?
- Does plugin management have its own version policy?
- Are there independent included/composite builds needing separate locks?

Do not take the lockfile of the `api` module and deduce that `worker` uses the exact same versions. Two modules can have different runtime dependencies.

### 17.2. Microservices do not need to force the same graph

Two independently deployed services can share a baseline BOM, yet do not necessarily need to lock all modules to identical versions. If one service needs to upgrade a library for JDK 21 while another remains on JDK 17, forcing the whole system onto a single version can cause regressions.

Distinguish:

- **Platform policy:** minimum/allowed versions and compatible library sets.
- **Service lock:** resolved graph of each individual deployable artifact.
- **Release artifact:** specific tested JAR/container image.
- **Compatibility contract:** API/protocol between services.

Service-level version locking keeps rollbacks traceable without forcing every service to deploy in lockstep.

### 17.3. Shared libraries and transitive APIs

A library can inadvertently expose types from a dependency through its public API:

```java
public interface Exporter {
    org.example.json.JsonNode export();
}
```

When upgrading `org.example.json`, this is no longer just an implementation dependency change. Consumers may compile against the public dependency type and suffer binary/source compatibility impact.

If a dependency is only used inside the implementation, avoid leaking its types into the public API. With Gradle `java-library`, distinguishing `api` and `implementation` helps express that.

## 18. JDK migration: dependency upgrades must be strategic

### 18.1. Why changing the JDK first is not enough

Upgrading JDK 8 to 17, 21, or 25 can affect:

- Bytecode target and compiler plugins.
- Frameworks relying on JDK internals.
- Reflection and module encapsulation.
- Jakarta/Java EE APIs that changed or are no longer bundled with the JDK.
- Annotation processors and bytecode manipulation.
- GC, TLS, crypto providers, and security defaults.
- JNI/native dependencies and platform classifiers.
- Test runners, build plugins, and Java agents.

A dependency graph locked years ago may reproduce bugs very well, yet does not automatically make the application run on the new JDK.

### 18.2. Establishing two baselines

Store at least:

| Baseline | JDK | Dependency graph | Purpose |
|---|---|---|---|
| Legacy baseline | Currently stable JDK | Current lock/dependency report | Reference point when regressions occur |
| Target baseline | Target JDK | Controlled upgraded graph | Intended release configuration |

Also save plugin/build-tool versions, CI image, JVM flags, and smoke test results for comparison.

### 18.3. Upgrading in groups rather than all at once

A possible sequence:

1. Upgrade the build tool and compiler plugins to versions supporting the target JDK.
2. Identify critical dependencies: framework, ORM, JSON, logging, security, bytecode, JDBC, and test tooling.
3. Use a BOM/platform or dependencyManagement to align by family.
4. Upgrade libraries that require changes due to JDK incompatibility.
5. Update the lockfile/graph and review transitive changes.
6. Run compile/tests on old and new JDKs if both remain within the support window.
7. Add integration tests for changed behaviors.
8. Release as canary and monitor runtime errors.
9. Switch baselines once stabilized.

There is no need to follow the exact same order for every project; the principle is limiting change size and maintaining explainability for every regression.

### 18.4. Do not retain vulnerable dependencies just because of a lockfile

A lockfile is evidence of selected versions, not a promise that they are never allowed to change. Have a security update process:

- SCA and advisory monitoring scoped to dependencies.
- Create issues/PRs when CVEs or end-of-support affect locked versions.
- Review compatibility and run tests.
- Update locks in controlled batches.
- Document the reason and timing of upgrades.
- Maintain an exception policy when upgrades cannot happen immediately, with mitigations and expiry.

Locks should enable controlled change, not become a barrier keeping the project forever on unsupported libraries.

## 19. Diagnosing the dependency graph in Gradle

### 19.1. Viewing all dependencies by configuration

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
```

This report shows dependency trees and resolved versions for the runtime configuration. The command is not equivalent to reports for compile, test, or annotation processors.

### 19.2. Explaining why a version was selected

```shell
./gradlew :app:dependencyInsight \
    --dependency json-core \
    --configuration runtimeClasspath
```

The `dependencyInsight` report can show request paths to the dependency and reasons for version selection depending on Gradle version/metadata.

During migration, this is often a better tool than just reading `build.gradle` because conflict resolution can change versions declared in transitive dependencies.

### 19.3. When lockfiles and declarations conflict

A common error:

```text
Version declaration updated
          |
          v
Lockfile still holds old version
          |
          v
Resolution does not match lock policy
```

Do not resolve this by deleting the lockfile and committing a new file without viewing the diff. Identify which dependency was intentionally upgraded and update the lock per process.

If a lock was generated in an old environment yet runs on a new OS/JDK, configurations may pick different variants or include conditional dependencies. Check the lock scope and platform-specific artifacts instead of assuming the tool malfunctioned.

## 20. Diagnosing the dependency graph in Maven

### 20.1. Dependency tree

```shell
mvn dependency:tree
```

Inspect paths to target dependencies, selected versions, and modules omitted due to conflicts depending on output mode/plugin version.

### 20.2. Effective POM

```shell
mvn help:effective-pom
```

The Effective POM helps determine the resulting configuration after combining parent, profiles, and dependencyManagement. However, it does not replace the dependency tree: the two reports answer different questions.

### 20.3. Profiles and environment

Maven profiles can be activated based on JDK, OS, properties, or other conditions. The same commit can yield different dependencies when switching JDKs.

For example, `activation` configuration by JDK can activate a profile on JDK 21 while leaving it inactive on JDK 17. In that case, the source POM does not change yet the resolved graph differs.

During migration, list active profiles:

```shell
mvn help:active-profiles
```

When building releases, record profile flags and environment variables controlling resolution. Do not assume the root POM is the entirety of the applied configuration.

## 21. Common errors and classification

### Error 1: Rerunning an old build yields a new dependency version

**Symptom:** the same commit produces different dependency trees or introduces incompatible APIs.

**Cause:** dynamic versions/ranges, SNAPSHOTs, mutable artifacts, or differing metadata caches.

**Resolution:** pin versions per policy, generate/update locks, control repositories, and store the resolved graph.

### Error 2: Compilation succeeds, yet runtime throws `NoSuchMethodError`

**Symptom:** the class is present, yet the method called by code does not exist at runtime.

**Possible cause:** compile and runtime classpaths selected different versions, or a transitive library is binary-incompatible.

**Resolution:** compare compile/runtime graphs, use `dependencyInsight` or `dependency:tree`, and verify actual versions inside deployed artifacts. Do not merely add a strong constraint without identifying which API callers need.

### Error 3: `UnsupportedClassVersionError` after a dependency upgrade

**Symptom:** an older runtime JDK cannot load classes of the new library.

**Cause:** the dependency was built with a class-file version requiring a higher JDK.

**Resolution:** check release notes, dependency metadata, and support matrices; pick a version compatible with the committed runtime or upgrade the runtime as planned.

### Error 4: Lockfile changes too extensively after a small PR

**Symptom:** a single direct dependency upgrade alters dozens of other modules.

**Possible cause:** a new BOM, dynamic versions, changed metadata, or a newly resolved configuration.

**Resolution:** review each group of changes; check platforms, repositories, and lock scopes. Split large upgrades into purposeful PRs if needed.

### Error 5: Lockfile does not prevent JAR byte differences

**Symptom:** same coordinates/version yet checksums on two machines mismatch.

**Cause:** repository allows overwrites, different caches/proxies, or tampered artifact source.

**Resolution:** immutable repositories, verification metadata, checksum/signature policies, and publish auditing. Version locking alone is not enough.

### Error 6: Maven build output changes when reordering dependencies

**Symptom:** a transitive dependency resolves differently even though direct versions barely changed.

**Cause:** Maven mediation and dependency graph structure.

**Resolution:** use dependencyManagement/BOMs to clarify versions and verify the dependency tree in CI.

### Error 7: Same dependency graph yet different JAR checksums

**Symptom:** identical dependencies, different build output.

**Cause:** timestamps, file ordering, generated content, toolchains, or OS/locale.

**Resolution:** configure reproducible archives, pin the build tool/JDK, remove nondeterministic inputs, and compare artifacts in a controlled environment.

### Error 8: A "safe" locked build receives vulnerability alerts

**Symptom:** SCA detects a dependency with a CVE even though the graph did not change.

**Cause:** version locking only controls change, not security posture.

**Resolution:** update per advisories and compatibility tests, adding mitigations if an upgrade cannot proceed yet.

### Error 9: Private repository replaced by an identically named artifact in a public repo

**Symptom:** the build pulls an unexpected package with wrong checksum or behavior.

**Cause:** repository ordering/content policy and namespace collisions.

**Resolution:** filter repositories by group, use trusted mirrors and artifact verification, and check provenance.

### Error 10: One OS resolves a different native artifact than another OS

**Symptom:** runs on Windows but fails on Linux due to missing native binary or different classifier.

**Cause:** dependencies have platform-specific variants or native classifiers.

**Resolution:** inspect graphs per OS/architecture, pin toolchains, and test packaging/running the real artifact. Lockfiles need to support committed variants, not just a developer's machine.

## 22. Controlling upgrades via pull requests

A dependency upgrade should include enough description for reviewers to understand the change:

```text
Dependency: org.example:json-core
Old version: 2.4.3
New version: 2.5.1

Reason:
- Documented bug fix / target JDK support

Direct and transitive changes:
- List from lock diff or dependency tree

Compatibility:
- Minimum JDK:
- Source/binary/config/serialization notes:
- Affected modules:

Validation:
- Unit tests:
- Integration tests:
- JDK matrix:
- Smoke test:

Release:
- Canary plan:
- Rollback artifact:
- Owner:
```

Not every small change requires lengthy documentation, yet core dependencies such as frameworks, serializers, ORMs, crypto, JDBC drivers, bytecode tools, and Java agents should have a higher level of control.

### 22.1. Do not auto-update locks without review

A bot can propose PRs updating versions and lockfiles. This is a useful workflow if CI:

- Allows only defined changesets.
- Clearly displays transitive diffs.
- Runs builds/tests on the target JDK.
- Runs license and security checks.
- Requires reviewers for critical dependencies.
- Does not auto-merge major releases without a compatibility plan.

Automation reduces repetitive work; it does not replace compatibility decisions.

### 22.2. Periodic lock refresh

If a project does not use dynamic dependencies and all versions are pinned, a lock refresh is still useful when adding/removing modules or changing BOMs. With dynamic dependencies, schedule controlled updates instead of letting them change arbitrarily per build.

A sensible workflow is "one separate PR per dependency change containing the lock diff", paired with periodic security reviews. There is no need to modify locks daily if the graph has not changed.

## 23. Recommended CI process for reproducible builds

A pipeline can be structured as:

```text
Checkout immutable commit
           |
           v
Pin JDK + Gradle/Maven distribution
           |
           v
Load trusted repositories and credentials
           |
           v
Resolve dependencies under version policy + lock
           |
           v
Verify artifact checksums/signatures
           |
           v
Compile + test (JDK compatibility matrix)
           |
           v
Package deterministic JAR/image
           |
           v
Generate dependency graph / SBOM / provenance
           |
           v
Publish immutable artifact
           |
           v
Smoke test + rollout
```

Define where secrets are supplied: credentials for downloading private dependencies, signing keys, and publish tokens must not be stored in the repository or printed into logs.

### 23.1. CI gate for lockfiles

If using Gradle locking, release pipelines can run resolution using the exact committed lockfile and reject unexpected changes. Do not let release pipelines automatically rewrite lockfiles and silently use the new result.

A valid upgrade must appear in a PR modifying source/build files, be reviewed, and pass tests.

### 23.2. CI gate for dependency graphs

Store the dependency graph or SBOM alongside the release artifact to answer questions:

- Which version of `json-core` does this production artifact contain?
- Did that version come from a direct or transitive dependency?
- Are multiple versions of the same library packaged into the fat JAR?
- Was any module added without reviewers noticing?
- Which releases are affected by a newly disclosed CVE?

An SBOM is an inventory; it does not prevent vulnerabilities on its own. Yet a reliable inventory speeds up impact assessment and remediation planning.

### 23.3. CI gate for reproducibility

For a critical release, build twice in a controlled environment and compare SHA-256 of artifacts. If they differ, analyze timestamps, file ordering, generated resources, JDK/toolchains, and sources of nondeterminism.

Byte equality across different OSes is not strictly required if the product intentionally has OS-specific artifacts. What matters is stating the reproducibility scope clearly: same commit, same dependency graph, same toolchain/OS, and same build configuration.

## 24. Case study: migrating Java 17 to 21

A service has:

```groovy
dependencies {
    implementation 'org.example:legacy-http-client:3.+'
    implementation 'org.example:json-core:2.2.0'
    testImplementation 'org.example:testkit:1.8.0'
}
```

When moving to JDK 21, CI builds occasionally encounter API errors in `legacy-http-client`. Solve in sequence:

1. Record the specific version of every dependency resolved when the error occurred.
2. Use `dependencyInsight` to find branches requiring `legacy-http-client` and its transitive dependencies.
3. Identify the library version supported by the vendor on JDK 21.
4. Replace `3.+` with a version or constraint having an explicit policy.
5. Align the BOM/platform if the library belongs to a dependency family.
6. Enable locking for critical configurations and generate the lockfile.
7. Commit the lockfile alongside version declaration changes.
8. Verify artifact integrity from trusted repositories.
9. Run tests on JDK 17/21 if still committing to both.
10. Produce an immutable release artifact and archive the graph, checksums, and toolchain metadata.
11. Test rollback and monitor runtime errors in canary.

If during a dependency upgrade, the new library requires Java 21 while the application still has to run on Java 17, you cannot solve this merely with `--release 17` on application code. You must choose a dependency version suitable for both runtimes or adjust the support policy.

## 25. Pre-release checklist

### Version policy

- [ ] Identified critical direct, transitive, and build/plugin dependencies.
- [ ] Removed uncontrolled dynamic versions/ranges from the release path.
- [ ] Used BOM/platform or dependencyManagement for related library families.
- [ ] Distinguished `strictly`, `prefer`, `require`, and force in Gradle.
- [ ] Established a policy for when the graph encounters version conflicts.
- [ ] Recorded reasons for dependency upgrades and compatibility evidence.

### Dependency locking

- [ ] Critical configurations have appropriate lockfiles/graph policies.
- [ ] Lockfiles are committed and diffs are reviewed.
- [ ] Release builds do not auto-update locks without a PR.
- [ ] Inspected buildscripts/plugins/toolchains outside lock scope.
- [ ] Snapshot/changing modules are managed separately.
- [ ] Have a lock refresh process for handling security and JDK upgrades.

### Repository and supply chain

- [ ] Release artifacts cannot be overwritten at the same coordinates/version.
- [ ] Repositories are restricted to trusted sources and namespaces.
- [ ] Checksum/signature verification exists per policy.
- [ ] Credentials are not placed in source or build logs.
- [ ] Dependency graph/SBOM and provenance are archived alongside releases.
- [ ] Have a way to determine which libraries a production build actually contains.

### Reproducible build

- [ ] Gradle/Maven distribution is pinned via wrapper or CI policy.
- [ ] JDK vendor/version/toolchain and OS target are specified.
- [ ] Archive timestamps and entry ordering are managed where needed.
- [ ] Generated resources contain no random/uncontrolled inputs.
- [ ] Compilers, annotation processors, and packaging plugins have explicit versions.
- [ ] Build artifacts have checksums and are re-verified when needed.

### Java migration

- [ ] Build tools and plugins support the target JDK.
- [ ] New dependencies support the consumer's minimum JDK.
- [ ] Ran dependency graph diagnostics across compile/test/runtime.
- [ ] Checked Java agents, bytecode tools, ORMs, serializers, and native dependencies.
- [ ] Have unit/integration tests per the JDK support matrix.
- [ ] Have a canary/rollback plan and monitor linkage/behavior errors.
- [ ] Do not treat an "unchanged lockfile" as proof that the application is already compatible.

## Conclusion

Version constraints, dependency locking, and reproducible builds address three different layers of the same problem. **Constraints** state which versions are allowed or preferred. **Lockfiles** preserve dependency resolution results to avoid builds accidentally selecting new versions. **Reproducible builds** go one step further: controlling the JDK, build tools, plugins, repositories, timestamps, and other inputs to produce traceable and repeatable artifacts.

In Java Advance Compatibility Migration, start from the real dependency graph, align library families using BOMs/platforms or dependencyManagement, manage Gradle lockfiles or equivalent Maven mechanisms by policy, protect artifacts through verification and immutable repositories, and then test on the target JDK. A locked build may still contain bugs or CVEs; a byte-for-byte reproducible artifact may still be incompatible at runtime. Therefore, use locking to make change **controlled**, and use compatibility testing, security reviews, and release provenance to ensure that change is **correct and safe**.
