# Troubleshooting UnsupportedClassVersionError and JDK Mismatches Between Build and Runtime

## 1. Diagnostic Goal

`UnsupportedClassVersionError` occurs when the JVM attempts to read a `.class` file but does not support that class file's `major_version`/`minor_version` pair. A common scenario is an application or dependency compiled with a newer Java version and then executed on an older Java version.

Example:

~~~text
class file version 65.0
this runtime only recognizes class file versions up to 61.0
~~~

Class major 65 corresponds to Java 21; major 61 corresponds to Java 17. A Java 17 JVM cannot load Java 21 class files. To fix it properly, identify **which class** is incompatible and **which JVM** is loading it, then align the runtime or compile for a supported release.

This lesson belongs to the **Troubleshooting** section under **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Read major/minor class-file versions and map them to Java releases.
2. Distinguish the JDK running Maven/Gradle, compiler toolchain, bytecode target, test JVM, and production JRE.
3. Reproduce the Java 21 bytecode on Java 17 error and fix it with `--release`.
4. Configure Maven Compiler Plugin, Maven Toolchains, and Gradle Java Toolchains.
5. Locate the offending class in project source, transitive dependencies, build plugins, or nested JARs.
6. Distinguish `UnsupportedClassVersionError` from `NoSuchMethodError`, `NoClassDefFoundError`, and API incompatibility errors.
7. Align Java versions across local IDE, CI runners, test runners, and Docker/Kubernetes runtimes.
8. Use a Java 17 program to read a class file's header.
9. Create a CI gate to prevent artifacts with bytecode newer than the supported runtime.

**Example baseline:** Java `17`, Spring Boot `3.5.16`, Maven, and Gradle. Spring Boot 3.5.16 requires at least Java 17; other dependencies or plugins may impose higher requirements. Java 17 is the baseline for these examples, not a guarantee that every library in every application is Java 17 compatible.

## 2. Class-File Version: What Do 61 and 65 Mean?

The Java compiler does not write the string "Java 17" directly into a class file. It writes a binary header with two fields:

- `minor_version`: minor version of the class file format.
- `major_version`: major version of the class file format.

The start of a class file has magic bytes `CA FE BA BE`, followed by the minor and major versions. The JVM uses this version pair to decide whether it can read the class format.

Some common major versions:

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 24 | 68 |
| Java 25 | 69 |

The general rule is `major = Java release + 44`. For example, Java 17 corresponds to 61, Java 21 to 65. The full table is defined in the Java Virtual Machine Specification, `Class File Format` section.

**Do not confuse the major version with the Maven, Spring Boot, or dependency version.** This is the bytecode format version that the JVM must read.

### 2.1. Reproducing Java 21 Bytecode on Java 17

Create source `src/demo/VersionMismatchDemo.java`:

~~~java
package demo;

public class VersionMismatchDemo {
    public static void main(String[] args) {
        System.out.println("compiled-for-java-21");
    }
}
~~~

Compile with JDK 21 without lowering the target:

~~~bash
javac --release 21 -d target/java21 src/demo/VersionMismatchDemo.java
~~~

The generated class has major version 65. Run with Java 17:

~~~bash
/path/to/jdk17/bin/java -cp target/java21 demo.VersionMismatchDemo
~~~

The Java 17 JVM rejects class file version 65. Representative message:

~~~text
Exception in thread "main" java.lang.UnsupportedClassVersionError:
demo/VersionMismatchDemo has been compiled by a more recent version
of the Java Runtime (class file version 65.0), this version of the
Java Runtime only recognizes class file versions up to 61.0
~~~

The actual message usually appears on one long line and the stack trace depends on the command executed. Focus on the pair **65.0 vs. 61.0**.

### 2.2. Fixing by Compiling for the Right Release

If the application must run on Java 17, recompile:

~~~bash
javac --release 17 -d target/java17 src/demo/VersionMismatchDemo.java
~~~

Run with Java 17:

~~~bash
/path/to/jdk17/bin/java -cp target/java17 demo.VersionMismatchDemo
~~~

Exact stdout:

~~~text
compiled-for-java-21
~~~

The output string stays the same, but the class file is now Java 17 compatible. JDK 21 can cleanly produce Java 17 bytecode via `--release 17`; not every developer is required to install JDK 17 itself if the build is configured properly and dependencies meet the baseline.

## 3. Distinguishing Java Versions in a Pipeline

A pipeline can simultaneously use several JVMs/JDKs:

| Component | Role | How to Check |
| --- | --- | --- |
| JVM running Maven/Gradle | Runs build tool and plugins | `mvn -version`, `./gradlew --version` |
| Compiler/toolchain JDK | Runs `javac` or corresponding compiler | Toolchain config and build logs |
| Java release/bytecode target | Governs class files and platform APIs | `maven.compiler.release`, `options.release` |
| Runtime JVM | Loads classes and runs app/tests/containers | `java -version`, Docker image |

Valid example:

~~~text
Maven JVM        : Java 21
Compiler JDK     : Java 21
Compiler release : 17
Test JVM         : Java 17
Production JRE   : Java 17
Output bytecode  : major 61
~~~

Risky example:

~~~text
Maven JVM        : Java 21
Compiler JDK     : Java 21
Compiler release : not configured, defaults to 21
Test JVM         : Java 21
Production JRE   : Java 17
Output bytecode  : major 65
~~~

In the second example, CI build and tests are green because CI uses Java 21, yet production Java 17 cannot load major 65 classes.

### 3.1. JDK and JRE

- `JDK` contains the `javac` compiler, debugger, and development tools, in addition to the JVM/runtime libraries.
- `JRE` provides the JVM execution environment and runtime libraries; JRE images typically lack `javac`.
- `java -version` checks the `java` executable that the shell invokes.
- `javac -version` checks the compiler executable that the shell invokes.

A machine may have multiple JDKs and multiple `java.exe` binaries on `PATH`. Terminal, Maven, IDE, and Docker do not necessarily pick the same one. Do not infer the runtime version from the compiler version.

### 3.2. Spring Boot Baseline

Spring Boot 3.5.16 requires at least Java 17. This release supports Java up to the version listed in system requirements; third-party libraries may require a higher Java version. Maven and Gradle also have their own compatibility matrices.

Even when application bytecode is major 61, a dependency may require Java 21, or a build plugin may need a newer JVM to run. Therefore you must check **framework, dependencies, build plugins, and runtime**, not just the main application classes.

## 4. Identifying the Actually Running JVM

Before editing the POM or switching Docker images, gather versions from each environment.

### 4.1. Terminal

Linux/macOS:

~~~bash
which -a java
which -a javac
java -version
javac -version
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
$env:JAVA_HOME
~~~

`which -a` or `Get-Command -All` shows whether multiple executables exist on PATH. `JAVA_HOME` is a hint for build tools; it does not prove every process uses that JDK.

### 4.2. JVM Running Maven

~~~bash
mvn -version
./mvnw -version
~~~

Output includes Maven version, Java version, Java home, and OS. `mvn -version` reports the JVM running Maven, **not necessarily the compiler toolchain** if the project uses Maven Toolchains.

If `java -version` reports Java 17 while `mvn -version` reports Java 11, inspect `JAVA_HOME`, the Maven launcher, shell/IDE environment, and the Maven Wrapper process.

### 4.3. JVM Running Gradle

~~~bash
./gradlew --version
./gradlew javaToolchains
~~~

`./gradlew --version` shows the Gradle version and JVM/daemon environment. `javaToolchains` lists JDKs Gradle detects and can use for tasks.

The Gradle daemon JVM and compiler toolchain can differ. A Gradle build running on JVM 21 can still compile using a JDK 17 toolchain; conversely, the JVM running Gradle must be compatible with the Gradle version in use.

### 4.4. JVM Inside a Container

~~~bash
docker run --rm --entrypoint java your-image:tag -version
~~~

This invokes `java` inside the **image**, not Java on the host. If Kubernetes uses a different image than local testing, inspect the image digest and runtime of the exact failing pod.

## 5. Identifying Which Class Has an Incompatible Major Version

The error usually names a class. Read the first class appearing in `UnsupportedClassVersionError` and determine whether it belongs to:

1. An application class compiled by the project.
2. A Spring Boot loader/framework class.
3. A direct or transitive dependency.
4. A plugin/build tool running inside Maven/Gradle.
5. Code generated by an annotation processor, Kotlin/Scala/Groovy compiler, or bytecode enhancement.
6. A class inside a nested JAR of a Spring Boot executable archive.

Do not assume the first class always comes from `src/main/java`. If Maven fails immediately while loading a plugin or Gradle fails before the compile task, the error may belong to the **build tool process**, not the application artifact.

### 5.1. Using `javap` to Read Major Version

