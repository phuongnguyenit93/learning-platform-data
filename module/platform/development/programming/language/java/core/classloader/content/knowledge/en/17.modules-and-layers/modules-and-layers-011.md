# Loading Resources from Modules Using Class, ClassLoader, and Module in Java

When learning **classloader** in Java 9+ (including Java 17), you cannot always apply the mindset “if a resource is in the JAR/classpath, any class loader that finds it can read it”. With the **Java Platform Module System (JPMS)**, a resource can belong to a **named module**, and finding/reading resources is governed by **module encapsulation** rules.

Three easily confused APIs:

- `SomeClass.class.getResource(...)` and `SomeClass.class.getResourceAsStream(...)`: look up a resource **associated with a Class**, resolve relative names against its package, and, when the class belongs to a named module, search within **that module itself**.
- `someClassLoader.getResource(...)`, `getResources(...)`, and `getResourceAsStream(...)`: look up a resource via a **class loader**, following delegation rules and strict constraints when the resource resides in a package of a **named module**.
- `someModule.getResourceAsStream(...)`: look up a resource **owned by a specific Module**, while checking whether the package is open to the **caller's module**.

**Key takeaway:** A resource can exist in a module and be readable using `Class.getResourceAsStream` or `Module.getResourceAsStream` from code **inside the module**, yet still return **`null`** when code calls `ClassLoader.getResourceAsStream` — even when it is the same defining class loader. `exports` on a package containing public types **is not equivalent to `opens` for allowing access to non-`.class` resources**.

## 1. Recap: Resources, Classpath, and Modules

A resource is data packaged by an application alongside its code: `.properties`, `.json`, `.xml`, images, templates, schemas, `META-INF/services`, or even `.class` files.

For example, an application running on the classpath:

```text
out/
└── demo/
    ├── Main.class
    └── config.properties
```

The code snippets:

```java
URL a = Main.class.getResource("config.properties");
URL b = Main.class.getClassLoader()
        .getResource("demo/config.properties");
```

can return the same resource if the resource lies on the right search path. However, the two APIs use **different name interpretations**; and if `Main` is in a **named module**, `Class` can locate the resource in the module via a different mechanism than a public classloader lookup.

### What Is a Module at Runtime?

`java.lang.Module` represents a runtime module, either named or unnamed. Retrieve it via:

```java
Module m = Main.class.getModule();
System.out.println(m.getName());
System.out.println(m.isNamed());
```

This is an illustrative snippet requiring the `Main` class in scope. A class on the classpath typically belongs to the **unnamed module** of its defining loader. A class on the module path with a `module-info.class` is resolved into a **named module**, for example `com.acme.core`.

**A named module is not a class loader.** A single class loader can define classes from multiple named modules; knowing only the defining loader is not enough to determine which module owns a resource. This is one reason `Module.getResourceAsStream` and `Class.getResource...` exist.

## 2. Exact Comparison of the Three API Groups

| API | Input | Search Scope | Result |
|---|---|---|---|
| `SomeClass.class.getResource("a.txt")` | Package-relative name | Resource associated with `SomeClass`; in a named module, searches within the class's module | `URL` or `null` |
| `SomeClass.class.getResource("/pkg/a.txt")` | Absolute name from root | Same as above, except strips the leading `/` before lookup | `URL` or `null` |
| `SomeClass.class.getResourceAsStream(...)` | Same naming rules as `Class.getResource` | As above, returns a stream for reading bytes | `InputStream` or `null` |
| `loader.getResource("pkg/a.txt")` | Resource name from root, **without a leading `/`** | Parent/loader resource lookup; named modules are encapsulated | `URL` or `null` |
| `loader.getResources("pkg/a.txt")` | Resource name from root | Can find **multiple** resources across the loader hierarchy/modules according to its contract | `Enumeration<URL>` |
| `loader.getResourceAsStream("pkg/a.txt")` | Resource name from root | Stream read via loader lookup | `InputStream` or `null` |
| `module.getResourceAsStream("pkg/a.txt")` | Resource name from root (may have a leading `/`) | **Exactly one Module**; applies open checks against the caller module | `InputStream` or `null` |

Avoid two misconceptions:

1. `Class.getResourceAsStream` **does not simply** always delegate to `clazz.getClassLoader().getResourceAsStream` in Java 17. For a class belonging to a named module, the Javadoc specifies that it performs a **module-aware lookup** and checks accessibility based on the **caller's module**.
2. `ClassLoader.getResource` **does not bypass JPMS** merely because you hold a loader instance. For a non-`.class` resource inside a package of a named module, the ClassLoader API requires that package to be **opened unconditionally**. This behavior applies even when the calling code is in the same module; the ClassLoader API does not grant access based on the caller module like the other two APIs do.

