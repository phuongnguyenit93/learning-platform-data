# Choosing the Class-File API on Supported JDKs and Options for Lower JDKs

**Topic:** Java Advance → instrumentation → **Packaging and Deployment**.

An instrumentation tool needs to read, generate, or transform the bytecode of `.class` files. Since **JDK 24**, Java has an **official Class-File API** in the `java.lang.classfile` package, which helps build class-file processing tools using a standard API without necessarily adding an external bytecode library. However, **applications still running on Java 17, Java 21, or older JVMs do not have this API out of the box**. Choose the API based on the JVM version **running the tool/agent**, the compilation capability of the toolchain, **the input class-file version**, and the JVM **that will load the output bytecode**.

This article answers four concrete deployment questions:

1. **Which JDKs can use `java.lang.classfile`?** Preview milestones, stable release, compiler flags, and changes across releases.
2. **What if the host only has JDK 17/21?** Use a suitable bytecode library such as **ASM** or a higher-level tool like **Byte Buddy**, or use `javap` when only manual reading is needed.
3. **How to package for multiple JVMs?** Separate artifacts, shared API, and the **multi-release JAR** option, avoiding linkage to classes that do not exist on lower runtimes.
4. **How to verify?** Check the major version, parser support for the input format, agent loading capability, bytecode validity, and application behavior.

Two labs have complete source code: **Java 17 + ASM** and **Java 24+ + Class-File API**, both reading **the same Java 17 class file**. They help clearly distinguish between the "JDK running the tool" and the "bytecode version the tool is analyzing."

> **Core rule:** Use the standard Class-File API when the **tool's runtime is JDK 24+** and the required features are supported by that JVM. Use ASM/Byte Buddy or a compatible engine when the **runtime must still support lower JDKs**, while pinning a library version new enough for the class files to be read/written. Do not use `jdk.internal.org.objectweb.asm` as a stable application API.

## 1. Version Support Matrix

| Environment | Class-File API Status | Which Option to Choose? |
| --- | --- | --- |
| JDK 8–21 | **No** `java.lang.classfile` as a standard API for direct use | Compatible ASM/Byte Buddy version, or `javap`/custom tool |
| JDK 22 | **First preview — JEP 457** | Use only if preview flags and an API subject to change are acceptable |
| JDK 23 | **Second preview — JEP 466** | Still requires preview flags; do not treat as a stable API for broad release |
| JDK 24 | **Official API — JEP 484** | Use `java.lang.classfile` directly; `--enable-preview` is not required for the API itself |
| JDK 25+ with standard API | Class-File API continues to be available; details may be extended per JDK | Read the Javadoc for the exact JDK version, test on the actual runtime |

These milestones are **API history**, not a guarantee that older JVMs can run classes compiled by JDK 24. A class file from `javac --release 24` has **major version 68**, whereas Java 17 understands at most class-file major **61** for normal non-preview classes. Java 21 is **65**, Java 22 is **66**, and Java 23 is **67**.

Do not confuse three independent variables:

- **Compiler JDK**: which `javac` version the build machine uses.
- **Runtime JDK**: which `java` version the process running the agent/tool or application uses.
- **Class-file target major**: which version the output bytes contain in the `ClassFile` header.

A tool running on JDK 24 can **read a Java 17 class file** (major 61). However, `JdkInspector.class` itself, compiled with `--release 24`, cannot run on Java 17. If the tool needs to run directly inside a Java 17 process, a different engine must be provided.

### 1.1. Preview Is Not the Same as the Official API

In JDK 22/23, `java.lang.classfile` was a **preview API**. When compiling/running code that references a preview API, you must use the preview options matching **the exact JDK version in use**. For example, for JDK 23:

```bash
# Example when using the JDK 23 preview API;
# source must be written against the exact JDK 23 API signatures.
javac --enable-preview --release 23 -d out23 src23/demo/PreviewInspector.java
java --enable-preview -cp out23 demo.PreviewInspector
```

**This is an illustrative command for a separate preview project**, not the command to run the JDK 24 sources in the lab below. Preview code may require source edits when moving from JDK 22 to 23 or 24; a preview artifact from one release must not be considered binary-compatible with every other release. Class files using preview features may have **minor version 65535** and are restricted to running on the exact corresponding major release.

**Deployment recommendation:** for production systems, prefer the stable API from JDK 24 or a bytecode library engine that inherently supports lower JDKs. Avoid designing a binary using a preview API and treating it as a universal release solution.

## 2. What Does the Standard Class-File API Provide?

The main packages in the **`java.base` module** starting from JDK 24:

```text
java.lang.classfile
java.lang.classfile.attribute
java.lang.classfile.constantpool
java.lang.classfile.instruction
```

No Maven dependency is needed for this API itself on JDK 24+. Commonly used components:

| Component | Role |
| --- | --- |
| `ClassFile` | API context and options; created via `ClassFile.of()` |
| `ClassFile.parse(byte[])` / `parse(Path)` | Parses bytes/files to produce a `ClassModel`; called on a `ClassFile` instance |
| `ClassModel` | Immutable model of a class file, containing class name, version, fields, methods, attributes |
| `FieldModel`, `MethodModel` | Models for members and descriptors |
| `CodeModel`, `Instruction` | Bytecode and elements inside the `Code` attribute |
| `ClassTransform`, `MethodTransform`, `CodeTransform` | Transformation pipelines via builders |
| `ClassFile.build(...)` | Generates a class file |
| `ClassFile.verify(...)` | Helps check a class file, **does not replace** running the JVM verifier/behavior tests |

Correct syntax:

