# Class Loaders and Resource Lookup Scope in Java

## 1. When a Resource Exists in the Project but Java Reports "Not Found"

A multilingual Java application typically stores messages in `.properties` files, templates, images, configurations, or text data alongside program code. When running in the IDE, the program may find `messages_vi.properties`, yet after packaging into a JAR or moving into a plugin, it receives `null` or `MissingResourceException`.

This is not necessarily because the file was deleted. Very likely, **the file exists, but it is outside the search scope of the class loader or module being used**.

For example, suppose a resource is packaged at the path:

```text
demo/messages_vi.properties
```

but the code calls:

```java
SomeClass.class.getClassLoader()
        .getResource("messages_vi.properties");
```

Then the class loader searches for the name `messages_vi.properties` **directly under the root of the resource lookup path**, without automatically prepending `demo/`. If the file is at `demo/messages_vi.properties`, the proper name for `ClassLoader.getResource` is usually `"demo/messages_vi.properties"`.

Another scenario: code in the main application uses the **application class loader**, while the translation file resides inside a **plugin JAR loaded by a different URLClassLoader**. The application loader's search path does not automatically include all plugin loaders in the JVM.

With Java 9+ and Java 17, there is also the **Java Platform Module System (JPMS)**: a resource inside a **named module** can be encapsulated and hidden from code outside the module, even when the package containing the resource has been exported for type access.

This lesson focuses on: the classpath, class loader identity, resource names, relative/absolute lookup, `ResourceBundle`, JARs, thread context class loaders, named modules, common errors, and testing on Java 17.

## 2. Resources Are Different from Java Classes and OS Files

A **resource** is data used by an application at runtime that is not necessarily class bytecode: `.properties`, `.json`, `.txt` files, images, templates, certificates, etc. First, let's distinguish:

| Item | Example | Typical access method |
| --- | --- | --- |
| Java Class | `demo.App` | `ClassLoader.loadClass("demo.App")` |
| Resource on classpath | `demo/messages_vi.properties` | `Class.getResourceAsStream` or `ClassLoader.getResourceAsStream` |
| ResourceBundle | `demo.Messages` with `Messages_vi.properties` files | `ResourceBundle.getBundle("demo.Messages", locale)` |
| External file on disk | `/etc/app/config.properties` or `C:\data\settings.txt` | `Path`, `Files`, `FileInputStream` |
| Resource in a JAR | Entry `demo/messages_vi.properties` | Typically read via a resource stream from the class loader/module |
| Resource in a named module | `demo/messages_vi.properties` inside module `app.main` | `Class.getResourceAsStream` or `Module.getResourceAsStream` subject to encapsulation rules |

**A resource on the classpath is not an operating system file path**. Java resolves a resource name as a `/`-separated string within configured roots; it can come from a directory or from a JAR. If the file resides in a JAR, you generally cannot apply `Path.of(url.toURI())` as you would with a normal file on disk.

Do not use `new File("src/main/resources/...")` in runtime code: `src/main/resources` is a source path in the project, **not a path guaranteed to exist when running a distributed build**.

### 2.1. What Is the "Classpath Root"?

Suppose you have the output layout:

```text
out/
  demo/
    App.class
    messages.txt
  l10n/
    Messages.properties
    Messages_vi.properties
  settings.json
```

When running `java -cp out demo.App`, `out` is the **classpath root**, not the `demo` directory:

- The name `demo/messages.txt` points to `out/demo/messages.txt`.
- The name `l10n/Messages_vi.properties` points to `out/l10n/Messages_vi.properties`.
- The name `settings.json` points to `out/settings.json`.
- The name `messages.txt` will not automatically point to `out/demo/messages.txt`.

If resources are inside a JAR, the classpath root is understood as the **root of the entries in the JAR**. For example, the entry `l10n/Messages_vi.properties` in `app.jar` has the same logical resource name as in `out/l10n/…`.

## 3. ClassLoader and Lookup Scope

`java.lang.ClassLoader` is responsible for loading classes and provides APIs for finding resources. Every class at runtime is identified not only by its **fully qualified name** but also by its **defining class loader**. Two different loaders can define two classes with the same name that the JVM treats as two distinct types.

For resources, the key points are:

- Each loader has its own **search path** and delegation strategy.
- A resource is found only if it is visible through the active loader **and** satisfies module/encapsulation rules.
- `getResource(...)` returns a **`URL`** or `null`.
- `getResourceAsStream(...)` returns an **`InputStream`** or `null`.
- **Multiple resources with the same name** can exist on the classpath; a single-result API does not mean all of them were checked.
- With default parent delegation, the parent may be searched before the child; a custom loader may implement a different strategy.

### 3.1. Three Important Loaders in Java 17

In a standard Java runtime there are typically:

1. **Bootstrap class loader:** loads core platform classes; in Java APIs it is commonly represented as `null` when querying the loader of certain platform classes.
2. **Platform class loader:** `ClassLoader.getPlatformClassLoader()`; associated with platform modules.
3. **System/application class loader:** `ClassLoader.getSystemClassLoader()`; typically loads application classes per launcher configuration.

However, real-world systems can have other loaders: `URLClassLoader`, container loaders, plugin loaders, module layers, test runners, app servers, or framework loaders.

**Do not assume every class's loader is the system loader.** The reliable approach is to check where the class in question was loaded from using `MyClass.class.getClassLoader()` and know clearly which loader manages the resource you need.

Illustrative example:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader mine = MyClass.class.getClassLoader();
ClassLoader context = Thread.currentThread()
        .getContextClassLoader();
```

This snippet sits inside a method where class `MyClass` is in scope. The three references **may be identical or different**; do not treat their equality in a single local run as a rule for all containers/plugins.

### 3.2. Parent Delegation Does Not Search All Loaders

In standard `ClassLoader.getResource(name)`, the default mechanism checks the parent first and then searches locally when needed. For example:

```text
Application / Parent Loader
          |
          +----> plugin loader A
          |
          +----> plugin loader B
