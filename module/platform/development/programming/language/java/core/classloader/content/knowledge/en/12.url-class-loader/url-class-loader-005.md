# getURLs and the Limits of addURL in URLClassLoader

> **Context:** Java Core → ClassLoader → URLClassLoader. This article explains what `URLClassLoader.getURLs()` reflects, why `addURL(URL)` is `protected`, when adding a URL takes effect, and the important limits regarding parent delegation, class identity, class loading timing, closing the loader, and differences from the application classpath. The examples use standard Java 17+ APIs.

## 1. Two Seemingly Simple APIs That Are Easily Misunderstood

`java.net.URLClassLoader` is a `ClassLoader` that uses URLs as **the search path for classes and resources**. A URL can point to a directory containing a package tree, a JAR file, or another appropriate source supported by the implementation.

Two main methods:

```java
public URL[] getURLs();
protected void addURL(URL url);
```

- **`getURLs()`** returns **the URL search path array of that specific URLClassLoader instance**, consisting of the initial constructor URLs and any URLs added later via `addURL`.
- **`addURL(URL)`** appends a URL to the end of **that instance's** search path list. It does **not** create `Class<?>` objects immediately, does not preload the entire JAR, and does not expand the JVM-wide application classpath.
- `addURL` is **`protected`**, so Java code outside the class or subclass according to Java's access rules cannot call it directly as a public API. If an application genuinely owns a custom loader, a subclass can provide a controlled wrapper.

Two misconceptions to avoid right away:

1. `getURLs()` **is not an API that lists the entire classpath/module path or every location where a class can be found in the JVM**.
2. `addURL` **is not a mechanism to patch an already defined class**; it cannot force the JVM to reload a name that already exists on the same defining loader.

For example, `loader.getURLs()` returning 2 URLs does not mean the loader has loaded 2 classes, has exactly 2 JARs, or that those two sources are all the sources provided by the parent and modules.

## 2. How URLClassLoader Is Constructed and Search Order

One way to create a loader:

```java
import java.net.URL;
import java.net.URLClassLoader;

URL[] paths = { firstUrl, secondUrl };
ClassLoader parent = ClassLoader.getPlatformClassLoader();

try (URLClassLoader loader = new URLClassLoader(paths, parent)) {
    // The loader searches for classes/resources at the provided URLs,
    // after delegating to the parent according to default behavior.
}
```

The code above **is a snippet**: `firstUrl` and `secondUrl` need to be declared beforehand. It illustrates the constructor form and parent argument.

In the default usage of `URLClassLoader`:

```text
loadClass("com.example.Widget")
           |
           v
      findLoadedClass(...)
           |
     already loaded? -- yes --> return the recorded Class<?>
           |
           no
           v
     delegate to parent
           |
        found? -------- yes --> return the Class<?> loaded/defined by parent
           |
           no
           v
      URLClassLoader.findClass(...)
           |
           +--> iterate through search path URLs in order
           '--> locate entry com/example/Widget.class
                      |
                      '--> define the class in this loader
```

This is the general flow of the default `ClassLoader.loadClass` together with `URLClassLoader.findClass`; a custom loader may adjust delegation behavior. `URLClassLoader` searches URLs in the order they were declared, **after the parent has been tried first**, if no already-recorded class exists.

Important consequence: if the parent already finds `com.example.Widget`, adding another JAR that also contains `com.example.Widget` to the child **will not cause the child to override the parent's class** under normal parent-first policy.

## 3. What Does getURLs() Actually Tell You?

According to the Java SE API, `URLClassLoader.getURLs()` returns the URLs used as the search path for classes and resources of that loader. The returned array contains:

- The URLs passed to the **constructor** when creating the instance.
- The URLs **actually appended** by `addURL`, in search-path order.
- Not the loaded classes, and not every resource ever used.

Given:

```java
URLClassLoader loader = new URLClassLoader(
        new URL[] {urlA, urlB}, parent);
```

`loader.getURLs()` will represent a list starting with `urlA`, `urlB`. When a subclass successfully calls `addURL(urlC)`, `getURLs()` will reflect the new URL at the end.

