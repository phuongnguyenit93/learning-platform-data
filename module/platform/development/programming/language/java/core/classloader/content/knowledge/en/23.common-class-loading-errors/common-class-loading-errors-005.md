# ClassFormatError, VerifyError, and ClassCircularityError in Java ClassLoader

## 1. All three errors relate to JVM loading/linking, but are not synonymous

When the JVM loads a Java class, the task does not stop at finding the `.class` file. The JVM must also read the class file structure, check the version, determine superclass/superinterface relationships, verify the bytecode, and link references. The following three errors are often mistakenly grouped together as “class cannot be loaded”:

- **`ClassFormatError`:** the class file data **does not have a valid format** or cannot be interpreted by the JVM as a valid class file.
- **`VerifyError`:** the JVM detects that the class file **fails the bytecode verification step**: type safety, operand stack, local variables, or control flow rules are not satisfied.
- **`ClassCircularityError`:** the JVM detects a **cycle in the superclass or superinterface inheritance relationship** while loading/defining a class or interface.

These are **three types of `Error` under the `LinkageError` branch**, not `ClassNotFoundException`. If you encounter them, the fix is usually to **fix the class file, compiler/transformer version, or inheritance graph**, rather than just adding a JAR to the classpath.

### Learning Objectives

After this lesson, you can:
1. Distinguish between class file structure errors, verifier errors, and circular inheritance errors.
2. Understand that errors can occur at different points in loading/linking, not just immediately at the `loadClass` call.
3. Reproduce **all three errors** using Java 17+ without external libraries.
4. Distinguish `ClassCircularityError` from **static initialization cycles**, **object reference cycles**, and **deadlocks between class loaders**.
5. Debug errors properly across the runtime JDK, deployed bytes, ClassLoader, bytecode transformation, and dependency graph.

## 2. Exception inheritance tree: position of each error

```text
java.lang.Throwable
├── java.lang.Exception
│   └── ClassNotFoundException              [checked]
└── java.lang.Error
    └── LinkageError
        ├── ClassFormatError
        │   └── UnsupportedClassVersionError
        ├── VerifyError
        ├── ClassCircularityError
        ├── NoClassDefFoundError
        ├── IncompatibleClassChangeError
        │   ├── NoSuchMethodError
        │   ├── NoSuchFieldError
        │   └── IllegalAccessError
        └── ExceptionInInitializerError
```

The branches in the diagram only list the types relevant to the lesson; these are **not all** subclasses of `LinkageError`.

Key points:
- `ClassFormatError`, `VerifyError`, and `ClassCircularityError` are **three independent branches directly under `LinkageError`**.
- `UnsupportedClassVersionError` is a **subclass of `ClassFormatError`**, used when the major/minor class-file version is not supported by the runtime.
- `ClassNotFoundException` is a **checked exception** in the `Exception` branch: it indicates a failure to find a class according to the ClassLoader API.
- `NoClassDefFoundError` typically appears when the JVM needs an unavailable definition or a class that failed initialization; it is **not an alternative name** for the three errors being discussed.
- Normally, these `Error`s **should not be caught and swallowed** in business code; they can be categorized at a plugin/container boundary to report an artifact error and refuse to activate the plugin.

## 3. At which phase do the errors occur?

At a high level:

```text
Load request: loadClass("plugin.Greeter")
                  │
                  ▼
      ClassLoader searches for bytecode
                  │
                  ├─ not found ──► ClassNotFoundException
                  │
                  ▼
           defineClass(bytes)
                  │
                  ├─ corrupted class file structure
                  │      └──► ClassFormatError
                  │
                  ├─ unsupported major/minor version
                  │      └──► UnsupportedClassVersionError
                  │
                  ├─ superclass/superinterface cycle
                  │      └──► ClassCircularityError
                  │
                  └─ class defined
                         │
                         ▼
                Linking / verification
                         │
                         ├─ bytecode violates verifier
                         │      └──► VerifyError
                         │
                         └─ class is used
                                 │
                                 ▼
                       initialization when needed
```

This is a **mental model**, not a fixed chronological order that every JVM must execute in full before each instruction. The JVMS allows many linking activities—especially resolution—to occur **lazily** within the bounds of the specification.

Having `ClassLoader.loadClass(name)` return a `Class<?>` does not guarantee that:
- all method bytecode has been used;
- all symbolic references have been resolved;
- the static initializer has run;
- all dependencies will load successfully later.

In the Java experiment in section 8, `VerifyError` is reliably triggered by **using reflection to call the method containing the invalid bytecode**, rather than assuming that merely calling `loadClass` forces verification of everything.

## 4. ClassFormatError: structurally invalid class file

### 4.1. A class file is a structured binary format

According to the JVM Specification, the beginning of a class file has the layout:

```text
u4 magic                 // 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
cp_info constant_pool[constant_pool_count - 1]
u2 access_flags
u2 this_class
u2 super_class
...
```

A class file also contains interfaces, fields, methods, and attributes tables; constant-pool entries reference one another using rule-defined indices. A file carrying the `.class` extension that is actually an HTML response, ZIP/JAR, text, an incomplete download, or bytes from a faulty transformer does not become a valid class because of its filename.

**Examples of common causes:**

