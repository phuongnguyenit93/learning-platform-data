# Distinguishing Module Modification via Instrumentation from --add-modules, --add-reads, and --add-opens Configurations

In the Java Platform Module System (JPMS), when a Java agent wants to read classes, call APIs, or access private members belonging to a **named module**, it typically involves at least three distinct concerns: whether that module **has been resolved into a module layer**, whether the source module **can read the target module**, and whether the required package **is exported/opened to the caller**. Treating them as a single kind of "general access permission" leads to misconfiguration during instrumentation.

There are two main intervention points:

- **At JVM startup:** use the launcher options `--add-modules`, `--add-reads`, `--add-opens` (and `--add-exports` when needed) to adjust module resolution and access relationships.
- **When the JVM is already running and the agent has an `Instrumentation` object:** call `Instrumentation.redefineModule(...)` to **extend** `reads`, `exports`, `opens`, and service usage/provider declarations for an **existing** module. This is a **runtime module graph** update, not a way to create new modules or load new root modules.

This topic falls under **Instrumentation and Modules**. This article presents the exact meaning of each mechanism, when to use them as alternatives or complements, their relationship with class loaders, access permissions via reflection and agent-injected bytecode, how to verify results via `Module.canRead`/`Module.isOpen`, a **tested Java 17+ example** with three configurations, and the exceptions and limitations to keep in mind.

> **Version:** JPMS and `Instrumentation.redefineModule` were introduced in Java 9. The example uses `javac --release 17` and was compiled/run successfully on OpenJDK 24; use JDK 17+ with support for Java agents and named modules. Do not use JDK internals without compatibility guarantees.

## 1. Four Different Questions About Modules

Let's start with a diagram:

~~~text
1. Module OBSERVABLE?
   | Is there a module on --module-path / runtime image that can be found during resolution?
   v
2. Module RESOLVED?
   | Is it in the boot module layer (or a created layer)?
   v
3. Module READS target module?
   | Is m.canRead(other) true?
   v
4. Package EXPORTED / OPENED to caller?
   | Do public access and deep reflection have corresponding permissions?
   v
   Can MethodHandles / Reflection / bytecode linkage execute?
~~~

These four layers of conditions are related, yet **do not replace one another**.

| Concept | Core Question | Verification Example |
| --- | --- | --- |
| **Module observable** | Does the system know the module exists so it can be resolved? | `--module-path mods` only provides the search path for modules |
| **Module resolved** | Has the module been selected into the module graph/layer? | `ModuleLayer.boot().findModule("demo.vault")` |
| **Readability** | Is the source module allowed to read the target module? | `source.canRead(target)` |
| **Export** | Is the package exposed to a module for accessing public types/members? | `source.isExported("p", target)` |
| **Open** | Is the package opened for deep reflection into non-public members? | `source.isOpen("p", target)` |
| **Modifiability** | Can the agent use `redefineModule` on this module? | `instrumentation.isModifiableModule(source)` |

A module may already be **resolved** but lack `requires java.logging`, and therefore not yet **read** `java.logging`. A package may be **exported** to allow calling public methods but **not yet opened** for `setAccessible(true)` on private fields/methods. And even if `isModifiableModule` returns `true`, it does **not** automatically open any package before the agent calls the corresponding API.

## 2. Quick Comparison of the Three Launcher Options and `redefineModule`

| Mechanism | Timing | Main Change | Cannot Do |
| --- | --- | --- | --- |
| `--add-modules M` | JVM startup / module resolution | Adds **root modules** to resolve, along with their `requires` dependencies | Does not automatically add arbitrary `reads` between modules; does not open packages |
| `--add-reads M=N` | Startup / module graph initialization | Adds edge **M reads N** (directed from M → N) | Does not resolve a non-existent module; does not export/open N's packages |
| `--add-opens M/p=N` | Startup / module graph initialization | Opens package `p` of module M to N for **deep reflection** | Does not add a root module; does not automatically modify all other packages |
| `--add-exports M/p=N` | Startup / module access | Exports package `p` so public APIs can be accessed from N | Does not open private members for deep reflection |
| `Instrumentation.redefineModule(M,...)` | **Runtime**, from a Java agent with `Instrumentation` | Extends `reads`, `exports`, `opens`, `uses`, `provides` on an **existing module** | Does not create or resolve new modules; does not remove previously granted relationships; does not modify `module-info.class` on disk |

**Core distinction:**

- `--add-modules` specifies **which modules participate in resolution at startup**.
- `--add-reads` specifies **which module reads which module**.
- `--add-opens` specifies **which package is opened for deep reflection to which module**.
- `redefineModule` specifies **that the agent additionally updates relationships of an existing module at runtime**.

No single command among the three launcher flags is completely equivalent to `redefineModule`: the runtime API also supports `extraExports`, `extraUses`, and `extraProvides`. Conversely, `redefineModule` does not replace the resolution/root selection role of `--add-modules`.

## 3. `--module-path` and `--add-modules`: Finding a Module Does Not Mean Resolving It

A project might place `demo.vault` under the module path directory:

~~~bash
java --module-path mods -cp app-out Main
~~~

This makes `demo.vault` **observable** if the directory/module structure is valid; it does **not** automatically force it to appear in the boot layer of every program launched via classpath. Applications on the classpath usually reside in an **unnamed module**, and the launcher's default set of root modules does not necessarily include an application module that has not been requested.

To request resolution:

~~~bash
java --module-path mods --add-modules demo.vault -cp app-out Main
~~~

`--add-modules demo.vault` adds `demo.vault` to the resolution roots. If `demo.vault`'s descriptor has `requires` clauses for other modules, the resolver also considers those dependencies. However, this flag does **not** imply that `demo.vault` reads all modules in the runtime image, nor does it open `demo.vault`'s packages.

