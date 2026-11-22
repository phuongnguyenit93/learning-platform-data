# Distinguishing Tool JDK, Source Language, and Target Class Versions When Compiling Java

## 1. Three Different Questions in a Build

A Java project often says “uses Java 17”, but this statement is not enough to know whether the build is compatible with Java 17. It is necessary to distinguish **three version axes**:

1. **Tool JDK (*compiler/toolchain JDK*)**: the JDK installation that actually provides the running `javac`, for example JDK 24. It determines which source/target levels the compiler supports, and which options and bug fixes it has.
2. **Source language (*source language level*)**: the Java syntax constructs that source code is allowed to use, for example Java 17. It is controlled via `-source 17`, `--source 17`, or indirectly via `--release 17`.
3. **Target class (*target class-file level*)**: the generated JVM bytecode format, for example class-file major version **61** for Java 17. It is controlled via `-target 17`, `--target 17`, or `--release 17`.

There is **a fourth axis to check** if you want to actually run it: **the Java SE/JDK API platform that the code is allowed to reference**. `-source` and `-target` **do not automatically restrict** the standard APIs present on the compiler JDK. `--release` is usually the right way to simultaneously constrain source language, target class file, **and the platform APIs of the target release**.

| What to determine | Example | Option/check |
| --- | --- | --- |
| Which compiler runs? | `javac 24.0.2` | `javac -version`, JDK toolchain configuration |
| Which source syntax is allowed? | Java 17 | `-source 17`, `--release 17` |
| Which generation does the output class file belong to? | Major 61 = Java 17 | `-target 17`, `--release 17`, `javap -verbose` |
| Which standard APIs are called? | Java SE 17 | `--release 17` helps restrict APIs |
| Which version is the actual runtime? | `java 17` or `java 21` | `java -version`, launcher/container, and CI |

For example, **`javac` from JDK 24 compiling source code according to Java 17 and generating Java 17 bytecode** is completely valid. That does **not** mean the machine uses JDK 17 to compile. Conversely, using JDK 24 does **not** force the application to run only on Java 24.

## 2. Relationship Between Tool, Source, Target, and API Versions

### 2.1. Tool JDK: who performs the compile process?

`javac` is the compiler program belonging to the JDK, not the JVM runtime that runs the application after building. Newer JDKs can usually compile for several older releases, but **do not indefinitely support all previous releases**. Check the `Supported releases` list in:

~~~bash
javac -version
javac --help
~~~

A machine can have multiple JDKs installed; `javac -version` and `java -version` sometimes point to **two different installations** due to `PATH`, `JAVA_HOME`, IDE, Maven/Gradle toolchain, or container. When debugging, you must inspect the compiler **actually** selected by the build tool, rather than inferring from a separate terminal.

For libraries compiled via Maven/Gradle, the JDK version running the build tool itself can also differ from the JDK that the `JavaCompile` task selects via toolchain. In CI, check both if there are plugins that depend on the JDK version.

### 2.2. Source language level: which language is valid?

`-source 17` tells the compiler to check Java 17 language rules. It determines whether source code can use syntax introduced in newer Java versions. For example:
- `record` has been a standard feature since Java 16, so it is valid with `-source 17`.
- Pattern matching for `switch` was finalized as a standard feature in Java 21, so it cannot be used as standard Java 17 syntax.
- *Preview* features can only be used under dedicated rules; they are not automatically enabled by `-source` alone.

`-source` is not a parameter for selecting the compiler JDK. A JDK 24 can still run the compiler with `-source 17`.

### 2.3. Target class-file level: which bytecode format is generated?

`-target 17` requires the output to have the class-file version for Java 17. A JVM that is too old will refuse to load a class file with a major version newer than what it supports.

Common milestones:

| Java release | Class-file major version |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 18 | 62 |
| 19 | 63 |
| 20 | 64 |
| 21 | 65 |
| 22 | 66 |
| 23 | 67 |
| 24 | 68 |

For Java 9 and above, the major version increases by one per release: **major = release + 44**. This is a mnemonic for modern Java generations, not a substitute for checking with `javap -verbose`.

On Java 17, normal class files usually have **major 61, minor 0**. In some cases, class files using preview features have **minor 65535**; preview classes are subject to separate execution rules and cannot be treated the same as ordinary 61.0 classes.

### 2.4. API platform level: the most easily overlooked part

Suppose you use JDK 24 to compile with:

~~~bash
javac -source 17 -target 17 ApiDemo.java
~~~

These two options check Java 17 syntax and produce major 61 bytecode. However, without restricting the platform, the compiler can still see Java 24 APIs in the system modules of **JDK 24**.