For a class in Maven output:

~~~bash
javap -verbose target/classes/demo/VersionMismatchDemo.class
~~~

Look for the line:

~~~text
major version: 61
~~~

PowerShell:

~~~powershell
javap -verbose .\target\classes\demo\VersionMismatchDemo.class |
    Select-String "major version"
~~~

For a class in a normal dependency JAR:

~~~bash
javap -verbose -classpath path/to/library.jar com.vendor.LibraryType
~~~

The `major version` result shows the bytecode of the class analyzed by `javap`. If a dependency has many classes, check the exact class appearing in the stack trace.

### 5.2. Inspecting a Spring Boot Executable JAR

~~~bash
jar tf target/application.jar
~~~

A typical Spring Boot executable JAR contains:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/...
BOOT-INF/lib/spring-*.jar
BOOT-INF/lib/third-party-library.jar
org/springframework/boot/loader/...
~~~

Application classes reside under `BOOT-INF/classes`; dependencies reside in nested JARs under `BOOT-INF/lib`. `javap -classpath target/application.jar ...` does not automatically treat nested JARs as a standard classpath.

To inspect a class in a nested dependency, extract the inner JAR to a temporary directory:

~~~bash
mkdir -p target/inspect
cd target/inspect
jar xf ../application.jar BOOT-INF/lib/third-party-library.jar
javap -verbose -classpath BOOT-INF/lib/third-party-library.jar com.vendor.LibraryType
~~~

Replace `third-party-library.jar` with the actual entry found via `jar tf`. On Windows, you can run `jar xf` in a separate inspection directory and call `javap` similarly.

### 5.3. Finding the Transitive Dependency Source

Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dverbose
~~~

Locate the dependency whose group/artifact/version matches the failing JAR. The dependency may be pulled in transitively through a starter or another library. Check version mediation, exclusions, and effective POM before upgrading/downgrading versions.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency library-name --configuration runtimeClasspath
~~~

`dependencyInsight` shows where the dependency is requested, which version was selected, and why the resolver chose it. If the error occurs in tests, also check `testRuntimeClasspath`; if during compilation, check the compile classpath.

## 6. Java 17 Utility to Read the Class-File Header Directly

When you want to know the exact version of a `.class` file without relying on `javap`, read the first 8 bytes using the Java Standard Library.