1. The magic number is not `CAFEBABE`.
2. The file is missing bytes, truncated, read at the wrong offset, or still contains data in another compressed format.
3. Invalid constant pool tag/count/index.
4. Tables/attributes have incorrect length or structure.
5. Descriptor names, field/method attributes, or class-file constraints are not satisfied.
6. A bytecode generator/shader/obfuscator/agent corrupts part of the class file.
7. The loader reads the wrong resource due to an incorrect mapping from binary name to file path.

`ClassFormatError` indicates **a problem with the data**, not that the `ClassLoader` necessarily failed to find the data.

### 4.2. ClassFormatError and UnsupportedClassVersionError

`UnsupportedClassVersionError` is a subclass of `ClassFormatError`, thrown when the version in the class file is not supported by the JVM. Common milestones:

| Java source/runtime release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

An application running on Java 17 that reads class bytes built for Java 21 (major 65) may encounter `UnsupportedClassVersionError`. It should not be diagnosed as a “missing JAR” error.

**How to handle it:** compare `java -version` with `javac -version`, check the exact class file being deployed, compile with `javac --release 17` when the code and dependencies allow, or upgrade the runtime.

`minor_version` also matters, especially for class files tied to **preview features**. Do not change a few version bytes in the file to be “compatible” with an older runtime: opcodes, the constant pool, APIs, and semantics may differ.

### 4.3. A counterintuitive example

A custom loader:

```java
// Snippet inside findClass(String name):
byte[] bytes = Files.readAllBytes(classFile);
return defineClass(name, bytes, 0, bytes.length);
```

If the path exists and `bytes.length > 0`, that only proves bytes were read. It **does not prove** that the data is valid, belongs to the right binary name, has the right version, or passes the verifier.

Checking the `CAFEBABE` magic is a good precheck, but it **does not replace** JVM verification/format validation.

## 5. VerifyError: the class file is parseable, but the bytecode is invalid

### 5.1. What does the verifier check?

The bytecode verifier validates the safety conditions of the code inside methods, concerning:

- The types of values on the **operand stack** are compatible with the opcode being used.
- The stack depth is non-negative and does not exceed valid limits.
- Values in **local variables** are used with the correct type/state.
- `if`, `goto` branches, and exception handlers have matching stack/local variable states at merge points.
- `StackMapTable` rules for the applicable class-file versions are satisfied.
- Constructors and `uninitializedThis`/`uninitialized` values are not misused.
- The return value has the correct type for the method descriptor; for example, a `()I` method must return `int`.
- Other verification conditions according to the JVMS.

### 5.2. Example of bytecode with an invalid return type

Valid Java source:

```java
public class VerifyTarget {
    public static int value() {
        return 1;
    }
}
```

The compiler can generate bytecode for the `value` method:

```text
iconst_1  // push int 1 onto the stack
ireturn   // return int from the operand stack
```

If a transformer deliberately changes the `iconst_1` opcode to `aconst_null` while keeping `ireturn`, the stack holds a **null reference** whereas `ireturn` expects an **int**:

```text
aconst_null  // reference
ireturn      // requires int
             // → verifier detects a type conflict
```

`VerifyError` is the exact error here: the class file structure may still be parseable, but **the method instructions violate typing constraints**.

This is **not a normal Java source compiler error**. `javac` checks type safety itself and generates valid bytecode. VerifyError cases in production usually suggest:
- the class file was modified after compilation;
- bytecode instrumentation failed to update stack map frames;
- a code generation/obfuscation tool broke control flow;
- a version mismatch between an agent/framework and the class-file version being processed.

### 5.3. Do not “fix” it by disabling the verifier

Using legacy options to disable verification or fix invalid bytecode by skipping checks is not recommended. Some flags have been removed or are no longer supported in newer JDKs. Turning off the verifier can cause crashes or unsafe behavior; the bytes/transformer must be fixed.

## 6. ClassCircularityError: circular inheritance relationship

`ClassCircularityError` is thrown by the JVM when it **detects a cycle in the superclass/superinterface hierarchy** while loading/deriving a class or interface.

An invalid example at the graph level:

```text
class A extends B
class B extends A

A ──superclass──▶ B
▲                 │
└────superclass───┘

→ ClassCircularityError
```

Or a cyclic interface graph:

```text
interface X extends Y
interface Y extends X

X ──superinterface──▶ Y
▲                    │
└────superinterface──┘
```

**Normal Java source compilers reject inheritance cycles**. Therefore, this error is usually related to:
- bytecode that was modified or dynamically generated, bypassing normal Java source checks;
- a transformer incorrectly manipulating `super_class` or `interfaces` in the class file;
- class-loader setup and class definitions coordinating improperly when loading the graph;
- a corrupted artifact or a generator producing an invalid type hierarchy relationship.

### 6.1. Which entry in the class file determines the superclass?

After the constant pool and `access_flags`, a class file contains:

```text
u2 this_class      // index of the class being defined
u2 super_class     // index of the superclass (0 only in special cases)
```

`this_class` and `super_class` reference `CONSTANT_Class_info` entries. If you modify `CycleTarget`'s `super_class` to reference **`this_class` itself**, the class file describes a class that **extends itself**. The JVM detects that cycle when creating the class and throws `ClassCircularityError`.

### 6.2. Do not confuse this with a regular circular dependency

The following situations **do not automatically cause `ClassCircularityError`**:

- Class A holds a field of type B, and B holds a field of type A.
- Two objects reference each other.
- Method A calls method B, and B calls A back.
- Static initializer A reads a static field of B, and B reads A back.
- Two class loaders cross-delegate and threads deadlock.
- Two classes with the same name are defined by two different loaders.

