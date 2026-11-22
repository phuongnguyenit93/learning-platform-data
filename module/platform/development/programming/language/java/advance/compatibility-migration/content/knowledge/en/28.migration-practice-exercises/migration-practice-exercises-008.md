# Creating a Multi-Release JAR and Testing on Supported JDKs

## 1. Exercise Objectives

In **Java Advance Compatibility Migration**, a Java library may need to keep Java 8 as the minimum supported version while also wanting to use newer Java 17 APIs or optimize specifically for newer JDKs. If the entire library is compiled with Java 17, Java 8/11 users may encounter UnsupportedClassVersionError. If only the Java 8 implementation is kept, the library misses out on useful APIs on newer runtimes.

**Multi-release JAR (MR-JAR)** is a JAR format capable of holding multiple versions of a class or resource per **Java feature release**. Base classes reside at the root; variants are placed under META-INF/versions/N and the manifest has the attribute Multi-Release: true. Java 9+ runtimes have a mechanism to select the entry with the highest version not exceeding the runtime version, whereas Java 8 uses the root classes and does not perform versioned-entry selection.

This exercise will:

1. Create the public class org.example.mrjar.HexCodec with a stable API.
2. Write the **Java 8** base implementation using bit manipulation to encode bytes to hex.
3. Write the **Java 17** implementation with the same signature, using java.util.HexFormat.
4. Compile using javac --release 8 and --release 17 with separate output directories.
5. Package a single file hex-codec-mr.jar containing the manifest Multi-Release: true.
6. Verify JDK 8/11 use the base version and JDK 17/21 use the Java 17 version.
7. Compare class-file versions, validate the JAR, and run contract tests and a CI matrix.
8. Understand how to extend this in Gradle, module path, fat JARs, dependencies, and runtime deployment.

**Expected outcome**: a single JAR file runs successfully on Java 8, 11, 17, and 21, producing consistent encoding results while using the implementation suited to each runtime. The commands and outputs below are examples for the learner to execute; they are not logs run in the current workspace.

## 2. What Does MR-JAR Solve and What Does It Not Solve?

| Need | Is MR-JAR suitable? | Limitations |
|---|---|---|
| Keep old minimum Java, use new Java APIs when available | Yes | Root code and dependencies must still run on minimum Java. |
| Optimize implementation by JDK version | Yes | Must prove benefits and behavioral compatibility. |
| Maintain a single Maven/Gradle artifact | Yes | CI must test the same artifact across multiple JDKs. |
| Let Java 8 execute Java 17 class bytecode | No | Java 8 does not understand Java 17 class-file versions. |
| Automatically migrate from javax.* to jakarta.* | No | Binary API/framework/container compatibility requires separate handling. |
| Automatically select binaries by CPU, OS, libc | No | JNI/JNA/native agents require platform-specific packaging. |
| Automatically handle Java17-only dependencies on Java 8 | No | Runtime dependency graphs and class loading can still be incompatible. |
| Resolve data and event schema changes | No | Requires separate migration and compatibility contracts. |

MR-JAR is not a mechanism for the same public class to have completely different APIs per JDK. The safe design is **keeping the public/protected contract consistent and changing the internal implementation**. Packaging tools can check certain API constraints, yet consumer integration tests remain necessary.

### 2.1. When Should MR-JAR Not Be Used?

If an application only supports Java 21, maintaining multiple implementations can be unnecessary overhead. If a major new dependency no longer supports Java 8, or the public API requires fundamental changes, it may be more appropriate to raise the minimum Java version, release a major version, or split artifacts. MR-JAR is most useful when the part needing specialization is **small, stable, and has sufficient test coverage**.

## 3. Class Selection Mechanism by Runtime Version

An example MR-JAR:

~~~text
hex-codec-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 17/
│           └── org/example/mrjar/HexCodec.class
└── org/example/mrjar/
    ├── HexCodec.class
    └── Demo.class
~~~

Manifest:

~~~text
Manifest-Version: 1.0
Main-Class: org.example.mrjar.Demo
Multi-Release: true
~~~

For class HexCodec:

| Java runtime | Class selected by JVM |
|---|---|
| Java 8 | Root org/example/mrjar/HexCodec.class. |
| Java 11 | Root class, because there is no 9–11 variant. |
| Java 17 | META-INF/versions/17/org/example/mrjar/HexCodec.class. |
| Java 21 | versions/17 version, because there is no 18–21 variant. |

Selection is **per class/entry**. Demo exists only at the root, so Java 21 still uses root Demo. Another class with a versions/11 variant can be loaded from versions/11 in the same JAR.

### 3.1. The versions Directory Does Not Contain Application Versions

The name N is the Java feature release, not a library version, build update, or application semantic version:

~~~text
Valid in the Java release sense:
  META-INF/versions/9/
  META-INF/versions/11/
  META-INF/versions/17/
  META-INF/versions/21/

Do not use to select Java releases:
  META-INF/versions/java17/
  META-INF/versions/17.0.12/
  META-INF/versions/app-v2/
~~~

Java 17.0.x uses directory 17. If version 17 does not exist while 11 does, the runtime selects 11 for the corresponding class.

### 3.2. Class-File Versions Must Match

| Java | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

In this exercise, root classes must be major 52; the versions/17 variant has major 61 or lower appropriate for Java 17. Do not place major 65 classes into versions/17 because JDK 17 cannot load that bytecode.

### 3.3. The Manifest Determines MR Behavior

Merely having META-INF/versions/17 in the ZIP is not enough. The final manifest must include Multi-Release: true. A repackaging plugin may strip that attribute; therefore inspect the **final published artifact**, not just the source directory or an intermediate JAR.

## 4. Preparing the Environment and Directory Structure

Practice environment:

- **Build JDK:** JDK 21 with javac/jar supporting --release.
- **Target bytecode root:** Java 8.
- **Target bytecode variant:** Java 17.
- **Test runtimes:** JDK 8, 11, 17, 21.
- Terminal, filesystem, and file-creation permissions.
- No application server, framework, or external dependencies needed.

Structure:

~~~text
hex-codec-lab/
├── src/
│   ├── base/java/org/example/mrjar/
│   │   ├── HexCodec.java
│   │   └── Demo.java
│   └── versions/17/java/org/example/mrjar/
│       └── HexCodec.java
├── manifest.mf
├── build/classes/
│   ├── base/
│   └── java17/
└── dist/
    └── hex-codec-mr.jar
~~~

**Important:** the two HexCodec.java files share the same package/class name, yet have separate source roots and output directories. Compiling them in the same source set can cause the compiler to report duplicate classes or overwrite one with the other, breaking variant selection.

### 4.1. Verifying the Actual Toolchain

~~~bash
java -version
javac -version
jar --help
~~~

If the machine has multiple JDKs, prefer absolute paths or managed toolchains. Running java -version in one shell does not guarantee javac/jar or the production container JVM is the same installation.

## 5. Writing the Base Class for Java 8

File: src/base/java/org/example/mrjar/HexCodec.java

~~~java
package org.example.mrjar;

public final class HexCodec {

    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        if (bytes == null) {
            throw new IllegalArgumentException(
                    "bytes must not be null");
        }

        char[] output = new char[bytes.length * 2];

        for (int i = 0; i < bytes.length; i++) {
            int value = bytes[i] & 0xff;
            output[2 * i] = HEX[value >>> 4];
            output[2 * i + 1] = HEX[value & 0x0f];
        }

        return new String(output);
    }

    public static String implementation() {
        return "base-java8";
    }
}
~~~

### 5.1. Explanation

The class uses Java APIs available on Java 8. Java bytes are signed (-128..127), so bytes[i] & 0xff maps them to 0..255 when splitting the two nibbles. For byte FF, the hex result is ff, not a negative number representation.

The public API is kept fixed:

~~~java
public static String encode(byte[] bytes);
public static String implementation();
~~~

implementation() is only a diagnostic marker for the lab to verify class loading; it should not be treated as a security/feature negotiation mechanism in a real product.

### 5.2. Behavioral Contract

| Input | Expected result |
|---|---|
| new byte[0] | Empty string. |
| new byte[] {0} | "00". |
| new byte[] {0, 42, (byte) 255} | "002aff". |
| new byte[] {(byte) 128} | "80". |
| null | IllegalArgumentException. |

Every variant must preserve these semantics. Keeping the same public API signature while producing different output, different exceptions, or different encoding can still be a business regression.

## 6. Writing the Demo Class Runnable on Java 8

File: src/base/java/org/example/mrjar/Demo.java

~~~java
package org.example.mrjar;

public final class Demo {

    private Demo() {
    }

    public static void main(String[] args) {
        byte[] data = {0x00, 0x2a, (byte) 0xff};
        String result = HexCodec.encode(data);

        if (!"002aff".equals(result)) {
            throw new AssertionError(
                    "Unexpected encoding: " + result);
        }

        if (!"".equals(HexCodec.encode(new byte[0]))) {
            throw new AssertionError("Empty input mismatch");
        }

        try {
            HexCodec.encode(null);
            throw new AssertionError("Null input accepted");
        } catch (IllegalArgumentException expected) {
            // API contract is consistent across implementations.
        }

        String spec = System.getProperty(
                "java.specification.version");
        String selected = HexCodec.implementation();

        System.out.println("java.specification.version=" + spec);
        System.out.println("implementation=" + selected);
        System.out.println("result=" + result);
    }
}
~~~

Demo uses only Java 8-compatible APIs. When run on Java 17, HexCodec itself is re-selected from the variant by the runtime; Demo is still loaded from the root.

### 6.1. Why Is Testing Only Output Insufficient?

Both implementations can return the same "002aff". If the manifest is missing Multi-Release: true, JDK 17 may continue using the base version, and Demo still PASSES on output. We need **additional assertions checking the runtime marker** in testing to confirm that the MR-JAR mechanism truly operates.

## 7. Writing the Java 17-Specialized Implementation

File: src/versions/17/java/org/example/mrjar/HexCodec.java

~~~java
package org.example.mrjar;

import java.util.HexFormat;

public final class HexCodec {

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        if (bytes == null) {
            throw new IllegalArgumentException(
                    "bytes must not be null");
        }

        return HexFormat.of().formatHex(bytes);
    }

    public static String implementation() {
        return "java17";
    }
}
~~~

HexFormat has existed since Java 17, providing hex encoding without writing a manual loop. The default result from HexFormat.of().formatHex is lowercase hex, matching the base implementation in the example.

### 7.1. Why Not Call HexFormat Directly from the Root?

Java 8 does not have java.util.HexFormat. Root code referencing HexFormat will not compile with --release 8; even if placed inside a branch executed only on Java 17, the compiler must still resolve the type and method.

MR-JAR separates the two class files so older runtimes **do not have to load a class containing references to nonexistent APIs**.

### 7.2. The Public API Must Remain Stable

The Java 17 version still has the exact same two public static methods accepting and returning the exact same types. Do not change encode(byte[]) to encode(ByteBuffer), do not change the return type from String to byte[], and do not delete methods consumers already use.

For a real library, if you want to reduce duplication, you can keep a stable public facade at the root and version an internal implementation class. Under any model, verify binary compatibility and class loading.

## 8. Creating the Manifest

File manifest.mf:

~~~text
Manifest-Version: 1.0
Main-Class: org.example.mrjar.Demo
Multi-Release: true

