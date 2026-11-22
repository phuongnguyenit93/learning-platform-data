# Constant Pool, Method Ordering, and Attributes May Differ from Saved Bytes

**Context:** Java Advance → instrumentation → **Retransformation**.

When calling `Instrumentation.retransformClasses(...)`, the JVM may provide `ClassFileTransformer` with a class file representation that **differs byte-for-byte** from the `.class` file that was compiled, packaged into a JAR, or recorded during a previous load. Differences may lie in the **constant pool**, **method declaration order**, or **the presence of certain attributes**. This is not automatically a bug, does not necessarily mean a method was semantically modified, and is not proof that an agent ran repeatedly.

The official `Instrumentation.retransformClasses` documentation states clearly: the *initial class file bytes* represent the bytes passed to the transformers at the most recent `defineClass` or `redefineClasses`, **but are not guaranteed to be identical to the original byte array**. The constant pool may differ in layout/number/order of entries; some attributes may not be present; and the order of methods, where order is not significant, may not be preserved. Constant pool indices used by the bytecode must still reference the corresponding pool of that class representation appropriately.

The goal of this lesson is to understand **why discrepancies occur**, **what must remain valid**, **how to read the retransform pipeline correctly**, and **how to compare at the right levels (bytes → structure → semantics → behavior)**.

> **Lab requirements:** JDK 17+ with HotSpot supporting retransformation. The main example uses an **agent started via `-javaagent`**, not dynamic attach; therefore, `ClassFileTransformer` can be observed without depending on a self-attach workflow or permission to attach to another JVM.

## 1. Distinguishing Four Types of “Class Representations”

Under the same name `demo/Target`, there are multiple forms of bytes over time:

| Label | Class representation | Where is it obtained? | Guaranteed to match another? |
| --- | --- | --- | --- |
| **D — disk** | Compiled `.class` or entry in a JAR | `Files.readAllBytes`, `jar`, `javap -classpath ...` | No |
| **L — initial load input** | `classfileBuffer` of the transformer invoked during load/define | Captured in callback with `classBeingRedefined == null` | May be D bytes or output of a preceding transformer |
| **R — retransformation input** | `classfileBuffer` when the JVM runs `retransformClasses` | Captured in callback with `classBeingRedefined != null` | Not guaranteed to match D or L |
| **T — transformer output** | New array returned by a transformer | Captured at `return transformedBytes` / saved as a separate snapshot | Depends on transform algorithm and preceding steps |

In addition, there is the **class definition currently executed by the JVM** after the pipeline completes. You should not infer that the VM keeps a byte-for-byte copy of file D in the heap; **`javap` on disk only reads D**, and does not automatically read T or code installed in the JVM.

For an observing agent that returns `null`, the agent's output *is interpreted as not modifying the input* in that callback invocation. However, R may still differ from L because the JVM reconstructed the underlying bytes, or because of another transformer in the pipeline, or because a redefinition occurred between observations.

### 1.1. Terms That Must Be Used Precisely

- **`retransformClasses(Class<?>...)`**: requests the JVM to rerun the transformation process for already-loaded classes, within the capabilities supported by the VM.
- **`redefineClasses(ClassDefinition...)`**: actively supplies a **new** set of class file bytes to replace the current definition; not the same operation as `retransformClasses`.
- **`classfileBuffer`**: the **input bytes to the current callback itself**; may already contain the result of a preceding transformer.
- **`canRetransform=false`**: the transformer receives callbacks on load/redefine but **is not called again** on retransform; its previously produced effects are reapplied according to the specification.
- **`canRetransform=true`**: the transformer is invoked during retransformation (and the corresponding load/redefine events).
- **Binary equality**: two arrays having identical bytes and the same length.
- **Structural/semantic equivalence**: class content equivalent according to defined criteria, which may **not be binary-equal**.

No single `Arrays.equals(before, after)` call can by itself explain where a difference originated.

## 2. The JVM Contract on Differences in Initial Bytes

The Javadoc of `java.lang.instrument.Instrumentation` for `retransformClasses` describes the possibilities:

1. **Different constant pool layout/content:** the number of entries may be larger or smaller and the order may change.
2. **Indices in bytecode remain consistent:** operands of `ldc`, `getfield`, `invokevirtual`, `invokestatic`, etc. must point to the **correct entry in the constant pool of that same class representation**.
3. **Some attributes may be absent:** you must not assume every attribute from the original class is still present when the JVM supplies the bytes again.
4. **Method order may change:** method declaration order is not a method-identifying key under class-file semantics.
5. **Not always different:** the specification says **may** differ, not that every retransform is guaranteed to reorder the pool, strip attributes, or reorder methods.

Thus, both of the following cases **conform** to the contract, provided all other constraints are met:

```text
Case A: D == L == R                  [byte-for-byte equal]
Case B: D != R, but corresponding structure/behavior remains correct
```