The explanatory line in angle brackets above is descriptive, not Java syntax.

## 3. Resource Naming Rules: Class vs. ClassLoader/Module

Suppose a module contains:

```text
demo/assets/internal/
    Inside.class
    secret.txt
```

With the class `demo.assets.internal.Inside`:

```java
Inside.class.getResource("secret.txt");
Inside.class.getResource("/demo/assets/internal/secret.txt");
Inside.class.getResourceAsStream("secret.txt");
```

All target `demo/assets/internal/secret.txt` according to the naming rules.

- For **`Class.getResource`** and `Class.getResourceAsStream`: a name starting with `/` is resolved from the root; a name without a leading `/` is resolved relative to the class's package.
- For **`ClassLoader.getResource`**: pass `"demo/assets/internal/secret.txt"`, **without** a leading `/`; the name is in path form using `/` separators.
- For **`Module.getResourceAsStream`**: typically pass the name from the root such as `"demo/assets/internal/secret.txt"`; the API accepts a leading `/` and strips it before lookup.

Example:

```java
String name = "demo/assets/internal/secret.txt";
ClassLoader cl = Inside.class.getClassLoader();
Module mod = Inside.class.getModule();

InputStream a = Inside.class.getResourceAsStream("secret.txt");
InputStream b = cl.getResourceAsStream(name);
InputStream c = mod.getResourceAsStream(name);
```

This is an **illustrative snippet inside a method**, requiring an import of `java.io.InputStream`, the `Inside` class, and handling `IOException` for the call on `Module`. **Do not assume `a`, `b`, and `c` are equal**: if the resource is in an encapsulated package of a named module, `a` and `c` can be read from code inside the module while `b` is `null`.

**Do not call `ClassLoader.loadClass("demo/assets/internal/Inside.class")`.** `loadClass` takes a **binary class name** with dots, `demo.assets.internal.Inside`, not a resource path.

## 4. How Does JPMS Encapsulation Apply to Resources?

For a resource inside a **named module**, Java SE 17 `Module.getResourceAsStream` describes:

1. If the resource name ends with **`.class`**, that resource **is not encapsulated by this rule**.
2. The JVM/API derives the package name from the portion of the path before the last `/`, replacing each `/` with `.`.
3. If that package name **is actually a package in the module**, a non-`.class` resource can only be read from another caller module if the package is **opened (`opens`)** to that caller module.
4. If the path does not correspond to an actual package of the module, the resource **is not encapsulated under the package rule**. For example, `META-INF/MANIFEST.MF` does not belong to a valid Java package.
5. A resource that does not exist, is inaccessible, or is denied may result in `null`. With the `Module.getResourceAsStream` API, I/O errors can throw `IOException`.

### Exports Is Not Opens

`module-info.java`:

```java
module demo.assets {
    exports demo.assets.api;
}
```

allows other modules to **use public types** in the `demo.assets.api` package according to JPMS access rules. It **does not** mean that the `demo.assets.internal` package is open for other modules to read `secret.txt`.

Declaration forms:

```java
// Examples of each declaration style; do not combine all of them to apply at once:
exports demo.assets.api;
opens demo.assets.internal;
opens demo.assets.internal to demo.consumer;
```

These are **illustrative lines belonging to a module declaration**, not standalone Java code.

- `exports pkg;`: exposes public API types according to module access rules; **not sufficient** for non-`.class` resources to be found by a ClassLoader.
- `opens pkg;`: opens the package **unconditionally** to all modules; a ClassLoader can find non-`.class` resources in this package if other lookup conditions are met.
- `opens pkg to some.module;`: **qualified opens**, opening the package to a specified set of modules; `Module.getResourceAsStream` and `Class.getResourceAsStream` from an opened caller module can succeed, but **ClassLoader lookup still requires unconditional opens**.
- `open module demo.assets { ... }`: declares an open module whose packages are opened unconditionally; it has a broader impact and should not be used just to handle a single config file.
- `--add-opens module/package=target` at launch: can add controlled qualified opens; **does not turn qualified opens into unconditional opens**.

**Most important rule:** For `ClassLoader.getResource`/`getResources`/`getResourceAsStream`, the exception is for resources ending in `.class`; non-`.class` resources in a named module's package must belong to a package that is **opened unconditionally**, even when the code calling `ClassLoader` resides in that same module. This is a detail easily overlooked when migrating a project from the classpath to the module path.

