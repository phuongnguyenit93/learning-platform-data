# Printing Class Name, Loader, Module, and Code Source in Java Error Information

When a Java application has multiple `ClassLoader` instances — plugins, application servers, test runners, service providers, or module layers — simply printing `ClassNotFoundException: com.example.Plugin` is often **not enough for diagnosis**. Having the right class name does not mean the JVM used **the right class definition**. Two loaders can define two runtime types with the same name; an older parent JAR can win over a newer plugin JAR; a class belonging to a named module can be subject to exports/opens constraints. Therefore, useful error information should record at least:

1. **The requested class name or the actual class involved** (`Class.getName()`).
2. **Defining loader** (`Class.getClassLoader()`): which loader object defined the runtime class, along with the loader's name and type to distinguish it.
3. **Actual module** (`Class.getModule()`): whether it is a named module or an unnamed module, and its layer if needed.
4. **Code source** (`Class.getProtectionDomain().getCodeSource().getLocation()`), when provided.
5. **Error type, cause chain, stacktrace, the action being performed, and the loader used for lookup**; distinguish the *lookup loader* from the *defining loader*.
6. **Version and deployment context**: plugin ID/generation, expected artifact/version, Java runtime version, and request/correlation ID, without exposing secrets.

This Knowledge article belongs to **Java core – classloader / Diagnostics**, focusing on the topic **“Printing class name, loader, module, and code source in error information”** on Java 17+. The examples progress from minimal metadata logging to conflicts between two class loaders, lookup errors, and initialization errors; each standalone runnable program includes compile/run commands and expected stdout.

## 1. An Example Problem: Same Class Name, Different Meaning

Suppose:

```text
Host application classpath
  com.example.api.Widget   (loader = app)

Plugin A
  com.example.impl.Parser  (loader = plugin-A)
  com.example.lib.Json     (v1, loader = plugin-A)

Plugin B
  com.example.impl.Parser  (loader = plugin-B)
  com.example.lib.Json     (v2, loader = plugin-B)
```

If both plugins load `com.example.impl.Parser` themselves, `ParserA.getName()` and `ParserB.getName()` are the same, yet:

```java
System.out.println(ParserA == ParserB);
```

This is a **snippet** that requires two variables `Class<?> ParserA` and `Class<?> ParserB`. The result can be `false`, because the JVM determines runtime class identity by **binary name + defining class loader**.

The message:

```text
java.lang.ClassCastException: class com.example.impl.Parser ...
```

does not yet answer “**which loader defined** this class and from which artifact were its bytes loaded?”. By including the defining loader, module, and code source, we can identify an outdated class version or the wrong plugin tier without guessing from the source tree.

**Principle:** diagnose class loaders based on the **runtime `Class<?>` object** and actual metadata, not merely on class name strings, guessed paths, or Maven/Gradle configuration.

## 2. The Four Most Important APIs for Retrieving Class Metadata

| What to print | Java 17 API | Proper interpretation |
| --- | --- | --- |
| Runtime class name | `type.getName()` | Binary name for ordinary classes; array/primitive/hidden classes have their own naming rules |
| Defining loader | `type.getClassLoader()` | `null` usually denotes the bootstrap loader, and is always `null` for primitive/void types |
| Module | `type.getModule()`; `module.getName()` | `null` from `getName()` means an unnamed module, not the absence of a Module object |
| Code source | `type.getProtectionDomain().getCodeSource().getLocation()` | `CodeSource` or `location` may be absent; the URL is not absolute proof of the byte contents |

Additional information that is often useful:

- `type.getPackageName()`: the package name according to the Java runtime type; **the same package name does not necessarily mean the same runtime package** if the defining loaders differ.
- `type.getClassLoader() == expectedLoader`: identity check by object reference during investigation.
- `loader.getClass().getName()`: the loader's implementation class, such as a built-in/custom loader.
- `loader.getName()` (Java 9+): the descriptive name of the loader if set; may be `null`.
- `System.identityHashCode(loader)`: a reference identifier helping distinguish two instances within **a running JVM**, not a stable ID across restarts.
- `module.getDescriptor()` or `module.getLayer()`: when tracing named modules/JPMS layers is needed.
- `StackTraceElement.getClassLoaderName()`, `getModuleName()`, `getModuleVersion()`: frame metadata (may be `null`), though they do not themselves provide the `Class<?>` or code source.

**Avoid logging only `loader.toString()`.** Many loaders provide a useful `toString`, but it is not a contract guaranteeing a URL/source/version. With custom loaders, `toString()` may even be overly verbose or contain internal information that should not be exposed in public logs.

## 3. `Class.getName()`: Which Class Name Should Be Printed?

`Class.getName()` differs from file names and several display names:

| API/format | Example | When to use |
| --- | --- | --- |
| `type.getName()` | `com.example.MyService` | Logging the exact ordinary runtime type |
| `type.getSimpleName()` | `MyService` | Easy to read, but lacks the package and can be ambiguous |
| `type.getCanonicalName()` | `com.example.Outer.Inner` | Human-facing code name; may be `null` for local/anonymous/hidden classes |
| Nested class binary name | `com.example.Outer$Inner` | `Class.forName` and JVM lookup |
| Relative class-file path | `com/example/MyService.class` | Inspecting JAR entries/classpath |
| Descriptor | `Lcom/example/MyService;` | Bytecode/JVMS reference |
| Array class `getName()` | `[Ljava.lang.String;` | Not the source-style name `String[]` |

For error context, prefer **`type.getName()`** because it does not lose the package or nested-class identifier. If the class has not been loaded successfully, there is no `Class<?>` to call methods on; log the **requested binary name** instead of fabricating a placeholder class value.

**Missing class example**:

```java
String requested = "com.example.Missing";
try {
    Class<?> found = lookupLoader.loadClass(requested);
    // Only with a Class<?> can the defining loader/module/code source be read.
} catch (ClassNotFoundException error) {
    // Log requested and lookupLoader itself;
    // do not assert a defining loader that does not exist.
}
```

This is a **snippet** requiring a `ClassLoader` variable named `lookupLoader` and a method with exception handling.

## 4. Defining Loader Differs from Lookup Loader and Context Loader

A call:

```java
Class<?> type = child.loadClass("api.Shared");
```

does not guarantee `type.getClassLoader() == child`. With parent-first delegation, `child` can delegate to its parent and receive a runtime class defined by the parent.

Three roles:

1. **Requested/lookup loader:** the object on which code calls `loadClass` or passes into `Class.forName(name, ..., loader)`.
2. **Defining loader:** `type.getClassLoader()` of the actual runtime class, which may be a parent or ancestor.
3. **Thread context class loader (TCCL):** `Thread.currentThread().getContextClassLoader()`; often affects framework/SPI discovery (`ServiceLoader.load(service)`), and is not by default identical to the defining loader.

```text
thread TCCL = plugin-B
         │
         └── ServiceLoader selects service provider resources

requestedLoader = child-B
         │
         └── child-B.loadClass("api.Contract")
                 │
                 └── parent app defines api.Contract

type.getClassLoader() == app
```

When logging `ClassNotFoundException`, record the lookup loader and TCCL if meaningful; when logging `ClassCastException` or `LinkageError`, record the **defining loaders of both runtime types** if the caller is comparing them.

**Do not confuse `loader.getParent()` with `type.getClassLoader()`**: parent is an object relationship between loaders; the defining loader tells you which loader defined a specific class.

## 5. `getClassLoader() == null` Is Not Itself an Error

In many JVM implementations, a class defined by the bootstrap loader has:

```java
ClassLoader loader = String.class.getClassLoader();
System.out.println(loader == null);
```

This snippet is runnable if placed inside a method; on a typical JDK 17, the output is `true`. Here, `null` is how the API represents the bootstrap loader, which **has no public Java object to return**, rather than a bug or an unloaded class.

For `int.class` or `void.class`, `getClassLoader()` also returns `null`; distinguish them using `type.isPrimitive()`. Array classes do not have a class file defined via `defineClass` like ordinary classes; an array class's `getClassLoader()` reflects the loader of its element type, or `null` for primitive components.

Suggested formatter:

```java
static String loaderLabel(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    if (type.isPrimitive()) {
        return "<primitive>";
    }
    if (loader == null) {
        return "<bootstrap>";
    }
    String name = loader.getName();
    return name == null
            ? loader.getClass().getName()
            : name + " (" + loader.getClass().getName() + ")";
}
```

This is an illustrative method; it will not run on its own unless placed inside a class with a caller. In a production logger, consider also printing the **identity hash** of the loader instance, because two loaders with the same name and the same Java implementation class can still define two different classes.

## 6. Module: Named or Unnamed, and Why Can `getName()` Be Null?

`Class.getModule()` returns the `Module` object corresponding to the class; for classes on the classpath or classes created by `URLClassLoader` in a classpath-style setup, the module is typically the **unnamed module** of the defining loader.

```java
Module module = type.getModule();
String moduleName = module.isNamed()
        ? module.getName()
        : "<unnamed>";
```

This is a **snippet** requiring a variable `type` of type `Class<?>`.

Examples on Java 17:

- `String.class.getModule().getName()`: `"java.base"`.
- `MyClasspathClass.class.getModule().isNamed()`: `false` if the class runs on the application classpath.
- A class belonging to the named module `org.example.plugin` returns that module name, and may also have a module version in its descriptor.
- With custom-built named module layers, having the same module name in two layers **does not automatically guarantee the same `Class<?>` identity**; you need to inspect the `Module` object, layer, and corresponding loader.

**Do not infer that `module.getName() == null` means “module lookup failed”**. That is the name of an unnamed module, a normal concept in JPMS.

With `ClassCastException` or `IllegalAccessError`, module metadata helps quickly determine whether the issue is duplicate types or module access (`requires`/`exports`/`opens`). However, printing only the module name does not replace analyzing runtime type identity.

## 7. Code Source: `ProtectionDomain → CodeSource → URL`

Standard API:

```java
ProtectionDomain domain = type.getProtectionDomain();
CodeSource codeSource =
        domain == null ? null : domain.getCodeSource();
URL location = codeSource == null
        ? null : codeSource.getLocation();
```

This is a **snippet** requiring imports for `java.security.ProtectionDomain`, `java.security.CodeSource`, `java.net.URL`, and a `type` variable.

Meaning:

- `ProtectionDomain` attaches metadata about the runtime class's domain.
- `CodeSource` can describe the **source URL and associated signer certificates**.
- `CodeSource.getLocation()` is a URL, typically **`file:/.../app.jar`** or **`file:/.../classes/`** for classpath classes.
- `null` is a **valid** value if there is no CodeSource or location; many platform/JDK classes do not have a JAR/filesystem-path style source URL.
- `Class.getProtectionDomain()` can throw `SecurityException` on runtimes with relevant security checks (especially under legacy security models); the logger should handle this using a fail-safe policy.

**Do not call `type.getProtectionDomain().getCodeSource().getLocation().toString()` without null checks**. A `NullPointerException` thrown from the logger will obscure the original error under investigation.

**CodeSource location is not absolute cryptographic proof.** The URL may be the JAR/directory location used when defining the class, but it does not prove that the bytes currently on disk are the bytes that were loaded, does not prove the artifact has not been modified, and does not tell whether the class has the right build version without combining it with hashes/manifest/versioning.

## 8. CodeSource Differs from Class Resource URL and JAR Manifest

Some developers try:

```java
URL location = type.getResource(
        type.getSimpleName() + ".class");
```

This snippet can be useful to **find the resource matching the class name** in certain cases, but it is **not equivalent to `ProtectionDomain.CodeSource`**:

- `Class.getResource` depends on loader/module resource lookup, accessibility, and resource-name rules.
- `getResource(...)` can return a `jrt:/...` URL for classes in the JDK runtime image; that is a resource URL, not necessarily `CodeSource.getLocation()`.
- The resource may not be found, may be hidden by module encapsulation, or may not be the bytes used for the runtime definition.
- For a dynamically generated class/hidden class, **a URL-accessible `.class` file may not exist at all**.
- A custom loader can define a class from a byte array in memory, a database, or over the network without setting a CodeSource; `location == null` is completely valid.
- Resource URLs and CodeSource URLs can differ in granularity: one points directly to `some/Type.class`, while the other points to the **root JAR/directory**.

If you need to determine which JAR a class actually comes from, **prefer the CodeSource location when available** and cross-check it against class-loading logs and artifact inventory. If you need to prove which artifact the bytecode came from, the loader design can log **a build identifier or a verified SHA-256 digest of a trusted artifact** — not just the filename.

## 9. Practice A — Printing Class Name, Loader, Module, and CodeSource in Full

