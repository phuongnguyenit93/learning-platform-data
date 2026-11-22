# Placing Public Types in the Appropriate Package

In the Java Platform Module System (JPMS), deciding which package to place a type with the public modifier in is an API design decision rather than just directory organization. A class can be public to Java code within the same module, yet still cannot be imported by other modules if the package containing it is not exported. Conversely, when a package is exported, every eligible public top-level type in that package can become part of the externally visible API surface.

To maintain strong encapsulation, clearly separate **packages meant for the public contract** from **packages meant for the implementation**. Export only packages containing types genuinely committed to users; keep helper classes, adapters, caches, mappers, and internal algorithms in unexported packages.

This lesson explains how to choose packages for public types, how to avoid exposing implementations through public signatures, and how to arrange module-info.java so the API remains stable as the project grows.

## 1. Being Public in Java Is Not Enough to Become Module API

Java has two layers related to accessibility:

1. **Java language access:** public, protected, package-private, and private control access at the class and member levels.
2. **JPMS module access:** requires determines readability, exports determines packages used as normal API, and opens determines deep reflection permissions at runtime.

Suppose a module has the descriptor:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

And contains two classes:

~~~java
package com.example.catalog.api;

public interface CatalogService {
    String productName(String sku);
}
~~~

~~~java
package com.example.catalog.internal;

public final class DefaultCatalogService
        implements com.example.catalog.api.CatalogService {
    @Override
    public String productName(String sku) {
        return "Product " + sku;
    }
}
~~~

DefaultCatalogService is public, yet the com.example.catalog.internal package is not exported. Code in another module is not permitted to import this class as normal public API, even though the class modifier is public.

Meanwhile, CatalogService resides in an exported package, so modules with appropriate readability can reference this interface.

This is the essential point: **a public type and an exported package are two separate conditions**.

## 2. Packages Are the Export Boundary, Not Individual Classes

In module-info.java, JPMS has no directive to export a single class on its own:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

The exports directive opens access to public types across the entire api package. It does not export only the one interface you happen to care about.

If you place a public implementation helper in the same package:

~~~java
package com.example.catalog.api;

public final class CacheResetUtility {
    public static void resetAll() {
        // Internal operation
    }
}
~~~

then another module can see CacheResetUtility alongside the other public APIs, provided access rules are satisfied. This does not necessarily mean the publisher commits to supporting it, yet mechanically JPMS has exposed it on the access surface.

If a class is not meant for consumers, there are two usually sensible options:

- Move the class to an unexported package, such as com.example.catalog.internal.
- If the class is only used within the same package, consider removing the public modifier so it becomes package-private.

Do not make types public merely for convenience and then hope module-info.java can hide individual types inside an exported package.

## 3. Designing Packages from the Consumer's Perspective

When choosing packages, start with the question: **what are other modules permitted to depend on long-term?**

A good API typically consists of:

- Interfaces or classes representing the published business behavior.
- Stable input, output, and exception types.
- Factories or entry points to create objects if consumers should not know the implementation.
- Annotations or extension points that consumers are allowed to use.

Parts that usually belong in internal packages:

- Repository implementations, caches, mappers, and helpers.
- Data structures serving internal algorithms.
- Adapters integrating specific libraries.
- Generated code not designed as a contract.
- Classes containing wiring logic and module-specific configuration.

Example layout:

~~~text
src/com.example.catalog/
├── module-info.java
└── com/example/catalog/
    ├── api/
    │   ├── CatalogService.java
    │   ├── ProductView.java
    │   └── CatalogServices.java
    ├── internal/
    │   ├── DefaultCatalogService.java
    │   └── ProductCache.java
    └── persistence/
        └── FileProductStore.java
~~~

Descriptor:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

As a result, external modules depend only on com.example.catalog.api. The owning module can replace the cache or persistence implementation without forcing consumers to change imports.

