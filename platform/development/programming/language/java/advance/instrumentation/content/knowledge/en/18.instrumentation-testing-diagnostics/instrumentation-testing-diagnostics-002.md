# Transforming Bytes in Tests Before Installing a Java Agent into a Test JVM

## 1. Goal: Test the Bytecode Transformer First, Install the Agent Later

A Java agent uses `ClassFileTransformer` to modify class-file bytes before the JVM defines or updates a class. Mistakes in this logic can cause `ClassFormatError`, `VerifyError`, `LinkageError`, class-loading recursion, module/loader mismatches, or unexpected behavior. If you only test by starting the entire application with `-javaagent`, a small bug can prevent **the test JVM from starting**, and class-loading logs make it hard to tell whether the bug is in the algorithm, agent configuration, or runtime.

A good strategy is to **separate the class-file transformation logic into a component that can be run directly in tests**, and then verify the result before letting the agent affect the test JVM:

1. **Offline byte transformation tests:** read a compiled `.class` into a `byte[]`, invoke the transformer or transformation function directly, and verify that input bytes are not mutated, the output is correct, and a no-op returns `null`.
2. **Validity and behavior checks:** parse/disassemble the output, and use an isolated class loader in a test JVM or a child JVM with `-Xverify:all` to verify that the new class can be defined, linked, and executed as expected.
3. **Agent integration tests:** only after the two steps above, package a JAR with `Premain-Class` and launch a separate JVM with `-javaagent`, checking real callbacks, loaders/modules, transformer ordering, and behavior.
4. **Production-like environment tests:** confirm bootstrap/module visibility, multiple loaders, redefine/retransform, concurrency, and operational overhead if the feature uses those capabilities.

**Important distinction:** calling `transform(...)` like an ordinary Java method is **not** JVM instrumentation. An offline test simulates the arguments, bytes, and scenarios you explicitly provide; it does not prove that the JVM registered/granted capabilities to the agent, nor does it automatically test all runtime conditions.

This article belongs to the **Testing and Diagnostics** section of Java Advance — Instrumentation, presenting the workflow, test layers, how to catch errors early, a complete runnable Java 17 example, and a checklist before installing an agent into a test JVM.

## 2. Transformer Input/Output Contract to Test

