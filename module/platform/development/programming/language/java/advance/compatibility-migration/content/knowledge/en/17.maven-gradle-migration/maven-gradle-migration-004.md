# maven-compiler-plugin and release configuration

When upgrading a Java project, changing the JDK version locally or in CI is only the first step. Source code might be compiled with JDK 21 yet still need to run on Java 17; conversely, a project configured to target Java 8 might accidentally call a new JDK 17 API and fail only when deployed to a Java 8 JVM. These problems usually stem from confusing the **JDK used to build**, the **allowed Java syntax level**, the **class-file version**, and the **Java Platform APIs that code is permitted to use**.

In Maven, maven-compiler-plugin is the primary component controlling Java compilation in the lifecycle. The compiler plugin's **release** parameter configures compatibility targets more accurately than using only source and target. This lesson belongs to **Java Advance Compatibility Migration**, chapter **Maven and Gradle**, focusing on how to configure, verify, and transition maven-compiler-plugin during a Java upgrade, as well as how to compare it with the corresponding release and toolchain mechanisms in Gradle.

The goal after this lesson is to be able to read the effective compiler configuration of a Maven project, choose the right release, avoid unintentionally using overly new Java APIs, distinguish the Maven runtime from the compiler JDK, handle multi-module/annotation processing setups, and build a compatibility testing workflow before moving to production.

## 1. Four versions that are frequently confused

A Java project can have at least four independent version levels:

| Concept | Meaning | Example |
|---|---|---|
| JDK running Maven | The JVM executing Maven and certain Maven plugins | Maven running on JDK 21 |
| Compiler JDK | The javac binary used to compile the project | javac from JDK 21 |
| Java release target | The Java source, class-file, and Java Platform API level targeted by the code | Java 17 |
| Production JRE/JDK | The runtime actually executing the artifact | Java 17 |

In addition, there are the Maven version, maven-compiler-plugin version, annotation processor versions, Java agents, and dependency bytecode baselines.

For example, a valid project may have:

~~~text
Maven process:        JDK 21
Compiler toolchain:   JDK 21
maven.compiler.release: 17
Produced bytecode:    Java 17 (major 61)
Production runtime:   JDK 17
~~~

This differs from:

~~~text
Maven process:        JDK 17
Compiler toolchain:   JDK 17
maven.compiler.release: 21
~~~

The second case is invalid if javac actually comes from JDK 17, because that compiler cannot compile for a Java 21 release target. You must upgrade the compiler JDK or fix the release target.

### 1.1. A core misconception

**A newer build JDK does not mean the artifact requires a newer JDK.** A newer compiler can build for an older release if it supports that release.

**An older class-file version does not guarantee the application uses only old APIs.** This is why --release matters more than setting target alone.

## 2. Where does maven-compiler-plugin sit in the Maven lifecycle?

For jar packaging or packaging types with a corresponding compiler lifecycle, Maven typically runs maven-compiler-plugin's compile goal during the compile phase, and the testCompile goal during the test-compile phase.

~~~text
validate
   |
   v
generate-sources
   |
   v
process-sources
   |
   v
compile           <-- maven-compiler-plugin:compile
   |
   v
process-test-sources
   |
   v
test-compile      <-- maven-compiler-plugin:testCompile
   |
   v
test              <-- usually handled by maven-surefire-plugin
   |
   v
package
   |
   v
verify / install / deploy
~~~

The Maven Compiler Plugin primarily compiles sources. It **does not run unit tests itself**, does not determine the JVM used to run tests, and does not guarantee that all dependencies have bytecode compatible with the target release.

A command:

~~~bash
./mvnw clean compile
~~~

compiles main sources after deleting previous outputs. Meanwhile:

~~~bash
./mvnw clean verify
~~~

can execute through the compile, test-compile, test, package, and verify phases depending on the project's plugins/lifecycle.

On Windows, depending on the repository, mvnw.cmd may be used instead of ./mvnw. If the project does not yet include a Maven Wrapper, use the mvn command from a managed Maven installation.

## 3. How do source, target, and release differ?

Three commonly encountered parameters:

- **source:** determines the Java syntax level accepted by javac.
- **target:** determines the class-file version produced by javac.
- **release:** on compilers supporting --release, combines syntax level, class-file target, and the **Java Platform API set of the target release**.

### 3.1. source restricts syntax

Example:

~~~xml
<configuration>
    <source>8</source>
</configuration>
~~~

When compiling with source level 8, code cannot use syntax introduced in Java 10, 14, 16, or 17 such as local variable type inference with var, switch expressions, records, or sealed classes.

However, source does not by itself forbid referencing new APIs added to the current compiler JDK.

### 3.2. target restricts class-file version

Example:

~~~xml
<configuration>
    <target>8</target>
</configuration>
~~~

javac attempts to produce class files targeting Java 8, corresponding to major version 52. This does not mean every standard-library method called by the code existed in Java 8.

### 3.3. release restricts syntax, bytecode, and platform APIs

Example:

~~~xml
<configuration>
    <release>8</release>
</configuration>
~~~

On compilers supporting --release, Java code is compiled strictly against the Java Platform APIs corresponding to release 8. If the code calls a method introduced in Java 9, the compiler reports an error even though the JDK running javac contains that method.

