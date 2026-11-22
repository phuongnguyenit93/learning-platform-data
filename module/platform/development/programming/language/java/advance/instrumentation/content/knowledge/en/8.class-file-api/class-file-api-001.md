# java.lang.classfile as an Official API from JDK 24 and Version Compatibility Requirements

## 1. Objectives and Problems to Solve

Starting from **JDK 24**, `java.lang.classfile` is the **official Class-File API (standard API)** of the Java platform for **reading, parsing, generating, and transforming `.class` bytecode**. For instrumentation, this API can handle the **bytecode processing** work for which many projects previously had to rely on libraries such as ASM/Byte Buddy or internal JDK APIs.

However, "an official API from JDK 24" **does not mean** code using it can run on JVM 17/21, nor does it mean any bytecode it generates will run on older JVMs. To choose the right technology, you need to separate three questions:

1. **Which JDK compiles and runs the tool/agent code?** Code with `import java.lang.classfile.*` requires the **API to exist at compile time and runtime**: with the finalized API, the minimum target is JDK 24.
2. **Which format version does the `.class` being read or generated have?** A class file has its own `major_version` and `minor_version`, independent of the version of the tool currently running.
3. **Which JVM will the target bytecode run on?** The JVM must support the class-file version and the features/dependency paths actually used in that bytecode.

After this lesson, you will know the preview and final milestones, distinguish **JDK API compatibility** from **class-file format compatibility**, run an example of a **JDK 24 tool reading a Java 17 class**, check versions with `javap`, and choose an agent/tool release strategy for multiple JVM versions.

## 2. Development Milestones: Preview First, Official from JDK 24

| JDK Version | Class-File API Status | Key Things to Remember |
|---|---|---|
| **17 and 21** | No `java.lang.classfile` as a standard API | Cannot compile source using this package with `--release 17` or `--release 21` |
| **22** | **1st Preview**, JEP 457 | API in experimental stage; watch out for preview configuration and contract changes |
| **23** | **2nd Preview**, JEP 466 | Continued experimentation, with changes compared to 22; do not assume preview source is strictly compatible |
| **24** | **Final/standard**, JEP 484 | `java.lang.classfile` is part of the Java SE 24 API; `--enable-preview` is not needed for this API alone |
| **25 and newer JDKs providing the API** | Continues as a platform API | Check the Javadoc and runtime of the actual version when using new features/methods |

**"Finalized in 24" does not mean code based on the 22/23 previews can be kept unchanged and run on 24.** When upgrading versions, you must recompile and check which class names, signatures, and behaviors have changed. In addition, **preview API** and **preview language feature** are two different concepts: do not rely on `.class` version markers to infer whether a tool is using the preview Class-File API.

The official API was published in **JEP 484**. It consists of the following packages:

- `java.lang.classfile`: structures, models, builders, transformations, verification;
- `java.lang.classfile.attribute`: attribute structures of classes/methods/fields;
- `java.lang.classfile.constantpool`: constant-pool entries and builders;
- `java.lang.classfile.instruction`: instruction/bytecode models.

They reside in the **`java.base`** module. On JDK 24, there is no need to add a separate Maven dependency, no need for `--add-exports` to access the public API, and no need for `--enable-preview` just because you import `java.lang.classfile`. A modular Java application also does not need to declare `requires java.base` because `java.base` is an implicit dependency.

## 3. What Does the Class-File API Do in Instrumentation?

Distinguish between **bytecode processing** and **attaching to the JVM**:

~~~text
                           Java agent / instrumentation
                        -----------------------------------
JVM encounters class on load  ---> ClassFileTransformer.transform(...)
                                      |
                                      v
                              byte[] classfileBuffer
                                      |
                           +----------+----------+
                           | Class-File API (24+) |
                           | parse -> model       |
                           | transform / build    |
                           | verify -> byte[]     |
                           +----------+----------+
                                      |
                   return transformed bytes, or null to skip
                                      |
                                      v
                         JVM verifies and defines the class
~~~

**The Class-File API does not act as the Attach API or the Instrumentation API.** It does not load classes into the JVM on its own, does not provide `premain/agentmain`, and does not register a transformer automatically. An agent still needs the `java.instrument` module and `Instrumentation.addTransformer`/`retransformClasses` or an appropriate alternative mechanism.

