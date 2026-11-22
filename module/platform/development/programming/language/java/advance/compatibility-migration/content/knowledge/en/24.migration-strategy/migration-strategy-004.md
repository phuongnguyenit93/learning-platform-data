# Maintaining Parallel Build Capability on Old and New JDKs During the Transition Period

In **Java Advance Compatibility Migration**, upgrading the JDK should not be a one-time switch of **JAVA_HOME** assuming every component has been migrated. Development environments, CI, batch servers, production containers, shared libraries, and consumers may follow different upgrade schedules. A period where **both JDKs are supported together** helps an organization continuously validate changes, rather than discovering failures only when rolling back to the legacy environment is no longer possible.

This lesson belongs to the **Migration Strategy** chapter. It explains how to maintain parallel builds on the baseline JDK and target JDK, control toolchains/bytecode/APIs, structure the CI matrix and runtime tests, manage dependencies, annotation processors, build caches, and variant artifacts, as well as formal criteria for retiring legacy JDK support.

Examples use **JDK 17** and **JDK 21** as an illustrative pair. They are not mandatory choices for every project; use the versions declared in your organization's support policy.

## 1. What Does Parallel Building Actually Mean?

Suppose an application's source code must continue running on both Java 17 and Java 21.

An insufficient requirement:

> The build command succeeds once with Java 17 and once with Java 21.

A much more verifiable requirement:

- The build tool and compiler are explicitly identified for each lane.
- Primary source code is verified against the Java language/API baseline.
- Dependencies do not require a runtime higher than the baseline if publishing a single artifact.
- Test code executes on all still-supported runtimes.
- Generated sources/bytecode do not rely on stale outputs.
- The packaged artifact is launched using the exact target JVM.
- Integration contracts and behavioral changes are verified.
- The pipeline displays each JDK's status separately, with release gates.
- Clear criteria define when the legacy JDK is no longer supported.

### 1.1. Different Layers of Java Versions

| Concept | Meaning | Example |
|---|---|---|
| Build JVM | JVM running the Gradle daemon or Maven | JDK 21 |
| Compiler JDK | Exact `javac` compiling Java sources | `javac` 17 or `javac` 21 |
| Language level | Allowed Java syntax level | Java 17 |
| Platform API level | Permitted Java SE APIs to reference | Java SE 17 |
| Bytecode target | Class-file format readable by minimum JVM | Major 61 |
| Test JVM | JVM running JUnit/integration tests | 17 and 21 |
| Runtime JVM | Actual JVM running the artifact | 17 or 21 |
| Build plugin runtime | JVM on which Gradle/Maven plugins execute | May be the build tool's JVM |
| Agent/processor runtime | JVM or compiler environment for the tool | Not necessarily identical to the application runtime |

**A build using `javac` 21 with `--release 17` is not a build using `javac` 17.** The output may match Java 17 bytecode/API compatibility, yet annotation processors and compiler plugins still run on JDK 21.

### 1.2. Two Different Support Goals

**Model A — one source tree, one artifact running on multiple JDKs:**

~~~text
                    Same codebase
                         |
         +---------------+---------------+
         |                               |
   Build/test JDK 17                Build/test JDK 21
         |                               |
         +---------------+---------------+
                         |
                 Publish JAR target 17
                         |
             +-----------+-----------+
             |                       |
          Runtime 17              Runtime 21
~~~

Under this model, **the minimum runtime remains Java 17**. Do not introduce mandatory Java 21 APIs into shared code until the support policy changes or an isolated architecture is in place.

**Model B — one codebase, two artifact variants:**

~~~text
                    Shared modules
                         |
                 +-------+-------+
                 |               |
           Java 17 variant   Java 21 variant
                 |               |
           Test on 17       Test on 21
                 |               |
         Publish legacy    Publish modern
~~~

Model B enables using Java 21 APIs in the modern variant, but increases build, versioning, maintenance, and testing costs. Both variants must carry distinct **artifact identities** and must never be published under the same coordinates/version with indeterminate contents.

Choose the model before designing the matrix; otherwise, two “green” lanes can still produce two different artifacts without a clear release contract.

## 2. Why Maintaining Two JDKs Is Harder Than Running Two Commands

A modern build spans multiple layers:

~~~text
Source code
    |
    v
Gradle/Maven process
    |
    +--> Build plugins
    |
    +--> javac
    |      |
    |      +--> Annotation processors
    |      +--> Generated sources
    |
    +--> Test launcher/JVM
    |      |
    |      +--> JUnit, Mockito, Byte Buddy, JaCoCo
    |
    +--> Packaging
    |      |
    |      +--> Shaded JAR, WAR, Docker, jlink image
    |
    v
Runtime / Container / Cloud
~~~

Each layer has its own support matrix. For example:

- Older Gradle versions may fail to start on a newer JDK.
- Older Lombok versions may depend on `javac` internal APIs.
- Older Byte Buddy/JaCoCo versions may not yet support the new class-file version.
- An old Maven plugin may only work with the baseline JVM.
- Container images may run a different runtime than CI.
- A transitive dependency gets bumped to Java 21 bytecode.
- A generated class is missing only on clean CI runs.
- Java agents, TLS providers, or JNI libraries are no longer compatible.

Therefore, when a lane fails, properly classify it under **build tool**, **compiler**, **processor**, **test runtime**, **packaging**, or **application runtime**, rather than lumping every error under “JDK migration”.

