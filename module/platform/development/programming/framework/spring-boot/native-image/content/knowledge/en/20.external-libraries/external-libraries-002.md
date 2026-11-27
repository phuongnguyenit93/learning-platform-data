# Determining Native Support for the Exact Library Version

## 1. Why Must You Check the Exact Version?

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed with **Spring AOT** and compiled into a **GraalVM Native Image** to evaluate compatibility, startup time, memory usage, container packaging, and operations. An application typically uses many external libraries: JSON, logging, database drivers, cache clients, HTTP clients, telemetry, security, template engines, and Spring Boot starters. Native capability depends on the **actual resolved artifact version**, not just the library name.

A library might support native in a newer version while lacking metadata in an older version. One release may support a specific JDK or Spring Framework version, while another release has changed its API, reflection behavior, or resource packaging. Furthermore, a dependency can run fine on the JVM yet fail a native build because classes/members/resources are only accessed dynamically.

Therefore, the question "Does library X support Native Image?" must be broken down into:

- Which artifact is being used: group, artifact, version, classifier, and scope?
- Is that version confirmed by the publisher to support GraalVM Native Image?
- Is the native metadata packaged in the JAR, pulled from the GraalVM Reachability Metadata Repository, or supplied by the application itself?
- Does that metadata apply to the version in use and the current GraalVM/toolchain?
- Have the features the application actually uses been tested on a native executable?

After this lesson, learners can:

1. Trace the actual resolved version of direct and transitive dependencies.
2. Read native support evidence from publisher documentation, JARs, and metadata repositories.
3. Distinguish between "metadata present", "native tested", and "vendor supported".
4. Assess risk per feature, not just by dependency name.
5. Verify compatibility across the library, Spring Boot, Spring Framework, JDK, GraalVM, and target operating system.
6. Create a compatibility ledger with evidence, confidence level, and next actions.
7. Confirm conclusions via native builds and tests of actual execution paths.

> **Principle:** do not label a library "native-compatible" simply because the JVM application runs, or because another version of the library has metadata. Conclusions must be tied to exact artifact coordinates, version, toolchain, and tested features.

## 2. Native Compatibility Consists of Multiple Layers of Evidence

There is no single property in a POM or artifact name that guarantees a library runs natively. Multiple layers must be examined:

| Layer | Question to answer | Evidence to look for |
| --- | --- | --- |
| Publisher | Does the vendor announce Native Image support for this release? | Compatibility matrix, release notes, official native documentation. |
| Artifact | Does the JAR in use contain native metadata? | `META-INF/native-image/`, reachability metadata, `native-image.properties`. |
| Metadata repository | Is there configuration for the exact coordinates and version? | GraalVM Reachability Metadata Repository and plugin metadata download logs. |
| Spring AOT | Does the library integrate with Spring AOT or provide runtime hints? | Vendor guidance, Spring AOT integration, generated hints. |
| Toolchain | Is the library version compatible with the JDK/GraalVM/Spring being built? | Version matrix and native build logs. |
| Runtime feature | Do the features the application uses work in native mode? | Native integration tests, smoke tests, issues/known limitations. |
| Platform | Do binaries and native dependencies fit the target OS/architecture/libc? | Build image for target platform, inspect shared libraries, and container tests. |

Three conclusions are frequently confused:

- **Metadata present:** some dynamic accesses have been described for Native Image. This does not prove all features of the library work.
- **Built/tested successfully:** a specific configuration and test suite ran successfully. This does not mean the vendor commits to supporting every environment.
- **Vendor supported:** the vendor publishes a clear support scope, usually accompanied by a version/JDK/GraalVM matrix. Integration testing in the actual application is still required.

A library can be native-compatible even without its own `META-INF/native-image` directory if it requires no dynamic access or its accesses are handled by the framework/tooling. Conversely, a JAR with metadata can still lack metadata for an undescribed feature.

## 3. Start From the Actual Dependency Graph

