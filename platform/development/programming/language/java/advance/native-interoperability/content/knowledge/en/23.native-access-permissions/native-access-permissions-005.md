# Restrictions on JNI Starting in JDK 24 and Their Impact When Upgrading the JDK

## 1. Context and Goal

**JNI (Java Native Interface)** allows Java code to call functions in native libraries (typically written in C/C++) via `native` methods, while also allowing native code to call back into the JVM. Libraries can be `.so` on Linux, `.dylib` on macOS, or `.dll` on Windows. This capability is necessary for many drivers, compression libraries, image processing libraries, databases, and OS integration software, but native code can crash the JVM, access memory incorrectly, or break Java's safety guarantees.

**JEP 472 – Prepare to Restrict the Use of JNI**, introduced in **JDK 24**, extends the *native access restrictions* mechanism already applied to the Foreign Function & Memory (FFM) API to JNI. Starting in JDK 24, the JVM checks native access permissions when Java **loads a native library** and when it **binds a `native` method**. By default in JDK 24, 25, and 26, an ungranted operation still runs but emits a warning. A future JDK release will change the default to deny; that change should not be attributed to a specific version before an official announcement.

Goal of this article: accurately identify the two checkpoints, distinguish warnings from actual errors, grant permissions to the right modules, and prepare for a JDK upgrade without relying on temporary configurations.

> **Key takeaway:** JNI remains a standard interface and is neither removed nor marked deprecated by JEP 472. This JEP controls **permission to perform native operations on the Java/JVM side**, and does not disable JNI functions inside already-running C/C++ code.

## 2. Which JNI Operations Are Restricted?

| Java-side Operation | When Is It Checked? | Module Requiring Native Access |
| --- | --- | --- |
| `System.load(String absolutePath)` | When calling the library loading method | Module containing the code **calling load** |
| `System.loadLibrary(String libraryName)` | When calling the library loading method | Module containing the code **calling loadLibrary** |
| `Runtime.getRuntime().load(...)` / `loadLibrary(...)` | When calling the corresponding library loading method | Module containing the code **calling load** |
| Declaring `native` and calling the method for the first time | When the JVM binds the Java method to the native function (binding) | Module **declaring the `native` method** |

`System.load(...)` and `System.loadLibrary(...)` are convenience calls to `Runtime`; all four library loading methods belong to the restricted group. For `load`, the argument is an absolute path; for `loadLibrary`, the argument is a logical library name, for example `nativemath` so the JVM looks for `libnativemath.so` on Linux. Both still need to find a compatible library.

**Loading** is dangerous because OS initialization code or the `JNI_OnLoad` function can run immediately when the library is loaded. **Binding** is dangerous because the JVM cannot prove that the signature and behavior of the native function actually match the Java side. When a `native` method has never been called, merely declaring it or loading the class does not necessarily trigger a binding warning: the check occurs when the method is bound, usually on the first call.

A module that only **calls** a `native` method declared by **another module** does not automatically need native access permission for that call. However, whichever module performs `System.loadLibrary` still needs its own permission. For example, if `com.acme.loader` loads the library and `com.acme.codec` declares `native int decode(...)`, grant permission to **both** modules. If one module does both, grant it only to that module.

JNI functions called from C/C++ code are not individually prohibited by JEP 472. However, granting native access does not make C/C++ code memory-safe, does not grant file/OS access permissions, and does not replace ABI/architecture compatibility checks.

## 3. How Does Behavior Change When Upgrading the JDK?

| Milestone | Meaning for JNI |
| --- | --- |
| JDK 17/21 and releases before JDK 24 | JEP 472's JNI warning mechanism is not yet applied; traditional library, ABI, and binding errors still exist. |
| JDK 22–23 | The FFM API already has native access restrictions; JNI does not yet have the equivalent extension under JEP 472. |
| **JDK 24** | JEP 472 takes effect: default warnings on ungranted JNI loading/binding; handling of JNI and FFM is unified. |
| JDK 25–26 | Migration documentation continues to describe `warn` as the default and supports the native access options. |
| Future JDK | The plan is for `deny` to become the default and unauthorized native usage to result in an exception; check release notes before each upgrade. |

