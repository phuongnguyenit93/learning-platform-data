# Direct Dependencies and Transitive Dependencies

In the Java Platform Module System (JPMS), the **requires** directive declares that a module needs to read another module to compile and run. A module can declare a direct dependency with **requires**, or declare a direct dependency capable of propagating readability to consuming modules with **requires transitive**.

Both declarations create a dependency edge from the current module to the named module. The difference lies in the scope of readability: **requires** only makes the declaring module read the dependency; **requires transitive** also causes modules that read the declaring module to read that dependency as well. Properly understanding this difference helps design clear module APIs and avoids forcing every consuming application to re-declare dependencies that are already part of the public API.

## 1. What is a direct dependency?

Suppose an application module needs to use a library named **com.acme.catalog**. In the application's descriptor, declare:

~~~java
module com.acme.store {
    requires com.acme.catalog;
}
~~~

This is a direct dependency. The **com.acme.store** module reads **com.acme.catalog**, so source code in store can use types belonging to the packages that catalog exports.

For one module to read another, the dependency must be resolved on the module path or through the corresponding module configuration. The **requires** directive also participates in determining the order and validity of the module graph when the JVM launches.

For example, the catalog module exposes an API:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

The application can import the public type:

~~~java
package com.acme.store;

import com.acme.catalog.api.Product;

public final class StoreService {
    public Product findProduct(String id) {
        return new Product(id, "Keyboard");
    }
}
~~~

If **requires com.acme.catalog** is omitted, the store module does not read catalog. Even if catalog's JAR is present on the module path, the store module is still not automatically permitted to reference catalog's types.

A direct dependency should be declared when the module's source code or descriptor actually needs the other module. Explicit declaration helps readers identify which modules are direct dependencies, while helping build tools and the JVM resolve the module graph accurately.

## 2. Transitive dependencies with requires transitive

An intermediate library sometimes uses data types from another module in its public API. In that case, modules consuming the intermediate library also need to read the module containing those data types.

For example, there are three modules:

- **com.acme.model** contains the Product data type.
- **com.acme.service** provides a service and uses Product in its API.
- **com.acme.app** is the application calling service.

If service declares:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

then any module that reads **com.acme.service** also reads **com.acme.model**. The application only needs:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

The application can use both the service API and the Product type exposed by service in its public API, because the service module has propagated readability of the model module to consuming modules.

This is the meaning of the word "transitive": readability is propagated through an intermediate module in the module graph. It does not mean the JVM automatically copies classes or bundles dependency JARs into service's JAR.

## 3. Complete Example with Three Modules

Let's build a small example to clearly see how **requires** and **requires transitive** affect the source code of a consuming module.

Source tree structure:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/Product.java
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/CatalogService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### The model module

Descriptor:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Data type:

~~~java
package com.acme.model;

public record Product(String id, String name) {
}
~~~

The model module exports the **com.acme.model** package so modules that can read it can access Product.

### The service module

Descriptor:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

API:

~~~java
package com.acme.service.api;

import com.acme.model.Product;

public final class CatalogService {
    public Product findById(String id) {
        return new Product(id, "Mechanical Keyboard");
    }
}
~~~

Service depends directly on model because service's implementation and API signature use Product. The **transitive** keyword announces that the model module is also a dependency that readers of service need to be able to read.

### The app module

Descriptor:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Application runner class:

~~~java
package com.acme.app;

import com.acme.model.Product;
import com.acme.service.api.CatalogService;

public final class Main {
    public static void main(String[] args) {
        CatalogService service = new CatalogService();
        Product product = service.findById("P-100");

        System.out.println(product.name());
    }
}
~~~

Although app does not directly declare **requires com.acme.model**, it can still import and use Product because service declares **requires transitive com.acme.model**. App reads service; service propagates readability to model for app.

### Compiling and running

From the project directory, compile all three modules with the JDK:

~~~bash
javac -d out --module-source-path src -m com.acme.model,com.acme.service,com.acme.app
~~~

Run the application:

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Mechanical Keyboard
~~~

