# Isolating Two Library Versions Without Duplicating Contract Types

A Java application may need to run two plugins simultaneously, each compiled against a **different version of the same library**. If both versions are placed on a shared classpath, classes with identical fully qualified names can collide: the JVM uses only one class definition per name within the scope of a single class loader. A plugin may encounter `NoSuchMethodError`, `NoClassDefFoundError`, or observe behavior from the wrong version.

The solution at the plugin boundary is to **isolate implementations and dependent libraries using separate class loaders**, while keeping a **single copy of the SPI/API contract types in the parent class loader**. Two plugins can load two classes with the same binary name yet still be invoked by the application through the same interface.

This article illustrates that architecture using Java 17, two versions of `demo.lib.TextEngine` with **different** APIs, two providers bearing the same fully qualified name `demo.plugin.TransformPlugin`, and a shared `demo.spi.TextPlugin`. The example includes compile commands, JAR packaging, execution, and exact output.

## 1. The Problem: Duplicate Class Names on a Single Classpath

Suppose the `text-lib` library has two versions:

| Characteristic | `text-lib-v1.jar` | `text-lib-v2.jar` |
|---|---|---|
| Class name | `demo.lib.TextEngine` | `demo.lib.TextEngine` |
| Public API | `transform(String)` | `render(String)` |
| Behavior | Prepends `[v1]`, converts to lowercase | Prepends `[v2]`, converts to uppercase |
| Dependent plugin | Old plugin `legacy` | New plugin `modern` |

Both versions share the **same binary name** `demo.lib.TextEngine` but do not have the same set of methods. When a standard class loader loads the name `demo.lib.TextEngine` from a classpath containing both JARs, that class loader does not create two independent `Class` versions merely because there are two JARs. Whichever version is found by the classpath lookup mechanism is used for that class identity in that loader.

For example, the new plugin was compiled to call `TextEngine.render(String)`. If at runtime the name `TextEngine` gets linked to v1, which lacks `render(String)`, the call can fail with `NoSuchMethodError`. Swapping the order of the two JARs to fix the new plugin can break the old plugin. Forcing all plugins onto one version is also not always feasible because the APIs differ.

**The goal of this article** is not to load two classes of the same name into *one* loader; we create **two independent class-loading spaces** for the implementations while keeping **one shared space** for the communication contract.

## 2. Class Identity in the JVM: Name Alone Is Not Enough

In the JVM, class type identity with respect to class loading depends on the **binary name and the defining class loader**. Two classes with the same fully qualified name defined by two different loaders are **two distinct types**.

```text
Class identity ≈ (binary class name, defining class loader)

("demo.lib.TextEngine", loader-v1) !=
("demo.lib.TextEngine", loader-v2)
```

The notation above merely describes the type identity rule, not Java syntax. In real code, you can verify it by comparing two `Class<?>` objects:

```java
// Illustrative expression, used in full in Main.java below.
boolean sameType =
        loaderV1.loadClass("demo.lib.TextEngine")
        == loaderV2.loadClass("demo.lib.TextEngine");
```

The desired result is `false`. Two loaders can load two independent copies of `TextEngine`, even when the class names are identical.

However, this exact rule causes another problem if we also duplicate the `demo.spi.TextPlugin` contract:

```text
demo.spi.TextPlugin defined by parent
            DIFFERS FROM
demo.spi.TextPlugin defined by child
```

If a provider `implements` the interface version defined by the child while the host expects the interface version defined by the parent, the interface names look identical yet are **not the same type**. You can hit a provider "not a subtype" error, `ClassCastException`, or related type linkage errors.

Therefore, **two constraints** must be enforced simultaneously:

1. **Private to child:** each plugin's implementation classes and private libraries are defined in that plugin's loader.
2. **Shared from parent:** the SPI interface, DTOs, and shared types used in communication signatures are obtained from the parent class loader. Plugin JARs must not bundle an extra copy of the contract.

A class loader is only a class-loading mechanism; it does not automatically fix a design error when an SPI signature exposes types to the host that only exist inside a child class loader.

## 3. Parent–Child Architecture with Proper Boundaries

We organize it as follows:

```text
APPLICATION / PARENT CLASS LOADER
  classpath:
    spi.jar
    host.jar

  demo.spi.TextPlugin          <-- ONE single contract
  demo.host.Main
  demo.host.PluginClassLoader
                  |
         +--------+--------+
         |                 |
         v                 v
   PLUGIN LOADER V1   PLUGIN LOADER V2
    separate URLs      separate URLs
   plugin-v1.jar      plugin-v2.jar
   lib-v1.jar         lib-v2.jar

   demo.plugin.       demo.plugin.
     TransformPlugin    TransformPlugin
   demo.lib.          demo.lib.
     TextEngine         TextEngine
   (API v1)           (API v2)
         |                 |
         +--------+--------+
                  |
        Both implement/call
         demo.spi.TextPlugin
          loaded by parent
```

The path of an invocation:

1. The host uses **one** `TextPlugin.class` from the parent to request the services.
2. The host creates two distinct class loaders, each knowing only the JAR of one plugin and its corresponding library version.
3. Each loader discovers its provider via `ServiceLoader.load(TextPlugin.class, loader)`.
4. When loading `demo.plugin.TransformPlugin` or `demo.lib.TextEngine`, the child loader fetches the class from its own JAR set.
5. When the provider needs `demo.spi.TextPlugin`, it delegates to the parent and receives the **exact interface the host is using**.
6. The host holds/manipulates objects exclusively through `TextPlugin`, so it can invoke both providers without importing `TextEngine` from either version.

**Dependency boundary:** `spi.jar` and `host.jar` sit on the **application classpath**; `plugin-v1.jar`, `lib-v1.jar`, `plugin-v2.jar`, and `lib-v2.jar` are **not on the application classpath**. The host opens them via dedicated `URLClassLoader` instances at runtime.

If the parent lacks `demo.lib.*` or `demo.plugin.*`, two `URLClassLoader` instances using default parent-first delegation can also load classes that exist only in each child. The example below adds a **scoped child-first** rule for just those two private packages so loading stays as intended even if the parent environment accidentally contains matching class names. The SPI contract always follows the parent-first path.

## 4. Source Structure and Output JARs

Create the directories/files:

```text
isolation-demo/
├── contract/
│   └── src/demo/spi/TextPlugin.java
├── lib-v1/
│   └── src/demo/lib/TextEngine.java
├── lib-v2/
│   └── src/demo/lib/TextEngine.java
├── plugin-v1/
│   ├── src/demo/plugin/TransformPlugin.java
│   └── resources/META-INF/services/demo.spi.TextPlugin
├── plugin-v2/
│   ├── src/demo/plugin/TransformPlugin.java
│   └── resources/META-INF/services/demo.spi.TextPlugin
└── host/
    └── src/demo/host/
        ├── PluginClassLoader.java
        └── Main.java
```

After compilation:

```text
dist/
├── spi.jar
├── host.jar
├── lib-v1.jar
├── lib-v2.jar
├── plugin-v1.jar
└── plugin-v2.jar
```

There are **six JARs**, yet only `spi.jar` and `host.jar` are passed to `java -cp` when running `Main`. The remaining four JARs are opened by host code using two separate loaders.

## 5. Defining Exactly One SPI Contract

File `contract/src/demo/spi/TextPlugin.java`:

```java
package demo.spi;

public interface TextPlugin {
    String id();

    String transform(String text);
}
```

This contract uses only the JDK type `String` and makes no mention of `demo.lib.TextEngine`, provider class names, or library versions. `id()` returns a stable plugin identifier; `transform()` is the behavior the host is permitted to invoke. More complex data should travel through parent-owned API/DTO types, or standard JDK types.

**Do not put `TextPlugin.class` into the plugin JARs**. When compiling a plugin, `spi.jar` is present on the **compile classpath** so the compiler can check `implements`. When packaging a plugin JAR, bundle only the plugin's classes and metadata; do not copy SPI classes into it.

In this example, v1 and v2 can change every internal detail without altering the `TextPlugin` signature.

## 6. Two Library Versions with Different APIs

### 6.1. Version v1

File `lib-v1/src/demo/lib/TextEngine.java`:

```java
package demo.lib;

import java.util.Locale;

public final class TextEngine {
    private TextEngine() {}

    public static String transform(String input) {
        return "[v1] " + input.toLowerCase(Locale.ROOT);
    }
}
```

### 6.2. Version v2

File `lib-v2/src/demo/lib/TextEngine.java`:

