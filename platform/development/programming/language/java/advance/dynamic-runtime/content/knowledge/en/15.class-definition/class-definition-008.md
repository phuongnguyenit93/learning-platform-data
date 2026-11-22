# 15.8 Duplicate Class Definition, Wrong Class File Version, VerifyError, and LinkageError

**Module:** Java Advance - dynamic-runtime  
**Parent Topic:** 15. Class Definition  
**Practice Environment:** Java 17+ (compile examples with `javac --release 17`).  
**Focus:** defining classes with `ClassLoader.defineClass`, runtime class identity, version/format/bytecode checking, binary linkage, and error analysis.

## 1. Learning Objectives

In dynamic programs, classes may be precompiled, read from JARs, loaded by multiple `ClassLoader`s, or generated from bytecode. A class file that is valid in terms of **data** is not necessarily valid in terms of **JVM instruction flow**; a class that exists is not necessarily compatible with another class compiled against an older version; and the same **binary name** does not guarantee only a single runtime type across the entire JVM.

After completing this lesson, you can:

1. Distinguish **binary name**, **defining class loader**, **initiating loader**, `Class<?>` runtime identity, and the consequences of having the same name in different loaders.
2. Explain why redefining a binary name in the **same defining loader** with `defineClass` is not equivalent to reloading, and can throw `LinkageError`.
3. Read the class file header: `0xCAFEBABE`, `minor_version`, `major_version`; check compatibility between the JDK used for compilation and the JVM used for execution.
4. Accurately distinguish `UnsupportedClassVersionError`, `ClassFormatError`, `VerifyError`, and other subclasses of `LinkageError`.
5. Understand the logical order **loading → linking (verification, preparation, resolution) → initialization**, as well as why the time an error is observed may be delayed.
6. Compile a Java 17+ demo reproducing **duplicate definition**, **unsupported version**, **corrupted class bytes**, **unverifiable bytecode**, and **two different loaders with the same class name**.
7. Reproduce `NoSuchMethodError` by compiling a client against one API, then running with an incompatible API version.
8. Diagnose errors using `java -version`, `javac -version`, `javap -verbose`, classpath/module path, and class loading traces without "fixing" errors by disabling the verifier.

## 2. JVM Context: Three Easily Confused Class Name Concepts

### 2.1. Binary name in a class file

Each class has a binary name such as:

~~~text
com.example.plugin.UserTransformer
com.example.plugin.Outer$Inner
~~~

The internal name in the constant pool is usually written with slashes like `com/example/plugin/UserTransformer`. The class file stores this name in the `this_class` structure; when `ClassLoader.defineClass` receives `name == null`, the JVM obtains the actual name from the class bytes.

`ClassLoader.defineClass(String name, byte[] b, int off, int len)` can use an expected binary name. If `name` is specified but **does not match the binary name in the bytes**, the JVM may throw `NoClassDefFoundError` in the "wrong name" form. This is **not the same** as a duplicate definition error.

Clearly separate:

- **Filename `UserTransformer.class`**: a common way to store data; the filename itself does not create identity.
- **Binary name**: `com.example.plugin.UserTransformer` inside the class file.
- **`Class<?>` object**: the type already defined by the JVM, carrying actual class loader/module information.

### 2.2. Runtime identity is not just a name string

For ordinary reference types defined by a class loader, the JVM identifies a type by **binary name + defining loader**. Two separate loaders can define a class with the same binary name and obtain two **different** `Class<?>` objects:

~~~text
loader A -> class com.example.Message -> Class object A
loader B -> class com.example.Message -> Class object B

A.getName().equals(B.getName()) == true
A == B                               == false
~~~

This by itself is **not a duplicate definition error**, because the two loaders have different defining namespaces. However, it has consequences:

- An object created from loader B's type **cannot be automatically cast** to the same-named type of loader A.
- Two interfaces with the same binary name defined by two loaders may be incompatible in a plugin system.
- A method signature crossing two loader hierarchies may violate JVM **loader constraints**; some cases throw `LinkageError` with loader constraint violation details.
- If you want host/plugin to communicate using the same SPI, both must use **the exact same SPI definition** through an intentional class loader/module topology, not merely by copying a JAR with the same name.

**Do not equate:** "loaders A/B both define name X" is different from "one loader A attempts to `defineClass` name X a second time".

### 2.3. Defining loader and initiating loader

The **defining loader** is the loader that actually defines the class from bytes. The **initiating loader** is a loader recorded by the JVM as having participated in requesting to load that type; through parent delegation, the initiating loader is not necessarily the defining loader.

According to the default implementation of `ClassLoader.loadClass(name, resolve)`:

1. Check `findLoadedClass(name)` to see if that name has already been recorded by this loader.
2. Try the **parent loader**.
3. If the parent does not find it, call `findClass(name)` for the current loader to define it.
4. If requested, call `resolveClass`.

Therefore, **two standard calls to `loadClass("X")` do not mean two calls to `defineClass("X")`**. `loadClass` has caching/delegation and synchronization on the class loading lock. In the demo below, we **deliberately call a direct wrapper of `defineClass`** twice to demonstrate the JVM rejecting a duplicate definition; that is not a production loader implementation pattern.