## 3. Establish the Compatibility Policy from the Start

A support matrix should record:

1. Baseline and target JDKs; vendor/distribution if required.
2. Supported operating systems, CPU architectures, and container runtimes.
3. Minimum Java version of published artifacts.
4. Modules required to support both JDKs.
5. Modules intended only for the target JDK.
6. Gradle/Maven, plugin, JUnit, and processor versions.
7. CI jobs required to stay green at each milestone.
8. End-of-support timeline for the legacy JDK.
9. Criteria for retiring the legacy lane.
10. Rollback, security, and downstream consumer support rules.

Example:

| Attribute | Transition Phase | Post-Cutover |
|---|---|---|
| Min supported runtime | 17 | 21 |
| Source language level | 17 | 21 if approved |
| Target release | 17 | 21 if approved |
| Compiler JDK matrix | 17 and 21 | 21 |
| Runtime test matrix | 17 and 21 | 21 |
| Build tool/plugins | Must support both lanes | Can be upgraded separately per support |
| New JDK-only API | Avoid in shared code | Permitted after cutover |
| Legacy support gate | Required | Closed after sufficient evidence |

This is a **product decision**, not merely a DevOps configuration detail. For public libraries, raising the minimum Java version can be a breaking change.

### 3.1. Assurance Levels Should Be Explicitly Named

- **Compile-supported:** source compiles on the respective JDK.
- **Test-supported:** key test suites pass on that runtime.
- **Runtime-supported:** the artifact is verified when deployed in that environment.
- **Production-supported:** covered by support, monitoring, incident response, and security updates.

Do not declare “supports Java 17 and 21” solely from running one **javac** command; the exact scope must be explicit.

## 4. Understanding `javac --release` Properly

The **javac --release N** option is a crucial tool for compiling source targeting an older Java SE release using a newer `javac`.

Example running with `javac` 21:

~~~bash
javac --release 17 -d out src/example/Main.java
~~~

It constrains source syntax, referenceable Java SE APIs, and class-file target to release 17 within what `javac` supports.

### 4.1. `-source`/`-target` Is Not Equivalent to `--release`

Configuring:

~~~bash
javac -source 17 -target 17 -d out src/example/Main.java
~~~

limits syntax and bytecode, but does not automatically provide the same protection against referencing newer Java SE APIs via a newer compiler JDK.

For projects needing to preserve an older runtime, prefer **--release 17** when supported by the compiler and build tool.

### 4.2. `--release` Does Not Guarantee External Dependencies

Example:

~~~text
app.jar             -> class file major 61
  |
  +--> common.jar   -> class file major 61
  |
  +--> extra.jar    -> class file major 65
~~~

Java 17 can load `app.jar`, yet when a code path touches `extra.jar` with class-file major 65, the Java 17 JVM cannot load that class.

| Java release | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Inspect the **runtime classpath/transitive dependencies** and final artifact, not solely the bytecode of the main module.

### 4.3. `--release` Does Not Make Applications Behave Identically

Two JDKs can still differ in:

- GC/JIT and memory ergonomics.
- TLS, security providers, and disabled algorithms.
- Locale, timezone, and charset behavior.
- Reflection and JPMS encapsulation.
- Garbage collector metrics.
- Runtime exception messages.
- Native libraries and Java agents.
- Framework/driver behavior conditioned on runtime version.

**A green build under `--release 17` does not replace running runtime tests on real Java 17.**

### 4.4. When `--release 17` Cannot Be Maintained

If shared source requires a Java 21-only API or newer syntax, options include:

1. Defer the feature until Java 17 support ends.
2. Isolate it into a Java 21-only module/variant.
3. Use an abstraction with runtime-selected implementations packaged for proper targets.
4. Use a multi-release JAR if appropriate and testing capacity suffices.

Never manually patch the class-file major version to force a Java 21 class to run on Java 17.

## 5. Gradle Toolchains for Two JDKs

Gradle **Java Toolchains** let you select the compiler and runtime launcher for relevant tasks, decoupled from the JVM running the Gradle daemon.

Gradle Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

def buildJdk = providers.gradleProperty('buildJdk')
    .map { it.toInteger() }
    .orElse(17)
    .get()

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(buildJdk)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(buildJdk)
    }
}
~~~

Meaning:

- **buildJdk** selects which toolchain is used.
- **options.release = 17** preserves the Java 17 API/language target.
- **Test.javaLauncher** selects the matching runtime to execute tests.
- The Gradle daemon may run on a different JVM if supported by the Gradle version.
- Toolchains must be pre-installed or configured with an appropriate provisioning mechanism.

Illustrative commands:

~~~bash
./gradlew clean test -PbuildJdk=17
./gradlew clean test -PbuildJdk=21
~~~

On Windows use **gradlew.bat**. The commands merely illustrate the workflow for a real project.

### 5.1. Do Not Confuse the Gradle JVM with the Java Toolchain

Useful commands:

~~~bash
java -version
javac -version
./gradlew -version
./gradlew javaToolchains
~~~

**java -version** in the shell and **./gradlew -version** do not prove which compiler was selected for a given task.

Inside integration tests you can print:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
~~~

Printing directly inside the test process confirms the lane ran on the declared runtime.

### 5.2. Toolchains Do Not Automatically Make Old Gradle Run on Newer JDKs