## 4. Bad Design Scenario: Implementation Inside the API Package

Suppose a project initially only has:

~~~text
com/example/payment/
├── PaymentService.java
├── PaymentServiceImpl.java
├── DatabaseConnectionHelper.java
└── RetryPolicy.java
~~~

All four types are declared public and the package is exported:

~~~java
module com.example.payment {
    exports com.example.payment;
}
~~~

Every public type in this package is visible to other modules. A consumer might start instantiating PaymentServiceImpl directly or calling DatabaseConnectionHelper.

Later, the development team wants to change the database or retry architecture. Replacing the implementation could break consumer code that has come to depend on types that should never have been API.

A more suitable structure:

~~~text
com/example/payment/
├── api/
│   ├── PaymentService.java
│   ├── PaymentRequest.java
│   └── PaymentServices.java
├── internal/
│   ├── DefaultPaymentService.java
│   └── RetryPolicy.java
└── persistence/
    └── DatabaseConnectionHelper.java
~~~

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

The goal is not to minimize the number of public types at all costs, but to clearly separate **public to internal code** from **public API meant for other modules**.

## 5. Public Implementations in Unexported Packages Are Still Useful

Sometimes an implementation needs to be used from another package within the same module. In that case, the class may need to be public under Java language rules.

For example:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public String pay(String reference) {
        return "OK:" + reference;
    }
}
~~~

And a factory in the api package:

~~~java
package com.example.payment.api;

import com.example.payment.internal.DefaultPaymentService;

public final class PaymentServices {
    private PaymentServices() {
    }

    public static PaymentService create() {
        return new DefaultPaymentService();
    }
}
~~~

Even though DefaultPaymentService is public, it does not become a type that external consumers can import via JPMS because the internal package is not exported.

Other modules only use:

~~~java
import com.example.payment.api.PaymentService;
import com.example.payment.api.PaymentServices;

PaymentService service = PaymentServices.create();
System.out.println(service.pay("INV-001"));
~~~

This keeps consumers depending on the interface and factory rather than being coupled to instantiation details or the current implementation.

## 6. Public Signatures Must Use Types Accessible to Consumers

A common design mistake is placing an interface in an exported package yet using an internal type in a public method signature.

For example:

~~~java
package com.example.order.api;

import com.example.order.internal.OrderData;

public interface OrderService {
    OrderData load(String id);
}
~~~

OrderData only exists in an unexported internal package. Consumers can see the OrderService interface, yet encounter difficulties or compile errors when trying to use the OrderData return type.

The improvement is to move the contract data type to the API package:

~~~java
package com.example.order.api;

public record OrderView(String id, String status) {
}
~~~

~~~java
package com.example.order.api;

public interface OrderService {
    OrderView load(String id);
}
~~~

If the implementation needs a separate OrderData structure, convert it to OrderView at the API boundary.

This rule also applies to:

- Parameter types of public methods and public constructors.
- Return types, generic type parameters, and generic bounds.
- Exceptions declared as part of the contract.
- Public fields, superclasses, and interfaces that consumers must reference.
- Public nested types appearing in externally used signatures.

Do not inspect only types declared public; examine the **entire type graph appearing in the public API**.

## 7. Designing API DTOs or Records

Data types appearing in the contract should be placed in a package with a clear name and purpose, such as api, model, or contract, depending on team conventions.

For example:

~~~java
package com.example.inventory.api;

public record ProductView(
        String sku,
        String displayName,
        int availableQuantity) {
}
~~~

~~~java
package com.example.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

Descriptor:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Consumers can use ProductView without knowing internal entity or cache types.

Records are well suited for immutable data exposed by value when they fit business requirements. However, not every entity or complex object must be turned into a record. The goal is to choose stable contract types that do not leak persistence or framework details.

When designing DTOs, consider compatibility if public components or constructors change. Placing them in the API package means future changes can affect consumers.

## 8. API Packages and Internal Packages Do Not Require One Fixed Name

