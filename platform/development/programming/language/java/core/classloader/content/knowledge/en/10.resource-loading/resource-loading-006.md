# findResource, findResources, and Extension Points for Custom ClassLoaders

## 1. When a Class Loads but a Resource Is Still “Not Found”

Java applications typically package resources alongside bytecode, such as `.properties` files, HTML templates, JSON, images, public certificates, `META-INF/services/...` metadata, or plugin configurations. Being able to load `com.example.Plugin` **does not guarantee** finding `config/settings.properties`: the **class** lookup mechanism and the **resource** lookup mechanism have separate APIs, search paths, and access permissions.

Suppose the following code runs:

```java
ClassLoader loader = Plugin.class.getClassLoader();
java.net.URL url = loader.getResource("plugin/settings.properties");
```

This is an illustrative snippet, assuming `Plugin` has already been defined. When `url == null`, before concluding “forgot to package the file”, you need to check the **resource name**, the **loader being used**, **delegation**, whether the custom loader provides `findResource`/`findResources`, and **named module** boundaries.

This lesson focuses on **two extension points**:

- `protected URL findResource(String name)`: finds **one URL** to the resource in the source managed by the custom class loader.
- `protected Enumeration<URL> findResources(String name) throws IOException`: finds **all matching URLs** in the loader's local source, typically used to collect multiple configuration files or provider descriptors.

They combine with the **public** methods `getResource`, `getResources`, `resources`, and `getResourceAsStream`. Understanding this difference clearly is a prerequisite for designing a consistent plugin loader.

## 2. API Map: What Users Call, What Loaders Override?

| API | Scope/Function | Result When Not Found | Overridable in a Custom Loader? |
| --- | --- | --- | --- |
| `ClassLoader.getResource(name)` | Looks up a single resource using the default delegation algorithm: parent first, local second | `null` | Yes, though usually **unnecessary** if you only want to change the local source |
| `ClassLoader.getResources(name)` | Collects resources from the parent, then from local `findResources` | Empty `Enumeration` | Yes; must ensure ordering is consistent with `getResource` |
| `ClassLoader.resources(name)` (Java 9+) | `Stream<URL>` from the multi-resource mechanism; typically lazy | Empty stream | Yes, but unnecessary if `getResources` is already correct |
| `ClassLoader.getResourceAsStream(name)` | Gets an `InputStream` to read the first resource | `null` | Yes; usually unnecessary if `getResource` is correct |
| `protected findResource(name)` | Local extension point to find **one URL** | `null` | **Yes — where custom loaders typically implement it** |
| `protected findResources(name)` | Local extension point to find **multiple URLs** | Empty enumeration | **Yes — must be implemented if multiple local resources are needed** |
| `ClassLoader.getSystemResource(name)` | Finds a resource through the system class loader | `null` | Static method; does not replace plugin resource lookup |
| `Class.getResource(name)` | Looks up in the context of the class's own package (different naming rules below) | `null` | This is a `Class` API, not a `ClassLoader` extension point |
| `Module.getResourceAsStream(name)` | Finds a resource in a specific module, with module encapsulation checks | `null` | Does not replace the responsibility of a loader that supports modules |

**Defaults in JDK 17:**

- `ClassLoader.findResource(String)` returns `null`.
- `ClassLoader.findResources(String)` returns an enumeration **with no elements**.
- `ClassLoader.getResource(String)` searches the parent first; only when the parent does not find it does it call `findResource(String)`.
- `ClassLoader.getResources(String)` collects the list from the parent first and then appends the URLs provided by local `findResources(String)`.
- `ClassLoader.resources(String)` calls `getResources` by default and converts the enumeration into a stream; an `IOException` occurring while processing the stream may be wrapped in an `UncheckedIOException`.

**An easily overlooked consequence:** overriding **only** `findResource` can allow `getResource` to find a local file, while `getResources` still **cannot see** that file if `findResources` in the subclass has not been overridden. The two extension points are independent; you should not assume `ClassLoader`'s `findResources` will call `findResource` for you.

