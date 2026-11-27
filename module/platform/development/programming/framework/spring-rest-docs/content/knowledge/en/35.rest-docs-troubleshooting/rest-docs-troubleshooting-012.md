# Spring Framework or REST Assured Version Incompatibility

Spring REST Docs works alongside test frameworks and HTTP client libraries to record requests and responses. When upgrading Spring Boot, Spring Framework, Spring REST Docs, or REST Assured, dependencies can become incompatible. Common symptoms include dependency resolution failures, compilation errors due to API changes, `NoSuchMethodError`/`NoClassDefFoundError` at test runtime, a recorder failing to initialize, or snippets not being generated.

The proper approach is to identify the actual resolved versions of every dependency on the test runtime classpath, check compatibility, and select a consistent set of versions. Never try to fix errors by randomly adding another version to dependencies; doing so can introduce multiple Spring versions simultaneously and make errors even harder to diagnose.

This lesson belongs to the **Troubleshooting** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating snippets for requests, responses, payloads, parameters, and headers, then assembling Asciidoctor/Markdown and integrating with build and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify compatibility issues between Spring Boot, Spring Framework, and Spring REST Docs.
2. Check actual resolved versions instead of only looking at directly declared versions.
3. Distinguish compile-time, dependency-resolution, and runtime linkage errors.
4. Select the right REST Assured artifact and version compatible with your JDK/Spring stack.
5. Detect `javax`/`jakarta` conflicts and overridden dependencies.
6. Use dependency trees to trace which library pulls in an unwanted version.
7. Restore a consistent dependency set and verify documentation tests.

## 2. Recognizing Symptoms

| Symptom | Likely root-cause category |
| --- | --- |
| Could not resolve artifact/version | Missing or incompatible repository, artifact coordinates, or version |
| Compilation error: cannot find symbol | API change, wrong package/import, or missing compile dependency |
| `NoSuchMethodError` | Runtime loads a different class version than compile time |
| `NoClassDefFoundError` / `ClassNotFoundException` | Missing artifact, wrong module, or excluded dependency |
| `NoSuchFieldError` / `AbstractMethodError` | Binary modules are not from the same version line |
| `ClassCastException` between Spring types | Multiple versions of the same package/class or different classloaders |
| Test context fails to start | Spring Boot/Framework/test dependencies are out of sync |
| MockMvc/WebTestClient setup fails | Wrong Spring REST Docs integration module or API change |
| REST Assured filter not invoked | Wrong artifact, filter API, or dependency version |
| Tests run without generating snippets | Recorder not attached properly, tests skipped, or an independent config error |

An error message is a clue, not a conclusion. Inspect the first meaningful stack trace, which JAR the class was loaded from, and the test runtime dependency graph.

## 3. Version Layers That Must Align

| Component | Role |
| --- | --- |
| JDK | Determines Java bytecode and APIs supported at build and runtime |
| Spring Boot | Manages dependency versions via dependency management/BOM |
| Spring Framework | Provides Spring MVC, WebFlux, TestContext, and MockMvc |
| Spring REST Docs | Provides the core API and integration modules |
| REST Assured | Provides the HTTP DSL, request specification, and filters |
| JUnit / TestNG | Test engine and lifecycle APIs |
| Gradle / Maven | Resolves dependencies, compiles, and runs tests |
| Asciidoctor plugin | Renders documentation from snippets and sources |

An individual version may be valid on its own while the overall combination is invalid. Spring REST Docs integrations require the right Spring Test API; REST Assured needs the artifact matching the test stack; the JDK must meet the requirements of both libraries and plugins.

## 4. Checking Which Spring Version Is Actually Used

### 4.1. Spring Boot Dependency Management

If the project uses Spring Boot, prefer the dependency management/BOM provided by the Boot version. Avoid manually declaring versions for individual Spring Framework modules without a verified reason.

Gradle example:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.restdocs:spring-restdocs-mockmvc")
}
```

Maven example when using the Spring Boot parent or BOM:

```xml
<dependency>
  <groupId>org.springframework.restdocs</groupId>
  <artifactId>spring-restdocs-mockmvc</artifactId>
  <scope>test</scope>
