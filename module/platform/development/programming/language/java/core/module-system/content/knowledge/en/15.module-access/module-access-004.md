# Readability Combined with Exports

## 1. Why requires Alone Is Not Enough

In the Java Platform Module System (JPMS), a named module cannot automatically use every public class located in other JARs. For code in module A to access a public type belonging to module B through normal access, at least two independent conditions must be satisfied:

1. **Readability**: A must **read** B in the module graph.
2. **Exports**: B must **export the package containing that type** to A.

Afterward, Java still applies access modifier rules such as public, protected, package-private, and private. A non-public class does not become public just because its package is exported.

Example:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

App can reference public types in com.acme.catalog.api if the code and compilation environment are properly configured. However, app **cannot** import public types in com.acme.catalog.internal when the internal package is not exported. Conversely, if catalog exports api yet app **cannot read** catalog, app still cannot use that type.

You can visualize this as:

~~~text
       module com.acme.app
                 |
                 |  readability: requires
                 v
       module com.acme.catalog
                 |
                 |  exports com.acme.catalog.api
                 v
       catalog's public API

Necessary conditions: module read edge + exported package
~~~

**Core point:** Readability controls relationships between **modules**; exports controls access to **packages** across module boundaries. The two mechanisms complement each other to enforce strong encapsulation.

## 2. Three Layers of Access Control

JPMS does not replace Java's access modifiers; it adds module-level control layers.

| Layer | Question | Mechanism |
|---|---|---|
| Module | Does the consumer module read the provider module? | requires, requires transitive, reads relationship |
| Package | Is the provider's package exported to the consumer? | exports, exports ... to |
| Type/member | Does the type or member have a valid access level? | public, protected, package-private, private |

Example:

~~~java
package com.acme.catalog.api;

public class Product {
    private String code;

    public Product(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    void resetForTesting() {
        this.code = "";
    }
}
~~~

If module catalog exports com.acme.catalog.api and app reads catalog:

- App can instantiate new Product("P-1") and call code().
- App cannot call resetForTesting() because the method is package-private.
- App cannot directly access the code field because the field is private.

You should not think of exports as a mechanism that "opens an entire class". It only permits normal Java access that access modifiers already allow.

## 3. Setting Up an API Module and an Application Module

Suppose the source tree consists of:

~~~text
project/
├── src/
│   ├── com.acme.catalog/
│   │   ├── module-info.java
│   │   └── com/acme/catalog/
│   │       ├── api/Product.java
│   │       └── internal/ProductRepository.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

Catalog descriptor:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

API class:

~~~java
package com.acme.catalog.api;

public record Product(String sku, String name) {
}
~~~

Internal class:

~~~java
package com.acme.catalog.internal;

public final class ProductRepository {

    public ProductRepository() {
    }

    public String storageKey(String sku) {
        return "product:" + sku;
    }
}
~~~

Even though ProductRepository is declared public, package com.acme.catalog.internal is **not exported**. This is intentional: implementation details live inside the module and do not belong to the public API.

App descriptor:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Main code:

~~~java
package com.acme.app;

import com.acme.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("SKU-1", "Keyboard");
        System.out.println(product.name());
    }
}
~~~

When compiled and run with the proper module path, app can read catalog, the api package is exported, and Product is public. All three conditions hold.

## 4. Compiling and Running the Valid Example

With the source structure above:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.catalog,com.acme.app
~~~

Output directory:

~~~text
mods/
├── com.acme.catalog/
│   ├── module-info.class
│   └── com/acme/catalog/
│       ├── api/Product.class
│       └── internal/ProductRepository.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Run:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Keyboard
~~~

The javac command uses module-info.java to verify module readability and package accessibility at compile time. At runtime, the launcher builds the module graph from module roots and actual dependencies.

--module-path only specifies where to find compiled modules; it **does not automatically add reads edges between every pair of modules on the path**.

## 5. Missing requires: Exported Package Is Still Not Enough

Keep catalog unchanged:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Now change the app descriptor to:

~~~java
module com.acme.app {
}
~~~

App still imports:

~~~java
import com.acme.catalog.api.Product;
~~~

