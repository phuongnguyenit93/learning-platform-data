# How does JPMS change the type observability and access model?

## 1. From ClassLoader and classpath to the module graph

The **Java Platform Module System (JPMS)** was introduced in Java 9 (JEP 261). It does not replace ClassLoader, but adds a layer for describing dependencies and encapsulation at the **module** level. For a program running on the traditional classpath, using a type mainly depends on the loader's ability to find the class and the `public`, `protected`, package-private, and `private` access levels. With **named modules**, there are also the constraints of **module observability, resolution, readability, exports, and opens**.

A `public` class in a JAR is no longer by default an API accessible from every other module. **It is possible to find a `Class<?>` and still not be permitted to use a method of that class.**

Conceptual example:

```text
module school.app
    │ requires
    ▼
module school.library
    ├── exports school.library.api
    │      └── public class PublicApi    → normal access
    └── school.library.internal
           └── public class Secret       → not exported, encapsulated
```

The classes may both be defined by the JVM, but only the exported package becomes public API for a module reading the library. A package opened with `opens` also serves **deep reflection**, a mechanism distinct from `exports`.

This article explains precisely **how JPMS changes the type observability and access model**, how it combines ClassLoader and ModuleLayer, and common error scenarios on Java 17+.

## 2. Distinguishing four key concepts

| Concept | Key question | Not synonymous with |
|---|---|---|
| **Observable module** | Can the compiler/runtime environment observe this module as a candidate? | The module has joined the runtime graph |
| **Resolved module** | Has the resolver selected the module into the configuration? | Every other module can read it |
| **Readable module** | Does module A have a read edge to module B? | Every package of B is accessible |
| **Accessible type/member** | Do readability, exports/opens, and Java access allow this operation? | The class file can be found by a loader |

Therefore, it is necessary to look at the different steps:

```text
module artifacts / observable modules
                 │
                 ▼
       root modules + resolution
                 │
                 ▼
       resolved module graph
                 │
                 ▼
     readability: A reads B?
                 │
                 ▼
       B exports package to A?
                 │
                 ├── Normal Java access
                 │
                 └── If deep reflection:
                           B opens package to A?
                 │
                 ▼
         actual access rights
```

This is a diagram of the **conditions for using a type**. ClassLoader is still responsible for loading/defining runtime classes, and the JVM may defer resolution of bytecode symbols. The diagram must not be interpreted as steps that the JVM always executes in strict sequential order on every method call.

## 3. Observable and resolved: having a JAR file is not enough

