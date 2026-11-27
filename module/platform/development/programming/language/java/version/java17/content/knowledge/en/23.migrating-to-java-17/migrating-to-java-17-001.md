# Inventorying Source Code, Dependencies, Plugins, and Runtime Environment When Upgrading to Java 17

Upgrading an application to Java 17 is not just swapping the JDK and re-running the build command. Source code may call APIs that have been removed from the JDK; dependencies may not yet support Java 17; build plugins may require a different JDK; and the production runtime may pass legacy JVM flags or rely on behavior that is no longer supported.

Before migrating, build an evidence-backed inventory across four groups:

1. **Source code:** JDK APIs, deprecated/removed APIs, JDK internal APIs, reflection, modules, and native code.
2. **Dependencies:** direct/transitive libraries, frameworks, drivers, agents, and components running alongside the application.
3. **Plugins and build tools:** Gradle/Maven, compiler, test framework, annotation processors, code generators, static analysis, packaging, and CI tools.
4. **Runtime environment:** JDK distribution, JVM options, container/OS/CPU/memory, TLS/certificates, locale/timezone, environment variables, filesystem, and external services.

The goal is to identify what the application depends on, which parts carry incompatibility risks, who owns resolving them, and what evidence proves an item has been verified. This is the preparation step prior to migration; avoid upgrading versions en masse before understanding the actual dependencies and workload.

## 1. Define scope and baseline

Start by identifying the applications, artifacts, and environments within the upgrade scope. Record the repository, source revision/commit, service/module name, output artifact, current JDK, build tool, build profile, and deployment environment.

Do not assume every module in a monorepo uses the same JDK or build profile. One module may be on Java 8, another on Java 11, and another already on Java 17. Inventory by module/service rather than looking only at the root project.

### 1.1. Separate the three Java versions

| Component | Question to answer |
| --- | --- |
| Build runner JDK | Which JDK are Gradle/Maven and plugins running on? |
| Compile/test toolchain JDK | Which JDK do the compiler and test tasks use? |
| Runtime JDK | Which JDK does staging/production actually run on? |
| Release target | Which version are the target source, bytecode, and APIs at? |

The first three layers do not have to be identical. The Gradle daemon can run on one JDK, compiler tasks can use a different toolchain, and the artifact can be compiled with a lower release target. When targeting Java 17, you must verify the ability to run the build tool, compile, and run the artifact.

### 1.2. Collect the baseline

Before making changes, record:

- Build command, build result, and build duration.
- Unit/integration test results.
- Startup time and shutdown behavior.
- CPU, memory, heap, and GC behavior.
- Request latency p50/p95/p99, throughput, and error rate.
- Important logs, exceptions, and warnings.
- JVM flags, system properties, and environment variables.
- Smoke test and performance test results.

The baseline helps distinguish regressions caused by the Java upgrade from pre-existing issues. Without pre-upgrade metrics, evaluating whether "Java 17 runs fine" easily devolves into guesswork or merely checking whether the application starts up.

## 2. Inventory Java source code

The objective is to find places in the source code that may be affected by changes in the JDK, module system, APIs, and runtime behavior. Do not only search imports: APIs can be referenced by fully qualified name, reflection, service loading, generated source, or internal libraries.

### 2.1. Deprecated, deprecated-for-removal, and removed APIs

Distinguish between:

- **Deprecated:** the API still exists but is discouraged for new code.
- **Deprecated for removal:** the API carries a warning that it will be removed in the future; prioritize evaluating these.
- **Removed:** the API or module is no longer in the JDK; source or dependencies calling it directly may fail to compile or fail to run.

The JDK provides `jdeprscan` to scan compiled bytecode:

```bash
jdeprscan --release 17 path/to/application.jar
jdeprscan --release 17 --for-removal path/to/application.jar
```

The second command focuses on APIs deprecated for removal. Use the appropriate syntax per `jdeprscan --help` for the JDK you are using; record the tool version and output for reproducibility.

`jdeprscan` analyzes compiled classes/JARs. It does not replace searching source code, configuration, reflection strings, or APIs called indirectly through frameworks. Transitive dependencies may still call deprecated APIs even if the application source does not import them.

### 2.2. JDK internal APIs

Internal packages such as `sun.*` or implementation-specific APIs are not stable public contracts. Use `jdeps` to find references to JDK internals:

```bash
jdeps --multi-release 17 --jdk-internals path/to/application.jar
```

For each finding, record the calling class, the internal package/class being used, the dependency that owns that code, and the public API that can replace it.

Java 17 enforces strong encapsulation for JDK internals under JEP 403. Do not use `--illegal-access=permit` as a migration solution: this option no longer opens up access as it did in older JDKs. Prioritize upgrading or replacing the component; only consider narrowly scoped `--add-exports` or `--add-opens` when there is a clear technical justification and a removal plan.

### 2.3. Modules/APIs bundled in older JDKs

If the application is being upgraded from Java 8 or an older JDK, check APIs that used to be bundled with the JDK but have since been decoupled or removed. For example:

- Java EE/CORBA modules such as JAXB, JAX-WS, Activation, and CORBA were removed from the JDK in Java versions prior to Java 17.
- The Nashorn JavaScript engine was removed from the JDK in Java 15.
- The CMS garbage collector was removed in Java 14.
- Pack200 tools/APIs were removed in Java 14.
- RMI Activation was removed in Java 15.

If the application still uses these components, identify replacement dependencies or remove the corresponding functionality before running on Java 17.

Do not assume that every package starting with `javax.` has been removed. Java SE still includes many supported `javax` packages, such as `javax.crypto`, `javax.naming`, and `javax.sql`. Only address packages that are genuinely no longer provided by the JDK or belong to framework APIs that have changed.

Do not mass-replace `javax` with `jakarta` via search/replace. Moving from Java EE to Jakarta EE is a separate framework/platform change that depends on API versions and the application server; it is not a blanket rule for Java 17.

### 2.4. Reflection and deep access

Search for code using:

- `Class.forName()` with class names loaded from configuration.
- `getDeclaredField()`, `getDeclaredMethod()`, and `setAccessible(true)`.
- Reflection into JDK packages or packages belonging to other modules.
- Frameworks that dynamically generate proxies or access private fields.
- `--add-opens` and `--add-exports` configurations.

Strong encapsulation can block deep access that previously worked on older JDKs. Record the source module, package, target module, and purpose of access.

| Component | Package/class | Access mechanism | Purpose | Resolution |
| --- | --- | --- | --- | --- |
| JSON framework | Model package | Reflection on fields | Serialize/deserialize | Check framework version and opens requirements. |
| Legacy library | JDK internal package | Reflection | Read internal state | Upgrade/replace the library. |
| Test plugin | Application private package | Reflection | Test fixture | Check test module and test runtime. |

Do not open entire modules to all components just to silence errors. If opens are required, restrict them to the exact package and the exact framework module.

### 2.5. APIs and runtime behavior to review

Beyond removed APIs, inspect areas where runtime behavior can change:

- Default charset and file reading/writing.
- Timezone, locale, and date/time formatting.
- TLS protocols, cipher suites, certificates, and trust stores.
- Serialization and module encapsulation.
- Garbage collector and JVM flags.
- Processes, threads, and container resource awareness.
- Security providers and restricted algorithms.
- Class loading, service loading, and resource lookup.

Many issues only surface at runtime: TLS to legacy servers, parsing data with the wrong charset, or frameworks attempting to access private members.

## 3. Analyze module-level dependencies with jdeps

`jdeps` analyzes dependencies between classes, packages, and modules in bytecode. The tool helps answer which packages and JDK modules the application references.

```bash
# Dependency summary
jdeps --summary path/to/application.jar

# Recursive analysis
jdeps --recursive --summary path/to/application.jar

# Print required modules
jdeps --multi-release 17 --print-module-deps path/to/application.jar

# Find missing dependencies
jdeps --missing-deps path/to/application.jar

# Find JDK internal APIs
jdeps --multi-release 17 --jdk-internals path/to/application.jar
```

Use `--multi-release 17` when analyzing multi-release JARs for the target runtime. For applications spanning multiple JARs, provide the appropriate classpath/module-path; analyzing a single JAR in isolation may report missing dependencies simply because related libraries were not passed to the command.

### 3.1. Limitations of static analysis

`jdeps` cannot fully detect every dynamically generated or loaded dependency. Perform additional checks for:

- Reflection based on class names in properties/YAML/XML.
- Service Provider Interface and `ServiceLoader`.
- Classes loaded from a plugin directory or custom class loader.
- Annotation processors generating source/classes at build time.
- JNI/JNA and native libraries.
- Bytecode generated at runtime.
- Framework classpath scanning.
- Dependencies that only appear in rarely enabled profiles or features.

`jdeps` is important evidence, not a complete inventory of an application's dependencies.

## 4. Inventory direct and transitive dependencies

For each dependency, record coordinates/version, scope, direct/transitive status, minimum supported Java version, framework compatibility, maintenance status, security advisories, module name, native components, and reflection/class loading requirements.

### 4.1. Gradle dependency graph

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

For multi-project builds, inspect each subproject and relevant configuration. `runtimeClasspath` does not include all test dependencies, plugins, or annotation processors.

### 4.2. Maven dependency graph

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom
```

`dependency:tree` shows direct/transitive dependencies; `effective-pom` shows the configuration after applying the parent POM, properties, and profiles. Run under CI/production profiles because the graph can vary by profile.

### 4.3. Compile vs. runtime dependencies

A library can compile successfully yet fail at runtime because a dependency is only in compile scope, was excluded from the package, or differs in version across environments.

Inventory separately:

- Compile classpath.
- Runtime classpath/module path.
- Test classpath.
- Annotation processor path.
- Plugin classpath.
- Application server-provided libraries.
- Dependencies packaged inside fat JARs or images.

Do not inspect only the root `pom.xml` or `build.gradle`; verify which libraries the final artifact actually bundles.

## 5. Evaluate each dependency for Java 17 compatibility

A dependency should be considered ready when supported by solid evidence:

- The vendor announces Java 17 support for the version in use.
- Release notes mention JDK 17-related changes.
- The library's CI runs tests on Java 17.
- The artifact does not depend on encapsulated JDK internal APIs.
- The application's integration tests pass with that version.
- There are no unresolved security issues.

Do not conclude compatibility merely because a library downloads or compiles. An older library may fail when reflection, TLS, class loading, or native code is executed.

| Category | Criteria | Action |
| --- | --- | --- |
| Compatible | Vendor supports Java 17 and application tests pass. | Keep version or upgrade intentionally. |
| Compatible with constraints | Runs but requires specific flags/configs/versions. | Record constraint, owner, and workaround removal plan. |
| Upgrade required | Current version does not support Java 17 or has confirmed bugs. | Select replacement version and run regression tests. |
| Replace/remove | Unmaintained or no compatible release exists. | Replace or remove. |
| Unknown | No documentation or runtime evidence yet. | Create test/POC; do not mark compatible prematurely. |

Beyond business libraries, check logging, JSON/XML serializers, database drivers, ORMs, HTTP/messaging clients, cloud SDKs, web frameworks, dependency injection, proxy frameworks, caches, schedulers, security providers, monitoring agents, native access, and testing frameworks.

APM/profiler/bytecode instrumentation agents may not appear in compile dependencies yet still run inside the JVM. They require Java 17-compatible versions.

## 6. Inventory frameworks and application servers

Frameworks frequently use reflection, proxies, annotation scanning, and bytecode generation. Record the framework/module/version, Java support matrix, servlet/Jakarta APIs, application server/container, integration modules, and module opens requirements.

### 6.1. Servlet and Jakarta namespaces

If the application runs in a servlet container or application server, record the container version and the API namespace in use.

`javax.servlet` and `jakarta.servlet` are two different namespaces. Moving from Java EE to Jakarta EE may require changing namespaces and frameworks; that is a separate platform migration step, not something that happens automatically just by switching the JDK to Java 17.

Distinguish server-provided APIs from dependencies packaged in the application. Document `provided` scope (or equivalent) and the actual server version.

### 6.2. Framework reflection and proxies

Check `--add-opens`, `--add-exports`, reflection into JDK packages, proxy generation, bytecode enhancement, ORM instrumentation, and serialization.

Prioritize upgrading the framework to a version that supports Java 17. If opening packages is still required, record the package, framework module, justification, and review deadline. Do not use a broad list of opens across the entire JDK as a long-term configuration.

## 7. Inventory plugins and build tools

Build plugins are also code running on the JDK and may use changed APIs. Having compatible runtime dependencies does not guarantee older plugins can run on JDK 17.

List:

- Gradle/Maven wrapper and version.
- Compiler plugins.
- Test runners/test frameworks.
- Annotation processors.
- Code generators.
- Static analysis/linters.
- Coverage tools.
- Packaging/shading/fat JAR plugins.
- Javadoc/source archive plugins.
- Container/image build plugins.
- Database migration plugins.
- Quality/security scan plugins.
- Internal and convention plugins.

For each plugin, record the version, minimum JDK required to run, compatible build tool versions, and evidence on Java 17.

### 7.1. Gradle

```bash
./gradlew --version
./gradlew tasks
./gradlew buildEnvironment
```

`buildEnvironment` shows the buildscript classpath; it does not replace checking the plugins DSL and plugin resolution across all subprojects. Inspect `settings.gradle`, `settings.gradle.kts`, version catalogs, and convention plugins.

The Gradle daemon JVM and Java toolchain are two different settings. Gradle 7.3 and higher support running Gradle on Java 17. If the wrapper is older, check the compatibility matrix for that exact Gradle version and upgrade the wrapper before switching the daemon to JDK 17.

In build scripts, check the plugins DSL, buildscript dependencies, custom tasks using internal Gradle APIs, toolchain/compiler options, test JVM args, annotation processors, and tasks invoking standalone JDK executables.

Do not upgrade the Gradle wrapper, plugins, and dependencies simultaneously without a baseline. Changing them in separate groups helps pinpoint the cause when a build fails.

### 7.2. Maven

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

Inspect plugins in the parent POM, `pluginManagement`, profiles, and build extensions. Pin plugin versions explicitly; do not rely on default versions that can vary with the Maven super POM or environment.

Distinguish the Maven runtime JDK from the JDK used by compiler/test plugins. If using Maven Toolchains, check `toolchains.xml` and which JDK is actually selected.

### 7.3. Annotation processors and code generators

Tools such as Lombok, MapStruct, Dagger, QueryDSL, or internal generators run during the compile phase and depend on the compiler/JDK.

Record the processor version, JDK support, compiler plugin, processor path, generated source location, and clean build results on Java 17. If CI generates fresh code, verify that generation is reproducible and does not depend on an older JDK.

## 8. Inventory test, quality, and coverage tooling

Test frameworks may rely on deep reflection or bytecode instrumentation. Check JUnit/TestNG, Mockito/Byte Buddy/CGLIB, coverage tools, test containers, embedded servers, integration tests, static analysis, and test JVM arguments.

Specifically check tests relying on private reflection, mocking final classes, dynamic agent attachment, or bytecode instrumentation. If tests run on JDK 17 but the coverage or mocking plugin does not yet support it, the build may only fail during the test phase.

Separately record which tests run in CI and which only run manually. A suite that is not executed regularly is not reliable compatibility evidence.

## 9. Inventory Java agents, native libraries, and external tools

### 9.1. Java agents

Search for `-javaagent:`, `-agentlib:`, and `-agentpath:` arguments. Agents may be APMs, tracers, profilers, security monitors, coverage tools, or bytecode transformers.

Record the version, vendor, loading mechanism, JVM support matrix, and configuration. An incompatible agent can prevent the JVM from starting, corrupt bytecode transformations, or degrade performance.

### 9.2. JNI/JNA and native libraries

Inventory `System.loadLibrary()`, `System.load()`, JNI/JNA dependencies, native libraries bundled in JARs, OS/architecture-specific binaries, libc/OpenSSL, and `java.library.path` settings.

Java 17 does not make old native binaries compatible automatically. Verify OS, CPU architecture, ABI, and native library versions. For containers, also check the base image and system libraries inside the image.

### 9.3. External tools outside the JVM

Applications or builds may invoke `keytool`, `jarsigner`, `jlink`, `jdeps`, shell scripts, Node/Python, cloud/database CLIs, or Docker/BuildKit. Record versions and installation sources. Do not assume they automatically switch with `JAVA_HOME`.

## 10. Inventory JVM options and runtime flags

Production runtimes may carry flags accumulated over many years. Some flags have been removed, changed meaning, or are no longer appropriate for Java 17.

Gather configurations from startup scripts, service definitions, Dockerfiles, Kubernetes manifests/Helm values, CI/CD, application servers, and environment variables such as `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and `_JAVA_OPTIONS`.

