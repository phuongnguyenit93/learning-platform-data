# Verification: Checking the Structure and Validity of Java Bytecode

**Verification** (bytecode verification) is a phase within **linking** of the class lifecycle on the JVM. It checks that the binary representation of a class or interface conforms to the constraints of the Java Virtual Machine Specification (JVMS), particularly the rules regarding **value types, the operand stack, local variables, and control flow**. The goal is to prevent invalid bytecode from performing operations that break the JVM's type-safety assumptions.

An important point: a `.class` file *may be readable and have a recognizable structure* yet still be rejected because of invalid instruction content. Conversely, a class that passes verification can still throw exceptions at runtime or have business-logic bugs.

## 1. Where does verification fit in the class lifecycle?

Overview diagram:

```text
Loading (locate/read class data, create Class)
    |
    v
Linking
    |-- Verification  : check structural and type-safety constraints of bytecode
    |-- Preparation   : allocate and initialize static fields to default values
    '-- Resolution    : convert symbolic references into direct references (*)
    |
    v
Initialization        : run <clinit> when initialization conditions are triggered
    |
    v
Using the class       : invoke methods, instantiate objects, access fields...
```

`(*)` **Resolution can occur lazily** on a per-reference basis, depending on JVM rules; the diagram shows the tasks belonging to linking and does not guarantee the execution order of all operations or when errors appear in every implementation.

It is important to distinguish:

- **Loading:** the loader locates bytecode and defines the class. A class can come from a directory, JAR, module, network, or a byte array provided by a custom `ClassLoader`.
- **Verification:** the JVM evaluates whether the class satisfies class file and bytecode constraints. It does not need to execute business logic to perform this check.
- **Preparation:** prepares `static` fields with default values (which is not the same as running assignments in the class's `static` code).
- **Resolution:** resolves symbolic references to classes, fields, and methods. Some other linkage errors can arise here or when the class is used.
- **Initialization:** runs the class initializer `<clinit>` when needed. Verification completes before the class is initialized, but you should not infer that every error related to a dependency will appear immediately when the first class is loaded.

For example, `Class.forName(name, false, loader)` requests loading and linking the class **without requiring class initialization**. The exact point at which a verifier actually analyzes each method may depend on the implementation and the operation being performed. Simply observing a `Class<?>` object is not proof of when every check took place.

## 2. What does the JVM check?

Verification is not a single check, but a set of checks performed on class file information and bytecode. For learning purposes, they can be divided into two groups:

| Check group | Typical questions | Examples of rejection |
|---|---|---|
| Class file format/structure | Are the header, constant pool, method table, attributes, indices, and structure valid? | Corrupted `CAFEBABE` magic bytes or a malformed constant-pool entry |
| Semantic constraints and type safety | Are the bytecode instructions, stack, locals, branches, and return types consistent? | A method declared to return `int` uses `areturn` with an `int` value |

Some important details:

1. **Class format:** checks the class file structure (magic number, supported version, constant pool, field/method metadata, Code attribute, and corresponding constraints). Not every format error is reported as a `VerifyError`; structural errors typically result in a `ClassFormatError` or an appropriate linkage error class.
2. **Operand stack:** determines the types and number of elements on the stack at each program point; code must not pop a value that is not there or use an operand of the wrong type.
3. **Local variables:** using a local variable must match the type currently stored in it; reading a variable that has not been assigned a valid state or misusing a slot as a different type can be rejected.
4. **Return/argument typing:** `ireturn` may only be used in contexts with an appropriate integer result type; `areturn` is for reference values; arguments to a method invocation must match the method's descriptor.
5. **Control flow:** jumps must target valid instruction offsets; at merge points where multiple branches converge, the types and states of the stack and locals must have a valid relationship. Exception handlers also have their own entry points and stack states.
6. **Uninitialized objects:** the verifier tracks values created with `new` prior to calling the `<init>` constructor; it disallows using an uninitialized object as a normal object in ways that violate the rules.
7. **Accessibility and references:** class/interface, method/field references, and certain inheritance constraints must be valid; however, **runtime resolution and access checks** are separate parts of the linking/execution mechanism, so you should not attribute every `IllegalAccessError` or `NoSuchMethodError` to verification.

Verification checks the **abstract type** of values without needing to know actual arithmetic results or object contents at runtime. Whether an `int` has the value 42 or 100 is generally irrelevant to whether `ireturn` is type-valid.

## 3. Tracking the operand stack through bytecode

Consider the Java method:

```java
static int add(int a, int b) {
    return a + b;
}
```

In bytecode, the following sequence typically appears:

```text
0: iload_0
1: iload_1
2: iadd
3: ireturn
```

The verifier infers the type state:

| Instruction | Operand stack before | Operand stack after |
|---|---|---|
| `iload_0` | `[]` | `[int]` |
| `iload_1` | `[int]` | `[int, int]` |
| `iadd` | `[int, int]` | `[int]` |
| `ireturn` | `[int]` | Returns `int` from the method |

The input locals correspond to the two `int` parameters, with no `this` slot for a `static` method. `max_stack` and `max_locals` are metadata in the `Code` attribute describing resource limits for the method; the verifier also checks that actual usage is consistent with them.

If `ireturn` is replaced with `areturn`, the JVM cannot accept an `int` on the stack as a returned reference. This is a type-safety error, even though the instruction byte sequence still resides inside a validly formatted class file.

### When there are multiple branches

With `if`, `switch`, `goto`, or an exception handler, control flows can converge. The types of local variables and the operand stack at a merge point must be valid for **every branch that can reach it**. The JVM uses dataflow analysis rules based on type state.

In modern class files, the **`StackMapTable`** attribute provides *stack-map frames* describing the type-checking state at key offsets. For class file versions that apply this type-checking mechanism, the verifier uses those frames and state-transition rules to check consistency; it does not simply trust that the compiler always emits valid code. Not every method is required to contain a long list of frames: a simple linear method might not have explicit entries in `StackMapTable`.

Hypothetical **ill-typed** bytecode example (this is not a complete class file):

```text
method: public static int answer()
    bipush 42   // stack: [int]
    areturn     // invalid: areturn requires a reference and a matching result type
```

## 4. Java 17+ Hands-on: Corrupting Bytecode to Observe the Verifier

The example below creates a **valid** class with `javac`, reads the compiled `.class` file itself, and then attempts two modifications **only on an in-memory `byte[]` copy**:

- Changing a byte at the beginning of the class file to observe **`ClassFormatError`** (corrupted format).
- Changing the return opcode `ireturn` to `areturn` to observe **`VerifyError`** (structurally readable code that is not type-safe).

Creating a separate class loader allows calling `defineClass` with the same binary name in a different class namespace; the JVM identifies a class by **(binary name, defining class loader)**. The program does not overwrite the `.class` file on disk and does not depend on external bytecode libraries.

Create the file **`VerificationExample.java`**:

```java
import java.io.InputStream;
import java.util.Objects;

public final class VerificationExample {
    private static final class ByteArrayLoader extends ClassLoader {
        ByteArrayLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] data) {
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] original;
        try (InputStream in = VerificationExample.class
                .getResourceAsStream("/ExampleTarget.class")) {
            original = Objects.requireNonNull(
                    in, "ExampleTarget.class").readAllBytes();
        }

        byte[] modified = original.clone();
        int found = 0;
        for (int i = 0; i < modified.length - 2; i++) {
            if ((modified[i] & 0xff) == 0x10
                    && (modified[i + 1] & 0xff) == 0x2a
                    && (modified[i + 2] & 0xff) == 0xac) {
                modified[i + 2] = (byte) 0xb0;
                found++;
            }
        }
        if (found != 1) {
            throw new IllegalStateException(
                    "Expected exactly one opcode sequence, got " + found);
        }

        System.out.println("Original: " + ExampleTarget.answer());

        byte[] malformed = original.clone();
        malformed[0] = 0;
        try {
            new ByteArrayLoader(VerificationExample.class.getClassLoader())
                    .define("ExampleTarget", malformed);
            System.out.println("Unexpected acceptance");
        } catch (ClassFormatError expected) {
            System.out.println("Malformed header: ClassFormatError");
        }

        try {
            Class<?> changed =
                    new ByteArrayLoader(VerificationExample.class.getClassLoader())
                            .define("ExampleTarget", modified);
            changed.getMethod("answer").invoke(null);
            System.out.println("Unexpected acceptance");
        } catch (VerifyError expected) {
            System.out.println("Modified: VerifyError");
        }
    }
}

class ExampleTarget {
    public static int answer() {
        return 42;
    }
}
```

Compile with JDK 17+ (the `--release 17` flag targets the Java 17 class file version), then run from the directory containing the source file:

```bash
javac --release 17 -d out VerificationExample.java
java -cp out VerificationExample
```

With standard `javac` on JDK 17+ and HotSpot, the output is:

```text
Original: 42
Malformed header: ClassFormatError
Modified: VerifyError
```

**Exact explanation of the example:**

- `ExampleTarget.answer()` is a `static int` method returning 42. The `javac` compiler typically generates the instruction sequence `bipush 42` (`10 2a` in hex bytes) and `ireturn` (`ac`). The program searches for the exact sequence `10 2a ac` in the test class file copy; if it does not find **exactly one** occurrence, it intentionally aborts to avoid a misleading demonstration.
- `areturn` has opcode `b0`; after the replacement, the stack still holds the `int` produced by `bipush`. Consequently, the method fails to satisfy the return-type requirement. The JVM may detect the error when defining/linking the class or when a subsequent operation forces verification, but in both cases the `catch (VerifyError ...)` block captures the error to observe.
- `malformed[0] = 0` corrupts the `CA FE BA BE` magic number at the beginning of the class file, triggering a format error. Do not describe this error as “the verifier detecting a wrong return type”.
- A separate `ByteArrayLoader` is created for each `define` call. A class loaded by the system loader and a class defined by a child loader may share the same binary name, yet they are **two distinct classes** to the JVM.

This is **an intentional test tied to the specific bytecode generated by `javac`**, not a general-purpose class file editor: scanning the entire file for a byte sequence does not parse the `Code` attribute. With a different compiler, different bytecode, or different optimizations, the sequence might not appear or might not be unique; in that case, the test stops with `IllegalStateException`. For real-world bytecode manipulation, you should use a library that understands class file structure, such as ASM, and verify the result on the JVM.

### Viewing bytecode and metadata before modifying

After compiling, run:

```bash
javap -classpath out -c ExampleTarget
javap -classpath out -v ExampleTarget
```

`-c` displays instructions/offsets, such as the `answer` method body consisting of `bipush 42` followed by `ireturn`. `-v` lets you inspect the version, constant pool, `Code`, `stack`/`locals`, and other attributes (if present). The full `javap -v` output also includes compiler and environment information, so it should not be used as fixed expected stdout in tests.

## 5. `ClassFormatError`, `VerifyError`, and other linkage errors

**`VerifyError`** is a subclass of `LinkageError`; it indicates that the JVM has found an inconsistency in the class file regarding the applicable verification constraints. However, not every error that occurs when loading or linking a class is a `VerifyError`.

| Error | Typical meaning | Distinction |
|---|---|---|
| `ClassFormatError` | The class file is malformed or violates structural rules | May fail before type-flow analysis of instructions |
| `UnsupportedClassVersionError` | The class file uses a version not supported by the current JVM | A subtype of `ClassFormatError` |
| `VerifyError` | Bytecode/metadata fails type-checking or related validity constraints | For example, using a return opcode that mismatches the stack type |
| `NoClassDefFoundError` | Unable to find or complete the definition of a required dependent class in the context of use | Typically tied to loading/linkage, not automatically a verifier error |
| `NoSuchMethodError`, `NoSuchFieldError` | A symbolic reference cannot be resolved to the referenced member | Tied to resolution/compatibility; often caused by binary dependency changes |
| `IncompatibleClassChangeError` | An incompatible change in the binary relationship between classes/members | A linkage error; does not necessarily mean bytecode has invalid stack types |
| `ExceptionInInitializerError` | A static initializer threw an exception according to JVM rules | Belongs to initialization, after the required verification phase |

Fix quickly based on the root cause: for `ClassFormatError`, check the bytecode, tooling, and source files; for `VerifyError`, locate the bytecode or transformation producing an invalid stack/locals state; for resolution errors, inspect the JAR/classpath/modules and dependency versions. Never “fix” a `VerifyError` by catching it and attempting to continue using the rejected class.

## 6. Common Cases in Real-World Projects

### 6.1. Bytecode generated or modified by tools

Proxy, instrumentation, weaving, code generation libraries, or agents may generate bytecode at build time or runtime. A change in a method descriptor, branch control, stack map frames, or constructor ordering can cause the transformed code to be rejected even though the original Java source compiles.

A useful troubleshooting workflow:

1. Identify the binary name of the failing class and the **defining class loader** involved.
2. Save or capture the exact **post-transformation bytes** if the system allows it, not just the original `.class` file.
3. Run `javap -v -c` (or an equivalent class-file/ASM tool) on the corresponding class file to inspect descriptors, instructions, `Code`, and `StackMapTable`.
4. Check branch merge points, stack height, return types, method calls, and constructor constraints.
5. Reproduce under the same Java version and loader/agent setup, then fix the bytecode generation logic. Do not disable verification to mask the error.

### 6.2. Class file version too new

For example, running a class file targeting Java 21 on a Java 17 JVM can throw `UnsupportedClassVersionError`; this is a **class-file version** compatibility issue, not the verifier proving that `int` addition is wrong. Recompile with an appropriate `--release` flag or upgrade the runtime.

### 6.3. Issues appearing only after a library upgrade

A class may pass basic bytecode checks yet fail when method or dependency resolution occurs. For example, the class still references a method that was removed in a newer JAR version and throws `NoSuchMethodError`. This differs from code rejected due to local/stack types. Collect the full exception chain, loader identity, and dependency graph to classify the issue accurately.

### 6.4. Same class name, different loader

The JVM treats `(binary name, defining class loader)` as the identity of a runtime class. Two classes with the same name defined by two different loaders are **not** automatically interchangeable. A `ClassCastException` or `LinkageError` in that context does not mean the bytecode is invalid; you must also analyze class namespaces and loader constraints.

## 7. What does verification guarantee, and what does it not guarantee?

Verification is an essential runtime safeguard when the JVM accepts class files, especially external or transformed bytecode. It enforces the type-safety rules specified by the JVM model: a method cannot arbitrarily treat an integer as an object reference simply by emitting an ill-typed instruction.

However, verification **does not prove** that:

- The code satisfies business logic or returns the expected result.
- `NullPointerException`, `ClassCastException`, `ArrayIndexOutOfBoundsException`, `ArithmeticException`, or other valid runtime exceptions cannot occur. Those runtime checks remain necessary.
- There are no deadlocks, data races, concurrency bugs, resource leaks, or infinite loops.
- A user or process has permission to access data: authorization, sandboxing, and application security policies are separate concerns.
- Native code, JNI, `Unsafe`, or other privileged mechanisms are all governed solely by the verifier under the same assumptions as regular Java bytecode.

**Verification should not be understood as a comprehensive security sandbox.** It enforces a specific set of bytecode-level properties, whereas runtime exceptions, class loaders, access permissions, and application logic operate at other layers.

## 8. Check Your Understanding

1. **Why is `bipush 42; areturn` invalid?** Because `bipush` pushes an `int`, whereas `areturn` requires a reference operand, and the method is declared to return `int`.
2. **Is a file with a valid `CAFEBABE` magic number guaranteed to pass verification?** No. A valid header does not prove that the constant pool, code, stack maps, and dataflow are valid.
3. **Does `StackMapTable` replace all runtime checks?** No. It helps verify bytecode type states; value and condition checks at runtime still take place.
4. **Is `UnsupportedClassVersionError` a `VerifyError`?** No; it is a subclass of `ClassFormatError`.
5. **Does verification execute a class's `main` method to inspect the outcome?** No. It checks the class file and the type validity of the bytecode; it does not run business algorithms to predict results.
6. **Why can a proxy/agent cause a `VerifyError` even when the Java code compiles?** Because the transformed bytecode differs from the bytecode generated by `javac` and may contain inconsistent stack frames, descriptors, or instructions.

**Key takeaway:** In the class lifecycle, **verification belongs to linking and checks bytecode validity before the class is used in a way that requires linking to be completed**. Distinguish format error `ClassFormatError` from verification error `VerifyError` and resolution/initialization errors to find the right root cause, especially when working with class loaders, instrumented classes, and dynamically generated bytecode.