```java
package demo.lib;

import java.util.Locale;

public final class TextEngine {
    private TextEngine() {}

    public static String render(String input) {
        return "[v2] " + input.toUpperCase(Locale.ROOT);
    }
}
```

Both files declare `package demo.lib` and `public final class TextEngine`, but **v1 has `transform(String)` while v2 has `render(String)`**. This is an intentional API difference to illustrate a version conflict. They **must not be compiled together into the same output directory**: doing so would create two definitions of a class with the same name.

`Locale.ROOT` ensures lowercase/uppercase conversion in the example does not depend on the machine's default locale.

## 7. Two Providers with the Same Class Name, Compiled with Private Dependencies

### 7.1. Provider v1

File `plugin-v1/src/demo/plugin/TransformPlugin.java`:

```java
package demo.plugin;

import demo.spi.TextPlugin;
import demo.lib.TextEngine;

public final class TransformPlugin implements TextPlugin {
    @Override
    public String id() {
        return "legacy";
    }

    @Override
    public String transform(String input) {
        return TextEngine.transform(input);
    }
}
```

The legacy provider calls the exact API of `TextEngine` v1.

### 7.2. Provider v2

File `plugin-v2/src/demo/plugin/TransformPlugin.java`:

```java
package demo.plugin;

import demo.spi.TextPlugin;
import demo.lib.TextEngine;

public final class TransformPlugin implements TextPlugin {
    @Override
    public String id() {
        return "modern";
    }

    @Override
    public String transform(String input) {
        return TextEngine.render(input);
    }
}
```

The modern provider calls the exact API of `TextEngine` v2. Note that both providers also share the name `demo.plugin.TransformPlugin`, yet their bytecode differs and they are packaged into two separate JARs.

Both providers are `public` classes and have a public no-argument constructor provided by Java when no constructor is declared. This fits the classpath provider style that `ServiceLoader` instantiates.

During compilation, each provider must see:

```text
plugin-v1:  spi.jar + lib-v1.jar
plugin-v2:  spi.jar + lib-v2.jar
```

**Do not** place both `lib-v1.jar` and `lib-v2.jar` on a single provider's compile classpath at the same time. Each provider must link against the exact API version it was designed to use.

## 8. Registering the SPI for Each Provider JAR

On the classpath, `ServiceLoader` identifies providers through the resource:

```text
META-INF/services/demo.spi.TextPlugin
```

Contents of `plugin-v1/resources/META-INF/services/demo.spi.TextPlugin`:

```text
demo.plugin.TransformPlugin
```

Contents of `plugin-v2/resources/META-INF/services/demo.spi.TextPlugin`:

```text
demo.plugin.TransformPlugin
```

The two files have the **same name and the same contents** because both JARs supply a class with the same binary name. However, each file is packaged inside **that provider's own JAR**. `ServiceLoader.load(TextPlugin.class, loaderV1)` discovers providers from the resources visible to `loaderV1`, and `loaderV2` does the same within its own scope.

This is a detail to distinguish from ordinary setups: the exact same line `demo.plugin.TransformPlugin` **does not produce the same `Class`** if that class name is defined by two different class loaders.

Do not place these providers' registration resources in `spi.jar` or `host.jar`. The parent must own the contract, but should not accidentally advertise child-private providers on the host's own classpath.

## 9. Class Loader Isolating Implementations While Delegating SPI to Parent

File `host/src/demo/host/PluginClassLoader.java`:

```java
package demo.host;

import java.net.URL;
import java.net.URLClassLoader;

public final class PluginClassLoader extends URLClassLoader {
    public PluginClassLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        synchronized (getClassLoadingLock(name)) {
            Class<?> loaded = findLoadedClass(name);

            if (loaded == null) {
                if (name.startsWith("demo.plugin.")
                        || name.startsWith("demo.lib.")) {
                    loaded = findClass(name);
                } else {
                    loaded = super.loadClass(name, false);
                }
            }

            if (resolve) {
                resolveClass(loaded);
            }
            return loaded;
        }
    }
}
```

This is a minimal version of a class loader tailored for a **known** package layout, not a general-purpose plugin manager.

Points to read carefully:

- `demo.plugin.*` and `demo.lib.*` are **each plugin's private packages**. `findClass(name)` forces them to be searched within that loader's URLs rather than mistakenly picked up from the parent.
- `demo.spi.*`, `demo.host.*`, `java.*`, and packages outside the private list go through `super.loadClass(...)`, meaning they use default delegation rules. Thus `demo.spi.TextPlugin` is loaded by the parent.
- There is no `catch ClassNotFoundException` to fall back to the parent when a class *in a private package* is missing. This is a **fail-closed** policy: a plugin missing its own dependency must report an error instead of silently picking up a different version from the host.
- `findLoadedClass(name)` prevents defining the same class twice in the same loader. Synchronizing on `getClassLoadingLock(name)` protects the loading path, and `resolveClass` handles linking when requested.
- Allocate a separate loader for **each plugin and dependency group needing isolation**. If one shared loader contains two same-named versions of `TextEngine`, the conflict reappears inside that shared loader.

**Do not apply child-first to all packages.** If child-first were applied to `demo.spi.*` as well, SPI copies in each child could be defined differently from the parent, breaking the ability to cast providers to `TextPlugin`. Many frameworks also own APIs with special class-loading rules; the private package list must be restricted and tested.

For real applications, establish clear policies for resource loading, package sealing, native libraries, signed JARs, transitive dependencies, and logging. `URLClassLoader` does not automatically guarantee that every kind of dependency can be isolated.

## 10. Host Discovering Each Provider and Verifying Type Identity

File `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.TextPlugin;

import java.net.URL;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    private static TextPlugin loadOnly(ClassLoader loader) {
        List<TextPlugin> providers = new ArrayList<>();

        for (TextPlugin provider
                : ServiceLoader.load(TextPlugin.class, loader)) {
            providers.add(provider);
        }

        if (providers.size() != 1) {
            throw new IllegalStateException(
                    "Expected 1 provider, found " + providers.size());
        }

        return providers.get(0);
    }

    public static void main(String[] args) throws Exception {
        Path dist = Path.of("dist").toAbsolutePath();
        ClassLoader parent = TextPlugin.class.getClassLoader();

        URL[] oldJars = {
                dist.resolve("plugin-v1.jar").toUri().toURL(),
                dist.resolve("lib-v1.jar").toUri().toURL()
        };
        URL[] newJars = {
                dist.resolve("plugin-v2.jar").toUri().toURL(),
                dist.resolve("lib-v2.jar").toUri().toURL()
        };

        try (PluginClassLoader oldLoader =
                     new PluginClassLoader(oldJars, parent);
             PluginClassLoader newLoader =
                     new PluginClassLoader(newJars, parent)) {

            TextPlugin oldPlugin = loadOnly(oldLoader);
            TextPlugin newPlugin = loadOnly(newLoader);

            System.out.println(
                    oldPlugin.id() + " => "
                            + oldPlugin.transform("Hello Java"));
            System.out.println(
                    newPlugin.id() + " => "
                            + newPlugin.transform("Hello Java"));

            System.out.println("same provider name: "
                    + oldPlugin.getClass().getName().equals(
                            newPlugin.getClass().getName()));
            System.out.println("same provider Class: "
                    + (oldPlugin.getClass() == newPlugin.getClass()));
            System.out.println("same library Class: "
                    + (oldLoader.loadClass("demo.lib.TextEngine")
                    == newLoader.loadClass("demo.lib.TextEngine")));
            System.out.println("shared SPI Class: "
                    + (oldLoader.loadClass("demo.spi.TextPlugin")
                    == TextPlugin.class
                    && newLoader.loadClass("demo.spi.TextPlugin")
                    == TextPlugin.class));
        }
    }
}
```

`Main` has no `import demo.plugin.TransformPlugin` or `import demo.lib.TextEngine` statements. The host uses only `TextPlugin`, a type loaded by the parent. Each `ServiceLoader` is created **with a specific class loader**; calling the overload without a loader depends on the thread's context class loader and does not guarantee the intended isolation model.

The `loadOnly()` method checks that there is **exactly one provider in each scope**. This is the example's policy. In a multi-provider system, you can build a registry and select by ID/capability/configuration, while keeping discovery separated by loader to avoid collisions.

`try-with-resources` calls `close()` on both `URLClassLoader` instances at the end. This closes open loader resources, **which does not mean all classes are immediately unloaded**; the JVM can reclaim classes only when the loader and any related objects/threads/resources holding references are no longer live.