```

If A and B are two separate child loaders, a resource located only in B **does not automatically appear** when code queries A or queries the parent. The parent does not know about every child, and a child does not inherently look up siblings.

Some frameworks implement **child-first** or custom rules to isolate plugins. Do not assume every `ClassLoader` is parent-first if you are working in an environment with custom loaders.

## 4. Class.getResource and ClassLoader.getResource: Different Names and Root Positions

These two API families look similar, yet they resolve names differently:

| API | What does `"hello.txt"` mean? | What does `"/demo/hello.txt"` mean? |
| --- | --- | --- |
| `demo.App.class.getResource(name)` | Relative to package `demo` -> `demo/hello.txt` | Absolute root of the resource namespace -> `demo/hello.txt` |
| `demo.App.class.getResourceAsStream(name)` | Relative to package `demo` | Uses absolute root when prefixed with `/` |
| `demo.App.class.getClassLoader().getResource(name)` | Direct name from the classpath resource root | Do **not** add a leading slash; use `demo/hello.txt` |
| `ClassLoader.getSystemResource(name)` | Search root of the system class loader | Do **not** use a leading slash as with `Class.getResource` |

**Practical rules:**

- With `Class.getResource("name")`, **no leading `/`** -> the name is prefixed with the anchor class's package.
- With `Class.getResource("/some/path")`, **with a leading `/`** -> the name starts from the root; Java strips this slash when passing it to the underlying resource lookup mechanism.
- With `ClassLoader.getResource("some/path")`, use a **name relative to the root, without a leading slash**. Do not pass `"/some/path"` out of habit from `Class.getResource`.

In a **named module**, `Class.getResource` is also aware of the module to which the anchor class belongs; its access policy differs from `ClassLoader.getResource`, which searches across modules. Those module rules are covered in a dedicated section later.

### 4.1. Why Do Two Approaches Find the Same File?

If `demo.App` has the resource `demo/hello.txt` in the same classpath root, all three calls below can find the same entry:

```java
App.class.getResource("hello.txt");
App.class.getResource("/demo/hello.txt");
App.class.getClassLoader().getResource("demo/hello.txt");
```

This is illustrative code inside class `App` in package `demo` (or a method importing `demo.App`).

**Common mistake:** `App.class.getClassLoader().getResource("/demo/hello.txt")` — the leading slash belongs to `Class.getResource` syntax, not the class loader API syntax. On standard class loaders, this name usually returns `null`.

### 4.2. Not Just for Reading Translations

The same rules apply to images like `logo.png`, text files like `email-template.txt`, JSON files like `schema.json`, or properties. Having a `.properties` extension does not make Java automatically recognize them as resource bundles; only `ResourceBundle.getBundle(...)` has bundle naming, locale candidate lookup, and its own caching mechanism.

## 5. Standalone Java 17 Example: Seeing Resource Lookup Scope Clearly

Prepare the directory structure:

```text
project/
  src/
    demo/
      ResourceScopeDemo.java
  resources/
    demo/
      greeting.txt
```

Contents of `resources/demo/greeting.txt` (UTF-8):

```text
Xin chào
```

Save `src/demo/ResourceScopeDemo.java`:

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class ResourceScopeDemo {
    public static void main(String[] args) throws Exception {
        Class<?> anchor = ResourceScopeDemo.class;
        ClassLoader loader = anchor.getClassLoader();

        System.out.println("relative=" +
                (anchor.getResource("greeting.txt") != null));
        System.out.println("absolute=" +
                (anchor.getResource("/demo/greeting.txt") != null));
        System.out.println("loaderRoot=" +
                (loader.getResource("demo/greeting.txt") != null));
        System.out.println("wrongLoaderPath=" +
                (loader.getResource("greeting.txt") != null));

        try (InputStream input = Objects.requireNonNull(
                anchor.getResourceAsStream("greeting.txt"),
                "greeting.txt not found")) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println("content=" + text);
        }
    }
}
```

