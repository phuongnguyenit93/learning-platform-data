# Learning Sequence and Verification Criteria for a Complete Spring Boot Build

## 1. Destination: What Makes a "Complete Build"?

In Spring Boot, a **build** is the process of turning source code, resources, build configuration, and dependencies into a distributable product. A command reporting `BUILD SUCCESS` only proves the tasks actually invoked by that command completed; it **does not by itself prove** that the resulting package can start up, connect to the target environment, or contain the right resources.

For a **standalone Spring Boot application** deployed via an executable JAR, "complete" requires at least four layers of evidence:

1. **Controlled inputs:** exact source code/commit, JDK, build tool, plugins, and pinned dependencies.
2. **Passing build and tests:** compilation, resource processing, configured automated checks, and packaging succeed without errors; tests are not silently skipped.
3. **Right artifact type:** an executable JAR is produced with application classes and required dependencies; it can launch via `java -jar` under matching conditions.
4. **Verifiable runtime and handoff:** the app boots with expected configuration, passes a behavioral smoke test, has version metadata, and produces traceable CI outputs.

If a project targets a **WAR** for a servlet container or an **OCI image** for container platforms, substitute the JAR criteria with that artifact type's criteria and add checks on the actual target environment. You do not need to produce every artifact format for the same exercise.

Mental flow to master:

~~~text
Source + build definition + lock/toolchain
    -> resolve dependencies
    -> compile + process resources
    -> execute quality gates/tests
    -> package executable archive
    -> inspect archive
    -> run packaged artifact
    -> smoke test + publish evidence
~~~

**Core principle:** verify *the packaged artifact itself*, not just running from an IDE or `bootRun` / `spring-boot:run`. Dev-mode runners build a classpath directly via the build tool, which can mask packaging defects.

## 2. Recommended Learning Sequence: Learning by Dependencies and Observable Outputs

| Stage | What to Understand and Practice | Evidence Required Before Moving On |
| --- | --- | --- |
| 1. Toolchain & structure | Identify JDK, Maven/Gradle Wrapper, `pom.xml` or `build.gradle(.kts)`, `src/main` source, and `src/test` tests. | Record Java/build tool versions and run version checks using the Wrapper. |
| 2. Dependencies & plugins | Distinguish Spring Boot plugin, starters, BOM/dependency management, repositories, and dependency scopes/configurations. | Explain which libraries are needed for compile, test, and runtime; no unresolved dependencies. |
| 3. Compile & resources | Understand `compile`, resource processing, config files, main class, source sets/modules. | Code compiles cleanly and expected resources appear in the output. |
| 4. Testing & quality gates | Run unit tests, integration tests (if configured), config/code checks; read reports. | Tests are actually discovered and run; reports show exact counts, failures, and skips. |
| 5. Packaging | Distinguish library JARs, executable Spring Boot JARs, WARs, and OCI images; understand `repackage` / `bootJar`. | Artifact is in the right directory, in the right format, showing bundled dependencies/runtime launcher. |
| 6. Runtime verification | Run the packaged artifact with the right Java version, pass external config, watch logs, and test a use case. | Startup succeeds, endpoint/job works, clean shutdown; environment dependencies are ready. |
| 7. Release & CI | Build from a clean commit, archive test reports, checksums, artifacts, and build metadata; test on a clean runner. | Pipeline reproduces results; deliverable artifact is identifiable and tested as the exact deployable binary. |
| 8. Troubleshooting | Intentionally introduce dependency, test, packaging, or port/config errors and trace evidence. | Pinpoint which stage failed, how to fix it, and which command re-verifies it. |

Follow this sequence because each stage consumes the previous stage's output: runtime cannot be trusted until the artifact is right; an artifact should not be published until tests and dependencies are trustworthy. At the "Overview" level, the goal is to read and evaluate a build pipeline end to end without needing to optimize every advanced plugin option yet.

## 3. Stages 1–2: Lock Inputs and Understand Dependency Rules

### 3.1. Identifying the Project Setup

