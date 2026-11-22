# Splitting Packages by API and Implementation

## 1. The Goal of Separating API and Implementation

The Java Platform Module System (JPMS) allows a module to selectively expose packages via the `exports` directive. As a result, a module author can distinguish the **public contract** that external applications are allowed to use from the **internal implementation** that can change without breaking consumer code.

If you place both the API and the implementation in the same exported package, every public type in the package can be referenced by consumers according to Java and JPMS access rules. This makes it easy for consumers to depend directly on classes that the developer intended for internal use only.

Example of a structure that easily creates coupling:

~~~text
com.acme.inventory/
├── InventoryService.java
├── JdbcInventoryService.java
├── ProductRepository.java
└── ConnectionFactory.java
~~~

When the descriptor declares:

~~~java
module com.acme.inventory {
    exports com.acme.inventory;
}
~~~

both `InventoryService` and the `public` implementation classes in this package fall within the export scope. JPMS does not have an `exports` directive for individual classes.

A more appropriate organization:

~~~text
com.acme.inventory.api
com.acme.inventory.internal
~~~

And:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

Consumers only need to depend on the contract. The implementation can be replaced while keeping the API unchanged.

## 2. Categorizing Packages by Responsibility

You can start with the following groups:

| Group | Role | Example |
|---|---|---|
| API | Contract for code using the module | `com.acme.inventory.api` |
| Implementation | Classes implementing contracts, internal algorithms | `com.acme.inventory.internal` |
| Persistence | Repositories, database mappings, JDBC adapters | `com.acme.inventory.internal.persistence` |
| SPI | Contract for provider/extension authors | `com.acme.inventory.spi` |
| Integration | Contracts/adapters used for specialized integration | `com.acme.inventory.integration` |

An API package can contain interfaces, abstract classes, records/DTOs, enums, public exceptions, and a facade or factory. Not all public APIs have to be interfaces.

An implementation package typically contains concrete classes, caches, mappers, connection factories, repositories, adapters, and helpers that consumers do not need to know about.

Names like `api`, `spi`, and `internal` are merely naming conventions. **The real boundary is determined by the module descriptor and Java access rules.** If you name a package `internal` yet still `exports` it, JPMS will still allow access according to the export rules.

## 3. A Single Module Containing Both API and Implementation

For a small library, it is not yet necessary to split into two modules. You can separate packages right inside a single module:

~~~text
inventory/
└── src/main/java/
    ├── module-info.java
    └── com/acme/inventory/
        ├── api/
        │   ├── InventoryService.java
        │   └── InventoryServices.java
        └── internal/
            └── InMemoryInventoryService.java
~~~

Descriptor:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

Public contract:

~~~java
package com.acme.inventory.api;

public interface InventoryService {
    String findName(String sku);
}
~~~

Internal implementation:

~~~java
package com.acme.inventory.internal;

import com.acme.inventory.api.InventoryService;
import java.util.Map;

public final class InMemoryInventoryService
        implements InventoryService {

    private final Map<String, String> products =
            Map.of("SKU-1", "Notebook", "SKU-2", "Keyboard");

    @Override
    public String findName(String sku) {
        return products.getOrDefault(sku, "Not found");
    }
}
~~~

Public factory:

~~~java
package com.acme.inventory.api;

import com.acme.inventory.internal.InMemoryInventoryService;

public final class InventoryServices {

    private InventoryServices() {
    }

    public static InventoryService createDefault() {
        return new InMemoryInventoryService();
    }
}
~~~

Within the same named module, code in different packages can still use internal public classes according to Java rules. That does not mean external consumer modules are allowed to access the internal package.

The factory in this example performs wiring. In a larger architecture, implementation selection can be placed in a separate composition root so that the API module does not depend back on the implementation.

## 4. Consumers Only See the Contract

Consumer module:

~~~java
module com.acme.checkout {
    requires com.acme.inventory;
}
~~~

