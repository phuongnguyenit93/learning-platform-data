# Package Exports and Cross-Module Accessibility in Java (JPMS)

In the Java Platform Module System (JPMS, since Java 9), declaring a class `public` is not enough for code in another module to use it. The module containing the class must **allow the calling module to read it** and **export the package containing the class**. This mechanism establishes clear API boundaries, helping libraries expose only the necessary packages while keeping implementation details internal to the module.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why `public` does not mean "accessible from every module."
- Use `exports`, `exports ... to`, and `requires` to build APIs between named modules.
- Distinguish normal code access from reflection access (`opens`).
- Read compiler errors related to module readability and package visibility.
- Compile, run, and experiment with a multi-module application using `--module-path`.

## 2. Three Conditions to Access a Type from Another Module

Suppose module `com.example.app` wants to use the class `com.example.library.api.Greeting` located in module `com.example.library`. To use the class in normal Java code (for example, `import` and calling a method), all three must be satisfied simultaneously:

1. **Readability:** `com.example.app` *reads* `com.example.library`. The common way is declaring `requires com.example.library;` in the application's `module-info.java`.
2. **Package export:** `com.example.library` exports package `com.example.library.api` to the application module, via `exports com.example.library.api;` or a qualified export allowing that specific module.
3. **Java access rules:** the class must have appropriate visibility, typically `public`; the called constructor, field, or method must also be accessible. `private`, package-private, and `protected` rules still remain in effect.

You can remember it as:

> Cross-module access = calling module reads target module + package is exported to caller + Java member has sufficient visibility.

`requires` establishes the read relationship, while `exports` exposes a package as part of an API. **These two directives solve two different problems.**

### Minimal Example

The library's `module-info.java`:

```java
module com.example.library {
    exports com.example.library.api;
}
```

The application's `module-info.java`:

```java
module com.example.app {
    requires com.example.library;
}
```

Here, `com.example.app` can use `public` types in `com.example.library.api`. If the library also has a `com.example.library.internal` package that is not exported, `public` types in the `internal` package still cannot be accessed directly by the application under JPMS rules.

## 3. `exports` Works at the Package Level

A module can contain many packages. Each `exports` line exposes **one specific package**; it does not automatically expose subpackages.

```java
module com.example.library {
    exports com.example.library.api;
    // Does not export com.example.library.api.internal
    // Does not export com.example.library.impl
}
```

| Declaration | Meaning |
| --- | --- |
| `exports com.example.library.api;` | Modules that read the library can access `public` types in the API package. |
| No `exports` declaration for a package | The package is closed to normal code access from other modules. |
| `exports com.example.library.spi to com.example.plugin;` | Only `com.example.plugin` (if it reads the library) can access `public` types of the SPI package. |
| `opens com.example.library.model;` | Allows deep reflection on this package at runtime; does not make it an API that can be freely `import`ed. |
| `open module com.example.library { ... }` | Opens all packages for reflection; this is a broad choice that should be weighed carefully. |

**Note:** `exports` does not turn a package-private class into `public`, does not bypass `private`, and does not automatically add `requires` to the calling module.

### Inside the Same Module

Different packages *within the same module* do not need `exports` to use each other; they still follow standard Java language access levels. For example, a `public` class in package `impl` can be used by a class in package `api` within the same module even if `impl` is not exported.

## 4. Hands-On Project with Two Named Modules

Directory structure:

```text
src/
├── com.acme.catalog/
│   ├── module-info.java
│   └── com/acme/catalog/
│       ├── api/Product.java
│       └── internal/PriceRule.java
└── com.acme.shop/
    ├── module-info.java
    └── com/acme/shop/Main.java
```

**Library:** `src/com.acme.catalog/module-info.java`

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

**API class:** `src/com.acme.catalog/com/acme/catalog/api/Product.java`

```java
package com.acme.catalog.api;

public final class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

**Internal implementation class:** `src/com.acme.catalog/com/acme/catalog/internal/PriceRule.java`

```java
package com.acme.catalog.internal;

public final class PriceRule {
    public static int discountPercent() {
        return 10;
    }
}
```

`PriceRule` is `public`, but package `com.acme.catalog.internal` is **not exported**.

**Application module:** `src/com.acme.shop/module-info.java`

```java
module com.acme.shop {
    requires com.acme.catalog;
}
```

**Entry point:** `src/com.acme.shop/com/acme/shop/Main.java`

```java
package com.acme.shop;

