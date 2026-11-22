# Distinguishing Compiler Checks from JVM Bytecode Verification

A Java file that **compiles successfully** does not necessarily mean every class will be accepted by the JVM, and successful **bytecode verification** by the JVM also does not guarantee that the program will not encounter exceptions or run according to business requirements. These two checking systems operate at **different times and on different forms of data**:

- **Compiler, for example `javac`:** analyzes **Java source code** according to language rules, checks types, names, access rights, control flow, and emits `.class` files.
- **JVM:** reads **classfile/bytecode** (which may come from `javac` or another bytecode generator/modifier), checks the classfile format, and verifies the static safety constraints of the bytecode during class loading/linking.
- **Runtime:** once the code has been loaded, linked, and executed, the JVM continues to perform dynamic checks such as casts, array element access, `null` checks, and resolution of symbolic references when needed. These errors are not identical to verifier errors.

For example, `javac` rejects a Java method declared to return `int` that writes `return "hello";`. If another tool **directly creates a classfile with an invalid stack type** without going through `javac`, the JVM verifier can reject the classfile with a `VerifyError`. Conversely, a completely valid classfile accepted by the verifier can still throw an `ArithmeticException` due to division by zero at runtime.

This lesson belongs to the topic **compilation output validation**: understanding the limits of each layer to test, diagnose, deploy, and handle bytecode accurately on Java 17+.

## 1. Three Questions at Three Stages

| Stage | Input data | Typical question | Typical result/error |
| --- | --- | --- | --- |
| Compile-time | `.java` and dependencies visible to the compiler | Is the source code valid according to language and static typing rules? | `javac` generates `.class` or reports a compile error |
| Class loading and linking | Bytecode in `.class`, metadata, and related classes | Is the classfile valid, and does the bytecode satisfy verifier constraints? | Class is loaded/linked, or `ClassFormatError`, `VerifyError`, etc. occur |
| Resolution and execution | Loaded/currently linking classes, actual runtime data | Do references match the current dependencies? Are values valid at runtime? | Success, `NoSuchMethodError`, `ClassCastException`, `NullPointerException`, incorrect business results, etc. |

**Note on timing:** The JVM specification describes *loading, linking (verification, preparation, resolution), initialization*, and execution. The JVM may **perform resolution lazily** or carry out some work when the class is used. Therefore, you should not assume that every JVM error appears immediately at the initial `java` command or as soon as `ClassLoader#defineClass` returns.

### Overall Diagram

~~~text
Java source code
      |
      | javac: parse, name/type checking,
      |        definite assignment, access rules...
      v
.class file
      |
      | JVM loading: locate/read classfile
      v
Read classfile format
      |
      | invalid structure, constant pool, magic...
      +---------------------> ClassFormatError (depending on error)
      |
      v
Linking / verification
      |
      | bytecode type rules, stack/local,
      | branches, frames, and virtual machine invariants
      +---------------------> VerifyError (depending on error)
      |
      v
Resolution / initialization / execution
      |
      +---------------------> Other LinkageErrors,
      |                        exceptions, or logic bugs
      v
Program behavior
~~~

The diagram is a **mental model**, not a guarantee that every JVM implements each operation as a strictly linear step as illustrated. What matters is distinguishing the **cause of each error**, rather than relying solely on when the exception is observed.

## 2. What Does `javac` Check?

For a Java source program, the compiler typically:

1. **Lexical and syntactic analysis:** tokens, brackets/parentheses, declarations, statement structure.
2. **Name and type resolution:** are variables, packages, methods, overloads, generic types, and conversions compatible?
3. **Access scope checking:** `private`, `protected`, package-private, `public`; with JPMS, also module readability and exports in the compile configuration.
4. **Control flow analysis:** cases where local variables are not assigned before reading (*definite assignment*), branches with no valid completion path, checked exceptions, etc.
5. **Applying other compile-time information:** constants, annotation processing if enabled and configured.
6. **Classfile generation:** writing metadata, constant pool, bytecode, exception table, frame/stack map information when needed, and appropriate attributes.