## 5. Runnable Java 17+ Example: Same Module, Three APIs, Three Different Results

The test has two sides:

- **Named module `demo.assets`** owns a private resource `demo/assets/internal/secret.txt` in a package with **no `exports` and no `opens`**.
- **A classpath/unnamed module application** calls the public API `demo.assets.api.Api` and attempts to read the module's resource from outside.

A metadata file at `META-INF/demo.info` is placed **outside any package** for comparison: it is not encapsulated because the name `META-INF` is not a Java package.

### 5.1. File Structure

```text
module-resource-demo/
├── src/
│   └── demo.assets/
│       ├── module-info.java
│       └── demo/
│           └── assets/
│               ├── api/
│               │   └── Api.java
│               └── internal/
│                   └── Inside.java
├── resources/
│   └── demo.assets/
│       ├── demo/
│       │   └── assets/
│       │       └── internal/
│       │           └── secret.txt
│       └── META-INF/
│           └── demo.info
└── src-app/
    └── DemoMain.java
```

### 5.2. Module Descriptor

File **`src/demo.assets/module-info.java`**:

```java
module demo.assets {
    exports demo.assets.api;
}
```

Only the API package is exported so callers outside the module can invoke `Api.check()`. The `demo.assets.internal` package is an internal package, with neither `exports` nor `opens`.

### 5.3. Public API of the Module

File **`src/demo.assets/demo/assets/api/Api.java`**:

```java
package demo.assets.api;

import demo.assets.internal.Inside;

public final class Api {
    public static void check() throws Exception {
        Inside.check();
    }
}
```

`Api` is exported via `module-info.java`. Even though the `demo.assets.internal` package is not exported externally, **code inside the same module** such as `Api` can reference `Inside` because they are in the same module and `Inside` is declared public.

### 5.4. Resource-Reading Code Inside the Module

File **`src/demo.assets/demo/assets/internal/Inside.java`**:

```java
package demo.assets.internal;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Inside {
    private static final String NAME =
            "demo/assets/internal/secret.txt";

    private static String value(InputStream in) throws Exception {
        if (in == null) {
            return "(null)";
        }
        try (in) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void check() throws Exception {
        Module m = Inside.class.getModule();

        System.out.println("inside Class: "
                + value(Inside.class.getResourceAsStream("secret.txt")));

        System.out.println("inside ClassLoader: "
                + value(Inside.class.getClassLoader()
                        .getResourceAsStream(NAME)));

        System.out.println("inside Module: "
                + value(m.getResourceAsStream(NAME)));

        System.out.println("module named: " + m.isNamed());
    }
}
```

Within the same module:

- `Inside.class.getResourceAsStream("secret.txt")` knows which module the class belongs to and has **module-aware access** for its own module's package.
- `Inside.class.getClassLoader().getResourceAsStream(NAME)` follows the **ClassLoader** rule, so a non-`.class` resource in an internal package that is not opened unconditionally **is not returned**.
- `m.getResourceAsStream(NAME)` is called from `Inside` code belonging to the **same module**, so it is allowed to access the content if the resource exists.

### 5.5. Code Outside the Module

File **`src-app/DemoMain.java`**:

```java
import demo.assets.api.Api;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class DemoMain {
    private static String value(InputStream in) throws Exception {
        if (in == null) {
            return "(null)";
        }
        try (in) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Api.check();

        Module module = Api.class.getModule();
        String name = "demo/assets/internal/secret.txt";

        System.out.println("outside Module: "
                + value(module.getResourceAsStream(name)));

        System.out.println("outside ClassLoader: "
                + value(Api.class.getClassLoader()
                        .getResourceAsStream(name)));

        System.out.println("outside Class URL: "
                + (Api.class.getResource("/" + name) != null));

        System.out.println("class file visible: "
                + (Api.class.getClassLoader().getResource(
                        "demo/assets/internal/Inside.class") != null));

        System.out.println("outside root META-INF: "
                + value(module.getResourceAsStream(
                        "META-INF/demo.info")));
    }
}
```

`DemoMain` runs in the **unnamed module**, a different module from `demo.assets`. It can reference `Api` (exported), but **does not automatically have permission to read private resources belonging to the `demo.assets.internal` package**.

### 5.6. Creating the Two Resources

File **`resources/demo.assets/demo/assets/internal/secret.txt`**:

```text
hidden-in-module
```

File **`resources/demo.assets/META-INF/demo.info`**:

```text
public-metadata
```

### 5.7. Compiling and Running on Bash

From the root directory `module-resource-demo` (Linux/macOS/Git Bash), using JDK 17+:

```bash
mkdir -p mods/demo.assets/demo/assets/internal
mkdir -p mods/demo.assets/META-INF out/app

javac --release 17 -d mods/demo.assets \
  src/demo.assets/module-info.java \
  src/demo.assets/demo/assets/api/Api.java \
  src/demo.assets/demo/assets/internal/Inside.java

cp resources/demo.assets/demo/assets/internal/secret.txt \
   mods/demo.assets/demo/assets/internal/secret.txt
cp resources/demo.assets/META-INF/demo.info \
   mods/demo.assets/META-INF/demo.info

javac --release 17 --module-path mods \
  --add-modules demo.assets \
  -d out/app src-app/DemoMain.java

java --module-path mods --add-modules demo.assets \
  -cp out/app DemoMain
```

`--module-path mods` tells the runtime/compiler where to find the named module `demo.assets`. `--add-modules demo.assets` forces this module to be resolved when using a main class from the classpath/unnamed module. Do not run only `java -cp out/app ...` expecting the JVM to automatically discover the module from `mods`.

### 5.8. Basic Equivalent on Windows PowerShell

Replace the directory creation and resource copying steps with:

```powershell
New-Item -ItemType Directory -Force -Path mods/demo.assets/demo/assets/internal, mods/demo.assets/META-INF, out/app | Out-Null

javac --release 17 -d mods/demo.assets src/demo.assets/module-info.java src/demo.assets/demo/assets/api/Api.java src/demo.assets/demo/assets/internal/Inside.java

Copy-Item -LiteralPath resources/demo.assets/demo/assets/internal/secret.txt -Destination mods/demo.assets/demo/assets/internal/secret.txt
Copy-Item -LiteralPath resources/demo.assets/META-INF/demo.info -Destination mods/demo.assets/META-INF/demo.info

javac --release 17 --module-path mods --add-modules demo.assets -d out/app src-app/DemoMain.java

java --module-path mods --add-modules demo.assets -cp out/app DemoMain
```

### 5.9. Exact Output

The example was **compiled with `javac --release 17` and run on OpenJDK 21**, using the exact module structure above:

```text
inside Class: hidden-in-module
inside ClassLoader: (null)
inside Module: hidden-in-module
module named: true
outside Module: (null)
outside ClassLoader: (null)
outside Class URL: false
class file visible: true
outside root META-INF: public-metadata
```

**Result explanation:**

1. `inside Class`: code in the module's internal package calls `Class.getResourceAsStream`, so it is treated as a caller from **the module itself**.
2. `inside ClassLoader`: there is no unconditional `opens demo.assets.internal;`, so the non-`.class` resource is not visible through `ClassLoader`.
3. `inside Module`: a caller in the same module is allowed to read that module's resource.
4. `outside Module`: the caller is in the unnamed module; the `demo.assets.internal` package is not open to the caller, so it returns `null`.
5. `outside ClassLoader`: the ClassLoader rule requires unconditional opens; since that is not satisfied, it returns `null`.
6. `outside Class URL`: `Api.class.getResource("/.../secret.txt")` from an unnamed caller is also subject to module encapsulation rules; no URL is produced.
7. `class file visible`: `Inside.class` ends with `.class`, so the **`.class` resource exception** applies; the class-loader lookup can still see the class-file URL in this test.
8. `outside root META-INF`: the resource under `META-INF` is not in a Java package of the module, so it is permitted to be found under module resource rules, and prints the exact content.

**Do not conclude that every class file or every root resource in every runtime must have a URL.** Encapsulation rules do not forbid them the way non-`.class` package resources are forbidden, but in practice it still depends on whether the resource exists, whether the loader can construct a URL, and the runtime environment.

## 6. Testing Qualified Opens: Opening to the Caller Is Not Enough for ClassLoader

Keep the entire compiled project unchanged. Run again with:

```bash
java --module-path mods --add-modules demo.assets \
  --add-opens demo.assets/demo.assets.internal=ALL-UNNAMED \
  -cp out/app DemoMain
```

On PowerShell, you can use a single line:

```powershell
java --module-path mods --add-modules demo.assets --add-opens demo.assets/demo.assets.internal=ALL-UNNAMED -cp out/app DemoMain
```

`ALL-UNNAMED` in the launcher specifies the target as unnamed modules, including the module containing `DemoMain` in the example. This is **qualified opens**, not opening the package unconditionally.

Second output (tested):

```text
inside Class: hidden-in-module
inside ClassLoader: (null)
inside Module: hidden-in-module
module named: true
outside Module: hidden-in-module
outside ClassLoader: (null)
outside Class URL: true
class file visible: true
outside root META-INF: public-metadata
```

