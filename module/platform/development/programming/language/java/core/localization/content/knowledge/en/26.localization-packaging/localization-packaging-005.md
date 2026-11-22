# Limitations of ResourceBundle.Control in Named Modules

`ResourceBundle` is the standard Java mechanism for locating messages and resources by `Locale`. Before the Java Platform Module System (JPMS), an application typically ran on the **classpath** and could customize bundle lookup using `ResourceBundle.Control`: fallback locale order, file formats, cache duration, reloading, or bundle resolution logic.

Since Java 9, an application can be deployed inside a **named module** with `module-info.java`. Here is the crucial change:

> **In a named module, `ResourceBundle.getBundle(...)` overloads accepting a `ResourceBundle.Control` parameter are not supported and will throw `UnsupportedOperationException`.**

This rule still applies even when the `Control` argument is just a default object obtained from `ResourceBundle.Control.getControl(...)`; no custom subclass is required to trigger the error. Consequently, taking source code that runs on the classpath and merely adding `module-info.java` can break resource bundle customization, even though the `.properties` files still exist.

The right approach depends on the problem:
- If the bundle resides **in the same named module** and uses standard formats, call an overload **without `Control`**, such as `ResourceBundle.getBundle(baseName, locale)`.
- If bundles must be provided **across multiple named modules**, look at the **`ResourceBundleProvider`** mechanism, `ServiceLoader`, and `uses`/`provides` directives in `module-info.java`.
- If you need to read a bundle belonging to **a specific module**, learn `ResourceBundle.getBundle(baseName, locale, Module)` and package encapsulation/opening rules.
- If non-standard formats must be customized, a provider can **load contents itself** or extend `AbstractResourceBundleProvider` for the supported `java.class` / `java.properties` formats; do not assume `Control` will start working again.

This lesson focuses on the **limitations of `ResourceBundle.Control` in named modules**, explaining the architectural rationale, how to detect it, alternative APIs, Java 17+ examples, and a migration checklist to avoid losing localization in modular projects.

## 1. Context: What Problems Do `ResourceBundle` and `Control` Solve?

A typical bundle consists of files such as:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
Messages_fr.properties
~~~

Each file stores key/value pairs for a language:

~~~properties
greeting=Hello
goodbye=Goodbye
~~~

The program requests a bundle by locale:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", Locale.ENGLISH);

System.out.println(bundle.getString("greeting"));
~~~

This is a **snippet inside a method**, requiring imports of `java.util.ResourceBundle` and `java.util.Locale`. `getBundle` looks up a bundle by base name, locale, module/class loader environment, and fallback policy; it does not translate text automatically.

In non-modular applications or on the classpath, `ResourceBundle.Control` was used to customize:
- `getFormats`: the list of formats to try, such as `java.class` or `java.properties`.
- `getCandidateLocales`: candidate locales to check and their order.
- `getFallbackLocale`: fallback locale when no matching bundle is found.
- `getTimeToLive` and `needsReload`: cache and reload policies.
- `newBundle`: bundle creation mechanism, potentially from non-standard formats like XML.

It is a tool for **customizing bundle lookup/creation**, not a class that holds translated text. Migrating an application to JPMS requires revisiting this customization.

## 2. Named Module, Unnamed Module, and Classpath

| Deployment type | Characteristics | Relation to `Control` |
| --- | --- | --- |
| **Unnamed module** | Application classes on the classpath, not belonging to a named module | `getBundle(..., Control)` overloads are designed to work here |
| **Named module** | A module with a name in the module graph, typically declared via `module-info.java` | Overloads taking `Control` are rejected with `UnsupportedOperationException` |
| **Automatic module** | A JAR without a module descriptor placed on the module path for which Java derives a module name | It is a named module; do not casually treat it like the classpath |
| **java.base** | System module containing `ResourceBundle` and `Control` | The `Control` API still exists, but the module context calling `getBundle` enforces the restriction |

A class in an unnamed module can use a `Control` object. When that same class is packaged into a named module, the call taking a `Control` argument becomes unsupported.

**Subtle point:** "A class loader exists" does not mean "running in an unnamed module." Named modules still have class loaders. Checking `getClass().getClassLoader() != null` does not determine whether `ResourceBundle.Control` can be used.

You can check the actual module of the calling class:

~~~java
Module module = MyApp.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

This is a snippet where `MyApp` is an application class. For a named module `demo.app`, `isNamed()` returns `true` and `getName()` is `demo.app`; for an ordinary class on the classpath, the module is typically unnamed, with `isNamed() == false`.

## 3. Which APIs Are Restricted?

Two key overloads:

~~~java
ResourceBundle.getBundle(
        String baseName,
        Locale targetLocale,
        ResourceBundle.Control control);

ResourceBundle.getBundle(
        String baseName,
        Locale targetLocale,
        ClassLoader loader,
        ResourceBundle.Control control);
~~~