import com.acme.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Java Book");
        System.out.println(product.getName());
    }
}
```

At the project root directory, using JDK 9 or newer:

```bash
javac --module-source-path src -d mods -m com.acme.catalog,com.acme.shop
java --module-path mods -m com.acme.shop/com.acme.shop.Main
```

Expected output:

```text
Java Book
```

`javac --module-source-path src` tells the compiler the sources are organized by module name; `-d mods` places compiled output in the corresponding module tree. The run command uses `--module-path mods` to locate modules and `-m module/main-class` to select the entry point.

### Attempting to Access an Unexported Package

Edit `Main.java` and add:

```java
import com.acme.catalog.internal.PriceRule;
```

If you call `PriceRule.discountPercent()`, compiling the application module is rejected because `com.acme.catalog` does not export `com.acme.catalog.internal`. The `PriceRule` class being `public` does not change the outcome.

There are two proper design solutions:

- If this is a feature genuinely intended for external callers, provide a stable API in an exported package (for instance, a method in `com.acme.catalog.api`).
- Only if you intentionally want to expose that package directly, add `exports com.acme.catalog.internal;` to the library module. That is an API contract change and should be considered carefully.

In this example, keep `internal` encapsulated and expose the needed behavior through the public API.

## 5. Qualified Exports: Exposing to Specific Modules

Sometimes a library needs to share a specialized package with a partner module without turning it into a general API:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.internal to com.acme.report;
}
```

Then:

- `com.acme.shop` can use the public API, but cannot `import` `com.acme.catalog.internal.PriceRule`.
- `com.acme.report` can use `public` types of the `internal` package **if** that module also declares `requires com.acme.catalog;` (or has an equivalent readability relationship).
- A qualified export does not change the internal access modifiers of classes, constructors, or methods.

This is a deliberate way to open a package to a known set of named modules. It creates a dependency on the target module names; when renaming a module, the declaration must be updated.

## 6. `requires` and `requires transitive` Do Not Replace `exports`

Consider three modules:

```text
com.acme.client  ->  com.acme.facade  ->  com.acme.catalog
```

If `com.acme.facade` declares:

```java
module com.acme.facade {
    requires transitive com.acme.catalog;
    exports com.acme.facade.api;
}
```

and `com.acme.client` declares:

```java
module com.acme.client {
    requires com.acme.facade;
}
```

then `client` reading `com.acme.facade` also causes it to read `com.acme.catalog` thanks to `requires transitive`. However, `client` can still directly access only **the packages that `catalog` exports to `client`**. `requires transitive` propagates module readability; it does not make every package public.

`requires static` is another variant used when a dependency is needed at compile time but optional at runtime; it also does not replace `exports`.

## 7. `exports` and `opens`: Normal Code Access vs. Reflection

Reflection has two distinct usage levels:

- **Normal public access:** external code uses `public` types/members in an exported package; reflection can inspect and invoke public members according to the corresponding access rules.
- **Deep reflection:** a library/framework wants to access non-public members, such as a `private` field via `setAccessible(true)`. With named modules, the package usually must be opened using `opens`, `open module`, or an equivalent runtime opening option.

Example of a module storing data for a framework:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.serializer;
}
```

Here, `com.acme.serializer` is allowed to perform deep reflection on `com.acme.catalog.model`, but the `opens` statement **does not mean** the serializer's source code can `import` and directly call every model class as if it were an exported package. If both permissions are needed, both `exports` and `opens` can be used for the same package.

Do not add `opens` merely to fix a compile-time `import` error; check `requires` and `exports` first.

## 8. Classpath, Module Path, and Accessibility

| Code placement | Encapsulation characteristics |
| --- | --- |
| `--class-path` / `-cp` | Normal code belongs to the *unnamed module*. The classpath application's `module-info.java` is not used to enforce `requires/exports`; traditional Java access rules apply. |
| `--module-path` / `-p` with explicit named module | JPMS enforces readability and exports from `module-info.java`, alongside Java access rules. |
| JAR without `module-info.class` placed on the module path | Can become an *automatic module*, with a name determined from metadata/JAR filename; it has broader read/export compatibility behavior than an explicit module. |

For a classpath application that needs to use a named module on the module path, the target module must also be included in the resolved module set (in some configurations requiring `--add-modules`). Afterward, direct access still depends on whether the package has an appropriate export, such as an unqualified export.

Conversely, an explicit named module cannot simply write `requires` to the classpath's "unnamed module": the unnamed module has no name to declare. When migrating a legacy application to JPMS, check JAR locations, module names, and dependency directions first.

## 9. Reading and Resolving Common Errors

**Error A — Module does not read dependency**

The message usually states that the current module "does not read" the module containing the package, or that the package is not visible due to a missing read relationship.

How to check: Does the application module have `requires module.name;`? Is the dependency on `--module-path` and participating in the module graph? Is the module name spelled correctly?

**Error B — Package is not exported**

The message may look like:

```text
package com.acme.catalog.internal is not visible
(package ... is declared in module com.acme.catalog,
 which does not export it)
