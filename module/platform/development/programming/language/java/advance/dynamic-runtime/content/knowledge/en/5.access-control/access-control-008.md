# 5.8 Role and Scope of `--add-exports` and `--add-opens` in Experiments

## 1. Objectives and Context

Since Java 9, the **Java Platform Module System (JPMS)** allows a module to control which packages are exposed to code in other modules and which packages allow deep access via Reflection. The two command-line options `--add-exports` and `--add-opens` are ways to **grant scoped access for a single compilation/run or for an experimental environment**, when you do not want to or cannot immediately modify `module-info.java` of the module owning the package.

This lesson focuses on how to choose the right option, accurately identify the **source module / package / target module**, demonstrate the difference through runnable programs on Java 17+, read errors according to their true nature, and manage the impact scope of an experiment.

After this lesson, you can:

- Distinguish **readability**, **exports**, **opens**, and **Java access modifiers**.
- Explain that `--add-exports` lets code in another module use the **public API of a non-exported package**, whereas `--add-opens` allows **deep reflection at runtime** on that package.
- Know where to apply flags in `javac` and in the **JVM that actually runs the application or tests**, as well as the difference between `ALL-UNNAMED` and a **named module**.
- Build an experimental module yourself, reproduce compilation errors, `IllegalAccessError`, `trySetAccessible()` results, and the effect of each flag.
- Know the limits of the flags: permission is for a **specific package and target module**, does not turn private into public at the language level, does not automatically resolve all module readability relationships, and does not permanently modify module files.

> **Principle:** Both flags are isolation tools to investigate compatibility, test, or diagnose a dependency accessing a closed package. A successful experiment does not prove that depending on internal APIs is stable for a long-term application.

## 2. Access Control Model: Four Layers Must Be Distinguished

A cross-module call can pass through several different conditions:

| Layer | Question | Tool/Concept |
| --- | --- | --- |
| **Module readability** | Can the calling module read the module providing the type? | `requires` in `module-info.java`, module graph, `--add-reads` when truly needed |
| **Package exported** | Is normal code allowed to reference **public types** of that package? | `exports` or `--add-exports` |
| **Package open** | Is a framework allowed to use Reflection for deep access to non-public members/types? | `opens`, `open module`, or `--add-opens` |
| **Java/member rules** | Is the class/member itself `public`, `protected`, package-private, or `private`? | Java access control, `setAccessible` / `trySetAccessible` when appropriate |

These are related but **do not replace each other**.

For example, a package that has already been `exports`ed can still contain a `private` field. Code from another module may call the appropriate public API, but `Field.setAccessible(true)` to read the private field can be blocked by the module system if the package has not been `opens`ed.

Conversely, a package being `opens`ed for reflective access at **runtime** does not mean source code in another module has permission to `import` a public type of that package at **compile time**. Compile-time references still require an appropriate export.

If code uses a named module `app.module` to access module `lib.module`, `app.module` also needs to **read** `lib.module` (normally via `requires lib.module;`). `--add-exports` is not a way to automatically add every missing `requires`. For code placed on the **class path**, classes normally belong to the **unnamed module**, and the target will be specified with `ALL-UNNAMED` in the experiments below.

## 3. Exact Syntax and Meaning of Each Option

### 3.1. `--add-exports`: Adding an Export for a Package

Syntax:

```text
--add-exports=<source-module>/<package>=<target-module>[,<target-module>...]
```

Examples:

```text
--add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED
--add-exports=demo.lib/demo.lib.internal=demo.app
```

Where:

- `demo.lib` is the **module owning the package**.
- `demo.lib.internal` is the **exact package name** inside that module.
- `ALL-UNNAMED` is all unnamed modules, including class path code; it is **broader than a single specific JAR**.
- `demo.app` is the name of a **named module**, used when extra export permission only needs to be granted to that module.

The flag causes the package to be treated as **additionally exported** to the target module in the appropriate context; target code can reference **public types and public APIs** of the package without being blocked by JPMS export barriers, provided readability and access modifier conditions are also satisfied.

`--add-exports` is used at **compile time with `javac`** when source code needs to import a non-exported public type; it is also needed at **runtime with `java`** if the compiled program still accesses such a type through normal linkage. Passing the flag only to `javac` does not guarantee the running JVM will be granted the same permission.

The flag **does not grant private reflection permission**. When a non-public `Field` or `Method` needs `setAccessible`, export alone is usually not enough.