```java
ClassFile context = ClassFile.of();
ClassModel model = context.parse(bytes);
```

This is a **fragment**: it requires importing `ClassFile`/`ClassModel` and having a `byte[] bytes` variable. `parse` is an **instance method of the context**; you should not write `ClassFile.parse(bytes)` as a static call.

The API models are designed to be immutable/lazy: obtaining a `ClassModel` does not mean every method/instruction has already been parsed or deeply verified. An `IllegalArgumentException` may appear later when reading an accessor because data is decoded on demand. Parsing does not automatically load/initialize the target class via `Class.forName`.

### 2.1. When to Prefer the Standard API?

- A tool/agent **only needs to run on JDK 24+**, wants to minimize dependencies, and stay closely aligned with the JDK's class-file format.
- Need to inspect bytecode, traverse fields/methods, analyze symbolic operands, or generate/transform class files using a typed API.
- Want to avoid relying on the **JDK internal ASM fork**.
- Have a clear scheduled JDK upgrade process, tested against the specific production JDK.

The standard API does not solve everything: you still need to understand the JVM verifier, frame computation, class loaders, module access, class-file versions, transformer chaining, and semantics. It is not an API that "automatically adds correct tracing to every method."

### 2.2. Can a JDK 24 Tool Read Java 17 Bytes?

Yes, if the class file is valid and the format is supported by the API. For example, a JDK 24 tool can parse a major 61 class generated by `javac --release 17`. However, the reverse **is not true**: a Java 17 JVM cannot load a major 68 class from the JDK 24 tool, and `java.lang.classfile` does not exist in the Java 17 runtime.

**You must separate the tool's runtime from the output's runtime.** A build-time tool running on JDK 24 can generate bytes targeting Java 17, but that output will only run on Java 17 if the **class-file major, instructions, referenced APIs, and constraints** are compatible. When generating a class with a builder, you need to control the appropriate class version (`ClassBuilder.withVersion(...)` where appropriate) and verify all instructions/API references before release.

## 3. When You Only Have JDK 17/21, What to Choose?

### 3.1. ASM — Direct Bytecode Layer

**ASM** is a class-file processing library independent of `java.lang.classfile`. Its core APIs:

- `ClassReader` reads bytes and invokes `ClassVisitor`/`MethodVisitor`.
- `ClassWriter` generates a class file, or serves as the target receiving transformer output.
- `MethodVisitor` reads/inserts instructions using JVM opcodes.
- `AdviceAdapter` in the `asm-commons` artifact helps insert hooks at method entry/exit; exceptional exits must be handled properly.
- `CheckClassAdapter` in `asm-util` is useful for checking output structure and debugging.

Choose an **ASM version new enough** for the **highest major version the tool will encounter**, not just for the JDK running the library. For example, **ASM 9.7.1** added the `Opcodes.V24` constant (Java 24), and **ASM 9.9** added support for later versions; check the ASM release page before attempting to parse class files from even newer JDKs.

A Java 17 tool class using ASM can process class files compiled by a higher JDK **if that ASM version supports the format**, even though it cannot run those classes on Java 17. Conversely, an ASM library that is too old may report `Unsupported class file major version ...` when reading newer inputs.

### 3.2. Byte Buddy — Higher-Level API

**Byte Buddy** helps generate subclasses, intercept methods, and build instrumentation agents based on a declarative model; it typically uses ASM under the hood. When the goal is "instrument method X to measure duration" and you do not want to manage every opcode directly, Byte Buddy can reduce effort.

However, you must verify that the **Byte Buddy version supports the runtime JDK and class-file version**; agents also depend on class-loader constraints, module visibility, and attach/retransform permissions. Byte Buddy on Java 17 does not magically make a Java 17 JVM understand Java 24 class files.

### 3.3. `javap` — Simple Choice for Reading Only

If you only need to **print class-file information** for diagnostics:

```bash
javap -verbose -p -c -classpath target/classes demo.Sample
```

The JDK's `javap` reads class files and prints a human-readable dump; it does not provide a typed manipulation API like ASM/Class-File API and does not output transformed class files. It is great for QA of bytes before/after instrumentation, but if deep automated structural analysis is needed, use a dedicated API/library.

### 3.4. Do Not Rely on `jdk.internal.org.objectweb.asm`

The JDK has an **internal** ASM implementation/fork serving JDK components, but it **is not a public API with stability guarantees** for applications/agents:

```java
// Not recommended for production code:
import jdk.internal.org.objectweb.asm.ClassReader;
```

The line above is an **anti-pattern fragment**. On JDK 9+, module encapsulation can prevent code from compiling/running without `--add-exports`, and versions/semantics/internal packages can change between JDKs. `--add-exports` is a JVM-dependent workaround, **not** something that turns that internal package into a standard API. It is better to use the official ASM artifact or the Class-File API from JDK 24.

## 4. Comparison Lab: Same `.class` File, Two Engines

Goal: compile **`demo.Sample` to major 61 (Java 17)**, then use:

1. **ASM engine running on JDK 17+**, with a Maven dependency.
2. **Class-File API engine running on JDK 24+**, without an ASM dependency.

Both engines print the same class name, major version, signatures, and whether a method has a `Code` attribute. We **do not need to load `demo.Sample` into the JVM** to inspect the class file.

Directory structure:

```text
class-file-choice/
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               ├── Sample.java
│               └── AsmInspector.java
└── modern-src/
    └── demo/
        └── JdkInspector.java
```

To run the ASM branch, you need **JDK 17+ and Maven 3.x**, and the machine must be able to download dependencies from Maven Central or an internal cache. To run the standard branch, you need **JDK 24+**; both will read `target/classes/demo/Sample.class` compiled by Maven with `--release 17`.

