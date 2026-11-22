# Major version, minor version, and class file compatibility with the target JVM

## 1. Why care about class file versions?

A `.class` file contains bytecode and metadata in the **Java Virtual Machine class file** format. During compilation, `javac` (or a bytecode generation tool) writes the **`major_version.minor_version`** pair at the beginning of the file. This pair of numbers tells the JVM and bytecode-reading tools which format is used, thereby determining whether the class file can be accepted.

Three versions must be distinguished:

- **Compiling JDK version**: The JDK running `javac`, for example JDK 21.
- **Class file version**: The compilation output, for example `61.0` corresponding to the regular Java 17 format.
- **Target JVM version**: The actual JVM that will load/run the class, for example a Java 17 runtime on the server.

These numbers **do not necessarily match**: JDK 21 can use `javac --release 17` to produce a `61.0` class file for a Java 17 JVM. Conversely, compiling with defaults on JDK 21 typically produces `65.0` and cannot run on a Java 17 JVM.

Core rule: **the class file must be within the set of versions supported by the target JVM**, while also satisfying preview conditions (if any), valid bytecode format, and dependencies/APIs during linking and execution. Simply comparing the major number is only the first screening step, not a guarantee of full compatibility.

## 2. Where is the version pair located in a `.class` file?

According to JVMS `4.1, the structure begins as follows:

```text
ClassFile {
    u4 magic;                 // 4 bytes: 0xCAFEBABE
    u2 minor_version;         // 2 unsigned bytes
    u2 major_version;         // 2 unsigned bytes
    u2 constant_pool_count;   // starts at offset 8
    ...
}
```

| Byte offset (0-based) | Length | Field | Meaning |
| --- | ---: | --- | --- |
| `0..3` | 4 bytes | `magic` | Four bytes `CA FE BA BE` confirming the class file signature |
| `4..5` | 2 bytes | `minor_version` | Minor version, stored **before** major |
| `6..7` | 2 bytes | `major_version` | Major version |
| `8..9` | 2 bytes | `constant_pool_count` | Nominal number of constant pool entries, not part of the version |

`u2` is a **16-bit unsigned** integer and is stored in **big-endian** byte order. Do not confuse minor/major or interpret the two bytes as little-endian.

Example of the first eight bytes:

```text
CA FE BA BE  00 00  00 3D
| magic    |  minor  | major |
```

`0x003D = 61`, so this is a **`61.0`** class file, typically generated when targeting Java 17. As another example, `CA FE BA BE 00 00 00 41` has major `0x41 = 65`, i.e., `65.0` (Java 21). The two version bytes are only one part of the format: manually editing `00 41` to `00 3D` does not convert instructions, constant-pool entries, attributes, or new APIs into the Java 17 version.

## 3. Mapping major version to Java release

The table below shows the **latest major associated with each Java release**; it does not mean that the JVM of that release can only read a single major. For releases from Java 5 onward, a quick rule of thumb is **`major = 44 + Java version number`**; the early Java 1.x releases are exceptions in release numbering.

| Java/JDK release | Major | Regular class file |
| --- | ---: | --- |
| JDK 1.0, 1.1 | 45 | `45.x` (minor historically varied) |
| Java 1.2 | 46 | `46.0` |
| Java 1.3 | 47 | `47.0` |
| Java 1.4 | 48 | `48.0` |
| Java 5 | 49 | `49.0` |
| Java 6 | 50 | `50.0` |
| Java 7 | 51 | `51.0` |
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
| Java 26 | 70 | `70.0` |
| Java 27 | 71 | `71.0` |

According to JVMS Java SE 27, a JVM conforming to that specification supports majors **45 through 71** (minor/preview rules still apply). Therefore:

- `61.0` generally passes the **class file version** check on Java 17, 21, and 27; it can still fail at another step.
- `65.0` is rejected by a Java 17 JVM because major 65 is higher than the maximum supported by Java 17, which is 61.
- `71.0` requires a Java 27 or newer JVM that supports that format; a Java 21 JVM cannot load a class file of version 71.

Note: the number `17` in `--release 17` is the **Java version**, whereas the number `61` read by `javap` is the **class file major**. Do not use `major = 17` when intending to target Java 17.

## 4. Minor version and class files using preview

### 4.1. Before and after Java 12

- For **majors 45..55**, the specification allows the minor field to be within the `u2` numeric range (0..65535); historical JVMs/JDKs had different sets of supported minors. In practice, modern Java releases before Java 12 typically emit `minor = 0` for their new major.
- From **major 56** (Java 12) onward, valid `minor` values are only **`0` or `65535`** (`0xFFFF`). Do not interpret minor as a “patch version” like `17.0.8` of the JDK.
- `M.0` indicates that the class file does not depend on preview features under this version-marking mechanism.
- `M.65535` (with `M >= 56`) marks **a dependency on preview features of the exact release that produced major M**; the compiler may mark it this way due to a language preview feature even if there is no separate preview opcode.

### 4.2. Preview is bound strictly to the release

For example, with Java 21, the major is 65:

| Class file | Java 21 JVM | Java 22 or newer JVM |
| --- | --- | --- |
| `65.0` | Passes version check | Can pass version check |
| `65.65535` | Loaded only when **preview is enabled** | **Rejected**, even if preview is enabled |

A Java 21 JVM must be run with `--enable-preview` to load `65.65535`. When moving to a Java 22 JVM, a Java 21 preview class **does not** become a usable Java 22 class by enabling the flag again; it must be recompiled for the appropriate release. This rule also applies to preview majors from Java 12 onward (for instance, `71.65535` is tied to Java 27).

Illustrative syntax **on JDK 21 itself**, with source code that actually uses Java 21 preview features:

```bash
javac --enable-preview --release 21 PreviewExample.java
java --enable-preview PreviewExample
```

This is a command template, not a standalone program: `PreviewExample.java` must exist and contain valid preview code for Java 21. `javac --enable-preview` is only used with a source/release corresponding to **the current JDK compiler version**; you cannot use JDK 27 to compile Java 21 language preview features with `--release 21`.

**Implication for instrumentation:** if an agent transforms a class that depends on preview features, the output class must still match that exact major/minor and runtime. Lowering minor from `65535` to `0` does not automatically turn preview constructs into stable features.

## 5. How does the target JVM decide to load a class?

Conceptual verification sequence (simplified; the JVM's detailed order may differ):

1. Read magic, major/minor, and class file structure.
2. Check whether major/minor falls within the set supported by the JVM.
3. If `minor = 65535` from Java 12 onward, require **major to belong to the exact JVM release** and preview to be enabled.
4. Check format, constant pool, access flags, attributes, bytecode, and verification constraints.
5. When linking or using the class, resolve symbols, dependent classes, methods, fields, module/package access, APIs, and native libraries if any.

Typical scenarios:

- **Default JDK 21 compile, run on JVM 17**: class `65.0` → typically throws `UnsupportedClassVersionError`, because JVM 17 supports at most `61`.
- **JDK 21 compile with `--release 17`, run on JVM 17**: class `61.0` → passes the version check; still need to check dependencies, APIs, and bytecode transformed by other tools.
- **Class `65.65535` on JVM 21 without preview enabled**: fails because preview is not enabled.
- **Class `65.65535` on JVM 22 with preview enabled**: still fails because it is a preview from an older release.
- **Class `61.0` using an API that only exists from Java 21 onward**: JVM 17 may pass the major check but fail at linking/execution, typically with `NoSuchMethodError` or a related linkage error.

The **“newer running older class”** direction is generally supported in terms of format, but **does not 100% guarantee application behavior** when APIs are removed, dependencies are missing, module access policies change, or bytecode is invalid. The **“older JVM running a class with a newer major”** direction is blocked right at the class file level.

## 6. Hands-on: reading and verifying versions with Java 17+

Create two files in the same directory. The first program is the class to be inspected.

**File `VersionHello.java`:**

```java
public class VersionHello {
    public static void main(String[] args) {
        System.out.println("Hello, JVM 17");
    }
}
```

**File `ClassVersionReader.java`:** reads the first eight bytes directly; `DataInputStream` uses big-endian and `readUnsignedShort()` avoids misreading `65535` as a negative number.

```java
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassVersionReader {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java ClassVersionReader file.class");
        }

        try (DataInputStream in =
                     new DataInputStream(Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IllegalArgumentException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            System.out.printf("magic=%08X; major=%d; minor=%d%n",
                    magic, major, minor);
        }
    }
}
```

On JDK **17 or newer that still supports target 17**, run:

```bash
java -version
javac -version
javac --release 17 VersionHello.java ClassVersionReader.java
java VersionHello
java ClassVersionReader VersionHello.class
javap -verbose VersionHello
```

Exact stdout lines from the two `java` commands running the classes in the example:

```text
Hello, JVM 17
magic=CAFEBABE; major=61; minor=0
```

The `javap -verbose VersionHello` output is quite long; the relevant part will contain:

```text
  minor version: 0
  major version: 61
