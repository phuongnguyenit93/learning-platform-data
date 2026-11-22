# Distinguishing Compilation Errors from Linkage Errors Caused by Incompatible Libraries

A Java application may **compile successfully** today yet **fail to run** tomorrow if an accompanying library is replaced with an incompatible version. Conversely, a source file may **fail to compile** against a new library version while old class files still run if the library change is **binary compatible**. Therefore, in output validation, seeing `BUILD SUCCESS` or `.class` files is not enough to conclude that the entire application is ready to run.

This lesson distinguishes:

1. **Compile-time error**: `javac` cannot parse, type-check, resolve references, or accept the source program with the current classpath/module path.
2. **Linkage error**: the JVM loads/verifies/resolves classes and **symbolic references** already inside the class file, but the runtime environment does not provide a compatible definition.
3. **Runtime exceptions and application errors**: execution has reached program logic and caused an error such as `NullPointerException` or `IllegalArgumentException`; do not lump all runtime exceptions into linkage errors.
4. **Binary compatibility**: the extent to which a library change still allows **previously compiled** class files to continue linking properly.

The examples use Java 17+ and two versions of a library with the **same fully qualified class name**. Learners will see both the compiler's `cannot find symbol` error and the JVM's `NoSuchMethodError`, learn how to use `javap` to compare bytecode signatures, and build a safe release/library validation workflow.

## 1. Two Checking Moments and Two Perspectives

Suppose `demo.Main` calls `api.Greeter.message()`. During compilation, `javac` needs to read the library definition on the **compile classpath** to check types/methods; it writes a corresponding symbolic reference into the bytecode of `Main.class`.

At runtime, the JVM uses the **runtime classpath/module path and class loaders** to locate the definition of `api.Greeter` and resolve the reference to the method invoked by the bytecode. The JVM does not go back to read `Main.java` to automatically rename it or pick a similar method in library v2.

```text
SOURCE & COMPILE TIME                         RUNTIME
---------------------                         -------
src/demo/Main.java                           build/app/demo/Main.class
   |                                              |
   | javac -cp lib-v1                              | java -cp app:lib-v2
   v                                              v
lib-v1/api/Greeter.class (has message)     lib-v2/api/Greeter.class (no message)
   |                                              |
   v                                              v
javac resolves method successfully         JVM tries to resolve symbolic reference
   |                                              |
   v                                              v
Main.class contains message() call         NoSuchMethodError
```

Distinctions:

| Question | `javac` when compiling source | JVM when running class file |
| --- | --- | --- |
| Primary input | `.java` + dependency classes/modules | `.class` + runtime dependencies |
| Where methods/fields/types are looked up | Compile classpath/module path, source path | Runtime classpath/module path, class loaders |
| When a method is missing | Diagnostic such as `cannot find symbol` | `NoSuchMethodError` when the corresponding reference is resolved |
| When access is insufficient | Compile-time access error | `IllegalAccessError` if an old binary uses a member that is no longer accessible |
| When the class file is too new | Older compiler may report `bad class file / wrong version` | `UnsupportedClassVersionError` from a VM not supporting the format |
| When checks succeed | `javac` returns exit code 0; output may be generated | Does not guarantee every runtime path will execute successfully |
| When errors appear | During parse/enter/analyze/compile | Possibly at load, verify, resolve, or only when the relevant code branch is executed |

**Note on timing:** The JVM specification allows **lazy or eager resolution** within defined limits. You should not assert that `NoSuchMethodError` *always* appears right at startup or *always* at an exact specific `invokevirtual` instruction across every JVM. A linkage error may only surface when the program first uses a class or member.

## 2. How Do ABI and Binary Compatibility Differ from Source Compatibility?

**API** is the interface that programmers use at the source level; **ABI** (Application Binary Interface) describes what a **binary client** relies on after compilation: class/interface identity, member name, access flags, JVM descriptors, static/instance distinction, inheritance, and related metadata.

In Java, a class file has a **constant pool** containing symbolic references. For example, source code:

```java
String text = api.Greeter.message();
```

usually leads to a bytecode reference such as:

```text
invokestatic api/Greeter.message:()Ljava/lang/String;
```

This is an **abbreviated illustrative disassembly**, not the full output of `javap`. It shows that the JVM requires a method with:

- Owner class: `api/Greeter`.
- Name: `message`.
- Descriptor: `()Ljava/lang/String;`, meaning **no parameters, returning `java.lang.String`**.
- Invocation form: `invokestatic`, meaning the compiler believed this was a **static** method.

If library v2 only has `message(int)` or `text()`, the JVM does not automatically rewrite the symbolic reference in `Main.class` to the new name/descriptor. If the client is **recompiled** against API v2, `javac` will re-check and emit a diagnostic as soon as the source is no longer valid.

### Three Compatibility Properties to Separate

| Property | Question | Illustration |
| --- | --- | --- |
| **Source compatibility** | Can old client source code still compile against the new API? | Renaming a method causes source calling the old name to fail |
| **Binary compatibility** | Can an **unrecompiled** client class file link against the new library? | Removing an old method leads to `NoSuchMethodError` |
| **Behavioral compatibility** | Does the program still perform the expected behavior? | The method still exists but changes its result/state, not necessarily causing a linkage error |

**Binary compatibility does not mean behavioral compatibility.** A library can keep method signatures intact so all old classes continue linking, while changing outputs, side effects, exceptions thrown by the method body, or thread safety policies. Release validation requires both ABI checks and functional tests.

## 3. Complete Java 17 Example: Library v1, Application, Library v2

To accurately reproduce the difference, we create **two independent versions of the same class `api.Greeter`** and **one client `demo.Main`**.

### 3.1. Initial Source Tree

```text
project/
└── src/
    ├── v1/
    │   └── api/
    │       └── Greeter.java
    ├── v2/
    │   └── api/
    │       └── Greeter.java
    └── client/
        └── demo/
            └── Main.java
```

**`src/v1/api/Greeter.java`:**

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "library-v1";
    }
}
```

**`src/v2/api/Greeter.java`:**

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    // Method message() was removed in this version.
    public static String replacement() {
        return "library-v2";
    }
}
```

**`src/client/demo/Main.java`:**

```java
package demo;

import api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

These are **three separate files**; do not copy all three classes into a single `.java` file. The two `Greeter.java` files with the same package/class name **must not be compiled together into one output directory**; we select **one version at a time**. Separate output directories keep the experiment from mixing class files.

### 3.2. Compile Library v1 and the Client with Java 17

In the `project` directory:

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v1 src/v1/api/Greeter.java
javac --release 17 -encoding UTF-8 -cp build/lib-v1 -d build/app src/client/demo/Main.java
```

A successful compilation command usually prints no stdout. Expected result:

```text
build/
├── lib-v1/
│   └── api/Greeter.class
└── app/
    └── demo/Main.class
```

**Run with library v1.**

Linux/macOS (`:` classpath separator):

```sh
java -cp build/app:build/lib-v1 demo.Main
```

Windows PowerShell or cmd (`;` classpath separator):

```powershell
java -cp "build/app;build/lib-v1" demo.Main
```

**Exact stdout:**

```text
library-v1
```

This proves the compiler read API v1, the client binary was able to call `message()`, and the runtime at that moment contained the matching library version.

### 3.3. Compile Library v2 Separately, Without Recompiling the Client

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v2 src/v2/api/Greeter.java
```

Inspect the methods in both versions:

```sh
javap -classpath build/lib-v1 -p -s api.Greeter
javap -classpath build/lib-v2 -p -s api.Greeter
javap -classpath build/app -c demo.Main
```

In v1, the relevant part is equivalent to:

```text
public static java.lang.String message();
  descriptor: ()Ljava/lang/String;
```

In v2, the relevant part is equivalent to:

```text
public static java.lang.String replacement();
  descriptor: ()Ljava/lang/String;
```

In `Main.class`, the bytecode has a reference to **`api.Greeter.message:()Ljava/lang/String;`**. Actual `javap` output also includes constant-pool indices, offsets, and other information; the snippets above are **content excerpts**, not a guarantee of exact formatting.

Now **run the old client with library v2**:

Linux/macOS:

```sh
java -cp build/app:build/lib-v2 demo.Main
```

Windows:

```powershell
java -cp "build/app;build/lib-v2" demo.Main
```

**Result:** The JVM throws **`java.lang.NoSuchMethodError`** when the old method reference is resolved. The message usually specifies the `api.Greeter.message()` signature:

```text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String api.Greeter.message()'
```

This is a **typical representative line**, not the full mandatory stderr; stack trace, quotes, and wording may vary by JDK. What matters is the **exception type**, the class/member name, and the descriptor requested by the client.

Because this is a **linkage error caused by an incompatible ABI**, `Main.java` has not been modified, `Main.class` still exists, and compilation previously succeeded. Replacing the library at runtime is the root cause.

### 3.4. Recompile the Old Client Against Library v2: Now a Compile Error

Keep `src/client/demo/Main.java` unchanged, but recompile it against API v2:

```sh
javac --release 17 -encoding UTF-8 -cp build/lib-v2 -d build/app-v2 src/client/demo/Main.java
```

**Expected result:** `javac` fails because the current `api.Greeter` class has no `message()` method. A diagnostic snippet usually indicates:

```text
error: cannot find symbol
  symbol:   method message()
  location: class api.Greeter
