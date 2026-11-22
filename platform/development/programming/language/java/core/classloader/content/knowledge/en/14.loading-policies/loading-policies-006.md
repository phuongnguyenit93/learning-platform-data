# Preventing Classes and Resources from Using Different Priority Orders

In Java, a **custom class loader** can select **classes (`.class`) from one source**, while returning **resources (`.properties`, `.xml`, `META-INF/services/...`, templates, etc.) from another source** if the `loadClass` policy and the `getResource`/`getResources` policy are inconsistent.

A classic example: an application uses **child-first for `demo.Feature`** to run a plugin version, but keeps the default **parent-first** `ClassLoader.getResource`. The result can be:

```text
demo.Feature             -> plugin/child (version B)
demo/config.properties   -> application/parent (version A)
```

Code from version B reads configuration A, even though the two items appear to be packaged together in the plugin. This is a type of **class/resource provenance mismatch** bug: hard to detect because both loading the class and reading the file may succeed, yet the program runs with incorrect logic.

**Goal of this article:** Design and test a consistent priority policy across class loading, single-resource lookup, and **all**-resource lookup; while also understanding when to intentionally share parent resources instead of applying child-first to everything.

## 1. Classes and Resources Use Different APIs

A class loader has multiple independent lookup paths:

| Operation | Typical API | Input Name | Result |
|---|---|---|---|
| Load a class | `loadClass("demo.Feature")` | **Binary name** with `.` | `Class<?>` |
| Find where bytecode is defined | `findClass("demo.Feature")` | Binary name | `Class<?>` provided by the loader itself if available |
| Find a single resource | `getResource("demo/config.properties")` | **Resource name** with `/` | `URL` or `null` |
| Find all resources with the same name | `getResources("META-INF/services/spi.Plugin")` | Resource name | `Enumeration<URL>` |
| Read content | `getResourceAsStream(name)` | Resource name | `InputStream` or `null` |

The class name `demo.Feature` and the resource path `demo/Feature.class` **are not the same kind of input**. Do not pass `demo/Feature.class` to `loadClass` and do not pass `demo.Feature` to `getResource` expecting the same meaning.

Commonly overridden/extension methods:

- `loadClass(String, boolean)`: coordinates class loading, caching, delegation, and resolution.
- `findClass(String)`: finds/defines a class from the loader's own sources.
- `getResource(String)`: provides **one** resource URL.
- `getResources(String)`: provides **multiple** resource URLs, where order can matter.
- `findResource(String)` and `findResources(String)`: find resources in the loader's own sources.
- `getResourceAsStream(String)`: reads a resource as a stream; on `ClassLoader`, the default implementation is based on the resource lookup path.

**The problem:** Overriding `loadClass` does not automatically change the order of `getResource` and `getResources`. Overriding `findClass` also does not create resource lookup rules.

## 2. Default Policy: Parent-First for Both Classes and Resources

With the standard `ClassLoader` implementation, the general model is:

```text
loadClass("demo.Feature")
    1. findLoadedClass
    2. parent.loadClass or bootstrap
    3. current loader's findClass when parent cannot load it

getResource("demo/config.properties")
    1. parent.getResource or bootstrap resource lookup
    2. current loader's findResource if parent does not have it

getResources("demo/config.properties")
    1. parent/bootstrap resources
    2. current loader's resources (findResources)
```

Key point: **`getResource` selects only one URL**, whereas **`getResources` returns multiple URLs**. With the default loader, the parent takes precedence in both, but the list API can also contain two entries with the same name from different sources.

For example, both parent and child provide `demo/config.properties`:

```text
parent/classes/demo/config.properties  -> mode=parent
child/classes/demo/config.properties   -> mode=child

getResource(name)        -> parent's URL
getResources(name)       -> [parent URL, child URL]
```

This is the typical order when both are within the lookup scope of the loaders under the configuration above. Do not infer that **every custom loader** or **every module/JAR runtime** must preserve this exact order: implementations and module/resource restrictions can change the actual result set.

### Why Does a Conflict Appear When Choosing Child-First?

A plugin loader may intentionally override `loadClass`:

```text
loadClass("demo.Feature")
    1. child.findClass
    2. parent.loadClass if child does not have it
```

But if it does not override the resource methods:

```text
getResource("demo/config.properties")
    1. parent.getResource
    2. child.findResource
```

When both parent and child contain the class and the resource, the class will come from the **child**, while the resource will come from the **parent**. Declaring a child-first class policy **does not guarantee** that all accompanying resources are also child-first.

## 3. Provenance Model Must Consider Namespace and Resource Type

A sound policy typically separates three scopes:

| Scope | Class should come from | Resource should come from | Why? |
|---|---|---|---|
| **Platform/JDK classes** | Bootstrap/platform/parent | Platform resources via appropriate APIs | Preserves type identity and runtime rules |
| **Shared contracts** such as `spi.Plugin` | Parent/shared loader | Shared schemas/default configs by common design | Host and plugin must share one runtime interface |
| **Private implementation** such as `plugins.alpha.*` | Plugin/child (when isolation is required) | Resources packaged with the plugin version first, if that is the contract | Prevents version B implementation from reading version A resources |

Not **all** resources in the same package need to be child-first. For example, an application-level organizational configuration may be designed **intentionally to be read from the parent** so multiple plugins share it. The goal is **well-designed and testable rules**, not "every lookup must follow the same global order."

Similarly, `META-INF/services/...` is usually a **list of contributions from multiple JARs**, not a single resource where only one copy should be chosen. When handling this type, consider `getResources` and the `ServiceLoader` contract instead of only changing `getResource`.

## 4. Java 17+ Example Demonstrating the Bug and Policy Alignment

We build two versions of `demo.Feature` with **the same binary name but different contents**, and two `demo/label.txt` files. The app loader sees the parent copy; the child loader has its own child directory.

Then we compare two loaders:

- **`ChildFirstClassOnly`**: child-first specifically for `demo.Feature` while keeping parent-first resource lookup.
- **`CoherentLoader`**: keeps the same class policy, while also prioritizing the child for `demo/label.txt` in both `getResource` and `getResources`.

Structure:

```text
resource-order-demo/
├── src-parent/demo/Feature.java
├── src-child/demo/Feature.java
├── src-app/app/OrderDemo.java
└── out/
    ├── parent/demo/label.txt
    ├── child/demo/label.txt
    └── app/
```

### 4.1. Parent Class Version

File **`src-parent/demo/Feature.java`**:

```java
package demo;

public final class Feature {
    public static String origin() {
        return "parent-class";
    }
}
```

### 4.2. Child Class Version

File **`src-child/demo/Feature.java`**:

```java
package demo;

public final class Feature {
    public static String origin() {
        return "child-class";
    }
}
```

The two classes have the same binary name but **will be defined by different loaders**, so they are **two distinct runtime classes**. The demo does not attempt to cast those two classes to the same type; it uses reflection to invoke a public method returning `String` (a shared platform type).

### 4.3. Application Checking Classes and Resources

File **`src-app/app/OrderDemo.java`**:

```java
package app;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class OrderDemo {
    private static final String CLASS_NAME = "demo.Feature";
    private static final String RESOURCE_NAME = "demo/label.txt";

    static class ChildFirstClassOnly extends URLClassLoader {
        ChildFirstClassOnly(URL[] urls, ClassLoader parent) {
            super(urls, Objects.requireNonNull(parent));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!CLASS_NAME.equals(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    try {
                        result = findClass(name);
                    } catch (ClassNotFoundException missing) {
                        result = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    static final class CoherentLoader extends ChildFirstClassOnly {
        CoherentLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        public URL getResource(String name) {
            if (RESOURCE_NAME.equals(name)) {
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
            if (!RESOURCE_NAME.equals(name)) {
                return super.getResources(name);
            }

            Map<String, URL> ordered = new LinkedHashMap<>();
            Enumeration<URL> own = findResources(name);
            while (own.hasMoreElements()) {
                URL next = own.nextElement();
                ordered.putIfAbsent(next.toExternalForm(), next);
            }

            Enumeration<URL> parent = getParent().getResources(name);
            while (parent.hasMoreElements()) {
                URL next = parent.nextElement();
                ordered.putIfAbsent(next.toExternalForm(), next);
            }
            return Collections.enumeration(ordered.values());
        }
    }

    static String classValue(ClassLoader loader) throws Exception {
        Class<?> type = Class.forName(CLASS_NAME, true, loader);
        return (String) type.getMethod("origin").invoke(null);
    }

    static String resourceValue(URL url) throws IOException {
        try (InputStream stream = url.openStream()) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        URL childRoot = Path.of(args[0]).toUri().toURL();
        ClassLoader app = OrderDemo.class.getClassLoader();

        try (var naive = new ChildFirstClassOnly(
                    new URL[]{childRoot}, app);
             var aligned = new CoherentLoader(
                    new URL[]{childRoot}, app)) {

            System.out.println("Naive class: " + classValue(naive));
            System.out.println("Naive resource: "
                    + resourceValue(
                            naive.getResource(RESOURCE_NAME)));

            System.out.println("Aligned class: " + classValue(aligned));
            System.out.println("Aligned resource: "
                    + resourceValue(
                            aligned.getResource(RESOURCE_NAME)));

            List<String> items = new ArrayList<>();
            Enumeration<URL> urls =
                    aligned.getResources(RESOURCE_NAME);
            while (urls.hasMoreElements()) {
                items.add(resourceValue(urls.nextElement()));
            }
            System.out.println("Aligned all resources: "
                    + String.join(",", items));
        }
    }
}
```

