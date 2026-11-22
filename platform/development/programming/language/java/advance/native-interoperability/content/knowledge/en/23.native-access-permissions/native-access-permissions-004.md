# Native Access Permissions — Configuring Warnings or Denials with --illegal-native-access on Supported JDKs

## 1. Objectives and Scope

Java applications can interact with code outside the JVM using **JNI** (Java Native Interface) and the **FFM API** (Foreign Function & Memory API). Operations such as loading C/C++ libraries, linking native methods, creating foreign downcalls/upcalls, or interpreting a memory region at an arbitrary address can corrupt memory or crash the JVM if used incorrectly. Java therefore has a mechanism for **granting native access permissions per module** and a **policy for ungranted accesses**.

Starting in **JDK 24**, **JEP 472 — Prepare to Restrict the Use of JNI** extends the native access control mechanism, unifying how certain JNI operations and FFM restricted methods are handled. A new JVM option is:

```text
--illegal-native-access=allow
--illegal-native-access=warn
--illegal-native-access=deny
```

These three modes **do not grant permissions to any specific module**. They only specify how the JVM **reacts if an ungranted module** attempts to perform a restricted native operation. A more suitable long-term choice is to **allow the exact module that needs native access** using `--enable-native-access`, while setting `--illegal-native-access=deny` to detect what is missing.

**Objectives after this lesson:** accurately explain `allow/warn/deny` and version scope; create a Java 24 application to test all three; combine `--enable-native-access=ALL-UNNAMED` or a module name; understand warnings/`IllegalCallerException`; use `jnativescan` to locate where permissions need to be granted; and know why `allow` should not be used as a long-term fix.

**Version:** executable examples were verified on **OpenJDK 24.0.2, Windows x64**. Oracle documentation for **JDK 24, 25, 26** still describes the three values and the `warn` default in those releases. A future JDK release may change the default to `deny` or remove `allow`; you must check the documentation of the deployed JDK instead of assuming the policy is always fixed.

## 2. What Is “Illegal Native Access”?

**Native access** is when Java accesses or calls code/data located outside the Java runtime. In the new mechanism, not every ordinary Java computation operation requires permission; what is checked are **restricted native operations** according to the JDK specification.

### 2.1. FFM API

Examples of restricted methods in JDK 24:

- `Linker.downcallHandle(...)` to link a Java call → C function.
- `Linker.upcallStub(...)` to convert a Java `MethodHandle` into a callback pointer for C.
- `SymbolLookup.libraryLookup(...)` to load/look up symbols from a native library.
- `MemorySegment.reinterpret(...)` to create a view of a memory region with a size that Java cannot prove safe on its own.
- `AddressLayout.withTargetLayout(...)` to attach a target data layout to a pointer.

The list is **not fixed forever**. When upgrading the JDK, refer to the official documentation on restricted methods for that exact release. The test example in this lesson will use `AddressLayout.withTargetLayout(...)` because it is **restricted** yet **does not need to load a DLL, does not dereference a pointer, and does not call an actual C function**.

### 2.2. JNI

Starting in **JDK 24**, key JNI paths also fall under native-access restrictions:

- `System.load(...)`, `System.loadLibrary(...)`, `Runtime.load(...)`, and `Runtime.loadLibrary(...)`: loading a native library, which may trigger initializers or `JNI_OnLoad`.
- The first **binding** of a method declared `native` to the corresponding function in the library: a step with ABI and native code risks.

JDK 24 may emit a warning when loading a JNI library or linking a native method from a module that has not been granted native access. With `deny`, an unauthorized restricted operation throws `IllegalCallerException` instead of continuing normally.

**Note:** this **does not ban JNI/FFM**. The system only requires the application or runtime deployment to explicitly state **which modules are trusted to perform native operations**. Granting permission does not make native code safe if C pointers, C ABI, calling conventions, lifetimes, or synchronization are wrong.

