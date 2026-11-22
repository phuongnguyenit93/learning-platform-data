# JDK Compatibility of Direct and Transitive Dependencies

## 1. Why Are Dependencies a Risk Point in Java Migration?

In **Java Advance Compatibility Migration**, changing the JDK does not only affect source code written by the development team itself. An application typically depends on dozens or hundreds of libraries: frameworks, JSON/XML serialization, HTTP clients, database drivers, logging, security, caching, testing, bytecode manipulation, build plugins, and integration components.

A dependency may run well on the current JDK yet fail when switching JDKs because:

- The library was compiled for a newer Java version than the deployed runtime.
- The library uses JDK APIs that were removed or changed behavior.
- Legacy frameworks access JDK internal APIs or perform reflection into packages that are no longer open.
- A transitive dependency pulls in a class version incompatible with the library calling it.
- The build tool selects different dependency versions across compile, test, and runtime.
- A JAR contains a native library or javaagent that does not support the target CPU/JDK.
- Modules running on the module path differ from the traditional classpath.
- One library uses the javax.* namespace while another library expects jakarta.*.
- A newer library requires a higher Java version than the minimum Java level committed by the product.

A successful build does not automatically prove that the application is JDK-compatible. The compiler may not see all runtime dependencies; a class may only be loaded on a rare execution path; or the actual deployment container may carry a different set of dependencies from the test environment.

Therefore, dependency management in migration must inspect **the entire actually resolved dependency graph**, not merely the list of directly declared libraries.

## 2. Direct Dependencies and Transitive Dependencies

### 2.1. Direct Dependencies

A **direct dependency** is a library the application explicitly declares in the build file, for example:

~~~kotlin
dependencies {
    implementation("com.example:api-client:3.2.0")
    implementation("com.example:json-adapter:2.1.0")
}
~~~

These are illustrative coordinates, not real libraries to download. The developer intentionally selects api-client and json-adapter.

### 2.2. Transitive Dependencies

A **transitive dependency** is a library required by another dependency, even when the project does not declare it directly.

~~~text
application
  ├─ api-client:3.2.0             (direct)
  │   ├─ http-core:5.0.0         (transitive)
  │   │   └─ tls-helper:2.0.0    (transitive)
  │   └─ json-core:4.1.0         (transitive)
  └─ json-adapter:2.1.0           (direct)
      └─ json-core:3.8.0         (transitive, version conflict)
~~~

In the graph above, json-core appears along two paths with two versions. The build tool applies conflict resolution rules to choose the effective version, or reports an error if configuration/metadata does not allow selecting a consistent version.

A library at a deep level such as tls-helper can still prevent the application from running on the target JDK. Not declaring it directly does not eliminate its risk.

### 2.3. The Declared Graph Differs from the Used Graph

You must distinguish:

1. **Declared dependencies:** dependencies appearing in the build script/POM.
2. **Resolved dependencies:** the final version selected by the build tool after conflict resolution, dependency management, constraints, and exclusions.
3. **Packaged dependencies:** JARs/classes actually placed inside the executable JAR, container, deployment directory, or application server.
4. **Loaded dependencies:** classes actually loaded by the runtime/classloader during execution paths.

A dependency may be declared yet excluded by a profile; may resolve to a different version at runtime than at compile time; or may not be packaged due to provided scope. When a JDK error occurs, trace back to the actual artifact rather than looking only at the initial build file.

## 3. Compatibility Dimensions to Identify

JDK compatibility of a library is not a binary “yes/no” property based on a single number. Examine each dimension:

| Compatibility Dimension | Question | Required Evidence |
|---|---|---|
| Bytecode | Can the dependency's class files be read by the target JVM? | Class-file major version; inspect the entire artifact. |
| Java API | Does the library call APIs available only in a newer release or removed from the JDK? | Compile/test on the minimum runtime, analyze with tools. |
| JVM internals | Does the library use sun.*, jdk.internal.*, or reflection into the JDK? | jdeps, IllegalAccess/InaccessibleObjectException logs, release notes. |
| Binary linkage | Do the methods/classes/fields referenced by the library match the runtime version? | Dependency graph and integration tests; linkage errors. |
| Module system | Are module names, requires, exports, opens, and split packages valid? | module-info, jdeps, running on the actual module path. |
| Framework integration | Is the library compatible with the target framework/container version? | Support matrix, BOM, and integration tests. |
| Native code / agent | Do JNI, JNA, JVMTI, and agents support the JDK/OS/CPU? | Vendor docs, execution on the target runtime/architecture. |
| Behavioral | The API works, but does its behavior remain appropriate? | Regression tests for TLS, serialization, concurrency, locale, and business logic. |
| Security/support | Is the version still patched and supported on the target JDK? | Release notes, advisories, and vendor maintenance policy. |

A library with Java 17-compatible class files can still fail when running on Java 17 if it references a method available only in Java 21, or if the actual runtime dependency carries Java 21 bytecode.

**The application's minimum Java level must not be lower than the highest level required among the dependencies needed at runtime**, unless an alternative packaging/variant mechanism is specifically designed and verified.

## 4. Class-File Version: The First Signal