Multiple roots can be listed:

~~~bash
java --module-path mods --add-modules demo.vault,java.logging -cp app-out Main
~~~

Special values like `ALL-DEFAULT`, `ALL-SYSTEM`, or `ALL-MODULE-PATH` have specific semantics in the launcher. They can resolve a large number of modules, so use them intentionally and avoid putting them into production indiscriminately.

**Post-startup check:**

~~~java
boolean present =
        ModuleLayer.boot().findModule("demo.vault").isPresent();
~~~

The snippet above is not a standalone program; place it in a class with `main` as in the example in section 8. When `present=false`, do not start by calling `redefineModule` on a non-existent module object. First, verify that the module is placed on a valid module path and has been resolved into the layer the application is inspecting.

### 3.1. `--add-modules` Is Not `--add-reads`

Suppose `demo.vault` does not declare `requires java.logging;`. Even if both `demo.vault` and `java.logging` are resolved, module `demo.vault` still does not read `java.logging` by default. Adding another root module to the layer and adding a **read edge** between two modules are two different actions.

**Diagnostic tip:** use `ModuleLayer.boot().findModule(...)` to check resolution; use `Module.canRead(...)` to check readability. Do not conflate the two questions into "the module is on the module path yet it still fails" because they can have different causes.

## 4. `--add-reads`: Adding a One-Way Readability Edge

Launcher syntax:

~~~bash
java "--add-reads=demo.vault=java.logging" ...
~~~

Meaning: **source module `demo.vault` is allowed to read target module `java.logging`**. The reverse direction is **not** implied. If `java.logging` does not already read `demo.vault`, adding the edge `demo.vault → java.logging` does not automatically create `java.logging → demo.vault`.

Multiple target modules can be specified in one value, where the launcher permits. The special value `ALL-UNNAMED` of `--add-reads` means the source module is allowed to read unnamed modules according to launcher semantics; whereas the runtime API `extraReads` takes **specific `Module` objects**, so there is no `"ALL-UNNAMED"` sentinel string in the signature.

**Readability is not permission to access every package.** If the target module does not export the package you need, adding `reads` is still insufficient to call a public class in an encapsulated package. If you want deep reflection into private members, you must look at `opens`, not just `reads`.

This syntax is useful when bytecode instrumentation inserts calls to a type in another module while the module containing the modified method **has not declared `requires` on that module**. However, the compiler and runtime have different verification stages: `redefineModule` running at runtime does **not** automatically make `javac` compile source code missing a valid `requires`. For actual source modules, use the appropriate module descriptor/compiler flags, rather than merely adding runtime readability and expecting compile-time checks to be bypassed.

**Note:** having a read edge does not guarantee that instrumented bytecode will execute successfully. The class loader must still be able to load the type, the target module must export/open the appropriate package, and the helper must have the correct method descriptor.

## 5. `--add-opens`: Deep Reflection, Not Module Discovery

Syntax:

~~~bash
java "--add-opens=demo.vault/demo.vault=ALL-UNNAMED" ...
~~~

Breakdown:

- The first part `demo.vault` is the **source module** containing the package to open.
- The part after `/` is the **package name** `demo.vault` (which may share the same string as the module name, but they are two separate concepts).
- `ALL-UNNAMED` is a special target, meaning the package is opened to **all unnamed modules**, including unnamed modules created later according to launcher semantics.

When a package is opened to the caller module, code in the caller may be permitted to use `AccessibleObject.setAccessible(true)` or `MethodHandles.privateLookupIn` under appropriate conditions to access members otherwise blocked by strong encapsulation. Without `opens` permission, `setAccessible(true)` on a private method may throw `InaccessibleObjectException`.

`--add-opens` does **not** create module `demo.vault` if it has not been resolved; nor does it replace `--add-reads` if code in the source module needs to read another module.

### 5.1. `--add-opens` vs. `--add-exports`

| Scenario | Typically Needed |
| --- | --- |
| Code in another module wants to call **public** classes/methods from an unexported package | `exports` and an appropriate `reads` relationship |
| Reflection into **private** methods/fields of a class in a package | `opens` to the caller module |
| DI/ORM/serializer framework using deep reflection | `opens` to the corresponding framework module or unnamed module |
| Bytecode inserting `invokestatic Helper.method` from a module that does not read the helper module | Read edge + export/access + appropriate visibility |
| Agent only retrieving package or module names | Does not necessarily require opening the entire package |

**Subtlety when reading `Module.isExported`:** The `java.lang.Module` Javadoc states that a package **already open to a module is considered exported to that module at runtime**. Therefore, `isExported(package, target)` may return `true` after an `--add-opens` or `extraOpens` even without a separate `extraExports` operation. Do not use `isExported==true` to conclude "explicit export exists but the package is not open." To check deep reflection permission, use **`isOpen`**.

## 6. `Instrumentation.redefineModule`: Updating the Module Graph While the JVM Is Running

A Java agent receives `Instrumentation` in `premain` at startup or `agentmain` upon dynamic attach (if supported by the JVM). API:

~~~java
void redefineModule(
        Module module,
        java.util.Set<Module> extraReads,
        java.util.Map<String, java.util.Set<Module>> extraExports,
        java.util.Map<String, java.util.Set<Module>> extraOpens,
        java.util.Set<Class<?>> extraUses,
        java.util.Map<Class<?>, java.util.List<Class<?>>> extraProvides);
~~~

The signature above is for parameter reference, **not standalone source code**.

