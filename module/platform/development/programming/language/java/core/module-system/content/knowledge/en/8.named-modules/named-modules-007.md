# `public` APIs Without `exports` Are Still Restricted in the Java Module System

## 1. Objectives

In the Java Platform Module System (JPMS, since Java 9), a class declared `public` is **not guaranteed** to be usable by another module. When an application runs as **named modules**, external accessibility of a type depends simultaneously on Java access visibility, module readability relationships, and whether the package containing that type is exported.

After this lesson, you will be able to:

- Explain why a `public` class still causes an error when imported from another module.
- Distinguish `public`, `requires`, `exports`, `exports ... to`, and `opens`.
- Build an example consisting of a library module and an application module to observe encapsulation.
- Recognize compile-time errors, runtime access errors, and reflection access errors.
- Design a module's public API without accidentally exposing internal packages.

## 2. Three conditions for another module to call an API

Suppose class `com.acme.engine.internal.MathCore` resides in module `acme.engine` and the calling class resides in module `acme.app`. For normal calls in Java source code, three layers of control must be evaluated:

1. **Java language:** the type and member must have an appropriate access level. `public` permits access under language rules, but is only one condition.
2. **Module readability:** the calling module must be able to read the providing module; for example, `acme.app` declares `requires acme.engine;`.
3. **Exported package:** `acme.engine` must have `exports com.acme.engine.internal;`, or a qualified export dedicated to `acme.app`.

Missing just the third condition means `public class MathCore` still cannot be accessed directly from `acme.app`.

> Rule of thumb: **`public` grants access within Java's access rules; `exports` determines whether a package belongs to the API visible from outside the module.**

`exports` is a **package-level** mechanism, not per-class. Exporting a package does not automatically make package-private classes or `private` members public.

## 3. Hands-on example: a public class in an unexported package

Project structure:

~~~text
src/
├── acme.engine/
│   ├── module-info.java
│   └── com/acme/engine/
│       ├── api/Calculator.java
│       └── internal/MathCore.java
└── acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

**Library module — `src/acme.engine/module-info.java`:**

~~~java
module acme.engine {
    exports com.acme.engine.api;
    // Does not export com.acme.engine.internal
}
~~~

**Exported API — `src/acme.engine/com/acme/engine/api/Calculator.java`:**

~~~java
package com.acme.engine.api;

import com.acme.engine.internal.MathCore;

public final class Calculator {
    private Calculator() {}

    public static int twice(int value) {
        return MathCore.twice(value);
    }
}
~~~

**Internal implementation — `src/acme.engine/com/acme/engine/internal/MathCore.java`:**

~~~java
package com.acme.engine.internal;

public final class MathCore {
    private MathCore() {}

    public static int twice(int value) {
        return value * 2;
    }
}
~~~

Note: both `MathCore` and the `twice` method are `public`. However, the `com.acme.engine.internal` package is not listed in the `exports` statements. `Calculator` is still allowed to call `MathCore`, because the two classes are in **the same module**.

**Application module — `src/acme.app/module-info.java`:**

~~~java
module acme.app {
    requires acme.engine;
}
~~~

**Application using the valid API — `src/acme.app/com/acme/app/Main.java`:**

~~~java
package com.acme.app;

import com.acme.engine.api.Calculator;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Calculator.twice(21));
    }
}
~~~

Compile from the project root directory and run:

~~~shell
javac -d out --module-source-path src -m acme.engine,acme.app
java --module-path out --module acme.app/com.acme.app.Main
~~~

Output:

~~~text
42
~~~

Now try modifying `Main.java` to access `MathCore` directly:

~~~java
import com.acme.engine.internal.MathCore;

// Inside main:
System.out.println(MathCore.twice(21));
~~~

The modification **fails to compile** because the `com.acme.engine.internal` package is not exported by `acme.engine` to `acme.app`. The diagnostic typically looks like:

~~~text
package com.acme.engine.internal is not visible
(package com.acme.engine.internal is declared in module acme.engine,
 which does not export it)
~~~

Even though `acme.app` has `requires acme.engine` and `MathCore` is `public`, the application still lacks permission to access the internal package. This is the **strong encapsulation** feature of named modules.

## 4. Distinguishing `public`, `requires`, and `exports`

| Declaration | Where is it placed? | Meaning |
|---|---|---|
| `public class X` | Java class | Permits access to the type under language rules, provided the path across module boundaries is also valid |
| `public void run()` | Java member | Permits access to the method if the enclosing type itself is accessible and other conditions are satisfied |
| `requires acme.engine;` | `module-info.java` of the consuming module | Creates a read relationship to module `acme.engine` |
| `exports com.acme.engine.api;` | `module-info.java` of the providing module | Exports the package to modules that can read the providing module |
| `exports com.acme.engine.internal to acme.debug;` | `module-info.java` of the providing module | Exports that package only to module `acme.debug` |
| `opens com.acme.engine.internal;` | `module-info.java` of the providing module | Permits reflective access at runtime under `opens` rules; does not grant `import` permission in source code |

