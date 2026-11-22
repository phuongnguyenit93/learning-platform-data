# Declaring the JNI Version Required by a Library

## 1. Why Does a JNI Library Need to Declare a Version?

A native library (C/C++) loaded via `System.loadLibrary` or `System.load` may need **Java Native Interface (JNI)** functions that only appeared starting from a certain JNI version. The JVM needs to know the **minimum JNI interface level** the library relies on in order to decide whether it can accept that library.

For **dynamically linked libraries**, the standard way to declare this is to export a function with the exact name **`JNI_OnLoad`** from the `.so`/`.dylib`/`.dll` file:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
```

This snippet is a **complete C function**, though not yet a self-contained shared library for Java to call native methods; section 6 has the full Java code, C code, and compile/run commands. Returning `JNI_VERSION_1_6` from the function means **“the library requires the JNI interface at level 1.6 or higher”**, not “runs only on JDK 6”, nor does it require the JVM to report back a JNI version equal to 1.6.

**Key takeaways:**

- `JNI_OnLoad` is a **library lifecycle hook**, not a `native` method declared in a Java class.
- The JVM calls the hook while **loading the native library**, before the successful loading step completes.
- The library returns a **JVM-recognized `JNI_VERSION_*` constant** for the JNI level it needs to use.
- If the JVM does not recognize the version returned by `JNI_OnLoad`, the JVM **rejects and aborts loading the library**, treating it as if the library was not loaded.
- If a dynamic library **does not export `JNI_OnLoad`**, per the specification the JVM assumes the library only requires `JNI_VERSION_1_1`. That is a legacy compatibility convention, **not** a recommendation to omit the declaration for modern libraries.

This lesson focuses on **how to declare, choose, check, and handle the JNI version** in the library lifecycle, without confusing it with the Java source/bytecode version or the operating system.

## 2. Distinguishing Three Easily Confused Version Concepts

| Concept | Example | What determines it? | What is it used for? |
| --- | --- | --- | --- |
| JDK/JVM version running the application | JDK 17, 21, 24 | The runtime installed and running the Java program | Determines the Java API, JVM, and JNI actually supported |
| Language/class file version | Java `--release 17`, class file version 61 | Compiler configuration and target runtime | Determines whether Java code runs on the corresponding JVM |
| **JNI version required by the library** | `JNI_VERSION_1_6`, `JNI_VERSION_1_8` | Declared by the library developer in `JNI_OnLoad` | Requests the JNI API level the library depends on |

For example, **JDK 17** can load a C library that declares **`JNI_VERSION_1_6`**: the library only requires a set of JNI functions that have existed since that level. There is no need to change it to “`JNI_VERSION_17`”; on JDK 17, `JNIEnv::GetVersion()` actually returns **`JNI_VERSION_10`**, because JNI interface version numbering does not necessarily increment with every Java SE release.

That means:

- `JNI_VERSION_1_6` does **not** mean “requires Java 6 equal to 6”.
- `JNI_VERSION_1_8` is **not** a Java compiler configuration flag.
- `JavaVM::GetEnv(..., JNI_VERSION_1_6)` requests obtaining the JNI level 1.6 interface on the current thread; it is **not** a command to load a library or start a JVM.
- `System.getProperty("java.version")` reports the Java runtime version; it **does not replace** `JNIEnv::GetVersion()` and must not be used to invent `JNI_VERSION_*` constant names.
- `--enable-native-access=...` in newer JDKs is **native access permission**, not the JNI version to declare.

## 3. `JNI_VERSION_*` Constants and How to Choose

The constants are defined in `jni.h` of the corresponding JDK. The levels commonly needed to know:

| Constant | Hex value | Description |
| --- | --- | --- |
| `JNI_VERSION_1_1` | `0x00010001` | JNI 1.1 (legacy compatibility level) |
| `JNI_VERSION_1_2` | `0x00010002` | JNI 1.2 |
| `JNI_VERSION_1_4` | `0x00010004` | JNI 1.4 |
| `JNI_VERSION_1_6` | `0x00010006` | JNI 1.6 |
| `JNI_VERSION_1_8` | `0x00010008` | JNI 1.8 |
| `JNI_VERSION_9` | `0x00090000` | JNI 9 |
| `JNI_VERSION_10` | `0x000A0000` | JNI 10 |
| `JNI_VERSION_19` | `0x00130000` | JNI 19, on supporting JDKs |
| `JNI_VERSION_21` | `0x00150000` | JNI 21, on supporting JDKs |
| `JNI_VERSION_24` | `0x00180000` | JNI 24, on supporting JDKs |

**Not every JDK defines or supports every constant in the table.** For example, `JNI_VERSION_24` does not exist in JDK 17 headers. If you compile native code with an older `jni.h` and write a newer constant, the compiler may report an undeclared identifier. At the same time, the compiler accepting a constant does not guarantee that the JVM at runtime also supports that level.

### 3.1. Which Version Is “Right”?

The principle is to **declare at least the JNI version needed for the functions actually used**:

- A library that only uses very basic functions but wants an explicit compatibility contract: can choose a well-supported stable level (for example `JNI_VERSION_1_6` for environments supporting Java 6 and above).
- A library using a function newer than the declared level must raise the required level high enough. Per the specification, `AttachCurrentThreadAsDaemon` was introduced in JNI 1.4, so a library using this function must declare **at least `JNI_VERSION_1_4`**.
- A library requiring APIs introduced in JNI 1.8 or later should return `JNI_VERSION_1_8` or the appropriate supported level, **not** keep `JNI_VERSION_1_2` just to look compatible.
- Do not return the highest constant that the SDK/`jni.h` happens to have if the library does not use those new features: doing so **unnecessarily raises the runtime requirement**.

**Example:** a library that only uses `GetIntArrayElements`, `ReleaseIntArrayElements`, `GetMethodID`, and `CallIntMethod`, running on modern JDKs, can completely choose an appropriate required level such as `JNI_VERSION_1_6` under the project's support policy, instead of always demanding the latest JNI.

When designing for compatibility with very old JVMs, you must check exactly **which version a JNI function first appeared in** from the specification and test on the lowest supported runtime; do not infer it from the Java source version number.

### 3.2. Major/Minor Representation in Constants

The `jint` type in JNI is used for version codes. The return value can be inspected as:

```c
jint version = JNI_VERSION_1_6; /* 0x00010006 */
jint major = (version >> 16) & 0xFFFF; /* 1 */
jint minor = version & 0xFFFF;         /* 6 */
```

This is an example of decoding the number; JNI version constants for Java 9 onward have major values like `9`, `10`, `19`, etc., and minor `0`. Do not confuse `JNI_VERSION_10` with the name “1.10”.

## 4. The `JNI_OnLoad` Mechanism in the Library Lifecycle

Standard signature:

```c
jint JNI_OnLoad(JavaVM *vm, void *reserved);
```

Components:

- **Name `JNI_OnLoad`:** the JVM looks up this exact exported symbol from the dynamically linked library; this is not an arbitrary name.
- **`jint`:** the integer return type containing the `JNI_VERSION_*` code.
- **`JavaVM *vm`:** pointer to the current JVM, which can be used to call Invocation API functions such as `GetEnv`. If stored for later use in native workers, JVM and thread lifecycles must be managed properly.
- **`void *reserved`:** reserved parameter, currently unused; do not dereference it.
- **`JNIEXPORT` and `JNICALL`:** macros in `jni.h` that assist with symbol exporting and the appropriate calling convention, especially important on Windows.

Typical loading flow:

```text
Java: System.loadLibrary("jniversiondemo")
                  |
                  v
    JVM/OS finds and opens shared library
                  |
                  v
         Is JNI_OnLoad present?
          /                 \
       Yes                   No
        |                      |
        v                      v
    Call JNI_OnLoad(vm, ...)   JVM assumes JNI_VERSION_1_1
        |
        v
    Check returned version
       /             \
    Valid          Unrecognized by JVM
      |                  |
      v                  v
    Finish loading     Cancel loading/library not accepted
      |
      v
  Java continues and can call native methods