There is no mandatory rule forcing every project to use the .api or .internal suffixes.

All of these naming approaches can be reasonable:

~~~text
com.example.billing.api
com.example.billing.contract
com.example.billing.spi
com.example.billing.internal
com.example.billing.persistence
com.example.billing.adapter
~~~

What matters is clear semantics:

- Packages containing types meant for consumers need to be documented as contracts.
- Internal packages should not be exported if external modules do not need to use them directly.
- An spi package meant for a Service Provider Interface must be designed carefully because external providers may need to implement types there.
- A model package could be API or internal; do not infer solely from the name model.

Do not turn package naming into the sole access control mechanism. It is module-info.java that determines which packages are exported at the JPMS level.

## 9. When the API Needs Types from Another Module

A public API may depend on a type residing in another named module. For example, the catalog library returns a Result type from a shared contract module.

Contract module:

~~~java
module com.example.contract {
    exports com.example.contract;
}
~~~

~~~java
package com.example.contract;

public record Result<T>(T value, boolean success) {
}
~~~

Catalog module:

~~~java
module com.example.catalog {
    requires transitive com.example.contract;
    exports com.example.catalog.api;
}
~~~

API:

~~~java
package com.example.catalog.api;

import com.example.contract.Result;

public interface CatalogService {
    Result<String> lookup(String sku);
}
~~~

requires transitive ensures any module reading com.example.catalog can also read com.example.contract under JPMS rules. This is appropriate when the catalog's public API requires types from contract.

If catalog only uses a dependency in its internal implementation and does not expose that dependency's types in the public contract, a regular requires is usually better than requires transitive.

Do not overuse transitive for every dependency. It increases the readability relationships inherited by consumers and couples the dependency more tightly to the API module.

## 10. Qualified Exports for Designated Partners

There are types that are not general API for all consumers yet need to be used by a specific integration module.

For example:

~~~java
module com.example.billing {
    exports com.example.billing.api;

    exports com.example.billing.integration
        to com.example.billing.bridge;
}
~~~

The integration package is exported specifically to com.example.billing.bridge, not to every other named module.

Qualified exports can be useful for:

- Adapter modules managed within the same product.
- A communication API between two modules in a large system.
- Specialized integrations not yet intended for wide publication.

However, this is not a security boundary against arbitrary code or all JVM configurations. It is an accessibility control mechanism in JPMS. For third-party APIs, consider the extensibility of the target module list and contract stability.

Do not use qualified exports as a way to hide a messy package design where dozens of implementation helpers sit alongside API types. Clean package organization remains foundational.

## 11. Opens Does Not Replace Exports

A serialization framework or ORM may need deep reflection into private fields of entities. In that case, the package containing entities may need opens:

~~~java
module com.example.billing {
    exports com.example.billing.api;

    opens com.example.billing.entity
        to com.example.persistence.framework;
}
~~~

This allows the framework to perform deep reflection on entities within the specified module scope. It does **not** make the entity package a normal API package for all clients to import.

Distinction:

| Directive | Purpose |
| --- | --- |
| exports p | Allows using public types of package p through normal Java access. |
| exports p to m | Exports package p only to module m. |
| opens p | Opens package p for deep reflection at runtime. |
| opens p to m | Opens package p for deep reflection from module m. |

If a client needs to compile code calling a public type, look at requires and exports. If a framework needs to read private state via reflection, look at opens.

Do not export an implementation package just because a serializer cannot access private fields; likewise, do not unnecessarily open an API package just to fix source import errors.

## 12. Public Top-Level Types and Java Language Rules

In Java, a top-level type can be public or package-private. For standard source files, the filename of a public top-level class/interface must match the public type's name.

For example:

~~~java
package com.example.catalog.internal;

final class CacheKey {
    private final String value;

    CacheKey(String value) {
        this.value = value;
    }
}
~~~

