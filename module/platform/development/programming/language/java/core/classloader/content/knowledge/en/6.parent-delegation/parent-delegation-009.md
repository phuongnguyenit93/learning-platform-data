# Delegation in a Graph Model and Exceptions with the Module System

When learning `ClassLoader`, we often encounter the **bootstrap ← platform ← application ← custom loader** diagram and the *parent-first* rule: a loader asks its parent first, and only then tries to find the class itself. This diagram is useful, but it **does not describe all delegation paths in Java 9+**, especially when the **Java Platform Module System (JPMS)** and new `ModuleLayer`s are used.

A loader still has **a single parent** according to `getParent()`, but the class lookup process can also have **direct delegation edges to other loaders**, including peer loaders or loaders that are not ancestors in the parent chain. This forms a **delegation graph** rather than just a tree. The JVM and the module system use module/package/exports metadata to determine where to look for a class; built-in loaders also have exceptions for *upgraded modules*.

This lesson belongs to the **Delegation Mechanism** group of Java core – classloader. After this lesson, you should be able to distinguish between the **parent tree**, the **module dependency graph**, and the **class-loading delegation graph**; understand the special mechanism of built-in loaders; run an example of two modules with peer loaders yourself; and know the boundaries regarding type identity, access permissions, deadlocks, and module layers.

## 1. The conventional model: parent-first tree

In the default mechanism of `ClassLoader.loadClass(String, boolean)`, the class lookup procedure is roughly as follows:

1. Check whether the class name has already been initiated for loading by this loader via `findLoadedClass`.
2. If not, try calling `parent.loadClass(...)`; if the parent is represented by `null`, use the bootstrap mechanism.
3. When the parent does not find it, call `findClass(...)` on the current loader.
4. If the class is found and the `resolve` parameter requests it, link it via `resolveClass(...)`.
5. If none of them find it, throw `ClassNotFoundException`.

A typical parent tree on JDK 17:

```text
[Bootstrap]                    (represented by null)
     ^
     | parent
[Platform]
     ^
     | parent
[Application/System]
     ^
     | parent
[PluginLoader]
```

A **parent edge** is a relationship stored/represented by `ClassLoader.getParent()`. It is **not** information about which loader actually defined a class.

For example, a call to `PluginLoader.loadClass("java.lang.String")` may delegate up to bootstrap to receive `java.lang.String`. `PluginLoader` is the *requesting/initiating loader*, but the **defining loader** of `String` is still represented as `null`:

```java
ClassLoader child = ClassLoader.getSystemClassLoader();
Class<?> type = child.loadClass("java.lang.String");
System.out.println(type == String.class);
System.out.println(type.getClassLoader() == null);
```

This is an **illustrative snippet that needs to be placed inside a method with `throws ClassNotFoundException`**; on a standard Java SE JDK, both lines print `true`. `loadClass` by itself does not require running the static initializer of the found class.

**Limitation of the parent tree:** a loader may know about other loaders through modules, frameworks, or custom policies. `getParent()` only returns **a single parent edge**; it does not promise to list every loader that may be queried during every class load.

## 2. Three types of "graphs" to keep separate

Imagine an application with modules `m.api` and `m.client`. `m.client` reads `m.api`, while each module is assigned to a different class loader.

### 2.1 Parent loader graph

```text
                  [System parent]
                   ^           ^
                   |           |
              [Loader A]   [Loader B]
                 m.api       m.client
```

Both A and B share the same parent. **A is not the parent of B**, and vice versa. This is the graph of parent edges (usually tree-shaped).

### 2.2 Module readability graph

```text
[m.client] --requires/reads--> [m.api]
```

This edge describes **which module reads which module**. The `module-info.java` source can declare `requires m.api;`; after module resolution, the runtime has the corresponding `Module.canRead` relationship. Being able to read a module is not enough to arbitrarily access every package: appropriate `exports` or `opens` must be considered.

### 2.3 Class-loader delegation graph

```text
[Loader B] --finds p.api.Service--> [Loader A]
                 |
                 +-- package p.api belongs to module m.api
                     and is exported/visible to m.client
```

In the loader mechanism of `ModuleLayer.defineModulesWithManyLoaders`, loader B can **go directly to A** when the class name is in a package that the module can read and that is appropriately exported. This edge **does not appear in B's `getParent()`**, because A is a peer loader.