The first example is a **complete Java 17+ program** on the application classpath. We print the metadata of the demo class itself and `java.lang.String`.

Structure:

```text
diagnostics-lab/
└── src/demo/DiagnosticDemo.java
```

File **`src/demo/DiagnosticDemo.java`**:

```java
package demo;

import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class DiagnosticDemo {
    private static String loaderOf(Class<?> type) {
        ClassLoader loader = type.getClassLoader();

        if (loader == null) {
            return type.isPrimitive() ? "<primitive>" : "<bootstrap>";
        }
        if (loader == DiagnosticDemo.class.getClassLoader()) {
            return "application";
        }
        return loader.getName() == null
                ? loader.getClass().getName() : loader.getName();
    }

    private static String moduleOf(Class<?> type) {
        Module module = type.getModule();
        return module.isNamed() ? module.getName() : "<unnamed>";
    }

    private static String sourceSchemeOf(Class<?> type) {
        try {
            ProtectionDomain domain = type.getProtectionDomain();
            CodeSource source =
                    domain == null ? null : domain.getCodeSource();
            URL location =
                    source == null ? null : source.getLocation();
            return location == null
                    ? "<unavailable>" : location.getProtocol();
        } catch (SecurityException denied) {
            return "<denied>";
        }
    }

    private static void describe(Class<?> type) {
        System.out.println("class=" + type.getName());
        System.out.println("loader=" + loaderOf(type));
        System.out.println("module=" + moduleOf(type));
        System.out.println("code-source scheme=" +
                sourceSchemeOf(type));
    }

    public static void main(String[] args) {
        describe(DiagnosticDemo.class);
        describe(String.class);
    }
}
```

Compile and run inside `diagnostics-lab`:

```sh
javac --release 17 -d out src/demo/DiagnosticDemo.java
java -cp out demo.DiagnosticDemo
```

**Expected stdout on OpenJDK/HotSpot Java 17 in this classpath configuration:**

```text
class=demo.DiagnosticDemo
loader=application
module=<unnamed>
code-source scheme=file
class=java.lang.String
loader=<bootstrap>
module=java.base
code-source scheme=<unavailable>
```

We intentionally print only the **URL scheme** instead of the full filesystem URL so that stdout does not depend on the project directory location and does not leak user paths.

### Explanation

- `DiagnosticDemo.class` is defined by the application loader from the `out` directory on the classpath; it belongs to the unnamed module. Its CodeSource typically contains a `file:` URL for the `out` directory.
- `String.class` is defined by the bootstrap loader on typical JDK 17 runtimes and belongs to the named module `java.base`. The CodeSource location is usually not provided in this metadata; **do not write code that requires it to exist**.
- `loader=application` is a label **chosen by convention in the example itself** by comparing the object against the loader of `DiagnosticDemo`, not a guarantee that Java always names the loader `application`.
- If run under a custom launcher/security configuration, the labels or accessibility of CodeSource may differ; the demo still handles `null` and `SecurityException`.
- In real logs, it may be necessary to record the **full URL** according to internal policy to identify the artifact; the example prints only the scheme to keep the expected stdout stable.

**Key distinction:** `Class.getProtectionDomain()` reads metadata and does not run the target's constructor or static initializer. Having a `Class<?>` also does not mean an instance of the class has been created.

## 10. Logging the Full CodeSource URL While Controlling Log Security

A suitable helper for logging:

```java
static String codeSourceUrl(Class<?> type) {
    try {
        var domain = type.getProtectionDomain();
        if (domain == null || domain.getCodeSource() == null) {
            return "<unknown>";
        }
        var url = domain.getCodeSource().getLocation();
        return url == null ? "<unknown>" : url.toExternalForm();
    } catch (SecurityException denied) {
        return "<access-denied>";
    }
}
```

This is an **illustrative method**; it must reside inside a class and is not a standalone program. It preserves the full URL when permitted, but **does not guarantee that the URL is appropriate for output to public logs**.

Some URLs can contain:

- a username or home directory path information;
- internal deployment directory structures;
- customer/tenant names or private environments;
- queries/fragments containing tokens in custom URL schemes;
- internal network hosts and endpoints.

**Better rule:** internal loggers can retain the canonical artifact ID/version/digest, whereas public-facing errors should only use an error code/correlation ID. If logging the URL is required, normalize/sanitize it and redact sensitive information according to system policy. Avoid using a URL pointing to an untrusted endpoint as a location from which to automatically read/download artifacts solely for diagnostics.

### “Code Source” Is Not Always a File

A class can come from:

- a **JAR** on the classpath/URLClassLoader;
- a **directory** containing class files;
- the **JDK runtime image** (`jrt:`), for which CodeSource may be unavailable;
- a **custom ClassLoader** generating bytecode in memory;
- a **module layer** that does not map simply to a filesystem URL;
- bytecode instrumentation or runtime enhancement.

Therefore, `CodeSource == null` should be logged as **`<unknown>`** or **`<unavailable>`**, rather than jumping to the conclusion that “it is definitely a malicious class/has no JAR”.

## 11. Printing Loaders by Identity, Not Only by Name

Two `URLClassLoader` instances can have the same implementation class, the same URLs, and even the same name, yet still be **two different defining loaders**.

A useful label for a session:

```java
static String loaderDetail(ClassLoader loader) {
    if (loader == null) {
        return "<bootstrap>";
    }
    String name = loader.getName();
    return loader.getClass().getName()
            + "[name=" + (name == null ? "<unnamed>" : name)
            + ", id=0x"
            + Integer.toHexString(System.identityHashCode(loader))
            + "]";
}
```

This is an illustrative helper; be careful because a custom-configured loader name may contain untrusted input.

**Why an identity hash instead of only `getName()`?**

- `getName()` can be null; custom loaders can have duplicate labels.
- `loader.getClass().getName()` is usually identical for all instances of the same subclass.
- `System.identityHashCode(loader)` helps distinguish objects within **a single run** even if `equals` is overridden.
- However, an identity hash is only a 32-bit hash value: **collisions can occur**, it is not a globally unique ID, must not be used as an authentication token, and is not consistent across restarts.

For production plugin systems, it is better to proactively assign a **pluginId + generation/version UUID** when creating the loader and log it alongside the identity hash as auxiliary diagnostic data.

## 12. Practice B — Two URLClassLoaders Defining the Same Name but Different Runtime Types