A call to a new API can be compiled into Java 17 bytecode for which **a Java 17 runtime has no corresponding method/class**. The result may be `NoSuchMethodError`, `NoClassDefFoundError`, or another linkage error when running on Java 17, depending on the API used.

That is why **`--release 17` is safer than `-source 17 -target 17`** for most projects that need to run on Java 17: it also uses the Java SE/JDK API set corresponding to release 17 when resolving supported platform APIs.

## 3. Rules of `javac`: which configuration to choose?

| Command | Compiler JDK | Source syntax | Class target | Java SE/JDK API controlled by target? |
| --- | --- | --- | --- | --- |
| `javac App.java` | Invoked JDK | Compiler default | Compiler default | Matches invoked JDK |
| `javac -source 17 -target 17 App.java` | Invoked JDK | Java 17 | Java 17 | **Not guaranteed** |
| `javac --release 17 App.java` | Invoked JDK, must support release 17 | Java 17 | Java 17 | **Yes**, for platform APIs controlled by `--release` |
| JDK 17 + `javac --release 17 App.java` | JDK 17 | Java 17 | Java 17 | Yes |
| JDK 24 + `javac --release 17 App.java` | JDK 24 | Java 17 | Java 17 | Yes |

**Important limitations:**
- `--release 17` does not install JDK 17 and does not change the running `javac` to version 17.
- `--release` **cannot be used together** with `-source` or `-target` in the same invocation.
- With `-source` / `-target`, **target cannot be lower than source**. For example, `-source 21 -target 17` is rejected by `javac`: the compiler does not promise to convert all Java 21 semantics/syntax into Java 17 bytecode that way.
- Newer compilers only support a **finite set** of older releases. If the requested release is not listed by `javac --help`, you must choose an appropriate JDK/toolchain.
- `--release` does not automatically verify **third-party dependencies**: if a dependency is compiled for Java 21, configuring the application's output for Java 17 does not guarantee that dependency will run on Java 17.
- `--release` also imposes restrictions on accessing internal/non-exported APIs of system modules. The `--add-exports` option cannot be used to bypass system packages of the target platform release when constrained by `--release`.

When the goal is to **actually run on Java 17**, a good starting point is:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/VersionDemo.java
~~~

Then test on an **actual Java 17 runtime**, including dependencies, instead of relying solely on the class-file version.

## 4. Experiment 1: JDK 24 Compiling to Java 17 Classes

Create **`src/VersionDemo.java`** with the full contents:

~~~java
public class VersionDemo {
    public static void main(String[] args) {
        System.out.println("Hello " + "Java");
    }
}
~~~

In the directory containing `src`, use a JDK that supports `--release 17`:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/VersionDemo.java
java -cp out VersionDemo
javap -verbose -classpath out VersionDemo
~~~

On Windows PowerShell, you can use `New-Item -ItemType Directory -Force out` instead of the directory-creation command. Application output:

~~~text
Hello Java
~~~

In the `javap -verbose` output of this class, look for:

~~~text
minor version: 0
major version: 61
~~~

Even though the compiler verified in the experiment is **`javac 24.0.2`**, the Java 17 output still has **major version 61**. That is concrete proof that **compiler JDK version** and **class target version** are not identical.

The command `java -cp out VersionDemo` runs using the `java` selected by the shell. To conclude that the application truly runs on Java 17, you must run it using the **`java` binary from JDK/JRE 17** and verify that `java -version` reports that exact version.

## 5. Experiment 2: `-source/-target` Can Still Use Newer APIs

The `Thread.ofVirtual()` API is a standard API present in Java 21, **not present in Java 17**. Use JDK 21 or higher to reproduce (for example, results verified with JDK 24).

Create **`src/ApiDemo.java`**:

~~~java
public class ApiDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = Thread.ofVirtual().start(
                () -> System.out.println("virtual"));
        thread.join();
    }
}
~~~

This is a standalone Java file. The experiment's goal is to illustrate the **API guardrail**; because the program uses a newer API, it should not be considered a Java 17-compatible program.

### 5.1. Setting only source/target 17

~~~bash
mkdir -p out-legacy
javac -source 17 -target 17 -encoding UTF-8 -d out-legacy src/ApiDemo.java
~~~

On `javac 24.0.2`, this command **compiles successfully (exit 0)** but emits a warning because Java 17 system modules have not been configured accordingly:

~~~text
warning: [options] location of system modules is not set in conjunction with -source 17
  not setting the location of system modules may lead to class files that cannot run on JDK 17
    --release 17 is recommended instead of -source 17 -target 17 because it sets the location of system modules automatically