Thus:

| Relationship | What does it ask? | Observable API or data |
| --- | --- | --- |
| Parent | Which loader is the parent of the current loader? | `ClassLoader.getParent()` |
| Module readability | Which modules are read by the current module? | `module-info.java`, resolved configuration, `Module.canRead(...)` |
| Module export/open | Which packages are allowed compile/runtime access or reflection? | `exports`, `opens`, `Module.isExported/isOpen` |
| Actual delegation | When loading this class name, whom will the loader ask? | `loadClass` policy + package/module/loader mapping |
| Defining loader | Who defined the returned class? | `Class.getClassLoader()` |

**Do not equate the three graphs.** A `requires` edge is module metadata, not automatically a `getParent()` link. A delegation edge allows asking a loader to find a class, but does not automatically grant Java access permissions beyond module constraints.

## 3. Why does JPMS need a graph-based delegation mechanism?

Before Java 9, the classpath learning model relied primarily on the lookup order along the parent chain and `findClass`. Since Java 9, **named modules** allow binding packages to resolved modules and binding modules to class loaders. For a loader managing multiple modules, finding a class may require knowing precisely:

- Which **package** does the class name belong to?
- Which resolved module does that package belong to?
- Is that module bound to the **current loader or another loader**?
- Is the package **exported** to the requesting module?
- If there is no suitable package/module mapping, should it fall back to the parent/classpath?

Some loaders created by JPMS use **direct delegation**: looking up the module by package and sending the request directly to the loader responsible for that module, instead of forcing a parent-first attempt in every case.

### Two strategies for creating a module layer

| `ModuleLayer` API | How modules map → loaders | Key consequence |
| --- | --- | --- |
| `defineModulesWithOneLoader(cf, parentLoader)` | Modules in the new layer share **one loader** | Modules in the same layer share a loader; can still direct-delegate to loaders of modules in parent layers |
| `defineModulesWithManyLoaders(cf, parentLoader)` | **Each module** in the new layer has its own loader | The loader of module B can direct-delegate to the loader of module A within the same layer if an appropriate relationship exists |
| `defineModules(cf, moduleNameToLoader)` | Caller provides a module → loader mapping function | For advanced strategies; the caller is responsible for managing loaders and validity conditions |

**Parent layer** and **parent class loader** are two different concepts. `ModuleLayer.boot()` can be the parent layer of a new layer; `ClassLoader.getSystemClassLoader()` can be the parent of the new loaders. This does not make two peer loaders parent–child by nature.

When choosing `defineModulesWithManyLoaders`, having **one loader per module** is a characteristic of the API; it does not mean every named module in the JVM always has its own loader. The boot layer may assign multiple modules to the same bootstrap/platform/application loader.

### Direct delegation flow by package

```text
Loader B needs p.api.Service
        |
        v
Package = p.api
        |
        v
Look up resolved module/package in the layer
        |
        +-- p.api belongs to m.api, exported to m.client
        |            |
        |            v
        |       Send request directly to Loader A
        |            |
        |            v
        |       Return the same Class<?> definition from Loader A
        |
        +-- No mapping to a suitable module
                     |
                     v
            Try parent loader per API contract
```

The diagram describes the mechanism of JPMS loaders created by the methods above. This is **not** a mandatory algorithm for every custom `ClassLoader`; custom loaders may apply different policies and must take responsibility for compatibility themselves.

## 4. Runnable Java 17+ example: two peer loaders, one direct delegation edge

We will create two named modules:

- **`m.alpha`** contains `p.alpha.Greeter` and exports package `p.alpha`.
- **`m.beta`** declares `requires m.alpha;`, and contains `p.beta.UseAlpha` which uses `Greeter`.
- A `Launcher` program on the classpath will resolve the two modules and then use `defineModulesWithManyLoaders` to create one loader per module. Both loaders share the system loader as their parent.

### 4.1 Directory structure

```text
project/
├── src/
│   ├── m.alpha/
│   │   ├── module-info.java
│   │   └── p/alpha/Greeter.java
│   └── m.beta/
│       ├── module-info.java
│       └── p/beta/UseAlpha.java
└── Launcher.java
```

Create all the directories above; run the `javac` commands below from the `project/` directory.

