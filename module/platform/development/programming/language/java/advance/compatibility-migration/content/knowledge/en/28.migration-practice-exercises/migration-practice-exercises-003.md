# Recompiling with --release and Verifying on the Minimum JDK

During a **Java Advance Compatibility Migration**, an organization may use a newer JDK on developer workstations and CI while still committing to running the software on an older JDK. For example, building with **JDK 21**, targeting **Java 17**, and then verifying the artifact on a real **JDK 17 runtime**.

If you simply run the compiler with JDK 21, the output can carry Java 21 classfiles and fail to run on Java 17. If you only use `-source 17 -target 17`, the compiler may still permit calling Java 21 APIs. If you properly use `--release 17` yet never test running on Java 17, the application can still fail due to third-party libraries, plugins, reflection, JNI, or startup flags.

This exercise progresses from minimal Java source to a releasable JAR, combining **passing tests**, **intentional failure tests**, bytecode version checks, and minimum-runtime testing. It then carries those same principles into Maven, Gradle, and CI.

## 1. Learning outcomes

After this lesson, you can:

1. Distinguish the JDK running the build, the compiler JDK, the Java release target, and the minimum runtime JDK.
2. Compile source using `javac --release` and understand language, API, and bytecode restrictions.
3. Use `javap` to determine a classfile's major version.
4. Package an executable JAR and run it on the exact minimum JVM.
5. Observe how `--release` blocks APIs that exist only in a newer JDK.
6. Demonstrate why `-source`/`-target` cannot substitute for `--release`.
7. Detect limitations when third-party dependencies, dynamic loading, and plugins do not fit the minimum JDK.
8. Integrate a verifiable minimum-runtime gate into a pipeline.

Throughout the examples, we choose:

| Component | Version |
|---|---|
| Build machine and compiler | JDK 21 |
| Target for Java source and Java SE API | `--release 17` |
| Committed minimum JDK | JDK 17 |
| Additional JDK for comparison | JDK 21 |
| Application | Small Java SE CLI, no framework needed |

This is an **illustrative combination**, not a claim that every framework/dependency runs on JDK 17. For real projects, cross-check the support matrix first.

## 2. Four values that must not be conflated

A workflow can look like this:

~~~text
CI runner
   |
   +-- Maven/Gradle runs on JDK 21
   |
   +-- javac from JDK 21, with --release 17
   |       |
   |       v
   |    Application classfile target 17
   |       |
   |       v
   |    Package JAR
   |
   +-- Smoke/integration job using JDK 17
   |       |
   |       v
   |    Run the exact JAR just built
   |
   +-- Additional runtime test on JDK 21
~~~

**Build JDK** is the JVM running Maven/Gradle. **Compiler JDK** is the `javac` binary actually generating bytecode, which may be selected via Java toolchains. **Release target** is the language, Java SE API, and classfile level the compiler is instructed to target. **Runtime JDK** is the JVM loading and executing the artifact.

Although in the example both compiler and build tool use JDK 21, these values can be separated in Maven/Gradle toolchains.

### 2.1. Why is runtime testing necessary?

`--release` catches errors at compile time, yet does not execute the software itself. It does not fully check errors that can arise at runtime such as `ServiceLoader`, `Class.forName`, loading JDBC drivers, SSL handshakes, native libraries, or Java agents.

Therefore, at least two layers of evidence are required:

- **Compile gate:** emits output with the right Java release target.
- **Minimum-runtime gate:** runs the exact final artifact on the minimum JVM and executes critical scenarios.

## 3. What can --release do?

The command:

~~~bash
javac --release 17 ...
~~~

instructs the compiler to support targeting Java 17 with respect to:

- **Source language level:** rejects syntax available only in newer Java releases.
- **Classfile target:** produces classfiles corresponding to Java 17.
- **Platform API exposure:** when source is compiled, only Java SE APIs matching release 17 are visible according to the target API data shipped by the compiler.

For instance, Java 21 added `List.getFirst()`; source calling this method must be rejected when compiling with `--release 17`.

### 3.1. --release does not solve every compatibility issue

It does not automatically:

- Downgrade dependency JAR bytecode from target 21 to target 17.
- Check APIs invoked via reflection.
- Guarantee every framework/plugin supports Java 17.
- Select the right Java executable in Docker/systemd/Windows services.
- Supply resource files or native libraries.
- Guarantee identical TLS, timezone, locale, and security providers.
- Verify behavioral contracts or persistence compatibility.
- Bundle a Java 17 runtime with the artifact.

This will be demonstrated in the experiments below.

## 4. Preparing two JDKs

Assume JDK 21 and JDK 17 are installed, with environment variables:

~~~text
JAVA21_HOME = JDK 21 installation directory
JAVA17_HOME = JDK 17 installation directory
~~~

