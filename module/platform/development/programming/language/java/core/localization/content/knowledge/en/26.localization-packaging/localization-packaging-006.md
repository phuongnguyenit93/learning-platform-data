# ResourceBundleProvider for Resources in the Java Module System (JPMS)

## Objectives

In Java Core, `java.util.ResourceBundle` loads messages or data by `Locale`. When an application runs on the classpath, `.properties` files and `ListResourceBundle` classes are typically resolved via the class loader. When moving to the **Java Platform Module System (JPMS)**, resources can be packaged inside **named modules** with their own access boundaries. When an application needs to obtain bundles from **an independent provider module**, the appropriate API is **`java.util.spi.ResourceBundleProvider`**.

`ResourceBundleProvider` is a **service provider interface (SPI)** introduced in Java 9, integrated with bundle lookup and `ServiceLoader`. Using `uses` and `provides ... with ...` in `module-info.java`, a consumer module can discover one or more resource-providing modules without importing a concrete implementation.

After this lesson, you will be able to:

- Distinguish bundles located in the **same named module** from bundles provided by **another named module**.
- Name the service interface accurately based on the bundle's **logical base name**.
- Use `ResourceBundleProvider#getBundle(String, Locale)` and understand the meaning of returning `null`.
- Implement `AbstractResourceBundleProvider` for `.properties` files and override `toBundleName` to relocate resources.
- Write three modules — API, provider, and consumer — with `exports`, `requires`, `uses`, and `provides` in their proper roles.
- Compile and run a **working Java 17+ example** using `--module-source-path` and `--module-path`.
- Understand **split packages**, module resolution, candidate locales, fallback, caching, and encapsulation.
- Distinguish `ResourceBundleProvider` from `ResourceBundle.Control` when upgrading a classpath application to JPMS.
- Diagnose missing provider modules, missing resource files, wrong service names, or `MissingResourceException`.

This lesson belongs to the **Packaging and Extensibility** group: the focus is supplying translations via SPI in JPMS, not number/date formatting syntax or automated translation systems.

## 1. Why Not Just Use ResourceBundle.getBundle Directly?

A small application can keep translation files and code in the same module:

```text
com.example.app
  module-info.java
  com/example/app/Main.class
  com/example/app/Messages_vi.properties
```

When resources are packaged properly and accessed from that same module, `ResourceBundle.getBundle(baseName, locale)` can load the local bundle; **creating a provider interface is not mandatory** for every JPMS application.

Different needs arise when translations are distributed separately, for example:

- A core product knows only the keys, while localization teams ship separate Vietnamese, English, and French modules.
- Plugins need to add languages after the main application has already been compiled.
- A library publishes only the resource API without bundling every translation.
- A provider module wants to load custom sources rather than letting consumers search internal files.

If the bundle resides in another named module, calling `ClassLoader.getResourceAsStream` from the consumer **will not always see the resource** due to encapsulation rules. `ResourceBundleProvider` lets the **module owning the resource** take responsibility for creating or loading the `ResourceBundle` and returning it to Java's bundle-loading mechanism.

```text
com.demo.bundle.app
    |
    | ResourceBundle.getBundle("com.demo.bundle.Messages", locale)
    | uses com.demo.bundle.spi.MessagesProvider
    v
com.demo.bundle.api
    |
    | interface MessagesProvider extends ResourceBundleProvider
    ^
    | implements
com.demo.bundle.impl
    |
    +-- DemoProvider
    +-- Messages_vi.properties
    +-- Messages_en.properties
```

The consumer still needs to know the **logical base name** and **message keys**, yet does not need a direct dependency on the implementation class or the physical package of the translation files.

## 2. Core Terminology and Roles

| Concept | Meaning | Example |
| --- | --- | --- |
| **Base name** | Logical identifier of the bundle family | `com.demo.bundle.Messages` |
| **Locale** | Requested language/region | `vi-VN`, `en-US` |
| **Service type** | Interface named per the special `ResourceBundleProvider` convention | `com.demo.bundle.spi.MessagesProvider` |
| **Provider implementation** | Class returning bundles by base name/locale | `com.demo.impl.DemoProvider` |
| **API module** | Module defining/exporting the service interface | `com.demo.bundle.api` |
| **Consumer module** | Module calling `ResourceBundle.getBundle` | `com.demo.bundle.app` |
| **Provider module** | Module implementing the service and owning resources | `com.demo.bundle.impl` |
| **Physical bundle name** | Where the provider looks up actual resource files/classes | `com.demo.impl.Messages_vi` |
| **Resolved locale** | Locale of the bundle actually loaded | `vi` |

