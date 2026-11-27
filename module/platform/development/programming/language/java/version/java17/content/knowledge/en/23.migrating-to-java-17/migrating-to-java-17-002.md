# Testing the Application Before Changing Multiple Components Together When Upgrading to Java 17

## 1. Why test before changing many things at once?

Upgrading an application to Java 17 typically touches multiple layers: the runtime JDK, build tool, compiler, third-party libraries, frameworks, plugins, JVM configuration, container image, and sometimes source code. If you change everything at once and only test afterward, pinpointing the root cause when the application fails becomes very difficult.

For example, after a simultaneous upgrade:

- The JDK was switched from 11 to 17.
- The framework was upgraded.
- A logging library was replaced.
- The compiler switched to `--release 17`.
- Legacy JVM flags were modified.

If the application fails to start, the cause could be an incompatible framework, a strongly encapsulated internal API, a build plugin that cannot run, or a removed JVM flag. Without intermediate test runs, these causes get tangled together.

A more controllable transition is to **test the existing artifact on JDK 17 first**, keeping other components unchanged as far as possible. That result tells you whether the application and its current dependencies are runtime-compatible. Only then should you upgrade the build, dependencies, configurations, and source code in focused batches.

The goal is not to forbid all concurrent changes through a rigid rule. The goal is to establish comparable checkpoints so that each change has one hypothesis, one verification result, and one rollback path.

After this lesson, learners should be able to:

1. Establish a baseline for the application on its current JDK.
2. Run the same artifact on JDK 17 to verify runtime compatibility.
3. Distinguish errors caused by the runtime, dependencies, build tools, compiler, and configuration.
4. Upgrade component groups in a verifiable sequence.
5. Use JDK tools to detect dependencies on internal or deprecated APIs.
6. Verify startup, health checks, business flows, and operational behavior.
7. Record results and decide whether to proceed or roll back based on evidence.

## 2. Define the exact upgrade scope

Before making changes, write down what is actually being upgraded. The phrase "upgrading to Java 17" can refer to several distinct activities:

| Component | Question to answer |
|---|---|
| Runtime JDK | Which Java 17 JDK and vendor will run the application? |
| Build JDK | Will the build/CI machines use JDK 17? |
| Compiler target | Is code compiled exclusively for Java 17 or must it still support older runtimes? |
| Dependencies | Do runtime and compile-time libraries support JDK 17? |
| Build tool/plugins | Do current Maven/Gradle versions and plugins run reliably on JDK 17? |
| Framework | Does the framework have a Java 17-compatible release and matching dependencies? |
| JVM options | Are any JVM flags removed, behavior-changed, or no longer needed? |
| Deployment | Do container images, startup scripts, health checks, and monitoring use the right JDK? |
| Source code | Do we need to adopt new Java 17 APIs or language features? |

Do not conflate these questions. An application can run on a Java 17 runtime even when its bytecode was compiled for Java 11. Conversely, the compiler may succeed while a library loaded only in production turns out to be incompatible with JDK 17.

### 2.1. Distinguish running on Java 17 from compiling for Java 17

These are two independent steps:

- **Runtime migration:** running the existing artifact on JVM 17.
- **Build/compile migration:** using the right toolchain/compiler and selecting the API/class-file target for the desired Java version.

A class file compiled for Java 11 can run on Java 17 if its dependencies and runtime behavior are compatible. Java 17 class files use major version 61. Runtimes older than Java 17 cannot load version 61 class files.

The `javac --release 17` option sets the language level, restricts usable Java SE APIs, and generates bytecode for release 17. It is not an option for choosing which JVM executes the program.

## 3. Establish a baseline before changing the JDK

The baseline is the observed behavior of the current version. Without a baseline, it is very hard to tell which behaviors Java 17 changed.

### 3.1. Record the current environment

Save the following details:

- JDK version and JDK vendor.
- Operating system, CPU architecture, and container/VM environment.
- Full startup command and JVM flags.
- Application version, commit/build number.
- Dependency graph and framework version.
- Environment variables and application configurations affecting runtime behavior.
- CPU quota, memory limit, heap size, and replica count.
- Dependent services such as databases, caches, message brokers, and HTTP services.