This example demonstrates why logging only the class name is not enough. We compile a class `plugin.Widget`, place its bytes in a separate directory, and then create two **named URLClassLoader instances** sharing the same URL and the same parent, yet having independent class identities.

Structure:

```text
duplicate-loader-lab/
├── src/plugin/plugin/Widget.java
├── src/host/demo/DuplicateLoaderDemo.java
├── plugin-out/
└── host-out/
```

**`src/plugin/plugin/Widget.java`:**

```java
package plugin;

public final class Widget {
    public Widget() {
    }

    public String label() {
        return "plugin widget";
    }
}
```

**`src/host/demo/DuplicateLoaderDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DuplicateLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL pluginRoot = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginRoot };
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader a =
                     new URLClassLoader("plugin-A", urls, platform);
             URLClassLoader b =
                     new URLClassLoader("plugin-B", urls, platform)) {

            Class<?> left = a.loadClass("plugin.Widget");
            Class<?> right = b.loadClass("plugin.Widget");
            Object rightObject =
                    right.getDeclaredConstructor().newInstance();

            System.out.println("same name=" +
                    left.getName().equals(right.getName()));
            System.out.println("same runtime Class=" + (left == right));
            System.out.println("left loader name=" +
                    left.getClassLoader().getName());
            System.out.println("right loader name=" +
                    right.getClassLoader().getName());
            System.out.println("left module named=" +
                    left.getModule().isNamed());
            System.out.println("left source scheme=" +
                    left.getProtectionDomain()
                        .getCodeSource()
                        .getLocation()
                        .getProtocol());

            try {
                left.cast(rightObject);
                System.out.println("unexpected cast success");
            } catch (ClassCastException mismatch) {
                System.out.println("cast error=" +
                        mismatch.getClass().getSimpleName());
            }
        }
    }
}
```

**Compile** from `duplicate-loader-lab` using JDK 17+:

```sh
javac --release 17 -d plugin-out src/plugin/plugin/Widget.java
javac --release 17 -d host-out src/host/demo/DuplicateLoaderDemo.java
```

**Run** (note: only `host-out` is on the app classpath):

```sh
java -cp host-out demo.DuplicateLoaderDemo
```

**Stdout on OpenJDK/HotSpot Java 17 with the directory URL above:**

```text
same name=true
same runtime Class=false
left loader name=plugin-A
right loader name=plugin-B
left module named=false
left source scheme=file
cast error=ClassCastException
```

**Analysis:**

1. Both loaders are given **the same `plugin-out` URL**, yet each instance defines `plugin.Widget` on its own.
2. `left.getName().equals(right.getName())` returns true: the binary names are identical.
3. `left == right` returns false: the defining loaders are two different objects.
4. `getName()` of the named `URLClassLoader` is set via the Java 9+ constructor, helping distinguish `plugin-A`/`plugin-B`.
5. The two classes belong to unnamed modules **separate per defining loader**. `isNamed()` returns false for each side.
6. The `CodeSource` of a class obtained by URLClassLoader from the `plugin-out` directory typically has the `file` URL scheme.
7. `Class.cast` checks runtime assignability, so the object created from `right` is not an instance of the runtime type `left`; `ClassCastException` is expected even though both have the same binary name.

**API note:** the demo directly reads `getCodeSource().getLocation()` for brevity because the source is a `URLClassLoader` from a controlled `file:` URL. In general logging code, **you must use a null-safe helper** as in sections 7–10, since many completely valid classes have no CodeSource.

Do not add `plugin-out` to the host's `-cp` if you want to observe two separate defining loaders. If the parent application loader has already defined `plugin.Widget` and parent-first delegation returns it, both children may end up using the parent's version, changing the result.

## 13. `ClassCastException`: Both Sides Must Be Logged

A message like:

```text
ClassCastException: plugin.Widget cannot be cast to plugin.Widget
```

looks paradoxical at first glance, yet can arise from **two `Class<?>` objects with different identities**. At runtime, you should record:

- `expectedType.getName()`, the defining loader, module, and CodeSource of the type expected by the host;
- `actualObject.getClass().getName()`, the defining loader, module, and CodeSource of the actual object;
- the class loader used to **load the provider/plugin**, and the TCCL if the framework uses it;
- the artifact ID/version of both;
- the full stacktrace/cause, while not exposing sensitive paths in the client response.

Pseudocode:

```java
Class<?> actual = value.getClass();
Class<?> expected = expectedApiClass;

System.err.println("expected=" + expected.getName());
System.err.println("actual=" + actual.getName());
System.err.println("same Class=" + (actual == expected));
System.err.println("assignable=" +
        expected.isAssignableFrom(actual));
// Also log loaderDetail and codeSourceUrl for both.
```

This is a **snippet** requiring the variables `value` and `expectedApiClass`. `isAssignableFrom` is better than just comparing names, especially for interfaces. For a valid implementation, `actual == expected` is usually false (the implementation differs from the interface), but `expected.isAssignableFrom(actual)` must be true.

**Do not print only `actual.getClassLoader()` and consider it enough.** A failed cast involves at least two types: expected and actual. Information for **both** is needed.

## 14. `ClassNotFoundException`: The Class Does Not Exist Yet, So Defining Loader Cannot Be Printed

When `ClassLoader.loadClass("plugins.Missing")` throws `ClassNotFoundException`, there is no resulting `Class<?>` to call `getModule()` or `getProtectionDomain()` on.

Instead, record:

```text
phase=LOAD_CLASS
requested=plugins.Missing
lookupLoader=plugin-loader-7
threadContextLoader=...
parentChain=...
artifactCandidates=...
error=ClassNotFoundException
cause=...
```

This is a **suggested schema**, not executed stdout.

Questions:

1. Is `requested` the right **binary name**? For nested classes use `Outer$Inner`, not `Outer.Inner` in `loadClass`.
2. Is the loader passed to `Class.forName` the right one?
3. If the framework uses `ServiceLoader`, does the TCCL point to the right provider-discovery loader?
4. Do the URL roots/JAR entries actually contain `plugins/Missing.class`?
5. Is package/module encapsulation or a loader policy blocking the lookup?
6. Is the error a missing **indirect dependency** leading to `NoClassDefFoundError`, rather than the requested class itself being missing directly?

**Do not automatically issue `Class.forName` calls to “fetch additional metadata” for every name not found**, because doing so can trigger loading/initialization side effects, alter the diagnostic state, or repeat the error.

## 15. Practice C — Reporting Requested Class on Lookup Failure, and Metadata on Initialization Failure

