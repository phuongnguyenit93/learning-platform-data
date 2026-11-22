# How root service consumers affect the graph in JPMS

In the Java Platform Module System (JPMS), a module can use a service without declaring direct dependencies on each implementation. The consuming module declares `uses`, and the supplying module declares `provides ... with ...`. The **service binding** mechanism uses those declarations to expand the set of resolved modules: when a module in the graph needs a service, matching provider modules can be brought into the configuration along with their dependencies.

The starting point of this process is the **root modules**. Therefore, if a root module is a service consumer, the services it declares can make the graph larger. Understanding the relationship between roots, `requires`, `uses`, `provides`, and the `--bind-services` option is essential to accurately predict which modules will be present in the runtime image.

## 1. Four concepts to distinguish

- **Root module**: a module chosen as a starting point during resolution. With `jlink`, roots are typically specified with `--add-modules`.
- **Service consumer**: a module that needs an abstraction/service and declares `uses fully.qualified.ServiceType` in `module-info.java`.
- **Service provider**: a module that implements a service and declares `provides fully.qualified.ServiceType with fully.qualified.ProviderClass`.
- **Service binding**: the resolution step that adds observable provider modules for services used by modules in the graph, and then resolves the dependencies of those providers.

For example, the `com.acme.app` application calls the `Codec` service. The application only depends on the `com.acme.codec.api` API; it does not need to know that the JSON implementation lives in the `com.acme.codec.json` module.

~~~text
Root: com.acme.app
    |
    +-- requires --> com.acme.codec.api
    |
    +-- uses Codec
             |
             +-- service binding locates provider
                         |
                         +--> com.acme.codec.json
                                  |
                                  +-- requires --> com.acme.codec.api
~~~

The `requires` relationship and the service binding relationship have different meanings. `requires` creates a readability dependency according to JPMS rules. `uses` records a service need so that the binding process locates providers; it does not mean the consumer must `requires` each provider module, nor does it cause implementation packages to be exported to the consumer.

## 2. Declaring the service consumer and provider

Suppose the project has three modules:

1. `com.acme.codec.api` containing the service interface.
2. `com.acme.codec.json` supplying the JSON implementation.
3. `com.acme.app` using the service.

### API module

Structure:

~~~text
modules/
└── com.acme.codec.api/
    ├── module-info.java
    └── com/acme/codec/spi/Codec.java
~~~

`module-info.java`:

~~~java
module com.acme.codec.api {
    exports com.acme.codec.spi;
}
~~~

Service interface:

~~~java
package com.acme.codec.spi;

public interface Codec {
    String name();
    byte[] encode(String value);
}
~~~

The API module exports the package containing the interface so consumers and providers can read and implement the service type.

### Provider module

`module-info.java` of the provider:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Implementation:

~~~java
package com.acme.codec.json;

import com.acme.codec.spi.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String name() {
        return "json";
    }

    @Override
    public byte[] encode(String value) {
        return ("\"" + value + "\"").getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

The provider module needs to read the API module to reference the interface. The implementation package does not need to be exported merely for `ServiceLoader` to locate the provider declared in the descriptor. In the standard implementation shown in this example, the provider class is public and has a public no-argument constructor.

### Consumer module

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.codec.api;

    uses com.acme.codec.spi.Codec;
}
~~~

Consumer code:

~~~java
package com.acme.app;

import com.acme.codec.spi.Codec;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader.load(Codec.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .forEach(codec -> System.out.println(codec.name()));
    }
}
~~~

The consumer only depends on the API module. It does not declare `requires com.acme.codec.json`. It is the `uses` and `provides` metadata that allows the service binding process to locate matching providers.

## 3. How do root modules change the graph?

The resolution process starts from a set of roots. From the roots, JPMS finds dependencies declared via `requires` and continues expanding the graph according to resolution rules. When performing service binding, the system inspects services declared by modules already in the graph, finds observable provider modules, adds them to the configuration, and resolves their dependencies.

With the example above, if `com.acme.app` is the root:

1. `com.acme.app` is placed into the graph.
2. The `com.acme.codec.api` dependency is resolved via `requires`.
3. The consumer declares `uses com.acme.codec.spi.Codec`.
4. Service binding locates observable modules declaring `provides com.acme.codec.spi.Codec`.
5. `com.acme.codec.json` is added to the graph.
6. The provider's dependencies, including `com.acme.codec.api`, are resolved.
7. If the provider module also declares `uses` for another service, the binding process can continue expanding the graph.