This is a complete program in Java 17+. A few details:

- `URLClassLoader` already provides `findClass`, `findResource`, and `findResources` for URL directories/JARs. We only change the selection order intentionally, without writing a custom bytecode parser.
- `ChildFirstClassOnly` is child-first **only for `demo.Feature`**, while other classes (especially Java/JDK classes) remain parent-first.
- `getClassLoadingLock` and `findLoadedClass` ensure concurrent or repeated lookup requests do not accidentally create duplicate classes within a single loader.
- `CoherentLoader.getResource` prioritizes the child's `findResource` for `demo/label.txt` before falling back.
- `CoherentLoader.getResources` returns child URLs first and parent URLs second, with **deduplication by `toExternalForm()` string** within the demo's scope. This is not a guarantee that all URLs representing the same physical resource are normalized/canonicalized identically.
- `Objects.requireNonNull(parent)` guarantees `getParent()` is always non-`null` in the demo. A general-purpose loader needs to consider the bootstrap parent case and Java platform resource lookups as well.
- When the code calls `Class.forName(CLASS_NAME, true, loader)`, the loader is **passed explicitly**; thus we control looking up the exact class from the namespace we want to test.

### 4.4. Compiling and Running

Bash (Linux/macOS/Git Bash), from the `resource-order-demo` directory:

```bash
mkdir -p out/parent/demo out/child/demo out/app

printf 'parent-resource\n' > out/parent/demo/label.txt
printf 'child-resource\n' > out/child/demo/label.txt

javac --release 17 -d out/parent src-parent/demo/Feature.java
javac --release 17 -d out/child src-child/demo/Feature.java
javac --release 17 -d out/app src-app/app/OrderDemo.java

java -cp "out/app:out/parent" app.OrderDemo out/child
```

On Windows PowerShell, create the directories and resources as follows:

```powershell
New-Item -ItemType Directory -Force -Path out/parent/demo, out/child/demo, out/app | Out-Null
[System.IO.File]::WriteAllText("out/parent/demo/label.txt", "parent-resource" + [Environment]::NewLine)
[System.IO.File]::WriteAllText("out/child/demo/label.txt", "child-resource" + [Environment]::NewLine)
javac --release 17 -d out/parent src-parent/demo/Feature.java
javac --release 17 -d out/child src-child/demo/Feature.java
javac --release 17 -d out/app src-app/app/OrderDemo.java
java -cp "out/app;out/parent" app.OrderDemo out/child
```

Note: Linux/macOS uses `:` to separate `java -cp` entries; Windows uses `;`. This is a command-line classpath rule and does not change the resource name `demo/label.txt`.

**Verified output** compiled with `javac --release 17` and run on JDK 21:

```text
Naive class: child-class
Naive resource: parent-resource
Aligned class: child-class
Aligned resource: child-resource
Aligned all resources: child-resource,parent-resource
```

### 4.5. Interpreting the Results

**Before fixing the resource policy:**

```text
ChildFirstClassOnly
  loadClass("demo.Feature")           -> child  -> "child-class"
  getResource("demo/label.txt")       -> parent -> "parent-resource"
```

