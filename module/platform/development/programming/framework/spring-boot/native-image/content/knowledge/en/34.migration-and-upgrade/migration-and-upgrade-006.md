# Cross-Referencing Spring Boot, Framework, GraalVM, and Native Build Tools Upgrade Guides

## 1. Why Cross-Reference Multiple Guides?

Upgrading a Spring Boot Native Image application typically involves multiple components with independent release lifecycles: Spring Boot, Spring Framework, the JDK, GraalVM Native Image, Gradle/Maven, the Spring Boot plugin, GraalVM Native Build Tools, buildpacks, and the native compiler/linker. Each component may publish different JDK requirements, minimum versions, compatibility limits, and behavioral changes.

A newer Spring Boot version may require a newer JDK; a newer GraalVM version may change how Native Image is installed or which targets are supported; a build plugin may require a minimum Gradle/Maven version; and Spring Framework may change AOT APIs used by integration libraries. Bumping individual versions without checking the full combination can cause failures during compilation, AOT processing, native compilation, or runtime.

In the **SPRING_BOOT_NATIVE_IMAGE** module, the goal of reading upgrade guides is to determine a supported and testable combination—not merely to pick the latest version of every component.

## 2. Map of Components to Cross-Reference

| Component | Documentation to check | Key questions |
|---|---|---|
| Spring Boot | System requirements, release notes, migration guide | Minimum JDK? Which Framework version is managed? What breaking changes? |
| Spring Framework | What's new, upgrade guide, AOT/native docs | Did AOT APIs, bean processing, hints, or proxies change? |
| JDK | Release notes, support policy, toolchain docs | Which Java releases/patches are supported? Any compiler/runtime changes? |
| GraalVM | Release notes, compatibility matrix, Native Image docs | JDK baseline, OS/architecture, libc, and Native Image options? |
| Native Build Tools | Plugin release notes and compatibility docs | Gradle/Maven version, Spring Boot integration, task/goal changes? |
| Gradle/Maven | Compatibility matrix and wrapper release notes | Which JDK runs the build tool? Which version do plugins require? |
| Native compiler/linker | GraalVM/toolchain docs | Which compiler, linker, SDK, and system libraries are needed? |
| Buildpacks/container | Builder/run image release notes | Are builder, lifecycle, run image, and target ABI compatible? |

Never rely on a single document to conclude the entire stack is compatible. Each vendor owns its own piece of the stack; you must verify the intersecting constraints.

## 3. Distinguish Minimum, Supported, and Tested

Three concepts are frequently confused:

- **Minimum requirement**: the lowest version documented as required to run or build.
- **Supported combination**: a version combination within the vendor-supported matrix.
- **Tested combination**: a combination actually exercised by your project/team through its test pipeline.

Spring Boot's minimum JDK does not automatically prove every GraalVM distribution with that JDK major version is compatible. A plugin may require a newer Gradle; a native dependency may support only specific OS/architectures.

Create a control table:

| Layer | Minimum | Selected | Evidence |
|---|---|---|---|
| JDK | Per Spring Boot/plugin | Specific version and vendor | Build toolchain log |
| Spring Boot | Per application | Supported patch release | Release notes/migration guide |
| Spring Framework | Per Boot BOM or verified override | Corresponding version | Dependency report |
| GraalVM | Per Native Image support | Specific distribution/version | Native Image version output |
| Native Build Tools | Per plugin compatibility | Specific version | Plugin docs/build log |
| Gradle/Maven | Per plugin requirements | Wrapper version | Wrapper properties |
| Builder image | Per native toolchain | Tag and digest | Image manifest |

Record URLs/document names, access dates or referenced releases, and the commit updating the table. This shows reviewers what evidence backs the compatibility conclusion.

## 4. Start from Spring Boot Release Notes

When upgrading Spring Boot:

1. Identify the current version and target version.
2. Read the system requirements for the target version.
3. Read release notes for every intermediate minor/major version.
4. Read the migration guide and deprecated API notes.
5. Identify the Spring Framework version managed by Spring Boot.
6. Check JDK baseline and Gradle/Maven plugin requirements.
7. Review changes to auto-configuration, properties, and test infrastructure.
8. Rebuild and pass the JVM application before bringing Native Image into scope.