## 3. The Three Modes of --illegal-native-access

| JVM option | When a module **without native access** calls a restricted operation | Usage meaning |
| --- | --- | --- |
| `--illegal-native-access=allow` | **Allow**, **no warning** | Temporarily reduce noise during migration, but hides modules missing permissions |
| `--illegal-native-access=warn` | **Allow** and emit a **warning to stderr** on each module's first violation | Detect native access debt without disrupting service |
| `--illegal-native-access=deny` | **Deny the operation**, throw `IllegalCallerException` | Test that the application declares permissions properly and prepare for a stricter default |

**The default in JDK 24** is `warn`. Oracle JDK 25 and 26 documentation also still describes `warn` as the default. However, JEP 472 states the direction to **change the default to `deny` in a future release**; `allow` is a transitional mode that may be removed. Do not predict a specific release number without an official announcement.

### 3.1. Important Details of `warn`

- The JVM emits **at most one group of warnings per module** in a process, on the **first time** that module performs illegal native access.
- Warnings are written to **stderr**, not necessarily the application's stdout.
- The ungranted module **is still allowed to execute the operation**. `warn` is an observability policy, **not a sandbox**.
- If **a new JVM** is started, the warning may repeat in the new process; “once” does not mean “once forever on the machine”.
- If **two different modules** both violate, each module may receive its own warning.
- Do not confuse warnings from `--illegal-native-access=warn` with compiler warnings about preview, deprecation, or another policy.

### 3.2. Important Details of `deny`

- When a restricted operation is not granted permission, the JVM throws `IllegalCallerException`.
- If the application catches the exception, the program **can continue running** but **the native operation is denied**; if not caught, the program usually terminates due to an uncaught exception.
- `deny` **does not revoke permissions** of modules already allowed via `--enable-native-access`. The two flags are designed to be used together.
- For code that needs to run actual native operations, configuring `deny` **without granting permission to the right module** can fail at startup, when loading a library, or on the very first call to a restricted method.
- This is permission control at defined API points, **not a mechanism to block malicious C code running inside a library that has already been granted permission**.

### 3.3. `allow` Is Not a “Thorough Fix”

Setting `allow` only suppresses warnings/denials **under the current policy**; it does not help find the Java/JNI libraries that need native access. The sustainable fix is to identify the module performing the restricted call, **grant permission to that module**, and run tests with `--illegal-native-access=deny`. Keeping `allow` in production long-term can hide migration bugs and cause failures when a later version removes this mode.

**Valid values in JDK 24 are `allow`, `warn`, `deny`.** `debug` and `permit` belong to the historical **`--illegal-access` for reflection**, **not** values of `--illegal-native-access`. Do not copy old reflection flags to native access.

## 4. Distinguishing the Two Options: Policy and Explicit Permission

### `--enable-native-access=...`: granting permission to modules

```bash
# Grant permission to ALL unnamed modules (code on the classpath):
java --enable-native-access=ALL-UNNAMED -cp out MyMain

# Grant permission to one named module:
java --enable-native-access=com.example.nativebridge \
  --module-path mods \
  -m com.example.app/com.example.app.Main

# Grant to multiple specific named modules:
java --enable-native-access=com.example.nativebridge,com.example.codec \
  --module-path mods -m com.example.app/com.example.app.Main
```

The names `MyMain`, `com.example.app`, `com.example.nativebridge`, and `com.example.codec` in the examples only illustrate module configuration; they must be replaced with actual classes/modules in the project. The target that needs permission is **the module containing the code that directly performs the restricted operation**, not necessarily the module containing `main`.

### `--illegal-native-access=...`: handling ungranted modules

```bash
# Any module NOT granted permission will be denied.
java --illegal-native-access=deny -cp out MyMain

# Permission is explicitly granted; other modules are still denied.
java --illegal-native-access=deny \
  --enable-native-access=ALL-UNNAMED \
  -cp out MyMain
```