Compile and prepare the classpath (Bash shell on macOS/Linux; on Windows PowerShell perform equivalent copy operations):

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/ResourceScopeDemo.java
cp resources/demo/greeting.txt out/demo/greeting.txt
java -cp out demo.ResourceScopeDemo
```

Stdout with the exact structure specified:

```text
relative=true
absolute=true
loaderRoot=true
wrongLoaderPath=false
content=Xin chào
```

Interpretation:

- `getResource("greeting.txt")` from `demo.ResourceScopeDemo` looks up `demo/greeting.txt`.
- `getResource("/demo/greeting.txt")` starts from the root and reaches the same resource.
- `loader.getResource("demo/greeting.txt")` uses a root-relative path.
- `loader.getResource("greeting.txt")` looks in the wrong location and thus returns `null` on a test classpath containing only the stated resource.
- The `InputStream` is closed with `try-with-resources`, and UTF-8 bytes are decoded explicitly.

Do not use `Objects.requireNonNull` if the product wants a soft fallback; this example intentionally **fails fast** when a required resource is missing to avoid a blank screen with no message.

### 5.1. A Resource Path Is a Logical Path, Not an OS Path

Even on Windows, resource names still use forward slashes **`/`**, such as `"demo/greeting.txt"`, rather than OS-dependent `"demo\\greeting.txt"`. The classpath is configured by the JVM using the launcher's syntax; resource entry names themselves are slash-separated.

**Distinction to keep in mind:** in the `java -cp` command, **classpath entries** are separated by an OS-dependent character (typically `:` on Unix, `;` on Windows). However, **resource names inside an entry** still use `/`.

## 6. Null, URL, and InputStream: Finding Does Not Equal Reading Successfully

`Class.getResource`/`ClassLoader.getResource` returns a `URL` or `null`. `getResourceAsStream` returns an `InputStream` or `null`, and does not throw `FileNotFoundException` when a resource is missing.

Proper error-handling example:

```java
try (InputStream in = App.class.getResourceAsStream(
        "/l10n/Messages_vi.properties")) {

    if (in == null) {
        throw new IllegalStateException("Missing resource");
    }

    byte[] data = in.readAllBytes();
    // Decode using the charset agreed upon with the resource author.
}
```

This is an illustrative snippet inside a method of `App`, handling `IOException` and importing `InputStream`.

Depending on the resource type, `URL.openStream()` or `getResourceAsStream` can throw `IOException` while reading; verifying that a resource URL exists **does not** guarantee the file can be read completely. In practice, permissions, corrupt JAR files, resource providers, or I/O failures can still occur.

**Do not turn every missing resource into `null` and silently continue.** In a multilingual system, a missing required message file should be reported clearly, with a designed and tested fallback.

### 6.1. Reading Resources Inside a JAR

When packaged, the URL can look conceptually like:

```text
jar:file:/opt/app/app.jar!/demo/greeting.txt
```

This is **not** a default-filesystem `Path` that can be passed directly to `Files.readString(Path.of(url.toURI()))` in every environment.

When you only need text or binary contents, use a stream:

```java
try (InputStream in =
        App.class.getResourceAsStream("/demo/greeting.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing resource");
    }
    String text = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
}
```

This snippet sits inside a method of `App` with `StandardCharsets` imported. Stream reading works for classpath directories and JARs if the loader/module permits access. Do not assume a URL can always be opened as a file path or that the file is writable.

## 7. How Does ResourceBundle Use the Class Loader?

`java.util.ResourceBundle` operates at a higher level: retrieving a **family** of resources by `baseName` and `Locale`, with candidate rules, fallback, and caching.

Example family:

```text
l10n/
  Messages.properties
  Messages_en.properties
  Messages_vi.properties
  Messages_vi_VN.properties
```

The files usually contain `key=value` pairs. Calling:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "l10n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

During lookup, `ResourceBundle` treats `baseName` as a **package-style, dot-separated** name, not a full filename:

- `"l10n.Messages"` -> `l10n/Messages.properties` and its locale variants.
- `"l10n.Messages_vi"` is not the right `baseName` if you want the system to select locales from `l10n.Messages`.
- Do not pass `"l10n/Messages.properties"` expecting `getBundle` to behave like `getResourceAsStream`.
- If no suitable bundle is found and there is no valid fallback path, `getBundle` throws `MissingResourceException` instead of returning `null`.

In Java 17, overloads without a `ClassLoader` parameter are defined in terms of the **caller module** (and associated loader rules when running in an unnamed module); do not assume they always use the **thread context class loader**.

### 7.1. Specifying the Loader Explicitly When Needed

For classpath applications or plugins in an unnamed module, there is an overload:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "l10n.Messages", locale, targetLoader);
```

Meaning:

- `"l10n.Messages"` is the base name.
- `locale` is the target locale, **not the class loader**.
- `targetLoader` defines the classpath/resource scope for locating the bundle in the appropriate API context.

Do not pass the system loader to this overload if the resource actually belongs only to a child plugin loader. Likewise, do not overuse custom loaders for all bundles in a **named module**: JPMS has its own module, visibility, and provider rules; you may need the overload taking `Module` or a `ResourceBundleProvider`.

### 7.2. Runnable Java 17: Same Loader, Two Locales

Prepare:

```text
project/
  src/demo/BundleScopeDemo.java
  resources/l10n/Messages.properties
  resources/l10n/Messages_vi.properties
```

File `resources/l10n/Messages.properties`:

```properties
hello=Hello
appName=Example
```

File `resources/l10n/Messages_vi.properties` (UTF-8):

```properties
hello=Xin chào
appName=Ví dụ
```

Source `src/demo/BundleScopeDemo.java`:

```java
package demo;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleScopeDemo {
    public static void main(String[] args) {
        ClassLoader loader =
                BundleScopeDemo.class.getClassLoader();

        ResourceBundle root = ResourceBundle.getBundle(
                "l10n.Messages", Locale.ROOT, loader);
        ResourceBundle vietnamese = ResourceBundle.getBundle(
                "l10n.Messages",
                Locale.forLanguageTag("vi-VN"),
                loader);

        System.out.println("root=" + root.getString("hello"));
        System.out.println("vi=" + vietnamese.getString("hello"));
        System.out.println("viName=" +
                vietnamese.getString("appName"));
    }
}
```

Bash:

```bash
mkdir -p out/l10n
javac -encoding UTF-8 -d out src/demo/BundleScopeDemo.java
cp resources/l10n/Messages*.properties out/l10n/
java -cp out demo.BundleScopeDemo
```

With the files and standard JDK 17, stdout:

```text
root=Hello
vi=Xin chào
viName=Ví dụ
```

`ResourceBundle` finds a matching translation from the family. In this example, `Messages_vi.properties` is present without needing `Messages_vi_VN.properties`; locale `vi-VN` can receive the `vi` variant via the candidate lookup mechanism. That is the **bundle selection mechanism**, not `ClassLoader` guessing the language.

**Encoding note:** since JDK 9, `PropertyResourceBundle` reads `.properties` files as UTF-8 by default with a legacy ISO-8859-1 compatibility strategy; system properties such as `java.util.PropertyResourceBundle.encoding` can affect this. For Java 17, save bundles consistently in UTF-8 and pin/runtime-test if legacy data exists.

### 7.3. Bundle Caching: Editing a File May Not Take Effect Immediately

`ResourceBundle.getBundle` caches by default; the same `baseName`/`locale`/`loader` can return a cached bundle rather than re-reading the file immediately. When replacing a translation file while the application is running, replacing the file alone does not guarantee the application loads the new version.

There is an API such as:

```java
ResourceBundle.clearCache(loader);
```

However:

- It applies to the resource bundle cache; it does not alter the classpath or a loader's resource visibility.
- It does not automatically refresh resources inside a JAR unless the JAR file itself is properly replaced.
- With named modules and providers, cache/visibility management has its own rules.
- Per-loader caching interacts with plugin lifecycles and the risk of retaining references to stale data.

This is an illustrative snippet inside a method that has a `loader` variable. Do not treat `clearCache` as a fix for a wrong path or a missing package open.

## 8. Custom Class Loaders and Plugins: Resources Do Not Automatically Cross Loaders

A plugin may be stored separately outside the main classpath:

```text
project/
  src/demo/PluginResourceDemo.java
  plugin-data/
    plugin/
      Labels.properties
```

File `plugin-data/plugin/Labels.properties`:

```properties
title=Plugin loaded
```

We create a `URLClassLoader` pointing to the `plugin-data` directory. This loader sees resources that the application classpath does not necessarily know about.

### Runnable Java 17: Separate Loader for a Bundle

File `src/demo/PluginResourceDemo.java`:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Locale;
import java.util.ResourceBundle;

public class PluginResourceDemo {
    public static void main(String[] args) throws Exception {
        URL root = Path.of("plugin-data")
                .toAbsolutePath().toUri().toURL();

        // Parent null: isolate from application classpath
        // in this simple demo.
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[]{root}, null)) {

            boolean visible = pluginLoader.getResource(
                    "plugin/Labels.properties") != null;

            ResourceBundle labels = ResourceBundle.getBundle(
                    "plugin.Labels", Locale.ROOT, pluginLoader);

            System.out.println("pluginVisible=" + visible);
            System.out.println("title=" +
                    labels.getString("title"));
        }
    }
}
```

Run from the `project` directory with Bash:

```bash
mkdir -p out
javac -encoding UTF-8 -d out src/demo/PluginResourceDemo.java
java -cp out demo.PluginResourceDemo
```

Stdout with `plugin-data/plugin/Labels.properties` set up as described:

```text
pluginVisible=true
title=Plugin loaded
```

**Why use `parent=null` in the example?** To emphasize the plugin's resource root and avoid a situation where the application parent already contains a resource of the same name. In a production plugin, the parent loader should not arbitrarily be set to `null`: plugins may need host API classes or shared libraries, and delegation policies affect type identity/security. Use the framework's loader strategy or an explicit classloading design.

**Do not confuse:** `URLClassLoader` is passed the URL of the **root directory** `plugin-data`, not the URL of `plugin-data/plugin/Labels.properties`. The resource path `plugin/Labels.properties` is resolved relative to that root.

### 8.1. When a Plugin Resides Inside a JAR

If a plugin is packaged in `plugin.jar` with entry `plugin/Labels.properties`, a `URLClassLoader` initialized with the URL of **the JAR file itself** can read the resource using the same logical name. How it is set up depends on packaging, dependency visibility, and Java module architecture.

You cannot simply drop a JAR into an arbitrary directory and expect an already-created application loader to scan it automatically. You must configure the classpath/module path at startup or construct an appropriate plugin loader/layer.

## 9. Thread Context Class Loader (TCCL): A Framework Tool, Not Magic

Each Java thread can have a **context class loader**, typically read with:

```java
ClassLoader tccl = Thread.currentThread()
        .getContextClassLoader();
```

Some libraries and frameworks (including certain service discovery mechanisms) use the TCCL to locate classes/resources when library code does not know the specific application/plugin loader ahead of time.

However, **not every** resource API automatically uses the TCCL:

- `MyClass.class.getResource(...)` relies on the anchor class and its module.
- `MyClass.class.getClassLoader().getResource(...)` uses the class's defining loader.
- `ClassLoader.getSystemResource(...)` uses the system loader.
- `ResourceBundle.getBundle(baseName, locale, loader)` uses the **passed-in loader**.
- `ResourceBundle.getBundle(baseName, locale)` depends on the caller module/loader per the Java 17 overload, **with no guarantee of automatically using the TCCL**.
- `Thread.currentThread().getContextClassLoader()` only returns a reference; the caller must **actively use** it if that is the library's policy.

**Do not "fix" missing resources by setting the TCCL indiscriminately.** Changing the TCCL on a shared thread can affect other libraries, especially in thread pools, async jobs, and application servers.

### 9.1. When Temporarily Setting the TCCL Is Necessary

A framework sometimes does:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call a library designed to use the TCCL.
    // Explicit example: use the TCCL itself to look up the resource.
    ClassLoader current = thread.getContextClassLoader();
    URL url = current.getResource("plugin/Labels.properties");
} finally {
    thread.setContextClassLoader(previous);
}
```

This is illustrative code inside a method with `pluginLoader` and `java.net.URL` imported. `try/finally` ensures the previous loader is restored upon completion. With thread pools or asynchronous callbacks, do **not** assume the TCCL is automatically propagated across every mechanism or restored by every library.

### 9.2. Distinguishing the Three Identities

In a plugin system, there can be differences among:

1. **The calling class's defining loader** (`SomeService.class.getClassLoader()`).
2. **The system loader** (`ClassLoader.getSystemClassLoader()`).
3. **The thread's context loader** (`Thread.currentThread().getContextClassLoader()`).

If they differ, picking the wrong API can make a program work only in the IDE but fail in an app server. Log **loader identities** using non-sensitive metadata when diagnosing, avoiding dumping full internal paths or secrets.

## 10. JPMS: Named Modules Add Another Boundary for Resource Lookup

Since Java 9, alongside class loaders there are **modules**. Java 17 distinguishes:

- **Unnamed module**: typically holds classes/resources run on the classpath.
- **Named module**: has a module name and `module-info.java` rules, exports, opens, requires, and resource encapsulation.

A class in a named module can access resources **belonging to its own module** via `Class.getResourceAsStream` (with the right name). However, `ClassLoader.getResource`, which searches via a loader across modules, enforces stricter encapsulation rules.

