# Adjusting reads, exports, and opens Within Permitted Bounds Using ModuleLayer.Controller

When Java runs with the **Java Platform Module System (JPMS)**, relationships between modules do not depend solely on the class path or package names. Three key pieces of information govern interoperability:

- Which module **reads** which module: an edge in the module graph.
- Which packages are **exported** to another module: grants access to `public` types and members under standard Java access control, when other access conditions are met.
- Which packages are **opened** to another module: grants **deep reflective access** via APIs such as `setAccessible(true)`, including non-`public` members, if the corresponding reflective access conditions are met.

`ModuleLayer.Controller` is an API introduced in Java 9 that allows **the creator of a new module layer** to add those relationships at runtime for **modules belonging to the layer managed by that controller**. It is useful for plugin systems, applications creating custom module layers, and trusted frameworks needing limited access grants.

Core rule:

> `Controller.addReads(source, target)`, `Controller.addExports(source, packageName, target)`, and `Controller.addOpens(source, packageName, target)` can only modify relationships **originating from a source module belonging to the controlled layer**. A controller cannot be used to arbitrarily modify source modules belonging to the boot layer, a parent layer, or another independent layer.

These operations **add permissions at runtime**; they do not rewrite `module-info.java`, do not mutate the original `ModuleDescriptor`, and do not provide a way to revoke permissions afterward. Therefore, the controller must be kept in trusted infrastructure code and never handed directly to untrusted plugins.

## 1. Why Do We Need a Controller When module-info.java Already Exists?

In an explicit named module, the descriptor specifies normal relationships:

~~~java
module sample.consumer {
    requires sample.provider;
}
~~~

~~~java
module sample.provider {
    exports sample.provider.api to sample.consumer;
    opens sample.provider.internal to sample.framework;
}
~~~

These are **two independent illustrative `module-info.java` snippets**, not the configuration of the runnable example below. `requires` determines readability when building the configuration; `exports` permits public API access; `opens` permits designated frameworks to perform deep reflection.

However, many extensible systems do not know all target modules when building the source code:

1. The host may load plugin modules after the application is already running, from a user-selected directory.
2. The host may create a new `ModuleLayer` at runtime and want to grant specific permissions between modules in that layer.
3. A host-controlled framework may need to read a plugin's internal package via reflection when the plugin does not want to `opens ...` to every module.
4. The application may want to add a readability edge for a pair of already-resolved modules that lack a static `requires` relationship.

`ModuleLayer.Controller` serves to **configure the access graph of a new layer** under the authority of the layer creator. It is a scoped coordination tool; it does not replace clean `module-info.java` design when module dependencies are static and known upfront.

## 2. The Three Operations and Their Exact Semantics

| Method | Change on Source Module | What It Permits | What It Does Not Do Automatically |
| --- | --- | --- | --- |
| `addReads(source, target)` | Adds edge `source` reads `target` | Causes `source.canRead(target)` to become `true` | Does not export `target`'s packages; does not add classes/modules to the layer |
| `addExports(source, "p.q", target)` | Exports package `p.q` of `source` specifically to `target` | Makes `source.isExported("p.q", target)` return `true`; supports public access per other conditions | Does not automatically permit deep reflection into private members; does not add a reverse reads edge |
| `addOpens(source, "p.q", target)` | Opens package `p.q` of `source` specifically to `target` | Makes `source.isOpen("p.q", target)` return `true`; supports `setAccessible(true)` and appropriate deep reflection | Does not open the package to all modules; does not load/initialize plugins or grant arbitrary access to other modules |

All three calls return the `ModuleLayer.Controller` itself so they can be chained:

~~~java
controller.addReads(consumer, provider)
          .addExports(provider, "sample.provider.api", consumer)
          .addOpens(provider, "sample.provider.internal", framework);
~~~

