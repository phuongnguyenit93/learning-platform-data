# Checking for missing providers after packaging

## 1. Why can a provider disappear after packaging?

The Java Service Provider Interface (SPI) allows a module or application to use a service without depending directly on concrete implementations. With the Java Platform Module System (JPMS), the service consumer declares \`uses\`, while the module supplying the implementation declares \`provides ... with ...\` in \`module-info.java\`.

A program may run fine in an IDE yet fail to find providers after packaging because the runtime environment has changed: the module path became the classpath, \`module-info.class\` is no longer in the final JAR, \`META-INF/services\` resources were dropped when creating a fat JAR, the provider module was not included in the runtime image, or the provider class cannot be instantiated.

When investigating, separate three stages:

1. **Declaration and packaging:** does the final artifact have the necessary metadata or service configuration?
2. **Provider discovery:** does \`ServiceLoader\` see the provider in the module layer or class loader being used?
3. **Provider instantiation:** was the provider found, yet failed when loading the class, calling the constructor, or calling the provider method?

A "no provider found" symptom and a \`ServiceConfigurationError\` usually point to two different stages. Do not rush to change dependencies before identifying at which stage the provider was lost.

## 2. Determining whether the application runs on JPMS or the classpath

This is the first step because the two provider registration mechanisms differ.

- **Named modules on the module path:** \`provides\` metadata in \`module-info.class\` registers providers. The consumer must declare \`uses\`.
- **Applications on the classpath:** \`ServiceLoader\` looks for the configuration file \`META-INF/services/<fully-qualified-service-name>\`. The file contains the fully qualified name of each implementation, one name per line.
- **A modular JAR placed on the classpath:** the JVM treats that JAR as a regular JAR; \`module-info.class\` is not used to create a module. If classpath-based discovery is needed, the artifact must contain \`META-INF/services\`.

For example, an application launched with:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

is running on the module path. If switched to:

~~~bash
java -cp "app.jar:provider.jar:spi.jar" com.acme.app.Main
~~~

then the JARs are processed on the classpath. On Windows, the classpath separator is a semicolon (\`;\`) instead of a colon (\`:\`).

Do not infer the execution mode merely from files having a \`.jar\` extension. Inspect the exact launch command or container/service configuration running in the deployment environment.

## 3. Registering providers properly in module-info.java

Suppose an application has three modules:

- \`com.acme.spi\` contains the service interface.
- \`com.acme.json\` provides the implementation.
- \`com.acme.app\` uses the service.

### 3.1. Service module

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Service interface:

~~~java
package com.acme.spi;

public interface Formatter {
    String format(String value);
}
~~~

The package containing the service must be exported so consumer and provider modules can reference the \`Formatter\` type.

### 3.2. Provider module

~~~java
module com.acme.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
            with com.acme.json.JsonFormatter;
}
~~~

Implementation:

~~~java
package com.acme.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String value) {
        return "\"" + value + "\"";
    }
}
~~~

The provider module must be able to read the module containing the service, so it declares \`requires com.acme.spi\`. The \`provides\` directive must use the exact service name and fully qualified provider class name.

For a regular provider class, the class must be public and have a public no-argument constructor. JPMS also supports provider methods: a public provider class can declare a \`public static\` method named \`provider\` with no parameters and returning a type compatible with the service. When using a provider method, the class declaring the method does not have to implement the service interface directly.

The implementation package does not need to be exported merely for \`ServiceLoader\` to use a provider declared with \`provides\`. Export that package only if the application needs to access the implementation's public API directly.

### 3.3. Consumer module

~~~java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
~~~

The consumer must declare \`uses\` for the service it loads via \`ServiceLoader\`. Without this directive, calling \`ServiceLoader\` from a named module can fail with \`ServiceConfigurationError\`, even if the provider JAR is present.

Code using the service:

~~~java
package com.acme.app;

import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loader =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loader) {
            System.out.println(formatter.getClass().getName());
            System.out.println(formatter.format("hello"));
        }
    }
}
~~~

If the loop does not execute at all, the loader found no matching provider in the discovery scope being used. If the loop throws \`ServiceConfigurationError\`, read the root cause: missing class, incompatible type, invalid constructor/provider method, or initialization error.

## 4. Inspecting artifacts after building

Inspect the actual deployed JAR, not just the IDE output directory or build directory before the final packaging step.

### 4.1. Inspecting the descriptor of a modular JAR

Use the command:

~~~bash
jar --describe-module --file mods/com.acme.json.jar
~~~

The provider's descriptor must show the module name and the \`provides\` directive, for example:

~~~text
com.acme.json
requires com.acme.spi
provides com.acme.spi.Formatter with com.acme.json.JsonFormatter
~~~

Inspect the consumer:

~~~bash
jar --describe-module --file mods/com.acme.app.jar
~~~

The output should contain \`uses com.acme.spi.Formatter\` and the dependency on the module containing the service.

If \`jar --describe-module\` reports no module descriptor and derives an automatic module, the final artifact no longer has the expected explicit descriptor. Check the packaging configuration to make sure \`module-info.class\` is preserved and the JAR is being placed on the module path.

### 4.2. Checking classes and files in the JAR

List the contents of the provider JAR:

~~~bash
jar --list --file mods/com.acme.json.jar
~~~

Verify that it contains:

- \`module-info.class\` at the root of the JAR for a modular JAR.
- The provider class file, such as \`com/acme/json/JsonFormatter.class\`.
- Required dependency classes needed to instantiate the provider.

For classpath applications, check the service configuration file:

~~~bash
jar --list --file provider.jar
~~~

The artifact must contain a resource at the exact path:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

File contents:

~~~text
com.acme.json.JsonFormatter
~~~

The service name in the path and the implementation name in the contents must be fully qualified and case-sensitive. If there are multiple providers, each provider is written on its own line.

### 4.3. Checking fat JARs and shaded JARs

A common mistake is multiple dependencies containing \`META-INF/services\` resources, where the fat JAR creation step keeps only one dependency's resource or overwrites the earlier file. In that case, the provider may work in the IDE but vanish in the merged JAR.

The packaging configuration must **merge** service configuration files with the same path, keeping all valid providers and removing duplicate lines if supported by the tool. For example:

- Gradle Shadow Plugin has the \`mergeServiceFiles()\` action.
- Maven Shade Plugin has the \`ServicesResourceTransformer\` transformer.

After changing the configuration, re-check the resources in the final artifact with \`jar --list\` and read the contents of the packaged service configuration file. Merely seeing a provider dependency in the dependency tree does not prove the provider registration resource is inside the JAR.

## 5. Checking whether the module is resolved at startup

When running a modular application, the provider module must be found on the module path and placed into the module layer being used.

Run with the option that displays the resolution process:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Read the output to verify:

- The consumer module is resolved.
- The module containing the service is resolved.
- The provider module appears in the service binding output.
- There are no missing module, duplicate module name, or unresolvable dependency errors.

JPMS has a service binding mechanism: during resolution, observable provider modules on the module path can be added when an already resolved module declares \`uses\` for the corresponding service. Therefore, the consumer having \`uses\` and the provider having \`provides\` are two halves of the same configuration.

To diagnose, you can instruct the launcher to add all modules on the module path to the root set:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --module com.acme.app/com.acme.app.Main
~~~

If the provider only appears when using \`--add-modules ALL-MODULE-PATH\`, re-check service binding and the consumer/provider descriptors. This is a way to isolate the cause; you do not necessarily have to keep this option in production commands.

You can validate modules on the module path with:

~~~bash
java --validate-modules --module-path mods
~~~

This command helps detect certain module structure and dependency issues before running the application.

## 6. Cases using jlink or custom ModuleLayers

### 6.1. Runtime image created with jlink

If the application is packaged as a runtime image, the provider module must exist in the final image. Just having the JAR on the build machine does not mean that module was included in the image.

When you need to link service providers and their dependencies into the image, use the \`--bind-services\` option:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --output runtime-image
~~~

After creating the image, check the module list:

~~~bash
runtime-image/bin/java --list-modules
~~~

On Windows, use \`runtime-image\\bin\\java.exe --list-modules\` and adjust the module path separator for the operating system. Verify that the provider module is in the image. If not using \`--bind-services\`, explicitly include the provider module in the set of linked modules when the application architecture requires it.

### 6.2. Provider loaded in a separate ModuleLayer

Plugins can be loaded into a \`ModuleLayer\` created by the application. In that case, searching for providers in the boot layer is not the same as searching for providers in the plugin layer.

Use the overload that accepts a layer:

~~~java
ModuleLayer pluginLayer = /* layer created for plugins */;
ServiceLoader<Formatter> loader =
        ServiceLoader.load(pluginLayer, Formatter.class);

for (Formatter formatter : loader) {
    System.out.println(formatter.format("hello"));
}
~~~

Ensure the module containing the service API is properly shared between the application and the plugin layer. If each layer or class loader loads a different copy of the service interface, two types with the same fully qualified name can still be two distinct Java types, making the provider incompatible with the service \`Class\` passed by the consumer.

## 7. Program to inspect descriptors and providers at runtime

You can write a small utility to list provider directives read by \`ModuleFinder\` from the module path:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectServiceDeclarations {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        for (ModuleReference reference : finder.findAll()) {
            ModuleDescriptor descriptor = reference.descriptor();

            descriptor.provides().forEach(provides -> {
                System.out.printf(
                        "%s provides %s with %s%n",
                        descriptor.name(),
                        provides.service(),
                        provides.providers());
            });

            descriptor.uses().forEach(service -> {
                System.out.printf(
                        "%s uses %s%n",
                        descriptor.name(),
                        service);
            });
        }
    }
}
~~~

This utility reads metadata of modules found on the module path without instantiating providers. It answers "does the JAR declare a provider?", but does not prove the provider can be instantiated in the actual runtime.

To test discovery and instantiation, run the \`ServiceLoader\` code inside the application itself with the same module path, module layer, and class loader as the production environment. If you need to log errors clearly:

~~~java
try {
    for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
        System.out.println("Loaded: " + formatter.getClass().getName());
    }
} catch (java.util.ServiceConfigurationError error) {
    error.printStackTrace();
}
~~~

Do not swallow \`ServiceConfigurationError\` and return an empty list; the error details usually pinpoint which provider class or configuration is broken.

## 8. Common causes and solutions

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| No provider on the module path | Consumer is missing \`uses\` or provider is missing \`provides\` | Use \`jar --describe-module\` to inspect both descriptors. |
| Provider JAR does not appear during resolution | JAR is not on the module path or provider module is not resolved | Check the launch command, \`--show-module-resolution\`, and try \`--add-modules ALL-MODULE-PATH\` to isolate. |
| Works in IDE but fat JAR cannot see provider | \`META-INF/services\` resource was overwritten or dropped during merge | Inspect resources in the final JAR; configure service file merging in the packaging plugin. |
| Works with \`-m\` but loses provider with \`-cp\` | \`module-info.class\` does not apply on the classpath | Add \`META-INF/services\` for classpath execution or keep running on the module path. |
| \`ServiceConfigurationError\`: provider class not found | Provider class is missing from the artifact or class name is wrong | Check \`jar --list\`, package name, and packaged classes. |
| \`ServiceConfigurationError\`: provider not a subtype | Provider implements a different copy of the service API or declares the wrong type | Share a single API module/JAR; remove duplicate SPI copies from the fat JAR and classpath. |
| Provider found but instantiation fails | Missing public no-arg constructor, invalid provider method signature, or missing runtime dependency | Check constructor/provider method and read the root cause in the stack trace. |
| Provider works in boot layer but missing in plugin | Looking up provider in the wrong ModuleLayer | Call \`ServiceLoader.load(pluginLayer, Service.class)\` with the layer containing the provider. |
| Provider exists on build machine but missing in runtime image | `jlink` did not link the provider module | Check \`java --list-modules\` in the image; consider \`jlink --bind-services\`. |

In addition to the causes above, check whether the service name matches identically between consumer and provider. Module name, package name, service name, and provider name are distinct values; do not use the JAR file name in place of a module name or class name.

## 9. Short investigation workflow

When an issue only appears after packaging, go through these steps in order:

1. Record the exact launch command and determine whether the module path or classpath is used.
2. Run \`jar --describe-module\` on the provider JAR and consumer JAR if using JPMS.
3. Run \`jar --list\` on the final artifact to confirm the provider class, \`module-info.class\`, or \`META-INF/services\` is actually present.
4. Use \`--show-module-resolution\` to see whether the provider module is resolved.
5. Run \`ServiceLoader\` in the actual production runtime and record any full \`ServiceConfigurationError\` if one occurs.
6. If the application uses `jlink` or plugin layers, verify the provider module is in the runtime image/layer and use the right \`ServiceLoader\` overload.

The result of each step helps pinpoint the exact failure: missing declaration, unpackaged resource/class, unresolved module, loader searching the wrong scope, or provider failing instantiation. Fix the exact failing layer and then re-verify the final artifact with the exact deployment command.