These are illustrative method signatures from the Java API, not literal valid Java calls; when calling them, pass **variable values**, not type names.

In Java 17, when **called from a named module**, overloads accepting `ResourceBundle.Control` throw `UnsupportedOperationException`. Do not test only the three-argument overload and try the four-argument overload to "bypass" the restriction: both take `Control`.

The following overloads **do not take `Control` and remain supported under their own contracts**:

~~~java
ResourceBundle.getBundle(baseName);
ResourceBundle.getBundle(baseName, locale);
ResourceBundle.getBundle(baseName, locale, loader);
ResourceBundle.getBundle(baseName, module);
ResourceBundle.getBundle(baseName, locale, module);
~~~

However, "supported" does not mean every overload will find the right bundle. **Base name, caller module, specified loader/module, exports/opens, and provider implementation** still govern resource lookup.

## 4. Do Not Confuse `UnsupportedOperationException` with `MissingResourceException`

The two exceptions reflect two distinct issues:

| Exception | Typical meaning | Resolution |
| --- | --- | --- |
| `UnsupportedOperationException` | Calling a `getBundle` overload taking `Control` from a named module | Change the bundle-loading strategy/API; do not just rename files |
| `MissingResourceException` | No matching bundle or key found per lookup rules | Check base name, locale, path, module encapsulation, provider |
| `IllegalArgumentException` | Depending on the case, invalid `Control`/candidate locales when allowed | Review the `Control` implementation |
| `NullPointerException` | Passing `null` for a required parameter | Validate inputs against the Javadoc |

Suppose a module has a completely valid `Messages_fr.properties`, yet code calls:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_DEFAULT);

ResourceBundle bundle =
        ResourceBundle.getBundle("demo.app.Messages",
                Locale.FRENCH, control);
~~~

In a **named module**, the failure happens **before it even checks whether the resource exists**: the overload taking `Control` itself is unsupported.

**Do not try to "fix" this by adding another `Messages.properties` or changing paths** if the stack trace shows `UnsupportedOperationException` from an overload taking `Control`; fix the API call first.

## 5. Complete Example: A Named Module with Bundles in the Same Module

Assume the project layout:

~~~text
src/
└── demo.app/
    ├── module-info.java
    └── demo/
        └── app/
            ├── Main.java
            ├── Messages.properties
            └── Messages_fr.properties
~~~

**`src/demo.app/module-info.java`**:

~~~java
module demo.app {
}
~~~

**`src/demo.app/demo/app/Main.java`**:

~~~java
package demo.app;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                Main.class.getModule().getName());

        ResourceBundle french = ResourceBundle.getBundle(
                "demo.app.Messages", Locale.FRENCH);

        System.out.println(french.getString("greeting"));

        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        try {
            ResourceBundle.getBundle(
                    "demo.app.Messages", Locale.FRENCH, control);
        } catch (UnsupportedOperationException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

**`src/demo.app/demo/app/Messages.properties`**:

~~~properties
greeting=Hello
~~~

**`src/demo.app/demo/app/Messages_fr.properties`**:

~~~properties
greeting=Bonjour
~~~

In a shell environment with `javac`, `java`, and `cp` (Linux/macOS), from the directory containing `src`:

~~~bash
javac --module-source-path src -d out -m demo.app
cp src/demo.app/demo/app/Messages*.properties out/demo.app/demo/app/
java --module-path out -m demo.app/demo.app.Main
~~~

**Note:** `javac` compiles `.java` sources but does not automatically copy `.properties` files into the output in this workflow. Therefore, the `cp` command is essential; when using Maven/Gradle, configure resource packaging accordingly. On Windows/PowerShell, you can use `Copy-Item` instead of `cp`.

Expected output on JDK 17+:

~~~text
demo.app
Bonjour
UnsupportedOperationException
~~~

Both calls operate on the same bundle name and locale, yet yield different outcomes because of the **overload taking `Control`**. `ResourceBundle.getBundle(baseName, locale)` loads the standard bundle inside the same module, whereas `getBundle(baseName, locale, control)` is blocked by the named-module context.

In this example, there is only one module, so no `opens` or `exports` for an external consumer is needed because code **inside the module** accesses its own resources. Access rules change when resources reside in another module.

## 6. The Classpath Can Still Run the Same `Control` Syntax

When using `ResourceBundle.Control` from an unnamed module (classpath), the API remains valid, especially for supporting non-default formats, fallback, or TTL.

A standalone program running on the classpath:

**`ClasspathControlDemo.java`**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class ClasspathControlDemo {
    public static void main(String[] args) {
        System.out.println(
                ClasspathControlDemo.class
                        .getModule().isNamed());

        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        System.out.println(control.getFormats("Messages"));
        System.out.println(control.getCandidateLocales(
                "Messages", Locale.forLanguageTag("fr-CA")));
    }
}
~~~

Compile and run on the classpath (without creating `module-info.java`):

~~~bash
javac ClasspathControlDemo.java
java -cp . ClasspathControlDemo
~~~

Output on JDK 17:

~~~text
false
[java.class, java.properties]
[fr_CA, fr, ]
~~~

`Control` exists and methods like `getFormats`/`getCandidateLocales` can still be called. **What is restricted is passing `Control` into `ResourceBundle.getBundle` called from a named module**, not that the `ResourceBundle.Control` class was removed from the JDK.

On the classpath, calling `getBundle(..., control)` without matching bundles still throws `MissingResourceException` under normal rules. Do not assume `Control` will always locate a resource.

## 7. Why Did JPMS Change the Bundle Lookup Strategy?

JPMS introduced the **module graph**, **encapsulation**, and **service binding**:
- Each named module defines which packages external code is permitted to access.
- Resources inside a named module's packages can be **encapsulated** per `Module.getResourceAsStream` rules and `ResourceBundle`'s lookup mechanism.
- Global classpath scanning is no longer the sole model for resources.
- For bundles packaged in separate modules, `ResourceBundleProvider` + `ServiceLoader` is the extension mechanism integrated with the module system.

A `ResourceBundle.Control` subclass often intervenes directly in constructing resource names, selecting loaders, or reading resource sources. That does not cleanly substitute for **module visibility** and **service provider discovery** rules.

**Do not try to work around this with a custom `ClassLoader` to bypass module encapsulation.** Beyond being brittle, resource access must obey JPMS contracts and permissions.

During migration, first determine whether the **bundle belongs to the same module** or **is provided by another module**; the solutions differ.

## 8. The Simple Case: Drop `Control`, Keep Standard Bundles in the Same Module

Before modularization, code might have used:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", locale, control);
~~~

This is a snippet where `locale` already exists. `FORMAT_PROPERTIES` specifies searching only for the `java.properties` format in the `Control`-based lookup path. When that code moves into a named module, the overload taking `Control` becomes invalid.

If the program only has standard `.properties` files and **needs no custom behavior**, the updated code is typically:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", locale);
~~~

Ensure the resources are packaged properly inside the **module containing the caller** or resolved under active rules; if they reside in another module, handle module/package access or providers.

**Do not claim that dropping `Control` always preserves identical behavior.** If you previously intentionally restricted lookup to `java.properties`, customized candidate locales, fallback, or TTL, analyze the differences of the default algorithm. Removing the parameter is only the right solution when you do not genuinely depend on a custom `Control`.

## 9. Overloads Taking `Module` in Java 9+

An overload can explicitly specify the module used to look up the bundle:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", Locale.FRENCH, targetModule);
~~~

This is a snippet; `targetModule` is a resolved `Module` object (e.g., `SomeClass.class.getModule()`). It **does not accept `Control`**.

One usage inside a class belonging to the target module:

~~~java
Module mine = MyApp.class.getModule();

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", Locale.FRENCH, mine);
~~~

This is a snippet; `MyApp` is a class in the corresponding module.

**Restriction to remember:** `Module` does not automatically open every package. For bundles in another module, ensure resources are accessible under module encapsulation contracts, or use a provider service by design. Choosing an overload taking `Module` **does not allow** bringing `Control` back.

In particular, the `getBundle(baseName, locale, ClassLoader)` overload has its own rules when the caller is a named module and the class loader matches the caller's loader; do not assume it always emulates classpath behavior. When you know the exact module to access, the overload taking `Module` expresses intent more clearly.

## 10. `exports` Differs from `opens` in module-info

Two directives that are often confused:

- **`exports p;`:** exports a package so other modules can access its **public types** when module relationships permit.
- **`opens p;`:** opens a package for **deep reflection/resource encapsulation** under applicable rules, including scenarios where resources in the package are accessed from other modules.

A `.properties` file typically sits at a path mirroring a package:

~~~text
demo/app/Messages_fr.properties
~~~

If code in **another module** needs to load resources packaged inside a named module's package, merely using `exports` does not guarantee every resource-reading mechanism will succeed. `opens` may be required per `Module.getResourceAsStream` and `ResourceBundle` rules.

Conceptual example in `module-info.java`:

~~~java
module demo.resources {
    opens demo.resources.i18n;
}
~~~

This is an **illustrative directive**; package `demo.resources.i18n` must belong to the module and file paths must be packaged properly. Do not open an entire module with `open module` just to fix one bundle when opening a single controlled package suffices.

**Important:** `opens` does not make `ResourceBundle.getBundle(..., Control)` valid. It addresses **resource visibility**, whereas `UnsupportedOperationException` occurs because the **`Control` API is unsupported in named modules**.

## 11. `ResourceBundleControlProvider` Is Also Ignored in Named Modules

Java also has the SPI:

~~~java
java.util.spi.ResourceBundleControlProvider
~~~

It allows supplying a `ResourceBundle.Control` to alter default behavior when clients invoke `getBundle` overloads without passing `Control` in supported contexts.

However, the Java 17 `ResourceBundle` documentation confirms:

**Implementations of `ResourceBundleControlProvider` are ignored for named modules.**

Therefore, the following "workaround" **is unreliable and unsupported**:

~~~text
Remove the Control parameter directly from getBundle(...)
    ↓
Register ResourceBundleControlProvider
    ↓
Expect this provider to apply the custom Control to a named module
~~~

There is no such "backdoor." `ResourceBundleControlProvider` and `ResourceBundleProvider` are **two different SPIs**:

| SPI | Purpose | Named modules |
| --- | --- | --- |
| `ResourceBundleControlProvider` | Supplies a custom `ResourceBundle.Control` for lookup | Ignored in named modules |
| `ResourceBundleProvider` | Provides `ResourceBundle` via service discovery | The supported direction for named modules |

Do not confuse the `ControlProvider` and `Provider` suffixes and accidentally configure `provides` with the wrong interface.

## 12. `ResourceBundleProvider` Is the Appropriate Replacement

Standard interface:

~~~java
java.util.spi.ResourceBundleProvider
~~~

It defines:

~~~java
ResourceBundle getBundle(String baseName, Locale locale);
~~~

A provider can:
- return a matching `ResourceBundle` or `null` if it does not support the `baseName`/`locale`;
- be declared with `provides ... with ...` in the module containing the implementation;
- be declared by the consuming module with `uses ...`;
- implement bundle-loading logic for standard or custom formats.

`ResourceBundle.getBundle` uses provider discovery via `ServiceLoader` according to JPMS rules.

**Easy mistake:** `ResourceBundleProvider` does not mean simply writing `implements ResourceBundleProvider` on any class and calling it done. Java mandates a **service type name derived from the base name**:
- Base name `com.example.app.Messages`;
- Service interface must be named `com.example.app.spi.MessagesProvider`.

Formula:

~~~text
<package of baseName>.spi.<simple name of baseName>Provider
~~~

Thus `Messages` in `com.example.app` corresponds to `com.example.app.spi.MessagesProvider`. This is a **specific service type**, not merely referencing the generic `java.util.spi.ResourceBundleProvider` interface in `module-info.java`.

## 13. Example of Declaring the Service Interface Correctly

Suppose the base name is:

~~~text
com.example.app.Messages
~~~

**File `com/example/app/spi/MessagesProvider.java`**:

~~~java
package com.example.app.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
~~~

In the consuming module, **`module-info.java`** must declare:

~~~java
module com.example.app {
    exports com.example.app.spi;
    uses com.example.app.spi.MessagesProvider;
}
~~~

`exports` allows the provider-implementing module to reference the public service interface. `uses` declares that the consuming module consumes that service; this is essential for `ResourceBundle.getBundle` to locate providers in the module graph.

On the implementation side, another module needs:

~~~java
module com.example.translation {
    requires com.example.app;

    provides com.example.app.spi.MessagesProvider
        with com.example.translation.MessagesProviderImpl;
}
~~~

**Note:** These are excerpts of a multi-module project structure, not a complete standalone program. Class `MessagesProviderImpl` must exist, implement the interface properly, and be packaged inside the provider module. Implementation details are illustrated in the next section.

Do not declare `provides java.util.spi.ResourceBundleProvider with ...` when the actual service type `ResourceBundle.getBundle` looks for is `com.example.app.spi.MessagesProvider`.

## 14. `AbstractResourceBundleProvider` Helps Implement Standard Providers

Java provides the class:

~~~java
java.util.spi.AbstractResourceBundleProvider
~~~

This class implements the base mechanics for `ResourceBundleProvider` supporting the **`java.class`** and **`java.properties`** formats. Constructors accept allowed format names; for example:

~~~java
super("java.properties");
~~~

Inside an implementation class, this instructs the provider to look only for properties-formatted bundles.

Example in a multi-module structure:

**`com/example/translation/MessagesProviderImpl.java`**:

~~~java
package com.example.translation;

import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

import com.example.app.spi.MessagesProvider;

public final class MessagesProviderImpl
        extends AbstractResourceBundleProvider
        implements MessagesProvider {

    public MessagesProviderImpl() {
        super("java.properties");
    }

    @Override
    public ResourceBundle getBundle(
            String baseName, Locale locale) {

        if (!"com.example.app.Messages".equals(baseName)
                || !Locale.FRENCH.equals(locale)) {
            return null;
        }

        return super.getBundle(baseName, locale);
    }

    @Override
    protected String toBundleName(
            String baseName, Locale locale) {

        return "com.example.translation.Messages_"
                + locale.getLanguage();
    }
}
~~~

The bundle `Messages_fr.properties` can be packaged inside the provider module under the corresponding path:

~~~text
com/example/translation/Messages_fr.properties
~~~

Illustrative contents:

~~~properties
greeting=Bonjour
~~~

**What must be right during integration:**
1. The service interface follows the exact naming convention from `baseName`.
2. The consumer module has `uses` and the provider module has `provides`.
3. The provider module is **resolved** into the module graph at runtime.
4. The resource is **packaged** at the path returned by `toBundleName`.
5. The provider returns `null` for unsupported locales/baseNames rather than fabricating bundles for every locale.
6. Tests run on the actual module path, not just the classpath.

`AbstractResourceBundleProvider` only supports the formats noted in the API. If XML/JSON or a database source is needed, the implementation can construct an appropriate `ResourceBundle` itself; the abstract class **does not automatically know** how to read arbitrary custom formats.

## 15. Flow of an SPI-Based Call

A sample lookup chain:

~~~text
Consumer named module: com.example.app
    |
    | ResourceBundle.getBundle(
    |    "com.example.app.Messages", Locale.FRENCH)
    v
ResourceBundle derives the service type:
    com.example.app.spi.MessagesProvider
    |
    | module com.example.app: uses ...
    v
ServiceLoader finds the resolved provider module
    |
    | module com.example.translation: provides ...
    v
MessagesProviderImpl.getBundle(baseName, locale)
    |
    +-- bundle available -> ResourceBundle
    |
    +-- unsupported -> null
~~~

This is a **flow diagram**, not a Java statement.

Having the provider implemented in another module does not mean all resources are "exported" as public classes. `ResourceBundleProvider` is a **controlled retrieval interface**; the provider can fetch resources inside its own module and supply messages to the caller.

For systems where multiple modules provide different locales, design resource packages to avoid **split packages** across named modules. You can group resources by language/region or use `toBundleName` to map to the provider module's own package.

## 16. Why Must Split Packages Be Avoided?

JPMS does not permit arbitrarily having **multiple named modules in the same layer contain the same package**. This differs from many pre-Java 9 JAR layouts.

Suppose two modules both attempt to place classes/resources under package:

~~~text
com/example/app/i18n/
~~~

If they also place classes of the same package into different modules, the layout causes split-package conflicts. Even with resources alone, package rules and lookup behavior must be examined carefully.

An organization that is usually easier to manage:

~~~text
French provider:
    com/example/translation/fr/Messages_fr.properties

Japanese provider:
    com/example/translation/ja/Messages_ja.properties
~~~

Each provider can customize `toBundleName` to map the logical `baseName` to an actual location **without overlapping packages across named modules**. Do not split modules by locale without checking package layout and service discovery mechanics.

If a single application module holds all `Messages_en.properties`, `Messages_fr.properties`, and `Messages_vi.properties` bundles, there is no need to use the SPI to scatter resources. Keep the design simple when provider distribution is not required.

## 17. There Is No 1:1 Replacement for Every `Control` Callback

A former `Control` user often wrote:

~~~java
class MyControl extends ResourceBundle.Control {
    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return 5_000;
    }
}
~~~

