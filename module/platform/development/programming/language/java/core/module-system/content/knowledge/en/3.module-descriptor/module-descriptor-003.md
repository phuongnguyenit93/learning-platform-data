# requires, exports, opens, uses, and provides in a Module Descriptor

In the Java Platform Module System (JPMS), the module-info.java file is where a module declares its contract with the rest of the application. The module descriptor specifies which modules a module needs to read, which packages it exposes, where reflection is permitted, and how it participates in the service mechanism.

The five most common directives are **requires**, **exports**, **opens**, **uses**, and **provides**. Each directive controls a distinct aspect. Understanding them accurately helps design APIs with clear boundaries and handle compatibility issues with frameworks.

## 1. Where Does the Module Descriptor Reside?

For a named module, the module-info.java source file sits at the root of the module's source set, alongside its packages. For example:

~~~text
src/
└── com.example.orders/
    ├── module-info.java
    └── com/
        └── example/
            └── orders/
                ├── api/
                │   └── OrderService.java
                └── internal/
                    └── OrderRepository.java
~~~

Minimal descriptor:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

The name after the module keyword is the module name. The directives inside the curly braces describe dependencies and access permissions. When compiled, Java generates module-info.class; in a modular JAR, this file sits at the root directory of the JAR.

A module can always read the platform module java.base without an explicit requires declaration. This is where core APIs such as java.lang, java.util, and java.io reside.

The module descriptor is not a list of all classes in the JAR. It is a declaration of relationships and boundaries that JPMS uses when resolving modules and enforcing access control.

## 2. Overview of the Five Directives

| Directive | Question It Answers | Effect |
| --- | --- | --- |
| **requires** | Which modules does this module need to read? | Declares dependencies and readability relationships. |
| **exports** | Which packages' APIs can other modules use? | Exposes packages for standard Java access. |
| **opens** | Which packages are frameworks allowed to deeply reflect on? | Permits deep reflection at runtime. |
| **uses** | Which service implementations does this module need to locate? | Declares a service consumer. |
| **provides** | Which services does this module supply implementations for? | Registers a service provider in the module layer. |

These directives are not interchangeable. For instance, requires does not automatically expose a dependency's packages; exports does not grant deep reflection permissions; opens does not turn a package into an API for other code to import freely.

## 3. requires: Declaring Dependent Modules

Basic syntax:

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

The orders module declares that it needs to read the customer module. Thanks to this relationship, code in orders can reference types belonging to packages that customer appropriately exports.

For API usage to succeed, both sides are required:

- The consuming module declares requires to the module owning the API.
- The module owning the API exports the package containing the types to be exposed.

Example:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

If requires is present but the API package is not exported, the orders module still cannot access that package. If the package is exported but orders does not read customer, code in orders likewise does not automatically gain permission to use the API.

### 3.1. requires transitive

~~~java
module com.example.orders.api {
    requires transitive com.example.customer.api;
}
~~~

requires transitive creates an implied readability relationship. Modules that read orders.api are also permitted to read customer.api through this relationship.

Use transitive when a dependency's types appear in the current module's public API. For example, a public method returns Customer or accepts Customer as a parameter. Consumers of the API may need to read the customer module to compile code calling that method.

Do not add transitive solely because the current module uses the dependency internally. If the dependency is only an implementation detail and does not appear in the API contract, a regular requires is more appropriate.

### 3.2. requires static

~~~java
module com.example.orders {
    requires static com.example.optional.annotations;
}
~~~

requires static declares a dependency needed at compile time but not required to be present in the runtime configuration. It is typically suited for compile-time-only annotations or optional integrations.

If executing code genuinely needs a class belonging to an optional dependency, the application must still ensure that class is present when running that code path. requires static does not synthesize stubs, nor does it handle missing classes automatically.

You can combine static and transitive when a dependency is both an optional compile-time dependency and needs to be propagated in readability relationships:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
}
~~~

### 3.3. Implicit Dependency java.base