On Java 17, `ClassFileTransformer` has a six-parameter overload:

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
```

The snippet above only excerpts the signature; you need to import `java.security.ProtectionDomain` and `java.lang.instrument.IllegalClassFormatException`.

Fields to understand:

| Parameter/value | When called by the real JVM | When called directly in an offline test |
| --- | --- | --- |
| `module` | Runtime module containing the transformed class | Can pass an appropriate `Module` object; `null` in the demo is only a **simulated context**, not representing the unnamed module |
| `loader` | Defining class loader; `null` for bootstrap | Can provide a simulated loader; `null` in the demo does not prove the target is defined by bootstrap |
| `className` | JVM internal name, e.g., `demo/Greeter` | The test must provide **the exact slash form**; do not confuse with `demo.Greeter` |
| `classBeingRedefined` | `null` for initial load; non-null on redefine/retransform | `null` simulates the initial-load path; does not show which classes the JVM has loaded |
| `protectionDomain` | Domain of the class being defined/updated | Can be `null` in a unit test if the rule does not need it; this does not test protection domains |
| `classfileBuffer` | Full current class-file bytes in the transformer chain | Read from a `.class` file or from an emitter; **not `.java`/JAR contents** |
| Return value `null` | Do not transform bytes at this step | Unit test asserts that no-op follows the contract |
| Return value `byte[]` | New classfile array that the JVM/subsequent transformers will process | Test checks integrity, structure, and behavior of the array |

**Important rules from the Java 17 Javadoc:**

- Do not modify `classfileBuffer` in place; if a transformation occurs, return **a new byte array**.
- If no transformation is needed, return **`null`**, not `new byte[0]` or a pointless clone.
- The transformer must produce a valid class file for the target JVM. You must not edit code while ignoring the constant pool, method descriptors, exception table, or stack map frames if they are affected.
- Transformers **are chained**; the bytes from an earlier transformer become the input to the next transformer. A unit test of a single transformer does not prove the whole pipeline is correct.
- An exception from a transformer does not automatically abort class loading; the JVM may continue calling subsequent transformers and attempt to define the class with the previous bytes.
- With `redefineClasses`/`retransformClasses`, there are also restrictions on changing schema/fields/methods/hierarchy.

In Java 17, both the five- and six-parameter forms have default implementations, so `ClassFileTransformer` **is not a functional interface**. Do not write `ClassFileTransformer t = (...) -> ...`; use a class/anonymous class with `@Override`.

## 3. Boundaries of the Three Test Layers

### 3.1. Testing the Pure Byte Transformation Function

You can extract the transformation core into a nearly pure function:

```java
static byte[] transformBytes(
        String internalName, byte[] originalBytes)
        throws IllegalClassFormatException {
    // Filter the right class, parse input, and produce output when changed.
    // If unmodified, return null.
}
```

This is an illustrative signature, not a complete program. Given the same input bytes, the same rules, and the same immutable configuration, the effective output should be **deterministic**. Tests can verify:

- **Target match:** the desired class is modified.
- **Non-target:** returns `null`, does not modify input.
- **Input immutable:** the initial snapshot still equals the bytes after the call.
- **No-op/idempotence:** running again on already-patched bytes produces no duplicate change.
- **Negative input:** malformed bytes are detected instead of causing out-of-bounds array access.
- **Output valid:** a parser/VM can accept the new class file.
- **Behavior:** the transformed method returns the expected result.

**Advantages:** fast, easy to repeat many times, and on failure you can preserve the input/output for analysis without restarting the whole application.

### 3.2. Checking with a Dedicated Class Loader in the Test JVM

You can create a subclass of `ClassLoader` and call `defineClass(String binaryName, byte[], ...)` on the output. The JVM actually **defines** the class from those bytes, thereby catching many class-file/verification/linkage errors and allowing methods to be invoked via reflection.

Note, however, that this **is still a JVM executing the test**: it is not completely "untouched by a JVM." What does **not** happen is installing/registering a Java agent on the test JVM; the class is defined **in isolation in the test runner's own loader**.

The two steps do not replace each other:

- Pure parser/unit tests catch transform logic bugs.
- An isolated class loader partially confirms the JVM's ability to use the new bytes.

If the class depends on native libraries, a special security domain, module reads/exports, bootstrap helpers, or a plugin loader, an isolated loader does **not** automatically reproduce all of those conditions. A separate integration JVM is needed.

### 3.3. Real Testing with `-javaagent`

Only in a JVM launched with:

```bash
java -javaagent:patch-agent.jar -cp ... Main
```

does the JVM execute the agent loading sequence, invoke `premain`, register the transformer via `Instrumentation.addTransformer`, and call `transform` with the **real module/loader/domain**. This test additionally catches issues with the manifest, classpath, module graph, class loading order, access permissions, helper dependencies, and agent startup.

You should include:

- **Negative control:** run the same application **without** `-javaagent`; the result is unpatched.
- **Positive control:** run with `-javaagent`; the result is patched.
- **Verifier run:** add `-Xverify:all` on the test JVM when appropriate.
- **Isolation:** use a separate process, bounded runtime, capture stdout/stderr and exit code; never touch a production JVM.

### 3.4. Test Table by Cost and Scope

| Test layer | Agent installed? | What it catches | What it does not prove |
| --- | --- | --- | --- |
| Pure `byte[]` check | No | Rule matching, bytes, determinism, no-op, input unchanged | JVM accepts output, real loader/module |
| `javap`/bytecode parser check | No | Constant pool/methods/attributes, structural differences | Full runtime linkage/behavior |
| `defineClass` in isolated loader | No | JVM define/verify, simple method invocation, binary name | JPMS/agent registration/production loader semantics |
| Child JVM `-Xverify:all` using output bytes | Not required | Class verification and behavior when running the new file | Callback invoked by a real agent |
| Child JVM `-javaagent` | **Yes** | Manifest, `premain`, callback, real loader/module, behavior | Production traffic, multiple agents/versions/layers |
| Production-like staging | Yes | Multi-loader, multi-module, concurrency, compatibility/overhead | Guarantee that every real workload behaves identically |

The goal is not to eliminate all risk with a single unit test, but to **push simple bugs down to the cheapest test layer** before starting a complex system.

## 4. Preparing the Fixture: The Original Class Must Match the Target Artifact

Before testing, **compile a Java class into full class-file bytes**:

```bash
javac --release 17 -d build/classes src/demo/Greeter.java
```

Then the file to read is:

```text
build/classes/demo/Greeter.class
```

**Do not use:**

- The contents of `src/demo/Greeter.java` (UTF-8 source text).
- An entire `.jar`/ZIP containing the class.
- The bytes of a single method instead of the `.class` file.
- A class file with the same name from a **different loader/module/build version** if you want to reproduce a real bug.
- Bytecode different from the bytes the transformer will actually receive after preceding transformers.

When the JVM has multiple transformers, **order** matters: the output of transformer A may be the input to B, so B's tests need both the base fixture and the fixture already processed by A. Unit tests with arbitrarily chosen inputs can miss composition bugs.

### 4.1. Artifact Checkpoints

In CI you can record:

- The file path from the build artifact and its SHA-256 hash.
- The class-file major version; Java 17 has major version **61**.
- The JVM target and `javac --release`.
- The binary name `demo.Greeter` and internal name `demo/Greeter`.
- The module/loader namespace if the rule depends on it.
- The transformer configuration and parser/writer dependency version.
- `javap` output or verifier reports on failure.

Do not use a **single** output hash as proof of correctness across all builds: debug attributes, line numbers, or compiler options can change classfile bytes without changing behavior. Hashes help **identify the tested artifact**, while correctness requires assertions/verification.

## 5. Creating a Testable Java 17 Transformer

The example uses a small, reproducible edit: changing the constant-pool UTF8 literal `"BEFORE"` to `"AFTER!"` in class `demo/Greeter`.

Both strings are **6 ASCII bytes** long, so the patch preserves the length of `CONSTANT_Utf8` and all subsequent offsets. This is an **intentionally constrained fixture** to focus on the testing workflow; in a real agent, complex transformations of instructions, annotations, signatures, or stack frames must use ASM, Byte Buddy, or the Java Class-File API on JDK 24+.

### 5.1. Project Structure

```text
offline-transform-lab/
├── agent.mf
└── src/
    ├── demo/
    │   └── Greeter.java
    ├── BytePatchTransformer.java
    ├── OfflineCheck.java
    ├── PatchAgent.java
    └── AgentApp.java