### 3.4. Comparison table

| Condition | source=8 | target=8 | release=8 |
|---|---|---|---|
| Restricts newer Java syntax | Yes | Does not do this by itself | Yes |
| Produces Java 8 class files | Not sufficient alone | Yes | Yes |
| Restricts Java SE APIs to Java 8 | No | No | Yes, with javac supporting --release |
| Restricts third-party dependencies | No | No | No |
| Specifies JVM running Maven | No | No | No |
| Specifies JVM running tests | No | No | No |

**General recommendation when migrating:** prefer using release for a single Java target rather than setting source/target separately.

## 4. Practical example: code builds cleanly yet fails on older Java

Java 9 introduced List.of. Suppose Maven runs on JDK 17 and the project configures:

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Source:

~~~java
import java.util.List;

public final class Sample {
    public static List<String> values() {
        return List.of("A", "B");
    }
}
~~~

The code uses valid Java 8 syntax. However, the List.of method does not exist in Java 8.

If a newer JDK compiler compiles with source=8 and target=8 **without using a Java 8 bootclasspath/API signature set**, it may emit version 52 class files containing a reference to List.of. When executed on Java 8, that call can throw NoSuchMethodError.

Changing to:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
~~~

with a compiler supporting --release causes the build to fail at List.of because that API is not part of Java 8.

This is the most practically valuable difference provided by release.

### 4.1. When might source/target still fit?

Very old projects may be constrained by a compiler or build system that does not yet support --release. In those cases, you must manage bootclasspath or API baselines appropriately and test on the lowest supported Java runtime.

For projects moving to modern JDKs, you should generally update Maven/compiler plugin versions and use release instead of keeping uncontrolled source/target settings.

### 4.2. release does not check everything

Keep in mind that --release primarily constrains syntax, class files, and Java Platform APIs. It **does not guarantee**:

- Third-party Maven libraries support the older runtime.
- Java agents or native dependencies are compatible.
- Dependency bytecode falls within target limits.
- Runtime behavior is identical across JDKs.
- Frameworks, servlet containers, JDBC drivers, and TLS policies are compatible.
- Non-Java runtime components share the same contract.

Additional dependency validation and runtime tests are necessary.

## 5. Basic Maven Compiler Plugin configuration

In the POM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>migration-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version 3.13.0 in the example is one version supporting release configuration; when applying this, select a compiler plugin version matching your Maven/JDK setup and current organizational dependency policy. Do not assume the example version is the “latest” at all times.

With the maven.compiler.release property, the plugin receives release 17 for standard main Java compilation. Declaring the plugin version explicitly makes builds less dependent on default lifecycle mappings or uncontrolled versions inherited from a parent.

### 5.1. Direct configuration inside the plugin

Instead of a property, you can declare:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

These two forms are configuration alternatives; you do not need to use both at once. If properties, profiles, plugin configuration, and parent POMs set different values, inspect the **effective configuration** actually applied by Maven.

### 5.2. Avoid mixing source/target/release inadvertently

A POM containing all three:

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

creates confusion and can yield conflicting configurations depending on plugin version and compiler options. Java's javac does not allow combining --release with --source or --target in conflicting ways.

If choosing release as the standard, remove obsolete source/target settings and confirm no parent, profile, or execution overrides them.

## 6. Where do Maven properties and plugin configuration come from?

A large project often has multiple POM layers:

~~~text
company-parent/pom.xml
        |
        +--- service-parent/pom.xml
                  |
                  +--- app-api/pom.xml
                  +--- app-core/pom.xml
                  +--- app-server/pom.xml
~~~

The compiler plugin can be configured via:

- Parent POM.
- pluginManagement.
- Module plugins.
- Properties in the POM.
- Maven profiles.
- Command-line -D properties.
- Environment-activated settings/profiles.
- Separate goal executions for specific source sets/modules.

Therefore, merely searching for the string maven.compiler.release across a repository is not enough to confirm the target in use.

### 6.1. pluginManagement vs. plugins

pluginManagement in a parent defines default versions/configurations for a plugin whenever it is used. It does not mean every optional goal runs in every module. For goals bound by the default lifecycle, pluginManagement settings can apply when the plugin enters through lifecycle mapping.

Parent example:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Child modules can explicitly declare the plugin or rely on the corresponding lifecycle compiler binding. If a module needs different settings, check inheritance, merging, and executions.

### 6.2. Reading the effective POM

Useful command:

~~~bash
./mvnw help:effective-pom
~~~

You can write it to a file:

~~~bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

In a multi-module project, select the appropriate module or inspect the effective POM of the affected module. The filename is merely diagnostic output, not a file to commit into source control.

Inspect active profiles:

~~~bash
./mvnw help:active-profiles
~~~

Inspect a property value:

~~~bash
./mvnw help:evaluate -Dexpression=maven.compiler.release -DforceStdout
~~~

That command prints the expression value in the corresponding execution context. When a plugin has separate direct configuration, inspect the effective POM and actual compiler command, not just the property.

## 7. Determining which JDK Maven actually uses

First command when investigating:

~~~bash
./mvnw -version
~~~

Its output typically shows:

- Maven version.
- Java version.
- Java home.
- OS and environment details.

However, this only confirms the JVM running Maven. If the project uses **Maven Toolchains** or a separately configured compiler, the selected javac may come from a different JDK.

### 7.1. Different JDK sources

| Component | Which JDK can it use? |
|---|---|
| Maven launcher | JAVA_HOME or Java selected by wrapper/environment |
| maven-compiler-plugin | JDK running Maven or toolchain/compilation setup JDK |
| maven-surefire-plugin | Configured separate JVM or matching build JVM |
| maven-failsafe-plugin | Configured integration-test JVM |
| javadoc plugin | May use JDK toolchain or separate executable |
| Annotation processor | Typically runs inside the selected compiler context |
| Production | JDK on server/container at deployment |

Thus, a project can compile with JDK 21 while running tests on a different JVM. Verify explicitly rather than assuming “running Maven with Java 21” means every plugin and test runs on Java 21.

### 7.2. Developer vs. CI environments

A common mistake is developers using JDK 21 in their IDE while CI still runs Maven with JDK 17. The POM sets release 21; local builds succeed while CI reports:

~~~text
error: release version 21 not supported
~~~

The fix is updating the CI compiler toolchain or adjusting the chosen release. Never hide the error by deleting release so the build “succeeds” with the wrong bytecode.

## 8. Maven Toolchains: separating the Maven JVM from the compiler JDK

Toolchains let toolchain-aware plugins select a JDK by criteria instead of relying solely on the JDK running Maven.

One use case:

~~~text
Maven runs on JDK 17
          |
          v
Toolchain selects JDK 21
          |
          v
Compiler javac JDK 21
          |
          v
maven.compiler.release = 17
          |
          v
Java 17 target artifact
~~~

This is useful when build machines host multiple JDKs or when Maven and certain plugins need to stay on a different JVM from the compiler.

### 8.1. Toolchains file

Maven can read a toolchains configuration file in the user's home directory, typically:

~~~text
~/.m2/toolchains.xml
~~~

Illustrative example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Paths and vendor names are examples. They must match the actual installed JDK and criteria required by the project.

### 8.2. Declaring toolchain requirements in the POM

A classic configuration uses maven-toolchains-plugin with the toolchain goal:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.1.0</version>
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
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The Maven Toolchains Plugin has additional capabilities and goals depending on version. The example above illustrates the mechanism relying on toolchains.xml and criteria; when applying it, use the configuration documented for your current version.

### 8.3. Toolchain does not replace release

Toolchain answers: “Which javac to use?”

Release answers: “Which Java level to compile for?”

Both remain necessary when a project wants the JDK 21 compiler while targeting Java 17 artifacts. A project using a JDK 21 toolchain without setting release can emit Java 21 class files and use unexpected new Java APIs.

### 8.4. Do all plugins use toolchains?

No. A plugin uses a toolchain only if it supports toolchains and is properly configured. A build may have its compiler use JDK 21 while testing, code-checking, or documentation plugins use Maven's JVM or another JDK.

Inspect build logs, toolchain selection, and actual task executions to confirm.

## 9. Choosing release based on application requirements

Do not set release to match the installed JDK simply because it is the newest version. Release must align with the runtimes you are committed to supporting.

Examples:

| Product type | Release to consider | Rationale |
|---|---|---|
| Internal service running only on JDK 21 | 21 | Can use Java 21 language/APIs |
| Library supporting Java 17+ | 17 | Java 17 consumers must load its classes |
| CLI still supporting Java 11 | 11 | Maintain the corresponding baseline |
| Application migrating incrementally from Java 8 | Temporarily 8, then raise | Decouple compiler/build upgrade from runtime upgrade |
| Multi-release library | Multiple releases with separated sources/classes | Requires specialized structure, not just one property |

Decisions must also factor in frameworks, dependencies, annotation processors, containers/runtimes, and security requirements.

### 9.1. Release target should reflect product requirements

If product policy declares Java 17 as the minimum runtime, compiler release 17 is a sound baseline. However, if production still runs Java 11 nodes, selecting release 17 prevents those nodes from loading the class files.

Determine:

- The set of runtimes actually deployed.
- The lowest version still supported.
- Feasibility of synchronized runtime upgrades.
- Whether the dependency ecosystem supports the target version.
- The rollback plan when the new release is deployed.

Do not raise maven.compiler.release to 21 before production runtimes have been upgraded at least to the corresponding level.

## 10. Class-file versions and how to verify artifacts

Common milestones:

| Java | Class-file major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

For example, to inspect a compiled class:

~~~bash
javap -verbose -classpath target/classes com.example.Main
~~~

In the output you can check:

~~~text
major version: 61
~~~

If compiled with Java 17 release, the corresponding major version is normally 61.

You can inspect a specific class file:

~~~bash
javap -verbose target/classes/com/example/Main.class
~~~

The class-file version indicates only the bytecode level; it is **not sufficient proof** of compatibility with dependencies or non-Java-Platform APIs.

### 10.1. Encountering UnsupportedClassVersionError

Example:

~~~text
UnsupportedClassVersionError:
class file version 65.0,
this Java Runtime only recognizes ... 61.0
~~~

