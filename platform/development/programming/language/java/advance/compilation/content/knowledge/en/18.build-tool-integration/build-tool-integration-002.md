# Configuring a Toolchain Independent of the JDK Running the Build Tool

A Java project can run **Maven or Gradle on JDK 21**, yet **compile source code with JDK 17**, run unit tests with JDK 17 or JDK 21, and distribute an artifact compatible with Java 17. This capability comes from the *Java toolchain*: explicitly configuring the JDK version/installation used for build tasks, instead of implicitly taking every tool from `JAVA_HOME` or the JVM running the build tool.

This lesson focuses on **build and compilation integration**: distinguishing the JVMs/JDKs involved, configuring toolchains with Maven and Gradle, comparing with `--release`, verifying the actual version used, and keeping builds reproducible across developer machines, CI, and deployment environments.

## 1. Three Frequently Confused Concepts

~~~text
Terminal / CI / IDE
      |
      |  Select JVM running build tool (JAVA_HOME, IDE, daemon)
      v
Maven JVM or Gradle daemon JVM
      |
      |  Read pom.xml / build.gradle(.kts)
      |  Resolve dependencies, schedule tasks, run plugins
      |
      +------------------------+
      | Java toolchain         |
      | Select JDK for task    |
      v                        v
JDK using javac            JDK using java for Test/JavaExec
      |                        |
      v                        v
*.class + JAR               Test runtime / task runtime
      |
      |  target/release level; artifact and dependencies
      v
Deployment machine JDK (may be a third installation)
~~~

A build can have the following versions, **not necessarily identical**:

| Layer | Role | Example |
| --- | --- | --- |
| **Build JVM** | Runs Maven CLI, Gradle launcher/daemon, build scripts, and plugins | JDK 21 |
| **Compiler toolchain** | Provides `javac` and bytecode-building tools | JDK 17 |
| **Test launcher/toolchain** | Runs the JVM of test tasks | JDK 17 or 21, depending on configuration |
| **Javadoc/tool task** | Generates documentation, runs `javadoc`/`jarsigner` or other tasks | Toolchain supported/selected by the plugin |
| **Target release** | Source version, Java platform APIs, and class-file format that the artifact targets | Java 17 |
| **Deployment JVM** | JVM that actually runs the artifact when deployed | Java 17+ compatible JDK/JRE |

**Do not conflate them:** “Maven runs on JDK 21” does **not** mean the compile task's `javac` is necessarily JDK 21; “bytecode class version 61” does **not** by itself prove it was compiled with JDK 17. A newer compiler can generate class files targeting Java 17.

## 2. Why Are Toolchains Needed?

Without an explicitly declared toolchain, build results can accidentally depend on the environment:

- Machine A uses JDK 17, machine B uses JDK 21, and both run the same `mvn package` or `gradle build` command.
- A developer changes `JAVA_HOME` to run a new IDE/plugin and the project's compiler target also changes unintentionally.
- CI uses JDK 21 to run a new Gradle version, yet a library application must still be compiled with JDK 17 for end users.
- A compile task uses JDK 17, while the test task silently runs on another JDK. Test results might fail to reproduce issues in the real runtime.
- Annotation processors, Javadoc, or code-generation tools depend on JDK tool APIs, not just the Java language level of the source.

**A toolchain creates a build contract**: the project requests a specific tool type and version; the build system finds or provisions a matching JDK installation and supplies the tool to toolchain-aware tasks.

Toolchains **do not automatically download a JDK in every case**. Maven and Gradle have different discovery/provisioning mechanisms. A build may fail when no matching installation is found; that is generally better behavior than silently using the wrong JDK.

## 3. How Does a Toolchain Differ from `--release`?

Suppose JDK 21 is used to compile code that must run on Java 17. Two different questions:

1. **Which compiler is used?** → JDK toolchain (e.g., JDK 21).
2. **Which release is the compiler restricted to generate compatible artifacts for?** → `javac --release 17`.

