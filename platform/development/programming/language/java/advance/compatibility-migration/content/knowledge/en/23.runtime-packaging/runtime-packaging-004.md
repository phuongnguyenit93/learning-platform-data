# Multi-Release JAR: META-INF/versions Structure and Class Selection

In **Java Advance Compatibility Migration**, there are libraries that must continue running on Java 8 or Java 11 while wanting to use newer APIs, optimization mechanisms, or better ways of interacting with the JDK when an application runs on Java 17, 21, or newer releases. Publishing a separate JAR for each JDK increases operational cost, yet compiling the entire library for newer Java causes old JDK users to encounter class-loading errors.

**Multi-release JAR (MRJAR)** is a mechanism introduced in **Java 9 under JEP 238** that allows a single JAR to contain a **base implementation** alongside alternate class/resource versions intended for higher Java releases. When a runtime or MRJAR-supporting tool accesses a class, it can select an entry under `META-INF/versions/<N>/` appropriate for the Java runtime instead of always using the entry at the root of the JAR.

An MRJAR is **not** a mechanism that automatically converts an entire library to a newer JDK, nor is it a form of shading or arbitrarily changing the public API. It is a **packaging convention with a manifest and version-selection rules**, helping maintain a shared API contract while providing specialized logic implementations for different JDKs.

This lesson explains archive structure, the class-selection algorithm, the `Multi-Release: true` manifest attribute, compiling with the proper class-file version, a Java example that runs across multiple JDKs, how to build with `javac`/`jar` and organize Gradle/Maven, its relationship with JPMS, risks for class loaders and tools, and a testing strategy when upgrading JDKs.

## 1. The Problem Multi-Release JARs Solve

Suppose a data-encoding library must run on **Java 8**, yet when running on **Java 17** wants to use `java.util.HexFormat`, added in Java 17, to implement converting bytes into a hex string.

If written directly as:

~~~java
import java.util.HexFormat;

public final class HexCodec {
    public static String encode(byte[] input) {
        return HexFormat.of().formatHex(input);
    }
}
~~~

and compiled with Java 17, the artifact cannot be used as-is on Java 8: the class file version and platform APIs do not match the older runtime.

There are alternative solutions:

- Use only Java 8 APIs for all runtimes, giving up specialized implementations.
- Publish separate artifacts such as `hex-codec-java8.jar` and `hex-codec-java17.jar`.
- Use reflection/`MethodHandle`/runtime feature detection to call the newer API if present.
- Create a **multi-release JAR**: one shared API, a Java 8 base implementation, and a Java 17 alternate implementation.

MRJAR fits when a library has the **same public contract**, yet needs optimized implementations or different integrations per JDK.

### 1.1. One JAR, Multiple Implementations

~~~text
               hexcodec-mr.jar
                       |
         +-------------+--------------+
         |                            |
         v                            v
  Base class (Java 8)       Java 17 class override
  com/example/HexCodec     META-INF/versions/17/
                            com/example/HexCodec
         |                            |
         +-------------+--------------+
                       |
                       v
                  Java runtime
        Choose suitable implementation
~~~

A physical JAR can contain multiple class files with the same logical name at **different archive paths**. This is an intentional structure, not two classes with the same name inside the same package directory.

### 1.2. Not Every Library Needs an MRJAR

If a library can use a single stable Java 8 implementation with minimal code and acceptable performance, keeping one code path is usually simpler. MRJAR adds build, testing, scanning, debugging, and maintenance costs. Only adopt it when the benefits of JDK-specific implementations justify the cost.

## 2. Fundamental Concepts

| Term | Meaning |
|---|---|
| Base entry | A class/resource at the regular path of the JAR |
| Versioned entry | An alternate entry under `META-INF/versions/N/` |
| Versioned directory | A directory named with a Java version number such as `9`, `11`, `17`, `21` |
| Multi-Release manifest attribute | The `Multi-Release: true` attribute in the main section of the manifest |
| Runtime feature version | The Java release number of the runtime, for example 17 or 21 |
| Class-file major version | The bytecode format version number, for example 61 for Java 17 |
| Logical resource name | The requested class/resource name such as `com/example/HexCodec.class` |
| Physical ZIP entry | The actual path inside the JAR, for example `META-INF/versions/17/com/example/HexCodec.class` |
| Version-aware lookup | The mechanism for finding an entry according to MRJAR rules |
| Base fallback | Using the root entry if no suitable override exists |

**Java feature release** (17) and **class-file major version** (61) are two different numbers. The `META-INF/versions/17/` directory uses **17**, not **61**.

## 3. Standard Directory Structure of a Multi-Release JAR

Example of an archive:

~~~text
hexcodec-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── com/
│       │       └── example/
│       │           └── codec/
│       │               └── HexCodec.class
│       └── 17/
│           └── com/
│               └── example/
│                   └── codec/
│                       └── HexCodec.class
├── com/
│   └── example/
│       └── codec/
│           └── HexCodec.class
└── README.txt
~~~

Meaning:

- `com/example/codec/HexCodec.class`: the base version, used when no suitable override exists.
- `META-INF/versions/11/com/example/codec/HexCodec.class`: the version for Java 11 and above until a higher suitable version exists.
- `META-INF/versions/17/com/example/codec/HexCodec.class`: the version for Java 17 and above until a higher suitable version exists.
- `META-INF/MANIFEST.MF`: carries the marker indicating the archive is processed as an MRJAR.
- Classes without an override continue to be loaded from the base path.

### 3.1. Each Class Can Have a Different Set of Versions

It is not mandatory for every class to have an override in every directory:

~~~text
com/example/A.class
com/example/B.class

META-INF/versions/11/com/example/A.class
META-INF/versions/17/com/example/B.class
~~~

On Java 17, `A` can be selected from version 11, while `B` is selected from version 17. **The selection rule applies per requested class/resource name**, rather than there being a “single version for the entire JAR”.

### 3.2. Version Directory Numbers Are Not Arbitrary

The versioned directory structure uses release numbers from **9 onward**, such as `9`, `11`, `17`. Do not use names like `java17`, `jdk-17`, `61`, or `8` as an MRJAR directory version under the standard convention.

If you need to support Java 8, the Java 8 version must reside **at the root of the JAR**, not inside `META-INF/versions/8`.

## 4. Manifest: The Condition to Enable Multi-Release Mode

