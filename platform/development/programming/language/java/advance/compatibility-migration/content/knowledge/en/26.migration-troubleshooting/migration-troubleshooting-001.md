# UnsupportedClassVersionError and per-dependency bytecode levels

When upgrading or switching Java environments, one of the most confusing errors is **`java.lang.UnsupportedClassVersionError`**. An application may compile successfully on a development machine, yet fail to start in production; or the main application already uses `--release 17`, while a transitive dependency contains classes generated for Java 21. In some cases, a service runs for hours before failing when a plugin, JDBC driver, serializer, or rarely used class is loaded. In other cases, the message “Unsupported class file major version 65” comes from ASM/Gradle rather than the JVM.

The key point of diagnosis is that **the bytecode level is a property of each `.class` file, not a single property of the entire project**. A classpath can contain thousands of classes from multiple JARs with different class-file major versions. The runtime JVM must support the specific class it is loading; a compiler, bytecode transformer, or build plugin must also understand the class format it parses.

This lesson in the **Troubleshooting** chapter of *Java Advance Compatibility Migration* presents the meaning of the error, how to read major/minor versions, how to locate the exact class and artifact causing the error — including transitive dependencies, nested JARs, shaded classes, multi-release JARs, and test/agent/plugin classpaths — and how to fix it at the right layer via the JDK runtime, dependency version, or compiler target, instead of lowering versions arbitrarily.

## 1. What does UnsupportedClassVersionError actually mean?

### 1.1. A typical message

Suppose an application is run on JDK 17, but the class to be loaded was compiled for JDK 21:

```text
Exception in thread "main" java.lang.UnsupportedClassVersionError:
  com/example/payment/PaymentClient has been compiled by a more recent
  version of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

Analysis:

| Component | Meaning |
|---|---|
| `com/example/payment/PaymentClient` | Binary name of the class the JVM is attempting to define |
| `class file version 65.0` | The `.class` file was written with class-file major 65, minor 0 |
| `recognizes ... up to 61.0` | The current runtime supports class-file major versions up to 61 |
| `UnsupportedClassVersionError` | The JVM rejects the class format/version, typically immediately during class loading/definition |

Here **65 corresponds to Java 21; 61 corresponds to Java 17**. Changing the compiler's `JAVA_HOME` on the developer machine does not make the production JVM 17 automatically understand Java 21 classes.

### 1.2. The error can originate from a dependency, not application code

The problem is not necessarily in `Main.class`. For example:

```text
order-service (classes target 17)
├── payment-sdk 4.2       (classes target 17)
│   └── payment-crypto 3.1 (classes target 21)
├── json-library 2.0      (classes target 11)
└── logging-api 1.4       (classes target 8)
```

In the hypothetical diagram, JDK 17 can load most classes. When the payment processing path reaches `payment-crypto`, the JVM rejects the major 65 class. One should not conclude that the entire `payment-sdk` was compiled for Java 21 if in reality only one transitive artifact has this bytecode.

### 1.3. The runtime may start up before the error appears

Class loading usually happens on demand. Therefore:

- `Main` having run does not mean every dependency can be loaded.
- `GET /health` returning 200 does not guarantee that the JPA provider or encryption code can be loaded.
- An optional module may only be loaded when a feature flag is enabled.
- Reflection, ServiceLoader, plugin discovery, or dynamic classloading can cause a class to appear only when executing a workflow.
- A multi-release JAR may select a different implementation when the runtime JDK changes.

**Startup pass is not enough** to confirm bytecode compatibility for the entire application artifact.

## 2. Class-file format: major and minor versions

### 2.1. Header of a .class file

According to the class file format, the beginning contains:

```text
Offset   Size (bytes)   Content
0        4              Magic number: CA FE BA BE
4        2              minor_version
6        2              major_version
8        ...            Constant pool and the rest
```

`major_version` and `minor_version` are 16-bit unsigned integers in **big-endian** order. The JVM reads these fields before it can fully understand the rest of the class.

For example:

```text
CA FE BA BE 00 00 00 41 ...
            ----- -----
            minor major
              0    65
```

`0x0041` in decimal is 65. Do not confuse 65 with “Java 65”; it is the *class-file major version* corresponding to Java 21.

### 2.2. Common bytecode level table

| Java release | Class-file major | Example |
|---|---:|---|
| Java 8 | 52 | `52.0` |
| Java 9 | 53 | `53.0` |
| Java 10 | 54 | `54.0` |
| Java 11 | 55 | `55.0` |
| Java 12 | 56 | `56.0` |
| Java 13 | 57 | `57.0` |
| Java 14 | 58 | `58.0` |
| Java 15 | 59 | `59.0` |
| Java 16 | 60 | `60.0` |
| Java 17 | 61 | `61.0` |
| Java 18 | 62 | `62.0` |
| Java 19 | 63 | `63.0` |
| Java 20 | 64 | `64.0` |
| Java 21 | 65 | `65.0` |
| Java 22 | 66 | `66.0` |
| Java 23 | 67 | `67.0` |
| Java 24 | 68 | `68.0` |
| Java 25 | 69 | `69.0` |

The table reflects class-file versions according to the listed releases, not a list of all runtime vendors/updates. A modern JDK runtime typically supports the corresponding older class formats, but **does not support class-file major versions from future releases**.

### 2.3. Minor version and preview features

Starting from Java releases that support previews, classes using a preview language feature are typically marked with **minor version 65535 (0xFFFF)**, instead of 0.

For example, a class:

```text
major version: 65
minor version: 65535
```

differs from ordinary `65.0`. A Java 21 preview class must be handled according to the preview rules of **Java 21 itself**, including the `--enable-preview` option when required. One cannot simply change the runtime to Java 22 and assume Java 21 preview bytecode will be accepted; preview classes carry release-specific constraints.

Practical rules:

- Must read **both major and minor**, not just major.
- Distinguish between “runtime too old” and “preview class not enabled/supported”.
- Do not recommend `--enable-preview` as an arbitrary fix for classes with a major version higher than the JDK.
- Do not publish a preview artifact as an ordinary portable Java 21/22 library without documenting the runtime condition.

### 2.4. Java source version is not enough to infer dependency bytecode

A project using Java 17 source syntax can still be built by JDK 21 with some tasks producing major 65 classes if compiler configuration is not applied consistently. Conversely, source written in 17-compatible syntax can be compiled with JDK 21 using `--release 17` to produce bytecode 61.

Additionally, **every library downloaded from a repository is already pre-compiled**. The project's compiler does not recompile those classes simply because the project sets release 17.

## 3. Distinguishing JVM errors from bytecode tooling errors

Not every log containing the words “unsupported class file major version” is a `java.lang.UnsupportedClassVersionError` from the JVM.

### 3.1. JVM loader rejects the class

For example:

```text
java.lang.UnsupportedClassVersionError:
  com/example/Foo has been compiled by a more recent version...
