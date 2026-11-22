# Troubleshooting Unsupported Class Version Errors in Java

## 1. What is an Unsupported Class Version Error?

**UnsupportedClassVersionError** is a JVM error indicating that a `.class` file was generated in a newer bytecode format than the current Java runtime supports. The most common case is a project compiled with a newer JDK while the application runs on an older JRE/JDK.

Example:

~~~text
java.lang.UnsupportedClassVersionError:
  demo/App has been compiled by a more recent version of the Java Runtime
  (class file version 61.0),
  this version of the Java Runtime only recognizes class file versions up to 55.0
~~~

Explanation:

- The class to be executed has major version 61, corresponding to Java 17.
- The runtime only supports up to major version 55, corresponding to Java 11.
- Java 11 cannot load a class compiled for Java 17.
- You need to upgrade the runtime to Java 17 or higher, or rebuild all relevant classes with a target compatible with Java 11.

The error can appear when running the main application, loading a library, initializing a plugin, running tests, running an annotation processor, or starting a build tool. Therefore, a project compiling successfully does not prove that the runtime on the target machine is new enough.

## 2. How does the JVM read class file versions?

Every class file begins with a binary header. The beginning consists of:

| Field | Size | Meaning |
|---|---:|---|
| magic | 4 bytes | Fixed value 0xCAFEBABE, identifying a class file |
| minor_version | 2 bytes | Minor version |
| major_version | 2 bytes | Major class format version |

The JVM reads the major/minor versions before verifying and executing bytecode. For modern class files, the major version increases with each Java SE release. This number does not match the Java version number: Java 17 produces class file major version 61, not 17.

A class file with a major version higher than what the JVM supports will be rejected during class loading. This is a bytecode format compatibility error, not a Java syntax error or a missing class in the classpath.

## 3. Mapping Table of Java Releases and Class File Major Versions

Common milestones:

| Java release | Class file major | Notes |
|---|---:|---|
| Java 8 | 52 | Many legacy applications and libraries |
| Java 11 | 55 | LTS |
| Java 17 | 61 | LTS |
| Java 21 | 65 | LTS |
| Java 24 | 68 | JDK 24 |
| Java 25 | 69 | LTS |
| Java 26 | 70 | JDK 26 |

The JVM of a given release supports older major versions within the specification's compatibility range. For example, Java 25 supports class file major 69 and earlier major versions; Java 24 only supports up to major 68.

Do not take the major number and subtract one to deduce the Java release. Refer to the table or use `javap -verbose` to read the actual class file. The JVMS specification for each release is the authoritative source when handling new versions.

## 4. Distinguishing Compile JDK, Target Release, and Runtime JDK

These three versions can differ:

- **Compile JDK:** The JDK providing `javac` used to compile the source.
- **Target release:** The Java release that the output class files must be compatible with.
- **Runtime JDK:** The JVM that actually runs the application or library.

For example, a team can compile with JDK 24, set the target to Java 17, and deploy on a Java 17 runtime. This configuration is valid if all dependencies, plugins, and loaded classes are also compatible with Java 17.

Conversely, compiling with JDK 24 by default usually produces class file major version 68. Running that file on Java 17 will cause an `UnsupportedClassVersionError`.

Do not confuse which JDK Maven/Gradle runs on with the JDK used for the compile task. Maven Toolchains or Gradle Java Toolchains can select a different compiler from the JVM running the build tool.

## 5. Reading the Error Message Correctly

Look for three parts in the stack trace:

1. **Class name:** for example, `com/example/LibraryAdapter`. This is usually the first class rejected by the JVM.
2. **Class file version:** for example, `65.0`. This is the bytecode version of the class being loaded.
3. **Runtime recognizes up to:** for example, `61.0`. This is the limit of the current JVM.

Example:

~~~text
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

The class requires Java 21, while the runtime only supports up to Java 17. Upgrade the runtime to Java 21 or higher, or use a dependency/build version compatible with Java 17.

If the message mentions preview features, check the minor version and the `--enable-preview` flag. Not every `UnsupportedClassVersionError` is solely a major version mismatch.

## 6. Common Causes

