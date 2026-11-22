# Compatibility Matrix Between Build Tool Versions and JDKs

When migrating Java from JDK 8 or 11 to JDK 17, 21, 25, or newer versions, a project can fail even before executing a single line of source code: the Gradle daemon fails to start, a Maven plugin requires a newer Java version, Groovy or ASM cannot read the class-file version, the compiler generates bytecode beyond the target runtime, or tests run on a different JDK from the production application.

The root cause often lies in treating “the project uses Java 21” as a single configuration. In reality, **the build tool, compiler, test JVM, plugins, product runtime, and CI toolchains can use different Java versions**. They must be compatible with one another, though they do not necessarily have to be identical.

This lesson builds a **compatibility matrix between Maven/Gradle and the JDK**, explains how to read official matrices, how to lock configuration for reproducible builds, and an upgrade workflow with rollback capability. The version milestones in the matrix are reference snapshots as of **November 2026**, not a guarantee that every plugin in a project works with that combination. Always cross-check the release notes and compatibility matrix of the exact build tool version, JDK vendor/build, and plugins in use.

## 1. A Java Project Has Multiple JDK Roles

Look at the diagram of a real build:

~~~text
             Developer / CI / Build agent
                         |
             +-----------+-----------+
             |                       |
       Maven launcher           Gradle Wrapper
             |                       |
         Maven JVM               Gradle JVM/Daemon
             |                       |
             +-----------+-----------+
                         |
                Build lifecycle / plugins
                         |
       +-----------------+-----------------+
       |                 |                 |
  Java compiler      Test JVM         Javadoc/Codegen
  JDK 17/21/...      JDK 17/21/...   JDK or separate plugin
       |
   class files / JAR
       |
       v
 Application runtime in staging/production
 JDK 17/21/... and corresponding dependency graph
~~~

There may also be JDKs for the Kotlin compiler daemon, annotation processors, bytecode instrumentation, native image, and analysis tools. In all cases, distinguish the primary roles:

| Role | Meaning | Common Configuration |
|---|---|---|
| **Build tool runtime** | JVM running Maven core or the Gradle daemon | `JAVA_HOME`, Gradle daemon JVM criteria, IDE settings |
| **Compiler JDK** | Actual `javac` generating class files | Gradle toolchain, Maven toolchains, compiler plugin |
| **Language/API target** | Syntax, class-file format, and Java SE APIs the artifact is allowed to use | `--release`, compiler options |
| **Test JVM** | JVM executing unit/integration tests | Gradle `Test.javaLauncher`, Maven Surefire/Failsafe toolchain |
| **Application runtime** | JVM running the released artifact | Container image, service runtime, Kubernetes deployment |
| **Plugin runtime** | JVM in which a plugin executes or compilers/services launched by the plugin | Plugin version, Gradle/Maven API, JDK |
| **CI/IDE JVM** | Environment launching the build locally and on runners | GitHub Actions/Jenkins tool configuration, IDE Gradle JVM |

A build running with Gradle 9 on JDK 21 can **compile Java 17 code** using toolchain 17 and test the artifact on JDK 17. Similarly, Maven running on JDK 21 can invoke a JDK 17 compiler via toolchains. Conversely, Maven reporting Java 21 in `mvn -version` **does not** prove the compiler plugin or test runner also uses Java 21 when toolchains are configured.

### 1.1. Compatibility Relationships to Verify

A practical matrix must answer several questions:

1. **Does the build tool run on the chosen JDK?**
2. **Can the build tool locate and drive the target JDK toolchain?**
3. **Do plugins support that build tool version?**
4. **Do plugins support the class-file format and APIs of that JDK?**
5. **Does the compiler produce artifacts matching the declared runtime baseline?**
6. **Do tests run on both the lowest JDK and the newest JDK that must be supported?**
7. **Do runtime dependencies have bytecode and behavior compatible with the deployment JDK?**

If you only verify question 1, the outcome may be “Gradle starts up” while `compileJava` or `test` still fails. If you only verify compilation, the code can still throw `UnsupportedClassVersionError` or `NoSuchMethodError` in production.

## 2. Official Gradle Matrix: Distinguishing Toolchains from Gradle Runtime

Gradle has **two important Java compatibility columns**:
- **Support for toolchains:** the first Gradle version supporting use of a given Java JDK via the toolchain mechanism to execute suitable tasks.
- **Support for running Gradle:** the first Gradle version verified to **run Gradle itself** on the corresponding Java JVM.

The two columns can differ. For example, Gradle 8.4 supports Java 21 via toolchains, whereas **Gradle 8.5 is required to run Gradle on Java 21**.

### 2.1. Gradle – Java Matrix (November 2026 Reference)

The table below is drawn from the [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) page, where relevant milestones must be read against the exact release version at deployment time:

| Java/JDK | Minimum Gradle supporting **toolchain** | Minimum Gradle supporting **running Gradle** | Notes |
|---:|---|---|---|
| 8 | N/A in historical toolchain table | 2.0; Gradle 9 daemon does not support JDK 8 | Legacy builds; do not select JDK 8 as the Gradle daemon on Gradle 9 |
| 11 | N/A in historical toolchain table | 5.0; Gradle 9 daemon does not support JDK 11 | Can continue targeting Java 11 using a suitable JDK |
| 17 | 7.3 | 7.3 | Good milestone to begin considering an upgrade from JDK 11 |
| 18 | 7.5 | 7.5 | Check plugins and build scripts |
| 19 | 7.6 | 7.6 | Check plugins and build scripts |
| 20 | 8.1 | 8.3 | Toolchain earlier than Gradle runtime |
| 21 | 8.4 | 8.5 | Common milestone when upgrading JDK 17 → 21 |
| 22 | 8.7 | 8.8 | Toolchain earlier than Gradle runtime |
| 23 | 8.10 | 8.10 | Both milestones coincide |
| 24 | 8.14 | 8.14 | Do not extrapolate from Java 23 support |
| 25 | 9.1.0 | 9.1.0 | Requires corresponding Gradle 9.x |
| 26 | 9.4.0 | 9.4.0 | Requires corresponding Gradle 9.x |
| 27 | 9.8.0 | 9.8.0 | Verify JDK 27 and plugins in the concrete release |

**Understanding N/A properly:** this is the compatibility table's notation in the toolchains column for older JDKs; it does not mean newer Gradle cannot compile code targeting 8/11. Support for compiling/testing with toolchains also depends on the task, discoverable JDKs, and running Gradle version; read the notes in the documentation for that specific version.

**Important Gradle 9 constraint:** starting with Gradle 9.0, **the Gradle daemon requires JVM 17 or newer**. This does not force application artifacts to run on Java 17; Gradle can use toolchains/`--release` to produce code supporting older Java versions when the build and plugins allow. Certain client/wrapper components have different JVM requirements from the daemon, so do not draw conclusions solely by inspecting the executable wrapper.

The milestones in the table reflect **Gradle core support levels**. A Spring Boot plugin, Kotlin Gradle plugin, Android Gradle plugin, annotation processor, or code quality plugin may require a newer Gradle version, an older one, or support only a specific range. Therefore, the combination “Gradle core supports Java 25” does not yet prove the product's entire build supports Java 25.

### 2.2. Examples of Wrong and Right Gradle/JDK Choices

**Scenario A:** The project still uses Gradle 7.6 while setting `JAVA_HOME` to JDK 21.

- Gradle 7.6 is not in the official range supporting running on Java 21.
- `./gradlew --version` or project configuration may fail due to Gradle/Groovy/class-file support.
- Fix by upgrading the Gradle Wrapper to a release supporting **running on Java 21** (starting at 8.5), and upgrading plugins accordingly.
- Do not merely set `sourceCompatibility = 21`, because compiler configuration does not resolve Gradle's own runtime.

**Scenario B:** You want to compile with JDK 21 while Gradle 8.4 runs on JDK 17.

- Gradle 8.4 supports Java 21 via toolchains.
- The Gradle runtime stays on JDK 17 while the compiler is selected from JDK 21.
- This is valid for tasks/toolchains supported by that Gradle version.
- Inspect the test JVM and production runtime separately; do not assume tests run on 21 merely because the compiler uses 21.

**Scenario C:** The project uses Gradle 9 and the app must run on Java 11.

- The Gradle daemon runs on JDK 17+.
- Java sources can be compiled with release 11 if the JDK compiler and plugins support it.
- Tests must run on Java 11 if that is the supported baseline.
- If a dependency contains Java 17 bytecode or uses APIs available only on JDK 17, the artifact still fails on Java 11 even though project source targets 11.

### 2.3. The Matrix Is Not a Future Prediction

How columns are published can change as new Gradle versions release. For newly released or early-access JDKs, **Gradle may support using them as toolchains before supporting running the daemon on them**. Do not extrapolate from trends in earlier milestones. Use the table for the **exact Gradle version** pinned by the wrapper as your verification source and update migration records whenever changing versions.

## 3. Apache Maven – JDK Matrix: Different from Gradle

Maven does not publish a combined “toolchains vs running Maven” table in the same style as Gradle. What must be separated:
- **Maven core** requires a minimum JDK to run `mvn`.
- **Maven plugins** are released independently from Maven core and carry their own Maven/JDK requirements.
- **Toolchains** allow Compiler, Surefire, Javadoc, and toolchain-aware plugins to use a different JDK from the JVM running Maven.
- **The JDK release target** can be lower than the JDK running Maven/`javac`.

### 3.1. Maven Branch Matrix (November 2026 Reference)

| Maven Branch | Minimum JDK to Run Maven | Migration Significance |
|---|---|---|
| Maven 3.9.x | Java 8 | Can run on newer JVMs when plugins/dependencies are compatible; does not automatically guarantee plugins support every newer JDK |
| Maven 3.10.x | Java 8 | Newer Maven 3 branch; still must verify plugins and transport |
| Maven 4.0.0 RC (pre-GA at reference time) | Java 17 | Major Maven core transition; check plugin compatibility and readiness before adopting in production |