On Bash:

~~~bash
"$JAVA21_HOME/bin/java" -version
"$JAVA21_HOME/bin/javac" -version
"$JAVA17_HOME/bin/java" -version
~~~

On Windows PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\java.exe" -version
& "$env:JAVA21_HOME\bin\javac.exe" -version
& "$env:JAVA17_HOME\bin\java.exe" -version
~~~

Confirm the real compiler is JDK 21 and the real minimum runtime JVM is JDK 17. Simply running `java -version` from `PATH` does not tell you which JDK `javac` or another Java process is using.

No Java 17 locally? You can run the runtime gate on a managed CI runner or JDK 17 container. However, **never mark a check as PASS without actually running the artifact on Java 17**.

## 5. Practice project structure

Create the project:

~~~text
compat-release-lab/
├── src/
│   ├── main/
│   │   └── java/com/acme/compat/CompatDemo.java
│   ├── test/
│   │   └── java/com/acme/compat/CompatSmoke.java
│   └── negative/
│       └── java/com/acme/compat/TooNewApi.java
└── build/
    ├── classes/
    └── test-classes/
~~~

Bash:

~~~bash
mkdir -p src/main/java/com/acme/compat
mkdir -p src/test/java/com/acme/compat
mkdir -p src/negative/java/com/acme/compat
mkdir -p build/classes build/test-classes
~~~

In PowerShell, create equivalent directories via your IDE or `New-Item -ItemType Directory -Force`. File paths and commands in examples run from the `compat-release-lab` root directory.

## 6. Writing an application using a Java 17 API

Create `src/main/java/com/acme/compat/CompatDemo.java`:

~~~java
package com.acme.compat;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.Objects;

public final class CompatDemo {

    private CompatDemo() {
    }

    public static String encode(String value) {
        Objects.requireNonNull(value, "value");
        return HexFormat.of().formatHex(
                value.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) {
        String text = args.length == 0 ? "Java" : args[0];

        System.out.println("input=" + text);
        System.out.println("hex=" + encode(text));
        System.out.println(
                "runtime=" + System.getProperty("java.version"));
    }
}
~~~

`java.util.HexFormat` is a Java SE API available since Java 17. Thus it fits release target 17, yet cannot be used in source targeting Java 11 without an alternative approach.

With input `Java`, the first two lines should be:

~~~text
input=Java
hex=4a617661
~~~

The `runtime` line shows the JVM actually executing the application. It does not replace recording the full vendor/version of the Java executable in CI logs.

## 7. Compiling with JDK 21 using --release 17

On Bash:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

On PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\javac.exe" --release 17 -encoding UTF-8 -d build\classes src\main\java\com\acme\compat\CompatDemo.java
~~~

Explanation:

| Parameter | Meaning |
|---|---|
| `$JAVA21_HOME/bin/javac` | JDK 21 compiler |
| `--release 17` | Java 17 target |
| `-encoding UTF-8` | Source encoding |
| `-d build/classes` | Output directory |
| `.java` filename | Source to compile |

Expected result:

~~~text
build/classes/com/acme/compat/CompatDemo.class
~~~

This is the **compilation** step; it does not yet prove runtime compatibility.

### 7.1. If release version not supported is reported

Example:

~~~text
error: release version 17 not supported
~~~

The usual cause is that the selected `javac` does not support that target. Check:

~~~bash
"$JAVA21_HOME/bin/javac" -version
"$JAVA21_HOME/bin/javac" --help
~~~

Do not simply delete `--release` to make the build green, because then the compiler may emit a default target exceeding the product's minimum JDK.

## 8. Inspecting the classfile with javap

After compiling:

~~~bash
"$JAVA21_HOME/bin/javap" \
  -verbose \
  -classpath build/classes \
  com.acme.compat.CompatDemo
~~~

Find the line:

~~~text
major version: 61
~~~

Milestone table:

| Java release | Classfile major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Even though the compiler runs on JDK 21, `--release 17` creates a Java 17 target classfile (major version 61).

Quick filter on Bash:

~~~bash
"$JAVA21_HOME/bin/javap" -verbose \
  -classpath build/classes \
  com.acme.compat.CompatDemo | grep "major version"
~~~

On PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\javap.exe" -verbose -classpath build\classes com.acme.compat.CompatDemo | Select-String "major version"
~~~

**The right major version is a necessary condition, not proof that the entire app runs.** A runtime dependency might still contain a major 65 classfile or a plugin might call an API missing on Java 17.

## 9. Testing running the class on JDK 17

Bash:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/classes \
  com.acme.compat.CompatDemo Java
~~~

Expected:

~~~text
input=Java
hex=4a617661
runtime=17...
~~~

The `runtime=17...` string depends on the installed Java 17 update version.

If the command succeeds, you have evidence that some behaviors of the current class run on Java 17. Still, we must package a JAR and run the real artifact.

## 10. Packaging an executable JAR from compiled classes

Using JDK 21:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --create \
  --file build/compat-demo.jar \
  --main-class com.acme.compat.CompatDemo \
  -C build/classes .
~~~

List contents:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --list --file build/compat-demo.jar
~~~

The JAR should contain:

~~~text
META-INF/MANIFEST.MF
com/acme/compat/CompatDemo.class
~~~

Now run **the JAR file itself** with Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -jar build/compat-demo.jar Java
~~~

Expect `hex=4a617661` and the Java 17 runtime line as before.

### 10.1. Why package into a JAR and re-test?

In a real project, packaging can drop resources, omit dependencies, write a wrong manifest, use a custom loader, or bundle unexpected classfiles. Verifying only against the compiler output directory does not replace verifying the **final distribution**.

`Main-Class` only specifies the entrypoint. It does not automatically lower classfile versions or package runtime dependencies.

## 11. Adding a plain Java smoke test

Create `src/test/java/com/acme/compat/CompatSmoke.java`:

~~~java
package com.acme.compat;

public final class CompatSmoke {