The compiler uses the information **available during that specific compilation**. Later, an application might run with a different dependency version, on a different runtime, or have its bytecode transformed by third-party tools. Thus, `javac` succeeding is proof that **the source code is valid in the compile environment**, not a certificate for every possible runtime environment.

### Example: A Type Error Caught Before Any Classfile Exists

File **`SourceTypeError.java`**:

~~~java
public class SourceTypeError {
    static int value() {
        return "hello";
    }
}
~~~

Compile:

~~~sh
javac -encoding UTF-8 SourceTypeError.java
~~~

`javac` fails because the return type is `int` while the expression `"hello"` has type `String`. The diagnostic message typically conveys:

~~~text
incompatible types: String cannot be converted to int
~~~

The full message, line, column, and formatting may vary by JDK. **There is no bytecode verifier test happening here**: the source has not passed language checks.

If `return "hello";` is changed to `return 42;`, the method is type-valid and can be compiled.

### Another Example: Definite Assignment Check

The following snippet is **intentionally invalid**, not a standalone runnable program:

~~~java
static int read(boolean condition) {
    int number;
    if (condition) {
        number = 10;
    }
    return number; // variable number might not have been initialized
}
~~~

The compiler must consider the execution path when `condition == false`; on that branch `number` has not been assigned. This is a **source/control-flow check by the compiler**, not a `VerifyError` after entering the JVM.

## 3. The JVM Does Not Necessarily Receive Classfiles from `javac`

A `.class` file may be produced by:

- `javac` from Java source;
- the compiler of another JVM language;
- a framework generating dynamic proxies or classes;
- a bytecode generator/transformer (instrumentation, weaving, code generation) modifying it;
- a corrupted, replaced, or incomplete artifact on disk.

Therefore, the JVM cannot simply assume "if a `.class` exists, the compiler must have checked everything." It must check the **format and constraints of the classfile itself** during loading/linking.

A classfile contains a structure such as:

~~~text
magic = 0xCAFEBABE
minor_version, major_version
constant_pool
access_flags, this_class, super_class
interfaces, fields, methods
attributes (where a method may have a Code attribute)
~~~

This is a **structural diagram**, not a valid binary file to copy directly. Inside the `Code` attribute are bytecode instructions, `max_stack`, `max_locals`, exception handlers, and potentially `StackMapTable`.

Two categories of checks are commonly distinguished:

- **Classfile format checking:** do the bytes represent a classfile with valid structure/version? Corrupted headers, constant pool, indices, or attributes can lead to `ClassFormatError` or related errors.
- **Bytecode verification:** does the read bytecode satisfy the static safety rules of the JVM? For instance, an object reference cannot be used as an `int` on the operand stack; control flow/local types must be consistent at merge points. Violations can lead to `VerifyError`.

Both `ClassFormatError` and `VerifyError` are types of `LinkageError`, but **they cannot be used interchangeably**. Invalid classfile structure does not mean the verifier analyzed and detected a bytecode type error.

## 4. The Verifier Cares About Operand Stack, Local Variables, and Control Flow

In JVM bytecode, many instructions do not carry explicit Java source type information like high-level statements do. The verifier tracks data types across the instruction stream.

Example meanings of a few instructions:

| Instruction | General meaning |
| --- | --- |
| `iconst_1` | Pushes an `int` value of 1 onto the operand stack |
| `aconst_null` | Pushes a `null` reference onto the operand stack |
| `iadd` | Pops two `int` values from the stack, adds them, and pushes an `int` |
| `ireturn` | Returns an `int` from a method with a matching return type |
| `areturn` | Returns a reference of a compatible type |
| `iload_0` | Reads an `int` value from local slot 0 |
| `aload_0` | Reads a reference from local slot 0 |

For example, a Java method:

~~~java
static int answer() {
    return 42;
}
~~~

is typically compiled into bytecode equivalent to:

~~~text
bipush 42
ireturn
~~~