This creates a chain effect. A root service consumer can pull in providers, the providers' dependencies, and providers of subsequent services. The process repeats until no more matching providers need to be added.

Remember three cases:

- **Consumer is in the graph**: services declared by that module can trigger provider lookup.
- **Consumer is not in the graph**: that module's `uses` directives do not cause the current graph to pull in providers.
- **Provider is specified as a root or directly required**: the provider is resolved via root/`requires`, even without service binding.

Therefore, a provider can appear in the graph for several reasons: chosen as a root, being a dependency via `requires`, or added via service binding. When analyzing a graph, determine the path that caused a module to appear rather than only looking at the module name in the final output.

## 4. Service binding in jlink

`jlink` creates a runtime image from a set of resolved modules. The `--add-modules` option specifies the root modules. The `--bind-services` option instructs the tool to link service provider modules and their dependencies.

Example of creating a runtime image for an application:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output runtime-app
~~~

Where:

- `$JAVA_HOME/jmods` contains the JMODs of the JDK being used.
- `mods` contains the compiled application modules, such as modular JARs or exploded modules.
- `--add-modules com.acme.app` selects the consumer as the root.
- `--bind-services` allows providers of services used by the graph to be added along with the providers' dependencies.
- `--output runtime-app` is the output runtime image directory being created.

With the three example modules, the linked graph may include:

~~~text
com.acme.app
com.acme.codec.api
com.acme.codec.json
java.base
...
~~~

Other platform modules will depend on the actual dependencies of the application and providers.

### Comparison when omitting --bind-services

If you run:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-app
~~~

`jlink` still resolves the roots and `requires` dependencies. However, providers are not automatically included merely because the consumer has `uses`. If the provider is neither a root nor required via normal dependencies, the provider may be absent from the image.

When the application calls `ServiceLoader.load(Codec.class)`, without the provider in the runtime image `ServiceLoader` cannot find that implementation. Therefore, if an application relies on providers discovered via service binding, verify that the providers have been included in the image.

Another approach is to specify the provider as a root:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app,com.acme.codec.json --output runtime-app
~~~

In this case, the provider is included because it was explicitly selected, without needing service binding to add that provider itself. However, this approach forces the deployment configuration to know the implementation names. Service binding is better suited when you want to keep the consumer dependent on the API and let provider metadata decide which implementations can participate.

## 5. Which providers can be added?

Service binding can only select providers that the resolution tool can observe. A module declaring `provides` that lies outside the module finders or outside the observable module scope cannot be added to the graph.

Factors to check:

- **Module path**: the directory containing the provider's modular JAR or exploded module must be on `--module-path`.
- **Module descriptor**: the provider must declare the exact service type in `provides`.
- **Service type**: the consumer and provider must reference the exact same service type name, in the right package and API module.
- **Root set**: at least one module in the graph must declare `uses` for that service, unless the provider is brought in as a root or other dependency.
- **Module universe**: restrictions such as `--limit-modules` can exclude a provider module from the set of resolvable modules.
- **Provider dependencies**: modules needed by `requires` in the provider must also be resolvable.

If multiple modules provide the same service, service binding can add multiple matching providers to the graph. This mechanism does not choose a single implementation on behalf of the application. If business logic needs to prioritize a specific provider, design a provider selection policy in the application or explicitly configure the set of deployed modules; do not rely on incidental module ordering.

## 6. Observing the graph with JDK tools

First, you can ask `jlink` to suggest providers for a service type:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --suggest-providers com.acme.codec.spi.Codec
~~~

This command checks whether modules on the module path contain providers for the queried service. It is an exploratory step; suggesting providers does not mean they have already been included in a runtime image.

After creating the image, list the modules in the runtime:

~~~bash
runtime-app/bin/java --list-modules
~~~

On Windows:

~~~powershell
runtime-app/bin/java.exe --list-modules
~~~

Look for the provider module in the list to confirm the image contains it. You can run the application using the new runtime image:

~~~bash
runtime-app/bin/java -m com.acme.app
~~~

If you need to inspect module resolution when launching a module-path application in an existing runtime that has the corresponding modules, use:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app
~~~