**Observability** is a concept from JLS `7.7.6: a module can be observed by the host system through the environment's compilation units/module artifacts. The Java platform modules and the module artifacts on the module path are important sources.

**Resolution** determines the set of modules that actually belong to the module graph of a build/run. For example:

```bash
java --module-path mods --module school.app/school.app.Main
```

The resolver starts from the root `school.app` and other roots requested by the configuration, then selects the required modules according to `requires`. Even though the `mods` directory contains many artifacts, **not every module placed there is resolved by default**.

To add a root module:

```bash
java --module-path mods --add-modules school.debug --module school.app/school.app.Main
```

This is a syntax example, assuming `school.debug` and `school.app` actually exist. `--add-modules` makes the module an appropriate root, without automatically exporting or opening all of its packages.

Clearly distinguish three errors:
- **Module is not observable:** the path configuration or module name is wrong.
- **Module is observable but not resolved:** it is not part of the selected roots or dependency closure.
- **Module is resolved but not accessible:** there is no read edge or the package is not exported/opened.

When debugging, use `java --show-module-resolution ...` to view the actual resolution, instead of just checking whether there is a JAR file on disk.

## 4. Readability: requiring another module as a dependency

The `module-info.java` descriptor defines dependency relationships:

```java
module school.app {
    requires school.library;
}
```

This creates a read edge from `school.app` to `school.library` in the appropriate module configuration. However, **`requires school.library` does not open every package of the library**.

Example:

```java
module school.library {
    exports school.library.api;
}
```

The app reads the library, so it can use public types belonging to `school.library.api`. The package `school.library.internal` is not exported and is not part of the library's normal API, even when it contains a class declared `public`.

### requires transitive

```java
module school.library {
    requires transitive school.model;
    exports school.library.api;
}
```

When `school.app` reads `school.library`, a read edge to `school.model` is **implied** by `requires transitive`, supporting the case where the library's public API uses public types from the model. However, `requires transitive` does not automatically export packages from either module.

### requires static

`requires static school.optional;` denotes a dependency used at compile time, though the target module may not be needed at runtime according to the resolution rules. Do not confuse this with a Java `static` field/method.

### java.base

Normal named modules read `java.base` according to JPMS rules, so standard types such as `String` and `Object` remain available without explicitly writing `requires java.base;` in every descriptor.

## 5. Exports: exposing API by package

`exports package.name;` provides normal access to other modules that read the current module:

```java
module school.library {
    exports school.library.api;
}
```

When the package is exported and a read edge exists, code outside the module can import the appropriate `public` types and use members that satisfy Java access control.

`exports` must not be interpreted as:
- Automatically making every class in the package `public`.
- Allowing access to private fields/methods via deep reflection.
- Automatically creating a read edge from every other module to this module.
- Exporting all subpackages: the package `school.library.api.internal` is a separate package and is not automatically exported just because `school.library.api` is exported.

### Qualified exports

```java
module school.library {
    exports school.library.api;
    exports school.library.testing to school.testkit;
}
```

Only the `school.testkit` module benefits from the qualified export of `school.library.testing`, alongside the requirement of reading the target module. This is a way to expose a restricted API to testing tools or closely related modules.

Package names and Java access still matter: a package-private class in an exported package does not automatically become public.

## 6. Opens: deep reflection permission at runtime

JPMS distinguishes **normal source/binary access** from **deep reflection**.

- `exports p;`: allows access to appropriate public/protected APIs at compile/runtime.
- `opens p;`: allows deeper reflective access at runtime, making it possible to enable `AccessibleObject.setAccessible(true)` or `trySetAccessible()` for private members when other conditions are met.
- `opens p to framework.module;`: opens only to the listed module.
- `open module m { ... }`: opens packages at runtime via the open module mechanism, while `exports` must still be used for compile-time public APIs.

Example:

```java
module school.library {
    exports school.library.api;
    opens school.library.internal to school.app;
}
```

`school.app` is allowed to reflect into `school.library.internal` under this open policy, **but `opens` alone does not make the app's Java source allowed to `import school.library.internal.Secret`**. Direct import requires an appropriate `exports`.

### Comparison table

| Declaration in module B | A imports public type at compile time | A public reflection at runtime | A private deep reflection |
|---|---|---|---|
| Package not exported/opened | No | Generally no | No |
| `exports p;` | Yes if A reads B | Yes | Not automatically |
| `exports p to A;` | For A | For A | Not automatically |
| `opens p;` | No (not from opens) | Possible per runtime access | Yes |
| `opens p to A;` | No (not from opens) | For A | For A |
| `open module B` | Only packages with exports | Opened packages | Yes per permissions/runtime checks |

A subtle point: `Module.isExported(p, A)` can return `true` **at runtime** after `p` is opened to A, even though `module-info.java` does not have `exports p`. Do not rely on the `isExported` result alone to infer that the compiler permits `import` of that package.

## 7. Complete Java 17+ example: class is found, but access is blocked

Create two named modules:
- `school.library` has an exported API package and a closed internal package.
- `school.app` reads `school.library`.
- The app calls the public API successfully and obtains the `Class<?>` of the internal class by name, but reflective invocation is blocked.

### 7.1. Layout

```text
project/
└── src/
    ├── school.library/
    │   ├── module-info.java
    │   └── school/library/
    │       ├── api/PublicApi.java
    │       └── internal/Secret.java
    └── school.app/
        ├── module-info.java
        └── school/app/Demo.java
