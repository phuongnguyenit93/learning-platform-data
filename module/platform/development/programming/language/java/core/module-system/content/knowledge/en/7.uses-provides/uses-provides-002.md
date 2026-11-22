# provides ... with Declares a Service Provider

## 1. The Role of provides in JPMS

JPMS supports the Service Provider Interface (SPI) mechanism so that a module can publish an implementation for a service defined by another module. This mechanism lets the consuming module depend on an abstraction, while implementations can be replaced or added without the consumer knowing the concrete implementation class names.

A service typically consists of three parts:

- **Service API**: defines the interface or abstract class that the application wants to use.
- **Provider module**: contains the implementation and declares that the module supplies the service using the `provides ... with ...` directive.
- **Consumer module**: uses the service and declares its need using the `uses` directive.

For example, a payment application only needs to know `PaymentProcessor`. One module can provide card processing, while another module provides bank transfer processing. The consumer does not need to import or invoke the constructor of each implementation.

The `provides` directive belongs in the `module-info.java` of the module providing the service. General syntax:

~~~java
provides service.type with provider.type;
~~~

Multiple providers can be declared for the same service:

~~~java
provides com.acme.payment.api.PaymentProcessor
    with com.acme.payment.card.CardPaymentProcessor,
         com.acme.payment.bank.BankPaymentProcessor;
~~~

Service and provider names are typically fully qualified with their package names. Each provider must satisfy JPMS rules regarding constructors or provider methods.

## 2. Separating the Service API from the Implementation

A maintainable module structure typically separates the API and providers:

~~~text
payment-api/
  module-info.java
  com/acme/payment/api/PaymentProcessor.java

payment-card/
  module-info.java
  com/acme/payment/card/CardPaymentProcessor.java

checkout-app/
  module-info.java
  com/acme/checkout/Main.java
~~~

The API module exposes the package containing the service type:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Service interface:

~~~java
package com.acme.payment.api;

public interface PaymentProcessor {
    String process(String orderId, long amount);
}
~~~

The API package must be exported so that provider modules and consumer modules can reference the `PaymentProcessor` type. Exporting the service API does not require exporting the package containing the implementation.

## 3. Declaring a Provider with provides ... with

The provider module reads the API module and declares the implementation:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.acme.payment.card;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProcessor implements PaymentProcessor {

    public CardPaymentProcessor() {
    }

    @Override
    public String process(String orderId, long amount) {
        return "Card payment for " + orderId + ": " + amount;
    }
}
~~~

In this example:

- `requires com.acme.payment.api` establishes the readability relationship so the provider can use the service type.
- `provides PaymentProcessor with CardPaymentProcessor` registers the provider with the module system.
- The provider class implements the `PaymentProcessor` interface.
- The provider has a public no-argument constructor so `ServiceLoader` can create an instance.
- The `com.acme.payment.card` package does not need to be exported just for `ServiceLoader` to locate and instantiate the provider.

That last point is crucial: the consumer depends on the service API, not directly on the implementation package. The provider implementation can reside in an internal package and remain encapsulated.

## 4. Two Ways to Create a Provider Instance

A provider class declared after the `with` keyword can use one of two mechanisms.

### Public no-argument constructor

This is the most common approach. The provider class must be public, implement the service type, and have a public no-argument constructor:

~~~java
public final class CardPaymentProcessor implements PaymentProcessor {
    public CardPaymentProcessor() {
    }

    @Override
    public String process(String orderId, long amount) {
        return "Card: " + orderId;
    }
}
~~~

When `ServiceLoader` instantiates the provider, it invokes this constructor. If the constructor does not exist, is not public, or throws an error during initialization, loading the provider may fail.

This approach fits when the implementation can be created directly without custom configuration parameters.

### Public static provider() method

If creating the service requires a factory, configuration, or implementation selection, the provider class can declare a public static method named `provider` that takes no parameters and returns the service type or a subtype of it.

Descriptor:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProvider;
}
~~~

Provider factory:

~~~java
package com.acme.payment.card;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProvider {

    private CardPaymentProvider() {
    }

    public static PaymentProcessor provider() {
        return new CardPaymentProcessor(loadConfiguration());
    }

    private static PaymentConfiguration loadConfiguration() {
        return PaymentConfiguration.fromEnvironment();
    }
}
~~~

In this approach, `CardPaymentProvider` is the provider class listed after `with`; the `provider()` method returns the object implementing the service. The provider class does not have to implement `PaymentProcessor` itself. It must be public and have a public static provider method with the matching signature.

A factory method is useful when the implementation needs to be initialized through a custom procedure. If no factory is needed, a public no-argument constructor is usually simpler.

## 5. Consumer Declaring uses

A module consuming the service needs to declare `uses` in its module descriptor:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

The `uses` directive states that the checkout module needs to find providers for the `PaymentProcessor` service. The consumer does not need to declare:

~~~java
requires com.acme.payment.card;
~~~

if it only uses the service interface and does not call the implementation directly. Binding the provider is the responsibility of module resolution and `ServiceLoader`.

Consumer code:

~~~java
package com.acme.checkout;

import com.acme.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProcessor> loader =
            ServiceLoader.load(PaymentProcessor.class);

        for (PaymentProcessor processor : loader) {
            System.out.println(
                processor.process("ORDER-100", 250_000)
            );
        }
    }
}
~~~

In a named module, calling `ServiceLoader.load(...)` without declaring `uses` for the corresponding service may fail with a `ServiceConfigurationError`. Therefore, declare `uses` directly in the consumer module rather than relying solely on the service interface being imported in the source code.

## 6. Relationship Between Service API, Provider, and Consumer

Dependency diagram:

~~~text
                 requires
payment-card -----------------> payment-api
     |                              ^
     | provides                     | requires
     | PaymentProcessor             |
     v                              |
ServiceLoader <---------------- checkout-app
                                  uses PaymentProcessor
~~~

The diagram can be read as three relationships:

1. The provider module reads the service API because the implementation must reference the interface.
2. The consumer module also reads the service API because the application code calls the interface.
3. The provider module registers the implementation via `provides`; the consumer module declares its need via `uses`.

`provides` does not create a direct API import for the consumer. Nor does it force the consumer to declare `requires` on the provider module. When module resolution performs service binding, matching providers can be included in the configuration if they are observable on the module path and the service is used in the configuration.

If the application creates a `ModuleLayer` manually, pay attention to how the `Configuration` is constructed. `Configuration.resolveAndBind(...)` performs the additional step of binding service providers; `Configuration.resolve(...)` only resolves the requested root dependencies. When you want providers to be automatically discovered in a custom layer, use the appropriate resolve-and-bind process and load services from that layer.

## 7. Multiple Providers for a Service

A single module can provide multiple different services:

~~~java
module com.acme.platform.adapters {
    requires com.acme.payment.api;
    requires com.acme.notification.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.platform.adapters.CardPaymentProcessor;

    provides com.acme.notification.api.Notifier
        with com.acme.platform.adapters.EmailNotifier;
}
~~~

A single service can also have multiple providers listed in the same directive:

~~~java
provides com.acme.payment.api.PaymentProcessor
    with com.acme.platform.adapters.CardPaymentProcessor,
         com.acme.platform.adapters.BankTransferProcessor;
~~~

The consumer can iterate through all discovered providers:

~~~java
ServiceLoader<PaymentProcessor> loader =
    ServiceLoader.load(PaymentProcessor.class);

loader.stream().forEach(provider ->
    System.out.println(provider.type().getName())
);
~~~

You should not rely on provider order as a business priority rule if the application needs to choose a specific implementation. If selection by configuration is needed, read dedicated metadata or configuration and apply an explicit selection policy in the application.

If providers need their own name, order, or configuration properties, the service API can expose metadata methods, or the application can manage its own registry. You should not infer behavior from the order in which JARs appear on the module path.

## 8. Common Mistakes When Declaring provides