**Do not infer the following information from `getURLs()` alone:**

| What you want to know | Is `getURLs()` sufficient? | Why |
| --- | --- | --- |
| The search path configured directly for **this loader** | Yes, within the API contract. | That is the method's contract. |
| Which JAR definitely contains a specific class | No. | A URL may point to a source without that class or not yet opened; a JAR has many entries. |
| Classes that have been defined by the loader | No. | `getURLs` is the search path configuration, not a history log. |
| Which classes are being provided by the parent | No. | The parent has its own sources and lookup strategy. |
| All classpaths and module paths across the entire JVM | No. | There are bootstrap/platform/system loaders, modules, and other custom loaders. |
| The actual resolution order for a duplicate class name in all situations | No. | Delegation, URL order, auxiliary sources, and loaded state must be considered. |
| Resources currently open/closed | No. | Configured URLs differ from file descriptors/stream state. |
| The classpath that `java` received at launch from `-cp` | Not necessarily. | A custom URLClassLoader can be completely separate from the application loader. |

Do not mutate elements of the returned array and expect the loader's configuration to change. `getURLs()` is an **observation method**; the API for modifying the search path (when permitted) is `addURL`. To keep your application easy to reason about, store your configuration sources separately rather than treating the URL array as mutable state storage.

### URLs in getURLs May Not Be Opened Yet

Having a URL in the search path is not proof that the file exists, is accessible, or has already been opened as a JAR. Actually loading a class or resource is what triggers the implementation to access the source. If the URL is invalid, lacks permissions, has a corrupted archive, or lacks the corresponding entry, lookup can still fail.

## 4. addURL Is protected: Proper Access Scope

The Javadoc defines:

```java
protected void addURL(URL url)
```

Therefore, the following code **does not compile** from a class without appropriate `protected` access:

```java
URLClassLoader loader = new URLClassLoader(new URL[0]);
loader.addURL(newUrl); // addURL(URL) has protected access
```

This is **an intentionally invalid snippet to illustrate the compile error**; `newUrl` must be declared if tested separately. The mistake is assuming "a method appears in the Javadoc, so any caller can invoke it."

The valid way when you genuinely want to add sources to your own loader:

```java
import java.net.URL;
import java.net.URLClassLoader;

public final class ExtensibleLoader extends URLClassLoader {
    public ExtensibleLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    public void append(URL url) {
        super.addURL(url);
    }
}
```

This is **a standalone compilable Java class** if saved as `ExtensibleLoader.java`; it has no `main` method and is meant to be used as a component in an application.

Do not use reflection on `URLClassLoader.addURL` or JDK internal loaders to bypass `protected` in production. Java 9+ enforces stronger module encapsulation, and that approach also depends on the concrete implementation type of the actual loader.

### Why Should the Wrapper Be Designed Carefully?

A public `append` wrapper can allow any caller holding a reference to that loader to inject unwanted dependencies. In a real plugin system, expose this API only to plugin management code, and validate allowed URLs/paths, loader ownership, resource/certificate policies, close state, and concurrency.

A minimal wrapper used in a demo shows the **API mechanism**; it does not by itself provide security policies or complete lifecycle management.

## 5. How Does addURL Append URLs? null, Duplicates, and Closed Loaders

According to the Java SE 21 API:

| Case | Result with `addURL` |
| --- | --- |
| Valid URL, not yet present, loader not closed | The URL is appended to the end of the search path. |
| `url == null` | No effect. |
| URL already exists in the list | No effect; no duplicate is appended. |
| Loader has been `close()`d | No effect. |

For example, a loader with initial order `[A, B]`:

```text
getURLs()         -> [A, B]
addURL(C)         -> [A, B, C]
addURL(C)         -> [A, B, C]   (no duplicates)
addURL(null)      -> [A, B, C]   (no change)
close()
addURL(D)         -> [A, B, C]   (closed, not added)
```