Key components:

| API | Role |
|---|---|
| `ClassFile.of()` | Creates a default context for reading/writing/transforming class files |
| `ClassFile.parse(byte[])` or `parse(Path)` | Reads class bytes into a `ClassModel` |
| `ClassModel` | Class model: name, version, fields, methods, attributes, constant pool |
| `ClassFile.build(...)` | Generates class bytes from a builder |
| `ClassFile.transformClass(ClassModel, ClassTransform)` | Creates new class bytes by processing the `ClassElement`s of the model |
| `ClassTransform.ACCEPT_ALL` | Passes all elements through the pipeline, **without inserting new probes** |
| `ClassFile.verify(...)` | Returns a list of class-file validation errors according to the API |
| `ClassFile.latestMajorVersion()` | The highest class-file major version supported by the running runtime |

**`ClassModel` is an immutable and lazily parsed model.** A successful `parse` call does not mean every attribute/instruction in the file has been validated. A later accessor call can still throw `IllegalArgumentException` when encountering a malformed or unsupported structure. When used concurrently, do not assume every lazy model is safe to share concurrently.

### Why is it useful for instrumentation?

When needing to record the execution time of a method, a tool typically has to parse the `Code` attribute, generate instructions to call a probe, adjust exception flow, frames, and the constant pool, and then emit a new class. The standard API helps represent those structures as strongly typed models/builders. Even so, **being able to generate bytes does not guarantee they are valid for every JVM**; you must still verify the version, bytecode verification, redefinition/retransformation restrictions, and module/class loader constraints.

## 4. Separating Three Versions to Avoid Wrong Conclusions

Consider three entities in the same project:

~~~text
(1) Tool compiled with JDK 24
    ClassFileApiDemo.class ------ major 68, references java.lang.classfile
                                      |
                                      | reads / transforms
                                      v
(2) Application class compiled with --release 17
    demo/Greeter.class ---------- major 61
                                      |
                                      | runs on compatible JVM
                                      v
(3) Target runtime Java 17 ------ supports class-file major 61
~~~

**A tool running on JDK 24 can still parse and generate Java 17-compatible bytecode.** Conversely, **that tool cannot run on Java 17 itself** because the tool class is compiled for Java 24 and depends on `java.lang.classfile`, which does not exist in Java 17.

Common class-file major version table:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| **Java 24** | **68** |
| Java 25 | 69 |

Normally, a newer Java release reads/runs classfiles from older releases within what the JVM supports, whereas an older JVM **cannot load a classfile with a higher major version than it understands**. For example, Java 17 cannot load a major 68 class, typically reporting `UnsupportedClassVersionError`.

That is only **class-file format compatibility**. Beyond the major version, you must also account for:

- **APIs referenced by Java code:** a major 61 class can still fail to run on Java 17 if compiled with unchecked flags and referencing an API that only exists from Java 24 onward; errors may be `NoClassDefFoundError`, `ClassNotFoundException`, or `NoSuchMethodError`.
- **Preview classfiles:** starting from releases supporting previews, minor version `65535` is associated with classes using preview features and has special rules; it is not simply an old classfile allowed to run on any newer JDK.
- **Class loaders, module access, and bytecode verifier:** a class with a supported major version can still fail to run if its structure, linkage, or access permissions are invalid.
- **Same-JVM agent:** an agent using the standard Class-File API must have a Java 24+ runtime, even if **the application it targets** only uses Java 17 source/bytecode.

## 5. Example: Java 24 Parsing a Class Compiled for Java 17

This example separates the **class to be analyzed** and the **analysis tool** into two outputs. This is the clearest way to verify the core message of this lesson: **the JDK running the API can be newer than the classfile being processed**.

### 5.1. Directory Tree

~~~text
classfile-version-lab/
├── src/
│   ├── demo/
│   │   └── Greeter.java
│   └── ClassFileApiDemo.java
├── out17/                    # Generated on build: Java 17 class
├── out24/                    # Generated on build: Java 24 tool class
└── outCopy/                  # Generated on tool run: rewritten class
~~~

The `out*` directories hold build/experiment outputs. The two `.java` files below are **complete Java programs** that can be compiled and run independently with the commands shown.

