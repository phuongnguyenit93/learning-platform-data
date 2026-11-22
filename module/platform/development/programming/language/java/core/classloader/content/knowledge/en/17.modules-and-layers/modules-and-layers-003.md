# Distinguishing Class Discoverability from Class Accessibility

## 1. Two Different Questions: “Found?” and “Allowed to Use?”

In Java, a **class loader** helps the JVM locate or define a class, but that **does not guarantee** that the calling program has permission to use the class or its members. Since Java 9, the module system (JPMS) has made this distinction clearer: **module readability**, **package exports**, **package opens**, and **Java access modifiers** each have their own role.

A typical scenario on Java 17:

- Module `m.library` contains a class `internal.Secret` and a public API `api.PublicApi`.
- Module `m.client` depends on (`requires`) `m.library`.
- `m.client` can find the runtime `Class<?>` of `internal.Secret` via `Class.forName("internal.Secret")`, provided the loader can see the class.
- However, `m.library` **does not export package `internal`**. `m.client` cannot use `internal.Secret` directly as a Java type in source code, even though the class is `public`.
- If package `internal` is also **not open** to `m.client`, an attempt at deep reflection with `setAccessible(true)` is denied.

**Key takeaway:** *The ability to find class bytes or obtain a `Class<?>` is a matter of loading/lookup; permission to access a class/member is a matter of accessibility, the module graph, and reflection policy.*

To analyze an error yourself, separate out at least four questions:

1. Is the class or module **already in the runtime configuration** and visible to the loader?
2. Can the caller's module **read** the module containing the type?
3. How is the package containing the type **exported** or **opened** by the source module to the caller?
4. Does the class/member have an appropriate access modifier (`public`, `protected`, package-private, `private`), and is the operation being used **ordinary access** or **reflection**?

You should not try to fix every `IllegalAccessError` or `InaccessibleObjectException` by switching to a different class loader; conversely, you cannot fix every `ClassNotFoundException` simply by adding `exports`.

## 2. JVM Model: Class Loading ≠ Access Checking

You can visualize two different flows:

```text
A. LOOKUP / LOADING
Name: internal.Secret
       |
       v
Select loader / module layer / class search path
       |
       +-- Not found -> ClassNotFoundException
       |                or NoClassDefFoundError in a VM context
       |
       +-- Found -> runtime Class<?> is returned / linked when needed
                        |
                        v
B. ACCESSIBILITY
Does the caller read the target module? Is the package exported or opened?
Does the class/member have appropriate public/protected/package/private access?
       |
       +-- Permitted -> specific usage succeeds (if there are no other errors)
       |
       +-- Denied -> compile-time error, IllegalAccessError,
                     IllegalAccessException or
                     InaccessibleObjectException depending on context
```

This is an **explanatory diagram**, not a requirement that every JVM execute each step in a fixed order. The JVM is allowed to perform some resolutions earlier or later; `Class.forName` returning successfully also does not mean that every member of the class is accessible.

### Different Checking Layers

| Mechanism | Primary Role | Observable Example |
|---|---|---|
| **ClassLoader / class path / module path** | Locate and define runtime classes, determine identity | `Class.forName`, `ClassLoader.loadClass` |
| **Module resolution & readability** | Determine which named modules are resolved and which module reads which | `module-info.java` with `requires`; `Module.canRead` |
| **Exports** | Allow other modules to access **public types/members** in a package under ordinary rules | `exports api;` or `exports api to m.client;` |
| **Opens** | Allow **deep reflection** into a package according to the specified scope | `opens internal;`, `opens internal to m.client;` |
| **Java language access** | Rules for `public`, `protected`, package-private, `private`; declaring class information | Compiler/access checks |
| **Reflective checks** | Check accessibility for `Method.invoke`, `Constructor.newInstance`, and ability to use `setAccessible` | `IllegalAccessException` / `InaccessibleObjectException` |