This is a conceptual diagram based on the contract; `A`, `B`, `C`, `D` are URLs, not Java code. Checking whether a URL is "already in the list" relies on the URL comparison semantics used by the implementation; do not assume every equivalent spelling of a path is normalized identically. Pass clearly normalized paths/URLs to avoid hard-to-spot semantic duplicates.

**Appending a URL does not validate that the JAR is valid.** The newly appended element may point to a deleted file, an archive missing the expected entry, or non-class-file data; errors will surface when a lookup actually occurs.

## 6. Runnable Practice: Before and After addURL

This example uses **two class directories** separate from the application classpath. We run the application from `build/app`, intentionally letting the custom loader see `build/first`, and only afterward append `build/second`.

### Project Structure

```text
src/
  first/
    example/
      First.java
  second/
    extra/
      Second.java
  app/
    UrlPathsDemo.java
build/
  first/           (created by javac)
  second/          (created by javac)
  app/             (created by javac)
```

**File `src/first/example/First.java`:**

```java
package example;

public class First {
    public String value() {
        return "first";
    }
}
```

**File `src/second/extra/Second.java`:**

```java
package extra;

public class Second {
    public String value() {
        return "second";
    }
}
```

**File `src/app/UrlPathsDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class UrlPathsDemo {
    static final class MutableLoader extends URLClassLoader {
        MutableLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        public void append(URL url) {
            super.addURL(url);
        }
    }

    public static void main(String[] args) throws Exception {
        URL first = Path.of("build/first")
                .toAbsolutePath().toUri().toURL();
        URL second = Path.of("build/second")
                .toAbsolutePath().toUri().toURL();

        Class<?> saved;

        try (MutableLoader loader = new MutableLoader(
                new URL[]{first}, ClassLoader.getPlatformClassLoader())) {

            System.out.println("initial URLs: " + loader.getURLs().length);

            System.out.println("first defined here: "
                    + (loader.loadClass("example.First")
                            .getClassLoader() == loader));

            System.out.println("parent class visible: "
                    + (loader.loadClass("java.lang.String") == String.class));

            try {
                loader.loadClass("extra.Second");
                System.out.println("unexpected second load");
            } catch (ClassNotFoundException expected) {
                System.out.println("second before append: missing");
            }

            loader.append(second);

            System.out.println("after append URLs: "
                    + loader.getURLs().length);

            System.out.println("second appended last: "
                    + loader.getURLs()[1].equals(second));

            loader.append(second);
            loader.append(null);

            System.out.println("duplicate and null ignored: "
                    + (loader.getURLs().length == 2));

            saved = loader.loadClass("extra.Second");

            System.out.println("second defined here: "
                    + (saved.getClassLoader() == loader));
        }

        System.out.println("loaded class usable after close: "
                + saved.getMethod("value")
                        .invoke(saved.getConstructor().newInstance()));
    }
}
```

### Compile and Run

Run these commands from the root directory containing `src` (the shell commands do not depend on a global `CLASSPATH`):

```bash
javac -d build/first src/first/example/First.java
javac -d build/second src/second/extra/Second.java
javac -d build/app src/app/UrlPathsDemo.java
java -cp build/app UrlPathsDemo
```

**Stdout compiled and verified on JDK 24; the code uses only APIs available in Java 17+:**

```text
initial URLs: 1
first defined here: true
parent class visible: true
second before append: missing
after append URLs: 2
second appended last: true
duplicate and null ignored: true
second defined here: true
loaded class usable after close: second
```

### What Does This Prove?

1. The first URL points to `build/first`, so the custom loader itself defines `example.First`.
2. Even though `getURLs()` has only **one URL**, the loader still finds `java.lang.String` via parent delegation. Therefore, **never treat `getURLs()` as the entire class search space**.
3. `extra.Second` is not yet in the search path, so the first `loadClass` throws `ClassNotFoundException`, which is intentionally caught.
4. After `append(second)`, the `getURLs()` array has length 2 and the new URL is at the end. The direct `loadClass("extra.Second")` call immediately afterward succeeds. This proves that **the newly added source can be used for subsequent class lookups** in the demo configuration.
5. Re-adding a duplicate URL and adding `null` do not increase the element count.
6. After closing the loader, **an already defined class** can still be used via its surviving `Class<?>`, objects, and metadata. `close()` is not a command to "delete classes from the JVM."

