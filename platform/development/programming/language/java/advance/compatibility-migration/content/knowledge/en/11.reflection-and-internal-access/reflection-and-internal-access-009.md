# Class Name Strings in Configuration That `jdeps` Does Not Detect

A Java application can pass compilation and run `jdeps` without showing suspicious dependencies, yet still fail after upgrading the JDK or upgrading libraries. Sometimes the cause does not lie in a Java call written directly in source code, but in a **class name stored as a string**: in `.properties`, YAML, XML, or JSON files, environment variables, configuration tables, or plugin metadata. Only when the runtime reads that string and calls `Class.forName(...)`, `ClassLoader.loadClass(...)`, or a reflection-based framework does the JVM actually locate and use the corresponding class.

`jdeps` is a useful tool for analyzing **static dependencies in class files/JARs**. It is not an application execution tool and cannot fully infer which classes will be loaded from configuration data. Therefore, a `jdeps` result reporting no dependency **does not prove** that the application does not use an internal class, a renamed class, or an optional dependency at runtime.

In Java Advance Compatibility Migration, this is an important blind spot: a class referenced only through a configuration string may not appear as a type reference in the constant pool that `jdeps` relies on to build its dependency graph. This lesson explains the mechanism, common scenarios, and how to combine static analysis with configuration inspection and runtime observation so dynamic dependencies are not missed.

## 1. How Do Static Dependencies and Dynamic Dependencies Differ?

### 1.1. Static Dependency: The Class Is Referenced as a Java Type

Consider the code:

```java
package com.example.app;

import com.example.plugins.FastNormalizer;

public class Processor {
    public String process(String input) {
        return new FastNormalizer().normalize(input);
    }
}
```

To compile this class, the compiler must know the `FastNormalizer` type. The class file of `Processor` contains symbolic references to the corresponding class and member. A bytecode analysis tool such as `jdeps` has a basis to find that dependency relationship when the appropriate input classes and paths are provided.

This is a dependency **observable via static analysis**: if the used class changes its package, is deleted, or is moved out of its JAR, source code or binary consumers may be affected. `jdeps` helps list such dependencies, but does not replace runtime behavior verification.

### 1.2. Dynamic Dependency: The Class Name Is Data

Now consider the code:

```java
package com.example.app;

public class Processor {
    public Object create(String className) throws Exception {
        Class<?> type = Class.forName(className);
        return type.getDeclaredConstructor().newInstance();
    }
}
```

The program does not import `FastNormalizer`. The bytecode only needs to know standard APIs such as `Class`, `Constructor`, and `Object`. The specific class name can be supplied at runtime:

```properties
processor.implementation=com.example.plugins.FastNormalizer
```

Another run might use:

```properties
processor.implementation=com.example.plugins.LegacyNormalizer
```

With the exact same `Processor.class` file, two configurations can load two different implementations. There is no requirement for the compiler to record a type reference to every implementation in `Processor`'s class file. A tool that only analyzes static dependencies cannot know which class names will appear in production configuration.

### 1.3. Key Differences Determining Analysis Results

| Characteristic | Direct Type Reference | Class Name in Configuration String |
|---|---|---|
| Example | `new FastNormalizer()` | `Class.forName(configuredName)` |
| Compile-time checking | Compiler knows the type and API being called | Compiler does not know the final class name if it comes from configuration |
| Trace in consumer class file | Usually contains class/member references | May only show reflection APIs and config-reading strings/logic |
| `jdeps` infers dependency on implementation | Possible when static references exist | Cannot reliably infer from names present only in external configuration |
| When missing class is detected | Compile time or runtime depending on packaging | Usually only when runtime attempts to load the class |
| Post-migration risk | Bytecode/API, module, and JAR changes | In addition to the risks above: stale config, old class names, dynamic loading |

Two points must be distinguished: `jdeps` **can analyze the JAR containing the implementation** if that JAR is supplied as input; however, analyzing the application JAR **does not prove that the application will load that implementation via configuration**. The gap here is the missing *dynamic link from configuration data to the actual class*.

## 2. What Does `jdeps` Actually Observe?

`jdeps` is a tool bundled with the JDK used to analyze dependencies of Java class files, JARs, and modules. Common modes support viewing dependencies by package, class, or module.

Example:

```bash
jdeps --summary application.jar
```

Or view at the class level:

```bash
jdeps --verbose:class --recursive application.jar
```

When external dependencies are placed in the `libs` directory, you can supply the classpath for analysis:

```bash
jdeps --class-path 'libs/*' --verbose:class --recursive application.jar
```

