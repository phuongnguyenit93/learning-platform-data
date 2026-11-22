# The uses Directive in the Java Module System

## 1. Role of uses in JPMS

In the Java Platform Module System (JPMS), the **uses** directive declares that a module requires a service of a predefined type. A service is typically an interface or abstract class that acts as a contract; other modules can provide implementations without the consuming module needing to know the implementation module names in advance.

This mechanism supports the **Service Provider Interface (SPI)** architecture:

- The API module defines the service type, for example the Greeter interface.
- The consumer module invokes the service through the API and declares uses in its module descriptor.
- One or more provider modules register implementations using the provides directive.
- ServiceLoader discovers and instantiates the appropriate providers at runtime.

For example, an application needs to send notifications without directly depending on an SMTP, console, or external service implementation. The application works only with the NotificationSender interface. Provider modules can supply ConsoleNotificationSender or EmailNotificationSender depending on the deployment configuration.

uses is part of the module descriptor, the module-info.java file. It describes service requirements at the module level, allowing the module resolver to participate in finding providers when building the module graph.

## 2. Syntax of the uses Directive

Syntax:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

Where:

- uses is the keyword of the module declaration.
- The following name is the fully qualified name of the service type.
- The service type is usually a public interface or abstract class exported by the API module.
- A module can declare multiple uses directives, each for one service type.
- A service type can have multiple providers.

Example of a module consuming multiple services:

~~~java
module com.example.application {
    requires com.example.payment.api;
    requires com.example.notification.api;

    uses com.example.payment.PaymentGateway;
    uses com.example.notification.NotificationSender;
}
~~~

The uses directive does not create objects, invoke methods, or automatically load configuration files. It declares the service that the module intends to look up at runtime. Discovering and using instances is typically performed with java.util.ServiceLoader.

The service type name must be resolvable within the module declaring uses. If the service interface resides in another module, the consumer needs an appropriate readability relationship, usually declared via requires on the API module.

## 3. Distinguishing uses, requires, and provides

These three directives often appear together, but they serve different purposes:

| Directive | Role | Typically appears in |
|---|---|---|
| requires | Declares a module dependency and readability of another module. | Consumers and providers that need to use the service API. |
| uses | Declares that a module consumes a service type. | Consumer module. |
| provides ... with ... | Registers an implementation for a service type. | Provider module. |

Example:

~~~java
// module-info.java of the API
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

~~~java
// module-info.java of the consumer
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

~~~java
// module-info.java of the provider
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

The consumer needs requires on the API to compile against and invoke Greeter. The consumer declares uses to request the service. The provider also needs to read the API so its implementation can implement the interface, and then uses provides to register the implementation.

The consumer does not need requires on the provider module just to use the service. This is what creates decoupling between the application and the implementation. The module resolver can locate providers through the service binding mechanism while resolving the module graph.

## 4. Service Type and Module Boundaries

The service type is the shared contract between consumer and provider. You should place the interface or abstract class in a small, stable API module and export only the necessary packages.

Example:

~~~java
package com.example.greeter;

public interface Greeter {
    String greet(String name);
}
~~~

API module:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

The package containing Greeter must be exported so that consumer and provider modules can access this public type. Qualified exports can be used if an organization wants to restrict which modules may read the API package.

The implementation typically resides in the provider's own package:

~~~java
package com.example.greeter.english;

import com.example.greeter.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Provider module:

~~~java
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

The package containing EnglishGreeter does not need to be exported just for ServiceLoader to instantiate the provider. The module descriptor has already registered the provider; keeping the implementation package encapsulated ensures the consumer depends on the service contract rather than the concrete implementation class.

You should not place implementation classes inside the API module. Doing so forces consumers to carry the implementation or tightly couples the API module to a specific implementation choice.

## 5. How Does ServiceLoader Find Providers?

java.util.ServiceLoader is the standard API for loading service providers. For named modules, calling ServiceLoader.load(ServiceType.class) uses the caller's module context and corresponding module layer. The consumer module must declare uses for the service type being loaded.

Basic usage:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(Greeter.class);

for (Greeter greeter : loader) {
    System.out.println(greeter.greet("Java"));
}
~~~

