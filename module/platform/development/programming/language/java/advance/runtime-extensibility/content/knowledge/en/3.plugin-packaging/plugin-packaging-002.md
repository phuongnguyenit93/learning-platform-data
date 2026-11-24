# Plugin Packaging: Organizing Classes, Resources, and Private Dependencies in a Release Bundle

A Java plugin is not just a JAR file containing a few classes. A release bundle must tell the host **which part is the shared contract, which part is the plugin implementation, where resources are located, and which libraries must be loaded alongside the plugin**. Organizing these components properly enables the host to load and unload plugins in a controlled manner, avoid version conflicts, and diagnose deployment failures.

## 1. Defining Boundaries Before Packaging

Suppose a host application supports plugins implementing the Greeter interface. There are four groups to distinguish:

| Component | Role | Where It Should Be Placed |
| --- | --- | --- |
| **Plugin API/SPI** | Contract that both the host and plugins compile against, such as the Greeter interface and data exchange types | A stable API artifact, loaded by the host's shared class loader |
| **Plugin implementation** | SPI implementation classes, algorithms, internal configuration | Each plugin's own JAR |
| **Plugin resources** | Config files, templates, message bundles, service descriptors, default data | Resource paths inside the plugin's JAR or a well-defined configuration directory |
| **Private dependencies** | Libraries used solely by this implementation | Dependency JARs in the plugin's lib directory or validly packaged into the plugin JAR |

**Class identity principle:** in the JVM, a class's identity depends on both its *binary name* and the *class loader that defined it*. Two copies of dev.example.spi.Greeter defined by two different loaders are two distinct types, even with identical bytecode. Therefore, the host and plugin must see **the exact same copy of the API**. Do not include a duplicate API copy as a private library that a child loader might preferentially redefine.

**Boundary of responsibilities:** the host decides how to discover, create loaders, verify compatibility, and manage the lifecycle; the plugin provides the implementation along with only the resources/dependencies it genuinely needs. Good packaging does not replace the host's class-loading policy: both must be designed in alignment.

## 2. Source Structure and Release Bundle

A minimal example using Java 17+, one host, one API, one plugin, and one helper library used only by the plugin:

~~~text
demo/
├── api/src/main/java/dev/example/spi/Greeter.java
├── helper/src/main/java/dev/example/helper/TextUtil.java
├── plugin/src/main/java/dev/example/plugin/HelloGreeter.java
├── plugin/src/main/resources/
│   ├── META-INF/services/dev.example.spi.Greeter
│   └── hello-plugin/message.txt
└── host/src/main/java/dev/example/host/Host.java
~~~

After building, the plugin installation layout looks like:

~~~text
release/
└── hello/
    ├── hello-plugin.jar           # implementation + resources + service descriptor
    └── lib/
        └── plugin-helper.jar      # plugin's private dependency
~~~

The plugin-api.jar file stays on the **host's classpath**; do not place another copy in release/hello/lib. The demo uses a helper library we compile ourselves to clearly illustrate dependency linkage without needing to download libraries from the Internet.

In real projects, clearly distinguish three types of paths:

- **Source path:** where .java files and resources live before building.
- **JAR entry path:** path inside the JAR; Java looks up resources by this path, not by the source file's location on disk.
- **Deployment path:** where the host finds the plugin JAR and lib JARs at runtime.

Changing the deployment directory path does not automatically change resource paths inside the JAR.

## 3. Runnable Example: API, Plugin Class, Resource, and Private Dependency

### 3.1. Contract Provided by the Host

File **api/src/main/java/dev/example/spi/Greeter.java**:

~~~java
package dev.example.spi;

public interface Greeter {
    String id();
    String greet(String target);
}
~~~

The interface contains only types understood by both host and plugin. If an SPI method exposes a class from a private library in its parameters or return type, that library is no longer truly a private dependency: the host must understand that type as well. For public contracts, prefer JDK types or DTOs belonging to the API artifact.

### 3.2. Library Used Only by the Plugin

File **helper/src/main/java/dev/example/helper/TextUtil.java**:

~~~java
package dev.example.helper;

public final class TextUtil {
    private TextUtil() {}

    public static String compose(String prefix, String target) {
        return prefix + ", " + target + "!";
    }
}
~~~

Helper must not be referenced directly by the host. At runtime, the loader created for the plugin must be able to find plugin-helper.jar; merely putting the JAR into the lib folder is not enough if the host does not add it to the class lookup path.