```

This is an error at the class definition/loading layer: the runtime JVM does not support the requested class format/version.

### 3.2. ASM or bytecode parser does not understand the class

Another error may be:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

The running JVM may **already be JDK 21**, but the ASM library used by a Gradle plugin, code coverage agent, serializer, or bytecode transformer does not yet support class-file major 65.

Fixing at the right layer means checking the **ASM/Byte Buddy/Groovy/Kotlin compiler/coverage/build plugin version** and the environment running the tool. There is no evidence that the application source needs to be changed.

### 3.3. Build tool fails to start on a new JDK

For example, an error occurs when Gradle loads build logic or Kotlin DSL, before the `compileJava` task runs. In that case, check:

- Whether the Gradle Wrapper version supports **running the Gradle Daemon** on the target JDK.
- Whether the plugin binary was compiled for the JVM running the Daemon.
- Whether the embedded Groovy/Kotlin compiler or ASM version in the tool recognizes the new class format.
- Whether an internal plugin calls an API that has changed.

Do not equate “Gradle does not run on JDK 21” with “the application JAR does not run on JDK 21”.

### 3.4. Quick classification table

| Error line or timing | Component worth checking first |
|---|---|
| JVM reports `UnsupportedClassVersionError` during `java -jar` | Runtime Java version and the loaded class |
| ASM `ClassReader` reports unsupported major | Bytecode parser version in the tool |
| Gradle fails during configuration phase | Gradle Wrapper, plugin API, build logic JVM |
| Maven Mojo fails before compiling | Maven JVM and plugin/plugin dependencies |
| JUnit discovery/coverage fails | Test engine, Byte Buddy, ASM, JaCoCo, or agent |
| Native-image build fails when analyzing classes | AOT toolchain/JDK compatibility |
| Reflection loads class for the first time on a request | Lazy-loaded dependency or generated class |

**Read the exception type and full stack trace before choosing a fix.** A log with only a single line “major version 65” is not enough to determine whether the error belongs to the JVM, Gradle, ASM, or the test framework.

## 4. Why is the bytecode level of each dependency the answer?

### 4.1. A dependency graph is a collection of different binaries

An application may contain:

- Main project classes.
- Previously published internal modules.
- Direct dependencies.
- Transitive dependencies.
- Runtime-only providers.
- Test dependencies and test engines.
- Annotation processors and code generators.
- Build plugins with their own classpaths.
- Java agents, instrumentation libraries.
- JARs provided by the application server or plugin container.
- Classes shaded/relocated into a fat JAR.
- Multi-release JAR entries.

Each source may contain different class-file major/minor versions. A project setting:

```xml
<maven.compiler.release>17</maven.compiler.release>
```

**does not** convert major 65 class files already inside a library downloaded from Maven Central into 61.

Similarly in Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

only restricts the Java compile tasks to which that configuration applies, and does not automatically modify the bytecode of all dependencies or Gradle plugins.

### 4.2. Direct dependencies do not necessarily contain the offending class

For example:

```text
api-service
└── com.example:search-client:5.0   [declared]
    └── com.example:search-core:7.2
        └── com.example:vector-bridge:3.0
            └── com.example:simd-helper:2.0 [bytecode 65]
```

The source of `api-service` may not import `simd-helper`. The runtime can still load its classes when the search client uses an optimization path.

Therefore, asking to “lower sourceCompatibility to 17” is at the **wrong layer** if the error lies in a transitive artifact already compiled for 21.

### 4.3. One JAR can contain multiple major versions

There is no rule forcing all classes in a JAR to have the same major. A build can accidentally bundle generated classes from a newer JDK, classes from another tool, or relocated code.

In addition, a multi-release JAR intentionally contains different implementations per Java release. Therefore, one should record all of:

- **Minimum/maximum major** found.
- **Specific class path**.
- **Archive and nested archive location**.
- **Effective major selected by the runtime**, if a multi-release JAR is used.
- **Module/artifact owner and dependency path**.

A report stating only “JAR X compiled for Java 21” may be too coarse if the error actually comes from a class that is not selected when running on JDK 17.

## 5. Diagnostic workflow from stack trace to artifact

### Step 1 — Capture the full error

Record:

- Exact exception type and message.
- Rejected class.
- Reported major/minor version.
- Maximum class-file version recognized by the runtime.
- Full `Caused by` chain.
- Thread/task/endpoint that triggered the error.
- Timestamp and environment.

Do not only copy the last line `Application failed to start`.

### Step 2 — Verify which JVM is actually running

```bash
java -version
```

only tells you the Java on the current shell. An application started by a service manager, Gradle daemon, Maven Surefire fork, or container entrypoint may use a different JVM.

Example running with an explicit path:

```bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/java" -jar app.jar
```

On PowerShell:

```powershell
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\java.exe" -jar .\app.jar
```

Check `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, image digest, and runtime process command line as well.

### Step 3 — Read the major version of the offending class

If the class is inside a regular JAR:

```bash
javap -verbose -classpath lib/problem-library.jar \
  com.example.payment.PaymentClient
```

Find:

```text
minor version: 0
major version: 65
```

Use `javap` from a sufficiently new JDK to parse the class-file format used. If the class is in a nested JAR, WAR, or nonstandard launcher, point to the exact file/class or extract in a controlled manner.

### Step 4 — Identify the exact artifact

Use Maven/Gradle dependency graphs, the file list inside the artifact, class-loading logs, and repository metadata to identify the JAR containing the class.

Do not assume group/artifact version from the stack trace: package names can be relocated, bundled, or shaded.

### Step 5 — Observe where the class is loaded from

If there are multiple copies of the same class on the runtime classpath, the class source at runtime may differ from the file being inspected with `javap`.

On HotSpot you can use logging:

```bash
java -Xlog:class+load=info -jar app.jar
```

The log is very large and should only be used in an appropriate diagnostic environment. If the class itself is rejected by the JVM before definition, the log may not have a “loaded successfully” line for that class; combine the exception with classpath/archive inspection.

### Step 6 — Decide which layer to fix

There are three main directions:

1. **Upgrade the runtime JVM** to a release that supports the binary's major version, if permitted and the entire stack is compatible.
2. **Select a dependency release matching the minimum runtime JDK**, preferring a vendor-supported version.
3. **Recompile the source of the offending artifact** with an appropriate compiler target, if you own the source and APIs/dependencies allow it.

Do not pick a fix by blindly changing `sourceCompatibility` of the main project or editing a few header bytes in the class file.

## 6. The javap tool: verifying a specific class

### 6.1. Inspecting a class from the build directory

```bash
javap -verbose -classpath build/classes/java/main \
  com.example.Main
```

or with Maven:

```bash
javap -verbose -classpath target/classes \
  com.example.Main
```

The output usually has `minor version` and `major version` near the top. If the compiled class does not exist at this path, check the actual task/source set/module configuration instead of creating a different output yourself.

### 6.2. Inspecting a class in a dependency JAR

```bash
javap -verbose -classpath libs/payment-client.jar \
  com.example.payment.PaymentClient
```

Use the exact JAR that was resolved or deployed. A JAR manually downloaded from the internet with the same name but a different checksum is not evidence for the production artifact.

### 6.3. Inspecting a class without a simple package name

For example, class `com/example/PaymentClient.class`:

```bash
jar tf libs/payment-client.jar
```