```

All code is **Java 17** compatible. Neither Maven/Gradle nor JUnit is required to run this lab, though in a real project you can move the assertions into JUnit 5.

### 5.2. File `src/demo/Greeter.java`

```java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "BEFORE";
    }
}
```

The original has a public static method returning the string `BEFORE`. We will **not compile another source version**: all changes will be performed directly on the byte array of `Greeter.class`.

### 5.3. File `src/BytePatchTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class BytePatchTransformer
        implements ClassFileTransformer {

    private static final byte[] OLD =
            "BEFORE".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "AFTER!".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer)
            throws IllegalClassFormatException {

        // Ignore all other classes and redefine/retransform callbacks.
        if (!"demo/Greeter".equals(className)
                || classBeingRedefined != null) {
            return null;
        }

        // Core does not depend on Instrumentation or global JVM state.
        return patchConstantPool(classfileBuffer);
    }

    private static byte[] patchConstantPool(byte[] input)
            throws IllegalClassFormatException {

        if (input == null || input.length < 10) {
            throw new IllegalClassFormatException(
                    "Missing/truncated class file");
        }

        if ((input[0] & 255) != 0xCA
                || (input[1] & 255) != 0xFE
                || (input[2] & 255) != 0xBA
                || (input[3] & 255) != 0xBE) {
            throw new IllegalClassFormatException(
                    "Invalid CAFEBABE magic");
        }

        int poolCount = u2(input, 8);
        int p = 10;
        byte[] output = null;

        for (int i = 1; i < poolCount; i++) {
            require(input, p, 1);
            int tag = input[p++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(input, p);
                    p += 2;
                    require(input, p, length);

                    if (length == OLD.length
                            && equalsAt(input, p, OLD)) {
                        // Never mutate the input buffer in place.
                        if (output == null) {
                            output = input.clone();
                        }
                        System.arraycopy(
                                NEW, 0, output, p, NEW.length);
                    }
                    p += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> {
                    require(input, p, 4);
                    p += 4;
                }
                case 5, 6 -> { // Long/Double occupy two pool slots.
                    require(input, p, 8);
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> {
                    require(input, p, 2);
                    p += 2;
                }
                case 15 -> {
                    require(input, p, 3);
                    p += 3;
                }
                default -> throw new IllegalClassFormatException(
                        "Unsupported constant-pool tag: " + tag);
            }
        }

        // null means no literal needed to be changed.
        return output;
    }

    private static int u2(byte[] input, int position)
            throws IllegalClassFormatException {
        require(input, position, 2);
        return ((input[position] & 255) << 8)
                | (input[position + 1] & 255);
    }

    private static void require(
            byte[] input, int position, int length)
            throws IllegalClassFormatException {
        if (position < 0 || length < 0
                || position > input.length - length) {
            throw new IllegalClassFormatException(
                    "Truncated constant pool");
        }
    }

    private static boolean equalsAt(
            byte[] input, int at, byte[] pattern) {
        // Caller already checked bounds for the UTF8 entry.
        for (int j = 0; j < pattern.length; j++) {
            if (input[at + j] != pattern[j]) {
                return false;
            }
        }
        return true;
    }
}
```

**Structure and limitations explained:**

- The `className` filter uses the JVM internal name with `/`; `"literal".equals(className)` is safe when `className == null`.
- `classBeingRedefined != null` is ignored in the demo to focus on **initial load**. Production code supporting redefine/retransform needs a rule compatible with schema constraints and its own lifecycle.
- `patchConstantPool` is the byte-processing logic and can be invoked directly through `transform` in unit tests without `Instrumentation`.
- The input is validated at the header and while walking each constant-pool entry; the input array **is not mutated**.
- It calls `clone` only when `BEFORE` is found; if there is no match, it returns `null`.
- When called again on output containing `AFTER!`, there is no `BEFORE` entry left, so the second result is `null`: the patch is **effectively idempotent** on this fixture.
- The parser reads the constant-pool tags in Java 17. It does **not** prove full class validity, does not inspect all attributes/methods, and is not a general-purpose classfile library. Replacing a same-length literal on this fixture requires no adjustment to instruction offsets, stack map frames, or descriptors.
- If another class has the same internal name in a different loader, filtering by name alone could patch that class too: the demo runs in an isolated environment; a real product should consider loader/module/artifact if required.
- Do not call `Class.forName`/reflection inside the callback, to avoid loading the very class being defined by the JVM.
- The callback throws `IllegalClassFormatException` per contract when it sees an invalid classfile; **the JVM is not forced to abort** just because a transformer throws this exception. Direct unit tests can observe the exception, while integration tests must check JVM behavior separately.

## 6. Writing an Offline Unit Test to Check Bytes and Behavior Directly

### 6.1. File `src/OfflineCheck.java`

```java
import java.lang.instrument.IllegalClassFormatException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public final class OfflineCheck {
    private OfflineCheck() {
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class IsolatedLoader extends ClassLoader {
        IsolatedLoader() {
            // Delegate only to bootstrap; do not load Greeter from app classpath.
            super(null);
        }

        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    private static String invokeMessage(byte[] bytes)
            throws Exception {

        // Use a new defining loader each time:
        // two versions with the same binary name do not collide in identity.
        Class<?> type = new IsolatedLoader().define(
                "demo.Greeter", bytes);

        Method method = type.getMethod("message");
        return (String) method.invoke(null);
    }

    public static void main(String[] args) throws Exception {
        check(args.length == 1,
                "Usage: OfflineCheck <Greeter.class>");

        Path inputFile = Path.of(args[0]);
        byte[] original = Files.readAllBytes(inputFile);
        byte[] snapshot = original.clone();
        BytePatchTransformer transformer =
                new BytePatchTransformer();

        // 1. Non-target must be a no-op.
        byte[] unrelated = transformer.transform(
                null, null, "other/Name",
                null, null, original);
        check(unrelated == null,
                "Unrelated class should be ignored");

        // 2. Target must produce a NEW byte array.
        byte[] changed = transformer.transform(
                null, null, "demo/Greeter",
                null, null, original);
        check(changed != null, "Target was not patched");
        check(changed != original,
                "Output must not alias original input");
        check(!Arrays.equals(changed, original),
                "Output bytes must differ from input");

        // 3. Original buffer must remain unchanged.
        check(Arrays.equals(original, snapshot),
                "Transformer mutated original bytes");

        // 4. Idempotence: second patch is a no-op.
        byte[] repeated = transformer.transform(
                null, null, "demo/Greeter",
                null, null, changed);
        check(repeated == null,
                "Repeated patch must be no-op");

        // 5. Test JVM defines 2 classes in 2 isolated loaders.
        String before = invokeMessage(original);
        String after = invokeMessage(changed);
        check("BEFORE".equals(before),
                "Unexpected original behavior");
        check("AFTER!".equals(after),
                "Unexpected transformed behavior");

        // 6. Malformed classfile: unit call must throw an error.
        boolean rejected = false;
        try {
            transformer.transform(
                    null, null, "demo/Greeter",
                    null, null, new byte[]{1, 2, 3});
        } catch (IllegalClassFormatException expected) {
            rejected = true;
        }
        check(rejected, "Invalid bytes were not rejected");

        // 7. Write output for further inspection by javap and child JVM.
        Path outputFile =
                Path.of("build/rewritten/demo/Greeter.class");
        Files.createDirectories(outputFile.getParent());
        Files.write(outputFile, changed);

        System.out.println("[offline] nonTarget=null");
        System.out.println("[offline] inputUnchanged=true");
        System.out.println("[offline] changed=true");
        System.out.println("[offline] repeat=null");
        System.out.println("[offline] before=" + before);
        System.out.println("[offline] after=" + after);
        System.out.println("[offline] invalid=rejected");
        System.out.println("[offline] PASS");
    }
}
```

### 6.2. What Do the Assertions Actually Prove?

| Check | Proves | Does not prove |
| --- | --- | --- |
| `unrelated == null` | The rule does not patch a different class name | The agent will not patch other classes on a real JVM due to other configuration |
| `changed != original` | Output is a different array object | Output is a valid class file |
| `!Arrays.equals(changed, original)` | There is a byte-level change | That the change is the one you intended |
| `Arrays.equals(original, snapshot)` | The input array was left intact | That the code does not retain an input reference in a cache |
| `repeated == null` | For this fixture, the second patch is a no-op | That every transformer in a pipeline is idempotent |
| `invokeMessage(original)` returns `BEFORE` | The JVM can define and invoke the original | That the production JVM loads this exact loader/module |
| `invokeMessage(changed)` returns `AFTER!` | The JVM can define/link/invoke output in the test loader | That the agent ran, or that all methods/exception paths are correct |
| Invalid bytes are rejected | The parser detects an obviously broken classfile | That the parser safely handles every malformed input |
| Output written to `build/rewritten` | Artifact for inspection in the next step | Self-installation of bytes onto a test JVM |

**Notable point:** `ClassLoader#defineClass` takes a **binary name** `demo.Greeter`, whereas the callback `className` is an **internal name** `demo/Greeter`. In tests, mixing up these two forms can cause `NoClassDefFoundError` or prevent the test from hitting the right code path.

### 6.3. Why Does Each Version Use a Separate Loader?

In a JVM, **the same binary name cannot be defined twice in the same defining loader**. If you call `defineClass("demo.Greeter", ...)` twice on the same loader, the second call can throw `LinkageError` due to duplicate definition. The two versions in `OfflineCheck` use **two separate `IsolatedLoader` instances**, so they do not share a duplicate class identity.

This technique is suitable for testing raw bytes, but **it is not equivalent to `Instrumentation.redefineClasses`**: redefinition replaces method bodies within an existing class identity, whereas an isolated loader creates a new class identity. If you want to test redefinition, you must run an integration test with the proper capability.

## 7. Commands to Run the Offline Unit Test with JDK 17

### 7.1. Compile

From the root directory `offline-transform-lab/`:

```bash
mkdir -p build/classes

javac --release 17 -d build/classes \
  src/demo/Greeter.java \
  src/BytePatchTransformer.java \
  src/OfflineCheck.java \
  src/PatchAgent.java \
  src/AgentApp.java
```

The test **does not install an agent**. `PatchAgent.java` and `AgentApp.java` are defined in section 9; you can compile all five files up front to run the steps in order.

### 7.2. Run the Test Suite Directly

```bash
java -cp build/classes OfflineCheck \
  build/classes/demo/Greeter.class
```

**Expected stdout when the test passes:**

```text
[offline] nonTarget=null
[offline] inputUnchanged=true
[offline] changed=true
[offline] repeat=null
[offline] before=BEFORE
[offline] after=AFTER!
[offline] invalid=rejected
[offline] PASS
```

If an assertion fails, the program throws `AssertionError` and the process exits with a nonzero status. Missing the `PASS` line indicates the test did not pass. Do not catch all exceptions just to print `PASS` at all costs.

The `OfflineCheck` command **has no `-javaagent`**. The JVM still executes the test runner's bytecode and defines two versions of the class in isolated loaders, but **there is no `premain` and no registered transformer**: that is the main difference from an integration test.

### 7.3. Inspecting the Original and Output Class Files

`OfflineCheck` saves:

```text
build/rewritten/demo/Greeter.class
```

Inspection commands:

```bash
javap -v -p build/classes/demo/Greeter.class
javap -v -p build/rewritten/demo/Greeter.class

javap -c -p build/classes/demo/Greeter.class
javap -c -p build/rewritten/demo/Greeter.class
```

In the original output, the constant pool contains the literal `BEFORE`; in the new output, the corresponding literal is `AFTER!`. The `message()` method still has the `ldc` + `areturn` form with the appropriate constant; indices may vary across builds/JDKs.

**Do not compare the entire `javap` stdout byte-for-byte** across two different builds: constant pool indexes, debug attributes, or line numbers may differ. In the demo, the new bytes are derived directly from the old bytes by replacing a single constant-pool entry of the same length, so the expected difference is very tightly scoped.

### 7.4. Verifying in a Child JVM with the Verifier Enabled

```bash
java -Xverify:all \
  -cp "build/rewritten:build/classes" AgentApp
```

**Stdout:**

```text
[agent-jvm] message=AFTER!
```

This command **does not use `-javaagent`**. Because `build/rewritten` precedes `build/classes` on the classpath, the child JVM's system loader finds `demo.Greeter` from the patched bytes; `AgentApp` is in `build/classes`. Running with `-Xverify:all` checks verification in a real JVM environment, but it does not mean every method path, exception, module, or runtime composition is proven correct.

Control command using only the original output:

```bash
java -Xverify:all -cp build/classes AgentApp
```

**Control stdout:**

```text
[agent-jvm] message=BEFORE
```

**Note:** do not assume that verification flags behave identically across all JVMs/versions, and a class verifying without error does not prove business logic is correct. Behavioral assertions and integration tests are still required.

## 8. When to Use ASM, Byte Buddy, or the Java Class-File API?

The raw byte patcher here is limited to **same-length constant-pool UTF8 entries**. If your real transformation inserts method-entry advice, replaces invoke instructions, modifies exceptions, annotations, bootstrap methods, or frames, use a tool that understands class-file structure.

| Tool | Strengths | Things to watch |
| --- | --- | --- |
| **ASM** | Low-level class file reading/writing, visitors, tree API, frames, `CheckClassAdapter` | Pick a version supporting the target classfile; understand `COMPUTE_FRAMES` and hierarchy resolution |
| **Byte Buddy** | High-level declarative behavior/advice, more convenient testing | Still subject to JVM instrumentation, class loader, and helper visibility limits |
| **Java Class-File API (JDK 24+)** | Standard JDK API `java.lang.classfile`; read/write/verify class models | **Not available in Java 17**; must target the right JDK |
| **`javap` + JVM verifier** | Built into the JDK, easy to inspect/check artifacts | Not a replacement for semantic assertions |
| **Pure transformer unit tests** | Fast execution, isolates logic bugs and byte-level invariants | Does not validate agent lifecycle or module graph |

### 8.1. Testing Output with ASM If the Project Already Uses ASM

With ASM, you can use `org.objectweb.asm.util.CheckClassAdapter` to check bytecode structure, alongside the JVM verifier for actual behavior. Keep compiler/bytecode library dependencies in **test scope** if the runtime agent does not need them, or package/shade them properly in the agent if production needs them.

Illustrative snippet (not a standalone program, and requires compatible ASM JARs):

```java
ClassReader reader = new ClassReader(transformedBytes);
CheckClassAdapter.verify(reader, false, printWriter);
```

`transformedBytes` is the full class-file output; `printWriter` is a `PrintWriter` configured in the test. Checking with a verifier/library alone still does not replace real JVM tests if the code depends on loaders/modules or runtime APIs.

### 8.2. Stack Maps and Control Flow

When inserting instructions/try-finally:

- Update branch offsets, max stack/max locals, and exception tables.
- Preserve or recompute `StackMapTable` for the target JVM.
- Check constructors `<init>` and initialization rules.
- Do not forget both `normal exit` and `exceptional exit` when inserting timers.
- Test synchronized methods/`monitorenter`/`monitorexit` so monitor balance is not broken.
- Choose a hierarchy resolver that does not trigger class loading in the wrong namespace when computing frames.

Do not accept the advice "just use `COMPUTE_FRAMES` and it is always right" if the hierarchy resolver uses the wrong loader or accidentally loads new classes. You must test against the real namespace/environment.

## 9. Only After Offline PASS: Package the Agent JAR and Run Integration JVM

To test **real callbacks** instead of manual calls, we reuse `BytePatchTransformer`.

### 9.1. File `src/PatchAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class PatchAgent {
    private PatchAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation inst) {

        // The JVM will call transform(...) when the target class is defined.
        inst.addTransformer(new BytePatchTransformer(), false);
    }
}
```

The agent only needs to transform at initial class load; therefore it **does not need** `Can-Redefine-Classes` or `Can-Retransform-Classes` in the manifest. Registering with `canRetransform=false` still allows callbacks on initial load.

### 9.2. File `src/AgentApp.java`

```java
import demo.Greeter;