Comparison:

| Lookup | Before qualified opens | After qualified opens |
|---|---|---|
| `Inside.class.getResourceAsStream` called inside the module | Succeeds | Succeeds |
| `Inside.class.getClassLoader().getResourceAsStream` | `null` | Still `null` |
| `Module.getResourceAsStream` called from the unnamed module | `null` | Succeeds |
| `Class.getResource` called from the unnamed module | `null` | Succeeds |
| `ClassLoader.getResourceAsStream` called from the unnamed module | `null` | Still `null` |

This is practical evidence of **the difference in access control granularity**:

- `Class`/`Module` checks whether the package is open to the **caller module**.
- `ClassLoader`, for non-`.class` resources in named-module packages, only returns the resource if the package is **opened unconditionally**.

If you modify `module-info.java` to:

```java
module demo.assets {
    exports demo.assets.api;
    opens demo.assets.internal;
}
```

and recompile the module, the internal package will be opened unconditionally according to the module declaration. When the remaining resource-lookup conditions are satisfied, ClassLoader can see `secret.txt`. This is a **different design choice**, not a free tweak: it opens the package much more broadly, so encapsulation must be weighed.

**Security note:** Do not add `opens` or `--add-opens` indiscriminately just so a piece of code can read a config. If a resource is internal, it is usually better to have an API read the resource **inside the module** and expose only the processed data.

## 7. Reading Resources from the Right Class and the Right Module

When code and resource belong to the same named module, a common approach is to let a class inside the module own the reading:

```java
package demo.assets.internal;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ConfigReader {
    public static String load() throws IOException {
        try (InputStream in =
                ConfigReader.class.getResourceAsStream("secret.txt")) {
            if (in == null) {
                throw new IOException("Missing secret.txt");
            }
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

This is a **compilable utility class**, though it has no `main` and must be built with the `secret.txt` resource actually in the same package. When `ConfigReader.load()` runs inside the module owning the package, `Class.getResourceAsStream` uses the appropriate caller context to read the internal resource without having to open the package to all modules.

At the module level, you can use:

```java
Module owner = ConfigReader.class.getModule();
try (InputStream in = owner.getResourceAsStream(
        "demo/assets/internal/secret.txt")) {
    if (in == null) {
        throw new IOException("Resource missing/inaccessible");
    }
    // Process the stream here.
}
```

This is an illustrative snippet inside a method that has `InputStream` and `IOException` imported; access conditions are still checked against the **actual caller's module**. If you move this exact code into another module, the internal resource may become `null`.

**Remember:** Reading via `Class` does not grant permanent access to every caller. It can succeed when the call originates inside module A, yet a caller in module B calling `AClass.class.getResource(...)` can be denied when A does not open the package to B.

## 8. When to Choose Class, ClassLoader, or Module?

### Choose Class When the Resource "Accompanies the Class" and Belongs to the Class's Module

For example: private schemas, internal templates, default configs, or migration texts that only the owning application/module knows how to interpret.

```java
try (InputStream in =
        MyComponent.class.getResourceAsStream("default.yaml")) {
    // ...
}
```

This is a non-standalone illustrative snippet. Benefits: simple relative naming, tied to the class/module, avoiding loader context mistakes. You should place resource-reading code inside the module that owns the resource if it is encapsulated.

### Choose Module When the Target Module Is Known and Lookup by Module Name/Identity Is Needed

For example, a framework holds a `Module` instance after creating a `ModuleLayer`:

```java
Module pluginModule = layer.findModule("demo.assets")
        .orElseThrow();

try (InputStream in =
        pluginModule.getResourceAsStream(
                "demo/assets/internal/secret.txt")) {
    // ...
}
```

This is an illustrative snippet requiring a valid `layer` variable of type `ModuleLayer`. **Holding a reference to a `Module` does not automatically grant permission to read private resources**: the caller must still have the package opened appropriately, or the resource must not be encapsulated.

### Choose ClassLoader When Looking Up Resources in a Loader Namespace or Aggregating Multiple Sources

Example:

```java
ClassLoader loader = Thread.currentThread()
        .getContextClassLoader();