Two situations must be distinguished:

- **Same named module:** classes in an unexported package can still be used by code in other packages of **that same module**, as long as `public`/`protected`/package-private/`private` rules allow it.
- **Different named module:** the package must be exported to the calling module, and the calling module must read the providing module. `requires` alone does not replace `exports`.

For example, `exports com.acme.engine.api;` does not mean all packages under the `com.acme.engine` prefix are exported. `com.acme.engine.internal` is a separate package and remains closed.

## 5. When should `exports ... to` be used?

A library may need to expose a technical package to a single known integration module while keeping that package hidden from everything else:

~~~java
module acme.engine {
    exports com.acme.engine.api;
    exports com.acme.engine.internal to acme.debug;
}
~~~

In that case:

- `acme.debug` can use `public` types belonging to `com.acme.engine.internal` if it reads `acme.engine`.
- `acme.app` does not automatically receive that permission.
- Exporting by module name is an intentional exception; changing the receiving module's name requires updating the declaration.

Prefer a stable API in a broadly exported `api` package. Qualified exports are useful when designing private communication between controlled modules, and should not be used to indiscriminately expose every internal package.

## 6. Does `opens` replace `exports`?

**No.** `exports` and `opens` serve two different use cases.

~~~java
module acme.engine {
    exports com.acme.engine.api;
    opens com.acme.engine.internal;
}
~~~

- `exports` permits **normal access** to types and members with appropriate access levels in the exported package, including compile-time and runtime checks.
- `opens` permits **access via reflection at runtime**, including deep reflection when reflection APIs require an open package. It **does not** make `import com.acme.engine.internal.MathCore;` valid in another module.
- `opens p to other.module;` restricts the open permission to the module named `other.module`.
- `open module acme.engine { ... }` opens the module's packages for runtime reflection, but is not synonymous with exporting all packages for normal access.

For frameworks that require reflection to read or write non-public members, configuring `opens` may be necessary; for source code that wants to call a class from another module, check `requires` and `exports`.

### Example: checking module boundaries with the runtime API

From `Main`, since `Calculator` is in an exported API package, we can obtain the module info and query whether the internal package is exported or open to the application module:

~~~java
Module library = Calculator.class.getModule();
Module consumer = Main.class.getModule();

System.out.println(
    library.isExported("com.acme.engine.internal", consumer)
);
System.out.println(
    library.isOpen("com.acme.engine.internal", consumer)
);
~~~

With the initial `module-info.java` in section 3, both results are `false`. That is a check of **the specific relationship between two modules**, rather than guessing access permissions from the `public` keyword in a Java file.

## 7. Understanding common errors accurately

**Compile-time error: `package ... is not visible`.** This is a common sign that the package belongs to a named module but is not exported to the calling module. Check the `exports` declaration in the providing module and `requires` in the consuming module.

**Compile-time error: `module not found`.** Different from an unexported package: here Java cannot find the module on the module path or build configuration. Check the module name and `--module-path`.

**Runtime error: `IllegalAccessError`.** Can occur when bytecode references a class/member that is no longer validly exported by the module at runtime, such as when compile-time and runtime configurations differ. Successful compilation under one configuration should not be treated as proof that every runtime configuration is valid.

**Reflection error: `InaccessibleObjectException`.** Typically appears when an application attempts to use deep reflection, such as `setAccessible(true)`, on a package that has not been properly opened. Check `opens`/`--add-opens` instead of merely adding `exports`.

**Reflection error: `IllegalAccessException`.** Can appear when a reflective call targets a type or member that is inaccessible under the relevant rules. Reflection is not a default shortcut to bypass the encapsulation of named modules.

## 8. `--add-exports` and `--add-opens`: exception tools

Sometimes a legacy application or test tool needs temporary access to an unexported package. The JVM and compiler support options to grant additional access for a single run or compilation.

Example allowing `acme.app` direct access to the internal package:

~~~shell
javac --add-exports acme.engine/com.acme.engine.internal=acme.app -d out --module-source-path src -m acme.engine,acme.app
java --add-exports acme.engine/com.acme.engine.internal=acme.app --module-path out --module acme.app/com.acme.app.Main
~~~

This is a **configuration exception**. When `acme.app` source code actually references `MathCore` directly, appropriate configuration must be ensured at both compile time and runtime.

