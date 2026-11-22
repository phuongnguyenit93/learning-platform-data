# Determining the minimum Java version committed by applications and libraries

During system assessment before migration, an important decision is determining the lowest Java version that an application can and will support. This result directly impacts the target JDK version, framework and library choices, build configuration, deployment environment, test matrix, and the range of users who can upgrade.

The minimum version cannot be determined solely by looking at the JDK installed on a developer machine or the version declared in a build file. You must simultaneously consider application source code, bytecode, Java APIs used, all dependencies required at runtime, frameworks, application servers, agents, and vendor support commitments.

## 1. Understanding the minimum Java version properly

The minimum Java version (or minimum supported Java version) is the lowest version for which a component is designed, tested, and declared to be supported. In a real system, there are multiple different minimum levels; clearly state which level is being discussed.

### 1.1. Minimum version to run the application

This is the lowest JRE/JDK version on which the application can run in a supported environment. This level is influenced by:

- Bytecode versions of classes in the application and dependencies.
- Java platform APIs used by source code or libraries.
- Java requirements of frameworks, application servers, drivers, agents, and runtime libraries.
- JVM features or runtime configurations the application relies upon.
- Supported operating systems, CPU architectures, and native libraries.

An application may compile successfully yet fail to run on a lower runtime if a dependency requires newer bytecode or APIs.

### 1.2. Minimum version to compile

This is the lowest JDK that can be used to compile source code under the project's configuration. This level may differ from the runtime version.

For example, a project may use JDK 21 as the compiler while setting `--release 17` to emit bytecode and restrict platform APIs to Java 17. In that case, the build requires a sufficiently new JDK per the build tool's requirements, while the artifact targets a Java 17 runtime. Using a newer compiler does not automatically mean the application requires a runtime of the same version.

### 1.3. Minimum version to run the build workflow

Maven, Gradle, plugins, annotation processors, packaging tools, and CI runners also have their own JDK requirements. A version of Gradle or a plugin may require a newer JDK to run, even though the application is compiled for a lower runtime.

Therefore, record separately:

| Scope | Question to answer |
| --- | --- |
| Build JDK | Which JDK can run Maven/Gradle and the project's plugins? |
| Compile release | Which Java version's APIs and bytecode is the source code compiled against? |
| Test JDK | Which Java versions are the application and test suite executed on? |
| Runtime JDK | What is the lowest supported Java version when deploying the application? |
| Production support | Which versions do vendors and the organization commit to supporting in operations? |

Do not collapse these levels into a single number if they have different meanings. When saying an application “supports Java 17”, clarify whether that means supporting running the application, building the application, or both.

### 1.4. Runnable version vs committed supported version

An application might happen to run on Java 11 while the development team only tests, patches, and supports production from Java 17 onward. In that case:

- Java 11 may be the observed technical compatibility level.
- Java 17 is the product's official support level.

When assessing for migration, identify both if possible. The minimum version published to customers or dependent systems should be based on an evidenced and testable commitment, not on a guess that “it probably still runs”.

## 2. Scope to assess

Before gathering versions, pinpoint the exact deployment unit and execution paths that must be supported.

### 2.1. Identify the application unit

For a single-application system, you can assess the main deployment artifact such as JAR, WAR, or EAR. For a multi-service system, produce separate results for each service because they may have different dependencies and upgrade lifecycles.

For a multi-module application, distinguish:

- Modules packaged and deployed together.
- Modules published independently as libraries.
- Modules serving only build or testing.
- Modules or dependencies enabled only in a specific profile or environment.

A module using a newer Java version can raise the minimum of the entire product if it is always packaged or loaded in the same process. If a module is optional and absent in a given deployment configuration, record the minimum per configuration.

### 2.2. List dependencies actually required at runtime

Collect both direct and transitive dependencies. Classify them by role:

| Group | Example | Can affect runtime floor? |
| --- | --- | --- |
| Required runtime | Framework, logging, ORM, business libraries, JDBC driver | Yes; must evaluate lowest supported version. |
| Environment-dependent runtime | Database driver, messaging client, cloud SDK, adapter | Yes if that environment is within support scope. |
| Optional/profile | Reporting module, integration plugin, connector enabled only in one profile | Yes in configurations enabling that component; may need per-profile runtime floor. |
| Build-time | Compiler plugin, code generator, annotation processor | Usually affects build JDK; can affect artifact if generated code depends on new APIs. |
| Test-only | JUnit, test framework, mock server, test container | Usually affects test JDK; does not necessarily dictate production runtime. |
| Operational | Java agent, profiler, monitoring agent, security agent | Can affect runtime if loaded in production. |

