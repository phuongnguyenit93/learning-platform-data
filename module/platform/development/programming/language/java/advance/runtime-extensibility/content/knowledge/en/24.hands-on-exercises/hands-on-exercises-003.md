# Hands-On: Loading Two Plugins with Separate Library Versions via Independent Classloaders

## 1. Objectives and Expected Outcomes

A Java host application must run two plugins simultaneously, where each plugin depends on **a different version of the same library**. For example, plugin A requires `vendor.Helper` version `1.0`, while plugin B requires `vendor.Helper` version `2.0`. Both library JARs contain a class with the binary name `vendor.Helper`, so if both are placed on the same application classpath, the classloader usually defines only one version for that name and the other plugin may behave incorrectly or throw `NoSuchMethodError`.

Hands-on solution: place the SPI contract in the **parent classloader**, and place each plugin along with its own library JAR in **an independent child URLClassLoader**. Verification goals:

- Both providers can be cast to the same `spi.Plugin` interface of the host.
- Plugin A returns a result containing version `1.0`, and plugin B returns version `2.0`.
- The two `vendor.Helper` classes have the **same binary name but different identities** because they are defined by two different loaders.
- Plugin A cannot see plugin B's private dependency through its own loader.
- Stop plugins, clear references, and close loaders following proper lifecycle rules; do not confuse classloader isolation with a security sandbox.

```text
                           Parent / AppClassLoader
                           spi.Plugin (shared API)
                                    |
                         +----------+----------+
                         |                     |
                    URLClassLoader A       URLClassLoader B
                     plugin-a.jar           plugin-b.jar
                     helper-v1.jar          helper-v2.jar
                         |                     |
               vendor.Helper v1        vendor.Helper v2
                         |                     |
                   '1.0: alpha'          '2.0: beta'
```

## 2. Class Identity and Parent Delegation Mechanics

In the JVM, a runtime class is identified by its **binary name together with its defining classloader**, not solely by package/class name. Therefore, two different loaders can define `vendor.Helper` from different bytecode. However, `spi.Plugin` implemented by both providers must be the **exact same runtime class** defined by the parent loader; if a child contains and loads a copy of the API using child-first delegation, the host may encounter `ClassCastException` even though the interface names are identical.

This example uses the default `URLClassLoader` with **parent-first delegation**. This works when:

1. The parent classpath contains only the **shared API + host**, and does not contain `vendor.Helper` or plugin implementation classes.
2. Each child has only its own plugin JAR and matching dependency JAR version.
3. Plugin implementations are new classes in the child, so the parent cannot find them; the child defines them.
4. The `vendor.Helper` dependency is not in the parent, so each child loads its own version.

**Important note:** A separate URLClassLoader does not automatically isolate dependencies if the parent has already loaded a class with the same name. You must not place both `helper-v*.jar` files on the system classpath and expect the child to pick the right version. This is why the runtime classpath below contains only the host and the API.

## 3. Project Structure

```text
plugin-isolation-demo/
  src/
    api/spi/Plugin.java
    lib-v1/vendor/Helper.java
    lib-v2/vendor/Helper.java
    plugin-a/plugins/PluginA.java
    plugin-b/plugins/PluginB.java
    host/Host.java
  build/
    api/
    lib-v1/
    lib-v2/
    plugin-a/
    plugin-b/
    host/
  dist/
    api.jar
    helper-v1.jar
    helper-v2.jar
    plugin-a.jar
    plugin-b.jar
    host.jar
```

This is **classpath-based plugin isolation** using `URLClassLoader`, not a JPMS named modules example. When using separate JPMS layers, you must also consider module resolution and split packages. This exercise focuses on loading two versions of a library sharing the same class name into two independent classloaders.

## 4. Writing the Shared SPI Contract

Create `src/api/spi/Plugin.java`:

```java
package spi;

public interface Plugin extends AutoCloseable {
    String id();
    String execute(String input);
    @Override
    default void close() throws Exception {}
}
```

The interface resides in `api.jar` owned by the host/parent loader. Plugin JARs **do not bundle a copy** of `spi/Plugin.class`; when compiling, plugins only reference the API on the compilation classpath.

## 5. Creating Two Versions of the Same Library

Library V1 at `src/lib-v1/vendor/Helper.java`:

```java
package vendor;

public final class Helper {
    private Helper() {}
    public static String transform(String input) {
        return "1.0: " + input;
    }
}
```

Library V2 at `src/lib-v2/vendor/Helper.java`:

```java
package vendor;

public final class Helper {
    private Helper() {}
    public static String transform(String input) {
        return "2.0: " + input;
    }
}
```

Both sources share the same package, class name, and method signature to clearly demonstrate which version is loaded; real-world versions may change both implementation and API. When compiled into separate directories/JARs, the JVM can load both versions concurrently in two loaders.

## 6. Creating Two Independent Plugins

`src/plugin-a/plugins/PluginA.java`:

```java
package plugins;

import spi.Plugin;
import vendor.Helper;

public final class PluginA implements Plugin {
    @Override public String id() { return "plugin-A"; }
    @Override public String execute(String input) {
        return Helper.transform(input);
    }
}
```