An exported package does not make every `private` field public. An open package does not automatically make a source-level reference to `internal.Secret` valid in the client module. And a class loader finding bytecode does not automatically open the package of the module containing that class.

## 3. JPMS: Why Can a Class Be Found Yet Still Inaccessible?

**Lookup, resolution, and access checking are three different stages:**

| Check | Question to Answer | Example Error Symptom |
| --- | --- | --- |
| Module resolution | Has the target module been brought into the runtime graph from roots and `requires`? | Matching module/class not found |
| Readability | Does the caller module read the target module? | Module access error during link/invoke |
| Exports | Does the target package export its public types to the caller? | Import or ordinary access is denied |
| Opens | Is the package open for deep reflection from the caller? | `InaccessibleObjectException` when calling `setAccessible(true)` |
| Java member access | Is the type/member actually public or accessible under language rules? | `IllegalAccessException` or a Java visibility error |

The following descriptor example allows `m.client` to read `m.library` and access the **public** API in package `api`:

~~~java
module m.client {
    requires m.library;
}
~~~

~~~java
module m.library {
    exports api;
    opens internal to m.client;
}
~~~

These are **two separate `module-info.java` files**. `requires` creates a readability edge; `exports api` enables ordinary public access; `opens internal to m.client` only allows deep reflection into package `internal` specifically from module `m.client`. It does not allow Java source in the client to automatically `import internal.Secret` without `exports internal`.

You can observe the runtime graph using `callerModule.canRead(targetModule)`, `targetModule.isExported("api", callerModule)`, and `targetModule.isOpen("internal", callerModule)`, though each individual check **does not on its own verify all** conditions required to invoke a class/member. If a module is merely on the module path without being resolved, you must fix the roots/dependencies before addressing `exports` or `opens`.

Dedicated articles on `Readability, exports and opens` and launcher flags go deeper into `requires transitive`, `requires static`, qualified access, compile/runtime flags, and exceptional cases. Here, the example in Section 4 focuses on demonstrating that a class loader can find a class while the Java access check still denies its use.

## 4. Java 17 Demo: Class Found but Not Accessible

This example builds **two separate named modules**. One module has an exported API package and an internal package that is not exported/opened. The client module uses the valid API and still finds the internal class via `Class.forName`, yet is not permitted to call the internal class's public method via normal reflection.

### 4.1. Directory Structure

```text
src/
  m.library/
    module-info.java
    api/
      PublicApi.java
    internal/
      Secret.java
  m.client/
    module-info.java
    app/
      Main.java
out/
  (directory created during compilation)
```

### 4.2. Library Module

File `src/m.library/module-info.java`:

```java
module m.library {
    exports api;
}
```

File `src/m.library/api/PublicApi.java`:

```java
package api;

public final class PublicApi {
    private PublicApi() {}

    public static String message() {
        return "API is accessible";
    }
}
```

File `src/m.library/internal/Secret.java`:

```java
package internal;

public final class Secret {
    private Secret() {}

    public static String message() {
        return "internal";
    }
}
```

Class `Secret` is `public` and method `message` is `public`, but **package `internal` is not exported/opened** in the module's descriptor. The private constructor in this example does not participate in the static method invocation check.

### 4.3. Client Module

File `src/m.client/module-info.java`:

```java
module m.client {
    requires m.library;
}
```

File `src/m.client/app/Main.java`:

```java
package app;

import api.PublicApi;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(PublicApi.message());

        ClassLoader loader = Main.class.getClassLoader();
        Class<?> secret =
                Class.forName("internal.Secret", false, loader);

        Module clientModule = Main.class.getModule();
        Module libraryModule = secret.getModule();

        System.out.println("Found class: "
                + secret.getName().equals("internal.Secret"));
        System.out.println("Module: " + libraryModule.getName());
        System.out.println("Client reads library: "
                + clientModule.canRead(libraryModule));
        System.out.println("Internal exported: "
                + libraryModule.isExported("internal", clientModule));
        System.out.println("Internal open: "
                + libraryModule.isOpen("internal", clientModule));

        Method publicMethod = secret.getMethod("message");
        try {
            publicMethod.invoke(null);
            System.out.println("Unexpected public invocation success");
        } catch (IllegalAccessException expected) {
            System.out.println("Public reflection denied");
        }

        Method declared = secret.getDeclaredMethod("message");
        try {
            declared.setAccessible(true);
            System.out.println("Unexpected deep reflection success");
        } catch (InaccessibleObjectException expected) {
            System.out.println("Deep reflection denied");
        }
    }
}
```

### 4.4. Compiling and Running

From the directory containing `src`, run with JDK 17:

```bash
javac -d out/m.library \
  src/m.library/module-info.java \
  src/m.library/api/PublicApi.java \
  src/m.library/internal/Secret.java

javac --module-path out -d out/m.client \
  src/m.client/module-info.java \
  src/m.client/app/Main.java

java --module-path out -m m.client/app.Main
```

For Windows PowerShell, use each single-line command:

```powershell
javac -d out/m.library src/m.library/module-info.java src/m.library/api/PublicApi.java src/m.library/internal/Secret.java
javac --module-path out -d out/m.client src/m.client/module-info.java src/m.client/app/Main.java
java --module-path out -m m.client/app.Main
```

Stdout output on JDK 17 with the clean module configuration stated above:

```text
API is accessible
Found class: true
Module: m.library
Client reads library: true
Internal exported: false
Internal open: false
Public reflection denied
Deep reflection denied
```

### 4.5. What Does Each Line Prove?

1. `PublicApi.message()` succeeds because `m.client` **requires** `m.library`, package `api` is **exported**, and both the class and method are public.
2. `Class.forName("internal.Secret", false, loader)` finds the class in the resolved module served by the appropriate loader. It does not prove that `internal` is an exported package.
3. `clientModule.canRead(libraryModule)` is true: there is readability from `requires m.library`.
4. `libraryModule.isExported("internal", clientModule)` is false: there is still **no** ordinary access to a public class in package internal.
5. `libraryModule.isOpen("internal", clientModule)` is false: there is no deep reflection permission under JPMS.
6. `publicMethod.invoke(null)` throws `IllegalAccessException` because although `internal.Secret` is public, its declaring package is not exported to the caller module.
7. `declared.setAccessible(true)` throws `InaccessibleObjectException` because the package is also not open to `m.client`.

**Key point of the example:** `Class<?>` is returned successfully and the module is even **readable**, yet **access is still denied**. Readability and lookup capability do not replace exports/opens.

Note: The three-parameter `Class.forName` overload `(name, initialize, loader)` selects the loader explicitly, and the `false` flag avoids requiring initialization at the call site. If `m.library` resides in a **different loader** or the module is not yet resolved, the example needs to adjust the lookup path; do not infer from this demo that every class in every layer can be found by the caller's loader.

## 5. Illustrating Compile-Time Access: Module Visible, Still Cannot Import internal

If you add to `Main.java`:

```java
import internal.Secret;
```

and then use:

```java
System.out.println(Secret.message());
```

these are **two snippets that intentionally violate module encapsulation**; do not merge them into the complete program from Section 4 when you need it to be runnable.

Inside module `m.client`, `javac` will reject this because package `internal` is declared in `m.library` but **not exported to `m.client`**. The fact that the method is `public` does not fix the package visibility issue.

### Fixing It Properly with exports

If `Secret` is genuinely a public API, modify the module declaration:

```java
module m.library {
    exports api;
    exports internal;
}
```

After recompiling the appropriate modules, `m.client` can reference `internal.Secret` (with `requires m.library` already in place). However, exporting all internal packages is usually **not the design you should choose**: a package named `internal` suggests it is not a stable API.

If only one module needs the API, a qualified export:

```java
exports internal to m.client;
```