According to the Java 17 API, a **non-`.class`** resource in a package of a named module can generally be found via `ClassLoader.getResource` only if that package is **opened unconditionally**. A package that is only `exports`-ed for class access **is not equivalent** to `opens` for resource access.

### 10.1. Exports and Opens Are Not the Same

| Declaration | Primary purpose | Does it mean resources are visible through any loader? |
| --- | --- | --- |
| `exports demo.api;` | Lets other modules use public types in the package | **No** |
| `opens demo.i18n;` | Opens the package for deep reflection and certain resource access | May allow resource access under JPMS rules |
| `opens demo.i18n to some.module;` | Conditionally opens to a specific module | **Not enough** for `ClassLoader.getResource`, which requires *unconditional* opens |
| No `opens` | Package is encapsulated | Owning module can read internally; external access may be denied |

**Scope warning:** `ClassLoader.getResource` and `Module.getResourceAsStream` have different conditions. On named modules, `ClassLoader.getResource` requires unconditional opens for non-`.class` resources in a package. `Module.getResourceAsStream` can allow access when the package is opened to the **caller module**, and code inside the owning module has appropriate internal access. Do not infer one API's behavior from the other.

### 10.2. Module.getResourceAsStream

`Module.getResourceAsStream(name)` can read a resource from the **specified module** per the Java 17 API; it throws `IOException` if reading fails and returns `null` if the resource does not exist or is not visible.

Example inside a class of a named module:

```java
Module ownModule = SomeClass.class.getModule();

try (InputStream stream = ownModule.getResourceAsStream(
        "demo/i18n/Messages_vi.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Resource not accessible");
    }
    // Read resource ...
}
```

This is illustrative code inside a method where `SomeClass` belongs to the module, importing `java.io.InputStream` and handling `IOException`. The name here is defined as the resource path inside the module.

To access a resource in **another module**, check whether the package is opened appropriately to the calling module; merely having a `Module` object does not bypass encapsulation boundaries.

### 10.3. Difference Between Class.getResource and ClassLoader.getResource in Named Modules

Per Java 17 documentation:

- `Class.getResource` resolves the resource name relative to the anchor class's package (or absolutely with a leading `/`) and then applies access checks for the module containing that class.
- `ClassLoader.getResource` has loader-level scope and stricter visibility conditions for non-`.class` resources in named modules.
- `Module.getResourceAsStream` targets a specific module, suited when code wants a resource from a particular module (still subject to encapsulation).
- `ResourceBundle` in named modules has its own lookup/provider mechanism and should not be oversimplified to a single `getResource` call.

Therefore, when translation resources sit **next to classes in the same named module**, `Anchor.class.getResourceAsStream("...")` or `Anchor.class.getModule().getResourceAsStream("full/path")` is usually easier to control than searching via the system class loader.

### 10.4. Illustrative module-info.java Example

```java
module demo.app {
    exports demo.api;

    // Example: open the package containing resources unconditionally.
    opens demo.i18n;
}
```

This is an **illustrative descriptor file**, not a standalone runnable program; compiling it requires packages `demo.api`, `demo.i18n`, and a valid project/module structure. Opening a package unconditionally is **not always desirable**. If only internal module code needs to read the resources, do not automatically open them to everyone externally, as that can increase the access surface.

Do not use `opens` merely to paper over a path error when the resource was never packaged into the module/JAR; check packaging first.

## 11. ResourceBundle in Named Modules and Providers

`ResourceBundle.getBundle` has multiple overloads since Java 9:

```java
ResourceBundle local = ResourceBundle.getBundle(
        "demo.i18n.Messages", locale);

ResourceBundle fromModule = ResourceBundle.getBundle(
        "demo.i18n.Messages", locale, module);
```

This is illustrative code assuming `locale` and `module` exist. The overload taking `Module` allows requesting bundle lookup **on behalf of a specific module**, still obeying resource encapsulation.

Key points:

1. In a named module, `getBundle(baseName, locale)` has **caller module** semantics; it does not simply use the system loader for every bundle.
2. Bundles in the same module can be packaged and loaded under internal rules; other modules can access them only when visibility/providers permit.
3. `ResourceBundleProvider` can help provide bundles via service provider modules; this involves `uses`/`provides` declarations in `module-info.java`.
4. `ResourceBundle.Control` is primarily intended for unnamed modules/classpath; overloads with `Control` can throw `UnsupportedOperationException` when used from a named module.
5. For `.properties` resource bundles, make sure the file actually exists in the module artifact with the proper `baseName` and locale suffix.
6. Java caches resource bundles, so changing a class loader/module or translation file may require examining cache lifetime and updates.

### A Common Migration Error

An application migrates from the classpath to the module path, while still calling:

```java
ResourceBundle.getBundle(
        "demo.i18n.Messages", Locale.forLanguageTag("vi-VN"),
        ClassLoader.getSystemClassLoader());
```

The code may no longer find bundles packaged inside a named module due to resource encapsulation, even though it ran fine before modularization. Do not open every package globally just to keep the old call unchanged. Re-select the loading approach based on the **caller's module**, using the `Module` overload or the provider API as fits the project architecture.

## 12. JAR Packaging: Having the Source File Does Not Guarantee the Resource Is in the Artifact

A very common deployment mistake:

```text
src/main/resources/l10n/Messages_vi.properties  ✓ exists on dev machine
target/app.jar / build/libs/app.jar               ? not guaranteed to be included
```

Maven/Gradle/IDEs usually copy resources, yet project-specific configuration can exclude files, change output directories, or filter contents. Hence, when a resource is missing after deployment, inspect the **actual JAR artifact** instead of only checking `src/main/resources`.

An example:

```bash
jar tf app.jar
```

The output must contain the required resource entry, such as `l10n/Messages_vi.properties`, **if that is where the application expects to find it**. The entry name must match the resource path, including letter casing (JAR entry names are normally case-sensitive).

