# Public Types in Exported Packages

In the Java Platform Module System (JPMS), a class declared `public` is not guaranteed to be usable by another module. To access a **public type** belonging to another **named module**, the program must simultaneously satisfy conditions on **readability** between modules, **exports** of the package containing the type, and **Java access permissions** of the type itself and the members being used.

This is a crucial difference compared to traditional classpath thinking: `public` governs accessibility in the Java language, whereas `exports` governs the package boundary of a module. The two mechanisms complement each other; neither replaces the other.

## 1. Three Conditions for a Consumer to Use a Public Type

Suppose module `com.acme.app` wants to call `com.acme.catalog.api.CatalogClient` located in module `com.acme.catalog`.

For consumer source code to use that type through the public API, it needs:

1. **The consumer module reads the provider module:** usually via `requires com.acme.catalog;` in the consumer's descriptor.
2. **The provider module exports the package to the consumer:** `exports com.acme.catalog.api;` or a qualified export `exports ... to com.acme.app;`.
3. **The type has appropriate access permissions:** for a top-level class, interface, enum, or record used publicly across modules, the type must be declared `public`. Constructors, methods, and fields used by the consumer must also have valid visibility.

General formula:

```text
Can use a public type from another named module
             =
  Consumer reads provider module
             +
  Provider exports the type's package to consumer
             +
  Type/member is accessible under Java rules
```

An exported package does not mean every class or member inside becomes public. Conversely, declaring a `public class` in an unexported package does not make that type an API accessible from an external named module.

## 2. Simple Two-Module Example

A library publishes an API:

```text
project/
└── src/
    ├── com.acme.catalog/
    │   ├── module-info.java
    │   └── com/acme/catalog/api/CatalogClient.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

Library descriptor:

```java
// src/com.acme.catalog/module-info.java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Public type in the exported package:

```java
// src/com.acme.catalog/com/acme/catalog/api/CatalogClient.java
package com.acme.catalog.api;

public final class CatalogClient {
    public CatalogClient() {
    }

    public String find(String id) {
        return "Catalog item: " + id;
    }
}
```

Consumer descriptor:

```java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.catalog;
}
```

Application using the public API:

```java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import com.acme.catalog.api.CatalogClient;

public class Main {
    public static void main(String[] args) {
        CatalogClient client = new CatalogClient();
        System.out.println(client.find("P-100"));
    }
}
```

In this example, `requires` establishes readability, `exports` publishes the package, and `CatalogClient` along with the accessed constructor and method are all `public`. Therefore, `javac` can compile the application with the proper module path.

## 3. Compiling and Running the Example Above

Stand in the `project` directory. On Linux/macOS:

```shell
javac --module-source-path src \
      -d out \
      -m com.acme.catalog,com.acme.app

java --module-path out \
     -m com.acme.app/com.acme.app.Main
```

Expected output:

```text
Catalog item: P-100
```

`--module-source-path src` tells `javac` that the source tree is organized by module name. The `-m` option selects the source modules to compile. `-d out` places compiled class files into the corresponding module directories under `out`.

`java --module-path out` uses the compiled modules; `-m com.acme.app/com.acme.app.Main` specifies the module and main class.

If you want to create modular JARs for each module:

```shell
jar --create --file com.acme.catalog.jar \
    -C out/com.acme.catalog .

jar --create --file com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C out/com.acme.app .
```

You can inspect the packaged descriptors:

```shell
jar --describe-module --file com.acme.catalog.jar
jar --describe-module --file com.acme.app.jar
```

In real-world applications, Maven or Gradle may perform the compilation and packaging steps, yet the `requires`, `exports`, and `public` conditions remain unchanged.

## 4. Missing requires: Package Export Alone Is Still Not Enough

Keep the library descriptor unchanged:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

But change the consumer descriptor to:

```java
module com.acme.app {
}
```

When the source code tries to import `CatalogClient`, the compiler lacks a proper readability relationship from `com.acme.app` to `com.acme.catalog`.

A message similar to the following may appear:

```text
package com.acme.catalog.api is not visible
(package com.acme.catalog.api is declared in module
 com.acme.catalog, but module com.acme.app does not read it)
```

The proper fix is to add the module dependency as actually needed:

```java
module com.acme.app {
    requires com.acme.catalog;
}
```

Merely adding a JAR to the module path does not mean the consumer module will automatically read every observable module. The module path only provides locations to find modules; `requires` and the resolution mechanism determine reads relationships.

As an exception, runtime has special rules for the unnamed module and automatic modules; those transitional mechanisms should not be used to infer that normal explicit named modules do not need dependency declarations.