### 4.1. File `src/main/java/demo/Sample.java`

```java
package demo;

public final class Sample {
    private Sample() {}

    public static int plus(int value) {
        return value + 1;
    }
}
```

The sample class is very short, with a private constructor and one method. This is **data for the inspector**, so `Sample` itself does not need a `main` method.

### 4.2. Maven `pom.xml` — Java 17 + ASM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>class-file-choice</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.9</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Maven locks `maven.compiler.release=17` and a specific ASM version. `pom.xml` includes the third-party artifact `org.ow2.asm:asm`, so deployment must carry that dependency; JDK 17 does not provide a public ASM API on the classpath.

### 4.3. File `src/main/java/demo/AsmInspector.java`

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class AsmInspector {
    private AsmInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: AsmInspector <class-file-path>");
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassReader reader = new ClassReader(bytes);

        System.out.println("ENGINE=ASM");
        reader.accept(new ClassVisitor(Opcodes.ASM9) {
            @Override
            public void visit(
                    int version, int access, String name,
                    String signature, String superName,
                    String[] interfaces) {

                System.out.println("CLASS=" + name);
                System.out.println("MAJOR=" + (version & 0xffff));
            }

            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {

                return new MethodVisitor(Opcodes.ASM9) {
                    boolean hasCode;

                    @Override
                    public void visitCode() {
                        hasCode = true;
                    }

                    @Override
                    public void visitEnd() {
                        System.out.println("METHOD=" + name
                                + descriptor + " HAS_CODE=" + hasCode);
                    }
                };
            }
        }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
    }
}
```

**Explanation:**

- `ClassReader` parses bytes; `reader.accept` invokes the visitor instead of having to manually read offsets/constant-pool entries.
- `visit` receives the **internal class name** `demo/Sample` and the class-file version. `version & 0xffff` extracts the lower 16 bits (major version) of ASM's version value.
- `visitMethod` creates a `MethodVisitor` for each method. `visitCode` runs when the method has a `Code` attribute; `visitEnd` prints `HAS_CODE` exactly once.
- Passing `SKIP_DEBUG` and `SKIP_FRAMES` in the lab is only to avoid processing debug tables/stack frames; **do not** set `SKIP_CODE` because it would misidentify code presence.
- This program is **read-only** and does not produce a transformed class. With ASM, you can insert code using `ClassWriter` and visitors, but you must preserve `max_stack`/`max_locals`, stack map frames, exception handlers, and semantics.

### 4.4. Running the ASM Engine on JDK 17+

From the `class-file-choice` directory:

```bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.AsmInspector -Dexec.args=target/classes/demo/Sample.class
```

Application stdout (excluding Maven/plugin logs):

```text
ENGINE=ASM
CLASS=demo/Sample
MAJOR=61
METHOD=<init>()V HAS_CODE=true
METHOD=plus(I)I HAS_CODE=true
```

Both methods have `Code`. `<init>()V` is the private constructor, and `plus(I)I` is the method taking and returning an `int`. `MAJOR=61` because Maven compiled with `release=17`, even if you happen to run Maven on JDK 24.

**Runnability:** `AsmInspector` source code uses only Java 17 syntax/APIs and the public ASM library. It runs on Java 17+ when the compatible ASM 9.9 dependency is present, though whether it can parse higher major class files depends on the ASM version; that does not mean JVM 17 can **load/run** classes of that major version.

### 4.5. File `modern-src/demo/JdkInspector.java`

```java
package demo;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public final class JdkInspector {
    private JdkInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: JdkInspector <class-file-path>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        System.out.println("ENGINE=CLASS_FILE_API");
        System.out.println("CLASS=" + model.thisClass().asInternalName());
        System.out.println("MAJOR=" + model.majorVersion());

        for (MethodModel method : model.methods()) {
            System.out.println("METHOD="
                    + method.methodName().stringValue()
                    + method.methodType().stringValue()
                    + " HAS_CODE=" + method.code().isPresent());
        }
    }
}
```

This file is a **standalone Java 24+ program** without needing the ASM library. `ClassFile.of()` creates the context; `parse(Path)` returns a `ClassModel`. `methods()` lists the methods; `code().isPresent()` distinguishes a method with a `Code` body from an `abstract`/`native` method.

### 4.6. Running the JDK Engine on JDK 24+

After Maven has generated `target/classes/demo/Sample.class` (major 61), switch to JDK 24+ and run from the root directory:

```bash
java -version
javac -version
javac --release 24 -d modern-classes modern-src/demo/JdkInspector.java
java -cp modern-classes demo.JdkInspector target/classes/demo/Sample.class
```

Stdout with the exact same Java 17-compiled `Sample`:

```text
ENGINE=CLASS_FILE_API
CLASS=demo/Sample
MAJOR=61
METHOD=<init>()V HAS_CODE=true
METHOD=plus(I)I HAS_CODE=true
```

**Comparison with ASM output:** only the engine name differs; the class/major/method information read is identical. This verifies "one input format — two engines" rather than just checking whether the compiler can find `java.lang.classfile`.

**Note:** `JdkInspector.class` from `--release 24` has **major 68**. It runs on JDK 24+ (while the API remains compatible), but `java -cp modern-classes ...` on JDK 17 will fail with `UnsupportedClassVersionError` before it even gets a chance to parse the Java 17 input. The output `MAJOR=61` is **the class file being read**, not the major version of the inspector itself.

## 5. Class-File API on JDK 24: Transform Instead of Mutating Input

The standard API is not just for inspection; it provides builders and transforms:

```java
// Fragment that runs on JDK 24+.
// Requires importing java.lang.classfile.ClassFile;
// java.lang.classfile.ClassModel;
// java.lang.classfile.ClassTransform.