At compile time, javac resolves dependencies from the descriptors. At runtime, the JVM also builds the module graph from the module path and requires directives. If the model module is not present on the module path, resolving service will fail because service needs model directly.

## 4. What happens if service only uses requires?

Replace service's descriptor with:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

Now service still reads model and can compile its own implementation. However, app declaring only **requires com.acme.service** will not automatically read model.

If app's source code directly imports Product or declares a variable of type Product, the compiler may report that the package or module is not read. For app to use Product, app needs to declare additionally:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

The two options have different API meanings:

| Service's descriptor | App's readability when only requiring service |
|---|---|
| **requires com.acme.model** | App reads service, but does not automatically read model. |
| **requires transitive com.acme.model** | App reads service and receives propagated readability to model. |

If service does not expose any type from model in its public API, using **requires** is usually sufficient. App does not need to know service's internal dependencies and should not be forced to depend on model just because service's implementation uses it.

## 5. Rules for propagating readability across multiple layers

Transitive relationships can chain across multiple modules. Suppose:

~~~text
com.acme.app
    requires com.acme.service

com.acme.service
    requires transitive com.acme.model

com.acme.model
    requires transitive com.acme.types
~~~

When app reads service, readability is propagated onward through the **requires transitive** edges. App can read service, model, and types, provided that the involved modules are validly resolved.

The flow can be visualized as follows:

~~~text
app
 |
 | requires
 v
service
 |
 | requires transitive
 v
model
 |
 | requires transitive
 v
types
~~~

A regular **requires** edge stops readability propagation at the declaring module. A **requires transitive** edge allows modules reading the current module to also read the target module. When multiple transitive edges are chained in sequence, the effect is propagated through subsequent layers.

This does not mean every dependency of a module automatically becomes a transitive dependency. Each edge in the module graph has its own semantics. If service declares **requires model** and model declares **requires types**, app reading service does not implicitly read model or types through those regular edges.

## 6. When should requires transitive be used?

**requires transitive** should be used when the dependent module is an intentional part of the public API and consuming modules reasonably need to read that dependency.

Common situations:

- The API returns or accepts a parameter whose data type is defined in another module.
- A public interface extends an interface from a dependent module.
- A public class implements a public interface belonging to a dependent module.
- The public API uses generic types, annotations, or other types from the dependency that callers need to reference at compile time.
- A facade module designed to provide a unified API and explicitly expose the foundational modules that API users need to read.

Example:

~~~java
module com.acme.orders.api {
    requires transitive com.acme.money;
    exports com.acme.orders;
}
~~~

If orders' public API returns **Money** or accepts **Money** as a parameter, modules consuming orders typically need to read the money module to use that signature. A transitive declaration accurately expresses this relationship.

You should not use **requires transitive** just because the current module is calling a few classes from the dependency. If the dependency only serves internal implementation and does not appear in the public API contract, use **requires** to keep the consumer's module graph leaner.

## 7. Public API, exports, and requires transitive are three different things

Three concepts must be distinguished:

- **requires transitive** propagates readability of the dependent module to modules that read the current module.
- **exports** exposes a package so other modules that can read this module can access public types in that package.
- **opens** permits deep reflective access to a package under JPMS rules.

A dependency can be readable while its packages are not exported. In that case, the consuming module still cannot import types in unexported packages. Therefore, **requires transitive** does not automatically expose every package of the dependency.

Example model module:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Service module:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

App can read model because service propagates readability, but app can only access model packages that have been exported to app under module rules. Unexported internal packages remain encapsulated against normal access from other modules.

You should also not confuse **requires transitive** with **opens**. One module can read another module without being allowed deep reflective access to private members of packages in that module.

## 8. Impact on contracts and compatibility

A **requires transitive** directive is part of the public module descriptor. Consuming modules can rely on this relationship to reference types from the dependency without declaring a separate **requires**.

If a library changes from:

~~~java
requires transitive com.acme.model;
~~~

to:

~~~java
requires com.acme.model;
~~~

then applications that previously only read the library may lose readability to model. Consuming source code importing Product may fail to compile after upgrading the library.

