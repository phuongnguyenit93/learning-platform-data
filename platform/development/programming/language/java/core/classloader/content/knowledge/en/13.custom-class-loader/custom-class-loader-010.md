# Adding Resource Lookup Corresponding to Classes in a Custom ClassLoader

## 1. Problem: Classes Can Be Loaded, but Resources Cannot Be Found

A custom ClassLoader can read bytecode from a directory, database, JAR, or custom repository and then use `defineClass(...)` to create a runtime class. However, if it **only overrides `findClass(...)`**, resources bundled alongside the class — such as `config.properties`, `messages.txt`, templates, or service descriptors — will not necessarily be found by:

~~~java
Class<?> pluginType = customLoader.loadClass("demo.plugin.Widget");
URL url = pluginType.getResource("message.txt");
~~~

Those two operations go through **two different lookup paths**:

- **Class lookup:** `loadClass` (usually delegating to the parent first) and then the custom loader's `findClass`.
- **Resource lookup:** `getResource`/`getResources` (usually querying the parent first) and then the custom loader's `findResource`/`findResources`.

Therefore, **successfully loading a class does not automatically make data files alongside `.class` discoverable**. When writing a custom ClassLoader, you need to design the resource lookup path corresponding to where bytecode is stored.

Objective of this article: starting from a **root directory containing both `.class` files and resources**, implement `findClass`, `findResource`, and `findResources` completely; test package-relative resources and resources with the same name as those in the parent, and avoid misconceptions about lookup order. The example uses **Java 17+** and runs standalone with `javac`/`java`.

## 2. Class and Resource Method Pairs

| API | Role | Who Usually Calls It? |
|---|---|---|
| `ClassLoader.loadClass(name)` | Class lookup entry point, parent-first by default | Host, reflection, JVM/framework |
| `ClassLoader.findClass(name)` | Hook for a custom loader to **define a class** when the parent does not find it | `loadClass` |
| `ClassLoader.getResource(name)` | Entry point to find **one URL** of a resource, parent-first by default | Host, `Class.getResource` via defining loader |
| `ClassLoader.findResource(name)` | Hook to find a resource in the loader's **own source** | `getResource` |
| `ClassLoader.getResources(name)` | Lists **multiple URLs** following parent-then-own-resources order | Frameworks and applications |
| `ClassLoader.findResources(name)` | Hook to list resources in the loader's **own source** | `getResources` |
| `ClassLoader.resources(name)` | Represents multiple URLs as a `Stream<URL>` (Java 9+) | Applications using the Stream API |
| `ClassLoader.getResourceAsStream(name)` | Opens an `InputStream` for the first resource | Applications reading data |

**Design principle:** When your loader has a shared repository for bytecode and resources, `findClass` and `findResource(s)` should be based on **the same root, the same path-mapping rules, and the same data-source lifecycle**.

The `findResource`/`findResources` hooks do not define classes and do not initialize classes on their own. They only return URLs that the caller can open to fetch data. Conversely, `findClass` does not automatically expose every non-class file in the source directory to the resource API.

## 3. Mapping from Class Names and Resource Names

Suppose the binary class name is `demo.plugin.Widget` and the package is `demo.plugin`:

~~~text
Binary class name:     demo.plugin.Widget
Class file:            demo/plugin/Widget.class

Class-relative name:   message.txt
Resolved resource:     demo/plugin/message.txt

Root-relative name:    demo/plugin/message.txt
~~~

Key rules:

- `findClass("demo.plugin.Widget")` needs to find `demo/plugin/Widget.class` in the class root.
- `ClassLoader.getResource("demo/plugin/message.txt")` searches by **resource name from the root**. Normally it does **not** have a leading `/`.
- `Widget.class.getResource("message.txt")` resolves the relative name to `demo/plugin/message.txt` before looking it up via `Widget`'s loader.
- `Widget.class.getResource("/demo/plugin/message.txt")` treats the leading `/` as an **absolute path from the resource root**, then strips this slash when querying the loader.
- `Widget.class.getResourceAsStream("message.txt")` also follows the package-relative naming rule, but returns a stream instead of a URL.