The error requires a **cycle in the superclass/superinterface relationship during the loading/defining process**. Having two classes depend on each other for fields, methods, or data **is not an inheritance relationship**.

## 7. Summary of the three errors: signs and troubleshooting

| Error | JVM detects | Example causes | First checks |
|---|---|---|---|
| `ClassFormatError` | Class file has invalid format/structural constraints | Wrong magic, invalid constant pool, truncation | Header, actual bytes, transformer |
| `VerifyError` | Method bytecode fails verification | `ireturn` when stack holds a reference; invalid frames | `javap -v -c`, StackMapTable, instrumentation |
| `ClassCircularityError` | Superclass/superinterface hierarchy cycle | A extends B extends A, self-superclass | `super_class`, interfaces, type graph |
| `UnsupportedClassVersionError` | Major/minor version not supported by the JVM | Runtime JDK older than target | `java -version`, `javap -verbose` |
| `ClassNotFoundException` | Loader cannot find the requested class | Wrong name, URL/path missing JAR | ClassLoader hierarchy, classpath |
| `NoClassDefFoundError` | JVM needs an unavailable class definition or class init previously failed | Missing dependency, wrong name, erroneous class | Cause chain, loader, init log |

There can be **multiple cascading errors**: a corrupted class file prevents one class from loading; later, a class depending on it may report a different `LinkageError`. Always look for the **first error and the actual artifact**, rather than just reading the message at the end of the log.

## 8. Java 17+ experiment to reproduce all three errors accurately

This experiment intentionally modifies bytes **in memory**; it does **not** overwrite any real `.class` files in the project and does **not require ASM/Byte Buddy**. We compile two completely valid classes:

1. `VerifyTarget` has a method returning `int 1`.
2. `CycleTarget` extends `Object`.

Then a host loader uses the modified bytes:
- random bytes → `ClassFormatError`;
- `iconst_1` opcode changed to `aconst_null` → `VerifyError`;
- `super_class` changed to `this_class` → `ClassCircularityError`.

The demo uses a **different ClassLoader for each case**, avoiding `findLoadedClass` state from a previous attempt. The program runs on **Java 17+**; the results below were verified when compiling with `javac --release 17` and running on OpenJDK 21.

### 8.1. The VerifyTarget.java file

```java
public class VerifyTarget {
    public static int value() {
        return 1;
    }
}
```

### 8.2. The CycleTarget.java file

```java
public class CycleTarget {
}
```

Both are classes in the **default package** solely to keep the demo minimal. In real systems, use an explicit package for plugins and avoid the default package.

