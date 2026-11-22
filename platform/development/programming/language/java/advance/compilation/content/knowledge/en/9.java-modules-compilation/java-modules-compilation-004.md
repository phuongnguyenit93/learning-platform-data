# requires transitive, requires static, and Their Impact at Compile Time

In the **Java Platform Module System (JPMS)**, each named module has a `module-info.java` file to declare dependency relationships, exported packages, and required access permissions. When a module writes `requires other.module;`, it does more than help the compiler find a JAR: it helps define the application's **dependency graph** (*module graph*) and **module readability** relationships (*readability*).

The two modifiers `transitive` and `static` answer **two different questions**:

- **`requires transitive`:** when module A reads module B, and B declares a transitive dependency on C, then A also **reads C**. It supports the usability of APIs exposed across modules.
- **`requires static`:** the dependency is required **at compile time**, yet may **be absent at runtime**. It serves optional dependencies; this does not automatically guarantee that every execution path still works when the dependency is missing.

You can combine both: `requires static transitive module.name;`. In that case, the *transitive* semantics apply to reading the dependency through another module, while *static* specifies that the dependency is required at compile time yet may be absent at runtime. In this lesson, we clearly distinguish **module resolution**, **readability**, **exports**, and **executing code paths that actually use an optional module**.

This hands-on lesson uses **Java 17+** and can be compiled with JDK 21 using `--release 17`. Complete source code and commands are provided to build each example separately; none of it is pseudocode.

## 1. Reviewing the JPMS Model

A module has the following basic structure:

```text
src/
  my.module/
    module-info.java
    my/
      package/
        SomeClass.java
```

In `module-info.java`, you can write:

```java
module my.module {
    requires java.logging;
    exports my.package;
}
```

Meaning:

- `module my.module`: name of the current module. In these examples, the module name must match the module directory name on `--module-source-path`.
- `requires java.logging`: the current module reads `java.logging` and has a dependency on this module.
- `exports my.package`: allows other modules, if they **read `my.module`**, to access eligible `public` types in package `my.package`.
- `java.base` is implicitly read by every named module under language rules; you usually do not need to declare `requires java.base;`.

Two independent checks for a module A to use a type `public p.Type` belonging to module B are:

1. **Does A read B?** That is, whether the readability relationship in the module graph allows A to access B.
2. **Does B export package `p` to A?** If B does not export that package (or exports it conditionally, but not to A), the type cannot be accessed normally from A.

`requires transitive` addresses only the **module readability relationship**, not automatically exporting all packages of the dependency module. `requires static` addresses **phase-specific requirement**, not automatically downloading or loading every class at runtime.

### Four forms of requires to remember

| Declaration in module B | Does B read C at compile time? | Is C required at runtime? | Does module A reading B automatically read C? |
| --- | --- | --- | --- |
| `requires C;` | Yes | Yes, per regular module resolution | Not solely because A reads B |
| `requires transitive C;` | Yes | Yes | **Yes**, via transitive readability |
| `requires static C;` | Yes | **Not mandatory** | Not solely because A reads B |
| `requires static transitive C;` | Yes | **Not mandatory** | **Yes at compile time**; at runtime only when C is appropriately resolved |

In the table above, "required at runtime" refers to dependencies required by the module resolver for a valid module configuration; it does not mean every class in the module must be loaded immediately. `static` marks optional resolution at runtime, rather than changing the principle that **missing a class that is actually used can still fail**.

## 2. requires: A Dependent Module Reads Another Module, Without Automatic Propagation

Suppose there are three modules:

```text
learn.app  --->  learn.api  --->  learn.model
```

If `learn.app` declares `requires learn.api;`, while `learn.api` declares only `requires learn.model;`, then:

- `learn.api` reads `learn.model` to compile its own code.
- `learn.app` reads `learn.api` because it declares this dependency.
- `learn.app` **does not automatically gain readability to `learn.model`**, even though `learn.api` uses it.

This is intentional in the module system: dependency relationships are part of the declared API. For the application itself to access types from `learn.model`, the application either needs `requires learn.model;` directly, or the API module must publish the dependency with `requires transitive learn.model;` when that fits the API design.