The safe conclusion is **“byte identity is not guaranteed”**, not “the JVM always rewrites the constant pool on every pass”.

### 2.1. Boundaries of Allowed Differences

The JVM is allowed to differ in parts that do not break the validity of the class representation; that does **not** mean format or semantic checks can be skipped. The received `classfileBuffer` must be interpreted according to the **JVMS ClassFile format**, in which every field/method/attribute has a well-defined structure. Constant pool references must be valid; instructions must match descriptors/stack; the class file at the end of the pipeline must pass validation before being installed.

For an actual transformation, the JVM also enforces **retransformation restrictions**: you cannot arbitrarily add/remove/rename fields or methods, change inheritance or signatures if the current capability does not support it. Errors such as `UnsupportedOperationException`, `UnmodifiableClassException`, or validation errors must be analyzed separately, rather than attributing everything to “the pool was reordered”.

## 3. Why Can the Constant Pool Differ While Opcodes Keep the Same Meaning?

In a class file, the **constant pool** is a table storing UTF-8 strings, class names, names/types, references to fields/methods, integer/string constants, method handles, bootstrap-linked entries, and other `CONSTANT_*` types. Many bytecode instructions point into this table using a **numeric index**.

Suppose in a class file, the Java statement:

```java
System.out.println("hello");
```

is modeled through the following symbols:

```text
GETSTATIC  java/lang/System.out:Ljava/io/PrintStream;
LDC        "hello"
INVOKEVIRTUAL java/io/PrintStream.println:(Ljava/lang/String;)V
```

In actual bytes, instructions like `getstatic` and `invokevirtual` carry a **constant-pool index**. Illustratively:

```text
Snapshot A
  #7  = Fieldref java/lang/System.out:Ljava/io/PrintStream;
  #11 = String "hello"
  #17 = Methodref java/io/PrintStream.println:(Ljava/lang/String;)V

  getstatic #7
  ldc #11
  invokevirtual #17

Snapshot B (illustrating a different layout, NOT actual javap output)
  #21 = Fieldref java/lang/System.out:Ljava/io/PrintStream;
  #9  = String "hello"
  #33 = Methodref java/io/PrintStream.println:(Ljava/lang/String;)V

  getstatic #21
  ldc #9
  invokevirtual #33
```

Both can invoke the **exact same target symbol**. What matters is that `#17` in snapshot A **and `#33` in snapshot B** resolve to the same owner/name/descriptor; not that the `#n` numbers are equal.

### 3.1. Consequences When Pool Layout Changes

- **Raw bytes differ:** `constant_pool_count`, entry order, and operand indices may differ, so SHA-256 may differ even when method logic is equivalent.
- **Instruction size may differ:** `ldc` uses a `u1` operand, while `ldc_w` uses `u2` for larger indices; a writer may choose the appropriate variant. When code size changes, branch offsets and related metadata must also remain valid.
- **Unused entries may exist:** the presence of an extra entry in the pool does not by itself prove a new instruction was inserted.
- **`long`/`double` occupy two slots:** the index number does not equal the count of usable entries; index 0 is not a regular entry.
- **`invokedynamic`, `condy`, bootstrap metadata:** you must compare symbols/arguments and associated bootstrap methods, not just `#n` text.

**Be careful:** a constant pool reference actually changing from `Math.abs(I)I` to `Math.max(II)I`, from an old field to a different field, or from `"hello"` to `"goodbye"` **is a semantic change**. Do not use “the pool may be reordered” as an excuse to ignore every discrepancy.

### 3.2. What Must Remain Consistent Within Each Snapshot

Within a single snapshot, `getstatic #k` must point to the appropriate entry kind, `invoke* #m` must point to a method reference of the right type, field/method descriptors must be valid, and `ldc` must use a valid constant. When pool indices are changed, the writer is responsible for updating **all references in the class file**, not just the opcodes visible at a glance.

Therefore, **never sort the constant pool yourself using `Arrays.sort(...)` over a byte region**: the format consists of variable-length structures, index numbers appear in many places, some entries occupy two slots, and metadata has cross-references. Use a proper class-file parser/writer such as ASM or the JDK Class-File API (JDK 24+).

## 4. Method Ordering May Change

According to the JVMS, a `method_info` is tied to its **name and method descriptor**. There cannot be two methods with the same **name + descriptor** pair in the same class file; however, the JVM does not need to treat the **Nth position in `methods[]`** as a method's identity.

For example, one snapshot may have:

```text
methods[] of Snapshot A
  0. <init>()V
  1. alpha(I)I
  2. beta(Ljava/lang/String;)V
```

Another snapshot may use the order:

```text
methods[] of Snapshot B
  0. beta(Ljava/lang/String;)V
  1. <init>()V
  2. alpha(I)I
```