Do not conclude from item 4 that **every** `NoClassDefFoundError` in bytecode or every previously failed resolution result will automatically heal after appending a URL. The `ClassNotFoundException` in the example arises from a **direct `loader.loadClass` call**; the JVM also has caching/linking semantics for symbolic references. For plugin runtimes, avoid designs that rely on patching the classpath after part of a dependency graph has already failed linking.

### JAR Loading Variant

In the example, `build/second` is a directory URL. If you want to load from a JAR instead, after compiling the second class:

```bash
jar --create --file second.jar -C build/second .
```

Replace the `second` declaration in `UrlPathsDemo.java` with:

```java
URL second = Path.of("second.jar")
        .toAbsolutePath().toUri().toURL();
```

After recompiling `UrlPathsDemo` and running with `java -cp build/app UrlPathsDemo`, the custom loader will find `extra/Second.class` inside `second.jar`. This is a **program variant**, not an extra `second` variable declaration to copy into the same scope.

`Path.toUri().toURL()` for a directory includes a trailing `/`, matching the `URLClassLoader` contract. A `file:` URL pointing to a JAR does not end with `/`; manually concatenating URLs as strings easily causes confusion between directories and archives. Use `Path.toUri().toURL()` instead of `"file:" + path` to handle spaces and special characters properly.

## 7. Important Limits of addURL

### 7.1. Only Modifies the Search Path of the Loader It Is Called On

`append` calls `addURL` on **a single URLClassLoader instance**. By contract, it does not:

- Change `System.getProperty("java.class.path")`.
- Change the class search path of the bootstrap/platform/system loaders.
- Change the configuration of other `URLClassLoader` instances.
- Force other class loaders to use the newly added URL.
- Automatically add a new module to a named module graph or module layer.

If the host framework uses a different loader to find plugins, appending a URL to a self-created loader **without placing that loader on the class loading path** will have no effect. You must call `loader.loadClass(...)` or the appropriate plugin API.

### 7.2. Cannot Replace an Already Defined Class

The JVM identifies an ordinary class or interface by **(binary name, defining class loader)**. If a loader has already defined `com.example.Plugin` from `v1.jar`, adding `v2.jar` containing the same binary name will not make the loader reload `v2` under that name.

Example:

```text
URL loader path = [v1.jar]
loadClass("com.example.Plugin") -> Class object P1

addURL(v2.jar)
loadClass("com.example.Plugin") -> still uses Class P1
```

Distinguish between **re-requesting the same name on the same loader** and **creating a new loader** (which can define a different class with the same name). A new loader produces **a different runtime type**, causing `ClassCastException` if the host and plugin have two separate copies of the API/interface. Plugin designs should place the shared API on an appropriate parent loader and define only implementations in the dedicated plugin loader.

### 7.3. Parent Delegation Can Win Over the New URL

If the parent has already defined `com.acme.Config`, adding `override.jar` containing `com/acme/Config.class` to the child will not replace the class returned by the parent under default parent-first search.

Also distinguish between **ClassLoader.loadClass** and **findClass**. `URLClassLoader.findClass` only searches for the class in the loader's URL path; `loadClass` also checks already-loaded classes and parent delegation. Do not call `findClass` directly to bypass the parent without a clear architectural reason.

### 7.4. A New URL Does Not Guarantee a Complete Dependency Graph

A JAR may reference classes in other JARs. Adding the URL of `plugin.jar` lets the loader see the plugin's bytecode, **without automatically guaranteeing** sufficient transitive dependencies. If a referenced method, field, or class is missing at link or run time, you can still encounter `NoClassDefFoundError`, `NoSuchMethodError`, `VerifyError`, or `ClassNotFoundException` depending on the path taken.