The JVM can only load class files in formats supported by that version. A class compiled for a newer runtime can fail on older Java with UnsupportedClassVersionError.

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Example:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Reading class metadata:

~~~bash
javap -verbose -classpath dependency.jar com.example.library.EntryPoint
~~~

Look for the major version field in the output.

### 4.1. Inspect the Entire JAR, Not Just One Class

A JAR can contain multiple packages, generated classes, shaded dependencies, or classes under META-INF/versions in a multi-release JAR. Checking one entry point does not guarantee that every other class in the artifact shares the same target.

You can list the contents:

~~~bash
jar tf dependency.jar
~~~

When a multi-release JAR is present, the base part and variants specific to individual Java releases may use different class-file versions. Confirm how the JVM selects classes on the target runtime, especially with dependency packaging or analysis tools that do not handle multi-release layout properly.

### 4.2. The Build Release Level Is Not the Java Runtime Level

Gradle example:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

This configuration requires a Java 21 compiler toolchain while generating application bytecode targeting Java 17 in the corresponding JavaCompile tasks. It **does not** force runtime dependencies to also be Java 17-compatible. If runtimeClasspath pulls in a Java 21-only JAR, the application can still fail on Java 17.

Similarly, the Maven property maven.compiler.release only controls project compilation when properly configured; it does not rewrite bytecode inside JARs downloaded from a repository.

## 5. Java APIs and Other Changes Beyond Bytecode

Even when major versions match, a dependency can still face risks due to platform changes.

### 5.1. APIs Removed from the JDK

A classic example is the Java EE and CORBA modules once bundled with some older JDKs and removed starting in JDK 11. Legacy libraries may reference javax.xml.bind, javax.xml.ws, or org.omg.CORBA where previously no external dependency was needed.

In this case:

- Check source/bytecode and integration libraries to see which APIs are used.
- Identify replacement API JARs and runtime implementations.
- Choose the javax or jakarta generation matching the framework.
- Verify both build-time code generation and the runtime provider.

Do not merely add an API JAR and conclude XML/SOAP functionality works. For some technologies, an independent runtime implementation or provider is what actually performs execution.

### 5.2. Encapsulation and Internal APIs

Some older dependencies access JDK internal APIs, such as sun.misc or jdk.internal, or use reflection to open private fields of platform Java classes.

When the JDK enforces stricter module encapsulation, the application may encounter:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
~~~

To detect JDK internal API dependencies:

~~~bash
jdeps --jdk-internals dependency.jar
~~~

However, static analysis is not guaranteed to detect reflective lookups using dynamically constructed class names. It must be combined with integration tests.

Flags such as --add-opens or --add-exports are sometimes used as controlled transitional measures, yet are not proof of long-term library compatibility. If the vendor has released a version replacing internal APIs with supported APIs, that appropriate version should generally be preferred.

### 5.3. Runtime Behavior Changes

A dependency handling TLS, timezone, locale, charset, serialization, or concurrency can change behavior when switching JDKs even without linkage errors:

- TLS handshake or certificate validation fails due to changed security policies.
- Default charset or locale changes how data is encoded/decoded.
- Reflective access no longer works as before.
- Serialization frameworks require module opens or new configuration.
- Date/time and timezone databases affect formatting results.
- Algorithms or native providers differ in numerical calculations.

Identify critical business contracts and test on the real JDK, rather than relying solely on library compatibility claims.

## 6. The Dependency Graph in Gradle

Gradle resolves dependencies per configuration and can use module metadata, variants, constraints, platforms, and rules. Therefore, you must inspect each required classpath, not just a single project-wide list.

### 6.1. Viewing Compile and Runtime Dependencies

Example in a project using the Java/Java Library plugin:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

If multi-module:

~~~bash
./gradlew :service-a:dependencies --configuration runtimeClasspath
~~~

Note that configuration names may vary by plugin or module; the commands above illustrate standard Java source sets.

### 6.2. Tracing the Source of a Transitive Dependency

~~~bash
./gradlew :service-a:dependencyInsight \
    --dependency library-name \
    --configuration runtimeClasspath
~~~

dependencyInsight helps observe dependency paths and why a version was selected, such as a constraint, rule, or version conflict. In Gradle, a library requesting a higher version can cause Gradle to pick a different version than the developer expected when no strict constraint is present.

When you spot a Java 17-incompatible library appearing in runtimeClasspath, find **the parent library pulling it in**, rather than just deleting the JAR from the build directory.

### 6.3. Distinguishing Configurations

| Configuration | Common Scope | Migration Significance |
|---|---|---|
| implementation | Dependency used in implementation, not necessarily exposed in the consumer's compile API. | Typically affects the module's compile/runtime and downstream runtime per metadata. |
| api | Dependency exposed in the public API of a module using the java-library plugin. | Consumers may need its types at compile time; upgrading versions can affect source/binary API. |
| compileOnly | Present at compile time, not automatically included at runtime. | Risks missing classes at runtime if the container does not provide them. |
| runtimeOnly | Needed to run, not needed to compile main source. | Can cause failures that surface only at runtime. |
| testImplementation | Used for test compile/runtime. | Test frameworks or helpers also have their own minimum JDK levels. |
| testRuntimeOnly | Needed only when running tests. | Tests may fail on the JDK even if the production application does not use that dependency. |

