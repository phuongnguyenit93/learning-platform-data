# Providers in the Current Layer, Ancestor Layers, and Limitations with Unnamed Modules

## 1. Context: ModuleLayer Defines the Provider Lookup Scope

In a Java plugin system using the **Java Platform Module System (JPMS)**, a host can create a new `ModuleLayer` to load **named modules** after the application starts. A layer contains modules resolved by a `Configuration` and mapped to one or more `ClassLoader` instances. Layers have **parent/child** relationships, enabling a plugin in a child layer to use modules already present in ancestor layers.

When an application discovers SPIs, there are two distinct questions:

1. **Which starting point is chosen for lookup?** A passed-in `ModuleLayer`, or a passed-in `ClassLoader`?
2. **Where was the provider registered?** A named module in a layer, or an unnamed module from the classpath?

With the Java 17 API:

```java
ServiceLoader.load(layer, Service.class)
```

`ServiceLoader` searches for providers declared in **named modules belonging to that layer and its ancestor layers**. The specification explicitly states: **this overload does not search for providers in unnamed modules**. Changing the thread context class loader or adding `META-INF/services` files onto the classpath does not turn an unnamed provider into a layer provider searched by this overload.

This is the core difference from:

```java
ServiceLoader.load(Service.class, loader)
```

The `ClassLoader` overload can find providers in **both named modules and unnamed modules** depending on the modules/loading paths visible to that loader. Meanwhile, the single-argument overload `ServiceLoader.load(Service.class)` uses the thread context class loader, so it belongs to the `ClassLoader`-based lookup family, not a query scoped to a specific `ModuleLayer`.

**Do not equate “the class can be loaded” with “it is in the layer's provider set”.** A library may be able to open a JAR with its own classloader, yet `ServiceLoader.load(layer, service)` still will not find classpath/unnamed providers.

## 2. Current Layer, Ancestors, Descendants, and Other Branches

An application may organize layers as follows:

```text
                       L0: ModuleLayer.boot()
                         |    demo.api
                         |
                       L1: parentLayer
                         |    demo.parent (provider P)
                         |
                       L2: childLayer
                              demo.child (provider C)

Classpath (unnamed module):
    demo.classpath.ClasspathGreeter (provider U)
    META-INF/services/demo.spi.Greeter
```

Suppose P, C, and U all implement the same `demo.spi.Greeter` service, but:

- P is **published via `provides ... with ...`** in named module `demo.parent` in L1.
- C is similarly published in named module `demo.child` in L2.
- U is only published via a `META-INF/services` file in a JAR on the **classpath**, belonging to the application classloader's unnamed module.

Results for **scope**, assuming no other providers exist for this service:

| Call | Providers Discoverable | Not Discovered |
|---|---|---|
| `ServiceLoader.load(L2, Greeter.class)` | C in L2, P in L1; plus providers in L0 if any | U in the unnamed module |
| `ServiceLoader.load(L1, Greeter.class)` | P in L1; plus providers in L0 if any | C in child layer L2 and U |
| `ServiceLoader.load(L0, Greeter.class)` | Providers in L0 | P/C in descendant layers and U |
| `ServiceLoader.load(Greeter.class, systemLoader)` | Providers in named/unnamed modules visible via `systemLoader`'s search mechanism; in the example setup, U | No guarantee of scanning newly created child layers |

**Lookup goes from child up to parent, not from parent down to child.** A host holding only a reference to L1 can find P, yet cannot automatically find C defined in L2. Nor does a layer have a “global plugin directory” containing every module ever created in the JVM.

### Search Order Across Multiple Parent Layers

According to Java 17's `ServiceLoader.load(ModuleLayer, Class)`:

1. Search for providers in the **passed layer first**.
2. Then traverse **parent layers depth-first** in the exact order the parents were registered.
3. Each layer is visited **at most once**.
4. **Order among modules within the same layer is unspecified.** If a single module declares multiple providers, the declaration order in its module descriptor is preserved for those providers.