| Group | Examples to record |
| --- | --- |
| Heap | `-Xms`, `-Xmx`, `-XX:MaxRAMPercentage` |
| GC | Collector flags, pause/throughput goals, GC logging |
| Module/reflection | `--add-opens`, `--add-exports` |
| Security/TLS | Trust store, keystore, provider, disabled algorithms |
| System properties | `-D...`, locale, timezone, proxy |
| Agents | `-javaagent`, `-agentlib`, `-agentpath` |
| Diagnostics | JFR, heap dump, error file, GC log |

### 10.1. Removed or ineffective flags

Do not copy the entire set of JVM options from an older JDK to Java 17 without checking them.

The CMS GC was removed from HotSpot prior to Java 17. If startup scripts still pass `-XX:+UseConcMarkSweepGC` or CMS tuning flags, remove them and select a currently supported collector after measuring the workload.

`--illegal-access` is no longer a way to grant internal access in Java 17. To resolve reflection errors, upgrade the dependency or identify the exact package/module that needs to be opened.

Check options on the target JVM:

```bash
java -XX:+PrintFlagsFinal -version
java -Xlog:help
java --help
```

Test the application's startup command in staging and inspect warnings/errors when the JVM parses flags. Do not rely solely on whether a flag appears in a config file.

### 10.2. GC and memory settings