```

File `src/school.library/module-info.java`:

```java
module school.library {
    exports school.library.api;
}
```

File `src/school.library/school/library/api/PublicApi.java`:

```java
package school.library.api;

public final class PublicApi {
    private PublicApi() {
    }

    public static String message() {
        return "hello API";
    }
}
```

File `src/school.library/school/library/internal/Secret.java`:

```java
package school.library.internal;

public final class Secret {
    private Secret() {
    }

    public static String reveal() {
        return "secret";
    }

    private static String whisper() {
        return "private";
    }
}
```

File `src/school.app/module-info.java`:

```java
module school.app {
    requires school.library;
}
```

File `src/school.app/school/app/Demo.java`:

```java
package school.app;

import java.lang.reflect.Method;
import school.library.api.PublicApi;

public final class Demo {
    public static void main(String[] args) throws Exception {
        Module app = Demo.class.getModule();
        Module library = PublicApi.class.getModule();

        System.out.println("app module: " + app.getName());
        System.out.println("library module: " + library.getName());
        System.out.println("reads library: " + app.canRead(library));
        System.out.println("api exported: "
                + library.isExported("school.library.api", app));
        System.out.println("internal exported: "
                + library.isExported("school.library.internal", app));
        System.out.println("internal opened: "
                + library.isOpen("school.library.internal", app));
        System.out.println("api message: " + PublicApi.message());

        Class<?> hidden = Class.forName(
                "school.library.internal.Secret");
        System.out.println("found hidden: " + hidden.getName());

        try {
            System.out.println("public reflection: "
                    + hidden.getMethod("reveal").invoke(null));
        } catch (IllegalAccessException expected) {
            System.out.println("public reflection: denied");
        }

        Method privateMethod =
                hidden.getDeclaredMethod("whisper");
        System.out.println("deep reflection enabled: "
                + privateMethod.trySetAccessible());
    }
}
```

### 7.2. Compile and run

Run in the `project` directory with JDK 17+:

```bash
javac --module-source-path src -d mods src/school.library/module-info.java src/school.library/school/library/api/PublicApi.java src/school.library/school/library/internal/Secret.java src/school.app/module-info.java src/school.app/school/app/Demo.java
java --module-path mods --module school.app/school.app.Demo
```

Stdout:

```text
app module: school.app
library module: school.library
reads library: true
api exported: true
internal exported: false
internal opened: false
api message: hello API
found hidden: school.library.internal.Secret
public reflection: denied
deep reflection enabled: false
```

**Points to understand:**

1. Because of `requires school.library`, `app.canRead(library)` is `true`.
2. The API package `school.library.api` is exported: calling `PublicApi.message()` succeeds.
3. `school.library.internal.Secret` is a `public` class, but its package is not exported, so the app cannot import or call it directly.
4. `Class.forName` still finds the internal runtime class; having `Class<?>` **does not by itself prove valid member access**.
5. `Method.invoke` fails with `IllegalAccessException`; the code catches it and prints `public reflection: denied`.
6. `trySetAccessible` on the private method returns `false` because the package is not opened to the app.

The example has been verified to compile and run on JDK 21; the syntax, module access, and APIs are compatible with Java 17+.

### 7.3. What changes if only opens is added?

Edit just the one file `src/school.library/module-info.java` to:

```java
module school.library {
    exports school.library.api;
    opens school.library.internal to school.app;
}
```

Recompile both modules using the `javac` command in section 7.2, then run again. The changed lines become:

```text
internal exported: true
internal opened: true
public reflection: secret
deep reflection enabled: true
```

The remaining lines do not change. `opens` allows runtime reflection by `school.app`. At this point `isExported(internal, app)` also returns `true` because **runtime access** can be granted from `opens`; this does **not** allow compile-time import of a package that is only opened.

This is a direct demonstration of the difference between **class lookup**, **readability**, **exports**, and **opens**.

## 8. Reflection error: IllegalAccessException and InaccessibleObjectException

In reflection code:

```java
// Snippet: type is the Class<?> of another class.
java.lang.reflect.Field field = type.getDeclaredField("value");
field.setAccessible(true);
```

If the target package is not opened to the caller module, `setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException`. Using `trySetAccessible()` typically allows checking via a boolean instead of throwing an exception when access permission cannot be enabled.

Distinguish between:
- `IllegalAccessException`: a reflective method/field/constructor call lacks access permission.
- `InaccessibleObjectException`: a request to relax reflection access via `setAccessible` cannot be satisfied.
- `IllegalAccessError`: a linkage/runtime bytecode access error, different from a checked reflective exception.
- `ClassNotFoundException`: the loader did not find the class; a missing export cannot be concluded from a CNFE alone.

Do not "fix" all of these errors by catching `Throwable` or opening every package. The right approach is to provide an appropriate public API, use targeted `exports`/`opens`, or fix the framework design.

## 9. Java module system flags

| Flag | Function |
|---|---|
| `--module-path` or `-p` | Source of module artifacts for the resolver to search |
| `--add-modules m` | Add a root module during resolution |
| `--add-reads source=target` | Add a read edge |
| `--add-exports source/pkg=target` | Add a qualified export |
| `--add-opens source/pkg=target` | Open a package for runtime deep reflection |
| `--show-module-resolution` | Print resolution details at startup |

Example of rerunning the program from section 7 with package-opening permission from the command line **without changing the descriptor**:

```bash
java --module-path mods --add-opens school.library/school.library.internal=school.app --module school.app/school.app.Demo
```

When a framework is on the classpath (unnamed module), you may encounter the `ALL-UNNAMED` target:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar Main
```