ClassFile context = ClassFile.of();
ClassModel model = context.parse(inputBytes);

byte[] output = context.transformClass(
        model, ClassTransform.ACCEPT_ALL);
```

`inputBytes` must be a prepared class-file `byte[]`. `ClassTransform.ACCEPT_ALL` passes existing elements to the builder; the output is **a new byte array** describing the class file, and **must not be assumed to be byte-for-byte identical to the input** in all cases (constant-pool/attribute layout may change due to writer/options).

If you actually insert instructions, you must delegate transformations to method/code transforms and handle stack maps, locals, branch targets, try/catch blocks, constructors, and annotations. **Do not** insert arbitrary bytes using fixed offsets; do not mutate `classfileBuffer` passed by the JVM to `ClassFileTransformer` in place.

An additional verification snippet:

```java
// JDK 24+ fragment, applied after obtaining byte[] output.
var errors = ClassFile.of().verify(output);
System.out.println("VERIFY_ERRORS=" + errors.size());
```

`verify` helps catch certain class-file issues, **but does not replace** loading the class on the target JVM, testing method behavior, and running the real runtime verifier. Even if `VERIFY_ERRORS=0`, that does not guarantee the new code has correct business logic or can run on a lower JDK.

### 5.1. Transforming Class Files for Lower Runtimes

A tool running on JDK 24 can produce output class files targeting **Java 17** if the output satisfies all conditions:

1. Class-file header **major 61** (and appropriate minor), not the tool's default major 68.
2. No opcodes, constant-pool forms, attribute semantics, or language/runtime features unsupported by Java 17.
3. No calls to APIs that only exist on Java 24 from classes released for Java 17.
4. Stack map frames and handlers are valid for the Java 17 verifier.
5. Run **integration tests on an actual Java 17 JVM**, not only on JDK 24.

When building a class from scratch in the Class-File API, `ClassBuilder.withVersion(61, 0)` is an API to choose the version **for the built class**, but merely setting the version number **does not automatically strip** incompatible bytecode features. When transforming a Java 17 input, first verify that the output has the right version; do not assume the engine preserves/downgrades the version as a blanket guarantee for every option.

## 6. Why `javac --release 17` Cannot Fix a Missing API

`javac --release N` does not just set the class-file major version; it restricts the **Java platform APIs** that source code can reference to release N.

If you run on JDK 24:

```bash
javac --release 17 -d out modern-src/demo/JdkInspector.java
```

then source importing `java.lang.classfile.ClassFile` **is invalid against the Java 17 API surface**, because the `java.lang.classfile` package did not exist in Java 17. If instead you use:

```bash
javac --release 24 -d out modern-src/demo/JdkInspector.java
```

the compiler finds the API, but the output major 68 class file requires JDK 24+ to run.

**There is no single `--release` option that both "calls an API introduced in Java 24" and "runs directly on Java 17."** To support Java 17, you must:

- Use a compatible independent library (ASM/Byte Buddy).
- Run the analysis/transformation step in a **JDK 24 build-time** process and ship only output bytes that are genuinely Java 17 compatible.
- Or separate implementations per JVM version using an appropriate strategy/packaging.

This is especially critical for **Java agents**: if the manifest `Premain-Class` points to a major 68 class or static imports/calls that only exist in Java 24, starting `-javaagent` on Java 17 can fail **before the application's `main` runs**.

## 7. Packaging for Multiple Runtimes: Three Strategies

### 7.1. Option A — Support JDK 24+ Only

Simplest if all production runtimes are already on JDK 24+:

```text
agent-modern.jar
  META-INF/MANIFEST.MF
    Premain-Class: demo.ModernAgent
  demo/ModernAgent.class          (target JDK 24+)
  demo/ModernTransformer.class    (uses java.lang.classfile)
```

Build with `--release 24` or the corresponding JDK toolchain; compile and run tests on the minimum committed JVM. No ASM runtime dependency is needed if ASM is not used elsewhere.

**Risk:** if a deployment slot is still on Java 17/21, the agent JAR can halt the JVM on load with `UnsupportedClassVersionError` or `NoClassDefFoundError`. Do not attach a modern artifact to every runtime without a compatibility matrix.

### 7.2. Option B — Two Independent Artifacts

Produce **two JARs for two runtime groups**:

```text
agent-legacy.jar    Java 17 bytecode + compatible ASM/Byte Buddy
agent-modern.jar    Java 24 bytecode + java.lang.classfile

Deployment:
  runtime JDK 17 / JDK 21 -> agent-legacy.jar
  runtime JDK 24+         -> agent-modern.jar
```

This is the **recommended model when you want low complexity**:

- Each JAR has a valid `Premain-Class` for its corresponding runtime.
- Separate build/test pipelines: `--release 17`, `--release 24`.
- Can share a common **API module** built for Java 17 containing no references to `java.lang.classfile`.
- CI tooling or container images **select the JAR at deploy time**, rather than fragile runtime regex parsing of `java -version`.
- ASM must be bundled/selected on a valid classpath; if shading/fat-JAR is chosen, consider relocation, licenses, signatures, and dependency clashes.
- The modern runtime can still read older data/class files. Behavioral tests should compare the legacy and modern engines.

**Avoid** building a JAR with a Java 24-compiled `Premain-Class` and hoping `if (Runtime.version().feature() < 24)` can save Java 17. The JVM **must load the entrypoint class itself before executing the `if` branch**, so class version/linkage errors can occur very early.

### 7.3. Option C — Multi-Release JAR (MR-JAR)

Since Java 9, a **multi-release JAR** can contain **the same class name** at the baseline and an alternative version for newer runtimes:

```text
inspector-mr.jar
├── META-INF/MANIFEST.MF
│     Multi-Release: true
│     Premain-Class: demo.AgentBootstrap
├── demo/AgentBootstrap.class            # Java 17 baseline
├── demo/Inspector.class                 # Java 17+ implementation, using ASM
└── META-INF/versions/24/
      └── demo/Inspector.class           # Java 24+ implementation,
                                          # using java.lang.classfile