~~~

The manifest must adhere to JAR manifest syntax, including the trailing blank line ending the main attributes section. In this example:

- Main-Class enables running via java -jar.
- Multi-Release: true enables MR-JAR resolution.
- Manifest-Version declares the manifest format version.

**Do not confuse** Multi-Release with the module-info filename or the Java release version. Simply creating a versions/17 directory does not make the JVM pick that class if the manifest/artifact is invalid.

## 9. Compiling Root Classes with javac --release 8

Assume using **JDK 21** javac from the project root:

~~~bash
mkdir -p build/classes/base build/classes/java17 dist

javac --release 8 \
  -d build/classes/base \
  src/base/java/org/example/mrjar/HexCodec.java \
  src/base/java/org/example/mrjar/Demo.java
~~~

Expected output:

~~~text
build/classes/base/org/example/mrjar/HexCodec.class
build/classes/base/org/example/mrjar/Demo.class
~~~

### 9.1. Why Use --release Instead of Only -source/-target?

--release 8 not only selects the bytecode/class-file target, it also restricts public Java platform APIs to those available in Java 8 via compiler support. Using only -source 8 -target 8 when building with a newer JDK can emit version 52 bytecode while accidentally referencing newer JDK APIs, causing linkage errors on Java 8.

Note: --release does **not** downgrade class-file versions of third-party libraries already compiled for Java 17/21. Inspect the runtime dependency graph separately.

### 9.2. Avoid Relying on Default javac

Do not run javac source.java without setting release and assume the classes will run on Java 8. A JDK 21 compiler by default may emit major version 65 classes. Verify with javap and runtime tests after packaging.

## 10. Compiling the Java 17 Variant Separately

~~~bash
javac --release 17 \
  -cp build/classes/base \
  -d build/classes/java17 \
  src/versions/17/java/org/example/mrjar/HexCodec.java
~~~

Output:

~~~text
build/classes/java17/org/example/mrjar/HexCodec.class
~~~

The version 17 class is emitted separately so the jar tool places it cleanly under META-INF/versions/17. Do not compile both src/base and src/versions/17 into the same classes directory.

### 10.1. Compile Classpath in Larger Projects

A variant may need to reference other classes from base or external dependencies. In that case, the compile classpath must include the exact dependencies used at the target Java release without letting root code accidentally link against newer APIs.

In this example, Java 17 HexCodec is standalone and uses only java.util.HexFormat, minimizing third-party library risk.

## 11. Packaging the MR-JAR

~~~bash
jar --create \
  --file dist/hex-codec-mr.jar \
  --manifest manifest.mf \
  -C build/classes/base . \
  --release 17 \
  -C build/classes/java17 .
~~~

| Command part | Meaning |
|---|---|
| --create | Creates a new JAR. |
| --file dist/hex-codec-mr.jar | Sets the artifact path. |
| --manifest manifest.mf | Uses the manifest declaring multi-release. |
| -C build/classes/base . | Places base classes into the JAR root. |
| --release 17 | Places subsequent entries into the versioned 17 region. |
| -C build/classes/java17 . | Places Java 17 HexCodec.class under META-INF/versions/17. |

This is the JDK jar tool syntax supporting MR-JAR. Do not manually rename a versions directory or rename class files to mimic --release; the bytecode contents must still be compiled properly.

### 11.1. Expected Entries

~~~text
META-INF/MANIFEST.MF
org/example/mrjar/HexCodec.class
org/example/mrjar/Demo.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Listing order may differ; what matters is the **exact path**. Specifically, there must be no build/classes/java17 prefix inside the JAR.

### 11.2. Why Not Zip Two Classes at the Same Path?

A ZIP/JAR has only one logical root path for a class. Putting two versions of HexCodec.class at the same org/example/mrjar/HexCodec.class causes one to overwrite the other or produces a duplicate entry. MR-JAR requires the newer class to reside at a separate versioned path.

## 12. Inspecting JAR Structure and Manifest

List contents:

~~~bash
jar --list --file dist/hex-codec-mr.jar
~~~

Look for both entries:

~~~text
org/example/mrjar/HexCodec.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Read the manifest from the final JAR using a ZIP tool or extract into a separate inspection folder. You must see:

~~~text
Multi-Release: true
Main-Class: org.example.mrjar.Demo
~~~

**Do not inspect only manifest.mf on the filesystem:** Maven/Gradle plugins, shading, or repackaging can overwrite the manifest after an intermediate build step.

### 12.1. jar --validate

~~~bash
jar --validate --file dist/hex-codec-mr.jar
~~~

On a supporting JDK, the tool validates the structure and several constraints on versioned entries/APIs of the multi-release JAR. CI must check the exit code; do not treat error messages as warnings and proceed to publish.

**Limitation:** jar --validate does not replace unit tests, consumer compatibility tests, runtime class selection assertions, or benchmarks. It does not execute code or catch business semantics errors.

### 12.2. Checking Bytecode with javap

~~~bash
javap -verbose \
  -classpath build/classes/base \
  org.example.mrjar.HexCodec

javap -verbose \
  -classpath build/classes/java17 \
  org.example.mrjar.HexCodec
~~~

In the output, the root class is expected to have major version **52**, and the variant is expected to have major version **61**. On supporting JDKs, you can inspect versioned contents with:

~~~bash
javap --multi-release 17 \
  -classpath dist/hex-codec-mr.jar \
  org.example.mrjar.HexCodec
~~~

Tool results should be cross-checked against the artifact layout, though runtime tests in the next step remain the strongest evidence of which class the JVM actually loads.

## 13. Running the Same Artifact Across JDKs

Assume four installations configured in variables JDK8_HOME, JDK11_HOME, JDK17_HOME, JDK21_HOME on a Unix-like shell:

~~~bash
"$JDK8_HOME/bin/java"  -jar dist/hex-codec-mr.jar
"$JDK11_HOME/bin/java" -jar dist/hex-codec-mr.jar
"$JDK17_HOME/bin/java" -jar dist/hex-codec-mr.jar
"$JDK21_HOME/bin/java" -jar dist/hex-codec-mr.jar
~~~

On Windows, use the java.exe path suitable for PowerShell/cmd; do not blindly copy Unix shell variable syntax.

Expected results:

~~~text
JDK 8:
  java.specification.version=1.8
  implementation=base-java8
  result=002aff

JDK 11:
  java.specification.version=11
  implementation=base-java8
  result=002aff

JDK 17:
  java.specification.version=17
  implementation=java17
  result=002aff

JDK 21:
  java.specification.version=21
  implementation=java17
  result=002aff
~~~

This is **sample output**, not measured results. If JDK 17 prints base-java8 while result is still correct, functionality passes yet **multi-release selection has failed**.

### 13.1. Do Not Build Four Separate JARs

The lab's goal is build once/test many:

~~~text
Build JDK 21
    │
    ▼
hex-codec-mr.jar (single checksum)
    │
    ├── JDK 8
    ├── JDK 11
    ├── JDK 17
    └── JDK 21
    │
    ▼
Contract tests + class-selection tests
~~~

If each runtime gets its own JAR, you have not proven multi-release behavior of the single artifact. In CI, distribute the file via an artifact store and verify its checksum across jobs.

### 13.2. java -cp Must Also Be Tested

MR-JARs are commonly used as libraries rather than executable applications:

~~~bash
"$JDK17_HOME/bin/java" \
  -cp dist/hex-codec-mr.jar \
  org.example.mrjar.Demo
~~~

When loaded by the standard class loader from the final JAR, the versions/17 variant is selected. However, if the classpath puts loose build/classes/base ahead of the JAR, HexCodec may be loaded from that directory instead of the MR-JAR.

Do not test an MR-JAR with a classpath containing loose source output directories that shadow it when the goal is validating the final artifact.

## 14. Adding an Assertion for Runtime Selection

The initial Demo checked the encode result, yet we must also verify implementation() matches the JDK. Add the following snippet inside main:

~~~java
String version = System.getProperty(
        "java.specification.version");

int feature;
if (version.startsWith("1.")) {
    feature = Integer.parseInt(version.substring(2));
} else {
    feature = Integer.parseInt(version);
}

String expected = feature >= 17
        ? "java17"
        : "base-java8";

String actual = HexCodec.implementation();

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected variant " + expected
                    + ", got " + actual);
}
~~~

This fragment belongs **inside Demo.main**, not as a standalone Java file. It handles java.specification.version = 1.8 on JDK 8 as well as values 11/17/21.

When repackaged and run:

- Java 8/11 selects base; selection assertion PASSES.
- Java 17/21 selects Java 17; selection assertion PASSES.
- If the manifest loses Multi-Release: true, JDK 17/21 uses root, and the test FAILS.
- If the versioned class is at the wrong path, JDK 17/21 uses root, and the test FAILS.

In a real library, the marker can live in an internal test fixture or consumer smoke test; a public method solely for checking the implementation is not strictly necessary.

## 15. Functional Contract Tests Across All JDKs

Do not only check the implementation marker. Every variant must uphold the contract:

| Test | Input | Expected |
|---|---|---|
| H-01 | empty byte array | Empty string. |
| H-02 | 00 | "00". |
| H-03 | 0F | "0f". |
| H-04 | 10 | "10". |
| H-05 | 7F | "7f". |
| H-06 | 80 | "80". |
| H-07 | FF | "ff". |
| H-08 | 00 2A FF | "002aff". |
| H-09 | null | IllegalArgumentException. |
| H-10 | bytes generated with fixed seed | Hex output consistent with oracle. |

### 15.1. JUnit Jupiter Example

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.example.mrjar.HexCodec;

final class HexCodecContractTest {

    @Test
    void encodesBoundaryValues() {
        byte[] bytes = {0x00, 0x2a, (byte) 0xff};
        assertEquals("002aff", HexCodec.encode(bytes));
    }

    @Test
    void acceptsEmptyArray() {
        assertEquals("", HexCodec.encode(new byte[0]));
    }

    @Test
    void rejectsNullArray() {
        assertThrows(IllegalArgumentException.class,
                () -> HexCodec.encode(null));
    }
}
~~~

This test requires matching JUnit Jupiter dependencies. When running on Java 8, choose JUnit/runtime dependencies that support Java 8; do not use a test framework version requiring Java 17 and mistakenly conclude the Java 8 library is incompatible.

### 15.2. Gradle Tests May Not Load the Final JAR

Gradle's default Java Test task typically uses source set outputs—the classes directories—rather than the packaged JAR. It may load only the base HexCodec and fail to test MR selection.

Therefore separate:

1. **Source-level tests:** logic of base and variants, running on matching compiler/runtime.
2. **Artifact-level smoke tests:** load the **final packaged JAR** on JDK 8/11/17/21 and assert both the implementation marker and behavior.

If you do only group 1, multi-release packaging can break while CI stays green.

## 16. Gradle Build Model for MR-JAR

In a Gradle project, base and Java 17 variant are typically split into two compilation tasks. This example uses Gradle **Kotlin DSL** and a JDK 21 toolchain. Corresponding layout:

~~~text
src/main/java/org/example/mrjar/HexCodec.java
src/main/java/org/example/mrjar/Demo.java
src/java17/java/org/example/mrjar/HexCodec.java
~~~

Only the source root paths changed from earlier sections; the Java contents remain identical.

### 16.1. Illustrative build.gradle.kts