| Parameter | What to Pass | Meaning |
| --- | --- | --- |
| `module` | The **source** module being adjusted | An actual existing `Module` object |
| `extraReads` | `Set<Module>` | Adds read edges from the source to the modules in the set |
| `extraExports` | `Map<String, Set<Module>>` | Additionally exports packages belonging to the source module to the specified modules |
| `extraOpens` | `Map<String, Set<Module>>` | Additionally opens packages belonging to the source module to the specified modules |
| `extraUses` | `Set<Class<?>>` | Adds service types used by the source module |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>` | Adds service providers provided by the source module |

`extraExports` and `extraOpens` take keys as **dot-separated full package names**, for example `"demo.vault"`, **not** internal JVM names `"demo/vault"`. The value must be a **non-empty set** whenever a key is present. All arguments must be non-null; when you do not want to modify a relationship type, pass `Set.of()` or `Map.of()` of the appropriate type.

### 6.1. This Is an Extension, Not a Reset

The Javadoc specifies that `redefineModule` cannot remove existing read edges, exports, opens, uses, or provides. Calling it multiple times can **add** relationships, and provides no "unread", "unexport", or "re-close package" button to undo them.

If called on an **unnamed module**, the API is a **no-op**. `isModifiableModule(unnamed)` may still return `true` per the contract, but there is no reason to expect calling this API to change the state of the classpath's module in the same way as a named module.

Because `redefineModule` adds runtime permissions, this is a **process-wide action** on the module graph; it should not be called indiscriminately for every module as a workaround for misconfigured helpers.

### 6.2. Lacks the "Add Root" Capability of `--add-modules`

`redefineModule` requires a `Module` object and operates on an existing module; it does **not** add a root module to the boot layer. If `ModuleLayer.boot().findModule("demo.vault")` returns `Optional.empty`, you cannot fix that by calling `redefineModule` on an unresolved name string.

You can use module-layer resolution APIs to create new layers in application design, but that is a **different** topic and mechanism from `redefineModule`. This article focuses on the difference between root selection at startup and extending the runtime graph of an existing module.

### 6.3. Allowing an Agent to Do What Modules Normally Cannot Do on Their Own

Regular `Module.addReads`/`Module.addOpens` APIs have **caller** restrictions: another module cannot arbitrarily open a target module simply by calling `Module.addOpens` from the outside. `Instrumentation.redefineModule` is provided to agents so they can update the module graph when instrumentation requires it, within what the JVM permits.

Therefore, if code running in an **agent's unnamed module** calls `vault.addOpens("demo.vault", app)`, that is not automatically a valid alternative: it may throw `IllegalCallerException` because the caller is not the `vault` module. An agent using `Instrumentation.redefineModule` per its contract is clearer and more testable.

### 6.4. Checking Before Modifying

~~~java
if (!inst.isModifiableModule(vault)) {
    throw new IllegalStateException("Module is not modifiable");
}
~~~

This snippet is only valid inside a method that already has `inst` and `vault`. `isModifiableModule` is **different** from `isModifiableClass`: adjusting the module graph is not the same as redefining/retransforming the bytecode of a `Class<?>`.

## 7. Before/After Model in a Closed Named Module

We have module `demo.vault` with the descriptor:

~~~java
module demo.vault {
}
~~~

It has **no `exports demo.vault;`**, **no `opens demo.vault;`**, and **no `requires java.logging;`**. Inside the module is the class:

~~~java
package demo.vault;

public final class Secrets {
    private static String secret() { return "secret-value"; }
}
~~~

The class and the method are two different things to check: the class may exist and be loaded by the JVM, but the private method cannot be accessed via deep reflection from the unnamed app when the package is not yet open. To observe this, the `Main` application will query:

~~~java
Module vault = ModuleLayer.boot()
        .findModule("demo.vault")
        .orElseThrow();
Module app = Main.class.getModule(); // unnamed module on classpath
Module logging = java.util.logging.Logger.class.getModule();

boolean reads = vault.canRead(logging);
boolean open = vault.isOpen("demo.vault", app);
~~~

This is just a snippet used in full inside `Main.java` in section 8.

The three states we want to see:

~~~text
BEFORE RESOLUTION (without --add-modules):
demo.vault is not in the boot layer -> no Module to modify

AFTER --add-modules demo.vault,java.logging (no permissions added yet):
demo.vault is resolved
reads java.logging = false
open demo.vault to unnamed app = false
deep reflection private method = blocked

AFTER Instrumentation.redefineModule(...):
reads java.logging = true
open demo.vault to the exact unnamed app = true
deep reflection private method = allowed

WITH --add-reads and --add-opens FLAGS AT LAUNCH:
read/open are already true before the agent calls redefineModule
~~~

This experiment **intentionally does not inject new bytecode**, only illustrating the module graph. To use it with a real transformer, you still have to verify helper class/package/loader access and the generated bytecode calls.

## 8. Runnable Java 17+ Demo: Three Configurations, One Agent

The demo set has **four source files** and one manifest:

~~~text
demo/
  src/
    demo.vault/
      module-info.java
      demo/
        vault/
          Secrets.java
  Agent.java
  Main.java
  MANIFEST.MF
~~~

**Expected results:**

1. Without requesting an additional root module: `demo.vault` is **not resolved** into the sample program's boot layer.
2. With only `--add-modules`: the module is resolved, but read/open permissions are still missing; then **the agent grants permissions at runtime**.
3. With `--add-modules`, `--add-reads`, and `--add-opens` all provided: permissions are already configured at startup, so the agent does not need to "fix" the failure from the previous run.

This is a startup agent to avoid dependence on the Attach API and per-JVM dynamic agent loading; `premain` receives `Instrumentation` from the JVM at startup. The build uses a plain classpath for `Agent` and `Main`, while using the module path for `demo.vault`.

### 8.1. `src/demo.vault/module-info.java`

~~~java
module demo.vault {
}
~~~

The descriptor intentionally **does not export/open the package** and **does not require java.logging**. A module automatically reads `java.base` under JPMS, but that does not imply reading `java.logging`.

### 8.2. `src/demo.vault/demo/vault/Secrets.java`

~~~java
package demo.vault;

public final class Secrets {
    private static String secret() {
        return "secret-value";
    }
}
~~~

`Secrets` is a public class in an unexported package. The `secret` method is private. Code in an unnamed module can obtain `Class<?>` by name under runtime conditions, but `setAccessible(true)` is not allowed to bypass `opens` rules. In the demo, calling reflection **after** the package is opened retrieves `secret-value`.

### 8.3. `Agent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class Agent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void grant(Module source, Module app, Module logging) {
        if (!instrumentation.isModifiableModule(source)) {
            throw new IllegalStateException("Module is not modifiable");
        }

        instrumentation.redefineModule(
                source,
                Set.of(logging),
                Map.of(),
                Map.of("demo.vault", Set.of(app)),
                Set.of(),
                Map.of());
    }
}
~~~