if (loader != null) {
    URL url = loader.getResource(
            "META-INF/services/demo.spi.Provider");
}
```

This is an illustrative snippet and does not guarantee that the provider exists. Resources under `META-INF/services/...` typically lie outside regular Java packages; APIs such as `ServiceLoader` have their own discovery rules in named modules via `provides ... with ...`, rather than only reading descriptors from the classpath.

ClassLoader is suitable for looking up resources from the classpath/unnamed modules, plugin loaders, or framework-managed aggregation — but **should not be used to "break into" private named-module packages**.

## 9. "Resource Exists but Is null" — Systematic Diagnosis

When `getResource` or `getResourceAsStream` returns `null`, check in order:

1. **Is the name right?** `Class.getResource("file.txt")` is package-relative; `ClassLoader.getResource("pkg/file.txt")` uses a path from the root without a leading `/`; `Module.getResourceAsStream` uses a root path (and can strip a leading `/`).
2. **Is the resource in the output?** Having the file in the source project does not mean the compiler/build tool copied it into `mods` or the JAR.
3. **Which module is the class in?** Check `clazz.getModule().getName()`, `isNamed()`; classpath/unnamed and module path/named follow different rules.
4. **Which API is being called?** `Class`, `ClassLoader`, and `Module` each have their own access rules.
5. **Which module does the caller belong to?** `Module.getResourceAsStream` and `Class.getResourceAsStream` check whether the package is open to the caller; the same module behaves differently from an external one.
6. **Which package does the resource path belong to?** For `demo/assets/internal/secret.txt`, it derives `demo.assets.internal`; check whether that package actually belongs to the module.
7. **`exports` or `opens`?** `exports` on a public API is not enough. `opens ... to ...` may be enough for a specific caller, but is not enough for `ClassLoader.getResource`.
8. **Is it a `.class` resource?** The `.class` exception in the rules should be considered, though it still depends on resource availability.
9. **Is it the right class loader?** Parent delegation, TCCL, and custom child loaders can change the source/set of resources.
10. **Is there an IOException or inability to construct a URL?** `null` can also come from the loader/resource provider mechanism; do not assume encapsulation is always the sole cause.
11. **Is the module unresolved?** The module path may contain the module, yet the runtime does not resolve it unless configured with an appropriate root/add-module.
12. **Have you tested from within the module itself?** If the module's own code can read it while the external app cannot, inspect module access rather than copying the resource onto the classpath and masking the root cause.

A diagnostic snippet in code where a `Class<?> type` object is available:

```java
Module owner = type.getModule();
System.out.println("type=" + type.getName());
System.out.println("module=" + owner.getName());
System.out.println("named=" + owner.isNamed());
System.out.println("loader=" + type.getClassLoader());
System.out.println("opens to caller="
        + owner.isOpen(type.getPackageName(),
                Diagnostic.class.getModule()));
```

This is an **illustrative snippet**, requiring the `Diagnostic` class and an existing `type` variable. The value of `isOpen(..., callerModule)` is an indicator of package access and does not replace verifying that the resource name actually exists or checking the `ClassLoader` rule regarding unconditional opens.

## 10. Resources Packaged in a JAR/Module Image Are Not Necessarily a File

`Class.getResource` can return URLs such as:

```text
file:/opt/app/classes/demo/assets/config.txt
jar:file:/opt/app/lib/demo.jar!/demo/assets/config.txt
jrt:/java.base/java/lang/String.class
```

`file:` typically corresponds to a resource on the filesystem. `jar:` represents an entry inside a JAR; `jrt:` represents a resource inside the JDK runtime image.

**Do not write**:

```java
File f = new File(type.getResource("config.txt").toURI());
```

as a solution for every resource. `File(URI)` requires a suitable `file:` URI. For `jar:`/`jrt:`, converting directly does not correspond to a local filesystem file and can throw an exception.

When the goal is **reading bytes**, prefer:

```java
try (InputStream in =
        type.getResourceAsStream("config.txt")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource absent or inaccessible");
    }
    byte[] bytes = in.readAllBytes();
}
```

This is a snippet inside a method that handles `IOException`. For large resources, use streaming/buffering and memory bounds instead of reading everything at once.

**Important:** Streams keep code independent of storage location **after resource lookup is permitted**; using a stream **does not bypass module encapsulation**.

## 11. How Do Unnamed Modules and the Classpath Differ from Named Modules?

Placing classes/resources on the classpath typically looks like:

```text
java -cp out/app demo.Main
```

Classes on the classpath belong to the **unnamed module** of their respective loader. The special rules for encapsulated **named-module packages** do not apply in the same way to resources that live only in a regular unnamed module/classpath.

However, when moving the same project to:

```text
java --module-path mods -m demo.assets/demo.assets.api.Main
```

and declaring `module-info.java`, resource packages can become encapsulated under JPMS. Therefore, testing that "it works in the IDE/on the classpath" **is not enough** to prove that a module-path deployment works correctly.

**Safe migration approach:**

- Keep internal assets read by code in the same module using `Class.getResourceAsStream` or `Module.getResourceAsStream`.
- If code in module B needs to read a resource from A, design a **public data API** in module A before opening the package.
- If external module lookup is strictly required, use `opens pkg to consumer.module` with the minimal appropriate scope.
- Only use unconditional `opens pkg;` if policy allows the resource to be exposed more broadly and reflection exposure has been reviewed.
- Do not arbitrarily add all resources to another JAR/classpath to "work around" encapsulation, as doing so creates duplicate sources and deployment coupling.

## 12. ModuleLayer and Resource Lookup When Plugins Have Multiple Layers

For frameworks that build their own module layers, **module identity and loader mapping** are distinct dimensions:

```text
Boot layer
   ├── java.base
   └── ...