In the snippet above, **the source module of the first call is `consumer`**, while the source of the next two calls is `provider`. Both must belong to **the layer managed by `controller`**. `framework` or `consumer` in the **target** position may be another module depending on the scenario—including a module in a parent layer or an unnamed module—yet exporting/opening must target an actual package of the source module.

### 2.1. Readability Does Not Mean Access to Every Class

Adding only:

~~~java
controller.addReads(consumer, provider);
~~~

allows `consumer` to **read** `provider`, but does not automatically make an unexported package publicly accessible. If `provider` contains `sample.provider.api.PublicFeature` and that package is not exported, `consumer` still normally cannot link against that public class through standard access mechanisms.

Conversely, `addExports(provider, "sample.provider.api", consumer)` opens public access to the package in the direction `provider → consumer`, yet does not automatically add a `consumer → provider` reads edge. For a consumer module to use a public API normally, **both readability and export** must be satisfied.

Adding a reads relationship at runtime also does not fix compile-time errors when a source file imports types from a module that `javac` has not been permitted to read. For source code with static dependencies, declare `requires`, configure the compiler properly, or design a shared interface; the controller operates after the program begins creating layers.

### 2.2. Export Differs from Open

`exports p.q` is designed for **ordinary public API access**. It does not grant a framework permission to call `setAccessible(true)` to access private fields inside a closed package.

`opens p.q` is meant for **deep reflection**, such as dependency injection, serializers, or object instantiation frameworks. With `addOpens`, only the **selected target module** receives open-package permission. Avoid assuming that opening to one module opens to the entire JVM. For reflection, readability checks have specific conventions; the key requirement for deep reflection of private members in our example is that the package is opened to the calling module.

Example package containing a class with a private field:

~~~java
package sample.provider.internal;

public final class Secrets {
    private static final String TOKEN = "layer-secret";
}
~~~

If the host has not been granted `opens` for this package, `Field.setAccessible(true)` can throw `InaccessibleObjectException`. Once the package is opened to **the host's own module**, appropriate reflective access can succeed.

Do not use `addOpens` as a “quick fix” for every import or classloading error: it is deep access with consequences for encapsulation and confidentiality of internal state.

### 2.3. Operations Are Additive, Not Replacements

Per the Java 17 API:

- `addReads` is a no-op if `source` already reads `target`.
- `addExports` is a no-op if the package is already exported at least to `target`.
- `addOpens` is a no-op if the package is already open at least to `target`.

There is no `removeReads`, `removeExports`, or `removeOpens` in `ModuleLayer.Controller`. Once a relationship is added to active `Module` instances, the controller cannot be used to revoke that exact permission. If the policy must change completely, you typically have to build a new generation of layers and retire the old layer when safe; creating a new layer also does not force the JVM to drop references to old modules/classes.

## 3. How Is a Controller Obtained?

Two groups of APIs look very similar yet differ in return value:

| Call | Return Value | Controller Returned for Further Adjustment? |
| --- | --- | --- |
| `parentLayer.defineModulesWithOneLoader(configuration, parentLoader)` | `ModuleLayer` | No controller returned |
| `parentLayer.defineModulesWithManyLoaders(configuration, parentLoader)` | `ModuleLayer` | No controller returned |
| `parentLayer.defineModules(configuration, loaderFunction)` | `ModuleLayer` | No controller returned |
| **`ModuleLayer.defineModulesWithOneLoader(configuration, parentLayers, parentLoader)`** | **`ModuleLayer.Controller`** | **Yes** |
| **`ModuleLayer.defineModulesWithManyLoaders(configuration, parentLayers, parentLoader)`** | **`ModuleLayer.Controller`** | **Yes** |
| **`ModuleLayer.defineModules(configuration, parentLayers, loaderFunction)`** | **`ModuleLayer.Controller`** | **Yes** |

The **static** overloads accepting a list of parent layers are the layer-creation entry points that return a controller. Afterward, obtain the new layer via:

~~~java
ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer layer = controller.layer();
~~~

This is an illustrative snippet; the `configuration` variable must be properly resolved against the corresponding parent configurations. You cannot take an arbitrary previously created `ModuleLayer` and “ask for its controller again” through a standard API like `getController()`.

### 3.1. Sequence for Building a Module Layer

Typically the host executes:

1. Choose a `ModuleFinder` to locate modular JARs/exploded modules.
2. Resolve into a `Configuration` with parent configurations, the appropriate root modules list, and verified dependencies.
3. Use **static** `ModuleLayer.defineModulesWith...` to create a layer together with its controller.
4. Retrieve the specific `Module` objects from `controller.layer().findModule(name)`; confirm layer/module identity.
5. Grant the **minimum required permissions** using `addReads`, `addExports`, and `addOpens`.
6. Only after configuration is complete should components in the layer use APIs or execute plugin code.

Skeleton example:

~~~java
ModuleLayer boot = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Configuration cf = boot.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("sample.provider", "sample.consumer"));

ModuleLayer.Controller ctl = ModuleLayer.defineModulesWithOneLoader(
        cf, List.of(boot), ClassLoader.getSystemClassLoader());
ModuleLayer child = ctl.layer();
~~~

This is an **illustrative Java snippet requiring imports**, not a standalone program; the next section provides a complete program.

`defineModulesWithOneLoader` uses one new class loader for the modules defined in the layer, whereas `defineModulesWithManyLoaders` uses a separate loader per module. The two choices affect code isolation, package/loader constraints, and class loadability. Adding reads/exports/opens **does not** add URLs/JARs, fix classloading strategies, or solve `ClassNotFoundException` caused by missing artifacts.

## 4. Complete Java 17 Example: Adjusting All Three Permissions on a New Layer

This example intentionally places the modules into the same **child layer**, without declaring `requires` or `exports`/`opens` between them. The host runs on the classpath (unnamed module), holds the controller, and acts as the reflection caller.

Observed goals:

- Initially, `consumer.canRead(provider)`, `provider.isExported(..., consumer)`, and `provider.isOpen(..., host)` are all `false`.
- Initially, the host cannot use `setAccessible(true)` to read the private field `TOKEN` of the provider module.
- After three controller calls, all three checks become `true` and reflective access succeeds.
- The provider module's descriptor still has no `exports`.
- Attempting to modify `java.base` of the boot layer with the child layer's controller or exporting a nonexistent package is rejected.

### 4.1. File Layout

~~~text
src/
├── sample.provider/
│   ├── module-info.java
│   └── sample/provider/
│       ├── api/Visible.java
│       └── internal/Secrets.java
└── sample.consumer/
    ├── module-info.java
    └── sample/consumer/Anchor.java
host/
└── LayerControllerDemo.java
~~~

File `src/sample.provider/module-info.java`:

~~~java
module sample.provider { }
~~~

The descriptor exports or opens no packages. Both packages of the module contain actual classes, so the compiler records them as packages belonging to the module.

File `src/sample.provider/sample/provider/api/Visible.java`:

~~~java
package sample.provider.api;

public final class Visible {
    public static String ping() { return "public"; }
}
~~~

`Visible` is a public class, yet package `sample.provider.api` is **not exported**. Java does not grant all other named modules access to classes in an unexported package merely because of the `public` modifier.

File `src/sample.provider/sample/provider/internal/Secrets.java`:

~~~java
package sample.provider.internal;

public final class Secrets {
    private static final String TOKEN = "layer-secret";
}
~~~

The private static field `TOKEN` is used to test deep reflection capabilities before and after the package is opened to the host module.

File `src/sample.consumer/module-info.java`:

~~~java
module sample.consumer { }
~~~

The consumer module does not `requires sample.provider;`. The purpose of this exercise is to **grant readability via the controller at runtime**, rather than creating a static dependency in the descriptor.