Step-by-step explanation:

- `premain` receives and stores `Instrumentation`; the example does not call `new Instrumentation()`.
- `isModifiableModule(source)` checks whether the JVM allows modifying the module before proceeding.
- `Set.of(logging)` corresponds to **adding the read edge** `demo.vault → java.logging`.
- `Map.of()` for `extraExports` means the demo **does not request a separate export**.
- `Map.of("demo.vault", Set.of(app))` for `extraOpens` means opening **specifically package `demo.vault`** of the source module to **the exact unnamed Module object of `Main`**.
- The last two arguments `Set.of()` and `Map.of()` mean **no additional uses/provides**.
- Calling the API at startup or runtime follows the same contract: it only adds permissions, never removing previously granted ones.

**Notable difference from the launcher:** `--add-opens=demo.vault/demo.vault=ALL-UNNAMED` affects **all unnamed modules** per launcher semantics, whereas `Set.of(app)` opens only to **one specific module object**. If the runtime has multiple class loaders, each of their unnamed modules may be a different object; do not assume an `extraOpens` call for `app` applies to all of them.

### 8.4. `Main.java`

~~~java
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.util.logging.Logger;

public final class Main {
    public static void main(String[] args) throws Exception {
        var found = ModuleLayer.boot().findModule("demo.vault");
        System.out.println("MODULE_RESOLVED=" + found.isPresent());
        if (found.isEmpty()) return;

        Module vault = found.orElseThrow();
        Module app = Main.class.getModule();
        Module logging = Logger.class.getModule();

        System.out.println("READS_LOGGING_BEFORE=" + vault.canRead(logging));
        System.out.println("OPEN_TO_APP_BEFORE=" + vault.isOpen("demo.vault", app));
        System.out.println("REFLECTION_BEFORE=" + reflection());

        Agent.grant(vault, app, logging);

        System.out.println("READS_LOGGING_AFTER=" + vault.canRead(logging));
        System.out.println("OPEN_TO_APP_AFTER=" + vault.isOpen("demo.vault", app));
        System.out.println("REFLECTION_AFTER=" + reflection());
    }

    private static String reflection() throws Exception {
        Class<?> type = Class.forName("demo.vault.Secrets");
        Method method = type.getDeclaredMethod("secret");
        try {
            method.setAccessible(true);
        } catch (InaccessibleObjectException ex) {
            return "BLOCKED";
        }
        return (String) method.invoke(null);
    }
}
~~~

Intentional details:

1. `ModuleLayer.boot().findModule("demo.vault")` distinguishes **an unresolved module** from **a resolved module that still lacks permissions**. If unresolved, the program prints `MODULE_RESOLVED=false` and exits; it does not assume `redefineModule` can resolve that module.
2. `Logger.class.getModule()` provides the `java.logging` module object to measure readability and serve as the target of `extraReads`. Both runs that include `demo.vault` require `--add-modules demo.vault,java.logging` to ensure those modules are resolved.
3. `Main.class.getModule()` is the unnamed module of the classpath app in the demo; it is the **target of `extraOpens`** at runtime.
4. `vault.canRead(logging)` and `vault.isOpen("demo.vault", app)` yield two booleans for **different purposes**.
5. `Class.forName(...)` looks up class `Secrets` by its known name. `getDeclaredMethod("secret")` retrieves the method metadata; `setAccessible(true)` is where deep reflection is blocked when the package is not yet open.
6. Only `InaccessibleObjectException` is caught around `setAccessible(true)`, returning the string `BLOCKED` so the demo has clear stdout. The example does not treat every `ReflectiveOperationException` or module-resolution failure as "properly blocked"; other errors are allowed to surface so tests report failures accurately.
7. `Agent.grant(...)` is called **after the BEFORE measurements**; this allows observing actual runtime mutation rather than starting in a state where all permissions are already granted.
8. There is no need to access private contents via the compiler in `Main`, so the app can compile even though the package is not exported/opened. This is a technique for **observing reflection capability**, not a recommendation to write entire applications using reflection.

### 8.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

The manifest file requires a trailing newline and a blank line after the main section. `Can-Retransform-Classes` and `Can-Redefine-Classes` are not needed because this demo **does not call `retransformClasses`/`redefineClasses`**. `redefineModule` has its own `isModifiableModule` API; do not confuse permission to modify modules with permission to modify class bytecode.

### 8.6. Compile and Package Commands

From the `demo/` directory:

~~~bash
javac --release 17 -d mods/demo.vault src/demo.vault/module-info.java src/demo.vault/demo/vault/Secrets.java
javac --release 17 -d agent-out Agent.java
javac --release 17 -cp agent-out -d app-out Main.java
jar --create --file agent.jar --manifest MANIFEST.MF -C agent-out .
~~~

`mods/demo.vault` then contains `module-info.class` and `demo/vault/Secrets.class`. This is an **exploded named module** on the module path `mods`. `agent-out` has `Agent.class`, `app-out` has `Main.class`, and `agent.jar` has `Premain-Class: Agent`.

