# Compatibility and Version Migration in the Java Ecosystem

## 1. Why Is It Necessary to Understand Compatibility Before Upgrading?

A Java application rarely depends only on the JDK. It also depends on the bytecode of libraries, frameworks, build plugins, testing tools, application servers, the operating system, container images, and services communicating over the network. Therefore, changing the Java version can affect multiple layers at the same time. A project that compiles successfully on a new JDK may still fail to start in an older deployment environment; a library that preserves its API signatures may still change its behavior; a new framework may require both a new JDK and a different API namespace.

**Version compatibility** is the ability of components to continue working together correctly when one or more components change versions. **Version migration** is the process of moving a system from a working set of versions to a target set of versions while controlling changes to source code, bytecode, APIs, behavior, data, and the operational environment.

The goal of a migration is not merely to make the application run on a new JDK. The system must preserve its contracts with users and dependent systems, be reproducibly buildable in CI, be deployable to the target environment, and have ways to detect and handle errors when changes occur.

In this article, the “Java ecosystem” includes the JDK/JVM, the Java language, libraries, frameworks, build systems, development and testing tools, deployment platforms, as well as the protocols and data formats that the application uses.

After studying this article, the reader will be able to:

- Distinguish between compatibility types and identify which type matters for a specific change.
- Explain the relationship between JDK version, bytecode version, language level, and allowed Java APIs.
- Assess the impact of upgrading the JDK, frameworks, libraries, and build tools.
- Build a version matrix and a verifiable migration plan.
- Recognize common errors such as `UnsupportedClassVersionError`, the `javax` to `jakarta` transition, dependency conflicts, and errors caused by accessing internal APIs.

## 2. Compatibility Dimensions to Distinguish

There is no single “compatible” label that applies to all situations. A change can be compatible at the compilation level while being incompatible at the behavioral or operational level. Before upgrading, it is necessary to identify which component is the provider and which component is the consumer of the contract.

| Compatibility Type | Question to Answer | Examples of Changes That Can Break Compatibility |
| --- | --- | --- |
| Source compatibility | Does old source code still compile against the new API/compiler version? | Removing an overload, changing parameter types, changing packages, or adding an overload that makes a call ambiguous. |
| Binary compatibility | Does compiled bytecode still link and run with the new library/runtime? | Removing a method or field referenced by old bytecode; changing a descriptor or visibility/accessibility. |
| Behavioral compatibility | Does the program still produce the same results and side effects as before? | Changing default values, processing order, algorithms, timeouts, or error-handling behavior. |
| Data compatibility | Can stored data still be read, written, and interpreted correctly? | Changing schemas, field types, JSON property names, or serialization formats. |
| Protocol/API compatibility | Can independent systems continue communicating with each other? | Changing endpoints, headers, error codes, message schemas, or authentication rules. |
| Build/tooling compatibility | Can the project continue to be built, tested, and packaged with the new toolchain? | Plugins not supporting the new Gradle/Maven/JDK; annotation processors incompatible with the compiler. |
| Operational compatibility | Does the application work properly in the deployment environment? | Missing CA certificates in the image, changed TLS defaults, different memory limits, or different JVM configurations. |

### 2.1. Source Compatibility

Source compatibility refers to the ability to recompile existing source code. For example, version 2 of a library might still provide most of version 1's API but change a constructor from `public` to `protected`. Source code calling that constructor will no longer compile.

Source compatibility can also be affected by changes in the compiler or language. A previously valid variable name may become a keyword or have special contextual meaning in a new language version. Adding an overload can also make a previously unambiguous call ambiguous. Therefore, “only adding APIs” does not strictly mean “cannot cause compilation errors”.

### 2.2. Binary Compatibility

Binary compatibility concerns already-compiled bytecode. The JVM links classes and members based on name, descriptor, access modifiers, and type structure. If a compiled application calls `LibraryClient.send(String)`, but a new library removes that method or changes its descriptor, an error may only appear when the class is loaded or the method is called.

