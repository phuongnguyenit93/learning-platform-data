# Ordering, duplicate providers, and implementation selection

In Java, `ServiceLoader` allows a module or application to discover implementations of a service interface without depending directly on each implementation class. A service can have multiple providers at the same time: for example, multiple payment gateways, multiple serializers, or multiple plugins.

When there are multiple providers, the application needs to solve three problems:

- **Ordering:** is the order in which providers are discovered stable, and does it carry priority semantics?
- **Duplicate providers:** where can the same provider be registered multiple times, and how does the application handle duplicates?
- **Implementation selection:** when there are multiple valid implementations, what rule determines which implementation is used?

`ServiceLoader` is responsible for discovering providers. It does not itself define a business policy for choosing the best provider. If results must be deterministic, the application must establish explicit selection rules.

## 1. A service can have multiple providers

Suppose a payment application defines a service interface:

~~~java
package com.acme.payment.spi;

public interface PaymentGateway {
    String id();

    int priority();

    PaymentReceipt charge(PaymentCommand command);
}
~~~

Implementations may come from different modules:

~~~java
package com.acme.payment.stripe;

public final class StripeGateway implements PaymentGateway {
    @Override
    public String id() {
        return "stripe";
    }

    @Override
    public int priority() {
        return 100;
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        return new PaymentReceipt("stripe-" + command.orderId());
    }
}
~~~

~~~java
package com.acme.payment.bank;

public final class BankGateway implements PaymentGateway {
    @Override
    public String id() {
        return "bank";
    }

    @Override
    public int priority() {
        return 80;
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        return new PaymentReceipt("bank-" + command.orderId());
    }
}
~~~

A consumer module can discover all implementations with:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(PaymentGateway.class);

for (PaymentGateway gateway : loader) {
    System.out.println(gateway.id());
}
~~~

The loop may return multiple providers. This is normal SPI behavior: a service interface describes the shared contract, while providers supply different implementations.

## 2. Registering providers in named modules

With JPMS, providers can be declared in `module-info.java`.

Module containing the service API:

~~~java
module com.acme.payment.spi {
    exports com.acme.payment.spi;
}
~~~

Consumer module:

~~~java
module com.acme.checkout {
    requires com.acme.payment.spi;
    uses com.acme.payment.spi.PaymentGateway;
}
~~~

The `uses` directive declares that the checkout module consumes the `PaymentGateway` service. It lets the module system know which services need to be located when using service binding and `ServiceLoader`.

Provider module:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.spi;

    provides com.acme.payment.spi.PaymentGateway
        with com.acme.payment.stripe.StripeGateway;
}
~~~

Another provider can reside in a separate module:

~~~java
module com.acme.payment.bank {
    requires com.acme.payment.spi;

    provides com.acme.payment.spi.PaymentGateway
        with com.acme.payment.bank.BankGateway;
}
~~~

The provider class must satisfy `ServiceLoader` rules. The common approach is a public class implementing the service with a public no-argument constructor. For providers in named modules, a public static provider method following JPMS rules can be used to create the service object; this is useful when a factory or initialization configuration is needed.

In a plugin architecture using `ModuleLayer`, you can specify the layer to search for providers:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(pluginLayer, PaymentGateway.class);
~~~

This call lets the application search for providers in the specified layer and its parent layers. It is the right choice when providers are loaded dynamically in a plugin layer. The service API should be shared from a parent layer so the consumer and providers reference the same interface definition.

## 3. Registering providers on the classpath

Unmodularized libraries can register providers using a configuration file:

~~~text
META-INF/services/com.acme.payment.spi.PaymentGateway
~~~

The file contents list the fully qualified names of the provider classes, one class per line:

~~~text
com.acme.payment.stripe.StripeGateway
com.acme.payment.bank.BankGateway
~~~

Lines may contain whitespace and comments starting with `#`. The file is read as UTF-8. Duplicate provider names within the same provider-configuration file are ignored according to `ServiceLoader` rules.