### Why do errors often appear only when switching to named modules?

On the traditional classpath, multiple JARs are placed into a relatively flat search space. When moving to the module path, the compiler enforces **module readability and exports**. The presence of a JAR on disk or a module on the module path **does not mean** code in every module has permission to import its types.

A typical error when readability is missing looks similar to:

```text
package learn.model is not visible
(package learn.model is declared in module learn.model, but module learn.app does not read it)
```

Actual diagnostic lines may have different filenames, line numbers, positions, and phrasing depending on the compiler version. Do not fix this by moving everything back to the classpath before understanding the module graph.

## 3. Lab 1: requires transitive Exposes a Dependency in the API

We create three named modules where the API returns a type declared in another module.

### 3.1. Directory tree

Create the files following this exact structure:

```text
transitive-lab/
  src/
    learn.model/
      module-info.java
      learn/model/Message.java
    learn.api/
      module-info.java
      learn/api/Greeter.java
    learn.app/
      module-info.java
      learn/app/Main.java
```

At the `transitive-lab` root directory, create `src/learn.model/module-info.java`:

```java
module learn.model {
    exports learn.model;
}
```

Create `src/learn.model/learn/model/Message.java`:

```java
package learn.model;

public record Message(String text) {}
```

`record` is supported in Java 17. Package `learn.model` must be **exported** so consuming modules can use `Message`.

Create `src/learn.api/module-info.java`:

```java
module learn.api {
    requires transitive learn.model;
    exports learn.api;
}
```

Create `src/learn.api/learn/api/Greeter.java`:

```java
package learn.api;

import learn.model.Message;

public class Greeter {
    public static Message message() {
        return new Message("hello");
    }
}
```

Design point: `Greeter.message()` **returns `learn.model.Message`**, so `learn.model` is part of the API surface visible to clients. `requires transitive learn.model;` allows users of `learn.api` to read the module containing that public type.

Create `src/learn.app/module-info.java`:

```java
module learn.app {
    requires learn.api;
}
```

Finally, create `src/learn.app/learn/app/Main.java`:

```java
package learn.app;

import learn.api.Greeter;
import learn.model.Message;

public class Main {
    public static void main(String[] args) {
        Message message = Greeter.message();
        System.out.println(message.text());
    }
}
```

**Observation:** `learn.app` does not declare `requires learn.model;`, yet it is allowed to import `Message` because `learn.api` publishes the dependency via `requires transitive learn.model;` and `learn.model` exports the corresponding package.

### 3.2. Compile and run

From the `transitive-lab` root directory. To avoid relying on operating system glob syntax, the following command lists all six source files explicitly:

```bash
javac --release 17 --module-source-path src -d mods src/learn.model/module-info.java src/learn.model/learn/model/Message.java src/learn.api/module-info.java src/learn.api/learn/api/Greeter.java src/learn.app/module-info.java src/learn.app/learn/app/Main.java
java --module-path mods -m learn.app/learn.app.Main
```

Exact stdout:

```text
hello
```

The same two commands work in Bash, zsh, Windows PowerShell, and cmd when written **each command on a single line** with relative paths matching the directory tree. On Windows, Java also accepts forward slashes `/` in most of the path arguments described here. The compiler creates the directories `mods/learn.model`, `mods/learn.api`, and `mods/learn.app`, each containing the class files of its respective module.

`--module-source-path src` tells `javac` how source code is laid out by named modules. `-d mods` specifies where class files are generated. `--module-path mods` makes the compiled modules visible to the Java launcher. `-m learn.app/learn.app.Main` selects the entry module and main class.

### 3.3. What happens if transitive is removed?

Modify only the file `src/learn.api/module-info.java` to:

```java
module learn.api {
    requires learn.model;
    exports learn.api;
}
```

Then **recompile all six files using the exact `javac` command in section 3.2** (you can use a new output directory like `mods-plain` and adjust `-d` accordingly to be sure). The compiler reports an error for `learn.app` at the import of `learn.model.Message`, because `learn.app` **does not read `learn.model`**. The error message looks similar to:

```text
package learn.model is not visible
(module learn.app does not read module learn.model)
```

