# Class version compatibility and limits of the `--enable-preview` flag

When compiling Java, `javac` generates `.class` files containing bytecode and metadata for the JVM. **A JVM cannot load every `.class` file from every Java version.** It checks the class file format version, structure, and other constraints before execution. For **preview** features, there is an even stricter rule: a class file that depends on a preview feature of **Java N** can only be loaded by **Java N** when preview is enabled. Enabling `--enable-preview` on **Java N+1** does not allow running a preview class file from Java N.

This article explains `major_version`, `minor_version`, common causes of `UnsupportedClassVersionError`, how `javac --release` affects compatibility, and the exact limits of `--enable-preview` at both **compile time** and **run time**. The examples use JDK 17 to have a concrete preview case; the tables and normative rules are based on the *Java Virtual Machine Specification* (JVMS).

## 1. What version information does a `.class` file contain?

In a class file, the header has the conceptual structure:

```text
Byte address   Data (big-endian)    Meaning
0..3           CA FE BA BE          magic number
4..5           u2 minor_version     minor version
6..7           u2 major_version     major version
8..9           u2 constant_pool_count
...            ...                  constant pool, class metadata, method code...
```

This is metadata of the **class file format**, not directly the `java -version` string of the build machine. The JVM uses the `major.minor` pair to decide whether it supports that class file encoding.

- **`major_version`** indicates the bytecode format generation associated with a Java release.
- **`minor_version`** is the minor version; since Java 12, the special value **65535** means the class file **depends on preview features** of that release.
- **`CAFEBABE`** is the magic number identifying the format, not a Java version number.
- A `.jar` file is a ZIP container holding many `.class` files and resources; **there is no single major version for the entire JAR** if the classes inside have different versions.

Example output from `javap -verbose Example`:

```text
minor version: 0
major version: 61
```

This means class file format **61.0**, corresponding to **Java 17**, not “Java version 61”. If `minor version: 65535` with `major version: 61`, that class carries the **Java 17 preview** dependency marker.

## 2. Class-file major version and Java releases

Java releases have common major levels:

| Java SE / JDK | Class-file major | Example |
| --- | ---: | --- |
| Java 8 | 52 | `52.0` |
| Java 11 | 55 | `55.0` |
| Java 12 | 56 | `56.0` or `56.65535` if preview-dependent |
| Java 17 | 61 | `61.0` or `61.65535` |
| Java 21 | 65 | `65.0` or `65.65535` |
| Java 22 | 66 | `66.0` or `66.65535` |
| Java 23 | 67 | `67.0` or `67.65535` |
| Java 24 | 68 | `68.0` or `68.65535` |
| Java 25 | 69 | `69.0` or `69.65535` |

For modern Java releases, the major version of Java N is usually **N + 44** (for example Java 17 → 61); this is a mnemonic, while **the JVMS table** is the authoritative source. Java 1.0/1.1 have their own historical details.

**Normal class file case (`minor = 0`):** a newer JVM generally supports older major versions specified for that release. For instance, Java 17 bytecode `61.0` is supported by the Java 21 JVM at the **class file format** level.

However, “the JVM accepts the major version” is **not enough** to guarantee the program runs successfully. One must still consider whether APIs exist, the module system, dependent libraries, behavioral changes, reflection/encapsulation, native libraries, system configuration, and relevant runtime characteristics.

**Case where major is higher than the JVM supports:** Java 17 cannot load a `65.0` class from Java 21. The `--enable-preview` flag on Java 17 **does not raise the major limit** to 65.

### 2.1. Minor version: why is 65535 special?

According to the JVMS, for **major 56 and above**, minor has only two valid values in the class file format: **0** or **65535**.

- `M.0`: normal class file, not marked as preview-dependent via the version pair.
- `M.65535`: class file depending on preview **of the exact release with major M**.
- `M.1`, `M.2`, ... are not how versions are assigned for modern Java.
- Older majors from 45 to 55 have different historical minor rules; **do not infer that 65535 in any old class file means preview**.