| Mechanism | Selects JDK performing compilation? | Restricts language? | Restricts Java platform APIs? | Class-file target? |
| --- | --- | --- | --- | --- |
| Toolchain JDK 17 | Yes, compiler from JDK 17 | Per selected compiler | Per APIs supported by that compiler/JDK | Default per compiler/options |
| Toolchain JDK 21 + `--release 17` | Yes, JDK 21 | Java 17 level | Java platform APIs in Java 17 via the `--release` mechanism | Java 17 |
| `--release 17` alone | Does not select JDK; uses compiler already selected by task | Java 17 | Java 17 Java platform APIs | Java 17 |
| `-source 17 -target 17` | Does not select JDK | Java 17 | **Does not guarantee** only Java 17 APIs are used | Java 17 |
| `JAVA_HOME` | May affect build JVM, environment, and tool discovery | Does not lock source level | Does not lock API level | Does not lock class version |

**Different scenarios:**

- If the requirement is “**must use the exact javac 17**” to catch compiler/annotation-processor compatibility issues, set toolchain 17.
- If the requirement is “**use javac 21 but output supports Java 17**”, use toolchain 21 **combined with** `--release 17`.
- If you only write `--release 17` without selecting a toolchain, the actual compiler can still vary across machines.
- `--release` primarily constrains the **Java platform**; it does not guarantee that third-party library versions or native APIs the application depends on are also compatible.

Not every newer compiler supports every older release; check `javac --help` or the toolchain/version configuration used by the project.

## 4. Java 17 Application Example to Verify the Build

Use the same standalone source for both the Maven and Gradle examples below.

**File `src/main/java/edu/example/toolchain/BuildProbe.java`:**

~~~java
package edu.example.toolchain;

public final class BuildProbe {
    private record Greeting(String name) {}

    public static void main(String[] args) {
        Greeting greeting = new Greeting("Java");
        System.out.println("toolchain-ok:" + greeting.name());
    }
}
~~~

Records became standard Java language syntax before Java 17 and are completely valid with Java 17 source/target. The project requires no external libraries.

Self-check when JDK 17+ is available:

~~~bash
javac --release 17 -d out src/main/java/edu/example/toolchain/BuildProbe.java
java -cp out edu.example.toolchain.BuildProbe
~~~

**Exact stdout:**

~~~text
toolchain-ok:Java
~~~

A compiler supporting `--release 17` will produce class files, including the binary type for the nested record `Greeting`. Do not guess there is only `BuildProbe.class`: there is also `BuildProbe$Greeting.class`. This example also helps observe multiple class outputs from the same source.

To inspect the class-file target:

~~~bash
javap -verbose -classpath out edu.example.toolchain.BuildProbe
~~~

Look for `major version: 61`, the class-file version value for Java 17. **Major version 61 only proves the target class format**, not that the compiler came from JDK 17 rather than a JDK 21 toolchain with `--release 17`.

## 5. Maven: Separating the JVM Running Maven from the JDK Used for Building

Maven usually runs with Java from `JAVA_HOME`/the launcher chosen by the user. The command:

~~~bash
mvn -version
~~~

displays the Java runtime Maven is currently using, such as Java 21. This is **not a direct measurement** of the JDK that the Maven Compiler Plugin selects after toolchain configuration.

The Maven Toolchains Plugin allows a project to **request a toolchain**, select from JDKs declared on the machine, and place the toolchain into the build context for *toolchain-aware* plugins to use.

### 5.1. Installing Both JDKs

Suppose the machine has:

~~~text
/opt/jdks/jdk-17/       # real JDK 17, with bin/java and bin/javac
/opt/jdks/jdk-21/       # real JDK 21, with bin/java and bin/javac
~~~

The paths above are **examples** and must be replaced with real JDK installation paths. On Windows, paths may look like `C:\Program Files\Java\jdk-17` and `C:\Program Files\Java\jdk-21`.

You can choose JDK 21 to run Maven, yet require JDK 17 to compile code. The **JDK running Maven** must still be compatible with the Maven version and plugins in use; toolchains do not allow a build tool to run on a Java version that the build tool itself does not support.

### 5.2. Declaring Local JDKs in `~/.m2/toolchains.xml`

**File `~/.m2/toolchains.xml`** (on Windows usually `%USERPROFILE%\.m2\toolchains.xml`):

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

`<provides><version>17</version>` is the toolchain identification information used to **match requirements**. `<configuration><jdkHome>...` is the root path of the installation. Other vendor tokens can also be declared, though if a vendor is requested in the POM then the local toolchain must have a matching token.

**Do not assume Maven automatically validates every attribute such as version/vendor from the directory name.** With manual configuration, verify directly:

~~~bash
/opt/jdks/jdk-17/bin/java -version
/opt/jdks/jdk-17/bin/javac -version
/opt/jdks/jdk-21/bin/java -version
~~~