Record the current collector, `-Xms`/`-Xmx`, pause/throughput goals, GC logging, heap dump settings, container memory limit, direct memory, native memory, and thread counts.

Do not switch GCs merely because you are upgrading the JDK. Verify the workload and baseline first; after upgrading, compare GC pauses, allocation rates, throughput, and latency.

## 11. Inventory the runtime environment

An application can build cleanly on JDK 17 yet fail when deployed because the runtime environment differs from the developer machine. Create separate tables for local, test, CI, QA/staging, performance test, production, and disaster recovery.

For each environment, record OS, architecture, JDK distribution/build, CPU, memory, container image, JVM args, certificates, environment variables, and service endpoints.

### 11.1. OS and CPU architecture

Check Windows/Linux/macOS and version, x86_64/AArch64, kernel/libc when native libraries are used, file permissions, path separators, filesystem case sensitivity, process signals, and service managers.

Do not use Windows test results to conclude Linux production will behave identically if the application uses native libraries, paths, shell commands, or platform-dependent filesystem behavior.

### 11.2. Containers and resource limits

Record the base image/digest, JDK/JRE distribution, CPU quota/request, memory limit, entrypoint, user, mounted volumes, secrets, health checks, and shutdown grace period.

On supported Linux containers, the JVM can detect container resource limits and use them for ergonomics. Still, verify how many CPUs and how much memory the JVM actually sees; do not infer it from host settings.

```bash
java -version
java -XshowSettings:system -version
java -XX:+PrintCommandLineFlags -version
```

These commands inspect runtime details and selected flags. Output depends on the platform and container metadata access permissions.

### 11.3. Environment variables and system properties

