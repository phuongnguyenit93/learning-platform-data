# Readability of Named Modules

In the Java Platform Module System (JPMS), a module may exist on the module path, yet code in another module is still not allowed to use its types. An important condition is **readability**: whether the module being written reads the module containing the type it wants to use.

Readability is a relationship between modules in the module graph. It answers the question: "Can Module A read Module B?". This is a necessary condition to use types from B, though not sufficient on its own. The package containing that type must also be appropriately exported, and the type/member must satisfy Java access rules.

## 1. What is readability?

For a named module, the `requires` directive in `module-info.java` declares a direct dependency and establishes a module readability relationship.

Example:

~~~java
module com.acme.orders {
    requires com.acme.catalog;
}
~~~

This declaration states that module `com.acme.orders` reads module `com.acme.catalog`. Code in orders can reference public types in packages that catalog exports, provided other access conditions are also met.

You can visualize it as:

~~~text
com.acme.orders  ──reads──>  com.acme.catalog
~~~

A module does not automatically read every module simply because their JARs sit together on the module path. The module path is where modules are located; readability is a relationship determined in the module graph after resolution.

Readability is also not synonymous with loading all classes of a module into memory. It is a module-level permission/relationship used by the compiler and runtime to enforce access rules.

## 2. Direct readability via requires

If A declares `requires B`, A reads B:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
module com.acme.service {
    requires com.acme.model;
}
~~~

The graph has two dependency edges:

~~~text
com.acme.app ──requires──> com.acme.service
com.acme.service ──requires──> com.acme.model
~~~

From the declarations above, app reads service. Service reads model. App **does not automatically read model** just because service has a dependency on model.

This is an important point when reading module descriptors: a module's dependencies are not passed by default to all consumers of that module. Each module should explicitly declare the modules its own code needs to read, unless a dependency is propagated via `requires transitive`.

In addition to declared dependencies, every named module (except `java.base` itself) has an implicit requirement on `java.base`. Therefore, normal modules can use foundational APIs such as `java.lang.String` and `java.util.List` without writing `requires java.base;` in the descriptor.

## 3. Transitive readability when using requires transitive

`requires transitive` allows a module to pass readability of a dependency on to modules that read it.

Example:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

If app declares:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

then app reads both service and model:

~~~text
com.acme.app
     │
     └── requires ──> com.acme.service
                              │
                              └── requires transitive ──> com.acme.model

Readability of app:
  app ──reads──> service
  app ──reads──> model
~~~

The rule can be stated as follows:

- A directly reads B when A declares `requires B`.
- If A reads B and B declares `requires transitive C`, then A also reads C.
- The rule continues to apply along chains of transitive dependencies.
- A regular `requires` edge from B does not propagate C to A.

`requires transitive` does not copy code, merge modules, or turn C into part of B. It only extends the consumer's readability relationship.

## 4. When should requires transitive be used?

Consider `requires transitive` when a dependency's type appears in the module's public API and consumers need to read that type in order to use the API.

For example, the model module provides the `Product` type:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Product(String id, String name) {
}
~~~

The service module uses `Product` in a public signature:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
package com.acme.service.api;

import com.acme.model.api.Product;

public interface ProductService {
    Product findById(String id);
}
~~~

The consumer only needs:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Because service exposes `Product` in its API and declares model as transitive, app can read model to import and use `Product`.

If service only uses model in its internal implementation, and the public API only returns types owned by service, use regular `requires`:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

Example of an API that does not expose types from model:

~~~java
package com.acme.service.api;

public record ProductSummary(String id, String displayName) {
}
~~~

Consumers of service only need to read service. The fact that service uses model internally is not a reason to pass the model dependency to every consumer.

### Two approaches when a consumer needs a dependency's type

Suppose app wants to use `Product` directly:

**Approach 1 — service exposes the dependency transitively**

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

This approach fits when service defines model as part of the API contract that consumers should be able to read through service.

**Approach 2 — app declares the dependency directly**

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

This approach fits when app actively uses model for app's own needs. The dependency is shown directly where it is used.

Do not choose `transitive` merely to make a "package is not visible" error go away. Check whether the dependency's type is actually part of the intermediate module's public API and whether consumers truly ought to depend on it.

## 5. Readability differs from exports and opens

A module can read another module yet still be unable to access packages that the other module keeps private.

Example:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

The app module:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

App reads catalog, but can only use public types in the `com.acme.catalog.api` package. If app attempts to import a type in `com.acme.catalog.internal`, the compiler reports that the package is not exported or not visible.

Three concepts need to be checked separately:

| Concept | Question answered | Directive |
| --- | --- | --- |
| Readability | Does Module A read Module B? | `requires`, `requires transitive` |
| Export | Which packages does Module B publish to regular Java code? | `exports` |
| Open | Which modules does Module B allow to perform deep reflection on a package? | `opens` |

For app to call a public method in catalog's API package, all of the following are required simultaneously:

1. App reads the catalog module.
2. Catalog exports the package containing that type to app (or exports it unqualified).
3. The type and member satisfy normal Java access rules.

`opens` does not make a package a compile-time API. It is intended for runtime reflection, such as when a framework needs to access private fields.

## 6. Complete example: three modules app, service, and model

Suppose there are three modules:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/api/Product.java
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/ProductService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