### 8.3. The ErrorKindsDemo.java file

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class ErrorKindsDemo {

    static final class BytesLoader extends ClassLoader {
        private final String target;
        private final byte[] bytes;

        BytesLoader(String target, byte[] bytes) {
            super(ErrorKindsDemo.class.getClassLoader());
            this.target = target;
            this.bytes = bytes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(target)) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static int u2(byte[] bytes, int offset) {
        return ((bytes[offset] & 0xff) << 8)
                | (bytes[offset + 1] & 0xff);
    }

    static byte[] badFormat() {
        // Not a valid CAFEBABE magic / class file.
        return new byte[] {0, 1, 2, 3, 4, 5};
    }

    static byte[] badVerify(byte[] input) {
        byte[] bytes = input.clone();
        int match = -1;

        // For the "return 1;" method with javac --release 17,
        // iconst_1; ireturn is encoded as 04 ac.
        for (int i = 0; i + 1 < bytes.length; i++) {
            if ((bytes[i] & 0xff) == 0x04
                    && (bytes[i + 1] & 0xff) == 0xac) {
                if (match != -1) {
                    throw new IllegalStateException(
                            "Not unique sequence");
                }
                match = i;
            }
        }

        if (match == -1) {
            throw new IllegalStateException(
                    "Bytecode sequence missing");
        }

        // iconst_1 (int) -> aconst_null (reference),
        // but the following ireturn still requires int.
        bytes[match] = 0x01;
        return bytes;
    }

    static byte[] badCycle(byte[] input) {
        byte[] bytes = input.clone();
        int pos = 8; // After magic, minor_version, major_version.
        int cpCount = u2(bytes, pos);
        pos += 2;

        // Walk the constant pool to reach access_flags/this/super.
        for (int i = 1; i < cpCount; i++) {
            int tag = bytes[pos++] & 0xff;
            switch (tag) {
                case 1 -> {
                    int length = u2(bytes, pos);
                    pos += 2 + length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                        pos += 4;
                case 5, 6 -> {
                    pos += 8;
                    i++; // long/double occupy two CP slots.
                }
                case 7, 8, 16, 19, 20 -> pos += 2;
                case 15 -> pos += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant tag: " + tag);
            }
        }

        pos += 2; // access_flags
        int selfIndex = u2(bytes, pos); // this_class
        pos += 2; // super_class offset

        // Change superclass to be this class itself.
        bytes[pos] = (byte) (selfIndex >>> 8);
        bytes[pos + 1] = (byte) selfIndex;

        return bytes;
    }

    static void inspect(String title, String className, byte[] bytes)
            throws Exception {
        try {
            Class<?> type = Class.forName(
                    className,
                    true,
                    new BytesLoader(className, bytes)
            );

            // Force the VerifyTarget case to use the method:
            // the JVM may defer verification until needed.
            if ("VerifyTarget".equals(className)) {
                type.getMethod("value").invoke(null);
            }
            System.out.println(title + " -> unexpectedly loaded");

        } catch (LinkageError error) {
            System.out.println(
                    title + " -> "
                    + error.getClass().getSimpleName()
            );

        } catch (ClassNotFoundException error) {
            System.out.println(
                    title + " -> ClassNotFoundException"
            );
        }
    }

    public static void main(String[] args) throws Exception {
        inspect(
                "bad format",
                "BrokenFormat",
                badFormat()
        );

        inspect(
                "bad verifier",
                "VerifyTarget",
                badVerify(Files.readAllBytes(
                        Path.of("inputs/VerifyTarget.class")))
        );

        inspect(
                "circular superclass",
                "CycleTarget",
                badCycle(Files.readAllBytes(
                        Path.of("inputs/CycleTarget.class")))
        );
    }
}
```

### 8.4. Create directories, compile, and run

Place the three source files in a working directory:

```text
classloader-errors/
├── VerifyTarget.java
├── CycleTarget.java
├── ErrorKindsDemo.java
├── inputs/
└── host/
```

On Bash/Linux/macOS:

```bash
mkdir -p inputs host
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force inputs,host | Out-Null
```

Compile with JDK 17+ while targeting Java 17 class files:

```bash
javac --release 17 -d inputs VerifyTarget.java CycleTarget.java
javac --release 17 -d host ErrorKindsDemo.java
java -cp host ErrorKindsDemo
```

**Do not add the `inputs` directory to the host's `-cp`.** If you do, the parent application loader may define `VerifyTarget` or `CycleTarget` before `BytesLoader.findClass` is called, causing the demo not to use the modified bytes.

### 8.5. Verified stdout

```text
bad format -> ClassFormatError
bad verifier -> VerifyError
circular superclass -> ClassCircularityError
```

The program prints only the **simple class name** of the error to avoid depending on detailed messages that vary across JDKs/runtimes.

### 8.6. Why does each branch throw its error?

**The bad format branch:**
- `badFormat()` creates a 6-byte array without the `CAFEBABE` magic and without a class file structure.
- `BytesLoader.findClass("BrokenFormat")` calls `defineClass`.
- The JVM rejects the bytes, so `ClassFormatError` is thrown.

**The bad verifier branch:**
- The original `VerifyTarget.class` file is validly generated by `javac --release 17`.
- `badVerify` locates the exact `04 ac` opcode sequence for `iconst_1; ireturn` in the demo target and changes `04` to `01` (`aconst_null`).
- The file still has a header, constant pool, and method structure, but the instruction sequence returns a reference where an int is required.
- `Class.forName(..., true, ...)` and reflective invocation force the JVM to verify/use the method; the verifier detects that it is invalid and throws `VerifyError`.

**The circular superclass branch:**
- `badCycle` reads enough of the class-file constant pool to find the offsets of `this_class` and `super_class`.
- The program changes `super_class` to the same index as `this_class`.
- This produces a class-file graph where superclass points to the class itself, creating a circularity.
- The JVM detects the error when creating the class and throws `ClassCircularityError`.

### 8.7. Limitations of the demo

- `badVerify` intentionally relies on the `04 ac` pattern of **the class compiled from the source above with `--release 17`**. If you change the method, run an obfuscator, or use a compiler that emits different bytecode, the program deliberately throws `IllegalStateException` instead of silently modifying the wrong bytes. For a production transformer, you must parse Code attributes according to the spec using an appropriate tool, rather than scanning raw bytes like this.
- `badCycle` is a **simplified** parser solely meant to step through the constant pool to `super_class`. It handles the tags needed for common class-file formats; it is not a complete security/commercial-grade class-file reader, and it does not validate every length or input data. Use it on **valid self-compiled input** as instructed.
- Reflection may throw other exceptions such as `NoSuchMethodException`/`InvocationTargetException` if you edit the source so that the matching method no longer exists. Do not use this example as a general-purpose loader for arbitrary classes.
- `BytesLoader` does not define packages/classes from a real JAR; it only uses `defineClass` on a byte array to demonstrate the three errors.
- Do not use intentionally corrupted byte files in real applications or publish them as artifacts.

## 9. Control experiment: static initialization cycle is not ClassCircularityError

Java allows two classes to reference **each other's static fields**. That does **not** create a superclass/superinterface inheritance cycle.

Create `InitializationCycleDemo.java`:

```java
public class InitializationCycleDemo {
    static final class First {
        static int a = Second.b + 1;
    }

    static final class Second {
        static int b = First.a + 1;
    }

    public static void main(String[] args) {
        System.out.println("First.a=" + First.a);
        System.out.println("Second.b=" + Second.b);
    }
}
```

Run:

```bash
javac --release 17 InitializationCycleDemo.java
java InitializationCycleDemo
```

Stdout:

```text
First.a=2
Second.b=1
```

Explanation:

1. When `main` reads `First.a`, the JVM starts initialization of `First`. `First.a` initially has the default value `0` before being assigned by the initializer.
2. `First.a = Second.b + 1` triggers initialization of `Second`.
3. `Second.b = First.a + 1` references `First.a` while `First` is currently being initialized **by the same thread**. The JVM does not re-initialize First; the value of `First.a` at this moment is still `0`.
4. `Second.b` is assigned `1`, then returning to `First.a`, it is assigned `2`.
5. The two variables have values `2` and `1`. **No class extends itself, nor is there a superclass cycle.**

This is a case of **incomplete initialization state**, not class circularity. With multiple threads, circular initialization can lead to waiting/deadlock depending on the synchronization code; however, even that deadlock is not synonymous with `ClassCircularityError`.

## 10. Circular loader delegation is different from a circular type hierarchy

A custom loader can be configured to cross-delegate:

```text
Loader-A.loadClass("x.Service")
    └── Loader-B.loadClass("x.Service")
           └── Loader-A.loadClass("x.Service")
                  └── ...
```

This is a **cycle in the class-lookup algorithm**, which can cause overly deep recursion, `StackOverflowError`, or a lock-induced deadlock, depending on the code. There does not necessarily have to be a circular superclass/superinterface relation.

Conversely:

```text
class A extends B
class B extends A
```

is a **cycle in the type hierarchy**. The JVM reports `ClassCircularityError` when detecting it according to the class creation/loading algorithm.

Distinguish the two types of graphs:
- **Loader delegation graph:** which loader asks which loader.
- **Superclass/superinterface graph:** which class/interface extends which class/interface.

A program can have both issues, so debugging must identify where the cycle actually lies.

## 11. Cases where an error appears after loadClass has already succeeded

In the JVM, **class loading, verification, resolution, and initialization** can occur at different times. Therefore:

```java
// Snippet: loader is a ClassLoader managed by the application.
Class<?> type = loader.loadClass("demo.Plugin");
System.out.println(type.getName()); // May succeed.

// The error might only appear upon a later usage:
type.getDeclaredMethods();
```

This is an **illustrative snippet, not a standalone runnable file**. There is no guarantee that `getDeclaredMethods()` will always trigger `VerifyError` if the class is broken; it depends on the type of violation and JVM timing. The key point: **do not confirm a plugin is safe solely from a single `loadClass` call not throwing an error**.

In a plugin system:
- A rarely invoked method may only be verified/resolved late.
- A new dependency may only be loaded when that feature is activated.
- An AOP/agent transformer might only be applied to classes first requested after startup.
- A test that only loads the entry-point class does not cover all provider implementations.

For greater assurance, run integration tests covering the critical code paths, rather than only calling `Class.forName` on a single class and declaring the artifact valid.

## 12. The role of a custom ClassLoader in these three errors

A custom loader typically reads bytes and then defines the class:

```java
// Snippet inside a ClassLoader subclass:
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    String path = name.replace('.', '/') + ".class";
    byte[] bytes;

    try {
        bytes = Files.readAllBytes(root.resolve(path));
    } catch (IOException cause) {
        throw new ClassNotFoundException(name, cause);
    }

    return defineClass(name, bytes, 0, bytes.length);
}
```

This is a **snippet**; it requires `root`, imports, and an appropriate class loader superclass. Boundary of responsibilities:

- `Files.readAllBytes`: handles I/O errors of the byte source.
- `defineClass`: instructs the JVM to read the class file structure and create a runtime class.
- Verification/linking: performed by the JVM according to the rules.
- The ClassLoader must not ignore `LinkageError` by default or “fix” bytes via exception mapping.

**Anti-pattern**:

```java
// DO NOT use in production:
try {
    return defineClass(name, bytes, 0, bytes.length);
} catch (Throwable ignored) {
    throw new ClassNotFoundException(name);
}
```

This is a flawed snippet. It erases information about:
- `ClassFormatError`;
- `VerifyError`;
- `ClassCircularityError`;
- `OutOfMemoryError` and other severe errors.

Anyone debugging will think the class simply has a missing file and waste time trying to change the classpath. **Only convert actual I/O errors on the lookup path into `ClassNotFoundException` when appropriate for the loader contract, preserving the original cause.**

## 13. ClassFormatError can still occur even when the magic is valid

Looking only at `0xCAFEBABE` is not enough.

Examples of data that still starts with a valid magic number yet may be rejected by the JVM:
- `constant_pool_count` describes more entries than the remaining bytes.
- A `CONSTANT_Class_info` references a non-existent CP slot or one with the wrong tag.
- The `Code` attribute declares a length that does not match its contents.
- A method signature/descriptor violates grammar rules.
- Duplicate/invalid items in class-file structures prohibited by the specification.
- Flags, arrays, and attributes that fail to satisfy class file constraints.

Some errors may be named `ClassFormatError` or another specific error depending on the condition the JVM detects; **do not assert that every byte modification always leads to one fixed Error type**.

To verify:
- Compare the file bytes against the original artifact from the build output and the final artifact on disk/JAR.
- Use `javap -verbose` to inspect the CP and attributes if the tool can parse the file.
- If there is a transformer, compare **before/after bytes**, not just the Java source.
- Use checksums to avoid debugging the wrong JAR or a version cached by the container.

## 14. How does VerifyError commonly go hand in hand with StackMapTable?

For modern class files, the verifier uses information from `StackMapTable` according to JVMS rules. Bytecode transformers must preserve invariants when:
- adding/removing opcodes;
- changing branch destinations;
- adding try/catch handlers;
- changing local variable slots or operand-stack shapes;
- changing a method descriptor/return type;
- changing a constructor initialization path.

Example of a transformer inserting an additional branch:

```text
if (condition) goto L1
...
L1:
   uses a local variable that a prior path
   did not define with the right type
```

If control-flow paths merge with incompatible stack/local variable states, the JVM can throw `VerifyError`. That is a **bytecode verification** error, even though the class file header and CP remain valid.

Some tools such as ASM provide utilities to recompute frames (`COMPUTE_FRAMES`) and max stack. However, enabling frame computation does not automatically fix a broken transformation algorithm: you must ensure valid method semantics and exception handlers.

### Do not confuse with binary API errors

If the method bytecode **passes the verifier**, yet the runtime library lacks a method that existed at compile time, a subsequent call can throw `NoSuchMethodError`. If the method's static/instance contract changed, it may be `IncompatibleClassChangeError`. If access changed, it may be `IllegalAccessError`.

These are **other linkage issues**, not `VerifyError` just because they arise when using a method.

## 15. ClassCircularityError and hierarchy correctness

A JVM runtime class has a superclass chain following the rules, and interfaces have superinterfaces. This chain/graph must not form an invalid cycle.

For example:
- `A extends B`;
- `B extends C`;
- `C extends A`.

A normal source compiler will reject such relationships if all sources are analyzed together. However, tools that generate/merge class files independently or deploy mismatched artifacts can produce bytes representing a cyclic inheritance graph.

When the JVM needs to define `A`, it must determine the relevant super types. If it detects that the class being defined appears again in its own super chain, **`ClassCircularityError`** reflects the superclass/superinterface cycle.

### Is circularity a deadlock?

No. `ClassCircularityError` is a type of `LinkageError` thrown by the JVM to report an invalid type hierarchy; a deadlock occurs when threads lock/wait on one another and may not throw an exception.

### Is a cycle in an object graph invalid?

No. Two objects holding references to each other is a common situation, and the GC supports collecting entire cycles when not reachable from roots:

```java
class Node {
    Node next;
}
```

The snippet above is valid. `a.next=b; b.next=a;` is **unrelated** to `ClassCircularityError`.

## 16. Step-by-step diagnostic technique

### Step 1 — Retrieve the root error, not just the wrapper

In a plugin manager, exceptions from reflection may be wrapped by `InvocationTargetException`, `ExecutionException`, or framework-specific exceptions. Log:
- the actual Throwable type;
- the message and stack trace;
- the cause chain;
- suppressed exceptions when present;
- the requested class binary name;
- the class loader identity and source URL/JAR.

For example, logging only `"Error loading plugin"` is not enough.

### Step 2 — Identify the actual bytes

If the class appears in multiple JARs, on the classpath/module path, or across parent/child loaders, you must know **which file was actually defined**. Record:
- the JAR path and entry;
- the version/build hash;
- the actual class file bytes or checksum when available;
- the bytes before/after instrumentation;
- the defining loader of related successfully loaded classes.

Do not just look at the project's `src/` and assume the final artifact matches the source.

### Step 3 — Compare compile JDK and runtime JDK

```bash
java -version
javac -version
```

If the versions differ, inspect the compilation target. Information such as the major version is very helpful:

```bash
javap -verbose -classpath inputs VerifyTarget
```

With `javac --release 17`, the `major version` is normally `61`.

### Step 4 — Distinguish the three branches

**If `ClassFormatError`:**
- Check the magic/header, size, constant pool, and class-file attributes.
- Check whether a wrong JAR/HTML/other resource was read.
- Compare artifacts before/after the transformer.
- Check `UnsupportedClassVersionError` first because it is a specific subtype.

**If `VerifyError`:**
- Use `javap -c -v` to inspect opcodes and `StackMapTable`.
- Identify the method or control-flow location reported by the JVM.
- Compare bytecode before/after agents, shading, and obfuscation.
- Check whether the bytecode tool version supports the class-file target.

**If `ClassCircularityError`:**
- Identify the class/interface mentioned in the message.
- Trace `super_class`/`interfaces` from the class file.
- Build the superclass/superinterface graph of the actual artifacts; look for cycles.
- Distinguish cycles in the loader delegation graph from cycles in the type hierarchy.

### Step 5 — Reproduce in a clean loader and runtime

If a class has already been successfully defined on a loader, `findLoadedClass` may return the old class instead of re-reading the modified file. When debugging bytecode variants:
- create a **new ClassLoader** or start a new JVM process;
- ensure the parent does not already have a class with the same name;
- separate the host and plugin classpaths;
- keep the exact JVM arguments/agents/plugin classpath from the failing environment.

Do not claim “the file was fixed yet the error stays the same” if the JVM is actually using a previously loaded runtime class.

## 17. Log/observe the JVM with appropriate tools

On HotSpot, unified logging is supported:

```bash
java -Xlog:class+load=info -cp host ErrorKindsDemo
```

The command assumes `host`/`inputs` were created per section 8 and runs in the correct directory. The class loading log can be very long; it is **not** a complete log of verification/resolution or the steps performed by a custom loader.

You can use:

```bash
javap -verbose -classpath inputs VerifyTarget
javap -c -classpath inputs VerifyTarget
```

`javap` shows **the original class before the program modifies the bytes in memory**. If you need to inspect **the modified bytes**, dump a temporary copy in a test environment and inspect that copy; avoid overwriting a valid artifact currently used by the running application.

A custom loader can log:

```java
// Snippet inside findClass, before defineClass:
System.out.println(
        "requested=" + name
        + ", loader=" + this.getClass().getName()
        + ", bytes=" + bytes.length
);
```

Do not log raw bytecode or paths containing secrets/credentials in production unless necessary. A file checksum is usually more useful than printing all bytes.

## 18. How to catch errors properly at the plugin boundary

In the plugin orchestration layer, it is sometimes necessary to turn JVM errors into a **diagnostic report** instead of letting the entire host crash immediately. Here is an illustrative snippet:

```java
// SNIPPET: loader and binaryName are existing variables,
// report(...) is a method of the plugin manager.
try {
    Class<?> type = loader.loadClass(binaryName);
    activatePlugin(type);

} catch (UnsupportedClassVersionError error) {
    report("Unsupported class file version", error);

} catch (ClassFormatError error) {
    report("Malformed class file", error);

} catch (VerifyError error) {
    report("Bytecode verification failed", error);

} catch (ClassCircularityError error) {
    report("Circular superclass/superinterface hierarchy", error);

} catch (ClassNotFoundException error) {
    report("Class not found by configured loader", error);

} catch (LinkageError error) {
    report("Other JVM linkage error", error);
}
```

**This is not a standalone compilable source:** `activatePlugin`, `report`, `loader`, and `binaryName` belong to application code.

Essential rules:
- **Catch order:** `UnsupportedClassVersionError` before `ClassFormatError` because it is a subclass. Specific errors before `LinkageError`.
- `ClassNotFoundException` is a checked exception; preserve the original cause from I/O/lookup when appropriate.
- Do not catch broad `Error` or `Throwable` and “let the plugin keep running as if nothing happened”.
- A plugin that failed loading/linking may not be safe to continue; mark its failure state and do not activate a partial instance.
- Clean up resources registered during plugin start (listeners, tasks, classloader) via the lifecycle manager; handling a diagnostic error does not mean all side effects prior to the error were rolled back.
- If you see `OutOfMemoryError`, `StackOverflowError`, `ThreadDeath`, or other VM errors, they are **not** cases to arbitrarily fall back to another JAR.

**Do not convert `ClassFormatError`/`VerifyError`/`ClassCircularityError` into `ClassNotFoundException`.** Doing so hides the technical cause and usually leads to modifying the classpath in the wrong place.

## 19. Parent-child class loading mechanism must not replace the cause

The default loader performs:

```text
findLoadedClass(name)
   ↓ not yet present
parent.loadClass(name)
   ↓ if parent does not find it
findClass(name)
   ↓ defineClass(bytes)
```

Note when the parent loader throws `ClassFormatError`:
- This is **not `ClassNotFoundException`**.
- The standard `loadClass` algorithm **does not automatically catch every LinkageError from the parent and fall back to the child**.
- If a custom loader does so, it can mask a corrupted artifact in the parent and arbitrarily load another version, increasing the risk of class identity, package mismatch, or binary compatibility issues.

Cases that genuinely need to search the child before the parent must define a clear **delegation policy** by namespace and obey JVM constraints. Do not use child-first as a generic “cure-all” for broken bytecode.

## 20. A “triage” table for reading stack traces

| What is in the stack trace? | What to verify first | What not to do |
|---|---|---|
| `ClassFormatError: Incompatible magic value ...` | Is the class file data from the right source/format? | Only adding a JAR without inspecting the bytes |
| `UnsupportedClassVersionError: class file version ...` | Target major/minor and runtime JDK | Patching a few header bytes to a lower version |
| `VerifyError: Bad type on operand stack` | Method bytecode, frames, transformer | Disabling verification |
| `VerifyError: Expecting a stackmap frame ...` | Branch target, StackMapTable, Java target | Guessing it is ClassNotFoundException |
| `ClassCircularityError: ...` | Actual superclass/interface graph | Treating every field reference as an “inheritance cycle” |
| `NoClassDefFoundError: ...` | Missing dependency, wrong name, or prior init failure | Assuming it is VerifyError by default |
| `ClassNotFoundException: ...` | Loader search path/binary name/parent | Assuming the file is corrupted by default |
| `NoSuchMethodError` | Compile/runtime ABI of the dependency | Baselessly editing StackMapTable |

Specific messages and stack-trace frames are **VM/version-specific**. The table is intended to suggest troubleshooting directions, not to guarantee that the message string will be identical across all JVMs.

## 21. Common mistakes when generating or transforming bytecode yourself

The three main errors must be addressed through the **source bytes** and **appropriate JVM rules**:

| Practical scenario | Error category | How to fix |
| --- | --- | --- |
| Custom loader mistakenly fetches HTML/ZIP or the class file is truncated | `ClassFormatError` | Check resource URL, magic, constant pool/attributes, and input bytes passed to `defineClass` |
| Transformer changes branches, operand stack, or exception handlers without updating frames | `VerifyError` | Check `Code`, `StackMapTable`, paths, and use a generator compatible with the target JDK |
| Transformer sets `super_class` to `this_class` itself or creates A↔B inheritance | `ClassCircularityError` | Analyze the superclass/superinterface graph from the actual class files |

Related scenarios that **do not share the same mechanism**: a Java 17 runtime receiving major 65 bytecode causes `UnsupportedClassVersionError`; a `static` initialization cycle is not a circular superclass; parent/child loader delegation recursion does not automatically produce `ClassCircularityError`.

If a loader has already defined a `Class<?>`, replacing the JAR on disk and calling `loadClass` again may return the old class. To reproduce a bytecode fix, you need a **fresh defining loader/JVM** and must ensure the parent does not shadow the bytecode under test. When testing, do not catch every `Throwable` and convert it into `ClassNotFoundException`, because that loses the real cause.

## 22. Safe Java artifact release checklist

**At build time:**
- Pin the target JDK (`--release`) and supported runtime JDK.
- Verify that ASM/Byte Buddy/Javassist/obfuscator versions match the class-file version.
- Do not ignore important compiler warnings about invalid bytecode transformers.
- Keep artifact metadata/checksums to trace the exact class files actually released.
- For generated classes, run JVM loading and invocation tests on the target JDK.

**At plugin loading:**
- Distinguish missing bytes from invalid bytes.
- Use the proper parent/shared API; avoid redefining duplicate runtime types.
- Pass the exact binary name to `defineClass`.
- Do not swallow `LinkageError` and fall back silently.
- Halt activation when class hierarchy/verification fails.

**During debugging:**
- Capture the full stack trace and cause chain of the **first error**.
- Inspect the class loader instance, module/layer when applicable, and source artifact.
- Use `javap -verbose`/`-c`, runtime logs, and bytecode before/after transformation.
- Reproduce in a fresh JVM/loader with the same runtime version/properties/agent.
- For `ClassCircularityError`, check the **extends graph**, not just method calls.

**In operations:**
- If plugin startup fails, clean up created resources before reporting the error.
- Do not let listeners/threads/caches of a failed plugin retain the loader in memory.
- If you want to test a fixed class version, create a new-generation loader instead of continuing to use the old runtime class.
- Do not expect GC/unloading to happen immediately after encountering `LinkageError` or calling `URLClassLoader.close()`.

## 23. Self-check exercises

1. **Is `ClassFormatError` a checked exception?** No; it extends `LinkageError` → `Error`.
2. **Is `VerifyError` a subclass of `ClassFormatError`?** No; it is a sibling under `LinkageError`.
3. **What kind of cycle does `ClassCircularityError` report?** A superclass/superinterface hierarchy cycle.
4. **Is Java source with `A extends B` and `B extends A` valid?** No; a normal compiler rejects it.
5. **Does field `A.b` of type B and `B.a` of type A automatically produce ClassCircularityError?** No.
6. **Does a file with the right magic guarantee it will not throw ClassFormatError?** No; other structures may be invalid.
7. **What can a method `int f()` executing `aconst_null; ireturn` cause?** `VerifyError`.
8. **What is `UnsupportedClassVersionError` a subclass of?** `ClassFormatError`.
9. **Does a successful `loadClass` guarantee that every method has been fully checked by the verifier?** You should not assume so; verification/resolution timing may differ.
10. **Does a TCCL/delegation cycle between loaders always throw `ClassCircularityError`?** No; that is a different type of graph, which can cause recursion/deadlock.
11. **If the parent throws `VerifyError`, does a default child loader automatically use another version?** No; LinkageError is not treated as ClassNotFoundException.
12. **When running Java 17 with a major 65 class file, what error is commonly encountered?** `UnsupportedClassVersionError`.
13. **Why does the demo use a separate loader for each scenario?** To avoid caching an already loaded class and to isolate test state.
14. **Why shouldn't you catch `Throwable` and throw CNFE?** It hides verifier/format/circularity errors as well as other VM errors.
15. **How do you find the root ClassFormatError?** Check source bytes, header/CP/attributes, transformers, and artifacts.
16. **How do you find the root VerifyError?** Inspect method instructions, StackMapTable, frames, and bytecode after instrumentation.
17. **How do you find the root ClassCircularityError?** Build the superclass/superinterface graph from the actual class files.
18. **Does the static initialization cycle in the `First`/`Second` example throw ClassCircularityError?** No; this is initialization, where incomplete static values can be observed.
19. **If you fix the .class on disk and call the old loader again, are you guaranteed to get the fixed version?** No; the loader may have already defined the old runtime class.
20. **What should a plugin manager do with a LinkageError when activating a plugin?** Log diagnostics, mark failure, and clean up resources; do not continue running it as a valid plugin.

## 24. Official references

- [Java SE 17 — ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html): malformed class file error or unable to be interpreted validly.
- [Java SE 17 — VerifyError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html): class bytecode verification error.
- [Java SE 17 — ClassCircularityError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCircularityError.html): cycle in the superclass/superinterface hierarchy.
- [Java SE 17 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): class file major/minor version error.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, class identity/delegation.
- [JVMS 17 — `4 The Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): magic, constant pool, `this_class`, `super_class`, `Code`, and `StackMapTable`.
- [JVMS 17 — `5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class/interface creation, circularity checks, linking, and verification.
- [JLS 17 — `12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, and error timing requirements.

**Conclusion:** When Java cannot use a class, classify it properly: **`ClassFormatError` is class-file structure/format**, **`VerifyError` is bytecode verification**, and **`ClassCircularityError` is a superclass/superinterface hierarchy cycle**. All three belong to **`LinkageError`** yet require different investigation paths. The most reliable investigation data consists of **the actual class file bytes received by the JVM, the defining ClassLoader, the runtime JDK, the specific method/type relationship, and the first root error** — not just the JAR name or the string “class loading failed”.