This indicates the artifact was compiled for Java 21 while running on a runtime supporting at most Java 17.

How to handle:

1. Confirm the actual production JVM.
2. Identify which class failed: application code or a dependency.
3. Check the release of the module containing the class.
4. If Java 17 runtime support is required, recompile the application with release 17 and use compatible dependencies.
5. If a feature requires Java 21, upgrade the runtime according to plan rather than mechanically lowering the target.

## 11. Multi-module Maven: one shared release or multiple releases?

In a multi-module project, not every module shares identical requirements.

Example:

~~~text
platform-parent
  |
  +-- core-api          Java 11 baseline
  +-- business-core     Java 17 baseline
  +-- service-app       Java 21 runtime
  +-- integration-test  Java 21 test environment
~~~

One option is setting release 17 in the parent and overriding modules needing Java 11 or 21. Pay close attention to **dependency direction**:

- A module targeting Java 11 must not depend on an artifact that only runs on Java 17.
- A module targeting Java 17 cannot load class files requiring Java 21 on a Java 17 runtime.
- A Java 21 module can normally consume a Java 17 artifact if APIs/dependencies are compatible.

### 11.1. Parent POM

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

### 11.2. Module requiring a different baseline

~~~xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
~~~

Overriding the property can be clean and explicit, provided the plugin actually reads that property and no direct configuration in a parent/profile overrides it.

### 11.3. Testing the exact module

~~~bash
./mvnw -pl core-api -am clean verify
~~~

Depending on structure and module naming, -pl selects the project and -am adds the dependency modules needed to build alongside it. Run validation for modules with distinct baselines rather than only running at the root and assuming a green overall build covers everything.

### 11.4. Do not use release as a substitute for module architecture

If one module must use Java 21 APIs while another must support Java 11, you cannot satisfy both by toggling properties back and forth in the same source set. Module splitting, adapters, or multi-release JARs may be needed when use cases truly demand it and technical constraints allow.

## 12. Annotation processing and generated sources

Many Java projects use Lombok, MapStruct, Hibernate metamodel, Dagger, QueryDSL, or custom annotation processors. When upgrading the compiler JDK, annotation processors can fail even though human-written code has not changed.

Boundaries to distinguish:

1. The compiler JDK actually running the processor.
2. APIs/compiler internals used by the processor.
3. Source code generated by the processor.
4. The release target of the compiled sources.
5. Ordering between generate-sources and compile.
6. Versions of processors and emitted dependencies.

### 12.1. Why --release does not shield processors from a new JDK

Suppose a JDK 21 compiler compiles the project with release 17. Annotation processors typically still execute inside the javac/JDK 21 context, not inside a simulated JDK 17 JVM.

If a processor relies on javac internals, it can hit IllegalAccessError or similar failures when compiler internals change. This must be resolved by upgrading the processor or picking an appropriate compiler version, not merely by changing release.

### 12.2. Declaring annotationProcessorPaths

For example, maven-compiler-plugin can configure the annotation processor path:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.6.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

This exemplifies putting a processor on the processor path; the listed version only illustrates syntax—select a version compatible with your MapStruct dependency and actual JDK.

In newer JDKs, automatic processor discovery can change due to security policies and compiler defaults. Declare processors explicitly rather than relying on javac implicitly scanning the entire classpath.

### 12.3. Do not edit generated code directly

If generated sources use an overly new Java API or syntax incompatible with release, update the generator version/configuration/source templates. Editing output in target/generated-sources is only temporary and will be overwritten on the next build.

### 12.4. Do processors need their own toolchain?

Some projects have multiple source generators or plugins that do not support toolchains. Check each goal individually to know which JDK runs it. maven.compiler.release does not force every source-generation task to execute on a particular JDK.

## 13. Test compilation and the test-execution JVM are two different things

Maven Compiler Plugin also handles test compilation in the default lifecycle. However, the JVM executing tests is typically controlled by Surefire/Failsafe and related configuration.

~~~text
maven-compiler-plugin:testCompile
          |
          v
target/test-classes
          |
          v
maven-surefire-plugin:test
          |
          v
JVM running unit tests
~~~

### 13.1. Why does compilation pass yet tests fail?

Scenarios:

- Tests compiled with release 17 while Surefire forks a Java 11 JVM.
- Test runtime lacks a dependency due to incorrect scope.
- Framework/test agent does not yet support the new JDK.
- Code reflects into JDK internals and gets blocked by strong encapsulation.
- TLS/certificate policies differ between old and new JDKs.
- Generated test sources have a different class-file version.
- Test environment needs module opens for mocking frameworks.

To guarantee runtime compatibility, run tests on the exact JDKs supported by the product. If both Java 17 and 21 must be supported, CI should include a two-runtime matrix.

### 13.2. Test code can have a different baseline from main code

Some projects distribute main artifacts for Java 17 while running tests on JDK 21 with newer test tools. This can be valid when configured explicitly. However, never let test configuration accidentally mask the main artifact using newer APIs.

Depending on plugin version, Compiler Plugin can support separate test-compilation settings. When differentiation is needed, inspect the parameters of your plugin version and verify effective executions. Do not assume a single main release property automatically solves all special test-source cases.