## 3. Class Lifecycle: Which Phase Do Errors Appear In?

Conceptual model:

~~~text
Read class bytes / find definition
        |
        v
LOADING: create or find Class object, check required structure
        |
        v
LINKING:
    - verification: check types and validity of bytecode
    - preparation: prepare static fields area with default values
    - resolution: connect symbolic references to actual classes/members
        |
        v
INITIALIZATION: run static initializer / set up static state
        |
        v
USAGE: instantiate instance, call method, access field
~~~

Do not infer from the diagram that every JVM must perform **all resolution** at a single point in time before using a class. Resolution of symbolic references may be performed eagerly or lazily according to JVM rules; verification of a class may also become observable when the class is **resolved/actively-used/reflectively-used**, depending on the specific mechanism.

This matters in debugging: a stack trace at `Class.forName`, `ClassLoader.defineClass`, `getDeclaredMethod`, or a method call is **not sufficient** to conclude that the error was *created at that source line*. Often that is simply the point where the JVM is forced to load/link a dependent class that is no longer valid.

### 3.1. Do not confuse compile-time and runtime

- **Compile-time (`javac`):** source is checked against the dependencies visible to the compiler, producing bytecode and symbolic references.
- **Runtime (`java`):** the JVM loads the actual artifacts present on the classpath/module path. They **may have a different version** than at build time.
- **Class loading:** bytes may come from disk, archive, network, generated code, or a custom loader.
- **Linking:** the JVM must trust that the classfile and its links are valid; an error may only surface when a specific method is used.

Successful compilation does not guarantee that the runtime classpath contains binary compatible dependencies.

## 4. `LinkageError` Is an Error Family, Not a Single Cause

`java.lang.LinkageError` is a subclass of `Error`, and contains many errors related to defining/linking/executing compiled classes. It is not a checked exception like `ClassNotFoundException`.

~~~text
java.lang.Error
  |
  +-- LinkageError
       |
       +-- ClassFormatError
       |     +-- UnsupportedClassVersionError
       +-- VerifyError
       +-- NoClassDefFoundError
       +-- IncompatibleClassChangeError
       |     +-- NoSuchMethodError
       |     +-- NoSuchFieldError
       |     +-- AbstractMethodError
       |     +-- IllegalAccessError
       +-- ClassCircularityError
       +-- BootstrapMethodError
       +-- ExceptionInInitializerError
       +-- UnsatisfiedLinkError
~~~

*This is a hierarchy diagram of some common error types*, not an exhaustive list of every subclass or every situation. The subclasses describe **many different failure mechanisms**; read the specific type rather than only knowing generally "LinkageError".

| Type | Layer typically involved | Typical symptom |
| --- | --- | --- |
| Direct `LinkageError` | Conflicting definition/linkage | A defining loader attempts to define the same binary name a second time; loader constraint violation |
| `UnsupportedClassVersionError` | Classfile format/version | JVM does not support `major_version`/`minor_version` |
| `ClassFormatError` | Reading class file structure | Invalid magic/header/constant pool/attribute or corrupted class bytes |
| `VerifyError` | Bytecode verification | Classfile has sufficient basic structure, but operand stack/local types/frames are invalid |
| `NoClassDefFoundError` | JVM needs a class but has no suitable definition, or the class previously failed initialization | Missing runtime dependency, mismatched name, or erroneous state of the class |
| `NoSuchMethodError` | Resolution of a method reference | Client was compiled against a method present in API v1, while runtime sees API v2 without that method |
| `NoSuchFieldError` | Resolution of a field reference | Field was removed/renamed/changed in type according to the binary contract |
| `AbstractMethodError` | Method call with no usable implementation | Interface/class change makes an old binary implementation no longer valid |
| `IllegalAccessError` | Runtime access checking | Member/package/module is no longer accessible under runtime linkage |
| `IncompatibleClassChangeError` | Mismatched member/class kinds and binary API | Changed from instance to static, or changed a class to an interface |
| `BootstrapMethodError` | `invokedynamic`/dynamic constants linkage | Bootstrap does not produce valid linkage |
| `ExceptionInInitializerError` | Class initialization | Static initializer throws an exception that is not an Error |
| `UnsatisfiedLinkError` | Native library/method linkage | Missing native library or appropriate JNI symbol |

**Special distinction:** `UnsupportedClassVersionError extends ClassFormatError extends LinkageError`. Meanwhile, `VerifyError extends LinkageError` **directly**, not through `ClassFormatError`. Therefore, a `catch(ClassFormatError e)` statement can catch unsupported version as well, but **does not catch VerifyError**.

Do not use `catch(LinkageError e)` to swallow all errors and continue with a class loader in an uncertain state. These are usually **serious configuration/build/artifact/ABI errors**; diagnostics should be collected, the failing plugin isolated, and the problematic execution path stopped.

## 5. Class File Version: major/minor and `UnsupportedClassVersionError`

### 5.1. Class file header

The beginning structure of a JVM class file:

~~~text
byte offset    0  1  2  3 | 4  5 | 6  7
value          CA FE BA BE | minor | major
               magic        u2      u2