Questions to verify:

- Is the resource actually inside the JAR, or is it only in the source directory without being copied?
- At which root is the resource placed? Does it have an extra prefix like `resources/`?
- What is the actual classpath of `java -cp` or `java -jar`?
- When using `java -jar`, the `-cp` parameter in many cases does not determine the classpath the way one expects; understand the launcher and the JAR's manifest.
- In a fat JAR/special launcher, is there a custom nested-JAR loader or a resource URI other than standard `jar:file`?
- Does the module path change visibility rules compared to the classpath?
- Are there duplicate translations with the same name across multiple dependency JARs?

### Do Not Convert a Resource URL into a Path by Default

A resource inside a JAR is a **JAR entry**, not an ordinary file path. If you need bytes, use `InputStream`. If a third-party library **strictly requires** a physical file path, you may need to extract the resource to a temporary directory with managed lifecycle and safety, or use an appropriate filesystem provider; do not force every URL through `Path.of(...)`.

## 13. Duplicate Resource Names: getResource and getResources

Two dependencies might both package:

```text
config/defaults.properties
```

In that case:

- `loader.getResource("config/defaults.properties")` typically returns only **one** URL found according to the loader's search order.
- `loader.getResources("config/defaults.properties")` returns an `Enumeration<URL>` to iterate over matching resources visible to the loader.
- `loader.resources("config/defaults.properties")` (Java 9+) returns a `Stream<URL>`.
- `ClassLoader.getSystemResources(name)` uses the **system loader**, not a scan across every live loader.

For named modules, `getResources` is also subject to visibility/opens restrictions. Resource ordering across multiple modules in the same loader may be unspecified; do not rely on "which JAR wins" if the application needs deterministic configuration ordering.

### Example: Iterating Over All URLs

```java
ClassLoader loader = App.class.getClassLoader();
Enumeration<URL> urls = loader.getResources(
        "config/defaults.properties");

while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    // Log/extract in a controlled manner.
}
```

This is illustrative code inside a method with `App`, importing `java.net.URL` and `java.util.Enumeration`, and handling `IOException`.

Do not use `getResource` to merge multiple identically named translation files automatically. `ResourceBundle` follows per-locale candidate/fallback rules, not an algorithm that merges every `.properties` resource across JARs. If plugins are allowed to contribute multiple bundles, design an explicit provider/namespace or loader strategy.

## 14. When Does ResourceBundle Throw MissingResourceException?

`MissingResourceException` can occur for different reasons:

1. Incorrect `baseName` (using slashes instead of dots, appending `.properties`, wrong package).
2. No matching bundle exists and there is no root/default fallback per policy.
3. The bundle file exists but was not copied into the classpath/JAR.
4. Code is using the **wrong class loader**; the translation resides in another plugin loader.
5. Code was moved to a **named module** and the resource is hidden by module encapsulation.
6. The resource is in the artifact, but the classpath/module path differs from assumptions.
7. The bundle file exists, yet the requested **key** is absent in the bundle/parent chain.
8. File names have mismatched casing or use non-standard locale suffixes.

Distinguish two errors:

- **Bundle family not found:** `getBundle(...)` throws `MissingResourceException`.
- **Bundle found, key missing:** `bundle.getString("some.key")` also throws `MissingResourceException`, but the cause is that the key is missing from the bundle and its fallback chain.

Do not "fix" all of these errors by creating empty bundles, as that can mask mandatory translations. When preparing content for multiple locales, provide an appropriate **root fallback** and test all required keys.

### 14.1. Diagnose Resource Visibility Before Diagnosing Fallback

An effective workflow:

1. Confirm the resource name according to the namespace of the API being used.
2. Confirm the file is present in the **deployed artifact**.
3. Confirm which class loader/module the code is actually using.
4. Use `getResource` or `getResourceAsStream` in the **exact** namespace to verify whether the resource is visible.
5. Only if the raw resource is visible should you inspect `ResourceBundle` naming, candidate locales, keys, cache, and providers.
6. For named modules, check `exports`/`opens`/resource access rather than extrapolating directly from class loader lookup results.

**Subtle point:** a raw lookup with `ClassLoader.getResource` can fail for a resource in a named module even when code in the same module can load the bundle or resource via module-aware APIs. Therefore, step 4 must use the **right API and scope for the situation**, rather than treating the system loader as the "absolute standard" for diagnosing every module.

## 15. Thread Context Loader in Real-World Services and Plugins

A shared library is often loaded by a parent loader yet needs to look up resources from a plugin/user module. If the library only calls `Library.class.getResource(...)`, it anchors to the library class/module and will not necessarily see the plugin's resources.

There are several design options:

| Approach | When appropriate | Risk to manage |
| --- | --- | --- |
| Pass `ClassLoader` explicitly | Plugin/resource is managed by a separate loader | Caller must pass the right loader |
| Pass `Class<?> anchor` | Resource sits beside a class in the plugin | Must understand relative/absolute naming and modules |
| Pass `Module` | Resources are packaged in a named module | Must respect encapsulation |
| Use TCCL per framework contract | Library is designed to look up via context | Must restore when using thread pools |
| Use `ResourceBundleProvider` | Bundles are distributed across provider modules | Requires module descriptor/service plumbing |
| Put all resources on system classpath | Simple demos | Unsuitable for isolated architectures |

A library API can accept an **anchor class** or a loader specified by the host, for example:

```java
static InputStream findRequiredResource(
        Class<?> anchor, String absoluteName) {
    InputStream in = anchor.getResourceAsStream(absoluteName);
    if (in == null) {
        throw new IllegalArgumentException(
                "Resource missing: " + absoluteName);
    }
    return in;
}
```

This is an illustrative helper method; the caller must close the returned stream. If `absoluteName` does not start with `/`, it is resolved relative to `anchor`'s package. If a library wants to reference a resource module rather than a specific class, design an overload taking `Module` with appropriate access rules.