For example, in a diamond where L3 has parents L1 then L2 (both children of L0): the layer visitation order is **L3 → L1 → L0 → L2**. It is not always a linear chain L3 → L2 → L1 → L0, and you must not implicitly assume the order among modules in the same layer is fixed.

In a plugin system, if providers must be prioritized by version, configuration, or trust, the host should **explicitly select/sort** by metadata or policy rather than relying on incidental iteration order from `ServiceLoader`.

## 3. Named Modules, Unnamed Modules, and Automatic Modules

### 3.1. Named Modules Published via Module Descriptor

An *explicit named module* can declare a provider:

```java
// Inside module-info.java of module demo.child
module demo.child {
    requires demo.api;
    provides demo.spi.Greeter with demo.child.ChildGreeter;
}
```

This is the **entire contents of an example `module-info.java` file**. `requires demo.api` makes the plugin module depend on the contract module, while `provides ... with ...` registers the service implementation class. While defining modules in the layer, the JVM records the provider registration from the module descriptor.

A service-consuming module that is an **explicit named module** generally must declare:

```java
// Inside module-info.java of a service-consuming module
module demo.consumer {
    requires demo.api;
    uses demo.spi.Greeter;
}
```

This snippet is independent of the hands-on program in section 5. The `uses` rule governs the validity of `ServiceLoader` calls from an explicit module. The hands-on program places the host on the **classpath**, meaning the host belongs to the unnamed module, so it does not need its own `module-info.java` or `uses`.

**Distinction:** `requires` only expresses readability of the API module; it does not replace `uses` on the consumer side or `provides` on the provider side.

### 3.2. Unnamed Modules on the Classpath

A JAR on the classpath without a module descriptor is not defined as a named module. Its classes belong to the **unnamed module** of the corresponding classloader. Traditional provider registration uses:

```text
META-INF/services/demo.spi.Greeter
```

with content:

```text
demo.classpath.ClasspathGreeter
```

That is valid for `ServiceLoader.load(Greeter.class, someLoader)` when the loader can see the JAR and provider class. However, `ServiceLoader.load(layer, Greeter.class)` **does not scan unnamed modules**, even if the classpath contains this file and the classloader holding that class is active.

### 3.3. Automatic Modules Are Not Unnamed Modules

A JAR **placed on the module path** without `module-info.class` can be treated by the system as an **automatic module** (a named module once resolved). The module name can be declared in the manifest (`Automatic-Module-Name`) or derived from the JAR filename. For automatic modules, `META-INF/services` metadata can contribute to forming provider descriptors.

Therefore, the accurate statement is **“the layer overload does not find providers in unnamed modules”**, rather than “only modules with `module-info.java` can participate in a layer” or “the layer overload never considers `META-INF/services`”. An automatic module resolved and defined into a layer is a **named module**, distinct from the same JAR on the classpath/unnamed module.

Check **where the JAR sits, how the module is resolved, and which layer the module actually belongs to**, not merely whether the JAR contains a descriptor file.

## 4. Defining a Layer Does Not Mean the Plugin Is Activated

To create a dynamic layer, a host typically performs:

1. Use `ModuleFinder` pointing to module paths, such as compiled directories or modular JARs.
2. Use `Configuration.resolve(...)` to resolve root modules and dependencies against the parent layer's configuration.
3. Use `ModuleLayer.defineModulesWithOneLoader(...)` or `defineModulesWithManyLoaders(...)` to create the layer and the classloaders defining the modules.
4. Call `ServiceLoader.load(layer, Service.class)` to discover providers in the layer and its ancestors.
5. Iterate providers and instantiate them when needed; only then does the host invoke business lifecycle methods such as `start()` if the contract defines them.

`ModuleLayer` is a **boundary for organizing modules and parent/child relationships**; it is not itself a plugin manager. Nor does `ServiceLoader` automatically perform trust verification, rollback, resource limits, or plugin unloading.

