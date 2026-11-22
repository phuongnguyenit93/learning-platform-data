# Minimal Exports for the Public Surface

## Objectives

After this lesson, you will be able to design the API boundary of a named module by exporting only the packages that need to be public, distinguish Java public access from module-level access, use qualified exports when restricting consumers is needed, choose `requires transitive` when the public API depends on types from another module, and inspect the module descriptor before release.

## 1. Public in Java Does Not Automatically Mean Public Across Modules

In Java, the `public` keyword controls access at the class/member level. With JPMS, a named module also controls which packages are exposed to other modules via the `exports` directive.

For example, a class can be declared `public`:

~~~java
package com.acme.billing.internal;

public final class PricingEngine {
    public Money calculate(Order order) {
        // ...
        return Money.zero();
    }
}
~~~

However, if the package `com.acme.billing.internal` is not exported in `module-info.java`, other modules cannot use this class merely because the class has the `public` modifier.

There are two distinct layers of control:

- **Java access control**: `public`, `protected`, package-private, and `private` determine who can access classes/members according to language rules.
- **Module access control**: `exports` determines which packages can be accessed by other modules through the module graph and readability.

For another module to use a public type in an exported package, both conditions are generally required: the consumer module reads the module owning the package, and the package is exported to that consumer.

Therefore, a module's public surface is formed from the packages that the module actively exports, together with the public/protected APIs inside those packages. Marking a class as `public` does not automatically place it in the module's public surface.

## 2. `exports` Operates at the Package Level

Syntax:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

This directive exports the entire `com.acme.billing.api` package to other modules that have readability to `com.acme.billing`. JPMS does not have syntax to export individual classes separately. Therefore, when a package is exported, all public types in that package can become part of the API used by consumers.

Example module structure:

~~~text
com.acme.billing/
  module-info.java
  com/acme/billing/api/
    BillingService.java
    Invoice.java
    PaymentStatus.java
  com/acme/billing/internal/
    PricingEngine.java
    InvoiceRepository.java
  com/acme/billing/adapter/
    SqlInvoiceRepository.java
~~~

Descriptor:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Public classes in `com.acme.billing.api` can be used by other modules if the consumer reads module `com.acme.billing`. The `internal` and `adapter` packages are not exported and thus remain encapsulated at the module level.

This is why packages should be split along API and implementation boundaries. If the API and implementation sit in the same exported package, public implementation classes will also be accessible to consumers.

## 3. Designing a Small and Stable API Package

Create a package dedicated to the types that consumers actually need:

~~~java
package com.acme.billing.api;

public interface BillingService {
    Invoice createInvoice(OrderRequest request);
}
~~~

~~~java
package com.acme.billing.api;

public record OrderRequest(String customerId, long amountInCents) {
}
~~~

~~~java
package com.acme.billing.api;

public record Invoice(String id, long amountInCents) {
}
~~~

Module descriptor:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

The implementation resides in an unexported package:

~~~java
package com.acme.billing.internal;

import com.acme.billing.api.BillingService;
import com.acme.billing.api.Invoice;
import com.acme.billing.api.OrderRequest;

public final class DefaultBillingService implements BillingService {
    @Override
    public Invoice createInvoice(OrderRequest request) {
        // Validate, calculate and persist the invoice.
        return new Invoice("INV-001", request.amountInCents());
    }
}
~~~

If other modules need to create the service, provide a public factory or composition root instead of exporting the entire implementation package just so consumers can call an internal constructor.

Example factory API:

~~~java
package com.acme.billing.api;

public final class BillingServices {
    private BillingServices() {
    }

    public static BillingService createDefault() {
        return new com.acme.billing.internal.DefaultBillingService();
    }
}
~~~

In practice, having the API package directly reference an implementation package can make API code depend on internal details. You can place the factory in an implementation module, use a service provider, or use internal dependency injection to keep the API package more independent. What matters is that consumers only need to know the stable contract.

## 4. Do Not Export a Package Just Because It Has Public Classes

Before adding `exports`, determine which types consumers need and why they need them.

For example, do not export all three packages just because they contain public classes:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.internal;
    exports com.acme.billing.adapter;
}
~~~

If consumers only need `BillingService`, `Invoice`, and `OrderRequest`, the two implementation packages should not be in the public surface. Exporting them allows consumers to depend on concrete implementation classes, repositories, or adapters.

That creates hard-to-change constraints:

- Consumers can instantiate the implementation directly.
- Consumers can call methods intended only for internal use.
- Renaming packages or replacing implementation classes can break consumer code.
- Implementation dependencies can leak into the API.
- The module becomes harder to swap adapters in or refactor internally.

A package should only be exported when the module is willing to commit that its public types are supported integration points.

## 5. Qualified Exports to Restrict Consumers

If a package is intended only for one or a few specific modules, use a qualified export:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.spi to com.acme.reporting;
}
~~~

In the example:

- `com.acme.billing.api` is exported without restricting target modules.
- `com.acme.billing.spi` is exported only to the `com.acme.reporting` module.

The target module must still have readability to the source module, usually via:

~~~java
module com.acme.reporting {
    requires com.acme.billing;
}
~~~

Qualified exports are useful when there is an SPI or integration package meant only for a companion module. They help avoid turning that package into public API for every consumer.

If a package is exported to a specific target module, other modules do not gain access to public types in that package simply by adding `requires`. Both readability and the export target must match.

Qualified exports are not a security mechanism replacing runtime authentication or data access control. They are a module-level access boundary.

## 6. Public API Referencing Types from Another Module