File `src/sample.consumer/sample/consumer/Anchor.java`:

~~~java
package sample.consumer;

public final class Anchor {}
~~~

The `Anchor` class ensures the consumer module contains an actual class. It does not need to import or call `Visible`; the host is demonstrating mutating the module graph and checking runtime metadata.

### 4.2. Host Program Creating the Layer and Controlling Relationships

File `host/LayerControllerDemo.java`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class LayerControllerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();
        Configuration configuration = parent.configuration().resolve(
                ModuleFinder.of(Path.of("mods")), ModuleFinder.of(),
                Set.of("sample.provider", "sample.consumer"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration, List.of(parent), ClassLoader.getSystemClassLoader());
        ModuleLayer layer = controller.layer();
        Module provider = layer.findModule("sample.provider").orElseThrow();
        Module consumer = layer.findModule("sample.consumer").orElseThrow();
        Module host = LayerControllerDemo.class.getModule();

        Field token = layer.findLoader("sample.provider")
                .loadClass("sample.provider.internal.Secrets")
                .getDeclaredField("TOKEN");

        System.out.println("before reads=" + consumer.canRead(provider));
        System.out.println("before exports="
                + provider.isExported("sample.provider.api", consumer));
        System.out.println("before opens="
                + provider.isOpen("sample.provider.internal", host));
        try {
            token.setAccessible(true);
            System.out.println("deep reflection before=allowed");
        } catch (InaccessibleObjectException expected) {
            System.out.println("deep reflection before=denied");
        }

        controller.addReads(consumer, provider)
                .addExports(provider, "sample.provider.api", consumer)
                .addOpens(provider, "sample.provider.internal", host);

        System.out.println("after reads=" + consumer.canRead(provider));
        System.out.println("after exports="
                + provider.isExported("sample.provider.api", consumer));
        System.out.println("after opens="
                + provider.isOpen("sample.provider.internal", host));
        token.setAccessible(true);
        System.out.println("token=" + token.get(null));
        System.out.println("descriptor exports unchanged="
                + provider.getDescriptor().exports().isEmpty());

        try {
            controller.addReads(String.class.getModule(), provider);
            System.out.println("parent source rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("parent source rejected=true");
        }
        try {
            controller.addExports(provider, "missing.package", consumer);
            System.out.println("missing package rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("missing package rejected=true");
        }
    }
}
~~~

Technical points to note:

- `ModuleLayer.boot()` is the parent layer; `ModuleFinder.of(Path.of("mods"))` finds only the modules compiled into `mods`.
- `parent.configuration().resolve(...)` puts both root modules into a new resolved configuration. Because consumer does not declare `requires sample.provider`, it does not yet have a reads edge.
- Static `ModuleLayer.defineModulesWithOneLoader(...)` returns a **controller**, not just a layer.
- `layer.findModule(...)` retrieves the exact `Module` objects belonging to the child layer; `String.class.getModule()` is `java.base` in the **boot layer**, so it is not a valid source for this controller.
- `LayerControllerDemo.class.getModule()` is the **host's unnamed module** during this classpath run. It is a valid **target** to receive opens; the host does not need to become a member of the child layer.
- `token.setAccessible(true)` fails the first time because the package has not been opened to the host. After `addOpens` with the right target, the same call can access the private field.
- `provider.getDescriptor().exports().isEmpty()` remains `true` because the controller **dynamically** alters runtime access state without rewriting the module descriptor.

### 4.3. Compiling and Running

Create the directories/files matching the tree above. From the directory containing `src` and `host`, run with JDK 17 or higher:

~~~bash
javac --release 17 --module-source-path src -d mods -m sample.provider,sample.consumer
javac --release 17 -d out-host host/LayerControllerDemo.java
java -cp out-host LayerControllerDemo
~~~

In this example `mods` **does not need** to be placed on `--module-path` at startup, because the program itself uses `ModuleFinder.of(Path.of("mods"))` to find and resolve modules into the child layer. The host uses the classpath, while plugin modules are loaded in the new layer.

Verified stdout when compiled with `--release 17` and run:

~~~text
before reads=false
before exports=false
before opens=false
deep reflection before=denied
after reads=true
after exports=true
after opens=true
token=layer-secret
descriptor exports unchanged=true
parent source rejected=true
missing package rejected=true
~~~

**Interpretation of each piece of evidence:**

1. The three initial `false` values confirm that the reads/exports/opens relationships do not yet exist between the `Module` instances referenced in code.
2. `deep reflection before=denied` reflects JPMS denying breaking encapsulation of a private member in an unopened package.
3. The `true` values after calling the controller prove the three runtime relationships were added.
4. `token=layer-secret` confirms deep reflection works after granting open permission solely to the host module.
5. `descriptor exports unchanged=true` proves the declared metadata was not modified.
6. `parent source rejected=true` is evidence of the management boundary: the child layer's controller cannot modify the parent layer's source module `java.base`.
7. `missing package rejected=true` confirms an arbitrary package not owned by the source module cannot be exported.

The example intentionally **does not** compile source in `sample.consumer` directly importing `sample.provider.api.Visible`. The program is demonstrating **adjusting the runtime access graph**. For ordinary compile-time imports, `javac` must also be configured with the corresponding module relationships; a controller created at runtime cannot go back in time to change compilation results.

## 5. Exact Scope That a Controller Is Allowed to Modify

### 5.1. Source Must Belong to the Controlled Layer Itself

Example:

~~~text
boot layer
    java.base                  <-- cannot be used as source for the controller below
       |
       +---- child layer (controller.layer())
                sample.consumer  <-- valid source for addReads
                sample.provider  <-- valid source for addExports/addOpens
~~~

In each call:

~~~java
controller.addReads(source, target);
controller.addExports(source, "some.package", target);
controller.addOpens(source, "some.package", target);
~~~

`source` must be a `Module` object belonging to `controller.layer()`. It is **not** enough if a module merely has the same string name as a module in that layer. Two different layers can contain modules with the same name that are distinct `Module` objects and classes.

For `addExports`/`addOpens`, `some.package` must be a **package belonging to the source module**. The package name must match exactly; exporting a parent package name does not automatically apply to subpackages. For example, `sample.provider` is not a substitute for `sample.provider.internal`.

### 5.2. Target Does Not Have the Same Membership Restriction as Source

The target of the three methods is the module receiving the new relationship; the API does not require the target to reside in the same layer as the source. For example, this article grants `opens` from a source module in the child layer to the **host's unnamed module**. That is valid, whereas using `java.base` as the **source** to update from the child layer's controller is invalid.

Depending on the operation, the target is still subject to normal module graph and API constraints. Do not confuse “the target may reside outside the layer” with “the controller has authority to modify the target itself”: adding `source.reads(target)` or `source.exports(package, target)` **does not** grant the host permission to update the internal exports/opens of the target module.

### 5.3. Permissions Are Not Automatically Transitive

If `A` reads `B` and `B` reads `C`, you cannot conclude all read relationships and public API access propagate to `A`. JPMS has the concept of implied readability via `requires transitive` in descriptors and resolution rules; a single `addReads` edge does not mean “all dependencies of B are exposed to A”.

Similarly, exporting `p` from module `B` to `A` does not mean exporting `p` to every module that reads `A`, and opening `p` to framework `F` does not open the package to every module invoked by the framework.

### 5.4. No Revocation API in Controller

The controller holds authority to add edges/permissions during the module lifecycle. The API provides no inverse operations. Do not design a mechanism to “open a package for 5 milliseconds and then close it” using `addOpens`: Java provides no corresponding `removeOpens` here.

If providers need per-session or per-tenant isolation, create separate layers/loaders according to policy and manage references/lifecycle. However, a new layer does not delete `Module`, `Class`, or instance objects of an old layer if the host still holds references.

## 6. Comparison with Module.addReads/addExports/addOpens

A `Module` object also has methods such as `Module.addReads`, `Module.addExports`, and `Module.addOpens`, yet they are **caller-sensitive**: normally only code inside the source module can grant those relationships for its own module, provided API conditions are met.

`Controller` is a mechanism that **the party authorized to create the new layer** can use to adjust modules in that layer without needing code executed from within each source module itself. That is a difference in **scope of orchestration authority**, not a feature that disables all JPMS restrictions.

| Case | Appropriate Tool |
| --- | --- |
| Module knows public dependencies at compile time | `requires` / `exports` in `module-info.java` |
| Module proactively opens a package to a known framework | `opens p.q to framework.module;` in the descriptor |
| A module grants permissions to itself at runtime per its own contract | `Module.addReads/addExports/addOpens`, when the caller is valid |
| Host just created a child layer and needs to add relationships within that layer's scope | `ModuleLayer.Controller` |
| Adjusting access for a source module in the boot/parent layer | Cannot use a child layer's controller; revisit architecture/descriptors/mechanisms permitted by the module owner or launcher |

Avoid equating the `Controller` API with JVM options `--add-reads`, `--add-exports`, and `--add-opens`. Launcher options have different scope/lifecycle and are configured at startup; the controller operates on `Module` objects of a layer created at runtime.

## 7. Difference Between Access Permissions and Finding/Resolving/Loading Classes

Adding a module relationship does not automatically solve every runtime issue:

- **Resolve:** `Configuration.resolve` must resolve the required modules before creating the layer. `addReads` does not make an unresolved module appear.
- **Class loading:** `ModuleLayer` maps modules to class loaders. If the artifact/JAR is absent or the class loader cannot locate the bytecode, adding readability will not fix `ClassNotFoundException`.
- **Readability:** module `A` must read the exact module containing `B` to access types through normal linkage.
- **Exports:** the package containing a public type must be exported to the accessing module (aside from special conditional access mechanisms).
- **Opens/reflection:** private access via reflection requires the right package to be opened to the module of the code performing the reflective operation.
- **Service use/provision:** `uses`, `provides`, and `ServiceLoader` have their own contracts; adding reads/exports does not register a new service provider.

For example, a provider class that exists yet cannot be loaded due to a wrong JAR will still not be resolved by calling `addOpens`. Conversely, a class already loaded by a loader may still be inaccessible to code in another module due to module readability/package exports.

Dynamically adding permissions can serve subsequent valid linkage and reflective access from that point onward; do not infer that it “recompiled” bytecode or automatically recovered operations that already failed or partially initialized before permissions were added.

## 8. Common Errors and Handling Policy

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `IllegalArgumentException` from `addReads` | `source` does not belong to the layer managed by the controller | Check `source.getLayer() == controller.layer()` and how the `Module` was obtained |
| `IllegalArgumentException` from `addExports`/`addOpens` | Source in wrong layer or package does not belong to source | Verify exact `Module` and full package name |
| `InaccessibleObjectException` on `setAccessible(true)` | Package not opened to the module performing reflection | Grant qualified opens to the right target or fix the descriptor |
| `IllegalAccessException` during reflection call | Member/class not accessible under current mode | Check caller module, exports/opens, and how reflection is invoked |
| `ClassNotFoundException` | Loader cannot find class/JAR | Check `ModuleFinder`, layer loader, module artifact; do not merely adjust reads |
| `NoClassDefFoundError`/`LinkageError` | Missing dependency, classloader identity/loader constraints, or prior initialization error | Inspect causes, module graph, class loaders, and linkage timing |
| `java.lang.SecurityException` when creating layer | Environment/security manager (if present) denies a privileged operation | Comply with environment policy; do not treat controller as a bypass |
| `findModule(name)` returns empty | Module was not resolved into the layer/parents or wrong name | Review roots, finder, configuration |
| Package is open yet code still fails | Issue at compile time, class loading, access kind, or wrong target module | Separate read/export/open layers and verify actual `Module` objects |

Per the Javadoc, controller methods may throw `IllegalArgumentException` for a source not in the layer, and for export/open also when the package does not exist in source. A `null` argument generally results in `NullPointerException` unless documented otherwise. Do not mask errors by probing arbitrary packages until errors “go away”: that signals faulty module metadata or ownership.

### 8.1. Inspecting the Access Graph via API, Not Just Logs

~~~java
boolean reads = source.canRead(target);
boolean exports = source.isExported("sample.provider.api", target);
boolean opens = source.isOpen("sample.provider.internal", target);
~~~

These are three expressions used with existing `source` and `target` variables; they inspect runtime relationship state. In the main example program, the three methods are called with **different source/target module pairs** matching each permission.

When diagnosing, also log:

~~~java
System.out.println("source=" + source.getName() + " layer=" + source.getLayer());
System.out.println("target=" + target.getName() + " layer=" + target.getLayer());
~~~

This snippet only makes sense when `source` and `target` are already-obtained `Module` objects, not as a standalone program. If `target` is an unnamed module, `getName()` can be `null` and `getLayer()` may have no layer in the sense of named modules; never use string names as the sole key in place of module identity.

### 8.2. Checking Whether a Package Actually Belongs to Source

For a resolved named module, `source.getPackages()` returns the packages contained in the module. You can check:

~~~java
if (!source.getPackages().contains("sample.provider.internal")) {
    throw new IllegalArgumentException("Source module does not contain package");
}
~~~

This catches wrong package names before calling the controller. Packages in `ModuleDescriptor`/`Module` are concrete package names; there is **no** rule to “export an entire sub-namespace” when exporting a parent package.

## 9. Operational Safety and Privilege Boundaries

**Do not hand the controller to untrusted code.** This is a direct recommendation from the `ModuleLayer.Controller` Javadoc: holding the controller means having the ability to widen module relationships across the entire controlled layer. If a plugin obtains the controller, it can weaken encapsulation boundaries between modules in the layer.

For a host managing plugins, you should:

1. Keep the controller in a trusted infrastructure module or component; do not expose it in public extension contexts.
2. Validate the **source module** using the `Module` object itself and layer ownership, not merely a module name string supplied by a plugin.
3. Choose the **target module** deliberately, granting opens/exports per specific package and target, avoiding unnecessarily broad access surfaces.
4. Complete configuration before publishing providers into a registry or invoking callbacks. Avoid letting in-flight requests observe half-configured permission state unless intentionally designed.
5. Log/audit new relationships with source, target, package, reason, and plugin version; record all errors rather than silently continuing.
6. Do not rely on reversing permissions via the controller: to change policy, design a new layer generation and a controlled transition.
7. Clean up loaders, threads, service instances, listeners, caches, and context references when stopping a plugin. Retaining a `Module` or `Class<?>` long-term can prevent the old layer/loader from being garbage collected.
8. Understand the limits of JPMS: module encapsulation is an inter-module access control mechanism, **not a comprehensive security sandbox** for running malicious code in the same process.

**Note on reachability:** The `addReads` Javadoc states that added read edges are **weak** and do not by themselves keep the target module alive merely because the source remains strongly reachable. Do not rely on read edges to manage object or plugin lifecycles; the host must retain needed references during active use.

## 10. Usage Scenarios and Design Choices

### Scenario A: A Plugin Consumer Needs to Read a Provider's New API

Consumer and provider are already in the child layer, yet the consumer's descriptor does not declare a static dependency; the host wants to add permissions at runtime:

~~~java
controller.addReads(consumer, provider)
          .addExports(provider, "sample.provider.api", consumer);
~~~

This adds readability and public API access for the package. It makes sense when the host **intentionally** wires already-resolved runtime modules. If the consumer needs to import and use the API at compile time, compiler dependencies still must be handled appropriately.

### Scenario B: A Framework Needs Access to Private Fields for Serialization

The host wants a specific framework module to read internal model state:

~~~java
controller.addOpens(provider, "sample.provider.internal", serializerModule);
~~~

Grant qualified `opens` only to `serializerModule` when reflective access is genuinely required. If the host runs in an unnamed module, pass the host's own module object as in the example. Do not automatically pass the ultimate caller's module or open to all plugins.

### Scenario C: The Plugin Knows Its Static API Upfront

If all module relationships are fixed at build time, declaring them in `module-info.java` can be easier to maintain and verify:

~~~java
module consumer.module {
    requires provider.api;
}
~~~

Using a controller in this case only adds a dynamic configuration point without necessarily adding value. Reserve dynamic access control for cases genuinely needing runtime orchestration.

## 11. Required Test Suite

When implementing a host with `ModuleLayer.Controller`, verify at least:

| Group | What to Test | Expected Sign |
| --- | --- | --- |
| Layer creation | Matching configuration/parent layers, static factory returns `Controller` | `controller.layer()` is the new layer with expected modules |
| Readability | Before/after `addReads` for a specific source/target | `canRead` transitions from `false` to `true` if no edge existed beforehand |
| Qualified exports | Source package exists, right target module | `isExported(pn, target)` is accurate, without confusing targets |
| Qualified opens | Deep reflection blocked before and permitted to the right target after | `isOpen` changes and `setAccessible(true)` succeeds only where appropriate |
| Ownership/scope | Try a source in boot/parent/another layer | `IllegalArgumentException`, no out-of-scope module modified |
| Package validation | Try a package absent from source | `IllegalArgumentException` |
| Descriptor invariance | Inspect `getDescriptor()` before/after | Descriptor does not gain synthetic `requires`, `exports`, `opens` |
| Module resolution | Omit a root/artifact from finder | Resolution or module-not-found error detected early |
| Classloader | Intentionally use wrong artifact/loader | Loading errors distinguished from access errors |
| Lifecycle | Reload multiple layer generations, close plugin resources | No leaked callbacks/threads/references retaining old loaders |

Do not rely on one successful reflection call to infer that all packages are exported or all modules can read each other. Verify **each exact relationship by source, package, and target**.

## 12. Key Points to Remember

~~~text
static ModuleLayer.defineModulesWithOneLoader(...)
          |
          +--> ModuleLayer.Controller
                     |
                     +--> layer() : child ModuleLayer
                     |
                     +--> addReads(source, target)
                     |         source belongs to child layer
                     |
                     +--> addExports(source, package, target)
                     |         source belongs to child layer
                     |         package belongs to source
                     |
                     +--> addOpens(source, package, target)
                               source belongs to child layer
                               package belongs to source

Controller:
  + adds relationships at runtime
  + supports qualified targets
  + does not modify module-info/ModuleDescriptor
  + does not revoke newly added permissions
  + does not control sources in parent/boot/another layer
~~~

**Rule of practice:** First identify **which source modules belong to the newly created layer**, then identify the exact **target modules and packages requiring access**, and finally use the controller to add the minimal relationships needed at runtime. For a plugin system, treat the controller as a bounded layer-administration capability held exclusively by the trusted host.

### Standard References

- [JDK 17 – ModuleLayer.Controller](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.Controller.html): describes controller, `addReads`, `addExports`, `addOpens`, source scope, and exceptions.
- [JDK 17 – ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): creating layers via static or instance factories, configurations, and class loaders.
- [JDK 17 – Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, and module-level APIs.
- [JDK 17 – Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html): `resolve` module graphs from finders and parent configurations.
- [JDK 17 – AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): conditions for `setAccessible` and reflective access across module boundaries.