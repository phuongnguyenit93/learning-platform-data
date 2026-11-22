# One Loader and Many Loaders in ModuleLayer (Java 9+)

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish **module**, **configuration**, **module layer**, and **class loader** in the Java Platform Module System (JPMS).
- Explain when modules in a layer share a single class loader and when each module has its own class loader.
- Create layers using **defineModulesWithOneLoader** and **defineModulesWithManyLoaders**, and inspect the actual loader using **findLoader**.
- Run an example consisting of two named modules, observe the output, and choose a loader organization suitable for an application/plugin.
- Recognize common errors involving packages, readability, exports, reflection, and class identity.

**Scope:** Java 9 and later; examples use JDK 21 syntax and tools. This is a Java SE JPMS mechanism and does not require Spring or any framework.

## 1. Four Concepts That Must Be Kept Distinct

**Module** is a unit containing packages, classes, resources, and a **module-info.class** file. A descriptor can declare **requires**, **exports**, **opens**, **uses**, and **provides**. For example, module **com.demo.app** declares **requires com.demo.api** to read the library module.

**Configuration** is the result of resolving the module graph at the descriptor level: which modules are selected, which dependencies are connected, and whether the constraints are satisfied. It does not yet define the classes into the JVM.

**ModuleLayer** is the layer that organizes modules already defined at runtime based on a configuration. A layer can have one or more parent layers. The JVM starts with **ModuleLayer.boot()**; an application can create child layers to load modules/plugins dynamically.

**ClassLoader** is the object involved in locating and defining classes. The runtime identity of a class is tied to **(binary name + defining class loader)**. Therefore, two classes with the same name but defined by two different loaders are still two different types.

A brief mental model:

~~~text
ModuleFinder: finds modules on disk
    ↓
Configuration: resolves the dependency graph
    ↓
ModuleLayer: defines modules into the runtime
    ↓
ClassLoader: loads/defines classes belonging to modules
~~~

**A module layer is not synonymous with a class loader.** A layer can contain multiple modules and map them to one or more loaders. Likewise, the parent layer graph is not simply the parent tree of class loaders.

## 2. Two Options When Creating a Layer

Suppose a configuration contains two new modules:

~~~text
com.demo.app  --requires-->  com.demo.api
~~~

From the parent layer, we can call:

~~~java
ModuleLayer parent = ModuleLayer.boot();
Configuration cf = /* resolved configuration */;
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();

ModuleLayer one =
        parent.defineModulesWithOneLoader(cf, parentLoader);

ModuleLayer many =
        parent.defineModulesWithManyLoaders(cf, parentLoader);
~~~

Both approaches create a **new layer** with the modules in the configuration. The primary difference is the module → loader mapping strategy.

| Aspect | One loader | Many loaders |
|---|---|---|
| Instance API | **defineModulesWithOneLoader** | **defineModulesWithManyLoaders** |
| New modules in the layer | Share one new loader | Each module gets a new loader |
| Comparing loaders of two different modules in the same layer | Same reference | Different references |
| Class namespace separation at the loader level | Lower | Higher |
| Loader management overhead | Fewer loader objects | More loader objects |
| Ability to have identically named packages across modules | Restricted because of sharing a loader | More flexible, still subject to JPMS constraints |
| Typical fit | Groups of modules released/operated together | Modules/plugins needing separate loader boundaries |

**Important note about the `parentLoader` parameter:** this is the *parent loader* passed in when creating the new loader(s). It is **not** the loader object that will be returned by **layer.findLoader("module-name")**. With both APIs, the loaders for the new modules are created by the runtime.

A specific module is associated with only **one** defining loader in the created layer. When using many loaders, the loaders also have a mechanism to locate classes belonging to modules that the current module reads; therefore, giving each module its own loader does not break **requires** relationships.

## 3. Complete Example: Two Modules and a Launcher on the Classpath

We create two modules with a clear dependency relationship. The **Launcher** program sits on the classpath to actively create a layer at runtime; the two modules will be discovered from the **mods** directory.

### 3.1. Directory Structure

~~~text
demo/
├── Launcher.java
└── src/
    ├── com.demo.api/
    │   ├── module-info.java
    │   └── com/demo/api/Greeting.java
    └── com.demo.app/
        ├── module-info.java
        └── com/demo/app/Entry.java
~~~

### 3.2. Library Module: com.demo.api

File **src/com.demo.api/module-info.java**:

~~~java
module com.demo.api {
    exports com.demo.api;
}
~~~

File **src/com.demo.api/com/demo/api/Greeting.java**:

~~~java
package com.demo.api;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "Hello from com.demo.api";
    }
}
~~~