The second command only **illustrates the syntax**, assuming `app.jar` and `Main` actually exist; this is not a recommendation to open JDK packages broadly. Prioritize module descriptors or clear public APIs first, and use narrow-scoped flags for diagnostics/migration.

`--add-opens` does not automatically bring an unresolved module into the graph or make source code able to compile an `import` of the package. `--add-exports` does not automatically grant deep-reflection permission for private members.

## 10. ClassLoader continues to determine the runtime class

JPMS adds `Module` but does not eliminate the **defining ClassLoader** and runtime class identity rules. For a class:

```java
Class<?> type = String.class;
Module module = type.getModule();
ClassLoader loader = type.getClassLoader();

System.out.println(module.getName());
System.out.println(loader);
```

This is a **Java snippet** and needs to be placed inside a method/class. `String` belongs to `java.base`, and the bootstrap defining loader is typically shown as `null`.

Key points:
- A single ClassLoader can define classes of **multiple named modules**; there is no rule that one module must have its own loader.
- Two classes in **two named modules** sharing the same loader do not automatically have package-private access to each other or bypass module access.
- A class can have an initiating loader (the loader receiving the load request) that differs from the loader that defined it.
- Some built-in/module-layer loaders use **direct delegation based on package-to-module mapping**, not necessarily a simple parent-first chain.
- To identify a runtime class, log **`getName()`, `getModule()`, and `getClassLoader()`** together.

Therefore, JPMS combines the **module graph** and the **class loader graph**, rather than replacing one graph with the other.

## 11. ModuleLayer: adding modules dynamically without modifying the boot layer

`ModuleLayer` is a set of runtime named modules defined from a `Configuration` and assigned to class loaders. `ModuleLayer.boot()` represents the layer created when the JVM starts. A plugin application can create a **child layer** to add new modules without modifying the boot layer.

~~~text
Boot layer: java.base, host.api
    |
    +-- Child layer: sample.plugin
          +-- sample.plugin.api.Plugin
~~~

A typical sequence of operations:

1. Use `ModuleFinder.of(...)` to locate artifacts containing modules and read their descriptors.
2. Call `parent.configuration().resolve(finder, ModuleFinder.of(), roots)` to compute the dependency graph of the selected roots.
3. Call `parent.defineModulesWithOneLoader(configuration, parentLoader)` or `defineModulesWithManyLoaders` to create runtime modules bound to a new loader.
4. Use `child.findModule("sample.plugin")` or `child.findLoader("sample.plugin")` to inspect the module and loader; `Class.getModule().getLayer()` indicates the actual layer of a loaded class.

