# Communicating via Interfaces, DTOs, and Exceptions with Unified Identity in Plugin Architecture

## 1. The Core Problem: Plugins Run Independently but Must Understand the Same Contract

A plugin architecture typically has a **host application** and multiple **plugin class loaders**. The host wants to invoke a plugin without knowing its concrete implementation in advance; a plugin wants to use its own libraries, potentially at different versions from another plugin. This introduces two seemingly conflicting requirements:

- **Isolation:** plugin A's implementation classes and private dependencies do not mix with the corresponding classes of plugin B.
- **Interoperability:** the host and all plugins must uniformly understand the types crossing the API boundary: interfaces, data-transfer objects (DTOs), exceptions, and types nested in signatures.

In the JVM, a runtime type is not identified solely by a name such as `api.Request`. **A runtime class/interface identity is the pair (binary name, defining class loader)**. If the host uses `api.Request` defined by loader H, while a plugin uses a copy of `api.Request` defined by loader P, they are **two different types**, even if the source/bytecode and package name are identical.

**Design principle: share contract types, isolate implementation types.**

```text
            Host / Shared API loader (H)
            ├── api.Plugin              [H]
            ├── api.Request             [H]
            ├── api.Result              [H]
            └── api.PluginFailure       [H]
                     |
          +----------+-----------+
          |                      |
   Plugin loader A (A)     Plugin loader B (B)
   ├── plugin.Worker [A]   ├── plugin.Worker [B]
   └── impl.Formatter [A]  └── impl.Formatter [B]

   plugin.Worker [A] != plugin.Worker [B]
   api.Request seen from A == api.Request seen from H
   api.Request seen from B == api.Request seen from H
```

In this model, the host receives an object implementing the right interface, exchanges DTOs with the same runtime identity, and catches checked exceptions of the right type. Plugins still retain the right to use their own `impl.Formatter`.

This lesson explains **why**, **loader graph design**, **how to define the API**, **a runnable multi-file Java 17 example**, **common pitfalls**, and **testing identity/binary compatibility**.

## 2. Distinguishing Binary Name, Defining Loader, and Initiating Loader

A Java class such as:

```java
package api;
public record Request(String text) {}
```

has the **binary name** `api.Request`. If the class is defined by loader H, its runtime identity is `("api.Request", H)`.

If loader A does not define `api.Request` itself and instead delegates to H, `loaderA.loadClass("api.Request")` can return the same `Class<?>` object as `Request.class` in the host.

If loader A uses child-first and defines its own copy of `api.Request`, two classes can exist at runtime:

```text
("api.Request", H) != ("api.Request", A)
```

These two types cannot be "merged" merely by casting, renaming loaders, giving them the same source code, or copying the same JAR. Java runtime type identity is tied to the **defining loader**, not to the file path or bytecode hash.

Distinctions:

| Term | Meaning |
|---|---|
| **Binary name** | `api.Request`, `api.Plugin`, `plugin.Worker` |
| **Defining loader** | The loader that actually defines the runtime class; `clazz.getClassLoader()` returns this information for ordinary classes |
| **Initiating loader** | The loader recorded by the JVM as having initiated loading/resolving the class, which may receive a class defined by a parent |
| **Parent loader** | The loader queried first by a child loader in the default `loadClass` |
| **Runtime type identity** | Binary name combined with the defining loader |
| **Loading constraint** | A JVM rule requiring that the same type name in certain signatures linked across loaders must resolve to the **same runtime class** |

Two class loader objects can have the same `getName()` and still be different. Loader names are only for diagnostics. When checking true identity, compare `Class<?>` with `==` or inspect the defining loader object.

### Class<?> Differs from Class Name

`clazzA.getName().equals(clazzB.getName())` can be `true` while `clazzA == clazzB` is `false`. In a plugin architecture, checking the name alone is not enough to prove that the host and plugin share the same API.

When you need to check:

```java
System.out.println(hostType == pluginViewType);
System.out.println(hostType.getClassLoader()
        == pluginViewType.getClassLoader());
```

This is an **illustrative snippet** requiring two actual `Class<?>` variables. Comparing defining loaders is one signal, while comparing `Class<?>` with `==` directly confirms the same runtime class.

## 3. Communication Signatures Must Be Designed in the Shared Loader

Suppose the host publishes:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

This is the ideal contract to be defined by **one** shared loader. The host and plugins must agree on:

1. `api.Plugin` — the interface so the host can cast the implementation and call the method.
2. `api.Request` — the parameter data type passed in by the host.
3. `api.Result` — the return type sent back by the plugin.
4. `api.PluginFailure` — the exception the host wants to catch by concrete class.

If each plugin bundles its own copy of the API and defines it in its own loader, problems can appear at multiple stages:

- The plugin implementation may no longer be `instanceof Plugin` with respect to the host's `Plugin.class`.
- Casting from the implementation to the host's `api.Plugin` may throw `ClassCastException`.
- The JVM may throw `LinkageError` due to a **loading constraint violation** when linking method/field descriptors that are required to use the same runtime reference type.
- A host's `catch (PluginFailure e)` cannot catch an exception class with the same binary name but defined by another loader if it is not a subtype of the exact runtime `PluginFailure` known to the host.
- DTO copies in two loaders cannot be exchanged directly as the same Java type; serialization/deserialization may also pick the wrong loader when reconstructing objects.