Conversely, adding **requires transitive** expands the set of modules that consumers can read. That can be helpful when an API begins exposing types from a dependency, but it also widens the scope of dependencies visible to library users.

Therefore, before changing **requires** to **requires transitive** or vice versa, check public API signatures, extended/implemented types, library documentation, and consuming modules. This change should be treated as a module contract change, not merely a descriptor syntax edit.

## 9. requires static and combining with transitive

JPMS also has the **requires static** variant for dependencies needed at compile time but not mandatory at runtime in some situations. This meaning can be combined with readability propagation:

~~~java
module com.acme.integration {
    requires static transitive com.acme.annotations;
}
~~~

This declaration indicates that the annotations dependency is required at compile time, and readability to it is propagated to modules that read integration. However, because the dependency is static, the application must still ensure the dependency is present at runtime if execution paths actually need it.

Do not use **requires static transitive** to hide a mandatory runtime dependency. If code always needs that module to operate, declare the runtime dependency explicitly. In particular, annotations with source or class retention may have different runtime requirements than frameworks that need to read annotations via reflection.

## 10. Distinguishing the JPMS module graph from Maven/Gradle's dependency graph

JPMS and build tools both describe dependencies, but they solve different problems:

| Aspect | JPMS | Maven/Gradle |
|---|---|---|
| Goal | Defines which modules read which modules and which packages are accessible. | Finds, downloads, selects versions, and places artifacts onto the compile/runtime classpath or module path. |
| Declaration | **requires**, **requires transitive**, **requires static** in the module descriptor. | Dependency declarations and build tool configurations/scopes. |
| Dependency propagation | Propagates readability in the module graph. | Dependency transitivity rules of the artifact management system. |
| Packaging | The descriptor does not bundle dependencies into a JAR. | Plugins and tasks decide which artifacts are published or included in distribution packages. |

A **requires transitive** declaration does not replace Maven or Gradle's dependency publishing configuration. The build tool still needs to know which artifacts must be resolved and published to library users. Similarly, a dependency pulled in by Maven/Gradle does not automatically mean the current module is allowed to read it under JPMS.

For modular projects, the two graphs must stay synchronized: artifact dependencies must be resolved properly by the build tool, and module descriptors must accurately describe readability between named modules. If a build works on the classpath yet the application is launched via the module path, omissions in the descriptor may surface clearly.

## 11. How to inspect module readability

You can view the descriptor of a packaged module with:

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

Inspect a module on the module path:

~~~bash
java --module-path mods --describe-module com.acme.service
~~~

To observe resolution when running the application:

~~~bash
java --show-module-resolution --module-path mods --module com.acme.app
~~~

When encountering errors, check in turn:

1. Whether the target module is on the module path or in the module configuration being used.
2. Whether the module name in **requires** matches the name in the descriptor or the automatic module name.
3. Whether the intermediate module declares **requires transitive** for the exact dependency that the public API exposes.
4. Whether the module containing the data type exports the corresponding package.
5. Whether JPMS dependencies match the dependencies resolved and packaged by the build tool.

An unreadable module error and an unexported package error are two different issues. Identify whether the error pertains to module readability or package accessibility before modifying the descriptor.

## 12. Dependency Design Checklist

When writing a module descriptor, ask yourself:

- Does the current module directly use types or services from this dependency? If yes, declare **requires**.
- Does the dependency appear in the public API such that consumers need to read it? If yes, consider **requires transitive**.
- Has the package containing the dependency's API been exported appropriately?
- Is the dependency only needed at compile time or mandatory at runtime? Only use **requires static** when the dependency's lifecycle genuinely allows its absence at runtime.
- Does propagating the dependency expose too many internal modules to consumers?
- Does the Maven/Gradle configuration publish and resolve artifacts consistently with the module descriptor?
- Will changing the descriptor break compilation for existing consuming modules?

A module should expose exactly the dependencies that its API contract requires. **requires** keeps a dependency scoped to the direct module; **requires transitive** propagates readability to consumers when the dependency genuinely belongs to the API surface. Choosing properly between the two directives helps the module graph reflect the architecture clearly, reduces repetitive declarations, and prevents internal dependencies from being exposed unnecessarily.