can also be used, provided the corresponding module graph/build is set up. You should prefer a clear API package (`api`) rather than exposing an internal package just to fix an error.

## 6. Illustrating Deep Reflection: Using opens with the Right Scope

If the goal is for a serialization library, dependency injection framework, or test framework to read private members, ordinary `exports` may not be enough. In that case, consider **opens**.

In the runtime environment, you can try:

```bash
java --module-path out \
  --add-opens m.library/internal=m.client \
  -m m.client/app.Main
```

The `--add-opens` option opens package `internal` of `m.library` to module `m.client` at runtime. In the Section 4 program, `libraryModule.isOpen("internal", clientModule)` will reflect the opened package permission; `declared.setAccessible(true)` can succeed.

However, **the Section 4 program prints an “Unexpected...” message when `setAccessible` succeeds**, because it was written to verify the *denied* branch under the default configuration. Therefore, do not treat the fixed stdout in Section 4 as the expected result for the `--add-opens` configuration; update the test code to verify success if you want to run a second experiment.

A long-term design variant is adding to `module-info.java`:

```java
module m.library {
    exports api;
    opens internal to m.client;
}
```

This is an **illustrative descriptor**. When compiling the library module separately, the compiler may warn if the target module is not visible during compilation; you should use an appropriate module-aware build. `opens` differs from `exports`: it allows reflective access according to the rules, and **does not grant source-level direct import on its own**.

### Using setAccessible Is Not a “JPMS Bypass Trick”

Before Java 9, many reflection examples called `setAccessible(true)` and expected to access any private member. With strong encapsulation in modern Java, `setAccessible` is checked against module boundaries and can throw `InaccessibleObjectException`.

Related APIs:

- `AccessibleObject.setAccessible(boolean)`: throws an exception if access suppression cannot be enabled.
- `AccessibleObject.trySetAccessible()`: returns `false` if it cannot be enabled, which is useful when you want to check rather than rely on exceptions.
- `Method.invoke` or `Constructor.newInstance`: perform invocation access checks if bypassing them has not been permitted.
- `MethodHandles.Lookup`, `privateLookupIn`: have their own capability/access mechanism; do not treat method handles as a way to bypass opens.

When your library requires deep reflection, ask the owning module to **open the right package to the right consumer**, rather than spreading `--add-opens ...=ALL-UNNAMED` across the entire runtime if unnecessary.

## 7. Exports, opens, and protected/private as a Decision Table

| Scenario | `requires`/readability | `exports` | `opens` | Java modifier |
|---|---|---|---|---|
| Client directly calls `api.PublicApi.message()` | Yes | `api` exported to client | Not needed | Class/method must be accessible, usually `public` |
| Client imports `internal.Secret` normally | Yes | `internal` must be exported to client | Opens alone is **not enough** | Class/method accessible |
| Reflection invokes a public method of a public class in another module | Correct module graph/lookup | Package exported to caller is usually enough for ordinary reflection access | Opens can be used with `setAccessible` when appropriate | Public class/member must be checked |
| Reflection accesses a private field of another module using `setAccessible(true)` | Appropriate module/lookup | Exports is **not enough** | Package usually needs to be open to caller | Private member still requires access suppression |
| Looking up `Class<?>` with `Class.forName` | Loader sees type and module is resolved | Not necessarily | Not necessarily | Does not indicate permission to use members |
| `MethodHandles.privateLookupIn` targeting a class in another module | API access/lookup requirements | Not sufficient on its own | Package must be open to caller per contract | Lookup must have appropriate access rights |

**Precise distinction:**

- `exports` is aimed at **ordinary compile-time/runtime access to public types and members**.
- `opens` is aimed at **runtime deep reflection**.
- `requires` establishes **readability**; simply having a module found by the loader is not enough for ordinary access.
- `public` is a Java access modifier; it does not override module encapsulation.