A common design mistake is assuming that calling `defineModulesWithOneLoader` immediately instantiates every provider. In practice, provider declaration/discovery and provider instantiation can happen at different times, depending on `ServiceLoader` operations and how the host iterates results.

## 5. Complete Java 17+ Example: Two Layers and One Unnamed Provider

This example uses **one service in the named module `demo.api` in the boot layer**, two plugins in two dynamically created layers, and one provider JAR on the classpath. The goal is to demonstrate simultaneously:

- Querying the **parent layer** retrieves only providers from parent/boot.
- Querying the **child layer** retrieves providers in both child and parent.
- Both `ModuleLayer`-based queries **do not retrieve the provider from the unnamed module**.
- Querying with the **application classloader** can retrieve the classpath provider, yet does not automatically scan every module in the two child layers.

### 5.1. Source File Layout

```text
layer-demo/
├── api/
│   ├── module-info.java
│   └── demo/spi/Greeter.java
├── parent/
│   ├── module-info.java
│   └── demo/parent/ParentGreeter.java
├── child/
│   ├── module-info.java
│   └── demo/child/ChildGreeter.java
├── unnamed/
│   └── demo/classpath/ClasspathGreeter.java
├── unnamed-resources/
│   └── META-INF/services/demo.spi.Greeter
└── host/
    └── demo/host/Main.java
```

Source paths are **relative to the `layer-demo` directory**. Compiled modules are placed in separate `mods/api`, `mods/parent`, and `mods/child` directories; `module-info.class` resides at the root of each module directory. The classpath provider is packaged into an independent JAR.

### 5.2. Service API in the Boot Layer

**`api/module-info.java`**

```java
module demo.api {
    exports demo.spi;
}
```

**`api/demo/spi/Greeter.java`**

```java
package demo.spi;

public interface Greeter {
    String id();
}
```

`demo.api` exports the package so the parent/child named modules and the host on the classpath see **one single type identity** for `Greeter`. The launch command will use `--add-modules demo.api` to bring the API module into the boot layer.

### 5.3. Provider in the Parent Layer

**`parent/module-info.java`**

```java
module demo.parent {
    requires demo.api;
    provides demo.spi.Greeter with demo.parent.ParentGreeter;
}
```

**`parent/demo/parent/ParentGreeter.java`**

```java
package demo.parent;

import demo.spi.Greeter;

public final class ParentGreeter implements Greeter {
    public ParentGreeter() {
    }

    @Override
    public String id() {
        return "parent";
    }
}
```

`demo.parent` is a named module declaring its provider directly in the descriptor; `META-INF/services` is not needed for this example.

### 5.4. Provider in the Child Layer

**`child/module-info.java`**

```java
module demo.child {
    requires demo.api;
    provides demo.spi.Greeter with demo.child.ChildGreeter;
}
```

**`child/demo/child/ChildGreeter.java`**

```java
package demo.child;

import demo.spi.Greeter;

public final class ChildGreeter implements Greeter {
    public ChildGreeter() {
    }

    @Override
    public String id() {
        return "child";
    }
}
```

`demo.child` is resolved in a configuration whose parent is `parentLayer`'s configuration; only then is it defined as `childLayer`.

### 5.5. Provider in the Unnamed Module

**`unnamed/demo/classpath/ClasspathGreeter.java`**

```java
package demo.classpath;

import demo.spi.Greeter;

public final class ClasspathGreeter implements Greeter {
    public ClasspathGreeter() {
    }

    @Override
    public String id() {
        return "unnamed";
    }
}
```

**`unnamed-resources/META-INF/services/demo.spi.Greeter`**, containing a single line:

```text
demo.classpath.ClasspathGreeter
```

This class is packaged into a JAR **placed only on the application classpath**, not resolved as a module in the parent/child layers.

### 5.6. Host Creating Layers and Listing Providers

**`host/demo/host/Main.java`**

