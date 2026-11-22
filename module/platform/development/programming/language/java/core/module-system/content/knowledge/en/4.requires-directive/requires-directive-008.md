# Reducing Dependencies with Small APIs and Clear Boundaries

In the Java Platform Module System (JPMS), a module does not merely group packages into a deployment unit. A module also creates a boundary to control dependencies and the portion of the API that the module exposes externally.

A well-designed module typically has two characteristics:

- **Small API:** exposes only the types and operations that consumers genuinely need.
- **Clear boundary:** consumers depend on a stable contract, while implementation details are kept inside the module.

These two characteristics help reduce coupling (tight dependency), limit the scope of changes, and keep the module graph easy to understand as the system grows.

## 1. Where does coupling form?

Coupling arises when one module knows too much about the structure or inner workings of another module. For example, a checkout module might depend directly on:

- A concrete payment handler class such as `StripePaymentGateway`.
- Internal packages containing repositories, HTTP clients, or provider configurations.
- Data types from a framework or implementation library.
- Many detail classes just to invoke a simple operation.

When the implementation changes, consumers may have to be modified and recompiled even though business requirements have not changed. If multiple modules depend on those details, a small change can ripple across many places.

JPMS helps reduce coupling by controlling two relationships:

1. **Module dependency:** which module declares `requires` on which module.
2. **Package accessibility:** which packages are exposed with `exports`, and which packages are opened for reflection with `opens`.

Module-level dependencies and package-level APIs must be designed together. Splitting code into many modules while exporting too many packages still leaves weak boundaries.

## 2. Export only the necessary API surface

A module can contain many packages yet export only certain specific packages. Unexported packages still belong to the module, but other modules cannot use types in those packages through regular Java access.

Example:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Package structure:

~~~text
com.acme.catalog/
├── module-info.java
└── com/acme/catalog/
    ├── api/
    │   ├── Product.java
    │   └── Catalog.java
    ├── internal/
    │   ├── JdbcCatalog.java
    │   └── ProductRowMapper.java
    └── config/
        └── DatabaseConfig.java
~~~

Consumers can only use APIs in `com.acme.catalog.api` if the module reads `com.acme.catalog`. The `internal` and `config` packages are not exported and are therefore kept inside the module's boundary.

This establishes a clear contract:

- `api` is the surface that the module commits to consumers for use.
- `internal` is implementation detail that can change without forcing consumers to depend on it.
- `config` holds how the module configures itself; consumers do not need to know internal structure.

There is no need to create a separate module for every package. A boundary can live right inside a named module, with a few intentionally exported packages.

### What does a small API look like?

A small API usually has:

- Few public types, with clear names and responsibilities.
- Methods expressing business behavior, without exposing internal steps.
- Stable input/output data types.
- Understandable and handleable error contracts.
- No exposure of implementation classes, persistence entities, or framework types if consumers do not need them.

For example, a consumer only needs to retrieve product information:

~~~java
package com.acme.catalog.api;

public interface Catalog {
    Product findById(String productId);
}
~~~

~~~java
package com.acme.catalog.api;

public record Product(String id, String name) {
}
~~~

Consumers work with `Catalog` and `Product`. They do not need to know whether the module is using JDBC, JPA, files, or a remote service to look up data.

If `JdbcCatalog` is later replaced by `RemoteCatalog`, the module can swap implementations while keeping the API intact.

## 3. Use requires for direct dependencies

In `module-info.java`, declare `requires` for modules that the current module's code actually uses:

~~~java
module com.acme.checkout {
    requires com.acme.catalog;
}
~~~

This states that `com.acme.checkout` needs to read the `com.acme.catalog` module and that dependency must be resolved when the application runs under module system rules.

Some principles:

- Declare dependencies directly, without relying on another module happening to pull the dependency into the graph.
- Do not add `requires` just because a module appears on the module path.
- Avoid depending on an implementation module when only a small API is needed.
- Do not create dependency cycles between named modules; design the graph in clear directed layers of responsibility.

Example of an easy-to-understand graph:

~~~text
com.acme.checkout  ──requires──>  com.acme.catalog
        │
        └──────────requires──>  com.acme.payment.api
                                      ▲
                                      │ requires
                              com.acme.payment.provider
~~~

In this model, checkout depends on the payment contract. The provider also depends on that contract to implement it. Checkout does not need to know the specific provider.

## 4. Do not overuse requires transitive

