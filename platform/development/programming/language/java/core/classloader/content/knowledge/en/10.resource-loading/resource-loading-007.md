# Resource Delegation Order Must Be Consistent with Class Loading Policy

When writing a custom `ClassLoader`, we typically focus on `loadClass()`: should we ask the **parent** first (*parent-first*) or search for the class in the **child**'s own source first (*child-first*)? However, a Java application also loads **resources** such as `.properties`, templates, schemas, logging configurations, `META-INF/services/...` metadata, or data files packaged with libraries. Resources are located using `getResource()`, `getResources()`, and `getResourceAsStream()`.

**Core design rule:** If a plugin/class is defined from a child source, the resources **associated with that implementation** should usually also be selected from the child; if a shared class is defined by the parent, the corresponding metadata/resources need a clear policy from the parent. When switching `loadClass()` to child-first while leaving `getResource()` and `getResources()` with the default parent-first behavior, you can end up with **the child's code but the parent's config/metadata**, creating behavior that is very difficult to detect.

To be precise: Java **does not require every resource to always follow a single fixed order for all classes**. Some configurations intentionally require parent-first, while some resources need to be aggregated from multiple sources. What must be ensured is **a lookup policy consistent with resource ownership scope and the class-loading contract**, especially for resources tightly coupled to a specific class/provider.

## 1. Two Lookup Paths That Must Be Understood Separately

| Operation | Common APIs | Goal |
| --- | --- | --- |
| Load a class definition | `ClassLoader.loadClass(String)`, `Class.forName(..., loader)` | Obtain a `Class<?>` with the appropriate defining loader. |
| Find a single resource | `ClassLoader.getResource(String)` | Return the **first matching URL** or `null`. |
| Open a resource stream | `ClassLoader.getResourceAsStream(String)` | Usually based on the resource selected via `getResource`, returning an `InputStream` or `null`. |
| Find multiple resources with the same name | `ClassLoader.getResources(String)` | Return an `Enumeration<URL>` of the found entries according to the loader's policy. |
| Find a resource associated with a class | `SomeClass.class.getResource(...)` | Apply package-based relative/absolute naming rules, then look up within the context of the class/module. |

In the default `java.lang.ClassLoader`, the standard class-loading path follows **parent delegation**: check if already loaded, ask the parent first, and only then search locally via `findClass()`. For resources, the default `getResource()` implementation also tries the parent first before calling `findResource()`; the default `getResources()` enumerates results from the parent first and then from `findResources()`.

However, these are **two separate mechanisms**. If you only override `loadClass` without considering the resource APIs, classes can follow child-first while resources remain parent-first. Similarly, if you only override `getResource` while forgetting `getResources`, looking up a single resource and looking up multiple resources can end up following different policies.

### Problem Diagram

~~~text
               Same name: plugin/Engine.class
                          plugin/config.properties

                       Parent      Child
                         │           │
          class?         │           └──── SELECT Child's Engine
                         │
          resource?      └──────────────── SELECT Parent's config

             Child Engine + Parent config
                 → wrong schema, wrong feature flag,
                   hard-to-reproduce behavior
~~~

This is a common situation when the same resource name exists across multiple JARs/directories. If the parent does not have a colliding resource, the problem can remain hidden during development; after upgrading the host or plugin, a new resource appears in the parent and starts taking precedence unexpectedly.

## 2. Parent-First and Child-First: What Does Consistency Mean?

**Parent-first** prioritizes classes and resources provided by the parent:

~~~text
loadClass("demo.Marker")         → Parent tried first → Parent.Marker
getResource("demo/id.properties")→ Parent tried first → Parent resource
getResources(...)                → Parent entries first, then child entries
~~~

The advantage is sharing common APIs and resources, preventing plugins from replacing classes owned by the host. If a resource truly belongs to the child plugin version, parent-first is not always the desired choice.

**Child-first** instructs the child to prioritize classes and resources **within the chosen isolation scope**:

~~~text
loadClass("plugin.impl.Engine")     → Child tried first → Child.Engine
getResource("plugin/engine.yml")    → Child tried first → Child resource
getResources("plugin/engine.yml")   → Child entries first, then parent entries
~~~

Note: it is possible and usually **recommended** to keep parent-first for `java.*` and shared API contract packages, applying child-first only to private implementations. Avoid blanket child-first without clear boundaries, as it easily leads to duplicate interfaces/classes, `ClassCastException`, or linking issues.

**Single-resource** and **multi-resource** lookups have distinct requirements:

- `getResource(name)` selects **one** location; changing the order can immediately change the result.
- `getResources(name)` can find **multiple** entries. The enumeration order can affect configuration merging or provider discovery. Do not arbitrarily reverse or drop results if the framework relies on merge semantics.
- `getResourceAsStream(name)` typically delegates to the loader's own `getResource`; if a custom loader changes how URLs are located, the stream path must be reviewed consistently.
- `findResource` and `findResources` are designed to find the loader's **local resources**; parent delegation belongs to the `get...` method layer.

**Invariant to verify for resources tightly coupled to a class:** Once you know which loader actually defines class `C`, resources packaged alongside `C` must be retrieved according to that component's contract, avoiding accidental use of a copy from another component.

## 3. Standalone Java 17 Example: Observing the Two Policies

The following program creates two temporary directories, `parent` and `child`. Both contain the same class name `demo.Marker` and resource `demo/id.properties`, but with different contents. It uses the JDK's `JavaCompiler` to compile both versions of the class at runtime, and then observes which class and resource each loader selects.

**Single file: `ResourceDelegationDemo.java`**

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import java.io.InputStream;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Properties;

public class ResourceDelegationDemo {
    private static final String CLASS_NAME = "demo.Marker";
    private static final String RESOURCE = "demo/id.properties";

    static class ChildFirstLoader extends URLClassLoader {
        ChildFirstLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);

                if (type == null) {
                    if (CLASS_NAME.equals(name)) {
                        try {
                            type = findClass(name);
                        } catch (ClassNotFoundException notLocal) {
                            type = super.loadClass(name, false);
                        }
                    } else {
                        type = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        public URL getResource(String name) {
            if (RESOURCE.equals(name)) {
                URL local = findResource(name);
                if (local != null) {
                    return local;
                }
            }
            return super.getResource(name);
        }

        @Override
        public Enumeration<URL> getResources(String name)
                throws IOException {
            if (!RESOURCE.equals(name)) {
                return super.getResources(name);
            }

            List<URL> result = Collections.list(findResources(name));
            result.addAll(Collections.list(
                    getParent().getResources(name)));
            return Collections.enumeration(result);
        }
    }

    private static void buildVersion(Path directory, String owner)
            throws IOException {
        Path source = directory.resolve("src/demo/Marker.java");
        Path resource = directory.resolve(RESOURCE);

        Files.createDirectories(source.getParent());
        Files.createDirectories(resource.getParent());
        Files.writeString(source,
                "package demo; public class Marker { " +
                "public static String owner() { return \"" +
                owner + "\"; } }");
        Files.writeString(resource, "owner=" + owner + "\n");

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK, not a JRE");
        }

        int exit = compiler.run(
                null, null, null,
                "-d", directory.toString(), source.toString());

        if (exit != 0) {
            throw new IllegalStateException("Compilation failed: " + exit);
        }
    }

    private static String readOwner(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }

        Properties props = new Properties();
        try (InputStream input = url.openStream()) {
            props.load(input);
        }
        return props.getProperty("owner");
    }

    private static void inspect(String label, ClassLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass(CLASS_NAME);
        String classOwner =
                (String) type.getMethod("owner").invoke(null);

        String firstResource =
                readOwner(loader.getResource(RESOURCE));

        Enumeration<URL> found = loader.getResources(RESOURCE);
        List<String> resourceOrder = new ArrayList<>();

        while (found.hasMoreElements()) {
            resourceOrder.add(readOwner(found.nextElement()));
        }

        System.out.println(label + " class: " + classOwner);
        System.out.println(label + " resource: " + firstResource);
        System.out.println(label + " resources: " +
                String.join(" -> ", resourceOrder));
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("resource-order-");
        Path parentDir = Files.createDirectories(root.resolve("parent"));
        Path childDir = Files.createDirectories(root.resolve("child"));

        buildVersion(parentDir, "PARENT");
        buildVersion(childDir, "CHILD");

        try (URLClassLoader parent = new URLClassLoader(
                    new URL[] { parentDir.toUri().toURL() }, null);
             URLClassLoader parentFirst = new URLClassLoader(
                    new URL[] { childDir.toUri().toURL() }, parent);
             ChildFirstLoader childFirst = new ChildFirstLoader(
                    new URL[] { childDir.toUri().toURL() }, parent)) {

            inspect("Parent-first", parentFirst);
            inspect("Child-first", childFirst);
        }
    }
}
~~~

Compile and run in the directory containing `ResourceDelegationDemo.java`, using **JDK 17+** (requires `javac` and the system compiler from the `jdk.compiler` module):

