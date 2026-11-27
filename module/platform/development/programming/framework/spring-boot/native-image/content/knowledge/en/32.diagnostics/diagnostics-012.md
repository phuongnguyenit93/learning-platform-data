# Minimize a Reproducer and Isolate Whether a Bug Belongs to the Application, Spring, or GraalVM

## 1. Why Do You Need a Minimal Reproducer?

An error appearing only when building or running a Spring Boot Native Image often involves multiple layers: application code, Spring AOT, auto-configuration, third-party libraries, reachability metadata, the GraalVM Native Image builder, the C compiler/linker, and the container environment. Sharing an entire large repository with thousands of log lines makes it difficult for others to pinpoint the failing component or test a specific hypothesis.

A **minimal reproducible example (MRE)** is the smallest project that still reproduces the error with clear execution steps. An MRE helps:

- Confirm the failure is repeatable from a clean checkout.
- Strip out unrelated dependencies and configuration.
- Separate application business-logic bugs from AOT/native bugs.
- Test a specific Spring/GraalVM version or metadata change.
- Produce a self-contained report maintainers can run without accessing internal systems.

The goal of diagnosis is finding the **minimal conditions that trigger the failure**, then identifying which layer owns that behavior. Never conclude "GraalVM bug" merely because an application runs on the JVM yet fails as a native executable; the cause may be missing metadata, a library lacking Native Image support, or application AOT configuration.

After this lesson, you will be able to:

- Establish a JVM/AOT/native baseline using identical dependency versions.
- Shrink a project by removing dependencies, beans, configuration, and code paths one at a time.
- Classify bugs as belonging to the application, Spring Boot/Spring Framework, a third-party library, GraalVM, or the build environment.
- Collect logs and diagnostics at the exact level needed.
- Write an MRE, reproduction README, and actionable issue report.
- Isolate regressions with a version matrix instead of upgrading multiple components at once.

## 2. Start by Describing the Symptom Precisely

Before changing code, record four facts:

1. **Action:** which command ran, which profiles were active, which endpoint/test was invoked?
2. **Actual result:** build failure, process crash, wrong response, which exception occurred?
3. **Expected result:** what should the application do under those same conditions?
4. **Conditions:** JVM or native, local or CI, Linux or Windows, clean build or cached build?

Avoid vague descriptions like "native image doesn't run." Write an observable symptom, for example:

> `./mvnw -Pnative package` builds cleanly. Running `./target/order-service` and sending `POST /orders` throws `MissingReflectionRegistrationError` at `OrderPluginInvoker.invokeCode`. The same test succeeds on the JVM with the exact same dependency tree.

Or:

> `process-aot` fails when analyzing a `@Configuration` class in Spring Boot 4.2.0. The error does not occur when running standard JVM tests. A fresh Spring Boot project containing only that configuration class also reproduces the failure.

These two descriptions lead to different investigation paths. The first prioritizes reachability metadata; the second prioritizes Spring AOT and configuration structure.

## 3. Snapshot the Environment Before Making Changes

Native Image is sensitive to JDK, GraalVM, Native Build Tools, OS, architecture, and native toolchain versions. A report stating only the Spring Boot version is insufficient.

### 3.1. Information to Record

| Category | Information |
|---|---|
| Application | Git commit, branch, failing module, Maven/Gradle command, and profiles |
| Spring | Spring Boot version, Spring Framework version, Spring AOT/plugin version |
| Java | JDK vendor, version, distribution, and architecture |
| GraalVM | Distribution (GraalVM Community/Oracle GraalVM), version, `native-image` version |
| Build tool | Maven/Gradle wrapper version, Native Build Tools plugin version |
| Platform | OS, kernel, CPU architecture, libc, C compiler, and linker |
| Native config | Build arguments, runtime arguments, reachability metadata, and class-initialization options |
| Runtime | Container base image, relevant environment variables, command, and reproducer input |

### 3.2. Gather Information via Commands

On a Linux runner:

```bash
java -version
native-image --version
./mvnw -version
./gradlew --version
uname -a
uname -m
ldd --version
gcc --version
```

If the project uses Maven:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dverbose > target/dependency-tree.txt
```

If the project uses Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath > build/runtime-dependencies.txt
./gradlew buildEnvironment > build/build-environment.txt
```

