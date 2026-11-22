# Complete Profile: Descriptor, Graph, Service, Layer, Image, and Verification

## 1. Objectives and Scope

A complete modular application requires several parts working together:

- **Module descriptor:** declares dependencies, API packages, and service contracts.
- **Module graph:** determines which modules are resolved and the relationships among them.
- **Service:** decouples consumers from provider implementations using `uses`/`provides`.
- **Module layer:** determines where modules are loaded; can use the boot layer or create child layers for plugins.
- **Runtime image:** packages the JDK runtime together with needed application modules using `jlink`.
- **Verification:** verifies descriptors, dependencies, service discovery, module resolution, and the image after building.

This lesson builds an end-to-end example using three modules: SPI, application, and provider. It then extends to two deployment styles: provider in the boot layer and provider loaded into a separate child layer. Finally, it builds a static runtime image or an image with external plugins.

## 2. Project Structure

The example uses a `GreetingService` service. The consumer needs to produce a greeting; the provider supplies how it is performed.

Source structure:

```text
project/
├── src/
│   ├── com.acme.spi/
│   │   ├── module-info.java
│   │   └── com/acme/spi/GreetingService.java
│   ├── com.acme.app/
│   │   ├── module-info.java
│   │   └── com/acme/app/Main.java
│   └── com.acme.provider.en/
│       ├── module-info.java
│       └── com/acme/provider/en/EnglishGreeting.java
├── out/
├── mods/
├── plugins/
└── image/
```

The three modules have separate responsibilities:

- `com.acme.spi` owns the service interface.
- `com.acme.app` is the consumer, depending only on the SPI.
- `com.acme.provider.en` implements the service and registers the implementation.

## 3. Module descriptors and service contract

### SPI module

File `src/com.acme.spi/module-info.java`:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

File `src/com.acme.spi/com/acme/spi/GreetingService.java`:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

The package is exported because consumer and provider need to reference the interface. The SPI does not need to know which module holds the implementation.

### Provider module

File `src/com.acme.provider.en/module-info.java`:

```java
module com.acme.provider.en {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.en.EnglishGreeting;
}
```

File `src/com.acme.provider.en/com/acme/provider/en/EnglishGreeting.java`:

```java
package com.acme.provider.en;

import com.acme.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

The provider needs to read the SPI to implement the interface. For a provider class declared directly with `provides ... with ...`, the implementation class must be public and have a public no-argument constructor. The implementation package does not need to be exported if consumers do not call the provider class directly.

### Consumer module

File `src/com.acme.app/module-info.java`:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

The consumer declares `requires` to read the service interface and `uses` to announce its need to discover providers. It does not declare `requires com.acme.provider.en`, thus avoiding direct dependency on the implementation.

File `src/com.acme.app/com/acme/app/Main.java`:

```java
package com.acme.app;

import com.acme.spi.GreetingService;
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
            throw new IllegalStateException(
                    "No GreetingService provider was found");
        }
    }
}
```

Output when the English provider is present:

```text
Hello, Java!
```

## 4. Reading the module graph before building

Relationships among modules:

```text
                    requires
com.acme.app ----------------------> com.acme.spi
     |                                     ^
     | uses GreetingService                | requires
     |                                     |
     + - - service binding - - > com.acme.provider.en
                                           |
                                           +-- provides GreetingService
```

Two kinds of relationships must be distinguished:

- `requires` creates a dependency and readability between modules.
- `uses`/`provides` describes a service relationship. Service binding can bring a provider into the graph without creating a direct dependency from consumer to provider.

A module graph is not a call graph. Resolving a module does not mean every class in the module is immediately loaded or every service method is invoked.

## 5. Compiling and packaging the modules

Standing in the `project` directory. Create output directories:

```bash
mkdir -p out mods
```

Compile all three modules at once:

```bash
javac --module-source-path src -d out -m com.acme.spi,com.acme.provider.en,com.acme.app
```

After compiling, the `out` directory contains the compiled modules. Package into modular JARs:

```bash
jar --create --file mods/com.acme.spi.jar -C out/com.acme.spi .
jar --create --file mods/com.acme.provider.en.jar -C out/com.acme.provider.en .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Each JAR must retain `module-info.class`. You can verify:

```bash
jar --describe-module --file mods/com.acme.spi.jar
jar --describe-module --file mods/com.acme.provider.en.jar
jar --describe-module --file mods/com.acme.app.jar
```

Confirm the descriptors show correctly:

- SPI exports package `com.acme.spi`.
- Provider requires SPI and provides `GreetingService`.
- App requires SPI and uses `GreetingService`.

On Windows, the same `javac` and `jar` commands can be run in PowerShell; the separator for multiple entries on the module path is a semicolon instead of a colon.