There is no guarantee that a JAR can be used as a "safe" plugin simply because `getURLs()` returns its name. Package sealing, version conflicts, code sources, resource collisions, and module access must still be considered.

### 7.5. getURLs() Does Not Reflect Parent, Manifest, and Module Graph as an Inventory

A `URLClassLoader` can access `java.lang.String` through its parent, yet `getURLs()` does not include those platform classes. A JAR with `Class-Path` in its manifest can also cause class/resource lookups to involve locations **not all of which are represented as directly appended URLs**. Therefore, treat `getURLs()` as **the instance's configured URL search path**, not a canonical representation of the entire dependency graph or transitive sources.

### 7.6. Do Not Use getURLs() by Casting the System Loader to URLClassLoader

Legacy code:

```java
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
URL[] urls = app.getURLs();
```

This may have worked on some default JDK 8 setups, but it is **not portable**: starting in JDK 9, Oracle/OpenJDK's built-in application class loader is no longer a `URLClassLoader`. The cast can throw `ClassCastException`. `ClassLoader.getSystemClassLoader()` is declared to return `ClassLoader`, promising no specific concrete type.

If your goal is to diagnose the startup classpath, use launcher/build configuration, `System.getProperty("java.class.path")`, and environment details (noting that this property does not contain every custom loader or module). If your goal is to extend plugin sources, **create and manage your own `URLClassLoader`** instead of mutating the system loader.

## 8. What Does close() Mean for getURLs and addURL?

`URLClassLoader` implements `Closeable`/`AutoCloseable`; the `close()` method was added in Java 7, making it suitable for `try-with-resources`.

When closed:

- The loader can no longer be used to **load new classes/resources defined or found by itself**.
- Classes/resources provided by the parent remain accessible via delegation.
- Classes/objects loaded before closing can still exist and continue to be used.
- For `jar:` and `file:` URLs, the loader attempts to close files it opened itself; `close()` may throw `IOException`, with additional errors potentially attached as suppressed exceptions.
- Calling `close()` again has no effect; `addURL` after close also **has no effect**.
- If one thread is loading a class while another thread calls `close()`, the Javadoc states that the result of that load is **undefined**.

Example of what to avoid:

```java
URLClassLoader loader = new URLClassLoader(urls, parent);
// Thread A: loader.loadClass(...)
// Thread B: loader.addURL(...), loader.close(), loader.addURL(...)
// Do not design around concurrent interactions lacking synchronization and lifecycle rules.
```

The snippet above is architectural pseudo-code only, not a standalone program. Manage synchronization, ownership, and loader state at the application layer. In plugin managers, it is common to use one loader per plugin generation, block new load operations before closing, and release references whenever possible.

**Closing a loader does not force the JVM to unload classes immediately.** The JVM can only reclaim them when the loader and its associated metadata/objects become eligible for GC; threads, static caches, TCCL, and callbacks may still retain references.

**Reading `getURLs()` after close does not prove the loader is still usable.** It describes the existing configuration; to determine lifecycle state, track the state you manage yourself and observe API outcomes, rather than relying on the URL array still being returned.

## 9. Choosing the Right Solution for Your Goal

| Need | Recommended choice | Avoid |
| --- | --- | --- |
| List the URLs configured on **an actual URLClassLoader** | `thatUrlLoader.getURLs()` | Assuming it is the entire Java classpath. |
| Load classes from a new JAR/directory with a dedicated loader | Create `URLClassLoader(urls, parent)` or a subclass exposing controlled `append` | Casting the application loader to `URLClassLoader`. |
| Find a class already present in the application environment | `Class.forName` or `ClassLoader.loadClass` with the right loader | Adding a new URL unrelated to the missing source. |
| Read a resource inside a JAR | `Class.getResourceAsStream`/`ClassLoader.getResourceAsStream` | Inferring from `getURLs` and manually converting every URL to a `File`. |
| Inspect multiple resources with the same name | `getResources` on the actual loader | Believing `getURLs` determines the entire resource order. |
| Load providers via SPI | `ServiceLoader` with the appropriate parent/loader/module | Guessing which class names exist in every JAR via the URL array. |
| Add fixed dependencies at startup | Configure `-cp` or module path in the launcher/build tool | Calling `addURL` mid-process without state control. |
| Hot-reload plugins / switch versions | Design a new loader per generation, managing shared API and lifecycle | Appending a new JAR and expecting already-loaded classes to be replaced. |
| Find the source of a specific class | Inspect `clazz.getClassLoader()`, code source when available, and class loading debug logs | Assuming `getURLs()[0]` definitely contains that class. |