To run it, do **not** place `mods/demo.vault` directly on the classpath. It is discovered via `--module-path mods` and resolved via `--add-modules`. This is precisely the module path/classpath boundary the demo is designed to test.

### 8.7. Run 1 — Module Observable but Not Resolved

~~~bash
java --module-path mods -javaagent:agent.jar -cp app-out Main
~~~

**Experimental standard output (OpenJDK 24, Java 17 class files):**

~~~text
MODULE_RESOLVED=false
~~~

In this configuration, `demo.vault` is neither requested as a root nor a dependency of any selected module. Therefore, it is not in the boot layer even though the module path directory contains all the class files. `Main` returns immediately without calling `Agent.grant`.

Do not conclude that **every** named module placed on the module path in every program is unresolved: if a module is the main module or is required via `requires`/other root options, it may already be resolved. This run illustrates a specific module **with no other reason to be resolved**.

### 8.8. Run 2 — Add `--add-modules`, Agent Grants Permissions at Runtime

~~~bash
java --module-path mods --add-modules demo.vault,java.logging -javaagent:agent.jar -cp app-out Main
~~~

**Actual compiled and executed standard output:**

~~~text
MODULE_RESOLVED=true
READS_LOGGING_BEFORE=false
OPEN_TO_APP_BEFORE=false
REFLECTION_BEFORE=BLOCKED
READS_LOGGING_AFTER=true
OPEN_TO_APP_AFTER=true
REFLECTION_AFTER=secret-value
~~~

Points to analyze:

- `MODULE_RESOLVED=true` proves `demo.vault` entered the boot layer thanks to `--add-modules`.
- `READS_LOGGING_BEFORE=false` because `demo.vault`'s descriptor does not `requires java.logging` and no read edge has been added yet.
- `OPEN_TO_APP_BEFORE=false` because package `demo.vault` is not yet open to the unnamed app.
- `REFLECTION_BEFORE=BLOCKED` because `setAccessible(true)` is not yet permitted on the private member.
- After `Agent.grant`, `extraReads` creates an edge to `java.logging`, and `extraOpens` opens the package to `app`; checks on the same `Module` objects immediately switch to `true`.
- `REFLECTION_AFTER=secret-value` proves deep reflection is now allowed, and the private method returns the string as designed.

This proves **no restart is needed** to add permissions for an existing module when the agent successfully uses `redefineModule`. However, the same logic cannot be used to create new root modules or to roll back granted permissions.

### 8.9. Run 3 — Configure `--add-reads` and `--add-opens` Right at Startup

~~~bash
java --module-path mods --add-modules demo.vault,java.logging "--add-reads=demo.vault=java.logging" "--add-opens=demo.vault/demo.vault=ALL-UNNAMED" -javaagent:agent.jar -cp app-out Main
~~~

Quoting the entire argument containing `=` helps preserve JVM arguments across common shells, especially when using Windows PowerShell. Place **all JVM options before the `Main` class name**; if placed after `Main`, they become application arguments.

**Standard output verified on OpenJDK 24:**

~~~text
MODULE_RESOLVED=true
READS_LOGGING_BEFORE=true
OPEN_TO_APP_BEFORE=true
REFLECTION_BEFORE=secret-value
READS_LOGGING_AFTER=true
OPEN_TO_APP_AFTER=true
REFLECTION_AFTER=secret-value
~~~

Conclusions from the comparison:

- `--add-modules` makes the module resolved at startup.
- `--add-reads` makes `canRead(java.logging)` true **before the agent modifies the graph**.
- `--add-opens` makes `isOpen("demo.vault", app)` true, so private member reflection succeeds **right at the BEFORE check**.
- Calling `redefineModule` again only adds relationships that already exist; the API is additive, so the AFTER state remains true. It is neither an undo operation nor a replacement for the flags.

Run 2 and Run 3 have similar **final states** for that exact app module object, but **the timing of when permissions take effect differs**. Run 3 applies at startup for all unnamed modules; Run 2 grants permissions when the agent is invoked for one specific unnamed module. Do not mistake the two as completely equivalent.

## 9. Reading Results with the `Module` API, Not Just Guessing from JVM Flags

Recommended ways to observe:

| Check | What Is It Asking? | Note |
| --- | --- | --- |
| `ModuleLayer.boot().findModule("demo.vault")` | Is the module in the boot layer yet? | Does not imply readability or openness |
| `vault.canRead(logging)` | Does vault read logging? | This edge is one-way; not determined solely by launcher flags |
| `vault.isExported("demo.vault", app)` | Is public access considered exported to app? | May be true because the package is **open** to app |
| `vault.isOpen("demo.vault", app)` | Is deep reflection open to app yet? | Tied to a specific package and target module |
| `inst.isModifiableModule(vault)` | Can the agent update this module? | Does not mean class bytes are modifiable |
| `Main.class.getModule()` | The unnamed/named module **of Main** | Not guaranteed to match an unnamed module in another custom loader |
| `ClassLoader.getSystemClassLoader()` | Current system loader | Cannot answer all module relationships |

**What `Module.isOpen` does not prove:** code is not guaranteed to run correctly just because a package is open. The module must still be resolved, the class loader must find the class, the method signature must be correct, member access permissions must be valid, and the execution logic must not throw errors. In the demo, those conditions are actually verified via `Method.invoke`.

### 9.1. Runtime Module Graph and Descriptor Are Not the Same Configuration Object

A module descriptor in `module-info.class` may remain unchanged on disk after the JVM applies flags or `redefineModule`. Therefore, reading `module.getDescriptor().requires()` or reopening `module-info.java` is **not** the only way to determine runtime read edges. Use `Module.canRead`, `isExported`, `isOpen`, and test actual access in the JVM.