An important decision is which dependencies appear in the public signature of the API.

Suppose module `com.acme.money` provides the `Money` type:

~~~java
module com.acme.money {
    exports com.acme.money.api;
}
~~~

~~~java
package com.acme.money.api;

public record Money(long cents) {
}
~~~

The billing module uses that type in its API:

~~~java
package com.acme.billing.api;

import com.acme.money.api.Money;

public interface BillingService {
    Money totalFor(String customerId);
}
~~~

Billing's descriptor:

~~~java
module com.acme.billing {
    requires transitive com.acme.money;
    exports com.acme.billing.api;
}
~~~

The consumer only needs to declare:

~~~java
module com.acme.client {
    requires com.acme.billing;
}
~~~

Thanks to `requires transitive com.acme.money`, a module reading `com.acme.billing` also gains readability to `com.acme.money`. The consumer can use `Money` in its signatures and code without declaring an extra `requires com.acme.money`.

If billing only declares:

~~~java
requires com.acme.money;
~~~

then this dependency is not propagated to modules reading billing. Consumers may need to declare `requires com.acme.money` directly to use the `Money` type in the API.

Practical rule: use `requires transitive` when your module exposes types from that dependency in an API that consumers need to read. Do not use `transitive` for every dependency by default, because that increases the readability graph of dependent modules and can unintentionally widen public dependencies.

## 7. Distinguishing `exports` from `opens`

These two directives serve two different types of access:

| Directive | Purpose | Usage Example |
| --- | --- | --- |
| `exports` | Allows other modules to access public APIs in the package | Consumer calls public services and DTOs |
| `opens` | Allows deep reflection into the package at runtime | ORM or serializer accesses private fields |

Example:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    opens com.acme.billing.persistence to org.example.orm;
}
~~~

The API package is exported for normal Java access. The persistence package is opened to the named ORM module to perform deep reflection.

Opening a package does not make the package a public API for consumers to compile against. Exporting a package also does not automatically allow frameworks to access private members via deep reflection. If both permissions are needed, both `exports` and `opens` must be declared for their respective purposes.

## 8. How the Public Surface Affects Module Evolvability

An exported package is a design commitment. Once consumers start compiling and running against public types in that package, API changes can affect other modules.

Some principles to reduce maintenance costs:

- Keep the public API small, placed in a dedicated package.
- Prefer interfaces and business-meaningful data types over exposing implementation classes.
- Do not let the API return or accept parameters whose types reside in unexported implementation packages.
- Do not expose framework-specific types if the module does not want to publicly depend on that framework.
- Use qualified exports for internal SPIs that need to be shared with a defined group of modules.
- Use `requires transitive` intentionally when types from a dependency appear in the API.
- Treat removing or renaming an exported package as a change that can break consumers.

If you need to change the implementation, keep the API contract stable and change classes inside the module. This is a major benefit of module encapsulation.

## 9. Avoiding Split Packages and Ambiguous Boundaries

A package should belong to one clear module in the module graph. Avoid placing classes with the same package name in multiple different modules, because split packages make class resolution and loading unpredictable and are generally rejected by the module system within the same configuration.

Example of a design to avoid:

~~~text
com.acme.billing.api/
  BillingService.class     (module com.acme.billing.api)
  Invoice.class            (module com.acme.billing.model)
~~~

Group types belonging to the same package into one module, or rename packages to reflect real boundaries:

~~~text
com.acme.billing.api/
  BillingService.class
  Invoice.class
~~~

Also, do not create a `com.acme.billing.internal` package in another module just to place implementations close to the API package name. Choose a distinct package name for the module that owns the implementation.

## 10. Inspecting the Public Surface and Dependencies

You can read the descriptor of a modular JAR:

~~~bash
jar --describe-module --file mods/com.acme.billing.jar
~~~

The output shows the module name, along with any `requires`, `exports`, `opens`, `uses`, and `provides`. Confirm that only the intended packages appear in the exports section.

Use `jdeps` to analyze module and API dependencies:

~~~bash
jdeps --module-path mods --api-only --module com.acme.billing
~~~

`--api-only` focuses on analyzing dependencies that appear in the public API. This is a useful way to detect dependencies that may need `requires transitive` or implementation dependencies leaking into the public surface.

You can check the module descriptor and dependency graph with:

~~~bash
jdeps --module-path mods --check com.acme.billing
~~~

Analysis commands help find dependencies and descriptors to review; the decision to export a package must still be based on the API contract the module intends to support.

## 11. Checklist When Designing Exports

1. List the packages that consumers genuinely need to use.
2. Separate stable API from implementation, adapter, and persistence packages.
3. Export API packages using `exports`.
4. Use qualified exports for packages intended only for specific target modules.
5. Check whether public/protected signatures reference types from other modules.
6. Use `requires transitive` when consumers of the module need readability to dependencies appearing in the public API.
7. Use `opens` separately for deep reflection; do not replace exports with opens.
8. Inspect the descriptor with `jar --describe-module` and dependencies with `jdeps`.
9. Compile an independent consumer module to confirm the public surface is sufficient without depending on implementation.
10. Treat every exported package as an API commitment requiring compatibility management.

## Key Takeaways

`exports` is the package-level public API boundary of a named module. Only export packages that consumers need to use and that the module is ready to support long-term. Use qualified exports to restrict an SPI to target modules; use `requires transitive` when the public API exposes types from a dependency that consumers need to read. Keep implementations in unexported packages, and use `opens` separately for frameworks needing deep reflection. A small public surface lets a module retain the freedom to change its implementation with minimal impact on consumers.