### 5.2. Application Class: Greeter.java

Save at **`src/demo/Greeter.java`**:

~~~java
package demo;

public final class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from Java 17 bytecode");
    }
}
~~~

The code intentionally uses only Java 17 features (in fact, even simpler) so that when compiled with `--release 17`, we get class version **61** and no dependency on Java 24 APIs.

### 5.3. Tool Using the Java Class-File API

Save at **`src/ClassFileApiDemo.java`**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassFileApiDemo {
    public static void main(String[] args) throws Exception {
        ClassFile api = ClassFile.of();
        ClassModel model = api.parse(Path.of(args[0]));

        System.out.println(
                "name=" + model.thisClass().name().stringValue());
        System.out.println("class-major=" + model.majorVersion());
        System.out.println("class-minor=" + model.minorVersion());
        System.out.println(
                "jdk-major=" + ClassFile.latestMajorVersion());
        System.out.println(
                "methods=" + model.methods().stream()
                        .map(m -> m.methodName().stringValue())
                        .sorted()
                        .toList());

        // Pass through the transform pipeline without adding probes or modifying logic.
        byte[] copy = api.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println(
                "transformed-major=" + api.parse(copy).majorVersion());
        System.out.println(
                "verify-errors=" + api.verify(copy).size());

        Path output = Path.of("outCopy", "demo", "Greeter.class");
        Files.createDirectories(output.getParent());
        Files.write(output, copy);
    }
}
~~~

**Explanation of the API and output values:**

- `api.parse(Path.of(args[0]))` opens the `.class` file and creates a `ClassModel`; it does not execute any methods in that class.
- `model.thisClass().name().stringValue()` reads the internal JVM name such as `demo/Greeter`.
- `majorVersion()`/`minorVersion()` are the **versions of the file being parsed**, not the version of the JDK running the tool.
- `ClassFile.latestMajorVersion()` is the highest class file version recognized by the **JDK running the tool**; on **JDK 24 it is 68**.
- `model.methods()` lists both the `<init>` constructor as a method in the class file and `main`; `sorted()` keeps the output deterministic.
- `ClassTransform.ACCEPT_ALL` passes class elements through the pipeline, **performing no instrumentation**. The resulting byte array may differ at the byte level due to attribute/writer processing; do not assume bit-for-bit equality with the input.
- `api.verify(copy).size()` counts issues detected by the Class-File API. **Zero does not prove a class is guaranteed to link/run on every JVM**, but it is a useful structural check.
- `Files.write` writes an output classfile following the proper package path; this statement does not cause a target JVM to automatically reload an already-loaded class.

### 5.4. Compiling

Verify that the terminal points to JDK 24:

~~~bash
java -version
javac -version
~~~

In Bash (Linux/macOS), create the directories:

~~~bash
mkdir -p out17 out24 outCopy
~~~

In PowerShell (Windows):

~~~powershell
New-Item -ItemType Directory -Force out17, out24, outCopy
~~~

After that, the following commands are compatible with both Bash and PowerShell. **Run using the JDK 24 toolchain** from the lesson root directory:

~~~bash
javac --release 17 -d out17 src/demo/Greeter.java
javac --release 24 -d out24 src/ClassFileApiDemo.java
~~~

Here there are **two compilation targets**:

- `Greeter.java` chooses `--release 17`: classfile and API target Java 17; no separate JDK 17 is needed when the current compiler is JDK 24.
- `ClassFileApiDemo.java` chooses `--release 24`: the compiler allows importing the official Class-File API and produces a tool with class-file major 68; **the runtime executing the tool must be JDK 24-compatible**.

### 5.5. Running the Analysis Tool and the Generated Class

~~~bash
java -cp out24 ClassFileApiDemo out17/demo/Greeter.class
~~~

**Expected stdout on JDK 24** with the exact two sources above:

~~~text
name=demo/Greeter
class-major=61
class-minor=0
jdk-major=68
methods=[<init>, main]
transformed-major=61
verify-errors=0
~~~

The lines `class-major=61` and `transformed-major=61` matter more than the number "tool runs on JDK 24": **the processed class remains a Java 17 classfile**. No Java 24 instructions are added to the output.

Run the output class:

~~~bash
java -cp outCopy demo.Greeter
~~~

Stdout:

~~~text
Hello from Java 17 bytecode
~~~

This checks the semantic behavior of the "accept all" transform on the example class. The analysis tool runs on JDK 24, while **the output class carries major 61**. If you truly need to prove it runs on JVM 17, also use **`java` from JDK 17** to run `outCopy` in a test environment; testing on JDK 24 alone does not replace compatibility testing on the older runtime.

## 6. Countercheck: A Tool Cannot Both Use the JDK 24 API and Compile for Java 17

Try this (no need to edit the source):

~~~bash
javac --release 17 -d out24 src/ClassFileApiDemo.java
~~~

The result **fails to compile** because the `java.lang.classfile` API does not exist in the Java 17 API. The message typically includes:

~~~text
error: package java.lang.classfile does not exist
~~~

This is a **source/API compatibility** check, unrelated to whether `ClassFileApiDemo` is analyzing a Java 17 class.

### 6.1. Why Should You Use --release?

With the JDK 24 compiler:

- `--release 17` simultaneously enforces the language rules, target classfile version, and **the system APIs allowed to be referenced** according to Java 17.
- Using only `-source 17 -target 17` sets the language level and classfile target, **without guaranteeing that all APIs from the current JDK are blocked**. You could produce a classfile with major 61 that references JDK 24 classes/methods and fails at runtime on JDK 17.
- `--release 24` allows using `java.lang.classfile` with the JDK 24 toolchain; artifacts using this API must run on a runtime that has the corresponding API.

**You cannot use `--release 17` to "downgrade" a Java 24 package into a package available on Java 17.** Bytecode format compatibility and API availability are two separate contracts.

### 6.2. Checking the Major Version of Actual Files

Run with the JDK toolchain:

~~~bash
javap -verbose -classpath out17 demo.Greeter
javap -verbose -classpath out24 ClassFileApiDemo
~~~

In the output of the first command, look for:

~~~text
major version: 61
~~~

In the output of the second command, look for:

~~~text
major version: 68
~~~

`javap` reads the actual file, not just the build configuration. This is a useful check if a repository has multiple toolchains and build machines have multiple JDKs.

## 7. When the Application and Agent Need to Run on Different JDKs

This is the biggest risk in the instrumentation module: **the agent is loaded into the target JVM itself**. If the target JVM is Java 17, every class the agent needs to load must be compatible with it; the agent cannot use Java 24's standard Class-File API inside a Java 17 process.

| Scenario | Can `java.lang.classfile` be used directly in that process? | How to Handle |
|---|---|---|
| Standalone CLI tool running on **JDK 24**, analyzing Java 17 classes | **Yes** | Compile tool with `--release 24`; keep appropriate target for input/output classes |
| Startup Java agent running inside **JVM 24** | **Yes** | Agent uses Java 24 API; still verify transformed bytecode, manifest, and transformer |
| Attaching agent to **JVM 24** | **Yes**, if attach is supported | Agent code loads in JVM 24; check dynamic loading/retransform permissions |
| Agent loaded into **JVM 17 or 21** | **No** with this standard API | Use a parser/rewriter compatible with the target JDK, or upgrade the target runtime |
| Java 17 app running on **JVM 24** | **Yes**, because the running JVM is 24 | Choose the right classfile target for app/agent; verify frameworks and instrumentation |
| Compiling the tool with JDK 24 using `--release 17` | **No** | Separate the Java 24 tool from the Java 17 module or remove dependency on this API |

**Key takeaway:** "The application is written in Java 17" does not tell the whole story. You must ask whether it actually **runs in JVM 17 or JVM 24**. An application with Java 17 source running in JVM 24 can be instrumented by a JDK 24 agent; a Java 17 application running in JVM 17 cannot load an agent that references `java.lang.classfile`.

### 7.1. Practical Compatibility Strategies

**Strategy A — Offline JDK 24 tool:** Run a separate JDK 24 tool in the build pipeline, use the Class-File API to parse/transform Java 17 target classes, and verify that the output has major 61. Include the **output classes**, not the **Java 24 tool**, in the artifact running on JVM 17. Ensure the output classes do not reference APIs or bytecode supported only on Java 24.