CacheKey is not public, so only classes in the same package can directly access it under Java's package-private rules.

Another class in the same module but in a different package will not be able to import CacheKey just because they are in the same module. **JPMS does not eliminate Java's access modifiers.**

If an implementation needs to be used by multiple packages within the same module, you can create a public type in an unexported package, or design a controlled internal access point. Also consider keeping the internal API small rather than making every helper public for convenience.

## 13. Public Nested Types and Enclosing Types

A nested class or nested interface can be public, yet external accessibility still depends on the enclosing type, package, and module.

For example:

~~~java
package com.example.catalog.api;

public final class CatalogOptions {
    public enum Mode {
        STRICT,
        LENIENT
    }

    private CatalogOptions() {
    }
}
~~~

If the api package is exported and readability conditions are satisfied, consumers can use CatalogOptions.Mode.

Conversely, a public nested type inside a top-level type that is inaccessible from other modules does not automatically become useful public API for consumers.

When designing public nested types, consider how consumers write imports and call the API. Do not surface an internal nested type in an API signature just because it has the public modifier.

## 14. Avoiding Split Packages Between Named Modules

JPMS is incompatible with multiple named modules providing the same package in the same module graph and related class-loading environment. Splitting a package across multiple modules can cause resolution or configuration errors.

Example of a design to avoid:

~~~text
module com.example.catalog.api
└── package com.example.catalog.shared

module com.example.catalog.impl
└── package com.example.catalog.shared
~~~

They should be organized into separate packages by responsibility:

~~~text
com.example.catalog.api
com.example.catalog.internal
com.example.catalog.persistence
~~~

Each package belongs to an appropriate module in the configuration. If two modules need the same contract type, consider placing that type in a shared API module instead of duplicating the same package across multiple modules.

This also reduces class identity risks and dependency conflicts when adding plugins or module layers.

## 15. Avoiding Leaking Framework Classes in the API

Another design error is placing an API class in the right package yet letting its signature depend on a framework-specific type:

~~~java
package com.example.payment.api;

public interface PaymentService {
    FrameworkSession beginPayment();
}
~~~

If FrameworkSession is an implementation detail of an ORM or HTTP framework, consumers may be forced to depend on that framework just to call the business API.

A more independent contract:

~~~java
package com.example.payment.api;

public record PaymentTicket(String reference, String status) {
}
~~~

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentTicket beginPayment();
}
~~~

The implementation can convert between PaymentTicket and the framework object inside the internal package.

Exposing external types is not always wrong: a library dedicated to providing integration may intentionally expose framework types. However, that must be an intentional design choice, documented and managed for compatibility.

## 16. API and SPI Are Two Different Surfaces

API serves consumers; SPI serves providers of implementations or plugins.

For example:

~~~text
com.example.report.api
com.example.report.spi
com.example.report.internal
~~~

An SPI interface can be exported so plugin modules can implement it:

~~~java
module com.example.report {
    exports com.example.report.api;
    exports com.example.report.spi;
    uses com.example.report.spi.ReportProvider;
}
~~~

A provider module can declare:

~~~java
module com.example.report.pdf {
    requires com.example.report;

    provides com.example.report.spi.ReportProvider
        with com.example.report.pdf.PdfReportProvider;
}
~~~

The API module can use ServiceLoader to discover providers. Note that the package containing the PdfReportProvider implementation does not have to be exported merely to supply the provider via provides.

Placing the SPI in a separate package helps clarify that it is a contract for system extenders, which not every consumer needs to use. This convention also supports clearer documentation and API evolution.

## 17. Designing Packages for Libraries Used on Both JPMS and the Classpath

When the same JAR can be used on the module path or the classpath, remember:

- On the module path, JPMS enforces the exports/opens boundaries of the named module.
- On the classpath, classes belong to the unnamed module and the exports boundaries of the modular descriptor do not operate under the same mechanism as when the JAR is a named module.
- Java's public/package-private modifiers still apply in both models.