This is an **illustrative class snippet**, requiring imports of `ResourceBundle` and `Locale` or fully qualified names. `getTimeToLive` specifies a TTL in milliseconds in the `Control` lookup system, not a guarantee that every bundle automatically refreshes after exactly 5 seconds.

When migrating to named modules, `ResourceBundleProvider` has no method with a `getTimeToLive` signature. It is a **bundle-providing model**, not a per-callback clone of `Control`.

Comparison table:

| Legacy `Control` customization | Redesign direction in named modules |
| --- | --- |
| `getFormats` | Standard bundles in module or provider chooses how to load |
| `newBundle` | `ResourceBundleProvider` creates/returns the bundle |
| `toBundleName` | Override `AbstractResourceBundleProvider.toBundleName` if extending that class |
| `getCandidateLocales` | Design locale/fallback support per provider/module contract; do not assume copying the callback verbatim |
| `getFallbackLocale` | Define fallback locale policy and test actual behavior; can be handled at app/provider layer |
| `getTimeToLive` | Manage cache/versioning/reloading at module/application design level instead of relying on Control TTL |
| `needsReload` | Intentional invalidation/reload mechanism in the application or provider |

**Do not promise that `AbstractResourceBundleProvider` supports XML just because `Control.newBundle` previously read XML.** `AbstractResourceBundleProvider` by default only works with the standard formats permitted by its constructor; custom formats require custom implementation logic.

