# Boundaries with Application Configuration, In-Depth Testing, and Native Image

## 1. Where Does This Lesson Fit?

Within **Spring Boot Build Tooling Packaging**, build tooling covers using Gradle/Maven and plugins to compile, process resources, manage dependencies, and produce distributable deliverables (artifacts). Packaging is the stage of assembling what is needed into an executable JAR/WAR or as input to a container image. For a JVM-based Spring Boot application, the central question is: **"Which components do we include, in what structure do we package them, and how do we produce a runnable deliverable?"**

Three areas frequently sit alongside build/packaging yet carry distinct responsibilities:

1. **Application configuration** governs how the application behaves at startup and across environments.
2. **In-depth testing** verifies business logic, API contracts, system interactions, and quality attributes.
3. **Native Image** is a specialized compilation/deployment target requiring AOT processing and distinct compatibility constraints.

The goal here is to recognize the boundaries, intersections, and how to pick the right tool for each situation. Details on configuration binding, advanced testing techniques, or tuning GraalVM are covered in their dedicated deep-dive topics.

## 2. Responsibility Map

| Aspect | Build Tooling & Packaging | Application Configuration | In-Depth Testing | Native Image |
| --- | --- | --- | --- | --- |
| Question to answer | Which artifact is produced, what classes/resources/dependencies are inside, and can it launch? | Which port, profile, endpoints, logging, and connections does the app use? | Are functionality, integration, performance, and error handling correct? | How is the app ahead-of-time compiled into JVM-independent machine code? |
| Common inputs | `build.gradle`, `pom.xml`, source code, resources, dependencies, plugin config | `application.yml`, `application.properties`, environment variables, CLI args, external secrets | Test source, test fixtures, mocks, databases/testcontainers, acceptance criteria | GraalVM Native Build Tools config, Spring AOT, reachability hints, toolchain |
| Outputs | Executable JAR/WAR, metadata/layers; usable to create OCI images | Effective configuration values and active runtime beans/behaviors | Test results, failure reports, quality evidence | Native executable or container image containing a native executable |
| Primary execution locus | Gradle/Maven tasks and Spring Boot plugins | Spring `Environment`, application configuration system | Test frameworks, test suites, and CI pipelines | AOT build chain + native compiler/buildpacks |
| Minimum success bar | Artifact has the right format and can start in an appropriate environment | Configuration loads properly and behaves as intended | Test assertions and criteria are satisfied | Native artifact compiles and runs properly on the target platform |

These columns can work together in the same pipeline, yet **do not replace each other**. A successfully packaged JAR does not prove all APIs or production configs are correct; a green test suite does not prove the distributable artifact is packaged properly; an OCI image is not automatically a Native Image.

## 3. Boundary with Application Configuration

### 3.1. Build-Time vs. Runtime

**Build-time** handles artifact structure: compiler/toolchain, dependency versions, main startup class, filename, resources, and packaging layout. **Runtime** handles execution behavior: HTTP ports, database connections, profiles, log levels, feature flags, and credentials.

For example, a project that **already applies** `org.springframework.boot` and `java` plugins can name its executable JAR in Gradle Groovy DSL:

```groovy
// build.gradle (packaging configuration snippet)
tasks.named('bootJar') {
    archiveFileName = 'demo-app.jar'
}
```

Meanwhile, default application configuration lives at:

```yaml
# src/main/resources/application.yml
server:
  port: 8080
logging:
  level:
    root: INFO
```

Once valid Spring Boot code and required dependencies are in place, you can run:

```bash
./gradlew bootJar
java -jar build/libs/demo-app.jar --server.port=9090
```

The first command creates the executable JAR. The second **starts** the artifact while passing HTTP port 9090 via a command-line property; for a standard web app following normal configuration rules, this can override the default 8080 in the YAML file. The Gradle snippet only illustrates naming the artifact, **not** a complete standalone project config. On Windows, use `gradlew.bat` instead of `./gradlew` if needed.

Distinguish **"packaging a config file"** from **"determining effective values"**. By convention, resources under `src/main/resources` are processed and placed on the classpath, typically in `BOOT-INF/classes` inside an executable JAR. Spring Boot can still read external config sources outside the JAR such as environment variables, external config files, and command-line arguments. Precedence depends on config sources and Spring Boot rules; do not assume values inside the JAR always win or always lose to every other source.

### 3.2. Which Changes Require Rebuilding?

- **Changing artifact name, runtime dependencies, startup class, JAR layout, or packaged resources:** belongs to build/packaging; generally requires rebuilding the artifact.
- **Changing port, service URLs, log levels, or environment settings:** prefer externalized runtime config; for standard JVM applications, the same artifact can serve multiple environments.
- **Changing Java code, bean structure, or embedded resources:** requires building a new artifact.
- **Config changes affecting bean selection in AOT/native apps:** check AOT constraints because some conditions are evaluated at build-time; do not mechanically apply the rule that any config change works without rebuilding.