public final class AgentApp {
    private AgentApp() {
    }

    public static void main(String[] args) {
        System.out.println(
                "[agent-jvm] message=" + Greeter.message());
    }
}
```

This is a minimal application that only loads `demo.Greeter` when run, after `premain`. It never calls `BytePatchTransformer.transform` itself. If the JVM invokes the callback properly, `message()` changes from `BEFORE` to `AFTER!`.

### 9.3. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PatchAgent

```

This is the agent JAR manifest; it has a **trailing blank line ending the main section**. The name `PatchAgent` must match the binary name of the class containing `premain`.

### 9.4. Building the JAR After Unit Tests Pass

```bash
jar --create --file patch-agent.jar \
  --manifest agent.mf \
  -C build/classes PatchAgent.class \
  -C build/classes BytePatchTransformer.class

jar --list --file patch-agent.jar
```

The JAR needs to contain `PatchAgent.class`, `BytePatchTransformer.class`, and `META-INF/MANIFEST.MF`. In this example the transformer has no anonymous/nested helpers; if a real agent has other classes/helpers, all dependencies must be packaged.

### 9.5. Control and Running with the Agent

**Without the agent:**

```bash
java -cp build/classes AgentApp
```

**Stdout:**

```text
[agent-jvm] message=BEFORE
```