**Strategy B — Agent must run on JVM 17:** Compile the agent with `--release 17` and choose a bytecode library that supports Java 17. ASM/Byte Buddy are common choices; the library version must also support the required classfile version. Do not import `java.lang.classfile` in the part of the agent that will be loaded on JVM 17.

**Strategy C — Require runtime JDK 24+:** If the system can be upgraded, declare **minimum runtime JDK 24** for the agent and related applications, and build/test thoroughly. Do not deploy that configuration into an environment that only has JDK 17/21.

**Strategy D — Multiple artifacts/deployment branches:** Provide separate agents/tools per JDK range or use a properly structured *multi-release JAR* if truly needed. With a multi-release JAR, base entries must run on older JDKs, `META-INF/versions/24` entries are used only on the corresponding JDK, the manifest must contain `Multi-Release: true`, and any eager linkage from older branches to `java.lang.classfile` must be avoided. A multi-release JAR **does not turn a Java 24 API into a JVM 17 API**.

For a library/agent with many customers, releasing multiple versioned artifacts can be simpler and easier to test than complex JDK conditional logic inside a single JAR.

## 8. Using the Class-File API Inside ClassFileTransformer

A `ClassFileTransformer` has the callback:

~~~java
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
~~~

**The signature above is an illustrative excerpt**, not a complete class; in practice you need to implement the interface and include the appropriate imports.

On **JVM 24+**, the callback can use `ClassFile.of().parse(classfileBuffer)`, read the `ClassModel`, transform it via `ClassTransform`, and return a new `byte[]`. However:

1. Process only classes within the scope that needs instrumentation; distinguish internal `className` format like `demo/Greeter` from Java names like `demo.Greeter`.
2. The API can detect malformed input classfiles or **a classfile version newer than the runtime/tool**; `parse` or model accessors may throw `IllegalArgumentException`. Do not return invalid bytes.
3. If no changes are needed, by the transformer contract return **`null`**. Return `transformClass` output only when intentionally emitting verified bytes.
4. Do not mutate the `classfileBuffer` array directly; if changes are needed, generate valid new bytes.
5. When injecting method calls/field accesses, ensure the helper class actually exists and the JVM can load it via the appropriate class loader/module.
6. With retransformation, restrictions on schema changes and currently executing bytecode still apply; the standard API does not remove `Instrumentation` limitations.
7. Test on the exact target JVM with real class loaders, frameworks, and modules, because a low error count from the API's `verify` does not replace linkage/runtime tests.

### 8.1. Conditional Logic Example (Not a Standalone Transformer)

~~~java
if (!"demo/Greeter".equals(className)) {
    return null;
}

try {
    ClassFile api = ClassFile.of();
    ClassModel model = api.parse(classfileBuffer);

    // Inspect the model to decide whether a probe actually needs to be inserted.
    // If there is no valid transform yet, skip it.
    return null;
} catch (IllegalArgumentException badClass) {
    // Log a bounded error and do not return a corrupted classfile array.
    return null;
}
~~~

This snippet needs to live inside an existing transformer method, with `className` and `classfileBuffer` in scope, and `import java.lang.classfile.*`. **It does not insert any probes.** Intentionally returning `null` demonstrates the boundary between *analyzing a class* and *instrumenting a class*.

If JDK 24-based code must run in a real agent, check the target JVM runtime **before choosing how to compile/release**. Do not try to fix a missing-API error by adding `--add-exports`: the public package `java.lang.classfile` **simply does not exist on Java 17/21**.

## 9. Reading a Class File and Determining Its Version Before Processing

At the beginning of every classfile is the magic number `CAFEBABE`, followed by `minor_version` and then `major_version`. Therefore, a tool can read the header to learn the version **before** passing the bytes into a version-specific parser:

~~~text
Offset (byte)   Content
0..3            0xCAFEBABE  (magic)
4..5            minor_version (u2, big-endian)
6..7            major_version (u2, big-endian)
8..             constant_pool_count and remaining content
~~~

For example, Java 17 typically has major `61`, minor `0`; Java 24 typically has major `68`, minor `0` if no preview features are used. **Do not assume every non-zero minor version is an error:** preview classfiles have special rules, especially `65535`.