```

This is a **diagnostic excerpt**, not a guarantee of the full verbatim text, line numbers, or error count across all compilers. With this command, the compiler **was able to read** `Greeter.class` v2 (same class-file major 61), but the source no longer matches the API.

**Conclusion of the experiment:** *The same library change — removing the `message()` method — leads to errors at two different stages*:

| Case | What is being checked | Error |
| --- | --- | --- |
| `javac` compiles `Main.java` with lib-v2 | **Source compatibility** | `cannot find symbol: method message()` |
| `java` runs old `Main.class` with lib-v2 | **Binary compatibility** | `NoSuchMethodError` |
| `java` runs old `Main.class` with lib-v1 | API/ABI still matches | Prints `library-v1` |
| Edit `Main.java` to call `replacement()` and compile with lib-v2 | Client and library share the new API | Compiles; must test runtime separately |

### 3.5. Proper Fixes

One of two sustainable approaches:

**Preserve binary compatibility for old clients** by re-providing the method in library v2:

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    /** @deprecated Use replacement() in new code. */
    @Deprecated
    public static String message() {
        return replacement();
    }

    public static String replacement() {
        return "library-v2";
    }
}
```

This is a **complete replacement version** for `src/v2/api/Greeter.java`. When library v2 is rebuilt with `message()` included, old client binaries can link against it. The output becomes `library-v2` due to the new implementation, even though binary compatibility is preserved.

**Or proactively upgrade the client**: update `Main.java` to use `Greeter.replacement()`, recompile against library v2, and ensure the runtime packages lib-v2. Updating the client is a breaking-change migration; you cannot simply bump the version number while skipping recompilation and other binary clients.

## 4. Second Example: Changing a Static Method to an Instance Method

A common ABI change that is sometimes harder to spot than removing a method is changing **`static` to instance**. Suppose the binary client was compiled against:

```java
public static String message()
```

If the new library still has a method with the same name and return type but drops `static`:

```java
package api;

public final class Greeter {
    public Greeter() {
    }

    public String message() {
        return "instance-v3";
    }
}
```

