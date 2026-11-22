# `isModifiableModule` and Preconditions Before Modifying Module Relationships

> **Goal:** Understand precisely what `Instrumentation.isModifiableModule(Module)` checks; when a Java agent can call `Instrumentation.redefineModule(...)` to add **reads**, **exports**, **opens**, **uses**, or **provides** relationships; how to verify the right module, right package, and right recipient before making changes; and how to verify the result without confusing opening a module with modifying class bytecode.

This lesson belongs to the **Instrumentation Capabilities** topic of Java 17+. The focus is JPMS (Java Platform Module System) behavior at **runtime** in the JVM. A Java agent often needs permission to read a helper class or use reflection into a closed package; checking `isModifiableModule` is an important precondition step, but a `true` result is **not sufficient** to prove that every intended change is valid and safe.

## 1. Why Does Instrumentation Need to Care About Modules?

Since Java 9, JPMS allows applications to split code into **named modules**. A module declares dependencies and decides which packages are exported or opened to other modules. For example:

```java
// Application's module-info.java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
    // com.example.orders.internal is not exported/opened.
}
```

A Java agent wanting to insert a probe into `com.example.orders.internal.OrderRepository` may need to perform the following operations:

- Transformed bytecode calls a helper type located in **another module**, but the source module does not yet have the required `reads` relationship.
- The agent or framework wants to use reflection to access private fields/methods in `com.example.orders.internal`, but this package has not been **opened** to the module calling reflection.
- An implementation library wants to use a public API in a package that has not been **exported** to the consuming module.
- A component actually participating in `ServiceLoader` needs to add a `uses`/`provides` declaration at runtime.

Those scenarios concern **relationships between modules**, not necessarily replacing the bytes of a `.class`. `Instrumentation` supports modifying relationships via `redefineModule(...)`. Before executing it, the agent needs to identify the exact **Module object** belonging to the current JVM, check the module's modifiability, and validate the arguments.

## 2. Two Key APIs

```java
boolean isModifiableModule(Module module);

void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
```

These are API signatures for reference (not a standalone Java file; `Instrumentation`, `Set`, `Map`, and `List` belong to the JDK). Both methods were added in **Java 9** on `java.lang.instrument.Instrumentation`. A Java agent receives `Instrumentation` via `premain(String, Instrumentation)` when using `-javaagent`, or via `agentmain(String, Instrumentation)` if an appropriate dynamic agent mechanism is supported.

- **`isModifiableModule(module)`**: asks the JVM whether this module is allowed to be modified via `redefineModule`. `null` causes a `NullPointerException`.
- **`redefineModule(...)`**: adds new relationships to the runtime module graph. It **only extends** the set of reads/exports/opens/uses/provides; it cannot narrow or remove existing relationships.
- **For an unnamed module**: `isModifiableModule(unnamedModule)` always returns `true`, but `redefineModule` operating on an unnamed module is a **no-op**. Do not infer "it returned true so the call will change something."
- **For an unmodifiable named module**: `redefineModule` can throw `UnmodifiableModuleException`; check modifiability before calling and still handle errors at the call site.
- `redefineModule` is **completely different** from `redefineClasses` and `retransformClasses`: this modifies module relationships, not rewriting bytecode inside methods.

A common check pattern:

```java
Module target = SomeApplicationClass.class.getModule();

if (!target.isNamed()) {
    throw new IllegalArgumentException("Expected a named target module");
}
if (!instrumentation.isModifiableModule(target)) {
    throw new IllegalStateException("Target module is not modifiable");
}
```

The snippet above is a **logic pattern** used inside an agent that already has the `instrumentation` variable and the `SomeApplicationClass` type, not a self-contained runnable program. The hands-on exercise below has all the files needed to run independently.

## 3. Distinguishing Read, Export, and Open Before Adding Relationships

Suppose there are two named modules:

```text
com.example.app            (module containing code to observe)
com.example.agent.helper   (module containing helpers for the agent)
```

Three easily confused concepts:

| Relationship | Direction and Question | What It Allows | What It Does Not Automatically Do |
| --- | --- | --- | --- |
| **reads** | `app → helper`: can module `app` read `helper`? | Access resolution along the module graph, required for references to another module | Does not automatically export packages in `helper` |
| **exports** | `app/package → helper`: is `app`'s package exported to `helper`? | Normal access to the package's public API subject to visibility and module read conditions | Does not automatically allow deep reflection to private members |
| **opens** | `app/package → helper`: is the package opened to `helper`? | Allows deep reflection (`setAccessible`, appropriate lookup) within the opened scope | Not a guarantee that every call/method will succeed; does not turn private into public in source |

