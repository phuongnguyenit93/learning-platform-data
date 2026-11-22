# Distinguishing Runtime Upgrade, Recompilation, and Source Modernization

In a Java project, the phrase "upgrading Java" often refers to several different tasks: changing the JVM version running the application, recompiling the application with a new JDK, or modifying source code to use more modern APIs and idioms. These three tasks are related, but they are not synonymous. If they are combined into a single change, it will be difficult for the development team to identify the cause when errors occur and to know the exact scope of testing to perform.

This lesson distinguishes these three types of changes in the context of **Java Advance Compatibility Migration**, under the **Migration Overview** chapter. The goal is to help identify which layer of the system a migration plan is changing, which level of compatibility must be preserved, and what evidence must be collected before deployment.

## 1. Looking at the Layers of a Java Application

A Java application goes through a sequence of steps from source code to the runtime environment:

~~~text
Java source code
    |
    | JDK compiler + build tool + dependency
    v
Bytecode (.class) and application package (JAR/WAR)
    |
    | JVM + platform libraries + configuration + operating system
    v
Running application
~~~

Each layer can be changed independently to a certain degree:

- **Source code** consists of .java files, package structure, API calls, and business logic.
- **Compilation environment** includes the JDK used to run the compiler, compiler options, annotation processors, Gradle or Maven, and build plugins.
- **Bytecode** is the compilation output in .class files; JAR/WAR packages bytecode together with resources and may contain dependent libraries.
- **Runtime environment** includes the JVM, Java libraries bundled with the runtime, JVM parameters, operating system, certificates, locale, timezone, and deployment configurations.
- **Dependencies** may have their own JDK or runtime requirements, even when the application source code does not directly use new features.

Therefore, it is necessary to distinguish at least three versions that are often collectively called the "Java version":

1. **JDK used to run the build tool**: the Java version running Gradle or Maven.
2. **JDK used for compilation**: the compiler version actually selected for the compile task.
3. **Target version of bytecode and API**: the Java version that the product is compiled to support.

In addition, there is the **JVM used to run the application in production**. This version may be the same as or different from the JDK used to build. A build machine running JDK 21 can certainly produce bytecode targeting Java 17, and the application is then run on Java 17 if the source code, APIs, and all dependencies satisfy that constraint.

This is the foundation for distinguishing the three activities below.

## 2. The Three Activities and Precise Definitions

### 2.1. Runtime Upgrade

A runtime upgrade is changing the application's execution environment to a newer JVM or Java runtime version. The immediate goal is to run the **existing artifact** on the new environment.

Example:

- The application has already been packaged as **orders-service.jar** with Java 17 bytecode.
- The operations team changes the container image from a Java 17 distribution to Java 21.
- The deployment team runs that exact same JAR on JVM 21 without recompiling the source code.

In this case, the primary change is in the runtime environment. The source code and artifact can remain unchanged.

A runtime upgrade can bring:

- JVM security patches and bug fixes.
- Improved Garbage Collector, JIT compiler, and runtime performance.
- Support for new TLS, cipher suites, encryption algorithms, and certificates.
- Better support for new operating systems, CPU architectures, or deployment platforms.
- Operational and monitoring capabilities better aligned with current infrastructure.

However, the fact that a new JVM can read older bytecode **does not mean the application will definitely run correctly**. The new runtime may change default behaviors, remove old JVM options, tighten internal access, update platform libraries, or change how certain edge cases are handled.

Some areas to check when upgrading the runtime:

| Area of change | Potential risks |
|---|---|
| Platform APIs | APIs have been removed or are no longer supported |
| Reflection and modules | Deep access to internal packages is blocked or requires explicit configuration |
| JVM options | Old JVM flags are removed, renamed, or change meaning |
| TLS and security | Old ciphers, protocols, or algorithms are no longer enabled by default |
| Charset, locale, timezone | Data read/write or formatting results may differ |
| Garbage Collector and JIT | Latency, memory usage, or throughput changes |
| JNI and native libraries | Native libraries are incompatible with the new architecture or runtime |
| Third-party libraries | Dependencies may not support the target JVM |

A notable example is the default charset change. Starting in Java 18, UTF-8 became the default charset in many environments under JEP 400. An application that previously relied on the machine's default charset to read files may produce different results after a runtime upgrade. If a data format requires a specific charset, the application should specify that charset explicitly instead of relying on the machine default.