```

**Packaging diagram, not a pre-built MR-JAR.** On Java 17/21, the runtime picks the root `demo.Inspector`. On Java 24+, it can pick the versioned class under `META-INF/versions/24`. Note:

1. **Bootstrapping:** `Premain-Class`/entrypoint at the root must **be loadable on the minimum JVM**, e.g., major 61 if Java 17 is committed. Do not reference Java 24 classes directly in the root's static initializer.
2. **Preserve binary contract:** root and versioned implementations must have APIs/signatures compatible with older callers; the versioned API must not accidentally change the public contract when another version is selected.
3. **Maven dependencies:** the root ASM implementation still depends on ASM and must be packaged properly; the versioned implementation must not require JDK 24 APIs in root code.
4. **Metadata:** the manifest must have `Multi-Release: true`. Placing files under `META-INF/versions/24` without the manifest entry is not enough.
5. **Build:** use a JDK new enough to create versioned classes; compile root with `--release 17`, compile versioned with `--release 24`; do not mix classes into the wrong path.
6. **Validate:** run `jar --validate --file inspector-mr.jar` with a JDK that has the appropriate MR-JAR tool; test on both Java 17 and Java 24.
7. **Class loading:** when an agent applies custom loader/module rules, actually verify that the right implementation is selected; do not assume every custom classloader/JAR processor understands MR-JARs like the system loader does.

MR-JAR reduces the number of deployment artifacts, **but increases build, dependency packaging, and test matrix complexity**. It is not necessarily worth choosing if two separate JARs suffice.

## 8. A Shared API Keeps Both Engines from Leaking into the Application

Instead of letting every application class import ASM or `java.lang.classfile`, define a **boundary interface** compiled for Java 17:

```java
package demo.api;

public interface ClassInspector {
    InspectionResult inspect(byte[] classFile);
}
```

This is an **architectural fragment**: `InspectionResult` must be defined in the API module using Java 17-compatible types. The idea:

```text
                         Shared API (Java 17 baseline)
                         ClassInspector.inspect(byte[])
                                  │
                   ┌──────────────┴───────────────┐
                   ▼                              ▼
          AsmInspectorImpl                 JdkInspectorImpl
          runtime Java 17+                 runtime Java 24+
          org.ow2.asm                      java.lang.classfile
                   │                              │
                   └──────────────┬───────────────┘
                                  ▼
                      Normalized InspectionResult
```

If you need to select an implementation at runtime via `ServiceLoader` or a strategy factory:

- Ensure the Java 24 provider **is not loaded on Java 17**. Merely placing the file/class in the JAR does not make it safe if Java 17 code calls `Class.forName` or eagerly scans it.
- Declare service providers matching versioned packaging. If Java 17 sees a major 68 service provider class and tries to instantiate it, it will fail.
- Return neutral DTOs instead of returning `ClassModel` or `ClassNode` directly in the shared API, if the goal is to swap engines independently.
- Tests for **method owners, descriptors, attributes, and instruction behavior** must compare meaningful results, not just text dumps that differ in layout.

A dispatcher that only checks `Runtime.version().feature() >= 24` is a **necessary condition, not sufficient**: that VM must have the corresponding API and the right implementation class packaged; do not leave static references that break linkage before dispatch.

## 9. Agent Startup Layer and Loading Risks

A Java agent declares:

```text
Premain-Class: demo.AgentBootstrap
Can-Retransform-Classes: true
```

When the JVM sees `-javaagent:agent.jar`, it loads `demo.AgentBootstrap` and calls `premain`. If this root class is built as major 68 while production runs Java 17, the JVM can halt **before application `main`**.

Better:

```text
Java 17-compatible bootstrap:
    receives Instrumentation
    selects compatible engine by runtime/configuration
    registers ClassFileTransformer
    does not directly import java.lang.classfile

Versioned implementation:
    Java 17: ASM
    Java 24+: java.lang.classfile