## 18. Caching: `clearCache` Does Not Turn a Named Module into Control

`ResourceBundle` caches by default. APIs include:

~~~java
ResourceBundle.clearCache();
ResourceBundle.clearCache(loader);
~~~

This is a snippet with a `loader` variable of type `ClassLoader`. However, clearing the cache **does not replace** `Control.getTimeToLive`, does not fix `UnsupportedOperationException`, and does not guarantee external sources (databases, config files, remote stores) reload immediately as desired.

A dynamic translation system should define:
- Who owns the source of truth for messages?
- How are translations **versioned**?
- Does caching live in `ResourceBundle`, the provider, or an external service?
- When translations change, does the app fetch new configuration via events, TTL, or a new deployment?
- Must multiple requests avoid seeing mixed translation versions within the same transaction?

According to the Javadoc, `ResourceBundle.clearCache()` also has a **cache scope tied to the caller module**. Therefore, do not assume a `clearCache` call from an arbitrary module clears all resources across every provider/module.

## 19. The Exception Does Not Mean the `.properties` File Is Corrupt

A common migration scenario:

~~~text
Before:
    app.jar on classpath
    ResourceBundle.getBundle(baseName, locale, control)
    -> loads successfully

After:
    add module-info.java
    move to module path
    keep the same getBundle(..., control)
    -> UnsupportedOperationException