An MRJAR must declare in the **main section** of `META-INF/MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

The trailing blank line indicates the end of the section according to the manifest format. When using build tools, manifest entries can be generated automatically.

A JAR containing a `META-INF/versions/17` directory **but missing the `Multi-Release: true` attribute** is not treated as an MRJAR by default in normal class loading. A Java class loader may see only the base class; entries under the versioned directory remain ordinary ZIP files under their physical names.

### 4.1. Use the Exact Name and Value

The attribute name is `Multi-Release`, and the enabling value is `true`. It is best to use the `jar` tool, Maven JAR Plugin, or Gradle `Jar.manifest` to generate the attribute rather than editing the manifest file manually after the archive is packaged.

### 4.2. The Manifest Does Not Replace Class Content

Enabling `Multi-Release: true` does not automatically create version-specific classes. If only base entries exist, the JAR still runs using the base. The mechanism only takes effect when valid versioned entries exist in the archive.

### 4.3. Do Not Confuse with Automatic-Module-Name

`Automatic-Module-Name` is an attribute specifying an automatic module name in JPMS. It does not enable MRJAR and does not replace `Multi-Release: true`.

A single JAR can have both:

~~~text
Manifest-Version: 1.0
Multi-Release: true
Automatic-Module-Name: com.example.codec

~~~

The two attributes address two different concerns: **per-JDK implementation selection** and **module identification**.

## 5. Class Selection Rules by Runtime Version

When a class/resource is requested through an MR-aware mechanism, the runtime evaluates versioned entries according to these rules:

1. Determine the Java runtime feature version, for example 17.
2. Search for the version matching the logical entry name in the versioned directory with **the largest N not exceeding the runtime version**.
3. If no suitable override exists, use the base entry.
4. If multiple overrides exist at eligible N values, select **the largest N**.
5. An entry whose N is higher than the runtime is not used as an implementation for a lower runtime.

Example with base, Java 11, and Java 17:

| Runtime | Selected Class |
|---|---|
| Java 8 | `com/example/codec/HexCodec.class` (base) |
| Java 9 | Base (no override for 9) |
| Java 10 | Base |
| Java 11 | `META-INF/versions/11/.../HexCodec.class` |
| Java 16 | Version in `versions/11` |
| Java 17 | Version in `versions/17` |
| Java 21 | Version in `versions/17` if no suitable 18–21 version exists |

**There is no bytecode interpolation or recompilation.** Java 16 simply selects the class packaged at version 11; Java 21 can select the version 17 class without automatically upgrading it into Java 21 code.

### 5.1. Selection Pseudocode

~~~text
function resolve(logicalName, runtimeVersion):
    for version from runtimeVersion down to 9:
        candidate = "META-INF/versions/" + version + "/" + logicalName
        if candidate exists and versioned entry is applicable:
            return candidate

    return logicalName at JAR root
~~~

The pseudocode explains the principle; it does not accurately represent all caching, module/classloader behavior, resource behavior, security checks, and implementation details in the JVM.

### 5.2. Without an Alternate Class, Base Is Used

If `Order.class` only resides at the root, a Java 21 runtime still loads the base. An MRJAR can optimize just a few classes instead of duplicating the entire library.

### 5.3. The Runtime Will Not Use a Version Higher Than Its Capability

Java 11 does not pick `versions/17/...` merely because it is newer in the archive. The MRJAR mechanism intentionally prevents a lower runtime from reading classes written for a higher release.

## 6. Class Selection Differs from Artifact Version Selection

MRJAR is not Maven/Gradle dependency resolution.

~~~text
Maven/Gradle selects:
  org.example:hexcodec:1.2.0
                   |
                   v
             One JAR artifact
                   |
             Class loader / JVM
                   |
                   v
     Select base / versions/11 / versions/17
~~~

The build tool selects **one artifact version** such as `1.2.0`. Inside that artifact, the JVM can choose the implementation suited to the runtime. Replacing `hexcodec:1.2.0` with `hexcodec:1.3.0` changes the dependency version; loading `versions/17` instead of base happens **inside the same artifact**.

This matters when debugging: two environments using **the exact same JAR checksum** can still execute **different class bytecode** if their JDK runtimes differ.

## 7. Practical Runnable Example: Same API, Different Implementations

Let us build a `HexCodec` library with the same API:

~~~java
public static String encode(byte[] input)
public static String implementation()
~~~

The base version compiles for Java 8, while the Java 17 version uses `java.util.HexFormat`.

### 7.1. Planned Source Structure

~~~text
hexcodec-example/
├── manifest.mf
├── src/
│   ├── base/
│   │   └── com/example/codec/HexCodec.java
│   ├── java17/
│   │   └── com/example/codec/HexCodec.java
│   └── app/
│       └── com/example/app/Main.java
└── build/
    ├── classes-base/
    ├── classes-17/
    ├── app/
    └── hexcodec-mr.jar
~~~

**Note:** The two Java files share the same package/class name, so they **must not be compiled together as two source files in the same `javac` invocation**. They belong to two separate source trees/compilation tasks.

### 7.2. Base Implementation for Java 8

File `src/base/com/example/codec/HexCodec.java`:

~~~java
package com.example.codec;

public final class HexCodec {

    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexCodec() {
    }

    public static String encode(byte[] input) {
        StringBuilder result = new StringBuilder(input.length * 2);

        for (byte b : input) {
            int value = b & 0xff;
            result.append(HEX[value >>> 4]);
            result.append(HEX[value & 0x0f]);
        }

        return result.toString();
    }

    public static String implementation() {
        return "base-java8";
    }
}
~~~

This code uses only Java SE APIs and syntax compatible with Java 8.

### 7.3. Alternate Implementation for Java 17

File `src/java17/com/example/codec/HexCodec.java`:

~~~java
package com.example.codec;

import java.util.HexFormat;

public final class HexCodec {

    private HexCodec() {
    }

    public static String encode(byte[] input) {
        return HexFormat.of().formatHex(input);
    }

    public static String implementation() {
        return "java17-hexformat";
    }
}
~~~

Both versions have **the same public class**, the same package name, and the same public static method signatures. The implementation changes, yet consumers do not have to import a different package.

### 7.4. Consuming Application

File `src/app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.codec.HexCodec;

public final class Main {

    public static void main(String[] args) {
        byte[] input = new byte[] { 0, 15, -1 };

        System.out.println(HexCodec.encode(input));
        System.out.println(HexCodec.implementation());
    }
}
~~~

The `encode` output in both versions must be:

~~~text
000fff
~~~

The `implementation` line merely demonstrates which class the runtime selected; a production library normally does not need to expose such a method publicly.

## 8. Compiling Two Source Trees with `javac`

Command examples use Unix/Linux/macOS style or a shell with equivalent tools. Source directories must be created following the layout above.

### 8.1. Compiling the Base Version for Java 8

Use a JDK recent enough to support `--release 8`:

~~~bash
mkdir -p build/classes-base build/classes-17 build/app

javac --release 8 \
  -d build/classes-base \
  src/base/com/example/codec/HexCodec.java
~~~

`--release 8` lets the compiler restrict **syntax, class-file target, and Java SE APIs** to Java 8, rather than only setting `-target 8` while accidentally referencing newer Java APIs.

If the project uses a very new toolchain, always verify the `javac` release list still supports the legacy target required by your organization.

### 8.2. Compiling the Java 17 Version

~~~bash
javac --release 17 \
  -d build/classes-17 \
  src/java17/com/example/codec/HexCodec.java
~~~

This version is allowed to use `HexFormat` because the API has existed since Java 17. Do not allow the base class to reference `HexFormat` or any version 17 class in static initializers/constant pools along code paths required on Java 8.

### 8.3. Checking the Class-File Major Version

~~~bash
javap -verbose \
  -classpath build/classes-base \
  com.example.codec.HexCodec
~~~

Expected base:

~~~text
major version: 52
~~~

Similarly:

~~~bash
javap -verbose \
  -classpath build/classes-17 \
  com.example.codec.HexCodec
~~~

Expected Java 17:

~~~text
major version: 61
~~~

Major 52 corresponds to Java 8; major 61 corresponds to Java 17. The class-file major version and the version directory number are not the same value.

## 9. Packaging with the `jar` Tool and Manifest

Create `manifest.mf`:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

After compiling both source trees, you can use the JDK `jar` tool supporting the multi-release option:

~~~bash
jar --create \
    --file build/hexcodec-mr.jar \
    --manifest manifest.mf \
    -C build/classes-base . \
    --release 17 \
    -C build/classes-17 .
~~~

Meaning:

- `--create` creates a new archive.
- `--file` specifies the artifact.
- `--manifest` supplies the manifest containing `Multi-Release: true`.
- `-C build/classes-base .` places base classes at the JAR root.
- `--release 17` switches subsequent packaging into `META-INF/versions/17/`.
- `-C build/classes-17 .` adds Java 17 classes into the versioned area.

This syntax illustrates the `jar --release` capability of modern JDKs. Across different JDKs/tools, check `jar --help`, manifest output, and actual archive contents.

### 9.1. Inspecting Archive Contents

~~~bash
jar --list --file build/hexcodec-mr.jar
~~~

Relevant entries should include:

~~~text
META-INF/MANIFEST.MF
com/example/codec/HexCodec.class
META-INF/versions/17/com/example/codec/HexCodec.class
~~~