```

This is **architectural pseudocode**, not a complete Java class. If the agent is required to start on JDK 17, the bootstrap must be built and tested on real Java 17. **Do not** assume the module system opens all packages to the agent; when instrumenting classes in named modules, you may need `Instrumentation.redefineModule`/opens packages according to policy.

Both engines, when receiving `classfileBuffer`, must:

- **Not mutate** the input array provided by the JVM.
- Return `null` when not modifying the class.
- Return a **new output array** containing valid class-file bytes when actually transforming.
- Not instrument logger/transformer helpers themselves in a way that causes recursive loading.
- Control target version, loaders, frames, branch targets, exception handlers, and constructor semantics.
- Account for transformer ordering and retransform/redefine constraints (do not arbitrarily add fields/methods when the VM disallows it).
- Not assume "same hash" output even when logic is equivalent: constant pool/method ordering/attributes may differ.

A common deployment failure source is **shading ASM** without testing relocation or omitting required `asm-commons`/`asm-util` dependencies. Packages missing from the JAR can cause `NoClassDefFoundError` inside `premain`/transformer.

## 10. Five Compatibility Layers to Check Separately

| Compatibility Layer | Question | Example Failure |
| --- | --- | --- |
| **1. Tool runtime API** | Does the JDK running the inspector/agent have `java.lang.classfile` or the ASM dependency? | `NoClassDefFoundError: java/lang/classfile/ClassFile` |
| **2. Tool bytecode version** | What major version of `Inspector.class` can the JVM running the tool load? | `UnsupportedClassVersionError` when a 24-compiled agent runs on JDK 17 |
| **3. Input format** | Does the parser support the target class file's major/attributes/opcodes? | Older ASM reports unsupported class file major |
| **4. Output class format** | Are the generated bytes valid in version, frames, references, and class structure for the target runtime? | `ClassFormatError`, `VerifyError` |
| **5. Packaging/loader** | Are the agent entrypoint, dependencies, MR-JAR resolution, and module visibility correct? | `ClassNotFoundException` / `NoClassDefFoundError` |

Distinguish **"tool can read a new class file"** from **"old JVM can run a new class file."** ASM 9.9 can parse high-major bytes in a tool running on Java 17 if the library supports it, but a Java 17 VM still cannot define a class with major above 61.

### 10.1. Checking the Class-File Header

A `.class` file starts with:

```text
u4 magic             0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

To see the actual major version of a class:

```bash
javap -verbose -classpath target/classes demo.Sample
```

Look for the line `major version: 61` in the output, since the sample was compiled by Maven with `--release 17`. Do not mistake the `java -version` of the inspector command for the version of the file being read.

For generated/transformed class files, log **input major** and **output major** separately in QA logs. If output targeting Java 17 unexpectedly has major 68, the build pipeline chose the wrong target or the transform did not preserve the version policy.

## 11. Testing Modules and Programs Across Multiple JDKs

A practical QA matrix:

| Case | JVM Running Tool | Input Class | Expectation |
| --- | --- | --- | --- |
| ASM Java 17 | JDK 17 | Java 17 major 61 | Parses and prints metadata correctly |
| ASM Java 17 | JDK 21 | Java 17 major 61 | Runs with the right ASM dependency |
| ASM Java 17 | JDK 24 | Java 17 major 61 | Equivalent metadata results |
| Class-File API | JDK 24 | Java 17 major 61 | Parses and prints metadata correctly |
| Class-File API | JDK 24 | Java 24 major 68 | Parses when the class file is valid |
| Class-File API class major 68 | JDK 17 | Java 17 major 61 | **Tool fails to load**: `UnsupportedClassVersionError` |
| Older ASM | JDK 17 | Class major newer than supported | Parser rejects; upgrade ASM version |
| Agent producing new bytecode output | Committed target JVM | Transformed class file | JVM verifier, behavior, and loading must all pass |

Note that the Java 17 lab running on JDK 24 still prints **major 61** if the input `Sample.class` was built by Maven with `release=17`. That is the intended test outcome.

### 11.1. Separating Tests by Level

**Level 1 — Parser tests:** input `.class` files of various versions, checking names, method descriptors, and attributes. Because of lazy parsing, you must traverse the used elements to catch deferred errors.

**Level 2 — Structural diff:** map methods by **name + descriptor**, CP entries by symbolic references (not raw indices). If two engines output different field/method/constant-pool ordering, do not jump to concluding semantic differences.

**Level 3 — Bytecode verification:** `ClassFile.verify(...)` on JDK 24 or ASM's `CheckClassAdapter` (when `asm-util` is added), together with **loading the output on the target JVM**. Errors in stack maps, max locals, or branch offsets may only surface when the class is verified.

**Level 4 — Behavioral tests:** compare return values, exceptions, side effects, concurrency, class loader boundaries, and coexisting agents. Passing a verifier does not prove instrumentation logic is correct.

**Level 5 — Deployment tests:** run `-javaagent` from the production launch script across the entire JDK matrix, checking classloaders, module rules, dependencies, startup failures, and restart/rollback.

## 12. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `package java.lang.classfile does not exist` | Using JDK ≤ 21 compiler or `--release 17/21` | Use JDK 24+ and `--release 24` for the modern implementation |
| `ClassFile` reported as preview | Using JDK 22/23 | Use the exact release's preview flags, or move to JDK 24+ |
| `UnsupportedClassVersionError` when running modern tool on JDK 17 | Tool class major 68 > target JVM 61 | Use ASM fallback JAR or upgrade the runtime |
| `NoClassDefFoundError: java/lang/classfile/ClassFile` | Runtime lacks the standard API | Do not run the Java 24 implementation on JDK 17/21 |
| ASM `Unsupported class file major version` | ASM is too old for the input | Upgrade ASM per official compatibility/releases |
| `ClassFormatError` | Malformed output, invalid CP/attributes | Parse/write with the proper API, inspect bytes |
| `VerifyError` | Incorrect stack maps, operand stack, or handler ranges | Recompute frames and verify on the target JVM |
| `ClassNotFoundException` for inspector/agent | Wrong path, manifest, or classloader | Check JAR entries and `Premain-Class` |
| `NoSuchMethodError` after engine upgrade | API version/library conflict or old preview code | Pin proper dependencies and check linkage |
| `NoClassDefFoundError: org/objectweb/asm/...` | ASM not bundled or invisible to classloader | Package dependency, shade/relocate per policy |
| `IllegalArgumentException` while parsing | Corrupt/unsupported class file or lazy accessor failure | Identify the offending getter/opcode, inspect input |
| MR-JAR selects the wrong implementation | Missing `Multi-Release: true`, wrong path, or custom loader | `jar --validate`, inspect manifest, test each JDK |
| `Premain-Class` compiled targeting JDK 24 | Bootstrap cannot run on JDK 17 | Build root bootstrap with `--release 17` |
| Output class runs on JDK 24 but fails on JDK 17 | Incompatible major/API reference/instructions | Verify and run regression tests on real JDK 17 |
| Overwriting input `classfileBuffer` | Violates `ClassFileTransformer` contract | Parse input read-only, return new output bytes, `return null` if unchanged |
| Repeated agent runs duplicate hooks | Transformer lacks idempotency | Check hook symbols, test multiple retransform passes |
| Agent/ASM library conflict | Different package/module/shaded versions | Isolation/relocation, startup integration tests |
| `javap` missing a method | Looking at wrong JAR/classpath or class loader | Snapshot input/output at the right stage, use `javap -classpath` |
| Java 17 with ASM still cannot load major 68 | Parser differs from JVM verifier/loader | Read offline only; target class must be Java 17 compatible |

