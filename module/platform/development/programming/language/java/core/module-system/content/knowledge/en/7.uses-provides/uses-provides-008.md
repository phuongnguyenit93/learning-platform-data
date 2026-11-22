# Checking Service Binding with Module Descriptors

## 1. What Is Service Binding in JPMS?

JPMS supports the Service Provider Interface (SPI) mechanism so that one module publishes a service, another module provides an implementation, and a consuming module discovers implementations via `ServiceLoader`.

This mechanism is described by two directives in `module-info.java`:

- `uses`: declares that a module needs to use a service type.
- `provides ... with ...`: declares that a module supplies an implementation for that service type.

General example:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.spi.PaymentProvider;
}
~~~

Implementation module:

~~~java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

These declarations are module metadata. They inform the compiler, JVM, and module resolution mechanism which service a consumer needs and which provider registers that service. When the application calls `ServiceLoader`, matching providers can be discovered and instantiated through the service loading mechanism.

Two activities should be distinguished:

1. **Service binding during module graph resolution:** the resolver can locate and add modules providing used services into the module configuration.
2. **Service loading at application runtime:** `ServiceLoader` locates and instantiates providers for application code to use.

The module descriptor declares the relationship. Runtime verification confirms that the application actually locates and uses the provider.

## 2. Three Roles in a Service

A service typically has three roles:

| Role | Responsibility | Declaration in module descriptor |
|---|---|---|
| Service API | Defines the interface or abstract service type | Export the package containing the service type |
| Consumer | Needs to use the service without directly depending on a specific implementation | `requires` API module and `uses` service type |
| Provider | Supplies an implementation of the service | `requires` API module and `provides ... with ...` |

Example with a payment system:

~~~text
com.acme.payment.api
    Defines PaymentProvider

com.acme.payment.fastpay
    Provides FastPayProvider

com.acme.checkout
    Uses PaymentProvider via ServiceLoader
~~~

The consumer only needs to know the `PaymentProvider` contract. When a new provider becomes available, the provider module can be added without modifying consumer code, provided the provider conforms to the same service contract and is included in the appropriate runtime configuration.

## 3. Declaring the Service API

Create the API module:

~~~java
// src/com.acme.payment.api/module-info.java
module com.acme.payment.api {
    exports com.acme.payment.spi;
}
~~~

Define the service type in the exported package:

~~~java
// src/com.acme.payment.api/com/acme/payment/spi/PaymentProvider.java
package com.acme.payment.spi;

public interface PaymentProvider {
    String name();

    void pay(long amount);
}
~~~

The package containing the service type must be exported so the consumer can import the interface and the provider can implement it.

Concrete implementations should not be placed in the API module. The API module only holds the contract that both sides depend on.

## 4. Declaring a Provider with provides

The provider module declares:

~~~java
// src/com.acme.payment.fastpay/module-info.java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

Implementation:

~~~java
// src/com.acme.payment.fastpay/com/acme/payment/fastpay/FastPayProvider.java
package com.acme.payment.fastpay;

import com.acme.payment.spi.PaymentProvider;

public class FastPayProvider implements PaymentProvider {

    public FastPayProvider() {
    }

    @Override
    public String name() {
        return "FastPay";
    }

    @Override
    public void pay(long amount) {
        System.out.println("FastPay processes " + amount);
    }
}
~~~

Reading the directive:

~~~java
provides com.acme.payment.spi.PaymentProvider
    with com.acme.payment.fastpay.FastPayProvider;
~~~

- The part after `provides` is the service type.
- The part after `with` is the registered provider class.
- The provider module must read the module containing the service type, so the example includes `requires com.acme.payment.api;`.

The provider class must satisfy service provider rules, such as having a public no-argument constructor as shown above. JPMS also supports the provider method form per `ServiceLoader` rules; when using that form, ensure the `provider()` method has a valid signature and returns the corresponding service type.

The implementation package `com.acme.payment.fastpay` does not need to be exported just so consumers can locate the provider via `ServiceLoader`. The consumer depends on the service type, while the provider's module descriptor registers the implementation. Keeping the implementation package unexported prevents turning implementation classes into public API.

## 5. Declaring a Consumer with uses

The consumer module declares:

~~~java
// src/com.acme.checkout/module-info.java
module com.acme.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.spi.PaymentProvider;
}
~~~

The two directives have distinct roles:

- `requires com.acme.payment.api;` creates a readability relationship so consumer code can use the `PaymentProvider` type.
- `uses com.acme.payment.spi.PaymentProvider;` declares that the consumer needs to find providers for that service type.

For named modules, a module calling `ServiceLoader.load(...)` must declare `uses` for the service type. Without this declaration, service loading from that module may fail with a `ServiceConfigurationError`.