Create `ClassVersionProbe.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassVersionProbe {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionProbe.java <class-file>");
        }

        Path path = Path.of(args[0]);
        byte[] bytes = Files.readAllBytes(path);

        if (bytes.length < 8
                || (bytes[0] & 0xff) != 0xca
                || (bytes[1] & 0xff) != 0xfe
                || (bytes[2] & 0xff) != 0xba
                || (bytes[3] & 0xff) != 0xbe) {
            throw new IllegalArgumentException(
                    "Not a valid Java class file: " + path);
        }

        int minor = ((bytes[4] & 0xff) << 8)
                | (bytes[5] & 0xff);
        int major = ((bytes[6] & 0xff) << 8)
                | (bytes[7] & 0xff);

        String release = major >= 45
                ? Integer.toString(major - 44)
                : "unknown";

        System.out.println("class.major=" + major);
        System.out.println("class.minor=" + minor);
        System.out.println("class.java-release=" + release);
    }
}
~~~

The program checks the `CAFEBABE` magic number, reads two 16-bit big-endian fields, and displays the corresponding release according to the standard major-version mapping. It requires only the Java 17 Standard Library, with no Maven/Spring imports.

Run on a compiled Java 17 class:

~~~bash
java ClassVersionProbe.java target/classes/demo/CompatibilityDemoApplication.class
~~~

If the class was compiled with release 17, exact stdout:

~~~text
class.major=61
class.minor=0
class.java-release=17
~~~

If the class was compiled with Java 21 without lowering the target:

~~~text
class.major=65
class.minor=0
class.java-release=21
~~~

**Limitation:** the utility reads one specific `.class` file. It does not automatically scan nested JARs, analyze `META-INF/versions/` of multi-release JARs, or prove the entire dependency graph is compatible. Use it to verify an identified class, then inspect dependencies per the stack trace.

## 7. Maven: Configuring the Release Target Explicitly

### 7.1. Complete Java 17 Spring Boot POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>java-compatibility-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`java.version` is the convention property used by the Spring Boot parent to configure the Java build. `maven.compiler.release` explicitly declares the target/API platform for the Maven Compiler Plugin. If using another parent, verify which property the plugin actually reads.

### 7.2. `--release` Differs from `source`/`target`

Maven Compiler Plugin can accept:

- `source`: accepted Java syntax version.
- `target`: class-file target version.
- `release`: controls both syntax/bytecode and the target release's public JDK API.

JDK 21 compiling with `-source 17 -target 17` can produce major version 61 while still seeing APIs present only in JDK 21. The class file may load, yet fail on a Java 17 runtime with `NoSuchMethodError` or `NoClassDefFoundError`.

`--release 17` restricts both bytecode target 17 and the API platform to Java 17. Therefore, when compiling with a newer JDK to support an older runtime, prefer `maven.compiler.release`.

### 7.3. Build and Verify

~~~bash
mvn -version
mvn -B -ntp clean verify
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

Look for `major version: 61` in the `javap` output. Then run the executable JAR with the baseline runtime:

~~~bash
java -version
java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --spring.main.web-application-type=none
~~~

If the application has a `CommandLineRunner` like in section 10, the output printed intentionally by code is `java-compatibility-demo:ready`. Spring startup logs may vary by environment.

### 7.4. Maven Toolchains: Compiler JDK Independent of Maven JVM

`maven.compiler.release=17` specifies the target/API, but does not force the Maven process to run on JDK 17. If the actual compiler must be JDK 17, use Maven Toolchains.

File `~/.m2/toolchains.xml` on the build machine:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

`jdkHome` is the actual JDK installation path; `/opt/jdks/temurin-17` is just a Linux example. Replace it with an appropriate Windows/macOS/CI path. Do not commit personal machine paths to the project.

In the POM, add the plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
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
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

The toolchains plugin selects a JDK matching the requirement from `toolchains.xml` and supplies the toolchain to supporting Maven plugins, such as Maven Compiler Plugin. The Maven process can still run on another JVM if the Maven/plugin versions allow it.

Verify:

~~~bash
mvn -version
mvn -B -ntp validate
mvn -B -ntp clean verify
~~~

`mvn -version` shows the JVM running Maven; build logs/toolchain selection show the selected compiler toolchain. **These two values can differ and still be correct by design.**

### 7.5. Enforcer Checking the JVM Running Maven

If the project requires the Maven process itself to run at least Java 17, Maven Enforcer can check Maven's JVM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>enforce-build-jdk</id>
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

The `requireJavaVersion` rule checks the JVM running Maven; it does not replace checking the compiler target and production runtime. If Maven runs Java 21 while the compiler uses toolchain 17, the rule still passes because Maven's JVM meets the minimum of 17.

## 8. Gradle: Toolchain and `options.release`

### 8.1. Groovy DSL

In `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

`toolchain` selects the JDK 17 compiler for toolchain-supporting Java tasks. `options.release=17` tells the compiler to restrict Java 17 APIs and produce target 17 bytecode.

### 8.2. Kotlin DSL