For example, `61.65535` means “Java 17 preview”, **not** “a Java 17 bytecode that can run on any JDK with preview enabled”.

## 3. The most important compatibility matrix

Assuming the class file format is otherwise well-formed and there are no other library/API issues:

| Class file | Running JVM | `--enable-preview` enabled at runtime? | Result at class-version level |
| --- | --- | --- | --- |
| `61.0` (normal Java 17) | Java 17 | No | **Allowed** |
| `61.0` | Java 21 | No | **Allowed** |
| `65.0` (normal Java 21) | Java 17 | Yes or no | **No**, major too new |
| `61.65535` (Java 17 preview) | Java 17 | No | **No**, preview disabled by default |
| `61.65535` | Java 17 | Yes | **Allowed** |
| `61.65535` | Java 21 | No or yes | **No**, preview belongs to a different release |
| `65.65535` (Java 21 preview) | Java 21 | Yes | **Allowed** |
| `65.65535` | Java 17 | Yes | **No**, major too new |

“Allowed” only means **passing the version/preview gate**, not a guarantee that the entire application will run. If the class uses an unavailable API, a missing library, a blocked module, or invalid bytecode, the program can still fail during loading, linking, or execution.

Core rule for preview classes:

```text
class file = N_major . 65535
                       │
                       ▼
Runtime must be Java N  +  --enable-preview at runtime
                       │
         Cannot use Java N+1, N+2, ...
         even if newer runtimes also have --enable-preview
```

This is **by design**: preview features can change syntax/semantics, be finalized into a permanent feature, or be withdrawn in a subsequent release. The JVM does not promise to preserve the ability to run preview bytecode from a previous release.

## 4. Why does major version cause `UnsupportedClassVersionError`?

Suppose you have **JDK 21** installed on your build machine and compile with the default settings:

```bash
javac App.java
```

If `App.class` has `major version: 65`, and you run it with Java 17:

```bash
java App
```

The Java 17 runtime only understands class-file major up to 61; the typical error is `java.lang.UnsupportedClassVersionError`, with a message like “class file version 65.0 ... recognizes up to 61.0”. The exact error string depends on the JVM and environment.

One fix when **the code and APIs are actually Java 17 compatible** is to compile with a sufficiently new JDK targeting release 17:

```bash
javac --release 17 App.java
```

Then `javac` produces the class format for Java 17 and checks the language/APIs of release 17. There is **no** basis to expect an application using APIs/syntax only available in Java 21 to still compile successfully with `--release 17`.

If the application strictly requires Java 21, the solution is to upgrade the deployment runtime to the corresponding Java 21 (or adjust/rewrite the code to be compatible with the target version).

### 4.1. Differences between `--release`, `--source`, `--target`

| `javac` option | What it controls |
| --- | --- |
| `--source N` or `-source N` | Language/syntax rules of Java release N |
| `--target N` | Generated class file version |
| `--release N` | Combines source, target, and the **public API surface** of platform release N supported by the tool |

In projects that need to support an older Java runtime, **prefer `--release N`** when appropriate, because setting only `--target N` does not prevent all cases where code references newer Java APIs at compile time. When run on the older machine, that API can cause `NoSuchMethodError`, `NoClassDefFoundError`, or a corresponding linkage error.

Example of compiling Java 11-compatible code on a JDK that supports `--release 11`:

```java
public class CompatibleApp {
    public static void main(String[] args) {
        System.out.println("Compatible class");
    }
}
```

Save the file as **`CompatibleApp.java`**:

```bash
javac --release 11 CompatibleApp.java
javap -verbose CompatibleApp
java CompatibleApp
```

When `javac` finishes, `javap` for this class will show:

```text
minor version: 0
major version: 55
```

Stdout of the program:

```text
Compatible class
```

A `55.0` class can be loaded by a Java 11 or later JVM **in terms of class file version**, provided the remaining runtime requirements are met. Depending on your system, you may need to specify the full path to `javac`/`java` of the right JDK, because multiple JDKs may coexist.