These are Unix command examples. On Windows, use the corresponding executables from `bin` and put paths in quotes when they contain spaces.

**Do not commit personal machine paths into `pom.xml`.** `toolchains.xml` is normally **per-machine/CI** configuration, whereas the POM declares version requirements that can be shared in the repository.

### 5.3. Complete POM Requiring JDK 17

**File `pom.xml`** in the project root directory containing `src/main/java` from section 4:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>edu.example</groupId>
  <artifactId>toolchain-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-toolchains-plugin</artifactId>
        <version>3.3.0</version>
        <executions>
          <execution>
            <goals>
              <goal>toolchain</goal>
            </goals>
          </execution>
        </executions>
        <configuration>
          <toolchains>
            <jdk>
              <version>17</version>
            </jdk>
          </toolchains>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Why are there both a toolchain and `<release>17</release>`?**

- `maven-toolchains-plugin` selects a JDK 17 from the entries in `toolchains.xml`. The `toolchain` goal is bound by default to the `validate` phase and puts the selection into the Maven build context.
- `maven-compiler-plugin` is a plugin that supports JDK toolchains; it can take `javac` from the toolchain instead of defaulting to the JDK that launched Maven.
- `<release>17</release>` instructs compilation to target the Java 17 language/platform API/classfile release. This is a **target constraint**, not a JDK selection mechanism.

Plugin versions are explicitly specified so the build does not depend on implicit environment plugin versions. For real projects, choose versions confirmed compatible with the organization's Maven/JDK. The example requires Maven to be able to download plugins/dependencies from a configured repository (typically Maven Central) or an existing cache.

### 5.4. Compiling and Verifying

From the directory containing `pom.xml`:

~~~bash
mvn -version
mvn clean package
java -cp target/classes edu.example.toolchain.BuildProbe
~~~

Output of `mvn clean package` includes logs depending on Maven version, cache, and configuration; it should not be treated as fixed stdout. Running `BuildProbe` successfully will print:

~~~text
toolchain-ok:Java
~~~

If shell `java` points to JDK 21, the program is executed using JDK 21. That **does not change** the fact that compilation was requested to use JDK 17. To test runtime 17 explicitly, use:

~~~bash
/opt/jdks/jdk-17/bin/java -cp target/classes edu.example.toolchain.BuildProbe
~~~

On Unix/Windows, adjust the path accordingly. Note: the last command does **not** prove Maven selected JDK 17 during compilation; it proves **the artifact runs on a Java 17 runtime**. To verify the compiler toolchain, inspect the logs of the Toolchains Plugin/Maven Compiler Plugin (using `mvn -X clean compile` when needed), or the environment selected by the task.

### 5.5. No Matching Toolchain Found

If the POM requests JDK 17 but `toolchains.xml` only has JDK 21, the build can fail during the `validate` phase with a diagnostic stating no matching toolchain was found. That is good behavior: the project refuses to compile silently with another compiler.

How to fix:

1. Install the exact JDK 17 required.
2. Check that `jdkHome` points to the **JDK home**, not the `bin` folder or a non-existent path.
3. Declare matching `version`/`vendor` tokens in `toolchains.xml`.
4. Re-run `mvn -version` to check the Maven JVM (just to distinguish layers), then read the toolchain selection logs during the build.

**Do not “fix” it by deleting the toolchains plugin** just to make the build temporarily pass on JDK 21 if the project contract truly requires a JDK 17 compiler.

## 6. Maven: Selecting a JDK via Discovery or Plugin-Specific Toolchain

### 6.1. Newer Discovery Mechanism

Maven Toolchains Plugin from the 3.2.0 line supports **JDK discovery** and the `select-jdk-toolchain` goal. This mechanism differs from manually writing `toolchains.xml` and using the `toolchain` goal.

A project can use the discovery goal to choose a suitable JDK from installations recognized by the tool. However, automatic detection does not mean every machine has JDK 17. You must inspect the list of detected installations and require specific matching; CI should fail clearly when a JDK is missing rather than silently picking another one.

Useful diagnostic goal in modern plugin versions:

~~~bash
mvn toolchains:display-discovered-jdk-toolchains
~~~

Output depends on the JDKs actually found. **There is no need to combine the two selection methods** inadvertently: the main example chooses the manual `toolchains.xml` style; using discovery is an alternative option with its own configuration.

