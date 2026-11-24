# Resource Path Rules and the Risk of Picking the Wrong Copy from a Parent Loader

A Java application can load plugins, drivers, codecs, or configuration rule sets at runtime. Each component typically packages resources such as `.properties`, `.yaml`, JSON, templates, certificates, or `META-INF/services` files. An easily overlooked problem is that **the resource name does not guarantee it comes from the right JAR or the right plugin version**.

For example, both the application library and a plugin contain `config/mode.txt`. Code calling `pluginLoader.getResource("config/mode.txt")` might read **the parent loader's copy**, even though the call is made on the `pluginLoader` variable. The root cause lies in **path naming rules and the resource lookup delegation mechanism** of `ClassLoader`.

This article explains how Java interprets resource paths, the difference between `Class.getResource` and `ClassLoader.getResource`, the parent/child loader lookup algorithm, how to detect duplicate-named copies, the impact of the thread context class loader and JPMS, along with a runnable Java 17 example and verified output.

## 1. How Are Resources on the Classpath Identified?

A **resource name** in Java is a logical path string whose components are separated by `/`. It is **not necessarily a file path on disk**:

- `config/app.properties`: resource name starting from the **classpath root or root managed by the loader**.
- `META-INF/services/com.example.spi.Codec`: SPI metadata by convention.
- `com/example/plugin/schema.json`: resource placed in the same namespace/package as a plugin.
- `images/icon.png`: resource that may reside in a build directory, JAR, or another source understood by the loader.

If a project has `src/main/resources/config/app.properties`, when built following standard classpath layout, the lookup name is `config/app.properties`. Do not pass `src/main/resources/config/app.properties` into `getResource` at runtime: `src/main/resources` is the source layout for the build process, not the standard prefix of the packaged resource.

Important rules:

1. Use `/` in resource names, even when running on Windows; do **not** construct resource names with `File.separator` or concatenate paths like OS files.
2. Match exact uppercase/lowercase and every path segment. Inside a JAR, entry names are case-sensitive; when running from an exploded directory, the filesystem may have different case rules. Portable code should not rely on the filesystem ignoring case differences.
3. A **leading `/`** has a special meaning when using `Class.getResource`, but is not syntax you should pass to `ClassLoader.getResource`. Distinguish the two APIs in the next section.
4. If a resource is not found, `getResource` returns `null`, and `getResourceAsStream` may also return `null`; errors should report the resource name and the loader being used.
5. The returned URL may use `jar:`, `file:`, `jrt:`, or another loader mechanism. **Do not assume a resource URL can be turned into a `java.io.File`**; prefer `URL.openStream()` or `getResourceAsStream()`.

```text
Source layout                          Runtime lookup name
src/main/resources/
    config/app.properties          --> config/app.properties
    com/acme/plugin/rules.json     --> com/acme/plugin/rules.json
    META-INF/services/x.y.Codec    --> META-INF/services/x.y.Codec
```

Note: resources are not identical to class code. The fact that a class is found by a given loader does not mean a same-named resource in that loader will take precedence if the resource lookup path still delegates to the parent.

## 2. Distinguishing Class.getResource and ClassLoader.getResource

This is a very common source of bugs when moving code between packages or moving from a plugin helper into host code.

### `ClassLoader.getResource(String name)`

The resource name is resolved from the root of the namespace searched by the loader; normally it **does not start with `/`**:

```java
ClassLoader loader = MyPlugin.class.getClassLoader();
URL url = loader.getResource("com/acme/plugin/rules.json");
```

This is an **illustrative snippet**: `MyPlugin` must be an existing class, and the `ClassLoader`/`URL` imports along with the corresponding resource must exist in the project. `getResource` returns the first URL according to the loader's rules. `getResourceAsStream` selects the source using that same resource lookup rule.

### `Class.getResource(String name)`

`Class` supports two interpretations:

- If `name` **does not have a leading `/`**, it is a name **relative to the class's package**.
- If `name` **starts with `/`**, the leading slash is stripped and the remainder is interpreted as an **absolute name from the root resource namespace**.

Suppose the class is `com.acme.plugin.MyPlugin`:

| Call | Resulting Absolute Resource Name |
| --- | --- |
| `MyPlugin.class.getResource("rules.json")` | `com/acme/plugin/rules.json` |
| `MyPlugin.class.getResource("config/rules.json")` | `com/acme/plugin/config/rules.json` |
| `MyPlugin.class.getResource("/config/rules.json")` | `config/rules.json` |
| `MyPlugin.class.getClassLoader().getResource("config/rules.json")` | `config/rules.json` |
| `MyPlugin.class.getClassLoader().getResource("/config/rules.json")` | Not the standard ClassLoader path form; with a standard `URLClassLoader` it may fail to find the resource |

**Be careful with the assumption that "using Class.getResource will definitely select the plugin's resource."** For classes in an unnamed module, this API constructs the absolute resource name and delegates to the **class's defining loader**; that loader may continue delegating resource lookup to its parent. For classes in a named module, Java has module-specific resource lookup paths and module encapsulation rules; see section 7.

When changing a class's package location, `MyPlugin.class.getResource("rules.json")` changes the corresponding resource name. Therefore, using a relative path is convenient for resources truly bound to a class/package; use an explicit root path for resources with a package-independent contract.

### Obtaining a Stream and Closing Resources

Example using `ClassLoader` with a URL:

```java
ClassLoader loader = MyPlugin.class.getClassLoader();
URL url = loader.getResource("com/acme/plugin/rules.json");
if (url == null) {
    throw new IllegalStateException("Resource not found: com/acme/plugin/rules.json");
}
try (InputStream in = url.openStream()) {
    byte[] bytes = in.readAllBytes();
    // Decode/parse bytes according to the resource's contract.
}
```

This is also a snippet, requiring `URL`, `InputStream`, and the `MyPlugin` class. Read into bytes and then choose the right charset (usually UTF-8 if the contract specifies it), closing the `InputStream` with try-with-resources. With `getResourceAsStream`, you must also check for `null` and close the stream; it is convenient when you don't need to know the URL, but **the URL is useful for diagnosing the origin of the selected copy**.

## 3. Why Can a Child Loader Pick the Wrong Copy from a Parent Loader?

Standard `ClassLoader` uses the **delegation** model. For `getResource(name)`, the default implementation works conceptually as follows:

1. Ask the **parent class loader** first; if the parent is `null`, search the bootstrap loader's sources.
2. If the parent returns a URL, take that URL and finish.
3. If the parent does not find it, call `findResource(name)` to search in the current loader itself.

For `getResources(name)`, the default implementation enumerates results from the **parent first**, then appends results from the child loader's `findResources(name)`.

```text
ClassLoader parent
    resources/
        config/mode.txt      (PARENT)
            |
            | delegation
            v
ClassLoader child
    resources/
        config/mode.txt      (CHILD)

child.getResource("config/mode.txt")
    -> parent.getResource(...) -> PARENT is selected
    -> no need to search CHILD

child.getResources("config/mode.txt")
    -> [URL of PARENT, URL of CHILD]  (with default URLClassLoader)
```

This is the rule of the **default parent-first `ClassLoader` and `URLClassLoader` implementations**, not a guarantee that all custom class loaders behave identically. A plugin host or application server may override `getResource`/`getResources` or apply a child-first policy for certain namespaces. In named modules, the search order across modules in the same loader even has unspecified cases. **Do not build version-selection logic based on arbitrary assumptions about result order.**

### A Mechanically Real Integration Bug

The host provides `config/codec.properties` version 1; the plugin also has that same name for version 2. The plugin code calls `getClass().getClassLoader().getResourceAsStream("config/codec.properties")`. If the plugin loader goes through parent-first delegation, the host's version 1 content may be selected. The system keeps running, yet algorithm settings, mappings, versions, or feature flags can be silently wrong.

The dangerous part is that **a resource is found**, so `null` checks do not catch the bug. You need to verify **provenance** (which provider/artifact/version the resource belongs to), and ideally avoid name collisions by design.

## 4. Standalone Java 17 Example: Reproducing Parent-First and Checking Duplicate-Named Copies