## 3. Delegation Flow: getResource and getResources Are Not Equivalent

Suppose both the parent and the child contain the file `demo/config.properties`:

```text
Root / ParentLoader
    └── demo/config.properties   (version: parent)

Plugin / ChildLoader
    └── demo/config.properties   (version: child)
```

When keeping the default public APIs unchanged:

```text
child.getResource("demo/config.properties")
    ├── parent.getResource(...)          -> found in parent
    └── child.findResource(...)          -> does NOT need to be called
Result: parent's URL
```

Conversely:

```text
child.getResources("demo/config.properties")
    ├── parent.getResources(...)         -> parent's URL
    └── child.findResources(...)         -> child's URL
Result: Enumeration [parent URL, child URL]
```

This serves two purposes:

1. **`getResource` selects a single source** consistent with the parent-first strategy.
2. **`getResources` enables discovering multiple sources** with the same name, such as multiple JARs where each JAR provides a `META-INF/services/com.example.spi.Plugin` file.

Parent-before-local ordering is the contract of the default implementation. A framework can **override** `getResource`/`getResources` to apply child-first loading by namespace, but when doing so it must maintain **consistency**: the first resource returned by `getResources(name)` should be the same resource that `getResource(name)` selects for the same name under the same access conditions.

**Note:** `getResources` is an enumeration, not a merged and deduplicated `List`; the same content may appear from multiple locations. You must define how to handle multiple duplicate configurations yourself, rather than assuming “the JVM only returns the latest version”.

## 4. Resource Names: /, Packages, and Classpath Root

Java identifies `ClassLoader` resource names using **`/`-separated paths**, not binary class names:

| Resource to Find | Name Passed to `ClassLoader.getResource` |
| --- | --- |
| Config at the classpath root `application.properties` | `"application.properties"` |
| Config in package `com.acme` | `"com/acme/settings.properties"` |
| Service descriptor | `"META-INF/services/com.acme.spi.Plugin"` |
| Class file in a classpath source | `"com/acme/Plugin.class"` (though looking up a class file is not equivalent to using the class-loading API) |

With **`ClassLoader.getResource`**, do not add a leading `/` to the name: use `"com/acme/config.properties"`. With **`Class.getResource`**, the rules differ:

- `SomeClass.class.getResource("config.properties")`: looks up relative **to the package of SomeClass**.
- `SomeClass.class.getResource("/com/acme/config.properties")`: absolute name from the root; the leading `/` is stripped before passing it to the lookup.
- `SomeClass.class.getResourceAsStream(...)` follows the corresponding naming rules.

Illustrative example in class `com.acme.SomeClass`:

```java
java.net.URL viaClassRelative =
        SomeClass.class.getResource("config.properties");

java.net.URL viaClassAbsolute =
        SomeClass.class.getResource("/com/acme/config.properties");

java.net.URL viaLoader =
        SomeClass.class.getClassLoader()
                .getResource("com/acme/config.properties");
```

This is an illustrative snippet, assuming the class and resource file actually exist. For an **unnamed module**, these three approaches typically resolve to the same resource in the same package given a matching classpath configuration; for a **named module**, lookup paths and encapsulation rules may differ; see the JPMS section.

**Do not pass** `"com.acme.config.properties"` if the actual file name is `com/acme/config.properties`. Do not use `File.separator` instead of `/` to name resources inside a JAR.

### Inside a JAR, a Resource Is Not Necessarily a Regular File on Disk

If a resource resides in a JAR, its URL may look like `jar:file:/.../plugin.jar!/demo/config.properties`. If it resides in a module image or is supplied by a custom loader, it may not be `file:` or `jar:file:`.

Therefore, use `url.openStream()` or `getResourceAsStream()` to read it, and close the stream with try-with-resources. Do not force `new File(url.toURI())` for every type of URL, because `jar:` paths are not regular file paths and a URL may use a special protocol.