## 14. Preview features and --enable-preview

Some Java language features appear in preview before finalization. If source code uses a preview feature, the compiler may require --enable-preview, and release must typically match the compiler release offering that preview.

Conceptual example on a JDK with preview support:

~~~bash
javac --enable-preview --release 21 PreviewExample.java
~~~

Which syntax counts as preview depends on the JDK version. Never enable preview simply because the compiler was upgraded, and never add --enable-preview across all modules as a default setting.

### 14.1. Maven compilerArgs

A configuration might include:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>21</release>
        <compilerArgs>
            <arg>--enable-preview</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

If preview code is used, test and production JVMs may also require --enable-preview per the requirements of that release. Java releases do not guarantee binary compatibility for preview features across versions.

**Preview is not a default compatibility migration path.** It is a decision carrying language/runtime risk that must be recorded explicitly.

## 15. Common errors when configuring maven-compiler-plugin

### 15.1. Release version not supported

Message:

~~~text
error: release version 21 not supported
~~~

The common cause is that the javac being invoked is too old to support release 21. Check Maven -version, compiler toolchain selection, and actual build logs.

Solution: use a compiler JDK supporting Java 21, or select a release aligned with your existing baseline.

### 15.2. Source option or target option no longer supported

A newer JDK may drop support for a very old source/target. For instance, an old project requiring Java 6 on a compiler that no longer supports that target.

Solution: verify the baseline that must be preserved, assess whether dedicated controlled build tooling with an older JDK is needed, or raise the minimum runtime. Modern javac cannot be forced to emit every historical class-file target.

### 15.3. NoSuchMethodError on an older runtime

If class files target Java 8 yet code calls a Java 11 API, source/target was likely configured without constraining platform APIs.

Solution: use release properly and build a runtime test matrix. Check dependency bytecode as well.

### 15.4. Cannot find symbol after enabling release

For example, switching from source/target=8 to release=8 causes the compiler not to find List.of. This can be a legitimate error surfacing a previously hidden API dependency.

Solution: use APIs supported on Java 8, raise the baseline if product requirements permit, or split implementations by release under a clear policy.

### 15.5. --release cannot be used with --source/--target

Conflicting settings may come from a parent POM, profile, plugin configuration, or compilerArgs manually adding flags.

Solution: remove overlapping settings and make release the single source of truth where appropriate.

### 15.6. Invalid target release

Messages like:

~~~text
invalid target release: 21
~~~

usually indicate the compiler does not recognize the requested target. Identify the javac actually executing, not just the IDE's Java version.

### 15.7. Bad class file has wrong version

Example:

~~~text
bad class file: library.jar
class file has wrong version 65.0, should be 61.0
~~~

A dependency may have been compiled for Java 21 while the active compiler/runtime only supports Java 17.

Solution: use a dependency version matching the baseline, or upgrade the compiler/runtime per plan. The application's release setting does not rewrite dependency JARs into older bytecode.

### 15.8. Annotation processor errors

Examples:

~~~text
IllegalAccessError
ExceptionInInitializerError
NoClassDefFoundError
~~~

inside a processor when upgrading the compiler can reflect Lombok/processor/tooling versions incompatible with the JDK. Inspect the stack trace, upgrade the processor, and verify the compiler JDK instead of disabling release.

## 16. Maven Wrapper, plugin versions, and reproducible builds

Projects should minimize discrepancies between developer machines, CI, and release pipelines.

A baseline may include:

- Controlled Maven Wrapper or Maven version.
- Explicit compiler plugin version.
- Documented JDK toolchain.
- Managed maven.compiler.release.
- Pinned processor versions.
- Controlled dependency versions/BOMs.
- Runtime test matrix.
- Managed plugin versions in parent POM.
- Build logs recording actual JDK and effective configuration.

### 16.1. Why Maven Wrapper is not enough

Maven Wrapper standardizes the Maven distribution, yet does not automatically install/enforce every JDK or ensure all tools use the same JDK. JAVA_HOME, PATH, toolchains, and CI images still must be managed.

### 16.2. Why plugin versions must be pinned

If builds depend on default plugins whose versions change via Maven lifecycle or parent POM updates, compilation results can shift when environments update. Pinning versions and verifying the effective POM reduces drift.

However, pinning versions does not mean staying on ancient plugins forever. When upgrading the JDK, upgrade plugins according to compatibility matrices and release notes.

### 16.3. Build reproducibility goes beyond class files

Beyond the compiler, reproducibility is also influenced by:

- Annotation processors.
- Compiler flags.
- Locale/timezone.
- Input ordering and generated code.
- Dependency resolution.
- Resource filtering.
- Manifests and timestamps.
- Packaging plugins.
- Operating system and filesystem behavior.

Maven compiler release is an important piece, though not the entire mechanism behind reproducible builds.

## 17. Equivalents in Gradle

In Gradle, Java toolchains and release targets must likewise be distinguished.

Java/Groovy DSL example:

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

This configures a JDK 21 toolchain for Java compilation while requiring target release 17.

A configuration setting only:

~~~groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
~~~

may not provide the platform API guarantees of options.release on compilers supporting --release. Distinguish and check according to actual Gradle/JDK versions.