This is an **intentional compile-time error**: `learn.api` still compiles with `Message`, but `learn.app` does not inherit readability through an ordinary `requires`.

There are two solutions depending on the API intent:

1. **Restore `requires transitive learn.model;`** in `learn.api` when `Message` is genuinely part of `Greeter`'s public API.
2. Or add `requires learn.model;` to `learn.app/module-info.java` if the client intentionally depends directly on model and you want an explicit dependency contract at the client.

Missing readability cannot be solved simply by adding `exports learn.model;` when that `exports` directive is already present: the module exports the package, yet the client still has to **read the module**.

### 3.4. Deriving the readability graph

With `learn.api` declaring `requires transitive learn.model;`:

```text
learn.app  --requires-->  learn.api
    |                         |
    |--reads implied----------+--requires transitive--> learn.model
```

The purpose is not to "automatically pull every dependent JAR into the application." `transitive` describes a **module read edge**; the module must still be present/appropriately resolved, the accessed class must still be `public`, and the package must still be exported.

### When should you choose requires transitive?

Choose `requires transitive` when the current module's public API **depends on types belonging to the other module**: return types, parameter types, public superclasses/interfaces, or generic APIs that clients are expected to manipulate. Do not use `transitive` for every internal dependency; overusing it exposes many relationships in the module graph and reduces the clarity of API boundaries.

If `Greeter` only returns `String` and uses `Message` solely inside its implementation, `requires learn.model;` is usually enough: clients do not need to directly read the model module just to call a string-returning API. However, the final choice depends on API goals and the scope of types clients actually need.

## 4. requires static: Mandatory at Compile Time, Optional at Runtime

`requires static optional.module;` is understood as follows:

- **When compiling the declaring module:** the compiler must see the requested named module; code in the declaring module can use types exported from that dependency.
- **At runtime:** the declaring module can be resolved without the optional module being present. Not reaching the dependency's types along that execution path can allow the app to run successfully.
- **If code actually attempts to load/use a missing type:** runtime errors can still occur, such as `NoClassDefFoundError` or related errors depending on the reference site. `static` does not create a "dummy implementation" and does not make every API optional-safe.

The word `static` in a module directive **is unrelated to the `static` modifier on fields/methods**. It is a kind of dependency based on **when the module is required**.

A typical example is a module with an optional extension feature: at build time the API is needed for the compiler to type-check, whereas when deploying in "basic mode" that plugin library is not needed. The design must avoid triggering code that uses the plugin when it is absent.

## 5. Lab 2: requires static and an Optional Runtime Module

This lab creates **three modules independent** of the previous example; use a new directory `static-lab` to avoid module or class name collisions.

### 5.1. Structure and source code

```text
static-lab/
  src/
    learn.optional/
      module-info.java
      learn/optional/OptionalText.java
    learn.feature/
      module-info.java
      learn/feature/Feature.java
    learn.host/
      module-info.java
      learn/host/Main.java
```

File `src/learn.optional/module-info.java`:

```java
module learn.optional {
    exports learn.optional;
}
```

File `src/learn.optional/learn/optional/OptionalText.java`:

```java
package learn.optional;

public class OptionalText {
    public static String value() {
        return "optional works";
    }
}
```

File `src/learn.feature/module-info.java`:

```java
module learn.feature {
    requires static learn.optional;
    exports learn.feature;
}
```

File `src/learn.feature/learn/feature/Feature.java`:

```java
package learn.feature;

import learn.optional.OptionalText;

public class Feature {
    public static String safe() {
        return "core works";
    }

    public static String optional() {
        return OptionalText.value();
    }
}
```

File `src/learn.host/module-info.java`:

```java
module learn.host {
    requires learn.feature;
}
```

File `src/learn.host/learn/host/Main.java`:

```java
package learn.host;

import learn.feature.Feature;

public class Main {
    public static void main(String[] args) {
        System.out.println(Feature.safe());
        if (args.length > 0) {
            System.out.println(Feature.optional());
        }
    }
}
```

`Main` calls `Feature.optional()` **only when** command-line arguments are present. This separates the safe execution path from the execution path requiring the optional dependency.

### 5.2. Compile all three modules