A Gradle release might support Java 21 as a compiler toolchain while having separate requirements to run the Gradle daemon itself on Java 21. Check the Gradle compatibility matrix for your actual wrapper version.

Other plugins such as Spring Boot, Kotlin, Shadow, or code generators also maintain their own compatibility matrices.

### 5.3. Kotlin DSL Configuration

If the repository uses **build.gradle.kts**, an equivalent variant:

~~~kotlin
plugins {
    java
}

val buildJdk = providers.gradleProperty("buildJdk")
    .map(String::toInt)
    .orElse(17)
    .get()

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(buildJdk))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(buildJdk))
    })
}
~~~

There is no need to maintain both Groovy and Kotlin DSL in the same project. Pick syntax matching your current build and supported Gradle version.

## 6. Gradle Main Sources, Test Sources, and Generated Code

A project may define source sets:

~~~text
src/main/java
src/test/java
src/integrationTest/java
build/generated/sources/annotationProcessor/java/main
build/generated/sources/annotationProcessor/java/test
~~~

Two JDKs can differ in annotation processing, compilation, and test launchers. When adding an `integrationTest` source set, verify the dedicated launcher/configuration for that task.

### 6.1. Be Careful with `annotationProcessor`

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    annotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'

    testCompileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    testAnnotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
}
~~~

Placeholders must be replaced with an actual processor release that supports the compiler JDK in use.

Placing a processor only in **implementation** does not reliably run it in Gradle. Starting with `javac` in **JDK 23**, annotation processing also changed its default behavior: do not rely on implicit classpath discovery without explicit processing configuration.

### 6.2. Do Not Share One Output Directory Across Two Concurrent Builds

Two Gradle commands executing concurrently in the same workspace can contend writing:

~~~text
build/classes/java/main
build/classes/java/test
build/generated/sources/annotationProcessor/java/main
build/test-results/test
~~~

Safer approach: give each CI lane its own workspace or output directory; use properly configured build caching and avoid sharing writable directories.

### 6.3. Clean Builds Still Matter

A processor that fails to run while leftover generated classes from a prior build still exist can keep local builds green. Clean CI checkouts may fail due to missing classes.

To prove compatibility, at least one verification path must produce outputs from a clean state with clear provenance, not relying on stale generated artifacts.

## 7. Maven: Compiling the Same Target with Two JDKs

With Maven, the simplest method is running **mvn clean verify** across two CI jobs with different **JAVA_HOME** values.

Example **pom.xml**:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Versions here illustrate configuration syntax. Verify the actual JDK support matrix for Maven, Compiler Plugin, and Surefire.

Each lane:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

One job uses JDK 17 and the other uses JDK 21. Logging versions directly in CI output aids investigation if tests run on an unexpected JVM.

### 7.1. Maven Toolchains

Maven Toolchains allow selecting the JDK used by toolchain-aware plugins separately from the JVM running Maven itself.

Example configuration in **~/.m2/toolchains.xml**:

~~~xml
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Paths illustrate Unix layouts; Windows or containers use different paths.

Crucially: **not every Maven plugin automatically obeys the compiler toolchain**. Check compiler, Surefire/Failsafe, code generation, and other subprocesses per plugin version.

### 7.2. A Build Running Maven 21 and Compiling for 17 Does Not Prove Runtime 17

If the Maven process runs JDK 21 and the compiler toolchain emits target 17 bytecode, yet Surefire still runs under JDK 21, the lane may miss Java 17 runtime failures.

Test against separate JVMs aligning with your support policy. In many cases, two CI jobs running Maven on JDK 17 and JDK 21 respectively are easier to observe.

### 7.3. Newer Plugins Have Their Own Minimum Java

A newer Maven/Gradle plugin release may require a JVM higher than the baseline JDK. During coexistence, you can:

- Pick a plugin version supporting both environments.
- Run a newer build JVM with toolchains for older compiler/test targets.
- Separate build variants with explicit rules.
- Plan to retire baseline support if it cannot be sustained.

Do not skip an important plugin in the 17 lane and call it a “successful build” if the real release artifact depends on that plugin.

## 8. CI Matrix with GitHub Actions

An example of two independent lanes:

~~~yaml
name: Java JDK compatibility

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21']

    steps:
      - uses: actions/checkout@v4

      - name: Select JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Show Java versions
        run: |
          java -version
          ./gradlew -version

      - name: Test
        run: ./gradlew clean test -PbuildJdk=${{ matrix.java }}
~~~

The matrix JDK value must be passed into the action and Gradle property using CI syntax. In the rendered workflow above, those two spots use GitHub Actions expressions.

**Note:** action versions here illustrate workflow structure. Production CI should follow policies for pinning/verifying third-party actions and verifying supported JDK distributions.

### 8.1. `fail-fast: false`

When one lane fails, **fail-fast: false** lets the other job finish, giving visibility into both baseline and target status. This is valuable during migration: knowing Java 17 passed while Java 21 failed differs from having both jobs abort.

### 8.2. Jenkins, GitLab, Azure DevOps

GitHub Actions is not required. Other CI systems can build the exact same JDK matrix:

- One build job per JDK.
- Separate workspaces.
- Explicit JDK toolchains.
- Identical commits/dependency locks.
- Defined test suites.
- Labeled artifacts.
- Each lane's status wired as a release gate.
- Logs recording the actual JDK used.