In `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

These are Gradle DSL fragments; real projects also need repositories, wrapper version, test dependencies, and other configuration. Use syntax matching the current DSL; do not mix the two styles.

### 8.3. Gradle Daemon JVM Differs from Compiler Toolchain

`./gradlew --version` reports the JVM running Gradle. `javaToolchains` lists JDKs detected by Gradle. The project toolchain selects the appropriate compiler/test launcher; the daemon JVM must be compatible with the Gradle version in use.

A Gradle release may require a minimum Java version to run Gradle itself. Targeting Java 17 in a project does not automatically allow running an overly old Gradle version on Java 21, or running a newer Gradle on an unsupported JVM. Cross-check the Gradle compatibility matrix and Spring Boot Gradle plugin compatibility.

### 8.4. Inspecting Gradle Output

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew clean build
javap -verbose build/classes/java/main/demo/CompatibilityDemoApplication.class
~~~

Expect class major 61 if the compile task used release 17. If output is still major 65, check whether `compileJava` had `options.release` overridden or another task/module generated the classes.

If the project has custom `JavaExec` tasks, integration test launchers, or tasks running other tools, inspect which JVM that task actually uses. Compiling major 61 while running integration tests on Java 21 does not prove the application works on Java 17.

## 9. Why Can a Build With the Right Compile Target Still Fail?

### 9.1. Dependency Compiled With a Newer Java

Application classes may be major 61 while a transitive library has major 65. When the JVM loads that library's class, the error still happens.

~~~bash
mvn dependency:tree -Dscope=runtime
jar tf target/application.jar
~~~

Locate the dependency named in the error stack, extract the exact version JAR, and inspect the class with `javap -verbose`. Upgrade the runtime to an appropriate version or pick a dependency version still supporting the current runtime. Do not downgrade libraries randomly; check API compatibility, security fixes, and the Spring Boot BOM.

### 9.2. Framework Has a Higher Baseline Than Runtime

A framework can raise its baseline between major/minor releases. Setting a lower application bytecode target does not lower the framework's runtime requirement.

For example, Spring Boot 3.5 requires at least Java 17. If an app uses Boot 3.5 on production Java 11, changing `maven.compiler.release=11` will not make Boot 3.5 run. Upgrade the runtime to 17+ or choose a framework version compatible with the runtime per support policy.

### 9.3. Using `source`/`target` Instead of `release`

`source=17` and `target=17` control language syntax and bytecode, but if the JDK 21 compiler still sees Java 21 APIs, source code can call newer APIs. A Java 17 runtime then fails linkage.

Prefer `--release 17` in Maven/Gradle. If a build tool/plugin does not support the release option, check compatibility and consider a real JDK 17 compiler/toolchain.

### 9.4. Annotation Processors and Generated Code

Lombok, MapStruct, QueryDSL, or custom annotation processors can run inside the compiler process and generate code. Processors also have their own JDK requirements; the plugin/compiler can fail before producing application classes.

Distinguish:

- The processor binary must run on the active JVM/compiler JDK.
- Generated Java source must be compiled for the project's target/release.
- A processor may generate bytecode or classes via its own mechanism; inspect the output.
- The compiler plugin, processor plugin, and Maven JVM may not share the same JDK if toolchains are not applied to all of them.

When an error occurs during the compile phase, read the first stack trace to see whether it is a processor/plugin or an application runtime class.

### 9.5. Kotlin, Scala, Groovy, and Mixed-Language Projects

`maven.compiler.release` only configures the Java compiler. Kotlin has `jvmTarget`/`jdkRelease`, Scala has its own bytecode target/toolchain, and the Groovy compiler also has its own bytecode target.

If Java compiles to major 61 while a Kotlin module outputs major 65, the executable JAR still contains Java 21 classes. Configure each compiler plugin and inspect class outputs of every source set/module.

### 9.6. Multi-Release JARs

A dependency can be a `Multi-Release JAR`: the same JAR contains base classes and version-specific implementations under `META-INF/versions/N`. The manifest has `Multi-Release: true` so the JVM picks the class version matching the runtime.

For instance, a JAR may have base classes supporting Java 11 and version-specific classes in `META-INF/versions/21` for Java 21. A Java 17 JVM does not necessarily load the Java 21 class in the version 21 folder; it chooses the highest compatible implementation not exceeding the runtime.

Therefore, do not write a script that scans every entry and fails merely upon seeing a high major class under `META-INF/versions/21`. Understand the manifest and multi-release rules. Conversely, a high major class in the base path of a non-multi-release dependency can genuinely cause errors.

### 9.7. Preview Features

Class files using preview features can carry `minor_version=65535`. At runtime, the JVM needs the exact matching Java release and the `--enable-preview` flag. Preview classes are not treated like normal bytecode simply because their major version falls within the supported range.

If the error message mentions preview features or minor version `65535`, check whether the compiler enabled `--enable-preview` and whether the runtime uses the exact matching release/flag.

## 10. Java 17 Spring Boot Application for Verification

Create `src/main/java/demo/CompatibilityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatibilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CompatibilityDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println(
                "java-compatibility-demo:ready");
    }
}
~~~

Using the POM in section 7, build:

~~~bash
mvn -B -ntp clean verify
~~~

Inspect class:

~~~bash
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

With `maven.compiler.release=17`, look for:

~~~text
major version: 61
~~~

Run executable JAR:

~~~bash
java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Exact stdout printed by `CommandLineRunner`:

~~~text
java-compatibility-demo:ready
~~~

Spring Boot logs may appear depending on logging config; the line above is application output. Because the example does not include a web starter, the process exits after the runner finishes.

### 10.1. Verifying Across Two Runtimes

If both JDK 17 and JDK 21 are available:

~~~bash
/path/to/jdk17/bin/java -jar target/java-compatibility-demo-1.0.0.jar
/path/to/jdk21/bin/java -jar target/java-compatibility-demo-1.0.0.jar
~~~