In the `static-lab` directory:

```bash
javac --release 17 --module-source-path src -d mods src/learn.optional/module-info.java src/learn.optional/learn/optional/OptionalText.java src/learn.feature/module-info.java src/learn.feature/learn/feature/Feature.java src/learn.host/module-info.java src/learn.host/learn/host/Main.java
```

At compile time, module `learn.optional` **must be within the compiler's visibility**. Thanks to `requires static learn.optional;`, `Feature.java` compiles even though it contains a reference to `OptionalText`. If you completely exclude the optional module from both the sources and module path when recompiling `learn.feature`, compilation will fail because the required dependency cannot be found.

This is the exact difference from runtime: `static` does not mean the dependency is optional at **both** phases.

### 5.3. Run the baseline path

```bash
java --module-path mods -m learn.host/learn.host.Main
```

Stdout:

```text
core works
```

The program does not call `Feature.optional()`. With `requires static`, `learn.optional` does not automatically become a resolved module in the runtime graph solely due to `learn.feature`'s `requires static` declaration, even when it is present in the `mods` directory.

If you want to test genuinely omitting the optional module from distribution, you can create a copy of the runtime directory containing only `learn.feature` and `learn.host`, and point `--module-path` to it. The key point is to **keep the compiled output unchanged** and run with a module path lacking `learn.optional`; the example still prints `core works`.

### 5.4. Running the dependency-requiring feature: the optional module must be resolved

Still in `static-lab`, run:

```bash
java --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Exact stdout:

```text
core works
optional works
```

`--add-modules learn.optional` makes `learn.optional` an additional root module so the runtime **resolves the module**. Once the module is actually in the graph and its package is exported, `Feature.optional()` can call `OptionalText.value()`.

Try without `--add-modules` but with the `use` argument:

```bash
java --module-path mods -m learn.host/learn.host.Main use
```

In this example's specific module configuration, the program prints `core works` and then throws an error of the form:

```text
java.lang.NoClassDefFoundError: learn/optional/OptionalText
```

This is the **critical part of the error**; the stack trace and nested causes may vary by JVM. We see that a module being present **on the module path** does not guarantee it is **resolved** into the graph. Therefore, one must distinguish between "module file exists," "is resolved," "is readable," and "class is loaded."

If the optional module is completely absent from the module path, `--add-modules learn.optional` cannot resolve that module either; the actual dependency must be provided first. `--add-modules` does not download libraries from the Internet.

### 5.5. Conditions for a genuinely optional-safe application

The simple example uses an `if (args.length > 0)` branch. Real-world applications may require a different architecture:

- Do not let the baseline path initialize a class whose static initializer touches an absent type.
- Do not assume every signature containing an optional type is safe everywhere it is loaded, inspected, or reflected upon.
- Separate the core API from integration modules or adapter classes if the dependency is strictly optional.
- Test both deployment configurations: **with the dependency and without the dependency**, across the actual code paths used by deployments.
- If implementing plugins via the service mechanism, you can consider `ServiceLoader`/`uses`/`provides`, though `requires static` does not trigger service discovery by itself.

**Errors like `NoClassDefFoundError` are not a good optional business branch.** Design proper integration capability checks and module separation; do not use class linkage errors as a normal feature-selection mechanism.

## 6. Combining requires static transitive

`transitive` and `static` are two valid modifiers on the same `requires` directive, so they can be combined:

```java
module learn.feature {
    requires static transitive learn.optional;
    exports learn.feature;
}
```

At compile time:

- `learn.feature` can use `learn.optional` thanks to the `static` dependency.
- Another module reading `learn.feature` gains **readability to `learn.optional` during compilation** thanks to `transitive`.
- The ability to reference `public` types still obeys the optional module's `exports`.

At runtime:

- The optional module **is not required to be present solely because of `static transitive`**.
- If the optional module is present and appropriately resolved, the readability relationships allow code using the type to work.
- If the optional module is absent, code paths not touching that type can run; code paths depending on it can still fail when the class is used.

### 6.1. Trying changes to two files in static-lab

After running the previous example, replace `src/learn.feature/module-info.java` with:

```java
module learn.feature {
    requires static transitive learn.optional;
    exports learn.feature;
}
```

And replace `src/learn.host/learn/host/Main.java` with:

```java
package learn.host;