~~~kotlin
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.tasks.Jar

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.named<JavaCompile>("compileJava") {
    options.release.set(8)
}

val compileJava17 by tasks.registering(JavaCompile::class) {
    source = fileTree("src/java17/java") {
        include("**/*.java")
    }

    destinationDirectory.set(
        layout.buildDirectory.dir("classes/java/java17")
    )
    javaCompiler.set(javaToolchains.compilerFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    options.release.set(17)

    classpath = files(
        sourceSets.main.get().output,
        configurations.compileClasspath
    )
    dependsOn(tasks.named("classes"))
}

tasks.named<Jar>("jar") {
    dependsOn(compileJava17)

    manifest {
        attributes(
            "Main-Class" to "org.example.mrjar.Demo",
            "Multi-Release" to "true"
        )
    }

    into("META-INF/versions/17") {
        from(compileJava17.flatMap { it.destinationDirectory })
    }

    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

This is a **reference template** that must be adapted to your actual Gradle/plugin versions and source sets. Larger projects can define a dedicated source set for Java 17, declare dependency buckets, and control compile order in more detail.

### 16.2. Explaining the Gradle Tasks

- compileJava compiles main classes with --release 8.
- compileJava17 takes only src/java17/java with --release 17, without overwriting main output.
- compileJava17 depends on base output.
- The jar task packages main output at the root.
- The jar task places Java 17 output under META-INF/versions/17.
- The JAR manifest declares Multi-Release: true.

Building with JDK 21 does **not** make root bytecode Java 21 if compileJava sets options.release=8. However, third-party runtime dependencies still require verification.

### 16.3. Commands Used in the Test Project

~~~bash
./gradlew clean jar
jar --list --file build/libs/hex-codec-lab.jar
jar --validate --file build/libs/hex-codec-lab.jar
~~~

The actual filename depends on project name, version, and Gradle archive settings. These commands are **examples**, not executed during the writing of this lesson.

### 16.4. Do Not Validate Only the Intermediate JAR

If the project also uses Shadow plugin, Maven Shade, bootJar, or framework repackaging, the final artifact may differ from the build/libs JAR created by the Java plugin. Always check the manifest/entries and run runtime smoke tests on the artifact **to be published/deployed**, not merely an intermediate build JAR.

## 17. Gradle Test Runtime and JDK Matrix

One way to select a JDK for Test tasks:

~~~kotlin
val testJdk = providers.gradleProperty("testJdk")
    .orElse("17")
    .map(String::toInt)

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(
            JavaLanguageVersion.of(testJdk.get())
        )
    })
}
~~~

In CI, you can run:

~~~bash
./gradlew test -PtestJdk=8
./gradlew test -PtestJdk=11
./gradlew test -PtestJdk=17
./gradlew test -PtestJdk=21
~~~

However, distinguish **Gradle tests running against classes** from **smoke tests running against the final MR-JAR**. Choosing a Java launcher for the Test task does not automatically point the classpath at the versioned JAR; a dedicated artifact-level job as in sections 13–14 is needed.

If running multiple Gradle jobs in parallel, manage build directories/caches and toolchains to avoid races or mixed outputs.

## 18. Designing a Build-Once, Test-Many CI Pipeline

An illustrative matrix:

| CI job | JDK | Mandatory checks |
|---|---|---|
| package | Build JDK 21 | Root --release 8, variant --release 17, jar validation. |
| smoke-java8 | Java 8 | base-java8, accurate behavior, exit 0. |
| smoke-java11 | Java 11 | base-java8, accurate behavior, exit 0. |
| smoke-java17 | Java 17 | java17, accurate behavior, exit 0. |
| smoke-java21 | Java 21 | java17, accurate behavior, exit 0. |
| consumer-library | Published JDKs | Public API usable from another app. |
| packaging-integration | Relevant JDKs/frameworks | Nested/fat JAR preserves MR resolution. |

A CI provider might use the concept:

~~~yaml
strategy:
  matrix:
    java: ['8', '11', '17', '21']
~~~

This is an **illustrative snippet**, not a complete GitHub Actions workflow. A real workflow needs checkout, Java setup, artifact upload/download, permissions, and checksum verification.

### 18.1. Shell Pseudo-CI

~~~bash
set -eu

JAR=dist/hex-codec-mr.jar

jar --validate --file "$JAR"

"$JDK8_HOME/bin/java"  -jar "$JAR"
"$JDK11_HOME/bin/java" -jar "$JAR"
"$JDK17_HOME/bin/java" -jar "$JAR"
"$JDK21_HOME/bin/java" -jar "$JAR"
~~~

Once Demo has the version-selection assertion added, any JDK loading the wrong class will produce a non-zero exit code.

**Quality gate rule:** a missing mandatory runtime test or missing artifact metadata must not automatically be treated as PASS. If the CI environment lacks JDK 8, mark Java 8 as lacking evidence rather than claiming support because Java 21 runs fine.

### 18.2. Same Checksum for One Artifact

If CI rebuilds the JAR separately inside each matrix job, it could accidentally produce:

~~~text
JDK 8  → root-only artifact
JDK 11 → root-only artifact
JDK 17 → Java17-only artifact
JDK 21 → Java17-only artifact
~~~

All four artifacts might run, yet they do not prove MR-JAR behavior. Build one artifact, store its checksum (e.g., SHA-256 per policy), and feed that exact artifact into all runtime jobs.

## 19. Binary API Compatibility and Consumer Tests

For versioned classes, the Java compiler/JVM must see compatible public/protected contracts.

### 19.1. Comparing Signatures with javap

~~~bash
javap -public \
  -classpath build/classes/base \
  org.example.mrjar.HexCodec

javap -public \
  -classpath build/classes/java17 \
  org.example.mrjar.HexCodec