**Having two classes with the same name in two loaders is not always a bug.** Separating two copies of `impl.Formatter` or `plugin.Worker` can be completely right. Risk arises when runtime types that **must be shared** according to the contract are defined redundantly.

## 4. Choosing Which Types Are Allowed Across the Boundary

Design guideline table:

| Data type | Recommended policy | Reason |
|---|---|---|
| `api.Plugin` or shared SPI | Single definition in the shared API loader | Host and plugin have the same interface identity |
| `api.Request` / `api.Result` | Shared API loader | Exchanged DTOs do not differ in runtime type |
| `api.PluginFailure` and contract exceptions | Shared API loader | Host catches the exact exception type; compiler/VM understand a unified signature |
| `java.lang.String`, primitives, Java core types | Appropriate JVM built-in loader | Foundational types are shared |
| `impl.Formatter`, plugin-internal services | Separate plugin loader | Can retain different versions/configurations |
| Version-dependent types such as `thirdparty.Parser` | Separate plugin loader if not exposed in the public API | Allows multiple versions to coexist |
| `List<Request>` / `Map<String, Result>` | `List`/`Map` from the JDK, while `Request`/`Result` are from the shared API | Generics do not eliminate the identity requirement of element types |
| Plugin-specific exception handled only internally | Plugin loader, caught/translated into shared `PluginFailure` at the boundary | Host does not need to import private error types |
| DTO serialization schema or JSON | Shared schema/adapter with an explicit version contract | Avoids passing private objects; serialization still requires compatibility tests |

A good API is typically **small, stable, and free of plugin-private dependencies** in its public signatures.

### Record DTOs in Java 17

`record` is suitable for simple immutable data:

```java
package api;

public record Request(String text) {}
```

This is a **separate file `Request.java`**. A record generates the `text()` accessor, canonical constructor, and component-based equality/hashCode. However, **records do not solve classloader identity**: if two loaders define two separate copies of `api.Request`, they are still two different runtime classes.

If a DTO contains fields whose types are plugin classes, such as `privateparser.Node ast`, then even a shared DTO class carries an unstable dependency across the boundary. Use shared interfaces/records or convert to intermediate data with a well-defined schema.

### Checked Exceptions Are Also a Runtime Type

`throws PluginFailure` is part of the Java source method contract and is used by the compiler to enforce checked exception handling; the JVM method descriptor *does not contain* the `throws` list. An exception class still has a runtime identity and must resolve properly when thrown/caught.

Therefore, you **should not** place a copy of `api.PluginFailure` in the plugin loader and expect the host's `catch (api.PluginFailure)` to recognize it by name. A plugin's exception class may be a subtype of a shared base type, but the host must catch the **exact shared base class** if it wants a stable contract.

## 5. Parent Delegation Unifies the Shared API

A simple loader diagram:

```text
          App/Shared API loader H
          ├── api.Plugin
          ├── api.Request
          ├── api.Result
          └── api.PluginFailure
                    ^
                    |
          +---------+----------+
          |                    |
      Loader A             Loader B
      plugin.*             plugin.*
      impl.*               impl.*
```

Each plugin loader uses `H` as its parent. The default `ClassLoader.loadClass` typically checks whether the class is already loaded, queries the parent, and only then invokes `findClass`/reads its own bytes when the parent does not have the class.

For `api.*`, H returns the shared class. For `plugin.*` and `impl.*`, H does not have them, so A/B define them independently. Thus **parent-first is sufficient to both share the API and isolate implementations**, provided the parent's classpath does not contain plugin implementation classes.

Points to note:

- The parent is **not** the Java superclass of the class loader object.
- Having the same parent **does not guarantee** that every child-first custom loader shares the API; if `loadClass` is overridden to define `api.*` on its own, types can still be duplicated.
- `parent == null` in the default loader points to the bootstrap loader and **does not automatically see** the application loader's API; choosing a null parent for a plugin that needs a shared API typically requires a custom lookup mechanism.
- In an application server or a JPMS multi-layer setup, `ClassLoader.getSystemClassLoader()` is not necessarily the loader that owns the shared API. You should select the loader of the shared interface itself, such as `Plugin.class.getClassLoader()`, when appropriate.
- If the shared interface is defined by the bootstrap loader, `getClassLoader()` can be `null`; you must read the API contract of the loader/factory accepting the parent to understand this special case.

### Do Not Isolate the API with Child-First

If child-first is needed to load a separate `thirdparty.*`, apply **selective child-first** for designated packages. The `api.*` packages shared by the host and plugins must prioritize the parent.

Architectural pattern:

```text
loadClass(name):
    if name startsWith "api.":
        use parent-first
    else if name startsWith "thirdparty.":
        try own classes first
        fallback according to explicit policy
    else:
        default parent-first or plugin policy
```