On the classpath, `ServiceLoader.load(PaymentGateway.class)` typically uses the thread context class loader to locate provider configurations and their corresponding classes. Consequently, when an application or framework changes the context class loader, the set of discovered providers may also change.

Do not mix the two registration styles:

- Named modules declare services with `uses` and `provides`.
- Providers on the classpath declare classes in `META-INF/services`.

Both serve SPI, but their metadata sources and class-loading scopes differ.

## 4. Ordering: the order in which providers are discovered

`ServiceLoader` discovers providers lazily. Providers are only loaded or instantiated when the application iterates the results or calls `Provider.get()`. A service loader also caches loaded providers; subsequent iterations may return cached instances before searching for new providers.

Do not treat provider discovery order as a business priority policy.

For providers on the classpath, order can be affected by the order in which resources are returned by the class loader and the order of class names within each configuration file. For providers in named modules, do not rely on the order in which modules are found by the resolver or the iteration order of a module set. The API does not provide a global priority contract for an application to select an implementation by position.

The following example looks concise:

~~~java
PaymentGateway gateway =
    ServiceLoader.load(PaymentGateway.class)
        .findFirst()
        .orElseThrow();
~~~

However, `findFirst()` only takes the first provider in the current encounter order. If discovery order changes due to the classpath, module finder, plugin layer, or packaging, the chosen implementation can change accordingly.

Use `findFirst()` only when the application genuinely does not care which provider is selected, or when the order is already guaranteed by a configuration controlled by the application. If providers have priorities, represent priority as data and sort explicitly.

## 5. Duplicate providers: where do duplicates come from?

Duplicate providers can occur at multiple levels:

1. **Duplicate lines in the same configuration file:** the same provider name is listed multiple times in a single `META-INF/services` file.
2. **Duplicate registration during packaging:** the same implementation is pulled into multiple dependencies or multiple configuration resources.
3. **Duplicate logical implementation:** two different classes perform the same function or claim the same provider code.
4. **Duplicates across discovery sources:** the application combines providers from the classpath and a module layer, causing the same implementation or functionality to appear from multiple places.

`ServiceLoader` ignores repeated provider names within the same provider-configuration file. However, that does not solve all business-level duplicate cases. Two different classes can both return `id()` as `stripe`; a single class can also be packaged or loaded in different environments.

Therefore, a service should have a stable identifier such as `id()`. The application can check for duplicate IDs after discovering providers:

~~~java
Map<String, PaymentGateway> byId = new HashMap<>();

for (PaymentGateway gateway : ServiceLoader
        .load(PaymentGateway.class)) {

    PaymentGateway previous =
        byId.putIfAbsent(gateway.id(), gateway);

    if (previous != null) {
        throw new IllegalStateException(
            "Duplicate payment provider id: " + gateway.id()
        );
    }
}
~~~

This detects two implementations advertising the same ID. If the system allows multiple versions of a provider, the ID should include a namespace or version according to a defined contract.

Do not automatically discard duplicate providers by keeping the first element. When discovery order is not guaranteed, doing so can silently select different implementations across runs. For misconfigurations, failing with a clear error is usually much easier to diagnose.

## 6. Selecting an implementation using priority and a tie-breaker

A service can define two properties:

- `priority()`: a higher integer indicates higher priority.
- `id()`: a unique, stable identifier to resolve priority ties.

Example of provider selection:

~~~java
import java.util.Comparator;
import java.util.ServiceLoader;
import java.util.stream.Collectors;
import java.util.List;

List<PaymentGateway> gateways =
    ServiceLoader.load(PaymentGateway.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .collect(Collectors.toList());

PaymentGateway selected = gateways.stream()
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException("No PaymentGateway provider found")
    );
~~~

The rules here are:

1. A provider with higher priority is selected first.
2. If priorities are equal, the ID with the smaller lexicographical order is selected.
3. If no provider exists, the application reports a clear error.