The example below creates two temporary directories, each containing `config/mode.txt` with different content. One `URLClassLoader` acts as the parent and another loader acts as the child; the child receives that parent upon construction. Finally, an isolated loader is tested to see the copy inside the child. The program requires no libraries outside the JDK.

Create `ParentFirstResources.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Enumeration;

public class ParentFirstResources {
    static String read(URL url) throws IOException {
        if (url == null) return "<missing>";
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("resource-choice-");
        Path parentRoot = root.resolve("parent");
        Path childRoot = root.resolve("child");
        Path parentFile = parentRoot.resolve("config/mode.txt");
        Path childFile = childRoot.resolve("config/mode.txt");

        try {
            Files.createDirectories(parentFile.getParent());
            Files.createDirectories(childFile.getParent());
            Files.writeString(parentFile, "PARENT\n", StandardCharsets.UTF_8);
            Files.writeString(childFile, "CHILD\n", StandardCharsets.UTF_8);

            try (URLClassLoader parent = new URLClassLoader(
                         new URL[] {parentRoot.toUri().toURL()}, null);
                 URLClassLoader child = new URLClassLoader(
                         new URL[] {childRoot.toUri().toURL()}, parent);
                 URLClassLoader childOnly = new URLClassLoader(
                         new URL[] {childRoot.toUri().toURL()}, null)) {

                String name = "config/mode.txt";
                System.out.println("selected=" + read(child.getResource(name)));

                Enumeration<URL> all = child.getResources(name);
                int index = 0;
                while (all.hasMoreElements()) {
                    System.out.println("candidate" + (++index)
                            + "=" + read(all.nextElement()));
                }

                System.out.println("isolated=" + read(childOnly.getResource(name)));
                System.out.println("slashFound=" + (child.getResource("/" + name) != null));
            }
        } finally {
            Files.deleteIfExists(parentFile);
            Files.deleteIfExists(childFile);
            Files.deleteIfExists(parentFile.getParent());
            Files.deleteIfExists(childFile.getParent());
            Files.deleteIfExists(parentRoot);
            Files.deleteIfExists(childRoot);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ParentFirstResources.java
java ParentFirstResources
```

Stdout verified with `javac --release 17` and `java`:

```text
selected=PARENT
candidate1=PARENT
candidate2=CHILD
isolated=CHILD
slashFound=false
```

**Explanation:**

1. `parentRoot` and `childRoot` both contain the logical path `config/mode.txt`, with different content so we can observe which source gets selected.
2. `parent` is a `URLClassLoader` with a `null` parent; `child` delegates to `parent`. Due to parent-first, `child.getResource(name)` receives the content `PARENT`.
3. `child.getResources(name)` lists both copies and in this example in the order `PARENT` then `CHILD`. This is the behavior of the default loader pair created in the example.
4. `childOnly` has no `parent` containing the resource, so the query selects `CHILD`. **This is an experiment demonstrating isolation, not a recommendation to always set parent to `null` for production plugins**: real classes/plugins may need shared APIs from the host and platform modules.
5. `slashFound=false` shows that with the loader in the example, `ClassLoader.getResource("/config/mode.txt")` does not find it. For `Class.getResource("/config/mode.txt")`, the leading `/` has a valid meaning as shown in section 2.

Do not conclude that replacing the parent loader with `null` is a universal solution. It can prevent the provider from seeing service interfaces, dependent libraries, or cause duplicate class identities. The appropriate solution is usually **giving resources their own namespace**, checking for collisions, and building an explicit lookup policy.

## 5. When Multiple Copies Exist: Detecting, Choosing Correctly, and Failing Fast

### Using getResources to Find Collisions

If you only call `getResource` or `getResourceAsStream`, the application knows "a resource exists," but may not know "a second copy exists." When a resource **is required to be unique**, check with `getResources`:

```java
static URL requireUniqueResource(ClassLoader loader, String name)
        throws IOException {
    var locations = java.util.Collections.list(loader.getResources(name));
    if (locations.size() != 1) {
        throw new IllegalStateException(
            "Expected exactly one resource '" + name
            + "', found " + locations.size() + ": " + locations);
    }
    return locations.get(0);
}
```