If each method still has the right name/descriptor/flags/code/metadata, an **index-based** comparison will report a series of “changed methods”, even though only the **order of `method_info` entries** differs.

### 4.1. The Correct Comparison Key

Within a class, the fundamental key of a method is:

```text
classInternalName + definingLoaderIdentity (when comparing runtime classes)
+ methodName + methodDescriptor
```

For example:

```text
demo/Service#save(Ljava/lang/String;)V
demo/Service#save(I)V
demo/Service#<init>()V
```

Two `save` overloads share the same **name** but have different **descriptors**. And when the same binary name can be defined by **two class loaders**, runtime logging/caching must also record **loader/module identity** as appropriate for the context.

Do **not** reorder **instructions inside a method's Code** to “normalize” it. The order of instructions, branches, handlers, monitor operations, and side effects **is semantically significant**. Only lists whose order is defined as insignificant by the spec can be compared as sets/maps.

## 5. How Should “Some Attributes May Not Be Present” Be Understood?

Class-file **attributes** appear at the class, field, method, or `Code` level. For example:

| Attribute | Common location | What can it be used for? | Can it be ignored in QA? |
| --- | --- | --- | --- |
| `SourceFile` | Class | Source file name for diagnostics | May differ/be missing in some snapshots; should be noted |
| `LineNumberTable` | Code | Bytecode ↔ source line mapping | Missing may affect stack traces/debugging |
| `LocalVariableTable` | Code | Local variable debug names and scopes | Usually debug metadata; missing does not alter computation |
| `LocalVariableTypeTable` | Code | Generic type debug info | May affect debugger experience |
| `Signature` | Class/field/method | Generic signatures | **May affect reflection generic metadata** |
| `RuntimeVisibleAnnotations` | Class/field/method... | Annotations visible at runtime | Cannot be automatically ignored |
| `Exceptions` | Method | Declared checked exceptions metadata | May affect reflection/tooling |
| `Code` | Non-abstract/non-native method | Bytecode and exception table | Missing/wrong in a method with a body is critical |
| `StackMapTable` | Code | Verification type frames | Wrong table can cause `VerifyError` |
| `Record`, `NestHost`, `NestMembers`, `PermittedSubclasses` | Class | Record/nest/sealed semantics | Must be compared according to corresponding semantics |
| `BootstrapMethods` | Class | Bootstrap information for dynamic linkage | Wrong references break `invokedynamic`/`condy` |

The Javadoc on retransformation **does not guarantee a fixed list of attributes that will be stripped**. Therefore, do not claim “retransform always removes `LineNumberTable`” or “the JVM always preserves all annotations”. Specific cases require inspecting the **actual bytes received** and the documentation of the running JVM.

An attribute being “optional in class-file syntax” also **does not mean it is safe to drop** in every application. Many frameworks read annotations, generic signatures, records, or module metadata. Establish a clear comparison policy:

- **Debug-oriented comparison:** allows differences in `SourceFile`, line/local tables if the goal is solely execution semantics and loss of debug info is acceptable.
- **Reflection/API compatibility:** compares `Signature`, annotations, method parameters, exceptions, records, nest/permits/module metadata as needed.
- **Verifier/runtime correctness:** strictly ensures `Code`, `StackMapTable`, handlers, type relationships, and class-file validity are correct.
- **Reproducible build/forensics:** requires preserving exact bytes or metadata when genuinely required; do not use a retransform snapshot as “proof” of byte identity against a release artifact.

## 6. The Retransformation Pipeline: Understanding Which Step Produces the Bytes

`Instrumentation.retransformClasses(Target.class)` does not mean calling all transformers again identically to when the class was loaded. The Javadoc defines the pipeline:

```text
Initial class: bytes from defineClass or redefineClasses (logical initial)
     │
     │  JVM may re-represent valid bytes
     ▼
[T0]  non-retransform-capable transformers:
      NOT called again; previous results are automatically reapplied
     ▼
[T1]  retransform-capable transformers:
      transform(...) callback is CALLED AGAIN in group order
     ▼
[T2]  bytecode definitions after transform
     ▼
VM checks, verifies, and installs the new class definition
```

In practice, there are also **native transformers** (JVMTI `ClassFileLoadHook`) following the group order defined by the API:

1. Non-retransform-capable Java transformers.
2. Non-retransform-capable native transformers.
3. Retransform-capable Java transformers.
4. Retransform-capable native transformers.

Within each group, registration order is preserved. For non-retransform-capable groups, the VM **reapplies the previous result** without **calling that callback again**. Therefore, the R that a `canRetransform=true` transformer receives may already include the results of preceding transformers.

### 6.1. Two Dangerous Misconceptions

**Misconception A: “The next pass starts with the output of this same transformer from the previous pass.”**  
Do not assume this. Retransformation starts from the *initial class file bytes* under the API model, reapplies results of non-retransform-capable transformers, and calls retransform-capable transformers again. If the code you inserted on the previous pass came from a `canRetransform=true` transformer, the next pass will not necessarily have it in the input buffer.