Before looking up native support, you must determine the exact dependency graph used by the build. Declarations in `pom.xml` or `build.gradle` are not enough because dependency management, exclusions, constraints, platforms/BOMs, and transitive dependencies can alter the final resolved version.

### 3.1. Maven: Inspect the Dependency Tree

Run from the project directory:

~~~bash
./mvnw dependency:tree
~~~

To view dependency details and transitive paths:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Filter for a specific library:

~~~bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Check for conflicted, omitted, or selected dependency versions. `dependency:tree` shows resolution relationships; save the output alongside the commit/build profile so others can reproduce it.

You can export the runtime classpath to locate the actual JARs:

~~~bash
./mvnw dependency:build-classpath \
  -DincludeScope=runtime \
  -Dmdep.outputFile=target/runtime-classpath.txt
~~~

This classpath is useful for identifying resolved artifact paths. If the project uses Maven profiles, run the command with the same profiles and properties as the native build.

### 3.2. Gradle: Inspect runtimeClasspath

View the dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

See why a particular version was selected:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Repeat for each dependency to verify. `dependencyInsight` helps uncover versions upgraded/downgraded by constraints, platforms, force rules, or transitive dependencies.

If the application has multiple source sets or configurations, `runtimeClasspath` may not represent the native task's classpath. Inspect the task graph and `nativeCompile` configuration; explicitly record the configuration used by the native plugin.

### 3.3. Check the Exact Artifact, Not Just the Library Name

A library may publish multiple artifacts:

- Core module and integration module.
- Starter and implementation module.
- JDBC driver and connection pool.
- Pure Java JAR and artifacts with separate classifiers/native binaries.
- Community and enterprise editions.
- Optional modules loaded only when a feature is enabled.

Metadata for `library-core` does not automatically apply to `library-jdbc` or `library-spring-boot-starter`. Check every artifact appearing in the dependency graph and identify which modules are actually invoked at runtime.

## 4. Look Up Evidence From the Publisher

Prioritize official publisher documentation for the **exact version**. Look for:

1. Native Image/GraalVM support statement.
2. Version compatibility matrix: JDK, Spring Boot, Spring Framework, GraalVM, and OS.
3. Release notes for the version in use and intermediate versions with native support changes.
4. AOT instructions, reflection/resource configuration, or required plugins.
5. Known limitations: dynamic class loading, scripting, JNI, runtime compilation, serialization, proxies, cryptography, filesystem, or networking.
6. Official testing methods: native test suites, sample apps, container images, or CI jobs.

### 4.1. Read Scoped Support Statements

A "supports GraalVM" statement might only mean the library was tested with a specific GraalVM/JDK. Check whether the statement specifies:

- Minimum library version or supported version range.
- GraalVM distribution and release.
- JDK version.
- Spring Boot/Spring Framework version.
- OS/architecture.
- Modules/features within scope.
- Whether separate metadata or build profiles are required.

If the documentation only says "native-ready" without a version matrix, record it as **insufficiently detailed evidence** and verify via artifacts/tests. Do not extrapolate that claim to all versions.

### 4.2. Check Release Notes

Important changes may appear in release notes:

- Added GraalVM reachability metadata.
- Added Spring `RuntimeHintsRegistrar` or `@RegisterReflectionForBinding`.
- Changed how resources are read or classes are loaded.
- Added an AOT support module.
- Removed legacy APIs or raised the JDK baseline.
- Fixed bugs that only occur in native executables.

If the current version lacks support, identify the first version that added support and check for breaking changes when upgrading. Do not automatically pick the latest version if it is incompatible with the Spring Boot/JDK in use.

## 5. Inspect Metadata Packaged in the JAR

A library can distribute reachability metadata right inside its artifact. Common layout:

~~~text
some-library-2.4.0.jar
├── com/vendor/library/...
└── META-INF/
    └── native-image/
        └── com.vendor/
            └── some-library/
                ├── reachability-metadata.json
                └── native-image.properties