### 4.2 Contents of module `m.alpha`

File `src/m.alpha/module-info.java`:

```java
module m.alpha {
    exports p.alpha;
}
```

File `src/m.alpha/p/alpha/Greeter.java`:

```java
package p.alpha;

public class Greeter {
    public static String message() {
        return "Hello from alpha";
    }
}
```

`exports p.alpha;` allows another module that reads `m.alpha` to access the public API of this package subject to module system rules.

### 4.3 Contents of module `m.beta`

File `src/m.beta/module-info.java`:

```java
module m.beta {
    requires m.alpha;
    exports p.beta;
}
```

File `src/m.beta/p/beta/UseAlpha.java`:

```java
package p.beta;

public class UseAlpha {
    public static String call() {
        return p.alpha.Greeter.message();
    }
}
```

`requires m.alpha;` makes module `m.beta` read `m.alpha`. `exports p.beta;` allows `Launcher` to invoke the public method via valid reflection from the unnamed module, once the class is found.

### 4.4 Program creating a new module layer

File `Launcher.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Launcher {
    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration cf = ModuleLayer.boot()
                .configuration()
                .resolve(finder, ModuleFinder.of(), Set.of("m.beta"));

        ModuleLayer layer = ModuleLayer.boot()
                .defineModulesWithManyLoaders(
                        cf, ClassLoader.getSystemClassLoader());

        ClassLoader a = layer.findLoader("m.alpha");
        ClassLoader b = layer.findLoader("m.beta");

        System.out.println("different loaders: " + (a != b));
        System.out.println("same parent: "
                + (a.getParent() == b.getParent()));
        System.out.println("peer is not parent: "
                + (b.getParent() != a));

        Class<?> viaB = b.loadClass("p.alpha.Greeter");
        System.out.println("B can load A: "
                + (viaB == a.loadClass("p.alpha.Greeter")));

        Class<?> use = b.loadClass("p.beta.UseAlpha");
        System.out.println("call: "
                + use.getMethod("call").invoke(null));

        try {
            a.loadClass("p.beta.UseAlpha");
            System.out.println("reverse: found");
        } catch (ClassNotFoundException expected) {
            System.out.println("reverse: not found");
        }
    }
}
```

Key points to note:

- `ModuleFinder.of(Path.of("mods"))` retrieves compiled modules from the `mods` directory.
- `resolve(... Set.of("m.beta"))` also resolves `m.alpha` because `m.beta` requires that module.
- `defineModulesWithManyLoaders` creates a separate loader for each module and sets the same system loader as their parent.
- `layer.findLoader(name)` retrieves the loader assigned to the module in the layer.
- `b.loadClass("p.alpha.Greeter")` finds the class defined by loader A even though A is **not** the parent of B.
- `a.loadClass("p.beta.UseAlpha")` has no valid reverse edge in this example. Nor does the parent system loader contain the two modules that were only introduced into this layer.

### 4.5 Compiling and running

Requires **JDK 17 or higher**. From `project/`:

```bash
javac --release 17 -d mods --module-source-path src -m m.alpha,m.beta
javac --release 17 Launcher.java
java -cp . Launcher
```

This example was verified with `javac --release 17` and run on Java 17–compatible JDK 21. Exact stdout:

```text
different loaders: true
same parent: true
peer is not parent: true
B can load A: true
call: Hello from alpha
reverse: not found
```

**Why is this proof of a delegation graph?**

`same parent: true` proves A and B share the same parent. `peer is not parent: true` confirms A is not the parent of B. Yet `B can load A: true` still occurs: loader B finds `p.alpha.Greeter` via **direct delegation** based on package/module and exports, receiving the exact `Class<?>` defined by A.

This edge is directed: `m.beta` reads `m.alpha` and the API module is exported to B; conversely, `m.alpha` has no corresponding read/export relationship for B to become a class source for A. Therefore, `reverse: not found` is the expected result in this example.

**Note when reproducing:** do not simultaneously put `mods` on `java`'s `--module-path` and resolve them in `Launcher` if your goal is to observe modules defined by the new layer. The run command places only `Launcher` on the classpath to avoid mixing the boot layer with the custom layer.

## 5. Special behavior of built-in loaders: platform can delegate to application