For example:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

For a running process, `jcmd` can be used if supported by the current JDK:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

Do not include command-line passwords, tokens, or secrets in baseline reports. Store configuration details according to your project's security policy.

### 3.2. Select representative business flows

Do not just check an endpoint that returns HTTP 200. Pick flows that exercise key components:

- Application startup and dependency injection completion.
- Database connection and query execution.
- File or object storage reads and writes.
- Message publishing and consumption if the application uses queues.
- Outbound calls to external HTTP services.
- Authentication and authorization.
- Unicode, date/time, and locale data processing.
- Batch tasks or scheduled jobs.
- Graceful shutdown and signal/termination handling.

For each flow, record inputs, expected outputs, status, side effects, and success criteria. If sensitive data is involved, use anonymized fixtures or approved test data.

### 3.3. Measure pre-upgrade behavior

| Category | Baseline to save |
|---|---|
| Startup | Startup duration, time until health check reports ready |
| Functional | Test outcomes, response/status, created/updated data |
| Performance | Throughput, p50/p95/p99 latency, error rate |
| JVM | Heap, GC, thread count, class loading |
| Resource | CPU, RSS, memory limit, file descriptors if relevant |
| Logs | Common warnings/errors and known exceptions |
| Operations | Health checks, readiness/liveness, shutdown, restart |

You do not need to measure every conceivable metric. Choose metrics tied to operational requirements and save the exact workload so you can compare later.

## 4. Run the existing artifact unchanged on JDK 17

This is an important milestone for separating runtime compatibility from build and source changes.

### 4.1. Keep the artifact fixed

Take the exact JAR/WAR/distribution currently running on the old JDK. Record its hash or build ID to confirm the artifact was not rebuilt during this test step.

If the application is packaged as a fat JAR, container image, or multi-module distribution, keep the artifact contents intact and swap only the runtime JDK in the test environment. Change only the JDK needed to run it.

### 4.2. Run with JDK 17

For example:

~~~bash
java -version
java -jar application.jar
~~~

Ensure `java` in `PATH` is genuinely JDK 17. In environments with multiple JDKs installed, use the full path to the executable to avoid ambiguity:

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -jar application.jar
~~~

If the application uses custom startup scripts, agents, native libraries, or JVM options, invoke the exact test-environment entry point and document any differences.

### 4.3. Keep everything else unchanged

On the first run, try to preserve:

- The packaged artifact and dependencies.
- Application configuration.
- Dataset and request mix.
- Equivalent database/schema and dependent services.
- CPU/memory limits and replica count.
- JVM options, provided Java 17 still accepts them.

If a legacy JVM option prevents Java 17 from starting, record the error and make only the minimal change required for the JVM to boot. Do not take the opportunity to change the collector, heap size, framework, and libraries in the same test run. Distinguish "removing an unsupported flag so the JVM boots" from "re-tuning the entire JVM configuration."

### 4.4. Why running the old artifact is valuable

If the exact same artifact runs cleanly on the old runtime but fails on Java 17, the issue likely involves:

- Changed or removed JDK APIs.
- Strong encapsulation of the module system.
- A library using internal APIs or deep reflection.
- Incompatible native/JNI components.
- Removed JVM or collector options.
- Changed runtime, security, or environment behavior.

If the artifact runs cleanly on Java 17, that provides positive evidence of runtime compatibility for the exercised flows. It does not yet prove that the build pipeline, compiler, plugins, or rarely executed code paths are compatible.

## 5. Verify startup and real behavior

### 5.1. Startup and readiness

After starting:

1. Confirm the process is running on the right JDK 17.
2. Wait for the application to finish initializing rather than just checking process existence.
3. Query readiness/health endpoints.
4. Confirm connection pools, message consumers, and schedulers are ready.
5. Inspect startup logs and warnings.

A live JVM process does not mean the application is ready to serve traffic. Readiness should reflect the status of critical dependencies according to the system's design.

### 5.2. Smoke tests and end-to-end tests