import learn.feature.Feature;
import learn.optional.OptionalText;

public class Main {
    public static void main(String[] args) {
        System.out.println(Feature.safe());
        if (args.length > 0) {
            System.out.println(OptionalText.value());
        }
    }
}
```

Note: `learn.host/module-info.java` **still declares only** `requires learn.feature;`. Code in `learn.host` now imports `learn.optional.OptionalText` directly without declaring `requires learn.optional;`, because it receives readability via `requires static transitive` at compile time.

Rerun the compilation command for **all six source files** from section 5.2. This command has been verified successfully on JDK 21 with `--release 17`.

Run without arguments:

```bash
java --module-path mods -m learn.host/learn.host.Main
```

Stdout:

```text
core works
```

Run with the optional module added to the roots set:

```bash
java --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Stdout:

```text
core works
optional works
```

If you omit `--add-modules` and still execute the branch using `OptionalText`, the example can encounter a similar class linkage error. This illustrates how **static** and **transitive** act along two different dimensions: when the module is required and whether clients can read the module through the API.

Do not use `requires static transitive` merely "just in case." Use it when the optional library is genuinely a public part of the API, and there is a clear runtime strategy for when it is absent. If the core API does not expose types from the dependency, plain `requires static` exposes fewer dependency relationships.

## 7. Compile-Time vs. Runtime Comparison Table from Three Perspectives

Suppose A requires B, and B has dependency C:

| B declares | Is C needed when compiling B? | Can A use `public` types exported from C without `requires C`? | Is C required when resolving B at runtime? |
| --- | --- | --- | --- |
| `requires C` | Yes | No; A usually must `requires C` separately | Yes |
| `requires transitive C` | Yes | Yes, if C exports the appropriate package | Yes |
| `requires static C` | Yes | No; A usually must `requires C` separately | Not mandatory |
| `requires static transitive C` | Yes | Yes at compile time, if C exports the appropriate package | Not mandatory |

Note two independent control concepts:

- **Readability** answers "can code in A use types from C?"
- **Module resolution** answers "is C actually present in the current module graph?"

A module present on `--module-path` is merely **observable**, not necessarily **resolved**. A resolved module still needs an appropriate readability edge for its exported types to be accessible in another module's code.

### 7.1. exports and opens are two different permissions

`exports p;` is for **accessing public types** from other modules under language checks and runtime access rules. `opens p;` primarily grants **deep reflection** permission on the package when module conditions are satisfied. Do not replace `exports` with `opens` expecting the compiler to let modules import `public p.Type`. `requires transitive` also does not create `opens` and does not permit arbitrary reflection on private fields.

For example, if `learn.model` does not declare `exports learn.model;`, even if `learn.api` uses `requires transitive learn.model;`, code in `learn.app` still cannot import `learn.model.Message` under ordinary module access. **Readability must be paired with export**.

### 7.2. requires static is not synonymous with static import

`requires static learn.optional;` in `module-info.java` is **completely different** from `import static java.lang.Math.PI;` in a regular Java file.

- `requires static`: the module dependency may be absent at runtime.
- `import static`: merely lets you reference static members by short names in source code; it does not replace module readability and does not make a dependency optional.

Do not use the word "static" to infer any connection to static initialization or method dispatch in this case.

## 8. Common Errors and How to Identify Them