### 3.3. Implementation Class Reading the Plugin's Own Resource

File **plugin/src/main/java/dev/example/plugin/HelloGreeter.java**:

~~~java
package dev.example.plugin;

import dev.example.helper.TextUtil;
import dev.example.spi.Greeter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class HelloGreeter implements Greeter {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String target) {
        try (var input =
                 HelloGreeter.class.getResourceAsStream("/hello-plugin/message.txt")) {
            if (input == null) {
                throw new IllegalStateException("Missing hello-plugin/message.txt");
            }
            String prefix =
                    new String(input.readAllBytes(), StandardCharsets.UTF_8).strip();
            return TextUtil.compose(prefix, target);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
~~~

File **plugin/src/main/resources/hello-plugin/message.txt** contains a single line:

~~~text
Hello
~~~

A path starting with / in Class.getResourceAsStream is an absolute path from the **classpath root of the loader that defined HelloGreeter**. When built, the corresponding entry inside the JAR is hello-plugin/message.txt, without the src/main/resources prefix. Specifying UTF-8 avoids depending on the environment's default charset.

File **plugin/src/main/resources/META-INF/services/dev.example.spi.Greeter** contains the provider's binary name without the .class extension:

~~~text
dev.example.plugin.HelloGreeter
~~~

The descriptor filename must match the **fully qualified name of the SPI interface**; the name inside the file must match the implementation class. This example uses Java ServiceLoader on the classpath; when migrating to the JPMS module path, the uses/provides declarations in module-info.java must be designed separately.

### 3.4. Host Creating a Class Loader with All Required JARs

File **host/src/main/java/dev/example/host/Host.java**:

~~~java
package dev.example.host;

import dev.example.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Host <plugin-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath();
        Path pluginJar = dir.resolve("hello-plugin.jar");
        Path helperJar = dir.resolve("lib/plugin-helper.jar");
        if (!Files.isRegularFile(pluginJar) || !Files.isRegularFile(helperJar)) {
            throw new IllegalArgumentException("Missing plugin or dependency JAR");
        }

        URL[] urls = {pluginJar.toUri().toURL(), helperJar.toUri().toURL()};
        ClassLoader apiLoader = Greeter.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(urls, apiLoader)) {
            ServiceLoader<Greeter> providers =
                    ServiceLoader.load(Greeter.class, pluginLoader);
            int count = 0;
            for (Greeter provider : providers) {
                System.out.println(provider.id() + " -> " + provider.greet("Java"));
                count++;
            }
            if (count == 0) {
                throw new IllegalStateException("No Greeter provider found");
            }
        }
    }
}
~~~

This is a **demo with hardcoded filenames** for easy verification. A real production host needs to read the plugin's manifest/metadata, validate the list of permitted JARs, and manage each loader; it should not arbitrarily infer dependency names by concatenating strings from the plugin name.

The parent of URLClassLoader is the loader that loaded Greeter. A standard URLClassLoader delegates to its parent first; thus the host and implementation see the same Greeter class. The URL of plugin-helper.jar is also added to the loader, enabling HelloGreeter to find TextUtil without the host needing to add helper to the shared classpath.

### 3.5. Compiling, Creating JARs, and Running