The code is running the child version of the class while reading the parent version of the resource. If `label.txt` were replaced by a template, schema, or database mapping from two library versions, the mismatch could cause the program to behave incorrectly without throwing an exception.

**After aligning the policy:**

```text
CoherentLoader
  loadClass("demo.Feature")           -> child  -> "child-class"
  getResource("demo/label.txt")       -> child  -> "child-resource"
  getResources("demo/label.txt")      -> [child, parent]
```

For resources marked as **plugin-private/versioned**, child-first is the desired policy. For other **shared/global** resources, this loader still uses the default parent-first policy.

**Scope limitations:** The demo illustrates two directories and one class/one resource to make the issue clear. A production system needs rules for **entire namespaces**, dependencies, `META-INF/services`, package/module constraints, URL/JAR providers, and loader lifecycles; do not copy a single-name equality check into a large system.

## 5. Why Fixing getResource Alone Is Not Enough

There are at least three common reading paths:

```java
URL one = loader.getResource("demo/label.txt");

Enumeration<URL> all =
        loader.getResources("demo/label.txt");

try (InputStream stream =
        loader.getResourceAsStream("demo/label.txt")) {
    // Read bytes if stream is non-null.
}
```

This is an illustrative snippet placed inside a method with `loader` already declared and exception handling as needed.

If you only override `getResource` without overriding `getResources`:

- Single-item reads may see the child first.
- APIs that scan all URLs can still list the **parent first**.
- A framework using `getResources` may pick configuration A instead of B, producing different results from code calling `getResource` directly.

Conversely, if you only override `getResources` and omit `getResource`, single-file reads may remain parent-first. Never assume that one default method is always implemented in terms of the other.

`getResourceAsStream` on `ClassLoader` normally opens a stream via the corresponding loader's `getResource`; if a custom subclass overrides `getResourceAsStream`, you must ensure the new logic does not diverge from the chosen policy.

You must verify **which actual API** the framework calls. A framework might use `Class.getResource`, `ClassLoader.getResource`, `Thread.currentThread().getContextClassLoader().getResources`, or a custom resource resolver with its own ordering.

## 6. Watch Out: Class.getResource Differs from ClassLoader.getResource

The following two calls often point to the same resource but interpret names differently:

```java
URL fromClass = demo.Feature.class.getResource("label.txt");

URL fromLoader = demo.Feature.class.getClassLoader()
        .getResource("demo/label.txt");
```

- `Class.getResource("label.txt")` uses a name relative to **the class's package**: `demo/label.txt`.
- `Class.getResource("/demo/label.txt")` uses a name from the namespace root (the leading `/` is stripped during lookup).
- `ClassLoader.getResource("demo/label.txt")` requires a resource name with `/` separating packages, **without a leading `/`**.

If the caller `demo.Feature` is defined in the plugin loader, `Feature.class.getClassLoader()` returns that defining loader. Therefore, a resource lookup based on **the relevant class itself** is often better than arbitrarily using `ClassLoader.getSystemResource`.

However, with **named modules**, resource encapsulation also affects whether a resource can be found. Some resources in a module's package are not exposed via `ClassLoader.getResource` if the package is not opened according to API rules. `Class.getResource` and `Module.getResourceAsStream` also have specific contracts. Do not conclude that a `null` result is always due to **priority order**; it may be a module access issue.

### Class Resources Also Need Consideration

A deeper mismatch occurs when `loadClass("demo.Feature")` defines the class from the child, while `getResource("demo/Feature.class")` returns **the parent's bytecode**. If an inspection tool, scanner, or bytecode transformer uses resource lookup to fetch the class file and assumes those bytes belong to the loaded runtime class, it may analyze the wrong version.

Do not treat `getResource("...class")` as absolute proof of the bytecode source used: a custom loader may decrypt, generate, or transform bytes before `defineClass`; the resource URL may not reflect these steps. If strict synchronization is required, design a dedicated **provenance API** and retain a manifest/hash/metadata of the bytes the loader actually defined.

## 7. Do Not Blindly Reorder Every Resource

There are two types of resources that must be handled differently:

### 7.1. **Exclusive** or Versioned Resources

Examples:

```text
plugins/acme/schema.json
plugins/acme/templates/view.html
plugins/acme/config/default.properties
```