~~~

Subdirectory layouts can differ across artifacts; the key point is that metadata sits under `META-INF/native-image/` at the root of a classpath entry in a format supported by Native Image.

### 5.1. List JAR Contents

After locating the JAR path on the dependency classpath:

~~~bash
jar tf /path/to/some-library-2.4.0.jar
~~~

Filter the metadata section:

~~~bash
jar tf /path/to/some-library-2.4.0.jar | grep 'META-INF/native-image/'
~~~

On PowerShell, you can replace `grep` with `Select-String`. `/path/to/...` is only a placeholder; replace it with the actual resolved JAR path.

### 5.2. Inspect Metadata Contents

If `reachability-metadata.json` is present, read the file to see what it describes:

- Reflection: classes, constructors, methods, fields, and access levels.
- Resources: patterns or specific resources.
- Dynamic proxy: interface combinations.
- Serialization: supported types.
- JNI: classes/members accessed from native code.
- Resource bundles: bundles to package.
- Condition/version: scope of applicability if the schema supports conditions.

Do not conclude "full native support" just from seeing a JSON file. Check whether the metadata covers the exact classes/members used by the application's features. A file might cover only part of the library or only one integration module.

### 5.3. Inspect native-image.properties

A dependency may contain:

~~~properties
Args = --some-native-image-option
~~~

This file can append Native Image build arguments for the artifact. Read each argument carefully because an option in a dependency can affect every consuming application. If metadata requires global flags, clearly record the source of configuration and verify the flags remain valid in the GraalVM version in use.

Do not copy metadata files from a different JAR version and assume compatibility. Configuration might reference renamed classes/members or a schema rejected by the current GraalVM.

### 5.4. Spring Boot Executable JARs With Nested Dependencies

JARs repackaged by Spring Boot typically have this structure:

~~~text
application.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    └── lib/
        ├── some-library-2.4.0.jar
        └── another-library-1.8.0.jar
~~~

Running `jar tf application.jar` only shows that nested JARs exist. It does not automatically display all `META-INF/native-image` contents inside each dependency JAR.

You can extract a nested JAR to a temporary file and inspect it separately:

~~~bash
unzip -p application.jar BOOT-INF/lib/some-library-2.4.0.jar \
  > target/some-library-2.4.0.jar

jar tf target/some-library-2.4.0.jar | grep 'META-INF/native-image/'
~~~

On Windows, use an appropriate ZIP tool or PowerShell to extract nested JARs. With Spring Boot's integrated native compilation, the plugin must prepare the proper classpath; inspect native task logs and AOT output rather than inferring from a single archive listing.

## 6. Look Up the GraalVM Reachability Metadata Repository

Not every library publishes native metadata in its own JAR. The **GraalVM Reachability Metadata Repository** is a community-maintained metadata repository for various third-party libraries. This repository can supply reflection, resource, proxy, serialization, or JNI configuration for listed artifacts/versions.

Project page:

- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)

When looking up an entry:

1. Find the exact `groupId` and `artifactId`.
2. Check the version or version range to which the metadata applies.
3. Inspect the types of metadata provided.
4. Read notes, conditions, and tests if available.
5. Confirm your project's Native Build Tools version integrates with/is configured to use the repository as assumed.
6. Check build logs to see whether the metadata was fetched and included in native analysis.

The metadata repository is not a registry containing every Java library. Not finding an entry **does not prove** the library is incompatible; it only means there is no metadata evidence from the repository for that artifact yet. The library may not need metadata, may bundle metadata in its JAR, may use Spring hints, or may not have been added by the community yet.

### 6.1. Read Version Ranges Carefully

A metadata entry may apply to a version range, not necessarily a single version. Read the version conditions published by the repository. Do not assume that `2.3.x` metadata is always safe for `2.4.x`, or that newer version metadata is always compatible with older versions.