Run from the **demo/** directory in a POSIX shell (Linux/macOS, or compatible bash); requires JDK 17 or later:

~~~bash
mkdir -p build/api build/helper build/plugin build/host release/hello/lib

javac -encoding UTF-8 -d build/api api/src/main/java/dev/example/spi/Greeter.java
jar --create --file build/plugin-api.jar -C build/api .

javac -encoding UTF-8 -d build/helper helper/src/main/java/dev/example/helper/TextUtil.java
jar --create --file release/hello/lib/plugin-helper.jar -C build/helper .

javac -encoding UTF-8 -cp "build/plugin-api.jar:release/hello/lib/plugin-helper.jar" -d build/plugin plugin/src/main/java/dev/example/plugin/HelloGreeter.java
jar --create --file release/hello/hello-plugin.jar -C build/plugin . -C plugin/src/main/resources .

javac -encoding UTF-8 -cp build/plugin-api.jar -d build/host host/src/main/java/dev/example/host/Host.java
java -cp "build/host:build/plugin-api.jar" dev.example.host.Host release/hello
~~~

Expected output:

~~~text
hello -> Hello, Java!
~~~

On Windows, replace the **:** separator between classpath entries in the -cp argument with **;**, and create directories using your shell's syntax. The jar -C flag packages classes and resources at the **root of the JAR**; it does not create an extra build/plugin or src/main/resources directory layer inside the archive.

Inspect the plugin bundle:

~~~bash
jar --list --file release/hello/hello-plugin.jar
jar --list --file release/hello/lib/plugin-helper.jar
~~~

In hello-plugin.jar, at least the following three entries must appear (in addition to META-INF/MANIFEST.MF and directories):

~~~text
dev/example/plugin/HelloGreeter.class
META-INF/services/dev.example.spi.Greeter
hello-plugin/message.txt
~~~

In plugin-helper.jar, dev/example/helper/TextUtil.class must be present. Greeter.class does **not** need to be inside hello-plugin.jar or plugin-helper.jar. If the service descriptor is missing, ServiceLoader will not discover the implementation; if the resource is missing, the greet method throws an error per the check in the example; if helper is missing, loading or using the implementation may cause NoClassDefFoundError.

## 4. Choosing How to Distribute Private Dependencies

| Approach | Release Bundle | Key Considerations |
| --- | --- | --- |
| **Thin plugin JAR + lib/** | Plugin JAR contains only implementation/resources; dependency libraries are placed as separate JARs alongside | The host must include **all** required JARs in the plugin's class loader, including required transitive dependencies |
| **Uber/Fat JAR** | Bundles classes and resources from multiple dependencies into one JAR | Must properly merge ServiceLoader descriptors and identically named resources; check duplicate classes, licenses, signatures, and special META-INF files |
| **Shading + relocation** | Bundles and renames packages of libraries prone to conflicts | Update all class/resource/service references accordingly; watch out for reflection, serialization, and class names stored in config |
| **JAR-in-JAR (nested JAR)** | Plugin JAR contains .jar files inside it | Standard URLClassLoader/JDK classpath **does not automatically find classes** in nested JARs; requires explicit loader support or safe extraction before loading |

In the Gradle Java plugin, the default jar task typically packages the **source set outputs** (classes and resources), without automatically bundling external implementation dependencies into the archive. Similarly, declaring a Maven/Gradle dependency only ensures build-time/resolution relationships according to configuration; it does not mean a running host will automatically scan the plugin's lib directory.

One way to classify dependencies in a build:

- **Host-provided API:** needed by the plugin at compile time, but the plugin release does not ship its own separately loaded copy of the API. With Gradle you can use the compileOnly configuration for the corresponding SPI, depending on the multi-project design.
- **Private implementation dependency:** needed at runtime and must be distributed in lib/, or bundled/relocated using a tested strategy.
- **Dependency shared by host and plugin:** must have an agreed version and unified class loader; it is only private if it does not appear in the API or objects exchanged with the host.
- **Private resources:** packaged inside the JAR or pointed to via an external config location; prefer a plugin-prefixed directory name to avoid resource collisions.

When there are multiple plugins, **each plugin should have its own dependency closure and explicit class loader/lifecycle**. Using one global classpath for all dependencies can cause plugin A to inadvertently use a library version brought in by plugin B. However, a parent-first loader can still pick a class already present in the parent, even if the plugin's lib has a different version: separate directories alone are **not enough** to guarantee version isolation. If multiple versions truly must coexist, control which packages are supplied by the parent and which are loaded privately (such as a selective child-first policy or shading), always keeping JDK classes and the shared SPI on the parent side.

## 5. Rules for Organizing Classes and Resources

**Keep packages meaningful.** Place the SPI in an independent package, e.g., dev.example.spi; the implementation in the plugin's package, e.g., dev.example.plugin; and private helpers in packages belonging to their own libraries. Avoid placing plugin classes in the host's package or giving them the same class name as host classes and relying on classpath order.

**Use the right loader to locate resources.** For resources tightly coupled to the implementation, calling HelloGreeter.class.getResourceAsStream searches using that class's loader. ClassLoader.getResourceAsStream takes a path without a leading /; Class.getResourceAsStream with / uses a path from the root. Do not assume System.getClassLoader() or the working directory can find resources located only inside the plugin JAR.

**Mind the thread context class loader (TCCL).** Some frameworks/providers use Thread.currentThread().getContextClassLoader() to look up classes and services. The host may need to set the TCCL to the plugin's loader within the appropriate invocation scope, then **restore it in a finally block** so other tasks are unaffected. The example above uses the ServiceLoader.load(service, loader) overload, explicitly specifying the loader to search for providers.

**Resource namespaces can also collide.** Two plugins both having config.yml at the JAR root will be hard to distinguish if the host searches via a shared class loader. Place resources under a dedicated path like hello-plugin/; consider how parent-first resource lookup behaves before assuming a resource is private.

**Do not leak private dependencies through the SPI.** If the host receives an object belonging to a private library and tries to cast or call methods on it, class identity and version become an unintended contract. Pass stable API DTOs or JDK types instead.

**Discovery mechanisms must be packaged completely.** For ServiceLoader on the classpath, the file META-INF/services/<fully-qualified-SPI-name> is a JAR resource, not a class and not a Java manifest. If using custom metadata such as plugin.properties or a JSON manifest, the host must have code to read and validate it; Java does not activate a plugin merely because the file exists.

## 6. Versioning, Lifecycle, and Bundle Safety

A release should declare or record at least **plugin ID, plugin version, API compatibility, entry point/discovery convention, Java target version, locked dependency set, and checksum**. Metadata can be kept in the manifest or a separate file according to the host's contract. Use version pinning and dependency locking during builds; CI should produce the exact expected set of artifacts and verify licenses and dependency sources.

At runtime, the host should follow this sequence:

1. Discover the plugin directory/bundle and verify metadata, file existence, and checksum/signature per deployment policy.
2. Check Java/API compatibility; detect duplicate plugin IDs and unmet dependency requirements.
3. Create the class loader/module layer with the plugin's exact classpath; keep the SPI consistent with the host.
4. Load the provider, verify types, configuration, resources, and run a lightweight initialization check; on failure, log **plugin ID + version + cause** clearly.
5. Monitor active plugins; on stop, unregister, terminate tasks/threads, and close streams, sockets, JDBC pools, and loaders appropriately.

Closing a URLClassLoader releases the loader's access to JAR files, but **does not guarantee the JVM will immediately unload classes**. If threads, static caches, ThreadLocals, callbacks, or references from the host to plugin classes/objects remain, the loader may stay alive. Hot-update mechanisms require dedicated stop/reinitialize procedures and state handling; do not assume merely replacing a JAR on disk automatically swaps already-loaded classes.

A class loader is a namespace boundary, **not a security sandbox**. Plugins running in the same JVM can exercise the process's permissions. Do not load untrusted code into the host merely because it resides in a separate JAR; for untrusted code, process/container isolation, permission controls, and appropriate communication protocols are required.

## 7. Common Errors and How to Verify

| Symptom | Causes to Check | How to Fix |
| --- | --- | --- |
| ServiceLoader finds no provider | Missing/wrong META-INF/services, wrong binary name, provider not visible to loader | List JAR entries; check descriptor, verify provider implements SPI and correct loader is passed |
| ServiceConfigurationError: not a subtype or ClassCastException | Host and plugin see **two copies of SPI from different class loaders** | Ensure SPI comes from the shared loader; remove API copy redefined by the plugin loader |
| ClassNotFoundException / NoClassDefFoundError | Missing runtime dependency, wrong URL, or missing transitive dependency | List all runtime JARs; compare dependency tree against deployment classpath |
| NoSuchMethodError / IncompatibleClassChangeError | Library actually loaded differs from compile-time version; incompatible ABI | Check which loader loaded the class; pin versions and test with the exact release bundle |
| Resource returns null | File not in JAR, wrong path, or looked up via a different loader | Use jar --list; check leading / and internal path; prefer the plugin's own root class |
| Works in IDE, fails when installed as plugin | IDE adds dependencies to global classpath that release does not carry | Test using packaged JARs on a classpath containing only host and API |
| Fails after multiple reloads | Plugin did not stop threads/callbacks or host still holds references to loader | Track lifecycle and memory/class loaders; clean up before replacing versions |

**Pre-release checklist:** (1) clean build from source; (2) clearly distinguish shared API and private dependencies; (3) verify archive contents including classes, META-INF/services, and resources; (4) check transitive dependencies, versions, and conflicts; (5) run integration tests against the actual host from the packaged release directory, not relying on the IDE; (6) test a missing JAR/resource case to confirm errors are diagnosable; (7) test two plugins with different versions of a dependency if the system claims isolation support; (8) test stop/reload and observe references, threads, and file handles.

When **shared API – implementation – resources – private dependencies** are properly organized, plugin bundles can be deployed, tested, and upgraded independently of host source code, within the defined compatibility bounds and class-loader policy.
