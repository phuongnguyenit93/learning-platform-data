# Provider Constructors and Instantiation Requirements

In the Java Platform Module System (JPMS), `uses` and `provides` describe the relationship between a module consuming a service and a module providing an implementation of that service. When `ServiceLoader` finds a provider, it needs a valid way to instantiate the service object. For providers declared in `module-info.java`, Java supports two mechanisms: a **public no-argument constructor** or a **public static provider() factory method**.

Understanding these instantiation rules helps avoid `ServiceConfigurationError` when a module descriptor declares a provider but the provider class does not satisfy `ServiceLoader`'s contract.

## 1. What Is a Provider?

Suppose an application depends on an abstraction:

    package com.example.spi;

    public interface GreetingService {
        String greet(String name);
    }

The module containing this interface exposes the service so other modules can read it:

    module com.example.spi {
        exports com.example.spi;
    }

A provider module supplies an implementation of `GreetingService`. The consuming module only needs to know the service interface; it does not need to depend directly on the concrete implementation class.

In JPMS, the provider module declares:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.EnglishGreetingService;
    }

The `provides ... with ...` directive states that this module provides an implementation for the named service. The name after `with` is the provider class that `ServiceLoader` will use.

The consuming module declares:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.GreetingService;
    }

The `uses` directive indicates that the app module needs to find providers for the service. The application does not need to declare `requires com.example.greeting.provider;` just to invoke the service via ServiceLoader.

## 2. First Approach: Public No-Argument Constructor

For a provider class declared in `provides`, the traditional approach is to have a public constructor that takes no parameters.

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class EnglishGreetingService implements GreetingService {

        public EnglishGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

Key requirements to remember:

- The provider class must be `public`.
- The provider class must have a `public` no-argument constructor.
- The provider class must implement the service type declared in `provides`.
- The constructor must be callable to instantiate the provider; a constructor that only accepts parameters does not satisfy this rule.

If no constructor is declared, Java generates a default constructor with access matching the class. For a `public` class, the default constructor also has `public` access. However, writing the constructor explicitly makes the instantiation contract required by ServiceLoader clear to readers.

The following example does not meet the requirements:

    public final class InvalidGreetingService implements GreetingService {

        private InvalidGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

A private constructor is not a public no-argument constructor, so ServiceLoader cannot use the traditional provider instantiation approach. A constructor that only takes parameters is also invalid for this approach.

## 3. When Does ServiceLoader Instantiate a Provider?

The application locates providers using `ServiceLoader`:

    package com.example.app;

    import com.example.spi.GreetingService;
    import java.util.ServiceLoader;

    public class Main {
        public static void main(String[] args) {
            ServiceLoader<GreetingService> loader =
                    ServiceLoader.load(GreetingService.class);

            for (GreetingService service : loader) {
                System.out.println(service.greet("Phuong"));
            }
        }
    }

`ServiceLoader.load(...)` creates a loader object to locate matching providers. Provider discovery and instantiation happen lazily: a provider is created when the program iterates over the results or requests that provider, such as in the loop above.

ServiceLoader caches providers already discovered within a loader instance. If `reload()` is called, the cache is cleared and the loader will rediscover providers on the next iteration.

A provider constructor is not invoked simply because the application starts or because the module descriptor contains a `provides` line. It is invoked when ServiceLoader actually needs to create an instance of the provider.

## 4. Complete Example with a Public No-Argument Constructor

Source structure:

    src/
    ├── com.example.spi/
    │   ├── module-info.java
    │   └── com/example/spi/GreetingService.java
    ├── com.example.greeting.provider/
    │   ├── module-info.java
    │   └── com/example/greeting/provider/EnglishGreetingService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

File `src/com.example.spi/module-info.java`:

    module com.example.spi {
        exports com.example.spi;
    }

File `src/com.example.spi/com/example/spi/GreetingService.java`:

    package com.example.spi;

    public interface GreetingService {
        String greet(String name);
    }

File `src/com.example.greeting.provider/module-info.java`:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.EnglishGreetingService;
    }

File `src/com.example.greeting.provider/com/example/greeting/provider/EnglishGreetingService.java`:

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class EnglishGreetingService implements GreetingService {

        public EnglishGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.GreetingService;
    }

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.spi.GreetingService;
    import java.util.ServiceLoader;

    public class Main {
        public static void main(String[] args) {
            ServiceLoader<GreetingService> loader =
                    ServiceLoader.load(GreetingService.class);

            loader.forEach(service ->
                    System.out.println(service.greet("Phuong")));
        }
    }

Compile from the directory containing `src`:

    javac --module-source-path src -d out
        -m com.example.spi,com.example.greeting.provider,com.example.app

Run the application and add the provider module to the resolved module set:

    java --module-path out
        --add-modules com.example.greeting.provider
        -m com.example.app/com.example.app.Main

Output:

    Hello, Phuong

In this example, the provider package does not need an `exports` directive. The module descriptor declares the provider via `provides`, and ServiceLoader handles loading and instantiating the provider through the module service mechanism. The application only accesses the service interface exported by the SPI module.

## 5. Second Approach: Public Static provider() Factory Method

For providers declared in a module descriptor, Java also allows the provider class to supply a factory method named exactly `provider`.

Method rules:

- The provider class must be `public`.
- The method must be `public static`.
- The method takes no parameters.
- The return type must be the service type or a subtype assignable to the service type.
- ServiceLoader calls this method to obtain the service instance instead of invoking the provider class's constructor.

Example:

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class GreetingProvider {

        private GreetingProvider() {
        }

        public static GreetingService provider() {
            return new EnglishGreetingService();
        }
    }

Here, `GreetingProvider` does not directly implement `GreetingService`. It acts as the provider class and supplies the instance via `provider()`. The constructor of `GreetingProvider` can be private because ServiceLoader uses the factory method rather than instantiating the provider class itself.

Module descriptor:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.GreetingProvider;
    }

