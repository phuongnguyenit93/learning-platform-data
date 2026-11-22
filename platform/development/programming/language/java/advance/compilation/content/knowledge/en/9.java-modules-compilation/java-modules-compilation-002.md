# Named Module, Unnamed Module, and Automatic Module

Since Java 9, the **Java Platform Module System (JPMS)** adds the concept of a *module* on top of packages and JARs. Modules help the system represent named dependencies, control which packages are accessible from the outside, and resolve the required set of modules at compile time and runtime. However, a Java project can simultaneously contain code using the legacy classpath mechanism and new modules.

Therefore, it is necessary to distinguish accurately:

- **Explicit named module:** a module with a name declared in `module-info.java` (after compilation, `module-info.class`).
- **Unnamed module:** a module **without a name**, containing classes loaded according to the traditional classpath model of a class loader.
- **Automatic module:** a JAR **without a module descriptor** that is placed on the module path and assigned an automatic module name by the system.

Most importantly: **an automatic module is also a named module**. In classification, named modules include explicitly named modules and automatic modules. The three labels above are three cases to practice, not three disjoint sets.

This lesson is implemented using Java 17+, without external libraries outside the JDK. You will create two named modules, run that JAR on the classpath to observe an unnamed module, and then turn a legacy JAR into an automatic module so that a modular application can reference it using `requires`.

## 1. Why Did JPMS Appear?

Before JPMS, developers typically specified locations on the **classpath** so that `javac` and `java` could find classes. This approach is useful, but a JAR is not required to declare its complete set of dependencies and has no `exports` boundary at the module level.

Consider a library with package `org.example.greetings.api` and package `org.example.greetings.internal`. On the classpath, a `public` class in the internal package can be referenced by external code if other Java access rules are satisfied. With an explicit named module, the author can deliberately export only the API package and keep the internal package unexported.

The descriptor file:

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
}
~~~

The line `module org.example.greetings` declares the module name. The `exports` line declares the package whose eligible `public` types other modules can use. Each package can contain multiple classes; a module can also contain multiple packages.

Another module that wants to use this API typically declares:

~~~java
module org.example.app {
    requires org.example.greetings;
}
~~~

`requires` expresses a **readability** relationship: the application module reads the dependency module. Specific access to a type also requires the package to be exported and the type/member to have an appropriate modifier. `java.base` is implicitly read by every module, so there is no need to write `requires java.base;`.

Summary:

~~~text
org.example.app (named)
       |
       | requires org.example.greetings
       v
org.example.greetings (named)
       |
       | exports org.example.greetings.api
       v
public API Greeter
~~~

This is why `public` and `exports` do not mean the same thing: `public` belongs to the type/member access system, whereas `exports` is a module-level boundary.

## 2. The Three Module Types Side by Side

| Property | Explicit named | Unnamed | Automatic |
| --- | --- | --- | --- |
| Has module name | Yes, explicitly declared | No | Yes, automatically assigned |
| `module-info.class` | Yes | Not needed | No explicit descriptor |
| Typical location | Module path | Classpath | Module path |
| Can be targeted by another module's `requires` | Yes | **No** | Yes |
| `exports` | Per descriptor | Considered to export all packages | Automatically exports all packages |
| `opens` | Per descriptor/JPMS mechanism | Considered to open all packages | Automatically opens all packages |
| Use case | Designing modules with clear boundaries | Running traditional code | Bridging legacy JARs to JPMS |

**Being named is a characteristic, not synonymous with having a developer-authored `module-info.java`.** An automatic module has a name, yet its descriptor is synthesized by the system. An unnamed module has no name and therefore cannot be targeted by a `requires some.name;`.

An application can use multiple modules and JARs, yet **where a JAR is placed** matters: a non-modular JAR on the classpath belongs to an unnamed module; that same JAR on the module path can become an automatic module.

## 3. Explicit Named Modules: Full Example

Create the following tree, setting `module-demo` as the working directory:

~~~text
module-demo/
├── src/
│   ├── org.example.greetings/
│   │   ├── module-info.java
│   │   └── org/example/greetings/api/Greeter.java
│   ├── org.example.app/
│   │   ├── module-info.java
│   │   └── org/example/app/Main.java
│   └── ...
├── out/
│   ├── greetings/
│   └── app/
└── mods/
~~~

**`src/org.example.greetings/module-info.java`:**

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
}
~~~

**`src/org.example.greetings/org/example/greetings/api/Greeter.java`:**

~~~java
package org.example.greetings.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

**`src/org.example.app/module-info.java`:**

~~~java
module org.example.app {
    requires org.example.greetings;
}
~~~