### 3.2. `--add-opens`: Opening a Package for Deep Reflection at Runtime

Syntax:

```text
--add-opens=<source-module>/<package>=<target-module>[,<target-module>...]
```

Examples:

```text
--add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED
--add-opens=java.base/java.time=ALL-UNNAMED
--add-opens=demo.lib/demo.lib.internal=demo.app
```

This flag opens a package at **runtime** for the target module to perform **deep reflection**, for example:

- `Field.trySetAccessible()` or `Field.setAccessible(true)` on a private field.
- Non-public `Method`/`Constructor` enabled for deep access when Reflection rules allow.
- A framework such as a serializer, ORM, proxy/DI, or test tool that has a valid reason to manipulate non-public metadata.

Opening a package also allows public access at runtime within the opened scope, but **does not grant a compile-time export** so that source code in another module can directly import public types. Therefore, `javac` may accept the `--add-opens` option only to warn that it **has no effect at compile time**.

Note: **having an open package** does not mean any arbitrary Reflection operation will succeed. There are still rules regarding how calls are made, target objects, data types, final fields, and specific API limitations. The flag only resolves the JPMS package openness barrier.

### 3.3. Brief Comparison

| Criterion | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Primary goal | Let target code use public API of a non-exported package | Let target code perform deep reflective access at runtime |
| `javac` | **Effective** when compiling access to internal public types | **Does not open package at compile time** |
| `java` | Grants additional export at runtime | Grants additional open at runtime |
| Accessing private field with `setAccessible` from another module | **Not enough** | **Can allow** if other conditions are met |
| Scope | One package in one source module to target module(s) | One package in one source module to target module(s) |
| Modifies `module-info.java`? | No | No |
| Use to replace a stable public API? | Should not | Should not |

Both syntaxes `--add-exports=X/Y=Z` and `--add-exports X/Y=Z` usually work in the launcher; using `=` right after the flag name is especially convenient when configuring in IDEs/Gradle/Maven. The examples in this lesson use one consistent form for easy comparison.

## 4. Verification Experiment with a Custom Module

Instead of relying on internal classes that may change across JDKs, we create our own module `demo.lib` containing a package intentionally **neither exported nor opened**. Two programs on the class path will test public access and private reflection.

**Requirements:** JDK 17 or higher, `javac` and `java` on `PATH`. The Java commands below run from the root directory `jpms-flags-lab`.

### 4.1. Create the Directory Structure

```text
jpms-flags-lab/
├── src/
│   ├── demo.lib/
│   │   ├── module-info.java
│   │   └── demo/lib/internal/Helper.java
│   └── app/
│       ├── ExportDemo.java
│       └── OpenDemo.java
└── out/
    ├── mods/
    └── app/
```

You can create the directories before creating the files according to the diagram. With Bash (Linux, macOS, Git Bash/WSL):

```bash
mkdir -p src/demo.lib/demo/lib/internal src/app out/mods out/app
```

With Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "src/demo.lib/demo/lib/internal","src/app","out/mods","out/app"
```

The two directory-creation command blocks above are **OS-specific choices**; then create the exact four files below with their corresponding contents.

### 4.2. Library Module: Neither Exported Nor Opened

File **`src/demo.lib/module-info.java`**:

```java
module demo.lib {
    // Intentionally neither exports nor opens the internal package.
}
```

File **`src/demo.lib/demo/lib/internal/Helper.java`**:

```java
package demo.lib.internal;

public class Helper {
    private static String secret = "SECRET";

    public static String hello() {
        return "HELLO";
    }
}
```

`Helper` is a **public class**, and `hello()` is also a public method. However, package `demo.lib.internal` has not been exported, so code from another module cannot automatically reference these two members via normal static access. `secret` is a private field, helping test deep access permission.

### 4.3. Program Testing Public API Access

File **`src/app/ExportDemo.java`**:

```java
import demo.lib.internal.Helper;