An application may **compile and run fine on JDK 21**, and then **still run but emit `WARNING` to stderr on JDK 24+**. If strict checking mode `deny` is enabled without granting permissions, the application may fail right at the library loading step or on the first method binding. Because the warning usually appears **once per module**, clean logs after the first call do not prove that all JNI paths have been tested.

### Two JVM Options to Distinguish

- `--enable-native-access=...`: **grants permission** to the specified module(s); this is the long-term configuration to use.
- `--illegal-native-access=...`: chooses **how the JVM reacts when a module lacks permission**. This is a testing/migration tool, not a replacement for granting permissions.

| `--illegal-native-access` | Behavior for Ungranted Operations | When to Use |
| --- | --- | --- |
| `allow` | Allows execution without warning | Only as a short-term transition workaround if truly needed; easily hides native dependencies. |
| `warn` | Allows execution and warns on the first violation per module | Default in JDK 24–26; helps detect usage during actual runs. |
| `deny` | Throws `IllegalCallerException` at the unauthorized operation | **Recommended in CI/staging** along with identified permissions to verify readiness for future JDK upgrades. |

The warning may mention the module name, class, method, and suggest `--enable-native-access=...`. It is sent to **stderr**; the wording and file locations in the message vary by JVM, so do not write tests that hard-match the entire warning text.

## 4. Granting Native Access with the Right Scope

### 4.1. Applications Running on the Classpath (Unnamed Modules)

If the code using JNI is on the classpath, you can grant permission to unnamed modules:

```bash
java --enable-native-access=ALL-UNNAMED -cp app.jar com.acme.Main
```

To test strict blocking behavior in advance:

```bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp app.jar com.acme.Main
```

`ALL-UNNAMED` allows **all code on the classpath** to perform restricted JNI/FFM operations; because of its broad scope, use it only when libraries requiring native access cannot yet be moved to the module path. `ALL-UNNAMED` does **not** automatically grant permission to named modules on the module path.

### 4.2. Applications Using the Java Platform Module System (JPMS)

If JNI resides in a module named `com.acme.nativebridge`:

```bash
java --enable-native-access=com.acme.nativebridge --illegal-native-access=deny --module-path mods -m com.acme.app/com.acme.app.Main
```

In practice, add all modules that actually **call load methods** or **declare `native` methods** to the comma-separated list:

```bash
java --enable-native-access=com.acme.loader,com.acme.nativebridge --illegal-native-access=deny --module-path mods -m com.acme.app/com.acme.app.Main
```

The module name must match the **runtime name**, which does not necessarily match the package, project name, or JAR file. For automatic modules, you can check the derived name with `jar --describe-module --file path/to/library.jar` or observe the actual warning.

### 4.3. Other Places Where Configuration Can Be Passed

- Startup scripts, container configurations, systemd/services, application server launchers, and test pipelines all need to pass the options to **the right `java` process**.
- You can use the `JDK_JAVA_OPTIONS` environment variable or a launcher argument file such as `java @java-options.txt`.
- For an **executable JAR** run with `java -jar`, the application JAR's manifest can specify `Enable-Native-Access: ALL-UNNAMED`. The supported manifest value is **`ALL-UNNAMED`**, not a list of named modules; do not expect a dependency JAR's manifest to grant permission for the entire application.
- For custom runtime images, you can use `jlink`'s `--add-options` option to bundle the appropriate JVM options. Every deployment method must be tested on the actual image and startup command.

**Do not use `--add-opens` or `--add-exports` to address JEP 472 warnings**: those flags are for encapsulation/module access, which is different from native access. Also, do not treat `-Djava.library.path=...` as a way to grant JNI permission: this property only helps locate libraries.

## 5. Self-Compilable and Verifiable JNI Example

The example runs on **Linux** with JDK 24+ and the `gcc` C compiler; the Java part uses Java 17+ compatible syntax. On Windows/macOS, the library build step uses the tools and library format appropriate for the operating system.

**Step 1 — `NativeMath.java`:**

```java
public final class NativeMath {
    static {
        System.loadLibrary("nativemath");
    }

    private static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println("sum=" + add(3, 4));
    }
}
```

