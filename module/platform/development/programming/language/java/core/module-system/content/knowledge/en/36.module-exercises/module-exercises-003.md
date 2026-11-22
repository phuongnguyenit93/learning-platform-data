# Registering Service Providers with uses and provides

## 1. Objectives

The Java Platform Module System (JPMS) has a service mechanism so that a module can use a contract without depending directly on each implementation. The consumer declares its need with **uses**; the module supplying an implementation registers it with **provides ... with ...**. The API module defines the shared service type.

This design pattern is commonly used when an application can swap implementations per environment or needs multiple providers implementing one service, for example:

- Sending notifications via SMTP, SMS, or external services.
- Reading JSON, XML, or CSV files.
- Storing data with multiple storage types.
- Integrating different payment gateways.
- Extending an application with trusted plugins.

After this lesson, you can create the three API, consumer, and provider modules; write the module descriptor for each role; run ServiceLoader to discover providers; include providers in the module graph; and handle cases with zero or multiple providers.

## 2. The Three-Module Model

Example using a greeting service:

~~~text
com.acme.greeting.api
    com.acme.greeting
        GreetingService
        GreetingRequest

com.acme.greeting.app
    com.acme.greeting.app
        Main

com.acme.greeting.provider
    com.acme.greeting.provider.internal
        DefaultGreetingService
~~~

The three modules have separate responsibilities:

| Module | Responsibility | Dependency |
|---|---|---|
| com.acme.greeting.api | Defines the service contract | Does not depend on consumer/provider |
| com.acme.greeting.app | Uses the service via ServiceLoader | requires API, uses service |
| com.acme.greeting.provider | Supplies an implementation | requires API, provides service |

Dependency relationship:

~~~text
             com.acme.greeting.api
                /             \
               /               \
       consumer app        provider module
          uses               provides
~~~

Both consumer and provider depend on the API module. The consumer does not need to know the concrete implementation class. The provider does not need to depend back on the consumer.

## 3. Creating the service API module

Create the structure:

~~~text
src/
  com.acme.greeting.api/
    module-info.java
    com/
      acme/
        greeting/
          GreetingService.java
          GreetingRequest.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting;
}
~~~

Service interface:

~~~java
package com.acme.greeting;

public interface GreetingService {
    String providerId();

    String greet(GreetingRequest request);
}
~~~

Request type:

~~~java
package com.acme.greeting;

public record GreetingRequest(String name) {
}
~~~

The package containing the service interface and request type must be exported so the consumer and provider can reference these types. Export only the contract package that needs to be public; do not place implementation classes in the API module.

### Designing the service contract

The contract should express the business capability the consumer wants to perform, without exposing how the provider implements it:

- Use neutral names such as GreetingService, PaymentGateway, or DocumentReader.
- Define request/response types belonging to the API module.
- Do not return classes specific to an SMTP library, database driver, or provider SDK.
- Specify business errors, timeouts, and synchronous/asynchronous semantics when needed.
- Keep the interface small so providers can implement it without depending on the consumer's framework.

For example, if the service interface returns SmtpMessage, the consumer already depends on SMTP details. Move the shared data to be exchanged into the API module.

## 4. Consumer declares its need with uses

Create the source:

~~~text
src/
  com.acme.greeting.app/
    module-info.java
    com/
      acme/
        greeting/
          app/
            Main.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.app {
    requires com.acme.greeting.api;

    uses com.acme.greeting.GreetingService;
}
~~~

The two directives serve different purposes:

- **requires** creates readability to the API module so the consumer can reference GreetingService and GreetingRequest.
- **uses** declares that the consumer uses the service type. This is the service-use declaration that the module system uses when resolving providers and ServiceLoader uses to locate implementations.

A named module calling ServiceLoader for a service type must declare the corresponding uses in the caller module's descriptor. Missing this directive can lead to a ServiceConfigurationError when ServiceLoader looks up providers.

Consumer code:

~~~java
package com.acme.greeting.app;

import com.acme.greeting.GreetingRequest;
import com.acme.greeting.GreetingService;

import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        GreetingService service = loader.findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No GreetingService provider is available"));

        System.out.println(
                service.greet(new GreetingRequest("Lan")));
    }
}
~~~