Some common errors are `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, `IllegalAccessError`, and `IncompatibleClassChangeError`. They usually indicate that the bytecode was compiled against a different contract than the one present on the runtime classpath. You should not treat these errors by adding dependencies randomly; instead, determine the exact class and version being loaded.

Binary compatibility does not guarantee behavioral compatibility. If a method still exists with the same signature but changes its algorithm, default values, or exception handling, old bytecode can still link, yet the application may behave differently.

### 2.3. Forward Compatibility and Backward Compatibility

These two terms are often confused because the perspective can vary. Always state clearly which side is the new version and which side is the old version:

- **Backward compatibility:** the new version continues to support contracts or data produced by the old version. For example, a new service can still read messages published using the old schema.
- **Forward compatibility:** an old component can safely ignore or handle data/features produced by a new component. For example, an old consumer ignores unrecognized JSON fields.

Not every protocol or format automatically has both properties. A strict parser may reject new fields; an old consumer may misinterpret a new enum value. When designing an API or schema, you need to clearly define rules for unknown fields, new enum values, required fields, and default values.

### 2.4. Data and Protocol Compatibility

For enterprise applications, data contracts often outlive a single deployment. JSON, XML, message queues, database tables, and exported files can be produced by multiple different versions of an application. An upgrade that only modifies a Java class but renames a JSON field is still an external contract change.

With Java Serialization, `serialVersionUID` and class structure affect the ability to read old streams. With JSON, you must consider field names, data types, nullability, enums, date/time formats, and rules for ignoring unknown fields. With databases, you must consider the possibility of old and new application versions running concurrently during a rollout.

A common strategy is **expand–migrate–contract**: first expand the schema so that both the old and new versions can operate together; then migrate the data and deploy the new application; finally, remove the old structure once no consumers use it anymore. This approach reduces risk when all components cannot be upgraded simultaneously.

## 3. JDK, Java Language Level, and Bytecode Are Not the Same Concept

When saying “the project uses Java 21,” at least three things need to be clarified:

1. Which JDK runs Gradle/Maven and the build tools?
2. Which language level and Java APIs does the compiler use to compile the source code?
3. What is the lowest JVM version supported to run the generated artifact?

In addition, each library in the dependency graph may have been compiled with a different Java version. An application targeting Java 17 still cannot run on Java 17 if it depends on a library that only ships Java 21 bytecode.

### 3.1. JVM and Class-File Version

`javac` translates Java source code into bytecode in `.class` files. Each class file contains a major version value indicating the bytecode format that the JVM must understand. Some common milestones:

| Java Version | Class-File Major Version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

For example, if a class is compiled to Java 21 bytecode and then run on a Java 17 JVM, the older JVM does not understand class-file version 65 and may throw `UnsupportedClassVersionError`. This differs from `NoSuchMethodError`: the first error usually indicates that the bytecode is newer than the runtime, whereas the second usually indicates a classpath contract mismatch.

You can inspect a class file with:

```bash
javap -verbose com.example.Main
```

In the output, look for `major version`. For a JAR, you can extract it or use `javap` with the appropriate classpath to inspect specific classes. Do not infer compatibility for the entire application solely from the main class: dependencies also contain their own class files.

### 3.2. `--source`, `--target`, and `--release`

The compiler options address different concerns:

- `--source` restricts the accepted Java syntax/language features.
- `--target` specifies the target bytecode format.
- `--release` combines the language level, bytecode version, and allowed Java SE API surface for that release.

When you need to produce an artifact compatible with an older Java release, `--release` is usually a clearer choice than setting only `source` and `target`. For example, building with JDK 21 using `--release 17` constrains Java SE API usage to Java 17, instead of accidentally compiling calls to APIs available only in JDK 21 while emitting older target bytecode.

However, `--release 17` does not turn every dependency into a Java 17-compatible library. Nor does it check all behavioral differences across the JVM, third-party libraries, reflection, system configuration, or external services. All dependencies and the runtime environment must be verified separately.

### 3.3. Using Toolchains to Pin the Build JDK

A project may be built on multiple machines. If each machine uses a different default JDK, results can vary or only some machines may succeed in building. Gradle Java Toolchains let you declare the JDK used for compile/test/run tasks instead of relying on each machine's `JAVA_HOME`.

Gradle Groovy DSL example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

This example uses a JDK 21 toolchain to perform the build while generating bytecode and restricting the Java SE API to level 17. You must ensure that other tasks, plugins, annotation processors, and the test runtime also align with that choice. If the actual target is to run on Java 21, set the release accordingly and test on a Java 21 JVM.

With the Maven Compiler Plugin, you can declare the release in `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Compiler configuration is only one part of the toolchain. Maven or Gradle itself also needs to run on a JDK supported by that build tool version. Distinguish between the **JVM running the build tool** and the **JDK toolchain used to compile and run tests**.