```

Important point: **exporting a native method `Java_Package_Class_method` does not replace `JNI_OnLoad`**. The library loading sequence and looking up native method symbols are two steps with different roles.

### 4.1. Why Use `JNI_OnLoad` Even Without Complex Initialization?

There are several benefits:

1. **Declaring the minimum version via a formal contract:** readers and the JVM know which interface the library expects.
2. **Checking the environment at load time:** detecting `JNI_EVERSION` or setup errors early, rather than waiting until the first native call.
3. **A controlled initialization point:** you can store `JavaVM*`, register native methods with `RegisterNatives`, or prepare resources if truly needed.
4. **Cleanup logic attachment point:** if there are resources to clean up when the class loader unloads, you can provide the corresponding `JNI_OnUnload` (though the timing of the unload hook is not guaranteed to occur when the process exits).

However, `JNI_OnLoad` **should not** become a place to launch background work without shutdown, arbitrary Java callbacks, or hold JNI references without clear ownership. On initialization failure, clean up all allocated resources and return an error value instead of pretending loading succeeded.

## 5. `GetEnv`, `GetVersion`, and `JNI_OnLoad` Are Not the Same Thing

Three easily confused APIs/concepts:

| API | Role | Where used |
| --- | --- | --- |
| `JNI_OnLoad(...)` | **Declares the minimum JNI required by the native library** and performs setup | Hook called by the JVM when loading the library |
| `JavaVM::GetEnv(..., requestedVersion)` | Obtains `JNIEnv*` for the **current thread** and a requested interface version | Native code that has `JavaVM*` |
| `JNIEnv::GetVersion()` | Inspects the **JVM's JNI version** | Native code that already has a valid `JNIEnv*` |

Example of checking the `JNI_VERSION_1_6` level in `JNI_OnLoad`:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    JNIEnv *env = NULL;

    jint status = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (status != JNI_OK || env == NULL) {
        return JNI_ERR;
    }
    return JNI_VERSION_1_6;
}
```

