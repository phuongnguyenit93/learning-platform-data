# Service provider interface and consumer

## 1. What are SPI and consumer?

In Java, a **Service Provider Interface (SPI)** is an interface or abstract contract describing a service for which multiple modules can supply different implementations. A **consumer** is a module that needs to use that service. A **provider** is a module that supplies a concrete implementation.

The three roles are decoupled:

- **SPI module** defines the service type known to both the consumer and the provider.
- **Consumer module** depends on the service type, requests the service with `uses`, and then discovers implementations using `ServiceLoader`.
- **Provider module** depends on the SPI, implements the service, and registers the implementation with `provides ... with ...`.

The consumer only needs to know the contract. It does not need to know the implementation class name or depend directly on the provider module. As a result, providers can be added, replaced, or removed without modifying the consumer, as long as the contract remains compatible.

The example below uses a `GreetingService` service: the consumer requests a greeting, and the provider decides the content of the greeting.

## 2. Module structure

The example consists of three named modules:

```text
src/
├── com.acme.greeting.spi/
│   ├── module-info.java
│   └── com/acme/greeting/spi/GreetingService.java
├── com.acme.greeting.provider.en/
│   ├── module-info.java
│   └── com/acme/greeting/provider/en/EnglishGreeting.java
└── com.acme.greeting.consumer/
    ├── module-info.java
    └── com/acme/greeting/consumer/Main.java
```

Dependency flow:

```text
com.acme.greeting.consumer
       | requires + uses
       v
com.acme.greeting.spi
       ^
       | requires + provides
com.acme.greeting.provider.en
```

The diagram shows that both modules know about the SPI. The consumer does not declare `requires com.acme.greeting.provider.en`; finding the provider is delegated to JPMS's service mechanism and `ServiceLoader`.

## 3. Defining the service contract in the SPI module

File `src/com.acme.greeting.spi/module-info.java`:

```java
module com.acme.greeting.spi {
    exports com.acme.greeting.spi;
}
```

File `src/com.acme.greeting.spi/com/acme/greeting/spi/GreetingService.java`:

```java
package com.acme.greeting.spi;

public interface GreetingService {
    String greet(String name);
}
```

The package containing the interface is `exports`-ed so that other modules can reference the `GreetingService` type. This is the public contract of the system. The SPI module does not need to know how many providers exist or where they are located.

A good SPI should describe the behavior the consumer needs, keep the API stable, and avoid exposing implementation details of individual providers in the contract.

## 4. Implementing and registering the provider

File `src/com.acme.greeting.provider.en/module-info.java`:

```java
module com.acme.greeting.provider.en {
    requires com.acme.greeting.spi;

    provides com.acme.greeting.spi.GreetingService
        with com.acme.greeting.provider.en.EnglishGreeting;
}
```

File `src/com.acme.greeting.provider.en/com/acme/greeting/provider/en/EnglishGreeting.java`:

```java
package com.acme.greeting.provider.en;

import com.acme.greeting.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Two important parts in the module descriptor:

- `requires com.acme.greeting.spi` allows the provider to reference the interface it implements.
- `provides GreetingService with EnglishGreeting` registers the provider class for the `GreetingService` service type.

When declaring a provider by class as in this example, the provider class must be `public` and have a public no-argument constructor. JPMS does not require the package containing the implementation to be `exports`-ed; the consumer does not call this class directly. That allows the provider to keep its implementation in an internal package.

A provider module can supply multiple service types. A service type can also have multiple providers; within a single `provides` directive, multiple provider classes can be listed, separated by commas.

## 5. Declaring the consumer and discovering the service

File `src/com.acme.greeting.consumer/module-info.java`:

```java
module com.acme.greeting.consumer {
    requires com.acme.greeting.spi;

    uses com.acme.greeting.spi.GreetingService;
}
```

The consumer needs `requires` on the SPI to compile and use the interface. The `uses` directive declares that this module will look up that service type at runtime.

File `src/com.acme.greeting.consumer/com/acme/greeting/consumer/Main.java`:

```java
package com.acme.greeting.consumer;

import com.acme.greeting.spi.GreetingService;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;
        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet(name));
        }

        if (!found) {
            System.out.println("No GreetingService provider was found.");
        }
    }
}
```

`ServiceLoader.load(GreetingService.class)` returns a `ServiceLoader` that can iterate over the discovered implementations. Loading and instantiating providers happens during iteration, so multiple providers can be handled without listing specific classes in the consumer.

Output with the English provider:

```text
Hello, Java!
```

The consumer does not import `EnglishGreeting`, does not call its constructor, and does not need to know the name of the provider module. It only works with `GreetingService`.

## 6. Compiling and running the example

From the directory containing the `src` directory, run:

```bash
javac --module-source-path src -d out \
  -m com.acme.greeting.spi,com.acme.greeting.provider.en,com.acme.greeting.consumer