### 6.2. Compiler Plugin `<jdkToolchain>`

In some cases, the Maven Compiler Plugin has its own `<jdkToolchain>` configuration to request a JDK directly for that plugin itself, for example this illustrative configuration snippet:

~~~xml
<configuration>
  <release>17</release>
  <jdkToolchain>
    <version>17</version>
  </jdkToolchain>
</configuration>
~~~

This is **not a standalone POM** and should not be pasted over a POM already using a global toolchain without reason. The plugin-specific mechanism can **override the session's toolchain selection** for the compiler plugin, while other plugins like Surefire/Javadoc may use a different selection. If tests/javadoc also need to run with a fixed JDK, toolchains should be selected/arranged for the **entire pipeline**, not just the compiler.

## 7. Gradle: Java Toolchain Distinct from the JVM Running the Gradle Daemon

In Gradle, the **JVM used to run Gradle** is selected via environment, IDE, or *Daemon JVM criteria* depending on Gradle version. The **project's Java toolchain** is a separate configuration.

For example, the Gradle daemon runs on JDK 21 while a project uses:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

When the Java plugin is applied, Gradle can use JDK 17 for `JavaCompile`, `Test`, and `Javadoc` by default according to the project toolchain, even though the daemon still uses JDK 21. This is not a step where “Gradle downgrades its own JVM to Java 17”; Gradle simply supplies the appropriate tool to tasks that need it.

**Gradle version note:** the chosen Gradle version must be able to run on the JVM used for the daemon, while also supporting the desired JDK toolchain. If Gradle needs a higher Java version to run itself, only change the daemon JVM when it satisfies Gradle's runtime requirements; do not force the daemon onto an old JDK just because the application target is old.

### 7.1. Complete Gradle Kotlin DSL

Assume the same `src/main/java/edu/example/toolchain/BuildProbe.java` from section 4.

**File `settings.gradle.kts`:**

~~~kotlin
rootProject.name = "toolchain-demo"
~~~

**File `build.gradle.kts`:**

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

application {
    mainClass = "edu.example.toolchain.BuildProbe"
}
~~~

Explanation:

- `application` applies the Java plugin and provides the `run` task, where the main class is declared.
- `java.toolchain.languageVersion` requests **JDK 17** for Java tasks that support toolchains. It does not require Gradle's daemon to run on JDK 17.
- `options.release.set(17)` adds the Java 17 language/API/classfile target constraint to `JavaCompile` tasks.
- `application.mainClass` defines the entry point for the `run` task.

Run in the project using the **project-managed Gradle Wrapper** (if the wrapper has already been generated):

~~~bash
./gradlew --version
./gradlew clean build
./gradlew run
~~~

On Windows, `gradlew.bat` is normally used. If the project does not yet have a Gradle Wrapper, generate it with an appropriate installed Gradle version, e.g., `gradle wrapper`, and then commit the wrapper files so teammates/CI use the same Gradle distribution. Do not create a Gradle wrapper JAR manually by fabricating contents.

`./gradlew run` executes the application with the Java launcher configured by Gradle for the project/toolchain (when tasks/plugins support it). **Stdout printed by the application**:

~~~text
toolchain-ok:Java
~~~

Gradle may add task/status logging around the result; therefore the entire terminal output of `gradlew run` is not necessarily a single line.

### 7.2. Equivalent Gradle Groovy DSL

If the project uses `build.gradle` instead of Kotlin DSL:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'edu.example.toolchain.BuildProbe'
}
~~~

Choose only **one DSL suited to the project**; do not keep both Gradle config files simultaneously as two conflicting sources of truth.

## 8. Gradle: Combining a JDK 21 Compiler with a Java 17 Target

In some projects, the goal is a **compiler from JDK 21** while output is only allowed to use **Java 17 APIs/language**.

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

This is an illustrative Gradle Kotlin DSL configuration usable in a project **with a Java 21 toolchain installed**. The compiler tool is JDK 21; `--release 17` constrains source/API/classfile. Unit tests default to the project toolchain JDK 21 if not overridden; **they do not automatically prove the application was tested on a Java 17 runtime**.

If the minimum production version is Java 17, you need to add a test task/CI job running Java 17 to avoid missing runtime and third-party dependency differences. Do not draw conclusions from bytecode major version alone.

### 8.1. Using JDK 17 for Tests Even When Compiling with JDK 21

Kotlin DSL configuration example when application bytecode is compiled with `--release 17`:

~~~kotlin
val java17Launcher = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(java17Launcher)
}
~~~

This snippet is placed in a `build.gradle.kts` **that has already applied the Java plugin**, with JDK 17 discoverable by Gradle. Overriding the test launcher **does not change the compiler toolchain**; it only changes the Java process running the tests. For custom `JavaExec` tasks, there is a corresponding `javaLauncher` property when the task supports it.

You can use different launchers for a test matrix, but avoid turning a single task named `test` into multiple runtime tests with undistinguished outputs. Create separate tasks per runtime or clear CI jobs.

## 9. Where Does Gradle Find JDK Toolchains?

Gradle has a mechanism to **auto-detect installed JDKs** from several locations and the environment, and can **auto-provision** when a repository/toolchain resolver is properly configured. Conditions to remember:

- `languageVersion = JavaLanguageVersion.of(17)` sets a **requirement**; it does not promise “every machine will automatically download JDK 17 even when offline or without a configured resolver”.
- Gradle can inspect different JDK installations and pick one satisfying the requirement; if multiple vendors/distributions have the same version, the selected result may vary without additional constraints.
- Vendor, implementation/JVM options can be declared per the toolchain specification when needed. Do not add unnecessary criteria; for instance, only requesting Java 17 can accept multiple suitable JDK 17 distributions.
- The JDK used to **run the Gradle daemon** and the JDK **providing the toolchain** often appear in the same list, yet remain two independent decisions.
- Toolchain provisioning/caching depends on Gradle version configuration, repositories, and network/CI policies; do not rely on silent downloads when builds must be reproducible offline.

Check JDKs detected by Gradle:

~~~bash
./gradlew javaToolchains
~~~

This is a diagnostic task supporting Java installations with a compatible Gradle version. Output can list JDK vendor/version/path and detection status. It **does not replace** looking at compile/test task logs to see which tool was actually selected.