**Misconception B: “Because R differs from D, an unknown agent must have instrumented it.”**  
Incorrect. The specification itself allows R not to be byte-identical to D. You must inspect structure, semantic method bodies, the chain of transformers, and the final output, rather than inferring solely from hashes.

### 6.2. Relationship to Redefinition and Runtime State

- `redefineClasses` supplies a new set of bytes to the VM on demand; afterward, *initial* for retransformation may be based on the **most recent redefine**, not the original JAR file.
- `retransformClasses` does not rerun static initializers and does not automatically reset static fields; existing objects continue to exist.
- If a method currently has **active stack frames**, those frames continue running the old bytecode definition as specified; **new invocations** use the new definition.
- Retransformation is a capability that may not exist in every VM/configuration. `Instrumentation.isRetransformClassesSupported()`, the manifest `Can-Retransform-Classes: true`, and `isModifiableClass(target)` must all be checked.

A byte difference in a snapshot **does not directly tell you** which version an active frame is executing at a given moment.

## 7. Complete Java 17+ Lab: Capturing Snapshots During Load and Retransform

The purpose of the lab is to **observe two exact points in time** and **save independent snapshots**, not to force the JVM to change the constant pool. The observer does not transform bytecode: it only clones the buffer, logs the callback, and **`return null`**. On some VMs both snapshots may be binary-equal; on other VMs they may differ. **Both are valid**, and that is the core takeaway.

### 7.1. Project Structure

Create the directory `retransform-snapshots`:

```text
retransform-snapshots/
├── agent.mf
└── src/
    └── demo/
        ├── Target.java
        ├── ObserverAgent.java
        ├── AppMain.java
        └── CompareSnapshots.java
```

Compiling produces `out/demo/*.class` and the agent JAR. At runtime, two files are created under `snapshots/load/demo/Target.class` and `snapshots/retransform/demo/Target.class`. Do not touch `out/demo/Target.class`.

### 7.2. `src/demo/Target.java`

```java
package demo;

public final class Target {
    private Target() {}

    public static String message() {
        return "hello";
    }
}
```

### 7.3. `src/demo/ObserverAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ObserverAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile byte[] loadBytes;
    private static volatile byte[] retransformedBytes;

    private ObserverAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This VM does not support retransformation");
        }

        inst.addTransformer(new Observer(), true);
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            if (classBeingRedefined == null) {
                loadBytes = classfileBuffer.clone();
                System.out.println("OBSERVED=load");
            } else {
                retransformedBytes = classfileBuffer.clone();
                System.out.println("OBSERVED=retransform");
            }

            // Observer does not modify classfileBuffer at all.
            return null;
        }
    }

    public static void retransformAndSave(Class<?> target)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target cannot be modified");
        }

        inst.retransformClasses(target);

        byte[] load = loadBytes;
        byte[] again = retransformedBytes;
        if (load == null || again == null) {
            throw new IllegalStateException("Missing callback snapshot");
        }

        Path first = Path.of(
                "snapshots", "load", "demo", "Target.class");
        Path second = Path.of(
                "snapshots", "retransform", "demo", "Target.class");

        Files.createDirectories(first.getParent());
        Files.createDirectories(second.getParent());
        Files.write(first, load);
        Files.write(second, again);
        System.out.println("SNAPSHOTS=2");
    }
}
```

**Why does this code satisfy the contract?**

- `premain` registers a **`canRetransform=true`** transformer before `AppMain` calls `Target.message()`.
- Filters specifically for `demo/Target` by **internal class name**. Does not instrument every JDK class or the agent's own classes.
- `classBeingRedefined == null` in the first callback during load; on `Target`'s retransform pass, this value is non-`null`.
- `clone()` creates separate snapshots; does not retain a reference to `classfileBuffer` and never writes into the JVM-provided buffer.
- `return null` means the observer requests no changes to the class.
- Using `volatile` publishes snapshots safely when the callback and application code run on different threads; the lab intentionally performs only one load and one retransform.
- I/O to write snapshots happens **after the callback**, not writing files on the hot class-loading path. In a production agent, avoid retaining all class bytes indefinitely and have a dedicated policy for multiple loaders/retransform passes.

### 7.4. `src/demo/AppMain.java`

```java
package demo;

public final class AppMain {
    private AppMain() {}