## 11. Compiling Six JARs with Java 17+

The example is verified with Java 17-compatible code (`javac --release 17`). Run from the `isolation-demo` directory created with the exact file tree above. The compilation commands below **intentionally separate each output directory** so same-named classes do not overwrite each other.

### 11.1. Linux/macOS (Bash)

```bash
mkdir -p out/spi out/lib-v1 out/lib-v2 out/plugin-v1 out/plugin-v2 out/host dist

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/TextPlugin.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -d out/lib-v1 lib-v1/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v1.jar -C out/lib-v1 .

javac --release 17 -encoding UTF-8 -d out/lib-v2 lib-v2/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v2.jar -C out/lib-v2 .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar:dist/lib-v1.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar:dist/lib-v2.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/PluginClassLoader.java host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp dist/spi.jar:dist/host.jar demo.host.Main
```

### 11.2. Windows PowerShell

PowerShell and Windows Java classpaths use `;` to separate JARs. Put quotes around the classpath string when it contains `;`:

```powershell
New-Item -ItemType Directory -Force out/spi,out/lib-v1,out/lib-v2,out/plugin-v1,out/plugin-v2,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/TextPlugin.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -d out/lib-v1 lib-v1/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v1.jar -C out/lib-v1 .

javac --release 17 -encoding UTF-8 -d out/lib-v2 lib-v2/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v2.jar -C out/lib-v2 .

javac --release 17 -encoding UTF-8 -cp 'dist/spi.jar;dist/lib-v1.jar' -d out/plugin-v1 plugin-v1/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp 'dist/spi.jar;dist/lib-v2.jar' -d out/plugin-v2 plugin-v2/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/PluginClassLoader.java host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp 'dist/spi.jar;dist/host.jar' demo.host.Main
```

**Classpath check:** in the **final `java` command**, only `spi.jar` and `host.jar` are present. The `lib-v1`, `lib-v2`, `plugin-v1`, and `plugin-v2` JARs are opened by Java code from `Path.of("dist")`; if you are running from a different directory, update the `dist` directory path in the program or run from the exact demo root directory.

### 11.3. Expected Output

Stdout on a successful run:

```text
legacy => [v1] hello java
modern => [v2] HELLO JAVA
same provider name: true
same provider Class: false
same library Class: false
shared SPI Class: true
```

Line-by-line explanation:

- `legacy` calls v1's `TextEngine.transform` properly, producing `[v1] hello java`.
- `modern` calls v2's `TextEngine.render` properly, producing `[v2] HELLO JAVA`.
- The binary names of the two providers are **identical**, yet the two `Class` objects are distinct because they were defined in two separate loaders.
- The two `demo.lib.TextEngine` copies are also two distinct `Class` objects, so the v1/v2 APIs do not collide.
- Each child, when requesting `demo.spi.TextPlugin`, receives the exact `TextPlugin.class` from the parent. This is the prerequisite for the host to interact with both through the same interface.

## 12. Verifying That the JARs Truly Package the Right Boundaries

Use the `jar --list` command (identical across operating systems):

```bash
jar --list --file dist/spi.jar
jar --list --file dist/plugin-v1.jar
jar --list --file dist/plugin-v2.jar
jar --list --file dist/lib-v1.jar
jar --list --file dist/lib-v2.jar
```

Conditions to check:

| Artifact | Must contain | Must not contain |
|---|---|---|
| `spi.jar` | `demo/spi/TextPlugin.class` | `demo/lib/TextEngine.class`, provider classes, provider registration files |
| `plugin-v1.jar` | `demo/plugin/TransformPlugin.class`, `META-INF/services/demo.spi.TextPlugin` | `demo/spi/TextPlugin.class`, `TextEngine.class` of another version |
| `plugin-v2.jar` | `demo/plugin/TransformPlugin.class`, corresponding registration file | SPI copy, v1 library classes |
| `lib-v1.jar` | v1 `demo/lib/TextEngine.class` | Contract classes, plugin classes |
| `lib-v2.jar` | v2 `demo/lib/TextEngine.class` | Contract classes, plugin classes |
| `host.jar` | `demo/host/Main.class`, `demo/host/PluginClassLoader.class` | Provider classes or private libraries |