Record variables affecting runtime behavior such as `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, proxies, truststore, locale/timezone, application profile, database/message broker endpoints, and feature flags.

Do not write secrets into the inventory or logs. Record only the variable name, source, applicable environments, and owner; secret values belong in a secret manager or appropriate security mechanism.

## 12. Check TLS, certificates, and external connections

Changing the JDK can change TLS implementations, security providers, trust stores, and permitted algorithms. Older endpoints may only support protocols/ciphers no longer accepted by the client.

Inventory:

- HTTPS endpoints, database TLS, LDAP, message brokers, and external APIs.
- TLS versions and cipher suites.
- Certificate chains and CA trust.
- Keystore/truststore types, formats, and locations.
- Certificate expiration/rotation.
- Custom security providers.
- Mutual TLS, proxies, and network inspection.
- Security properties and restricted algorithms.

Do not weaken security policies or re-enable weak algorithms just to make legacy connections work. Identify the endpoint, server version, and certificate chain; coordinate upgrading the server or configuring appropriate trust/security.

For TLS errors, capture the full exception, peer/endpoint, timestamp, protocol, and certificate chain (without sharing private keys). Run integration tests from the actual Java 17 runtime image.

## 13. Check charset, locale, and timezone

Applications can depend on the machine's default charset, locale, or timezone. Check:

- `new String(byte[])` or `String.getBytes()` without an explicit charset.
- `FileReader`/`FileWriter` using the default charset.
- Number/date/time formatting without an explicit `Locale`.
- Calls to `ZoneId.systemDefault()` or `TimeZone.getDefault()`.
- Date/time parsing without a zone or offset.
- Resources generated on Windows and executed on Linux.

You can print runtime defaults:

```java
System.out.println("Java version: " + Runtime.version());
System.out.println("Default charset: " + java.nio.charset.Charset.defaultCharset());
System.out.println("Default locale: " + java.util.Locale.getDefault());
System.out.println("Default zone: " + java.time.ZoneId.systemDefault());
```

For file and data exchange requiring stability, pass an explicit charset such as UTF-8. For absolute instants in time, prefer `Instant`; for local calendar times, manage `ZoneId` explicitly. Do not assume container timezones match developer machines.

## 14. Inventory databases, messaging, and integration services

Connections outside the JVM are part of the runtime. Java 17 can expose issues in drivers, TLS, authentication, or integration frameworks.

| System | Information to inventory |
| --- | --- |
| Database | Driver/version, database version, TLS, authentication, pool, dialect, JDBC URL properties |
| Message broker | Client version, protocol, TLS, authentication, serializer, and retry policy |
| Cache | Client version, topology, TLS, timeout, and serialization format |
| HTTP API | Client library/version, TLS, proxy, timeout, redirect, and certificates |
| LDAP/SSO | Provider, TLS, truststore, and authentication flow |
| File/object storage | SDK version, endpoint, native dependencies, and credential provider |

A driver may support Java 17 yet not support the current database server or TLS policy. Check both sides and run integration tests from a production-like staging environment.

## 15. Inventory deployment, startup, and shutdown

Trace the entire path from build to live process:

- Where CI artifacts are built.
- How artifacts are packaged into images.
- How image tags/digests are deployed.
- How the JVM command line is constructed by the entrypoint/orchestrator.
- When secrets/certificates are mounted.
- What conditions health checks verify.
- How the process handles SIGTERM and shuts down.
- Whether the grace period is sufficient to drain requests and flush data.
- Which image/JDK/artifact is used for rollback.

Check whether startup scripts invoke the JDK via an absolute path or rely on a specific installation directory. If switching base images, confirm that timezone data, CA certificates, native libraries, and required diagnostic tools are still present.

## 16. Build the inventory matrix and risk assessment

Every item needs evidence, an owner, and a status; do not just maintain a flat list of package or dependency names.

| Group | Component | Version/current state | Evidence | Risk | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Source | Internal JDK API | Specific package/class | jdeps output | High | Team A | Action needed |
| Dependency | ORM | Current version | Release notes + integration test | Medium/High | Team B | Unconfirmed |
| Plugin | Compiler plugin | Current version | Build on JDK 17 | Medium | Build team | Verified |
| Runtime | Java agent | Deployed version | Vendor support matrix | High | Platform | Upgrade needed |
| Environment | TLS endpoint | Protocol/certificate | Integration test | Medium | Infra | Investigating |

### 16.1. Risk classification

- **High:** can break builds, prevent JVM startup, weaken security, or break critical functionality.
- **Medium:** can cause failures in a specific profile, endpoint, or data type, or degrade performance.
- **Low:** has no immediate direct impact but needs updating or poses a risk when changing environments.

Base assessments on evidence. A dependency lacking Java 17 information is `Unknown`, not automatically `Compatible` just because no error has been observed yet.

### 16.2. Inventory statuses

| Status | Meaning |
| --- | --- |
| Not inventoried | Information has not been collected yet. |
| Inventoried | Version/configuration and evidence source recorded. |
| Needs assessment | Information exists but is insufficient to conclude compatibility. |
| Upgrade required | Confirmed that an upgrade or replacement is needed. |
| Verified on Java 17 | Appropriate tests executed on JDK 17 and evidence saved. |
| Accepted constraint | Known limitation with an owner and approved mitigation controls. |
| Removed | Component is no longer used and has been removed from build/deployment. |

Do not mark an item `Verified on Java 17` simply because the compiler reported no errors. Specify the test level: compile, unit, integration, startup, smoke, performance, or production canary.

## 17. Iterative inventory process

### Round 1 — static inventory

1. Identify repositories, modules, and source revisions.
2. Gather JDKs, Gradle/Maven wrappers, and build profiles.
3. Export dependency graphs.
4. List plugins, annotation processors, agents, and native libraries.
5. Run `jdeps` and `jdeprscan` on current artifacts.
6. Locate JVM flags, environment variables, and module options in deployment configs.

The output is a list of components and open questions to verify, not yet a compatibility conclusion.

### Round 2 — cross-reference support documentation

For each dependency/plugin:

1. Identify the exact version.
2. Look up the vendor's Java 17 support matrix/release notes.
3. Check relevant issue trackers or advisories.
4. Identify a replacement version if the current one is unsupported.
5. Record constraints and the responsible owner.

Do not use documentation for the latest version to assume an older version is also compatible. Evidence must match the exact artifact and version.

### Round 3 — verify on JDK 17

1. Install the chosen JDK 17 distribution/build.
2. Run the build via the wrapper.
3. Run unit and integration tests.
4. Start the application using the target runtime image.
5. Verify databases, messaging, HTTP/TLS, and file storage.
6. Verify startup/shutdown, logging, metrics, and agents.
7. Run smoke/performance tests against the baseline.

Record workarounds such as `--add-opens`, truststore changes, or JVM flags. Do not leave workarounds living only in one developer's local command line.

### Round 4 — finalize the migration plan

Group items that can be kept, need version upgrades, need replacement/removal, require source edits, require deployment changes, or remain unknown. Each item should have an owner, deadline, acceptance criteria, and appropriate rollback plan.

## 18. Reference inventory commands

### JDK and runtime

```bash
java -version
javac -version
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
```

`jcmd` requires appropriate attach permissions; some production environments disable attach or run inside isolated containers.

### Static API and dependency analysis

```bash
jdeprscan --release 17 application.jar
jdeprscan --release 17 --for-removal application.jar
jdeps --multi-release 17 --summary application.jar
jdeps --multi-release 17 --recursive --print-module-deps application.jar
jdeps --multi-release 17 --jdk-internals application.jar
jdeps --missing-deps application.jar
```

### Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew buildEnvironment
./gradlew dependencyInsight --dependency <name> --configuration runtimeClasspath
```