**`src/org.example.app/org/example/app/Main.java`:**

~~~java
package org.example.app;

import org.example.greetings.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("Lan"));
    }
}
~~~

On Linux/macOS, create the target directories from the project root:

~~~sh
mkdir -p out/greetings out/app mods
~~~

On Windows PowerShell, you can create them with:

~~~powershell
New-Item -ItemType Directory -Force out/greetings, out/app, mods | Out-Null
~~~

You only need to run one appropriate directory-creation command. Then compile and package the library first:

~~~sh
javac -encoding UTF-8 -d out/greetings src/org.example.greetings/module-info.java src/org.example.greetings/org/example/greetings/api/Greeter.java
jar --create --file mods/org.example.greetings.jar -C out/greetings .
~~~

`-d out/greetings` produces output following the package structure; `jar -C out/greetings .` packages from the **module output root**. The resulting JAR contains `module-info.class` and `org/example/greetings/api/Greeter.class`.

Compile and package the consuming module:

~~~sh
javac -encoding UTF-8 --module-path mods -d out/app src/org.example.app/module-info.java src/org.example.app/org/example/app/Main.java
jar --create --file mods/org.example.app.jar -C out/app .
~~~

`--module-path mods` specifies where to locate module dependencies. `javac` can find `org.example.greetings` and check `requires` and `exports`. Run:

~~~sh
java --module-path mods --module org.example.app/org.example.app.Main
~~~

Stdout:

~~~text
Hello, Lan
~~~

The part before `/` in `--module` is the **module name**, and after it is the **fully qualified main class name**. That is the syntax for selecting a module/class, not a file path.

Inspect the JARs:

~~~sh
jar --describe-module --file mods/org.example.greetings.jar
jar --describe-module --file mods/org.example.app.jar
~~~

Both JARs have explicit module descriptors. The exact metadata output printed by the command may differ across JDKs, but what to check are the module names and `requires`/`exports` relationships.

### Verifying the meaning of `exports`

If you change the library descriptor to:

~~~java
module org.example.greetings {
}
~~~

then recompile the library, package a new JAR, and recompile the application, the code `import org.example.greetings.api.Greeter;` is rejected because the package is not exported to the application module. **Greeter being `public` is still not enough.** This is a module-level access error, not a missing class file.

The descriptor code above is an **experimental version** intended to trigger an error; do not use it at the same time as the version with `exports` if you want the program to run successfully.

## 4. Unnamed Module: Applications Using Classpath

**Classpath** is the traditional mechanism that lists class directories or JARs for the class lookup mechanism. Classes loaded through that mechanism belong to the **unnamed module of the corresponding class loader**. A JVM can have multiple class loaders and therefore does not necessarily have only a single global unnamed module.

Characteristics:

- Has no module name and no `module-info.java` to declare `requires`.
- Maintains compatibility with pre-JPMS Java code.
- Packages belonging to an unnamed module are treated as exported/opened for compatibility purposes.
- Unnamed code can read named modules that have been resolved under JPMS rules, yet target packages must still be properly exported; not every JAR placed on the module path is automatically resolved into the graph.

### Using a modular JAR on the classpath

The same `mods/org.example.greetings.jar` from section 3, if placed on the **classpath**, will be handled under the classpath model; the descriptor inside does not make the JAR act as an explicit named module in this configuration.

Create the file **`src/classapp/LegacyMain.java`** without a package declaration:

~~~java
import org.example.greetings.api.Greeter;

public class LegacyMain {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("Linh"));
    }
}
~~~

Create `out/classapp` first. Compile with the library on the classpath:

~~~sh
javac -encoding UTF-8 -cp mods/org.example.greetings.jar -d out/classapp src/classapp/LegacyMain.java
~~~

Run on Linux/macOS:

~~~sh
java -cp "out/classapp:mods/org.example.greetings.jar" LegacyMain
~~~

On Windows (PowerShell/CMD):

~~~powershell
java -cp "out/classapp;mods/org.example.greetings.jar" LegacyMain
~~~

Running an appropriate command will print:

~~~text
Hello, Linh
~~~

Notable point: **a JAR with `module-info.class` can sit on the classpath and be used like a traditional library**, rather than a named module resolved by descriptor. The class-loading context decides, not the `.jar` extension.

### Can a named module `requires` an unnamed module?

**No.** Because an unnamed module has no name, a descriptor cannot write a `requires` clause referencing it. The following example is not a solution for a library located on the classpath:

~~~java
module org.example.app {
    requires some.unnamed.module;
}
~~~

This is an **intentionally invalid pattern when the actual dependency is only on the classpath**. The name `some.unnamed.module` is not automatically generated from the classpath.