**exports** makes package **com.demo.api** usable by other modules according to JPMS rules.

### 3.3. Application Module: com.demo.app

File **src/com.demo.app/module-info.java**:

~~~java
module com.demo.app {
    requires com.demo.api;
    exports com.demo.app;
}
~~~

File **src/com.demo.app/com/demo/app/Entry.java**:

~~~java
package com.demo.app;

import com.demo.api.Greeting;

public final class Entry {
    private Entry() {}

    public static void run() {
        System.out.println(Greeting.text());
    }
}
~~~

**requires** allows **com.demo.app** to read **com.demo.api**. The line **exports com.demo.app** allows **Launcher** code to invoke **Entry**'s public methods via standard reflection. Exporting a package does not grant access to private members; that case requires an appropriate **opens** mechanism.

### 3.4. Launcher Creating a Layer in One or Many Mode

File **Launcher.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Launcher {
    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "one" : args[0];

        // Find the two compiled modules in the mods directory.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        // Resolve app and its dependencies (including com.demo.api)
        // on top of the boot layer's configuration.
        ModuleLayer parent = ModuleLayer.boot();
        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.demo.app")
        );

        // This is the parent loader, not the module's new loader.
        ClassLoader parentLoader = ClassLoader.getSystemClassLoader();

        ModuleLayer layer = switch (mode) {
            case "one" ->
                    parent.defineModulesWithOneLoader(cf, parentLoader);
            case "many" ->
                    parent.defineModulesWithManyLoaders(cf, parentLoader);
            default ->
                    throw new IllegalArgumentException(
                            "Valid modes: one or many"
                    );
        };

        ClassLoader appLoader = layer.findLoader("com.demo.app");
        ClassLoader apiLoader = layer.findLoader("com.demo.api");

        System.out.println("Mode: " + mode);
        System.out.println("Same loader: " + (appLoader == apiLoader));
        System.out.println("App uses parentLoader: "
                + (appLoader == parentLoader));

        // Launcher does not import Entry at compile time.
        // It obtains the class via the loader of the module created in the layer.
        Class<?> entry = appLoader.loadClass("com.demo.app.Entry");
        entry.getMethod("run").invoke(null);

        System.out.println("Entry belongs to module: "
                + entry.getModule().getName());
        System.out.println("Module belongs to new layer: "
                + (entry.getModule().getLayer() == layer));
    }
}
~~~

Explanation of key lines:

1. **ModuleFinder.of(Path.of("mods"))** locates module artifacts in the **mods** directory (such as exploded module directories after compilation).
2. **parent.configuration().resolve(...)** resolves the root module **com.demo.app** and the modules it needs to read. This configuration is the common input for both modes.
3. **defineModulesWithOneLoader** or **defineModulesWithManyLoaders** creates the layer and the corresponding loaders.
4. **layer.findLoader(...)** retrieves the loader attached to the module with the specified name in this layer; a name that does not exist in the layer causes an **IllegalArgumentException**.
5. **appLoader.loadClass(...)** loads the class through the application module's loader, while **getModule().getLayer()** shows that the class belongs to the new layer.

The example does not use single-argument **Class.forName("com.demo.app.Entry")** from Launcher: the loader that sees Launcher's classpath does not automatically search down into the child loaders of the new layer.

### 3.5. Compiling and Running