`System.loadLibrary` runs when the class is initialized; the call `add(3, 4)` causes the JVM to bind the `native` method to its implementation in the library.

**Step 2 — `NativeMath.c`:**

```c
#include "NativeMath.h"

JNIEXPORT jint JNICALL Java_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
```

`NativeMath.h` is generated by `javac -h` and contains the corresponding JNI signature; `jclass` is the parameter for the `static native` method. The C code computes the sum of two numbers and does not retain memory pointers beyond the call.

**Step 3 — Compile on Linux:**

```bash
javac -h . NativeMath.java
gcc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -o libnativemath.so NativeMath.c
```

The command requires `JAVA_HOME` to point to the exact JDK used for building. The output produces `NativeMath.class`, `NativeMath.h`, and `libnativemath.so` in the current directory.

**Step 4 — Compare Three Modes When Running with JDK 24+:**

```bash
# (A) Default: runs, but emits a native access warning on stderr.
java -Djava.library.path=. NativeMath

# (B) Future simulation: denies if permission is not granted.
java --illegal-native-access=deny -Djava.library.path=. NativeMath

# (C) Grant permission and enforce strict check: runs without JEP 472 warnings.
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -Djava.library.path=. NativeMath
```

For (A) and (C), the **exact stdout** of the program is:

```text
sum=7
```

In (A), JDK 24+ by default prints a warning to **stderr** when loading the library. Because the same unnamed module has already emitted a warning, the JVM does not necessarily print another warning when `add` is bound. In (B), the ungranted `System.loadLibrary` operation results in `IllegalCallerException`; because it occurs in a static initializer, the stack trace may also include `ExceptionInInitializerError`. The program does **not** print `sum=7`. In (C), permission is granted to the unnamed module containing both the load operation and the `native` declaration.

If (A) or (C) reports `UnsatisfiedLinkError`, check the `.so` file, `java.library.path`, 32/64-bit architecture, dependent libraries, and JNI signature; this library finding/loading/binding error is **different** from lacking native access permission.

## 6. Detecting Which Parts of an Application Depend on JNI

**Static scanning with `jnativescan` (available since JDK 24):**

```bash
jnativescan --class-path app.jar
jnativescan --class-path app.jar --print-native-access
jnativescan --module-path mods --add-modules com.acme.app --print-native-access
```

The tool scans JARs and dependent modules in the specified configuration, detecting references to restricted methods and `native` declarations; the `--print-native-access` mode returns the module names that need review. It does not replace runtime testing: classes loaded only via reflection, platform-selected libraries, rare error paths, and JNI buried deep in dependencies can leave the inventory incomplete if you miss scanning a JAR or fail to exercise the right feature.

**Runtime observation:** run the real application build on the target JDK, saving stderr from the startup phase **and** functional flows that require JNI. The JDK Flight Recorder events `jdk.NativeLibraryLoad` and `jdk.NativeLibraryUnload` help observe libraries being loaded/unloaded, but do not by themselves replace identifying which Java module needs permission.

**Dependency inspection:** audit JARs containing `native` declarations, code calling `System.loadLibrary`, bundled `.so/.dll/.dylib` libraries, native launchers/agents, driver versions, and related environment variables. A pure Java application at the business layer can still depend on JNI indirectly through a third-party library.

## 7. Recommended Process When Upgrading from JDK 17/21 to JDK 24+

1. **Lock down target version and baseline:** record the JDK of development, CI, staging, and production environments; inspect the Java and native libraries actually loaded, including CPU architecture and OS.
2. **Inventory native access owners:** scan JARs with `jnativescan`, run integration tests on the target JDK to collect warnings, and categorize by modules **performing loads** or **declaring `native`**; verify transitive dependencies as well.
3. **Grant minimal permissions:** prefer named modules and `--enable-native-access=M1,M2`. If the system still runs completely on the classpath, use `ALL-UNNAMED` in a controlled manner and plan to narrow it down when appropriate.
4. **Enable strict checking:** run staging/CI with `--illegal-native-access=deny` alongside the required permission list. Actually trigger features that call JNI, including lazy loading, startup hooks, shutdown hooks, and error cases.
5. **Fix libraries/packaging:** upgrade library versions to support the target JDK/OS/ABI, fix library names/paths if needed; avoid trying to solve `UnsatisfiedLinkError` by adding unrelated permissions.
6. **Add options to the real launcher:** verify that flags reach the JVM in Docker/Kubernetes, deploy scripts, test runners, IDEs, and service wrappers; retest from the final artifact, not just from a test command on a developer machine.
7. **Set release criteria:** with the target configuration, critical JNI flows pass under `deny` without `IllegalCallerException`, without native/ABI errors, and preserve correct business results. Continue monitoring release notes of subsequent JDKs.