This is a helper snippet, requiring imports for `URL` and `IOException` and to be called from a declared class. It checks the **number of resource locations visible to the loader at lookup time**; it does not automatically verify content, signatures, permissions, or versions. For configurations required to be unique, failing fast is better than silently taking the first copy.

On the other hand, resources designed to have **multiple copies** should not fail fast just because `getResources` returns multiple URLs. For example, `META-INF/services/<service-interface>` is used by `ServiceLoader` to discover multiple providers; `META-INF/services` should be processed per SPI rules, not treated as a single-owner config file. Some applications also intentionally merge multiple metadata fragments from JARs. In those cases, you must define clear policies for merging, duplicates, and parse errors.

### Three Valid Source-Selection Policies

**A. Owner-Specific Namespace**

Use `META-INF/com.acme.plugin-x/config/rules.json` or `com/acme/pluginx/rules.json` instead of placing every resource as `config.json`/`application.properties` at the root. This is usually the simplest measure and least dependent on class loader order. When changing schema versions, declare the version in the name, metadata, or content if the contract needs to distinguish them.

**B. A Single Lookup Point with Clear Ownership**

A plugin registry can hold a `ClassLoader`, `Module`, or handle to a validated artifact and provide `openResource(pluginId, resourceName)`. Business logic does not arbitrarily call the system loader or TCCL. At this point, the registry can check: plugin ID, version, path within allowed namespaces, duplicate candidates, and URL provenance. For a specific JAR, entries can be read via `JarFile`/`JarEntry` according to an explicit contract rather than relying on a parent-first loader's resource algorithm; JAR/stream lifecycles must be managed.

**C. Intentional, Tested Precedence**

Some hosts design parent-first for shared APIs and child-first for plugin-private resources. If the system genuinely requires that policy, implement it in a loader/registry that clearly documents **which namespaces take precedence**, when fallback occurs, what happens on name collisions, and whether consistency with `getResources` is maintained. Arbitrarily flipping all lookups to child-first can cause class identity, ABI, or dependency conflict bugs.

**Do not use "the second URL in the enumeration" as a contract.** The specific order of the `URLClassLoader` pair in the example is observable, but many custom loaders and module configurations have unstable or unspecified ordering.

## 6. TCCL, System Loader, and the Class's Defining Class Loader

Three calls can use **three different loaders**:

```java
ClassLoader defining = MyPlugin.class.getClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

This is a snippet; `MyPlugin` must exist. `defining` is the loader that defined the class (which may be `null` for bootstrap classes). `context` is the **thread context class loader (TCCL)**, a per-thread setting used by many frameworks to discover implementations/resources. `system` is the JVM's system/application loader.

For example, a host request thread has TCCL pointing to the host's loader, while a worker thread has a different TCCL; the same `context.getResource("config/mode.txt")` call can receive two different results. A thread pool might retain the TCCL from when it was created or have it altered by a framework. You should not assume the TCCL is always the loader of the plugin currently handling the request.

If an API actively uses the TCCL, you must determine who sets it, who restores it, and whether that operation aligns with the framework contract. When temporarily changing the TCCL, restore it in `finally` to avoid polluting the thread pool's context:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Call a framework API designed to use the TCCL.
} finally {
    thread.setContextClassLoader(old);
}
```

The snippet above is illustrative and requires the `pluginLoader` variable to have been created and checked beforehand. **Changing the TCCL does not change the class loader that defined a class, nor does it automatically eliminate parent-first delegation.** If you only need to read a resource belonging to a known artifact, prefer an API that takes an explicit loader/module/artifact rather than mutating thread-wide context.

## 7. Resources in the Java Platform Module System (JPMS)

With **named modules**, resource lookup rules have an added layer of **encapsulation**. Two points to distinguish:

1. `ClassLoader.getResource(name)` and `getResources(name)` enforce restrictions on resources **not ending in `.class`** inside packages belonging to a named module: they can only return such a resource through these APIs when the package is **unconditionally** `opens`. `exports` for public Java APIs is not equivalent to `opens` for resource/reflective access.
2. `SomeClass.class.getResource(...)` (when `SomeClass` belongs to a named module) first searches within the module associated with the class and applies package-opening conditions to the caller's module. `Module.getResourceAsStream(name)` also targets a specific module, applying that module's resource access rules.