The model module:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Product(String id, String name) {
}
~~~

The service module propagates readability of model because `Product` appears in the public API:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
package com.acme.service.api;

import com.acme.model.api.Product;

public class ProductService {
    public Product findFeatured() {
        return new Product("P-100", "Java Module Guide");
    }
}
~~~

The app module only requires service:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
package com.acme.app;

import com.acme.model.api.Product;
import com.acme.service.api.ProductService;

public class Main {
    public static void main(String[] args) {
        Product product = new ProductService().findFeatured();
        System.out.println(product.id() + ": " + product.name());
    }
}
~~~

Compile from the directory containing `src`:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.model,com.acme.service,com.acme.app
~~~

Run app:

~~~bash
java --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
P-100: Java Module Guide
~~~

App did not declare `requires com.acme.model`, yet it can still import `Product` because service declared `requires transitive com.acme.model`.

If the service descriptor is changed to:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

then app code can still read `ProductService`, but importing `Product` will no longer be valid unless app declares `requires com.acme.model` directly. This is a practical example showing how transitive readability directly affects consumer compilation.

## 7. Readability in special cases

### requires static

~~~java
module com.acme.report {
    requires static com.acme.annotations;
}
~~~

`requires static` indicates a dependency required at compile time but allowed to be absent at runtime. It is useful for certain annotations or APIs that only serve compilation. If the program actually uses classes from that dependency at runtime, the dependency's absence can still cause loading or linking errors.

`static` and `transitive` can be combined when the contract needs to propagate readability during compilation while the dependency remains optional at runtime. Only use this when those semantics genuinely fit the API.

### Automatic modules

Legacy JARs without `module-info.class`, when placed on the module path, can be treated as automatic modules. Automatic modules have broader readability and export rules than explicit named modules. Do not use automatic module rules to infer that a regular named module can read every module on the module path.

When converting a library from an automatic module to an explicit named module, explicitly declare `requires` and `exports`. Consumers may need to add direct dependencies if they previously relied on the broad behavior of automatic modules.

### Unnamed modules

Code running on the classpath belongs to the unnamed module. The unnamed module has broad readability across modules in the runtime configuration under JPMS rules, but that does not mean named modules also have such broad readability.

When an application migrates from the classpath to the module path, dependencies that previously worked thanks to the unnamed module may need explicit declarations in `module-info.java`.

## 8. Adjusting readability when compatibility is needed

Module read relationships can be supplemented using a launcher option:

~~~bash
java --add-reads com.acme.app=com.acme.legacy \
  --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

`--add-reads source=target` instructs the source module to read the target module during that run. This is a useful mechanism for compatibility or diagnostics, especially when a dependency's descriptor cannot yet be modified.

At compile time, `javac` also has a corresponding `--add-reads` option. The runtime option does not modify `module-info.class` and does not alter the source descriptor.

Do not use `--add-reads` as the default solution for long-term architecture. If a dependency is a stable part of a module, declare `requires` in source so the dependency is managed, reviewed, and verified alongside the code.

## 9. Diagnosing readability errors

When the compiler or JVM reports that a module cannot read another module, identify the exact phase and relationship:

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `module not found` | Required module is missing from the module path/module source path | Check artifact location and module name in the descriptor |
| `package ... is not visible` | Module is readable but the package is not exported, or readability is missing | Check both `requires` and `exports` |
| App uses a type from a transitive dependency but compilation fails | Intermediate module uses regular `requires` | App declares the dependency directly, or intermediate module exposes it transitively if appropriate |
| Runtime reports missing required module | Dependency is missing from the runtime configuration | Check the runtime module path and root modules |
| Classpath code works but named module fails | Code previously relied on the broad readability of the unnamed module | Declare dependencies and package access explicitly |

Useful commands:

~~~bash
# Display the resolved module graph at runtime
java --show-module-resolution \
  --module-path out \
  --module com.acme.app/com.acme.app.Main

# Check dependencies of a module
jdeps --check com.acme.app --module-path out
~~~

When using `jdeps`, make sure the module path contains the modules the tool needs to analyze. If you need to inspect a specific descriptor, you can use `jar --describe-module` or `javap -v module-info.class`.

## 10. Design principles

1. **Direct requires:** each named module declares the dependencies its code actually needs to read.
2. **Intentional transitive:** only propagate readability when the dependency appears in the public API and consumers need to use that type.
3. **Do not rely on the module path:** a JAR existing on the module path does not automatically create a read relationship for a named module.
4. **Separate readability from visibility:** check both `requires` and `exports`; do not use one directive to solve the wrong directive's problem.
5. **Keep the public API lean:** intermediate modules should not pass every implementation dependency to consumers.
6. **Verify both compile and runtime:** the module graph and module path of both phases must align.
7. **Minimize configuration exceptions:** use `--add-reads` for controlled compatibility; place durable dependencies in the descriptor.

## Conclusion

Readability determines which modules can read which other modules in JPMS. `requires` establishes a direct read relationship; `requires transitive` propagates readability to consumers when a dependency is part of the public contract. Readability must still go hand in hand with `exports` for normal Java code to access packages and public types.

Designing named modules clearly with direct dependencies, small APIs, and intentional transitive edges keeps the module graph understandable, reduces accidental coupling, and keeps internal changes from heavily impacting consumers.