A `public` class inside an unexported package differs from a package-private class inside an exported package; these two causes of missing access must be fixed in different ways.

## 8. ClassLoader Does Not Enforce the Entire JPMS Graph on Its Own

Sometimes developers try:

```java
ClassLoader targetLoader =
        ClassLoader.getSystemClassLoader();
Class<?> type = targetLoader.loadClass("internal.Secret");
```

If the call finds `Class<?>`, that is **no promise** that any code in any module can call constructors, methods, or access fields of this type.

Similarly, using:

```java
Class.forName("internal.Secret", false, targetLoader);
```

only explicitly selects the loader and initialization behavior. Permission to use the class/member still depends on the caller's module, the type's module, package exports/opens, and Java modifiers.

### ClassLoader Visibility and Module Readability Are Two Independent Dimensions

- **Loader visibility**: can the binary class name be found/defined by the loader or returned through delegation?
- **Module readability**: does the module containing the caller have a JPMS readability relationship to the module containing the type?
- **Exports/opens**: which packages can the consumer access under ordinary or reflection semantics?

A module can be **readable** while its package is not exported; the Section 4 example demonstrates this. A loader may know about a class while code in the caller module is not permitted to use that type in source. Conversely, if the source code has the proper `requires` and `exports` but the runtime is missing the JAR/module or uses the wrong loader, the class still **cannot be found**.

## 9. ModuleLayer and Class Loaders: Do Not Assume Every Class Is in the Application Loader

JPMS allows multiple `ModuleLayer`s; a configuration can resolve modules defined by separate loaders or a designated loader. These two concepts should not be conflated:

- **ModuleLayer** describes the set of modules and their resolution, readability, and service binding relationships within the corresponding configuration.
- **ClassLoader** is the mechanism for loading/defining runtime classes; a layer can use multiple loaders, and a loader can define classes belonging to the appropriate modules.
- **Exports/opens/readability** are relationships between modules, not relationships between two loader objects.

When creating a custom layer, the caller's loader does not necessarily see the new module. You can find the loader used by the layer for a named module:

```java
ClassLoader moduleLoader = layer.findLoader("m.plugin");
Class<?> pluginType =
        Class.forName("plugin.EntryPoint", false, moduleLoader);
```

This is an **illustrative snippet**, requiring a `layer` variable of type `ModuleLayer` that contains module `m.plugin` and ensuring the corresponding class exists. `layer.findLoader` can throw `IllegalArgumentException` if the module does not exist in the layer; successfully finding `Class<?>` does not mean the caller has permission to access the package of `plugin.EntryPoint`.

### Using ModuleLayer.findModule

```java
java.util.Optional<Module> found = layer.findModule("m.plugin");
```

This illustrative snippet serves to locate the module in the layer or its parent layers, but `Optional<Module>` is not a `Class<?>` and does not mean the module's package is exported.

When running multiple plugin versions across multiple layers, you must consider **loader identity, the module graph, exports/opens, and shared API contracts** simultaneously. Isolating class loaders can keep multiple runtime class identities distinct, but a `public` API is not necessarily accessible when modules lack the appropriate readability/export edges.

## 10. Class Path and Named Modules: Why Do Examples Differ?

On the traditional class path, classes reside in the **unnamed module** of their corresponding loader. Code in an unnamed module generally reads all modules; unnamed modules export and open all of their packages under JPMS semantics.

However, Java access modifiers still apply: a package-private class does not become public, and a private field is not automatically accessible from another package. The distinction between *findable* and *accessible* still exists even without using `module-info.java`.

Named modules introduce additional boundaries:

- `requires` / readability
- `exports`
- `opens`
- `ModuleLayer` and module resolution
- Access checks in reflection

Therefore, reflection code that worked on the class path can start throwing `InaccessibleObjectException` when migrated to a named module without opening the appropriate package.

**Do not assume that moving a JAR from the module path back to the class path is always a good fix**. Doing so alters the encapsulation model and can affect dependencies, service resolution, or module names. Understand your API requirements and desired access configuration before changing packaging.

