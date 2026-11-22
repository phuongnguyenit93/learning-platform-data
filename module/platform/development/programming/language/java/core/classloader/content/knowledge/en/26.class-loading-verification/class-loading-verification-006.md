# Verifying Resource Lookup and Service Providers in Java ClassLoader

A plugin system can **load classes** yet still **fail to read resources** or **fail to find service providers**. Conversely, a `getResource(...)` call can return a valid URL but retrieve the **parent's copy of the resource**, rather than the one with the same name in the child plugin. Therefore, when testing a classloader, you cannot simply assert that “`loadClass` succeeds” and conclude that resources and SPI are also correct.

This article builds a **behavioral verification** process for three components:

1. **Resource lookup:** `ClassLoader.getResource`, `getResources`, `getResourceAsStream`, `URLClassLoader.findResource`, `Class.getResource`.
2. **Service provider discovery:** SPI, `META-INF/services/<binary-service-name>`, `ServiceLoader`, lazy discovery, and the provider constructor.
3. **Correct classloader boundaries:** parent delegation, the provider's defining loader, shared SPI type, TCCL, and named modules when applicable.

Results must be verified using the **actual requested name/path, the loader used, the returned source URL, the number of providers, and runtime type identity**. Do not rely on a directory/JAR “having that file on disk” as sufficient proof.

## 1. Objectives of Resource and Service Provider Testing

Suppose the application has:

~~~text
ApplicationLoader
  |
  +-- api.Formatter (SPI interface)
  +-- config/marker.txt         (resource: parent-data)
  |
  +-- PluginLoader (child)
        |
        +-- plugin.PluginFormatter.class
        +-- META-INF/services/api.Formatter
        +-- config/marker.txt   (resource: plugin-data)
~~~

We want to verify:

- The parent can load **`api.Formatter`** and the child uses the **same runtime API type**, without defining another copy of the SPI itself.
- `PluginLoader.getResource("config/marker.txt")` under default delegation can return the **parent resource**.
- `PluginLoader.findResource("config/marker.txt")` (if it is a `URLClassLoader`) finds the URL source **specific to the child**.
- `PluginLoader.getResources("config/marker.txt")` can show **both resources**, not just the first result.
- `ServiceLoader.load(api.Formatter.class, parent)` does not find the plugin's provider because the descriptor/class is in the child.
- `ServiceLoader.load(api.Formatter.class, pluginLoader)` finds exactly **one provider**, can instantiate it, and the provider implements the correct runtime SPI.
- `ServiceLoader.load(api.Formatter.class)` uses the **thread context class loader (TCCL)**; setting the right pluginLoader within a controlled scope helps find the provider; finally, the TCCL must be restored.

This is a **contract test of the loader architecture**: if any assertion differs from expectations, review the classpath structure, descriptors, parent chain, runtime types, or resource policy.

## 2. Resource APIs Have Different Path Rules

### 2.1. `ClassLoader.getResource(String)`

~~~java
URL url = pluginLoader.getResource("config/marker.txt");
~~~

This is an illustrative snippet; it requires an existing `pluginLoader` variable and an import for `java.net.URL`.

- Accepts the resource name as a **path from the search path root**, using `/`.
- Returns **one URL** or `null`.
- The default behavior of `ClassLoader` queries the parent first, then `findResource` of the current loader.
- If both parent and child contain a resource with the same name, **the parent can shadow the child**.
- In named modules, resources belonging to a package of a named module may be subject to `opens` and encapsulation rules; having a physical URL does not necessarily mean the ClassLoader API will return it.

### 2.2. `ClassLoader.getResources(String)`

~~~java
Enumeration<URL> urls =
        pluginLoader.getResources("config/marker.txt");
~~~

- Returns an `Enumeration<URL>` of multiple candidates, which may include parent and child.
- Used when verifying **duplicate resource names** or formats that have multiple files with the same name.
- Do not automatically treat the enumeration order as a long-term business priority if the plugin architecture has custom overrides.
- Ensure streams are closed **after opening** each URL; `getResources` only returns a URL enumeration, not opened streams.

Counting:

~~~java
List<URL> all = Collections.list(
        pluginLoader.getResources("config/marker.txt"));

System.out.println("resource candidates: " + all.size());
~~~

This is an illustrative snippet with imports `java.util.List`, `java.util.Collections`.

### 2.3. `URLClassLoader.findResource(String)`

~~~java
URL own = pluginLoader.findResource("config/marker.txt");
~~~

Here, the `pluginLoader` variable is assumed to be of type `URLClassLoader`. The `findResource` API on `URLClassLoader` is public and finds **the resource in that loader's URL search path**, without querying the parent like the default `getResource`. For other classloader subclasses, `findResource` is usually a protected hook and cannot necessarily be called from the host.

**Do not conclude:** `findResource` is “always better than” `getResource`. Only use it when **there is an explicit requirement to select the plugin's resource**, or to debug the source. In frameworks where a dedicated resource policy has already been defined, follow that policy.

### 2.4. `getResourceAsStream(String)`

~~~java
try (InputStream in =
        pluginLoader.getResourceAsStream("config/marker.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing marker");
    }
    String text = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

This is an illustrative snippet; it requires imports `InputStream` and `StandardCharsets`. The stream may be `null` if not found. **It must be closed after reading**, even when URLClassLoader is closed at the end of the plugin lifecycle.

