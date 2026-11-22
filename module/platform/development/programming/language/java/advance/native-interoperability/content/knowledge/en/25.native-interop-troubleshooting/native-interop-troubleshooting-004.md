# Detecting JNI with jnativescan and Checking Native Access Permissions When Upgrading the JDK

## 1. Objectives and Scope

When upgrading an application from an older JDK to JDK 24 or newer, the fact that the application still starts up **does not guarantee** that code paths using JNI are safe under the native access policy. This lesson guides you through identifying which JARs/modules use JNI, interpreting the output of the `jnativescan` tool, testing the impact of `--illegal-native-access` at runtime, and granting permissions with the right scope using `--enable-native-access`.

After this lesson, you should be able to do four things: (1) distinguish static scanning from JNI execution; (2) find classes declaring `native` and calls to restricted methods; (3) check class path/module path configuration, warnings, and errors; (4) establish evidence before changing the JDK in a production environment.

**Version scope:** `jnativescan` and the JNI restriction mechanism described below are available starting in **JDK 24** (JEP 472). Use the JDK 24+ toolset to scan; JDK 17/21 can compile simple Java examples but do not have this same tool/check flag. According to the JDK 27 documentation, the default mode is still `warn`; `deny` is expected to become the default in a future release. Always check the documentation for the exact target JDK version instead of guessing when the change will happen.

## 2. What Is Actually Restricted?

The Java Native Interface (JNI) lets Java interact with native code (typically `.so`, `.dll`, or `.dylib` libraries). JNI is useful when you need to use OS APIs or existing libraries, but native code lies outside the JVM's normal safety guarantees: pointer, ABI, or memory bugs can crash the process.

In JDK 24+, two JNI cases require special attention:

- **Loading native libraries:** calling `System.load(...)`, `System.loadLibrary(...)`, `Runtime.load(...)`, or `Runtime.loadLibrary(...)`. These are restricted methods because a library can execute native code right during the loading process.
- **Binding `native` methods:** a declaration such as `private static native int sum(int a, int b);` is bound to a native function when that method is called for the first time. This binding step is a restricted operation.

The JDK also applies the native access model to the **Foreign Function & Memory API (FFM)**. Therefore `jnativescan` can also report restricted FFM calls, even though the main inventory target of this lesson is JNI.

Warnings may appear late: a rarely executed business branch will not yet trigger library loading or `native` method binding. Conversely, a `native` declaration may be found by the scanner even if the application never calls it. **Static scanning is an indicator to investigate; testing actual execution paths is what reveals runtime behavior.**

## 3. Using jnativescan Properly

Check the tools first:

~~~bash
java -version
jnativescan --version
jnativescan --help
~~~

Make sure both the `java` used for testing and `jnativescan` belong to the target JDK or an intentionally chosen JDK version. The tool accepts **JARs**, class path, module path, and root modules; do not misunderstand it as a tool that directly scans machine code inside `.dll`/`.so` files.

| Option | Effect |
| --- | --- |
| `--class-path app.jar` | Scans JARs on the class path; they belong to the unnamed module. |
| `--module-path mods --add-modules com.example.app` | Scans root modules and dependent modules resolved from the module path, including providers via the `uses` mechanism. |
| `--print-native-access` | Prints a list of module names to review, instead of the JAR/class/method tree. |
| `--release 25` | Selects restricted API rules and classes in multi-release JARs appropriate for Java 25; replace `25` with the target version. |
| `--help`, `--version` | Displays syntax and tool version. |

Use `:` between class path/module path elements on Linux and macOS; use `;` on Windows. All JARs specified in `--class-path` are scanned, including JARs declared in the manifest's `Class-Path` if found. With `--module-path`, providing the path is **not enough**: `--add-modules` is needed to specify the root modules to scan.

General examples (replace paths and module names according to your application):