**Conclusion on runtime upgrade:** the artifact does not necessarily have to be rebuilt, but application behavior can still change because the JVM and platform libraries have changed. Therefore, testing on the target runtime is mandatory.

### 2.2. Recompilation

Recompilation is running the compiler on source code to produce new bytecode and a new artifact. This activity can be performed without changing source code logic or structure.

Example:

- The source code is still written for Java 17.
- The build team switches to using JDK 21 to run the compiler.
- The compiler produces a new artifact targeting Java 17.
- The new artifact continues to be deployed on JVM 17.

In this example, **the compiler JDK changed, but the production runtime and target bytecode version may remain unchanged**.

Recompilation is commonly performed to:

- Switch the build toolchain to an organization-supported JDK.
- Produce a new artifact from source code stored in the repository.
- Update the compiler, annotation processors, or build plugins.
- Verify whether the source code still compiles with the new compiler.
- Generate bytecode for a specific target Java version.
- Rebuild artifacts to support a repeatable release process.

The key point is to distinguish the **JDK running the compiler** from the **target release**. For example, JDK 21 can compile source code for Java 17 using the **--release 17** option. In that case, the compiler restricts syntax and APIs to release 17 while generating class files compatible with Java 17.

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

If the release option is omitted and the JDK 21 compiler is used with default settings, the output typically targets Java 21. That artifact may not run on JVM 17.

In JDK 9 and later, **--release** should be preferred over simply combining **-source** and **-target**. The two options -source and -target control the syntax level and class file version, but if the configuration does not properly restrict platform APIs, the source code can still accidentally call APIs that only exist in a newer JDK. --release simultaneously enforces the language, bytecode, and platform API constraints of the selected release.

Recompilation can also uncover or introduce issues:

- Old source code no longer compiles due to compiler or API changes.
- Annotation processors generate different code or are incompatible with the new JDK.
- Build plugins do not yet support the JDK being used to run Gradle/Maven.
- Dependencies are upgraded indirectly or resolved differently due to build configuration changes.
- New warnings appear, such as deprecated APIs or unsafe operations.
- The new artifact may differ from the old artifact even though the source code is unchanged, because the compiler, dependencies, or packaging process has changed.

Therefore, "just recompiling" is still a change that can impact the product. Dependencies, toolchains, compiler options, and packaging processes should be pinned so that differences between two artifacts can be explained.

### 2.3. Source Modernization

Source modernization is proactively modifying source code to improve coding style, APIs, structure, maintainability, safety, or efficiency. This is a change at the source code layer and usually requires recompilation to produce a new artifact.

Modernization may include:

- Replacing outdated APIs with recommended APIs.
- Using **java.time** instead of legacy date and time APIs when appropriate.
- Using try-with-resources to manage resources.
- Using generics, lambdas, the Stream API, or language constructs appropriate for the target Java version.
- Using records for pure data types when record semantics fit.
- Using switch expressions or pattern matching when they help express logic more clearly.
- Improving exception handling, null handling, concurrency, and resource management.
- Removing dependencies on JDK internal APIs.
- Separating responsibilities, reducing coupling, and clarifying module boundaries.

For example, a legacy code snippet that closes resources manually:

~~~java
BufferedReader reader = null;
try {
    reader = new BufferedReader(new FileReader(path));
    return reader.readLine();
} finally {
    if (reader != null) {
        reader.close();
    }
}
~~~

Can be modernized to:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
~~~

This change both uses try-with-resources and specifies the charset explicitly. However, the charset of the actual data must be verified before making the change; data decoding should not be altered merely to use a new API.

Another example is a simple immutable data model. If the target Java version supports records and the type only needs to carry data, you can use:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
~~~

Records reduce boilerplate code for constructors, accessors, equals, hashCode, and toString. However, records are not the right choice for every class: if a type needs to inherit from another class, has mutable state, or requires complex lifecycle control, a regular class may be more appropriate.

Source modernization does not mean replacing all old syntax with new syntax. A change is only valuable when it improves the correctness, safety, readability, performance, or evolvability of the system. Each change must also take into account the target Java version and compatibility with current consumers.

Note that some changes commonly referred to as "modernize Java" are actually framework or ecosystem migrations. For example, moving packages from javax.* to jakarta.* can alter the application's API and binary compatibility. This is not merely a Java syntax change; framework versions, dependencies, and contracts of the related components must be evaluated.