Application:

~~~java
package com.acme.checkout;

import com.acme.inventory.api.InventoryService;
import com.acme.inventory.api.InventoryServices;

public final class Main {

    public static void main(String[] args) {
        InventoryService service =
                InventoryServices.createDefault();

        System.out.println(service.findName("SKU-1"));
    }
}
~~~

The consumer does not import the implementation class. It only uses types present in the exported API package.

If the consumer tries:

~~~java
import com.acme.inventory.internal.InMemoryInventoryService;
~~~

the compiler may report:

~~~text
package com.acme.inventory.internal is not visible
(package com.acme.inventory.internal is declared in module
 com.acme.inventory, which does not export it)
~~~

This message illustrates the difference between:

- `public`: accessibility of a type under Java language rules.
- `requires`: readability of a module dependency.
- `exports`: accessibility of public types of a package across the module boundary.

Even though `InMemoryInventoryService` is `public`, another named module still cannot use it as public API when the package containing the class is not exported.

## 5. exports Is Not Applied Recursively

If the descriptor declares:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

then the package `com.acme.inventory.api.internal` is **not automatically exported**. Java does not treat subpackages as part of the parent package for access control.

Similarly, `exports com.acme.inventory` does not export every package with the prefix `com.acme.inventory.*`.

To export multiple packages, each package must be listed explicitly:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
    exports com.acme.inventory.events;
}
~~~

There is no wildcard syntax:

~~~java
// Invalid syntax:
exports com.acme.inventory.*;
~~~

Because JPMS exports at the package level, determine from the start which packages contain public types that are genuinely supported long-term. Do not place implementation classes in an API package and hope for another keyword to hide them.

## 6. Avoiding Leaking Implementations Through Public Signatures

A subtle design flaw is placing an interface in the API package while having a method return a type from the implementation package:

~~~java
package com.acme.inventory.api;

import com.acme.inventory.internal.SqlProductEntity;

public interface InventoryService {
    SqlProductEntity find(String sku);
}
~~~

Even though the API package is exported, consumers are still coupled to `SqlProductEntity`, an unexported internal type.

A better approach is to define the exchange data in the API:

~~~java
package com.acme.inventory.api;

public record ProductView(String sku, String name) {
}
~~~

Then:

~~~java
package com.acme.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

The implementation converts the database entity to `ProductView` before returning the result.

When evaluating a public API, check:

1. Return types and parameter types.
2. Generic arguments, such as `List<ProductView>`.
3. Checked exceptions in `throws`.
4. Superclasses/interfaces inherited by public types.
5. Annotations and other types in the contract that consumers need to compile against.

If an API returns `List<SqlProductEntity>` when the entity is only meant for persistence, changing the ORM or database can break consumers. A stable API should avoid exposing these implementation decisions.

## 7. Dependency Direction Between API and Implementation

A maintainable design usually follows:

~~~text
consumer  ----->  API contract  <-----  implementation
~~~

Meaning:

- Consumers know the contract, without needing to know the concrete implementation.
- Implementations implement the contract.
- A composition root, factory, or service-discovery mechanism decides which implementation is used.

In a single-module design, a factory located in the API package can use an implementation in the same module. For systems needing multiple interchangeable implementations, a multi-module model is usually clearer.

An API module should not `requires` an implementation module just to instantiate a specific object. If wiring is needed, move the responsibility of choosing a provider to a host/composition module or use `ServiceLoader`.

## 8. When Should You Split into an API Module and an Implementation Module?

Splitting modules is an appropriate choice when:

- Multiple teams or different systems share the same contract.
- There are multiple interchangeable backends: file, database, cloud storage, or in-memory.
- The application needs dynamic plugins or extensions.
- The implementation has heavy dependencies that the API should not carry.
- You want to release the API and implementation on separate lifecycles/versions.

Example structure:

~~~text
src/
├── com.acme.inventory.api/
│   ├── module-info.java
│   └── com/acme/inventory/api/InventoryService.java
├── com.acme.inventory.provider/
│   ├── module-info.java
│   └── com/acme/inventory/provider/internal/FileInventoryService.java
└── com.acme.checkout/
    ├── module-info.java
    └── com/acme/checkout/Main.java
~~~

The important point is that each module owns its own packages. Do not copy API classes into each provider JAR, as doing so can create split packages or different class identities when using separate class loaders/layers.

## 9. Public API Module

Descriptor:

~~~java
module com.acme.inventory.api {
    exports com.acme.inventory.api;
}
~~~

Service contract:

~~~java
package com.acme.inventory.api;

public interface InventoryService {
    String findName(String sku);
}
~~~

The API module does not know which provider will be installed. Callers using the interface only need `requires com.acme.inventory.api;`.

The API package should keep its number of dependencies as small and stable as possible. If a public signature must contain a type from another module, consider `requires transitive` when that accurately reflects the contract; do not add `transitive` for every internal dependency.

## 10. Provider Module and ServiceLoader

A provider module can register an implementation via JPMS service binding:

~~~java
module com.acme.inventory.provider {
    requires com.acme.inventory.api;

    provides com.acme.inventory.api.InventoryService
        with com.acme.inventory.provider.internal.FileInventoryService;
}
~~~

Implementation:

~~~java
package com.acme.inventory.provider.internal;

import com.acme.inventory.api.InventoryService;

public final class FileInventoryService
        implements InventoryService {

    public FileInventoryService() {
    }

    @Override
    public String findName(String sku) {
        return "File-backed: " + sku;
    }
}
~~~

Notes:

- The provider class resides in an unexported package.
- `provides ... with ...` registers the implementation with the service type.
- Consumers do not have to import or `requires` a specific provider module.
- The provider module needs `requires` on the API module to properly implement the service type.
- For `ServiceLoader` to instantiate a valid provider, the provider implementation package does not need to be exported.

For a named module using the service, the caller needs to declare `uses` for that service type.

## 11. Consumer Discovering the Implementation via the Service Contract

Consumer descriptor:

~~~java
module com.acme.checkout {
    requires com.acme.inventory.api;
    uses com.acme.inventory.api.InventoryService;
}
~~~

Code:

~~~java
package com.acme.checkout;

import com.acme.inventory.api.InventoryService;
import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        InventoryService service =
                ServiceLoader.load(InventoryService.class)
                        .findFirst()
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No InventoryService provider"));

        System.out.println(service.findName("SKU-1"));
    }
}
~~~

The host operates through `InventoryService`. It does not need to see the `FileInventoryService` class.

At runtime, the provider needs to be resolved into the module configuration. For example, if you want to add the provider as an explicit root module:

~~~bash
java --module-path mods \
  --add-modules com.acme.inventory.provider \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

This example does not impose a provider order when multiple implementations exist. If business logic needs to select a backend by name or priority, define an explicit selection mechanism rather than relying on `ServiceLoader` order.

## 12. Compiling the Multi-Module Example

With the `src/<module-name>/...` source layout above:

~~~bash
javac --module-source-path src \
  -d mods \
  -m com.acme.inventory.api,com.acme.inventory.provider,com.acme.checkout
~~~

Output:

~~~text
mods/
├── com.acme.inventory.api/
│   └── module-info.class
├── com.acme.inventory.provider/
│   └── module-info.class
└── com.acme.checkout/
    └── module-info.class
~~~

The `.class` files for the API, provider, and consumer are placed by the compiler into the corresponding package paths under each module directory.

Run:

~~~bash
java --module-path mods \
  --add-modules com.acme.inventory.provider \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

Illustrative output:

~~~text
File-backed: SKU-1
~~~

Note that using `--module-source-path` fits a source tree that has a subdirectory named after each module. If using a Maven/Gradle multi-project with `src/main/java` in each subproject, the build tool usually manages the output and module path instead of using this exact command.