Observational queries on a runtime `Module`:

```java
boolean canRead   = app.canRead(helper);
boolean exported  = app.isExported("com.example.app.api", helper);
boolean opened    = app.isOpen("com.example.app.internal", helper);
```

This snippet illustrates the syntax in a context where two variables `Module app` and `Module helper` exist. `Module.isExported(package, other)` and `Module.isOpen(package, other)` check the relationship **to a specific module**; the overloads without `other` query unconditional export/open. The results of `isExported/isOpen` **do not check** whether the receiving module can read the source module: to understand actual accessibility, you may need to check the `reads` direction as well.

**An easily overlooked detail:** at runtime, a package **opened** to a module is treated as **exported** to that module for certain access checks; therefore `isExported(pkg, other)` can return `true` after the package is opened. Do not mistakenly infer from that value that the source `module-info.java` already had `exports`, or that rebuilding the application will still grant the same permission.

### Reads and opens are two different problems

Suppose the agent uses reflection on a `private` method. Adding a `reads` edge is **not enough** to bypass strong encapsulation. The package owner needs to open the right package to the module where **the reflection code is running**. Conversely, adding `opens` just to allow bytecode to call a public helper class may be broader than necessary; in that case, consider the appropriate reads/exports relationships.

For helper code in the agent's **unnamed module**, the `java.lang.instrument` package also describes certain read edges automatically arranged by the JVM for modules of transformed classes. Therefore, do not assume every bytecode probe must manually call `redefineModule` to add a read edge. First verify the actual access error and `Module.canRead(...)`.

## 4. All Six Arguments of `redefineModule`

The first argument is **the source module being modified**; the remaining five arguments describe the extensions:

| Argument | Type | Meaning |
| --- | --- | --- |
| `module` | `Module` | The module **being modified** (not the module receiving permission) |
| `extraReads` | `Set<Module>` | Additional modules that `module` is allowed to read |
| `extraExports` | `Map<String, Set<Module>>` | Packages of `module` additionally exported to each set of modules |
| `extraOpens` | `Map<String, Set<Module>>` | Packages of `module` additionally opened to each set of modules |
| `extraUses` | `Set<Class<?>>` | Service types declared as additionally used by `module` |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>` | Service types and lists of implementations declared as additionally provided |

The collections **may be empty** (e.g., `Set.of()` and `Map.of()`) when not modifying that kind of relationship; however, they **must not be `null`**. Wherever a map `extraExports`, `extraOpens`, or `extraProvides` has an entry, **the corresponding set/list must be non-empty**.

### Example: adding only a read edge

```java
// Both app and helper are verified Module instances:
instrumentation.redefineModule(
    app,
    Set.of(helper), // app reads helper
    Map.of(),       // No extra exported packages
    Map.of(),       // No extra opened packages
    Set.of(),       // No extra service uses
    Map.of()        // No extra service providers
);
```

After a successful call, check `app.canRead(helper)`. This does **not** automatically export `helper`'s packages; if `helper` is a named module with encapsulated packages, the export direction from `helper` to `app` must be considered separately. A class needs both a graph read edge **and** appropriate package/type/method access permissions.

### Example: opening only one package to the agent

```java
// app owns the internal package, agentModule is the agent's Module:
instrumentation.redefineModule(
    app,
    Set.of(),
    Map.of(),
    Map.of("com.example.app.internal", Set.of(agentModule)),
    Set.of(),
    Map.of()
);
```

Only **a package existing in `app`** may be used as a key. After the operation, check:

```java
boolean nowOpen =
        app.isOpen("com.example.app.internal", agentModule);