Record the native options the plugin actually passes to the builder. If you need to inspect the generated command line, enable verbose output or run `native-image --dry-run` on an equivalent build. Do not copy configuration solely from `pom.xml`/`build.gradle`: parent POMs, convention plugins, environment variables, and CI can add extra options.

### 3.3. Keep a Repeatable Baseline

Before dropping dependencies or upgrading versions:

- Commit or save the current patch.
- Keep Maven Wrapper/Gradle Wrapper and lockfiles intact.
- Use the same JDK/GraalVM distribution and native toolchain.
- Use the same OS/architecture and container base image.
- Record full commands along with exit codes.
- Run at least twice from a clean state if the failure appears intermittent.

If the failure occurs only in CI, reproduce inside the exact same builder container or runner image. Never blame GraalVM when local and CI are running two different GraalVM releases or two different libcs.

## 4. Use a Matrix to Isolate the Failing Layer

### 4.1. Four Baseline Checks

Run the exact same business flow or test across these modes:

| Mode | Question to answer |
|---|---|
| Standard JVM | Do the code and dependencies work without AOT/native? |
| Spring AOT on JVM | Does Spring AOT-generated code initialize and run cleanly? |
| Native build | Can GraalVM analyze and compile the application? |
| Native runtime | Does the executable run the failing flow on the exact input? |

Not every project needs AOT-on-JVM as a long-lived pipeline stage. However, when native build/runtime fails, testing AOT-generated code on the JVM clarifies whether the bug happens before or during GraalVM compilation.

### 4.1.1. Run Spring AOT-Generated Code on the JVM

This check is fast because you do not wait for GraalVM native compilation:

With Maven using `spring-boot-starter-parent`:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/order-service.jar
```

With Gradle, ensure the build includes the Spring Boot AOT plugin. The `org.graalvm.buildtools.native` plugin applies the AOT plugin automatically; if you only want to run AOT on the JVM, you can apply `org.springframework.boot.aot` directly. After building the executable JAR:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/order-service.jar
```

Check startup logs for `Starting AOT-processed ...` to confirm generated code is active. The JAR must contain generated AOT assets; passing `spring.aot.enabled=true` to a plain non-AOT JAR is not enough.

AOT mode freezes the classpath and bean graph at build time. `@Profile` and `@ConditionalOnProperty` controlling bean creation must be configured when AOT processing runs. Therefore, a profile/runtime-condition issue can surface in AOT JVM even when standard JVM works.

### 4.2. Result Interpretation Matrix

| Standard JVM | AOT JVM | Native build | Native runtime | First investigation target |
|---|---|---|---|---|
| Fail | No need to run | No need to run | No need to run | Application logic, configuration, or dependencies; native is not the primary cause yet |
| Pass | Fail | Usually not needed yet | No need to run | Spring AOT contracts, bean discovery, conditions, generated initializers, or hint registrars |
| Pass | Pass | Fail | No need to run | Native Image analysis, unsupported APIs, class initialization, toolchain, or build configuration |
| Pass | Pass | Pass | Fail | Runtime metadata, resources, reflection, proxies, serialization, security providers, charset/locale, or runtime environment |
| Pass | Pass | Pass | Pass locally, fail in container | OS/libc, file permissions, DNS, truststore, timezone, filesystem, architecture, or container base image |

This matrix points in a direction; it does not automatically assign ownership. A third-party library may work on the JVM yet lack native metadata; that is a dependency compatibility or metadata issue, not necessarily a GraalVM compiler bug.

### 4.3. Vary One Version Axis at a Time

When suspecting a regression, hold other components fixed and test:

- Another Spring Boot patch/minor version with the same GraalVM.
- Another GraalVM/JDK version with the same Spring Boot and dependencies.
- Another Native Build Tools version with the same builder.
- Another OS/container base image with the same code and versions.

If you change Spring Boot and GraalVM simultaneously, you cannot tell which change made the error disappear. Record results in a compact table and archive logs for each combination.

## 5. Shrink the Project Step by Step

Spring Boot recommends creating a vanilla application from `start.spring.io` and gradually adding code and dependencies until the error reproduces. This reduces noise far more effectively than submitting a production app carrying years of accumulated changes.

### 5.1. Create a Minimal Base Project

Create a fresh project with:

- The exact Spring Boot version under investigation.
- The same Java version.
- The same build tool (Maven or Gradle).
- Only the minimal starters required to reproduce.
- A small test or `CommandLineRunner` triggering the failing behavior.

Example minimal structure:

```text
native-reproducer/
  pom.xml
  mvnw
  src/
    main/
      java/com/example/reproducer/
        ReproducerApplication.java
        ReproducerService.java
    test/
      java/com/example/reproducer/
        ReproducerApplicationTests.java
```

Do not copy the entire `application.yml`, `@Configuration` classes, or dependency tree of a large application upfront. Add only what is necessary to trigger the symptom.

### 5.2. Add Back Components One by One

Add sequentially:

1. A small class or method triggering the failure.
2. One directly involved dependency.
3. Beans/configuration required to initialize that dependency.
4. Related resources, reflection, proxies, or serializers.
5. Missing auto-configurations or starters.
6. The exact reproducing test/input.

After each addition, re-run the exact command. Once the error appears, keep the last change and try stripping sub-parts of that change individually.

### 5.3. Remove Unrelated Dependencies

Inspect the dependency tree and try removing:

- Starters unrelated to the failing flow.
- Logging appenders or monitoring agents unneeded for reproduction.
- Unrelated test libraries.
- Kotlin, Lombok, or code generation if not a triggering condition.
- Internal SDKs, snapshot dependencies, or non-public artifacts.

Do not delete dependencies in bulk at once. If the error disappears, you will not know which dependency or interaction caused it. Use before-and-after dependency trees to verify the project was genuinely minimized.

### 5.4. Remove Configuration and Beans by Group

If the failure occurs during Spring AOT or context startup, try removing groups:

- Unrelated `@Configuration` and `@Import` classes.
- `@ConditionalOnClass`, `@ConditionalOnProperty`, `@Profile`.
- Custom `BeanFactoryPostProcessor` and `BeanDefinitionRegistryPostProcessor`.
- `FactoryBean`, suppliers, or programmatically registered beans.
- `@ConfigurationProperties` and nested properties.
- AOP, transaction, security, or serialization configuration.

If removing a configuration makes the error vanish, re-add individual beans/imports in that configuration to find the trigger. Record active profiles and properties because conditions may be evaluated during the AOT build.

### 5.5. Minimize External Infrastructure

If a database, Redis, Kafka, or external HTTP server is required, build a small setup with Docker Compose or Testcontainers. Keep only services strictly needed for the failure. If the failure occurs before connecting to an external service, omit that service from the MRE entirely.

Never require maintainers to access your VPN, private registry, or cloud account. Replace internal endpoints with an equivalent local service, or supply a tiny stub if it still triggers the error.

### 5.6. Verify the MRE from a Clean Checkout

An MRE is trustworthy only when someone else can re-run it:

```bash
git clone <reproducer-repository>
cd native-reproducer
./mvnw test
./mvnw -Pnative package
./target/reproducer
```

With Gradle:

```bash
git clone <reproducer-repository>
cd native-reproducer
./gradlew test
./gradlew nativeCompile
./build/native/nativeCompile/reproducer
```

Substitute the project's actual output directory for the executable path. The README must state clearly which commands pass, which fail, and what the expected outcome is.

## 6. Identify Which Layer Owns the Bug

### 6.1. Application Bug

Common signs:

- JVM tests reproduce the exact same wrong behavior.
- Application input or configuration is invalid.
- Fixing business logic removes the failure without changing Spring/GraalVM.
- The MRE does not need AOT/native to reproduce.

Action: write logic tests, verify input contracts, inspect concurrency/resource lifecycles, and fix application code. If JVM passes while native fails, still inspect application code using dynamic features or class initialization before reassigning ownership.

### 6.2. Spring Boot or Spring Framework Bug

Signs:

- Standard JVM works, but Spring AOT processing or generated initializers fail.
- A fresh MRE using only Spring and minimal configuration reproduces it.
- Failure involves bean discovery, conditions, configuration properties, proxy/AOP, generated code, or auto-configuration.
- Changing Spring Boot/Spring Framework versions makes the error appear or disappear while GraalVM stays fixed.

Action:

1. Check AOT docs and known limitations for your exact Spring Boot version.
2. Inspect AOT-generated sources/classes and runtime hints.
3. Compare an adjacent patch version if suspecting a regression.
4. Check [Spring AOT smoke tests](https://github.com/spring-projects/spring-aot-smoke-tests) to see if a similar application pattern is tested.
5. Create an MRE and report to Spring if the bug still reproduces on a supported version.

Spring Boot does not bundle hints for every third-party library; the framework relies on the Reachability Metadata Repository and library-provided metadata. Therefore, a missing reflection metadata error in a dependency is not automatically a Spring bug.

### 6.3. Third-Party Library Bug

Signs:

- Failure centers inside a specific library or SDK.
- Code invokes the library in a dynamic way not covered by metadata.
- The dependency works on the JVM yet fails in native on reflection, JNI, proxies, serialization, or resource loading.
- A tiny plain-Java MRE without Spring reproduces it using that same library.

Action:

1. Check whether the library is listed in the [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata).
2. Check whether metadata matches the exact library version in use.
3. Run with `--exact-reachability-metadata` and `-XX:MissingRegistrationReportingMode=Warn` to pinpoint missing registrations.
4. Add minimal metadata inside the application to confirm the hypothesis.
5. If metadata belongs to the library, notify its maintainers or contribute metadata to the corresponding repository.

Never add broad reflection/resource wildcards just to silence an error and declare the library compatible. Identify the exact members/resources needed and test the production flow.

### 6.4. GraalVM Native Image Bug

Stronger signs include:

- A small plain-Java program without Spring reproduces the failure on the same GraalVM/JDK.
- The build compiler crashes, hits an internal error, or miscompiles supported inputs and APIs.
- The error persists after verifying metadata, class initialization, and the toolchain.
- Changing only the GraalVM patch version makes the bug appear/disappear while everything else stays fixed.

Action:

1. Run diagnostics mode and collect build output.
2. Create an MRE without Spring if possible.
3. Verify version/OS/architecture and supported toolchains.
4. Search existing GraalVM issues.
5. If none exists, file an issue with exact commands, logs, and the MRE.

GraalVM asks users to file Native Image runtime issues only after ruling out common causes such as missing metadata, `java.home`/classpath, URL protocols, and security providers. Use `--diagnostics-mode` to capture diagnostic data on class initialization, substitutions, and build details.

### 6.5. Build or Runtime Environment Bug

Signs:

- Fails only on one OS, architecture, libc, or container base image.
- Local passes while CI fails due to compiler/linker, permissions, memory, filesystem, or network.
- A native executable built on one machine fails to run on another due to CPU instruction set or ABI differences.
- Failure happens before application code is invoked.

Action: reproduce in the exact same container image, compare `native-image --version`, `gcc`/`clang`, linker, libc, architecture, environment variables, and resource limits. Do not attribute this to Spring or GraalVM before ruling out environment differences.

## 7. Diagnose Missing Reachability Metadata

### 7.1. When to Suspect Missing Metadata

Typically involved errors:

- `MissingReflectionRegistrationError` or reflection failing to locate a member.
- `MissingResourceException` or resource bundle missing from the image.
- `MissingJNIRegistrationError`.
- Dynamic proxy or serialization failing at runtime.
- Failure appearing only when exercising a feature not covered by JVM tests.

First verify whether the dependency already has metadata provided by the library or the Reachability Metadata Repository. Then enable exact reachability metadata to detect unregistered dynamic accesses.

### 7.2. Enable Exact Reachability Metadata

For GraalVM for JDK 23 and later:

```bash
native-image --exact-reachability-metadata -jar target/order-service.jar order-service
```

You can scope checking by package:

```bash
native-image --exact-reachability-metadata=com.example.orders -jar target/order-service.jar order-service
```

After building, run the executable in warning mode:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

`Warn` lists potentially missing registrations exercised during the scenario. Not every warning requires adding metadata; focus on failures causing incorrect behavior and code paths your application uses.

To catch metadata errors swallowed by `catch (Throwable)`, run integration tests with:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

On GraalVM releases prior to JDK 23, option names and timing differ: older docs use `-H:ThrowMissingRegistrationErrors=` and `-H:MissingRegistrationReportingMode=Warn` at build time. Do not copy JDK 23+ flags onto older GraalVM versions without checking `native-image --help` and version-specific docs.

### 7.3. Do Not Patch Metadata Before Confirming the Source

When a registration is missing:

1. Determine whether the stack trace originates in application code or a library.
2. Identify the exact class/member/resource/proxy accessed dynamically.
3. Check whether metadata already exists from the dependency or Spring AOT.
4. Add the minimal hint in the MRE.
5. Re-run the native test for that feature.

If the minimal hint eliminates the failure, you have evidence supporting the metadata hypothesis. Then decide whether the hint belongs in the application, Spring integration, or the library. Never commit raw Tracing Agent output without reviewing it first.

## 8. Diagnose Class Initialization Errors

### 8.1. Distinguish Build-Time and Runtime Initialization

Native Image may initialize certain classes during the build to persist state in the image heap. If a static initializer reads files, environment variables, timezones, DNS, random seeds, or secrets from the build machine, that data can be captured and cause unexpected runtime behavior.

Signs:

- Logs show a class unexpectedly initialized at build time.
- The native executable uses build-machine environment values.
- Static fields hold file handles, sockets, threads, or invalid runtime objects.
- Application fails after changing timezone, locale, hostname, or runtime config.

### 8.2. Trace Class Initialization

Use:

```bash
native-image \
  --trace-class-initialization=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

Or enable diagnostics mode for deeper information on class initialization and substitutions:

```bash
native-image --diagnostics-mode -jar target/order-service.jar order-service
```

When finding which class instantiates a suspicious type during the build:

```bash
native-image \
  --trace-object-instantiation=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

These options can vary by GraalVM version. Supply exact fully qualified class names and trace only relevant classes; tracing the entire application produces massive output.

### 8.3. Test Targeted Runtime Initialization

Once you prove static state must be created from the runtime environment, you can test:

```bash
native-image \
  --initialize-at-run-time=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

This serves as a diagnostic experiment and can become the final configuration if appropriate. Do not move an entire package to runtime initialization to mask an error; that can slow down startup without fixing the underlying captured static state.

## 9. Collect Build Diagnostics and Reports

### 9.1. Enable Verbose and Diagnostics Modes

```bash
native-image \
  --verbose \
  --diagnostics-mode \
  -jar target/order-service.jar \
  order-service
```

- `--verbose` prints command/tool invocations and detailed build information.
- `--diagnostics-mode` generates diagnostic output covering class initialization, substitutions, and build-related details.

Archive the diagnostics directory alongside build logs when preparing an MRE. Do not send only the tail of the log, as root causes often appear before the final summary error line.

### 9.2. Build Report

On GraalVM distributions supporting Build Report:

```bash
native-image --emit build-report -jar target/order-service.jar order-service
```

Build Report provides details on build stages and executable contents such as the code area, image heap, resources, and SBOM. Current documentation notes Build Report is not included in GraalVM Community Edition; if using CE, skip this step and rely on other logs/reports.

### 9.3. JSON Build Output for CI and Version Comparisons

Native Image can write machine-readable build output:

```bash
native-image \
  -H:BuildOutputJSONFile=target/native-build-output.json \
  -jar target/order-service.jar \
  order-service
```

The JSON file is useful for comparing reachable type/method counts, phase durations, or tracking regressions across builds. Parse it using the schema matching your GraalVM version; avoid scraping human-readable console logs as if they were a stable API.

### 9.4. Configure in Maven and Gradle

With Maven Native Build Tools:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--verbose</buildArg>
            <buildArg>--diagnostics-mode</buildArg>
            <buildArg>--exact-reachability-metadata</buildArg>
            <buildArg>-H:BuildOutputJSONFile=target/native-build-output.json</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

With Gradle Native Build Tools:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.addAll(
                    '--verbose',
                    '--diagnostics-mode',
                    '--exact-reachability-metadata',
                    '-H:BuildOutputJSONFile=build/native-build-output.json'
            )
            runtimeArgs.add('-XX:MissingRegistrationReportingMode=Warn')
        }
    }
}
```

This is a temporary diagnostic configuration. After finding the root cause, keep options valuable for CI and drop bulky report flags if no longer needed. On GraalVM releases before JDK 23, swap exact reachability/missing registration flags for that version's equivalents.

## 10. Check Limits and Compatibility Before Filing Upstream Issues

### 10.1. Verify the Version Is Still Supported

Before reporting a Spring Boot bug, verify that your Spring Boot version is still supported by the open-source project or under an applicable support policy. If running an end-of-life version, test on a supported version before concluding there is a regression.

### 10.2. Check Known Limitations

Spring Boot maintains [Spring Boot with GraalVM](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM), documenting known limitations. Check whether the library, feature, or JDK API you use appears there.

Spring Boot also states clearly that hints generated by Spring AOT do not replace metadata for all third-party libraries. If the error lies in a dependency, check the reachability metadata repository and that library's issue tracker first.

### 10.3. Use Spring AOT Smoke Tests as a Reference

The [spring-aot-smoke-tests](https://github.com/spring-projects/spring-aot-smoke-tests) repository holds smoke tests for Spring AOT and Native Image across Spring Boot branches. If a sample resembles your failing application, check whether that smoke test passes on the current version.

A passing smoke test does not prove your application is bug-free; it merely confirms a common framework setup is tested. A failing smoke test on the same version can be a signal to investigate Spring or GraalVM.

### 10.4. Try a Non-Spring MRE When Isolating GraalVM

If you suspect a GraalVM compiler/runtime bug, write a tiny Java program using the suspected API or dependency without starting a Spring ApplicationContext. If that MRE still fails with the same GraalVM version, the likelihood of a Native Image or dependency issue rises.

If the failure happens only when Spring AOT generates initializers/bean graphs, keep Spring in the MRE and test across Boot versions. Never strip Spring out of the example if removing Spring also removes the triggering condition.

## 11. Write an Actionable Issue Report

A good issue report tells maintainers how to reproduce without multiple rounds of back-and-forth questions.

### 11.1. Minimum Contents

| Item | Details to include |
|---|---|
| Summary | One sentence describing the error and phase where it occurs |
| Versions | Spring Boot, Spring Framework, JDK, GraalVM, Native Build Tools |
| Environment | OS, architecture, libc, compiler/linker, container base image |
| Reproducer | Link to a public MRE or minimal patch |
| Steps | Complete commands in exact execution order |
| Expected | Expected behavior |
| Actual | Exception, exit code, logs, and when it occurs |
| JVM comparison | Does the same test/flow pass on the JVM? |
| AOT comparison | Does Spring AOT processing/JVM pass? |
| Native details | Build args, runtime args, diagnostic output, and relevant metadata |
| Version matrix | Last passing version and first failing version if identified |

### 11.2. README for an MRE

Short README example:

```markdown
# Native Image reproducer

## Environment
- Spring Boot: 4.2.0
- Java: 25
- GraalVM: Oracle GraalVM for JDK 25, exact build version
- OS/architecture: Linux x86_64
- Build: Maven Wrapper

## Reproduce
1. Run `./mvnw test` — passes.
2. Run `./mvnw -Pnative package` — passes.
3. Run `./target/reproducer`.
4. Send `POST /reproduce` — fails with the exception below.

## Expected
The endpoint returns HTTP 200 with the generated value.

## Actual
The native executable throws `MissingReflectionRegistrationError`.

## Logs
See `logs/native-runtime.log` and `logs/native-build.log`.
```

Replace example versions with actual versions. Never leave placeholders or vague descriptions in an MRE submitted upstream.

### 11.3. Never Send Sensitive Data

Before publishing an MRE/logs:

- Strip tokens, passwords, private keys, and internal certificates.
- Replace internal hostnames, account IDs, and endpoints with dummy values.
- Scrub customer data and production payloads.
- Inspect build logs to verify no environment variables or command lines expose secrets.
- Do not attach internal artifacts without publication approval.

If the issue involves security, do not disclose exploit details publicly before following the project's vulnerability reporting process.

## 12. Decision Table: Who Should You Report To?

| Strongest evidence | First owner to investigate | Evidence to include |
|---|---|---|
| Standard JVM also fails on the same input | Application team | Unit test, input, stack trace, and expected logic |
| JVM passes, Spring AOT JVM fails in a Spring-only MRE | Spring Boot/Framework | MRE, generated AOT output, Boot/Framework version matrix |
| JVM/AOT pass, native runtime reports missing registration in a dependency | Dependency maintainer or Reachability Metadata Repository | Stack trace, exact metadata warning, dependency tree, minimal metadata |
| Plain Java MRE without Spring crashes or misbehaves in GraalVM | GraalVM Native Image | Java MRE, native-image command, diagnostics mode, GraalVM/JDK/OS details |
| Fails only on one runner/container/architecture | Platform/build infrastructure | Runner image, libc/toolchain, cgroup/resource limits, container reproduction |
| Error disappears when upgrading a single dependency | That dependency's maintainers | Last passing/first failing version, dependency tree, and MRE |

If evidence is inconclusive, shrink the MRE further and expand the version matrix. Do not assign ownership solely from the class name on the top line of a stack trace; identify which component introduced the wrong behavior or lacks metadata.

## 13. Hands-on Exercise: Investigate a Reflection Error in order-service

**Context:** `order-service` runs normally on the JVM. The native executable builds cleanly, yet the order export endpoint throws `MissingReflectionRegistrationError` when invoking a plugin by class name.

### Step 1 — Capture the Baseline

Record Spring Boot, Spring Framework, JDK, GraalVM, Native Build Tools, OS/architecture, build args, and the dependency tree. Run JVM tests and record results.

### Step 2 — Enable Exact Metadata Reporting

Build with `--exact-reachability-metadata`, run the executable with `-XX:MissingRegistrationReportingMode=Warn`, and invoke the export endpoint. Save the full stack trace and missing class/member names.

### Step 3 — Build the MRE

Create a new Spring Boot project from Initializr. Add one plugin class, one reflection invoker, and an endpoint or test calling the invoker. Omit databases, messaging, or security if unrelated.

### Step 4 — Identify Ownership

- If plain Java using the same reflection also fails in native, check metadata and GraalVM.
- If plain Java passes while Spring AOT/native fails, inspect generated hints and how Spring registers the plugin.
- If the error lies inside a plugin SDK, check SDK-provided metadata.

### Step 5 — Validate the Hypothesis

Add a minimal hint for the exact invoked constructor/method. Re-run the native endpoint and test with `MissingRegistrationReportingMode=Exit`. If the error vanishes, metadata is confirmed as the direct cause.

### Step 6 — Finalize the Issue Report

Include the MRE, README, dependency tree, version matrix, and relevant logs in the issue. State clearly that JVM passes, whether AOT passes/fails, and the native result so maintainers can pinpoint the failing stage.

### Result Sheet

| Item | Result to record |
|---|---|
| Spring Boot / Framework | _(record)_ |
| JDK / GraalVM | _(record)_ |
| Native Build Tools | _(record)_ |
| JVM test | PASS/FAIL |
| Spring AOT | PASS/FAIL |
| Native build | PASS/FAIL |
| Native runtime | PASS/FAIL |
| Exact metadata warning | _(record)_ |
| MRE reproduces from clean checkout | PASS/FAIL |
| Suspected component | Application / Spring / Library / GraalVM / Environment |
| Last passing / first failing version | _(record)_ |
| Complete issue report | PASS/FAIL |

## 14. Takeaways

Describe the symptom first, snapshot the environment and dependency tree, and run the JVM, Spring AOT, and Native Image matrix. Shrink the project by creating a fresh application and re-adding dependencies, configurations, beans, and code paths one by one until the error reproduces. An MRE must run from a clean checkout and state clearly which commands pass or fail.

JVM errors point toward the application or dependencies; Spring AOT errors point toward Spring configuration/generated code; native runtime errors may stem from missing metadata or environment differences; conclude GraalVM only when a small Java program also reproduces the issue in Native Image. Use exact reachability metadata, diagnostics mode, class-initialization tracing, and build reports to gather evidence. Submit issues with an MRE, a version matrix, and sanitized logs.

### Official References

- [Spring Boot — How To Get Help](https://github.com/spring-projects/spring-boot/wiki/How-To-Get-Help)
- [Spring Boot — Advanced Native Images Topics and Known Limitations](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
- [Spring Boot — With GraalVM: Known Limitations](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM)
- [Spring AOT Smoke Tests](https://github.com/spring-projects/spring-aot-smoke-tests)
- [GraalVM — Troubleshoot Native Image Run-Time Errors](https://www.graalvm.org/latest/reference-manual/native-image/guides/troubleshoot-run-time-errors/)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Native Image Build Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)
- [GraalVM — Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/)
- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)
- [GraalVM — Contributing and Reporting Bugs](https://github.com/oracle/graal/blob/master/CONTRIBUTING.md)