**Do not "fix" this by changing class-file major 68 to 61 via editing a few header bytes.** The bytecode may use constructs not understood by Java 17, and method references may point to nonexistent APIs. That is a "fake version downgrade," not a proper backport.

## 13. Responsible Packaging: Dependencies, Modules, and Runtime Permissions

### 13.1. Choosing Maven Dependencies Clearly

For ASM, use the artifact/version declared in `pom.xml` and check SBOM/licenses. If `AdviceAdapter` is needed, add `asm-commons` at the matching version; if `CheckClassAdapter` is needed, add `asm-util`. Do not mix ASM artifacts of different minor versions assuming API compatibility.

If the application already pulls in another ASM version, consider **tested** shading/relocation, especially when the Java agent is loaded alongside the application classpath. By contrast, Java 24 `java.lang.classfile` lives in `java.base`, so you do not package a copy of the API into the JAR.

### 13.2. Modules and Classloaders in Java Agents

When instrumenting classes from named modules, merely having `Instrumentation` in the agent does not mean modules allow all reflective access. If deep access is required, design `redefineModule`/opens/exports with proper scope. Java agent helper classes must be loaded by the right loader or a bridge loader if instrumenting bootstrap/system classes; avoid dependencies unavailable when the JVM defines the target.

On lower runtimes, do not let the Java 17 bootstrap directly reference a major 68 modern engine through static fields, superclasses, signatures, or eager service loading. Separating with an `if` alone is not always enough because class verification/linkage can happen before the branch is evaluated.

### 13.3. Inspecting Release Artifacts

For JAR/MR-JAR and class files:

```bash
jar tf agent-legacy.jar
jar tf agent-modern.jar
jar --validate --file inspector-mr.jar
javap -verbose -classpath target/classes demo.Sample
```

These are **illustrative commands**; `agent-legacy.jar`/`agent-modern.jar`/`inspector-mr.jar` only exist after you build the corresponding artifacts. `jar tf` shows JAR entries, `jar --validate` checks various MR-JAR constraints, and `javap -verbose` displays class-file major. **Do not** treat `jar --validate` as sufficient proof that the agent will start on every JDK.

### 13.4. Avoid Guessing "One Engine Runs on Every JDK"

Define the compatibility policy by the **actual baseline runtime**:

```text
Runtime deployment matrix
  Java 17/21:
      Java 17 bootstrap + ASM engine
      code target release 17
  Java 24+:
      Java 24 Class-File API engine
      output target release per workload
  Common:
      method signatures, normal/error behavior,
      output class verification, module/access rules
```

This is a strategy diagram, not shell commands. Where both must be supported, build separately, test separately, and roll out with rollback capability. If JDK 24+ was expected but Java 17 is actually running in the container, fix the **runtime image/launcher config or choose the legacy artifact**; do not just change `JAVA_HOME` in a developer terminal.

## 14. Security and Agent Operations

A Java agent loaded at startup runs with the privileges of the JVM process and can alter class definitions. Essential practices:

- Use only trusted artifacts, lock checksums/signatures/sources, and verify the supply chain.
- Do not log arguments, secrets, or entire input bytes to production logs unnecessarily.
- Limit instrumentation targets; do not insert hooks into logger/agent support classes that cause recursive class loading.
- Test callback paths on both Java 17 and Java 24+, especially retransform, exception exits, and constructors.
- Monitor CPU/memory/GC overhead of parsing, frame computation, and bytecode transforms.
- Never load an incompatible agent into a production JVM just to try it out; always test in an equivalent environment.
- Separate bytecode format tests from business behavior tests and rollback tests.
- When auto-upgrading the JDK, upgrade/test the ASM version if used; do not assume "a newer JDK will make old ASM read new bytecode."

## 15. Decision Checklist

- [ ] Verify the **JVM currently running the tool/agent** (not just the build machine).
- [ ] If the runtime is Java 24+, consider stable `java.lang.classfile`.
- [ ] If the runtime is below Java 24, choose a compatible ASM/Byte Buddy version.
- [ ] If using JDK 22/23 preview, apply the proper preview flags and accept API changes.
- [ ] Check the Java tool's class major version and API references; do not "force `--release 17`" on code calling Java 24 APIs.
- [ ] Check input class major, unsupported attributes/opcodes, and ASM/JDK parser support.
- [ ] Determine the output class major version and the runtime where the output must be loaded by the JVM.
- [ ] For output targeting Java 17, test on a real Java 17 JVM; do not verify only on JDK 24.
- [ ] Choose one modern artifact, two artifacts, or an MR-JAR based on operational cost.
- [ ] If using an MR-JAR, the root bootstrap must be compatible with the baseline JDK and the manifest must have `Multi-Release: true`.
- [ ] Check ASM dependencies, relocation/shading, Java agent classloader, and JPMS visibility.
- [ ] For transformers, do not mutate `classfileBuffer` and handle `return null` per contract.
- [ ] Test load/retransform/redefine, exception paths, class schema constraints, and idempotency.
- [ ] Run regression tests across the JDK matrix, vendor/OS, and module/classloader cases.
- [ ] Document clearly what is verified by source checks, unit tests, verifier, and runtime behavior.