This is a **complete** C function, used in the full native file in section 6. Calling `GetEnv` is not an attach command: if the thread is not attached, it returns `JNI_EDETACHED`; if the interface version is not supported, it returns `JNI_EVERSION`. When `JNI_OnLoad` is called from Java loading the library, the current thread already has an appropriate JVM context, so this check pattern is reasonable.

**Do not write:**

```c
/* WRONG: GetEnv does not return a version code, it returns a status code. */
jint version = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_6);
return version;
```

`GetEnv` returns **`JNI_OK`, `JNI_EDETACHED`, or `JNI_EVERSION`**, not a `JNI_VERSION_*` constant. Returning `JNI_OK` (typically 0) from `JNI_OnLoad` will not declare a valid JNI version.

### 5.1. Then What Does `GetVersion()` Return?

In a JNI C function that has been passed `JNIEnv *env`:

```c
jint actual = (*env)->GetVersion(env);
```

`actual` describes the JNI version provided by the JVM; it is **not** forced to equal the minimum level the library returned in `JNI_OnLoad`. Specifically, the JNI specification table lists **Java SE 17 returning `JNI_VERSION_10`**, even though a library may declare `JNI_VERSION_1_6`.

A library can have a low minimum requirement (`1.6`) yet run on a JVM with a higher JNI (`10`, `21`, `24`...). That is normal backward compatibility.

If code needs additional newer APIs conditionally at runtime, it should check support via a grounded mechanism (such as `GetEnv` for the needed JNI level), rather than assuming the Java version always equals the JNI version code. Do not “bump” the `JNI_OnLoad` version based on runtime if doing so breaks running on older JVMs where the library still has full functionality.

## 6. Runnable Example: Java 17 + C Declaring `JNI_VERSION_1_6`

The following example includes complete Java source, C source, header generated by `javac`, and build commands on three operating systems. The exercise verifies:

- The JVM actually accepts `JNI_OnLoad` returning `JNI_VERSION_1_6`.
- Java can still call both native methods.
- The required JNI value is printed in major/minor format from the C library.
- Deterministic stdout is identical on **JDK 17 and newer JDKs that still support JNI level 1.6**, on the successful loading path.

### 6.1. File `JniVersionDemo.java`

```java
public final class JniVersionDemo {
    static {
        System.loadLibrary("jniversiondemo");
    }

    private JniVersionDemo() {
    }

    private static native int requiredVersion();
    private static native int add(int a, int b);

    public static void main(String[] args) {
        int version = requiredVersion();

        int major = (version >>> 16) & 0xFFFF;
        int minor = version & 0xFFFF;

        System.out.println("required JNI: " + major + "." + minor);
        System.out.println("add: " + add(20, 22));
    }
}
```

`System.loadLibrary` takes the **logical name** `"jniversiondemo"`, without `lib` or an extension. When the JVM runs the class's static initializer, it locates the corresponding shared library in the native library search path and then processes `JNI_OnLoad`. The methods `requiredVersion()` and `add(...)` are implemented in C.

### 6.2. Generating the JNI Header

In the directory containing `JniVersionDemo.java`, run:

```bash
javac -h . JniVersionDemo.java
```

The command produces `JniVersionDemo.class` and `JniVersionDemo.h`. The generated header declares exactly two JNI functions:

- `Java_JniVersionDemo_requiredVersion` (returns `jint`).
- `Java_JniVersionDemo_add` (takes two `jint` arguments and returns `jint`).

**`JNI_OnLoad` is not a Java method**, so it **does not need and does not have a corresponding Java `native` declaration**; the `JNI_OnLoad` symbol is exported directly from the C library per the Invocation API specification.

### 6.3. File `JniVersionDemo.c`

```c
#include "JniVersionDemo.h"

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void)reserved;

    JNIEnv *env = NULL;
    jint status = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (status != JNI_OK || env == NULL) {
        /* Do not use the JNI interface before it is confirmed. */
        return JNI_ERR;
    }

    /* Declare the minimum JNI level the library requires. */
    return JNI_VERSION_1_6;
}

JNIEXPORT jint JNICALL Java_JniVersionDemo_requiredVersion(
        JNIEnv *env, jclass callerClass) {
    (void)env;
    (void)callerClass;
    return JNI_VERSION_1_6;
}

JNIEXPORT jint JNICALL Java_JniVersionDemo_add(
        JNIEnv *env, jclass callerClass, jint a, jint b) {
    (void)env;
    (void)callerClass;
    return a + b;
}
```

Explanation:

- `JniVersionDemo.h` includes `jni.h`, which defines `JNIEXPORT`, `JNICALL`, `JNI_VERSION_1_6`, and the types `JNIEnv`/`JavaVM`/`jint`.
- `JNI_OnLoad` is called by the JVM when the library loads; it checks that `GetEnv` succeeds and returns **`JNI_VERSION_1_6`**.
- `JNI_ERR` is used to reject initialization when checks fail. It is **not** a JNI version constant.
- `requiredVersion` returns the same `JNI_VERSION_1_6` constant for Java to display; it is an **illustrative JNI method**, not the formal version declaration mechanism.
- Both native methods are `static`, so the second implicit JNI parameter is `jclass`, not `jobject`.
- Adding `20 + 22` produces a deterministic result with no risk of `jint` overflow.

### 6.4. Linux — GCC

Prerequisites: JDK 17+ pointed to by `JAVA_HOME`, `gcc` available, commands run in the same directory as the two source files.

```bash
javac -h . JniVersionDemo.java

gcc -shared -fPIC \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    JniVersionDemo.c -o libjniversiondemo.so

java -Djava.library.path=. JniVersionDemo
```

### 6.5. macOS — Clang

Prerequisites: valid `JAVA_HOME` and Clang/Xcode Command Line Tools available.