## 13. SPI Is a Contract for Providers, Not an Implementation

If a system has a clear SPI, it can be divided as:

~~~text
com.acme.payment.api
com.acme.payment.spi
com.acme.payment.provider.internal
~~~

Where:

- `api` is for consumers calling the feature.
- `spi` is for providers or extensions implementing the feature.
- `provider.internal` contains the implementation that consumers should not import.

An SPI implemented by a provider in another module must also be exported appropriately:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
    exports com.acme.payment.spi;
}
~~~

If the SPI is only used by specific modules, qualified exports can be chosen. However, you should not hide the SPI interface in an unexported package and expect an independent provider module to implement it with normal code.

Conversely, the package containing the provider's implementation class usually does not need to be exported. Distinguishing the **provider contract** from the **provider implementation** gives the service architecture clear boundaries.

## 14. Qualified Exports for Specialized Integration Packages

Sometimes a package only needs to be exposed to a known adapter module:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;

    exports com.acme.inventory.integration
        to com.acme.inventory.adapter;
}
~~~

In that case, `com.acme.inventory.adapter` can access the eligible public types in the integration package if it also has readability. Other modules are not automatically granted that access.

Qualified exports are useful when:

- A package is an internal contract among a group of modules.
- You do not want to turn the package into public API for all consumers.
- Target module names are managed and stable.

If you have to list too many target modules, consider creating a dedicated API module for integration or redesigning the contract. Qualified exports do not replace compatibility management for the API they expose.

## 15. opens Is for Reflection, Not a Replacement for exports

A framework may need deep reflection into a model/entity package even though consumer code must not import the implementation.

Example:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;

    opens com.acme.inventory.internal.model
        to com.fasterxml.jackson.databind;
}
~~~

In the case above:

- The API package is exported so consumers can use public types.
- The model package is opened to a specific framework module.
- An open package does not automatically become an exported package for normal Java access.

Only open the exact package and the exact module performing reflection. If using JPA/Hibernate or another framework, the target module may not be Jackson; check the actual runtime configuration.

Avoid using `open module` for the entire module when only one package needs reflection. That widens the reflective access scope beyond the original need.

## 16. Avoiding Split Packages Between Named Modules

A common mistake when splitting modules is putting the same package `com.acme.inventory.common` into both the API module and the provider module:

~~~text
com.acme.inventory.api module:
    com.acme.inventory.common

com.acme.inventory.provider module:
    com.acme.inventory.common
~~~

JPMS configurations have strict rules regarding duplicate package names across modules. Splitting a package across two JARs can cause compilation or module resolution errors when those modules participate in the same module graph.

Separate packages clearly:

~~~text
com.acme.inventory.api
com.acme.inventory.provider.internal
~~~

Two packages sharing a common prefix but having different full names are valid. There is no requirement for each module to own a unique namespace prefix, but **a package with the same full name should not be split across multiple named modules**.

If shared types are needed, place them in the API module and let providers/consumers use the same class identity instead of copying classes.

## 17. Inspecting Exported Packages with JDK Tools

After building the modular JAR:

~~~bash
jar --describe-module --file build/libs/inventory.jar
~~~

Illustrative output:

~~~text
com.acme.inventory
requires java.base mandated
exports com.acme.inventory.api
contains com.acme.inventory.internal
~~~

`contains`, when shown by the tool, means the package is present in the module, not that the package is exported.

With module output on the module path:

~~~bash
java --module-path mods \
  --describe-module com.acme.inventory
~~~

You can check at runtime with the Module API:

~~~java
Module provider = InventoryService.class.getModule();
Module consumer = Checkout.class.getModule();

boolean readsProvider = consumer.canRead(provider);

boolean apiExported =
        provider.isExported("com.acme.inventory.api", consumer);