```java
package demo.host;

import demo.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    private static String names(ServiceLoader<Greeter> services) {
        return services.stream()
                .map(provider -> provider.get().id())
                .sorted()
                .toList()
                .toString();
    }

    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        Configuration parentConfig =
                boot.configuration().resolve(
                        ModuleFinder.of(Path.of("mods/parent")),
                        ModuleFinder.of(),
                        Set.of("demo.parent"));

        ModuleLayer parentLayer =
                boot.defineModulesWithOneLoader(
                        parentConfig, ClassLoader.getSystemClassLoader());

        Configuration childConfig =
                parentLayer.configuration().resolve(
                        ModuleFinder.of(Path.of("mods/child")),
                        ModuleFinder.of(),
                        Set.of("demo.child"));

        ModuleLayer childLayer =
                parentLayer.defineModulesWithOneLoader(
                        childConfig, ClassLoader.getSystemClassLoader());

        System.out.println("parent=" + names(
                ServiceLoader.load(parentLayer, Greeter.class)));
        System.out.println("child=" + names(
                ServiceLoader.load(childLayer, Greeter.class)));
        System.out.println("classpath=" + names(
                ServiceLoader.load(
                        Greeter.class, ClassLoader.getSystemClassLoader())));
    }
}
```

**Explanation of host code:**

- `boot` already contains `demo.api`; the host uses this module as the shared contract.
- `parentConfig` resolves `demo.parent` on top of the boot configuration; `parentLayer` is created with boot as its parent.
- `childConfig` resolves `demo.child` on top of the parent configuration; `childLayer` has `parentLayer` as its parent.
- Both parent and child use the `defineModulesWithOneLoader` overload: **each layer gets a loader for the modules within that layer**, which does not mean both layers share the same loader.
- `names(...)` instantiates providers via `Provider.get()`, extracts the identifier string, and **sorts alphabetically** for deterministic output. This sorting is a choice of the example, not an ordering guarantee of `ServiceLoader`.
- The host is a class on the classpath belonging to the unnamed module, yet it can call `ServiceLoader.load(layer, ...)` to discover providers from **named modules in the layer**. The fact that *the caller is in an unnamed module* does not mean *providers in unnamed modules* are also discovered by this overload.

### 5.7. Compiling and Running on Windows PowerShell with JDK 17+

Run the commands from the `layer-demo` directory matching the exact layout above:

```powershell
New-Item -ItemType Directory -Force -Path mods\api,mods\parent,mods\child,out\host,out\unnamed,lib | Out-Null

javac -d mods\api api\module-info.java api\demo\spi\Greeter.java

javac --module-path mods\api -d mods\parent parent\module-info.java parent\demo\parent\ParentGreeter.java

javac --module-path mods\api -d mods\child child\module-info.java child\demo\child\ChildGreeter.java

javac --module-path mods\api --add-modules demo.api -d out\unnamed unnamed\demo\classpath\ClasspathGreeter.java

Copy-Item -Path unnamed-resources\META-INF -Destination out\unnamed -Recurse
jar --create --file lib\unnamed-provider.jar -C out\unnamed .

javac --module-path mods\api --add-modules demo.api -d out\host host\demo\host\Main.java

java --module-path mods\api --add-modules demo.api -cp "out\host;lib\unnamed-provider.jar" demo.host.Main
```

Standard output:

```text
parent=[parent]
child=[child, parent]
classpath=[unnamed]
```

This example intentionally has only the three providers listed above; no extra modules/providers for the same service are installed. `parent` does not retrieve `child` because L2 is a descendant of L1. `child` retrieves both named providers in L2 and L1. Both layer-based queries **ignore** the classpath provider. The system-classloader query reads the unnamed JAR's service descriptor and finds `unnamed`; `systemLoader` in this setup is not the classloader that defined the modules of the two dynamic layers.

**OS note:** on macOS/Linux, use `/` for paths, `:` as the classpath separator, and equivalent shell commands for creating directories/copying. The commands above are tailored for PowerShell; avoid pasting them verbatim into Bash.