**With the agent, using a fresh JVM and verifier enabled:**

```bash
java -Xverify:all \
  -javaagent:patch-agent.jar \
  -cp build/classes AgentApp
```

**Expected stdout:**

```text
[agent-jvm] message=AFTER!
```

Only this test proves: the manifest is valid, the JVM starts `premain`, the transformer is registered, the target class is defined through the transformer, and the method actually uses the output. Even so, it does not yet prove safety on a production JVM with multiple modules/layers, other agents, custom loaders, or retransform.

### 9.6. Windows PowerShell

From the directory containing `src` and `agent.mf`:

```powershell
New-Item -ItemType Directory -Force build/classes | Out-Null

javac --release 17 -d build/classes src/demo/Greeter.java src/BytePatchTransformer.java src/OfflineCheck.java src/PatchAgent.java src/AgentApp.java

java -cp build/classes OfflineCheck build/classes/demo/Greeter.class

javap -v -p build/rewritten/demo/Greeter.class

java -Xverify:all -cp "build/rewritten;build/classes" AgentApp

jar --create --file patch-agent.jar --manifest agent.mf -C build/classes PatchAgent.class -C build/classes BytePatchTransformer.class

java -cp build/classes AgentApp
java -Xverify:all -javaagent:patch-agent.jar -cp build/classes AgentApp
```