~~~

Expected public methods:

~~~text
public static java.lang.String encode(byte[]);
public static java.lang.String implementation();
~~~

A binary API diff tool can additionally check superclasses, interfaces, fields, annotations, and other public/protected changes. Yet API equality still does not prove output semantics are correct.

### 19.2. Consumer Already Compiled on Java 8

A valuable scenario:

1. Compile the consumer separately with --release 8 against the root's public API.
2. Package the consumer with the built MR-JAR dependency.
3. Run the consumer on JDK 8/11/17/21.
4. Verify no NoSuchMethodError, IllegalAccessError, or LinkageError occurs.
5. Verify output and exception semantics.

If the Java 17 version removed a method the binary consumer still calls, the failure may appear only on JDK 17/21 while Java 8/11 tests PASS.

### 19.3. API Break Example

Root:

~~~java
public static String encode(byte[] bytes);
~~~

Broken variant:

~~~java
public static byte[] encode(byte[] bytes);
~~~

That changes the JVM method descriptor, not merely an implementation optimization. Do not abuse MR-JAR to ship diverging APIs per JDK when consumer contracts require stability.

## 20. Module Path and JPMS

Java 9 introduced the module system. An MR-JAR can run on the classpath and integrate with the module path in various ways, yet public packages, module descriptors, exports/opens, and service resolution require separate inspection.

### 20.1. Classpath PASS Does Not Guarantee Module Path PASS

On the module path you may encounter:

- Unstable module names.
- Split packages across multiple modules.
- Reflection without opens.
- Undeclared service providers.
- Dependencies missing requires or failing resolution.

If the library is advertised as supporting the module path, test a real modular consumer on all supported JDKs.

### 20.2. module-info.class in MR-JAR

Some projects keep a Java 8 base while providing a module descriptor for Java 9+ via versioned entries, for example conceptually:

~~~text
root Java 8 classes
META-INF/versions/9/module-info.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

The descriptor must be compiled for the corresponding Java release and satisfy module/JAR constraints. Do not put a Java 17 module-info.class under versions/9 and expect JDK 9 to read it.

For this lab, module-info.class is not yet needed; get the classpath MR-JAR right before expanding into modular packaging.

## 21. ServiceLoader and Custom Classloaders

If the library uses ServiceLoader or a plugin architecture, test runtime discovery.

Example service descriptor:

~~~text
META-INF/services/org.example.api.CodecProvider
~~~

A provider class existing only in versions/17 may be unavailable on Java 8. It is better to keep the service provider contract compatible with minimum Java and version the implementation in a controlled manner.

### 21.1. Custom Class Loaders

A plugin loader that reads raw ZIP entries itself may pick the root class instead of applying MR-JAR semantics. Do not assume every launcher, application server, nested JAR loader, or bytecode transformer handles versioned entries like the standard JVM class loader.

For frameworks using custom classloading:

1. Check the supported framework version.
2. Package the MR-JAR just like production.
3. Load the class via the framework's actual loader.
4. Assert the variant marker and behavior.
5. Test ServiceLoader/reflection if applicable.

### 21.2. Raw ZIP Differs from Runtime Resolution

When opening a JAR as a plain ZIP, tools may see both:

~~~text
org/example/mrjar/HexCodec.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

The Java runtime picks one variant by feature version. Static scanners may need to inspect **all variants**, not just the root entry; conversely, bytecode-rewriting tools must preserve proper layout and signatures after processing.

## 22. Resources and Versioned Entries

In MR-JAR-aware environments, resource lookup can be affected by versioned entries; however, raw ZIP tooling and custom classloaders may behave differently.

Conceptual example:

~~~text
config/default.properties
META-INF/versions/17/config/default.properties
~~~

If you want to version resources, test specifically with ClassLoader.getResource/getResourceAsStream or whichever API the app uses. Verify whether the framework's loader actually applies runtime-version semantics.

For this first exercise, override only HexCodec.class to keep the model simple. Do not store secrets inside a JAR or versioned resource: entries can still be extracted as a ZIP and are not encrypted by MR-JAR.

## 23. Fat JARs, Shading, and Nested Libraries

Packaging plugins such as Shadow/Maven Shade or executable JAR packagers can break an MR-JAR if configuration/version lacks support:

- Multi-Release: true manifest attribute is dropped.
- META-INF/versions/N is stripped from the archive.
- Versioned classes are moved into the root.
- Class name relocation applies only to base, not to versions.
- Duplicate files are merged improperly.
- Nested JAR classloaders ignore MR resolution.

### 23.1. Two Testing Loops

~~~text
Base library hex-codec-mr.jar
       │
       ├── jar validation
       └── direct runtime matrix
              │
              ▼
Consumer application packaging
       │
       ├── fat/shaded/boot JAR
       └── framework classloader
              │
              ▼
Consumer integration matrix
~~~

Do not conclude a Spring Boot/OSGi/application-server deployment will pick the right Java17 variant just because the library's direct classpath test PASSES. Test the actual deployed artifact.

### 23.2. JAR Signing

If the JAR is signed, modifying the manifest or class files after signing invalidates signatures. Design the pipeline compile → assemble → validate → sign/publish and verify the signed artifact per policy.

## 24. Dependency Graph and Minimum Java

MR-JAR selects classes only by JDK version; it does not resolve all dependency issues automatically. Specifically:

- A Java 17-only dependency declared as a mandatory runtime dependency can crash JDK 8 if loaded.
- A new class may be eager-loaded by a framework scanner on an old runtime.
- Third-party bytecode is not automatically downgraded to Java8-compatible by javac --release 8.
- Reflection, ServiceLoader, and native libraries can fail lazily when a feature is invoked.

Therefore verify:

1. Resolved runtimeClasspath or Maven dependency tree.
2. Minimum Java versions of direct/transitive dependencies.
3. Class-file versions inside dependency JARs.
4. Native libraries/agents and OS ABI if present.
5. Consumer integration running on minimum Java.

Sometimes it is better to split a specialized dependency into a separate artifact rather than hiding it in an MR-JAR. If the whole product has already moved to Java 17, raising the minimum version can be simpler than maintaining multiple compatibility variants.

## 25. Extension: Adding a Java 21 Variant

To extend the lab, add another source root:

~~~text
src/versions/21/java/org/example/mrjar/HexCodec.java
~~~

This class must have the **exact same public signatures**. It can use APIs introduced in Java 21 in its implementation—such as SequencedCollection.getFirst()—while still preserving encode output and error contracts.

Compile:

~~~bash
mkdir -p build/classes/java21

javac --release 21 \
  -d build/classes/java21 \
  src/versions/21/java/org/example/mrjar/HexCodec.java
~~~

Package once the source/compiled variant exists:

~~~bash
jar --create \
  --file dist/hex-codec-mr.jar \
  --manifest manifest.mf \
  -C build/classes/base . \
  --release 17 \
  -C build/classes/java17 . \
  --release 21 \
  -C build/classes/java21 .
~~~

Runtime selection then changes to:

| Runtime | Expected implementation |
|---|---|
| Java 8/11 | base-java8 |
| Java 17 | java17 |
| Java 21 | java21, if the Java21 version returns that marker |

Do not just add an empty versions/21 directory and expect the JVM to conjure specialization. Complete compiling/packaging/testing, and update Gradle tasks and CI assertions.

### 25.1. Self-Extension Exercise

Try creating a Java 21 version using a new API while still encoding "002aff" accurately for the sample byte array. Before accepting the new variant, run:

- jar --validate.
- Public API signature comparison.
- JDK8/JDK11/JDK17/JDK21 smoke tests.
- Contract tests for empty bytes, FF, null, and large inputs.
- Consumer integration on real packaging.

## 26. Benchmarks and Performance Across Variants

Do not assume Java 17 HexFormat is faster than the Java 8 loop in every scenario. Benchmarks must control for JIT, warmup, workload, hardware, memory, and JDK updates.

To compare **algorithms**:

- Run both implementations on the **same JDK 17** if possible.
- Use the same dataset, input distribution, and collector/flags.
- Use JMH or an appropriate benchmark harness with warmup/measurement/forks.
- Measure throughput, ns/op, and allocation where relevant.

When comparing a Java 8 runtime with a Java 17 runtime, differences also reflect JIT/GC/runtime implementations, so they cannot all be attributed to the HexFormat API.

### 26.1. Behavior First, Benchmarks Second

Benchmark only after confirming equivalent outputs across all test cases. A faster implementation that skips validation, uses the wrong encoding, or drops data is not a shippable improvement.

### 26.2. Large Data and Memory Usage

In the base implementation, new char[bytes.length * 2] can overflow/run out of memory on oversized inputs. The Java 17 implementation using HexFormat also requires memory for output. In a real product, define a max input policy or appropriate streaming interface; if adding validation, apply it **identically in both root and versioned classes**.

## 27. Common Errors and Troubleshooting Table

| Symptom | Possible cause | How to verify |
|---|---|---|
| JDK 8 hits UnsupportedClassVersionError | Root or dependency compiled above Java8. | javap major version, --release 8, runtime dependencies. |
| JDK 17 still prints base-java8 | Manifest missing Multi-Release, wrong path, classpath shadowing. | Inspect manifest/artifact, marker, classpath. |
| JDK 11 loads Java 17 class | Java17 class placed at root or broken custom loader. | Inspect JAR layout/bytecode. |
| javac does not recognize HexFormat | Variant compiled with JDK <17 or --release 8. | javac -version, options.release. |
| jar --validate reports API mismatch | Variant changed public/protected signatures or invalid layout. | javap -public, fix contract. |
| Duplicate class during compilation | Both HexCodec.java files in the same source set. | Separate source roots/outputs. |
| Unit tests PASS, final JAR fails | Tests ran against loose classes, final package wrong. | Artifact-level smoke tests. |
| NoSuchMethodError on one JDK | Binary API variant/dependency mismatch. | Consumer binary tests, dependency analysis. |
| ServiceLoader fails only on Java8 | Provider/config exists only in Java17. | Java8 integration test. |
| Fat JAR loads wrong version | Shading/nested classloader drops MR semantics. | Verify final artifact/framework runtime. |
| Agent/native fails on Linux arm64 | MR-JAR does not select OS/CPU ABI. | Native artifacts and environment matrix. |
| Results differ between CI runners | Different toolchains/flags/caches/dependencies. | Pin versions, artifact digest, and baseline. |

### 27.1. A Quick Investigation Workflow

When Java 17 does not use the variant:

1. Check the exact Java executable/version.
2. Check the final JAR path and checksum.
3. Read MANIFEST.MF inside the final JAR.
4. Check the exact META-INF/versions/17 path.
5. Check the variant's major version <= Java17 limit.
6. Check whether the classpath has loose base classes or duplicate JARs.
7. Inspect custom classloaders/nested packaging.
8. Run selection assertions and capture exit codes/logs.

Do not rewrite encoding logic when the actual issue is merely the manifest or JAR layout.

## 28. Misconceptions to Avoid

**"MR-JAR runs on every Java version."** No. Root and dependencies must support minimum Java, and runtimes outside the support matrix have no evidence.

**"Having a versions directory is enough."** No. The manifest and versioned layout must both be valid.

**"Java 21 automatically runs Java17 code inside Java8."** No. The Java8 runtime only has the APIs/bytecode it supports.