Do not cache or share a single `InputStream` across threads; it has read-cursor state and a `close` lifecycle. If you want to cache shared resource data, cache a byte snapshot or an immutable representation and create a separate stream for each caller.

### 2.5. `Class.getResource` and Package-Relative Names

Assume class `plugin.PluginFormatter` is in package `plugin`:

~~~java
Class<?> type =
        pluginLoader.loadClass("plugin.PluginFormatter");

// Relative to the plugin package:
URL a = type.getResource("settings.txt");

// Absolute from the root:
URL b = type.getResource("/plugin/settings.txt");

// ClassLoader accepts a root-relative name, WITHOUT a leading slash:
URL c = pluginLoader.getResource("plugin/settings.txt");
~~~

This is an illustrative snippet; the URLs are only non-null when the file actually exists at the right path.

| Call | Resource name looked up |
|---|---|
| `PluginFormatter.class.getResource("settings.txt")` | `plugin/settings.txt` |
| `PluginFormatter.class.getResource("/plugin/settings.txt")` | `plugin/settings.txt` |
| `pluginLoader.getResource("plugin/settings.txt")` | `plugin/settings.txt` |
| `pluginLoader.getResource("settings.txt")` | `settings.txt` at root |

**Do not mix these conventions** when writing tests: `ClassLoader.getResource("/plugin/settings.txt")` is not the standard way to pass a path like `Class.getResource("/plugin/settings.txt")`.

## 3. Having a Resource on Disk Does Not Mean It Is in the Runtime Artifact

A common mistake is that the source code has:

~~~text
src/main/resources/config/marker.txt
~~~

but the runtime artifact does not contain:

~~~text
config/marker.txt
~~~

`javac` compiles `.java` files and **does not copy all text files by default** into the output class directory. Gradle/Maven have dedicated resource processing; when using the `javac` command directly, resources must be copied manually.

If distributing a plugin JAR, check:

~~~bash
jar --list --file dist/plugin.jar
~~~

Entries must have names using `/`, for example:

~~~text
plugin/PluginFormatter.class
META-INF/services/api.Formatter
config/marker.txt
~~~

**`META-INF/services` is resource data, not a Java class.** It must be located in the exact JAR/directory that the loader uses to discover providers.

If `getResource` returns `null`, check in order:

1. Does the name use `/` properly?
2. Has the file been copied into the runtime artifact?
3. Is the URL root/classpath root pointing to the correct directory level?
4. Can the loader see the source, or can only another parent/child/sibling loader see it?
5. Is the named-module resource restricted by package encapsulation?
6. Has the resource lookup policy been overridden by a subclass in a different way?

## 4. SPI and ServiceLoader: Verify Metadata as Well, Not Just Bytecode

A **Service Provider Interface (SPI)** is an interface/abstract class that describes a contract, for example:

~~~java
package api;

public interface Formatter {
    String format();
}
~~~

Provider:

~~~java
package plugin;

public final class PluginFormatter implements api.Formatter {
    public PluginFormatter() {
    }

    @Override
    public String format() {
        return "plugin-provider";
    }
}
~~~

For a **classpath/unnamed-module provider**, the registration file must be:

~~~text
META-INF/services/api.Formatter
~~~

and its content:

~~~text
plugin.PluginFormatter
~~~

The exact two kinds of “names”:

- **Descriptor file name:** the binary name of the service `api.Formatter`.
- **Content of each line:** the fully qualified binary name of the provider `plugin.PluginFormatter`.

Do not use `plugin/PluginFormatter.class` as a provider config line. The config file is UTF-8 encoded; comments use `#`, blank lines are ignored; duplicate provider names are filtered according to the API rules.

**ServiceLoader does not scan all classes to find every `implements Formatter`.** It discovers them via resource descriptors and module metadata.

### Finding the Right Descriptor

~~~java
Enumeration<URL> descriptors = pluginLoader.getResources(
        "META-INF/services/api.Formatter");
~~~

If no descriptor is found, look for the cause in **resource visibility/packaging**, rather than immediately fixing constructor reflection.

### The Provider Must Have the Same Runtime Service Type

With two different class loaders:

~~~text
Host interface:   (api.Formatter, AppLoader)
Plugin interface: (api.Formatter, PluginLoader)
~~~

Even though they have the same name, they are **two different interfaces** if each defines its own. If the provider implements the plugin's copy, `api.Formatter.class.isAssignableFrom(providerClass)` from the host may return `false`.

Correct design: **the shared SPI is defined by the parent loader**, while the plugin loader delegates loading the API to the parent and only defines the implementation itself.

### Provider Constructor in Classpath Mode

In an unnamed module/classpath, the provider class must meet `ServiceLoader` requirements, typically being a **public class with a public no-argument constructor** and assignable to the SPI. If the descriptor points to a class that is not a subtype, lacks a constructor, or the provider cannot be initialized, the ServiceLoader iterator/stream may throw `ServiceConfigurationError`.

Check:

~~~java
Class<?> providerClass = pluginLoader.loadClass(
        "plugin.PluginFormatter");

System.out.println(api.Formatter.class
        .isAssignableFrom(providerClass));
~~~

This is an illustrative snippet that requires `api.Formatter` and `pluginLoader` to already exist. `true` proves assignability under the runtime class identities currently in use; it does not guarantee that constructor/provider invocation will not fail.

## 5. How ServiceLoader Selects a Class Loader