This is the **complete content of another `Greeter.java` version**, so compile it into a separate `build/lib-v3` rather than putting it in the same directory as v1/v2:

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v3 src/v3/api/Greeter.java
```

The command above assumes you saved the source at **`src/v3/api/Greeter.java`**. If you run `Main.class` compiled with v1 while the runtime provides v3, the JVM throws **`IncompatibleClassChangeError`** because the bytecode uses `invokestatic` whereas the runtime method is an instance method. It cannot be resolved by "finding a method with the same name": **the static/instance distinction is part of the binary contract**.

Conversely, if you **recompile the old `Main.java` source** against lib-v3, the compiler rejects `Greeter.message()` being invoked statically from the class name and emits a diagnostic similar to "non-static method cannot be referenced from a static context." Two different paths from the same API/ABI change.

**Note:** `IncompatibleClassChangeError` is the superclass of several other linkage errors such as `NoSuchMethodError` and `NoSuchFieldError`; when the JVM reports a specific error, keep the **actual subclass name** instead of writing only a generic "incompatible class."

## 5. Important Linkage Errors When Upgrading or Replacing Libraries

| JVM Error | A typical compatibility cause | Example change |
| --- | --- | --- |
| `NoSuchMethodError` | Binary calls a method/constructor whose name + descriptor can no longer be resolved | Deleting a method, changing the return type or parameter types |
| `NoSuchFieldError` | Field referenced by old binary no longer exists with that name + descriptor | Deleting/changing a field's type, no matching field remains |
| `IllegalAccessError` | A previously accessible class/member is no longer accessible at runtime | Reducing visibility; changing module `exports` |
| `IncompatibleClassChangeError` | A class/member changed kind incompatibly and cannot satisfy the instruction/linking | `static` ↔ instance; certain class/interface/inheritance changes |
| `AbstractMethodError` | Binary attempts to call a method for which runtime has no valid concrete implementation | Changing a concrete method to abstract or implementation incompatibility |
| `NoClassDefFoundError` | VM needed a class definition but could not find/initialize it in the loading context | Runtime missing a transitive dependency or class initialization failed |
| `UnsupportedClassVersionError` | VM does not support the class-file major/minor version | Library built with `--release 21` running on Java 17 |
| `VerifyError` | JVM verifier finds class files do not satisfy verification rules | Changed binaries/transformers/libraries producing invalid bytecode |

**`LinkageError` is a branch of `Error`, not an ordinary `Exception`.** Using `catch (Exception e)` **does not** catch `NoSuchMethodError`. Although `catch (LinkageError e)` may be used at a plugin diagnostic boundary, normal applications **should not treat a linkage error as a simple recoverable business error**. It usually indicates an incorrect environment/deployment/classloader and requires fixing artifact versions.

### `ClassNotFoundException` Is Not the Same as `NoClassDefFoundError`

`ClassNotFoundException` is a **checked exception** commonly encountered when code requests loading a class by name, such as:

```java
Class.forName("com.example.Missing")
```

This is an **illustrative expression**; running it standalone requires a surrounding class/method and handling the checked exception.

`NoClassDefFoundError` is a **`LinkageError`** that occurs when the VM needs to define a class referenced by a binary but no suitable definition is found; it can also appear after a prior class initialization failure (often accompanied by "Could not initialize class"). Do not infer "missing class name" as the sole symptom: check the cause and root cause in the logs.

### `ExceptionInInitializerError` and Subsequent `NoClassDefFoundError`

If a class's static initializer throws a runtime exception, the JVM may report `ExceptionInInitializerError` the first time. When the program tries to use the class again after initialization failed, the JVM may report `NoClassDefFoundError` because the class is in a failed initialization state. This is not the same scenario as renaming/removing a method in a JAR; check the **initial cause**.

### Class-File Version Is an Independent Axis from ABI

`UnsupportedClassVersionError` can occur even when method names are completely compatible, if the JVM **cannot read the `.class` format**. For example, Java 17 typically supports major 61; Java 21 classes have major 65. Setting `--release 17` on the **app itself** does not automatically convert major 65 class files inside a library.

You need to separate:

- **Is the class file format supported?**
- **Can the class/library be found and loaded?**
- **Do symbolic references resolve properly?**
- **Are access rights and classloader/module rules satisfied?**
- **Are the method body/runtime behavior correct?**

An application may pass several steps yet fail at another.

## 6. Inspecting with `javap`: Method Name, Descriptor, and Opcode

For the v1/v2 experiment in section 3:

```sh
javap -classpath build/lib-v1 -p -s api.Greeter
javap -classpath build/lib-v2 -p -s api.Greeter
javap -classpath build/app -c -p demo.Main
javap -classpath build/app -v demo.Main
```

Meaning:

| Command | Used to verify |
| --- | --- |
| `javap -p` | Whether public/private members still exist or have disappeared |
| `javap -s` | JVM method/field descriptors, especially return type/parameter types |
| `javap -c` | Bytecode instructions `invokestatic`, `invokevirtual`, `getstatic`, etc. |
| `javap -v` | Constant pool symbolic references and detailed flags/attributes |

In Java source, **method signature** usually refers to name + parameter types. However, in a **JVM method descriptor**, the **return type is also encoded**. Changing the return type, even when the source call ignores the return value, can leave old binary clients calling the missing descriptor and throwing `NoSuchMethodError`.

Example:

```java
// v1
public static int count() { return 3; }