Meanwhile, the instruction sequence below is **intentionally invalid** if the method has a descriptor returning `int`:

~~~text
aconst_null
ireturn
~~~

`aconst_null` pushes a **reference**, while `ireturn` requires an **int**. If a classfile has a method of type `()I` with this exact invalid instruction sequence, the verifier must reject it when verifying the method. This is a **bytecode type** issue, unlike Java source code which `javac` would have already blocked earlier.

The verifier also handles conditions such as:

- Not using the stack when there are insufficient operands (*stack underflow*).
- Merging operand/local types properly at points where multiple branches converge.
- Not accessing locals beyond `max_locals` or using a local with an invalid type.
- Complying with object/constructor initialization rules and reference types.
- Jumping only to valid instruction boundaries.
- Checking stack-map frames according to the rules applicable to the corresponding classfile version.

**StackMapTable** provides type state information at control-flow locations in many modern classfiles. The verifier uses this information according to the mechanism in the Java Virtual Machine Specification. You should not assume every classfile from every Java version has the same stack map structure; verification methods vary by version and case.

## 5. Running a Java 17+ Example: Valid Source, Verifier Accepts, Runtime Can Still Fail

File **`RuntimeBehaviorDemo.java`**:

~~~java
public class RuntimeBehaviorDemo {
    static int divide(int numerator, int denominator) {
        return numerator / denominator;
    }