Important point: `Class.getResource(...)` **does not use the Thread Context ClassLoader (TCCL) by default**. It is tied to the class being called on and that class's loader/module. Therefore, if `Widget` is defined by a custom loader, calling `Widget.class.getResource("message.txt")` can look up through that loader — **as long as that loader implements resource lookup**.

## 4. Parent-First Diagram and Hook Scope

Suppose the host uses the application loader (parent), and the plugin uses `DirectoryLoader` (child):

~~~text
Caller calls child.loadClass("demo.plugin.Widget")
    ├─ Parent tries to find Widget
    └─ Not found → child.findClass("demo.plugin.Widget")
                       └─ reads plugin-root/demo/plugin/Widget.class

Caller calls child.getResource("demo/plugin/message.txt")
    ├─ Parent tries to find message.txt
    └─ Not found → child.findResource("demo/plugin/message.txt")
                       └─ returns URL to plugin-root/demo/plugin/message.txt

Caller calls child.getResources("demo/plugin/shared.txt")
    ├─ Parent finds shared.txt  → HOST_SHARED
    └─ child.findResources      → CHILD_SHARED
                                  |
                                  v
                      [URL(parent), URL(child)]
~~~

With the default `ClassLoader`, you usually **do not need to override `loadClass` or `getResource`** to have parent-first behavior. Overriding the `findClass`, `findResource`, and `findResources` hooks is enough to provide a custom search path when the parent cannot find the target or when enumeration is needed.

If you override `getResource` with an implementation that only searches your own resources, you may accidentally **bypass the parent's resources**. If you override `getResources` with an implementation that only returns your own resources, you may omit the parent's service/config descriptors from the results. Only change the delegation mechanism when there is a clear reason and a design compatible with the other APIs.

## 5. Java 17+ Example: DirectoryLoader Supporting Both Classes and Resources

We will write a custom loader that reads from a plugin directory on disk, rather than using the built-in `URLClassLoader`, in order to learn how to add resource hooks in a controlled manner.

The program demonstrates two cases:

1. The resource `message.txt` **resides only in the plugin root**, so it can be found using `Widget.class.getResource(...)` or `DirectoryLoader.getResource(...)`.
2. The resource `shared.txt` appears **in both the host root and the plugin root**. Because of parent-first delegation, the default lookup returns the host's version; meanwhile, `findResource` returns the child's version when explicitly accessing the own-source hook.

### 5.1. File Structure

~~~text
directory-loader-demo/
├── src/
│   └── DirectoryLoaderDemo.java
├── plugin-src/
│   └── demo/plugin/Widget.java
├── host-resources/
│   └── demo/plugin/shared.txt
└── plugin-resources/
    └── demo/plugin/
        ├── message.txt
        └── shared.txt
~~~

The text files are UTF-8 without BOM, with the following contents respectively:

| Path | Content |
|---|---|
| `host-resources/demo/plugin/shared.txt` | `HOST_SHARED` |
| `plugin-resources/demo/plugin/message.txt` | `PLUGIN_MESSAGE` |
| `plugin-resources/demo/plugin/shared.txt` | `CHILD_SHARED` |

After compilation, `build/host` contains host classes + host resources; `build/plugin` contains plugin bytecode + plugin resources. **Do not put `build/plugin` on the application classpath** when running.

### 5.2. Plugin Class

File **`plugin-src/demo/plugin/Widget.java`**:

~~~java
package demo.plugin;

public final class Widget {
    public Widget() {
    }

    public String message() {
        return "Widget ready";
    }
}
~~~

This is a normal class with a `public` no-argument constructor. The host **does not import** `Widget` because the custom loader must be responsible for defining that class.

### 5.3. Complete Host and Custom Loader