**ServiceLoader.load(GreetingService.class)** creates a ServiceLoader for the service type. **findFirst()** returns an Optional containing the first provider found; if there is no provider, the Optional is empty. The example above turns the missing-provider case into a startup error with a clear message.

You can iterate over all providers:

~~~java
for (GreetingService service :
        ServiceLoader.load(GreetingService.class)) {
    System.out.println(service.providerId());
}
~~~

The consumer only knows GreetingService. It does not import DefaultGreetingService and does not need to know the provider's internal package.

### uses must be in the module that actually calls ServiceLoader

If a helper module contains the code calling ServiceLoader, that module itself must declare uses for the service type. Another application module declaring uses does not automatically substitute for the declaration in the module making the call.

For code running on the classpath in the unnamed module, there is no module-info.java to declare uses. The uses rule here applies to named modules.

## 5. Provider registers an implementation with provides

Create the source:

~~~text
src/
  com.acme.greeting.provider/
    module-info.java
    com/
      acme/
        greeting/
          provider/
            internal/
              DefaultGreetingService.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.DefaultGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.greeting.provider.internal;

import com.acme.greeting.GreetingRequest;
import com.acme.greeting.GreetingService;

public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String providerId() {
        return "default";
    }

    @Override
    public String greet(GreetingRequest request) {
        return "Hello, " + request.name() + "!";
    }
}
~~~

For a constructor-based provider class, the provider must be public and have a public no-argument constructor for ServiceLoader to instantiate it. The class must implement the service type named in provides.

### No need to export the implementation package

The package com.acme.greeting.provider.internal does not need to be exported just for ServiceLoader to locate and instantiate the provider:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.DefaultGreetingService;
}
~~~

No need to add:

~~~java
exports com.acme.greeting.provider.internal;
~~~

Registering the provider in the module descriptor allows the service mechanism to access the provider under JPMS's dedicated rules. Keeping the implementation package unexported helps avoid turning internal classes into an API that other modules can depend on directly.

## 6. Provider method instead of constructor

A named module can register a provider class that has a public static method named **provider** returning the service type. This approach fits when a factory is needed or implementation initialization goes through configuration.

Example provider class:

~~~java
package com.acme.greeting.provider.internal;

import com.acme.greeting.GreetingService;

public final class GreetingServiceFactory {

    private GreetingServiceFactory() {
    }

    public static GreetingService provider() {
        return new DefaultGreetingService(loadPrefix());
    }

    private static String loadPrefix() {
        return "Hello";
    }
}
~~~

Module descriptor:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.GreetingServiceFactory;
}
~~~

In the provider method case, the class named in provides does not necessarily have to directly implement the service interface. It must be a valid provider class and have a public static no-argument method named provider with a return type assignable to the service type.

Distinguishing the two forms:

| Form | Provider class | How the service is created |
|---|---|---|
| Constructor | Public class implementing the service, with a public no-arg constructor | ServiceLoader instantiates the provider |
| Provider method | Public class with public static provider() returning the service type | ServiceLoader invokes the factory method |

Choose one form suited to the initialization style. Do not declare conflicting mechanisms simultaneously for the same provider.

## 7. Compiling the three modules

With the source structure above, multiple modules can be compiled in a single javac invocation:

~~~text
javac
  --module-source-path src
  -d mods
  -m com.acme.greeting.api,com.acme.greeting.app,com.acme.greeting.provider
~~~

After compiling, the output directory has a structure similar to:

~~~text
mods/
  com.acme.greeting.api/
    module-info.class
    com/acme/greeting/
      GreetingService.class
      GreetingRequest.class
  com.acme.greeting.app/
    module-info.class
    com/acme/greeting/app/
      Main.class
  com.acme.greeting.provider/
    module-info.class
    com/acme/greeting/provider/internal/
      DefaultGreetingService.class
~~~

Meaning of the options:

- **--module-source-path src**: specifies where the module source hierarchy resides.
- **-d mods**: places class output.
- **-m**: lists the modules to compile in the invocation.