### 4.2. Build tools must also be consistent

In a Maven/Gradle project, check the **Java toolchain**, `sourceCompatibility` / `targetCompatibility`, the corresponding `--release`, the bytecode of **dependent libraries**, and the JDK actually used on the machine running the app.

Example showing Gradle Groovy DSL configuration to select JDK 17 and target Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

The snippet above is **an illustration for a project with the appropriate `java` plugin**, not a standalone Java program. Choosing a toolchain controls which compiler is used, while `options.release` controls the compilation target. You also need to check dependencies, plugins, and the JVM used for testing/deployment. Do not assume an IDE setting automatically affects every build task or container.

## 5. What is a preview feature? What does enabling the flag do?

A **preview feature** is a Java feature that is specified and implemented enough for experimentation, but **not yet permanently committed**. It can be language syntax, a VM capability, or a preview API released for feedback before becoming official.

Two steps may be needed in a program's lifecycle:

1. **Compile time:** enable preview on the right `javac` version if the code uses a preview feature supported by that JDK.
2. **Run time:** enable preview on **the exact same Java version** when running class files that require preview, or when executing a runtime preview feature.

Some features later become standard and do not need `--enable-preview` in the finalized version. A preview feature of Java N can also be changed or removed in N+1; you should not rely on a preview feature as a long-term compatibility contract.

### 5.1. Typical compile syntax

When using **JDK 17** and using a preview feature in Java 17:

```bash
javac --enable-preview --release 17 Preview17.java
```

An equivalent form often used with the appropriate compiler:

```bash
javac --enable-preview --source 17 Preview17.java
```

With modern `javac`, to enable preview for a release you must choose **the current release for which that compiler supports preview**. For example, `javac` from JDK 21 **cannot** use `--enable-preview --release 17` to reproduce or enable Java 17 preview. The Java 17 preview compile command above requires **JDK 17**.

If you only write:

```bash
javac --enable-preview Preview17.java
```

The exact rule requiring `--release`/`--source` when enabling preview depends on the rules of the corresponding `javac`; the clear, reproducible approach is **explicitly specifying `--enable-preview --release <current JDK version>`** as in the example.

### 5.2. Run syntax

If a class file is marked as depending on **Java 17** preview, run it with **Java 17**:

```bash
java --enable-preview Preview17
```

Running with Java 17 without the flag can produce `UnsupportedClassVersionError` reporting that preview is not enabled. Running with Java 21, even with `--enable-preview`, still cannot load a `61.65535` class: that is **Java 17** preview, not Java 21 preview.

`--enable-preview` applies to preview features **of the release being used**; it does not let you selectively enable individual preview features. This flag also does not mean enabling incubator modules, accessing internal APIs, opening module packages, or bypassing the class verifier.

## 6. Java 17 preview example: seeing `61.65535`

Java 17 has **pattern matching for switch** in *preview* status. Use this example **on JDK 17** to illustrate the actual boundary.

Create file **`Preview17.java`**:

```java
public class Preview17 {

    static String describe(Object value) {
        return switch (value) {
            case String text -> "String: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("JVM"));
        System.out.println(describe(42));
    }
}
```

Compile with **JDK 17**:

```bash
javac --enable-preview --release 17 Preview17.java
```

The compiler may print notes/warnings related to preview and options for detailed warnings; those are **diagnostics on stderr**, not the program's stdout. After compiling, inspect the metadata:

```bash
javap -verbose Preview17
```

The version lines you should see:

```text
minor version: 65535
major version: 61
```

Run on **Java 17**:

```bash
java --enable-preview Preview17
```

**Exact stdout:**

```text
String: JVM
Integer: 42
```

Explanation:

1. `switch` using `case String text` and `case Integer number` is pattern matching for switch, preview in Java 17.
2. JDK 17 `javac`, when compiling in preview mode, marks the class using this feature with version **61.65535**.
3. Java 17 runs that class when preview is enabled; there is no need for “two runtime layers” or recompiling on the fly in the `java` command.
4. If you move `Preview17.class` to Java 21, the Java 21 JVM **cannot load it**, even if you run `java --enable-preview Preview17`.
5. To run on Java 21, you must **recompile from source with a Java 21 compiler and valid Java 21 syntax/features**, then recheck major/minor. There is no promise that a preview feature behaves identically across two releases.

**Reliability note:** the example specifically requires JDK 17 installed; a JDK 24 or JDK 21 compiler cannot act as a “Java 17 preview compiler” by setting `--release 17`. This is a real limitation of preview, not a bug in the source code.

### 6.1. Three intentional failure/success tests

Once you have `Preview17.class` in `61.65535` form:

**Test 1: Java 17 without preview enabled**

```bash
java Preview17
```

Expected result: the JVM refuses to load the class, typically with `UnsupportedClassVersionError` explaining that preview is not enabled. **Do not expect program stdout** because `main` is not executed.

**Test 2: Java 17 with preview enabled**

```bash
java --enable-preview Preview17
```

Result: runs successfully and prints the two lines shown above.

**Test 3: Java 21 with preview enabled**

```bash
java --enable-preview Preview17
```

If `java` here is actually Java 21, class `61.65535` is **not valid for the Java 21 release**. The fact that Java 21 normally supports many older major class versions **does not** extend to Java 17 preview classes. The specific error message may vary, but the runtime must reject it according to JVMS rules.

When testing, use absolute paths or set `JAVA_HOME`/`PATH` explicitly to ensure the command invokes **the exact runtime you want to test**.

## 7. What does `--enable-preview` NOT solve?

| Situation | Why the flag does not help | Appropriate resolution |
| --- | --- | --- |
| Java 17 running a `65.0` class | Major 65 is higher than the Java 17 runtime supports | Upgrade runtime to Java 21 or recompile targeting 17 if source/APIs allow |
| Java 21 running a `61.65535` class | Preview bytecode is tied strictly to Java 17 | Recompile source for valid Java 21; cannot enable old preview on Java 21 |
| JDK 21 `javac` enabling Java 17 preview | Compiler only supports preview of its own current release | Use JDK 17 to compile Java 17 preview or update code to Java 21 |
| Class has verification/format errors | The flag does not bypass the class file verifier | Fix the bytecode, generator/instrumentation, or dependency |
| Missing library or API at runtime | The flag does not supply modules/JARs or APIs | Align dependencies, module path/classpath, release APIs |
| Accessing internal packages blocked by modules | Preview is different from opening module encapsulation | Use public APIs or configure appropriate module flags when truly needed |
| Using an **incubator module** such as Vector API in some JDKs | Incubators are not auto-enabled by the preview flag | Check module docs and configure `--add-modules` separately |
| Wanting to run a preview program long-term without code changes | Preview makes no long-term compatibility promise | Track status across releases and migrate to standard APIs/syntax when ready |

In particular, **`--enable-preview` is not “disable version checks”**. It changes the activation state of **preview features supported by that release's own runtime/compiler**, and the runtime still checks major/minor strictly.

## 8. Preview API, preview language feature, and class files

An `M.65535` class file can be generated when the compiler needs to record a preview dependency, such as when source uses a **preview language feature**. Do not assume every `.class` file compiled in a command with `--enable-preview` must have minor `65535` if it does not depend on preview; **always inspect the actual version of each class file**.

Aspects to distinguish:

- **Preview language feature:** new syntax/expressions; the compiler may have to mark the output class file as preview-dependent.
- **Preview VM feature:** a JVM capability defined by the JVMS of that release; execution depends on a supporting runtime and preview-enabled state.
- **Preview API:** an API presented as preview for the release; usage has compiler conditions/warnings and its own deployment rules.
- **Incubator API/module:** a different experimental mechanism; `--enable-preview` **does not** automatically grant access or resolve module configuration for incubators.

