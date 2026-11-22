# Service Interface and Provider Implementation

In Java, a Service Provider Interface (SPI) is a design pattern where one module publishes a service contract and another module provides the implementation of that contract. The module using the service depends only on the interface; it does not need to know which specific class will perform the work. The Java Platform Module System (JPMS) supports this mechanism using the two directives `uses` and `provides`, combined with the `ServiceLoader` API.

This organization makes it possible to swap providers without modifying the consumer, allows multiple implementations to coexist, and keeps implementation packages internal. Familiar examples include JDBC drivers, logging backends, plugins, encoders, formatters, and deployment-environment adapters.

## 1. Distinguishing Service Interface, Consumer, and Provider

An SPI design typically has three roles:

- **Service interface:** a public contract describing a capability the application needs, such as `GreetingService`, `PaymentProcessor`, or `StorageProvider`.
- **Consumer:** a module that calls the service interface to perform work. The consumer knows the interface type but does not depend on the implementation class.
- **Provider:** a module that supplies a class implementing the service interface and registers that class with the module system.

The dependency flow looks like this:

```text
             +----------------------+
             |    Service API       |
             |  GreetingService     |
             +----------------------+
                    ^        ^
             requires|        |requires
                    |        |
          +---------+--+   +--+-------------+
          | Consumer   |   | Provider       |
          | uses SPI   |   | provides SPI  |
          +------------+   +----------------+
```

Both the consumer and the provider depend on the module containing the service interface. The consumer does not need to `requires` a specific provider module. The module system and `ServiceLoader` locate registered implementations when the application runs.

## 2. The Service Interface as a Stable Contract

The service interface should express the functionality the consumer needs, avoiding exposing implementation details such as internal libraries, private data structures, or how external systems are connected.

Example:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

In the API module's descriptor, export the package containing the interface:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

The `exports` directive allows consumers to import and call the public `GreetingService` type. This is a Java language-level API; it does not register any implementation on its own.

A good SPI usually keeps its contract small and focused. If the interface changes incompatibly, all providers must be updated or a backward-compatibility mechanism must be maintained. Therefore, clearly define parameters, return values, exceptions, and service lifecycle rules.

## 3. Provider Implementation

The provider creates a class implementing the interface:

```java
package com.acme.provider.internal;

import com.acme.spi.GreetingService;

public class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The provider class is public and has a public no-argument constructor so that `ServiceLoader` can instantiate it via the standard constructor mechanism. For a provider declared with `provides` in a named module, the package containing the implementation does not need to be exported to the consumer. The consumer only needs to see the service interface; provider instantiation is handled by the service loading mechanism.

Provider module descriptor:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.EnglishGreetingService;
}
```

The `provides ... with ...` directive registers the implementation. The part before `with` is the service type; the part after is one or more provider classes. A single module can register multiple providers for the same service.

A provider can supply multiple different services, as long as the implementations satisfy their respective contracts and are declared in the descriptor.

## 4. Consumer Declaring uses

A module using a service needs to declare `uses` for the service type it will load:

```java
module com.acme.consumer {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

`requires com.acme.spi` establishes readability so consumer code can reference the interface. `uses com.acme.spi.GreetingService` declares that the module needs to find providers for that service. The two directives serve distinct purposes.

The consumer uses `ServiceLoader`:

```java
package com.acme.consumer;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

        for (GreetingService service : loader) {
            System.out.println(service.greet("Java"));
        }
    }
}
```

The consumer works solely with `GreetingService`. It does not import `EnglishGreetingService`, does not invoke the provider constructor, and does not need to know the provider module's name. When a provider is discovered, `ServiceLoader` creates an instance and returns it under the interface type.

If no providers are found, the loop does not execute. The application must decide explicitly whether the service is optional or required: it can use a default implementation, report missing configuration, or stop with an appropriate error.

## 5. Complete Example with Three Modules

Source structure:

```text
src/
├── com.acme.spi/
│   ├── module-info.java
│   └── com/acme/spi/GreetingService.java
├── com.acme.provider/
│   ├── module-info.java
│   └── com/acme/provider/internal/EnglishGreetingService.java
└── com.acme.consumer/
    ├── module-info.java
    └── com/acme/consumer/Main.java
