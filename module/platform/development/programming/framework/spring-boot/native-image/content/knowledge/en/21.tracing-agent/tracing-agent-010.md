# Rebuilding and Testing Native After Combining Hints with Agent Results

## 1. Goal of the Combining and Testing Step

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed with **Spring AOT** and compiled into a **GraalVM Native Image** to evaluate compatibility, startup time, memory usage, and container operations. When the application involves reflection, resource lookups, dynamic proxies, serialization, or JNI, the team can use the **Native Image Tracing Agent** to observe dynamic access paths on the JVM and generate reachability metadata.

Agent results are only one source of information. A Spring Boot application may also have:

- Spring Runtime Hints declared via `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, or binding annotations.
- Native Image metadata provided by dependency JARs.
- Metadata retrieved from the GraalVM Reachability Metadata Repository.
- Metadata recorded by the tracing agent from executed tests or application flows.
- Supplemental configuration reviewed and maintained by the development team in source.

The goal of this lesson is to combine these sources into reproducible native build inputs, then rebuild and run the same test suite on the native executable. Neither agent-generated JSON nor a native compiler exit code of 0 should be treated as final proof. Results must demonstrate that the application preserves correct behavior after merging metadata.

After this lesson, learners can:

1. Distinguish Spring Runtime Hints, dependency metadata, and tracing agent metadata.
2. Collect metadata from multiple JVM scenarios into one safe directory.
3. Review, filter, and merge agent results with existing metadata.
4. Place approved metadata into the proper location on the native build classpath.
5. Configure metadata copying for Maven/Gradle Native Build Tools.
6. Rebuild the executable with the right GraalVM/toolchain and inspect outputs.
7. Run native unit/integration/smoke tests with the same data used on the JVM.
8. Detect missing metadata, excess metadata, version mismatches, or environment/platform errors.
9. Record evidence, coverage, and release decisions.

> **Principle:** the agent records accesses that occurred in instrumented processes. Spring hints describe needs declared in code. Dependency metadata describes library requirements. Keep the origin of every configuration clear, review the results, and only then use them to build native.

## 2. How Do the Three Metadata Sources Work Together?

### 2.1. Spring Runtime Hints

Spring Runtime Hints are declared in source code via the Spring Framework API. For example, a registrar registering a plugin constructor and template resources:

~~~java
public final class OrderRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            OrderPlugin.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("templates/order-*.txt");
    }
}
~~~

The registrar is wired into the application context with the `@ImportRuntimeHints` annotation. Spring AOT processes these hints while preparing the application. Keep them in source code so reviewers can see the rationale and tests can verify them with `RuntimeHintsPredicates`.

### 2.2. Library Metadata

A dependency may package reachability metadata inside its own JAR's `META-INF/native-image/` directory, or Native Build Tools may fetch metadata from the GraalVM Reachability Metadata Repository. These configurations describe the dependency's requirements for the matching artifact/version.

Do not copy metadata from a different dependency version assuming it fits. When upgrading a library or GraalVM version, re-verify schemas, version conditions, and related features.

### 2.3. Tracing Agent Results

The tracing agent attaches to a **JVM process** and observes dynamic accesses occurring while the program runs. It can record metadata for reflection, resources, dynamic proxies, JNI, and other Native Image-supported mechanisms.

The agent cannot know on its own what an unexecuted business flow will need. If tests only exercise a successful order-creation flow, metadata for retries, validation errors, alternative plugins, or other profiles may not appear.

### 2.4. Overall Flow Diagram

~~~mermaid
flowchart TD
    A[Spring RuntimeHints in source] --> D[Spring AOT processing]
    B[Dependency JARs and metadata repository] --> E[Native classpath]
    C[JVM scenarios run with tracing agent] --> F[Agent metadata output]
    F --> G[Review, filter, and merge]
    G --> H[META-INF/native-image in application resources]
    D --> I[Native Build Tools]
    E --> I
    H --> I
    I --> J[GraalVM Native Image build]
    J --> K[Native executable]
    K --> L[Native unit/integration/smoke tests]
    L --> M[Compatibility and release evidence]
~~~

This is a conceptual diagram. The exact task graph, generated outputs, and how metadata is copied depend on your Spring Boot and Native Build Tools versions.

## 3. Preparation Before Running the Agent

Before collecting metadata, lock in the same configuration for both the JVM run and the native build:

- Commit/source revision under test.
- Spring Boot and Spring Framework versions.
- JDK/GraalVM distribution and version.
- Maven/Gradle Native Build Tools version.
- Dependency graph and active profiles.
- OS/architecture of the build host and target runtime.
- Test fixtures, environment variables, and required external services.
- Runtime Hints already declared in source.
- Existing metadata in dependency JARs and application resources.

Record the GraalVM JDK version:

~~~bash
java -version
native-image --version
~~~

If Gradle uses Java toolchains or the Maven plugin selects a different GraalVM than the terminal, inspect the native build logs to confirm which executable and toolchain were actually used. The tracing agent should come from the GraalVM JDK matching the build toolchain; do not mix outputs from different agent/schema versions without checking compatibility.

### 3.1. Create a Dedicated Working Directory for the Agent

In examples, use:

~~~text
target/
└── tracing-agent/
~~~

This is a temporary directory for collection and review. Do not write the first raw output straight into a reviewed metadata directory in source if you do not yet know which files the agent will emit. Keeping a raw output copy lets you diff and strip unnecessary entries.

For Gradle, the plugin's default output directory is typically under `build/native/agent-output/<taskName>`. For Maven, Native Build Tools may use `target/native/agent-output`. Check your exact logs and plugin version before copying.

### 3.2. Identify Scenarios to Execute

Build a list of paths involving dynamic access. For a Spring Boot service, this may include:

| Category | Scenarios to Run |
| --- | --- |
| Reflection | Instantiate each configured plugin implementation and invoke required constructors/methods. |
| Binding/JSON | Standard DTOs, records, generic collections, nested DTOs, polymorphic subtypes. |
| Resource | Read templates, schemas, certificates, resource bundles, and classpath config files. |
| Proxy | Create JDK dynamic proxies or integration proxies used by the application. |
| Serialization | Serialize/deserialize actual types, including error payloads if any. |
| JNI/native library | Load and invoke native integration paths if used by the application. |
| Error paths | Validation errors, retries, fallbacks, exception mapping, and invalid inputs. |
| Profile/configuration | Profiles or feature flags that change selected classes/resources. |

Include only features that genuinely belong to the application. Scenarios need representative data and expected outcomes so they can be re-run later on the native executable.

## 4. Collecting Metadata from the JVM with the Tracing Agent

### 4.1. Running the Spring Boot Executable JAR

After building the JVM JAR, run it with the agent:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar
~~~

Replace `orders-service.jar` with your actual artifact. The agent option must appear before `-jar` and application arguments. If passing profiles or application arguments, place them after the JAR name:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check
~~~

After the application starts, call APIs or execute the planned scenarios. When finished, stop the application gracefully so the JVM exits and the agent writes final metadata. For long-running server applications, periodic write options such as `config-write-period-secs` can be used if appropriate for your GraalVM version; still verify output after the process exits.

**The agent must run on the JVM.** Do not attach `native-image-agent` to a pre-built native executable. A native executable is not a JVM process that this agent can instrument.

### 4.2. Collecting Multiple Scenarios into the Same Directory

The first run uses `config-output-dir` to create the metadata set:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=orders
~~~

Subsequent runs use `config-merge-dir` to append to the existing configuration:

~~~bash
java \
  -agentlib:native-image-agent=config-merge-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=payments
~~~

Continue with resource, error-handling, or other plugin scenarios:

~~~bash
java \
  -agentlib:native-image-agent=config-merge-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=error-paths
~~~

`config-merge-dir` instructs the agent to extend the existing configuration set rather than overwriting the previous run's output. If multiple processes run concurrently, do not let them write into the same directory. Use a separate output directory per process/scenario and merge with GraalVM-supported tooling, or run sequentially with `config-merge-dir`.

If an application exits only upon receiving a stop signal, ensure shutdown hooks run so the agent gets a chance to write files. Do not read the output directory while the process is still writing and conclude the files are complete.

### 4.3. Running the Agent via `JAVA_TOOL_OPTIONS`

When you cannot modify the launch command, you can inject the agent via `JAVA_TOOL_OPTIONS`:

~~~bash
export JAVA_TOOL_OPTIONS="-agentlib:native-image-agent=config-output-dir=target/tracing-agent"
./mvnw spring-boot:run
~~~

This approach depends on the shell, launcher, and how child processes inherit environment variables. If multiple JVM processes pick up this variable, each process must have its own output directory to avoid overwrites or conflicts.

Once collection finishes, unset `JAVA_TOOL_OPTIONS` before running ordinary JVM tests or native builds. Do not accidentally keep collecting metadata on unintended builds.

## 5. Using Maven Native Build Tools to Collect and Copy Metadata

The Maven plugin can automatically attach the agent to test processes and copy metadata back into the project. Exact configuration depends on the plugin version; example structure in `native-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <agent>
            <enabled>true</enabled>
            <metadataCopy>
                <merge>true</merge>
                <outputDirectory>
                    src/main/resources/META-INF/native-image/com.example/orders-service
                </outputDirectory>
            </metadataCopy>
        </agent>
    </configuration>
