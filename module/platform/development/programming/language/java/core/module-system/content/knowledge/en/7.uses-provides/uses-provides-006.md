# Provider Module Without Exporting Implementation Packages

The Java Platform Module System (JPMS) allows a module to publish a service without exposing the package that contains the service's implementation class. This is a key aspect of the **ServiceLoader** mechanism: the consuming module knows the service contract, the supplying module registers the implementation using the **provides ... with ...** directive, and the implementation package can remain hidden by omitting **exports**.

This organization separates the API from the implementation. Service consumers depend on a stable interface; providers can change implementation classes or internal package structure without forcing consuming modules to reference those classes directly.

## 1. Three Roles in a Service Architecture

A modular application using service providers typically has three roles:

- **Service API module** defines the interface or abstract service type and exports the API package.
- **Provider module** implements the service and registers the implementation in its module descriptor using **provides**.
- **Consumer module** declares **uses** to indicate it needs the service and locates providers via **ServiceLoader**.

The dependency flow looks like this:

~~~text
             requires
Consumer -----------------> Service API
    |                           ^
    | uses Service              | implements
    v                           |
 ServiceLoader             Provider module
                                |
                                | provides API with Implementation
                                v
                      internal implementation package
                      (not exported)
~~~

The consumer needs to know the service interface, but does not need to know the implementation class name or internal packages of the provider. The provider depends on the service API to implement the contract. Provider registration is performed through the module descriptor.

## 2. Creating the Service API Module

Suppose the service needs to provide greetings. Create module **com.acme.greeter.api** with the structure:

~~~text
src/
└── com.acme.greeter.api/
    ├── module-info.java
    └── com/acme/greeter/api/GreetingService.java
~~~

Descriptor:

~~~java
module com.acme.greeter.api {
    exports com.acme.greeter.api;
}
~~~

Service interface:

~~~java
package com.acme.greeter.api;

public interface GreetingService {
    String greet(String name);
}
~~~

The API package must be exported so consumer and provider modules can reference the **GreetingService** interface in source code. This is the public contract of the service; it contains no concrete implementation classes.

Keep the API small and stable. Consuming modules only need to depend on the types published in this package, allowing providers to change internally without exposing implementation structure.

## 3. Creating the Provider Module with an Encapsulated Implementation Package

Create module **com.acme.greeter.provider**:

~~~text
src/
└── com.acme.greeter.provider/
    ├── module-info.java
    └── com/acme/greeter/provider/internal/
        └── VietnameseGreetingService.java
~~~

Provider descriptor:

~~~java
module com.acme.greeter.provider {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.provider.internal.VietnameseGreetingService;
}
~~~

Implementation class:

~~~java
package com.acme.greeter.provider.internal;

import com.acme.greeter.api.GreetingService;

public final class VietnameseGreetingService
        implements GreetingService {

    public VietnameseGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

Notice that the provider descriptor **does not** contain the line:

~~~java
exports com.acme.greeter.provider.internal;
~~~

The **com.acme.greeter.provider.internal** package remains an internal package of the provider module. The implementation class can be **public** and have a public no-argument constructor to satisfy ServiceLoader's provider class rules, yet other modules cannot import this class across the module boundary because the package is not exported.

The **provides ... with ...** directive registers the implementation class as a provider for the stated service type. JPMS and ServiceLoader use this declaration to discover and instantiate the provider. Registration does not require exporting the implementation package.

## 4. Creating the Consumer Module

The consumer only needs to know the service API. Structure:

~~~text
src/
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Descriptor:

~~~java
module com.acme.app {
    requires com.acme.greeter.api;
    uses com.acme.greeter.api.GreetingService;
}
~~~

**requires** allows the consumer to read the module containing the service interface. **uses** declares that this module consumes the **GreetingService** service type. The **uses** directive is not a dependency on a specific provider.

The main class locates and invokes providers:

~~~java
package com.acme.app;

import com.acme.greeter.api.GreetingService;

import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java Module System" : args[0];

        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService service : loader) {
            System.out.println(service.greet(name));
        }
    }
}
~~~