How to remember:

```text
             Module M calls a restricted operation
                            │
                            ▼
                Does M have native access?
                     ┌──────┴───────┐
                    YES             NO
                     │              │
                     ▼              ▼
                   Allow       --illegal-native-access?
                                    │
               ┌────────────────────┼───────────────────┐
               ▼                    ▼                   ▼
             allow                 warn                deny
               │                    │                   │
             Allow                Allow       IllegalCallerException
            silently            + warning
```

**Recommended combination when preparing for migration:**

```bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp out MyMain
```

This is the right syntax for the **classpath**. In a real modular system, you should **only grant the module name that needs native access** instead of the broad `ALL-UNNAMED`. If a Java library on the classpath calls a restricted method, the library's unnamed module itself needs permission; `--enable-native-access=com.example.app` **does not automatically grant** permission to all JARs still on the classpath.

### Do Not Confuse with Other Flags

| Flag | Domain | Does it replace the native access policy? |
| --- | --- | --- |
| `--enable-preview` | Enable preview APIs/features of that exact JDK release | **No**; preview and restricted permissions are two different things |
| `--add-opens` | Open a package for deep reflection | **No** |
| `--add-exports` | Export a package for compile/runtime access | **No** |
| `--illegal-access` | Old reflection mechanism, obsolete since JDK 17 | **No**; it is not `--illegal-native-access` |
| `--enable-native-access` | Grant a module permission to perform native restricted operations | **Yes**, this is the right way to grant permission |
| `--illegal-native-access` | Specify allow/warn/deny when a module **has not been granted permission** | **Yes**, this is the violation policy, not a permission grant list |

Both `--enable-native-access` and `--illegal-native-access` are **JVM launcher options**. Place them **before** the main class name, `-jar`, or `-m` target. Do not place `--illegal-native-access=deny` after `NativeAccessModesDemo`, because it will become a string in `args` instead of configuring the JVM.

## 5. Runnable Java Example: Testing All Three Modes on JDK 24

The example intentionally **does not load a native library** and **does not call a dangerous pointer**. It calls a **restricted FFM API** to show the exact policy the JVM applies, making it reproducible on a JDK 24+ machine with the FFM API.

### 5.1. Full Source `NativeAccessModesDemo.java`

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

public final class NativeAccessModesDemo {
    public static void main(String[] args) {
        try {
            AddressLayout layout = ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT);

            System.out.println("restricted call: OK");
            System.out.println("pointer bytes: " + layout.byteSize());
        } catch (IllegalCallerException denied) {
            System.out.println("restricted call: IllegalCallerException");
        }
    }
}
```

**Why choose `AddressLayout.withTargetLayout`?** JDK 24 marks it as a restricted FFM method. It allows declaring the target data type of a pointer layout without dereferencing an arbitrary C address. Therefore, this policy test **does not need a C compiler or shared library**. Other FFM operations such as `Linker.downcallHandle` or JNI `System.loadLibrary` also follow native-access permissions, but testing with them adds platform dependencies.

`catch (IllegalCallerException)` here is only to **produce stable stdout for the lesson**. In production, do not use this catch to silently treat unexecuted native code as success; you must configure permissions properly or report a deployment error.

### 5.2. Compile Once

Use **JDK 24** `java` and `javac`. On Windows PowerShell or a Unix terminal:

```bash
java -version
javac -version

mkdir -p out
javac -encoding UTF-8 -d out NativeAccessModesDemo.java
```

`--enable-preview` is not needed just to use FFM in JDK 24: FFM has been finalized since JDK 22. `--illegal-native-access` is not a `javac` flag; it belongs to the **java launcher**.

### 5.3. Run Default and `warn`

```bash
# Default in JDK 24: warn.
java -cp out NativeAccessModesDemo