~~~bash
javac --release 17 ResourceDelegationDemo.java
java ResourceDelegationDemo
~~~

**Expected stdout with a standard JDK 17+ and the directory URLs generated by the program:**

~~~text
Parent-first class: PARENT
Parent-first resource: PARENT
Parent-first resources: PARENT -> CHILD
Child-first class: CHILD
Child-first resource: CHILD
Child-first resources: CHILD -> PARENT
~~~

Explanation:

1. `buildVersion` generates two `demo.Marker` classes (each returning a different owner name) and two identically named `demo/id.properties` resources.
2. `parent` has a URL pointing to the PARENT version; both `parentFirst` and `childFirst` point to the CHILD version while sharing the same parent.
3. `parentFirst` is a default `URLClassLoader`, so both `loadClass` and `getResource` delegate to the parent first; both resolve to PARENT.
4. `ChildFirstLoader.loadClass` calls `findClass` locally first **only for `demo.Marker`**, and falls back to the parent afterward. For other classes (especially JDK classes), it preserves standard behavior.
5. `ChildFirstLoader.getResource` prioritizes the child's `findResource` specifically for the resource name associated with `demo.Marker`, and falls back to the parent afterward.
6. `ChildFirstLoader.getResources` returns the child's entries first followed by the parent's **for the selected resource**; other resources use the standard implementation. Consequently, the enumeration results reverse order between the two policies.
7. `getClassLoadingLock(name)` and `findLoadedClass(name)` prevent duplicate self-definitions and help keep class-loading behavior synchronized; `resolveClass` is only called when resolution is requested.

**Scope of the code:** This is a demonstration of classes/resources on a **directory-based classpath** with a single specific class name. Real-world loaders must handle package control, protection of shared APIs, duplicate resource ordering, I/O errors, and module relationships more thoroughly. `getResources` in the example intentionally does not deduplicate URLs; when an application performs merging or provider discovery, it must consider deduplication and preserving order according to its contract.

### What If Only loadClass() Is Overridden?

If `ChildFirstLoader` only overrides `loadClass` while keeping the `getResource` and `getResources` implementations from `ClassLoader`/`URLClassLoader`, you can observe:

~~~text
Child-first class: CHILD
Child-first resource: PARENT
Child-first resources: PARENT -> CHILD
~~~

This is the **analytical result for the variant** without the two resource overrides, not the output of the complete program currently provided. It illustrates precisely why policies must be synchronized when classes and resources are related.

## 4. Distinguishing Class.getResource from ClassLoader.getResource

The two APIs use **different resource naming rules**, which can easily lead to misdiagnosing loader delegation order:

| API Call | Path Interpretation |
| --- | --- |
| `loader.getResource("config/app.properties")` | Resource name resolved from the **root**, without a leading `/`. |
| `SomeClass.class.getResource("config/app.properties")` | Relative name resolved from **the package of SomeClass**. |
| `SomeClass.class.getResource("/config/app.properties")` | Absolute name resolved from the **root** (leading `/` is stripped before lookup). |

For example, when `demo.Marker` looks up `demo/id.properties`:

~~~java
// Illustrative fragment with an existing Class<?> markerType.
markerType.getResource("id.properties");
markerType.getResource("/demo/id.properties");
markerType.getClassLoader().getResource("demo/id.properties");
~~~

All three calls can refer to the resource corresponding to package `demo`, **but the lookup path and module semantics of Class.getResource may differ**. This snippet is a fragment and is not part of the complete example in the previous section.

Do not prepend a `/` to the name passed to `ClassLoader.getResource` and then blame parent/child order for returning `null`; the issue may simply be **a resource name violating the convention**.

**With named modules (Java 9+)**, lookups for non-`.class` resources are also affected by module encapsulation/`opens`; loader order is not the only factor. With `Class.getResource`, the module defining the class can determine how and where the resource is accessible. The Java 17 example in Section 3 uses a URL classpath/unnamed module to clarify delegation independently of JPMS.

## 5. getResources(): How Important Is Aggregation Order?

Many frameworks do not look for **a single** file, but instead iterate over **all** resources with the same name. Examples include:

- `META-INF/services/com.acme.api.Plugin` metadata for Java's SPI mechanism.
- Multiple configuration files with the same name provided by both the host and plugins.
- Resources for discovery, routing, template registries, or library configuration.

In the default `ClassLoader`, `getResources` enumerates the parent first and then the child's local entries. If classes are prioritized from the child while the parent's SPI resource appears first, the code may discover a provider that does not match the loaded class/API version or merge configurations in an unexpected order.

