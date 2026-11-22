# Distinguishing Native Access Permissions from `--enable-preview` and `--add-opens`

## Goals and Context

Java uses different control mechanisms when an application approaches the boundaries of the platform: **restricted native operations** (JNI/Foreign Function & Memory API), **preview features**, and **module encapsulation** (JPMS). The three options `--enable-native-access`, `--enable-preview`, and `--add-opens` correspond to these three mechanisms. They can appear together in the `java` command, but **do not replace each other**.

Distinguish between three questions:

1. **Native access:** Which module is allowed to perform native operations marked as restricted by the JDK?
2. **Preview:** Is the current JDK version allowed to use Java features that are still in the preview stage?
3. **Deep reflection:** Which consumer module is allowed deep reflective access to a package of another module?

## 1. Comparison Table of the Three Options

| JVM Flag | Actual Purpose | Scope of Impact | No Effect On |
| --- | --- | --- | --- |
| `--enable-native-access=M1,M2` or `--enable-native-access=ALL-UNNAMED` | Allows restricted native operations, including FFM operations and, starting from JDK 24, restricted JNI operations as well | The **modules performing** the native operation; `ALL-UNNAMED` covers code on the class path | Does not open private fields via reflection; does not enable preview; cannot install/load a missing library by itself |
| `--enable-preview` | Allows using preview language/VM features of that exact JDK release | Compiler and runtime corresponding to the preview feature | Does not grant native permissions, does not open JPMS packages |
| `--add-opens=sourceModule/package=targetModule` | Allows **deep reflection** into a package of the source module from the target module | A specified package and target modules | Does not make a restricted FFM/JNI operation valid; does not enable preview |

A package opened with `--add-opens` only changes reflective access rules; it does not guarantee safety or permission to call native code. Conversely, native permission does not grant permission to read/write private fields of classes in `java.base`.

### Native access: permission by the module performing the operation

The option has two common forms:

- `--enable-native-access=ALL-UNNAMED`: applies to **all unnamed modules**, typically the application and libraries located on the class path.
- `--enable-native-access=com.example.nativebridge`: grants permission specifically to the named module `com.example.nativebridge`; multiple module names can be listed separated by commas.

Example configuration for an application running on the class path:

```bash
java --enable-native-access=ALL-UNNAMED -cp app.jar com.example.Main
```

Example for a modularized application, where `com.example.nativebridge` contains the restricted operations:

```bash
java --enable-native-access=com.example.nativebridge -p mods -m com.example.app/com.example.app.Main
```

These are **configuration command templates**; depending on the project, the corresponding JAR, module path, and main class are needed. Permission is checked by the module containing the restricted operation, not simply by where `main()` is placed. If a JNI/FFM library calls a restricted operation in its own module, granting permission only to the application module may still be insufficient.

Starting from **JDK 24**, JEP 472 standardizes how restricted operations of JNI and FFM are handled. This includes loading libraries with `System.load`/`System.loadLibrary`, declaring `native` methods, and FFM methods such as `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, or `MemorySegment.reinterpret`. This mechanism protects JVM integrity against operations that the runtime cannot prove to be safe.

On **JDK 24–25**, the `--illegal-native-access` policy defines the response when permission is missing:

| Value | When a module has not been granted native access |
| --- | --- |
| `warn` (default in JDK 24–25) | Allows running, prints a warning on the first illegal native access of each module |
| `deny` | Denies with `IllegalCallerException` |
| `allow` | Allows running, no warning; should only be considered a transitional mechanism |

A future release is expected to use `deny` as the default; therefore, when testing migration, you should proactively choose `--illegal-native-access=deny` and grant the necessary native access. JDK versions prior to 24 have a different policy history; do not extrapolate the table above backward to all releases.

### Preview: status of a Java feature

A preview feature is a language/VM feature that has not yet been finalized as a stable standard, released to gather feedback. If code uses a preview feature of JDK release `N`, `--enable-preview` must be enabled at **two points**: compiling with `javac --enable-preview --release N` (or `--source N`), and running with `java --enable-preview` on the exact corresponding JDK version. Classes using preview from an older JDK version are not guaranteed to be preview-compatible with a newer JDK.

**Common point of confusion with FFM:** The Foreign Function & Memory API became a **finalized API in JDK 22** (JEP 454), so using the stabilized FFM API on JDK 22+ does not by itself require `--enable-preview`. However, some FFM methods are still marked **restricted**, so `--enable-native-access` may still be needed. When a program both uses a preview feature and calls a restricted native operation, **both permissions** need to be handled independently.

### Open package: reflection permission

Example:

```bash
java --add-opens=java.base/java.lang=ALL-UNNAMED MyApp
```

Meaning: opens the `java.lang` package of the `java.base` module to unnamed modules for deep access via reflection, such as `Field.setAccessible(true)`. This option does not enable JNI/FFM permissions. In addition, `--add-exports` serves access to public types in a package across module boundaries; `--add-opens` serves deep reflection. Only open the specific packages that are truly needed and prefer libraries that use supported public APIs.

## 2. Practice: a program to test both types of permissions

The **JDK 25** example below runs standalone and does not require a C library. It only **creates** an FFM downcall handle using a restricted method without calling any native function; at the same time, it attempts reflection on a private field of `String`. Adding `--illegal-native-access=deny` makes the result clear, avoiding reliance on default `stderr` warnings.

Create the file **`AccessGates.java`**:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class AccessGates {
    public static void main(String[] args) throws NoSuchFieldException {
        Module caller = AccessGates.class.getModule();
        System.out.println("Native access: " + caller.isNativeAccessEnabled());

        try {
            Linker.nativeLinker().downcallHandle(FunctionDescriptor.ofVoid());
            System.out.println("Restricted FFM: ALLOWED");
        } catch (IllegalCallerException e) {
            System.out.println("Restricted FFM: DENIED");
        }

        Field valueField = String.class.getDeclaredField("value");
        try {
            valueField.setAccessible(true);
            System.out.println("Deep reflection: ALLOWED");
        } catch (InaccessibleObjectException e) {
            System.out.println("Deep reflection: DENIED");
        }
    }
}
```