boolean internalExported =
        provider.isExported("com.acme.inventory.internal", consumer);
~~~

With explicit named modules where the descriptor only exports `api` and there are no launcher flags granting extra access, `apiExported` is typically `true` and `internalExported` is `false`. `readsProvider` depends on the readability relationship.

A useful architectural test is to write a consumer that tries to import an implementation class and confirm the compiler rejects it. That is a sign the module boundary is working as intended, not a bug to be fixed with `--add-exports`.

## 18. Anti-Patterns to Avoid

| Practice | Consequence |
|---|---|
| Placing public implementations in the same API package | Consumers can create direct coupling to concrete classes |
| Exporting a package named `internal` | Package naming no longer helps enforce encapsulation |
| Public API returning an internal persistence entity | Contract becomes tied to storage technology |
| API module `requires` the provider implementation module | Reverses the desired dependency direction |
| Copying API classes into each plugin/provider JAR | Easily causes split packages or class identity mismatches |
| Exporting the implementation package just for ServiceLoader to discover the provider | Unnecessary when `provides` is declared properly |
| Adding `--add-exports` everywhere so consumers can import internal | Weakens boundaries and increases maintenance difficulty |
| Using `open module` just because a framework needs one model package | Opens deep reflection scope too broadly |

JPMS provides tools to enforce boundaries, but choosing what constitutes the long-term contract remains a design responsibility of the development team.

## 19. Process for Transitioning a Legacy Library to an Encapsulated Design

When modularizing an old Java library:

1. List the packages currently imported by external projects.
2. Identify the public contract that needs continued support.
3. Move interfaces, DTOs/records, enums, and public exceptions into the API package.
4. Move repositories, database mappers, caches, and adapters into the implementation package.
5. Inspect API signatures to eliminate exposed implementation types.
6. Create `module-info.java` and export only supported packages.
7. Add qualified exports if there are special integration contracts.
8. Open packages with `opens` when a framework genuinely needs deep reflection.
9. If there are multiple implementations, consider an API module + provider modules + `ServiceLoader`.
10. Compile consumers on the module path to detect imports of internal packages.
11. Use `jar --describe-module` to verify the packaged descriptor.
12. Test service discovery, reflection, and business flows using the API.

You can use `jdeps` to assist with dependency analysis:

~~~bash
jdeps --list-deps build/libs/inventory.jar
~~~

Static analysis is only part of the picture. Dependencies used via reflection, ServiceLoader, or class names in configuration need to be verified with appropriate runtime tests.

## 20. Pre-Release Checklist

- [ ] API packages contain the stable contract that consumers need.
- [ ] Implementations and helpers reside outside exported packages.
- [ ] The descriptor exports only genuinely supported packages.
- [ ] Public types do not expose internal types in method signatures.
- [ ] Consumers only `requires` necessary API modules, without unwarranted implementation dependencies.
- [ ] Provider modules share the service type from the API module.
- [ ] `uses` and `provides` are accurate when using ServiceLoader.
- [ ] Provider implementation packages are not exported solely for service loading.
- [ ] Reflection is only opened via `opens` within the proper scope.
- [ ] There are no split packages between named modules.
- [ ] Descriptors of modular JARs and the module path have been inspected.
- [ ] Compiling a consumer using only the public contract has been tested.

## 21. Key Takeaways

**Splitting packages by API and implementation is the most practical step to leverage JPMS strong encapsulation.** API packages contain the types consumers are allowed to depend on; implementation packages contain details that can change independently.

For small libraries, a single module can contain both `api` and `internal` while exporting only `api`. For plugins or multiple interchangeable implementations, you can separate API and provider modules, then use ServiceLoader to discover implementations without exposing internal classes.

General rule: **consumers depend on the contract, implementations implement the contract, and the module descriptor exposes exactly the needed packages**. Package names communicate intent, while `requires`, `exports`, `opens`, and module graph relationships enforce that boundary.