This is **pseudocode**, not a complete Java implementation. A real `loadClass` override must use `findLoadedClass`, `getClassLoadingLock(name)`, and handle `resolveClass`/errors properly. Do not catch every `LinkageError` and fall back to another copy of the API as if it were a class-not-found error.

## 6. Complete Java 17 Demo: Shared Interface, DTO, and Checked Exception

The demo has **two plugins** loaded via **two different `URLClassLoader` instances**. Each plugin defines its own classes with the same binary names `plugin.Worker` and `impl.Formatter`, while both delegate `api.*` to the application loader.

Results to observe:

1. The host can cast both objects to `api.Plugin`.
2. Plugins A/B receive the same `Request` type and return the same `Result` type as the host.
3. The host catches the exact `api.PluginFailure` thrown by a plugin.
4. The two implementation classes have different identities, and their private helpers also have different identities.
5. Both plugin class loaders return the same `Class<?>` for the shared API types.

### 6.1. Project Structure

Create the directory tree:

```text
src/
  api/
    Plugin.java
    Request.java
    Result.java
    PluginFailure.java
  plugin-a/
    impl/
      Formatter.java
    plugin/
      Worker.java
  plugin-b/
    impl/
      Formatter.java
    plugin/
      Worker.java
  host/
    PluginHost.java
out/
  api/
  plugin-a/
  plugin-b/
  host/
```

The `out` directory will be created by the compilation commands; do not mix the source/output of plugins A and B on the same classpath when building the host.

### 6.2. Shared API — Compile Only One Copy

File `src/api/Plugin.java`:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

File `src/api/Request.java`:

```java
package api;

public record Request(String text) {}
```

File `src/api/Result.java`:

```java
package api;

public record Result(String message) {}
```

File `src/api/PluginFailure.java`:

```java
package api;

public class PluginFailure extends Exception {
    public PluginFailure(String message) {
        super(message);
    }
}
```

These files are **four independent source files**. `Request`/`Result` are Java 17 records, and `PluginFailure` is a checked exception because it extends `Exception`. All of them must be defined once by the shared loader H.

### 6.3. Plugin A — Private Formatter Version A

File `src/plugin-a/impl/Formatter.java`:

```java
package impl;

public final class Formatter {
    public String format(String input) {
        return "A:" + input;
    }
}
```

File `src/plugin-a/plugin/Worker.java`:

```java
package plugin;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import impl.Formatter;

public final class Worker implements Plugin {
    @Override
    public Result handle(Request request) throws PluginFailure {
        if (request.text().isBlank()) {
            throw new PluginFailure("blank");
        }
        return new Result(new Formatter().format(request.text()));
    }
}
```

`Formatter` is an implementation detail. Do not place the `impl.Formatter` type in the `api.Plugin.handle` signature.

### 6.4. Plugin B — Same Binary Names, Different Behavior

File `src/plugin-b/impl/Formatter.java`:

```java
package impl;

public final class Formatter {
    public String format(String input) {
        return "B:" + input;
    }
}
```

File `src/plugin-b/plugin/Worker.java`:

```java
package plugin;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import impl.Formatter;

public final class Worker implements Plugin {
    @Override
    public Result handle(Request request) throws PluginFailure {
        if (request.text().isBlank()) {
            throw new PluginFailure("blank");
        }
        return new Result(new Formatter().format(request.text()));
    }
}
```

Plugins A/B have the same binary name for `plugin.Worker` and `impl.Formatter`; however, the class bytes of `Formatter` are stored in separate output directories. Each plugin loader will define an independent runtime copy.

### 6.5. Host — Loading and Invoking Plugins Using Shared Types

File `src/host/PluginHost.java`:

```java
package host;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    private static URL url(String directory) throws Exception {
        return Path.of(directory).toUri().toURL();
    }

    private static Plugin create(URLClassLoader loader)
            throws Exception {
        Class<?> implementation =
                Class.forName("plugin.Worker", true, loader);
        Object instance =
                implementation.getDeclaredConstructor().newInstance();
        return (Plugin) instance;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader apiLoader = Plugin.class.getClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                     "plugin-A",
                     new URL[] { url("out/plugin-a") },
                     apiLoader);
             URLClassLoader loaderB = new URLClassLoader(
                     "plugin-B",
                     new URL[] { url("out/plugin-b") },
                     apiLoader)) {

            Plugin pluginA = create(loaderA);
            Plugin pluginB = create(loaderB);

            Request request = new Request("hello");
            Result answerA = pluginA.handle(request);
            Result answerB = pluginB.handle(request);

            System.out.println("A result: " + answerA.message());
            System.out.println("B result: " + answerB.message());

            Class<?> workerA = pluginA.getClass();
            Class<?> workerB = pluginB.getClass();
            Class<?> formatterA = loaderA.loadClass("impl.Formatter");
            Class<?> formatterB = loaderB.loadClass("impl.Formatter");

            System.out.println("Worker identity differs: "
                    + (workerA != workerB));
            System.out.println("Formatter identity differs: "
                    + (formatterA != formatterB));

            System.out.println("Both implement shared Plugin: "
                    + (pluginA instanceof Plugin
                    && pluginB instanceof Plugin));

            boolean sharedApi =
                    loaderA.loadClass("api.Plugin") == Plugin.class
                    && loaderB.loadClass("api.Plugin") == Plugin.class
                    && loaderA.loadClass("api.Request") == Request.class
                    && loaderB.loadClass("api.Request") == Request.class
                    && loaderA.loadClass("api.Result") == Result.class
                    && loaderB.loadClass("api.Result") == Result.class
                    && loaderA.loadClass("api.PluginFailure")
                            == PluginFailure.class
                    && loaderB.loadClass("api.PluginFailure")
                            == PluginFailure.class;

            System.out.println("All shared API identities match: "
                    + sharedApi);

            System.out.println("Request defining loader shared: "
                    + (Request.class.getClassLoader() == apiLoader));

            try {
                pluginA.handle(new Request(""));
            } catch (PluginFailure expected) {
                System.out.println("Caught from A: "
                        + expected.getMessage());
                System.out.println("A failure class shared: "
                        + (expected.getClass() == PluginFailure.class));
            }

            try {
                pluginB.handle(new Request(""));
            } catch (PluginFailure expected) {
                System.out.println("B failure class shared: "
                        + (expected.getClass() == PluginFailure.class));
            }
        }
    }
}
```