When classes/dependencies are Java 17 compatible and do not use APIs/features requiring a higher version, both runtimes can run it. Java 21 supports major 61 classes; Java 17 also supports major 61. Newer runtimes generally read older release bytecode, though you still need to test API behavior and dependencies.

## 11. Docker and Kubernetes: Where Mismatches Surface Late

### 11.1. Dockerfile Using JRE 17

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app
COPY target/java-compatibility-demo-1.0.0.jar /app/application.jar

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

The Docker image uses JRE 17; the JAR must be compiled for Java 17 or lower and all dependencies/frameworks must be Java 17 compatible.

Check runtime inside the image:

~~~bash
docker run --rm --entrypoint java compatibility-demo:1.0.0 -version
~~~

Check the application:

~~~bash
docker run --rm compatibility-demo:1.0.0 --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If the Java 21 host runs fine while the Java 17 container throws `UnsupportedClassVersionError`, compare the class major version with the runtime inside the image. Do not substitute the host's `java -version` for the container's version.

### 11.2. Different Build Stage and Runtime Stage

A multi-stage Dockerfile can build on JDK 21 and run on JRE 17. This is valid **if** the compiler uses `--release 17` and all dependencies are compatible.

~~~text
Build stage      : JDK 21 + Maven
Compiler         : --release 17
Artifact         : class major 61
Runtime stage    : JRE 17
Expected result  : compatible if dependencies also support Java 17
~~~

If the build stage does not set `release`, it may produce major 65 and copy it into a Java 17 runtime stage. The Docker build still succeeds because `COPY` does not check class-file compatibility; the error only surfaces when the container starts and the JVM loads the class.

### 11.3. Kubernetes Image Tag and Digest

In Kubernetes, a pod may run a different image than local testing. Check:

- Image reference in the Deployment/StatefulSet.
- Actual image digest pulled by the node.
- Base image/JRE version inside.
- Multi-arch manifest selected for the node architecture.
- Whether init containers, sidecars, and startup scripts invoke a different Java.

When using mutable tags, two nodes can pull different images depending on timing. For releases, pin the registry digest and record the JAR SHA/source revision. An error appearing on only one node can be an inconsistent image rollout.

## 12. CI: Locking Java Versions Across Build, Test, and Runtime

### 12.1. GitHub Actions with Java 17

~~~yaml
name: Java 17 compatibility

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show Java used by Maven
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify

      - name: Inspect compiled bytecode
        run: |
          javap -verbose target/classes/demo/CompatibilityDemoApplication.class |
            grep "major version"

      - name: Run packaged executable JAR
        run: |
          output="$(java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --spring.main.web-application-type=none)"
          test "$output" = "java-compatibility-demo:ready"
~~~

`setup-java` installs Java 17 for the job; `mvnw -version` shows the Maven JVM; `javap` verifies the major version; finally `java -jar` runs the exact packaged JAR in the same runtime.

If you want to build on JDK 21 while targeting Java 17, change `java-version` to 21 while keeping `maven.compiler.release=17`, then **add a smoke job/runtime step using Java 17**. Testing only on JDK 21 does not prove the artifact runs on Java 17.

### 12.2. Matrix Testing Multiple Runtimes

You can build one Java 17 artifact and test the exact same file on Java 17 and Java 21:

~~~yaml
strategy:
  matrix:
    java: ['17', '21']
~~~

In each matrix job, install the runtime per matrix, download **the exact same executable JAR** from the build job, and run the smoke test. Do not rebuild in each matrix job if the goal is to verify one binary runs on multiple JVMs; if each job compiles separately, you are testing different artifacts.

If only Java 17 is supported in production, the Java 21 matrix is an additional compatibility check, not a replacement for the required Java 17 gate.

### 12.3. Verifying Image Runtime

A container stage should:

1. Build the executable JAR with locked release/toolchain.
2. Record SHA-256 and pass along the exact verified JAR.
3. Build the Docker image from that JAR.
4. Verify the JAR inside the image matches the transferred bytes.
5. Run `java -version` inside the image.
6. Smoke-test the application inside the container.
7. Publish the image only after all gates pass.

A green build on a Java 21 runner paired with a Java 17 deploy image is a mismatch that must be caught before release.

## 13. Distinguishing UnsupportedClassVersionError from Related Errors