## 11. Distinguishing Common Exceptions and Errors

| Symptom | Common Context | What to Check |
|---|---|---|
| **`ClassNotFoundException`** | `Class.forName` or `ClassLoader.loadClass` cannot find the requested class name | Is the module resolved? Is the loader right? Is the class path/module path right? |
| **`NoClassDefFoundError`** | The VM needs a class during linking/runtime but cannot obtain/define it as expected, or earlier initialization failed | Missing dependency, class initialization cause, loader mapping |
| **`IllegalAccessError`** | VM linking/resolution detects illegal access between runtime types/members | `exports`, visibility, access modifiers, runtime module graph |
| **`IllegalAccessException`** | Reflective invocation, field access, or constructor access is blocked by Java/member/module accessibility | Is the class/member public? Is the package exported? Is access suppression enabled? |
| **`InaccessibleObjectException`** | `setAccessible(true)` cannot enable access suppression | Is the package `opens` to the caller? Is there a module boundary? |
| **javac error “package ... is not visible”** | Client source directly imports an unexported package or unreadable module | `requires`, `exports`, package path |
| **`LayerInstantiationException`** | Defining a new layer fails due to configuration/loader/package constraints | ModuleLayer configuration/loader mapping and package conflicts |
| **`ServiceConfigurationError`** | Provider discovery/instantiation fails under `ServiceLoader` | Provider type identity, module `uses/provides`, loader/resource visibility |

Do not claim that a specific exception has only a single cause: for instance, `IllegalAccessException` can result from a private member or from an unexported JPMS package in a reflective call. Read **message + stack trace + runtime module graph**.

### Three Similar-Looking Errors with Different Fixes

**Case A — class cannot be found:**

```text
ClassNotFoundException: plugin.EntryPoint
```

Check whether the module is resolved, the right `ModuleLayer` loader is used, the class name, the JAR/class path, and dependencies. Adding `exports` will not help if the JVM cannot find the class bytes yet.

**Case B — class is found, but ordinary access is blocked:**

```text
package internal is declared in module m.library,
which does not export it to module m.client
```

This is a classic compile-time scenario: `m.client` already sees the module, but the package is not exported to it. Resolve this by designing an appropriate public API or using a qualified export if intentionally permitted.

**Case C — class is found, but deep reflection is blocked:**

```text
InaccessibleObjectException:
module m.library does not "opens internal" to module m.client
```

Check whether the framework genuinely needs reflection into internals. If so, open the package with the right scope or use an exported public API; switching loaders is not the default solution.

## 12. Checking Access at Runtime with the Module API

You can use standard methods on Java 17:

```java
Module source = someType.getModule();
Module caller = callerType.getModule();

boolean readable = caller.canRead(source);
boolean exported = source.isExported("api", caller);
boolean opened = source.isOpen("internal", caller);
```

This is an **illustrative snippet** requiring `someType` and `callerType` to be validly obtained class tokens. The results describe the runtime module graph, which is useful for diagnostics; it does not replace checking the access modifiers of individual members.

Questions you should record in logs:

1. What is `callerType.getModule().getName()`? Is it an unnamed module (`getName() == null`)?
2. What is `someType.getModule().getName()`? Which layer/loader does the class belong to?
3. Is `caller.canRead(source)` true?
4. Is `source.isExported(packageName, caller)` true?
5. Is `source.isOpen(packageName, caller)` true?
6. Do `someType.getModifiers()` and the method/field modifiers satisfy Java access checks?
7. Does the loader returning the class match the expected module `Class.getModule()`?

**Do not infer the package from a class name by naively splitting on dots when arrays or nested classes are involved**. For normal classes on Java 9+, `Class.getPackageName()` retrieves the appropriate package name; for array types, check the API semantics.

### Observing the Module Graph via the Launcher