### 17.1. Maven and Gradle side by side

| Need | Maven | Gradle |
|---|---|---|
| Choose release target | maven.compiler.release or plugin release | JavaCompile.options.release |
| Choose compiler JDK | Maven Toolchains / compiler configuration | Java Toolchains |
| Choose build tool runtime | JAVA_HOME, launcher, environment | JVM running Gradle daemon/launcher |
| Choose test JVM | Surefire/Failsafe configuration | Test task javaLauncher/toolchain |
| Inspect resolved config | effective-pom, active-profiles, debug logs | task configuration, --info/--debug, and Java Toolchain info |
| Inspect dependencies | dependency:tree | dependencies, dependencyInsight |

Maven example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle example:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Both aim to constrain compiler release, though build lifecycles, plugin inheritance, and toolchain selection still differ.

## 18. Library API baseline and the dependency graph

When building a library targeting Java 17, not only classes produced by the project must match the baseline. Dependencies loaded at runtime must also support Java 17.

Example:

~~~text
my-library.jar            major 61 / Java 17
  |
  +-- dependency-a.jar    major 61 / Java 17
  |
  +-- dependency-b.jar    major 65 / Java 21
~~~

Maven Compiler Plugin can compile main sources with release 17, yet does not automatically recompile dependency-b.jar into Java 17. Depending on how it is referenced, incompatibilities may surface at compile time or only when the runtime loads the class.

### 18.1. Inspecting the dependency graph

~~~bash
./mvnw dependency:tree
~~~

To filter a dependency by groupId/artifactId, use the appropriate parameters of the Maven Dependency Plugin in use.

Check:

- Direct dependencies.
- Transitive dependencies.
- Plugin dependencies.
- Annotation processors.
- Test/runtime scopes.
- Java agents and framework/container libraries.
- Multi-release JARs if present.

### 18.2. How to verify bytecode baselines

You can use bytecode scanning tools/Enforcer rules or dedicated scripts to inspect the maximum class-file major version of runtime artifacts. Never infer “the Maven build is green, so every JAR runs on Java 17”.

If a dependency raised its Java baseline, typical options are:

1. Keep a dependency version that still supports the target release during the transition period.
2. Raise the application's runtime baseline if feasible.
3. Replace the dependency.
4. Extract into a module/service running a newer JVM behind a clear API boundary.

## 19. Maven Enforcer and compiler release solve different problems

maven-enforcer-plugin can enforce specific build conditions, such as the running Maven or Java version.

Conceptual example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-environment</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The example requires Maven to run on Java 17 or newer. It does not mean the compiler emits Java 17 bytecode, because the compiler could use a different toolchain and release target.

Furthermore, the requireJavaVersion rule applies to the JVM running Maven as implemented by the plugin. It does not guarantee the production JVM satisfies the requirement or that all dependency bytecode matches the baseline.

You can combine:

- Enforcer to control the build environment.
- Toolchains to control the compiler.
- Compiler release to control Java Platform APIs and class target.
- Dependency/bytecode scanning to control artifacts.
- Runtime tests to control product behavior.

## 20. JPMS and module-info.java when using release

When moving from Java 8 to Java 9+, projects may add module-info.java.

Example:

~~~java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
}
~~~

The compiler needs source/release compatible with module syntax and APIs. Under release 8, module descriptors are not valid Java 8 syntax. When targeting 17 or 21, javac compiles module-info under the corresponding rules.

### 20.1. Module path vs. classpath

maven-compiler-plugin can interact with the module path when modular configuration is detected, though you must check:

- Module descriptor.
- requires/exports/opens.
- Which artifacts are named modules or automatic modules.
- Dependency versions.
- Annotation processors and generated modules.
- Whether Surefire/Failsafe runs tests on classpath or module path.

**release=17 does not automatically open internal packages for reflection.** InaccessibleObjectException, IllegalAccessError, or module readability errors must be addressed through JPMS and dependency compatibility, not compiler release alone.

### 20.2. --release does not mean --add-exports

When compiling code depending on JDK internals, some teams add --add-exports. However, with --release, javac restricts access to APIs outside the platform release. Do not combine flags to keep relying on internals as a standard solution.

Prioritize migrating to public APIs and libraries supporting the target JDK.

## 21. Multi-release JARs: an exception by design

A library may wish to support Java 11 while using optimized implementations specifically for Java 17 or 21. Multi-release JARs are a different mechanism from simply changing maven.compiler.release.

Example layout:

~~~text
META-INF/MANIFEST.MF
com/example/Feature.class                  (baseline Java 11)
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

The manifest must declare the proper multi-release attribute. Building typically requires separate source sets, compiler executions, and output directories, with each class compiled against its matching release.

Do not merely swap the release property in a single compile step and expect Maven to automatically assemble a multi-release JAR. It is a multi-step packaging configuration with strict rules.

### 21.1. Risks when using MR-JARs

- Public APIs between baseline and versioned classes must obey multi-release JAR constraints.
- Tests must run across all supported runtimes.
- Dependency versions may vary.
- JAR tooling, shading, and bytecode scanning must understand versioned entries.
- Debugging and runtime dispatch are harder.

Use MR-JARs only when benefits truly justify the complexity; many applications can opt for simpler separate modules or services.