`src/plugin-b/plugins/PluginB.java`:

```java
package plugins;

import spi.Plugin;
import vendor.Helper;

public final class PluginB implements Plugin {
    @Override public String id() { return "plugin-B"; }
    @Override public String execute(String input) {
        return Helper.transform(input);
    }
}
```

Each plugin depends on the shared `spi.Plugin` but invokes `vendor.Helper` from the dependency version **inside its own loader**. To verify this, the host will inspect the `vendor.Helper` class using each plugin's respective loader.

## 7. Host Loading Plugins with Two URLClassLoaders

Create `src/host/Host.java`:

```java
import spi.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Host {
    static URL url(String file) throws Exception {
        return Path.of("dist", file).toAbsolutePath().toUri().toURL();
    }

    static Plugin load(URLClassLoader loader, String className)
            throws Exception {
        Class<?> clazz = Class.forName(className, true, loader);
        return clazz.asSubclass(Plugin.class)
                .getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = Plugin.class.getClassLoader();
        try (URLClassLoader loaderA = new URLClassLoader(
                     new URL[]{url("plugin-a.jar"), url("helper-v1.jar")}, parent);
             URLClassLoader loaderB = new URLClassLoader(
                     new URL[]{url("plugin-b.jar"), url("helper-v2.jar")}, parent)) {

            Plugin a = load(loaderA, "plugins.PluginA");
            Plugin b = load(loaderB, "plugins.PluginB");
            try {
                System.out.println(a.id() + " -> " + a.execute("alpha"));
                System.out.println(b.id() + " -> " + b.execute("beta"));

                Class<?> helperA = loaderA.loadClass("vendor.Helper");
                Class<?> helperB = loaderB.loadClass("vendor.Helper");
                System.out.println("same helper class? " + (helperA == helperB));
                System.out.println("same API? " +
                        (a instanceof Plugin && b instanceof Plugin));
            } finally {
                try { a.close(); } finally { b.close(); }
            }
        }
    }
}
```

Here, `new URLClassLoader(urls, parent)` gives the two plugins two **independent namespaces**. `Class.forName(..., loader)` uses the designated loader. `asSubclass(Plugin.class)` confirms that the provider uses the same API class identity; if the class is incompatible, it fails immediately. `try-with-resources` closes both loaders, though in a real application you must ensure no callbacks or threads are still using the plugin before closing.

### Teardown notes

The example uses nested `try/finally` so that closing B is still attempted if closing A throws an error. In production, aggregate exceptions with `addSuppressed`, stop incoming requests, close executors/listeners/sockets, and only then close the loader. `URLClassLoader.close()` releases resources held by the loader; it **does not automatically unload all classes or stop plugin threads**.

## 8. Compiling Components Separately on Java 17+

From the root directory `plugin-isolation-demo`, run in a bash shell:

```bash
mkdir -p build/api build/lib-v1 build/lib-v2 build/plugin-a build/plugin-b build/host dist
javac --release 17 -d build/api src/api/spi/Plugin.java
javac --release 17 -d build/lib-v1 src/lib-v1/vendor/Helper.java
javac --release 17 -d build/lib-v2 src/lib-v2/vendor/Helper.java
javac --release 17 -cp build/api:build/lib-v1 -d build/plugin-a src/plugin-a/plugins/PluginA.java
javac --release 17 -cp build/api:build/lib-v2 -d build/plugin-b src/plugin-b/plugins/PluginB.java
javac --release 17 -cp build/api -d build/host src/host/Host.java

jar --create --file dist/api.jar -C build/api .
jar --create --file dist/helper-v1.jar -C build/lib-v1 .
jar --create --file dist/helper-v2.jar -C build/lib-v2 .
jar --create --file dist/plugin-a.jar -C build/plugin-a .
jar --create --file dist/plugin-b.jar -C build/plugin-b .
jar --create --file dist/host.jar -C build/host .

java -cp dist/api.jar:dist/host.jar Host
```

On Windows, `javac -cp` and `java -cp` use `;` instead of `:` as the separator; for example, `-cp "build/api;build/lib-v1"`. `Path` in `Host` resolves files from the `dist` directory relative to the working directory; run the program from the project root.

Expected output:

```text
plugin-A -> 1.0: alpha
plugin-B -> 2.0: beta
same helper class? false
same API? true
```

Both classes have the same `vendor.Helper` name, yet `helperA != helperB` because each child loader defines its own class. Conversely, both providers implement the single `spi.Plugin` runtime class from the parent, so the `instanceof Plugin` checks both evaluate to true.

## 9. Why Does the Simpler Approach Usually Fail?

If you place all JARs on the same classpath:

```bash
java -cp dist/api.jar:dist/host.jar:dist/plugin-a.jar:dist/plugin-b.jar:dist/helper-v1.jar:dist/helper-v2.jar Host
```