Structure:

```text
error-context-lab/
└── src/demo/ErrorContextDemo.java
```

**`src/demo/ErrorContextDemo.java`:**

```java
package demo;

import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class ErrorContextDemo {
    static final class Broken {
        static int value = initialize();

        private static int initialize() {
            throw new IllegalStateException("bad configuration");
        }
    }

    private static String codeSourceScheme(Class<?> type) {
        ProtectionDomain domain = type.getProtectionDomain();
        CodeSource codeSource =
                domain == null ? null : domain.getCodeSource();
        URL location = codeSource == null
                ? null : codeSource.getLocation();
        return location == null
                ? "<unavailable>" : location.getProtocol();
    }

    public static void main(String[] args) {
        String missing = "demo.NotPresent";
        ClassLoader lookup =
                ErrorContextDemo.class.getClassLoader();

        try {
            lookup.loadClass(missing);
        } catch (ClassNotFoundException failure) {
            System.out.println("requested=" + missing);
            System.out.println("lookup was app=" +
                    (lookup == ErrorContextDemo.class.getClassLoader()));
            System.out.println("lookup error=" +
                    failure.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.value);
        } catch (ExceptionInInitializerError failure) {
            Class<?> target = Broken.class;

            System.out.println("failing type=" + target.getName());
            System.out.println("defined by app=" +
                    (target.getClassLoader() == lookup));
            System.out.println("module=" +
                    (target.getModule().isNamed()
                            ? target.getModule().getName()
                            : "<unnamed>"));
            System.out.println("source scheme=" +
                    codeSourceScheme(target));
            System.out.println("init error=" +
                    failure.getClass().getSimpleName());
            System.out.println("root cause=" +
                    failure.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile/run with JDK 17+ from `error-context-lab`:

```sh
javac --release 17 -d out src/demo/ErrorContextDemo.java
java -cp out demo.ErrorContextDemo
```

**Stdout on typical Java 17/HotSpot:**

```text
requested=demo.NotPresent
lookup was app=true
lookup error=ClassNotFoundException
failing type=demo.ErrorContextDemo$Broken
defined by app=true
module=<unnamed>
source scheme=file
init error=ExceptionInInitializerError
root cause=IllegalStateException
```

Explanation:

- In the `ClassNotFoundException` branch, there are only the **requested binary name** and the **lookup loader**; there is no class result to mistakenly assign a module/CodeSource to.
- `Broken.value` is a static field that is **not a compile-time constant**; accessing it triggers initialization, `initialize()` throws `IllegalStateException`, and the JVM reports `ExceptionInInitializerError`.
- In the catch block, `Broken.class` lets us retrieve metadata of **the class that has already been defined**, even though initialization failed. The class may be in an **erroneous** state, yet its `Class<?>` metadata remains meaningful.
- The runtime class `demo.ErrorContextDemo$Broken` is defined by the app loader from the `out` directory, belongs to the unnamed module, and has the `file` CodeSource scheme in the example configuration.
- Logging the **root cause** is more important than printing only the top-level `ExceptionInInitializerError`; in real systems, the full stacktrace/cause chain must be preserved.

**Do not assume every `NoClassDefFoundError` is a missing file.** A class whose initialization previously failed can cause `NoClassDefFoundError` on subsequent active uses. Investigate the cause and **the earliest failure event**.

## 16. A Good Logger Must Preserve the Original Error and Must Not Throw Another Error

Do not write:

```java
try {
    service.run();
} catch (Throwable error) {
    System.err.println("source=" +
        service.getClass()
               .getProtectionDomain()
               .getCodeSource()
               .getLocation());
    // Accidental NullPointerException in the logger → obscures root cause.
}
```

This is an **unsafe pattern**, lacks `service`, and is not a runnable program. `CodeSource` can be null. Additionally, catching `Throwable` indiscriminately can hide `VirtualMachineError` or unrecoverable JVM errors.

Instead:

1. **Catch only error types within the handler's scope**, keeping the failure object intact.
2. If an actual class is available, retrieve metadata using a **null-safe** helper; if not, log the lookup context.
3. **Do not invoke a class constructor/initializer to retrieve metadata**; diagnostic operations must minimize side effects.
4. **Attach the throwable to the logger**: `logger.log(Level.SEVERE, "message", failure)` to preserve the stacktrace/cause.
5. Metadata failures (for example `SecurityException`) should only be turned into a `<denied>` sentinel or an auxiliary note, never replacing the primary error.
6. Limit log size and sanitize strings from untrusted sources.

Proper logging example:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("plugin.diagnostics");

static void reportFailure(
        String phase, String requested, ClassLoader lookup,
        Class<?> resolved, Throwable failure) {

    String type = resolved == null
            ? "<not-resolved>" : resolved.getName();

    LOG.log(java.util.logging.Level.SEVERE,
            "phase=" + phase
            + ", requested=" + requested
            + ", resolved=" + type
            + ", lookupLoader=" + String.valueOf(lookup),
            failure);
}
```

This is an **illustrative helper**, not yet a standalone runnable class; a real implementation adds the defining loader/module/code source from `resolved` in a null-safe manner. If `resolved == null`, do not fabricate metadata.

**Caution:** `String.valueOf(lookup)` may invoke a custom `toString()`. When handling security-sensitive loggers, use a separately managed loader identifier instead of executing arbitrary logic inside `toString()`.

## 17. Information to Record in a Class-Loading Error Entry

A structured log record can use the following fields:

| Field | Meaning | When absent |
| --- | --- | --- |
| `event` | `CLASS_LOAD_FAILURE`, `LINKAGE_FAILURE`, `PROVIDER_FAILURE` | Required |
| `phase` | `LOOKUP`, `DEFINE`, `LINK`, `INITIALIZE`, `INVOKE` | May be `UNKNOWN` if unknown to the caller |
| `requested_class` | Binary name requested by the code | `<not-applicable>` |
| `resolved_class` | `Class.getName()` when a `Class<?>` is available | `null`/omitted |
| `defining_loader_name` | `loader.getName()` or a framework-assigned label | `<unnamed>/<bootstrap>` |
| `defining_loader_type` | Java class name of the loader | `<bootstrap>` |
| `defining_loader_instance` | Scoped ID/plugin generation/identity hash | `<unknown>` |
| `module_name` | Named module or `<unnamed>` | `<not-resolved>` |
| `module_layer` | Named module layer when helpful | `<none>`/omitted |
| `code_source` | URL/code artifact ID if available and permitted to log | `<unavailable>/<denied>` |
| `lookup_loader` | Loader object initially queried | `<bootstrap>/<unknown>` |
| `tccl` | Thread context loader | May be `null` |
| `expected_artifact` | Expected plugin version/SHA | Omit if unknown |
| `actual_artifact` | Artifact from CodeSource/loader mapping | `<unknown>` |
| `error_type` | `failure.getClass().getName()` | Required |
| `message` | Sanitized error message | May be empty |
| `cause_chain` | Causes and suppressed errors within limits | May be absent |
| `stacktrace` | Stacktrace preserved in the logging backend | May be truncated by policy |
| `correlation_id` | Links request, job, and plugin generation | Do not fabricate if unavailable |