**A layer is not a subclass of `ClassLoader`.** `WithOneLoader` maps all modules of the new configuration to a single loader; `WithManyLoaders` creates one loader per module. Both must comply with module resolution, package ownership, and access rules. Resources, class identity, and plugin lifecycle still require separate design.

If the program only needs to demonstrate that **JPMS blocks access to a class**, the two-named-modules example in section 7 is sufficient. When dynamic loading needs to be implemented, the article on `ModuleLayer.boot`, `ModuleFinder`, and `defineModulesWithOneLoader/ManyLoaders` in this chapter presents standalone experiments, build commands, and loader mapping in greater detail.

## 12. Type identity across modules, loaders, and layers

Two modules with the same name in **two different ModuleLayers** are not necessarily the same runtime Module object. Two classes with the same binary name defined by **two different defining loaders** are two distinct runtime classes, even if they are loaded from two JARs with identical contents.

```text
Layer-A → Loader-A → module example.plugin → example.Plugin
Layer-B → Loader-B → module example.plugin → example.Plugin

Class_A != Class_B when defining loaders differ
```

Consequences:
- Do not cast an implementation object across two classes with the same name just because `getName()` is equal.
- Place the shared API interface in a stable common module/loader if plugins need to communicate with the host.
- The `requires`/`exports` relationship determines readability/access, while type identity still depends on the loader and runtime definition.
- Creating a new layer does not automatically close the old layer or force the JVM to unload classes; that still depends on references, tasks, GC, and loader lifecycle.

## 13. Unnamed modules: the classpath has not disappeared

Code running on the classpath typically belongs to the **unnamed module** associated with its class loader. Key characteristics:

- `Module.isNamed()` returns `false`; `Module.getName()` returns `null`.
- Each ClassLoader has a corresponding unnamed module; the JVM can have multiple unnamed modules.
- The unnamed module reads all runtime modules according to special rules, and exports/opens all of its own packages.
- However, it **does not automatically have access to every unexported/unopened package** in named modules.

Example `UnnamedDemo.java`:

```java
public final class UnnamedDemo {
    public static void main(String[] args) {
        Module module = UnnamedDemo.class.getModule();
        System.out.println("named: " + module.isNamed());
        System.out.println("module name: " + module.getName());
    }
}
```

Run:

```bash
javac UnnamedDemo.java
java -cp . UnnamedDemo
```

Stdout:

```text
named: false
module name: null
```

This helps JPMS support legacy applications, but it also means moving a JAR from the classpath to the module path can significantly change access permissions between libraries.

## 14. Automatic modules and migration strategy

A JAR **without `module-info.class`** placed on the module path can become an **automatic module** when resolved:

- The module name is derived from the manifest `Automatic-Module-Name` or the JAR name.
- It has broad readability rules for compatibility with other modules and legacy code.
- The packages of an automatic module are broadly exported and opened; **it does not provide strong encapsulation like an explicit named module that only exports its API**.
- It provides an easy bridge when part of the dependency graph still consists of legacy libraries.

Example in the main manifest:

```text
Automatic-Module-Name: legacy.network
```

This keeps the module name stable when the JAR moves from the classpath to the module path. However:
- A JAR on the classpath still belongs to an unnamed module.
- An automatic JAR on the module path does not have the permission structure of an explicit descriptor.
- A JAR with `module-info.class` becomes an explicit module according to the corresponding rules.

Do not mistakenly assume that a package named `internal` is protected from external code while the library is still an automatic module.

## 15. ServiceLoader and uses/provides declarations

JPMS provides an SPI model with descriptors:

Consumer module:

```java
module shop.app {
    requires shop.api;
    uses shop.api.PaymentProvider;
}
```

Provider module:

```java
module shop.payment.impl {
    requires shop.api;
    provides shop.api.PaymentProvider
        with shop.payment.impl.DefaultPaymentProvider;
}
```