</plugin>
~~~

This is an illustrative snippet to integrate into an existing plugin/profile. Preserve your existing version, executions, `mainClass`, build arguments, and Spring Boot settings.

You can enable the agent for a single run via property:

~~~bash
./mvnw -Pnative -Dagent=true test
~~~

If `metadataCopy` is configured, run the copy goal per your plugin version:

~~~bash
./mvnw -Pnative -Dagent=true test native:metadata-copy
~~~

If your POM permanently sets `enabled` to `true`, the agent will continue attaching to subsequent Maven runs. After collecting/copying, disable the agent in configuration or move agent activation to a dedicated collection profile/property. Then re-run tests/builds **without the agent enabled** to confirm metadata was copied and the native build uses the reviewed results. If your project uses a Maven profile other than `native`, adjust commands to match your real profile.

`metadataCopy` can merge output with existing metadata in `outputDirectory` when `merge` is enabled. This helps prevent overwriting existing manual metadata. Always review contents after copying; a mechanical merge does not replace evaluating each entry.

## 6. Using Gradle Native Build Tools to Collect and Copy Metadata

In `build.gradle.kts`, you can configure the agent and metadata copy using the plugin's DSL:

~~~kotlin
graalvmNative {
    agent {
        enabled.set(true)

        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add(
                "src/main/resources/META-INF/native-image/com.example/orders-service"
            )
            mergeWithExisting.set(true)
        }
    }
}
~~~