- **Maven:** `pom.xml`, Maven Wrapper (`mvnw` / `mvnw.cmd`); lifecycle phases include `compile`, `test`, `package`, and `verify`. Plugin goals bound to phases determine what actually executes.
- **Gradle:** `settings.gradle(.kts)`, `build.gradle(.kts)`, Gradle Wrapper (`gradlew` / `gradlew.bat`); common tasks include `compileJava`, `processResources`, `test`, `bootJar`, and `build`. Task dependencies govern execution order.
- **JDK:** the build JDK must match Spring Boot, plugin, and bytecode target requirements; the deployment runtime must also support that bytecode. Verify both `java` and `javac` rather than relying on the JDK selected in your IDE.
- **Wrapper:** commit and use the Wrapper in the repository so the team and CI use the exact pinned Maven or Gradle version. Wrappers **do not automatically pin the JDK**; pair them with toolchains or runner configuration.

~~~bash
# macOS/Linux: choose the commands matching your project
java -version
javac -version
./mvnw -version
# Or for a Gradle project:
./gradlew --version
~~~

On Windows, use `mvnw.cmd -version` or `gradlew.bat --version`. A project does not need to have both Maven and Gradle.

### 3.2. Inspecting the Dependency Map Before Building

Spring Boot starters group common libraries; dependency management/BOMs align compatible versions without automatically pulling every library into the app. Distinguish:

- Maven `compile`/`runtime`/`test`/`provided` vs. Gradle `implementation`/`runtimeOnly`/`testImplementation`/`compileOnly`: they affect classpaths and packaged contents differently; **do not treat scopes and configurations as exact 1:1 equivalents**.
- Test-only libraries must not end up in production artifacts. Libraries needed at execution time must appear on the runtime classpath unless explicitly provided by the target environment.
- Build plugins play a different role from application dependencies: declare the Spring Boot Maven/Gradle plugin for executable packaging; declare a web starter for an HTTP server; one does not substitute for the other.

Diagnostic commands for version conflicts or missing dependencies:

~~~bash
# Maven: view the resolved dependency tree
./mvnw dependency:tree

# Gradle: view runtime configuration of a Java project
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands require the matching plugins/configurations to exist. In Gradle multi-project builds, target the specific module's task when needed; in Maven multi-module builds, select the application module via the reactor. You pass this stage when you can explain **why** a library is or isn't inside the runtime archive and spot version conflicts.

## 4. Stages 3–4: Compilation, Resources, and Evidenced Testing

### 4.1. Compilation Success Is Not Enough

Compilation validates Java syntax/types and emits classes; resource processing copies and optionally filters configuration files, templates, and static assets. In multi-module applications, verify that the module containing `@SpringBootApplication` and `main` is the module being packaged rather than accidentally packaging a library module.

Minimum checklist:

- Zero compiler errors; correct source/target/toolchain settings.
- Required resources from `src/main/resources` are present (e.g., YAML files, templates, or static assets actually used).
- No credentials, secret keys, or developer-machine-only settings baked into the artifact.
- Do not judge build health by green indicators in the IDE; rerun with the Wrapper in a terminal.

### 4.2. Knowing Which Tests Actually Ran

| Test Type | What It Proves | Limitations |
| --- | --- | --- |
| Unit tests | Isolated logic returns expected results. | Does not prove the app boots or connects to infrastructure. |
| Integration tests | Components such as Spring context, DB, queues, and HTTP clients cooperate per contract. | Valid only for the configured environment, fixtures, and test paths. |
| Smoke test on artifact | The built package starts and performs core behavior. | Does not replace logic, security, load, or production testing. |

~~~bash
# Maven: run phases up through verify, including default tests and
# integration-test/verify if the project configured corresponding plugins
./mvnw clean verify

# Gradle with Java/Spring Boot plugins: run assemble + check per task graph
./gradlew clean build
~~~

**Observable evidence:** zero exit code, test/report summary lines, executed suite names, total tests run, failures, and skips. Maven Surefire typically writes reports to `target/surefire-reports/`; Failsafe writes its own reports if configured; Gradle Java tests write to `build/test-results/test/` and `build/reports/tests/test/`. Locations may vary if build scripts customize them.

Important distinction: Maven's `verify` **does not automatically ensure integration tests exist** unless Failsafe or an equivalent plugin is wired in; similarly, Gradle's `build` **does not automatically create an `integrationTest` task**. Flags that skip tests (`-DskipTests`, `-Dmaven.test.skip=true`, `-x test`) should only be used with approved justification; never treat such builds as passing the test gate.