    public static void main(String[] args) throws Exception {
        System.out.println("BEFORE=" + Target.message());
        ObserverAgent.retransformAndSave(Target.class);
        System.out.println("AFTER=" + Target.message());
    }
}
```

### 7.5. `agent.mf`

Create the text file **`agent.mf`**, one entry per line and **with a trailing newline at the end of the file**:

```text
Manifest-Version: 1.0
Premain-Class: demo.ObserverAgent
Can-Retransform-Classes: true
```

`Premain-Class` specifies the entrypoint for `-javaagent`. `Can-Retransform-Classes: true` is the agent's capability request; it does not guarantee every JVM supports it, so the code still checks `isRetransformClassesSupported()`.

### 7.6. Compile and Run Commands

On JDK 17+ in the `retransform-snapshots` directory, run:

```bash
javac -d out src/demo/Target.java src/demo/ObserverAgent.java src/demo/AppMain.java
jar --create --file observer-agent.jar --manifest agent.mf -C out .
java -javaagent:observer-agent.jar -cp out demo.AppMain
```

The three `javac`/`jar`/`java` commands use standard JDK syntax. The `out` directory is created by `javac -d` when needed. On a HotSpot/JDK environment supporting retransform with a modifiable target, the **deterministic stdout from the demo** is:

```text
OBSERVED=load
BEFORE=hello
OBSERVED=retransform
SNAPSHOTS=2
AFTER=hello
```

This is the application/agent stdout of the example above, excluding any extra lines a shell/tool might add. In this lab, both before and after retransform return `hello` because the transformer **does not modify bytecode**. If the VM does not support the capability, agent startup fails with the explicit error in `premain`; that is an environmental condition, not a successful output.

**There is no fixed `BYTES_EQUAL=true` line** in the output because **equality of the two snapshots is not guaranteed by the specification**. We will use a separate comparator program to inspect the actual result instead of fabricating a value for every machine.

### 7.7. Reading the Three Snapshots: Disk, Load, Retransform

After running, there are three artifacts to compare:

```text
out/demo/Target.class
snapshots/load/demo/Target.class
snapshots/retransform/demo/Target.class
```

Using `javap`:

```bash
javap -classpath out -p -s -c -v demo.Target
javap -classpath snapshots/load -p -s -c -v demo.Target
javap -classpath snapshots/retransform -p -s -c -v demo.Target
```

To generate text dumps for diffing:

```bash
javap -classpath out -p -s -c -v demo.Target > disk.javap.txt
javap -classpath snapshots/load -p -s -c -v demo.Target > load.javap.txt
javap -classpath snapshots/retransform -p -s -c -v demo.Target > retransform.javap.txt
```

`javap` only reads the class file on the path you specify. The `-v` output includes the header, CP indices, method listings, and attributes; a raw textual diff can be very long and contain differences that are not bugs. On Windows PowerShell you can use:

```powershell
Compare-Object (Get-Content load.javap.txt) (Get-Content retransform.javap.txt)
```

On Linux/macOS:

```bash
diff -u load.javap.txt retransform.javap.txt
```

If the output does not differ, **do not force a difference in the experiment by modifying `classfileBuffer`**. The main goal of the lab is to observe that the JVM contract **allows differences**, not that it promises every VM must produce them.

### 7.8. Java 17+ Comparator to See Actual Results (No Guessing)

Create **`src/demo/CompareSnapshots.java`**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public final class CompareSnapshots {
    private CompareSnapshots() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: CompareSnapshots <file-a> <file-b>");
        }

        byte[] left = Files.readAllBytes(Path.of(args[0]));
        byte[] right = Files.readAllBytes(Path.of(args[1]));

        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        System.out.println("BYTE_EQUAL=" + Arrays.equals(left, right));
        System.out.println("LEFT_SHA256="
                + HexFormat.of().formatHex(sha.digest(left)));
        System.out.println("RIGHT_SHA256="
                + HexFormat.of().formatHex(sha.digest(right)));
    }
}
```

Compile/run:

```bash
javac -d out src/demo/CompareSnapshots.java
java -cp out demo.CompareSnapshots snapshots/load/demo/Target.class snapshots/retransform/demo/Target.class
```

Example keys that will appear in stdout:

```text
BYTE_EQUAL=<true or false depending on the actual JVM>
LEFT_SHA256=<64 hex characters of the first file>
RIGHT_SHA256=<64 hex characters of the second file>
```

**This is an output format template, not fixed stdout.** The program computes real data at runtime; the hashes on the last two lines cannot be known in advance from the prompt. With `BYTE_EQUAL=false`, inspect `javap` and compare structure, rather than concluding the app was semantically altered. With `BYTE_EQUAL=true`, do not conclude the JVM is required to preserve identity on subsequent runs or for other classes.

## 8. Supplementary Exercise: Producing Two Class Files with Different Bytes but Identical Behavior

To observe **in a controlled manner** the phenomenon of class files with different bytes, you can compile the same class with two different debug metadata configurations. This is a **javac experiment**, **not proof that the JVM did the same during retransformation**.

Save **`DebugSample.java`**:

```java
public final class DebugSample {
    public static int doubleOf(int value) {
        int result = value * 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println(doubleOf(4));
    }
}
```