**"Compiling with JDK21 means output classes are Java21."** It depends on options.release/--release. Check bytecode and runtime loading.

**"jar --validate is sufficient."** No. That is only tool-scoped structural/API validation; functional/integration tests remain mandatory.

**"Gradle Test tasks automatically test MR-JAR."** Not necessarily, as the test classpath may point to classes directories.

**"MR-JAR replaces Maven/Gradle dependency constraints."** No. Minimum Java dependencies and runtime linkage still require checking.

**"MR-JAR is a security or code-hiding mechanism."** No. Entries can still be read from the ZIP.

**"MR-JAR selects native libraries by OS/CPU."** No. Versioned directories are keyed solely by Java release.

**"When optimizing the Java17 variant, public signatures can be changed freely."** No. Consumers need a stable API contract; if breaking changes are required, consider a major release/separate artifact.

## 29. Exercise Acceptance Checklist

### 29.1. Compilation and JAR Format

- [ ] Root HexCodec/Demo compiled with --release 8.
- [ ] Java17 HexCodec compiled with --release 17.
- [ ] Root and Java17 outputs do not overwrite each other.
- [ ] Final manifest contains Multi-Release: true and exact Main-Class.
- [ ] JAR contains root HexCodec.class and versions/17 HexCodec.class.
- [ ] jar --validate PASSES.
- [ ] Class-file major versions match 52 and 61.

### 29.2. Runtime

- [ ] JDK8: implementation=base-java8, result=002aff.
- [ ] JDK11: implementation=base-java8, result=002aff.
- [ ] JDK17: implementation=java17, result=002aff.
- [ ] JDK21: implementation=java17, result=002aff.
- [ ] Selection assertion executed on the final artifact.
- [ ] Null, empty, FF, and boundary inputs tested.
- [ ] Loose classes not accidentally loaded when testing the packaged JAR.
- [ ] A single artifact checksum used across the entire runtime matrix.

### 29.3. Release/Integration

- [ ] Base/variant public signatures are compatible.
- [ ] Java8-compiled consumer code runs across the JDK matrix.
- [ ] Runtime dependency graph supports minimum Java.
- [ ] Module path/ServiceLoader/custom loaders tested if used by the product.
- [ ] Final shaded/fat/nested JAR preserves MR semantics.
- [ ] JDK compiler/Gradle plugins and artifact provenance recorded.
- [ ] Release notes document actual support matrix and limitations.

This checklist is for **self-verification by the learner**. Do not check off steps as completed just from reading the guide or viewing hypothetical output.

## 30. Result Report Template

~~~text
Module: Java Advance Compatibility Migration
Lesson: Creating a Multi-Release JAR and Testing on Supported JDKs

Artifact:
  jar path:
  jar checksum:
  manifest Multi-Release:
  root class major:
  versioned class major:
  jar --validate exit code:

Build:
  JDK vendor/build:
  javac --release base:
  javac --release variant:
  build tool/plugin versions:

Runtime:
  Java 8: selected class / output / exit status
  Java 11: selected class / output / exit status
  Java 17: selected class / output / exit status
  Java 21: selected class / output / exit status

Contracts:
  encode empty:
  encode 002aff fixture:
  encode null:
  public API diff:

Integration:
  classpath:
  module path if applicable:
  shaded/boot JAR if applicable:
  minimum-JDK dependency check:

Decision:
  PASS / FAIL / INCONCLUSIVE:
  blockers:
  owner:
  evidence reference:
~~~

Do not fill in fake PASS results. Every value should come from executed commands, test reports, artifact metadata, and verified runtimes.

## 31. Workflow for Applying MR-JAR in a Real Migration Project

**Step 1 — Determine minimum Java and target matrix.** Do not silently raise minimum Java while the library still commits to supporting older JDKs.

**Step 2 — Choose implementations with clear benefits.** Prefer a small internal API or utility; avoid duplicating entire framework modules.

**Step 3 — Write contract tests.** Public API, input/output, exception behavior, serialization, and concurrency if applicable.

**Step 4 — Separate source roots.** Keep root code/variant code and compiled outputs distinct.

**Step 5 — Compile with --release.** Use a sufficiently recent toolchain while enforcing minimum-Java restrictions.

**Step 6 — Package the proper MR layout.** Manifest Multi-Release: true, META-INF/versions/N at the exact path.

**Step 7 — Validate the artifact.** jar --list, jar --validate, class-file versions, public API diff.

**Step 8 — Runtime matrix.** Run **one artifact** across all supported JDKs; assert both version selection and behavior.

**Step 9 — Test consumer packaging.** Test shaded/fat JARs, framework loaders, and classpath/module path if applicable.

**Step 10 — Release and monitor.** Version build metadata/checksums, document the support contract, and keep an artifact rollback plan if new packaging fails.

## 32. Conclusion

**Multi-release JARs allow a single Java artifact to hold a base implementation alongside variants per JDK release.** With root classes compiled for Java 8, the Java 17 implementation in META-INF/versions/17, and Multi-Release: true in the manifest, a library can support JDK 8/11 while leveraging java.util.HexFormat on JDK 17/21 without requiring Java 8 to understand newer bytecode.

The key takeaway of this exercise is not merely producing a JAR file. You must **compile with the right --release, validate manifest/class versions, run the exact same artifact across Java 8/11/17/21, verify class selection and API contracts**, and then repeat with the real packaging of consuming applications.

In Java Advance Compatibility Migration, MR-JAR is a valuable tool when maintaining an older minimum Java while specializing select implementations. It does not handle dependency compatibility, native ABI, modules, data, or security on its own. Only with a support matrix, regression tests, and CI gates grounded in **actually published runtimes** does a team have reliable footing to ship multi-release JARs across both old and new JDKs.