will help confirm the entry path. `javap` typically takes a binary name like `com.example.PaymentClient`, not the zip file path.

### 6.4. If javap fails because the format is too new

An older JDK tool may also not understand a classfile version higher than itself. Use a sufficiently new JDK to analyze or read the 8-byte class-file header with a binary tool. **You do not need to load the class with an older runtime to read the file's major version**.

## 7. Inspecting all class-file versions, not just one class

### 7.1. Why is scanning needed?

A dependency may contain 2,000 classes while only a few are major 65. A large JAR may use toolchains that produce different source sets. If you want to know the effective minimum JDK of an entire bundle, you should observe bytecode levels **per class**, including relevant transitive/nested JARs.

### 7.2. Example Python script to scan .class files in an archive

A small tool can read class headers directly without launching a JVM or compiling the application. The example below uses the Python standard library, scanning JAR/WAR/EAR/ZIP and up to two levels of nested archives:

```python
import io
import struct
import sys
import zipfile
from collections import Counter

MAJOR_LABELS = {
    52: "Java 8",
    55: "Java 11",
    61: "Java 17",
    65: "Java 21",
    66: "Java 22",
    69: "Java 25",
}

ARCHIVE_EXTENSIONS = (".jar", ".war", ".ear", ".zip")
MAX_NESTING = 2
rows = []


def scan_archive(archive, origin, depth=0):
    for entry in archive.infolist():
        if entry.is_dir():
            continue

        path = entry.filename
        full_name = f"{origin}!/{path}"

        if path.endswith(".class"):
            with archive.open(entry) as stream:
                header = stream.read(8)

            if len(header) != 8:
                print("TRUNCATED", full_name)
                continue

            magic, minor, major = struct.unpack(">IHH", header)
            if magic != 0xCAFEBABE:
                print("NOT_CLASS", full_name)
                continue

            rows.append((major, minor, full_name))
            continue

        if depth < MAX_NESTING and path.lower().endswith(
            ARCHIVE_EXTENSIONS
        ):
            # Example; only use with archives from trusted sources.
            # In practice, limit decompressed size and number of extracted files.
            with archive.open(entry) as stream:
                nested_bytes = stream.read()

            try:
                with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                    scan_archive(nested, full_name, depth + 1)
            except zipfile.BadZipFile:
                print("BAD_NESTED_ARCHIVE", full_name)


if len(sys.argv) != 2:
    raise SystemExit("Usage: python scan_versions.py app.jar")

with zipfile.ZipFile(sys.argv[1]) as archive:
    scan_archive(archive, sys.argv[1])

counts = Counter((major, minor) for major, minor, _ in rows)

print("Scanned classes:", len(rows))
for (major, minor), count in sorted(counts.items()):
    label = MAJOR_LABELS.get(major, "unknown release")
    print(f"major={major}, minor={minor}, {label}: {count}")

print("Top class-file versions:")
for major, minor, path in sorted(rows, reverse=True)[:30]:
    print(f"  {major}.{minor}  {path}")
```

Reference run:

```bash
python scan_versions.py application.jar
```

The script only illustrates reading headers and aggregating statistics; it is not a complete production audit tool. For untrusted archives, you must limit decompressed size, entry count, recursion, and resources to avoid ZIP bombs or overly large files. A two-level depth may miss deeply nested archives; artifacts outside the archive such as a `lib/` directory must be scanned separately.

### 7.3. How to read the results

Hypothetical example:

```text
Scanned classes: 7421
major=52, minor=0, Java 8: 1002
major=55, minor=0, Java 11: 3311
major=61, minor=0, Java 17: 3006
major=65, minor=0, Java 21: 102

Top class-file versions:
  65.0  app.jar!/BOOT-INF/lib/crypto-lib.jar!/com/example/crypto/...
  65.0  app.jar!/BOOT-INF/lib/crypto-lib.jar!/com/example/crypto/...
```

There are 102 major 65 classes to investigate when targeting a Java 17 runtime. However, a “highest major 65” result **does not automatically prove Java 17 will definitely load those classes** — for example, version-specific classes inside a multi-release JAR might not be selected. You need to inspect the entry location and loader semantics.

### 7.4. Distinguishing detection from runtime selection

A scanner reads all class bytes, whereas a runtime classloader only loads classes according to lookup paths, environment conditions, and multi-release rules.

Therefore, there are two questions:

1. **Inventory:** which class-file major versions does the artifact contain?
2. **Effective runtime:** on a specific JDK and classloader, which class will be selected/loaded?

Reports should answer both when triaging a real incident.

## 8. Multi-release JARs: one JAR, multiple intentional bytecode levels

### 8.1. Structure

A multi-release JAR may contain:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
├── META-INF/versions/9/com/example/Feature.class
├── META-INF/versions/17/com/example/Feature.class
└── META-INF/versions/21/com/example/Feature.class
```

The manifest may include:

```text
Multi-Release: true
```

When running on a runtime that supports multi-release JARs, the standard classloader can select the highest version-specific class not exceeding the runtime feature version for matching lookups.

### 8.2. Why can a scanner raise a “false alarm”?

Suppose:

- Root `Feature.class` is major 52.
- `META-INF/versions/17/Feature.class` is major 61.
- `META-INF/versions/21/Feature.class` is major 65.

A scanner checking all classes will report major 65. However, on Java 17, the version in directory 21 is typically not selected; the JVM can use version 17. Having a major 65 class in an MR-JAR does not always mean Java 17 cannot run.

On the other hand, if the **root entry** or the **entry selected for JDK 17** has major 65, the error is real.

### 8.3. Inspecting manifest and entry names

```bash
jar tf library.jar
jar --describe-module --file library.jar
```

The second command inspects module metadata and does not replace checking the manifest. For a specific archive, you can use a ZIP tool or extract the manifest to confirm `Multi-Release: true`.

### 8.4. Framework launchers may have their own classloading

Spring Boot executable JARs, OSGi bundles, application servers, and custom classloaders may load classes through their own logic. You must verify **how the actual loader handles multi-release entries**. Do not assume every nested archive is read by every tool the same way as Java's standard `JarFile`.

### 8.5. Preview classes inside an MR-JAR

If a version-specific class uses preview bytecode, preview rules still apply. A major 65 minor 65535 entry intended for Java 21 may require `--enable-preview` when selected on JDK 21; it should not be used as the default implementation across multiple releases.

## 9. Maven: finding which dependency was actually selected

### 9.1. Dependency tree by module and scope

Reference commands:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw dependency:tree -Dverbose
```

In a multi-module project, run on the application module or the appropriate reactor selection. Note the Maven Dependency Plugin version to see how it displays omitted/conflicts.

Look for:

- Was a direct dependency upgraded in version?
- Which transitive artifacts changed due to a BOM?
- Does runtime scope differ from compile scope?
- Was a higher version selected due to dependency management or direct declaration?
- Is there an optional/provider dependency loaded dynamically?
- Does a profile or plugin produce a different graph between local and CI?

### 9.2. The resolved version does not indicate bytecode major

For example:

```text
com.example:crypto-core:jar:3.0.0:runtime
```