If using a build tool, the corresponding configuration must ensure the three modules have proper dependencies and the provider is included in the runtime graph. Do not place the provider implementation in the consumer's source tree just so ServiceLoader can find it.

## 8. Including the provider in the module graph at runtime

Putting the provider JAR or compiled module on the module path is not enough in every configuration. The provider must be resolved into the module layer that ServiceLoader searches.

You can add the provider module as an explicit root module at launch:

~~~text
java
  --module-path mods
  --add-modules com.acme.greeting.provider
  --module com.acme.greeting.app/com.acme.greeting.app.Main
~~~

Here:

- The main module is com.acme.greeting.app.
- The provider module is added to the graph via --add-modules.
- The API module is resolved because both consumer and provider require it.
- ServiceLoader in the consumer can discover providers resolved in the same layer.

If the provider is not in the module layer being searched, ServiceLoader cannot detect it merely because a JAR file exists in some folder on the machine.

### Service binding and resolveAndBind

The module system also has a service binding mechanism when resolving module configurations. The **Configuration.resolveAndBind(...)** API performs resolution combined with locating providers for services used by already-resolved modules.

During binding, provider modules can be added to the graph; dependencies of providers are also resolved. A newly added provider may use other services, causing the process to continue adding matching providers.

When an application creates a ModuleLayer itself, consider resolveAndBind if the goal is to automatically bring providers of used services into the configuration. If you want strict control over the implementation list, you can add provider modules as explicit roots via configuration.

For custom runtime images, jlink has the **--bind-services** option to request service binding when creating the image. If this option is not enabled, add required providers with --add-modules or ensure they are required via the dependency graph.

## 9. Multiple providers for the same service

Another module can provide the same GreetingService:

~~~java
module com.acme.greeting.formal {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.formal.internal.FormalGreetingService;
}
~~~

If both providers are resolved in the module layer, ServiceLoader can discover both:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.providerId());
}
~~~

Do not use provider discovery order as a business priority rule. Provider order is not a stable selection contract for applications.

If you need to select a provider by configuration:

~~~java
String configuredId = "formal";