Plugin layer
   ├── plugin.a
   └── plugin.b
        |
        └── may be attached to its own loader or a shared loader
```

If the framework has a `ModuleLayer` instance and a module name:

```java
Module module = pluginLayer.findModule("plugin.a")
        .orElseThrow();
InputStream in = module.getResourceAsStream(
        "plugin/a/config/defaults.json");
```

This is an illustrative snippet: `pluginLayer` is created elsewhere; you still need to handle `IOException`/`null` and close the stream. The `Module` API lets you select the exact module **even when multiple modules share a class loader**.

When multiple modules on the same loader provide the same resource name, `ClassLoader.getResources` may return them in an **unspecified order**; you should not design plugin configs to "take the first resource" and assume it is the right version/tenant. Use explicit module lookup or a clear source policy instead.

### TCCL Does Not Automatically Open Packages

`Thread.currentThread().setContextClassLoader(pluginLoader)` affects APIs that actively read the TCCL (for example, certain service discovery mechanisms), but **does not cause a named module's package to automatically have `opens`**. Even when the TCCL points to the right loader, `ClassLoader.getResource` is still bound by the unconditional opens rule for non-`.class` resources of a named module.

## 13. META-INF/services, Module Services, and File Resources

`META-INF/services/<service-binary-name>` is the resource convention used for **classpath-based service provider declarations**, whereas named modules can register services using `module-info.java`:

```java
module plugin.provider {
    requires plugin.api;
    provides plugin.api.Service
        with plugin.impl.ServiceImpl;
}
```

This is an illustrative module declaration requiring a `plugin.api` module and a valid implementation. `ServiceLoader` understands **provider declarations in named modules**, so you do not need to manually read every `META-INF/services` file in all cases.

Key points:

- `ServiceLoader.load(Service.class)` uses the **thread context class loader** per the Java SE 17 API (along with module-specific discovery rules).
- `ServiceLoader.load(layer, Service.class)` uses the specified **module layer**.
- `ClassLoader.getResource("META-INF/services/...")` is just a form of resource access; **it does not replace** the full `ServiceLoader` contract.
- For custom loaders, `getResources` must properly support aggregation so provider-configuration files from multiple JARs are not accidentally missed.
- A qualified `opens` to a consumer module is not a mechanism for "exporting" all of a module's configs via ClassLoader.

## 14. Common Mistakes to Avoid

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| Calling `ClassLoader.getResource("/p/config.txt")` | The Loader API takes a name from the root **without a leading `/`** | `getResource("p/config.txt")` |
| Assuming `Class.getResource("config.txt")` always searches from the root | A name without a leading `/` is **package-relative** | Use `"/p/config.txt"` if you want the root |
| Assuming `exports p;` lets ClassLoader find `p/config.txt` | Exports public types, not an unconditional open | Use `Class`/`Module` internally or an intentional `opens` |
| Using qualified `opens p to x;` and expecting ClassLoader to see it | ClassLoader requires **unconditional opens** for non-`.class` resources | Use a module-aware API from an opened caller |
| Setting the TCCL to the plugin loader and assuming JPMS opens change automatically | TCCL and module encapsulation are two separate mechanisms | Choose the right API/module policy |
| Concluding the file is not packaged because the resource returns `null` | The package might not be open, or it could be the wrong module, wrong name, or unresolved module | Check both resource existence and access |
| Slicing a `jar:...!/path` URL string to construct a `File` | A JAR entry is not a standalone local file | Read as a stream, or use ZIP FS when truly needed |
| Using `ClassLoader.getResources` and relying on module order | Ordering among resources from multiple modules on the same loader may be unspecified | Select the target module explicitly |
| Reading `META-INF/services` manually and assuming it equals ServiceLoader | ServiceLoader also understands named module providers | Use the `ServiceLoader` API |
| Opening all packages unconditionally just to "make it run" | Broadens exposure, affecting reflection/resource access | Open only the needed package/caller or provide an API |
| Forgetting to close `InputStream` | Leaks handles and causes memory/resource pressure | Use `try-with-resources` |
| Testing only the classpath without testing the module path | Named module resources have different encapsulation | Test the actual deployment layout as well |

## 15. Implementation Checklist for Modular Applications

1. Identify **which module owns the resource** and whether the file is copied into the module output/JAR.
2. Choose `Class`/`Module` if the asset belongs to a module; use the loader namespace only when requirements fit.
3. Identify the **caller module** performing the lookup, avoiding guesswork from ClassLoader.
4. Compare the resource's package path against `Module.getPackages()` when diagnosing issues.
5. If the resource is non-`.class` in a real package of a named module, check **opens**:
   - code in the same module: module-aware lookup can read it;
   - another caller module: requires opens to that caller;
   - ClassLoader lookup: requires unconditional opens.
6. Handle `null` as missing or inaccessible; do not dereference immediately.
7. Handle `IOException` and use streams for JAR/JRT resources.
8. Do not arbitrarily swap classpath/module path/loaders across application parts without testing.
9. When multiple modules/layers exist, prefer explicit module identification instead of relying on `getResources` ordering.
10. Verify on the actual Java runtime/module-path, not only in the IDE.
11. Do not add `opens` broader than necessary, and remember to consider reflective access exposure.
12. Keep the resource schema and version compatible with the code in the module that owns it.

## 16. Self-Check Questions

**1. Where does `Class.getResource("a.txt")` look when the class belongs to `demo.internal`?** Relative to the package: `demo/internal/a.txt`.

**2. Does `ClassLoader.getResource("demo/internal/a.txt")` need a leading `/`?** No. This is a name from the loader's root namespace.

**3. In a named module that does not open the `demo.internal` package, can code inside that same module read `a.txt` using `Module.getResourceAsStream`?** Yes, it can read it if the resource exists and lookup conditions are met; the caller is the module itself, so it satisfies the access rule.

**4. Does code inside the module calling `ClassLoader.getResourceAsStream` automatically get permission to read that same resource?** No. The ClassLoader API still requires the package to be opened **unconditionally** if it is a non-`.class` resource located in a package of a named module.

**5. Is `exports demo.internal;` equivalent to `opens demo.internal;`?** No. `exports` grants public API access; `opens` governs reflective access and package-resource access according to the applicable rules.

**6. Does `--add-opens demo.assets/demo.assets.internal=ALL-UNNAMED` allow ClassLoader.getResource to read it?** Not from this qualified opens alone. It allows unnamed callers to read via module-aware APIs; ClassLoader still requires unconditional opens.

**7. Is the resource `demo/internal/Inside.class` subject to the same restriction as `demo/internal/secret.txt`?** No. A resource name ending in `.class` is an exception to the resource encapsulation rule; the lookup may still fail to find it for other reasons.

**8. Does the resource `META-INF/demo.info` require opening the `META-INF` package?** Not under the package encapsulation rule, because `META-INF` is not a valid Java package name.

**9. Are Module and ClassLoader the same object?** No. A Module represents a namespace and metadata in JPMS; a loader defines classes and can be associated with multiple modules.

**10. If `Module.getResourceAsStream` returns `null` from another module, is unconditional `opens` always the best fix?** No. Prefer a public API that reads the resource inside the module, or a qualified opens scoped as needed if direct access is truly required.

## 17. Official References

- **Java SE 17 API — `Class`**, `getResource(String)` and `getResourceAsStream(String)`, name handling and named-module lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API — `ClassLoader`**, `getResource`, `getResources`, `getResourceAsStream`, `findResource(moduleName,name)`, unconditional opens: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `Module`**, `getResourceAsStream(String)`, module source, caller module, and package-opening rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- **Java SE 17 — `java` command**, `--module-path`, `--add-modules`, `--add-opens`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JLS `7.7 — Module Declarations**, `exports`, `opens` and `open module`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7
- **Java SE 17 API — `ModuleLayer`**, finding a module in a layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html

**Takeaway:** **`Class` and `Module` know which module a resource belongs to and evaluate package-opening permissions based on the caller; `ClassLoader` searches within the loader namespace and requires a named module's package to be opened unconditionally for non-`.class` resources.** If a resource is internal, read it inside the module and expose a data API externally; do not open every package just to make a single resource lookup work.