## 5. Complete Java 17 Program: Two Loaders, Two Resource Sources

This example actually builds **two loaders in a parent-child relationship**, where both contain a resource with the same name. We override **both** `findResource` and `findResources` so single-resource and multi-resource results remain consistent. No Maven, Gradle, external JARs, or network connection are required.

Create the file `ResourceLookupDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public class ResourceLookupDemo {

    private static final String CONFIG =
            "lesson_resource_demo_2026/config.txt";

    static final class DirectoryResources extends ClassLoader {
        private final Path root;

        DirectoryResources(Path directory, ClassLoader parent) {
            super(parent);
            this.root = directory.toAbsolutePath().normalize();
        }

        private Path localPath(String name) {
            // This practice exercise only uses controlled resource names.
            if (name.startsWith("/")
                    || name.indexOf('\\') >= 0
                    || name.contains("..")) {
                return null;
            }
            Path candidate = root.resolve(name).normalize();
            return candidate.startsWith(root) ? candidate : null;
        }

        @Override
        protected URL findResource(String name) {
            Path file = localPath(name);
            if (file == null || !Files.isRegularFile(file)) {
                return null;
            }
            try {
                return file.toUri().toURL();
            } catch (MalformedURLException e) {
                return null;
            }
        }

        @Override
        protected Enumeration<URL> findResources(String name)
                throws IOException {
            URL local = findResource(name);
            if (local == null) {
                return Collections.emptyEnumeration();
            }
            return Collections.enumeration(List.of(local));
        }
    }

    private static String read(URL url) throws IOException {
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("resource-lookup-");
        Path parentRoot = temp.resolve("parent");
        Path childRoot = temp.resolve("child");
        Path parentFile = parentRoot.resolve(CONFIG);
        Path childFile = childRoot.resolve(CONFIG);

        try {
            Files.createDirectories(parentFile.getParent());
            Files.createDirectories(childFile.getParent());
            Files.writeString(parentFile, "PARENT\n");
            Files.writeString(childFile, "CHILD\n");

            DirectoryResources parent = new DirectoryResources(
                    parentRoot,
                    ClassLoader.getPlatformClassLoader());
            DirectoryResources child = new DirectoryResources(
                    childRoot, parent);

            URL first = child.getResource(CONFIG);
            System.out.println("getResource=" + read(first));

            Enumeration<URL> urls = child.getResources(CONFIG);
            List<String> values = new ArrayList<>();
            while (urls.hasMoreElements()) {
                values.add(read(urls.nextElement()));
            }
            System.out.println("getResources=" + values);

            System.out.println("missing="
                    + (child.getResource(
                            "lesson_resource_demo_2026/missing.txt")
                            == null));
            System.out.println("leadingSlash="
                    + (child.getResource("/" + CONFIG) == null));
        } finally {
            Files.deleteIfExists(parentFile);
            Files.deleteIfExists(childFile);
            Files.deleteIfExists(parentFile.getParent());
            Files.deleteIfExists(childFile.getParent());
            Files.deleteIfExists(parentRoot);
            Files.deleteIfExists(childRoot);
            Files.deleteIfExists(temp);
        }
    }
}
```

Compile and run using JDK 17 or later:

```bash
javac ResourceLookupDemo.java
java ResourceLookupDemo
```

**Exact stdout under standard execution conditions**, when the platform loader does not contain a resource with the same name used in the experiment:

```text
getResource=PARENT
getResources=[PARENT, CHILD]
missing=true
leadingSlash=true
```

**How to read the output:**

1. `child.getResource(CONFIG)` asks the parent first. The parent has `CONFIG`, so it returns the parent's URL: the line `getResource=PARENT`.
2. `child.getResources(CONFIG)` collects the enumeration from the parent and from the child's `findResources`; each loader provides one URL, so the displayed order is `[PARENT, CHILD]`.
3. The name `missing.txt` does not exist in platform/parent/child in this experiment, so `getResource` returns `null`.
4. A resource name starting with `/` does not match the naming convention expected by `ClassLoader.getResource`; `DirectoryResources.localPath` rejects this name, so the result is `true`.
5. All resources are read using `URL.openStream` and closed via try-with-resources. The temporary directory and both files are cleaned up in `finally` after no open streams remain.