Every named module has a readability relationship to java.base. Therefore, a descriptor typically does not need to write:

~~~java
module com.example.orders {
    // java.base is required implicitly.
}
~~~

Other JDK modules such as java.sql or java.logging still need to be declared when the module's code uses their APIs:

~~~java
module com.example.reporting {
    requires java.sql;
    requires java.logging;
}
~~~

## 4. exports: Exposing API Packages

Syntax:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

exports allows modules that read the orders module to access public types in the com.example.orders.api package, along with their public/protected members according to Java's access rules.

Example:

~~~java
package com.example.orders.api;

public class OrderService {
    public void submit() {
        // Process the order.
    }
}
~~~

If this package is exported, other modules can import OrderService once they declare requires to the module owning the package.

A public class in an unexported package still does not become an API usable from another named module. Java's public keyword and JPMS's export boundary are two distinct layers of control.

### 4.1. Qualified exports

You can restrict a package to only specific modules:

~~~java
module com.example.orders {
    exports com.example.orders.spi to
        com.example.orders.plugin,
        com.example.orders.test;
}
~~~

This is a qualified export. The orders.plugin and orders.test modules can access the SPI package, while other modules do not receive that permission just because the package was exported with restrictions.

This approach is useful for internal APIs between modules within the same product. It also helps avoid turning every supporting package into a public contract for all library users.

### 4.2. exports Does Not Open Private Fields for Reflection

exports serves regular API access. It does not grant blanket permission for frameworks to call setAccessible on private fields or constructors of the package.

If a framework needs deep reflection, consider opens. Do not add exports merely to fix InaccessibleObjectException, because the two directives address different needs.

## 5. opens: Allowing Deep Reflection

Some frameworks need to access non-public members to map objects, inject dependencies, serialize data, or create proxies. JPMS controls this operation using opens.

Syntax:

~~~java
module com.example.domain {
    opens com.example.domain.model;
}
~~~

The declaration above opens the model package for deep reflection at runtime to other modules. It does not expose the package as a regular Java API.

### 5.1. Qualified opens

Limit reflection permissions to specific framework modules whenever possible:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
~~~

Only the mapper module is allowed deep reflection on the model package. If another framework also needs permission, additional target module names can be listed.

### 5.2. open module

You can open all packages of a module for deep reflection using the syntax:

~~~java
open module com.example.domain {
    requires com.example.validation;
}
~~~

This is an open module declaration. Every package in the module is opened for deep reflection at runtime. Because of its broad scope, use it only when the module truly requires general reflection capabilities.

An open module declaration must not contain individual opens directives. If only a few packages need to be opened, use a regular module declaration with clearly scoped opens directives.

### 5.3. Opening Packages via JVM Arguments

When you cannot yet edit a library's module-info.java, you can test or temporarily configure it with --add-opens:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper ...
~~~

If the framework sits on the classpath and belongs to the unnamed module:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED ...
~~~

This argument opens the package at runtime to the specified target. It is useful for confirming that an error stems from reflection restrictions, but must be managed carefully in deployment configurations.

## 6. uses: Declaring a Service Consumer

JPMS supports the Service Provider Interface (SPI), allowing a module to use a service contract without depending directly on implementation classes.

A consuming module declares a service with uses:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.api.PaymentProcessor;
}
~~~

In the example, checkout needs to locate one or more implementations of PaymentProcessor. It depends on the module containing the service interface, without needing to declare requires to each provider module.

The service interface can be defined as follows:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    void process(long orderId);
}
~~~

The package containing the interface must be exported so that the consumer module can reference the PaymentProcessor type.

When code in checkout calls ServiceLoader, the uses declaration indicates that this module intends to consume that service:

~~~java
ServiceLoader<PaymentProcessor> processors =
        ServiceLoader.load(PaymentProcessor.class);

for (PaymentProcessor processor : processors) {
    processor.process(1001L);
}
~~~

In a named module, calling ServiceLoader.load for a service must be declared by the module using uses. A missing declaration can lead to a ServiceConfigurationError when ServiceLoader checks permission to use the service.