These are **two illustrative descriptors**, assuming the corresponding interface and implementation exist. The provider's implementation package **does not need to be exported** to the consumer just for `ServiceLoader` to locate and instantiate the provider under the JPMS contract.

Some discovery APIs:
- `ServiceLoader.load(Service.class)` typically uses the Thread Context ClassLoader for loader-based models.
- `ServiceLoader.load(ModuleLayer layer, Service.class)` locates providers in the layer according to the contract.
- `ModuleLayer.findLoader(name)` is useful when the host needs the loader of a plugin module.

TCCL remains useful, but when plugins reside in a child layer, you must determine whether the API/framework uses **TCCL**, an explicit loader, or **ModuleLayer** so that providers are not missed.

## 16. Resource visibility and class access are not the same check

For a named module, the resource APIs:
- `ClassLoader.getResource(...)`
- `Class.getResource(...)`
- `Module.getResourceAsStream(...)`

have their own encapsulation rules, especially for resources belonging to non-opened packages. A file physically existing in a JAR does not automatically guarantee that an arbitrary caller can retrieve the resource through the ClassLoader API.

Conversely, `Class.forName(...)` can find a class in a non-exported package, yet invoking its constructor/methods can be blocked by module access. Therefore, do not use `getResource("...class")` as the sole test for type accessibility.

## 17. JPMS error diagnostic table

| Error/symptom | Cause category | What to check |
|---|---|---|
| `module not found` | Module is not observable/resolved | `--module-path`, module name, root, `requires` |
| `package ... is not visible` at compile time | No readability or not exported | `requires`, `exports` |
| `ClassNotFoundException` | Loader/layer cannot find the class | Module resolution, loader, binary name |
| `IllegalAccessError` | Invalid bytecode member access | Readability, exports, runtime package, ABI |
| `IllegalAccessException` from reflection | Reflective invoke lacks permission | Public access, package exports/opens |
| `InaccessibleObjectException` | Deep reflection blocked by strong encapsulation | `opens` or qualified `--add-opens` |
| `LayerInstantiationException` | Invalid module configuration/layer | Package overlap, split delegation, module rules |
| `ClassCastException` with two identical class names | Different defining ClassLoaders | `getClassLoader` and `getModule` |
| Module exists on disk but `findModule` does not find it | Not part of the queried configuration/layer | Root modules, resolution, parent layer |
| `ServiceLoader` does not find provider | Wrong discovery path/module descriptor | `uses`/`provides`, layer, TCCL |

**Not every error is a loader error.** A class that exists but is blocked by `exports`/`opens` is a **module access** error, different from a missing class file or wrong classpath.

## 18. Practical JPMS debugging workflow

1. Confirm the actual JVM/JDK: `java -version`, `javac -version`.
2. Check whether the artifact is on the **classpath** or **module path**.
3. Read `module-info.java`/`module-info.class` or determine the automatic module name.
4. Determine the module graph: root modules, `requires`, `requires transitive`, resolution logs.
5. Locate the runtime class: `getName()`, `getModule()`, `getClassLoader()`.
6. Check `Module.canRead` for the relationship between caller and target.
7. Check whether the package has `exports` or `opens` for the right module.
8. Check access modifiers and the type of reflection being used.
9. If plugins are involved, determine the `ModuleLayer`, `findLoader`, TCCL, and shared API.
10. If SPI is involved, check `uses`/`provides` and the ServiceLoader overload.
11. Use narrow-scoped `--add-reads`, `--add-exports`, or `--add-opens` for diagnostics; then fix the descriptor/architecture.
12. Run tests on the actual runtime and launch configuration, without assuming from a classpath run that a modular launch will behave identically.

Useful commands:

```bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution --module-path mods --module school.app/school.app.Demo
```

The third line assumes the example modules in section 7 have already been built. `java --list-modules` and `--describe-module` display module information in the appropriate runtime; for a JAR, you can inspect the contents of `module-info.class` using the `jar --describe-module` tool.

