# Compile-Time Classpath Differs from Runtime Classpath

## 1. Core Problem: Successful Compilation Does Not Guarantee Successful Execution

A Java project can compile completely normally, yet at execution time report:

```text
java.lang.NoClassDefFoundError: com/acme/lib/Formatter
```

This situation usually occurs when **a dependency is present on the compile-time classpath, but is absent (or is the wrong version) on the classpath that the JVM uses at runtime**. The compiler needs to locate types to verify names, methods, fields, and type relationships; the JVM must locate the actual definitions at the moment the class needs to be loaded/linked/initialized.

These are two separate environments:

- **Compile-time classpath:** the set of directories, JARs, and artifacts that the compilation tool (typically `javac`, via CLI/IDE/build tool) uses to resolve dependency types outside the source being compiled.
- **Runtime classpath:** the set of directories, JARs, and artifacts that the launcher/JVM and related class loaders can use to load the required classes when running the application on the classpath.
- **Module path:** since Java 9, applications can use JPMS; the module path and module resolution rules are not synonymous with the traditional classpath. When using modules, you must check both `requires` and `exports` relationships and how the launcher configures the module path.

The two classpaths can be the same, but **they are not the same by default**. They often differ when using an IDE, dependency scopes, applications packaged as JARs, running in Docker, server deployments, CI/CD, plugins, or inconsistent library versions.

### Real-world example

The application calls `Formatter.format()` from the `shared-formatting.jar` library. The developer's machine has the JAR in the compile classpath, so `javac` confirms that the method exists and produces `Main.class`. When only `Main.class` is deployed to the server and `shared-formatting.jar` is forgotten, the JVM may still find the `Main` entry point, yet when `Formatter` is needed it cannot find the class.

Therefore, the question “Why didn't `javac` report an error?” is answered by the fact that **javac and the JVM are looking up dependencies under two different configurations**.

## 2. Compile Classpath and Runtime Classpath Answer Two Different Questions

A directory `out/app` contains `com/acme/app/Main.class`, while `out/lib` contains `com/acme/lib/Formatter.class`. If you compile `Main.java` with `javac -cp out/lib -d out/app ...`, the compiler finds the `Formatter` type; **it does not automatically copy `Formatter` into the application output**.

| Stage | Example Command on Linux/macOS | Outcome to Observe |
| --- | --- | --- |
| Compile | `javac -cp out/lib -d out/app src/app/com/acme/app/Main.java` | Compiler finds external types |
| Runtime with full libraries | `java -cp "out/app:out/lib" com.acme.app.Main` | Class and dependency can be loaded |
| Runtime missing library | `java -cp out/app com.acme.app.Main` | Main can start, but linking to Formatter fails |

Windows uses a semicolon `;` between classpath entries, while Linux/macOS uses a colon `:`. `javac -d` selects **where to write** bytecode; it does not define the library search path for the `java` process that will run afterward.

## 3. When Is It Not Just a Missing File?

A classpath entry must be the **package tree root** or an appropriate JAR. Putting a JAR in a directory does not mean the application's loader will automatically find it. Aside from missing libraries, compile-time and runtime can also select **two versions of a class with the same name**: the JVM finds the class, but the API in the bytecode does not match, resulting in `NoSuchMethodError`, `NoSuchFieldError`, or a linkage error. The following experiment isolates one dependency to illustrate the exact cause; how Gradle/Maven select and distribute dependencies is covered in depth in the final article of the chapter.

## 4. Java 17+ Experiment: Formatter Present at Compile Time, Missing at Runtime

We create two independent parts: a library class and an application class. The example does not depend on Maven/Gradle; it only requires JDK 17+.

Create the directory tree along these paths:

```text
src/
├── lib/
│   └── com/acme/lib/Formatter.java
└── app/
    └── com/acme/app/Main.java
```

Contents of `src/lib/com/acme/lib/Formatter.java`:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String format(String text) {
        return "Formatted: " + text;
    }
}
```

Contents of `src/app/com/acme/app/Main.java`:

```java
package com.acme.app;

