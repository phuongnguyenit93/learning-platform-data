# `--enable-native-access`: granting native access to named modules and `ALL-UNNAMED` on the classpath

## Objectives

After this lesson, you can: (1) identify **which module actually needs native access** when using JNI or Foreign Function & Memory (FFM); (2) launch a JPMS application with specific module names, a classpath application with `ALL-UNNAMED`, or a mixed application using both; (3) verify granted permissions and diagnose warnings/errors on the appropriate JDK versions; (4) choose the narrowest scope of permission required.

## 1. Why does the JVM need this flag?

**Native access** is the ability of Java code to perform operations that can go outside the JVM's normal safety guarantees, such as calling C functions via FFM, loading native libraries, or interacting through JNI. A call with a wrong function signature, wrong address, wrong memory region lifecycle, or an untrusted native library can crash the JVM process or cause memory corruption. Therefore, the JDK marks certain APIs as *restricted* and enforces stricter control over native activity.

Core syntax:

```text
java --enable-native-access=<module-name>[,<module-name>...] <how-to-launch>
java --enable-native-access=ALL-UNNAMED <how-to-launch>
```

The `--enable-native-access` flag **grants permission to code belonging to the specified module** when that code performs a controlled native operation. The JVM checks **the module of the code calling the restricted operation** (the caller), not the module containing the `main` class, the `java.base` module, or the `.so`/`.dll`/`.dylib` library filename. If the `com.acme.nativebridge` library calls a restricted FFM method on behalf of the `com.acme.app` application, grant the permission to `com.acme.nativebridge`.

This flag **does not** automatically load libraries, locate library files, grant operating system permissions, verify C function signatures, manage pointer safety, or turn native code into a sandbox. It is also not `--enable-preview` or a switch to allow reflective access.

## 2. How do named modules and unnamed modules differ?

| Deployment type | Module containing the code | How to grant native access | Scope |
| --- | --- | --- | --- |
| Explicit JAR/module on `--module-path`, with `module-info.java` | Named module, e.g. `com.acme.nativebridge` | `--enable-native-access=com.acme.nativebridge` | Exactly the named module |
| Regular JAR placed on `--module-path` | Automatic named module, whose name can come from `Automatic-Module-Name` or the JAR filename | `--enable-native-access=<actual-module-name>` | Exactly that automatic module |
| Classes/JARs on `--class-path` or `-cp`, including applications run via `-jar` | Unnamed module | `--enable-native-access=ALL-UNNAMED` | **All unnamed modules**, not just a single JAR |
| Application combining module path and classpath | Named + unnamed | `--enable-native-access=com.acme.nativebridge,ALL-UNNAMED` | Listed named modules **and** unnamed modules |

**`ALL-UNNAMED` is a special keyword**, not a user-defined module name, and there is no corresponding `module-info.java` file. When multiple JARs are on the classpath together, you cannot grant native access to only one JAR using `ALL-UNNAMED`; this option opens it for all code belonging to unnamed modules. If you need to narrow permissions to a single library, consider moving that JAR to the module path as a named or automatic module and granting permission using its exact name.

Each named module has its own identity, regardless of which module contains `main`. Having `requires com.acme.nativebridge;` in `module-info.java` only expresses a module readability relationship; it **does not propagate native access** from module A to B.

## 3. Writing JVM commands with the right scope

The examples below assume a real application has already been compiled and packaged. Replace paths/module names/class names with your project structure.

**One named module needs permission:**

```bash
java --enable-native-access=com.acme.nativebridge --module-path mods -m com.acme.app/com.acme.app.Main
```

Even though `main` is in `com.acme.app`, permission is granted to `com.acme.nativebridge` if the bridge itself calls the restricted API.

**Two named modules both need permission:**

```bash
java --enable-native-access=com.acme.nativebridge,com.acme.plugin --module-path mods -m com.acme.app/com.acme.app.Main
```

Names are separated by commas; avoid inserting spaces in the list.

**Classpath application:**

```bash
java --enable-native-access=ALL-UNNAMED -cp "app.jar:lib/*" com.acme.app.Main
```