## 19. Misconceptions to avoid

| Misconception | Reality |
|---|---|
| A JAR on the module path makes all classes immediately usable | Resolution, readability, exports/opens, and Java access are required |
| `requires` automatically exports all packages of the dependency | No; the dependency controls exports |
| A `public` class can always be called from any module | The package containing it may not be exported |
| `exports` allows calling private members via reflection | Deep reflection requires appropriate opens |
| `opens` allows importing the package at compile time | No; exports is required |
| `Class.forName` succeeding means you have permission to invoke | No; class lookup does not check permission for every member |
| Each module has exactly one independent loader | One loader can define multiple named modules |
| A layer is a loader | A layer maps modules to one or more loaders |
| Two classes with the same name in two layers must be the same type | Their defining loaders may differ |
| An automatic module encapsulates its implementation | Automatic modules have a broad access policy |
| The classpath stopped working in Java 9 | The classpath continues via unnamed modules |
| `setAccessible(true)` bypasses all restrictions | Strong encapsulation can deny it |
| `--add-opens` solves every error | It does not fix dependency, resolution, ABI, or missing-class issues |
| The module graph completely replaces the ClassLoader graph | The two mechanisms coexist and interact |

## 20. Self-check questions

1. **Which Java version introduced JPMS?** Java 9.
2. **Are the module path and the resolved graph the same thing?** No; a module can be on the path without being resolved.
3. **If A `requires B`, can it use all public classes of B?** No; B's package exports must be checked.
4. **If B `exports b.api`, does it automatically export `b.api.internal`?** No; that is a different package.
5. **Does `Class.forName` finding an internal class guarantee reflective invocation will work?** No.
6. **What is the main difference between exports and opens?** Exports serves normal API access; opens serves runtime deep reflection.
7. **Does `opens p to A` make it valid for A's source code to import p?** No.
8. **Why can `Module.isExported(p,A)` be true after opens?** The API queries runtime access, and opens can grant a runtime export.
9. **Can a single ClassLoader define multiple named modules?** Yes.
10. **What is `Class.getModule()` for?** Determining the runtime module of a class.
11. **Does creating a child ModuleLayer unload the old layer?** Not automatically.
12. **What kind of module does code on the classpath belong to?** The unnamed module of its corresponding loader.
13. **Does an automatic module have strong encapsulation like an explicit module with restricted exports?** No.
14. **Can a service provider that does not export its implementation package be used by ServiceLoader?** Yes, according to `provides` and the appropriate contract.
15. **If a method triggers `InaccessibleObjectException`, what should be checked?** Whether the package has opens to the caller module.
16. **Are two classes with the same binary name in two different loaders guaranteed to be the same runtime type?** No.
17. **Are readability and class loadability the same?** No.
18. **What must be reviewed when migrating from the classpath to named modules?** Resolution, requires, exports/opens, service descriptors, loaders/layers, and tests.

## Official references

- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS mechanisms, module path, and module resolution.
- [Java Language Specification 17 — Chapter 7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): `7.7` module declarations, `7.7.1` dependences, `7.7.2` exports/opens, `7.7.5` unnamed modules, `7.7.6` module observability.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getClassLoader`.
- [Java SE 17 API — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): `Configuration`, `findModule`, `findLoader`, `defineModulesWithOneLoader`, and `defineModulesWithManyLoaders`.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getModule`, `getClassLoader`, `Class.forName`.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible` and deep reflection.
- [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): `uses`/`provides` and service discovery by module layer.
- [JVMS 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, class loaders, module runtime access.

**Conclusion:** JPMS does more than just give names to JARs. It brings **module observability and resolution**, **read edges**, **exports/opens**, and **ModuleLayer** into the model. ClassLoader still locates/defines classes; JPMS determines which module observes/reads which module and which packages are actually permitted to be accessed. Therefore, when debugging Java 9+, always ask separately: **"Can the class be found/loaded?"** and **"Does the caller code have permission to use that class/member in this way?"**