`jdeps` can help identify referenced modules and packages, check dependencies on JDK internal APIs via static references it observes, and assist modularization planning. For example:

```bash
jdeps --jdk-internals application.jar
```

However, `--jdk-internals` does not turn the tool into a detector for every use of internal APIs. If the application merely reads the string `"jdk.internal.misc.Unsafe"` from a configuration file and loads the class via reflection, there may be no static class reference to `Unsafe` for `jdeps` to report.

### 2.1. What `jdeps` Cannot Fully Infer

- Class names read from `.properties`, YAML, XML, JSON files, or databases at runtime.
- Class names constructed via string concatenation, conventions, or environment names.
- Classes loaded by a custom `ClassLoader`, plugin framework, or `URLClassLoader` from a directory outside the main artifact.
- Providers located via `META-INF/services/` resources solely from provider names in service configuration file contents.
- Classes/constructors/methods selected via annotation metadata or framework configuration when no direct type reference exists in the analyzed code.
- Dependencies appearing only in a specific tenant, profile, feature flag, or rarely executed error branch.
- Class loading paths triggered by startup scripts, agents, containers, or deployment infrastructure.

Not every case above is completely invisible to all analysis modes: for instance, a module descriptor may declare `uses` or `provides`, and the provider's bytecode may have its own static references. The core point is that **the static dependency graph is not the graph of every class that will execute across all runtime configurations**.

### 2.2. Why a Clean `jdeps` Run Is Not Yet a Safe Migration Conclusion

Suppose:

```text
application.jar
   |
   | class files reference java.base and reflection APIs
   v
jdeps only sees familiar static dependencies

production.properties
   |
   | implementation=com.example.legacy.OldConnector
   v
Class.forName(...)
   |
   v
legacy-connector.jar (loaded only in production)
```

If the JAR `legacy-connector.jar` is omitted from the new image, `jdeps application.jar` has no reason to warn that the production configuration will miss a class. The failure only appears when execution reaches the code loading that connector. If the connector itself uses JDK internal APIs, the application may even pass class lookup yet fail when invoking reflection or methods inside that class.

## 3. Where Can Class Names Reside in a Java System?

It is not only `.properties` files that contain class names. In real systems, an implementation is often selected by configuration metadata spread across repositories, artifacts, and deployment infrastructure.

### 3.1. `.properties` Files

```properties
payment.gateway.class=com.example.payment.LegacyGateway
report.renderer.class=com.example.report.PdfRenderer
```

The application uses `Properties` or a configuration library to read the values. If the package `com.example.payment` is renamed, the source still compiles, yet the runtime may fail when loading `LegacyGateway`.

### 3.2. YAML and JSON

```yaml
pipeline:
  handlerClass: com.example.pipeline.LegacyHandler
```

```json
{
  "serializerClass": "com.example.serialize.CustomSerializer"
}
```

A framework can use `handlerClass` or `serializerClass` as data to instantiate objects. Renaming a package in code does not necessarily update independently deployed configuration files.

### 3.3. XML and Framework Metadata

```xml
<component
    name="auditPublisher"
    class="com.example.audit.FileAuditPublisher" />
```

An XML file in resources, a dependency JAR, or an external configuration directory can also specify runtime classes. Some frameworks accept fully qualified class names, while others accept aliases or IDs and map them to classes. You must understand each framework's structure; you cannot assume a single universal property name across all frameworks.

### 3.4. Java SPI with `META-INF/services/`

The Java Service Provider Interface can register implementations in resource files. Suppose there is a service interface:

```java
package com.example.spi;

public interface Encoder {
    byte[] encode(String value);
}
```

A provider JAR has the file:

```text
META-INF/services/com.example.spi.Encoder
```

File content:

```text
com.example.providers.Utf8Encoder
```

Client usage:

```java
ServiceLoader<Encoder> providers = ServiceLoader.load(Encoder.class);
for (Encoder provider : providers) {
    System.out.println(provider.getClass().getName());
}
```

The client has a static reference to the **service interface** `Encoder`, while the provider name `Utf8Encoder` may only be declared in the JAR's service resource. Running `jdeps` on the client does not guarantee finding and validating all provider names in service files. When a provider name is wrong, the class is missing, no matching constructor/provider method exists, or class loading fails, `ServiceLoader` can throw `ServiceConfigurationError`.

With *named modules*, services can also be declared using `uses` and `provides ... with ...` in `module-info.java`. This is module metadata, not arbitrary class name strings in a `.properties` file; both forms need to be checked when a system mixes classpath and module path.

### 3.5. Environment Variables, System Properties, and External Data Sources