### 3.4. Preview Features and Incubator APIs

Some Java features are released as preview features or incubator APIs before becoming stable APIs. Preview features typically must be enabled explicitly at both compile time and runtime, and are tied to a specific release. Bytecode using preview features should not be treated as a broadly compatible artifact across multiple JDKs.

If an application uses preview/incubator APIs, document this as a separate migration constraint: identify the exact JDK version, compiler/runtime flags, usage scope, and replacement plan if the API changes or is removed.

## 4. Common Changes When Upgrading the JDK

Upgrading the JDK can expose pre-existing issues that were previously not strictly enforced. The following areas should be reviewed deliberately.

### 4.1. Deprecated, Removed, or Changed APIs

Deprecated APIs may still work in one release, yet be removed or changed in a later release. When migrating across multiple LTS releases, read the migration guides and release notes for the relevant intermediate versions rather than reading only the notes for the target version.

Useful tools include:

```bash
jdeprscan --release 21 application.jar
jdeps --jdk-internals application.jar
```

`jdeprscan` helps find certain references to deprecated APIs in an artifact. `jdeps --jdk-internals` helps detect dependencies on internal JDK APIs. These are static analyses; they cannot detect every reflective call, runtime configuration, or execution path that only occurs in production. Their results must be cross-checked against actual testing.

### 4.2. Internal API Access and the Module System

Since Java 9, the Java Platform Module System (JPMS) has introduced module boundaries and stronger encapsulation mechanisms. Applications or libraries that used deep access into internal JDK packages may start receiving warnings or access errors when running on newer JDKs.

Errors such as `InaccessibleObjectException` often occur when a library uses reflection to access members not opened to its module. The `--add-opens` flag can be useful as a controlled transitional measure, but it should be treated as a signal to update the dependency or replace the access pattern. Keeping numerous internal-open flags long-term increases coupling to JDK implementation details.

### 4.3. Java EE/CORBA Modules Formerly Bundled with the JDK

Several Java EE and CORBA modules previously included in older JDKs were removed from the standard JDK in newer releases. For example, an older application might rely on the JAXB API/implementation bundled with JDK 8, which is no longer present by default on JDK 11 and later.

When encountering `ClassNotFoundException` or `NoClassDefFoundError` after an upgrade, check whether the application relies on modules previously bundled in an older JDK. If the API is still needed, declare the appropriate dependency and select a version compatible with the target JDK/framework.

### 4.4. The `javax` and `jakarta` Namespaces

A major change in the Jakarta EE ecosystem is the move of many enterprise APIs from the `javax.*` namespace to `jakarta.*`. For example:

| API | Old Namespace | New Namespace |
| --- | --- | --- |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence | `javax.persistence.*` | `jakarta.persistence.*` |
| Validation | `javax.validation.*` | `jakarta.validation.*` |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |

This is a package change at both the source and binary levels. The classes `javax.persistence.Entity` and `jakarta.persistence.Entity` are two distinct types; libraries/frameworks expecting one namespace are not automatically compatible with the other.

Do not blindly replace every occurrence of `javax` with `jakarta`. Java SE still contains valid `javax` packages, such as APIs in `javax.crypto`, `javax.net`, and `javax.sql`. Only migrate APIs belonging to the ecosystem that changed namespaces and match the target framework version.

When upgrading a framework that undergoes the Jakarta transition, align dependencies, imports, annotations, configurations, code-generation plugins, test libraries, and the runtime container. Mixing libraries built on the two namespace generations in the same integration flow often leads to hard-to-trace type errors or class-loading failures.

### 4.5. JVM and Environment Default Changes

A new JDK may change defaults related to TLS, digital certificates, cryptographic algorithms, charsets, locales, the timezone database, garbage collectors, JIT, container awareness, or resource limits. Not every change breaks compatibility, but they can expose outdated assumptions in the application.