# Explicitly specify warn.
java --illegal-native-access=warn -cp out NativeAccessModesDemo
```

**Stdout for each command (tested on Windows x64/OpenJDK 24.0.2):**

```text
restricted call: OK
pointer bytes: 8
```

**stderr has a group of warnings**, in which the key lines are:

```text
WARNING: A restricted method in java.lang.foreign.AddressLayout has been called
WARNING: java.lang.foreign.AddressLayout::withTargetLayout has been called by NativeAccessModesDemo in an unnamed module (...)
WARNING: Use --enable-native-access=ALL-UNNAMED to avoid a warning for callers in this module
WARNING: Restricted methods will be blocked in a future release unless native access is enabled
```

The `(...)` indicates the machine-specific classpath path part, **not** literal Java output. The warning states **the restricted API**, **the offending class/module**, and **the suggested grant flag**. Under the `warn` policy, the method still works, so stdout still reports `OK`.

### 5.4. Run `allow`

```bash
java --illegal-native-access=allow -cp out NativeAccessModesDemo
```

**Tested stdout:**

```text
restricted call: OK
pointer bytes: 8
```

**Native-access-related stderr of the example: empty.** There is no warning even though the module still has not been explicitly granted permission. This is why `allow` is dangerous if used to “clean up logs”: it easily hides JNI/FFM dependencies that need to be addressed before upgrading the JDK.

### 5.5. Run `deny` Without Granting Permission

```bash
java --illegal-native-access=deny -cp out NativeAccessModesDemo
```

**Tested stdout:**

```text
restricted call: IllegalCallerException
```

There is no `pointer bytes: 8` line, because the restricted method was denied. The demo program **intentionally catches the exception**, so the process exit code can still be `0`; do not use the demo's exit code alone to declare that native access succeeded. In real code, do not blindly catch this exception or turn a denial into a successful result.

### 5.6. Run `deny` with Proper Permission Granted

```bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp out NativeAccessModesDemo
```

**Tested stdout:**

```text
restricted call: OK
pointer bytes: 8
```

**No restricted warnings** in the demo's stderr. Reason: code in the unnamed module was explicitly granted permission, so `deny` only applies to other modules that have **not** been granted permission. This is the configuration pattern that is **correct in principle**: strict policy + explicit permission.

### 5.7. Summary Table of Tested Results

| How it was run | Module granted permission? | Key stdout | stderr native warning |
| --- | --- | --- | --- |
| Default (JDK 24) | No | `restricted call: OK`, `pointer bytes: 8` | Yes |
| `--illegal-native-access=warn` | No | `restricted call: OK`, `pointer bytes: 8` | Yes |
| `--illegal-native-access=allow` | No | `restricted call: OK`, `pointer bytes: 8` | No |
| `--illegal-native-access=deny` | No | `restricted call: IllegalCallerException` | No; operation was denied |
| `--illegal-native-access=deny --enable-native-access=ALL-UNNAMED` | Yes | `restricted call: OK`, `pointer bytes: 8` | No |

**Scope of the number `8`:** that is the pointer width in bytes on the tested **Windows x64**. On a 32-bit ABI, `layout.byteSize()` may differ (usually `4`), but the meaning of `allow/warn/deny` does not change.

## 6. Named Module Example: Least-Privilege Permission

If an application is modularized, you should not grant `ALL-UNNAMED` to the entire classpath when only one bridge module needs restricted APIs. The example below is **compiled and run directly on JDK 24**.

### 6.1. Project Structure

```text
src/
└── com.example.nativebridge/
    ├── module-info.java
    └── com/
        └── example/
            └── nativebridge/
                └── NativeAccessNamedDemo.java
```

**`src/com.example.nativebridge/module-info.java`**:

```java
module com.example.nativebridge {
}
```

**`src/com.example.nativebridge/com/example/nativebridge/NativeAccessNamedDemo.java`**:

```java
package com.example.nativebridge;

import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