The `:` in the classpath above is for Linux/macOS; Windows uses `;`. If the JAR has a `Main-Class` manifest attribute, you can run `java --enable-native-access=ALL-UNNAMED -jar app.jar`. Note that `-jar` uses the executable JAR's classpath mechanism and does not automatically turn that JAR into a named module.

**Mixed module path and classpath:**

```bash
java --enable-native-access=com.acme.nativebridge,ALL-UNNAMED --module-path mods -cp "legacy.jar" -m com.acme.app/com.acme.app.Main
```

The combined form is only appropriate when **both** the named bridge module and some unnamed code actually need native access. Do not add `ALL-UNNAMED` just to make warnings disappear if you do not yet know where the calls are coming from.

**Where should the option be placed?** Place JVM options **before** the main class name, `-m`, or `-jar`, and ensure they are passed to the actual `java` process. Arguments placed **after** the main class name/application path are usually arguments passed to `main(String[] args)`, not JVM options. If running via an IDE, Gradle, Maven, an application server, or a container, configure the **JVM arguments of the application's runtime process**, and do not confuse them with program arguments or compiler arguments.

## 4. Practice 1 — checking whether a module has been granted permission (JDK 22+)

Since JDK 22, `Module.isNativeAccessEnabled()` is the standard API for querying a module's permission. The example below only reads the status; it **does not call any native function**, so it is safe for testing named/unnamed modules.

Create the directory structure:

```text
src/
└── com.example.nativeprobe/
    ├── module-info.java
    └── com/example/probe/NativeAccessProbe.java
```

File `src/com.example.nativeprobe/module-info.java`:

```java
module com.example.nativeprobe {
}
```

File `src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java`:

```java
package com.example.probe;

public class NativeAccessProbe {
    public static void main(String[] args) {
        Module current = NativeAccessProbe.class.getModule();
        String name = current.isNamed() ? current.getName() : "<unnamed>";
        System.out.println("module=" + name);
        System.out.println("nativeAccessEnabled=" + current.isNativeAccessEnabled());
    }
}
```

### 4.1 Running as a classpath/unnamed module

The following shell commands are for Bash on Linux/macOS or a compatible environment; on Windows, you can create directories with equivalent commands. Run from the directory containing `src`:

```bash
mkdir -p build/classes build/mods/com.example.nativeprobe
javac -d build/classes src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java

java -cp build/classes com.example.probe.NativeAccessProbe
java --enable-native-access=ALL-UNNAMED -cp build/classes com.example.probe.NativeAccessProbe
```

**Stdout of command 1:**

```text
module=<unnamed>
nativeAccessEnabled=false
```

**Stdout of command 2:**

```text
module=<unnamed>
nativeAccessEnabled=true
```

Not compiling `module-info.java` into `build/classes` causes the class running on the classpath to belong to the unnamed module. `ALL-UNNAMED` changes the state from `false` to `true`.

### 4.2 Running as a named module

```bash
javac -d build/mods/com.example.nativeprobe src/com.example.nativeprobe/module-info.java src/com.example.nativeprobe/com/example/probe/NativeAccessProbe.java

java --module-path build/mods -m com.example.nativeprobe/com.example.probe.NativeAccessProbe
java --enable-native-access=com.example.nativeprobe --module-path build/mods -m com.example.nativeprobe/com.example.probe.NativeAccessProbe
```

**Stdout of command 1:**

```text
module=com.example.nativeprobe
nativeAccessEnabled=false
```

**Stdout of command 2:**

```text
module=com.example.nativeprobe
nativeAccessEnabled=true
```

Now the class is packaged in a named module; the permission name is `com.example.nativeprobe`. Using `ALL-UNNAMED` alone will **not** grant native access to this module. When testing with JDK 17–21, do not copy the `isNativeAccessEnabled()` query example as-is: this API became standard in JDK 22; earlier versions had different preview/incubator lifecycles.

## 5. Practice 2 — seeing the effect on a restricted FFM method (JDK 24+)