```

API module:

```java
// src/com.acme.spi/module-info.java
module com.acme.spi {
    exports com.acme.spi;
}
```

Provider module:

```java
// src/com.acme.provider/module-info.java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.EnglishGreetingService;
}
```

Consumer module:

```java
// src/com.acme.consumer/module-info.java
module com.acme.consumer {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

Compile all three modules from the directory containing `src`:

```shell
javac --module-source-path src -d out \
    -m com.acme.spi,com.acme.provider,com.acme.consumer
```

Run the consumer on the module path:

```shell
java --show-module-resolution --module-path out \
    --module com.acme.consumer/com.acme.consumer.Main
```

When resolving the module configuration, Java can locate observable provider modules that declare `provides` for a service used by a root module and include the matching providers in the configuration. Thus, the consumer does not have to declare a direct dependency on `com.acme.provider`. The `--show-module-resolution` option helps observe the modules resolved at startup.

The `com.acme.provider.internal` package is not exported. That remains valid: the provider implementation is not an API that consumers call directly. If you want the application to reference the provider class in source code, that is a different design and would require exposing the corresponding package.

## 6. A Service Can Have Multiple Providers

SPI allows multiple modules to provide implementations for the same interface. For example:

```java
module com.acme.provider.english {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.english.EnglishGreetingService;
}
```

```java
module com.acme.provider.vietnamese {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.vietnamese.VietnameseGreetingService;
}
```

The consumer can iterate over all providers:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

loader.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(service ->
        System.out.println(service.greet("Java"))
    );
```

You should not rely on provider order as a stable priority rule. If the application needs to select a specific provider, design an explicit selection mechanism, such as a configuration property, custom metadata, or a capability-identifying method on the interface.

If multiple providers are discovered, the consumer must decide whether it wants to use all of them, pick one based on configuration, or reject the case of multiple choices. Avoid silently picking the first element if ordering is not part of the contract.

## 7. ServiceLoader and Provider Methods

In addition to a public no-argument constructor, a named module can supply a provider via a public static provider method. With this approach, the provider class exposes a method named `provider` that returns the service type:

```java
package com.acme.provider.internal;

import com.acme.spi.GreetingService;

public class GreetingProvider {
    public static GreetingService provider() {
        return new EnglishGreetingService();
    }
}
```

The module descriptor registers the provider class:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.GreetingProvider;
}
```

A provider method is useful when creating the implementation requires a factory, configuration, or an object not created directly via a public constructor. The provider class must still satisfy `ServiceLoader`'s provider method rules; the method must be `public static`, take no parameters, and return a type compatible with the service type.

Choose a provider method only when it solves a specific instantiation need. For simple implementations, a public no-argument constructor is usually easier to understand.

## 8. SPI on the Classpath and META-INF/services Files

The service loading mechanism existed before JPMS. When providers are deployed on the classpath, they are typically registered using a configuration file:

```text
META-INF/services/com.acme.spi.GreetingService
```

The file lists the fully qualified name of each provider class, one provider per line:

```text
com.acme.provider.internal.EnglishGreetingService
com.acme.provider.internal.VietnameseGreetingService
```

The consumer can still use:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);
```

When running on the classpath, providers are located through `META-INF/services` configuration and the class loader. When running as a named module, providers can be registered directly via the `provides` directive in `module-info.java`, while consumers declare `uses`.

For libraries that need to support both the classpath and the module path, package and verify the appropriate metadata for each distribution mode. Do not assume `META-INF/services` files and module descriptors are always handled identically across every packaging style.

## 9. Common Errors and Diagnostics

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Provider not found | Provider module not resolved, missing `provides`, or incorrect classpath metadata | Check module path and descriptor/JAR |
| Consumer errors when calling `ServiceLoader` | Named module has not declared `uses` for the service type | Add `uses` to consumer descriptor |
| Provider cannot be instantiated | Provider class or constructor/provider method does not meet rules | Check public class, constructor, or provider method |
| Service interface fails to compile | Consumer missing `requires` on API module or API package not exported | Check API module and consumer descriptor |
| Consumer depends directly on implementation | Consumer code imports concrete provider class | Switch dependency to the service interface |
| Multiple implementations exist but wrong one is chosen | Application assumes provider order | Add an explicit provider selection policy |

You can inspect each JAR's descriptor:

```shell
jar --describe-module --file provider.jar
jar --describe-module --file consumer.jar
```

For a modular provider, check the `provides` entry. For a consumer, check the `uses` entry. If the application runs on the module path, also check the `--show-module-resolution` output to see whether the provider module actually participates in the runtime configuration.

## 10. SPI Design Principles

- Place the service interface in a dedicated API module and export the package containing the interface.
- Have the consumer declare `requires` on the API and `uses` for the service type.
- Have the provider declare `requires` on the API and `provides ... with ...` in its module descriptor.
- Keep the implementation in an internal package; do not export the provider package unless consumers need direct access.
- Keep the interface small and stable, with clear rules for lifecycle, errors, and thread-safety.
- Do not rely on provider ordering to decide which implementation is chosen.
- If supporting the classpath, provide a `META-INF/services` file with the exact service interface name.
- Verify module resolution and artifact metadata in the actual deployment environment.

SPI separates the contract from the implementation. When consumers depend only on the service interface, providers can be replaced, added, or distributed independently without tightly coupling consumers to concrete implementation classes. JPMS makes this relationship explicit with `uses` and `provides`, while `ServiceLoader` handles provider discovery and instantiation at runtime.