```bash
javac -h . JniVersionDemo.java

clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    JniVersionDemo.c -o libjniversiondemo.dylib

java -Djava.library.path=. JniVersionDemo
```

### 6.6. Windows — MSVC

Open x64 Native Tools Command Prompt (or the Developer Command Prompt matching the JDK architecture), configure `JAVA_HOME`, and use `cmd.exe`:

```bat
javac -h . JniVersionDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" JniVersionDemo.c /link /OUT:jniversiondemo.dll

java -Djava.library.path=. JniVersionDemo
```

To avoid ABI errors, use a compiler/binary format matching the architecture of the running JVM. If the JVM is 64-bit, the library must also be 64-bit compatible.

### 6.7. Exact Stdout

When Java finds the library, the JVM recognizes the version and both native methods run successfully:

```text
required JNI: 1.6
add: 42
```

In this example, the code only prints the library's **fixed required level** and the addition; it does not print the runtime JNI version, so these two lines do not change just because the JDK supports a newer JNI level.

If you want to observe the runtime, you can add a native method returning `(*env)->GetVersion(env)` and decode major/minor in Java. In that case **the output depends on the JDK**: for example on Java SE 17, `GetVersion` corresponds to `JNI_VERSION_10`, not 1.6; do not hard-code “runtime JNI = 1.6” in multi-JDK tests.

### 6.8. What If You Want to Require JNI 1.8 Instead of 1.6?

In **`JniVersionDemo.c`**, only when the library logic genuinely requires that level, update consistently:

```c
/* Excerpt of changes, not a standalone C file. */
jint status = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_8);

/* In JNI_OnLoad after GetEnv succeeds: */
return JNI_VERSION_1_8;

/* In the illustrative native requiredVersion(): */
return JNI_VERSION_1_8;
```

Then you must **recompile** the library using JDK headers that have the `JNI_VERSION_1_8` constant and run on a JVM supporting this level. The illustrative stdout will become `required JNI: 1.8`. Do not only change the Java source, because the version is determined on the native side.

## 7. Distinguishing Version Negotiation from Calling Unsupported APIs

### 7.1. `JNI_OnLoad` Does Not Grant Arbitrary API Access

Returning `JNI_VERSION_1_8` does not “upgrade” an old JVM to JNI 1.8. It only requires the JVM to **recognize** that level; if not, loading is rejected. Newer JNI functions can only be used if the runtime actually supports them. Choose the minimum version according to the functions actually used and the project's testing matrix.

### 7.2. Omitting `JNI_OnLoad` Should Not Be Used as a Compatibility Trick

You may omit `JNI_OnLoad` if a dynamic library truly only needs the 1.1 level interface: the JVM **assumes `JNI_VERSION_1_1` by default**. However, the fact that a library can load on a modern JDK without exporting the hook **does not prove** the library has properly declared the newer functions it needs. For modern JNI, export `JNI_OnLoad` and return a valid required level.

### 7.3. Do Not Confuse `GetEnv` with `AttachCurrentThread`

`GetEnv` only retrieves the `JNIEnv*` of an **already attached thread**. If a native worker created by C/C++ needs to call Java, the worker must attach via `AttachCurrentThread` or `AttachCurrentThreadAsDaemon` as appropriate before using JNI. The version argument of `GetEnv` does not automatically attach the thread and is not the return value of `JNI_OnLoad`.

Example in C (illustrative snippet inside code that has a valid `JavaVM *vm`):

```c
JNIEnv *threadEnv = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&threadEnv, JNI_VERSION_1_6);

if (status == JNI_OK) {
    /* Thread is already attached and has the JNI 1.6 interface. */
} else if (status == JNI_EDETACHED) {
    /* Thread is not attached: need to design attaching if calling JNI. */
} else if (status == JNI_EVERSION) {
    /* JVM does not support the requested JNI version. */
}
```

Do not use `threadEnv` on another thread and do not call `DetachCurrentThread` while Java frames are on the stack.

## 8. Differences Between Dynamic Libraries and Statically Linked Libraries