If a dependency is upgraded before the metadata repository is updated, a native build may:
- Skip applying metadata because the version falls outside the range.
- Apply metadata whose class/member names have changed.
- Build successfully while missing configuration for new features.
- Fail with schema or unsupported option errors.

### 6.2. Confirm the Plugin Actually Uses the Metadata

Native Build Tools can integrate with the reachability metadata repository depending on version and configuration. Do not assume the plugin automatically downloads an entry just because it exists in the repository. Verify:

- The GraalVM Native Build Tools Maven/Gradle plugin version in use.
- Repository/metadata configuration in the plugin per that version's documentation.
- Metadata download logs or configuration files passed into the native build.
- Results when running the corresponding feature in the native executable.

If the plugin version does not use the repository automatically, configure it per the documentation or bring metadata into the project in a supported manner. Avoid manually downloading files and adding ad-hoc flags without recording the metadata's source and version.

## 7. Check Spring AOT and Library Integrations

For Spring Boot applications, a library can support native through:

- Spring `RuntimeHintsRegistrar`.
- Annotations such as `@RegisterReflectionForBinding`.
- Spring AOT contributions or integration modules.
- GraalVM reachability metadata packaged in the JAR.
- Metadata from the Reachability Metadata Repository.
- Application-supplied configuration when the library does not provide enough.

### 7.1. Identify the Source of Hints

If a library has Spring integration, check the documentation to see whether it auto-registers hints or requires importing configuration. Some hints are only discovered when the corresponding auto-configuration or bean configuration is present in the application context processed by AOT.

If a library provides a registrar but the application context does not import/scan the relevant configuration, the registrar may not be invoked. Verify via AOT output, build logs, or `RuntimeHintsPredicates` tests.

### 7.2. Distinguish Library Metadata From Application Metadata

Metadata inside a dependency JAR describes the library's own requirements. Runtime hints declared by the application describe the application's own dynamic accesses or integration parts the library cannot know about.

For example, a JSON library already has metadata for its internal classes, but the application passes a `PaymentPlugin` subtype selected from a property. The application must still ensure its own subtype is reachable and has the required constructors/members. Do not expect external library metadata to guess application business classes.

### 7.3. Do Not Add Overly Broad Hints to Mask Missing Support

If a library lacks metadata, pinpoint the exact failing operation:
- Reflection on which class?
- Which constructor/method/field is called?
- Which resource path is read?
- Which interfaces make up the proxy?
- Which serialization type is used?
- Which JNI library is loaded?

Add minimal hints for those points, and explicitly document this as application-maintained metadata. Do not register entire packages or all members without justification.

## 8. Inspect Special Dependency Categories

Certain categories of libraries carry specific native risks and require deeper inspection beyond reflection metadata.

| Library category | Items to verify |
| --- | --- |
| JDBC/database driver | Driver class loading, service providers, JNI/native transport, TLS/certificates, DNS, and database integration tests. |
| Logging | Service loader, resource bundles, config files, plugin discovery, and appender native dependencies. |
| JSON/XML/serialization | DTO constructors, reflection, generic signatures, subtype registration, resources/schemas, and custom serializers. |
| ORM/data access | Entity introspection, proxy/lazy loading, bytecode enhancement, JDBC drivers, and query paths. |
| Cache/message broker | Client transport, Netty/native transport, TLS, DNS, compression, serializers, and connection lifecycle. |
| HTTP client | TLS provider, proxy configuration, DNS resolver, native transport, service loading, and resource certificates. |
| Metrics/tracing | Service loader, reflection, runtime instrumentation, exporters, native libraries, and shutdown hooks. |
| Scripting/expression engine | Runtime compilation, dynamic class loading, bytecode generation, and script engines. |
| Image/document/PDF processing | JNI, codecs, fonts, resource files, native binaries, and OS packages. |
| Cryptography | Provider discovery, native crypto libraries, entropy sources, certificate stores, and FIPS/provider constraints. |