**The logical base name does not have to match the physical bundle name.** This is an important extensibility point: callers use a stable family name while provider modules can organize resources in distinct packages.

## 3. Service Interface Naming Convention

Per Java SE 17, the service type for a bundle with `baseName` must have the fully qualified name:

```text
<package of baseName> + ".spi."
+ <simple name of baseName> + "Provider"
```

Examples:

| Base name | Service interface |
| --- | --- |
| `com.demo.bundle.Messages` | `com.demo.bundle.spi.MessagesProvider` |
| `org.acme.ui.Errors` | `org.acme.ui.spi.ErrorsProvider` |
| `io.example.labels.Buttons` | `io.example.labels.spi.ButtonsProvider` |

Correct interface for our example:

```java
package com.demo.bundle.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

Note that this interface **inherits** the `getBundle(String, Locale)` method. Its name must match the `com.demo.bundle.Messages` family.

Two common mistakes:

1. Putting `MessagesProvider` in package `com.demo.bundle` instead of `com.demo.bundle.spi` and expecting Java to find it.
2. Writing only `uses java.util.spi.ResourceBundleProvider;` in the consumer, when the service type looked up for the family is `com.demo.bundle.spi.MessagesProvider`.

In this case, the name is not an arbitrary preference of the development team: it is an **API naming contract**. Calling `ResourceBundle.getBundle("...Messages", locale)` requires all modules to agree on the corresponding service type.

## 4. How Do the API, Consumer, and Provider Modules Link Together?

### API Module

```java
module com.demo.bundle.api {
    exports com.demo.bundle.spi;
}
```

`exports` exposes the package containing the interface so both provider and consumer can reference the Java type.

### Consumer Module

```java
module com.demo.bundle.app {
    requires com.demo.bundle.api;
    uses com.demo.bundle.spi.MessagesProvider;
}
```

`requires` lets the app read the API module; `uses` declares that the module consumes that service.

### Provider Module

```java
module com.demo.bundle.impl {
    requires com.demo.bundle.api;