**Three distinct policies must be clearly defined:**

1. **First-wins**: takes the first resource (typically via `getResource`); child-first or parent-first determines the outcome.
2. **Last-wins**: reads every resource and overwrites values in order; a reversed order can cause the last entry to take precedence.
3. **Merge-all**: requires all resources, though deduplication or handling name/provider conflicts may be necessary.

Do not equate `getResources` with looking up a single resource. A custom implementation may sometimes legitimately return entries from both parent and child, but it must maintain **a consistent and documented ordering rule**. With `ServiceLoader`, there are also requirements on the provider type and the ability to load the provider class using the selected loader; changing resource order **does not guarantee** that ServiceLoader can cast a provider if the API interface has been defined redundantly across loaders.

### Metadata Conflict Example

~~~text
parent:
  com/acme/api/Codec.class
  META-INF/services/com.acme.api.Codec  → com.acme.api.DefaultCodec

child:
  com/acme/plugin/FastCodec.class
  META-INF/services/com.acme.api.Codec  → com.acme.plugin.FastCodec
~~~

In a valid design, **the Codec interface is shared** from the parent; the FastCodec class is defined by the plugin loader yet implements that exact interface. SPI resources can be aggregated via `getResources` so that both providers can be discovered. You should not redefine `Codec` in the child and expect reversing the `getResources` order to fix a `ClassCastException`.

## 6. When Should Child Resources Be Prioritized and When Should Parent Resources Be Kept?

Do not enforce child-first for everything. A practical policy typically establishes boundaries:

| Class/Resource Group | Recommended Rule | Rationale |
| --- | --- | --- |
| Java platform and shared host APIs | Parent-first | Preserves type identity/API contracts and platform behavior. |
| Plugin-specific implementations | Child-first if isolation is needed | Allows the plugin to use its own implementation version. |
| Resources bundled with plugin implementations | Correspondingly child-first | Prevents the plugin from reading the host's config/schema/templates. |
| Host configuration resources intentionally overridden by plugins | Explicit agreement on first-wins or merge | May require parent-first, child-first, or merge depending on business goals. |
| `META-INF/services/...` | Usually enumerate multiple resources | Preserves complete provider discovery and ensures shared APIs. |

The policy can be implemented by **namespace/package/resource prefix** or by an explicit mapping between plugins and resources. What matters is defining **who owns** each path and **what happens if both sides share the same name**.

For a custom-written child-first loader, the methods that typically need to be considered as a related set are:

~~~text
loadClass / findClass
getResource / findResource
getResources / findResources
getResourceAsStream
~~~

`getResourceAsStream` in the standard implementation is based on `getResource`; a separate override is usually unnecessary if opening a stream from the URL already meets your needs. However, if a custom loader stores resources in memory, on a non-standard filesystem, or performs special stream handling, you must check that the stream path follows the same policy as well.

## 7. Common Implementation Pitfalls

### 7.1. Changing Only loadClass and Forgetting getResource

**Symptom:** `MyPlugin.class.getClassLoader()` is the child, yet `loader.getResource("plugin/config.yml")` returns a URL inside the parent JAR. The plugin may read a configuration from the wrong version.

**Fix:** Unify the policy for implementation-bound resources. Print the selected URL and the class's defining loader when debugging.

### 7.2. Child-First getResource with Parent-First getResources

**Symptom:** Reading a single file returns the child copy, while a framework using enumeration loads the parent's provider/config first.

**Fix:** Add tests for both `getResource` and the ordering of `getResources` for critical resource names. For resources that need merging, inspect the full list rather than only the first element.

### 7.3. Overriding loadClass in a Way That Breaks Parent Delegation

**Symptom:** `ClassCastException` between two copies of the same API name, `LinkageError`, or JDK classes being blocked from lookup.

**Fix:** Keep parent-first for API/JDK classes and apply child-first only to controlled implementation packages; use `findLoadedClass`, `getClassLoadingLock`, and `resolveClass` according to the contract.

### 7.4. Assuming the Returned URL Is a File on Disk

A resource may have a `jar:`, `jrt:`, or custom-loader URL scheme. Do not force `Paths.get(url.toURI())` on every URL. You should generally use `url.openStream()` or `getResourceAsStream` when you only need to read bytes. With a `jar:` URL, the path to an entry inside a JAR is not a standalone file on the default filesystem.

### 7.5. Confusing Relative and Absolute Names