If an application module needs a legacy library, a common approach is to place that JAR on the **module path** as an automatic module, or to find an explicitly modularized version of the library. Compatibility options like `--add-reads` can assist in certain situations, but they are controlled workarounds and do not turn an unnamed module into a named module.

## 5. Automatic Module: Legacy JARs Placed on the Module Path

This is the most important transition mechanism when the Java ecosystem has not yet been modularized uniformly.

A **plain JAR without `module-info.class`**, when used as a module on the **module path**, can be recognized as an **automatic module**. The tooling synthesizes a descriptor and assigns a name, allowing an explicit named module to write `requires automatic.name;`.

An automatic module:

1. **Has a name** and participates in the module graph as a named module.
2. Automatically **exports all packages** in the JAR.
3. Automatically **opens all packages** to support the many ways legacy libraries use reflection.
4. Has broad readability relationships for legacy library compatibility, including other named modules and unnamed modules under JPMS rules.
5. Contains no explicit descriptor from the author, so it **does not establish strict API/module boundaries** like an explicit module.

Do not equate "automatic module" with "a JAR that automatically downloads dependencies over the network." JPMS is not a library downloader; Maven/Gradle and dependency management tools handle fetching artifacts. An automatic module is how **a JAR is viewed within the module graph**.

### Automatic module names can come from two sources

If the manifest has:

~~~text
Automatic-Module-Name: legacy.math
~~~

then the JAR is recognized by the name `legacy.math` when acting as an automatic module. If the attribute is absent, the name can be **derived from the JAR filename** according to normalization rules (including handling version numbers at the end of the name).

For instance, `legacy-math-1.0.jar` is typically derived as `legacy.math`, but relying on a derived name leaves the `requires` contract vulnerable when the filename changes. The manifest's `Automatic-Module-Name` is a useful way to **stabilize the name during the transition period**.

This attribute **does not automatically generate `module-info.class`** and does not turn the JAR into an explicit named module. When the library is fully modularized, an explicit descriptor is needed to specify dependencies and appropriate exports/opens.

## 6. Example: Turning a Plain JAR into an Automatic Module

We use a JAR containing `legacy.math.LegacyMath`. The JAR has no module descriptor, yet the manifest specifies the module name `legacy.math`. The consuming application is the explicit named module `org.example.consumer`.

Tree added to `module-demo`:

~~~text
src/
├── legacy/legacy/math/LegacyMath.java
└── org.example.consumer/
    ├── module-info.java
    └── org/example/consumer/Main.java

automatic.mf
out/
├── legacy/
└── consumer/
mods/
└── legacy-math-1.0.jar  (will be created)
~~~

**`src/legacy/legacy/math/LegacyMath.java`:**

~~~java
package legacy.math;

public final class LegacyMath {
    private LegacyMath() {
    }

    public static int triple(int value) {
        return value * 3;
    }
}
~~~

Do not create `module-info.java` for this library.

**`automatic.mf`** is a plain-text manifest file with a trailing newline and a blank line at the end:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: legacy.math

~~~

**`src/org.example.consumer/module-info.java`:**

~~~java
module org.example.consumer {
    requires legacy.math;
}
~~~

**`src/org.example.consumer/org/example/consumer/Main.java`:**

~~~java
package org.example.consumer;

import legacy.math.LegacyMath;

public class Main {
    public static void main(String[] args) {
        System.out.println("Triple = " + LegacyMath.triple(7));
    }
}
~~~

Create the `out/legacy` and `out/consumer` directories first, and ensure `mods` already exists. Compile the library like a regular JAR and then package it:

~~~sh
javac -encoding UTF-8 -d out/legacy src/legacy/legacy/math/LegacyMath.java
jar --create --file mods/legacy-math-1.0.jar --manifest automatic.mf -C out/legacy .
~~~

Inspect:

~~~sh
jar --list --file mods/legacy-math-1.0.jar
jar --describe-module --file mods/legacy-math-1.0.jar
~~~

The JAR must contain the entry `legacy/math/LegacyMath.class`, **no `module-info.class`**, and be described by the tool as an automatic module named `legacy.math`. The formatting details printed by `jar --describe-module` vary by JDK, so do not assume a fixed stdout layout.

Continue compiling the consuming explicit named module:

~~~sh
javac -encoding UTF-8 --module-path mods -d out/consumer src/org.example.consumer/module-info.java src/org.example.consumer/org/example/consumer/Main.java
jar --create --file mods/org.example.consumer.jar -C out/consumer .
java --module-path mods --module org.example.consumer/org.example.consumer.Main
~~~

Output:

~~~text
Triple = 21
~~~