### `ServiceLoader.load(SPI.class, loader)`

~~~java
ServiceLoader<api.Formatter> found =
        ServiceLoader.load(api.Formatter.class, pluginLoader);
~~~

This is **explicit loader mode**. Use it when the exact plugin loader is already known and you want to avoid depending on external thread state.

### `ServiceLoader.load(SPI.class)`

~~~java
ServiceLoader<api.Formatter> found =
        ServiceLoader.load(api.Formatter.class);
~~~

The single-argument overload uses the **thread context class loader (TCCL)** of the current thread. In a plugin runtime:

- The TCCL may be the application loader, which cannot see plugin descriptors.
- The TCCL may be set by the framework to the plugin loader, which can see providers.
- The TCCL may be an old loader after a redeploy if the thread pool does not restore the context.

Do not assume that the TCCL is always equal to the system class loader or the SPI's defining loader.

### Setting a Scoped TCCL and Restoring It

~~~java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<api.Formatter> providers =
            ServiceLoader.load(api.Formatter.class);
    // Iterate over providers here.
} finally {
    thread.setContextClassLoader(before);
}
~~~

This is an illustrative snippet. You must **restore in `finally`** so that the thread pool/next request does not leak the loader context.

### Lazy Discovery and Caching

Calling `ServiceLoader.load(...)` typically creates the ServiceLoader object; provider discovery and instantiation happen when iterating or using a stream. Therefore:

~~~java
ServiceLoader<api.Formatter> services =
        ServiceLoader.load(api.Formatter.class, pluginLoader);

// It is not yet guaranteed that every provider has been instantiated.
for (api.Formatter formatter : services) {
    System.out.println(formatter.format());
}
~~~

Provider configuration errors may appear **during iteration**, not necessarily right at `load`. When testing, you must actually **iterate the iterator/stream**, not just assert that the ServiceLoader instance != null.

`reload()` clears the cache of the ServiceLoader instance; it **does not automatically redefine Java classes, unload classloaders, or rebuild JARs**. ServiceLoader itself is **not thread-safe** if multiple threads share/iterate/reload the same instance without synchronization.

## 6. Runnable Java 17+ Example: Parent Resource Differs from Child Resource, Provider Only in Child

Test harness design:

~~~text
                App loader
             /     |       \
        api.Formatter    host code
             |          config/marker.txt = parent-data
             |
        URLClassLoader child
              |
         plugin.PluginFormatter.class
         config/marker.txt = plugin-data
         META-INF/services/api.Formatter
              |
        ServiceLoader with explicit loader/TCCL
~~~

The results will prove that **classloading success is not enough to infer resource/source/provider semantics**.

### 6.1. Source File Structure

~~~text
project/
  src/
    api/
      api/
        Formatter.java
    plugin/
      plugin/
        PluginFormatter.java
    host/
      ResourceAndProviderCheck.java
  resources/
    host/
      config/
        marker.txt
    plugin/
      config/
        marker.txt
      META-INF/
        services/
          api.Formatter
  out/
    api/
    host/
    plugin/
~~~

### 6.2. File `src/api/api/Formatter.java`

~~~java
package api;

public interface Formatter {
    String format();
}
~~~

### 6.3. File `src/plugin/plugin/PluginFormatter.java`

~~~java
package plugin;

import api.Formatter;

public final class PluginFormatter implements Formatter {
    public PluginFormatter() {
    }

    @Override
    public String format() {
        return "plugin-provider";
    }
}
~~~

### 6.4. File `resources/host/config/marker.txt`

~~~text
parent-data
~~~

### 6.5. File `resources/plugin/config/marker.txt`

~~~text
plugin-data
~~~

The two resources intentionally use the **same relative path** `config/marker.txt` but different contents to test the delegation order.

### 6.6. File `resources/plugin/META-INF/services/api.Formatter`

~~~text
plugin.PluginFormatter
~~~

The descriptor is placed only in the plugin source, **not** in the host output. Thus, a ServiceLoader using the parent will not find this provider, whereas a child with the right URL will find it.

### 6.7. File `src/host/ResourceAndProviderCheck.java`

~~~java
import api.Formatter;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;
import java.util.ServiceLoader;

public final class ResourceAndProviderCheck {
    private static final String DATA = "config/marker.txt";
    private static final String DESCRIPTOR =
            "META-INF/services/api.Formatter";

    static String read(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }

        try (InputStream input = url.openStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    static int count(ServiceLoader<Formatter> loader) {
        int result = 0;
        for (Formatter ignored : loader) {
            result++;
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ResourceAndProviderCheck <plugin-dir>");
        }

        ClassLoader parent = Formatter.class.getClassLoader();
        URL pluginRoot = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        try (URLClassLoader child = new URLClassLoader(
                "plugin", new URL[]{pluginRoot}, parent)) {

            System.out.println("parent resource: "
                    + read(parent.getResource(DATA)));

            System.out.println("child getResource: "
                    + read(child.getResource(DATA)));

            System.out.println("child findResource: "
                    + read(child.findResource(DATA)));

            List<URL> all = Collections.list(
                    child.getResources(DATA));

            System.out.println("resource candidates: "
                    + all.size());

            List<URL> descriptors = Collections.list(
                    child.getResources(DESCRIPTOR));

            System.out.println("provider descriptors: "
                    + descriptors.size());

            System.out.println("parent providers: "
                    + count(ServiceLoader.load(
                            Formatter.class, parent)));

            ServiceLoader<Formatter> services =
                    ServiceLoader.load(Formatter.class, child);

            int providerCount = 0;

            for (Formatter service : services) {
                providerCount++;

                System.out.println("provider value: "
                        + service.format());

                System.out.println("provider defined by child: "
                        + (service.getClass().getClassLoader()
                           == child));
            }

            System.out.println("explicit child providers: "
                    + providerCount);

            Class<?> apiFromChild =
                    child.loadClass("api.Formatter");

            System.out.println("shared SPI identity: "
                    + (apiFromChild == Formatter.class));

            Thread thread = Thread.currentThread();
            ClassLoader previous =
                    thread.getContextClassLoader();

            try {
                thread.setContextClassLoader(child);

                System.out.println("TCCL providers: "
                        + count(ServiceLoader.load(
                                Formatter.class)));
            } finally {
                thread.setContextClassLoader(previous);
            }

            System.out.println("TCCL restored: "
                    + (thread.getContextClassLoader()
                       == previous));
        }
    }
}
~~~

### 6.8. Compiling and Copying Resources

The following commands run from the `project` directory using **Bash on Linux/macOS** or a compatible Bash environment:

~~~bash
mkdir -p out/api out/host/config
mkdir -p out/plugin/config out/plugin/META-INF/services

javac -d out/api src/api/api/Formatter.java

javac -cp out/api -d out/plugin \
    src/plugin/plugin/PluginFormatter.java

javac -cp out/api -d out/host \
    src/host/ResourceAndProviderCheck.java

cp resources/host/config/marker.txt \
    out/host/config/marker.txt

cp resources/plugin/config/marker.txt \
    out/plugin/config/marker.txt

cp resources/plugin/META-INF/services/api.Formatter \
    out/plugin/META-INF/services/api.Formatter

java -cp "out/api:out/host" \
    ResourceAndProviderCheck out/plugin
~~~

**Important conditions:**

- `out/api` and `out/host` belong to the **application classpath**.
- `out/plugin` is **not** added to `-cp`; it only appears in the child's URL search path.
- Both parent and child contain `config/marker.txt`, but only the child contains the descriptor and the provider implementation.
- The plugin compiles against `out/api`, but the plugin artifact **does not copy `api/Formatter.class`**, because the SPI must be defined once by the parent.

On Windows PowerShell, use `New-Item -ItemType Directory -Force` to create directories and `Copy-Item` to copy resources. Replace the classpath separator `:` with `;`:

~~~powershell
java -cp "out/api;out/host" ResourceAndProviderCheck out/plugin
~~~

### 6.9. Expected Stdout with the Exact Structure Above

~~~text
parent resource: parent-data
child getResource: parent-data
child findResource: plugin-data
resource candidates: 2
provider descriptors: 1
parent providers: 0
provider value: plugin-provider
provider defined by child: true
explicit child providers: 1
shared SPI identity: true
TCCL providers: 1
TCCL restored: true
~~~

**Reading and understanding the results:**

1. **`parent resource: parent-data`:** the parent loader sees the resource at `out/host/config/marker.txt`.
2. **`child getResource: parent-data`:** URLClassLoader uses parent-first resource lookup by default; the parent's copy is selected.
3. **`child findResource: plugin-data`:** `findResource` skips the parent to search within the child's URL search path.
4. **`resource candidates: 2`:** `getResources` shows both candidates; in the test configuration, there are exactly two files at the same path.
5. **`provider descriptors: 1`:** only the plugin has `META-INF/services/api.Formatter`; this proves the descriptor is within the child's search scope.
6. **`parent providers: 0`:** the parent does not see the child plugin descriptor, so it does not know about the provider.
7. **`provider value: plugin-provider`:** ServiceLoader not only sees the descriptor but also loads and instantiates the provider.
8. **`provider defined by child: true`:** the implementation class belongs to the child; it is not shadowed by the parent.
9. **`explicit child providers: 1`:** only one provider is registered in the test fixture.
10. **`shared SPI identity: true`:** the child delegates `api.Formatter` to the parent; the host and provider use the same runtime interface.
11. **`TCCL providers: 1`:** the `ServiceLoader.load(Formatter.class)` overload uses the temporary TCCL, which is the child.
12. **`TCCL restored: true`:** finally, the thread is returned to the old context loader, not retaining the child plugin loader in the thread pool.

**Do not hard-code these results for every application:** if the parent classpath accidentally contains a provider for the same SPI, if additional JARs provide descriptors, or if the URLClassLoader has a custom policy, the number of candidates/providers and their order may differ. This is the expected stdout of the **standalone fixture with files configured exactly as instructed**.

### 6.10. Packaging the Plugin as a JAR to Verify Packaging

Replace the child directory with a JAR:

~~~bash
mkdir -p dist

jar --create --file dist/formatter-plugin.jar -C out/plugin .

jar --list --file dist/formatter-plugin.jar

java -cp "out/api:out/host" \
    ResourceAndProviderCheck dist/formatter-plugin.jar
~~~

The JAR must contain at least:

~~~text
plugin/PluginFormatter.class
config/marker.txt
META-INF/services/api.Formatter
~~~

The host converts the argument into a `URL` using `Path.toUri().toURL()`, so either a **directory or a JAR** can be used as the URL source. With an equivalent fixture, the assertions/output remain the same.

## 7. Why Must Provider Descriptors and Provider Classes Be Checked Separately?

`ServiceLoader` operates through multiple stages:

~~~text
ServiceLoader.load(SPI, loader)
                  |
                  v
       ServiceLoader instance
                  |
                  v
     Iterator / Stream is iterated
                  |
                  v
 Find META-INF/services/<SPI binary name>
                  |
                  v
 Read provider implementation name
                  |
                  v
 class loader finds implementation class
                  |
                  v
 Check assignability to runtime SPI
                  |
                  v
 Instantiate provider
                  |
                  v
 Return service object
~~~

A test that only asserts `ServiceLoader.load(...) != null` is **virtually meaningless** for proving that a provider was found. An empty ServiceLoader is still a non-`null` object.

Separate assertions are needed:

- The descriptor URL exists within the right loader scope.
- The descriptor is UTF-8 encoded and has valid provider binary names.
- The provider class can be loaded and has the right defining loader.
- The provider is a subtype of **the consumer's exact SPI `Class<?>`**.
- The constructor/factory matches the mode and executes successfully.
- Iterating actually returns the provider with expected behavior.

If a step fails, do not lump every cause together as “ClassLoader does not work”.

## 8. Negative Tests Worth Having

### 8.1. Missing Descriptor File

Keep `plugin/PluginFormatter.class` but remove:

~~~text
META-INF/services/api.Formatter
~~~

Result:

- `child.loadClass("plugin.PluginFormatter")` may still succeed.
- `ServiceLoader.load(Formatter.class, child)` does not discover this provider due to missing registration.
- Testing `provider descriptors == 0` helps isolate packaging issues.

This is a **variant scenario**, not the output of the standard fixture.

### 8.2. Misnamed Descriptor

Wrong:

~~~text
META-INF/services/Formatter
~~~

Correct:

~~~text
META-INF/services/api.Formatter
~~~

The file name must be the **full binary name of the SPI**. Having the provider's package folder right does not help if the descriptor name is wrong.

### 8.3. Descriptor Containing the Wrong Provider Name

Wrong:

~~~text
plugin/PluginFormatter.class
~~~

Correct:

~~~text
plugin.PluginFormatter
~~~

If ServiceLoader reads the descriptor but cannot find the provider name, it may throw `ServiceConfigurationError` **when iterating**, rather than returning an empty list. Catch/log the error at the plugin boundary instead of swallowing it.

### 8.4. Provider Not Assignable to the SPI

If the plugin is loaded under a child-first policy and defines another copy of `api.Formatter` itself, the provider may implement **a different runtime interface**:

~~~text
(api.Formatter, ParentLoader)
(api.Formatter, ChildLoader)
~~~

Having the same source/binary name is not enough. `Formatter.class.isAssignableFrom(providerClass)` from the host will be `false`; ServiceLoader may throw `ServiceConfigurationError` when the provider type does not match.

**Fix:** the shared SPI is defined by a common loader; the child delegates to it. Do not simply copy the same interface bytes into every plugin JAR.

### 8.5. Faulty Provider Constructor

In unnamed-module/classpath mode, a provider typically needs a **public no-arg constructor** and an appropriate public class. If it is missing or the constructor throws an exception, `ServiceConfigurationError` may be raised when ServiceLoader instantiates the provider.

Tests must actually iterate through the providers, rather than stopping at the descriptor URL. For named modules, explicit module providers also have a provider factory method with its own rules; **do not mistakenly apply JPMS provider factory rules to an unnamed-module descriptor**.

### 8.6. Resource Shadowed by Parent

Both parent and child have:

~~~text
config/marker.txt
~~~

`getResource` returns the parent's copy by default. Tests must distinguish:

- **Resource visibility:** can the resource be found?
- **Resource ownership/source:** which copy is selected?
- **Resource content:** do the bytes match the right version/environment?

Do not just assert `getResource(...) != null`. If the application must use the plugin's private config, check the resource URL or use an intentional namespace/lookup API.

### 8.7. Wrong TCCL in a Thread Pool

A test running only on the main thread may pass, whereas production uses a thread pool with a different TCCL. If a library calls `ServiceLoader.load(SPI.class)`, the result may vary by thread.

The test needs to create a task with a preset TCCL, verify the provider count, and then **restore it in finally**, preventing plugin A's context from leaking into a request for plugin B.

### 8.8. Duplicate Descriptors and Provider Ordering

When multiple JARs provide the same SPI, `getResources("META-INF/services/SPI")` may return multiple URLs. ServiceLoader may aggregate provider names and ignore duplicate declarations according to its rules.

Do not assume the “first provider” is always the preferred provider in business logic. If you need to select an implementation, collect the list of providers and apply an **explicit policy** (ID/priority/compatible version/capabilities) instead of relying on uncontrolled classpath order.

## 9. Building an Automated Assertion Suite for CI

In a test suite (JUnit or a self-checking `main` like the demo), assertions should be designed in layers:

| Layer | Assertion | What It Protects |
|---|---|---|
| Artifact | JAR contains class + resource + descriptor | Avoids missing files from the build |
| Binary name | `loadClass("plugin.PluginFormatter")` succeeds | Correct package/classpath root |
| Defining loader | `providerClass.getClassLoader() == pluginLoader` | Provider belongs to the plugin |
| Shared SPI | `pluginLoader.loadClass("api.Formatter") == Formatter.class` | No duplicate API |
| Parent resource | Content is `parent-data` | Correct parent view |
| Child own resource | Content is `plugin-data` | Plugin file is packaged |
| Delegated resource | `getResource` returns expected parent content | Correct default order |
| All resources | Exactly two URLs in the fixture | Detects collisions |
| Provider descriptor | Correct descriptor URL count | Registration is visible |
| ServiceLoader parent | No plugin provider | Parent does not look down into child |
| ServiceLoader child | Exactly one provider | Discovery + instantiation |
| TCCL | Single-arg overload sees provider when set to child | Correct thread context |
| Lifecycle | TCCL is restored, URL loader is closed after use | No leftover loaders retained |

### Robust Checks Instead of Hard-Coding Beyond the Fixture

For a test fixture with fixed data, `== 2` or `== 1` is a good check. However, for real applications, tests should use **known artifact sources**, restrict roots, and have clear runtime dependencies so they are not affected by other plugins.

If there is a custom resource lookup policy, the expected order may **differ from the default URLClassLoader**; in that case, the test must describe the desired policy and then verify against the contract, rather than blindly applying “parent always wins” to every loader subclass.

## 10. Distinguishing Classpath Providers from Named-Module Providers

The full example above runs in **classpath / unnamed-module mode**. With JPMS named modules, provider registration can reside in `module-info.java`:

~~~java
module formatter.consumer {
    requires formatter.api;
    uses api.Formatter;
}
~~~

Provider module:

~~~java
module formatter.provider {
    requires formatter.api;
    provides api.Formatter with plugin.PluginFormatter;
}
~~~

These are **two illustrative module-info.java files**, not replacement files for the classpath demo. The module graph/layer must be resolved appropriately.

### Differences to Verify with JPMS

- The consumer named module needs `uses api.Formatter;` when using ServiceLoader under the module model.
- The provider module declares `provides api.Formatter with plugin.PluginFormatter;`.
- The provider module must be **resolved** in the module layer where ServiceLoader searches.
- `ServiceLoader.load(ModuleLayer layer, Formatter.class)` has lookup rules in the layer/parent layers that differ from `load(SPI, ClassLoader)`.
- Do not treat `META-INF/services` and `provides` as always equivalent in every module configuration.
- A provider in an explicit named module can use a **public static provider() factory method** meeting the conditions of the JDK specification; that is not a general constructor rule for all classpath providers.

### Module Resource Encapsulation

For resources in a **named module package**, `ClassLoader.getResource` may only see a resource when the package is opened as required by the API (except for certain special paths such as `.class` per the contract). Therefore:

~~~java
URL url = loader.getResource("p/secret.txt");
~~~

returning `null` **does not necessarily** mean the file `p/secret.txt` does not exist in the module artifact.

When testing modular resources, check:

1. Is the module named and resolved?
2. Which package does the resource reside in?
3. How are `opens`/`exports`/readability configured?
4. Is the API being used `Module.getResourceAsStream`, `Class.getResourceAsStream`, or `ClassLoader.getResource`?
5. From which caller module and under which rules is the lookup performed?

Do not use `--add-opens` as a “universal fix” for every wrong resource path, and do not confuse a module access error with a duplicate classloader SPI identity.

## 11. ServiceLoader, TCCL, and Lifecycle During Hot Redeploy

In a plugin system, there are often consecutive generations:

~~~text
Generation 1:
  URLClassLoader-A -> provider-A
          |
          +-- ServiceLoader cache / TCCL / callbacks

Generation 2:
  URLClassLoader-B -> provider-B
          |
          +-- new provider
~~~

If the host still holds a `ServiceLoader` from generation A, provider instances, or a TCCL pointing to loader A, the old classloader may not be GC'd/unloaded immediately even after `URLClassLoader.close()` has been called.

**Technical notes:**

- `ServiceLoader.reload()` resets the provider cache of the ServiceLoader instance; it **does not unload/redefine Java classes**.
- `URLClassLoader.close()` closes the loader's JAR/file handles; it **does not force class unloading**.
- `getResourceAsStream` streams must be closed separately.
- Plugin tasks/threads, scheduled jobs, callbacks, ThreadLocals, and cached Class/Method objects can keep the loader alive.
- The thread context class loader must be restored after calling the framework/ServiceLoader within the plugin scope.
- When closing a loader, avoid having another thread concurrently loading classes; the API does not guarantee deterministic results for concurrent close/load.

A good lifecycle:

~~~text
ACTIVE
   |
   v
DRAINING (stop new requests; wait for jobs to finish)
   |
   +-- close resource streams
   +-- stop tasks/threads
   +-- remove provider/listener callbacks
   +-- restore TCCL
   +-- drop ServiceLoader/provider caches
   +-- URLClassLoader.close()
   |
   v
RETIRED (drop strong references)
   |
   v
GC may unload when eligible, not guaranteed immediately
~~~

If plugin resources or service provider data are updated to a new version, **creating a new loader generation** may be the right approach; do not assume modifying a JAR file on disk makes the old loader automatically see every new version.

## 12. Specific Diagnostics When Tests Fail

### `getResource` Returns Null

Ask:

- Is the resource path properly root-relative?
- Is the file present in the class output/JAR?
- Is the child's URL valid and accessible?
- Does the resource's package belong to a named module that requires `opens`?
- Does the subclass override `findResource` or `getResource` incorrectly?

### `getResource` Has a URL but Reads the Wrong Config

- Print the returned URL, not just the data content.
- Compare `getResource` with `findResource`.
- Use `getResources` to see parent/child candidates.
- Place private resources under a non-conflicting namespace or explicitly select the source.
- Check the cache and version/generation.

### Descriptor Exists but ServiceLoader Is Empty

- Are you using the **right SPI class**?
- Can the loader passed to ServiceLoader see the descriptor?
- Does the descriptor have the full name `META-INF/services/<binary-name>`?
- Are you running with named modules where `uses`/`provides` must be used?
- Have you touched the iterator/stream to trigger lazy discovery?

### ServiceLoader Throws `ServiceConfigurationError`

- Does the descriptor contain a valid provider binary name?
- Can the provider class be found by the loader?
- Is the provider a subtype of the **right runtime SPI**?
- Does the constructor/provider method have the right mode/visibility?
- Is there an underlying `NoClassDefFoundError`/`ExceptionInInitializerError`/dependency error hidden inside?
- Is there a duplicate API class loaded separately by child-first?

**Do not catch `Throwable` broadly and treat errors as “no provider”.** It hides serious linkage, native, memory, and initialization failures. Preserve the stack trace/cause chain and record the artifact/loader identity.

### Error Occurs Only in One Thread

- Log `Thread.currentThread().getContextClassLoader()`.
- Log the defining loader of the SPI and the provider.
- Try `ServiceLoader.load(SPI.class, explicitPluginLoader)`.
- Check TCCL restoration in thread pools.
- Ensure no old generation remains in callbacks/caches.

## 13. Observability Tools for Confirmation

**Log resource URLs:**

~~~java
Enumeration<URL> urls =
        pluginLoader.getResources("config/marker.txt");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

This is an illustrative snippet; the order/absolute paths vary by machine, so it is unsuitable to hard-code the full URL string in cross-platform tests.

**Log defining loaders:**

~~~java
Class<?> impl =
        pluginLoader.loadClass("plugin.PluginFormatter");

System.out.println(impl.getName());
System.out.println(impl.getClassLoader());
System.out.println(impl.getModule());
~~~

**Log SPI identity:**

~~~java
Class<?> viaChild = pluginLoader.loadClass("api.Formatter");

System.out.println(viaChild == api.Formatter.class);
~~~

**Inspect the JAR:**

~~~bash
jar --list --file dist/formatter-plugin.jar
~~~

**JVM classloading logs (HotSpot JDK 17):**

~~~bash
java -Xlog:class+load=info \
    -cp "out/api:out/host" ResourceAndProviderCheck out/plugin
~~~

Diagnostic commands can print class names, sources, and runtime details, but they **do not replace verification of provider descriptors/resources**; classloading logs do not list the full contents of every text resource or the cause of every ServiceLoader failure.

## 14. Common Misconceptions

1. **“If `loadClass` succeeds, `getResource` is guaranteed to succeed.”** False: resource lookup takes a different path.
2. **“A resource present in the `src/resources` directory means it is in the JAR.”** False: it must be copied/packaged.
3. **“`ClassLoader.getResource("x.txt")` searches from the package of the calling class.”** False: it is root-relative.
4. **“`Class.getResource("x.txt")` always searches from the root.”** False: without a leading slash, it is package-relative.
5. **“Child-first class lookup automatically results in child-first resource lookup.”** False: they are overridden separately.
6. **“`getResource` shows all candidate URLs.”** False: use `getResources`.
7. **“URLClassLoader's `findResource` also queries the parent.”** False: it searches only within the loader's own URLs.
8. **“Simply having the provider class implement the SPI allows ServiceLoader to scan and find it automatically.”** False: it must be registered via a descriptor/JPMS provides.
9. **“`META-INF/services` is named after the provider class.”** False: it is named after the **SPI binary name**.
10. **“Provider config lists the file path `plugin/Impl.class`.”** False: the line contains the binary name `plugin.Impl`.
11. **“`ServiceLoader.load` already proves the provider can be instantiated.”** False: lookup/instantiation is lazy during iteration.
12. **“ServiceLoader.load(SPI.class)` always uses the system class loader.”** False: it uses the TCCL.
13. **“Set the TCCL once on a thread pool and don't bother restoring it.”** False: this causes cross-plugin visibility and lifecycle leaks.
14. **“Two `api.Formatter` interfaces from the same source in two loaders are the same.”** False: their runtime identities differ.
15. **“Having the provider descriptor in the JAR guarantees the provider works.”** False: the constructor/type/linkage/dependencies may fail.
16. **“`ServiceConfigurationError` is a normal signal that there are zero providers.”** False: it is usually a provider configuration/loading problem.
17. **“Reading a URL from the child and getting the parent's config means the JVM read it wrong.”** No: parent-first resource lookup is the default.
18. **“Named-module resource rules are completely identical to classpath resources.”** False: JPMS encapsulation may restrict access.
19. **“`ServiceLoader.reload()` unloads classes/plugins immediately.”** False: it only resets the cache.
20. **“`URLClassLoader.close()` immediately GCs the loader.”** False: references/lifecycle/GC still apply.

## 15. Verification Checklist When Finalizing a Plugin

- [ ] The SPI is defined in a shared API belonging to the appropriate parent loader.
- [ ] The plugin artifact does not redefine the SPI itself when an uncontrolled child-first policy is in place.
- [ ] The provider class is packaged at the right package path.
- [ ] `META-INF/services/<SPI binary name>` exists with the right name and UTF-8 encoding.
- [ ] The provider config lists the right binary implementation names.
- [ ] The provider has a public no-arg constructor matching classpath mode or a JPMS provider method matching its mode.
- [ ] Tests actually iterate providers and assert behavior, rather than just asserting ServiceLoader != null.
- [ ] Test the provider's defining loader, SPI assignability, and runtime type identity.
- [ ] Test that parent provider visibility differs from the child when required by the architecture.
- [ ] Test the parent resource and the child's own resource under the same path.
- [ ] Test `getResource`, `findResource`, and `getResources` separately.
- [ ] Assert the actual content/hash of the resource, not just URL != null.
- [ ] Close streams after reading.
- [ ] Test the TCCL-selected provider count and restoration.
- [ ] Test missing descriptors, malformed provider names, and constructor/linkage failures.
- [ ] Test duplicate provider registrations/candidate resource order when multiple JARs are present.
- [ ] Test the final packaged JAR, not just the source folder.
- [ ] If using named modules, check `uses`/`provides`, module resolution/layer, and `opens` for resources when needed.
- [ ] Log source URLs, loader identities, and provider errors.
- [ ] Ensure clean-up/redeploy lifecycle does not retain old loaders via TCCL or caches.
- [ ] Do not use unreliable file-system resource/path tests as a substitute for actual runtime lookup.

## 16. Self-Check Questions

**Question 1.** Both parent and child contain `config/marker.txt`. Why might `child.getResource("config/marker.txt")` return the parent's copy?

**Answer:** Because default ClassLoader resource lookup searches the parent first. `URLClassLoader.findResource` can be used to look up the resource within the child's own URLs.

**Question 2.** How do `getResource` and `getResources` differ?

**Answer:** `getResource` returns the first URL or null; `getResources` returns an Enumeration of all URLs visible according to the loader mechanism.

**Question 3.** Why does `type.getResource("settings.txt")` differ from `loader.getResource("settings.txt")`?

**Answer:** The Class API prepends the package of `type` when the name does not start with `/`; the ClassLoader API looks up from the root of the search path.

**Question 4.** The provider class is in the JAR and implements the SPI, yet ServiceLoader does not find it. What should you check first?

**Answer:** `META-INF/services/<SPI binary name>` or `provides` in JPMS, the full provider name, whether the loader/TCCL can see the descriptor, and whether the ServiceLoader is actually iterated.

**Question 5.** The provider is defined by the child and the SPI is defined by the parent. Can the host cast the provider to the SPI?

**Answer:** Yes, if the provider implements **the exact runtime SPI type** defined by the parent and method/access rules are satisfied. The provider implementation class does not need to belong to the parent.

**Question 6.** Why can a valid provider descriptor file still cause a `ServiceConfigurationError`?

**Answer:** The provider class is not found, is not a subtype of the SPI, lacks an appropriate constructor, encounters an initialization error, has dependency/linkage issues, or has config syntax errors.

**Question 7.** You need to test `ServiceLoader.load(SPI.class)` from another thread pool. What factor is important?

**Answer:** The thread's TCCL; set/restore it within a controlled scope and avoid retaining the old loader after the task.

**Question 8.** If `getResource` returns null for a named-module resource, is it certain that the file was deleted?

**Answer:** No. The resource may be restricted by JPMS encapsulation/`opens`, or the path/loader may be wrong.

**Question 9.** Does `ServiceLoader.reload()` replace the bytecode of an already-loaded provider?

**Answer:** No. It resets the provider cache of the ServiceLoader instance; it does not redefine classes or unload the defining loader.

**Question 10.** Why must CI run against the final packaged JAR rather than testing only `src/main/resources`?

**Answer:** Resource configs/descriptors might be forgotten during copying or packaged incorrectly during the build; runtime lookup uses the final artifact, not source folders.

## 17. Verification Decision Model

~~~text
             Plugin provider does not work
                         |
             Can the Java class be loaded?
                  /              \
                 No              Yes
                 |                 |
             check URL          check resource
             root/name         + descriptor
                                   |
                     getResource/findResource/getResources
                                   |
                      right config source?
                             /       \
                            No       Yes
                            |          |
                      resource policy  ServiceLoader iterate
                                        |
                              provider found?
                                  /        \
                                 No        Yes
                                 |          |
                          descriptor/TCCL  check type identity,
                          module graph     constructor/behavior
                                            |
                                      stop/redeploy:
                                      close streams,
                                      restore TCCL,
                                      clear cached refs
~~~

**Conclusion:** Verifying resources and service providers means verifying the **entire data path**, from the artifact, loader visibility, URL source, and provider descriptor to the runtime SPI type and lifecycle. For a plugin classloader, **`loadClass`, `getResource`/`findResource`/`getResources`, and `ServiceLoader`** must be tested separately; these APIs do not automatically share the same lookup policy. A test harness with a parent/child setup containing a same-path resource and a descriptor only in the child will immediately reveal hidden bugs that a simple class-loading test misses.

### Official Documentation

- [Java SE 17 — ClassLoader: getResource/getResources/getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findResource and close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String))
- [Java SE 17 — ServiceLoader: classpath providers/TCCL/JPMS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 — Module.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [JLS 17 7.7 — uses/provides module declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
