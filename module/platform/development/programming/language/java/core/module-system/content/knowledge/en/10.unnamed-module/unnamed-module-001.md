# Unnamed module of the classpath

In the Java Platform Module System (JPMS), classes loaded from the classpath belong to an **unnamed module** associated with the class loader that loaded them. An unnamed module is a module without a name and without a `module-info.java`. It allows traditional Java applications to keep running without immediately migrating to the named module model.

When running an application with `-cp` or `--class-path`, Java does not create a separate named module for each JAR on the classpath. Classes loaded by the same class loader belong to the unnamed module of that class loader. Therefore, JARs on the classpath typically share an unnamed module space, even though they may still reside in separate files.

## 1. How is an unnamed module created?

Each class loader has a corresponding unnamed module. For a normally run application, the application class loader loads classes from the directories and JARs specified on the classpath; those classes belong to the unnamed module of the application class loader.

For example:

```shell
java -cp "app.jar;lib-a.jar;lib-b.jar" com.acme.app.Main
```

On Windows, the classpath separator is a semicolon. On Linux and macOS, use a colon:

```shell
java -cp "app.jar:lib-a.jar:lib-b.jar" com.acme.app.Main
```

Classes that the application class loader loads from `app.jar`, `lib-a.jar`, and `lib-b.jar` all belong to that class loader's unnamed module. Packaging each library into a separate JAR does not automatically make it a named module.

If an application creates its own class loader, classes loaded by that loader belong to the unnamed module associated with that custom loader. Consequently, a single JVM can have multiple unnamed modules, each associated with a different class loader.

## 2. Characteristics of an unnamed module

An unnamed module has several important characteristics:

- **No module name:** it cannot be referenced by name in a `requires` directive.
- **No module descriptor:** there is no `module-info.java` to declare `requires`, `exports`, `opens`, `uses`, or `provides`.
- **Reads other modules:** an unnamed module has broad readability to modules in the relevant configuration/layer, so classpath code can use exported APIs of named modules.
- **Exports its packages:** packages in an unnamed module are exported, so named modules can access them if the named module has readability to the unnamed module.
- **Is an open module:** packages of an unnamed module are open for deep reflection.
- **Does not create package-level encapsulation boundaries like an explicit module:** classpath code continues to rely on Java access modifiers and class loader rules.

These characteristics support compatibility with legacy applications. However, an unnamed module does not provide clear dependency control and package boundaries like an explicit module.

## 3. module-info.class is ignored on the classpath

A JAR can contain `module-info.class` to become an explicit module when placed on the module path. However, when the same JAR is placed on the classpath, the runtime does not use that descriptor to create a named module. The classes are loaded into the class loader's unnamed module.

For example, a JAR has the descriptor:

```java
module com.acme.library {
    exports com.acme.library.api;
}
```

If run as:

```shell
java -cp "app.jar;library.jar" com.acme.app.Main
```

then the module boundaries and `exports` directive of `com.acme.library` are not enforced as they are when the JAR is on the module path. The classpath uses the unnamed module model.

If switched to:

```shell
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

then modular JARs on the module path are resolved into named modules and their descriptors are enforced. A non-exported package can prevent a consumer from accessing it, even if the class inside has the `public` modifier.

Therefore, a library might work on the classpath but raise access errors when moved to the module path. During migration, it is necessary to inspect descriptors, `requires`, `exports`, `opens`, and the actual location of each dependency.

## 4. Distinguishing between an unnamed module and an automatic module

These two concepts are often confused because both can appear when working with legacy libraries without `module-info.class`.

| Characteristic | Unnamed module | Automatic module |
|---|---|---|
| Common source | Classes/JARs loaded from the classpath | JAR without a descriptor placed on the module path |
| Has a module name | No | Yes |
| Has an explicit module descriptor | No | No author-written descriptor; module name and behavior are derived |
| Reads other modules | Broadly, without declaring `requires` | Broad readability to support migration |
| Exported packages | All packages of the unnamed module | All packages of the automatic module |
| Can be `requires`-ed by a named module | Cannot be named because it has no module name | Can declare `requires` using the automatic module name |

Consider a legacy library without `module-info.class`:

- Placed on the classpath: classes belong to the class loader's unnamed module.
- Placed on the module path: the JAR is treated as an automatic module, with a name taken from `Automatic-Module-Name` in the manifest if present, or derived from the JAR filename.

An automatic module is still a named module and can be referenced in `requires`. An unnamed module has no name, so it cannot appear in the `requires` directive of a module descriptor.

## 5. Can a named module read an unnamed module?

The direction of readability is very important when combining the module path and classpath. An unnamed module reads named modules, but a named module does not automatically read unnamed modules. Therefore, a modular application might not be able to access a library that only resides on the classpath.

A named module cannot write:

```java
module com.acme.app {
    requires unnamed;
}
```

There is no name `unnamed` to reference. In a migration scenario where a named module needs to access the classpath, a readability relationship can be added at compile/run time using `--add-reads`:

```shell
java --module-path mods \
     --class-path legacy-library.jar \
     --add-reads com.acme.app=ALL-UNNAMED \
     --module com.acme.app/com.acme.app.Main