| Error | Common Meaning | What to Check |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM does not support class-file major/minor or preview mode | Class version, runtime, compiler target, preview flag |
| `NoSuchMethodError` | Class loaded, but runtime class lacks a method expected by bytecode | Dependency version conflict, API platform mismatch |
| `NoSuchFieldError` | Runtime class lacks a field referenced by compile-time class | Dependency mediation and binary compatibility |
| `NoClassDefFoundError` | Required class is missing or static initialization failed | Classpath/nested JAR, prior init exception |
| `ClassNotFoundException` | Code using class-loading API cannot find the class | Classpath, classloader, optional dependency |
| `IncompatibleClassChangeError` | Binary contract changed between compile/runtime | API shape, static/instance change, dependency conflict |
| `UnsupportedOperationException` | Operation not supported by the implementation | Runtime behavior/API contract; not bytecode version |

If the major version is lower than the runtime yet the application still fails, do not keep upgrading the JDK reflexively. The issue may be a dependency conflict or API mismatch.

## 14. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution Step |
| --- | --- | --- |
| Class major 65, runtime max 61 | Java 21 bytecode running on Java 17 | Compile with `--release 17` or upgrade runtime |
| App class major 61 yet still fails | Dependency/framework/plugin class is newer | Read class name in error, inspect dependency JAR |
| `java -version` is 17, Maven build fails | Maven JVM or plugin uses a different JDK | `mvn -version`, Toolchains, plugin requirements |
| Maven JVM 21, output major 65 | `maven.compiler.release` not applied | Effective POM, Compiler Plugin config/log |
| Maven JVM 21, compiler toolchain 17, app still fails | Incompatible dependency or generated code | Dependency tree and archive inspection |
| `javac -version` is 17, `java -version` is 11 | PATH contains multiple JDKs | Check executable paths and `JAVA_HOME` |
| Works locally, fails in Docker | Base image uses a lower JRE than host | `docker run --entrypoint java ... -version` |
| CI build green, production fails | CI test runtime newer than production | Run artifact on production baseline |
| Tests fail, app runs | Surefire/Failsafe JVM differs from compile/runtime | Check test toolchain and test runtime |
| Spring Boot plugin fails before compile | Maven JVM does not meet plugin/framework minimum | Check `mvn -version` and plugin requirements |
| Java 17 bytecode yet `NoSuchMethodError` | Compiled against newer JDK API via source/target | Use `--release 17` |
| One dependency class fails | A transitive JAR has newer bytecode | `dependencyInsight`/`dependency:tree` and `javap` |
| High class version in `META-INF/versions/21` | Multi-release JAR | Inspect manifest and runtime selection |
| Error mentions preview features/minor 65535 | Preview bytecode running on wrong release/missing flag | Match JDK release and `--enable-preview` |
| Gradle daemon will not run on current Java | Gradle version does not support daemon JVM | Compatibility matrix, wrapper upgrade |
| Gradle compiles with unexpected Java | Toolchain not configured or task overridden | `javaToolchains`, compile task config |
| One module has high major | Module uses separate compiler/target | Check child POM/`build.gradle` and inherited config |
| K8s pod fails on only one node | Different image digest/architecture/rollout | Inspect pod `imageID` and actual runtime |

## 15. Ordered Diagnostic Checklist

When encountering an error, follow this sequence:

1. **Record the exact error.** Capture the class name and major/minor versions.
2. **Identify the throwing process.** Maven/Gradle build, test JVM, local app, or container.
3. **Measure the actual JVMs.** `java -version`, `mvn -version`, `./gradlew --version`, Docker runtime.
4. **Inspect the class file.** Use `javap -verbose` or `ClassVersionProbe`.
5. **Trace the class source.** Project output, dependency tree, nested JAR, plugin, generated code.
6. **Check compiler config.** `maven.compiler.release`, Maven Toolchains, Gradle toolchain, and `options.release`.
7. **Check framework/dependency baselines.** Spring Boot, Spring Framework, Kotlin/Scala plugins, and transitive dependencies.
8. **Clean build and re-inspect.** Use `mvn clean`/`gradlew clean`; do not delete local dependency repositories arbitrarily.
9. **Run the exact artifact on the target runtime.** Do not substitute IDE classpath or `spring-boot:run`.
10. **Inspect the actual Docker/Kubernetes image.** Runtime JRE, image digest, platform, and startup command.
11. **Record evidence.** Commit, toolchain versions, class major, dependency tree, JAR hash, and image digest.

### 15.1. Quick Information Gathering Commands