If you want to read a resource associated with a known module:

```java
Module owner = SomeProvider.class.getModule();
try (InputStream in = owner.getResourceAsStream(
        "com/acme/provider/schema.json")) {
    if (in == null) {
        throw new IllegalStateException("Resource unavailable in module");
    }
    // Read according to the plugin's charset/schema.
}
```

This is a snippet requiring the `SomeProvider` class and the appropriate `InputStream` import; the API can throw `IOException`. **It does not mean** that merely knowing the module grants permission to read every package resource: for a named module, the package containing the resource may need to be `opens` to the caller. Resources not belonging to a module's packages and `.class` files have separate encapsulation rules.

In a module layer with multiple modules containing the same resource name, `ClassLoader.getResource` does not guarantee a search order among them. To bind a resource to the exact module/version, use the module reference chosen by the registry and verify access rights, instead of looking up a generic name on the class loader.

The JDK 17 documentation clearly specifies these rules in `ClassLoader.getResource/getResources`, `Class.getResource`, and `Module.getResourceAsStream`.

## 8. In What Order Should You Diagnose "Right Name, Wrong Copy"?

When a plugin loads the wrong configuration file, the goal is to prove which **resource name, loader, URL, and content/version** was actually selected, not merely whether the filename exists.

### Step 1 — Identify the Exact Resource Name

Record the logical name the code passes to the API, whether it has a leading `/`, whether it is a package-relative path, and whether the casing is exact. Do not check only files in the `src/main/resources` directory; inspect the **artifact/runtime classpath** actually executing.

### Step 2 — Record the Loader Source and Context

Determine which API was called: `SomeClass.class.getResource`, `someLoader.getResource`, or a loader obtained from the TCCL. Observe the class/identity of the defining/context loader and parent chain if possible. Avoid logging sensitive configuration contents; log only safe metadata.

### Step 3 — Enumerate Candidates Instead of Reading Only the First Match

In an environment where safe diagnostics can run:

```java
String name = "com/acme/pluginx/rules.json";
ClassLoader loader = plugin.getClass().getClassLoader();
var urls = java.util.Collections.list(loader.getResources(name));

System.out.println("resource=" + name);
System.out.println("loader=" + loader);
System.out.println("candidates=" + urls.size());
urls.forEach(url -> System.out.println("candidateUrl=" + url));
```

This is a snippet: it requires a `plugin` object, `getResources` can throw `IOException`, and you should consider that logging URLs may expose internal paths. If there are two URLs, compare the JAR name, version, and checksum in a test environment; do not pick merely by enumeration index.

### Step 4 — Verify What File Is Actually Packaged

List the entries inside the JAR:

```bash
jar --list --file plugin.jar
```

Look for names like `com/acme/pluginx/rules.json` or `META-INF/services/...`. If the entry is missing, you must fix the build/packaging; it cannot be cured by changing the class loader. If two copies exist in host/plugin, check the JARs actually used and the loader order. For shaded/assembled JARs, inspect how metadata is merged/overwritten, especially `META-INF/services`.

### Step 5 — Add Tests Guarding Resource Selection Rules

You should have integration tests that set up both parent and child resources with **the same name and different contents**, as in section 4's example. Test the specific production loader (including app servers/frameworks) and verify the selected URL; add fail-fast tests when a resource must be unique but >1 candidate exists, as well as missing-resource tests.

On production paths, if a resource governs critical behavior (mappings, policies, trust stores, serialization schemas), you can additionally verify version/schema/checksum or source signatures per contract. Silently picking a "plausible-looking" wrong copy can be more dangerous than a `null` error.

## 9. Common Errors Table

