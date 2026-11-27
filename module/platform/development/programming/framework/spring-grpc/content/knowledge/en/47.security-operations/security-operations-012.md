# Auditing Dependencies and Codegen Plugins

In a Spring gRPC service, application source code is only one part of the software supply chain. The build also downloads Spring and gRPC libraries, runs Gradle or Maven plugins, and invokes the Protocol Buffers compiler (`protoc`) alongside gRPC code-generation plugins such as `protoc-gen-grpc-java`. Components executed at build time can run arbitrary code on developer machines or CI runners, so they require the same controls as runtime dependencies.

The goal of auditing is to know precisely which components are downloaded, where each version originates, whether versions are compatible, whether artifacts have been tampered with, and which known vulnerabilities need remediation. For Spring gRPC, audit runtime libraries, build plugins, and codegen tools separately; a BOM managing runtime libraries does not automatically pin plugin or `protoc` versions.

## 1. Identifying Components in the Build Chain

| Category | Examples in a Spring gRPC Project | What to Audit |
|---|---|---|
| Application libraries | Spring gRPC starter, `grpc-protobuf`, `grpc-stub`, `grpc-netty-shaded`, `protobuf-java` | Direct and transitive versions, artifact provenance, CVEs, compatibility with Spring Boot and JDK |
| Build plugins | Gradle `com.google.protobuf` or `protobuf-maven-plugin`; Spring Boot Gradle/Maven plugin | Plugin version, plugin dependencies, distribution repositories, and checksums |
| Codegen tools | `com.google.protobuf:protoc`, `io.grpc:protoc-gen-grpc-java` | Compiler/generator versions, OS/architecture-specific artifacts, binary integrity |
| Generated code | Java message classes and gRPC stubs from `.proto` files | Code generated from approved schemas and toolchains; clean rebuilds must produce consistent output |

`protoc` and `protoc-gen-grpc-java` are two distinct tools: `protoc` parses Protocol Buffers schemas, while the gRPC plugin generates service descriptors, client stubs, and server base classes. The Gradle/Maven plugin orchestrates both. Inspecting only `runtimeClasspath` can miss risks hiding in plugins or codegen binaries.

gRPC modules should use a verified-compatible version set. You can use `io.grpc:grpc-bom` to align gRPC runtime libraries. This BOM does not manage Gradle/Maven plugin versions, `protoc`, or `protoc-gen-grpc-java`; those components must still be declared and reviewed separately. The Spring gRPC starter version must align with the Spring Boot version supported by the project.

## 2. Dependency Control Principles

**Declare versions explicitly.** Never use dynamic versions like `1.+`, `latest.release`, wide version ranges, or snapshots in release builds. Pin plugin, compiler, generator, and library versions. When upgrading, change each group deliberately so you can trace which component altered the dependency graph.

**Restrict artifact sources.** Configure only organization-approved repositories, such as Maven Central or an internal mirror. Never add arbitrary repositories from URLs found in online tutorials. Audit both repositories resolving plugins and repositories resolving libraries: Gradle has a separate `pluginManagement.repositories`; Maven can configure mirrors in `settings.xml`.

**Lock resolution results and verify integrity.** Lockfiles record resolved dependency versions; checksums or signatures detect artifacts differing from approved ones. A lockfile alone does not prove an artifact is safe, and checksums are meaningful only when reference values come from a trusted source and are reviewed.

**Inspect transitive dependencies.** A single direct library can pull in many others. Inspect the full dependency tree, understand why a particular version was selected, and catch conflicts. Avoid using `force` or global exclusions merely to make a build green before understanding the impact.

**Separate build privileges from operational privileges.** Plugins and codegen execute in the build environment. CI should use short-lived runners with minimal write permissions and never expose deployment secrets or production credentials to jobs building untrusted pull requests.

## 3. Auditing with Gradle

### 3.1. Pinning Runtime and Codegen Versions

The example below uses Gradle Kotlin DSL. Placeholders inside `<...>` mark where team-approved versions go; never copy them literally as real versions.

```kotlin
plugins {
    java
    id("com.google.protobuf") version "<pinned-protobuf-gradle-plugin-version>"
}

val grpcVersion = "<approved-grpc-version>"
val protobufVersion = "<approved-protobuf-version>"

dependencies {
    // BOM aligns gRPC runtime libraries.
    implementation(platform("io.grpc:grpc-bom:$grpcVersion"))
    implementation("io.grpc:grpc-protobuf")
    implementation("io.grpc:grpc-stub")
    runtimeOnly("io.grpc:grpc-netty-shaded")

    // Declare the Spring gRPC starter per the Spring Boot BOM/compatibility
    // matrix used by the project.
}

protobuf {
    // Protocol Buffers compiler.
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }

    // Generator producing Java service stubs for gRPC.
    plugins {
        id("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }

    generateProtoTasks {
        all().configureEach {
            plugins {
                id("grpc")
            }
        }
    }
}
```