## 5. Missing exports: requires Alone Is Also Not Enough

If the library changes its descriptor to:

```java
module com.acme.catalog {
}
```

then the package `com.acme.catalog.api` is not exported. Even if the consumer has `requires com.acme.catalog;`, the compiler still refuses references to public classes in the non-exported package.

Common error message:

```text
package com.acme.catalog.api is not visible
(package com.acme.catalog.api is declared in module
 com.acme.catalog, which does not export it)
```

Standard fix when the package is genuinely part of the public API:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

If the package intentionally contains internal implementation, do not export it just to let a caller access a single class. Create a public facade or service interface in a published API package and keep the implementation inside an unexported package.

## 6. exports Does Not Automatically Make a Class Public

Consider an exported package:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

But the source contains:

```java
package com.acme.catalog.api;

class InternalCatalog {
    static String find(String id) {
        return id;
    }
}
```

`InternalCatalog` is a **package-private top-level class**, not a public type. A consumer outside the package cannot import or directly use this class even though its containing package is exported.

Similarly:

```java
package com.acme.catalog.api;

public class CatalogClient {
    private CatalogClient() {
    }

    String internalLookup(String id) {
        return id;
    }
}
```

The consumer can see the public class name `CatalogClient`, but cannot invoke the private constructor or the package-private `internalLookup` method.

If the API needs consumers to instantiate the class and call methods:

```java
package com.acme.catalog.api;

public class CatalogClient {
    public CatalogClient() {
    }

    public String find(String id) {
        return id;
    }
}
```

Access permissions must be designed at **both the type level and the member level**. Do not rely on `exports` to work around a non-public constructor or a `private` member.

## 7. Top-Level, Nested, and Member Accessibility

An exported package can contain various kinds of types:

```java
package com.acme.catalog.api;

public interface Catalog {
    String find(String id);
}
```

```java
package com.acme.catalog.api;

public enum CatalogStatus {
    READY, UNAVAILABLE
}
```

```java
package com.acme.catalog.api;

public record CatalogItem(String id, String title) {
}
```

These `public` types can form part of an exported package's API.

For nested types, you must still consider both the nested type's modifiers and the enclosing type:

```java
package com.acme.catalog.api;

public class CatalogResult {
    public static class Summary {
    }

    private static class InternalState {
    }
}
```

If the consumer reads the module and the package is exported, it can use `CatalogResult.Summary` under Java rules, but it cannot directly access `CatalogResult.InternalState` because that nested type is `private`.

A public nested type is also unusable as a public API if the enclosing type itself is not accessible. Design the entire chain of enclosing types and members so that the access contract is consistent.

## 8. Qualified Exports: Exposing an API Only to Selected Modules

JPMS supports unconditional exports:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

And **qualified exports**:

```java
module com.acme.catalog {
    exports com.acme.catalog.integration to com.acme.partner;
}
```

In the second case, the package `com.acme.catalog.integration` is exported only to the named module `com.acme.partner`. Another named module `com.acme.app` that has `requires com.acme.catalog;` but is not listed in the `to` clause cannot use public types in the integration package via normal access.

When multiple consumers are needed:

```java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.partner, com.acme.admin;
}
```

The `to` syntax takes **module names**, not Maven artifact coordinates, package names, or JAR file names.

Qualified exports are typically used for cooperative APIs between mutually known modules, not to hide an API that in practice every consumer needs. When renaming a target module, remember to review and update qualified export lists accordingly.

## 9. Public Types and requires transitive

Suppose module `com.acme.catalog` exports an API whose return type comes from `com.acme.model`:

```java
// com.acme.catalog.api.Catalog
package com.acme.catalog.api;

import com.acme.model.Product;

public interface Catalog {
    Product find(String id);
}
```

Catalog module descriptor:

```java
module com.acme.catalog {
    requires transitive com.acme.model;
    exports com.acme.catalog.api;
}
```

With `requires transitive`, a consumer reading `com.acme.catalog` is also granted readability to `com.acme.model`, which fits when catalog's public API exposes `Product`.

Consumer:

```java
module com.acme.app {
    requires com.acme.catalog;
}
```

This does not mean module `com.acme.model` automatically exports all of its packages: the model module itself must still export the package containing `Product`.

If the catalog module uses a regular `requires com.acme.model;` instead, a consumer wanting to directly use types from the model module may need to add its own `requires com.acme.model;`.