## 6. Running with the provider in the boot layer

When all three JARs are on the module path:

```bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
```

The Java launcher resolves root module `com.acme.app`, `requires` dependencies, and matching observable service providers. `--show-module-resolution` output usually contains lines showing root, requires, and binds; exact content depends on the JDK and module graph.

You can pass arguments:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main Ada
```

Result:

```text
Hello, Ada!
```

In this deployment, the application, SPI, and provider belong to the boot layer. `ServiceLoader.load(GreetingService.class)` discovers providers according to the caller's layer.

If you do not want a provider bound, check service declarations and the set of observable modules. Do not rely merely on the JAR existing on disk; the provider must be visible to the resolver and placed in the appropriate layer.

## 7. Creating a custom ModuleLayer for plugins

For a plugin system, the application and SPI can remain in the boot layer while the provider resides in a separate directory:

```text
mods/
├── com.acme.spi.jar
└── com.acme.app.jar

plugins/
└── com.acme.provider.en.jar
```

The consumer module still declares `uses` as above. The provider JAR is compiled with the SPI available on the module path, yet packaged separately in `plugins`.

Build the foundational modules:

```bash
mkdir -p out mods plugins
javac --module-source-path src -d out -m com.acme.spi,com.acme.app
jar --create --file mods/com.acme.spi.jar -C out/com.acme.spi .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Compile the provider separately, referencing SPI from `mods`:

```bash
javac --module-path mods --module-source-path src -d plugins -m com.acme.provider.en
jar --create --file plugins/com.acme.provider.en.jar -C plugins/com.acme.provider.en .
```

In the application, you can create a child layer:

```java
import com.acme.spi.GreetingService;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));

Configuration pluginConfiguration =
        ModuleLayer.boot().configuration().resolveAndBind(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.acme.provider.en")
        );

ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                pluginConfiguration,
                ClassLoader.getSystemClassLoader()
        );

ServiceLoader<GreetingService> plugins =
        ServiceLoader.load(pluginLayer, GreetingService.class);

for (GreetingService service : plugins) {
    System.out.println(service.greet("Ada"));
}
```

Here:

- The SPI module is already in the boot layer because the application requires the SPI.
- The provider is found in the `plugins` directory.
- `resolveAndBind` resolves the provider along with related dependencies and service bindings.
- `defineModulesWithOneLoader` creates a child layer using the specified parent class loader.
- `ServiceLoader.load(pluginLayer, GreetingService.class)` discovers service providers in that layer.

In a real application, handle cases where the provider does not exist, the module name is wrong, dependencies are missing, or the provider fails to initialize. Only load plugins from verified and approved artifacts; a module layer is not a security sandbox.

If there are multiple plugins, layers can be created per group or per deployment lifecycle. Avoid recreating the same layer on every request unless there are isolation requirements around class identity or lifecycle.

## 8. Creating a runtime image with jlink

`jlink` creates a runtime image containing the necessary JDK modules and application modules. For providers statically packaged on the module path, use `--bind-services` to link matching providers for services the application uses.

Example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output image
```

The command above:

- Takes system modules from the JDK's `jmods` directory.
- Takes application modules from `mods`.
- Starts from root module `com.acme.app`.
- Binds matching service providers and their dependencies.
- Creates the runtime image at `image`.

Run using the image:

```bash
image/bin/java -m com.acme.app/com.acme.app.Main
```

Check the modules included in the image:

```bash
image/bin/java --list-modules
```

On Windows, the executable is `image/bin/java.exe`; multiple module path entries use a semicolon.

### Image for dynamically loaded plugins

If you want providers to sit outside the runtime image and be loaded via a custom layer:

1. Link the image from the foundational modules `com.acme.app` and `com.acme.spi`.
2. Omit the provider plugin from the `jlink` command's module path.
3. Package the provider separately in the `plugins` directory.
4. Run the application from the image; the application uses `ModuleFinder`, `resolveAndBind`, and `ModuleLayer` to create a child layer.

Example linking the foundational image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output image
```

Then keep `plugins/com.acme.provider.en.jar` outside the image and use the custom layer code from the previous section.

The two deployment styles serve different purposes:

| Approach | Where is the provider? | How is it discovered? |
|---|---|---|
| Static service binding | Linked into the runtime image | ServiceLoader in the boot layer |
| Dynamic plugin layer | Separate JAR outside the image | ModuleFinder + resolveAndBind + ServiceLoader in child layer |

`jlink` needs proper explicit modules to link; automatic modules cannot be used as normal input modules for a runtime image. Libraries that are still automatic modules must be modularized or handled differently in the architecture before linking.

## 9. Verifying descriptors and the module graph

### Inspecting descriptors