This is a **suggested schema**; not every system needs to print all fields on every request. The goal is to have enough information to answer **“which class was requested, what defined the actual class, which module it belongs to, and where the bytes may have come from?”**.

For `ClassCastException`, **two sets of metadata** are needed for expected/actual types. For `ClassNotFoundException`, `resolved_class` is absent. For `ServiceConfigurationError`, inspect both the service API identity and which loader/TCCL discovered the provider implementation.

## 18. Java 9+ Stacktraces Include Module/Loader, but Still Lack CodeSource

Java 9 added fields to `StackTraceElement`:

```java
String classLoaderName = frame.getClassLoaderName();
String moduleName = frame.getModuleName();
String moduleVersion = frame.getModuleVersion();
String className = frame.getClassName();
```

This is a **snippet** requiring a `frame` of type `StackTraceElement`. The loader/module/version fields can be null if the JVM has no corresponding metadata; `getClassName()` is the class name according to the frame, not a `Class<?>` object.

A stack trace can display module/loader prefixes:

```text
at java.base/java.lang.Thread.run(Thread.java:...)
at plugin-A//plugin.Widget.run(Widget.java:...)
```

This is an **illustrative format example**, not specific output from the program in section 12. Stacktrace formatting can depend on runtime/module/loader names; do not parse this text as a stable protocol.

Limitations:

- The loader name in a frame is not a guaranteed unique object identity.
- `StackTraceElement` **does not have `getCodeSource()`**.
- A frame shows where the exception stack passed through, and does not itself reveal the **expected runtime class** in a `ClassCastException`.
- A class may have already been unloaded or cannot be looked up again from the current TCCL; do not assume `Class.forName(frame.getClassName())` will load the exact original class.
- The named module name/version in a frame may not be enough to distinguish two layers or artifacts.

Therefore, **preserve the stacktrace**, while also logging `Class<?>` metadata at boundaries where type objects are available.

## 19. Do Not Let the Logger Alter the Class-Loading Process

Diagnostic actions that can cause side effects:

- Calling the single-argument overload `Class.forName(name)` can **initialize the class**, running static blocks.
- Using `Class.forName(name, true, loader)` also requests initialization.
- Calling `getDeclaredMethods()` or performing deep reflection can trigger additional resolution/access checks, raising other errors if dependencies are missing.
- Printing `loader.toString()` on a custom loader can execute user-defined code.
- Calling `resourceUrl.openStream()` to “inspect bytes” can cause I/O/blocking, network access, and permission checks.
- Scanning all of `java.class.path`/`java.module.path` at error time can be time-consuming or expose deployment information.
- Logging full URLs, environment variables, system properties, or command-line arguments can leak secrets.

**Minimally invasive diagnostics:** if you already have `Class<?> type`, retrieve `getName()/getClassLoader()/getModule()/getProtectionDomain()` according to policy. If the class does not exist yet, record the requested name + lookup loader + known artifact paths from configuration without attempting to initialize a new class just to “see more metadata”.

During deep investigation outside the request flow, you can use `Class.forName(name, false, loader)` to request a lookup **without actively initializing the target**, though that operation can still **load/link additional classes or throw an error**. Do this deliberately; do not put it into every error handler.

## 20. Common Errors Table and Prioritized Metadata

| Symptom | Important metadata | Hypotheses to verify |
| --- | --- | --- |
| `ClassNotFoundException` | Requested binary name, lookup loader, TCCL, URLs/JAR entries | Class not found from allowed sources |
| `NoClassDefFoundError` | Missing dependency name, loader, earliest cause/stacktrace | Dependency failed to load/link or class is erroneous |
| `ClassCastException` | Expected + actual `Class<?>`, defining loaders, modules, CodeSources | Two different runtime type identities |
| `NoSuchMethodError` | Caller and callee CodeSources, binary descriptors, loader, module | Version skew: compiled against a different API than runtime |
| `NoSuchFieldError` | Callee artifact/version + field descriptor | Runtime class is missing the corresponding field |
| `LinkageError: loader constraint violation` | Types in method descriptors, both defining loaders | Loaders use incompatible definitions |
| `IllegalAccessError` | Caller/target module, runtime package, defining loader, exports | Incompatible package-private/JPMS access |
| `InaccessibleObjectException` | Caller module, target module/package, opens rules | Deep reflection into an unopened package |
| `ServiceConfigurationError` | Service API, provider name, loader/TCCL, descriptor/JAR | Provider missing, not assignable, or constructor/factory error |
| `ExceptionInInitializerError` | Failing class, module, CodeSource, root cause | `<clinit>` failed; class was loaded but not initialized |
| `ClassFormatError` | Class bytes source, classfile major/minor, generator version | Malformed bytecode/class file structure |
| `UnsupportedClassVersionError` | Artifact path, `javap -verbose`, running JVM version | Classfile version too new/preview mismatch |

**Do not infer from the exception message alone.** `NoClassDefFoundError` has more than one cause; `IllegalAccessError` can involve packages/modules, not merely `private`. Class metadata and the cause chain are what allow verification.

## 21. CodeSource Location Does Not Prove Checksum, Version, or Actual Source After Transformation

A common mistake is taking:

```java
URL origin = type.getProtectionDomain()
                 .getCodeSource().getLocation();
```

and concluding “this class definitely has hash X because the JAR is at path Y”. This is **not checksum verification**.

With custom loaders, bytecode can be transformed before `defineClass`; the path/code source still indicates only the starting point or the assigned domain. The file on disk may be replaced after the bytes have been loaded. A multi-release JAR can select class bytes based on the runtime version. Java agents can transform bytecode at load time. Therefore, a CodeSource URL does not by itself prove the entirety of the bytecode defined by the JVM.