With Groovy DSL, property setters can use assignment syntax depending on plugin version:

~~~groovy
graalvmNative {
    agent {
        enabled = true

        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add(
                "src/main/resources/META-INF/native-image/com.example/orders-service"
            )
            mergeWithExisting = true
        }
    }
}
~~~

Run JVM tests with the agent:

~~~bash
./gradlew -Pagent test
~~~

Once tests have run and the agent has produced metadata, copy it to resources:

~~~bash
./gradlew metadataCopy
~~~

Then disable the agent and run normal native tests/builds:

~~~bash
./gradlew clean test
./gradlew nativeTest
./gradlew nativeCompile
~~~

If the plugin version requires specifying a mode explicitly, pass the configured mode, e.g., `-Pagent=standard`. With Gradle `java-library`, the plugin may default to `conditional` mode, which requires a user-code filter. Check logs to confirm which mode and tasks were instrumented.

`inputTaskNames` must match the task name run with the agent, such as `test`, `run`, or a dedicated integration test task. `outputDirectories` specifies the destination receiving metadata; `mergeWithExisting` controls whether to merge with existing metadata at the destination.

## 7. Reviewing and Merging Agent Results with Existing Hints

This is the most important step before rebuilding. Agent metadata is observational data; it can contain excess entries, missing entries, or test-framework dependencies.

### 7.1. Check File List and Format

List the output directory:

~~~text
target/tracing-agent/
├── reachability-metadata.json
└── ...
~~~