~~~

- `magic=0xCAFEBABE`: marker identifying a class file.
- `minor_version` and `major_version`: two **unsigned 16-bit big-endian** integers describing the class format version.
- Subsequent sections include the constant pool, modifiers, superclass/interfaces, methods, and attributes.

Common mapping examples:

| Java release | Class file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

A Java 17 JVM supports classfile major up to **61**, and cannot load a Java 21 classfile with major 65. That case can produce `UnsupportedClassVersionError`. The demo example below **deliberately sets major to 99** so it is guaranteed not to be supported on the JDK used for testing, **not** an actual Java release version.

From class file major 56 onward, minor is usually `0` or `65535` by format; minor `65535` relates to **preview features** and has additional rules allowing loading only on a JVM of the exact release with preview enabled. Do not only check major while ignoring minor in all cases.

### 5.2. How to identify the actual version

Check the tools actually being used:

~~~bash
java -version
javac -version
~~~

Inspect the built class file:

~~~bash
javap -verbose -classpath out 'ClassDefinitionFailureDemo$Good'
~~~

Look for the line:

~~~text
major version: 61
~~~

Commands using nested class names contain the `$` character, so the example puts the name in **single quotes**. If using Windows PowerShell, single quotes also preserve the `$` character literally. Do not rely solely on `pom.xml`/`build.gradle`: the artifact actually running may be pulled from a cache, Docker image, shaded JAR, multi-release JAR, or another dependency.

### 5.3. Properly fixing unsupported version errors

- If the **runtime is older** while the artifact was compiled with a newer Java, upgrade the runtime according to release policy **or** rebuild targeting a supported release.
- With JDK 17+ targeting Java 17: `javac --release 17 ...`. This flag selects the language, classfile version, **and** platform API appropriate for the target release.
- Do not assume `--source 17 --target 17` is always equivalent to `--release 17` in guaranteeing that only Java 17 APIs are used when the compiler is running on a newer JDK.
- Do not manually edit the major byte down to 61 in production artifacts: the bytecode may still use incompatible opcodes, constant pool tags, classfile features, or newer APIs. The demo modifies bytes **only to create a controlled error**.
- If using preview features, configure the corresponding Java release/`--enable-preview`; do not treat `--release` alone as a solution for all preview classes.

## 6. Duplicate Name Definition in the Same Loader

### 6.1. `defineClass` creates a class, not "replacing methods of an existing class"

Suppose a custom loader has executed:

~~~java
Class<?> first = defineClass(
        "demo.Dynamic", validBytes, 0, validBytes.length);
~~~

This snippet is only **an illustration inside a `ClassLoader` subclass** that has access to the protected method; `validBytes` is classfile bytes with the matching binary name. If the loader **attempts to define the same name again** in that very same loader, the JVM may throw `LinkageError` directly for "attempted duplicate class definition".

This is not a hot reload mechanism. A `Class<?>` object that has already been defined cannot be replaced by calling `defineClass` a second time in the same loader.

### 6.2. Two valid ways to handle a reload requirement

**If you only want to reuse an already loaded class:** use `loadClass` with caching/parent delegation; by default `ClassLoader.loadClass` already has `findLoadedClass` logic. Custom loaders usually only override `findClass`, rather than calling `defineClass` on every request.

**If you genuinely need a different version of a class with the same name:** you can create a **new class loader** to define the new version. However, objects from the old and new loaders have **different runtime types**, which can cause `ClassCastException`, duplicate service contracts, loader constraints, resource retention, or classloader leaks. You must separate communication boundaries through a shared API/SPI and manage lifecycle.

**Instrumentation:** `java.lang.instrument.Instrumentation.redefineClasses`/`retransformClasses` is a different specialized mechanism with limitations (not all class structure changes are supported). It is **not** equivalent to calling `defineClass` a second time. Do not present it as the default solution for every plugin hot swap.

### 6.3. Class loading race and synchronization rules

If two threads concurrently request to define the same name:

- Use the standard `loadClass` mechanism and appropriate `getClassLoadingLock(name)` locking; the JVM also needs to protect the defining namespace.
- Avoid unsynchronized "check-then-define": two threads both see the class is absent and both call `defineClass`.
- Parallel-capable loaders have their own registration and locking rules; do not invent custom synchronization without understanding the model.
- Do not catch `LinkageError` and assume the second class "has already been loaded successfully": distinguish racing-thread conflicts from other classfile/loader constraints.

## 7. How Do `ClassFormatError` and `VerifyError` Differ?

### 7.1. Format checking: can the classfile be decoded?

For example, class bytes with an invalid magic number:

~~~text
before: CA FE BA BE ...
after:  00 FE BA BE ...
~~~

When the JVM reads bytes that no longer have a valid classfile header, the appropriate error is **`ClassFormatError`**. Other errors can arise when the constant pool, attributes, metadata, or classfile size are structurally invalid.

**`UnsupportedClassVersionError`** is the case where the classfile version is not supported and sits **under `ClassFormatError` in the inheritance tree**. The error message may contain "class file version X" and "runtime recognizes up to Y", but do **not** rely on the text message as a stable API contract.