On Windows, classpaths with multiple entries use **`;`**, while on POSIX they use **`:`**. With `build/rewritten` on the classpath, place it before `build/classes` as instructed so the transformed class takes precedence. When testing the agent, **do not** place `build/rewritten` before `build/classes`, otherwise you might observe the right result even if the agent did nothing.

## 10. What Direct `transform` Unit Tests Do Not Fully Simulate

A test can PASS in a synthetic environment yet FAIL when called by the real JVM. Key differences:

### 10.1. Module, Loader, Protection Domain

In `OfflineCheck`, we passed `null` for module, loader, and protection domain **intentionally**, because the demo transformer only needs the internal name and byte buffer. That is not equivalent to the JVM passing null during initial class load of a classpath app.

- For an ordinary class in the unnamed module, the real callback receives a **`Module` object** with `module.isNamed() == false`.
- `loader == null` in a real JVM callback means the bootstrap loader; passing null manually does not create bootstrap loading.
- `className` must be in internal/slash form, even though `defineClass` uses binary/dot form.
- `classBeingRedefined` is non-null during redefine/retransform, and the callback may see input bytes already modified by other transformers.

If a production transformer uses module identity/loader equality or `ProtectionDomain`, unit tests must supply matching fixtures and assertions **and integration tests are still needed** to validate real modules/loaders.

### 10.2. Transformer Ordering

Suppose the JVM registers A first and then B. B does not necessarily see the original bytes from the JAR: it may see **the output of A**. Unit tests for B should be run with:

```text
B(originalBytes)       — standalone test
B(A(originalBytes))    — ordered composition test
```

For `null` returns, composition must be handled accurately:

```text
effective(input, transformer) =
    result == null ? input : result
```

Do not chain a `null` array as if it were class-file bytes. Do not test transformers only in isolation and ignore ordering, because two transformations that are each valid alone can conflict when combined.

### 10.3. Redefine, Retransform, Active Frames

Testing by defining a **new** class does not check redefinition limits. If a production agent uses:

```java
inst.redefineClasses(new ClassDefinition(target, newBytes));
inst.retransformClasses(target);
```