Java SE 17 explicitly documents an important exception to the parent tree:

> When a module is upgraded or overridden under the module system, the platform class loader may need to delegate to another loader, such as the application class loader, even though the application loader is **not an ancestor** of the platform loader.

This relates to the case of an **upgraded module** defined to the platform loader that reads modules defined to another loader. To satisfy those package/module references, the platform loader may query the loader responsible for the target module **directly**, rather than only walking up the parent chain.

Conceptual diagram:

```text
        [Bootstrap]
             ^
             | parent
        [Platform] -----------------+
             ^                      |
             | parent               | can direct-delegate
        [Application] <-------------+
        
      Parent edge: Application → Platform → Bootstrap
      Extra lookup edge: Platform → Application (when required by modules)
```

In the diagram, parent arrows point upward and the exception edge is explicitly labeled. The platform → application path **is not a new parent**, does not turn the default loader hierarchy into a parent cycle, and **does not mean** platform always sees every class on the application classpath.

**Key takeaways:**

1. `ClassLoader.getPlatformClassLoader().getParent()` does not change just because there is a delegation edge to app.
2. This edge appears **on demand for specific modules/packages**, notably in the case of upgraded modules; it is not a policy of "platform falls back to every application class".
3. Java SE 17 behavior at the API level permits/explains this mechanism. Specific runtime package mapping and checking details may vary across versions/implementations.
4. Parent-first remains the default model recommended by `ClassLoader` for ordinary custom loaders, but **built-in loaders serving JPMS** may operate under their own rules.

Do not fabricate a claim that "platform can always load class `com.myapp.X`" on a normal JDK. Demonstrating the actual exception requires an appropriate upgraded-module / module-read configuration. The `ModuleLayer` example in section 4 provides **runnable** proof of the same direct delegation principle between peer loaders without depending on a specific JDK upgrade configuration.

## 6. How do parent, readability, exports, and opens work together?

A common question: **If B can load `p.alpha.Greeter` from A, can code in B definitely call every member of `Greeter`?**

**No.** The delegation graph only explains how classes are found. Module rules also govern **access permissions**.

| Concept | Function | Example |
| --- | --- | --- |
| `requires m.alpha;` | Module B has a readability relationship to A | `m.beta` uses `m.alpha`'s API |
| `requires transitive m.alpha;` | Readability is propagated to modules that read the declaring module per JPMS rules | An API module re-exports a dependency |
| `exports p.alpha;` | Allows other modules to access qualified public/protected APIs of the package | `UseAlpha` calls `Greeter.message()` |
| `exports p.alpha to m.beta;` | Exports the package only to the named module | Restricts compile/runtime access by module |
| `opens p.alpha;` | Allows deep reflection on the package within the opened scope | Frameworks reflect on private members when needed |
| `opens p.alpha to m.beta;` | Opens deep reflection only to the specified module | Restricts reflection permissions |
| `Module.canRead(...)` | Inspects runtime readability between modules | Debugging readability |
| `Module.isExported(...)` / `isOpen(...)` | Inspects runtime export/open permissions | Debugging access/encapsulation |

`requires` does not mean packages are automatically exported. `exports` does not mean every module automatically reads the source module. `opens` is primarily for deep reflection; it does not turn a private method into a public method that can be called directly from Java source code.

An `IllegalAccessError` or `InaccessibleObjectException` can occur **after the class has already been found**. Do not try to fix it by changing the parent loader when the root cause lies in `exports`/`opens` or Java access permissions.

### Connection from the module graph to the class-loader graph

In module-layer loaders, **exported packages and module relationships** are used to determine direct-delegation routes. However, **not every `requires` edge becomes a parent edge**, and **not every kind of class lookup repeats the Java compiler's module-reading algorithm**.

In particular, when a loader API directly receives an external binary class name, the loader's package/module mapping mechanism may serve as the cue to locate the class; checking whether that class can be **used** from code in a specific module is a different question from obtaining a `Class<?>` via an API.

## 7. What architectures can `ModuleLayer` create?

### 7.1 One loader holding multiple modules

`defineModulesWithOneLoader` assigns all modules in the new layer to **a single loader**. This lets the modules share one loader namespace, but **does not merge the modules into a single module**. `requires`, `exports`, and `opens` relationships still apply.