```

This is a change **from `app` to `agentModule`**, not from the agent to `app`. It has no effect on a package not belonging to `app`, and `extraOpens` **does not accept wildcards like `"com.example.*"`**.

### Example: selective export

```java
instrumentation.redefineModule(
    app,
    Set.of(),
    Map.of("com.example.app.api", Set.of(helper)),
    Map.of(),
    Set.of(),
    Map.of()
);
```

`extraExports` lets the receiving module use the appropriate public API of the package, **without opening deep reflection into private members**. Evaluate the read edge from `helper` to `app` if that is the access direction.

### `extraUses` and `extraProvides` have their own constraints

- Each element of `extraUses` is a **service type** (`Class<?>`). When expanding uses, the agent must ensure the service type is **accessible** at every site where instrumented code uses it; `redefineModule` does not automatically prove all of those access conditions.
- Each key of `extraProvides` is a service type. Each value is a **non-empty list** of implementation classes. Each provider must **belong to the module being modified** and be a valid implementation of the service type. An implementation from another module or one that does not implement the service can cause `IllegalArgumentException`.
- Do not use `extraProvides` to arbitrarily add classes to a module; the API only modifies service provider declarations at runtime, and does not create `.class` files or reload JARs.

An agent should only add uses/provides if it genuinely needs to integrate a service. The common problem of opening reflection into a package only needs `extraOpens`, as in the experiment.

## 5. Preconditions to Check Before `redefineModule`

A careful procedure consists of the checks below.

### 5.1. Identify the exact runtime Module object

A simple module name is not always sufficient identification, especially when an application uses multiple **module layers** or class loaders. Start from **the class that actually needs instrumentation**:

```java
Module target = targetClass.getModule();
```

Or, if certain the module is in the **boot layer**, use:

```java
Module target = ModuleLayer.boot()
        .findModule("com.example.app")
        .orElseThrow();
```

When custom module layers are used, do not assume the module is in the boot layer. `Module.getName()`, `getLayer()`, `getClassLoader()`, and `getPackages()` help verify this. If you grab the wrong `Module` object, `redefineModule` may modify **a module with the same name but a different instance**, not the running target.

### 5.2. Distinguish named and unnamed

```java
if (!target.isNamed()) {
    // JPMS: isModifiableModule returns true, but redefineModule is a no-op.
    // Choose an approach suitable for an unnamed module; do not report "package opened".
}
```

Unnamed modules already have broad read and open relationships by their own rules. Calling `redefineModule` on one has no value for opening an additional relationship. `isModifiableModule` returning `true` here is **not confirmation that a change will occur**.

### 5.3. Ask the JVM about module modifiability

```java
boolean modifiable = instrumentation.isModifiableModule(target);
if (!modifiable) {
    throw new IllegalStateException("Target module cannot be redefined");
}
```

This value is a property/capability of the module in the current JVM; do not guess based on whether the module belongs to `java.base`, an application JAR, or a library. `isModifiableModule` **does not replace** the data precondition checks below.

**Do not confuse with `isModifiableClass(...)`:** that check answers whether a class can participate in redefinition/retransformation. `isRetransformClassesSupported`/`isRedefineClassesSupported` are different capabilities. They are not needed just to call `redefineModule`, and `isModifiableModule` does not guarantee that a transformer has permission to modify method bytes.

### 5.4. Verify the package belongs to the source module

For `extraExports`/`extraOpens`, the key is the full package name, **not** a class name, a `module/package` string, a wildcard package, or a path containing `/`.

```java
String pkg = "com.example.app.internal";
if (!target.getPackages().contains(pkg)) {
    throw new IllegalArgumentException(
            "Package does not belong to target module: " + pkg);
}
```

If the package does not belong to the module, the API may throw `IllegalArgumentException`. Do not add a new package to a module via `redefineModule`.

### 5.5. Verify the exact recipient

For exports/opens, each `Set<Module>` must be non-empty. Each element must be **the actual module receiving permission**, obtained from the appropriate class/layer.

```java
Module agentModule = MyAgent.class.getModule();
if (agentModule == target) {
    throw new IllegalArgumentException(
            "Expected different source and receiving modules");
}
```

The snippet above is an example policy when intending to grant access to **an agent in another module**. The API itself does not forbid both variables from pointing to the same module; a module reads itself and can access its own packages under JPMS rules. Do not interpret this guard as a constraint mandated by the JDK.

**Important note on scope:** if `agentModule` is the **unnamed module** of the system class loader, opening a package to it means opening it to **all code in that same unnamed module**, not just a single agent class. To reduce the permission surface area, consider a helper in a separate named module if the architecture permits.

### 5.6. Validate collections and service consistency

- No argument or collection key/value element may be `null`; `NullPointerException` is specified by the API for those cases.
- Do not pass an `extraExports` or `extraOpens` entry with an empty `Set.of()`; `extraProvides` must not have an empty list.
- Package keys must genuinely belong to the **source module**.
- Provider classes must belong to the source module and implement the service type; check `provider.getModule()` and the type relationship before calling.
- For `extraUses`, verify yourself that the service type is accessible at the code sites where it will be used. Do not infer that every lookup will succeed just because the module has a uses edge.

Using `Map.of`/`Set.of` helps avoid `null` in simple examples, but data structures coming from external configuration still require validation before building collections and calling the API.

### 5.7. Determine whether the change is actually needed

Read the current relationship before requesting a change:

```java
if (!target.isOpen(pkg, agentModule)) {
    instrumentation.redefineModule(
            target, Set.of(), Map.of(),
            Map.of(pkg, Set.of(agentModule)),
            Set.of(), Map.of());
}
```

This makes intent easier to review and avoids adding permissions that already exist. However, in a JVM with multiple agents, state can change between the two statements. `redefineModule` is designed to be safe for concurrent calls; you **must still** catch errors and re-check the state after calling. Do not treat check-then-act as a transaction or a security locking mechanism.

## 6. Runnable Java 17+ Example: An Agent Opening a Package of a Named Module

The experiment uses:

- A **named module** `demo.target` with an unexported/unopened package `demo.target.internal`.
- A Java agent on the class path (belonging to the **unnamed module** of the system class loader) receiving `Instrumentation` via `premain`.
- The agent checks `isModifiableModule`, verifies the package exists, and calls `redefineModule` only to add a **qualified open** to the agent's module.
- Then the agent uses reflection to invoke a private static method to observe the effect. There is no bytecode transformation or dynamic agent loading.

### 6.1. File structure

```text
module-open-demo/
├── agent.mf
├── agent-src/
│   └── ModuleAccessAgent.java
└── src/
    └── demo.target/
        ├── module-info.java
        └── demo/
            └── target/
                ├── Main.java
                └── internal/
                    └── SecretBox.java