~~~bash
jnativescan --class-path app.jar
jnativescan --class-path app.jar --print-native-access
jnativescan --module-path mods --add-modules com.example.app
jnativescan --module-path mods --add-modules com.example.app --print-native-access
jnativescan --class-path app.jar --release 25
~~~

In the detailed report, read sequentially **JAR → module → class → method**. The line `is a native method declaration` indicates there is a `native` declaration; the line `references restricted methods` indicates which restricted methods the bytecode references. The module list from `--print-native-access` is input for evaluating permission grants, **not automatic proof that all those methods executed**.

## 4. Reproducible Practice Without Building a C Library

Create a file `NativeAccessAudit.java` as follows (valid Java 17+). The example intentionally uses a nonexistent library name to separate **permission** errors from **library lookup** errors. Run only in a clean test directory without a library of the same name:

~~~java
public final class NativeAccessAudit {
    private static native int nativeSum(int left, int right);

    private static void probe() {
        try {
            System.loadLibrary("native_audit_demo_library_not_installed");
            System.out.println("Library loaded");
        } catch (IllegalCallerException ex) {
            System.out.println("Denied: IllegalCallerException");
        } catch (UnsatisfiedLinkError ex) {
            System.out.println("Gate passed; library absent");
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && "probe".equals(args[0])) {
            probe();
        } else {
            System.out.println("Ready; no native operation executed");
        }
    }
}
~~~

Compile, package, run the path that **does not execute** JNI, then scan the JAR:

~~~bash
javac NativeAccessAudit.java
jar --create --file native-access-audit.jar NativeAccessAudit.class
java -cp native-access-audit.jar NativeAccessAudit
jnativescan --class-path native-access-audit.jar
jnativescan --class-path native-access-audit.jar --print-native-access
~~~

The `stdout` of the first `java` command is exactly:

~~~text
Ready; no native operation executed
~~~

The detailed scan result will point out both signals: the declaration `NativeAccessAudit::nativeSum(int,int)int` is `native`, and the method `probe()` references `java.lang.System::loadLibrary(String)void`. Line positions/formatting depend on the tool version. With `--print-native-access` mode, a JAR placed on the class path returns:

~~~text
ALL-UNNAMED
~~~

Point to remember: the program just run **did not emit any JNI warning** on the default branch, yet `jnativescan` still detected native access capability. The reason is that `main` did not call `probe` or `nativeSum`.

Now test the permission gate directly on **JDK 24+**:

~~~bash
java --illegal-native-access=deny -cp native-access-audit.jar NativeAccessAudit probe
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp native-access-audit.jar NativeAccessAudit probe
~~~

Without the permission flag, the first command prints:

~~~text
Denied: IllegalCallerException
~~~

Once native access has been granted to the unnamed module, the second command prints:

~~~text
Gate passed; library absent
~~~

The second command passes the native access check, and then `System.loadLibrary` fails because **the library file does not exist**; `UnsatisfiedLinkError` was caught so the practice exercise runs standalone. This **does not prove that a real JNI library linked successfully**. For integration testing, you need to provide the right native binary, CPU architecture, dependent libraries, and load path.

Trying `--illegal-native-access=warn` on the `probe` branch will allow passing through the gate and may show a `WARNING` on **stderr** (typically once per module in this mode), while still receiving the missing-library message on `stdout`. Do not match warnings verbatim: actual class names, module names, and paths vary by JDK and environment.

## 5. Granting Permissions by Module, Understanding ALL-UNNAMED

The `--enable-native-access` flag specifies **which modules are allowed** to perform restricted operations. It needs to appear in the configuration of the **actual JVM process** running the program, before the main class name or `-jar` argument.

**Applications on the class path** (legacy JARs, code resides in the unnamed module):

~~~bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp "app.jar:lib/dependency.jar" com.example.Main
~~~

The example above uses the Linux/macOS `:` separator; replace with `;` if running on Windows. `ALL-UNNAMED` grants native access to **all code on the class path**, so it should only be used when you understand the scope and cannot yet isolate a narrower module.

**Applications with named modules**:

~~~bash
java --enable-native-access=com.example.nativebridge --illegal-native-access=deny --module-path mods --module com.example.app/com.example.Main
~~~

The illustrative command assumes `mods` contains the modules `com.example.app` and `com.example.nativebridge`, and the second module is where restricted operations are performed. These names are examples; take real names from your module configuration and scan results. If multiple modules directly use native access, pass a comma-separated list: `--enable-native-access=mod.one,mod.two`.

You can place a JAR without `module-info.class` on the module path so the JVM treats it as an **automatic module**, then grant permission using its actual module name. Moving paths can affect dependencies, reflection, and service loading; you must re-test the application. Do not assume the module name from the artifact name without checking.

| `--illegal-native-access` Mode | Behavior When a Module Has Not Been Granted Permission |
| --- | --- |
| `allow` | Allows execution without warning; only suitable for comparison/temporary use. |
| `warn` | Allows execution, warns on first occurrence per module; default in JDK 24–27 per current documentation. |
| `deny` | Throws `IllegalCallerException` on unauthorized native access; should be used when testing JDK upgrades. |

**The most effective way to test:** run the entire integration test suite with `--illegal-native-access=deny`, then grant `--enable-native-access` only to modules verified to need JNI/FFM. Do not use `--illegal-native-access=allow` as a long-term upgrade solution. Granting permission does not replace verifying the trustworthiness of native libraries.

## 6. Application Audit Process Before Upgrading the JDK

1. **Record the target runtime:** current and target JDK versions, OS/CPU architecture, actual launch command (CLI, IDE, Gradle/Maven, container, service), packaged native libraries, and load paths. Also identify child processes spawned by test tools or frameworks.
2. **Collect all runtime JARs:** including the application and runtime dependencies, plugins, and JDBC/driver/framework native bridges if any. For Spring Boot executable/fat JARs containing nested JARs in `BOOT-INF/lib/`, do not assume `jnativescan --class-path app-fat.jar` will automatically scan nested JARs; extract the individual dependency JARs to scan them.
3. **Run a detailed scan first:** run `jnativescan` on the actual class path or `--module-path ... --add-modules ...`, specifying `--release` matching the target JDK if needed. Save results by JAR, class, and method; aggregate modules with `--print-native-access`.
4. **Classify the results:** which libraries directly declare `native`, which classes call `System.load*`/`Runtime.load*` or restricted FFM, who owns the dependency, which business paths trigger it, and whether a library version compatible with the new JDK exists.
5. **Run behavioral tests:** use `--illegal-native-access=deny` without granting permissions first to identify which branches are actually blocked. Then add only the necessary `--enable-native-access` flags and re-test startup, rarely used features, shutdown, the test suite, and the packaged environment.
6. **Cross-check logs:** with `warn`, warnings are typically written to stderr. Use the stack trace and module name in the warning to locate the calling code. You can enable JFR and inspect `jdk.NativeLibraryLoad` / `jdk.NativeLibraryUnload` events to find which libraries are actually loaded/unloaded; these events do not replace the list of bound JNI methods.
7. **Finalize upgrade evidence:** save the tool version, scan commands, JAR/module inputs, list of modules needing permission, final JVM flags, before/after errors, and native binary test results on each OS/architecture; re-run on the target JDK whenever dependencies change.

One way to cross-check library loading events with Java Flight Recorder (JFR) when the JDK and recording configuration support it:

~~~bash
java -XX:StartFlightRecording=filename=native-audit.jfr,settings=profile -cp app.jar com.example.Main
jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload native-audit.jfr
~~~

This is a **command template for a real application** and cannot run immediately without `app.jar`/`com.example.Main`. Not seeing events may be because the path did not execute or the JFR configuration did not enable the events; do not conclude an application does not use JNI from an empty result alone.

## 7. Scan Limitations and Common Pitfalls