    provides com.demo.bundle.spi.MessagesProvider
            with com.demo.impl.DemoProvider;
}
```

`provides ... with ...` registers the implementation class. This class must implement the exact interface and satisfy JPMS service-loading requirements. The example uses a `public` class with a `public` no-arg constructor.

These declarations must **match the exact same interface**. Omitting `requires com.demo.bundle.impl;` from the app is intentional to avoid a direct dependency on the implementation; the provider is discovered via service binding when the module is resolved.

**Do not use `open module` to fix a wrong service name.** Opening packages for reflection is unrelated to proper service registration and resource loading.

## 5. The ResourceBundleProvider#getBundle Contract

The base SPI in `java.util.spi` has the signature:

```java
ResourceBundle getBundle(String baseName, Locale locale);
```

Do not create your own Java file in package `java.util.spi`; this is the built-in API signature.

The provider is invoked while `ResourceBundle` searches for a matching bundle across candidate locales:

- `baseName` is the logical name requested by the consumer.
- `locale` is a candidate locale being tried, not necessarily the final requested locale.
- Return a `ResourceBundle` when the provider has the matching resource.
- Return `null` when the provider **has no resource for the `baseName`/`locale` pair**.

Example in a subclass of `AbstractResourceBundleProvider`:

```java
@Override
public ResourceBundle getBundle(String baseName, Locale locale) {
    if (!"com.demo.bundle.Messages".equals(baseName)) {
        return null;
    }
    return super.getBundle(baseName, locale);
}
```

This is an illustrative snippet inside a provider class with `import java.util.ResourceBundle;` and `import java.util.Locale;`.

`null` **is not an exception**: it allows the loading process to try other candidates or other suitable sources. However, do not catch I/O errors, corrupt data, or bugs and silently return `null`; doing so hides operational signals.

If no bundle is found, `ResourceBundle.getBundle` throws `MissingResourceException`. If a bundle is found yet a key is absent, `bundle.getString(key)` also throws `MissingResourceException`. Distinguish these two cases when investigating.

## 6. AbstractResourceBundleProvider and toBundleName

`java.util.spi.AbstractResourceBundleProvider` supplies a base implementation that looks up bundles **inside the provider's own module**. Constructor:

```java
public DemoProvider() {
    super("java.properties");
}
```

`java.properties` and `java.class` are the formats supported by the base class. For other formats such as XML or JSON, implement `getBundle` appropriately instead of passing unsupported format strings to the superclass.

Method:

```java
protected String toBundleName(String baseName, Locale locale);
```

is used to construct the resource name corresponding to a locale. By default it follows standard naming like `Messages_vi` or `Messages_en_US`.

If multiple translation modules are placed into the same module graph, placing them in the same Java package can cause **split package** issues. A provider can override it to redirect to its own physical package:

```java
@Override
protected String toBundleName(String baseName, Locale locale) {
    return "com.demo.impl.Messages"
            + (locale.equals(Locale.ROOT)
                ? "" : "_" + locale.toString());
}
```

For locale `vi`, the result is `com.demo.impl.Messages_vi`, corresponding to:

```text
com/demo/impl/Messages_vi.properties
```

The consumer still calls baseName `com.demo.bundle.Messages`. The physical mapping lives inside the implementation, unexposed in the consumer's API.

Other separate providers can choose packages such as `com.demo.impl.fr`, `com.demo.impl.de`, etc., when designing for extensibility, provided they avoid package collisions and obey module/resource rules.

## 7. Complete Java 17+ Example with Three Named Modules

The layout below was compiled and run on JDK 21 using only APIs present in Java 17. Illustrative translation values use ASCII so output does not depend on terminal charsets; real translation files can store accented Vietnamese text in UTF-8.

### 7.1. Directory Tree

```text
resourcebundle-provider-demo/
├── src/
│   ├── com.demo.bundle.api/
│   │   ├── module-info.java
│   │   └── com/demo/bundle/spi/MessagesProvider.java
│   ├── com.demo.bundle.impl/
│   │   ├── module-info.java
│   │   └── com/demo/impl/
│   │       ├── DemoProvider.java
│   │       ├── Messages_vi.properties
│   │       └── Messages_en.properties
│   └── com.demo.bundle.app/
│       ├── module-info.java
│       └── com/demo/app/Main.java
└── mods/                          (generated during build)
```

Directories under `src` must match the module names in `module-info.java` when using `--module-source-path`.

### 7.2. API Module

File `src/com.demo.bundle.api/module-info.java`:

```java
module com.demo.bundle.api {
    exports com.demo.bundle.spi;
}
```

File `src/com.demo.bundle.api/com/demo/bundle/spi/MessagesProvider.java`:

```java
package com.demo.bundle.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

### 7.3. Provider Module

File `src/com.demo.bundle.impl/module-info.java`:

```java
module com.demo.bundle.impl {
    requires com.demo.bundle.api;

    provides com.demo.bundle.spi.MessagesProvider
            with com.demo.impl.DemoProvider;
}
```

File `src/com.demo.bundle.impl/com/demo/impl/DemoProvider.java`:

```java
package com.demo.impl;

import com.demo.bundle.spi.MessagesProvider;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

public final class DemoProvider extends AbstractResourceBundleProvider
        implements MessagesProvider {

    public DemoProvider() {
        super("java.properties");
    }

    @Override
    protected String toBundleName(String baseName, Locale locale) {
        return "com.demo.impl.Messages"
                + (locale.equals(Locale.ROOT)
                    ? "" : "_" + locale.toString());
    }

    @Override
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!"com.demo.bundle.Messages".equals(baseName)) {
            return null;
        }

        String language = locale.getLanguage();
        if (!language.equals("vi") && !language.equals("en")) {
            return null;
        }

        return super.getBundle(baseName, locale);
    }
}
```

This class exposes a public no-arg constructor and implements the proper interface. `toBundleName` loads files from package `com.demo.impl` rather than the logical package. `getBundle` rejects mismatched families or unsupported languages, delegating valid cases to the superclass to locate the resource.

File `src/com.demo.bundle.impl/com/demo/impl/Messages_vi.properties`:

```properties
welcome=Xin chao
```

File `src/com.demo.bundle.impl/com/demo/impl/Messages_en.properties`:

```properties
welcome=Hello
```

To switch to accented translations, save in UTF-8 and check the build encoding. `PropertyResourceBundle` since Java 9 supports UTF-8 by contract with ISO-8859-1 fallback when applicable; do not confuse it with `Properties.load(InputStream)`.

### 7.4. Consumer Module

File `src/com.demo.bundle.app/module-info.java`:

```java
module com.demo.bundle.app {
    requires com.demo.bundle.api;
    uses com.demo.bundle.spi.MessagesProvider;
}
```

File `src/com.demo.bundle.app/com/demo/app/Main.java`:

```java
package com.demo.app;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        ResourceBundle vi = ResourceBundle.getBundle(
                "com.demo.bundle.Messages",
                Locale.forLanguageTag("vi-VN"));

        ResourceBundle en = ResourceBundle.getBundle(
                "com.demo.bundle.Messages",
                Locale.US);

        System.out.println("VI=" + vi.getString("welcome")
                + " (" + vi.getLocale().toLanguageTag() + ")");

        System.out.println("EN=" + en.getString("welcome")
                + " (" + en.getLocale().toLanguageTag() + ")");
    }
}
```

The app does not import `DemoProvider`; it only knows the `baseName` and the service contract.

### 7.5. Compiling and Copying Resource Files

Run from the `resourcebundle-provider-demo` directory using Bash on Linux/macOS:

```bash
mkdir -p mods

javac -encoding UTF-8 \
  --module-source-path src \
  -d mods \
  $(find src -name '*.java')

cp src/com.demo.bundle.impl/com/demo/impl/*.properties \
   mods/com.demo.bundle.impl/com/demo/impl/
```

`find`, `cp`, and `$(...)` syntax belong to Bash; do not run them verbatim in PowerShell. In PowerShell, you can collect Java files with `Get-ChildItem -Recurse -Filter *.java` to pass paths to `javac`, and use `Copy-Item` to copy `.properties` files.

**Commonly forgotten step:** `javac` compiles Java files but does not automatically copy non-Java resources into `mods`. If `.properties` files stay only in `src`, the runtime will have no content for the provider to load. When using Maven/Gradle, verify that resources actually reach the build output/JAR at the expected path.

### 7.6. Running the Program

```bash
java --module-path mods \
  --module com.demo.bundle.app/com.demo.app.Main
```

Stdout:

```text
VI=Xin chao (vi)
EN=Hello (en)
```

At runtime in this test, service binding resolves the provider module from the module path because the app declares the matching `uses`. You can also explicitly add the provider module to the graph:

```bash
java --module-path mods \
  --add-modules com.demo.bundle.impl \
  --module com.demo.bundle.app/com.demo.app.Main
```

Output remains identical.

Why `vi` and `en`? The code requested `vi-VN` and `en-US`, yet the provider only has `Messages_vi.properties` and `Messages_en.properties`. `ResourceBundle` tries less specific candidates, so `bundle.getLocale()` reports `vi` or `en`.

This three-module example has been **compiled and executed**, including both with and without `--add-modules`; it is not an unverified set of snippets.

## 8. Candidate Locale, Fallback, and Resolved Locale

A request for `Locale.forLanguageTag("vi-VN")` can follow:

```text
Requested: vi-VN
    |
Candidate: vi_VN (no Messages_vi_VN.properties)
    |
Candidate: vi    (has Messages_vi.properties)
    |
Resolved locale: vi
```

This is a **diagram illustrating a concrete case**, not the complete fallback rules for all locales. `ResourceBundle` may inspect scripts/variants, the root bundle, and the default locale per the API contract when candidates are missing.

Distinguish:

- `requestedLocale`: what the user or program asked for.
- `candidateLocale`: a candidate tried by the loading mechanism.
- `resolvedLocale`: the locale of the bundle actually returned, obtained via `bundle.getLocale()`.

A provider should return `null` when it does not support a candidate so the algorithm can keep trying. Do not return English content for every candidate if the application needs accurate fallback locale awareness.

If a system needs to enforce "only allow vi and en," define the supported language list at the application layer, choose fallback explicitly, and assert against the returned bundle's locale. Do not assume `getBundle` always returns the exact requested locale.

## 9. Service Binding, Module Path, and Encapsulation

`--module-path` specifies where available modules live; it does not tell the JVM to unconditionally load every artifact there into the graph. A provider is used only when its module is **resolved**.