### 8.3. Practical Execution Cadence

| Timing | Old JDK | New JDK | Goal |
|---|---|---|---|
| Pull request | Compile + unit smoke | Compile + unit smoke | Catch regressions early |
| Merge/main | Appropriate full tests | Appropriate full tests | Maintain continuous compatibility |
| Nightly | Integration/long-running | Integration/long-running | Deeper verification |
| Release candidate | Packaged runtime smoke | Packaged runtime smoke | Verify final artifact |
| Canary deployment | If still supported | New runtime | SLOs and observability |
| Post-cutover | Per updated policy | Required | Close support window |

Any non-required lane must have an owner and deadline; it cannot stay “optional” indefinitely while product docs still advertise support for that JDK.

## 9. Cross-Testing Compilers and Runtimes

Two typical lanes:

~~~text
javac17 -> runtime17
javac21 -> runtime21
~~~

are insufficient to prove that an artifact built with `javac` 21 and **--release 17** runs on Java 17.

If requiring a single artifact for both runtimes, consider this matrix:

| Compiler | `--release` | Test runtime | Goal |
|---|---|---|---|
| JDK 17 | 17 | JDK 17 | Baseline compile/runtime |
| JDK 21 | 17 | JDK 21 | New compiler and new runtime |
| JDK 21 | 17 | JDK 17 | New artifact running on baseline |
| JDK 17 | 17 | JDK 21 | Baseline artifact running on target |

You do not need to run every combination on every pull request, yet you must know which combinations are genuinely tested and which remain assumptions.

### 9.1. Benefit of the JDK 21 Compile → JDK 17 Runtime Test

It can catch:

- Transitive libraries compiled for Java 21.
- Resource or service provider differences.
- Generated sources/classes using inappropriate APIs.
- Runtime reflection/serialization assumptions.
- Packaging that accidentally includes a higher class version.

If a class file with major 65 ends up inside a target 17 artifact and is loaded on runtime 17, failures occur even though the project used **--release 17**.

### 9.2. Which Artifact Is Selected for Release?

CI may produce:

~~~text
build-17/app.jar
build-21/app.jar
~~~

If the strategy is **one artifact**, only one path must enter the release and be tested on all supported runtimes. Do not let the pipeline publish whichever job finished last under the same filename from a different compiler.

### 9.3. A Build Can Still Run on the Old JDK While Breaking Backward Data Compatibility

A Java 17 app can read Java 17 class files yet fail to understand new messages/events written by a Java 21 app. Build matrices must be paired with **cross-version protocol tests** if both versions access a shared database, queue, or cache.

## 10. Managing Dependencies by Minimum Runtime

A library may bump a major/minor release and change its minimum JDK. Audit:

- Direct dependencies.
- Transitive dependencies.
- Test-only dependencies.
- Annotation processors.
- Maven/Gradle plugins.
- Runtime agents.
- Native/JNI libraries.
- Shaded/fat JAR contents.
- Platform-specific variants.

### 10.1. Example of a Dependency Changing Its Minimum JDK

~~~text
Before:
  core-lib 1.x -> supports Java 17

After:
  core-lib 2.x -> requires Java 21
~~~

If a shared artifact must still run on Java 17, you cannot simply upgrade `core-lib`, keep **--release 17** on the project, and assume everything is safe.

Options:

1. Choose a library version still supporting both JDKs.
2. Split Java 21-only functionality out of the shared artifact.
3. Use an adapter or variant.
4. Change the support policy after legacy consumers are migrated.
5. Inspect dependency locks and the bytecode inside the packaged artifact.

### 10.2. Resolution Graphs Can Differ Between Lanes

Build tools may pick dependency variants based on metadata, attributes, or platform. Two lanes sharing the same source code can resolve different artifacts.

Save dependency graphs for each lane when troubleshooting. If differences are intentional, document them in the release policy; otherwise, normalize them for repeatable builds.

### 10.3. Multi-Release JARs in Dependencies

Some libraries are multi-release JARs: different JDK runtimes load different implementations from the same file. This allows version-specific optimization, yet means **identical JAR checksums do not guarantee identical execution paths**.

Test on real runtimes, especially if dependencies rely on native access, reflection, or newer APIs.

## 11. Annotation Processors: A Fragile Point When Upgrading the Compiler

Common tools:

- Lombok.
- MapStruct.
- JPA metamodel/Hibernate Processor.
- Dagger and dependency injection processors.
- AutoValue, Immutables, or internal generators.
- QueryDSL and other annotation-processing generators.

Processors execute at compile time, distinct from runtime libraries.

### 11.1. Configure Processor Paths Explicitly

Gradle:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    annotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'

    testCompileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    testAnnotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
}
~~~

Placeholders must be replaced with an actual version compatible with the compiler JDK in use.

### 11.2. From JDK 23, Watch Default Activation

`javac` starting in JDK 23 no longer automatically runs annotation processing without explicit processing configuration. If a legacy build relied on implicit classpath scanning, generated classes can vanish after upgrading the compiler.

Solution: configure explicit processor paths/processor lists via the build tool rather than relying on service files appearing incidentally on the dependency classpath.

### 11.3. The JDK Running Processors Is Not `--release`

**`javac` 21 `--release` 17** still executes processors inside the JDK 21 compiler environment. A Lombok version knowing only `javac` 17 internals can fail even with target bytecode 17.