### Service type is not readable

The provider module must read the module that owns the service type. If missing:

~~~java
module com.acme.payment.card {
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

then the descriptor or provider source may fail to compile properly because the module has not declared the dependency. Add `requires com.acme.payment.api`.

### Provider class does not meet instantiation rules

If using a constructor, the provider class needs a public no-argument constructor. If using a provider method, the method must be public static, take no parameters, and return a type compatible with the service.

These errors may surface when `ServiceLoader` iterates over or instantiates the provider. Inspect the full exception, including its underlying cause, rather than looking only at the first line of the `ServiceConfigurationError`.

### Consumer forgets uses

The consumer module already has `requires` on the service API, but forgets:

~~~java
uses com.acme.payment.api.PaymentProcessor;
~~~

In that case, the consumer may encounter a `ServiceConfigurationError` when using `ServiceLoader`. Add `uses` to the module descriptor of the module invoking the service.

### Provider module is not resolved

The provider JAR may exist on disk but not be part of the running module configuration/layer. Check the module path, module name, service binding, and how the layer is created. Do not just check that the JAR file exists in the directory.

### Accidentally exporting the implementation package

There is no need to add:

~~~java
exports com.acme.payment.card;
~~~

just so `ServiceLoader` can find the provider declared with `provides`. Keep the implementation package unexported if consumers do not need direct access.

## 9. Checking Descriptors and Artifacts

After building the provider JAR, inspect the actual descriptor:

~~~bash
jar --describe-module --file build/libs/payment-card.jar
jar --list --file build/libs/payment-card.jar
~~~

The output should show the module name, the dependency on the service API, the `provides` directive, and that the provider class is present in the archive.

Check module resolution:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

Run the consuming application with the actual release JARs. Verify that:

- The consumer has `uses` for the correct service type.
- The provider module is resolved and service binding locates the provider.
- The provider is instantiated successfully.
- Each provider fulfills the service contract properly.
- No dependency exists only in the IDE environment while missing from the release module path.

If using a custom layer, create the configuration with the appropriate service binding mechanism and call `ServiceLoader.load(layer, PaymentProcessor.class)` for that layer.

## 10. When to Use provides vs. META-INF/services?

In an explicit named module, declare the provider using `provides ... with ...` in `module-info.java`. This is how the module system reads it directly from the descriptor.

For applications or libraries running on the classpath in the traditional manner, ServiceLoader uses a configuration file:

~~~text
META-INF/services/com.acme.payment.api.PaymentProcessor
~~~

The file lists the fully qualified name of each provider class, one name per line.

Both approaches serve the same SPI model but belong to different packaging mechanisms. When migrating a JAR from the classpath to an explicit named module, move provider registration to `provides` and check consumer `uses`. Do not assume that merely adding `module-info.java` means all legacy service configurations have been migrated properly.

## 11. Checklist Before Releasing a Provider Module

- [ ] The service interface is in an exported package of the API module.
- [ ] The provider module declares `requires` on the API module.
- [ ] `provides` uses the exact service type and provider class.
- [ ] The provider class has a valid public no-argument constructor or public static `provider()` method.
- [ ] The consumer module declares `uses` for the service it loads.
- [ ] The implementation package is not exported unless there is a direct API need.
- [ ] The provider module is present in the module configuration or service binding of the layer.
- [ ] The release JAR contains the correct `module-info.class` and provider class.
- [ ] ServiceLoader has been tested on the actual module path and any custom layers.
- [ ] Provider instantiation errors and service configuration errors are thoroughly checked.

## Conclusion

`provides ... with` registers the provider on the supplying module side; `uses` declares the demand on the consuming module side. The provider module reads the service API via `requires`, while the consumer typically only needs to read the service API without directly depending on the implementation module.

For a service to operate reliably, check the provider class or provider method, service binding, module layer, packaged artifacts, and the actual consumer. By keeping the implementation package internal and publishing the proper service API, implementations can be replaced or added without coupling consumers to concrete implementation classes.