```

The `out/` directories will be created during compilation and do not need to exist beforehand.

**File `src/demo.target/module-info.java`:**

```java
module demo.target {
    // Intentionally does not export/open package demo.target.internal.
}
```

**File `src/demo.target/demo/target/Main.java`:**

```java
package demo.target;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app=running");
    }
}
```

**File `src/demo.target/demo/target/internal/SecretBox.java`:**

```java
package demo.target.internal;

public final class SecretBox {
    private SecretBox() {}

    private static String status() {
        return "READY";
    }
}
```

`SecretBox.status()` is private. Code in another module cannot use reflection to gain access to the private method if the package remains closed.

**File `agent-src/ModuleAccessAgent.java`:**

```java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class ModuleAccessAgent {
    public static void premain(String arguments, Instrumentation inst)
            throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target")
                .orElseThrow(() -> new IllegalStateException(
                        "Target module is not in the boot layer"));
        Module agentModule = ModuleAccessAgent.class.getModule();
        String pkg = "demo.target.internal";

        System.out.println("target named=" + target.isNamed());
        System.out.println("agent unnamed=" + !agentModule.isNamed());

        if (!target.isNamed()) {
            throw new IllegalStateException("Expected a named module");
        }
        if (!target.getPackages().contains(pkg)) {
            throw new IllegalStateException("Target package is missing");
        }

        boolean modifiable = inst.isModifiableModule(target);
        System.out.println("modifiable=" + modifiable);
        if (!modifiable) {
            System.out.println("module update=skipped");
            return;
        }

        boolean before = target.isOpen(pkg, agentModule);
        System.out.println("open before=" + before);

        if (!before) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of(),
                    Map.of(pkg, Set.of(agentModule)),
                    Set.of(),
                    Map.of()
            );
        }

        boolean after = target.isOpen(pkg, agentModule);
        System.out.println("open after=" + after);
        if (!after) {
            throw new IllegalStateException("Open edge was not established");
        }

        Class<?> type = Class.forName(
                "demo.target.internal.SecretBox",
                false,
                ClassLoader.getSystemClassLoader());
        Method method = type.getDeclaredMethod("status");
        method.setAccessible(true);
        System.out.println("reflect=" + method.invoke(null));
    }
}
```

Explanation of key points:

1. The agent uses `ModuleLayer.boot()` because the launch command itself places the `demo.target` module in the boot layer. For another module layer, you must find the module in the exact layer.
2. `ModuleAccessAgent.class.getModule()` returns the module of the code calling reflection. In this layout, that is the unnamed module of the system class loader.
3. `getPackages().contains(pkg)` confirms the package is present in the target module; this avoids a package key error for a package not belonging to the module.
4. `isModifiableModule` is queried **before** modifying relationships. On a JVM that does not support it, the agent prints `module update=skipped` and does not attempt `redefineModule`.
5. `extraReads`, `extraExports`, `extraUses`, and `extraProvides` are empty collections. **Only** `extraOpens` has one package and one receiving module.
6. `isOpen(pkg, agentModule)` is the actual postcondition check on the runtime module graph.
7. `Class.forName(...)` can find the class definition, but calling `setAccessible(true)` to access a private method still requires an appropriate open package. Without opening the package, deep reflection from another module is typically rejected with `InaccessibleObjectException`.
8. `method.invoke(null)` is valid because `status()` is static. `"READY"` is a deterministic result independent of time or randomness.

**File `agent.mf`** (the manifest ends with a newline; keep the trailing blank line if possible):

```text
Manifest-Version: 1.0
Premain-Class: ModuleAccessAgent