GreetingService selected = ServiceLoader
        .load(GreetingService.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(service -> service.providerId().equals(configuredId))
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Configured provider is unavailable: " + configuredId));
~~~

In a real system, configuredId should come from controlled configuration. If the provider does not exist, throw a clear error or apply a designed fallback. Do not silently pick an arbitrary implementation.

If the application requires exactly one provider, count and validate the number of providers found. If multiple providers are valid, define explicit selection criteria based on capability, request type, or deployment configuration.

## 10. ServiceLoader with a separate ModuleLayer

A plugin application can create its own module layer to load providers independently from the boot layer:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

The overload taking a ModuleLayer restricts the search to the selected layer and its parent layers according to the ServiceLoader contract.

When creating a separate layer, pay attention to:

- The Service API must be properly shared between consumer and provider.
- The provider module must be present in the Configuration used to create the layer.
- The consumer module must declare uses if code in that named module calls ServiceLoader.
- Do not accidentally create two independent copies of the service API in two layers if they need to exchange the same service type.
- Manage layer lifecycle and provider resources when plugins are unloaded or replaced.

Not every application needs a separate ModuleLayer. For a simple modular application, the default module layer is usually sufficient.

## 11. Providers on the classpath and named modules

There are two common ways to register a provider:

### Named module

Use module-info.java:

~~~java
provides com.acme.greeting.GreetingService
    with com.acme.greeting.provider.internal.DefaultGreetingService;
~~~

This is the appropriate registration method for a provider residing in a named module.

### Classpath

Providers on the classpath typically use a service configuration file:

~~~text
META-INF/services/com.acme.greeting.GreetingService
~~~

The file content is the fully qualified name of the provider class:

~~~text
com.acme.greeting.provider.internal.DefaultGreetingService
~~~

ServiceLoader supports both forms, but the registration method and module access rules differ. Do not create a META-INF/services file to replace a module descriptor for a named module when the goal is to declare the provider via JPMS.

## 12. Error handling and lifecycle

### No provider found

ServiceLoader does not require a provider to be present. When a service is optional, the consumer can check the Optional and use a fallback:

~~~java
Optional<GreetingService> provider =
        ServiceLoader.load(GreetingService.class).findFirst();

if (provider.isEmpty()) {
    // Choose the designed fallback behavior.
}
~~~

If the service is mandatory, fail startup or return a meaningful error. Do not let the error surface only later on a critical request.

### Invalid provider or initialization failure

ServiceLoader can throw **ServiceConfigurationError** if the provider configuration is malformed, the provider is invalid, or initialization fails.

Log enough information to identify the service type and the failing provider, but do not log secrets or sensitive data from configuration.

### Providers opening resources

A provider may open connections, threads, or clients. ServiceLoader is not a full dependency injection container and does not automatically manage the lifecycle of provider resources.

If a service needs shutdown or complex lifecycle management, design an explicit lifecycle management API or let an application container manage the provider. Clarify who initializes, who closes, and whether the provider is thread-safe.

### ServiceLoader and concurrency

Do not assume a ServiceLoader instance can be used concurrently by multiple threads without synchronization. The API documentation does not guarantee ServiceLoader is thread-safe. You can create a dedicated instance per usage scope or synchronize access if sharing is required.

## 13. Common Errors

### Forgetting requires API module

Consumer or provider cannot read the service interface. Add requires to the API module in the corresponding descriptor.

### Forgetting exports API package

The package containing the service type is not exported so other modules cannot reference the contract. Export the right API package.

### Forgetting uses

A named module calls ServiceLoader without declaring uses for the service type. Add uses to the module containing the call.

### Forgetting provides

The provider class exists, but the provider module does not register the service in its descriptor. Add provides ... with ....

### Invalid provider class

For constructor-based providers, the class must be public, implement the service type, and have a public no-argument constructor. If a factory is needed, use a valid provider method.

### Over-exporting the implementation package

ServiceLoader does not require exporting the implementation package just to discover the provider. Keep internal packages unexported if no other API needs access.

### Provider module not resolved

The module path has the provider JAR, but the module layer does not contain the provider. Add the provider to root modules or use resolveAndBind when service binding is desired.

### Consumer depends on implementation

The consumer declares requires to a concrete provider and calls the class directly. Move the dependency to the API module and use uses/ServiceLoader.

### Selecting provider by order

Do not treat the first provider as a business-meaningful default provider. Select based on configuration or defined capabilities.

## 14. Implementation Workflow

1. Create the API module containing the service interface and request/response types.
2. Export the package containing the contract.
3. Create the consumer module, declaring requires API and uses service type.
4. Write the consumer calling ServiceLoader and handling the missing-provider case.
5. Create the provider module, declaring requires API and provides service type with implementation.
6. Place the implementation in an internal package; export only if there is an independent API need.
7. Verify the provider class has a valid constructor or a contract-compliant provider method.
8. Compile the modules and inspect the module descriptors in the output.
9. Include the provider in the runtime module graph or module layer.
10. Run a test with ServiceLoader and confirm the provider is discovered.
11. Test cases with zero providers, multiple providers, and provider initialization failures.
12. Run integration tests on a module path or runtime image configuration close to production.

## 15. Service Provider Registration Checklist

- Does the API module have an exported service interface?
- Does the consumer have requires API module and uses for the right service type?
- Does the provider have requires API module and provides for the right service type?
- Does the provider class have a public no-arg constructor or a valid provider method?
- Can the implementation package remain unexported?
- Does the consumer avoid requiring the provider implementation directly?
- Is the provider module resolved into the layer that ServiceLoader searches?
- Are multiple providers selected according to an explicit policy?
- Is there clear behavior for missing or failing providers?
- Are provider resources and lifecycle managed?
- Do integration tests run on an actual module path or runtime image?

**Remember:** the API module defines the service contract; the consumer declares **requires + uses**; the provider declares **requires + provides**. Bring the provider into the right module layer so ServiceLoader discovers it. Keep the consumer depending on the contract and keep the implementation in an internal package so providers can be swapped without coupling the consumer to implementation details.

## References

- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java Language Specification, Java SE 21 — Service Providers and Module Declarations: https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-7.html
- Oracle Java SE 21 — The java Command, module selection and module path: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java SE 21 API — Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261