During migration:

- Pick a processor version supporting both compiler 17 and 21.
- Do not confuse **javax.annotation.processing** with the Jakarta Persistence namespace.
- Check processor classpath/module path.
- Run clean builds to purge stale generated artifacts.
- Verify implementations are generated in both lanes.
- Do not treat workarounds opening **jdk.compiler** internals as a long-term solution.

### 11.4. Test Sources Need Processors Too

If test code uses Lombok or generated test fixtures, configure **testAnnotationProcessor** accordingly. Green main compilation does not guarantee test compilation ran annotation processing.

## 12. Test Agents, Coverage, and Bytecode Tools

A newer JDK can break the testing pipeline in bytecode-handling tools rather than in Java source code.

| Tool | Risk When Changing JDK |
|---|---|
| Mockito | Mock maker/inline instrumentation/agent compatibility |
| Byte Buddy | Class-file version, runtime instrumentation |
| JaCoCo | Coverage engine does not understand newer bytecode |
| JUnit engine/launcher | Plugin or discovery mismatch |
| PowerMock/legacy mocking | Relies on class loaders and JDK internals |
| Java agents/APM | Attach, bytecode transform, module access |
| Testcontainers | Container engine/JDK/image/runtime config |
| JNI/native test libraries | OS architecture, binary dependencies |

### 12.1. A Class-File Error Is Not Necessarily a Source Error

If a stack trace says the coverage tool cannot parse a new class-file major version, upgrade the coverage tool/ASM dependency properly. Adding **--add-opens** does not fix an outdated bytecode parser.

### 12.2. Test Execution Differs from Test Compilation

An application might compile for Java 17 on both toolchains yet fail when testing on Java 21 due to:

- Module encapsulation.
- TLS/security provider behavior.
- Different reflection exceptions.
- Deprecated/removed runtime features.
- Changed default GC or charset.
- Libraries supporting Java 17 but not Java 21.

Distinguish tool failures from application behavior failures via stack traces and representative tests.

## 13. Caches, Generated Outputs, and Build Reproducibility

Running two parallel builds requires careful management of output state and caches.

### 13.1. Causes of Unreliable Results