```

### 6.2. Compile and package

From the `module-open-demo` root directory, example **PowerShell** commands:

```powershell
New-Item -ItemType Directory -Force -Path out/modules, out/agent |
    Out-Null

javac --module-source-path src -d out/modules -m demo.target
javac -encoding UTF-8 -d out/agent agent-src/ModuleAccessAgent.java

jar --create --file out/module-access-agent.jar --manifest agent.mf `
    -C out/agent .
```

If running from Bash, use the equivalent commands:

```bash
mkdir -p out/modules out/agent
javac --module-source-path src -d out/modules -m demo.target
javac -encoding UTF-8 -d out/agent agent-src/ModuleAccessAgent.java
jar --create --file out/module-access-agent.jar --manifest agent.mf \
    -C out/agent .
```

The commands produce:

- `out/modules/demo.target/` containing the compiled module, including `module-info.class`.
- `out/agent/` containing the agent class outside any named module.
- `out/module-access-agent.jar` with `Premain-Class` for `-javaagent`.

Run with **JDK 17+** including `java.instrument`:

```bash
java -javaagent:out/module-access-agent.jar \
    --module-path out/modules \
    --module demo.target/demo.target.Main
```

In **PowerShell**, replace the line continuation `\` with a backtick, or run on a single line:

```powershell
java -javaagent:out/module-access-agent.jar --module-path out/modules --module demo.target/demo.target.Main
```

### 6.3. Output on HotSpot/OpenJDK supporting module redefinition

With `module-info.java` as above and no `--add-opens` on the command line, expected stdout:

```text
target named=true
agent unnamed=true
modifiable=true
open before=false
open after=true
reflect=READY
app=running
```

If the current JVM reports `modifiable=false`, the agent proactively prints `module update=skipped` and the application can still enter `main`; do not treat this as a bug in `isModifiableModule`. If the package is already open due to startup configuration, `open before=true` and the agent does not need to call `redefineModule`, while `open after` is still true.

**Conclusion of the experiment:** Opening `demo.target.internal` to the module where the agent runs allows the agent to use deep reflection on a private method. The relationship is changed **at runtime**, without editing `module-info.java`, without changing `SecretBox`'s bytecode, and without automatically opening the package to all named modules.

## 7. Control Experiments and Postcondition Checks

To see clearly that the conditions are meaningful, modify **a local copy of the experiment** and recompile/rerun for each case.

### Case A — module does not contain the requested package

If you change `pkg` in the agent to `demo.target.missing`, the step:

```java
target.getPackages().contains(pkg)
```

returns false and the agent throws `IllegalStateException` due to the guard before calling the API. If you remove the guard and pass a package not belonging to the module into the `extraOpens` map, the API can throw `IllegalArgumentException`. **Do not** remove the guard when writing a real agent.

### Case B — package is already open

Try running with a runtime configuration that already opens the exact package:

```bash
java --add-opens demo.target/demo.target.internal=ALL-UNNAMED \
    -javaagent:out/module-access-agent.jar \
    --module-path out/modules \
    --module demo.target/demo.target.Main