Thus, an explicit named module can use a legacy library **without `module-info.java`**, provided that JAR is recognized as an automatic module on the module path and has a name that `requires` can use.

**Distinguish the two situations:** If `legacy-math-1.0.jar` is placed only on the classpath, it does not provide the named module `legacy.math` for the `requires legacy.math;` clause. In that case, compiling the consumer module may report that the module was not found. You cannot simply replace `--module-path` with `-cp` while keeping the descriptor unchanged.

## 7. Readability, exports, and opens

Three concepts often mistakenly conflated:

**Readability:** Is there a read edge between two modules? An explicit descriptor uses `requires` to declare a dependency. Without `requires` (or an equivalent mechanism establishing the relationship), a module is not necessarily permitted to reference another module even if its JAR is on the module path.

**Exports:** Is the package exposed for ordinary access from another module? In an explicit module, `exports org.example.greetings.api;` allows eligible public types in that package to appear in the consumed API. An unexported package remains hidden from ordinary access by other modules.

**Opens:** Is the package opened for deep reflection? In an explicit module, you can use `opens some.package;` or scoped variants as appropriate. `exports` does not mean external code can use reflection to access every private field.

Illustrative descriptor example:

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
    opens org.example.greetings.internal;
}
~~~

**This is only an illustrative snippet**, not a standalone runnable file for the exercise: a real `org.example.greetings.internal` package must exist when using that configuration.

Unnamed modules and automatic modules have broad export/open boundaries for compatibility with traditional code. When upgrading a JAR from an automatic module to an explicit module, frameworks using reflection may need `opens` added in the right places; you cannot assume the application will continue running identically even if compilation succeeds.

One more note: **a named module does not automatically see every JAR on the module path**. The system must first resolve the needed modules into the graph; `--add-modules` can be used in certain situations to add root modules.

## 8. Classpath, Module Path, and How to Launch

| Tool/syntax | Purpose |
| --- | --- |
| `javac -cp path ...` | Lets the compiler locate classes/JARs on the classpath |
| `java -cp path MainClass` | Runs the main class using the traditional classpath mechanism |
| `javac --module-path path ...` | Lets the compiler locate modules to resolve |
| `java --module-path path --module name/pkg.Main` | Runs the entry point in a named module |
| `java -p path -m name/pkg.Main` | Short form of the two module-related options |
| `jar --describe-module --file file.jar` | Views the module descriptor/module contents recognized by the tool |

Example of two equivalent commands:

~~~sh
java --module-path mods --module org.example.app/org.example.app.Main
java -p mods -m org.example.app/org.example.app.Main
~~~

When a classpath or module path consists of **multiple elements**, Linux/macOS uses `:` as the separator, while Windows uses `;`. However, in the example the module path consists of only one directory `mods`, so no separator is needed.

Note regarding a classpath app using a named module: **an unnamed module can read named modules that have been resolved**, yet simply placing a JAR on the module path does not guarantee that module is resolved under the runtime configuration. In some cases, add the target module to the root set with `--add-modules`:

~~~sh
java --module-path mods --add-modules org.example.greetings -cp out/classapp LegacyMain
~~~

This illustrative command relies on `LegacyMain.class` and the named-module JAR created in the earlier section. When compiling classpath code that references a named module, the `javac` configuration must also be set consistently; do not assume runtime flags automatically fix compile-time issues.

## 9. Common Errors When Combining Modules and JARs

| Symptom | What to check |
| --- | --- |
| `module not found: legacy.math` | Is the automatic JAR on the module path, and what is its actual name? |
| `package ... is not visible` | Does the module read the dependency and is the package exported? |
| `Could not find or load main class` | Are you using `-cp` or `-m`; are the class name and classpath root right? |
| `NoClassDefFoundError` | Missing runtime class or dependency loading/initialization failure |
| `Error occurred during initialization of boot layer` | Module resolution, duplicate modules, split packages, path configuration |
| Reflection access denied | Check `opens`/module rules, not just `exports` |

**Split package:** A package appearing in two resolved named modules can make the resolution process invalid. For example, if two different JARs both contain `com/example/shared/...` and both become named modules, splitting the package can cause a conflict. This is rarely detected when testing them only on the old-style classpath; before moving batches of JARs onto the module path, check for duplicate packages.

**Duplicate automatic module names:** Two JARs can derive the same module name from their filenames or manifests; this is a different issue from duplicate packages. Run `jar --describe-module` on each artifact and avoid accidentally putting two versions of a dependency on the same path.

**The absence of `module-info.class` does not guarantee an unnamed module.** A plain JAR can be unnamed when placed on the classpath or automatic when placed on the module path. The location and how the module is resolved decide.