Do not ignore transitive dependencies. An application might not call a library directly, yet a framework or another library still loads and executes it at runtime.

### 2.3. Identify the actual environment

Record components outside Java source code:

- JDK distribution and version used in each environment.
- Container image or deployment host.
- Application server or servlet container.
- Java agents, JNI libraries, and native libraries.
- Operating system, CPU architecture, and related system packages.
- JVM options, environment variables, system properties, and security configuration.

A library may support Java 11 while the monitoring agent or application server in use requires Java 17. The minimum of the deployed application must account for these mandatory components as well.

## 3. Gathering evidence of Java requirements

No single source always reflects the full minimum Java version. Combine official documentation, artifact metadata, build configuration, bytecode analysis, and runtime testing.

### 3.1. Vendor compatibility documentation

For frameworks, application servers, drivers, and key libraries, locate the following documents:

- System requirements or prerequisites.
- Supported Java versions or compatibility matrix.
- Release notes of the exact version in use and the planned target version.
- Migration guides and minimum dependency version information.
- Support, maintenance, and end-of-support policies.

Prioritize official documentation from the exact vendor and exact artifact version. An old tutorial or forum answer can help find investigation leads, but is not enough to establish a support commitment.

When recording, save the URL or document name, library version, check date, and relevant concluding statement. If documentation only says “tested on Java 17” without declaring lower versions unsupported, do not infer the support boundary on your own.

### 3.2. Metadata in Maven POM

Open the artifact's POM or the POM published alongside the library. You may encounter properties such as:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
```

Compiler properties indicate how the project declares compilation. They are useful evidence, yet not always a complete runtime commitment. A POM may omit these properties, inherit settings from a parent, or use a separately configured plugin.

In particular, `source` and `target` do not fully restrict the Java APIs source code can call. A project compiled with a newer JDK while setting a lower `target` can still accidentally call an API introduced only in the newer JDK. When possible, use `release` configuration to control language level, bytecode, and platform APIs together.

### 3.3. Metadata in Gradle

Inspect `build.gradle`, `build.gradle.kts`, convention plugin configurations, and metadata published by the library. For example:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

In this example, the toolchain picks JDK 21 for the compiler, while `options.release` sets Java 17 API and bytecode targeting. Actual configuration may reside in shared plugins or be applied per subproject, so inspect the effective configuration rather than just a root-directory build file.

Gradle Module Metadata may include the `org.gradle.jvm.version` attribute for published variants. This attribute is helpful when checking the JVM level a variant requires. However, not every library publishes Gradle metadata; check the POM, documentation, and actual artifact as well.

### 3.4. Manifest and JAR structure

A JAR manifest may contain information such as `Build-Jdk`, `Created-By`, or other implementation details. These are traces of the environment that produced the artifact, not conclusive proof of the minimum runtime.

For multi-release JARs, a single artifact can contain different classes for different Java versions under `META-INF/versions/`. The JVM selects the appropriate class slice according to the runtime version. When analyzing, examine the exact class slice the target runtime will load; do not draw conclusions from an arbitrarily extracted class.

### 3.5. Class file bytecode version

Every class file has a major version indicating the bytecode format version. You can inspect it with `javap`:

```bash
javap -verbose -classpath path/to/library.jar com.example.SomeClass
```

In the output, locate the `major version` line. Some common values:

| Java release | Class file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

If a required class has a major version higher than what the JVM supports, the older JVM cannot load that class and typically throws `UnsupportedClassVersionError`.

However, the bytecode version indicates only one important limit; it does not prove full compatibility. A class may be compiled to Java 8 bytecode yet still reference an API available only since Java 11 if compilation did not restrict APIs properly. Therefore, combine class file inspection with API checks and support documentation.

### 3.6. Analyzing dependencies and APIs with JDK tools

`jdeps` helps inspect dependencies at class/package level and detect some dependencies on JDK internal APIs:

```bash
# Find dependencies on JDK internal APIs
jdeps --recursive --jdk-internals path/to/application.jar