Therefore, an unexported package should not be treated as an absolute secret across every runtime environment. The goal of encapsulation design is **clear dependency contracts and maintainability**, not security isolation against untrusted code in the same process.

If a library is released for both modular and non-modular applications, still maintain a clean API/internal package design. Public API documentation should stay consistent, even when the classpath allows broader access.

## 18. Process for Moving a Public Type to the Appropriate Package

Suppose clients previously used:

~~~java
import com.example.catalog.DefaultCatalogService;
~~~

After redesigning, the development team wants consumers to depend on CatalogService in the api package.

This can be an incompatible change for existing client code. Because a type's full name includes its package, moving a type to a new package changes its binary name.

A safe process:

1. Identify which types are true API and which types are implementation.
2. Inspect all public methods, constructors, generic types, and exceptions in the contract.
3. Design the api or contract package and corresponding module exports.
4. Move public interfaces, DTOs, and factories to the new package.
5. Keep implementations in unexported internal packages.
6. Update clients to use the new API.
7. If the library already has users, consider adapters or deprecated forwarding types to manage compatibility.
8. Compile and run consumers in a separate module to confirm the contract is usable.

For a published library, packages should not be moved silently. Both source compatibility and binary compatibility need to be considered.

Not every type should change packages immediately. An old public facade can be kept during a transition period and then removed according to the project's versioning policy.

## 19. Complete Example: Separating API and Implementation

Project layout:

~~~text
src/
├── com.example.inventory/
│   ├── module-info.java
│   └── com/example/inventory/
│       ├── api/
│       │   ├── InventoryService.java
│       │   ├── ProductView.java
│       │   └── InventoryServices.java
│       └── internal/
│           └── InMemoryInventoryService.java
└── com.example.cli/
    ├── module-info.java
    └── com/example/cli/Main.java
~~~

Inventory descriptor:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Public DTO:

~~~java
package com.example.inventory.api;

public record ProductView(String sku, String name) {
}
~~~

Service interface:

~~~java
package com.example.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

Implementation in internal package:

~~~java
package com.example.inventory.internal;

import com.example.inventory.api.InventoryService;
import com.example.inventory.api.ProductView;
import java.util.Optional;

public final class InMemoryInventoryService
        implements InventoryService {

    @Override
    public Optional<ProductView> find(String sku) {
        if ("P-100".equals(sku)) {
            return Optional.of(new ProductView("P-100", "Notebook"));
        }
        return Optional.empty();
    }
}
~~~

Factory in API package:

~~~java
package com.example.inventory.api;

import com.example.inventory.internal.InMemoryInventoryService;

public final class InventoryServices {
    private InventoryServices() {
    }

    public static InventoryService inMemory() {
        return new InMemoryInventoryService();
    }
}
~~~

Client descriptor:

~~~java
module com.example.cli {
    requires com.example.inventory;
}
~~~

Client:

~~~java
package com.example.cli;

import com.example.inventory.api.InventoryService;
import com.example.inventory.api.InventoryServices;

public class Main {
    public static void main(String[] args) {
        InventoryService inventory = InventoryServices.inMemory();
        System.out.println(inventory.find("P-100"));
    }
}
~~~

The client only imports types from the api package. Having the implementation be public does not make it a published API because the internal package is not exported.

## 20. Compiling the Modular Example

With the module-source-path layout above, you can compile:

~~~bash
javac --module-source-path src \
    -d out \
    -m com.example.inventory,com.example.cli
~~~

Run the application:

~~~bash
java --module-path out \
    -m com.example.cli/com.example.cli.Main
~~~

On Windows, single-line commands can be used:

~~~powershell
javac --module-source-path src -d out -m com.example.inventory,com.example.cli
java --module-path out -m com.example.cli/com.example.cli.Main
~~~