## 5. Stage 5: Packaging the Exact Deliverable Artifact

### 5.1. Three Common Outcomes

| Output | Purpose | How to Identify / Test |
| --- | --- | --- |
| **Executable JAR** | Run a standalone Spring Boot app with `java -jar`. | JAR contains appropriate launcher/manifest, app classes, and runtime dependencies; starts cleanly. |
| **WAR** | Run with `java -jar` when packaged executable, or deploy to an external servlet container when configured. | Inspect `WEB-INF` structure and test the intended runtime mode. |
| **OCI image** | Distribute the app with a runtime/base image for container platforms. | Build an image tag/digest and run the container with appropriate config/ports. |

A Spring Boot executable JAR typically stores app classes in `BOOT-INF/classes`, dependencies in `BOOT-INF/lib`, and uses a manifest pointing to a suitable launcher. A standard Java JAR can compile and package cleanly yet **fail** to launch via `java -jar` with all Spring Boot application dependencies.

### 5.2. Maven and Gradle Packaging Commands

- **Maven:** with `spring-boot-maven-plugin` and a configured `repackage` execution, `package`/`verify` lifecycles can produce an executable archive. Projects using `spring-boot-starter-parent` normally preconfigure the `repackage` execution, though the plugin must still be declared; without the parent, configure the execution explicitly. `mvn package spring-boot:repackage` invokes it explicitly when needed.
- **Gradle:** projects applying the Spring Boot plugin alongside the Java plugin get the `bootJar` task; `bootWar` applies when the War plugin is present. The plain `jar` task is not equivalent to `bootJar`; inspect the project's actual task graph.
- **OCI:** depending on configuration, run `./gradlew bootBuildImage` or `./mvnw spring-boot:build-image`; Spring Boot Buildpacks require access to a compatible container daemon, typically Docker. Succeeding at building an image does not guarantee the service inside will be healthy at runtime.

~~~bash
# If the exercise uses Maven, output is typically under target/
./mvnw clean verify

# If the exercise uses Gradle, output is typically under build/libs/
./gradlew clean build

# Inspect actual JAR contents; adjust path to the generated file
jar tf target/demo-0.0.1-SNAPSHOT.jar
~~~

The `jar tf` line above is only for a **sample Maven artifact with that exact name**. For Gradle, use the JAR path under `build/libs/`. In an executable JAR listing, look for `BOOT-INF/classes/`, `BOOT-INF/lib/`, and `META-INF/MANIFEST.MF`; exact manifest entries and launcher classes can differ across Spring Boot generations. Archive layout is only a *static* check; the next stage must run the artifact for real.

## 6. Stage 6: End-to-End Practice from Source to Runtime