`ClassLoader.getResource("demo/id.properties")` and `Marker.class.getResource("id.properties")` may refer to the same logical resource name, whereas `ClassLoader.getResource("/demo/id.properties")` violates the standard convention. Always verify the path inside the JAR using an appropriate tool.

### 7.6. Module Access Affecting Resource Lookup

With named modules, resources enclosed in an unopened package may not be returned through external APIs, even if the appropriate class loader sees that module. Do not solve every `null` by flipping parent/child order; check module ownership and `opens`/encapsulation when needed.

### 7.7. Modifying the Global TCCL Without Lifecycle Management

`Thread.currentThread().getContextClassLoader()` is used by many frameworks to select a loader for resources/providers. Changing the TCCL without restoring it in `finally` can cause results to vary by thread and retain old plugin loaders after a redeploy. Use the TCCL deliberately and manage its lifecycle.

## 8. Investigation Procedure When the Class Is Right but the Resource Is Wrong

1. **Identify the target class** and print `Class.getClassLoader()` to find the actual defining loader. Do not assume the loader calling `loadClass` defined the class itself.
2. **Determine the exact resource name**: whether the path is absolute or relative, whether it includes a package prefix, and whether it has a leading `/`.
3. **Print the first URL** from `loader.getResource(name)` and iterate through **all URLs in order** from `loader.getResources(name)`.
4. **Compare where the class is defined** with where the resource is selected from: a child class paired with a parent config is a suspicious sign.
5. **Check which lookup path the resource is accessed through**: `SomeClass.getResource`, `ClassLoader.getResource`, `ServiceLoader`, or the TCCL may differ.
6. **Check the parent-first/child-first policy** for the class name and resource name, along with the fallback when the child does not have the resource.
7. **Check module/resource encapsulation** if named modules are involved.
8. **Lock in the desired behavior with a small test** using two identically named class/resource versions, verifying both `getResource` and `getResources` like the Java 17 program above.

A short diagnostic snippet (fragment, assuming `type` and `resourceName` are available):

~~~java
ClassLoader loader = type.getClassLoader();
System.out.println("Defining loader: " + loader);

URL first = loader.getResource(resourceName);
System.out.println("First resource: " + first);

Enumeration<URL> all = loader.getResources(resourceName);
while (all.hasMoreElements()) {
    System.out.println("Candidate: " + all.nextElement());
}
~~~

The fragment above requires importing `java.net.URL`, `java.util.Enumeration`, handling `IOException`, and assumes `loader` is non-null. When `type` is defined by the bootstrap loader (`getClassLoader() == null`), you must use an appropriate resource lookup API instead of invoking methods on null.

## 9. Self-Check

**Question 1.** A custom loader loads `plugin.Engine` using child-first, while keeping the default `getResource`. Both parent and child contain `plugin/settings.properties`. Which resource is usually selected?

**Answer:** Parent-first resource lookup usually selects **the parent's copy**; the result may not match the `Engine` implementation from the child.

**Question 2.** Why is overriding `getResource` not enough if a framework uses `getResources`?

**Answer:** `getResources` has its own enumeration rules. A framework may see the parent's entry first even though `getResource` prioritizes the child.

**Question 3.** Should all `java.*` classes and host API interfaces be loaded child-first to stay synchronized with the plugin?

**Answer:** No. Keeping parent-first for platform and shared APIs helps avoid two different type definitions. Apply scoped child-first only to implementations and resources belonging to the plugin.

**Question 4.** Which name is appropriate for `ClassLoader.getResource` if the file is located at `demo/id.properties`?

**Answer:** `"demo/id.properties"`, without a leading `/`.

**Question 5.** For `META-INF/services`, is reversing `getResources` to child-first alone enough to fix all `ServiceLoader` errors?

**Answer:** No. You must ensure that the discovered providers **implement the exact same API interface** defined by the loader expected by the consumer; module/discovery and provider loading capability must also be considered.

## Key Takeaways

**Class loading and resource lookup are two distinct lookup paths that are semantically linked.** With parent-first, both classes and resources default to prioritizing the parent; with selective child-first, implementation-bound resources must be coordinated consistently across `getResource`, `getResources`, and related stream paths. Clearly define **which classes belong to the parent or child**, **which resources belong to that component**, and **the first-wins/merge-all ordering** to avoid combining code from one version with configuration/metadata from another.

**Official references:**

- Java SE 17 API, `ClassLoader`, methods `loadClass`, `getResource`, `getResources`, `findResource`, `findResources`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `Class.getResource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