```

After compiling, run the consumer's main class:

```bash
java --module-path out \
  -m com.acme.greeting.consumer/com.acme.greeting.consumer.Main
```

You can pass a name as an argument:

```bash
java --module-path out \
  -m com.acme.greeting.consumer/com.acme.greeting.consumer.Main "Ada"
```

When running on the module path, JPMS's service binding mechanism can bring matching provider modules into the module graph based on the services that resolved modules declare with `uses`. This is why the consumer does not need to declare `requires` on each provider. You can add `--show-module-resolution` to the `java` command to observe the module resolution process when troubleshooting.

## 7. How does ServiceLoader work?

At a typical usage level, the workflow consists of these steps:

1. The consumer declares `uses` for the service type in `module-info.java`.
2. The provider module declares `provides` and the corresponding implementation class.
3. The module system finds matching providers in the module graph; for named modules, service binding participates in resolution.
4. The consumer calls `ServiceLoader.load(ServiceType.class)`.
5. During iteration, `ServiceLoader` loads and instantiates the providers and returns them as the service interface type.

A few points to keep in mind:

- If no provider is found, the loop does not execute at all. Decide clearly whether the consumer should report an error, use a default value, or skip the service.
- There may be multiple providers. Do not rely on iteration order to determine which provider has the highest priority; if selection is needed, use configuration or an explicit selection rule.
- Provider loading can throw `ServiceConfigurationError` if a declaration or provider is invalid. The application can catch this error at an appropriate boundary to log or report a configuration issue.
- `ServiceLoader` caches loaded providers within its instance. Calling `reload()` clears the cache so that the next iteration reloads providers.
- If the application creates its own `ModuleLayer`, it can use `ServiceLoader.load(layer, GreetingService.class)` to find providers in the specified layer.

## 8. Named modules and the classpath

For named modules on the module path, service registration lives in `module-info.java` using `uses` and `provides`.

For applications running on the classpath or libraries using the traditional classpath mechanism, providers are typically registered via a file:

```text
META-INF/services/com.acme.greeting.spi.GreetingService
```

This file contains the fully qualified name of each provider class, one per line, for example:

```text
com.acme.greeting.provider.en.EnglishGreeting
```

These are two different registration mechanisms. When working with named modules, declare services in the module descriptor; when working with the classpath, check whether the `META-INF/services` file is included in the packaged artifact.

## 9. Common errors

| Symptom | Causes to check |
|---|---|
| Consumer fails to compile when referencing the service type | The SPI module has not `exports`-ed the package containing the interface, or the consumer has not `requires`-ed the SPI |
| Consumer reports that the module does not declare usage of the service | Missing `uses` directive in the consumer's `module-info.java` |
| Provider is not found | Missing `provides ... with ...`, wrong service type/provider class, provider module missing from the module path or not resolved |
| Provider cannot be instantiated | Provider class is not public, lacks a public no-argument constructor, or constructor throws an exception |
| Provider does not implement the contract properly | Provider class is not assignable to the service type or method signatures do not match |
| Consumer must be edited whenever a provider is added | Consumer depends directly on the implementation instead of depending only on the SPI |

When debugging, check all three places simultaneously: whether the service interface is exported properly, whether the consumer declares `uses`, and whether the provider declares `provides` with the right service type and implementation.

## 10. When should you use the SPI pattern?

SPI is suitable when an application needs to allow multiple implementations to follow a single contract, such as:

- Multiple database drivers providing a single data access interface.
- Multiple format parsers implementing a single data reading interface.
- Multiple encryption algorithms, converters, or plugins that can be added independently.
- A core application that needs to be extended by modules developed by other teams or third parties.

If the application only has a fixed single implementation and does not need an extension mechanism, calling the implementation directly may be simpler. SPI is useful when separating the contract from the implementation brings replaceability, extensibility, or independent provider deployment.

## Key takeaways

- **SPI** defines the shared contract.
- **Consumer** declares `requires` on the SPI and `uses` for the service type.
- **Provider** declares `requires` on the SPI and `provides` for the implementation.
- **ServiceLoader** discovers and loads providers by service type; the consumer does not need to depend directly on the provider module.
- In JPMS, the package containing the service interface must be exported; the implementation package can remain encapsulated.