Never place real passwords or tokens directly into `build.gradle`, packaged `application.yml`, or task parameters logged during builds just for convenience. Sensitive settings should be supplied through proper secret mechanisms at runtime.

### 3.3. Build Profiles and Spring Profiles Are Separate Concepts

Maven/Gradle options, tasks, and profiles adjust **how the artifact is built**; Spring profiles adjust **application configuration and bean selection**. They may be coordinated explicitly in a pipeline, yet they do not automatically share names, are not synonymous, and do not automatically activate one another. For instance, passing a packaging property to a Gradle task does not automatically activate a Spring profile with the same name.

## 4. Boundary with In-Depth Testing

### 4.1. Build Tasks Relate to Tests, but Packaging Does Not Define Test Strategy

In a standard Gradle Java/Spring Boot project:

```bash
./gradlew test       # run tests configured in the test task
./gradlew bootJar    # build executable JAR; does not run test task by default
./gradlew check      # run checks attached to check
./gradlew build      # typically combines assemble and check
```

The `bootJar` task packages the application; the `test` task runs tests declared by the project. With the Java plugin, `build` depends on `assemble` and `check`, and `check` typically triggers `test`. However, tasks can be customized, tests can be disabled or skipped, and integration tests may live in a separate task. Therefore, **never conclude "running bootJar means tests ran"** nor "a green build proves full production integration is verified".

With Maven, the `package` lifecycle normally runs unit test phases before packaging unless skipped; integration testing and verification in the `verify` phase happen only as configured by the project's plugins/lifecycle. The `spring-boot:repackage` command focuses on archive repackaging and does not constitute a business test suite.

### 4.2. Matching Test Depth to Risk

| Scenario | Appropriate Evidence | Why Packaging Alone Is Insufficient |
| --- | --- | --- |
| Calculation logic fails on boundary inputs | Unit tests with clear assertions | Presence of classes in a JAR does not prove logic correctness |
| Endpoint returns wrong HTTP status/body | Web/API tests, contract tests | Packaging a controller does not verify API contracts |
| App cannot connect to real database | Integration tests against compatible dependencies | Building does not verify runtime infrastructure, credentials, or schemas |
| Works under low load but stalls under high load | Load/performance tests against target SLAs | A valid artifact does not measure throughput or latency |
| JAR builds cleanly but misses config files or libraries | Archive inspection and startup smoke tests | Unit tests can still pass while the release package is broken |

A basic pre-release pipeline might run `./gradlew test` followed by `./gradlew bootJar`, inspect the generated artifact, and run a smoke test with production-like config. If using `./gradlew build`, confirm that test tasks are actually wired into the project's task graph. Testcontainers, mock servers, test slices, security testing, and performance benchmarking are dedicated testing disciplines: build tools can *invoke* them, but do not design test data, edge cases, or assertions for you.

### 4.3. Reading Failure Signals Correctly

- **Compilation / dependency resolution / packaging task failure:** check build scripts, toolchain, dependency graph, main class, and archive creation first.
- **Test case failure:** read assertions, test fixtures, logs, and root causes at the behavior/integration layer.
- **JAR builds cleanly yet app fails to start:** inspect runtime logs, config, classpath, dependent services, and runtime environment together; do not automatically blame Gradle.
- **Fails only in CI/production:** compare Java runtime, paths, environment variables, permissions, secrets, and launch commands before altering packaging.

## 5. Boundary with Native Image

### 5.1. Three Frequently Confused Output Targets

| Target | Characteristics | How to Run / Deploy |
| --- | --- | --- |
| **Spring Boot executable JAR on JVM** | Contains bytecode, resources, libraries, and Boot launcher; typically has `BOOT-INF/classes` and `BOOT-INF/lib` | `java -jar app.jar` on a compatible JVM |
| **JVM-based OCI container image** | Packages application and runtime environment in an image, e.g., via Cloud Native Buildpacks | Run image with a container runtime; a JVM still runs inside |
| **GraalVM Native Image** | Ahead-of-time compiled machine code for target OS/architecture, combining Spring AOT and reachability metadata | Run native executable directly or inside a container |

Gradle's `bootBuildImage` uses Cloud Native Buildpacks to build an **OCI image**. Under normal JVM configuration, it builds a JVM-based image; when integrated with the GraalVM Native Image plugin and matching config, the workflow can build a native image. Thus, the word "image" in `bootBuildImage` **is not synonymous** with GraalVM "Native Image". This task also requires an appropriate container/buildpack environment (per plugin docs, typically a Docker daemon).

### 5.2. Why Native Needs a Dedicated Knowledge Track

The JVM relies on dynamic class loading and reflection; native compilation needs to know many structures ahead of time to determine reachable code and resources. **Spring AOT** analyzes the application at build-time, generating supporting code and metadata including hints for reflection, resources, proxies, or serialization where required. **GraalVM Native Build Tools** and the native toolchain perform the actual native compilation.