public class NativeAccessNamedDemo {
    public static void main(String[] args) {
        try {
            AddressLayout layout = ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT);

            System.out.println("named module: granted");
            System.out.println("native enabled: "
                + NativeAccessNamedDemo.class.getModule()
                      .isNativeAccessEnabled());
            System.out.println("pointer bytes: " + layout.byteSize());
        } catch (IllegalCallerException denied) {
            System.out.println("named module: denied");
        }
    }
}
```

`Module.isNativeAccessEnabled()` returns the native access grant status for the current module. Because the restricted method call comes before the check line, the program will print `named module: denied` when blocked and will not print the grant status.

### 6.2. Compile the Module

```bash
javac --module-source-path src -d mods -m com.example.nativebridge
```

### 6.3. Denied Because Permission Was Not Granted

```bash
java --illegal-native-access=deny \
  --module-path mods \
  -m com.example.nativebridge/com.example.nativebridge.NativeAccessNamedDemo
```

**Tested stdout:**

```text
named module: denied
```

### 6.4. Grant the Right Named Module, Keep `deny` for Everything Else

```bash
java --illegal-native-access=deny \
  --enable-native-access=com.example.nativebridge \
  --module-path mods \
  -m com.example.nativebridge/com.example.nativebridge.NativeAccessNamedDemo
```

**Tested stdout on Windows x64/OpenJDK 24:**

```text
named module: granted
native enabled: true
pointer bytes: 8
```

The result shows that **the module directly calling the restricted method** is the one that needs permission. If `com.example.app` calls into a bridge `com.example.nativebridge` and the bridge itself creates the FFM downcall, the bridge's name is the appropriate target for `--enable-native-access`. Do not arbitrarily grant permission to the `main` module just because it is the entry point.

**Note:** cross-platform Java commands in shells that support the `\` character for line continuation (Linux/macOS, bash); on PowerShell, use **a single-line command** or PowerShell's backtick character for line continuation instead of `\`. Single-line commands can all be written equivalently and have been tested through PowerShell.

## 7. Finding Modules That Need Native Access with `jnativescan`

**`jnativescan`** has been available since JDK 24 to scan JARs/modules to detect places that potentially use native functionalities, including **restricted method calls** and **`native` method declarations**. It helps prepare for `--illegal-native-access=deny` without having to trace every stack trace manually.

The example in section 5 can be packaged into a JAR:

```bash
# Run in the directory containing the class file, or specify the exact path:
jar --create --file demo.jar -C out NativeAccessModesDemo.class

jnativescan --class-path demo.jar

jnativescan --class-path demo.jar --print-native-access
```

**Actual scan result on JDK 24 (JAR path shortened for readability):**

```text
demo.jar (ALL-UNNAMED):
  NativeAccessModesDemo:
    NativeAccessModesDemo::main(String[])void references restricted methods:
      java.lang.foreign.AddressLayout::withTargetLayout(MemoryLayout)AddressLayout
```

With `--print-native-access`, the **exact stdout** of the test:

```text
ALL-UNNAMED
```

**Scanner limitations:**

- `jnativescan` is **static analysis** on the classpath/module path configuration you provide; it does not observe every code path executed at runtime.
- Reflection, dynamically loaded plugins, generated code, libraries not yet in the scanned JARs, or native code called externally may not appear completely.
- An `ALL-UNNAMED` result only says the scanned code is on the classpath; it **does not prove that every classpath JAR actually needs permission**.
- For modular projects, scan the right root modules and dependencies; use the results together with runtime tests running `deny`, rather than relying only on static analysis.
- A runtime warning usually clearly states **the caller class and module**. You can rely on it to find the exact JAR/library, upgrade the dependency, or design a named module.

The tool may be present depending on the JDK/JVM distribution. Check `jnativescan --help` on the target JDK; do not assume JDK 17/21 has this command.

## 8. Configuration in Maven, Gradle, IDEs, and Production Launchers

`--illegal-native-access` is a **runtime flag**. Configuring the `javac` compiler does not automatically pass the flag to the JVM running tests, `java -jar`, plugin executors, daemons, IDEs, or Docker containers.

### 8.1. Maven Surefire (fragment)

Example snippet inside `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>
          --illegal-native-access=deny
          --enable-native-access=ALL-UNNAMED
        </argLine>
      </configuration>
    </plugin>
  </plugins>