## 22. Two-phase migration strategy

A practical roadmap is **upgrading build tools first**, then **upgrading the application's Java baseline**.

### Phase A — Use the new compiler while keeping the old release

Suppose the application runs on Java 17 and wants to prepare the build JDK upgrade to 21:

~~~text
Before:
  Maven/Javac JDK 17
  release 17
  runtime 17

After phase A:
  Maven/Javac JDK 21
  release 17
  runtime 17
~~~

Benefits:

- Surfaces plugins/processors incompatible with the new compiler.
- Validates build scripts on the new JDK.
- Ensures sources do not accidentally call Java 21 APIs.
- Keeps production runtime unchanged during the initial phase.

### Phase B — Raise release together with runtime

Once the application server, dependencies, and runtime are ready:

~~~text
After phase B:
  Maven/Javac JDK 21
  release 21
  runtime 21
~~~

Only now intentionally adopt Java 21 syntax/APIs. Run tests and verify runtime changes: TLS, reflection, garbage collector, serialization, and frameworks.

### 22.1. Advantages of two phases

If builds fail in phase A, the root cause likely sits in compiler/plugins/processors. If failures occur only after phase B, they more likely relate to source/API baseline or runtime behavior. Splitting phases makes root-cause analysis far easier than changing everything at once.

## 23. CI matrix and artifact verification

A pipeline should clearly report:

~~~text
Maven version
JDK running Maven
Compiler toolchain JDK
Compiler plugin version
Effective release target
Dependency versions
Main/test class-file major versions
Runtime test JDK(s)
Build/test results
~~~

### 23.1. Suggested jobs

**Compile baseline:** Use the chosen compiler with the official release target.

**Runtime baseline test:** Execute unit/integration tests on the lowest Java version supported by the product.

**Runtime newest-supported test:** Run on the new target Java to detect behavioral shifts.

**Dependency scan:** Check whether any JAR exceeds the baseline class-file version.

**API scan:** Detect JDK internal APIs or deprecated APIs as needed.

**Packaging smoke test:** Start the packaged artifact on the exact production runtime/container.

### 23.2. Do not test only on the compiler JDK

If compiling with JDK 21 and release 17, running tests only on JDK 21 does not prove the artifact runs on JDK 17. While --release constrains platform APIs, dependencies, agents, or runtime behavior can still fail on JDK 17.

### 23.3. Inspect the packaged JAR

Checking only target/classes can miss:

- Shaded dependencies.
- Classes generated by other plugins.
- Multi-release entries.
- Bytecode instrumentation.
- Dependencies embedded into executable JARs.

When preparing a release, inspect the final artifact that users/production will actually run.

## 24. Investigation workflow when Maven builds for the wrong release

### Step 1 — Identify the symptom

Examples:

- Compiler does not support release.
- Compiled source uses overly new APIs.
- Class-file major is higher than runtime supports.
- CI and local builds emit different artifacts.
- One reactor module uses a different release.
- Annotation processor breaks after JDK upgrade.
- Test JVM is older than compiled classes.

### Step 2 — Confirm the actual maven-compiler-plugin and release

Inspect:

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw help:active-profiles
~~~

Review parents, pluginManagement, plugin executions, profiles, and command-line overrides.

### Step 3 — Confirm javac/toolchain

Maven -version reports the JVM running Maven. You also need compiler plugin logs/toolchain output to determine the actual javac.

If using custom executables/forks, inspect that configuration. Do not rely solely on JAVA_HOME.

### Step 4 — Run a clean compile

~~~bash
./mvnw clean compile
~~~

Deleting old outputs prevents seeing leftover class files from a prior compile. In reactor builds, select the exact module where needed.

### Step 5 — Check class-file major version and API usage

Use javap on compiled classes. Verify sources do not call overly new Java Platform APIs by compiling with the release target and analyzing JDK internals where relevant.

### Step 6 — Inspect dependency bytecode

Check the dependency graph, dependency class versions, and suitability on the target runtime. Do not generalize from the main artifact's bytecode alone.

### Step 7 — Run runtime tests on the baseline JDK

If the product must run on Java 17, include at least one test job on real Java 17. Then run an additional job on the newer JDK.

### Step 8 — Record configuration and changes

Save Maven/JDK/plugin versions, release targets, dependency updates, and test outcomes. When builds later change, you can compare instead of guessing.

## 25. Common configuration mistakes

### “JAVA_HOME is 21, so the artifact definitely runs on Java 21”

Incorrect. release may be 17; Maven may use another compiler toolchain; production runtime is also independent.

### “source=8 and target=8 equals release=8”

Incorrect on modern compilers without Java Platform API restrictions. Source/target can allow code to call APIs existing only on the newer JDK.

### “If target is 8, NoSuchMethodError cannot happen on Java 8”

Incorrect. Version 52 class files can still reference methods absent in Java 8 if the build does not constrain platform APIs.

### “Maven Toolchains replaces release”

Incorrect. Toolchain picks the compiler JDK, whereas release chooses the Java baseline targeted by sources and bytecode.

### “release also constrains third-party dependencies”

Incorrect. You must inspect dependency bytecode, the transitive graph, and runtime compatibility separately.