You cannot confirm “whether this class uses preview” merely by spotting the string `--enable-preview` in a build file. You need to check **source, dependencies, compiler diagnostics, and class-file metadata**, especially when build tasks compile multiple modules at different releases.

### 8.1. What if a preview feature has become standard?

When a feature is standardized in a newer Java version, using the **syntax/API form recognized by the newer version** may no longer need the preview flag. However, **a preview class built on the old version still carries minor 65535 of the old version** and does not automatically turn into a normal class.

For example, pattern matching for `switch` became permanent in Java 21; even though equivalent source can compile on JDK 21 without using preview for that feature, a `Preview17.class` file already marked `61.65535` **does not change metadata** just by being brought to Java 21.

**The right approach:** recompile the source on the new toolchain with the new configuration, then verify the generated class format.

## 9. Multi-version compatibility and multi-release JARs

With libraries, you may encounter a **multi-release JAR**: a JAR with base classes and specialized classes in paths like:

```text
lib.jar
├── META-INF/MANIFEST.MF     (Multi-Release: true)
├── com/example/Api.class
└── META-INF/versions/17/com/example/Api.class
```

A compatible runtime can select the specialized class for a supported version; the exact structure and selection rules follow the multi-release JAR specification. This mechanism helps provide per-version implementations, **not** turn Java 17 preview bytecode into valid runnable code on Java 21.

For example, if the class in `META-INF/versions/17` is `61.65535`, that version is still subject to the **Java 17 exact-release preview** rule. When using multi-release JARs, design each class/path for the right target JVM and verify which class the runtime actually selects.

A JAR can contain a `65.0` class in the Java 21 branch and a `55.0` class in the base branch for Java 11; that does not mean Java 11 is allowed to load the major 65 class directly. Paths and manifest metadata determine the ability to select the appropriate version.

## 10. Checking the actual versions of toolchain, class, and runtime

### 10.1. Basic command set

```bash
# Java runtime being invoked
java -version

# Compiler being invoked
javac -version

# Class header/bytecode details; command requires JDK
javap -verbose -p CompatibleApp

# On a JAR, inspect specific classes after extracting appropriately
jar tf application.jar
```

`java` and `javac` can come from **two different JDKs** if `PATH` or IDE/CI is inconsistent. Verify the executable paths and toolchain configuration in CI/containers.

`javap` displays class metadata (e.g., major/minor, constant pool, method code), but the running JVM is a separate component. `javap` from a newer JDK can read a format that cannot run on an older Java runtime.

### 10.2. How to read three error forms

**Error A — class file too new:**

```text
... UnsupportedClassVersionError ...
... class file version 65.0 ...
... recognizes class file versions up to 61.0 ...
```

This is an **illustrative message pattern**, not fixed stdout for every JVM. A Java 17-level runtime encountering a Java 21 class will typically report a mismatch between major 65 and 61. Fix the target/build or runtime.

**Error B — preview class file but not enabled:**

```text
... UnsupportedClassVersionError ...
... class file version 61.65535 ...
... preview features are not enabled ...
```

Verify the right Java 17 and add `--enable-preview` **at runtime**, if you genuinely intend to use preview for that release.

**Error C — preview belonging to another release:**

```text
... UnsupportedClassVersionError ...
... class file version 61.65535 ...
... preview features ... unsupported for this runtime ...
```

On Java 21, class `61.65535` cannot run even with preview enabled. Fix by **recompiling from Java 21-compatible source** or running on the exact Java 17 with preview.

### 10.3. 5-step diagnostic process

1. **Identify the file actually loaded:** classpath/module path, JAR, and version-specific path; do not guess based on library name.
2. **Read major/minor:** use `javap -verbose` or an appropriate class-file metadata reader.
3. **Check the actual runtime:** `java -version`, IDE toolchain/launcher, CI image/container.
4. **Branch:** major too high, preview minor 65535 wrong release/not enabled, or another error such as missing API/dependency?
5. **Fix at the right layer:** adjust `--release` when source/APIs allow; align JDK at build and runtime; recompile preview source on the right release; update dependencies, then recheck the actual class.