### Why Does the Example Use a Helper Method localPath?

Resources can be named from configuration, user-supplied paths, or external data. When converting a resource name into a `Path`, you must prevent names like `../secret.txt` from escaping the root. The example applies a **lexical** check: rejecting a leading `/`, `\\`, and `..`, then normalizing and comparing against the root.

**Security limitation to understand properly:** lexical checks are not sufficient against a subdirectory inside the root being a **symbolic link** pointing outside. In a real system that handles untrusted resource names, you must check the real path, access permissions, symlink policy, file size limits, and allowed sources before reading. This instructional example only uses self-created files and fixed names.

### What If Only findResource Is Overridden in DirectoryResources?

`child.getResource(CONFIG)` can still find the parent, and a resource **only in the child** can be found by `findResource`. However, `child.getResources(CONFIG)` **does not automatically call findResource to collect local URLs**; without overriding `findResources`, the default implementation returns an empty enumeration for the local portion. Therefore, any system that needs to enumerate multiple resources must have a corresponding `findResources` implementation.

## 6. One or Multiple Resources: Why Shouldn't You Just “Grab the First URL”?

There are different use cases:

| Need | Recommended Usage | Handling Rule |
| --- | --- | --- |
| Read only a single configuration with parent-first priority | `getResource` / `getResourceAsStream` | Clearly determine which source has priority |
| List descriptors with the same name across multiple JARs | `getResources` | Iterate through all URLs, parse each source, and handle errors individually |
| Use the stream API to filter URLs | `resources` | May encounter `UncheckedIOException` when evaluating the stream |
| Want to log every place providing configuration | `getResources` | Do not assume the returned URLs are unique |
| Search only the custom loader's local source | `findResource` / `findResources` in a subclass | These are protected extension points, not public APIs to call throughout the application |

Example of a valid snippet once you have a `loader` object:

```java
String name = "META-INF/services/com.acme.spi.Plugin";
Enumeration<URL> entries = loader.getResources(name);
while (entries.hasMoreElements()) {
    URL descriptor = entries.nextElement();
    try (InputStream in = descriptor.openStream()) {
        // Read using the proper charset/format for the descriptor being processed.
    }
}
```

This is a snippet (without `main`, assuming `loader` and the imports), used to illustrate iterating over resources. When implementing real ServiceLoader usage, you should use `ServiceLoader` so the framework handles the provider descriptor protocol or `provides ... with ...` declarations in modules, rather than writing a manual parser that ignores the rules.

**Order is not “version recency”.** If multiple JARs contain `config.properties`, parent-first may return the parent's file first even if the child contains a newer version; if your code only takes the first URL, the child's version will not be used. This is a loader policy; you must design explicitly if you want to prioritize the plugin.

## 7. When Child-First Resource Lookup Is Needed

Some plugin systems allow a plugin's libraries to use their own resources even when the parent has a file with the same name. You can choose a **child-first** policy for a specific resource namespace:

```text
getResource("plugin-private/config.yaml")
    -> search for the resource in the plugin first
    -> only delegate to the parent if not found
```

However, overriding `getResource` while **not** handling `getResources` consistently can create hard-to-detect bugs:

- `getResource(name)` returns the child's URL.
- `getResources(name)` continues returning the parent first.
- One library reading a single resource and another library enumerating the same name receive different priority results.

If there is a genuine reason to require child-first, design **both APIs** so that the first element of the enumeration reflects the same policy, check how to avoid duplicate URLs, and ensure access to the parent where appropriate.

In many applications, a simpler measure is to place dedicated resources in a non-conflicting namespace, such as `plugin-a/config.yaml`, instead of sharing `config.yaml` at the root. This reduces dependency on JAR order and delegation.