Use `requires transitive` only when you intend to propagate readability as part of the contract. Do not turn every implementation dependency into a transitive one, as consumers would gain unnecessary reads relationships.

## 10. Exported Packages vs. Open Packages

The two directives solve two different needs:

| Capability | `exports P` | `opens P` |
|---|---|---|
| Consumer imports and uses public types under normal Java rules | Yes, when consumer reads the module | Does not grant normal compile-time access |
| Access public members under Java access rules | Yes | Does not replace exports |
| Deep reflection into private fields/constructors | Not automatically | Allowed under runtime reflection rules |
| Intended for | Public API between named modules | Frameworks, serializers, ORMs, reflection |
| Has qualified `to M` variant | Yes | Yes |

Example of a library with a public API and a model used by a framework:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
}
```

The application module uses the public API in `com.acme.catalog.api`. The `com.acme.json` framework is permitted to perform deep reflection on `com.acme.catalog.model` at runtime.

Do not replace `exports com.acme.catalog.api;` with `opens com.acme.catalog.api;` if the goal is for consumers to import and call the public API. Conversely, if a framework needs to modify private fields, exporting the package alone is not enough; an appropriate open-package policy is required.

`open module` broadens reflection capability to all packages across the entire module. It does not turn private members into Java public API and is usually too broad for strong encapsulation design.

## 11. Public Types on the Classpath vs. the Module Path

A public class in a traditional classpath JAR is normally accessed based on Java access modifiers and how the class loader loads classes. If the same JAR is recognized as an **explicit named module** on the module path, `module-info.class` and module boundaries take effect.

Comparison:

```text
Classpath:
  public class + classloader visibility
  (no exports from a named module for that JAR)

Module path:
  module readability + exports + Java visibility
```

This is why a library that runs fine on the classpath can report `package ... is not visible` after moving to the module path.

If a JAR does not yet have `module-info.class`, placing it on the module path may turn it into an **automatic module**. Automatic modules have special readability/exports mechanisms to aid migration, unlike explicit named modules. Do not rely on an automatic module's broad export behavior to assume every package will remain public once the library ships an explicit descriptor later.

## 12. Do Not Confuse Exported Packages with Split Packages

An exported package does not mean the same package name can be arbitrarily distributed across multiple named modules.

Example:

```text
com.acme.alpha
    com.acme.shared.Alpha

com.acme.beta
    com.acme.shared.Beta
```

If both modules export `com.acme.shared` and a consumer reads both, the module graph can reject the configuration because the consumer reads the same package name from two modules.

Typical error message:

```text
module com.acme.app reads package com.acme.shared
from both com.acme.alpha and com.acme.beta
```

This issue is not solved by adding `exports` or `opens`. You must establish clear package ownership: move classes into the right module, rename packages, or remove duplicate artifacts.

When you see a split package error, distinguish it from a normal access error caused by an unexported package. Their root causes and fixes are different.

## 13. Inspecting Exports from Packaged Artifacts

Do not rely solely on descriptors sitting in the source tree. The module descriptor inside the final JAR is the metadata the module system actually uses.

Inspect with:

```shell
jar --describe-module --file libs/com.acme.catalog.jar
```

The tool displays the module name, dependencies, exported packages, opened packages, and declared services.

When running the application, you can observe module resolution:

```shell
java --show-module-resolution \
     --module-path mods:libs \
     -m com.acme.app/com.acme.app.Main
```

On Windows, the separator between module path entries is `;`, not `:` as on Linux/macOS.

For a module already inside the runtime image:

```shell
java --describe-module java.logging
```

You can inspect resolved modules or runtime relationships with the Java Module API when needed. However, metadata checks do not replace compiling and running an actual consumer.

## 14. Checking Access Permissions with the Java Module API

A program can query `Module` for readability and exports:

```java
Module consumer = Main.class.getModule();
Module provider = CatalogClient.class.getModule();

boolean readable = consumer.canRead(provider);

boolean exportedToConsumer =
    provider.isExported("com.acme.catalog.api", consumer);

System.out.println("Readable: " + readable);
System.out.println("Exported: " + exportedToConsumer);
```

This example assumes both `Main` and `CatalogClient` can already be referenced/loaded in the test environment. If you are diagnosing an inaccessible type, avoid writing code that directly imports that type just to debug. You can use descriptors and module metadata from APIs or tools to identify the relevant module and package.

There are two ways to query exports:

- `module.isExported("package.name")`: checks unconditional export.
- `module.isExported("package.name", consumer)`: checks whether the package is exported to a specific module, including qualified exports.

`module.canRead(other)` answers a different question than `isExported`. Both must be checked to explain whether a public type can be accessed.

These APIs reflect module relationships at runtime, including dynamic changes applied during execution, not necessarily everything written verbatim in the source descriptor.

## 15. Comparing Compile Time and Runtime

A public type can compile successfully yet fail at runtime if the configurations of the two phases do not match.

For example, the compiler is granted an extra export permission:

```shell
javac \
  --module-path mods \
  --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
  -d out/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