With module source compilation, the compiler may report that the package is not visible because com.acme.app does not read com.acme.catalog. If module catalog is not even included in the resolution configuration, the message may also say the module is not in the module graph.

The root cause is neither Product lacking public nor catalog forgetting exports. The problem is that app **does not yet have readability** to catalog.

Standard fix:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

When an application genuinely depends on catalog's API, declaring requires in the descriptor establishes a clear and sustainable dependency contract.

Do not simply add catalog.jar to the module path and expect the error to disappear. The module path indicates where modules **can be found**; requires establishes the consumer's reads relationship.

## 6. Having requires Without exports: A Readable Module Is Still Not Enough

Suppose app wants to call ProductRepository:

~~~java
package com.acme.app;

import com.acme.catalog.internal.ProductRepository;

public class InvalidMain {
    public static void main(String[] args) {
        ProductRepository repository = new ProductRepository();
        System.out.println(repository.storageKey("SKU-1"));
    }
}
~~~

App already requires catalog, but catalog only exports api:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Javac may report:

~~~text
package com.acme.catalog.internal is not visible
(package is declared in module com.acme.catalog,
 which does not export it)
~~~

This is a **package accessibility** error, not a module readability error. Adding another requires line or changing JAR locations will not fix the real cause.

Possible resolutions:

1. **Prefer calling the public API** instead of accessing the internal package.
2. If the package is genuinely an API meant for all consumers, consider exporting that package.
3. If only one integration module should be allowed access, use qualified exports.
4. If the need is deep reflection, consider opens rather than exports.

Do not export com.acme.catalog.internal merely to silence a compile error without verifying whether that access fits the module design.

## 7. Readability and Exports Matrix

Consider module A wanting to import a public class from package p belonging to module B:

| A reads B? | B exports p to A? | Result of normal Java access |
|---|---|---|
| No | No | Not accessible |
| No | Yes | Not accessible due to missing readability |
| Yes | No | Not accessible because the package is not exported |
| Yes | Yes | Can access public types/members according to access modifiers |

This matrix is the most important takeaway of the lesson.

Note: "accessible" also assumes the module has been resolved, the class exists, and the type/member has a valid access level. An exports directive does not fix ClassNotFoundException from missing bytecode, and a requires directive does not turn a private field into public.

## 8. Unqualified Exports and Qualified Exports

An **unqualified export** exposes a package to every module that reads the source module:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Any named module with a suitable reads relationship to com.acme.catalog can access public types in com.acme.catalog.api.

A **qualified export** permits only specifically named modules:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;

    exports com.acme.catalog.integration
        to com.acme.erp.bridge;
}
~~~

Module com.acme.erp.bridge can use public types in com.acme.catalog.integration **if it reads com.acme.catalog**:

~~~java
module com.acme.erp.bridge {
    requires com.acme.catalog;
}
~~~

Even though module com.acme.app also has requires com.acme.catalog, it does not receive the qualified export meant for bridge.

Multiple target modules can be listed:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.erp.bridge,
           com.acme.reporting.bridge;
}
~~~

The names after to are **JPMS module names**, not package names, directory names, or Maven artifact names.

Qualified exports help extend integration capabilities without turning an entire implementation package into a public API.

## 9. Exports Applies to Packages, Not Individual Classes

JPMS has no syntax to export a single specific class:

~~~text
exports com.acme.catalog.api.Product;
~~~

This is not a valid module descriptor directive. Exports accepts a **package name**:

~~~java
exports com.acme.catalog.api;
~~~

When a package is exported, public top-level types and public members with valid access permissions in that package can be used by consumers.

If only certain classes should become API, organize the packages appropriately:

~~~text
com.acme.catalog.api
    Product
    ProductService

com.acme.catalog.internal
    ProductRepository
    CacheIndex
~~~

Then export only com.acme.catalog.api. Package organization is part of encapsulation design; module descriptors do not replace separating code by responsibility.

## 10. Readability Is Not Automatically Transitive via Regular requires

Consider three modules:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.order
    |
    | requires
    v
com.acme.model
~~~