On a machine with JDK 17+ (create two output directories as desired; `javac -d` requires the destination directory to already exist in some environments):

```bash
mkdir with-debug
mkdir no-debug
javac -g -d with-debug DebugSample.java
javac -g:none -d no-debug DebugSample.java
java -cp with-debug DebugSample
java -cp no-debug DebugSample
javap -classpath with-debug -p -c -v DebugSample > with-debug.txt
javap -classpath no-debug -p -c -v DebugSample > no-debug.txt
```

Both `java` runs print **exact**:

```text
8
```

However, `with-debug/DebugSample.class` and `no-debug/DebugSample.class` typically differ in debug attributes such as `LineNumberTable`, `LocalVariableTable`, or `SourceFile` according to the `javac` options. `javac -g` requests full debug info; `-g:none` emits no debug info. Use `javap -v` to confirm which attribute names are actually present/absent; do not infer the kind of changed attribute from a hash.

This experiment clearly illustrates: **two class files with identical behavior can still be non-binary-identical**. It does not prove every attribute can be stripped during retransformation, and cannot replace checking `Instrumentation`'s own constraints.

## 9. How to Compare “at the Right Layer,” from Coarse to Deep

| Comparison level | What is compared? | Strengths | Limitations |
| --- | --- | --- | --- |
| **L0. Raw bytes/hash** | `Arrays.equals`, SHA-256 | Verifies files are completely identical | Reports differences even when only pool/order/debug attrs change |
| **L1. Header/schema** | Class name, version, superclass, interfaces, access flags, fields/methods by key | Detects schema changes that may violate redefine rules | Does not yet prove method behavior |
| **L2. Constant symbols** | Resolves CP refs to owner/name/descriptor/constant values | Eliminates `#n` numbering noise | Requires decoding bootstrap/dynamic constants properly |
| **L3. Code logic** | Instruction kinds, symbolic operands, branch flow, handlers, return semantics | Reveals execution logic changes | Offsets, `ldc`/`ldc_w`, and frames may differ while remaining valid |
| **L4. Metadata policy** | `Code`/`StackMapTable` and selected attributes | Identifies changes affecting verifier, reflection, debug | Requires distinguishing mandatory/optional/semantic attributes |
| **L5. Verification and behavior** | Load class, run tests, errors/returns/side effects/concurrency | Catches real runtime failures | Does not prove two programs are equivalent for all inputs |

**Recommended QA flow:**

```text
(1) Record snapshot source + timestamp + JVM vendor/version
                         │
                         ▼
(2) If bytes are equal ─────► Conclude binary-equal (for this pair)
    If bytes differ:
                         │
                         ▼
(3) Parse ClassFile, match class name / superclass / interfaces
                         │
                         ▼
(4) Compare fields and methods by name + descriptor, NOT by index
                         │
                         ▼
(5) Resolve constant-pool references, compare symbolic code content
                         │
                         ▼
(6) Compare attributes per policy, validate branches/handlers/stack maps
                         │
                         ▼
(7) Run verifier/application/tests and check side effects
```

### 9.1. Building a Fingerprint for Debugging Without Redefining Equivalence

A logical fingerprint might include:

```text
Class name + class major version + flags
Superclass + interfaces in structural meaning
Fields: sorted by (name, descriptor) with flags and selected metadata
Methods: sorted by (name, descriptor) with flags and selected metadata
Code: opcodes and resolved symbolic operands
Control flow: normalized branch targets and exception handlers
Attributes: normalized values of attributes that must be compared
```

This is **pseudocode describing a structural summary**, not a standalone runnable Java program. To implement it, use ASM or the JDK Class-File API (JDK 24+) to parse the format; do not slice bytes by guessed offsets. “Normalize” only at places where you have verified an equivalence relation. For example, **method** order can be treated as a keyed map, whereas **instruction** order and **exception handler** order can affect semantics and must not be sorted arbitrarily.

Do not use a logical fingerprint in place of SHA-256 if the requirement is **proving byte-for-byte artifact immutability** (compliance, supply-chain verification). The two goals are different and require two different kinds of checks.

## 10. Diff Locations That Easily Cause False Alarms

### 10.1. Different Constant Pool Indices

`javap -v` may show:

```text
#12 = Methodref ... java/lang/Object."<init>":()V
#28 = Methodref ... java/lang/Object."<init>":()V
```

The two lines above are **index illustrations only**, not output from a specific file. If both snapshots call `java/lang/Object.<init>()V`, differing `#12` and `#28` indices are not enough to report different behavior.

**Right:** compare owner/name/descriptor after resolution.  
**Wrong:** compare raw text `#12 != #28` and conclude the class called a different method.

### 10.2. Different Method Ordering

If the `javap` dump of A prints `alpha` before `beta`, while B prints `beta` before `alpha`, a raw text diff will flag an entire block as changed. Map each method by `name+descriptor` and compare the corresponding contents.