For reflection, the corresponding runtime option looks like:

~~~shell
java --add-opens acme.engine/com.acme.engine.internal=acme.app --module-path out --module acme.app/com.acme.app.Main
~~~

`--add-opens` serves reflective access; it does not turn a package into an API permitted for `import` at compile time.

Use these options for migration, diagnostics, or controlled testing. If application code depends long-term on a library's internal package, fix the API or module design rather than treating command-line flags as a stable contract.

## 9. Avoiding exposing internal types in exported APIs

Even if `com.acme.engine.api` is exported, the following design is still hard to use from other modules:

~~~java
package com.acme.engine.api;

import com.acme.engine.internal.MathCore;

public class EngineFactory {
    public MathCore create() {
        // Example illustrating return type:
        return null;
    }
}
~~~

`EngineFactory` is accessible, but the signature of `create()` contains the `MathCore` type from an unexported package. External clients may hit type access errors when compiling or using the API. Having `public` in the signature does not automatically export that type.

A better design is to place a stable interface or DTO type in the exported package, so the API returns or accepts **truly public types**:

~~~java
// Package com.acme.engine.api
public interface Operation {
    int apply(int value);
}
~~~

~~~java
// Package com.acme.engine.api
public final class EngineFactory {
    private EngineFactory() {}

    public static Operation doubling() {
        return value -> value * 2;
    }
}
~~~

Here the client only depends on `Operation` and `EngineFactory` in the API package. Algorithm details can change inside the module without forcing clients to depend on `internal`.

Principles to apply when designing modules:

1. Intentionally export packages that serve as the public contract, typically containing interfaces, DTOs, facades, or stable service classes.
2. Keep internal implementation packages unexported, even when classes inside need to be declared `public` for other packages **within the same module** to use.
3. Avoid placing unexported types in parameters, return types, or superclasses/interfaces of APIs facing other modules.
4. Use `opens` for genuine reflection needs and consider `opens ... to` if only one framework/module needs that access.
5. When publishing a library, also verify callability from an **independent consuming module**, not solely the library's internal tests.

## 10. Inspecting modules with JDK tools

After compiling successfully, you can view the module description:

~~~shell
java --module-path out --describe-module acme.engine
~~~

Observe the lines listing exported packages and packages contained in the module. This command helps verify the module configuration in the build under test; the description output may vary slightly across JDK versions.

When encountering errors in a real program, proceed in order:

1. Determine whether the calling code belongs to a **named module** or is running on the classpath/unnamed module.
2. Identify the module that owns the class; verify the exact package name.
3. Check whether the calling module reads the owning module (`requires` or the corresponding readability relationship).
4. Check whether the package is exported via `exports` to the calling module or only `exports ... to` another module.
5. If using reflection, separately check `opens` and any relevant runtime options.

Note: the behavior of an application running purely on the classpath differs from an application running with named modules on the module path. The example in this lesson intentionally places both modules on the module path to observe JPMS's `exports` control.

## 11. Self-check exercises

**Exercise 1.** Module `shop.core` contains `public class Inventory` in package `shop.core.internal`. `shop.frontend` has `requires shop.core;`, while `shop.core` only exports `shop.core.api`. Can `shop.frontend` do `import shop.core.internal.Inventory`?

**Answer:** No. `Inventory` is `public`, but the package containing it is not exported to `shop.frontend`.

**Exercise 2.** Does adding `opens shop.core.internal;` allow the `import` statement in Exercise 1 to compile?

**Answer:** No. `opens` addresses reflective access at runtime; normal imports require the package to be appropriately exported via `exports`.

**Exercise 3.** If `exports shop.core.internal to shop.admin;` is added, can `shop.frontend` use `Inventory`?

**Answer:** No, because the export permission is restricted to `shop.admin`. Module `shop.admin` must also read `shop.core` and obey Java access rules.

**Exercise 4.** Inside `shop.core`, can class `shop.core.api.InventoryService` call a `public` method of `shop.core.internal.Inventory` when the `internal` package is not exported?

**Answer:** Yes, if standard Java access levels are satisfied. The `exports` mechanism controls access **from other modules**; it does not prevent packages in the same module from using each other's `public` classes.

## 12. Key takeaways

- `public` is only an access scope within the Java language; with named modules, external accessibility also depends on **readability** and **exports**.
- `requires` allows one module to read another module; `exports` allows a package to be accessed across module boundaries.
- A `public` class in an unexported package can still be an **internal implementation detail** of a module.
- `opens` serves runtime reflection, whereas `exports` serves normal access; they are not interchangeable.
- Good API design exports a stable surface and keeps internal implementation encapsulated.