**Conclusion on source modernization:** the source code changes intentionally, which usually entails recompilation and behavioral testing. Whether a runtime upgrade is needed depends on the new APIs and features used.

## 3. Comparing the Three Activities by Scope of Change

| Criterion | Runtime upgrade | Recompilation | Source modernization |
|---|---|---|---|
| Primary layer changed | Execution environment | Compiler and artifact | Source code |
| Are .java files modified? | Not required | Not required | Yes |
| Is a new artifact produced? | Not required | Yes | Yes, after compilation |
| Does the production JVM change? | Yes | Not required | Not required |
| Does the bytecode version change? | No | May change or stay the same | Depends on the target release |
| Can new APIs be used? | Only APIs present in the runtime and the artifact's current dependencies | Yes, if usable in source code and supported by the target release | Yes, if supported by the runtime, compiler, and target release |
| Primary risk | Runtime behavioral differences | Compiler, dependency, and artifact differences | Logic, API, contract, and behavioral bugs |
| Key evidence to focus on | Testing on the new JVM | Reproducible builds, bytecode inspection, and tests | Change review, business tests, and compatibility tests |

The three activities are not mutually exclusive. A Java migration plan may perform all three, but each activity should be identified separately to know which change caused an issue.

## 4. Understanding Source Compatibility, Binary Compatibility, and Runtime Compatibility Correctly

The word "compatibility" does not have just one meaning. When evaluating a migration, it is necessary to specify which type of compatibility is required.

### 4.1. Source Compatibility

Source compatibility answers the question: **can the existing source code be compiled by the target compiler without modifications or with modifications only within an acceptable scope?**

For example, a project written in Java 17 can continue to compile with JDK 21 if the source code, annotation processors, compiler options, and dependencies support that configuration.

Source compatibility does not guarantee that the artifact can run on the target runtime. Source code can compile successfully yet call APIs that do not exist in an older runtime if API constraints are not configured properly.

### 4.2. Binary Compatibility

Binary compatibility concerns whether already-compiled classes can link with and use other classes or libraries without encountering linkage errors.

A library might keep the same class name but change a method signature, remove a constructor, or change a return type. A previously compiled application may encounter errors such as NoSuchMethodError or NoClassDefFoundError when running with the new library.

Binary compatibility is especially important when upgrading dependency versions, changing the public API of a shared library, or changing how modules are packaged.

### 4.3. Runtime and Behavioral Compatibility

Runtime compatibility answers the question: **can the artifact start up and execute on the target environment?**

Behavioral compatibility goes further: **does the application continue to produce the expected results and business effects?**

An application can start up successfully yet still behave incorrectly because:

- Date/time or decimal number parsing behavior changes.
- The default charset differs.
- TLS no longer accepts the old configuration.
- Processing order or timing in a concurrent application changes.
- The Garbage Collector alters latency characteristics.
- Libraries change default values or edge-case data handling.

Therefore, checking that "the application can start" proves only a small part of compatibility.

### 4.4. Platform and Operational Compatibility

Platform compatibility considers Java APIs, the module system, operating system, CPU architecture, native libraries, container images, and services external to the application.

Operational compatibility considers operability: health checks, logging, metrics, tracing, memory limits, startup time, shutdown, JVM configuration, and rollback procedures.

A migration can be valid at the source and binary levels yet still fail in production if the container lacks certificates, a native library does not match the architecture, or memory settings are unsuitable for the new JVM.

## 5. Relationship Between JDK Version, Bytecode, and Runtime

### 5.1. Newer JDKs Usually Run Older Bytecode, but Do Not Guarantee Full Application Compatibility

JVMs generally support older class file versions. Therefore, a JAR compiled for Java 17 can usually be run on Java 21. However, the application also depends on platform APIs, dependencies, reflection, native code, and runtime behavior.

The reverse direction has a stricter limit: an older JVM cannot execute class files with a version newer than what it supports. This situation typically causes UnsupportedClassVersionError.

Some common class file versions:

| Java version | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

For example, if a class is compiled with major version 65, the runtime must support Java 21 class files. Running that class on Java 17 can cause UnsupportedClassVersionError.

### 5.2. Inspecting the Bytecode Version

You can use javap to view class file information:

~~~bash
javap -verbose -classpath app.jar com.example.Main
~~~

