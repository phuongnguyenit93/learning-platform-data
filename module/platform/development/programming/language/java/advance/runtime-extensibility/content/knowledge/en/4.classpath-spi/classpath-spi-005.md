# Relationship Between Registration File Location and Provider Class Visibility

In a Java SPI (Service Provider Interface) deployed on the **classpath**, an application can call `ServiceLoader` to locate classes implementing an interface without writing concrete class names directly into application code. However, having a JAR contain the provider class **does not guarantee** `ServiceLoader` will find that provider; conversely, finding the registration file **does not guarantee** the provider class can be loaded.

This lesson explains those two interrelated conditions precisely:

1. **The registration file is visible as a resource**: the class loader used by `ServiceLoader` must find a resource with the exact path `META-INF/services/<fully-qualified-service-name>`.
2. **The provider class is visible as a class and compatible with the service**: the class name written in the resource must be loadable through the active class loader; the class must be the right kind, satisfy the instantiation contract, and share the same service type identity with the application.

These are two separate steps. An application can see the provider class without seeing the registration file; it can also see the registration file without being able to load the class named inside it.

## 1. The ServiceLoader Discovery Chain on the Classpath

Suppose the application has a service interface **demo.spi.Formatter** and an implementation class **demo.impl.UpperFormatter**. A typical provider is located through the following process:

~~~text
Application: ServiceLoader.load(Formatter.class)
                       |
                       v
Choose ClassLoader L
  - Default: current thread's context class loader (TCCL)
  - Or: ClassLoader explicitly passed to load(service, L)
                       |
                       v
Find resource: L.getResources("META-INF/services/demo.spi.Formatter")
                       |
           +-----------+-----------+
           |                       |
      No resource             Resource found
           |                       |
           v                       v
  No providers discovered    Read UTF-8, extract provider name
  from file                        |
                                   v
                       Attempt to load demo.impl.UpperFormatter
                       via the corresponding class-loading mechanism
                                   |
                      +------------+------------+
                      |                         |
                 Cannot load                 Loaded
                      |                         |
                      v                         v
             ServiceConfigurationError    Check type and
             during provider iteration    instantiation rules
                                                |
                                  +-------------+-------------+
                                  |                           |
                                Valid                      Invalid
                                  |                           |
                                  v                           v
                          Instantiate provider         ServiceConfigurationError
                          on demand and return to app  during provider iteration
~~~

The diagram focuses on **providers on the classpath (unnamed modules)**. In a JVM with named modules, `ServiceLoader` also performs provider discovery via module descriptors, which is distinguished later.

There are two timing milestones to remember:

- Calling `ServiceLoader.load(...)` primarily creates the discovery object; file parsing, loading, and provider creation are **lazy**, typically occurring when calling `iterator`/`next`, `findFirst`, or processing a stream.
- When no matching registration file exists, iteration can return an empty sequence. When a file has an invalid declaration, iteration typically throws **`ServiceConfigurationError`**, rather than silently ignoring the broken configuration.

**Necessary conditions** for a provider to be discovered through the classpath registration file mechanism are that the resource path is correct and visible, the provider name is declared properly, the provider class can be loaded by the required loader, and it fulfills the service contract. Placing the class and the file next to each other is merely a convenient packaging choice; it is **not** a mandatory requirement.

## 2. Where Must the Registration File Reside?

For a classpath SPI, the resource name always follows the pattern:

~~~text
META-INF/services/<fully.qualified.ServiceType>
~~~

For example:

~~~text
META-INF/services/demo.spi.Formatter
~~~

UTF-8 content of this file:

~~~text
demo.impl.UpperFormatter
~~~

You must distinguish **the file name** from **the file contents**:

| Component | Whose Name Is Used? | Example |
| --- | --- | --- |
| File inside `META-INF/services` | **Service interface or service class** | `META-INF/services/demo.spi.Formatter` |
| One line inside the file | **Provider class implementing the service** | `demo.impl.UpperFormatter` |
| Actual class file | Package directory path of the provider | `demo/impl/UpperFormatter.class` |

Names must be **fully qualified binary names**, matching letter case. Do not append a `.class` extension, do not write filesystem paths instead of class names, and do not use the simple name `UpperFormatter` when the provider resides in a package. The registration file is not a Java source file, not an annotation, and must not be placed in the same package directory as `Formatter.class`.