import com.acme.lib.Formatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println(Formatter.format("Java"));
    }
}
```

These two classes have consistent **packages** and **paths**. There is no assumption that an IDE or build tool automatically adds libraries.

### Step 1 — Compile the library

From the root directory of the example:

```bash
javac --release 17 -d out/lib src/lib/com/acme/lib/Formatter.java
```

The library is written as:

```text
out/lib/com/acme/lib/Formatter.class
```

### Step 2 — Compile the application with the library on the compile-time classpath

```bash
javac --release 17 -cp out/lib -d out/app src/app/com/acme/app/Main.java
```

This command succeeds because `javac` finds `com.acme.lib.Formatter` from `out/lib`. The application output is written to:

```text
out/app/com/acme/app/Main.class
```

**Important point:** `javac -cp out/lib` only lets the compiler use the library; it **does not copy `Formatter.class` into `out/app`**. The files remain in two separate output directories.

### Step 3 — Run with the full runtime classpath

Linux/macOS:

```bash
java -cp "out/app:out/lib" com.acme.app.Main
```

Windows (PowerShell or Command Prompt):

```powershell
java -cp "out/app;out/lib" com.acme.app.Main
```

Deterministic stdout:

```text
Application started
Formatted: Java
```

Both the root containing `Main.class` and the root containing `Formatter.class` are present, so the JVM can load the program's class and its dependency.

### Step 4 — Run with a runtime classpath missing the library

```bash
java -cp out/app com.acme.app.Main
```

In this run, `Main.class` is still in `out/app`. However, `out/lib` is excluded from the runtime classpath, so the JVM has no path to locate `com.acme.lib.Formatter` through the standard mechanism.

On typical JVMs, stdout has usually already printed `Application started` before the `Formatter.format(...)` call triggers an error; stderr will contain information similar to:

```text
Exception in thread "main" java.lang.NoClassDefFoundError: com/acme/lib/Formatter
    ...
Caused by: java.lang.ClassNotFoundException: com.acme.lib.Formatter
    ...
```

The specific stack trace lines, the order of appearance between stdout/stderr when redirected, and when the JVM chooses to perform resolution may be implementation-dependent; therefore, this is an **error pattern**, not an assertion that the entire output is invariant across all VMs. There is no need to guess source line numbers in the stack trace.

**Why did `Main` compile?** Because `out/lib` was present at compile time. **Why did it fail at runtime?** Because only `out/app` was present at runtime, with no source from which to load `Formatter`. This is the clearest example separating the two classpaths.

### Step 5 — Run again after fixing the path

Add `out/lib` back to the runtime classpath as in step 3 and run again; the program's output will return to the two success lines. For a process that has already encountered an initialization or linkage error in an active class loader, fixing the classpath typically requires **launching a new process**; you cannot simply modify files and expect the running loader to reconfigure itself.

## 5. Compile Time and Runtime Can Have the Same Name but Different Versions

A trickier error than a completely missing class: **both environments have `com.acme.lib.Formatter`, but the actual bytecode differs**.

For example, compile-time has library v1:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String format(String value) {
        return "v1:" + value;
    }
}
```

The application is compiled with the call `Formatter.format("Java")`. After deployment, runtime uses version v2 instead:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String render(String value) {
        return "v2:" + value;
    }
}
```

The two snippets are **two mutually replacing versions of the same binary name**, not two files compiled simultaneously into the same output. If at runtime the JVM loads version v2, which no longer has `format(String)`, the compiled call in `Main.class` still references the old method signature. When the JVM resolves that call, it can throw:

```text
java.lang.NoSuchMethodError: 'java.lang.String com.acme.lib.Formatter.format(java.lang.String)'
```

A similar situation occurs when deleting/changing a field (`NoSuchFieldError`), changing a method between instance and static, replacing a class with an interface, or changing inheritance relationships in a binary-incompatible way.

Therefore, you should not only check “Does the JAR exist?”; you must check **the exact version loaded at runtime** and the ABI that the compiled code expects.

### Bytecode compatibility is not always source compatibility

- **Source compatibility:** can the source code be recompiled against the new API?
- **Binary compatibility:** can a previously compiled `.class` file still link/run against the new API?
- **Behavioral compatibility:** it runs, but does the result match expectations?

A dependency change can prevent source from compiling while the old binary still runs; or old source compiles against version A while runtime loads version B and produces `NoSuchMethodError`. These three concepts need to be distinguished when diagnosing issues.

## 6. ClassLoader Determines Which Class Is Actually Visible at Runtime

Even a properly configured classpath must still take into account **the class loader handling the request**.

In a Java application running on a simple classpath, the application/system loader typically searches for classes in the paths provided by the launcher. However, in containers, plugin frameworks, servlet containers, or module systems, multiple loaders can have different visibility scopes.

```text
Application / Parent Loader
    |- app.Main
    |- lib.Formatter v1
    |
    +-- Plugin Loader
            |- plugin.Entry
            |- lib.Formatter v2