The `uses` directive does not name a provider class. The consumer does not need to know the name `FastPayProvider`, nor does it need `requires com.acme.payment.fastpay;` if the goal is to discover implementations through SPI.

## 6. Discovering Providers with ServiceLoader

Code in the consumer:

~~~java
// src/com.acme.checkout/com/acme/checkout/Main.java
package com.acme.checkout;

import com.acme.payment.spi.PaymentProvider;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<PaymentProvider> providers =
                ServiceLoader.load(PaymentProvider.class);

        for (PaymentProvider provider : providers) {
            System.out.println("Provider: " + provider.name());
            provider.pay(1000);
        }
    }
}
~~~

At runtime, `ServiceLoader` searches for registered providers of `PaymentProvider` within the corresponding service loading scope.

If multiple providers exist, the loop may receive multiple implementations. Provider ordering should not be used as a business priority rule; if the application needs to select a provider based on configuration, build an explicit selection policy.

If no provider is found, the loop has no elements to process. That may be valid if the service is optional; if the application strictly requires a provider, check for it and report a configuration error explicitly.

## 7. Checking Module Descriptors

When you suspect a service is not properly registered, inspect each module's descriptor according to its role.

### 7.1. Checking the API Module

Ensure the API descriptor exports the package containing the service type:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.spi;
}
~~~

If the package is not exported, consumers or providers in other modules cannot use the service type under standard Java access rules.

### 7.2. Checking the Provider Module

Ensure the provider module has both required parts:

~~~java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

Points to verify:

- The service type name has the exact package and class name.
- The provider class name matches the implementation class.
- The provider class resides inside the same module that declares `provides`.
- The provider module can read the module containing the service type.
- The provider class satisfies `ServiceLoader` provider instantiation rules.

A common mistake is that the implementation code exists, but `provides` was forgotten. In that case, placing the JAR on the module path is not enough to make the implementation a registered provider in JPMS.

### 7.3. Checking the Consumer Module

Ensure the consumer has:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.spi.PaymentProvider;
}
~~~

Do not confuse `uses` with `requires`:

- `requires` states that the consumer module needs to read the API module.
- `uses` states that the consumer module needs the service loader to locate implementations for the service type.

If the consumer calls `ServiceLoader` but omits `uses`, the descriptor does not fully describe the module's service requirements.

## 8. Checking Descriptors Packaged Inside JARs

After building modules into JARs, use the `jar` tool to read the module descriptors:

~~~bash
jar --describe-module --file build/libs/payment-api.jar
jar --describe-module --file build/libs/payment-fastpay.jar
jar --describe-module --file build/libs/checkout.jar
~~~

Each JAR's output confirms that the module name, `requires`, `exports`, `uses`, and `provides` have been packaged.

For example, the provider JAR should display equivalent relationships:

~~~text
com.acme.payment.fastpay
requires com.acme.payment.api
provides com.acme.payment.spi.PaymentProvider
  with com.acme.payment.fastpay.FastPayProvider
~~~

The consumer JAR should display:

~~~text
com.acme.checkout
requires com.acme.payment.api
uses com.acme.payment.spi.PaymentProvider
~~~

Exact formatting and labels may vary across JDK versions, but the right service type and provider class should appear in the output.

If `provides` or `uses` is missing from the output, check the `module-info.java` source, source set configuration, and packaging steps. You may be inspecting the wrong JAR or an artifact built from stale sources.

## 9. Building and Testing All Modules Together

With a module source structure like this:

~~~text
src/
├── com.acme.payment.api/
│   ├── module-info.java
│   └── com/acme/payment/spi/PaymentProvider.java
├── com.acme.payment.fastpay/
│   ├── module-info.java
│   └── com/acme/payment/fastpay/FastPayProvider.java
└── com.acme.checkout/
    ├── module-info.java
    └── com/acme/checkout/Main.java
~~~

All modules can be compiled with the JDK:

~~~bash
javac --module-source-path src -d mods   -m com.acme.payment.api,com.acme.payment.fastpay,com.acme.checkout
~~~

After compiling, the `mods` directory contains the compiled modules. Run the consumer module:

~~~bash
java --module-path mods   --module com.acme.checkout/com.acme.checkout.Main
~~~

If all declarations and providers are valid, the program will locate `FastPayProvider`, print the provider's name, and call the `pay` method.

When you need to observe module resolution, add `--show-module-resolution`:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.checkout/com.acme.checkout.Main
~~~

The output lets you observe the root modules, dependency relationships, and modules brought into the configuration by the resolver. When service binding occurs, pay attention to lines showing modules bound due to services. A provider module appearing in the configuration still does not prove that its constructor or business logic succeeds; inspect `ServiceLoader` results in the program.