public class ExportDemo {
    public static void main(String[] args) {
        System.out.println(Helper.hello());
    }
}
```

This is a class in the **unnamed module** because it will be compiled/run on the class path.

Compile the library module:

```bash
javac --module-source-path src -d out/mods -m demo.lib
```

**Try compiling `ExportDemo` without granting export:**

```bash
javac --module-path out/mods --add-modules demo.lib -d out/app src/app/ExportDemo.java
```

This command is **expected to fail** because package `demo.lib.internal` is not exported by `demo.lib`. The compiler may report an equivalent error:

```text
error: package demo.lib.internal is not visible
(package demo.lib.internal is declared in module demo.lib, which does not export it)
```

With the same module source, only change the access permission condition during compilation:

```bash
javac --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -d out/app src/app/ExportDemo.java
```

**Result:** compilation succeeds. Note that `--add-modules demo.lib` causes the module to be resolved in the class path context, while `--add-exports` adds export permission; the two options have separate roles.

**Try running without runtime export:**

```bash
java --module-path out/mods --add-modules demo.lib -cp out/app ExportDemo
```

Even though compilation succeeded, runtime is **expected to throw `IllegalAccessError`** when the code tries to access `Helper`, because the JVM running the program has not been granted the additional export. A typical error has the meaning:

```text
java.lang.IllegalAccessError: class ExportDemo (in unnamed module ...)
cannot access class demo.lib.internal.Helper (in module demo.lib)
because module demo.lib does not export demo.lib.internal
```

The `...` above is an **omission of the runtime-dependent module address/stack trace**, not the full log text to match verbatim.

**Grant export when running:**

```bash
java --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app ExportDemo
```

Exact stdout:

```text
HELLO
```

**Experiment 1 Conclusion:** `--add-exports` resolves permission to reference public types of a closed package, but it must be placed at both the **compile stage** and the **JVM runtime** when both stages check that permission.

### 4.4. Program Testing Reflection on a Private Field

File **`src/app/OpenDemo.java`**:

```java
import java.lang.reflect.Field;

public class OpenDemo {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("demo.lib.internal.Helper");
        Field field = type.getDeclaredField("secret");
        boolean opened = field.trySetAccessible();

        System.out.println("opened=" + opened);
        if (opened) {
            System.out.println("secret=" + field.get(null));
        }
    }
}
```

The program only uses the class name as a string, without importing `Helper`. `Class.forName` and `getDeclaredField` can find metadata even when the package is not exported; the **step requesting permission `trySetAccessible()`** is what checks whether deep reflection from the calling module is allowed. `field.get(null)` is valid because `secret` is a **static field**; it is only executed after permission is granted successfully.

Compile the program:

```bash
javac -d out/app src/app/OpenDemo.java
```

**Run 1 — no flags:**

```bash
java --module-path out/mods --add-modules demo.lib -cp out/app OpenDemo
```

Stdout:

```text
opened=false
```

**Run 2 — only `--add-exports`:**

```bash
java --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app OpenDemo
```

Stdout is **still**:

```text
opened=false
```

Public export is not enough to open a private field. If you replace `trySetAccessible()` with `setAccessible(true)` while the package is not open, Java may throw `java.lang.reflect.InaccessibleObjectException` instead of returning `false`.

**Run 3 — grant `--add-opens` properly:**

```bash
java --module-path out/mods --add-modules demo.lib --add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app OpenDemo
```

Stdout:

```text
opened=true
secret=SECRET
```

**Experiment 2 Conclusion:** `--add-opens` opens a package for deep reflection from the unnamed module. This experiment **does not need** `--add-exports` because `OpenDemo` has no static import to `Helper`; the lookup is via Reflection. If source code **does** have a static import to a closed package, compile-time export permission remains a separate issue.

### 4.5. Observed Result Matrix

| Program / stage | Flag applied | Result |
| --- | --- | --- |
| `javac ExportDemo.java` | No export | Compile error: package not visible |
| `javac ExportDemo.java` | `--add-exports` | Succeeds |
| `java ExportDemo` after compiling with export | No runtime export | `IllegalAccessError` |
| `java ExportDemo` | Runtime with `--add-exports` | `HELLO` |
| `java OpenDemo` | No flag | `opened=false` |
| `java OpenDemo` | Only `--add-exports` | `opened=false` |
| `java OpenDemo` | `--add-opens` | `opened=true`, `secret=SECRET` |

The seven cases above use the **same Java files**, changing only the exact JVM arguments in each run; the difference reflects the package export/open boundary of JPMS.

## 5. Short Experiment with the JDK Itself: Package Exported but Not Open

`java.time` is a public API package of module `java.base`. We can call `LocalDate.of(...)` normally, but deep access into a private field inside `LocalDate` is a different matter.

Create file **`JdkOpenExperiment.java`** (independent of the project directory in section 4):

```java
import java.lang.reflect.Field;
import java.time.LocalDate;