```

With parent-first delegation, a `PluginLoader.loadClass("lib.Formatter")` request can be satisfied by the parent with v1 **before** the child loader ever reaches v2. Even though the v2 JAR is present in the plugin's directory, the class actually loaded is still version v1.

Conversely, intentionally configured child-first delegation can pick version v2 in the plugin first; in that case, two loaders can define two versions with the same name. However, if the plugin's own library type is passed across a host API that uses version v1, there is a risk of `ClassCastException` or `LinkageError` related to type identity.

### Type identity also depends on the defining loader

A runtime type is identified by the pair **(binary name, defining loader)**. Two independent loaders defining `lib.Formatter` create two distinct types, even when the bytecode is identical.

Therefore, to diagnose which class is actually being used, you can print:

```java
static void describe(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
    System.out.println("source="
            + (cs == null ? "<unknown>" : cs.getLocation()));
}
```

This is a **helper method** that must be placed in an application class and called with an already-loaded `Class<?>` object; it is not a standalone `main` program. `getClassLoader()` returns `null` when a class is defined by the bootstrap loader. `CodeSource` can be `null`, especially for platform classes, modules, or custom-defined classes. Do not conclude that the classpath is wrong solely because `source=<unknown>`.

**TCCL is not synonymous with defining loader:** `Thread.currentThread().getContextClassLoader()` is only a context loader that certain APIs, such as service discovery, choose to use when looking up dependencies; it does not itself change the loader that defined a specific class.

## 7. When Errors Appear Depends on Loading and Linking

Sometimes an application runs for several seconds before reporting a missing class, even though the library was absent from runtime from the start. This relates to the class lifecycle:

1. **Loading:** the JVM locates the class definition when needed; the superclass and superinterfaces are structural dependencies required when defining the class.
2. **Linking:** verifier, preparation, and resolution of the constant pool. Resolution may occur eagerly or when the reference is used, within the bounds of the specification.
3. **Initialization:** when active use requires it, the JVM initializes the class and any dependencies that need initialization according to the JLS/JVMS rules.

Example:

```java
class OptionalFeature {
    static void run() {
        LibraryOnlyAtRuntime.execute();
    }
}
```

This is **illustrative code, not a standalone runnable program**; it assumes `LibraryOnlyAtRuntime` is present at compile time. The fact that a code path has not yet executed does not prove that all dependencies are present; the JVM may resolve references at a different time and fail when the feature is used.

On the other hand, a missing direct or indirect superclass or superinterface of the class being defined can cause class loading to fail **even before any method is invoked**.

Therefore, you should not rely solely on when the stack trace appears to conclude that the error lies only in the Java statement currently displayed. You must examine **which dependent class the JVM was looking for at that moment**, which loader was involved, and whether linking/initialization was involved.

## 8. Typical Error Types When Compile and Runtime Classpaths Differ

| Error / Symptom | Likely Interpretation | What to Check |
| --- | --- | --- |
| Compile: `package com.acme.lib does not exist` | Compile classpath is missing the library | `javac -cp`, dependency scope, path to JAR/classes |
| Compile: `cannot find symbol` | The compiler cannot resolve a type, method, or field name | Import, package name, API version, source path |
| Runtime: `Could not find or load main class` | The launcher cannot find or load the entry class | Runtime `-cp`, package root, main name, JAR manifest |
| Runtime: `ClassNotFoundException` | An API such as `Class.forName` / `loadClass` looked up a class by name and did not find it | Binary name, requested loader, where the file/JAR is located |
| Runtime: `NoClassDefFoundError` | The JVM cannot use an expected class; usually a missing dependency or a class that previously failed initialization | `Caused by` chain, first error, packaged dependencies |
| Runtime: `NoSuchMethodError` / `NoSuchFieldError` | Binary is running against an API version different from compile time | Runtime class location, method/field ABI, dependency conflicts |
| Runtime: `IncompatibleClassChangeError` | Incompatible change regarding class/interface, static/instance, or type hierarchy | Compile/runtime JARs and method descriptors |
| Runtime: `UnsupportedClassVersionError` | Class was compiled for a newer JVM than the one running it | `java -version`, target/release, JDK pipeline |
| Runtime: `ClassCastException` between classes with the same name | Possibly caused by two independent defining loaders | `clazz.getClassLoader()` on both sides |
| Runtime: `ServiceConfigurationError` | Service provider is missing or cannot load/initialize/execute the SPI | Provider JAR, `META-INF/services`, loader, module config |

**Read the cause, not just the error type.** `NoClassDefFoundError` does not automatically mean “the classpath is definitely missing something”: a previously failed initializer can leave the class in an erroneous state, causing subsequent calls to throw the same error type. `ClassNotFoundException` can often appear in the `Caused by` chain of `NoClassDefFoundError` when the loader fails to find a dependency.

**Being on the classpath does not guarantee usability.** A library may contain a class with the right name yet be compiled for a higher Java version, lack a transitive dependency, be invisible to the classloader, or have package access disallowed by JPMS.

## 9. Direct, Transitive, and Runtime Dependencies

An application can compile against `A.jar` while A also uses `B.jar`. If B is missing at runtime, the code fails only when the execution path needs B. With Gradle, `compileOnly` is on the compile classpath but does not automatically enter the runtime classpath; `runtimeOnly` works in the opposite direction. Maven's `provided` means the deployment environment is expected to supply the appropriate dependency.

| Symptom | What to Cross-Check |
| --- | --- |
| Compilation succeeds, runtime is missing a class | `compileClasspath` and `runtimeClasspath`, and the JARs present at runtime |
| Class is found, method is missing | Runtime class version compared with compile-time signature |
| Dependency exists in build but is missing on deployment | Final artifact, launcher, and distribution, not just the build declaration file |

The article **Differences Between Build Tool Dependencies and Actual JVM Paths** focuses on configurations/scopes, resolution, and how a plain JAR differs from the `run` task. In the current article, follow *when the JVM needs to load/link a class* and analyze the first error.

## 10. Running a JAR: Differences Between -jar and -cp

Example packaging the entry class into `app.jar`:

```bash
jar --create --file app.jar --main-class com.acme.app.Main -C out/app .
```

This command only places the classes in `out/app` into `app.jar` following the existing structure; it **does not automatically include** `Formatter.class` located in `out/lib`.

If you use:

```bash
java -jar app.jar
```

The runtime will lack the dependency unless it is supplied through mechanisms supported by the Java launcher/JAR manifest. A standard executable JAR can use the **manifest `Class-Path`** attribute pointing to external dependency JARs (relative paths following manifest rules), or it can be built as an uber/fat JAR using an appropriate packaging tool.

Do not expect:

```bash
java -cp out/lib -jar app.jar
```

to automatically add `out/lib` to the user classpath for `-jar` mode as when invoking a main class with `-cp`. According to the launcher contract, when `-jar` is used, the classpath specified by `-cp` is ignored when locating user classes; the manifest and how the JAR is packaged are what you must inspect.

For a **plain JAR**, you can run by specifying the main class name and a classpath containing both the JAR and its dependencies:

Linux/macOS:

```bash
java -cp "app.jar:out/lib" com.acme.app.Main
```

Windows:

```powershell
java -cp "app.jar;out/lib" com.acme.app.Main
```

The choice between `java -jar` and `java -cp` must match the artifact type. For example, an executable JAR packaged by a framework with nested JARs has its own launcher; a plain Java classpath command may not see the nested libraries the way a user might expect.

## 11. Classpath, Module Path, and Environments from Java 9 Onward

Starting with Java 9, JPMS added the **module path**. When using named modules, key options include:

- `--module-path` / `-p`: search path for modules (modular JARs or exploded modules).
- `--module` / `-m`: tells the launcher to run the main class of a named module.
- `requires`: module readability relationship declared in `module-info.java`.
- `exports`: package that a module allows access to at the module level.
- `opens`: package opened for reflective access according to JPMS rules.

**The module path is not a “new classpath” with identical semantics.** On the traditional classpath, code typically resides in the unnamed module; on the module path, module resolution and visibility/encapsulation introduce additional constraints.

If an application compiles successfully because a module was present on the compile module path, yet the runtime module graph lacks it, an error can occur immediately when the Java launcher resolves the graph, such as a message like:

```text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module ... not found, required by ...
```

The `...` placeholders here **illustrate where module names appear**, not fixed stdout. The proper action is to check the runtime module path, module names, and the resolved graph, rather than randomly adding a JAR to the classpath and expecting a named module to read it.

You should not fix module encapsulation errors by haphazardly altering the classpath: if `exports`/`opens` or module readability is missing, the error type and solution differ from a completely missing `.class` file.

## 12. Practice: Verifying Compile and Runtime Classpaths

You can follow a systematic procedure, especially for “works in IDE, fails in production” cases:

1. **Record the actual compilation command.** Do not merely note “I used javac”: capture the compile classpath or the classpath provided by the IDE/Gradle/Maven; save the resolved dependencies and versions.
2. **Record the actual launch command.** Inspect the exact `java` command line, `-cp`, `-jar`, `--module-path`, working directory, environment, and JVM launch options.
3. **Inspect packaged files.** For plain JARs you can use `jar --list --file app.jar` or `jar tf app.jar`; note that nested JARs/framework launchers have their own rules.
4. **Verify binary name and root path.** Class `com.acme.app.Main` must be located via the root containing `com/acme/app/Main.class`, not a root nested inside a package directory.
5. **If there is a linkage error, identify which class was actually loaded.** Inspect the defining loader and code source when the class can be loaded.
6. **Check for duplicate classes across JARs and version conflicts.** Two JARs containing the same binary name do not mean the JVM automatically picks the newest version; ordering and loader selection matter.
7. **Compare the compile JDK with the runtime JDK.** A higher class file target version can cause `UnsupportedClassVersionError`.
8. **Read the `Caused by` chain and the first error in the log.** Secondary symptoms following an initialization failure can mask the root cause.

### Useful command-line tools

```bash
java -version
javac -version
jar tf app.jar
javap -classpath out/app -public com.acme.app.Main
```

- `java -version` and `javac -version` help detect when two different JDKs/JREs are selected.
- `jar tf` shows the contents inside the artifact (it does not show all external dependencies).
- `javap -classpath ...` lets you inspect the compiled class/bytecode structure in the specified root/JAR, which is useful when you suspect the running code does not match the source.

To observe class loading on a JVM supporting unified logging (JDK 17+):

```bash
java -Xlog:class+load=info -cp "out/app:out/lib" com.acme.app.Main
```

The example command uses the Linux/macOS separator; on Windows, change `:` in `-cp` to `;`. The class-load log helps identify which source many classes are loaded from, though it can be very long; distinguish the bytecode source from the **defining loader** and focus on the exact class experiencing the error.

### Classpath directly inside the JVM

For an application running strictly on the classpath, you can print:

```java
System.out.println(System.getProperty("java.class.path"));
```

This is an **illustrative snippet**, not a standalone program. This value is useful for inspecting the user classpath configured by the Java launcher, but **it does not represent every URL of every custom class loader**, the module path, or dynamic bytecode sources. Therefore, not seeing a plugin JAR in the property string is not enough to conclude that the plugin loader cannot load it.

## 13. Common Misconceptions

| Assumption | Reality |
| --- | --- |
| “If `javac` can compile it, the JVM will always see those classes.” | Compile classpath and runtime classpath are independent; the build does not automatically package every JAR used for compilation. |
| “Since `-d out/app` was used, `java` automatically knows to search in out/app.” | You must specify an appropriate runtime path such as `java -cp out/app ...`. |
| “Having the JAR on the classpath guarantees the JVM uses the right library version.” | Duplicate JARs/classes with the same name may exist, a parent loader may prioritize another version, or the module graph may not use that JAR. |
| “`-cp` always applies when combined with `-jar`.” | `-jar` mode uses classpath rules from the JAR/manifest and does not use `-cp` to locate user classes in the usual way. |
| “`lib/*` automatically scans every JAR in all subdirectories.” | The launcher wildcard is not recursive file discovery; you must package and lay out directories properly. |
| “Seeing `NoClassDefFoundError` always means a JAR is missing.” | It could be a missing dependency, or a class that previously failed initialization; you must check the cause and context. |
| “`NoSuchMethodError` cases are unrelated to the classpath.” | Very often it happens because runtime loads a library version with a different ABI than compile time. |
| “Having the `CLASSPATH` environment variable means you don't need to check the command.” | Explicit `-cp`/`--class-path` can change/override the default classpath; launch tools/frameworks can also set it themselves. |
| “`--release 17` packages Java 17 dependencies.” | `--release` controls the compilation target; it does not bundle third-party libraries into the artifact. |
| “All classes use the system classpath.” | Custom class loaders, parent delegation, and JPMS can create multiple search scopes. |

## 14. Self-Check Questions

**Question 1.** `javac -cp lib/api.jar -d classes Main.java` runs successfully. If `Main` uses a class from `api.jar`, is `java -cp classes Main` guaranteed to run?

**Answer:** No. The runtime needs the dependency when the class is used; if the JVM cannot find the API class, a loading/linkage error can occur. You must include the dependency in the runtime classpath or the corresponding launcher mechanism.

**Question 2.** On Windows, what character separates the two classpath roots `out/app` and `out/lib`?

**Answer:** The `;` character. In PowerShell, use `java -cp "out/app;out/lib" ...` to keep the classpath argument as a single string.

**Question 3.** On Linux, `java -cp out/app com.acme.app.Main` reports `NoClassDefFoundError: com/acme/lib/Formatter`, even though compilation used `-cp out/lib`. What is the most immediate direct cause to check?

**Answer:** Runtime omitted `out/lib`. Use `java -cp "out/app:out/lib" com.acme.app.Main`.

**Question 4.** Runtime has `Formatter.class`, yet reports `NoSuchMethodError` when calling `Formatter.format(String)`. Why?

**Answer:** Runtime may have loaded a version of `Formatter` with a different ABI from the one `Main.class` was compiled against; you must compare the actual class, method signature, and JAR version.

**Question 5.** A plugin has JAR v2, but the parent loader has already loaded a class with the same name from JAR v1. Is adding JAR v2 to the plugin classpath guaranteed to fix it?

**Answer:** No. Parent-first may continue returning version v1. You need to check the defining loader and design appropriate delegation/API boundaries.

**Question 6.** `java -jar app.jar` cannot find a dependency, and adding `-cp lib/*` alongside `-jar` still fails. How should you handle this?

**Answer:** Check the executable JAR type, the manifest `Class-Path`, the framework launcher mechanism, or run the main class with `-cp` containing both app.jar and its dependencies if it is an appropriate plain JAR.

**Question 7.** Why can `Class.forName("com.acme.lib.Formatter")` throw `ClassNotFoundException` whereas invoking already-compiled code throws `NoClassDefFoundError`?

**Answer:** `Class.forName` surfaces a class-lookup exception through the API; when the JVM is resolving a compiled bytecode dependency, a linkage error due to an unavailable class can be `NoClassDefFoundError`. You must read the cause chain to determine the mechanism that triggered the failure.

## 15. Reliable Deployment Checklist

Before considering a build ready to run in another environment:

- [ ] The deployment artifact contains the **exact** main class, application classes, and all required runtime dependencies, or has a clear contract for dependencies provided by the environment.
- [ ] The runtime JDK is compatible with the target class files and libraries.
- [ ] The launch command uses the correct `-cp` / `-jar` / `--module-path` for the chosen packaging format.
- [ ] No wrong dependency version is accidentally used due to JARs with duplicate binary names or a parent-first class loader.
- [ ] A smoke test has been run using the **actual artifact and launch command** in an environment as close to production as possible.
- [ ] When an error occurs, collect the full stack trace, class loader, bytecode source, and resolved dependency graph.

## 16. Conclusion and References

The compile-time classpath answers the question **“which types must the compiler locate to produce valid bytecode?”**; the runtime classpath answers **“which types can the JVM and class loaders actually locate, load, and link when the program executes?”**. The two dependency sets can differ in **directories, JARs, versions, and delegation behavior**. To avoid errors, verify the compile configuration, runtime launch configuration, and deployed artifact rather than inferring from a “BUILD SUCCESSFUL” message.

Official documentation:

- Java SE 17 `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 `java` launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification 17 §5, Loading, Linking, and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