Linux/macOS:

~~~bash
java -version
javac -version
mvn -version
./mvnw -version
./gradlew --version
mvn help:effective-pom
mvn dependency:tree -Dscope=runtime
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

Windows PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
mvn -version
.\mvnw.cmd -version
javap -verbose .\target\classes\demo\CompatibilityDemoApplication.class |
    Select-String "major version"
~~~

Run the commands appropriate for your actual build tool; Maven and Gradle do not both need to exist in every project.

## 16. Prevention Checklist in Projects

### Build Tool and Compiler

- [ ] Identify the minimum JDK needed to run Maven/Gradle and plugins.
- [ ] Declare the release target explicitly; Maven uses `maven.compiler.release`, Gradle uses toolchain + `options.release`.
- [ ] If a specific compiler JDK is needed, configure Maven/Gradle toolchains.
- [ ] Do not rely solely on PATH or IDE JDK settings.
- [ ] Align Java targets across Java, Kotlin, Scala, Groovy, and generated code.
- [ ] Check annotation processors and compiler plugins.

### Dependencies and Framework

- [ ] Choose a Spring Boot version compatible with the runtime baseline.
- [ ] Check transitive dependencies and their minimum Java requirements.
- [ ] Use BOM/dependency management to reduce version drift.
- [ ] Inspect the class named in the error stack instead of upgrading all dependencies.
- [ ] Evaluate multi-release JARs and preview features in proper context.

### Testing and Release Runtime

- [ ] Test the packaged JAR, not just the development classpath.
- [ ] Have a smoke test on the production JVM baseline.
- [ ] Container base image uses the right JRE/Java version.
- [ ] Record image digest and verify the runtime inside the image.
- [ ] CI build, test, package, and deploy use a consistent version policy.
- [ ] After changing dependencies/JDK/runtime, re-run compatibility tests.

## 17. Self-Check Questions

**A. Does class file major 65 mean Java 17?**

No. Major 65 corresponds to Java 21; Java 17 is major 61.

**B. Can Maven running on JDK 21 but compiling with `--release 17` produce classes that run on Java 17?**

Yes, if source/dependencies/framework are compatible and the compiler actually applies release 17. `--release` constrains both bytecode and the platform API.

**C. Is setting `source=17` and `target=17` equivalent to `--release 17`?**

No. `source`/`target` do not fully restrict the JDK APIs visible to the compiler; code may call newer APIs and fail on an older runtime.

**D. `mvn -version` reports Java 21. Does that prove the compiler uses JDK 21?**

No, not if Maven Toolchains or a compiler-specific toolchain is configured. `mvn -version` is the JVM running Maven; check toolchain selection and compiler logs.

**E. Application classes are major 61, yet the Spring Boot JAR still errors with major 65. What could be the cause?**

A nested dependency, Boot loader, generated class, or plugin-related class has major 65. Check the class name in the stack trace and inspect the corresponding dependency JAR.

**F. The host has Java 21, while the Docker image has JRE 17. Which runtime version decides?**

The JRE inside the image. Host Java does not replace the JVM running inside the container.

**G. Does a multi-release JAR containing a major 65 class definitely fail on Java 17?**

No. If the class is properly inside `META-INF/versions/21` in a JAR with `Multi-Release: true` in its manifest, JVM 17 can pick the base or a lower version. You must check its path and manifest.

**H. Why is testing on Java 17 still necessary even when using `--release 17`?**

The compiler target does not prove every dependency, framework, native library, runtime configuration, or container is compatible. Testing on the target runtime is an independent gate.

## 18. Official References

- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Oracle — UnsupportedClassVersionError API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedClassVersionError.html
- Java Virtual Machine Specification, Java SE 21 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se21/html/index.html
- Apache Maven Compiler Plugin — Setting the --release of the Java Compiler: https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html
- Apache Maven — Guide to Targeting a Java Version: https://maven.apache.org/guides/mini/guide-java-target.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Toolchains Plugin — Introduction and goals: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven Toolchains Plugin — Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Java compatibility matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Java 17 — javap tool reference: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Remember:** `UnsupportedClassVersionError` is a compatibility issue between **the class-file format and the actual JVM loading the class**. Identify the exact class and the exact process, then control the compiler with `--release`/toolchains, inspect dependencies, and test the packaged artifact on the production runtime. Aligning Java versions from the build tool through Docker/Kubernetes catches mismatches in CI rather than after deployment.