</build>
```

**This is a fragment, not a standalone `pom.xml`.** A real project needs to pin a plugin version compatible with JDK 24+ and configure the full build. If JaCoCo or another plugin already uses `argLine` to attach a Java agent, **do not overwrite `-javaagent`**; combine the two types of flags in a way appropriate for the current build.

When the project is ready to modularize, replace `ALL-UNNAMED` with the name of the module that actually calls native code. If a test needs to run **the failure path due to a missing grant as well**, create a separate test profile/process with `--illegal-native-access=deny` **without** setting `--enable-native-access` for the module under test; if permission is granted beforehand, denial cannot be tested.

### 8.2. Gradle Groovy DSL (fragment)

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--illegal-native-access=deny',
            '--enable-native-access=ALL-UNNAMED'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--illegal-native-access=deny',
            '--enable-native-access=ALL-UNNAMED'
}
```

`Test` controls the JVM running tests; `JavaExec` controls the JVM run by Gradle tasks. These flags are **not guaranteed** to apply to a `java -jar app.jar` process outside Gradle: they must be placed in the product's launcher, service unit, container command, or corresponding runtime options.

### 8.3. IDE

In the Run/Debug configuration of IntelliJ IDEA, Eclipse, or another IDE:

- Select a **JDK 24+** that supports the option.
- Put `--illegal-native-access=deny` and `--enable-native-access=...` in **VM options**, not **program arguments**.
- JUnit/test runner and code coverage configurations often have their own JVMs; they must be configured independently.
- If multiple JDKs are installed on the same machine, check the actual Java executable used by the IDE.

### 8.4. CLI and CI/CD

Example of an application packaged as a JAR running on the classpath:

```bash
java --illegal-native-access=deny \
     --enable-native-access=ALL-UNNAMED \
     -jar myapp.jar
```

For named modules, use `--module-path` and `-m` as in section 6. When packaging as a Docker image or custom Java runtime with `jlink`, ensure the launcher in the deploy environment has **the same policy and grants** as CI. Do not assume the build's `JAVA_HOME` variable is the JDK running the container.

You can use `JDK_JAVA_OPTIONS` or a Java `@argument-file` to pass launcher flags; this affects **every Java process** that inherits the configuration, so be careful when using it in environments with multiple applications. A clearer approach is to configure it directly in the launcher that needs native access.

### 8.5. Multi-Step Migration Testing

1. Record the actual Java runtime using `java -version`.
2. Run a baseline with **`--illegal-native-access=warn`** to find callers/modules using restricted operations.
3. Run `jnativescan` on the actual JARs/modules and cross-check with runtime warnings.
4. Upgrade/update native libraries if a version with better native access policy support is available.
5. Grant explicit native access only to the modules that need it, e.g. `com.example.nativebridge`.
6. Run integration tests with **`--illegal-native-access=deny`** to catch grant gaps, including lazy JNI loading paths or on-demand loaded plugins.
7. Test native library loading/unloading, callbacks, error branches, and shutdown after changing the policy.
8. Deploy with explicit grants and strict mode on a supported JDK; re-verify on the target JDK release after every upgrade.

## 9. Behavior by JDK Version