If `META-INF/versions/17` is missing, the Java 17 version was not included in the archive or the packaging task ran incorrectly.

### 9.2. Validating a Multi-Release JAR

The JDK `jar` tool includes a multi-release JAR validation feature:

~~~bash
jar --validate --file build/hexcodec-mr.jar
~~~

Validation can detect certain structural/API consistency violations. It **does not replace** contract tests, behavioral checks, or actually running on multiple JDKs.

### 9.3. The Manifest Must Have the Activation Marker

Even when versioned files are present, verify that the manifest included in the archive by the build contains `Multi-Release: true`.

Some build plugins generate or merge manifests automatically, so do not just look at `manifest.mf` in the source tree and assume the archive preserved it unchanged.

## 10. Compiling the Consuming Application and Running Tests

Compile `Main` against the Java 8 API of the MRJAR:

~~~bash
javac --release 8 \
  -classpath build/hexcodec-mr.jar \
  -d build/app \
  src/app/com/example/app/Main.java
~~~

On Unix systems, use `:` to separate the classpath:

~~~bash
java \
  -classpath "build/app:build/hexcodec-mr.jar" \
  com.example.app.Main
~~~

On Windows, the classpath separator is typically `;`:

~~~powershell
java -classpath "build/app;build/hexcodec-mr.jar" com.example.app.Main
~~~

### 10.1. Illustrative Output When Running on Java 8

~~~text
000fff
base-java8
~~~

Java 8 lacks MRJAR-aware loading, so it uses the base entry like an ordinary JAR.

### 10.2. Illustrative Output When Running on Java 17

~~~text
000fff
java17-hexformat
~~~

When JDK 17 supports MRJAR and reads valid attributes/entries, `HexCodec` is loaded from `META-INF/versions/17`.

### 10.3. When Running on Java 21

If the archive has no suitable `versions/18`, `versions/19`, `versions/20`, or `versions/21`, Java 21 can continue using the `versions/17` entry.

### 10.4. Results Must Be Verified on Real Runtimes

The outputs above are **expected example outputs**, not results already executed on the learner's machine. You must test using real JDK 8/17/21 runtimes in the corresponding supported environment, rather than merely changing `JAVA_HOME` in an unrelated shell.

## 11. Precedence When Multiple Overrides Exist

Suppose a library contains:

~~~text
com/example/Feature.class

META-INF/versions/9/com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

Under an MR-aware mechanism:

| Java Runtime | Selected Class |
|---|---|
| Java 8 | Base |
| Java 9 | Version 9 |
| Java 10 | Version 9 |
| Java 11 | Version 11 |
| Java 16 | Version 11 |
| Java 17 | Version 17 |
| Java 20 | Version 17 |
| Java 21 | Version 21 |
| Java 25 | Version 21, if no higher suitable version exists |

**The runtime picks the largest N that does not exceed its own feature version**. It does not always pick the nearest Java release by filename, nor does it pick the entry with the “highest class-file major version that the classloader tries to read”.

### 11.1. Why Does Java 16 Pick Version 11 Instead of Base?

Because `11 ≤ 16` and there are no overrides for versions 12–16. A newer Java feature release can inherit an implementation specialized for an older release that remains valid.

### 11.2. Intermediate Milestones Can Be Omitted

A JAR having only `versions/17` is still valid when the base provides the API for runtimes below 17. You do not need to create directories `9, 10, 11, ..., 16` just to “fill in the numbers”.

## 12. Class-File Versions and Compilation Requirements

Numbers to distinguish:

| Java release | MRJAR directory | Class-file major |
|---|---|---:|
| Java 8 | Base JAR root | 52 |
| Java 9 | `META-INF/versions/9` | 53 |
| Java 11 | `META-INF/versions/11` | 55 |
| Java 17 | `META-INF/versions/17` | 61 |
| Java 21 | `META-INF/versions/21` | 65 |
| Java 25 | `META-INF/versions/25` | 69 |

A version-specific class must be compiled for the release represented by its directory or a lower compatible release according to MRJAR/packaging rules; in practice, set **`--release N` for source tree version N** to avoid accidentally using newer Java APIs.

Invalid example:

~~~text
META-INF/versions/11/com/example/Feature.class
    but the class file was compiled for Java 17 (major 61)
~~~

A Java 11 runtime may select the version 11 entry and then fail to load the class because the bytecode is too new. This is a severe packaging bug and cannot be fixed by “opening a module” or altering the manifest.

### 12.1. Use `--release` Instead of Only `-source`/`-target`

`-source` controls syntax; `-target` controls bytecode target. Some older setups run a newer JDK compiler with `-source 8 -target 8`, which still allows referencing newer Java SE APIs and breaks on a Java 8 runtime.

`--release 8` controls the platform API baseline as well, avoiding many errors of this kind.

### 12.2. Annotation Processors and Generated Code

If version-specific sources use annotation processors, separate outputs for each compilation and ensure generated classes land in the proper base/versioned directories. Never allow files generated for Java 17 to leak into the base tree.

## 13. Keeping the API Contract Consistent Across Versions

A common goal of MRJAR is to **replace the implementation while keeping equivalent public/protected APIs** between base and versioned classes.

Base API example:

~~~java
public final class HexCodec {
    public static String encode(byte[] input) { /* ... */ }
}
~~~

If the Java 17 version changes to:

~~~java
public final class HexCodec {
    public static byte[] encode(byte[] input) { /* ... */ }
}
~~~

then **the return type has changed**, and source/binary clients can break. This is inappropriate for using MRJAR to maintain a stable library API.

By design, preserve:

- Exposed fully qualified class names.
- Compatible public/protected constructors and methods.
- Promised field contracts and inheritance/interfaces.
- Exception semantics according to the API contract.
- Serialization/protocol/data formats.
- Critical behavior that consumers rely upon.

### 13.1. Identical Public APIs Do Not Guarantee Identical Behavior

Two implementations of `HexCodec.encode` may share the exact signature yet differ in how they handle null, UTF-8, casing, or error behavior. `jar --validate` does not prove equivalent outputs.

Therefore, run the **same contract test suite** on a runtime selecting base and on runtimes selecting overrides.

### 13.2. Internal Helpers Can Be Specialized

A versioned implementation can have its own private/package-private helpers to leverage newer JDKs, provided packaging rules are respected and the public API is unbroken. They must be packaged in the right versioned tree and never accidentally referenced by the base implementation.

### 13.3. Maintaining Binary Compatibility

In practice, consumers may have been compiled on Java 8 yet run on Java 17. If the versioned class deletes a public method required by consumer bytecode, `NoSuchMethodError` can occur at runtime.

Do not judge compatibility solely by recompiling every consumer on a newer JDK; test **older-compiled clients** as well if the library requires it.

## 14. Multi-Release JAR Is Not a Library with Different Public APIs per JDK

A tempting shortcut is adding a public API `newFeatureOnlyOnJava17()` in `versions/17` while omitting it from the base. This causes problems:

- Java 8 clients cannot see the API.
- Compilers may emit code referencing an API that does not exist when running on a lower JDK.
- `jar --validate` or API consistency tools may warn or reject the mismatch.
- Library documentation becomes runtime-dependent.
- Reflection frameworks or tooling may observe different APIs depending on the environment.

It is better to keep **one stable public facade**, controlling implementations via MRJAR. If distinct APIs per JDK are genuinely needed, consider publishing separate modules/artifacts or defining an explicit contract for supported versions.

## 15. Versioned Resources: Not Just `.class` Files

MRJAR permits version-specific resources in the appropriate structure when the runtime uses an MRJAR-aware resource lookup mechanism.

Example:

~~~text
com/example/codec/defaults.properties
META-INF/versions/17/com/example/codec/defaults.properties
~~~

In some MR-aware access paths, looking up the logical name `com/example/codec/defaults.properties` can select the version 17 resource on Java 17.