**Do not run with a module path containing `mods/parent` or `mods/child` at startup** if you want to observe dynamic layer creation. Only `demo.api` should be present in the boot layer; the two provider modules are discovered via `ModuleFinder.of(...)` while the host runs.

### 5.8. Experiments Changing One Condition

**Experiment A — calling from parent:**

```java
ServiceLoader.load(parentLayer, Greeter.class)
```

Does not find the `child` provider. Therefore, if the host only holds `parentLayer` but wants to find new plugins in `childLayer`, the host must keep and use the reference to `childLayer` itself (or an explicit registry mechanism).

**Experiment B — removing the unnamed JAR from the classpath:** `classpath=[]` is printed, while `parent=[parent]` and `child=[child, parent]` remain unchanged. If you also remove `META-INF/services` while keeping `ClasspathGreeter` in the JAR, classloader-based lookup will not automatically discover this provider either.

**Experiment C — changing only the TCCL:** in the setup above, calling `Thread.currentThread().setContextClassLoader(...)` does not alter the **layer set** of `ServiceLoader.load(childLayer, Greeter.class)`; the layer argument determines the scope. However, TCCL can affect libraries or providers that use other lookup APIs during execution. Whenever you must change TCCL, always restore it in a `finally` block.

**Experiment D — adding another provider to the parent module:** when the provider is validly declared via `provides`, both parent and child lookups can see this new provider. Do not rely on its position in the list if multiple providers exist in the same layer; sort according to application policy.

## 6. Essential Limitations When Designing a ModuleLayer-Based Plugin System

### 6.1. Does Not Search Down into Child/Sibling Layers

If a host has multiple plugin layers such as L1, L2a, and L2b sharing a parent, `ServiceLoader.load(L2a, Service.class)` does not automatically discover L2b's providers simply because they are “siblings”. Likewise, searching from L1 does not discover providers in L2a or L2b. Explicitly identify **which layer serves as the context** for each lookup.

### 6.2. “Named” Is Necessary, Yet Provider Declaration Is Still Required

Having a named module containing a class `MyProvider implements Service` does not mean `ServiceLoader` automatically scans every class for implementations. Explicit modules need `provides ... with ...` (or the corresponding specified registration mechanism). Automatic modules are the distinct case discussed in section 3. Being able to load a class does not mean the module has **published a service provider**.

### 6.3. Consumer Module and Service Access Requirements

- An explicit module calling `ServiceLoader.load(...)` must declare `uses` for the service; otherwise it can receive `ServiceConfigurationError`.
- If the service type resides in another module, the consuming module also needs appropriate `requires` and access to the package from which the type is exported.
- The provider module needs `requires` for the service API and a valid `provides ... with ...` declaration. The provider class must satisfy JPMS rules for type, constructor/factory, and loadability.
- In the example, the host is in the unnamed module; it can read `demo.api` after `--add-modules demo.api` resolves the API into the boot layer. That specific startup flag is part of the example and cannot be omitted arbitrarily.

**Do not guess based solely on classloader visibility.** In JPMS, module readability, exports/opens, module names, and `Configuration` resolution all affect the usability of types and resources.

### 6.4. Watch Out for Class Identity and Duplicate APIs

If a plugin bundles its own copy of `demo.spi.Greeter` and its loader actually defines that copy, the JVM can treat the two `demo.spi.Greeter` types as distinct despite having identical names. The provider may then be rejected by `ServiceLoader` as not a subtype of the service the host expects. All providers should share **one API module and contract class identity**; fixing this error is not as simple as changing the TCCL.

### 6.5. Do Not Treat Layers as Sandboxes or Complete Hot-Reload

Creating a new layer does not isolate I/O, network, threads, or untrusted code. Closing files/JARs or dropping references to a `ModuleLayer` does not guarantee immediate class unloading either. Threads, caches, `ServiceLoader` instances, object instances, or callbacks holding onto the classloader can keep resources alive longer than intended. The host must manage plugin lifecycles and resources.