## 7. provides: Registering a Service Provider

A module containing an implementation declares a provider with provides ... with ...:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public class CardPaymentProcessor implements PaymentProcessor {
    @Override
    public void process(long orderId) {
        System.out.println("Processing card payment for order " + orderId);
    }
}
~~~

The provider module needs to read the module containing the service interface. The provides directive associates the service type with one or more provider types.

Multiple providers can be registered for the same service:

~~~java
module com.example.payment {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor with
        com.example.payment.card.CardPaymentProcessor,
        com.example.payment.wallet.WalletPaymentProcessor;
}
~~~

The package containing the provider does not necessarily need to be exported. ServiceLoader can instantiate the provider per the module declaration without exposing the implementation package to all other modules.

A provider in a named module typically supplies a public no-argument constructor, or a public static provider method following ServiceLoader rules. The provider method is named provider, takes no parameters, and returns a type compatible with the service type. The provider method mechanism is useful when instantiating the implementation needs to be controlled by the provider module.

## 8. Complete Example: Separating API, Application, and Provider

A small example consisting of three modules:

~~~text
src/
├── com.example.payment.api/
│   ├── module-info.java
│   └── com/example/payment/api/PaymentProcessor.java
├── com.example.payment.card/
│   ├── module-info.java
│   └── com/example/payment/card/CardPaymentProcessor.java
└── com.example.checkout/
    ├── module-info.java
    └── com/example/checkout/Main.java
~~~

### API Module

module-info.java:

~~~java
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

PaymentProcessor.java:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    void process(long orderId);
}
~~~

### Provider Module

module-info.java:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

CardPaymentProcessor.java:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public class CardPaymentProcessor implements PaymentProcessor {
    @Override
    public void process(long orderId) {
        System.out.println("Card payment for order " + orderId);
    }
}
~~~

### Application Module

module-info.java:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.api.PaymentProcessor;
}
~~~

Main.java:

~~~java
package com.example.checkout;

import com.example.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProcessor> loader =
                ServiceLoader.load(PaymentProcessor.class);

        for (PaymentProcessor processor : loader) {
            processor.process(1001L);
        }
    }
}
~~~

The application knows only the PaymentProcessor interface. It does not need to import CardPaymentProcessor and does not need to declare requires to the provider module. The service relationship is described via uses and provides.

Compile the three modules:

~~~bash
javac --module-source-path src -d out -m     com.example.payment.api,com.example.payment.card,com.example.checkout
~~~

At launch time, ensure the provider module is included in the module configuration. You can add the provider as a root module:

~~~bash
java --module-path out --add-modules com.example.payment.card     -m com.example.checkout/com.example.checkout.Main
~~~

Or use a service binding mechanism suited to the runtime configuration so providers are linked into the module graph. If only the checkout and API modules are resolved without including the provider in the configuration, ServiceLoader cannot discover an unresolved provider.

## 9. Combining Directives in One Descriptor

A module descriptor can use multiple directives simultaneously:

~~~java
module com.example.orders {
    requires java.sql;
    requires transitive com.example.customer.api;
    requires static com.example.annotations;

    exports com.example.orders.api;
    exports com.example.orders.spi to com.example.orders.plugin;

    opens com.example.orders.model to com.example.orm;

    uses com.example.orders.spi.OrderProcessor;

    provides com.example.orders.spi.OrderProcessor
        with com.example.orders.internal.DefaultOrderProcessor;
}
~~~

This example illustrates different decisions:

- java.sql is a dependency that the module uses.
- customer.api has readability propagated transitively because its types can appear in the public API.
- annotations is only an optional compile-time dependency.
- the api package is exposed to modules that read orders.
- the spi package is reserved for internal plugins.
- the model package is opened for the ORM to perform deep reflection.
- the module both consumes OrderProcessor and supplies a default implementation.

Not every project needs all five kinds of directives. Declare only the relationships that truly exist in the module design.