## 16. Locale, Class Loader, and Bundle Lookup Are Three Separate Axes

A common misconception is thinking:

> "Since I passed `Locale.forLanguageTag("vi-VN")`, Java must automatically find `Messages_vi.properties` anywhere on the machine."

Incorrect. There are three separate decisions:

| Axis | Question | API/concept |
| --- | --- | --- |
| **Locale** | Which language/region translation do we want? | `Locale` |
| **Resource naming** | Which family/path contains the data? | `baseName`, resource name |
| **Class loader/module scope** | Which data is the current runtime allowed to look up? | `ClassLoader`, `Class`, `Module` |

You can have the right locale with the wrong loader; the right loader with the wrong `baseName`; the right `baseName` yet the file is absent from the JAR; or the right file yet the package is not opened to the caller module.

Moreover, `Locale.setDefault(...)` changes the JVM-wide default locale; it **does not** add a JAR to the classpath and does not change named module visibility. Do not use `setDefault` to work around resource packaging errors.

### Why Is This Lesson Part of Localization?

Localization is not only about choosing number/date formatting patterns, but also about **ensuring translated content is packaged and looked up in the right place**. When an application has multiple modules or plugins, translations may be partitioned by feature. If the class loader scope is wrong, the UI can lose labels or fall back to the default language even when the locale tag is completely valid.

## 17. Safety and Correctness When Reading Resources

Resource lookup reads data located within a loader/module's search path. When building an API that fetches resources based on external input, enforce controls:

- Do not directly concatenate user-supplied paths into resource names and assume it is safe; whitelist names/bundles whenever possible.
- Avoid exposing internal path listings in public error messages.
- Use fixed domain/application resource names when loading mandatory content.
- Do not assume every `.properties` file from the resource root is trusted data if third-party plugins can contribute to the classpath/loader.
- Avoid generic resource names that collide easily across dependencies when you can use a distinct namespace.
- Close streams with `try-with-resources`, and specify the charset (UTF-8 for text per contract).
- With untrusted plugins, a class loader **is not by itself a security sandbox**. Do not rely on custom loaders as an absolute access-isolation mechanism.
- With named modules, do not unconditionally open packages holding sensitive data just for convenience in finding resources; follow the principle of least privilege in architecture.

Resource path safety is not solely about `../`: loaders/providers may handle names differently, so it is best not to design a public endpoint that "reads any resource name" from the classpath.

## 18. How to Test When Packaging Changes

### 18.1. Test Both in the IDE and with the Actual Artifact

Do not run only unit tests using `src/test/resources`, because test resources are normally absent from production JARs. For releases, run integration tests against the **packaged JAR/module** and verify required bundles.

Checks to include:

- Every required resource is inside the artifact at the exact entry path.
- `getResourceAsStream` is non-null when called from the proper scope.
- UTF-8 decodes Vietnamese messages and non-ASCII characters accurately.
- `vi-VN`, `en-US`, and root bundles behave per product specifications.
- Missing keys produce clear errors or defined fallbacks.
- Run on both Windows and Linux environments to ensure no OS path separator dependencies exist in resource names.

### 18.2. Test Multiple Class Loaders

If using plugins:

1. A resource present only in plugin loader A.
2. A resource present only in plugin loader B.
3. A resource with the same name in both parent and child.
4. A missing resource.
5. A plugin loader that is closed/disposed and recreated.

Verify that the API retrieves the right resource according to the **intended scope**, without accidental mixing. Do not assume `ClassLoader.getSystemClassLoader()` sees B's resources when they reside only in `URLClassLoader` B.

### 18.3. Test Named Modules

On Java 17, verify:

- Are resources in the same module readable via `Class.getResourceAsStream` / `Module.getResourceAsStream` with the exact path?
- Is access from another module to an unopened package denied as expected?
- Do `opens` and `exports` target the intended packages?
- Does `ClassLoader.getResource` obey the unconditional open requirement for non-class resources?
- Does `ResourceBundle.getBundle` locate bundles according to the caller module/provider setup?
- Does switching from classpath to module path change caching/lookup behavior?

Do not use a classpath test suite to claim JPMS works properly without testing on the module path.

### 18.4. Test Fallback and Cache

When `Messages_vi_VN.properties` is absent but `Messages_vi.properties` exists, confirm the `vi` variant is selected per policy. When a key is missing in a specific bundle, verify parent/root fallback if that is the expected behavior. If hot reload exists, test cache invalidation and class loader lifecycles. **Do not clear the cache as a default fix** before confirming the right lookup scope.

## 19. Common Mistakes and How to Fix Them

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| `ClassLoader.getResource("/a/b.txt")` | Incorrect lookup per loader convention | Use `"a/b.txt"` |
| `SomeClass.class.getResource("file.txt")` when file is at root | Looks up relative to the wrong package | Use `"/file.txt"` or place in the proper package |
| Using `new File("src/main/resources/…")` after deployment | Source directory no longer exists | Read runtime resource stream |
| Coercing a JAR entry URL to a default FS `Path` | Scheme/path error | Use `getResourceAsStream` |
| Passing `ResourceBundle.getBundle("a/b.properties", locale)` | Invalid `baseName` | Use `"a.b"` (family name) |
| Source file exists but is excluded from JAR | Missing in production | Inspect artifact with `jar tf` |
| Using application loader for a plugin-only resource | `null`/`MissingResourceException` | Pass the appropriate plugin loader/anchor |
| Setting TCCL when the API does not read TCCL | Changing context has no effect | Check API contract and pass loader explicitly |
| Not restoring TCCL in a thread pool | Other requests are affected | Restore with `try/finally` |
| Changing `Locale.setDefault` to "find" a bundle | Does not fix scope, causes side effects | Fix loader/module/path |
| `exports package` and thinking it means `opens package` | Resource remains encapsulated | Choose proper access per JPMS |
| Treating `ClassLoader.getResource` as searching across all modules | Encapsulated resources are invisible | Use context-appropriate module-aware API |
| Two JARs share a resource name, assuming stable order | Reads an unexpected copy | Separate namespaces, check `getResources` |
| Calling `ResourceBundle.clearCache` to "add" a new resource | Loader still cannot see the file | Fix classpath/loader and artifact |
| Reading translation files with the default charset | Vietnamese diacritics break on other machines | Explicit UTF-8 / proper JDK `ResourceBundle` |
| Treating `getResource != null` as successful read | Stream may fail while reading | Read inside `try-with-resources`, handle I/O |
| Using `ClassLoader` as a plugin sandbox | Insufficient security isolation | Design real permissions/isolations |
| Claiming IDE tests suffice for JAR/module | Runtime layout differs | Run integration tests on packaged artifact |