Do not modify `module-info.java` at runtime via `redefineModule`. The API does not rewrite source files, compile, or alter JARs on disk; it updates the module relationships used by the JVM in the current process.

## 10. When Bytecode Instrumentation Needs Helpers in Another Module

If a transformer inserts a call to helper `H` into module `M`, trace the path separately:

~~~text
JVM uses class loader to locate helper class H
        |
        v
Does module M have a read edge to the module containing H?
        |
        v
Is H's package properly exported/opened to M?
        |
        v
Are method owner/name/descriptor/opcode in bytecode correct?
        |
        v
Does the hook execute without causing dangerous recursion/exceptions?
~~~

A scenario:

~~~text
Module demo.app has method process()
  -> agent inserts invokestatic demo.agent.helper.Probe.record(...)
     -> Probe is in module demo.agent.helper, different from demo.app
     -> demo.app does not yet require the helper module
     -> may need to extend reads from demo.app to the helper module
     -> helper package needs to be exported to demo.app
     -> the defining class loader of process() must see Probe
~~~

If using `Instrumentation.redefineModule` once the agent has started, conceptual example:

~~~java
inst.redefineModule(
        applicationModule,
        Set.of(helperModule),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**This snippet is not standalone:** `inst`, `applicationModule`, and `helperModule` must already be resolved objects in the agent's context. It only adds a **read edge**. If the helper's package is not yet exported to the application module, the relationship must be adjusted on the **helper module side**, for example calling `redefineModule(helperModule, Set.of(), Map.of("helper.pkg", Set.of(applicationModule)), ...)`, rather than arbitrarily opening the application module's packages.

For helpers loaded from a JAR into an **unnamed module** on the classpath/system loader, the target object for `extraReads` is the appropriate unnamed `Module`; there is no `ALL-UNNAMED` literal as an argument to `Set<Module>`. Configuring `--add-reads M=ALL-UNNAMED` at startup is a different approach with a different scope.

If the goal is **deep reflection** by the agent into a private field in module M, you need **extraOpens** from **M to the caller's module**, not an extra read edge in an arbitrary direction. These are two different use cases even if both appear in the same agent.

### 10.1. When Should `redefineModule` Be Called?

- For a startup agent, you can update the module graph in `premain` before registering transformers and before the application enters code paths needing the helper.
- For a dynamic attach agent, you can update the graph in `agentmain` after the JVM is already running; however, you must check which classes/bytecode have already been loaded and whether linking errors already occurred before the agent intervened.
- When changing the module graph after bytecode has already created symbolic references, be cautious about resolution failures that have already occurred. Some resolution errors may be cached by the JVM for the same symbolic reference; granting permissions late does not guarantee all old invocations will automatically recover.
- If multiple threads/agents modify modules concurrently, `redefineModule` is permitted for concurrent use by the Javadoc, yet you still need to plan permission scopes and track changes.
- Only open the necessary packages/target modules to minimize the security impact surface.

An exception arising from whether **injected bytecode is valid**, such as `VerifyError` due to an incorrect operand stack, **is not automatically fixed** just by `--add-opens` or `redefineModule`. Module access and the bytecode verifier are different layers of checks.

## 11. What Is the Scope of `extraExports` and `extraOpens`?

Consider two snippets (both **in a context that already has `Instrumentation inst`**):

**Exporting a package to a consumer module:**

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of("com.example.api", Set.of(consumerModule)),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**Opening a package for reflection into private members:**

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of(),
        Map.of("com.example.internal", Set.of(reflectionModule)),
        Set.of(),
        Map.of());
~~~

Common pitfall: `sourceModule` must **own the package** named in the map. `extraExports`/`extraOpens` with a package name not belonging to the source module will result in `IllegalArgumentException` per the contract. The set of target modules for each package must not be empty. If you do not know module ownership, look it up via `Class.getModule()` on an actual type (where it is safe to load), rather than guessing from package strings.

Semantically, "export" is for **public access**, and "open" is for **deep reflective access**. When a package is open to a module, `Module.isExported(package, target)` also returns true at runtime; however, you should still choose the right operation to express **least privilege intent**. Do not use `extraOpens` everywhere just because code needs to call a public method.

### 11.1. The Service Parameters

`extraUses` and `extraProvides` have no direct equivalent among the three flags `--add-modules`, `--add-reads`, `--add-opens`. They allow an agent to add service use/provide relationships per the JPMS contract. However:

- `extraUses` holds service types as `Class<?>`; not service name strings.
- `extraProvides` maps a service type to a list of valid provider classes. A provider must belong to the right module and conform to the service contract, not be an arbitrary class.
- The Javadoc notes the agent's responsibility to ensure the service type is accessible at instrumentation sites; the API does not automatically make all packages/exports/readability valid simply by declaring use/provide.
- The lab exercise does not need service relationships, so the last two parameters pass empty collections. Do not add them just to "fill all six parameters."

## 12. `--add-modules` Is Neither `--patch-module` Nor `redefineModule`

Three similarly named mechanisms:

- `--add-modules` selects additional root modules to **resolve**.
- `--patch-module M=path` allows the launcher to **override or augment a module's contents** with class/resource files at path (subject to module/launcher constraints).
- `Instrumentation.redefineModule` adds **access/service relationships** to an existing module at runtime.

Do not confuse `redefineModule` with `redefineClasses`. Both methods start with `redefine`, but **their targets are different**:

| API | What Does It Modify? | Does It Change Method Bytecode? |
| --- | --- | --- |
| `Instrumentation.redefineModule` | A Module's reads/exports/opens/uses/provides | **No** |
| `Instrumentation.redefineClasses` | Class definitions, using new classfile bytes | Yes, within JVM limits |
| `Instrumentation.retransformClasses` | Re-runs the transformer pipeline on loaded classes | Possibly, if a transformer returns new bytes |
| `--patch-module` | Class/resource content fed into a module at startup | Can affect which class definitions the JVM picks at load time |
| `--add-modules` | Root module resolution | Does not directly change class bytes |