## 10. Distinguishing exports, opens, and provides

These three directives are often confused because all refer to packages or types within a module, yet they serve different mechanisms:

| Directive | Who Uses It? | Result |
| --- | --- | --- |
| exports | Java code of other modules | Can import and call public APIs in the exported package. |
| opens | Frameworks or libraries using reflection | Can perform deep reflection into the package at runtime. |
| provides | ServiceLoader and module resolution | Registers an implementation for a service type. |

For example, an ORM needing to read private fields needs opens. A module wanting to import OrderService needs the package containing OrderService to be exported via exports and the calling module to have requires. An application wanting to discover implementations via ServiceLoader needs the consumer to have uses and the provider to have provides.

## 11. Inspecting Module Descriptors and Common Errors

You can inspect a JAR's descriptor using:

~~~bash
jar --describe-module --file libs/example.jar
~~~

This command displays the module name, requires, exports, opens, and provider information if present.

Some errors and how to check them:

| Symptom | Possible Cause | Check or Fix |
| --- | --- | --- |
| package is not visible | Missing requires or package not yet exported via exports | Check the descriptors of both consumer and owner. |
| module does not read module | No readability relationship exists | Add requires for the right module. |
| does not export package | API package has not been exported to the consumer | Add exports or qualified exports. |
| InaccessibleObjectException | Framework needs deep reflection | Open the right package using opens or --add-opens. |
| ServiceConfigurationError | Missing uses, unresolved provider, or misconfigured provider | Check uses, provides, and the module graph. |
| Module not found | Missing JAR or wrong module name | Use jar --describe-module and check the module path. |

When diagnosing, distinguish compile-time errors from runtime errors. exports affects regular API accessibility at compile time and runtime; opens primarily serves runtime reflection. uses and provides relate to declaring, resolving, and locating service providers.

## 12. Principles for Designing Maintainable Descriptors

- **Declare direct dependencies:** each module should describe the modules its code actually needs to read.
- **Use transitive intentionally:** propagate readability only when the dependency is part of the API exposed by the module.
- **Export API packages:** avoid exporting implementation packages or internal-only packages.
- **Limit with qualified exports/opens:** if only a few modules need access, explicitly name the targets.
- **Open reflection according to framework needs:** do not use a broad open module just to avoid finding out which packages actually need to be opened.
- **Separate service contracts and providers:** consumers depend on interfaces; providers depend on contracts and register via provides.
- **Check the module graph:** after adding or changing dependencies, verify the descriptor and runtime configuration with JDK tools.

A good module descriptor clarifies the module's contract in one place: which dependencies are read, which APIs are exposed, which packages are open for reflection, and which services are consumed or provided.

## 13. Self-Check

**Scenario 1:** The checkout module calls a public type in a customer package but encounters a package is not visible error. Which declarations need to be checked?

Answer: checkout needs requires to customer; customer needs exports for the package containing that type. Having only one of the two declarations is not enough.

**Scenario 2:** An ORM needs to assign values to private fields of an entity. Should the entity package be exported?

Answer: this need is deep reflection. Use opens for the entity package and restrict it to the ORM module if possible. exports does not replace opens.

**Scenario 3:** An application needs to locate all implementations of PaymentProcessor without depending on specific implementation classes. Which declarations are needed?

Answer: the application module declares uses PaymentProcessor; each provider module declares provides PaymentProcessor with Implementation. Provider modules also need to be included in the module configuration so ServiceLoader can discover them.

**Scenario 4:** A library appears in a facade's public API. When should requires transitive be used?

Answer: use requires transitive when readers of the facade also need to read that library to use types or contracts exposed by the facade. If the dependency is only an internal detail, use regular requires.

**Scenario 5:** A framework running on the classpath needs reflection into a package in a named module. Who can the package be opened to?

Answer: you can use opens ... to ... if the framework has a suitable module name; for libraries on the classpath, the target can be ALL-UNNAMED when using the --add-opens argument.