### 6.6. Ordering and Caching

`ServiceLoader` loads providers lazily during iteration and caches providers per **`ServiceLoader` instance**. If you change layer configurations or release a new plugin version, do not assume an already-created `ServiceLoader` automatically sees the new layer. Normally, loading a new module/version requires **creating the appropriate configuration/layer**, then creating a new `ServiceLoader` against the new layer and releasing references to the old lifecycle. `reload()` only resets the provider cache of that same `ServiceLoader` instance; it does not alter the module layer structure.

### 6.7. Common Errors and How to Isolate Them

| Symptom | Common Cause | What to Check |
|---|---|---|
| `load(parentLayer, service)` misses child providers | Lookup traverses ancestors only, never descendants | Call with `childLayer` if you want to see child and ancestors |
| Classpath provider does not appear from `load(layer, service)` | Unnamed modules are excluded by this overload's specification | Use the classloader overload for classpath providers or make the module a proper layer module |
| `ResolutionException` during resolve | Dependent module not found or configuration conflict | Check module path, root modules, `requires`, and parent configuration |
| `LayerInstantiationException` when defining layer | Cannot define modules/classloaders per JPMS constraints | Check overlapping packages, duplicate module names in a loader, or loader mapping |
| `ServiceConfigurationError` on lookup/init | Missing `uses`, invalid provider, or failed instantiation | Check descriptor, class constructor/factory, and `cause` |
| `ClassCastException` or “not a subtype” | API/SPI defined as multiple distinct types | Check the origin of the service type and the provider's defining loader |
| Provider list changes order | Order across modules in the same layer is unspecified | Sort by metadata/priority before selecting |
| Plugin not seen after replacing JAR | Old layer/loader/`ServiceLoader` is still being used | Re-identify the layer, manage caches and lifecycle |

## 7. Self-Check Questions

1. **Does `ServiceLoader.load(childLayer, Service.class)` find providers in `parentLayer`?** Yes, if they are published in valid named modules in the parent layer and satisfy discovery conditions.
2. **Does `ServiceLoader.load(parentLayer, Service.class)` find providers in `childLayer`?** No; lookup traverses the current layer and ancestors, never descendants.
3. **Why is a provider JAR with `META-INF/services` on the classpath not found by the layer overload?** Because that provider belongs to an unnamed module; the `load(ModuleLayer, Class)` overload excludes unnamed modules.
4. **Is an automatic module an unnamed module?** No; an automatic module is a named module once resolved into a layer. You cannot decide solely by whether `module-info.java` is present or absent.
5. **Why are `uses` and `provides` required?** They explicitly state SPI consumption and implementation provision to JPMS; `requires` does not replace those two declarations.
6. **Are providers in a child layer guaranteed to precede all parent-layer providers?** Yes with respect to *layer* visitation order per specification. However, ordering among modules within the same layer is unspecified; do not build business priority solely on the iterator.
7. **Does TCCL turn a classpath provider into a layer provider?** No. It participates in classloader selection for classloader-based APIs, not in changing the module set of the layer overload.
8. **Why sort `names(...)` in the example?** To keep stdout deterministic and clearly illustrate scope; that is a convention of the example, not an ordering guarantee from `ServiceLoader`.

**Exercise:** add a named module `demo.sibling` into a sibling layer of `childLayer`, declaring the same service. Predict and verify that looking up from `childLayer` does not automatically find the provider in the sibling. Then add two providers in the same layer and compare `ServiceLoader.stream()` with the sorted result to see the difference between discovery order and provider selection policy.

## References

- Oracle Java SE 17, `ServiceLoader` — specifically the `load(ModuleLayer, Class)` and `load(Class, ClassLoader)` overloads: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17, `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Oracle Java SE 17, `Configuration` and `ModuleFinder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java Language Specification 17, Chapter 7 — modules and service directives: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html