## 10. Checking Service Binding with Configuration.resolveAndBind

Beyond the launcher, the Java API allows creating module configurations with service binding via `Configuration.resolveAndBind(...)`.

Conceptually, the resolver starts from root modules, reads `uses` directives, finds modules with `provides` for those service types, and adds provider modules along with their required dependencies into the configuration if they can be located.

Key distinction:

- `Configuration.resolve(...)` resolves the module graph according to dependency relationships.
- `Configuration.resolveAndBind(...)` performs resolution taking service binding into account.

This is useful when an application creates dynamic module layers, such as a plugin system discovering modules from a directory. A module layer can be created from the resolved configuration; then use the `ServiceLoader.load(layer, ServiceType.class)` overload to locate services in that layer.

Service binding is a configuration resolution step. It does not automatically invoke provider constructors, execute business code, or replace error handling when services are loaded.

## 11. Runtime Verification and Common Errors

After descriptors are verified, run an actual check with `ServiceLoader`.

You can check the number of providers:

~~~java
long count = ServiceLoader.load(PaymentProvider.class)
        .stream()
        .count();

if (count == 0) {
    throw new IllegalStateException(
            "No PaymentProvider is available");
}
~~~

If a provider is mandatory, checking for an empty count causes configuration errors to surface at startup rather than failing only when a payment is processed.

Several situations to distinguish:

| Symptom | Common Cause | How to Check |
|---|---|---|
| Provider not found | Provider module is absent from the module path or not bound into the configuration | Check the module path and module-resolution output |
| JAR has implementation but ServiceLoader does not find it | Missing `provides` in descriptor or missing service configuration file in legacy packaging | Use `jar --describe-module` to inspect the descriptor |
| Consumer calls ServiceLoader but gets configuration error | Named consumer is missing `uses` | Check `module-info.java` of the module calling ServiceLoader |
| Cannot import service interface | API package is not exported or consumer does not require API module | Check API and consumer descriptors |
| Provider fails to instantiate | Invalid constructor/provider method, or initialization code throws an exception | Read `ServiceConfigurationError` and its root cause |
| Incompatible provider class | Provider does not properly implement the service type | Check return type and inheritance/interface relationship |
| Works on classpath but fails on module path | Descriptors or encapsulation rules differ from classpath execution | Check module path, `uses`, `provides`, `exports`, and `opens` |

Errors from service loading may be reported as `ServiceConfigurationError`. Do not merely catch and ignore the error; log the service type, provider, and cause clearly so operators know which module needs fixing.

## 12. Service Providers in Modules vs. Legacy Providers

JPMS does not eliminate Java's traditional service provider mechanism. On the classpath, libraries can register providers using a file:

~~~text
META-INF/services/com.acme.payment.spi.PaymentProvider
~~~

This file contains the fully qualified names of provider classes, typically one provider per line.

For named modules, declare providers using `provides ... with ...` in `module-info.java`. For applications in transition, you may still encounter legacy JARs using `META-INF/services`; check how they are placed on the classpath or module path and how the runtime configuration resolves providers.

Do not assume that a JAR containing a `META-INF/services` file means its module descriptor already has `provides`. Inspect the actual artifact.

## 13. Service Binding Verification Checklist

When verifying a service in JPMS, follow this order:

1. The service type resides in an exported package of the API module.
2. The consumer declares `requires` on the API module.
3. The consumer declares `uses` for the exact service type.
4. The provider declares `requires` on the API module.
5. The provider declares `provides ServiceType with ProviderClass`.
6. The provider class has the exact name, resides in the provider module, and satisfies instantiation rules.
7. Required modules are placed on the module path or in the module layer.
8. Use `jar --describe-module` to confirm the descriptor inside the artifact.
9. Use `--show-module-resolution` when needed to observe resolution and service binding.
10. Run `ServiceLoader` to confirm the provider is discovered and can be instantiated.

Do not stop at seeing a `provides` line in source code. Better evidence is a properly packaged descriptor, a runtime configuration that resolves the provider module, and consumer code actually receiving the provider.

## 14. Key Takeaways

In JPMS, `uses` describes a consumer's service need, while `provides ... with ...` registers an implementation in the provider module. Both directives belong in their respective modules according to their roles.

`requires` and `exports` remain necessary so the service type can be used across modules. A provider's implementation package can usually remain hidden because consumers work only with the service abstraction.

To verify service binding, inspect all three layers of evidence: **module descriptor**, **module resolution**, and **ServiceLoader at runtime**. A correct descriptor indicates the relationship is declared; the resolver confirms the module graph can bring the provider into the configuration; runtime verification confirms the provider is actually discovered and instantiated.