If two modules in the same layer declare **overlapping packages** when using one loader, layer creation can fail with `LayerInstantiationException`. This rule prevents a situation where one package resides in multiple named modules in the same loader without a clear owner.

### 7.2 One loader per module

`defineModulesWithManyLoaders` creates one loader for each module, with the specified `parentLoader`. Those loaders can be **siblings** while using direct delegation based on package exports to satisfy module readability. The runnable example in section 4 illustrates this case.

### 7.3 Module → custom loader mapping function

`defineModules` lets you pass a function that determines the corresponding loader. This is an advanced scope for container/plugin engines that need namespace control. You must ensure every module/package has a valid loader, no package conflicts occur, and no uncontrolled delegation routes are introduced.

### 7.4 Multiple parent layers

The static `ModuleLayer` API accepts a list of parent layers, and `Configuration` has corresponding parent relationships. A module in a child layer can read a module in one of the appropriate parent layers. **Layer parent relationships** are resolution relationships between layers; they do not necessarily match `ClassLoader.getParent()` on individual loaders.

`ModuleLayer.findLoader(name)` helps retrieve the loader bound to a module in the layer. `ModuleLayer.findModule(name)` can search parent layers as well. A loader does not "become a child of every loader in every parent layer"; direct delegation to the right module depends on runtime routing.

## 8. Boundaries of the delegation graph

### 8.1 Class lookup paths are directed

If B asks A, it does not follow that A can ask B. Asymmetry helps bound dependencies. For instance, `m.beta requires m.alpha` does not automatically create a reverse edge.

### 8.2 Class name alone does not guarantee type identity

The JVM identifies a class/interface by the pair **binary name + defining loader**. If A and B each define their own `p.api.Contract`, those are two different types even if the name and bytecode are identical. The goal of proper direct delegation is for the consumer to **receive the same `Class` object** defined by the loader that owns the module.

If a plugin object cannot be cast to a host interface, check:

```java
System.out.println(object.getClass().getName());
System.out.println(object.getClass().getClassLoader());
System.out.println(object.getClass().getModule());
```

This is an **illustrative snippet inside a method**, where `object` is the instance under investigation. Also print the class loader of the expected interface and compare `Class<?>` identity, not just names.

### 8.3 Not every graph is safe

A custom loader can override `loadClass` and create an edge to any arbitrary loader. If designed as A → B and B → A, missing caching/checks and unsafe lock ordering can cause lookup cycles or deadlocks. Only add edges when there are clear constraints on packages, ownership, and cycle prevention.

### 8.4 Does not replace a security boundary

JPMS restricts readability and package accessibility; class loader isolation restricts which types are defined/visible. Neither is a **complete sandbox environment** for executing untrusted bytecode. Do not rely on "parent = null" or "plugin has its own loader" as the sole security solution.

### 8.5 Resource lookup has different rules

`getResource` and `getResources` also have delegation mechanisms and are subject to named-module encapsulation rules. Some `ModuleLayer` APIs specify searching resources in the layer's modules before the parent; resources located in packages that are not openly `opens` may be hidden. Therefore, "class B can be found from loader A" does not imply every resource `p/alpha/config.properties` can be looked up through B.

## 9. Multithreading: why ClassLoader documentation mentions parallel capable

The `ClassLoader` Javadoc warns that when delegation is **not strictly hierarchical**, class loaders need to support **parallel-capable loading** to avoid deadlocks caused by holding a lock on one loader while requesting another loader.

In the classic mechanism, `loadClass` could be synchronized on a single lock on the loader. If:

```text
Thread 1: holds lock on Loader A → waits for Loader B
Thread 2: holds lock on Loader B → waits for Loader A
```

then the two threads can stall waiting for each other. When a loader is **parallel capable**, synchronization can be based on `getClassLoadingLock(name)` per class name, helping avoid locking the entire loader in some situations. However, parallel capable **does not prove every cyclic graph is safe**: deadlocks can still occur if routing/locking is designed incorrectly.

A custom subclass intending to participate in a delegation graph must understand `registerAsParallelCapable`. Registration must be called during class initialization of the subclass, and the conditions on superclasses in the class loader hierarchy must also match. Do not call that method arbitrarily inside every `loadClass` or treat it as a switch that cures all deadlocks.