- Both lanes writing to the same **build/** or **target/** directory.
- Cache keys not encoding JDK/toolchain.
- Generated code left over from a previous build.
- A plugin embedding timestamps/random metadata in artifacts.
- Unpinned/unlocked dependencies resolving differently across runs.
- Tests downloading uncontrolled external data.
- Maven local repository receiving overwritten snapshot artifacts mid-run.
- A task reading environment variables without declaring them as inputs.

### 13.2. Isolate Workspaces/Outputs

Prefer running each CI matrix job in an isolated workspace. Sharing **read-only dependency caches** or properly keyed build-tool caches differs sharply from two invocations overwriting the same generated/class outputs.

### 13.3. Byte-for-Byte Reproducibility Differs from Behavioral Compatibility

Two JDK compilers can emit byte-level different classes/JARs despite identical **--release 17**. A checksum difference does not prove faulty behavior.

Separate the goals:

- **Reproducible build:** fixed inputs/toolchains yield identical artifacts per project standards.
- **Cross-JDK compatibility:** the artifact preserves API/behavior and runs across supported runtimes.
- **Supply-chain integrity:** the artifact has verifiable provenance, dependency checksums, and trusted sources.

Do not demand byte-identical outputs across two JDKs without explicit design and justification.

## 14. Single Artifact, Two Variants, or Multi-Release JAR?

### 14.1. Single Artifact Targeting Java 17

Advantages:

- Consumers use the same Maven/Gradle coordinates.
- Fewer variants and less deployment confusion.
- Simpler version/SBOM management.
- Testable across both Java 17 and Java 21.

Limitations:

- Cannot call Java 21 APIs directly in shared code.
- Transitive dependencies must support Java 17.
- Cannot exploit certain newer features without isolation.

### 14.2. Two Artifacts

Example:

~~~text
my-lib-2.0-java17.jar
my-lib-2.0-java21.jar
~~~

Illustrative names; real repositories may use classifiers or distinct artifact coordinates.

Publish clearly:

- Variant naming and selection.
- Minimum JDK for each artifact.
- Binary/public API compatibility across variants.
- Differing dependency graphs.
- Backport/security policies.
- Dedicated CI tests.
- Release notes and how consumers migrate.

Never publish two artifacts with different contents under the exact same identity/version without distinguishing them.

### 14.3. Multi-Release JAR

**Multi-release JAR** lets one JAR carry versioned classes for different JVMs:

~~~text
library.jar
  META-INF/MANIFEST.MF
  com/example/Feature.class
  META-INF/versions/21/com/example/Feature.class
~~~

Manifest requires:

~~~text
Multi-Release: true
~~~

Base classes must be Java 17 compatible; Java 21 can select the version 21 implementation per MRJAR rules.

However, MRJAR increases complexity:

- Differing packaging and compiler targets.
- Public API consistency.
- Static analysis and code generation.
- Classloading/reflective behavior.
- Dependency compatibility.
- Testing on every real runtime.

Adopt only with clear technical rationale and sufficient maintenance capacity.

## 15. Container Deployment and Runtime Images

CI might compile with Java 17 yet package the artifact into a Java 21 Docker image. Those are two different things.

Example Java 17 runtime:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

For Java 21, swap the base image for a controlled Java 21 runtime image.

In production, pin base images by version/digest alongside a security update policy rather than relying solely on floating tags.

### 15.1. Testing the Final Artifact Inside the Real Image

Steps:

1. Build the artifact per release policy.
2. Package into the exact runtime image.
3. Start the container.
4. Confirm **java.version** inside the running process.
5. Run health/smoke/integration tests.
6. Verify agents, JVM flags, and module availability.
7. Check CPU/memory cgroups and GC.
8. Save artifact/image digests as evidence.

**`java -version`** on the CI host does not verify the Java runtime inside the container.

### 15.2. Minimal `jlink` Images

A custom **jlink** runtime image may omit modules present in a full developer JDK. During migration, test against the final runtime image rather than only a full JDK.

This matters for reflection, XML, management, JFR, or components relying on specific modules.

## 16. Runtime Behavior: A Newer JDK Can Change Test Outcomes

A project targeting Java 17 might not produce identical results on Java 17 and Java 21.

### 16.1. Security and TLS

Inspect HTTPS/mTLS, truststores, JDBC TLS, and partners using legacy ciphers. Upgrading the JDK can change supported algorithms or security defaults.

Do not arbitrarily relax TLS/security policies just to turn a CI target green; classify whether changes are intentional and evaluate actual impact.

### 16.2. Locale/Charset/Timezone

Do not let tests depend on default locale, timezone, or charset when business contracts demand deterministic values.

Example:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.util.Locale;

var charset = StandardCharsets.UTF_8;
var zone = ZoneId.of("UTC");
var locale = Locale.ROOT;
~~~

Code using explicit settings where appropriate reduces noise between the two lanes.

### 16.3. GC/JIT/Performance

Do not compare raw GC counts between two JDKs/collectors and conclude an application improved or degraded. Measure p95/p99 latency, throughput, CPU, heap, and business SLOs on equivalent workloads.

### 16.4. Native/JNI and Profilers

An application targeting Java 17 can still fail on a Java 21 runtime due to incompatible JNI libraries/Java agents. Inventory and test native binaries/agents bundled with the artifact, not just the Java JAR.

## 17. Schemas and Protocols When Two Runtimes Coexist

Parallel builds commonly support a **rolling migration**:

~~~text
App A / JDK 17 ------+
                     |
                     +--> Shared DB / Queue / Cache
                     |
App B / JDK 21 ------+
~~~

Both can write and read data inside the same system.

Mandatory questions:

- Are ORM entities compatible with the shared schema?
- Does a newer JSON serializer omit fields expected by old consumers?
- Does Producer B emit enum values unknown to A?
- Can Consumer B read older messages already sitting in the queue?
- Does a new writer produce data that old readers fail to parse?
- Is rolling back to App A still safe?
- Does Code B use newer APIs while preserving the older protocol?

If schema changes are needed, apply **expand-before-contract**: add new structures, keep read/write compatibility, backfill and reconcile, and remove old fields only once no consumer depends on them.

**A build matrix does not replace cross-version data compatibility tests.**

## 18. Risk-Based Testing Matrix

A test plan may include:

| Test layer | Java 17 | Java 21 | Rationale |
|---|---|---|---|
| Compile main source | Yes | Yes | Compiler/toolchain |
| Compile test source | Yes | Yes | Test code/APT |
| Unit tests | Yes | Yes | Behavioral regression |
| Integration DB/ORM | Yes | Yes | Driver, runtime behavior |
| HTTP/JSON contract | Yes | Yes | Serializer/protocol compatibility |
| Messaging | Yes | Yes | Old/new payloads |
| Final artifact smoke | Yes | Yes | Runtime classpath and packaging |
| Agent/coverage | Yes | Yes | Bytecode instrumentation |
| Container smoke | Per support | Per support | Real image/runtime |
| Performance baseline | As needed | As needed | Post-migration SLO |
| Cross-version producer/consumer | Yes | Yes | Coexistence |
| Consumer precompiled artifact | If needed | If needed | Binary compatibility |

Not every stress test must run on every PR, yet every advertised capability must have corresponding tests and a release gate.

### 18.1. Contract Tests Against Unrebuilt Consumers

For shared libraries, a previously compiled consumer can hit **NoSuchMethodError** or **IllegalAccessError** when swapping the library. Building the library source on two JDKs does not catch all such errors.

When binary compatibility must be preserved, keep an old consumer artifact and run it against the new library on supported runtimes.

### 18.2. Flaky Tests

Different JDKs can shift scheduling/timing, exposing data races or tests hardcoded to tight timeouts.

Do not fix this by blindly disabling flaky tests. Analyze concurrency assumptions, test isolation, external dependencies, and environment wait budgets.

## 19. When a Lane Goes Red: Ordered Investigation

| Symptom | Likely Cause | What to Check |
|---|---|---|
| Gradle daemon fails to start | Gradle release does not support JDK | Gradle/JDK matrix |
| Maven plugin fails | Plugin minimum JVM mismatch | Maven JVM, plugin version |
| Compilation error on Java API | Source uses API outside `--release` | Source level, API baseline |
| `UnsupportedClassVersionError` | Dependency/class major newer than runtime | Runtime classpath |
| Generated mappers missing | Processor path/activation | Clean build/APT config |
| `IllegalAccessError` in Lombok | Internal `javac` API changed | Processor/JDK versions |
| Mockito/JaCoCo failure | Bytecode/agent support | Test tool versions |
| `InaccessibleObjectException` | Reflection/JPMS | Module/package/caller |
| Test fails on Java 17 yet passes on Java 21 | Dependency/runtime needs newer JDK | Bytecode/API and integration |
| Test fails on Java 21 yet passes on Java 17 | Runtime behavior or outdated framework | Cause chain |
| CI passes yet container fails | Image JDK/modules/agents differ | Container inspection |
| Local passes, CI clean fails | Stale build outputs/caches | Generated files, cache isolation |
| JSON differences | Serializer/framework behavior | Contract/golden payloads |

Procedure:

1. Record the lane/commit and build artifact.
2. Verify the build JVM, compiler JDK, and test JVM.
3. Identify the failing phase.
4. Read the stack trace to locate the owning component.
5. Inspect compile flags, dependency resolution, and processors.
6. Verify clean caches/outputs.
7. Check runtime image/agents.
8. Fix at the right layer.
9. Re-run all affected lanes.
10. Document evidence and residual risk.

Never drop a lane merely because the new lane turned green. Retiring support requires an independent release gate.

## 20. Release Gates During the Transition

### Gate M0 — Baseline

- Legacy JDK and build tool versions documented.
- Dependencies/processors/test agents inventoried.
- Currently deployed artifact has checksum/provenance.
- Test baseline is reproducible.
- Support policy documented.

**Go:** baseline is clear enough for comparison.

### Gate M1 — Build Tool Readiness

- Gradle/Maven and plugins run as planned.
- Compiler/toolchain targets exist.
- No plugins block the newer JDK.
- Major processor/compiler internal issues resolved.

**Go:** infrastructure can run two lanes.

### Gate M2 — CI Matrix

- Two independent lanes.
- Correct build flags/source/API targets.
- Test runtimes verified.
- Clean generated outputs.
- Dependency graphs and caches controlled.
- Results from both lanes clearly visible.

**Go:** trustworthy signals exist for both legacy and new JDKs.

### Gate M3 — Runtime Compatibility

- Packaged artifact exercised on supported runtimes.
- Integration/contract tests pass.
- Agents/TLS/native dependencies checked.
- Observability and SLO baseline ready.
- Rollback plan in place.

**Go:** release is ready for canary.

### Gate M4 — Coexist/Rollout

- Old and new apps can concurrently read/write required data.
- No breaking schema/protocol changes during the overlap window.
- Canary metrics and error rates are stable.
- Incident owner and runbook assigned.
- Rollback verified within valid bounds.

**Go:** traffic can shift without losing legacy version support.

### Gate M5 — Ending Legacy JDK Support

- No supported runtimes/clients still need the baseline.
- Batch jobs, scheduled jobs, and recovery tooling upgraded.
- Consumer owners sign off.
- Legacy rollback window closed or alternatives approved.
- Minimum Java version docs updated.
- Release team approval granted.

**Go:** legacy build lane may be removed and target release raised if desired.

## 21. When Should You Stop Maintaining Two Builds?

Parallel builds incur costs:

- Doubled or substantially higher CI compute.
- Dependencies pinned to versions supporting the old JDK.
- Delayed adoption of newer Java features.
- Harder plugin/test tool upgrades.
- More configuration variants to maintain.
- Potential discrepancies between compiler and runtime.
- Risk of one lane becoming neglected.

Therefore, set an **end date and exit criteria**. Do not keep both indefinitely just because it feels “safer”, yet do not cut prematurely while consumers still have published support commitments.

### 21.1. Template for Closing the Baseline

~~~text
Gate: DROP_JDK_17_SUPPORT

[ ] No supported production JVMs on JDK 17
[ ] No library consumers require Java 17
[ ] Batch/recovery tools migrated
[ ] Rollback window closed or alternative approved
[ ] Build plugins/agents support new baseline
[ ] Target runtime SLO accepted
[ ] Release notes and API docs updated
[ ] Consumer owners signed off

Decision: GO / NO-GO / PENDING
Owner:
Evidence:
Date:
~~~

**PENDING does not mean GO.** If a public library previously committed to Java 17, raising the minimum runtime to Java 21 must be announced as a potentially breaking change for consumers.

## 22. Common Mistakes

### 22.1. Only Changing `JAVA_HOME`

A Gradle task may use another toolchain or a container may run another JDK. **Fix:** verify each process/compiler/test runtime.

### 22.2. Using `-target 17` Instead of `--release 17`

Code may reference Java APIs newer than the target. **Fix:** use `--release` where appropriate and audit dependency APIs.

### 22.3. Compiling Only with JDK 21

There is no proof the Java 17 runtime still runs it. **Fix:** execute the artifact on real Java 17.

### 22.4. Using Java 21 APIs in Shared Code While Still Supporting Java 17

Source fails to compile or breaks on the runtime. **Fix:** defer, isolate into a variant, or introduce an abstraction.

### 22.5. Upgrading Test Agents Too Late

Old Mockito/Byte Buddy/JaCoCo versions may fail on newer class files. **Fix:** verify the tool matrix before upgrading the JDK.

### 22.6. Not Declaring Annotation Processors Explicitly

Processors may silently stop running on newer compilers. **Fix:** configure explicit processor paths, upgrade versions, and run clean builds.

### 22.7. Mixing Outputs from Two JDKs

Generated files/classes overwrite each other. **Fix:** separate workspaces and outputs, and isolate caches.

### 22.8. Demanding Identical Hashes Across Two JDKs

A build can be behaviorally correct while emitting byte-level different artifacts. **Fix:** distinguish reproducibility from compatibility, and pin specific release artifacts.

### 22.9. Ignoring the Runtime Image

CI host runs JDK 17 while the Docker image runs JDK 21, or vice versa. **Fix:** test the final image.

### 22.10. Leaving the Legacy Lane Optional Forever

Regressions can linger for weeks without blocking releases. **Fix:** enforce required checks or time-bound owned exceptions.

### 22.11. Neglecting Cross-Version Data Contracts

Two Java applications on different JDKs share a database/queue yet misinterpret each other's schemas. **Fix:** test the producer/consumer matrix and apply expand-and-contract.

### 22.12. Deleting the Legacy Lane Once New Canary Looks Good

Batch jobs, SDK clients, or rollback paths may still require the old JDK. **Fix:** close the legacy lane only with evidence and approvals.

## 23. Compatibility Report Template for a Release

~~~text
Release:
Commit:
Build system + version:
Baseline JDK:
Target JDK:
Minimum supported runtime:
Source/API target:
Artifacts published:

Lane 17:
  Build JVM:
  Compiler JDK:
  Test JVM:
  Compile:
  Unit tests:
  Integration tests:
  Package:
  Runtime smoke:
  Known deviations:

Lane 21:
  Build JVM:
  Compiler JDK:
  Test JVM:
  Compile:
  Unit tests:
  Integration tests:
  Package:
  Runtime smoke:
  Known deviations:

Cross-runtime artifact tests:
Dependency/processor compatibility:
Java agents/native libraries:
Container images:
Data/protocol compatibility:
Observability/SLO:
Rollback plan:
Release gate:
Owner approvals:
Evidence links:
~~~

Such a report separates technical failures from business decisions regarding support scope while creating evidence to formally retire the baseline JDK.

## 24. Completion Checklist

### Policy and Architecture

- [ ] Locked in baseline/target JDKs and minimum supported runtime.
- [ ] Decided between a single artifact or separate variants.
- [ ] Identified which modules fall within dual-JDK scope.
- [ ] Assigned an owner and exit criteria for coexistence.
- [ ] Established release/rollback policies.

### Build and Dependencies

- [ ] Gradle/Maven versions genuinely support the matrix.
- [ ] Compiler JDK/test runtime selected explicitly.
- [ ] `--release` and API target match the baseline.
- [ ] Verified bytecode/runtime support for dependencies.
- [ ] Processors declared explicitly.
- [ ] Generated outputs are not stale.
- [ ] Plugin and build-tool minimum JDKs do not break the baseline.
- [ ] Writable outputs are not shared across lanes.

### Testing and Release

- [ ] CI runs both lanes with clear labels and logs.
- [ ] Required checks align with the support policy.
- [ ] Unit/integration/contract tests match each runtime.
- [ ] Cross-runtime testing exists when publishing a single artifact.
- [ ] Packaged JAR/container executed directly on baseline and target.
- [ ] Mockito/Byte Buddy/JaCoCo/agents are compatible.
- [ ] TLS, native libraries, JPMS, and framework behavior accounted for.
- [ ] Artifacts carry clear provenance/versioning without accidental publishing.
- [ ] Canary, metrics, rollback, and release evidence in place.

### Closing Migration

- [ ] No consumers/batch jobs/recovery tools require the old JDK.
- [ ] Data/protocol contracts remain supported within scope.
- [ ] Support docs and release notes updated.
- [ ] Respective owners approved closing the legacy lane.
- [ ] Target release/API baseline raised only after the formal gate.

## 25. Reference Documentation

When applying this in real projects, check the documentation for your exact JDK and tools:

- **javac --release:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java class-file format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Gradle Java Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html
- **Gradle Java Compatibility:** https://docs.gradle.org/current/userguide/compatibility.html
- **Maven Compiler Plugin:** https://maven.apache.org/plugins/maven-compiler-plugin/
- **Maven Toolchains Plugin:** https://maven.apache.org/plugins/maven-toolchains-plugin/
- **Maven Surefire Plugin:** https://maven.apache.org/surefire/maven-surefire-plugin/
- **Maven Failsafe Plugin:** https://maven.apache.org/surefire/maven-failsafe-plugin/
- **JDK 23 javac / annotation processing:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **JEP 238 — Multi-Release JAR Files:** https://openjdk.org/jeps/238
- **GitHub Actions setup-java:** https://github.com/actions/setup-java
- **Java Migration Guide:** https://docs.oracle.com/en/java/javase/21/migrate/

Tool support and plugin behavior can change across releases. Do not copy an illustrative version into production without verifying the support matrix and project security policy.

---

**Conclusion:** Maintaining parallel build capability across old and new JDKs is a **continuously verified compatibility contract**. Explicitly separate the build JVM, compiler JDK, Java API/bytecode target, test runtime, and deployment runtime. Configure independent toolchains and CI matrices, use **--release** properly, inspect dependencies/annotation processors/agents, prevent generated outputs or caches from masking errors, and run the final artifact across all still-supported runtimes. Retire the legacy lane only once evidence confirms consumers, batch jobs, production, and rollback no longer need it.