(illustrative snippet where `target` is an existing `Class<?>` object), you need:

- Manifest capabilities `Can-Redefine-Classes` / `Can-Retransform-Classes` and API support checks;
- `inst.isModifiableClass(target)`;
- No changes to field/method schema, modifiers, or hierarchy beyond JVM limits;
- Accounting for `canRetransform=false` transformers whose cached output is reused instead of being re-invoked on retransform;
- Checking old active stack frames and verifying class state is not unexpectedly reset;
- Testing multiple passes to catch double instrumentation.

These tests cannot be replaced by two isolated class loaders defining two separate class identities.

### 10.4. Helper Classes and Visibility

If the output adds a call to `agent.Helper`, an isolated loader with a null parent may fail to find the helper while the JVM app/system loader finds it, or vice versa. Tests must deliberately choose a loader topology matching runtime, or use the corresponding module/JPMS-aware configuration.

**Do not stop at checking "the class was defined" and forget to invoke the code path containing the helper reference**: some linkage errors only surface when the JVM actually resolves the target method/class. If the helper lives on the bootstrap search path or in a named module, verify reads/exports/opens as required.

## 11. Building a Standard Test Matrix for CI

| Test case | Expectation | Minimum layer |
| --- | --- | --- |
| Non-matching `className` | `null`, input unchanged | Unit |
| Matching `className`, original bytes | New output array, expected change | Unit |
| Input byte array unmutated | `Arrays.equals(original, snapshot)` | Unit |
| Second patch run | No-op/idempotent per rule | Unit |
| Buffer missing full header | `IllegalClassFormatException` in direct call | Unit |
| Output missing `Code`/corrupted constant pool | Verifier/parser reports error | Bytecode verify |
| Key method after patch | Expected return value | Isolated loader or child JVM |
| Wrong binary name | Test fails rather than silently loading another class | Isolated loader |
| JDK target/class-file version | Accepts supported version, rejects unsupported version | Child JVM |
| With/without agent | `BEFORE`/`AFTER!` per JVM process | Integration |
| Missing or invalid agent manifest | Process fails/no instrumentation | Integration |
| Different module/loader | Policy affects only the intended class identity | Integration |
| Concurrent threads hitting callback | No race, deadlock, or state bleed | Integration |
| Two transformers | Correct output in order | Unit composition + integration |
| Repeated retransform/redefine | No duplicate insertion, still valid | Integration with capability |
| Complex classfile | Frames, try/catch, constructor, synchronized remain valid | Verifier + behavioral tests |
| Agent logging/performance | No log storm, overhead within budget | Staging load test |

Keep fixtures as minimal as possible while still reproducing the bug. For bugs depending on stack frames or exception handlers, do not rely only on a class returning a simple string; add fixtures with branches, try/finally, checked exceptions, records, interfaces, lambdas, bootstrap/module access, and custom loaders as appropriate.

## 12. Diagnostics When Output Is Wrong

### 12.1. Unit Test Returns `null` on Target

Check:

- `className` is `demo/Greeter`, not `demo.Greeter`.
- Class name has the right case and package.
- Whether `classBeingRedefined != null` is set, causing the rule to skip it.
- Whether the input `.class` actually contains the expected literal.
- Whether the output was already patched earlier; idempotence will return `null`.
- Whether data was read from the right path/artifact.

### 12.2. Unit Test Produces Different Bytes but JVM Still Returns `BEFORE`

Possible causes:

- The test patched a constant-pool entry not used by the method.
- `AgentApp` loaded a class copy from a different classpath entry or loader.
- In the integration JVM, the class was loaded **before** the agent registered.
- Subsequent transformers overwrote the output.
- The transformation did not affect the invoked method (or JIT/frames in redefinition need separate analysis).

Run `javap -v -p` on the **exact output file**, inspect loader/class source in the JVM if needed, and run negative/positive controls in **two fresh JVMs**.

### 12.3. `ClassFormatError`, `VerifyError`, `LinkageError`

- `ClassFormatError`: malformed classfile, invalid constant-pool tags/lengths, attributes, or hierarchy.
- `VerifyError`: instruction control flow, stack types, or stack map frames fail the verifier.
- `LinkageError`: name/loader/duplicate definition/module/helper resolution depending on subtype.
- `NoClassDefFoundError`: mismatched binary name, unloadable dependency, or failed linkage.
- `IllegalAccessError`: invalid module/package/class access or method/field visibility.

Do not jump to conclusions from an exception name alone. Preserve the **exact input/output class files**, JDK version, classpath/module path, transformer order, stderr, and full stack trace **outside the callback** to reproduce.

### 12.4. Direct Test Passes but `-javaagent` Fails Startup

Check:

- Whether `META-INF/MANIFEST.MF` actually has `Premain-Class: PatchAgent` in the main section.
- Whether the JAR contains `PatchAgent.class` and `BytePatchTransformer.class`.
- Whether nested/helper classes or ASM/Byte Buddy dependencies of the agent were omitted.
- Whether `premain` initializes a logger/loader/DI framework causing recursion.
- Whether `-javaagent` and classpath/module path are correct.
- Whether the JVM supports the class-file version of both the agent and target.
- Whether the agent accidentally instruments its own helpers/libraries.

**Note:** when agent startup fails, the JVM may exit early and log more details than a unit test. That is why you should pass the offline step before enabling the agent in a larger environment.

