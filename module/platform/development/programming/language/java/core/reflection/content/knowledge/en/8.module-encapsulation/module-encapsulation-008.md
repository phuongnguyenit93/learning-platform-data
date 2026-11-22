# Distinguishing `--add-exports` from `--add-opens` in the Java Module System

## 1. Why Are These Two Options Needed?

Since Java 9, the Java Platform Module System (JPMS) manages both **module dependencies** and **package visibility**. A class declared `public` is still not guaranteed to be usable from another module: its package may not have been `exports`-ed. On the other hand, a framework using Reflection sometimes needs to read non-public constructors, fields, or methods that normal access permissions still disallow.

Two command-line options let you add exceptions to module configuration:

- **`--add-exports`**: exports a package of a source module to a target module, so the target module can use **public types and accessible members under Java rules**, including direct access at compile time and runtime. It **does not automatically open access to private fields/methods**.
- **`--add-opens`**: opens a package to a target module to perform **deep reflection at runtime**, such as `getDeclaredField(...)` followed by `trySetAccessible()` / `setAccessible(true)`. It **does not turn that package into an exported package for the compiler**.

Both are exceptions to *strong encapsulation*. When designing a module you own, consider declaring `exports` / `opens` intentionally in `module-info.java` before reaching for command-line flags. When compatibility with legacy libraries is required, open only the right package to the right module that needs it.

## 2. Quick Comparison

| Criterion | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Primary purpose | Allows using the `public` API of an encapsulated package | Allows Reflection deep access even to non-public members |
| Direct access from Java source outside the module | **Yes**, for types/members permitted by Java visibility | **Does not grant compile permission** for imports or direct calls |
| Use with `javac` | **Effective** during compilation | Does not open compile permission; `javac` warns the option has no effect at compile time |
| Use with `java` | **Effective** at runtime | **Effective** at runtime |
| Allows `trySetAccessible()` on private members in target package | **No**, exporting alone is not enough | **Possible**, if the package is open to the caller's module and no other restrictions apply |
| Preserves `private`, package-private, `protected` rules on direct access | **Yes** | **Yes**; deep reflection still requires using the Reflection API |
| Equivalent in `module-info.java` | `exports some.package;` or `exports some.package to target.module;` | `opens some.package;` or `opens some.package to target.module;` |

**Do not oversimplify to "exports for public, opens for private"**: `opens` also allows Reflection on public members, while `exports` enables regular reflective access to public types/members that already meet access conditions. The real difference is **API access under Java language rules** versus **deep reflection permission**.

## 3. Syntax and Meaning of Each Part

Both options follow the pattern:

~~~text
--add-exports <source-module>/<package>=<target-module>[,<target-module>...]
--add-opens   <source-module>/<package>=<target-module>[,<target-module>...]
~~~

Examples:

~~~bash
java --add-exports=demo.vault/internal.api=demo.client ...
java --add-opens=demo.vault/internal.api=demo.framework ...
java --add-opens=demo.vault/internal.api=ALL-UNNAMED ...
~~~

- `demo.vault` is the **module containing the package** to export/open.
- `internal.api` is the **full package name**, not a class or method name.
- `demo.client` or `demo.framework` is the **module granted permission**.
- `ALL-UNNAMED` is the special target for **all unnamed modules** (typically code loaded from the classpath, including JAR libraries on the classpath). Its scope is broader than a specific named module.
- Multiple named modules can be listed on the right-hand side, separated by commas.
- Both `--add-opens=module/package=target` and `--add-opens module/package=target` forms are supported by the Java launcher; the form with `=` after the option name is convenient when configuring JVM arguments in certain tools.

These two flags **do not automatically add module readability**. For a named module wanting to use a dependency, `requires demo.vault;` in `module-info.java` or an appropriate mechanism like `--add-reads` is still needed. For applications on the classpath, if `demo.vault` is on the module path without being resolved into the module graph, `--add-modules demo.vault` may be needed.

Note: the target name in the command is the **module of the code consuming the API or performing Reflection**, not necessarily the module containing the class whose data the application is processing.

## 4. Compilable and Runnable Java 17+ Example

We will create a named module `demo.vault` containing a public class, **without exporting its package**. Two programs on the classpath will separately attempt **calling a public method directly** and **using Reflection on a private method**. This lets us observe the exact effect of each flag without relying on unstable internal JDK classes.

### 4.1. Directory Structure

~~~text
project/
├── src/
│   └── demo.vault/
│       ├── module-info.java
│       └── internal/
│           └── api/
│               └── PublicTool.java
├── client-src/
│   ├── DirectMain.java
│   └── ReflectMain.java
├── mods/                 (generated on compile)
└── out/                  (generated on compile)
~~~

File `src/demo.vault/module-info.java`:

~~~java
module demo.vault {
    // No exports or opens for internal.api.
}
~~~

File `src/demo.vault/internal/api/PublicTool.java`:

~~~java
package internal.api;