Most desktop/server JNI applications use a **shared library**; for this type, the standard hook is **`JNI_OnLoad`**. However, the JNI Specification also defines a **statically linked native library** mechanism (a library statically linked with the VM/application), introduced in JDK 8.

If a static library has the logical name `L`, it must provide the hook:

```c
/* Illustrative syntax: L is replaced with the library name. */
JNIEXPORT jint JNICALL JNI_OnLoad_L(JavaVM *vm, void *reserved);
```

Specifically for the name `mylib`, the hook is `JNI_OnLoad_mylib`. The specification requires the JNI version returned from `JNI_OnLoad_L` to be **at least `JNI_VERSION_1_8`**. If the JVM does not recognize that code, the static library is likewise not accepted for loading through the corresponding JNI mechanism.

**Do not confuse them:** the library built with `gcc -shared` or `cl /LD` in the section 6 example is a **dynamic library**, so it uses **`JNI_OnLoad`**, not `JNI_OnLoad_jniversiondemo`. The library-name-suffixed hook is only for the static linking path per the specification.

For dynamic libraries, the corresponding cleanup hook is `JNI_OnUnload`; for static libraries, it is `JNI_OnUnload_L`.

## 9. `JNI_OnUnload` and Resource Cleanup

If cleanup is needed when the class loader owning the library is garbage collected, a dynamic library can export:

```c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Clean up native resources that the library actually owns. */
}
```

This is a **standalone hook template for explanation**, not a required part of the C example in section 6.

Important notes:

- `JNI_OnUnload` is called when the **class loader containing the library is GC'd** in the corresponding situations, and is **not guaranteed** to run when Java `main` finishes or at JVM shutdown.
- The hook may be called in an **unpredictable context**; the specification advises using JNI services cautiously and avoiding arbitrary Java callbacks.
- If `JNI_OnLoad` allocates native resources and then fails before returning a valid version, **do not rely on `JNI_OnUnload` always being called** to clean up partial resources. Clean up immediately on the error path inside `JNI_OnLoad` itself.
- For native background threads, ensure there is a stop/join/detach mechanism following an independent lifecycle. Do not let threads continue calling JNI via `JavaVM*` after the VM terminates.

`JNI_OnLoad`/`JNI_OnUnload` are lifecycle attachment points; they **do not replace** pointer ownership rules, local/global references, or thread attachment.

## 10. Common Mistakes When Declaring the JNI Version

| Symptom or mistake | Possible cause | How to handle |
| --- | --- | --- |
| Returning `JNI_OK` from `JNI_OnLoad` | Confusing `GetEnv`'s return code with a version code | Return a valid `JNI_VERSION_*` constant after confirming setup succeeded |
| Returning `JNI_VERSION_1_8` in a binary run on a JVM that is too old | Runtime does not recognize the requested level | Lower the requirement **only if newer APIs are truly not used**, or raise the minimum supported JVM |
| Returning `JNI_VERSION_1_1` while using newer JNI functions | Declaration does not reflect actual dependencies | Raise the library's minimum version |
| `JNI_OnLoad` symbol not exported | Missing `JNIEXPORT`/`JNICALL`, wrong name, or C++ name mangling | Use `jni.h`, exact signature, add `extern "C"` when writing C++ |
| Native code has `JNI_OnLoad` but the built file is not linked into the library | Missing object file in linker input | Check that the source/object is packaged into `.so`/`.dll` |
| C compiler does not recognize `JNI_VERSION_24` | `jni.h` header is too old | Use matching JDK headers, and test compatibility against the target runtime |
| `GetEnv` returns `JNI_EVERSION` | Requested JNI version is not supported | Check the constant against the runtime level, handle failure |
| `GetEnv` returns `JNI_EDETACHED` | Current thread is not attached | Attach the thread following the proper lifecycle if JNI is genuinely needed |
| `UnsatisfiedLinkError` on `System.loadLibrary` | Could be wrong path, architecture, dependency, version return, or symbol | Read the actual message, check both the OS loader and the JNI hook |
| Native method not found after loading succeeds | Exported JNI symbol name or Java/C signature is wrong | Use `javac -h`, inspect with `nm`/`dumpbin`, and check class/package names |
| Returning the highest version “just to be safe” | Unnecessarily breaks compatibility | Use the minimum level based on actual APIs |
| Thinking Java 17 must return `JNI_VERSION_17` | Confusing Java SE version and JNI API version | Read the `GetVersion` table in the spec; JDK 17 returns JNI version 10 |
| Treating `JNI_OnLoad` as a place to freely call Java at any time | At load time there are restrictions on context/class loader/exceptions | Only perform necessary setup, check errors, consider lazy initialization |
| Skipping cleanup when `JNI_OnLoad` fails | Partially allocated resources are not freed | Clean up before returning an error/unsupported version code |