If the bug is "package is not open for reflection," `redefineClasses` is not the right solution. If the bug is "method body was instrumented incorrectly," opening the package with `redefineModule` cannot fix the operand stack or logic. Distinguishing the question saves many debugging cycles.

## 13. Limitations and Exceptions When Calling `redefineModule`

According to the Java 17 Javadoc, the API may throw:

| Type | Typical Cause |
| --- | --- |
| `UnmodifiableModuleException` | The specified module cannot be modified via `redefineModule` |
| `IllegalArgumentException` | Package key does not belong to the module; map contains an empty set; `extraProvides` has an invalid provider |
| `NullPointerException` | An argument or a key/value in the sets/maps is null |

**Note:** `isModifiableModule` returns true for an unnamed module, but calling `redefineModule` on an unnamed module is a **no-op**. Therefore, checking `isModifiableModule` alone is not enough to guarantee an observable effect. Practice on a named module and verify `canRead`/`isOpen` after the call.

There is no "unopen" or "remove extraReads" API via `redefineModule`. Once runtime permissions are granted, removing agent configuration later does not automatically revoke the added permissions. When testing multiple times in the same JVM, the "AFTER" state from the previous run may still be in effect; to test the true "BEFORE" state, run **a new JVM** as in the demo commands.

### 13.1. Runtime and Compiler Report Different Errors

- **Compiler:** package is not visible or source module does not `requires` target module when compiling source with direct references. Fix `module-info.java` or appropriate compiler configuration.
- **Runtime loader:** class not found (`ClassNotFoundException` / `NoClassDefFoundError`), even though the module graph may already be open.
- **Runtime access:** `IllegalAccessError` when bytecode linkage violates module/package permissions, or `InaccessibleObjectException` when deep reflection is blocked.
- **Bytecode validity:** `VerifyError`, `ClassFormatError` due to invalid bytecode transformation, not directly related to opens/reads flags.
- **Agent API:** `UnmodifiableModuleException`/`IllegalArgumentException` when passing invalid modules/packages/targets.

Do not catch a generic `Exception` and log "module inaccessible" for every case. Clearly record the **stage** (resolve, load, link, reflect, redefineModule) and the error type.

## 14. Least Privilege Rules When Opening Modules

The ability to modify the runtime module graph is useful for monitoring/tracing, but it also reduces encapsulation if used without control. Points to follow:

1. **Only open the exact packages needed.** Do not open entire modules or package trees when only one API is needed.
2. **Choose the right target module.** Use `Set.of(agentModule)`/`Set.of(helperModule)` instead of opening indiscriminately to all unnamed modules if the runtime scope allows.
3. **Distinguish export from open.** If only public linkage is needed, export and read; only deep reflection needs opens.
4. **Check the actual loader/module.** Two classes with the same package string may belong to different modules/loaders; targeting `Main.class.getModule()` is only right for the example's app.
5. **Do not grant permissions to a module that does not need them.** An unnecessary `extraReads` can alter coupling between modules; an unnecessary `extraOpens` can allow access to private state.
6. **Audit agent-made changes.** Log source module, package, target, timestamp, reason, and agent version; do not expose private data in diagnostics.
7. **Do not confuse a runtime patch with a long-term build policy.** If the application controls the source, prefer declaring valid `requires`/`exports`/`opens` in the module descriptor rather than overusing flags/agent workarounds.
8. **Ensure the module is resolved and helpers can be loaded.** Module permissions do not replace module path, classpath, and dependency packaging setup.

In JVMs used by multiple agents, extensions made by individual agents can combine; inspect the actual state of the module graph rather than assuming only your agent's configuration determines all permissions.

## 15. When to Use Startup Flags, and When to Use `redefineModule`?

| Need | Reasonable Preference | Why |
| --- | --- | --- |
| Certain that module M must be present from startup | `--module-path` + `--add-modules M` | The module must be resolved before obtaining a Module object |
| Need a stable read edge between two named modules from startup | `--add-reads M=N` or `requires` in descriptor | Configured before code runs |
| Framework known in advance to need deep reflection | `--add-opens M/p=N` or appropriate `opens` | Package is already open before the first reflection |
| Late-attaching agent needing instrumented code to read another module | `Instrumentation.redefineModule` if the module already exists | No restart needed to extend the graph |
| Agent needs to narrowly open a package to a specific helper's module | `extraOpens` to `Set.of(helperModule)` | Target scoped by Module object |
| Missing root module not resolved in the boot layer | Launcher `--add-modules` or layer design | `redefineModule` does not perform resolution |
| Want to update a class's method body | `retransformClasses` or `redefineClasses` per contract | Not the job of `redefineModule` |
| Only need a public API in an encapsulated package | Read + exports, do not open private members | Reduces granted permission surface |
| Need new service uses/providers for instrumentation | `redefineModule` with `extraUses`/`extraProvides` | The launcher flags above do not directly carry the same data |

A practical rule of thumb: **if the condition is known in advance and you have control over JVM startup, declaring it at startup is easier to reproduce**. If the condition only arises while the agent is running and the module is already resolved, `redefineModule` may be more appropriate. However, do not use the runtime API to mask a module resolution or packaging issue.

## 16. Symptom-Based Diagnostic Table