From the **demo** directory. The following commands work in a terminal with JDK 21 and **javac**/**java** on PATH:

~~~bash
javac --module-source-path src -d mods -m com.demo.api,com.demo.app
javac -d out Launcher.java

java -cp out Launcher one
java -cp out Launcher many
~~~

When running **one** mode, the beginning of the output will be similar to:

~~~text
Mode: one
Same loader: true
App uses parentLoader: false
Hello from com.demo.api
Entry belongs to module: com.demo.app
Module belongs to new layer: true
~~~

When running **many** mode:

~~~text
Mode: many
Same loader: false
App uses parentLoader: false
Hello from com.demo.api
Entry belongs to module: com.demo.app
Module belongs to new layer: true
~~~

**What to observe:** the application behaves identically in both modes. The verifiable difference is the expression **appLoader == apiLoader**. The exact output of **ClassLoader.toString()** can vary across JDKs; comparing with **==** clarifies the identity relationship.

## 4. Understanding Readability, Exports, Opens, and Delegation Properly

JPMS has two related sets of rules that do not replace one another:

**Module rules:**

- **requires** creates a readability edge from the consuming module to the dependency module.
- **exports** allows other modules to access public types/members in the exported package, according to the export scope.
- **opens** allows deep reflective access to a package according to the opened scope; distinct from **exports**.
- These rules are enforced by the JVM and reflection APIs whether modules are attached to the same loader or different loaders.

**Class loader rules:**

- A loader locates/defines classes; the fact that a loader can find a class does not by itself alter readability or exports relationships.
- In many-loaders mode, a module's loader may need to coordinate to look up classes from the loaders of modules it reads. Therefore, you should not infer that every **loadClass** call sees only a single module.
- **parentLoader** typically serves delegation to the existing system. Do not infer that a parent layer is identical to a parent loader.
- The boot layer continues to hold Java's platform modules; creating a child layer does not duplicate **java.base** into a new module.

For example: if you remove **requires com.demo.api**, access by **com.demo.app** to **Greeting** is not guaranteed by the two modules sharing one loader. If you remove **exports com.demo.api**, public classes in that package still cannot be accessed by other modules as a public API. A loader is not a tool for bypassing JPMS encapsulation.

## 5. Class Identity and Isolation Between Layers

In the JVM, two copies of a class with the same binary name can be two different types when defined by two different class loaders.

Suppose you create two independent layers, each resolving the same **com.demo.app** module from the same artifact:

~~~java
ModuleLayer first = parent.defineModulesWithOneLoader(cf, parentLoader);
ModuleLayer second = parent.defineModulesWithOneLoader(cf, parentLoader);

Class<?> a = first.findLoader("com.demo.app")
        .loadClass("com.demo.app.Entry");
Class<?> b = second.findLoader("com.demo.app")
        .loadClass("com.demo.app.Entry");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                          // false
~~~

Each layer creation produces new loaders for the new modules; therefore, the two classes have the same name but different identities. Practical consequences:

- Do not cast objects created from a class copy in layer A directly to the homonymous class in layer B.
- Do not rely on a class's fully qualified name to determine whether two objects have the same runtime type.
- When exchanging objects between plugins, prefer a common API loaded in a shared parent layer, or exchange normalized data through a clear interface.
- With many loaders in **the same layer**, the app module and api module have different loaders; this still allows app to use api's types as long as the module graph and access rules are valid.

**ClassCastException** or **LinkageError** can occur if a library/plugin assumes classes with the same name from two loaders are the same type. Choosing one loader or many loaders does not replace designing an API boundary.

## 6. Choosing One Loader or Many Loaders?

**Prefer one loader when:**

- The modules form a cohesive functional unit whose lifecycle and versions typically move together.
- You want a single shared loader for the new modules of the layer.
- The modules do not have package conflicts that would cause assignment to the same loader to be rejected.
- There is no need to separate class namespaces per module within the layer.

**Consider many loaders when:**

- Each module needs its own loader identity, such as extension components managed separately.
- You want to avoid the constraint of a single loader having to define the packages of all new modules; cases with identically named packages still must satisfy JPMS resolution and access rules.
- Diagnostic tools or the application's class-loading mechanism need to clearly distinguish loaders per module.
- You accept having more loader objects and the complexity of passing classes/objects between components.

Do not assume **many loaders = security**, **one loader = faster**, or **each module having its own loader = can be independently unloaded at any time**. JPMS is not a security sandbox. Releasing classes/layers depends on garbage collection of the loader and all live references (classes, instances, threads, static fields, services, caches, etc.); there is no simple "unload module" command.

For real plugin systems, also consider plugin lifecycle, dependency versions, shared APIs, thread context class loader, **ServiceLoader**, resource lookup, and resource-closing strategies. The two APIs here only decide how loaders are assigned to modules in the new layer.

## 7. Common Mistakes and How to Reason About Them

### 7.1. Confusing Configuration with Layer

**Symptom:** resolution succeeds, but classes cannot be retrieved as expected.

**Reason:** **Configuration** only resolves the graph. You must call a **defineModules...** API to define the modules at runtime and obtain the class loaders in the created layer.

### 7.2. Confusing `parentLoader` with the Module's Loader

**Symptom:** checking **layer.findLoader(name) == parentLoader** and treating false as an error.

**Reason:** both APIs create new loaders. Use **findLoader** to observe the actual mapping, rather than inferring it from the passed-in parameter.

### 7.3. Missing `requires`, `exports`, or `opens`

**Symptom:** module resolution errors, **IllegalAccessException**, **InaccessibleObjectException**, or other access errors.

**How to reason:** determine which module reads which module; which packages must be exported; whether code only calls public members or needs to reflect on private members. Fix **module-info.java** appropriately; do not change loaders to "bypass" rules.

### 7.4. Duplicate Packages When Using One Loader

**Symptom:** layer creation fails with **LayerInstantiationException** or package/module verification errors.

**Reason:** two new modules cannot arbitrarily define the same package in the same loader. Check the package structure and module graph. Many loaders may allow identically named packages in different loaders in valid configurations, yet still must comply with JPMS rules; there is no guarantee that every package conflict is solved merely by switching APIs.

### 7.5. Using Launcher's Loader to Find Classes in the New Layer

**Symptom:** **ClassNotFoundException** when calling **Class.forName** from the classpath or **ClassLoader.getSystemClassLoader().loadClass(...)**.

**Reason:** the system loader does not automatically search for classes inside newly created child loaders. Use **layer.findLoader("com.demo.app")** and load the corresponding class, or use an API designed specifically for interacting with the layer.

### 7.6. Assuming Many Loaders Allows Arbitrary Object Exchange

**Symptom:** casting fails even though classes have the same name; frameworks retain objects from another loader.

**Reason:** class identity includes the defining loader. Design a shared API boundary from a parent layer, or define a clear data protocol. Do not cast based on class name.

### 7.7. Assuming Creating a New Layer Modifies the Boot Layer

**Symptom:** calling **ModuleLayer.boot().findModule(...)** does not show the newly added module.

**Reason:** the module is defined in the child layer, not inserted into the boot layer. Retain a reference to the new layer and call **layer.findModule(...)** / **layer.findLoader(...)** on it.

## 8. Related APIs to Know

- **ModuleLayer.boot()**: gets the JVM's boot layer.
- **ModuleLayer.configuration()**: gets the configuration of a layer.
- **Configuration.resolve(...)**: resolves modules from finders and a set of root modules.
- **ModuleFinder.of(Path...)**: creates a finder from module artifacts on disk.
- **ModuleLayer.defineModulesWithOneLoader(cf, parentLoader)**: instance API, creates a child layer with one loader for the new modules.
- **ModuleLayer.defineModulesWithManyLoaders(cf, parentLoader)**: instance API, creates a child layer with a separate loader for each new module.
- **ModuleLayer.findLoader(moduleName)**: gets the loader of the module defined **in that layer**; returning **null** can be valid for modules defined by the bootstrap loader, for example in the boot layer.
- **ModuleLayer.findModule(moduleName)**: searches for a module through the current layer and parent layers according to API rules.
- **Class.getModule()** and **Module.getLayer()**: identifies the runtime module and layer containing a class.
- **ModuleLayer.defineModulesWithOneLoader(cf, parentLayers, parentLoader)** and the **static** **defineModulesWithManyLoaders**: take a list of parent layers and return **ModuleLayer.Controller**; obtain the layer via **controller.layer()**. Do not confuse this return type with the two instance methods in the example.
- **ServiceLoader.load(layer, serviceType)**: a way to find service providers in a layer's modules when building a JPMS-based plugin architecture. Provider modules need to declare **provides ... with ...**, and consumer modules need to declare **uses** as appropriate.

## 9. Self-Practice Exercises

**Exercise 1 — Inspecting loaders.** Run the example in both modes. Record three expressions:

~~~java
appLoader == apiLoader
appLoader == parentLoader
entry.getModule().getLayer() == layer
~~~

Expected respectively: **true / false / true** in one mode; **false / false / true** in many mode. Explain why the last expression remains true in both modes.

**Exercise 2 — Testing module boundaries.** Remove **exports com.demo.app** in the app descriptor, recompile, and try reflective invocation from Launcher. Observe the access error and restore **exports**. Analyze why switching one ↔ many is not a solution to this restriction.

**Exercise 3 — Two independent layers.** Create two layers using the same configuration and the same one mode. Obtain the class **com.demo.app.Entry** from each layer, and compare **getName()** and **==**. Explain using the pair *(binary name, defining class loader)*.

**Exercise 4 — Designing plugins.** A system has a shared API module and three plugin modules. Sketch which modules belong in the parent layer, which belong in child layers, and whether to use one or many loaders. Evaluate against the criteria: API sharing, class identity, package conflicts, lifecycle, and complexity.

## 10. Key Takeaways

- **Configuration** resolves the module graph; **ModuleLayer** defines them at runtime; **ClassLoader** loads classes.
- **One loader:** new modules in the same layer share a single loader.
- **Many loaders:** each new module in the layer has its own loader; module readability relationships are still maintained by JPMS.
- **parentLoader** is an input for delegation; to find the loader associated with a module, use **layer.findLoader(name)**.
- **requires/exports/opens** and **class-loader identity** solve two different problems; both must be understood when designing modular applications.
- Loader choice is only part of the architecture. When building real plugins, clearly design shared classes, isolated classes, dependencies, and resource lifecycles.