Look for the major version line in the output. Note that with a multi-release JAR, a single JAR can contain multiple class variants for different runtimes; you need to check the exact class entry selected by the JVM.

Commands to check the Java version currently used by the shell:

~~~bash
java -version
javac -version
~~~

The two commands can point to two different installations if PATH, JAVA_HOME, or toolchain configuration is inconsistent. The output of javac -version also does not prove that Gradle or Maven is using that exact compiler.

### 5.3. Using --release to Specify the Compilation Target

For example, if you want to build with JDK 21 while still supporting Java 17:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

With the Maven Compiler Plugin, you can declare the release in properties:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

With Gradle, you can separate the toolchain and the target release:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

In the Gradle example:

- Toolchain selects JDK 21 to run the compiler.
- options.release = 17 restricts APIs and bytecode to Java 17.
- The JVM running the application must still be specified separately in the test and production environments.
- The Gradle daemon can also run on a different JDK, as long as the Gradle version supports that environment.

You should not read a single "Java version" value in the configuration and conclude that the entire pipeline is using the same version.

## 6. Common Migration Combinations

### Case A — Runtime Upgrade Only

~~~text
Source:       unchanged
Build:        unchanged
Artifact:     unchanged
Runtime:      Java 17 -> Java 21
~~~

The goal is to validate the existing artifact on the new JVM. This is a way to isolate the impact of a runtime upgrade. If the application fails, investigation can focus on changed APIs, JVM options, dependencies, TLS, reflection, charset, or the deployment environment.

### Case B — Recompilation Only, Keeping the Target Release

~~~text
Source:         unchanged
Compiler:       JDK 17 -> JDK 21
Target release: Java 17 -> Java 17
Artifact:       rebuilt
Runtime:        still Java 17
~~~

The goal is to switch the toolchain or rebuild the artifact while retaining the ability to run on Java 17. You need to check the build tool, annotation processors, dependencies, and artifact reproducibility.

### Case C — Recompilation with a New Release and Runtime Upgrade

~~~text
Source:         can remain unchanged
Compiler:       JDK 21
Target release: Java 21
Artifact:       rebuilt with Java 21 bytecode
Runtime:        Java 17 -> Java 21
~~~

The goal is to move both the build platform and runtime to Java 21. If dependencies or source code do not support Java 21, additional changes may be needed. This migration has a broader scope than the previous two cases.

### Case D — Source Modernization, Keeping the Old Release

~~~text
Source:         modified
Compiler:       may change
Target release: unchanged
Runtime:        unchanged
~~~

The goal is to improve source code quality while preserving the old compatibility baseline. This approach works when APIs and syntax available in the current release can be used. Not every new feature can be used if the target release does not support it.

### Case E — Source Modernization and Platform Migration

~~~text
Source:         modified
Compiler:       new JDK
Target release: increased
Artifact:       rebuilt
Runtime:        upgraded to a supported version
~~~

This is a comprehensive migration. It may include replacing legacy APIs, updating dependencies, migrating frameworks, adjusting configurations, and leveraging new Java features. Because multiple layers change together, it needs to be broken down into steps that can be verified and rolled back.

## 7. Choosing a Strategy Based on Goals

Not every project needs to modernize its source code when upgrading the runtime. Nor does every project that needs a runtime upgrade have to change the target bytecode release.

| Goal | Typically suitable approach |
|---|---|
| Need security patches or a supported runtime | Evaluate a runtime upgrade; keep the artifact if compatible |
| Want to standardize the CI/build JDK | Switch the toolchain and recompile; keep the target release if older runtimes must be supported |
| Want to run on a new runtime without using new features yet | Upgrade the runtime first, keeping source and bytecode unchanged if possible |
| Want to support an older runtime while building with a new JDK | Use the new toolchain with the appropriate --release |
| Want to remove outdated APIs or improve maintainability | Modernize source code in groups of changes |
| Want to use APIs or features available only in newer Java | Upgrade the target release, runtime, and dependencies accordingly |
| Framework or library has dropped support for the old platform | Plan a dependency/framework migration together with contract testing |

A cautious strategy typically separates the migration into phases:

1. Record the current state: build JDK, compiler, target release, production JVM, Gradle/Maven, dependencies, and deployment configuration.
2. Test running the existing artifact on the target runtime if the immediate goal is a runtime upgrade.
3. Switch the build toolchain and recompile with a clearly defined target release.
4. Upgrade dependencies or frameworks according to compatibility requirements.
5. Modernize source code in small groups, with each group having specific goals and tests.
6. Upgrade the target bytecode release when the system is ready.
7. Deploy environment by environment, observe metrics, and preserve rollback capability.