You can see both plugin JARs contain a class at the **exact same path** `demo/plugin/TransformPlugin.class`; that is intentional and safe only because each plugin is opened from a **separate loader**.

If using Maven or Gradle, the equivalent is: `spi.jar` is a shared compile dependency, **no copy of the SPI may be shaded/relocated into individual plugins**; private dependencies are packaged in their own class-loading scope and do not leak onto the host classpath. Transitive dependencies must also be audited, because conflicts do not happen only with direct libraries.

## 13. Why Seemingly Simple Approaches Can Fail

### 13.1. Putting Both JARs with Overlapping Classes on the Host Classpath

The command below illustrates an **incorrect configuration**; you do not need to run it to understand the consequence:

```bash
# Illustrates an INCORRECT configuration when wanting to isolate two versions
java -cp "dist/spi.jar:dist/host.jar:dist/lib-v1.jar:dist/lib-v2.jar:dist/plugin-v1.jar:dist/plugin-v2.jar" demo.host.Main
```

Once the host already sees the provider classes and resources, the discovery/parent-delegation boundary is polluted: the parent can locate provider registration resources for both plugins, while the parent itself can hold only one definition per class name. The outcome depends on configuration and can cause `ServiceLoader` to see unintended providers or hit API errors. Do not turn the host's `-cp` into a catch-all list containing all plugin versions.

### 13.2. Placing `spi.jar` Independently in Each Loader and Child-First Loading the SPI Too

If each child defines `demo.spi.TextPlugin` itself, then even though the provider inside the child `implements TextPlugin`, **it is not the `TextPlugin.class` held by the host**. A common message when `ServiceLoader` discovers a provider that is not a subtype can be `ServiceConfigurationError`; manual casting can also cause `ClassCastException`.

The solution is to publish the contract in the parent and force loaders to obtain the SPI from the parent. Put only implementation and private dependency packages in the child-first list.

### 13.3. Letting Private Library Types Appear in SPI Signatures

The following contract is **unsuitable** for the goal of isolating v1 and v2:

```java
// Illustrates a design to avoid, not a standalone runnable example.
public interface BadPlugin {
    demo.lib.TextEngine getEngine();
}
```

Which `demo.lib.TextEngine` type would the host understand, when v1 and v2 are two distinct classes? Instead, return a shared type in `spi.jar`, a parent-defined DTO, or standard data like `String`, `byte[]`, or `InputStream` with clear ownership/lifecycle rules.

Not only return types: parameters, public exceptions, callbacks, and superinterfaces must all be evaluated under the same principle. Do not exchange private library objects directly across two loader scopes and attempt to cast on the host side.

### 13.4. Assuming `close()` on a Loader Enables Hot Upgrades

`URLClassLoader.close()` closes the resources managed by the loader; classes and instances can still remain alive if registries, threads, context class loaders, callbacks, singletons, or static fields elsewhere still hold references. Replacing a plugin while the JVM is running requires a procedure to stop usage, close resources, unregister, drop references, create a new loader, and verify safety for in-flight requests.

Do not describe `ServiceLoader.reload()` as a "swap JAR" feature. It only clears the provider cache of the corresponding `ServiceLoader` instance; it does not replace URLs, JAR versions, class loaders, or instances already held by the host.

## 14. Typical Errors and Root-Cause Diagnosis

| Symptom | Possible cause | What to check |
|---|---|---|
| `NoSuchMethodError` when plugin calls library | Provider compiled against v2 API but runtime linked the class name to v1 (or vice versa) | Inspect JARs in each loader and actual methods present in the class |
| `ServiceConfigurationError: ... not a subtype` | Provider implements an SPI copy from a different loader than the host's SPI | Check `TextPlugin.class` identity, parent-first policy, and whether SPI was bundled in the plugin |
| `ClassCastException` despite identical class names | Two `Class<?>` objects were defined by two different loaders | Compare `Class.getClassLoader()` and `Class<?>` rather than only `getName()` |
| `ClassNotFoundException` or `NoClassDefFoundError` | Plugin is missing a private JAR or transitive dependency | Check `oldJars`/`newJars`, JAR contents, and actual file paths |
| `Expected 1 provider, found 0` | Missing `META-INF/services` file or provider JAR is outside loader scope | Check registration file and how many providers the loader detects |
| `Expected 1 provider, found 2` | One loader sees multiple provider resources or the parent published providers | Audit host classpath, `getResources`, and which component owns metadata |
| Running one plugin works, adding the second fails | Both versions of the library were combined into one loader or the host classpath | Separate loaders and ensure the host contains only contract/host |
| Loader closed yet classes have not unloaded | Live references exist to classes, instances, threads, or the loader | Inspect registries, thread context loaders, callbacks, caches, and lifecycle |
| Class loads properly yet returned data cannot be cast | Child-private type leaked through signature or payload | Move communication types into the parent-owned SPI/API |