| JDK | Related FFM/JNI and native-access policy |
| --- | --- |
| **JDK 17** | Legacy FFM still in incubator; **do not apply** the JDK 24 `--illegal-native-access` option as-is |
| **JDK 21** | FFM **Third Preview (JEP 442)**, requires `--enable-preview` when compiling/running; do not use the new JDK 24 `--illegal-native-access` command as if it already existed |
| **JDK 22–23** | FFM finalized since JDK 22 (**JEP 454**), but `--illegal-native-access` did not yet have JEP 472's unified semantics; restricted FFM policy had differences |
| **JDK 24** | **JEP 472** introduces `--illegal-native-access=allow/warn/deny` and applies a consistent JNI/FFM warning mechanism; **`warn` default** |
| **JDK 25–26** | Corresponding Oracle documentation still describes `allow/warn/deny` and `warn` default; verify the actual runtime |
| **Future JDK** | Direction is to switch to **`deny` by default**, remove `allow`, and eventually the transitional option; do not rely on a fixed default |

Do not use `--illegal-native-access=debug`: that is not a valid mode. Do not treat `--enable-preview` as a way to grant restricted JNI/FFM permissions. Do not assume `--enable-native-access` must appear in `javac` for normal Java programs; it is a launch-time module permission.

### Subtle Difference Between JDK 22–23 and JDK 24

JEP 472 **softens** some FFM situations in JDK 24 to match JNI: before JDK 24, if native access had been granted to one or more modules and another module called a restricted FFM method, that other module could be denied with `IllegalCallerException`; with `warn` in JDK 24, it may be allowed to continue running with a warning. Therefore, the fact that an application **runs on JDK 24 with warnings** does not prove it is safely configured for a future `deny` policy.

Stable testing solution: configure `--enable-native-access=...` explicitly for the necessary modules and **enable `--illegal-native-access=deny`** in CI. This is also the migration direction recommended by Oracle.

## 10. Troubleshooting Common Configuration Errors

| Symptom | Common reason | How to fix |
| --- | --- | --- |
| Console has `WARNING: A restricted method ...` | Module not granted permission, `warn` policy | Find the module in the warning; grant the exact `--enable-native-access` |
| `IllegalCallerException` when using FFM/JNI | `deny` policy rejects restricted call from ungranted module | Grant the right module or remove unnecessary native operation |
| Have `--enable-native-access=com.example.app` but bridge is still blocked | Restricted call is actually in another library/bridge module | Grant permission to the module with the actual caller; use `jnativescan`/warning |
| Enabling `--illegal-native-access=allow` removes warnings | `allow` hides violations, not a proper permission grant | Switch to explicit grant + `deny` |
| Ran `deny` but demo still exits with code 0 | Demo intentionally catches `IllegalCallerException` | Check stdout `restricted call: IllegalCallerException`, not just exit code |
| `Unrecognized option: --illegal-native-access` | JVM is too old or does not support it | Use appropriate JDK 24+, do not apply new flag to Java 21 |
| `Unrecognized option / invalid mode debug` | Confused `--illegal-native-access` with `--illegal-access` | Use `allow`, `warn`, `deny` |
| Placed flag after main class name | Flag becomes a program argument | Place before class/`-jar`/`-m` |
| App runs on CLI but tests fail | Test JVM does not have permission/grant yet | Configure Surefire, Gradle Test, or IDE test VM options |
| App tests pass but Docker fails | Runtime in container has different JDK or lacks launcher flags | Check `java -version` and the actual deploy command |
| Warning from a dependency on the classpath | Unnamed module contains restricted native call | Temporarily use `ALL-UNNAMED` when needed; long-term move bridge JAR separately to module path |
| `--illegal-native-access=deny` passes but native code still crashes | Policy does not check all ABI/lifetime/memory bugs | Fix C ABI, sizes, pointer lifetimes, allocators, and native code |

### Do Not Confuse Warning Suppression with Real Security

`--illegal-native-access=deny` helps **detect/forbid restricted operations from ungranted modules**. Once a module has been granted native access, code in that module can still use JNI/FFM unsafely and crash the JVM. Native access restriction does not isolate native code into a sandbox, nor does it check every C/C++ address access.