### Maven

```bash
./mvnw --version
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

### Artifacts and modules

```bash
jar --describe-module --file application.jar
jar tf application.jar
javap -verbose -classpath application.jar com.example.Main
```

`jar --describe-module` inspects module descriptors or automatic module metadata; `javap -verbose` displays bytecode metadata such as the major version. For Java 17, the class file version is 61. Fat JARs may contain multiple libraries; inspect individual dependencies when needed.

Not every command applies to every project. Record the command, JDK/tool version, input artifact, and output so results are reproducible.

## 19. Common mistakes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Only changing `JAVA_HOME` and building | Misses plugins, dependencies, and runtime flags. | Inventory source, dependencies, build, and runtime. |
| Checking only direct dependencies | Misses transitive dependencies and plugin classpaths. | Export graphs for compile/runtime/test/plugin scopes. |
| Running only `jdeps` | Misses reflection, SPI, JNI, and code generation. | Combine static scans, config searches, and runtime tests. |
| Treating all `javax.*` as obsolete | May mistakenly replace still-supported Java SE APIs. | Check the specific package and API provider. |
| Replacing all `javax` with `jakarta` | Breaks code using Java SE or frameworks that have not migrated namespaces. | Identify exact frameworks/APIs and plan separate migrations. |
| Keeping all legacy JVM flags | JVM may reject options or use meaningless configurations. | Collect the command line and test every flag on JDK 17. |
| Using `--illegal-access` to fix reflection | Does not restore package opening behavior on Java 17. | Upgrade dependencies or scope opens by module/package. |
| Testing compilation only | Misses runtime, TLS, serialization, and native library errors. | Run integration, startup, and smoke tests on runtime 17. |
| Ignoring Java agents | Agents can block startup or corrupt bytecode transformations. | Inventory `-javaagent` and native agents. |
| Testing only on a developer machine | CI/production may use different JDKs, OSes, and flags. | Test on the exact CI and runtime images. |
| Failing to save evidence | Unclear who verified an item and how. | Record version, command, output, owner, and status. |

## 20. Inventory completion criteria

The inventory can be considered complete enough for migration planning when:

- All modules/services in scope have a recorded source revision and owner.
- Current JDK, target JDK, and release target are clearly documented.
- Build tools, wrappers, plugins, and compiler/test toolchains are listed.
- Direct/transitive dependencies and runtime graphs have been exported.
- Dependencies/frameworks have documented Java 17 support or explicit `Unknown` status.
- JDK internal APIs, deprecated/removed APIs, and reflection risks have been reviewed.
- Java agents, native libraries, and external non-JVM tools are listed.
- Runtime flags and environment variables have been collected from actual deployments.
- OS, architecture, container images, CPU/memory limits, and TLS endpoints are recorded.
- Pre-upgrade test baselines and performance metrics are saved.
- Each risk has an owner, remediation plan, and acceptance criteria.
- No high-impact `Unknown` items remain without a verification plan.

After the inventory is complete, the team can establish the upgrade sequence: build tools, plugins/dependencies, source code, runtime, and testing. Do not turn an inventory list into an uncontrolled mass version bump.

## 21. Hands-on exercises

### Exercise 1 — create an application inventory

Pick a service. Record its source revision, current JDK, build tool, modules, artifacts, runtime command, and deployment environment. Identify which pieces of information currently lack evidence.

### Exercise 2 — analyze APIs

Build the application with the current JDK, then run `jdeprscan --release 17` and `jdeps --jdk-internals` on the artifact. Categorize the results into deprecated, removed/unsupported, and internal APIs. Document the limitations of each tool.

### Exercise 3 — export dependency graphs

For Gradle, run `dependencies` for runtime/test configurations; for Maven, run `dependency:tree`. Pick one transitive dependency and trace which library pulled it in.

### Exercise 4 — inspect plugins

List compiler, test, coverage, annotation processor, and packaging plugins. Look up Java 17 support documentation for the exact versions in use. Note which plugins must be upgraded before switching the build JVM.

### Exercise 5 — inventory runtime flags

Gather command lines from startup scripts, container manifests, and `jcmd VM.command_line`. Identify legacy flags, module access options, GC options, and Java agents. Verify every flag on JDK 17 in staging.

### Exercise 6 — inspect integration environments

Select critical databases, HTTP endpoints, and message brokers. Record driver/client versions, TLS protocols, certificate sources, and timeouts. Run integration tests from the target Java 17 runtime image.

### Exercise 7 — complete the risk register

For each issue, record impact, likelihood, evidence, owner, proposed action, and acceptance criteria. Do not mark anything compatible based solely on assumptions or without running tests.

## 22. Quick reference

| Area | What to inventory | Tools / evidence |
| --- | --- | --- |
| Source/API | Deprecated, removed, JDK internals, reflection, modules | `jdeprscan`, `jdeps`, source/config search |
| Dependencies | Direct/transitive, frameworks, drivers, agents | Gradle dependencies/dependencyInsight, Maven dependency:tree, vendor support matrix |
| Plugins/build | Wrapper, compiler, test, processors, generators, packaging | Gradle/Maven wrapper, effective POM, buildEnvironment, plugin release notes |
| Native/agent | JNI/JNA, `-javaagent`, native libraries | Startup config, image inspection, vendor compatibility |
| Runtime | JDK distribution, flags, heap/GC, properties | `java -version`, `jcmd`, runtime command line |
| Environment | OS, architecture, containers, CPU/memory | Image digest, deployment manifests, container runtime data |
| Integration | TLS, certificates, DB, messaging, HTTP | Integration tests, connection config, server/client support matrix |
| Evidence | Baselines, test results, risks, owners | Inventory register, CI logs, metrics, and acceptance criteria |

**Core principle:** Before upgrading to Java 17, know exactly what source code, dependency graph, plugins/build tools, and runtime environment you are using. Use `jdeps` and `jdeprscan` to spot bytecode-level signals, but still check reflection, SPIs, agents, native libraries, and deployment configs. Every item needs an exact version, compatibility evidence, owner, and clear status. Once the inventory is complete and the baseline is saved, the team can migrate step by step and verify results with tests and runtime metrics.