## 13. Rules for Preserving Reliability and Performance

- **Do not mutate `classfileBuffer` in place.** Snapshot bytes before testing to detect mutation.
- **Return `null` when unchanged.** Do not use an empty array to signal a no-op.
- **Do not load the target class inside `transform` via `Class.forName`.** It can cause circular loading.
- **Avoid logger I/O inside the callback.** Unit tests can log externally; production agents should use counters/bounded events.
- **Do not retain every `byte[]`/`ClassLoader`/`Class<?>` in a static cache.** Design appropriate size limits/eviction or weak references.
- **Keep output deterministic.** Avoid random helper names, timestamps, or nondeterministic ordering when unnecessary.
- **Separate baseline and instrumented tests into distinct JVM processes.** Do not try to redefine the same binary name on the same loader to compare behavior.
- **Do not ignore module/loader when policy relies on them.** Null synthetic args are only acceptable for testing rules independent of that metadata.
- **Inspect end-of-pipeline bytes.** Input to a later transformer may already differ from the original artifact.
- **Check the JVM verifier and runtime behavior.** A static parser cannot prove all branches, exceptions, linkage, and concurrency.
- **Set test deadlines.** A child JVM with a buggy agent can hang in a classloader deadlock; CI needs timeouts and stderr capture.
- **Never test-install an agent into a production JVM.** Use a child JVM/staging with controlled artifacts, versions, and configuration.

## 14. Recommended Workflow for a Transformer Change

```text
Change rule/instrumentation
       |
       v
Build .class fixture with matching --release and artifact
       |
       v
Unit: call transform(...) directly
       |
       +-- FAIL --> fix rule, fixture, parser
       |
       v
Check input immutability, no-op, idempotence
       |
       v
javap / ASM verifier / class-file validation
       |
       +-- FAIL --> fix bytecode, frames, constant pool
       |
       v
Isolated loader / child JVM -Xverify:all
       |
       +-- FAIL --> fix linking, code/loader dependencies
       |
       v
Package agent JAR and check manifest
       |
       v
Fresh child JVM: baseline vs -javaagent
       |
       +-- FAIL --> investigate lifecycle/callback/module/loader
       |
       v
Integration: multiple transformers, modules, loaders,
redefine/retransform, threads, rollback, performance
       |
       v
Staging / canary per operational process
```

Separating these steps shows whether a failure occurs **before** or **after** the JVM enters the real agent lifecycle. Do not lump everything into one large application startup command and compare only the final stdout.

## 15. Self-Check Questions

**Question 1.** Does calling `transform(null, null, "demo/Greeter", null, null, bytes)` mean an agent has been installed into the JVM?

**Answer:** No. That is an ordinary Java call to a method on a transformer object. The null module/loader/domain are test-supplied values, not JVM-provided metadata.

**Question 2.** Why should a unit test compare `original` with `original.clone()` after transformation?

**Answer:** To detect code that accidentally mutates `classfileBuffer` in place, violating the `ClassFileTransformer` contract.

**Question 3.** Why does `defineClass("demo.Greeter", output,...)` use dots while the callback `className` is `demo/Greeter`?

**Answer:** `ClassLoader.defineClass` uses a **binary name**, whereas the callback uses a JVM **internal name**.

**Question 4.** If `transform` returns an output array different from the input, does that prove the JVM will accept the class?

**Answer:** No. You still need classfile verification, define/link/invoke tests, and integration in the target runtime.

**Question 5.** Why are two `IsolatedLoader` instances needed to compare `BEFORE` with `AFTER!`?

**Answer:** The same binary name cannot be defined twice in the same defining loader. Two loaders create two independent class identities for the fixture.

**Question 6.** Why can a passing unit test still fail when running `-javaagent`?

**Answer:** Because the unit test has not checked the manifest, `premain`, callback order, real module/loader/protection domain, helper visibility, JVM verifier on the full path, or other transformers in the chain.

**Question 7.** Can `retransformClasses` be fully tested by using two class loaders?

**Answer:** No. Retransformation modifies the bytecode of an already-loaded class identity with its own capabilities and JVM semantics; isolated definition does not substitute for it.

**Question 8.** Why should you enable `-Xverify:all` in a test child JVM?

**Answer:** To catch many verifier/linking errors when running the new bytes on the JVM, though semantic tests and context-appropriate class loader/module checks are still required.

## 16. Official Documentation

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): overloads, callback metadata, `return null`, input immutability, transformer chain, and exception semantics.
- [Oracle Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, binary names, loader identity, class loading.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `redefineClasses`, `retransformClasses`, and capability checks.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest, `premain`, and Java agent startup.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-v`, `-c`, `-p`, and inspecting class files.
- [JVMS SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, `Code`, `StackMapTable`, and class-file format.
- [OpenJDK — ASM Commons/util](https://asm.ow2.io/): bytecode library documentation, `CheckClassAdapter` for projects using ASM.

**Takeaway:** test **class bytes as data** before installing an agent: assert the right class match, immutable input, valid distinct output, no-op/idempotence, and that the JVM can define/invoke it in an isolated test environment. Only then package the agent and launch **a fresh JVM with `-javaagent`** to confirm lifecycle, module/loader, and real results. An offline PASS is an important quality gate, **not** a substitute for full integration testing.