A project may have framework/plugin-specific configurations. You must inspect the actual resolved graph of the deployed artifact/launcher.

### 6.4. Gradle Variants and Java Compatibility Metadata

When published in metadata, Gradle can use a variant's Java compatibility attribute, such as org.gradle.jvm.version, when selecting a matching artifact. This mechanism helps detect some cases where a dependency requires a newer Java version than the consumer.

However:

- Not every artifact from a Maven repository has metadata fully describing its minimum Java level.
- Incorrect or missing metadata can cause an unsuitable artifact to be selected.
- Variant checking does not replace inspecting class files and runtime tests.
- The Java toolchain of a compile task, the module target, and the Java version running Gradle are distinct concepts.

Therefore, when Gradle reports no matching variant found for a Java version, check the metadata and the Java level actually declared by the consumer. Do not raise the target solely to silence the resolver if the product is still obligated to support older JDKs.

## 7. The Dependency Graph in Maven

Maven resolves dependencies using POMs, scopes, dependencyManagement, and mediation rules. For a normal release, inspect the resolved tree rather than only the dependencies written in pom.xml.

### 7.1. Viewing the Dependency Tree

~~~bash
./mvnw dependency:tree
~~~

If you need to focus on runtime:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

You can filter by artifact group/name when supported by the tool and plugin version:

~~~bash
./mvnw dependency:tree -Dincludes=org.example:example-core
~~~

In these commands, org.example:example-core is an illustrative coordinate. If a plugin must be installed/configured, use the version managed in the build.

### 7.2. Dependency Mediation: Nearest Definition and Version Management

In Maven, version conflict resolution has mediation rules based on dependency distance in the tree; when paths have equal depth, declaration order can affect selection. dependencyManagement can manage versions used by corresponding dependencies, yet declaring a version in dependencyManagement **does not** by itself add the dependency to the project.

Example:

~~~text
application
  ├─ A:1.0
  │   └─ common:1.1
  └─ B:2.0
      └─ common:2.5
~~~

If library A was built against common:1.1 while runtime resolves to common:2.5, check binary/behavioral compatibility between the two versions. A newer version is not always compatible or suitable for the minimum Java level.

### 7.3. BOM and dependencyManagement

A BOM (Bill of Materials) helps align versions across a group of libraries, especially frameworks with multiple interdependent modules.

Maven structure example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The coordinate above is illustrative. A BOM helps manage version combinations, yet you still must verify which target JDK and minimum Java level that framework/BOM version supports.

### 7.4. Maven Scopes and Runtime Impact

| Scope | Key Points to Note |
|---|---|
| compile (default) | Present in compile and many downstream classpaths; normally present at runtime. |
| runtime | Not needed to compile main source, yet required to run the application. |
| provided | Expected to be supplied by the environment/container/JDK at runtime; verify this assumption. |
| test | Used only for testing; may require a distinct Java version. |
| optional | Affects transitive propagation to consumers; may require explicit declaration when used. |

An API previously in JDK 8 that was removed in JDK 11+ should no longer be assumed to be provided by a newer JDK. Distinguish between an application server environment that actually supplies the API/implementation and a standard JDK that no longer contains the legacy module.

## 8. When Direct and Transitive Dependencies Conflict

### 8.1. One Version Selected, Multiple Libraries Using It

Example:

~~~text
Payment Service
  ├─ payment-client 4.x ──> jackson-core A
  ├─ audit-library 2.x ──> jackson-core B
  └─ framework BOM     ──> jackson-core C
~~~

Versions A/B/C may not be equivalent. The build tool picks one version per resolution rules, yet a library compiled against B's API may reference a method absent from C.

Errors that may appear:

- NoSuchMethodError when the expected method does not exist in the runtime version.
- NoSuchFieldError when a field changed or disappeared.
- IncompatibleClassChangeError if a static/instance or class/interface contract changed.
- AbstractMethodError due to an unsynchronized interface/implementation.
- ClassCastException when incompatible types or duplicate classes exist across classloaders.
- NoClassDefFoundError if a class is missing or fails to load.

Not every error comes from the JDK. Changing the JDK often goes together with upgrading a framework, producing a different resolved dependency set than before; inspect both.

### 8.2. Forcing the Latest Version Is Not Always Right

A newer version can:

- Require a newer Java version than the application supports.
- Change namespace from javax to jakarta.
- Remove old methods or alter APIs.
- Change default serialization, HTTP, or TLS behavior.
- Drop support for an older framework/application server.
- Contain license or security policy changes requiring review.

Therefore, “force latest” is not a general solution for dependency conflicts. Choose a **supported combination**, based on the framework matrix, release notes, and real tests.

### 8.3. Purposeful Exclusions and Overrides

When a transitive dependency pulls in an unsuitable version, one approach can be:

1. Find the pull-in path using dependencyInsight or dependency:tree.
2. Check the version requirements of the parent dependency.
3. Consult the official framework BOM or constraints.
4. If a compatible release exists, adjust the direct dependency version or alignment policy.
5. If excluding is necessary, declare the replacement dependency explicitly and test at runtime.
6. Document the rationale, risks, and conditions for removing the override.