Do not treat `--enable-preview` as a “try blindly” step whenever you hit `UnsupportedClassVersionError`. Usually just looking at **major.minor** is enough to distinguish two very different cases.

## 11. Applying to builds and deployments

An application that needs to support multiple runtimes should set the **lowest Java target** required by product requirements, use CI to test against the actual target runtimes, and design compatible dependencies. If choosing a preview feature for learning or experimentation, lock the tooling and runtime to the exact **Java release**, and have a migration plan when preview status changes.

Developer checklist:

- Identify the actual version of `java` and `javac` on local machines, CI, and containers.
- Choose `--release N` or a toolchain matching the runtime you want to support; check that dependencies are also compatible.
- If using preview: declare the specific JDK compiler release, use `--enable-preview` properly at compile/run time, and run tests on **that exact release**.
- Check `javap -verbose` on key classes; for JARs/multi-module builds, inspect the selected class files rather than just one class.
- When upgrading the JDK, **recompile preview sources**; do not carry `N.65535` as-is onto N+1.
- For features that have become standard, update syntax/toolchain for the new release and then verify the `minor` of the generated class file.
- Keep builds reproducible: explicitly record JDK/toolchain version, release flags, and deployment images.

## 12. Self-check exercises (with answers)

**Question 1.** A class file has `major 61`, `minor 0`. On Java 21, is `--enable-preview` needed?

**Answer:** **No**, because the class is not marked as preview-dependent. Java 21 accepts major 61 classes at the format level; full execution still depends on APIs/libraries/runtime.

**Question 2.** A class file has `major 61`, `minor 65535`. On Java 21 with `--enable-preview` added, can it run?

**Answer:** **No.** That is **Java 17** preview; the class must be run on Java 17 with preview enabled, or the source must be recompiled for Java 21.

**Question 3.** Using JDK 21 `javac` with `--release 17 --enable-preview`, can you enable Java 17 preview?

**Answer:** **No**. Preview can only be enabled by the compiler for the current release that compiler supports. For Java 17 preview source, you need the JDK 17 compiler (or update the code to constructs accepted by JDK 21).

**Question 4.** Why can `javac --target 11` be an insufficient choice when supporting Java 11?

**Answer:** Because the target class format does not necessarily block references to platform APIs that only exist on the newer build JDK. `--release 11` controls language, target, and the supported API surface together.

**Question 5.** If you run a `65.0` class on a Java 17 JVM and get `UnsupportedClassVersionError`, should you just add `--enable-preview`?

**Answer:** **No.** This is a **major 65 > 61** issue, not a preview minor 65535 issue. Upgrade the runtime or compile with target 17 if the code and dependencies allow.

**Question 6.** Pattern matching for switch became standard in Java 21. Can you run a `61.65535` file compiled as Java 17 preview directly on Java 21?

**Answer:** **No.** The class-file minor still marks Java 17 preview; you must **recompile** to produce the appropriate class-file version.

## Key takeaways

- **`major.minor` describes the class file format**; major relates to the Java release, and minor `65535` since Java 12 indicates preview dependency for that exact release.
- **Normal class `N.0`** can be loaded by newer runtimes at the format level, but API/module/dependency compatibility must still be checked.
- **Preview class `N.65535`** can only be loaded on **Java N with `--enable-preview`**. Newer runtimes, even with the preview flag, do not accept preview classes from N.
- **`--release`** is useful for targeting older Java when not depending on preview; **`--enable-preview`** is a mechanism to experiment with preview of the exact JDK, not a bytecode conversion tool, feature backport, or verification bypass.

### Authoritative references

- [JVMS Java SE 21 — ClassFile structure (`4.1`), version and preview](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 21 — Preview features (`1.5`)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-1.html#jvms-1.5).
- [JEP 12 — Preview Language and VM Features](https://openjdk.org/jeps/12).
- [JDK 17 `javac` manual: `--release`, `--enable-preview`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JDK 17 `java` launcher manual: `--enable-preview`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