| Symptom | Possible cause | Appropriate fix |
| --- | --- | --- |
| `package ... is not visible`, module A does not read C | Missing `requires C` or a `requires transitive C` edge is needed in B | Inspect the API surface; declare the dependency in the right module |
| Compiler sees the package but reports module does not export it | C does not `exports` the package to A | Export only the needed API portion, considering boundaries |
| `module not found: learn.optional` at compile time | A `requires static` dependency must still exist at compile time | Provide the optional module on the build's source/module path |
| Running the app missing a module with regular `requires C` | The runtime module graph requires the dependency | Provide the correct version of module C |
| Running with `requires static C` succeeds even when C is absent | No execution path forces the use of C | This is expected optionality; still test the branches |
| Module sits in `mods` yet optional code still fails | The static dependency module has not been resolved or the class is not properly present | Check `--add-modules`/roots, the graph, module path, and code paths |
| Calling optional code throws `NoClassDefFoundError` | The type is referenced without a runtime class/module to satisfy it | Ensure the module is resolved or avoid calling the integration when missing |
| Declared `requires transitive` yet still cannot import | Package is not exported, type is not public, module path is wrong, or package name is incorrect | Check exports, readability, access modifiers, and names |
| Removing a dependency compiles but fails at runtime | Build has hidden classpath/module path or different version/runtime graph | Reproduce a clean build and compare module graphs |
| Adding a dependency on the classpath is unseen by JPMS | Named module code looks for dependencies on the module path under a different configuration | Use the module path properly and check automatic modules if needed |

**Do not by default propose `--add-reads` or `--add-exports` just to "make it compile."** Those flags can aid experimentation or migration, but if the source module descriptor has the wrong contract, fixing `module-info.java` and API boundaries is the more sustainable approach.

## 9. How to Inspect the Actual Module Graph

Beyond reading `module-info.java`, the JDK provides tools to assist verification.

### 9.1. Inspecting compiled modules

For examples that already have the `mods` directory:

```bash
jar --describe-module --file mods/learn.api/module-info.class
```

The `jar --describe-module` command is typically used with a JAR file; for an **exploded module** such as `mods/learn.api`, use the appropriate module path syntax for your tool version or inspect directly with `javap` as shown below. A more reliable way to inspect the descriptor from a class file is:

```bash
javap -v mods/learn.api/module-info.class
```

Look for entries belonging to the module descriptor, especially `requires transitive`. For the `static-lab` example, inspect `mods/learn.feature/module-info.class` to confirm `requires static` or `requires static transitive` after compilation.

**Tip:** do not interpret `javap`'s output on `module-info.class` as verbatim reconstructed Java source; it is class-file attribute information with flag names displayed by the tool.

### 9.2. Observing runtime resolution

On a JDK supporting the option to display module resolution:

```bash
java --show-module-resolution --module-path mods -m learn.host/learn.host.Main
```

This command is for **static-lab**. The output can be long, depending on the JDK and modules brought into the graph. Compare with:

```bash
java --show-module-resolution --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Now you can observe the optional module being added to roots. **Do not assume `--show-module-resolution` prints the same order or line count** across JDKs.

Additionally, `java --list-modules` lists the runtime's **system modules**, not the list of all JAR modules of an arbitrary application on the module path. To inspect modules on the application path, use the proper graph/runtime resolution tools as shown, or inspect descriptors/JARs individually.

### 9.3. jdeps for dependency analysis

`jdeps` is a static dependency analysis tool at the class/JAR/module level. It can help identify module dependencies in an artifact, though results depend on packaging, `--module-path` options, and referenced classes. `jdeps` cannot replace runtime testing of optional branches because it relies purely on static analysis.

To view options appropriate for your JDK:

```bash
jdeps --help
javac --help
java --help
```

## 10. API Design: When transitive, When static?

**Choose `requires transitive` when:**

- A type from the dependency appears directly in the public API that consumers will use (return type, parameter, superclass/interface, generic signature).
- The module wants to explicitly express that clients reading it also need to read that dependency.
- The dependency is present at runtime and resides in the regular module graph.

**Choose `requires static` when:**

- Compilation needs types from the dependency, while runtime has deployments or execution paths that do not use that dependency.
- Absence of the dependency is handled by API design and testing, rather than relying on catching linkage exceptions as normal control flow.
- How the optional module will be added to the runtime graph if needed has been determined.

**Choose `requires static transitive` when both hold:**

- The current module's API exposes types belonging to an optional module to clients.
- Clients need readability at compile time.
- The product has a runtime strategy with and without the optional module and the branches are properly separated.

**Choose ordinary `requires` when:**

- The dependency is needed during normal operation but is not part of the API contract that clients must import directly.

A quick decision diagram:

```text
Is the dependency actually needed at runtime?
    |
    +-- Yes -------------------> Does client code need to read types from the dependency?
    |                                |
    |                                +-- Yes -> requires transitive
    |                                +-- No  -> requires
    |
    +-- May be absent ---------> Does the client need to read types from the dependency at compile time?
                                     |
                                     +-- Yes -> requires static transitive
                                     +-- No  -> requires static