    public static void main(String[] args) {
        expect("4a617661", CompatDemo.encode("Java"));
        expect("", CompatDemo.encode(""));

        boolean rejectedNull = false;
        try {
            CompatDemo.encode(null);
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }

        if (!rejectedNull) {
            throw new AssertionError(
                    "Null input should be rejected");
        }

        System.out.println("SMOKE_OK");
    }

    private static void expect(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + actual);
        }
    }
}
~~~

The test needs no JUnit, keeping focus on compiler/runtime. It verifies hex output, empty-string handling, and throwing on `null` input.

Compile the test with JDK 21 targeting 17:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -encoding UTF-8 \
  -classpath build/classes \
  -d build/test-classes \
  src/test/java/com/acme/compat/CompatSmoke.java
~~~

Run the test with Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp "build/classes:build/test-classes" \
  com.acme.compat.CompatSmoke
~~~

Windows PowerShell:

~~~powershell
& "$env:JAVA17_HOME\bin\java.exe" -cp "build\classes;build\test-classes" com.acme.compat.CompatSmoke
~~~

Expected:

~~~text
SMOKE_OK
~~~

**Note:** the classpath separator on Unix-like systems is usually `:`, and on Windows is `;`.

### 11.1. Why is compiling tests with target 17 not enough?

Because if the test runner still runs on JDK 21, you have not executed the methods on a Java 17 runtime. Record the exact Java executable that the test process actually uses.

## 12. Negative test: calling a Java 21 API

Create `src/negative/java/com/acme/compat/TooNewApi.java`:

~~~java
package com.acme.compat;

import java.util.List;

public final class TooNewApi {

    public static void main(String[] args) {
        String first = List.of("A", "B").getFirst();
        System.out.println(first);
    }
}
~~~

`List.getFirst()` was added in Java 21 via the sequenced collections APIs; it is absent in Java 17.

Try compiling with JDK 21 while targeting 17:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -d build/negative17 \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

**The expected result is compilation failure**, with a message like:

~~~text
error: cannot find symbol
  symbol:   method getFirst()
~~~

This is a good failure: `--release 17` prevents source from referencing a Java 21 API.

### 12.1. Do not put the negative fixture in the main source set

`TooNewApi.java` sits in a separate `src/negative` folder for this exercise. Putting it into the production source set will make the build fail as expected. In CI, a negative-test step can handle its exit code separately.

## 13. Trying to compile that file with --release 21

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 21 \
  -d build/negative21 \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

On JDK 21, this example compiles successfully because the API is supported.

Run `javap` on the new class:

~~~bash
"$JAVA21_HOME/bin/javap" \
  -verbose \
  -classpath build/negative21 \
  com.acme.compat.TooNewApi
~~~

Expected classfile:

~~~text
major version: 65
~~~

Run with Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/negative21 \
  com.acme.compat.TooNewApi
~~~

Expected outcome is `UnsupportedClassVersionError` because the Java 17 runtime does not support Java 21 target classfiles. This differs from `cannot find symbol` at compile time.

## 14. Distinguishing --release and -source/-target

An older project may use:

~~~bash
javac -source 17 -target 17 ...
~~~

However, these two flags **do not guard the target's Java SE API availability the way `--release` does** when the compiler is a newer JDK.

Try the same `TooNewApi.java` file:

~~~bash
"$JAVA21_HOME/bin/javac" \
  -source 17 \
  -target 17 \
  -d build/unsafe \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