When a project applies a compatible GraalVM Native Image plugin and configures Spring Boot AOT, tasks such as `nativeCompile` can build a native executable, and `nativeTest` supports native testing when configured. Those tasks **do not appear merely because** the app already has `bootJar` or because a runtime property was added.

AOT can fix certain bean graph and conditional decisions at build-time. For configuration affecting `@Profile`, `@ConditionalOnProperty`, or bean creation, distinguish values evaluated during AOT from values operators expect to toggle later. Pure runtime properties can still change, but changes altering the bean graph must be designed, tested, and sometimes require rebuilding the native image.

### 5.3. Evaluating Native with Concrete Criteria

Native Image is often considered to optimize cold start, memory footprint, or deployment profile, yet comes with compile/toolchain overhead, reflection/dynamic-loading constraints, reachability hints, native library differences, and OS/architecture lock-in. Do not claim native is always faster for every workload, always uses less RAM in every case, or replaces JVM testing. Evaluate against measurable targets: startup time, memory consumption, throughput, diagnostics/observability, artifact size, and functional stability.

**Where this lesson stops:** recognizing why Native Image demands its own pipeline and testing. Detailed GraalVM setup, hints, AOT testing, native buildpacks, and runtime tuning belong to specialized lessons.

## 6. Typical Flow and Responsibility Boundaries

```text
Source code + dependencies + resources
                |
                v
      Gradle/Maven + Boot plugin
          |               |
          v               v
     run tests      build executable JAR/WAR
     (if wired         |           |
     in pipeline)      |           +--> build JVM-based OCI image
                       |
                       +--> run on JVM with runtime configuration
                       |
                       +--> AOT branch + GraalVM Native Build Tools
                                      |
                                      v
                              native executable/image
```

The diagram shows **possible branches**, not that calling one task executes everything. Artifacts must be verified according to how they actually run; environment configuration, system prerequisites, and proper test suites are complementary responsibilities.

Consider three common requests:

1. **"Run the exact same release on port 8080 in dev and 9090 in staging."** Use Spring Boot's runtime configuration mechanisms (such as environment variables or CLI arguments). You do not need two separate JARs just for different ports, provided it is a JVM app and your deployment workflow permits overrides.
2. **"The release is missing a library when running `java -jar`."** Check dependency scopes/classpath, `bootJar` output, archive contents, and launch command. Changing `server.port` will not fix a missing library.
3. **"Reduce cold start time using native."** Define performance targets, verify Spring AOT/GraalVM support across dependencies and build infrastructure, and design a dedicated native pipeline and test suite. Merely renaming `.jar` or putting a JAR into a container does not produce a native executable.

## 7. Self-Check After This Lesson

When facing a change or incident, answer in order:

1. **What needs to change?** Artifact contents/format, runtime values, behavioral reliability, or native compilation mechanics?
2. **When does the change take effect?** Compile/package, image build, startup, or during an active request?
3. **Who owns the configuration?** Gradle/Maven plugin, Spring `Environment`, test framework, or AOT/native toolchain?
4. **What evidence is needed?** Archive inspection, `java -jar` execution, test assertions, integration/smoke tests, or native benchmarks?
5. **Can the artifact be reused?** Usually yes for externalized JVM configs; code/dependency changes or AOT bean conditions may require rebuilding.
6. **Is the action within proper scope?** Do not fix test failures by disabling tests, do not bake secrets into artifacts, and do not switch to native just to work around a runtime configuration bug.

### Misconceptions to Avoid

- **"Build succeeded means the app is production-ready."** A build only confirms the invoked tasks succeeded; you need to know which tasks ran and what was tested.
- **"`bootJar` and `jar` are the same."** Spring Boot's `bootJar` creates an executable archive with Boot's launcher and dependencies; the standard `jar` task creates a plain archive per the Java plugin. In common plugin configs, the plain file carries the `plain` classifier to avoid name collisions.
- **"Setting variables in `application.yml` configures the build tool."** It is typically runtime application config packaged as a resource; the build script controls packaging.
- **"Having a Docker/OCI image means you have a Native Image."** A container is a distribution format; native vs. JVM is how the code executes inside.
- **"Native is just flipping a flag."** Native requires matching AOT/toolchain setup, library compatibility, hints when needed, and dedicated testing.
- **"Running `bootJar` runs all tests."** `bootJar` focuses on building the archive; test execution depends on the actual task graph.

## 8. Official Resources for Deeper Study

- Spring Boot Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot Gradle Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html
- Spring Boot Gradle Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- Spring Boot — Introducing GraalVM Native Images: https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html
- Gradle — The Base Plugin (lifecycle tasks): https://docs.gradle.org/current/userguide/base_plugin.html

Exact APIs, tasks, and behaviors should always be checked against the **Spring Boot/Gradle/Maven/GraalVM versions actually used in your project** before applying detailed instructions.