Run smoke tests first to confirm basic flows. Then run integration/E2E tests for behaviors with side effects.

| Flow | Verification | Result to save |
|---|---|---|
| Login | Authenticate and issue session/token | Expected status, claims, or session state |
| Database | Read/write a test record | Data and transaction result |
| HTTP client | Call a test dependency | Status, body, timeout behavior |
| Message | Publish and consume a message | Ack, retry, and final payload |
| File | Read/write a UTF-8 file | Expected content and byte format |
| Scheduler | Trigger a test job | Job status and side effect |
| Shutdown | Send termination signal | Resources closed and process exits |

Do not run tests that create real transactions or send external notifications unless the environment is isolated.

### 5.3. Compare results against the baseline

Do not simply mark it "pass." Compare:

- Do the new logs contain different warnings or exceptions?
- Do outputs and side effects match expectations?
- Did startup time change noticeably?
- Are throughput and latency within SLO?
- Did heap, GC, CPU, or RSS shift abnormally?
- Are there failures that only appear after prolonged execution?

A single successful smoke test is an initial step, not a substitute for regression, soak, and load tests.

## 6. Classify errors appearing on Java 17

During test runs, record the original error, stack trace, reproduction steps, and environment conditions before modifying any code.

### 6.1. UnsupportedClassVersionError

This error usually indicates that the running JVM does not support the class file version of a loaded class. When targeting Java 17, check:

- Whether the artifact or a dependency contains class files newer than version 61.
- Whether the wrong JDK runtime is on `PATH` or inside the container.
- Whether a dependency is a multi-release JAR or contains bytecode built for a different runtime.

You can inspect a class version with:

~~~bash
javap -verbose -classpath application.jar com.example.Main
~~~

For complex JARs, identify the offending class from the stack trace and inspect that exact class file. Do not rush to change the whole source target if the error actually stems from a mispackaged dependency.

### 6.2. NoClassDefFoundError, ClassNotFoundException, or NoSuchMethodError

These errors may relate to:

- Missing or incompatible dependency versions.
- Two libraries pulling in different versions of the same API.
- Classes loaded only along an untested code branch.
- Methods/classes changed or absent in the runtime dependency version.

Inspect the dependency tree, artifact contents, and class loaders. Upgrade only the relevant dependency once the cause has been identified.

### 6.3. InaccessibleObjectException or module access errors

Java 17 enforces strong encapsulation for JDK internals under JEP 403. Older frameworks may use reflection to access private fields or internal packages.

Resolution approach:

1. Identify the class/package being accessed.
2. Check whether a Java 17-compatible version of the framework/library exists.
3. Upgrade the library or switch to public APIs.
4. If `--add-opens` is needed as a temporary bridge, open the exact package to the exact module and document a removal plan.

Do not add broad `--add-opens` flags to mask every error. That weakens encapsulation and obscures dependencies that actually need fixing.

### 6.4. JVM fails to start due to invalid options

Several legacy JVM flags have been deprecated or removed. For instance, the CMS collector was removed prior to Java 17; `-XX:+UseConcMarkSweepGC` is not a valid configuration for Java 17.

When encountering an option error:

- Save the exact JVM message.
- Identify whether the flag relates to GC, memory, logging, modules, or diagnostics.
- Check Java 17 documentation for its current status.
- Remove unsupported flags or replace them with modern equivalents serving the same goal.
- Change only one option group at a time and record the impact.

Do not copy a block of JVM flags from an old blog post without verifying them against the exact JDK.

### 6.5. JNI/native library errors

An application can boot Java yet fail when loading native libraries due to:

- CPU architecture mismatch.
- Native binary incompatibility with the OS or ABI.
- Native library dependencies on another runtime.
- JNI/JNA or wrapper versions not supporting the new environment.

Verify the architecture, loaded libraries, and Java 17 support versions. If native dependencies must be updated, perform that as a separate verifiable change.

## 7. Inventory internal and deprecated APIs

Once the artifact runs, inspect the source and dependencies to uncover latent risks.

### 7.1. Find JDK internals with jdeps

Run on the JAR:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