Depending on the GraalVM release, the agent may create a single `reachability-metadata.json` file or separate config files such as `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `serialization-config.json`, and `jni-config.json`. Use the format supported by the GraalVM version you are building with. Do not change schemas merely by renaming files.

Validate JSON syntax and inspect metadata categories. Pay attention to:
- Reflection entries: type, constructor, method, field, and access category.
- Resource entries: glob/pattern and conditions.
- Proxy entries: interface set.
- Serialization entries: types serialized/deserialized.
- JNI entries: classes/members accessed from native code.
- Conditional metadata: `typeReached` conditions or other conditions if supported by schema/version.

### 7.2. Distinguishing Three Merge Operations

| Operation | Purpose | Where Applied |
| --- | --- | --- |
| Agent `config-merge-dir` | Appends results from the next JVM run into existing agent metadata. | Tracing agent output directory. |
| Native Build Tools `metadataCopy` with merge enabled | Copies and merges agent output with existing metadata at the target directory. | Application resources or metadata output directory. |
| Spring AOT processing Runtime Hints | Converts hints declared in source into AOT/native inputs. | Application context and generated AOT outputs. |

`config-merge-dir` does not read every `RuntimeHintsRegistrar` in source. Nor does `metadataCopy` replace Spring AOT. Keep registrars in source and let Spring AOT process them during the build pipeline.

### 7.3. Avoid Overwriting Manual Metadata

Suppose source already contains:

~~~text
src/main/resources/
└── META-INF/native-image/
    └── com.example/orders-service/
        └── reachability-metadata.json
~~~

If agent output is copied into this exact directory, enable merge as supported by the plugin. Without merge enabled, prior metadata can be overwritten. Before running copy, commit or back up existing files so you can inspect the diff.

If metadata is maintained across multiple subdirectories, you can keep each source in its own classpath entry and let Native Image read them all. You do not have to combine everything into a single file just to have one management location; what matters is that the build classpath includes the right metadata and every entry has a clear origin.

### 7.4. Distinguishing Agent Metadata from Spring-Generated Output

Spring AOT can generate code and metadata in build output. Do not edit generated files directly to add agent entries, because subsequent builds may overwrite them. Instead:

- Keep `RuntimeHintsRegistrar` and annotations in source.
- Keep reviewed agent metadata in application resources or where supported by your plugin.
- Keep library metadata in dependency artifacts.
- Inspect the native build classpath to confirm all sources are consumed.

If an access is already described by Spring hints and also recorded by the agent, check whether both entries target the same scope or different scopes. Duplication does not always cause errors, but avoid maintaining two broad configurations with unclear ownership.

## 8. Filtering Excess Metadata and Removing Test-Framework Traces

When the agent runs on JUnit or integration tests, it can observe accesses from JUnit, the Gradle/Maven test launcher, logging, and test libraries. Those entries may not be needed in the production executable.

### 8.1. Keep Built-in Filters

The Tracing Agent includes built-in caller filters and heuristic filters to drop accesses that Native Image already supports or does not need declared. Do not disable them just to produce a larger metadata file. Disabling filters usually produces less useful, noisier configuration.

### 8.2. Caller Filters and Access Filters Differ

- **Caller filter** filters based on the class/method performing the dynamic access.
- **Access filter** filters the class/member/resource that is the target of the access.

Add custom filters only after understanding which entries are unneeded. For example, you can exclude test-harness callers if you are sure they are not production execution paths. Do not exclude a library's entire package merely because test output contains many entries; the application may need part of that library.

Filter structure and option names depend on the GraalVM version. Consult agent documentation before applying `caller-filter-file` or `access-filter-file`.

### 8.3. Review by Feature

For each agent-generated entry, ask:

1. Does the entry belong to application code, a production library, or the test harness?
2. Which scenario generated this entry?
3. Which application feature requires this entry?
4. Is the entry already described by Spring Runtime Hints or dependency metadata?
5. Can it be narrowed from all members down to a specific constructor/method/field?
6. If the entry is removed, which native test will verify whether it is unnecessary?

Do not bulk-delete metadata just to shrink file size. Use diffs and native regression tests to confirm every narrowing change.

## 9. Placing Approved Metadata on the Native Classpath

Typical location in application resources:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── orders-service/
                └── reachability-metadata.json
~~~

After resource processing:
- Maven typically copies it to `target/classes/META-INF/native-image/...`
- Gradle typically copies it to `build/resources/main/META-INF/native-image/...`

Check output:

~~~bash
find target/classes/META-INF/native-image -type f
~~~

or:

~~~bash
find build/resources/main/META-INF/native-image -type f
~~~

If using PowerShell, use `Get-ChildItem -Recurse` with the corresponding path.

Package the JAR and inspect:

~~~bash
jar tf target/orders-service.jar
~~~

A Spring Boot executable JAR typically places application resources under `BOOT-INF/classes/` and dependency JARs under `BOOT-INF/lib/`. Native Build Tools integrated with Spring Boot must prepare the native classpath accordingly. Do not simply see metadata inside the archive and conclude the native task used it. Confirm in the native build log and output classpath.

If using a metadata directory outside the classpath, GraalVM provides version-specific directory options such as `-H:ConfigurationFileDirectories`. Prefer mechanisms supported by Native Build Tools/Spring Boot and document how metadata is passed into the build for reproducibility.

## 10. Rebuilding Native from Scratch

Once metadata has been reviewed and copied into source resources, run a fresh build. A clean build removes stale outputs from verification; it does not delete metadata in `src/main/resources`.

### 10.1. Maven

With the configured `native` profile and plugin:

~~~bash
./mvnw clean
./mvnw -Pnative test
./mvnw -Pnative package
~~~

If the project configures native test execution, `test` may run both JVM tests and native tests in the plugin-defined order. Check logs/test reports to confirm which tests ran. If you only want to compile the executable and run smoke tests manually:

~~~bash
./mvnw -Pnative -DskipTests package
~~~

Use `-DskipTests` only when tests have already run in a separate step and you intentionally skip tests during the `package` phase. Never use this flag and then report native tests as passing.

### 10.2. Gradle

With Gradle Native Build Tools:

~~~bash
./gradlew clean
./gradlew test
./gradlew nativeTest
./gradlew nativeCompile
~~~

`nativeTest` runs tests on a native test executable if the plugin/test engine is configured. `nativeCompile` builds the main executable. If your test suite uses a dedicated task, configure the corresponding native test binary or run smoke/integration tests against the built executable.

### 10.3. Inspect Build Logs

Verify:

- Correct JDK/GraalVM distribution and version.
- Correct Native Build Tools plugin version.
- Spring AOT ran and recognized configurations with `@ImportRuntimeHints`.
- Dependency graph matches the compatibility matrix.
- Application resource metadata was copied to output.
- Dependency/repository metadata was included in native analysis.
- No JSON schema, missing registration, or conflicting initialization warnings.
- New executable was generated at the expected output path.

Do not accidentally test an old executable after metadata changes. Record timestamp/hash or build output path to guarantee you are running the newly built binary.

## 11. Native Testing After Combining Metadata

The test suite should cover both the exact scenarios used to generate metadata and critical scenarios that were never run under the agent. This uncovers missing metadata caused by insufficient coverage.

### 11.1. Running the Native Executable

Maven example:

~~~bash
./target/orders-service
~~~

Gradle example:

~~~bash
./build/native/nativeCompile/orders-service
~~~

Executable names and output paths depend on plugin configuration. Use the exact path printed in build logs.

Check health endpoints, startup, shutdown, environment variables, logging, and resource files. If running inside a container, use the exact runtime image/OS/architecture planned for deployment.

### 11.2. Re-running the Same Fixtures on JVM and Native

Use the same set of requests/inputs across both modes:

| Scenario | JVM Baseline | Native Executable |
| --- | --- | --- |
| Create order with standard DTO | Expected result and response | Compare identical result |
| Deserialize generic list/map | Correct element types | Does not return raw map or throw reflection error |
| Select plugin by config name | Correct implementation | Class is reached and constructor works |
| Read template/resource | Correct content | Resource is embedded in executable |
| Dynamic proxy | Invokes right interface | Proxy is created and works |
| Serialization/deserialization | Data round-trips cleanly | Equivalent result |
| Error path/retry | Correct status codes and side effects | Equivalent behavior |
| Other profile/configuration | Correct features per profile | Metadata suffices for supported profile |

Do not compare only HTTP status codes. Inspect response bodies, data types, side effects, key logs, database state, and released resources.

### 11.3. Native Tests and Smoke Tests Have Different Roles

- **Native unit tests:** verify small logic and reflection paths inside the native test image.
- **Native integration tests:** verify multiple components/dependencies working together.
- **Smoke tests:** verify executable startup, health endpoints, and primary flows.
- **Container tests:** verify OS libraries, certificates, environment, filesystem, and networking in the runtime image.

Passing a unit test does not prove database drivers or HTTP transports work inside the container. Passing a smoke test does not prove error paths and optional features were checked.

### 11.4. Test Paths Not Yet Observed by the Agent

After the native build passes, proactively execute scenarios not triggered by the tracing agent:
- A rarely used subtype/plugin.
- Another locale/resource bundle.
- A retry or fallback branch.
- A validation/error path.
- Another profile/configuration.
- An optional module enabled in deployment.

If a new test reveals missing metadata, go back to the JVM with the agent, run a reproducing scenario, merge output, review the diff, rebuild, and re-run the regression suite.

## 12. Diagnosing Missing Metadata and Regressions

### 12.1. Native Reports Missing Class/Member/Resource

Identify the error category before adding metadata:

| Symptom | What to Check |
| --- | --- |
| `ClassNotFoundException` | Class name, dependency on classpath, reflection reachability. |
| `NoSuchMethodException` or constructor failure | Constructor signature and invocation metadata. |
| Reflection access/missing registration | Member category, condition, and exact GraalVM schema. |
| Resource not found | Resource path, glob/pattern, whether resource is in JAR/output. |
| Proxy creation error | Exact interface combination and proxy metadata. |
| Serialization error | Concrete type, serializer, subtypes, and serialization metadata. |
| JNI load/link error | JNI metadata, native library, OS/architecture, and shared dependencies. |

Do not add `allDeclaredMethods` or full reflection for an entire package before knowing which member is missing. Reproduce with a small test and add the minimal configuration.

### 12.2. Use Missing-Registration Diagnostics When Supported by Version

Some GraalVM releases support more detailed missing reachability metadata reporting modes, such as `--exact-reachability-metadata` in corresponding versions or runtime reporting modes. Flag names and support timelines depend on the GraalVM release. Check your toolchain's documentation before adding flags to build arguments.

These diagnostics can pinpoint unregistered classes/members, but you still must run the actual feature to trigger the failure. Do not substitute test coverage with a single diagnostic-enabled build.

### 12.3. If the Native Build Passes but Runtime Fails

Investigate in order:

1. Confirm the executable is the newly built binary.
2. Confirm metadata is on the native build classpath.
3. Check whether the scenario was ever run with the agent.
4. Check whether the Spring AOT registrar was imported.
5. Check dependency versions and metadata conditions.
6. Check profile/environment/OS differences from JVM tests.
7. Check JNI/shared libraries, certificates, and system resources.
8. Create a native regression test for the failing operation.

### 12.4. If Metadata Grows Unusually Large

Common causes are test frameworks or broad scenarios triggering many classes. Inspect diffs, classify entries by package/caller/feature, and apply controlled filters. Do not delete entries merely because they belong to a dependency; some accesses may represent real production paths.

## 13. Iterative Workflow When Missing Metadata Is Found

Repeat the following loop until target tests are stable:

~~~mermaid
flowchart TD
    A[Native test detects missing metadata] --> B[Create reproducing JVM scenario]
    B --> C[Run tracing agent into existing output]
    C --> D[Review diff and entry origin]
    D --> E{Needed for production?}
    E -->|No| F[Drop entry or adjust scenario/filter]
    E -->|Yes| G[Keep entry and update metadata]
    F --> H[Clean native build]
    G --> H
    H --> I[Run regression suite on native]
    I --> J{All target scenarios pass?}
    J -->|No| B
    J -->|Yes| K[Record compatibility evidence]
~~~

Each iteration must have a clear reproducing scenario, a reviewable metadata diff, and a regression test confirming the issue is fixed. Do not run the agent repeatedly without saving corresponding scenarios/outputs; otherwise it becomes hard to tell which entry came from which flow.

## 14. Acceptance Criteria Before Release

Consider the combining and testing step complete only when sufficient evidence is gathered:

- Agent metadata was collected from listed, repeatable scenarios.
- Agent outputs were reviewed; test-only and excess entries were handled with justification.
- Spring Runtime Hints remain maintained in source and processed by Spring AOT.
- Library metadata matches artifact/version and was not overwritten.
- Approved metadata sits on the native classpath.
- Native build used the exact right JDK/GraalVM/Native Build Tools.
- Native executable was freshly rebuilt after metadata changes.
- Native unit/integration/smoke tests pass within the defined scope.
- JVM and native produce equivalent results with identical fixtures.
- Container/platform tests cover the target environment.
- Known limitations and untested scenarios are clearly documented.

## 15. Hands-On Exercise: Combining Hints and Agent Metadata for an Order Service

**Context:** a Spring Boot service has `OrderPlugin` selected from config, `Order` DTOs using Jackson, email templates read from the classpath, and a client creating JDK dynamic proxies. The application already has `OrderRuntimeHints`, but native tests detect a missing plugin and resource template in a secondary profile.

### Tasks

1. Record GraalVM/JDK/Spring Boot/Native Build Tools versions and the dependency graph.
2. Read `OrderRuntimeHints` and confirm the registrar is imported into the application context.
3. Build a scenario list covering the default plugin, secondary plugin, JSON binding, templates, and proxies.
4. Run the app/tests on the JVM with `config-output-dir` for the first scenario.
5. Run remaining scenarios using `config-merge-dir` or Maven/Gradle `metadataCopy`.
6. Review metadata: remove entries duplicating hints, test-only entries, overly broad resource patterns, and plugins outside the allowlist.
7. Merge approved metadata into application resources using a plugin-supported merge mechanism.
8. Inspect resource output and JAR; confirm the native classpath uses the metadata.
9. Run a clean native build using Maven or Gradle.
10. Run native unit/integration tests and smoke tests for each profile.
11. Run one additional scenario not used during tracing to check coverage.
12. Record metadata diffs, test reports, build logs, executable path, and conclusions.

### Evidence Record

| Evidence | Contents to Save |
| --- | --- |
| Toolchain | JDK, GraalVM, Spring Boot, Native Build Tools, and platform. |
| Scenario inventory | Scenarios, inputs, profiles, expected results. |
| Agent output | Directory, run timestamp, command, and metadata files. |
| Merge/review | Before/after diff, added/removed entries, rationale, and reviewer. |
| Spring hints | Registrar/annotations, import site, and predicate tests. |
| Dependency metadata | Artifact/version and metadata used. |
| Native build | Command, logs, executable path, and build timestamp/hash. |
| Native tests | Test reports, fixtures, profiles, and outcomes. |
| Container tests | Image/architecture, runtime config, and smoke test results. |
| Known limitations | Unexecuted features, unverified metadata, and next actions. |

### Completion Criteria

- [ ] Collected metadata from at least two distinct JVM scenarios.
- [ ] Properly used `config-output-dir` and `config-merge-dir` for their intended purposes.
- [ ] Distinguished merging across agent runs, `metadataCopy`, and Spring AOT hints.
- [ ] Reviewed and removed unnecessary entries based on evidence.
- [ ] Placed approved metadata onto the native classpath.
- [ ] Rebuilt the executable cleanly with Maven/Gradle.
- [ ] Verified via native tests that plugins, JSON, resources, and proxies work.
- [ ] Executed an additional scenario outside prior agent coverage.
- [ ] Recorded build/toolchain/test evidence for reproducibility.

## 16. Self-Assessment Questions

1. Why must the tracing agent run on the JVM instead of the native executable?
2. When should `config-output-dir` be used, and when should `config-merge-dir` be used?
3. What metadata can the agent miss if scenarios do not traverse error paths or secondary plugins?
4. Why should agent output not directly overwrite reviewed metadata?
5. How does Native Build Tools' `metadataCopy` differ from `config-merge-dir`?
6. At which stage are Spring Runtime Hints processed, and why should registrars still live in source?
7. How can you distinguish production entries from entries generated solely by JUnit/test frameworks?
8. Why does a successful native build not prove native runtime correctness?
9. When must you re-run the tracing agent after a dependency upgrade or profile change?
10. What evidence is required before concluding metadata was merged properly?

## 17. Official Documentation

Agent syntax, metadata schemas, and plugin DSLs change across GraalVM/Native Build Tools releases. Always consult documentation matching your actual toolchain:

- [GraalVM Native Image — Configure with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/): running the agent, `config-output-dir`, `config-merge-dir`, rebuilding, and testing.
- [GraalVM Native Image — Collect Metadata with the Tracing Agent](https://www.graalvm.org/reference-manual/native-image/Agent/): periodic writes, caller/access filters, and supplying metadata to Native Image.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): agent integration, `metadataCopy`, `nativeTest`, and `nativeCompile`.
- [GraalVM Native Build Tools — Maven End-to-End Guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): agent activation, metadata copy, native tests, and troubleshooting missing configuration.
- [Spring Framework — Ahead-of-Time Processing](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints and Spring AOT processing.
- [Spring Boot — GraalVM Native Image](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): building and operating native Spring Boot applications.

**Key takeaway:** agent metadata only reflects observed execution paths; Spring Runtime Hints and library metadata still play their own distinct roles. Review sources, merge using the right mechanism, place approved metadata on the classpath, rebuild the executable cleanly, and run regression tests on native before release.