An exclusion only alters the dependency graph; it does not magically create compatibility between the parent library version and the substituted version. If the parent library calls a removed method, excluding the JAR and pulling another version can still trigger linkage errors.

## 9. Special Attention to Frameworks, BOMs, and Jakarta Migration

Large frameworks typically maintain compatibility matrices tied to JDKs and many components:

- Spring/Spring Boot and starters.
- Jakarta EE application servers.
- Hibernate/JPA.
- Netty, HTTP stacks, Servlet containers.
- gRPC and protobuf.
- Logging frameworks, bytecode instrumentation.
- Database drivers, message brokers, cloud SDKs.

Do not upgrade one module within a framework family too far away from its BOM and expect everything to keep working. For example, a newer JPA provider may require Jakarta Persistence while the legacy application still uses javax.persistence. A newer JSON binding library may alter reflection handling or require a higher Java release.

### 9.1. Separate JDK Migration and Framework Migration When Possible

A multi-step plan:

~~~text
Application on the older JDK
        │
        ▼
Upgrade dependencies within lines still compatible with the older JDK
        │
        ▼
Verify runtime on the target JDK (keep API/framework if feasible)
        │
        ▼
Upgrade framework + BOM + code generation from the same generation
        │
        ▼
Migrate javax/jakarta or API breaking changes if needed
        │
        ▼
Test and deploy the new artifact
~~~

Not every combination is feasible; a target framework may require a newer JDK, forcing certain steps to happen together. In such cases, document the constraints so root causes are not misattributed when failures occur.

### 9.2. Do Not Blindly Replace Every javax with jakarta

The Jakarta EE namespace migration applies to many Java EE APIs, yet several javax.* packages still belong to Java SE. Beyond source imports, annotations, generated code, providers, serializers, and the runtime framework must also come from the same generation.

A direct dependency might move to jakarta while a transitive dependency remains compiled against javax. In that case, the same conceptual API has different binary names; they cannot be treated as the same class.

Verify the exact packages provided and consumed by each artifact rather than looking only at groupId or library names.

## 10. Build Plugins, Annotation Processors, and Code Generation Also Have JDK Levels

The dependency graph does not consist solely of runtime libraries. The build pipeline involves many plugins/tools:

- Compiler plugins and annotation processors (e.g., code generators).
- Build plugins, static analysis, code coverage.
- Test runners, mocking frameworks, testcontainers.
- Bytecode instrumentation, agents.
- JAXB/JAX-WS/Protobuf/OpenAPI codegen.
- Packaging, shading, and native-image tooling when used.

They may run on a different JDK than the application's target bytecode. A build plugin requiring Java 21 does not force a published library to run only on Java 21, provided compiler release, packaging, and actual runtime dependencies still satisfy the minimum Java level. Conversely, a plugin generating classes for a newer Java version can prevent the final artifact from running on older Java.

### 10.1. Questions to Check

1. Which JDK is running the Gradle/Maven daemon/process?
2. Which compiler toolchain executes JavaCompile?
3. Are annotation processors compatible with the target compiler/JDK?
4. Does generated source use APIs newer than the target release?
5. Are the test launcher and test dependencies compatible with the tested JDK?
6. Do Jacoco/coverage agents, Mockito/Byte Buddy, or other agents recognize the target class-file version?
7. Are plugins compatible with the Gradle/Maven version and the JDK running the build tool?

Build failures caused by a plugin failing to recognize a Java class-file version differ from runtime failures of the application itself. Separate these paths and avoid bumping the entire production runtime solely to work around an outdated build tool.

## 11. Multi-Release JARs, Shading, and Service Discovery

### 11.1. Multi-Release JARs

A multi-release JAR can contain older-Java-compatible base code alongside classes specialized for newer runtimes under META-INF/versions.

Example:

~~~text
library.jar
  com/example/Feature.class
  META-INF/versions/17/com/example/Feature.class
  META-INF/versions/21/com/example/Feature.class
~~~

On Java 17, the JVM picks the appropriate version under the multi-release mechanism if manifest/packaging complies with requirements. On older runtimes, the base classes must be compatible for the JAR to work.

Check:

- Does the manifest declare Multi-Release according to the applicable rules?
- Do class-file versions inside each versioned directory match the corresponding Java version?
- Does the JAR analysis tool examine the base or a specific release?
- Are any classes missing from the base version, preventing the minimum runtime from executing?

You cannot conclude an entire JAR requires Java 21 merely because it contains a class in META-INF/versions/21. Conversely, you cannot conclude a JAR supports Java 8 merely because one base class has major version 52.

### 11.2. Shaded/Fat JARs

In an executable/fat JAR, dependencies may be bundled or relocated into the same artifact. This creates differences:

- Maven/Gradle metadata no longer clearly indicates the versions of all bundled classes.
- Class versions inside a shaded dependency may be higher than the application's own code.
- Relocation can alter reflection, serialization, and service-provider discovery.
- META-INF/services files may require proper merging so ServiceLoader finds providers.
- Duplicate resources or classes can cause one version to silently overwrite another.

Therefore, compatibility checks must run on the final artifact, not only on pre-packaging JARs.