Just looking at the version string 3.0.0 cannot tell you whether it requires Java 17 or 21. You must check release notes/minimum Java version or the **class-file headers of the actual artifact**.

A “newer” library version does not automatically have a higher bytecode target; many projects keep a Java 8/11 target across multiple releases. Conversely, a minor release can raise the minimum JDK under vendor policy.

### 9.3. Effective POM and dependency management

```bash
./mvnw help:effective-pom
```

BOMs and parent POMs can manage a different version than the value you thought was declared. When multiple BOMs manage the same artifact, verify which management entry wins according to Maven rules.

Do not override a version directly in a child module while ignoring BOM/framework alignment. This can create binary/API mismatches even if it resolves `UnsupportedClassVersionError`.

### 9.4. Plugin classpath is independent from app classpath

Maven plugins are loaded into the plugin realm of the JVM running Maven. If an internal Mojo or Maven plugin is compiled for Java 21 while Maven runs on Java 17, an error can occur **when the plugin is executed**, even if application code targets 17.

In that case, you need to:

- Check `./mvnw -version` to see the Maven JVM.
- Find the plugin goal and group/artifact/version.
- Check the class-file major of the plugin artifact.
- Choose a compatible Maven JVM or supported plugin release.
- Avoid adding plugin libraries to application `<dependencies>` as a way to “fix” the plugin realm.

## 10. Gradle: inspecting the graph by configuration

### 10.1. Do not look at only one generic dependency report

With Gradle, there are multiple classpaths/configurations:

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

Names like `:app` are examples; replace with the actual module. If the application uses custom configurations, Android/Kotlin plugins, or custom build logic, check the corresponding graphs.

### 10.2. dependencyInsight

```bash
./gradlew :app:dependencyInsight \
  --dependency crypto-core \
  --configuration runtimeClasspath
```

The output can tell you why a version was selected and the related dependency path. This helps investigate cases where a transitive dependency has bytecode exceeding the minimum runtime.

However, `dependencyInsight` **does not read the major version of individual classes**. It explains version resolution; bytecode inspection is a separate step.

### 10.3. Java toolchains separate the compiler from the Gradle Daemon

For example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

In a Gradle release supporting this configuration, the JDK 21 compiler can produce Java 17 target application classes. However:

- Which JDK the Gradle Daemon runs on is still a separate question.
- Build plugins may require a different JVM.
- Annotation processors have their own runtime/bytecode constraints.
- Kotlin/Scala/Groovy compiler tasks are not necessarily governed by JavaCompile config.
- Dependencies downloaded from repositories retain their original bytecode.
- The test JVM may differ from the toolchain if tasks are not configured or are controlled differently by plugins.

A major 65 class error in a plugin when the Gradle Daemon runs on JDK 17 is not fixed by `options.release=17` in the application module.

### 10.4. Source compatibility is also not enough

```groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
```

can affect the language/bytecode target for Java compilation, but does not provide full restriction of Java platform APIs like `--release 17`. When needing to support runtime 17, prefer appropriate toolchain/`options.release` and inspect dependency bytecode separately.

### 10.5. If Gradle fails to start

Do not try to run all `dependencies` tasks with a Gradle Wrapper that does not support the JDK you are using. First check wrapper/JDK compatibility, and you can use a compatible build JDK to run dependency-reporting tasks while the target runtime being verified remains a different JDK.

**The JDK running Gradle does not necessarily have to be the same as the JDK running the application.**

## 11. Annotation processors and generated classes

### 11.1. A processor is an executable binary in the build

Lombok, MapStruct, QueryDSL, Dagger, and many other annotation processors are loaded inside the compiler process. If a processor JAR contains major 65 classes while the compiler process runs on Java 17, a class loading/version error can occur during compilation.

Setting application source target 17 does not change the processor's bytecode.

### 11.2. Generated source does not equal generated bytecode

A processor can:

- Generate `.java` files, and then the main compiler creates bytecode according to target.
- Generate `.class` files directly.
- Generate resources/metadata used at runtime.
- Trigger another code generation plugin/program.

If a task generates classes directly using a JDK 21 toolchain and packages them into a target 17 artifact, the output may contain major 65 even though the main JavaCompile produces major 61.

Therefore, when debugging, scan the **packaged artifact**, not just `build/classes/java/main`.

### 11.3. Compilation pipelines that need alignment

| Pipeline | What to verify |
|---|---|
| JavaCompile main | `--release`/toolchain/bytecode target |
| JavaCompile test | Test target and test runtime JDK |
| Kotlin compilation | Kotlin JVM target/JDK, compatibility with Java classes |
| Groovy/Scala compilation | Compiler target and JVM requirements |
| Annotation processor | Processor bytecode and JDK running the compiler |
| Codegen/bytecode enhancement | Tool version, emitted class-file version |
| Test agent/instrumentation | Parser/ASM/Byte Buddy support for major version |
| Shadow/shade/repackage | Not accidentally embedding newer class versions |

When multiple modules and languages work together, a `--release` configuration on the root module does not guarantee all outputs are produced at the right level.

## 12. Runtime-only, compile-only, and plugin classpaths can differ

A project may have these layers:

```text
BUILD JVM (Gradle/Maven):
  - build plugins
  - convention plugins
  - annotation processors / generators

COMPILER TARGET:
  - application classes
  - generated classes

TEST JVM:
  - application/test classes
  - JUnit engine + mocking/coverage agents

PRODUCTION JVM:
  - application JAR/WAR
  - runtime dependencies
  - application server/shared libs
  - javaagent/native integration
```

Each JVM has a specific version and each classpath may contain different bytecode majors.

### 12.1. Example mismatch between test and production

- Developers run tests with Java 21; all major 65 dependencies load fine.
- Application class output is compiled targeting 17.
- The production container uses Java 17.
- A runtime-only major 65 dependency is loaded when processing a real message.
- Production hits `UnsupportedClassVersionError`.

Only checking `javap` on `Main.class` will show major 61 and miss the error. You must inspect the **runtime graph** and run the packaged artifact on the minimum supported JDK.

### 12.2. Example mismatch between Maven JVM and Surefire fork

Maven may run on JDK 17 while the test JVM is configured to use JDK 21 (or vice versa). A plugin must load on the **Maven JVM**, whereas test classes must load on the **test JVM**.

When an error appears in the plugin realm or forked test process, explicitly record which process threw the exception. Do not use `mvn -version` as sole proof of the test runtime if toolchains/fork overrides are present.

### 12.3. Application server

A WAR may be compiled with major 61 while a server shared library/provider has major 65 classes. If the container/app server runs Java 17, the error can come from the server module rather than `WEB-INF/lib`.

Read server logs, inspect classloader sources, and check against the server/JDK support matrix. Scanning only the WAR is not enough.

## 13. Thin JARs, fat JARs, shaded JARs, and nested dependencies

### 13.1. Thin JAR

For example:

```text
distribution/
├── app.jar
└── lib/
    ├── http-client.jar
    ├── serializer.jar
    └── native-bridge.jar
```

You must scan **all JARs actually on the launcher classpath**. A scan of `app.jar` alone will miss major 65 in `lib/serializer.jar`.

### 13.2. Executable Spring Boot JAR