ServiceLoader supplies providers lazily. A provider is typically loaded and instantiated only when the iterator or stream is traversed. Therefore, creating a ServiceLoader does not mean every provider is instantiated immediately.

With named modules on the module path, a provider's module descriptor uses provides to register its implementation. The module resolver performs service binding: when a resolved module declares uses, matching provider modules can be added to the module graph if they are observable on the module path.

As a result, the application can specify only the application module as the root module at launch. Providers are discovered through service binding without the consumer needing to list provider names in requires.

## 6. Complete Example with Three Java 17 Modules

The example consists of three modules:

- com.example.greeter.api: defines the Greeter interface.
- com.example.greeter.english: provides EnglishGreeter.
- com.example.app: consumes Greeter using uses and ServiceLoader.

Directory structure:

~~~text
service-demo/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/Greeter.java
    ├── com.example.greeter.english/
    │   ├── module-info.java
    │   └── com/example/greeter/english/EnglishGreeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### API Module

File src/com.example.greeter.api/module-info.java:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

File src/com.example.greeter.api/com/example/greeter/Greeter.java:

~~~java
package com.example.greeter;

public interface Greeter {
    String greet(String name);
}
~~~

### Provider Module

File src/com.example.greeter.english/module-info.java:

~~~java
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

File src/com.example.greeter.english/com/example/greeter/english/EnglishGreeter.java:

~~~java
package com.example.greeter.english;

import com.example.greeter.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Consumer Module

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeter.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeter> loader =
                ServiceLoader.load(Greeter.class);

        for (Greeter greeter : loader) {
            System.out.println(greeter.greet("Java"));
            return;
        }

        throw new IllegalStateException("No Greeter provider found");
    }
}
~~~

### Compiling and Running

From the service-demo root directory, using JDK 17 or later:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.example.greeter.api,com.example.greeter.english,com.example.app
~~~

The compiler locates each module's sources by directory name under src and writes the compiled modules into mods.

Run the application:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java!
~~~

The application only declares requires com.example.greeter.api and uses Greeter. It does not declare requires com.example.greeter.english. The provider is discovered via service binding when the launcher resolves the module graph. If the provider module is not on the module path or is not resolved, ServiceLoader will not find that provider.

To observe module resolution, you can run:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Diagnostic output may vary by JDK and environment, but it can be used to inspect the resolved modules, including provider modules added via service binding.

## 7. A Service Can Have Multiple Providers

A service type can be provided by multiple modules:

~~~java
module com.example.greeter.french {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.french.FrenchGreeter;
}
~~~

If both the English and French providers are observable and resolved, ServiceLoader can return multiple implementations. Provider iteration order should not be treated as a stable business priority rule.

If the application needs to select a specific implementation, define an explicit selection policy, such as:

- Reading the desired provider name from configuration.
- Iterating over providers and inspecting application-defined metadata or properties.
- Selecting based on capabilities advertised by the provider.
- Reporting a clear error if no matching provider exists or if multiple providers cannot be disambiguated.

Do not rely on the order returned by ServiceLoader to implicitly decide the primary provider. If order matters, model that ordering in configuration or in the application's API.

## 8. Provider Constructor and Provider Method

The most common approach is a public provider class that implements the service type and has a public no-argument constructor. The EnglishGreeter example above uses a no-argument constructor.

JPMS also supports a provider method: the module descriptor still declares the provider class in provides, but that class can provide a public static method named provider that takes no arguments and returns the service type. This is useful when creating the implementation requires a factory or when you do not want to expose the implementation class directly as the provider type.

Example:

~~~java
package com.example.greeter.factory;

import com.example.greeter.Greeter;
import com.example.greeter.english.EnglishGreeter;

public class GreeterProvider {
    public static Greeter provider() {
        return new EnglishGreeter();
    }
}
~~~

When using a provider method, the descriptor registers the provider class:

~~~java
provides com.example.greeter.Greeter
    with com.example.greeter.factory.GreeterProvider;
~~~

The provider method must be public, static, parameterless, and return the service type or a compatible subtype. Choose one consistent provider pattern and verify ServiceLoader requirements for your target JDK.