```

In the demo, `open before` can be true because `--add-opens` already granted the corresponding permission. The agent checks and does not request opening it again. Note that `ALL-UNNAMED` opens to **unnamed modules** per launcher policy, which is broader than a single separate named helper module. Only use it in controlled tests.

### Case C — changing the recipient to the wrong module

Suppose the agent opens the package to another module, while the reflection code still runs in `ModuleAccessAgent` (the unnamed module). The other module having permission does not mean the agent has permission: `isOpen(pkg, agentModule)` can still be false, and `setAccessible(true)` will be rejected. You must check **the exact module containing the reflection code**, not just whether any `opens` entry exists.

### Case D — named vs unnamed source module

If the target class is only on the class path, `targetClass.getModule().isNamed()` is false. `isModifiableModule(target)` still returns true per the JDK API, while `redefineModule(target, ...)` creates no additional relationships. Therefore, the `target.isNamed()` guard prevents falsely reporting that a package was actually opened.

### Case E — adding `reads` without `exports`

Module A is given `extraReads=Set.of(B)`, but the needed package in B is not exported to A. Code in A can still encounter an access error when using a public type from B because the read relationship and the export relationship are two separate conditions. Verify the **permission direction** of both; do not blindly add `opens` to B as a substitute for understanding the error.

## 8. Bounded Modification Mechanism and No "Undo" Step

`redefineModule` is **additive**: you can add, but you cannot revoke a read edge, export, open, or service declaration through that API. If an agent accidentally opens a sensitive package to an inappropriate module, there is no "remove" argument to undo it within the same JVM. In practice, restoring the original module graph state usually requires **restarting the JVM** with the corrected configuration/agent.

Distinguish clearly:

```text
isModifiableModule(module) → Can redefineModule be used for this module?
redefineModule(module, ...) → Add module relationships at runtime
isModifiableClass(clazz)   → Can this class have its definition modified/bytecode transformed?
retransformClasses(clazz)  → Attempt to transform bytecode of a loaded class
```

A module can be modifiable while some of its classes are not modifiable. Similarly, a successful `redefineModule` **does not confirm** that a bytecode transformer is active and does not cause a method to be instrumented automatically. These are independent capabilities and paths that must be checked according to your purpose.

The fact that `Instrumentation.redefineModule` supports concurrent calls so multiple agents can update the same module **does not mean** the whole system is guaranteed to be logically correct when multiple agents modify permissions together. Each agent should grant only the minimum required permissions, avoid treating stale snapshots as immutable facts, and check postconditions.

## 9. Common Errors and Causes

| Symptom | Explanation / How to Handle |
| --- | --- |
| `isModifiableModule(target)` returns `false` | The JVM does not allow modifying that module; stop the modification and consider startup configuration or an alternative design |
| `isModifiableModule(null)` throws `NullPointerException` | The module was not validly resolved; check the source and layer first |
| Returns `true` for an unnamed module with no change | Expected per API: `redefineModule` on an unnamed module is a no-op |
| `UnmodifiableModuleException` | `redefineModule` was called on a module the JVM does not allow modifying; do not ignore the error |
| `IllegalArgumentException` from `extraExports`/`extraOpens` | Key is not a package belonging to the source module, or a target set in the map is empty |
| `IllegalArgumentException` from `extraProvides` | Provider does not belong to the source module, does not implement the service type, or the list is empty |
| `NullPointerException` from `redefineModule` | An argument or a collection key/value element is `null` |
| `InaccessibleObjectException` during `setAccessible` | The package is not opened to the module **of the reflection code**; check `isOpen(pkg, requesterModule)` |
| `IllegalAccessError` when calling a public helper | Usually related to read/export relationships or visibility between modules; verify `canRead` and `isExported` in the same direction |
| `ClassNotFoundException` | The class is not in the right module graph/class loader; `redefineModule` does not create classes or fix the class path |
| `isOpen` is true but reflection still fails | Possibly selected the wrong `Class`/module/layer, wrong signature/method, or another access condition applies; inspect the stack trace and specific exception type |
| Agent operating in the wrong layer | Module name matches, but the `Module` object is not the target; obtain it from `targetClass.getModule()` when you have the class to instrument |

Errors are not always caused by the module graph. OS permissions, class loaders, method signatures, runtime policies, and agent loading failures can cause errors elsewhere. Do not automatically open all of `java.base` or use `ALL-UNNAMED` across many packages just because you hit a first exception.

## 10. Checklist Before Deploying on a Real JVM

1. **Right target:** identify the exact JVM, class loader, module layer, and `Module` of the class to observe.
2. **Right module kind:** know whether the source is named or unnamed; do not treat unnamed `true` as an effective modification.
3. **Modifiability:** call `isModifiableModule` and handle `false`; do not confuse it with class retransformation.
4. **Specific reason:** determine whether you genuinely need to add any read, export, open, or service declaration.
5. **Minimal scope:** only open/export existing packages, and only to the receiving modules actually needed; understand the scope of an unnamed module.
6. **Valid data:** no nulls, no empty collection values in entries where disallowed; valid provider classes.
7. **No over-privileged grants:** if only public API access is needed, do not casually open private reflection; if no module change is needed, leave it untouched.
8. **Error handling:** account for `UnmodifiableModuleException`, `IllegalArgumentException`, `NullPointerException`, and access errors at runtime.
9. **Post-call verification:** use `canRead`, `isExported`, and `isOpen` in the right direction and test the minimal required operation.
10. **Lifecycle assessment:** added relationships have no rollback mechanism via `redefineModule`; have a restart/redeploy plan if a mistake is made.
11. **Real-tool testing:** after opening the module, still verify that bytecode is instrumented properly, logging/tracing overhead is acceptable, no data leaks occur, and everything works on the target JDK.
12. **Change management:** document why the agent needs the permissions, which module grants access to whom, and how to detect unexpectedly broad permission configurations.

## 11. Self-Check Questions

**Question 1.** `isModifiableModule` returns `true`. Can you immediately call `redefineModule` with any package?  
**Answer:** No. Packages for `extraExports`/`extraOpens` must belong to the source module, value sets must be valid, arguments must not be null, and permissions must target the right recipient.

**Question 2.** What does `isModifiableModule` return for an unnamed module?  
**Answer:** Always `true`, but `redefineModule` on an unnamed module is a no-op.

**Question 3.** Module `app` needs to call a public helper in `helper`. Is adding `reads` alone enough?  
**Answer:** Not necessarily. The direction `app → helper` needs a read edge, and the package containing the public helper must also be exported/accessible to `app` under JPMS.

**Question 4.** You need to call a private method of `app.internal` via reflection in the agent. Should you add `exports` or `opens`?  
**Answer:** You should check and, if needed, add a **qualified `opens`** from `app.internal` to **the module containing the reflection code**; `exports` does not automatically grant deep reflection to private members.

**Question 5.** Why can't you pass `Map.of("com.example.*", Set.of(agentModule))` to `extraOpens`?  
**Answer:** The key must be **an actual full package name** in the source module; wildcards are not supported.

**Question 6.** Can `redefineModule` remove an `opens` edge that was already added?  
**Answer:** No. The API only extends relationships, so reverting to the initial configuration usually means restarting the JVM.

**Question 7.** If `isModifiableClass(SomeClass.class) == false`, can you conclude that the module containing the class is not modifiable?  
**Answer:** No. The two checks query two different capabilities.

**Question 8.** Why does the demo check `target.isOpen(pkg, agentModule)` after the call?  
**Answer:** That is the actual runtime postcondition: the right package was opened to the right receiving module. `redefineModule` does not guarantee that remaining assumptions about class loaders or methods are automatically valid.

## Official References

- [JDK 21 — `Instrumentation.isModifiableModule` and `redefineModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): signatures, exceptions, additive behavior, and unnamed-module no-op.
- [JDK 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isNamed`, `getPackages`, `canRead`, `isExported`, `isOpen`, and runtime relationship checks.
- [JDK 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): creating agents, `premain`/`agentmain`, and support for instrumenting code in named modules.
- [JDK 21 — `UnmodifiableModuleException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): error when a module cannot be modified.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): module graph goals and strong encapsulation.

**Key takeaway:** `isModifiableModule` is a **capability gate**, not a license to modify everything. Only call `redefineModule` after confirming the right source module, right relationship direction, valid packages/services, and minimal permission scope; then verify the result with the `Module` API. Changing the module graph does not automatically change bytecode and cannot be reversed by another `redefineModule` call.