    public static void main(String[] args) {
        System.out.println("Before division");

        try {
            System.out.println(divide(12, 0));
        } catch (ArithmeticException ex) {
            System.out.println("Runtime exception: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("After division");
    }
}
~~~

Compile and run on JDK 17+:

~~~sh
javac --release 17 -encoding UTF-8 RuntimeBehaviorDemo.java
java RuntimeBehaviorDemo
~~~

**Exact stdout:**

~~~text
Before division
Runtime exception: ArithmeticException
After division
~~~

The program is syntactically and type valid: the method returns `int` and performs properly typed integer division. The JVM can verify the class bytecode because the instructions are valid. However, when `denominator == 0`, integer division causes an `ArithmeticException` **at runtime**.

This is neither a compiler nor a verifier error. `javac` cannot prove every runtime value is non-zero in every program. The bytecode verifier also has no responsibility to check business logic or every runtime input.

### Observing Bytecode Generated by `javac`

After compiling the file above:

~~~sh
javap -c -p RuntimeBehaviorDemo
~~~

`javap -c` disassembles the instructions in the methods. You will see in `divide` the instructions to load integer parameters and `idiv`; in `main` there is the section creating/catching the exception. Filenames, jump labels, offsets, and print formatting depend on the classfile/compiler, so **do not copy a fixed output snippet as a correctness criterion**.

When you need to inspect more detailed classfile and frame information:

~~~sh
javap -v RuntimeBehaviorDemo
~~~

`javap` is a **classfile display/inspection tool**, not a command to "run the verifier and guarantee the entire program is safe." The fact that `javap` can read a file does not mean the JVM has successfully verified every method or that it will run properly.

## 6. Experiment 1: Malformed Class and `ClassFormatError`

We will pass a byte array that is **intentionally not a valid classfile** to `ClassLoader#defineClass(...)`. This is a **format** error experiment, not a bytecode type error.

File **`MalformedClassDemo.java`**:

~~~java
public class MalformedClassDemo {
    private static final class BytesLoader extends ClassLoader {
        Class<?> defineBadClass() {
            byte[] notAClassFile = {0, 0, 0, 0};
            return defineClass("Broken", notAClassFile,
                    0, notAClassFile.length);
        }
    }

    public static void main(String[] args) {
        try {
            new BytesLoader().defineBadClass();
            System.out.println("Unexpected success");
        } catch (ClassFormatError err) {
            System.out.println("Rejected: "
                    + err.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 -encoding UTF-8 MalformedClassDemo.java
java MalformedClassDemo
~~~

**Expected stdout on a standard JVM:**

~~~text
Rejected: ClassFormatError
~~~

The array has only four 0x00 bytes, carrying neither the magic number `0xCAFEBABE` nor a classfile structure. The JVM cannot load it as a valid Java classfile; `ClassFormatError` is the appropriate signal for a format error.

Do not conclude that "the JVM ran the method verifier and detected a type error" in this experiment: **there was never any valid method bytecode for the verifier to analyze**.

### Avoid Testing by Corrupting Real Classfiles

Do not randomly modify or delete bytes in production JARs/classfiles to "test the verifier." The resulting errors may be structural, checksum, classpath, or class loader errors — they do not accurately demonstrate bytecode type checking. Use dedicated test data, and do not overwrite active artifacts.

## 7. Experiment 2: Classfile with Basic Structure but Type-Invalid Code

To clearly distinguish `VerifyError` from `ClassFormatError`, we can **generate a minimal classfile in memory** with a method returning `int` whose instruction body uses `aconst_null; ireturn`. The purpose is solely for learning about the verifier. Do not use this kind of bytecode generation in production applications; use proper libraries/classfile tooling and rigorous testing if you actually need class transformation.

In the example, the simulated classfile uses **classfile major version 49 (Java 5)** solely because this older format allows demonstrating a minimal example without needing to add `StackMapTable`. **The program that generates it still compiles/runs with JDK 17+.** You should not infer that classfile version 49 is a recommended target for modern projects.

Standalone file **`VerifyErrorDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;

public class VerifyErrorDemo {
    private static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);          // CONSTANT_Utf8
        out.writeUTF(value);
    }

    private static byte[] invalidClass() throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);     // minor version
            out.writeShort(49);    // major version: Java 5

            out.writeShort(9);     // constant_pool_count
            utf8(out, "Broken");   // #1
            out.writeByte(7);      // #2 CONSTANT_Class
            out.writeShort(1);
            utf8(out, "java/lang/Object"); // #3
            out.writeByte(7);      // #4 CONSTANT_Class
            out.writeShort(3);
            utf8(out, "value");    // #5
            utf8(out, "()I");      // #6
            utf8(out, "Code");     // #7
            utf8(out, "SourceFile"); // #8 (unused by attributes)

            out.writeShort(0x0021); // public + ACC_SUPER
            out.writeShort(2);      // this_class = Broken
            out.writeShort(4);      // super_class = Object
            out.writeShort(0);      // interfaces_count
            out.writeShort(0);      // fields_count
            out.writeShort(1);      // methods_count

            out.writeShort(0x0009); // public static
            out.writeShort(5);      // name: value
            out.writeShort(6);      // descriptor: ()I
            out.writeShort(1);      // method attributes_count

            out.writeShort(7);      // attribute name: Code
            out.writeInt(14);       // Code attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(0);      // max_locals
            out.writeInt(2);        // code_length
            out.writeByte(0x01);    // aconst_null
            out.writeByte(0xAC);    // ireturn: expects int
            out.writeShort(0);      // exception_table_length
            out.writeShort(0);      // Code attributes_count
            out.writeShort(0);      // class attributes_count
        }

        return buffer.toByteArray();
    }

    private static final class BytesLoader extends ClassLoader {
        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            Class<?> broken = new BytesLoader().define(invalidClass());
            // Verifier may run during loading/linking or before use.
            broken.getDeclaredMethod("value").invoke(null);
            System.out.println("Unexpected success");
        } catch (VerifyError err) {
            System.out.println("Rejected: "
                    + err.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run **the bytecode-generating program**, not compiling class `Broken` from Java source:

~~~sh
javac --release 17 -encoding UTF-8 VerifyErrorDemo.java
java VerifyErrorDemo
~~~

**Expected stdout with a Java 17 JVM checking bytecode per specification:**

~~~text
Rejected: VerifyError
~~~

Explanation:

1. The byte array has magic/version/constant pool, metadata for class `Broken`, and one `public static int value()` method.
2. The `Code` attribute has two instructions. `aconst_null` pushes a reference onto the stack, whereas `ireturn` requires an int.
3. This is an **operand stack type state error**. `javac` never checked Java source for the `Broken` method, because this method was written directly in binary.
4. When the JVM performs verification under the applicable rules, the type on the stack is incompatible with `ireturn`, causing `VerifyError`.
5. The program only displays the **error class name** and does not hardcode detailed diagnostic content, because verifier messages and throw timing may differ across JVMs.

The minimal classfile generation example is intentional; it is **not a guide to writing a complete compiler or bytecode transformer**. If you need to generate classfiles in real code, a classfile-supporting library and testing with the target JVM is a more appropriate approach than writing magic bytes manually.

### Why Are the Two Examples Different?

- `MalformedClassDemo` passes in bytes without a classfile format: a **format** error.
- `VerifyErrorDemo` passes in a basic classfile structure, but the **method bytecode is invalid with respect to stack types**: a **verification** error.

A class can be rejected for one of many reasons, so you need to inspect the **specific error type and the entire cause** before concluding. Do not call every `LinkageError` a `VerifyError`.

## 8. When `javac` Succeeds but a Dependency Is Replaced at Runtime

Not every post-compilation error is caused by the verifier. A common case is **binary compatibility**: application code is compiled against an old API, but the JVM runs with a different version of the library.

Let us try the following three files/steps in a separate test directory; keep only one version of `Api.java` at a time.

**`Api.java` version 1:**

~~~java
public class Api {
    public static String value() {
        return "v1";
    }
}
~~~

**`Consumer.java`:**

~~~java
public class Consumer {
    public static void main(String[] args) {
        System.out.println(Api.value());
    }
}
~~~

Compile both and run:

~~~sh
javac --release 17 -encoding UTF-8 Api.java Consumer.java
java Consumer
~~~

Stdout:

~~~text
v1
~~~

Now replace **only `Api.java`** with version 2:

~~~java
public class Api {
    public static String renamed() {
        return "v2";
    }
}
~~~

Recompile only the library, **without** recompiling `Consumer.java`:

~~~sh
javac --release 17 -encoding UTF-8 Api.java
java Consumer
~~~

At runtime, `Consumer.class` still references the previously compiled symbol `Api.value:()Ljava/lang/String;`. However, the new `Api.class` no longer has that `value()` method, so the JVM can throw:

~~~text
java.lang.NoSuchMethodError: 'java.lang.String Api.value()'
~~~

The full message/stack trace may vary by JDK version; the key error type is **`NoSuchMethodError`**, a **linking/resolution** error regarding a method symbol. This error **does not mean `Consumer`'s bytecode has invalid operand stack types**; the bytecode was validly compiled, but the binary contract of the runtime dependency changed.

If `Consumer.java` is recompiled after removing `Api.value()`, the compiler will catch the error at **compile-time** before execution. This example shows that the same missing-method issue can be detected at different stages depending on the artifacts being used.

### Related Errors to Distinguish

| Error/symptom | Common meaning |
| --- | --- |
| `VerifyError` | Bytecode violates verifier constraints |
| `ClassFormatError` | The class file has an invalid format/structure |
| `UnsupportedClassVersionError` | The classfile has a version not supported by the current JVM |
| `NoSuchMethodError` | The referenced method symbol does not exist in the resolved runtime class |
| `NoSuchFieldError` | The referenced field symbol does not exist in the runtime class |
| `IllegalAccessError` | Disallowed access at the linking/runtime level |
| `NoClassDefFoundError` | A required class is unavailable/cannot be loaded or had a prior initialization issue |
| `ClassCastException` | A dynamic type cast fails during execution |
| `NullPointerException` | Code performs an invalid operation on a null reference during execution |
| `ArithmeticException` | An invalid arithmetic operation at runtime, e.g., integer division by zero |

The errors listed above can have deeper root causes, such as an incorrect classpath, incorrect module path, duplicate dependency versions, corrupted files, or buggy code generators. Always read the error name, stack trace location, and the actual source of the loaded classfile.

## 9. Does `javac` Automatically Guarantee Its Output Passes the Verifier?

A compliant Java compiler is expected to produce classfiles compatible with the JVM when the source code is valid and the configuration is supported. Under normal circumstances, standard `javac` output **should be accepted by the target JVM at the format and verification levels**.

However, concluding "`javac` succeeded = guaranteed to run" is too strong because:

- The compiler may compile with a **JDK version** different from the target JVM.
- The classfile may be **transformed after compilation** by instrumentation or packaging tools.
- The compile classpath may differ from the runtime classpath; binary APIs may have changed.
- Load/link errors for another class only occur when that class is actually needed.
- Runtime exceptions and logic bugs can still occur even when bytecode is valid.
- A bug in the compiler, transformer, or runtime is also a real possibility, though not the default assumption.

**You do not need to suspect `VerifyError` just because `javac` succeeded.** If running an ordinary Java program hits an error, read the actual exception. A `NoSuchMethodError` or `ClassNotFoundException` should point you toward dependencies/linking; a `VerifyError` specifically suggests corrupted bytecode or an abnormal transformer/generator.

### Role of `StackMapTable`

For bytecode generated for modern Java versions, the compiler typically provides appropriate stack-map frame information to assist verification. If a transformer alters control flow or stack types without **updating the necessary frames**, the JVM may reject the classfile with a `VerifyError`.

This explains why **editing bytecode via simple byte-replacement operations** can corrupt a classfile even when the original Java statements are completely valid. Modifying bytecode requires considering the constant pool, offsets, exception table, stack map, classfile version, and related attributes.

You should not try to "fix" verifier errors by arbitrarily stripping `StackMapTable` or forcing the classfile back to an older version: such steps can cause other errors or lose support for language/classfile features.

## 10. Multi-Layer Output Validation

A quality validation pipeline can separate four layers:

**Layer A — Compile:** use `javac`/Compiler API, check exit status, diagnostics, type warnings, and completeness of source units/dependencies. A warning-free codebase does not by itself prove the logic is correct.

**Layer B — Inspect artifact:** use `jar --list`, `javap -v`, check the manifest, classfile version, package/module names, and distribution structure. This is a static check that assists diagnostics, **not a replacement for JVM verification**.

**Layer C — Load/link on target runtime:** run smoke tests with the exact JDK, classpath, module path, and dependencies to be deployed; detect classfile version, binary compatibility, missing classes, or verifier problems. The JVM may link/resolve some references lazily, so a single launch does not cover every execution path.

**Layer D — Execute and test logic:** run unit/integration tests, multiple inputs, branches, and exceptions. A successful verifier pass only indicates that the bytecode satisfies bytecode constraints, **not that the business outcome is correct**.

Example checklist:

~~~text
[ ] javac/build succeeds with warnings reviewed
[ ] Artifact contains the right classes/resources/modules
[ ] Classfile version matches the deployment runtime
[ ] No unintended dependency replacements remain
[ ] Application loads/links key entrypoints
[ ] Smoke tests run on the target JVM, not only the dev JVM
[ ] Unit/integration tests verify behavior and exceptions
[ ] If bytecode instrumentation is used: test the verifier on the target JVM
~~~

### `javap` Is Not a Compiler

The command:

~~~sh
javap -c -v RuntimeBehaviorDemo
~~~

only **analyzes/prints metadata and instructions of an existing classfile**. It is useful for inspecting descriptors, bytecode, stack/locals, version, constant pool, and frame attributes. However, clean output does not prove every runtime path is safe or that the program will not encounter exceptions. If you need to confirm that the JVM actually loads/verifies the class, you must **test it on the JVM**.

## 11. Error Detection Timing Can Be Late

The JVM may not need to resolve every symbolic reference immediately, and can load classes on demand. Therefore:

- Being able to run `main` **does not prove** that every rarely used class/method has been loaded/linked.
- A `NoSuchMethodError` may only surface when executing the exact call to the method involved.
- A classfile with a verifier error may be rejected when the loader/linker processes it, but **you should not assert a fixed point in time** between `defineClass`, `getDeclaredMethod`, and the first invocation.
- Packaging classfiles into a JAR **is not** an actual verification pass of all bytecode in the archive.

When testing binary compatibility, you need to run the entrypoints/feature paths that use the dependency, not just invoke `java -version` or start the application and shut it down immediately.

### Be Careful with Wrapped Exceptions

Reflection can wrap an exception occurring **inside the invoked method** into an `InvocationTargetException`; frameworks and class loaders can also wrap the cause in their own exceptions. When investigating, inspect the **cause chain**. Specifically, `VerifyError` is a `LinkageError`, not a normal business exception; broadly catching `Throwable` to hide verifier errors is dangerous.

In production application code, rather than swallowing `LinkageError` and continuing with half-initialized state, you should usually report a deployment/artifact error and halt the affected flow.

## 12. Compiler Warnings, Generics, and Runtime Checks

Another example helps understand compiler limits:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    public static void main(String[] args) {
        List raw = new ArrayList<String>();
        raw.add(123);

        @SuppressWarnings("unchecked")
        List<String> strings = raw;

        try {
            String first = strings.get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("Runtime: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked ErasureDemo.java
java ErasureDemo
~~~

**Stdout:**

~~~text
Runtime: ClassCastException
~~~

The compiler can warn about raw types and unchecked operations. `@SuppressWarnings("unchecked")` on the variable only suppresses part of the warnings; it **does not guarantee the list elements are `String`**. Generic type arguments are erased at runtime; the compiler may insert `checkcast String` when retrieving an element, and encountering an `Integer` throws `ClassCastException`.

The verifier checks that the `checkcast` instruction is valid, rather than **proving in advance which values will be cast successfully**. Do not confuse `ClassCastException` with `VerifyError`.

In real code, a better approach is to avoid raw types, use `List<String>`, and validate data at integration boundaries. The example above intentionally uses a raw type to illustrate the risk, **not as a recommended design pattern**.

## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`javac` checks the bytecode of all runtime libraries." | The compiler checks source/dependency information in the compile environment; the JVM checks loaded classfiles in the runtime environment. |
| "Any `.class` file has passed through `javac`." | Bytecode can be generated/modified by many other tools. |
| "`ClassFormatError` is the same as `VerifyError`." | One is a classfile structure error, and the other is a bytecode verification constraint error. |
| "The verifier accepting a class means the algorithm is correct." | The verifier does not check business requirements or all runtime input values. |
| "`ClassCastException` is a verifier error." | Most cases are dynamic type-check errors at runtime. |
| "`NoSuchMethodError` means invalid bytecode types." | Usually caused by a symbolic reference not matching the runtime dependency. |
| "No error at startup means all classes are verified." | Loading/linking/resolution can be deferred, and rarely used code may not have been triggered yet. |
| "`javap -v` succeeding means the JVM can run it." | `javap` only inspects; you need to test on the real JVM and runtime dependencies. |
| "Annotations/bytecode transforms do not affect the verifier." | Incorrectly transforming instructions/frames/metadata can produce a `VerifyError`. |
| "`@SuppressWarnings` can fix `VerifyError`." | This annotation affects supported compiler warnings and does not repair broken bytecode at runtime. |
| "Every `LinkageError` can be retried like a network error." | Many linkage errors reflect invalid artifacts/dependencies and require fixing the deployment. |

## 14. Signal-Based Diagnostic Workflow

When a Java program fails to work, follow this sequence:

1. **Did the error occur in `javac` or in `java`?** If it is a compile error, fix the source, dependencies, and compiler options; do not look for verifier logs.
2. **If `java` fails, read the specific error class.** `ClassFormatError`, `VerifyError`, `NoSuchMethodError`, `UnsupportedClassVersionError`, and `ClassCastException` point in different directions.
3. **Inspect the actual artifact being loaded.** Are there duplicate JAR/class versions? Is there a transformer or bytecode generation? Was the classfile packaged properly?
4. **Compare compile/runtime dependencies.** The same class name with changed methods/fields/signatures can cause resolution/linking errors.
5. **Check the classfile version and JVM version.** Use `javap -verbose` or build metadata; run a smoke test on the target runtime.
6. **If you suspect the verifier, inspect instructions/frames.** Use `javap -v -c` or a suitable classfile tool, examine stack/local/StackMapTable flow and recently applied transformations.
7. **If the class runs but the logic is wrong, test with data.** The verifier does not replace application tests.
8. **Do not modify production artifacts directly.** Reproduce with a test copy, preserve diagnostics, and keep a repeatable build process.

## 15. Practical Exercises

**Exercise 1 — Compiler error.** Compile `SourceTypeError.java`. Identify why the compiler rejects `return "hello";` when the method returns `int` and why there is no `VerifyError` here.

**Exercise 2 — Valid bytecode, runtime error.** Run `RuntimeBehaviorDemo.java`. Explain why integer division by zero compiles and passes bytecode verification, yet throws `ArithmeticException` at runtime.

**Exercise 3 — Inspect bytecode.** Use `javap -c -p RuntimeBehaviorDemo` and find `idiv`. Does it check for a zero divisor at compile-time or perform the division at runtime?

**Exercise 4 — Classfile format.** Run `MalformedClassDemo.java`. Determine whether the input data is actually a valid classfile, and why the error type is `ClassFormatError`.

**Exercise 5 — Verification.** Run `VerifyErrorDemo.java` on a Java 17 JVM. Explain the operand type pushed by `aconst_null` and the type required by `ireturn`, and state why the verifier rejects it.

**Exercise 6 — Binary compatibility.** Compile `Consumer` against `Api.value()`, then replace `Api.class` with a version lacking the method without recompiling `Consumer`. Why is the observed error `NoSuchMethodError` instead of a compile error?

**Exercise 7 — Generics.** Run `ErasureDemo.java`. Distinguish between the raw type warning, `@SuppressWarnings`, runtime `checkcast`, and `ClassCastException`.

**Exercise 8 — Deployment.** Plan the validation of a library with bytecode instrumentation: compiler output check, classfile inspection, target JVM smoke test, regression tests, and artifact/dependency version verification.

### Self-Check Questions

1. **What form of data does `javac` check?** — Java source code and the type/dependency information needed for compilation.
2. **What form of data does the JVM verifier check?** — Loaded classfiles/bytecode to ensure valid bytecode constraints.
3. **How does `ClassFormatError` differ from `VerifyError`?** — One reports invalid classfile structure/format; the other reports bytecode failing verification.
4. **Does a classfile created by a tool other than `javac` need the verifier?** — Yes, it must be accepted by the JVM according to class loading/linking rules.
5. **Does `VerifyError` prove a business bug?** — It reflects invalid bytecode, not a check of business requirements.
6. **Can a method containing `idiv` pass the verifier yet divide by 0?** — Yes; dividing by 0 causes `ArithmeticException` at runtime.
7. **What does `NoSuchMethodError` usually suggest?** — A dependency/runtime API mismatch against the compiled reference or a similar resolution issue.
8. **Does `javap` guarantee that all bytecode will run properly?** — No; it helps inspect classfiles.
9. **Why can "launching without errors" not be treated as checking every class?** — Classes/references may be loaded or resolved lazily.
10. **After the compiler + verifier, what needs to be tested?** — Runtime linking, compatibility, exceptions, and logical behavior with real inputs.

**Summary:** `javac` confirms that **Java source code is valid in the compile environment**, whereas the JVM checks the **actual classfile/bytecode** to enforce virtual machine constraints. Even after passing both, code can still encounter binary compatibility or runtime logic errors. Therefore, validating Java output requires combining **compile diagnostics, artifact inspection, JVM loading/linking, and behavioral testing** on the exact deployment environment.