```

`ALL-UNNAMED` refers to the relevant unnamed modules at runtime. After adding readability, the application module can reference public types in packages of the unnamed module according to standard Java access rules.

This is a useful transitional solution when legacy libraries cannot yet be modularized. In the long term, libraries should be moved to the module path as explicit or automatic modules, or dependencies should be packaged following a clear modular architecture.

## 6. Example of checking whether a class belongs to an unnamed module

You can check a class's module at runtime using the `Class.getModule()` API:

```java
public class ModuleInfoExample {
    public static void main(String[] args) {
        Module module = ModuleInfoExample.class.getModule();

        System.out.println("Named: " + module.isNamed());
        System.out.println("Name: " + module.getName());
        System.out.println("Class loader: "
            + ModuleInfoExample.class.getClassLoader());
    }
}
```

When the class is loaded from the classpath by the application class loader, the output typically shows:

- `isNamed()` returns `false`.
- `getName()` returns `null`.
- Class loader is the application class loader.

If the class is in a named module on the module path, `isNamed()` returns `true` and `getName()` returns the module name, for example `com.acme.app`.

You can check the module of a specific library:

```java
Module libraryModule = com.acme.legacy.LegacyClient.class.getModule();

System.out.println(libraryModule.isNamed());
System.out.println(libraryModule.getName());
```

This check is more reliable than just looking at the JAR filename, because the same JAR can be placed on the classpath or module path and be handled in two different modes.

## 7. ServiceLoader with the classpath

The traditional SPI mechanism can work on the classpath using configuration files in the `META-INF/services` directory.

Suppose the service interface is:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

Provider implementation:

```java
package com.acme.provider;

import com.acme.spi.GreetingService;

public class EnglishGreetingService implements GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

In the provider JAR, create the file:

```text
META-INF/services/com.acme.spi.GreetingService
```

File contents:

```text
com.acme.provider.EnglishGreetingService
```

The consumer can discover the provider using:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.greet("Java"));
}
```

When running on the classpath, `ServiceLoader` finds providers via `META-INF/services` files and the class loader. When using named modules, the consumer declares `uses` and the provider declares `provides ... with ...` in `module-info.java`. These are the two corresponding registration forms for the two packaging approaches.

## 8. Classpath and limitations when migrating to the module path

The classpath offers high flexibility and compatibility, but does not provide explicit module boundaries:

- Dependencies are not declared with `requires`; the JVM locates classes based on class loaders and classpath order.
- A package can be contributed by multiple JARs; class loading depends on ordering and class loader mechanisms.
- There is no `exports` to restrict which packages can be used by other modules.
- There is no explicit per-module `opens`; the unnamed module opens its packages for deep reflection.
- A JAR with `module-info.class` still does not have its descriptor enforced when running on the classpath.

When migrating from the classpath to the module path, you need to check for split packages, duplicate classes, service providers, resource lookups, and frameworks that rely on classpath scanning. Some legacy libraries assume every dependency can be found via `java.class.path`; that assumption may not hold with the module path.

## 9. Diagnosis and verification

To determine whether a JAR is being used as an unnamed module or a named module, first check the launch command:

```shell
# Classpath: classes are loaded into the class loader's unnamed module
java -cp "app.jar;legacy.jar" com.acme.app.Main

# Module path: resolves named/automatic modules
java --show-module-resolution --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

You can inspect the module descriptor of a JAR:

```shell
jar --describe-module --file legacy.jar
```

If the JAR has no descriptor but is placed on the module path, the tool can display the derived automatic module name. If running on the classpath, use `Class.getModule()` to determine which unnamed module the class actually belongs to.

When a classpath library is inaccessible from a named module, verify whether the calling module has readability to the unnamed module. In transitional cases, consider `--add-reads <module>=ALL-UNNAMED`. When a named module cannot access a package of another named module, check `exports` or qualified exports; if deep reflection is needed, check `opens`.

## 10. When to keep the classpath and when to modularize?

The classpath is suitable for legacy applications, libraries that do not yet support JPMS, or projects that do not yet need modular packaging. It allows rapid integration, though dependencies and package boundaries are less explicit.

Named modules are suitable when you want explicit dependency declarations, control over package APIs, early detection of missing dependencies, and support for minimal runtime images. For libraries without `module-info.java`, an automatic module can serve as a transitional step on the module path. When ready, the author can add an explicit module descriptor.

Do not switch to the module path merely by changing JVM flags. Inspect the entire dependency graph, module names, package exports, reflection, service registration, and how frameworks discover resources.

## 11. Key takeaways

- `public` does not mean a package is exposed across module boundaries.
- The classpath places classes into the class loader's unnamed module; a module descriptor in a JAR is not enforced in this mode.
- An unnamed module has no name, so a named module cannot `requires` it.
- An unnamed module reads named modules and exports its own packages; the reverse direction requires appropriate readability.
- An automatic module has a name and appears on the module path; it is distinct from an unnamed module.
- `requires` establishes readability, `exports` exposes packages, and `opens` grants deep reflection access.
- During migration, inspect the actual artifacts and launch commands rather than relying solely on source code.

The unnamed module serves as a bridge so classpath applications can continue running on a platform with JPMS. Understanding its boundaries helps explain why a public class can be accessible in a traditional application yet restricted when the library is placed in a named module, while also helping choose an appropriate migration path.