- **An empty scan result is not enough to conclude “no JNI”.** `jnativescan` statically analyzes JARs and references visible in bytecode. It does not run the application and does not guarantee seeing every library loading branch via reflection, dynamically generated bytecode, plugins loaded outside the scanned JAR set, or native code itself calling other native APIs.
- **Scanning the wrong input set:** omitting runtime dependencies, multi-release JARs, service provider modules, or only scanning a “fat” JAR with nested libraries will give an incomplete picture. You must scan a runtime class path/module path as close as possible to the deployment.
- **Confusing warnings with library loading errors:** `IllegalCallerException` is the native access gate blocking access; `UnsatisfiedLinkError` is usually a missing native library/symbol, wrong architecture, or mismatched signature; JVM crashes can be caused by bugs in native code. Granting permission does not fix binary/ABI errors.
- **Confusing a `native` declaration with “native code executed”:** this is a static signal. JNI binding only happens when the method is called; the library may also be loaded on another branch.
- **Granting permission to the wrong module:** whichever module contains the code performing the restricted operation needs the permission. Granting permission to the application entrypoint does not automatically grant it to every dependent named module library.
- **Placing flags in the wrong position:** JVM flags go before the main class name or `-jar`; every Gradle `test` configuration, container entrypoint, service wrapper, and other launcher must be checked separately.
- **Confusing native access with reflective access:** `--add-opens` and `--add-exports` address a different set of Java module system restrictions; they **do not** replace `--enable-native-access`.
- **Using `ALL-UNNAMED` unconditionally:** convenient for legacy systems, but opens permission for the entire class path. Prefer narrowing via named/automatic modules if the application allows it.

## 8. Quick Diagnostic Table

| Observation | Interpretation | What to Check |
| --- | --- | --- |
| `jnativescan` reports `native method declaration` | There is a JNI method in bytecode. | Find the calling branch, the library containing the corresponding function, and the OS/JDK version. |
| `jnativescan` reports `references restricted methods` | There is a restricted API call in the JAR. | Class name, method, module; the runtime path executing the call. |
| At runtime, `WARNING` about native access appears | The module has not been granted permission; in `warn` mode, the operation is still allowed. | Launch flags, module name in stderr, originating source. |
| `IllegalCallerException` when `deny` is set | The native access gate is blocking unauthorized code. | Grant permission to the right module, not just the main module. |
| `UnsatisfiedLinkError` after permission is granted | Likely a binary lookup/load or native method binding error, independent of the gate. | `java.library.path`, paths, CPU architecture, dependencies, JNI symbol/signature. |
| No warning at startup, yet scan has results | The native branch has not executed yet, or the module has already been granted permission. | Functional testing, stderr logs, and launch configuration. |

## 9. Completion Criteria Before Upgrading the JDK

- [ ] Identified and recorded the exact target JDK, `jnativescan` tool, and `--release`.
- [ ] Scanned all runtime JARs and root modules; inspected results by class/method.
- [ ] Distinguished `native` declarations, restricted method calls, and operations that actually occur.
- [ ] Ran `--illegal-native-access=deny` on main flows, error flows, batch/plugin flows, and rarely used branches.
- [ ] Specified `--enable-native-access` for the exact modules that must use native code; `ALL-UNNAMED` scope explicitly weighed if required.
- [ ] Handled `UnsatisfiedLinkError`, wrong binary/ABI, and permission errors independently; did not use one flag to mask other errors.
- [ ] Tested on the real deployment environment and saved commands, scan results, stderr, and test results for comparison in the next JDK upgrade.

## Official Documentation

- JEP 472 — Prepare to Restrict the Use of JNI: https://openjdk.org/jeps/472
- Oracle JDK 25, `jnativescan` command: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html
- Oracle JDK 27, `java` command (native access options): https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Oracle JDK 27, Migration Guide (JNI/native access): https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html

**Remember:** `jnativescan` helps identify **where native access is potentially used**; `deny` mode and runtime flow testing show **where the system actually needs permission**. Permission on the right module combined with compatible native libraries is the outcome to achieve when upgrading the JDK.