`URLClassLoader(String name, URL[] urls, ClassLoader parent)` has existed since Java 9, so it is valid on Java 17. Loaders A/B use the **same** `apiLoader` as their parent; each loader has its own URLs.

Notes:

- `Class.forName("plugin.Worker", true, loader)` requests lookup via the selected plugin loader and initialization per the API.
- `getDeclaredConstructor().newInstance()` creates the implementation object via the public implicit no-arg constructor.
- The `(Plugin) instance` cast is valid because `api.Plugin` is always defined by the parent.
- The `Result` created by `plugin.Worker` is the exact `api.Result` shared type, so the host calls `message()` without intermediate reflection/serialization.
- The `PluginFailure` thrown by the implementation is the exact host exception class. `catch (PluginFailure)` catches it from both plugins.
- `getClass().getClassLoader()` of the implementation is the plugin loader, whereas `Request.class.getClassLoader()` is the shared loader.
- `try-with-resources` closes both `URLClassLoader` instances after use; closing a loader **does not immediately unload** classes or destroy objects that still have live references.

### 6.6. Compile and Run

With Bash on Linux/macOS, run in the directory containing `src`:

```bash
mkdir -p out/api out/plugin-a out/plugin-b out/host

javac -d out/api \
  src/api/Plugin.java \
  src/api/Request.java \
  src/api/Result.java \
  src/api/PluginFailure.java

javac -cp out/api -d out/plugin-a \
  src/plugin-a/impl/Formatter.java \
  src/plugin-a/plugin/Worker.java

javac -cp out/api -d out/plugin-b \
  src/plugin-b/impl/Formatter.java \
  src/plugin-b/plugin/Worker.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api:out/host" host.PluginHost
```

On Windows PowerShell (the classpath separator is `;`):

```powershell
New-Item -ItemType Directory -Force out/api,out/plugin-a,out/plugin-b,out/host

javac -d out/api src/api/Plugin.java src/api/Request.java src/api/Result.java src/api/PluginFailure.java

javac -cp out/api -d out/plugin-a src/plugin-a/impl/Formatter.java src/plugin-a/plugin/Worker.java

javac -cp out/api -d out/plugin-b src/plugin-b/impl/Formatter.java src/plugin-b/plugin/Worker.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api;out/host" host.PluginHost
```

**Never include `out/plugin-a` or `out/plugin-b` on the host's classpath when running the demo.** If the parent sees `plugin.Worker` or `impl.Formatter`, parent-first delegation may return the parent's class first, breaking isolation.

### 6.7. Expected Stdout on JDK 17+

With a clean structure and without changing the classpath described above:

```text
A result: A:hello
B result: B:hello
Worker identity differs: true
Formatter identity differs: true
Both implement shared Plugin: true
All shared API identities match: true
Request defining loader shared: true
Caught from A: blank
A failure class shared: true
B failure class shared: true
```

**Result analysis:**

1. `A:hello` and `B:hello` prove that the two plugins use separate `Formatter` classes.
2. `workerA != workerB` despite the same binary name `plugin.Worker` proves that class identity differs across defining loaders.
3. `formatterA != formatterB` confirms that private dependencies with the same name are also isolated.
4. Both are `instanceof Plugin` because the `api.Plugin` interface is defined by **one** parent loader.
5. `sharedApi` compares the **four shared classes** from the perspective of both loaders; a true result proves unified contract identity in the demo.
6. `Request.class.getClassLoader() == apiLoader` indicates that the defining loader of the DTO in the host is the shared loader.
7. Both `catch (PluginFailure)` statements from A and B succeed; the exception class is the host's exact `PluginFailure.class`, not an exception copy with the same name.

**Demo limitations:** the project runs on a traditional classpath; in named modules or when using `ModuleLayer`, you must also account for `requires`, `exports`, `opens`, and the module-to-loader mapper. Sharing the same loader does not automatically bypass access rules.