A common layout:

```text
app.jar
├── BOOT-INF/classes/
├── BOOT-INF/lib/
│   ├── payment-client.jar
│   └── crypto-core.jar
└── org/springframework/boot/loader/...
```

Each nested JAR contains pre-compiled classes. The Spring Boot launcher having major 61 does not prove `BOOT-INF/lib/crypto-core.jar` is also major 61.

Use an archive scanner that supports nested JARs, or extract an inspection copy to a trusted temporary directory and run `javap` on the dependency you want to inspect.

### 13.3. Shaded/relocated classes

A fat JAR may contain library classes under renamed packages, for example:

```text
com/example/app/shaded/crypto/NativeBridge.class
```

The stack trace then no longer reflects the original groupId. You need to use build configuration/relocation reports, dependency locks/graphs, and class fingerprints to determine the source.

Even if the original library targeted Java 17, a shading plugin bumping bytes does not mean all classes have the same version. Only the class header and what is actually packaged give the exact answer.

### 13.4. Assembly/resource transforms

Some packaging plugins can:

- Embed a newer JAR than expected.
- Package duplicate versions.
- Strip certain classes/resources.
- Regenerate classes or bytecode via instrumentation.
- Lose `META-INF/services`, causing a different provider to be loaded.

The right test is inspecting the **final deployed artifact**, not just outputs prior to `jar`/`shadowJar`/`repackage`.

## 14. Class loading logs and classpath sources

### 14.1. When multiple copies of the same class exist

For example:

```text
app.jar!/BOOT-INF/lib/crypto-3.1.jar
server/lib/crypto-2.4.jar
plugins/crypto-2.8.jar
```

If binary names collide, which class is loaded depends on the classloader and delegation policy. A major 65 copy of `crypto-3.1` might not be selected, or might be selected in an application classloader even though an older copy exists on the server.

To investigate:

1. Identify the class causing `UnsupportedClassVersionError`.
2. List all JARs/paths containing that binary name.
3. Identify the classloader defining the class.
4. Observe classloading/logs if appropriate.
5. Compare with launcher, application server, and shading configuration.
6. Check the version/bytecode of the copy actually selected.

### 14.2. Java agents can also create/load classes

Agents can instrument code and load helper classes into the bootstrap/system/application classloader. If a newer agent version introduces major 65 classes into a Java 17 runtime, the exception can appear before the business application.

Check `-javaagent`, the agent JAR manifest, and vendor JDK compatibility. Do not remove the agent from production as a default fix; obtain a supported version or an alternative operational plan.

### 14.3. Plugin systems and ServiceLoader

A plugin JAR that is only loaded when a specific feature is enabled can carry a higher bytecode version. If testing only starts the application without activating the plugin, the error will be missed.

You need to run plugin discovery, provider creation, and workflows that actually use the plugin on the minimum supported JDK.

## 15. Preview features: errors differ from lower runtimes

### 15.1. Compiling preview

In a Java release supporting preview features, an example compile command may be:

```bash
javac --enable-preview --release 21 PreviewExample.java
```

If the compiler emits a class file marked minor 65535 for preview, the JVM will apply the preview rules of the corresponding release.

### 15.2. Runtime of the same release

```bash
java --enable-preview PreviewExample
```

However, `--enable-preview` does not mean “allowed to run any future bytecode”.

For example:

- JDK 17 cannot read major 65 classes just because preview is enabled.
- A Java 21 preview class is not automatically allowed to run on Java 22 as an ordinary Java 21 class.
- A dependency using preview public APIs may impose preview requirements on consumers and publication policies.

### 15.3. Deciding when a dependency contains preview classes

1. Determine the actual major/minor of the class.
2. Check whether the dependency release intentionally uses preview.
3. Read vendor policy and runtime requirements.
4. If production does not accept preview, choose another stable release.
5. If preview is permitted, test with the exact JDK release, flags, and workload.
6. Do not lower the minor version in the class header with a hex editor; class semantics/APIs may genuinely depend on preview.

## 16. Fixing at the right layer: upgrading the runtime JDK

### 16.1. When should you upgrade the runtime?

If a dependency requires Java 21 while the environment runs Java 17, and the application/framework/OS/vendor policy already supports Java 21, upgrading the production JDK may be the right path.

Roadmap:

1. Confirm the minimum JDK of the dependency and other components.
2. Run the **current artifact** on the target JDK when possible.
3. Check framework/native/agent compatibility.
4. Run integration/contract tests.
5. Measure startup, warm-up, p95/p99, CPU/GC/memory.
6. Perform a controlled rollout with rollback.

Changing the runtime does not mean all code must compile with target 21. Major 61 classes can still be loaded on JDK 21.

### 16.2. Do not upgrade the JDK solely for an unnecessary optional dependency

If a major 65 dependency is only pulled in by an unused feature, you can:

- Remove the dependency following supported architecture.
- Select a library version that supports the minimum JDK.
- Split modules/features by runtime requirement.
- Use appropriate server/client APIs instead of that library.

Upgrading the entire production runtime still requires evaluating support and operations; it is not always the lowest-cost option.

### 16.3. Production image must use the right JDK

A CI build using Java 21 might release onto a Java 17 Docker image because the Dockerfile was not updated. When the error appears, check:

- Runtime base image and image digest.
- Entrypoint.
- JVM process `java -version`.
- Helm/manifest environment overrides.
- Service manager.
- Whether the rollout actually pulled the new image.

Do not edit application source if the cause is an outdated runtime image.

## 17. Fixing at the right layer: choosing a dependency compatible with the minimum JDK

### 17.1. When the runtime cannot be upgraded

Production may be forced to stay on JDK 17 due to vendor support, compliance, application server, or rollout constraints. When a new library requires Java 21, you must choose a **release supported by the vendor on Java 17**.

Hypothetical example:

```text
crypto-lib 3.0  -> minimum Java 17
crypto-lib 4.0  -> minimum Java 21
application target/runtime -> Java 17
```

Do not look only at semver; check release notes, minimum supported Java, and binary contents of the specific release.

### 17.2. Downgrading can cause linkage errors

If the application or another library was compiled against `crypto-lib 4.0` but runtime substitutes 3.0, you may encounter:

```text
NoSuchMethodError
NoSuchFieldError
AbstractMethodError
ClassCastException
```

Therefore, fixing `UnsupportedClassVersionError` via downgrade does not prove the entire stack is compatible.

You need to:

1. Check the framework/BOM compatibility matrix.
2. Identify API differences between the two library releases.
3. Verify binary compatibility of callers.
4. Run source compilation when needed.
5. Run runtime integration tests.
6. Check security support and CVEs.

### 17.3. A BOM can raise the minimum JDK for the whole suite

Upgrading Spring Boot/framework/BOM can change dozens of transitive versions. If one dependency bumps its minimum JDK, it may be a symptom of a **whole-stack minimum JDK requirement**, not an isolated bug in one JAR.

Trying to pin an old version via an override can break compatibility. Prefer selecting a BOM/framework line that supports the target runtime, then use justified and tested exceptions.

### 17.4. Do not rewrite bytecode by editing headers