Descriptors:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
module com.acme.order {
    requires com.acme.model;
    exports com.acme.order.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

Order reads model, and app reads order. However, app **does not automatically read model** just because order reads model with a regular requires.

If app imports:

~~~java
import com.acme.model.api.Customer;
~~~

the compiler may report that app does not read model. The model's api package is exported, yet readability from app to model is missing.

One fix is for app to declare requires com.acme.model directly. If model is part of the public API exposed by order, a more meaningful option is requires transitive.

## 11. requires transitive and Dependency APIs

A module should consider **requires transitive** when its public API contains types from a dependency module.

Example type:

~~~java
package com.acme.model.api;

public record Customer(String id) {
}
~~~

OrderService exposes Customer in its signature:

~~~java
package com.acme.order.api;

import com.acme.model.api.Customer;

public final class OrderService {
    public Customer getCustomer() {
        return new Customer("C-1");
    }
}
~~~

The order descriptor can be written:

~~~java
module com.acme.order {
    requires transitive com.acme.model;
    exports com.acme.order.api;
}
~~~

App descriptor:

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

When app reads order, the requires transitive rule lets app read model as well. If model exports com.acme.model.api, app can use the Customer type in OrderService's public API.

Two things still need to be kept separate:

- requires transitive provides readability to model.
- exports com.acme.model.api in module model provides accessibility to Customer's package.

If model does not export com.acme.model.api, requires transitive **does not automatically open that package**.

Use requires transitive only when appropriate for the API contract; do not turn every internal dependency into a transitive dependency, as that broadens the consumer's module graph unnecessarily.

## 12. requires static and Compile/Run Time

A module can declare:

~~~java
module com.acme.feature {
    requires static com.acme.annotations;
}
~~~

requires static represents a dependency required for compilation that may be absent at runtime. This is common for annotations processed only at compile time.

However, when the dependency is present in the module graph, access to its public types still requires appropriate package exports. Readability and exports do not vanish just because a dependency is static.

If runtime code actually loads or calls types from the optional module when that module does not exist, the application still risks class loading/linkage errors. requires static does not guarantee that every use of the dependency is safe when the module is absent.

Distinguish between:

- requires: mandatory dependency during module resolution.
- requires static: compile-time dependency, optional at runtime.
- requires transitive: readability propagated to consumers reading the source module.
- requires static transitive: combines static and transitive semantics when required by the API contract.

Using the right modifier expresses the dependency contract accurately instead of treating all requires identically.

## 13. Public Classes in Unexported Packages Remain Encapsulated

A common point of confusion: **public** on a class declaration does not mean that class is a public API for the entire module graph.

Example:

~~~java
package com.acme.catalog.internal;

public final class CacheManager {
    public void clear() {
    }
}
~~~

The class is public because code in other packages **within the same module** may need to use it. Yet if module-info.java does not export com.acme.catalog.internal, other modules cannot use CacheManager via normal Java access.

This is a major benefit of JPMS: a module can have multiple internal packages collaborating via public types without being forced to expose those types externally.

Example:

~~~text
com.acme.catalog
    com.acme.catalog.api          exported
    com.acme.catalog.service      not exported
    com.acme.catalog.repository   not exported
    com.acme.catalog.cache        not exported
~~~

The service, repository, and cache packages can use each other's public types **inside the same module**. External consumers only see the exported API.

## 14. Qualified Exports Do Not Create requires Automatically

Suppose catalog writes:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.erp.bridge;
}
~~~

This line does not make bridge automatically read catalog. Bridge still needs the descriptor:

~~~java
module com.acme.erp.bridge {
    requires com.acme.catalog;
}
~~~

If bridge lacks requires catalog, merely naming bridge after to is not enough to import types from the integration package.

This is a fairly common design mistake: seeing the target module in exports ... to and assuming the dependency has been established in both directions.

In practice:

- **requires** appears in the consumer module, pointing toward the used module.
- **exports ... to** appears in the provider module, granting package access to the designated consumer.

The two directives look at the same API relationship from opposite sides, and they do not replace each other.

## 15. Exports and Opens Solve Different Needs

In some cases, a consumer module does not import a type directly; instead, a framework uses reflection to invoke a constructor or access private fields.

Distinguish:

**exports** supports normal Java access to public types and appropriate public/protected members.

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

**opens** allows deep reflection on a package according to JPMS rules.