### 10.1. C++: Must Avoid Name Mangling

C++ normally mangles function symbol names into codes containing overload/type information. The JVM requires the **exact C name `JNI_OnLoad`**. Therefore, if implementing in C++, use:

```cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM* vm, void* reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
```

This is a **valid C++ hook**, though it has no application native methods to run on its own. When writing in a `.c` file as in section 6, **do not use `extern "C"`**, because that syntax is for C++.

### 10.2. Diagnosing Library Load Failures by Layer

When `System.loadLibrary("jniversiondemo")` fails, there are at least three layers to check:

1. **Locating the main library:** correct logical name, OS-specific filename, `java.library.path` directory, access permissions.
2. **Native OS loader:** matching JVM/ABI architecture, valid DLL/so/dylib, and dependent libraries can be loaded.
3. **JNI loader:** properly exported `JNI_OnLoad`, receives a valid `JavaVM*`, returns a version code supported by the JVM; after loading, exported native method names must also match.

Start from the actual error message, and do not assume every `UnsatisfiedLinkError` is caused by a JNI requirement that is too high. Use `nm -D`/`objdump -T` on Linux, `nm` on macOS, `dumpbin /EXPORTS` on Windows when you need to inspect symbols. Tools and flags vary by platform.

## 11. Compatibility Policy for Released Libraries

### 11.1. Determine the Minimum Support Level Before Building

A library released for multiple Java versions should clearly document:

- **Minimum supported JDK/JVM** and supported architectures/OSes.
- **Minimum JNI API version** (`JNI_VERSION_*`) based on the functions actually used.
- **JDK used to build the native library** (to locate the right `jni.h`/architecture).
- **Native ABI/toolchain** and OS dependencies, because a valid JNI version still cannot save a binary built for the wrong OS.

If shipping one binary for multiple JDKs, test **actually on the lowest runtime** as well as a few higher runtimes. Do not only run on the latest JDK and guess that an older JVM will understand a version code defined by a newer `jni.h`.

### 11.2. Declare by Need, Not by “Project Version Number”

Suppose a product develops with Java 17, but the C code only relies on older JNI functions. `JNI_OnLoad` can return `JNI_VERSION_1_6`, even though the Java application source uses Java 17, if the library's targets allow it. Conversely, if the C code genuinely uses JNI 1.8 features, it must declare at least `JNI_VERSION_1_8`, regardless of whether the Java sources are written with older syntax.

In case you want to support both old and new APIs at runtime: you need to design **real fallback**. One `JNI_OnLoad` returns the minimum level, and then the code only calls newer functions after confirming the runtime supports them. Do not automatically assume that a higher version number means all platform-specific features exist.

### 11.3. Native Access Permission on Newer JDKs Is Independent of Version

In JDKs with stricter native access policies, loading/calling JNI may emit warnings or require configuring `--enable-native-access`. For example with classpath on a supporting JDK:

```bash
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. JniVersionDemo
```

This line **does not increase** the JNI version the VM supports and **does not modify** the return code of `JNI_OnLoad`. It only handles **native access permission** per runtime policy. With JDK 17, use the run command without this flag in section 6.

The JNI version is also **not** the version of the Java Foreign Function & Memory API (FFM). FFM is a different interop mechanism with its own contract and version requirements.