The Spring Boot BOM/parent manages a dependency set tested together with the release. If overriding Spring Framework or core libraries, verify compatibility separately and document the rationale. Do not upgrade Spring Framework alone just to pick up a fix without evaluating the BOM and auto-configuration.

## 5. Read the Spring Framework Migration Guide Through an AOT Lens

Spring Framework may change APIs/configuration affecting:

- `ApplicationContext` and bean definition processing.
- `RuntimeHints`, `RuntimeHintsRegistrar`, and reflection metadata.
- Proxy/AOP generation.
- Resource handling.
- Serialization and binding.
- Classpath scanning and condition evaluation.
- `TestContext` and AOT test support.

Upgrading Spring Boot usually changes the Framework version via the BOM as well. Read the What's New and upgrade guide for that Framework version, focusing on APIs used by the application or custom libraries.

Search the codebase for signals: implementations of `RuntimeHintsRegistrar`, custom `BeanFactoryPostProcessor`, `BeanDefinitionRegistryPostProcessor`, custom conditions, proxy configuration, and resource loaders. Extensions that hook deeply into the context may need adjustments when the AOT engine evolves.

Do not check compilation alone. An API may still compile while AOT behavior or the generated bean graph changes.

## 6. Cross-Reference JDK and GraalVM Distributions

GraalVM has multiple distributions/release lines and may be packaged differently. When reading documentation, clarify:

- GraalVM distribution/vendor.
- JDK major and patch version.
- Native Image component/version.
- How Native Image is installed.
- OS and CPU architecture.
- `glibc`/`musl` or ABI target.
- Native compiler/linker requirements.
- Container build support and cross-compilation if needed.

Do not infer that GraalVM distributions sharing the same JDK major version share identical Native Image options or compatibility. Distributions can differ in components, licenses/features, and packaging.

Inspect actual versions in CI:

```bash
java -version
native-image --version
native-image --help
```

Save this output in the build manifest. If using a container builder, record the image digest and platform as well, not just the tag.

## 7. Cross-Reference GraalVM Native Image Release Notes

On every GraalVM/Native Image upgrade, review:

- Deprecated, renamed, or removed options.
- Reachability analysis and default behavior changes.
- Runtime initialization vs. build-time initialization.
- Reflection, JNI, serialization, and resource metadata.
- PGO/profile-guided optimization if used.
- Debug information and diagnostic options.
- Static/dynamic linking, libc, and target support.
- Compiler/linker and memory requirements.
- Build time, executable size, and runtime behavior.

An option that previously worked may change semantics or become the default. Never copy all `native-image` arguments from an old build to a new version without reading release notes and checking `--help`.

For compilation failures, preserve the command line and full compiler log to compare changes. For runtime failures, preserve binary identity, stack traces, and runtime image digest.

## 8. Cross-Reference the Native Build Tools Plugin

Native Build Tools connects Gradle/Maven to the Native Image compiler. When upgrading the plugin, check:

- Plugin version and JDK requirements.
- Minimum Gradle/Maven version.
- Task/goal names and lifecycle integration.
- How build arguments are passed.
- Toolchain configuration and GraalVM detection.
- Test support and native test execution.
- Container/buildpack integration if applicable.
- Default changes and deprecations.

The plugin version does not have to match the GraalVM version. Choose versions using the plugin and GraalVM compatibility docs, then verify in the pipeline. If the Spring Boot plugin already manages or integrates Native Build Tools, avoid adding a second plugin in a way that creates conflicting configurations.

## 9. Verify Gradle/Maven Compatibility

The Gradle Wrapper or Maven Wrapper must be compatible with both the JDK running the build and the applied plugins.

Gradle:

```bash
./gradlew --version
./gradlew tasks
./gradlew buildEnvironment
```