~~~

Do not immediately:
- change the charset of `.properties` files;
- rename `Messages_fr.properties`;
- clear the cache;
- add unconditional `opens`;
- merge all translation data into another file;
- download a new Unicode library.

Those steps do not address the primary cause: **overloads taking `Control` are forbidden** in named modules. Only after removing or replacing `Control`, if `MissingResourceException` appears, should you inspect visibility/resource packaging.

In addition, errors when using `ClassLoader` to locate resources may stem from a separate **module encapsulation** issue. Read the stack trace and the invoked overload signature rather than lumping every error into "ResourceBundle doesn't support modules."

## 20. Diagnostic Checklist for Bundle Loading Errors

When an error occurs, verify in order:

1. **Which module is the caller in?** Check `Caller.class.getModule().isNamed()` and `getName()`.
2. **Is a `getBundle` overload taking `Control` being called?** If so from a named module, expect `UnsupportedOperationException`.
3. **Is a legacy `ResourceBundleControlProvider` being used?** Named modules ignore such providers.
4. **Is the bundle in the same module or another module?** If in the same module, try the non-Control API and verify the resource is packaged.
5. **Does the base name match the package/path?** `com.example.app.Messages` corresponds to `com/example/app/Messages_fr.properties` in standard format.
6. **Is the locale or key wrong?** Distinguish missing bundle from missing key.
7. **If in another module, is the package accessible under JPMS?** Check `opens`/resource encapsulation.
8. **If using the SPI, does the service interface follow the naming rule?** `package.spi.SimpleNameProvider`.
9. **Did the consumer declare `uses`?** Did the provider declare `provides`?
10. **Is the provider module resolved in the module graph?** Merely placing a JAR on disk does not guarantee the service runs.
11. **Is the provider returning `null` for the requested locale?** Check candidate locales/fallback.
12. **Is there a split package across provider modules?** Check packages and `toBundleName`.
13. **Were resources copied during build?** `javac` does not automatically copy `.properties` to the output directory.
14. **Are there lingering assumptions about legacy `Control` TTL/auto-reload?** Redesign version/cache management.

This is a **layered** diagnostic process rather than guessing a single failure.

## 21. `UnsupportedOperationException` vs. `MissingResourceException` in Testing

When unit tests run on the classpath while production runs on the module path, tests may **fail to reproduce the error** because the caller is in an unnamed module during tests.

Example scenarios:

| Environment | Caller module | Calling `getBundle(..., Control)` |
| --- | --- | --- |
| Test on classpath | Unnamed | May succeed if resources and `Control` are valid |
| Modular Java runtime | Named | Throws `UnsupportedOperationException` |
| Module-path test | Named | Accurately reproduces the restriction |
| Automatic module on module path | Named | Do not assume classpath behavior |

Therefore in CI:
- Have at least one **integration test running on the module path**.
- Use `java --module-path ... -m module/name.Main` for tests close to production.
- Do not run only `java -cp ...` and conclude `ResourceBundle` integration in named modules is sound.
- Test **same-module bundles**, **provider-module bundles**, **unsupported locales**, and **encapsulated resources**.
- If testing the `Control` lookup path, expect failure in named modules and success on the classpath when demonstrating the difference.

The **caller context** itself is part of the API contract; merely checking that resource files exist is not enough.

## 22. A Diagnostic Program for Module Context

A simple class usable on both the classpath and in a named module:

**`ModuleContextDemo.java`**

~~~java
public class ModuleContextDemo {
    public static void main(String[] args) {
        Module current =
                ModuleContextDemo.class.getModule();

        System.out.println(current.isNamed());
        System.out.println(current.getName());
    }
}
~~~

Compile and run on the classpath:

~~~bash
javac ModuleContextDemo.java
java ModuleContextDemo
~~~

Output:

~~~text
false
null
~~~

Inside a **named module**, the output changes to `true` and the declared module name (after organizing classes/packages and building for JPMS). This example helps distinguish runtime modes without relying on environment variables.

However, do not use `isNamed()` to mindlessly toggle custom `Control` and return inconsistent bundles. It is better to design **two tested compatible paths**, or migrate completely to non-Control/SPI APIs if the product targets named modules.

## 23. Designing Locale Fallback Without Control