`jdeps` can detect many static references to JDK internal APIs and suggest replacements when available. The output helps pinpoint classes or dependencies that need attention.

Limitation: static analysis cannot guarantee detection of dynamically constructed class names, string-based reflection, runtime-generated code, or plugins loaded only under rare configurations.

### 7.2. Find deprecated APIs with jdeprscan

~~~bash
jdeprscan --release 17 application.jar
~~~

Deprecated APIs and internal APIs are two distinct groups. A public API can be deprecated; an internal API might not be marked deprecated yet still carry no support guarantee. Use both tools when a broader picture is needed.

### 7.3. Inspect third-party dependencies

For each library:

- Confirm Java 17 support in the vendor's documentation.
- Check whether frameworks, plugins, or agents depend on JDK internals.
- Check native components and annotation processors.
- Check libraries loaded only on test, startup, or production paths.
- Identify minimum compatible versions and transitive dependencies.

You do not necessarily have to upgrade every library to its very latest release. Choose versions that are compatible, supported, and tested with the application.

## 8. Upgrade build tools and compiler only after runtime tests

Once you have runtime results for the existing artifact on Java 17, move on to the build pipeline.

### 8.1. Confirm the build tool runs on JDK 17

Check Maven/Gradle and plugin versions. The build tool itself may run on JDK 17 while an older plugin still uses internal APIs or lacks runtime support.

Record:

- Build tool version.
- Compiler plugin/toolchain version.
- Annotation processors.
- Test runners and code coverage agents.
- Packaging, shading, bytecode enhancement, and instrumentation plugins.

If the build fails before compiling source code, distinguish a build tool/plugin failure from a source code failure. Do not edit source code to work around a plugin that cannot run on JDK 17.

### 8.2. Use explicit toolchains

In Gradle, Java toolchains specify which JDK compiles and tests code independently of the machine's default JDK:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

In Maven, configure the compiler plugin at a project-supported version and set the release:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

These snippets illustrate the declaration; full syntax and plugin versions should be verified against your project's build setup.

### 8.3. Why prefer --release?

`--release 17` restricts the Java SE APIs source code can reference to release 17 and emits matching class files. Setting only `-source 17` and `-target 17` does not guarantee the compiler uses only Java 17 APIs; if building on a newer JDK, source code could accidentally call APIs introduced after the target.

If the application only needs to run on Java 17, `--release 17` is usually the clearest choice for the compiler. If older runtimes must also be supported, choose the lowest required release and test on every target runtime.

## 9. Upgrade dependencies and frameworks in groups

Once the build tool is stable, address libraries.

### 9.1. Do not upgrade all dependencies at once

Group related components:

1. Core framework and foundational dependencies.
2. Logging and monitoring.
3. Persistence/ORM/database drivers.
4. HTTP client/server and serialization.
5. Security/authentication.
6. Test frameworks, mocking libraries, and agents.
7. Plugins or native integrations.

The exact order depends on the dependency graph. Before upgrading, check release notes and framework version requirements.

### 9.2. Lock versions for repeatable tests

Do not allow version ranges or dynamic dependencies to drift between two runs. Save a dependency lockfile or dependency tree using your build tool's mechanism.

If multiple libraries must be upgraded together because a new framework requires them, treat that as a single cohesive change group and document the reason. Run tests afterward before moving to the next group.

### 9.3. Watch out for agents and instrumentation

APM agents, profilers, coverage agents, mocking frameworks, and bytecode enhancers can interfere with class loading or instrumentation. They are often overlooked if you inspect only runtime dependencies.

Run tests with the same agents and configuration planned for deployment. If an agent is suspected of causing an error, perform a controlled run without the agent to isolate the cause, then verify the agent version supports JDK 17.

## 10. Modify source code after the runtime is stable

There is no need to rewrite the entire codebase just because the application moved to Java 17. First identify which source changes are genuinely required for compatibility or design improvements.

### 10.1. Fix dependencies on internal APIs

Replace internal APIs with corresponding public APIs, or redesign if no direct replacement exists. Do not keep an unsupported dependency merely because it still runs on a particular JDK build.