However, distinguish between:

- Resource lookup via class loader/JAR APIs that support MRJAR.
- Opening the physical file with `ZipFile` or ordinary unzip tools.
- Iterating ZIP entries with an external scanner.
- A framework implementing its own custom resource loader without applying MRJAR rules.

**Do not assume every ZIP-reading library or resource framework performs version selection like the JVM class loader.** Check the exact API consuming the resource.

### 15.1. Configuration and Sensitive Resources

Do not use versioned resources to covertly change secrets, connection endpoints, or security policies per JDK without clear ownership. One JAR with the exact same checksum reading different configuration on different runtimes is a hard-to-observe source of bugs.

### 15.2. `META-INF` Has Special Rules

Much of the metadata in `META-INF`, such as manifests, signatures, and service provider configurations, follows separate rules; **do not assume every entry in `META-INF` can be versioned simply by copying it into `versions/N/META-INF/`**.

As a common example, `META-INF/services/...` is service configuration metadata at the JAR root; do not assume placing it under the versioned tree will be handled by `ServiceLoader` like class files. If JDK-specific providers are needed, design provider classes and service registration according to the relevant specification/tooling, then test directly.

## 16. Class Loaders and Archive Access APIs

MRJAR selection rules are implemented in supporting Java mechanisms. Not every way of accessing a ZIP behaves the same.

| Access Method | What to Note |
|---|---|
| Standard Java application class loading on an MRJAR-supporting JDK | Can select the appropriate versioned class |
| `java.util.jar.JarFile` with runtime-version-aware constructor | Capable of looking up logical entries according to the chosen version |
| Plain `ZipFile`/ZIP enumeration | Sees physical ZIP entries; does not automatically have the same class resolution semantics |
| `jar --list` | Lists physical entries; does not imply selecting an override for execution |
| Custom class loader | Must verify whether its implementation is MR-aware |
| Nested JAR loader in an executable framework | Must check framework loader/version support for MRJAR |
| Bytecode scanning/annotation scanning | May read base, all versions, or a variant depending on the tool |
| Native-image/AOT build pipeline | Build-time and runtime class selection must be verified separately |

Some custom class loaders read bytes directly from `ZipFile` and invoke `defineClass`. If that code only looks up `com/example/Feature.class` at the JAR root, it may ignore overrides even when the manifest is valid.

### 16.1. `JarFile` Supports Version Selection on Open

Java provides the `JarFile` API for working with multi-release archives. Illustrative code on a modern JDK:

~~~java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;

public final class InspectMrJar {

    public static void main(String[] args) throws Exception {
        File archive = new File("build/hexcodec-mr.jar");

        try (JarFile jar = new JarFile(
                archive,
                true,
                ZipFile.OPEN_READ,
                Runtime.version())) {

            System.out.println("MRJAR = " + jar.isMultiRelease());

            JarEntry entry =
                    jar.getJarEntry("com/example/codec/HexCodec.class");

            System.out.println(entry == null
                    ? "not found"
                    : entry.getName());
        }
    }
}
~~~

The constructor taking `Runtime.Version` demonstrates **explicitly selecting a version context** when working with an MRJAR. Understand behavior for the specific JDK/version/API in use, especially when tools open archives using different constructors/ZIP APIs.

### 16.2. Why Does `jar tf` Always List Both Base and Versions?

`jar tf` shows the contents of the archive; it is not a JVM running business code. Seeing both `com/example/Feature.class` and `META-INF/versions/17/com/example/Feature.class` in the listing is normal.

## 17. Observing Which Class Is Selected at Runtime

When you need to know which implementation was loaded on a real runtime, you can:

- Add a test-only diagnostic method such as `implementation()` in the example.
- Use JVM class loading logs.
- Record JDK vendor/version and JAR checksum.
- Use `javap` or bytecode readers against individual physical entries.
- Inspect the class loader and code source location.
- Run behavioral contract tests on specific JDKs.

Example enabling class loading logs on modern Java:

~~~bash
java -Xlog:class+load=info \
  -classpath "build/app:build/hexcodec-mr.jar" \
  com.example.app.Main
~~~

`-Xlog` is the logging mechanism of modern JVMs and is not Java 8 compatible syntax. On Java 8, use different logging flags if needed. Do not keep overly broad logging enabled in production for extended periods as it can generate large amounts of data.

### 17.1. `CodeSource` Location Does Not Always Point to the Physical Versioned Entry

A class may be reported as loaded from the JAR path, yet logs or `ProtectionDomain.getCodeSource()` do not necessarily display `META-INF/versions/17` as a physical path. Depending on class loader/JAR URL semantics, the location may simply be the archive itself.

Therefore, to prove an override was selected, use behavioral tests or tools inspecting the actual entry bytes rather than relying solely on a code source URL.

## 18. MRJAR and JPMS (Java Platform Module System)

Java 9 introduced **JPMS** alongside MRJAR. The two features complement each other but are not the same.

A library can:

1. Be an MRJAR on the classpath without `module-info.class`.
2. Be an MRJAR placed on the module path as an automatic module if no explicit descriptor is present.
3. Have a suitable `module-info.class` to become an explicit module on Java 9+.
4. Have a module descriptor in the versioned tree under certain MRJAR layouts supporting Java 8 and Java 9+ compatibility.

### 18.1. Why Place `module-info.class` in Version 9?

Java 8 does not understand JPMS. A library wanting to keep Java 8 base classes while supplying a module descriptor for Java 9+ can structure it as:

~~~text
com/example/codec/HexCodec.class
META-INF/versions/9/module-info.class
META-INF/MANIFEST.MF
~~~

When using a proper MRJAR structure, Java 9+ on the module path can pick up the module descriptor through mechanisms supported by the module system, while the Java 8 classpath only processes base classes.

This requires proper packaging/toolchain support and adherence to compatibility constraints. Do not place `module-info.class` anywhere arbitrarily and assume the module system will understand it.

### 18.2. `module-info.class` Is Not a Business Class Replacement

A module descriptor describes the module name, `requires`, `exports`, `opens`, and other directives. It is module metadata, not an alternate implementation for `HexCodec`.

### 18.3. Classpath and Module Path Differ

The classpath generally places classes in the unnamed module, whereas the module path enforces module resolution and access rules. An MRJAR may run fine on the classpath yet encounter `requires`/`exports`/`opens` issues on the module path.

In a Java 8 → Java 17 migration, test both deployment modes if the product supports both. Do not use MRJAR to forcefully bypass module encapsulation rules.

## 19. API Contracts and Module Descriptors

A Java 17 version of a library can use specialized private implementations, but module exports and services must stay consistent with the API promised to consumers.

When JPMS is present:

- Public packages usually must be properly exported via `exports`.
- Reflection frameworks may need appropriate `opens`.
- Versioned libraries introducing new dependencies must examine `requires` and module resolution.
- Split packages across modules can still be a blocker.
- Service binding may use `uses`/`provides` in the descriptor.

If a versioned entry uses a library absent from the module graph or improperly declared, class loading can fail even if the archive contains the right entry.

**MRJAR solves entry selection; it does not automatically ensure module graph validity.**

## 20. Using MRJAR to Support Libraries on Newer JDKs

A realistic case in Java Compatibility Migration is legacy code that relied on internal implementations:

~~~text
Base: logic working on Java 8
Java 11: use new API to avoid legacy workaround
Java 17: use new public API instead of old reflection operations
~~~

One design direction:

~~~text
PublicFacade (shared contract)
       |
       +-- Base implementation: Java 8 compatible
       |
       +-- META-INF/versions/11: implementation for Java 11+
       |
       +-- META-INF/versions/17: implementation for Java 17+
~~~

There is no need to add an overlay for every release. Create one only where a real difference is necessary.

### 20.1. When Not to Use MRJAR to “Rescue” an Old Library