### 7.2. Verification: is the bytecode safe under the JVM type system?

A classfile can have **valid magic, a supported version, and a valid constant pool**, yet the code inside violates type safety:

- `iadd` requires popping **two `int`s** from the operand stack; `ladd` requires **two `long`s**.
- `ireturn` requires `int`, `areturn` requires reference; the return opcode must match the method descriptor.
- Local variables have types incompatible with load/store instructions.
- Control flow jumps to an invalid offset, inconsistent stack height/stack map frames, or improper use of uninitialized objects.
- A bytecode-modifying tool (instrumentation/obfuscator/generator) corrupts `StackMapTable` or frames for modern Java classfiles.

Example method:

~~~java
public static int addOne(int n) {
    return n + 1;
}
~~~

With `javac --release 17`, the bytecode sequence for this method can be:

~~~text
iload_0
iconst_1
iadd
ireturn
~~~

In the tested demo, we replace **one opcode byte `iadd (0x60)`** with **`ladd (0x61)`**, while the stack beforehand holds two ints. The classfile still has basic structure, but the method **cannot be verified** → `VerifyError`.

This is an illustration to understand the verifier; **it is not a guide for modifying real artifacts**. Do not patch bytes of production libraries or disable the verifier to "make it run". If using ASM/Byte Buddy/agents, ensure **bytecode shape, operand stack, local frames, and stack maps** are valid and the version is appropriate.

### 7.3. Do not determine the phase solely from where the error is thrown

The JVM may perform format checks when defining a class and verify at link time / when the class is required for use. In the demo, the code deliberately looks up the method via Reflection after `defineClass` to trigger verification if it has not happened yet. **There is no guarantee that `VerifyError` is always thrown right at `defineClass`** across all JVMs.

`javac` normally produces valid bytecode. If you see `VerifyError` after instrumentation, shading, or bytecode enhancement, inspect the **final bytes the JVM actually receives**, not just the original Java source.

## 8. Java 17 Demo: Reproducing Four Error Types in One File

Complete program:

- Reads bytes of **compiled nested classes**.
- Defines a binary name with a custom loader, then attempts `defineClass` a second time **in the same loader**.
- Defines the same name from **another loader** and compares runtime identity.
- Changes `major_version` to 99 → `UnsupportedClassVersionError`.
- Corrupts the first magic byte → `ClassFormatError`.
- Changes `iadd` to `ladd` in a simple method → `VerifyError`.
- Checks the superclass relationships among the error types.

**Standalone runnable file:** `ClassDefinitionFailureDemo.java`

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;

public final class ClassDefinitionFailureDemo {
    public static final class Good {
        public static String message() { return "ok"; }
    }

    public static final class Arithmetic {
        public static int addOne(int n) { return n + 1; }
    }