In a Java 24 tool, use `ClassFile.latestMajorVersion()` to know the maximum version supported by the runtime. For files with a higher major version, do not force parsing and expect the tool to understand future instructions/attributes. `ClassFile.parse` may throw `IllegalArgumentException` if the classfile is malformed or uses an unsupported version. Because the model is lazy, errors can also occur in later accessor calls.

**Reading and transforming an old class does not automatically turn it into a new class.** Calling `transformClass` can preserve the major version of the input model. If you actively create a new class with `build` or use new features, **you must verify the output major version** and bytecode instructions/attributes before releasing. Do not edit the two version bytes in the header to "downgrade" a class file: the bytecode may use structures that older JVMs do not support.

## 10. Build Integration and Testing in Real Projects

### 10.1. Java Toolchain in Gradle

For a **separate project** dedicated to a tool/agent running on JDK 24, for example in Groovy DSL `build.gradle`:

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
    options.release = 24
}
~~~

This snippet selects the Java 24 compiler for that project's source. It **does not automatically upgrade other Java 17 modules to 24**; in a multi-module repository, configure toolchain/release per module intentionally.

Use a Gradle Wrapper version capable of running/managing the appropriate JDK 24 toolchain. **Gradle runtime compatibility** and **Java toolchain support** are two different concepts; check [Gradle Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html) for your **actual wrapper version** before upgrading. A Java 24 tool can coexist with a Java 17 app, but they need separate artifacts and test environments.

### 10.2. Recommended Test Matrix

| Test Layer | Test Case | Significance |
|---|---|---|
| Compiler/API | Build tool with JDK 24, `--release 24` | The public `java.lang.classfile` API is visible |
| Negative compile | Try building the same tool source with `--release 17` | Proves the Java 17 API surface does not contain the package |
| Class file input | `javap -verbose` on Java 17 app | Confirms input major 61 |
| Model/parser | `ClassFile.of().parse` and read fields/methods | Verifies the parser understands the input format |
| Transformation | `transformClass` + `verify` | Checks that output does not violate rules detected by the API |
| Runtime target | Run output class on JVM 17 if 17 support is required | Verifies format and dependencies are truly compatible |
| Agent target | Load agent on each declared supported JVM | Verifies agent classes, libraries, loaders, and hooks |
| Regression | Recompile on a newer JDK and inspect output | Detects API/format differences when upgrading JDK |

You should not run tests only on a JDK 24 development machine and then claim Java 17 compatibility. The fact that a tool can parse a Java 17 class **does not prove** an agent using that same tool will run on JVM 17.

## 11. Common Errors and How to Resolve Them

| Symptom | Typical Cause | Resolution |
|---|---|---|
| `package java.lang.classfile does not exist` | Compiler/JDK or `--release` is lower than 24 | Use JDK 24+ for the tool and `--release 24`, or drop the API if targeting older JVMs |
| `UnsupportedClassVersionError` when running the tool | Tool classfile is major 68 while the JVM is 17/21 | Run the tool with JDK 24+ or release a different tool for older runtimes |
| `NoClassDefFoundError: java/lang/classfile/...` | Class has a low major version yet still references Java 24 APIs; older runtime lacks the package | Separate the tool runtime, use `--release` properly, and remove references from older artifacts |
| `ClassFile.parse` throws `IllegalArgumentException` | Corrupted input or classfile version unsupported by the parser | Check magic/version, class bytes, and tool JDK; do not arbitrarily patch headers |
| `ClassFile.verify` returns a list of errors | Generated bytes do not satisfy rules checked by the API | Inspect transforms, stack maps, constant pool, descriptors, and attributes |
| Tool runs, but agent produces no telemetry | Class-File API only reads/writes bytes; `ClassFileTransformer` not registered or no probe inserted | Check `addTransformer` call site, output bytecode, class loader, and instrumentation permissions |
| JDK 24 agent fails to attach to JVM 17 | Target runtime lacks the API/class version required by the agent | Use a Java 17-compatible agent or upgrade the target JVM |
| Classfile is major 61 but still fails on JDK 17 | Code depends on newer APIs/runtime or has incompatible bytecode/attributes | Use `--release 17` for the target, check dependencies, and test on JVM 17 |
| Compiles in IDE but fails in CI | Different IDE/JDK/Gradle toolchains | Explicitly specify toolchain, compiler release, `JAVA_HOME`, and verification pipeline |
| JDK 22/23 preview source does not compile on 24 | Preview API changed before finalization | Migrate to Java 24 Javadocs and recompile |