// v2
public static long count() { return 3L; }
```

These are **two illustrative snippets from two library versions**, not a standalone source file that can place both in one class. The v1 descriptor is `()I`, and the v2 descriptor is `()J`; an old binary requesting `()I` will not be updated automatically.

### Note on Fields with Compile-Time Constants

A misleading case is:

```java
public static final int LIMIT = 10;
```

If `LIMIT` is a **constant variable** inlined by the Java compiler into the client binary, the client may **not need** `getstatic` to read it; changing `LIMIT` in the new library can leave the old client still using the **value 10** instead of reporting `NoSuchFieldError`.

To use an experiment where field linkage is easily observed, choose a field that is **not a compile-time constant**, such as:

```java
public static int counter = 7;
```

In that case, the client normally uses `getstatic` to access it. If v2 removes/changes the field while running the old client class, `NoSuchFieldError` can appear. Do **not** draw conclusions about fields from an example of a primitive/String constant inlined at compile time.

## 7. Distinguishing Compiler Errors from Runtime Errors in Real Pipelines

A real build pipeline usually has multiple steps:

```text
Dependency resolution
       |
       v
Compile source -> annotation processing -> output classes
       |
       v
Package JAR/WAR/container
       |
       v
Deploy / JVM loading / linking
       |
       v
Runtime execution and tests
```

Each step produces different errors:

| Phase | Example errors | Clue |
| --- | --- | --- |
| Download/resolve dependency | Artifact not found, version conflict | Maven/Gradle repository and dependency graph |
| Compile source | `cannot find symbol`, incompatible types, module not readable | `javac` diagnostics, compile classpath |
| Compile reading class file | `bad class file: wrong version` | JDK compiler and target/format of the dependency |
| Package | Missing JAR in bundle, wrong shade relocation, wrong manifest/module path | Inspect packaged artifact |
| JVM load/link | `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError` | Runtime classpath/classloader and ABI |
| JVM execute | `NullPointerException`, wrong output, race condition | Runtime state and application logic |

Do not jump to conclusions from keywords like "class" or "method" in a message. **Timing** and the **full error type** matter more.

### Why Does Compilation Succeed Yet CI Still Fails?

For example, suppose a project has:

- `compileClasspath` carries `library:1.0` with `message()`.
- `runtimeClasspath` carries `library:2.0` without `message()` because another dependency forces the version.
- `Main.class` is compiled against v1, so compilation passes.
- Integration tests or the server run with v2 and call the old method → `NoSuchMethodError`.

If you only inspect the `compileJava` log, you will not catch it. You must compare the **effective compile classpath** and **effective runtime classpath** after dependency mediation/overrides, not just the version declared on a single line of a build file.

### The Runtime Class Loader May Pick a Different Class Than Expected

Application servers, IDEs, plugins, OSGi, servlet containers, or shaded/fat JARs can have multiple classloaders. An `api.Greeter` class may be loaded from a **different JAR** than the file you just inspected with `javap`.

When running standard Java 9+, you can use class-loading logging to aid investigation:

```sh
java -Xlog:class+load=info -cp build/app:build/lib-v2 demo.Main
```

The `-Xlog` output **is very verbose and JVM/JDK-dependent**; look at the line for `api.Greeter` and the code source location. Do not paste the entire log into a unit test for byte-by-byte comparison. For apps with Java agents or custom class loaders, logging may need additional configuration.

In addition, you can inspect the class source after loading:

```java
System.out.println(
    api.Greeter.class.getProtectionDomain()
        .getCodeSource().getLocation());