## 7. What Happens If a Plugin Re-Packages the API?

There are two distinct scenarios.

### Scenario A: The Plugin JAR Contains a Copy of the API, but the Loader Remains Parent-First

If the plugin artifact includes `api.*` classes, yet the parent loader has already defined `api.Plugin`, `api.Request`, `api.Result`, and `api.PluginFailure`, the default `loadClass` algorithm typically returns the class from the parent first. The copy on the child classpath **may never be defined** in that lookup path.

However, redundantly packaging the API remains a dependency management risk: a delegation change, a misconfigured parent, or a child-first plugin loader can turn that copy into a different runtime class.

**Better practice:** build the plugin with the API dependency as **compile-only/provided**; package private implementation dependencies, but do not re-bundle the shared API into the plugin runtime artifact when unnecessary.

### Scenario B: A Child-First Plugin Defines the API Itself

Suppose a plugin has its own copy of `api.Plugin` defined by loader P:

```text
api.Plugin [H] != api.Plugin [P]
```

The `plugin.Worker` class in P implements `api.Plugin [P]`. The host holds `api.Plugin [H]` and wants to:

```java
api.Plugin plugin = (api.Plugin) implementation;
```

This is an illustrative snippet referencing pre-existing variables/classes. If `implementation` only implements P's version of the interface, the cast does not satisfy runtime assignability with H and may throw `ClassCastException`.

Even when methods have the same names and identical descriptor strings, the JVM **does not infer the same runtime interface type**.

If method overriding or cross-loader resolution requires type names such as `api.Request` or `api.Result` to agree, yet the two loaders resolve them differently, the JVM may reject linking with a `LinkageError` due to a **loader constraint violation**.

**Not every case waits until the cast.** For certain method/interface or field linkages, the error can occur right during loading/linking. Do not hardcode the exception timing across all JVMs.

## 8. Loading Constraints Protect Signature Consistency

In the JVM, class/interface identity is determined by the binary name and defining loader. When classes from two loaders participate in certain linking relationships, the JVM imposes **loading constraints**.

Consider:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

The JVM method descriptor (excluding `throws`) is:

```text
(Lapi/Request;)Lapi/Result;
```

If class `plugin.Worker` defined by loader P implements `api.Plugin` defined by loader H, the JVM must maintain consistency of the reference types in the descriptor in accordance with linking/preparation rules, such as:

```text
api.Request^P = api.Request^H
api.Result^P  = api.Result^H
```

This is conceptual notation for the requirement to resolve to the same runtime class, not a Java expression. Using parent delegation for `api.*` causes P and H to see the same runtime class and satisfy the constraint.

**Important note on exceptions:** `throws PluginFailure` is represented in the `Exceptions` attribute of method/class metadata, **not in the method descriptor**. Therefore, **do not claim that the JVM imposes a loading constraint on `api.PluginFailure` solely because it appears in `throws`**. Nevertheless, if the host needs to catch the exact exception type, the identity of `PluginFailure` must still be unified via the shared loader. Other symbolic references to the exception type may also have their own linking rules.

### Generics Do Not Rescue Runtime Identity

Example:

```java
List<Request> handleAll(List<Request> requests);
```

The code above is a method declaration snippet requiring `import java.util.List`. In bytecode, generic type arguments undergo erasure; the regular descriptor is:

```text
(Ljava/util/List;)Ljava/util/List;
```

`Request` may reside in the generic `Signature` metadata rather than directly in the descriptor here. That **does not make two `Request` classes in two defining loaders the same type**. When accessing elements, the compiler may insert a `checkcast` against the expected runtime class; a DTO copy from another loader can cause a `ClassCastException`.

Do not treat generic type parameters as a safe channel for passing objects between two separate loader spaces.

## 9. Exception Identity and Plugin Error-Handling Strategy

### 9.1. Sharing the Exception Contract

The host often needs to catch and handle domain errors:

```java
try {
    Result result = plugin.handle(request);
} catch (PluginFailure error) {
    // Log, return business result, retry according to policy.
}
```

The illustration requires `plugin` and `request` to have the right shared types. Catching the exact `PluginFailure` in the host works when the plugin throws the **exact runtime `api.PluginFailure`** or a valid subclass of it.

In the demo in section 6, both plugins A and B call:

```java
throw new PluginFailure("blank");
```

The name `PluginFailure` is imported from package `api`, and the parent loader provides the same class known to the host.

### 9.2. Private Exceptions Should Be Translated at the Boundary

A plugin may depend on a private library that throws `vendor.ParseException` or `impl.InternalFault`. The host should not have to import private exception classes owned by the plugin loader. An adapter at the plugin boundary:

```java
@Override
public Result handle(Request request) throws PluginFailure {
    try {
        return executeInternal(request);
    } catch (VendorParseException error) {
        throw new PluginFailure("Input format is invalid");
    }
}
```

This is **Java-like pseudocode**: to compile, it requires the `executeInternal` method and `VendorParseException` class to be declared, along with the shared `Result`/`Request`/`PluginFailure`. If preserving the cause is required, design the shared `PluginFailure` with a `(String, Throwable)` constructor, though note that the cause may carry a private exception object/class to the host.