Linkage errors in the JVM can surface **lazily**, on the first execution of a code path needing that method/class. A plugin initializing successfully does not prove all dependencies are compatible. Run smoke tests across each provider's critical paths.

## 15. Limitations of Class-Loader-Based Isolation

Class loaders solve **class namespace** conflicts, but do not automatically provide:

- **Process or permission isolation:** providers run inside the host's JVM and can access corresponding resources. Do not treat class loaders as a sandbox for running untrusted code.
- **System state isolation:** system properties, environment, process state, files, ports, certain caches/JDK singletons, and native resources may still be shared.
- **Universal compatibility:** libraries using JNI/native libraries, reflective access, context class loaders, nested `ServiceLoader` calls, or complex callbacks may require additional configuration.
- **Automatic security patch management:** each library version still requires separate SBOM, CVE, license, and release lifecycle management.
- **Safe hot reload:** stopping old plugins and creating new loaders is a lifecycle problem, especially in multithreaded applications.

In large environments, you can use plugin frameworks, JPMS module layers, or process isolation when requirements are more complex. The Java Platform Module System uses module/layer concepts and `uses`/`provides` declarations; this example **intentionally uses only classpath and `URLClassLoader`** to focus on the boundary between shared types and private dependencies.

## 16. Pre-Project Design Checks

Answer the following questions for every plugin architecture:

1. **Who owns the SPI?** Is there exactly one parent class loader defining the interfaces and shared communication types?
2. **Which packages are private?** Does the child loader define only implementation classes and truly isolated dependencies, or did it accidentally create an extra copy of the API?
3. **Which version does each plugin see?** Do its compile classpath and runtime URLs match the exact library version required?
4. **Where does provider discovery happen?** Is the right class loader passed to `ServiceLoader`, and is `META-INF/services` placed in the right plugin JAR?
5. **Which types cross the boundary?** Are any DTOs, exceptions, or callbacks carrying child-private types that will fail to cast on the host?
6. **When are errors caught?** Are providers verified, smoke tests run, and class loader/JAR info logged to diagnose mislinkage?
7. **What is the lifecycle?** Who closes loaders, destroys providers, stops threads, and releases resources when unloading a plugin?
8. **What is the safety boundary?** Are plugins trusted, and is process isolation needed instead of class loaders alone?

## 17. Reinforcement Exercises

1. **Demonstrate version dependency:** change only `lib-v2`'s method from `render(String)` to `render(String, boolean)` without recompiling provider v2. Predict which linkage error can occur when calling `modern` and explain why `legacy` still works in its own loader. Then recompile provider v2 against the new API.
2. **Intentionally misconfigure the classpath:** add both library versions to the host classpath and observe why discovery results can change. Before trying, save the working commands to restore the demo environment.
3. **Verify class identity:** print `oldPlugin.getClass().getClassLoader()` and `newPlugin.getClass().getClassLoader()`. Why are the class names identical yet you cannot conclude they are the same type?
4. **Introduce a shared DTO:** add `demo.spi.TransformRequest` to `spi.jar` and change the contract to `transform(TransformRequest)`. Verify that both plugins use the exact DTO from the parent.
5. **Add a third provider:** create a v3 dependency version in a third loader. The host should only hold objects through the shared interface. Design an identifier and provider selection rule that does not rely on discovery order.
6. **Loader release:** describe what keeps a loader from being reclaimed if a plugin thread keeps running after the host closes the loader.

**Decision principle:** to run two library versions with colliding class names in parallel, you need **separate loaders for private dependencies**; for the host to speak with both, you need **a shared contract class defined by the parent**. JAR organization, classpaths, delegation mechanisms, and cross-boundary data types must all adhere to that principle.