In classpath applications, developers might have overridden:

~~~java
@Override
public Locale getFallbackLocale(String baseName, Locale locale) {
    return Locale.ENGLISH;
}
~~~

This is a **snippet from a `ResourceBundle.Control` subclass**, not a method on `ResourceBundleProvider`.

After migration, determine:
- Which bundle is the root/default `Messages.properties`?
- Are `Messages_en`, `Messages_en_US`, and `Messages_fr_CA` variants provided?
- When the requested locale is unsupported, should it fall back to **root**, to **English**, or report an error?
- Should fallback be handled by default `ResourceBundle` rules, the provider, or the calling layer?
- If multiple provider modules support different locales, avoid unintended fallbacks that pull bundles from the wrong module.

Do not assume `ResourceBundleProvider` has a `getFallbackLocale` callback. Providing bundles via providers differs from `Control`; test locale fallback and missing keys on the actual deployed module graph.

## 24. Class-Based Bundles, Properties, and Access Restrictions

For bundles inside named modules, the two standard formats are:
- **`java.properties`:** `Messages_fr.properties` files containing key/value pairs.
- **`java.class`:** classes extending `ListResourceBundle` or `ResourceBundle` per bundle naming rules.

Both are subject to **JPMS access rules**, and an application locating classes/resources in another module does not always behave like the classpath.

Points to note:
- Class-based resources also involve type/class visibility of the bundle class.
- For properties files, package/resource paths must be packaged and checked for accessibility.
- Internal bundles in the same module are usually simpler than bundles distributed across modules.
- When using a provider, resources can remain inside the provider module and be loaded appropriately by the provider.

**Do not use module-wide `opens` as a "blanket fix"** if bundles can stay internal or use a service provider. Broadening the access surface requires reviewing project security and encapsulation requirements.

## 25. Service Discovery and Named Modules

`ServiceLoader` is the foundation of the provider model. With named modules, service discovery depends on the module graph and directives:
- Consumer has `uses service.Type;`.
- Provider has `provides service.Type with implementation.Type;`.
- The provider module is included in the runtime/resolution configuration.
- The implementation can actually be instantiated and return a bundle.

Illustrative integrated launch example (schematic):

~~~bash
java --module-path out --add-modules com.example.translation \
  -m com.example.app/com.example.app.Main
~~~

