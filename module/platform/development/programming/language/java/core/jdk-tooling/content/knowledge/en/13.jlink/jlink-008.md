# Include service binding with jlink

The **`--bind-services`** option of the `jlink` tool instructs the runtime image linking process to find and include service provider modules for the services used by the selected modules, along with the providers' required dependencies.

This option is especially useful for applications that use **`ServiceLoader`**. An application can declare only the service interface and the `uses` directive; the module implementing the service is discovered through the `provides` directive. When creating a runtime image, `jlink --bind-services` links the matching providers without requiring each provider to be listed in `--add-modules`.

## 1. What is service binding in the Java Module System?

The Java Platform Module System (JPMS) allows a module to use a service through an interface without directly depending on the implementation module.

There are three components:

- **Service:** an interface or abstract class describing the functionality the application needs.
- **Service consumer:** a module that uses the service. In `module-info.java`, the module declares the `uses` directive.
- **Service provider:** a module that implements the service. In `module-info.java`, the module declares the `provides ... with ...` directive.

This organization decouples the API definition from the implementation. An application can use multiple different providers without having to recompile to reference each implementation class directly.

Example of the relationship:

```text
Application module
       |
       | uses GreetingService
       v
GreetingService interface
       ^
       | implements
       |
Provider module
       |
       | provides GreetingService with ...
       v
Concrete provider class
```

When linking a runtime image, service binding helps locate matching providers on the module path and includes them along with their required dependencies in the image.

## 2. Distinguishing uses, provides, and --bind-services

These three concepts serve different roles:

| Component | Where declared | Role |
| --- | --- | --- |
| `uses` | Consumer's `module-info.java` | Declares that the module needs to use a service |
| `provides ... with ...` | Provider's `module-info.java` | Registers the service implementation class |
| `--bind-services` | `jlink` command | Finds and links provider modules along with their dependencies into the runtime image |

Example consumer declaration:

```java
module com.example.app {
    requires com.example.greeting.api;
    uses com.example.greeting.GreetingService;
}
```

Example provider declaration:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.GreetingService
        with com.example.greeting.provider.EnglishGreetingService;
}
```

The `uses` and `provides` directives describe service relationships in the module descriptor. The `--bind-services` option of `jlink` uses those declarations when building the image.

**Note:** `--bind-services` does not automatically write `uses` or `provides` directives into modules. Modules must declare services properly in `module-info.java`.

## 3. Syntax of jlink --bind-services

Basic syntax:

```bash
jlink --module-path <module-path> --add-modules <root-modules> --bind-services --output <directory>
```

Components:

- `--module-path`: where to locate input modules, such as the JDK's `jmods` directory and the compiled modules directory.
- `--add-modules`: the root modules to include in the runtime image.
- `--bind-services`: finds and links service provider modules along with their required dependencies.
- `--output`: the directory for the generated runtime image.

Example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
```

On Windows PowerShell, the separator between module path entries is a semicolon:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --bind-services --output image
```

On macOS/Linux, the separator is a colon:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
```

The `$JAVA_HOME/jmods` directory provides the JDK platform modules; `mods` contains the compiled application modules. Use the same compatible JDK for both `javac` and `jlink`.

## 4. Complete example: ServiceLoader and three modules

The following example creates three modules:

1. `com.example.greeting.api`: defines the service interface.
2. `com.example.greeting.app`: consumes the service via `ServiceLoader`.
3. `com.example.greeting.provider`: provides an implementation.

The goal is to link a runtime image with only the application module as the root. `jlink --bind-services` will find the matching provider on the module path and include the provider in the image.

Directory structure:

```text
project/
  src/
    com.example.greeting.api/
      module-info.java
      com/example/greeting/GreetingService.java
    com.example.greeting.app/
      module-info.java
      com/example/greeting/app/Main.java
    com.example.greeting.provider/
      module-info.java
      com/example/greeting/provider/EnglishGreetingService.java
```

### Step 1: Create the service API module

File **`src/com.example.greeting.api/module-info.java`**:

```java
module com.example.greeting.api {
    exports com.example.greeting;
}
```

File **`src/com.example.greeting.api/com/example/greeting/GreetingService.java`**:

```java
package com.example.greeting;

public interface GreetingService {
    String greet();
}
```

The package is exported so that consumer and provider modules can reference the public interface.

### Step 2: Create the provider module

File **`src/com.example.greeting.provider/module-info.java`**:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.GreetingService
        with com.example.greeting.provider.EnglishGreetingService;
}
```

File **`src/com.example.greeting.provider/com/example/greeting/provider/EnglishGreetingService.java`**:

```java
package com.example.greeting.provider;

import com.example.greeting.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet() {
        return "Hello from a linked service provider";
    }
}
```

The provider class implements the interface and has a public no-argument constructor. The implementation package does not need to be exported solely to register the provider with the `provides` directive.

### Step 3: Create the application module that uses the service

File **`src/com.example.greeting.app/module-info.java`**:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.GreetingService;
}
```