Maven:

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
```

Read the Gradle/Maven compatibility matrix to verify which Java runtime supports running the build tool; distinguish that from the Java toolchain used to compile the application. For example, the Gradle daemon may run on one JDK while compilation targets another JDK. Native Build Tools might pick a different GraalVM installation if configuration is ambiguous.

Pin wrapper distribution and checksum, plugin versions, dependency locks, and JDK/GraalVM installations in CI.

## 10. Check Spring Boot Plugin and Native Build Tools Integration

With Gradle, determine what manages `nativeCompile` and AOT processing: the Spring Boot Gradle plugin, the Native Build Tools plugin, or custom configuration. With Maven, inspect Spring Boot Maven Plugin executions and Native Build Tools integration.

Do not assume tasks/goals stay identical across plugin versions. Inspect the task list/effective POM and logs to see the actual lifecycle.

After upgrading, verify:

- AOT processing runs exactly once with the right profile.
- Native Image receives the right build arguments.
- Output executable is placed at the path expected by packaging tasks.
- Native tests execute against the right artifact.
- Buildpacks use the right builder/run image.
- No obsolete tasks or duplicate plugins remain.

## 11. Build a Project Compatibility Matrix

Your project matrix should reflect combinations verified by CI. Structure example, not a version recommendation:

| Profile | JDK/GraalVM | Spring Boot | Native Build Tools | Build tool | Target |
|---|---|---|---|---|---|
| Current | Pinned version | Released version | Pinned version | Pinned wrapper | linux/amd64 glibc |
| Upgrade candidate | Proposed version | Target version | Compatible version | Compatible wrapper | linux/amd64 glibc |
| Secondary target | Same release policy | Same release policy | Same release policy | Same wrapper policy | linux/arm64 |

Each row needs results for build, JVM tests, AOT, native compilation, native tests, container tests, and benchmarks. Clearly mark unsupported or untested combinations; never extrapolate amd64 results to arm64 or glibc to musl.

## 12. Read Migration Guides in Upgrade Order

A practical sequence reduces the number of moving variables:

1. Upgrade JDK/toolchain to a version supported by the current stack.
2. Upgrade Gradle/Maven Wrapper if required by the target version.
3. Upgrade Spring Boot along with its plugins/BOM.
4. Update code per the Spring Framework migration guide.
5. Upgrade GraalVM distribution/Native Image.
6. Upgrade Native Build Tools per the compatibility matrix.
7. Upgrade builder/runtime base images and native packages.
8. Re-run the entire pipeline and benchmarks.

This order can change if release notes require a specific pairing. Document dependencies between steps. You don't need to upgrade everything in a single commit if it can be split into smaller reviewable changes.

## 13. Check Deprecated APIs and Breaking Changes

Look for signals:

- Compiler deprecation warnings.
- Plugin warnings about obsolete tasks/configurations.
- Deprecated/removed Spring APIs.
- Renamed properties or changed defaults.
- Changed auto-configuration conditions.
- Changed `RuntimeHints` APIs or metadata formats.
- Removed JDK APIs or unavailable modules.
- Unsupported GraalVM options.

Enable compiler/plugin warnings on the upgrade branch and save logs. Do not suppress warnings wholesale just to make the pipeline green; separate new warnings, pre-existing warnings, and dependency warnings.

For property migrations, check effective configuration in both JVM and native runs. Obsolete properties may be silently ignored without failing the build.

## 14. Upgrade Third-Party Dependencies

The Spring Boot BOM does not manage every dependency. Inventory libraries with deep integration:

- JDBC drivers and connection pools.
- Jackson/serialization modules.
- Security/OAuth/JWT.
- HTTP clients and TLS providers.
- Messaging clients.
- Logging/metrics/tracing exporters.
- JNI/native libraries.
- Cloud/vendor SDKs.
- Libraries shipping reachability metadata.

Read each vendor's release notes and Native Image support matrix. Check whether the library ships official reachability metadata, supports the newer GraalVM version, and changes native binaries across OS/architectures.

Do not upgrade a dependency solely because a newer version exists. Evaluate compatibility, security fixes, CVEs, licenses, runtime behavior, and build reproducibility.

## 15. Run a Post-Upgrade Verification Pipeline

An upgrade candidate should pass through layered checks:

| Stage | Required evidence |
|---|---|
| Dependency resolution | Dependency tree/lockfile has no unexpected conflicts |
| Compile | Main/test sources compile |
| JVM tests | Unit and integration tests pass |
| Spring AOT | AOT processing completes with target profiles |
| Native compile | Native Image build succeeds |
| Native tests | Tests run on native executable or native test runtime |
| Smoke test | Process start, readiness, and shutdown succeed |
| Container test | Final image runs with expected user/base image/architecture |
| Feature tests | JSON, TLS, database, resources, proxies, JNI per feature |
| Performance | Startup, RSS, throughput/latency compared to baseline |

Passing native compilation does not prove runtime passes. Passing JVM tests does not prove complete native reachability. Verify the exact packaged and deployed artifact.

## 16. Example Spring Boot and GraalVM Upgrade Workflow

Suppose a project runs a pinned Spring Boot release line, JDK/GraalVM, and Native Build Tools. The team wants to upgrade Spring Boot and GraalVM.

**Before editing:**

- Record current versions from the build manifest.
- Save dependency tree, toolchain output, and builder digest.
- Run the current pipeline to establish the baseline.
- Save startup/RSS benchmarks and test reports.

**During upgrade:**

- Read system requirements and migration guide for the target Spring Boot release.
- Identify the Spring Framework version managed by the BOM.
- Read GraalVM release notes and Native Image compatibility.
- Check Native Build Tools/Gradle compatibility.
- Update wrapper/plugins/dependency locks.
- Fix deprecated APIs, hints, and build arguments per the guides.

**After upgrading:**

- Run the JVM/AOT/native/container pipeline.
- Verify JSON/TLS/resources/profiles and JNI libraries.
- Compare performance under the same protocol.
- Save the new manifest and review results.
- Promote only the verified artifact.

## 17. When Vendor Documentation Conflicts

Sometimes one document states a JDK version is supported while a plugin or dependency requires another version. Handle it systematically:

1. Verify each document applies to the exact product/version/distribution.
2. Prioritize the official compatibility matrix/release notes of the owning component.
3. Check publication dates and whether documentation was updated for patch releases.
4. Distinguish minimum requirements from tested combinations.
5. Create a minimal reproduction or compatibility spike in CI.
6. Document the chosen combination and unverified limits.
7. If no intersecting combination exists, pick another version line or wait for vendor support.

Never resolve conflicts by forcing versions or stripping dependency constraints without tests. A single successful build does not turn an unsupported combination into a vendor-supported one.

## 18. Record Evidence and Upgrade Decisions

Every upgrade pull request should include:

- Current/target version table.
- Links/names of cross-referenced release notes and migration guides.
- Compatibility matrix of JDK, GraalVM, Spring Boot, plugins, and build tools.
- Dependency diff and lockfile changes.
- Native Image argument changes.
- Stage-by-stage test results.
- Container builder/runtime image digests.
- Before/after benchmarks if performance is affected.
- Known limitations and rollback path.

Do not just write "bumped versions." Reviewers need to see why the new combination is compatible and what evidence proves the application works.

## 19. Pre-Acceptance Upgrade Checklist

- Read Spring Boot system requirements and migration guide for the exact target version.
- Identified the Spring Framework version managed by the BOM.
- Read Spring Framework What's New/upgrade notes for relevant AOT APIs.
- Checked JDK vendor/version and GraalVM distribution/Native Image compatibility.
- Read GraalVM release notes on options, targets, linker, and metadata.
- Checked Native Build Tools plugin compatibility with Gradle/Maven.
- Pinned wrapper and plugin versions.
- Verified third-party dependencies with native/reachability support.
- Verified Buildpacks builder/run image or Docker base image.
- Recorded results for JVM tests, Spring AOT, Native Image compile, and native tests.
- Smoke/integration tested the final container image on the target architecture/libc.
- Compared performance against baseline where impacted.
- Recorded release evidence and rollback path.

## 20. Self-Check Questions

1. Why does a JDK minimum requirement not prove the entire Native Image toolchain is compatible?
2. How does the Spring Boot BOM help manage the Spring Framework version?
3. Which parts of the Spring Framework upgrade guide matter most for AOT?
4. Which components must Native Build Tools be compatible with?
5. Why should you read GraalVM release notes before keeping old build arguments?
6. What is the difference between minimum, supported, and tested combinations?
7. Why must OS/architecture/libc be tested separately?
8. When vendor documentation conflicts, how do you make an evidence-based decision?
9. Which stages must run after upgrading Spring Boot/GraalVM?
10. What evidence should an upgrade pull request store for reviewers?

**Key takeaway:** cross-reference exact documentation and versions for every component, identify the intersecting compatible region, and record it in a project compatibility matrix. After upgrading, verify from dependency resolution and Spring AOT through Native Image, native tests, and the final container on the exact target before promoting.