Compile with **JDK 25**:

```bash
javac --release 25 AccessGates.java
```

Run the following scenarios on **JDK 25** (options placed **before** the main class name):

| `java` command | `Native access` line | `Restricted FFM` line | `Deep reflection` line |
| --- | --- | --- | --- |
| `java --illegal-native-access=deny AccessGates` | `false` | `DENIED` | `DENIED` |
| `java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED AccessGates` | `true` | `ALLOWED` | `DENIED` |
| `java --illegal-native-access=deny --add-opens=java.base/java.lang=ALL-UNNAMED AccessGates` | `false` | `DENIED` | `ALLOWED` |
| `java --illegal-native-access=deny --enable-preview AccessGates` | `false` | `DENIED` | `DENIED` |
| `java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED AccessGates` | `true` | `ALLOWED` | `ALLOWED` |

Example **exact** stdout when native access is enabled but the reflection package is not opened:

```text
Native access: true
Restricted FFM: ALLOWED
Deep reflection: DENIED
```

**Exact** stdout when only the reflection package is opened:

```text
Native access: false
Restricted FFM: DENIED
Deep reflection: ALLOWED
```

Explanation: `Module.isNativeAccessEnabled()` reflects the native permission of the running module. `Linker.downcallHandle(...)` is a restricted method, so under the `deny` policy it only succeeds when the module is granted native access. `String.value` is a private field located in the `java.lang` package of `java.base`; `setAccessible(true)` is only allowed when that package has been opened to the program's unnamed module. `--enable-preview` does not affect this test because the code does not use any preview features.

If `--illegal-native-access=deny` is **not** specified on JDK 25, FFM lacking permission may still return a handle but produce a **warning on stderr**. That does not mean the module has been granted native access. Nor should `--enable-preview` be used to try to "suppress native warnings".

## 3. Diagnostic Table When Running Real-World Applications

| Symptom | How to Identify and Fix Correctly |
| --- | --- |
| "restricted native access" warning when loading a JNI library or calling FFM on JDK 24+ | Find the module containing the restricted operation; grant `--enable-native-access` to that module, then test with `--illegal-native-access=deny`. |
| `IllegalCallerException` from a restricted FFM method with `deny` | The module calling the method lacks native permission; opening a package with `--add-opens` will not solve it. |
| `InaccessibleObjectException` from `setAccessible(true)` | Check which module/package is being accessed reflectively; prefer updating the library, or add `--add-opens=sourceModule/package=consumer` with the proper scope. |
| `javac` or JVM reports preview features disabled | The code actually uses preview; enable `--enable-preview` at both compile time and runtime, with the same release version. |
| `UnsatisfiedLinkError` when loading a native library | Check the native file, name, search location, architecture/ABI, and library dependencies. Native permission does not automatically provide `.dll`, `.so`, or `.dylib` files. |

An application may need **all three flags** if all three mechanisms are used together, but each flag must have a specific reason. For example: a library performing JNI operations, a framework reflecting into JDK internals, and the application's own code using preview syntax are three separate situations.

## 4. Common Mistakes and Configuration Principles

- **"FFM is a final API so there are no more native restrictions."** False: the API may be stable, but operations affecting JVM integrity remain restricted.
- **"`--enable-preview` allows running C code."** False: preview enables experimental Java features, not permission to cross the native boundary.
- **"`--add-opens` is the same as `--enable-native-access`."** False: one is for deep reflection in the module system, while the other is permission for restricted native operations.
- **"No exception means native permission is already correct."** On JDK 24–25, `warn` allows running with a warning; test with `deny` to assess readiness.
- **"Always grant native access to the module of `main()`."** Incorrect when a library in another module is the one containing the restricted operation.
- **"`ALL-UNNAMED` only grants to the current class."** False: it applies to all unnamed modules, typically covering the entire class path.
- **"Just add more `--add-opens` until the errors go away."** That opens up more reflective access, making the configuration hard to audit; you should fix dependencies and only open the exact packages needed.

The handling process should be: check `java -version` → identify the error type and API version → identify the target module/package → choose the right flag with the narrowest scope → run tests under `--illegal-native-access=deny` (JDK 24+) and verify that native binaries work in the deployment environment. The `jnativescan` tool on newer JDKs can help find traces of JNI usage and restricted methods; `Module.isNativeAccessEnabled()` helps verify native permission from Java code.

**Remember:** `--enable-native-access` manages **native operation permissions**, `--enable-preview` manages **unfinalized Java features**, and `--add-opens` manages **deep reflection across packages/modules**.

## Official References

- [Oracle JDK 25 — Java launcher options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle JDK 25 — Restricted methods](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/RestrictedMethods.html)
- [Oracle JDK 25 — Restricted method list](https://docs.oracle.com/en/java/javase/25/docs/api/restricted-list.html)
- [Oracle JDK 25 — Preview language/VM features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html)
- [Oracle JDK 25 — Migrating from older JDKs](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Inside Java — JDK 24 restricted native access update](https://inside.java/2024/12/09/quality-heads-up/)