## 9. ServiceLoader API: Iterator, Stream, and Caching

ServiceLoader implements Iterable, so you can use an enhanced for-loop or iterator to obtain instances:

~~~java
for (Greeter provider : ServiceLoader.load(Greeter.class)) {
    System.out.println(provider.greet("Java"));
}
~~~

Since Java 9, ServiceLoader provides stream(), which returns Provider descriptors. You can inspect a provider's type before requesting an instance:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(Greeter.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);
~~~

When you need to instantiate from a Provider, call Provider.get(). The stream approach is useful when you want to filter by annotation, class name, or implementation metadata before instantiation.

ServiceLoader caches loaded providers. If the environment changes providers and the application has a reason to reload them, you can call reload() to clear the cache. reload() does not install new modules into a module layer; it only refreshes provider iteration against the layer/class loader that the loader is using.

ServiceLoader instances are not designed to be shared concurrently across multiple threads without proper synchronization. If multiple threads need access, manage the lifecycle and provider iteration explicitly.

When a provider is misconfigured, lacks an appropriate constructor, or fails to instantiate, ServiceLoader can throw ServiceConfigurationError while iterating or retrieving the provider. Handle errors at the application initialization boundary so that it is clear which service and provider caused the issue.

## 10. Services on the Classpath and Module Path

ServiceLoader supports both traditional classpath applications and modular applications, though provider registration differs.

| Environment | How providers are registered |
|---|---|
| Classpath / unnamed module | File META-INF/services/<fully qualified name of the service type> in the provider JAR. |
| Named module on the module path | The provides directive in module-info.java. |

Example classpath provider file:

~~~text
META-INF/services/com.example.greeter.Greeter
~~~

The file contents are the fully qualified names of the implementation classes, one provider per line:

~~~text
com.example.greeter.english.EnglishGreeter
~~~

The META-INF/services file mechanism remains useful for classpath-compatible libraries. When migrating a provider to a named module, declare provides in the module descriptor so JPMS understands service binding.

Do not confuse the META-INF/services file with the uses directive. uses belongs in the consumer's module descriptor; the META-INF/services file or provides belongs on the provider side. One describes demand, while the other describes the registered implementation.

For a named consumer module, you must declare uses for the service type it loads via ServiceLoader. Having a META-INF/services file in a JAR does not replace declaring uses in the module descriptor.

## 11. Services in a Custom ModuleLayer

Advanced applications can create a separate module layer to dynamically load plugins or module groups. In that case, you can specify the layer when loading a service:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(pluginLayer, Greeter.class);
~~~

pluginLayer is a ModuleLayer created from a corresponding Configuration and ClassLoader. Provider modules must be resolved into that layer.

When building a configuration for plugins, pay attention to service binding. The Configuration.resolveAndBind API can additionally resolve provider modules based on uses/provides in the module graph. If you only resolve regular dependencies without performing service binding, provider modules may not be added to the graph as expected.

Creating a layer typically requires managing:

- The ModuleFinder and the location containing plugin modules.
- The parent configuration and parent layer.
- The class loader used to define modules.
- Service types shared between the host and plugins.
- Access permissions, lifecycle, and how plugins are unloaded.
- How faulty providers or incompatible modules are handled.

Avoid creating a new class loader/module layer for every service call. Design a clear plugin lifecycle, avoid loading duplicate modules, and keep the service API stable between host and providers.

## 12. Common Errors When Using uses and ServiceLoader

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Consumer module cannot compile the service type | Missing requires on the API module or the API package is not exported. | Check module dependencies and exports. |
| ServiceLoader does not find any provider | The provider module is not on the module path or is not resolved. | Check provides and service binding. |
| Error reporting that module does not declare uses | A named module calls ServiceLoader for a service type not declared in its descriptor. | Add uses for the exact service type in module-info.java. |
| Invalid provider class | Missing public no-arg constructor or valid provider method. | Verify provider class/provider method requirements. |
| ServiceConfigurationError during iteration | The provider cannot be loaded, instantiated, or does not match the service type. | Inspect the exception and the specific module/provider. |
| Consumer has to requires the implementation module | Design depends directly on the provider instead of the service. | Consumer only requires the API and uses the service; provider uses provides. |
| Provider package is exposed unnecessarily | Mistaken assumption that the consumer must access the implementation class. | Keep the implementation package encapsulated; export only the service API. |
| New provider not visible after reload | The provider module has not been added to the layer or module graph. | Update the layer/configuration per the plugin lifecycle; reload only clears ServiceLoader's cache. |
| Classpath provider not found | Missing or incorrect META-INF/services file. | Check the service file name, contents, and location in the JAR. |
| Multiple providers yield unstable results | The application relies on provider iteration order. | Define an explicit provider selection policy. |