## 12. Self-Check Questions

**1. If a dynamic library does not declare `JNI_OnLoad`, which JNI version does the JVM assume?** Per the specification, **`JNI_VERSION_1_1`**.

**2. When loading on JDK 17, is it mandatory to return `JNI_VERSION_17`?** No. JDK 17 supports many older JNI versions; `JNI_OnLoad` returns the library's required level. The `GetVersion` table records JDK 17 as corresponding to `JNI_VERSION_10`.

**3. If `GetEnv` returns `JNI_OK`, can you immediately return `JNI_OK` from `JNI_OnLoad`?** No. `JNI_OK` is only a **status code**; `JNI_OnLoad` must return a valid **version code** such as `JNI_VERSION_1_6`.

**4. Why does the example call `GetEnv(..., JNI_VERSION_1_6)` before returning `JNI_VERSION_1_6`?** To confirm that the current thread can obtain the JNI interface at the level the library needs. If unsuccessful, the library actively rejects initialization.

**5. What happens if the JVM does not recognize the returned `JNI_VERSION_*` code?** The JVM **does not accept loading the library** and treats it as if the library was not loaded. Java may see a load error instead of calling the native method normally.

**6. Can `JNI_OnLoad_mylib` replace `JNI_OnLoad` in the shared library example?** No. `JNI_OnLoad_mylib` is the hook pattern **for a statically linked library named mylib**; dynamic shared libraries use the fixed name `JNI_OnLoad`.

**7. Why shouldn't you pick the highest JNI version in the header “just to be safe”?** Because older JVMs may reject the library even though the library uses no APIs at that high level. Declaring the minimum preserves compatibility across the intended support range.

**8. Does returning `JNI_VERSION_1_6` automatically guarantee the C library is compatible across Linux/Windows/macOS?** No. The JNI API version is only one compatibility axis; there are also binary format, CPU architecture, ABI, loader paths, and native dependencies.

## 13. Checklist Before Shipping a JNI Library

1. Identify the exact JNI functions the library needs and the first version level that supports them.
2. In a **shared library**, export `JNI_OnLoad(JavaVM*, void*)`, using `JNIEXPORT`/`JNICALL` and `extern "C"` if written in C++.
3. Return a **JVM-recognized `JNI_VERSION_*`**, not mistakenly returning `JNI_OK`, the Java version, or a custom integer.
4. If checking `GetEnv` in `JNI_OnLoad`, check both `JNI_OK` and `JNIEnv*` before using it.
5. Clean up any partially initialized resources before returning an error; do not rely on `JNI_OnUnload`.
6. Compile with matching `jni.h` headers and test on the lowest supported JDK.
7. Verify `javac -h`, native symbols, architecture, and file names for each OS.
8. Distinguish **JDK version**, **JNI API version**, and **native-access permission**.
9. If using static JNI linking, apply `JNI_OnLoad_L` and the minimum JNI level 1.8 per the specification, without mixing with dynamic linking.
10. Verify that `System.loadLibrary` actually succeeds and native methods are callable; monitor load errors and lifecycle cleanup.

## Official References

- [Oracle Java 17 — JNI Specification: Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_OnLoad`, `JNI_OnUnload`, `JNI_OnLoad_L`, `GetEnv`, and rules for rejecting unrecognized versions.
- [Oracle Java 17 — JNI Functions: GetVersion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): how to read the runtime JNI version; table of JNI versions associated with Java SE releases.
- [Oracle Java 24 — JNI Functions: Version Constants](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html): version codes `JNI_VERSION_1_1`, `JNI_VERSION_1_6`, `JNI_VERSION_1_8`, `JNI_VERSION_9`, `JNI_VERSION_10`, and newer levels.
- [Oracle Java 17 — System.loadLibrary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): path for loading a native library from a Java program.
- [Oracle Java 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-h` option for generating JNI native headers.
- [OpenJDK — JEP 472](https://openjdk.org/jeps/472): direction for restricting native access for JNI in modern JDKs.