Use JVM logging to see which modules are resolved:

```bash
java --show-module-resolution --module-path out -m m.client/app.Main
```

This command typically prints additional module resolution details before the program's output, which is useful for analyzing why a module is present or absent. Do not use this log output as a substitute for checking package `exports`/`opens`.

View a module description:

```bash
java --module-path out --describe-module m.library
```

This information reveals the public module declaration; qualified exports/opens and runtime overrides may require inspecting the launch arguments as well.

## 13. When Are add-exports, add-opens, add-reads Needed?

Launcher options useful in migration, testing, or compatibility:

| Option | Effect | Problem Scope |
|---|---|---|
| `--add-reads m.client=m.library` | Adds a readability edge at runtime | Caller module does not read the target yet |
| `--add-exports m.library/internal=m.client` | Exports package `internal` to the client module | Ordinary/public access at the boundary |
| `--add-opens m.library/internal=m.client` | Opens package `internal` to the client | Deep reflection |
| `--add-modules m.library` | Adds a root module to participate in resolution | Module is on the path but not resolved yet |
| `--module-path out` | Specifies the search path for modules | Module discovery |

**Do not treat these options as synonymous**. `--add-opens` does not automatically solve all compile-time errors; `--add-exports` does not automatically permit private reflection; `--add-reads` does not make a private package public; `--add-modules` does not automatically choose the right class loader for every layer.

For named-module applications, prefer standard declarations in `module-info.java` when the API design allows it. Use runtime options like `--add-opens` for diagnostics, migration, or integrating frameworks that genuinely require them; do not open all internals without considering the encapsulation impact.

### API-level adjustments

`java.lang.Module` also has methods such as `addReads`, `addExports`, and `addOpens`, but they carry **caller/ownership constraints** and are not arbitrary APIs allowing any module to open another module's internals. Do not assume you can call `targetModule.addOpens("internal", callerModule)` from arbitrary host code and always have it succeed.

## 14. Why Can Opening a Package Be Necessary Yet Still Not Enough?

Once code has the appropriate loader and module access, several separate conditions remain:

- **Does the constructor/method exist?** `NoSuchMethodException` and `NoSuchFieldException` can occur even when the package is exported.
- **Is the target object of the right type?** `ClassCastException` involves runtime type identity and is not cured by opens.
- **Does the provider genuinely implement the shared interface?** `ServiceLoader` may reject a provider with the wrong class identity.
- **Does a module/package conflict occur?** Defining a layer and class loader can fail due to package overlap or layer configuration.
- **Does static initialization fail?** The single-parameter `Class.forName(name)` overload requests initialization, which can cause `ExceptionInInitializerError`.
- **Access modifiers still matter.** An exported public class does not allow a private method to be called directly.
- **Other security or runtime policies** can still affect the ability to perform an action after finding the type; loaders and module access are not a comprehensive sandbox system.

Therefore, analyze errors in stages: **module resolved → class findable → caller readable → package exported/open → member accessible → operation successful**. This is a diagnostic checklist, not an immutable internal order of the JVM.

## 15. Common Misconceptions

| Misconception | Correction |
|---|---|
| “If `Class.forName` succeeds, `newInstance`/`invoke` will definitely succeed.” | Lookup does not guarantee access to constructors/methods. |
| “`requires` is enough to use every package of a module.” | Appropriate package `exports` are needed for ordinary access. |
| “Anyone can use a public class in an internal package.” | A named module may not export that package. |
| “`exports` allows reflection into every private field.” | Deep reflection usually requires `opens` to the caller. |
| “`opens` lets code import an internal type at compile time.” | Ordinary source access requires `exports`, not just `opens`. |
| “If a class cannot be loaded, add `--add-opens`.” | Check the class/module lookup path and resolution first. |
| “A ClassLoader seeing a class means the caller module has `canRead`.” | Loader visibility and module readability are two different relationships. |
| “Switching to the TCCL definitely bypasses JPMS.” | TCCL affects the lookup path of APIs that use it; it does not grant module access rights. |
| “Renaming the loader will make the class accessible.” | Loader name is not a JPMS export/open policy. |
| “Every module is defined by the system loader.” | Module layers can use different loaders; use `layer.findLoader` or runtime inspection. |
| “`setAccessible(true)` always works like in Java 8.” | Strong encapsulation may throw `InaccessibleObjectException`. |
| “`IllegalAccessException` means the class does not exist.” | Usually the class/member was already found, but the reflective operation is not permitted. |