### 10.2. Address deprecated APIs

Read Javadoc and release notes to see what replacements exist for deprecated APIs. Not every deprecated API is removed in Java 17, but new code should avoid adding dependencies on APIs flagged for removal.

Use `jdeprscan --release 17` to aid inventorying, then review each occurrence in the source.

### 10.3. Do not adopt every new language feature immediately

Java 17 offers useful language and API features, but runtime migration does not require converting existing code to records, sealed classes, text blocks, or pattern matching. Adopting new features should be a separate set of changes after the runtime and build are stable.

Separate the two goals:

- **Compatibility:** getting the existing application running properly on Java 17.
- **Modernization:** improving source code using Java 17's new capabilities.

When these two goals are delivered separately, regressions are much easier to trace.

## 11. Test after every checkpoint

Each checkpoint should have a fixed test suite:

| Checkpoint | Change | Required tests |
|---|---|---|
| A | Runtime switched to JDK 17 only | Startup, smoke, critical E2E, logs |
| B | Minimal JVM options fixes | Startup, GC/resource metrics, shutdown |
| C | Build tool/compiler upgrade | Clean build, unit tests, packaging |
| D | One dependency group upgraded | Unit/integration/E2E related to that group |
| E | Source compatibility fixes | Regression tests and boundary tests |
| F | Performance tuning | Load/soak tests compared against baseline |

Do not advance to the next checkpoint while the current one still has unexplained failures. If an exception is accepted, document its impact and owner.

### 11.1. Functional testing

Compare results against the baseline:

- Returned payloads.
- Side effects.
- Exceptions and error handling.
- Serialization/deserialization where applicable.
- Date/time, timezone, locale, and encoding.
- Security behavior, TLS, and certificates.

### 11.2. Load testing

Once functionality is verified, run a workload matching the baseline. Compare throughput, p95/p99, error rate, CPU, heap, GC, and RSS.

Do not tweak heap or GC just because numbers differ slightly from the baseline. Determine whether any SLO is violated, budget is exceeded, or abnormal trend appears.

### 11.3. Long-running soak tests

Soak tests help uncover:

- Gradually increasing heap or RSS.
- Unreleased threads or connections.
- Continuously growing queues.
- Errors appearing only after repeated reconnects/retries.
- Scheduled tasks failing to run or running concurrently in duplicate.
- Resource leaks during reload/shutdown.

## 12. Build a test matrix to isolate root causes

A simple matrix:

| Experiment | Runtime JDK | Artifact/build | Dependencies | Goal |
|---|---|---|---|---|
| Baseline | Current JDK | Current artifact | Current | Record baseline behavior |
| Runtime-only | JDK 17 | Same artifact | Same dependencies | Identify runtime compatibility bugs |
| Build-only | JDK 17 | Updated build tool/compiler | Dependencies unchanged | Verify build pipeline |
| Dependency group 1 | JDK 17 | Stable build | Upgrade group 1 only | Isolate framework/dependencies |
| Dependency group 2 | JDK 17 | Stable build | Upgrade group 2 only | Isolate next group |
| Source migration | JDK 17 | Release 17 | Selected dependencies | Verify source/API target |
| Final candidate | JDK 17 | Target config | Target dependency set | Regression, load, and soak |

If forced to change many components together due to mandatory coupling, document the change group and test along the smallest feasible boundaries. Each row in the table does not have to be a separate release; what matters is fault attribution.

## 13. Manage rollbacks and trial deployments

### 13.1. Retain old artifacts and configurations

Before deploying:

- Keep the currently running artifact.
- Keep the image/container digest.
- Keep JVM options and environment variables.
- Keep dependency lockfiles/manifests.
- Document how to revert to the previous runtime.

Do not overwrite old artifacts during testing. Maintain reproducible builds and know the exact commit that produced each build.

### 13.2. Test on staging/canary

Deploy Java 17 to staging or a small slice of traffic following your system's rollout process. Monitor:

- Startup/readiness.
- Error rate.
- Latency.
- CPU/RAM/GC.
- Dependency failures.
- Logs and alerts.