public class JdkOpenExperiment {
    public static void main(String[] args) throws Exception {
        Field field = LocalDate.class.getDeclaredField("year");
        boolean opened = field.trySetAccessible();
        System.out.println("opened=" + opened);

        if (opened) {
            System.out.println("year="
                    + field.getInt(LocalDate.of(2025, 3, 5)));
        }
    }
}
```

Compile with Java 17+:

```bash
javac JdkOpenExperiment.java
```

Without flags:

```bash
java JdkOpenExperiment
```

Stdout on a JDK that has field `LocalDate.year` such as JDK 17:

```text
opened=false
```

Provide the flag **only to the JVM running the example**:

```bash
java --add-opens=java.base/java.time=ALL-UNNAMED JdkOpenExperiment
```

Stdout:

```text
opened=true
year=2025
```

Points to distinguish:

- `java.base/java.time` means **package `java.time` inside module `java.base`**, not a class name.
- Package `java.time` already exports its public API; `--add-exports=java.base/java.time=ALL-UNNAMED` in this case **does not solve private reflection**.
- `year` is an **implementation detail** of `LocalDate` in the tested JDK, not a public API guaranteed to exist or keep the same shape across all JDKs. Therefore, this is only an experiment; production code should use `LocalDate.getYear()`.
- The flag takes effect when starting a **new JVM**; enabling the flag in another JVM later does not change an already running JVM.

## 6. True Scope of the Flags

### 6.1. One Package, One Source Module, Target Module Set

There is no wildcard to “open every package of every module” in the syntax of each flag. With:

```text
--add-opens=java.base/java.time=ALL-UNNAMED
```

we are opening package `java.time` belonging to `java.base` for **all unnamed modules**; it does not automatically open `java.lang`, `java.util`, packages belonging to other modules, or named modules. Nor does it mean that only **one specific JAR** on the class path receives permission: `ALL-UNNAMED` applies to all matching unnamed modules.

For a modular application with module `my.test.runner`, the scope can be narrowed:

```text
--add-opens=demo.lib/demo.lib.internal=my.test.runner
--add-exports=demo.lib/demo.lib.internal=my.test.runner
```

Those are two different permissions, and the target module name must actually match the module executing the accessing code. If a framework/library is loaded on the class path, its module is usually unnamed; writing the name of another named module will not grant permission to it.

### 6.2. One Compilation or One Specific Running JVM

- Flags passed to `javac` only affect how **that compilation** checks accessibility (where `--add-exports` has effect).
- Flags passed to `java` only affect the **JVM launched by that launcher**.
- They do not automatically propagate to child JVMs created via `ProcessBuilder`, forked test plugin JVMs, other IDE run configurations, other Gradle `Test` / `JavaExec` tasks, or an already running server process.
- Placing the flag on a command running a unit test when the error actually comes from a different worker/integration test JVM will not solve the error.

In an IDE or build tool, identify the **process that is throwing the error**. For tests run by Gradle, runtime flags need to go into the `jvmArgs` configuration of the exact `Test` task, not just the command line starting the Gradle daemon. If source code needs `--add-exports` to compile, compiler arguments must be configured separately on the exact `JavaCompile` task. In Maven or an IDE, the same principle applies: **compiler option** and **runtime VM option** are two different places.

A minimal illustrative configuration for the **Test task** in Gradle Groovy DSL:

```groovy
tasks.named('test', Test) {
    jvmArgs '--add-opens=java.base/java.time=ALL-UNNAMED'
}
```

This is only the **runtime configuration of the JVM running the `test` task**, not a flag for every build process or a standalone Java command. Add it only to experiments that truly need reflective access.

### 6.3. `--add-exports` Does Not Solve Readability, Module Resolution, or Java Modifiers

If named module `app.module` does not have a readability relationship to `lib.module`, check `requires lib.module;` or, when there is a clear reason, consider `--add-reads`. If `lib.module` is not yet resolved on the module path in the experimental setup, `--add-modules lib.module` may be needed. `--add-exports` does not replace either of those.

Even once a package is exported:

- A **private** class/member does not automatically become `public` in the Java language.
- `protected` and package-private still have their own Java rules.
- Code calling a method must use the right arguments, target object, and return type.
- `--add-exports` does not automatically enable `setAccessible(true)` and does not guarantee deep reflection will succeed.

### 6.4. `--add-opens` Is a Runtime Permission, Not “Everything Allowed”

An open package allows many deep Reflection operations to work, but does not change Java signatures or abolish all Reflection rules. For example, `final` fields have their own update restrictions; module openness does not guarantee writing to every final field. Class loading issues, unresolved modules, missing dependencies, and calling methods with wrong arguments are still separate errors.

A package inside an **open module** (declared `open module ...`) or that already has an appropriate `opens` in `module-info.java` may **not need** an additional flag. Before adding a flag, check the actual boundary in the module descriptor.

### 6.5. Java 17+ and the Old `--illegal-access` Option

Since JDK 17, JEP 403 places most JDK internals under strong encapsulation. The old `--illegal-access` option that served as a transition in Java 9–16 **no longer grants reflective access** on Java 17: using it may only produce a warning about an obsolete option. When an experiment needs to open a package, you must specify the **exact package** with `--add-opens`, instead of expecting `--illegal-access=permit`.

Some internal/critical APIs have historical exceptions (for example `sun.misc.Unsafe` in module `jdk.unsupported`), but that does not make arbitrary internal packages stable public APIs.

When compiling against JDK internal APIs, the `javac --release` option also restricts bypassing module exports of system modules; do not treat adding `--add-exports` as a guaranteed way to bypass all `--release` constraints. Experiments should clearly state the JDK used to compile and the build compatibility target.

## 7. Diagnosing Errors by the Right Barrier

| Symptom | Possibility to check | Experimental handling direction |
| --- | --- | --- |
| `package ... is not visible` on `javac` | Package of a named module is not exported to compiled code, or module is not read/resolved | Check module graph; add the right compile-time `--add-exports` if the issue is export |
| `IllegalAccessError` at runtime despite compiling | Runtime JVM lacks the corresponding export permission | Put `--add-exports` on the **JVM actually running the code**; verify module, package, target |
| `InaccessibleObjectException` on `setAccessible(true)` | Package is not open to the module performing deep reflection | Use `--add-opens` with the right package/module and right runtime |
| `trySetAccessible()` returns `false` | Runtime does not yet allow deep access to the member | Check `opens`, caller's module, and module/package declaring the member |
| `ClassNotFoundException` / `NoClassDefFoundError` | Class/dependency not found or module not yet resolved | Fix class path/module path/module resolution; the two flags do not create missing classes |
| Error only happens in test fork/IDE, not reproduced in shell | Flag was passed to a different process | Check VM options of the **exact process**, test runner, and test workers |
| Still errors after adding flag | Wrong module/package name, wrong target module, non-public member used directly, insufficient readability, or other cause | Verify `Class.getModule()`, `getPackageName()`, module graph, and stack trace |

You can systematically check the module and package of a class:

```java
// Illustrative snippet; assume Class<?> type has already been determined.
Module owner = type.getModule();
String packageName = type.getPackageName();
Module caller = OpenDemo.class.getModule();