## 20. Practice Exercises and Answers

**Exercise 1.** Class `com.acme.App` wants to read `com/acme/help.txt`. Which two calls are equivalent when running on the standard classpath?

**Answer:** `App.class.getResource("help.txt")` and `App.class.getResource("/com/acme/help.txt")`. With a class loader, use `App.class.getClassLoader().getResource("com/acme/help.txt")`.

**Exercise 2.** File `Messages_vi.properties` sits in `l10n/` inside the JAR. Which `baseName` does `ResourceBundle.getBundle` need?

**Answer:** `"l10n.Messages"`, not `"l10n/Messages_vi.properties"`.

**Exercise 3.** Loaders A and B are both children of parent P; a resource resides only in B. Will querying `A.getResource(name)` necessarily find B's resource?

**Answer:** No. Lookup scope and delegation strategy do not automatically include sibling loaders.

**Exercise 4.** Why can `Files.readString(Path.of("src/main/resources/a.txt"))` work in the IDE yet fail in a production JAR?

**Answer:** Because the source directory is not necessarily shipped. Resources should be read from the runtime classpath/module via streams.

**Exercise 5.** `ClassLoader.getResource` fails to find a `.properties` file in a named module, whereas `SomeClass.class.getResourceAsStream` from a class in the same module reads it. Is that a contradiction?

**Answer:** No. The two APIs have different module encapsulation mechanisms/rules; `ClassLoader.getResource` restricts access to packages that are not opened unconditionally.

**Exercise 6.** A user switches the locale from `en-US` to `vi-VN`, yet the loader cannot find bundle `l10n.Messages`. Will calling `Locale.setDefault(viVN)` fix the loader scope?

**Answer:** No. Locale only affects candidate selection/fallback; it does not make resources outside the loader visible.

**Exercise 7.** Does `Thread.currentThread().setContextClassLoader(pluginLoader)` guarantee that `ResourceBundle.getBundle("x.Y", locale)` uses the plugin loader?

**Answer:** No. That overload uses the caller context/module per API; if you need the plugin loader in a classpath setup, pass `pluginLoader` explicitly using the three-argument overload.

**Exercise 8.** Two dependency JARs both contain `config/settings.properties`; what should you do if deterministic results are needed?

**Answer:** Use separate namespaces or define a clear merge/priority policy. You can use `getResources` to detect duplicates; do not rely unconditionally on "first resource" ordering.

**Exercise 9.** Module X `exports x.messages` but does not `opens` that package. Is resource `x/messages/Messages.properties` guaranteed to be readable via the system class loader from another module?

**Answer:** No. `exports` does not mean `opens`; non-class resources in named modules are governed by encapsulation depending on the lookup API.

**Exercise 10.** When a translation file inside a JAR is updated, is calling `ResourceBundle.clearCache(loader)` always enough?

**Answer:** No. You must ensure the loader actually sees the new artifact, the JAR was reloaded/replaced properly, and module visibility matches; caching is only one part.

**Exercise 11.** A method receives `Class<?> anchor` and calls `anchor.getResourceAsStream("a.txt")`. Why can changing `anchor` to a class in another package alter the outcome?

**Answer:** Because a name without a leading slash is resolved **relative to the anchor's package**. If you want a fixed root path, pass `"/path/a.txt"`.

**Exercise 12.** Why should you avoid using a generic name like `messages.properties` across all plugins?

**Answer:** It can collide across classpath entries or loaders when delegation/namespaces are unclear. Naming bundles by package/feature such as `pluginA.i18n.Messages` is much easier to control.

## 21. Summary

- **The class loader determines the scope of visible classes/resources**, not merely whether a file exists on disk.
- `Class.getResource("relative")` searches relative to the package; `Class.getResource("/absolute")` starts from the root; `ClassLoader.getResource("root/path")` uses a name **without a leading slash**.
- Resources inside a JAR must typically be read via `InputStream`; do not assume they are always regular `File`/`Path` objects.
- **ResourceBundle** uses `package.Name`-style `baseName`, locale candidates, fallback, and caching; loader/module can be selected explicitly via appropriate overloads.
- **Plugin loaders** are not automatically queried by the application loader or sibling loaders. The TCCL only matters when an API/library actually reads it.
- **Named modules** add resource encapsulation. `exports` differs from `opens`; `ClassLoader.getResource` and `Module.getResourceAsStream` do not share identical visibility rules.
- When deploying, verify the **actual JAR/module artifact**, exact path, loader/module scope, and cache/fallback; do not inspect only the source folder.
- Use UTF-8 for text per contract, close streams, avoid untrusted user-controlled resource names, and do not treat a class loader as a security sandbox.
- **For reliable localization, get the Locale, bundle name, and class loader/module scope all right.**

### Official Java SE 17 Documentation

- [Class — getResource / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — getResource / getResources / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [ResourceBundle — class loaders, modules, caching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Module — getResourceAsStream / isOpen / isExported](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [URLClassLoader — plugin loader example](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