| Cause | Example |
|---|---|
| Compiled with a newer JDK | Compiled with Java 25 by default, run on Java 17 |
| Dependency newer than runtime | Application targets Java 17, but a library requires Java 21 |
| Wrong Java selected on PATH | `javac` is JDK 24, but `java` runs JDK 11 |
| IDE and terminal use different JDKs | Terminal uses Java 21, IDE Run Configuration uses Java 17 |
| Maven/Gradle uses a different JVM | Build daemon runs Java 17, plugin or compiler toolchain selects a different Java |
| Different Docker build/runtime images | Builder compiles Java 24 classes, runtime image contains Java 17 |
| CI uses inconsistent runners | Build job uses JDK 25, deploy/test job uses JDK 17 |
| Plugin or annotation processor | Plugin is compiled for a newer JDK than the JVM running Maven/Gradle |
| Preview class file | Compiled with preview in one release and run in another release or missing the enable flag |

Application classes are not the only ones that can cause the error. A transitive JAR, plugin, processor, or dynamically loaded class can also be the source.

## 7. Checking Which Java Runtime is Actually Running

First, check both the runtime and the compiler:

~~~bash
java --version
javac --version
~~~

On Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

On Linux/macOS:

~~~bash
command -v java
command -v javac
readlink -f "$(command -v java)"
echo "$JAVA_HOME"
~~~

Check the runtime properties:

~~~bash
java -XshowSettings:properties -version
~~~

Look for `java.version` and `java.home` in the output. `java.home` indicates the runtime used by that process.

A machine can have multiple JDKs installed. `PATH` might point to Java 11 while `JAVA_HOME` points to JDK 24, or an IDE/daemon holds a different Java home. Checking only the `JAVA_HOME` variable is not enough; you must check the exact command/process that produces the error.

## 8. Inspecting Class Files with javap

`javap` comes with the JDK and can display the class header:

~~~bash
javap -verbose -classpath target/classes demo.App
~~~

Look for two lines:

~~~text
minor version: 0
major version: 61
~~~

The class above was compiled for Java 17. On Windows, you can filter the output:

~~~powershell
javap -verbose -classpath target/classes demo.App | Select-String "minor version|major version"
~~~

On Linux/macOS:

~~~bash
javap -verbose -classpath target/classes demo.App | grep -E "minor version|major version"
~~~

Use the correct classpath to avoid accidentally inspecting another copy of a class with the same name. If the class is inside a JAR, add the JAR to the classpath:

~~~bash
javap -verbose -classpath libs/example-library.jar com.example.LibraryAdapter
~~~

If the current JDK is too old to understand that class file, `javap` may also reject it. In that case, run `javap` using a newer JDK or use an appropriate class-file header reader tool.

## 9. Identifying the Causing Dependency

When the stack trace points to a class belonging to an external library, locate the JAR containing that class and then check its version:

~~~bash
jar tf libs/example-library.jar
javap -verbose -classpath libs/example-library.jar com.example.LibraryAdapter
~~~

With Maven, inspect the dependency tree:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:example-library
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

Check transitive dependencies as well. A project might directly declare a Java 17-compatible library, while another dependency pulls in a newer version requiring Java 21.

If the failing class belongs to a build plugin, check the classloader/plugin realm and plugin version. The runtime running Maven/Gradle must be new enough to load the plugin, even if the application target release can be lower.

## 10. Fix 1: Upgrade the Java Runtime

If the application or a dependency genuinely needs APIs/language features from a newer Java version, upgrade the runtime to the same release or newer.

For example, class file major 69 requires a Java 25 or higher runtime:

~~~bash
java --version
java -jar app.jar
~~~

After upgrading the runtime, verify:

- The service runs using the correct new Java executable.
- `JAVA_HOME`, `PATH`, service wrappers, and startup scripts point to the right location.
- Production containers/VMs/hosts have the same runtime.
- IDEs, scheduled tasks, Windows Services, or systemd units do not retain the old Java path.
- Frameworks, drivers, and native libraries remain compatible with the new runtime.

Do not just install a new JDK on the build machine and assume production has been upgraded. You must update the environment that actually launches the application.

## 11. Fix 2: Compile to a Lower Java Release

If production must run Java 17, build Java 17-compatible class files even if the build machine uses JDK 24 or JDK 25.

Using `javac`:

~~~bash
javac --release 17 -d target/classes src/main/java/demo/App.java
~~~

`--release 17` simultaneously controls:

- Java 17 syntax/language rules.
- Class file target Java 17 (major 61).
- The set of Java/JDK APIs allowed under Java 17.

This is a more reliable way to cross-compile than only setting `source` and `target`. If the source calls an API introduced only in Java 21, `javac` will report an error when building with `--release 17` instead of letting the error appear at runtime.