For example, HTTPS connections may fail because a server only supports cipher suites or protocols disabled in the new JDK. An application might consume more CPU or memory due to changes in container detection. You should inspect logs, metrics, handshakes, and JVM configuration in a production-like environment instead of relying solely on unit test results.

## 5. Compatibility Across Frameworks, Libraries, and Build Tools

The JDK is only one axis in the version matrix. A framework may require a minimum JDK, a specific Spring Framework line, a servlet container version, or a new API namespace. Build plugins and testing tools also maintain their own support matrices.

### 5.1. Building a Version Matrix

Before upgrading, document the affected components along with their current and target versions. For example:

| Component | Current Version | Target Version | What to Verify |
| --- | --- | --- | --- |
| Build JDK | JDK 17 | JDK 21 | Can Gradle/Maven and plugins run on JDK 21? |
| Java release | 17 | 21 or 17 | What is the lowest JVM version the artifact must support? |
| Gradle/Maven | Currently used version | Version supporting target JDK | Are the wrapper, daemon, plugins, and lifecycle compatible? |
| Spring Boot | Current line | Target line | What are the minimum JDK, Spring Framework, Jakarta, and container requirements? |
| ORM/JPA | Current version | Framework-compatible version | Have the namespace, dialect, queries, or schema changed? |
| Jackson/JSON | Current version | Target version | Have serialization, naming, date/time, or polymorphism changed? |
| Test stack | Current JUnit/Mockito/... | Target version | Are the engine, extensions, mock agent, and test runtime compatible? |
| Deployment image | Current base image | Image with target JRE/JDK | Are CAs, timezone, user, native libraries, and CPU architecture suitable? |

The table above is an analysis template, not a pre-validated set of compatible versions. Specific versions must be verified against the official documentation of each component at the time of migration.

### 5.2. Dependency Graph and Dependency Mediation

A directly declared dependency can pull in many transitive dependencies. Two libraries may require different versions of the same artifact; Maven or Gradle will apply resolution rules to pick one version. The build may still succeed even when the selected version does not match what one of the libraries expects.

Inspect the dependency graph before and after migration. With Gradle:

```bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Pay attention to transitively pulled dependencies, overridden versions, duplicate artifacts, test/runtime-only dependencies, and libraries that have dropped support for the target JDK. When using Spring Boot or a similar platform, a BOM/dependency management helps keep a set of versions that have been tested together. Avoid upgrading individual core libraries out of the managed set unless you have verified the compatibility matrix.

### 5.3. Framework Major Versions and Migration Contracts

Major versions often contain changes that can break APIs or behavior, though not all projects follow SemVer identically. Release notes and migration guides are the authoritative source for determining actual changes.

For a framework, look for at least the following:

- The minimum JDK and base framework versions required by the release.
- Packages or annotations that have changed, been removed, or changed defaults.
- Whether old configurations remain supported or must be migrated to new ones.
- Changes to bean lifecycle, transactions, validation, security, serialization, or exception handling.
- Changes to extension APIs used by the application or internal libraries.
- Servlet container, driver, database, and plugin versions that need to be aligned.

Do not just fix compilation errors until the build turns green. A security or transaction configuration might still compile while having different effects at runtime.

### 5.4. Build Tools and Plugins

Gradle/Maven have their own runtime versions and extension plugins. Upgrading the JDK before upgrading the build tool can prevent the wrapper or plugins from starting. Conversely, upgrading the build tool without checking plugins can alter existing tasks, configurations, or conventions.

With Gradle, check Gradle's Java compatibility matrix, the wrapper version in `gradle-wrapper.properties`, plugins in `plugins {}`, and internal plugins. With Maven, check the Maven runtime, Maven Wrapper, Maven Compiler/Surefire/Failsafe Plugins, annotation processors, and Maven extensions.

Components that are easily overlooked include Lombok, MapStruct, QueryDSL, the Kotlin compiler plugin, Error Prone, JaCoCo, SpotBugs, formatters, code generators, test engines, and native packaging tools. They may interact directly with the compiler API or bytecode format and therefore require versions that support the new JDK.

## 6. A Controlled Migration Process

A good migration starts by defining the contracts and impact scope, then makes changes in observable steps. Avoid upgrading too many axes simultaneously if the team would not be able to attribute failures to the exact change.

### Step 1: Define Goals and Constraints

State the reason for upgrading clearly: end-of-support for an older JDK, security requirements, a new framework, performance, language features, or environment standardization. Identify:

- The JDK version running the build and the JDK version running production.
- The lowest Java version the artifact must support.
- Frameworks and dependencies that must be kept or must be upgraded.
- Deployment platform, operating system, container, and CPU architecture.
- External consumers, data formats, and protocols that must remain compatible.
- Support timelines, deployment windows, and rollback plans.

If the consumer's lowest JVM version has not been determined, you cannot yet conclude that the artifact's bytecode can switch to a newer release.

### Step 2: Establish a Reproducible Baseline

Before making changes, record the current build/test state, dependency graph, runtime configuration, startup logs, and key operational metrics. Note any pre-existing failing tests so old failures are not misattributed to the migration.

Ensure the build can be reproduced from the wrapper and controlled repository configuration. If the build depends on an arbitrary JDK installed on a developer's machine, standardize the toolchain/CI first or explicitly document this limitation.

### Step 3: Verify the Toolchain Upgrade Path

Verify that the Gradle/Maven version and plugins can run on the target JDK. If not, upgrade the wrapper/build tool and plugins through supported compatibility steps. After each change, run a minimal build to separate build system errors from source code errors.

Check the daemon JVM, compiler toolchain, test JVM, code-generator tasks, and the CI JVM. One task can inadvertently use a different default JDK than the compile task.

### Step 4: Upgrade Dependencies in Compatible Sets

Read the release notes/migration guide of the primary framework, then identify the appropriate BOM or dependency platform. Upgrade tightly coupled libraries together, such as the framework, persistence provider, servlet API, validation provider, and test integration.

After updating, inspect the dependency graph for overridden or conflicting versions. Do not use exclusions or forced versions as a quick way to make the build green without understanding which library needs that artifact and why.

### Step 5: Modify Source Code and Configuration Deliberately

Address compiler errors, deprecated APIs, package namespaces, removed configurations, and contract changes. Each change should be tied to a reason from release notes, compiler diagnostics, or tests. When modifying JSON/schemas/databases, evaluate consumers and the ability for old and new versions to run concurrently.

Avoid bulk find-and-replace by package or method name without first distinguishing whether an API belongs to Java SE, Jakarta EE, or a specific library. Run the proper versions of formatters and generators after updating the toolchain.

### Step 6: Multi-Layer Verification

A migration requires multiple forms of evidence:

1. **Build:** a clean build using the wrapper and the intended JDK, without relying on stale outputs.
2. **Static analysis:** check deprecated APIs, internal JDK APIs, the dependency graph, and unsupported configurations.
3. **Unit tests:** verify local logic and edge cases.
4. **Integration tests:** verify databases, message brokers, HTTP clients/servers, serialization, security, and framework wiring.
5. **Contract tests:** verify the APIs/schemas consumed by other services.
6. **Runtime tests:** run the artifact on the exact target JVM and deployment image.
7. **Performance/operational tests:** compare startup time, throughput, latency, memory, GC, threads, and connection errors against the baseline.

A green build only proves that the build steps completed. It does not by itself prove data, protocol, or behavioral compatibility in production.

### Step 7: Deploy with Observability and Rollback

If supported by the system, use a canary deployment or roll out by instance groups. Monitor startup failures, exceptions, warning logs, error rates, latency, JVM resources, database connections, and message backlogs. For schema changes, ensure that rolling back the application still allows reading data written by the new version.

Rollback must be designed in advance: keep old artifacts, know whether the old image/JDK remains available, and determine which data migrations are reversible. Not every schema change can be rolled back safely; sometimes a roll-forward fix is required.

### Step 8: Finalize and Standardize

Once stable, update build documentation, JDK requirements, base images, CI, developer guides, dependency policies, and release procedures. Gradually remove temporary compatibility flags such as `--add-opens` once they are no longer needed. Document any remaining constraints so the next upgrade does not have to rediscover them from scratch.

## 7. Upgrade Strategy: Single Step or Incremental?

There are two common approaches:

- **Big-bang upgrade:** migrate multiple components in a single release. This approach can suit small applications with few consumers and solid automated tests. The risk is that when an error occurs, many changes arrive together, making root-cause attribution harder.
- **Incremental upgrade:** standardize build tools, upgrade the JDK, upgrade frameworks, and then change schemas or APIs in stages. This approach creates multiple checkpoints and makes isolating errors easier, though intermediate compatibility states may have to be maintained longer.

You can use the following matrix to choose an approach:

| Condition | Usually Suitable Approach |
| --- | --- |
| Small application, few dependencies, no independent consumers | Can perform a direct (big-bang) upgrade if reliable tests and rollback exist. |
| Framework major version with namespace/API migration | Split into stages to separate toolchain changes from framework changes. |
| Multiple services exchanging messages or sharing a database | Design data/protocol compatibility first, then deploy in producer-consumer order. |
| Internal library used by multiple applications | Check binary/source compatibility and release the library on its own schedule. |
| Production environment cannot stop all at once | Use a multi-step rollout and compatibility contracts between old and new versions. |

There is no single fixed upgrade order for all projects. A useful principle is to upgrade foundational components that subsequent steps depend on first, provided the new version of that component still supports the remaining components during the transition period.

## 8. Example Analysis of a Java 17 to Java 21 Migration

Suppose a service is running Java 17, built with Gradle, using Spring Boot, Hibernate, Jackson, and JUnit. The goal is to run production on Java 21.

Before making changes, the team needs to answer:

- Does the current Gradle wrapper version support running on JDK 21?
- Does the currently used Spring Boot version support Java 21 and the corresponding base dependencies?
- Are Hibernate/Jakarta, the database driver, Jackson, and the test stack compatible with the target framework?
- Are any dependencies compiled with a Java version higher than 21 or accessing internal JDK APIs?
- Does the production image have JRE 21 along with the appropriate certificates, timezone, and native libraries?
- Are there any consumers that still need to run the artifact or read data produced by the older version?

A feasible plan might include:

1. Run the baseline build/tests on Java 17 and save the dependency graph.
2. Check the Gradle wrapper/plugins; upgrade them to versions that support JDK 21 if needed.
3. Run the build with JDK 21 while temporarily keeping Java release 17 if the product still must release artifacts running on Java 17.
4. Upgrade frameworks/dependencies according to a compatible BOM and work through the migration guide.
5. Run tests on both the lowest supported JVM and JVM 21 during the transition period.
6. Once consumers are ready, switch the release target to 21 if the product decides to drop Java 17 support.
7. Update CI, container images, the production runtime, and operational documentation.

Key point to note: “building with JDK 21” and “requiring users to run Java 21” are two different decisions. If Java 17 must still be supported, maintain `--release 17` and verify that dependencies also run on Java 17. If switching the artifact to Java 21 bytecode, every runtime environment must have a compatible JVM.

## 9. Diagnosing Common Compatibility Errors

| Symptom | Possible Cause | Investigation Steps |
| --- | --- | --- |
| `UnsupportedClassVersionError` | The running JVM is older than a class's class-file version | Identify the failing class, check its major version, and inspect the actual JVM used by the process. |
| `NoSuchMethodError` | Runtime loads a library version missing a method required by the bytecode | Check the dependency tree, classpath, and where the class is loaded from. |
| `NoClassDefFoundError` / `ClassNotFoundException` | Missing class at runtime, excluded dependency, or API no longer bundled with the JDK | Check runtime scope, packaging, and modules/dependencies detached from the JDK. |
| `InaccessibleObjectException` | Reflection accesses an encapsulated member or package | Identify the library performing reflection; upgrade/replace it or temporarily open the package in a controlled manner. |
| `ClassCastException` between two types with the same name | Two classloaders or two different namespaces/versions | Check classloaders, duplicate dependencies, and `javax`/`jakarta`. |
| `NoSuchFieldError` or `AbstractMethodError` | Binary contract mismatch between modules | Check API/implementation versions and classpath ordering. |
| Build succeeds but tests/runtime fail | Compile classpath and runtime classpath differ; configuration or behavior changed | Run tests with the exact toolchain, inspect runtime dependencies, and check environment configuration. |
| TLS/HTTPS handshake failure | Differences in protocols, ciphers, certificates, or truststores | Inspect the handshake, certificate chain, truststore, and JDK policies. |
| Unreadable JSON or messages | Incompatible schema or serialization changes | Compare actual payloads, schemas, and producer/consumer versions. |

During investigation, record the actual JVM running the process, not just the JDK installed on the machine. You can use `java -version`, inspect service/container configuration, and check startup logs. For the classpath, identify the exact JAR loaded; seeing multiple versions in a cache directory does not prove which version is being used.

## 10. Common Mistakes to Avoid

**Only changing `JAVA_HOME` and concluding the migration is done.** The build JDK, compiler toolchain, test runtime, and production runtime can all differ. Each one must be verified.

**Only setting `source`/`target` without controlling the API.** This can emit older bytecode while still referencing newer APIs. Use `--release` when appropriate and verify dependencies.

**Upgrading every dependency to the latest version.** “Latest” does not mean “compatible with one another.” Rely on support matrices, BOMs, and release notes.

**Forcing a dependency version to silence an error.** Forcing or excluding can mask conflicts and cause another module to fail at runtime. Understand which dependency requires which version.

**Replacing all `javax` with `jakarta`.** The two namespaces have different scopes; Java SE still retains many `javax` packages. Only migrate APIs belonging to the Jakarta transition.

**Using `--add-opens` as a long-term solution.** This flag can help during transition, but it preserves dependencies on internal structures and can become a burden on the next upgrade.

**Running only unit tests.** Unit tests do not adequately cover databases, message brokers, HTTP contracts, TLS, containers, serialization, and operational behavior.

**Not testing rollback.** An upgrade can alter data in ways the older version cannot read. Test side-by-side compatibility and verify the recovery plan.

## 11. Design Principles to Make Future Migrations Easier

Upgradeability is not decided solely at migration time. Architecture and day-to-day development habits can lower the cost of future transitions:

- Declare JDK, build tool, and plugin versions explicitly via wrappers and toolchains; avoid relying on local machine configurations.
- Manage library versions centrally using a BOM or version catalog; avoid duplicate declarations and unjustified overrides.
- Avoid depending on internal JDK APIs, deep reflection, and undocumented behavior.
- Package versioned API/schema contracts; perform consumer-provider testing and preserve the ability to read old data for as long as needed.
- Use integration tests for critical boundaries: databases, HTTP, messaging, serialization, security, and framework wiring.
- Monitor warnings/deprecations and update dependencies periodically instead of letting multiple releases accumulate into one massive migration.
- Separate source code changes from data/protocol changes when possible; each step should have a verification method and a recovery plan.
- Document version constraints of internal modules so consumers know the minimum JDK, framework, and dependencies.

## 12. Technical References

When performing an actual migration, consult documentation matching the exact versions being deployed, as support matrices and guidance can change:

- **Java SE Migration Guide:** guidance on changes between JDK releases, removed APIs, and items to check: <https://docs.oracle.com/en/java/javase/21/migrate/>.
- **OpenJDK JEP Index:** descriptions of goals and changes for Java platform features and enhancements: <https://openjdk.org/jeps/>
- **Gradle Java Compatibility:** matrix of Gradle versions and the JDKs supported for running Gradle and using toolchains: <https://docs.gradle.org/current/userguide/compatibility.html>
- **Maven Compiler Plugin:** compiler, release, and toolchain configuration: <https://maven.apache.org/plugins/maven-compiler-plugin/>
- **Spring Boot System Requirements:** Java and build tool version requirements for each Spring Boot release: <https://docs.spring.io/spring-boot/system-requirements.html>

Reference documentation should be selected for the specific version in use. A `current` page may describe a newer release than the one your project uses; open the documentation matching the exact major/minor version before making decisions.

## Conclusion

Version compatibility is a property of the entire cooperating system, not solely of Java source code or the JDK. A safe migration must clearly identify source, bytecode, behavioral, data, protocol, build, and operational contracts; then upgrade according to a verified version matrix and validate with the artifact running in an actual environment.

When evaluating an upgrade proposal, always ask three questions: **which components are changing, which contracts could be affected, and what evidence proves that consumers still work correctly?** Answering these three questions turns an upgrade from a version-bumping task into a controllable engineering process.