`allow` also does not help track down memory leaks, double-free, use-after-free, or stack corruption. Other QA layers are needed: ABI testing, runtime integration tests, JNI pending exception error handling, FFM arena lifetimes, memory sanitizers on the native side, and appropriate OS/process-level permission limits.

## 11. Deployment Checklist

- [ ] Confirm **JDK 24+** actually supports `--illegal-native-access`; do not assume from the Java version in the IDE.
- [ ] Record `java -version` and the actual JVM execution path in CLI, tests, CI, Docker/production.
- [ ] Understand the difference between **policy for ungranted modules** and **explicit module grant**.
- [ ] Choose `warn` to probe ongoing native access (on JDK 24 the default is `warn`).
- [ ] Choose `deny` to test strict enforcement; do not use `allow` as a permanent workaround.
- [ ] Only grant `--enable-native-access` to **modules containing restricted code**, do not infer from the `main` module name.
- [ ] With classpath, understand `ALL-UNNAMED` grants broadly to unnamed modules; modularize when least-privilege is desired.
- [ ] Identify JNI `System.loadLibrary`, native method bindings, and restricted FFM methods in dependencies.
- [ ] Scan with `jnativescan` then run integration tests with `deny` to find unscanned dynamic paths.
- [ ] Do not place VM flags as program arguments; do not mix with `--illegal-access` or `--enable-preview`.
- [ ] For Maven/Gradle/IDEs, configure **each execution JVM**, not just the compile step.
- [ ] When upgrading the JDK, re-check the **default mode and still-supported modes** in the official documentation.
- [ ] Even with grants, continue controlling C ABI, pointer bounds, arena lifetimes, and native error handling.

## 12. Self-Study Questions

1. Does `--illegal-native-access=warn` allow a restricted call to continue running, and at most how many times is a warning emitted for a module in the same JVM?
2. Do `--illegal-native-access=deny` and `--enable-native-access=ALL-UNNAMED` contradict each other? Why is using them together useful?
3. If restricted code is in `com.example.nativebridge` while `main` is in `com.example.app`, which module name needs `--enable-native-access`?
4. Why can `allow` be a migration risk even though the program reports no warnings?
5. Does `IllegalCallerException` necessarily cause the JVM to exit nonzero if the demo has caught the exception?
6. Why is `AddressLayout.withTargetLayout` suitable for testing the policy without needing a C library?
7. What does `jnativescan --print-native-access` returning `ALL-UNNAMED` mean, and why are runtime tests still needed?
8. Which new JNI mechanisms are subject to native access restrictions in JDK 24 according to JEP 472?
9. Can `--enable-preview` or `--add-opens` replace `--enable-native-access`?
10. Does `--illegal-native-access=deny` guarantee that C code already granted permission will not cause memory corruption?
11. If a warning only appears when lazy-loading a plugin in production, which files/modules and launcher flags will you check?
12. When the default policy changes in a future JDK, what needs to be ensured so the app does not unexpectedly fail?

**Remember:** On **JDK 24 and versions supporting `--illegal-native-access`**, `warn` **lets it run and warns**, `allow` **lets it run silently**, while `deny` **blocks and throws `IllegalCallerException`** when an **ungranted** module calls a restricted native operation. The sustainable deployment approach is **`--enable-native-access=<correct module>` + `--illegal-native-access=deny`**, rather than relaxing with `allow` across the entire JVM.

### Official Documentation

- [Oracle JDK 24 — java launcher: --enable-native-access and --illegal-native-access](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html).
- [Oracle JDK 24 — Migration Guide: Controlling the Effect of Native Access Restrictions](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html).
- [Oracle JDK 26 — Migration Guide: JNI/FFM native access restrictions](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle JDK 25 — jnativescan command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html).
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).
- [Inside Java — JDK 24 Quality Outreach Heads-up: Prepares Restricted Native Access](https://inside.java/2024/12/09/quality-heads-up/).
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final, JDK 22)](https://openjdk.org/jeps/454).