### 11.3. JPMS, Classpath, and Module Path

On the module path, the JVM enforces module boundaries and resolution differently from the classpath. A dependency may:

- Have a module-info.java with unsatisfied requires.
- Have an automatic module name different from what the team expects.
- Cause split packages when multiple modules supply the same package.
- Require opens for framework reflection.
- Lack necessary uses/provides declarations for ServiceLoader in module scenarios.

If the product actually runs on the classpath, you do not need to convert everything to JPMS during a JDK upgrade, nor should you use classpath test results to declare module-path deployments compatible.

## 12. Native Libraries, JNI, and javaagent

Some dependencies rely on native libraries or runtime agents. Examples:

- JDBC drivers with native authentication.
- Cryptographic providers, HSM, or PKCS#11.
- Compression/media processing libraries.
- JNA/JNI bridges.
- Monitoring/tracing/profiling agents.
- Bytecode weaving/instrumentation.

These components impose additional constraints on:

| Constraint | Scenarios to Check |
|---|---|
| OS | Do Linux/Windows/macOS have matching native binaries? |
| CPU architecture | Are packages supported for x86_64, aarch64, or other platforms? |
| libc/platform | Do Alpine/musl and glibc containers differ? |
| JVM/JVMTI | Does the agent support the Java release, class-file version, and runtime startup options? |
| Security provider | Does the native crypto provider work on the newer JDK? |
| Container | Are native files packaged with load permissions? |

A JAR may be compiled for Java 8 yet contain a native library that cannot run on the target architecture. Hence, Java binary compatibility does not prove full environment compatibility.

If a failure occurs only in production containers or agent-enabled tests, record the OS, architecture, base image digest, JDK distribution, and full list of agent options to reproduce it.

## 13. Tools Supporting Dependency Compatibility Analysis

### 13.1. jdeps

jdeps can analyze dependencies between classes/JARs:

~~~bash
jdeps --jdk-internals dependency.jar
~~~

With an app artifact and required classpath:

~~~bash
jdeps --missing-deps --class-path "libs/*" app.jar
~~~

With a multi-release JAR, you can select the appropriate Java release when supported by the tool version:

~~~bash
jdeps --multi-release 17 --class-path "libs/*" app.jar
~~~

This is static analysis. Reflection, class loading from string names, service providers, and dynamic plugins may not be fully observed. Combine it with runtime tests.

### 13.2. jdeprscan

jdeprscan helps detect bytecode referencing deprecated or forRemoval JDK APIs for a selected release:

~~~bash
jdeprscan --release 17 dependency.jar
jdeprscan --release 17 --for-removal dependency.jar
~~~

Scanning for deprecated APIs does not equate to scanning full compatibility; a library might use no deprecated APIs yet still require a higher JDK or hit other runtime failures.

If using another JDK, verify which releases that jdeprscan supports. When scanning an application JAR, dependencies used for class resolution are not necessarily all scanned automatically; if a specific dependency needs evaluation, scan that artifact directly.

### 13.3. javap and jar

~~~bash
javap -verbose -classpath dependency.jar com.example.EntryPoint
jar tf dependency.jar
~~~

javap helps inspect major versions, signatures, and certain metadata. jar tf helps inspect layout and classes/resources. With hundreds of dependencies, combine automated build/CI tools to generate reports rather than relying on manual checks of one representative class.

### 13.4. Binary API Checking Tools

For libraries publishing public APIs, API diff tools such as japicmp or Revapi can detect changes to classes, methods, modifiers, and hierarchies between two versions.

These tools answer “how has the API between two artifacts changed,” not directly “whether the whole application runs on JDK X.” You still must execute legacy client binaries against the new library and verify runtime compatibility.

### 13.5. Security/SBOM Scanning

Dependency management also requires auditing CVEs, licenses, and support lifecycles. An SBOM helps identify the product's components and versions, while vulnerability scanners surface alerts needing evaluation.

Do not treat applying a security patch as a harmless version bump; a patch/major upgrade can also raise the minimum Java level or alter APIs. Combine security policy with the compatibility matrix.

## 14. Dependency Compatibility Matrix

Each critical dependency should have a record:

| Field | Data to Record |
|---|---|
| Artifact | groupId:artifactId:version or equivalent identifier. |
| Source | Direct or transitive; which path chain introduced it. |
| Scope/configuration | Compile, runtime, test, plugin, annotation processor. |
| Resolved version | Version actually selected by the build tool. |
| Minimum Java | Minimum Java requirement from reliable, verified sources. |
| Target bytecode | Class-file major version or multi-release info. |
| JDK target | Target JDKs the product is migrating to/intends to support. |
| Framework constraints | Versions required by BOM/framework/container. |
| Risk | Removed APIs, internal JDK, reflection, native, namespace, security. |
| Evidence | Release notes, dependency report, test run, artifact checksum. |
| Decision | Keep, upgrade, replace, controlled exclusion, isolate, or remove. |
| Owner/status | Responsible person and handling status. |

Illustrative data example, **not actual compatibility claims of specific libraries**:

| Component | Relationship | Resolved | Required JDK (Hypothetical) | Decision |
|---|---|---|---|---|
| web-framework | Direct | 3.x | Java 17+ | Keep if target Java is 17/21 and matrix is verified. |
| serialization-core | Transitive via web-framework | 2.x | Java 8+ | Test serializer and reflection on JDK 17/21. |
| telemetry-agent | Runtime/agent | 1.x | Java 11–17 (hypothetical) | Need to upgrade agent if production uses Java 21. |
| legacy-xml-api | Transitive via plugin | 2.x | Legacy javax API | Determine build-time vs runtime scope; pick matching generation. |

Do not use the hypothetical values above to decide real versions. Actual policy must rely on concrete artifacts and specific release notes.

### 14.1. Determining the Minimum Java Level for the Whole Product

Suppose the application sets --release 17, yet runtimeClasspath contains a JAR requiring Java 21. When deployed on Java 17, execution is no longer guaranteed.

Choose one of these directions:

1. Select a dependency version that still supports Java 17 with suitable maintenance.
2. Replace the dependency with another implementation compatible with Java 17.
3. Isolate functionality requiring Java 21 into a separate service/artifact if architecture allows.
4. Raise the product's minimum Java level to 21 alongside versioning policy and breaking-change notice.

Do not merely change compiler release from 17 to 21 to make things “fit” and silently break the contract with consumers still running Java 17.

## 15. Testing on the Target JDK

### 15.1. Establish a Reproducible Baseline

Before changing dependencies:

- Record the commit, build tool wrapper, and full JDK details.
- Save the resolved dependency graph for compile/runtime/test.
- Record platforms/BOMs, constraints, exclusions, and custom rules.
- Record artifact checksums, container image digests, and runtime configs.
- Identify key integrations supplied by frameworks/plugins.

If upgrading the JDK simultaneously changes the framework and dozens of dependencies, clearly record all changed variables to analyze regressions.

### 15.2. Recommended Build/Test Matrix

| Item | Current JDK | Target JDK | Significance |
|---|---|---|---|
| Source and generated code build | Baseline | Required if supported | Detects compiler/plugin errors. |
| Unit tests | Baseline | Required | Checks logic and test dependencies. |
| Integration tests | Baseline | Required | Checks framework, DB, HTTP, messaging, serialization. |
| Runtime startup | Baseline | Required | Detects class loading/provider/module errors. |
| Deployment container | Baseline if applicable | Required | Checks OS, native agent, image, and runtime packaging. |
| Minimum-supported Java | If different from baseline | Required if product still commits to it | Confirms the true minimum level. |
| Binary consumer fixture | When public API exists | When public API exists | Runs old client against new library without recompiling. |

If a library advertises Java 17 support despite building with JDK 21, run tests executing the actual artifact and runtime dependencies on Java 17. Running all tests on JDK 21 proves only partial compatibility with JDK 21.

### 15.3. Critical Integration Flows

For framework and infrastructure-level dependencies, prioritize testing:

- JSON/XML serialization: fields, annotations, timezone, null handling.
- HTTP/TLS: certificate chain, hostname, HTTP protocol, proxy, and connection pooling.
- JDBC/ORM: connection authentication, queries, transactions, metadata, schema.
- Message brokers: producer/consumer, serializers, retries, and ACL/TLS.
- Security: token signatures, authorization rules, OAuth/OIDC callbacks.
- Logging/tracing/metrics: agent loading, context propagation, and startup.
- Caching: serialization compatibility and invalidation.
- Scheduler/batch: classloaders, cron, timezones, and long-lived resources.
- Native/agent paths: matching OS/CPU architecture and target JDK.

Success of a single isolated test does not prove an entire dependency is compatible; test scope should reflect critical product execution paths.

## 16. Incident Example: Transitive JAR Requires a Higher JDK

Suppose an application advertises minimum Java 17 and still compiles with --release 17. After upgrading a direct HTTP client, runtimeClasspath pulls in a new transitive dependency compiled for Java 21.

In a CI environment running Java 21, build and tests both succeed. However, when deploying on Java 17:

~~~text
UnsupportedClassVersionError: ... class file version 65.0;
this runtime only recognizes up to version 61.0
~~~

Investigation procedure:

1. Identify the exact class reporting the error.
2. Locate the JAR containing that class in the runtime deployment.
3. Check the major version using javap.
4. Use dependencyInsight or dependency:tree to trace the parent dependency.
5. Check release notes for both the direct dependency and the transitive artifact.
6. Select a Java 17-compatible version/combination or decide to raise minimum Java.
7. Re-run tests on Java 17 against the resolved artifact.

This incident shows that **build JDK is not minimum runtime JDK**. If CI runs only in a Java 21 environment, pipelines easily miss such bugs.

## 17. Incident Example: NoSuchMethodError After Upgrading a Framework

Suppose module A was compiled against common-library 4.x, while module B pulls in common-library 3.x via a transitive dependency. After conflict resolution, runtime uses 3.x, which lacks a method called by A.

When executing the affected code path:

~~~text
java.lang.NoSuchMethodError: 'Result CommonApi.execute(Request)'
~~~

Investigation:

1. Confirm which JAR actually supplies class CommonApi at runtime, not just the version in the build file.
2. Compare the method descriptor in the runtime JAR with the method referenced by the binary caller.
3. Inspect the resolved runtimeClasspath and the dependency path causing that version selection.
4. Cross-check version alignment/BOM compatible with A and B.
5. Adjust versions or upgrade A/B to a compatible combination.
6. Run integration tests on the real deployment artifact, especially flows involving that method.

Do not simply clear caches or force the latest version without knowing the compatibility matrix. If an app server/plugin classloader loads a different copy of common-library, resolve it at the deployment/classloader boundary.

## 18. Incident Example: JDK Encapsulation and Reflection

An older framework uses reflection to access private JDK members. After switching JDKs, the application encounters:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible
~~~

Steps:

1. Read the stack trace and identify the dependency owning the reflection call.
2. Check whether a framework/bytecode utility version supports the target JDK.
3. Use jdeps and note direct internal API usages if any.
4. Prefer upgrading to a framework version that does not require restricted access.
5. If a temporary --add-opens workaround exists, limit its scope and set a removal deadline.
6. Test startup, serialization, proxies, ORM, and code generation on the target JDK.

Do not treat every InaccessibleObjectException as a bytecode target error. They belong to access restriction/module behavior; changing compiler --release will not fix them.

## 19. Controlling Dependency Drift in CI and Deployment Environments

### 19.1. Why Can the Graph Change on Its Own?

The resolved graph can fluctuate due to:

- Using dynamic versions such as 1.+ or wide version ranges.
- Snapshot/changing modules updating over time.
- Changing a BOM/parent POM or plugin.
- Repository mirrors returning different metadata.
- Out-of-sync caches or dependency locks.
- Modules/profiles/feature flags altering dependency scope.
- Containers packaging a different artifact from the tested one.

For migration, prefer pinning/locking versions using mechanisms suited to your build tool. Save the resolved graph, checksums, and build identifier so results can be traced.

### 19.2. Dependency Locking and Verification

Gradle supports dependency locking and dependency verification depending on configuration. Maven generally relies on fixed versions, dependency management, repository policies, and supplementary tools to produce inventories/verify checksums.

Goals:

- Prevent a transitive dependency version from shifting silently between builds.
- Reduce supply-chain risks or mismatched artifact metadata.
- Keep CI and local builds resolving the exact same set of versions.
- Have evidence of the dependency graph accompanying a release.

Do not use checksums or lockfiles as a substitute for JDK testing; a locked artifact version may still be incompatible with the target runtime.

### 19.3. SBOM and Provenance

For distributed products, an SBOM can list components and versions for security teams/customers to inspect. Ensure the SBOM represents the **actually released artifact**, not merely all dependencies in the repository, while storing proper build provenance.

When using fat JARs, shading, or application server-provided dependencies, clearly record who provides each component and its scope in the SBOM.

## 20. Safe Strategies to Replace or Upgrade Dependencies

### 20.1. Prefer Upgrading in Compatible Clusters

Tightly coupled components such as framework modules, ORMs, HTTP stacks, or logging should be upgraded together according to supported BOM/version pairs. Upgrading a single module alone can produce untested combinations.

Example workflow:

~~~text
Lock in baseline dependency graph
           │
           ▼
Determine target JDK and minimum Java contract
           │
           ▼
Group dependencies by framework/BOM and owner
           │
           ▼
Select supported + security-patched versions
           │
           ▼
Build + static analysis + runtime matrix tests
           │
           ▼
Inspect artifact, lock versions, release notes
           │
           ▼
Deploy in phases and monitor regressions
~~~

### 20.2. When a Dependency Needs Removal

A dependency may be unmaintained and block a JDK upgrade. Options:

- Replace with modern JDK APIs if suitable for business logic and contracts.
- Use another actively supported library.
- Write an adapter to isolate the legacy API while consumers migrate.
- Extract into an independent service if runtime differences cannot coexist in one JVM.
- Maintain a time-boxed legacy branch when support commitments cannot yet end.

Avoid maintaining a long-term internal dependency fork without a plan for security patches, licensing, testing, and ownership. Forking may solve an immediate issue yet transfers full maintenance burden onto your team.

### 20.3. Handling Priority Levels

| Level | Situation | Action |
|---|---|---|
| Blocker | Runtime requires a higher class-file version than the committed Java level. | Block release or change dependency/minimum Java per policy. |
| Blocker | Linkage/runtime failure in a primary business flow, or security provider fails to initialize. | Investigate and fix before deploy. |
| High | Dependency lacks target JDK support, relies on internal APIs, and runs only with broad workarounds. | Upgrade/replace and reduce workarounds. |
| High | Severe CVE in a runtime dependency with an applicable attack path. | Coordinate security response and choose a compatible patch. |
| Medium | Deprecated non-forRemoval JDK API warnings with available alternatives. | Track and schedule remediation. |
| Investigate | Missing metadata or untested rarely used dependency. | Verify scope, add tests, or log an owner-assigned exception. |

This is an illustrative grouping; concrete severity must reflect business impact, exposure scope, support level, and organizational policy.

## 21. Template Dependency Inventory Report for Migration

A concise report can include:

~~~text
Module/artifact:
Commit/build:
Target JDK:
Minimum supported Java runtime:
Build JDK/compiler toolchain:
Dependency graph identifier:
Artifact checksum:

Direct dependencies:
  - name/version/scope

Transitive dependencies:
  - resolved name/version
  - introduced by ...

Compatibility findings:
  - class-file version mismatch
  - removed/deprecated Java APIs
  - JDK internal/reflection/module issues
  - framework/BOM mismatch
  - native or agent risk
  - security/support risk

Decisions:
  - keep / upgrade / align / exclude / replace / isolate
  - owner / due date / evidence

Validation:
  - build JDK
  - minimum runtime JDK tests
  - target runtime JDK tests
  - integration and binary consumer tests
  - deployment artifact verification

Open blockers and accepted exceptions:
Release readiness:
~~~

Do not mark “compatible” merely because no compile errors appeared. If a dependency has not been checked, record “not yet verified” or state the missing test scope.

## 22. Common Misconceptions

| Misconception | Why It Is Wrong | Approach |
|---|---|---|
| “Only direct dependencies need to be compatible.” | Transitive JARs are also loaded at runtime and may require newer Java. | Inspect the entire resolved runtime graph. |
| “Building with JDK 21 means the app requires Java 21.” | The compiler can target --release 17 artifacts. | Distinguish build JDK, target, and runtime. |
| “Compiling with --release 17 makes every dependency run on Java 17.” | --release does not downgrade bytecode or APIs in external JARs. | Check dependencies and test on a Java 17 runtime. |
| “The latest version is always best.” | It may raise minimum Java or change APIs/frameworks. | Choose a supported version set and test. |
| “Adding an API JAR makes the runtime work.” | Certain technologies need a separate implementation/provider. | Confirm runtime providers and packaging. |
| “dependencyManagement/BOM automatically adds every dependency.” | They mainly manage versions, not add modules in every case. | Check the resolved graph and declare needed dependencies. |
| “Exclusions fix every conflict.” | Removing a JAR can cause missing classes or break binary APIs. | Use exclusions with evidence and integration tests. |
| “Same package means same library generation.” | javax/jakarta and artifact versions can differ in binary names/semantics. | Check actual classes and the framework matrix. |
| “One class in a JAR having bytecode 52 means the JAR supports Java 8.” | Other classes or variants may require a higher level. | Check the whole artifact and runtime. |
| “No jdeps errors means the app is compatible.” | Reflection, native code, dynamic plugins, and behavioral changes can slip through. | Combine static analysis and runtime tests. |
| “Testing on the latest JDK is enough.” | The product may still commit to an older minimum JDK. | Include minimum-supported Java in the CI matrix. |
| “If no error appears locally, production is fine.” | Runtime images, classloaders, and TLS/native differ. | Test the real artifact and deployment topology. |
| “The JAR version in the POM is always the loaded one.” | Mediation, shading, profiles, and classloaders can alter the runtime version. | Cross-check resolved graph and class sources. |
| “On a CVE, immediately force the dependency to a new major version.” | This can cause breaking JDK/API changes. | Evaluate viable patches, exposure, and compatibility. |

## 23. Process for Handling Each Risky Dependency

When dealing with a library whose JDK compatibility is unclear:

1. **Identify the real artifact.** Record groupId, artifactId, version, checksum, and source.
2. **Trace the path.** Use dependencyInsight or dependency:tree to see direct/transitive status and why that version was chosen.
3. **Determine the scope.** Runtime, compile, test, plugin, optional, provided, or native/agent?
4. **Gather Java requirements.** Review release notes, metadata, class-file versions, and framework/BOM info.
5. **Analyze APIs.** Check JDK internals, removed/deprecated APIs, javax/jakarta, JPMS, and reflection.
6. **Evaluate options.** Keep, upgrade, replace, apply controlled override, extract module, or raise minimum Java.
7. **Make the change in the graph.** Keep versions consistent and avoid expanding overrides beyond need.
8. **Rebuild the artifact.** Use the defined wrapper/toolchain and verify real packaging.
9. **Run the matrix.** Minimum JDK, target JDK, and critical integrations.
10. **Record the conclusion.** Store test evidence, decision, owner, security status, and remaining limitations.

If a dependency is only for testing or build-time and does not reside in the deployed artifact, its Java requirement may differ from the product's declared minimum runtime level. Still, it must be compatible with the JDK running tests/builds for the pipeline to operate reliably.

## 24. Conclusion

JDK compatibility of dependencies must be evaluated on **the resolved dependency graph and actual artifacts**, encompassing both direct and transitive libraries. A dependency version can raise minimum Java requirements, change binary APIs, bring in an incompatible provider, use JDK internal APIs, or cause module/classloader conflicts even when application code still compiles.

For safe Java migration, inventory compile/runtime/test/build dependencies, separate the build JDK from minimum runtime Java, verify class-file versions and APIs, align with framework/BOM matrices, trace the exact source of transitive conflicts, and test on both the target JDK and committed minimum JDK. Locking resolved versions, recording compatibility evidence, and rolling out in phases helps curb dependency drift and prevent issues that only surface in production.

**The goal is not merely eliminating warnings in the dependency tree, but achieving a supported, verified, and reproducible set of dependencies across the Java versions the product actually commits to support.**