```

This diagram is an **API design guide**, and does not replace the JLS or special cases such as service binding, automatic modules, dynamic layers, and reflection.

## 11. Exercises with Answers

### Exercise 1: Reading a dependency diagram

Given:

```java
module alpha {
    requires beta;
}
module beta {
    requires transitive gamma;
}
module gamma {
    exports gamma.api;
}
```

Assuming valid descriptors and all modules properly provided, can code in `alpha` import `public` types from `gamma.api`?

**Answer:** Yes, because `alpha` reads `beta`, and `beta` declares `requires transitive gamma;`. Readability to `gamma` is implied and `gamma.api` is exported.

### Exercise 2: Removing transitive

Change `beta` to `requires gamma;` while keeping `alpha` as before. What happens when code in `alpha` imports `gamma.api.Point`?

**Answer:** Compile-time error because `alpha` does not have readability to `gamma`. Fix by adding `requires gamma;` directly in `alpha`, or restoring `requires transitive gamma;` in `beta` if the dependency belongs to the API exposed by `beta`.

### Exercise 3: Optional module at runtime

```java
module feature {
    requires static plugin.api;
}
```

Can `feature` be compiled when `plugin.api` is completely absent? And can `feature` run without `plugin.api`?

**Answer:** The compiler **must see `plugin.api`**; without the dependency, compiling the declaring module fails. The runtime **can** run when the optional module is absent, provided no executed code path needs its types and other mandatory dependencies are satisfied.

### Exercise 4: Optional module present but not resolved

Why can `java --module-path mods -m learn.host/learn.host.Main use` in `static-lab` fail even though `mods/learn.optional` exists?

**Answer:** `requires static` does not automatically require the runtime to resolve the optional module. The module path describes modules that *can be found*, which differs from the set of modules actually resolved; in this example `--add-modules learn.optional` is needed when running the `use` branch.

### Exercise 5: requires static transitive

A module `api` declares `requires static transitive types;`, while `app` declares `requires api;`. Is `types` always packaged and loaded when app runs?

**Answer:** No. During compilation, `app` reads `types` via the transitive relationship when the dependency is present. At runtime, `types` is not required solely due to `static`; it must be provided/resolved if the code needs those types.

### Exercise 6: Exports and transitive

`api` has `requires transitive model;`, yet `model` does not export `model.internal`. Can a client reading `api` import `model.internal.Secret` solely because of transitive?

**Answer:** No. Readability and export are two independent conditions; internal types remain encapsulated at the module boundary.

## 12. Summary and Official Documentation

You can remember it using two questions when reading `module-info.java`:

1. **"Who gets to read this module through the dependency?"** — `transitive` clarifies transitive readability, especially for APIs using types from another module.
2. **"When must the dependency be present?"** — `static` makes the dependency mandatory at compile time yet allows it to be absent at runtime.

When combining `requires static transitive`, both properties coexist: transitive readability **for compilation**, optionality **at runtime**. For code to actually use optional classes at runtime, the module must be present and resolved; the API portion must still be exposed with `exports`.

Official sources:

- [Java Language Specification SE 21 — `7.7.1 Dependences](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.1): semantics of `requires`, `transitive`, and `static`.
- [java.lang.module package — Resolution and Readability](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html): resolving the module graph and establishing read edges.
- [dev.java — Optional Dependencies with requires static](https://dev.java/learn/modules/optional-dependencies/): examples and practice with optional dependencies.
- [JDK 21 javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--module-source-path`, `--module-path`, `--release`, and compiling multiple named modules.
- [JDK 21 java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--add-modules`, and `--show-module-resolution`.

**A module seen on the module path is not necessarily resolved; a resolved module is not necessarily read by every other module; a module that is read does not necessarily export the needed package.** These three boundaries explain most JPMS errors when compiling and deploying transitive or optional dependencies.