`EnglishGreetingService` is the actual implementation returned by the factory. It must be compatible with the `GreetingService` type; how it is created can be controlled by the provider method.

This approach is useful when instantiating the service requires configuration, implementation selection, caching, or constructing an object through an internal factory. The provider method can encapsulate instance creation logic without forcing ServiceLoader to invoke the provider class constructor.

Note: the provider method mechanism is for providers declared with `provides` in a named module. Providers declared in `META-INF/services` configuration files on the classpath must follow the public no-argument constructor rule.

## 6. Comparing the Two Instantiation Approaches

| Criterion | Public no-arg constructor | `provider()` factory method |
|---|---|---|
| Provider class | Public | Public |
| Service creation point | Provider class constructor | Factory method |
| Signature | Public constructor, no arguments | `public static`, no arguments, named `provider` |
| Must provider class implement service? | Yes | Not required if the factory returns a compatible service type |
| Provider class constructor | Must be public and no-argument | Not invoked by ServiceLoader; can be private |
| Best suited for | Simple implementations, direct instantiation | Controlling or encapsulating instantiation logic |

When a provider class has both a valid constructor and a valid `provider()` method, ServiceLoader uses the provider method according to the named-module provider contract. Choose one clear approach so readers understand the primary instantiation point.

## 7. Providers on the Classpath and META-INF/services Files

Not all Java applications use named modules. In traditional classpath applications, ServiceLoader locates providers via a configuration file:

    META-INF/services/com.example.spi.GreetingService

The file lists the fully qualified name of each provider class, one provider per line:

    com.example.greeting.provider.EnglishGreetingService

Provider classes declared this way must implement the service type and have a public no-argument constructor. The `provider()` factory method mechanism in module descriptors does not replace the constructor rule for providers listed in classpath configuration files.

Therefore, when migrating a library from the classpath to a named module, recheck the provider declaration and instantiation contract. A class with only a static `provider()` method may work when declared with `provides` in a named module, yet fail the traditional provider class rules in `META-INF/services`.

## 8. Common Instantiation Errors

ServiceLoader may throw `ServiceConfigurationError` when it detects an invalid provider configuration or fails to create an instance. Common causes include:

1. **Missing public no-argument constructor:** the provider uses the constructor approach but only declares a private or parameterized constructor.
2. **Non-public provider class:** the class listed after `with` does not have public access.
3. **Wrong service type:** the constructor-based provider does not implement the declared service.
4. **Invalid provider method:** the method is not named `provider`, is not public, is not static, takes parameters, or returns an incompatible type.
5. **Missing provider module in runtime configuration:** the provider module is absent or not resolved into the module layer being searched.
6. **Missing `uses` in the consuming module:** the module calls ServiceLoader, but its module descriptor does not declare the corresponding service in `uses`.
7. **Service type is not readable:** the consuming module lacks readability to the module containing the service interface.
8. **Constructor or factory throws an exception:** the provider is found, but initialization fails.

When encountering an error, read the `ServiceConfigurationError` message to identify which provider failed, then verify the module descriptor and the corresponding constructor or provider method signature.

## Key Takeaways

- Providers are declared in named modules using `provides Service with Provider;`.
- The provider class must be public.
- The constructor approach requires a public no-argument constructor; the provider class must also implement the service type.
- Named-module providers can use a parameterless `public static provider()` method returning a compatible service type; in that case, ServiceLoader uses the factory method.
- Providers declared in `META-INF/services` on the classpath still require a public no-argument constructor.
- ServiceLoader instantiates providers when iterating or retrieving them, following lazy loading.

When designing a provider, clearly determine which module supplies the service, how the provider is declared, and which instantiation entry point ServiceLoader will use.