```bash
java -Dapp.handlerClass=com.example.handlers.FastHandler \
     -jar application.jar
```

```java
String name = System.getProperty("app.handlerClass");
Class<?> type = Class.forName(name);
```

Actual values may be set in Docker Compose, Kubernetes manifests, Helm charts, secret/config management, startup scripts, or admin UIs. Scanning only the source repository may miss the very configuration running in production.

In some systems, class names are even stored in a database or delivered to the application via a configuration service. Treat those sources as part of the migration inventory, while avoiding printing sensitive data to logs or committing secret files into the repository.

## 4. End-to-End Example: A Class Existing Only in Configuration

Suppose an application is tasked with normalizing strings, but the implementation is chosen at runtime. The application code does not import any plugin class.

### 4.1. Application Source

File `src-app/com/example/app/ConfiguredNormalizer.java`:

```java
package com.example.app;

import java.io.InputStream;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class ConfiguredNormalizer {
    public static void main(String[] args) throws Exception {
        Properties config = new Properties();

        try (InputStream in = Files.newInputStream(Path.of("plugin.properties"))) {
            config.load(in);
        }

        String className = config.getProperty("normalizer.class");
        if (className == null || className.isBlank()) {
            throw new IllegalArgumentException("normalizer.class is required");
        }

        Class<?> type = Class.forName(className);
        Object instance = type.getDeclaredConstructor().newInstance();
        Method normalize = type.getMethod("normalize", String.class);
        Object result = normalize.invoke(instance, "  Hello Java  ");

        System.out.println(result);
    }
}
```

The example uses Java 11 or later (`Path.of` and `String.isBlank`). To keep the exercise simple, the application invokes the method purely via reflection; a better production design should use a strongly typed interface and restrict allowed implementations.

### 4.2. Plugin Source

File `src-plugin/com/example/plugins/FastNormalizer.java`:

```java
package com.example.plugins;

public class FastNormalizer {
    public FastNormalizer() {
    }

    public String normalize(String input) {
        return input.strip().toLowerCase(java.util.Locale.ROOT);
    }
}
```

File `plugin.properties`:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

The application can be compiled without needing the plugin JAR on the compile classpath. The plugin only needs to exist at runtime.

### 4.3. Compiling and Packaging

Example with a Unix-style shell:

```bash
mkdir -p out-app out-plugin

javac -d out-app src-app/com/example/app/ConfiguredNormalizer.java
javac -d out-plugin src-plugin/com/example/plugins/FastNormalizer.java

jar --create --file app.jar -C out-app .
jar --create --file normalizer-plugin.jar -C out-plugin .
```

Analyze the application:

```bash
jdeps --verbose:class app.jar
```

This analysis may show dependencies on `java.base` and APIs used in the application code, but will not necessarily show a dependency line to `com.example.plugins.FastNormalizer`: that class name resides only in `plugin.properties`, not as a type directly referenced by `ConfiguredNormalizer.class`.

Run the program with the plugin JAR:

```bash
java -cp 'app.jar:normalizer-plugin.jar' \
     com.example.app.ConfiguredNormalizer
```

Expected output:

```text
hello java
```

If `normalizer-plugin.jar` is omitted from the runtime classpath:

```bash
java -cp app.jar com.example.app.ConfiguredNormalizer
```

The program can fail with `ClassNotFoundException: com.example.plugins.FastNormalizer`, even though `app.jar` itself compiles and `jdeps` analyzes it cleanly.

On Windows, the classpath separator is a semicolon (`;`), for example `-cp 'app.jar;normalizer-plugin.jar'` in PowerShell. The `plugin.properties` file in the example above is read from the process's **working directory**; running from a different directory requires placing the file in the right location or modifying the code to accept a configuration path.

### 4.4. Renaming a Class Causes Errors That the Build Does Not Catch

Suppose in a later version, the plugin is renamed to `com.example.plugins.StandardNormalizer`, while the production configuration file still contains:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

If the old class is no longer in the artifact, the runtime will try to load the old name and fail. Recompiling the application does not fix configuration strings outside the JAR. This is a classic example of *a source build succeeding while the deployment is incompatible with actual configuration*.

Even if the new class has the same `normalize(String)` method as the old class, reflection does not automatically map the old class name to the new class name.

## 5. Runtime Errors That Can Appear After Finding the Class Name

Finding the class name string is the first condition, not the end of testing. The runtime must still locate the class, verify its bytecode, check access permissions, initialize it, and execute the functionality the framework expects.