The Comparator defines a complete tie-breaker so the result does not depend on encounter order, provided each provider has a unique and stable ID.

If the business logic requires selection by region, currency, tenant, or feature flag, put those criteria into a separate policy. For example, the application can filter gateways supporting the currency first, and only then sort by priority. Do not rely on priority alone if a provider is incapable of handling the current request.

## 7. Checking for duplicate IDs before selecting

You can combine duplicate detection with implementation selection in a single step:

~~~java
Map<String, PaymentGateway> providersById = new HashMap<>();

for (PaymentGateway gateway : ServiceLoader
        .load(PaymentGateway.class)) {

    String id = gateway.id();

    if (id == null || id.isBlank()) {
        throw new IllegalStateException(
            "PaymentGateway provider must declare a non-empty id"
        );
    }

    PaymentGateway existing =
        providersById.putIfAbsent(id, gateway);

    if (existing != null) {
        throw new IllegalStateException(
            "More than one PaymentGateway declares id: " + id
        );
    }
}

PaymentGateway selected = providersById.values().stream()
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException("No PaymentGateway provider found")
    );
~~~

This example assumes providers instantiate successfully and `id()` is part of the service contract. If instantiating a provider is expensive, has side effects, or requires prior configuration, design a separate factory/configuration so discovery does not trigger full business operations.

Another option is to inspect metadata before creating an instance using `ServiceLoader.stream()` and `Provider.type()`. However, class metadata is only useful if the selection policy can be determined from the type or annotations without calling the provider. If priority is runtime data supplied by the instance, the application still must create the instance to read it.

## 8. Filtering providers by capability rather than just order

Priority answers which provider is preferred, but not necessarily which provider fits the request.

For example, a gateway might only support USD and EUR:

~~~java
public interface PaymentGateway {
    String id();

    int priority();

    boolean supports(String currency);

    PaymentReceipt charge(PaymentCommand command);
}
~~~

Selecting among providers that support the currency:

~~~java
PaymentGateway selected = ServiceLoader
    .load(PaymentGateway.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(gateway -> gateway.supports(command.currency()))
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException(
            "No gateway supports currency " + command.currency()
        )
    );
~~~

The selection flow should reflect business order:

1. Exclude providers incompatible with the request.
2. Exclude providers disabled by configuration or feature flags.
3. Sort remaining providers by priority.
4. Apply a deterministic tie-breaker.
5. Report an error if no matching provider remains.

If the application needs operators to choose the implementation, an explicit configuration such as `payment.gateway=stripe` can be used. In that case, ServiceLoader still handles discovery, while configuration decides which provider is chosen. Report an error if the configured ID does not exist or the provider does not support the request.

## 9. How are providers lazily initialized and cached?

`ServiceLoader` does not necessarily create all providers right when `load()` is called. Discovery and instantiation happen when the application iterates the iterator or retrieves an instance from `Provider`.

The `stream()` API returns `ServiceLoader.Provider<S>` elements. Each provider descriptor can reveal its type before calling `get()` to create an instance:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(PaymentGateway.class);

loader.stream().forEach(provider -> {
    System.out.println(provider.type().getName());
});
~~~

When an instance is needed:

~~~java
PaymentGateway gateway = provider.get();
~~~

Loaded instances are cached in the service loader. If provider configuration changes or the application needs to rediscover providers, it can call:

~~~java
loader.reload();
~~~

`reload()` clears the cache of loaded providers; the next iteration will search for providers again against the current configuration. It does not automatically change module layers, the module path, or JARs already defined in the runtime.

A `ServiceLoader` is not designed for safe concurrent use from multiple threads. If concurrent access is needed, create loaders scoped to their usage or synchronize access according to the application's design.

## 10. Handling errors when providers are discovered

Discovery or instantiation can fail. Common causes include:

- An invalid provider name in `META-INF/services`.
- The provider class cannot be found by the class loader.
- The provider does not implement the service interface.
- The constructor or provider method cannot be invoked.
- The provider throws an exception during initialization.
- The provider module misdeclares the service or the consumer module lacks `uses`.