This is why module system loaders have specialized routing and synchronization mechanisms. At the application level, prefer the standardized `ModuleLayer` API instead of manually creating multiple `loadClass` overrides with cross-references between them.

## 10. A way to inspect the graph using runtime data

When an issue involves class loaders, you can inspect three layers of information:

**A. Parent chain**

```java
static void printParents(ClassLoader loader) {
    while (loader != null) {
        System.out.println(loader);
        loader = loader.getParent();
    }
    System.out.println("bootstrap (null)");
}
```

This is an **illustrative method**; add it to a class before calling it. The parent chain only answers "whose parent is whom"; it **does not represent direct delegation edges** such as B → A in the example.

**B. Module and defining loader of the actual class**

```java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    System.out.println("class=" + type.getName());
    System.out.println("module=" + module.getName());
    System.out.println("loader=" + type.getClassLoader());
}
```

`module.getName()` can be `null` for an unnamed module; `getClassLoader()` is `null` for bootstrap classes. Print the loader both **at the source of the request and on the resulting class** to distinguish initiating from defining loaders.

**C. Resolved module graph**

```java
Module client = layer.findModule("m.beta").orElseThrow();
Module api = layer.findModule("m.alpha").orElseThrow();

System.out.println("reads: " + client.canRead(api));
System.out.println("exports: " + api.isExported("p.alpha", client));
System.out.println("different loaders: "
        + (layer.findLoader("m.beta") != layer.findLoader("m.alpha")));
```

This is an **illustrative snippet to add to `Launcher.main` from section 4**, after the `layer` variable has been created. In the example, all three lines print `true`. `Module.canRead` and `isExported` prove module-level visibility; the two different loaders prove the classes do not have to reside in the same loader. The direct delegation edge is observed via `b.loadClass(...)` and then comparing `Class<?>` identity.

**D. Class loading logs**

On HotSpot supporting unified logging, try:

```bash
java -Xlog:class+load=info -cp . Launcher
```

Logs can show which source a class was loaded from, but are often quite verbose; the format is not fixed across JVMs. Do not use those logs as the sole proof for the entire graph. If needed, temporarily add logging in a custom `loadClass`/`findClass` to observe the request path, while avoiding logging that triggers recursion.

## 11. Errors and how to diagnose them

| Symptom | Questions to check |
| --- | --- |
| `ClassNotFoundException` when B looks up class A | Which module contains the package? Was the module resolved into the layer? Is there an appropriate export/delegation path? |
| `NoClassDefFoundError` during linking/execution | Is a runtime dependency missing, another linking error, or did a prior initialization fail? Check `cause` |
| `IllegalAccessError` | The class was found, but do Java access permissions / module exports allow the call? |
| `InaccessibleObjectException` during deep reflection | Does the package have appropriate `opens` for the caller? |
| `ClassCastException` between two identical class names | Did two defining loaders define the same name? Is the same API class shared in the right place? |
| `LayerInstantiationException` when creating a module layer | Is there an overlapping package / split delegation / invalid module mapping? |
| Hang at runtime when two loaders cross-load | Is there a delegation/lock cycle and a non-parallel-capable custom loader? |
| `ServiceLoader` does not find a provider | Are module `uses`/`provides`, layer, loader, TCCL, and package exports/visibility configured correctly? |

**Practical workflow:**

1. Collect the class name to load, the caller, and the operation (bytecode, reflection, `Class.forName`, service discovery).
2. Identify the **actual class definition** using `getClassLoader()` and `getModule()`.
3. Retrieve the **parent chain** separately; do not confuse it with the entire delegation graph.
4. For named modules, check the module in the right `ModuleLayer`, `requires`/readability, and `exports`/`opens`.
5. If there are multiple peer loaders, check the **package → module → loader mapping** and the direction of the direct-delegation edge.
6. When names collide, compare `Class<?>` identity and defining loaders; when hangs occur, inspect locks and cross-loading cycles.
7. Fix the dependency/module mapping, shared API architecture, or loader policy, then rerun the same failing call path. Do not use `--add-opens`/`--add-exports` as an arbitrary patch when the real cause is class identity.

## 12. Common misconceptions