1 warning
~~~

`javap` still shows **major 61**, but the bytecode references `Thread.ofVirtual()`, which Java 17 does not provide. If that exact code path executes on a Java 17 JVM, a **`NoSuchMethodError`** linkage error may occur. There is no contradiction: the class 61 format is valid for Java 17, but **the referenced API is incompatible**.

The exact warning may vary by JDK; the technical point to grasp is that `-source`/`-target` does not replace platform API checking.

### 5.2. Using `--release 17`

~~~bash
mkdir -p out-release
javac --release 17 -encoding UTF-8 -d out-release src/ApiDemo.java
~~~

In the experiment with `javac 24.0.2`, the command fails as expected because Java 17 does not have this method:

~~~text
error: cannot find symbol
        Thread thread = Thread.ofVirtual().start(
                              ^
  symbol:   method ofVirtual()
  location: class Thread
1 error
~~~

Paths and line numbers in the diagnostic have been omitted to focus on the error content. This is the **desired result**: the configuration detects APIs that do not exist on the target release right at compile time.

If the actual target is Java 21 or newer, you can choose `--release 21` and a Java 21+ runtime, with a compiler new enough to support that release. Do not “fix” it by reverting to `-source 17 -target 17` while still intending to run on Java 17.

## 6. Experiment 3: Syntax Newer Than Target Is Rejected

Even with Java source that uses no special features, you can still intentionally pass two inconsistent levels:

~~~bash
javac -source 21 -target 17 src/VersionDemo.java
~~~

On `javac 24.0.2`, the compiler returns the diagnostic:

~~~text
error: specified target release 17 is too old for the specified source release 21
  --release 17 is recommended when compiling code to run on JDK 17
~~~

This command intentionally **fails**; there is no usable valid class output. The compiler does not promise to *backport* Java 21 language constructs to a Java 17 runtime by setting an arbitrarily lower target. If the same codebase needs to run on Java 17, the source code must adhere to a compatible language level or require a specialized transformation process with clear limitations.

## 7. Reading Class-File Version and Distinguishing It from Runtime Compatibility

When the class already exists, use:

~~~bash
javap -verbose -classpath out VersionDemo
~~~

Or for a JAR with packaged classes:

~~~bash
javap -verbose -classpath application.jar com.example.Main
~~~

Look for `major version` and `minor version`. This is data **from the actual file**, more useful than guessing from `pom.xml` or IDE messages.

If the runtime is older than the class-file major version, the JVM may report:

~~~text
java.lang.UnsupportedClassVersionError
~~~

The message usually includes the two numbers for the class-file version required by the class and the maximum supported by the runtime. The solution is to use a sufficiently new runtime **or** recompile for a supported release, while fixing any incompatible APIs and dependencies.

**However, a matching major version is only a necessary condition.** The build can still fail to run because of:
- Calling Java SE/JDK APIs newer than the target release due to using only `-source/-target`.
- A dependency JAR having a class-file major version newer than the target.
- Dependencies on native libraries/JNI, module exports, third-party libraries, service providers, or other runtime configurations.
- Using a preview feature with **minor 65535** requires the corresponding matching-release runtime and appropriate flags; it must not be treated as stable bytecode for older JVMs.
- Checking only a few classes; the JAR contains other classes compiled with a newer target.

In large applications, you should check all required modules and dependencies, not just `Main.class`.

## 8. What Does `--release` Guarantee and What Does It Not Guarantee?

**For Java SE/JDK APIs:** `--release N` selects the language rules of release N, the class-file target of N, and the platform APIs supported in release N. It helps catch errors like `Thread.ofVirtual()` in the Java 17 example right at compile time.

**For third-party libraries:** `--release N` does not “downgrade” the bytecode version or APIs of dependency JARs. An application class targeting 17 can still call into a library that only works on Java 21 if the build is misconfigured or lacks dependency verification. You must use a dependency version that declares Java 17 support and test it directly on JDK 17.

**For runtime behavior:** the same class 61 can behave differently across Java 17, 21, and 24 due to API implementations, defaults, environment, operating system, or compatibility behavior changes. Compatibility testing is still necessary.

**For preview features:** `--enable-preview` must accompany a source/release level matching **the JDK version running the compiler** according to `javac`'s support rules; you cannot use JDK 24 to compile a Java 17 preview feature just with `--release 17 --enable-preview`. Classes containing preview features have their own runtime constraints. If you want to distribute a library widely, you should avoid depending on preview features unless product requirements allow it.

**For internal APIs:** `--release` is designed to restrict public/valid platform APIs by release, and does not allow arbitrary use of unexported `jdk.internal.*` or `com.sun.*` APIs. Projects that use compiler internals need separate documentation and build paths; `--release` cannot be treated as a tool supporting those APIs.

## 9. Configuration in Maven

With **Maven Compiler Plugin 3.6+** and a compiler JDK supporting `--release`, you can declare in `pom.xml`:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This is **part of an existing POM**, not a standalone POM. The `maven.compiler.release` property instructs the plugin to pass the appropriate release level to the compiler. If you want to set it directly:

~~~xml
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
    </plugins>
</build>
~~~

This is also just a **configuration snippet inside `<project>`**, with a specific plugin version shown for illustration; when applying it, use the plugin version vetted by the project or a version suitable for the current build.

Checking which JDK Maven selects:

~~~bash
mvn -version
mvn clean compile
~~~

`mvn -version` reflects the JVM running Maven, whereas the Maven Toolchains Plugin/compiler configuration can specify a different JDK to invoke `javac`. If the project uses toolchains, inspect the toolchain configuration and compiler logs. Do not conclude the compiler JDK solely from `JAVA_HOME` if the build has multiple layers of JDK selection.

In multi-module Maven, you must ensure each module matches the target of the final artifact. A Java 17 module directly using a Java 21 library module will not automatically become compatible just because the app sets `maven.compiler.release=17`.

## 10. Configuration in Gradle: Toolchain and Release Are Two Separate Things

In Gradle, **Java toolchain** selects the JDK for compiling; **`options.release`** determines the Java release that source/classes/platform APIs target. You can configure **JDK 21 to compile while targeting Java 17**.

With Groovy DSL (`build.gradle`):

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
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

With Kotlin DSL (`build.gradle.kts`):

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
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

Both snippets are **standalone build configurations for a Gradle Java project**, not Java code. Conditions: the versions of Gradle and the Java plugin being used support the selected toolchain; JDK 21 must be available or Gradle must be configured for provisioning. When a processor/plugin needs a newer JDK, the execution capability of the build tools must be considered separately.

If you only write:

~~~groovy
sourceCompatibility = '17'
targetCompatibility = '17'
~~~

it only expresses language/target compatibility via the older mechanism, **does not restrict APIs** as strictly as `options.release`, and also does not guarantee the compile JDK is 17. Prefer `options.release = 17` and an explicit toolchain when both reproducibility and ability to run on the target Java version are needed.

Verification:

~~~bash
./gradlew --version
./gradlew clean compileJava
~~~

On Windows, use `gradlew.bat`. `./gradlew --version` shows Gradle's JVM, which is not sufficient to verify the task's compiler when a toolchain is configured; check compile logs/config and actual class-file versions.

## 11. Choosing Configuration by Goal

| Goal | Recommendation | Why |
| --- | --- | --- |
| Build with JDK 17, run on Java 17 | JDK toolchain 17 + `--release 17` | Reproduces the compiler JDK and controls syntax/class/API |
| Build with JDK 21, run on Java 17 | Toolchain 21 + `--release 17` | Uses a newer compiler while targeting an older platform |
| Build with JDK 24, run on Java 21 | Toolchain 24 + `--release 21` | Source, bytecode, and API follow Java 21 |
| Need Java 21 language features | `--release 21` + Java 21+ runtime | Cannot use standard Java 21 features with a Java 17 target |
| Use Java 21 APIs from Java 17-style source | **Cannot be considered Java 17 compatible** | Older source syntax does not bring new APIs back to older releases |
| Library project needing wide distribution | Choose the minimum supported runtime, compile with matching `--release`, test on the lowest version | Avoids introducing newer classes/APIs into the artifact |

The toolchain JDK can be higher than the target release, but **you cannot choose a `--release` higher than the releases the compiler supports**. For instance, `javac 17` does not know Java 21 features and cannot run `--release 21`; a sufficiently new compiler must be used.

## 12. Common Errors and How to Identify Them

### 12.1. `invalid source release` / `release version ... not supported`

The compiler JDK is **too old** or the requested release is not supported by the compiler. For example, invoking the JDK 17 compiler with `--release 21` will be rejected. Check `javac -version`, `javac --help`, and the actual Maven/Gradle toolchain; upgrade to an appropriate JDK toolchain or choose a supported release.

### 12.2. `UnsupportedClassVersionError`

The JVM is **too old to load the class file** (or a preview class has special rules). Check major/minor via `javap -verbose`, the runtime `java -version`, JARs on the runtime path, and which dependency is actually loaded.

### 12.3. `NoSuchMethodError` even though the class target is right

The application or library references a method not present in the actual runtime API/class. If compiled with `-source/-target` on a newer JDK, check for **accidental use of newer Java APIs**. Additionally, the error can be caused by two inconsistent versions of a third-party library between compile and runtime classpaths; `--release` does not fix library version mismatches.

### 12.4. Compiles in the IDE but fails to compile in CI

The IDE and CI may select two different `javac` binaries, two different Gradle/Maven JDKs/toolchains, or two different `--release` levels. Read the invocation logs and build configuration in the repository; run a clean build. Do not just edit “Project language level” in the IDE while neglecting the main build configuration.

### 12.5. Preview feature works at compile time but fails at runtime

Preview classes can carry class-file minor 65535 and require `--enable-preview` on a runtime of the corresponding Java release. Compiling with `--enable-preview` does not turn a preview feature into a stable API for older releases. For production builds with minimum runtime requirements, manage preview features as a very strict version dependency.

### 12.6. Library class is too new

An application artifact targeting Java 17 may pull in JARs from libraries compiled for Java 21. When a Java 17 runtime loads the library's classes, it may reject major 65. Check the minimum Java requirement of each dependency and its class-file version; select a compatible library version or raise the minimum runtime.

## 13. Checklist for Verifying a Build Actually Runs on Target Java

1. **Verify the compiler**: run `javac -version` or check the compiler/toolchain in Maven/Gradle logs, avoiding confusion with the build tool's runtime.
2. **Verify configuration**: prefer `--release N`; do not mix with `-source/-target`. Set `-encoding UTF-8` when source files are saved as UTF-8.
3. **Compile from a clean state**: avoid letting old classes compiled with a different target slip into the artifact.
4. **Inspect bytecode**: run `javap -verbose` on representative classes; check critical classes and dependency modules as needed.
5. **Verify APIs**: check that compilation does not call Java SE APIs newer than the target release; check library dependencies as well.
6. **Run on the actual target runtime**: for example, if supporting Java 17, there must be a test job running `java` 17, not just running on JDK 24.
7. **Check dependencies/classpath/module path**: JARs must have appropriate versions and minimum Java requirements; not just the classes of the main module.
8. **Run integration tests**: serialization, reflection, service loading, networking, security providers, and native dependencies can expose runtime differences.
9. **Pin CI and toolchains**: record JDK vendor/version, build plugin versions, `--release`, and test environment so builds are reproducible.
10. **Inspect the final artifact**: classes inside the fat JAR, module JAR, distribution, or container image are what actually gets deployed; avoid confusing them with intermediate outputs.

## 14. Self-Check

**Question 1.** Using `javac 24` with `--release 17`, what major version does the bytecode carry?  
**Answer:** **61**, corresponding to a Java 17 class file; the compiler is still JDK 24.

**Question 2.** Can you run `javac 17 --release 21`?  
**Answer:** **No.** The JDK 17 compiler does not support the Java 21 release.

**Question 3.** Why can `-source 17 -target 17` produce an application that fails to run on a Java 17 JVM?  
**Answer:** These two options do not automatically restrict the standard APIs of the compiling JDK; the code may reference APIs newer than Java 17.

**Question 4.** What is the preferred way for a newer compiler to check Java 17 syntax, bytecode, and APIs simultaneously?  
**Answer:** `--release 17`, if the compiler supports that release.

**Question 5.** If `javap` shows `major version: 61`, is that enough to prove the application is completely Java 17 compatible?  
**Answer:** **Not yet.** You need to examine APIs, dependencies, preview features, and run tests on Java 17.

**Question 6.** Is `source=21, target=17` a way to backport Java 21 to Java 17?  
**Answer:** **No.** `javac` rejects a target lower than the source.

**Question 7.** Do Gradle toolchain JDK 21 and `options.release = 17` conflict with each other?  
**Answer:** **No.** Toolchain selects the compiler; release selects the target language/bytecode/API platform.

**Question 8.** The application has class 61 but a dependency has class 65; can the whole bundle be deployed on Java 17?  
**Answer:** **Cannot be guaranteed**; when class 65 needs to be loaded, a Java 17 JVM does not support that format. Choose a compatible dependency or change the minimum runtime.

## 15. Official Documentation

- [Oracle javac command — `--release`, `--source`, `--target`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [JVMS 17, §4.1 — ClassFile structure and major version](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle Java toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

**Takeaway:** **Tool JDK** is which compiler is run; **source level** is which syntax is written; **target level** is which JVM generation the class file is for. To genuinely build for Java N, also control **platform APIs** with `--release N`, inspect libraries, and run tests on an **actual Java N runtime**.