Changing bytes `00 41` (65) to `00 3D` (61) in the header does not turn a Java 21 class into Java 17 bytecode. The class may use new instructions, constant-pool structures, attributes, APIs, or semantics.

Do not treat patching headers, downloading pre-modified JARs from unknown sources, or running arbitrary bytecode transformers as an officially supported solution. If backporting is needed, perform it using appropriate source/compiler/toolchain and regression tests.

## 18. Fixing at the right layer: compiling artifacts you own

### 18.1. What does --release solve?

With a sufficiently new JDK compiler, `javac --release N` targets:

- The language level of Java release N.
- The corresponding class-file target.
- The Java SE platform APIs permitted in release N.

For example, an application must run on Java 17 but builds on JDK 21:

```bash
javac --release 17 -d out src/com/example/Main.java
```

Ordinary class output will have major 61, not 65. However, if the source actually uses a Java 21 API, the compiler will report an error because the API does not belong to release 17.

### 18.2. Maven Compiler Plugin

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Choose a compatible Maven Compiler Plugin version, Maven core, and build JDK. If configured in a parent, check the effective POM and module overrides.

Maven compiler release **does not recompile** third-party dependencies. If there are generated classes/other language tasks, check their outputs separately.

### 18.3. Gradle JavaCompile

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Illustrative configuration: uses the Java 21 compiler and generates Java 17 output for the configured JavaCompile tasks. Requires a Gradle version that supports JDK 21 toolchains.

Do not confuse the JDK running the Gradle Daemon with the compiler/toolchain JDK. A major 65 plugin binary will still fail to load on a JDK 17 Daemon.

### 18.4. Recompiling may not be enough

Even after compiling application classes to major 61:

- Dependency JARs contain major 65 classes.
- Generated bytecode contains 65.
- Test fixtures contain 65.
- Kotlin/Scala/Groovy modules have different targets.
- The runtime app server/agent still loads major 65 classes.

Therefore, you must scan the **final artifact and the dependency JARs actually deployed**.

## 19. Build JDK and runtime JDK: common cases

### 19.1. JDK 21 build, JDK 17 deploy

```text
CI Java:
  java -version -> 21

Compiler:
  release -> 21 (implicit/default)

Container:
  java -version -> 17

Result:
  application classes -> major 65
  production runtime -> supports up to major 61
```

Possible fixes:

- If runtime policy requires 17: configure `--release 17` and check APIs/dependencies.
- If the application needs Java 21 features: upgrade the runtime container to 21.
- If CI changed JDKs accidentally: pin the toolchain and runtime matrix.

### 19.2. Application target 17, transitive dependency target 21

```text
Application .class: 61
Dependency A .class: 61
Dependency B .class: 65
Runtime: Java 17
```

The fix does not lie in the application's compiler target. You need to upgrade the runtime or replace dependency B (with API/compatibility checks).

### 19.3. Build plugin target 21, Gradle Daemon Java 17

```text
Gradle Daemon: Java 17
Convention plugin: major 65
Java compiler toolchain: Java 21
Application target: Java 17
```

The plugin is loaded inside the Gradle Daemon before the Java compiler toolchain can help. The fix is ensuring the Daemon is new enough for the plugin or rebuilding/choosing a plugin compatible with the JVM running Gradle — while also checking Gradle API compatibility.

### 19.4. Java 21 tests, Java 17 production runtime

A JUnit test suite running on JDK 21 can load a major 65 dependency successfully. Java 17 production fails. Therefore, CI should include a step testing **on the declared minimum runtime**, not only on the latest JDK used for compilation.

## 20. Distinguishing from other linkage errors

| Error | Typical meaning | How does it differ from UnsupportedClassVersionError? |
|---|---|---|
| `UnsupportedClassVersionError` | Class-file format/version is not accepted by the runtime | JVM rejects class version |
| `NoClassDefFoundError` | Class is missing/cannot be defined when required at runtime | May be due to missing class or initialization error, not necessarily major |
| `ClassNotFoundException` | Dynamic class lookup failed | Lookup path/classloader could not find the class |
| `NoSuchMethodError` | Method descriptor requested by caller does not exist | Caller/callee ABI mismatch |
| `NoSuchFieldError` | Field descriptor does not exist | Field API binary mismatch |
| `AbstractMethodError` | Dispatch to implementation that does not satisfy method | Interface/class ABI mismatch |
| `IllegalAccessError` | Illegal access to class/member at runtime | Access rules/linkage, not class major |
| `ClassFormatError` | Class file violates class-file format structure | Not necessarily version too high |
| `VerifyError` | Bytecode fails verification | Does not necessarily require a newer JVM |
| `InaccessibleObjectException` | Reflection into module/package is blocked | JPMS/reflective access |
| `NoSuchElementException` in ServiceLoader | Provider/configuration mismatch | SPI/runtime configuration |
| `UnsatisfiedLinkError` | Native library/symbol load failed | OS/ABI/JNI, not class-file major |

`UnsupportedClassVersionError` is one branch of class loading/linkage-related errors, but the fix must be based on the specific exception. If the JVM reports class major 65 on runtime 17, upgrading an unrelated JSON parser will not solve the root cause.

## 21. Dependency bytecode policy in a multi-module system

### 21.1. Defining minimum runtime at the product level

For example:

```text
Product: payment-service
Minimum supported Java runtime: 17
Maximum accepted class-file major for ordinary classes: 61
Preview classes: not allowed
Deployment: Linux x86-64 JDK 17 + JDK 21 matrix
```

This is an illustrative policy; it needs adjustment if there are multi-release JARs, modules using specific APIs, or plugin/test-only graphs.

### 21.2. Every module should clearly declare its requirements

A reusable library can declare:

- Minimum Java runtime.
- Compiler target.
- Framework/Jakarta API versions.
- Required native libraries or agents.
- Preview feature usage.
- Multi-release JAR behavior.
- Supported Gradle/Maven plugin/JDK combinations if it is a build plugin.

Do not merely write “Java compatible”; it is necessary to know whether it is Java 8, 11, 17, or 21.

### 21.3. Library API vs runtime dependency

A library compiled to major 61 with a runtime-only provider of major 65 cannot be considered fully Java 17 supported. If the provider is required for core functionality, the **effective minimum runtime** may be Java 21.

Conversely, an optional major 65 provider that is not loaded on Java 17 may still allow certain features to run on Java 17, but the contract must clearly publish the feature/version boundary and have tests.

### 21.4. Guardrails should be placed in CI

If a product supports Java 17:

- Compile Java source with `--release 17` where appropriate.
- Inspect the bytecode of produced classes.
- Scan third-party runtime dependencies.
- Distinguish unselected multi-release entries.
- Run tests on the minimum JDK.
- Test the packaged artifact, not only source-set outputs.
- Assign an issue owner when a dependency raises its minimum JDK.
- Record artifact checksums to prevent “local pass, CI fail”.

Do not just check `java -version` of the build runner and assume runtime/dependencies are right.

## 22. Inspecting by artifact graph instead of version names

### 22.1. Useful data inventory

A report might record:

| Artifact | Source | Highest scanned major | Selected major on JDK 17 | JDK requirement per vendor |
|---|---|---:|---|---|
| `app.jar` | Application | 61 | 61 | 17 |
| `crypto-core.jar` | Runtime direct | 65 | 65 | 21 |
| `json-core.jar` | Transitive | 55 | 55 | 11 |
| `multi-lib.jar` | Runtime transitive | 65 | 61 (MR-JAR) | 17+ |
| `build-plugin.jar` | Gradle plugin | 65 | Not part of app runtime | Gradle Daemon JDK 21 |

The rows are only hypothetical examples. In a real report, if the classpath has multiple classloaders, or MR-JARs are handled separately, the “Selected major” column must have concrete evidence.

### 22.2. Why are vendor support and class scanning both needed?

- Vendor documentation says the library supports Java 17, yet the artifact was mistakenly published with major 65 classes.
- Artifact scan finds only major 61, yet the library uses JDK 21 APIs via conditional reflection or native bindings.
- An MR-JAR contains major 65 classes under version 21, yet the vendor supports Java 17 via the root/17 implementation.
- A provider is missing on a Java 17 runtime even though all class majors are <=61.

Class scanning detects **a very specific category of risk**, and does not replace full compatibility testing.

## 23. Runtime dependency mismatch after upgrading framework/BOM

### 23.1. Scenario

Before migration:

```text
framework-bom vA
  -> library-x 2.x (minimum Java 17)
```

After upgrading:

```text
framework-bom vB
  -> library-x 3.x (minimum Java 21)
```

The application still sets `--release 17`. The build may succeed on JDK 21 depending on API usage/compile graph, but running on Java 17 and loading `library-x 3.x` will fail.

### 23.2. Do not override a single module and ignore the rest of the stack

A framework may be tested with coordinated versions. If you downgrade `library-x` to 2.x, the newer framework may call a method that only appeared in 3.x.

Therefore:

1. Verify the JDK requirement of the framework release line.
2. Select a BOM/platform matching the minimum runtime.
3. If an override is necessary, document the risk and test API/binary compatibility.
4. Do not allow multiple uncontrolled versions of the same library family.
5. Scan the packaging output and run the application on the minimum JDK.

### 23.3. A new toolchain JDK is a build condition, not a deploy condition

An organization can use JDK 21 to build while still releasing Java 17-compatible binaries. That is valid if source/platform APIs/dependencies and generated code all comply.

Conversely, just because the Gradle Wrapper uses JDK 21 does not mean the artifact automatically must deploy on Java 21.

## 24. Testing on the minimum supported JDK

### 24.1. Verification matrix

If a library/app declares support for Java 17 and Java 21, it may have a matrix:

| Stage | JDK | Objective |
|---|---|---|
| Compile | 21 with `--release 17` | Restrict source/platform target |
| Bytecode scan | Class-file reading tool | Confirm class major of artifact/deps |
| Unit/integration | 17 | Minimum runtime compatibility |
| Unit/integration | 21 | Target/new runtime compatibility |
| Packaged artifact smoke | 17 and 21 | Verify launcher, JAR/WAR, and runtime libs |
| Production canary | Target runtime | SLO, agent/native/security compatibility |

Not every library necessarily tests every JDK release. However, the **minimum supported runtime** is an important test to catch class-file major drift.

### 24.2. Testing startup and lazy-loaded features

A service may load the offending library only on a special request. Testing needs to trigger:

- Main business endpoints.
- Background jobs and message consumers.
- Driver/provider discovery.
- Serialization formats.
- Plugin loading.
- Optional features supported on the minimum JDK.
- Failure/retry paths.
- Application startup/restart.

### 24.3. Do not skip lowest runtime tests just because the compiler used --release

`--release` restricts Java standard APIs and the class-file target of compiled source, **not** the bytecode of dependent JARs. Runtime testing on the minimum JDK remains essential evidence.

## 25. Security and supply-chain when choosing a remediation

### 25.1. Downgrading can drop security patches

If a newer dependency release requires Java 21 due to a platform upgrade, reverting to an older release may bring back CVEs or end of support. Do not downgrade merely to clear the exception without reviewing security/vulnerability history.

Prefer:

- Selecting a release line still maintained on the current JDK.
- Upgrading the runtime in a controlled manner if business/support policy permits.
- Splitting legacy modules/features along boundaries if needed.
- Having a plan to retire workarounds and technical debt.

### 25.2. Do not take “bytecode-downgraded” JARs from unknown sources

Bytecode transformation/backport tools can have specific use cases, but nothing guarantees that lowering the class-file major is enough to support an older runtime, especially if the code calls APIs absent from older Java.

If using an official backport approach, require:

- A trusted tool/artifact source.
- Published compatibility contract.
- Security review and checksum.
- Integration tests on the target runtime.
- Vendor/support stance.
- Clear release provenance.

### 25.3. Runtime images and JDK updates

A container image tag can change the JDK update or vendor. Record the digest and confirm the actual binary, avoiding situations where a project claims to run Java 17 while a new image has upgraded to Java 21 or still uses an old runtime.

## 26. Practical scenario A: Java 17 application, Java 21 dependency

Assumption:

```text
Application: invoice-service
Main source target: Java 17
Compile JDK: 21
Production JDK: 17
Dependency: report-engine 5.0
  -> render-core 3.0 (class major 65)
```

When the application starts generating reports:

```text
UnsupportedClassVersionError: com/vendor/render/Renderer
class file version 65.0, runtime recognizes up to 61.0
```

### 26.1. Triaging

1. Verify production Java is actually 17.
2. Confirm `Renderer` resides in `render-core-3.0.jar`.
3. Use `javap` or a scanner to confirm class major 65.
4. Check the transitive path from `report-engine`.
5. Read the vendor's minimum Java requirement.
6. Verify the framework/support matrix.

### 26.2. Two potentially valid branches

**Branch 1:** Upgrade the service runtime to JDK 21, keep dependency 3.0, and test all functionality and operations.

**Branch 2:** Use a `render-core`/`report-engine` release still supporting Java 17, with compatibility tests and security review.

**Not a solution:** changing the app's `sourceCompatibility=17` again or patching class headers from 65 down to 61.

## 27. Practical scenario B: Gradle plugin fails, application has never run

Suppose:

```text
Gradle Daemon: Java 17
Java toolchain: Java 21
Custom convention plugin: compiled for Java 21 (major 65)
Application release target: Java 17
```

The build fails when applying the plugin, before `compileJava` executes.

### 27.1. Root cause

The plugin is a binary running inside the **Java 17 Gradle Daemon JVM**. It is not loaded simply because the Java compiler toolchain is Java 21.

### 27.2. Remediation direction

- If Gradle distribution/plugin support allows, run the Daemon on JDK 21.
- Or compile/publish the internal plugin with a lower target, using compatible public Gradle APIs.
- Test plugin consumer fixtures on committed Gradle/JDK combinations.
- Keep the application target/release policy separate.

Do not raise the application bytecode target to 21 if the product still needs to run on Java 17.

## 28. Practical scenario C: Multi-release JAR reports major 65, yet JDK 17 still runs

Suppose a JAR contains:

```text
com/example/Codec.class                     -> major 52
META-INF/versions/17/com/example/Codec.class -> major 61
META-INF/versions/21/com/example/Codec.class -> major 65
```

The manifest has `Multi-Release: true`. An inventory scanner sees major 65. When running on JDK 17 with a loader that supports MR-JARs, the version 17 class is selected and can load normally.

In this case, a policy scanner needs to distinguish between:

- High-major classes in versioned directories meant for newer runtimes.
- High-major classes in the root or effective path of the minimum runtime.
- Preview/minor restrictions.
- Whether or not a loader processes MR-JARs according to contract.

Do not discard a good library just because a scanner reads the aggregate major level without understanding multi-release semantics.

## 29. Practical scenario D: ASM does not support new classfiles

Suppose building on Java 21:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
    at some.coverage.Plugin...
```

The JVM may still support major 65 classes. The issue lies in the version of the library **reading or transforming bytecode**.

Steps:

1. Identify the plugin/agent/classloader containing the actual ASM.
2. Check the plugin's support matrix for Java 21 classfiles.
3. Upgrade the supported tool (coverage, instrumentation, Groovy/compiler, or framework plugin).
4. Check transitive ASM conflicts.
5. Re-run the build/test on the target JDK.
6. Do not force a lower source target arbitrarily if the application needs Java 21 features.

If using `-Xlog:class+load` or plugin dependency inspection is needed, do so in a controlled manner. A newer ASM version does not necessarily fix the error if the plugin still uses another internal API that is no longer compatible.

## 30. Practical scenario E: Preview class with minor 65535

A library is built with Java 21 preview but deployed on Java 21 without preview enabled. The class carries:

```text
major: 65
minor: 65535
```

Upon loading, the runtime may reject it because preview features are not enabled. Depending on product policy:

- Enable preview on the exact JDK release if permitted.
- Choose a stable release of the library that does not use preview.
- Rebuild source without using preview features if possible.
- Avoid declaring a Java21-preview release as Java17-compatible.

Do not use `--enable-preview` to “allow” JDK 17 to run major 65 bytecode or to run Java21 preview classes on a Java22 runtime.

## 31. Quick investigation questionnaire

When receiving an error ticket, you can start with a sequence of questions:

1. Is the exact exception type `UnsupportedClassVersionError` or an exception from ASM/Gradle?
2. Which runtime/process threw the error — application JVM, Maven, Gradle Daemon, JUnit fork, or agent?
3. Which Java release and vendor/build is that JVM using?
4. What is the name of the reported class?
5. What are the major/minor versions of the class?
6. Which JAR is it in, and under which archive is it nested?
7. Does this JAR belong to a direct/transitive/runtime/plugin/processor/test dependency?
8. Why was that dependency version selected?
9. Are there duplicate JARs or custom classloaders?
10. Is this a multi-release entry or a preview class?
11. What is the minimum supported JDK of the product/framework?
12. Can we upgrade the runtime, choose another dependency release, or rebuild the right artifact?
13. Does the option break ABI, security support, or framework BOM alignment?
14. Has the packaged artifact been tested on the real minimum JDK?

Every question should have evidence: logs, bytecode scans, dependency graphs, JDK metadata, or vendor documentation.

## 32. Handoff record for a bytecode compatibility error

A useful investigation record may state:

```yaml
incident:
  error_type: "java.lang.UnsupportedClassVersionError"
  class_name: "com.example.crypto.NativeBridge"
  class_file:
    major: 65
    minor: 0
    required_java: 21
runtime:
  java_version: 17
  max_supported_major: 61
  image_digest: "<digest>"
artifact:
  name: "crypto-core.jar"
  sha256: "<sha256>"
  location: "app.jar!/BOOT-INF/lib/crypto-core.jar"
dependency:
  kind: "transitive-runtime"
  path: "app -> sdk -> crypto-core"
build:
  compile_jdk: 21
  application_release_target: 17
  runtime_dependency_scan: "completed"
decision:
  action: "<upgrade-runtime-or-select-compatible-library>"
  owner: "<owner>"
verification:
  minimum_jdk_test: "PENDING"
  packaged_smoke: "PENDING"
```

This is example data, not a real incident. If application source is major 61 while a transitive library is major 65, clearly record both: that is evidence for why adjusting the application compiler target **cannot solve the root cause**.

## 33. Diagnostic and release checklist

### Identifying the error

- [ ] Confirmed whether the exception truly came from the JVM or from a bytecode parser/tooling.
- [ ] Captured full stack trace and `Caused by`.
- [ ] Verified the exact process/JVM version causing the error.
- [ ] Recorded class name, major, and minor version.
- [ ] Distinguished between an ordinary class and a preview class.
- [ ] Identified the timing of the error: startup, test, build plugin, or lazy runtime path.

### Finding the right artifact

- [ ] Verified the JAR/class containing the offending class by checksum.
- [ ] Checked direct/transitive dependency paths.
- [ ] Checked relevant compile/runtime/test/processor/plugin configurations.
- [ ] Checked nested JARs, fat/shaded JARs, or server shared libraries.
- [ ] Checked multi-release JARs and the effective entry per runtime.
- [ ] Checked duplicate classes/classloaders when signs indicate it.
- [ ] Observed the **deployed** artifact, not only pre-packaging outputs.

### Choosing a solution

- [ ] Checked against minimum supported JDK of the product and dependency.
- [ ] Distinguished between upgrading runtime, changing dependency, and recompiling source-owned artifacts.
- [ ] Checked Maven/Gradle BOM/platform alignment.
- [ ] Did not downgrade a library without reviewing ABI and CVEs.
- [ ] Did not manually edit class-file headers to “downgrade bytecode”.
- [ ] Configured `--release`/compiler toolchain appropriately for generated/application classes.
- [ ] Checked plugin/JUnit/agent ASM parser support if the error belongs to tooling.
- [ ] Checked preview flags per exact release, not using them to bypass major mismatches.

### Verification

- [ ] Scanned class-file headers of the actually deployed artifact and dependencies.
- [ ] Tested on the minimum runtime JDK.
- [ ] Exercised code paths that load optional/lazy/plugin providers.
- [ ] Ran unit, integration, contract, and packaged smoke tests.
- [ ] Checked Java agents, native libraries, and application server when relevant.
- [ ] Confirmed security/support policy and vendor compatibility.
- [ ] Recorded checksum, selected version, root cause, and rollback.
- [ ] Saved a CI guardrail to detect bytecode drift later.

**Conclusion:** `UnsupportedClassVersionError` is a very specific symptom: a JVM does not accept a class-file version it must load. Yet the rejected target can be **any class in the runtime/build/test graph**, not necessarily code the project just compiled. Effective diagnosis begins by **reading major/minor, verifying the right JVM, locating the exact class and artifact, distinguishing the JVM loader from ASM/tooling parsers, and then inspecting the dependency graph and classloader**. Only then should you choose to upgrade the JDK runtime, switch to a supported dependency release, or recompile the artifact that actually needs fixing. This approach reduces the risk of fixing at the wrong layer and produces clear evidence for each step of Java compatibility migration.