The consumer does not import **VietnameseGreetingService**, does not call the implementation's constructor, and does not need to declare **requires com.acme.greeter.provider**. It works with the interface and lets ServiceLoader locate registered providers in the module layer.

## 5. Compiling and Running the Example

From the project directory, compile all three modules with JDK 21:

~~~bash
javac -d out --module-source-path src \
    -m com.acme.greeter.api,com.acme.greeter.provider,com.acme.app
~~~

You can compile on a single line in the terminal if your environment does not support line continuation as shown in the example.

At runtime, the provider module must be resolved into the module layer along with the consumer. With provider modules on the module path, use the **--bind-services** option to instruct the launcher to resolve modules providing services used by the selected modules:

~~~bash
java --module-path out --bind-services \
    --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Xin chao, Java Module System!
~~~

If the provider is not included in the module layer, ServiceLoader cannot discover it in that layer. **--bind-services** helps the launcher bind providers on the module path for services declared with **uses** by root modules. In configurations where module layers are created programmatically via the API, the application or bootstrap code must perform appropriate service binding when resolving the configuration.

The key point is that the consumer does not need a compile-time dependency on the provider module. Providers are selected through the service contract and the module system's binding mechanism.

## 6. Why Does the Implementation Package Not Need to Be Exported?

In regular class calls, another module wanting to import a type from a provider's package must read the provider module and that package must be exported. However, ServiceLoader uses provider registration metadata in the module descriptor to locate implementations.

JPMS allows a provider class declared in **provides ... with ...** even when its containing package is not exported. The service provider mechanism is an integration point directly supported by the module system; it does not require exposing the implementation package as an API.

This yields several benefits:

- **Hide implementation details:** consumers cannot import implementation classes across module boundaries.
- **Freedom to refactor internally:** providers can rename classes, split packages, or restructure implementations without changing the service API.
- **Reduce coupling:** consumers depend only on interfaces, not on specific suppliers.
- **Support multiple providers:** multiple modules can register implementations for the same service type.
- **Control API surface:** only contract packages are exported; internal packages stay encapsulated.

Do not confuse a provider class being declared **public** with its containing package being exported. The **public** modifier governs accessibility under Java language access rules; the module descriptor continues to enforce package visibility across module boundaries.

## 7. Rules for Provider Classes

For a traditional provider class declared in **provides ... with ...**, the class must be public and have a public no-argument constructor so ServiceLoader can create an instance:

~~~java
public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The class can live in an unexported package. The provider module only needs to declare:

~~~java
provides com.acme.greeter.api.GreetingService
    with com.acme.greeter.provider.internal.DefaultGreetingService;
~~~

Another option is to use a provider method. The provider class listed in the descriptor can declare a parameterless **public static provider()** method returning the service type or a subtype:

~~~java
package com.acme.greeter.provider.internal;

import com.acme.greeter.api.GreetingService;

public final class GreetingProviderFactory {
    private GreetingProviderFactory() {
    }

    public static GreetingService provider() {
        return new VietnameseGreetingService();
    }
}
~~~

The descriptor then references the factory:

~~~java
provides com.acme.greeter.api.GreetingService
    with com.acme.greeter.provider.internal.GreetingProviderFactory;
~~~

A provider method is useful when service creation requires a factory, configuration, or implementation selection. The factory package can still remain unexported. When using a provider method, the class declared in **with** does not have to directly implement the service type; ServiceLoader invokes the provider method according to its rules.

## 8. Multiple Providers for the Same Service

JPMS allows multiple modules to supply the same service API. For example:

~~~java
module com.acme.greeter.english {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.english.internal.EnglishGreetingService;
}
~~~

And a Vietnamese provider:

~~~java
module com.acme.greeter.vietnamese {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.vietnamese.internal.VietnameseGreetingService;
}
~~~

Each provider keeps its implementation package private. The consumer still only declares:

~~~java
uses com.acme.greeter.api.GreetingService;
~~~

ServiceLoader may return multiple providers. Provider ordering should not be used as a mechanism for language selection or business priority if the application requires a deterministic choice. Add metadata/configuration or an explicit coordinator class when a specific provider must be selected.

## 9. Provider and Consumer Modules Do Not Need Direct Dependencies on Each Other

In a service design, the provider module depends on the service API; the consumer module also depends on the service API. There is no need to create direct dependencies from the consumer to individual providers:

~~~text
com.acme.app
    requires com.acme.greeter.api
    uses GreetingService

com.acme.greeter.provider
    requires com.acme.greeter.api
    provides GreetingService with InternalImplementation
~~~

If the consumer declares **requires com.acme.greeter.provider** just to invoke the implementation, it defeats provider substitutability and forces the application to know supplier details. When the service contract suffices, let ServiceLoader perform discovery.

In a plugin system, provider modules can be installed or added to the module path according to deployment configuration. The application can expand its set of providers without modifying consumer source code, as long as providers conform to the service contract and are resolved into the module layer.

## 10. Verifying Provider Registration

You can inspect the provider JAR's descriptor:

~~~bash
jar --describe-module --file mods/com.acme.greeter.provider.jar
~~~

The output should show:

- The provider module name.
- The **requires com.acme.greeter.api** dependency.
- The **provides com.acme.greeter.api.GreetingService with ...** line.
- No implementation package in the **exports** list.

You can enable module resolution logging when running:

~~~bash
java --show-module-resolution --module-path mods --bind-services \
    --module com.acme.app/com.acme.app.Main
~~~

If ServiceLoader does not find the provider, check in order:

1. Whether the provider module is on the module path or in the appropriate module finder source.
2. Whether the provider module is resolved into the same module layer as the consumer.
3. Whether the consumer descriptor declares **uses** for the exact service type.
4. Whether the provider descriptor declares **provides ... with ...** with the exact service and implementation names.
5. Whether the provider class has a valid public no-argument constructor or provider method.
6. Whether the provider depends on the right service API module and the service type has the same module/class identity as the consumer's.

If an implementation class triggers a package visibility error when the consumer tries to import it directly, that is a sign the consumer is depending on the implementation instead of using the service contract. In this architecture, the consumer does not need access to internal packages.

## 11. Distribution and Runtime Images

When packaging modular JARs, ship the service API, consumer, and selected providers for the application. Provider modules may not appear in the consumer's directly declared dependencies, so runtime configuration and resolution must ensure providers are bound.

When building a runtime image with **jlink**, you can use **--bind-services** to include the necessary provider modules in the image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --bind-services \
    --output runtime
~~~

On Windows, the module path uses a semicolon as the separator:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --bind-services --output runtime
~~~

Run the application in the runtime image:

~~~bash
runtime/bin/java --module com.acme.app/com.acme.app.Main
~~~

When distributing, verify that providers are actually resolved and service discovery works in the final image. An application running successfully inside an IDE does not prove that providers have been included in the release package.

## 12. Encapsulated Provider Design Checklist

When creating a service provider module, check:

- The service interface resides in an API package exported from the service API module.
- The consumer declares **uses** for the exact service type.
- The provider module declares **requires** on the service API module.
- The provider module registers the implementation with **provides ... with ...**.
- The provider class follows the public class/public no-arg constructor rules, or uses a valid provider method.
- The implementation package has no **exports** unless consumers need direct access.
- The consumer does not import implementation classes and does not declare direct dependencies on providers unnecessarily.
- The provider module is resolved into the module layer at runtime; use **--bind-services** when the launcher needs to bind providers on the module path.
- The runtime image or final distribution package contains the required providers.

A well-designed provider module publishes via the service contract and keeps implementation packages internal. **provides ... with ...** is the official registration mechanism that allows ServiceLoader to locate implementations without exporting the containing package. As a result, consumers depend only on the API, providers can change their implementations, and the module system preserves encapsulation boundaries.