`ServiceLoader` can throw `ServiceConfigurationError` when a configuration or provider is invalid. Do not catch the error and silently skip all broken providers, as the application might continue with an implementation that does not meet requirements.

Example explicitly reporting a failing provider:

~~~java
try {
    for (PaymentGateway gateway :
            ServiceLoader.load(PaymentGateway.class)) {
        System.out.println("Loaded: " + gateway.id());
    }
} catch (ServiceConfigurationError error) {
    throw new IllegalStateException(
        "Unable to load PaymentGateway providers",
        error
    );
}
~~~

If the system has a fallback policy, explicitly define which provider is permitted as a substitute, what conditions trigger fallback, and how it is logged. Do not treat any arbitrary working provider as a valid fallback.

## 11. Selecting providers in plugin layers

When plugins are loaded into a child layer, use the overload taking a layer to scope discovery:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(pluginLayer, PaymentGateway.class);
~~~

Suppose:

~~~text
Parent layer
└── com.acme.payment.spi

Plugin layer
├── com.acme.payment.stripe
└── com.acme.payment.bank
~~~

Both provider modules declare `provides` for the service API in the parent. The application can discover providers in the plugin layer and its parent layers according to this overload's rules.

If the application has multiple independent plugin layers, it can create a service loader for each layer and combine candidates according to the host's policy. When combining, check for duplicate IDs across the entire candidate set; two plugins in different layers can still advertise the same ID.

Do not rely on the order of `pluginLayer.modules()` to decide the preferred provider. That is the layer's set of modules, not a service priority list. Fetch providers through ServiceLoader and then apply an explicit policy.

## 12. Design principles

- **Stable identifier:** each provider should have a unique ID within the scope managed by the application.
- **Explicit priority:** if multiple implementations exist, define priority and a tie-breaker instead of using `findFirst()`.
- **Do not depend on discovery order:** provider order can vary by configuration source, class loader, or layer.
- **Check for duplicates:** detect duplicate IDs and report an actionable configuration error.
- **Separate discovery from selection:** ServiceLoader finds candidates; application policy selects the right candidate.
- **Filter by capability:** verify that a provider supports the current request before comparing priorities.
- **Manage lifecycle:** understand lazy initialization, caching, `reload()`, and thread-safety limits.
- **Keep the service API stable:** providers and consumers both depend on the SPI module, not directly on each other's implementations.

## 13. Diagnosing common issues

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| No provider found | Missing `uses`, missing `provides`, missing service file, or wrong layer/class loader | Check descriptors, `META-INF/services`, and the `ServiceLoader.load` overload |
| First provider changes across environments | Code relies on encounter order | Add priority and a deterministic tie-breaker |
| Same functionality appears multiple times | Provider registered via multiple artifacts or modules | Check provider IDs and registration sources |
| Two providers share the same ID | Duplicate configuration or contract does not enforce unique IDs | Fail fast and fix registration |
| Provider fails during iteration | Class cannot be loaded or constructor/provider method fails | Check the cause of `ServiceConfigurationError` |
| New provider does not appear after config change | Loader holds a cache or layer has not been recreated | Consider `reload()` and inspect layer lifecycle |
| Plugin is incompatible with service interface | SPI class loaded from a different definition or wrong version | Place SPI in a shared parent layer and check the defining class loader |

## Conclusion

`ServiceLoader` can discover multiple implementations of the same service. It supports registering providers via `provides ... with ...` in named modules or via `META-INF/services` files on the classpath, while loading providers lazily and caching discovered instances.

The application must define how to handle multiple providers. Assign stable IDs, detect duplicate IDs, filter by capability, and select implementations using priority and a deterministic tie-breaker. `findFirst()` only reflects the current encounter order; it is not a durable priority policy. With plugin layers, use `ServiceLoader.load(layer, service)` to discover within the proper scope and apply the same application selection policy.