A dedicated loader with `parent = ClassLoader.getPlatformClassLoader()` as in the demo typically works well for plugins that do not depend on host-specific interfaces. If a plugin needs to implement host interfaces, the parent should be a loader that **sees the same host API definitions**, otherwise type incompatibility can occur even when binary names match.

## 10. How to Debug When addURL Does Not Produce the Expected Result

When `append(pluginUrl)` completes but you still encounter `ClassNotFoundException`:

1. **Verify the instance:** Is the code calling `loadClass` on **the exact loader that was appended to**? Is a framework using TCCL, the system loader, or another child loader instead?
2. **Inspect `getURLs()`:** Is the URL at the end of the path? If not, check for `null`, duplicates, closed state, or whether the wrapper actually calls `super.addURL`.
3. **Check the URL scheme:** A directory URL should end with `/`, and a JAR path should point to the JAR file. Use `Path.toAbsolutePath().toUri().toURL()` to avoid path-escaping bugs.
4. **Check the file/entry:** Does `jar tf plugin.jar` actually show `com/acme/Plugin.class`? The binary name passed to `loadClass` must be `com.acme.Plugin`, not `com/acme/Plugin.class`.
5. **Check parent delegation:** Has the parent already defined a class with the same name? If so, the child may never read the new entry.
6. **Check transitive dependencies:** Does the plugin JAR have the target class but lack base classes, interfaces, or APIs needed by the verifier/linker?
7. **Read the full exception:** `ClassNotFoundException` differs from `NoClassDefFoundError`, `ClassFormatError`, `LinkageError`, or `ClassCastException`. Do not lump all loading/invocation errors into "addURL doesn't work."
8. **Verify lifecycle:** Was the loader `close()`d or replaced by another instance? Is a thread still holding the old loader?
9. **Do not rely on accidental ordering:** If two URLs contain duplicate classes/resources, choose an explicit order and avoid duplicate dependencies.
10. **Do not use `getURLs` as final proof:** Inspect the actual resulting `Class<?> clazz`, `clazz.getClassLoader()`, resource URLs, and deployment sources when appropriate.

How to inspect resources of a controlled loader:

```java
// Snippet inside a method that has a URLClassLoader named loader:
URL[] configured = loader.getURLs();
for (URL url : configured) {
    System.out.println("configured: " + url);
}

var found = loader.getResource("com/acme/config.properties");
System.out.println("found: " + found);
```

`found` may come from the parent or from the loader's URLs according to resource lookup rules. Do not use the printed path to infer there are no security or encapsulation issues; in named modules, some resources are also subject to module access rules.

HotSpot provides `-Xlog:class+load=info` logging to observe class loading sources:

```bash
java -Xlog:class+load=info -cp build/app UrlPathsDemo
```

This command prints many additional JVM lines, so **do not use it as the baseline stdout for the Section 6 experiment**. Class loading logs are not a complete record of every URL or resource lookup.

## 11. Common Mistakes and Fixes