Only use the lowest release that the product needs to support and that all dependencies can satisfy.

## 12. Why source/target Do Not Fully Replace --release

Two legacy options:

~~~bash
javac -source 17 -target 17 App.java
~~~

`-source` selects the language rules; `-target` selects the output bytecode format. When compiling with a newer JDK, the compiler can still see APIs newer than the target release if the platform API is not appropriately restricted.

For example, code using a Java 21 API can compile on JDK 21 with `source/target 17`, but will not run on Java 17 because the runtime lacks that API. This can lead to `NoSuchMethodError` or `NoClassDefFoundError`, even though the class major version is already correct.

`--release` checks both the class-file target and the APIs of the target release. For JDK 9 and later, prefer `--release` for builds requiring backward compatibility.

## 13. Configuring Maven Compiler Plugin

Example POM targeting Java 17:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

Build and verify:

~~~bash
mvn -B -ntp clean package
javap -verbose -classpath target/classes demo.App
java -jar target/app.jar
~~~

When using JDK 9 or later, the Compiler Plugin passes `release` to `javac`. Maven Compiler Plugin 3.13.0 and later also provide a compatibility mechanism for building with JDK 8 when using the default compiler; JDK 8 does not have the `--release` option, so the plugin falls back to the appropriate `source`/`target`. For legacy projects, read the documentation for the pinned plugin version.

## 14. Configuring Gradle Java Toolchain and options.release

Groovy DSL example using JDK 24 to compile while targeting Java 17 bytecode/APIs:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

If the team already has JDK 17 installed and wants both compiler and tests to use JDK 17, set the toolchain to 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

The toolchain selects the JDK for compile/test/Javadoc tasks. `options.release` restricts the language/API/class file target. The two settings serve different purposes and can be used together.

Check the toolchains Gradle detects:

~~~bash
./gradlew -q javaToolchains
./gradlew --version
./gradlew clean test
~~~

`gradlew --version` displays the JVM running Gradle/daemon. `javaToolchains` shows the JDKs detected and used as toolchains by Gradle.

## 15. Checking Which JDK Maven and Gradle Are Using

Maven:

~~~bash
mvn --version
./mvnw --version
mvn -X -DskipTests compile
~~~

`mvn --version` shows the Java running Maven. If Maven Toolchains are configured, the Compiler Plugin may use a different JDK to compile. Check the toolchain configuration and debug logs when you need to determine the actual compiler.

Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew -Dorg.gradle.java.home=/path/to/jdk17 test
~~~

`org.gradle.java.home` selects the JVM running the Gradle daemon; it does not replace the Java Toolchain declaration for compile/test tasks. Do not set this path to a JRE that is too old if the Gradle version in use requires a newer JVM.

Maven Wrapper and Gradle Wrapper pin the build tool version; they do not automatically pin the Java runtime or bytecode target. Manage all three factors: build tool, compiler toolchain, and deployment runtime.

## 16. Checking IDE and Build Daemon

A project may build in the terminal but fail in the IDE because the IDE uses a different JDK.

Check these locations:

- **IntelliJ IDEA:** Project SDK, language level, Maven Runner JRE, Gradle JVM, and Run/Debug Configuration.
- **Eclipse:** Installed JREs, compiler compliance level, and the JRE of each Run Configuration.
- **VS Code:** Java runtime configuration and the JDK selected for the project.
- **Gradle:** JVM running the daemon, Java Toolchain, and launcher for Test/JavaExec tasks.
- **Maven:** JVM running Maven, Maven Toolchains, and compiler plugin configuration.

After changing the JDK, stop the old daemon if it still holds onto the previous JVM:

~~~bash
./gradlew --stop
~~~

Open a new terminal or restart the IDE when the environment has changed. Re-check `java.version` and `java.home` of the actual process running the application.

## 17. Checking Docker and Container Runtime

A common mistake is having a builder image newer than the runtime image:

~~~dockerfile
FROM eclipse-temurin:24-jdk AS build
WORKDIR /app
COPY . .
RUN ./mvnw -B -ntp clean package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

If Maven compiles with JDK 24 by default, class files may be major 68 while the final container only has Java 17 (major 61). The application will fail on startup.

There are two approaches:

1. Keep the Java 17 runtime and configure the compiler with `--release 17`.
2. Upgrade the runtime image to Java 24 or the release corresponding to the classes/dependencies.

Example targeting Java 17:

~~~dockerfile
FROM eclipse-temurin:24-jdk AS build
WORKDIR /app
COPY . .
RUN ./mvnw -B -ntp -Dmaven.compiler.release=17 clean package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Inspect the runtime image after building:

~~~bash
docker run --rm your-app-image java --version
~~~

Do not rely on the JDK installed on the host. The JVM inside the container is the actual runtime of the application.

## 18. Dependencies and Plugins Must Also Be Compatible

An application targeting Java 17 can still fail if a dependency was built for Java 21 or higher. Setting `release` in `pom.xml`/`build.gradle` only controls code compiled by the project's compiler task; it does not automatically downgrade the bytecode of downloaded dependencies.

Troubleshooting steps:

1. Identify the first class in the `UnsupportedClassVersionError`.
2. Locate the JAR or plugin containing that class.
3. Check the resolved version using dependency tree/insight.
4. Check the Java baseline published by the library maintainer.
5. Upgrade the runtime or downgrade the dependency to a version supporting the baseline.
6. Rebuild and run tests on the lowest supported runtime.

For Maven plugins or annotation processors, check the JDK running Maven and the compatibility of the plugin itself. For Gradle plugins, check the Gradle JVM and the plugin's Java requirements.

Do not try to fix this by adding another dependency to the classpath if the class already exists but its bytecode is too new.

## 19. Preview Features and Minor Version 65535

Since Java 12, class files using preview features have minor version `65535`. For example, a Java 26 preview class has version `70.65535`.

To compile preview features, enable preview in the compiler:

~~~bash
javac --enable-preview --release 26 -d out src/demo/PreviewDemo.java
~~~

And enable preview at runtime on the same release:

~~~bash
java --enable-preview -cp out demo.PreviewDemo
~~~

Preview class files are tied to the exact Java release that produced them. A Java 25 preview class cannot run on Java 26 simply by adding `--enable-preview`; it must be recompiled with the new release. Missing the preview flag at runtime can also cause `UnsupportedClassVersionError` even if the major version is correct.

Do not use preview features for artifacts requiring broad compatibility unless you have a plan to build, test, and deploy on the same release.

## 20. Multi-Release JARs and Class Files Across Multiple Java Releases

A multi-release JAR can contain different implementations per Java release:

~~~text
app.jar
  META-INF/MANIFEST.MF
  com/example/Parser.class
  META-INF/versions/17/com/example/Parser.class
  META-INF/versions/21/com/example/Parser.class
~~~

The manifest must declare:

~~~text
Multi-Release: true
~~~

The JVM selects the implementation matching the running release. The root entry in the JAR must still support the lowest baseline the product declares; entries in `META-INF/versions/N` are only used on runtimes that are new enough.

Inspect the JAR contents:

~~~bash
jar --list --file app.jar
jar --describe-module --file app.jar
~~~

When creating a multi-release JAR, compile each part with the corresponding release and test on each runtime. Do not place newer classes in the root directory expecting older Java versions to automatically ignore them.

## 21. Java 17+ Example to Check Class Version

Create the file `src/demo/VersionProbe.java`:

~~~java
package demo;

public final class VersionProbe {
    public static void main(String[] args) {
        System.out.println("READY class version");
    }
}
~~~

Compile for Java 17 using a newer JDK:

~~~bash
javac --release 17 -d out src/demo/VersionProbe.java
~~~

View the class file header:

~~~bash
javap -verbose -classpath out demo.VersionProbe
~~~

Key output:

~~~text
minor version: 0
major version: 61
~~~

Run the program:

~~~bash
java -cp out demo.VersionProbe
~~~

Exact stdout:

~~~text
READY class version
~~~

This example was tested with Azul JDK 24.0.2. `javac` 24 compiling with `--release 17` produces major 61/minor 0; JVM 24 runs the class and prints the exact output.

## 22. Reproducing UnsupportedClassVersionError in a Controlled Way

You can test how the JVM rejects a newer class file without installing a newer JDK by creating a test copy and changing the major version in the header. This is a diagnostic test, not a way to fix applications.

On Windows PowerShell, after compiling `VersionProbe` as in the previous section:

~~~powershell
$bytes = [System.IO.File]::ReadAllBytes("out\demo\VersionProbe.class")
$bytes[4] = 0
$bytes[5] = 0
$bytes[6] = 0
$bytes[7] = 69

New-Item -ItemType Directory -Force -Path "out-new\demo" | Out-Null
[System.IO.File]::WriteAllBytes("out-new\demo\VersionProbe.class", $bytes)