**Exercise:** use a Spring Boot Web project with the web starter appropriate for your Spring Boot version, a compatible JDK, the Spring Boot build plugin, and a small endpoint. Use `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

This is a **complete Java class**, but to run it must live inside a **Spring Boot project configured** with the required dependencies and plugin. `@SpringBootApplication` configures the app and auto-configuration; `@RestController` exposes HTTP handlers; `@GetMapping("/ping")` maps HTTP GET to the string `pong`. Do not guess dependency versions: rely on the version set managed by the project.

Follow this verification sequence:

1. **Prepare:** record commit/revision, JDK version, and Wrapper; verify the endpoint compiles and has at least one meaningful automated test (e.g., logic test or HTTP/status check matching the framework version).
2. **Build:** pick **one** command suite—`./mvnw clean verify` or `./gradlew clean build`—and verify expected tests ran. If it fails, stop and do not proceed to release.
3. **Verify artifact:** list the actual JAR file; run `jar tf` and confirm it is an executable Boot archive. In multi-module projects, pick the application module's archive.
4. **Run the artifact:** open a new terminal and run one of the commands below, matching the generated filename and running a single instance.
5. **Smoke test:** in another terminal, send an HTTP GET and confirm **status 200**, response body **exactly `pong`**, and stability during testing.
6. **Shutdown:** stop the process with Ctrl+C, confirm nothing remains listening on the test port, and archive logs/build/test outputs in your verification record.

~~~bash
# Example with Maven and an illustrative artifact name:
java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8085

# Or with Gradle and an illustrative artifact name:
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

~~~bash
# Call after application logs confirm startup completed
curl -i http://localhost:8085/ping
~~~

Expected result: HTTP `200 OK` and **response body `pong`**. Headers, startup logs, timestamps, PIDs, status line formatting, and default ports depend on the runtime, so do **not** treat sample log text as a pass condition. If `curl` is unavailable, use an equivalent HTTP client; evidence should capture request, status, and body. For Spring Batch/CLI apps without HTTP endpoints, replace the check above with a **minimal verifiable job/input**, checking exit code and contract output.

**Test an intentional config change:** switch the port to 8085 via runtime arguments as above without editing source code or rebuilding. The app listening on 8085 demonstrates *externalized configuration*. Profiles, database URLs, and secrets should be provided by the runtime environment through proper mechanisms rather than embedded in the JAR. If external dependencies exist (DB, broker), document the startup prerequisites; "works on my machine" is not reproducible deployment evidence.

## 7. Stage 7: Quality Gates and Final Acceptance Criteria

Evaluate using **observable evidence**, avoiding conclusions drawn from a single log line or JAR size.

| Gate | PASS Criteria | Evidence to Retain |
| --- | --- | --- |
| **G1 — Input** | Commit, Java, Wrapper, plugin/build config, and dependency sources identified; no hidden IDE settings. | Commit SHA, `--version` outputs, build definition/lockfile if used. |
| **G2 — Compile/resources** | Compilation and packaging of required resources succeed cleanly. | Task/phase results, files/resources present in the artifact. |
| **G3 — Tests** | Required tests ran and passed; any skips have approved justification. | Exit code, reports, executed/passed/failed/skipped counts, suite list. |
| **G4 — Package** | Correct deployment format with valid manifest/launcher/runtime dependencies. | Artifact path, `jar tf`/manifest, or image/WAR metadata. |
| **G5 — Runtime** | Running **the release artifact**, starts cleanly, external config applies, core behavior works. | `java -jar`/container command, startup logs, HTTP/job smoke result, exit/shutdown. |
| **G6 — Reproduce & handoff** | Independent pipeline builds and stores a versioned artifact; deployers know exactly which build to fetch. | CI job run, commit, artifact name/version, checksum/digest, test reports. |
| **G7 — Target-specific gate** | If WAR/container/native packaging is chosen, checks specific to that target pass. | Container health/probes, servlet deploy smoke test, or target-specific criteria. |

**Definition of done for this exercise:** gates G1–G6 all PASS; G7 applies only if the deployment target requires it. Every "PASS" must link to auditable evidence. If CI is not set up yet, mark G6 as **not met** rather than assuming local commands equal a clean pipeline. If this is a learning exercise, you may complete local milestones G1–G5 and note G6 as the next stage, without calling it release-ready.

A concise handoff record can follow this template:

~~~text
Commit: <commit-sha>
Build tool: <maven-or-gradle-wrapper> / version
JDK build + runtime: <version>
Build command: <command>
Tests: <executed-count> executed, 0 failures, <skipped-count> skipped (reason if any)
Artifact: <file-path-and-name>
SHA-256 / image digest: <value-measured-from-actual-artifact>
Run command / environment: <command-and-config-without-secrets>
Smoke test: <input> -> <status/result>
CI run / artifact location: <reference-if-available>
Result: PASS or FAIL with gate and evidence
~~~

The lines inside the block above are a **fill-in template**, not measured logs. For checksums, compute directly on the actual distributed artifact: Linux typically uses `sha256sum`, Windows PowerShell uses `Get-FileHash -Algorithm SHA256`; images need their digest recorded if distribution relies on a registry.

## 8. Reproducibility, Reliability, and the Boundary with "Production Ready"

A build can succeed once yet remain unreliable if it depends on hidden state. Focus on these points when moving from local machines to CI:

- **Use explicit toolchains:** pin the Wrapper and target JDK per project; avoid "machine A uses Java 17, machine B uses Java 23" without checking compatibility.
- **Stabilize versions:** use dependency management/locking or approved version policies; avoid uncontrolled dynamic selectors or snapshots in releases. If remote repositories change, retain source metadata and checksums as required.
- **Do not depend on local caches:** test building on a clean runner/workspace; caches speed up builds but must not alter correctness.
- **Preserve the artifact:** build once in CI, test that exact artifact, and distribute the same binary—avoid rebuilding separately at deploy time and creating a different binary. Attach commit, version, and checksum/digest for traceability.
- **Secure the output:** scan dependencies and images when policy requires; never bundle secrets or dev-only files; keep base images patched when using OCI. SBOMs, artifact signatures, provenance, and license scans are optional gates depending on assurance levels.
- **Environment-agnostic artifacts:** keep the artifact immutable across dev/test/prod; supply environment settings externally and verify via smoke tests in the target environment.

**Distinguish three levels:** `compiles` = compiles cleanly; `build verified` = tests + packaging + running the artifact against stated criteria; `production ready` also requires operations, security, observability, recovery, performance, rollout/rollback, infrastructure, and system approvals. Do not conflate these three levels.

## 9. Common Errors: Pinpoint the Right Stage Instead of Retrying Blindly

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Runs in IDE, `java -jar` fails with `no main manifest attribute`. | Built a plain JAR, missing/skipped Boot repackage, or picked the wrong file. | Check plugins/tasks, manifest, and archive layout; select executable JAR and rebuild. |
| `ClassNotFoundException` or `NoClassDefFoundError` at startup. | Dependency only on compile/test classpath, excluded, or wrong runtime classpath. | Inspect dependency tree/`runtimeClasspath`, `BOOT-INF/lib`, and scopes. |
| `UnsupportedClassVersionError`. | Runtime JDK is older than the compiled bytecode. | Check runtime `java -version` and toolchain/target settings. |
| Green build yet test count is 0 or critical tests were skipped. | Tests not discovered, bad filter, skip flags, missing integration test task/goal. | Inspect reports/task graph, JUnit/Surefire/Failsafe or Gradle test task config. |
| JAR has classes but misses `application.yml`/templates. | Resource processing/source set or wrong file location. | Check source resources, build config, and `jar tf`. |
| Startup fails on port or DB/secrets. | Port already in use, wrong profile, external dependency unready. | Read the **root cause** in the stack trace; check port, profile, env vars, and dependent services. |
| Passes locally, fails in CI. | Differences in JDK, env, paths, permissions, timezone, locale, cache, or order-dependent tests. | Compare recorded toolchain/environment; rerun with Wrapper in a clean environment. |
| Image built cleanly but container is unhealthy. | Wrong port/exposed port, startup command, config, or readiness dependency. | Run the exact image, inspect logs, health endpoints/probes, and port mappings. |

Fix the **root cause** at the corresponding stage, then rerun from the affected gate through the end of the chain: fixing a dependency requires rebuild + test + package + runtime smoke test; changing runtime config still requires testing the artifact in the target environment.

## 10. Self-Assessment After Studying

You have met the lesson goals when you can answer and prove:

1. Which Wrapper does the project use, which JDK, and where are plugin/dependency versions managed?
2. Why do `./mvnw clean verify` and `./gradlew clean build` not guarantee integration tests exist if unconfigured?
3. What is the difference between a standard Java `jar` and `bootJar` / Spring Boot Maven `repackage`?
4. Where is the release artifact located; have you inspected its contents and **run that exact artifact** rather than only running from an IDE?
5. Which tests prove logic, which prove integration, and which check proves packaged runtime behavior?
6. If startup fails, can you distinguish missing dependencies, wrong JDK, port conflicts, external config, and external services?
7. Can someone else trace the exact commit, build tool, test results, and artifact checksum/digest to verify it independently?
8. When targeting WAR or OCI, do you adapt acceptance criteria to match the actual runtime environment?

**Capstone exercise:** submit a G1–G7 form backed by real evidence, clearly indicating PASS/FAIL per gate, with at least a build log, test report, artifact path, archive inspection output, run command, and smoke test. For any FAIL, explain which stage failed and what must change to turn it into PASS.

## Official References

- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)

Sample commands assume the application module already configures the Spring Boot plugin, starters, and compatible Java version. Always consult the real project's build definition to choose the exact commands and artifact paths.