public final class PublicTool {
    private PublicTool() { }

    public static String greet() {
        return "hello";
    }

    private static String secret() {
        return "hidden";
    }
}
~~~

File `client-src/DirectMain.java`:

~~~java
import internal.api.PublicTool;

public class DirectMain {
    public static void main(String[] args) {
        System.out.println("direct: " + PublicTool.greet());
    }
}
~~~

File `client-src/ReflectMain.java`:

~~~java
import java.lang.reflect.Method;

public class ReflectMain {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("internal.api.PublicTool");
        Method method = type.getDeclaredMethod("secret");

        boolean opened = method.trySetAccessible();
        System.out.println("private opened: " + opened);

        if (opened) {
            System.out.println("reflect: " + method.invoke(null));
        }
    }
}
~~~

`ReflectMain` does not import `PublicTool`: it knows the class name only as a string. The `secret` method is `private static`, so `method.invoke(null)` uses the proper receiver type once permission is opened. `trySetAccessible()` returns `false` when the package is not opened to the caller's unnamed module.

### 4.2. Creating Output Directories and Compiling

Inside the `project` directory, create the output directories first. Bash example (Linux/macOS):

~~~bash
mkdir -p mods/demo.vault out
~~~

In PowerShell (Windows), you can use:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/demo.vault,out
~~~

The following `javac` commands apply identically in both environments:

~~~bash
javac -d mods/demo.vault src/demo.vault/module-info.java src/demo.vault/internal/api/PublicTool.java

javac --module-path mods --add-modules demo.vault --add-exports demo.vault/internal.api=ALL-UNNAMED -d out client-src/DirectMain.java client-src/ReflectMain.java
~~~

In the second compilation, `DirectMain` **directly imports** a class from an unexported package. Therefore `--add-exports` must be passed to **`javac`**. If you omit this flag, the compiler reports that package `internal.api` is not visible from module `demo.vault`.

`--add-modules demo.vault` ensures the named module on the module path is resolved. Here `--add-exports` grants permission only to unnamed modules, matching `DirectMain`'s location on the classpath.

### 4.3. Running the Direct Access Example: `--add-exports` Needed at Runtime

~~~bash
java --module-path mods --add-modules demo.vault --add-exports demo.vault/internal.api=ALL-UNNAMED -cp out DirectMain
~~~

Stdout:

~~~text
direct: hello
~~~

**Why is the flag still needed at runtime?** The `javac --add-exports` flag affects only compilation. It does not permanently write an export permission into `demo.vault`. If you run the compiled program without the runtime flag, linking/accessing the unexported class can result in `IllegalAccessError`.

Using **only `--add-opens` on `javac` does not solve the import error**, because opening a package for runtime Reflection is not exporting the package for compile-time source code.

### 4.4. Running the Reflection Example: `--add-opens` Needed

Run first **without granting package-opening permission**:

~~~bash
java --module-path mods --add-modules demo.vault -cp out ReflectMain
~~~

Stdout:

~~~text
private opened: false
~~~

Reflection still finds the method metadata via `getDeclaredMethod("secret")`, yet cannot enable permission to invoke a `private` method in a package not opened to the caller.

Add **`--add-opens`**:

~~~bash
java --module-path mods --add-modules demo.vault --add-opens demo.vault/internal.api=ALL-UNNAMED -cp out ReflectMain
~~~

Stdout:

~~~text
private opened: true
reflect: hidden
~~~

Now package `internal.api` is opened to the unnamed module; `trySetAccessible()` can set the flag suppressing access checks and `Method.invoke` invokes the `private` method. **`--add-exports` is not needed** for `ReflectMain`, because it does not import or statically reference `PublicTool`.

### 4.5. Summary Results

| Task | `--add-exports` Only | `--add-opens` Only |
| --- | --- | --- |
| Compile `DirectMain` with `import internal.api.PublicTool` | Yes, if the module is resolved and proper readability exists | No |
| Run validly compiled `DirectMain` | Sufficient for public API access at runtime | Not the right configuration for original compile permission; do not use instead of `--add-exports` |
| Enable `trySetAccessible()` for `private secret()` from `ReflectMain` | No, unless another open permission exists | Yes in this example |
| Access `public` methods via normal Reflection | Possible, under Java access rules | Possible, under reflective access rules |

The example was verified on OpenJDK 21 (code and options JDK 17 compatible): `direct: hello`; `private opened: false`; `private opened: true` then `reflect: hidden`.

## 5. Comparing with `exports` and `opens` in `module-info.java`

A module author can declare permissions intentionally:

~~~java
module demo.library {
    exports demo.library.api;
    exports demo.library.spi to demo.plugin;

    opens demo.library.model to demo.framework;
}
~~~

This is a **configuration illustration**; compiling requires the corresponding packages and target modules.