```bash
jar --describe-module --file mods/com.acme.app.jar
jar --describe-module --file mods/com.acme.spi.jar
jar --describe-module --file mods/com.acme.provider.en.jar
```

Cross-check module names and directives against the design. If using a plugin layer, inspect the provider JAR in the `plugins` directory.

### Checking static dependencies

```bash
jdeps --module-path mods --check com.acme.app
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

`jdeps` helps inspect bytecode dependencies and cross-check module descriptors. It does not automatically detect all reflection, class names in configuration, or dynamically loaded providers.

### Validating the module set

```bash
java --validate-modules --module-path mods --add-modules ALL-MODULE-PATH
```

This command validates observable modules on the module path. It is useful for detecting inconsistent module graphs, split packages, and broken dependencies. Use `ALL-MODULE-PATH` for validation; do not necessarily use it as a root in production commands.

### Observing resolution at runtime

```bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
```

Confirm:

- `com.acme.app` is the root.
- `com.acme.spi` is resolved via `requires`.
- The provider is bound when service binding finds the matching module.
- There are no unexpected modules or missing dependencies.

With custom layers, log module names in the created configuration and layer to confirm providers are loaded from the right directory.

## 10. Verifying service discovery

Minimum testing should confirm:

- At least one provider is found in the expected deployment.
- The provider returns correct results for representative inputs.
- No providers outside the allowlist are present.
- The consumer handles the no-provider case properly.
- Initialization errors or errors in provider methods are recorded per policy.
- Multiple providers do not cause results to depend unexpectedly on traversal order.

Example result check:

```text
Input: Ada
Expected: Hello, Ada!
Actual:   Hello, Ada!
Result:   PASS
```

With a plugin layer, also check that the SPI type is shared from the parent layer, the provider is loaded into the child layer, and `ServiceLoader.load(pluginLayer, GreetingService.class)` finds the right implementation.

Do not treat `ServiceLoader` returning a provider as proof that the provider is trustworthy. Artifact provenance, checksums/signatures, and allowlists must be verified independently.

## 11. Verifying the runtime image

After linking the image:

```bash
image/bin/java --list-modules
image/bin/java --show-module-resolution -m com.acme.app/com.acme.app.Main
```

Run functional tests from the image itself, not just from the full JDK. This helps detect missing system modules, unbound providers, or runtime configuration differing from the build environment.

If using static service binding, confirm the provider module is in the image. If using dynamic plugins, confirm the image has the SPI and app, while the plugin JAR is found in the directory outside the image.

Test on the target OS and architecture. Runtime images built by `jlink` are platform-dependent; build images matching the deployment operating system/architecture.

## 12. Common Errors

| Symptom | Causes to check |
|---|---|
| `module not found` | Wrong module path, wrong module name, or missing dependency |
| Package not visible | Consumer missing `requires` or module owning package missing `exports` |
| Service provider not found | Missing `uses`/`provides`, provider not resolved, or not in the searched layer |
| Provider fails to instantiate | Invalid constructor/provider declaration or initialization code throws an error |
| Custom layer cannot resolve provider | Finder points to wrong directory, provider missing dependencies, or SPI absent from parent configuration |
| jlink reports invalid module | Dependency is not a valid explicit module, missing module, or inconsistent descriptors |
| Image runs yet lacks service | Provider not linked via service binding or external plugin not loaded into child layer |
| App runs on full JDK yet fails on image | Runtime image missing system modules, providers, or needed resources |

## 13. Release Checklist

- [ ] Each module has a stable name and accurate descriptor.
- [ ] `requires` dependencies reflect actual relationships.
- [ ] Only API packages needing exposure are exported.
- [ ] Consumer declares `uses`; provider declares `provides`.
- [ ] No split packages or missing dependencies exist.
- [ ] Module graph is verified with `--show-module-resolution`.
- [ ] Static dependencies are checked with `jdeps`.
- [ ] Service discovery is tested in the right layer.
- [ ] Provider artifacts have verified provenance, version, and checksums.
- [ ] Runtime image is built with the right set of modules.
- [ ] Image is tested independently on the target platform.
- [ ] Logging, rollback, and provider update procedures are in place.

## Remember

- Descriptors define readability, API packages, and service contracts.
- The module graph is resolved from roots and dependencies; service binding can add providers without creating a direct dependency from consumer to provider.
- The boot layer suits providers deployed with the application; child layers are useful for plugins with independent lifecycles.
- `jlink --bind-services` brings matching providers into the runtime image; dynamic plugins can stay outside the image and be loaded via a custom layer.
- `jdeps`, `jar --describe-module`, `--validate-modules`, and `--show-module-resolution` inspect different aspects.
- Test services, images, and dynamic dependencies with the exact deployment artifacts.
- Module encapsulation and layers are not a sandbox; only load providers from trusted sources.