| Mistake or assumption | Why it is wrong | How to fix |
| --- | --- | --- |
| `URLClassLoader addURL` can be called directly from any class | `addURL` is `protected`. | Subclass it to create an authorized wrapper and control sources. |
| After append, `getURLs()` grows so every class in the JAR is loaded | The API only changes the search path. | Load classes only when needed; inspect the actual `Class<?>` returned. |
| `getURLs()` returns 1 URL so the loader only sees 1 source | Parent delegation can still provide classes. | Analyze both the parent and the loader graph. |
| Adding a duplicate URL twice changes its priority | `addURL` ignores duplicate URLs. | Create a new loader with the desired path order. |
| Appending `null` creates a placeholder entry | The API ignores `null`. | Validate input configuration beforehand. |
| Adding `v2.jar` updates an already loaded `v1` class | Class identity is tied to defining loader and binary name. | Create a new loader for the new plugin generation, managing shared APIs. |
| Casting the system loader to `URLClassLoader` to call `addURL` | The JDK 9+ built-in app loader is not a `URLClassLoader`. | Use your own loader, launch-time classpath, or the proper framework API. |
| Appending after `close` still works | `addURL` after `close` has no effect. | Create a new loader or keep the loader open for its proper lifecycle. |
| Directory URL missing a trailing `/` | `URLClassLoader` may misinterpret the source type. | Use `Path.toUri().toURL()`, and verify the URL. |
| `getURLs` shows the URL but `findClass` cannot find the class | The URL may be broken, missing the entry, or lack access permissions. | Check the file, archive, and class-file path. |
| Parent has a class with the same name but plugin should override it | Parent-first selects the parent first. | Design deliberate package/loader isolation; avoid arbitrary overrides. |
| Calling `close` concurrently with `loadClass` | The Javadoc specifies the outcome of the ongoing load is undefined. | Synchronize the plugin loader lifecycle. |

## 12. Review Questions with Answers

1. **Does `getURLs()` list JDK bootstrap/platform module classes?**  
   No. It returns the search URLs configured for that `URLClassLoader` itself, while the parent and modules operate separately.
2. **Is `addURL` a public method?**  
   No, it is `protected`. From an authorized subclass, use `super.addURL(url)`, or create a new loader with constructor URLs.
3. **What does `addURL(null)` do?**  
   Nothing, according to the Javadoc.
4. **Does re-appending an already existing URL increase `getURLs().length`?**  
   No; duplicate URLs are ignored.
5. **In a default parent-first loader, if the parent has already loaded class `p.X`, does appending a JAR containing `p.X` to the child replace it?**  
   No; lookup will continue to return the class defined by the parent.
6. **Does adding a JAR to a loader immediately initialize every class inside it?**  
   No; it only expands the search sources and does not run constructors or static initializers.
7. **Why was the `ClassNotFoundException` before append in the demo resolved after append?**  
   Because the subsequent direct `loader.loadClass` call used the expanded search path and found the previously undefined class.
8. **Can you rely on appending to cure every `NoClassDefFoundError` that already occurred during linking?**  
   No. Resolution and loading have their own semantics; design initialization and dependency loading consistently.
9. **Does `close()` destroy already defined `Class<?>` objects?**  
   No. Already loaded classes can continue to be used; `close` primarily restricts new loads and closes open resources.
10. **When a plugin needs host interfaces, what parent should be chosen?**  
    A loader that can provide the same host API/interface definitions; do not automatically pick the platform loader if the plugin needs host types.
11. **Is modifying elements in the `getURLs()` array the official way to append?**  
    No. `getURLs` is for viewing the search path; appending is done through the `addURL` method subject to access and lifecycle rules.
12. **If `getURLs()` has three URLs but `ClassLoader.loadClass` finds a class from the parent, who is the class's defining loader?**  
    The parent (if the parent directly defined the class), not necessarily the `URLClassLoader` holding those three URLs.

## 13. Authoritative References

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `getURLs`, `addURL`, `findClass`, constructors, `close`, and limits when the loader is closed.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, parent delegation, and type identity.
- [Java SE 21 — URL](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URL.html): URL protocols, equality, and path syntax.
- [Java SE 21 — Path.toUri](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toUri()): converting directory/JAR paths to properly formatted URIs.
- [Java SE 21 — JarFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): archive mechanisms when reading or inspecting entries.
- [JVM Specification `5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): binary name and defining class loader.
- [Oracle JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): changes to the built-in application loader; no longer a `URLClassLoader` subtype.