`requires transitive` causes a dependency to have its readability propagated to modules that read the current module. This is a useful tool when the dependency is part of the public API, but it widens the consumer's dependency graph.

Compare:

~~~java
module com.acme.billing {
    requires com.acme.money;
    exports com.acme.billing.api;
}
~~~

and:

~~~java
module com.acme.billing {
    requires transitive com.acme.money;
    exports com.acme.billing.api;
}
~~~

In the first case, the billing module reads the money module. Consumers of billing do not automatically read money; if a consumer directly uses types belonging to money, it must declare its own direct dependency.

In the second case, consumers reading billing are also permitted to read money. This makes sense when types from money appear in billing's public API and consumers need to use those types.

Example API:

~~~java
package com.acme.billing.api;

import com.acme.money.Money;

public interface Invoice {
    Money total();
}
~~~

Because `Money` appears in `Invoice`'s public signature, consumers need to read the module containing `Money` to use the API fully. Billing can declare `requires transitive com.acme.money` if it wants to commit to propagating this readability to consumers.

If the API only returns a type owned by billing:

~~~java
package com.acme.billing.api;

public record InvoiceTotal(long amountInCents, String currency) {
}
~~~

then billing can keep a regular `requires com.acme.money` for its internal implementation, or even not need to depend on money if it does not use it. Consumers only need to know the `InvoiceTotal` type.

Do not use `transitive` as a "quick fix" for compile errors. First check whether the dependency's types truly appear in the public API or whether the consumer is simply missing its own direct dependency.

## 5. Invert dependencies with interfaces or service APIs

An effective way to reduce coupling is to have business modules depend on small abstractions, while implementations live in other modules.

For example, a checkout system needs to process payments. If checkout depends directly on a specific provider, changing providers will affect the business module.

Instead, define a small contract in an API module:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

~~~java
package com.acme.payment.api;

public interface PaymentGateway {
    PaymentReceipt charge(PaymentCommand command);
}
~~~

~~~java
package com.acme.payment.api;

public record PaymentCommand(String orderId, long amountInCents) {
}
~~~

~~~java
package com.acme.payment.api;

public record PaymentReceipt(String transactionId) {
}
~~~

The checkout module uses this contract:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    exports com.acme.checkout.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

`uses` declares that the checkout module needs to locate an implementation of the `PaymentGateway` service. The checkout module does not have to declare a dependency on a specific provider.

The provider module implements the contract:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.stripe.internal.StripePaymentGateway;
}
~~~

~~~java
package com.acme.payment.stripe.internal;

import com.acme.payment.api.PaymentCommand;
import com.acme.payment.api.PaymentGateway;
import com.acme.payment.api.PaymentReceipt;

public final class StripePaymentGateway implements PaymentGateway {
    public StripePaymentGateway() {
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        String transactionId = "txn-" + command.orderId();
        return new PaymentReceipt(transactionId);
    }
}
~~~

The `com.acme.payment.stripe.internal` package does not need to be exported. The provider is declared with `provides ... with ...`, so the module system and `ServiceLoader` can locate the implementation via service metadata.

Inside the checkout module, locating the provider can be done via:

~~~java
package com.acme.checkout.api;

import com.acme.payment.api.PaymentCommand;
import com.acme.payment.api.PaymentGateway;
import com.acme.payment.api.PaymentReceipt;

import java.util.ServiceLoader;

public final class CheckoutService {
    public CheckoutResult checkout(CheckoutRequest request) {
        PaymentGateway gateway = ServiceLoader
            .load(PaymentGateway.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No PaymentGateway provider is available"
            ));

        PaymentReceipt receipt = gateway.charge(
            new PaymentCommand(request.orderId(), request.amountInCents())
        );

        return new CheckoutResult(request.orderId(), receipt.transactionId());
    }
}
~~~

Checkout's public types can be owned by checkout itself:

~~~java
package com.acme.checkout.api;

public record CheckoutRequest(String orderId, long amountInCents) {
}
~~~

~~~java
package com.acme.checkout.api;

public record CheckoutResult(String orderId, String paymentReference) {
}
~~~

Consumers of checkout only need to know `CheckoutRequest` and `CheckoutResult`. They do not need to import `PaymentGateway`, `PaymentCommand`, or `StripePaymentGateway`, because those types do not appear in checkout's public signatures.

When launching the example, the provider must be present in the runtime module configuration. You can add the provider explicitly as a root module:

~~~bash
java --module-path out \
  --add-modules com.acme.payment.stripe \
  --module com.acme.checkout/com.acme.checkout.app.Main
~~~

This example demonstrates three boundaries:

1. `com.acme.checkout` depends on the payment API.
2. `com.acme.payment.stripe` depends on the same API to provide an implementation.
3. Consumers of checkout depend only on the checkout API they use.

When switching from the Stripe provider to another provider, the checkout module needs no code changes if the new provider adheres to the same contract and is included in the runtime configuration.

## 6. Keep implementations inside the boundary

A module can export its API package and keep the rest in unexported packages:

~~~java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Example:

~~~text
com.acme.order/
├── module-info.java
└── com/acme/order/
    ├── api/
    │   ├── OrderService.java
    │   ├── OrderRequest.java
    │   └── OrderResult.java
    ├── internal/
    │   ├── DefaultOrderService.java
    │   └── OrderValidator.java
    └── persistence/
        ├── OrderRepository.java
        └── JdbcOrderRepository.java
~~~

Consumers only see `api`. Classes in `internal` and `persistence` can change without becoming part of the public contract.

Do not export a package just so another module can call an internal class. If another module genuinely needs that functionality, determine whether the functionality belongs to a stable API or should be provided across an interface/service boundary.

### exports, qualified exports, and opens

There are three options commonly considered:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.spi to com.acme.order.extension;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

- `exports` exposes a package to every module that reads this module.
- `exports ... to ...` exposes a package only to a specified set of modules.
- `opens ... to ...` grants a specified module deep reflective access to a package.

Qualified exports can be helpful for an internal SPI shared with a few known extensions. However, if the consumer list keeps growing, that can be a sign that the boundary is leaking.

`opens` serves framework reflection needs. It is not a replacement for a normal Java API and should not open all packages if only one framework needs access to a specific package.

## 7. Keep the module graph directed with few dependency layers

A clear graph typically flows from the consuming layer to the contract-providing layer:

~~~text
application
    │
    ▼
business module
    │
    ▼
small API / SPI
    ▲
    │
provider / adapter
~~~

Business modules should not depend back on adapter implementations. Adapters depend on the abstractions they implement.

If two modules need to call each other, check whether they are merging two different responsibilities into the same boundary. You can extract a small shared contract into an API module, but avoid creating a giant `common` module containing every utility type in the system.

Balance must be maintained:

- **Module too large:** blurry boundaries, unrelated features bundled together.
- **Module too small:** complex dependency graph, many descriptors, and coordination overhead with no benefit.
- **API too wide:** consumers depend on too many unnecessary types and details.
- **API too fragmented:** consumers must piece together many low-level operations to perform one business action.

The goal is high-cohesion modules: internal components serve a single responsibility, while the public API accurately reflects consumer needs.

## 8. Process for designing a new boundary

When creating a module or refactoring dependencies, you can follow these steps:

1. **Identify consumers:** which modules need the functionality and which operations do consumers actually need to call?
2. **Define the API first:** create the necessary interfaces, records, or exceptions with small and stable signatures.
3. **Choose public packages:** export only packages containing contracts that consumers are permitted to use.
4. **Keep implementations internal:** place implementation classes, repositories, adapters, and configuration in unexported packages.
5. **Declare direct dependencies:** use `requires` for modules that code genuinely needs to read.
6. **Review public signatures:** only use `requires transitive` when consumers need to read dependencies appearing in the public API.
7. **Invert dependencies when appropriate:** use interfaces/SPI and `uses`/`provides` if business modules should not know specific providers.
8. **Inspect the module graph:** ensure dependencies flow in the intended architectural direction and do not create dependency cycles.
9. **Verify runtime:** confirm providers and dependencies are present in the module configuration at launch.

A good API boundary must have a clear reason for every public type and every `requires` edge. If you cannot explain why a consumer needs a given package or dependency, review that export and declaration.

## Conclusion

Reducing dependencies in JPMS starts with minimizing the API surface and keeping implementations behind the module's boundary. `exports` specifies which packages are exposed; `requires` expresses direct dependencies; `requires transitive` should only be used when the dependency is genuinely part of the public contract. For replaceable integrations, interfaces and service providers allow business modules to depend on abstractions rather than concrete implementations.

When designing modules, start from consumer needs, define small contracts, keep internal packages unexported, and inspect the direction of the module graph. This approach enables implementations to evolve more independently and limits the blast radius of each change.