then the application classloader may find `vendor.Helper` in the parent before the child loader; both plugins may end up using the same V1 version, defeating the isolation goal. This command is an **example of a misconfiguration, not a standard run step**. Furthermore, when the parent contains plugin implementations, `plugins.PluginA` may be defined by the parent, misleading you into thinking a separate classloader was used.

Therefore, place only `api.jar` and `host.jar` on the parent classpath; plugins and their libraries are handed exclusively to child loaders.

## 10. When Two Versions Have Incompatible APIs

In this example, both versions share the `transform(String)` method so the source compiles cleanly. In reality, V2 may change method signatures or return types. Plugin A and B must compile against their respective correct library versions; if plugin B is accidentally run with V1, you may get `NoSuchMethodError`, `NoClassDefFoundError`, or logic bugs.

The rule is: each plugin bundle/loader includes its **complete matching set of dependencies**, and the shared API lives in the parent. If both plugins need to interact, never pass `vendor.Helper` objects directly across the boundary; exchange data through DTOs/interfaces in the shared API or standard types such as `String`, `byte[]`, or immutable records belonging to the parent API.

## 11. TCCL, ServiceLoader, and Resources

Some libraries discover services using the thread context classloader (TCCL) or the default `ServiceLoader.load(Service.class)`, and thus may fail to see a plugin's resources. When executing plugin code that requires a specific TCCL, the host can temporarily set the loader:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(loaderA);
    a.execute("work");
} finally {
    thread.setContextClassLoader(previous);
}
```

This is an illustrative snippet inside a method that has variables `loaderA` and plugin `a`, not a complete program. Never forget to restore the TCCL: if a loader remains referenced by a long-lived thread pool, it can prevent garbage collection of a stopped classloader.

Plugins can also have their own `META-INF/services`. With `ServiceLoader.load(service, loaderA)`, ensure that the SPI interface `service` has its class identity from the parent and that the descriptor resides in the right plugin/dependency JAR. Do not use TCCL or `ServiceLoader` to try forcing objects of plugin-private dependencies across the boundary.

## 12. Testing Isolation and Lifecycle

Tests should not only inspect output. You should verify:

1. **Class identity:** `loaderA.loadClass("vendor.Helper") != loaderB.loadClass("vendor.Helper")`.
2. **Shared API:** `a instanceof spi.Plugin` and `b instanceof spi.Plugin`.
3. **Versions:** A's output contains V1, and B's output contains V2 as expected.
4. **No leakage:** the parent classpath does not contain plugin/vendor classes.
5. **Negative test:** intentionally assign the V1 dependency to B and observe the mismatch or failure behavior.
6. **Reload:** create a new loader with the new version JAR; do not redefine a class with the same name in the old loader.
7. **Teardown:** stop plugins, close loaders, unregister listeners, and clean up threads.
8. **Artifact test:** run the host from the distributed JARs, not only from compiled class files in the IDE.

## 13. Common Errors

| Error | Cause | Fix |
| --- | --- | --- |
| Both plugins use V1 | `vendor.Helper` is on the parent classpath | Remove private dependencies from the parent |
| `ClassCastException` to `spi.Plugin` | Each child bundles/loads a copy of the API | Parent owns the API; children do not bundle the API |
| `NoSuchMethodError` | Plugin loads the wrong dependency version | Bundle the matching per-plugin dependencies |
| `ClassNotFoundException` | JAR is missing from the corresponding loader's URLs | Check the URL list and filenames |
| Resources/SPI not found | Wrong loader/TCCL or missing descriptors | Use the proper classloader and keep resource files |
| JAR remains locked or loader leaks | Loader not closed, or thread/listener holds a reference | Follow lifecycle stop and clean up TCCL/registries |
| `LinkageError` on reload | Redefining the same class name in the same loader | Create a new loader for the new version |

## 14. Security Limitations

Classloader isolation only separates **class namespaces** and supports dependency version management; plugins still run in the same JVM, OS user, heap, and thread pools, and can corrupt host state. Do not use `URLClassLoader` as a sandbox for untrusted code. For untrusted plugins, move to a separate JVM/process or container with minimal OS privileges and schema-validated IPC with timeouts and quotas.

## 15. Exercise Completion Checklist

- [ ] Both versions of `vendor.Helper` are compiled and packaged **separately**.
- [ ] Host + API appear only on the parent classpath.
- [ ] Each plugin has a child `URLClassLoader` with its exact plugin JAR and vendor JAR.
- [ ] Providers implement the single `spi.Plugin` interface from the parent.
- [ ] Plugin A/V1 and plugin B/V2 run simultaneously with the expected output.
- [ ] Different `vendor.Helper` identities are verified.
- [ ] TCCL is managed when libraries require it and restored in `finally`.
- [ ] Plugins and loaders are closed following lifecycle rules, with checks for memory leaks.
- [ ] Dependency isolation is not confused with security isolation.

**Conclusion:** The model of **one parent API + one classloader per plugin and its private dependency set** allows Java to run two versions of a library sharing the same class name simultaneously. This exercise emphasizes verifying **class identity**, **API sharing**, **clean artifact classpaths**, and **loader lifecycles**, rather than just checking a single line of output.