```

How to check: Does the library module export **that exact package**? If it is `exports ... to`, is the calling module in the allowed list? Do not confuse a parent package with a subpackage.

**Error C — Java member lacks sufficient access level**

The package may already be exported, yet a `private` constructor, package-private method, or non-`public` class still cannot be called. Fix the Java access modifier design; `exports` cannot be used to bypass it.

**Error D — Framework reflection is blocked**

The runtime message may be `InaccessibleObjectException`. Identify the package containing the accessed member and the module performing reflection; consider `opens package to framework.module;` if genuinely needed.

**Error E — Using temporary opening flags when integrating legacy code**

JVM/compiler flags can be used such as:

```bash
# Temporarily allow a module to access an internal package within a specified scope:
--add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.shop

# Temporarily open a package for deep reflection at runtime:
--add-opens com.acme.catalog/com.acme.catalog.model=com.acme.serializer
```

These are **options placed after the appropriate `java`/`javac` command**, not two standalone shell commands. `--add-opens` is for runtime behavior; `--add-exports` may need to be set at both compile time and runtime depending on the use case. They are useful when diagnosing or maintaining legacy software, but in new designs fix `module-info.java` and APIs instead of keeping bypass flags.

## 10. Principles of Module API Design

1. **Export as little as possible:** only packages intended as stable APIs/SPIs should be exposed; `internal` and `impl` packages are usually kept closed.
2. **Define module boundaries by role:** do not export just because a class is marked `public`; it may need to be `public` for code inside the same module.
3. **Reduce reverse dependencies:** modules consuming APIs depend on exported packages; avoid directly depending on implementation details.
4. **Use qualified exports purposefully:** suitable for integrations with known target module names; note that this creates a permission bound to a specific partner.
5. **Separate reflection from APIs:** use `opens` accurately for frameworks needing deep reflection; do not open the whole module when only one package is needed.
6. **Verify both compile time and runtime:** module path flags, resolved module sets, and `requires/exports` directives must be consistent.

## 11. Self-Check Exercises

**Exercise 1.** Module `m.data` has:

```java
module m.data {
    exports dev.demo.api;
}
```

In `dev.demo.api`, there is a `public class Item` and a `class HiddenHelper`. Module `m.app` declares `requires m.data;`. Can `m.app` use both classes?

**Answer:** It can use `Item` if the called members have appropriate visibility; `HiddenHelper` is package-private, so it cannot be accessed directly from another package even though the package is exported.

**Exercise 2.** Module `m.data` exports `dev.demo.api` but **does not** export `dev.demo.api.internal`. Can a `public` class in `dev.demo.api.internal` be called directly by another module?

**Answer:** No. Exporting a parent package does not mean exporting its subpackages.

**Exercise 3.** `m.app` declares `requires m.data;`, but `m.data` does not export the package containing the type to import. Will adding `requires transitive m.data;` to `m.app` fix it?

**Answer:** No. `requires transitive` only relates to readability propagated to modules that read `m.app`; the target package still needs an appropriate export.

**Exercise 4.** A framework needs to write to a `private` field using reflection in package `dev.demo.model` inside module `m.data`. Should you use `exports dev.demo.model;`?

**Answer:** Exporting alone does not satisfy the requirement for deep reflection on a `private` field. Consider `opens dev.demo.model to framework.module.name;` and keep the opened scope as small as possible.

## Takeaways

A package in a named module only becomes an API for external modules when it has an appropriate `exports` declaration. The consuming module must also read the providing module, and every call remains subject to Java's `public`/`protected`/package-private/`private` rules. For reflection needing deeper access, use `opens` scoped to what is genuinely needed.