The output helps observe the resolved roots and dependencies. To conclude whether a provider was added by service binding or by `requires`, you still need to cross-check the consumer/provider descriptors and how the runtime image was built.

## 7. Comparing resolve() and resolveAndBind() via the Java API

The Java API in `java.lang.module` lets you create a configuration from root modules. The main difference is that `resolveAndBind()` performs the additional service binding step.

Example:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Set;

public class CompareResolution {
    public static void main(String[] args) {
        ModuleFinder applicationModules =
            ModuleFinder.of(Path.of("mods"));

        Configuration parent =
            ModuleLayer.boot().configuration();

        Set<String> roots = Set.of("com.acme.app");

        Configuration withoutBinding = parent.resolve(
            ModuleFinder.of(),
            applicationModules,
            roots
        );

        Configuration withBinding = parent.resolveAndBind(
            ModuleFinder.of(),
            applicationModules,
            roots
        );

        print("resolve()", withoutBinding);
        print("resolveAndBind()", withBinding);
    }

    private static void print(
            String label,
            Configuration configuration) {
        System.out.println("\n" + label);

        configuration.modules().stream()
            .map(ResolvedModule::name)
            .sorted(Comparator.naturalOrder())
            .forEach(System.out::println);
    }
}
~~~

Run the program from a suitable classpath, with the `mods` directory containing the example modules. The output depends on the actual modules present in the module finder:

- `resolve()` resolves the roots and dependencies via `requires`.
- `resolveAndBind()` performs resolution along with service binding, so `com.acme.codec.json` and the provider's dependencies can also appear.

`configuration.modules()` returns the modules in the newly created configuration; modules belonging to the parent configuration are not listed as new modules of the child configuration. This is why the printed list may not contain all platform modules running in the boot layer.

Neither method modifies JAR files or descriptors. They produce a resolution result in memory so the application can construct or inspect a `ModuleLayer`.

## 8. Common mistakes

**The consumer has `uses` but the provider does not appear.** Check whether you used `jlink --bind-services`, whether the provider is on the module path, whether the descriptor declares the right service type, and whether the consumer module is actually in the graph.

**`--bind-services` was used, yet the provider is still not found.** `--bind-services` does not automatically search every directory on the machine for modules. Check the module path, module names, and the observable module scope. Also check whether the provider is packaged as a valid modular JAR or exploded module.

**A provider appears even though it is not directly used.** The provider could be a root, a dependency of another module, or added by another consumer in the graph. Inspect all roots, `requires`, `uses`, and `provides` directives before drawing conclusions.

**The runtime image is larger than expected.** Service binding can add multiple providers for the same service, dependencies of those providers, and providers of subsequent services. Check which modules declare `uses`, narrow the root set and module path, and then compare the module lists before and after enabling binding.

**The application finds multiple providers.** This is valid if multiple modules provide the service. Use properties or a provider selection policy at the application layer if only one implementation is allowed.

**Confusing `uses` with `requires`.** `uses` does not create a compile-time dependency on an implementation. The consumer needs to `requires` the module containing the service API; the provider needs to `requires` the API module and declare `provides`. Service binding is the mechanism that resolves providers into the configuration.

## 9. Practice

1. Create the three modules `com.acme.codec.api`, `com.acme.codec.json`, and `com.acme.app` following the example.
2. Package the modules as modular JARs or prepare exploded modules in the `mods` directory.
3. Run `jlink` with root `com.acme.app` and enable `--bind-services`. Use `java --list-modules` from the new runtime to verify the provider is in the image.
4. Build a second image but omit `--bind-services`. Compare the module list and the result of calling `ServiceLoader`.
5. Build a third image by adding the provider directly to `--add-modules`. Compare why the provider appears in the graph in this case.
6. Use `--suggest-providers` to inspect available providers on the module path.
7. Run the `CompareResolution` example to compare the module sets between `resolve()` and `resolveAndBind()`.

When analyzing a graph with service binding, start from the root modules, follow `requires` edges, and then examine the services declared by modules in the graph via `uses`. A provider can only be added if it lies within the observable module set. With `jlink`, `--bind-services` turns those service relationships into modules linked into the runtime image, so a root service consumer can significantly determine the size and composition of the generated runtime.