But the application runs without the corresponding flag:

```shell
java --module-path mods:out \
  -m com.acme.app/com.acme.app.Main
```

The bytecode may throw `IllegalAccessError` when attempting to access a public class in `com.acme.catalog.internal`, which is not exported to the application module at runtime.

If a temporary runtime workaround is truly needed, the appropriate permission must be specified:

```shell
java \
  --module-path mods:out \
  --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
  -m com.acme.app/com.acme.app.Main
```

However, a more sustainable solution is to migrate the consumer to the public API or export the package when it is part of a supported contract. You should not depend on `internal` packages long-term.

Errors caused by binary access changes, such as changing a constructor from `public` to `private`, can also trigger `IllegalAccessError` without involving `exports`. Always read the exact error message and compare against the actual artifacts.

## 16. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `module not found: M` | Dependency module missing from module path or wrong name | Check module name and build dependencies |
| `module A does not read B` | Missing readability | Declare `requires B;` or review the module graph |
| `package P is not visible` | Package not exported to consumer or missing readability | Check `requires` and `exports` |
| `class X is not public` | Type lacks the `public` modifier | Use public API or fix visibility in the owning source |
| `constructor X() has private access` | Constructor is not accessible | Use a supported factory or public constructor |
| `method m() is not public` | Member lacks appropriate access | Use a public API instead |
| `InaccessibleObjectException` | Deep reflection is blocked | Check `opens` and framework configuration |
| `IllegalAccessError` at runtime | Bytecode and runtime access permissions mismatch | Compare descriptors, flags, JARs, and runtime |
| `reads package P from both M1 and M2` | Split package | Fix package/dependency structure, do not just add exports |

If code runs on the classpath but fails on the module path, do not open all packages wholesale with `open module`. Identify the exact error: readability, exports, Java visibility, reflection, or split package.

## 17. Designing Exported Packages as a Public Contract

Several principles help keep module boundaries clear:

1. **Export API packages intentionally.** Packages like `api`, `spi`, or `public` should only contain types that consumers are permitted to depend on.
2. **Keep internal packages unexported.** Public classes inside internal packages can serve intra-module collaboration or service providers without becoming a consumer contract.
3. **Do not export every package just to fix build errors.** Every export is a potential compatibility commitment to consumers.
4. **Restrict with qualified exports when appropriate.** Use `to` to specify collaborating modules instead of exposing a package to the entire module graph.
5. **Ensure a consistent API surface.** Public types must have public constructors/factories/methods matching supported use cases.
6. **Use `requires transitive` selectively.** Only propagate readability when exposing a dependency is part of the API.
7. **Separate reflection from API access.** `opens` for frameworks does not substitute for `exports` of an API.
8. **Maintain compile tests from a separate consumer module.** This catches closed packages or inaccessible APIs early.
9. **Test against the distributed artifacts.** Source code and module descriptors before packaging can differ from the final JAR.
10. **Document export changes in changelogs.** Removing or narrowing a package export can break source compatibility and runtime linkage even if the class still exists.

## 18. Practical Checklist

Before using a public type from another named module, check in order:

- [ ] Does the consumer use the exact **JPMS module name** in `requires`?
- [ ] Is the JAR containing the module present on the module path and resolved?
- [ ] Does the provider module export **the exact package** containing the type?
- [ ] If the export uses `to`, is the consumer included in the target module list?
- [ ] Is the top-level/nested type truly accessible under Java rules?
- [ ] Do the constructor, fields, and methods to be used have valid visibility?
- [ ] If the public API includes types from another module, is readability handled appropriately?
- [ ] If deep reflection is needed, has `opens` been considered separately?
- [ ] Are compiler and runtime using the same artifacts and module descriptors?
- [ ] Are there any split package conflicts or duplicate module names?

**Conclusion:** `public` and `exports` are two halves of API access in JPMS, while `requires` provides module readability. A type can only be validly used by a consumer when the module graph, package boundaries, and Java visibility all allow it. Designing exported packages as explicit API contracts helps modular applications reduce implementation coupling and avoid hard-to-diagnose access errors during library upgrades.