A file can contain multiple providers, one name per line, with blank lines and comments starting with `#`. Names repeated within the same file or appearing across multiple configuration files for the same service are deduplicated by `ServiceLoader` during discovery. Provider ordering on the classpath depends on the order in which resources are found by the loader, and then the order of names in each file; applications should not treat system-wide classpath order as a durable priority policy.

### Source Paths and Runtime Paths Are Two Different Things

In a typical Maven/Gradle project, the file is **authored** at:

~~~text
provider-project/src/main/resources/META-INF/services/demo.spi.Formatter
~~~

Yet at runtime, it must sit at the **classpath root or JAR root** at the location:

~~~text
META-INF/services/demo.spi.Formatter
~~~

When a provider JAR is packaged properly, the final structure looks like:

~~~text
provider.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── demo.spi.Formatter
└── demo/
    └── impl/
        └── UpperFormatter.class
~~~

If the file ends up packaged as **src/main/resources/META-INF/services/demo.spi.Formatter** inside the JAR, `ServiceLoader` searching from `META-INF/services` will not see it. Similarly, a file under **META-INF/service/** (missing the `s`), with the wrong package for the interface name, or with mismatched letter case will not match.

The resource must actually be included in the build artifact. Creating the file in the source tree is not enough; verify the final artifact with `jar --list` or `jar --describe-module` as appropriate. Do not infer from your IDE that the file is definitely in the JAR.

## 3. Why Can Finding the Registration File Still Fail to Load the Provider?

After seeing the line `demo.impl.UpperFormatter`, `ServiceLoader` still has to work with the **class**, not just the resource.

A typical classpath provider must:

1. Be a **`public`, concrete class** implementing or extending the exact service type; avoid abstract classes or interfaces as classpath providers.
2. Have a **public no-argument constructor** for `ServiceLoader` to instantiate it; other constructors may exist but do not replace this requirement.
3. Have its own bytecode and required dependency classes loadable by the class loader.
4. When type-checked, actually be **assignable** to the service `Class` object passed by the application to `ServiceLoader`.

That last factor is critical: in the JVM, class identity is tied to **binary name and the class loader that defined the class**. Two types both named `demo.spi.Formatter` defined by two different class loaders are two distinct `Class` objects. Therefore, a provider compiled against its own copy of `Formatter` inside a child-first loader can be judged as not implementing the host's `Formatter`.

A common plugin design puts the **shared service API in the parent loader**, so the provider loader delegates loading `Formatter` to the parent. The plugin keeps its implementation classes and specific dependencies isolated, while host and plugin share a single `Class` object for the interface.

### Different Kinds of "Visibility"

- **Resource visibility**: the loader finds the registration file via `getResources(path)`.
- **Class visibility**: the loader can load the provider name and the provider's dependencies.
- **Type compatibility**: the provider is genuinely a subtype/implementation of the same service `Class` used by the caller.
- **Instantiation**: the provider has a valid constructor and initializes successfully.

Satisfying only the first one or two steps is not enough. You should not use `Class.forName(providerName)` with the default loader as sole proof, because the caller of that method and `ServiceLoader` may be using two different loaders.

## 4. Java 17 Example: Three JARs and Two Ways of Choosing a Class Loader

This self-contained example intentionally separates three components:

- **api.jar**: shared contract `demo.spi.Formatter`.
- **provider.jar**: class `demo.impl.UpperFormatter` along with `META-INF/services/demo.spi.Formatter`.
- **app.jar**: application using `ServiceLoader`.

Source file structure:

~~~text
spi-demo/
└── src/
    ├── demo/
    │   ├── spi/
    │   │   └── Formatter.java
    │   ├── impl/
    │   │   └── UpperFormatter.java
    │   └── app/
    │       └── Main.java
    └── META-INF/
        └── services/
            └── demo.spi.Formatter
~~~

**File src/demo/spi/Formatter.java:**

~~~java
package demo.spi;

public interface Formatter {
    String format(String input);
}
~~~

**File src/demo/impl/UpperFormatter.java:**

~~~java
package demo.impl;

import demo.spi.Formatter;
import java.util.Locale;

public final class UpperFormatter implements Formatter {
    public UpperFormatter() {
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**File src/META-INF/services/demo.spi.Formatter:**

~~~text
demo.impl.UpperFormatter
~~~

**File src/demo/app/Main.java:**

~~~java
package demo.app;

import demo.spi.Formatter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            show("context", ServiceLoader.load(Formatter.class));
            return;
        }

        if (args.length == 1 && args[0].equals("child")) {
            // The system classpath for this run does not contain provider.jar.
            show("context", ServiceLoader.load(Formatter.class));

            URL providerUrl = Path.of("build/provider.jar").toUri().toURL();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] { providerUrl },
                    Formatter.class.getClassLoader())) {

                // This loader sees provider.jar and shares Formatter from the parent.
                show("child", ServiceLoader.load(Formatter.class, pluginLoader));
            }
            return;
        }

        throw new IllegalArgumentException("Use no arguments or child");
    }

    private static void show(String label, ServiceLoader<Formatter> loader) {
        int count = 0;
        for (Formatter provider : loader) {
            count++;
            System.out.println(label + " -> "
                    + provider.getClass().getName() + ": "
                    + provider.format("Xin chào"));
        }
        System.out.println(label + " count=" + count);
    }
}
~~~

The code depends on no external frameworks or libraries. The program runs on **JDK 17+**; output is deterministic because there is only one provider and string formatting uses `Locale.ROOT`.

### Compiling and Packaging

From the **spi-demo** directory, run in Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p build/api build/provider build/app build/provider/META-INF/services

javac -encoding UTF-8 -d build/api src/demo/spi/Formatter.java
javac -encoding UTF-8 -cp build/api -d build/provider src/demo/impl/UpperFormatter.java
cp src/META-INF/services/demo.spi.Formatter build/provider/META-INF/services/
javac -encoding UTF-8 -cp build/api -d build/app src/demo/app/Main.java

jar --create --file build/api.jar -C build/api .
jar --create --file build/provider.jar -C build/provider .
jar --create --file build/app.jar -C build/app .
~~~

On Windows PowerShell, you can replace `mkdir -p` with `New-Item -ItemType Directory -Force` for each directory and replace `cp` with `Copy-Item`. The remaining `javac` and `jar` commands stay the same.

Inspect the JAR contents after building:

~~~bash
jar --list --file build/provider.jar
~~~

Both entries must appear in the list:

~~~text
META-INF/services/demo.spi.Formatter
demo/impl/UpperFormatter.class
~~~

Note: `jar --list` may also display directories and the manifest; the two lines above are **the entries to verify**, not the entire stdout.

### Experiment A: Classpath Without provider.jar

~~~bash
java -cp "build/api.jar:build/app.jar" demo.app.Main
~~~

Exact output:

~~~text
context count=0
~~~

The application has the `Formatter` interface and the `ServiceLoader` call, yet the default loader does not see the registration file inside `provider.jar` because that JAR was not put on the classpath. Failing to find a provider does not mean `UpperFormatter`'s code is wrong.

### Experiment B: Putting provider.jar on the Classpath

~~~bash
java -cp "build/api.jar:build/provider.jar:build/app.jar" demo.app.Main
~~~

Exact output:

~~~text
context -> demo.impl.UpperFormatter: XIN CHÀO
context count=1
~~~

Now the main thread's context class loader (in this standard launch, the application class loader) sees `META-INF/services/demo.spi.Formatter` and `demo.impl.UpperFormatter`, and the provider implements `Formatter` taken from `api.jar`.

### Experiment C: provider.jar Present Only in a Child URLClassLoader

Keep `provider.jar` off the system classpath and pass the `child` argument:

~~~bash
java -cp "build/api.jar:build/app.jar" demo.app.Main child
~~~

Exact output:

~~~text
context count=0
child -> demo.impl.UpperFormatter: XIN CHÀO
child count=1
~~~

This is crucial evidence of the relationship between **resource location – chosen loader – class loading capability**:

- The `ServiceLoader.load(Formatter.class)` call uses the current thread's context class loader. This loader lacks `provider.jar`, so it sees no registration.
- The `ServiceLoader.load(Formatter.class, pluginLoader)` call uses the new `URLClassLoader` whose URL points to `provider.jar`. It sees the registration file and loads the provider.
- The parent of `pluginLoader` is `Formatter.class.getClassLoader()`; thanks to delegating from child loader to parent loader for the service API, provider and host use the exact same `Formatter` type.

If you subsequently call `ServiceLoader.load(Formatter.class)` from a thread whose **context class loader was temporarily set to `pluginLoader`**, discovery can also see the provider; you must restore the old loader in a `finally` block and avoid retaining references to a closed class loader/plugin. Using an explicit loader parameter is usually easier to control when the host actively manages individual plugins.

**On Windows**, the classpath separator is a semicolon (**;**), whereas on Linux/macOS it is a colon (**:**). Therefore the `-cp` part of Experiment A can be written `-cp "build/api.jar;build/app.jar"` in PowerShell. This is the classpath element separator, not part of the `META-INF/services` path inside a JAR.

## 5. Experiment Distinguishing "Having the Class" from "Having the Registration"

From `build/provider` created above, you can package two additional JARs that intentionally separate the class part and the resource part:

~~~bash
# Contains only package demo/impl/..., without META-INF/services
jar --create --file build/class-only.jar -C build/provider demo

# Contains only META-INF/services/..., without demo/impl/...
jar --create --file build/registry-only.jar -C build/provider META-INF
~~~

**Case 1 — class only, missing registration file:**

~~~bash
java -cp "build/api.jar:build/class-only.jar:build/app.jar" demo.app.Main
~~~

Output:

~~~text
context count=0
~~~

The JVM could load the provider class if requested by name, yet `ServiceLoader` has no resource declaring the provider to discover.

**Case 2 — registration only, missing class:**

~~~bash
java -cp "build/api.jar:build/registry-only.jar:build/app.jar" demo.app.Main
~~~

When iterating over providers, the program will fail with **`ServiceConfigurationError`**, because `demo.impl.UpperFormatter` is declared yet cannot be loaded. The exact stack trace and wording can vary by JDK version; what matters is **failure during provider discovery/loading**, rather than a valid empty list.

**Case 3 — class and registration in two separate JARs yet both visible:**

~~~bash
java -cp "build/api.jar:build/registry-only.jar:build/class-only.jar:build/app.jar" demo.app.Main
~~~

Output:

~~~text
context -> demo.impl.UpperFormatter: XIN CHÀO
context count=1
~~~

This proves that **the resource and the provider class do not have to be in the same JAR**. What decides the outcome is whether the initiating loader used by `ServiceLoader` sees the resource and can load the provider under the effective class-loading model. Still, when distributing an independent plugin, packaging declaration and implementation together in one provider JAR helps avoid missing one of the two parts.

## 6. Relationship Between Parent, Child, and Thread Context Class Loaders

A class loader can look up resources or classes from different places. With the common `URLClassLoader`, requests normally delegate to the parent first; some containers/plugin frameworks use different rules. Therefore, **do not infer visibility solely from a class or JAR existing on disk**. You must examine the specific loader `ServiceLoader` is using, its parent chain, assigned URLs/classpath, and framework policies.

| Actual Distribution | Loader Passed to ServiceLoader | Common Consequence |
| --- | --- | --- |
| Provider JAR is absent from all URLs/classpath of the loader used | Application loader | Does not see registration file, 0 providers from that JAR |
| Registration and class both in a provider JAR visible to the loader | Application loader | Finds resource and loads provider if contract is valid |
| Provider class visible but resource is not at the exact path | Loader with the class | Does not auto-detect provider; 0 providers for the missing file |
| Resource visible, provider class cannot be loaded | Loader with the resource | `ServiceConfigurationError` during iteration |
| Child loader sees provider JAR, parent loader sees only service API | Child loader | Succeeds when sharing the same service `Class` via parent |
| Parent loader sees only API, app calls `ServiceLoader.load(service)` on a thread whose TCCL is parent | Parent loader | Cannot find providers residing only in child loader |
| Plugin has its own copy of API defined as a different `Class` | May see resource and class | May fail with provider not being a subtype of host's service |

The case where a resource is found from a parent loader while the class resides in a child loader must be analyzed via the **initiating loader in `ServiceLoader.load(service, loader)`**. Under the Java SE 17 contract, a provider registered via a resource file can reside in a different JAR from the file; the provider class must be visible from the loader **initially queried** to find resources, not necessarily identical to the loader that ultimately found that resource.

**TCCL (thread context class loader)** allows shared infrastructure, even when defined in a parent loader, to locate extensions of an application running under a child loader. By default, `ServiceLoader.load(Formatter.class)` is equivalent to calling with `Thread.currentThread().getContextClassLoader()`. TCCL is per-thread state, so server environments, thread pools, workers, or executors may carry a different loader than the originating caller thread.

In a plugin host, establish a consistent rule: use **`ServiceLoader.load(Service.class, pluginLoader)`** for every discovery, or manage TCCL deliberately and always restore it afterward. Avoid caching a single `ServiceLoader` using TCCL across all applications/tenants: the loader active when it was created may be wrong for subsequent requests, and holding the cache can prevent garbage collection of old class loaders.

## 7. Diagnosing Errors in the Proper Order

When `ServiceLoader` does not return the expected provider, inspect in order from **artifact -> resource -> class -> type -> instantiation**, rather than guessing constructor bugs right away.

### Step 1 — Inspect the Packaged Artifact

Verify the provider JAR actually contains the class and resource:

~~~bash
jar --list --file build/provider.jar
~~~

Look for the exact entries `META-INF/services/demo.spi.Formatter` and `demo/impl/UpperFormatter.class`. For applications using Maven/Gradle, inspect the JAR **after build/shade/fat-jar**, not just the source tree. If the resource was omitted from the JAR, move it into `src/main/resources` and configure resource copying.

### Step 2 — Identify the Loader and Probe the Actual Resource

This is a diagnostic snippet to place **inside a program that already has `Formatter` on the classpath** (not a standalone runnable Java file):

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
String path = "META-INF/services/" + demo.spi.Formatter.class.getName();
var found = loader.getResources(path);
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

Printing no URLs means that loader does not see the resource via `getResources(path)`. If a URL appears, open that exact file to confirm the provider name and encoding. Results may include multiple resources from different JARs; `ServiceLoader` can combine valid declarations. In containers or environments using custom class loaders, inspect the actual class of the loader and its parent order.

### Step 3 — Use That Same Loader to Check the Provider Class

The following diagnostic snippet also runs in a program that already imports or has the `demo.spi.Formatter` API, using the exact `loader` variable from the step above:

~~~java
Class<?> candidate = Class.forName(
        "demo.impl.UpperFormatter", false, loader);
System.out.println(demo.spi.Formatter.class.isAssignableFrom(candidate));
System.out.println(candidate.getClassLoader());
System.out.println(demo.spi.Formatter.class.getClassLoader());
~~~

- **`ClassNotFoundException`**: the loader cannot load the provider name; check JAR, classpath, parent/child, and package name.
- **`NoClassDefFoundError` or similar linkage error**: a dependency may be missing or a class version incompatible; check the dependency tree and bytecode/JDK version.
- **`isAssignableFrom` returns `false`**: the provider does not actually implement the right service API, or there is a separate API copy giving a different `Class` identity.
- **All steps above pass yet `ServiceLoader` still fails**: check `public` visibility, public no-arg constructor, exceptions during initialization, and configuration file contents.

`Class.forName(..., false, loader)` **is only for diagnosing type loadability and does not instantiate the provider**. Its result does not replace testing the full `ServiceLoader` process. If the system uses an explicit plugin loader exclusively, replace the `loader` variable with **that exact plugin loader** instead of TCCL.

### Step 4 — Match Symptoms to Causes

| Symptom | Cause to Check First | How to Confirm |
| --- | --- | --- |
| Iteration completes with 0 providers | Resource not visible or wrong resource name | `getResources(path)` empty; `jar --list` lacks entry |
| Resource exists but error `Provider ... not found` | Provider class not visible | `Class.forName` with the exact loader fails |
| Error `provider not a subtype` | API loaded as two distinct types or class implements wrong type | `isAssignableFrom`, compare class loaders of service API |
| Error `no public no-args constructor` | Classpath provider lacks a public no-arg constructor | Inspect class code and constructors |
| Works in IDE, loses provider when packaged as JAR | Resource not copied, plugin JAR absent from runtime classpath | Compare build output and launch command |
| Found via child loader but not via `load(service)` | TCCL is a different loader | Print TCCL, call `load(service, pluginLoader)` |
| Some providers appear, others do not | Resource on different classpath, missing class/dependency, or invalid config | List all resource URLs, iterate each provider with clear error handling |
| Not visible after adding plugin | Class loader or `ServiceLoader` cache still uses old config | Check effective loader/URLs and reload/discovery mechanism |

In production, catch `ServiceConfigurationError` at the plugin-loading boundary to log full context (service, provider, loader, artifact) and apply an error-isolation policy. Do not mask errors by returning an empty list, as operators will think no plugin is installed.

## 8. Common Packaging Pitfalls and Limitations

### Package Renaming, Shading, and Fat JARs

When a build tool merges multiple libraries into a fat/uber JAR, those JARs may both contain `META-INF/services/demo.spi.Formatter`. Simply overwriting one file causes some providers to lose registration. You must **merge service descriptors** using the appropriate build feature, and update service/provider names inside descriptors when relocating packages.

For example, if a class is relocated from `demo.impl.UpperFormatter` to `shaded.demo.impl.UpperFormatter` yet the file still records the old name, `ServiceLoader` sees the registration yet fails to load the old provider name. Conversely, if the class is right yet the descriptor is filtered out of the JAR, 0 providers are discovered.

### A Directory Containing JARs Is Not Automatically on the Classpath

Putting `provider.jar` in a `plugins/` directory does not mean the application class loader automatically scans it. The `-cp` option reads only explicitly declared elements; wildcard syntax like `lib/*` expands JARs **directly inside `lib`**, not recursively across subdirectories. If the host loads plugins dynamically, it must explicitly supply URLs to a plugin loader and pass that loader to `ServiceLoader`.

Do not treat relative paths in a workspace as proof for production; in Java, the actual `-cp` and working directory at launch time determine what entries are searched. For an executable JAR launched with `java -jar`, a user-supplied `-cp` option is ignored for the launcher's class search path; you must use manifest `Class-Path` or an appropriate launcher/loader mechanism, and verify the specific launch mode.

### `reload` Cannot Fix a Broken Classpath

`ServiceLoader.reload()` clears the discovered-provider cache of **that specific `ServiceLoader` instance** and lets the next iteration re-discover. It does not add JARs to a `URLClassLoader`, does not fix `META-INF/services` entry names, does not make classes in another loader visible, and does not guarantee class unloading. Dynamic plugin systems usually require a separately managed class loader/plugin session, along with resource closing and reference cleanup procedures.

### Service Scope on Classpath vs. Module Path

This lesson focuses on the classpath. With an **explicit named Java module**, providers are typically published via `module-info.java`:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.Formatter with demo.impl.UpperFormatter;
}
~~~

The corresponding service-consuming module declares `uses demo.spi.Formatter`; the host must configure the module path, module readability, and an appropriate module layer. You cannot conclude that classpath `META-INF/services` files are the sole mechanism for all Java SPIs. Automatic modules have their own compatibility rules; do not mechanically apply classpath class/descriptor results to an application running on the module path.

## 9. Pre-Release Verification Checklist for Providers

1. **Service name**: exact file name `META-INF/services/<binary name of service>`, exact case, UTF-8 encoding.
2. **Registration content**: each line is a provider binary name, updated for any shading/relocation.
3. **Artifact**: the finished JAR contains the right resource path and required class bytecode, not merely present in the source tree.
4. **Runtime visibility**: the loader actually used by `ServiceLoader` sees the resource via `getResources` and can load the class and provider dependencies.
5. **Shared API identity**: host and provider use the same `Class` for the service, with no incompatible duplicate copies across loaders.
6. **Construction**: the classpath provider is a public concrete class with a public no-arg constructor that initializes without errors.
7. **Discovery code**: call the right `load(service, loader)` overload or manage TCCL; remember providers are discovered lazily, so errors may appear during iteration.
8. **Packaging tests**: test runs with API-only, with provider, class-only, registration-only, and two split JARs; run from the actual release command.
9. **Lifecycle**: for hot reload, recreate loaders/services within the right scope and release references holding old loaders; do not treat `reload()` as a cure-all for classpath changes.

A sound verification process always answers **"does the loader see the resource?"**, **"can the loader load the provider?"**, and **"is the provider the right service `Class` and validly instantiated?"**. The registration file location governs the **discovery** step, while provider class visibility and compatibility govern the **loading/instantiation** step; both must succeed for a classpath SPI to work.

**Official reference:** [Java SE 17 ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).