~~~java
module com.acme.catalog {
    opens com.acme.catalog.entity;
}
~~~

**Qualified opens** restricts which modules are permitted deep reflection:

~~~java
module com.acme.catalog {
    opens com.acme.catalog.entity
        to com.acme.persistence.framework;
}
~~~

For example, a serialization framework may need setAccessible(true) to read private fields in an entity. If the package is not properly opened, reflection may fail with InaccessibleObjectException.

Key points to remember:

- exports does not automatically allow deep reflection on private members.
- opens is not equivalent to exporting a package so consumers can import types directly in source code.
- Package accessibility rules for public APIs cannot be fixed simply by opening a package for deep reflection.
- open module opens the module's packages more broadly for deep reflection; do not use it if only one package/framework needs access.

Readability and reflective access permissions have separate rules. Identify whether the error occurs at compile-time access, runtime method invocation, or deep reflection before choosing a configuration approach.

## 16. Distinguishing Module Path, Resolution, Reads, and Exports

Four concepts are frequently mixed up:

1. **Observable**: the module can be found via a module finder or module path.
2. **Resolved**: the module was selected into a Configuration via roots, requires, or service binding.
3. **Readable**: a specific module has a reads relationship to another module.
4. **Accessible**: the package is appropriately exported and the type/member has valid access permissions.

Example module path:

~~~text
mods/
├── com.acme.app/
├── com.acme.catalog/
└── com.acme.experiment/
~~~

Run:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

This does not mean app reads com.acme.experiment. Module experiment may only be observable and not yet resolved; even if resolved, app still has no reads edge to experiment without an appropriate JPMS relationship.

You can add module experiment to the root set:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     -m com.acme.app/com.acme.app.Main
~~~

However, --add-modules **does not automatically add a requires from app to experiment**.

Separating these concepts prevents wrong fixes: a module not found error requires checking the module path and roots, while a does not read error requires checking the readability graph.

## 17. Comparing with the Traditional Classpath

On the classpath, the class loader typically locates classes from configured JARs, and those classes belong to the corresponding unnamed module. Module boundaries like requires/exports are not declared per JAR.

Example:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

On the module path:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Named modules require explicit dependencies and exported packages. Do not treat --module-path as just another spelling of --class-path.

A library may run fine on the classpath yet fail to compile when turned into a named module because:

- Missing requires for a dependency.
- Using a public type in a package that the dependency does not export.
- Having split packages across modular JARs.
- Module name or module descriptor does not match the artifact.
- Framework reflection needs opens that the descriptor does not yet declare.

JPMS makes explicit the dependencies that were previously hidden in a shared classpath configuration.

## 18. The Unnamed Module and Automatic Modules

The **unnamed module** contains classes loaded from the traditional classpath. It has broad readability rules to support compatibility, yet that does not mean every internal package of a named module is exported to it.

An **automatic module** appears when a JAR without module-info.class is placed on the module path. It gets an automatic module name or one via Automatic-Module-Name, and generally exports all of its packages under compatibility rules.

Automatic modules have broader reading mechanics than explicit named modules, making them a bridge when modularizing legacy libraries. Still, they participate in module resolution and can hit split package conflicts if multiple artifacts contain the same package.

Important point: a library on the module path is not always an explicit named module with an author-written descriptor. You must identify whether it is an explicit named module, an automatic module, or classpath code to explain its access rules accurately.

## 19. --add-reads Can Supplement Readability Temporarily

For applications needing compatibility, the JDK supports:

~~~text
--add-reads source.module=target.module
~~~

Example:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     --add-reads com.acme.app=com.acme.experiment \
     -m com.acme.app/com.acme.app.Main
~~~

This option adds a reads relationship at runtime. If the target module has a public API exported to app, app can access that API under normal rules.

However:

- --add-reads does not automatically export packages.
- --add-reads does not create a new module or ensure the target module is resolved.
- --add-reads does not modify module-info.class.
- If the type is needed at compile time, the build may need the corresponding compile-time option.
- This is a configuration or migration solution and should not replace requires in the official descriptor for stable dependencies.

The special target ALL-UNNAMED can be used in certain interoperability scenarios so a named module can read the classpath, but this compatibility option should be managed carefully.