For example, a JDBC driver might have complete reflection metadata yet still depend on a native library for transport. Conversely, a pure Java driver might build cleanly yet require service provider/resource metadata to register itself. Test actual features instead of assigning a blanket label to the entire category.

## 9. Build a Compatibility Matrix for the Exact Toolchain

Native support for a library is only meaningful within a specific environment combination. Record at minimum:

| Component | Details to lock down |
| --- | --- |
| Spring Boot | Exact version and BOM/platform managing dependencies. |
| Spring Framework | Actual version pulled in by Spring Boot. |
| JDK | Vendor, major version, and toolchain used to build. |
| GraalVM | Distribution, release, `native-image --version`. |
| Native Build Tools | Maven/Gradle plugin version and metadata repository configuration. |
| External library | `groupId`, `artifactId`, `version`, `classifier`, `scope`. |
| OS/architecture | OS, CPU architecture, libc/base image if relevant. |
| Build mode | Direct native compile or Buildpacks/container builder. |
| Feature coverage | Library APIs/features actually run in native tests. |

### 9.1. Capture Versions From the Actual Toolchain

You can record:

~~~bash
java -version
native-image --version
./mvnw -version
./gradlew --version
~~~

These commands show the shell environment. Plugins may use a separately configured toolchain, so inspect native build logs to confirm which JDK/GraalVM the plugin actually invokes.

### 9.2. Distinguish Build Host From Target Runtime

A native executable is typically tied to the OS/architecture and native libraries it was built for. A successful build on Linux x86_64 does not prove the executable runs on Linux ARM64, Windows, or Alpine/musl.

If deploying via containers, verify:
- Builder image and runtime image are compatible.
- OS/architecture of the executable matches the target image.
- `glibc`/`musl` and required shared libraries are present.
- Native libraries of dependencies are packaged and loaded properly.
- TLS certificates, timezone data, fonts, codecs, or system files are available.

## 10. Verify by Feature, Not Just by Dependency

After gathering documentation and metadata evidence, you must exercise the paths the application actually uses. A library may only be partially usable in native mode.

### 10.1. Define a Feature Inventory

For each dependency, record:

1. APIs called directly.
2. Features enabled via configuration or auto-configuration.
3. Dynamic access paths: reflection, resources, proxies, serialization, service loaders, JNI.
4. Enabled optional modules.
5. Profiles or deployment environments that alter features.
6. External integration points: databases, brokers, HTTP services, file systems.

You do not need to test every public API of the library; you must test all features the application depends on.

### 10.2. Use the JVM as a Baseline

Run the same test suite on the JVM first. Save JSON fixtures, inputs, environment variables, configuration, and expected outputs. When a native test fails, the baseline helps distinguish:
- Logic/data bugs already present on the JVM.
- Differences due to type erasure or generic configuration.
- Missing reflection/resource/proxy metadata.
- Native library, linker, or OS issues.
- Errors caused by differing profiles/configurations.

### 10.3. Native Smoke and Integration Tests

For each critical dependency, have at least one native test exercising its main features. For example:

- JSON: bind DTOs, generic collections, custom serializers, and subtypes.
- JDBC: load driver, open connection, query, transaction, and close.
- HTTP client: TLS, DNS, proxy, and request/response.
- Logging: load configuration, service providers, write logs, and shutdown.
- ORM: initialize context, query entities, proxies/lazy loading if used.
- Broker: connect, publish, consume, retry, and graceful shutdown.

A passing native build only proves compilation finished. A passing native smoke test only proves the exercised paths work under test conditions. Clearly note what remains unverified.

### 10.4. Native Image Tracing Agent as Supporting Evidence

The tracing agent can record reflection/resource/proxy/serialization accesses during JVM scenarios and generate suggested metadata. Use it to uncover missed access points, while keeping in mind:

- Unexecuted code flows will not appear in the output.
- The agent may generate broader metadata than actually needed.
- Generated metadata must be reviewed, checked against version/schema, and placed in a supported location.
- The agent does not prove vendor support for the library or all native features.