**Do not switch all class loading to child-first just to fix a single resource.** Class loading affects type identity, API/SPI, and packages that need to be shared; adjust resource lookup only to the extent needed.

## 8. Class Resources and Resource Loaders Can Differ

To retrieve a resource accompanying a class, developers commonly use:

```java
InputStream stream =
        Plugin.class.getResourceAsStream("settings.properties");
```

With the `Plugin` class in package `com.acme.plugin`, this looks up relatively within that package. If the code uses:

```java
Plugin.class.getClassLoader()
        .getResourceAsStream("settings.properties");
```

it looks up the resource at the **classpath root** instead. The `/` / package difference is a common cause of `null`.

Two additional factors:

1. `Class.getResource` takes context from the **specific class** (and that class's module, if it is a named module). A library in a parent loader does not automatically look down into every resource of a child plugin.
2. `Thread.currentThread().getContextClassLoader()` (TCCL) is a loader attached to a thread, managed by application code or frameworks. Some provider discovery APIs (such as typical `ServiceLoader` usage) may rely on the TCCL, but changing the TCCL **does not change** the defining loader of an already-loaded class.

In host–plugin communication, explicitly document where `META-INF/services/...` descriptors must be placed and which loader is used to look them up. If the host only uses the system loader while the resource resides in the plugin loader, simply packaging the file properly is not enough.

Especially when code runs in a thread pool, if you temporarily change the TCCL, you must restore it in a `finally` block to avoid leaving the plugin context active beyond the task's lifetime:

```java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Call discovery APIs that use the context class loader if needed.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
```

This is an illustrative snippet, assuming `pluginLoader` has already been created; it is not a standalone program.

## 9. JPMS: Named Modules Add Resource Visibility Rules

Since Java 9, the same class loader can define classes from **multiple modules**. Reading resources in a named module is subject to **module encapsulation** in addition to normal delegation.

### 9.1. ClassLoader.getResource(s) and the opens Requirement

According to the Java SE 17 API, `ClassLoader.getResource`, `getResources`, and `resources` are restricted when a resource resides in a package of a **named module**:

- An exception exists for resources whose names end with `.class`, per the API rules.
- For resources **that are not `.class`** in a package of a named module, these APIs normally return the resource only if that package is **opened unconditionally**.
- `exports` serves module API/type access; it does not imply `opens` for all resources to be accessed via a class loader.
- A resource not located in a package of a named module has different rule application; you should not mechanically assume that every resource of every named module requires opening a package.

Therefore, even though a file is clearly present in the module JAR, `loader.getResource("com/acme/internal/settings.json")` may still return `null` because the package is not opened unconditionally.

### 9.2. Class.getResource and Module.getResourceAsStream

When code has a class belonging to a named module:

- `SomeClass.class.getResource(...)` uses the class's module context and corresponding module-aware delegation.
- `Module.getResourceAsStream(name)` uses the target module and performs access checks against the caller module; a package may be opened **conditionally** to the calling module.
- Do not infer that `ClassLoader.getResource` will produce the same results as `Module.getResourceAsStream` across all JPMS configurations.

A class loader that supports defining modules has a protected overload:

```java
protected URL findResource(String moduleName, String name)
        throws IOException
```

This is an API signature (not a standalone program). This overload supports looking up resources belonging to a named module and serves as the foundation for `Class`/`Module` APIs. Default implementation:

- If `moduleName == null`, attempts to delegate to `findResource(String name)`.
- If `moduleName != null`, returns `null`; a custom loader that truly supports multiple named modules should override it to look up the appropriate module.

This protected overload itself does not enforce all encapsulation rules intended for caller APIs; implementers must understand the contract of each call site.

**Do not use `--add-opens` as a catch-all patch for every resource lookup failure**: many `ClassLoader.getResource` APIs require **unconditional opens** by contract, and the actual root cause could also be a wrong resource path, launcher, module path, or chosen loader.

## 10. findResource vs. findClass, and Resource Packaging

`findClass("com.acme.Plugin")` finds or defines the bytecode of a **class**. `findResource("com/acme/plugin.yaml")` finds a **resource URL**. There is no contract guaranteeing that overriding one method makes the other automatically support the same data source.

For example, a custom loader might read `plugin/Greeter.class` from a database to call `defineClass`, yet without implementing resource lookup, `getResource("plugin/defaults.yaml")` can still return `null`.

Similarly, `javac` **does not automatically copy all `.properties` or `.json` files** from the source directory to the output classes directory. Many build tools have their own resource-processing step:

- Maven typically copies `src/main/resources` into the output during the resources lifecycle phase, then packages them into the JAR.
- The Gradle Java plugin typically processes `src/main/resources` via `processResources` into the appropriate resources output directory.
- If using standalone `javac`, you must manually place resources into the right classpath root/JAR and verify the structure using a tool such as `jar tf app.jar`.

For the resource `com/acme/config.properties` to be found by `getResource("com/acme/config.properties")`, the JAR must contain an entry with that exact path; placing the file outside the JAR and using a classpath pointing to the wrong root will cause the lookup to fail.

**Some sources can only be read through their own loader/framework**, such as nested JARs in an executable application framework; do not assume every JAR structure can be accessed via `new File(url.getPath())`.

## 11. Common Errors and Exceptions

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `getResource(name) == null` | Wrong name, missing resource, different loader, blocked by JPMS, or missing custom `findResource` | Print the resource name and loader used; inspect the JAR, module, and path |
| `getResourceAsStream(name) == null` | Resource not found / cannot be opened per contract | Check the same causes as `getResource`; do not dereference `null` |
| `getResource` finds it, but `getResources` misses the child version | Overrode `findResource` without overriding `findResources` | Check the implementation of both extension points |
| `getResources` returns unexpected multiple results | Same-named file in parent, multiple JARs, or multiple loader sources | Iterate through URLs; check delegation order and merge rules |
| `getResource` picks up an old configuration | Parent-first selected the parent's file | Separate namespaces or design an appropriate priority |
| `IOException` when iterating/reading resources | I/O error from `getResources` or `URL.openStream` | Inspect the cause, close streams, check permissions/source |
| `UncheckedIOException` when processing `resources(name)` stream | I/O error occurred during stream evaluation | Handle it explicitly or use `getResources` as appropriate |
| `SecurityException` / URL not visible | Access restricted by environment or module | Check legacy SecurityManager, permissions, and module opening |
| ServiceLoader reports missing provider | Missing descriptor, wrong SPI name, or provider cannot be loaded/cast | Check `META-INF/services`, SPI defining loader, classpath/module path |
| Resource URL has `jar:` so File API fails | Resource is inside a JAR, not a regular file | Use `openStream` instead of assuming a filesystem path |
| Old resource still appears after redeploy | Old loader/cache or unchanged runtime classpath | Check live loaders, URL caches, lifecycle, and deployed resources |

**Read the cause before “fixing”.** A resource may exist at the right path yet be loaded from a different loader; adding a duplicate file to the classpath will not by itself resolve parent-first precedence.

## 12. Designing a Custom Loader: Consistency, Performance, and Resources

### 12.1. Ordering and Completeness

When overriding `findResource` and `findResources`, you need to decide:

1. **Which local sources are valid?** Directory, JAR, in-memory, database, or a controlled endpoint.
2. **How do resource names map to sources?** Normalize `/`, package paths, and prevent path traversal.
3. **Can a resource have multiple local copies?** If so, `findResources` must be able to return multiple URLs, rather than calling `findResource` once like the sample directory loader that contains at most one file per name.
4. **Can the URL open a stream reliably?** A URL that merely “looks right” while `openStream()` fails is an incomplete implementation.
5. **How are parent vs. local prioritized?** If overriding the public APIs as well, ensure `getResource` and the first element of `getResources` are consistent.
6. **Enumeration timing and lifecycle:** if resources are modified or deleted right between lookup and opening the stream, `URL.openStream` can fail after the URL has already been returned.

### 12.2. Handling Untrusted Data

Do not trust externally configured resource names: prevent reading outside the root, symlink escapes, unexpected URL sources, extremely large files, and network loading models lacking timeouts/limits. Grant read access only to designed sources.

In the example, the `findResource` override returns `null` if a URL cannot be constructed, following the API contract. For a real-world loader, write appropriate diagnostic logs at the application layer (without exposing sensitive information) and define how I/O errors are handled, rather than swallowing every exception so that file lookup silently “succeeds with empty”.

### 12.3. Concurrency and Caching

Multiple threads calling `getResource` / `getResources` concurrently do not acquire a class initialization lock like `<clinit>`. If the loader holds mutable state, caches, backend connections, or counters, it needs its own appropriate synchronization mechanism.

For files/JARs that may change after startup, caching resource URLs or contents requires a clear invalidation policy. Do not assume the JVM automatically reloads a resource just because a file has been replaced; some frameworks snapshot or cache at a separate layer.

### 12.4. Closing Loaders and Streams

When using `URLClassLoader`, `close()` releases resources managed by the loader (such as JAR handles), but does not guarantee that already-defined classes unload immediately. You must close each `InputStream` individually for every read. To reload a plugin, you typically must manage the class loader lifecycle, references to classes/instances, and caches/descriptors—not merely overwrite files inside a JAR currently in use.

### 12.5. Do Not Write a Custom URL Handler Unnecessarily

If resources already reside in normal directories/JARs, `URLClassLoader` implements class/resource lookup from URLs, so in most cases there is no need to override these methods yourself. Only write a custom loader when the bytecode/resource source is different or has special policy requirements; adding an unnecessary custom layer easily loses JAR/module features that the runtime already supports.

## 13. Diagnostic Procedure When a Resource Is Not Found

1. **Record the exact resource name** passed in, including any leading `/`, letter casing, and package location.
2. **Identify the specific API**: `Class.getResource`, `ClassLoader.getResource`, or `getResources`? They have different naming and lookup rules.
3. **Identify the loader**: which loader defined the running class; does the API use the TCCL, the system loader, or a plugin loader?
4. **Verify the actual resource in the deployed artifact**: for a JAR, use `jar tf file.jar` and compare entry names; for a classes directory, check the classpath root.
5. **Read all results** from `getResources` if there is a conflict: which URL appears first, and does the parent have a resource with the same name?
6. **For custom loaders, inspect each extension point separately**: `findResource` / `findResources`. Note that by default neither automatically reads custom directories.
7. **For named modules, check whether the package is opened** and whether the specific API requires unconditional opens or opening to the caller module.
8. **Read via URL.openStream()**; if reading fails even though the URL exists, distinguish a lookup failure from an I/O error on open.
9. **Check the lifecycle**: has the loader been closed, where is the thread context loader pointing, and was the resource deleted or updated mid-flight?
10. **Run a smoke test using the actual runnable artifact**, avoiding checking only that the resource exists in the source tree without being copied into the output/JAR.

Diagnostic snippet usable in an application once you have a `ClassLoader loader`:

```java
String name = "com/acme/config.properties";
System.out.println("first=" + loader.getResource(name));
Enumeration<URL> matches = loader.getResources(name);
int count = 0;
while (matches.hasMoreElements()) {
    System.out.println("match[" + count++ + "]="
            + matches.nextElement());
}
System.out.println("count=" + count);
```

This is a **snippet**; you must import `java.net.URL` and `java.util.Enumeration` and handle `IOException` in the caller. Printed URLs are meant for diagnosing sources—avoid letting URLs containing tokens or sensitive paths appear in production logs.

## 14. Common Misconceptions

**“If a class can be loaded, accompanying .properties files will definitely be found too.”** False: class loading and resource lookup are separate. A class can be created from bytecode without the loader knowing how to find other resource files.

**“Overriding findResource is enough for both getResource and getResources.”** False: `findResources` returns an empty enumeration by default and must be overridden when you want to find multiple local resources.

**“getResource and getResources always return the same URL.”** One API returns a single URL while the other can return multiple; with the default implementation, the first URL in the enumeration should align with getResource under corresponding access conditions.

**“Resource names must always start with a leading /.”** With `ClassLoader.getResource`, resource path names do not start with a slash; a leading `/` is a special rule of `Class.getResource` when specifying an absolute path.

**“findResource can return a Path or File.”** Its signature returns a `URL`; it can point to a jar, a file, or another protocol capable of opening a stream, not necessarily a file.

**“Resource names in Java use Windows File.separator.”** Per the API, resource names use `/`, not `\\` between segments.

**“If the exact file is visible in the module JAR, loader.getResource will definitely return a URL.”** Named modules enforce encapsulation; `ClassLoader.getResource` may require the package to be opened unconditionally for non-.class resources.

**“If a provider is not found, you only need to add findClass.”** ServiceLoader discovery also requires valid provider metadata, working resource lookup, and consistent SPI type identity.

**“Closing a URLClassLoader automatically closes all open streams.”** Streams must be closed independently; URL/JAR lifecycles and class unloading are separate concerns.

## 15. Self-Check Exercises

**Question 1.** Both the parent and the child contain `demo/config.properties`. Under default delegation, which copy does `child.getResource` typically return?

**Answer:** The parent's copy, because `getResource` queries the parent first and only calls local `findResource` if the parent does not find it.

**Question 2.** What does `child.getResources("demo/config.properties")` return if both the parent and child provide it and the loader supports local findResources?

**Answer:** An Enumeration with the URLs returned by the parent first, followed by the child's URL. Contents may overlap, and the API does not automatically resolve them by version.

**Question 3.** A custom loader only overrides `findResource` and has a child-only resource. Why does `getResources` not see that resource?

**Answer:** Because `getResources` calls the `findResources` extension point to collect local URLs; by default `findResources` returns empty and does not automatically call `findResource`.

**Question 4.** For a class in `com.acme`, how does `SomeClass.class.getResource("config.properties")` differ from `SomeClass.class.getClassLoader().getResource("config.properties")`?

**Answer:** The method on `Class` looks up relative to the `com/acme/` package; the method on `ClassLoader` looks up from the root using the exact name without a package prefix.

**Question 5.** `getResource` returns a URL starting with `jar:file:`. Should you use `new File(url.toURI())` to read it?

**Answer:** Do not assume the URL is a local file. Use `url.openStream()` and close it with try-with-resources; handle I/O errors.

**Question 6.** A JSON resource resides inside a package of a named module, yet `ClassLoader.getResource` returns null. What additional checks should you perform?

**Answer:** Check whether that package is opened **unconditionally** per the ClassLoader resource lookup requirements; also verify the resource name, module/loader, and lookup method.

**Question 7.** When should you use `Module.getResourceAsStream` instead of `ClassLoader.getResource`?

**Answer:** When you want to access a resource in a specific module and need to follow module/caller access rules, rather than relying on general class loader lookup.

## 16. Conclusion and Official Documentation

`findResource` and `findResources` are the **two resource lookup extension points** of `ClassLoader`. The first supports finding a single local URL, and the second supports enumerating multiple local URLs; they are independent and must be implemented consistently. With the default public APIs, `getResource` prioritizes the parent when finding a single resource, while `getResources` combines parent then local. Designing this mechanism properly helps plugins and frameworks manage configuration, metadata, and service providers reliably while avoiding lookup-order and module-boundary bugs.

Reference documentation:

- Java SE 17 `ClassLoader` API (`getResource`, `getResources`, `findResource`, `findResources`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getResource`, `getResourceAsStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `Module` API (`getResourceAsStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