### 10.3. Absent Debug Attributes

A changed `LineNumberTable` may cause stack traces to lack line numbers, but does not prove computation logic changed. Do not treat it as harmless if debugging is a requirement; report a **metadata difference** separately from a **code behavior difference**.

### 10.4. “Different Hash” Even When the Transformer Returns `null`

Even when the lab's observer only returns `null`, the JVM may supply an input R that does not match input L under the specification. Discrepancies can also come from **other transformers**, a redefinition that occurred, or a snapshot not taken at the right point. Therefore, always record the **snapshot stage** instead of using a vague “original” label.

### 10.5. Code Was Changed, Yet SHA Did Not Change?

If you compare the exact **same two files** with SHA-256 and the hashes are genuinely equal, in practice the bytes are almost certainly identical; however, that fact does not guarantee in-memory instrumentation never ran. You might be hashing **before/after disk files** without capturing the transformer's output bytes; or the class was transformed inside the JVM while the artifact on disk remained untouched.

## 11. Idempotency: Do Not Rely on Comparing Original Bytes

A transformer may need to avoid inserting a hook twice across load, redefine, or retransform. Two error-prone approaches:

- `Arrays.equals(classfileBuffer, originalDiskBytes)` to decide “not yet instrumented”: the JVM may re-represent bytes, causing the equality check to fail even when no hook is present.
- Checking a specific offset, such as the byte at position 123 or constant-pool index `#15`, to detect a marker: offsets/indices can shift when builds/pipelines/CPs change.

**A more resilient approach:** inspect **code structure** and actual hook characteristics, such as an invocation to `agent/TraceHooks.enter(Ljava/lang/String;)V` at the right site; or use valid metadata/markers supported by the pipeline, combined with the JVM's policy on allowed changes during retransform.

Note: do **not** use a “add a new marker field” strategy during retransformation if the JVM does not allow changing class schema. An approach that works at load time may be invalid during retransform. For a retransform-capable transformer, you can design the transform to be **deterministic on input without the current stage's hook**, and write tests for repeated retransformation. If another transformer precedes yours, be aware its hook may already have been reapplied.

## 12. Common Errors and Troubleshooting

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Disk file SHA-256 differs from retransform snapshot | JVM may re-represent bytes, transformer pipeline, redefinition | Compare at the right stage and semantic diff; do not jump to conclusions |
| `javap -v` shows different CP count or `#n` | CP layout/contents changed, writer/VM restructured | Resolve symbolic references; verify operands remain valid |
| Same method names, but diff reports everything shifted | Comparing by `methods[]` position instead of key | Map by `name + descriptor` |
| `SourceFile`, `LineNumberTable` missing | Snapshot may differ in attributes or compiled with `javac -g:none` | Classify debug metadata, note debugger impact |
| Runtime annotations disappeared | Possible unintended transformation | Do not ignore; check reflection behavior and pipeline |
| `VerifyError` after transform | Wrong stack maps, branch offsets, CP refs, or method descriptors | Use verifier, ASM check, `javap -v`; fix writer/transform logic |
| `UnmodifiableClassException` | JVM does not allow modifying that class | Check `isModifiableClass`, or different target type |
| `UnsupportedOperationException` when registering retransform | Agent/VM does not support the capability | Manifest `Can-Retransform-Classes` and `isRetransformClassesSupported` |
| Transformer callback “did not run again” | Registered with `canRetransform=false` | Expected per contract; previous result is reapplied |
| Hook inserted twice | Non-idempotent transformer or duplicate pipeline | Detect hook by code symbols; test multiple retransform passes |
| `javap` stdout diff has many changes | Constant pool indices, methods order, or attributes differ | Separate code logic diff from metadata/layout |
| `ClassFormatError` or `VerifyError` | Invalid output class | Do not just compare hashes; validate class file and stack/frames |
| Output lost after calling `retransformClasses` | Possibly only instrumenting at load, not retransform-capable | Analyze transformer groups and automatic reapplication |
| JVM uses old definition in running frame | Active frames keep old bytecode | Check semantics of active frames vs new invokes |
| Bytes match on machine A, differ on machine B | Different vendor, VM, version, or tools | Do not hardcode expectations of byte identity |

A real bug must be demonstrated by **changed symbols/behavior**, an invalid class format, required metadata lost against requirements, or incorrect transform coverage—not merely by a new hash.

## 13. Verification Checklist in an Instrumentation Project