```

This is a **snippet** inside an application that has successfully loaded the `api.Greeter` class, not a standalone file. `getCodeSource()` can be `null` depending on the classloader/security context; null checks are needed in real code. If the class cannot be loaded due to `UnsupportedClassVersionError`, even accessing the class literal/reflecting is not a reliable debugging mechanism.

## 8. How Do Common Library Changes Affect Compatibility?

| Library change | Old source client (recompiled) | Old binary client (not recompiled) |
| --- | --- | --- |
| Remove a called `public` method | Fails to compile | May throw `NoSuchMethodError` |
| Rename a method | Fails to compile if still using the old name | May throw `NoSuchMethodError` |
| Change parameters/return type | Usually fails to compile if call no longer matches | May throw `NoSuchMethodError` because the descriptor changed |
| Reduce `public` visibility to package-private/private | Source outside the package/module fails to compile | May throw `IllegalAccessError` |
| Change method static ↔ instance | Old source may fail to compile | May throw `IncompatibleClassChangeError` |
| Change concrete method to abstract | Source may fail depending on class hierarchy | May throw `AbstractMethodError` when invocation requires an implementation |
| Remove non-constant public field | Old source fails to compile | May throw `NoSuchFieldError` |
| Add a new overload | May make recompilation ambiguous or select another overload | Old binary usually keeps the previously chosen reference |
| Change `throws` clause | Source compatibility may change | **Does not by itself break binary compatibility** since checked exceptions are checked at compile time |
| Change method body, keeping descriptor and access | Recompilation usually succeeds | Usually remains binary compatible, though behavior may change |
| Add a new method | Old client source usually still compiles | Usually binary compatible; there are exceptions/effects in hierarchies |
| Change module exports/opens | Source/client access may fail | May cause access/linkage or reflective-access errors depending on context |

The table is only a **guideline**; JLS Chapter 13 analyzes many cases involving inheritance, interfaces, generic erasure, default methods, overloaded methods, sealed types, enums, and constants. Do not treat one small example as an absolute rule for every class hierarchy.

### ABI of Generics

In the JVM, generic type parameters mostly undergo **erasure**. A change in the source generic signature can affect source compatibility while the post-erasure descriptor remains unchanged. Conversely, changing a bounded type so that erasure changes can impact the descriptor and ABI.

**Bridge** methods may be generated by the compiler to preserve overriding after erasure or covariant returns. When inspecting with `javap -v`, you may encounter `ACC_BRIDGE` and `ACC_SYNTHETIC`. Do not strip bridge/helper methods with bytecode tools just because they are "not in the source"; binary clients may require them.

### Enum and Constant Inlining

Adding an enum constant is generally considered binary compatible by the JLS, but exhaustive `switch` behavior or client logic can change. Reordering constants can also skew data relying on `ordinal()` even without a linkage error. Binary compatibility is one aspect, **not a complete behavioral validation result**.

## 9. Module Path, Classpath, and Compatibility of Runtime Dependencies

In Java 9+, the environment may include:

- **Classpath:** unnamed module, where class names are resolved according to class loader/classpath order.
- **Module path:** explicit named/automatic modules, with readability/exports/resolution checks.
- **Multiple class loaders/layers:** for example, a plugin system or application server.

If `javac` is not permitted by a module to read a package, it may emit diagnostics like `package ... is not visible` or `module ... does not read ...`. If the runtime module graph differs from compile-time, code can encounter errors during resolution/loading/access checks. **Do not assume every JPMS error is `NoSuchMethodError`**.

**Qualified exports** and `opens` should be distinguished: `exports` allows conditional public Java access to a package; `opens` allows deep reflection at runtime. A reflection framework hitting `InaccessibleObjectException` is not the same issue as a binary client calling a removed method.

### Direct and Transitive Dependencies

Suppose library `A` depends on `B`; the application only declares `A`, while runtime is missing `B` or has a different version of `B`. When the compiler compiles with full `A+B` but deployment omits `B`, the error may only appear when code in `A` calls into `B`.

To investigate, inspect all of:

1. **Direct dependency:** the version of `A` that the client was compiled against.
2. **Transitive dependencies:** the versions of `B`, `C`, ... present in the compile/runtime graph.
3. **Dependency mediation:** final version selection rules of Maven/Gradle, exclusions, constraints.
4. **Shading/relocation:** classes packaged with new/old packages, duplicate classes.
5. **Deployment class loader:** which JAR from the application or container/shared libs is selected.

Renaming JARs or editing `CLASSPATH` arbitrarily may mask errors but does not solve provenance/ABI issues.

## 10. Inspection Tools: From Small Commands to CI Testing

### Check the JDK Used to Compile and Run

```sh
javac -version
java -version
```

The two versions can differ if the build tool uses a separate Java toolchain. When a class file is compiled with a newer JDK than the JVM supports, `UnsupportedClassVersionError` is related to the **class-file version**, not directly caused by a removed method. Check with:

```sh
javap -verbose -classpath build/lib-v2 api.Greeter
```

The Java 17 class-file major version is **61**; Java 21 is **65**. Setting `--release 17` on the application does not automatically convert a dependency built for Java 21 into class-file major 61.

### Verify the Exact Symbolic Reference

```sh
javap -c -p -classpath build/app demo.Main
javap -p -s -classpath build/lib-v1 api.Greeter
javap -p -s -classpath build/lib-v2 api.Greeter
```

Focus on:

- Method name and JVM descriptor.
- The client's `invokestatic`/`invokevirtual`/`invokeinterface` opcode.
- Does the method actually exist in the runtime library?
- Are the public/private/protected/static access flags still compatible?
- Have the owner class and inheritance path changed?

Do not just visually compare the text `public String message()` in source; the class file descriptor and how the JVM resolves it determine binary linkage.

### Inspect the Build Tool's Dependency Graph

Some common commands (must be run in a real project with the tool installed):

```sh
mvn dependency:tree
```

For Gradle:

```sh
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-lib --configuration runtimeClasspath
```

These are **command templates**; `example-lib` must be replaced with the real dependency name, and `runtimeClasspath` depends on the plugin/project. On Windows, `gradlew.bat` can be used. Check both compile and runtime configurations when suspecting a version mismatch.

**A dependency tree shows resolution**, and does not always prove which JAR the JVM actually loads when container classpaths, fat JARs, custom loaders, or agents are involved. Use class-loading logs as a supplement when needed.

### How Does `jdeps` Help?

`jdeps` analyzes static dependencies from class/JAR files and can help detect module/class dependencies:

```sh
jdeps --class-path libs/* build/app
```

This is an **illustrative command template**: wildcard expansion/classpath syntax varies by shell, and the tool must receive the actual files/JARs. `jdeps` does not replace full method/field ABI checking, especially with reflection and custom classloaders.

## 11. Building a Validation Pipeline That Covers Both Compile-Time and Runtime

To detect incompatibilities early, do not just run `javac` on source:

### Step 1 — Lock Down the Target Runtime

For example, suppose the application commits to running on Java 17. Record the JDK compiler version, `--release 17` target, and minimum JVM in the build configuration. A release that only runs on Java 21 must be announced as raising the minimum Java version, rather than keeping a "Java 17 compatible" label.

### Step 2 — Build a Reproducible Dependency Graph

Use version pinning/constraints/lockfiles appropriate for your build tool. Avoid solutions that silently change libraries between compilation and packaging/deployment. Verify transitive dependencies.

### Step 3 — Run Compile Tests Against the Expected API

Recompile the application with the **exact dependency version expected to be packaged**. This step catches source errors: removed methods/fields, new access modifiers, and generic APIs that no longer match.

### Step 4 — Run Binary Compatibility Tests

If released clients must be supported, keep **old client binaries** and run them against the **new library**. Do not recompile the old client in this test, because recompiling changes the question being answered. Suitable API/ABI diff tools can be used to assess breaking changes, but runtime tests are still required.

### Step 5 — Test the Final Packaged Artifact

Run integration/smoke tests with the **target JVM** along with the JAR/WAR/container that production receives. Check for class-loading failures along code paths that use critical APIs; do not just invoke main and exit.

### Step 6 — Tie Causes to Evidence

If `NoSuchMethodError` occurs, log at a minimum:

- Exception class and full member signature from the error.
- Stack trace showing where the reference was used.
- Runtime JDK version.
- Module/class loader name and code source of the involved class when possible.
- Packaged artifact versions/hashes/paths; are there classes with duplicate names?
- `javap -s` output of the **old client** and the **actual runtime library**.

Only from there should you decide whether to restore the binary API, recompile the client, upgrade/downgrade the library, or fix dependency resolution.

## 12. Diagnosing by Error Type: Choosing the Right Next Step

| Sign in logs | First step to take |
| --- | --- |
| `error: cannot find symbol` | Verify source imports/methods/fields, compile classpath, and current API |
| `package ... is not visible` | Check module readability/exports and access permissions |
| `bad class file: wrong version` | Compare `javac -version` with the dependency's class-file major version |
| `NoSuchMethodError` | Run `javap` on method owner/name/descriptor of caller and runtime callee, compare JAR versions |
| `NoSuchFieldError` | Inspect JVM field descriptor, constant inlining, and runtime owner class |
| `IllegalAccessError` | Check visibility, module exports, classloader identity, and descriptor |
| `IncompatibleClassChangeError` | Check static/instance distinction, class/interface kind, and hierarchy |
| `AbstractMethodError` | Check the actual interface/class implementation and compiled library |
| `NoClassDefFoundError` | Check missing transitive JAR, class name, and initialization failure cause |
| `UnsupportedClassVersionError` | Check classfile major/minor, build/runtime JDK, and preview features |
| Runs at runtime but produces wrong output | Test behavioral/API contract, data, and dependency semantics; do not blame the linker without evidence |

### An 8-Question Debugging Workflow

1. **Is the error in `javac` or `java`?** Which command log failed?
2. **Which specific class does the error belong to?** Compile diagnostic, `LinkageError`, or application exception?
3. **Which class/method/field is requested?** Record the exact name and descriptor if available.
4. **Which artifact was the client binary compiled against?** Do not guess just from a version in a POM file.
5. **Which artifact does the runtime actually load?** Inspect the classpath/module path/classloader.
6. **Where did the ABI between the two artifacts change?** Use `javap -p -s -v` when needed.
7. **Can the difference be fixed in the client or the library?** Restore the API or recompile and package consistently.
8. **After fixing, have both the old binary and packaged runtime been tested?** Do not just re-run compilation.

## 13. Some Misconceptions That Can Cause Broken Releases

**"If compilation succeeded, runtime linking is guaranteed to succeed."** False. Bytecode references symbolic members checked by the resolver at runtime, in an environment that may contain a different dependency version.

**"`NoSuchMethodError` is an `Exception`, so catching `Exception` will catch it."** False. It is a `LinkageError`. The proper fix is resolving the artifact mismatch, not wrapping errors in a generic try-catch.

**"Just updating the app's source to adapt keeps all old clients safe."** False. If you publish a public library, unrecompiled old binaries can still call the old method descriptor. Binary compatibility must be evaluated separately.

**"The compiler will replace the old method with a similarly named method in the new JAR."** False. Resolution strictly follows the method owner, name, and descriptor contained in the client binary; compiler overload resolution already occurred when compiling the old client.

**"Every public API change breaks old binaries."** False. Adding an overload can be binary compatible; changing a method body or `throws` clause does not by itself break binary compatibility, although source/behavior may change.

**"Changing a `static final int` and seeing the old client still run means the linker picked the new version."** Not necessarily. The compiler may inline the constant into the client so the field is not resolved at runtime; the old client still retains the old value.

**"IDE and production classpaths are always identical."** False. Test runners, servers, Gradle/Maven, fat JARs, and containers can pick different dependencies/classloaders.

**"Every `NoClassDefFoundError` is due to a missing JAR."** False. It can also involve an initialization failure or a deeper cause; read the cause.

**"Changing the class-file major version with a hex editor will fix incompatibilities."** False. The class format may contain constructs that older JDKs do not understand; changing the header does not validly convert bytecode or ABI.

**"Linkage errors must appear immediately at startup."** False. The JVM may defer resolution; tests must cover code paths.

## 14. Pre-Release Verification Checklist

- [ ] Has client source been recompiled against the dependency versions the release actually uses?
- [ ] Do final class files/JARs have a target major version compatible with the minimum JVM?
- [ ] Have compile classpath and runtime classpath been compared after dependency resolution?
- [ ] Have transitive dependencies, shaded classes, and module/classloader paths been checked?
- [ ] If old clients are supported, have tests been run **without recompiling old binaries** against the new library version?
- [ ] Have method/field JVM descriptors and access/static flags been checked for public ABI changes?
- [ ] Have generic erasure, bridge methods, and inlined compile-time constants been reviewed?
- [ ] Have source compatibility, binary compatibility, and behavioral compatibility been distinguished?
- [ ] Have integration tests been run on the **packaged artifact** with the target Java runtime?
- [ ] Does CI not rely solely on `javac` exit code, and include runtime smoke tests on critical flows?
- [ ] Is enough information logged from `NoSuchMethodError`/`IllegalAccessError` to identify the binary caller and actual callee?
- [ ] If making incompatible API changes, is there a migration/versioning plan or compatibility shim?
- [ ] Has the build/test been re-run from a clean output directory to avoid stale class files masking errors?

**Key takeaway:** *Compilation errors* indicate that the current source code does not match the libraries `javac` sees. *Linkage errors* indicate that the JVM cannot satisfy references recorded in an **old binary** using the classes/members actually present at runtime. To verify library compatibility, compare **the source API, class-file ABI, and runtime artifact graph**, rather than taking a single successful compilation as sole proof.

## Official References

- Java Language Specification 17, **Chapter 13 — Binary Compatibility**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Java Virtual Machine Specification 17, **Chapter 5 — Loading, Linking, and Initializing**, especially `5.4` Resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java SE 17, API **`LinkageError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java SE 17, API **`NoSuchMethodError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
- Java SE 17, API **`UnsupportedClassVersionError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html
- Oracle JDK 17, **`javap` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle JDK 17, **`javac` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html