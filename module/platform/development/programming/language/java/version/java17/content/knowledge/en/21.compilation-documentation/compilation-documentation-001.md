# javac --release 17 and Target API Boundaries

When compiling a Java 17 application, setting only the syntax level or bytecode format is not enough to guarantee that the program can run on Java 17. A newer compiler can see new JDK APIs that the Java 17 runtime does not yet have. If the code calls those APIs, the class file may still use a bytecode format compatible with Java 17, yet fail at runtime because a method or class is missing.

The **javac --release 17** option solves this problem by synchronizing three critical constraints:

1. The Java language level used during compilation is set to Java 17.
2. Generated class files follow the Java 17 format.
3. The compiler only allows references to platform APIs supported and exported for Java 17.

The third point is the crucial difference compared to using only **-source 17 -target 17**. The **--release** option detects calls to APIs that only exist in newer JDKs right at compile time. This is the right choice when building on a newer JDK while the product must run on Java 17.

## 1. What does --release 17 do?

The **--release N** option instructs javac to compile source code for Java SE version N. With --release 17, the compiler applies:

- Java 17 language and syntax rules.
- The Java 17 class file format, with major version 61.
- The set of platform APIs published and supported for Java 17.

Example:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

If the source uses syntax introduced in a Java version newer than 17, the compiler rejects it. If the source calls a method or uses a platform class that only appeared after Java 17, the compiler rejects that as well.

The --release option has been available since JDK 9. With JDK 17, you can target releases supported by that compiler, including Java 17. A compiler can only compile for releases that it supports itself; JDK 17 cannot target Java 21, whereas a newer JDK can use --release 17 to produce artifacts for Java 17.

### Example of compiling a Java 17 program

~~~java
package com.example;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        names.forEach(System.out::println);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Run with Java 17:

~~~bash
java -cp out com.example.Main
~~~

List.of() is an API introduced in Java 9, so it is available in Java 17. The generated class file uses the Java 17 bytecode level.

## 2. Why are -source and -target not enough?

These two options control two different parts:

- **-source N**: restricts the accepted language/syntax level.
- **-target N**: chooses the output class file bytecode format.

They do not automatically restrict the set of JDK APIs visible to the compiler. If you use JDK 21 to compile with -source 17 -target 17, the compiler can still see methods added in JDK 21.

For example, List.getFirst() was added in Java 21:

~~~java
import java.util.List;

public class NewerApiExample {
    public static void main(String[] args) {
        List<String> values = List.of("first", "second");
        System.out.println(values.getFirst());
    }
}
~~~

If you use JDK 21 and only set source/target:

~~~bash
javac -source 17 -target 17 -d out NewerApiExample.java
~~~

The compiler may accept the call to getFirst() because JDK 21's List API has that method. The output class may have bytecode version 61, but when running on Java 17, the runtime lacks List.getFirst() and can throw NoSuchMethodError.

If you use:

~~~bash
javac --release 17 -d out NewerApiExample.java
~~~

The compiler reports an error because List.getFirst() is not part of the Java 17 API. This catches the error early in the build step rather than when the application runs on the target environment.

### Comparison table

| Option | Language restriction | Class file format | Release-based platform API restriction |
| --- | --- | --- | --- |
| Only -source 17 | Yes | Does not automatically set matching target | No |
| Only -target 17 | Does not automatically restrict syntax | Yes | No |
| -source 17 -target 17 | Yes | Yes | No |
| --release 17 | Yes | Yes | Yes |

Therefore, when the target is running on Java 17, --release 17 is usually a more complete and less error-prone way to express intent than combining -source with -target.

Do not pass --release together with -source or -target in the same compilation. --release already sets those levels and must not be combined with separate source/target options.

## 3. What does target API restriction mean?

When compiling with --release 17, javac checks references to platform APIs against the Java 17 API set. Classes, methods, or fields added only in later releases are unavailable during that compilation.

Examples of APIs by version:

| API | Release added | Usable with --release 17? |
| --- | ---: | --- |
| List.of(...) | Java 9 | Yes |
| String.isBlank() | Java 11 | Yes |
| Files.mismatch(...) | Java 12 | Yes |
| Stream.toList() | Java 16 | Yes |
| List.getFirst() | Java 21 | No |

This table illustrates the principle: APIs present in release 17 or earlier can be used if they remain part of the supported API; APIs added after Java 17 are restricted.

### Not just checking method names

API restrictions also apply to:

- Classes and interfaces.
- Constructors.
- Methods and overloads.
- Fields and constants.
- Data types in method signatures.
- Platform module APIs exported for that release.

For example, a method may exist since Java 17, but an overload accepting a newer type may only appear in Java 21. Compiling with --release 17 will disallow the new overload.

### Published JDK APIs vs. internal APIs

--release targets the public, supported, and documented APIs of the selected release. Internal packages such as jdk.internal.* do not become stable APIs merely because they exist in a JDK distribution.

Do not use internal APIs to bypass the target boundary. If a capability does not have a suitable public API in Java 17, choose a compatible library or design an alternative implementation.

## 4. Building with a newer JDK while running on Java 17

A common scenario is that a build machine has JDK 21 or newer installed, while the deployment environment still uses Java 17.

If you rely solely on the default compiler of the newer JDK, source code may accidentally reference new APIs. The explicit configuration is:

~~~bash
javac --release 17 -d out src/com/example/*.java
~~~

The compiler can be from a newer JDK, while the platform APIs and output bytecode are constrained to Java 17.

Then run tests on a Java 17 runtime:

~~~bash
java -version
java -cp out com.example.Main
~~~

--release 17 does not install a Java 17 runtime and does not automatically select the runtime when executing. It only configures the compiler. The build machine may still be running JDK 21, while the application needs to be tested using an actual JDK 17 or equivalent environment.

### Checking the active compiler and runtime

On a machine with multiple JDKs, javac and java may point to different versions via PATH:

~~~bash
javac -version
java -version
~~~

These two commands help identify which compiler and runtime versions are being invoked. For CI, build containers, or build agents, explicitly specify the JDK/toolchain so results are reproducible.

## 5. Inspecting class files after compilation

Java 17 class files have major version 61. You can check this with javap:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

In the output, look for the line:

~~~text
major version: 61
~~~

This is evidence that the class file format matches Java 17. However, checking only the major version does not prove that every dependency or every API call is compatible with the Java 17 runtime. You must combine this with dependency checks and running tests on JDK 17.

### Running javap for a specific class

If the class is in a package:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

If the class has no package:

~~~bash
javap -verbose -classpath out Main
~~~

javap is a tool for reading class file information. Do not manually edit bytecode just to change the major version from a higher value down to 61; changing that number does not convert new syntax, APIs, or bytecode into something Java 17 understands.

## 6. --release does not backport new Java features

--release 17 does not translate Java 21 code into Java 17 code. It requires the source code to already conform to the Java 17 language and only use APIs available in release 17.

For example:

- Language syntax newer than Java 17 will be rejected.
- Platform APIs introduced only in Java 21 will be rejected.
- The generated bytecode remains Java 17 bytecode.

If you want to use a newer language feature or API, you must raise the minimum runtime version or find an equivalent implementation on Java 17. Simply changing compiler flags cannot make an older runtime understand new features.

### Preview features are a special case

Preview features are tied to a specific release and must be explicitly enabled when compiling and running with the corresponding JDK. They are not stable APIs to include by default in an application requiring long-term compatibility. For a standard Java 17 target, use finalized features in Java 17 and avoid depending on previews.

## 7. What --release 17 does not guarantee

--release is an important guardrail, but it does not replace the entire compatibility verification process.

### Does not check all third-party dependencies

The compiler checks platform APIs against Java 17, but dependencies on the classpath/module path are separate inputs. If a library requires Java 21 or calls APIs that exist only on Java 21, the application can still fail when running on Java 17.

For example:

- A JAR containing class files with a version higher than 61 can cause UnsupportedClassVersionError when the Java 17 runtime loads that class.
- A library compiled at a lower bytecode level that calls new JDK APIs via reflection or dynamic loading can fail at execution time.
- A library might use a new platform class in a code path executed only in a rare scenario; compiling the application does not necessarily catch every runtime error inside dependencies.

Therefore, verify the minimum Java requirement of each dependency and run tests on the target runtime.

### Does not guarantee compatibility with JDK internals

If code uses reflection, Class.forName, MethodHandles, or dynamically constructed class names to access internal components, the compiler may not detect that dependency. Java 17's strong encapsulation and module access rules still apply at runtime.

Do not rely on sun.*, jdk.internal.*, or private JDK members to build application APIs.

### Does not select the application runtime

Building with --release 17 does not force production to run Java 17. If production runs Java 11, bytecode version 61 is still incompatible. If production runs Java 21, the program can usually run, but behavior still needs to be tested on the actual runtime.

### Does not configure encoding or other build settings

--release does not replace settings such as:

- Source encoding (-encoding UTF-8).
- Classpath or module path.
- Annotation processors.
- Resource filtering and packaging.
- Runtime JVM options.
- Test runner configuration.

Those aspects still must be configured separately.

## 8. --release and the module system

For modular applications, --release 17 still restricts platform APIs to Java 17. Application modules and dependencies must be placed on the module path appropriately.

Example structure:

~~~text
src/
  com.example.app/
    module-info.java
    com/example/app/Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.net.http;
    exports com.example.app;
}
~~~

Compile:

~~~bash
javac --release 17 \
      -d out \
      --module-source-path src \
      -m com.example.app
~~~

Run:

~~~bash
java --module-path out \
     -m com.example.app/com.example.app.Main
~~~

This example uses the java.net.http module, introduced in Java 11 and therefore present in Java 17. When compiling with --release 17, the compiler rejects platform modules or APIs that appeared only in later releases.

### Cannot use --add-exports to expand system module APIs when --release is set

--release fixes the platform API and module set to the target release. Because of this, the compiler disallows using --add-exports to expose system module packages outside that selected set in the same compilation.

If the source depends on an internal package of a system module, that is a signal to review the dependency. Do not break the target API boundary just to make code depending on JDK internals compile.

--add-exports and --add-opens serve different roles in module access; they are not substitutes for compatible public APIs.

## 9. Maven configuration for Java 17

With Maven, use the maven.compiler.release property to configure the compiler plugin:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Ensure the maven-compiler-plugin in the build uses a version that supports the release property. You can declare the plugin explicitly under build/plugins:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.11.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This example uses a specific plugin version to illustrate the configuration structure. In real projects, use a plugin version managed and supported by your organization in the current build; avoid letting an overly old plugin ignore or fail to understand the release configuration.

### Why not just set source and target in Maven?

The older configuration:

~~~xml
<maven.compiler.source>17</maven.compiler.source>
<maven.compiler.target>17</maven.compiler.target>
~~~

only describes source/target. When building with a newer JDK, the compiler can still see newer APIs. For a Java 17 target, prefer:

~~~xml
<maven.compiler.release>17</maven.compiler.release>
~~~

### Selecting the build JDK with Maven Toolchains

If an organization needs to specify a dedicated compiler JDK, Maven Toolchains allows the build to select a configured JDK instead of relying entirely on the JDK running Maven. Distinguish between:

- The JDK running Maven.
- The compiler JDK selected via toolchain.
- maven.compiler.release as the target API/bytecode level.
- The JDK running tests or the application.

Setting release does not automatically install or select a toolchain JDK. CI must provide the right JDK and verify the actual version.

## 10. Gradle configuration for Java 17

Gradle provides Java toolchains to choose the JDK used for compiling/testing/running and options.release to restrict the target API/bytecode release.

Groovy DSL example:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL example:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Toolchain instructs Gradle to locate a suitable JDK 17 for the task. options.release = 17 sets the target API/bytecode level of the Java compiler. If the goal is to use a newer JDK for building while releasing for Java 17, you can select a newer toolchain and still set release 17, provided that compiler supports that release.

### Toolchain and release answer two different questions

| Configuration | Question answered |
| --- | --- |
| Java toolchain | Which JDK/compiler is used to perform the build? |
| options.release | Which Java release/API is the artifact compiled against? |
| Test launcher/runtime | Which JDK do tests actually run on? |

Do not assume that setting only the toolchain ensures every external task or plugin uses the same runtime. Check the compile, test, and execution configurations of the build.

## 11. CI: compiling for the release and running on the target runtime

A CI pipeline for a Java 17 application should separate these steps:

1. Select a JDK/compiler supported by the organization.
2. Compile with --release 17 or the equivalent build tool configuration.
3. Run unit tests on Java 17.
4. Run integration tests on Java 17 with real dependencies or an appropriate simulated environment.
5. Check whether dependencies require a newer runtime.
6. Inspect artifacts and class file versions when needed.
7. Package and deploy using the designated Java 17 runtime.

If building with JDK 21 while production uses JDK 17, include an actual test job on JDK 17. Having the compiler accept --release 17 is an important safeguard, not a replacement for runtime testing.

### Direct build command example in CI

~~~bash
javac --release 17 -encoding UTF-8 -d out @sources.txt
java -cp out com.example.Main
~~~

The sources.txt file contains the list of source files to compile, one path per line. The -encoding UTF-8 option configures source encoding separately; it is not part of --release.

In real CI, run these two commands with JDK 17 or use a dedicated Java 17 runtime to verify the artifact.

## 12. Inspecting dependencies and artifacts

### Checking class file version

Use javap -verbose to confirm application classes have major version 61:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.Main
~~~

With Maven, the class output directory is usually under target/classes; with Gradle it is typically build/classes/java/main. The exact path depends on build configuration.

### Analyzing dependencies with jdeps

jdeps helps inspect dependencies between classes, packages, and modules. Example:

~~~bash
jdeps --multi-release 17 --summary application.jar
~~~

You can use jdeps --jdk-internals to locate some references to JDK internal APIs:

~~~bash
jdeps --jdk-internals application.jar
~~~

These commands assist artifact analysis; they do not prove every runtime code path is compatible. String-based reflection, dynamic loading, and logic executed only under specific conditions may not be fully detected by static analysis.

### Checking library version requirements

Before adding a dependency:

- Read the minimum Java requirement in the library's documentation.
- Choose an artifact/version that supports Java 17.
- Inspect transitive dependencies.
- Run tests on a Java 17 runtime.
- Avoid relying solely on a successful compile on a newer JDK.

An application can be compiled with --release 17 and still fail to run on Java 17 if a library packages higher-version bytecode or requires newer APIs.

## 13. Common misconceptions

### Building on JDK 21 does not mean the application requires Java 21

If you use JDK 21 with --release 17, Java 17-compliant source code, and compatible dependencies, the artifact can be designed to run on Java 17. The JDK version running the compiler and the application's minimum runtime version are two separate pieces of information.

### Class file version 61 does not guarantee API compatibility

A class file with major version 61 only indicates that the bytecode format matches Java 17. It does not prove the class does not reference a method available only in Java 21, especially if the bytecode was generated or modified by another tool, or if references are loaded dynamically.

### Successful compilation does not prove dependencies will run

The compiler checks source code and the types it sees. It does not execute all code paths, perform every reflective access, or verify that external services exist.

### --release is not a bytecode downgrader

You cannot take a Java 21 JAR and run javac --release 17 to downgrade that JAR. --release applies when compiling source code; it does not convert class files with major version 65 into class files with version 61, replace API calls, or backport dependencies.

### Compiler flags do not replace runtime policies

The application still needs a supported runtime, heap/GC configuration, certificates, native libraries, and compatible dependencies. --release only addresses compatibility for one part of the build process.

## 14. Common errors and how to handle them

| Situation | Cause | Resolution |
| --- | --- | --- |
| Used -source 17 -target 17 but Java 17 runtime throws NoSuchMethodError | Code referenced a newer JDK API | Use --release 17 and recompile |
| Compiler reports method not found with --release 17 | Method is not part of the Java 17 API | Use a compatible API or raise the minimum runtime |
| Java 17 reports UnsupportedClassVersionError | Dependency/class was compiled for a newer Java version | Choose a dependency built for Java 17 or change version |
| javac reports release 17 is not supported | Compiler is too old | Install a JDK/compiler supporting release 17 |
| Local build passes but CI fails | Different JDK/toolchain or dependencies | Record and pin the toolchain, verify versions |
| Maven ignores the release configuration | Compiler plugin is too old or property is wrong | Use a plugin supporting release and check effective POM |
| Gradle compiles with an unexpected JDK | Toolchain not configured or another task differs | Configure toolchain and inspect JavaCompile tasks |
| Compile succeeds but Java 17 tests fail | Incompatible dependency or runtime code path | Run tests on JDK 17 and inspect dependencies |
| Attempting to change a JAR's major version with a bytecode tool | Only modifies header, does not convert API/bytecode | Recompile source/dependencies for the appropriate target |
| Newer API called via reflection | Compiler cannot see static call | Audit class/method strings and run runtime tests |
| Using --add-exports to expand system API alongside --release | Two conflicting configuration goals | Use APIs supported for the target release |

## 15. Workflow for targeting Java 17 APIs

When a project must run on Java 17:

### Step 1: Define the minimum runtime

Explicitly state that the application requires Java 17. This guides choices for syntax, APIs, dependencies, build tools, and deployment environments.

### Step 2: Select the compiler/toolchain

You may use JDK 17 or a newer JDK that supports target release 17. Record the compiler vendor/version so builds are reproducible.

### Step 3: Configure --release 17

Use directly:

~~~bash
javac --release 17 ...
~~~

Or the equivalent configuration in Maven/Gradle. Avoid using only -source and -target when API restrictions are needed.

### Step 4: Check dependencies

Select libraries whose minimum Java requirement is compatible with a Java 17 runtime. Check class file versions, APIs, and module requirements when needed.

### Step 5: Test on Java 17

Run unit tests, integration tests, and smoke tests on the actual runtime. Pay special attention to code using reflection, service loading, native libraries, serialization, and newer APIs.

### Step 6: Inspect artifacts

Use javap to check major version when needed. Use jdeps to analyze modules/internal APIs. Do not treat any single metric as complete proof.

### Step 7: Keep configuration in CI

Put the release target, toolchain, runtime tests, and dependency constraints into version-controlled build configuration. Avoid relying on whatever JDK happens to be installed on a developer machine.

## 16. Practical principles

When compiling and releasing a Java 17 application:

1. Use javac --release 17 to synchronize source language, bytecode target, and platform APIs.
2. Do not use only -source 17 -target 17 if the build might run on a newer JDK.
3. Understand that --release restricts platform APIs to Java 17 and does not backport new APIs.
4. Distinguish between the JDK running the compiler, the release target, and the JDK running the application.
5. Check third-party dependencies; --release does not convert bytecode or restrict the APIs of external JARs.
6. Use Maven/Gradle compiler configurations that support release and configure toolchains explicitly.
7. Run tests on an actual Java 17 runtime, not just compile on a newer JDK.
8. Use javap to inspect class versions and jdeps to assist dependency analysis.
9. Do not rely on JDK internals or expand system modules to bypass API boundaries.
10. Record compiler, runtime, and dependency configurations in CI to ensure reproducible builds.

--release 17 is an explicit way to tell the compiler that the artifact must conform to Java 17's language, bytecode, and platform APIs. It prevents many compatibility errors that would otherwise be discovered late at runtime, especially when building on a newer JDK. To ensure the application actually runs on Java 17, compatible dependencies and testing on the exact target runtime remain essential.