This example can compile under JDK 21: the classfile carries major version 61, yet the bytecode still calls `List.getFirst()`.

Run:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/unsafe \
  com.acme.compat.TooNewApi
~~~

Java 17 reads major 61 classfiles, yet lacks the `List.getFirst()` method. A typical error is:

~~~text
java.lang.NoSuchMethodError
~~~

### 14.1. Comparison table

| Configuration | Bytecode target | Is Java SE API restricted to target? | Important outcome |
|---|---|---|---|
| JDK 21, no target flags | 21 | Follows JDK 21 platform | No Java 17 commitment |
| JDK 21, `-source 17 -target 17` | 17 | Not equivalent to `--release 17` | Can call Java 21 APIs |
| JDK 21, `--release 17` | 17 | Yes | Reduces risk of referencing newer APIs |
| JDK 17, default target | 17 | Follows JDK 17 platform | Runtime tests still required |

If a project intends to support Java 17, prefer `--release 17` or configure the build tool to pass the equivalent option. Do not use `-target` as complete proof of Java SE API compatibility.

## 15. Trying HexFormat with --release 11

The main app uses `HexFormat` (Java 17 API). Try:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 11 \
  -d build/negative11 \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

Expect the compiler to fail to find `java.util.HexFormat` because that API did not exist in Java 11.

This tests consistency of target policy:

- If the minimum JDK is 17, `HexFormat` is valid.
- If the minimum JDK is 11, replace the encode implementation or change the minimum runtime requirement.
- Do not tweak target numbers just to get a green build without checking which Java versions consumers still run.

## 16. Why is the right classfile major version still not enough?

The application can compile for target 17 while carrying a third-party library compiled for target 21.

~~~text
app.jar
  com/acme/app/Main.class        -> major 61

vendor-library.jar
  com/vendor/Feature.class       -> major 65

Java 17 runtime
  -> Main loads
  -> Feature loads when request executes
  -> UnsupportedClassVersionError
~~~

`--release 17` applies only to source currently being compiled for the target. It does not rewrite class files inside dependencies.

### 16.1. Java 21 library example

Create a separate file:

~~~java
package com.acme.lib;

public final class Only21 {
    public static String answer() {
        return "Library built with Java 21";
    }
}
~~~

Suppose it resides at `src/lib21/java/com/acme/lib/Only21.java`. Compile:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 21 \
  -d build/lib21-classes \
  src/lib21/java/com/acme/lib/Only21.java
~~~

Package JAR:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --create \
  --file build/lib21.jar \
  -C build/lib21-classes .
~~~

An application compiling on JDK 21 with `--release 17` can use `lib21.jar` as a compile dependency. The JDK 21 compiler can read the library's classfile, yet **the Java 17 runtime cannot load a major 65 classfile** when code requires it.

Exercise: add a small app calling `Only21.answer()`, compile the app with `--release 17 -classpath build/lib21.jar`, then run on Java 17. Observe the failure and inspect the major version of `Only21.class`. Do not mix this fixture into your green main app.

### 16.2. Takeaways for dependencies

Verify:

- Actual runtime dependencies and transitive versions.
- Minimum Java requirements of frameworks, JDBC drivers, JSON libraries, logging, and agents.
- Classfile versions of suspect libraries.
- Classes loaded only in rarely exercised features.
- Native libraries and operating system requirements.

A `jdeps` report or classfile scan is useful, yet **does not replace runtime integration tests**.

## 17. Reflection and dynamic invocation bypass API guards

Consider:

~~~java
try {
    java.lang.reflect.Method method =
        java.util.List.class.getMethod("getFirst");

    System.out.println("Method present: " + method);
} catch (NoSuchMethodException expectedOnOldJdk) {
    System.out.println("Method not available");
}
~~~

This snippet compiles with `--release 17` because the method name `"getFirst"` is inside a string; the compiler does not treat it as a static invocation of `List.getFirst()`.

At runtime:

- Java 17: reflection does not find the method.
- Java 21: the method can exist.

The same applies to `Class.forName`, `MethodHandle`, Java SPI, plugin discovery, and frameworks loading class names from configuration.

If an application has optional JDK-version-dependent features, test the fallback on the **lowest JDK**, not only the code path running on the newer JDK.

## 18. ServiceLoader and plugins carry distinct risks

An application may call:

~~~java
ServiceLoader<MyService> providers =
    ServiceLoader.load(MyService.class);
~~~

Code compiles with `--release 17`, yet a provider JAR may:

- Be missing from the runtime classpath/module path.
- Have a classfile version higher than 17.
- Use Java 21 APIs in a rare callback.
- Have wrong `META-INF/services` or JPMS `provides` metadata.
- Bundle a conflicting SPI API causing a classloader identity mismatch.