| Error or Exception | Common Context | What to Check |
|---|---|---|
| `ClassNotFoundException` | `Class.forName` or class loader cannot find the configured name | Class name, JAR, classpath/module path, class loader |
| `NoClassDefFoundError` | Class is needed during linking/usage but a dependency is missing or earlier initialization failed | Runtime dependencies, initial cause, classpath |
| `UnsupportedClassVersionError` | Plugin was built for a newer class file version than the running JVM | Build and runtime JDKs, `--release`, bytecode version |
| `ClassFormatError` or `VerifyError` | Plugin bytecode is invalid or was transformed incorrectly by a tool | Agents, proxy/bytecode generators, actual artifact |
| `NoSuchMethodException` | Reflection searches for a constructor/method with a nonexistent signature | Plugin runtime API, method name, and parameter types |
| `IllegalAccessException` | Java reflection lacks permission to invoke the member | Modifiers, module access, reflection call style |
| `InaccessibleObjectException` | Deep reflection is blocked by JPMS strong encapsulation | `opens`, caller module, framework/JDK |
| `InvocationTargetException` | The method invoked via reflection threw an exception | `getCause()` to find the underlying logic error |
| `ExceptionInInitializerError` | Static initializer in the plugin failed | Environment variables, dependencies, initialization code |
| `ClassCastException` | Plugin does not actually implement the required interface/type contract or class loaders differ | API/SPI, class loaders, duplicate JARs |
| `ServiceConfigurationError` | SPI provider is misregistered or cannot be loaded/instantiated | `META-INF/services` files, module declarations, provider |

Do not fix every error by adding a JVM flag. Each category reflects a different stage or contract. For example, `--add-opens` will not make a missing class appear on the classpath; `--add-exports` will not fix a method whose descriptor changed; upgrading the JVM will not fix a wrong class name in YAML.

### 5.1. Reflection on JDK Internal APIs

An evident risk when upgrading the JDK is an internal class name sitting in configuration, such as a class in a `jdk.internal.*` package. If code only reads this name from properties and calls `Class.forName`, `jdeps --jdk-internals` on the consumer may not show the expected dependency.

However, when the runtime tries to deeply access a member of an internal class, JPMS may block it because the package is not exported or opened. Starting in JDKs that enforce strong encapsulation, calling `setAccessible(true)` on a non-public member of an internal package can throw `InaccessibleObjectException`.

Investigation must determine **which library** requires the internal class name, what API it uses, and whether an alternative version using standard APIs exists. In some cases `--add-opens` or `--add-exports` can be used as a temporary, clearly scoped measure, yet upgrading the framework/library or switching to a supported API should take priority.

## 6. Class Loaders and JPMS Make the Problem More Complex

### 6.1. A Class on Disk May Still Not Be Found by the Loader

The class loader determines the namespace and class visibility. In plugin applications, servlet containers, or frameworks, a class may reside in a JAR yet be loaded by a loader different from the one `Class.forName` is using.

`Class.forName(String)` uses a loader determined from the caller's context; some frameworks instead use the *thread context class loader*:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName(className, false, loader);
```

The `false` argument requests not initializing the class as part of that call. It does not guarantee that the class will initialize or execute successfully later.

When errors appear only in a plugin or container, record the actual class loader, class source path, and parent delegation mechanism. Do not assume that every class on the system is visible to the application class loader.

### 6.2. Same Class Name, Different Class Loader

The JVM distinguishes types by binary name **and defining class loader**. Two different loaders can define two classes with the same name that are not equivalent types. A plugin carrying its own copy of an API shared with the host can encounter a `ClassCastException` even though the class names in the message look identical.

Therefore, the dynamic dependency inventory needs to record both the JAR location and the class loader loading the class. Checking only the fully qualified class name is insufficient when using plugin systems or application servers.

### 6.3. Named Modules, `exports`, and `opens`

With JPMS, a plugin JAR placed on the module path may belong to a named module, an automatic module, or be omitted from the module graph depending on configuration. Having the right class name and the JAR on the module path does not guarantee the class is resolved and validly accessible.

In a named module:

- `requires` (or equivalent readability relationship per configuration) determines which module can read which module.
- `exports` exposes public types of a package for ordinary Java access from permitted modules.
- `opens` allows deep reflection into a package within the specified scope.

If a framework needs to invoke constructors or read private fields via reflection, the package may need `opens` for the framework module. Do not use `--add-opens` to mask every access error when a module, export, or dependency is actually missing.

### 6.4. Automatic Modules and Unnamed Modules in Migration

JARs on the classpath typically belong to an unnamed module; JARs without descriptors placed on the module path can become automatic modules. Moving a JAR from the classpath to the module path can alter how module resolution, package access, and service loading behave.

A plugin configuration that previously ran on the classpath may fail after switching to named modules because a module was not included in the graph or a package was not opened properly. When testing migration, use the exact production deployment mechanism rather than testing on the classpath just for convenience.

## 7. How to Find Missed Class Name Strings

Because `jdeps` cannot see all runtime data, you must supplement it with a **configuration inventory**. There is no single command guaranteed to find every class name; multiple sources must be combined.

### 7.1. Searching in Source and Resources

You can start with a search pass for common APIs and keys:

```bash
rg -n 'Class\.forName|loadClass\(|getDeclaredConstructor|ServiceLoader|setAccessible' \
  src