This example highlights four items requiring independent review: the Gradle protobuf plugin version, `protoc` version, `protoc-gen-grpc-java` version, and gRPC runtime BOM. Select them according to your project's compatibility matrix. Generated code must compile cleanly against the corresponding `protobuf-java` and gRPC runtime versions; never assume all latest releases are mutually compatible.

In `settings.gradle.kts`, restrict where Gradle searches for plugins. For example, declare only the Gradle Plugin Portal or an approved internal mirror inside `pluginManagement.repositories`. Configure dependency repositories separately in `dependencyResolutionManagement.repositories` and consider `RepositoriesMode.FAIL_ON_PROJECT_REPOS` so subprojects cannot add arbitrary download sources.

### 3.2. Inspecting the Dependency Tree and Plugin Classpath

Run these commands from the directory containing the Gradle Wrapper:

```bash
# Inspect resolved runtime dependencies.
./gradlew dependencies --configuration runtimeClasspath

# Trace why a specific version was selected.
./gradlew dependencyInsight \
  --dependency grpc-netty-shaded \
  --configuration runtimeClasspath

# Inspect dependencies declared on the buildscript classpath.
./gradlew buildEnvironment

# Inspect plugin resolution and codegen execution logs.
./gradlew --info generateProto
```

`dependencies` and `dependencyInsight` uncover transitive versions and conflicts in application configurations. `buildEnvironment` focuses on the buildscript classpath; for plugins declared via `plugins {}`, also check `pluginManagement`, versions in build files, and plugin resolution logs. Never conclude the plugin classpath is clean solely from a `runtimeClasspath` report.

### 3.3. Enabling Dependency Locking and Verification

Enable locking for resolved configurations in the build:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Then run the build with `--write-locks` and commit the generated lockfiles. When updating, review lockfile diffs alongside build file changes; never auto-accept every new version.

Gradle supports generating checksum metadata for artifact verification. Bootstrap metadata during a controlled resolution:

```bash
./gradlew --write-verification-metadata sha256 clean generateProto test
```

Review `gradle/verification-metadata.xml`, confirm the provenance and checksum of every artifact, then commit the file. In CI, enforce strict verification:

```bash
./gradlew --dependency-verification=strict clean generateProto test
```

If verification fails, verify the artifact and distribution source before updating checksums. Never work around failures by deleting metadata or disabling strict mode. Also pin and verify the Gradle Wrapper distribution via `distributionSha256Sum` in `gradle/wrapper/gradle-wrapper.properties`; dependency verification does not replace verifying the Gradle distribution itself.

## 4. Auditing with Maven

In Maven, place runtime library versions in `dependencyManagement` and import the gRPC BOM. Declare plugin versions in `pluginManagement` or directly on the plugin declaration. The codegen example below uses properties so versions are reviewed in one place:

```xml
<properties>
    <grpc.version>approved-grpc-version</grpc.version>
    <protobuf.version>approved-protobuf-version</protobuf.version>
    <protobuf.maven.plugin.version>approved-plugin-version</protobuf.maven.plugin.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-bom</artifactId>
            <version>${grpc.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<build>
    <plugins>
        <plugin>
            <groupId>org.xolstice.maven.plugins</groupId>
            <artifactId>protobuf-maven-plugin</artifactId>
            <version>${protobuf.maven.plugin.version}</version>
            <configuration>
                <protocArtifact>com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}</protocArtifact>
                <pluginId>grpc-java</pluginId>
                <pluginArtifact>io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}</pluginArtifact>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>compile</goal>
                        <goal>compile-custom</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

`os.detected.classifier` is commonly provided by `os-maven-plugin`. If the project uses that extension, pin the extension's version as well. `protoc` and `protoc-gen-grpc-java` artifacts are platform-specific executables; inspect the resolved classifier on CI runners and prevent builds from silently downloading unapproved binaries.

Useful commands:

```bash
# Application dependency tree, including transitive dependencies.
mvn dependency:tree -Dverbose

# Effective POM after parent inheritance and profile resolution.
mvn help:effective-pom

# Resolve Maven build plugin dependencies.
mvn dependency:resolve-plugins