## 16. Self-Check Questions

1. **Does JDK 21 have the standard `java.lang.classfile` API?**  
   No. Use ASM/Byte Buddy or upgrade the tool runtime.

2. **Can JDK 22 use the Class-File API completely like JDK 24?**  
   No. JDK 22 is preview JEP 457; JDK 23 is preview JEP 466; JDK 24 is final JEP 484.

3. **Why does a tool compiled with `--release 24` not run on Java 17?**  
   It has class-file major 68; JVM 17 does not support that major version, and `java.lang.classfile` does not exist in Java 17.

4. **Can a JDK 24 tool parse a major 61 input?**  
   Yes, provided the class file is valid and supported by the API; the input version does not have to match the tool's version.

5. **Can ASM running on JDK 17 read a class file from Java 24?**  
   If the ASM version supports the newer format, it can **parse offline**, but JVM 17 still cannot define a major 68 class.

6. **Can a `-javaagent` JAR with `Premain-Class` built for Java 24 run on JVM 17?**  
   No. The entry class must load before `main`; a Java 17-compatible root bootstrap or a legacy artifact is required.

7. **Does `javac --release 17` on JDK 24 allow importing `java.lang.classfile`?**  
   No. The release 17 API surface does not contain this package.

8. **Does the standard Class-File API eliminate the need to test with the bytecode verifier?**  
   No. Structurally valid build/transform output does not prove correct behavior or target runtime compatibility.

9. **Do two engines printing the same methods prove identical class output semantics for all inputs?**  
   No. That is only metadata inspection; code/attribute checks and behavioral tests are needed.

10. **In an MR-JAR, is `META-INF/versions/24` selected on Java 17?**  
    No, under standard MR-JAR rules; Java 17 uses the root baseline implementation.

11. **What happens if you place a modern class under `META-INF/versions/24` but forget `Multi-Release: true`?**  
    Normal runtimes will not select it as an override under MR-JAR rules.

12. **Why not import `jdk.internal.org.objectweb.asm` on Java 17 to avoid a dependency?**  
    It is an internal JDK implementation with no compatibility guarantees and is subject to module encapsulation.

13. **Is a major 61 output class enough to prove Java 17 compatibility?**  
    Not yet. You must check instructions, metadata, references to Java APIs, and run tests on JVM 17.

14. **If targeting Java 17, can JDK 24 be used to build/transform?**  
    Yes, provided the output bytes are genuinely valid, do not call newer APIs, and pass tests on Java 17.

15. **If the ASM dependency is included in the Maven build but missing from the agent JAR at runtime, what error occurs?**  
    Likely `NoClassDefFoundError` for `org/objectweb/asm/...`, depending on how loading proceeds.

16. **When running `mvn compile exec:java`, what does `MAJOR=61` indicate?**  
    `Sample.class` was compiled targeting release 17, not the major version of the JDK running Maven.

17. **Why is splitting into two artifacts often simpler than an MR-JAR?**  
    Each artifact has clear compiler/runtime/dependency/premain settings; an MR-JAR must maintain binary contracts and a more complex versioned layout.

18. **If newer JVMs have the Class-File API, is there still any reason to use Byte Buddy?**  
    Yes. Byte Buddy provides a higher-level API for interception/generation, agent integration, and abstraction; choose based on needs and compatibility.

## 17. References

1. **JEP 457 — Class-File API (Preview), JDK 22**: https://openjdk.org/jeps/457
2. **JEP 466 — Class-File API (Second Preview), JDK 23**: https://openjdk.org/jeps/466
3. **JEP 484 — Class-File API (Final), JDK 24**: https://openjdk.org/jeps/484
4. **Oracle JDK 24 — `java.lang.classfile` package**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html
5. **Oracle JDK 24 — `ClassFile`**, `of`, `parse`, `build`, `transformClass`, `verify`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html
6. **Oracle JDK 24 — `ClassModel`, `ClassTransform`, `ClassBuilder.withVersion`**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html
7. **Oracle — `javac --release`**: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
8. **ASM official versions**, class file format support: https://asm.ow2.io/versions.html
9. **ASM public site**: https://asm.ow2.io/
10. **Byte Buddy docs**: https://bytebuddy.net/
11. **Oracle JDK 17 — `ClassFileTransformer` contract**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
12. **Oracle JDK 17 — `java.lang.instrument` agent manifest/startup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
13. **Oracle — Multi-Release JAR format (`JAR File Specification`)**: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
14. **JVMS — ClassFile format and major version**: https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html

**Conclusion:** The Class-File API in `java.lang.classfile` is the natural choice when the **tool/agent runtime is JDK 24+** and you want typed bytecode APIs without external library dependencies. When you must run directly on **JDK 17/21**, use a compatible ASM/Byte Buddy engine or split implementations; do not try to "lower `--release`" on code that references APIs available only in JDK 24. Always check **tool runtime, tool class version, input class version, output target, and packaging/classloader** as five independent compatibility layers.