### “Root build passed, so every module shares the same release”

Not necessarily. Modules can override properties, plugin executions, profiles, or use different source generators.

### “Only updating the compiler plugin version is enough”

Insufficient. Reconcile build JDK, release target, annotation processors, Surefire/Failsafe, and dependency versions.

### “Compilation passed means migration verification is complete”

Incorrect. Class files may execute on a different runtime than the compiler; reflection, TLS, binary compatibility, and framework behavior require runtime tests.

### “Maven Wrapper automatically guarantees the JDK”

Incorrect. The wrapper mainly standardizes the Maven distribution. JDKs still must be managed via environment/toolchains.

### “Raising release to the latest version is always best”

Incorrect. Release must align with the minimum runtime and support requirements of the product.

## 26. Controlled Maven configuration template

Example of a project using Maven Compiler Plugin with a Java 17 baseline:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example shows both the property and direct release configuration to illustrate valid locations, yet in a real project you should **choose one explicit configuration source** to avoid unnecessary duplication.

If you want one property driving the target, remove the release element from plugin configuration and keep maven.compiler.release. If you want all compiler settings inside the plugin, remove the release property from properties. Check the effective POM after deciding.

### 26.1. Organizational configuration rules

A practical convention might be:

- Parent POM manages the maven-compiler-plugin version.
- Parent defines the shared baseline release.
- Children override only for documented product reasons.
- CI uses a toolchain new enough to compile all release targets.
- Plugins/processors are selected via compatibility matrices.
- Builds always run tests on both the minimum runtime and the target JDK.
- Do not maintain source/target alongside release unless a verified special use case requires it.

A unified configuration immediately shows reviewers which Java version artifacts target instead of requiring searches across multiple scattered properties.

## 27. Pre-sign-off migration checklist

- [ ] Confirmed running Maven version.
- [ ] Confirmed Maven JVM and actual javac compiler JDK.
- [ ] Confirmed maven-compiler-plugin version.
- [ ] Reviewed effective POM of relevant modules.
- [ ] Confirmed release target matches the lowest supported runtime.
- [ ] Removed conflicting source/target when using release.
- [ ] Verified compiler JDK supports the chosen release.
- [ ] Checked module overrides and profiles.
- [ ] Verified annotation processors/generators are compatible with compiler JDK.
- [ ] Verified source does not call Java APIs newer than target release.
- [ ] Confirmed class-file major version of the main artifact.
- [ ] Checked bytecode/dependency baseline.
- [ ] Executed clean build from empty output.
- [ ] Executed tests on the lowest supported Java runtime.
- [ ] Executed tests on the new target Java runtime.
- [ ] Inspected the final artifact, including shaded/multi-release JARs if applicable.
- [ ] Documented residual risks and rollback plan.

## 28. Compiler and release configuration record template

~~~text
PROJECT / MODULE
  Repository:
  Maven version:
  Maven wrapper version:
  maven-compiler-plugin version:
  Parent POM:
  Active profiles:

BUILD JDK
  JDK running Maven:
  JAVA_HOME:
  Compiler JDK / toolchain:
  Annotation processor JDK/context:

JAVA BASELINE
  Current release:
  Target release:
  Minimal supported runtime:
  Production runtime:
  Preview features enabled?:

COMPILER CONFIG
  maven.compiler.release:
  source/target settings:
  Direct plugin configuration:
  Module overrides:
  Compiler args:
  Generated sources:

DEPENDENCIES
  Runtime dependency graph:
  Maximum dependency class-file major:
  Processor/tooling versions:
  Known unsupported APIs:

VALIDATION
  Effective POM:
  Clean compile:
  Class-file major:
  Unit tests:
  Integration tests:
  Runtime matrix:
  Packaged artifact smoke test:

DECISION
  Accepted configuration:
  Exceptions:
  Owner:
  Rollback:
  Next upgrade milestone:
~~~

Store this record alongside the POM, CI configuration, and migration docs so other teams can reproduce the exact tools and release settings used.

## 29. Summary

maven-compiler-plugin is one of the most important control points when transitioning Java versions. Its **release** feature enables modern compilers to generate code for a specific Java baseline and prevents unintentionally calling APIs newer than promised.

Principles to remember:

1. **Do not confuse the build JDK with the target runtime.** A newer JDK can compile for an older release.
2. **Prefer release over source/target alone.** Release restricts syntax, class files, and Java Platform APIs together.
3. **Toolchain and release answer two different questions.** Toolchain picks javac; release picks the language/API baseline.
4. **Read the effective POM.** Parents, pluginManagement, profiles, and child modules can all alter settings.
5. **Inspect actual artifacts.** Class-file major versions, dependencies, processors, and runtime tests all need verification.
6. **Split migration into phases.** Upgrade compiler/tooling first, then upgrade Java release/runtime afterward.
7. **Do not treat compile success as the end.** Compatibility also encompasses runtime, frameworks, reflection, TLS, native dependencies, and consumer behavior.

When selecting release based on application requirements and verifying from the POM through the final artifact, development teams can upgrade Maven, the JDK, and dependencies in a controlled manner—avoiding releasing bytecode or Java APIs beyond what production environments support.