File **`src/DirectoryLoaderDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class DirectoryLoaderDemo {
    private static final String MESSAGE = "demo/plugin/message.txt";
    private static final String SHARED = "demo/plugin/shared.txt";

    private DirectoryLoaderDemo() {
    }

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        private Path existingFile(String relativeName) {
            if (relativeName == null
                    || relativeName.isEmpty()
                    || relativeName.startsWith("/")
                    || relativeName.indexOf('\\') >= 0) {
                return null;
            }

            final Path relative;
            try {
                relative = Path.of(relativeName);
            } catch (InvalidPathException ex) {
                return null;
            }

            Path file = root.resolve(relative).normalize();
            if (!file.startsWith(root) || !Files.isRegularFile(file)) {
                return null;
            }
            return file;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = existingFile(
                    name.replace('.', '/') + ".class");

            if (file == null) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        @Override
        protected URL findResource(String name) {
            Path file = existingFile(name);
            if (file == null) {
                return null;
            }

            try {
                return file.toUri().toURL();
            } catch (MalformedURLException ex) {
                throw new UncheckedIOException(ex);
            }
        }

        @Override
        protected Enumeration<URL> findResources(String name)
                throws IOException {
            URL found = findResource(name);
            return Collections.enumeration(
                    found == null ? List.<URL>of() : List.of(found));
        }

        // Only to demonstrate the child's own resource,
        // bypassing the parent-first mechanism of getResource.
        URL ownResource(String name) {
            return findResource(name);
        }
    }

    private static String text(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }
        try (InputStream in = url.openStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static String text(InputStream input) throws IOException {
        if (input == null) {
            return "(missing)";
        }
        try (InputStream in = input) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static String all(Enumeration<URL> urls)
            throws IOException {
        List<String> labels = new ArrayList<>();
        while (urls.hasMoreElements()) {
            labels.add(text(urls.nextElement()));
        }
        return String.join(" > ", labels);
    }

    private static String all(Stream<URL> urls) {
        try (urls) {
            return urls.map(url -> {
                try {
                    return text(url);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }).collect(Collectors.joining(" > "));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DirectoryLoaderDemo <plugin-root>");
        }

        Path pluginRoot = Path.of(args[0]).toAbsolutePath();
        if (!Files.isDirectory(pluginRoot)) {
            throw new IllegalArgumentException(
                    "Not a plugin directory: " + pluginRoot);
        }

        ClassLoader parent =
                DirectoryLoaderDemo.class.getClassLoader();
        DirectoryLoader child =
                new DirectoryLoader(pluginRoot, parent);

        Class<?> widget = child.loadClass("demo.plugin.Widget");
        Object instance = widget.getConstructor().newInstance();

        System.out.println("Widget says: "
                + widget.getMethod("message").invoke(instance));
        System.out.println("Widget defined by child: "
                + (widget.getClassLoader() == child));

        System.out.println("Class relative message: "
                + text(widget.getResource("message.txt")));
        System.out.println("Class absolute message: "
                + text(widget.getResource("/" + MESSAGE)));
        System.out.println("Loader message: "
                + text(child.getResource(MESSAGE)));
        System.out.println("Loader message stream: "
                + text(child.getResourceAsStream(MESSAGE)));
        System.out.println("Parent sees plugin message: "
                + (parent.getResource(MESSAGE) != null));

        System.out.println("Parent-first shared: "
                + text(child.getResource(SHARED)));
        System.out.println("Child's own shared: "
                + text(child.ownResource(SHARED)));
        System.out.println("All shared: "
                + all(child.getResources(SHARED)));
        System.out.println("Shared stream: "
                + all(child.resources(SHARED)));
        System.out.println("Class relative shared: "
                + text(widget.getResource("shared.txt")));

        System.out.println("Leading slash on loader fails: "
                + (child.getResource("/" + MESSAGE) == null));

        boolean parentCannotLoad;
        try {
            parent.loadClass("demo.plugin.Widget");
            parentCannotLoad = false;
        } catch (ClassNotFoundException expected) {
            parentCannotLoad = true;
        }
        System.out.println("Parent cannot load Widget: "
                + parentCannotLoad);
    }
}
~~~

**Why does `DirectoryLoader` only override three hooks?** This approach preserves the parent-first contract of `loadClass`, `getResource`, and `getResources` in `ClassLoader`. The new loader only needs to tell the JVM how to retrieve bytecode and resource URLs from `root`.

**Why is `ownResource` declared separately?** It is only a method for *observing* the child's `findResource` result. Application code should not use an own-source hook as the default API, because that hook ignores resources provided by the parent. If a plugin system's requirements truly call for child-first behavior, that behavior should be clearly defined across the entire system rather than relying on a convenience method.

## 6. Compile and Run Commands

Requires JDK **17+**, including `javac` and `java`. Open a terminal in the `directory-loader-demo/` directory containing all the files listed above.

**Bash (Linux, macOS, or Git Bash):**

~~~bash
mkdir -p build/host build/plugin

javac -encoding UTF-8 -d build/host src/DirectoryLoaderDemo.java
javac -encoding UTF-8 -d build/plugin \
  plugin-src/demo/plugin/Widget.java

cp -R host-resources/. build/host/
cp -R plugin-resources/. build/plugin/

java -cp build/host DirectoryLoaderDemo build/plugin
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin | Out-Null

javac -encoding UTF-8 -d build/host src/DirectoryLoaderDemo.java

javac -encoding UTF-8 -d build/plugin plugin-src/demo/plugin/Widget.java

Copy-Item -Path host-resources/* -Destination build/host -Recurse -Force
Copy-Item -Path plugin-resources/* -Destination build/plugin -Recurse -Force

java -cp build/host DirectoryLoaderDemo build/plugin
~~~

After building, check the structure:

~~~text
build/
├── host/
│   ├── DirectoryLoaderDemo.class
│   ├── DirectoryLoaderDemo$DirectoryLoader.class
│   └── demo/plugin/shared.txt            (HOST_SHARED)
└── plugin/
    └── demo/plugin/
        ├── Widget.class
        ├── message.txt                   (PLUGIN_MESSAGE)
        └── shared.txt                    (CHILD_SHARED)
~~~

Do not add `build/plugin` to the host's `java -cp`. If the parent has already loaded `Widget` from there, `child.loadClass(...)` may return the parent's class instead of using `findClass`, and the verification results will differ.

### Expected Stdout

With the exact files, classpath, and a standard Java 17 runtime:

~~~text
Widget says: Widget ready
Widget defined by child: true
Class relative message: PLUGIN_MESSAGE
Class absolute message: PLUGIN_MESSAGE
Loader message: PLUGIN_MESSAGE
Loader message stream: PLUGIN_MESSAGE
Parent sees plugin message: false
Parent-first shared: HOST_SHARED
Child's own shared: CHILD_SHARED
All shared: HOST_SHARED > CHILD_SHARED
Shared stream: HOST_SHARED > CHILD_SHARED
Class relative shared: HOST_SHARED
Leading slash on loader fails: true
Parent cannot load Widget: true
~~~

**Stdout analysis:**

1. `Widget defined by child: true` confirms that the parent does not have the class and that `DirectoryLoader.findClass` read the bytecode at `build/plugin/demo/plugin/Widget.class`.
2. Both calls `widget.getResource("message.txt")` and `widget.getResource("/demo/plugin/message.txt")` resolve to `demo/plugin/message.txt`, which is found by `Widget`'s defining loader.
3. `child.getResource(MESSAGE)` and `child.getResourceAsStream(MESSAGE)` find the resource belonging to the plugin; the host parent does not have that resource.
4. For `shared.txt`, the parent contains `HOST_SHARED`, so `child.getResource(SHARED)` returns the parent's copy, **not** the copy alongside `Widget.class`. This is what parent-first means.
5. `child.ownResource(SHARED)` accesses the child's source, so it sees `CHILD_SHARED`.
6. `getResources` and `resources` include the parent's URL followed by the child's URL, producing `HOST_SHARED > CHILD_SHARED`.
7. `widget.getResource("shared.txt")`, even though it starts from a class defined by the child, still goes through the ClassLoader's parent-first delegation. Therefore, the selected resource is `HOST_SHARED`.
8. With `ClassLoader.getResource`, a name starting with `/` is not handled like `Class.getResource` and does not match the stored resource name; the parent does not have a matching name either.
9. The parent does not search downward into the child, so `parent.loadClass("demo.plugin.Widget")` throws `ClassNotFoundException`.

## 7. `findClass`: Bytecode Path Sharing the Root Rule

In `findClass`:

~~~java
// Excerpt of the core logic from the example.
String relative = name.replace('.', '/') + ".class";
Path file = existingFile(relative);
byte[] bytes = Files.readAllBytes(file);
return defineClass(name, bytes, 0, bytes.length);
~~~

The snippet above only illustrates the success branch; the full runnable code checks for null and wraps `IOException` in `ClassNotFoundException`.

Using the same `root` for `findClass` and `findResource` establishes an easy-to-understand rule:

~~~text
root/demo/plugin/Widget.class  ← data for defineClass
root/demo/plugin/message.txt   ← data for findResource
root/demo/plugin/shared.txt    ← another resource in the same package
~~~

However, you must distinguish:

- `defineClass` only accepts valid Java class bytecode; do not use it to load text files.
- `findResource` returns a `URL` pointing to data; it does not define a class or trigger static initializers.
- `getResource` may return the parent's resource even when the child's `findResource` also finds the same name.
- There may be multiple source roots or JARs; in that case, `findClass` and `findResources` must use an explicit list of sources rather than assuming a single Path as in the example.

If classes reside in a **JAR** rather than a directory, you should consider the built-in `URLClassLoader`. It already supports class lookup, URL resource lookup, parent delegation, and the `close()` lifecycle. There is no need to rewrite a ZIP/JAR parser if the goal is simply to load a few ordinary JARs.

## 8. `findResource` and `findResources`: Why Are Both Needed?

A very common mistake is overriding only `findResource`:

~~~java
@Override
protected URL findResource(String name) {
    // Find the first resource in the loader's own repository.
    ...
}
~~~

In that case, `getResource(name)` may work, **but `getResources(name)` will not necessarily list resources belonging to the loader's own repository**, because the default implementation of `findResources` does not automatically aggregate from the subclass's `findResource`. This is the difference between a **single-lookup API** and a **multi-enumeration API**.

To support both, you need to implement:

~~~java
@Override
protected Enumeration<URL> findResources(String name)
        throws IOException {
    URL found = findResource(name);
    return Collections.enumeration(
            found == null ? List.<URL>of() : List.of(found));
}
~~~

This is an appropriate approach **when each name has at most one file in the child's root**. When the loader searches across **multiple JARs/roots**, you must enumerate every URL in the desired order, for example:

~~~java
// Illustrative code, not runnable standalone:
List<URL> found = new ArrayList<>();
for (Repository repository : repositories) {
    URL url = repository.find(name);
    if (url != null) {
        found.add(url);
    }
}
return Collections.enumeration(found);
~~~

Do not return immediately on the first match if the contract of `findResources` is to list all URLs with that name.

**Useful consistency condition:** The first URL listed by `getResources(name)` should match `getResource(name)` when the lookup system is not being modified concurrently. If a subclass overrides the entry-point methods inconsistently, frameworks using the single-resource API and those using the multi-resource API may unintentionally see different datasets.

## 9. Class-Relative Resources: Same Package Does Not Guarantee Same Source

An easily mistaken assumption:

> "`Widget.class.getResource("shared.txt")` definitely reads the file from the exact directory containing `Widget.class`."

That is **not true in general**. `Class.getResource` resolves a **package-relative resource name** and then delegates the lookup to the appropriate ClassLoader/module. If the ClassLoader uses parent-first delegation and the parent has a resource with the same name, **the parent's resource may take precedence**, even though the `Widget` class was defined by the child.

In the example:

~~~text
Widget.class        → defined by child, located in build/plugin
shared.txt (host)   → provided by parent, HOST_SHARED
shared.txt (plugin) → provided by child, CHILD_SHARED
~~~

The call:

~~~java
URL chosen = widget.getResource("shared.txt");
~~~

receives `HOST_SHARED`. To query only the plugin root in a system with a requirement that "resources must stay alongside plugin code", you need an API controlled by the framework, such as `ownResource`, or a collision-avoiding namespace/path design.

**Better practical strategy:** place resources under a unique identifying path, such as `META-INF/my-plugin-id/config.json`, instead of a generic name like `config.properties` at the root of multiple JARs. If the code intentionally wants to support multiple resources with the same name, use `getResources` with explicit merge/priority rules.

## 10. Resource Names and Slash Rules

| Caller | Input | Meaning |
|---|---|---|
| `loader.getResource("demo/plugin/message.txt")` | No leading slash | Path from the loader root |
| `loader.getResource("/demo/plugin/message.txt")` | Has leading slash | Typically does not match a resource name; do not use |
| `Widget.class.getResource("message.txt")` | Relative name | From package `demo.plugin` |
| `Widget.class.getResource("/demo/plugin/message.txt")` | Leading slash | Absolute name from the resource root |
| `Widget.class.getResourceAsStream("message.txt")` | Relative name | InputStream of the selected resource; must be closed |

For resources in a **named module**, module encapsulation and `opens` rules also apply. `Class.getResource` is not simply string concatenation followed by calling any loader; the lookup may involve module access checks. This example uses **classpath/unnamed modules** so that the behavior can be easily verified.

## 11. Path Safety and Correctness of a Custom Loader

The example code has an `existingFile` method to restrict lookups within the root:

~~~java
Path file = root.resolve(relative).normalize();
if (!file.startsWith(root) || !Files.isRegularFile(file)) {
    return null;
}
~~~

Calling `normalize()` and checking `startsWith(root)` helps prevent **some** simple `../` accesses or absolute paths outside the root. However, this is **not a sandbox or a complete path-traversal defense**:

- A **symbolic link** inside the root may point to a file outside; comparing normalized paths does **not** handle that case. If the resource source is untrusted, you need a symlink policy, real-path checks, and protection against filesystem modification races (TOCTOU).
- Paths supplied by the caller may follow different rules between Windows and Unix (separators, drives, case sensitivity). Production libraries need explicit input validation/normalization.
- Untrusted callers should not be allowed to arbitrarily request any file inside the plugin root if the root contains sensitive secrets/configs.
- `defineClass` does not create a security boundary: plugin bytecode runs in the same JVM/process. For untrusted code, isolate privileges using an appropriate process/container.
- A production loader must also consider `ProtectionDomain`, package metadata/sealing, JAR signatures, thread safety, lifecycle, and concurrent loading; this example focuses on **resource lookup** and does not present a complete production JAR loader.

If the file disappears between `Files.isRegularFile` and `Files.readAllBytes`, the `IOException` branch in `findClass` converts the error into a `ClassNotFoundException` with a cause; the resource URL branch can also encounter an error when the caller opens the URL. Finding a `URL` **does not guarantee** that the file will still be readable afterward.

## 12. Resource Lifecycle: URL and InputStream

`findResource` returns a `URL` pointing to the file. When the caller invokes `URL.openStream()` or `getResourceAsStream`, an `InputStream` is opened. The caller must **close the stream**:

~~~java
// Illustrative code assuming the loader already exists.
try (InputStream in =
             loader.getResourceAsStream("demo/plugin/message.txt")) {
    if (in == null) {
        throw new IOException("Resource missing");
    }
    String text = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
    // Process text...
}
~~~

Do not treat a URL as the resource content itself. A URL is a **location**; the file may be modified or deleted after the URL is returned. If resources must remain immutable throughout a plugin version, manage snapshots/versions explicitly.

Note that the `DirectoryLoader` demonstrated here **does not implement `AutoCloseable`**, nor does it hold `JarFile`/stream handles to close. There is no automatic `close()` like `URLClassLoader`. If you build your own loader reading ZIPs, JARs, or network connections, you must design a mechanism to close resources owned by the loader, stop tasks, and clean up objects/threads/callbacks before unloading the plugin.

Making `DirectoryLoader` unreferenced can allow the JVM to garbage-collect the classes/loader once all related objects/classes are no longer reachable, but there is no guarantee of immediate unloading; TCCL, `ThreadLocal`, and framework caches may retain the loader longer than expected.

## 13. `getResources`, `resources`, and Multi-Source Metadata

With a single root, the example's `findResources` only returns one URL or an empty Enumeration. However, ClassLoader's `getResources` **can still return multiple URLs**, because it combines the results from the parent and the child.

For `shared.txt`:

~~~text
child.getResources("demo/plugin/shared.txt")
    → [HOST_SHARED, CHILD_SHARED]

child.resources("demo/plugin/shared.txt")
    → Stream<URL> following the same lookup
~~~

`getResources` returns an `Enumeration<URL>`. `resources` (Java 9+) returns a `Stream<URL>`, allowing filtering/mapping/collecting. **Both APIs return URLs, not file contents**. When reading each URL, open and close separate `InputStream`s as shown in the `text(url)` method in the example.

A common case is `META-INF/services/com.example.Service`:

- Multiple JARs may provide descriptors with the same name.
- `ServiceLoader` performs resource/provider lookup according to its own rules.
- If a custom loader only implements `findResource` without implementing `findResources`, a framework that needs to enumerate multiple descriptors may fail to see providers located in the loader's own source.
- Merely defining a file with the same `META-INF/services/...` name is not enough; the provider and the service interface must belong to the matching runtime types for `ServiceLoader` to accept them.

Whenever possible, use `ServiceLoader` instead of writing your own descriptor parser. If the API allows passing a loader, use the overload that takes an explicit `ClassLoader`; TCCL is only a contextual lookup option and does not replace a class's defining loader.

## 14. Custom ClassLoader with JARs: When Not to Write Your Own?

If the goal is simply "loading classes and resources from a list of JARs", the simpler choice is usually `URLClassLoader`:

~~~java
// Illustrative code; requires urls and parent.
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    Class<?> type = loader.loadClass("demo.plugin.Widget");
    URL resource = loader.getResource("demo/plugin/message.txt");
    // Use the class and read the resource while the loader is still open.
}
~~~

`URLClassLoader` already supports `findClass`, `findResource`, `findResources`, URL ordering, parent delegation, and `close()` to release files/JARs opened by the loader. That saves a great deal of work and avoids common bugs compared to a subclass that reads ZIP/JAR files manually.

Consider a custom ClassLoader only when the data source is genuinely different (for example, bytecode/resources from an encrypted bundle, database, network repository, or dynamic content) or when explicit verification/version control is needed. When writing one, you must handle **both classes and resources**; loading `.class` files while omitting `findResource(s)` is an incomplete design.

## 15. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `child.loadClass("demo.plugin.Widget")` succeeds, but `Widget.class.getResource("message.txt")` returns null | `findClass` is implemented, but `findResource` is missing | Implement resource lookup from the same root with the proper path |
| `getResource` finds the resource, but `getResources` does not list the child's file | `findResource` is implemented, but `findResources` is missing | Override both hooks; enumerate all matches in the child |
| The host's resource "wins" over the file next to the plugin class | `getResource` is parent-first and the parent has a matching name | Use a dedicated namespace or an API that explicitly queries the plugin source |
| `ClassLoader.getResource("/demo/plugin/message.txt")` returns null | A name with a leading slash does not follow `ClassLoader` rules | Use `"demo/plugin/message.txt"` |
| `Widget.class.getResource("message.txt")` does not find a file at the root | Class-relative lookup prepends the package path | Move the resource into `demo/plugin/` or use an absolute name |
| The parent cannot find the child's class | The parent does not search the child's own source automatically | Have the host invoke the child loader and communicate via a shared API |
| `ClassCastException` when classes share the same name | Two loaders defined two incompatible runtime classes | Share the interface/DTO in a common loader |
| `getResource` returns a URL, but reading it later fails | The file was deleted/modified or I/O failed | Open and read within a managed lifecycle, and handle `IOException` |
| Normalized path still escapes the root | Symlink or filesystem race | Verify the real path and enforce a trusted-source policy |
| Plugin fails to unload even when no longer used | Threads/TCCL/caches retain the classloader | Clean up callbacks, threads, resources, and references |
| `ServiceLoader` does not discover the provider | Wrong descriptor, wrong lookup loader, or missing `findResources` | Check `META-INF/services`, type identity, and enumeration |

## 16. Self-Check Questions

**Question 1.** A custom ClassLoader only overrides `findClass`. It successfully loads `Widget.class` from its own directory. Is `Widget.class.getResource("message.txt")` guaranteed to find the file located next to `Widget.class`?

**Answer:** No. Class lookup and resource lookup are two separate paths; the loader needs to provide `findResource` (and `findResources` if enumeration is desired).

**Question 2.** Why can `Widget.class.getResource("shared.txt")` return the parent's resource even though `Widget.class.getClassLoader()` is the child?

**Answer:** `Class.getResource` resolves the package-relative name and then uses the resource lookup mechanism. With a parent-first ClassLoader, the parent can supply a resource with the same name before the child does.

**Question 3.** Why should you override `findResources` if you already have `findResource`?

**Answer:** Because the `getResources` API is intended to enumerate **multiple URLs** and typically calls the `findResources` hook; the default hook does not automatically enumerate entries from a customized `findResource`.

**Question 4.** How many resources does `getResources("demo/plugin/shared.txt")` return in the example?

**Answer:** Two URLs: the host parent's resource first, followed by the child's own resource. `resources(...)` provides them via the Stream API.

**Question 5.** When a custom loader reads classes from a database and resources are stored in the database under the same key prefix, how should it be designed?

**Answer:** `findClass` maps the binary name to the bytecode key, while `findResource(s)` maps the resource name to an appropriate URL/access path (or provides a protocol handler with a managed lifecycle). You must ensure that the returned URI/URL can actually be opened, and properly handle errors and resource closing.

**Question 6.** Do you need to override `getResource` to use parent-first behavior with resources in a custom loader?

**Answer:** Usually no. Use `findResource`/`findResources`; `ClassLoader.getResource(s)` performs parent delegation by default.

## 17. References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `findClass`, `findResource`, `findResources`, `getResource`, `getResources`, and `resources`.
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): package-relative and absolute naming rules.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loader implementation with JAR/resource lookup paths.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): relationship between multiple resource descriptors and provider discovery.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, and `startsWith` when mapping roots.

**Key takeaway:** A custom ClassLoader must design **a paired class and resource lookup mechanism**. Override `findClass` to define classes, `findResource` to look up a single own resource, and `findResources` to list own resources; let the `loadClass`/`getResource(s)` entry points manage parent-first behavior unless there is a reason to change it. A resource in the same package as a class is **not guaranteed** to come from the same source when the parent has a matching name; verify the namespace, path, and delegation order.