    private static final class RawLoader extends ClassLoader {
        RawLoader() {
            super(ClassDefinitionFailureDemo.class.getClassLoader());
        }
        Class<?> defineRaw(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    private static byte[] classBytes(Class<?> type) throws IOException {
        String resource = type.getName().replace('.', '/') + ".class";
        try (InputStream input = ClassDefinitionFailureDemo.class
                .getClassLoader().getResourceAsStream(resource)) {
            if (input == null) {
                throw new IOException("Missing resource: " + resource);
            }
            return input.readAllBytes();
        }
    }

    private static int locate(byte[] bytes, byte[] pattern) {
        int found = -1;
        for (int i = 0; i <= bytes.length - pattern.length; i++) {
            boolean match = true;
            for (int j = 0; j < pattern.length; j++) {
                if (bytes[i + j] != pattern[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                if (found >= 0) {
                    throw new IllegalStateException("Bytecode pattern not unique");
                }
                found = i;
            }
        }
        if (found < 0) {
            throw new IllegalStateException("Bytecode pattern absent");
        }
        return found;
    }

    public static void main(String[] args) throws Exception {
        byte[] good = classBytes(Good.class);
        int major = ((good[6] & 0xff) << 8) | (good[7] & 0xff);
        System.out.println("classFileMajor=" + major);

        RawLoader firstLoader = new RawLoader();
        Class<?> first = firstLoader.defineRaw(good);
        System.out.println("first=" + first.getName());

        try {
            firstLoader.defineRaw(good);
            System.out.println("duplicate=unexpected");
        } catch (LinkageError expected) {
            System.out.println("duplicate=" + expected.getClass().getSimpleName());
        }

        Class<?> peer = new RawLoader().defineRaw(good);
        System.out.println("sameBinaryName=" +
                first.getName().equals(peer.getName()));
        System.out.println("sameRuntimeClass=" + (first == peer));

        byte[] tooNew = good.clone();
        tooNew[6] = 0;
        tooNew[7] = 99;
        try {
            new RawLoader().defineRaw(tooNew);
            System.out.println("version=unexpected");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("version=" + expected.getClass().getSimpleName());
        }

        byte[] badFormat = good.clone();
        badFormat[0] = 0;
        try {
            new RawLoader().defineRaw(badFormat);
            System.out.println("format=unexpected");
        } catch (ClassFormatError expected) {
            System.out.println("format=" + expected.getClass().getSimpleName());
        }

        byte[] broken = classBytes(Arithmetic.class);
        byte[] instructions = {(byte) 0x1a, (byte) 0x04, (byte) 0x60, (byte) 0xac};
        int offset = locate(broken, instructions);
        broken[offset + 2] = (byte) 0x61; // iadd -> ladd; stack holds two ints
        try {
            Class<?> invalid = new RawLoader().defineRaw(broken);
            Method method = invalid.getDeclaredMethod("addOne", int.class);
            method.invoke(null, 1);
            System.out.println("verify=unexpected");
        } catch (VerifyError expected) {
            System.out.println("verify=" + expected.getClass().getSimpleName());
        }

        System.out.println("versionIsLinkage=" +
                (UnsupportedClassVersionError.class.getSuperclass()
                        == ClassFormatError.class));
        System.out.println("verifyIsLinkage=" +
                (VerifyError.class.getSuperclass() == LinkageError.class));
        System.out.println("formatIsLinkage=" +
                (ClassFormatError.class.getSuperclass() == LinkageError.class));
    }
}
~~~

### 8.1. Compile and run

Save with the exact filename `ClassDefinitionFailureDemo.java`, using JDK 17 or higher:

~~~bash
javac --release 17 -d out ClassDefinitionFailureDemo.java
java -cp out ClassDefinitionFailureDemo
~~~

The commands above work when run from the directory containing the source; `javac -d out` creates the output directory if it does not exist yet. The helper classes `Good`/`Arithmetic` are generated by `javac` in the same classpath directory; the `classBytes` helper reads them via resource stream.

**Verified stdout of the program:**

~~~text
classFileMajor=61
first=ClassDefinitionFailureDemo$Good
duplicate=LinkageError
sameBinaryName=true
sameRuntimeClass=false
version=UnsupportedClassVersionError
format=ClassFormatError
verify=VerifyError
versionIsLinkage=true
verifyIsLinkage=true
formatIsLinkage=true
~~~

The demo was compiled with `javac --release 17` and ran successfully on the test JVM, and `javap -verbose` confirmed classfile major 61.

### 8.2. Why does the demo use `defineClass(null, ...)`?

This is an intentional test setup:

- `name=null` lets the JVM obtain the binary name from the class bytes; thus we do not need to know the nested class name before calling.
- `defineRaw` **bypasses parent delegation** and calls `defineClass` directly, allowing us to intentionally trigger a duplicate name error in the **same loader**.
- Production loaders typically use `findClass` within the `loadClass` model; do not copy `defineRaw` as a way to "reload" classes.
- Each modified-bytes test uses **a new `RawLoader` instance** so the error being tested is not confused with a duplicate error from the previous test.
- Classfile bytes are only cloned and modified **in RAM**. The program does not overwrite any JAR/class file of the project.

### 8.3. Explanation of each output line

**`classFileMajor=61`:** `javac --release 17` produces the class file format corresponding to Java 17.

**`duplicate=LinkageError`:** `firstLoader` already defined `ClassDefinitionFailureDemo$Good` once; the second definition with the same binary name and defining loader is rejected by the JVM.

**`sameBinaryName=true`, `sameRuntimeClass=false`:** two different `RawLoader`s define the same bytes, same name, but return two different `Class<?>` objects. There is no `LinkageError` merely because two independent loaders use the same name.

**`version=UnsupportedClassVersionError`:** byte offsets 6–7 were set to major 99, which is not supported by the running JVM. This is a **version error**, not a VerifyError.

**`format=ClassFormatError`:** the first byte of magic `CAFEBABE` was modified, causing the format to no longer be recognized.

**`verify=VerifyError`:** the `Arithmetic` classfile still has valid file structure, but method `addOne` has opcode `ladd` while the operand stack holds two ints. The verifier rejects the method; the program catches the exact error type at the link/use phase.

**Three `...IsLinkage=true` lines:** show the direct superclass relationships:
- `UnsupportedClassVersionError` has superclass `ClassFormatError`;
- `ClassFormatError` and `VerifyError` have superclass `LinkageError`.

### 8.4. Notes when modifying bytecode for illustration

The `locate` method finds **exactly one** byte sequence `1a 04 60 ac` across the entire classfile generated by `javac --release 17`. This is a simple approach with duplicate/missing checks for testing a short class. It is **not a general-purpose classfile parser**: changing the compiler, optimization/bytecode, or modifying the `addOne` method could make that byte pattern disappear.

In real systems, if bytecode needs to be modified, use a tool that understands the `Code` structure, constant pool, and `StackMapTable`, and run full verification/tests. The goal of the demo is **distinguishing errors**, not teaching production bytecode patching.

## 9. Second Demo: Compile with API v1, Run with API v2 Causing `NoSuchMethodError`

The example above shows errors right at definition/verification. Now let us distinguish that from **binary compatibility**: source code compiles cleanly, class files are all valid, but at runtime a dependency is provided whose method has changed.

Create the tree:

~~~text
src-v1/sample/Api.java
src-v2/sample/Api.java
src-client/sample/Client.java
~~~

### 9.1. API v1

**File `src-v1/sample/Api.java`:**

~~~java
package sample;

public final class Api {
    public static String greet() {
        return "hello-v1";
    }
}
~~~

### 9.2. API v2 no longer has method `greet()`

**File `src-v2/sample/Api.java`:**

~~~java
package sample;

public final class Api {
    public static String speak() {
        return "hello-v2";
    }
}
~~~

### 9.3. Client compiled **only against v1**

**File `src-client/sample/Client.java`:**

~~~java
package sample;

public final class Client {
    public static void main(String[] args) {
        System.out.println(Api.greet());
    }
}
~~~

The client bytecode has a symbolic method reference to `sample.Api.greet:()Ljava/lang/String;`. This code compiles when the compiler sees API v1. API v2 still has class `sample.Api`, but **has no method** named `greet` with that descriptor.

### 9.4. Build and run on Windows PowerShell

From the directory containing the three source trees:

~~~powershell
javac --release 17 -d build/v1 src-v1/sample/Api.java
javac --release 17 -d build/v2 src-v2/sample/Api.java
javac --release 17 -cp build/v1 -d build/client src-client/sample/Client.java
java -cp "build/v1;build/client" sample.Client
java -cp "build/v2;build/client" sample.Client
~~~

### 9.5. Build and run on Bash (Linux/macOS)

~~~bash
javac --release 17 -d build/v1 src-v1/sample/Api.java
javac --release 17 -d build/v2 src-v2/sample/Api.java
javac --release 17 -cp build/v1 -d build/client src-client/sample/Client.java
java -cp "build/v1:build/client" sample.Client
java -cp "build/v2:build/client" sample.Client
~~~

**With v1**, the program prints exactly:

~~~text
hello-v1
~~~

**With v2**, the program terminates with an error; the key line in the stack trace looks like:

~~~text
java.lang.NoSuchMethodError: ... sample.Api.greet() ...
~~~

The `...` indicates an **illustrative message**, not exact full stdout to match; the JVM may format descriptors and quotes differently. Testing confirmed the actual error type is **`NoSuchMethodError`**.

### 9.6. How is this different from "duplicate definition"?

In **each run** of the v1/v2 example, the app loader loads only **one** copy of `sample.Api` according to the provided classpath. There is no attempt to call `defineClass` twice in the same loader. The problem is that **the client binary requires a method that no longer exists in the runtime dependency**.

If you **recompile the client** against v2, `javac` will detect a source error because `Api.greet()` does not exist. However, the old client binary only surfaces the error at runtime when the JVM resolves/calls the method reference.

Prevention techniques: test **binary compatibility**, align dependency versions and classpath, and avoid distributing an old client with a new API that breaks the ABI. Renaming `greet` to `speak` is an API breaking change even if both methods perform similar business logic.

## 10. Distinguishing `ClassNotFoundException` and `NoClassDefFoundError`

Two names that are often confused:

- **`ClassNotFoundException`** is a **checked exception** from an explicit class lookup request such as `Class.forName("...")` or `ClassLoader.loadClass("...")` when the loader cannot find the requested name.
- **`NoClassDefFoundError`** is a **`LinkageError`**, occurring when the JVM cannot obtain a required class definition during linking/execution. For example, a binary is missing a dependency at runtime, the requested class name does not match the bytes, or a class entered an erroneous state after an initialization failure.

There is insufficient basis to infer backward that "`NoClassDefFoundError` always means the `.class` file is missing on disk". It can also involve the class loader, classpath/module path, a missing dependency *of* that class, or an initialization failure.

For example, a line `Class.forName("no.such.Plugin")` may throw `ClassNotFoundException` when no matching class exists; conversely, bytecode calling into a class that existed at compile time but is missing at runtime may throw `NoClassDefFoundError`. The two symptoms come from **how the JVM requests and resolves classes**, not merely the wording "class not found".

## 11. Diagnosing Errors in a Reproducible Order

### 11.1. Identify the actual artifact, class loader, and JVM

1. Record the **running `java` command**, `java -version`, `javac -version`, and runtime configuration in Docker/service/IDE/CI. The JDK used to build and the JRE/JVM used to run may not be the same version.
2. Identify which JAR/directory the class is being loaded from; check **classpath order**, module path, shaded/fat JARs, plugin bundles, and dependency versions.
3. Inspect the classfile header: `javap -verbose -classpath <path> com.example.Type`, looking for `major version`. For JARs, use `jar tf file.jar` to find the actual entry first.
4. If there is a custom loader, print the binary name and defining loader identity. Do not just print the class name. Suggestion:

~~~java
Class<?> type = someObject.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
System.out.println(type.getProtectionDomain().getCodeSource());
~~~

This snippet assumes `someObject` already exists and is only for **diagnostics in an authorized environment**; `getCodeSource()` can be `null` for dynamically generated classes, so it must not be treated as a field that always exists. Logs may expose internal paths — protect production logs appropriately.

### 11.2. Separate errors by type

| First symptom | Investigation direction |
| --- | --- |
| `LinkageError: attempted duplicate class definition` | Which loader called `defineClass` a second time? `findLoadedClass`/`loadClass`/race/parallel-capable? |
| `UnsupportedClassVersionError` | Major/minor of the class bytes vs. runtime; build JDK different from run JDK? Preview enabled? |
| `ClassFormatError` | Truncated/corrupted class bytes, jar corruption, constant pool/attribute patch? |
| `VerifyError` | Final bytecode, frames, stack/local types, classfile generator/agent/obfuscator |
| `NoSuchMethodError` or `NoSuchFieldError` | Which API was the client built against? What is the actual runtime dependency version/ABI? |
| `AbstractMethodError` | Interface/class contract changed while an old provider binary was not rebuilt? |
| `IllegalAccessError` | Runtime permissions changed, class/member modifiers, module exports? |
| `NoClassDefFoundError` | Required class missing at runtime, wrong-name, initialization failure, class loader topology |
| `ClassCastException` with the same binary name | Different defining loaders create different class identities; not necessarily a duplicate definition |
| `BootstrapMethodError` | Does the `invokedynamic` bootstrap/metafactory have a valid signature/linkage/permission? |

### 11.3. Useful diagnostic commands

~~~bash
java -version
javac -version
javap -verbose -classpath out com.example.Type
jar tf application.jar
~~~

`out`, `com.example.Type`, and `application.jar` are **example placeholder names for diagnostic operations**, not paths required to exist in the demo. On HotSpot JVMs supporting Unified Logging, `-Xlog:class+load=info` can be used to observe class loading, though log volume is large and syntax/support depends on the JVM.

Do not use `-noverify` or `-Xverify:none` to "fix" `VerifyError`. Aside from being restricted/deprecated in newer JDKs, disabling the verifier hides serious classfile bugs and does not produce valid bytecode. If using a bytecode enhancer/agent, fix the generator or build pipeline.

### 11.4. Loader/module problems that easily cause confusion

- **Multiple JAR versions with the same class:** the classpath usually picks the first one according to loader policy, rather than automatically defining both and causing a duplicate. However, mixed bytecode/JAR versions can lead to `NoSuchMethodError`.
- **Parent-first vs child-first:** changing the policy can create types with the same name in different loaders; the shared SPI area must be designed carefully.
- **JPMS package export/open:** manages accessibility by module, and does not replace classfile version checking or the bytecode verifier. You cannot solve `UnsupportedClassVersionError` with `--add-opens`.
- **Hot reload:** a new loader can load a class with the old name, but does not automatically turn objects from the old loader into the type of the new loader. Clean up resources and remove references holding the old loader before expecting class unloading.
- **Untrusted plugins:** class loaders/JPMS are not an OS sandbox; do not let being able to define a class imply permission to run arbitrary sensitive operations.

## 12. Building a Reliable Class Definition System

### 12.1. For a plugin manager

Design a **shared interface/contract** loaded in a loader where both host and plugin see the exact same `Class<?>`. Let the plugin loader handle implementation packages. When updating a plugin:

- Version the contract before releasing new artifacts.
- Load the new plugin into a controlled loader/module layer; do not redefine classes in the same loader.
- Verify artifacts before running: source, checksum/signature where appropriate, Java target version, dependency list, and permission policy.
- Keep the loader lifecycle clear; close resources, clear references/caches, and do not hold onto old thread context class loaders indefinitely.
- Log the class name/loader/module/actual artifact of errors; do not swallow `LinkageError` to continue using a "half-valid" class.

### 12.2. For a bytecode generator/agent

A pipeline can corrupt a classfile even if the original source is valid. Check in order:

1. Classfile version supported by the target JVM.
2. Magic, constant pool, and class/method/field structures.
3. Bytecode instruction semantics: stack height, types, locals, control flow.
4. `StackMapTable`/frames after inserting/removing branches or methods.
5. External references/ABI against the actual dependencies/runtime.
6. Automated testing **from the final class bytes** fed into the loader, not just source unit tests.

**Do not use the trick of patching the major byte to force running** an incompatible classfile. If you want to generate Java 17-compatible code, build from a compiler/bytecode generator targeting Java 17 and verify the APIs/bytecode techniques actually permitted.

### 12.3. For CI and releases

- Set up at least one **test step running on the minimum supported JVM**, not only compiling with `--release` on a higher JDK.
- Test clean runtime classpath/module path and build reproducibility; eliminate caches that skew artifacts.
- Add binary compatibility checks when a library has independent clients/plugins released earlier.
- For multi-release JARs (`META-INF/versions/...`), inspect the classfile of **the actual entry the JVM selects** for the corresponding release, not only the root entry.
- Document the release target, bytecode enhancement tool version, agent, and dependency compatibility in the release process.

## 13. Misconceptions to Avoid

1. **"Two loaders loading class X will definitely cause a duplicate."** False. Two independent defining loaders can create two different runtime types with the same name.
2. **"`Class.forName` calls `defineClass` every time."** False. Loaders have caching and delegation; repeated loads usually return the already loaded class.
3. **"`LinkageError` only occurs when a class does not exist."** False. The error family covers duplicates, version, malformed/invalid bytecode, ABI incompatibility, and many other situations.
4. **"`VerifyError` is a `ClassFormatError`."** False regarding hierarchy. Both are `LinkageError`, but `VerifyError` does not inherit from `ClassFormatError`.
5. **"`UnsupportedClassVersionError` just reports invalid Java source syntax."** False. It concerns the version of **the classfile being read by the JVM**.
6. **"Changing the major bytes down to 61 lets it run on Java 17."** False. The newer classfile may still use unsupported features/constant pool entries/APIs.
7. **"A successful `javac` command means runtime dependencies are all compatible."** False. `NoSuchMethodError` occurs when a v1 client binary encounters an incompatible v2 API.
8. **"`NoClassDefFoundError` and `ClassNotFoundException` are identical."** False. One is a LinkageError; the other is a checked exception from an explicit class lookup request.
9. **"`VerifyError` is always thrown at `defineClass`."** False. Depending on the point of linking/verification/active use, the error may surface differently.
10. **"Disabling verification or adding `--add-opens` fixes bad bytecode."** False and unsafe.
11. **"Same binary name means objects can be cast across different loaders."** False. Runtime type depends on the defining loader.
12. **"Hot reload = `defineClass` the same name a second time."** False. A new loader or instrumentation under its own rules is a different matter.
13. **"Catching `LinkageError` and ignoring it is fine."** False. It should be treated as a serious system/artifact error, its cause identified, and the execution path isolated.

## 14. Practice Exercises

**Exercise 1 — Error hierarchy:** Draw the relationship between `LinkageError`, `ClassFormatError`, `UnsupportedClassVersionError`, and `VerifyError`. Does `catch(ClassFormatError)` catch VerifyError? Why?

**Exercise 2 — Name and loader:** In `ClassDefinitionFailureDemo`, why is `first.getName().equals(peer.getName())` true while `first == peer` is false? If two objects are instantiated from the respective classes, can they be implicitly cast to each other?

**Exercise 3 — Duplicate definition:** Replace the second `firstLoader.defineRaw(good)` with `firstLoader.loadClass(first.getName())`, and observe which loader returns the class. Why might parent delegation cause the result to differ from `first`? Do not only compare class names.

**Exercise 4 — Version:** Use `javac --release 17` to build the demo and read major with `javap -verbose`. If you want to deploy on a Java 11 JVM (maximum major 55), what must be done besides changing major bytes?

**Exercise 5 — Verifier:** In the demo, how does changing `iadd` to `ladd` cause stack types to mismatch? Try removing the `getDeclaredMethod` call: does the JVM always throw `VerifyError` at the exact same line across all implementations?

**Exercise 6 — ABI:** With the `sample.Api` v1/v2 demo, explain why the client compiles with v1 successfully but fails with `NoSuchMethodError` when run with v2. Try recompiling the client with v2 to see the compile-time error and compare.

**Exercise 7 — Wrong name:** Write a `ClassLoader` subclass that calls `defineClass("other.Name", goodBytes, 0, len)` while the bytes actually contain `ClassDefinitionFailureDemo$Good`. Predict which `LinkageError` subtype appears.

**Exercise 8 — Loading diagnostics:** Given two plugin JARs containing the same `com.example.Spi` but defined in two loaders. Find a way to measure class identity and propose a loader hierarchy so host/plugin use one shared contract.

**Exercise 9 — CI compatibility:** Design a pipeline to validate a Java 17 artifact from build to deploy: `--release 17`, major check, runtime test on JDK17, binary compatibility check, and loader logging. Explain why all steps are needed.

## 15. Summary

- **A binary name in the same defining class loader can only be defined once.** Calling `defineClass` again is not a reload; it can cause `LinkageError`. Two different loaders can define the same name as **two different runtime types**.
- **`UnsupportedClassVersionError`** reports a classfile major/minor not supported by the JVM; **`ClassFormatError`** reports a corrupted classfile structure; **`VerifyError`** reports bytecode/type-state failing the verifier.
- **`UnsupportedClassVersionError extends ClassFormatError extends LinkageError`**, whereas **`VerifyError extends LinkageError`** directly.
- **`NoSuchMethodError`** is an example of a binary linkage error when a client uses an API per its compile-time version while runtime contains an incompatible API.
- Errors may surface during load, link, resolution, or active-use; investigate the **actual artifact and loader/JVM**, rather than guessing from a single stack trace location.
- Fix properly by aligning versions, improving class loader policies, and producing **valid classfiles/bytecode**, not by disabling verification.

## Official References (Java 17)

- [ClassLoader — `defineClass`, `loadClass`, `findLoadedClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [LinkageError — subclasses and general semantics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html)
- [UnsupportedClassVersionError — unsupported version](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html)
- [ClassFormatError — malformed classfile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html)
- [VerifyError — bytecode verifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html)
- [JVMS 17 `4.1 — ClassFile structure, version table](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [JVMS 17 `4.10 — Verification of class files](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10)
- [JVMS 17 `5.3–5.4 — Loading, Linking, Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JLS 17 Chapter 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [javac Java 17 manual — `--release`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