rg -n 'className|class-name|class:|implementation|provider|driverClass|factory' \
  src/main/resources config
```

The commands use `rg` (ripgrep) if installed. These are search hints, not a universal rule set for every framework; depending on the project, configuration keys may be `type`, `strategy`, `adapter`, `dialect`, or team-defined keys.

To find class names across many configuration files, you can search for strings matching familiar package-name patterns:

```bash
rg -n 'com\.example\.|org\.|jdk\.internal\.|sun\.' \
  config src/main/resources
```

Results must be manually categorized by context: not every dotted string is a class name; URLs, package names, loggers, and bean names can look similar.

### 7.2. Inspecting Resources Inside JARs

```bash
jar --list --file application.jar
jar --list --file plugin.jar
```

Pay attention to files such as:

```text
META-INF/services/*
META-INF/spring/*
*.properties
*.xml
*.json
*.yaml
*.yml
```

Not all JARs share the same structure. With Spring Boot executable JARs or artifacts packaging nested JARs, you must understand the loader and how resources are contained inside. If plugins are loaded from a separate directory at runtime, inspect that directory as well, not just the application JAR.

### 7.3. Reviewing Operational Configurations

For multi-environment systems, examine the configuration sources actually used:

- Config files mounted into containers or VMs.
- Environment variables and system properties passed in startup scripts.
- Kubernetes ConfigMaps, Helm values, or corresponding configuration management mechanisms.
- Plugin registration data in databases or feature flag management services.
- Profile-specific configurations such as `dev`, `test`, `staging`, and `prod`.
- Customer/tenant-specific configurations and existing legacy versions.

Take care not to print full secrets into logs for inventory purposes. You can extract keys and class name lists after redacting sensitive information.

### 7.4. Building a Dynamic Dependency Inventory Table

A useful tracking table may include:

| Field | Meaning |
|---|---|
| Config source | File, key, environment variable, or configuration service providing the class name |
| Effective value | Class name used after profiles and overrides are applied |
| Loader/module | Class loader or module expected to load the class |
| Artifact | JAR, image, or plugin bundle containing the class |
| Instantiation path | `Class.forName`, `ServiceLoader`, framework factory, or other mechanism |
| Contract | Required interface, constructor, method, annotation, or metadata |
| Environment | Dev/test/staging/prod/tenant where the configuration applies |
| Migration risk | Missing class, changed API, blocked reflection, too-new bytecode, etc. |
| Verification | Tests or logs proving the class loads and functions |
| Owner/status | Responsible team and resolution status |

Example:

| Config source | Effective value | Risk When Upgrading JDK | Minimum Test |
|---|---|---|---|
| `plugin.properties:normalizer.class` | `com.example.plugins.FastNormalizer` | Missing JAR or class package changed | Load, instantiate, and invoke `normalize` |
| `META-INF/services/...Encoder` | `com.example.providers.Utf8Encoder` | Provider not packaged or module unresolved | Iterate `ServiceLoader` and invoke `encode` |
| Property used by legacy framework | A `jdk.internal.*` class | Deep reflection blocked by strong encapsulation | Initialize framework and run an actual integration flow |

The inventory is part of the migration plan; avoid concluding "no risk" before confirming the effective configuration of relevant environments.

## 8. Observing Class Loading at Runtime

Configuration analysis finds candidates. Running the application under representative conditions confirms which classes are **actually loaded** and from where.

### 8.1. JVM Unified Logging

On modern JDKs, you can enable class loading logs:

```bash
java -Xlog:class+load=info -cp 'app.jar:plugin.jar' \
  com.example.app.ConfiguredNormalizer
```

Output may include class names and loading sources, depending on the JDK and log level. Since the logs can be large, collect them in a test environment, filter by package/plugin, or save to a file with appropriate data protection policies.

The goal is to answer specific questions:

- Is the configured class loaded?
- From which JAR or module is it loaded?
- Do multiple JARs contain classes with the same name?
- Does loading happen at startup or only when a feature is triggered?

If plugins are loaded through a custom class loader, class loading logs are a very useful supplementary source of evidence when the application's static classpath does not fully capture the plugin system.

### 8.2. Logging at the Implementation Selection Point

In code that actively reads class names from configuration, include structured or diagnostic logging to identify the config key, the resolved class name, and the load result:

```java
String className = config.getProperty("normalizer.class");
System.out.println("Selected normalizer class: " + className);

Class<?> type = Class.forName(className);
System.out.println("Loaded class from: " +
    type.getProtectionDomain().getCodeSource());
```

This is an illustration for a test environment; `CodeSource` can be `null` in some cases, and secret configuration data should not be logged. In production, use a controlled logger instead of `System.out.println`, and classify what information is permitted to be logged.

### 8.3. Testing Multiple Profiles and Feature Paths

A class present in configuration is not guaranteed to be loaded immediately at startup. For example, handlers for rare transaction types, tenant-specific providers, or backend-failure fallbacks may only be triggered on a specific branch.

Therefore, a passing startup smoke test is not enough. You should run scenarios that exercise different class names, including production profiles, optional plugins, error paths, and feature flags.

## 9. Testing Dynamic Contracts Instead of Only Checking Class Existence

Some tests stop at `Class.forName(name)` and assume the migration succeeded. This only proves the class was found (and possibly initialized depending on the overload), not that it is compatible with the framework or expected API.

### 9.1. Use an Interface Instead of Calling Methods by Name When Possible

Instead of unrestricted reflection:

```java
Object object = Class.forName(className)
    .getDeclaredConstructor()
    .newInstance();
```

design a concrete typed contract:

```java
package com.example.spi;

public interface Normalizer {
    String normalize(String input);
}
```

And load the implementation with type checking:

```java
Class<?> rawType = Class.forName(className);
Class<? extends Normalizer> implementation =
    rawType.asSubclass(Normalizer.class);

Normalizer normalizer = implementation
    .getDeclaredConstructor()
    .newInstance();

String result = normalizer.normalize("Example");
```

`asSubclass` helps detect early when the configured class does not implement the expected interface. However, the constructor may still be missing, non-public, or throw an exception; the full instantiation and business-call path must be tested.

### 9.2. Verify Constructor and Method Constraints

If the framework requires a no-argument constructor, check `getDeclaredConstructor()` and access permission conditions. If the framework expects a method with a specific signature, check both parameter and return types rather than only the method name.

When a framework uses annotations, generic metadata, or named modules, verify those conditions against the target framework/JDK version. Having only the right interface may not be enough if the framework still requires reflection into private members.

### 9.3. Quality Testing for SPI

An SPI test should iterate through actual providers and exercise them:

```java
import com.example.spi.Normalizer;
import java.util.ServiceLoader;

public class ProviderSmokeTest {
    public static void main(String[] args) {
        int count = 0;
        for (Normalizer normalizer : ServiceLoader.load(Normalizer.class)) {
            count++;
            System.out.println(normalizer.normalize("  JAVA  "));
        }
        if (count == 0) {
            throw new IllegalStateException("No Normalizer providers found");
        }
    }
}
```

The snippet requires the service interface and provider to be packaged properly. If the service is not mandatory in every profile, the `count == 0` condition must be adjusted according to environment policy rather than applied mechanically.

### 9.4. Testing Released Binaries

When migrating a library, you may need to keep an old client JAR and run it alongside a new runtime/dependency. If a class name in config points to an old implementation, verify both instantiation and the API calls the client expects. If you edit/recompile everything before testing, you can miss errors that existing production artifacts still hit.

## 10. Combining `jdeps` with Other Sources of Evidence

Do not discard `jdeps` just because it has blind spots. The proper approach is to use each source for the question it answers best.

| Source/Tool | Answers Well | Does Not Fully Prove |
|---|---|---|
| `jdeps` | Static dependencies at class/JAR/module level, static references to JDK internals | Class names coming from configuration data or runtime behavior |
| Source/config search | String literals, config keys, and provider names stored as text | Dynamically built values, out-of-repo overrides, rarely used code |
| `jar --list` and resource inspection | Which artifact contains classes/resources declaring providers | Classes actually loaded in the process |
| `javap -verbose`/`-s` | Class file version, constant pool, member descriptors | Runtime configuration, full module graph, framework behavior |
| `-Xlog:class+load=info` | Classes actually loaded in the executed paths | Classes not loaded on untested branches |
| Integration/contract test | Whether loading, instantiation, and execution succeed | Uncovered profiles, tenants, or production conditions |
| Release notes/migration guide | Which JDK/framework components changed or were removed | Whether a specific application uses that component via config |

### 10.1. Analyzing Plugin JARs Separately

If `legacy-connector.jar` is found in the inventory, you can run:

```bash
jdeps --jdk-internals legacy-connector.jar
jdeps --verbose:class --recursive legacy-connector.jar
```

When analyzing the plugin as well, you can uncover **static dependencies inside the plugin** that `jdeps` on the main application cannot see. However, if the plugin also uses string configuration or reflection, the same blind spot remains and must be checked further.

### 10.2. Note on Multi-Release JARs

A JAR may contain classes specific to different Java versions under `META-INF/versions/`. When using `jdeps` on a multi-release JAR, select the analysis option matching the target version, for example:

```bash
jdeps --multi-release 17 --verbose:class library.jar
```

This avoids inspecting only base classes and missing dependencies of the variant used on the target JDK. Even so, it still does not solve the problem of class names supplied by configuration outside the JAR.

## 11. Migration Process for Configuration-String Dependencies

A pragmatic workflow can be broken into the following steps.

### Step 1: Identify the Target Environment

Record the current and target JDK versions, vendor/build, frameworks, module path/classpath, plugin JARs, and startup configuration. Distinguish the compiler JDK from the actual JVM runtime.

### Step 2: Run Static Analysis

Use `jdeps` on the application and key JARs to list static dependencies. Record notable internal APIs or modules/packages. Do not mark something "unused" just because a class name does not appear in tool output.

### Step 3: Build an Inventory from Configuration

Search for `Class.forName`, `loadClass`, factory reflection, `ServiceLoader`, provider names, and configuration fields containing class names. Review resources inside JARs and configuration deployed outside the repository. For multiple profiles/tenants, record the effective value for each scope.

### Step 4: Map Class Names to Artifacts and Loaders

For each found name, identify the JAR containing the class, version, class file major version, and the class loader or module responsible for loading it. Flag cases where a class appears only in an optional artifact or the production environment.

### Step 5: Cross-Reference JDK/Framework Changes

Check removed or renamed classes/packages, changed APIs, strong encapsulation, module exports/opens, and plugin JDK requirements. Do not focus only on missing classes; a class may still exist yet no longer allow calling its old constructor or method.

### Step 6: Run Targeted Dynamic Tests

Exercise at least the class loading paths in the effective configuration: locate the class, instantiate it, verify interfaces/constructors, invoke representative operations, and handle exceptions. For SPI, iterate and activate providers. For ORMs/serializers, run integration tests with actual reflection permissions.

### Step 7: Observe Runtime

Collect class loading logs or diagnostics at plugin selection points. Confirm the source JAR, loader, and loading behavior in the target profile. Save enough trace data to reproduce without exposing secrets in logs.

### Step 8: Fix and Lock Down Contracts

If an old class name is no longer valid, update the configuration and deployment plan. If the implementation uses a JDK internal API, prefer standard APIs or supported dependencies/frameworks. For plugin architectures, gradually transition to explicit interfaces/SPIs, use aliases/versioning for implementations, and test contracts. If a temporary module flag is needed, record the owner and removal conditions.

### Step 9: Test in a Production-Equivalent Deployment

Test the exact container image, launcher, classpath/module path, plugin directory, and effective config. Exercise critical profiles, feature flags, and fallback cases. Conclude an item is resolved only when the configurations to be supported have test evidence, not merely when a `jdeps` job completes.

## 12. Designing Systems to Reduce Fragile Dependencies on Class Names

A class name in a configuration file is a direct coupling from deployment to implementation details. When renaming packages or refactoring, this coupling link is easily missed because the compiler does not enforce it. You can reduce risk in the following ways.

### 12.1. Use Stable Logical Names or Aliases

Instead of having configuration specify an FQCN:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

you can use a functional name:

```properties
normalizer.type=fast
```

The application maps `fast` to an implementation through a strongly typed registry. When renaming packages or replacing classes, developers can update the registry without editing every deployed configuration file. Aliases must also have a versioning policy, because changing what `fast` means can alter behavior even without a linking error.

### 12.2. Use an SPI with Tested Contracts

A stable interface and `ServiceLoader` reduce reliance on clients knowing the exact implementation class name. However, providers must still be properly registered, properly packaged, and tested in practice. Switching from unrestricted reflection to SPI does not automatically eliminate all dynamic dependencies.

### 12.3. Fail Fast with Helpful Error Messages

If the implementation is essential, validate the class/contract at startup or during an appropriate readiness step, rather than waiting for the first request to load the class and fail a client.

Error messages should state the configuration key, resolved class name, original error type, and relevant artifact/loader when possible. Do not wrap every failure in `RuntimeException("Unable to start")` and lose the original root cause.

### 12.4. Manage Plugin and Configuration Lifecycles

For systems with separately released plugins, establish a version policy, support matrix, and compatibility testing across host, plugin, JDK, and framework. When renaming classes, consider an alias/adapter mechanism or deprecation warnings for legacy configurations during the transition.

### 12.5. Restrict Classes Allowed to Be Loaded from Configuration

Do not allow untrusted data to freely specify class names and then load and instantiate arbitrary classes. If a class name can be manipulated via external input, use an allowlist/registry, validate configuration permissions, restrict plugin sources, and enforce appropriate trust boundaries.

This issue relates not only to migration, but also to security and operations. An unvetted plugin can execute arbitrary code with the process's privileges; a successful `Class.forName` call says nothing about the trustworthiness of the implementation.

## 13. Common Misconceptions

**"`jdeps` does not report the class, so the application does not depend on it."** Incorrect. The class may only be mentioned in `.properties`, YAML, XML, `META-INF/services/`, or a database and loaded at runtime.

**"If a class name string is in bytecode, `jdeps` will recognize it as a dependency."** Not necessarily. A plain string literal is not a Java type reference; `jdeps` does not execute `Class.forName` to inspect every string.

**"Scanning the source repository is enough."** Insufficient. Production configs, plugin directories, images, and resources inside dependency JARs may not reside in the application source.

**"A successful `Class.forName` is enough."** No. Constructors, methods, interfaces, module access, and initialization/execution logic can still fail.

**"`jdeps --jdk-internals` will detect all internal JDK accesses."** No. The tool primarily relies on static dependencies; internal APIs loaded via string/reflective lookups may not be detected.

**"Adding `--add-opens` will fix all class loading errors."** No. You must distinguish missing classes, mismatched bytecode versions, missing modules, missing exports, and blocked deep reflection.

**"If the application starts up, all plugins are compatible."** No. Many plugins are loaded only when invoked by a profile, feature flag, tenant, or error path.

**"Having a class in the JAR means the JVM loaded that exact class."** No. Classpath order, module path, class loaders, and duplicate JARs can determine which class is actually loaded.

**"Switching to `ServiceLoader` eliminates dynamic dependencies."** No. Providers are still registered via metadata, and provider loading must be tested.

## 14. Checklist for Investigating Class Name Strings During a JDK Upgrade

- [ ] Recorded actual JDK, vendor/build, frameworks, and classpath/module path mechanism.
- [ ] Ran `jdeps` on the application and critical JARs/plugins, understanding the scope of static analysis.
- [ ] Located all `Class.forName`, `ClassLoader.loadClass`, factory reflection, and `ServiceLoader` sites.
- [ ] Reviewed `.properties`, YAML, XML, JSON, and resource registrations inside JARs.
- [ ] Checked system properties, environment variables, and configuration outside the repository.
- [ ] Cataloged effective class names by critical profiles, tenants, and feature paths.
- [ ] Identified the JAR/module/class loader containing each implementation.
- [ ] Verified class file versions and the APIs/constructors/interfaces required by clients or frameworks.
- [ ] Assessed access to JDK internal APIs, module `exports`, and `opens`.
- [ ] Tested instantiation and functional invocation, not just class loading.
- [ ] Tested SPI providers, optional plugins, and rarely used execution paths.
- [ ] Observed class loading in a production-equivalent environment.
- [ ] Saved evidence and categorized unverified configurations.
- [ ] Prepared plans to update class names/aliases/registries and roll back when needed.

## 15. Conclusion

`jdeps` helps identify dependencies expressed via static references in class files, yet **cannot guarantee finding classes selected solely by name strings in runtime configuration**. When classes are loaded via reflection, `ServiceLoader`, plugin frameworks, or custom class loaders, implementation dependencies may go undetected by the compiler or `jdeps` analyzing the main application artifact.

In Java Advance Compatibility Migration, the solution is not to abandon static analysis tools, but to supplement them with additional sources of evidence: scanning configurations inside and outside JARs, checking provider metadata, identifying class loaders/modules, observing class loading, and running integration tests for critical configuration paths. A safe result is only valid once **the right class, right artifact, right JDK, right access permissions, and right behavior** have been verified in the target environment.