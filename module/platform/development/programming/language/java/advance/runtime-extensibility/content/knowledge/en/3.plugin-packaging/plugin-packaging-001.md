# Separating the Contract JAR, Host Application JAR, and Implementation JAR

## Purpose and Role of Each JAR

A plugin system needs clear boundaries between the **extension contract**, the **host application**, and **replaceable implementations**. Instead of compiling the host application together with every plugin, package the three components separately:

| Component | What It Contains | Compile-Time Dependencies | Distributed To |
|---|---|---|---|
| **Contract/API JAR** | Interfaces and stable data types shared by both sides | Minimal, ideally no external dependencies | Both the host and plugin authors |
| **Host JAR** | Entry point, lifecycle, plugin discovery, and invocation | Contract JAR | Application operators/runners |
| **Plugin implementation JAR** | Interface implementation classes, provider descriptors, and private resources | Contract JAR | Plugin installers; can be released independently |

Compile-time dependency direction:

\`\`\`text
       host.jar ───────────┐
                           ▼
                      contract.jar
                           ▲
       plugin.jar ─────────┘

The host does not directly import implementation classes in the plugin.
The plugin does not depend on host.jar.
\`\`\`

This is the **compile-time dependency** boundary. At runtime, the host still needs access to the contract JAR and a way to discover plugin JARs. The example below uses Java SPI (\`ServiceLoader\`) on the classpath to illustrate this separation. More complex dynamic loading mechanisms, ClassLoader isolation, security, and API versioning are additional decisions; separating JAR files alone does not solve those problems.

## Complete Example on Java 17+

We will build a message-processing application using plugins. The contract defines the processing operation; the host selects providers via \`ServiceLoader\`; the plugin supplies an implementation. Project structure:

\`\`\`text
plugin-demo/
├── contract-src/
│   └── demo/api/MessagePlugin.java
├── host-src/
│   └── demo/host/Main.java
├── plugin-src/
│   ├── demo/plugin/UppercasePlugin.java
│   └── META-INF/services/demo.api.MessagePlugin
└── build/                              # generated when running commands
\`\`\`

### 1. Contract JAR: Defining the Shared API

File \`contract-src/demo/api/MessagePlugin.java\`:

\`\`\`java
package demo.api;

public interface MessagePlugin {
    String id();
    String transform(String input);
}
\`\`\`

\`id()\` is the identifier for the host to recognize the plugin; \`transform()\` is the behavior that providers must implement. The interface belongs to the \`demo.api\` package, not inside the host's or plugin's package. The signature uses JDK \`String\`, avoiding coupling the API to host-specific types.

Compile and package from the \`plugin-demo\` directory:

\`\`\`bash
mkdir -p build/contract-classes
javac -d build/contract-classes contract-src/demo/api/MessagePlugin.java
jar --create --file build/contract.jar -C build/contract-classes .
\`\`\`

\`contract.jar\` now contains \`demo/api/MessagePlugin.class\`. There must be exactly one copy of it within the shared class-loading scope of the host and plugins.

### 2. Plugin JAR: Implementing and Registering the Provider

File \`plugin-src/demo/plugin/UppercasePlugin.java\`:

\`\`\`java
package demo.plugin;

import demo.api.MessagePlugin;
import java.util.Locale;

public final class UppercasePlugin implements MessagePlugin {
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
\`\`\`

The text file \`plugin-src/META-INF/services/demo.api.MessagePlugin\` contains the exact provider class name:

\`\`\`text
demo.plugin.UppercasePlugin
\`\`\`

For standard providers on the classpath, the implementation class must be declared as a provider in the configuration file \`META-INF/services/<fully-qualified-interface-name>\`. Here the class is \`public\`, has an implicit public no-argument constructor, implements the interface, and is instantiated by the JVM when \`ServiceLoader\` iterates over providers. A missing or misspelled descriptor prevents the provider from being discovered; an invalid provider declaration can cause a \`ServiceConfigurationError\`.

Compile the plugin with only the **contract JAR** on the compile classpath, then package both the \`class\` files and the descriptor:

\`\`\`bash
mkdir -p build/plugin-classes
javac -cp build/contract.jar -d build/plugin-classes plugin-src/demo/plugin/UppercasePlugin.java
jar --create --file build/plugin.jar \
  -C build/plugin-classes . \
  -C plugin-src META-INF/services
\`\`\`

The \`jar\` command does not automatically copy the descriptor just because we compiled the class: this resource must be explicitly included in the JAR. The plugin JAR does not contain a duplicate copy of \`MessagePlugin.class\` from the contract.

### 3. Host JAR: Knowing Only the Interface

File \`host-src/demo/host/Main.java\`:

\`\`\`java
package demo.host;

import demo.api.MessagePlugin;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<MessagePlugin> plugins = ServiceLoader.load(MessagePlugin.class);
        boolean found = false;
        for (MessagePlugin plugin : plugins) {
            found = true;
            System.out.println(plugin.id() + ": " + plugin.transform("Hello Java"));
        }
        if (!found) {
            System.out.println("No plugin found");
        }
    }
}
\`\`\`

The host does not import \`demo.plugin.UppercasePlugin\`: binding to the implementation happens at runtime via the service descriptor.

\`\`\`bash
mkdir -p build/host-classes
javac -cp build/contract.jar -d build/host-classes host-src/demo/host/Main.java
jar --create --file build/host.jar --main-class demo.host.Main -C build/host-classes .
\`\`\`

In this packaging approach, \`host.jar\` contains only the host code and the \`Main-Class\` manifest attribute. It is **not** a fat JAR; the contract and plugin are separate files that must be placed on the runtime classpath.

### 4. Running and Verifying Replaceability

On Linux/macOS, the classpath separator is \`:\`:

\`\`\`bash
java -cp "build/host.jar:build/contract.jar:build/plugin.jar" demo.host.Main
\`\`\`

On Windows, use \`;\`:

\`\`\`powershell
java -cp "build/host.jar;build/contract.jar;build/plugin.jar" demo.host.Main
\`\`\`

The exact output of both:

\`\`\`text
uppercase: HELLO JAVA
\`\`\`

Try removing the plugin JAR from the runtime classpath:

\`\`\`bash
java -cp "build/host.jar:build/contract.jar" demo.host.Main
\`\`\`

Output:

\`\`\`text
No plugin found
\`\`\`

Thus, the same \`host.jar\` and \`contract.jar\` still run without any plugins, and detect the plugin when a JAR providing a provider is present. If you swap the provider or add a compatible provider, you do not have to recompile the host.

You can inspect the contents directly with:

\`\`\`bash
jar --list --file build/contract.jar
jar --list --file build/plugin.jar
jar --list --file build/host.jar
\`\`\`

Verify that \`contract.jar\` contains \`demo/api/MessagePlugin.class\`, \`plugin.jar\` contains \`demo/plugin/UppercasePlugin.class\` along with \`META-INF/services/demo.api.MessagePlugin\`, and \`host.jar\` contains \`demo/host/Main.class\`. The full listing also includes the manifest and directory entries depending on the packaging command.

## Dependency Rules When Using Maven or Gradle

In a multi-module project, express the dependency direction as follows:

\`\`\`text
:plugin-api          (defines the contract; published as a separate artifact)
:host                -> :plugin-api
:uppercase-plugin    -> :plugin-api
\`\`\`

With the Gradle Java Library plugin, example dependencies sections:

\`\`\`groovy
// host/build.gradle
plugins { id 'application' }
dependencies { implementation project(':plugin-api') }
application { mainClass = 'demo.host.Main' }
\`\`\`

\`\`\`groovy
// uppercase-plugin/build.gradle
plugins { id 'java-library' }
dependencies { compileOnly project(':plugin-api') }
\`\`\`

\`compileOnly\` is appropriate when the host runtime already supplies the API JAR and we do not want to repackage the contract into the plugin. It also means the plugin must be run in an environment where the contract is present; if you need to test the plugin independently, add \`testImplementation project(':plugin-api')\` as needed. For systems that publish plugins for third parties, the contract should have clear artifact coordinates and a version, such as \`com.example:plugin-api:1.0.0\`. Plugin authors compile against the published API without depending on internal host code.

If a plugin needs its own library, package or distribute that runtime dependency intentionally. A standard JAR does not bundle its dependent JARs. A fat JAR may fit certain models, but strictly avoid embedding a separate copy of \`contract.jar\` into the provider's ClassLoader space when the host expects the same contract class.

## Classpath, ClassLoader, and Type Identity

On the simple classpath in the example, all three JARs are loaded by the application ClassLoader. When moving to an architecture where the host loads plugins at runtime using \`URLClassLoader\`, you must maintain **one shared definition** of \`demo.api.MessagePlugin\` via the parent ClassLoader. In the JVM, a class's fully qualified name is **not enough** to guarantee the same type: class identity also depends on the ClassLoader that defined it. If the host and plugin load two copies of the contract in two different ClassLoaders, the two identically named interfaces may be incompatible and casting will fail (\`ClassCastException\`).

A common design is for the parent loader to provide the contract and shared types; the plugin's child loader loads the implementation and private dependencies, typically with the standard parent-first mechanism. You must proactively handle duplicate dependencies, package names, native libraries, resources, threads, unloading capability, and lifecycle management when moving to plugin isolation. \`ServiceLoader.load(MessagePlugin.class)\` defaults to using the thread context ClassLoader; if using a custom loader, pass the loader explicitly with \`ServiceLoader.load(MessagePlugin.class, pluginClassLoader)\`.

## Version Compatibility, Publishing, and Testing

- **Keep the contract small and stable:** avoid introducing implementation types, host-specific dependencies, or internal state into the API. Document rules for nullability, exceptions, thread safety, and lifecycle if they affect providers.
- **Manage API changes:** adding an abstract method to an interface can break older providers when the method is called; changing signatures or removing methods can cause linkage errors. Use binary compatibility checks and test plugins compiled against older API versions on the newer host. Default methods can sometimes aid extensibility, but conflicts and behavior must still be evaluated.
- **Separate the three build steps:** build/publish \`plugin-api\` first; host and plugins compile against the API artifact; release plugins without rebuilding the host. Verify metadata, JAR contents, and service descriptors after packaging.
- **Test both runtime states:** missing plugins should have a fallback or clear message; present plugins should be discovered and executed properly. With multiple providers, do not assume \`ServiceLoader\` order is business priority order; sort or select intentionally if needed.
- **Protect the host:** validate plugin IDs, inputs/outputs, provider errors, and compatibility before activation; \`ServiceLoader\` can throw \`ServiceConfigurationError\`, and implementations can throw exceptions. Third-party plugins running in the same process have access to many process resources; a separate JAR is not a security sandbox.

## Common Design Mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Host imports \`UppercasePlugin\` | Host is tightly coupled to one implementation; must rebuild when changing plugins | Host imports only the interface and discovers implementations |
| Plugin depends on \`host.jar\` | Exposes host internals, easily creates circular dependencies | Move genuinely shared types into an independent API |
| Packaging duplicate contracts in separate loaders | Identically named types may fail to cast | Use a single contract supplied by the parent loader |
| Missing \`META-INF/services\` | \`ServiceLoader\` cannot find providers on the classpath | Name the descriptor properly and package it in the plugin JAR |
| Putting only \`plugin.jar\` on the runtime classpath | Host or provider may fail to find the API | Supply \`contract.jar\` and required runtime dependencies |
| Assuming every plugin is compatible with every API | \`NoSuchMethodError\`, initialization failures, or behavioral changes can occur | Version the API and run compatibility tests |

## Pre-Distribution Checklist

1. Contract JAR contains only the public API and shared types designed to be stable.
2. Host JAR compiles against the contract without compile-time dependencies on implementations.
3. Plugin JAR compiles against the contract and includes complete provider descriptors and resources.
4. The runtime JAR set contains exactly one shared contract version in a compatible loader.
5. Run verification with plugins present, without plugins, with faulty plugins, and test compatibility across supported versions.
6. Release documentation clearly specifies the Java version, contract version, runtime dependencies, how to install/uninstall plugins, and the provider selection mechanism.

**Conclusion:** Separating the contract, host, and implementation into three artifacts enables independent plugin releases and keeps the host stable. Practical effectiveness depends on dependency direction, class-loading strategy, provider metadata, and compatibility rules verified at runtime.