## 16. Self-Check Exercises

**Question 1.** Module `m.client` has `requires m.library`, but `m.library`'s `internal` package is not exported. Can the client call `internal.Secret.publicMethod()` directly?

**Answer:** No. Readability exists, but the package is not exported to the caller module; the public modifier on the class/method is not enough.

**Question 2.** `Class.forName("internal.Secret")` finds the class. Does that prove package `internal` is exported?

**Answer:** No. Lookup and accessibility are two different questions.

**Question 3.** Does `exports internal to m.client;` automatically make private fields of `internal.Secret` accessible via `setAccessible(true)` from the client module?

**Answer:** No. Exporting relates to ordinary public access. Deep reflection usually requires `opens internal to m.client;` or valid access granted by the API.

**Question 4.** Only `opens internal to m.client;` is present without an export. Can the client compile `import internal.Secret;`?

**Answer:** Not under ordinary source access. `opens` supports reflective access; it does not replace `exports`.

**Question 5.** Why does the demo program print both `Client reads library: true` and `Internal exported: false` at the same time?

**Answer:** `m.client` has `requires m.library`, so it reads the library; however, `m.library` only exports package `api`, not `internal`. These are two independent properties.

**Question 6.** What does calling `setAccessible(true)` on a member in an unopened package of a named module typically throw?

**Answer:** `InaccessibleObjectException`, when suppressing Java language access checks is not permitted under `AccessibleObject` and JPMS.

**Question 7.** A new module in a child `ModuleLayer` contains class `plugin.EntryPoint`, but the app loader cannot see that name. What should you check?

**Answer:** Whether the module has been resolved in the layer, which loader the layer uses (`layer.findLoader`), and then the module's readability/exports/opens with respect to the caller. Do not merely change `exports`.

**Question 8.** What elements are required for library `m.client` to call `m.library`'s public API via source code?

**Answer:** The module must be resolved and readable; the public API package must be exported to the client; the class/member must be accessible according to Java modifiers; and the class bytes must be findable through the proper loader.

**Question 9.** When should `--add-opens` be used instead of `--add-exports`?

**Answer:** When the requirement is deep reflection (for example, accessing private members from a framework) and the package is not yet open. If the goal is ordinary public access, look at `exports`/`--add-exports` along with readability.

## 17. Summary and Authoritative Sources

**Five core points to remember:**

1. **Findability:** the loader and module configuration determine whether a runtime class can be found.
2. **Readability:** `requires`/the module graph determines which modules a caller module reads.
3. **Exports:** determine ordinary access to a package's public types/members across a module boundary.
4. **Opens:** allow deep reflection into a package within the permitted scope; they do not grant direct import on their own.
5. **Member access:** `public`/`protected`/package-private/`private` and reflective access checks remain in effect in addition to module relationships.

In Java 17, the question to ask after `Class.forName` succeeds is **not just** “did we get a `Class<?>`?”, but also “**in what way is the module containing the caller allowed to use this type/member?**”.

**Official references:**

- [JLS 17 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, qualified exports/opens, and source-level rules.
- [JLS 17 — `6.6 Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): class/member access and package visibility.
- [Java SE 17 — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, and module runtime APIs.
- [Java SE 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getModule`, `getClassLoader`.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`/`trySetAccessible` and module checks.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layers and `findLoader`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module graph, access control, and launcher options.