The `requires` directive allows the application to read the API module. The `uses` directive declares that the application needs the `GreetingService` service.

File **`src/com.example.greeting.app/com/example/greeting/app/Main.java`**:

```java
package com.example.greeting.app;

import com.example.greeting.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        GreetingService service = ServiceLoader
            .load(GreetingService.class)
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No GreetingService provider found")
            );

        System.out.println(service.greet());
    }
}
```

The application depends only on the `GreetingService` interface; it does not directly import or instantiate `EnglishGreetingService`. `ServiceLoader` locates the implementation registered by the provider module.

### Step 4: Compile the three modules

Run from the `project` root directory.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.greeting.api,com.example.greeting.app,com.example.greeting.provider
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.greeting.api,com.example.greeting.app,com.example.greeting.provider
```

After compiling, the output structure looks like:

```text
mods/
  com.example.greeting.api/
    module-info.class
    com/example/greeting/GreetingService.class
  com.example.greeting.app/
    module-info.class
    com/example/greeting/app/Main.class
  com.example.greeting.provider/
    module-info.class
    com/example/greeting/provider/EnglishGreetingService.class
```

Each directory in `mods` is an exploded module containing `module-info.class` and the corresponding class files.

### Step 5: Create the runtime image with service binding

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeting.app --bind-services --output image
```

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app --bind-services --output image
```

Command breakdown:

- The only specified root module is `com.example.greeting.app`.
- The application module requires `com.example.greeting.api`, so the API module is resolved as a dependency.
- The application declares `uses GreetingService`.
- The provider module declares `provides GreetingService with EnglishGreetingService`.
- `--bind-services` finds the matching provider on the module path and includes the provider and its required dependencies in the runtime image.

There is no need to add `com.example.greeting.provider` to `--add-modules` in this example because the goal is to demonstrate service binding discovering the provider automatically. The provider must be present and observable on the input module path.

### Step 6: Run the application from the runtime image

**Windows PowerShell:**

```powershell
.\image\bin\java.exe -m com.example.greeting.app/com.example.greeting.app.Main
```

**macOS/Linux:**

```bash
./image/bin/java -m com.example.greeting.app/com.example.greeting.app.Main
```

Expected output:

```text
Hello from a linked service provider
```

The output confirms that the provider module was linked into the runtime image and `ServiceLoader` found the implementation at runtime.

## 5. What happens if --bind-services is not used?

If you only run:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app --output image-no-bind
```

and the provider is not a direct dependency or another root module, the provider may not be included in the image. When running the application, `ServiceLoader` will not find any provider and the example above will throw:

```text
java.lang.IllegalStateException: No GreetingService provider found
```

This is a common situation when an application uses a service interface and expects providers to be discovered automatically, yet the image only contains modules resolved through regular dependencies.

There are two ways to resolve this:

- Use `--bind-services` to link providers for the services used by the selected modules.
- Explicitly list the provider module in `--add-modules` if you want to decide which provider modules are included.

Example of explicitly linking the provider:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app,com.example.greeting.provider --output image-explicit
```

This command adds the provider as a root module. Therefore, service binding is no longer needed to include this specific provider in the image.

On Windows, replace the colon in the module path with a semicolon:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeting.app,com.example.greeting.provider --output image-explicit
```

## 6. How are providers discovered?

In the module system, a service provider is declared in the module descriptor. For example:

```java
provides com.example.greeting.GreetingService
    with com.example.greeting.provider.EnglishGreetingService;
```

When resolving modules for the runtime image:

1. `jlink` starts from the root modules in `--add-modules`.
2. Dependencies requested via `requires` are resolved.
3. When `--bind-services` is present, service binding searches for provider modules for the services declared as used by the resolved modules.
4. The provider module and its dependencies are added to the set of linked modules.
5. The process can continue for any services used by the provider module itself.

As a result, a provider can pull in additional modules. The final image includes not only the provider class, but also the modules required for that provider to function.

`--bind-services` only discovers providers that are observable on the module path and validly declared. It does not arbitrarily load every JAR in a directory, nor does it automatically turn classpath libraries into named modules.

## 7. How do --bind-services and --add-modules differ?

| Criterion | `--add-modules` | `--bind-services` |
| --- | --- | --- |
| Role | Selects root modules to include in the image | Finds and adds provider modules for used services |
| Input | List of module names | `uses` and `provides` relationships in module descriptors |
| Selection method | Explicitly specified by the builder | Module system resolves matching providers |
| Dependencies | Dependencies of root modules are resolved | Dependencies of providers are also linked |
| When appropriate | The application knows the exact modules needed | The application uses services and wants providers linked automatically |

The two options can be used together:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app,com.example.metrics --bind-services --output image
```

In this example, `com.example.greeting.app` and `com.example.metrics` are explicitly selected root modules. Service binding continues by finding providers for the services used by the resolved modules.

## 8. Finding providers with --suggest-providers

`jlink` provides the `--suggest-providers` option to suggest modules that provide one or more service types found on the module path.

Example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --suggest-providers com.example.greeting.GreetingService
```

On Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --suggest-providers com.example.greeting.GreetingService
```

This option is useful when:

- You do not know which module provides a service.
- You want to verify whether the module path contains the expected provider.
- You are investigating why service binding did not include a provider in the image.
- You want to identify providers before deciding between automatic binding or explicit module addition.

The results depend on the modules present on the module path and their `provides` declarations.

## 9. Impact of service binding on runtime image size

`--bind-services` can make the runtime image larger because it adds provider modules and their dependencies.

The size increase depends on:

- The number of services used by the selected modules.
- The number of providers found for each service.
- The dependencies required by those providers.
- Which platform or application modules are already present in the image.

If a service has multiple observable providers, binding may link multiple matching providers. Do not assume only the first provider is included in the image just because `ServiceLoader.findFirst()` picks one provider at runtime; that operation is not `jlink`'s module selection rule.

To keep the image as small as possible, consider:

- Including only the root modules that are truly needed.
- Limiting the module path to managed input modules.
- Checking which providers are actually necessary.
- Comparing images built with and without `--bind-services`.
- If only one specific provider is needed, considering adding that module explicitly and structuring the module path accordingly.

Do not omit `--bind-services` solely to reduce size if the application needs the providers to work properly.

## 10. Requirements for service binding to work

Verify the following conditions:

- The consumer module declares `uses service.Interface`.
- The provider module declares `provides service.Interface with ProviderClass`.
- The provider class properly implements the service type.
- The provider module can read the service API module via `requires`.
- The provider module is present and observable on the module path used by `jlink`.
- The module path contains the application, API, and required provider modules.
- A JDK that supports JPMS and a compatible `jlink` tool are used.
- The application actually invokes `ServiceLoader` or the corresponding service mechanism.

For a regular provider class declared in `provides`, the provider must satisfy `ServiceLoader` requirements, such as being a public class with a public no-argument constructor. Java also supports a provider method form according to service provider module rules; when using that form, follow the requirements in the corresponding JDK `ServiceLoader` documentation.

## 11. Common errors

| Symptom | Common cause | Solution |
| --- | --- | --- |
| `ServiceLoader` cannot find a provider in the image | The provider module was not linked | Check `uses`, `provides`, and the module path, and use `--bind-services` or add the provider to `--add-modules` |
| `ServiceConfigurationError` stating the module does not declare `uses` | The consumer is missing the `uses` directive | Add `uses` to the consumer's module descriptor and recompile |
| The provider module is not recognized | The provider is missing from the module path or the descriptor lacks a valid `provides` | Inspect with `jmod describe`, `jar --describe-module`, or check the compiled module structure |
| The provider fails to instantiate | The provider class or constructor does not meet `ServiceLoader` requirements | Check the implementation class and constructor/provider method |
| `jlink` reports module not found | The module path is missing the `mods` directory or JDK `jmods` | Verify the paths and the OS-specific separator |
| The image is larger than expected | Binding added multiple providers and dependencies | Use `--suggest-providers`, inspect the module path, and compare module lists |
| Works when run directly, but the image is missing the provider | The provider was on the module path at runtime, not linked into the image | Use `--bind-services` or add the provider module explicitly |
| Provider is on the classpath, but `jlink` cannot find it | `jlink` links modules and does not package arbitrary classpath entries | Package the provider as a proper module and place it on the module path |

## 12. Checklist when using --bind-services

When creating a runtime image for an application using `ServiceLoader`:

1. Identify the service interface and the module that owns the interface.
2. Verify that the consumer declares `uses`.
3. Verify that the provider declares `provides ... with ...`.
4. Compile all modules and confirm the output module structure.
5. Place the application, API, provider modules, and JDK `jmods` on the module path.
6. Run `jlink --suggest-providers` if you need to confirm the provider can be found.
7. Use `jlink --add-modules <root> --bind-services` to build the image.
8. Inspect the module list in the image with `image/bin/java --list-modules`.
9. Run the application using the Java executable inside the image.
10. Check logs and `ServiceLoader` output in the target environment.

When comparing results, build another image without `--bind-services` or one with explicitly specified providers. Use separate output directories for each image to avoid overwriting or mixing up results.

## 13. Key takeaways

- `uses` declares a service required by a consumer module.
- `provides ... with ...` registers an implementation in a provider module.
- `jlink --bind-services` links matching provider modules and their dependencies into the runtime image.
- Providers must be present and observable on the input module path.
- `--bind-services` does not replace `--add-modules`; root modules must still be specified.
- If you do not use service binding, you can add provider modules explicitly with `--add-modules`.
- `--suggest-providers` helps locate modules that provide a service.
- Service binding can increase image size because it adds providers and their dependencies.
- `jlink` links modules; it does not package arbitrary classpath-only dependencies.

Understanding `--bind-services` allows you to build compact runtime images while retaining all providers your application needs, with clear control over the relationship between the service API, consumer, and implementation in the Java Module System.