# Run code generation, compilation, and tests from a clean state.
mvn clean generate-sources test
```

`dependency:tree` primarily reflects project dependencies; use `dependency:resolve-plugins` to inspect plugin dependencies. `help:effective-pom` reveals plugin versions inherited from parent POMs or profiles. You can configure Maven Enforcer to require explicit plugin versions, enforce dependency convergence, and ban snapshot dependencies in release builds. With Maven Wrapper, pin the distribution checksum in `.mvn/wrapper/maven-wrapper.properties` using `distributionSha256Sum` if your Wrapper version supports it.

Maven repositories should route through managed mirrors in `settings.xml`. Set the repository checksum policy to `fail` so Maven rejects artifacts lacking valid repository-supplied checksums. That provides one verification layer; for critical artifacts, also verify checksums/signatures per internal procedures and retain provenance evidence.

## 5. Vulnerability Scanning and Inspecting Generated Code

### 5.1. Scanning Build-Time Dependencies Too

Use an organization-approved SCA tool to scan direct and transitive dependencies, such as OWASP Dependency-Check or an equivalent CI scanner. Coverage should include runtime libraries, build plugins, and codegen tools within scanner capabilities. An application dependency scan report does not automatically cover the entire plugin classpath or binaries downloaded for codegen; cross-check reports against the resolved plugin and tool inventory.

For each CVE alert, verify artifact coordinates, affected versions, fixed versions, exploitability, and whether the component actually enters the released build. Prefer upgrading to patched versions. When suppressing a false positive, record the justification, owner, artifact scope, and expiration date; never apply blanket suppressions across whole dependency groups.

Generate an SBOM for builds or releases when required by project governance. The SBOM must accurately reflect packaged components and, where tooling supports it, key build tools. Retain SCA reports, SBOMs, lockfiles, and verification metadata as build evidence.

### 5.2. Verifying Codegen Output

After upgrading `protoc`, the protobuf plugin, or `protoc-gen-grpc-java`:

1. Inspect diffs of `.proto` files and plugin configuration to verify input changes.
2. Clean old outputs and regenerate code using the pinned Wrapper and toolchain.
3. Verify generated code lands in expected packages and source sets; never hand-edit generated files.
4. Compile and run tests to catch API mismatches between generated code and runtime libraries.
5. If the repository checks in generated sources, review the diff and confirm it is reproducible from the schemas with the same tool versions. Otherwise, ensure the pipeline always regenerates code cleanly from schemas.

Generated sources are outputs of the compiler and generator, so reviewing diffs does not replace verifying the provenance of those two tools. When building untrusted pull requests, execute codegen inside isolated runners without deployment secrets or production access.

## 6. Review Workflow for Dependency or Codegen Changes

| Step | Action | Evidence to Retain |
|---|---|---|
| 1. Identify change | State upgrade rationale, artifact, old/new versions, and source repository | Diff of build files, parent POM, or version catalog |
| 2. Inspect resolution | Review runtime dependency tree, plugin dependencies, and codegen artifacts | Output of `dependencies`, `dependencyInsight`, or `dependency:resolve-plugins` |
| 3. Check compatibility | Cross-check Spring Boot, Spring gRPC, gRPC runtime, protobuf runtime, compiler, and generator | Compatibility matrix or approved upgrade notes |
| 4. Security check | Verify checksums/signatures, run CVE scans, and review license changes if required | Verification metadata, SCA report, and repository source review |
| 5. Verify output | Regenerate code, compile, and run tests from a clean state | CI logs, test results, and generated-source diff if applicable |
| 6. Lock results | Update lockfiles and verification metadata after successful review | Lockfile, checksum metadata, SBOM, and commit hash |

If a new plugin pulls in unfamiliar dependencies, halt approval until you confirm which plugin introduced them, which repository served them, and whether they are genuinely needed by the build. Use `dependencyInsight` for application dependencies or `dependency:resolve-plugins` for Maven plugins to trace provenance, comparing against lockfile diffs and resolution logs. If provenance or integrity cannot be verified, keep that artifact out of the release pipeline.

## 7. Pre-CI Build Checklist

- [ ] All Gradle/Maven plugins use pinned versions and approved distribution repositories.
- [ ] `protoc` and `protoc-gen-grpc-java` have pinned versions, expected classifiers, and runtime compatibility.
- [ ] Spring gRPC starter, Spring Boot, and gRPC libraries form a compatible version set; BOMs apply at the proper scope.
- [ ] Transitive dependencies and build-plugin dependencies were inspected, not solely application `runtimeClasspath` or `dependency:tree`.
- [ ] Lockfiles and checksum/verification metadata have been reviewed, committed, and enforced in CI.
- [ ] Gradle/Maven Wrapper versions and distribution checksums are pinned.
- [ ] Vulnerability scan findings are triaged; suppressions include rationale and expiration dates.
- [ ] Clean builds regenerate code, compile, and pass tests on supported runners.
- [ ] Build jobs run with least privilege and never expose production secrets to plugin/codegen steps on untrusted code.

## References

- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Plugin management](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Maven — Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Maven — Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [Protocol Buffers — Java generated code](https://protobuf.dev/reference/java/java-generated/)
- [gRPC — Java generated code](https://grpc.io/docs/languages/java/generated-code/)
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/)