This exact order does not have to be followed in every project. What matters is that each phase has clear inputs, changes, and output evidence.

## 8. Process for Analyzing a "Java Upgrade" Request

When receiving a Java upgrade request, clarify the following questions before making changes to the system.

### Step 1 — Identify What Needs to Change

Clarify which case the request falls into:

- Replacing the JVM/runtime running the application?
- Switching the JDK used to build?
- Changing the bytecode version supported by the product?
- Modifying source code to use new APIs or features?
- Upgrading frameworks and dependencies because old versions are no longer supported?

A request like "upgrade from Java 17 to Java 21" is not specific enough. It could refer only to the production JVM, the compiler JDK, the target release, or all three.

### Step 2 — Map the Current Versions

Record at least:

| Component | Question to answer |
|---|---|
| Build tool JDK | Which JDK is Gradle/Maven running on? |
| Compiler toolchain | Which JDK does the compile task use for the compiler? |
| Source/release | Which release are the source code and target APIs restricted to? |
| Bytecode | What major version does the current artifact have? |
| Test runtime | Which JVM do unit/integration tests run on? |
| Production runtime | Which JVM does the production container or server run? |
| Dependencies | Which Java versions do the libraries and plugins support? |
| Native components | Are there any JNI components, agents, or native libraries? |

Do not infer the production version from a developer's machine or from the JDK running CI.

### Step 3 — Define the Compatibility Contract to Preserve

Examples:

- The new artifact must still run on Java 17.
- Only production is upgraded to Java 21 in the first wave.
- Shared modules must maintain binary compatibility with older consumers.
- Public APIs and data formats must not change.
- The application must run on both the current Linux container and the staging environment.

The clearer the compatibility contract, the easier it is to control the scope of the migration.

### Step 4 — Check Dependencies and Build Tools

An application may not use any new Java features yet still fail to build if Gradle/Maven plugins, annotation processors, or dependencies do not yet support the new JDK.

Checks needed:

- Whether the Gradle/Maven version supports the JDK used to run the build.
- Whether the compiler plugin supports the target release.
- Whether annotation processors and bytecode instrumentation are compatible.
- Whether dependencies contain class files or APIs requiring a newer runtime.
- Whether libraries use deep reflection or JDK internal APIs.
- Whether testing, packaging, coverage, and static analysis plugins support it.

### Step 5 — Select a Verification Slice

Before migrating the entire system, choose a representative module or service that has full dependencies and a deployment setup similar to production. Verify the build, tests, startup, external service connectivity, and runtime observability on the target platform.

An overly simple module may not expose issues with dependencies, reflection, or configuration. Choose a slice capable of representing real-world risks.

### Step 6 — Define Completion Criteria

Criteria should include:

- Successful build using the selected toolchain.
- The artifact has the declared bytecode release.
- Unit tests and integration tests run on the target runtime.
- Verification of API contracts and critical data formats.
- Verification of startup, shutdown, health checks, logging, and metrics.
- Verification of TLS, certificates, database drivers, message brokers, and external services.
- Measurement of memory, CPU, throughput, and latency when there are performance requirements.
- A rollback procedure that has been tested or can be clearly executed.

## 9. Common Misconceptions

### "Using JDK 21 to Build Means the Application Is Already Running on Java 21"

Incorrect. The JDK used to build and the JVM used to run the application are two separate configurations. Moreover, JDK 21 can compile with --release 17, producing bytecode targeting Java 17.

### "Old Bytecode Runs on a New JVM, So Testing Is Unnecessary"

Incorrect. Being able to read class files is only one condition. Removed APIs, reflection, JVM options, TLS, charset, timezone, native libraries, and default behaviors can still cause the application to fail or produce different results.

### "Setting sourceCompatibility and targetCompatibility Is Enough"

Not always enough. Platform APIs must be restricted to match the target release. With JDK 9 and later, --release is usually a clearer choice. At the same time, dependencies and compiler plugins must be checked.

### "Recompiling Without Changing Source Code Carries No Risk"

Recompilation can change the compiler, annotation processors, plugins, dependency graph, or packaging process. Therefore, the new artifact still needs to be tested.