The command above targets shells supporting `\` line continuation, assuming properly built modules in `out`. `--add-modules` ensures the provider module is resolved in this example. In real applications, services may be resolved via service binding, a custom runtime image, or another module configuration.

If `provides` is right yet the provider is absent from the resolved layer/module graph, `getBundle` still cannot find it. Naming `module-info.java` properly is **necessary but not sufficient** for service discovery.

## 26. Common Mistakes During Migration

| Mistake | Why it fails | Fix |
| --- | --- | --- |
| Keeping `getBundle(..., Control)` | Named modules do not support `Control` overloads | Drop `Control` if no customization is needed; or design a provider |
| Trying `ClassLoader + Control` overload as a workaround | Still takes a `Control` parameter | Do not use that overload in named modules |
| Registering a new `ResourceBundleControlProvider` | This SPI is ignored in named modules | Use `ResourceBundleProvider` when needed |
| Thinking `Control` was removed from the JDK | The class is still present | Distinguish the class API from usage inside named modules |
| Adding `opens` to fix UOE | `opens` does not fix an unsupported overload | Fix the API call first, encapsulation second |
| Using `exports` to expose `.properties` files | Exports public types, insufficient for all resource lookups | Understand `opens`/module access for the scenario |
| Naming the service interface wrong | SPI lookup relies on a convention derived from `baseName` | `package.spi.SimpleNameProvider` |
| Forgetting `uses` or `provides` | `ServiceLoader` cannot locate the provider | Declare in module descriptors |
| Only placing provider JAR on disk | Not guaranteed to be resolved | Check module graph/launch options |
| Forgetting to copy `.properties` | Java compilation does not copy resources automatically | Include resources in output/JAR |
| Packaging multiple providers in the same package | Split-package conflict | Separate packages or customize `toBundleName` |
| Expecting `getTimeToLive` to keep running | `Control` callbacks are not invoked | Design TTL/cache outside `Control` |
| Testing on classpath then deploying on module path | Caller context differs | Modular integration tests |
| Forgetting fallback for missing locales | Unexpected resource/fallback outcome | Test each locale/provider |

## 27. QA Checklist for Modular Multilingual Applications

A minimal test suite:

1. **Same named module:** `getBundle(baseName, locale)` loads valid `.properties`.
2. **`Control` restriction:** `getBundle(baseName, locale, control)` throws `UnsupportedOperationException`.
3. **Classpath reference test:** the `Control` overload still exists and works in an unnamed module.
4. **Localization keys:** the same key yields distinct values across two locales, e.g., French/English.
5. **Missing resource:** when a bundle is absent, `MissingResourceException` is thrown and distinguished from UOE.
6. **Package encapsulation:** another consumer module cannot bypass resource access controls.
7. **Service interface naming:** the service interface follows `package.spi.BaseNameProvider`.
8. **Service binding:** `uses`, `provides`, and resolved provider module are verified.
9. **Provider scope:** provider handles supported locales and returns `null` when unsupported.
10. **Packaging:** resource files exist in actual output/JARs, not just in `src`.
11. **Fallback:** missing locales produce the product-specified outcome.
12. **Caching:** updated messages are picked up per the newly designed cache/reload policy.
13. **No class loader workarounds:** module boundaries remain respected.
14. **Regression:** run on the exact JDK/modular deployment used in production, not only the classpath.

When debugging, log the **non-sensitive** caller module name, base name, and locale. Do not log full translated message contents that could contain user personal data.

## 28. Self-Check Exercises

**Question 1.** Why does code that runs on the classpath throw `UnsupportedOperationException` when moved into a named module?

**Answer:** `ResourceBundle.getBundle` overloads accepting `ResourceBundle.Control` are designed for unnamed modules and are **not supported when called from a named module**.

**Question 2.** If `Messages_fr.properties` is only inside the same named module, is creating a `ResourceBundleProvider` mandatory?

**Answer:** No. You can use `ResourceBundle.getBundle(baseName, Locale.FRENCH)` and package the standard resource file in the right location.

**Question 3.** If the package containing the bundle is already `opens`-ed, will `getBundle(..., Control)` stop throwing UOE?

**Answer:** No. `opens` governs module resource access; it does not lift the restriction on `Control` overloads.

**Question 4.** Can `ResourceBundleControlProvider` replace `ResourceBundleProvider` in named modules?

**Answer:** No. Custom `ResourceBundleControlProvider` implementations are ignored in named modules.

**Question 5.** For `baseName` `com.example.app.Messages`, what should the service type be named?

**Answer:** `com.example.app.spi.MessagesProvider`.

**Question 6.** What does the consumer module declare to use a bundle provider service?

**Answer:** `uses com.example.app.spi.MessagesProvider;`, while the provider declares `provides ... with ...;`.

**Question 7.** Does `AbstractResourceBundleProvider` understand arbitrary XML by default?

**Answer:** No. It supports `java.class`/`java.properties` as API-permitted formats; custom formats require custom implementation.

**Question 8.** If you previously overrode `getTimeToLive` in `Control`, is there an identical callback when moving to the SPI?

**Answer:** No. A provider is not a 1:1 mirror of `Control` callbacks; caching, versioning, and reloading must be designed per requirements.

**Question 9.** How does `MissingResourceException` differ from UOE in this lesson?

**Answer:** `MissingResourceException` means the bundle or key was not found; UOE means the `Control` overload is unsupported in a named module.

**Question 10.** Can you rely on integration tests run with `java -cp` to verify named-module behavior?

**Answer:** No. Tests must run on the **module path**, because unnamed and named modules differ in behavior.

## 29. Recommended Migration Workflow

1. **Inventory all `ResourceBundle.getBundle` calls** and locate any using `Control`, including overloads taking `ClassLoader`.
2. **Map the target module graph** after migration; distinguish named/unnamed callers and local/provider bundles.
3. **For standard bundles in the same module**, switch to non-Control APIs and verify resource packaging, locales, and fallback.
4. **For format customization or cross-module bundles**, design `ResourceBundleProvider`, properly named service types, `uses`/`provides`, and resource loading inside the provider module.
5. **Decompose `Control` callbacks into business requirements**: format, resource location, fallback, TTL/reload; do not attempt to copy the subclass verbatim.
6. **Review encapsulation**: open only necessary packages; do not unconditionally open entire modules or use custom loaders to bypass access checks.
7. **Verify the build** to ensure `.properties` files land in the final artifact; the Java compiler does not always copy them.
8. **Write integration tests on the module path** covering multiple locales, missing bundles, UOE, SPI binding, fallback, and caching.
9. **Monitor in deployment**: distinguish UOE, `MissingResourceException`, and provider resource-loading failures.
10. **If both classpath and module path must be supported**, clearly define both execution paths, versioned tests, and a plan to retire JPMS-incompatible mechanisms.

**Key takeaway:** `ResourceBundle.Control` **was not removed from Java**, but **`ResourceBundle.getBundle` overloads taking `Control` are not supported in named modules**. For standard bundles inside a module, prefer non-Control `getBundle` APIs; for cross-module extensibility or custom formats, use **`ResourceBundleProvider`/`ServiceLoader`** and understand `uses`/`provides`, resource encapsulation, fallback, and caching. This restriction belongs to **JPMS architecture**, not font, charset, or translation file bugs.

**Official Java SE 17 Documentation:**
- [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [ResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [AbstractResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html)
- [ResourceBundleControlProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleControlProvider.html).