If a dependency only has a JNI-based version, **keeping JNI and granting proper permissions** is a valid solution. Consider the FFM API (stable since JDK 22) for appropriate new development or modernization, but FFM also has restricted operations and still requires native access at the relevant points; **migrating from JNI to FFM does not automatically eliminate the need to grant permissions**.

## 8. Common Issues and Troubleshooting

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| `WARNING: A restricted method ... System::loadLibrary ...` | The module calling library load has not been granted permission | Identify the module performing the load and add it to `--enable-native-access`. |
| `WARNING: A native method ... has been bound` | The module **declaring** the `native` method has not been granted permission | Grant permission to the declaring module, not just the calling module. |
| `IllegalCallerException` when `deny` is enabled | A restricted operation occurred in a module without native access | Use the warning/scan/stack trace to find the module, update the launcher, and rerun with `deny`. |
| `UnsatisfiedLinkError: no ... in java.library.path` | Missing library or wrong lookup path | Check the logical library name, file, `java.library.path`, OS dependencies, and architecture. |
| `UnsatisfiedLinkError` on a `native` method | Symbol not found or JNI signature mismatch | Regenerate header with `javac -h`, check exported symbols, library/classloader. |
| Warning persists even after adding `ALL-UNNAMED` | Restricted code is in a **named module**, or the option did not reach the right JVM | Read the module name in the warning; grant permission specifically to the named module; check the startup command. |
| Java code only calls a wrapper but still sees warnings | The wrapper/dependency performs the load or declares `native` | Find the implementation and module owning the restricted operation; do not look only at the business caller. |

Do not confuse the following errors with JEP 472: reflection/module access errors such as `InaccessibleObjectException`, missing exported packages, native libraries with the wrong ABI, crashes from C/C++ pointers, or OS permissions. `--enable-native-access` only addresses the JVM's native access policy.

## 9. Knowledge Self-Check

**Scenario A:** Module `com.acme.api` calls `NativeBridge.compute()`; `NativeBridge` declares `native` in `com.acme.bridge`, and `com.acme.bridge` itself calls `System.loadLibrary`. **Which module should be granted permission?** → `com.acme.bridge`; `com.acme.api` only calls a Java method declared in another module.

**Scenario B:** `com.acme.loader` calls `System.loadLibrary`, and `com.acme.bridge` declares `native`. **Which module should be granted permission?** → Both `com.acme.loader` and `com.acme.bridge`, because the load and binding checks are tied to two different modules.

**Scenario C:** After upgrading to JDK 24, startup still works, but stderr shows a JNI warning once. **Can it be ignored permanently?** → No. It is a signal that permission needs to be granted and `--illegal-native-access=deny` should be tested before future JDK releases tighten the default.

**Scenario D:** `--enable-native-access=ALL-UNNAMED` was added, yet the application still fails with `libfoo.so` not found. **What should be fixed?** → Check library packaging and loading paths; the permission flag does not provide the library file.

## 10. Official References for Version Upgrades

- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): scope, loading/binding warnings, granting permissions, and plans to change the default.
- [Oracle JDK 24 Migration Guide – Restrictions on and Warnings from Accessing Native Code](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html): migration and deployment guidance.
- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): behavior in subsequent releases.
- [JDK 24 `jnativescan` Tool Guide](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jnativescan.html): classpath/module path scanning syntax.
- [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/index.html): JNI interaction and binding rules.

**Operating principle:** pinpoint where Java loads a library or declares a `native` method → grant native access to the corresponding module → run integration tests with `--illegal-native-access=deny`. That is how to keep JNI applications running reliably across JDK upgrades.