System.out.println("owner=" + owner.getName());
System.out.println("package=" + packageName);
System.out.println("caller=" + caller.getName()); // null: unnamed module
System.out.println("exported=" + owner.isExported(packageName, caller));
System.out.println("open=" + owner.isOpen(packageName, caller));
```

**Note:** The code above is a **snippet**, used to help inspect metadata in a context where `type` and `OpenDemo` exist; it is not a standalone program. `Module.isExported(packageName, caller)` and `Module.isOpen(packageName, caller)` help check **effective permission for the exact caller module**, rather than guessing from a JAR name. For an unnamed module, `getName()` returns `null`.

In the `OpenDemo` example, we can also use `Class.forName(...)` to find the package owner, then inspect `type.getModule()`. Do not confuse package `demo.lib.internal` with module name `demo.lib` when filling in the flag.

## 8. How to Structure a Verifiable Experiment

To conclude that a flag truly solves the right issue, record:

1. **JDK + version** of `javac` and `java` (for example `java -version`, `javac -version`); ensure the program is using the expected JDK.
2. **Minimal program** showing the exact error and source/target modules; avoid adding many libraries at once.
3. **Baseline without flags**: what is the compile error, runtime error, or `trySetAccessible() == false`?
4. **Add only one flag for the right package/target**; rerun the same program to prove the change. When needed, test both compile and runtime as in section 4.3.
5. **Confirm the JVM receives the flag** via the command line or configuration of that exact process; do not rely on the parent process's configuration.
6. **Remove the flag to retest the baseline** if you need to verify causality; do not attribute a change caused by code/library versions changing at the same time.
7. **Record results and alternative paths**: supported public API, proper library configuration, library update, or changing `module-info.java` in a module you own.

A suitable short record:

| Attribute | Example |
| --- | --- |
| Java runtime | JDK 17+ |
| Source module | `demo.lib` |
| Package to access | `demo.lib.internal` |
| Target module | `ALL-UNNAMED` |
| Behavior before | `opened=false` |
| Single change | `--add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED` |
| Behavior after | `opened=true`, `secret=SECRET` |
| Conclusion that can be asserted | Package was not open to unnamed module; the runtime flag granted deep reflection permission for this experiment |
| Conclusion **not** to be inferred | Private reflection is a stable public API or all other JDKs/packages behave this way |

## 9. One-Minute Flag Selection Decision

- **Source code `import`s a public class from a non-exported package and `javac` reports package invisible?** Check the module graph, then try **`--add-exports` at compile time**. If the running binary still accesses that class, **`--add-exports` at runtime** is usually also needed.
- **Public API is already accessible, but `setAccessible(true)` is blocked when reading a private field/constructor?** Check the package owner and try **`--add-opens` on the right runtime**.
- **Only know the class name via `Class.forName`, need Reflection on a non-public member?** You may only need **`--add-opens`**, without compile-time export if there is no static reference.
- **Class not found or module not yet resolved?** Fix class path/module path, `--add-modules`, or `requires` relationship first.
- **Application in a named module?** Use the **specific target module name** when possible, instead of granting `ALL-UNNAMED` broader than needed.

In the long run, prefer updating code to use officially exported APIs; if you own the library, consider designing `exports`/`opens ... to ...` in `module-info.java` with only the truly necessary scope. Flags are **launch-time supplementary permissions**, useful for isolating compatibility causes, but should be kept in a clear configuration location with a technical rationale.

## 10. Self-Check Exercises

**Question 1.** Does `java --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED` make `Field.trySetAccessible()` on a private field in `Helper` return `true`?  
**Answer:** In the section 4 example, **no**. Export supports public access; deep reflection requires opening the appropriate package with `--add-opens`.

**Question 2.** Why does `ExportDemo` compile with `--add-exports` on `javac` yet still throw `IllegalAccessError` when run without the flag?  
**Answer:** Compile and runtime are two separate checking contexts. Extra export permission in the compiler is not automatically “packaged” into the `.class` file for another JVM to inherit.

**Question 3.** For a JUnit test running on the class path, does the `=ALL-UNNAMED` part grant permission only to that test class?  
**Answer:** No. It grants permission to **all unnamed modules**, including matching class path classes/JARs in that JVM. If narrower permission is needed, consider running tests in a named module.

**Question 4.** Does adding only `--add-opens` to the `javac` command allow source code that `import`s a public class from a non-exported package to compile?  
**Answer:** No. `--add-opens` is for runtime reflective access, not compile-time export.

**Question 5.** A named module cannot read the source module. Does adding only `--add-exports` solve the whole problem?  
**Answer:** Not necessarily. An appropriate readability relationship (`requires` or intentional read configuration) is also needed, and the source module must be resolved.

**Question 6.** Why should we test `java.base/java.time` with `--add-opens` but not keep code reading the private field `LocalDate.year` in production?  
**Answer:** That field is an implementation detail. The public API `LocalDate.getYear()` is more stable; an experimental flag does not turn internal details into a guaranteed interface.

**Question 7.** If `--add-opens` is added to the Gradle daemon but unit tests running in a forked test JVM still fail, what should you do?  
**Answer:** Configure runtime arguments for the **exact task/process running the tests**, confirming the flag is present in the JVM throwing `InaccessibleObjectException`.

## 11. Official References

- [Dev.java — Circumventing Strong Encapsulation with `--add-exports` and `--add-opens`](https://dev.java/learn/modules/add-exports-opens/): examples of compile-time export, runtime export, deep reflection, and package-opening scope.
- [Oracle Java SE 17 — `java` launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): module system options when launching the JVM.
- [Oracle Java SE 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--add-exports` rules at compile time, module graph, and `--release` limitations.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): why JDK 17 is stricter about reflective access into JDK internals.
- [Oracle Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible()`, `setAccessible(true)`, and access permission conditions across different modules.
- [Oracle Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isExported()`, `isOpen()`, and the concept of module openness.