Use the tracing agent alongside vendor documentation, existing metadata, unit tests, and native integration tests.

## 11. Classify Results and Decide Usage

You can use the following statuses in the compatibility ledger:

| Status | Meaning | Action |
| --- | --- | --- |
| Vendor-supported | Publisher confirms support for the exact version/toolchain within a specific scope. | Check version matrix and run application integration tests. |
| Metadata-present | Metadata exists in the JAR or repository matching the version. | Confirm plugin uses metadata and test features. |
| Tested-in-project | Native build and application feature tests passed. | Document configuration, platform, and test scope. |
| Partial | Only certain modules/features run natively or have known limitations. | Enable only tested parts; isolate or replace missing features. |
| Unknown | Insufficient reliable evidence for the exact version. | Create a small spike/test, ask vendor, or inspect metadata. |
| Incompatible | Evidence of failure exists or vendor states this combination is unsupported. | Upgrade version, add configuration, replace dependency, or use JVM mode. |

Do not turn `Unknown` into `Incompatible`. Missing metadata in the repository is not conclusive proof that a library cannot run natively. Conversely, the existence of metadata is not enough to promote status to `Vendor-supported`.

### 11.1. Example Evaluation Table

| Dependency | Resolved version | Evidence | Tested features | Status |
| --- | --- | --- | --- | --- |
| JSON library | Actual version from dependency tree | Vendor docs + JAR metadata | DTO, generic list, subtype | Tested-in-project |
| JDBC driver | Actual version from BOM | Vendor matrix | Connect/query/transaction | Vendor-supported + tested |
| Image codec | Actual version | No metadata found; uses JNI | Decode PNG/JPEG in native | Unknown |
| Scripting engine | Actual version | Docs note runtime compiler | Evaluate script | Incompatible or Partial per test/vendor scope |

The rows above only illustrate how to record entries; they are not conclusions for any specific library. When applying in a project, replace them with actual artifacts/versions and real evidence.

## 12. Record a Reproducible Compatibility Ledger

A good ledger table should include these columns:

~~~text
groupId
artifactId
versionResolved
classifier
scope
directOrTransitive
introducedBy
vendorNativeStatement
vendorDocsUrl
jarMetadataPresent
metadataRepositoryEntry
metadataVersionRange
springAotIntegration
graalvmVersion
jdkVersion
nativeBuildPluginVersion
targetOS
targetArchitecture
featuresUsed
nativeTests
knownLimitations
status
owner
lastVerifiedCommit
verifiedAt
nextAction
~~~

Record specific URLs and release notes, not just generic documentation landing pages. Save `dependency:tree` or `dependencyInsight` output alongside the commit. When upgrading dependencies or GraalVM, re-evaluate rows whose version or support scope changed.

### 12.1. When Is Re-Verification Required?

Re-run the evaluation when:
- Upgrading the Spring Boot BOM or Spring Framework.
- Upgrading a direct or transitive library version.
- Upgrading GraalVM/JDK or Native Build Tools.
- Changing the base image, OS, CPU architecture, or libc.
- Enabling new modules/features.
- Changing serializers, transport, TLS providers, or native dependencies.
- The metadata repository updates version ranges or fixes metadata.

Do not reuse old results if the dependency graph or toolchain has changed significantly.

## 13. Hands-On Exercise: Audit Native Support for a Dependency Graph

**Scenario:** a Spring Boot service uses JSON, JDBC, an HTTP client, logging, and telemetry. The JVM application works, but the team does not yet know which versions in the dependency graph have native metadata or which features require extra configuration.

### Tasks

