# Running ServiceLoader on the Module Path

## 1. Objectives

Java ServiceLoader allows a module to use a service interface without directly depending on the implementation classes. When running on the Java Platform Module System (JPMS), the service API, consumer module, and provider module can be packaged as separate named modules.

For ServiceLoader to locate implementations on the module path, three parts must work together:

1. The API module exposes the service interface.
2. The consumer module declares the service it needs using the `uses` directive.
3. The provider module declares the implementation using the `provides ... with ...` directive.

When launching the application, the module resolver must see the provider module and include it in the module graph. Only then can ServiceLoader discover the provider and supply service instances.

This lesson builds a complete three-module example, compiles it into modular JARs, runs the application on the module path, and handles common errors.

After this lesson, you can:

- Distinguish among service API, consumer, and provider modules.
- Write `uses` and `provides ... with ...` properly in `module-info.java`.
- Compile multiple modules and package them into modular JARs.
- Run the application using `java --module-path` and `--module`.
- Use `ServiceLoader.load` to obtain providers.
- Inspect module resolution and diagnose when ServiceLoader fails to find a provider.

## 2. Project Structure

We will build a greeting application with three modules:

| Module | Responsibility |
| --- | --- |
| `com.example.greeting.api` | Declares the service interface shared by consumer and provider. |
| `com.example.greeting.provider` | Supplies an implementation for the service. |
| `com.example.greeting.app` | Launches the application and asks ServiceLoader to locate providers. |

Source tree structure:

~~~text
service-loader-demo/
└── src/
    ├── com.example.greeting.api/
    │   ├── module-info.java
    │   └── com/example/greeting/api/GreetingService.java
    ├── com.example.greeting.provider/
    │   ├── module-info.java
    │   └── com/example/greeting/provider/FormalGreetingService.java
    └── com.example.greeting.app/
        ├── module-info.java
        └── com/example/greeting/app/Main.java
~~~

Each module has a `module-info.java` at the root of the module's source tree. The module directory name matches the module name declared in the descriptor.

## 3. Declaring the service API

The API module specifies that the package containing the interface is exported:

~~~java
// src/com.example.greeting.api/module-info.java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Service interface:

~~~java
// src/com.example.greeting.api/com/example/greeting/api/GreetingService.java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

The API module does not need to know which implementation will be used. It only defines a shared contract for consumers to call and providers to implement.

The package containing the interface must be exported because the consumer needs to read the `GreetingService` type, and the provider needs to implement that interface.

## 4. Declaring the provider module with provides

The provider module depends on the API and publishes its implementation in the descriptor:

~~~java
// src/com.example.greeting.provider/module-info.java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
~~~

Implementation:

~~~java
// src/com.example.greeting.provider/com/example/greeting/provider/FormalGreetingService.java
package com.example.greeting.provider;

import com.example.greeting.api.GreetingService;

public final class FormalGreetingService implements GreetingService {

    public FormalGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The `provides S with P` directive means this module supplies implementation `P` for service type `S`.

In this example, the provider module declares `requires com.example.greeting.api` to read the service interface. The implementation package `com.example.greeting.provider` does not need to be exported just for ServiceLoader to discover the provider registered in the module descriptor. The module system can discover the provider via the `provides` metadata while keeping the implementation package encapsulated.

With constructor-based instantiation, the provider class must have a public no-argument constructor. JPMS also supports static provider methods per ServiceLoader rules, though this example uses a constructor for simplicity.

## 5. Declaring the consumer module with uses

The application module reads the API and declares the service to look up:

~~~java
// src/com.example.greeting.app/module-info.java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
~~~

The `uses` directive states that the app module uses the `GreetingService` service type. It does not name the provider module and does not create an explicit dependency from app to `com.example.greeting.provider`.

This is the key point of ServiceLoader: the consumer depends on the contract, while the implementation can be replaced with another provider without editing consumer code.

## 6. Writing code that calls ServiceLoader

Main class:

~~~java
// src/com.example.greeting.app/com/example/greeting/app/Main.java
package com.example.greeting.app;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
            ServiceLoader.load(GreetingService.class);

        boolean found = false;

        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet("Java Module System"));
        }

        if (!found) {
            throw new IllegalStateException(
                "No GreetingService provider is available"
            );
        }
    }
}
~~~

Execution steps:

1. `ServiceLoader.load(GreetingService.class)` creates a loader for the service type.
2. The loader discovers available providers in the current module/class loader environment.
3. The loop retrieves each service instance.
4. The consumer calls methods on the `GreetingService` interface without referencing the implementation class.