### "Modernization Means Replacing All Old Syntax"

No. New syntax should only be used when it makes code easier to understand, safer, or easier to maintain. Old code that is stable, clear, and compatible with the target release does not necessarily need to be rewritten.

### "Upgrading the Runtime and Upgrading the Bytecode Release Are the Same Thing"

No. The runtime is the execution environment; the bytecode release is the compilation target. You can upgrade the runtime while keeping the artifact unchanged, or build with a new JDK while still generating bytecode for an older runtime.

### "If the Application Starts Up, the Migration Succeeded"

Not sufficient. Starting up successfully does not prove that business logic, data, integrations, security, performance, and operability remain correct. Testing must be conducted according to the defined compatibility contract.

## 10. Comprehensive Example: Migrating a Service from Java 17 to Java 21

Suppose a service currently has the following configuration:

~~~text
JDK running Gradle:    17
Compiler:              17
Target release:        17
Bytecode:              Java 17
Test runtime:          17
Production runtime:    17
~~~

The team wants to move production to Java 21 without using new language features yet.

The work can be split into two phases.

**Phase 1: upgrade the runtime, keep the artifact**

~~~text
JDK running Gradle:    17
Compiler:              17
Target release:        17
Artifact:              unchanged
Test runtime:          21
Production runtime:    21
~~~

Run the existing artifact on Java 21 in a test environment. Verify startup, business flows, integrations, TLS, charset, logs, metrics, and performance. If errors are found, investigate runtime differences before expanding the scope of changes.

**Phase 2: standardize the build toolchain**

~~~text
JDK running Gradle:    a version supported by Gradle
Compiler toolchain:    21
Target release:        17
Bytecode:              Java 17
Test runtime:          17 and/or 21 depending on support targets
Production runtime:    21
~~~

Switch the compiler toolchain to JDK 21 while keeping release 17. Rebuild the artifact and run tests. If the product needs to continue supporting Java 17, it must be tested on Java 17; if Java 21 is the new minimum runtime, tests should still be run on Java 21 and deployment requirements clearly updated.

Once these two phases are stable, the team can plan a separate change to modernize source code or raise the target release to 21. That way, when an error occurs, the team can distinguish whether the error is caused by the runtime, the compiler/artifact, or source code changes.

## 11. How to Document Migration Scope in Technical Documentation

A migration plan should avoid simply stating "Upgrade Java 17 to 21". Document it specifically:

~~~text
Runtime:
  Current: Java 17
  Target: Java 21

Build JDK:
  Current: JDK 17
  Target: JDK 21

Compiler release:
  Current: 17
  Target: 17

Source changes:
  None in this phase

Dependency changes:
  List exact libraries and versions, or state none

Compatibility contract:
  Artifact must remain runnable on Java 17
  Production deployment target is Java 21

Validation:
  Build, unit tests, integration tests, runtime smoke tests,
  security/TLS checks and operational metrics

Rollback:
  Previous artifact and Java 17 runtime remain deployable
~~~

When changes span multiple layers, document each layer and its rationale. For example, upgrading the runtime to receive security patches is one goal; raising the target release to use new APIs is another goal; migrating frameworks because the old framework is no longer supported is a third goal. Each goal may require its own rollout timing, completion criteria, and rollback plan.

## 12. Key Points to Remember When Evaluating a Migration Proposal

Before approving a proposal, be able to clearly answer:

1. Is the primary change in the runtime, compiler/artifact, or source code?
2. What are the current versions of the build JDK, compiler JDK, target release, and production JVM?
3. What is the lowest Java version that the new artifact must support?
4. Do dependencies, frameworks, annotation processors, and native libraries meet the target?
5. Is the compatibility to be preserved source, binary, runtime, behavioral, or operational?
6. What evidence proves the application works correctly on the target environment?
7. If the change fails, how can we roll back to the previous artifact and runtime?

Three short questions can be used for quick classification:

- **Runtime upgrade:** "Does the existing artifact run correctly on the new JVM?"
- **Recompilation:** "Can the existing source code be rebuilt with the new toolchain and produce an artifact with the right release?"
- **Source modernization:** "Which source code changes deliver value while still preserving the necessary compatibility contracts?"

Once these three questions are answered, the scope of a Java migration becomes clearer. The team can plan layer by layer, select focused tests, and identify the cause when a migration step fails to meet requirements.