1. Run `dependency:tree -Dverbose` or `dependencies --configuration runtimeClasspath` and save the dependency graph.
2. Pick at least five important dependencies, including one transitive dependency and one dependency likely using JNI/native libraries.
3. Record `groupId`, `artifactId`, `version`, `classifier`, and resolved `scope`.
4. Look up publisher documentation and release notes for the exact version; save the JDK/Spring/GraalVM compatibility matrix if available.
5. Inspect each JAR at `META-INF/native-image/`; read the metadata and note the types of access described.
6. Check the GraalVM Reachability Metadata Repository; verify the version range and whether Native Build Tools actually uses the entry.
7. Identify Spring AOT integrations, runtime hints, or metadata the application needs to supply.
8. Lock down the GraalVM/JDK/plugin versions and target platform.
9. Write native smoke/integration tests for the actual features of each important dependency.
10. Classify each dependency as `Vendor-supported`, `Metadata-present`, `Tested-in-project`, `Partial`, `Unknown`, or `Incompatible`.
11. Create a compatibility ledger detailing evidence and action items before release.

### Evidence Log

| Evidence | Contents to save |
| --- | --- |
| Dependency graph | Maven/Gradle output and corresponding commit. |
| Artifact identity | Group, artifact, version, classifier, scope. |
| Vendor support | Documentation URLs, release notes, and version/platform scope. |
| JAR metadata | File list, contents, and hint types. |
| Repository metadata | Entry, version range, and proof the plugin used it. |
| Toolchain | JDK, GraalVM, Native Build Tools, Spring Boot. |
| Feature inventory | APIs/features actually used by the application. |
| Native tests | Commands executed, test reports, OS/architecture, and results. |
| Known limitations | Unsupported features, workarounds, and remaining risks. |
| Decision | Status, owner, verification date, and next action. |

### Completion Criteria

- [ ] Traced the exact resolved versions of direct and transitive dependencies.
- [ ] Distinguished artifacts with metadata from vendor-supported native artifacts.
- [ ] Verified JAR and repository metadata against exact version ranges.
- [ ] Confirmed Native Build Tools actually uses the expected metadata.
- [ ] Documented a compatibility matrix for JDK, Spring Boot, GraalVM, plugins, and platform.
- [ ] Native tests cover critical dependency features.
- [ ] Ledger records evidence, status, limitations, and next actions.
- [ ] Did not conclude `Incompatible` merely because the repository lacks metadata.

## 14. Self-Assessment Questions

1. Why is a dependency declaration in `pom.xml` insufficient to determine the version used by a native build?
2. Does metadata in `library-core`'s JAR automatically apply to `library-jdbc`?
3. What is the difference between `Metadata-present`, `Vendor-supported`, and `Tested-in-project`?
4. Why does not finding a dependency in the GraalVM Reachability Metadata Repository fail to prove incompatibility?
5. When should you inspect nested JARs inside `BOOT-INF/lib`?
6. Why must metadata repository version ranges be cross-checked against the actual resolved version?
7. What error can a dependency with reflection metadata still encounter if it uses JNI?
8. Why does a passing native build not prove every library feature works?
9. Which components besides the library version must be recorded in the compatibility matrix?
10. When must a compatibility assessment be re-run?

## 15. Official Documentation

Pages and repositories may change across releases. When evaluating, select documentation matching your library version and toolchain:

- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata): community-maintained metadata for Java libraries.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): format, location, and how to provide metadata.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): Maven/Gradle plugins and native build integration.
- [Spring Boot — GraalVM Native Image](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): Spring AOT, native compilation, and packaging.
- [Spring Framework — Ahead-of-Time Processing](https://docs.spring.io/spring-framework/reference/core/aot.html): runtime hints and AOT contributions.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): viewing the Maven dependency graph.
- [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependency insight and version selection.
- Compatibility matrices, release notes, and native image guides from **each library's publisher**: use the official pages for the exact resolved artifact/version.

**Key takeaway:** native support is a conclusion tied to artifact version, toolchain, platform, and exercised features. Start from the actual dependency graph, verify metadata and publisher claims, then run native tests and record the evidence in a compatibility ledger.