A production policy typically includes:

- Categorizing errors using shared error codes or a small shared exception hierarchy.
- Not leaking implementation/private-library classes in public signatures.
- Retaining root-cause information in logs in accordance with data/privacy policies, avoiding exposing full stack traces or secrets to other plugins.
- Distinguishing checked business failures from fatal runtime failures; do not catch every `Throwable` and hide `OutOfMemoryError`/`ThreadDeath` as an ordinary business error.

### 9.3. Catching the Same Name in a Different Loader Is Not Equivalent

Suppose the host defines `api.PluginFailure [H]` and plugin P defines its own `api.PluginFailure [P]`. Both classes extend `Exception`, yet have **no inheritance relationship** with each other. The `catch (api.PluginFailure)` statement in the host only catches `Throwable` instances assignable to **host runtime class H**.

If the host needs to handle a private exception, you need a **shared supertype** or must translate it into a shared exception/DTO at the plugin adapter boundary; do not rely on `getName()`.

## 10. DTO Compatibility: Same Runtime Class Is Not Enough for API Evolution

Unifying the defining loader solves **runtime type identity**, but **does not automatically guarantee binary/source compatibility** between host and plugin versions.

For example, host API v2 changes the record:

```java
public record Request(String text, int timeout) {}
```

If a plugin was compiled against v1 `Request(String text)` while the runtime host only has v2, the matching constructor/signature/method invocation may change, causing `NoSuchMethodError` or another linkage error. Even though at runtime there is only **one** `api.Request` defined by H, the public ABI itself has changed incompatibly.

Design rules:

1. Version the shared API independently from the plugin implementation version.
2. Establish clear compatibility guidelines: changes to constructors, record components, interface methods, and exception contracts must be reviewed before release.
3. Consider factory methods, builders, or DTO envelopes with a version field if schema evolution is needed.
4. Test plugins compiled against older APIs running on newer hosts within the committed compatibility scope.
5. Avoid allowing `vendor.*` or `impl.*` to appear in public fields, method parameters/returns, exception contracts, and serialized forms.
6. If DTOs cross into another process/JVM, classloader identity is no longer the object-passing mechanism; a versioned serialization schema/protocol is required.

### Records Are Not Always the Best DTO

Records are great for immutable messages within the same JVM when the shared API is stable; however, changing a record component list typically alters the canonical constructor and certain contracts. For an API requiring long-term backward compatibility, an interface, a builder-based value object, or a versioned message schema may be more suitable.

You should not use Java `Serializable` as a default workaround to "cross class loaders": deserialization still requires loader selection, type checking, and serial compatibility; in particular, untrusted input must be safely managed.

## 11. ServiceLoader and the Provider's Loader

With classpath SPI, the provider JAR writes `META-INF/services/api.Plugin` containing the provider name such as `plugin.Worker`. The host uses `ServiceLoader.load(Plugin.class, pluginLoader)` to select the loader explicitly; the provider must be assignable to **the host's exact `Plugin.class`**. A duplicate SPI defined by a child can cause `ServiceConfigurationError: not a subtype`. The single-parameter overload uses the thread's TCCL; named modules use the `uses`/`provides` mechanism and `ServiceLoader.load(layer, service)`.

## 12. Multiple Class Loader Cases: Arrays, Generics, Resources, and Reflection

### Arrays of DTOs

`Request[]` is a reference array type. If `Request` is defined by loader H, the array class has defining-loader behavior tied to its component/element type according to the JVM. Plugins A/B sharing `Request` will share the corresponding runtime array class.

If plugin B defines its own copy of `Request`, its `Request[]` is also incompatible with the host's `Request[]` in the way the Java type system expects. You cannot rely on array covariance to make two component types from different loaders become the same type.

### Generics and Bridge Methods

`List<Result>` only preserves generic type information in Java source/reflection metadata to a certain extent, whereas the JVM verifier and casts operate on actual runtime types. For interface/generic methods bridged by the compiler, the classloader identity of the shared API must still be unified to ensure proper method dispatch/linking.

Do not infer from a generic `Signature` in a class file that two identically named DTOs across loaders are compatible.

### Resources and the Classpath

Class lookup differs from resource lookup:

```java
ClassLoader loader = plugin.getClass().getClassLoader();
java.net.URL resource = loader.getResource("plugin.properties");
```

The illustrative snippet requires the `plugin` variable. If a plugin uses a private configuration/resource, prioritize resource lookup via that specific **plugin loader**. If the resource is part of the host's contract, use the shared API anchor/classloader as designed.

Service configuration files in `META-INF/services` are also resources; parent delegation/resource lookup and duplicate descriptors must be tested.

### Reflection

`Class.forName("plugin.Worker", true, loaderA)` finds A's implementation, but object instantiation/casting still depends on constructor/accessibility and shared interface identity. If `getDeclaredConstructor().newInstance()` is used, method/constructor access checks and JPMS exports/opens may affect behavior when moving to named modules.