If these files are directly tied to the implementation of a child-first plugin, prioritizing **child** before parent may be appropriate. When a resource is absent in the child, falling back to the parent may be allowed if the contract permits; if fallback is considered dangerous, **fail fast** to avoid accidentally using a schema from another version.

This is a policy decision:

| Resource missing in child | Possible behavior | When appropriate |
|---|---|---|
| Valid shared default exists | Fallback to parent | Compatibility/default settings are explicitly designed |
| Same version strictly required | No fallback, throw error | Schemas, migration scripts, or templates that must match implementation |
| Multiple override layers exist | Use ordered overlay | Configuration systems with clear precedence |
| Multiple contributors exist | Return full `getResources` | SPIs, plugin registries, extension descriptors |

Do not rely on "first match wins" if the contract actually requires **merging multiple sources**.

### 7.2. **Aggregation / Multi-Source** Resources

Examples:

```text
META-INF/services/com.example.spi.Plugin
META-INF/spring.factories                 (certain ecosystems/versions)
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

These files typically describe contributions from **multiple JARs**. If `getResources` is changed to return only **one** child resource, the framework may lose all parent providers or configurations.

For metadata aggregation, a sound policy can be:

1. Find all resources from permitted sources.
2. Specify ordering if the framework has a relevant contract.
3. Ensure no valid entries are dropped.
4. Deduplicate only when the API/framework's definition of duplication is known; **duplicate URLs** do not always equate to **duplicate content/providers**.
5. Test startup, discovery, caching, and reloading with multiple JARs.

**Specifically for ServiceLoader:** `ServiceLoader.load(service)` in Java SE 17 uses the TCCL to discover providers; `ServiceLoader.load(service, loader)` uses an explicit loader. In classpath mode, provider configurations reside under `META-INF/services/<binary-name-of-service>`. Incorrect `getResources` behavior can cause `ServiceLoader` to miss descriptors or pick an unwanted provider. The service type and provider class must be compatible within **the same runtime type namespace**.

## 8. Parent-First for Shared APIs, Child-First for Private Implementations

With plugins:

```text
ApplicationClassLoader
    ├── shared.api.Plugin
    └── shared.api.Message
           ^
           | parent delegation
           |
PluginClassLoader
    ├── plugins.acme.AcmePlugin
    ├── plugins.acme.schema.json
    └── META-INF/services/shared.api.Plugin