| Symptom | Common Cause | How to Verify and Fix |
| --- | --- | --- |
| `getResource` returns `null` even though the file is in the project | Passing the `src/main/resources` prefix, wrong package, wrong case, or resource not packaged | Check the resource name from root, JAR entry list, and actual artifact |
| `Class.getResource("x.json")` looks in the wrong place | This method treats `x.json` as relative to the class's package | Use the absolute path `"/config/x.json"` when root is needed; verify module/package |
| `ClassLoader.getResource("/x.json")` fails to find it | Confusing the leading `/` rule from `Class.getResource` | Pass `"x.json"` to `ClassLoader` |
| Plugin reads the host's configuration | Parent-first selects the same resource name from the parent loader | Use `getResources` to find collisions; give plugins distinct namespaces and clear registry ownership |
| Old content still seen after updating JAR | Runtime still uses parent JAR/old loader, framework cache, or artifact not replaced in process | Inspect source URL and deployment/version; refresh according to lifecycle |
| Works on one machine, fails on another | Different packaging, classpath order, class loader policy, or filesystem environment | Test against real artifact/container; remove reliance on implicit order |
| `getResourceAsStream` returns data but wrong config | Not verifying provenance or multiple copies share the same name | Inspect URLs with `getResources`, compare version/schema, fail fast when needed |
| Resource in named module not found | Package not properly `opens` or wrong module-lookup API used | Check `module-info.java`, use appropriate `Class`/`Module` API with proper permissions |
| `Paths.get(url.toURI())` fails for a resource inside a JAR | Not every resource URL corresponds to a file in the default filesystem | Use `URL.openStream()`, or an appropriate ZIP/JAR API when needed |
| Changing TCCL breaks other plugins in thread pool | Context not restored or expecting TCCL to change delegation | Use `try/finally`; prefer explicit loader/module and test reload paths |

## 10. Resource Design Rules for Extensible Modules

**Name with ownership.** Avoid generic keys like `config.json` or `settings.properties` at the classpath root if multiple plugins might use them. Namespace by organization/plugin and keep it stable in the contract; version schemas when needed.

**Separate logical names from physical sources.** Core APIs can accept `pluginId + resourceName`, while the plugin registry routes to the permitted loader/module/JAR. Business code does not need to know the JAR path on disk or loader order.

**Have clear collision rules.** Some resources legitimately must be unique; others like SPI metadata can be aggregated. Define which groups must fail fast, which may be merged, and how to handle duplicate providers/configs.

**Do not mix resource paths with OS paths.** Resource names use `/`, not absolute paths on the host machine. Do not trust resource names supplied by unvalidated input; the registry should restrict namespaces, block path traversal, and verify the owner before opening artifacts.

**Manage loader and stream lifecycles.** Close `InputStream` immediately after reading; if managing a `URLClassLoader`, close it when the plugin lifecycle ends and no active operations need the resources. Closing a loader does not immediately unload already-defined classes; to unload old versions, release all associated references.

**Test in the real deployment environment.** Unit tests using a single flat classpath cannot reproduce parent-child resource collisions. Add integration tests that build a production-like hierarchy, verifying the exact source/version and module access.

### Short Pre-Release Checklist for Plugins

- [ ] Resource names use `/` and are calculated accurately relative to root/package per the API called.
- [ ] Does not rely on `src/main/resources` or real file paths at runtime.
- [ ] Knows **which class loader/module** owns the plugin and whether the lookup path is parent-first.
- [ ] If names can collide, checks `getResources` and handles them according to a clear policy.
- [ ] Does not let the parent loader silently dictate plugin-specific config when the plugin copy is required.
- [ ] TCCL is set/restored properly if required by a framework; never use TCCL as a shortcut for isolation.
- [ ] Verified `opens`/JPMS restrictions when reading resources inside named modules.
- [ ] Streams are closed, source URLs are inspectable, and versions/schemas are validated.
- [ ] Includes parent/child resource collision tests and tests on real JAR artifacts.

JDK 17 References:

- [`ClassLoader` and methods `getResource`, `getResources`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`Class.getResource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String))
- [`Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))

**Remember:** the right path only tells Java **what name to look for**; **the loader, delegation order, and module access** determine **which copy is actually returned**. For plugins, you must design resource namespaces, check for collisions, and bind resource sources to the proper owner/version instead of trusting that calling on a child loader will automatically prefer its own copy.