If you need **strong provenance**:

1. At deployment time, record the artifact build ID, version, and SHA-256 digest from a trusted source.
2. If you need to verify the loaded content, design the bytecode loader pipeline to verify the digest/signature according to policy before defining the class.
3. Record the **loader generation → artifact ID/version/digest** mapping outside class metadata, with clear ownership.
4. Do not automatically fetch arbitrary URLs inside an error handler to hash remote content; doing so can cause SSRF, latency, secret exposure, or reading bytes different from what actually ran.
5. For classes transformed by a Java agent, if auditing post-transform content is truly needed, build a dedicated mechanism at the instrumentation boundary and manage log security.

**The code source in logs is an indicator for narrowing down the issue, not complete proof of integrity.**

## 22. Combining Log Metadata with JVM and Artifact Inspection

When `Class<?>` metadata reveals an unexpected loader or CodeSource, you can run HotSpot with `-Xlog:class+load=info` to observe class names and sources as the JVM loads them:

```bash
java -Xlog:class+load=info -cp out demo.DiagnosticDemo
```

This is an illustrative command; the lines output by the JVM depend on the JDK, classpath, and load timing. A load log does not prove that a class has initialized, nor does it always provide the loader's object identity. Use `java -Xlog:help` to inspect available tags. For `NoSuchMethodError`, compare binary descriptors from the runtime artifact using `javap -s -p`; use `jar --list --file plugin.jar` to inspect entries. Both tool commands read artifacts from disk and do not prove that the JVM actually selected that specific artifact.

Subsequent articles separately cover how to read Unified Logging (`-verbose:class`, `class+load`, `class+init`), as well as workflows for `javap`/`jar`/`jdeps`. The focus here is **connecting offline diagnostic results to the exact logged runtime class/loader**, while preserving the original throwable/cause.
## 23. Class Loader + Module Access: Reading Both Sides of the Error

For `IllegalAccessError` or JPMS reflection errors, log all of the following:

- **caller class**: the `Class<?>` representing the calling code, along with its loader/module/package;
- **target class**: loader/module/package/code source;
- **member**: method/field name and descriptor if available;
- **module rules**: whether the caller module reads the target module, and whether the target package has appropriate exports/opens;
- **runtime package**: whether the two classes share the same package name *and* defining loader.

With named modules, `module.isNamed()` and `module.getName()` provide the name, but **a module name is not equivalent to module object identity**. When there are multiple `ModuleLayer` instances, recording the layer/loader helps distinguish configurations that share the same module name.

Example logic:

```java
Module callerModule = callerClass.getModule();
Module targetModule = targetClass.getModule();

boolean reads = callerModule.canRead(targetModule);
boolean exported = targetModule.isExported(
        targetClass.getPackageName(), callerModule);

System.err.println("reads=" + reads);
System.err.println("exported=" + exported);
```

This is a **snippet** requiring two variables `callerClass`/`targetClass`. `canRead`/`isExported` aid diagnosis but do not prove that a specific reflective operation will succeed; member visibility, `opens`, lookup privileges, and caller context still matter.

## 24. When an Error Occurs in ServiceLoader

For `ServiceConfigurationError`, log **two distinct roles**: the service API type requested by the consumer and the provider implementation (if the provider has been resolved), along with the loader/module/CodeSource of each side. In addition, log the loader used to discover providers: the `ServiceLoader.load(service)` overload uses the TCCL, whereas `ServiceLoader.load(service, chosenLoader)` uses the passed-in loader.

If discovery fails before obtaining a provider `Class<?>`, record only the provider *binary name* read from the descriptor (if known), without fabricating a defining loader. Distinguish between a missing provider descriptor, a provider that failed to load, a failing constructor, and a provider that is not assignable because the service interface was defined twice. Preserve `ServiceConfigurationError` and its cause. In named modules, check `uses`/`provides` and the relevant layer. The ServiceLoader article in the context class loader chapter explains the SPI mechanism in detail.
## 25. Structured Log Pattern Without Exposing Information to End Users

An internal record:

```json
{
  "event": "PLUGIN_LINKAGE_FAILURE",
  "correlationId": "req-42",
  "phase": "INVOKE",
  "requestedClass": "plugin.Widget",
  "resolvedClass": "plugin.Widget",
  "definingLoader": "plugin-A",
  "module": "<unnamed>",
  "codeSource": "<internal-artifact-id>",
  "errorType": "java.lang.ClassCastException",
  "expectedType": "api.Widget",
  "actualType": "plugin.Widget"
}
```

This is an **illustrative sample JSON**, not executed output from any example and not a mandatory schema. The ID/source values are illustrative only. The internal error logger should also store the actual throwable/stacktrace and plugin generation according to policy.

The message returned to the client can simply be:

```text
PLUGIN_EXECUTION_FAILED (correlationId=req-42)
```

Do not expose paths like `file:/home/.../deployment/secrets`, absolute filesystem paths, internal hostnames, signer metadata, or full stacktraces through a public API. **Rich information for operators, minimal information for untrusted callers** is the better choice.

A structured log can still allow log injection if fields accept untrusted data. The logging backend must escape newline/control characters and limit the size of each field.

## 26. Practical Classloading Diagnostics Checklist

1. **Identify the operation**: `loadClass`, `Class.forName`, SPI discovery, linkage, init, or reflection/invoke?
2. **Record the requested binary name** when there is no `Class<?>` yet. Do not fabricate a placeholder “resolved class”.
3. **If a runtime class is available**, record `getName()`, `getClassLoader()`, `getModule()`, and null-safe `CodeSource.location`.
4. **Identify the loader instance** by name/type/framework-assigned ID, not only the loader's Java class name.
5. **Record both expected and actual classes** for cast/assignability failures.
6. **Record the lookup loader and TCCL** if they can affect delegation/discovery.
7. **Do not assume CodeSource must exist**: bootstrap, generated classes, and custom loaders can return null.
8. **Clearly record named/unnamed module**, and the module layer if the system uses multiple layers.
9. **Preserve the stacktrace/cause chain** of the first failure; especially when `ExceptionInInitializerError` leads to a later `NoClassDefFoundError`.
10. **Cross-check the actual artifact**: full CodeSource in permitted internal logs, build/version/digest, and URL roots.
11. **Do not trigger unintended initialization** just to log metadata.
12. **Do not make unbounded network/I/O calls in an error handler**, and do not download classes/JARs solely to test a hypothesis.
13. **Respect log security**: redact secrets/paths/tenant data, and keep the correlation ID.
14. **Reproduce in the exact class loader graph**; an IDE/test classpath can cause the parent loader to shadow a plugin JAR.
15. **Verify failures after a fix**: resolving `ClassNotFoundException` may uncover a `NoSuchMethodError` caused by a dependency version.
16. **Clearly recognize the limits** of logging: CodeSource does not prove integrity, loader name is not a unique identifier, and module name does not determine all access.