A canary must have clear stop criteria. If metrics cross thresholds, halt the rollout and revert to the known-good artifact/runtime.

### 13.3. Rollbacks must be verified

Rollback is not merely changing an image tag. Verify:

- Are database migrations backward-compatible?
- Have queue/message formats changed?
- Have cache keys or serialized payloads changed?
- Can the old artifact read data written by the new candidate?
- Can configuration be reverted without losing secrets or settings?

If data migrations are not backward-compatible, address deployment ordering and recovery plans before rolling out.

## 14. Example upgrade workflow for an application

Suppose a service runs on Java 11, builds `orders-service.jar`, and uses a database, HTTP client, and message broker.

### Phase 1: Baseline on Java 11

~~~bash
java -version
java -jar orders-service.jar
~~~

Run smoke/E2E tests and save startup time, request latency, error rate, heap/GC, and logs.

### Phase 2: Run the exact artifact on Java 17

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -jar orders-service.jar
~~~

Keep the artifact, config, dataset, and dependencies unchanged. Re-run the same test suite. If the JVM fails to start due to a legacy option, remove/replace only the offending option and record it.

### Phase 3: Inventory dependencies

~~~bash
jdeps --jdk-internals --recursive orders-service.jar
jdeprscan --release 17 orders-service.jar
~~~

Review outputs, check frameworks, agents, database drivers, and native dependencies. Create a task list with owners and corresponding tests.

### Phase 4: Update the build pipeline

Update the build tool/plugins needed to run on JDK 17. Configure the compiler release for the target. Run a clean build and unit tests without upgrading all dependencies yet.

### Phase 5: Upgrade dependencies in groups

Upgrade frameworks/dependencies in the order dictated by the dependency graph. After each group, run relevant integration/E2E tests and record differences.

### Phase 6: Finalize source and configuration

Replace internal APIs, fix reflection access, update JVM options to modern equivalents, and adopt Java 17 language/API features only when warranted.

### Phase 7: Test the final candidate

Run regression, load, soak, and shutdown tests in a production-like environment. Compare against the baseline and roll out canary according to defined criteria.

## 15. Common mistakes

### 15.1. Changing JDK, framework, and dependencies all at once

When the app breaks, you cannot tell whether the fault lies in the runtime or library changes.

**How to handle:** run the existing artifact on JDK 17 first, then change components in groups.

### 15.2. Checking compilation success only

Compilation does not exercise all code paths, nor does it verify runtime plugins, reflection, native libraries, or lazily loaded dependencies.

**How to handle:** run startup, smoke, integration, E2E, and critical operational flows.

### 15.3. Treating `--release 17` as a runtime selector

`--release` is a compiler flag; it does not select the JVM at runtime.

**How to handle:** separately verify `java -version` and the compiler release.

### 15.4. Adding broad --add-opens to ignore errors

This may get the app running temporarily while hiding dependencies on private JDK internals.

**How to handle:** upgrade the framework or replace internal APIs; if temporary flags are needed, narrow the package/module scope and set a removal plan.

### 15.5. Upgrading every library to latest

Latest does not necessarily mean most compatible with the current application. Large jumps can pull in breaking changes and obscure root causes.

**How to handle:** pick supported versions aligned with the dependency graph and upgrade in groups.

### 15.6. Tuning GC/heap before establishing a baseline

Changing the collector and heap size at the same time as runtime migration destroys comparability.

**How to handle:** keep configuration close to the baseline during runtime-only testing; tune only after functionality is stable and backed by metrics.

### 15.7. Running a smoke test only once

One successful startup does not prove background jobs, reconnects, shutdown, or high load behave properly.

**How to handle:** test across the business-flow and workload matrix, including soak tests where appropriate.

### 15.8. Failing to keep old artifacts/configs

Without a known-good prior build, rollbacks become unpredictable.

**How to handle:** preserve the baseline artifact, image digest, config, and dependency lockfile.

## 16. Checklist for a Java 17 test run

**Before running:**