| Misconception | Correction |
| --- | --- |
| "Each loader can only ask its parent." | True for the default parent-first algorithm; JPMS loaders and custom loaders can direct-delegate to other loaders. |
| "Two loaders with the same parent cannot see each other's classes." | A module layer can create a package/module edge from B to peer loader A. |
| "`getParent()` lists every edge of the graph." | It only reports the parent; graph edges require checking the loader policy and module mapping. |
| "`requires` makes loader A the parent of B." | `requires` creates module readability; it does not alter the parent structure. |
| "If B loads a class, B defined that class." | B may return a `Class<?>` defined by A or bootstrap. |
| "Platform always delegates to application." | It can only occur under appropriate upgraded-module / module-read conditions; it is not an unconditional fallback path. |
| "Every named module has its own loader." | The boot layer may assign multiple modules to the same built-in loader; new layers are created per the one/many/custom API. |
| "Having readability means private reflection works." | Exports/opens, Java access permissions, and reflection constraints are still required. |
| "A loader graph is safe as long as you override `loadClass`." | There is risk of delegation cycles and deadlocks; proper locking and parallel-capable design are needed. |
| "Class loader isolation alone protects against all malicious bytecode." | Loaders/modules are namespace and access-control mechanisms, not sufficient as a comprehensive sandbox. |

## 13. Self-check questions

**Q1.** Loaders A and B both have the system loader as their parent. In the example, why can B still load `p.alpha.Greeter` defined by A?

**Answer:** `defineModulesWithManyLoaders` creates direct delegation based on the package belonging to module `m.alpha` being appropriately exported and read by module `m.beta`. A is a peer loader of B and does not need to be its parent.

**Q2.** Is there a contradiction between `b.getParent() != a` and `b.loadClass("p.alpha.Greeter") == a.loadClass("p.alpha.Greeter")`?

**Answer:** No. `getParent()` only returns the parent relationship; `loadClass` can delegate directly to another loader according to module mapping and return the same `Class<?>`.

**Q3.** Why does `m.beta requires m.alpha` not mean every private method in `m.alpha` can be called from `m.beta`?

**Answer:** Module readability does not override Java access permissions. Public APIs also need appropriate package exports; deep reflection may require `opens` and other conditions.

**Q4.** Why can the platform loader sometimes delegate to the application loader even though application is a child in the parent chain?

**Answer:** In certain upgraded-module configurations, a platform module may read a module defined by another loader, such as the app loader. Direct delegation by module/package resolves that reference without changing `getParent()`.

**Q5.** Does running `defineModulesWithOneLoader` instead of `defineModulesWithManyLoaders` remove `requires` relationships?

**Answer:** No. It only changes how modules are mapped to class loaders; module readability and `exports`/`opens` remain in effect.

**Q6.** If a class with the same name is defined independently in A and B, does the JVM consider them the same type?

**Answer:** No. Type identity requires both the binary name and the defining loader. Sharing a class via delegation so that the same `Class<?>` is returned is how to avoid this error when designing APIs across modules/plugins.

**Q7.** Why can carelessly creating two custom loaders that cross-delegate cause a deadlock?

**Answer:** Each thread may hold a lock on one loader while waiting for the other loader. For graphs that are not strictly hierarchical, routing and concurrency must be designed carefully, including using parallel-capable loaders where appropriate.

**Q8.** To know "who defined the class", do you use `getParent()` or `Class.getClassLoader()`?

**Answer:** Use `Class.getClassLoader()` on the obtained class. `getParent()` only tells you the parent of a loader; it does not identify the defining loader for each class-loading result.

## Study takeaway

The **parent** relationship is a structural branch of class loaders; the **module reads/exports** relationship determines dependencies and accessibility between named modules; and **delegation during class loading** can be a **directed graph** with edges to peer loaders or non-ancestor loaders. Therefore, to explain where a class was found from, examine **the package, module, module layer, assigned loader, delegation path, and defining loader** instead of only tracing `getParent()`.

Standard references to consult:

- [ClassLoader – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) (delegation, parallel-capable, and the platform/application exception with upgraded modules).
- [ModuleLayer – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) (`defineModulesWithOneLoader`, `defineModulesWithManyLoaders`, package/module mapping, and direct delegation).
- [Module – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) (readability, exports, opens).
- [JVM Specification 17 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) (defining loader, initiating loader, type identity, and loading constraints).