## 27. Common Misinterpretations to Avoid

- **“Same `Class.getName()` means the same runtime type.”** False if the defining loaders differ.
- **“If `child.loadClass` returns a class, that class was defined by child.”** False; parent-first delegation can return a parent's class.
- **“`getClassLoader() == null` means the class is broken.”** False; it is usually bootstrap or a primitive.
- **“`getModule().getName() == null` means there is no module.”** False; an unnamed module is valid.
- **“Every `Class<?>` has a CodeSource URL.”** False; `CodeSource` or its location can be null.
- **“The current CodeSource file path proves the bytes loaded by the JVM.”** False; the file may have changed or the bytes may have been transformed.
- **“`Class.getResource` is the same as `CodeSource.getLocation`.”** False; class resources and artifact provenance have different semantics.
- **“`ClassNotFoundException` always has a `Class<?>` to print loader/module.”** No; you must log the requested name and lookup context.
- **“A single-line exception message is enough to find the right JAR.”** Not in plugin/module loader graphs.
- **“`ClassLoader.getName()` is globally unique.”** No; it can be null/duplicated, so add a generation/instance ID.
- **“`StackTraceElement.getModuleName()` provides the code source.”** No; there is no `getCodeSource` on a stack frame.
- **“Logging full absolute paths/URLs in client responses is safe.”** No; it can expose internal details/secrets.
- **“Calling `Class.forName(name)` just to inspect metadata has no side effects.”** False; the default overload can initialize the class.
- **“Catching `Throwable` and running deep reflective probes always improves logs.”** False; it can obscure the root cause, introduce new errors, or block.
- **“`javap` proves the runtime selected that artifact.”** False; it is an offline bytecode inspection tool.
- **“Adding `-Xlog:class+load` means every class has initialized.”** False; loading and initialization are different.
- **“Having the same module name means having the same loader identity.”** No; you need the module object, layer, and defining loader.

## 28. Self-Check Questions

**1. What four pieces of runtime information should be included when logging a `Class<?>`?** Class name, defining loader, module, and CodeSource location if provided.

**2. What can `Class.getClassLoader() == null` be?** Bootstrap loader representation or a primitive/void type.

**3. What does `module.getName() == null` mean?** An unnamed module, not a class belonging to no module.

**4. Why does `child.loadClass("api.Contract")` not prove that child defined the class?** Parent-first delegation can return a parent's class; you need to check `type.getClassLoader()`.

**5. Can `CodeSource.getLocation()` be null?** Yes; null-safe checks are required.

**6. Why not print `ClassNotFoundException` together with a defining loader?** The lookup failed so there is no resolved `Class<?>` yet; log only the requested name and lookup loader.

**7. Why does `ClassCastException` need metadata for both the expected and actual types?** Two types may share the same binary name while having different defining loaders, making `isAssignableFrom` false.

**8. Does `ClassLoader.getName()` guarantee distinct identification for two loader instances?** No. It can be null or duplicated; also use a runtime-scoped identity/generation.

**9. How does a CodeSource URL differ from a class resource URL?** CodeSource typically describes a JAR/directory-level source/domain; a resource can point to an individual `.class` and is looked up according to module/loader rules.

**10. If a JDK class has `CodeSource == null`, can we conclude it is missing a JAR?** No; this can be normal in the runtime image.

**11. Should `Class.forName(name)` be used inside an exception logger to retrieve metadata?** Not by default; it can trigger class initialization.

**12. For `NoSuchMethodError`, what else is needed besides the loader and CodeSource?** Compare compile-time/runtime method descriptors (`javap -s`), versions, dependencies, and the callsite.

**13. With named modules, is the module name enough to confirm valid access?** No; you must inspect readability, exports/opens, caller/target modules, and members.

**14. Which loader/module metadata does `StackTraceElement` in Java 9+ provide?** `getClassLoaderName()`, `getModuleName()`, and `getModuleVersion()` — they can be null.

**15. Should a CodeSource URL be trusted like a SHA-256 of the bytes the JVM executed?** No; integrity requires verifying the artifact/bytes separately.

**16. How should class metadata be logged without leaking secrets?** Use artifact ID/build version in public records, keep full URLs in controlled internal systems, and redact paths/tokens.

**17. Can a class generated completely in memory by a custom loader have a CodeSource?** It can if a domain was assigned, or it can have none; do not assume one must exist.

**18. When a logger encounters a `SecurityException` while reading metadata, what should it do?** Preserve the primary error, record a sentinel such as `<denied>`, and never replace the original throwable.

## 29. Official References

- [Java SE 17 — `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `getModule`, `getProtectionDomain`, `getResource`.
- [Java SE 17 — `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getName`, parent delegation, `loadClass`, `getParent`.
- [Java SE 17 — `Module` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isNamed`, `getName`, `getLayer`, readability/exports.
- [Java SE 17 — `ProtectionDomain` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): `getCodeSource()` and domain metadata.
- [Java SE 17 — `CodeSource` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html): `getLocation()`, signer information, and nullability.
- [Java SE 17 — `StackTraceElement` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): frame class, loader/module names, and versions.
- [Java SE 17 — `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL roots, named loaders, and class/resource loading.
- [Java Virtual Machine Specification 17, `5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loaders, runtime type identity, linking/access.
- [JDK 17 `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting binary names, descriptors, and classfile major version.

**Conclusion:** When a Java application encounters a class loading/linking error, **the class name alone is not enough**. If a `Class<?>` is available, log **`getName()` + `getClassLoader()` + `getModule()` + null-safe `ProtectionDomain/CodeSource`**, combined with the lookup loader/TCCL, expected/actual types, stacktrace, and artifact generation. If the class has not loaded successfully, log the **requested name and lookup context**, without fabricating a defining loader/module. Finally, always balance diagnostic quality with **the possibility of missing metadata and log information security**.