MRJAR cannot fix:

- Another dependency that is unmaintained and runtime-incompatible.
- Public API changes in a library that cannot be kept consistent.
- Missing modules/dependencies in the runtime required by the versioned implementation.
- Protocol/serialization changes with altered semantics.
- Security issues caused by weak APIs/ciphers if the old version is still distributed and executed.
- A custom class loader that does not support MRJAR.
- Frameworks that do not support the archive format or shading that breaks the layout.

If only Java 17 and above are supported, sometimes it is simpler to **raise the baseline of the entire library** rather than retaining a Java 8 base and multiple variants.

## 21. Building with Gradle: Organizing Source Sets and Tasks

Gradle does not automatically treat `src/java17` as a source tree destined for `META-INF/versions/17` merely because the project uses a Java toolchain. You must configure compilation and packaging explicitly or use a reliable plugin.

A Groovy DSL example illustrating the approach:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// Code in src/main/java is the base, Java 8 compatible.
tasks.named('compileJava', JavaCompile) {
    options.release = 8
}

def compileJava17 = tasks.register('compileJava17', JavaCompile) {
    dependsOn(tasks.named('compileJava'))

    source = fileTree('src/java17/java') {
        include '**/*.java'
    }

    classpath = files(sourceSets.main.output)
    destinationDirectory = layout.buildDirectory.dir('classes/java17')

    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }

    options.release = 17
}

tasks.named('jar', Jar) {
    dependsOn(compileJava17)

    manifest.attributes('Multi-Release': 'true')

    into('META-INF/versions/17') {
        from(compileJava17.flatMap { it.destinationDirectory })
    }
}
~~~

This example assumes a Gradle version providing the corresponding `toolchain`, `destinationDirectory`, `tasks.named`, and provider-mapping APIs. Depending on the Gradle wrapper, task declarations and configuration may need adjustment.

### 21.1. Why Separate Compilations Are Needed

If Java 17 sources are placed directly in `sourceSets.main.java`, the compiler will see **two classes with the same fully qualified name** (base and Java 17 `HexCodec`), causing a duplicate class error.

Therefore:

- Base tree goes into `src/main/java`.
- Java 17 tree goes into `src/java17/java`.
- The two compilations have separate destination directories.
- The `jar` task places Java 17 classes into the versioned path.
- The manifest marks the JAR as an MRJAR.

### 21.2. Avoiding Compiler Classpath “Looking at the Wrong” Implementation

When compiling a versioned implementation, the base output may be needed on the classpath to inherit utility/public contracts, yet overlay outputs must not be reused by build tooling as base sources. Dependency flows must be clear to prevent cycles or accidental joint compilation.

### 21.3. Gradle Tests Must Run Against the Actual JAR

By default, Gradle `test` may use compiled class directories from the source set rather than the final packaged JAR. If the goal is to verify MRJAR **runtime selection**, a dedicated integration test against the **packaged JAR** on the respective JDK 8/11/17/21 runtimes is needed.

If tests only run against `build/classes/java/main`, they may always execute the base implementation even on a Java 17 runtime, yielding misleading results about MRJAR behavior.

## 22. Maven: Manifest and Compiling Versioned Sources

In Maven, a multi-step configuration is usually required:

1. Compile base sources using `--release 8`.
2. Compile Java 17 overlay sources using `--release 17` into a separate output or appropriate versioned layout.
3. Place overlay files into `META-INF/versions/17` inside the JAR.
4. Write `Multi-Release: true` into the manifest.
5. Validate the archive and run integration tests across multiple JDKs.

Maven JAR Plugin example setting the manifest attribute:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifestEntries>
                <Multi-Release>true</Multi-Release>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
~~~

**This fragment only configures the manifest; it does not yet compile the Java 17 source tree or move files into the versioned directory.**

Depending on the Maven Compiler Plugin version, you can use multi-release output features or configure separate compilation executions combined with resources/assembly steps. Consult the documentation of the plugin version in use, especially for multi-module builds and generated sources.

### 22.1. Do Not Compile Both Source Trees into `target/classes` Root

If both versions of `com.example.codec.HexCodec` are compiled into `target/classes/com/example/codec`, the later one can overwrite the earlier one. The artifact either loses a valid base entry for Java 8 or loses its override.

Each JDK variant needs a separate output path prior to packaging.

### 22.2. Maven Test Classpath Is Not the JAR Runtime

Like Gradle, Maven unit tests may use `target/classes` directly. To test overlay selection, run integration tests or a Java process using the **packaged JAR artifact** under each target JDK runtime.

## 23. When an Ordinary Gradle/Maven Artifact Is Enough

Not every multi-JDK library needs an MRJAR. Options may include:

| Strategy | Advantages | Drawbacks |
|---|---|---|
| Single JAR compiled for lowest Java | Simple, fewer test variants | Cannot directly use newer APIs in the implementation |
| MRJAR | Single artifact, per-JDK implementations | More complex build/test/tooling |
| Separate artifacts by classifier | Version selection handled by build/dependency management | Consumers must select the right variant |
| Raising the Java baseline | Fewer code paths, leverages newer JDKs | Drops consumers on older JDKs |
| Reflection/feature detection | Can keep a single base class file | Harder to read/debug, runtime checks, access issues |
| Service-based abstraction | Separates implementations via SPI | Extra wiring and dependency management |

Choose MRJAR when there is a clear reason to maintain **a single artifact coordinate** while supporting different JDK versions with specialized APIs/logic.

## 24. MRJAR Inside Fat JARs, Shaded JARs, and Executable JARs

A common failure point is **repackaging** an MRJAR into another artifact.

Example:

~~~text
dependency-hexcodec.jar    (valid MRJAR)
            |
            v
Maven Shade / Gradle Shadow / Spring Boot packaging
            |
            v
application.jar            (different layout/class loader)
~~~

Issues:

- Shade/merge plugins can drop the `Multi-Release: true` manifest attribute.
- Entries under `META-INF/versions` get stripped or flattened.
- Versioned classes get package-relocated inconsistently with the base.
- Duplicate handling picks the wrong class.
- Signatures or checksums of the original JAR become invalid after transformation.
- The framework's nested JAR loader must support selecting the right versioned entry.
- License/CVE analyzers/scanners may inspect all physical classes.

### 24.1. Nested JARs Do Not Guarantee MRJAR Is Intact

Some executable frameworks include class loaders supporting nested libraries with MRJAR semantics. Yet you cannot infer merely from the presence of `META-INF/versions` files in an archive that every custom launcher selects the right class.

Verify the **exact launcher and framework version** with runtime tests; do not merely run `java -cp dependency.jar` and assume the final executable package behaves identically.

### 24.2. Always Inspect the Final Artifact After Shading

Steps:

1. Build the dependency MRJAR properly.
2. Build the shaded/fat JAR.
3. Inspect the physical entries and manifest of the final artifact.
4. Exercise differing runtime logic to verify class selection.
5. Run contract tests on low and high JDKs.
6. Scan signatures, duplicate classes, and dependencies if required by the pipeline.

If shading strips MRJAR semantics, consider preserving nested dependency JARs intact rather than merging classes, or adjust plugin configuration according to its documentation.

## 25. MRJAR and Custom Class Loaders

Web applications, OSGi, plugin engines, application servers, or custom class loaders may load JARs in specialized ways.

Questions:

- Does the loader use an MR-aware `JarFile`/lookup?
- Does the loader read the JAR as a plain ZIP and ignore the manifest?
- Does the loader cache bytes from one runtime and reuse them on another?
- Does child-first/parent-first delegation cause a homonymous class to be loaded from another library?
- Does framework scanning see both base and overrides as separate classes?
- Which JDK is the container running, and does it load artifacts during hot deploy?