In real migrations, test **the actual provider binaries in use**, not only recompiled internal source.

Unit tests that skip `ServiceLoader` may pass while the application fails when plugin loading starts. Include discovery paths and callbacks in the runtime gate.

## 19. Compiler target does not control Java agents

A Java agent may be attached at launch:

~~~bash
"$JAVA17_HOME/bin/java" \
  -javaagent:/opt/agent/monitoring.jar \
  -jar build/compat-demo.jar
~~~

This is a configuration example: it does not imply the agent file already exists in the lab.

Agents may require their own runtime targets, compatible bytecode libraries, reflection permissions, and different JDK flags. Upgrading the app compiler to JDK 21 does not update the agent; lowering `--release` does not make an old agent support a newer JDK either.

For products with APM/profiler/tracing/security agents, minimum-runtime tests should run with **the real agent configuration** and exercise instrumented classes.

## 20. Maven: setting maven.compiler.release

A Maven project can define:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Or declare directly:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

This is a real plugin version used to illustrate syntax, not a recommendation to always use this version for every Maven/JDK or a claim that it is the latest. Projects must choose per policy and support matrix.

Inspect the Maven process:

~~~bash
./mvnw --version
~~~

Compile:

~~~bash
./mvnw -B clean package
~~~

However, **Maven tests do not automatically run on Java 17 just because the compiler target is 17**. If the Maven process uses JDK 21, tests forked by Surefire/Failsafe may also run on JDK 21 unless a separate Java toolchain/test JVM is configured.

### 20.1. Separate minimum runtime job

You can structure it as:

~~~text
Job Build:
  Maven JVM JDK 21
  maven.compiler.release = 17
  Package app.jar
  Publish checksum + artifact

Job Runtime:
  Java executable from JDK 17
  Download the exact app.jar from Job Build
  Run smoke/integration tests
  Record runtime vendor/build
~~~

This separates a compile pass from a runtime pass.

### 20.2. Maven Jar Plugin

To build a runnable JAR for `CompatDemo`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.4.2</version>
  <configuration>
    <archive>
      <manifest>
        <mainClass>com.acme.compat.CompatDemo</mainClass>
      </manifest>
    </archive>
  </configuration>
</plugin>
~~~

Maven Jar Plugin normally packages only the module's classes/resources. If the app uses external runtime libraries, provide them via an appropriate distribution/launcher or packaging plugin. Do not run `java -jar` on a thin JAR missing dependencies and blame `--release`.

## 21. Maven Toolchains and test plugins

Maven Toolchains can choose JDKs for toolchain-aware plugins. However:

- The JDK running the Maven process has its own requirements.
- The compiler JDK can differ from the Maven runtime JDK.
- `<release>17</release>` does not automatically set the test JVM to Java 17.
- Surefire/Failsafe require separate configuration if the goal is forking tests on the minimum JDK.

An independent verification is running the artifact with the Java 17 executable in a separate CI job. If using toolchains, log the selected toolchain and verify the actual test JVM rather than reading only the POM.

## 22. Gradle: Java toolchain and options.release

In `build.gradle` (Groovy DSL):

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

The configuration expresses clearly:

- Compiles with the JDK 21 toolchain.
- Source, Java SE API, and classfile target are 17.
- The Gradle daemon has its own JVM support constraints.
- Test/JavaExec tasks do not necessarily share the compiler's JVM.

### 22.1. Running Gradle Test on Java 17

With Gradle versions supporting the corresponding APIs, you can declare:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

This configuration requires a JDK 17 toolchain to be provided/discoverable per policy. Do not implicitly assume Gradle chose the right JDK without observing the test setup.

Example commands:

~~~bash
./gradlew --version
./gradlew clean test
~~~

`./gradlew --version` usually reflects the JVM running Gradle, which is insufficient proof for every Test JVM. When needed, log the Java version directly inside the test process or run a smoke check directly on JDK 17.

## 23. Gradle Application Plugin and the final artifact

An application may use:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.acme.compat.CompatDemo'
}
~~~

The Application Plugin can build a distribution via:

~~~bash
./gradlew installDist
~~~

Distributions usually contain JARs, runtime libraries, and startup scripts. Check which runtime the startup script picks when deployed, including `JAVA_HOME` and `PATH`.

A project might compile for target 17 while generated scripts or framework loaders were only tested on 21. Thus minimum-runtime tests must run **the exact releasable distribution**, not just classes under `build/classes`.

## 24. --release and JPMS

If the application has `module-info.java`, the module descriptor is also compiled for the corresponding target release.

Example:

~~~java
module com.acme.compat {
    requires java.logging;
    exports com.acme.compat.api;
}
~~~

Note:

- JPMS began in Java 9; a Java 9+ descriptor cannot be treated as normal under a Java 8 source target.
- Third-party JARs may be explicit modules, automatic modules, or sit on the classpath.
- Module names and `requires` must match.
- `exports`/`opens` affect accessibility/reflection.
- Custom Java runtime images built with `jlink` may omit system modules.
- Module paths in CI may differ from production.

`--release 17` does not replace module resolution tests when launching via `java --module ...`. An app compiled for target 17 can still fail with `FindException: Module ... not found` if the runtime module path lacks an artifact.

## 25. Multi-release JARs cannot be judged by a single classfile

A multi-release JAR may contain:

~~~text
com/acme/codec/Parser.class
META-INF/versions/11/com/acme/codec/Parser.class
META-INF/versions/17/com/acme/codec/Parser.class
META-INF/versions/21/com/acme/codec/Parser.class
~~~

and manifest:

~~~text
Multi-Release: true
~~~

A supporting runtime selects versioned entries according to the corresponding rules. This allows a library to maintain an older baseline while offering optimized implementations on newer JDKs.

Therefore:

- Classfile 65 under `META-INF/versions/21` does not prevent Java 17 from running the JAR.
- If classfile 65 is placed at the base path and Java 17 needs to load it, that is a problem.
- Shading/repackaging must preserve directory structure and manifest metadata.
- Testing on real Java 17 proves version selection picks the right path.

## 26. API compatibility does not equal behavioral compatibility

Even when bytecode and APIs match, runtime can still differ due to:

- Default locale/timezone/charset.
- TLS algorithms, keystores, CA certificates.
- GC/JIT and container memory ergonomics.
- Filesystem paths/permissions.
- Native libraries, OS/architecture.
- Runtime flags or Java agents.
- Reflection behavior or module encapsulation.
- Behavioral changes between framework/library versions.

To reduce reliance on defaults, use explicit charsets:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

However, charset/timezone selection must stay consistent with existing data contracts. Do not alter defaults during migration without confirming current semantics.

## 27. JVM options and startup commands also need verification

Example launch with Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -Xms256m \
  -Xmx512m \
  -Duser.timezone=UTC \
  -jar build/compat-demo.jar Java
~~~

JVM options precede `-jar`. Arguments after the JAR name are passed to the application, unless a framework interprets them specifically.

Misplaced option:

~~~bash
"$JAVA17_HOME/bin/java" -jar build/compat-demo.jar -Xmx512m
~~~

Here `-Xmx512m` is just an application argument. A JVM option unsupported by JDK 17 can cause the launcher to fail before `main` runs, even when classes compile cleanly with `--release 17`.

## 28. Runtime testing with the exact production artifact

A minimum-runtime smoke test should:

1. Take the final CI-built artifact, without rebuilding another copy in the test step.
2. Record the SHA-256 or checksum of that artifact.
3. Select the Java executable from the specific JDK 17.
4. Run minimal startup/health/CLI or API scenarios.
5. Check stdout/stderr and exit codes.
6. Verify resources/dependencies actually loaded.
7. Run critical integration paths: DB, HTTP, broker, TLS, plugins.
8. Test graceful shutdown if it is a service.
9. Record JDK version and runtime environment in the report.

If the lab runs only `CompatDemo` with no external integrations, a PASS proves only a simple CLI flow. It does not mean an enterprise service with Hibernate, Spring, Kafka, and JDBC has been tested.

### 28.1. Compile once, test across runtimes

~~~text
Commit X
   |
   v
Build with JDK 21, --release 17
   |
   v
Artifact SHA-256 = H
   |
   +--> Java 17 runtime test (artifact H)
   |
   +--> Java 21 runtime test (artifact H)
   |
   v
Release only after required gates
~~~

If each runtime job compiles its own artifact with its own JDK, the team is no longer comparing the exact same binary distribution.

## 29. Suggested test matrix

| Compiler | Target | Runtime | Expected outcome |
|---|---|---|---|
| JDK 21 | `--release 17` | Java 17 | **Must pass** for supported scenarios |
| JDK 21 | `--release 17` | Java 21 | Passes if product supports runtime 21 |
| JDK 17 | Default release 17 | Java 17 | Optional baseline |
| JDK 21 | `--release 21` | Java 17 | Expected failure due to classfile 65 |
| JDK 21 | `--release 17`, calls `List.getFirst()` | Not run | Intentional compile failure |
| JDK 21 | `-source 17 -target 17`, calls API21 | Java 17 | May compile yet fails at runtime |

Intentional failure scenarios are **negative tests**, not signs that production pipelines should accept failures.

## 30. Minimal CI pipeline

A pipeline can be split into:

~~~text
STAGE A — Verify toolchains
  - Actual build compiler is JDK 21
  - Actual test runtime is JDK 17

STAGE B — Build immutable artifact
  - Compile --release 17
  - Package
  - Save artifact SHA-256

STAGE C — Static checks
  - Inspect classfile target
  - Inspect dependency versions/minimum Java
  - Report suspicious classes and APIs

STAGE D — Minimum runtime test
  - Run artifact on Java 17
  - Run smoke, contract, integration tests
  - Verify startup/shutdown and exit status

STAGE E — Additional runtime test
  - Run exact same artifact on Java 21

STAGE F — Release decision
  - Save evidence and unresolved risks
  - Block release if mandatory Java 17 gate fails
~~~

A small Bash script for the lab:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p build/classes

"$JAVA21_HOME/bin/javac" --release 17 \
  -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/acme/compat/CompatDemo.java

"$JAVA21_HOME/bin/jar" --create \
  --file build/compat-demo.jar \
  --main-class com.acme.compat.CompatDemo \
  -C build/classes .

"$JAVA17_HOME/bin/java" \
  -jar build/compat-demo.jar Java
~~~

This is a skeleton; it does not yet assert full output or run integration scenarios. Real pipelines must check exit codes, data expectations, and dependencies.

## 31. Dependency graph and minimum supported Java

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
~~~

These commands reveal resolved versions, yet do not by themselves prove a library supports Java 17.

Also verify:

- Vendor/framework support matrix.
- Minimum-Java requirements documented in release notes/docs.
- Classfile inspection when mismatches are suspected.
- Tests for dynamic paths.
- Packaged runtime classpath/module path tests.
- Native/JNI compatibility where applicable.
- Agent/plugin compatibility with the minimum JDK.

A library compiled for target 21 does not become Java 17 compatible simply because the application uses `--release 17`.

## 32. Troubleshooting table

| Symptom | Common cause | What to check |
|---|---|---|
| `release version 17 not supported` | Wrong/too old compiler | `javac -version` |
| `cannot find symbol: getFirst` with release 17 | Java 21 API properly blocked | API target and source |
| `cannot find symbol: HexFormat` with release 11 | API exists only from Java 17 | Minimum Java policy |
| `UnsupportedClassVersionError` | Bytecode newer than JVM supports | `javap` on app/dependencies |
| `NoSuchMethodError` | API absent at runtime or binary mismatch | Source/target/API/versions |
| `NoClassDefFoundError` | Missing runtime dependency or init failure | Classpath and root cause |
| `ClassNotFoundException` | Dynamic class loading cannot find class | Loader/plugin/resource |
| `ServiceConfigurationError` | Provider SPI/ServiceLoader failure | Service descriptors/JPMS |
| `InaccessibleObjectException` | Reflection/module boundaries | Library version, opens |
| CI passes yet Java 17 fails | Tests ran on JDK 21 or missing coverage | Actual test JVM |
| Container fails yet local passes | Different image JDK/native/config | Dockerfile, launch flags |
| Main passes, batch job fails | Dependency loaded only in rare path | Integration coverage |

Do not read an exception in isolation. Confirm JVM version, artifact checksum, runtime dependencies, and exact execution steps when the error occurred.

## 33. Extension exercise A: lowering minimum to Java 11

Using the same `CompatDemo.java`, try:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 11 \
  -d build/release11 \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

Expected: fails because `HexFormat` is absent in Java 11.

Requirements:

1. Replace the `encode` implementation with Java 11 APIs or compatible plain code.
2. Preserve hex output `4a617661`.
3. Compile with `--release 11`.
4. Run on a real Java 11 runtime if that is the required target.
5. Do not alter business behavior when downgrading platform APIs.

## 34. Extension exercise B: testing a Java 21 library with a Java 17 app

Create the `Only21` library as shown, then an application calling `Only21.answer()`. Compile the application using JDK 21 with `--release 17`, leaving the target-21 library on the compiler classpath.

When running on Java 17, identify which classfile actually causes the error and demonstrate that the library was not automatically downgraded. Then propose one of these options:

- Select a library version supporting Java 17.
- Replace the API/library with a compatible implementation.
- Raise the minimum runtime through an approval process, announcing a breaking change.
- Split the Java 21-dependent component into a separate service if architecture allows.

Do not resolve it by deleting the Java 17 runtime test.

## 35. Extension exercise C: adding gates to CI

Design two jobs:

**Build job** uses JDK 21, compiles with `--release 17`, packages an immutable artifact, and publishes its checksum.

**Minimum-runtime job** uses JDK 17, downloads that exact artifact, verifies the Java executable, runs smoke/integration tests, and saves output.