## 20. --add-exports Can Open a Package Temporarily

Syntax:

~~~text
--add-exports source.module/package=target.module
~~~

Example:

~~~bash
java --module-path mods \
     --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

The command above adds an export of the internal package for app at runtime. It does not automatically add a reads edge.

If app code needs to import an internal type at compile time when the original descriptor does not export it, you may need to pass the corresponding --add-exports option to javac. If the package needs to be opened for deep reflection, use --add-opens rather than only --add-exports.

Using --add-exports can help with legacy libraries or specialized tests, yet broadly exporting internal packages increases coupling and dependence on implementation details.

If a module API truly needs to be exposed to stable consumers, consider updating module-info.java rather than maintaining scattered startup flags.

## 21. Combining --add-reads and --add-exports

A migration scenario may need both:

- App does not yet read the dependency module.
- The dependency module does not yet export the used package.

Conceptual example:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     --add-reads com.acme.app=com.acme.experiment \
     --add-exports com.acme.experiment/com.acme.experiment.api=com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

These options do not modify the module descriptors inside JARs; they adjust the runtime configuration. If app source was compiled relying on this relationship, javac had to be configured accordingly beforehand.

However, when app genuinely has a direct, long-term dependency, the architectural solution is usually:

~~~java
module com.acme.app {
    requires com.acme.experiment;
}
~~~

and the provider module exports its API package according to design policy:

~~~java
module com.acme.experiment {
    exports com.acme.experiment.api;
}
~~~

This is clearer, easier to maintain, and easier to analyze with jdeps or jar --describe-module.

## 22. ServiceLoader and Provider Modules That Need Not Export Implementations

In plugin architectures, consumers often need a service contract without needing to import the implementation class.

Service API:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Consumer:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

Provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.card.CardGateway;
}
~~~

The provider module does not need to export com.acme.payment.card just for ServiceLoader to instantiate it. The consumer works with the PaymentGateway type from the API module, so the required accessibility is on the exported API package.

This is an important example of how module readability and exports combine with dependency inversion. The app depends only on the service contract; the provider can be brought into the module layer via resolution/service binding without the app importing the provider class.

If the app tries to import CardGateway directly from the unexported package, it will be rejected by package accessibility rules — even though ServiceLoader can still instantiate the matching provider.

## 23. How to Inspect Module Access

When encountering an error, read the descriptors and observe resolution.

Inspect a named module in a modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.catalog.jar
~~~

Inspect a compiled descriptor:

~~~bash
javap -v -p mods/com.acme.catalog/module-info.class
~~~

Observe module resolution when running:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Static dependencies can be analyzed with jdeps:

~~~bash
jdeps --list-deps \
      --module-path mods \
      --module com.acme.app
~~~

These tools help answer:

- Is the app module resolved?
- Is the catalog module resolved?
- Does the app descriptor have requires catalog?
- Is there a requires transitive edge providing indirect readability?
- Which packages does catalog export, and to which modules?
- Is app importing the right API package or mistakenly importing an internal package?

jdeps performs static bytecode analysis; it does not replace checking service providers or reflective dependencies loaded dynamically at runtime.

## 24. Common Errors

### module not found

Example:

~~~text
module not found: com.acme.catalog
~~~

This is usually a module resolution failure or the compiler cannot find the dependency module. Check the module path, module name, modular JAR, and output directory.

### module does not read

Example:

~~~text
package com.acme.catalog.api is not visible
(module com.acme.app does not read com.acme.catalog)
~~~

This is a readability error. Check app's requires declarations, possible appropriate requires transitive edges, and relations added by runtime config.

### package is not exported

Example:

~~~text
package com.acme.catalog.internal is not visible
(module com.acme.catalog does not export it)
~~~

This is an exports/accessibility error. Check the public API policy and whether the internal type should be used at all.

### Public class is still inaccessible

The public class is in an unexported package, or the consumer module lacks readability. Check both JPMS conditions; public alone is not enough.

### Package is opened yet import still fails

opens serves deep reflection, not a replacement for exports to let Java source import public types from another module.

### Framework reports InaccessibleObjectException

The framework is attempting deep reflection on a package not yet opened to the framework module. Consider qualified opens or --add-opens with the exact target package and module.