Because app is a named module and uses the service type, the `uses` directive in `module-info.java` is mandatory. If missing, ServiceLoader can throw `ServiceConfigurationError` when checking permission to use the service.

If only one provider is needed, you can use:

~~~java
GreetingService service = ServiceLoader
    .load(GreetingService.class)
    .findFirst()
    .orElseThrow(() ->
        new IllegalStateException("No GreetingService provider found")
    );
~~~

If the application may have multiple implementations, decide explicitly whether to use all providers or choose one based on metadata/configuration. Do not rely on discovery order as a stable priority mechanism.

## 7. Compiling the modules from the source tree

From the `service-loader-demo` root directory, create the output directory and compile the three modules:

~~~bash
javac --module-source-path src -d mods -m com.example.greeting.api,com.example.greeting.provider,com.example.greeting.app
~~~

Where:

- `--module-source-path src` specifies the location of the modules' source trees.
- `-d mods` puts compiled output into the `mods` directory.
- `-m` specifies the modules to compile.

After compilation, the output structure looks like:

~~~text
mods/
├── com.example.greeting.api/
│   ├── module-info.class
│   └── com/example/greeting/api/GreetingService.class
├── com.example.greeting.provider/
│   ├── module-info.class
│   └── com/example/greeting/provider/FormalGreetingService.class
└── com.example.greeting.app/
    ├── module-info.class
    └── com/example/greeting/app/Main.class
~~~

These are exploded modules: each module is a directory containing `module-info.class` and the compiled classes.

If the source tree is not structured properly, the compiler may report that a module or package cannot be found. Check module directory names, `module-info.java` placement, package declarations, and `requires`/`exports` directives.

## 8. Running the application using the module path

Use the Java launcher with the module path pointing to the `mods` directory:

~~~bash
java --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Short form:

~~~bash
java -p mods -m com.example.greeting.app/com.example.greeting.app.Main
~~~

In the command:

- `--module-path mods` or `-p mods` specifies where the compiled modules are located.
- `--module` or `-m` selects the application module and main class.
- The part before `/` is the module name.
- The part after `/` is the fully qualified name of the main class.

Expected output:

~~~text
Hello, Java Module System!
~~~

When the launcher resolves the module graph, the consumer declares `uses` and the provider module has a matching `provides`. The launcher's service binding mechanism can bring observable provider modules into the configuration so ServiceLoader can discover them.

The provider module must lie within the module path visible to the launcher. Simply having a JAR file in a directory not specified in the module path is not enough.

## 9. Packaging into modular JARs

Instead of running exploded modules, you can package each module into a modular JAR.

~~~bash
jar --create --file mods/com.example.greeting.api.jar -C mods/com.example.greeting.api .
jar --create --file mods/com.example.greeting.provider.jar -C mods/com.example.greeting.provider .
jar --create --file mods/com.example.greeting.app.jar -C mods/com.example.greeting.app .
~~~

The JAR files still contain `module-info.class`, so the module name is determined by the descriptor rather than depending on the file name.

Run the application from the modular JARs:

~~~bash
java --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

The module path can contain modular JARs or exploded modules. Both can be used to resolve named modules if their structure is valid.

You can inspect the provider's descriptor:

~~~bash
jar --describe-module --file mods/com.example.greeting.provider.jar
~~~

The output should show the module name and the `provides com.example.greeting.api.GreetingService with ...` directive.

## 10. ServiceLoader.load and ModuleLayer

The earlier example used:

~~~java
ServiceLoader.load(GreetingService.class)
~~~

This uses the thread context class loader to search for providers in the current loader environment. For applications running on the standard module path, this is usually the simplest approach.

If the application creates its own module layer using the `ModuleLayer` API, use the overload taking a layer:

~~~java
ServiceLoader<GreetingService> services =
    ServiceLoader.load(customLayer, GreetingService.class);
~~~

This overload searches for providers in the specified layer and its ancestor layers. This is useful when plugins or providers are loaded into a dynamic layer, separate from the boot layer.

Conceptual example:

~~~java
ModuleLayer customLayer = /* resolved and defined layer */;
ServiceLoader<GreetingService> services =
    ServiceLoader.load(customLayer, GreetingService.class);
~~~

The layer must contain or see the appropriate provider module. Creating a layer does not automatically guarantee the provider is present: the module finder must locate the module, the configuration must resolve that module, and the descriptor must register the service properly.