The single-parameter `Class.forName(String)` overload **does not automatically use the TCCL**; it uses the caller's loader. Therefore, plugin discovery via reflection should explicitly specify the loader to avoid finding the host's or another plugin's class.

## 13. ClassLoader Isolation and Its Limitations

Shared API identity does not mean a plugin's resources or access permissions are completely isolated. Static state of classes in the parent can be shared across plugins; instances/`Class<?>`/threads/TCCL/caches can keep an old loader reachable after redeployment. `URLClassLoader.close()` does not force unloading. Untrusted plugin code requires process/OS isolation, because a separate classloader does not forbid using JDK file/network APIs.

## 14. Diagnosing Issues at the Host–Plugin Boundary

### Error: ClassCastException Even Though the Class Implements an Interface with the Same Name

Check:

1. `hostPluginClass == loaderA.loadClass("api.Plugin")`?
2. Does `pluginObject.getClass().getInterfaces()` contain the exact runtime `Plugin.class`?
3. Did the plugin bundle `api.Plugin` itself and use child-first?
4. Are the class names the same while the defining loaders differ?

**Fix:** define the API only in the shared loader, and have plugins delegate the API package to the parent. Do not "cast through Object" to mask the error; the runtime type is still wrong.

### Error: LinkageError with a Loader Constraint Violation Message

Inspect field/method descriptors at the host/plugin boundary:

```bash
javap -classpath out/api -s -p api.Plugin
javap -classpath out/plugin-a -p plugin.Worker
```

In the demo example, `Plugin.handle` has the descriptor:

```text
(Lapi/Request;)Lapi/Result;
```

If the plugin resolver sees two copies of `api.Request`/`api.Result` from two defining loaders, the JVM may require unified identity due to method overriding/linking and report an error.

Fix this through the module/classloader architecture, not merely by renaming source files. With Java 17 HotSpot, you can use class loading logs to identify the source of a class:

```bash
java -Xlog:class+load=info -cp "out/api:out/host" host.PluginHost
```

Logs can be very long and their format is JVM-dependent. Combine this with `Class.getClassLoader()` to confirm the defining loader.

### Error: catch Fails to Catch the Plugin Exception

Possible causes:

- The plugin throws a private exception that is not a subtype of the shared `PluginFailure`.
- The plugin defines its own copy of `api.PluginFailure` in a different loader.
- The code catches the wrong exception family.

**Fix:** catch/translate the error at the adapter boundary into a shared exception (or shared error DTO) and inspect the runtime `Class<?>` of the exception.

### Error: NoSuchMethodError After Upgrading the Shared API

A plugin was compiled against an ABI different from the runtime host API; type identity may be shared, yet a method descriptor/constructor has changed. Check the API version/ABI; do not immediately conclude it is a classloader collision.

### Error: ServiceConfigurationError in SPI

The provider is not assignable to the shared service interface, lacks a public provider constructor, or has an incorrect `META-INF/services` configuration. Check both the loader used to locate the provider and the loader that defines the interface.

### Error: ClassNotFoundException for a Shared DTO

The parent loader cannot see the API class, a null-parent plugin loader has no path to find shared types, or the runtime is missing a JAR. Check build artifacts, classpath/module path, parent delegation, and binary names.

### Error: Works Locally, Fails in Application Server

Inside a container, `getSystemClassLoader()` is not necessarily the owner of the shared API; the TCCL may belong to another deployment/worker. Use the `Plugin.class.getClassLoader()` anchor or a factory/registry that supplies the right loader, and then also check module access if JPMS is used.

## 15. Design and Testing Checklist

Before releasing a plugin, verify:

1. **Clear API boundary:** all primary interfaces/DTOs/checked exceptions reside in the shared API artifact.
2. **Single defining loader for shared types:** the host and all plugins resolve `api.*` through the same loader.
3. **No unnecessary API bundling:** the plugin compiles against the shared API but does not define duplicate API classes itself.
4. **Separate private implementations:** plugin-specific code and versioned dependencies are owned by the plugin loader.
5. **No private type leakage:** public method parameters/returns, public fields, and exception contracts do not use plugin-private classes.
6. **Binary compatibility:** host API versions and plugin builds are verified; generic changes, record component changes, default methods, and constructors are evaluated.
7. **Exception contract:** the host catches the exact shared exception or a common base type; internally, the plugin has an error-translating adapter.
8. **SPI on the right loader:** plugin providers share the service interface identity and have valid service descriptors/module provider declarations.
9. **Concurrency:** a custom class loader overriding `loadClass` must avoid defining the same name twice; use an appropriate name-based locking mechanism.
10. **Lifecycle:** plugin shutdown hooks, thread locals, TCCL, listeners, caches, and URLs are cleaned up.
11. **Observability:** log the loader name and defining loader identity, module, and classpath roots, without logging secrets or sensitive object payloads.
12. **Cross-version testing:** run plugins A/B side by side together with DTO/exception handling to safeguard the shared boundary.

A strong integration test does not just assert that `a.handle(...)` returns the expected content; also assert:

```java
assert loaderA.loadClass("api.Plugin") == Plugin.class;
assert loaderB.loadClass("api.Request") == Request.class;
assert pluginA.getClass() != pluginB.getClass();
```