- [ ] Record full **vendor, `java.vm.name`, JDK version, loader/module identity**, timestamp, and action `load`/`redefine`/`retransform`.
- [ ] Clearly label whether a snapshot is **disk**, **callback input**, or **callback output**; avoid misleading names like `original.class`.
- [ ] Do not mutate `classfileBuffer` in place; return a new valid array when transforming, or `null` when unchanged.
- [ ] Enable capability in the manifest and `addTransformer(..., true)` when retransform is needed, and check `isRetransformClassesSupported()`/`isModifiableClass`.
- [ ] Do not expect a `canRetransform=false` transformer to be invoked again; understand the result reapplication mechanism.
- [ ] Compare hashes when byte identity is the goal; do not conclude a semantic difference solely from hashes.
- [ ] Map methods by **name + descriptor**, not by index/text block.
- [ ] Resolve constant-pool indices to **symbolic references** before comparing instructions.
- [ ] Compare attributes by purpose: debug, reflection, verifier, module, or API compatibility.
- [ ] When comparing code, preserve the semantics of instruction order/exception handlers/control flow; do not sort arbitrarily.
- [ ] Run the verifier and test behavior after transformation, including normal returns/exceptions/constructors/overloads.
- [ ] Test retransform **twice in a row** to catch duplicate hooks and inconsistent state.
- [ ] If bytes differ but behavior matches, record the conclusion at the right level: **not binary-equal, no semantic regression observed under current checks**.
- [ ] Do not claim “every JVM reorders the pool” or “any attribute can be discarded”; rely on the documentation of the actual VM.

## 14. Self-Check Questions

1. **Why can the SHA-256 of a class file on disk differ from the callback snapshot during retransform?**  
   Because the VM is allowed to use a class file representation that is not byte-identical to the original define/redefine input; furthermore, the transformer pipeline and redefinition can affect it.

2. **Constant pool entry `println:(I)V` is at `#18` in snapshot A and `#41` in snapshot B. Does behavior necessarily change?**  
   No. You must verify that the bytecode of each snapshot references the right symbol; `#n` numbers only have meaning within that snapshot's pool.

3. **Two snapshots have the same three methods but in different order. How should you compare them?**  
   Use the key `class + methodName + descriptor`, then compare flags, code, and metadata for each matching pair.

4. **Is the absence of some attributes in the retransform callback a JVM bug?**  
   Not automatically. The Javadoc allows some attributes to be absent. However, metadata affecting runtime/reflection/verification must be evaluated against requirements, not ignored unconditionally.

5. **Is `canRetransform=false` called again during `retransformClasses`?**  
   No, under the standard mechanism; the VM reapplies the previous transformation result without invoking that callback.

6. **If the observer returns `null`, is snapshot R always byte-for-byte identical to snapshot L?**  
   Not guaranteed. `null` only states that the observer made no transformation in that callback; the VM/pipeline may still supply different input.

7. **Can a `canRetransform=true` transformer assume input R contains the hook it inserted on the first pass?**  
   No. The retransform pipeline starts from initial bytes and reapplies non-retransform-capable groups; design transforms without depending on this false assumption.

8. **Can `StackMapTable` be omitted because Java can infer the stack on its own?**  
   Do not assume that. A valid class file and verifier constraints must be satisfied; verification metadata may be required under the applicable circumstances.

9. **Methods `save(String)` and `save(int)` share the same name. Can you use just `save` as the key?**  
   No. You must include the descriptor, such as `(Ljava/lang/String;)V` and `(I)V`.

10. **If `byte[]` differs but program output is the same, is equivalence proven for all inputs?**  
    No. That only covers a few behavioral checks; code/metadata analysis, test coverage, and business constraints are still required.

11. **Does `javap -classpath out demo.Target` automatically show code that a transformer only installed in the JVM?**  
    No. It reads bytes from the specified classpath; you must dump the transformer's output separately to inspect runtime transformations.

12. **Why can running a retransform preserve the state of static fields and existing objects?**  
    Because `retransformClasses` replaces the class definition according to VM rules without rerunning static initialization or resetting object state.

## 15. Official Sources

1. Oracle JDK 17 — **`Instrumentation.retransformClasses`**: constant pool/order/attribute differences, pipeline, active frames, and schema restrictions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)
2. Oracle JDK 25 — **`Instrumentation`** (cross-checking the contract in a newer release): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. Oracle JDK 17 — **`ClassFileTransformer`**, transformer ordering, `classfileBuffer`, `null`, and output arrays: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. Oracle JDK 17 — **Agent package**, `Premain-Class` and `Can-Retransform-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
5. JVMS 17 — **Class-file format `4`**, constant pool, methods, attributes, and Code: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
6. Oracle JDK 17 — **`javap`**, `-c`, `-v`, `-p`, `-s`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
7. JVMTI — **RetransformClasses** and VM Tool Interface constraints: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RetransformClasses

**Conclusion:** `retransformClasses` operates on a **valid class file definition** rather than promising to return the exact bytes of a saved artifact. Constant-pool entries, method ordering, and attributes may differ. When building instrumentation tools, protect the input byte buffer, identify the stage/snapshot, compare structure by symbols/descriptors, ignore metadata only under an explicit policy, and finally verify with the verifier and runtime behavior.