Do not default to `ServiceLoader.load(service)` if the provider lives in a custom layer that the thread context class loader does not represent. Choose the overload matching where the provider is loaded.

## 11. How do named module and classpath providers differ?

ServiceLoader supports both named modules and the traditional classpath, but provider registration differs.

| Environment | Provider registration method |
| --- | --- |
| Named module on the module path | `provides Service with Provider` directive in `module-info.java`. |
| Classpath/unnamed module | `META-INF/services/<fully-qualified-service-name>` file containing the fully qualified provider class name. |

Example service configuration file on the classpath:

~~~text
META-INF/services/com.example.greeting.api.GreetingService
~~~

Content:

~~~text
com.example.greeting.provider.FormalGreetingService
~~~

For a modular JAR used as a named module, declare `provides` in the module descriptor. Do not rely on a `META-INF/services` file instead of the descriptor for a named provider module.

A consumer on the classpath has no `module-info.java`, so it does not declare `uses`. A consumer that is a named module must declare `uses` for the service type it uses.

## 12. Inspecting module resolution when providers do not appear

If the program cannot find a provider, check layer by layer.

### Inspecting module descriptors

View the consumer's descriptor:

~~~bash
java --module-path mods --describe-module com.example.greeting.app
~~~

Confirm the app module has `uses com.example.greeting.api.GreetingService`.

View the provider's descriptor:

~~~bash
java --module-path mods --describe-module com.example.greeting.provider
~~~

Confirm the provider has `provides` for the right service type and the implementation class has the right package/name.

### Checking whether the module is observable

~~~bash
java --module-path mods --list-modules
~~~

The name `com.example.greeting.provider` should appear in the set of observable modules. If not, check the module path, modular JAR/exploded module structure, and module name in the descriptor.

### Viewing the resolved graph at launch

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

The output helps observe root modules, dependencies, and provider binding information during launcher resolution. If the provider is not brought into the graph, check `uses`, `provides`, module finder, and module path scope.

### Distinguishing provider-not-found from initialization failure

If the provider was discovered but its constructor or provider method fails, the issue is no longer simply the module path. ServiceLoader can throw `ServiceConfigurationError` if provider configuration is invalid, the class cannot be loaded, or the instance cannot be created.

Inspect the exception and root cause, including the constructor, runtime dependencies, module access permissions, and class loader. Do not simply catch all errors and return an empty list, as that hides configuration bugs.

## 13. Common Errors

**Consumer missing uses**

A named module calls ServiceLoader without declaring `uses` for the service type. Add the directive to the consumer's `module-info.java` and recompile.

**Provider missing provides**

The provider class implements the interface, but the module descriptor does not register it. Add `provides Service with Provider` to the provider module's descriptor.

**Provider not on the module path**

The launcher cannot find the provider module if the module path does not contain the appropriate artifact. Add the proper directory or modular JAR to `--module-path`.

**Wrong service type**

The consumer uses one interface while the provider registers another, even if the implementation class name looks right. Check the fully qualified name of the service type in both descriptors.

**Provider class cannot be instantiated**

Check the public no-argument constructor or provider method, implementation dependencies, and root exception. This is a provider initialization error rather than necessarily a resolution error.

**Using the wrong loader or layer**

The provider is loaded in a custom ModuleLayer, yet the code looks up via the context class loader of another layer. Use `ServiceLoader.load(layer, Service.class)` with the right layer.

**Implementation package not exported**

Normally there is no need to export the package containing the provider class just for ServiceLoader to discover a provider declared with `provides`. Only export the package if another module needs to access public APIs in that package.

## 14. Key Takeaways

- The API module exports the service interface.
- The consumer module declares `uses ServiceType;`.
- The provider module declares `provides ServiceType with ProviderClass;` and reads the API module using `requires`.
- Compile modular source trees with `javac --module-source-path`; run with `java --module-path` and `--module`.
- The provider must be observable and resolved into the module graph for ServiceLoader to locate it.
- `ServiceLoader.load(Service.class)` fits the current loader environment; `ServiceLoader.load(layer, Service.class)` is used when providers reside in a specific module layer.
- Named modules register providers in the descriptor; classpath providers use `META-INF/services`.
- `--list-modules`, `--describe-module`, and `--show-module-resolution` help verify observability, descriptors, and the resolved graph.

Keep the consumer depending on the service contract, so providers can be swapped or added without tightly coupling the application to a concrete implementation.