# Analyze multi-release JAR for the target release
jdeps --multi-release 17 --recursive path/to/library.jar
```

`jdeprscan` helps find deprecated APIs referenced in class files:

```bash
jdeprscan --release 17 path/to/application.jar
```

Replace paths and release values to match the project and JDK in use. Consult `--help` or documentation of the toolset itself before automating these commands, because supported release values depend on the JDK version.

Static analysis tools have limitations. They may not fully detect calls made via reflection, dynamically loaded class names, service loading, native code, external configuration, or behavior appearing only in a specific business flow. Output with zero warnings does not mean compatibility is proven.

## 4. Determining the minimum Java level of application source code

After assessing dependencies, determine which version's APIs and features the application's own source code requires.

### 4.1. Inspect effective compiler configuration

With Maven, inspect:

- Properties `maven.compiler.release`, `maven.compiler.source`, and `maven.compiler.target`.
- Configuration of `maven-compiler-plugin` in the current POM and parent POM.
- Maven profiles that may alter compiler release.
- Modules with custom settings or using a different compiler plugin.

Example release configuration:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

With Gradle, inspect:

- Java toolchain selected for each project.
- `options.release` on `JavaCompile` tasks.
- `sourceCompatibility` and `targetCompatibility`.
- Convention plugins, shared scripts, and per-task configurations.

Do not just read values in files; confirm which configuration is actually applied to the module producing the artifact under assessment.

### 4.2. Distinguishing `source`, `target`, and `release`

- `source` specifies the Java syntax/language level accepted by the compiler.
- `target` specifies the output bytecode format.
- `release` constrains the language level, class file format, and platform API set corresponding to the selected release.

If only `source` and `target` are set, the compiler may still see APIs of the running JDK. That creates a situation where code compiles yet calls APIs absent on a lower runtime. Using `--release` or equivalent configuration is usually a clearer way to produce artifacts targeting a specific Java version.

### 4.3. Finding APIs available only in newer Java versions

Cross-check APIs used by source code against the API documentation of the target version. Focus on:

- Classes, interfaces, methods, and fields newly added in recent releases.
- Deprecated or removed APIs.
- Reflection, module access, and internal package access.
- APIs for I/O, networking, security, processes, concurrency, and serialization.
- APIs invoked indirectly through frameworks or supporting libraries.

Some code snippets may compile with a lower release yet load classes or invoke newer APIs through reflection. Therefore, source code inspection must combine search, dependency analysis, and testing on the lowest runtime planned for support.

## 5. Determining the minimum Java level of each library

For each mandatory dependency, determine the minimum Java level of the exact version to be used. Do not take the Java level of the latest version to conclude for the existing version, and do not take the Java level of another dependency from the same vendor.

### 5.1. Inspect each direct dependency

For each library, record:

- Exact artifact name and version.
- Role and where it is used.
- Scope: compile, runtime, provided, optional, or test.
- Minimum Java version per official documentation.
- Evidence from POM, Gradle metadata, or class files.
- Replacement version if the current one does not meet requirements.

### 5.2. Trace transitive dependencies

A direct library may require Java 8 while one of its transitive dependencies requires Java 17. In that case, the minimum of that dependency branch is Java 17 if that dependency is actually loaded in the configuration under review.

With Maven, you can inspect the dependency tree:

```bash
mvn dependency:tree
```

With Gradle, you can inspect dependencies per configuration:

```bash
./gradlew dependencies
```

Take care to choose the right configuration such as `runtimeClasspath`, `compileClasspath`, or test configurations. A test-only dependency tree does not represent the full production runtime; conversely, inspecting only compile classpath can miss components loaded solely at runtime.

### 5.3. Handling optional dependencies and profiles

If a dependency is only used in a specific profile, plugin, or environment, calculate the Java level for each configuration. For example:

| Configuration | Additional dependency | Assumed minimum Java level |
| --- | --- | --- |
| Core service | Core runtime libraries | Java 11 |
| Core + reporting | Adds reporting library requiring Java 17 | Java 17 |
| Core + legacy connector | Legacy connector still supports Java 11 | Java 11 |

The numbers in the table only illustrate how to analyze. Real projects must use evidence from the exact artifact versions. If the organization declares support for all profiles within one product, the overall published level must satisfy the profile with the highest requirement. If publishing per configuration separately, clearly state the applicability conditions.

## 6. Computing the minimum Java version of the entire application

After collecting constraints, determine the set of mandatory components in each deployment configuration. The runtime floor of that configuration must satisfy the highest requirement within that component set.

This can be expressed as:

\[
J_{min}(profile) = \max(J_{app}, J_{dependency}, J_{framework}, J_{server}, J_{agent}, \ldots)
\]

Where each value is the verified minimum Java version for the corresponding component. Include in the calculation only components truly required in the profile under consideration; do not substitute the build tool's version for the runtime requirement.

### 6.1. Example of computing the minimum level

Suppose a service has the following verified requirements:

| Component | Minimum Java |
| --- | ---: |
| Application source code | 11 |
| Web framework | 17 |
| ORM and database driver | 11 |
| Business processing library | 8 |
| Application server | 17 |
| Mandatory monitoring agent | 17 |

The service's minimum level is Java 17 because the framework, application server, and agent all require at least that version. The fact that some libraries still support Java 8 or Java 11 does not lower the overall minimum.

Suppose the build pipeline uses JDK 21 and compiler release 17. The conclusion should record separately: the build runs on JDK 21; the artifact is compiled for Java 17; the minimum supported runtime is Java 17. Do not simply write “the project uses Java 21” because that sentence does not convey the full compatibility contract.

### 6.2. Separating technical level from product commitment level

After the calculation, compare the result against organizational and vendor support policies. If the application can run on Java 17 yet only has testing, patches, and production support from Java 21 onward, then the product commitment level should be Java 21.

Save at least two conclusions:

- **Technical minimum:** the lowest level with evidence showing the combination of source code, dependencies, and runtime can operate.
- **Supported minimum:** the lowest level that the development and operations teams commit to testing, fixing bugs on, and supporting.

These two levels may match or differ. Do not lower the published commitment simply because a single trial run succeeded on an older runtime.

## 7. Verifying conclusions with real builds and runtimes

Analyzing documentation and metadata produces a grounded hypothesis. To confirm the minimum level, test on that exact JDK and in an environment representative of deployment.

### 7.1. Checking which JDK is being used

Run commands in the build environment and runtime environment:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

On Windows, `gradlew.bat --version` can be used. Commands must run inside the exact terminal, container, or CI runner. `java`, `javac`, Maven, and Gradle can point to different JDKs if `PATH`, `JAVA_HOME`, toolchains, or daemon configurations are inconsistent.

### 7.2. Running on the lowest version planned for support

Prepare a clean environment with the JDK at the calculated minimum level. Run:

- Artifact build per the published configuration.
- Relevant unit tests and integration tests.
- Startup, class loading, and external service connectivity checks.
- Critical business flows.
- Security, TLS, serialization, and data-processing tests if applicable.
- Agent, logging, monitoring, and shutdown checks.

Do not merely run the application with a `java -jar` command if actual production uses an application server, container, agent, or custom JVM configuration. The test environment must represent how the application will be deployed.

### 7.3. Testing both the lowest version and target version

If a product declares support for multiple Java releases, build a test matrix. For example:

| JDK | Purpose | Results to save |
| --- | --- | --- |
| Lowest supported JDK | Confirm runtime floor | Build/test or artifact run, startup logs, business results |
| Migration target JDK | Confirm target environment | Full build/test, warnings, performance, and integration results |
| Higher JDKs if within support scope | Detect future compatibility issues | Test results per support policy |

If the build runs only on a newer JDK, a step running the artifact on the lowest runtime is still needed. Conversely, if tests run on the lowest JDK yet the artifact was built by a compiler without API restrictions, that result does not replace checking `release` configuration and dependencies.

## 8. Template table for recording assessment results

Maintain a table so others can review how conclusions were reached. The following template can be copied into migration documentation or a dependency inventory sheet.

| Component | Version in use | Role/scope | Minimum Java | Evidence source | Status |
| --- | --- | --- | ---: | --- | --- |
| Application/service | Record artifact version | Runtime | Record source analysis result | Compiler release, API scan, runtime test | Verified / needs check |
| Framework | Record version | Required runtime | Per compatibility matrix | Vendor documentation | Verified / needs check |
| Library A | Record version | Direct runtime | Per docs and artifact | Release notes, metadata, bytecode | Verified / needs check |
| Library B | Record version | Transitive dependency | Per docs and artifact | Dependency tree, metadata | Verified / needs check |
| Build plugin | Record version | Build-time | JDK running build | Plugin documentation | Verified / needs check |
| Application server | Record version | Runtime | Per support matrix | Server documentation | Verified / needs check |
| Java agent | Record version | Production runtime | Per agent docs | Vendor documentation and tests | Verified / needs check |

At the application level, additionally record:

| Field | Value to record |
| --- | --- |
| Deployment unit | Service, module, or artifact name |
| Build JDK | JDK version running the build workflow |
| Compile release | `release` value or equivalent configuration |
| Technical minimum | Lowest analyzed and verified runtime version |
| Supported minimum | Lowest version committed for support |
| Target migration version | Java version being migrated toward |
| Applicable configuration | Related profiles, environments, and optional dependencies |
| Evidence | Doc links, logs, scan reports, and test results |
| Reviewer/review date | Owner of conclusion and verification date |

## 9. Common mistakes when determining minimum Java version

### Relying solely on the JDK on a developer machine

The JDK installed on a workstation may be much newer than the production runtime. It may also differ from the JDK used by CI or containers. Collect information from every relevant environment.

### Equating build JDK with runtime JDK

Building with JDK 21 does not necessarily force the application to run on Java 21. Conversely, building with an older JDK does not prove dependencies support that runtime. Record build JDK, compile release, and runtime floor separately.

### Checking only `sourceCompatibility` or `targetCompatibility`

These two properties do not guarantee source code only calls APIs present in the target version. Prefer `--release` or equivalent configuration, while inspecting dependencies and dynamically loaded code.

### Checking only direct dependencies

Transitive dependencies, runtime plugins, agents, and drivers can impose higher requirements. Inspect the exact runtime dependency graph and deployment configuration.

### Relying on the major version of a single class

A high major version indicates an older runtime may fail to load the class. A low major version does not prove all APIs used exist on that runtime. Bytecode, APIs, documentation, and tests must be combined.

### Treating metadata as a complete commitment

A POM or manifest may be incomplete, outdated, or describe only how the build ran. Confirm against official documentation and the specific artifact version.

### Treating a single trial run as a support commitment

One successful run does not prove every profile, workload, operating system, or production configuration is supported. A support commitment requires a test matrix, clear scope, and an error-handling process.

## 10. Workflow during the system assessment phase

The following sequential workflow can be applied per service or artifact:

1. **Lock scope:** identify artifacts, modules, profiles, environments, and mandatory components.
2. **Record current state:** collect build/runtime JDKs, compiler release, frameworks, dependencies, servers, and agents.
3. **Build dependency graph:** include direct, transitive, runtime, optional, and test dependencies.
4. **Gather evidence:** read compatibility matrices, release notes, metadata, and bytecode details of the exact versions.
5. **Analyze source code:** inspect compiler release, Java APIs, reflection, module access, and dynamic loading points.
6. **Compute runtime floor:** take the highest requirement among mandatory components for each profile.
7. **Determine commitment level:** align with organizational support policies and test scope.
8. **Verify:** build and run on the lowest runtime planned for support, then test on the migration target JDK.
9. **Record decision:** save results, evidence sources, assumptions, and unverified items.

The output of the assessment phase should be a verifiable conclusion, such as: “Service A uses JDK 21 to build, compiles with release 17, requires minimum runtime Java 17 due to framework and application server; Java 17 and Java 21 are in the supported test matrix.” Only record such a conclusion when all details have factual evidence.

## 11. Assessment completion checklist

- [ ] Clearly identified every service, artifact, module, and profile requiring support.
- [ ] Recorded build JDK, compile release, test JDK, and runtime JDK separately.
- [ ] Inventoried direct, transitive, runtime, optional dependencies, frameworks, servers, and agents.
- [ ] Looked up support documentation for exact versions of key dependencies.
- [ ] Inspected effective compiler configuration in Maven/Gradle and related modules.
- [ ] Analyzed bytecode, platform APIs, and reflection or dynamic class-loading points where appropriate.
- [ ] Calculated the runtime floor for each deployment configuration.
- [ ] Distinguished technical compatibility level from official support level.
- [ ] Tested on the lowest runtime planned for support and saved evidence.
- [ ] Clearly recorded target migration Java version, assumptions, and unverified items.

Upon completing the assessment, the development team can use the runtime floor and supported minimum as inputs for deciding on JDK upgrades, dependency upgrades, deployment environment adjustments, and test matrix design. If the requirement of a mandatory component has not yet been verified, keep its status unverified and continue investigating before publishing the minimum Java level of the whole application.