- `exports demo.library.api;`: every module that can read this module may use the package's public API.
- `exports ... to demo.plugin;`: only `demo.plugin` receives the specified export permission.
- `opens ... to demo.framework;`: opens the package so the framework can use Reflection on members, including non-public ones, at runtime. It does not let the framework's code directly import types that were not exported at compile time.
- You can **both `exports` and `opens` a package** when both public API and deep reflection are needed.
- `open module demo.library { ... }` opens every package in that module for Reflection. This is broader than opening individual packages; an `open module` does not declare additional individual `opens`.

Command-line flags add the corresponding export/open edges **for the compiling or running process**, even if the original module does not declare them. They do not modify the published `module-info.java` file.

## 6. Diagnosing Errors and Choosing the Right Flag

### Case A: Import Error at Compile Time

Messages typically read like:

~~~text
package ... is not visible
(package ... is declared in module ..., which does not export it)
~~~

If the code **truly must directly reference the public API** in that package, consider `--add-exports` for `javac` and the launch command. First check if a supported public API exists in another package. `--add-opens` will not make the import compile.

### Case B: `IllegalAccessError` at Runtime

Often happens when code compiled with access permission runs on a JVM without the same export permission, or when the module environment differs from the build. Compare `--add-exports` configuration between **compile** and **runtime** and inspect the module graph. Do not rush to add `--add-opens` just because you see the word "Access".

### Case C: `InaccessibleObjectException` or `trySetAccessible() == false`

If the stack trace/condition indicates the package is not **opened** to the module calling Reflection, the appropriate flag is usually:

~~~bash
java --add-opens=source.module/source.package=target.module ...
~~~

For a legacy application running on the classpath, the target may be `ALL-UNNAMED`. Even after opening the package, other API constraints still apply: valid receiver type, `final` behavior, field mutability, and environment policies.

### Case D: Class/Module Not Found

`ClassNotFoundException` or module-not-found messages are **not automatically solved** by `--add-exports` / `--add-opens`. Check `--module-path`, `-cp`, module names, and module resolution (e.g., `--add-modules`) first. If a named module needs to read another module without an existing readability edge, consider `requires` or appropriate `--add-reads`.

## 7. Safe, Sustainable Usage Rules

1. **Prefer supported APIs.** Internal JDK/library packages can change across upgrades; replacing Reflection code with official APIs avoids maintaining flags.
2. **Open minimal permissions.** Choose a specific package and target named module whenever possible. `ALL-UNNAMED` grants broad permission to all code on the classpath.
3. **Place flags on the right JVM.** With `java -jar app.jar`, JVM arguments must appear **before `-jar`**. Test runners, IDEs, Gradle/Maven test forks, or containerized apps have their own JVMs and need the configuration on the Java process actually running the code.
4. **Distinguish compile and run.** `--add-exports` may be needed for both; `--add-opens` serves only runtime Reflection. Passing `--add-opens` to `javac` grants no compile-time permission.
5. **Do not treat flags as an API contract.** Having Reflection permission does not guarantee the operation succeeds: target object types, `final` fields, data types, exceptions from invoked methods, and other restrictions still apply.
6. **Check the Java version.** In JDK 17, strong encapsulation of JDK internals is enforced by default; the legacy `--illegal-access` option no longer opens permissions as in older versions.

## 8. Self-Check

**Question 1.** An unexported package contains `public class InternalApi`; client uses `import` to call a public method. Which permission is needed?  
**Answer:** `--add-exports` or an appropriate export in `module-info.java`, along with satisfying readability. For command-line flags, grant permission at both compile time and runtime.

**Question 2.** A library uses `getDeclaredField("secret")` and `trySetAccessible()`, yet the package in the named module is not opened. Which flag targets the issue?  
**Answer:** `--add-opens` from the module containing the package to the module performing Reflection; `--add-exports` is not enough to open private fields.

**Question 3.** Does `--add-opens` allow `import internal.api.PublicTool` to compile?  
**Answer:** No. `--add-opens` does not grant direct access at compile time.

**Question 4.** Does `ALL-UNNAMED` mean granting permission to a single JAR?  
**Answer:** No. It covers all unnamed modules, typically libraries/apps on the classpath.

**Question 5.** Once `--add-opens` is used, are all writes to `final` fields valid?  
**Answer:** No. Opening a package for Reflection does not remove restrictions on field modifications or other API rules.

**Takeaway:** need to **directly call a public API hidden by a module boundary** → consider `--add-exports`; need **deep Reflection into non-public members** → consider `--add-opens`. Always identify the exact source module, package, target module, compile/run phase, and module readability relationship.

### Official Documentation

- [Dev.java — Circumventing Strong Encapsulation with `--add-exports` and `--add-opens`](https://dev.java/learn/organizing/modules/add-exports-opens/)
- [Dev.java — Reflective Access with Open Modules and Open Packages](https://dev.java/learn/modules/opening-for-reflection/)
- [Oracle JDK 17 Migration Guide — Strong Encapsulation and Module Options](https://docs.oracle.com/en/java/javase/17/migrate/)
- [Java Language Specification §7.7.2 — Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