### ClassNotFoundException and NoClassDefFoundError

These are typically class loading/linkage or runtime dependency issues. Check whether the artifact contains the class, module layer, class loader, compatible version, and module graph.

### Assuming --add-modules creates readability

--add-modules adds a root module but does not automatically add a reads edge from the consumer to that module. If the consumer's import lacks readability, adjust requires or --add-reads as appropriate.

### Exporting the wrong package name

Exports must specify an actual package name inside the module. Module names and package names are distinct identifiers; do not export classes by fully qualified class name.

## 25. Roadmap for Designing Module Access

A practical workflow:

1. Identify the **owning module** of each API package.
2. Place stable public APIs in dedicated packages, not mixed with implementation.
3. Export only packages that genuinely form a contract for consumers.
4. In consumers, declare requires to directly used modules.
5. Use requires transitive when a module's public API exposes types from a dependency.
6. Use qualified exports for integrations with a controlled set of target modules.
7. Keep internal packages unexported when there is no valid external consumer.
8. Use opens separately for framework deep reflection; do not casually substitute it for exports.
9. Verify compiler output and the actual runtime module path.
10. Use --show-module-resolution to distinguish merely observable modules from resolved modules.
11. Avoid keeping --add-reads and --add-exports as permanent default configuration if relationships can be expressed in descriptors.
12. When extending services/providers, use SPI/ServiceLoader to avoid direct dependence on implementation classes.

This approach keeps the module graph accurately reflecting dependency direction while package exports accurately express each module's API surface.

## 26. Hands-on Exercises

**Exercise 1 — Missing requires**

Keep catalog exporting api, but remove requires com.acme.catalog in app. Try compiling app and explain why an exported package alone is still not enough to import Product.

**Exercise 2 — Missing exports**

Keep app requiring catalog, and try importing ProductRepository from the unexported internal package. Determine whether the error lies in module readability or package exports.

**Exercise 3 — Qualified exports**

Create module com.acme.erp.bridge, add exports com.acme.catalog.integration to com.acme.erp.bridge and the corresponding requires. Verify that bridge can access public types in the integration package while regular app cannot.

**Exercise 4 — requires transitive**

Create modules model and service where service's public API returns model's Customer type. Change requires to requires transitive in service and see whether app can use Customer when it only requires service.

**Exercise 5 — Reflection**

Create an entity with a private field in an unexported package. Try using reflection from another named module; observe the difference between exports, opens, and --add-opens.

**Exercise 6 — Module present on path**

Place an extra module com.acme.experiment in mods without requiring it. Use --show-module-resolution to determine whether it is resolved; use --add-modules and evaluate whether app automatically reads experiment.

The goal of these exercises is to identify each layer accurately: module resolution, readability, package exports, and Java access modifiers.

## 27. Key Takeaways

- For a named module to access a public type in another module, it needs **readability** to the source module and an appropriate **exports** for the package containing the type.
- requires is a dependency/readability edge; exports is package accessibility. They **do not replace each other**.
- Even if a class is public, it is not a public API outside the module unless its package is exported.
- exports package applies to the entire package; there is no syntax to export a single class.
- exports ... to restricts the package to the listed target named modules; target modules must still read the source module.
- requires transitive propagates readability when a module provides a public API that uses types from a dependency.
- requires static allows a compile-time dependency to be absent at runtime, but does not bypass access and linkage rules.
- opens/opens ... to serves deep reflection, not as a substitute for requires or exports in source-level access.
- A module appearing on the module path is not necessarily resolved or readable by a consumer.
- --add-reads adds a temporary reads relationship; --add-exports adds package export access; --add-opens serves deep reflection.
- ServiceLoader can instantiate providers whose implementation packages are not exported, provided the service contract and provider metadata are valid.
- When diagnosing errors, distinguish module not found, module does not read, package not exported, and reflection denied.

**Conclusion:** In JPMS, accessibility is no longer just a question of whether a class is public and on the classpath. The consumer module must read the source module, the package containing the type must be appropriately exported, and Java access modifiers continue to apply. The combination of **readability and exports** establishes clear API boundaries, allowing modules to expose what is genuinely needed while keeping internal implementations tightly encapsulated.