According to [Apache Maven Releases History](https://maven.apache.org/docs/history) and [Apache Maven Download](https://maven.apache.org/download.cgi), recent releases of the Maven 3 branch have a Java 8 JDK baseline; the Maven 4 RC branch requires 17+. **Maven 3 being able to run on JDK 21 does not automatically mean every plugin originally written for JDK 8 runs properly on JDK 21.**

Do not invent a matrix like “Maven 3.9 supports up to Java X, Maven 3.10 supports up to Java Y” when Maven core docs make no such promise. Actual outcomes depend on:
- The JVM running Maven.
- Minimum Maven Plugin API and each plugin's dependencies.
- The JDK used by the compiler/tests/instrumentation.
- The JDK/bytecode of project libraries and plugins.
- Frameworks, build extensions, and the operating system.

### 3.2. Do Not Assume Maven 4 Is Just Maven 3 with a New Version Number

Maven 4 brings changes to core/model/CLI/API, and moving from Maven 3 requires its own migration documentation. A plugin might work with Maven 3.9 yet not support Maven 4 RC; a core extension or custom plugin may rely on older Maven APIs.

Therefore, for a JDK upgrade task, decide whether a major Maven upgrade is needed in the same wave. If Maven 3.x already supports the target JDK and plugins are sufficiently modern, upgrading to Maven 4 at the same time can unnecessarily expand the change surface.

### 3.3. Maven Wrapper and the Actual Maven Version

If the project has `mvnw`/`mvnw.cmd`, use the wrapper rather than a globally installed Maven. Inspect the wrapper configuration and the version it downloads, not just `mvn -version` on the local machine.

~~~bash
./mvnw -version
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
~~~

`mvn -version` and `./mvnw -version` can report **two different Maven versions**. Record them separately when building the inventory. The wrapper pins the Maven distribution yet does not automatically pin JDKs, plugins, dependencies, or truststores.

## 4. A More Complete Matrix: Core, Plugins, Compiler, Tests, and Runtime

The Gradle/Maven ↔ JDK matrix is only the outer layer. In a real Java project, establish a decision table across these axes:

| Axis | Example Value | What to Confirm |
|---|---|---|
| Build tool | Gradle 9.x or Maven 3.9/3.10 | Does it support the JVM running the build? |
| Build runtime | Temurin JDK 21 | Do the daemon/Maven core use the exact binary? |
| Java compiler | JDK 21 toolchain | Does the compiler plugin pick the right JDK? |
| Java SE target | `--release 17` | Does it avoid accidentally calling Java 21 APIs? |
| Unit tests | JDK 17 | Does the artifact work on the baseline? |
| Integration tests | JDK 17 and JDK 21 | Are runtime, TLS, DB drivers, and module system working properly? |
| Framework/plugins | Spring Boot, Kotlin, JaCoCo, annotation processors | Do versions support the build tool/JDK/class-file target? |
| Application runtime | JDK 17 or 21 image | Are bytecode/dependencies and runtime settings compatible? |
| Artifact | JAR/WAR/container | Do packaging, manifest, and classpath avoid pulling wrong libraries? |
| CI agent | Linux/Windows/macOS | Are toolchains/JDKs present for the right vendor/architecture? |

### 4.1. Tool Plugins Have Independent Lifecycles

Common plugins to verify independently:
- **Gradle plugins:** Java/Kotlin/Groovy/Scala, Spring Boot, Android Gradle Plugin, protobuf, Shadow, SpotBugs, Checkstyle, JaCoCo, OpenRewrite.
- **Maven plugins:** Compiler, Surefire, Failsafe, Javadoc, Shade, Enforcer, Toolchains, JaCoCo, Dependency, WAR/JAR plugin.
- **Compiler integrations:** Lombok, MapStruct, Dagger, annotation processors, Kotlin KAPT/KSP, Error Prone.
- **Runtime/codegen tools:** Byte Buddy, ASM, Mockito, test engines, OpenAPI/gRPC generators, Kotlin compiler.

A build plugin can fail before compiling application source, or fail only upon encountering class files from a newer JDK. When upgrading the JDK, pin or upgrade each plugin to a declared compatible version; do not blindly track `latest.release`.

### 4.2. Spring Boot and Android Add Extra Constraint Layers

A project using the Spring Boot plugin has **at least three matrices**:
1. The Java baseline of the Spring Boot version.
2. Gradle/Maven versions supported by the Spring Boot plugin.
3. The JVM running Gradle/Maven and the JDK toolchain.

Android projects add the matrix of the Android Gradle Plugin, Gradle, and the JDK running AGP; this cannot be inferred from Gradle core alone. When building an Android build matrix, obtain the compatibility policy of the exact AGP version in use.

A combination should only be marked “supported” when **all intersecting constraints are satisfied**.

## 5. Checking Actual JDKs and Build Tools in the Project

Do not start editing `pom.xml` or `build.gradle` before completing an inventory.

### 5.1. Gradle

On Linux/macOS:

~~~bash
./gradlew --version
java -version
javac -version
echo "$JAVA_HOME"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
java -version
javac -version
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
~~~

`./gradlew --version` reveals the Gradle distribution and the JVM it picked. If using Gradle daemon JVM criteria or custom IDE settings, check **the JVM of the daemon executing the build**, not merely the client/wrapper. On modern Gradle versions, you can list discovered JDK toolchains:

~~~bash
./gradlew javaToolchains
~~~

If the `javaToolchains` task is unavailable in your project's version, check the documentation and tasks for that exact Gradle version; do not assume a JDK is missing simply because one command does not exist.

### 5.2. Maven

~~~bash
./mvnw -version
java -version
javac -version
~~~

Or if the project has no wrapper:

~~~bash
mvn -version
~~~

Inspect the effective POM:

~~~bash
./mvnw help:effective-pom
~~~

In multi-module projects, parent POMs, `pluginManagement`, profiles, and properties can alter final plugin versions or compiler settings. Do not draw conclusions from a single snippet of a child POM.

### 5.3. Checking Artifacts After Building

If you suspect bytecode has the wrong Java release:

~~~bash
javap -verbose -classpath build/libs/app.jar com.example.Main
~~~

Or for a Maven JAR:

~~~bash
javap -verbose -classpath target/app.jar com.example.Main
~~~

Look for `major version`:

| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

For a JAR containing many classes, check every class required on the target runtime, including dependencies. Multi-release JARs may hold classes with higher major versions under `META-INF/versions/N` without breaking older runtimes if packaged according to rules; do not flag every higher-version entry as an automatic error.

## 6. Gradle Wrapper: Locking the Build Tool Version

The Gradle Wrapper consists of launcher scripts and distribution configuration, typically located at:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
~~~

A common property:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.1.0-bin.zip
~~~

This is an example version, **not a requirement that every project must use Gradle 9.1.0**. The real version must be chosen based on your project's JDK and plugin compatibility. For externally downloaded distributions, apply checksum verification and trusted repository/distribution URLs per supply-chain policy.

### 6.1. Controlled Wrapper Upgrades

Example once an appropriate version is chosen:

~~~bash
./gradlew wrapper --gradle-version 9.1.0
~~~

Some Gradle workflows recommend running the wrapper task a second time with the new wrapper to update wrapper scripts/JAR according to the selected distribution. After the change, inspect configuration files, version-controlled scripts, and checksums if applicable.

If the old Gradle **cannot run on the new JDK**, do not switch `JAVA_HOME` to the new JDK and hope the wrapper task runs anyway. Instead:
1. Run the old Gradle with a **JDK it supports**.
2. Upgrade the wrapper to the selected version.
3. Run the new wrapper under the target JDK.
4. Only then update plugins/build scripts and run verification.

When moving from Gradle 8 to 9, check deprecations and plugin APIs because this is a major build tool upgrade independent of upgrading the JDK.

### 6.2. The JVM Running Gradle Can Differ from the Declared Toolchain

In modern Gradle, a project's Java toolchain does not necessarily control the JVM running the daemon. Each uses its own mechanism:
- `JAVA_HOME`, `PATH`, IDE configuration, or daemon JVM criteria govern the JVM running the build.
- `java.toolchain.languageVersion` governs the JVM/JDK used by `JavaCompile`, `Test`, `Javadoc`, and supported tasks.
- `options.release` governs the source semantics, APIs, and bytecode permitted by the compiler.

Thus, when using Gradle 9:

~~~text
Gradle daemon: JDK 21
Java toolchain: JDK 17
Artifact target: Java 17
Test runtime: JDK 17
Production runtime: Java 17 or 21 per support statement
~~~

This combination can be completely valid; not every row needs to be JDK 21.

## 7. Gradle Java Toolchains and `--release`

### 7.1. Configuring Toolchains in Groovy DSL

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Explanation:
- Gradle runs on its own daemon JVM and must satisfy the Gradle/JDK matrix.
- `java.toolchain` requests a JDK 21 compiler for suitably configured tasks.
- `options.release = 17` instructs the compiler to enforce Java 17 language syntax, Java SE APIs, and class-file target.
- The artifact **cannot use Java SE APIs introduced only in Java 21** when `--release 17` is used properly.

This is how **the JDK used for compiling** is separated from **the artifact's runtime floor**.

### 7.2. Equivalent Configuration in Kotlin DSL

Example `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

The two DSLs use different syntactic APIs; do not copy Groovy DSL verbatim into Kotlin DSL. API names can vary by Gradle release, so test examples against the exact build tool version you use.

### 7.3. `--release` Differs from `sourceCompatibility`/`targetCompatibility`

Classic configuration example:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

This controls source syntax and class-file target yet **does not completely prevent code from calling APIs appearing only in newer JDKs** if the compiler/classpath provides those APIs.

For example, when compiling with JDK 21 while setting only source/target Java 17, code can accidentally use `SequencedCollection`, which does not exist in Java 17, causing failures on older runtimes. Using `--release 17` lets the compiler check Java SE APIs for the target release, reducing this class of mistake.

However, `--release` constrains only Java SE APIs known to the compiler; it **does not verify whether third-party dependencies** support Java 17. A dependency JAR containing major-65 class files can still cause Java 17 consumers/runtimes to fail. You must inspect the dependency graph and run tests on the target JDK.

### 7.4. Testing on a Different JDK from the Compiler

If you want to compile with JDK 21 yet run tests on JDK 17:

~~~groovy
def java17Launcher = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

tasks.withType(Test).configureEach {
    javaLauncher = java17Launcher
}
~~~

This is a Gradle Java plugin example; ensure JDK 17 can be discovered or provisioned according to your setup. For custom `JavaExec` tasks, integration test plugins, forked test workers, or the Kotlin compiler, check whether each task honors toolchains; do not assume every forked process uses the same JVM.

### 7.5. Toolchains Cannot Always Auto-Download JDKs

Gradle can detect installed JDKs and, when configured with a suitable provisioning repository, download toolchains. However:
- Offline/air-gapped environments cannot download them.
- Certain Gradle/plugin versions require configuring a JDK provisioning repository.
- Proxies, certificates, checksums, and licensing policies may block downloads.
- Vendor/implementation/architecture specifications may not match available JDKs.
- CI requires reproducibility; pin or record JDK sources and images if required by the project.

If “No matching toolchains found” appears, do not rush to modify `options.release`; first check installed JVMs, paths, and toolchain resolvers.

## 8. Maven Compiler Plugin: `--release` and Toolchains

### 8.1. Compiling Code Supporting Java 17

Example `pom.xml` with a pinned Compiler Plugin version:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Plugin version 3.16.0 here illustrates a version supporting the `release` parameter; real projects must verify a plugin version compatible with Maven core and the chosen JDK. Per the Compiler Plugin documentation, using `maven.compiler.release` is preferred over relying solely on `source` and `target`.

With `javac` from JDK 9+, `--release 17` is meaningful only if the compiler supports targeting Java 17; JDK 8 cannot compile sources targeting Java 17. A newer JDK compiler also supports only an allowed set of target releases, not necessarily every historical Java version.

### 8.2. Maven Running JDK 21, Compiler Selecting JDK 17

The Maven Toolchains Plugin helps decouple Maven's own Java runtime from the JDK chosen by toolchain-aware plugins. Toolchain requirements can be declared in the POM. Example passing a specific toolchain to the Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

To work, a matching JDK must be discovered by Maven/the plugin or declared in toolchain configuration. This example requests a JDK 17 compiler and release 17 while the JVM running Maven may be JDK 21.

Do not conflate `<jdkToolchain>` with `<release>`:
- `jdkToolchain` selects the **compiler JDK**.
- `release` selects the **Java SE API/bytecode target** of the compilation.

### 8.3. Toolchains Plugin and `toolchains.xml`

A classic approach is declaring `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

The paths in the example are Linux placeholders; on Windows, replace them with real JDK paths. This file is typically machine/CI configuration and should not store secrets or have personal machine paths committed to a shared repository.

Starting in Maven Toolchains Plugin 3.2.0, JDK auto-discovery and the `toolchains:select-jdk-toolchain` goal are available. Newer plugin versions provide a goal to print discovered JDKs:

~~~bash
./mvnw toolchains:display-discovered-jdk-toolchains
~~~

Once the `select-jdk-toolchain` plugin goal is bound to the lifecycle, toolchain-aware plugins can use the selected JDK. However, **not every Maven plugin automatically supports toolchains**; custom plugins may still read the Maven process's `java.home` or invoke executables directly from `PATH`.

### 8.4. Separate Test JVM with Surefire/Failsafe

Maven Surefire/Failsafe can configure a JDK toolchain for forked tests in supporting versions. Example configuration intending to run unit tests with JDK 17:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

This illustrates where configuration belongs; before adopting it in a project, verify the exact version available in your repository and the plugin's documentation. If Surefire does not fork a JVM under a certain setup or a custom plugin controls the test runtime differently, inspect the effective configuration. For integration tests, verify Failsafe and external service/container JDKs separately.

A Maven build using JDK 21 for the Maven process, 17 for the compiler, and 17 for tests can be entirely intentional, provided all plugins, classpaths, and artifact versions satisfy it.

## 9. The Plugin Matrix Must Be Checked Separately

### 9.1. Maven Plugin Versions Can Raise Minimum JDK Requirements

A newer version of Compiler, Surefire, JaCoCo, or another plugin may require a newer Maven core or a newer JDK. Conversely, an older plugin may rely on internal libraries or APIs restricted on newer JDKs.

Verification sources:
- The “System Requirements” page of that exact Maven plugin version.
- Plugin release notes and compatibility pages.
- The plugin's POM and transitive dependencies.
- `mvn help:effective-pom` to determine which plugin version actually executes.

In multi-module projects, plugin versions can come from parent `pluginManagement`, corporate BOMs/parents, profiles, or module overrides—not just the XML slice currently in front of you.

### 9.2. Gradle Plugin Binary/API Compatibility

A new Gradle major version may remove or deprecate build tool APIs relied upon by older plugins. If a plugin is written in Groovy/Kotlin, embedded compiler/runtime or Kotlin DSL changes can also have an impact. Bytecode-processing plugins (JaCoCo, SpotBugs, bytecode enhancers, instrumentation) must support the class-file version produced by the newer compiler.

When upgrading Gradle 8 to 9:
- Review the Gradle changelog for breaking API changes.
- Check the compatibility range of every plugin.
- Address deprecation warnings before switching major versions.
- Update the wrapper and plugins in small increments while recording diffs/versions.
- Do not assume a plugin supports Java toolchains merely because Gradle core does.

### 9.3. Kotlin, Groovy, Scala, and Annotation Processors

In polyglot projects, verify at least:
- Gradle/Maven version.
- Kotlin/Groovy/Scala compiler and plugin versions.
- Compiler JDK/JVM targets.
- Annotation processors (Lombok, MapStruct, Dagger, etc.).
- Bytecode visitors and test instrumentation.

A Kotlin Gradle plugin may require a minimum Gradle version or validate only a specific Gradle range. A build may pass Java compilation yet fail on Kotlin compilation. An annotation processor may touch compiler internals and break on a JDK upgrade even when Java sources are valid.

**A valid build tool matrix paired with a broken compiler plugin matrix is still an unsupported combination.**

## 10. Diagnosing Failures by Compatibility Layer

| Symptom | First Suspected Layer | What to Inspect |
|---|---|---|
| Gradle fails to start on the new JDK | Gradle runtime vs JDK | `./gradlew --version`, compatibility matrix |
| `Unsupported class file major version ...` while configuring Gradle | Groovy/ASM/Gradle/plugin cannot read bytecode | Gradle & plugin versions, build JDK, plugin JARs |
| Maven reports plugin requires newer Java | Maven plugin JVM requirements | `mvn -version`, plugin dependencies/JDK requirement |
| `No matching toolchains found` | JDK toolchain discovery/provisioning | `javaToolchains`, toolchains.xml, JDK paths/vendors |
| `invalid source release: 21` | Compiler JDK is too old | Actual `javac -version` invoked by the task |
| `release version 17 not supported` | Compiler does not support `--release 17` | Compiler JDK and plugin options |
| `cannot find symbol` for new/old APIs | Source/API target or dependencies | `--release`, classpath, dependency tree |
| `UnsupportedClassVersionError` at app runtime | Artifact/dependency bytecode exceeds runtime JVM | `javap -verbose`, runtime `java -version` |
| `NoSuchMethodError` in tests | Dependency conflict or binary API incompatibility | Dependency graph and loaded classes |
| `InaccessibleObjectException` on new JDK | JPMS reflection, outdated framework/plugin | Stack trace, framework version, module access |
| `No tests found` / test engine crash | Test framework/plugin/JDK mismatch | Surefire/Gradle Test/JUnit runner configuration |
| Local build passes while CI fails | Different JDK/OS/architecture or plugin cache | Wrapper, Java vendor/build, toolchains, effective options |
| Tests pass on JDK 21, production JDK 17 fails | Test runtime mismatches baseline | Runtime matrix and class-file/API checks |
| TLS/truststore error after JDK upgrade | Runtime JDK and security, not just build tool | Ciphers, certificates, truststore, network protocols |

### 10.1. Do Not Abuse JVM Flags to Mask Build Tool Errors

For instance, adding `--add-opens` may help a framework performing deep reflection in the short term, yet it will not make an older Gradle version understand newer class-file versions or fix an outdated compiler. Likewise, `--enable-preview` must not be used to compensate for a wrong `--release` setting, and changing `JAVA_HOME` does not upgrade plugin dependencies.

Apply the fix at the exact failing layer:
- Gradle runtime lacks JDK support: upgrade the Gradle Wrapper or change the JVM running Gradle.
- Compiler is too old: select a newer JDK toolchain.
- Incompatible plugin: upgrade the plugin version or replace the plugin.
- Artifact bytecode exceeds runtime: fix the release target/dependencies or raise the runtime floor.
- JPMS/API behavior: update code/frameworks and test the runtime.

### 10.2. When Even `./gradlew --version` Will Not Run

If Gradle is pinned too old to boot under the current JDK, you can use an older JDK still supported by that Gradle version solely to run the wrapper task and the build tool migration step. Never run unpatched legacy JDKs for production workloads just because the old build needs them; this means isolating **the build migration environment** from **the target production runtime**.

For builds with strict security requirements, the legacy JDK must run in an isolated environment compliant with organizational policy and be retired once the wrapper upgrade completes.

## 11. Example Design of a Viable Project Matrix

Suppose an application commits to supporting Java 17 and Java 21 runtimes while CI upgrades the build tool.

| Layer | Planned Configuration | Rationale |
|---|---|---|
| Build tool | Gradle 9.x selected per plugin matrix | Gradle daemon uses JDK 17+ |
| Gradle daemon | JDK 21 | Convenient for CI builds, within supported range |
| Compiler toolchain | JDK 21 | Pinned compiler |
| Source/API/bytecode target | `--release 17` | Preserves Java 17 runtime floor |
| Test lane A | JDK 17 | Catches APIs/dependencies failing on baseline |
| Test lane B | JDK 21 | Catches behavioral differences on newer runtime |
| App runtime image A | JDK 17 | Release must continue supporting it |
| App runtime image B | JDK 21 | Migration target |
| Code quality/instrumentation | Plugin versions supporting JDK 21 and Gradle 9 | Avoids mid-build failures |
| Dependency graph | Pin versions, check bytecode/transitives | Prevents Java 21-only JARs |

If using Maven instead, you can keep Maven 3.9/3.10 running on JDK 21, compiler toolchain 21 + release 17, and test toolchains 17/21 accordingly. What matters is not making every tool the same version, but having a **verified and version-controlled combination**.

### 11.1. A Single Build with Multiple Java Release Targets

A library may need to publish a Java 8 artifact for older consumers while a newer server uses Java 21. Do not apply the same release target to every module if contracts differ.

Example:

~~~text
legacy-client-api   -> Java 8 bytecode / API
shared-protocol     -> Java 11 bytecode / API
orders-service      -> Java 21 bytecode / API
migration-tools     -> Java 21 build utility
~~~

Here the build tool/daemon can run JDK 21 while each module/compile task gets the appropriate toolchain/release. Also test each module on its **minimum declared runtime**. If a Java 8 module depends directly on a Java 21 artifact, setting `--release 8` on that module's sources will not magically make the dependency compatible.

## 12. CI Test Matrix

A reliable build pipeline typically has two tiers:

**Tier A: Build compatibility**
- Does the pinned Gradle/Maven version boot on the pinned build JDK?
- Do plugins and toolchains resolve properly?
- Do built artifacts target the right class-file/API level?

**Tier B: Runtime compatibility**
- Does the lowest supported JDK execute the artifact properly?
- Does the newest target JDK reveal behavioral differences?
- Do dependencies, TLS, serialization, reflection, and class loading work?

Conceptual pipeline example:

~~~text
Checkout repository
       |
       v
Verify wrapper distribution + checksum
       |
       v
Select build JVM (e.g., JDK 21)
       |
       v
Resolve plugins/dependencies + toolchains
       |
       v
Compile with --release 17
       |
       +-------> Unit + integration tests on JDK 17
       |
       +-------> Unit + integration tests on JDK 21
       |
       v
Inspect artifact class-file/dependencies
       |
       v
Package + smoke test in target runtime image
       |
       v
Publish artifact with toolchain provenance
~~~

### 12.1. Avoid Overly Broad Matrices Without Purpose

If the project only declares support for Java 17/21, there is no need to run every JDK from 8 to 27. An unmaintained sprawling matrix wastes resources without proving compliance with your real contract. Instead:
- Select the runtime floor and LTS/JDK releases with actual users.
- Use the exact JDK vendor/patch image on the release path.
- Maintain a candidate JDK lane for the next migration.
- Run a dedicated plugin/toolchain upgrade lane if needed.
- Record concrete results rather than a generic “build green” badge.

### 12.2. Build Reproducibility and Artifact Provenance

Record:
- Wrapper version and checksum/distribution source.
- JVM used to run the build: vendor, release, build number.
- Compiler toolchain/JDK: version/vendor/path or image digest.
- `--release` and compiler flags affecting ABI.
- Resolved Gradle/Maven plugin versions.
- Dependency lockfile or resolved dependency tree.
- Test runtime JDKs and container images.
- Build logs, artifact checksums, and SBOM if under policy.
- OS/architecture details if native dependencies are present.

Writing only “Java 21” in a README makes investigations very hard, because Gradle 8.4 running on JDK 17 with a Java 21 toolchain behaves differently from Gradle 8.5 running directly on JDK 21, and plugins may behave differently too.

## 13. Upgrade Process from an Older JDK to a Newer JDK

### Step 1: Capture Baseline

Record:

~~~bash
java -version
javac -version
./gradlew --version
# or
./mvnw -version
~~~

Collect the Gradle Wrapper/Maven Wrapper, plugin versions, compiler flags, and container images. Establish a baseline build with test results and artifact checksums.

### Step 2: Select Target Runtime JDK and Support Window

Ask:
- Is the product moving solely to JDK 21 or continuing to run on Java 17?
- Do external consumers use libraries published for Java 8/11?
- Can CI/build hosts upgrade JDKs independently of production?
- Which frameworks/plugins constrain the JDK or build tool version?
- Are there app servers, Android targets, JNI/native libraries, or custom JDK images?

The goal is an approved matrix, not simply one new Java version.

### Step 3: Select Build Tool Versions Supporting the Build JDK

For Gradle, check the **running Gradle** column matching the planned daemon JDK. For Maven, check Maven core and plugin requirements. Do not upgrade every plugin simultaneously if unnecessary; you can decouple build tool upgrades from application JDK upgrades.

### Step 4: Update Wrappers and Plugins in Groups

- Upgrade the pinned Gradle Wrapper or Maven distribution.
- Upgrade plugins blocking compatibility according to the support matrix.
- Review release notes to handle deprecations/build DSL changes.
- Keep separate commits or PRs when possible to isolate scope.
- Do not bypass dependency/security checks when bumping versions.

### Step 5: Configure Toolchains and `--release`

Explicitly define the compiler JDK, Java SE target, and test runtime. If Java 17 must be kept, set release 17 and execute tests on a real JVM 17. If the product raises its runtime floor to Java 21, update the support statement and dependency constraints rather than silently changing the target.

### Step 6: Run Matrix Tests

Build on the supported build JDK, test on target runtimes, and smoke-test the artifact in a production-equivalent environment. In particular verify:
- Java reflection/module access.
- Serialization and JSON/Protobuf.
- TLS/truststores.
- Annotation processors and instrumentation.
- Dependency bytecode newer than the runtime floor.
- Scheduled jobs, timezones, and changed JDK defaults.
- Container startup and JVM flags.

### Step 7: Rollout/Rollback with Clear Boundaries

Rolling back a build tool and rolling back an application runtime are two distinct operations. A JAR with Java 21 class-file major versions cannot suddenly run on a Java 17 JVM merely by rolling the wrapper back from Gradle 9 to Gradle 8. When data/protocol migrations are involved, check both legacy consumers and the application's rollback path.

### Step 8: Maintain the Matrix Post-Migration

Whenever bumping a JDK patch, Gradle/Maven version, or major plugin:
- Update the pinned matrix.
- Re-verify official release compatibility.
- Run committed test lanes.
- Record artifact provenance.
- Retire outdated toolchain configs no longer supported by project policy.

## 14. Common Reasoning Mistakes

- **“The Java version in `gradlew --version` is the target bytecode”:** false; that is the JVM running Gradle, not a substitute for compiler release.
- **“Gradle supports Java 21 toolchains so Gradle 8.4 runs on JDK 21”:** false; running Gradle on Java 21 starts at Gradle 8.5.
- **“Maven 3.9 runs with JDK 21 so every Maven plugin supports JDK 21”:** false; plugins have independent requirements.
- **“Gradle 9 does not run on Java 8 so it cannot build Java 8 libraries”:** false; daemon runtime and compiler target are distinct.
- **“Setting source/target 17 suffices to block Java 21 APIs”:** false; prefer `--release 17`.
- **“If the compiler targets 17, dependencies definitely run on Java 17”:** false; check dependency bytecode and APIs.
- **“Toolchains are configured, so tests definitely run on the right JDK”:** inspect actual tasks/plugins and forked test JVMs.
- **“Switching JAVA_HOME to a new JDK automatically updates the Gradle Wrapper”:** false; the wrapper version remains the pinned version.
- **“Updating Gradle/Maven core updates plugins”:** false; plugin versions have independent lifecycles.
- **“Building successfully in the IDE means CI is compatible”:** false if Gradle JVM, toolchains, vendors, or plugin caches differ.
- **“A newer JDK always runs every older plugin”:** untrue when plugins depend on JDK internals or older bytecode tooling.
- **“You can upgrade Gradle majors without reviewing deprecations”:** likely to break build scripts or custom plugins.
- **“Testing every JDK is best”:** pick the committed runtime range and track results systematically.
- **“Maven Toolchains automatically controls every plugin”:** only toolchain-aware plugins honor the selected toolchain.
- **“Java 21 is the exact same runtime everywhere”:** vendors/patches/builds, images, tzdb, and security settings can differ.

## 15. Checklist Before Accepting a Build/JDK Matrix

- [ ] Identified the supported product runtime JDKs and target compiler JDK.
- [ ] Recorded JDK vendor/patch/build along with OS/architecture for build/test/runtime.
- [ ] Identified the actual Gradle Wrapper or Maven Wrapper/distribution.
- [ ] Verified Gradle **running** compatibility with the daemon JDK.
- [ ] Verified Gradle **toolchain** compatibility with compiler/test JDKs.
- [ ] If using Maven, verified core JVM requirements and every critical plugin.
- [ ] Pinned Gradle/Maven versions and checksums/sources as required.
- [ ] Pinned/verified framework plugins, Kotlin/Groovy, annotation processors, and bytecode tooling.
- [ ] Configured toolchains explicitly rather than relying solely on ambient JAVA_HOME.
- [ ] Set `--release` matching the runtime floor rather than source/target alone.
- [ ] Checked bytecode class-file versions and dependency graphs after building.
- [ ] Ran tests on the lowest declared supported JDK.
- [ ] Ran tests on the new target JDK, including integration and runtime behavior.
- [ ] Verified wrapper/IDE/CI/containers do not invoke unexpected JVMs.
- [ ] Recorded test results per toolchain version, not just “build green.”
- [ ] Prepared separate upgrade/rollback plans for build tools and application runtime.
- [ ] Keep the matrix updated whenever upgrading JDK or Gradle/Maven/plugin versions.

## 16. Official Documentation for Updating the Matrix

Milestones in this lesson must be re-verified at deployment time, especially when a new JDK, Gradle, or Maven release ships:

- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDKs for toolchains and JDKs for running Gradle.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test JDKs, `--release`, toolchain sources, and JDK selection.
- [Gradle — Upgrading to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html): runtime floor changes, DSL/API/plugins.
- [Gradle — Releases](https://gradle.org/releases/): release notes and distribution versions.
- [Apache Maven — Download](https://maven.apache.org/download.cgi): current Maven branches and JDK baselines.
- [Apache Maven — Releases History](https://maven.apache.org/docs/history): release history, support status, JDK minimums.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): distinguishing compiler release from source/target.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): JDK toolchains and plugin integration.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): JDK discovery and toolchain selection.

When using “current” links, contents evolve with newer releases. For audit reports or long-lived migrations, record the access date, exact Gradle/Maven versions, and versioned documentation URLs so decisions remain reproducible.

## 17. Conclusion

**The Maven/Gradle compatibility matrix with JDKs is a multi-dimensional matrix, not a checklist for swapping the JDK and re-running the build command.** With Gradle, always read the **toolchain support** and **running Gradle support** columns separately; with Maven, separate Maven core's JVM requirement from each plugin's independent requirements and the JDK picked by toolchains. In both cases, compiler targets, test JVMs, artifact dependencies, and production runtimes remain distinct compatibility layers.

A sustainable Java migration workflow is **inventory wrapper/tools/plugins → choose a compatible build JDK → configure toolchains and `--release` → test on the runtime floor and target runtime → record provenance and update the matrix**. When layers are pinned and independently verified, teams can upgrade JDKs or build tools step by step, catch errors at the right layer, and prevent shipping artifacts that work only on the build machine while failing in customer environments.