When diagnosing issues, determine whether the application is running on the classpath or the module path. Then check the service type, uses, provides or META-INF/services, module/JAR locations, and module resolution. These differ by runtime mode and must be verified against the actual execution environment.

## 13. Tools for Inspecting Module Services

You can use JDK tools to inspect descriptors and module relationships.

Inspect the descriptor of a modular JAR:

~~~bash
jar --describe-module --file mods/com.example.greeter.english.jar
~~~

If using an exploded module directory, you can specify the module path when inspecting modules:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Use jdeps to check module and package dependencies:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Depending on project structure and artifact type, exact syntax may require adding a classpath or module path. Consult the help output of your specific JDK if adjustments are needed.

These commands assist in verifying module dependencies and resolution. They do not replace running actual service discovery tests. You should have tests confirming that expected providers are discovered, instantiated, and return the correct results.

## 14. Designing Safe and Stable Service APIs

The service interface is a contract that both consumers and providers depend on. When designing it, keep in mind:

- Keep the service API small and stable; expose only the types consumers actually need.
- Avoid placing implementation classes in the API module.
- Clearly specify behavior when there are zero providers, one provider, or multiple providers.
- Define how to select a provider when multiple implementations exist.
- Account for lazy provider loading and errors that may occur during instantiation.
- Keep implementation packages unexported if consumers do not need direct access.
- Define version compatibility between the API and providers.
- Control plugin module sources; ServiceLoader is not a security sandbox.

Provider code runs with the privileges of the application process and can perform any action those privileges allow. Therefore, load providers only from trusted sources and control the module path and file/plugin access permissions. JPMS encapsulation manages type and package accessibility; it does not isolate provider code like a sandbox.

If a service handles sensitive data or external operations, the API should clearly define authentication, timeouts, error handling, resource management, and granted permissions. Do not treat a provider's registration in a module descriptor as proof that the provider is safe.

## 15. Implementation Workflow for uses

1. Define the service contract and place the interface/abstract class in an API module.
2. Export the package containing the service type from the API module.
3. In the consumer, requires the API module to read the service type.
4. Declare uses with the fully qualified name of the service type in module-info.java.
5. In each provider, requires the API module and register the implementation with provides ... with ....
6. Ensure the provider has a valid public no-argument constructor or provider method.
7. Compile and place the modules on the module path.
8. Use ServiceLoader to discover providers; define a policy for zero or multiple providers.
9. Verify module resolution and test behavior in the deployment environment.
10. Monitor API/provider compatibility and control plugin sources.

## 16. Checklist When Using uses

- [ ] The service type is defined in a stable API module.
- [ ] The package containing the service type is appropriately exported.
- [ ] The consumer requires the API module.
- [ ] The consumer declares uses for the exact service type.
- [ ] The provider requires the API module and declares provides for the exact service type.
- [ ] The provider has a valid public no-arg constructor or public static provider method.
- [ ] The consumer does not depend directly on the implementation module if only the service contract is needed.
- [ ] The provider module is observable and resolved on the module path.
- [ ] Behavior with zero providers and multiple providers has been tested.
- [ ] ServiceConfigurationError and provider instantiation errors are handled.
- [ ] Classpath/META-INF/services has been checked if the application uses the legacy mechanism.
- [ ] ModuleLayer lifecycle is defined if dynamic plugins are used.
- [ ] Provider sources and plugin execution privileges are controlled.

The uses directive tells a module which service it needs. When combined with requires for the API, provides for implementations, and ServiceLoader to look up instances, an application can swap providers without modifying direct dependencies in the consumer.