Additional requirement: if JDK 17 is unavailable or tests cannot run, the result must be **BLOCKED/FAILED**, never PASS. If only classfile checks ran, explicitly record `Runtime NOT EXECUTED`.

## 36. Extension exercise D: analyzing a dynamic dependency

Pick a plugin, JDBC driver, or framework extension from a current project and answer:

- Which artifact/version is actually deployed?
- What is its minimum JDK requirement?
- Is it loaded at startup or upon feature invocation?
- Are `ServiceLoader`/reflection/module paths involved?
- Are any Java agents or bytecode transformers present?
- Which test must run on the minimum JDK to force that class to load?
- Is there a way to log class source and Java runtime upon failure?

This exercise bridges Java SE demos to enterprise migration.

## 37. Lab completion evidence sheet

After practice, a report can record:

~~~text
Project: compat-release-lab
Build JDK: 21 (actual vendor/update)
Compiler command: javac --release 17
Application classfile major: 61
Artifact: build/compat-demo.jar
Artifact SHA-256: <recorded from checksum tool>
Minimum runtime: Java 17 (vendor/update)
Java 17 smoke result: SMOKE_OK
Java 21 API negative test: compile failed as expected
Java 21 bytecode on Java 17: failed as expected
Dependency scan: <actual result>
Integration scenarios: <tested or NOT TESTED>
Remaining risks: <specify concretely>
~~~

Fields in angle brackets must be filled with **actual** measured data. The lesson does not claim the commands above were executed in the learner's environment.

### 37.1. Why save checksums?

If the Build job and Runtime job use two different artifacts despite having the same filename, passing tests do not prove the right artifact is being released. Checksums/digests tie test results to a specific binary.

## 38. Production project checklist

- [ ] Identified minimum JDK per product policy.
- [ ] Identified the JDK running Maven/Gradle and the actual compiler JDK.
- [ ] Verified compiler supports the selected `--release` target.
- [ ] Set consistent release target in Maven/Gradle.
- [ ] Verified major version of application classes.
- [ ] Avoided static references to Java SE APIs beyond the minimum target.
- [ ] Checked third-party/runtime/transitive dependencies.
- [ ] Checked bytecode tooling, agents, and plugins.
- [ ] Checked `ServiceLoader`/reflective/dynamic loading.
- [ ] Checked resources, classpath/module path, and packaging.
- [ ] Executed the final artifact on the minimum runtime JDK.
- [ ] Ran smoke and critical integration tests on the minimum JVM.
- [ ] Verified database, TLS, serialization, and external contracts.
- [ ] Verified JVM flags, environment, and native libraries.
- [ ] Used the same artifact across different Java runtime tests.
- [ ] Recorded checksum, JDK vendor/update, dependency versions, and test results.
- [ ] Accurately marked untested scenarios.
- [ ] Prepared rollback artifact/runtime in case of regression.

## 39. Common misconceptions

**"Building with JDK 21 forces the artifact to require Java 21."** Not necessarily: `--release 17` lets the compiler generate Java 17 target output.

**"`-source 17 -target 17` already blocks Java 21 APIs."** Incomplete. This is why `--release` is needed.

**"Major version 61 means every dependency runs on Java 17."** False. You must inspect runtime libraries and dynamically loaded classes.

**"`--release 17` means no need to install Java 17 for testing."** False if the product commits to Java 17 runtime support.

**"Maven/Gradle running on Java 21 means tests ran on Java 17."** False. The test JVM must be selected and verified separately.

**"The compiler automatically recompiles third-party JARs down to Java 17."** False.

**"Reflection is checked just like direct method calls."** False. Class/method names in strings may be resolved only at runtime.

**"Running main is enough."** False; an API/plugin may be loaded only when a user invokes a specific feature.

**"A JAR running on Java 21 proves it runs on Java 17."** False, even if application classfiles target 17.

## 40. Conclusion

In Java Advance Compatibility Migration, **`--release` is the compile-time tool to constrain language, Java SE APIs, and bytecode to the target JDK**, stronger than using `-source`/`-target` alone when the compiler runs on a newer JDK.

However, **minimum supported JDK** is a commitment to real runtime behavior. Therefore, package the complete artifact, verify dependencies, and run that exact artifact on the lowest supported JVM, accompanied by smoke, integration, plugin, and contract tests.

Recommended workflow:

~~~text
Identify minimum JDK
         |
         v
Build with new JDK + --release <minimum>
         |
         v
Package one artifact and save checksum
         |
         v
Inspect classfiles and dependencies
         |
         v
Run that artifact on the real minimum JDK
         |
         v
Smoke + integration + contract tests
         |
         v
Save evidence, release with rollback
~~~

**Compiling to the right target is the first step; only when the actual artifact is executed and verified on the minimum JDK does the compatibility commitment have a sound foundation.**