If a loader does not apply MRJAR semantics, a Java 17 process may still execute the base class. This situation does not necessarily throw an exception; it can silently prevent **Java 17 optimizations or fixes from activating**, leading to unexpected behavior.

### 25.1. Determining What the Loader Selected

Use a diagnostic test such as `HexCodec.implementation()` or an observable behavioral feature. Do not rely solely on `Class.getResource` or JAR file listings when testing selection, as URL/entry handling can differ.

## 26. Static Analysis, Code Coverage, and Bytecode Tools

MRJAR complicates scanning because an archive contains **multiple physical class files for the same logical class name**.

Example:

~~~text
com/example/codec/HexCodec.class                  (major 52)
META-INF/versions/17/com/example/codec/HexCodec.class (major 61)
~~~

An analyzer might:

- Analyze only base classes.
- Analyze all physical entries.
- Select a variant according to the runtime.
- Fail to understand MRJAR and treat versioned classes as “duplicates”.
- Fail upon encountering a newer class-file major version while the analyzer runs on an older JDK.
- Report different findings per target JDK.

### 26.1. JaCoCo and Instrumentation

If tests run on Java 17 and the JVM loads the versioned implementation, JaCoCo must support the corresponding class-file major version and bytecode constructs. However, if the report task is only fed base classes, coverage mapping can be wrong or missing data.

Explicitly check:

- JaCoCo agent/report versions.
- Test JVM version.
- Loaded physical class variant.
- Class files supplied to the report.
- Version-matched source files.
- Exclusions and aggregate report behavior.

A "100%" report on base classes does not prove the Java 17-specific implementation was tested.

### 26.2. SpotBugs/PMD/Checkstyle

- SpotBugs and bytecode analyzers may need to understand the highest class-file version being scanned.
- PMD/Checkstyle source scanners must understand the source syntax of each variant.
- Custom rules should be tested against each source tree/version if specialized APIs are present.
- Code quality pipelines must know their exact scope so version-specific code is not overlooked.

### 26.3. `jdeps`

`jdeps` is useful for inspecting dependencies and certain JDK internal API references, but you must understand how the tool handles MRJAR:

~~~bash
jdeps --multi-release 17 \
  build/hexcodec-mr.jar
~~~

Depending on JDK/tool version and analysis mode, `--multi-release 17` directs the tool to analyze the variant appropriate for Java 17. For a multi-version JAR, inspect the base variant and all supported target releases, rather than running just a single scan on CI's JDK.

`jdeps` does not fully see reflection with dynamically constructed class name strings or native code.

## 27. Checking with `jar --validate` and Its Limitations

~~~bash
jar --validate --file build/hexcodec-mr.jar
~~~

The tool can validate MRJAR structure and public API consistency according to the rules it supports.

However:

- It does not verify whether implementation logic is correct.
- It does not verify binary/data format compatibility across all dependencies.
- It does not prove the module graph is valid in every configuration.
- It does not prove custom class loaders handle the MRJAR properly.
- It does not scan the library for security vulnerabilities.
- It does not replace runtime tests on Java 8/11/17/21.
- It does not replace API/ABI compatibility regression tests when releasing a new library version.

Treat `jar --validate` as **one structural check layer**, not a certificate that every runtime works.

## 28. MRJAR and `META-INF/services` Resources

The Java service provider mechanism commonly uses files such as:

~~~text
META-INF/services/com.example.spi.CodecProvider
~~~

alongside the corresponding provider class/interface.

Do not assume that placing:

~~~text
META-INF/versions/17/META-INF/services/com.example.spi.CodecProvider
~~~

will make Java 17's `ServiceLoader` automatically prefer the new service configuration. Resource metadata under `META-INF` has dedicated rules, and versioned entries cannot be assumed to form a complete replacement metadata hierarchy.

If different service implementations per JDK are needed:

1. Define a shared SPI contract.
2. Check service registration at the root.
3. Design a provider class or facade with runtime-specific implementations.
4. Test `ServiceLoader` on target JDKs.
5. If using JPMS, verify `uses`/`provides` properly in the module descriptor.
6. Avoid duplicate providers or skewed metadata when shading/merging JARs.

Many applications can solve provider selection with another abstraction instead of attempting to directly version service files.

## 29. Security and Supply Chain When Using MRJAR

An MRJAR can contain multiple implementations, so security scanning tools must cover both base and overlays.

Risks:

- The JDK 8 path and JDK 17 path have different vulnerabilities.
- Security scanners read only the base and miss versioned implementations.
- License scanners skip packages located in versioned directories.
- Hash/signature verification is invalidated during shading.
- Vulnerable legacy code continues to be shipped to keep supporting older JDKs.
- Developers test on Java 17, while Java 11 production selects a different implementation.
- Tooling skips high-version class files, causing incomplete scan results.

A JAR does not automatically become safe just because Java 17-specific code fixed an issue; users on Java 8 may still execute the base path. If the base version carries unacceptable risk, consider **dropping Java 8 support**, changing the API structure, or releasing a separate version with a clear policy.

### 29.1. SBOM and Inventory

An SBOM typically lists artifact coordinates, version, and checksum. For MRJARs, additional metadata can be recorded:

- Minimum supported Java version.
- Versioned directories present in the archive.
- Toolchain/compiler releases used for each tree.
- Security scan coverage per variant.
- Runtime test matrix.
- Maintainer/owner for each implementation path.

Not every SBOM format has dedicated fields for variants, yet build/release documentation can capture supplemental metadata to support audits.

### 29.2. JAR Signing and Modifying Archives

If a JAR has already been signed, altering the manifest or class entries afterward can cause signature verification to fail. Build the complete MRJAR, validate, and test first, then execute signing according to the organization's approved release workflow.

## 30. Reproducible Builds and Provenance

An artifact built from multiple compilations is prone to inconsistent variables:

- Base build runs on one compiler JDK, overlay build on another.
- Source files get copied/overwritten between tasks.
- ZIP entry ordering/timestamps differ across builds.
- Dynamic dependency versions differ across environments.
- Manifest attributes get modified automatically by a plugin.
- Tools build part of an overlay and reuse stale caches.
- Code generation output embeds absolute paths or timestamps.
- Class files differ due to compiler settings.

A solid build pipeline should record:

1. Source Git commit.
2. Build tool wrapper/version.
3. JDK compiler releases for each variant.
4. `--release` flag for each compilation.
5. Dependencies and artifact checksums.
6. Packaging tool/plugin versions.
7. Manifest and archive layout.
8. `jar --validate` result.
9. Test matrix results.
10. Artifact checksum and signing metadata.

When there is a report that "Java 17 selected the wrong class", this information helps distinguish a runtime issue from a mispackaged artifact.

## 31. Performance: Does MRJAR Automatically Make Things Faster?

No. MRJAR only selects an implementation; performance is determined by the implementation and runtime.

A Java 17-specific version may use a more optimal API or reduce reflection overhead. Yet it can also increase allocations, alter GC behavior, or introduce new bugs.

Measure under the same workload:

- Throughput.
- p50/p95/p99 latency.
- CPU utilization.
- Heap allocations and GC.
- Startup/class loading.
- I/O, compression, or cryptographic throughput if relevant.
- Behavior under concurrency.
- Error/timeout rate.

**Do not benchmark against class directories and claim to have measured the versioned implementation.** Run the packaged JAR on the appropriate runtime and verify class selection first.

### 31.1. The JIT Can Make the Base Implementation Good Enough

A base implementation can be well optimized by Java 17's JIT even without using new APIs. Adopting MRJAR should be decided based on benchmarks and compatibility, not on the assumption that “newer Java must have separate code”.

## 32. Maintaining Compatibility When Publishing a Library

When publishing an MRJAR to a Maven repository, consumers can use the same coordinate:

~~~text
com.example:hexcodec:1.4.0
~~~

However, documentation must clearly state:

- Minimum supported Java version.
- Java releases with separate implementations.
- Public API support and policy.
- Whether preview/incubator features are used.
- Whether it depends on different modules/native libraries per runtime.
- Supported test matrix and class loader constraints.
- Deprecation/end-of-support schedule for older runtimes.
- Security patch policy for base and overlays.

Do not expect consumers to guess from the artifact version alone that Java 21 executes a different code path than Java 11.

### 32.1. SemVer Does Not Replace a Runtime Compatibility Statement

Semantic versioning describes API compatibility across artifact releases, whereas an MRJAR also contains **multiple implementation paths inside a single release**. Release testing and versioning policies must account for each runtime path.

## 33. Deployment on Spring Boot, Tomcat, and Application Servers

In Java web deployments, an MRJAR may appear as a dependency in:

- A Spring Boot executable JAR containing nested libraries.
- A WAR's `WEB-INF/lib`.
- A Tomcat/container shared library directory.
- An application server module path.
- A Java agent or instrumentation JAR.

An MRJAR library that works via `java -cp lib.jar` will not necessarily behave identically when loaded by a custom launcher/webapp class loader.

### 33.1. External WAR

A WAR may be deployed onto a Tomcat instance running JDK 17 while local tests used JDK 21. If a dependency MRJAR contains `versions/21`, local runs select version 21 while production selects version 17 (or base). This can change behavior without changing the WAR checksum.

### 33.2. Container Images and JDK Drift

When upgrading a base image from JDK 17 to JDK 21, an application can automatically switch to a different implementation under `META-INF/versions/21` without changing any dependency version. Consequently, image upgrades still require regression testing for MRJAR dependencies.

### 33.3. JPMS and Application Servers

If an environment uses the module path/JPMS, inspect module descriptors and the module graph rather than just classpath selection. Application servers have their own classloading rules that may handle archives differently from a direct Java classpath.

## 34. Common Errors and Diagnostics

| Symptom | Possible Cause | Inspection Priority |
|---|---|---|
| Java 17 still runs base | Manifest missing `Multi-Release: true`, wrong overlay path, custom loader | Manifest, JAR layout, loader, runtime version |
| Java 11 selects base despite Java 17 overlay | Expected behavior per `N ≤ runtime` rule | Should `versions/11` be created? |
| Java 17 throws `NoSuchMethodError` | Overlay public API differs from base or dependency mismatch | `jar --validate`, signatures, runtime graph |
| Java 11 throws `UnsupportedClassVersionError` | Version 11 entry compiled with Java 17 | `javap` major, `--release 11` |
| Java 8 base throws `ClassNotFoundException: java.util.HexFormat` | Base code accidentally references Java 17 API | Compile with `--release 8` and test on Java 8 |
| `jar --validate` reports API inconsistency | Versioned public/protected API differs from base | API signatures and compilation |
| Tests pass yet Java 17 override does not run | Tests used output classes instead of JAR | Integration tests using packaged JAR |
| Missing JaCoCo coverage | Report reads base while JVM ran overlay | Execution data, class files, source mapping |
| SpotBugs reports unsupported class major | Analyzer/ASM does not yet support higher variant | Analyzer version, class-file major |
| `ServiceLoader` fails to find provider | Misconfigured services metadata/loader/module config | Root `META-INF/services`, JPMS descriptors |
| Override disappears after shading | Manifest/versions entries dropped or relocated wrongly | Inspect final artifact |
| Different outputs on different servers | Different JDK, classloader, or image | Runtime logs, JAR checksum |
| Old code still executes after rollout | Cache/exploded archive, launcher, or stale artifact | Deployment/checksum/logging |
| Security scan misses bug in overlay | Scanner does not inspect versioned tree | Variant coverage and tooling |

Do not rush to conclude a classloader is “broken” if the environment runs an older Java than the version directory or intentionally disables MRJAR behavior in a tool. Collect JDK, manifest, entry, and loader context first.

## 35. Investigation Example: Java 17 Does Not Select the New Implementation

Suppose `HexCodec.implementation()` prints `base-java8` even though the application runs on Java 17.

Diagnostic steps:

1. Confirm the actual process JVM is Java 17, not an unrelated shell.
2. Inspect the real manifest inside the JAR and verify `Multi-Release: true`.
3. Use `jar --list` to check the path `META-INF/versions/17/com/example/codec/HexCodec.class`.
4. Use `javap` to inspect base/overlay class files and public method signatures.
5. Run `jar --validate`.
6. Run directly with `java -cp build/hexcodec-mr.jar...` as in the minimal example.
7. If direct execution works yet fails inside a framework, investigate custom/nested classloaders.
8. Check whether another `com.example.codec.HexCodec` class is being loaded earlier from a different library.
9. Inspect fat JAR/shading/relocation and container libraries.
10. Re-test behavior on the final deployable artifact.

### 35.1. Wrong Manifest

The archive contains:

~~~text
META-INF/versions/17/com/example/codec/HexCodec.class
~~~

but the manifest lacks `Multi-Release: true`. ZIP readers still list that entry, yet regular Java class lookup may load the base. Fix the packaging, not the Java code.

### 35.2. Wrong Class Path

The archive contains:

~~~text
META-INF/versions/17/HexCodec.class
~~~

whereas the logical class name is `com/example/codec/HexCodec.class`. A versioned entry must preserve the **matching package/class path** beneath the version directory.

### 35.3. Another Class Was Loaded First

An application may have multiple JARs containing the same fully qualified class. A class loader may select the class from another JAR before reaching the expected MRJAR. Inspect the dependency graph and class-loading logs rather than assuming the logical class name came from the intended MRJAR.

## 36. Investigation Example: Java 11 Loads an Unsupported Class

Symptom:

~~~text
java.lang.UnsupportedClassVersionError:
com/example/Feature has been compiled by a more recent
version of the Java Runtime
~~~

The JAR contains:

~~~text
META-INF/versions/11/com/example/Feature.class
~~~

yet `Feature.class` actually has major version **61**. Java 11 correctly selected version directory 11 per the rules, but the class file was compiled for Java 17, so the runtime cannot load it.

Fix:

- Compile the implementation under `versions/11` with an appropriate JDK and `--release 11`.
- Place the Java 17 implementation under `versions/17`.
- Compile the base with `--release 8` if Java 8 must be supported.
- Run validation and runtime tests on Java 11/17.
- Do not use `--add-opens` or alter the manifest to mask class-file version errors.

## 37. Investigation Example: JaCoCo Reports 0 Coverage on an MRJAR

Scenario:

- Test JVM runs Java 17.
- Runtime loads `META-INF/versions/17/com/example/codec/HexCodec.class`.
- JaCoCo execution data is recorded.
- The report task is supplied with the **base class file** `com/example/codec/HexCodec.class`.

Because bytecode/probe mappings do not match, the report may skip the class, warn about a mismatch, or display unexpected coverage.

Resolution:

1. Identify which class variant the test JVM loaded.
2. Check that the JaCoCo version supports the class-file major version.
3. Configure the report with class files matching the runtime variant.
4. Ensure source mappings are accurate.
5. Test the base runtime separately when the library still supports Java 8.
6. Do not arbitrarily merge execution data from different variants.
7. Distinguish line coverage of shared logic from JDK 17-only logic.

A successfully generated coverage report does not prove every runtime path was tested.

## 38. MRJAR Testing Matrix During Migration

Example for a library committing to run on Java 8, Java 11, Java 17, and Java 21:

| Item | Java 8 | Java 11 | Java 17 | Java 21 |
|---|---|---|---|---|
| JAR can be loaded | Test | Test | Test | Test |
| Selected implementation | Base | Override 11 or base | Override 17 | Override 21 or lowest suitable version |
| Public API compatibility | Test | Test | Test | Test |
| Contract/behavior equivalence | Test | Test | Test | Test |
| Binary client built for Java 8 | Test | Test | Test | Test |
| Serialization/protocol output | Test | Test | Test | Test |
| Reflection/JPMS if applicable | N/A or per model | Test | Test | Test |
| Resource lookup | Test | Test | Test | Test |
| ServiceLoader/provider behavior | Test | Test | Test | Test |
| Tests against packaged JAR | Test | Test | Test | Test |
| Variant coverage | Test | Test | Test | Test |
| Security scan/exposure | Review | Review | Review | Review |
| Performance baseline | Benchmark | Benchmark | Benchmark | Benchmark |

The cells indicate **tasks to perform**, not PASS results. Pick the JDKs that the artifact genuinely commits to supporting; if a Java version is EOL and no longer acceptable to the organization, consider dropping it from the support matrix rather than maintaining it indefinitely by default.

### 38.1. Contract Tests Must Run the Same Input Set

Example for `HexCodec`:

- Empty input.
- Byte values 0, 15, 127, 128, 255.
- Random data with a deterministic seed.
- Large inputs.
- Null handling according to the API contract.
- Concurrency if the API guarantees thread safety.

Compare outputs and exceptions across implementations. Merely verifying that `implementation()` differs only proves selection; **it does not prove the two implementations share identical semantics**.

### 38.2. Testing on Versions Without a Dedicated Override

If a library has overrides 11 and 17, also run on Java 16 (if supported by environment/policy) to verify Java 16 selects version 11. Likewise, verify Java 21 selects version 17 when no version 21 entry exists. These checks help catch assumptions of “only running on exact N”.

## 39. MRJAR Release Workflow

A pipeline can be structured as follows:

~~~text
Base source (Java 8)
      |
      +--> javac --release 8
      |
      v
Base output
      |
      +-----------------------------+
      |                             |
Java11 source                  Java17 source
      |                             |
javac --release 11          javac --release 17
      |                             |
      v                             v
versions/11 output           versions/17 output
      |                             |
      +--------------+--------------+
                     |
                     v
           Jar packaging + manifest
                     |
                     v
               jar --validate
                     |
                     v
              Inspect JAR entries
                     |
                     v
        Test on each supported runtime
                     |
                     v
        Static/security/coverage analysis
                     |
                     v
            Publish + artifact checksum
~~~

Ensure compilation/packaging dependencies are wired cleanly in the build pipeline; never let the `jar` task run before versioned classes are finished.

### 39.1. Release Gating

Only mark a release ready when:

- The manifest is valid.
- Base and overlays have appropriate class-file targets.
- Public API consistency is verified.
- The packaged JAR artifact has been tested across supported runtimes.
- Class/resource selection and semantics meet requirements.
- Dependency/security scanners cover all variants.
- Integration with actual launchers/servers is verified.
- The artifact is versioned, checksummed, and signed per policy.

## 40. Anti-Patterns to Avoid

### 40.1. Copying Java 17 Source into the Base Tree and Using `--target 8`

If code references Java 17 APIs, `-target 8` alone does not guarantee Java 8 compatibility. Separate the source trees and use the appropriate `--release` flag.

### 40.2. Naming Directories After Class-File Major Versions

`META-INF/versions/61` does **not** mean Java 17. Directories must use the Java feature release such as `17`.

### 40.3. Missing the `Multi-Release` Manifest Attribute

Overlay entries may exist, yet the JVM can still run the base class. The manifest attribute is an essential part of the format.

### 40.4. Changing the Public API Between Base and Overlay

Having the same artifact coordinate yet different method contracts per JDK makes compilation/testing difficult for consumers and can cause linkage errors.

### 40.5. Testing Against the Classes Directory and Concluding MRJAR Works

The classes directory has neither a manifest nor versioned archive rules. Always test the **packaged JAR**.

### 40.6. Testing Only on the Latest JDK

A JAR might run on Java 21 while the Java 11 branch fails due to a wrong compiler target. Test the lowest supported runtime and all override milestones.

### 40.7. Merging/Shading That Drops `META-INF/versions`

Shading can alter layout and manifest; inspect the final artifact and verify runtime behavior before release.

### 40.8. Assuming Every ZIP Scanner Is MR-Aware

`ZipFile` or custom loaders may read physical entries without applying runtime-selection logic.

### 40.9. Scanning Only Base Classes for Security

Versioned implementations are production code too and require maintenance, testing, and scanning.

### 40.10. Using MRJAR to Cling to Unpatched EOL JDKs

An artifact may technically support multiple JDKs, yet security policies may require dropping overly old runtimes. MRJAR cannot replace platform security maintenance.

## 41. Checklist Before Releasing an MRJAR to Consumers

- [ ] Identified minimum Java version and supported JDK releases.
- [ ] Compiled base classes for the lowest appropriate target.
- [ ] Placed versioned classes accurately under `META-INF/versions/N` with N starting from 9.
- [ ] Verified class-file major version of each versioned entry is compatible with N.
- [ ] Ensured the archive manifest contains `Multi-Release: true`.
- [ ] Verified public/protected API consistency between base and overlays.
- [ ] Ran `jar --validate` when supported by the toolchain.
- [ ] Confirmed JAR listing shows base and overlays at expected paths.
- [ ] Ran contract tests on every committed runtime.
- [ ] Ran tests using the packaged JAR, not merely the output classes directory.
- [ ] Tested intermediate Java runtimes between override milestones where relevant.
- [ ] Verified resource/`ServiceLoader`/JPMS behavior if used by the library.
- [ ] Confirmed nested JAR, shading, or WAR packaging does not break selection.
- [ ] Ensured static analysis and security scanners cover versioned code.
- [ ] Tied code coverage to the bytecode variant actually executed.
- [ ] Recorded build tool/compiler versions, checksums, and provenance.
- [ ] Documented all runtime/behavior differences with clear ownership.

This checklist is a guide for those performing the migration, **not a certification that a specific artifact has been tested**.

## 42. Concluding Principles

- **Multi-release JAR is a Java 9/JEP 238 mechanism enabling one artifact to carry multiple per-JDK implementations**, not an automatic way to upgrade source code to newer APIs.
- **`META-INF/versions/N` uses the Java release N, not the class-file major version.** Java 17 uses directory `17`, whereas its corresponding class-file major version is typically `61`.
- **The `Multi-Release: true` manifest attribute is an essential condition** for runtimes to recognize the format.
- **The runtime selects the entry with the largest N not exceeding its Java feature version**, falling back to base if no override exists.
- **Each logical class can resolve to a different override.** There is no “single version of the whole JAR” when some classes only exist in base.
- **Keep public/protected APIs stable across implementations.** Internal algorithms may change, yet binary and behavioral contracts must be protected.
- **Base sources must be compatible with the lowest supported Java**, and overlay compilations must use the appropriate `--release`.
- **`jar --validate` helps verify structural/API consistency**, but does not replace integration/behavioral tests.
- **Gradle/Maven must organize multiple compile outputs and package versioned directories properly**; testing the classes directory is insufficient.
- **JPMS, `ServiceLoader`, custom class loaders, and resource lookup follow distinct rules**; do not assume every tool/JAR loader is MR-aware.
- **Fat JARs, shading, WARs, and nested dependencies can alter class selection**; always inspect the final artifact.
- **Security, coverage, and static analysis must account for every variant** rather than scanning only the base.
- **A JAR with an unchanged checksum can run different code upon a JDK upgrade**, making JDK/image upgrades a reason to run regression tests.

In Java Advance Compatibility Migration, MRJAR is a useful tool for **preserving compatibility with older JDKs while providing specialized implementations for newer JDKs**. Yet this benefit is only sustainable when the `META-INF/versions` structure is accurate, the manifest is explicitly configured, classes uphold a shared API contract, and every runtime path is tested using the genuinely packaged artifact. When those factors are well managed, a library can evolve alongside Java without forcing every consumer to upgrade their JDK simultaneously.