**Not every class-loading error is caused by JPMS.** `.class` version errors, API incompatibilities, static initialization failures, or missing dependencies can still occur even when the module graph is valid.

### Diagnostic questions when a build fails

1. Am I compiling an **explicit named module** or code on the classpath?
2. Is the required JAR on the **classpath** or the **module path**?
3. Does the JAR have an explicit module descriptor yet? If not, how is the automatic name determined?
4. Does the consuming module's descriptor `requires` the right name?
5. Does the library module export the right API package?
6. If reflection fails, does the package need `opens`?
7. Are there duplicate module names or split packages on the module path?
8. At runtime, am I using **the exact same JARs and module path** as at compile time?

Checking in the proper order helps avoid guesswork fixes such as adding every JAR to both `-cp` and `--module-path` or unnecessarily opening all packages.

## 10. Approach to Migrating a Legacy Project to JPMS

There is no need to move the entire project onto the module path at once. You can proceed step by step:

1. **List all dependencies** and the actual versions used by build and runtime.
2. **Inspect descriptors/automatic names** of each JAR using `jar --describe-module`; prioritize libraries with stable names.
3. **Separate API and implementation** to know which packages need to be exported and which reflection targets need to be opened.
4. **Modularize the code you control** with `module-info.java` and appropriate `requires` and `exports`.
5. **Use automatic modules deliberately** for library JARs that do not yet support explicit modules.
6. **Check split packages, service loading, and reflection**, rather than only looking for a green build.
7. **Test the actual artifacts** in the target environment; compile classpath/module path must be consistent with runtime.
8. **Reduce temporary workarounds** like `--add-opens` if they can be replaced by module design or library upgrades.

An automatic module is a **transition bridge**, not a mandatory optimal state. Replacing it with an explicit named module requires defining clear API and access contracts.

## 11. Practice Exercises

**Exercise 1 — Two explicit named modules.** Create `Greeter` and `Main` from section 3. Run `jar --describe-module` and confirm the `requires` dependency. Run to get the stdout `Hello, Lan`.

**Exercise 2 — Removing export.** Remove `exports` from the library descriptor, rebuild the library and app. Explain why `public class Greeter` is still inaccessible across the module boundary.

**Exercise 3 — Same JAR, two mechanisms.** Place `org.example.greetings.jar` on `-cp` and run `LegacyMain`. Demonstrate that having `module-info.class` in a JAR is not enough for it to become a named module when used on the classpath.

**Exercise 4 — Automatic module.** Create `legacy-math-1.0.jar` with `Automatic-Module-Name: legacy.math` but without `module-info.class`; run `jar --describe-module`, then compile/run `org.example.consumer` with `requires legacy.math;`.

**Exercise 5 — Changing the path.** Try removing the automatic JAR from `mods` and running the consuming module. Predict when the missing-module error is reported; fix the module path without modifying `LegacyMath`'s logic.

**Exercise 6 — API boundaries.** Suppose a legacy library has `api` and `internal`, and a framework needs reflection into `internal`. When creating an explicit descriptor, state which packages need `exports`, which packages need `opens`, and why you should not open everything unconditionally.

### Self-Assessment

1. **Is an automatic module a named module?** — Yes; its name and synthesized descriptor are provided under the automatic module mechanism.
2. **Where does an unnamed module come from?** — From code loaded via the classpath by the corresponding class loader.
3. **Can a named module `requires` an unnamed module?** — No; an unnamed module has no name to write in a descriptor.
4. **What is `module-info.java` used for?** — Declaring an explicit module, its dependencies, and its export/open boundaries.
5. **Does `Automatic-Module-Name` make a JAR an explicit module?** — No; it only helps assign a stable name to an automatic module.
6. **Why is `public` not enough to access a class in another module?** — A readability relationship and an exported package under JPMS are also required.
7. **Are `-cp` and `--module-path` equivalent?** — No; the class-loading and module-resolution models are different.
8. **What does an automatic module export/open?** — All packages according to automatic module compatibility rules.
9. **How do you find out the actual module name of a JAR?** — Check `jar --describe-module --file ...` and the manifest when needed.
10. **What are the main risks when placing legacy JARs on the module path?** — Unstable derived module names, duplicate modules/packages, and incompatible dependencies and reflection.

**Conclusion:** An explicit named module proactively describes boundaries and dependencies; an unnamed module preserves the traditional classpath model; an automatic module gives a legacy JAR a name in the module graph without having to write a descriptor yet. Distinguishing these three cases helps you properly understand module-lookup errors, export/package errors, and how to organize modern Java compilation and deployment.