```

A typical design:

- **`shared.api.*`**: always prioritize parent so the app and plugin use the same `Class<?>` for the contract.
- **`plugins.acme.*`**: may prioritize child for the implementation if isolation is genuinely needed.
- **`plugins/acme/...` resources**: if versioned with the implementation, prioritize the plugin source or read via the associated class.
- **`META-INF/services/...`**: may need to aggregate descriptors from both parent and child, rather than simply taking the first resource.
- **JDK/platform classes**: never redefine them, to avoid breaking type identity and JVM protection rules.

If a plugin redefines `shared.api.Plugin` using child-first, application code will not necessarily be able to cast the plugin object to the interface of the same name. At that point, the error is no longer just a resource mismatch but a **class identity mismatch**.

### A Policy Map Should Be Written Explicitly

Instead of vague statements like "child-first for everything," build a matrix:

| Group | Class lookup | Single resource lookup | Multiple resource lookup |
|---|---|---|---|
| `java.*`, runtime/platform | Parent/bootstrap | Per platform/module APIs | Per platform/module APIs |
| `shared.api.*` | Parent-first | Shared resources from parent | Per shared contract |
| `plugins.alpha.*` | Child-first (if needed) | Child-first for corresponding resources | Child-first then parent, or child-only |
| `META-INF/services/*` | No class with this name | Not a complete discovery mechanism | Aggregate appropriate entries |
| `app/config/global.properties` | Not applicable | Parent-first, or explicit config source | Per application contract |

This table is only a **sample design**, not rules automatically enforced by the JVM. Other namespaces should be classified based on their actual responsibilities.

## 9. Safer Production Custom Loader Structure

You can centralize the policy into a name-based classifier (illustrated in pseudocode):

```text
classPolicy(binaryName):
    if JDK or shared contract:
        return PARENT_FIRST
    if plugin-private package:
        return CHILD_FIRST
    return PARENT_FIRST

resourcePolicy(resourceName):
    if plugin-private resource:
        return CHILD_FIRST
    if service/provider descriptor:
        return AGGREGATE
    return PARENT_FIRST
```

Then all three loading paths query the classifier:

```text
loadClass(name):
    determine classPolicy(name)
    check findLoadedClass, lock by name, parent/child
    resolve when needed

getResource(name):
    determine resourcePolicy(name)
    return first URL matching policy or null

getResources(name):
    determine resourcePolicy(name)
    merge enumeration according to contract
```

Even with a unified classifier, **never force every resource name into a binary class name**. Classes and resources have different naming conventions; one class namespace may be accompanied by many kinds of resources that do not map 1:1.

Points to check when implementing your own loader:

1. `loadClass` still checks `findLoadedClass` and uses `getClassLoadingLock(name)` to prevent races/duplicate definitions.
2. Do not catch or swallow `VerifyError`, `LinkageError`, `ClassFormatError`, or `SecurityException` as if they were `ClassNotFoundException` to silently fall back to another version.
3. `getResources` honors `IOException` and the enumeration contract; do not produce a truncated list if a library needs all descriptors.
4. Maintain deterministic ordering under stable inputs, and document when ordering is governed by classpath order, module/provider semantics, or plugin priority.
5. Close streams, JAR handles, and resource-specific file systems according to lifecycle.
6. Do not allow untrusted path/resource names to use `../` or out-of-scope URLs to escape the plugin's resource root.
7. Do not turn a class loader into a security sandbox for untrusted plugins: JVM class loading and OS isolation are separate concerns.
8. Design unloading/reloading without retaining unbounded references through caches, thread context loaders, or provider instances.

## 10. TCCL Can Change the Resource Source at the Call Site

A program might use:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

URL url = tccl == null
        ? null
        : tccl.getResource("plugins/acme/config.properties");
```

This is an illustrative snippet inside a method with `java.net.URL` imported; if the TCCL is the child, resource lookup can follow the child's policy. However:

```java
URL url = SomeLibrary.class.getClassLoader()
        .getResource("plugins/acme/config.properties");
```

uses **the defining loader of `SomeLibrary`**, which may be the parent and have a different policy. The same resource name does not guarantee the same result if lookup starts from **two different loaders**.

When temporarily changing the TCCL, always restore it:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Call framework/SPI whose contract uses TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
```

This is an illustrative snippet with `pluginLoader` already available. In thread pools, failing to restore the TCCL can cause subsequent requests to read the previous request's resources/plugin providers; at the same time, the TCCL holds a strong reference to the old loader, making the plugin hard to unload.

**Important:** `Class.forName(String)` **does not automatically use the TCCL**; the single-argument overload uses the calling class's defining loader. Do not try to fix a resource issue by changing the TCCL and assuming all class lookups will automatically switch to the child loader.

## 11. Manifest Class-Path, URLClassLoader, and JAR Resources

If the child has a URL pointing to `plugin.jar`, `URLClassLoader` can find `.class` files and resources inside that JAR. The JAR's manifest `Class-Path` can expand dependent URLs according to the JAR specification; this broadens the set of searchable sources but **does not automatically change the parent/child policy** you implemented.

For example:

```text
app.jar                       (parent)
  demo/Feature.class
  demo/label.txt

plugin.jar                    (child URLClassLoader)
  demo/Feature.class
  demo/label.txt
```

If the class policy is child-first while the resource policy is parent-first, the same mismatch as in the demo still occurs even though the source is a JAR instead of a directory.

JAR resources typically have URLs in the form:

```text
jar:file:/opt/plugins/plugin.jar!/demo/label.txt
```

This URL points to **an entry inside an archive**, not a standalone `java.io.File`. Use `URL.openStream()`/`getResourceAsStream` to read it instead of `new File(url.toURI())`. Avoid parsing with `substring` around `!/` if the loader/framework can return nested JAR URLs or special protocols.

**Classpath order is not the same concept as loader delegation order.** A `URLClassLoader` can have multiple JARs in URL order, but before checking those URLs, the default `getResource` may still ask the parent to search first. Adjusting the order of `URL[]` in the child is not enough for the child to beat the parent's resource when the parent has the same name.

## 12. The Module System and Limits of Order Alignment

On Java 9+, **JPMS named modules** have module readability, exports/opens, and resource encapsulation policies. Therefore:

- A class may exist in a module yet be unusable at the call site due to module/access rules.
- `ClassLoader.getResource` may not expose non-`.class` resources belonging to a package in a named module if the package has not been opened with `opens` per API rules.
- `Class.getResource`, `Module.getResourceAsStream`, and `ClassLoader.getResource` have contract differences; a `null` URL is not enough to conclude it was solely due to priority.
- Service discovery for named modules may rely on `provides ... with ...` and module layers, not necessarily `META-INF/services`.
- A custom loader does not automatically resolve module readability/exports/opens if code already violates those constraints.

When a system uses JPMS, decide whether classes and resources should be accessed **by module ownership** instead of assuming a simple parent/child URL search chain. For code tightly bound to a module, `Module.getResourceAsStream` may be a better choice if the access contract permits.

## 13. Testing to Catch Mismatches Before Production

### Tests Must Check **Both Value and Source**

Simply asserting:

```java
assertNotNull(loader.getResource("demo/label.txt"));
```

is not enough. The parent may return a resource with the same name, making the test pass while using the wrong version.

Verify:

- Whether `loadedClass.getClassLoader()` is the expected defining loader.
- Whether bytecode/class behavior belongs to the right version (e.g., the method returns `child-class`).
- Whether the resource URL comes from the expected archive/directory/module.
- Whether **the content** of the resource has a version/marker consistent with the implementation.
- Whether `getResource` picks the right single source; whether `getResources` has the right order and URL set per the contract.
- Whether the caller actually uses `Class.getResource`, an explicit loader, or the TCCL.
- Whether missing child resources fall back to the parent or fail fast.
- When two JARs share the same resource name or provider descriptor, how many copies are processed?

**Note:** Inferring class origin from `getResource("...class")` is only a heuristic. In a custom loader with transformations or in-memory bytecode, the `.class` source returned by `getResource` may not be the bytes passed to `defineClass`. If strong proof is needed, record provenance/hashes at class definition time.

### Useful Test Matrix

| Class in parent? | Class in child? | Resource in parent? | Resource in child? | Expected |
|---|---|---|---|---|
| Yes | Yes | Yes | Yes | Child-class + child-resource under private child-first policy |
| Yes | No | Yes | No | Fallback to parent if permitted |
| No | Yes | No | Yes | Child provides both |
| Yes | Yes | Yes | No | Fail-fast or fallback per contract, never silent |
| Yes | Yes | No | Yes | Child resource; class per defined policy |
| Multiple provider JARs | Multiple provider classes | Multiple descriptors | Multiple descriptors | `getResources`/SPI drops no valid contributions |

Do not test only cases where child and parent have non-overlapping names—in those cases two different policies can look identical. **You must create a fixture with intentionally colliding binary names and resource names**, like the demo in section 4.

## 14. Symptoms in Real-World Applications

### A. Plugin B's Class with Version A's Configuration

Symptom: a new plugin feature is loaded, yet the application uses an old schema, an old enum mapping, or an outdated template.

Check: `Class.getClassLoader`, where the class was defined, the `getResource` URL, the resource content, and the `getResources` order. If using child-first classes with parent-first resources, fix the policy or use a resource-reading API tied to the corresponding class.

### B. SPI Provider Not Discovered Even Though the Class Exists

Symptom: `Class.forName("plugins.X", false, pluginLoader)` works, yet `ServiceLoader.load(Service.class, pluginLoader)` fails to find the provider.

Check: whether the `META-INF/services/<service-binary-name>` file is packaged, whether `getResources` returns all descriptors, whether the provider type uses **the exact same shared service interface**, and whether the module/TCCL context is appropriate.

### C. Framework Reads a Different Configuration Than the Application Code

Symptom: `loader.getResource(name)` returns the child URL, but the framework still reads the parent resource.

Check: does the framework use `getResources`? Does it use the system loader, TCCL, `Class.getResource`, or another module resource API? Did it cache the resource list or configuration from an earlier startup?

### D. "Works in the IDE, Fails When Packaged as a JAR"

The IDE may place resource and class directories on the classpath in a different order than an executable JAR/container. When JAR deployment adds parent libraries or a plugin loader, colliding resource names can start causing shadowing.

Inspect build output/JAR entries with `jar --list --file ...` and compare the actual runtime loader/URLs, rather than relying solely on source directories.

### E. Hot Reload Still Uses Old Resources

If a new-generation loader loads class B while a singleton in the parent has cached URL/resource A, swapping the loader does not automatically invalidate that cache. Design cache keys/lifecycles per plugin generation or clear old caches.

## 15. Design Mistakes to Avoid

1. **Overriding `loadClass` as child-first for all classes** without keeping shared APIs in the parent: leads to duplicate class identities and `ClassCastException`.
2. **Overriding only `getResource`**, forgetting `getResources`: aggregation frameworks still use the old order.
3. **Overriding `getResources` to return only the first URL**, dropping service descriptors and plugin contributions.
4. **Aligning by switching all resources to child-first** regardless of shared/global configs or module rules.
5. **Using `getResource("...class")` as absolute proof of loaded bytes** even when code uses transformations/custom sources.
6. **Catching and masking `LinkageError` or `VerifyError` as if a resource were simply missing**; distinguish class loading errors from resource mismatches.
7. **Confusing resource names with class names**; `getResource("a.B")` and `loadClass("a/B.class")` are not equivalent calls.
8. **Reading JAR resources with `new File(url.toURI())`**; `jar:` URLs are not filesystem files.
9. **Forgetting to check `null`/`IOException`**, assuming every resource is present.
10. **Forgetting to reset the TCCL or release `URLClassLoader`/caches** after a plugin lifecycle.
11. **Failing to test cases where parent and child share the same name**, missing mismatches until real deployment.
12. **Assuming changing classpath order is enough to fix policy**, when parent delegation itself takes precedence before the child's classpath URLs.

## 16. Self-Check Questions

**1. A child overrides `loadClass` to be child-first. Does `getResource` automatically become child-first?** No. `getResource` is a separate lookup path, and `ClassLoader`'s default normally prioritizes the parent.

**2. Why can both a child class and a parent resource be found while the application still behaves wrongly?** The two versions are inconsistent; class B may read schema/config/template A.

**3. Why shouldn't you only fix `getResource`?** Because some frameworks/APIs use `getResources` to retrieve multiple resources. Without updating that method, the ordering or result set can still differ.

**4. In the example, why does `CoherentLoader.getResources` return child then parent?** The resource `demo/label.txt` is classified as private/versioned under the demo policy; the child is prioritized, while we still allow listing the parent copy.

**5. Should you return child-only for all `META-INF/services/*`?** No. SPIs usually need to discover providers from multiple sources; the proper aggregation contract must be preserved.

**6. If a plugin uses an interface with the same name but defined by a different loader, is having the right resource order enough?** No. A shared interface requires the same runtime identity; class identity depends on the defining loader.

**7. Do `Class.getResource("label.txt")` and `ClassLoader.getResource("label.txt")` necessarily find the same entry?** No. The `Class` API resolves names relative to the package; `ClassLoader` uses resource names from the root of the loader namespace.

**8. If a resource lookup returns `null` in a named module, is the priority order definitely wrong?** No. Module encapsulation/`opens` rules can also prevent a resource from being visible.

**9. Does changing the TCCL automatically make `Class.forName(String)` use the new loader?** No. `Class.forName(String)` uses the caller's defining loader; only APIs that intentionally read the TCCL are affected.

**10. Which test catches this bug fastest?** Create a parent and child with **the same class name and resource name** but different values, then assert class behavior, resource content, and `getResources` order.

## 17. Official References

- Java SE 17 API, `ClassLoader`: `loadClass`, `getResource`, `getResources`, `findResource`, `findResources`, and resource-stream methods: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: class/resource lookup from URLs and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `Class.getResource` and `Class.getClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `ServiceLoader`: provider discovery from resource descriptors/modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JVMS §5.3, *Creation of Classes and Interfaces*, on defining/initiating loaders and runtime class identity: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3

**Key takeaway:** A plugin can run **a class from the child** while reading **a resource from the parent** if only `loadClass` is changed. To avoid version skew, build **a policy matrix by namespace and resource type**, align `getResource` with `getResources` when needed, protect shared APIs, and test with colliding class/resource names across both sources. For service descriptors or aggregated resources, "consistent" usually means **aggregating properly** rather than always taking only the child.