java -cp out-new demo.VersionProbe
~~~

The two bytes at positions 6 and 7 are the major version in big-endian format. The value 69 simulates a Java 25 class file. JDK 24 only supports up to major 68, so the test returns a similar error:

~~~text
java.lang.UnsupportedClassVersionError:
  demo/VersionProbe has been compiled by a more recent version of the Java Runtime
  (class file version 69.0),
  this version of the Java Runtime only recognizes class file versions up to 68.0
~~~

In testing, the original major 61 class ran successfully; the copy with its header changed to major 69 was rejected by JVM 24 with exit code 1. Do not modify production class files by altering header bytes: a newer major version may come with bytecode, constant-pool entries, or structures that an older JVM does not understand.

## 23. Errors Easily Confused with UnsupportedClassVersionError

| Error | Common meaning |
|---|---|
| UnsupportedClassVersionError | JVM does not support the major/minor version of the class file |
| ClassNotFoundException | Class not found when code requests loading by name |
| NoClassDefFoundError | Required class is missing at runtime or earlier class initialization failed |
| NoSuchMethodError | Class was loaded, but the runtime lacks the method linked by bytecode |
| NoSuchFieldError | Referenced field does not exist in the runtime class |
| UnsupportedClassVersionError due to preview | Class uses an incompatible preview version/flag |

Do not use the same fix for all linkage errors. If the class file loaded successfully but is missing a method/API, it is usually a dependency/API compatibility issue rather than a major version issue.

## 24. Step-by-Step Troubleshooting Process

When encountering the error, follow this sequence:

1. Copy the full `UnsupportedClassVersionError` and record the class name.
2. Read the required class file version and the maximum version supported by the runtime.
3. Run `java --version` from the exact shell/service/container that is failing.
4. Check `java.home`, `JAVA_HOME`, and the executable path.
5. Use `javap -verbose` to inspect the project's output classes.
6. Find the JAR/plugin containing the failing class.
7. View the dependency tree to identify the resolved version.
8. Decide whether to upgrade the runtime or downgrade the compile target/dependency.
9. Configure `--release` in `javac`, Maven, or Gradle.
10. Test a clean build and run on the lowest supported runtime.
11. Re-check the IDE, daemon, CI runner, and production container.
12. Document the Java baseline clearly in README, build config, and release metadata.

Do not simply delete the `target`/`build` directory or cache and re-run without fixing the version mismatch. A clean build is useful for removing stale classes, but it does not make an older runtime understand newer bytecode.

## 25. Prevention Checklist

- [ ] Identify the lowest Java runtime the product supports.
- [ ] Pin the Java release target using `javac --release`, Maven `maven.compiler.release`, or Gradle `options.release`.
- [ ] Select a Java Toolchain for compiler and test tasks.
- [ ] Ensure direct and transitive dependencies support the same baseline.
- [ ] Check both the JDK running Maven/Gradle and the JDK toolchain used for compiling.
- [ ] Configure IDE project SDK, build JVM, and Run Configuration consistently.
- [ ] Use a runtime image compatible with the class files in Docker/production.
- [ ] Test artifacts on the exact lowest runtime, not just the latest JDK.
- [ ] Check preview features and minor version if using `--enable-preview`.
- [ ] Test multi-release JARs on each supported Java release.
- [ ] Document the Java baseline in installation docs and release pipelines.
- [ ] Update the runtime with testing when libraries or frameworks raise their Java requirement.

## 26. References

- [Java Virtual Machine Specification 26 — Introduction](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html): mapping table of Java releases and class file major versions, including Java 26 major 70.
- [Java Virtual Machine Specification 26 — Class File Format](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html): header structure, major/minor versions, and preview class file rules.
- [Oracle JDK 24 — javac command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html): `--release`, `--source`, `--target`, and compiling for older releases.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): configuring `maven.compiler.release` and limitations of `source`/`target`.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): examples of configuring release in Maven Compiler Plugin.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): selecting JDK for compile/test/Javadoc, combining toolchain and release, viewing detected toolchains.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java toolchain, `options.release`, and `source`/`target` compatibility.
- [Oracle JDK 26 — ClassFile API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html): major/minor model and minor version 65535 for preview.

`UnsupportedClassVersionError` almost always comes down to one question: which Java release was the class file built for, and what does the actually running JVM support? Read the class version, identify the actual runtime, and align the release target, dependencies, and deployment runtime to fix the root cause.