**Specifically:** `--enable-preview` on Java 17/21 **does not make** Java 24's finalized `java.lang.classfile` available. The preview flag only enables preview features **already present in that specific release**.

## 12. Practice Exercises and Self-Check Questions

### Exercise A — Observe the Three Versions

Run the commands in section 5. Record `javac -version`, `model.majorVersion()`, and `ClassFile.latestMajorVersion()`. Explain why **tool=24** and **target class=17** do not contradict each other.

### Exercise B — Try Compiling the API Source for an Older Release

Change the tool's `javac --release 24` to `--release 17`. Predict the compile error and then run it for real. Distinguish errors caused by a **missing API** from errors caused by a **corrupted input classfile**.

### Exercise C — Change the Input Class Version

Compile `Greeter.java` with `--release 21` and have the JDK 24 tool read it again. The expected major version is **65**. The tool still requires JDK 24, but the target bytecode has changed to 21. Use `javap -verbose` to verify.

### Exercise D — Prepare Deployment for Two Runtimes

Product requirement: two customer groups run JVM 17 and JVM 24, and both need to observe the same method. Propose how to split offline tools or agent artifacts so that **code calling `java.lang.classfile` is never loaded into JVM 17**. Outline the required CI matrix.

### Exercise E — Distinguish Output Class and Tool

In the example, generate `outCopy/demo/Greeter.class` with JDK 24 and try running it with JVM 17 if available. Why is there reason to expect this class to run, whereas `out24/ClassFileApiDemo.class` will not run on JVM 17? Answer based on **major version + API references**, not just the build machine.

### Self-Assessment Questions

1. **In which JDK did `java.lang.classfile` become a standard API?** — **JDK 24, JEP 484**; JDK 22/23 were previews.
2. **Which module does the package belong to?** — **`java.base`**.
3. **Does using the API on JDK 24 require `--enable-preview`?** — **No**, for the finalized Class-File API.
4. **Can a JDK 24 tool read a Java 17 class?** — **Yes**, given a valid classfile and a format supported by the parser.
5. **Can a JDK 24-compiled agent using this API run inside JVM 17?** — **No**, because JVM 17 lacks the API and does not support class major 68.
6. **Does `--release 17` allow importing Java 24 packages?** — **No**.
7. **Does `ClassTransform.ACCEPT_ALL` insert probes on its own?** — **No**, it passes elements through the pipeline.
8. **Does `verify` returning zero replace runtime tests?** — **No**, linkage, class loaders, modules, and runtime behavior still matter.
9. **Why shouldn't you edit the major version in the class header to support older JVMs?** — Because the format, instructions, attributes, and API dependencies may be incompatible.
10. **When should you choose a bytecode library supporting Java 17 instead of the Class-File API?** — When the **tool/agent itself must run on JVM 17**, not merely analyze Java 17 bytecode.

## 13. Key Takeaways and Official Documentation

**The Class-File API is the standard API from JDK 24 for parsing/building/transforming class files**, but **the tool's version**, **the classfile's version**, and **the target JVM's version** must be decided independently. A JDK 24 tool can produce valid Java 17 classes, whereas an agent using the JDK 24 API **must run in a JVM that has the corresponding API**. When releasing for multiple JDKs, verify **`--release`, major_version, API linkage, and test execution on the target JVM**.

Official documentation:

- [JEP 484 — Class-File API (final)](https://openjdk.org/jeps/484): JDK 24 final milestone.
- [JEP 457 — Class-File API (Preview)](https://openjdk.org/jeps/457): JDK 22 preview.
- [JEP 466 — Class-File API (Second Preview)](https://openjdk.org/jeps/466): JDK 23 preview.
- [Java SE 24 — java.lang.classfile package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): models, elements, constant pool, and class-processing API.
- [Java SE 24 — ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `build`, `transformClass`, `verify`, and versions.
- [Java SE 24 — ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ACCEPT_ALL` and transform types.
- [Java VM Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html): `major_version`, `minor_version`, verifier, and classfile structure.