| Symptom | What to Check First |
| --- | --- |
| `ModuleLayer.boot().findModule("M")` returns empty | `--module-path`, root selection `--add-modules`, `requires` descriptor |
| `M.canRead(N)==false` | `requires`, `--add-reads M=N`, or `extraReads` |
| `M.isOpen("pkg", caller)==false` | `opens` in descriptor, `--add-opens M/pkg=caller`, or `extraOpens` |
| Public type is inaccessible | Read edge **and** export/access from the module containing the package |
| `setAccessible(true)` throws `InaccessibleObjectException` | Whether the package is open to the **actual caller module** |
| `NoClassDefFoundError` despite `canRead` being true | Whether the loader can find the helper class; whether the target module is resolved |
| `IllegalArgumentException` in `redefineModule` | Whether the package key belongs to the module; whether set/list values are valid |
| `UnmodifiableModuleException` | `isModifiableModule(module)`, module/JVM type |
| Added `--add-opens` yet module is still not found | Unresolved root/observable module |
| Agent modifies module yet compiler still rejects source | Runtime redefine does not change module descriptor or compile-time checks |
| `isExported` is true while `isOpen` is also true | An open package is considered exported at runtime; do not infer an explicit export |
| Second run has BEFORE=true | Different launcher flags configured, or reusing JVM/agent state |
| One unnamed module can call it while another plugin loader cannot | Runtime `extraOpens` may have granted permission only to **one Module object**, not ALL-UNNAMED |

## 17. QA Checklist for Agents Using JPMS

- [ ] Identify the exact **source module** to modify, target module, and package belonging to the source module.
- [ ] Determine whether the module is **resolved** or only **observable**; do not call `redefineModule` on a name string.
- [ ] Use `Module.canRead` to measure read edges and `isOpen` to measure deep reflection; remember opens can make `isExported` true at runtime.
- [ ] If a root module is needed from startup, use `--add-modules` and a proper module path; do not use `extraReads` instead of resolution.
- [ ] If only public access is needed, verify export/read before opening private access.
- [ ] For runtime mutation, check `isModifiableModule` and use non-null sets/maps and valid package keys.
- [ ] Separate permissions among the agent's unnamed module, the app's, and each custom class loader's.
- [ ] Prepare helper visibility/bytecode contracts before instrumenting classes on hot paths.
- [ ] Do not perform complex reflection or synchronous logging directly inside `ClassFileTransformer.transform`.
- [ ] Compare a **clean** JVM without flags against a JVM with flags and a JVM modified only by the agent at runtime.
- [ ] Measure actual behavior, not just a few boolean values; test module resolution, reflection/linkage, and exceptions.
- [ ] Note at runtime that granted permissions cannot be revoked via `redefineModule`.

## 18. Self-Check Questions

1. Module M is already on `--module-path`, yet `ModuleLayer.boot().findModule("M")` returns empty. Should you fix `--add-reads` or `--add-modules` first?
2. M needs to call a public class of N, but M does not yet read N. Does `--add-modules N` automatically create the read edge M → N?
3. Does `--add-reads M=N` automatically export or open N's packages to M?
4. Why does `--add-opens M/p=ALL-UNNAMED` have a different scope from `extraOpens=Map.of("p", Set.of(Main.class.getModule()))`?
5. When `isExported("p", app)` returns true because a package has been opened, which method should you use to measure deep reflection permission specifically?
6. Why does adding only `--add-opens` fail to resolve an unresolved module?
7. Does `redefineModule` make a new module appear in the boot layer? Can it remove a previously granted read edge?
8. Do `extraExports` and `extraOpens` accept keys in the form `"demo.vault"` or `"demo/vault"`?
9. What are the two parameters `extraUses` and `extraProvides` used for? Are they directly tied to the three launcher flags discussed?
10. Why can't `redefineModule` be replaced with `redefineClasses` to fix module access errors?
11. Why does the `Main` demo not import `demo.vault.Secrets` directly and instead uses reflection?
12. In Run 2, why is `REFLECTION_BEFORE=BLOCKED` while `REFLECTION_AFTER=secret-value`?
13. In Run 3, why are `READS_LOGGING_BEFORE=true` and `OPEN_TO_APP_BEFORE=true` before the agent modifies anything?
14. If a plugin loader has its own unnamed module, does runtime `Set.of(app)` grant permission to it?
15. When using an agent attached to a long-running JVM, why must you also consider resolution errors that occurred before permissions were granted?
16. What tests are needed to ensure a bytecode helper can actually link even after the module graph has been updated?

## 19. Conclusion

**Do not confuse three independent conditions: the module is resolved, the source module can read the target module, and the package is exported/opened to the caller module.** `--add-modules` handles **root module selection at startup**; `--add-reads` adds **readability**; `--add-opens` opens **deep reflection** for a specific package. They are three flags with different purposes and do not replace one another.

`Instrumentation.redefineModule` is a complementary tool for agents: it **dynamically and additively** modifies read/exports/opens/uses/provides of an **existing** module. It does not create/resolve modules, does not modify `module-info.class` files, does not turn invalid symbolic references or code into valid bytecode, and does not allow removing previously added permissions.

The three-configuration experiment illustrates this clearly: without adding roots, module `demo.vault` is not resolved; when roots are added without permissions, the agent can open read/open at runtime; when launcher flags are supplied at startup, permissions are already in place before the agent calls the API. Understanding these boundaries helps implement instrumentation on named modules accurately and avoid granting overly broad permissions.

### Official Documentation

- [Oracle JDK 17 — Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)): six parameters, additive principle, no-op for unnamed modules, and exceptions.
- [Oracle JDK 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--add-modules`, `--add-reads`, `--add-opens`, and `--add-exports`.
- [Oracle JDK 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, and the caller restrictions of `Module.addReads`/`Module.addOpens`.
- [Oracle JDK 17 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): error when suppressed Java access checks cannot be enabled.
- [Oracle JDK 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): layers with resolved modules and `findModule` lookup.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module resolution mechanism and launcher options introduced in Java 9.