Checks to verify:

1. The app module is launched with `--module`.
2. The API module is in the graph via `requires`.
3. The app has `uses` for the exact service type tied to `baseName`.
4. The provider has the matching `provides` and is present on the module path.
5. The runtime performs service binding or adds the provider via `--add-modules` when needed.
6. The resource path inside the compiled provider module actually exists.

The implementation module does not need to `exports` its package to the app, because the app never imports implementation classes. In the example, the provider reads local resources via `AbstractResourceBundleProvider` without needing `open module`.

That does **not** mean every resource in every module is accessible from any `ClassLoader`. Encapsulation rules of `Module.getResourceAsStream` and private resources must still be respected.

### What Is a Split Package?

JPMS restricts multiple named modules from owning the same Java package. If independent translation modules both place resources/classes in physical package `com.demo.bundle`, the layout can trigger package conflicts. Use separate physical packages, such as `com.demo.impl`, and override `toBundleName` to keep the logical `baseName` stable.

## 10. Comparison with ResourceBundle.Control

`ResourceBundle.Control` is a mechanism for customizing loading, formats, candidate locales, and TTL in classpath/unnamed-module environments. With named modules, using a `Control` instance via `ResourceBundle.getBundle` overloads has restrictions and throws `UnsupportedOperationException` in unsupported cases.

Comparison table:

| Component | Role |
| --- | --- |
| `ResourceBundle.getBundle` | API to fetch a bundle for a base name/locale |
| `ResourceBundleProvider` | SPI allowing bundles to be supplied from provider modules |
| `AbstractResourceBundleProvider` | Base implementation for providers reading `java.properties`/`java.class` |
| `ResourceBundle.Control` | Customizes loading in traditional contexts; does not replace the JPMS SPI |
| `ResourceBundleControlProvider` | Separate SPI for supplying `Control`; not a translation provider for named modules |

When migrating a Java 8 codebase using `Control` to JPMS, review module boundaries, overload calls, and resource architecture. Do not merely copy a `Control` subclass and assume all custom-format loading logic continues working as before.

A provider can construct bundles from XML/JSON or another data source inside `getBundle`. However, `AbstractResourceBundleProvider` only accepts the standard formats it supports; data from other sources requires an appropriate implementation.

## 11. Caching and Multithreaded Safety

`ResourceBundle` caches loaded bundles using its standard mechanism. Therefore:

- Editing a resource file of an already-loaded module/JAR does not guarantee `getBundle` re-reads it immediately.
- Releasing new resources may require an appropriate deploy/restart lifecycle.
- `ResourceBundle.clearCache()` applies to caches within the API-defined scope; do not call it on every request.
- A provider backed by dynamic data sources must have an explicit refresh/version/caching policy rather than relying on ad-hoc file edits.

Standard implementations such as `PropertyResourceBundle` and `ListResourceBundle` ensure thread safety for their default operations. However, a custom provider may hold a `Map`, network client, or mutable cache; protect them when multiple threads access concurrently.

The SPI solves **resource discovery and distribution**; it does not automatically make all internal implementation state thread-safe.

## 12. Diagnosing MissingResourceException

If `ResourceBundle.getBundle("com.demo.bundle.Messages", locale)` fails, check sequentially:

1. Is the **base name** exact and free of file or locale suffixes?
2. Is the service interface named `com.demo.bundle.spi.MessagesProvider` per Java 17 rules?
3. Does the API module export the SPI package?
4. Does the consumer declare `requires com.demo.bundle.api` and `uses com.demo.bundle.spi.MessagesProvider`?
5. Does the provider module declare `provides ... with ...` matching the interface?
6. Does the provider class have a valid constructor and actually implement the interface?
7. Is the provider module present on the module path and resolved?
8. Is the provider's `getBundle` returning `null` due to overly strict `baseName` or `locale` checks?
9. Does `toBundleName` produce the right physical bundle name?
10. Was `Messages_vi.properties` copied into the output at the exact path?
11. Does a matching candidate locale or root bundle exist?
12. Is there a stale cache or is the runtime running a different artifact than what you just built?

If the bundle loads yet `getString("welcome")` fails, investigate the **key**, not the module graph from scratch.

Helpful diagnostic commands:

```bash
java --show-module-resolution --module-path mods \
  --module com.demo.bundle.app/com.demo.app.Main

jar --list --file provider.jar

jar --describe-module --file provider.jar
```

The two `jar` commands assume you have created a modular JAR named `provider.jar`. That is an illustrative name, not a pre-existing file in the demo directory tree before packaging.

## 13. Common Mistakes

| Mistake | Why it fails | Right approach |
| --- | --- | --- |
| Every bundle in a named module needs an SPI | Local bundles can be loaded directly | Use a provider only when separating modules/extensibility |
| Using only `uses ResourceBundleProvider` | Service type name is derived from `baseName` | Create and declare the interface in the `spi` package |
| Naming the provider arbitrarily | Breaks the service-type naming convention | Follow package + `.spi.` + simple name + `Provider` |
| App importing `DemoProvider` | Defeats implementation decoupling | App uses `ResourceBundle` and service declaration |
| Provider omitting `provides` | ServiceLoader needs module metadata | Declare `provides ... with ...` |
| Assuming `javac` copies properties | Compiler does not copy non-Java resources | Copy manually or configure build resource tasks |
| Thinking resource files must match logical package | Provider can map physical names itself | Override `toBundleName` |
| Returning the English bundle for every locale | Masks proper candidates and fallback | Return `null` for unsupported locales |
| Assuming requested locale always equals resolved locale | `vi-VN` may fall back to `vi` | Inspect `getLocale()` |
| Placing provider module on disk is enough | Module must be resolved into the graph | Verify module path and service binding |
| Opening the entire module fixes all errors | Wrong names, paths, and metadata still fail | Fix service/resource contracts properly |
| Using `Control` as on the classpath | Named modules enforce restrictions | Use a provider when needed |
| Editing resource files refreshes the app automatically | Bundles have caching/lifecycles | Manage versioning and refresh explicitly |
| Creating multiple providers for the same locale without a policy | Can depend on discovery order | Avoid overlap or define priority |

## 14. Self-Check Exercises

**Exercise 1 — Service name.** For base name `org.acme.ui.Words`, create the service type following the convention. Write `uses` in the consumer and `provides` in the provider.

**Exercise 2 — Adding French.** Add `Messages_fr.properties` to the implementation module and relax the provider's check. When requesting `Locale.FRANCE` while only the `fr` file exists, what is the resolved locale typically?

**Exercise 3 — Separating packages.** Suppose a German translation provider exists in another module. Place its resources in a separate physical package and override `toBundleName` to avoid a split package.

**Exercise 4 — Checking the build.** Remove the `.properties` copy step from the compile commands. Why can Java code compile cleanly while the runtime lacks the bundle?

**Exercise 5 — Provider resolution.** The provider module is not resolved. Check each condition of the module path, service metadata, and `--add-modules` to find the cause.

**Exercise 6 — Control and provider.** A legacy library used `ResourceBundle.Control` to read XML. When migrating to a named module, how would you structure `ResourceBundleProvider#getBundle`?

**Exercise 7 — Fallback.** Distinguish `requestedLocale = vi-VN`, candidates `vi-VN` and `vi`, and `getLocale() = vi` in the example. How do you test fallback independently of the default locale?

**Exercise 8 — Updating translations.** A service wants to update resources without restarting. Why do caching and named-module lifecycles make simply editing a file insufficient? Propose a versioning/refresh policy.

## 15. Conclusion

**`java.util.spi.ResourceBundleProvider` is the mechanism for supplying bundles across named modules in JPMS.** The consumer module knows the `baseName` and convention-based service type and declares `uses`; the provider module implements the interface and declares `provides ... with ...`. This lets applications add translation packs without depending directly on implementation classes.

`AbstractResourceBundleProvider` helps read `.properties` or class bundles inside the provider module. Overriding `toBundleName` lets resources live in separate physical packages while keeping the logical `baseName` stable. `ResourceBundle` continues handling candidate locales, fallback, and caching; providers must return `null` appropriately and be properly resolved in the module graph.

**Core principle:** *The translation contract lives in the base name and service interface; the implementation module owns the resources. Declare the service properly, package the right files, and verify module resolution and actual resolved locales.*

### API Documentation

- [`ResourceBundleProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [`AbstractResourceBundleProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html)
- [`ResourceBundle` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`ServiceLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