In JDK 24+, `--illegal-native-access` lets you test policies before the JDK switches to stricter defaults. The example below intentionally **only creates a downcall method handle**, without calling any native address:

File `RestrictedProbe.java` in the current working directory:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;

public class RestrictedProbe {
    public static void main(String[] args) {
        Linker.nativeLinker().downcallHandle(FunctionDescriptor.ofVoid());
        System.out.println("Restricted downcall handle created");
    }
}
```

```bash
javac RestrictedProbe.java

java --illegal-native-access=deny RestrictedProbe
java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED RestrictedProbe
```

- **First command:** the unnamed module has not been granted permission; calling `downcallHandle` is blocked with `IllegalCallerException`, so the success line is not printed.
- **Second command:** `ALL-UNNAMED` grants permission to the caller; the exact stdout is:

```text
Restricted downcall handle created
```

If you run `java RestrictedProbe` on JDK 24+ with the default `warn` policy, the operation is usually still allowed and the JVM prints a warning to **stderr**; the exact warning text may vary across JDK versions. **Creating a handle does not prove that an arbitrary native address or C signature is safe to call**; this exercise intentionally does not invoke the handle.

### Warnings and errors by JDK version

| Version group | Key points to remember |
| --- | --- |
| JDK 17–21 | FFM was still evolving as incubator/preview; check the exact JDK documentation and corresponding build/run flags. `--enable-native-access` already existed to control restricted FFM APIs, but do not assume all newer JNI rules apply by default. |
| JDK 22–23 | The FFM API was standardized starting in JDK 22. Restricted FFM calls and `--enable-native-access` are enforced; check the exact version's documentation for how ungranted access is handled (on JDK 22, specifying `--enable-native-access` can cause callers not on the list to fail with `IllegalCallerException`). |
| JDK 24+ | JEP 472 extends the restriction/warning mechanism to prepare for tightening JNI. `--illegal-native-access=allow` allows without warning, `warn` allows with a warning (the default in JDK 24–26), and `deny` blocks with `IllegalCallerException`. A `deny` default is planned for a future release; do not assume it is already the default in every JDK. |

On JDK 24+, running integration tests with `--illegal-native-access=deny` is the way to find missing permissions **before** upgrading the runtime. Do not use `allow` as a long-term fix just to hide warnings.

## 6. How to choose permissions in a multi-library project

Suppose the `com.acme.app` application calls `com.vendor.image`; inside `com.vendor.image` there is a restricted JNI/FFM call. Identify **the library containing the caller**:

1. Inspect the stack trace/JVM warning to find the module of the code calling the restricted method, or check classes declaring `native` methods / call sites of `System.loadLibrary`, `Linker.downcallHandle`, etc.
2. Check how the JAR is passed to the JVM: `--class-path` → unnamed; `--module-path` → named (possibly an automatic module).
3. If it is a named module, check the actual module name with `jar --describe-module --file path/to/library.jar` or the application's module metadata. Do not guess the module name from package names.
4. Grant permission to the **exact caller** module. Re-run with `--illegal-native-access=deny` on JDK 24+ and see if any other callers are still missing permission.
5. If a library must remain on the classpath, use `ALL-UNNAMED` with the understanding that this scope is broad. When appropriate, move the JAR needing permission onto the module path to restrict permissions per module; check module/dependency compatibility before migrating.

This permission is tied to the **module**; it does not propagate via `requires`, transitive dependencies, the module containing `main`, or Java objects passed across APIs. A named module does not gain permission just because another unnamed module was granted `ALL-UNNAMED`.

### Other configuration methods

- **`JDK_JAVA_OPTIONS` environment variable**: the launcher reads JVM options from this variable, which is useful when you do not directly control the launch command. Configure it in the right container/process and check its global impact on `java` commands launched from that environment.
- **Argument file**: write options into a file (e.g., `runtime.options`) and run `java @runtime.options ...`; the module selection rules remain identical.
- **Executable JAR manifest**: the `Enable-Native-Access: ALL-UNNAMED` attribute can grant permission to the classpath when running `java -jar`. This attribute **does not accept named module names** and does not replace settings for `--module-path`.
- **Dynamic module layers**: `ModuleLayer.Controller.enableNativeAccess(module)` supports specialized scenarios, but this operation itself is restricted and requires the caller to have native access. Do not treat it as an arbitrary permission bypass.

## 7. Distinguishing from commonly confused JVM flags

| Flag | Purpose |
| --- | --- |
| `--enable-native-access=M` | Allows code in module `M` to perform restricted/native access according to JDK policy |
| `--enable-native-access=ALL-UNNAMED` | Allows unnamed modules to perform native access; affects the entire classpath |
| `--add-opens=module/package=target` | Opens a package for deep reflection; **does not** grant native access |
| `--add-exports=module/package=target` | Exports a package so other modules can use public types; **does not** grant native access |
| `--enable-preview` | Enables preview language features/APIs of the corresponding JDK; **does not** substitute for native access |
| `-Djava.library.path=...` | Helps the JVM locate native libraries by name in certain library-loading mechanisms; **does not** grant native access and does not guarantee matching architecture/ABI |

### Common errors and how to resolve them

- **Placing `--enable-native-access` after the main class**: `main` receives that string as an application argument; move the flag to the JVM arguments before the main class/`-m`/`-jar`.
- **Granting only `ALL-UNNAMED` when the caller is a named module**: add the exact module name; `ALL-UNNAMED` does not cover named modules.
- **Granting only the application's module name when the restricted API is inside a library module**: update the list to match the actual caller's module.
- **Guessing an automatic module name from a package/JAR without checking**: use `jar --describe-module`, the `Automatic-Module-Name` manifest attribute, or JPMS metadata.
- **Getting `IllegalCallerException` on JDK 24+ with `deny`**: locate where the restricted method is called and grant the minimum required permission; do not rush to enable `allow` for everything.
- **Getting `UnsatisfiedLinkError` or `.dll/.so/.dylib` loading errors after granting permission**: check the library name/path, environment variables, native dependencies, OS/CPU/ABI; the native access flag does not fix linking errors.
- **Assuming that the disappearance of warnings means native code is safe**: risks such as use-after-free, wrong function descriptors, concurrency bugs, or untrusted libraries still exist.
- **Using newer JDK behavior to infer older JDK behavior**: even with the same flag, the set of restricted APIs and warning handling have changed; verify `java -version` and the release notes of the actual runtime.

## 8. Quick decision table

| Actual deployment | Command/value to choose |
| --- | --- |
| Only `com.acme.bridge` (named) calls native | `--enable-native-access=com.acme.bridge` |
| Both `com.acme.bridge` and `com.acme.plugin` call native | `--enable-native-access=com.acme.bridge,com.acme.plugin` |
| Native caller is in a JAR on the classpath | `--enable-native-access=ALL-UNNAMED` (consider moving to a named module if you want to narrow scope) |
| Both named module `com.acme.bridge` and classpath code call native | `--enable-native-access=com.acme.bridge,ALL-UNNAMED` |
| Pure Java application, performing no restricted/native operations | No need to add the flag just because the application has regular dependencies |

**Self-check:** If `com.example.app` runs from the module path, `vendor.legacy.jar` runs on the classpath, and **only** the legacy library calls a restricted FFM API, is `--enable-native-access=com.example.app` sufficient? **No.** The caller belongs to the unnamed module, so it needs `ALL-UNNAMED`, or you must move the library to the module path and grant permission by its module name. Conversely, if only `com.example.app` calls the restricted method, `ALL-UNNAMED` alone is not sufficient either.

## 9. Authoritative references

- Oracle, [`java` launcher, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--enable-native-access` and `--illegal-native-access` syntax.
- Oracle, [Restricted Methods, JDK 25](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html): granting permissions to named/unnamed modules, choosing narrow permissions.
- Oracle, [JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): impact of JEP 472 on JNI/FFM and how to test with `deny`.
- Oracle, [`java.lang.Module`, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `isNativeAccessEnabled()`.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454) and [JEP 472](https://openjdk.org/jeps/472): background on the FFM API and restricting native access.