</dependency>
```

Omit the Spring REST Docs version only when the active dependency management manages that version. If no BOM or parent manages it, declare the explicit version according to the corresponding release documentation.

### 4.2. Do Not Mix Spring Framework Versions Arbitrarily

Spring Framework modules such as `spring-core`, `spring-context`, `spring-test`, `spring-webmvc`, and `spring-webflux` generally belong to the same release train. If a dependency pulls in a `spring-test` version different from `spring-webmvc`, tests may compile yet fail at runtime.

Do not fix this by appending the latest `spring-test` version at the end of the build file. Identify which BOM/parent manages the versions and which dependency is overriding it.

## 5. Choosing the Right Spring REST Docs Integration Module

| Test client | Common integration module |
| --- | --- |
| MockMvc | `spring-restdocs-mockmvc` |
| WebTestClient | `spring-restdocs-webtestclient` |
| REST Assured | `spring-restdocs-restassured` |

Pick the module matching the test client in use. Do not add all three modules as a workaround if the project only uses one client type.

Maven example for MockMvc:

```xml
<dependency>
  <groupId>org.springframework.restdocs</groupId>
  <artifactId>spring-restdocs-mockmvc</artifactId>
  <scope>test</scope>
</dependency>
```

Gradle example:

```groovy
testImplementation(
    "org.springframework.restdocs:spring-restdocs-mockmvc:<version-managed-by-project>"
)
```

Replace the version placeholder with the version managed by your project. Choose a version compatible with your Spring stack and JDK; do not copy versions from guides targeting a different release train.

### 5.1. Core and Integration Modules

Each integration module depends on the Spring REST Docs core API. Avoid declaring two different versions for core and integration modules. If dependency management does not govern them, pin both to the same release version per the Spring REST Docs release notes.

A `NoSuchMethodError` in the `org.springframework.restdocs` package can indicate mismatched REST Docs modules at runtime or differences between the test compile and runtime classpaths.

## 6. REST Assured Compatibility

REST Assured provides separate modules/artifacts for its core DSL, Spring MockMvc, and WebTestClient in their respective setups. Artifact coordinates and APIs can change across version lines.

When using REST Assured with Spring REST Docs:

1. Determine whether tests send requests via standalone REST Assured or integrated MockMvc/WebTestClient.
2. Select the exact REST Assured module for that integration.
3. Select the Spring REST Docs REST Assured integration module.
4. Verify that the REST Assured version and Spring REST Docs version are compatible with the JDK and test APIs.
5. Verify that no REST Assured core/module is resolved in two different versions.

Illustrative dependency declaration:

```groovy
dependencies {
    testImplementation("io.rest-assured:rest-assured:<ra-version>")
    testImplementation(
        "org.springframework.restdocs:spring-restdocs-restassured:<restdocs-version>"
    )
}
```

Replace the placeholders with versions chosen from the compatibility/release documentation of the matching library lines. Then verify the dependency graph.

### 6.1. Filter API Errors After Upgrading

If code no longer compiles on filter calls, request specifications, or MockMvc/WebTestClient setup:

- Read the first compile error and identify the changed class or method.
- Check that imports point to the right package and artifact.
- Cross-check the API docs/changelog for the active version.
- Check whether examples in the project call deprecated APIs that were removed.
- Update test code to the new API rather than adding an old JAR to keep legacy APIs around.

## 7. JDK and Build Tools Are Also in the Compatibility Matrix

A library may be compatible with Spring yet require a newer JDK. Build tools and plugins also have their own runtime requirements.

Check the JDK running Gradle/Maven, the Java toolchain used for compilation, the Gradle/Maven wrapper, the Asciidoctor plugin, bytecode target/source compatibility, and the JDK on the CI runner.

Basic verification commands:

```bash
java -version
./gradlew --version
./mvnw -version
```

Run only the commands matching your project's build tool. With Gradle, the wrapper version and the JVM running Gradle can differ from the toolchain used to compile the project.

## 8. `javax` and `jakarta` Conflicts

A major shift in the Java ecosystem moved many enterprise APIs from the `javax` namespace to `jakarta`. Spring Framework 6 and Spring Boot 3+ rely on the Jakarta EE namespace for related integrations.

Common symptoms:

- `ClassNotFoundException` for `javax.*` or `jakarta.*` packages.
- Method signature mismatches caused by a module using the old namespace.
- Servlet API or validation API pulled in at an incompatible version.
- Both old and new APIs present on the test runtime classpath.

Do not mass-replace imports just to silence errors. Identify the Spring Boot/Framework major version, servlet container/API, and integration libraries. For a Spring Boot 3 / Spring Framework 6 stack, verify that related dependencies have migrated to compatible Jakarta versions. If the project uses an older Spring stack, select the matching namespace and integrations.

Spring REST Docs does not migrate an application from `javax` to `jakarta`; that is a full dependency and application stack upgrade.

## 9. Using the Dependency Tree to Find Pulled-In Versions

### 9.1. Gradle

List test runtime dependencies:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Find why a particular version was chosen for a module:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

Also inspect `spring-core`, `spring-webmvc`, `spring-restdocs`, `rest-assured`, and the servlet API. `dependencyInsight` shows which dependency requested a version, which version was selected, and whether any resolution rule substituted it.

### 9.2. Maven

View the dependency tree:

```bash
./mvnw dependency:tree -Dscope=test
```

Filter by library group if the output is long:

```bash
./mvnw dependency:tree -Dscope=test -Dincludes=org.springframework
./mvnw dependency:tree -Dscope=test -Dincludes=org.springframework.restdocs
./mvnw dependency:tree -Dscope=test -Dincludes=io.rest-assured
```

Inspect dependency management and the effective POM when versions originate from a parent/BOM or profile.

## 10. Interpreting Linkage Errors

| Exception | Typical meaning | What to check |
| --- | --- | --- |
| `NoSuchMethodError` | Runtime class lacks a method required by compiled code | Actual JARs, duplicate versions, dependency mediation |
| `NoClassDefFoundError` | Required class is absent at runtime or class initialization failed | Missing artifact, scope, static initialization cause |
| `ClassNotFoundException` | Code/classloader requested a class that was not found | Artifact, package namespace, classpath |
| `NoSuchFieldError` | Field is missing from the runtime class version | Module version mismatch |
| `AbstractMethodError` | Implementation does not satisfy the runtime interface | API and implementation versions |
| `IncompatibleClassChangeError` | Incompatible class or interface binary structure | Binary compatibility across dependencies |

A stack trace may wrap the root exception. Read the first cause containing class/method information and determine which JAR provides that class. In Gradle, `dependencyInsight` and `testRuntimeClasspath` are the starting points; in Maven, use `dependency:tree` and inspect resolved artifacts.

## 11. Systematic Troubleshooting Workflow

1. **Capture the error:** obtain the full compile error or stack trace, not just the last line.
2. **Identify the phase:** dependency resolution, compile, test context startup, test execution, or rendering.
3. **Record environment versions:** JDK, Gradle/Maven, Spring Boot, Spring Framework, Spring REST Docs, and REST Assured.
4. **Inspect the dependency graph:** find modules pulled in at multiple versions or overridden versions.
5. **Check compatibility:** compare against release notes and reference docs for the exact versions.
6. **Choose one cohesive version set:** use the Boot BOM/parent where appropriate; avoid ad-hoc overrides.
7. **Resolve cleanly:** refresh dependencies if needed and clean outputs.
8. **Run the smallest test:** start with a single documentation test using the relevant integration module.
9. **Run all docs tests:** verify snippets are generated properly.
10. **Render documentation:** do this only after tests pass.

Do not upgrade every dependency to `latest` at once as a guess. Changing many variables simultaneously makes it hard to tell which dependency caused the failure.

## 12. Scenario Walkthroughs

### Scenario A: `NoSuchMethodError` in Spring Test

The application compiles successfully, yet running a MockMvc documentation test throws `NoSuchMethodError` in a Spring Test class.

Resolution:

- Run `dependencyInsight` for `spring-test` and `spring-webmvc`.
- Verify whether they belong to the same release train.
- Check whether the Spring Boot BOM was overridden by a directly declared dependency version.
- Remove unnecessary overrides and let the BOM manage versions consistently.
- Re-run one MockMvc test and then all documentation tests.

### Scenario B: REST Assured Filter Fails to Compile After Version Upgrade

A filter call or request specification no longer matches the method signature.

Resolution:

- Confirm the exact REST Assured artifact and resolved version in use.
- Verify imports point to the API of the right module.
- Read the migration/release notes for the new REST Assured version.
- Update test code to match the new API.
- Verify the Spring REST Docs REST Assured integration belongs to a compatible line.

### Scenario C: `ClassNotFoundException` After a Spring Boot Major Upgrade

Tests report missing classes under `javax` or `jakarta`.

Resolution:

- Identify the Spring Boot and Spring Framework major versions.
- Identify the application's servlet container and API namespace.
- Locate old dependencies pulling in `javax` or mismatched dependencies pulling in `jakarta`.
- Upgrade or configure integration libraries compatible with the chosen stack.
- Run test context startup and documentation tests to verify.

## 13. Pre-Upgrade Verification Matrix

Maintain a version table verified by the project:

| Component | Current version | Check |
| --- | --- | --- |
| JDK | Per toolchain/CI | Supported by libraries and plugins |
| Spring Boot | Per parent/BOM | Manages Spring versions |
| Spring Framework | Managed by BOM | Modules stay aligned |
| Spring REST Docs | Unified version | Core and integration modules stay aligned |
| REST Assured | Per compatibility docs | Appropriate artifacts and APIs |
| JUnit | Per test stack | Compatible test engine |
| Gradle/Maven | Pinned wrapper | Compatible with plugins and JDK |
| Asciidoctor plugin | Pinned version | Runs on the build runtime |

Update this table when upgrading the framework or test clients. Record the CI-verified versions so teammates do not have to guess from build scripts.

## 14. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Multiple `spring-test` versions | Dependency override or transitive conflict | Use the BOM and inspect the dependency tree |
| REST Docs core/integration version mismatch | Separately declared versions | Align on the same release version |
| REST Docs class not found | Missing integration module or wrong scope | Add the module matching the test client in `test` scope |
| REST Assured filter API mismatch | Wrong artifact/version or API change | Check release notes and imports |
| `javax`/`jakarta` `ClassNotFound` | Stack namespace mismatch | Align dependencies with the Spring major version |
| Tests compile but fail at runtime | Compile and runtime classpaths differ | Inspect `testRuntimeClasspath`/dependency tree |
| Fails in CI, passes locally | Different JDK or dependency resolution | Pin wrapper/JDK and inspect the CI graph |
| Asciidoctor plugin fails to run | Plugin requires a different JDK or build tool | Check plugin compatibility |
| Still fails after refreshing dependencies | Version constraints/BOM still select conflicting version | Inspect `dependencyInsight`/effective POM |
| Upgraded many libraries at once | Unable to isolate root cause | Change one group at a time and run tests |

## 15. Best Practices

1. Use the Spring Boot BOM/parent to manage Spring dependencies when the project uses Boot.
2. Keep Spring Framework modules on the same release train.
3. Align Spring REST Docs core and integration module versions.
4. Choose the exact integration module for MockMvc, WebTestClient, or REST Assured.
5. Verify REST Assured artifacts/APIs against actual versions instead of copying dependencies from examples on another line.
6. Pin the JDK, Gradle/Maven wrapper, and plugin versions.
7. Inspect dependency tree/insight before adding exclusions or overrides.
8. Handle `javax`/`jakarta` transitions across the entire stack.
9. Upgrade one dependency group at a time, running a small test first and then all documentation tests.
10. Document the CI-verified version matrix.

## 16. Hands-On Exercise

A Spring Boot project uses MockMvc and Spring REST Docs. After upgrading dependencies, documentation tests fail with `NoSuchMethodError` in Spring Test. Another module declares REST Assured with an explicit version.

**Tasks:**

1. Record the JDK, Gradle/Maven wrapper, Spring Boot, and Spring REST Docs versions.
2. Run `dependencyInsight` or `dependency:tree` for `spring-test`, `spring-webmvc`, and `spring-restdocs`.
3. Identify which dependency overrides the version managed by the BOM.
4. Verify whether the REST Docs core and integration modules share the same version.
5. Inspect the REST Assured artifact/version and why that module is needed.
6. Remove unnecessary overrides or adjust versions according to compatibility documentation.
7. Run one MockMvc documentation test.
8. Run all documentation tests and verify snippets are generated.
9. Render Asciidoctor.
10. Record the verified version matrix in project documentation.

**Completion criteria:** consistent dependency graph; no remaining linkage/classpath errors; integration module matches the test client; documentation tests pass; snippets and documentation render successfully.

## 17. Key Takeaways

- Compatibility failures can originate from Spring Boot, Spring Framework, Spring REST Docs, REST Assured, the JDK, or build plugins.
- Inspect actual versions on the runtime classpath, not just directly declared versions.
- Use an appropriate BOM/parent to keep Spring modules aligned.
- Pick the exact Spring REST Docs integration module for MockMvc, WebTestClient, or REST Assured.
- Use `dependencyInsight` or `dependency:tree` to locate dependencies pulling in unwanted versions.
- `NoSuchMethodError` usually points to a compile/runtime binary mismatch; `ClassNotFoundException` usually points to a missing artifact or wrong namespace.
- Verify `javax`/`jakarta` alignment according to the Spring major version and the full stack.
- After fixing dependencies, run documentation tests and re-render documentation.