- [ ] Record the current JDK version, build ID, and configuration.
- [ ] Save the unmodified artifact and verify its hash/build identity.
- [ ] Prepare a test environment with equivalent dependencies.
- [ ] Select smoke/E2E tests and a representative workload.
- [ ] Define metrics and pass/fail criteria.
- [ ] Prepare a way to revert to the old artifact/runtime.

**During the run:**

- [ ] Confirm JDK 17 is actually running the process.
- [ ] Record every JVM option that had to be changed to start.
- [ ] Verify startup and readiness.
- [ ] Execute representative business flows.
- [ ] Collect logs, errors, latency, throughput, and resource metrics.
- [ ] Record errors along with stack traces and reproduction steps.

**After the run:**

- [ ] Compare against the baseline.
- [ ] Classify errors as runtime, dependency, build, source, or deployment.
- [ ] Run jdeps/jdeprscan to inventory dependencies.
- [ ] Proceed to the next change group only once current results are explained.
- [ ] Save the artifact, config, results, and go/rollback decision.

## 17. Hands-on exercises

### Exercise 1 — Create a baseline

Select an application running on a JDK lower than 17. Record its runtime version, artifact, JVM flags, dependencies, startup time, health check, several business flows, and performance metrics.

### Exercise 2 — Runtime-only test

Run the unmodified artifact on JDK 17 in a test environment. Do not change source or dependencies. Record startup, smoke tests, and logs. If a JVM option had to be changed to boot, explain why and record the old/new options.

### Exercise 3 — Classify errors

For each error below, identify the first area to investigate: `UnsupportedClassVersionError`, `NoSuchMethodError`, `InaccessibleObjectException`, native library load failure, and invalid JVM option. State what data to collect before fixing.

### Exercise 4 — Inventory dependencies

Run `jdeps --jdk-internals` and `jdeprscan --release 17` on the artifact. Distinguish internal API findings from deprecated API findings. Explain the limitation when a dependency uses dynamic reflection.

### Exercise 5 — Separate build migration

After the runtime-only test, update the build tool/compiler to use JDK 17 and `--release 17`. Run a clean build and unit tests without upgrading dependencies yet. Classify failures as build tool/plugin versus source.

### Exercise 6 — Upgrade one dependency group

Pick one group, such as database drivers or HTTP clients. Upgrade to a supported version, run related tests, and compare against the baseline. Do not alter other groups in the same experiment.

### Exercise 7 — Design a rollback

Write a procedure to revert to the old artifact/runtime. Determine whether the database, queues, caches, and serialized data are backward-compatible. State rollout stop conditions.

## 18. Completion criteria

Learners have mastered this lesson when they can:

1. Explain why an existing artifact should be tested on JDK 17 before changing multiple components.
2. Distinguish runtime migration, build migration, and source modernization.
3. Establish a baseline covering environment, workload, functionality, and metrics.
4. Run the exact artifact with a JDK 17 executable and verify the actual runtime.
5. Execute appropriate startup, readiness, smoke, E2E, load, and soak tests.
6. Classify class version, dependency, module access, JVM option, and native library errors.
7. Use jdeps/jdeprscan appropriately and understand static analysis limitations.
8. Update build tools, compilers, and dependencies at verifiable checkpoints.
9. Use `--release 17` for its proper role without confusing it with runtime selection.
10. Compare results against the baseline and maintain an actionable rollback plan.

## 19. Official documentation

- [Java SE 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): key changes to consider when migrating applications to JDK 17.
- [Java SE 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html): changes, removals, and compatibility issues in Java 17.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): impact of strong encapsulation.
- [Java SE 17 man page — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, compiler options, and compilation behavior.
- [Java SE 17 man page — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency and JDK internal analysis.
- [Java SE 17 man page — jdeprscan](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): detecting deprecated APIs.
- [Java SE 17 man page — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): launching applications and JVM options.

**Key takeaway:** Before changing frameworks, dependencies, compilers, and JVM flags all at once, run the existing artifact on JDK 17 to establish a runtime compatibility checkpoint. Record a baseline, test real flows, classify errors, and upgrade component groups sequentially. Conclude the migration is stable only after the build, functionality, operations, and performance have all been verified in the target environment.