If the client tries to directly import com.example.inventory.internal.InMemoryInventoryService, the modular application's compiler will reject access to the internal package because this package is not exported to com.example.cli.

This is a practical way to verify whether the API boundary matches the module descriptor.

## 21. Tools for Inspecting Module APIs

Some tools in the JDK:

~~~bash
jar --describe-module --file libs/inventory.jar
~~~

This command shows the JAR's module descriptor, including the module name and corresponding exports.

~~~bash
java --describe-module java.sql
~~~

This command describes the system module java.sql, useful for observing how a module exposes packages.

~~~bash
jdeps --module-path libs --check com.example.inventory
~~~

jdeps assists in analyzing requires and dependencies related to the module descriptor. Depending on packaging, pass the appropriate module path or JAR.

These tools help find module names and exported packages. However, deciding which types should become public API must still be based on the usage contract and architectural requirements.

## 22. Common Mistakes in Encapsulation Design

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Public type cannot be imported from another module | Package containing the type is not exported or readability is missing | Check requires and exports; export only if the type is genuinely API. |
| Consumer can import an implementation helper | Public helper resides in an exported package | Move the helper to an unexported package or reduce visibility. |
| API method uses internal type in signature | Contract exposes a type consumers cannot access | Use a public DTO/interface in the API package. |
| Package conflict when assembling modules | Split package or duplicate package in an unsuitable configuration | Separate packages by module and use one shared contract module. |
| Framework reflection fails | Package needs deep reflection but is not opened | Grant qualified opens on the exact package to the framework if truly needed. |
| Changing packages breaks client compilation | Binary name/import of public type changed | Manage migration and compatibility intentionally. |
| Package named internal is still used by consumers on classpath | Package name alone does not enforce access control | Separate contracts clearly; enforce via modifiers and exports when running modularly. |

## 23. Key Rules When Placing Public Types

- Place public interfaces, DTOs, factories, and exceptions in packages matching the module's contract.
- Export only packages meant for consumers; do not export the whole module for convenience.
- Do not let public signatures require types in unexported packages.
- Check dependencies appearing in public signatures and consider requires transitive if the API needs to propagate readability.
- Keep implementations, caches, mappers, and persistence helpers in unexported packages.
- Public implementations in internal packages can be used if multiple packages in the same module genuinely need them.
- Use qualified exports for integration APIs with a clear target scope.
- Use opens for deep reflection; do not treat opens as a way to publish normal APIs.
- Avoid split packages across named modules in the same configuration.
- Treat moving a public type between packages as a contract change requiring compatibility management.

## 24. Self-Check Questions

**Question 1:** A public class resides in com.example.billing.internal, yet the module only exports com.example.billing.api. Can another module import that internal class?

Not under standard JPMS access. A class's public modifier does not replace the package being exported.

**Question 2:** If an exported package has three public classes, can JPMS specify exporting only one class among them?

No. exports applies to the package. Reorganize packages or adjust visibility if you only want to expose a subset.

**Question 3:** An API interface returns an unexported InternalOrder type. What is wrong with this design?

Consumers may be unable to use the type in the signature. Expose a contract interface or DTO in the API package and convert from the internal type inside the module.

**Question 4:** A package containing entities needs an ORM to read private fields. Should you add exports or opens?

When only deep reflection is needed, opens scoped to the ORM module is usually appropriate; exports is for normal public API access.

**Question 5:** When should requires transitive be used?

When a module exposes an API depending on types from another module and wants consumers to read that dependency through the module contract. If the dependency is only an implementation detail, regular requires is usually better.

**Question 6:** Is a public class in an internal package always a design mistake?

No. It may need to be called from another package within the same module. What matters is that the internal package is not exported to external consumers if the class does not belong to the API contract.

**Question 7:** Why can changing a public type's package break compatibility?

Because a type's full name includes the package name. Changing the package changes the name referenced by client source code and bytecode, so a migration strategy is needed.