These are **assertion snippets**, not a standalone runnable class. Java `assert` is **disabled by default** unless run with `-ea`; in a test suite, use your testing framework's assertions or enable `-ea`. The demo code in section 6 uses `System.out.println` so behavior can be observed even without assertions enabled.

## 16. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Same package/name means same interface." | Runtime identity also depends on the defining loader. |
| "The plugin and host must share all libraries." | Only contract types need to be shared; private dependencies can have different versions. |
| "DTOs with identical source code can be cast across loaders." | Not if their defining loaders differ. |
| "Creating two loaders with the same parent is automatically safe." | Child-first can define duplicate APIs; you must verify the lookup policy. |
| "Different class loader names mean different class identities." | Names are only for diagnostics; the defining loader object determines identity. |
| "An exception with the same name will be caught properly." | Catch checks the runtime exception type/subtype, not just the class name. |
| "`throws` is in the JVM method descriptor." | `throws` is recorded in the `Exceptions` metadata, not in the parameter/return descriptor. |
| "Generic `List<Request>` guarantees every element has the right identity." | Erasure does not merge two `Request` runtime classes. |
| "Records automatically solve version compatibility." | Changing record components/constructors can break the ABI/schema. |
| "Always use child-first for every package for maximum isolation." | This can create duplicate shared APIs and linkage errors. |
| "`URLClassLoader.close()` immediately unloads the plugin." | Closing does not automatically clear all references or classes. |
| "Same interface name guarantees ServiceLoader accepts the provider." | The provider must be assignable to the exact shared service `Class<?>`. |

## 17. Self-Check Questions

**Question 1.** Loaders A and B each define `impl.Formatter` while both delegate `api.Plugin` to parent H. Is that valid?

**Answer:** Yes. Private implementations in different defining loaders may share the same name, while the shared interface maintains a single unified runtime identity.

**Question 2.** Two `api.Request` classes have the same binary name and bytecode but are independently defined by H and P. What will `requestH.getClass() == requestP.getClass()` evaluate to?

**Answer:** `false`, because the two runtime class identities have different defining loaders.

**Question 3.** Why should the host define `api.PluginFailure`?

**Answer:** The host wants to catch and handle errors using a stable runtime exception type; the plugin must throw that exact shared exception or a valid subtype, rather than defining its own copy.

**Question 4.** Which type names does the method descriptor of `Result handle(Request request) throws PluginFailure` contain?

**Answer:** `(Lapi/Request;)Lapi/Result;`. `PluginFailure` in `throws` is not part of the method descriptor; it is stored in exception metadata.

**Question 5.** If a plugin uses child-first for `api.*` and implements its own copy of `api.Plugin`, will the host casting the plugin object to H's `Plugin` definitely succeed?

**Answer:** No. If the class only implements P's own interface, it is not assignable to `api.Plugin` defined by H; a `ClassCastException` or related linking error may occur.

**Question 6.** Does `List<Request>` automatically make `Request` copies from two loaders compatible?

**Answer:** No. Generics erasure does not alter runtime class identity; runtime casts or usage can still fail.

**Question 7.** The host has API v2, whereas the plugin was compiled against API v1 and calls a removed method. If there is only a single defining loader for the shared API, can the program still fail?

**Answer:** Yes. `NoSuchMethodError` or binary compatibility errors can still occur due to an ABI mismatch; a shared loader identity does not guarantee compatibility across all versions.

**Question 8.** Why in the demo is `a.getClass() != b.getClass()` while both are still `instanceof Plugin`?

**Answer:** A and B each define their own `plugin.Worker` implementation, yet both implement the exact same runtime `api.Plugin` interface from the parent.

**Question 9.** Can `catch (PluginFailure e)` catch a class named `api.PluginFailure` from another loader solely because of the matching binary name?

**Answer:** No. The exception object must belong to the exact runtime class known to the host or a valid subclass of it.

**Question 10.** When hot-reloading plugin A, is it necessary to recreate the shared API loader every time?

**Answer:** Typically no. Create a new loader for the new implementation version and keep the shared API loader stable as long as the host contract remains compatible; clear references to the old plugin to support unloading.

## 18. Summary and References

**Three core principles:**

1. **Shared identity for the contract:** interfaces, DTOs, and exceptions used across the host–plugin boundary must resolve to the **same `Class<?>`**.
2. **Separate identity for implementations:** implementation classes and private versioned dependencies can be defined by separate loaders for isolation.
3. **Verify linking, ABI, and lifecycle:** parent delegation, Java/JVMS loading constraints, checked exceptions, ServiceLoader, version compatibility, and resource cleanup are all part of a resilient plugin architecture.

**Official sources (Java 17):**

- [JVMS 17 — 5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loaders.
- [JVMS 17 — 5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): type consistency requirements across loaders.
- [JVMS 17 — 4.3 Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): method descriptors and reference type names.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation, `findClass`, `loadClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): plugin URL paths, parent, and `close`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider lookup, explicit loader, TCCL.
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record type semantics.
- [JLS 17 — 13 Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): binary compatibility when changing APIs.