```

`java -version` and `javac -version` display the actual version of the machine, so there is no fixed stdout. If you want to view the raw header with a hex tool, the first eight bytes of `VersionHello.class` will look like `CA FE BA BE 00 00 00 3D`.

Limitation of `ClassVersionReader`: it **only reads the header** and does not yet check the constant pool, methods, attributes, total file length, bytecode, or whether the JVM can load it successfully. A fake file with the right first eight bytes can still throw `ClassFormatError` when loaded.

### An experiment on “matching major but incompatible API”

On **JDK 21 or newer**, consider the file `ApiTrap.java`:

```java
import java.util.List;

public class ApiTrap {
    public static void main(String[] args) {
        System.out.println(List.of("alpha", "beta").getFirst());
    }
}
```

`List.getFirst()` has existed since Java 21. If using a JDK 21+ compiler with `--source 17 --target 17`, the code can be compiled to **`61.0`** while still referencing the Java 21 API present on the build machine:

```bash
javac --source 17 --target 17 ApiTrap.java
javap -verbose ApiTrap
```

When taking that class to a Java 17 JVM, the `61.0` version is valid, but the `List.getFirst()` call does not exist in Java 17 → it can throw `NoSuchMethodError` at runtime. If instead you use:

```bash
javac --release 17 ApiTrap.java
```

the compiler will **report a compilation error** because `getFirst()` is not part of the Java 17 API. The exact wording of error messages and warnings depends on the JDK. This is why setting `-target` alone is not enough to guarantee compatibility on an older JVM.

## 7. Choosing the right compilation version for the deployment environment

| Option | What it controls | Limitations to remember |
| --- | --- | --- |
| `--source N` | Java N language syntax/semantics accepted by the compiler | Does not automatically lower the bytecode version or constrain APIs |
| `--target N` | Target major/class file format emitted by the compiler | By itself, it does not prevent calling APIs that only exist in newer JDKs |
| `--release N` | Combines the language level, class file, and **platform APIs supported in Java N** | Does not check all third-party libraries, reflection, native code, runtime behavior, or agent transformations |
| Java toolchain | Selects the JDK that actually runs the compiler/tooling | Selecting a JDK 21 toolchain **does not automatically** mean the output is `61.0`; target/release is still required |

Prefer `javac --release N` if the goal is to run on Java release N and the compiler supports that release. Avoid specifying `--release` together with `--source`/`--target`: `javac` does not allow such a combination. Check the releases supported by the compiler with `javac --help`; newer JDKs are not required to support every very old target.

Gradle Groovy DSL example, using the compiler from JDK 21 while generating class files for Java 17:

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

After the build, **verify the actual artifact** using `javap -verbose`/reading the header; do not rely solely on the version of the Gradle daemon or `JAVA_HOME`. If there are Kotlin/Scala, annotation processors, compiler plugins, or custom weaving/bytecode-generation tools, each pipeline may have a different target and class file handling mechanism. Test on the **lowest supported JVM** before releasing.

## 8. When class files are inside a JAR and transformed by instrumentation

### 8.1. Dependencies and multi-release JARs

An application might be compiled to `61.0` yet contain a Java 21 `65.0` library. A Java 17 JVM can still fail when loading a class from that library. Therefore, you must check **every class that is actually loaded**, not just the main class or a single line in `build.gradle`.

A regular JAR contains classes such as `com/example/Service.class`. With a **multi-release JAR** (manifest having `Multi-Release: true`), there may be variants at `META-INF/versions/9/...`, `META-INF/versions/17/...`, etc. The runtime selects the appropriate version according to multi-release rules; you must inspect **the variant that the target JVM actually selects**, rather than concluding from just any single class in the archive.

Helpful commands:

```bash
jar tf library.jar
javap -verbose -classpath library.jar com.example.Service
```

`jar tf` lists entries, while `javap` inspects the specified class. For multi-release JARs, tools have multi-release-related options; verify the exact entry for each runtime rather than assuming the default output selected the same variant as the production JVM.

### 8.2. Java agents, ASM, Byte Buddy, and modifying classes

In the instrumentation module, a Java agent can receive bytecode in `ClassFileTransformer.transform(...)` and return a new byte array. Those bytes must be valid for the JVM **that is defining or transforming the class**.

- **Reading the input**: the ASM/Byte Buddy/bytecode parser library must understand the latest major used by the application. A message like “Unsupported class file major version 71” may come from **the agent's parser**, rather than from the JVM; determine where the stack trace originates.
- **Writing valid output**: the transformed class must have a compatible major/minor, consistent constant pool, frames, attributes, flags, and bytecode. The tool must support the corresponding class file features; do not downgrade major by replacing the two header bytes.
- **Retransform/redefine note**: the JVM has restrictions on structural changes to already-loaded classes; even a class file with a supported version can still be rejected if the transformation violates those restrictions.
- **Do not bypass preview**: an agent running on a Java 21 JVM cannot “rescue” a `65.65535` class on a Java 22 JVM by enabling preview. You must generate bytecode compatible with the release actually deployed.

If a transformer generates classes on a Java 17 JVM, verify that the **output** is an appropriate version for Java 17 (usually `61.0` or lower), does not use formats/constructs only available from Java 21 onward, and check for `VerifyError`/`ClassFormatError` after transformation.

## 9. Diagnosing errors by layer

| Symptom | Likely failing layer | How to check |
| --- | --- | --- |
| `UnsupportedClassVersionError`; log says class version `65.0`, runtime supports at most `61.0` | JVM rejects the class file version | Compare `java -version`, `javap -verbose`; use a newer JVM or recompile with `--release 17` |
| Error loading `M.65535` related to preview | Minor/preview does not match release or flag is not enabled | Check the exact JDK/release that produced the class and `--enable-preview` on a JVM of the **same release** |
| “Unsupported class file major version 71” in ASM/Byte Buddy stack trace | Bytecode reading/generation library does not yet understand the new format | Upgrade the bytecode library/agent to a compatible version; check where the error is thrown |
| `ClassFormatError` or `VerifyError` after transform | Invalid class structure or bytecode/frames | Compare bytecode before and after, writer and verifier configuration; do not just fix the version |
| `NoSuchMethodError`, `NoClassDefFoundError`, or module access error | API, dependency, classpath/module path, or linkage | Check `--release`, runtime dependency set, classloader, and target environment |

Do not infer the cause solely from the text “Unsupported class file”: find **the exception type, the stack trace origin, and which class is being read**. Separately check the JDK version used for the build, the JVM running the application, the test runtime, the bytecode agent, and the dependencies.

## 10. Safe deployment checklist

1. Identify the **lowest JVM to support** (e.g., Java 17) and the policy on whether preview features are used.
2. Set `--release 17` for the main Java code, along with an equivalent target strategy for every language/class-generating tool.
3. Use `javap -verbose` or a header-reading program to confirm the major/minor of **the artifact after build, and after weaving/transform**.
4. Inspect the classes actually loaded from JARs, multi-release JARs, and dependencies; upgrade agents/ASM/Byte Buddy when adding a new JDK.
5. Run integration tests on an actual Java 17 JVM (if that is the minimum), test dynamic class loading/instrumentation paths, and enable preview only intentionally with the matching release.

**Key takeaway:** `major` indicates the class file format generation; `minor` from Java 12 onward distinguishes regular classes from preview-dependent classes; `--release` helps target the appropriate language, class file, **and platform APIs**. Actual runnability also depends on valid bytecode, libraries, and the JVM environment.

## Authoritative references

- [JVMS Java SE 27 `4.1 — The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html): positions of `major_version`/`minor_version` fields, version limits, and preview rules.
- [JVMS Java SE 27 `1.2 — Java SE releases & class file major versions](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): release/major mapping table.
- [JDK 27 `javac` documentation](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): meaning of `--release`, `--source`, `--target`, and compiler preview.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html): multi-release JAR rules.