Additional paths can be specified using Gradle properties configuration when auto-detection misses a custom JDK installation. An illustrative option in `gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

These are **Unix example paths**, not to be used verbatim on every machine. For portable projects, prefer configuring JDK installations at the CI/machine level or per organization policy rather than committing absolute paths into the repo.

### 9.1. What Effect Does `JAVA_HOME` Still Have?

`JAVA_HOME` can determine the JVM launching Gradle/Maven when no other setting exists, or be used by the build tool during discovery. However, when a project **has already requested its own toolchain**, do not infer that changing `JAVA_HOME` will change the compiler/task JDK to the same version. If both Gradle's JVM and the active toolchain happen to use the same JDK, that is a coincidence of configuration, not a mandatory contract.

IDEs (IntelliJ, Eclipse...) can have their own **Gradle JVM**. A project seeing Gradle daemon 21 in the IDE and 17 in the terminal can still compile with JDK 17 via a toolchain; what needs verification is *toolchain selection*, not just the Gradle JVM label in the IDE.

## 10. A Single Project Can Use Multiple JDKs in the Same Pipeline

Example release workflow for a library that must run on Java 17:

~~~text
CI runner:
    JDK 21 ---> runs Gradle daemon / Maven build engine
    JDK 21 ---> javac compiles --release 17
    JDK 17 ---> runs compatibility tests
    JDK 21 ---> runs forward-compatibility tests
    JDK 21 ---> javadoc or static analysis tools
    Java 17+ --> expected deployment target
~~~

This model is useful when Java 21 is needed for new build tooling while the library still commits to supporting runtime 17. In exchange, it requires multiple JDK installations, CI caching, and verification of paths/vendoring.

**Do not lower the target with just a number in POM/Gradle and consider it done:** binary dependencies may be compiled at a higher class-file version, or a third-party library may call an API existing only in Java 21. The compiler target of the **source code being compiled** does not verify every execution path in the dependency graph.

### 10.1. Which JDK Do Annotation Processors and Plugins Use?

Maven/Gradle can run plugins/build scripts on the **build JVM**; separately, the Java compilation task can use the **toolchain javac**. Annotation processors usually run inside the environment/compiler process corresponding to how the plugin invokes the compiler, so changing the toolchain can affect annotation processing.

Do not deduce that “every Maven/Gradle plugin has switched to JDK 17” after selecting toolchain 17. Only **toolchain-aware tasks/plugins** use the toolchain according to their contract. For instance, an arbitrary plugin reading `System.getProperty("java.home")` itself may still see the build JVM's Java home.

If an annotation processor uses internal `jdk.compiler` APIs or depends on compiler AST, test the processor with the exact selected compiler JDK, not just by changing `--release`.

## 11. Toolchains and Build Reproducibility

To turn a toolchain into a reliable contract, **multiple version layers** must be managed:

| Layer | Must lock/record |
| --- | --- |
| Build tool | Maven/Gradle wrapper or organization standard version |
| JVM running build | Supported version for build tool, IDE/CI daemon criteria when needed |
| Java toolchain | Major version, vendor/implementation when required |
| Target API/bytecode | `--release 17` or corresponding property |
| Dependencies | Versions of Java libraries, annotation processors, build plugins |
| Test runtime | Minimum JDK and newer JDKs that must be supported |
| Container/CI image | Actual available JDK installations, build cache, paths |
| Binary artifact | `.class` version, JAR contents, runtime startup validation |

**Toolchains do not automatically make builds bit-for-bit reproducible.** Two JDK 17 builds from different vendors or two minor/patch releases can differ in compiler fixes, diagnostics, or behavior, even with the same languageVersion. If the project requires strict artifact reproducibility, you must also control plugin versions, timestamps, archives, locale/timezone, file ordering, dependencies, and build parameters.

### 11.1. JDK Paths and Portability

- **Maven:** `~/.m2/toolchains.xml` has local `jdkHome`; the POM requests version/vendor and **does not hardcode home paths**. CI generates toolchains config or uses discovery per project policy.
- **Gradle:** the project declares `java.toolchain`; installations can be detected/provisioned per machine/CI configuration and repository resolvers. Do not commit absolute `/home/user/...` or `C:\Users\...\jdk` paths into shared build scripts.
- **Docker/CI:** provide the right JDKs from the image or cache provisioning, then run toolchain selection verification. Do not rely on the shell `java` version to conclude the compiler toolchain was correct.

## 12. Typical CI Scenarios

Suppose Maven runs on JDK 21 on an agent that has both JDK 17 and JDK 21:

~~~text
CI setup
  install JDK 21 (build JVM)
  install JDK 17 (compiler/test toolchain)
  create ~/.m2/toolchains.xml with JDK homes
  verify Maven toolchain selection
  run: mvn -B clean verify
  run smoke test with JDK 17
  publish JAR only after checks pass
~~~

This is **CI plan pseudocode**, not YAML for GitHub Actions/GitLab CI or a pipeline to copy verbatim. Each CI provider has its own tasks/actions for installing JDKs and managing caches.

With Gradle:

~~~text
CI setup
  install JDK 21 (Gradle daemon JVM)
  install/configure JDK 17 (project toolchain)
  use checked-in Gradle Wrapper
  run: ./gradlew --version
  run: ./gradlew javaToolchains
  run: ./gradlew clean check
  verify Java 17 runtime compatibility
  publish only after checks pass
~~~

Integration usually needs to separate the **verification job** and the **publication job** so an artifact is not released merely because compilation succeeded.

## 13. Checking Which Version the Compiler Actually Used

This is the central question of the lesson: to confirm the toolchain is **independent** of the JDK running the tool, you must observe the right layer.

### 13.1. Common Commands and What They Prove

| Command/observation source | Shows | Does not directly prove |
| --- | --- | --- |
| `java -version` in shell | Java executable currently chosen by shell | Maven/Gradle compiler JDK |
| `javac -version` in shell | javac currently chosen by shell | Actual javac chosen by plugin |
| `mvn -version` | Java runtime running Maven | Compiler plugin's JDK toolchain |
| `./gradlew --version` | Gradle version and runtime/daemon JVM depending on display | JDK of all compile/test tasks |
| `./gradlew javaToolchains` | JDKs recognized by Gradle and attributes | That a task definitely selected a specific JDK |
| Maven Toolchains Plugin logs | Toolchain selected in build context | That every plugin uses that selection |
| Gradle compile/test task logs (when info is enabled) | Compiler/launcher used for the task | Production deployment JVM |
| `javap -verbose` major version | Bytecode target class-file version | Compiler JDK and runtime used during build |
| Running tests with specific binary `/path/to/jdk-17/bin/java` | Artifact was actually tested on that JVM | Runtime code in every other environment |

### 13.2. Maven Logs

~~~bash
mvn -X clean compile
~~~

In the output, you can observe information about plugins' selected toolchain/JDK paths. Long logs may contain paths and arguments carrying internal data; strip sensitive information when sharing outside the organization. Do not use a single version warning line as sole evidence if a compiler/plugin has its own override.

### 13.3. Gradle Logs

~~~bash
./gradlew --info compileJava test
./gradlew javaToolchains
~~~

If task reports are insufficient to prove the compiler, inspect the `javaCompiler` task configuration or add a dedicated **read-only** diagnostic task (in a build environment where editing scripts is permitted), instead of running `java -version` and guessing.

### 13.4. Cross-Checking the Class-File Target

After compiling with target Java 17, a normal class file has:

~~~text
major version: 61
~~~

However, this is only the class-file version of **one specific class**. If the JAR contains dependencies or is a multi-release JAR, appropriate class entries must be checked; the project's target does not automatically turn every dependency's class version into 61.

## 14. Common Configuration Errors

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Maven compiles with the JDK running Maven, not JDK 17 | Toolchain goal not configured or compiler plugin does not take toolchain | Inspect POM executions and selected toolchain logs |
| Maven reports no matching JDK found | `toolchains.xml` missing entry, version/vendor mismatch, wrong `jdkHome` | Check local file and actual JDK version |
| Gradle reports no toolchain found for Java 17 | Machine lacks JDK 17, discovery misses it, provisioning unconfigured | Install JDK, adjust detection or appropriate resolver |
| `Unsupported class file major version` | Running JVM encounters class format from newer Java | Check actual runtime JVM and target/dependency bytecode |
| `invalid target release` / `release version not supported` | Selected compiler is too old or requested target is unsupported by it | Identify compiler toolchain and appropriate release |
| `NoSuchMethodError` / `ClassNotFoundException` at runtime | Incompatible dependency/runtime API, not necessarily toolchain | Check dependency versions, runtime classpath, module graph |
| Toolchain is right but tests use another JDK | Plugin/task lacks support or launcher not configured | Configure test runtime toolchain/launcher separately |
| IDE build OK, CI fails | IDE picks different JVM/Gradle daemon or CI lacks JDK toolchain | Compare environments and selection logs, use wrapper |
| Annotation processor fails when changing JDK | Processor depends on different APIs/compiler implementation | Test processor with exact compiler JDK and supported version |
| Build downloads JDK on machine A but fails offline on machine B | Provisioning/cache/repository not fully declared | Use image with pre-installed JDK or explicit resolver and cache |
| Java 17 bytecode fails with linkage error on Java 17 | Third-party dependency or code uses reflection/native/newer behavior | Integration test on real runtime and dependency graph |
| `JAVA_HOME` changes yet compile still uses another JDK | Separately configured toolchain is intentional | Verify build JVM and toolchain independently; do not delete options arbitrarily |

## 15. Common Misconceptions

**“Using JDK 21 to run Maven means the project definitely compiles with Java 21.”** Incorrect when the compiler plugin uses toolchain 17.

**“Setting `maven.compiler.release=17` selects JDK 17.”** Incorrect; it sets the target, it does not select the JDK/compiler executable.

**“Setting toolchain JDK 21 with `--release 17` makes it unable to run on Java 17.”** False: source/API/classfile are constrained accordingly, provided dependencies and runtime behavior are also compatible. Actual testing is required.

**“`sourceCompatibility=17` and `targetCompatibility=17` are enough to prevent calling Java 21 APIs.”** Not guaranteed; use `--release` when you want to restrict Java platform APIs.

**“`mvn -version` or `gradle --version` confirms the compiler version.”** No; they primarily identify the JVM running the build engine, not each task's selected compiler toolchain.

**“Declaring a JDK toolchain means Maven/Gradle always auto-downloads the JDK.”** No; provisioning/discovery mechanisms depend on the tool and configuration. Builds should fail clearly when an installation is missing.

**“Toolchain JDK 17 means every plugin also runs in JVM 17.”** No; the build engine and plugins usually still run on the build JVM. Toolchain-aware tasks/plugins select the corresponding executable/JDK.

**“Running on JDK 21 proves it runs on JDK 17.”** No; if Java 17 is the minimum runtime, it must be tested on JDK 17 with real dependencies.

## 16. Self-Check Exercises

**1. Maven runs on JDK 21, compiler plugin selects JDK 17: is there a contradiction?**  
No. The build JVM executes Maven/plugin logic; the JDK 17 toolchain supplies the compiler for the compilation task.

**2. How does the pair `toolchain 21 + --release 17` differ from `toolchain 17 + --release 17`?**  
Both target Java 17 language/API/classfile, yet they use **javac from two different JDKs**, thus differing in compiler version and potentially differing in behavior/tooling bugs.

**3. Why does Maven need `toolchains.xml` when using manual selection?**  
The POM contains the JDK **requirement**, while the local file provides the **installation path** meeting that requirement. The POM does not need to hardcode machine paths.

**4. Why does Gradle need `java.toolchain` when `JAVA_HOME` already points to JDK 21?**  
So compiler/test launcher tasks can be supplied a different JDK per project contract, without depending on each machine changing `JAVA_HOME`.

**5. `javap` shows major 61. Can we conclude that a JDK 17 toolchain was used?**  
No. JDK 21 with `--release 17` can also produce a major 61 class file.

**6. If `--release 17` is set, is the project automatically guaranteed that every dependency runs on Java 17?**  
No. You must verify binary dependencies and run integration tests on a Java 17 runtime.

**7. If the Gradle daemon uses JDK 21 and the Test task launcher uses JDK 17, where do unit tests run?**  
A JDK 17 JVM per the Test task's launcher, while the Gradle daemon still runs JDK 21.

**8. When Maven cannot find a toolchain, should you change `maven.compiler.release` from 17 to 21 to get a green build?**  
No, if the project contract requires JDK 17; install the right JDK and configure matching discovery/toolchains.

**9. Does a toolchain enforce the same vendor across developer/CI?**  
Not by default when selecting only major version. If reproducibility/vendor-specific bugs matter, add vendor/implementation constraints and verify in practice.

**10. Why should CI test on both the minimum JDK and a newer JDK?**  
The minimum JDK confirms backward compatibility; the newer JDK helps catch forward compatibility issues, dependency issues, and runtime changes.

## 17. Practical Checklist

- [ ] Clearly state **build JVM**, **compiler toolchain**, **test runtime**, and **minimum deployment JDK**.
- [ ] Choose a build tool version that runs on the JVM provided to the daemon/Maven.
- [ ] Use toolchains to select the JDK executing supported compile/test/Javadoc tasks.
- [ ] Use `--release` when needing to guarantee language level, Java platform APIs, and class target.
- [ ] With Maven, `pom.xml` holds requirements; local `toolchains.xml` or JDK discovery supplies actual JDKs.
- [ ] With Gradle, `java.toolchain.languageVersion` and task-specific launchers are explicitly configured.
- [ ] Do not assume `JAVA_HOME` determines every Java task when toolchains are used.
- [ ] Ensure CI has appropriate JDKs or a configured provisioning resolver, with offline/cache policies.
- [ ] Verify selection via Maven/Gradle task logs; do not look only at `mvn -version`.
- [ ] Inspect class-file target and test on the minimum JDK with the real dependency graph.
- [ ] Manage Gradle wrapper/Maven version, plugin versions, and dependencies alongside the toolchain.
- [ ] Check whether annotation processors, Javadoc, test tools, and plugins are toolchain-aware.
- [ ] Keep personal JDK paths out of source control; use per-machine or CI configuration.
- [ ] Do not treat toolchains as a sandbox, and do not treat them as automatically proving a bit-for-bit reproducible build.

## 18. Official Documentation

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): distinguishing the JDK running Maven from the JDK supplied by toolchain to plugins.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): `toolchain` goal, discovery, and supporting tools.
- [Maven Toolchains — JDK Toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html): `toolchains.xml`, `jdkHome`, version/vendor matching.
- [Maven Toolchains — `toolchain` goal](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchain-mojo.html): selection goal and `validate` phase.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): project/task toolchains, compile/test/Javadoc, detection, provisioning.
- [Gradle — Building Java projects](https://docs.gradle.org/current/userguide/building_java_projects.html): toolchain, `options.release`, and target level.
- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): meaning of `--release`, `-source`, `-target`.

**Conclusion:** Toolchains specify **which JDK provides specific build tools**; the JVM running Maven/Gradle is chosen independently; `--release` dictates **which Java version the output is compatible with**. For a reliable build, configure all three layers, verify the exact executable used by tasks, and run tests on the minimum runtime with actual dependencies — rather than relying solely on `JAVA_HOME` or a version label on `.class` files.
